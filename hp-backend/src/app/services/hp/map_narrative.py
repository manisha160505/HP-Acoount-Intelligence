"""Per-category and per-vendor HP narrative for the Technographic Map.

The map's deterministic layer knows what was detected and what HP relationship
follows. What it cannot say is the sentence a seller actually reads:

    Jamf - Apple device management - Complement
    Elite/Pro PCs + HP Wolf Security: below-the-OS protection complements MDM
    rather than competing with it.

That is what this produces. It is generated, so it is constrained:

  * the HP line must come from the approved HP product enum - the model cannot
    invent "HP SecureEdge Pro";
  * the play is a positioning statement about the DETECTED vendor, not a
    product specification. It may not assert a spec, a figure or a comparison -
    those live in the recommendation cards, where they carry their conditions;
  * the detected vendor and its description come from the account's own
    technographics and are passed in verbatim; the model never renames them.

Written back onto the technographic_map structure rather than kept separately,
because the map is what the seller reads. The classification stays honest: the
deterministic fields are computed, the narrative fields are marked inferred on
the widget through `narrative_source`.
"""

import json
import logging

from app.core.llm import generate_gpt4o_json_completion
from app.services.extractors.grounding import (
    HP_PRODUCT_LINES,
    corpus_from_texts,
    normalize_hp_product,
)

logger = logging.getLogger(__name__)

# 2 - "what_it_means" is written to the tuning logic's 70-100 word band. Rule 6
#     said "keep it to one sentence each" two lines under a request for two to
#     three, and the shorter instruction won: the median card ran 30 words.
MAP_NARRATIVE_PROMPT_VERSION = 2

# Recommendation Tuning Logic, Technographic Map: "What It Means for HP +
# supported motion. Minimum 70 words; maximum 100 words."
MEANING_MIN_WORDS = 70
MEANING_MAX_WORDS = 100

# Wording that would turn a positioning line into an unsupported product claim.
BANNED = [
    "guarantees", "ensures", "fastest", "cheapest", "best-in-class", "the best",
    "always", "never fails", "100%", "eliminates", "proven to",
]

SYSTEM_PROMPT = """You write HP positioning for technologies ALREADY detected in an account's stack.

You get the account name, and for each category: the category name, the HP
relationship the system has already determined (Compete / Complement / Open
opportunity / Contextual), and the detected vendors with their descriptions.

Produce ONE account-level summary:
  - strategic_read: 3 to 4 sentences on the shape of this estate. Say which
    categories HP competes in, which it complements, and where the whitespace
    is. Name real categories and real detected vendors. Describe the estate as
    observed - do not say what the account plans, wants or needs.

Produce, per category:
  - what_it_means: BETWEEN 70 AND 100 WORDS on what this category means for HP.
    Name at least one vendor actually detected in that category, say what the
    stated relationship means in practice for a seller, and say which motion it
    supports - displacement, attach, upgrade, coexistence or whitespace. Be
    specific to these vendors, not to the category in the abstract. Use the room
    for the detected estate, not for restating the relationship label.

Produce, per vendor:
  - hp_product: the HP line to position, chosen ONLY from allowed_hp_products.
    Use null when no HP line genuinely applies (for example an OS or a network
    appliance).
  - play_text: ONE sentence saying how that HP line relates to THIS vendor.

RULES, all mandatory:
1. Never invent an HP product name. Use allowed_hp_products verbatim or null.
2. Never state a specification, figure, percentage, benchmark or comparison.
   No "50 TOPS", no "30% faster". This is positioning, not a datasheet.
3. Respect the relationship. Complement must not be written as displacement;
   Contextual means HP has no direct line here, so hp_product is usually null.
4. Never claim the account has a problem, plan or intention. You are describing
   a technology's relationship to HP, not the customer's state.
5. No superlatives and no guarantees.
6. "play_text" is ONE sentence. That limit is for play_text alone - it is not
   the limit for what_it_means, which has its own word band above.
7. Plain, specific, no marketing language.

Return JSON only:
{"strategic_read": "...",
 "categories": [{"category_key": "...", "what_it_means": "...",
  "vendors": [{"vendor_name": "...", "hp_product": "..." or null, "play_text": "..."}]}]}"""


def _clean(text: str) -> str:
    return " ".join(str(text or "").split())


def _is_acceptable(text: str, account_corpus) -> bool:
    """Reject banned wording and any figure the account data does not carry."""
    low = _clean(text).lower()
    if not low:
        return False
    if any(term in low for term in BANNED):
        return False
    # A positioning line has no business carrying numbers. If one appears, it
    # must at least trace to the account's own data.
    return not account_corpus.unsourced_numbers(text)


def _retry_meaning(category: dict, account_name: str, current: str,
                   account_corpus) -> str | None:
    """One rewrite of a single category's meaning, for length alone.

    Returns the new text only when it is grounded AND closer to the band than
    what it would replace - a rewrite asked for length can come back shorter,
    and publishing the worse of two valid answers would be a regression.
    """
    def miss(text):
        n = len(str(text or "").split())
        if not n:
            return 10 ** 6
        return max(MEANING_MIN_WORDS - n, n - MEANING_MAX_WORDS, 0)

    try:
        again = generate_gpt4o_json_completion(SYSTEM_PROMPT, json.dumps({
            "account_name": account_name,
            "allowed_hp_products": HP_PRODUCT_LINES,
            "note": ("Rewrite what_it_means for this one category only. The "
                     "previous answer was %d words and the brief is %d to %d. "
                     "Use the extra room for the detected vendors and the motion "
                     "they support, not for padding, and add no new fact."
                     % (len(current.split()), MEANING_MIN_WORDS, MEANING_MAX_WORDS)),
            "categories": [{
                "category_key": category.get("category_key"),
                "category_name": category.get("category_name"),
                "hp_relationship": category.get("hp_relationship_label"),
                "vendors": [{"vendor_name": v.get("vendor_name"),
                             "description": v.get("description"),
                             "is_whitespace": bool(v.get("is_whitespace"))}
                            for v in (category.get("vendors") or [])],
            }],
        }, ensure_ascii=False)) or {}
    except Exception:
        logger.exception("map narrative: meaning retry failed for %s",
                         category.get("category_key"))
        return None

    for entry in (again.get("categories") or []):
        if not isinstance(entry, dict):
            continue
        text = _clean(entry.get("what_it_means"))
        if text and _is_acceptable(text, account_corpus) and miss(text) < miss(current):
            return text
    return None


def generate_map_narrative(categories: list, account_texts: list,
                           account_name: str = "") -> dict:
    """Fill what_it_means and hp_play in place; return the strategic read too."""
    payload_categories = []
    for category in categories:
        payload_categories.append({
            "category_key": category.get("category_key"),
            "category_name": category.get("category_name"),
            "hp_relationship": category.get("hp_relationship_label"),
            "vendors": [{
                "vendor_name": v.get("vendor_name"),
                "description": v.get("description"),
                "is_whitespace": bool(v.get("is_whitespace")),
            } for v in (category.get("vendors") or [])],
        })

    user_prompt = json.dumps({
        "account_name": account_name,
        "allowed_hp_products": HP_PRODUCT_LINES,
        "categories": payload_categories,
    }, ensure_ascii=False)

    result = generate_gpt4o_json_completion(SYSTEM_PROMPT, user_prompt)
    if not result or not isinstance(result.get("categories"), list):
        logger.warning("map narrative: no usable response; leaving fields absent")
        return {"generated": 0, "rejected": [], "strategic_read": None,
                "prompt_version": MAP_NARRATIVE_PROMPT_VERSION}

    by_key = {}
    for entry in result["categories"]:
        if isinstance(entry, dict) and entry.get("category_key"):
            by_key[str(entry["category_key"])] = entry

    account_corpus = corpus_from_texts(account_texts)
    generated, rejected = 0, []

    strategic_read = _clean(result.get("strategic_read"))
    if strategic_read and _is_acceptable(strategic_read, account_corpus):
        generated += 1
    elif strategic_read:
        rejected.append("strategic_read")
        strategic_read = None

    for category in categories:
        entry = by_key.get(str(category.get("category_key"))) or {}

        meaning = _clean(entry.get("what_it_means"))
        if meaning and _is_acceptable(meaning, account_corpus):
            # Length, retried one category at a time. Asked for six at once the
            # model writes about thirty words each whatever the brief says;
            # asked for one it writes to the brief.
            if not (MEANING_MIN_WORDS <= len(meaning.split()) <= MEANING_MAX_WORDS):
                longer = _retry_meaning(category, account_name, meaning,
                                        account_corpus)
                if longer:
                    meaning = longer
            category["what_it_means"] = meaning
            category["what_it_means_word_count"] = len(meaning.split())
            generated += 1
        elif meaning:
            rejected.append("%s.what_it_means" % category.get("category_key"))

        vendor_entries = {}
        for v in (entry.get("vendors") or []):
            if isinstance(v, dict) and v.get("vendor_name"):
                vendor_entries[_clean(v["vendor_name"]).lower()] = v

        for vendor in category.get("vendors") or []:
            got = vendor_entries.get(_clean(vendor.get("vendor_name")).lower())
            if not got:
                continue

            # The HP line must resolve to a real one. normalize_hp_product
            # rejects anything that names no HP line at all.
            product = normalize_hp_product(got.get("hp_product"))
            play = _clean(got.get("play_text"))

            if not product or not play:
                continue
            if not _is_acceptable(play, account_corpus):
                rejected.append("%s.%s.play_text" % (category.get("category_key"),
                                                     vendor.get("vendor_name")))
                continue

            vendor["hp_play"] = {"product": product, "play_text": play}
            generated += 1

    return {"generated": generated, "rejected": rejected,
            "strategic_read": strategic_read,
            "prompt_version": MAP_NARRATIVE_PROMPT_VERSION}
