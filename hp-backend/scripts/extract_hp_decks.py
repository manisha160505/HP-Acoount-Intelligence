# -*- coding: utf-8 -*-
"""Extract HP product facts from the decks in products/ into Atlas.

The decks are HP Confidential ("For use by HP or Partner with Customers under
HP CDA only" appears on 159 of their 422 slides) and run to about a gigabyte of
embedded media, so they are gitignored and never committed. Only the structured
facts are stored, in the `hp_product_knowledge` collection, which is how they
reach Render without the repository carrying them.

Where the important material actually lives, found by reading the decks:

  * slide text        - the claims, each carrying inline footnote markers such
                        as "up to 50 TOPS NPU2,3" or "HP Wolf Security27"
  * speaker notes     - three different things concatenated:
                          (a) internal sales talk-track          -> dropped
                          (b) per-slide country restrictions     -> parsed
                          (c) a DISCLAIMERS block defining every
                              numbered footnote                  -> parsed

The restrictions are per slide, not per deck, exactly as the HP rules document
requires ("Store these restrictions at claim level, not only at document
level"). A single EliteBook 8 G2 slide names Indonesia twice, under both EMEA
and APJ - which is why Astra, in Jakarta, cannot receive those superlatives.

Usage, from hp-backend/:

    python scripts/extract_hp_decks.py            # dry run, writes nothing
    python scripts/extract_hp_decks.py --apply

Nothing here logs claim text; slide identifiers only.
"""
import argparse
import hashlib
import io
import json
import logging
import os
import re
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

from pptx import Presentation                      # noqa: E402
from app.database.mongodb import get_db            # noqa: E402
from app.services.hp.claim_quality import filter_deck   # noqa: E402

logger = logging.getLogger("extract_hp_decks")

# Bump when the parsing changes shape, so knowledge_version moves even if the
# decks themselves have not.
#   2 - added the deterministic claim-quality pass (claim_quality.filter_deck)
EXTRACTOR_VERSION = 2

DECK_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "..", "products")

COLLECTION = "hp_product_knowledge"
VERSION_DOC_ID = "__knowledge_version__"

# ---------------------------------------------------------------------------
# Slides that are scaffolding rather than product content.
# ---------------------------------------------------------------------------
SKIP_SLIDE_PATTERNS = [
    re.compile(r"^\s*change log", re.I),
    re.compile(r"how to install fonts", re.I),
    re.compile(r"^\s*thank you\s*$", re.I),
    re.compile(r"download and install HP Forma", re.I),
]

CONFIDENTIAL_RE = re.compile(r"HP Confidential|CDA only", re.I)

# "under sales and press embargo until March 24th 2026"
EMBARGO_RE = re.compile(
    r"embargo(?:ed)?\s+until\s+"
    r"([A-Z][a-z]+\s+\d{1,2}(?:st|nd|rd|th)?,?\s+\d{4}"
    r"|\d{1,2}\s+[A-Z][a-z]+\s+\d{4})", re.I)

# The notes split into talk-track and the numbered footnote definitions.
DISCLAIMER_SPLIT_RE = re.compile(r"^\s*_*\s*DISCLAIMERS?\s*_*\s*$", re.I | re.M)
FOOTNOTE_DEF_RE = re.compile(r"^\s*(\d{1,3})[ivx]*\.\s+(.+?)(?=^\s*\d{1,3}[ivx]*\.\s+|\Z)",
                             re.M | re.S)

# Restriction detection.
#
# HP writes the country lists as run-on prose with inconsistent punctuation
# ("...Saudi Arabia-do NOT use Middle East, Mediterranean and Africa (MEMA) -
# DO NOT USE: Middle East: Turkey, ..."), so parsing them by punctuation is
# unreliable - an early attempt captured a 99,000-character blob. What IS
# reliable is the sentence that says which KIND of restriction the slide
# carries. That is detected here; the authoritative country lists live as
# constants in the guardrails module, taken from the HP rules document, where
# they can be audited.
SUPERLATIVE_RESTRICTION_RE = re.compile(
    r"superlative claim[^.]{0,80}(?:cannot|can not|do not|don't)\s*(?:be\s*)?use", re.I)
COMPETITOR_RESTRICTION_RE = re.compile(
    r"competitor name/?s?[^.]{0,80}(?:CANNOT|cannot|do not)\s*(?:be\s*)?use", re.I)
ANY_RESTRICTION_RE = re.compile(
    r"Use Restrictions|DO\s*NOT\s*USE|CANNOT be used in all countries", re.I)

# Countries named on a slide, used only to corroborate the constant lists.
# Matched by vocabulary rather than by splitting HP's prose.
COUNTRY_VOCAB = [
    "Romania", "Slovakia", "Turkey", "United Arab Emirates", "UAE", "Russia",
    "Armenia", "Belarus", "Kazakhstan", "Kyrgyzstan", "Moldova", "Tajikistan",
    "Turkmenistan", "Ukraine", "Uzbekistan", "China", "Vietnam", "Indonesia",
    "Malaysia", "Brazil", "Mexico", "Saudi Arabia", "State of Palestine",
    "Egypt", "Jordan", "Lebanon", "Syrian Arab Republic", "Bahrain", "Kuwait",
    "Oman", "Qatar", "Yemen", "Iran", "Iraq", "Nigeria", "Ethiopia",
    "Democratic Republic of the Congo", "South Africa", "Kenya", "Sudan",
    "Algeria", "Uganda", "Morocco", "Mozambique", "Ghana", "Angola",
    "Madagascar", "Cameroon", "Niger", "Burkina Faso", "Mali", "Malawi",
    "Zambia", "Senegal", "Chad", "Zimbabwe", "South Sudan", "Rwanda",
    "Tunisia", "Somalia", "Benin", "Burundi", "Togo", "Eritrea",
    "Sierra Leone", "Central African Republic", "Liberia", "Mauritania",
    "Namibia", "Botswana", "Gambia", "Equatorial Guinea", "Lesotho", "Gabon",
    "Guinea-Bissau", "Mauritius", "Eswatini", "Djibouti", "Comoros",
    "Cape Verde", "Tanzania", "Libya", "Guyana", "New Caledonia", "Seychelles",
]
COUNTRY_RE = re.compile(
    r"\b(" + "|".join(re.escape(c) for c in sorted(COUNTRY_VOCAB, key=len, reverse=True)) + r")\b",
    re.I)
# "CIS Countries" appears as a group name rather than a list.
CIS_MEMBERS = ["Armenia", "Belarus", "Kazakhstan", "Kyrgyzstan", "Moldova",
               "Russia", "Tajikistan", "Turkmenistan", "Ukraine", "Uzbekistan"]

# Qualifiers that must travel with a claim or the claim is worthless.
QUALIFIER_RE = re.compile(
    r"\b(up to|optional|where supported|where available|requires?|subject to|"
    r"may vary|not available in all|configured at the factory|"
    r"sold separately|where stated|selected|select )\b", re.I)

# Inline footnote markers: digits glued to the end of a word, not part of a
# number. "NPU2,3" and "Security27" match; "1.314kg", "90%" and "Windows 11"
# do not.
FOOTNOTE_MARKER_RE = re.compile(r"(?<=[A-Za-z\)™®])(\d{1,3}(?:\s*,\s*\d{1,3})*)(?![\d\.%])")

# Model designations look exactly like footnote markers - the "1" in "G1i" sits
# right after a letter. Stripping it turned "EliteDesk 8 Tower G1i" into
# "Tower Gi", which would defeat guardrail 16 (a G1i fact must never attach to
# a G2 product). Mask these before stripping footnotes, restore afterwards.
MODEL_TOKEN_RE = re.compile(
    r"\b(?:G\d[a-z]?\d?|X\d|Gen\s*\d+|Core\s*Ultra\s*\d|Ultra\s*\d|"
    r"Wi-?Fi\s*\d|RTX\s*\d+|A\d{3,4}|RX\d+|DDR\d)\b", re.I)

# The placeholder must not itself look like a footnote marker, so it is wrapped
# in pipes rather than letters - a digit preceded by "|" cannot match
# FOOTNOTE_MARKER_RE, which requires a preceding letter.
_MASK = "|#%d#|"


def _strip_footnote_markers(text: str) -> str:
    """Remove footnote digits without damaging model names such as G1i."""
    masks = {}

    def _hide(match):
        key = _MASK % len(masks)
        masks[key] = match.group(0)
        return key

    masked = MODEL_TOKEN_RE.sub(_hide, text)
    masked = FOOTNOTE_MARKER_RE.sub("", masked)
    for key, original in masks.items():
        masked = masked.replace(key, original)
    return masked

    def _hide(match):
        key = "%d" % len(masks)
        masks[key] = match.group(0)
        return key

    masked = MODEL_TOKEN_RE.sub(_hide, text)
    masked = FOOTNOTE_MARKER_RE.sub("", masked)
    for key, original in masks.items():
        masked = masked.replace(key, original)
    return masked


# A line that trails off mid-phrase is a headline fragment split across shapes,
# not a usable product fact.
DANGLING_TAIL_RE = re.compile(
    r"\b(with|and|or|the|a|an|to|for|of|in|on|that|plus|your)\s*$", re.I)

# Deck housekeeping that is not a product claim: embargo notices, confidentiality
# footers, image and forward-looking boilerplate, source and font instructions.
# These were being stored as facts a seller could quote.
NON_CLAIM_RE = re.compile(
    r"embargo|HP Confidential|CDA only|forward looking statement|"
    r"illustrations? and might not represent|images are not final|"
    r"for placement only|all product views|subject to change|"
    r"^\s*sources?\s*:|^\s*disclaimers?\s*:?|internal testing by HP as of|"
    r"^\s*change log|actual prices may vary", re.I)

# Generation / form factor, kept separate so a G1i fact can never attach to G2
# and a Tower fact never to a Mini (guardrail 16).
GENERATION_RE = re.compile(r"\bG(\d)(i|a|q8|q|e)?\b", re.I)
FORM_FACTORS = [
    ("aio", re.compile(r"\bAiO\b|All-in-One", re.I)),
    ("tower", re.compile(r"\bTower\b", re.I)),
    ("sff", re.compile(r"\bSFF\b|Small Form Factor", re.I)),
    ("mini", re.compile(r"\bMini\b", re.I)),
    ("notebook", re.compile(r"\bNotebook\b|\bLaptop\b", re.I)),
]
FAMILIES = [
    ("EliteBook Ultra", re.compile(r"EliteBook\s+Ultra", re.I)),
    ("EliteBook", re.compile(r"EliteBook", re.I)),
    ("ProBook", re.compile(r"ProBook", re.I)),
    ("EliteDesk", re.compile(r"EliteDesk", re.I)),
    ("ProDesk", re.compile(r"ProDesk", re.I)),
    ("EliteStudio", re.compile(r"EliteStudio", re.I)),
    ("ProStudio", re.compile(r"ProStudio", re.I)),
    ("HP 200", re.compile(r"\bHP\s*200\b", re.I)),
    ("BPS Portfolio", re.compile(r"BPS Portfolio|Sell-?In", re.I)),
    ("Competitive Playbook", re.compile(r"Competitive Playbook", re.I)),
]


def _norm(text):
    return " ".join(str(text or "").split())


def _slide_text(slide):
    parts = []
    for shape in slide.shapes:
        if shape.has_text_frame and shape.text_frame.text.strip():
            parts.append(shape.text_frame.text.strip())
    return "\n".join(parts)


def _notes_text(slide):
    if not slide.has_notes_slide:
        return ""
    return slide.notes_slide.notes_text_frame.text or ""


def split_notes(notes):
    """(talk_track, footnote_definitions) - the talk track is discarded."""
    parts = DISCLAIMER_SPLIT_RE.split(notes, maxsplit=1)
    if len(parts) == 2:
        head, tail = parts
    else:
        head, tail = notes, ""
    footnotes = {}
    for num, body in FOOTNOTE_DEF_RE.findall(tail):
        footnotes[num] = _norm(body)[:1200]
    return head, footnotes


def parse_restrictions(notes_head, slide_text):
    """Which kind of restriction this slide carries, and the countries it names.

    The restriction TYPE drives the block; the country list here only
    corroborates the authoritative lists in the guardrails module. Both the
    slide text and the notes are searched, because HP puts these in different
    places from deck to deck: the EliteBook 8 G2 superlative restriction is in
    the speaker notes, the Competitive Playbook's is in the slide body.
    """
    blob = (notes_head or "") + "\n" + (slide_text or "")

    superlative = bool(SUPERLATIVE_RESTRICTION_RE.search(blob))
    competitor = bool(COMPETITOR_RESTRICTION_RE.search(blob))
    if not (superlative or competitor or ANY_RESTRICTION_RE.search(blob)):
        return {"superlative": False, "competitor_claims": False,
                "countries": [], "raw": []}

    # Only look for countries inside the restriction region, so an unrelated
    # market mention elsewhere on the slide is not read as a restriction.
    match = ANY_RESTRICTION_RE.search(blob) or SUPERLATIVE_RESTRICTION_RE.search(blob)
    region = blob[match.start():match.start() + 3000] if match else ""

    countries = {_norm(c) for c in COUNTRY_RE.findall(region)}
    if re.search(r"\bCIS\b", region, re.I):
        countries.update(CIS_MEMBERS)
    # Normalise the one alias that appears both ways.
    if "UAE" in countries:
        countries.discard("UAE")
        countries.add("United Arab Emirates")

    return {
        "superlative": superlative,
        "competitor_claims": competitor,
        "countries": sorted(countries),
        "raw": [_norm(region[:400])],
    }


def parse_claims(slide_text, footnotes):
    """Claim lines with their footnote references and qualifiers.

    A claim is stored with the footnote text that qualifies it, so nothing
    downstream can present a figure without its condition.
    """
    claims = []
    for line in slide_text.splitlines():
        text = _norm(line)
        if len(text) < 25 or len(text) > 600:
            continue
        if CONFIDENTIAL_RE.search(text):
            continue
        if DANGLING_TAIL_RE.search(text) or NON_CLAIM_RE.search(text):
            continue
        refs = []
        masked = MODEL_TOKEN_RE.sub(" ", text)
        for hit in FOOTNOTE_MARKER_RE.findall(masked):
            refs.extend(n.strip() for n in hit.split(",") if n.strip())
        clean = _strip_footnote_markers(text)
        claims.append({
            "text": _norm(clean),
            "footnote_refs": sorted(set(refs), key=lambda x: int(x)),
            "footnotes": {r: footnotes[r] for r in set(refs) if r in footnotes},
            "qualifiers": sorted({_norm(q).lower() for q in QUALIFIER_RE.findall(text)}),
        })
    return claims


def classify(deck_name, slide_text):
    blob = deck_name + " " + slide_text
    family = next((name for name, rx in FAMILIES if rx.search(blob)), None)
    form = next((name for name, rx in FORM_FACTORS if rx.search(blob)), None)
    gen = None
    m = GENERATION_RE.search(blob)
    if m:
        gen = ("G" + m.group(1) + (m.group(2) or "")).lower()
    return family, gen, form


def parse_deck(path):
    deck_file = os.path.basename(path)
    deck_name = os.path.splitext(deck_file)[0]
    prs = Presentation(path)

    # Read every slide once first, then resolve footnotes deck-wide.
    #
    # HP does not always define a footnote in the notes of the slide that cites
    # it - many decks carry one disclaimers slide covering the whole deck.
    # Resolving per slide left 358 of 936 marked claims without their
    # condition, and guardrail 8 drops a claim whose condition is missing, so
    # those would have been lost for no reason.
    raw_slides = []
    deck_footnotes = {}
    for index, slide in enumerate(prs.slides, start=1):
        text = _slide_text(slide)
        if not text.strip() or any(rx.search(text) for rx in SKIP_SLIDE_PATTERNS):
            continue
        notes = _notes_text(slide)
        talk_track, footnotes = split_notes(notes)
        # First definition wins: a later slide repeating a number does not
        # overwrite the deck's own disclaimer text for it.
        for num, body in footnotes.items():
            deck_footnotes.setdefault(num, body)
        raw_slides.append((index, text, notes, talk_track, footnotes))

    out = []
    for index, text, notes, talk_track, footnotes in raw_slides:
        claims = parse_claims(text, deck_footnotes)
        if not claims and not footnotes:
            continue

        family, generation, form = classify(deck_name, text)
        embargo = EMBARGO_RE.search(text) or EMBARGO_RE.search(notes)

        out.append({
            "_id": "%s::%d" % (deck_name, index),
            "deck": deck_name,
            "deck_file": deck_file,
            "slide_number": index,
            "product_family": family,
            "generation": generation,
            "form_factor": form,
            "claims": claims,
            "disclaimers": footnotes,
            "restrictions": parse_restrictions(talk_track, text),
            "embargo_raw": _norm(embargo.group(1)) if embargo else None,
            "confidential": bool(CONFIDENTIAL_RE.search(text + notes)),
            "extractor_version": EXTRACTOR_VERSION,
        })

    # Quality pass. Runs after the whole deck is parsed, because deduplication
    # is deck-wide and provenance has to be merged onto the copy that is kept.
    # Extraction above is unchanged; this only decides keep or drop.
    out, quality = filter_deck(out)
    return out, quality


def knowledge_version(docs):
    """SHA-256 over every stored claim plus the extractor version.

    Downstream widget fingerprints include this, so re-extracting a corrected
    fact invalidates the recommendations built on it.
    """
    payload = json.dumps(
        [{"id": d["_id"], "claims": [c["text"] for c in d["claims"]],
          "restrictions": d["restrictions"], "embargo": d["embargo_raw"]}
         for d in sorted(docs, key=lambda x: x["_id"])],
        sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(
        (payload + "|v%d" % EXTRACTOR_VERSION).encode("utf-8")).hexdigest()


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--deck-dir", default=os.path.abspath(DECK_DIR))
    ap.add_argument("--apply", action="store_true", help="write; otherwise dry run")
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    if not os.path.isdir(args.deck_dir):
        sys.exit("No deck directory at %s" % args.deck_dir)

    files = sorted(f for f in os.listdir(args.deck_dir) if f.lower().endswith(".pptx"))
    if not files:
        sys.exit("No .pptx decks in %s" % args.deck_dir)

    all_docs = []
    print("%-48s %6s %7s %7s %7s %6s" % ("DECK", "slides", "kept", "dropped",
                                         "merged", "restr"))
    print("-" * 92)
    reasons = {}
    for name in files:
        docs, quality = parse_deck(os.path.join(args.deck_dir, name))
        restricted = sum(1 for d in docs if d["restrictions"]["countries"])
        print("%-48s %6d %7d %7d %7d %6d" % (
            name[:46], len(docs), quality["kept"], quality["dropped"],
            quality["merged"], restricted))
        for reason, count in quality["reasons"].items():
            reasons[reason] = reasons.get(reason, 0) + count
        all_docs.extend(docs)

    version = knowledge_version(all_docs)
    print("-" * 92)
    print("%-48s %6d %7d" % ("TOTAL", len(all_docs),
                             sum(len(d["claims"]) for d in all_docs)))
    print("knowledge_version: %s" % version)
    if reasons:
        print("\nclaims dropped by the quality pass:")
        for reason, count in sorted(reasons.items(), key=lambda kv: -kv[1]):
            print("   %-52s %5d" % (reason, count))

    if not args.apply:
        print("\nDry run - nothing written. Re-run with --apply.")
        return 0

    db = get_db()
    now = datetime.now(timezone.utc)
    col = db[COLLECTION]
    for doc in all_docs:
        doc["extracted_at"] = now
        doc_id = doc.pop("_id")
        col.update_one({"_id": doc_id}, {"$set": doc}, upsert=True)
        doc["_id"] = doc_id

    # Remove slides that no longer exist, so a shrinking deck cannot leave
    # stale facts behind.
    live = {d["_id"] for d in all_docs} | {VERSION_DOC_ID}
    removed = col.delete_many({"_id": {"$nin": list(live)}}).deleted_count

    col.update_one(
        {"_id": VERSION_DOC_ID},
        {"$set": {"knowledge_version": version,
                  "extractor_version": EXTRACTOR_VERSION,
                  "slide_count": len(all_docs),
                  "updated_at": now}},
        upsert=True)

    print("\nWrote %d slide records (%d stale removed)." % (len(all_docs), removed))
    print("Stored knowledge_version %s" % version)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
