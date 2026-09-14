"""Maintained topic dictionary for Intent & Demand Signals.

Maps a provider's raw intent topic to a broad theme and, only where the mapping
is direct, to an HP category. It labels topics; it never touches the
provider's score.

The terms are the feature spec's own list plus their plurals - nothing else.
An equivalent that turns up on real data is added here with a version bump,
so every mapping on screen can be traced to the dictionary that produced it.

Kept deliberately conservative. A topic that could be read two ways is left
unmapped and flagged for review rather than placed wherever it tells the
better sales story:

  * a longer term beats a shorter one inside it, so "3d printing" is 3D,
    not Print
  * a topic still matching two themes is ambiguous -> Other / Unmapped
  * a topic naming two HP categories (PC and Workstation) keeps its theme
    but gets no HP category
  * a hardware-category term next to a non-hardware word ("ais software
    for pc") is not treated as a device signal
  * AI & Compute never gets an HP category from the topic text alone

Account-agnostic: nothing below is derived from any particular account.
"""

from app.services.hp.product_rules import token_present

DICTIONARY_VERSION = "intent-map-v1"

THEME_AI = "AI & Compute"
THEME_DEVICES = "Devices & Endpoints"
THEME_COLLAB = "Collaboration & Workplace"
THEME_PRINT = "Print"
THEME_3D = "3D"
THEME_OTHER = "Other / Unmapped"

THEMES = (THEME_AI, THEME_DEVICES, THEME_COLLAB, THEME_PRINT, THEME_3D, THEME_OTHER)

CAT_PC = "PC"
CAT_WORKSTATION = "Workstation"
CAT_POLY = "Poly/Collaboration"
CAT_PRINT = "Print"
CAT_3D = "3D"

# term -> (theme, HP category or None). None means the term places the topic in
# a theme but does not say which HP line it concerns.
TERMS = {
    "generative ai": (THEME_AI, None),
    "chatgpt": (THEME_AI, None),
    "machine learning": (THEME_AI, None),
    "gpu": (THEME_AI, None),
    "gpus": (THEME_AI, None),
    "graphics processing unit": (THEME_AI, None),
    "graphics processing units": (THEME_AI, None),
    "ai compute": (THEME_AI, None),

    "pc": (THEME_DEVICES, CAT_PC),
    "pcs": (THEME_DEVICES, CAT_PC),
    "laptop": (THEME_DEVICES, CAT_PC),
    "laptops": (THEME_DEVICES, CAT_PC),
    "endpoint": (THEME_DEVICES, None),
    "endpoints": (THEME_DEVICES, None),
    "workstation": (THEME_DEVICES, CAT_WORKSTATION),
    "workstations": (THEME_DEVICES, CAT_WORKSTATION),

    "meeting room": (THEME_COLLAB, CAT_POLY),
    "meeting rooms": (THEME_COLLAB, CAT_POLY),
    "video collaboration": (THEME_COLLAB, CAT_POLY),
    "unified communications": (THEME_COLLAB, CAT_POLY),
    "hybrid work": (THEME_COLLAB, CAT_POLY),

    "printer": (THEME_PRINT, CAT_PRINT),
    "printers": (THEME_PRINT, CAT_PRINT),
    "print": (THEME_PRINT, CAT_PRINT),
    "printing": (THEME_PRINT, CAT_PRINT),
    "managed print": (THEME_PRINT, CAT_PRINT),

    "3d printing": (THEME_3D, CAT_3D),
    "additive manufacturing": (THEME_3D, CAT_3D),
}

# Words that, next to a hardware-category term, mean the topic is about
# something other than the hardware: "ais software for pc", "print advertising".
NON_HARDWARE_QUALIFIERS = ("software", "advertising", "marketing", "media")

# Words close to a theme that are not dictionary terms. A topic carrying one
# stays unmapped but is flagged, so a reviewer sees the near-misses first
# instead of hunting through every unmapped topic.
NEAR_MISS_TERMS = {
    THEME_AI: ("ai", "artificial intelligence"),
    THEME_DEVICES: ("desktop", "desktops", "notebook", "notebooks",
                    "device", "devices", "hardware"),
    THEME_COLLAB: ("collaboration", "conferencing", "meeting", "meetings"),
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


# Items in the HP category intent file that do not mean what the category
# assumes, each seen on real account data. A category carrying one is flagged
# on screen and is never picked as the account's primary HP category.
NOISY_CATEGORY_TERMS = {
    "sla": "In job postings SLA means service-level agreement, not "
           "stereolithography (SLA) 3D printing",
    "identified as competitor of": "A news relationship category - who the "
                                   "company competes with - not a print signal",
}

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
        result["mapping_status"] = "flagged"
        result["flag_reason"] = ("Matches more than one theme ("
                                 + ", ".join(themes) + "); left unmapped for review")
        return result

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
