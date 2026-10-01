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
GENERAL = "GENERAL"
CLAIM_TYPES = (FACT, DERIVED, SYNTHESIS, GENERAL)

# The two that assert something about the account and must carry evidence.
EVIDENCED_TYPES = (FACT, DERIVED)

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
    return _infer_dependencies(out)


def _infer_dependencies(segments: list) -> list:
    """A conclusion with no stated dependencies rests on the facts above it.

    The model omits `depends_on` often enough to cost a generation, and the
    answer is ordered: a SYNTHESIS that follows three FACTs is concluding from
    those three. Inferring it loosens nothing - the inferred list goes through
    the same check as a stated one, so a conclusion reaching past the facts
    above it still fails, and now fails for the right reason.
    """
    evidenced: list = []
    carries: dict = {}
    for segment in segments:
        if segment["type"] in EVIDENCED_TYPES:
            evidenced.append(segment["id"])
            for token in _named_entities(segment["text"]):
                carries.setdefault(token, segment["id"])
            continue
        if segment["type"] != SYNTHESIS:
            continue
        if not segment["depends_on"]:
            segment["depends_on"] = list(evidenced)
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


# A heading and a label are GENERAL claims that happen to sit on their own
# line, and the model reaches for them as a TYPE as readily as a block - it
# cost a whole generation the first time it did. Forgiving about which field
# the word landed in; `validate` is where the judging happens.
_TYPE_ALIASES = {
    "HEADING": GENERAL, "LABEL": GENERAL, "TITLE": GENERAL,
    "CONCLUSION": SYNTHESIS, "RECOMMENDATION": SYNTHESIS,
    "INFERENCE": DERIVED, "ADVICE": SYNTHESIS,
}


def _as_type(raw) -> str:
    value = str(raw or GENERAL).strip().upper()
    return _TYPE_ALIASES.get(value, value)


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def validate(segments: list, *, widget_keys, section_texts: dict,
             corpus, company: str = "", payload: str = "") -> tuple:
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
        reason = _segment_failure(segment, by_id, valid_keys, section_texts,
                                  corpus, company, _company_tokens(company))
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
    clean_text = clean(survivors)
    if clean_text:
        unsourced = corpus.unsourced_numbers(clean_text)
        if unsourced:
            failures.append({
                "id": _segment_carrying(survivors, unsourced[0]),
                "reason": "it states figure(s) that are not in the evidence: %s"
                          % ", ".join(unsourced[:4])})
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

    if segment["type"] == SYNTHESIS:
        if not segment["depends_on"]:
            return "it draws a conclusion but names no claim it rests on"
        missing = [d for d in segment["depends_on"] if d not in by_id]
        if missing:
            return "it rests on %s, which is not in the answer" % ", ".join(missing[:3])
        return _synthesis_introduces(segment, by_id, section_texts,
                                     company_tokens)

    # GENERAL - reasoning that is not about this account, and must not read as
    # though it were.
    if company and company.lower() in segment["text"].lower():
        return ("it names %s, so it is a claim about the account and needs "
                "evidence" % company)
    if _DIGIT_RE.search(segment["text"]):
        return "it carries a figure, so it is a claim about the account"
    return ""


def _synthesis_introduces(segment, by_id, section_texts,
                          company_tokens=frozenset()) -> str:
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

    # A figure is a claim whatever its case, so it is judged on its own.
    new_digits = _digits_in(segment["text"]) - supported_digits
    if new_digits:
        return ("it states figure(s) none of the claims it rests on carry: %s"
                % ", ".join(sorted(new_digits)[:3]))

    named = _named_entities(segment["text"]) - supported - set(company_tokens)
    if named:
        return ("it names %s, which is in none of the claims it rests on - "
                "state that as a FACT with its own evidence first"
                % ", ".join(sorted(named)[:4]))
    return ""


def _named_entities(text: str) -> set:
    """Tokens that assert a thing: proper nouns, and HP lines however spelled.

    The first word of a sentence is skipped - it is capitalised by grammar,
    not because it names anything - and so are ALL-CAPS runs, which are labels
    and are already accounted for by the block type.
    """
    found = set()
    for sentence in re.split(r"(?<=[.!?])\s+", text or ""):
        words = re.findall(r"[A-Za-z][\w'-]*", sentence)
        for index, word in enumerate(words):
            if index == 0 or len(word) < 3 or word.isupper():
                continue
            if word[0].isupper():
                # "Astra's" and "Astra" are the same name. Both forms are
                # kept so either spelling in a dependency covers the other.
                lowered = word.lower()
                found.add(lowered)
                found.add(re.sub(r"['\u2019]s$", "", lowered))
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
    if segment["type"] != SYNTHESIS:
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
                 "section AND a verbatim quote from that section. A segment "
                 "that only draws a conclusion needs depends_on, and must add "
                 "no name, number or technology its dependencies do not carry.")
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
    if not any(s["type"] in (FACT, DERIVED, SYNTHESIS) for s in kept):
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
        has_content = any(
            later["block"] not in (BLOCK_HEADING, BLOCK_LABEL)
            for later in segments[index + 1:])
        if has_content:
            out.append(segment)
    return out
