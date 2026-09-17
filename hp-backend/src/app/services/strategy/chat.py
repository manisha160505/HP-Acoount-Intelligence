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
import re

from app.core.llm import generate_chat_completion, generate_gpt4o_json_completion
from app.database.mongodb import get_db
from app.observability import steps
from app.services.extractors import grounding
from app.services.retrieval import evidence as ev, index_state, query
from app.services.strategy import personas as strategy_personas

logger = logging.getLogger(__name__)

INDEX = "strategy"
PROMPT_VERSION = 3

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

Label them. Put every statement about the account under a line reading FACTS: and every piece of
advice under a line reading RECOMMENDATION:. Use both labels whenever the answer contains both.
This is not decoration - a seller repeats facts to a customer and weighs recommendations themselves,
and an answer that blurs the two gets the platform's inferences quoted as the customer's own filings.

CITATIONS: each evidence line in the context ends with its own tag in square brackets, shaped
[<document>#c<number>]. EVERY sentence in a FACTS section must end with one.

Copy tags character for character from the context above. Never invent a tag, never adapt one, and
never use a tag that does not appear in the context - a tag written from memory or from an example
resolves to nothing and the whole answer is discarded.

HP RULES:
- You represent HP Inc. Never describe a competitor's product as ours.
- Name an HP product only if it appears in the evidence.
- Never claim {company} already uses HP unless the evidence says so.

IF THE EVIDENCE DOES NOT ANSWER THE QUESTION: say plainly that the platform does not hold it, and
name the closest thing it does hold. That is a correct answer, not a failure.

FORMAT: plain text. UPPERCASE section headers, numbered lists. No markdown, no asterisks, no hashes.
Keep it tight - a seller is reading this between meetings."""


ROLEPLAY_SYSTEM = """You are playing a role so that an HP seller can rehearse a real conversation.

{persona}

You are a SIMULATION OF THIS ROLE at {company}. You are not a named person, you are not speaking for
anyone, and you never claim to be a specific individual. If the seller asks who you are, answer with
the role.

You answer ONLY from the CONTEXT supplied with the question - this account's retrieved evidence. If
something is not in there, the platform does not hold it and neither do you.

HOW YOU SPEAK IS YOURS. Tone, register, how blunt or patient or sceptical this role would be, the
questions you ask back, how you open and close - all of that is yours to write, and it should sound
like the role rather than like a report.

WHAT YOU SAY IS NOT YOURS. Every concern, objection, priority, constraint, vendor, product, number
or piece of context you mention must come from the CONTEXT. You do not know anything else. You do
not have a budget, a timeline, a contract term, a renewal date, a team size, a colleague, a previous
conversation with HP or a personal opinion unless the evidence gives you one. Inventing one to make
the conversation feel real is the single worst thing you can do here - the seller will take it into
a real meeting.

CITATIONS: each evidence line in the context ends with its own tag in square brackets, shaped
[<document>#c<number>]. EVERY sentence in which you say something substantive must end with the tag
of the line it came from. Cite several when a sentence rests on several: [a#c1, b#c2].

Copy tags character for character from the context above. Never invent a tag, never adapt one, and
never use a tag that does not appear in the context - a tag written from memory is rejected and the
whole reply is discarded.

Say what the line you tagged actually says, in your own register. A checker compares each sentence
against the evidence you tagged it with, so tagging a line that does not support what you said fails
exactly as inventing the claim would.

Questions you ask the seller need no tag. Short conversational replies - "go on", "fair enough" -
need no tag. Every other sentence needs one.

IF THE SELLER ASKS SOMETHING THE EVIDENCE DOES NOT COVER: say so in character - that it is not
something this role can speak to, or not something you have in front of you. Do not guess and do not
fill the gap. That is a correct answer, not a failure.

HP RULES:
- The seller represents HP Inc. You do not. Never argue HP's case for them.
- Name a product only if it appears in the evidence.
- Never concede that {company} already uses HP unless the evidence says so.

FORMAT: plain text, first person, as spoken. No stage directions, no narration, no markdown, no
asterisks, no hashes. Do not prefix your lines with a name or a role label."""


def _system_prompt(company: str, persona: dict | None) -> str:
    """Which voice this turn is answered in - the single render point.

    Both prompts go through `str.format`, so a persona block containing a
    literal brace raises here rather than quietly producing a broken prompt.
    `personas.prompt_block` builds from account text, which is why that is worth
    knowing as the failure mode.
    """
    if not persona:
        return ANSWER_SYSTEM.format(company=company)
    return ROLEPLAY_SYSTEM.format(
        company=company, persona=strategy_personas.prompt_block(persona))


# --- validating dialogue ----------------------------------------------------
#
# Roleplay gets its own validator rather than an extra check bolted onto
# `_validate`, because `_validate` is wrong for dialogue in both directions.
#
# It is too strict: `_asserts_facts` treats anything that is not a refusal as
# asserting facts, so "Hmm. Go on." - two words that claim nothing - is rejected
# for citing nothing, retried three times, and surfaces as a failure. A persona
# that cannot say "go on" cannot hold a conversation.
#
# And it is too loose: it needs ONE resolvable citation for a whole answer. A
# persona could tag one sentence and invent three around it - "we are locked
# into a three-year agreement", "my team does not own that", "we looked at this
# last year". None carries a digit, so the figure check never sees them, and a
# seller repeats them in a real meeting.
#
# The rule is that the language may be the role's but the substance must come
# from a source. That is enforced here, per sentence, in Python.

_DIALOGUE_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+")

# Lines that say nothing about the account and need no source. A closed list,
# not a length heuristic: "Our refresh cycle is four years" is short too.
_GLUE_CLAUSE = (
    r"ok|okay|right|sure|fine|hmm+|look|well|go on|go ahead|i see|"
    r"i'm listening|i am listening|understood|noted|fair enough|fair|"
    r"alright|thanks|thank you|carry on|maybe|perhaps|possibly|of course|"
    r"indeed|true|agreed|that is fair|that's fair|say more|and|so|"
    r"let's hear it|let us hear it|i'm all ears|i am all ears|please do")
# Several clauses to a line, because that is how people speak: "Go ahead, I'm
# listening." is two glue clauses joined by a comma and matched none of them
# when the pattern anchored a whole sentence to a single alternative.
_GLUE_RE = re.compile(
    r"^\s*(%s)([\s,;-]+(%s))*[\s.,!?-]*$" % (_GLUE_CLAUSE, _GLUE_CLAUSE), re.I)

# What the prompt asks the persona to say when the evidence does not cover
# something - "that is not something I can speak to". Without this the prompt
# and the gate contradict each other: the persona is instructed to deflect in
# character and then rejected for deflecting without a citation. An answer that
# declines to claim anything has nothing to ground.
_ROLEPLAY_REFUSAL_RE = re.compile(
    r"\b(i (don't|do not|can't|cannot|couldn't|could not) (have|see|speak|"
    r"comment|answer|say|tell|know|recall|share)"
    r"|not something i (can|could)"
    r"|nothing (in front of me|i can (share|speak to))"
    r"|that'?s? not (mine|my call|something i)"
    r"|no information|not in front of me|i'd have to come back"
    r"|i would have to come back|you'?d have to ask)", re.I)

# A word long enough to carry meaning. Used to decide whether a sentence said
# anything at all, and to compare what it said against the evidence it cited.
_CONTENT_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z'-]{3,}|\d{2,}")
_STOPWORDS = frozenset({
    "that", "this", "these", "those", "they", "them", "their", "there", "then",
    "than", "with", "from", "have", "has", "had", "been", "being", "were",
    "will", "would", "could", "should", "what", "when", "where", "which",
    "your", "yours", "our", "ours", "you", "about", "into", "over", "just",
    "like", "want", "need", "know", "think", "said", "says", "tell", "told",
    "here", "very", "much", "more", "most", "some", "any", "not", "but", "and",
    "for", "the", "are", "was", "does", "did", "doing", "going", "get", "got",
})

# Whether a cited sentence must share vocabulary with the evidence it cited.
#
# A tag proves the model ASSERTED an attribution; it does not prove the sentence
# is in that evidence. Nothing in this codebase checked that before - not even
# in advisor mode - and without it a fabricated claim survives simply by
# carrying a plausible tag.
#
# This branch can check it more precisely than a whole-payload design could:
# `evidence.resolve` returns each cited row's own `source_text`, so a sentence
# is compared against the exact line it pointed at rather than against a whole
# section.
#
# It is a flag because it has a real false-positive cost: "That is not my call
# [a#c1]" shares no content word with that line and is rejected, so the persona
# is pushed toward the evidence's own vocabulary and some turns read stiffer.
# Every rejection is logged with the sentence so the rate can be measured
# against real conversations rather than guessed at.
ROLEPLAY_REQUIRE_EVIDENCE_OVERLAP = True


def _content_tokens(text: str) -> set:
    return {t.lower() for t in _CONTENT_TOKEN_RE.findall(text or "")
            if t.lower() not in _STOPWORDS}


def _validate_roleplay(account_id: str, answer: str, passages: list,
                       banned_names: list) -> tuple:
    """(ok, reason, cited_rows, cleaned). The gate for in-character dialogue.

    Same spirit as `_validate`, different unit: a sentence rather than an
    answer. Citations resolve through `evidence.resolve` exactly as they do for
    the advisor, so after-generation account isolation is unchanged, and figures
    go through the same grounding helper on the same passages - roleplay does
    not get a weaker numeric rule.
    """
    body = _text(answer)
    if not body:
        return False, "the model returned nothing", [], ""

    answer = _expand_citations(answer)
    cited = list(dict.fromkeys(_EVIDENCE_REF_RE.findall(answer)))
    resolved, invalid = ev.resolve(account_id, INDEX, cited)
    if invalid:
        return (False,
                "it cited %d evidence id(s) that do not resolve for this account: %s"
                % (len(invalid), ", ".join(invalid[:3])), [], "")

    # No real person is quoted, named or spoken for - not the role being played
    # and not a colleague. Message Evaluator's rule (`evaluator/sources.py`:
    # never what that person "thinks, wants or has said") applied to the whole
    # roster, because "talk to Budi about it" puts words about a named employee
    # into a simulated conversation just as surely as signing with their name.
    for name in (banned_names or []):
        if re.search(r"\b%s\b" % re.escape(name), answer, re.I):
            return (False,
                    "it named a real person (%s) - the role speaks, never the "
                    "individual" % name, [], "")

    source_text = {row.get("evidence_id"): _text(row.get("source_text"))
                   for row in (resolved or [])}

    unsourced, unsupported = [], []
    for raw in _DIALOGUE_SENTENCE_RE.split(_text_block(answer)):
        # The model writes a curly apostrophe about half the time, which made
        # "I'm listening" miss a pattern spelled with a straight one.
        sentence = raw.strip().replace("’", "'")
        if not sentence or _GLUE_RE.match(sentence):
            continue
        if _ROLEPLAY_REFUSAL_RE.search(sentence):
            continue
        bare = _CITATION_RE.sub("", sentence)
        bare = _EVIDENCE_REF_RE.sub("", bare).strip()
        tokens = _content_tokens(bare)
        if not tokens:
            continue

        tags = [t for t in _EVIDENCE_REF_RE.findall(sentence) if t in source_text]
        if not tags:
            # A question asserts nothing, and asking is how this role finds out
            # what the seller is proposing. Requiring a source for "what would
            # switching actually gain us" leaves the persona unable to ask
            # anything the evidence does not already contain, which is the end
            # of the rehearsal.
            #
            # The residue, stated plainly: a question CAN smuggle a claim -
            # "are you asking me to break a three-year agreement?". The figure
            # check and the name ban run over the whole reply and catch the
            # numeric and the named versions. A non-numeric claim phrased as a
            # question is what gets through, and closing it would mean deciding
            # in Python which questions are rhetorical.
            if bare.endswith("?"):
                continue
            unsourced.append(bare)
            continue

        if ROLEPLAY_REQUIRE_EVIDENCE_OVERLAP and not any(
                tokens & _content_tokens(source_text.get(tag, "")) for tag in tags):
            unsupported.append((bare, tags[0]))

    if unsourced:
        return (False,
                "it said %d thing(s) in character with no source: %s"
                % (len(unsourced), " / ".join(s[:70] for s in unsourced[:2])),
                [], "")

    # Figures before the overlap check, so an invented number is reported as an
    # invented number. Both would reject it; only one says why usefully, and the
    # reason is fed straight back as the correction for the next attempt.
    corpus = grounding.corpus_from_texts(passages)
    countable = _EVIDENCE_REF_RE.sub("", _CITATION_RE.sub("", answer))
    unsourced_numbers = corpus.unsourced_numbers(countable)
    if unsourced_numbers:
        return (False,
                "it states figure(s) that are not in the evidence: %s"
                % ", ".join(unsourced_numbers[:4]), [], "")

    if unsupported:
        for sentence, tag in unsupported:
            logger.info("strategy chat (roleplay): %r cited %s but shares "
                        "nothing with it", sentence[:120], tag)
        return (False,
                "it cited evidence that does not support what it said: %s"
                % unsupported[0][0][:90], [], "")

    cleaned = re.sub(r"\*\*(.+?)\*\*", r"\1", _text_block(answer))
    cleaned = re.sub(r"(?<!\*)\*(?!\*)", "", cleaned)
    # A speaker label the model prefixed its own line with - "COO:", "Irvan:".
    # The UI already says who is speaking, and a label is the one place a name
    # would reappear after being kept out of the prompt.
    cleaned = re.sub(r"^\s*[A-Z][A-Za-z ./&-]{2,40}:\s*", "", cleaned)
    return True, "ok", resolved, cleaned.strip()


def _persona_summary(persona: dict | None) -> dict | None:
    """Who the seller is rehearsing with, for the UI to render.

    The name travels HERE and not into the prompt. A seller preparing for a
    meeting is preparing for a person and the screen should say so; the model is
    told only the role, so nothing it writes can be read as that person's own
    words. The disclaimer is the Objection Playbook's, verbatim, because it is
    the same claim about the same data.
    """
    if not persona:
        return None
    return {
        "persona_id": persona.get("persona_id"),
        "name": persona.get("name"),
        "title": persona.get("title"),
        "department": persona.get("department"),
        "influence_type": persona.get("influence_type"),
        "disclaimer": ("A simulation of this role, built from the account's own "
                       "evidence. Not statements made by any contact."),
    }

def _retrieval_query(question: str, persona: dict | None) -> str:
    """What to search for - widened by the role when one is being played.

    On the whole-account design the persona's ammunition is citable by
    construction: everything in its prompt is also in the context. Retrieval
    splits those apart, and the split has a specific failure.

    `personas.resolve` reads the role's objections and pain points straight from
    Mongo, so the persona KNOWS them. The evidence the persona may CITE is
    whatever the question retrieved. Observed: a seller opens with "we can cut
    your refresh cost, what is stopping you?", retrieval returns cost and
    refresh chunks, and the persona answers with the ManageEngine objection it
    holds - which is real, and recorded against this exact role - but cannot
    tag, because that chunk was not fetched. The gate then rejects a true
    statement for being unsourced, and three attempts later the rehearsal stops.

    So the role's own terms join the query. The seller still sees their own
    question; only what is searched for is widened, and it is widened toward
    evidence the account genuinely holds about this role rather than toward
    anything the model fancies.
    """
    if not persona:
        return question
    terms = [question, persona.get("title") or ""]
    terms += [card.get("area") or "" for card in (persona.get("objections") or [])]
    terms += [_text(point) for point in (persona.get("pain_points") or [])[:2]]
    if persona.get("hp_play_focus"):
        terms.append(persona["hp_play_focus"])
    return " ".join(t for t in terms if t).strip()


def _answer_once(company: str, question: str, context: str, messages: list,
                 correction: str = "", persona: dict | None = None) -> str:
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
        _system_prompt(company, persona), turns) or ""


# ---------------------------------------------------------------------------
# Step 5 - validation, which the model cannot talk past
# ---------------------------------------------------------------------------

# One bracket can hold several ids - "[a6_x#c1, a6_y#c2]" - and the model does
# that whenever a sentence rests on two pieces of evidence.
#
# The original pattern required a bracket to contain EXACTLY one id, so a
# multi-id citation matched nothing, and both uses below failed silently:
#
#   * `findall` missed those ids, so they were never resolved. An id that does
#     not exist would pass validation as long as it shared a bracket with one
#     that does, and the sources never reached the published citation list - the
#     UI showed fewer than the answer claimed.
#   * `sub` left the id text in the answer, so the grounding check read the
#     account prefix as a figure. "a6a997c3b_play_daas#c1" contributed "997",
#     and the answer was rejected for stating a number nobody wrote. About one
#     run in five died this way.
#
# Two patterns rather than one: the ids are what gets resolved, the whole
# bracket is what gets removed before counting figures.
_EVIDENCE_REF_RE = re.compile(r"[A-Za-z0-9_]+#c\d+")
_CITATION_RE = re.compile(r"\[[^\[\]]*?[A-Za-z0-9_]+#c\d+[^\[\]]*\]")


# A bracket of citations, whatever is inside it. Parsed rather than matched, so
# that a form nobody anticipated is reported instead of silently skipped.
_CITATION_BRACKET_RE = re.compile(r"\[([^\[\]]*#c\d+[^\[\]]*)\]")
# One reference inside a bracket: a full id, or the shorthand the model uses for
# a second citation from the same document - "c3", "#c3".
_FULL_ID_RE = re.compile(r"^([A-Za-z0-9_]+)#c(\d+)$")
_SHORT_ID_RE = re.compile(r"^#?c(\d+)$")


def _expand_citations(answer: str) -> str:
    """Rewrite abbreviated citations into full evidence ids.

    The model writes a second citation from the same document in shorthand:

        [a6a997c3b_objection_066389c0779d#c2, c3]

    Every step here reads ids with `_EVIDENCE_REF_RE`, which matches a complete
    `doc#cN` and therefore saw only the first half. The consequences were silent
    and all bad: `c3` was never resolved, so it was never validated and never
    reached the seller's source list - the answer quoted a counter-question with
    no citation behind it - and the bracket did not match the UI's pattern
    either, so it rendered raw as `[a6a997c3b_objection_066389c0779d#c2, c3]`.

    Expanding here rather than forbidding it in the prompt: the shorthand is a
    reasonable thing for a model to write, and a rule it breaks once in twenty
    answers would cost a whole regeneration. Normalising is cheap and the
    published answer then carries well-formed ids, which is what the UI and the
    citation list both want.

    A reference that is neither form is left exactly as written, so it reaches
    `resolve` and fails loudly rather than being quietly dropped.
    """
    def expand(match):
        inside, last_doc, out = match.group(1), "", []
        # Comma or semicolon: the model uses both, sometimes in the same answer.
        # Splitting on one of them meant a "[x#c2; c3]" bracket kept its
        # shorthand and the second citation stayed invisible.
        for ref in re.split(r"[;,]", inside):
            ref = ref.strip()
            full = _FULL_ID_RE.match(ref)
            if full:
                last_doc = full.group(1)
                out.append(ref)
                continue
            short = _SHORT_ID_RE.match(ref)
            if short and last_doc:
                out.append("%s#c%s" % (last_doc, short.group(1)))
                continue
            out.append(ref)
        return "[%s]" % ", ".join(o for o in out if o)

    return _CITATION_BRACKET_RE.sub(expand, answer or "")


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
    that opened straight into prose asserted the account's people and figures
    while this returned False, and the uncited-facts check below never ran on
    it. Demonstrated against the live account: "The Chief Financial Officer is
    Someone Invented." - a fabricated name and title, no citation - passed
    validation in 8ms.

    The figure gate still bit, because an invented NUMBER is caught wherever it
    appears. An invented NAME, TITLE or VENDOR had nothing standing in its way,
    and ABX is explicit that those in particular "cannot come from model
    memory".

    The prompt asks for the labels, but a gate a model can disable by omitting a
    header is not a gate. So the label is no longer what decides it.

    The cost of the wide reading is that an answer which is purely advice, with
    no account facts at all, must still cite what the advice rests on. The
    prompt already asks for exactly that, and erring this way rejects an answer
    that was fine rather than publishing one that was not.
    """
    body = _text(answer).lower()
    return not any(phrase in body for phrase in _REFUSAL_PHRASES)


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

    # Shorthand expanded before anything reads the ids. See `_expand_citations`:
    # the model abbreviates a second citation from the same document, and the
    # abbreviated half was invisible to every step below.
    answer = _expand_citations(answer)

    # Every id in the answer, bracketed singly or several to a bracket.
    cited = list(dict.fromkeys(_EVIDENCE_REF_RE.findall(answer)))
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
    # Citations out before figures are counted: an evidence id is not a
    # claim, and its digits are not numbers the model asserted. Bare ids
    # are stripped too, in case one is written outside a bracket.
    countable = _EVIDENCE_REF_RE.sub("", _CITATION_RE.sub("", answer))
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


def answer(account_id: str, messages: list, mode: str | None = None,
           persona_id: str | None = None) -> dict:
    """Answer one question about one account. Returns the published payload.

    With a `persona_id` the chat stops advising and starts rehearsing: it plays
    that stakeholder's ROLE and pushes back, so a seller finds out where the
    pitch breaks before a customer does. The persona is resolved against this
    account only - one belonging to another account does not resolve, and the
    turn is answered as the advisor rather than silently as someone else.

    Every step names and times itself. A question that took nineteen seconds is
    not diagnosable from the request log alone - the only useful question is
    which step took them, and answering it used to mean writing a profiling
    script. The breakdown comes back under `generation.timings`, goes out as one
    structured log line, and opens a span per step for Cloud Trace.
    """
    db = get_db()
    timer = steps.StepTimer()
    with timer.step("persona"):
        persona = (strategy_personas.resolve(account_id, persona_id)
                   if persona_id else None)
    resolved_mode = "roleplay" if persona else (_text(mode) or "advisor")

    with timer.step("index_state"):
        state = index_state.get(account_id, INDEX)
    if state.get("status") not in (index_state.READY, index_state.STALE):
        raise ChatUnavailable(
            "the Strategy index is %s - %s"
            % (state.get("status"), state.get("last_error") or "build it first"))

    with timer.step("company_lookup"):
        company = _text((db["account_widgets"].find_one(
            {"account_id": account_id, "widget_key": "exec_summary_card"}) or {}
        ).get("data", {}).get("company_name")) or "this account"

    # A gpt-4o JSON call whenever there is history to resolve against, and free
    # on the first turn of a conversation - which is why it is timed separately
    # rather than folded into generation.
    with timer.step("resolve_question", turns=len(messages or [])):
        question, topic = _resolve_question(messages)

    if _is_small_talk(question):
        return _greeting(company, question, resolved_mode, persona)

    # Retrieval runs on the RESOLVED question. The history shaped that question
    # and contributes nothing else - what the assistant said earlier is not a
    # source for what it says now.
    #
    # `only_context=True` skips LightRAG's own answer generation. It writes one
    # on every query by default, and we discard it - the answer a seller reads
    # is written afterwards, against validated evidence. Paying for prose we
    # throw away cost about 3 seconds of every question.
    try:
        # `timer` is threaded in deliberately: retrieval runs on a different
        # thread's event loop, where a ContextVar set here is not visible. See
        # observability/steps.py - without this the embedding and LLM timings
        # come back empty and look like "retrieval made no calls".
        with timer.step("retrieval", top_k=TOP_K):
            result = query.ask(account_id, INDEX,
                               _retrieval_query(question, persona),
                               top_k=TOP_K, only_context=True, timer=timer)
    except query.IndexNotReady as exc:
        raise ChatUnavailable(str(exc)) from exc
    except Exception as exc:
        # Retrieval can refuse a question for its own reasons - a query it
        # considers too short, a transient backend error. None of those is a
        # server fault, and a 500 tells a seller nothing. Answer that we could
        # not look it up.
        logger.exception("strategy chat: retrieval failed for %r", question[:80])
        return _unavailable(company, question, topic,
                            "retrieval failed: %s" % exc,
                            mode=resolved_mode, persona=persona)

    # Two different bodies of text, for two different jobs.
    #
    # The model reasons over the GRAPH context - entities and relationships as
    # well as chunks. That is what makes a multi-hop question answerable: "who
    # should I approach about AI workstations" needs a person joined to an
    # intent topic joined to a technology, and no single chunk holds that join.
    # Until now this was retrieved on every question and discarded, so the chat
    # was vector RAG paying for a graph it never read.
    #
    # Figures are still checked against the CHUNKS alone. An entity description
    # is a model's paraphrase written during extraction, not the account's own
    # words, so allowing it to ground a number would let an extraction-time
    # invention be republished as a filed fact. Widening what the model can
    # reason from must not widen what counts as evidence.
    reasoning_context = _reasoning_context(result)
    passages = [p for p in [result.context] if _text(p)]
    if not passages:
        return _unavailable(company, question, topic, "no evidence was retrieved",
                            mode=resolved_mode, persona=persona)

    # Read once, not once per attempt. The roster cannot change between
    # attempts, and a three-attempt rehearsal was making three identical Mongo
    # round trips inside the retry loop.
    banned = strategy_personas.banned_names(account_id) if persona else []

    attempts, correction, last_reason = [], "", "no attempt was made"
    for attempt in range(MAX_VALIDATION_ATTEMPTS):
        with timer.step("generation"):
            raw = _answer_once(company, question, reasoning_context, messages,
                               correction, persona=persona)
        # Local, except for the evidence-registry lookup that resolves each
        # citation - which is a Mongo round trip and worth seeing separately
        # from the model call it follows.
        with timer.step("validation"):
            if persona:
                ok, reason, cited, cleaned = _validate_roleplay(
                    account_id, raw, passages, banned)
            else:
                ok, reason, cited, cleaned = _validate(account_id, raw, passages)
        attempts.append({"attempt": attempt + 1, "accepted": ok, "reason": reason})
        if ok:
            _log_timings(timer, question, accepted=True)
            return {
                "answer": cleaned,
                "question": question,
                "topic": topic,
                "mode": resolved_mode,
                "persona": _persona_summary(persona),
                "citations": [_citation(row) for row in cited],
                "available": True,
                "generation": {
                    "prompt_version": PROMPT_VERSION,
                    "retrieval_mode": result.mode,
                    "index_workspace": result.workspace,
                    "index_stale": result.stale,
                    "attempts": attempts,
                    # Slowest step first. Returned as well as logged because
                    # the person asking "why did that take so long" is usually
                    # looking at the screen, not at the server.
                    "timings": timer.as_dict(),
                },
            }
        last_reason = reason
        correction = reason
        logger.info("strategy chat: attempt %d rejected - %s", attempt + 1, reason)

    # Bounded retries, then stop. A third failure means the evidence does not
    # support the answer the model keeps wanting to give.
    _log_timings(timer, question, accepted=False)
    return _unavailable(company, question, topic, last_reason, attempts,
                        timings=timer.as_dict(),
                        mode=resolved_mode, persona=persona)


def _log_timings(timer, question: str, accepted: bool) -> None:
    """One line per question, carrying the request id the middleware set.

    A rejected answer is logged too, and is the more interesting case: three
    failed attempts means three generations and three validations, and the line
    shows that as `generation 41200ms/3` rather than leaving someone to wonder
    why a question took a minute.
    """
    logger.info("strategy chat timings: %s | %s | %r",
                timer.summary(), "accepted" if accepted else "rejected",
                _text(question)[:80],
                extra={"timings": timer.as_dict(),
                       "total_ms": timer.total_ms(),
                       "accepted": accepted})


# LightRAG assembles its context in this order, and puts the only citable part
# last. `_answer_once` then trims to MAX_CONTEXT_CHARS, which cut the tail.
_CHUNKS_MARKER = "Document Chunks"


def _reasoning_context(result) -> str:
    """The graph context, reordered so the citable evidence survives trimming.

    LightRAG emits entities, then relationships, then the document chunks, then
    the reference list. On a real question that ran to 97,938 characters with
    the chunks not starting until 60,817 - past the trim - so **every one of the
    184 citation tags was cut off**. The model was left holding entity JSON with
    nothing it was allowed to cite, produced a FACTS section with no tags, and
    was rejected three times for stating facts without evidence. It was obeying
    the prompt; the evidence simply was not there.

    So the chunks go first. Whatever is dropped is then graph colour rather than
    the account's own sentences and the tags that make them checkable.

    Falls back to the chunk text alone if the marker is not found, which is the
    safe direction: an answer with less graph reasoning, not one that cannot
    cite. That matters on a LightRAG upgrade, where this heading could change.
    """
    graph = _text_block(getattr(result, "graph_context", ""))
    chunks = _text_block(getattr(result, "context", ""))
    if not graph:
        return chunks

    at = graph.find(_CHUNKS_MARKER)
    if at < 0:
        logger.warning(
            "strategy chat: %r not found in the retrieved context - using chunks "
            "only. Check the LightRAG context format.", _CHUNKS_MARKER)
        return chunks or graph
    return "%s\n\n%s" % (graph[at:], graph[:at])


def _text_block(value) -> str:
    """Like `_text` but keeps the line breaks the context is structured by."""
    return str(value if value is not None else "").strip()


def _is_small_talk(question: str) -> bool:
    """Whether this is an opener rather than a question about the account."""
    stripped = _text(question).lower().strip(" .!?,")
    if len(stripped) < MIN_RETRIEVABLE_CHARS:
        return True
    return stripped in _SMALL_TALK


def _greeting(company: str, question: str, mode: str = "advisor",
              persona: dict | None = None) -> dict:
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
    if persona:
        # In character even here. A seller who opens a rehearsal with "hi"
        # should not be answered by the advisor introducing itself - that
        # breaks the exercise before it starts.
        body = ("You have my attention. I am the %s here. What did you want "
                "to talk about?" % (persona.get("title") or "person you asked for"))
    return {
        "answer": body,
        "question": _text(question),
        "topic": "greeting",
        "mode": mode,
        "persona": _persona_summary(persona),
        "citations": [],
        "available": True,
        "generation": {"prompt_version": PROMPT_VERSION,
                       "reason": "greeting - answered without retrieval",
                       "attempts": []},
    }


def _unavailable(company, question, topic, reason, attempts=None,
                 timings=None, mode: str = "advisor",
                 persona: dict | None = None) -> dict:
    closest = ("You could look at the Stakeholder Map, Tech Landscape or Recent "
               "Signals for the nearest related evidence.")
    body = UNAVAILABLE.format(company=company, closest=closest)
    if persona:
        # Deliberately OUT of character, and the one place the simulation breaks
        # on purpose. This path is reached when attempts failed validation - not
        # when the role legitimately has nothing to say, which the prompt
        # handles in character. Dressing a platform failure as the character
        # stonewalling would read as an in-scene signal ("he is not biting") and
        # teach the seller something about a customer that never happened. The
        # simulation may be empty; it may never be wrong.
        body = ("The rehearsal stopped here. Nothing in %s's retrieved evidence "
                "supports an in-character answer to that, and rather than let "
                "the role invent one I have stopped. Try rephrasing, or switch "
                "to Strategy Advisor to ask directly." % company)
    return {
        "answer": body,
        "question": question,
        "topic": topic,
        "mode": mode,
        "persona": _persona_summary(persona),
        "citations": [],
        "available": False,
        "generation": {"prompt_version": PROMPT_VERSION, "reason": reason,
                       "attempts": attempts or [],
                       "timings": timings or {}},
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
