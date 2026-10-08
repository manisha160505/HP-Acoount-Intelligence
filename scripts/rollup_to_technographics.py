"""GROUP_tech_stack_rollup.csv -> each group's technographics.csv.

Client, 8 Oct (open data gaps): Johor Corporation, POSCO and Sagility had no
Technographics / Tech Breakdown / Website Stack in Explorium; the client sent a
researched tech-stack roll-up for the three instead. It is written in the shape
of the Explorium technographics export - one row, 20 category columns plus
"Full Tech Stack" - so Tech Landscape, Opportunity Map and Objection Playbook
read it with no code change.

What the roll-up carries that technographics cannot (confidence, source tier,
sources, validation depth, last seen) is not written; the roll-up file stays the
record of it.

A row already in the account's technographics.csv (POSCO has one) is merged,
not replaced: every technology already listed stays, the roll-up's are added
after it. The file as it was is kept beside it as
_technographics_before_rollup.csv, and _manifest.json / _MISSING.txt are updated
to match.

Dry run by default; --apply writes.

    python scripts/rollup_to_technographics.py
    python scripts/rollup_to_technographics.py --apply

Then upload each account's technographics.csv (admin page, dataset
"technographics") and Submit on the Pipeline tab.
"""

import argparse
import csv
import json
import os
import shutil
import sys
from collections import OrderedDict

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
ROLLUP = os.path.join(ROOT, "GROUP_tech_stack_rollup.csv")
SPLIT = os.path.join(ROOT, "220 account split csv")

# group_company in the roll-up -> the account's folder.
ACCOUNTS = {
    "Johor Corporation": "JOHOR_CORPORATION",
    "POSCO": "POSCO_GROUP",
    "Sagility": "SAGILITY_PHILIPPINES_B_V_BRANCH_OFFICE",
}

# The Explorium technographics header, in its own order
# (hp-backend tech_landscape.TECHNOGRAPHICS_CATEGORY_COLUMNS + Full Tech Stack).
COLUMNS = [
    "Testing And Qa", "Sales", "Prog Langs And Frameworks", "Productivity And Operations",
    "Product And Design", "Platform And Storage", "Operations Software",
    "Operations Management", "Marketing", "It Security", "It Management", "Hr",
    "Finance And Accounting", "Ecommerce", "Devops And Development", "Customer Management",
    "Computer Networks", "Communications", "Collaboration", "Bi And Analytics",
    "Technology", "Full Tech Stack",
]

# Roll-up layer -> the technographics category it is filed under. A layer not
# listed goes to "Technology", Explorium's own catch-all.
LAYER_COLUMN = {
    "web_cms_frontend": "Devops And Development",
    "devops": "Devops And Development",
    "languages_frameworks": "Prog Langs And Frameworks",
    "martech_crm": "Marketing",
    "collab_productivity": "Collaboration",
    "cloud": "Platform And Storage",
    "database": "Platform And Storage",
    "security_iam": "It Security",
    "compliance_riskdata": "It Security",
    "data_ai_bi": "Bi And Analytics",
    "erp_core": "Operations Software",
    "infra_network": "Computer Networks",
    "endpoint_mobile": "It Management",
    "itsm_ops": "It Management",
    "cx_contact_clinical": "Customer Management",
    "hr_fin": "Hr",
}


def _names(cell) -> list:
    return [n.strip() for n in str(cell or "").split(",") if n.strip()]


def _add(target: list, name: str) -> None:
    if name.lower() not in {n.lower() for n in target}:
        target.append(name)


def build(rollup_rows, existing: dict | None) -> dict:
    """One technographics row: the existing one, plus the roll-up's technologies."""
    cells = OrderedDict((c, _names((existing or {}).get(c))) for c in COLUMNS)
    for row in rollup_rows:
        # The cells are comma-separated lists, so a comma inside one name
        # ("Java Platform, Enterprise Edition") would split it in two.
        tech = " ".join(str(row.get("technology") or "").replace(",", " /").split())
        if not tech:
            continue
        _add(cells[LAYER_COLUMN.get(row.get("layer"), "Technology")], tech)
        _add(cells["Full Tech Stack"], tech)
    return {c: ", ".join(v) for c, v in cells.items()}


def _read_existing(path: str) -> dict | None:
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8-sig", newline="") as fh:
        rows = list(csv.DictReader(fh))
    return rows[0] if rows else None


def _update_manifest(folder: str, techs: int) -> None:
    path = os.path.join(folder, "_manifest.json")
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as fh:
        manifest = json.load(fh)
    manifest.setdefault("datasets", {})["technographics"] = {
        "rows": 1, "source": "GROUP_tech_stack_rollup.csv", "sheet": None,
        "status": "ok",
        "reason": "client tech-stack roll-up, 8 Oct (%d technologies)" % techs,
    }
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2, ensure_ascii=False)


def _update_missing(folder: str) -> None:
    path = os.path.join(folder, "_MISSING.txt")
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as fh:
        lines = fh.readlines()
    kept = [ln for ln in lines if not ln.strip().startswith("technographics ")]
    if kept != lines:
        with open(path, "w", encoding="utf-8") as fh:
            fh.writelines(kept)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--apply", action="store_true", help="write the files")
    args = parser.parse_args()

    with open(ROLLUP, encoding="utf-8-sig", newline="") as fh:
        rollup = list(csv.DictReader(fh))
    unknown = sorted({r["group_company"] for r in rollup} - set(ACCOUNTS))
    if unknown:
        print("No account folder mapped for: %s" % ", ".join(unknown))
        return 1

    for group, slug in ACCOUNTS.items():
        folder = os.path.join(SPLIT, slug)
        if not os.path.isdir(folder):
            print("%s: folder %s not found" % (group, folder))
            return 1
        path = os.path.join(folder, "technographics.csv")
        existing = _read_existing(path)
        before = len(_names((existing or {}).get("Full Tech Stack")))
        row = build([r for r in rollup if r["group_company"] == group], existing)
        after = len(_names(row["Full Tech Stack"]))
        unfiled = len(_names(row["Technology"]))
        print("%-20s %-40s %3d -> %3d technologies (%d under 'Technology')"
              % (group, slug, before, after, unfiled))
        if not args.apply:
            continue
        if os.path.exists(path):
            shutil.copyfile(path, os.path.join(folder, "_technographics_before_rollup.csv"))
        with open(path, "w", encoding="utf-8-sig", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=COLUMNS)
            writer.writeheader()
            writer.writerow(row)
        _update_manifest(folder, after)
        _update_missing(folder)

    print("written" if args.apply else "dry run - nothing written (use --apply)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
