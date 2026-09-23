"""Maintained topic dictionary for Intent & Demand Signals.

Maps a provider's raw intent topic to a broad theme and, only where the mapping
is direct, to an HP category. It labels topics; it never touches the
provider's score.

v1 carried the feature spec's list only, which left most of a Bombora export
in the residual bucket. v2 widens the vocabulary and adds four context themes
(Cloud & Infrastructure, Security, Financial Services & Fintech, E-commerce &
Logistics) so the export is described rather than discarded. Every term still
lives here, so any mapping on screen traces to the dictionary that produced it,
and a new equivalent is added with a version bump.

The context themes carry no HP category: they say what the account researches,
not which HP line to sell. Only the HP category intent file drives an HP play.

Kept deliberately conservative. A topic that could be read two ways is left
unmapped and flagged for review rather than placed wherever it tells the
better sales story:

  * a longer term beats a shorter one inside it, so "3d printing" is 3D,
    not Print
  * two themes of different rank resolve by THEME_PRECEDENCE; two of equal
    rank stay ambiguous -> Other / Low Relevance
  * a topic naming two HP categories (PC and Workstation) keeps its theme
    but gets no HP category
  * a hardware-category term next to a non-hardware word ("ais software
    for pc") is not treated as a device signal
  * AI & Compute never gets an HP category from the topic text alone

Account-agnostic: nothing below is derived from any particular account.
"""

from app.services.hp.product_rules import token_present

DICTIONARY_VERSION = "intent-map-v2"

THEME_AI = "AI & Compute"
THEME_DEVICES = "Devices & Endpoints"
THEME_COLLAB = "Collaboration & Workplace"
THEME_CLOUD = "Cloud & Infrastructure"
THEME_SECURITY = "Security"
THEME_FINANCE = "Financial Services & Fintech"
THEME_COMMERCE = "E-commerce & Logistics"
THEME_PRINT = "Print"
THEME_3D = "3D"
# Renamed from "Other / Unmapped" in v2. The bucket never was a destination -
# it is the topics the dictionary does not place - and the old wording read as
# a mapping claim, which is what the client queried on the tooltip.
THEME_OTHER = "Other / Low Relevance"

# Display order on the Intent screen: HP-owned themes first, then the context
# themes that describe the account's wider research, then the residue.
THEMES = (THEME_COLLAB, THEME_AI, THEME_CLOUD, THEME_DEVICES, THEME_FINANCE,
          THEME_SECURITY, THEME_COMMERCE, THEME_PRINT, THEME_3D, THEME_OTHER)

# Themes added in v2 to describe the account's wider research. They carry no
# HP category by design: they say what the account is looking at, not which HP
# line to sell, and only the category file may drive an HP play.
CONTEXT_THEMES = (THEME_CLOUD, THEME_SECURITY, THEME_FINANCE, THEME_COMMERCE)

CAT_PC = "PC"
CAT_WORKSTATION = "Workstation"
CAT_POLY = "Poly/Collaboration"
CAT_PRINT = "Print"
CAT_3D = "3D"

# term -> (theme, HP category or None). None means the term places the topic in
# a theme but does not say which HP line it concerns.
TERMS = {
    # --- AI & Compute -------------------------------------------------
    "generative ai": (THEME_AI, None),
    "chatgpt": (THEME_AI, None),
    "openai": (THEME_AI, None),
    "machine learning": (THEME_AI, None),
    "artificial intelligence": (THEME_AI, None),
    "deep learning": (THEME_AI, None),
    "neural network": (THEME_AI, None),
    "neural networks": (THEME_AI, None),
    "large language model": (THEME_AI, None),
    "large language models": (THEME_AI, None),
    "llm": (THEME_AI, None),
    "llms": (THEME_AI, None),
    "ai strategy": (THEME_AI, None),
    "ai agents": (THEME_AI, None),
    "ai chips": (THEME_AI, None),
    "gpu": (THEME_AI, None),
    "gpus": (THEME_AI, None),
    "graphics processing unit": (THEME_AI, None),
    "graphics processing units": (THEME_AI, None),
    "ai compute": (THEME_AI, None),
    "supervised learning": (THEME_AI, None),
    "self-supervised learning": (THEME_AI, None),

    # --- Devices & Endpoints ------------------------------------------
    "pc": (THEME_DEVICES, CAT_PC),
    "pcs": (THEME_DEVICES, CAT_PC),
    "laptop": (THEME_DEVICES, CAT_PC),
    "laptops": (THEME_DEVICES, CAT_PC),
    "notebook": (THEME_DEVICES, CAT_PC),
    "notebooks": (THEME_DEVICES, CAT_PC),
    "desktop": (THEME_DEVICES, CAT_PC),
    "desktops": (THEME_DEVICES, CAT_PC),
    "endpoint": (THEME_DEVICES, None),
    "endpoints": (THEME_DEVICES, None),
    "endpoint management": (THEME_DEVICES, None),
    "device management": (THEME_DEVICES, None),
    "workstation": (THEME_DEVICES, CAT_WORKSTATION),
    "workstations": (THEME_DEVICES, CAT_WORKSTATION),
    # Peripherals and mobile hardware: Devices, but no HP category - the topic
    # text alone does not say the account wants an HP PC.
    "monitor": (THEME_DEVICES, None),
    "monitors": (THEME_DEVICES, None),
    "display": (THEME_DEVICES, None),
    "displays": (THEME_DEVICES, None),
    "oled display": (THEME_DEVICES, None),
    "projector": (THEME_DEVICES, None),
    "projectors": (THEME_DEVICES, None),
    "tablet": (THEME_DEVICES, None),
    "tablets": (THEME_DEVICES, None),
    "ipad": (THEME_DEVICES, None),
    "android": (THEME_DEVICES, None),
    "ios": (THEME_DEVICES, None),
    "raspberry pi": (THEME_DEVICES, None),
    "mobile device": (THEME_DEVICES, None),
    "mobile devices": (THEME_DEVICES, None),

    # --- Collaboration & Workplace ------------------------------------
    "meeting room": (THEME_COLLAB, CAT_POLY),
    "meeting rooms": (THEME_COLLAB, CAT_POLY),
    "huddle room": (THEME_COLLAB, CAT_POLY),
    "huddle rooms": (THEME_COLLAB, CAT_POLY),
    "video collaboration": (THEME_COLLAB, CAT_POLY),
    "video conferencing": (THEME_COLLAB, CAT_POLY),
    "unified communications": (THEME_COLLAB, CAT_POLY),
    "conferencing": (THEME_COLLAB, CAT_POLY),
    "headset": (THEME_COLLAB, CAT_POLY),
    "headsets": (THEME_COLLAB, CAT_POLY),
    "phone system": (THEME_COLLAB, CAT_POLY),
    "phone systems": (THEME_COLLAB, CAT_POLY),
    "voip": (THEME_COLLAB, CAT_POLY),
    "microsoft teams": (THEME_COLLAB, CAT_POLY),
    "zoom": (THEME_COLLAB, CAT_POLY),
    "webex": (THEME_COLLAB, CAT_POLY),
    # Workplace / people topics: the Collaboration & Workplace theme, but no
    # Poly category - an HR topic is not a hardware signal.
    "hybrid work": (THEME_COLLAB, None),
    "remote work": (THEME_COLLAB, None),
    "flexible working": (THEME_COLLAB, None),
    "future of work": (THEME_COLLAB, None),
    "return to office": (THEME_COLLAB, None),
    "workplace": (THEME_COLLAB, None),
    "collaboration": (THEME_COLLAB, None),
    "chat tool": (THEME_COLLAB, None),
    "google drive": (THEME_COLLAB, None),
    "staffing": (THEME_COLLAB, None),
    "recruitment": (THEME_COLLAB, None),
    "recruiting": (THEME_COLLAB, None),
    "onboarding": (THEME_COLLAB, None),
    "talent management": (THEME_COLLAB, None),
    "talent acquisition": (THEME_COLLAB, None),
    "employee experience": (THEME_COLLAB, None),
    "employee engagement": (THEME_COLLAB, None),
    "termination": (THEME_COLLAB, None),
    "layoff": (THEME_COLLAB, None),
    "layoffs": (THEME_COLLAB, None),
    "workforce": (THEME_COLLAB, None),
    "leadership": (THEME_COLLAB, None),
    "leadership training": (THEME_COLLAB, None),
    "management development": (THEME_COLLAB, None),
    "executive compensation": (THEME_COLLAB, None),
    "tuition assistance": (THEME_COLLAB, None),
    "vision care": (THEME_COLLAB, None),
    "c-suite": (THEME_COLLAB, None),
    "company relocation": (THEME_COLLAB, None),
    "process mapping": (THEME_COLLAB, None),
    "email management": (THEME_COLLAB, None),
    "automated reporting": (THEME_COLLAB, None),
    "job satisfaction": (THEME_COLLAB, None),
    "succession planning": (THEME_COLLAB, None),
    "successfactors": (THEME_COLLAB, None),
    "executive development": (THEME_COLLAB, None),
    "professional development": (THEME_COLLAB, None),
    "performance management": (THEME_COLLAB, None),
    "employee retention": (THEME_COLLAB, None),
    "employee services": (THEME_COLLAB, None),
    "hr": (THEME_COLLAB, None),
    "human resources": (THEME_COLLAB, None),
    "talent supply": (THEME_COLLAB, None),
    "generation z recruiting": (THEME_COLLAB, None),
    "gen z workforce": (THEME_COLLAB, None),

    # --- Cloud & Infrastructure ---------------------------------------
    "cloud": (THEME_CLOUD, None),
    "cloud computing": (THEME_CLOUD, None),
    "hybrid cloud": (THEME_CLOUD, None),
    "multicloud": (THEME_CLOUD, None),
    "public cloud": (THEME_CLOUD, None),
    "private cloud": (THEME_CLOUD, None),
    "data center": (THEME_CLOUD, None),
    "data centre": (THEME_CLOUD, None),
    "data centers": (THEME_CLOUD, None),
    "data centres": (THEME_CLOUD, None),
    "server": (THEME_CLOUD, None),
    "servers": (THEME_CLOUD, None),
    "linux servers": (THEME_CLOUD, None),
    "virtualization": (THEME_CLOUD, None),
    "virtualisation": (THEME_CLOUD, None),
    "kubernetes": (THEME_CLOUD, None),
    "containers": (THEME_CLOUD, None),
    "microsoft azure": (THEME_CLOUD, None),
    "azure": (THEME_CLOUD, None),
    "aws": (THEME_CLOUD, None),
    "amazon web services": (THEME_CLOUD, None),
    "google cloud": (THEME_CLOUD, None),
    "networking": (THEME_CLOUD, None),
    "network attached storage": (THEME_CLOUD, None),
    "storage": (THEME_CLOUD, None),
    "it management": (THEME_CLOUD, None),
    "system management software": (THEME_CLOUD, None),
    "temperature monitoring": (THEME_CLOUD, None),
    "wireless service providers": (THEME_CLOUD, None),
    "disaster recovery": (THEME_CLOUD, None),
    "point-in-time recovery": (THEME_CLOUD, None),

    # --- Security -----------------------------------------------------
    "security": (THEME_SECURITY, None),
    "cybersecurity": (THEME_SECURITY, None),
    "cyber security": (THEME_SECURITY, None),
    "cyber essentials": (THEME_SECURITY, None),
    "zero trust": (THEME_SECURITY, None),
    "ransomware": (THEME_SECURITY, None),
    "malware": (THEME_SECURITY, None),
    "phishing": (THEME_SECURITY, None),
    "anti spam": (THEME_SECURITY, None),
    "antivirus": (THEME_SECURITY, None),
    "avast": (THEME_SECURITY, None),
    "firewall": (THEME_SECURITY, None),
    "threat detection": (THEME_SECURITY, None),
    "incident response": (THEME_SECURITY, None),
    "vulnerability management": (THEME_SECURITY, None),
    "identity management": (THEME_SECURITY, None),
    "access management": (THEME_SECURITY, None),
    "authentication": (THEME_SECURITY, None),
    "encryption": (THEME_SECURITY, None),
    "data privacy": (THEME_SECURITY, None),
    "compliance": (THEME_SECURITY, None),
    "governance": (THEME_SECURITY, None),
    "soc": (THEME_SECURITY, None),
    "siem": (THEME_SECURITY, None),

    # --- Financial Services & Fintech ---------------------------------
    "fintech": (THEME_FINANCE, None),
    "payments": (THEME_FINANCE, None),
    "digital payments": (THEME_FINANCE, None),
    "tokenization": (THEME_FINANCE, None),
    "digital token": (THEME_FINANCE, None),
    "asset tokenization": (THEME_FINANCE, None),
    "mastercard": (THEME_FINANCE, None),
    "visa": (THEME_FINANCE, None),
    "banking": (THEME_FINANCE, None),
    "credit and collections": (THEME_FINANCE, None),
    "indicative pricing": (THEME_FINANCE, None),
    "trading": (THEME_FINANCE, None),
    "day trading": (THEME_FINANCE, None),
    "hedging": (THEME_FINANCE, None),
    "hedge funds": (THEME_FINANCE, None),
    "interest rate risk": (THEME_FINANCE, None),
    "trade notes": (THEME_FINANCE, None),
    "trigger rates": (THEME_FINANCE, None),
    "commercial mortgages": (THEME_FINANCE, None),
    "student loans": (THEME_FINANCE, None),
    "financial aid": (THEME_FINANCE, None),
    "tax preparation": (THEME_FINANCE, None),
    "payroll": (THEME_FINANCE, None),
    "invoicing": (THEME_FINANCE, None),
    "accounting": (THEME_FINANCE, None),
    "legal spend management": (THEME_FINANCE, None),
    "equities management software": (THEME_FINANCE, None),
    "aml": (THEME_FINANCE, None),
    "anti money laundering": (THEME_FINANCE, None),

    # --- E-commerce & Logistics ---------------------------------------
    "e-commerce": (THEME_COMMERCE, None),
    "ecommerce": (THEME_COMMERCE, None),
    "supply chain": (THEME_COMMERCE, None),
    "logistics": (THEME_COMMERCE, None),
    "warehouse": (THEME_COMMERCE, None),
    "warehousing": (THEME_COMMERCE, None),
    "fulfillment": (THEME_COMMERCE, None),
    "fulfilment": (THEME_COMMERCE, None),
    "shipping": (THEME_COMMERCE, None),
    "freight": (THEME_COMMERCE, None),
    "cargo": (THEME_COMMERCE, None),
    "transportation": (THEME_COMMERCE, None),
    "last mile": (THEME_COMMERCE, None),
    "inventory management": (THEME_COMMERCE, None),
    "retail": (THEME_COMMERCE, None),
    "marketplace": (THEME_COMMERCE, None),
    "online video marketing": (THEME_COMMERCE, None),
    "gift with purchase": (THEME_COMMERCE, None),
    "verizon connect": (THEME_COMMERCE, None),

    # --- Print --------------------------------------------------------
    "printer": (THEME_PRINT, CAT_PRINT),
    "printers": (THEME_PRINT, CAT_PRINT),
    "print": (THEME_PRINT, CAT_PRINT),
    "printing": (THEME_PRINT, CAT_PRINT),
    "managed print": (THEME_PRINT, CAT_PRINT),
    "document management": (THEME_PRINT, CAT_PRINT),
    "scanning": (THEME_PRINT, CAT_PRINT),
    "multifunction printer": (THEME_PRINT, CAT_PRINT),

    # --- 3D -----------------------------------------------------------
    "3d printing": (THEME_3D, CAT_3D),
    "additive manufacturing": (THEME_3D, CAT_3D),
    "3d printer": (THEME_3D, CAT_3D),
    "3d printers": (THEME_3D, CAT_3D),
}

# Words that, next to a hardware-category term, mean the topic is about
# something other than the hardware: "ais software for pc", "print advertising".
NON_HARDWARE_QUALIFIERS = ("software", "advertising", "marketing", "media")

# Words close to a theme that are not dictionary terms. A topic carrying one
# stays unmapped but is flagged, so a reviewer sees the near-misses first
# instead of hunting through every unmapped topic.
NEAR_MISS_TERMS = {
    THEME_AI: ("ai",),
    THEME_DEVICES: ("device", "devices", "hardware", "computer", "computers"),
    THEME_COLLAB: ("meeting", "meetings", "communications"),
    THEME_CLOUD: ("infrastructure", "network", "database", "databases"),
    THEME_SECURITY: ("secure", "risk", "fraud"),
    THEME_FINANCE: ("finance", "financial"),
    THEME_COMMERCE: ("delivery", "distribution"),
    THEME_3D: ("3d",),
}

# HP categories shown on the screen, in display order. hp_play is a static
# reference label, not evidence.
HP_CATEGORIES = (
    {"category": CAT_PC, "hp_play": "HP Elite & Pro PCs"},
    {"category": CAT_WORKSTATION, "hp_play": "Z by HP Workstations"},
    {"category": CAT_POLY, "hp_play": "Poly Collaboration Hardware"},
    {"category": CAT_PRINT, "hp_play": "HP Enterprise Printing & Managed Print Services"},
    {"category": CAT_3D, "hp_play": "HP Multi Jet Fusion (3D)"},
)

# The hiring-linked intent category of the source table: Source A topics whose
# text relates to staffing. They keep their Step 3 theme; this tag only places
# them beside the Source B job-posting signal. HR software ("hr tech:
# successfactors") is left out - it is a system, not staffing demand.
HIRING_TERMS = ("staffing", "staff", "recruitment", "recruiting", "hiring",
                "onboarding", "talent", "layoff", "layoffs", "workforce")


def is_hiring_linked(topic: str) -> bool:
    return any(token_present(t, topic) for t in HIRING_TERMS)


# Keyword-noise gate: DISABLED by client instruction (Sep 2026).
#
# This dictionary used to bar a category from becoming the account's primary
# HP category when its keywords carried an ambiguous term ("SLA" read as
# service-level agreement rather than stereolithography). The client has ruled
# that the HP category intent file is the source of truth: its scores are
# vendor-verified and are to be taken and used as supplied, with no
# second-guessing of the keywords behind them.
#
# It is left in place as an empty mapping rather than deleted so that every
# reader (`urgency.py`, `intent_demand_signals.py`, the input contract) keeps
# working and the gate degrades to a no-op: nothing is ever flagged, no
# category is barred, and the highest-scoring category is always primary, as
# the client's PDF states. Re-enabling is a matter of putting terms back here.
NOISY_CATEGORY_TERMS: dict[str, str] = {}

# Category names used by the HP category intent file -> the categories above.
CATEGORY_ALIASES = {
    "pc": CAT_PC, "pcs": CAT_PC,
    "workstation": CAT_WORKSTATION, "workstations": CAT_WORKSTATION,
    "poly": CAT_POLY, "poly/collaboration": CAT_POLY,
    "print": CAT_PRINT, "printer": CAT_PRINT, "printers": CAT_PRINT,
    "3d": CAT_3D, "3d printer": CAT_3D, "3d printers": CAT_3D,
}

# Supporting intent signals, steps 2-4 of the intent flow. Per HP category, the
# families of Source A (11_intent_score) topics that can support it, and the
# technologies (Explorium sheet 4 technographics, sheet 5 webstack) that show a
# family is actually in use at the account. A topic keeps its exact
# 11_intent_score score; a technology only confirms, it never scores, and no
# supporting signal changes the category file's score.
#
# Families are tried in order and a topic joins the first it matches, so the
# specific families come before the catch-all "AI / Machine learning".
# "product development" is left out of 3D because Bombora files agile
# retrospectives and test tooling under it; "Google Analytics" is not a data
# analytics technology here - it measures a website, not the business.
SIGNAL_FAMILIES = {
    CAT_WORKSTATION: (
        {"signal": "GPT / LLMs",
         "topic_terms": ("gpt", "chatgpt", "openai", "llm", "llms", "large language model",
                         "generative ai"),
         "tech_terms": ("openai", "chatgpt", "azure openai", "gpt")},
        {"signal": "AI chips / GPU",
         "topic_terms": ("ai chips", "gpu", "gpus", "graphics processing unit", "ai compute"),
         "tech_terms": ("nvidia", "cuda")},
        {"signal": "Vector databases",
         "topic_terms": ("vector database", "vector databases"),
         "tech_terms": ("pinecone", "weaviate", "milvus", "qdrant", "chroma", "pgvector")},
        {"signal": "Data analytics",
         "topic_terms": ("data analytics", "analytics", "data science"),
         "tech_terms": ("tableau", "power bi", "looker", "qlik", "cognos", "spark",
                        "databricks", "snowflake", "sas")},
        {"signal": "CAD / 3D design",
         "topic_terms": ("cad", "3d rendering", "3d modeling", "engineering simulation"),
         "tech_terms": ("autocad", "autodesk", "catia", "solidworks", "blender", "siemens nx",
                        "creo", "rhino")},
        {"signal": "AI / Machine learning",
         "topic_terms": ("ai", "artificial intelligence", "machine learning", "ml"),
         "tech_terms": ("pytorch", "keras", "tensorflow", "scikit-learn", "mllib", "sagemaker",
                        "azure machine learning", "vertex ai", "hugging face", "databricks")},
    ),
    CAT_PC: (
        {"signal": "PCs & endpoints",
         "topic_terms": ("pc", "pcs", "laptop", "laptops", "desktop", "desktops", "notebook",
                         "notebooks", "endpoint", "endpoints", "device management", "windows 11"),
         "tech_terms": ("intune", "jamf", "workspace one", "airwatch", "windows 10", "windows 11",
                        "microsoft windows os")},
    ),
    CAT_POLY: (
        {"signal": "Video & unified communications",
         "topic_terms": ("video collaboration", "video conferencing", "unified communications",
                         "meeting room", "meeting rooms", "huddle room", "microsoft teams",
                         "zoom", "webex", "hybrid work"),
         "tech_terms": ("microsoft teams", "zoom", "webex", "google meet", "ringcentral", "8x8")},
    ),
    CAT_PRINT: (
        {"signal": "Print & document workflow",
         "topic_terms": ("printer", "printers", "print", "printing", "managed print",
                         "document management"),
         "tech_terms": ("papercut", "printix", "uniflow", "kofax", "docuware")},
    ),
    CAT_3D: (
        {"signal": "Additive manufacturing",
         "topic_terms": ("3d printing", "additive manufacturing", "additive", "prototyping"),
         "tech_terms": ("materialise", "stratasys", "formlabs", "ultimaker", "markforged")},
        {"signal": "CAD / 3D design",
         "topic_terms": ("cad", "3d modeling", "3d design", "3d rendering"),
         "tech_terms": ("autocad", "autodesk", "catia", "solidworks", "blender", "siemens nx",
                        "creo", "fusion 360")},
    ),
}


# Categories whose families name hardware. For these, a topic that pairs the
# term with a non-hardware word ("ais software for pc") supports nothing.
# Workstation's families are AI and data research by design, so "ai for
# marketing" still counts there as AI research.
HARDWARE_FAMILY_CATEGORIES = {CAT_PC, CAT_POLY, CAT_PRINT, CAT_3D}


def signal_family(topic: str, category: str) -> dict | None:
    """The first supporting-signal family of the category this topic matches."""
    if category in HARDWARE_FAMILY_CATEGORIES and any(
            token_present(q, topic) for q in NON_HARDWARE_QUALIFIERS):
        return None
    for family in SIGNAL_FAMILIES.get(category, ()):
        if any(token_present(t, topic) for t in family["topic_terms"]):
            return family
    return None


def family_technologies(family: dict, technologies: list[dict]) -> list[dict]:
    """Technologies from the account's own stack that confirm a family."""
    return [t for t in technologies
            if any(token_present(term, t["match_name"]) for term in family["tech_terms"])]


# Strength bands for Bombora topic scores (0-100). The cut points are the 70+
# and 85+ filters the Intent screen already offered, so a band and a filter
# never disagree about where "high" starts. Not applied to the category file's
# scores - that provider supplies its own Buying Stage and Research Volume, and
# one provider's scale is not read against another's.
INTENSITY_BANDS = ((85, "High"), (70, "Moderate"), (0, "Low"))


def intensity(score) -> str | None:
    if score is None:
        return None
    for floor, label in INTENSITY_BANDS:
        if score >= floor:
            return label
    return None


# Theme precedence for a topic whose terms name two themes. v1 sent every such
# topic to Other; with nine themes the overlaps are ordinary ("security: cloud
# security", "hardware: ai chips") and dropping them lost real signal.
#
# The order puts the HP-owned themes above the context themes, so a topic that
# is both an HP signal and context is read as the HP signal. It applies only
# when the themes sit at different ranks: two themes of equal rank are still
# genuinely ambiguous and are flagged for review, as before.
THEME_PRECEDENCE = (THEME_3D, THEME_PRINT, THEME_DEVICES, THEME_COLLAB, THEME_AI,
                    THEME_SECURITY, THEME_CLOUD, THEME_FINANCE, THEME_COMMERCE)


def _resolve_themes(themes: list[str]) -> str | None:
    """The single winning theme, or None when two rank equally."""
    ranked = sorted(themes, key=lambda t: THEME_PRECEDENCE.index(t))
    if len(ranked) > 1 and (THEME_PRECEDENCE.index(ranked[0])
                            == THEME_PRECEDENCE.index(ranked[1])):
        return None
    return ranked[0]


def _drop_contained(terms: list[str]) -> list[str]:
    """Keep the longest terms: 'printing' goes when '3d printing' matched."""
    return [t for t in terms
            if not any(t != other and t in other for other in terms)]


def map_topic(topic: str) -> dict:
    """Theme, HP category and review flag for one raw topic.

    Returns matched_terms so the screen can show why a topic landed where it
    did, and mapping_status: 'mapped', 'unmapped' or 'flagged' (with a reason).
    """
    matched = _drop_contained([t for t in TERMS if token_present(t, topic)])
    themes = sorted({TERMS[t][0] for t in matched})

    result = {"theme": THEME_OTHER, "hp_category": None, "matched_terms": matched,
              "mapping_status": "unmapped", "flag_reason": None}

    if not matched:
        for theme, words in NEAR_MISS_TERMS.items():
            hit = next((w for w in words if token_present(w, topic)), None)
            if hit:
                result["mapping_status"] = "flagged"
                result["flag_reason"] = (f"Mentions '{hit}' but no {theme} dictionary "
                                         f"term; left unmapped for review")
                break
        return result

    if len(themes) > 1:
        theme = _resolve_themes(themes)
        if theme is None:
            result["mapping_status"] = "flagged"
            result["flag_reason"] = ("Matches more than one theme ("
                                     + ", ".join(themes) + "); left unmapped for review")
            return result
        # The winning theme's own terms decide the HP category; a term from the
        # theme that lost must not carry a category across.
        matched = [t for t in matched if TERMS[t][0] == theme]
    else:
        theme = themes[0]
    categories = sorted({TERMS[t][1] for t in matched if TERMS[t][1]})

    if categories:
        qualifier = next((w for w in NON_HARDWARE_QUALIFIERS if token_present(w, topic)), None)
        if qualifier:
            result["mapping_status"] = "flagged"
            result["flag_reason"] = (f"'{matched[0]}' appears with '{qualifier}', so it is "
                                     f"not treated as {categories[0]} hardware; left "
                                     f"unmapped for review")
            return result

    result["theme"] = theme
    result["mapping_status"] = "mapped"
    if len(categories) == 1:
        result["hp_category"] = categories[0]
    elif len(categories) > 1:
        result["mapping_status"] = "flagged"
        result["flag_reason"] = ("Names more than one HP category ("
                                 + ", ".join(categories) + "); kept broad in "
                                 f"{theme} with no HP category")
    return result
