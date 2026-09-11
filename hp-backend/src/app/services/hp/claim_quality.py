"""Deterministic quality filter for extracted deck claims.

The extractor pulls every text line off a slide. Much of it is not a fact a
seller can stand behind: "The gold standard trusted by business, preferred by
IT" is positioning, "Forward-looking statements" is legal boilerplate, and
"HP EliteBook 8 G2i 14-inch Next Gen AI PC" is a product name. Those were
reaching the approved-fact list, where they would have been quoted back as
evidence.

No language model is used here. A claim is kept when it carries at least one
concrete signal and trips no rejection signal. Concrete deliberately does NOT
mean "contains a number": "HP Wolf Security", "requires Windows 11" and
"Sure View is optional" are all specific and useful without one.

Nothing about a retained claim is rewritten - exact text, footnote links,
qualifiers, restrictions, model binding and provenance all pass through
untouched. This stage only decides keep or drop, and merges equivalents.
"""

import hashlib
import re

# ---------------------------------------------------------------------------
# Concrete signals. Any one of these makes a line a candidate fact.
# ---------------------------------------------------------------------------

# A measurement with a unit. Bare integers are excluded on purpose - "8" in
# "EliteBook 8" is a product name, not a specification.
MEASUREMENT_RE = re.compile(
    r"\d+\s*(?:TOPS|GB|TB|MB|Wh|W\b|kg|g\b|mm|cm|inch|inches|\"|MP\b|GHz|MHz|"
    r"dBA|nits|Hz|%|hours?|hrs?|minutes?|mins?|cores?|slots?|ports?|displays?|"
    r"bays?|lanes?|years?)", re.I)

# Named features and capabilities. HP product vocabulary, not account data.
FEATURE_TERMS = [
    "hp wolf security", "wolf pro security", "sure view", "sure recover",
    "sure run", "sure start", "sure sense", "sure click", "tamper lock",
    "client security manager", "endpoint security controller", "secured-core",
    "microsoft pluton", "tpm", "dtpm", "bios", "firmware",
    "poly studio", "poly camera pro", "magic background", "ai companion",
    "human presence detection", "onlooker detection", "noise reduction",
    "echo cancellation", "ir camera", "facial recognition", "fingerprint",
    "intel core ultra", "core ultra", "ryzen", "snapdragon", "vpro", "npu",
    "copilot", "rtx", "nvidia", "radeon", "ddr5", "sodimm", "m.2", "ssd",
    "thunderbolt", "usb-c", "usb type-c", "displayport", "power delivery",
    "rj-45", "kensington", "wi-fi", "bluetooth", "5g", "hp go", "lte",
    "epeat", "energy star", "tco certified", "recycled", "ocean-bound",
    "post-consumer", "packaging", "smart sense", "flex io", "flex module",
    "kvm", "device switch", "articulating stand", "spill-resistant",
    "haptic trackpad", "oled", "sure start", "remote manageability",
    "power consumption measurement", "single power on", "toolless",
    "serviceable", "serviceability", "manageability", "repairable",
    "intrusion sensor", "battery", "camera", "keyboard",
    "processor", "memory", "storage", "graphics", "display", "chassis",
]
FEATURE_RE = re.compile(
    r"\b(" + "|".join(re.escape(t) for t in sorted(FEATURE_TERMS, key=len, reverse=True))
    + r")\b", re.I)

# Compatibility, availability and support statements.
#
# Deliberately excludes bare "supports" and "designed to": both are ordinary
# marketing verbs. "Designed to support how and where you work" was passing as
# a specification on their strength alone. Support here has to be stated as a
# condition - supported ON something, required, optional, up to.
SUPPORT_RE = re.compile(
    r"\b(requires?|required|supported (?:on|by|in|with)|compatible with|"
    r"available (?:on|in|with)|works with|configured|enabled by|"
    r"only (?:on|with|in)|where (?:supported|stated|available)|"
    r"not available in|subject to|sold separately|optional|up to|"
    r"standard on|included with)\b", re.I)

# ---------------------------------------------------------------------------
# Rejection signals.
# ---------------------------------------------------------------------------

# Positioning and slogans, taken from the decks themselves.
MARKETING_RE = re.compile(
    r"gold standard|trusted by business|preferred by it|raw power|"
    r"stops what others can.?t see|break down barriers|get more out of|"
    r"delighters|purpose-?built|thoughtfully tailored|shared future|"
    r"limitless|stay in your flow|done right|effortlessly|seamless(?:ly)?|"
    r"unmatched|unparalleled|world-?class|iconic|complete the ecosystem|"
    r"elevate|empower|unleash|reimagine|game[- ]chang|next level|"
    r"peace of mind|built for what.?s next|more out of your fleet|"
    r"adaptable ai pc|power that fits", re.I)

# Legal, forward-looking and housekeeping text.
BOILERPLATE_RE = re.compile(
    r"forward.?looking statement|subject to change without notice|"
    r"all product views|illustrations? and might not|images are not final|"
    r"placement only|actual prices may vary|regional availability|"
    r"hp confidential|cda only|^\s*disclaimers?\s*$|^\s*sources?\s*:|"
    r"^\s*change log|embargo|for complete details|see data sheet|"
    r"^\s*learn more|^\s*click here|font", re.I)

# A line that is only a product name. "HP EliteBook 8 G2i 14-inch Next Gen AI
# PC" identifies a product; it does not say anything about it.
PRODUCT_NAME_ONLY_RE = re.compile(
    r"^\s*(?:hp\s+)?(?:elitebook|probook|elitedesk|prodesk|elitestudio|prostudio|"
    r"hp\s*200|z\s*by\s*hp)[\w\s/&.\-–—\"']*"
    r"(?:pc|notebook|laptop|desktop|series|tower|mini|sff|aio|all-in-one|"
    r"g\d[a-z]?\d?|flip|\d{2}(?:\.\d)?-?inch|\"\s*)?\s*$", re.I)

# Too short, or a sentence fragment that starts mid-thought.
FRAGMENT_RE = re.compile(r"^\s*(?:and|or|with|the|a|an|to|for|of|in|on|that|plus|"
                         r"your|by|from|at|as|is|are|be)\b", re.I)

MIN_WORDS = 4


def assess(claim: dict):
    """(keep, reason). `reason` names the rejection signal when dropped."""
    text = " ".join(str(claim.get("text") or "").split())
    if not text:
        return False, "empty"

    words = text.split()
    if len(words) < MIN_WORDS:
        return False, "too short"
    if FRAGMENT_RE.match(text):
        return False, "sentence fragment"
    if BOILERPLATE_RE.search(text):
        return False, "legal or housekeeping boilerplate"
    if PRODUCT_NAME_ONLY_RE.match(text):
        return False, "product name only"

    concrete = (
        bool(MEASUREMENT_RE.search(text))
        or bool(FEATURE_RE.search(text))
        or bool(SUPPORT_RE.search(text))
        or bool(claim.get("qualifiers"))
    )

    # Marketing language is only fatal when the line carries nothing concrete.
    # "Part of the world's first business PCs to protect the firmware against
    # quantum attacks" is a real capability claim wrapped in a superlative -
    # the country guardrail decides whether it may be used, not this filter.
    if MARKETING_RE.search(text) and not concrete:
        return False, "positioning language with no specification"
    if not concrete:
        return False, "no concrete specification, feature or condition"

    return True, None


def dedupe_key(claim: dict, slide: dict) -> str:
    """Identity of a claim for merging.

    Scoped by product binding AND restriction status, never by text alone:

      * the same sentence on a G1i slide and a G2 slide is two different
        claims, because guardrail 16 forbids carrying a fact across
        generations;
      * the same sentence on a superlative-restricted slide and an
        unrestricted one is also two claims, or merging them would either
        over-block the usable copy or leak the restricted one.
    """
    restrictions = slide.get("restrictions") or {}
    normalised = re.sub(r"[^a-z0-9 ]+", " ", str(claim.get("text") or "").lower())
    normalised = " ".join(normalised.split())
    parts = [
        normalised,
        str(slide.get("product_family") or ""),
        str(slide.get("generation") or ""),
        str(slide.get("form_factor") or ""),
        "S" if restrictions.get("superlative") else "-",
        "C" if restrictions.get("competitor_claims") else "-",
    ]
    return hashlib.sha1("||".join(parts).encode("utf-8")).hexdigest()[:16]


def filter_deck(slides: list):
    """Apply the quality pass across one deck's slides.

    Retained claims keep their exact text and every associated field, and gain
    `source_slides` listing every slide the claim appeared on. Duplicates are
    removed from the later slides so a fact is offered once, while its full
    provenance survives on the copy that is kept.
    """
    stats = {"kept": 0, "dropped": 0, "merged": 0, "reasons": {}}
    first_seen = {}

    for slide in slides:
        surviving = []
        for claim in slide.get("claims") or []:
            keep, reason = assess(claim)
            if not keep:
                stats["dropped"] += 1
                stats["reasons"][reason] = stats["reasons"].get(reason, 0) + 1
                continue

            key = dedupe_key(claim, slide)
            if key in first_seen:
                # Record the extra provenance on the copy already kept.
                primary = first_seen[key]
                if slide["slide_number"] not in primary["source_slides"]:
                    primary["source_slides"].append(slide["slide_number"])
                stats["merged"] += 1
                continue

            claim["claim_key"] = key
            claim["source_slides"] = [slide["slide_number"]]
            first_seen[key] = claim
            surviving.append(claim)
            stats["kept"] += 1

        slide["claims"] = surviving

    return slides, stats
