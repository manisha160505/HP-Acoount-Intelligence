"""The checks the code enforces, as opposed to the rules the model is asked to follow.

Spec Section 6, HP 220 - Content Studio & Message Evaluator - Build
Specification v1.0. Its framing is the whole point of this module:

    The prompt rules are instructions the model may follow. These are checks
    the code enforces.

Fourteen gates, G1 to G14. They run on every Content Studio generation, every
Message Evaluator rewrite output, and every 1-Pager before export.

**Nothing here raises.** Each gate returns audit rows, and the caller decides.
That is deliberate: the specification assigns each gate its own consequence -
some regenerate once and then reject, some reject outright - and a gate that
raised would collapse that distinction into one. `ACTION_REJECT` and
`ACTION_REGENERATE` carry it instead.

**An empty result is a pass.** A non-empty result lists specific rows to fix,
in the shape the six audit CSVs want (`audit_rows`).

What is reused rather than rebuilt: `grounding.Corpus.unsourced_numbers` for
G1, which is the same check the extractors already run, so a figure accepted
by one feature cannot be rejected by another; and `buyer_personas` for the
eligibility matrix and the committee angles.
"""

import re

from app.services.extractors.grounding import HP_PRODUCT_LINES
from app.services.hp import buyer_personas as bp

# Every HP line the platform recognises. G5 and G6 need "is any HP line named
# in this prose", which is the canonical enum rather than one persona's slice
# of it - a line denied to this persona is G4's business, not theirs.
ALL_HP_LINES = tuple(HP_PRODUCT_LINES)

# Which audit file a finding belongs in. Spec Section 6 names six.
AUDIT_UNSOURCED_NUMBERS = "audit_unsourced_numbers.csv"
AUDIT_LINE_ELIGIBILITY = "audit_line_eligibility.csv"
AUDIT_ASK_BOUND = "audit_ask_bound.csv"
AUDIT_NAME_LEAK = "audit_name_leak.csv"
AUDIT_BANNED_PHRASES = "audit_banned_phrases.csv"
AUDIT_EVIDENCE_LABELS = "audit_evidence_labels.csv"
AUDIT_OTHER = "audit_other.csv"

# What the caller does with a finding.
#
# REGENERATE means try once more with the fault fed back; if the second attempt
# fails the same gate, it becomes a rejection. REJECT means do not publish and
# do not retry - the specification reserves it for the faults where a second
# attempt is not the answer.
ACTION_REGENERATE = "regenerate"
ACTION_REJECT = "reject"


def _finding(gate, action, audit, **columns) -> dict:
    return {"gate": gate, "action": action, "audit": audit, **columns}


# ---------------------------------------------------------------------------
# Reading an asset
# ---------------------------------------------------------------------------
#
# Written against a normalised view rather than one content contract, so the
# same gates serve the current asset shape, the new 1-Pager contract and a
# rewritten Evaluator message without three copies of the traversal.

_TEXT_KEYS = ("subject_line", "title", "subtitle", "headline", "opening",
              "why_now", "body", "cta", "ask", "hp_play", "proof_point",
              "persona_framing")


def asset_texts(asset: dict) -> list:
    """Every piece of prose a reader will see, in reading order.

    `evidence_used` and `hp_products` are excluded: they are machine fields,
    and a label like `A1` counted as prose would fail the unsourced-number
    gate on its own digit.
    """
    asset = asset or {}
    out = [str(asset.get(key) or "") for key in _TEXT_KEYS]
    for section in asset.get("body_sections") or []:
        if isinstance(section, dict):
            out.append(str(section.get("heading") or ""))
            out.append(str(section.get("text") or ""))
        else:
            out.append(str(section or ""))
    for pillar in asset.get("pillars") or []:
        if isinstance(pillar, dict):
            out += [str(pillar.get(k) or "")
                    for k in ("heading", "challenge", "hp_response")]
    return [t for t in out if t.strip()]


# An evidence label as the prompt issues them: one capital letter and one or
# two digits, in square brackets. `[A1]`, `[P12]`, runs like `[A1, A2]` and
# adjacent pairs like `[P1][P4]`.
#
# Deliberately NOT `\[[^\]]+\]`. A seller-facing email opens "Dear [VP Name],"
# - a placeholder they fill in - and a loose pattern would leave "Dear ,".
# Eating the placeholder would be a worse bug than the one this fixes, so the
# shape is anchored and `test_content_labels.py` pins the placeholder.
#
# Named for the bracketed TAG, not the label. `_LABEL_RE` further down belongs
# to G2 and matches a bare "A1" in an `evidence_used` list - a different thing.
# The first version of this was also called `_LABEL_RE`, so the later
# definition won at module level and stripping left the brackets behind: the
# body read "[]" instead of nothing.
_EVIDENCE_TAG_RE = re.compile(r"\[\s*[A-Z]\d{1,2}(?:\s*,\s*[A-Z]\d{1,2})*\s*\]")
# What the removal leaves behind: a doubled space, or a space pushed up against
# the punctuation that followed the tag.
_TAG_GAP_RE = re.compile(r"[ \t]{2,}")
_TAG_PUNCT_RE = re.compile(r"\s+([,.;:!?])")


def strip_evidence_tags(text) -> str:
    """`text` with bracketed evidence tags removed and the gap closed."""
    out = _EVIDENCE_TAG_RE.sub("", str(text or ""))
    out = _TAG_PUNCT_RE.sub(r"\1", out)
    out = _TAG_GAP_RE.sub(" ", out)
    return out.strip()


def strip_evidence_labels(asset: dict) -> dict:
    """Every prose field of `asset`, with evidence labels removed. In place.

    The writing counterpart to `asset_texts`, over the SAME `_TEXT_KEYS` plus
    the same `body_sections` and `pillars` walk - so a prose field added to
    one is covered by the other, and they cannot drift apart.

    `evidence_used` (top level and per pillar), `evidence_labels` and
    `hp_products` are untouched: they are the machine fields that make the
    Evidence section, which the client explicitly wants kept.
    """
    asset = asset or {}
    for key in _TEXT_KEYS:
        if asset.get(key) is not None:
            asset[key] = strip_evidence_tags(asset[key])
    sections = asset.get("body_sections")
    if isinstance(sections, list):
        for i, section in enumerate(sections):
            if isinstance(section, dict):
                for k in ("heading", "text"):
                    if section.get(k) is not None:
                        section[k] = strip_evidence_tags(section[k])
            else:
                sections[i] = strip_evidence_tags(section)
    for pillar in asset.get("pillars") or []:
        if isinstance(pillar, dict):
            for k in ("heading", "challenge", "hp_response"):
                if pillar.get(k) is not None:
                    pillar[k] = strip_evidence_tags(pillar[k])
    return asset


def asset_blob(asset: dict) -> str:
    return "\n".join(asset_texts(asset))


def asset_word_count(asset: dict) -> int:
    """The words a reader sees.

    Not `len(asset_blob(...).split())`. A projected 1-Pager carries its
    structure and the rendering of that structure at once - `why_now` is also
    the `opening`, each pillar is also a body section, `hp_play` is also a
    section - because the structure is what the gates and the PDF export need
    and the envelope is what every renderer reads. Walking both and adding up
    counted a 185-word brief as 325 and put every 1-Pager over budget.

    So the count is taken over the RENDERED document, which is what the budget
    is about: the specification sets 350-500 words because "that is what fits
    on one page at readable body size". Where no projection exists - a bare
    structured asset, an Evaluator rewrite that returned `body` and `ask` - the
    structured keys are counted instead.

    The subject line and `persona_framing` are excluded. The specification
    counts the email budget "across opening + body + ask", and the framing is
    an internal note that is never sent.
    """
    asset = asset or {}
    parts = [str(asset.get(key) or "") for key in ("title", "headline", "subtitle")]
    parts.append(str(asset.get("opening") or asset.get("why_now") or ""))
    parts.append(str(asset.get("body") or ""))
    parts.append(str(asset.get("cta") or asset.get("ask") or ""))
    sections = asset.get("body_sections") or []
    if sections:
        for section in sections:
            if isinstance(section, dict):
                parts += [str(section.get("heading") or ""), str(section.get("text") or "")]
            else:
                parts.append(str(section or ""))
    else:
        for pillar in asset.get("pillars") or []:
            if isinstance(pillar, dict):
                parts += [str(pillar.get(key) or "")
                          for key in ("heading", "challenge", "hp_response")]
        parts += [str(asset.get("hp_play") or ""), str(asset.get("proof_point") or "")]
    return len(" ".join(p for p in parts if p.strip()).split())


_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+")


def _sentences(text: str) -> list:
    return [s.strip() for s in _SENTENCE_RE.split(str(text or "")) if s.strip()]


def _sentence_with(text: str, needle: str) -> str:
    """The sentence a finding sits in, so an audit row can be acted on."""
    low = str(needle or "").lower()
    for sentence in _sentences(text):
        if low and low in sentence.lower():
            return sentence[:300]
    return str(text or "")[:300]


# ---------------------------------------------------------------------------
# G1 - unsourced number
# ---------------------------------------------------------------------------

def g1_unsourced_numbers(asset: dict, corpus) -> list:
    """Every digit-bearing token must appear in the evidence.

    Delegated to the same `Corpus` the extractors use, so a figure that is
    sourced for one feature cannot be unsourced for another. A corpus is
    required: calling this without one would pass everything silently, which
    is worse than not running it.
    """
    if corpus is None:
        return [_finding("G1", ACTION_REJECT, AUDIT_UNSOURCED_NUMBERS,
                         offending_token="", sentence="",
                         detail="no evidence corpus supplied - cannot check figures")]
    out = []
    for text in asset_texts(asset):
        for token in corpus.unsourced_numbers(text):
            out.append(_finding("G1", ACTION_REGENERATE, AUDIT_UNSOURCED_NUMBERS,
                                offending_token=token,
                                sentence=_sentence_with(text, token)))
    return out


# ---------------------------------------------------------------------------
# G2 / G3 - evidence labels
# ---------------------------------------------------------------------------

_LABEL_RE = re.compile(r"\b([AP]\d{1,2})\b")


def g2_evidence_labels_valid(asset: dict, supplied_labels, dropped_labels=()) -> list:
    """Every label cited must be one the prompt actually supplied.

    Covers `pillars[].evidence_used` as well as the top-level list - the
    1-Pager cites per pillar, and a pillar citing a label that does not exist
    is the same fault one level down.

    `dropped_labels` is what makes this gate able to fire at all. The caller
    strips an unsupplied label before anything is published, so by the time the
    suite sees the asset its citations are valid by construction. The stripped
    ones are passed in as (where_found, label) pairs, so the audit row names
    the label the model invented instead of being permanently empty.
    """
    supplied = {str(label).strip() for label in (supplied_labels or [])}
    out = []
    for where, labels in _cited_labels(asset):
        for label in labels:
            if label not in supplied:
                out.append(_finding("G2", ACTION_REJECT, AUDIT_EVIDENCE_LABELS,
                                    invalid_label=label, where_found=where))
    for where, label in (dropped_labels or ()):
        out.append(_finding("G2", ACTION_REJECT, AUDIT_EVIDENCE_LABELS,
                            invalid_label=str(label), where_found=str(where)))
    return out


def _cited_labels(asset: dict) -> list:
    asset = asset or {}
    pairs = [("evidence_used", [str(x).strip()
                                for x in (asset.get("evidence_used") or [])])]
    for index, pillar in enumerate(asset.get("pillars") or []):
        if isinstance(pillar, dict):
            pairs.append(("pillars[%d].evidence_used" % index,
                          [str(x).strip() for x in (pillar.get("evidence_used") or [])]))
    return pairs


def g3_evidence_coverage(asset: dict, label_texts: dict) -> list:
    """`evidence_used` is non-empty, and the opening traces to a cited label.

    "Traces to" is checked as shared vocabulary rather than as a quotation:
    Rule 6 asks the opening to name an evidence item *by its content, not by
    its label*, so requiring the label string itself would reward the one
    behaviour the rule forbids.
    """
    asset = asset or {}
    cited = [str(x).strip() for x in (asset.get("evidence_used") or [])]
    if not cited:
        return [_finding("G3", ACTION_REGENERATE, AUDIT_EVIDENCE_LABELS,
                         invalid_label="", where_found="evidence_used",
                         detail="evidence_used is empty")]

    opening = str(asset.get("opening") or asset.get("why_now") or "")
    if not opening.strip():
        return []
    opening_words = _content_words(opening)
    for label in cited:
        if opening_words & _content_words(str((label_texts or {}).get(label) or "")):
            return []
    return [_finding("G3", ACTION_REGENERATE, AUDIT_EVIDENCE_LABELS,
                     invalid_label=", ".join(cited), where_found="opening",
                     detail="the opening shares no content with any cited label")]


_WORD_RE = re.compile(r"[A-Za-z][A-Za-z'-]{3,}")
_STOPWORDS = frozenset({
    "this", "that", "with", "from", "have", "your", "their", "they", "which",
    "will", "would", "could", "should", "been", "were", "into", "over", "about",
    "there", "these", "those", "than", "then", "when", "where", "what",
})


def _content_words(text: str) -> set:
    return {w.lower() for w in _WORD_RE.findall(str(text or ""))
            if w.lower() not in _STOPWORDS}


# ---------------------------------------------------------------------------
# G4 / G5 - the HP line
# ---------------------------------------------------------------------------

def g4_line_eligibility(asset: dict, persona_id: str) -> list:
    """No line from this persona's DENIED set, anywhere - including in prose.

    Spec Section 6: "Reject - no silent pass." This is the gate with no
    regeneration allowance, and the one the specification says to check first
    in review, because it is the failure that costs seller trust.

    Prose is checked as well as `hp_products` because the damage is done by
    the sentence a seller reads, not by the machine field beside it.
    """
    denied = bp.denied_lines(persona_id)
    blob = asset_blob(asset).lower()
    named = [str(p).strip() for p in (asset or {}).get("hp_products") or []]
    out = []
    for line in denied:
        where = ""
        if any(line.lower() == n.lower() for n in named):
            where = "hp_products"
        elif line.lower() in blob:
            where = "prose"
        if where:
            out.append(_finding("G4", ACTION_REJECT, AUDIT_LINE_ELIGIBILITY,
                                denied_line_named=line, where_found=where,
                                sentence=_sentence_with(asset_blob(asset), line)))
    return out


def g5_one_line_maximum(asset: dict) -> list:
    """`hp_products` holds 0 or 1 entry, and no second line is named in prose.

    An empty array stays a correct answer - Rule 4's discovery-led piece is
    what an account with no earned chain should produce.
    """
    named = [str(p).strip() for p in (asset or {}).get("hp_products") or [] if str(p).strip()]
    out = []
    if len(named) > 1:
        out.append(_finding("G5", ACTION_REGENERATE, AUDIT_LINE_ELIGIBILITY,
                            denied_line_named=", ".join(named),
                            where_found="hp_products",
                            detail="names %d HP lines; at most one" % len(named)))

    blob = asset_blob(asset).lower()
    in_prose = {line for line in ALL_HP_LINES if line.lower() in blob}
    # The line the asset declares is not a second mention of itself.
    extra = sorted(in_prose - set(named))
    if named and extra:
        out.append(_finding("G5", ACTION_REGENERATE, AUDIT_LINE_ELIGIBILITY,
                            denied_line_named=", ".join(extra),
                            where_found="prose",
                            detail="a second HP line appears in the copy"))
    return out


# ---------------------------------------------------------------------------
# G6 - the ask is bounded by the committee angle
# ---------------------------------------------------------------------------

_DECISION_TERMS = ("decide", "decision", "sign off", "sign-off", "approve",
                   "approval", "commit to", "commitment", "place an order",
                   "purchase order", "choose hp", "select hp", "go ahead",
                   "move forward with hp")
_COMMERCIAL_TERMS = ("price", "pricing", "quote", "quotation", "discount",
                     "rate card", "contract terms", "per seat cost",
                     "cost per seat")
_MONEY_RE = re.compile(r"(?:[$€£¥]|\b(?:usd|eur|gbp|jpy|idr|sgd|myr|thb|php|vnd|aud|krw)\b)",
                       re.I)


def g6_ask_bound(asset: dict, persona_id: str) -> list:
    """The closing ask must stay inside the persona's committee angle.

    Spec Section 2.2. An ask outside the angle is a failed output even when
    everything else is correct - a Gatekeeper asked to choose a vendor, a
    Finance owner quoted a price.
    """
    ask = str((asset or {}).get("ask") or (asset or {}).get("cta") or "")
    if not ask.strip():
        return []
    angle = bp.angle(persona_id)
    low = ask.lower()
    out = []

    def fault(violation):
        out.append(_finding("G6", ACTION_REGENERATE, AUDIT_ASK_BOUND,
                            committee_angle=angle, ask_text=ask[:300],
                            violation_type=violation))

    if angle == bp.ANGLE_GATEKEEPER:
        for line in ALL_HP_LINES:
            if line.lower() in low:
                fault("names an HP product to a Gatekeeper (%s)" % line)
                break
        if any(term in low for term in ("choose", "select", "pick")):
            fault("asks a Gatekeeper to choose a vendor")
    elif angle == bp.ANGLE_FINANCE:
        if _MONEY_RE.search(ask):
            fault("quotes a currency figure to a Finance - Budget Owner")
        for term in _COMMERCIAL_TERMS:
            if term in low:
                fault("names a commercial term (%s) to a Finance - Budget Owner"
                      % term)
                break
    elif angle == bp.ANGLE_TECHNICAL:
        for term in _DECISION_TERMS:
            if term in low:
                fault("asks a Technical Buyer for a decision (%s)" % term)
                break
        for term in _COMMERCIAL_TERMS:
            if term in low:
                fault("names a commercial term (%s) to a Technical Buyer" % term)
                break
    return out


# ---------------------------------------------------------------------------
# G7 - person-name leak on an unfilled persona
# ---------------------------------------------------------------------------

def g7_name_leak(asset: dict, filled: bool, known_names) -> list:
    """On an UNFILLED persona, no personal name and no greeting by name.

    The specification expects UNFILLED to be the normal path - 220 accounts by
    eight personas against three contacts each - so this gate runs constantly
    and has to be right rather than cautious.
    """
    if filled:
        return []
    blob = asset_blob(asset)
    low = blob.lower()
    out = []
    for name in (known_names or []):
        cleaned = str(name or "").strip()
        if cleaned and cleaned.lower() in low:
            out.append(_finding("G7", ACTION_REJECT, AUDIT_NAME_LEAK,
                                leaked_name=cleaned,
                                sentence=_sentence_with(blob, cleaned)))
    for greeting in _GREETING_RE.findall(blob):
        out.append(_finding("G7", ACTION_REJECT, AUDIT_NAME_LEAK,
                            leaked_name=greeting.strip(),
                            sentence=_sentence_with(blob, greeting)))
    return out


# "Hi Robert," / "Dear Ms Tan," - a greeting followed by a capitalised name.
# Role greetings ("Dear CIO,") are not a leak and must not match, so the name
# must not be an all-caps acronym.
# The case-insensitivity is scoped to the greeting word and the exclusions
# ONLY. The captured name keeps `[A-Z][a-z]+`, because that is what separates
# a person from a role: "Dear CIO," is an acronym and is exactly what an
# unfilled persona is supposed to write, whereas a blanket re.I would match it
# and reject the correct output.
_GREETING_RE = re.compile(
    r"\b(?i:hi|hello|dear|hey)\s+(?!(?i:there|team|all|sir|madam)\b)"
    r"((?:[A-Z][a-z]+)(?:\s+[A-Z][a-z]+)?)\s*[,.]")


# ---------------------------------------------------------------------------
# G8 - competitor handling
# ---------------------------------------------------------------------------

_OUR_COMPETITOR_RE_CACHE = {}


def g8_competitors(asset: dict, competitors) -> list:
    """No competitor is called HP's own, and none is disparaged.

    The "our <competitor>" half is the one the existing validator already
    catches. The disparagement half is new and is kept to explicit, checkable
    wording rather than sentiment.
    """
    blob = asset_blob(asset)
    low = blob.lower()
    out = []
    for name in (competitors or []):
        vendor = str(name or "").strip().lower()
        if not vendor:
            continue
        if re.search(r"\bour\s+%s\b" % re.escape(vendor), low):
            out.append(_finding("G8", ACTION_REJECT, AUDIT_OTHER,
                                detail='refers to %s as "our" product' % vendor,
                                sentence=_sentence_with(blob, vendor)))
        for slur in _DISPARAGEMENT:
            if re.search(r"\b%s\b[^.]{0,60}\b%s\b" % (re.escape(vendor), slur), low):
                out.append(_finding("G8", ACTION_REJECT, AUDIT_OTHER,
                                    detail="disparages %s (%s)" % (vendor, slur),
                                    sentence=_sentence_with(blob, vendor)))
                break
    return out


_DISPARAGEMENT = ("inferior", "outdated", "obsolete", "unreliable", "insecure",
                  "failing", "poor", "weak", "inadequate", "legacy and risky")


# ---------------------------------------------------------------------------
# G9 - banned phrases
# ---------------------------------------------------------------------------
#
# The specification's seed list, plus the phrases the existing validator
# already carried. "Seed list, extend from review" - so it is one list in one
# place rather than two that drift.

BANNED_PHRASES = (
    # Spec Section 6 seed list
    "industry-leading", "best-in-class", "world-class", "cutting-edge",
    "state-of-the-art", "unlock value", "drive efficiencies",
    "uncover opportunities", "as threats evolve", "in today's fast-paced",
    "digital transformation journey", "seamlessly integrate",
    "i hope this finds you well", "i hope you're doing well",
    "i wanted to reach out", "game-changer", "revolutionary",
    "robust and scalable", "empower your teams",
    # Carried from the existing Content Studio validator
    "i hope this email finds you", "best possible experience", "game-changing",
    "synerg", "stay ahead of the curve",
)


def g9_banned_phrases(asset: dict) -> list:
    """Banned phrases, any exclamation mark, the concessive template, and a
    deadline written as though it had not happened."""
    blob = asset_blob(asset)
    low = blob.lower()
    out = []
    for phrase in BANNED_PHRASES:
        if phrase in low:
            out.append(_finding("G9", ACTION_REGENERATE, AUDIT_BANNED_PHRASES,
                                phrase=phrase, sentence=_sentence_with(blob, phrase)))
    for sentence in _sentences(blob):
        if _PAST_DEADLINE_RE.search(sentence):
            out.append(_finding("G9", ACTION_REGENERATE, AUDIT_BANNED_PHRASES,
                                phrase="urgency built on a deadline that has passed",
                                sentence=sentence[:300]))
    if "!" in blob:
        out.append(_finding("G9", ACTION_REGENERATE, AUDIT_BANNED_PHRASES,
                            phrase="!", sentence=_sentence_with(blob, "!")))
    for sentence in _sentences(blob):
        if _CONCESSIVE_RE.search(sentence):
            out.append(_finding("G9", ACTION_REGENERATE, AUDIT_BANNED_PHRASES,
                                phrase="<praise> ... However, <vague upside>",
                                sentence=sentence[:300]))
    return out


# Rule 8's concessive template: a clause, then "However"/"That said", then a
# vague upside. Matched on the pivot rather than on the praise, because the
# praise is what varies.
_CONCESSIVE_RE = re.compile(
    r",\s*(?:however|that said|nevertheless)\s*,", re.I)


# Acceptance test T8. Windows 10 support ended in October 2025, so a sentence
# that puts the deadline in front of the reader is selling against a date that
# has gone - the single most common way this copy loses a device-lifecycle or
# procurement audience, because they lived through it.
#
# Matched on the forward-looking preposition rather than on the date, so it
# catches "before the deadline" and "ahead of end of support" without flagging
# the legitimate sentence that says the date has passed. Naming the estate that
# is STILL on Windows 10 is fine and is not this pattern.
_PAST_DEADLINE_RE = re.compile(
    r"\b(?:before|ahead of|in advance of|prior to|by)\b[^.]{0,60}?"
    r"(?:windows\s*10[^.]{0,30}?(?:deadline|end[\s-]of[\s-](?:support|life)|cut[\s-]?off)"
    r"|(?:deadline|end[\s-]of[\s-](?:support|life))[^.]{0,30}?windows\s*10)",
    re.I)


# ---------------------------------------------------------------------------
# G10 - industry is not justification
# ---------------------------------------------------------------------------

_CAUSAL = (r"because", r"since", r"given", r"as a", r"as an", r"being a",
           r"being an", r"operating in", r"in the")
_NEED_WORDS = ("need", "needs", "require", "requires", "must", "demand",
               "demands", "rely", "relies", "critical", "essential")


def g10_industry_as_justification(asset: dict, industry: str) -> list:
    """No sentence uses an industry or sector name as the reason for a need.

    Rule 2b, made mechanical. Checked as a co-occurrence inside one sentence -
    a causal connective, the account's own industry (or a bare "industry" /
    "sector"), and a need word - because the failure is a sentence shape
    rather than a phrase: "Because you operate in <industry>, your systems
    must be reliable" is a failed sentence whatever the industry is.
    """
    terms = [t for t in (str(industry or "").lower().split(" / ")) if t.strip()]
    terms += ["industry", "sector"]
    out = []
    for sentence in _sentences(asset_blob(asset)):
        low = sentence.lower()
        if not any(term in low for term in terms):
            continue
        if not any(re.search(r"\b%s\b" % c, low) for c in _CAUSAL):
            continue
        if not any(re.search(r"\b%s\b" % w, low) for w in _NEED_WORDS):
            continue
        out.append(_finding("G10", ACTION_REGENERATE, AUDIT_OTHER,
                            detail="industry used as the reason for a need",
                            sentence=sentence[:300]))
    return out


# ---------------------------------------------------------------------------
# G11 / G12 / G13 - shape
# ---------------------------------------------------------------------------

def g11_empty_string_fill(asset: dict, required_keys) -> list:
    """An omitted key is correct; an empty one is not.

    Rule 9 makes omission the default, so this gate does not ask whether a key
    is present - it asks whether a present key is hollow.
    """
    out = []
    for key in (required_keys or []):
        if key in (asset or {}) and not str(asset.get(key) or "").strip():
            out.append(_finding("G11", ACTION_REJECT, AUDIT_OTHER,
                                detail="%s is an empty string" % key, sentence=""))
    return out


# Spec Section 6, G12. These are the specification's budgets and they are
# WIDER than the word caps the current content contracts carry (email at most
# 110, LinkedIn Message at most 80, one-pager at most 400). Both cannot be
# right: an email written to the contract would fail this gate on every
# generation. The contracts move to these numbers when Content Studio is
# rewired - until then this table is the authority the specification names.
WORD_BUDGETS = {
    "email": (120, 180),
    "linkedin_message": (60, 110),
    "one_pager": (350, 500),
}


def g12_word_budget(asset: dict, content_type: str) -> list:
    budget = WORD_BUDGETS.get(str(content_type or "").strip())
    if not budget:
        return []
    low, high = budget
    words = asset_word_count(asset)
    if low <= words <= high:
        return []
    return [_finding("G12", ACTION_REGENERATE, AUDIT_OTHER,
                     detail="%s is %d words; the budget is %d-%d"
                            % (content_type, words, low, high),
                     sentence="")]


def g13_pillar_count(asset: dict, content_type: str) -> list:
    """1-Pager only: exactly 2 or 3 pillars, each citing its own evidence.

    The specification is explicit about why the bounds are not 1 and not 4:
    one pillar is an email, four stops being a one-pager. If the evidence
    supports only one, the correct output is an Email.
    """
    if str(content_type or "").strip() != "one_pager":
        return []
    pillars = (asset or {}).get("pillars")
    if pillars is None:
        return []
    out = []
    if not 2 <= len(pillars) <= 3:
        out.append(_finding("G13", ACTION_REGENERATE, AUDIT_OTHER,
                            detail="%d pillars; exactly 2 or 3" % len(pillars),
                            sentence=""))
    for index, pillar in enumerate(pillars):
        cited = (pillar or {}).get("evidence_used") if isinstance(pillar, dict) else None
        if not cited:
            out.append(_finding("G13", ACTION_REGENERATE, AUDIT_OTHER,
                                detail="pillar %d cites no evidence" % index,
                                sentence=""))
    return out


# ---------------------------------------------------------------------------
# G14 - chunk fidelity (Message Evaluator)
# ---------------------------------------------------------------------------

def g14_chunk_fidelity(chunks, stimulus: str) -> list:
    """Concatenated chunks must reconstruct the stimulus exactly.

    A paraphrased chunk cannot be highlighted in the UI and cannot be safely
    rewritten, so this is checked server-side rather than trusted.

    Whitespace is normalised before comparison and only whitespace: the
    specification asks for verbatim, contiguous spans, and normalising
    anything else would let a reworded chunk through on a technicality.
    """
    joined = "".join(str(c or "") for c in (chunks or []))
    if _squash(joined) == _squash(stimulus):
        return []
    return [_finding("G14", ACTION_REGENERATE, AUDIT_OTHER,
                     detail="the phrase chunks do not reconstruct the message "
                            "(%d chars against %d)"
                            % (len(_squash(joined)), len(_squash(stimulus))),
                     sentence="")]


def _squash(text: str) -> str:
    return " ".join(str(text or "").split())


# ---------------------------------------------------------------------------
# Running the suite
# ---------------------------------------------------------------------------

def run(asset: dict, *, persona_id: str, content_type: str,  # noqa: PLR0913 - one keyword per gate input; a context object would hide which gate needs what
        filled: bool, corpus=None, supplied_labels=(), label_texts=None,
        known_names=(), competitors=(), industry="", required_keys=(),
        dropped_labels=()) -> list:
    """Every gate that applies to a generated asset, in gate order.

    G14 is not here: it takes the Evaluator's chunks and its stimulus rather
    than an asset, and is called on its own.
    """
    findings = []
    findings += g1_unsourced_numbers(asset, corpus)
    findings += g2_evidence_labels_valid(asset, supplied_labels, dropped_labels)
    findings += g3_evidence_coverage(asset, label_texts or {})
    findings += g4_line_eligibility(asset, persona_id)
    findings += g5_one_line_maximum(asset)
    findings += g6_ask_bound(asset, persona_id)
    findings += g7_name_leak(asset, filled, known_names)
    findings += g8_competitors(asset, competitors)
    findings += g9_banned_phrases(asset)
    findings += g10_industry_as_justification(asset, industry)
    findings += g11_empty_string_fill(asset, required_keys)
    findings += g12_word_budget(asset, content_type)
    findings += g13_pillar_count(asset, content_type)
    return findings


def rejects(findings) -> list:
    return [f for f in (findings or []) if f["action"] == ACTION_REJECT]


def regenerates(findings) -> list:
    return [f for f in (findings or []) if f["action"] == ACTION_REGENERATE]


def audit_rows(findings, *, account_id: str, persona_id: str,
               content_type: str = "") -> dict:
    """{audit file: [row, ...]} in the shape Section 6 specifies.

    Every row carries the account and the persona, because the review that
    matters happens across a batch of 120 outputs rather than on one.
    """
    grouped = {}
    for finding in (findings or []):
        row = {"account_id": account_id, "persona_id": persona_id,
               "format": content_type, "gate": finding["gate"],
               "action": finding["action"]}
        row.update({k: v for k, v in finding.items()
                    if k not in ("gate", "action", "audit")})
        grouped.setdefault(finding["audit"], []).append(row)
    return grouped
