"""The 17 mandatory RAG guardrails, enforced in Python.

From "Mandatory RAG Guardrails" in the HP rules document. The prompt is told
about these too, but the prompt is not what enforces them: every claim that
reaches a seller has passed through `approve_facts` below.

The governing sentence is guardrail 17: "If the system cannot verify the exact
product, country eligibility, configuration, competitor/model, benchmark
context, source date/version, or availability condition needed for a claim, do
not generate that claim."  So the default here is to drop, never to soften.

Country lists are constants rather than parsed from the decks. HP writes them
as run-on prose with inconsistent punctuation, and an early attempt to parse it
captured a 99,000-character blob. The lists below are the document's own, and
the extractor additionally records the countries each slide names so the two
can be cross-checked.
"""

import logging
import re
from datetime import UTC, datetime

logger = logging.getLogger(__name__)

# --- Guardrail 2: superlative claims -----------------------------------------
SUPERLATIVE_BLOCK_COUNTRIES = {
    "romania", "slovakia", "turkey", "united arab emirates", "uae", "russia",
    "armenia", "belarus", "kazakhstan", "kyrgyzstan", "moldova", "tajikistan",
    "turkmenistan", "ukraine", "uzbekistan", "china", "vietnam", "indonesia",
    "malaysia", "brazil", "mexico",
}

# --- Guardrails 3 and 4: the Lenovo competitive playbook ---------------------
COMPETITOR_BLOCK_COUNTRIES = {
    "romania", "turkmenistan", "russia", "turkey", "united arab emirates", "uae",
    "saudi arabia", "state of palestine", "egypt", "jordan", "lebanon",
    "syrian arab republic", "bahrain", "kuwait", "oman", "qatar", "yemen",
    "iran", "islamic republic of iran", "iraq", "nigeria", "ethiopia",
    "democratic republic of the congo", "south africa", "kenya", "sudan",
    "algeria", "uganda", "morocco", "mozambique", "ghana", "angola",
    "madagascar", "cameroon", "niger", "burkina faso", "mali", "malawi",
    "zambia", "senegal", "chad", "zimbabwe", "south sudan", "rwanda", "tunisia",
    "somalia", "guinea", "benin", "burundi", "togo", "eritrea", "sierra leone",
    "central african republic", "republic of the congo", "liberia", "mauritania",
    "namibia", "botswana", "gambia", "equatorial guinea", "lesotho", "gabon",
    "guinea-bissau", "mauritius", "eswatini", "swaziland", "djibouti", "reunion",
    "comoros", "cape verde", "western sahara", "mayotte",
    "sao tome and principe", "seychelles", "tanzania", "libya",
    "cote d'ivoire", "ivory coast", "french guiana", "french polynesia",
    "french southern territories", "guadeloupe", "guyana", "martinique",
    "new caledonia", "saint pierre and miquelon", "china", "vietnam",
    "indonesia", "malaysia", "brazil", "mexico",
    # CIS, stored as a market-level block per the document's instruction
    "kazakhstan", "kyrgyzstan", "moldova", "tajikistan", "belarus", "armenia",
    "ukraine", "uzbekistan",
}

# --- Guardrail 15: AI-PC classes ---------------------------------------------
NEXT_GEN_AI_PC_MIN_TOPS = 40
NEXT_GEN_AI_PC_MAX_TOPS = 60
_TOPS_RE = re.compile(r"(\d{1,3})\s*TOPS", re.I)

# --- Guardrails 6 / 7 / 8: qualifiers that must survive ----------------------
REQUIRED_QUALIFIER_TRIGGERS = [
    (re.compile(r"\b5G\b", re.I),
     re.compile(r"optional|module|configured at the factory|where supported|carrier", re.I),
     "5G requires an optional factory-configured module and carrier availability"),
    (re.compile(r"HP Go", re.I),
     re.compile(r"subscription|US\b|supported|requires", re.I),
     "HP Go is a US subscription service on supported configurations only"),
    (re.compile(r"Wi-?Fi\s*7", re.I),
     re.compile(r"requires|separately|supported|compatible", re.I),
     "Wi-Fi 7 requires a compatible system and a separately purchased router"),
    (re.compile(r"Sure View", re.I),
     re.compile(r"optional|where supported|select", re.I),
     "Sure View is optional"),
    (re.compile(r"RTX\s*5050|A1000|A400|RX6300", re.I),
     re.compile(r"optional|configur|where supported", re.I),
     "discrete graphics are configuration-dependent"),
    (re.compile(r"up to \d+ displays", re.I),
     re.compile(r"graphics|flex|required|setup|configur", re.I),
     "display counts depend on the stated graphics/flex-I/O configuration"),
]

# --- Guardrail 5: comparison claims need their benchmark ---------------------
# Wording that makes a claim a superlative, for guardrail 2. The deck path
# reads this from each slide's parsed restriction block; a rulebook fact has no
# such block, so the claim text itself is what is tested.
SUPERLATIVE_RE = re.compile(
    r"\b(world'?s|industry'?s|market'?s)\b|\b(most|best|first|only|fastest|"
    r"strongest|safest|leading)\b", re.I)

# Competitor names, for guardrails 3 and 4 on a rulebook fact.
COMPETITOR_RE = re.compile(
    r"\b(lenovo|thinkpad|dell|latitude|apple|macbook|asus|acer|huawei|"
    r"samsung|microsoft surface)\b", re.I)

COMPARISON_RE = re.compile(r"\b\d{1,3}\s*%|\bhigher\b|\bbetter\b|\bfaster\b|\bless\b", re.I)
BENCHMARK_RE = re.compile(r"cinebench|procyon|mobilemark|internal testing|"
                          r"benchmark|tested|spec sheet|data sheet", re.I)

# --- Guardrail 9: planned is not available -----------------------------------
FUTURE_RE = re.compile(r"\bplanned\b|\bexpected\b|\bfuture\b|\bwill be available\b|"
                       r"\bcoming\b|\blater this year\b", re.I)

_MONTHS = ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december"]
_EMBARGO_DATE_RE = re.compile(
    r"([A-Z][a-z]+)\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(\d{4})", re.I)


def normalize_country(location: str) -> str:
    """Last comma-separated component of an HQ string, lowercased."""
    parts = [p.strip().lower() for p in str(location or "").split(",") if p.strip()]
    return parts[-1] if parts else ""


def parse_embargo(raw: str):
    if not raw:
        return None
    m = _EMBARGO_DATE_RE.search(raw)
    if not m:
        return None
    month = m.group(1).lower()
    if month not in _MONTHS:
        return None
    try:
        return datetime(int(m.group(3)), _MONTHS.index(month) + 1, int(m.group(2)),
                        tzinfo=UTC)
    except ValueError:
        return None


def ai_pc_class(text: str):
    """Guardrail 15. Next Gen = 40-60 TOPS, AI PC = below 40, non-AI = no NPU."""
    hits = [int(n) for n in _TOPS_RE.findall(str(text or ""))]
    if not hits:
        return None
    top = max(hits)
    if NEXT_GEN_AI_PC_MIN_TOPS <= top <= NEXT_GEN_AI_PC_MAX_TOPS:
        return "Next Gen AI PC"
    if top < NEXT_GEN_AI_PC_MIN_TOPS:
        return "AI PC"
    return "AI PC"          # above the stated band: do not invent a new class


class FactDecision:
    """Why one claim was kept or dropped - stored so the output is auditable."""

    def __init__(self, claim, slide_id, kept, reason=None, guardrail=None):
        self.claim = claim
        self.slide_id = slide_id
        self.kept = kept
        self.reason = reason
        self.guardrail = guardrail

    def as_dict(self):
        out = {"slide_id": self.slide_id, "kept": self.kept}
        if self.kept:
            out["text"] = self.claim.get("text")
            out["qualifiers"] = self.claim.get("qualifiers") or []
            out["conditions"] = list((self.claim.get("footnotes") or {}).values())
        else:
            out["guardrail"] = self.guardrail
            out["reason"] = self.reason
        return out


# Model and generation tokens, for guardrail 16. Deliberately narrow: an
# earlier attempt also matched form-factor words like "desktop", and calling a
# tower a desktop is ordinary English rather than a mixed record.
_GENERATION_RE = re.compile(r"\bG[12][iaq]?8?\b")


def prose_guardrail_faults(text: str, facts: list) -> list:
    """Guardrails 15 and 16 on one generated sentence about a product.

    `facts` are that recommendation's own approved facts. Returns the reasons
    the sentence must not be published, or an empty list.
    """
    faults = []
    said = " ".join(str(text or "").split())
    if not said:
        return faults

    sourced = " ".join(str(f.get("text") or "") + " "
                       + " ".join(f.get("conditions") or []) for f in (facts or []))

    # G 15 - the classes are fixed by the document and a figure decides them.
    for match in re.finditer(r"next\s*gen\s*ai\s*pc", said, re.I):
        window = said[max(0, match.start() - 140):match.start() + 140]
        figures = [int(n) for n in _TOPS_RE.findall(window)]
        if figures and not any(NEXT_GEN_AI_PC_MIN_TOPS <= n <= NEXT_GEN_AI_PC_MAX_TOPS
                               for n in figures):
            faults.append(
                "G15 AI-PC class: calls a %s TOPS product a Next Gen AI PC, "
                "which the rulebook defines as %d-%d TOPS"
                % (figures, NEXT_GEN_AI_PC_MIN_TOPS, NEXT_GEN_AI_PC_MAX_TOPS))
            break

    # G 16 - a generation the approved facts never state.
    for generation in sorted(set(_GENERATION_RE.findall(said))):
        if generation.lower() not in sourced.lower():
            faults.append(
                "G16 mixed generations: names %s, which this recommendation's "
                "approved facts never state" % generation)
            break

    return faults


# Wording that asserts the ACCOUNT has a settled requirement, project or
# buying motion. Section C allows that only at the Opportunity tier: a
# Conversation Starter may say a topic "creates a relevant conversation", and
# must not say the account needs, plans, is evaluating or is replacing
# anything.
#
# Deliberately anchored to the account, not to HP. "Wolf Pro Security requires
# a supported Windows PC" is an approved product condition and must survive;
# "Astra requires endpoint protection" is the claim the section forbids.
_CONFIRMED_NEED_RE = re.compile(
    r"\b(?:needs?|requires?|is\s+seeking|are\s+seeking|is\s+looking\s+(?:to|for)|"
    r"plans?\s+to|intends?\s+to|is\s+evaluating|are\s+evaluating|"
    r"is\s+replacing|are\s+replacing|is\s+refreshing|are\s+refreshing|"
    r"has\s+budget|have\s+budget|is\s+procuring|is\s+purchasing|will\s+purchase|"
    r"has\s+a\s+requirement|is\s+in\s+market)\b", re.I)

# Sentence openers that make the subject HP rather than the account, so the
# same verb is a product condition instead of an account claim.
_HP_SUBJECT_RE = re.compile(r"^\s*(?:hp\b|wolf\b|poly\b|z\s+by\s+hp\b|elite|pro\b)", re.I)

TIER_OPPORTUNITY = "Opportunity"
TIER_CONTEXT_ONLY = "Context Only"

# The client's ladder, 25 Sep: an offering "is relevant" only where the
# evidence reaches the Opportunity tier and the Rulebook's conditions are
# supported. Below that it "may be relevant", and at Context Only it is not
# recommended at all.
#
# These match the settled wording and the ordinary ways a model reaches for it.
# "may be relevant" is deliberately excluded - it is the permitted phrasing one
# rung down, and matching it here would reject the correct sentence.
_SETTLED_RELEVANCE_RE = re.compile(
    r"\b(?:is\s+relevant|are\s+relevant|is\s+(?:a\s+)?(?:strong|clear|direct|"
    r"natural)\s+fit|is\s+well[\s-]suited|is\s+the\s+right\s+(?:fit|solution)|"
    r"clearly\s+addresses|directly\s+addresses)\b", re.I)

# Wording that recommends an HP offering at all. Context Only may not.
_RECOMMENDS_RE = re.compile(
    r"\b(?:we\s+recommend|recommend(?:ed|ing)?|should\s+(?:deploy|adopt|buy|"
    r"purchase|consider)|propose|positions?\s+HP|pitch)\b", re.I)


def tier_language_faults(text: str, tier: str) -> list:
    """Where this prose claims more than its evidence tier permits.

    Section C attaches permitted language to each tier, and until this existed
    the tier was published beside prose that ignored it - a card resting on one
    pipeline could still read as a settled requirement.

    Only the account half is tested. A sentence whose subject is HP is stating
    a product condition, which every tier may state.
    """
    faults = []
    said = " ".join(str(text or "").split())
    if not said:
        return faults

    tier_name = str(tier or "") or TIER_CONTEXT_ONLY

    # The relevance ladder. Unlike the account-need check below, this one tests
    # HP-subject sentences too: "HP WXP is relevant to this opportunity" is
    # exactly the claim the ladder governs, and it is always HP-subject.
    if tier_name != TIER_OPPORTUNITY:
        hit = _SETTLED_RELEVANCE_RE.search(said)
        if hit:
            faults.append(
                "tier %s: says %r, which states settled relevance. On this "
                "evidence an offering may only \"be relevant\", never \"is "
                "relevant\"" % (tier_name, hit.group(0)))
    if tier_name == TIER_CONTEXT_ONLY:
        hit = _RECOMMENDS_RE.search(said)
        if hit:
            faults.append(
                "tier Context Only: says %r, but a detected technology alone is "
                "a possible fit and must not be recommended" % hit.group(0))

    if tier_name == TIER_OPPORTUNITY:
        return faults

    for sentence in re.split(r"(?<=[.;])\s+", said):
        if _HP_SUBJECT_RE.match(sentence):
            continue
        hit = _CONFIRMED_NEED_RE.search(sentence)
        if hit:
            faults.append(
                "tier %s: says %r, which states a confirmed need, project or "
                "buying motion that only the Opportunity tier may claim"
                % (tier_name, hit.group(0)))
            break
    return faults


def approve_rulebook_facts(rule, account_country, now=None):
    """The same filter, applied to a rule of the HP 220 Account Rulebook.

    Returns (approved, rejected) as `FactDecision` lists, exactly as
    `approve_facts` does, so every consumer of a recommendation keeps working
    unchanged - `recommendations.py`, `retrieval/corpus.py`,
    `evaluator/sources.py`, `dashboard/priorities.py` and
    `scripts/audit_grounding.py` all read
    `approved_facts[].{text, qualifiers, conditions, kept}` and none of them
    needs to know which corpus a fact came from.

    Three of the deck guardrails do not apply and are not pretended to:

      G8 (a claim citing a footnote the deck never defines) has no analogue -
      a rulebook fact carries its conditions in the rule's own `conditions`
      list, so there is no dangling reference to be missing.

      G10 (embargo) has none either. The rulebook states no embargo dates; the
      decks do, and that is one of the things the rulebook was written to
      settle.

      The slide-level competitor block still applies, but it is keyed on the
      rule rather than on a slide's parsed restrictions, because a rulebook
      rule names its competitor explicitly (Part A rule 8) instead of carrying
      a scanned restriction block.

    What does apply is everything about how a claim may be worded: the
    country-restricted superlatives, the competitor markets, benchmark context
    for a comparison, and the configuration qualifiers of G6/G7.
    """
    country = normalize_country(account_country)
    approved, rejected = [], []
    rule_id = str(rule.get("rule_label") or rule.get("_id") or "rulebook")
    conditions = [c.get("text") for c in (rule.get("conditions") or [])
                  if isinstance(c, dict) and c.get("text")]
    names_competitor = bool(rule.get("requires_exact_competitor")) or \
        bool(COMPETITOR_RE.search(" ".join(rule.get("allowed_facts") or [])))

    for text in (rule.get("allowed_facts") or []):
        claim = {"text": text, "qualifiers": [], "footnotes": {}}

        # Guardrail 2 - restricted superlative claims, by country.
        if country in SUPERLATIVE_BLOCK_COUNTRIES and SUPERLATIVE_RE.search(text):
            rejected.append(FactDecision(
                claim, rule_id, False,
                "restricted superlative claim in %s" % country,
                "G2 superlative by country"))
            continue

        # Guardrails 3 and 4 - competitor comparison claims, by market.
        if names_competitor and country in COMPETITOR_BLOCK_COUNTRIES:
            rejected.append(FactDecision(
                claim, rule_id, False,
                "competitor comparison claim in %s" % country,
                "G3/G4 competitor market"))
            continue

        # Guardrail 5 - a comparison needs its benchmark context. The rule's
        # own conditions count as context, the way a deck's footnotes do.
        if COMPARISON_RE.search(text) and names_competitor:
            context = text + " " + " ".join(conditions)
            if not BENCHMARK_RE.search(context):
                rejected.append(FactDecision(
                    claim, rule_id, False,
                    "comparison claim without benchmark context",
                    "G5 benchmark context"))
                continue

        # Guardrails 6 and 7 - configuration and availability qualifiers.
        fault = None
        for trigger, qualifier, note in REQUIRED_QUALIFIER_TRIGGERS:
            if trigger.search(text):
                haystack = text + " " + " ".join(conditions)
                if not qualifier.search(haystack):
                    fault = note
                    break
        if fault:
            rejected.append(FactDecision(claim, rule_id, False, fault,
                                         "G6/G7 missing qualifier"))
            continue

        # Kept. The rule's conditions travel with every fact of that rule,
        # which is C 04 - "Keep every country, device, operating-system,
        # configuration, benchmark, licence, term, seat-count, warranty,
        # registration, and availability condition written in the applicable
        # rule."
        claim["footnotes"] = {str(i): c for i, c in enumerate(conditions, 1)}
        approved.append(FactDecision(claim, rule_id, True))

    return approved, rejected


def approve_facts(slides, rule, account_country, now=None):
    """Filter a rule's candidate slides down to claims a seller may actually use.

    `slides` are hp_product_knowledge documents already restricted to the deck
    this rule maps to. Returns (approved, rejected) as FactDecision lists.
    """
    now = now or datetime.now(UTC)
    country = normalize_country(account_country)
    approved, rejected = [], []

    for slide in slides:
        slide_id = "%s::%s" % (slide.get("deck"), slide.get("slide_number"))
        restrictions = slide.get("restrictions") or {}
        slide_countries = {c.lower() for c in (restrictions.get("countries") or [])}

        # Guardrail 10 - embargo.
        embargo = parse_embargo(slide.get("embargo_raw"))
        if embargo and now < embargo:
            rejected.append(FactDecision({}, slide_id, False,
                                         "under embargo until %s" % embargo.date(),
                                         "G10 embargo"))
            continue

        # Guardrail 2 - superlative claims by country. The slide's own list and
        # the document's list both apply; either one blocks.
        if restrictions.get("superlative") and country and (
                country in SUPERLATIVE_BLOCK_COUNTRIES or country in slide_countries):
            rejected.append(FactDecision({}, slide_id, False,
                                         "superlative claims not permitted in %s" % country,
                                         "G2 superlative by country"))
            continue

        # Guardrails 3 + 4 - competitor comparison claims.
        if (restrictions.get("competitor_claims") or rule.get("competitor_claims")) \
                and country and (country in COMPETITOR_BLOCK_COUNTRIES
                                 or country in slide_countries):
            rejected.append(FactDecision({}, slide_id, False,
                                         "competitor comparison claims not permitted in %s"
                                         % country,
                                         "G3 competitor claims by market"))
            continue

        for claim in slide.get("claims") or []:
            text = claim.get("text") or ""
            conditions = claim.get("footnotes") or {}

            # Guardrail 8 - a marked claim without its condition is unusable.
            if claim.get("footnote_refs") and not conditions:
                rejected.append(FactDecision(claim, slide_id, False,
                                             "cites footnotes %s that the deck never defines"
                                             % ",".join(claim["footnote_refs"]),
                                             "G8 missing condition"))
                continue

            # Guardrail 5 - a comparison needs its benchmark context.
            if COMPARISON_RE.search(text) and rule.get("competitor_claims"):
                context = text + " " + " ".join(conditions.values())
                if not BENCHMARK_RE.search(context):
                    rejected.append(FactDecision(claim, slide_id, False,
                                                 "comparison claim without benchmark context",
                                                 "G5 benchmark context"))
                    continue

            # Guardrails 6 and 7 - configuration and availability qualifiers.
            fault = None
            for trigger, qualifier, note in REQUIRED_QUALIFIER_TRIGGERS:
                if trigger.search(text):
                    haystack = text + " " + " ".join(conditions.values()) \
                        + " " + " ".join(claim.get("qualifiers") or [])
                    if not qualifier.search(haystack):
                        fault = note
                        break
            if fault:
                rejected.append(FactDecision(claim, slide_id, False, fault,
                                             "G6/G7 missing qualifier"))
                continue

            approved.append(FactDecision(claim, slide_id, True))

    return approved, rejected


def summarise(rejected):
    """Counts by guardrail, for the widget payload. Never includes claim text."""
    out = {}
    for decision in rejected:
        out[decision.guardrail] = out.get(decision.guardrail, 0) + 1
    return out
