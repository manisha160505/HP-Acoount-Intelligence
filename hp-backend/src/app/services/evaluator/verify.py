"""Step E - what Python checks after the model answers.

Three things the model is asked for cannot be taken on trust, and each is
re-derived or re-checked here:

  * **Phrase feedback** must point at text the seller actually wrote. The model
    returns a quotation; this module finds that quotation in the draft by
    string search. A chunk that cannot be located is dropped and counted. It is
    never re-anchored onto nearby text, because a Keep/Improve/Change label
    attached to the wrong span is worse than no label - the seller edits the
    wrong sentence.

  * **The simulated reaction may not invent anything about the real person.**
    The prompt says so; this module enforces it. The contact's name may not
    appear, no belief/decision/intention/quotation may be attributed to the
    individual, and the whole thing is stored with a simulation label so it can
    never be read as reporting what the real contact said.

  * **A rewrite may not smuggle in new claims.** Facts present in the original
    must survive it, and any figure, link, superlative or competitor name that
    appears in the rewrite but not the original is checked against the source
    that has authority over it - HP claims against the HP corpus, account
    claims against the account corpus.

The through-line is the rule from Step D: the seller's own draft is not
evidence. A polished unsupported claim stays unsupported, and carrying it into
the rewrite unchanged would launder it.
"""

import logging
import re

from app.services.evaluator.sources import (
    SUPERLATIVE_RE, COMPETITOR_RE, VERDICT_SUPPORTED, VERDICT_UNSUPPORTED,
    VERDICT_RESTRICTED, VERDICT_NOT_CHECKABLE,
)

logger = logging.getLogger(__name__)

KEEP = "Keep"
IMPROVE = "Improve"
CHANGE = "Change"
VERDICTS = (KEEP, IMPROVE, CHANGE)

FACTUAL = "factual_grounding"
STYLE = "style"

_NUMBER_RE = re.compile(r"\d[\d,\.]*")
_URL_RE = re.compile(r"https?://[^\s\"'<>)\]]+", re.I)

# Attributing an inner state to the individual. The evaluator simulates how a
# role would react; it does not report what a person thinks.
_ATTRIBUTION_RE = re.compile(
    r"\b(thinks?|believes?|feels?|wants?|knows?|decided|has decided|intends?|"
    r"plans? to|is looking for|is worried|is concerned|would never|"
    r"told me|said that|mentioned that|confirmed that|agreed that|"
    r"is frustrated|is excited|is interested in|prefers?)\b", re.I)

# Third-person singular framing of a specific human ("he will", "she would").
_PERSONAL_PRONOUN_RE = re.compile(r"\b(he|she|his|her|him|hers)\b", re.I)

SIMULATION_LABEL = ("Simulated reaction - how someone in this role would likely "
                    "read this message. Not a statement about the real contact.")


def _text(value) -> str:
    return " ".join(str(value or "").split())


# ---------------------------------------------------------------------------
# Phrase feedback
# ---------------------------------------------------------------------------

def verify_phrases(raw_phrases, sources, max_chunks=None):
    """Locate every phrase in the draft and classify its problem type.

    Returns (phrases, dropped). A phrase survives only if its quoted text is
    found in the submitted draft.
    """
    phrases, dropped = [], []
    seen_spans = set()

    for item in (raw_phrases or []):
        if not isinstance(item, dict):
            dropped.append({"reason": "not an object", "chunk": _text(item)[:120]})
            continue

        chunk = _text(item.get("chunk") or item.get("text") or item.get("phrase"))
        if not chunk:
            dropped.append({"reason": "no chunk text returned", "chunk": ""})
            continue

        span = sources.locate(chunk)
        if not span:
            # The model quoted something the seller did not write.
            dropped.append({"reason": "not found in the submitted message",
                            "chunk": chunk[:160]})
            continue

        if span in seen_spans:
            dropped.append({"reason": "duplicate span", "chunk": chunk[:160]})
            continue
        seen_spans.add(span)

        verdict = _text(item.get("verdict") or item.get("label"))
        verdict = next((v for v in VERDICTS if v.lower() == verdict.lower()), IMPROVE)

        # The draft's exact wording, taken from the draft itself rather than
        # from the model's quotation of it.
        exact = sources.draft[span[0]:span[1]]

        # A grounding problem is separated from a style problem, because a
        # polished unsupported claim must still be flagged as factual.
        check = sources.verify_claim(exact, "phrase")
        if check["verdict"] in (VERDICT_UNSUPPORTED, VERDICT_RESTRICTED):
            problem_type = FACTUAL
            # Never label an unsupported claim "Keep".
            if verdict == KEEP:
                verdict = CHANGE
        else:
            problem_type = STYLE

        phrases.append({
            "chunk": exact,
            "start": span[0],
            "end": span[1],
            "verdict": verdict,
            "problem_type": problem_type,
            "comment": _text(item.get("comment") or item.get("reason") or item.get("note")),
            "suggestion": _text(item.get("suggestion") or item.get("rewrite")),
            "grounding": {"verdict": check["verdict"],
                          "routed_to": check.get("routed_to"),
                          "reasons": check.get("reasons") or []},
        })

    phrases.sort(key=lambda p: p["start"])
    if max_chunks:
        for extra in phrases[max_chunks:]:
            dropped.append({"reason": "over the LITE chunk limit",
                            "chunk": extra["chunk"][:160]})
        phrases = phrases[:max_chunks]

    return phrases, dropped


# ---------------------------------------------------------------------------
# Simulated reaction
# ---------------------------------------------------------------------------

def guard_reaction(raw_reaction, sources):
    """(reaction, faults). A reaction with any fault is not published.

    Withholding it is the right failure: the reaction is the one output a
    seller could mistake for intelligence about the real person, so a reaction
    that breaks the rules must not be shown with a warning attached.
    """
    text = _text(raw_reaction)
    if not text:
        return None, ["no reaction returned"]

    faults = []
    lowered = text.lower()

    for name in sources.contact_names():
        if re.search(r"\b%s\b" % re.escape(name.lower()), lowered):
            faults.append("names the contact (%r); a reaction is written in role "
                          "terms" % name)

    hit = _ATTRIBUTION_RE.search(text)
    if hit and _PERSONAL_PRONOUN_RE.search(text):
        faults.append("attributes %r to the individual; the reaction may describe "
                      "how a role would read the message, not what this person "
                      "thinks" % hit.group(0))

    if '"' in text or "“" in text:
        faults.append("contains a quotation; the contact has not said anything")

    # Every factual assertion in the reaction is checked like any other claim.
    unsupported = []
    for sentence in re.split(r"(?<=[.!?])\s+", text):
        if not _NUMBER_RE.search(sentence) and not _URL_RE.search(sentence) \
                and not SUPERLATIVE_RE.search(sentence) \
                and not COMPETITOR_RE.search(sentence):
            continue
        check = sources.verify_claim(sentence, "reaction")
        if check["verdict"] in (VERDICT_UNSUPPORTED, VERDICT_RESTRICTED):
            unsupported.append(check)
    if unsupported:
        faults.append("carries %d unsupported assertion(s): %s"
                      % (len(unsupported),
                         "; ".join(r for c in unsupported for r in c["reasons"])[:300]))

    if faults:
        logger.warning("evaluator: reaction withheld - %s", "; ".join(faults))
        return None, faults

    return {"text": text, "is_simulation": True, "label": SIMULATION_LABEL,
            "framing": "role", "persona_title": sources.persona.get("title")}, []


# ---------------------------------------------------------------------------
# Rewrite diff
# ---------------------------------------------------------------------------

def _claims_in(text):
    """The checkable assertions in a piece of text."""
    out = set()
    out.update(_NUMBER_RE.findall(text or ""))
    out.update(_URL_RE.findall(text or ""))
    return out


def diff_rewrite(original, rewritten, sources, selected=None):
    """(report, faults). What the rewrite added, removed, and whether it may.

    Two failure modes matter and they pull in opposite directions: a rewrite
    that quietly drops a fact the seller needed, and a rewrite that invents one.
    """
    original = str(original or "")
    rewritten = str(rewritten or "")
    faults = []

    before, after = _claims_in(original), _claims_in(rewritten)
    dropped = sorted(before - after)
    added = sorted(after - before)

    # A new figure or link must be answerable by the source with authority.
    new_claims = []
    for sentence in re.split(r"(?<=[.!?])\s+", rewritten):
        if not any(token in sentence for token in added):
            continue
        check = sources.verify_claim(sentence, "rewrite")
        new_claims.append(check)
        if check["verdict"] in (VERDICT_UNSUPPORTED, VERDICT_RESTRICTED):
            faults.append("the rewrite introduces an unsupported claim: %s"
                          % "; ".join(check["reasons"]))

    # A restriction the original respected must not be broken by the rewrite.
    if sources.superlatives_blocked:
        new_super = [m.group(0) for m in SUPERLATIVE_RE.finditer(rewritten)
                     if not SUPERLATIVE_RE.search(original)]
        if new_super:
            faults.append("the rewrite adds a superlative claim (%s) not permitted "
                          "in %s" % (new_super[0], sources.country.title()))
    if sources.competitor_claims_blocked:
        new_comp = [m.group(0) for m in COMPETITOR_RE.finditer(rewritten)
                    if not COMPETITOR_RE.search(original)]
        if new_comp:
            faults.append("the rewrite names a competitor (%s), a comparison claim "
                          "not permitted in %s" % (new_comp[0], sources.country.title()))

    report = {
        "facts_dropped": dropped,
        "facts_added": added,
        "new_claim_checks": new_claims,
        "applied_recommendations": list(selected or []),
        "length_before": len(original),
        "length_after": len(rewritten),
    }
    # Dropping a figure is reported, not blocked - a rewrite that removes an
    # unsupported number is doing the right thing, and the seller can see which
    # ones went.
    return report, faults
