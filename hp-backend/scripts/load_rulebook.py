"""Load the HP 220 Account Rulebook into Atlas, exactly as written.

    python scripts/load_rulebook.py                 # dry run, prints the parse
    python scripts/load_rulebook.py --apply         # write to hp_rulebook
    python scripts/load_rulebook.py --show 5        # sample 5 rules
    python scripts/load_rulebook.py --no-tokens     # skip the one model call

The rulebook is the client's authority for which HP offering fits which
verified account signal, what may be said about it, and under what conditions.
113 rules: 18 hardware (Part A) and 95 services (Part B), plus the routing
table, two selection matrices, 30 guardrails and 2 country lists.

## Why so little of this is inferred

Guardrail C 03 is "Use exact facts", C 04 is "Keep conditions". A rule's text is
what a seller is allowed to say to a customer under HP's name, so every string
a user will ever see is stored verbatim or split from verbatim text by a rule
written here. Nothing user-facing is paraphrased, summarised or generated.

The single exception is `signal_tokens` - the surface forms used to decide
whether an account's own evidence mentions what a rule is about. Those are
matching aids, never shown, and every one is verified back against the rule's
own signal cell before it is stored. See `_gate_tokens`.

## Why the tables are found by their headers

An earlier draft indexed them by position. The rulebook is a living document -
the client has already sent revisions - and a table inserted anywhere above
would have silently shifted every index, loading Care Pack rules as Wolf
Security rules with no error. Headers are matched instead, and a table whose
header matches nothing is reported rather than skipped quietly.

Shape follows `load_case_studies.py` and `extract_hp_decks.py`: dry run by
default, deterministic `_id`, upsert then prune by `$nin`, and a
`__knowledge_version__` sentinel written last so downstream fingerprints can
tell that a reload happened.
"""

import argparse
import hashlib
import json
import os
import re
import sys
import unicodedata

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from app.services.extractors.content_studio import COMPETITORS
from app.services.extractors.grounding import corpus_from_texts
from app.services.hp.product_rules import GLOBAL_EXCLUDE_PHRASES, RULES

# ==============================================================================
# Where things live
# ==============================================================================

COLLECTION = "hp_rulebook"
VERSION_DOC_ID = "__knowledge_version__"

# Bump when the parse changes shape, so a reload is detectable even when the
# document has not changed.
# 1 - first load: Part A, Part B, routing, matrices, guardrails, country lists.
# 2 - observable terms. Signal tokens alone matched nothing on a real account:
#     the rulebook describes business problems and account exports list vendor
#     names and job titles, and the two share no vocabulary.
# 3 - a prohibition is the negative clause, not the whole sentence containing
#     it. "Keep the two services separate" was being shown as something the
#     engine must not say, which is the opposite of what it means.
# 4 - the negative clause is lifted OUT of the fact it sat in, so a card no
#     longer shows the same sentence under both "What HP says" and "Do not say".
# 5 - the revised FINAL document: a tenth family (INK), print 3 -> 39, scan
#     3 -> 10, six new common guardrails, and the client's own 12-field
#     structured schema. Purely additive: no existing rule changed or was
#     withdrawn, which the tests assert.
EXTRACTOR_VERSION = 5

_HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_DOCX = os.path.abspath(os.path.join(
    _HERE, "..", "..", "additional_data",
    "HP_220_Account_Combined_Product_Services_and_Solutions_Rulebook_FINAL_.docx"))

# ==============================================================================
# Recognising the tables
# ==============================================================================
#
# Each entry is (kind, required header cells). A table matches when every
# required cell appears in its header row. Ordered most specific first: Part A
# and Part B share three header cells, so Part A's extra columns must be tested
# before the generic rule shape claims it.
TABLE_SIGNATURES = (
    ("part_a", ("rule", "hp material used", "hp facts available to the engine")),
    ("part_b", ("rule", "verified account signal", "hp offering to consider")),
    ("routing", ("opportunity type", "go to these rules")),
    ("matrix_wolf", ("offering", "segment in source")),
    ("matrix_iq", ("category", "compatibility and conditions")),
    ("guardrail_common", ("id", "area", "rule")),
    ("guardrail_service", ("id", "area", "simple rule")),
    ("guardrail_product", ("guardrail", "exact implementation rule")),
    ("country_list", ("restriction type",)),
    ("schema", ("structured field", "required content")),
    ("source", ("source", "use in this document")),
    ("structure", ("part", "use")),
)

# Part B rule labels open with their family. Closed set: a label that does not
# start with one of these is reported rather than filed under a guessed family.
# SCAN is here because the "Print and scan solution rules" table carries both
# PRINT 01-03 and SCAN 01-03. Reading the section heading rather than the rule
# labels would have filed three scan rules under print and lost them.
PART_B_FAMILIES = ("WXP", "CARE", "LIFE", "DEPLOY", "POLY",
                   "PRINT", "SCAN", "INK", "IQ", "WOLF")

# Routing type -> the Part B family it sends the engine to. The document says
# this in prose ("Go to these rules" = "WXP rules"), so it is read from that
# cell and checked against this map rather than trusted either way alone.
ROUTING_TO_FAMILIES = {
    "workforce experience": ("WXP",),
    "security": ("WOLF",),
    "support and care pack": ("CARE",),
    "lifecycle and sustainability": ("LIFE",),
    "deployment and configuration": ("DEPLOY",),
    "poly support": ("POLY",),
    # One routing type, two families - the rules table holds PRINT and SCAN
    # side by side and a scan requirement must reach the scan rules.
    # INK joins print: the revision added six ink rules but did not extend the
    # eight-row routing table, and ink sits in the document's print section
    # sharing its sources. Inventing a ninth routing type would be putting
    # words in the client's table.
    "print and scan": ("PRINT", "SCAN", "INK"),
    "enterprise ai": ("IQ",),
}

# The HP material each block of rules was written from, keyed on the section
# heading that introduces it. Taken from the document's own provenance table and
# the revision's new source bullets - not inferred.
#
# `confidential` marks a source the document restricts. C 16: "Original HP Ink
# Portfolio is HP Confidential / Internal-Channel Partner use only."
SECTION_TO_SOURCE = {
    "part a hardware product rules": {
        "source": "HP product decks, per rule (see material)"},
    "workforce experience platform and roi rules": {
        "source": "HP WXP and DEX ROI Calculator pages"},
    "care pack and fleet support rules": {
        "source": "HP Care Pack Services Definitions, February 2026 Revision 4"},
    "lifecycle and sustainability rules": {
        "source": "HP Q426 Services and Solutions final workbook"},
    "deployment configuration and factory service rules": {
        "source": "HP Q426 Services and Solutions final workbook"},
    "poly support rules": {
        "source": "HP Q426 Services and Solutions final workbook"},
    "print and scan solution rules": {
        "source": "HP Q426 Services and Solutions final workbook"},
    "expanded managed print, workflow, and scanner rules": {
        "source": "HP Managed Print Portfolio (2025/2026); HP Document and "
                  "Workflow Solutions, 4AA5-4773ENW, February 2023 Rev. 9"},
    "original hp ink portfolio rules": {
        "source": "Original HP Ink Portfolio, c09010935, April 2026, Rev. 1",
        "confidential": True},
    "hp iq for enterprise rules": {
        "source": "HP IQ for Enterprise Version 1.0 content and use-case slides"},
    "hp wolf security rules": {
        "source": "HP Wolf Security Portfolio, February 2026"},
}


# ==============================================================================
# Text
# ==============================================================================

_WS_RE = re.compile(r"\s+")
_SENTENCE_RE = re.compile(r"(?<=[.;])\s+(?=[A-Z(])")


def _text(value) -> str:
    """Whitespace-normalised, with the document's typography left intact."""
    return _WS_RE.sub(" ", str(value or "")).strip()


def _slug(value) -> str:
    out = re.sub(r"[^a-z0-9]+", "-", _text(value).lower()).strip("-")
    return out or "unnamed"


def _fold(value) -> str:
    """Lowercased and accent-stripped, for comparison only.

    The rulebook writes "Reunion (France)" and "Cote d'Ivoire" with accents and
    the codebase's country constants are ASCII, so a comparison that does not
    fold them silently fails to match.
    """
    # Curly quotes fold to straight ones first: the document writes
    # "Cote d’Ivoire" and the codebase's constants "cote d'ivoire", which
    # compare as different countries otherwise.
    flat = _text(value).lower().replace("’", "'").replace("‘", "'")
    decomposed = unicodedata.normalize("NFKD", flat)
    return "".join(c for c in decomposed if not unicodedata.combining(c))


def _sentences(value) -> list:
    """Sentences of a cell, kept verbatim.

    Split on a full stop or semicolon followed by a capital or an opening
    bracket. HP writes "EliteBook 8 G2i/G2a" and "up to 50 TOPS", so a naive
    split on every period would cut model names and figures apart.
    """
    text = _text(value)
    if not text:
        return []
    return [s.strip() for s in _SENTENCE_RE.split(text) if s.strip()]


# ==============================================================================
# Deterministic derivation - everything a user will ever see
# ==============================================================================

# What the engine must not say.
#
# Only a sentence that OPENS with a negative imperative is wholly a
# prohibition. An earlier version matched "do not" anywhere in the sentence and
# "keep ... separate", which inverted two rules on screen: "Keep the two
# services separate" and "Treat WXP Collaboration as a separate licence; do not
# present it as included in every WXP licence" are both instructions to DO
# something, and showing them under "Do not say" told a seller the opposite of
# what HP wrote.
#
# Where a positive sentence carries a negative clause, only that clause is the
# prohibition; the sentence itself stays a fact. So "Treat it as a separate
# licence" survives as guidance and "do not present it as included in every WXP
# licence" is what appears under the warning.
_PROHIBITION_RE = re.compile(
    r"^(do not|don't|never|avoid)\b", re.I)
_PROHIBITION_CLAUSE_RE = re.compile(
    r"(?:^|[;,]\s*|\.\s+)((?:do not|don't|never|avoid)\b[^;,.]{3,})", re.I)

# A sentence that constrains when a fact may be used at all.
_CONDITION_RE = re.compile(
    r"\b(only|requires?|required|must|where supported|where available|subject to|"
    r"depends on|provided that|if the|when the|not available|limited to|"
    r"eligible|supported)\b", re.I)

# What kind of condition it is. Ordered: the first match wins, so the more
# specific patterns come first. The first five types are testable against an
# account's own uploaded evidence; the rest are not, and are labelled instead.
#
# `unclassified` is the default and is deliberately NOT testable. A condition
# nobody taught this loader to read must surface on the card as unverified
# rather than quietly pass, which is the half of C 07 that is easy to lose.
CONDITION_TYPES = (
    ("country", (r"\bunited states\b", r"\bu\.s\.\b|\bus\b", r"\benglish\b",
                 r"\bcountry\b", r"\bmarket\b", r"\bregion\b", r"\blocation\b",
                 r"not available (in|everywhere)", r"\blaunch\b")),
    ("management_environment", (r"\bintune\b", r"\bentra\b", r"\bautopilot\b",
                                r"\bsccm\b", r"\bcloud (portal|management)\b",
                                r"\bon-premises\b", r"\btenancy\b",
                                r"\bmanagement (model|console)\b",
                                r"\bauthorization\b|\bauthorisation\b")),
    ("hardware", (r"\bnpu\b", r"\bvpro\b", r"\btops\b", r"\bram\b", r"\bmemory\b",
                  r"\bprocessor\b", r"\bgb\b", r"\bfirmware\b", r"\bbios\b",
                  r"\beligible hp\b", r"\bhp commercial pcs?\b")),
    ("device_family", (r"\belitebook\b", r"\bprobook\b", r"\bzbook\b",
                       r"\belitedesk\b", r"\bprodesk\b", r"\belitestudio\b",
                       r"\bprostudio\b", r"\bz workstation\b", r"\bpoly\b",
                       r"\bnotebook\b", r"\bdesktop\b", r"\bworkstation\b")),
    ("os", (r"\bwindows\b", r"\bmacos\b", r"\blinux\b", r"\bandroid\b",
            r"\bios\b", r"\boperating[- ]system\b")),
    ("licence_term", (r"\blicen[cs]e\b", r"\bsubscription\b", r"\bperpetual\b",
                      r"\bterm\b", r"\brenewal\b", r"\b\d+[- ]year\b")),
    ("seat_band", (r"\bseats?\b", r"\bband\b", r"\bminimum\b", r"\bvolume\b",
                   r"\bper user\b")),
    ("warranty", (r"\bwarranty\b", r"\bcare pack\b", r"\bcoverage\b",
                  r"\bresponse\b", r"\bregistration\b", r"\bentitlement\b")),
    ("commercial", (r"\bprice\b", r"\bcost\b", r"\bquote\b", r"\bsku\b",
                    r"\border\b", r"\bavailabilit(y|ies)\b")),
)

# Only the condition types that describe the ACCOUNT are testable. The rest
# are labelled on the card under C 07's second branch.
#
# `device_family` and `hardware` are deliberately NOT testable, though they
# look like the most checkable of all. A sentence naming a device is far more
# often naming the thing being recommended than constraining the estate: Part A
# rule 2 reads "Use EliteBook 6 G2 when the account needs enterprise AI across
# a large, repeatable fleet", and testing that as "the account must already run
# EliteBook 6 G2" would drop the rule every time it was right. Telling the two
# apart is a reading task, and guessing wrong silently deletes recommendations.
#
# Where a device condition genuinely gates an offering - "Eligible HP PCs only"
# in the Wolf matrix - it is enforced by `wolf_offering`, against the matrix
# column that means exactly that, rather than by reading prose.
TESTABLE_CONDITION_TYPES = frozenset({"country", "management_environment", "os"})


def classify_condition(sentence: str) -> str:
    """Which kind of condition a sentence states, from a closed vocabulary."""
    text = _fold(sentence)
    for name, patterns in CONDITION_TYPES:
        if any(re.search(p, text) for p in patterns):
            return name
    return "unclassified"


def _tidy_clause(text: str) -> str:
    """What is left of a sentence once a clause has been lifted out of it.

    Removing "do not present it as included in every WXP licence" from "Treat
    WXP Collaboration as a separate licence; do not present it as included in
    every WXP licence." leaves a dangling semicolon and a stray full stop.
    """
    out = " ".join(str(text or "").split())
    # Lifting the clause out leaves the punctuation that joined it on - a
    # dangling "; ." in "Treat it as a separate licence; ." - so trailing
    # separators go before the full stop is put back.
    out = out.replace(" ;", ";").strip(" ;,.")
    if not out or not any(c.isalpha() for c in out):
        return ""
    if not out.endswith("."):
        out += "."
    return out


def split_rule_text(facts_text: str, system_action: str) -> tuple:
    """(allowed_facts, prohibitions, conditions) for one rule.

    Part A states its facts in their own column, semicolon-separated, already
    curated by HP. Part B has no facts column at all - the facts, the
    conditions and the prohibitions are all sentences of `System action` - so
    for Part B that text IS the fact corpus and is split here instead.

    A sentence can be both a fact and a condition ("Recommend HP IQ only for
    the compatible hardware listed below"), so `conditions` overlaps
    `allowed_facts` by design. What a prohibition is not, is a fact: it tells
    the engine what to withhold, so it is removed from what may be said.
    """
    prohibitions, conditions = [], []

    facts = [f.strip() for f in _text(facts_text).split(";") if f.strip()] \
        if facts_text else []

    for sentence in _sentences(system_action):
        if _PROHIBITION_RE.search(sentence):
            prohibitions.append(sentence)
            continue

        # A positive sentence can still carry a negative clause. The clause
        # becomes the prohibition and the rest stays a fact, so the two never
        # say the same thing twice on one card.
        remainder = sentence
        for clause in _PROHIBITION_CLAUSE_RE.findall(sentence):
            remainder = remainder.replace(clause, "")
            text = clause.strip().rstrip(".;, ")
            if text:
                prohibitions.append(text[0].upper() + text[1:] + ".")

        if not facts_text:
            kept = _tidy_clause(remainder)
            if kept:
                facts.append(kept)

        if _CONDITION_RE.search(sentence):
            conditions.append({"text": sentence,
                               "condition_type": classify_condition(sentence)})

    # A prohibition can also carry the condition that triggers it ("Do not use
    # for non-HP PCs"), and C 07 has to see it, so conditions are read from the
    # whole action text rather than only from what survived as a fact.
    for sentence in prohibitions:
        if _CONDITION_RE.search(sentence):
            conditions.append({"text": sentence,
                               "condition_type": classify_condition(sentence)})

    return facts, prohibitions, conditions


# Rules that must never become a recommendation on their own.
#
# Part A has no column for this, but the current hand-typed table
# (`product_rules.RULES`) marks seven of its eighteen rules `modifier_only` or
# `routing_only`, and that distinction is load-bearing: without it a rule that
# only says "prefer the sustainable configuration of whatever you already
# chose" becomes a product recommendation of its own, and C 06 ("one main
# recommendation") is gone. The flags are re-derived here from what the system
# action actually says, so the port cannot lose them.
_MODIFIER_RE = re.compile(
    r"\balready[- ]selected\b|\bstrengthens?\b|\bfor the product already\b|"
    r"\bnever choose a product\b|\bdo not choose .+ alone\b|\bin addition to\b|"
    r"\bapplies to the (selected|chosen)\b|\bmapped .+ deck\b", re.I)
_ROUTING_RE = re.compile(
    r"\buse first\b|\bbefore (product )?selection\b|\brouting\b|"
    r"\bchoose the offering using\b|\bgo to\b|\bselect the exact\b", re.I)


def derive_flags(signal_text: str, material: str, system_action: str) -> dict:
    """`modifier_only` / `routing_only`, from the rule's own wording."""
    blob = " ".join((_text(signal_text), _text(material), _text(system_action)))
    return {
        "modifier_only": bool(_MODIFIER_RE.search(blob)),
        "routing_only": bool(_ROUTING_RE.search(blob)),
    }


# What the hand-typed table already knows about Part A, carried across rather
# than re-derived.
#
# `product_rules.RULES` was transcribed from an earlier HP document and has been
# in production since; its flags are the same eighteen rules' behaviour, learned
# the hard way. Deriving them from wording alone got two of eighteen wrong in
# opposite directions - it called rule 1 a modifier because its action says "Do
# not choose it from an AI signal alone" (a caution, not a demotion) and missed
# rule 18 entirely. Rule 1 is the AI-PC recommendation; demoting it would have
# silently removed the platform's main AI play.
#
# So the table is the authority for Part A, the regex is kept as a cross-check,
# and any disagreement is printed rather than resolved quietly. Part B has no
# prior table, so there the regex stands alone.
PART_A_CARRIED = {
    r["rule_id"]: {
        "modifier_only": bool(r.get("modifier_only")),
        "routing_only": bool(r.get("routing_only")),
        "requires_exact_competitor": bool(r.get("requires_exact_competitor")),
        "roster_signal": r.get("roster_signal"),
    }
    for r in RULES if r.get("rule_id")
}


# ==============================================================================
# Signal tokens - the one derived field, and the three gates on it
# ==============================================================================

SYSTEM_PROMPT = """You produce search tokens for one rule of an HP sales rulebook.

You are given the rule's "verified account signal" cell. Somewhere in a
company's uploaded data - job postings, technology detections, news, intent
topics - there may be wording that means the same thing. Your job is to list the
surface forms that wording realistically takes.

RULES, all mandatory:

1. EVERY TOKEN MUST BE ANCHORED IN THE SUPPLIED CELL. Use its own words, or an
   ordinary synonym of one of its words. Do not add a topic the cell does not
   raise. Every token is checked against the cell afterwards and an unanchored
   one is discarded.

2. NEVER NAME A VENDOR OR PRODUCT THE CELL DOES NOT NAME. Not HP's, not a
   competitor's. If the cell says "endpoint security" do not write "CrowdStrike"
   or "Microsoft Defender".

3. NO BARE GENERIC WORDS. A token must be specific enough that finding it in a
   company's files means something. "ai", "fleet", "security", "executive",
   "collaboration", "support" and "management" on their own are useless - they
   match everything. Two or three words is usually right.

4. LOWERCASE, NO PUNCTUATION, 2 to 6 WORDS EACH. Return 4 to 10 of them.

5. RETURN FEWER RATHER THAN PAD. A short, precise list is a good answer.

Return JSON only: {"tokens": ["<token>", ...]}"""

# Words that carry no meaning on their own. A token made only of these is
# dropped whatever the model says, and they do not count as anchors.
_STOPWORDS = frozenset(["a", "an", "and", "or", "the", "of", "for", "to", "in", "on", "with", "without", "at", "by", "from", "is", "are", "be", "being", "been", "that", "this", "those", "these", "it", "its", "as", "if", "then", "than", "when", "where", "which", "who", "whom", "whose", "any", "all", "some", "each", "other", "more", "most", "less", "least", "new", "existing", "such", "via", "per", "across", "need", "needs", "needed", "needing", "use", "used", "using", "uses", "may", "can", "could", "should", "would", "will"])

# Tokens that match almost any company's files. Every one of these was either
# observed as a false positive on a live account or is a word the rulebook uses
# so often that it identifies nothing.
_TOO_GENERIC = frozenset(["ai", "arm", "intelligence", "fleet", "security", "support", "management", "collaboration", "executive", "hardware", "software", "device", "devices", "technology", "operations", "business", "company", "customer", "customers", "user", "users", "employee", "employees", "service", "services", "solution", "solutions", "product", "products", "platform", "system", "systems", "data", "cloud", "digital", "work", "workplace", "workforce", "print", "printing", "scan", "scanning", "deployment", "lifecycle"])

# Vendor and product words. A token may narrow a rule's subject with ordinary
# English; it may never introduce one of these, because naming a vendor the rule
# does not name is how a WOLF rule would come to match "CrowdStrike".
# Curated rather than derived from `HP_LINE_TOKENS`: splitting that list into
# words dragged in "pc", "device", "workstation", "elite" and "pro", which are
# ordinary English here, and blocked good tokens for naming them. Only words
# that identify a maker or a named product belong in this set.
_ENTITY_WORDS = frozenset(
    list(COMPETITORS)
    + ["elitebook", "probook", "zbook", "elitedesk", "prodesk", "elitestudio",
       "prostudio", "dragonfly", "omnibook", "anyware", "daas", "siteprint",
       "sureclick", "thinkpad", "latitude", "macbook", "surface"]
    + ["hp", "poly", "microsoft", "google", "intel", "amd", "nvidia", "qualcomm",
       "snapdragon", "crowdstrike", "sentinelone", "symantec", "kaspersky",
       "mcafee", "sophos", "trellix", "vmware", "citrix", "ibm", "cisco",
       "xerox", "ricoh", "brother", "epson", "kyocera", "sharp", "toshiba",
       "fujitsu", "panasonic", "razer", "framework", "dynabook"])

_MIN_TOKEN_WORDS = 2
_MAX_TOKEN_WORDS = 6


def _content_words(value) -> list:
    """Meaningful words of a phrase, lowercased and stripped of punctuation.

    Trailing punctuation has to go or the token never matches: the signal cell
    ends "...or value sensitivity." and a stored token of "value sensitivity."
    would not be found in an account file that says "value sensitivity".
    """
    words = re.findall(r"[a-z0-9][a-z0-9+&/.-]*", _fold(value))
    return [w for w in (x.strip(".-/&+") for x in words)
            # A bare number is useless as a search token and actively harmful:
            # the cell "1,000 or more PC seats" split into "1" and "000", and
            # "000" then read as a figure the source never stated.
            if w and w not in _STOPWORDS and not w.isdigit()]


def baseline_tokens(signal_text: str) -> list:
    """Tokens taken straight out of the signal cell, with no model at all.

    The cell is a comma-or-semicolon separated list of phrases much of the
    time, so splitting it is already most of the answer. This is what the
    loader falls back to with `--no-tokens`, and it is the floor the model's
    suggestions are added to rather than a thing the model replaces.
    """
    out = []
    for piece in re.split(r"[,;]| - |–|—", _text(signal_text)):
        words = _content_words(piece)
        if _MIN_TOKEN_WORDS <= len(words) <= _MAX_TOKEN_WORDS:
            out.append(" ".join(words))
    return out


def _gate_tokens(proposed, signal_text: str) -> tuple:
    """(kept, rejected). Three gates, all deterministic, all in Python.

    1. **Anchored in subject.** At least one of the token's words must appear
       in this rule's own signal cell. Unanchored words are allowed - "ai hiring trends" for a cell that says
       "AI hiring" is a narrower phrasing and can only ever match less - but an
       unanchored word may not be a vendor or product name, which is the one
       way a token could change what the rule is about.
    2. **Specific.** Not made only of generic words, and not a known false
       positive from `product_rules.GLOBAL_EXCLUDE_PHRASES`, every entry of
       which was observed matching the wrong thing on a real account.
    3. **Well formed.** Two to six content words, no duplicates.

    An earlier version required *every* word to be anchored. It rejected 476 of
    ~700 proposals, nearly all for adding an ordinary modifier - "tools",
    "trends", "devices" - while the subject was intact. That is not what the
    gate is for.
    """
    anchor = set(_content_words(signal_text))
    kept, rejected, seen = [], [], set()

    for raw in (proposed or []):
        token = " ".join(_content_words(raw))
        if not token:
            continue
        words = token.split()

        if token in seen:
            continue
        if not (_MIN_TOKEN_WORDS <= len(words) <= _MAX_TOKEN_WORDS):
            rejected.append("%s: %d word(s)" % (token, len(words)))
            continue
        if all(w in _TOO_GENERIC for w in words):
            rejected.append("%s: generic" % token)
            continue
        if any(p in token for p in GLOBAL_EXCLUDE_PHRASES):
            rejected.append("%s: known false positive" % token)
            continue

        intruders = [w for w in words
                     if w not in anchor and w in _ENTITY_WORDS]
        if intruders:
            rejected.append("%s: names %s, which the rule does not"
                            % (token, ", ".join(intruders)))
            continue

        if not any(w in anchor for w in words):
            rejected.append("%s: no word of it appears in the rule's own signal"
                            % token)
            continue

        seen.add(token)
        kept.append(token)

    return kept, rejected


def signal_tokens(signal_text: str, use_model: bool) -> tuple:
    """(tokens, rejected) for one rule's signal cell."""
    proposed = list(baseline_tokens(signal_text))

    if use_model and _text(signal_text):
        from app.core.llm import generate_gpt4o_json_completion
        result = generate_gpt4o_json_completion(
            SYSTEM_PROMPT,
            "Verified account signal:\n%s" % _text(signal_text))
        if isinstance(result, dict):
            proposed += [str(t) for t in (result.get("tokens") or [])]

    return _gate_tokens(proposed, signal_text)


# ==============================================================================
# Observable terms - what the account's own files would actually say
# ==============================================================================
#
# `signal_tokens` are anchored in the rule's own wording, which makes them
# precise and nearly useless for matching. Measured against a real account:
# 3,440 evidence items, 113 rules, and not one routing type fired. The reason is
# not the matcher, it is the vocabulary gap.
#
#     the rulebook says   "High ticket volume, employee technology friction"
#     the account says    "ManageEngine", "JIRA Software", "Engineering Manager"
#
# Nothing lexical bridges that. The bridge is knowledge - ManageEngine is IT
# service management, which is where ticket volume lives - and it is exactly
# what `tech_confidence.RULEBOOK_TECHNOLOGIES` does by hand for thirteen rules.
# This does it for all 113, once, at load time, and stores the result as data a
# reviewer can read and correct.
#
# These terms are never shown to anyone. They decide which rule is considered,
# and the rule's own verbatim text is what a seller eventually reads.

OBSERVABLE_PROMPT = """You are given one rule from an HP sales rulebook: the business
signal it looks for, and the HP offering it leads to.

Your job is to list what would literally appear in a company's own data files if
that signal were true of them. Their files are exports, not prose: technology
detection lists, job postings, intent-topic labels, news headlines.

WHAT TO RETURN - concrete, observable things:
  - named software and vendors ("ServiceNow", "ManageEngine", "Intune", "Okta")
  - technology categories as a vendor list would label them ("endpoint security",
    "mobile device management", "managed print")
  - job titles and functions ("service desk analyst", "endpoint engineer")
  - named activities a posting or headline would describe ("device refresh",
    "office relocation", "iso 27001 certification")

WHAT NOT TO RETURN:
  - the rulebook's own abstract wording. "employee technology friction" and
    "fragmented fleet visibility" describe a problem; they never appear in an
    export. Translate them into what the data would show instead.
  - anything so broad it fits any company: "ai", "security", "cloud", "support",
    "management", "devices", "technology", "it".
  - HP's own products. The account's files describe the account, not HP's
    catalogue, and a rule must be earned by what the account has - not by HP.

Return 6 to 14 terms, lowercase, 1 to 4 words each.

Return JSON only: {"terms": ["<term>", ...]}"""


# A term claimed by this many different rule families is describing the modern
# workplace rather than any one opportunity, and would fire everything at once.
MAX_FAMILIES_PER_TERM = 3

# Platforms and vendors that essentially every enterprise runs. On their own
# they identify nothing: "microsoft" was the single term firing WXP 12, matched
# 40 technographics cells on a real account, and made "WXP Enhanced Onboarding
# Service" that account's top recommendation - a rule whose own text says the
# rulebook holds no details for it.
#
# Qualified they are fine, and often exactly right: "microsoft intune",
# "windows autopilot", "microsoft teams rooms" each name something specific. So
# the rule is about the bare word, not the vendor.
_UBIQUITOUS = frozenset("""
microsoft google apple adobe oracle sap amazon aws azure cisco ibm windows
linux android ios macos chrome office teams zoom slack outlook excel word
sharepoint onedrive gmail workspace salesforce jira confluence
""".split())


def _gate_terms(proposed) -> tuple:
    """(kept, rejected) for one rule's observable terms.

    A looser gate than `_gate_tokens`, and deliberately so: the whole point of
    these is to name things the rule's own wording does not, so anchoring them
    to it would defeat them. What survives instead is specificity - a term has
    to be narrow enough that finding it in a company's files means something.
    """
    kept, rejected, seen = [], [], set()
    for raw in (proposed or []):
        term = " ".join(_content_words(raw))
        if not term or term in seen:
            continue
        words = term.split()
        if len(words) > 4:
            rejected.append("%s: %d words" % (term, len(words)))
            continue
        if all(w in _TOO_GENERIC for w in words):
            rejected.append("%s: generic" % term)
            continue
        if any(p in term for p in GLOBAL_EXCLUDE_PHRASES):
            rejected.append("%s: known false positive" % term)
            continue
        if len(words) == 1 and words[0] in _UBIQUITOUS:
            rejected.append("%s: every enterprise runs it; qualify it or drop it"
                            % term)
            continue
        seen.add(term)
        kept.append(term)
    return kept, rejected


def observable_terms(signal_text: str, offering: str, use_model: bool) -> tuple:
    if not use_model or not _text(signal_text):
        return [], []
    from app.core.llm import generate_gpt4o_json_completion
    result = generate_gpt4o_json_completion(
        OBSERVABLE_PROMPT,
        "Business signal:\n%s\n\nHP offering it leads to:\n%s"
        % (_text(signal_text), _text(offering) or "(not stated)"))
    if not isinstance(result, dict):
        return [], ["the model returned nothing usable"]
    return _gate_terms(result.get("terms"))


def prune_overbroad(rules: list, routes: list = ()) -> list:
    """Drop rule terms that too many different families claim.

    Deterministic, and it catches what no per-rule gate can see: "microsoft
    office" is specific enough to pass on its own and useless once it turns up
    under workforce experience, deployment, print and security alike. Judged on
    families rather than rules, so twenty Care Pack rules sharing a term is
    fine - that is one opportunity, described twenty ways.

    Routing rows are exempt, and are not counted when tallying families. Their
    whole job is to be broad enough to open a family, so their terms overlap
    their own rules by design; counting each routing row as a family of its own
    dropped 447 terms and left every opportunity type unable to fire.
    """
    families: dict = {}
    for rule in rules:
        for term in rule.get("observable_terms") or []:
            families.setdefault(term, set()).add(rule.get("family"))

    dropped = []
    overbroad = {t for t, f in families.items() if len(f) > MAX_FAMILIES_PER_TERM}
    for rule in rules:
        keep = [t for t in (rule.get("observable_terms") or []) if t not in overbroad]
        for t in set(rule.get("observable_terms") or []) - set(keep):
            dropped.append("%s: %s claimed by %d families"
                           % (rule.get("rule_label"), t, len(families[t])))
        rule["observable_terms"] = keep
    return dropped


# ==============================================================================
# Parsing
# ==============================================================================

def _header(table) -> list:
    return [_fold(c.text) for c in table.rows[0].cells]


def _identify(table) -> str | None:
    """Which block a table is, by its header.

    A signature matches when every one of its cells is present, exactly or as a
    substring. Where two signatures both match, the one matching more cells
    EXACTLY wins - the service guardrails are headed "ID | Area | Simple rule"
    and the common ones "ID | Area | Rule", so a substring test alone let the
    common signature claim both and silently merged two different guardrail
    sets into one.
    """
    header = _header(table)
    best, best_score = None, -1
    for kind, required in TABLE_SIGNATURES:
        if not all(any(req == h or req in h for h in header) for req in required):
            continue
        score = sum(1 for req in required if any(req == h for h in header))
        if score > best_score:
            best, best_score = kind, score
    return best


def _tables_with_headings(doc):
    """(index, table, the Heading 1 above it) in document order.

    `doc.tables` loses the surrounding prose, and the prose is where the
    document says which HP material each block of rules came from.
    """
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    heading, index = "", 0
    for child in doc.element.body.iterchildren():
        tag = child.tag.split("}")[-1]
        if tag == "p":
            para = Paragraph(child, doc)
            if para.style.name.startswith("Heading") and para.text.strip():
                heading = _text(para.text)
        elif tag == "tbl":
            yield index, Table(child, doc), heading
            index += 1


def _highlighted_rows(table) -> set:
    """1-based data-row numbers carrying any highlighted run.

    The client highlights what a revision added. `python-docx` exposes it as
    `run.font.highlight_color`, so the marking is data rather than a reading of
    the page.
    """
    out = set()
    for position, row in enumerate(table.rows[1:], 1):
        for cell in row.cells:
            if any(run.font.highlight_color is not None
                   for para in cell.paragraphs for run in para.runs):
                out.add(position)
                break
    return out


def _rows(table) -> list:
    """Data rows as lists of verbatim cell text."""
    return [[_text(c.text) for c in r.cells] for r in table.rows[1:]]


def _col(header: list, *names) -> int | None:
    for name in names:
        for i, h in enumerate(header):
            if h == name or name in h:
                return i
    return None


def parse(path: str, use_model: bool, limit: int = 0) -> tuple:
    """(documents, report). Everything in the file, as storable documents."""
    from docx import Document

    doc = Document(path)
    docs, report = [], {"tables": [], "unmatched": [], "rejected_tokens": [],
                        "flag_disagreements": [], "overbroad_terms": [],
                        "unknown_families": []}

    for index, table, heading in _tables_with_headings(doc):
        kind = _identify(table)
        report["tables"].append({"index": index, "kind": kind,
                                 "rows": len(table.rows) - 1,
                                 "section": heading})
        if kind is None:
            report["unmatched"].append({"index": index, "header": _header(table)})
            continue
        if kind in ("structure",):
            continue

        header = _header(table)
        handler = _HANDLERS[kind]
        if kind == "part_a":
            rows = handler(_rows(table), header, report["flag_disagreements"])
        elif kind == "part_b":
            rows = handler(_rows(table), header, report["unknown_families"])
        else:
            rows = handler(_rows(table), header)

        # C 11 wants an `evidence_source` on every runtime offering, and C 12
        # allows only facts that source supports. The document already answers
        # it structurally: each rule table sits under the Heading 1 naming the
        # HP material it was written from.
        source = SECTION_TO_SOURCE.get(_fold(heading))
        highlighted = _highlighted_rows(table)
        for position, record in enumerate(rows, 1):
            if source:
                record["evidence_source"] = source["source"]
                record["confidential"] = bool(source.get("confidential"))
            # The client marks a revision's additions in yellow. Recording it
            # makes "what changed in this revision" answerable from the data
            # rather than by diffing documents by hand.
            record["is_new"] = position in highlighted
        docs.extend(rows)

    # `order` is the document-order tie-break, and it was counted per TABLE.
    # PRINT now spans two tables, so PRINT 01-03 were numbered 1-3 and PRINT 04
    # started again at 1 - which made "the rulebook's own order" ambiguous for
    # exactly the family the revision expanded. Renumbered per family across
    # the whole document, which is what the tie-break always meant.
    per_family: dict = {}
    for record in docs:
        if record.get("kind") != "rule":
            continue
        family = record["family"]
        per_family[family] = per_family.get(family, 0) + 1
        record["order"] = per_family[family]

    # Signal tokens, after parsing, so one pass over the rules covers both parts.
    #
    # Every rule gets the baseline first, so `--limit` bounds how many model
    # calls are made without leaving the rest of the rulebook half-built.
    rules = [d for d in docs if d["kind"] == "rule"]
    for rule in rules:
        tokens, rejected = _gate_tokens(
            baseline_tokens(rule["signal_text"]), rule["signal_text"])
        rule["signal_tokens"] = tokens
        rule["tokens_rejected"] = rejected or None

    # The routing table is the outer gate - a family whose routing type never
    # fires is loaded and unreachable, whatever its own rules say - so its rows
    # are given the same treatment rather than the baseline alone. Enterprise
    # AI produced no usable token from its own wording and would have made all
    # twelve HP IQ rules dead on arrival.
    routes = [d for d in docs if d["kind"] == "routing"]
    for route in routes:
        tokens, rejected = _gate_tokens(
            baseline_tokens(route["evidence_examples"]), route["evidence_examples"])
        route["signal_tokens"] = tokens
        route["tokens_rejected"] = rejected or None

    for item in rules + routes:
        item["observable_terms"] = []

    asked = (rules + routes)[:limit] if limit else (rules + routes)
    for i, item in enumerate(asked, 1):
        if not use_model:
            break
        source = item.get("signal_text") or item.get("evidence_examples")
        tokens, rejected = signal_tokens(source, True)
        item["signal_tokens"] = tokens
        item["tokens_rejected"] = rejected or None

        terms, term_rejected = observable_terms(
            source, item.get("offering") or "", True)
        item["observable_terms"] = terms
        if term_rejected:
            item["tokens_rejected"] = (item["tokens_rejected"] or []) + term_rejected
        if i % 10 == 0 or i == len(asked):
            print("   tokens %d/%d" % (i, len(asked)))

    report["overbroad_terms"] = prune_overbroad(rules, routes)

    # C 11, last: the structured view is built from the finished record so it
    # reflects every derivation above it.
    for rule in rules:
        rule["structured"] = structured_record(rule)

    for item in rules + routes:
        label = item.get("rule_label") or item.get("opportunity_type")
        for r in (item.get("tokens_rejected") or []):
            report["rejected_tokens"].append("%s: %s" % (label, r))

    report["counts"] = _counts(docs)
    return docs, report


def _handle_part_a(rows: list, header: list, disagreements: list) -> list:
    i_rule = _col(header, "rule")
    i_signal = _col(header, "account signal")
    i_material = _col(header, "hp material used")
    i_facts = _col(header, "hp facts available")
    i_action = _col(header, "system action")

    out = []
    for order, row in enumerate(rows, 1):
        label = row[i_rule]
        if not label:
            continue
        facts, prohibitions, conditions = split_rule_text(
            row[i_facts], row[i_action])
        rule_id = int(re.sub(r"\D", "", label) or order)

        read = derive_flags(row[i_signal], row[i_material], row[i_action])
        carried = PART_A_CARRIED.get(rule_id)
        if carried:
            for flag in ("modifier_only", "routing_only"):
                if read[flag] != carried[flag]:
                    disagreements.append(
                        "Part A rule %d: the text reads %s=%s, the shipped "
                        "table says %s - keeping the table"
                        % (rule_id, flag, read[flag], carried[flag]))
            flags = dict(carried)
        else:
            disagreements.append(
                "Part A rule %d is not in the shipped table; using the text"
                % rule_id)
            flags = read

        out.append({
            "_id": "A::%02d" % rule_id,
            "kind": "rule",
            "part": "A",
            "family": "HARDWARE",
            "rule_label": label,
            "order": order,
            "signal_text": row[i_signal],
            "material": row[i_material],
            "offering": row[i_material],
            "facts_text": row[i_facts],
            "system_action": row[i_action],
            "allowed_facts": facts,
            "prohibitions": prohibitions,
            "conditions": conditions,
            **flags,
        })
    return out


def _handle_part_b(rows: list, header: list, unknown: list | None = None) -> list:
    i_rule = _col(header, "rule")
    i_signal = _col(header, "verified account signal")
    i_offering = _col(header, "hp offering to consider")
    i_action = _col(header, "system action")

    unknown = unknown if unknown is not None else []
    out = []
    for order, row in enumerate(rows, 1):
        label = row[i_rule]
        if not label:
            continue
        family = label.split()[0].upper()
        if family not in PART_B_FAMILIES:
            # Loud. A bare `continue` here once dropped a whole family - the
            # revision added INK 01-06 and a load would have reported success
            # having stored six fewer rules than the document contains.
            unknown.append(label)
            continue
        facts, prohibitions, conditions = split_rule_text("", row[i_action])
        out.append({
            "_id": "B::%s" % _slug(label).upper(),
            "kind": "rule",
            "part": "B",
            "family": family,
            "rule_label": label,
            "order": order,
            "signal_text": row[i_signal],
            "material": None,
            "offering": row[i_offering],
            # Part B has no facts column: the system action IS the fact corpus.
            "facts_text": row[i_action],
            "system_action": row[i_action],
            "allowed_facts": facts,
            "prohibitions": prohibitions,
            "conditions": conditions,
            **derive_flags(row[i_signal], row[i_offering], row[i_action]),
        })
    return out


def _handle_routing(rows: list, header: list) -> list:
    i_type = _col(header, "opportunity type")
    i_evidence = _col(header, "examples of verified account evidence", "examples")
    i_go = _col(header, "go to these rules")

    out = []
    for order, row in enumerate(rows, 1):
        opportunity = row[i_type]
        if not opportunity:
            continue
        key = _fold(opportunity)
        families = ROUTING_TO_FAMILIES.get(key) or ()
        tokens, _rejected = _gate_tokens(
            baseline_tokens(row[i_evidence]), row[i_evidence])
        out.append({
            "_id": "routing::%s" % _slug(opportunity),
            "kind": "routing",
            "opportunity_type": opportunity,
            "order": order,
            "evidence_examples": row[i_evidence],
            "go_to_text": row[i_go],
            # Read from the document and checked against the map, rather than
            # trusted from either alone. An empty list is reported by `verify`,
            # never guessed at.
            "families": list(families),
            "signal_tokens": tokens,
        })
    return out


def _handle_matrix_wolf(rows: list, header: list) -> list:
    return [{
        "_id": "matrix::wolf::%s" % _slug(row[0]),
        "kind": "matrix",
        "matrix": "wolf",
        "family": "WOLF",
        "offering": row[0],
        "order": order,
        "columns": dict(zip(header, row, strict=False)),
    } for order, row in enumerate(rows, 1) if row and row[0]]


def _handle_matrix_iq(rows: list, header: list) -> list:
    return [{
        "_id": "matrix::iq::%s" % _slug(row[0]),
        "kind": "matrix",
        "matrix": "iq",
        "family": "IQ",
        "category": row[0],
        "order": order,
        "columns": dict(zip(header, row, strict=False)),
    } for order, row in enumerate(rows, 1) if row and row[0]]


def _guardrail(prefix: str, scope: str):
    def handler(rows: list, header: list) -> list:
        i_id = _col(header, "id", "guardrail")
        i_area = _col(header, "area")
        i_rule = _col(header, "rule", "simple rule", "exact implementation rule")
        out = []
        for order, row in enumerate(rows, 1):
            ident = row[i_id] if i_id is not None else ""
            body = row[i_rule] if i_rule is not None else ""
            if not (ident or body):
                continue
            out.append({
                "_id": "guardrail::%s-%s" % (prefix, _slug(ident) or order),
                "kind": "guardrail",
                "scope": scope,
                "guardrail_id": ident,
                "area": row[i_area] if i_area is not None else None,
                "order": order,
                "rule_text": body,
            })
        return out
    return handler


def _handle_country_list(rows: list, header: list) -> list:
    i_type = _col(header, "restriction type")
    i_countries = _col(header, "exact countries")

    out = []
    for order, row in enumerate(rows, 1):
        label = row[i_type]
        if not label:
            continue
        raw = row[i_countries] if i_countries is not None else ""
        # The cell is "Block the affected claim in: A; B; C." - everything
        # before the colon is instruction, not a country.
        body = raw.split(":", 1)[1] if ":" in raw else raw
        countries, aliases, notes = [], {}, []
        for piece in body.split(";"):
            # The final entry runs the last country into a paragraph of
            # instruction - "...; Mexico. Also block in any CIS country
            # covered by the playbook restriction. Store the CIS-country
            # restriction as a market-level block..." - and storing that whole
            # string as a country name is how "mexico. also block in any cis
            # country..." ended up in the list.
            head, _sep, tail = _text(piece).partition(". ")
            if tail:
                notes.append(tail.strip())
            name = head.rstrip(".")
            if not name:
                continue
            # "United Arab Emirates (UAE)" and "Reunion (France)" both carry a
            # parenthetical; it is an alias, not part of the name.
            bare = _text(re.sub(r"\([^)]*\)", "", name))
            inner = re.findall(r"\(([^)]*)\)", name)
            if not bare:
                continue
            countries.append(bare)
            for alias in inner:
                if _text(alias):
                    aliases[_fold(alias)] = _fold(bare)
        kind_key = "superlative" if "superlative" in _fold(label) else "competitor"
        out.append({
            "_id": "country_list::%s" % kind_key,
            "kind": "country_list",
            "restriction": kind_key,
            "restriction_label": label,
            "order": order,
            "countries": countries,
            "countries_folded": sorted({_fold(c) for c in countries}),
            "aliases": aliases,
            # Instructions that follow the list. The competitor cell carries a
            # sweep - "Also block in any CIS country covered by the playbook
            # restriction" - which is why the shipped constant names Armenia,
            # Belarus, Kazakhstan and the rest that the literal list does not.
            "notes": notes,
            "raw": raw,
        })
    return out


def _handle_source(rows: list, header: list) -> list:
    # Provenance only. C 02: "Source names are provenance only; the engine must
    # not reopen the original HP files during recommendation generation." These
    # are stored so a reviewer can trace a rule, and are never read at runtime.
    return [{
        "_id": "source::%s" % _slug(row[0]),
        "kind": "source",
        "source_name": row[0],
        "use_in_document": row[1] if len(row) > 1 else None,
        "order": order,
        "runtime_use": False,
    } for order, row in enumerate(rows, 1) if row and row[0]]


def _handle_schema(rows: list, header: list) -> list:
    """The client's 12-field runtime schema, stored as the contract it is.

    C 11 requires every runtime offering to carry these fields, and the
    governance note says a claim missing a required one must be narrowed or
    omitted rather than inferred. Storing the field list means the requirement
    is checkable against the loaded rules instead of living in a comment.
    """
    return [{
        "_id": "schema::%s" % _slug(row[0]),
        "kind": "schema",
        "field": row[0],
        "required_content": row[1] if len(row) > 1 else None,
        "order": order,
    } for order, row in enumerate(rows, 1) if row and row[0]]


_HANDLERS = {
    "schema": _handle_schema,
    "part_a": _handle_part_a,
    "part_b": _handle_part_b,
    "routing": _handle_routing,
    "matrix_wolf": _handle_matrix_wolf,
    "matrix_iq": _handle_matrix_iq,
    "guardrail_common": _guardrail("C", "common"),
    "guardrail_product": _guardrail("P", "product"),
    "guardrail_service": _guardrail("G", "service"),
    "country_list": _handle_country_list,
    "source": _handle_source,
}


def _counts(docs: list) -> dict:
    out = {}
    for d in docs:
        key = d["kind"]
        if key == "rule":
            key = "rule:%s" % d["family"]
        elif key == "guardrail":
            key = "guardrail:%s" % d["scope"]
        elif key == "matrix":
            key = "matrix:%s" % d["matrix"]
        out[key] = out.get(key, 0) + 1
    return dict(sorted(out.items()))


# ==============================================================================
# Verifying the parse against the document
# ==============================================================================

def verify(docs: list, unknown_families: list | None = None) -> list:
    """Problems worth refusing to load over.

    Cheap, and it is the difference between a silently half-loaded rulebook and
    a loud one. A rule with no signal can never fire; a rule with nothing it may
    say can only produce an empty card.
    """
    problems = []
    rules = [d for d in docs if d["kind"] == "rule"]

    for rule in rules:
        if not _text(rule["signal_text"]):
            problems.append("%s has no account signal" % rule["rule_label"])
        if not rule["allowed_facts"]:
            problems.append("%s has nothing it is allowed to say" % rule["rule_label"])
        if not rule["signal_tokens"] and not rule.get("observable_terms"):
            problems.append("%s has nothing to match on" % rule["rule_label"])

    families = {d["family"] for d in rules if d["part"] == "B"}
    for family in PART_B_FAMILIES:
        if family not in families:
            problems.append("no %s rules were parsed" % family)

    routed = set()
    for label in unknown_families or []:
        problems.append("%s names a family this loader does not know; the rule "
                        "was not stored" % label)

    for route in [d for d in docs if d["kind"] == "routing"]:
        if not route["families"]:
            problems.append("routing type %r maps to no rule family"
                            % route["opportunity_type"])
        if not route.get("signal_tokens") and not route.get("observable_terms"):
            problems.append("routing type %r has nothing to match on, so the %s "
                            "rules can never fire"
                            % (route["opportunity_type"],
                               ", ".join(route["families"])))
        routed.update(route["families"])

    # Every Part B family must be reachable from the routing table, or its
    # rules are loaded and can never fire.
    for family in sorted(families - routed):
        problems.append("%s rules exist but no routing type reaches them" % family)

    if not [d for d in docs if d["kind"] == "country_list"]:
        problems.append("no country restriction list was parsed")

    # Every generated token must trace to its rule. This repeats gate 1 on the
    # stored result, the way load_case_studies re-checks figures after writing
    # them - the gate and the check are separate on purpose.
    for rule in rules:
        corpus = corpus_from_texts([rule["signal_text"]])
        for token in rule["signal_tokens"]:
            if corpus.unsourced_numbers(token):
                problems.append("%s: token %r carries an unsourced figure"
                                % (rule["rule_label"], token))
    return problems


# Sentences that name a way the offering plugs into something the account
# already runs. C 11 calls this `integration_routes`.
_INTEGRATION_RE = re.compile(
    r"\b(integrat|interoperab|coexist|connect|plug|api|sso|federat|"
    r"works with|alongside|deploy(ed|ment)? (via|through|with))\b", re.I)

# Where an offering may be sold or used. C 14 is the reason this exists:
# "Where the source labels an offering Direct Only, retain Direct Only in
# market_availability and do not present it as a general channel route."
_AVAILABILITY_RE = re.compile(
    r"\b(direct only|availability|available (in|only|for)|country|countries|"
    r"region|market|launch|english|united states|not available)\b", re.I)

# The rulebook governs itself. C 11 wants an owner recorded for change control,
# and the document is its own authority.
RULEBOOK_OWNER = "HP 220 Account Rulebook (client-supplied)"


def structured_record(record: dict) -> dict:
    """The client's twelve-field runtime schema, for one rule.

    C 11: "Every runtime offering must carry offering_id, name, business_unit,
    what_it_enables, qualifying_conditions, integration_routes, disqualifiers,
    proof_ids, market_availability and evidence_source, plus owner and version
    for governance. Missing required fields must narrow or block the affected
    claim."

    Seven of these already existed under this codebase's own names and are
    aliased rather than moved - renaming in place would break every consumer in
    the same change that adds the fields. The rest are derived from text the
    rule already carries, so nothing is invented: `integration_routes` and
    `market_availability` are sentences selected out of the system action,
    `evidence_source` comes from the section heading, `owner` is the document.

    `proof_ids` is left empty here. It is filled at match time from
    `hp_case_studies`, because which proof supports a rule depends on the
    account being sold to, not on the rule alone.
    """
    sentences = _sentences(record.get("system_action") or "")
    conditions = [c.get("text") for c in (record.get("conditions") or [])
                  if isinstance(c, dict) and c.get("text")]

    return {
        "offering_id": record.get("_id"),
        "name": record.get("offering"),
        "business_unit": record.get("family"),
        "what_it_enables": list(record.get("allowed_facts") or []),
        "qualifying_conditions": list(conditions),
        "integration_routes": [s for s in sentences if _INTEGRATION_RE.search(s)],
        "disqualifiers": list(record.get("prohibitions") or []),
        "proof_ids": [],
        "market_availability": [s for s in sentences + conditions
                                if _AVAILABILITY_RE.search(s)],
        "evidence_source": record.get("evidence_source"),
        "owner": RULEBOOK_OWNER,
    }


def knowledge_version(docs: list) -> str:
    """SHA-256 over the stored rulebook plus the extractor version.

    Mirrors `extract_hp_decks.py` and `load_case_studies.py`: a downstream
    fingerprint that includes this regenerates when the rulebook is reloaded.
    """
    payload = json.dumps(
        [{"id": d["_id"], "kind": d["kind"],
          "text": [d.get("signal_text"), d.get("system_action"),
                   d.get("rule_text"), d.get("facts_text")],
          "tokens": d.get("signal_tokens"),
          "terms": d.get("observable_terms")}
         for d in sorted(docs, key=lambda x: x["_id"])],
        sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(
        (payload + "|v%d" % EXTRACTOR_VERSION).encode("utf-8")).hexdigest()


# ==============================================================================
# CLI
# ==============================================================================

def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--docx", default=DEFAULT_DOCX)
    ap.add_argument("--apply", action="store_true", help="write; otherwise dry run")
    ap.add_argument("--limit", type=int, default=0,
                    help="derive tokens for the first N rules only")
    ap.add_argument("--show", type=int, default=3, help="sample this many rules")
    ap.add_argument("--no-tokens", action="store_true",
                    help="skip the model call; use the cell's own wording only")
    args = ap.parse_args()

    if not os.path.isfile(args.docx):
        sys.exit("No rulebook at %s" % args.docx)

    use_model = not args.no_tokens
    print("reading %s" % os.path.basename(args.docx))
    if use_model:
        print("deriving signal tokens with gpt-4o ...")

    docs, report = parse(args.docx, use_model, args.limit)

    print("\ntables:")
    for t in report["tables"]:
        print("   %2d  %-18s %3d rows" % (t["index"], t["kind"] or "UNMATCHED",
                                          t["rows"]))
    for u in report["unmatched"]:
        print("   !! table %d matched no known shape: %s" % (u["index"], u["header"]))

    print("\nparsed:")
    for key, count in report["counts"].items():
        print("   %-22s %3d" % (key, count))
    rules = [d for d in docs if d["kind"] == "rule"]
    print("   %-22s %3d" % ("TOTAL RULES", len(rules)))

    flagged = [r for r in rules if r["modifier_only"] or r["routing_only"]]
    if flagged:
        print("\nrules that may never stand alone as a recommendation (C 06):")
        for r in flagged:
            kinds = [k for k in ("modifier_only", "routing_only") if r[k]]
            print("   %-10s %s" % (r["rule_label"], ", ".join(kinds)))

    if report["flag_disagreements"]:
        print("\nflag cross-check against the shipped table:")
        for line in report["flag_disagreements"]:
            print("   %s" % line)

    testable = sum(1 for r in rules for c in r["conditions"]
                   if c["condition_type"] in TESTABLE_CONDITION_TYPES)
    total = sum(len(r["conditions"]) for r in rules)
    print("\nconditions: %d total, %d testable against account evidence, "
          "%d label-only (C 07)" % (total, testable, total - testable))

    terms = sum(len(r.get("observable_terms") or []) for r in rules)
    print("\nobservable terms: %d across %d rules (%.1f each)"
          % (terms, len(rules), terms / max(1, len(rules))))
    if report["overbroad_terms"]:
        print("   %d dropped for spanning more than %d families:"
              % (len(report["overbroad_terms"]), MAX_FAMILIES_PER_TERM))
        for line in report["overbroad_terms"][:10]:
            print("      %s" % line)

    if report["rejected_tokens"]:
        print("\nsignal tokens rejected (%d):" % len(report["rejected_tokens"]))
        for line in report["rejected_tokens"][:20]:
            print("   %s" % line)
        if len(report["rejected_tokens"]) > 20:
            print("   ... and %d more" % (len(report["rejected_tokens"]) - 20))

    for rule in rules[:args.show]:
        print("\n" + "-" * 78)
        print("%s  [%s / %s]" % (rule["rule_label"], rule["part"], rule["family"]))
        print("  signal    : %s" % rule["signal_text"][:150])
        print("  offering  : %s" % (rule["offering"] or "")[:110])
        print("  tokens    : %s" % ", ".join(rule["signal_tokens"][:5]))
        print("  observable: %s" % ", ".join(rule.get("observable_terms") or [])[:150])
        for fact in rule["allowed_facts"][:3]:
            print("  may say   : %s" % fact[:130])
        for prohibition in rule["prohibitions"][:2]:
            print("  must not  : %s" % prohibition[:130])
        for condition in rule["conditions"][:3]:
            mark = "testable" if condition["condition_type"] in TESTABLE_CONDITION_TYPES \
                else "label only"
            print("  condition : [%s / %s] %s"
                  % (condition["condition_type"], mark, condition["text"][:100]))

    problems = verify(docs, report["unknown_families"])
    if problems:
        print("\n%d problem(s) with the parse:" % len(problems))
        for p in problems[:25]:
            print("   - %s" % p)
        if len(problems) > 25:
            print("   ... and %d more" % (len(problems) - 25))

    version = knowledge_version(docs)
    print("\nknowledge_version: %s" % version)

    if not args.apply:
        print("\nDry run. Nothing written. Re-run with --apply to store.")
        return

    if problems:
        sys.exit("\nRefusing to load: fix the problems above, or re-run with "
                 "--show to inspect. Nothing was written.")

    from app.database.mongodb import get_db
    db = get_db()
    for doc in docs:
        db[COLLECTION].update_one({"_id": doc["_id"]}, {"$set": doc}, upsert=True)

    live = {d["_id"] for d in docs} | {VERSION_DOC_ID}
    removed = db[COLLECTION].delete_many({"_id": {"$nin": list(live)}}).deleted_count

    db[COLLECTION].update_one(
        {"_id": VERSION_DOC_ID},
        {"$set": {"knowledge_version": version,
                  "extractor_version": EXTRACTOR_VERSION,
                  "rule_count": len(rules),
                  "document": os.path.basename(args.docx)}},
        upsert=True)

    print("wrote %d documents (%d rules), removed %d stale"
          % (len(docs), len(rules), removed))


if __name__ == "__main__":
    main()
