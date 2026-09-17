"""Strategy Chat - a grounded conversation over the whole account.

The client's framing, from the meeting:

    "the salesman, he will be lazy, he doesn't want to read... you made a story
     from raw data and showed it to me. But now I have to press that button and
     open it. So this is basically, **I can talk to my dashboard**."

ABX Feature 8 attaches the strictest guardrails in the document to that idea:
every factual sentence must map to retrieved evidence, *"named people, titles,
vendors, numbers and events cannot come from model memory"*, account isolation
validated before and after generation, and an information-not-available answer
rather than a guess.

The shape of the pipeline follows from that:

    retrieve  ->  generate  ->  validate deterministically  ->  publish or refuse

**gpt-4o writes the prose and has no authority over any fact in it.** Every
figure is checked against the retrieved passages, every citation is resolved
against the evidence registry, and an answer that fails is retried a bounded
number of times and then replaced by the unavailable response. A validation step
that can be talked past is not a validation step.

Two distinctions this module holds carefully.

**Conversation history resolves references; it is never evidence.** A follow-up
like "how does that compare to last year" is rewritten into a standalone
question using the history, and then that question goes back through retrieval.
What the assistant said three turns ago is not a source.

**A fact and a recommendation are held to different standards.** ABX's example
is exact: *"X is CIO"* needs evidence, while *"X may be a strong entry point"*
needs rationale. No filing will ever say "HP should lead with workstations", so
requiring a source sentence for a recommendation would forbid recommending
anything. What a recommendation needs is reasoning that rests on retrieved
account evidence, and on approved HP product facts where it names a product.
"""

import logging

from app.config.settings import settings
from app.core import gemini
from app.core.llm import generate_gpt4o_json_completion
from app.database.mongodb import get_db
from app.services.extractors import grounding
from app.services.strategy import context as account_context

logger = logging.getLogger(__name__)

PROMPT_VERSION = 1

MAX_HISTORY_TURNS = 12
MAX_VALIDATION_ATTEMPTS = 3

# LightRAG refuses a query under three characters, and a seller opening with
# "hi" is not a malformed request - it is how a conversation starts. Greetings
# and small talk are answered directly, without retrieval, because there is
# nothing to retrieve and a graph query would either fail or return whatever
# happened to embed near the word.
_SMALL_TALK = {
    "hi", "hey", "hello", "yo", "hiya", "morning", "good morning",
    "good afternoon", "good evening", "thanks", "thank you", "ta", "cheers",
    "ok", "okay", "cool", "great", "nice", "sure", "bye", "goodbye",
    "who are you", "what can you do", "help", "what do you do",
}
MIN_RETRIEVABLE_CHARS = 3


class ChatUnavailable(Exception):
    """The chat cannot answer, and the reason is worth showing a seller."""


def _text(value) -> str:
    return " ".join(str(value if value is not None else "").split())


# ---------------------------------------------------------------------------
# Step 1 - what is being asked
# ---------------------------------------------------------------------------

# The classes ABX names. This is a RANKING HINT and nothing else: every document
# stays searchable for every question. A real seller question is usually
# multi-hop - "who should I message for AI PCs" needs stakeholders and intent and
# technology and HP plays at once - and a classifier that narrowed the corpus
# would answer from one of those and sound perfectly confident doing it.
QUESTION_CLASSES = ("stakeholder", "priority", "technology", "objection",
                    "opportunity", "evidence", "general")

RESOLVE_SYSTEM = """You rewrite a follow-up question so it stands on its own.

You are given a conversation and its latest question. Replace pronouns and implicit
references ("that", "them", "last year", "the second one") with what they refer to,
using the conversation.

Rules:
- Change nothing else. Keep the seller's wording and intent.
- Add no facts, figures, names or products that are not already in the conversation.
- If the question already stands alone, return it unchanged.

Return JSON only: {"question": "...", "topic": "one of: stakeholder, priority, technology, objection, opportunity, evidence, general"}"""


def _resolve_question(messages: list) -> tuple:
    """(standalone_question, topic). History is used here and nowhere else.

    The rewritten question is what gets retrieved against. That keeps the
    conversation useful for reference-resolution without ever letting it act as
    a source: whatever it resolves to still has to be found in the account's
    evidence before it can be said back.
    """
    latest = ""
    for message in reversed(messages or []):
        if isinstance(message, dict) and _text(message.get("role")) == "user":
            latest = _text(message.get("content"))
            break
    if not latest:
        raise ChatUnavailable("no question was asked")

    history = [m for m in (messages or []) if isinstance(m, dict)][:-1]
    if not history:
        return latest, "general"

    rendered = "\n".join(
        "%s: %s" % (_text(m.get("role")).upper(), _text(m.get("content"))[:800])
        for m in history[-MAX_HISTORY_TURNS:]
        if _text(m.get("role")) in ("user", "assistant") and _text(m.get("content")))

    raw = generate_gpt4o_json_completion(
        RESOLVE_SYSTEM,
        "CONVERSATION:\n%s\n\nLATEST QUESTION: %s\n\nReturn JSON only."
        % (rendered, latest)) or {}

    question = _text(raw.get("question")) or latest
    topic = _text(raw.get("topic")).lower()
    return question, (topic if topic in QUESTION_CLASSES else "general")


# ---------------------------------------------------------------------------
# Step 4 - the answer
# ---------------------------------------------------------------------------

ANSWER_SYSTEM = """You are an ABM strategy assistant for HP Inc., helping an HP seller plan their approach to {company}.

You answer ONLY from the ACCOUNT DATA supplied with the question. That is the finished output of
every intelligence feature this platform runs on {company} - its filings and priorities, its people,
its technology, its intent signals, recent events, opportunity plays, objections and messaging - and
it is everything the platform knows about them. If something is not in there, the platform does not
hold it.

SEPARATE FACT FROM RECOMMENDATION. They are held to different standards:
- A FACT about the account - a name, title, vendor, number, date, event - must come from the evidence.
  Never state one from your own knowledge. If the evidence does not contain it, say so.
- A RECOMMENDATION - what to do, who to approach, what to lead with - is yours to make, but its
  reasoning must rest on the evidence. Say what it rests on.
Write recommendations so a reader can tell which is which: "Irvan Nr is Chief Operating Officer"
versus "Irvan Nr may be the strongest entry point because...".

Label them. Put every statement about the account under a line reading FACTS: and every piece of
advice under a line reading RECOMMENDATION:. Use both labels whenever the answer contains both.
This is not decoration - a seller repeats facts to a customer and weighs recommendations themselves,
and an answer that blurs the two gets the platform's inferences quoted as the customer's own filings.

CITATIONS: the account data is divided into sections, each introduced by a line reading
===== <section_name> (feature: ...) =====
EVERY sentence in a FACTS section must end with the section it came from, in square brackets - for
example [exec_urgency_score]. Cite several when a sentence rests on several: [a_section, b_section].

Copy section names character for character from those header lines. Never invent one, never adapt
one, and never use a name that does not appear as a header above - a name that does not match a
section is rejected and the whole answer is discarded.

HP RULES:
- You represent HP Inc. Never describe a competitor's product as ours.
- Name an HP product only if it appears in the evidence.
- Never claim {company} already uses HP unless the evidence says so.

IF THE EVIDENCE DOES NOT ANSWER THE QUESTION: say plainly that the platform does not hold it, and
name the closest thing it does hold. That is a correct answer, not a failure.

FORMAT: plain text. UPPERCASE section headers, numbered lists. No markdown, no asterisks, no hashes.
Keep it tight - a seller is reading this between meetings."""


def _answer_once(company: str, question: str, context: str, messages: list,
                 correction: str = "") -> str:
    """One generation attempt."""
    user = "\n".join([
        # Not truncated. The payload is the whole account and it fits the
        # window whole - that is the point of the model choice. A cap here
        # would silently drop whichever feature sorted last, and the answer
        # would be confidently wrong about it rather than visibly short.
        "ACCOUNT DATA:",
        context,
        "",
        ("CORRECTION - your previous answer was rejected: %s Write it again "
         "using only the account data above." % correction) if correction else "",
        "QUESTION: %s" % question,
    ])

    turns = [m for m in (messages or [])[:-1]
             if isinstance(m, dict) and _text(m.get("role")) in ("user", "assistant")
             and _text(m.get("content"))][-MAX_HISTORY_TURNS:]
    turns.append({"role": "user", "content": user})

    return gemini.generate(ANSWER_SYSTEM.format(company=company), turns)


# ---------------------------------------------------------------------------
# Step 5 - validation, which the model cannot talk past
# ---------------------------------------------------------------------------

import re

# A citation names the payload section it came from - "[exec_urgency_score]" -
# and one bracket can hold several when a sentence rests on two sections.
#
# Matched as "a bracket, then whatever keys are inside it", never as a
# separator-delimited list. The model varies the separator run to run: ", " one
# time, "; " the next, sometimes " and ". Every pattern that anticipated one
# separator rendered the others raw in the seller's face, and each fix only
# moved the problem to the next variant. Matching the bracket and extracting
# what is in it is indifferent to what sits between.
#
# A section key must contain an underscore. That is what separates a cited
# section from ordinary bracketed prose: every widget key is snake_case
# (`exec_key_metrics`, `news_signals_feed`), and "[see below]", "[TBD]" and
# "[1]" are not. A length rule alone is not enough - "below" passed one.
#
# The trade is explicit: a widget key with no underscore would not be seen as a
# citation. All twenty-five have one, and the failure would be loud rather than
# silent - the sentence would be read as uncited and the answer rejected for
# stating facts without evidence, not published with a broken link.
_SECTION_KEY_RE = re.compile(r"[a-z][a-z0-9]*(?:_[a-z0-9]+)+")
_CITATION_RE = re.compile(
    r"\[[^\[\]]*?[a-z][a-z0-9]*(?:_[a-z0-9]+)+[^\[\]]*\]")


def _section_refs(answer: str) -> list:
    """Every section key cited, in order, deduplicated."""
    out = []
    for bracket in _CITATION_RE.findall(answer or ""):
        for key in _SECTION_KEY_RE.findall(bracket):
            if key not in out:
                out.append(key)
    return out


class _SectionFinder:
    """`findall`-shaped, so `_validate` reads the same as it did."""

    @staticmethod
    def findall(answer):
        return _section_refs(answer)


_SECTION_REF_RE = _SectionFinder()


# `_expand_citations` is gone with the evidence ids it expanded. The model used
# to abbreviate a second citation from the same document ("[doc#c2, c3]") and
# the abbreviated half was invisible to every step that read ids. Section keys
# carry no such shorthand - there is nothing to inherit - so the bracket parser
# above is the whole mechanism.


# A refusal is the one answer that legitimately cites nothing: it asserts
# nothing about the account, so there is nothing to ground.
_REFUSAL_PHRASES = ("does not hold", "not hold", "no information",
                    "not available", "does not have", "does not include",
                    "is not in the account data", "no data")


def _asserts_facts(answer: str) -> bool:
    """Whether this answer claims something about the account.

    Everything except a refusal does. That is deliberately the wide reading.

    This used to return True only when the literal word "fact" appeared in the
    first 400 characters - effectively trusting the model to have written a
    "FACTS:" header before the citation requirement applied to it. An answer
    that opened straight into prose ("PT Astra International Tbk's revenue is
    in the range...") asserted the account's figures while this returned False,
    and the uncited-facts check below never ran on it. The figure gate still
    bit, but an uncited NAME or TITLE - the thing this feature must never
    invent - had nothing standing in its way.

    The prompt now requires the labels, but a gate that a model can talk past by
    omitting a header is not a gate. So the label is no longer what decides it.

    The cost of the wide reading is that an answer which is purely advice, with
    no account facts at all, must still cite what the advice rests on. The
    prompt already asks for exactly that, and erring this way rejects an answer
    that was fine rather than publishing one that was not.
    """
    body = _text(answer).lower()
    return not any(phrase in body for phrase in _REFUSAL_PHRASES)


def _validate(answer: str, payload: str, widget_keys: list) -> tuple:
    """(ok, reason, cited_keys, cleaned). Deterministic, and the last word.

    The model reads the whole account and writes the prose. It has no authority
    over any fact in it, and that is enforced here rather than requested in the
    prompt - a validation step a model can talk past is not a validation step.

    Two independent checks, both unchanged in spirit from the retrieval design:

    **Citations** must name a section that is actually in this payload. The
    payload is built scoped to one account, so a tag naming anything else -
    another account's widget, or one the model invented - does not resolve and
    the answer is sent back. That is the same after-generation isolation the
    evidence registry gave, enforced by membership rather than by a query.

    **Figures** are checked with `grounding.Corpus`, the same helper the
    extractors use, built over the payload itself. It normalises digits and
    judges percentages strictly rather than demanding literal string equality,
    so "IDR 323,392 billion" matches a payload holding 323392 while an invented
    42% still fails. A literal comparison would reject our own formatting.
    """
    body = _text(answer)
    if not body:
        return False, "the model returned nothing", [], ""

    valid = set(widget_keys or [])
    cited = list(dict.fromkeys(_SECTION_REF_RE.findall(answer)))
    invalid = [c for c in cited if c not in valid]
    if invalid:
        return (False,
                "it cited %d section(s) that are not in this account's data: %s"
                % (len(invalid), ", ".join(invalid[:3])), [], "")
    resolved = [c for c in cited if c in valid]

    # An answer that asserts account facts and cites nothing is the failure this
    # feature exists to prevent, and it passes every other check trivially -
    # there are no citations to fail resolution and no figures to fail grounding.
    # Observed: one run produced a four-point FACTS section naming three real
    # people with not a single tag. ABX is explicit that "every factual answer
    # sentence must map to retrieved evidence", so an uncited factual answer is
    # sent back rather than published.
    if not resolved and _asserts_facts(answer):
        return (False,
                "it states facts about the account without citing any evidence",
                [], "")

    corpus = grounding.corpus_from_texts([payload])
    # Citations out before figures are counted. A section tag is not a claim,
    # and a widget key like `exec_key_metrics` contributes no digits - but
    # `intent_topics_table` would have, and a tag is not something the model
    # asserted.
    countable = _CITATION_RE.sub("", answer)
    unsourced = corpus.unsourced_numbers(countable)
    if unsourced:
        return (False,
                "it states figure(s) that are not in the evidence: %s"
                % ", ".join(unsourced[:4]), [], "")

    # The prompt forbids markdown and the model mostly complies, but "**bold**"
    # still slips through - and the UI renders plain text, so a seller sees the
    # asterisks. Stripped here rather than retried over: it is formatting, not a
    # grounding fault, and sending a valid answer back for punctuation would
    # spend a whole generation on nothing.
    cleaned = re.sub(r"\*\*(.+?)\*\*", r"\1", answer)
    cleaned = re.sub(r"(?<!\*)\*(?!\*)", "", cleaned)
    # Markdown headings too. The prompt asks for "FACTS:" and the model mostly
    # writes that, but perhaps one run in three it reaches for "### FACTS"
    # instead - and the UI renders plain text, so the seller reads the hashes.
    # Rewritten to the labelled form rather than just stripped, so a heading
    # stays a heading: "### FACTS" -> "FACTS:".
    cleaned = re.sub(r"^\s{0,3}#{1,6}\s*(.+?)\s*:?\s*$",
                     lambda m: "%s:" % m.group(1).rstrip(":"),
                     cleaned, flags=re.M)

    return True, "ok", resolved, cleaned


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

UNAVAILABLE = (
    "I could not answer that from {company}'s account intelligence.\n\n"
    "Everything I say has to come from the data this platform holds for this "
    "account, and nothing in it supports an answer here.\n\n"
    "{closest}")


def answer(account_id: str, messages: list, mode: str | None = None) -> dict:
    """Answer one question about one account. Returns the published payload."""
    db = get_db()

    company = _text((db["account_widgets"].find_one(
        {"account_id": account_id, "widget_key": "exec_summary_card"}) or {}
    ).get("data", {}).get("company_name")) or "this account"

    question, topic = _resolve_question(messages)

    if _is_small_talk(question):
        return _greeting(company, question)

    # The whole account, in one payload. No retrieval, no index, no graph.
    #
    # The eight contributing features publish about 113,000 tokens of finished
    # JSON between them, which fits the model's window whole - so the question
    # is answered against everything the platform knows rather than against the
    # fragments that happened to resemble it. A multi-hop question no longer
    # depends on one chunk joining a person to a topic to a technology.
    #
    # The resolved question is what gets asked. History shaped it and
    # contributes nothing else: what the assistant said earlier is not a source
    # for what it says now.
    payload, sections = account_context.build(account_id)
    widget_keys = [row["widget_key"] for row in sections]
    if not payload:
        return _unavailable(company, question, topic,
                            "no feature has published anything for this account yet")

    attempts, correction, last_reason = [], "", "no attempt was made"
    for attempt in range(MAX_VALIDATION_ATTEMPTS):
        try:
            raw = _answer_once(company, question, payload, messages, correction)
        except gemini.GeminiTruncated as exc:
            # Named rather than left to the validator, which would have rejected
            # the cut-off answer for a missing citation and spent the remaining
            # attempts reproducing it.
            logger.error("strategy chat: %s", exc)
            return _unavailable(company, question, topic, str(exc), attempts)
        except gemini.GeminiUnavailable as exc:
            return _unavailable(company, question, topic, str(exc), attempts)
        ok, reason, cited, cleaned = _validate(raw, payload, widget_keys)
        attempts.append({"attempt": attempt + 1, "accepted": ok, "reason": reason})
        if ok:
            return {
                "answer": cleaned,
                "question": question,
                "topic": topic,
                "mode": _text(mode) or "advisor",
                "citations": [_citation(key, sections) for key in cited],
                "available": True,
                "generation": {
                    "prompt_version": PROMPT_VERSION,
                    "model": settings.GEMINI_MODEL_NAME,
                    "widgets_in_context": len(widget_keys),
                    "context_chars": len(payload),
                    "attempts": attempts,
                },
            }
        last_reason = reason
        correction = reason
        logger.info("strategy chat: attempt %d rejected - %s", attempt + 1, reason)

    # Bounded retries, then stop. A third failure means the evidence does not
    # support the answer the model keeps wanting to give.
    return _unavailable(company, question, topic, last_reason, attempts)


def _text_block(value) -> str:
    """Like `_text` but keeps the line breaks the context is structured by."""
    return str(value if value is not None else "").strip()


def _is_small_talk(question: str) -> bool:
    """Whether this is an opener rather than a question about the account."""
    stripped = _text(question).lower().strip(" .!?,")
    if len(stripped) < MIN_RETRIEVABLE_CHARS:
        return True
    return stripped in _SMALL_TALK


def _greeting(company: str, question: str) -> dict:
    """The opener, written here rather than retrieved.

    Deterministic on purpose: there is no evidence behind "hello", so there is
    nothing for the validator to check and no reason to spend a retrieval and a
    completion on it. It also states what the assistant is grounded in, which is
    the honest answer to "what can you do".
    """
    body = (
        "Hello. I am your HP ABM strategy assistant for %s.\n\n"
        "I answer from this account's own intelligence - its filings, "
        "stakeholders, technology, intent, recent signals, opportunity plays "
        "and objections - and I cite what I use. If the platform does not hold "
        "something, I will say so rather than guess.\n\n"
        "Try asking who to approach, what to sell, which signals to act on, or "
        "what objections to expect." % company)
    return {
        "answer": body,
        "question": _text(question),
        "topic": "greeting",
        "mode": "advisor",
        "citations": [],
        "available": True,
        "generation": {"prompt_version": PROMPT_VERSION,
                       "reason": "greeting - answered without retrieval",
                       "attempts": []},
    }


def _unavailable(company, question, topic, reason, attempts=None) -> dict:
    closest = ("You could look at the Stakeholder Map, Tech Landscape or Recent "
               "Signals for the nearest related evidence.")
    return {
        "answer": UNAVAILABLE.format(company=company, closest=closest),
        "question": question,
        "topic": topic,
        "mode": "advisor",
        "citations": [],
        "available": False,
        "generation": {"prompt_version": PROMPT_VERSION, "reason": reason,
                       "attempts": attempts or []},
    }


def _citation(widget_key: str, sections: list) -> dict:
    """One citation as the UI shows it.

    `evidence_id` keeps its name even though it now holds a section key. The
    frontend matches the tokens inside a citation bracket against this field to
    place its footnote markers; renaming it would stop every marker rendering
    while the answer itself still looked correct.
    """
    feature = next((row.get("feature_key") for row in (sections or [])
                    if row.get("widget_key") == widget_key), "")
    return {
        "evidence_id": widget_key,
        "source_text": SECTION_LABELS.get(widget_key,
                                          widget_key.replace("_", " ")),
        # The UI prints this as the source's bold label, so it must be the name
        # of the screen a seller can click through to - not the database key.
        "dataset": _feature_label(feature),
        # The key itself, for anything grouping citations by feature.
        "feature_key": feature,
    }


def _feature_label(feature_key: str) -> str:
    """"executive_dashboard" -> "Executive Dashboard".

    Read from the feature mapping rather than duplicated here: that table is
    already the one place a feature's display name is defined, and a second copy
    would drift the moment a feature is renamed in one of them.
    """
    if not feature_key:
        return "Account intelligence"
    from app.api.v1.feature_mapping import FEATURE_MAPPINGS
    entry = FEATURE_MAPPINGS.get(feature_key) or {}
    return entry.get("display_name") or feature_key.replace("_", " ").title()


# What each section is, in a seller's words. A citation reading
# "exec_urgency_score" is a database key; one reading "Urgency score and its
# drivers" answers "where did that come from". A key with no entry falls back to
# itself with the underscores removed, so a new widget is readable rather than
# blocked on someone remembering this table.
SECTION_LABELS = {
    "exec_summary_card": "Account profile and corporate structure",
    "exec_key_metrics": "Reported financials and size bands",
    "exec_strategic_priorities": "Strategic priorities and their filed evidence",
    "exec_urgency_score": "Urgency score and its drivers",
    "exec_hiring_velocity": "Hiring velocity",
    "stakeholder_contacts_grid": "Stakeholder contacts",
    "stakeholder_influence_map": "Buying group and influence",
    "stakeholder_talking_points": "Talking points per stakeholder",
    "news_signals_feed": "Recent news signals",
    "news_relevance_summary": "Why each signal matters",
    "opportunity_narrative_plays": "HP opportunity plays",
    "opportunity_trigger_signals": "Opportunity trigger signals",
    "opportunity_context_card": "Opportunity context",
    "objection_reframe_cards": "Objections and reframes",
    "objection_incumbent_context": "Incumbent vendors behind each objection",
    "technographic_map": "Technology map",
    "technographic_hp_recommendations": "HP product recommendations",
    "tech_stack_matrix": "Installed technology by category",
    "webstack_breakdown": "Public website technology",
    "tech_detections_reference": "Technology detection history",
    "intent_topics_table": "Intent topics",
    "intent_category_summary": "Intent by HP category",
    "intent_hiring_demand": "Hiring demand signal",
    "messaging_pillars_output": "Message house pillars",
    "messaging_context_card": "Messaging context",
}
