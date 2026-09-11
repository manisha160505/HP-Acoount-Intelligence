"""Standing grounding audit.

Walks every LLM-generated string currently stored for an account and reports any
number, URL or HP product name that does not trace to that account's uploaded
data. Run it after any prompt change - it is the regression check that
"nothing is invented" still holds.

    python scripts/audit_grounding.py                 # first account found
    python scripts/audit_grounding.py "Astra"         # by name fragment

Account-agnostic: the corpus is whatever the account uploaded.
"""

import os
import re
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from app.database.mongodb import get_db                                    # noqa: E402
from app.services.extractors.grounding import (                            # noqa: E402
    build_corpus, normalize_hp_product,
)
from app.services.extractors.solution_narrative_opportunity_map import (   # noqa: E402
    _read_dataset_records,
)

ALL_DATASETS = [
    "firmographics", "technographics", "intent_score", "google_news",
    "news_events", "prospect_contacts", "job_openings", "intent_topics",
    "webstack", "technology_detections", "company_hierarchy",
]

# widget_key -> how to pull the generated strings out of its data
def _collect(widget_key: str, data: dict):
    out = []
    if widget_key == "stakeholder_talking_points":
        for cid, t in (data.get("talking_points") or {}).items():
            for f in ("how_to_open", "hp_play_focus", "decision_power"):
                out.append((f"{cid}.{f}", t.get(f)))
            for i, pp in enumerate(t.get("pain_points") or []):
                out.append((f"{cid}.pain_points[{i}]", pp))
    elif widget_key == "news_relevance_summary":
        for sid, v in (data.get("scores") or {}).items():
            out.append((f"{sid}.sales_angle", v.get("sales_angle")))
            for dim, r in (v.get("rationales") or {}).items():
                out.append((f"{sid}.rationale.{dim}", r))
    elif widget_key == "objection_reframe_cards":
        for c in (data.get("cards") or []):
            for f in ("objection", "reframe", "counter_question"):
                out.append((f"{c.get('area')}.{f}", c.get(f)))
    elif widget_key == "opportunity_narrative_plays":
        for p in (data.get("opportunity_plays") or []):
            for f in ("title", "hp_capability", "inference", "proof_point", "source_url"):
                out.append((f"{p.get('play_key')}.{f}", p.get(f)))
            out.append((f"{p.get('play_key')}.recommended_cta",
                        (p.get("entry_path") or {}).get("recommended_cta")))
    elif widget_key == "technographic_hp_recommendations":
        # ACCOUNT-FACING FIELDS ONLY.
        #
        # `why_this_product` is deliberately excluded: it describes an HP
        # product, and HP product facts are not in the account's uploads, so
        # checking it against the account corpus would fail every time. That
        # field is verified at generation against the approved-fact corpus for
        # its own recommendation - see the hp_facts_checked / hp_facts_rejected
        # counters on the widget's grounding_report, and _audit_hp_facts below.
        for r in (data.get("recommendations") or []):
            rid = r.get("rule_id")
            for f in ("rationale", "discovery_question"):
                out.append((f"rule-{rid}.{f}", r.get(f)))
    return [(k, v) for k, v in out if isinstance(v, str) and v.strip()]


def _audit_hp_facts(data: dict):
    """Second corpus: every HP product claim must resolve to its approved facts.

    Returns (checked, failures). Each recommendation is checked only against
    the facts approved for THAT recommendation, so a fact belonging to one
    model can never vouch for prose about another (guardrails 1 and 16).
    """
    from app.services.extractors.grounding import corpus_from_texts

    checked, failures = 0, []
    for rec in (data.get("recommendations") or []):
        prose = str(rec.get("why_this_product") or "").strip()
        if not prose:
            continue
        facts = rec.get("approved_facts") or []
        corpus = corpus_from_texts(
            [f.get("text") for f in facts]
            + [c for f in facts for c in (f.get("conditions") or [])])
        checked += 1
        unsourced = corpus.unsourced_numbers(prose)
        if unsourced:
            failures.append(f"rule-{rec.get('rule_id')}: {unsourced}")
    return checked, failures


def _audit_technographic_map(data: dict, techno_row: dict):
    """Every vendor card must be able to substantiate what it says.

    Two failures this catches, both of which shipped once:

      * a stated provenance naming a column the vendor is not in - the string
        used to be hardcoded per detection branch, so Symantec / Kaspersky
        claimed "IT SECURITY" while appearing only in Full Tech Stack;
      * a description naming a product that was never detected - the Apple card
        said "macOS / iOS" on a stack containing only "Apple iOS".

    Returns (checked, failures).
    """
    checked, failures = 0, []
    columns = {k.lower(): str(v or "").lower() for k, v in (techno_row or {}).items()}

    for category in (data.get("categories") or []):
        for vendor in (category.get("vendors") or []):
            if vendor.get("is_whitespace"):
                continue
            checked += 1
            name = vendor.get("vendor_name")
            detected = [str(d) for d in (vendor.get("detected_as") or [])]

            # 1. provenance must resolve to somewhere the vendor really is
            provenance = str(vendor.get("provenance") or "")
            named = provenance.split("->")[-1]
            for column in [c.strip() for c in named.split(",") if c.strip()]:
                haystack = columns.get(column.lower())
                if haystack is None:
                    failures.append("%s: provenance names '%s', which is not a "
                                    "technographics column" % (name, column))
                elif detected and not any(d.lower() in haystack for d in detected):
                    failures.append("%s: provenance claims '%s' but no detected "
                                    "entry appears there" % (name, column))

            # 2. the description may not name a product that was not detected
            description = str(vendor.get("description") or "").lower()
            blob = " ".join(detected).lower()
            for token in ("macos", "ios", "windows", "linux", "android"):
                if token in description and blob and token not in blob:
                    failures.append("%s: description says '%s' but it is absent "
                                    "from the detected entries" % (name, token))

    return checked, failures


def main() -> int:
    needle = sys.argv[1] if len(sys.argv) > 1 else ""
    db = get_db()
    query = {"name": {"$regex": needle, "$options": "i"}} if needle else {}
    account = db["accounts"].find_one(query)
    if not account:
        print("No matching account.")
        return 1
    aid = str(account["_id"])
    print(f"Account: {account.get('name')}  ({aid})")

    corpus = build_corpus({k: _read_dataset_records(aid, k) for k in ALL_DATASETS})
    print(f"Corpus : {corpus.cell_count} cells from {len(ALL_DATASETS)} datasets\n")

    widgets = ["stakeholder_talking_points", "news_relevance_summary",
               "objection_reframe_cards", "opportunity_narrative_plays",
               "technographic_hp_recommendations"]

    total_strings = bad_numbers = bad_urls = bad_products = 0
    hp_checked = 0
    hp_failures = []
    map_checked = 0
    map_failures = []
    techno_rows = _read_dataset_records(aid, "technographics")
    techno_row = techno_rows[0] if techno_rows else {}

    map_doc = db["account_widgets"].find_one(
        {"account_id": aid, "widget_key": "technographic_map"})
    if map_doc and map_doc.get("status") == "available":
        map_checked, map_failures = _audit_technographic_map(
            map_doc.get("data") or {}, techno_row)

    for wk in widgets:
        doc = db["account_widgets"].find_one({"account_id": aid, "widget_key": wk})
        if not doc or doc.get("status") != "available":
            print(f"  {wk:<34} (not available - skipped)")
            continue
        data = doc.get("data") or {}
        if wk == "technographic_hp_recommendations":
            checked, failures = _audit_hp_facts(data)
            hp_checked += checked
            hp_failures.extend(failures)
        strings = _collect(wk, data)
        total_strings += len(strings)

        n_bad = u_bad = 0
        for label, text in strings:
            for num in corpus.unsourced_numbers(text):
                print(f"    UNSOURCED NUMBER  [{wk}/{label}] {num!r}")
                n_bad += 1
            for url in corpus.unsourced_urls(text):
                print(f"    UNSOURCED URL     [{wk}/{label}] {url[:70]}")
                u_bad += 1

        p_bad = 0
        for p in (data.get("opportunity_plays") or []):
            for prod in (p.get("hp_products") or []):
                if not normalize_hp_product(prod):
                    print(f"    NON-HP PRODUCT    [{wk}/{p.get('play_key')}] {prod!r}")
                    p_bad += 1

        bad_numbers += n_bad
        bad_urls += u_bad
        bad_products += p_bad
        gr = data.get("grounding_report")
        note = f"report: {gr['numbers_checked']}n/{gr['urls_checked']}u checked" if gr else "no report"
        print(f"  {wk:<34} {len(strings):>3} strings, {n_bad} bad numbers, "
              f"{u_bad} bad URLs, {p_bad} non-HP products   [{note}]")

    if map_checked or map_failures:
        print("")
        print(f"  technographic_map: {map_checked} vendor card(s) checked against "
              f"their source columns, {len(map_failures)} unsupported")
        for failure in map_failures:
            print(f"    UNSUPPORTED CARD     {failure}")

    if hp_checked or hp_failures:
        print(f"\n  HP product prose: {hp_checked} checked against their own approved "
              f"facts, {len(hp_failures)} unsourced")
        for failure in hp_failures:
            print(f"    UNSOURCED HP FIGURE  {failure}")

    print(f"\nTOTAL: {total_strings} generated strings | "
          f"{bad_numbers} unsourced numbers | {bad_urls} unsourced URLs | "
          f"{bad_products} non-HP products | {len(hp_failures)} unsourced HP figures | "
          f"{len(map_failures)} unsupported vendor cards")
    failed = bad_numbers or bad_urls or bad_products or hp_failures or map_failures
    return 0 if not failed else 2


if __name__ == "__main__":
    raise SystemExit(main())
