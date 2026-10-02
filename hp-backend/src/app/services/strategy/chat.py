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

from app.config.settings import settings
from app.core import gemini
from app.core.llm import generate_gpt4o_json_completion
from app.database.mongodb import get_db
from app.observability import steps
from app.services.extractors import grounding
from app.services.regen import store as widget_store
from app.services.strategy import (
    claims as claim_model,
    context as account_context,
    personas as strategy_personas,
)

logger = logging.getLogger(__name__)

# 2: answer first, then the facts behind it, then next steps (Sahaj, 27 Sep:
#    "we need to structure the answers here, currently the system is throwing a
#    lot of gibberish and then the real answer comes out").
# 3: the whole account in one call instead of retrieved fragments; citations
#    name the payload section they came from.
# 4: the ANSWER is as long as the question needs - a block per part when the
#    question asks for several things - instead of two or three sentences
#    whatever was asked (30 Sep: "the answer part is very short").
# 5: v4 still prescribed a length per question type ("three or four sentences"
#    for a single-thing question), which is how "who is the strongest entry
#    point" came back at three sentences and 2% of the output budget. The
#    length is now the model's judgement, with the three shapes offered rather
#    than assigned, and FACTS / RECOMMENDED NEXT STEPS are dropped entirely
#    when the question does not call for them - "who is the CEO" is answered by
#    a name, not by a five-point evidence list and three things to do about it.
#    Also: read the whole account, not the one obvious section. The answer that
#    prompted this cited 2 sections out of ~23.
# 7: RECOMMENDATION is its own segment type. Advice used to be SYNTHESIS, which
#    may introduce nothing its dependencies do not carry - so every "week 1"
#    and "three touches" was read as an unsupported account figure and deleted.
#    Asked for a 90-day plan, the platform published the residue: a RECOMMENDED
#    NEXT STEPS heading over fourteen facts and no steps. Also: the platform's
#    own scores are no longer quoted as though they were facts about the
#    customer, and a pile of one-line facts no longer counts as an answer.
# 8: a conclusion's specifics are checked against the WHOLE payload, not
#    against the two or three facts it listed as dependencies. The rule was
#    right and the lookup was wrong: a sentence naming a vendor that is in the
#    account's data was rejected as an invention because the sentence had not
#    cited that section. Writing a fact was safe and writing a sentence that
#    meant something was a coin toss, so the model stopped answering and
#    recited the dashboard instead - six "facts", three of them advice quoted
#    out of the Objection Playbook, and an empty ANSWER block.
PROMPT_VERSION = 8

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

You answer ONLY from the ACCOUNT DATA given below these instructions. That is the finished output of
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

Keep them apart in the answer: statements about the account go under ANSWER: and FACTS:, and advice
goes under RECOMMENDED NEXT STEPS:. This is not decoration - a seller repeats facts to a customer and
weighs recommendations themselves, and an answer that blurs the two gets the platform's inferences
quoted as the customer's own filings.

HOW YOU ANSWER: not as prose, but as a list of SEGMENTS. Each segment is one sentence or one
short line of the answer, and each one says what it is. Read in order they are the answer; the
seller never sees the structure. Do NOT write citation tags into the text - say which section a
segment came from in its own field and the platform adds the citation itself.

The account data is divided into sections, each introduced by a line reading
===== <section_name> (feature: ...) =====
Copy section names character for character from those header lines. Never invent one, never adapt
one, and never use a name that does not appear as a header above.

EVERY SEGMENT HAS A TYPE, and the type decides what it must carry:

FACT - states something about the account: a name, title, vendor, number, date, event.
  Needs "sections": the section or sections it came from.
  Needs "quote": a short run of words copied EXACTLY from one of those sections that shows the
  fact is there. Copy it character for character from the data - it is checked against the
  section, and a quote that is not in it is rejected.

DERIVED - an account statement you worked out from the data rather than read off it: a count, a
  comparison between two things in the evidence, a restatement. Same requirements as FACT.

SYNTHESIS - your conclusion or judgement ABOUT THE ACCOUNT, drawn from segments already in the
  list. Needs "depends_on": the ids of the segments it rests on. Needs NO sections and NO quote.
  Write it as prose. You may reason, weigh, compare and conclude in your own words, and you may
  name any person, vendor, product, figure or event THAT APPEARS ANYWHERE IN THE ACCOUNT DATA -
  not only the ones the segments you depend on happened to mention. You do not need a separate
  FACT for every specific you refer to while reasoning.
  What is rejected is a specific the ACCOUNT DATA does not contain at all: a vendor it never
  names, a number it never states, a person it never lists. If you want to say it and it is not
  in the data, you cannot - say what the data does hold instead.

RECOMMENDATION - what the SELLER should do: who to approach, what to open with, what to send and
  when. Needs "depends_on", exactly like SYNTHESIS. Needs NO sections and NO quote.
  This is where a plan goes, and it is allowed the language a plan is made of - a cadence, a
  count of touches, a sequence, a channel. "Open with a short note in week 1", "three touches
  over 30 days", "follow up on LinkedIn" are all fine: they propose something you are advising,
  and they assert nothing about the customer that could be true or false of them.
  Like SYNTHESIS, it may name anything that appears anywhere in the ACCOUNT DATA, and it is
  rejected only for a specific the data does not contain at all - a person it never lists, a
  vendor it never names, a figure it never states. An HP product it does not recommend is still
  out of bounds wherever it appears.
  Use RECOMMENDATION for every line under RECOMMENDED NEXT STEPS:, and for any sentence that
  tells the seller what to do. Use SYNTHESIS for a conclusion about the account itself.

GENERAL - how this kind of situation usually works, said about the world and not about this
  account. No sections, no quote. It may not name {company} and may not carry a figure - if you
  find yourself doing either, it is a FACT and needs evidence.

Keep facts and conclusions in separate segments. One sentence that half-states a fact and
half-draws a conclusion cannot be checked, and will be rejected.

HP RULES:
- You represent HP Inc. Never describe a competitor's product as ours.
- Name an HP product only if it appears in the evidence.
- Never claim {company} already uses HP unless the evidence says so.

NEVER REPEAT THE PLATFORM'S OWN SCORING. The account data carries numbers this platform computed
about its own output - relevance scores, priority and tier labels, urgency and confidence scores,
rankings, match percentages. They are there to help YOU decide what matters. They are not facts
about the customer and no seller can use one in front of one.
"Mike Higgins has an HP relevance score of 100 and a high priority" is a sentence about our
dashboard. Say what it means instead: that he is the person to start with, and why - his role,
what his organisation is doing, what the account has said it is prioritising. Use the scores to
choose who and what to talk about; never quote them.

IF THE EVIDENCE DOES NOT ANSWER THE QUESTION: say plainly that the platform does not hold it, and
name the closest thing it does hold. That is a correct answer, not a failure.

OUTPUT - return ONE JSON object and nothing else. No prose around it, no markdown fence.

{{"segments": [
  {{"id": "c1", "type": "FACT", "block": "paragraph",
   "text": "...", "sections": ["a_section"], "quote": "exact words from that section"}},
  {{"id": "c2", "type": "SYNTHESIS", "block": "paragraph",
   "text": "...", "depends_on": ["c1"]}},
  {{"id": "c3", "type": "GENERAL", "block": "paragraph", "text": "..."}}
]}}

WORKED EXAMPLE. Three facts and the conclusion they earn:

{{"segments": [
  {{"id": "c1", "type": "GENERAL", "block": "heading", "text": "ANSWER:"}},
  {{"id": "c2", "type": "FACT", "block": "paragraph",
    "text": "Their estate runs AutoCAD and CATIA.",
    "sections": ["tech_stack_matrix"], "quote": "AutoCAD"}},
  {{"id": "c3", "type": "FACT", "block": "paragraph",
    "text": "The Opportunity Map rates workstations a Critical play.",
    "sections": ["opportunity_narrative_plays"], "quote": "Critical"}},
  {{"id": "c4", "type": "SYNTHESIS", "block": "paragraph",
    "text": "So the workstation line has the strongest case of the three.",
    "depends_on": ["c2", "c3"]}},
  {{"id": "c5", "type": "RECOMMENDATION", "block": "bullet",
    "text": "Open on the CAD estate in week 1, then send the workstation one-pager three days later.",
    "depends_on": ["c2", "c3"]}}
]}}

Read the "quote" rule off that example: "AutoCAD" and "Critical" are words
lifted out of the data, not sentences about it. A quote is a SHORT run of
characters you can find by searching the section - a vendor name, a title, a
status, a figure. Do not write a sentence of your own there; it is compared
against the section and a sentence you composed is not in it.

Read the SYNTHESIS rule off c4: it is ordinary prose, it carries no section
and no quote, and everything it refers to is in the account data. It would be
just as valid naming something from a section c2 and c3 never cited - the test
is whether the ACCOUNT DATA holds it, not whether a neighbouring segment
mentioned it. Invent nothing; refer to anything that is there.

Read the RECOMMENDATION rule off c5: "week 1" and "three days" are the plan's
own schedule and need no evidence, while "CAD estate" and "workstation" are
there only because c2 and c3 put them there. That is the whole difference -
a recommendation may invent the PLAN freely and may invent nothing about the
CUSTOMER.

Inside "text", never use a double quote - the answer is one JSON object and a
stray quote breaks it. Write a quoted phrase with single quotes, or none.

"block" is how the line sits on the page: "paragraph" for ordinary prose, "bullet" for an item in
a list, "heading" for a section heading such as ANSWER: or FACTS:, "label" for a SHORT ALL-CAPS
LABEL opening a block. Headings and labels are usually GENERAL - they name nothing about the
account - but a label that names a vendor is a FACT and needs its evidence.

The answer still has the shape it always had, written as segments:
A "heading" segment reading ANSWER: , then the answer. Then a "heading" segment reading FACTS:
and the facts, when the question calls for them. Then a "heading" segment reading
RECOMMENDED NEXT STEPS: and the steps, when the question asks what to do. ANSWER: is always there;
the other two are left out entirely when the question does not call for them.
ANSWER:
  Answer the question that was actually asked, at whatever length it deserves. There is no target
  length, no minimum and no house style. Judge it from the question:
  - A question with one answer - "who is the CEO", "what was revenue last year", "do they run
    Windows" - gets the answer and nothing else. One sentence, maybe two. Do not stretch it.
  - A question asking why, how, which, or what to do gets as much as it takes to be genuinely
    useful, and no more. Usually a paragraph.
  - A question asking about several things - a risk and a counter for each incumbent, a comparison,
    one recommendation per business unit - gets a short block for each, opened by a SHORT ALL-CAPS
    LABEL on its own line. Cover every part that was asked about.
  Pick the shape that fits. A page in answer to "who is the CEO" is as wrong as two sentences in
  answer to "how should I approach this account".

  KEEP A PLAN THE SIZE OF A PLAN. A campaign plan is phases, not a diary: three or four phases
  with a handful of lines each, not twelve separately numbered weeks each with its own activities,
  personas, content and metrics. Say a thing once - if a persona or a play belongs to three
  phases, name it in the phase where it matters and refer back. An answer that runs past about
  thirty segments is being padded, and a long answer that gets cut off is worth nothing to the
  seller, so length is not free.

  A LIST OF FACTS IS NOT AN ANSWER. If the question asks who to approach, what to say, how to
  go in, or what to do, the ANSWER block must contain at least one SYNTHESIS or RECOMMENDATION
  that actually answers it - in the seller's own words, naming the person or the play and saying
  why. Facts belong underneath, under FACTS:, as the support for that answer.
  Do not write one line per field of the data. Nine stakeholders each getting their own sentence
  is a directory, not an answer: name the one or two who matter for THIS question and say what
  to do about them. The seller can open the dashboard for the rest.
  DRAW ON THE WHOLE ACCOUNT, not just the obvious section. Who to approach is also about what they
  care about, what they already run and what they will push back on; the evidence for that is
  spread across the sections below, and an answer that reads one of them is a thinner answer than
  the data supports.
  Every segment here that says anything about the account is a FACT or a DERIVED with its own
  evidence - the first line, the sentences, and a label that names vendors. A bare label like
  COMPETITIVE RISKS names nothing and is GENERAL. A line that draws the answer together is a
  SYNTHESIS resting on the segments above it.
FACTS:
  A numbered list of the evidence behind the answer, one fact each, each a FACT segment with its
  section and quote, "block": "bullet". At most five for a single-topic answer; up to eight when
  the answer covers several things, so each part shows the evidence it rests on. Only the facts
  the answer rests on; not an inventory of everything known.
  LEAVE THIS SECTION OUT when the answer already said its facts and a list would only repeat them.
  A one-line answer does not need a FACTS block under it.
RECOMMENDED NEXT STEPS:
  A numbered list of two or three concrete actions for the seller, each a SYNTHESIS segment
  resting on the facts that justify it, "block": "bullet".
  LEAVE THIS SECTION OUT when the question did not ask what to do. "What was revenue last year" is
  answered by the figure, not by three things to do about it.
If the evidence does not answer the question, write ANSWER: saying so and naming the closest thing
the platform holds, and leave out the other two sections.
Each segment's "text" is plain: no markdown, no asterisks, no hashes, and no square-bracket
citation tags - the platform adds those. Do not pad: no background the question did not ask for,
no restating the question, no summary of what you are about to say. Length comes from covering
what was asked, never from saying it at greater length."""


# A separate constant rather than a branch inside ANSWER_SYSTEM, for three
# reasons. The advisor's ANSWER:/FACTS:/NEXT STEPS structure is the opposite of
# what dialogue needs. A persona block appended after that prompt's FORMAT
# section would be the last and most salient instruction the model reads,
# sitting downstream of the citation law - which is precisely how a model gets
# talked out of citing. And ANSWER_SYSTEM goes through str.format, so every
# brace added to it is a hazard.
#
# What carries over deliberately and word-for-word: the ACCOUNT DATA grounding
# paragraph, the rule that section names are copied character for character,
# and the HP rules. Only the identity and the output shape differ.
ROLEPLAY_SYSTEM = """You are playing a role so that an HP seller can rehearse a real conversation.

{persona}

You are a SIMULATION OF THIS ROLE at {company}. You are not a named person, you are not speaking for
anyone, and you never claim to be a specific individual. If the seller asks who you are, answer with
the role.

You answer ONLY from the ACCOUNT DATA given below these instructions. That is the finished output of
every intelligence feature this platform runs on {company} - its filings and priorities, its people,
its technology, its intent signals, recent events, opportunity plays, objections and messaging - and
it is everything the platform knows about them. If something is not in there, the platform does not
hold it.

HOW YOU SPEAK IS YOURS. Tone, register, how blunt or patient or sceptical this role would be, the
questions you ask back, how you open and close - all of that is yours to write, and it should sound
like the role rather than like a report.

WHAT YOU SAY IS NOT YOURS. Every concern, objection, priority, constraint, vendor, product, number
or piece of context you mention must come from the ACCOUNT DATA. You do not know anything else. You
do not have a budget, a timeline, a contract term, a renewal date, a team size, a colleague, a
previous conversation with HP or a personal opinion unless the account data gives you one. Inventing
one to make the conversation feel real is the single worst thing you can do here - the seller will
take it into a real meeting.

CITATIONS: the account data is divided into sections, each introduced by a line reading
===== <section_name> (feature: ...) =====
EVERY sentence in which you say something substantive must end with the section it came from, in
square brackets - for example [objection_reframe_cards]. Cite several when a sentence rests on
several: [a_section, b_section].

Copy section names character for character from those header lines. Never invent one, never adapt
one, and never use a name that does not appear as a header above - a name that does not match a
section is rejected and the whole answer is discarded.

Questions you ask the seller need no citation. Short conversational replies need no citation. Every
other sentence needs one.

IF THE SELLER ASKS SOMETHING THE ACCOUNT DATA DOES NOT COVER: say so in character - that it is not
something this role can speak to, or not something you have in front of you. Do not guess and do not
fill the gap. That is a correct answer, not a failure.

HP RULES:
- The seller represents HP Inc. You do not. Never argue HP's case for them.
- Name a product only if it appears in the evidence.
- Never concede that {company} already uses HP unless the evidence says so.

FORMAT: plain text, first person, as spoken. No stage directions, no narration, no markdown, no
asterisks, no hashes. Do not prefix your lines with a name or a role label."""


def _system_prompt(company: str, persona: dict | None, context: str = "") -> str:
    """The instructions AND the account, as one stable block.

    The single render point for both prompts. Both go through `str.format`, so
    a persona block containing a literal brace would raise here rather than
    quietly producing a broken prompt - `personas.prompt_block` builds from
    account text, which is why it is worth knowing that is the failure mode.

    **The payload is concatenated, never formatted.** It is compact JSON and
    therefore full of braces; passing it through `str.format` would raise
    KeyError on the first object key. Template first, account second.

    **Why the account lives here rather than in the question turn.** Gemini is
    stateless - `system_instruction` travels on every request exactly as
    `contents` does, so this saves nothing in transmission and is not meant to.
    What it buys is a STABLE PREFIX, which is the precondition for caching.

    The previous shape appended the account to the last user turn, so the wire
    looked like:

        system: 2.7 KB
        contents: [ history, history, ..., LAST TURN(453 KB + question) ]

    with growing history in front of the payload and the question glued to its
    back. The one large, unchanging block sat in the middle and moved every
    turn, so there was no reusable prefix and `cached_content_token_count` came
    back 0 on every call - measured across three consecutive turns. Here the
    instructions and the account are both fixed for the life of a conversation,
    and only the question varies.
    """
    rendered = (ANSWER_SYSTEM.format(company=company) if not persona
                else ROLEPLAY_SYSTEM.format(
                    company=company,
                    persona=strategy_personas.prompt_block(persona)))
    if not context:
        return rendered
    return "\n\n".join([rendered, "ACCOUNT DATA:", context])


def _answer_turns(question: str, messages: list, correction: str = "") -> list:
    """The conversation as sent: earlier turns, then this question.

    The account is NOT in these turns. It lives in the system prompt, which is
    fixed for the life of a conversation, so the only thing varying between
    turns is the question - see `_system_prompt` for why that matters to
    caching. The payload is still sent whole and still never truncated; it has
    simply moved to the one position where a cache can find it twice.
    """
    user = "\n".join([
        ("CORRECTION - your previous answer was rejected: %s Write it again "
         "using only the account data above." % correction) if correction else "",
        "QUESTION: %s" % question,
    ]).strip()

    turns = [m for m in (messages or [])[:-1]
             if isinstance(m, dict) and _text(m.get("role")) in ("user", "assistant")
             and _text(m.get("content"))][-MAX_HISTORY_TURNS:]
    turns.append({"role": "user", "content": user})
    return turns


def _answer_once(company: str, question: str, context: str, messages: list,
                 correction: str = "", persona: dict | None = None) -> str:
    """One generation attempt."""
    return gemini.generate(_system_prompt(company, persona, context),
                           _answer_turns(question, messages, correction))


# ---------------------------------------------------------------------------
# Step 5 - validation, which the model cannot talk past
# ---------------------------------------------------------------------------

import collections
import hashlib
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


# A refusal is the one thing a sentence can say that legitimately cites
# nothing: it asserts nothing about the account, so there is nothing to ground.
_REFUSAL_PHRASES = ("does not hold", "not hold", "no information",
                    "not available", "does not have", "does not include",
                    "is not in the account data", "no data")


def _asserts_facts(sentence: str) -> bool:
    """Whether this SENTENCE claims something about the account.

    Everything except a refusal and a piece of filler does. That is deliberately
    the wide reading.

    Two earlier versions of this were both too narrow, in different ways.

    It first returned True only when the literal word "fact" appeared in the
    first 400 characters - trusting the model to have written a "FACTS:" header
    before the citation requirement applied to it. An answer that opened
    straight into prose ("PT Astra International Tbk's revenue is in the
    range...") asserted the account's figures while this returned False. A gate
    a model can disable by omitting a header is not a gate, so the label stopped
    deciding it.

    It then read the WHOLE answer: one refusal phrase anywhere - "the platform
    does not hold a mobile number" as an aside - switched the citation
    requirement off for every other sentence in the reply, including a FACTS
    list of invented names below it. The unit is now the sentence, which is also
    the unit the prompt states the rule in and the unit `_validate_roleplay`
    has always used.

    (`_GLUE_RE` and `_content_tokens` live with the dialogue validator below.
    Both units of validation share them; they are defined once, there.)
    """
    text = _text(sentence)
    if not text or _GLUE_RE.match(text):
        return False
    if not _content_tokens(_CITATION_RE.sub("", text)):
        # Punctuation, a list marker, a bare label. Says nothing to source.
        return False
    lowered = text.lower()
    return not any(phrase in lowered for phrase in _REFUSAL_PHRASES)


# Where an advisor answer stops asserting and starts advising. A next step is
# the seller's action, not a claim about the account - "Open with the refresh
# cycle" cites nothing because it asserts nothing - and the prompt asks for a
# tag only under ANSWER: and FACTS:. Figures are still checked over the whole
# answer, so an invented number in a next step is still caught.
_ADVICE_HEADER_RE = re.compile(
    r"(?:recommended|suggested)?\s*next\s+steps\s*:|recommendations?\s*:", re.I)

# A header line: one the format asks for ("FACTS:") or a block label the
# answer uses to separate the parts of a multi-part question ("ENDPOINT
# SECURITY").
#
# The bare-label half is deliberately narrow - all caps, no digits, at most
# five words, colon optional. A blanket "an all-caps line asserts nothing"
# would be a way to state an uncited fact in capitals, and this gate exists
# because a gate a model can talk past is not a gate. A label that names
# vendors ("WORKSTATIONS - NVIDIA CUDA, AutoCAD") is longer than five words or
# carries lowercase, so it stays a claim and the prompt tells the model to tag
# it, which is right: naming a vendor is a claim about the account.
_HEADER_LINE_RE = re.compile(
    r"^[A-Z][A-Z \t/&-]{1,40}:\s*$"
    r"|^[A-Z][A-Z&/-]*(?:[ \t]+[A-Z&/-]+){0,4}:?\s*$")
_LABEL_PREFIX_RE = re.compile(
    r"^\s*(?:answer|facts?|context|evidence|so what(?:\s+for\s+hp)?)\s*:\s*",
    re.I)
_LIST_MARKER_RE = re.compile(r"^\s*(?:[-*•]|\(?\d{1,2}[.)])\s*")
_SENTENCE_END_RE = re.compile(r"[.!?][\"')\]]*$")
# A block label that is NOT bare: an all-caps run introducing something, as in
# "WORKSTATIONS - NVIDIA CUDA / GPUs, AutoCAD". It names vendors, so it is a
# claim and needs its own tag - which means it must not be glued to the
# sentence beneath it, or that sentence's tag would cover both.
_BLOCK_LABEL_RE = re.compile(r"^[A-Z][A-Z&/-]*(?:[ \t]+[A-Z&/-]+)*[ \t]*[-–—:]")

# The grounding corpus for one payload, built once.
#
# `Corpus.__init__` is eager: it normalises the whole payload - about 450 KB -
# and runs the number, percentage and URL scanners over it. That was affordable
# when it happened once per answer. It no longer is: streaming validates the
# prefix every time a citation bracket closes, and the point of a longer answer
# is more citations, so a fifteen-citation answer would scan the payload
# fifteen times while the seller waits.
#
# The corpus depends on the payload alone, and the payload is fixed for the
# life of a turn, so it is remembered. Two entries, not one: a retry validates
# the same payload as the attempt before it, and nothing here should be
# sensitive to a second conversation interleaving. Keyed on the text itself -
# not on `id()`, which a garbage-collected string can hand to a different
# payload.
_CORPUS_CACHE: "collections.OrderedDict" = collections.OrderedDict()
_CORPUS_CACHE_MAX = 2


def _corpus_for(payload: str):
    """`grounding.corpus_from_texts([payload])`, memoised on the payload."""
    key = hashlib.sha256(str(payload or "").encode("utf-8")).hexdigest()
    found = _CORPUS_CACHE.get(key)
    if found is None:
        found = grounding.corpus_from_texts([payload])
        _CORPUS_CACHE[key] = found
        while len(_CORPUS_CACHE) > _CORPUS_CACHE_MAX:
            _CORPUS_CACHE.popitem(last=False)
    else:
        _CORPUS_CACHE.move_to_end(key)
    return found


def _unwrap(lines: list) -> list:
    """Rejoin a sentence the model wrapped across two lines.

    `_claim_sentences` splits on newlines before it splits on sentences, so a
    sentence broken over two lines used to arrive as two claims - and the first
    half, the half without the trailing tag, was rejected as uncited. At two or
    three sentences that almost never happened. At paragraph length it is the
    likeliest false rejection there is.

    A line is joined to the one before it when that line did not finish a
    sentence. It is NOT joined when either side is a list item or a block
    label: two numbered facts on two lines are two claims and each carries its
    own tag, and merging them would let one tag cover both.

    The label case is the one that bites. "WORKSTATIONS - NVIDIA CUDA, AutoCAD"
    ends without a full stop, so a naive join glues it to the sentence beneath
    it and that sentence's tag silently covers the vendors named in the label.
    Verified: before this guard, a heading naming three vendors with no tag of
    its own published.
    """
    out = []
    for line in lines:
        joinable = (out
                    and not _SENTENCE_END_RE.search(out[-1])
                    and not _BLOCK_LABEL_RE.match(out[-1])
                    and not _LIST_MARKER_RE.match(line)
                    and not _BLOCK_LABEL_RE.match(line)
                    and not _HEADER_LINE_RE.match(line))
        if joinable:
            out[-1] = "%s %s" % (out[-1], line)
        else:
            out.append(line)
    return out


def _claim_sentences(body: str) -> list:
    """Every sentence of an advisor answer that could be asserting something.

    Headers, list markers and the RECOMMENDED NEXT STEPS block are dropped here
    rather than argued about in the validator: none of them is a claim about the
    account, and leaving them in would reject a correctly written answer for
    failing to cite the word "FACTS".
    """
    text = _text_block(body)
    advice = _ADVICE_HEADER_RE.search(text)
    region = text[:advice.start()] if advice else text

    kept = []
    for raw_line in region.split("\n"):
        line = raw_line.strip()
        if not line or _HEADER_LINE_RE.match(line):
            continue
        kept.append(_LABEL_PREFIX_RE.sub("", line))

    out = []
    for line in _unwrap(kept):
        for chunk in _DIALOGUE_SENTENCE_RE.split(line):
            sentence = _LIST_MARKER_RE.sub("", chunk).strip()
            if sentence:
                out.append(sentence)
    return out


# --- validating dialogue ----------------------------------------------------
#
# Roleplay gets its own validator rather than an extra check bolted onto
# `_validate`, because `_validate` is wrong for dialogue in both directions.
#
# It is too strict: `_asserts_facts` treats anything that is not a refusal as
# asserting facts, so "Hmm. Go on." - two words that claim nothing - is
# rejected for citing nothing, retried three times, and surfaces as a failure.
# A persona that cannot say "go on" cannot hold a conversation.
#
# And it is too loose: it needs ONE resolvable citation for a whole answer. A
# persona could tag one sentence and invent three around it - "we are locked
# into a three-year agreement", "my team does not own that", "we looked at this
# last year". None carries a digit, so the figure check never sees them, and a
# seller repeats them in a real meeting.
#
# The rule the user set is that the language may be the role's but the substance
# must come from a source. That is enforced here, per sentence, in Python.

_DIALOGUE_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+")

# Lines that say nothing about the account and need no source. Closed list, not
# a length heuristic: "Our refresh cycle is four years" is short too.
_GLUE_RE = re.compile(
    r"^(ok|okay|right|sure|fine|hmm+|look|well|go on|i see|i am listening|"
    r"understood|noted|fair enough|fair|alright|thanks|thank you|carry on|"
    r"go ahead|maybe|perhaps|possibly|of course|indeed|true|agreed|"
    r"that is fair|that's fair|say more|and\?|so\?)[\s.,!?-]*$",
    re.I)

# A word long enough to carry meaning. Used to decide whether a sentence said
# anything at all, and to compare what it said against the section it cited.
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

# Whether a cited sentence must share vocabulary with the section it cited.
#
# A tag proves the model ASSERTED an attribution; it does not prove the sentence
# is in that section. Nothing in this codebase checked that before - not even in
# advisor mode - and without it a fabricated claim survives simply by carrying a
# plausible tag.
#
# It is a flag because it has a real false-positive cost: "That is not my call
# [stakeholder_influence_map]" shares no content word with that section and is
# rejected, so the persona is pushed toward the evidence's own vocabulary and
# some turns read stiffer. Every rejection is logged with the sentence so the
# rate can be measured against real conversations rather than guessed at.
ROLEPLAY_REQUIRE_SECTION_OVERLAP = True


def _content_tokens(text: str) -> set:
    return {t.lower() for t in _CONTENT_TOKEN_RE.findall(text or "")
            if t.lower() not in _STOPWORDS}


def _section_texts(payload: str) -> dict:
    """{widget_key: that section's text}, by re-splitting the payload.

    Done here rather than by changing what `context.build` returns, so the
    payload stays one string and this stays a detail of validation.
    """
    found, key, buffer = {}, None, []
    for line in (payload or "").split("\n"):
        if line.startswith("=====") and "(feature:" in line:
            if key:
                found[key] = "\n".join(buffer)
            key = line.split("=====")[1].split("(feature:")[0].strip()
            buffer = []
        elif key:
            buffer.append(line)
    if key:
        found[key] = "\n".join(buffer)
    return found


def _validate_roleplay(answer: str, payload: str, widget_keys: list,
                       banned_names: list) -> tuple:
    """(ok, reason, cited_keys, cleaned). The gate for in-character dialogue.

    Same spirit as `_validate`, different unit: a sentence rather than an
    answer. Figures are checked by exactly the same helper on exactly the same
    payload - roleplay does not get a weaker numeric rule, and a future refactor
    that drops it should fail a test rather than pass review.
    """
    body = _text_block(answer)
    if not body.strip():
        return False, "the model returned nothing", [], ""

    valid = set(widget_keys or [])
    cited = list(dict.fromkeys(_SECTION_REF_RE.findall(body)))
    invalid = [c for c in cited if c not in valid]
    if invalid:
        return (False,
                "it cited %d section(s) that are not in this account's data: %s"
                % (len(invalid), ", ".join(invalid[:3])), [], "")
    resolved = [c for c in cited if c in valid]

    # No real person is quoted, named or spoken for - not the role being played
    # and not a colleague. This is Message Evaluator's rule
    # (`evaluator/sources.py`: never what that person "thinks, wants or has
    # said") applied to the whole roster, because "talk to Budi about it" puts
    # words about a named employee into a simulated conversation just as surely
    # as signing the reply with their name would.
    for name in (banned_names or []):
        if re.search(r"\b%s\b" % re.escape(name), body, re.I):
            return (False,
                    "it named a real person (%s) - the role speaks, never the "
                    "individual" % name, [], "")

    sections = _section_texts(payload) if ROLEPLAY_REQUIRE_SECTION_OVERLAP else {}
    unsourced, unsupported = [], []
    for raw in _DIALOGUE_SENTENCE_RE.split(body):
        sentence = raw.strip()
        if not sentence or _GLUE_RE.match(sentence):
            continue
        bare = _CITATION_RE.sub("", sentence).strip()
        tokens = _content_tokens(bare)
        if not tokens:
            # Punctuation, an interjection, a bare name of nothing. Says nothing
            # about the account, so there is nothing to source.
            continue

        tags = [key for key in _section_refs(sentence) if key in valid]
        if not tags:
            # A question asserts nothing, and asking is how this role finds out
            # what the seller is proposing. Requiring a source for "what would
            # switching actually gain us" leaves the persona unable to ask
            # anything the account data does not already contain, which is the
            # end of the rehearsal.
            #
            # The residue, stated plainly: a question CAN smuggle a claim -
            # "are you asking me to break a three-year agreement?". The figure
            # check and the name ban below run over the whole reply and catch
            # the numeric and the named versions of that. A non-numeric claim
            # phrased as a question is what gets through, and closing it would
            # mean deciding in Python which questions are rhetorical.
            if bare.endswith("?"):
                continue
            unsourced.append(bare)
            continue

        if ROLEPLAY_REQUIRE_SECTION_OVERLAP and not any(
                tokens & _content_tokens(sections.get(tag, "")) for tag in tags):
            unsupported.append((bare, tags[0]))

    if unsourced:
        return (False,
                "it said %d thing(s) in character with no source: %s"
                % (len(unsourced), " / ".join(s[:70] for s in unsourced[:2])),
                [], "")
    # Figures before the overlap check, so an invented number is reported as an
    # invented number. Both would reject it; only one says why usefully, and the
    # reason is fed straight back to the model as the correction for its next
    # attempt.
    corpus = _corpus_for(payload)
    countable = _CITATION_RE.sub("", body)
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
                "it cited a section that does not support what it said: %s"
                % unsupported[0][0][:90], [], "")

    cleaned = re.sub(r"\*\*(.+?)\*\*", r"\1", body)
    cleaned = re.sub(r"(?<!\*)\*(?!\*)", "", cleaned)
    # A speaker label the model prefixed its own line with - "COO:", "Irvan:".
    # The UI already says who is speaking, and a label is the one place a name
    # would reappear after being kept out of the prompt.
    cleaned = re.sub(r"^\s*[A-Z][A-Za-z ./&-]{2,40}:\s*", "", cleaned)
    return True, "ok", resolved, cleaned.strip()

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
    #
    # Checked per SENTENCE, which is the unit the rule is written in - "EVERY
    # sentence that states a fact about the account ... must end with the
    # section it came from". It used to be checked per answer: ONE resolvable
    # citation anywhere validated the whole reply, so a model could tag one
    # sentence and invent three around it. None of the three carries a digit, so
    # the figure check below never saw them, and a seller read them as evidence.
    # `_validate_roleplay` was written with this loop because dialogue made the
    # hole obvious; advisor answers had exactly the same hole.
    uncited = [s for s in _claim_sentences(answer)
               if _asserts_facts(s)
               and not any(key in valid for key in _section_refs(s))]
    if uncited:
        return (False,
                "it states %d thing(s) about the account without citing any "
                "evidence: %s"
                % (len(uncited), " / ".join(s[:70] for s in uncited[:2])),
                [], "")

    corpus = _corpus_for(payload)
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

# Why there is no answer. Three unrelated failures used to print one message -
# "nothing in it supports an answer here" - including the case where the model
# answered and the gate rejected it. A seller reading that concludes the
# platform holds nothing about the account, which on a 350,000-character
# payload is the most damaging thing it could tell them.
CAUSE_NO_DATA = "no_data"            # no feature has published anything
CAUSE_MODEL = "model"                # the model failed, or hit the token cap
CAUSE_UNEVIDENCED = "unevidenced"    # it answered; the answer could not be evidenced

CAUSE_OPENING = {
    CAUSE_NO_DATA:
        "I have nothing to answer from for {company} yet.\n\n"
        "No feature has published anything for this account, so there is no "
        "account intelligence to read.",
    CAUSE_MODEL:
        "I could not finish that answer for {company}.\n\n"
        "The model did not return a usable answer, so there is nothing I can "
        "stand behind. This is a fault on our side, not a gap in the data.",
    CAUSE_UNEVIDENCED:
        "I drafted an answer about {company} but could not evidence all of "
        "it.\n\nRather than show you claims I cannot trace to this account's "
        "data, I have held it back.",
}

UNAVAILABLE = (
    "I could not answer that from {company}'s account intelligence.\n\n"
    "Everything I say has to come from the data this platform holds for this "
    "account, and nothing in it supports an answer here.\n\n"
    "{closest}")


def answer(account_id: str, messages: list, mode: str | None = None,
           persona_id: str | None = None) -> dict:
    """Answer one question about one account. Returns the published payload.

    With a `persona_id` the chat stops advising and starts rehearsing: it plays
    that stakeholder's ROLE and pushes back, so a seller can find out where the
    pitch breaks before a customer does. The persona is resolved against this
    account only - one belonging to another account does not resolve, and the
    turn is answered as the advisor rather than silently as someone else.
    """
    db = get_db()
    timer = steps.StepTimer()
    with steps.use(timer):
        return _answer(db, timer, account_id, messages, mode, persona_id)


def _answer(db, timer, account_id, messages, mode, persona_id) -> dict:
    """The turn itself, with a timer in scope for everything it calls.

    Split out so `steps.use` wraps the whole turn including the Gemini calls -
    the client records its token usage against whatever timer is current, and
    that is how cache hits become visible at all.
    """
    turn = _prepare(db, timer, account_id, messages, mode, persona_id)
    if "done" in turn:
        return turn["done"]

    if turn["persona"]:
        return _answer_roleplay(timer, turn, messages, attempts=[])
    return _answer_advisor(timer, turn, messages)


def _stream_advisor(timer, turn, messages):
    """The advisor turn as SSE, validated before a word is shown.

    The same `_answer_advisor` decision, wrapped in the stage events the UI
    animates. Nothing unvalidated reaches the client: the answer arrives in one
    delta once the gate has passed it, which is the point of the change.
    """
    yield {"type": "stage", "stage": "writing"}
    result = _answer_advisor(timer, turn, messages)
    yield {"type": "stage", "stage": "checking"}
    if result.get("available") and result.get("answer"):
        yield {"type": "delta", "text": result["answer"]}
    yield {"type": "done", **result}


def _answer_advisor(timer, turn, messages) -> dict:
    """Generate the whole answer as segments, validate it whole, repair it.

    Nothing is published until the segment list holds. When the retry budget
    is spent the segments that DID hold are published and the rest dropped -
    an answer missing a line is worth more to a seller than being told the
    platform holds nothing about an account it holds 350,000 characters on.
    """
    attempts, correction = [], ""
    last_failures, last_segments = [], []

    for attempt in range(MAX_VALIDATION_ATTEMPTS):
        try:
            with timer.step("generation", attempt=attempt + 1):
                raw = _answer_once(turn["company"], turn["question"],
                                   turn["payload"], messages, correction)
        except gemini.GeminiTruncated as exc:
            # Cut off at the output limit. Worth one more go asking for less,
            # rather than ending the question with attempts still unspent -
            # the seller gets "I could not finish that answer" for something
            # the platform could answer in fewer words.
            logger.warning("strategy chat: %s", exc)
            attempts.append({"attempt": attempt + 1, "accepted": False,
                             "reason": str(exc)})
            correction = (
                "Your previous answer was cut off at the output limit. Answer "
                "the same question in materially fewer segments and shorter "
                "text: keep the structure and the specifics that matter, drop "
                "the repetition, and do not restate a fact you have already "
                "stated. Completing a shorter answer is worth more than "
                "starting a longer one.")
            continue
        except gemini.GeminiUnavailable as exc:
            # The model failed outright - a content filter, a 5xx, an empty
            # answer. Not retried: nothing about asking again would differ.
            logger.error("strategy chat: %s", exc)
            return _unavailable_for(turn, str(exc), attempts,
                                    cause=CAUSE_MODEL)
        try:
            with timer.step("validation"):
                ok, failures, cited, segments = _check_segments(turn, raw)
        except claim_model.ClaimError as exc:
            # A malformed list is the model's answer being unusable, not an
            # ungrounded claim. Named as such so the retry fixes the shape.
            reason = str(exc)
            attempts.append({"attempt": attempt + 1, "accepted": False,
                             "reason": reason})
            correction = ("Your previous answer was not a segment list: %s. "
                          "Return one JSON object with a \"segments\" array "
                          "and nothing else." % reason)
            logger.info("strategy chat: attempt %d unparsable - %s",
                        attempt + 1, reason)
            continue

        reason = _reason_for(failures)
        attempts.append({"attempt": attempt + 1, "accepted": ok, "reason": reason})
        if ok:
            _log_timings(timer, turn["question"], accepted=True)
            return _published(turn, claim_model.render(segments), cited,
                              attempts, timer, segments=segments)
        last_failures, last_segments = failures, segments
        correction = claim_model.repair_notes(failures)
        logger.info("strategy chat: attempt %d rejected - %s", attempt + 1, reason)

    # The retry budget is spent. Publish what held rather than nothing.
    kept = claim_model.surviving(last_segments, last_failures)
    if kept:
        ok, failures, cited, _ = _revalidate(turn, kept)
        if ok:
            dropped = len(last_segments) - len(kept)
            logger.info("strategy chat: published %d of %d segments, %d dropped",
                        len(kept), len(last_segments), dropped)
            _log_timings(timer, turn["question"], accepted=True)
            return _published(turn, claim_model.render(kept), cited, attempts,
                              timer, segments=kept, dropped=dropped)

    _log_timings(timer, turn["question"], accepted=False)
    return _unavailable_for(turn, _reason_for(last_failures), attempts, timer,
                            cause=CAUSE_UNEVIDENCED)


def _revalidate(turn: dict, segments: list) -> tuple:
    """The same gate, over a list we have already pruned."""
    ok, failures, cited = claim_model.validate(
        segments,
        widget_keys=turn["widget_keys"],
        section_texts=_section_texts(turn["payload"]),
        corpus=_corpus_for(turn["payload"]),
        company=turn["company"],
        payload=turn["payload"],
        question=turn["question"])
    return ok, failures, cited, segments


def _answer_roleplay(timer, turn, messages, attempts) -> dict:
    """In-character dialogue, unchanged.

    The persona path keeps prose with literal tags and the per-sentence gate.
    Its answer is spoken, not structured; segments would make a character read
    like a report, and `_validate_roleplay` carries rules - banned names,
    section overlap - that have nothing to do with the advisor.
    """
    correction, last_reason = "", "no attempt was made"
    for attempt in range(MAX_VALIDATION_ATTEMPTS):
        try:
            with timer.step("generation", attempt=attempt + 1):
                raw = _answer_once(turn["company"], turn["question"],
                                   turn["payload"], messages, correction,
                                   persona=turn["persona"])
        except gemini.GeminiUnavailable as exc:
            logger.error("strategy chat: %s", exc)
            return _unavailable_for(turn, str(exc), attempts, cause=CAUSE_MODEL)
        with timer.step("validation"):
            ok, reason, cited, cleaned = _check(turn, raw)
        attempts.append({"attempt": attempt + 1, "accepted": ok, "reason": reason})
        if ok:
            _log_timings(timer, turn["question"], accepted=True)
            return _published(turn, cleaned, cited, attempts, timer)
        last_reason = reason
        correction = reason
        logger.info("strategy chat: attempt %d rejected - %s", attempt + 1, reason)

    _log_timings(timer, turn["question"], accepted=False)
    return _unavailable_for(turn, last_reason, attempts, timer,
                            cause=CAUSE_UNEVIDENCED)


def _prepare(db, timer, account_id, messages, mode, persona_id) -> dict:
    """Everything a turn needs before the first generation.

    Returns {"done": payload} when the turn is already answered - small talk,
    or an account nothing has been published for - and otherwise the turn:
    who is speaking, the resolved question and the account payload.
    """
    with timer.step("persona"):
        persona = (strategy_personas.resolve(account_id, persona_id)
                   if persona_id else None)
    resolved_mode = "roleplay" if persona else (_text(mode) or "advisor")

    with timer.step("company_lookup"):
        company = _text((widget_store.get(account_id, "exec_summary_card", db=db)
                         or {}).get("data", {}).get("company_name")) or "this account"

    # A JSON call whenever there is history to resolve against, and free on the
    # first turn - which is why it is timed separately rather than folded into
    # generation.
    with timer.step("resolve_question", turns=len(messages or [])):
        question, topic = _resolve_question(messages)

    if _is_small_talk(question):
        return {"done": _greeting(company, question, resolved_mode, persona)}

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
    with timer.step("payload_build"):
        payload, sections = account_context.build(account_id)
    turn = {"company": company, "question": question, "topic": topic,
            "persona": persona, "mode": resolved_mode, "payload": payload,
            "sections": sections,
            "widget_keys": [row["widget_key"] for row in sections],
            # Read once, not once per attempt: the roster cannot change
            # between them.
            "banned": (strategy_personas.banned_names(account_id)
                       if persona else [])}
    if not payload:
        return {"done": _unavailable_for(
            turn, "no feature has published anything for this account yet",
            cause=CAUSE_NO_DATA)}
    return turn


def _check_segments(turn: dict, raw: str) -> tuple:
    """(ok, failures, cited, segments) for the advisor's segment list.

    Replaces reconstructing claims from prose. The model says what each piece
    of its answer is; this proves it. `failures` carries a segment id per
    fault so the repair can name what to fix instead of asking for the whole
    answer again.
    """
    segments = claim_model.parse(raw)
    ok, failures, cited = claim_model.validate(
        segments,
        widget_keys=turn["widget_keys"],
        section_texts=_section_texts(turn["payload"]),
        corpus=_corpus_for(turn["payload"]),
        company=turn["company"],
        payload=turn["payload"],
        question=turn["question"])
    return ok, failures, cited, segments


def _reason_for(failures: list) -> str:
    """The one-line reason that goes on the response and into the log."""
    if not failures:
        return "ok"
    head = failures[0]
    extra = " (and %d more)" % (len(failures) - 1) if len(failures) > 1 else ""
    return "segment %s: %s%s" % (head["id"], head["reason"], extra)


def _check(turn: dict, text: str) -> tuple:
    """(ok, reason, cited, cleaned) - the validator this turn's mode needs."""
    if turn["persona"]:
        return _validate_roleplay(text, turn["payload"], turn["widget_keys"],
                                  turn["banned"])
    return _validate(text, turn["payload"], turn["widget_keys"])


def _published(turn: dict, cleaned: str, cited: list, attempts: list,
               timer, segments: list | None = None, dropped: int = 0) -> dict:
    """The three outputs, kept apart.

    `answer` is what the seller reads: prose with `[section]` tags the UI turns
    into footnote markers. `answer_clean` is the same prose with none, for
    anything that reuses it - the copy button, an email draft, the history sent
    back to the model. `claims` is the evidence behind each line, so a
    downstream generator can be grounded without ever seeing a tag.
    """
    return {
        "answer": cleaned,
        "answer_clean": claim_model.clean(segments) if segments else cleaned,
        "claims": segments or [],
        "question": turn["question"],
        "topic": turn["topic"],
        "mode": turn["mode"],
        "persona": _persona_summary(turn["persona"]),
        "citations": [_citation(key, turn["sections"]) for key in cited],
        "available": True,
        "generation": {
            "prompt_version": PROMPT_VERSION,
            "model": settings.chat_model,
            "widgets_in_context": len(turn["widget_keys"]),
            "context_chars": len(turn["payload"]),
            "attempts": attempts,
            # Segments dropped after the retry budget was spent, so a partial
            # answer says so rather than looking complete.
            "segments_dropped": dropped,
            # Slowest step first, plus the token counters. Returned as well as
            # logged because the person asking "why did that take so long" is
            # looking at the screen, not the server.
            "timings": timer.as_dict(),
            "tokens": dict(timer.counters),
        },
    }


def _unavailable_for(turn: dict, reason: str, attempts=None, timer=None,
                     cause: str = CAUSE_UNEVIDENCED) -> dict:
    return _unavailable(turn["company"], turn["question"], turn["topic"], reason,
                        attempts, mode=turn["mode"], persona=turn["persona"],
                        timer=timer, cause=cause)


def _answer_once_stream(company: str, question: str, context: str, messages: list,
                        correction: str = "", persona: dict | None = None,
                        timer=None):
    """`_answer_once`, yielding deltas. The prompt is identical."""
    yield from gemini.generate_stream(
        _system_prompt(company, persona, context),
        _answer_turns(question, messages, correction), timer=timer)


def _last_citation_end(buffer: str) -> int:
    """Where the last closed CITATION ends in the buffer, or -1 if there is none.

    The release point for streaming, and it is `_CITATION_RE` rather than the
    last `]` for a reason. Any closing bracket used to extend the released
    prefix, and the model writes brackets that are not citations - "[see
    below]", "[1]", "[TBD]". A claim followed by one of those was published as
    though it had been sourced, which is the opposite of what the rule exists
    for. A bracket that holds no section key now moves nothing.
    """
    end = -1
    for match in _CITATION_RE.finditer(buffer or ""):
        end = match.end()
    return end


def _validated_prefix(turn: dict, buffer: str) -> tuple:
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

    The prefix goes through the same validator the final answer does. Nothing
    is relaxed for streaming - it is the identical function, run earlier.
    """
    end = _last_citation_end(buffer)
    if end == -1:
        return "", False
    ok, _reason, _cited, cleaned = _check(turn, buffer[:end])
    return (cleaned, True) if ok else ("", False)


def answer_stream(account_id: str, messages: list, mode: str | None = None,
                  persona_id: str | None = None):
    """`answer`, yielding the answer as it is written.

    Yields dicts the transport can serialise directly:

        {"type": "stage",  "stage": "reading" | "writing" | "rewriting" | "checking"}
        {"type": "delta",  "text": "...validated text so far..."}
        {"type": "done",   ...the same payload `answer` returns...}

    The contract `answer` holds is unchanged: a seller never reads a sentence
    that has not been checked against the account data. What streaming changes
    is *when* the checked sentences arrive - as each one completes, rather than
    all at the end.

    A rejected answer is never partially published: the final `done` carries the
    validated whole, and a caller that has been rendering deltas replaces what
    it showed with that.

    The timer is never put in scope across a `yield`: the server resumes this
    generator from whatever context it likes, so a context variable set before
    one `yield` is not reliably there after it. Setup runs inside `steps.use`
    with nothing yielded; the streamed generation is timed and counted
    explicitly.
    """
    db = get_db()
    timer = steps.StepTimer()
    with steps.use(timer):
        turn = _prepare(db, timer, account_id, messages, mode, persona_id)
    if "done" in turn:
        yield {"type": "done", **turn["done"]}
        return

    if not turn["persona"]:
        yield from _stream_advisor(timer, turn, messages)
        return

    attempts, correction, last_reason = [], "", "no attempt was made"
    for attempt in range(MAX_VALIDATION_ATTEMPTS):
        # Only the first attempt streams. A retry exists because the previous
        # answer was rejected, and the seller is already reading text from it -
        # streaming a second one over the top would rewrite the thread under
        # them. The retry is written silently and replaces what was shown.
        streaming = attempt == 0
        yield {"type": "stage", "stage": "writing" if streaming else "rewriting"}

        started = time.perf_counter()
        try:
            if streaming:
                # Validated only when a citation bracket *closes*, not on every
                # token that follows one: a new `]` is the only event that can
                # extend the safe prefix.
                buffer, published, last_end = "", "", -1
                for chunk in _answer_once_stream(
                        turn["company"], turn["question"], turn["payload"],
                        messages, correction, turn["persona"], timer):
                    buffer += chunk
                    end = _last_citation_end(buffer)
                    if end == last_end:
                        continue
                    last_end = end
                    safe, ok = _validated_prefix(turn, buffer)
                    if ok and len(safe) > len(published):
                        published = safe
                        yield {"type": "delta", "text": published}
                raw = buffer
            else:
                with steps.use(timer):
                    raw = _answer_once(turn["company"], turn["question"],
                                       turn["payload"], messages, correction,
                                       persona=turn["persona"])
        except gemini.GeminiUnavailable as exc:
            logger.error("strategy chat: %s", exc)
            yield {"type": "done", **_unavailable_for(turn, str(exc), attempts)}
            return
        finally:
            timer.record("generation", (time.perf_counter() - started) * 1000)

        yield {"type": "stage", "stage": "checking"}
        with steps.use(timer), timer.step("validation"):
            ok, reason, cited, cleaned = _check(turn, raw)
        attempts.append({"attempt": attempt + 1, "accepted": ok, "reason": reason})
        if ok:
            _log_timings(timer, turn["question"], accepted=True)
            yield {"type": "done",
                   **_published(turn, cleaned, cited, attempts, timer)}
            return
        last_reason = reason
        correction = reason
        logger.info("strategy chat: attempt %d rejected - %s", attempt + 1, reason)

    _log_timings(timer, turn["question"], accepted=False)
    yield {"type": "done",
           **_unavailable_for(turn, last_reason, attempts, timer)}


def _log_timings(timer, question: str, accepted: bool) -> None:
    """One line per question, carrying the request id the middleware set.

    A rejected answer is logged too, and is the more interesting case: three
    failed attempts means three generations, and the line shows that as
    `generation 41200ms/3` rather than leaving someone to wonder why a question
    took a minute. The cache line is separate because it explains the bill
    rather than the clock - a cached turn and an uncached one look identical on
    the clock and differ several-fold in price.
    """
    logger.info("strategy chat timings: %s | %s | %s | %r",
                timer.summary(), timer.cache_summary() or "cache n/a",
                "accepted" if accepted else "rejected", _text(question)[:80],
                extra={"timings": timer.as_dict(),
                       "tokens": dict(timer.counters),
                       "total_ms": timer.total_ms(),
                       "accepted": accepted})


def _text_block(value) -> str:
    """Like `_text` but keeps the line breaks the context is structured by."""
    return str(value if value is not None else "").strip()


def _is_small_talk(question: str) -> bool:
    """Whether this is an opener rather than a question about the account."""
    stripped = _text(question).lower().strip(" .!?,")
    if len(stripped) < MIN_RETRIEVABLE_CHARS:
        return True
    return stripped in _SMALL_TALK


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


def _unavailable(company, question, topic, reason, attempts=None,  # noqa: PLR0913, PLR0917 - every field of the refusal payload
                 mode: str = "advisor", persona: dict | None = None,
                 timer=None, cause: str = CAUSE_UNEVIDENCED) -> dict:
    closest = ("You could look at the Stakeholder Map, Tech Landscape or Recent "
               "Signals for the nearest related evidence.")
    # The opening line says which of the three things went wrong. It used to
    # assert "nothing in it supports an answer" for all of them, including the
    # case where the model answered and the gate rejected the answer.
    opening = CAUSE_OPENING.get(cause, CAUSE_OPENING[CAUSE_UNEVIDENCED])
    body = "%s\n\n%s" % (opening.format(company=company), closest)
    if persona:
        # Deliberately OUT of character, and this is the one place the
        # simulation breaks on purpose.
        #
        # This path is reached when three attempts failed validation - not when
        # the role legitimately has nothing to say, which the prompt handles in
        # character. Dressing a platform failure as the character stonewalling
        # would read to the seller as an in-scene signal ("he is not biting")
        # and teach them something about a customer that never happened. The
        # simulation may be empty; it may never be wrong.
        body = ("The rehearsal stopped here. Nothing in %s's account "
                "intelligence supports an in-character answer to that, and "
                "rather than let the role invent one I have stopped. Try "
                "rephrasing, or switch to Strategy Advisor to ask directly."
                % company)
    return {
        "answer": body,
        "question": question,
        "topic": topic,
        "mode": mode,
        "persona": _persona_summary(persona),
        "citations": [],
        "answer_clean": body,
        "claims": [],
        "available": False,
        "unavailable_cause": cause,
        "generation": {"prompt_version": PROMPT_VERSION, "reason": reason,
                       "attempts": attempts or [],
                       # The timer rather than two derived dicts: a refusal
                       # wants the same breakdown a published answer gets.
                       "timings": timer.as_dict() if timer else {},
                       "tokens": dict(timer.counters) if timer else {}},
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
