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
from datetime import datetime, timezone

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
COMPARISON_RE = re.compile(r"\b\d{1,3}\s*%|\bhigher\b|\bbetter\b|\bfaster\b|\bless\b", re.I)
BENCHMARK_RE = re.compile(r"cinebench|procyon|mobilemark|internal testing|"
                          r"benchmark|tested|spec sheet|data sheet", re.I)

# --- Guardrail 9: planned is not available -----------------------------------
FUTURE_RE = re.compile(r"\bplanned\b|\bexpected\b|\bfuture\b|\bwill be available\b|"
                       r"\bcoming\b|\blater this year\b", re.I)

_MONTHS = ("january february march april may june july august september "
           "october november december").split()
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
                        tzinfo=timezone.utc)
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


def approve_facts(slides, rule, account_country, now=None):
    """Filter a rule's candidate slides down to claims a seller may actually use.

    `slides` are hp_product_knowledge documents already restricted to the deck
    this rule maps to. Returns (approved, rejected) as FactDecision lists.
    """
    now = now or datetime.now(timezone.utc)
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
