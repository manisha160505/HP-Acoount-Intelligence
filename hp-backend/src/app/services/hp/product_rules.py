"""The 18 HP deck-usage rules, as an explicit table.

Taken from "HP 220-Account Platform - HP-Provided Knowledge Rules for RAG
Recommendations", table "HP Deck Usage Rules". Each row says: which account
signal makes a deck usable, which deck, and which facts that deck is allowed to
supply.

Matching is deterministic and token-based. The model never picks a product -
it is handed the matched rule and the approved facts and asked only to write
the rationale. That is the document's own instruction:

    "Do not choose a product only because a vector search says it is similar."

Account-agnostic: every token below describes HP product semantics or a generic
business signal. Nothing here is derived from any particular account.
"""

import re

# Signal tokens are matched on word boundaries against verified account
# evidence only - never against HP marketing text, which would let a deck
# create the very signal that justifies it (guardrail 13).


def token_present(token: str, haystack: str) -> bool:
    """Word-boundary match, so 'ai' cannot fire inside 'maintenance'."""
    if not token or not haystack:
        return False
    return re.search(r"(?<![a-z0-9])" + re.escape(token.lower()) + r"(?![a-z0-9])",
                     haystack.lower()) is not None


# Phrases that look like a signal but are not. Every entry below was a real
# false positive observed on real account data, not a hypothetical.
#
#   "tokenization"       - financial tokenisation, not endpoint security
#   "vehicle fleet"      - an automotive account's vehicles, not its devices
#   "analysis services"  - Azure / SQL Server products, not analyst users
#   "social collaboration", "marketing collaboration"
#                        - HR and marketing topics, not video meetings
#   "employee experience management"
#                        - HR software, not a hybrid-work device need
#   "executive development", "leadership training"
#                        - training topics, not senior leaders as device users
GLOBAL_EXCLUDE_PHRASES = [
    "tokenization", "tokenisation", "digital token",
    "vehicle", "vehicles", "fleet maintenance",
    "ai chips",
    "analysis services",
    "social collaboration", "marketing collaboration",
    "employee experience management",
    "executive development", "executive education", "leadership training",
    "leadership strategies", "management development",
]


def _is_excluded(text: str) -> bool:
    """True when the matched text is one of the known look-alikes."""
    low = " ".join(str(text or "").split()).lower()
    return any(phrase in low for phrase in GLOBAL_EXCLUDE_PHRASES)

DEVICE_NOTEBOOK = "notebook"
DEVICE_MINI = "mini"
DEVICE_SFF = "sff"
DEVICE_TOWER = "tower"
DEVICE_AIO = "aio"

RULES = [
    {
        "rule_id": 1,
        "condition": "Enterprise AI / local AI / AI adoption",
        "signal_tokens": ["ai adoption", "genai", "generative ai", "copilot",
                          "artificial intelligence", "machine learning",
                          "openai", "ai hiring", "local ai", "ai pc", "ai-pc"],
        "deck": "HP EliteBook 8 G2 Series",
        "deck_match": r"EliteBook 8 G2",
        "device_type": DEVICE_NOTEBOOK,
        "family": "Elite",
        "allowed_facts": [
            "EliteBook 8 G2i/G2a Next Gen AI PC models", "Intel Core Ultra",
            "AMD Ryzen AI PRO", "up to 50 TOPS NPU", "local AI processing",
            "Copilot+ positioning", "AI-enhanced conferencing", "HP Wolf Security",
            "Sure View", "5MP HDR IR camera", "optional 5G/HP Go",
            "up to 64GB memory where supported",
        ],
        "usage_note": ("For enterprise or mobile knowledge workers with strong AI "
                       "needs. Do not choose it from an AI signal alone; user type, "
                       "scale and device type must also fit."),
    },
    {
        "rule_id": 2,
        "condition": "Enterprise AI at scale / standard fleet",
        "signal_tokens": ["large workforce", "standard endpoint", "fleet rollout",
                          "it manageability", "long lifecycle", "global sku",
                          "cost control", "standardisation", "standardization"],
        "deck": "HP EliteBook 6 G2 Series",
        "deck_match": r"EliteBook 6 G2",
        "device_type": DEVICE_NOTEBOOK,
        "family": "Elite",
        "allowed_facts": [
            "Intel, AMD and Snapdragon variants", "AI PC / Next Gen AI PC options",
            "up to 50 TOPS on Next Gen variants", "up to 64GB memory where supported",
            "HP Wolf Security", "remote manageability",
            "SIPP / long lifecycle / global SKU positioning", "optional 5G/HP Go",
            "OLED/Sure View options where supported",
        ],
        "usage_note": ("Enterprise AI across a large, repeatable fleet rather than "
                       "the most premium device."),
    },
    {
        "rule_id": 3,
        "condition": "SMB / growing-business AI refresh",
        "signal_tokens": ["smb", "mid-market", "midmarket", "workforce growth",
                          "notebook refresh", "first ai-pc", "value sensitivity"],
        "deck": "HP ProBook 4 G2 Series",
        "deck_match": r"ProBook 4 G2",
        "device_type": DEVICE_NOTEBOOK,
        "family": "Pro",
        "allowed_facts": [
            "13/14/16-inch models", "Intel/AMD options",
            "Next Gen AI variants with up to 50 TOPS NPU", "up to 68Wh battery",
            "HP Wolf Security", "Wi-Fi 6E/Wi-Fi 7 options", "optional 5G",
            "5MP camera", "Poly Studio audio", "Flip option",
        ],
        "usage_note": "Growing businesses needing practical AI, hybrid work and value.",
    },
    {
        "rule_id": 4,
        "condition": "Executive / senior leader",
        # Deliberately no bare "executive": on real intent data it matches
        # "management and executive development", a training topic. The real
        # signal for this rule is the stakeholder roster, passed in separately.
        "signal_tokens": ["senior leader", "frequent traveler", "frequent traveller",
                          "customer-facing leader", "premium device", "c-suite"],
        "roster_signal": "C-Suite",
        "deck": "HP EliteBook Ultra G1i Customer Presentation",
        "deck_match": r"EliteBook Ultra G1i",
        "device_type": DEVICE_NOTEBOOK,
        "family": "Elite",
        "allowed_facts": [
            "Intel Core Ultra 5/7 Series 2", "up to 48 TOPS NPU", "HP AI Companion",
            "local AI", "9MP + IR camera", "Poly Camera Pro", "quad speakers",
            "Wi-Fi 7", "under 1.2kg stated weight", "3K OLED option",
            "haptic trackpad", "180-degree panel", "HP Wolf Security",
            "Secured-core PC",
        ],
        "usage_note": "Senior, highly mobile executives needing premium AI productivity.",
    },
    {
        "rule_id": 5,
        "condition": "ARM / Snapdragon mobile AI",
        # Not bare "arm": it matches a company's business "arm" in a
        # firmographic description. ARM here must be the architecture.
        "signal_tokens": ["snapdragon", "arm architecture", "arm-based",
                          "arm processor", "cloud-first"],
        "deck": "HP EliteBook Ultra G1q / G1q8",
        "deck_match": r"EliteBook Ultra G1q",
        "device_type": DEVICE_NOTEBOOK,
        "family": "Elite",
        "allowed_facts": [
            "Snapdragon X Elite / X Plus", "45 TOPS NPU",
            "G1q 12-core vs G1q8 8-core", "HP AI Companion", "Poly Studio",
            "Poly Camera Pro", "Wi-Fi 7", "Microsoft Pluton", "Wolf Pro Security",
            "Fast Charge up to 50% in 30 minutes under stated conditions",
            "14.4mm max height", "14-inch 2.2K display options",
        ],
        "usage_note": ("Only when ARM/Snapdragon fits the account need. Do not "
                       "replace Intel/AMD recommendations without a reason."),
    },
    {
        "rule_id": 6,
        "condition": "Security / cyber risk",
        "signal_tokens": ["ransomware", "phishing", "endpoint security", "zero trust",
                          "firmware security", "regulated", "cyber risk",
                          "endpoint protection"],
        "deck": "Mapped EliteBook / EliteDesk / ProBook deck",
        "deck_match": None,          # attaches to whichever product was selected
        "device_type": None,
        "family": None,
        "allowed_facts": [
            "HP Wolf Security", "BIOS protection/self-healing where stated",
            "Sure View / Onlooker Detection where supported", "TPM",
            "EliteBook 8 endpoint security controller",
            "Tamper Lock / intrusion sensor on supported desktops",
            "quantum-resistant firmware claims only where allowed",
        ],
        "usage_note": ("Strengthens an already-selected product. Never copy a "
                       "security feature from one model to another."),
        "modifier_only": True,
    },
    {
        "rule_id": 7,
        "condition": "Hybrid work / video meetings",
        # "collaboration" alone matched "social collaboration" and
        # "marketing collaboration"; "employee experience" matched an HR
        # product. Both are excluded by phrase; the tokens below are the ones
        # that actually denote meetings and hybrid working.
        "signal_tokens": ["hybrid work", "flexible working", "remote team",
                          "virtual meeting", "video conferencing", "unified communications",
                          "meeting room", "microsoft teams", "zoom", "webex"],
        "deck": "Mapped EliteBook / ProBook / AiO deck",
        "deck_match": None,
        "device_type": None,
        "family": None,
        "allowed_facts": [
            "Poly Camera Pro where supported", "AI camera effects",
            "exact 5MP/9MP camera spec for the selected model",
            "IR facial recognition where supported",
            "Magic Background on EliteBook 8 G1i", "Poly Studio audio",
            "AI noise reduction / echo cancellation",
            "HP Go/5G only where supported",
        ],
        "usage_note": ("Choose the product family from user type and scale first, "
                       "then use only that product's collaboration features."),
        "modifier_only": True,
    },
    {
        "rule_id": 8,
        "condition": "Lenovo ThinkPad X1 Carbon Gen 13 found",
        # Guardrail 4: this rule needs the EXACT competitor model, nothing looser.
        "signal_tokens": ["thinkpad x1 carbon gen 13", "thinkpad x1 carbon"],
        "requires_exact_competitor": "thinkpad x1 carbon gen 13",
        "deck": "Competitive Playbook - EliteBook X G1i vs Lenovo ThinkPad X1 Carbon",
        "deck_match": r"Competitive Playbook",
        "device_type": DEVICE_NOTEBOOK,
        "family": "Elite",
        "allowed_facts": [
            "up to 85% higher CPU performance on the cited Cinebench test",
            "up to 61% better office productivity on the cited Procyon test",
            "cited battery differences", "44% less keycap wobble",
            "trackpad comparison", "dual-sided USB-C", "HP AI Companion",
            "Poly Camera Pro", "Find/Lock/Wipe", "BIOS/security differences",
        ],
        "usage_note": ("Only when the exact Lenovo model matches. Never reuse "
                       "against Dell, Apple, another Lenovo model or an unknown "
                       "competitor. Keep benchmark setup, date and disclaimer."),
        "competitor_claims": True,
    },
    {
        "rule_id": 9,
        "condition": "Education / government / RFP notebook",
        "signal_tokens": ["public sector", "government", "education", "tender",
                          "rfp", "cost-conscious"],
        "deck": "HP 200 G2 Series",
        "deck_match": r"HP 200 G2",
        "device_type": DEVICE_NOTEBOOK,
        "family": "200",
        "allowed_facts": [
            "RJ-45", "Kensington Security Lock", "dTPM 2.0",
            "spill-resistant keyboard", "USB-C Power Delivery/DisplayPort",
            "fingerprint option", "FHD + IR camera", "Wi-Fi 7 option", "DDR5",
            "up to 68Wh battery", "14/16-inch models", "RFP positioning",
        ],
        "usage_note": "Subject to tender and country requirements.",
    },
    {
        "rule_id": 10,
        "condition": "Fixed-office AI / expandable desktop",
        # Not bare "analysis": it matches "Azure Analysis Services" and
        # "Microsoft SQL Server Analysis Service", which are databases.
        "signal_tokens": ["desktop refresh", "engineering", "cad", "simulation",
                          "3d modeling", "3d modelling", "rendering",
                          "multiple displays", "local compute", "data insights",
                          "research and development", "workstation"],
        "deck": "HP EliteDesk 8 Tower G1i / G1i E Desktop AI PC",
        "deck_match": r"SFF & Tower",
        "device_type": DEVICE_TOWER,
        "family": "Elite",
        "allowed_facts": [
            "Up to Intel Core Ultra 9", "13 TOPS NPU", "Intel vPro",
            "discrete graphics support", "local RTX chat where configured",
            "4 PCIe slots", "up to 128GB DDR5", "up to 11 native USB ports",
            "up to 8 displays with the required graphics/flex-I/O setup",
            "HP Wolf Security", "Tamper Lock", "intrusion sensor",
            "toolless storage", "power measurement where available",
        ],
        "usage_note": "Desk-based power users needing expansion and higher local compute.",
    },
    {
        "rule_id": 11,
        "condition": "Compact desktop / branch / call center",
        "signal_tokens": ["branch", "call center", "call centre", "shared workstation",
                          "small desk", "standard desktop deployment"],
        "deck": "HP EliteDesk 8 Mini G1i / HP ProDesk 4 Mini G1i",
        "deck_match": r"Mini G1i",
        "device_type": DEVICE_MINI,
        "family": "Elite",
        "allowed_facts": [
            "Mini form factor", "Intel Core Ultra", "13 TOPS NPU",
            "vPro on supported variants", "Thunderbolt 4", "flex modules",
            "EliteDesk up to 7 displays with the required setup", "mounting options",
            "up to 10 USB ports with flex modules", "toolless SSD access",
            "Single Power On under stated conditions", "energy measurement",
            "HP Wolf/Sure security",
        ],
        "usage_note": "Elite is the stronger enterprise option; Pro is more value-focused.",
    },
    {
        "rule_id": 12,
        "condition": "Integrated display / front desk / shared workspace",
        "signal_tokens": ["reception", "front desk", "customer-facing desk",
                          "collaboration area", "shared workspace"],
        "deck": "HP EliteStudio 8 AiO G1i / HP ProStudio 4 AiO G1i",
        "deck_match": r"AiO G1i",
        "device_type": DEVICE_AIO,
        "family": "Elite",
        "allowed_facts": [
            "27/23.8-inch EliteStudio and 23.8-inch ProStudio options",
            "portrait/landscape stand", "optional articulating stand", "5MP camera",
            "optional HDR + IR facial recognition", "Human Presence Detection",
            "AI noise reduction / echo cancellation", "EliteStudio optional RTX 5050",
            "supported KVM Device Switch", "Power Consumption Measurement",
        ],
        "usage_note": "EliteStudio is higher-end; ProStudio is mainstream.",
    },
    {
        "rule_id": 13,
        "condition": "Desktop performance with smaller footprint",
        "signal_tokens": ["small form factor", "upgradeability", "footprint"],
        "deck": "HP EliteDesk 8 SFF G1i Desktop AI PC",
        "deck_match": r"SFF & Tower",
        "device_type": DEVICE_SFF,
        "family": "Elite",
        "allowed_facts": [
            "Up to Intel Core Ultra 9", "13 TOPS NPU",
            "optional NVIDIA A1000/A400 or AMD RX6300",
            "3x M.2 SSD up to 6TB plus 3.5-inch HDD as stated", "up to 128GB DDR5",
            "up to 8 displays with supported graphics", "up to 11 native USB ports",
            "HP Sure Run", "HP Sure Recover", "Client Security Manager", "Tamper Lock",
        ],
        "usage_note": "When Mini is too limited but Tower is larger than needed.",
    },
    {
        "rule_id": 14,
        "condition": "Sustainability / ESG",
        "signal_tokens": ["epeat", "carbon", "sustainable procurement", "esg",
                          "sustainability", "net zero", "emissions"],
        "deck": "Product deck for the product already selected",
        "deck_match": None,
        "device_type": None,
        "family": None,
        "allowed_facts": [
            "recycled aluminum/plastic percentages",
            "ocean-bound plastic where stated", "packaging claims",
            "EPEAT/ENERGY STAR/TCO status", "power-consumption measurement",
        ],
        "usage_note": ("Never choose a product for sustainability alone. Choose from "
                       "the business need first, then add supported ESG facts."),
        "modifier_only": True,
    },
    {
        "rule_id": 15,
        "condition": "Fleet serviceability / IT operations",
        "signal_tokens": ["serviceability", "repairability", "support cost",
                          "it staffing", "fleet management"],
        "deck": "EliteBook 8 / EliteDesk / mapped product deck",
        "deck_match": None,
        "device_type": None,
        "family": None,
        "allowed_facts": [
            "serviceable battery, fans, SSD, SODIMM, WLAN where stated",
            "toolless desktop SSD/HDD access where stated",
            "vPro/remote manageability where supported",
            "Premium/Premium+ Support and predictive support only where supported",
        ],
        "usage_note": ("Do not turn this into an AI story unless there is also AI "
                       "evidence."),
        "modifier_only": True,
    },
    {
        "rule_id": 16,
        "condition": "5G / highly mobile workforce",
        "signal_tokens": ["field workforce", "frequent travel", "remote sales",
                          "mobile executive", "connectivity", "5g"],
        "deck": "Mapped notebook deck that supports 5G / HP Go",
        "deck_match": None,
        "device_type": DEVICE_NOTEBOOK,
        "family": None,
        "allowed_facts": [
            "5G option and HP Go only for supported models/configurations",
            "required 5G module", "service/geography limits",
            "Wi-Fi 7 where supported", "mobile design and battery facts",
        ],
        "usage_note": "Do not treat HP Go as available everywhere.",
        "modifier_only": True,
    },
    {
        "rule_id": 17,
        "condition": "User/persona routing before product selection",
        # Personas come from the stakeholder roster, not from intent topics
        # such as "leadership & strategy: management development".
        "signal_tokens": ["frontline", "knowledge worker", "field worker",
                          "deskless", "shift worker"],
        "roster_signal": "any",
        "deck": "BPS Portfolio Sell-In Deck FY26",
        "deck_match": r"BPS Portfolio",
        "device_type": None,
        "family": None,
        "allowed_facts": [
            "Persona definitions: Leadership, Frontline, Specialist, Generalist",
            "Elite = premium/high-value work with advanced collaboration/mobility/security",
            "Pro = SMB/mid-market, reliable and scalable",
            "Chrome = speed/simplicity", "Thin Client = cloud-first/virtualized",
            "Fortis = education",
        ],
        "usage_note": ("Use first to choose the HP family, then the product-specific "
                       "deck once user type, scale and device type are clear."),
        "routing_only": True,
    },
    {
        "rule_id": 18,
        "condition": "Why AI PCs now",
        "signal_tokens": ["ai initiative", "ai programme", "ai program",
                          "ai adoption", "device refresh"],
        "deck": "BPS Portfolio Sell-In Deck FY26",
        "deck_match": r"BPS Portfolio",
        "device_type": None,
        "family": None,
        "allowed_facts": [
            "AI moving from responses to agentic tasks",
            "cloud-only to hybrid device/cloud", "role-specific AI workloads",
            "local AI for performance/scale/cost control",
            "endpoint security for AI",
            "AI + security + collaboration + productivity",
        ],
        "usage_note": ("Explains why AI-PC modernization may matter once AI adoption "
                       "is already proven. Never use HP messaging as proof that the "
                       "account is adopting AI."),
        "modifier_only": True,
    },
]

RULES_BY_ID = {r["rule_id"]: r for r in RULES}


def match_rules(evidence_texts: list, competitor_models: list = None) -> list:
    """Rules whose signal appears in this account's verified evidence.

    `evidence_texts` must contain ONLY text drawn from the account's own
    uploads. Passing HP marketing text here would let a deck manufacture the
    signal that justifies it, which guardrail 13 forbids.
    """
    blob = " \n ".join(str(t or "") for t in (evidence_texts or []))
    competitor_models = [str(c).lower() for c in (competitor_models or [])]

    matched = []
    for rule in RULES:
        hits = [t for t in rule["signal_tokens"] if token_present(t, blob)]
        if not hits:
            continue

        # A token only counts when at least one piece of evidence containing
        # it is not a known look-alike. Checking the token against the exclude
        # list is not enough - "collaboration" is a fine token, but "social
        # collaboration" is not the signal this rule means.
        real = []
        for token in hits:
            for text in (evidence_texts or []):
                if token_present(token, str(text or "")) and not _is_excluded(text):
                    real.append(token)
                    break
        if not real:
            continue

        # Guardrail 4: the competitor rule needs the exact model, from the
        # account's own technology evidence.
        exact = rule.get("requires_exact_competitor")
        if exact and not any(exact in m for m in competitor_models):
            matched.append({"rule_id": rule["rule_id"], "matched_tokens": real,
                            "blocked": "requires exact competitor model '%s'" % exact})
            continue

        matched.append({"rule_id": rule["rule_id"], "matched_tokens": real,
                        "blocked": None})
    return matched
