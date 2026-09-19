"""Tech Landscape Confidence: two drivers, one percentage per card.

    Confidence % = [(Driver 1 x 0.70) + (Driver 2 x 0.30)] x 10

This implements `HP_Tech_Landscape_Confidence_Scoring_Logic_FINAL.docx`, the
client's scoring specification for the Technographic Map. It answers the
question the document puts at the top of itself:

    "The confidence % tells us how well the available evidence supports what the
    whole card is saying - not just whether the vendor name was found."

That distinction is the entire point. `tech_landscape.py` previously wrote
`Confirmed` when a vendor string appeared in the technographics export and
`Likely` when it came from a keyword rule - a statement about *detection*, not
about whether the detection supports the HP opportunity printed beside it. The
document's harness rule says so directly:

    "Explorium technographics tells us what technology/vendor is detected. It
    does not by itself prove that the vendor represents a specific HP business
    opportunity. Use the HP Rulebook to validate that interpretation."

So the old value is kept, under its own name, as the provenance flag it always
was. `confidence` now means what the document says it means.

## Only six numbers are reachable

Both drivers score 0, 5 or 10, so the formula has nine possible outputs - and
the suppression rule removes three of them, because a card scoring Driver 1 = 0
is never created:

    Driver 1 = 10:  D2=0 -> 70%   D2=5 -> 85%   D2=10 -> 100%
    Driver 1 =  5:  D2=0 -> 35%   D2=5 -> 50%   D2=10 ->  65%
    Driver 1 =  0:  no card

A reader who sees 72% on a card is looking at a bug, not a fine-grained
judgement.

## The suppression rule is the important half

    "Mandatory guardrail: If Driver 1 = 0, do not create the Tech Landscape
    card. Intent may strengthen an evidence-backed opportunity, but intent alone
    cannot prove that a technology is present."

Driver 2 is worth 30 points and can never, on its own, put a card on screen.
`is_publishable` is the gate, and it is deliberately a separate function from
the score so a caller cannot accidentally publish a zero by only reading the
percentage.

## What is deterministic here, and what is not

Driver 2 is a pure band lookup on a number - no judgement at all. Driver 1 is
decided against `RULEBOOK_TECHNOLOGIES` below, which is transcribed from the
rules in the HP rulebook that name concrete, detectable technologies. That makes
it deterministic too, at the cost of coverage: a technology no rule names scores
0 and its card is suppressed. That is the document's intent - it says to use the
rulebook to validate the interpretation, and a technology the rulebook never
mentions has not been validated.
"""

import re

from app.services.hp import intent_topic_map as tm

# ==============================================================================
# The formula
# ==============================================================================

DRIVER_1_WEIGHT = 0.70
DRIVER_2_WEIGHT = 0.30
DRIVER_SCALE = 10          # both drivers are scored out of 10

FORMULA = ("Tech Landscape Confidence % = [(Driver 1 x 0.70) + "
           "(Driver 2 x 0.30)] x 10")
FORMULA_AUTHORITY = "HP_Tech_Landscape_Confidence_Scoring_Logic_FINAL.docx"

# The three band values each driver may take. Anything else is a bug.
DIRECT_FIT = 10
RELATED_FIT = 5
NO_FIT = 0

BAND_VALUES = (NO_FIT, RELATED_FIT, DIRECT_FIT)


def confidence(driver_1: int, driver_2: int) -> int:
    """The card's confidence percentage, 0-100.

    Returns a whole number: every reachable combination of two band values lands
    exactly on an integer, so rounding never hides a fractional result.
    """
    total = (float(driver_1) * DRIVER_1_WEIGHT
             + float(driver_2) * DRIVER_2_WEIGHT) * DRIVER_SCALE
    return round(total)


def is_publishable(driver_1: int) -> bool:
    """The document's mandatory guardrail.

    Separate from `confidence` on purpose. A caller that only reads the
    percentage would happily publish a 30% card built on intent alone, which is
    the exact outcome the guardrail exists to prevent.
    """
    return int(driver_1) > NO_FIT


# ==============================================================================
# Driver 2 - HP-Category Intent Support (30%)
# ==============================================================================

# "Matching HP-category Intent Score | Driver 2 score", verbatim. Read as
# (inclusive lower bound, points); first match wins, highest band first.
INTENT_BANDS = (
    (50, DIRECT_FIT),
    (25, RELATED_FIT),
)
INTENT_BELOW_BANDS = NO_FIT      # "0-24 or missing"


def driver_2_intent(score, category: str | None = None) -> tuple:
    """Points for the intent score of the card's OWN HP business category.

    Returns `(points, basis)`. `score` is that category's 0-100 intent score, or
    None when the account has no score for it.

    The caller must pass the score for the card's own category. The document
    names the failure it is guarding against:

        "If the Tech Landscape card is Workstation, use Astra's Workstation
        Intent Score. Do not use the 3D Printers score of 34 for a Workstation
        card."

    A missing score scores 0 rather than being treated as unknown, because the
    document puts "or missing" in the bottom band itself. Driver 2 is a
    *supporting* signal - its absence weakens a card, it does not invalidate it,
    and it can never suppress one.
    """
    label = category or "the card's HP category"

    if score is None:
        return NO_FIT, "no intent score for %s" % label
    try:
        value = float(score)
    except (TypeError, ValueError):
        return NO_FIT, "intent score for %s is not a number" % label

    for lower, points in INTENT_BANDS:
        if value >= lower:
            return points, "%s intent score %g" % (label, value)
    return INTENT_BELOW_BANDS, "%s intent score %g, below 25" % (label, value)


# The card taxonomy is seven technology categories; the intent file has five HP
# business categories. Nothing in the codebase mapped between them, so this is
# the mapping, authored here.
#
# Three categories have no HP business counterpart and are mapped to None
# deliberately rather than omitted - `client_os` and `uem_mdm` are environment
# context, and `it_security_parity` sells Wolf Security, which is not one of the
# five intent categories at all. The document is explicit about what to do:
#
#     "If none of the five available intent categories is relevant to the HP
#     opportunity, Driver 2 = 0/10; do not force an unrelated intent category
#     into the calculation."
#
# Note there is no technographic category for 3D, so CAT_3D is unreachable from
# a card. That is a gap in the card taxonomy, not in this table.
CATEGORY_TO_HP_CATEGORY = {
    "pc_laptop_brands": tm.CAT_PC,
    "workstations_compute": tm.CAT_WORKSTATION,
    "collaboration_hybrid": tm.CAT_POLY,
    "print_fleet": tm.CAT_PRINT,
    "client_os": None,
    "uem_mdm": None,
    "it_security_parity": None,
}


def hp_category_for(category_key: str) -> str | None:
    """The HP business category a Tech Landscape card belongs to, or None."""
    return CATEGORY_TO_HP_CATEGORY.get(str(category_key or "").strip().lower())


# ==============================================================================
# Driver 1 - HP-Relevant Technology Evidence (70%)
# ==============================================================================

# Technologies the HP rulebook names explicitly, and the HP route each one
# supports. Transcribed from the rules that cite concrete, detectable
# technologies - the kind of thing that appears in a technographics export.
#
# Every row carries the rule it came from so a score on screen can be traced to
# the rule that justified it, the way `product_rules.py` carries `rule_id`.
#
# `family` is what makes a 5 possible. The document scores a related technology
# 5, and its own example is Azure against a WXP card:
#
#     "Azure indicates a Microsoft/cloud technology environment, but the WXP rule
#     specifically names technologies such as Microsoft Intune, Microsoft Entra
#     ID, Power BI and Power Automate - not Microsoft Azure itself as the
#     integration signal. Therefore Azure is related evidence, but not a direct
#     Rulebook-supported WXP mapping -> 5/10."
#
# So a detected technology in the same family as a named one, for the same
# route, is a related fit. Nothing is inferred beyond that: a technology in
# neither the named set nor a named family scores 0.
ROUTE_WXP = "HP Workforce Experience Platform"
ROUTE_SUPPORT = "HP Care Pack support services"
ROUTE_DEPLOY = "HP deployment and configuration services"
ROUTE_POLY = "Poly support services"
ROUTE_IQ = "HP IQ for Enterprise"
ROUTE_WOLF = "HP Wolf Security"
ROUTE_COMPETE = "HP competitive playbook"

FAMILY_MICROSOFT_CLOUD = "microsoft cloud and workplace"
FAMILY_ENDPOINT_MGMT = "endpoint and device management"
FAMILY_BI = "business intelligence and analytics"
FAMILY_VDI = "virtual desktop and workspace"
FAMILY_OS = "desktop operating system"
FAMILY_POLY = "poly collaboration hardware"

RULEBOOK_TECHNOLOGIES = [
    # --- WXP 04: the estate itself is the signal --------------------------
    {"rule": "WXP 04", "route": ROUTE_WXP, "family": FAMILY_OS,
     "names": ("microsoft windows", "windows", "windows 10", "windows 11",
               "macos", "mac os", "android")},

    # --- WXP 07: named integrations ---------------------------------------
    {"rule": "WXP 07", "route": ROUTE_WXP, "family": FAMILY_ENDPOINT_MGMT,
     "names": ("microsoft intune", "intune", "microsoft entra id", "entra id",
               "azure ad", "azure active directory", "servicenow")},
    {"rule": "WXP 07", "route": ROUTE_WXP, "family": FAMILY_BI,
     "names": ("microsoft power bi", "power bi", "power automate", "tableau",
               "tableau software")},

    # --- CARE 10 / G 12: vPro is a hardware precondition ------------------
    {"rule": "CARE 10", "route": ROUTE_SUPPORT, "family": FAMILY_ENDPOINT_MGMT,
     "names": ("intel vpro", "vpro")},

    # --- DEPLOY 05 / 06: registration and staging -------------------------
    {"rule": "DEPLOY 06", "route": ROUTE_DEPLOY, "family": FAMILY_ENDPOINT_MGMT,
     "names": ("autopilot", "windows autopilot", "microsoft intune", "intune",
               "azure ad", "azure active directory")},
    {"rule": "DEPLOY 05", "route": ROUTE_DEPLOY, "family": FAMILY_ENDPOINT_MGMT,
     "names": ("sccm", "microsoft endpoint configuration manager",
               "configuration manager")},

    # --- DEPLOY 03: provisioning packages ---------------------------------
    {"rule": "DEPLOY 03", "route": ROUTE_DEPLOY, "family": FAMILY_VDI,
     "names": ("vmware", "vmware vsphere", "vmware esxi", "vmware horizon",
               "vmware workspace one")},

    # --- POLY 01-05 -------------------------------------------------------
    {"rule": "POLY 01", "route": ROUTE_POLY, "family": FAMILY_POLY,
     "names": ("poly", "polycom", "poly studio", "poly trio", "poly voyager")},

    # --- IQ 07 / IQ 10 ----------------------------------------------------
    {"rule": "IQ 07", "route": ROUTE_IQ, "family": FAMILY_POLY,
     "names": ("poly x32", "poly x52", "poly x72")},
    {"rule": "IQ 10", "route": ROUTE_IQ, "family": FAMILY_ENDPOINT_MGMT,
     "names": ("microsoft intune", "intune", "microsoft entra id", "entra id")},

    # --- WOLF 04 / 05: supported Windows endpoints ------------------------
    {"rule": "WOLF 04", "route": ROUTE_WOLF, "family": FAMILY_OS,
     "names": ("microsoft windows", "windows", "windows 10", "windows 11")},

    # --- Part A rule 8: the exact competitor model, and nothing looser ----
    {"rule": "Part A rule 8", "route": ROUTE_COMPETE, "family": None,
     "names": ("thinkpad x1 carbon gen 13",)},
]

# Members of a family that no rule names directly. A detection here is related
# evidence for any route a rule reaches through that family - which is how the
# document's Azure example scores 5 rather than 0.
FAMILY_MEMBERS = {
    FAMILY_MICROSOFT_CLOUD: ("microsoft azure", "azure", "microsoft 365",
                             "office 365", "sharepoint", "microsoft teams",
                             "teams", "onedrive", "exchange online"),
    FAMILY_ENDPOINT_MGMT: ("jamf", "workspace one", "mobileiron", "manageengine",
                           "ivanti", "tanium", "kandji"),
    FAMILY_BI: ("looker", "qlik", "cognos", "ibm cognos", "sap businessobjects"),
    FAMILY_VDI: ("citrix", "citrix virtual apps", "nutanix", "hyper-v"),
    FAMILY_OS: ("linux", "ubuntu", "red hat", "rhel", "centos", "debian",
                "chromeos", "chrome os", "unix"),
    FAMILY_POLY: ("logitech", "cisco webex", "webex", "zoom rooms", "jabra"),
}

# The Microsoft cloud family reaches WXP through the rules that name Intune,
# Entra ID, Power BI and Power Automate - all Microsoft workplace technologies.
# Declared explicitly rather than inferred from vendor names, so the adjacency a
# score rests on is visible and reviewable.
FAMILY_REACHES_ROUTE = {
    FAMILY_MICROSOFT_CLOUD: (ROUTE_WXP,),
    FAMILY_ENDPOINT_MGMT: (ROUTE_WXP, ROUTE_DEPLOY, ROUTE_SUPPORT, ROUTE_IQ),
    FAMILY_BI: (ROUTE_WXP,),
    FAMILY_VDI: (ROUTE_DEPLOY,),
    FAMILY_OS: (ROUTE_WXP, ROUTE_WOLF),
    FAMILY_POLY: (ROUTE_POLY, ROUTE_IQ),
}


def _normalise(text: str) -> str:
    return " ".join(str(text or "").split()).lower()


def _names_it(detected: str, names) -> str | None:
    """The rulebook name this detection matches, on a word boundary.

    Substring matching alone would let "Windows" fire inside "Windows Server
    licensing consultancy" - which is fine - but also let "teams" fire inside
    "Teamsystem", which is not. The boundary check is what keeps an accidental
    substring from establishing a rulebook fit.
    """
    for name in names:
        pattern = r"(?<![a-z0-9])%s(?![a-z0-9])" % re.escape(name)
        if re.search(pattern, detected):
            return name
    return None


def driver_1_technology(detected_technologies, route: str | None = None) -> tuple:
    """Points for how well the detected technology supports the card's HP route.

    Returns `(points, basis, matched)` where `matched` names the rule and the
    technology that decided it, so the score is traceable.

        10 - a rule for this route names the technology outright
         5 - the technology is in a family a rule for this route reaches, but no
             rule names it
         0 - neither; the card is then suppressed by `is_publishable`

    `route` narrows the question to the opportunity actually printed on the card.
    Passing None asks the looser question "does any HP route recognise this
    technology", which is the right question when a card carries no specific
    route yet.
    """
    detections = [_normalise(t) for t in (detected_technologies or []) if _normalise(t)]
    if not detections:
        return NO_FIT, "no technology detected for this card", None

    # A direct fit outranks a related one, so every detection is checked for a
    # named match before any family match is considered.
    for entry in RULEBOOK_TECHNOLOGIES:
        if route and entry["route"] != route:
            continue
        for detected in detections:
            name = _names_it(detected, entry["names"])
            if name:
                return (DIRECT_FIT,
                        "%s names %s for %s" % (entry["rule"], name, entry["route"]),
                        {"rule": entry["rule"], "technology": name,
                         "route": entry["route"], "fit": "direct"})

    for family, members in FAMILY_MEMBERS.items():
        routes = FAMILY_REACHES_ROUTE.get(family) or ()
        if route and route not in routes:
            continue
        for detected in detections:
            name = _names_it(detected, members)
            if name:
                reached = route or (routes[0] if routes else None)
                return (RELATED_FIT,
                        "%s is %s, related to the technologies the rulebook "
                        "names for %s" % (name, family, reached),
                        {"rule": None, "technology": name, "route": reached,
                         "fit": "related", "family": family})

    return (NO_FIT,
            "no HP rulebook rule names or relates to %s" % ", ".join(detections[:3]),
            None)


def driver_1_for_card(detected_technologies, route: str | None,
                      hp_opportunity: str | None) -> tuple:
    """Driver 1 for a card that already carries an HP opportunity.

    `driver_1_technology` answers the narrow question "does a rulebook rule name
    this technology". That is the 10 band, and on its own it is far too strict to
    be the whole driver - it scores 0 for anything the rulebook does not name,
    and the rulebook names perhaps thirty technologies while a technographics
    export carries hundreds.

    The document does not intend that. Its 5 band is broad:

        "The detected technology is clearly related to the same technology
        environment/use case, but that specific technology is not explicitly
        mapped to the HP opportunity in the Rulebook. It provides useful
        supporting evidence, but the relationship is indirect."

    and its only example of a 0 is a deliberate mismatch - VMware detected
    against a proposed 3D-printing card, where "the Rulebook provides no
    supported connection".

    So 0 is for a technology that does not belong to the card's use case at all,
    not for one the rulebook simply never listed. **The card's own category is
    the use case**: a vendor sits on the IT Security card because it is security
    software, and the HP opportunity there is Wolf Security. Same environment,
    indirect relationship - which is the 5 band exactly.

    Hence: a named technology scores 10; any other technology on a card that
    carries an HP opportunity scores 5; a card with no HP opportunity to relate
    to scores 0 and is suppressed.
    """
    points, basis, matched = driver_1_technology(detected_technologies, route)
    if points > NO_FIT:
        return points, basis, matched

    detections = [_normalise(t) for t in (detected_technologies or []) if _normalise(t)]
    if not detections:
        return NO_FIT, "no technology detected for this card", None

    if hp_opportunity:
        return (RELATED_FIT,
                "%s sits in the same technology environment as the card's HP "
                "opportunity (%s); the rulebook does not name it directly"
                % (detections[0], hp_opportunity),
                {"rule": None, "technology": detections[0],
                 "route": hp_opportunity, "fit": "related"})

    return (NO_FIT,
            "the rulebook connects %s to no HP opportunity in this category"
            % ", ".join(detections[:3]),
            None)
