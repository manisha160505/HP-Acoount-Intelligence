"""Typed claims: the advisor answer as structure, validated whole.

The advisor used to write prose with `[widget_key]` tags glued to the end of
every fact-bearing line, and `chat._validate` reconstructed claim boundaries
from that prose - unwrapping wrapped lines, stripping headers and list markers,
splitting on sentence punctuation - then demanded a resolvable tag on every
sentence that asserted anything.

That cost us the answers the feature exists to give. A conclusion -
"Z by HP Workstations has the strongest case right now" - is drawn from several
cited sentences and belongs to no single section, so it can never be legally
tagged, and the whole answer was discarded three times over. Asked which HP
line had the strongest case at an account with 359,000 characters of evidence,
the seller was told "nothing in it supports an answer here".

The deeper problem was that the validator could not tell the two failures
apart. "Astra uses AutoCAD and CATIA" with no tag is a fact the model forgot to
cite and SHOULD fail; "so workstations have the strongest case" is a conclusion
that needs none. Both arrived as untagged prose sentences, so both were
rejected and neither was repaired.

So the model now declares what each piece of its answer IS. Segments
concatenate to the answer, which means claim boundaries are aligned by
construction - there is no second pass guessing which sentence a claim refers
to, because the claim IS the sentence.

Three outputs come off the same list and must never be conflated:

    render()  the answer the seller reads, with `[section]` tags reinserted by
              us after validation - so the existing footnote UI is untouched
    clean()   the same prose with no tags, for anything that reuses the answer
    validate() the grounding decision, which happens before either

Nothing here calls a model or touches the database.
"""

import json
import re

from app.services.extractors.grounding import normalize_hp_product

# What a segment can be. The names are the client's.
FACT = "FACT"
DERIVED = "DERIVED"
SYNTHESIS = "SYNTHESIS"
RECOMMENDATION = "RECOMMENDATION"
GENERAL = "GENERAL"
CLAIM_TYPES = (FACT, DERIVED, SYNTHESIS, RECOMMENDATION, GENERAL)

# The two that assert something about the account and must carry evidence.
EVIDENCED_TYPES = (FACT, DERIVED)

# The two that reason instead of reporting. Both rest on other segments and
# carry no evidence of their own; they differ only in what they may introduce,
# and that difference is the client's own: a conclusion ABOUT the account may
# add nothing, while advice TO THE SELLER is allowed the words advice is made
# of. See `_recommendation_introduces`.
REASONED_TYPES = (SYNTHESIS, RECOMMENDATION)

# Named things that are not claims about the account: the channels a seller's
# own plan is made of. "Follow up on LinkedIn" proposes a medium; it does not
# assert that the account uses one. Deliberately short - anything that could
# also be read as the account's own technology (a CRM, a collaboration suite
# they might run) stays out, because there the name IS a claim.
GENERIC_CHANNELS = frozenset({"linkedin", "inmail", "email", "webinar",
                              "workshop", "roadshow", "newsletter"})

# How a segment sits on the page. Layout is part of the contract because the
# answer is plain text - the UI renders it with `whitespace-pre-wrap` and no
# markdown parser, so paragraph breaks and ALL-CAPS labels are the only
# structure a seller gets.
BLOCK_PARAGRAPH = "paragraph"
BLOCK_BULLET = "bullet"
BLOCK_HEADING = "heading"
BLOCK_LABEL = "label"
BLOCKS = (BLOCK_PARAGRAPH, BLOCK_BULLET, BLOCK_HEADING, BLOCK_LABEL)

MAX_SEGMENTS = 60
MAX_DEPTH = 12

_CONTENT_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z'-]{3,}|\d{2,}")
_DIGIT_RE = re.compile(r"\d[\d,.]*")
_JSON_BLOCK_RE = re.compile(r"\{.*\}", re.S)


class ClaimError(Exception):
    """The model's answer was not a usable segment list."""


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def parse(raw) -> list:
    """The segment list, from whatever the model returned.

    Tolerant on the way in: the model is asked for a bare JSON object and
    mostly obliges, but wraps it in a ```json fence often enough to matter, and
    a rejection for punctuation costs a whole generation. Tolerant about the
    envelope, strict about the contents - `validate` does the judging.
    """
    if isinstance(raw, dict):
        payload = raw
    else:
        text = str(raw or "").strip()
        if not text:
            raise ClaimError("the model returned nothing")
        match = _JSON_BLOCK_RE.search(text)
        if not match:
            raise ClaimError("the model did not return a segment list")
        try:
            payload = json.loads(match.group(0))
        except (TypeError, ValueError) as exc:
            raise ClaimError("the segment list was not valid JSON (%s)"
                             % exc) from exc

    segments = payload.get("segments") if isinstance(payload, dict) else None
    if not isinstance(segments, list) or not segments:
        raise ClaimError("the model returned no segments")

    out = []
    for index, raw_segment in enumerate(segments[:MAX_SEGMENTS]):
        if not isinstance(raw_segment, dict):
            continue
        text = " ".join(str(raw_segment.get("text") or "").split())
        if not text:
            continue
        out.append({
            "id": str(raw_segment.get("id") or "s%d" % (index + 1)).strip(),
            "type": _as_type(raw_segment.get("type")),
            "block": str(raw_segment.get("block") or BLOCK_PARAGRAPH).strip().lower(),
            "text": text,
            "sections": [str(s).strip() for s in (raw_segment.get("sections") or [])
                         if str(s).strip()],
            "quote": " ".join(str(raw_segment.get("quote") or "").split()),
            "depends_on": [str(d).strip() for d in (raw_segment.get("depends_on") or [])
                           if str(d).strip()],
        })
    if not out:
        raise ClaimError("every segment was empty")
    return _infer_dependencies(_unique_ids(out))


def _unique_ids(segments: list) -> list:
    """Rename a repeated id rather than failing the answer over it.

    On a long answer the model reuses one - "c10" twice in 53 segments - and
    that cost a whole generation. A `depends_on` naming the id still resolves
    to the first segment carrying it, which is what a reader would assume,
    and the renamed one keeps its own text and its own dependencies.
    """
    seen: dict = {}
    for segment in segments:
        base = segment["id"]
        if base not in seen:
            seen[base] = 1
            continue
        seen[base] += 1
        segment["id"] = "%s-%d" % (base, seen[base])
        segment["renamed_from"] = base
    return segments


def _infer_dependencies(segments: list) -> list:
    """A conclusion with no stated dependencies rests on the facts above it.

    The model omits `depends_on` often enough to cost a generation, and the
    answer is ordered: a SYNTHESIS that follows three FACTs is concluding from
    those three. Inferring it loosens nothing - the inferred list goes through
    the same check as a stated one, so a conclusion reaching past the facts
    above it still fails, and now fails for the right reason.
    """
    # Everything the answer evidences, read before anything is judged - the
    # answer leads with its conclusion, so the facts a leading conclusion
    # rests on are below it, not above.
    everything = [s["id"] for s in segments if s["type"] in EVIDENCED_TYPES]
    carries: dict = {}
    for segment in segments:
        if segment["type"] in EVIDENCED_TYPES:
            for token in _named_entities(segment["text"]):
                carries.setdefault(token, segment["id"])

    evidenced: list = []
    for segment in segments:
        if segment["type"] in EVIDENCED_TYPES:
            evidenced.append(segment["id"])
            continue
        if segment["type"] not in REASONED_TYPES:
            continue
        if not segment["depends_on"]:
            # Facts above it when there are any. A conclusion that OPENS the
            # answer - the house format, not a mistake - rests on the facts
            # below instead, and on the ones carrying what it actually names
            # rather than on all of them: resting it on everything put eight
            # footnote markers on every line of the answer.
            segment["depends_on"] = (list(evidenced)
                                     or _linked_to(segment, carries)
                                     or list(everything))
            segment["inferred_depends_on"] = True
            continue
        # Stated some dependencies but not all of them. Trace each thing the
        # conclusion names to the evidenced segment that carries it; a name no
        # segment carries is left alone and fails below, which is the point.
        linked = list(segment["depends_on"])
        for token in _named_entities(segment["text"]):
            owner = carries.get(token)
            if owner and owner not in linked:
                linked.append(owner)
                segment["linked_depends_on"] = True
        segment["depends_on"] = linked
    return segments


def _linked_to(segment, carries: dict) -> list:
    """The evidenced segments carrying the things this one names, in order."""
    linked: list = []
    for token in sorted(_named_entities(segment["text"])):
        owner = carries.get(token)
        if owner and owner not in linked:
            linked.append(owner)
    return linked


# A heading and a label are GENERAL claims that happen to sit on their own
# line, and the model reaches for them as a TYPE as readily as a block - it
# cost a whole generation the first time it did. Forgiving about which field
# the word landed in; `validate` is where the judging happens.
_TYPE_ALIASES = {
    "HEADING": GENERAL, "LABEL": GENERAL, "TITLE": GENERAL,
    "CONCLUSION": SYNTHESIS,
    "INFERENCE": DERIVED,
    # RECOMMENDATION used to fold into SYNTHESIS, which is what made a plan
    # unpublishable. These now reach the type that can carry one.
    "ADVICE": RECOMMENDATION, "NEXT_STEP": RECOMMENDATION,
    "NEXT STEP": RECOMMENDATION, "STEP": RECOMMENDATION,
    "PLAN": RECOMMENDATION, "ACTION": RECOMMENDATION,
}


def _as_type(raw) -> str:
    value = str(raw or GENERAL).strip().upper()
    return _TYPE_ALIASES.get(value, value)


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def validate(segments: list, *, widget_keys, section_texts: dict,  # noqa: PLR0913, PLR0917 - the whole grounding context, passed explicitly
             corpus, company: str = "", payload: str = "",
             question: str = "") -> tuple:
    """(ok, failures, resolved_keys).

    `failures` is a list of {"id", "reason"} so a repair can name the segment
    that failed rather than asking for the whole answer again. A segment with
    no entry in `failures` is validated and may be published.

    The order of the checks is the order a reader would want them reported in:
    shape first, because a malformed list makes every other answer nonsense;
    then evidence per segment; then the whole-answer checks that only make
    sense once the segments are known good.
    """
    valid_keys = set(widget_keys or [])
    failures: list = []
    by_id = {}
    for segment in segments:
        if segment["id"] in by_id:
            failures.append({"id": segment["id"],
                             "reason": "two segments share this id"})
            continue
        by_id[segment["id"]] = segment

    for segment in segments:
        exempt = _company_tokens(company) | _question_tokens(question)
        reason = _segment_failure(segment, by_id, valid_keys, section_texts,
                                  corpus, company, exempt)
        if reason:
            failures.append({"id": segment["id"], "reason": reason})

    failed_ids = {f["id"] for f in failures}

    # A synthesis resting on a rejected claim is itself unsupported, however
    # well formed it is. Propagated rather than checked in the loop above
    # because a dependency can fail after its dependent has been read.
    for segment in _in_dependency_order(segments, by_id):
        if segment["id"] in failed_ids:
            continue
        broken = [d for d in segment["depends_on"] if d in failed_ids]
        if broken:
            failures.append({
                "id": segment["id"],
                "reason": "it rests on %s, which did not hold"
                          % ", ".join(sorted(broken)[:3])})
            failed_ids.add(segment["id"])

    survivors = [s for s in segments if s["id"] not in failed_ids]

    # The whole-answer checks. Run over what would actually be published, so a
    # figure inside a segment that is about to be dropped is not held against
    # the answer that remains.
    # Two texts, deliberately. The HP-product sweep runs over everything,
    # recommendations included - naming an HP line the account has no evidence
    # for is forbidden wherever it appears. The FIGURE sweep skips
    # recommendations: their numbers are the plan's own schedule, already
    # judged per segment by the cadence rule, and sweeping them here would
    # reject "week 2" for not appearing in the account's data - which is
    # exactly what made a week-by-week plan impossible to publish.
    clean_text = clean(survivors)
    figure_text = clean([s for s in survivors
                         if s["type"] != RECOMMENDATION])
    if figure_text:
        unsourced = corpus.unsourced_numbers(figure_text)
        if unsourced:
            failures.append({
                "id": _segment_carrying(survivors, unsourced[0]),
                "reason": "it states figure(s) that are not in the evidence: %s"
                          % ", ".join(unsourced[:4])})
    if clean_text:
        hp_fault = _unsupported_hp_line(clean_text, payload)
        if hp_fault:
            failures.append({"id": _segment_carrying(survivors, hp_fault),
                             "reason": "it names %s, which does not appear in "
                                       "this account's evidence" % hp_fault})

    failed_ids = {f["id"] for f in failures}
    resolved = []
    for segment in segments:
        if segment["id"] in failed_ids:
            continue
        for key in _sections_for(segment, by_id):
            if key not in resolved:
                resolved.append(key)
    return (not failures), failures, resolved


def _company_tokens(company: str) -> set:
    """The account's own name, which a conclusion may always say.

    "Astra's security leadership" names the account, not a new entity in it.
    Possessives included, because that is how a conclusion writes it.
    """
    tokens = set()
    for word in re.findall(r"[A-Za-z]{2,}", company or ""):
        tokens.add(word.lower())
        tokens.add(word.lower() + "'s")
    return tokens


def _question_tokens(question: str) -> set:
    """The words the seller used, which the answer may use back.

    "Include week-by-week activities, target personas, content types, and
    success metrics" and then the answer is rejected for naming Personas and
    Metrics. Echoing the question is not inventing a fact about the account,
    and these are capitalised only because they head a line.
    """
    return {w.lower() for w in re.findall(r"[A-Za-z]{3,}", question or "")}


def _segment_failure(segment, by_id, valid_keys, section_texts, corpus, company,  # noqa: PLR0911 - a rule per branch; collapsing them would hide which rule fired
                     company_tokens=frozenset()):
    """Why this one segment cannot be published, or "" when it can."""
    if segment["type"] not in CLAIM_TYPES:
        return "%r is not a claim type" % segment["type"]
    if segment["block"] not in BLOCKS:
        return "%r is not a block kind" % segment["block"]

    if segment["type"] in EVIDENCED_TYPES:
        if not segment["sections"]:
            return "it states something about the account and cites no section"
        unknown = [k for k in segment["sections"] if k not in valid_keys]
        if unknown:
            # The cross-account isolation check. The payload is built scoped to
            # one account, so a key naming anything else cannot resolve.
            return ("it cites %s, which is not a section of this account's data"
                    % ", ".join(unknown[:3]))
        if not segment["quote"]:
            return "it cites a section but quotes nothing from it"
        if not corpus.contains(segment["quote"]):
            return ("its quote %r does not appear in this account's data"
                    % segment["quote"][:60])
        cited_text = " ".join(section_texts.get(k, "") for k in segment["sections"])
        if segment["quote"].lower() not in cited_text.lower():
            # A tag proves the model ASSERTED an attribution. The quote proves
            # it. Without this a claim survives by carrying a plausible key and
            # a quote lifted from somewhere else entirely.
            return ("its quote %r is not in the section it cites"
                    % segment["quote"][:60])
        return ""

    if segment["type"] in REASONED_TYPES:
        if not segment["depends_on"]:
            return ("it draws a conclusion but names no claim it rests on"
                    if segment["type"] == SYNTHESIS else
                    "it recommends something but names no claim it rests on")
        missing = [d for d in segment["depends_on"] if d not in by_id]
        if missing:
            return "it rests on %s, which is not in the answer" % ", ".join(missing[:3])
        if segment["type"] == SYNTHESIS:
            return _synthesis_introduces(segment, by_id, section_texts,
                                         company_tokens, corpus)
        return _recommendation_introduces(segment, by_id, section_texts,
                                          company_tokens, corpus)

    # GENERAL - reasoning that is not about this account, and must not read as
    # though it were.
    if company and company.lower() in segment["text"].lower():
        return ("it names %s, so it is a claim about the account and needs "
                "evidence" % company)
    # A figure in general prose is a claim with no evidence - "most estates
    # of 4,000 seats" is exactly what this catches. The plan's own schedule
    # is not: "WEEK 1-2" is how a week-by-week answer is laid out, and the
    # prompt asks for headings to be typed GENERAL, so rejecting numbered
    # ones rejected eighteen segments of a 90-day plan at a stroke.
    unscheduled = _digits_in(segment["text"]) - _plan_figures(segment["text"])
    if unscheduled:
        return "it carries a figure, so it is a claim about the account"
    return ""


def _synthesis_introduces(segment, by_id, section_texts,
                          company_tokens=frozenset(), corpus=None) -> str:
    """Whether a conclusion smuggles in something new. "" when it does not.

    The rule, as the client set it: a synthesis sentence is allowed without its
    own tag when it only summarises, compares or concludes from facts already
    supported. It must not introduce a new account fact, number, technology,
    relationship or event.

    The test is not "is this word new" but "is this word a thing". Every
    category the client named - a fact, a number, a technology, a
    relationship, an event - is a NAMED entity, and in English those are
    proper nouns, figures and product lines. A lowercase word that appears in
    neither the dependencies nor their sections is prose; a capitalised one is
    a vendor, a person or a place the conclusion has just invented.

    An earlier version compared the entire vocabulary and rejected
    "specifically", "driven" and "plans". It published three bare facts and
    dropped the conclusion they were there to support.
    """
    supported, supported_digits = _supported_by(segment, by_id, section_texts)

    # A figure is a claim whatever its case, so it is judged on its own.
    new_digits = _unsupported_digits(segment["text"], supported_digits, corpus)
    if new_digits:
        return ("it states figure(s) that are not in this account's evidence: "
                "%s" % ", ".join(sorted(new_digits)[:3]))

    named = _unsupported_names(segment["text"], supported, company_tokens,
                               corpus)
    if named:
        return ("it names %s, which does not appear in this account's "
                "evidence" % ", ".join(sorted(named)[:4]))
    return ""


def _supported_by(segment, by_id, section_texts) -> tuple:
    """What the claims underneath a segment already carry: (words, figures).

    Both the dependency's own text and the text of the sections it cites - a
    conclusion resting on a fact may use any word the fact's evidence uses,
    not only the ones the fact chose to repeat.
    """
    supported = set()
    supported_digits = set()
    for dependency_id in segment["depends_on"]:
        dependency = by_id.get(dependency_id)
        if not dependency:
            continue
        supported |= _content_tokens(dependency["text"])
        supported |= _named_entities(dependency["text"])
        supported_digits |= _digits_in(dependency["text"])
        for key in dependency["sections"]:
            section = section_texts.get(key, "")
            supported |= _content_tokens(section)
            supported |= {w.lower() for w in re.findall(r"[A-Za-z]{3,}", section)}
            supported_digits |= _digits_in(section)
    return supported, supported_digits


# The numbers a plan is made of. "week 1", "within 30 days", "three touches",
# "a 90-day plan", "30/60/90" - each proposes something the seller should do
# and asserts nothing about the account, so none of them is held against the
# evidence the way an account figure is.
_PLAN_UNITS = (
    r"day|days|week|weeks|month|months|quarter|quarters|year|years|"
    r"hour|hours|minute|minutes|touch|touches|email|emails|call|calls|"
    r"meeting|meetings|session|sessions|follow-?up|follow-?ups|step|steps|"
    r"phase|phases|sprint|sprints|wave|waves|message|messages")
_PLAN_FIGURE_RE = re.compile(
    # "week 2", "phase 1", and the forms a real plan uses: a range
    # ("weeks 1-4") and a list ("weeks 2, 5 and 9").
    r"\b(?:%s)\s*#?\s*\d+(?:\s*(?:[-,/&]|to|and|through)\s*\d+)*"
    r"|\b\d+\s*-?\s*(?:%s)\b"     # "30 days", "90-day", "3 touches"
    r"|\b\d+\s*/\s*\d+"           # "30/60/90"
    % (_PLAN_UNITS, _PLAN_UNITS), re.IGNORECASE)


def _plan_figures(text: str) -> set:
    """The figures in `text` that are part of the plan's own schedule."""
    found = set()
    for match in _PLAN_FIGURE_RE.finditer(text or ""):
        found |= _digits_in(match.group(0))
    return found


def _recommendation_introduces(segment, by_id, section_texts,
                               company_tokens=frozenset(), corpus=None) -> str:
    """Whether advice asserts something about the account. "" when it does not.

    **This is not the synthesis rule relaxed.** SYNTHESIS keeps the client's
    rule exactly as they wrote it - a conclusion may add no name, number,
    technology, relationship or event its dependencies do not carry. This is
    the other half of the client's own distinction, the half the single strict
    rule left unimplemented: *a fact needs evidence, a recommendation needs
    reasoning that rests on evidence*.

    What a recommendation may do that a conclusion may not: use the vocabulary
    of a plan. A cadence, a count of touches, a channel. "Open with a short
    note in week 1" states nothing about the customer that could be true or
    false of them - it is the advice itself.

    What it still may not do, unchanged: name a person, a vendor, an HP line,
    a title or a figure that purports to be the account's. Those are facts,
    they need their own evidence, and the recommendation then rests on them.
    """
    supported, supported_digits = _supported_by(segment, by_id, section_texts)

    new_digits = (_unsupported_digits(segment["text"], supported_digits, corpus)
                  - _plan_figures(segment["text"]))
    if new_digits:
        return ("it states figure(s) that are neither in this account's "
                "evidence nor part of the plan's own schedule: %s"
                % ", ".join(sorted(new_digits)[:3]))

    named = _unsupported_names(segment["text"], supported,
                               set(company_tokens) | GENERIC_CHANNELS, corpus)
    if named:
        return ("it names %s, which does not appear in this account's "
                "evidence" % ", ".join(sorted(named)[:4]))
    return ""


def _unsupported_digits(text: str, supported_digits: set, corpus) -> set:
    """Figures in `text` that are in neither the dependencies nor the corpus.

    The corpus is `context.build()` - every contributing feature's published
    output. A figure that appears anywhere in it is a figure the platform
    holds, whether or not the sentence citing it listed that section.
    """
    unsupported = set()
    for token in _digits_in(text) - supported_digits:
        if not _corpus_has_digit(token, corpus):
            unsupported.add(token)
    return unsupported


def _corpus_has_digit(token: str, corpus) -> bool:
    """Whether the account's evidence carries this figure.

    Normalised the way `grounding` normalises - it stores "10,001" as "10001",
    so the two have to be flattened the same way before they are compared.
    """
    if corpus is None:
        return False
    flat = re.sub(r"[,\s]", "", str(token or "")).rstrip(".")
    if not flat:
        return False
    numbers = getattr(corpus, "numbers", set())
    percents = getattr(corpus, "percents", set())
    if flat in numbers or flat in percents:
        return True
    # "36" should be found by evidence reading "36.0", and the reverse.
    return "." in flat and flat.split(".")[0] in numbers


def _unsupported_names(text: str, supported: set, exempt, corpus) -> set:
    """Named things in `text` that are in neither the dependencies nor the
    corpus.

    Matched on a word boundary against the corpus blob rather than as a
    substring: "sap" must not be satisfied by "sapphire". Possessives are
    tried both ways, because a conclusion writes "Kaspersky's agent" and the
    evidence says "Kaspersky".
    """
    unsupported = set()
    for word in _named_entities(text) - supported - set(exempt or ()):
        if not _corpus_has_name(word, corpus):
            unsupported.add(word)
    return unsupported


def _corpus_has_name(word: str, corpus) -> bool:
    blob = getattr(corpus, "blob", "") if corpus is not None else ""
    if not blob or not word:
        return False
    # "workstations'" and "Kaspersky's" are both the word itself.
    for form in {word, re.sub(r"['\u2019]s?$", "", word)}:
        if form and re.search(r"\b%s\b" % re.escape(form), blob):
            return True
    return False


def _is_title_case(words: list) -> bool:
    """Whether this reads as a heading rather than as a sentence.

    Judged on the words that could carry a name at all - the first is
    capitalised by grammar and ALL-CAPS runs are labels already. Most of them
    capitalised means the capitals are layout.

    Deliberately hard to trigger. A looser version swallowed "Approach Mike
    Higgins in week 1" - two capitals out of three words - and let an
    invented person through, which is the one thing this check exists to
    stop. A real heading is longer than that and almost entirely capitalised.
    """
    eligible = [w for w in words[1:] if len(w) >= 3 and not w.isupper()]
    if len(eligible) < 4:
        return False
    capitalised = sum(1 for w in eligible if w[0].isupper())
    return capitalised / len(eligible) > 0.7


def _named_entities(text: str) -> set:
    """Tokens that assert a thing: proper nouns, and HP lines however spelled.

    The first word of a sentence is skipped - it is capitalised by grammar,
    not because it names anything - and so are ALL-CAPS runs, which are labels
    and are already accounted for by the block type.
    """
    found = set()
    # Clauses, not only sentences: a bullet reads "Content: Send an
    # introductory email", and the word after the colon is capitalised for
    # the same reason the first word of a sentence is. Treating it as a name
    # rejected an otherwise good plan for "naming" send.
    for sentence in re.split(r"(?<=[.!?:;])\s+", text or ""):
        words = re.findall(r"[A-Za-z][\w'-]*", sentence)
        if _is_title_case(words):
            # A heading or a label: every word is capitalised because of how
            # it sits on the page, not because it names anything. Reading
            # these as names turned "Target Personas" and "Discovery &
            # Awareness" into invented vendors and rejected the plan's own
            # scaffolding. What a label names is still swept by the HP-product
            # check and by every claim segment that discusses it.
            continue
        for index, word in enumerate(words):
            if index == 0 or len(word) < 3 or word.isupper():
                continue
            if word[0].isupper():
                # "Astra's" and "Astra" are the same name. Both forms are
                # kept so either spelling in a dependency covers the other.
                lowered = word.lower()
                found.add(lowered)
                found.add(re.sub(r"['\u2019]s?$", "", lowered))
    line = normalize_hp_product(text)
    if line:
        found |= {w.lower() for w in re.findall(r"[A-Za-z]{3,}", line)}
    return found


def _digits_in(text: str) -> set:
    return {d.strip(".,") for d in _DIGIT_RE.findall(text or "") if d.strip(".,")}


def _content_tokens(text: str) -> set:
    """Mirrors `chat._content_tokens` - kept here so this module stands alone."""
    return {t.lower() for t in _CONTENT_TOKEN_RE.findall(text or "")
            if t.lower() not in _STOPWORDS}


_STOPWORDS = frozenset({
    "that", "this", "these", "those", "they", "them", "their", "there", "then",
    "than", "with", "from", "have", "has", "had", "been", "being", "were",
    "will", "would", "could", "should", "what", "when", "where", "which",
    "your", "yours", "our", "ours", "you", "about", "into", "over", "just",
    "like", "want", "need", "know", "think", "said", "says", "tell", "told",
    "here", "very", "much", "more", "most", "some", "any", "not", "but", "and",
    "for", "the", "are", "was", "does", "did", "doing", "going", "get", "got",
})


def _unsupported_hp_line(text: str, payload: str) -> str:
    """An HP line named in the answer that the account's evidence never mentions.

    The prompt has always said "name an HP product only if it appears in the
    evidence" and nothing checked it. Uses the same resolver the extractors
    use, so a line spelled loosely in prose still resolves to its canonical
    name before the payload is searched.
    """
    if not payload:
        return ""
    low = payload.lower()
    for phrase in re.findall(r"\b(?:HP|Poly|Z by HP)[\w /&+()-]{2,40}", text):
        line = normalize_hp_product(phrase)
        if line and line.lower() not in low and phrase.strip().lower() not in low:
            return line
    return ""


def _segment_carrying(segments, needle: str) -> str:
    """The id of the segment a whole-answer fault came from, for the repair."""
    for segment in segments:
        if needle and needle.lower() in segment["text"].lower():
            return segment["id"]
    return segments[0]["id"] if segments else ""


def _in_dependency_order(segments, by_id) -> list:
    """Segments with their dependencies before them, cycles broken.

    A cycle cannot be resolved, so the segments in it are returned last and
    their dependency check simply fails - which is the right answer for a
    conclusion that rests on itself.
    """
    ordered, seen = [], set()

    def visit(segment, depth):
        if segment["id"] in seen or depth > MAX_DEPTH:
            return
        seen.add(segment["id"])
        for dependency_id in segment["depends_on"]:
            dependency = by_id.get(dependency_id)
            if dependency:
                visit(dependency, depth + 1)
        ordered.append(segment)

    for segment in segments:
        visit(segment, 0)
    return ordered


# ---------------------------------------------------------------------------
# Rendering - three outputs, one list
# ---------------------------------------------------------------------------

def _sections_for(segment, by_id) -> list:
    """The sections a segment shows to the reader.

    A FACT shows its own. A SYNTHESIS shows the union of the ones underneath
    it: the conclusion did not come from a section, but the seller still needs
    to see what it rests on, and the client asked for it explicitly.
    """
    if segment["type"] in EVIDENCED_TYPES:
        return list(segment["sections"])
    if segment["type"] not in REASONED_TYPES:
        return []
    out = []
    for dependency_id in segment["depends_on"]:
        dependency = by_id.get(dependency_id)
        for key in (dependency or {}).get("sections") or []:
            if key not in out:
                out.append(key)
    return out


def render(segments: list) -> str:
    """The answer the seller reads, with citation tags reinserted by us.

    The tags are literal `[widget_key]` text because that is what the UI
    parses: `AnswerWithCitations` matches the tokens inside each bracket
    against `citations[].evidence_id` to place its footnote markers, and drops
    the bracket. Emitting them here rather than demanding them from the model
    is the whole point of this module - the grounding decision is made first,
    and the citation is a consequence of it.
    """
    by_id = {s["id"]: s for s in segments}
    return _join(segments, lambda s: _with_tag(s["text"], _sections_for(s, by_id)))


def clean(segments: list) -> str:
    """The same prose with no tags, for anything that reuses the answer.

    The copy button, the email draft and the conversation history all used to
    carry `[tech_stack_matrix]` into places it means nothing. This is what they
    take instead.
    """
    return _join(segments, lambda s: s["text"])


def _join(segments, text_of) -> str:
    lines: list = []
    for segment in segments:
        text = text_of(segment)
        if not text:
            continue
        if segment["block"] == BLOCK_BULLET:
            lines.append("- %s" % text)
        elif segment["block"] in (BLOCK_HEADING, BLOCK_LABEL):
            if lines:
                lines.append("")
            lines.append(text)
        else:
            if lines and lines[-1] and not lines[-1].startswith("- "):
                lines.append("")
            lines.append(text)
    return "\n".join(lines).strip()


def _with_tag(text: str, sections: list) -> str:
    if not sections:
        return text
    return "%s [%s]" % (text.rstrip(), ", ".join(sections))


# ---------------------------------------------------------------------------
# Repair
# ---------------------------------------------------------------------------

def repair_notes(failures: list) -> str:
    """What to tell the model so it can fix exactly what failed.

    Named per segment. The old validator could only say "it states 6 thing(s)
    about the account without citing any evidence" and hand back two truncated
    prefixes, which asked the model to find the problem as well as fix it.
    """
    if not failures:
        return ""
    lines = ["Your previous answer was rejected. Fix ONLY these segments and "
             "return the complete segment list again, carrying every other "
             "segment through unchanged:"]
    for failure in failures[:8]:
        lines.append("  - segment %s: %s" % (failure["id"], failure["reason"]))
    lines.append("A segment that states a fact about the account needs its "
                 "section AND a verbatim quote from that section. A SYNTHESIS "
                 "or RECOMMENDATION needs depends_on, and may reason freely - "
                 "but every name, number and product it uses must appear "
                 "somewhere in the ACCOUNT DATA. If you want to name something "
                 "the data does not contain, you cannot: say what the data "
                 "does hold instead.")
    return "\n".join(lines)


def surviving(segments: list, failures: list) -> list:
    """What is left once the failures and anything resting on them are dropped.

    The last resort, after the retry budget is spent: publishing the part of an
    answer that held is better than telling a seller the platform holds nothing
    when it holds 359,000 characters. Returns [] when nothing substantive
    survives, and the caller refuses.
    """
    failed = {f["id"] for f in failures}
    by_id = {s["id"]: s for s in segments}
    kept = []
    for segment in _in_dependency_order(segments, by_id):
        if segment["id"] in failed:
            continue
        if any(d in failed for d in segment["depends_on"]):
            failed.add(segment["id"])
            continue
        kept.append(segment)
    order = {s["id"]: i for i, s in enumerate(segments)}
    kept.sort(key=lambda s: order.get(s["id"], 0))
    kept = _drop_empty_headings(kept)
    if not any(s["type"] in (FACT, DERIVED, *REASONED_TYPES) for s in kept):
        return []
    return kept


def _drop_empty_headings(segments: list) -> list:
    """A heading with nothing under it is worse than no heading.

    Reached only after segments have been dropped: "RECOMMENDED NEXT STEPS:"
    above an empty space reads as a section the platform failed to write,
    rather than one it had nothing to say in.
    """
    out = []
    for index, segment in enumerate(segments):
        if segment["block"] not in (BLOCK_HEADING, BLOCK_LABEL):
            out.append(segment)
            continue
        # Only as far as the next heading. Looking all the way down kept
        # "WEEK 5-8" on screen with nothing under it, on the strength of
        # "WEEK 9-12" further along having survived.
        has_content = False
        for later in segments[index + 1:]:
            if later["block"] in (BLOCK_HEADING, BLOCK_LABEL):
                break
            has_content = True
            break
        if has_content:
            out.append(segment)
    return out
