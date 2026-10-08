# -*- coding: utf-8 -*-
"""Build config/company_relationships.csv from the client's 7 Oct hierarchy data.

Run from hp-backend:
    python scripts/build_company_relationships.py ../final_merged_company_hierarchy_no_self_relationships.xlsx

Two sources, both from Dhruvi's email of 7 Oct 2026 (4:59 pm IST):

  * final_merged_company_hierarchy_no_self_relationships.xlsx - one row per
    relationship (Input Company, Relationship to Input = Parent | Subsidiary,
    Related Company) for 42 accounts, almost all of which have no parent or
    subsidiaries in Explorium. These ADD to Explorium.
  * the updated parent-company mapping in the email body, for 11 accounts.
    These REPLACE every other parent source for the account. "-" means the
    account has no parent; so does a parent that is the account itself.

Self rows are dropped here, by name and on review, not by a rule at read time:
a rule loose enough to catch "UOB" for United Overseas Bank would also drop
"Kuok Group" for Kuok (Singapore) and "Seiko Group" for Seiko Epson, which are
real parents. Every drop is listed in SELF_PARENT_ROWS with its reason.

After changing the output, bump RELATIONSHIPS_VERSION in
app/services/hp/company_relationships.py and update its file hash - a test
fails until both are done, so the Executive Dashboard goes stale exactly when
this data changes.
"""

import csv
import os
import sys

import pandas as pd

OUT = os.path.join(os.path.dirname(__file__), "..", "config", "company_relationships.csv")
SOURCE_MERGED = "merged company hierarchy (client, 7 Oct)"
SOURCE_MAPPING = "parent-company mapping (client, 7 Oct)"

# (account as uploaded, parent as the client wrote it, the client's note).
# None = no parent.
PARENT_MAPPING = [
    ("BANK FOR AGRICULTURE AND AGRICULTURAL COOPERATIVE - TH", "Ministry of Finance, Thailand",
     "State-owned bank; 99.79% owned by the Thai Ministry of Finance."),
    ("BHP BILLITON - AU", "BHP Group Limited",
     "Ultimate parent company; renamed to BHP Group Limited."),
    ("CHAROEN POKPHAND GROUP CO LTD - TH", "Chearavanont Family / CP Group Holding",
     "Ultimate parent conglomerate. PT Charoen Pokphand Indonesia is a subsidiary, not a parent."),
    ("MILITARY BANK - VN", "Ministry of National Defence, Vietnam",
     "State-owned commercial joint-stock bank managed under the Vietnamese Ministry of Defence."),
    ("MITSUBISHI UFJ FINANCIAL GROUP, INC. - JP", None,
     "Top-level Japanese financial holding company."),
    ("THE BANK OF TOKYO-MITSUBISHI LIMITED (BANGKOK BRANCH) - TH",
     "MUFG Bank, Ltd. / Mitsubishi UFJ Financial Group (JP)",
     "Overseas branch belonging to MUFG Bank."),
    # The client's "correct parent" is the company itself: independent and
    # top-level, so no parent is shown.
    ("SHISEIDO COMPANY, LIMITED - JP", None,
     "Independent, top-level publicly listed corporation (client named Shiseido Company, Limited itself)."),
    ("SUMITOMO MITSUI FINANCIAL GROUP, INC. - JP", None,
     "Independent Japanese financial holding company."),
    ("VIETTEL CORPORATION - VN", "Ministry of National Defence, Vietnam",
     "Vietnam state-owned telecommunications group under the Ministry of National Defence."),
    ("SEATRIUM LIMITED - SG", "Temasek Holdings",
     "Formed from the merger of Sembcorp Marine and Keppel Offshore & Marine. Temasek Holdings is the largest shareholder."),
    ("HEALTHSCOPE - AU", "Brookfield Asset Management (via Brookfield Business Partners)",
     "Acquired by Brookfield in 2019."),
]

# Parent rows in the merged sheet that name the account itself.
SELF_PARENT_ROWS = {
    ("BUNNINGS GROUP LIMITED", "Bunnings"): "the account itself",
    ("EAST JAPAN RAILWAY COMPANY", "East Japan Railway Company (JR East)"): "the account itself",
    ("FONTERRA CO-OPERATIVE GROUP LIMITED", "Fonterra"): "the account itself",
    ("ISUZU MOTORS LIMITED", "Isuzu Motors Ltd."): "the account itself",
    ("MINISTRY OF HOME AFFAIRS", "Ministry of Home Affairs Singapore"): "the account itself",
    ("HKMC GROUP(HYUNDAI AUTOEVER)", "Autoever"): "the account itself (Hyundai AutoEver)",
    ("NIPPON EXPRESS CO., LTD.", "Nippon Express CO."): "the account itself",
    ("PRICEWATERHOUSECOOPERS", "Price waterhouse Coopers LLP"): "the account itself",
    ("UNITED OVERSEAS BANK LIMITED (UOB)", "UOB"): "the account itself",
    ("SUMITOMO MITSUI FINANCIAL GROUP, INC.", "（株）三井住友フィナンシャルグループ"):
        "the account itself, in Japanese",
}


def _key(name: str) -> str:
    s = " ".join(str(name or "").lower().split())
    head, sep, tail = s.rpartition(" - ")
    return head if sep and len(tail) == 2 else s


def main(merged_path: str, accounts_dir: str) -> int:
    import json
    names = []
    for slug in sorted(os.listdir(accounts_dir)):
        meta = os.path.join(accounts_dir, slug, "_account.json")
        if os.path.exists(meta):
            with open(meta, encoding="utf-8") as fh:
                name = json.load(fh).get("name_for_upload")
            if name:
                names.append(name)
    by_key = {}
    for name in names:
        by_key.setdefault(_key(name), []).append(name)

    rows, dropped = [], []
    mapped = {account for account, _, _ in PARENT_MAPPING}
    for account, parent, note in PARENT_MAPPING:
        if account not in names:
            raise SystemExit("mapping names an unknown account: %s" % account)
        rows.append({"account": account,
                     "relationship": "parent" if parent else "no_parent",
                     "company": parent or "", "source": SOURCE_MAPPING, "note": note})

    df = pd.read_excel(merged_path)
    for _, r in df.iterrows():
        input_company = " ".join(str(r["Input Company"]).split())
        related = " ".join(str(r["Related Company"] or "").split())
        relationship = str(r["Relationship to Input"]).strip().lower()
        matches = by_key.get(_key(input_company), [])
        if len(matches) != 1:
            raise SystemExit("cannot match %r to one account: %s" % (input_company, matches))
        account = matches[0]
        if not related or related.lower() == "nan":
            continue
        if relationship == "parent":
            reason = SELF_PARENT_ROWS.get((input_company, related))
            if reason or account in mapped:
                dropped.append((account, related, reason or "replaced by the client's mapping"))
                continue
        elif relationship != "subsidiary":
            raise SystemExit("unknown relationship %r" % relationship)
        rows.append({"account": account, "relationship": relationship, "company": related,
                     "source": SOURCE_MERGED, "note": ""})

    seen, out = set(), []
    for row in rows:
        k = (row["account"], row["relationship"], row["company"].lower())
        if k not in seen:
            seen.add(k)
            out.append(row)
    out.sort(key=lambda r: (r["account"], r["relationship"] != "parent",
                            r["relationship"], r["company"].lower()))
    with open(OUT, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["account", "relationship", "company", "source", "note"])
        w.writeheader()
        w.writerows(out)

    counts = {}
    for row in out:
        counts[row["relationship"]] = counts.get(row["relationship"], 0) + 1
    print("wrote %s: %d rows %s, %d accounts" % (
        os.path.relpath(OUT), len(out), counts, len({r["account"] for r in out})))
    print("dropped %d parent row(s):" % len(dropped))
    for account, related, reason in dropped:
        print("  %s -> %s  (%s)" % (account, related, reason))
    return 0


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    accounts = sys.argv[2] if len(sys.argv) > 2 else os.path.join(
        os.path.dirname(__file__), "..", "..", "220 account split csv")
    sys.exit(main(sys.argv[1], accounts))
