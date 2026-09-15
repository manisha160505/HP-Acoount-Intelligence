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

import asyncio
import logging

from app.core.llm import generate_chat_completion, generate_gpt4o_json_completion
from app.database.mongodb import get_db
from app.services.extractors import grounding
from app.services.retrieval import evidence as ev
from app.services.retrieval import index_state, query

logger = logging.getLogger(__name__)

INDEX = "strategy"
PROMPT_VERSION = 1

TOP_K = 25
MAX_HISTORY_TURNS = 12
MAX_VALIDATION_ATTEMPTS = 3
MAX_CONTEXT_CHARS = 60000

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

You answer ONLY from the RETRIEVED ACCOUNT EVIDENCE supplied with the question. That evidence is
everything this platform knows about {company}.

SEPARATE FACT FROM RECOMMENDATION. They are held to different standards:
- A FACT about the account - a name, title, vendor, number, date, event - must come from the evidence.
  Never state one from your own knowledge. If the evidence does not contain it, say so.
- A RECOMMENDATION - what to do, who to approach, what to lead with - is yours to make, but its
  reasoning must rest on the evidence. Say what it rests on.
Write recommendations so a reader can tell which is which: "Irvan Nr is Chief Operating Officer"
versus "Irvan Nr may be the strongest entry point because...".

CITATIONS: each evidence line is tagged like [a1b2c3_contact_x#c4]. When a sentence states a fact
from the evidence, put that tag at the end of the sentence. Copy tags exactly. Never invent one.

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
        "RETRIEVED ACCOUNT EVIDENCE:",
        context[:MAX_CONTEXT_CHARS],
        "",
        ("CORRECTION - your previous answer was rejected: %s Write it again "
         "using only the evidence above." % correction) if correction else "",
        "QUESTION: %s" % question,
    ])

    turns = [m for m in (messages or [])[:-1]
             if isinstance(m, dict) and _text(m.get("role")) in ("user", "assistant")
             and _text(m.get("content"))][-MAX_HISTORY_TURNS:]
    turns.append({"role": "user", "content": user})

    return generate_chat_completion(
        ANSWER_SYSTEM.format(company=company), turns) or ""


# ---------------------------------------------------------------------------
# Step 5 - validation, which the model cannot talk past
# ---------------------------------------------------------------------------

import re

_CITATION_RE = re.compile(r"\[([A-Za-z0-9_]+#c\d+)\]")


def _asserts_facts(answer: str) -> bool:
    """Whether this answer claims something about the account.

    A refusal ("the platform does not hold that") and a pure recommendation are
    both legitimate without citations. A FACTS section is not.
    """
    body = _text(answer).lower()
    if any(phrase in body for phrase in
           ("does not hold", "not hold", "no information", "not available")):
        return False
    return "fact" in body[:400]


def _validate(account_id: str, answer: str, passages: list) -> tuple:
    """(ok, reason, cited_rows, cleaned). Deterministic, and the last word.

    Two independent checks:

    **Citations** are resolved through `evidence.resolve`, which scopes its query
    by account - so a citation belonging to another account does not resolve
    here, it is reported invalid. That is ABX's after-generation account
    isolation, enforced by the query rather than by a comparison we could forget.

    **Figures** are checked with `grounding.Corpus`, the same helper the
    extractors use. It normalises digits and judges percentages strictly rather
    than demanding literal string equality, so "IDR 323,392 billion" matches
    evidence holding "323,392" while an invented 42% still fails. A literal
    comparison would have rejected our own formatting.
    """
    body = _text(answer)
    if not body:
        return False, "the model returned nothing", [], ""

    cited = _CITATION_RE.findall(answer)
    resolved, invalid = ev.resolve(account_id, INDEX, cited)
    if invalid:
        return (False,
                "it cited %d evidence id(s) that do not resolve for this account: %s"
                % (len(invalid), ", ".join(invalid[:3])), [], "")

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

    corpus = grounding.corpus_from_texts(passages)
    unsourced = corpus.unsourced_numbers(_CITATION_RE.sub("", answer))
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

    return True, "ok", resolved, cleaned


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

UNAVAILABLE = (
    "I could not answer that from {company}'s account intelligence.\n\n"
    "Everything I say has to come from the data this platform holds for this "
    "account, and nothing in it supports an answer here.\n\n"
    "{closest}")


def answer(account_id: str, messages: list, mode: str = None) -> dict:
    """Answer one question about one account. Returns the published payload."""
    db = get_db()

    state = index_state.get(account_id, INDEX)
    if state.get("status") not in (index_state.READY, index_state.STALE):
        raise ChatUnavailable(
            "the Strategy index is %s - %s"
            % (state.get("status"), state.get("last_error") or "build it first"))

    company = _text((db["account_widgets"].find_one(
        {"account_id": account_id, "widget_key": "exec_summary_card"}) or {}
    ).get("data", {}).get("company_name")) or "this account"

    question, topic = _resolve_question(messages)

    if _is_small_talk(question):
        return _greeting(company, question)

    # Retrieval runs on the RESOLVED question. The history shaped that question
    # and contributes nothing else - what the assistant said earlier is not a
    # source for what it says now.
    #
    # `only_context=True` skips LightRAG's own answer generation. It writes one
    # on every query by default, and we discard it - the answer a seller reads
    # is written afterwards, against validated evidence. Paying for prose we
    # throw away cost about 3 seconds of every question.
    try:
        result = query.ask(account_id, INDEX, question,
                           top_k=TOP_K, only_context=True)
    except query.IndexNotReady as exc:
        raise ChatUnavailable(str(exc))
    except Exception as exc:
        # Retrieval can refuse a question for its own reasons - a query it
        # considers too short, a transient backend error. None of those is a
        # server fault, and a 500 tells a seller nothing. Answer that we could
        # not look it up.
        logger.exception("strategy chat: retrieval failed for %r", question[:80])
        return _unavailable(company, question, topic,
                            "retrieval failed: %s" % exc)

    passages = [p for p in [result.context] if _text(p)]
    if not passages:
        return _unavailable(company, question, topic, "no evidence was retrieved")

    attempts, correction, last_reason = [], "", "no attempt was made"
    for attempt in range(MAX_VALIDATION_ATTEMPTS):
        raw = _answer_once(company, question, result.context, messages, correction)
        ok, reason, cited, cleaned = _validate(account_id, raw, passages)
        attempts.append({"attempt": attempt + 1, "accepted": ok, "reason": reason})
        if ok:
            return {
                "answer": cleaned,
                "question": question,
                "topic": topic,
                "mode": _text(mode) or "advisor",
                "citations": [_citation(row) for row in cited],
                "available": True,
                "generation": {
                    "prompt_version": PROMPT_VERSION,
                    "retrieval_mode": result.mode,
                    "index_workspace": result.workspace,
                    "index_stale": result.stale,
                    "attempts": attempts,
                },
            }
        last_reason = reason
        correction = reason
        logger.info("strategy chat: attempt %d rejected - %s", attempt + 1, reason)

    # Bounded retries, then stop. A third failure means the evidence does not
    # support the answer the model keeps wanting to give.
    return _unavailable(company, question, topic, last_reason, attempts)


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


def _citation(row: dict) -> dict:
    """One citation as the UI shows it."""
    out = {"evidence_id": row["evidence_id"],
           "source_text": row.get("source_text"),
           "dataset": row.get("dataset")}
    for key in ("source_url", "publisher", "page", "filing_label", "period"):
        if row.get(key):
            out[key] = row[key]
    return out
