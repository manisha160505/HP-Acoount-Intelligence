# -*- coding: utf-8 -*-
"""Load HP customer case studies as a proof-point corpus.

Run from hp-backend:
    python scripts/load_case_studies.py                # dry run, writes nothing
    python scripts/load_case_studies.py --apply        # write to MongoDB
    python scripts/load_case_studies.py --limit 5      # enrich only 5, to try it

Five features in this platform were built around a proof point and have shipped
empty since: the Objection Playbook and Opportunity Map hardcode
`hp_proof_point: None`, Content Studio falls back to "No HP proof point is
attached to this account yet", Content Messaging has a whole `proof_points`
subsystem with nothing to feed it, and Strategy Chat already indexes the field.
This is the corpus they were waiting for.

## Why the model is involved at all

The structured columns of `hp_case_studies_final.csv` are clean - customer,
industry, product, URL. The prose columns are wreckage:

    title:    "Objectives"  /  "INDUSTRY:"  /  "Bowman set to disrupt bearing"
    use_case: "device management"  /  "with reduced packaging and"
    outcome:  "approximately 66%."  /  "printer fleet by 30%"
    metrics:  "75%; 50%; 70%; 000%"          <- 000% is a parse artefact

Real material is in there - "Reduces staging times by 90%", "15% drop in device
failures", NASA, Siemens, Carlsberg, City of Bonn - mixed with sentence
fragments, page furniture and HP spec-sheet boilerplate that repeats across
rows. Rendering that raw is not an option; discarding it wastes the corpus. So
the model rewrites each row into usable prose, **once, here**, rather than every
feature doing it per card per account per regeneration.

## Why every number is checked afterwards

The model is asked to use only figures present in its input, and then not
trusted about it. Each generated sentence is checked against a corpus built from
that one study's own fields, and a figure that is not there blanks the field it
appeared in.

This is `services/hp/recommendations.py`'s pattern - prose about a product is
verified against that product's approved facts, never against the account's
data - applied per study. It matters more here than almost anywhere else in the
product: these sentences are rendered under HP's name, next to a link to HP's
own page, on a card a seller may forward to a customer.

## Why a separate collection

`hp_product_knowledge` holds extracted slides from HP decks, which are HP
Confidential and carry country restrictions and embargo dates. Case studies are
public hp.com pages. Keeping them apart stops a confidentiality marking being
applied to rows that do not carry one, and stops a public URL being attached to
a claim that came from a confidential deck.

Nothing here writes raw source prose into the database without it having passed
the number check first.
"""

import argparse
import csv
import hashlib
import json
import logging
import os
import re
import sys
from datetime import UTC, datetime

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

from app.core.llm import generate_gpt4o_json_completion  # noqa: E402
from app.services.extractors.grounding import corpus_from_texts  # noqa: E402

logger = logging.getLogger("load_case_studies")

COLLECTION = "hp_case_studies"
VERSION_DOC_ID = "__knowledge_version__"

# Bump when the enrichment prompt or the cleaning rules change shape, so the
# knowledge version moves even if the CSV has not.
#   1 - first load: locale dedupe, confidence gate, model enrichment
#   2 - outcome_metrics withheld from the model, and an explicit rule that an
#       outcome must be something the customer achieved WITH HP - a Deloitte
#       survey stat sitting near their name was being attributed to them
#   3 - a customer's rows are MERGED rather than one being picked. They hold
#       different fragments of one story, and picking the richest lost the rest
#   4 - rows with no product tag are kept, and the model names the HP offering
#       from HP's own text. The tag is absent on 14 named-customer studies and
#       wrong on others, so it cannot be the only way in.
EXTRACTOR_VERSION = 6

_HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_CSV = os.path.abspath(os.path.join(
    _HERE, "..", "..", "additional_data", "hp_case_studies_final.csv"))

# ==============================================================================
# Cleaning - every rule below was measured against the real file
# ==============================================================================

# The same study appears once per language: Aereco is six rows, English, German,
# Spanish, French and Korean. The locale is in the URL.
_LOCALE_RE = re.compile(r"/([a-z]{2}-[a-z]{2})-")
_ENGLISH_PREFIXES = ("us-", "en-")

# `customer` carries a placeholder on roughly half the file, and on four rows it
# carries an HP page title instead of a company - "HP® Official Site",
# "Women in Tech". Neither is a customer, and naming one as a reference would be
# worse than showing no proof point.
_PLACEHOLDER_CUSTOMERS = {"enterprise customer", "nan", "", "none"}
_NOT_A_CUSTOMER = re.compile(
    r"HP®|Official Site|United Kingdom|^HP\s|Case Stud|Women in Tech", re.I)

# Below this the extractor was unsure who the customer was, and a proof point
# naming the wrong company is worse than none.
MIN_CUSTOMER_CONFIDENCE = 0.9

# Page furniture the extractor swept up as content. Passed to the model as
# things to ignore rather than stripped here, because it appears mid-string as
# often as at the edges.
# Below this many words of prose, after page furniture is removed, there is
# objectively nothing to read and the model is not called at all. Ten rows sit
# here and none has more than nine words - "IAM 3D HUB", "CSX", "NCS 3D".
#
# It is deliberately low, because length turned out to be the wrong instrument
# for the real problem. The City of Bonn row carries 36 words - a photograph
# caption ("The 72-meter-high city hall is the headquarters of the
# municipality...") and one clause clipped mid-word ("hat's especially
# well-developed in terms of security and the integrated virtual features of all
# current") - and from it the model wrote "HP supported the City of Bonn with
# security and virtual integration solutions", asserting an engagement the text
# never describes. thinkTEC 3D carries 37 words and one of them is a real
# result: "the 3D printed Pick-and-place EOAT with five rails is 80% lighter
# than its conventional counterpart". Stripping HP spec boilerplate that repeats
# across customers does not separate the two either - Bonn's caption is Bonn's
# own. No word count can tell those apart, so a floor set high enough to catch
# Bonn discards thinkTEC's outcome with it.
#
# What separates them is whether the text describes an HP engagement at all, and
# that is a reading task. So the model is asked, and `describes_engagement`
# below carries its answer; Python decides what happens next.
MIN_SUBSTANCE_WORDS = 10

PAGE_FURNITURE = ("Objectives", "INDUSTRY:", "COUNTRY:", "CASE STUDY |",
                  "FALLSTUDIE |", "CASO PRÁCTICO |", "ÉTUDE DE CAS |",
                  "HP® Official Site", "Customer Case Study")

# Columns deliberately NOT stored:
#   outcome_metrics     - a bare list of percentages with no sentence around
#                         them, and it contains parse artefacts like "000%"
#   solution_categories - all 192 `hp_route = "3D Printing"` rows are tagged
#                         "Print / Managed Print"; joining on it would file
#                         every 3D study behind a print recommendation


def _text(value) -> str:
    text = "" if value is None else str(value)
    text = " ".join(text.split())
    return "" if text.lower() in ("nan", "none", "null") else text


def _is_english(url: str) -> bool:
    match = _LOCALE_RE.search(str(url or ""))
    return (match is None) or match.group(1).startswith(_ENGLISH_PREFIXES)


def _float(value, default=0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def read_rows(path: str) -> list[dict]:
    with open(path, encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def clean(rows: list[dict]) -> tuple[list[dict], dict]:
    """The studies worth enriching, and a tally of why the rest were dropped."""
    dropped: dict = {}

    def drop(reason):
        dropped[reason] = dropped.get(reason, 0) + 1

    kept = []
    for row in rows:
        customer = _text(row.get("customer"))
        if not _is_english(row.get("canonical_url") or row.get("source_url")):
            drop("a non-English language variant of another row")
            continue
        if customer.lower() in _PLACEHOLDER_CUSTOMERS:
            drop("customer is the 'Enterprise Customer' placeholder")
            continue
        if _NOT_A_CUSTOMER.search(customer):
            drop("customer is an HP page title, not a company")
            continue
        if _float(row.get("customer_confidence")) < MIN_CUSTOMER_CONFIDENCE:
            drop("customer name below the confidence floor")
            continue
        # A missing product tag is NOT a reason to drop a study. Fourteen rows
        # with a named, high-confidence customer carry none - including Ulster
        # University, whose title reads "Unified Collaboration and Communication
        # Case Study" and which is the only collaboration study in the file.
        # The model reads the offering out of HP's own text instead; see
        # `hp_offering` below.
        kept.append(row)

    # One study per customer per product - but MERGED, not picked.
    #
    # The file carries several assets per customer, and they hold different
    # fragments of the same story rather than copies of it. Aereco has six rows:
    # one says "enhance their production processes and develop prototypes", a
    # second "prototypes, and final parts", a third mentions tooling. Keeping
    # the single richest row threw away five-sixths of what was known about
    # them, and the client's own worked example - Aereco used for "jigs,
    # fixtures, prototypes and final parts" - could not be reproduced from what
    # survived.
    #
    # So every fragment for a customer is collected and the model is given all
    # of them at once.
    groups: dict = {}
    for row in kept:
        key = (_text(row.get("customer")).lower(),
               _text(row.get("product_featured")).lower())
        groups.setdefault(key, []).append(row)

    merged = [_merge(rows) for rows in groups.values()]
    dropped["a duplicate asset, merged into the customer's other rows"] = (
        len(kept) - len(merged))
    return merged, dropped


def _merge(rows: list[dict]) -> dict:
    """One record per customer and product, holding every fragment they have.

    The industry is taken by majority rather than from whichever row happens to
    win. Aereco is labelled "Industrial Manufacturing" on four rows and
    "Technology" on two; picking one row stored the minority answer and cost it
    every industry match against a manufacturer.
    """
    base = dict(rows[0])

    industries = [_text(r.get("industry")) for r in rows if _text(r.get("industry"))]
    if industries:
        base["industry"] = max(set(industries), key=industries.count)

    # Every distinct fragment, longest first so the model reads the most
    # informative version of a repeated line before its truncations.
    for field in ("title", "use_case", "outcome_claimed"):
        seen, parts = set(), []
        for value in sorted((_text(r.get(field)) for r in rows), key=len, reverse=True):
            key = value.lower()
            if value and key not in seen and not any(key in s for s in seen):
                seen.add(key)
                parts.append(value)
        base[field] = " | ".join(parts)

    tags = []
    for row in rows:
        for tag in _text(row.get("account_signal_match")).split(";"):
            if tag.strip() and tag.strip() not in tags:
                tags.append(tag.strip())
    base["account_signal_match"] = "; ".join(tags)

    # The richest asset's link, so the seller lands on the fullest version.
    best_url = max(rows, key=lambda r: len(_text(r.get("outcome_claimed"))))
    base["source_url"] = _text(best_url.get("source_url")) or base.get("source_url")
    base["merged_from"] = len(rows)
    return base


# ==============================================================================
# Enrichment
# ==============================================================================

SYSTEM_PROMPT = """You rewrite one HP customer case study into clean, usable prose for a sales platform.

The input is a row from a machine-extracted CSV. Its structured fields are reliable. Its prose fields are damaged: sentences are cut off mid-clause, page furniture has been swept up as content, and some rows carry HP spec-sheet boilerplate instead of anything about the customer.

Your job is to recover what is genuinely there and write it properly. You are not summarising a document you can see - you only have these fields.

RULES, all mandatory:

1. NEVER state a figure that does not appear in the input. Not a rounded version, not a restated one. If the input says "90%" you may write 90%. If it says nothing, your sentence contains no number. Every number you write is checked afterwards against the input, and a sentence with an unsupported figure is discarded.

2. IGNORE PAGE FURNITURE. Strings like "Objectives", "INDUSTRY:", "COUNTRY:", "CASE STUDY |", "Customer Case Study", "HP® Official Site" are layout from the source page, not content. Never repeat them and never treat them as the customer's words.

3. IGNORE HP PRODUCT BOILERPLATE. Text like "HP Jet Fusion 3D Printing Solutions using HP 3D High Reusability PA 12 provide up to 80% powder reusability" is a spec-sheet line that repeats across many unrelated studies. It says nothing about THIS customer, so it is not an outcome.

3b. SOME FIELDS START PARTWAY THROUGH A SENTENCE, and the missing half is usually what the figure was about. "inspections can be as high as 20%2." is a footnoted statistic about how bad manual inspection error rates are - writing "inspections improved by up to 20%" turns a problem into a result. If you cannot see what a number refers to, do not use it.

4. AN OUTCOME IS SOMETHING THIS CUSTOMER ACHIEVED WITH HP. Nothing else is. Return null for "outcome" when the input offers only:
   - a third-party statistic that happens to sit near the customer's name ("A recent Deloitte study revealed that 86% of...") - that is an industry survey, not this customer's result, and attributing it to them would be false
   - a fact about the customer's own business ("It holds an overall market share of 20% in Bern") - true of them, but not something HP did
   - a general HP claim ("HP already delivers reduced product packaging") - true of HP everywhere, so it says nothing about this engagement
   A headline and a use case with no outcome is a good record. A wrong outcome under a real customer's name is not.

5. SAY SO WHEN THE INPUT DESCRIBES NO ENGAGEMENT. Some rows carry no account of anything HP did - a photograph caption, a page heading, a sentence clipped mid-word, a stray quote. Set "describes_engagement" to false for those and leave every prose field null. You are not being asked to make the best of it: something else will state the attribution. Set it to true only if the input actually says something about what this customer did with HP.

6. A NULL IS A COMPLETE ANSWER. If the input does not support a field, return null for it. A study that yields only a headline is useful - it still names a real HP customer a seller can point to. Do not pad, do not speculate, do not infer a challenge from the industry.

7. NAME THE HP OFFERING FROM THE TEXT, NOT THE TAG. The supplied `product_featured` is often absent and sometimes wrong - one study tagged "HP EliteBook" is entirely about HP Managed Device Services. Read what the title and use case actually describe. If they name no HP offering, return null; do not fall back to the tag.

8. Write plainly, in the third person, for a salesperson to read. No marketing language: no "revolutionary", "game-changing", "seamless", "unlock". Do not address the reader.

Return JSON only:
{
  "describes_engagement": true or false - see rule 5,
  "headline": "One line: what HP did, for whom, to what end. Always present.",
  "challenge": "The problem this customer had, in one or two sentences, or null.",
  "outcome": "What changed, as a proper sentence, using only figures from the input, or null.",
  "use_case": "The use case in plain words - what the product was actually used for - or null.",
  "why_relevant": "One sentence: the situation where a seller would reach for this example. Null if the input is too thin to say.",
  "hp_offering": "The HP product, service or solution this study is about, in HP's own words from the text - for example 'HP Managed Device Services', 'Poly Collaboration', 'HP Multi Jet Fusion'. Null if the text does not name one."
}"""

ENRICHED_FIELDS = ("headline", "challenge", "outcome", "use_case",
                   "why_relevant", "hp_offering")

# The raw fields the model is shown, and the same fields every generated number
# is checked against. One list so the two can never drift - a number can only be
# rejected for being absent from something the model was never given.
#
# `outcome_metrics` is deliberately NOT here. It is a bare semicolon list with no
# sentence around it - "86%; 100%; 80%; 17%" - and shown to the model it produced
# sentences like "achieved 86% efficiency, with additional metrics of 100%, 80%
# and 17%": invented precision assembled from numbers whose meaning nobody
# recorded. It also contains parse artefacts such as "000%". Excluding it means a
# figure can only be used if it appeared in real prose, which is the only place
# its meaning survives.
SOURCE_FIELDS = ("title", "use_case", "outcome_claimed",
                 "customer", "industry", "product_featured", "hp_route")


# The three damaged columns. The structured ones beside them are reliable.
PROSE_FIELDS = ("title", "use_case", "outcome_claimed")


def _begins_mid_sentence(value) -> bool:
    """True when a field starts partway through a sentence.

    The extractor clipped many rows at a character offset rather than a
    boundary, so a field can open mid-clause or even mid-word: "hat's
    especially well-developed in terms of security", "inspections can be as
    high as 20%2.". The first word of the real sentence - and with it the
    subject the figure belongs to - is simply gone.
    """
    text = " ".join(str(value or "").split())
    for char in text:
        if char.isalpha():
            return char.islower()
        if char.isdigit():
            return False
    return False


def _verifiable_texts(row: dict) -> list:
    """The source text a generated figure may be checked against.

    A clipped field is excluded, because a number in one cannot be read safely.
    The Inovako row carried `outcome_claimed = "inspections can be as high as
    20%2."` - a footnoted industry statistic about how bad manual inspection
    error rates are - and the model restated it as "Vehicle inspections can be
    improved by up to 20%", turning the problem into the result. The figure
    check passed it, because 20% was indeed present: presence was never the
    question, and this is where the check stops being able to help.

    The model still SEES these fields - they carry real meaning about the
    engagement - it just cannot quote a figure out of one, because a sentence
    written from the surviving half will be rejected as unsourced.
    """
    return [_text(row.get(field)) for field in SOURCE_FIELDS
            if not (field in PROSE_FIELDS and _begins_mid_sentence(row.get(field)))]


def _user_prompt(row: dict) -> str:
    payload = {field: _text(row.get(field)) for field in SOURCE_FIELDS}
    return ("Rewrite this case study.\n\n"
            + json.dumps(payload, ensure_ascii=False, indent=1)
            + "\n\nIgnore any of these that appear, they are page layout: "
            + ", ".join(PAGE_FURNITURE))


def substance_words(row: dict) -> int:
    """Words of prose in a row once page furniture is removed."""
    text = " ".join(_text(row.get(f)) for f in
                    ("title", "use_case", "outcome_claimed"))
    for furniture in PAGE_FURNITURE:
        text = text.replace(furniture, " ")
    return len([w for w in text.split() if any(c.isalpha() for c in w)])


def attribution_only(row: dict) -> dict:
    """The record for a study too thin to narrate.

    Everything here comes from the structured columns, which are reliable, and
    the model is not called. The claim made is the only one the row supports:
    HP published this case study about this customer. The product named is HP's
    own tag, and it is not asserted that the study's text says so - it is left
    in `product_featured` where it already was, which is also where
    `canonical_line` looks when no offering was read from the text.

    A record like this is still a usable proof point. It names a real HP
    customer and carries the public hp.com link a seller can forward, which is
    more than an empty slot and less than a sentence nobody can source.
    """
    customer = _text(row.get("customer"))
    product = _text(row.get("product_featured"))
    return {
        "attribution_only": True,
        "headline": ("HP published a case study with %s featuring %s."
                     % (customer, product) if product
                     else "HP published a case study with %s." % customer),
    }


def enrich(row: dict) -> tuple[dict, list[str]]:
    """Model-written fields for one study, and the ones rejected as unsourced.

    Every figure is checked against the study's own raw fields. A field whose
    sentence carries an unsupported number is dropped entirely rather than
    edited - a half-corrected claim is harder to spot than a missing one.
    """
    result = generate_gpt4o_json_completion(SYSTEM_PROMPT, _user_prompt(row))
    if not isinstance(result, dict):
        return {}, ["the model returned nothing usable"]

    # The model read the source and says it describes no engagement. Its prose
    # fields are discarded unread rather than salvaged: a sentence written from
    # a photograph caption is wrong however well it reads.
    if result.get("describes_engagement") is False:
        return attribution_only(row), []

    corpus = corpus_from_texts(_verifiable_texts(row))

    enriched, rejected = {}, []
    for field in ENRICHED_FIELDS:
        sentence = _text(result.get(field))
        if not sentence:
            continue
        unsourced = corpus.unsourced_numbers(sentence)
        if unsourced:
            rejected.append("%s: %s" % (field, ", ".join(unsourced)))
            continue
        enriched[field] = sentence
    return enriched, rejected


# ==============================================================================
# Documents
# ==============================================================================

def _study_id(row: dict) -> str:
    """Stable across reloads, so an upsert updates rather than duplicates.

    Built from customer and product rather than `case_study_id`, which has 357
    distinct values across 384 rows and is not unique.
    """
    key = "%s::%s" % (_text(row.get("customer")).lower(),
                      _text(row.get("product_featured")).lower())
    return hashlib.sha1(key.encode("utf-8")).hexdigest()[:16]


def build_document(row: dict, enriched: dict, rejected: list) -> dict:
    return {
        "_id": _study_id(row),
        # Structured fields, trusted as-is.
        "customer": _text(row.get("customer")),
        "industry": _text(row.get("industry")),
        "product_featured": _text(row.get("product_featured")),
        "hp_route": _text(row.get("hp_route")) or None,
        "signal_tags": [t.strip() for t in
                        _text(row.get("account_signal_match")).split(";") if t.strip()],
        "source_url": _text(row.get("source_url")) or None,
        "asset_type": _text(row.get("asset_type")) or None,
        # Model-written, every figure verified against the row above.
        **{field: enriched.get(field) for field in ENRICHED_FIELDS},
        # What was rejected, kept so a thin record is explicable rather than
        # looking like the model simply had nothing to say.
        # True when the source was too thin to narrate, so the headline states
        # the attribution and nothing else. Stored rather than inferred from the
        # absent fields, because "the model had nothing to say" and "we did not
        # ask it" are different facts about the same empty record.
        "attribution_only": bool(enriched.get("attribution_only")),
        "rejected_for_unsourced_figures": rejected or None,
        "source_case_study_id": _text(row.get("case_study_id")) or None,
        "merged_from_assets": row.get("merged_from", 1),
        "extractor_version": EXTRACTOR_VERSION,
        "confidential": False,     # public hp.com pages, unlike the decks
    }


def knowledge_version(docs: list) -> str:
    """SHA-256 over the stored prose plus the extractor version.

    Mirrors `extract_hp_decks.py`: a downstream fingerprint that includes this
    regenerates when the corpus is reloaded with corrected text.
    """
    payload = json.dumps(
        [{"id": d["_id"], **{f: d.get(f) for f in ENRICHED_FIELDS}}
         for d in sorted(docs, key=lambda x: x["_id"])],
        sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(
        (payload + "|v%d" % EXTRACTOR_VERSION).encode("utf-8")).hexdigest()


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--csv", default=DEFAULT_CSV)
    ap.add_argument("--apply", action="store_true", help="write; otherwise dry run")
    ap.add_argument("--limit", type=int, default=0,
                    help="enrich only the first N studies, to try the prompt")
    ap.add_argument("--show", type=int, default=3,
                    help="print this many before/after samples")
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    if not os.path.isfile(args.csv):
        sys.exit("No case-study CSV at %s" % args.csv)

    rows = read_rows(args.csv)
    studies, dropped = clean(rows)
    print("read %d rows -> %d studies after cleaning" % (len(rows), len(studies)))
    for reason, count in sorted(dropped.items(), key=lambda kv: -kv[1]):
        if count:
            print("   %4d dropped: %s" % (count, reason))

    if args.limit:
        studies = studies[:args.limit]
        print("\nenriching only the first %d" % len(studies))

    print("\nenriching with gpt-4o ...")
    docs, thin, all_rejected, attribution = [], 0, 0, 0
    for i, row in enumerate(studies, 1):
        if substance_words(row) < MIN_SUBSTANCE_WORDS:
            # No model call: fewer than ten words of prose is nothing to read.
            enriched, rejected = attribution_only(row), []
        else:
            enriched, rejected = enrich(row)
        if enriched.get("attribution_only"):
            attribution += 1
        all_rejected += len(rejected)
        if not enriched.get("headline"):
            thin += 1
        docs.append(build_document(row, enriched, rejected))
        if i % 10 == 0 or i == len(studies):
            print("   %d/%d" % (i, len(studies)))

    print("\n%d studies | %d attribution-only (the source describes no "
          "engagement) | %d with no headline | %d field(s) rejected for "
          "unsourced figures"
          % (len(docs), attribution, thin, all_rejected))

    for doc, row in list(zip(docs, studies, strict=False))[:args.show]:
        print("\n" + "-" * 78)
        print("%s - %s (%s)" % (doc["product_featured"], doc["customer"],
                                doc["industry"]))
        print("  BEFORE title   : %s" % _text(row.get("title"))[:96])
        print("  BEFORE outcome : %s" % _text(row.get("outcome_claimed"))[:96])
        for field in ENRICHED_FIELDS:
            if doc.get(field):
                print("  %-14s : %s" % (field, doc[field][:96]))
        if doc.get("rejected_for_unsourced_figures"):
            print("  REJECTED       : %s" % doc["rejected_for_unsourced_figures"])

    version = knowledge_version(docs)
    print("\nknowledge_version: %s" % version)

    if not args.apply:
        print("\nDry run. Nothing written. Re-run with --apply to store.")
        return

    from app.database.mongodb import connect_to_mongo, get_db
    connect_to_mongo()
    db = get_db()
    now = datetime.now(UTC)
    col = db[COLLECTION]

    for doc in docs:
        doc["loaded_at"] = now
        doc_id = doc.pop("_id")
        col.update_one({"_id": doc_id}, {"$set": doc}, upsert=True)
        doc["_id"] = doc_id

    # A study that has left the CSV must not linger. The version sentinel is
    # excluded explicitly or the write below would delete it.
    live = {d["_id"] for d in docs} | {VERSION_DOC_ID}
    removed = col.delete_many({"_id": {"$nin": list(live)}}).deleted_count

    col.update_one(
        {"_id": VERSION_DOC_ID},
        {"$set": {"knowledge_version": version,
                  "extractor_version": EXTRACTOR_VERSION,
                  "study_count": len(docs),
                  "updated_at": now}},
        upsert=True)

    print("wrote %d studies, removed %d stale" % (len(docs), removed))


if __name__ == "__main__":
    main()
