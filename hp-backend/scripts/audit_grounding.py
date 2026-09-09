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
    return [(k, v) for k, v in out if isinstance(v, str) and v.strip()]


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
               "objection_reframe_cards", "opportunity_narrative_plays"]

    total_strings = bad_numbers = bad_urls = bad_products = 0

    for wk in widgets:
        doc = db["account_widgets"].find_one({"account_id": aid, "widget_key": wk})
        if not doc or doc.get("status") != "available":
            print(f"  {wk:<34} (not available - skipped)")
            continue
        data = doc.get("data") or {}
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

    print(f"\nTOTAL: {total_strings} generated strings | "
          f"{bad_numbers} unsourced numbers | {bad_urls} unsourced URLs | "
          f"{bad_products} non-HP products")
    return 0 if (bad_numbers or bad_urls or bad_products) == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
