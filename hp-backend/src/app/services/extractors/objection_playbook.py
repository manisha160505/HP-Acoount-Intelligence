import difflib
import hashlib
import json
import logging
import re
from datetime import UTC, datetime

from bson import ObjectId

from app.core.llm import generate_gpt4o_json_completion
from app.database.mongodb import get_db
from app.services.extractors.grounding import (
    GroundingReport,
    build_corpus,
    check_text,
)
from app.services.hp import case_studies as cs, rulebook as rb
from app.services.hp.guardrails import (
    SUPERLATIVE_BLOCK_COUNTRIES,
    SUPERLATIVE_RE,
    approve_rulebook_facts,
    prose_guardrail_faults,
    summarise,
)

logger = logging.getLogger(__name__)
from app.services.extractors.datasets import (
    account_display_name,
    read_dataset_records,
    requires_local_datasets,
)
from app.services.extractors.stakeholder_map import (
    normalize_department,
    resolve_field,
)

TECHNOGRAPHICS_CATEGORY_COLUMNS = [
    "Testing And Qa",
    "Sales",
    "Prog Langs And Frameworks",
    "Productivity And Operations",
    "Product And Design",
    "Platform And Storage",
    "Operations Software",
    "Operations Management",
    "Marketing",
    "It Security",
    "It Management",
    "Hr",
    "Finance And Accounting",
    "Ecommerce",
    "Devops And Development",
    "Customer Management",
    "Computer Networks",
    "Communications",
    "Collaboration",
    "Bi And Analytics"
]

# ==============================================================================
# HP CONTEST AREAS
#
# These tables describe HP's product lines and the fixed Explorium category
# schema. Nothing here is specific to any account - vendors, categories and
# contacts are all read from the uploaded files at runtime.
# ==============================================================================

# Which technographics category columns speak to each area HP competes in.
AREA_CATEGORY_COLUMNS = {
    "Client Devices": ["Platform And Storage", "It Management"],
    "Collaboration": ["Collaboration", "Communications"],
    "Print / MPS": ["Productivity And Operations", "Operations Management"],
    "Endpoint Security": ["It Security", "Computer Networks"],
    "Device Management": ["It Management", "Computer Networks"],
}

# Vendor tokens that indicate a competing product is present in an area. Matched
# case-insensitively on word boundaries against the stack entries.
# Technologies that ARE the area. These carry the objection and the reframe.
AREA_PRIMARY_TOKENS = {
    "Client Devices": ["dell", "lenovo", "asus", "acer", "msi", "apple ios", "macos",
                       "chromeos", "microsoft windows", "thinkpad", "latitude",
                       "macbook", "matebook", "surface laptop"],
    "Collaboration": ["zoom", "microsoft teams", "webex", "poly", "logitech",
                      "g suite", "google workspace", "slack", "ringcentral",
                      "microsoft office 365", "google meet"],
    "Print / MPS": ["canon", "epson", "xerox", "ricoh", "brother", "kyocera",
                    "lexmark", "sharp", "konica", "papercut", "printer"],
    # Endpoint protection only. Network security and identity are adjacent, not
    # endpoint security, and are listed as context below.
    "Endpoint Security": ["symantec", "kaspersky", "defender", "crowdstrike",
                          "sentinelone", "mcafee", "sophos", "trend micro",
                          "bitdefender", "eset", "carbon black", "cylance"],
    # Device management only. MFA and identity providers authenticate people;
    # they do not manage a device estate, so they are not primary here.
    "Device Management": ["intune", "workspace one", "airwatch", "jamf", "manageengine",
                          "sccm", "ivanti", "tanium", "ninjaone"],
}

# Adjacent technologies worth showing, but never the basis of the argument.
AREA_CONTEXT_TOKENS = {
    "Endpoint Security": ["cisco asa", "cisco ironport", "fortinet", "fortigate",
                          "fortimanager", "aruba clearpass", "palo alto",
                          "check point", "azure ad", "okta"],
}



# Which contact functions plausibly own each area. Matched against the
# normalised department and, word-boundary-wise, against the job title.
AREA_OWNER_DEPARTMENTS = {
    "Client Devices": ["Information Technology", "Operations"],
    "Collaboration": ["Information Technology", "Operations"],
    "Print / MPS": ["Operations", "Information Technology", "Finance"],
    "Endpoint Security": ["Information Technology", "Engineering & Technical"],
    "Device Management": ["Information Technology", "Engineering & Technical"],
}
# Only a STRONG title match resolves to a named contact. A weak match means the
# nearest technically-adjacent person, which is not the same as the owner, so the
# card names the owning function instead.
AREA_OWNER_STRONG_TOKENS = {
    "Client Devices": ["procurement", "end user", "information technology",
                       "it operations", "infrastructure"],
    "Collaboration": ["collaboration", "communications", "end user", "workplace"],
    "Print / MPS": ["procurement", "facilities", "general affairs", "administration"],
    "Endpoint Security": ["security", "ciso", "infosec", "cyber",
                          "information security"],
    "Device Management": ["information technology", "it operations", "infrastructure",
                          "procurement", "end user"],
}
AREA_OWNER_WEAK_TOKENS = {
    "Client Devices": ["operations", "technology"],
    "Collaboration": ["applications", "operations", "technology"],
    "Print / MPS": ["operations", "finance"],
    "Endpoint Security": ["risk", "governance", "compliance", "infrastructure"],
    "Device Management": ["operations", "technology"],
}


# HP_ABX_v3_final: "typically 5-10 when evidence supports that many".
# The count stays evidence-led, so fewer than five is still valid.
MAX_OBJECTIONS = 10

# The spec's exact wording when no official HP proof point can be sourced.
# No HP proof-point corpus is supplied to this system, so this is what shows.
# Client ruling, 24 Sep: when there is nothing to show, leave the section out
# and write nothing. Set to None rather than deleted, so the field still exists
# for anything reading the payload and the wording returns by restoring the
# string if the client changes position (the decision is still with Sahaj).
NO_PROOF_POINT = None


# Bump when the objection prompt changes so cached output is regenerated.
# 6 - cards now carry an HP case study as their proof point, so a cached card
#     from before the corpus existed must be rebuilt rather than reused.
# 7 - the case study a card reaches is now chosen by computed offering rather
#     than HP's product tag, which reaches studies the tag hid entirely.
# 8 - no customer is cited on two cards in the same playbook.
# 9 - nor on a card another feature already cites, where the corpus has an
#     equally good alternative.
# 10 - the reframe's HP claim now comes from the HP 220 Account Rulebook
#      instead of the model's own knowledge of HP, so every cached card was
#      written under the looser rule and must be rebuilt.
# 11 - contact records no longer feed the rulebook match, and an integration
#      claim must name an integration the approved facts state. Both changed
#      what the prompt is given, so version 10 cards were written under
#      different constraints.
# 12 - the rulebook is matched against the account's whole research corpus
#      (`rb.EVIDENCE_DATASETS`) rather than this feature's three grounding
#      datasets, which held 39 cells and found almost nothing.
# 13 - a reframe may no longer name this system's own research ("visible in
#      your technographics data" was reaching the seller's mouth).
# 14 - the integration check reads the whole sentence. Parsing the verb's
#      object let "integrate seamlessly with" and "integrating with it" carry
#      an HP claim nothing approved, the second attributing it to HP material.
# 15 - case studies are ranked use-case first (the client's 25 Sep keys), so
#      the proof on an area card can change even when its evidence has not.
#      The version moves with it or the cache serves the old card.
OBJECTION_PROMPT_VERSION = 15

# The dataset key used everywhere in evidence, prompts and UI. Never the Source A
# sheet name - the application speaks in dataset keys.
TECHNOGRAPHICS_DATASET_KEY = "technographics"

# The catch-all column. Category columns are a subset of it, so both are read.
FULL_STACK_COLUMN = "Full Tech Stack"

NL = chr(10)


# Sector words drawn from an account's own Business Description. They pass the
# grounding check - they really are in the data - but nothing in the evidence
# links a sector to a device, security or print need, so using one as
# justification is an unsupported inference rather than a sourced fact.
SECTOR_WORDS = [
    "automotive", "financial services", "heavy equipment", "mining", "construction",
    "energy", "agriculture", "agribusiness", "infrastructure", "logistics",
    "property development", "plantations", "forestry", "banking", "insurance",
    "toll road", "palm oil", "coal",
]


def _sector_terms_used(text: str, business_description: str) -> list[str]:
    """Sector words present in BOTH the generated prose and this account's own
    description - i.e. a sector being leaned on as justification."""
    t = " ".join(str(text or "").split()).lower()
    bd = " ".join(str(business_description or "").split()).lower()
    return sorted({w for w in SECTOR_WORDS if w in t and w in bd})


def _norm_objection(text: str) -> str:
    """Case- and whitespace-insensitive form, for spotting two objections that
    differ only in wording."""
    return " ".join(str(text or "").split()).lower().strip('"“”')


def _token_present(token: str, text: str) -> bool:
    """Word-boundary containment. A plain substring test matches 'it' inside
    'quality' and 'digital', which produces nonsense owners and vendors."""
    if not token or not text:
        return False
    return re.search(r"(?<![a-z0-9])" + re.escape(token.lower()) + r"(?![a-z0-9])",
                     text.lower()) is not None

def _read_dataset_records(account_id: str, dataset_key: str) -> list[dict]:
    """Rows for one dataset. Shared implementation - see datasets.py.

    Non-strict: requires_local_datasets on the entry point below has already
    established that this account's files are present, so a miss here means the
    dataset simply is not registered for this account.
    """
    return read_dataset_records(account_id, dataset_key, strict=False)

def _build_area_evidence(techno_row: dict) -> list[dict]:
    """One entry per HP contest area, carrying the verbatim technographics cells
    that speak to it and the vendors detected in them.

    An area with no detected vendor is kept, flagged `not_in_technographics`.
    That flag means only that this export does not name one - never that the
    account has no such vendor, capability or process."""
    full_stack = [v.strip() for v in
                  str(techno_row.get(FULL_STACK_COLUMN) or "").split(",") if v.strip()]

    areas = []
    for area, columns in AREA_CATEGORY_COLUMNS.items():
        tokens = AREA_PRIMARY_TOKENS.get(area, [])
        context_tokens = AREA_CONTEXT_TOKENS.get(area, [])
        cells, detected, seen = [], [], set()

        # The category columns say WHERE a vendor was detected.
        for col in columns:
            raw = str(techno_row.get(col) or "").strip()
            if not raw:
                continue
            values = [v.strip() for v in raw.split(",") if v.strip()]
            hits = [v for v in values
                    if any(_token_present(t, v) for t in tokens) and v not in seen]
            if hits:
                cells.append({"column": col, "values": hits})
            for v in hits:
                seen.add(v)
                detected.append(v)

        # Full Tech Stack is a superset of the category columns - several vendors
        # appear only there, so it is scanned too rather than silently missed.
        stack_only = [v for v in full_stack
                      if any(_token_present(t, v) for t in tokens) and v not in seen]
        if stack_only:
            cells.append({"column": FULL_STACK_COLUMN, "values": stack_only})
            for v in stack_only:
                seen.add(v)
                detected.append(v)

        # Adjacent technologies: shown, but they cannot carry the objection.
        context_detected = []
        if context_tokens:
            pool = list(full_stack)
            for col in columns:
                raw = str(techno_row.get(col) or "").strip()
                pool.extend(v.strip() for v in raw.split(",") if v.strip())
            for v in pool:
                if v in seen or v in context_detected:
                    continue
                if any(_token_present(t, v) for t in context_tokens):
                    context_detected.append(v)

        if detected:
            parts = [c["column"] + ": " + ", ".join(c["values"]) for c in cells]
            evidence = TECHNOGRAPHICS_DATASET_KEY + " -> " + area + " | " + " | ".join(parts)
            if context_detected:
                evidence += " | supporting context: " + ", ".join(context_detected)
        else:
            evidence = (TECHNOGRAPHICS_DATASET_KEY + " -> " + area
                        + ": no vendor for this area appears in this account's"
                        + " technographics evidence")

        areas.append({
            "area": area,
            "columns": [c["column"] for c in cells],
            "cells": cells,
            "detected_vendors": detected,
            "context_vendors": context_detected,
            "not_in_technographics": not detected,
            "evidence": evidence,
        })
    return areas


def _resolve_likely_raiser(area: str, contacts: list[dict]) -> tuple[str, str]:
    """A real title from the account's own contacts where one plausibly owns the
    area, else the area name itself. Returns (raiser, source)."""
    dept_targets = AREA_OWNER_DEPARTMENTS.get(area, [])
    strong_tokens = AREA_OWNER_STRONG_TOKENS.get(area, [])

    best = None
    for row in contacts:
        title = resolve_field(row, ["Prospect job_title", "apollo_title"]) or ""
        dept_raw = resolve_field(row, ["Prospect job_department_main", "apollo_department"])
        dept = normalize_department(dept_raw)

        matched = [t for t in strong_tokens if _token_present(t, title)]
        if not matched:
            # A weak or department-only match is the nearest technically adjacent
            # person, not the owner of this subject. Naming them would overstate.
            continue
        rank = len(matched) + (1 if dept in dept_targets else 0)
        if best is None or rank > best[0]:
            best = (rank, title.strip(), matched[0])

    if best and best[1]:
        return best[1], "prospect_contacts"
    return area, "hp_contest_area"


# How many rules one area may draw approved claims from. The model is being
# given text to choose between, not a catalogue to summarise, and five rules of
# eight facts each would bury the objection it is meant to answer.
MAX_RULES_PER_AREA = 3

# And how many facts from any one rule. CARE 01 alone carries eight.
MAX_FACTS_PER_RULE = 4


def _area_families(area: str) -> frozenset:
    """The rulebook families whose rules may answer an objection in this area.

    Derived, not typed out again. Two maps already exist and both are
    maintained: `rulebook.RULEBOOK_FAMILY_TO_HP_LINE` says which HP line a
    family speaks for, and `case_studies.HP_LINE_TO_LINES` and `AREA_TO_LINES`
    resolve an HP line and an area to the same canonical vocabulary. Chaining
    them means a family added to the rulebook reaches the right areas without a
    seventh hand-typed copy of the taxonomy drifting out of step with the other
    six.
    """
    wanted = set(cs.lines_for_area(area))
    if not wanted:
        return frozenset()
    return frozenset(
        family for family, hp_line in rb.RULEBOOK_FAMILY_TO_HP_LINE.items()
        if set(cs.lines_for_hp_line(hp_line) or ()) & wanted)


def _rulebook_claims(db, corpus: list, areas: list[dict],
                     country: str, now=None) -> dict:
    """The HP claims each area's reframe is allowed to make, per the rulebook.

    Until this existed the reframe was the one place in this feature where HP
    was described from the model's own knowledge: the prompt handed it six HP
    line names and asked for "the concrete angle", and whatever it then said
    about HP was unverified. The account side has always been grounded - rule 1
    of the prompt, `check_text`, `_sector_terms_used` - so the HP side was the
    remaining gap.

    This closes it the way `recommendations.py` and the Opportunity Map already
    do. The rules are matched against the ACCOUNT's evidence (C 01 - HP material
    cannot prove the account has a problem), then filtered to the families that
    speak for this area's HP line, and only their `allowed_facts` may be stated.

    An area with no matched rule returns nothing, and the prompt then forbids a
    capability claim there rather than inventing one. That is C 07: "leave out
    the recommendation ... Do not force a match."
    """
    book = rb.load(db)
    if not book.get("rules"):
        return {}

    matches = rb.candidates(book, corpus, rb.route(book, corpus), country)
    claims = {}
    for area in areas:
        families = _area_families(area["area"])
        if not families:
            continue
        hits = [m for m in matches if m["family"] in families][:MAX_RULES_PER_AREA]
        if not hits:
            continue
        rules = []
        for match in hits:
            # The same guardrail pipeline every other rulebook consumer uses,
            # rather than the rule's raw facts: it is what applies C 14 market
            # availability, C 16 confidentiality and the competitor block, and
            # a fact those withhold must not reach a prompt.
            approved, rejected = approve_rulebook_facts(
                match["rule"], country, now)
            facts = [d.as_dict() for d in approved][:MAX_FACTS_PER_RULE]
            if not facts:
                continue
            rules.append({
                "rule_label": match["rule_label"],
                "offering": match["offering"],
                "hp_line": rb.RULEBOOK_FAMILY_TO_HP_LINE.get(match["family"]),
                "approved_facts": facts,
                "withheld": summarise(rejected),
                "prohibitions": [str(x) for x in
                                 (match["rule"].get("prohibitions") or [])],
                "matched_terms": (match.get("qualifying_terms")
                                  or match["matched_terms"]),
            })
        if rules:
            claims[area["area"]] = rules
    return claims


# Our words for our own research. A reframe is the sentence a seller says out
# loud, and "we cannot see a print vendor in your technographics" tells a buyer
# what our data does not contain - which is our gap to close, not their problem
# to hear about.
_INTERNAL_VOCABULARY = (
    "technographic", "firmographic", "the dataset", "our dataset",
    "our records", "our data", "the evidence shows", "evidence block",
)


# A claim that HP connects to something, anywhere in a sentence.
#
# Parsing the target out of the verb was tried and is not enough. "WXP
# integrates with ManageEngine" was caught; "Poly integrate SEAMLESSLY with
# Microsoft Teams" slipped past an adverb, and "WXP can complement your existing
# ManageEngine setup by integrating with IT, as noted in the supplied HP
# material" slipped past a pronoun - and that one also attributed the invented
# claim to HP. So the test is applied to the whole sentence: if it claims a
# connection and names a product HP's approved facts never name, the connection
# is to something HP did not say it connects to.
_INTEGRATION_VERB_RE = re.compile(
    r"\b(integrat\w*|interoperat\w*|work[s]?\s+with|connect[s]?\s+(to|into)|"
    r"plug[s]?\s+into|native\s+support\s+for|compatible\s+with)\b", re.I)

# A product name: capitalised, or ALLCAPS, and more than one letter.
_PROPER_NOUN_RE = re.compile(r"\b([A-Z][A-Za-z0-9]+(?:\s+[A-Z][A-Za-z0-9]+)*)\b")

# Never treated as a product HP must have named: HP's own name, and the words
# that begin a sentence or label a platform generically.
_NOT_A_PRODUCT = frozenset((
    "hp", "it", "this", "these", "the", "our", "your", "their", "we", "us",
    "windows", "pc", "pcs", "ai", "os", "and", "but", "however", "exploring",
    "understanding", "its",
    # HP's own brands and sub-brands. The question this check asks is what HP
    # claims to connect TO; HP naming its own product is not that claim, and
    # flagging "HP WXP integrates with Microsoft Intune" for saying "WXP" would
    # refuse the approved sentence along with the invented one.
    "poly", "wolf", "wxp", "anyware", "daas", "elitebook", "probook", "zbook",
    "elitedesk", "prodesk", "elite", "pro", "workpath", "sure", "admin",
    "tamper", "lock", "troy", "micr", "mps", "iq", "care", "pack",
))


def _named_products(text: str, company_name: str = "",
                    own_names: str = "") -> set:
    """Products a sentence names, excluding HP, the account and sentence-starts."""
    skip = set(_NOT_A_PRODUCT)
    for source in (company_name, own_names):
        for word in str(source or "").replace("/", " ").split():
            skip.add(word.strip(",.()").lower())
    found = set()
    for phrase in _PROPER_NOUN_RE.findall(text):
        for word in phrase.split():
            if word.lower() not in skip and len(word) > 1:
                found.add(word)
    return found


def _claim_provenance(rules: list) -> dict:
    """What a card says about where its HP claim came from.

    Shown rather than kept internal: a seller repeating a claim to a customer
    should be able to see which rule of HP's own rulebook stands behind it, and
    an area with no rule should say so instead of leaving the reader to assume
    one exists.
    """
    if not rules:
        return {
            "hp_claim_source": None,
            "hp_claim_rules": [],
            "hp_claim_note": ("No HP rulebook offering matches this area's "
                              "evidence, so the reframe makes no HP capability "
                              "claim."),
        }
    return {
        "hp_claim_source": "rulebook",
        "hp_claim_rules": [{"rule_label": r["rule_label"],
                            "offering": r["offering"],
                            "hp_line": r["hp_line"],
                            "matched_terms": r["matched_terms"],
                            "approved_facts": r["approved_facts"],
                            "withheld": r["withheld"]}
                           for r in rules],
        "hp_claim_note": None,
    }


def _claim_faults(reframe: str, rules: list, country: str,
                 company_name: str = "") -> list:
    """Why this reframe may not be published as written.

    Two checks, both reusing machinery the rulebook path already owns rather
    than inventing a policy for this feature.

    `prose_guardrail_faults` is G 15 and G 16 - the AI-PC class definition and a
    product generation the approved facts never state. It is the same gate
    `recommendations.py` runs on generated product prose.

    The superlative check extends guardrail 2 from the facts to the sentence.
    `approve_rulebook_facts` already withholds a restricted superlative FACT in
    the countries that restrict them; without this, the model could withhold
    nothing and simply write its own superlative instead, which is the same
    claim arriving by a different route.
    """
    facts = [f for rule in rules for f in rule["approved_facts"]]
    faults = list(prose_guardrail_faults(reframe, facts))

    leaked = sorted({w for w in _INTERNAL_VOCABULARY if w in reframe.lower()})
    if leaked:
        faults.append(
            "internal vocabulary: says %s, which names this system's own data "
            "rather than anything the buyer would recognise"
            % ", ".join(repr(w) for w in leaked))

    own_names = " ".join(str(r.get("offering") or "") + " "
                         + str(r.get("hp_line") or "") for r in rules)
    sourced_text = " ".join(str(f.get("text") or "") + " "
                            + " ".join(f.get("conditions") or [])
                            for f in facts)
    for sentence in re.split(r"(?<=[.;])\s+", reframe):
        if not _INTEGRATION_VERB_RE.search(sentence):
            continue
        unnamed = sorted(p for p in _named_products(sentence, company_name,
                                                    own_names)
                         if p.lower() not in sourced_text.lower())
        if unnamed:
            faults.append(
                "C 03 integration: claims HP connects to %s, which no approved "
                "fact names" % ", ".join(unnamed))
            break

    if country in SUPERLATIVE_BLOCK_COUNTRIES:
        sourced = " ".join(str(f.get("text") or "") for f in facts)
        for hit in {m.group(0) for m in SUPERLATIVE_RE.finditer(reframe)}:
            if hit.lower() not in sourced.lower():
                faults.append(
                    "G2 restricted superlative: says %r, which no approved fact "
                    "states and which %s restricts" % (hit, country))
                break
    return faults


def _claims_block(rules: list) -> str:
    """One area's approved claims, as the prompt sees them."""
    lines = []
    for rule in rules:
        lines.append("    * " + (rule["hp_line"] or "HP") + " - "
                     + (rule["offering"] or "") + " [" + rule["rule_label"] + "]")
        for fact in rule["approved_facts"]:
            text = str(fact.get("text") or "").strip()
            if not text:
                continue
            # A qualified fact travels with its qualifier. C 03 is "use exact
            # facts", and a figure separated from the condition it holds under
            # is no longer the fact the rulebook approved.
            for extra in (fact.get("qualifiers") or []) + (fact.get("conditions") or []):
                extra = str(extra or "").strip()
                if extra and extra.lower() not in text.lower():
                    text += " (" + extra + ")"
            lines.append("        may say: " + text)
        for ban in rule["prohibitions"]:
            lines.append("        MUST NOT say: " + ban)
    return NL.join(lines)


def _evidence_fingerprint(areas: list[dict], business_description: str,
                          case_studies_version: str = "",
                          rulebook_version: str = "") -> str:
    basis = sorted(
        [{"a": a["area"], "e": a["evidence"], "r": a.get("likely_raiser", "")} for a in areas],
        key=lambda x: x["a"],
    )
    payload = {
        "prompt_version": OBJECTION_PROMPT_VERSION,
        "areas": basis,
        "business_description": business_description,
        # A card stores its proof point, so reloading the case-study corpus has
        # to rebuild the cards that cite it. The account's own evidence does not
        # change when HP's corpus is corrected.
        "case_studies_version": case_studies_version,
        # A card stores the rulebook claims its reframe was written from, so a
        # reloaded rulebook has to rebuild the cards that lean on it.
        "rulebook_version": rulebook_version,
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()


def generate_objection_cards(account_id: str, areas: list[dict],
                             company_name: str, business_description: str,
                             industry: str = "") -> dict | None:
    """One cached GPT-4o call. The model writes only the objection, the reframe
    and the counter question. The evidence, the vendor list, the area and the
    likely raiser are owned by Python and are never sent back for rewriting."""
    db = get_db()
    now = datetime.now(UTC)
    fingerprint = _evidence_fingerprint(areas, business_description,
                                        cs.knowledge_version(db),
                                        rb.knowledge_version(db))

    existing = db["account_widgets"].find_one({
        "account_id": account_id,
        "widget_key": "objection_reframe_cards",
    })
    if (existing and existing.get("status") == "available"
            and existing.get("data", {}).get("evidence_fingerprint") == fingerprint):
        return existing

    # Grounding corpus: the datasets this feature reasons over.
    records = {k: _read_dataset_records(account_id, k) for k in
               ("technographics", "firmographics", "prospect_contacts")}
    ground = build_corpus(records)

    # The same cells again, as the rulebook matcher wants them. Built from the
    # records already read rather than through a second read, so the claims an
    # area may make and the evidence its card is checked against cannot come
    # from different snapshots of the account.
    # The rulebook is matched against the account's whole research corpus, not
    # just the three datasets this feature grounds its prose against. Those
    # three hold 39 cells for this account and the full corpus holds thousands;
    # matching on the narrow set meant four of five areas found no HP offering
    # that the same evidence plainly supports elsewhere in the product.
    #
    # `rb.EVIDENCE_DATASETS` is the shared definition, so the Opportunity Map,
    # the Technographic Map and this feature all answer from the same evidence.
    rb_corpus = rb.account_evidence(account_id)
    country = rb.account_country(account_id)

    try:
        claims_by_area = _rulebook_claims(db, rb_corpus, areas, country, now)
    except Exception:
        # A rulebook that is missing or half-loaded must not take the playbook
        # down with it. The cards then carry no approved claim, and the prompt
        # below forbids a capability claim rather than inventing one.
        logger.exception("objection playbook: rulebook claims unavailable")
        claims_by_area = {}
    report = GroundingReport(ground, ["objection", "reframe", "counter_question"])

    # One HP case study per area, chosen by Python before the model is called.
    #
    # The model never writes this and is never told it exists: rule 1 of the
    # prompt below forbids naming a customer that is not in the area's own
    # evidence, which is correct for prose it invents and would rule out every
    # case study. So the proof point is attached afterwards, the way
    # `likely_raiser` and the evidence already are.
    #
    # It is also kept out of `check_text` further down. That gate verifies
    # against the ACCOUNT's technographics and drops the whole card on a miss -
    # a case study's customer name and figures are not in this account's data,
    # so routing them through it would delete the card they exist to support.
    # They were verified at load time against their own source instead.
    # No customer appears on two cards. Client Devices and Device Management
    # both reach the device-services line, so without this the same university
    # was cited twice in one playbook - which reads as a bug to a seller and
    # spends two slots on one story. Areas are served in the order they arrive,
    # which is the fixed order of `AREA_CATEGORY_COLUMNS`; a later card takes
    # its next-best unused study, or none, rather than repeating an earlier one.
    # No customer appears twice - not on two cards here, and not on a card that
    # another feature already cites. Client Devices and Device Management both
    # reach the device-services line, and the Opportunity Map reaches it too, so
    # without this one university was cited three times across the account.
    #
    # The Objection Playbook chooses FIRST (see `cs.SURFACE_ORDER`): its five
    # areas are fixed and land on the thinnest lines in the corpus, so it has
    # the least room to move. `cited_above` is therefore empty for it today -
    # it is passed anyway, so that adding a surface above it needs no change
    # here.
    corpus_industry = cs.normalise_industry(industry)
    elsewhere = cs.cited_above(db, account_id, cs.SURFACE_OBJECTIONS)
    here: set = set()
    proof_by_area = {}
    for area in areas:
        point = cs.allocate(db, cs.lines_for_area(area["area"]),
                            industry=corpus_industry,
                            # Key 1 of the client's ranking: the use case the
                            # area is about, ahead of industry.
                            signals=cs.signals_for_opportunity(area["area"]),
                            taken=elsewhere, used_here=here)
        proof_by_area[area["area"]] = point
        if point and point.get("study_id"):
            here.add(point["study_id"])

    roster = []
    for a in areas:
        state = ("NO VENDOR DETECTED IN THE TECHNOGRAPHICS EVIDENCE"
                 if a["not_in_technographics"]
                 else "vendors detected: " + ", ".join(a["detected_vendors"]))
        rules = claims_by_area.get(a["area"]) or []
        approved = (NL + "    APPROVED HP CLAIMS for this area - the only "
                         "things you may assert about HP here:" + NL
                    + _claims_block(rules)) if rules else (
            NL + "    APPROVED HP CLAIMS for this area: NONE. The rulebook "
                 "connects no HP offering to the evidence in this area, so you "
                 "may name an HP line but MUST NOT state any capability, "
                 "benefit, saving or figure for it.")
        roster.append(
            "- area=" + a["area"] + " | " + state + NL
            + "    evidence (verbatim, do not rewrite): " + a["evidence"] + NL
            + "    topic owner at this account: " + a["likely_raiser"]
            + approved
        )

    system_prompt = (
"You are an HP enterprise sales strategist preparing a seller to meet " + company_name + "." + NL + NL
+ "ABOUT THE ACCOUNT (from its firmographics record):" + NL
+ (business_description or "No business description supplied.") + NL + NL
+ "HP competes in these areas: client devices, collaboration hardware (Poly), print and "
  "managed print services, endpoint security (HP Wolf Security), device management, and the "
  "device services that attach to them. Which HP offering applies to an area is not for you "
  "to decide - each area block below carries the offerings HP's rulebook connects to that "
  "area's evidence, and those are the ones to use." + NL + NL
+ "EVIDENCE - one block per area, drawn from this account's technographics dataset:" + NL
+ NL.join(roster) + NL + NL
+ "WRITE, FOR EACH AREA, one objection card." + NL + NL
+ "WHAT AN OBJECTION IS HERE:" + NL
+ "An objection is a HYPOTHETICAL. It is push-back a buyer working in that area MIGHT raise, "
  "that the seller should be ready for. It is NOT something anyone at " + company_name + " has said. "
  "Never write it as reported speech. Never attribute it to the topic owner or any person. "
  "Never imply it has been raised. The topic owner is given only so the seller knows who tends "
  "to own that subject - treat them as the audience, not the speaker." + NL + NL
+ "PRIMARY vs SUPPORTING CONTEXT: each area's evidence line lists the technologies that ARE that area, and may then list 'supporting context' - adjacent products that sit beside it without performing its function. Build the objection and the reframe on the PRIMARY technologies only. You may acknowledge context, but never write as though a context product performs the area's job: multi-factor authentication is not device management, and a network firewall is not endpoint protection." + NL + NL+ "RULES ON EVIDENCE:" + NL
+ "1. Never introduce a vendor, product, number, customer or event that is not in that area's own "
  "evidence block above. If a vendor is not listed there, it does not exist for the purposes of this card." + NL
+ "2. An objection must be answerable from that area's own evidence. If no PC vendor is listed, do NOT "
  "write a 'we already standardised on Dell/Lenovo' objection - there is nothing to support it." + NL
+ "3. WHERE NO VENDOR WAS DETECTED: this means only that the technographics evidence does not name one. "
  "It does NOT mean the account has no such vendor, no such process, or an open field. You MUST NOT write "
  "'they have no incumbent', 'there is no standard', 'the field is open', 'greenfield', or any equivalent "
  "claim about the account. Frame it as a visibility gap - the evidence does not show one, and a vendor may "
  "well exist undetected - and make the counter question one that FINDS OUT who owns that decision today." + NL
+ "4. Never rewrite, paraphrase or tidy the evidence string. You are reading it, not editing it." + NL
+ "6. HP CLAIMS. Everything you assert about what HP does, provides, includes or improves "
  "must come from that area's APPROVED HP CLAIMS block. Those sentences are HP's own approved "
  "wording; you may compress or rephrase one to fit the reframe, but you may not add a "
  "capability, a benefit, a comparison, a saving or a figure that is not in them. Where the "
  "block says NONE, name the HP line and stop there - answer the objection from the account's "
  "own evidence and let the counter question do the work. Anything marked MUST NOT say is a "
  "hard ban. Inventing an HP capability is the one failure that reaches a customer as HP's "
  "own word, so it is worse than a thin card." + NL
+ "5. The account description above lists the sectors this business operates in. Do NOT use a sector name as justification for a device, security, collaboration or print need - nothing in the evidence links a sector to a technology requirement. Write \"across the account's diverse business units\" instead of naming mining, financial services, heavy equipment or any other sector as a reason." + NL + NL
+ "FIELDS:" + NL
+ '- "objection": the anticipated push-back, in a buyer\'s own words, in quotes. One sentence. '
  "It must be something a busy buyer would actually say to get rid of a seller - a brush-off, a "
  "budget line, a we-already-have-this. NEVER write the buyer confessing ignorance or a lack of "
  "visibility about their own estate; that is our evidence gap, not theirs, and putting it in "
  "their mouth is wrong. For an area with no vendor detected, the realistic objection is the "
  "buyer DEPRIORITISING the topic - 'there is no RFP open for that', 'that is handled', 'why "
  "are we even discussing this' - not the buyer admitting they do not know." + NL
+ '- "reframe": the seller\'s answer. Two sentences at most, and it must do BOTH of these: '
  "name the HP line that applies AND give the concrete angle for this account, tied to a "
  "vendor or fact in that area's evidence. A reframe that names no HP line is a FAILED "
  "answer. Take the HP line, and everything you assert about it, from that area's APPROVED "
  "HP CLAIMS block - see the rule on HP claims below." + NL
+ '- "counter_question": one question the seller can ask next that advances the conversation.' + NL
+ '- "why_expected": one sentence on why THIS account would raise this, tied to its own evidence above. Not a general statement about buyers.' + NL
+ '- "recommended_next_step": the concrete next action for the seller after the counter question - a meeting, a discovery item, a thing to confirm. One short sentence.' + NL + NL
+ "STYLE - these are hard bans, and a card that breaks them is a failed answer:" + NL
+ "- Do NOT open the reframe by complimenting or validating the buyer. No 'It is great that you', "
  "'It is excellent that you', 'It is clear that you have invested', 'It is understandable that'. "
  "Start with the substance." + NL
+ "- Do NOT use the concessive template '<praise> ... However, <vague upside>'. Every one of your "
  "reframes must have a different shape from the others." + NL
+ "- Do NOT write filler abstractions: 'as threats evolve', 'optimise performance', 'uncover "
  "opportunities', 'drive efficiencies', 'streamline', 'best possible experience'. Say the "
  "specific thing about THIS account instead." + NL
+ "- Write as one seasoned seller briefing another, not as marketing copy." + NL
+ "- NEVER name this system's own data in the prose. Words like \"technographics\", "
  "\"firmographics\", \"the dataset\", \"the evidence\" and \"our records\" are how WE "
  "describe our research; a seller saying them to a buyer is telling the buyer what we "
  "do and do not know about them. Say \"what we can see of your estate\" or simply "
  "write the sentence without the reference." + NL + NL
+ "Return one entry per supplied area, using the area name exactly as given." + NL + NL
+ "Output JSON:" + NL
+ '{ "cards": [ { "area": "<area name exactly as supplied>", "objection": "...", '
  '"reframe": "...", "counter_question": "...", "why_expected": "...", '
  '"recommended_next_step": "..." } ] }' + NL
    )

    user_prompt = (
        "Write one objection card for each of the " + str(len(areas)) + " areas supplied, for "
        + company_name + ". Return JSON matching the schema."
    )

    rejected_sectors: list[str] = []
    rejected_claims: list[str] = []

    llm_res = generate_gpt4o_json_completion(system_prompt, user_prompt)

    by_area = {a["area"]: a for a in areas}
    cards = []
    if llm_res and isinstance(llm_res, dict) and isinstance(llm_res.get("cards"), list):
        for entry in llm_res["cards"]:
            if not isinstance(entry, dict):
                continue
            area = str(entry.get("area") or "").strip()
            src_area = by_area.get(area)
            if not src_area:
                continue
            objection = str(entry.get("objection") or "").strip()
            reframe = str(entry.get("reframe") or "").strip()
            counter = str(entry.get("counter_question") or "").strip()
            if not (objection and reframe and counter):
                continue

            sectors = _sector_terms_used(reframe + " " + counter, business_description)
            if sectors:
                # Grounded but unsupported: the sector is real, the link from
                # sector to technology need is not.
                rejected_sectors.append(f"{area}: {', '.join(sectors)}")
                continue

            bad_nums, bad_urls = check_text(ground, report, area,
                                            objection, reframe, counter)
            if bad_nums or bad_urls:
                # A figure or link the technographics never carried has no place
                # in a card that is meant to be evidence-led.
                continue

            faults = _claim_faults(reframe, claims_by_area.get(area) or [],
                                   country, company_name)
            if faults:
                # An HP claim the rulebook does not support reaches a customer
                # as HP's own word. Retried rather than dropped, so the area
                # keeps a card.
                rejected_claims.append("%s: %s" % (area, "; ".join(faults)))
                continue
            cards.append({
                "card_id": hashlib.sha1(area.encode("utf-8")).hexdigest()[:12],
                "area": area,
                "objection": objection,
                "reframe": reframe,
                "counter_question": counter,
                "why_expected": str(entry.get("why_expected") or "").strip() or None,
                "recommended_next_step": str(entry.get("recommended_next_step") or "").strip() or None,
                # No HP proof-point corpus is supplied to this system, so the
                # spec's empty state is shown rather than an unrelated case study.
                "hp_proof_point": (proof_by_area.get(area) or {}).get("text"),
                "hp_proof_point_note": (None if proof_by_area.get(area)
                                        else NO_PROOF_POINT),
                "hp_proof_point_detail": proof_by_area.get(area),
                **_claim_provenance(claims_by_area.get(area) or []),
                # technographics carries no link, date or confidence column, so
                # these are recorded as absent rather than invented.
                "evidence_source_link": None,
                "evidence_date": None,
                "evidence_confidence": None,
                # Python-owned, never model-supplied.
                "evidence": src_area["evidence"],
                "evidence_columns": src_area["columns"],
                "detected_vendors": src_area["detected_vendors"],
                "context_vendors": src_area.get("context_vendors", []),
                "not_in_technographics": src_area["not_in_technographics"],
                "likely_raiser": src_area["likely_raiser"],
                "likely_raiser_source": src_area["likely_raiser_source"],
            })

    if rejected_sectors or rejected_claims:
        logger.warning("objection playbook: retrying %d sector rejection(s) and "
                       "%d HP-claim rejection(s): %s", len(rejected_sectors),
                       len(rejected_claims), rejected_sectors + rejected_claims)
        why = []
        if rejected_sectors:
            why.append(
                "These cards used a business sector as justification for a technology "
                "need: " + "; ".join(rejected_sectors) + "." + NL
                + "A sector is not evidence of a technology requirement. Rewrite those "
                  "cards without naming any sector - say \"across the account's diverse "
                  "business units\".")
        if rejected_claims:
            why.append(
                "These cards made an HP claim the rulebook does not support: "
                + "; ".join(rejected_claims) + "." + NL
                + "Rewrite the reframe using ONLY that area's APPROVED HP CLAIMS, or "
                  "name the HP line and make no capability claim at all.")
        retry_system = system_prompt + (
            NL + NL + "RETRY - REJECTED." + NL + NL.join(why) + NL
            + "Return the COMPLETE card object for each."
        )
        retry_areas = sorted({s.split(":")[0]
                              for s in rejected_sectors + rejected_claims})
        retry_user = ("Return JSON containing only these areas: "
                      + ", ".join(retry_areas) + ".")
        rejected_sectors = []
        retry_res = generate_gpt4o_json_completion(retry_system, retry_user)
        if retry_res and isinstance(retry_res, dict) and isinstance(retry_res.get("cards"), list):
            have = {c["area"] for c in cards}
            for entry in retry_res["cards"]:
                if not isinstance(entry, dict):
                    continue
                area = str(entry.get("area") or "").strip()
                src_area = by_area.get(area)
                if not src_area or area in have:
                    continue
                objection = str(entry.get("objection") or "").strip()
                reframe = str(entry.get("reframe") or "").strip()
                counter = str(entry.get("counter_question") or "").strip()
                if not (objection and reframe and counter):
                    continue
                if _sector_terms_used(reframe + " " + counter, business_description):
                    continue
                if any(check_text(ground, report, area, objection, reframe, counter)):
                    continue
                if _claim_faults(reframe, claims_by_area.get(area) or [], country, company_name):
                    # Twice is enough. The area keeps no card rather than one
                    # carrying an HP claim nothing approved.
                    continue
                cards.append({
                    "card_id": hashlib.sha1(area.encode("utf-8")).hexdigest()[:12],
                    "area": area,
                    "objection": objection,
                    "reframe": reframe,
                    "counter_question": counter,
                    "why_expected": str(entry.get("why_expected") or "").strip() or None,
                    "recommended_next_step": str(entry.get("recommended_next_step") or "").strip() or None,
                    "hp_proof_point": (proof_by_area.get(area) or {}).get("text"),
                    "hp_proof_point_note": (None if proof_by_area.get(area)
                                            else NO_PROOF_POINT),
                    "hp_proof_point_detail": proof_by_area.get(area),
                    **_claim_provenance(claims_by_area.get(area) or []),
                    "evidence_source_link": None,
                    "evidence_date": None,
                    "evidence_confidence": None,
                    "evidence": src_area["evidence"],
                    "evidence_columns": src_area["columns"],
                    "detected_vendors": src_area["detected_vendors"],
                    "context_vendors": src_area.get("context_vendors", []),
                    "not_in_technographics": src_area["not_in_technographics"],
                    "likely_raiser": src_area["likely_raiser"],
                    "likely_raiser_source": src_area["likely_raiser_source"],
                })

    # "If two objections differ only in wording, merge them and preserve
    # persona-specific variants inside one entry."
    merged: list[dict] = []
    for card in cards:
        canon = re.sub(r"[^a-z0-9 ]", "", _norm_objection(card["objection"]))
        twin = next((m for m in merged
                     if difflib.SequenceMatcher(None, canon, m["_canon"]).ratio() >= 0.85), None)
        if twin:
            twin.setdefault("variants", []).append({
                "area": card["area"],
                "objection": card["objection"],
                "likely_raiser": card["likely_raiser"],
            })
            continue
        card["_canon"] = canon
        merged.append(card)
    for m in merged:
        m.pop("_canon", None)
    cards = merged[:MAX_OBJECTIONS]

    if cards:
        return {
            "account_id": account_id,
            "feature_key": "objection_playbook",
            "widget_key": "objection_reframe_cards",
            "data_classification": "inferred",
            "status": "available",
            "data": {
                "evidence_fingerprint": fingerprint,
                "cards_count": len(cards),
                "cards": cards,
                "grounding_report": report.as_dict(),
                "disclaimer": ("Anticipated objections a seller should be ready for, generated "
                               "from this account's technographics evidence. Not statements made "
                               "by any contact."),
            },
            "source_datasets": ["technographics", "firmographics", "prospect_contacts"],
            "extracted_at": now,
            "updated_at": now,
        }

    if existing and existing.get("status") == "available":
        return existing
    return None


@requires_local_datasets(
    "firmographics", "prospect_contacts", "technographics",
)
def extract_objection_playbook(account_id: str) -> list[dict]:
    db = get_db()
    now = datetime.now(UTC)

    techno_records = _read_dataset_records(account_id, "technographics")
    firmo_records = _read_dataset_records(account_id, "firmographics")
    contact_records = _read_dataset_records(account_id, "prospect_contacts")

    account_doc = None
    if ObjectId.is_valid(account_id):
        account_doc = db["accounts"].find_one({"_id": ObjectId(account_id)})
    company_name = account_doc.get("name", "Target Account") if account_doc else "Target Account"

    results = []

    # 1. Widget: objection_incumbent_context (Deterministic)
    incumbent_techs = []
    active_categories = []

    if techno_records and len(techno_records) > 0:
        row = techno_records[0]
        raw_full = str(row.get("Full Tech Stack") or "").strip()
        if raw_full:
            incumbent_techs = [s.strip() for s in raw_full.split(",") if s.strip()]

        for col in TECHNOGRAPHICS_CATEGORY_COLUMNS:
            val = str(row.get(col) or "").strip()
            if val:
                active_categories.append(col)

    business_context = {}
    if firmo_records and len(firmo_records) > 0:
        f = firmo_records[0]

        # DEC-052: generated prose names the account the way the header does.
        c_name = account_display_name(account_id, f)
        domain_val = str(f.get("Company Domain") or f.get("company_domain") or f.get("Domain") or f.get("Website") or f.get("website") or "").strip()

        city = str(f.get("City Name") or f.get("city_name") or "").strip()
        region = str(f.get("Region Name") or f.get("region_name") or "").strip()
        country = str(f.get("Country Name") or f.get("country_name") or "").strip()
        loc_parts = [p for p in [city, region, country] if p]
        hq_loc_val = ", ".join(loc_parts) if loc_parts else str(f.get("HQ Location") or f.get("hq_location") or "").strip()

        linkedin_ind = str(f.get("Linkedin Industry Category") or f.get("linkedin_industry_category") or "").strip()
        naics = str(f.get("Naics Description") or f.get("naics_description") or "").strip()
        sic = str(f.get("Sic Code Description") or f.get("sic_code_description") or "").strip()
        ind_parts = [p for p in [linkedin_ind, naics, sic] if p]
        ind_val = " / ".join(list(dict.fromkeys(ind_parts))) if ind_parts else str(f.get("Industry Classification") or f.get("industry") or "").strip()

        emp_val = str(f.get("Number Of Employees Range") or f.get("employee_count_range") or f.get("Employee Count") or f.get("employee_count") or "").strip()
        rev_val = str(f.get("Yearly Revenue Range") or f.get("yearly_revenue_range") or f.get("Yearly Revenue") or f.get("revenue") or "").strip()

        business_context = {
            "business_description": str(f.get("Business Description")
                                        or f.get("business_description") or "").strip(),
            "company_name": c_name,
            "domain": domain_val,
            "industry_classification": ind_val,
            "hq_location": hq_loc_val,
            "employee_count": emp_val,
            "revenue": rev_val
        }

    # Per-area evidence, and who at this account owns each area. Both entirely
    # deterministic and both computed before any model call.
    area_evidence = []
    if techno_records:
        area_evidence = _build_area_evidence(techno_records[0])
        for a in area_evidence:
            raiser, raiser_source = _resolve_likely_raiser(a["area"], contact_records)
            a["likely_raiser"] = raiser
            a["likely_raiser_source"] = raiser_source

    if incumbent_techs or business_context:
        incumbent_payload = {
            "account_id": account_id,
            "feature_key": "objection_playbook",
            "widget_key": "objection_incumbent_context",
            "data_classification": "deterministic",
            "status": "available",
            "data": {
                "total_incumbents_count": len(incumbent_techs),
                "incumbent_technologies": incumbent_techs,
                "relevant_categories": active_categories,
                "business_context": business_context,
                "area_evidence": area_evidence
            },
            "source_datasets": ["technographics", "firmographics"],
            "extracted_at": now,
            "updated_at": now
        }
    else:
        incumbent_payload = {
            "account_id": account_id,
            "feature_key": "objection_playbook",
            "widget_key": "objection_incumbent_context",
            "data_classification": "deterministic",
            "status": "empty",
            "data": {},
            "source_datasets": ["technographics", "firmographics"],
            "extracted_at": now,
            "updated_at": now
        }

    db["account_widgets"].update_one(
        {"account_id": account_id, "widget_key": "objection_incumbent_context"},
        {"$set": incumbent_payload},
        upsert=True
    )
    results.append(incumbent_payload)

    # 2. Widget: objection_reframe_cards (Inferred). Cached on a fingerprint of
    #    the evidence set, so a page load costs no model call.
    reframe_payload = None
    if area_evidence:
        reframe_payload = generate_objection_cards(
            account_id,
            area_evidence,
            company_name,
            str(business_context.get("business_description") or "").strip(),
            str(business_context.get("industry_classification") or "").strip(),
        )

    if reframe_payload is None:
        reframe_payload = {
            "account_id": account_id,
            "feature_key": "objection_playbook",
            "widget_key": "objection_reframe_cards",
            "data_classification": "inferred",
            "status": "pending",
            "data": {
                "evidence_fingerprint": None,
                "cards_count": 0,
                "cards": [],
                "notice": ("Objection generation requires OPENAI_API_KEY. The incumbent "
                           "evidence below is shown as extracted; no objections are invented."),
            },
            "source_datasets": ["technographics", "firmographics", "prospect_contacts"],
            "extracted_at": now,
            "updated_at": now
        }

    db["account_widgets"].update_one(
        {"account_id": account_id, "widget_key": "objection_reframe_cards"},
        {"$set": reframe_payload},
        upsert=True
    )
    results.append(reframe_payload)

    return results
