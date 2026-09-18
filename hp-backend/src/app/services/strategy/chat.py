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
import time

from app.core.llm import (
    generate_chat_completion, generate_gpt4o_json_completion,
    stream_chat_completion,
)
from app.database.mongodb import get_db
from app.services.extractors import grounding
from app.services.retrieval import evidence as ev, index_state, query

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


def _answer_once_stream(company: str, question: str, context: str, messages: list,
                        correction: str = ""):
    """`_answer_once`, yielding deltas. The prompt is identical."""
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

    yield from stream_chat_completion(ANSWER_SYSTEM.format(company=company), turns)


def _validated_prefix(account_id: str, buffer: str, passages: list) -> tuple:
    """(text safe to publish, whether it validated). Never a partial sentence.

    This is what makes streaming compatible with a guarantee that nothing
    unverified is shown, and the rule is narrow on purpose.

    An answer is released only as far as its last **closed citation bracket**.
    A sentence mid-flight has no citation yet - not because it is wrong, but
    because the model writes the claim before the tag - and releasing it would
    publish a figure the validator has not seen. A fabricated number therefore
    cannot escape: it sits after the last bracket until either a citation
    follows it, at which point it is validated like anything else, or the answer
    ends and the full check rejects it.

    The prefix is validated by the same `_validate` the final answer goes
    through. Nothing is relaxed for streaming - it is the identical function,
    run earlier and more often, which it can afford to be at about 60ms.
    """
    end = buffer.rfind("]")
    if end == -1:
        return "", False
    candidate = buffer[:end + 1]
    ok, _reason, _cited, cleaned = _validate(account_id, candidate, passages)
    return (cleaned, True) if ok else ("", False)


def answer_stream(account_id: str, messages: list, mode: str | None = None):
    """`answer`, yielding the answer as it is written.

    Yields dicts the transport can serialise directly:

        {"type": "stage",  "stage": "retrieving" | "writing" | "checking"}
        {"type": "delta",  "text": "...validated text so far..."}
        {"type": "done",   ...the same payload `answer` returns...}

    The contract `answer` holds is unchanged: a seller never reads a sentence
    that has not been checked against the evidence. What streaming changes is
    *when* the checked sentences arrive - as each one completes, rather than all
    at the end - so the wait is spent reading rather than watching a spinner.

    A rejected answer is never partially published: the final `done` carries the
    validated whole, and a caller that has been rendering deltas replaces what
    it showed with that. Because deltas are only ever validated prefixes of the
    same attempt, in practice the replacement is the same text plus its tail.
    """
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
        yield {"type": "done", **_greeting(company, question)}
        return

    yield {"type": "stage", "stage": "retrieving"}
    try:
        result = query.ask(account_id, INDEX, question,
                           top_k=TOP_K, only_context=True)
    except query.IndexNotReady as exc:
        raise ChatUnavailable(str(exc)) from exc
    except Exception as exc:
        logger.exception("strategy chat: retrieval failed for %r", question[:80])
        yield {"type": "done",
               **_unavailable(company, question, topic, "retrieval failed: %s" % exc)}
        return

    reasoning_context = _reasoning_context(result)
    passages = [p for p in [result.context] if _text(p)]
    if not passages:
        yield {"type": "done",
               **_unavailable(company, question, topic, "no evidence was retrieved")}
        return

    attempts, correction, last_reason = [], "", "no attempt was made"
    for attempt in range(MAX_VALIDATION_ATTEMPTS):
        # Only the first attempt streams. A retry exists because the previous
        # answer was rejected, and the seller is already reading text from it -
        # streaming a second one over the top would rewrite the thread under
        # them. The retry is written silently and replaces what was shown.
        streaming = attempt == 0
        yield {"type": "stage", "stage": "writing" if streaming else "rewriting"}

        if streaming:
            # Validated only when a citation bracket *closes*, not on every
            # token that happens to follow one. `_validate` resolves ids
            # against Mongo at about 70ms, so re-running it per token spent
            # more time checking the same prefix than the model spent writing
            # the answer - 531 calls and 82% of the wall clock, measured.
            # A new `]` is the only event that can extend the safe prefix.
            buffer, published, last_end = "", "", -1
            for chunk in _answer_once_stream(company, question, reasoning_context,
                                             messages, correction):
                buffer += chunk
                end = buffer.rfind("]")
                if end == last_end:
                    continue
                last_end = end
                safe, ok = _validated_prefix(account_id, buffer, passages)
                if ok and len(safe) > len(published):
                    published = safe
                    yield {"type": "delta", "text": published}
            raw = buffer
        else:
            raw = _answer_once(company, question, reasoning_context, messages,
                               correction)

        yield {"type": "stage", "stage": "checking"}
        ok, reason, cited, cleaned = _validate(account_id, raw, passages)
        attempts.append({"attempt": attempt + 1, "accepted": ok, "reason": reason})
        if ok:
            yield {"type": "done", "answer": cleaned, "question": question,
                   "topic": topic, "mode": _text(mode) or "advisor",
                   "citations": [_citation(row) for row in cited],
                   "available": True,
                   "generation": {"prompt_version": PROMPT_VERSION,
                                  "retrieval_mode": result.mode,
                                  "index_workspace": result.workspace,
                                  "index_stale": result.stale,
                                  "attempts": attempts}}
            return
        last_reason = reason
        correction = reason
        logger.info("strategy chat: attempt %d rejected - %s", attempt + 1, reason)

    yield {"type": "done",
           **_unavailable(company, question, topic, last_reason, attempts)}


def answer(account_id: str, messages: list, mode: str | None = None) -> dict:
    """Answer one question about one account. Returns the published payload."""
    # Where the time goes, per stage. A total is not diagnostic here: the same
    # ten seconds can be one slow retrieval or three fast generations thrown
    # away by validation, and those have opposite fixes. `timings` is reported
    # in milliseconds on the payload's `generation` block, which already
    # carries the per-attempt record the durations belong beside.
    t_start = time.perf_counter()
    timings = {}

    def _since(mark):
        return round((time.perf_counter() - mark) * 1000)

    db = get_db()

    state = index_state.get(account_id, INDEX)
    if state.get("status") not in (index_state.READY, index_state.STALE):
        raise ChatUnavailable(
            "the Strategy index is %s - %s"
            % (state.get("status"), state.get("last_error") or "build it first"))

    company = _text((db["account_widgets"].find_one(
        {"account_id": account_id, "widget_key": "exec_summary_card"}) or {}
    ).get("data", {}).get("company_name")) or "this account"

    # A follow-up pays for an LLM rewrite before retrieval even starts, and a
    # first question does not. Timing them together hides that difference.
    _t = time.perf_counter()
    question, topic = _resolve_question(messages)
    timings["resolve_question_ms"] = _since(_t)

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
    _t = time.perf_counter()
    try:
        result = query.ask(account_id, INDEX, question,
                           top_k=TOP_K, only_context=True)
        timings["retrieval_ms"] = _since(_t)
    except query.IndexNotReady as exc:
        raise ChatUnavailable(str(exc)) from exc
    except Exception as exc:
        # A retrieval that fails slowly is worth seeing, so the duration is
        # recorded before the early return rather than lost with the exception.
        timings["retrieval_ms"] = _since(_t)
        # Retrieval can refuse a question for its own reasons - a query it
        # considers too short, a transient backend error. None of those is a
        # server fault, and a 500 tells a seller nothing. Answer that we could
        # not look it up.
        logger.exception("strategy chat: retrieval failed for %r", question[:80])
        timings["total_ms"] = _since(t_start)
        return _unavailable(company, question, topic,
                            "retrieval failed: %s" % exc, timings=timings)

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
        timings["total_ms"] = _since(t_start)
        return _unavailable(company, question, topic, "no evidence was retrieved",
                            timings=timings)

    attempts, correction, last_reason = [], "", "no attempt was made"
    for attempt in range(MAX_VALIDATION_ATTEMPTS):
        # Generation and validation are timed apart because only one of them is
        # an LLM call. A rejected attempt is a whole generation paid for and
        # discarded, so the per-attempt figures are what show whether latency
        # is the model being slow or the loop running more than once.
        _t = time.perf_counter()
        raw = _answer_once(company, question, reasoning_context, messages, correction)
        generate_ms = _since(_t)

        _t = time.perf_counter()
        ok, reason, cited, cleaned = _validate(account_id, raw, passages)
        validate_ms = _since(_t)

        attempts.append({"attempt": attempt + 1, "accepted": ok, "reason": reason,
                         "generate_ms": generate_ms, "validate_ms": validate_ms})
        if ok:
            timings["total_ms"] = _since(t_start)
            logger.info(
                "strategy chat timing: total=%dms resolve=%dms retrieval=%dms "
                "attempts=%d generate=%dms validate=%dms",
                timings["total_ms"], timings.get("resolve_question_ms", 0),
                timings.get("retrieval_ms", 0), len(attempts),
                sum(a.get("generate_ms", 0) for a in attempts),
                sum(a.get("validate_ms", 0) for a in attempts))
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
                    "timings": timings,
                },
            }
        last_reason = reason
        correction = reason
        logger.info("strategy chat: attempt %d rejected - %s", attempt + 1, reason)

    # Bounded retries, then stop. A third failure means the evidence does not
    # support the answer the model keeps wanting to give.
    timings["total_ms"] = _since(t_start)
    logger.info(
        "strategy chat timing (refused): total=%dms resolve=%dms retrieval=%dms "
        "attempts=%d generate=%dms validate=%dms",
        timings["total_ms"], timings.get("resolve_question_ms", 0),
        timings.get("retrieval_ms", 0), len(attempts),
        sum(a.get("generate_ms", 0) for a in attempts),
        sum(a.get("validate_ms", 0) for a in attempts))
    return _unavailable(company, question, topic, last_reason, attempts, timings)


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


def _unavailable(company, question, topic, reason, attempts=None,
                 timings=None) -> dict:
    closest = ("You could look at the Stakeholder Map, Tech Landscape or Recent "
               "Signals for the nearest related evidence.")
    generation = {"prompt_version": PROMPT_VERSION, "reason": reason,
                  "attempts": attempts or []}
    # A refusal after three rejected attempts is the slowest path there is -
    # the one worth measuring most, and the one that would otherwise report
    # nothing.
    if timings:
        generation["timings"] = timings
    return {
        "answer": UNAVAILABLE.format(company=company, closest=closest),
        "question": question,
        "topic": topic,
        "mode": "advisor",
        "citations": [],
        "available": False,
        "generation": generation,
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
