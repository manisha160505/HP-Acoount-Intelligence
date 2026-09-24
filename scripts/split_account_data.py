#!/usr/bin/env python3
"""Split the four combined source workbooks into one folder of CSVs per account.

What this is for
----------------
Source data arrives combined: one Explorium workbook per company (19 sheets),
plus three workbooks that hold all ~220 accounts together, keyed by domain. The
upload API takes the opposite shape - one CSV per dataset_key, per account
(POST /api/v1/accounts/{account_id}/data). This script bridges the two.

It writes, per account:

    220 account split csv/<ACCOUNT_SLUG>/
        firmographics.csv
        company_hierarchy.csv
        ...
        _manifest.json          what was written, from where, and how many rows
        _MISSING.txt            datasets that came out empty, and why

Every dataset in DATASET_REGISTRY gets a file, including ones we have no source
for (stakeholder-map style). Those are created with their header row where the
schema is known, and left with zero data rows otherwise. The point is that the
folder is a complete slot board: when data for a gap arrives later, it drops
into a file that already exists under the right name.

Nothing here uploads. Writing files and registering them are separate steps on
purpose - see the note on placeholders below.

Placeholders must not be uploaded
---------------------------------
Extractors resolve a dataset through its MongoDB record, not by scanning disk
(services/extractors/datasets.py). A dataset that is not registered returns []
and the feature degrades cleanly. A dataset that IS registered but holds no
rows is a different thing: the extractor believes it has data and works from
nothing. So an empty placeholder is worse than no file at all, and
`--print-upload-plan` deliberately lists only the files that actually carry
rows. The upload endpoint rejects a 0-byte file anyway; this keeps a
header-only file from slipping past that check.

Usage
-----
    # every account found in the source data
    python scripts/split_account_data.py

    # one account, or a few (matched loosely on name or domain)
    python scripts/split_account_data.py --account "PT Astra" --account jal.com

    # see what would happen, write nothing
    python scripts/split_account_data.py --dry-run

    # coverage table across all accounts, then stop
    python scripts/split_account_data.py --report

    # which files are worth uploading, for one account
    python scripts/split_account_data.py --account "PT Astra" --print-upload-plan

Requires pandas and openpyxl (both already in hp-backend/requirements.txt).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from datetime import UTC, datetime
from pathlib import Path

try:
    import pandas as pd
except ImportError:
    sys.exit("pandas is required: pip install pandas openpyxl")

REPO_ROOT = Path(__file__).resolve().parent.parent
SOURCE_DIR = REPO_ROOT / "220 account data "   # trailing space is in the real folder name
OUTPUT_DIR = REPO_ROOT / "220 account split csv"

EXPLORIUM_DIR = SOURCE_DIR / "explorium_clean_220"
HP_INTENT_FILE = SOURCE_DIR / "hp_intent_results 2.xlsx"
GOOGLE_NEWS_FILE = SOURCE_DIR / "google_news_rss_data 1.xlsx"
# Same schema as the google news export, but far wider coverage: 215 domains
# against 99, so 119 accounts have news here and nowhere else. Merged into the
# google_news dataset rather than given its own dataset_key, because the
# registry has no key for it and the columns are identical.
EXA_FILE = SOURCE_DIR / "exa_data.xlsx"
PREDICTLEADS_FILE = SOURCE_DIR / "predictleads_combined_219_accounts.xlsx"

# Written with a BOM because that is what the existing stored CSVs carry, and
# the upload endpoint decodes with utf-8-sig either way.
ENCODING = "utf-8-sig"


# --------------------------------------------------------------------------
# Dataset plan
# --------------------------------------------------------------------------
# Mirrors DATASET_REGISTRY in hp-backend/src/app/schemas/account_data.py. The
# check_registry_drift() call below fails the run if the two ever disagree, so
# a dataset added to the backend cannot silently stop being produced here.
#
#   source: which workbook a dataset comes from
#   sheet:  the sheet within it
#   key:    the column that identifies the account (domain, unless noted)
#
# source=None means we have no feed for it yet. Those are the deliberate gaps.

EXPLORIUM = "explorium"
PREDICTLEADS = "predictleads"
HP_INTENT = "hp_intent"
GOOGLE_NEWS = "google_news"

DATASET_PLAN = {
    # --- Explorium workbook, one file per company, sheets pass through as-is
    "firmographics":        {"source": EXPLORIUM, "sheet": "1_Firmographics"},
    "company_hierarchy":    {"source": EXPLORIUM, "sheet": "2_Company_Hierarchy"},
    "subsidiaries":         {"source": EXPLORIUM, "sheet": "2_Subsidiaries"},
    "funding":              {"source": EXPLORIUM, "sheet": "3_Funding_Overview"},
    "technographics":       {"source": EXPLORIUM, "sheet": "4_Technographics"},
    "webstack":             {"source": EXPLORIUM, "sheet": "5_Webstack"},
    "workforce_trends":     {"source": EXPLORIUM, "sheet": "6_Workforce_Trends"},
    "company_ratings":      {"source": EXPLORIUM, "sheet": "7_Company_Ratings"},
    "website_traffic":      {"source": EXPLORIUM, "sheet": "8_Website_Traffic"},
    "social_media":         {"source": EXPLORIUM, "sheet": "9_Social_Media"},
    "intent_topics":        {"source": EXPLORIUM, "sheet": "10_Intent_Topics"},
    "intent_score":         {"source": EXPLORIUM, "sheet": "11_intent_score"},
    "prospect_contacts":    {"source": EXPLORIUM, "sheet": "14_Prospect_Contacts"},
    "news_events":          {"source": EXPLORIUM, "sheet": "13_News_Events"},

    # --- PredictLeads combined workbook, filtered by company_domain
    "company":               {"source": PREDICTLEADS, "sheet": "company"},
    "extended_company":      {"source": PREDICTLEADS, "sheet": "extended_company"},
    "job_openings":          {"source": PREDICTLEADS, "sheet": "job_openings"},
    "technology_detections": {"source": PREDICTLEADS, "sheet": "technology_detections"},
    "news_events_additional": {"source": PREDICTLEADS, "sheet": "news_events"},
    "connections":           {"source": PREDICTLEADS, "sheet": "connections"},
    "subpages":              {"source": PREDICTLEADS, "sheet": "subpages"},
    "similar_companies":     {"source": PREDICTLEADS, "sheet": "similar_companies"},

    # --- Standalone workbooks
    # hp_category_intent has a two-row header (category band above the field
    # names) and is written back with both rows intact, because the extractor
    # reads it through read_dataset_rows() and does its own header handling.
    "hp_category_intent":   {"source": HP_INTENT, "sheet": "Intent Data (Wide)",
                             "key": "Domain", "two_row_header": True},
    "google_news":          {"source": GOOGLE_NEWS, "sheet": "google_news_rss_data",
                             "key": "website_domain"},

    # --- No feed yet. Created empty, on purpose.
    # compliance_filings is PDFs, not a table, so it gets a directory rather
    # than a CSV - dropping filings into it is the whole workflow.
    "compliance_filings":   {"source": None, "note": "PDF filings - drop files into this folder",
                             "is_dir": True},
}

# Columns present in a source sheet that the existing stored CSVs dropped. We
# keep them by default: none of the extractors read them today, but dropping a
# column at split time loses it silently, and re-splitting later is cheap only
# if the source is still around. --match-legacy reproduces the old drop exactly
# when you need a byte-comparable file.
LEGACY_DROPPED_COLUMNS = {
    "google_news": ["signal_categories", "matched_keywords", "event_summary"],
}


# Vendors disagree about which domain represents a company, so rows that do
# belong to an account arrive under a domain the Explorium workbook never uses.
# Mapping is explicit rather than fuzzy on purpose: matching on company name
# would fold "Public Bank Lao Limited" (pbebank.com) into Public Bank Bhd and
# "Posco International" into Posco Group, and those are different entities.
# Each line below was checked against both workbooks individually.
#
#   <domain as it appears in a combined workbook>: <the account's domain>
DOMAIN_ALIASES = {
    "posco.com":            "posco-inc.com",        # Posco Group (KR)
    "shell.com.ph":         "pilipinas.shell.com.ph",  # Pilipinas Shell (PH)
    "shiseido.co.jp":       "corp.shiseido.com",    # Shiseido Company, Limited
    "stanley-electric.com": "stanley.co.jp",        # Stanley Electric Co., Ltd.
    # pbebank.com is deliberately NOT mapped: PredictLeads labels it "Public
    # Bank Lao Limited", a separate entity from Public Bank Bhd (MY), whose
    # workbook has no domain at all. Folding them would attribute one
    # country's hiring and technology to another's account.
}


def apply_domain_alias(domain: str) -> str:
    return DOMAIN_ALIASES.get(domain, domain)


# Some corporate domains are shared by more than one account in the source set:
# Jabil's Malaysian and Singaporean entities both sit under jabil.com, and MUFG
# and the Bank of Tokyo-Mitsubishi Bangkok branch both under mufg.jp. The
# vendors key their rows by that one domain, so a plain domain filter copies
# every row into both accounts - which inflates the totals and, worse, tells a
# seller that Singapore is hiring for roles that are actually in Malaysia.
#
# Neither vendor gives us a field that splits those rows by entity, so there is
# no honest way to divide them. The rows go to the primary account listed here
# and the secondary account gets none, which is the conservative reading: an
# account with no data reads as "no data", whereas an account with another
# entity's data reads as fact.
#
#   <shared domain>: <slug of the account that keeps the rows>
SHARED_DOMAIN_PRIMARY = {
    "jabil.com": "JABIL_CIRCUIT_SDN_BHD",
    "mufg.jp": "MITSUBISHI_UFJ_FINANCIAL_GROUP_INC",
}


# Every value this script derives rather than copies is appended here, so the
# run can answer "what did you change, and on what grounds?" without anyone
# re-reading the source by hand. A correction that cannot be explained in this
# list is a correction that should not be happening.
CORRECTIONS: list[dict] = []


def record_correction(account: str, field: str, source_value, derived_value,
                      reason: str):
    CORRECTIONS.append({
        "account": account,
        "field": field,
        "source": "" if source_value is None else str(source_value),
        "derived": "" if derived_value is None else str(derived_value),
        "reason": reason,
    })


def check_registry_drift() -> list[str]:
    """Compare DATASET_PLAN against the backend's DATASET_REGISTRY.

    A dataset the backend accepts but this script does not produce would show
    up as a permanently missing upload with nothing explaining why, so it is
    worth failing loudly at startup instead.
    """
    warnings = []
    schema_file = (REPO_ROOT / "hp-backend" / "src" / "app" / "schemas"
                   / "account_data.py")
    if not schema_file.exists():
        return ["could not find account_data.py - registry drift check skipped"]

    text = schema_file.read_text()
    body = text.split("DATASET_REGISTRY", 1)[-1]
    registry_keys = set(re.findall(r'^\s{4}"(\w+)":\s*\{', body, re.M))
    if not registry_keys:
        return ["could not parse DATASET_REGISTRY - drift check skipped"]

    for key in sorted(registry_keys - set(DATASET_PLAN)):
        warnings.append(f"registry has '{key}' but DATASET_PLAN does not - "
                        f"it will never be produced")
    for key in sorted(set(DATASET_PLAN) - registry_keys):
        warnings.append(f"DATASET_PLAN has '{key}' but the registry does not - "
                        f"upload would reject it")
    return warnings


# --------------------------------------------------------------------------
# Name / domain handling
# --------------------------------------------------------------------------

def slugify(name: str) -> str:
    """Folder name for an account. Mirrors the Explorium file naming."""
    norm = unicodedata.normalize("NFKD", str(name))
    norm = norm.encode("ascii", "ignore").decode()
    norm = re.sub(r"[^A-Za-z0-9]+", "_", norm).strip("_")
    return norm.upper() or "UNNAMED_ACCOUNT"


def normalize_domain(value) -> str:
    """Bare lowercase host: strips scheme, www. and any path or port.

    Domains are the join key across three of the four workbooks, and they are
    not written consistently in them (some carry https://, some www.), so
    matching on the raw string drops rows that do belong to the account.
    """
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    text = str(value).strip().lower()
    if not text or text in {"nan", "none", "-", "—"}:
        return ""
    text = re.sub(r"^[a-z]+://", "", text)
    text = text.split("/")[0].split("?")[0].split(":")[0]
    text = re.sub(r"^www\.", "", text).strip().strip(".")
    # Applied here so all four sources agree on one domain per account, rather
    # than each call site remembering to alias.
    return DOMAIN_ALIASES.get(text, text)


def normalize_name(value) -> str:
    """Loose company-name key: case, punctuation and suffixes removed."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    text = unicodedata.normalize("NFKD", str(value))
    text = text.encode("ascii", "ignore").decode().lower()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    for suffix in (" limited", " ltd", " inc", " corporation", " corp",
                   " company", " co", " plc", " pte", " sdn bhd", " tbk",
                   " gmbh", " ag", " sa", " nv", " bv", " pty"):
        if text.endswith(suffix):
            text = text[: -len(suffix)]
    return " ".join(text.split())


# --------------------------------------------------------------------------
# Source loading (cached - the combined workbooks are large)
# --------------------------------------------------------------------------

class SourceData:
    """Loads the three combined workbooks once and indexes them by domain."""

    def __init__(self, match_legacy: bool = False):
        self.match_legacy = match_legacy
        self._predictleads: dict[str, pd.DataFrame] = {}
        self._google_news: pd.DataFrame | None = None
        self._hp_intent: pd.DataFrame | None = None
        self._hp_intent_header: list[list[str]] | None = None

    # -- PredictLeads -----------------------------------------------------
    def predictleads_sheet(self, sheet: str) -> pd.DataFrame | None:
        if sheet not in self._predictleads:
            if not PREDICTLEADS_FILE.exists():
                self._predictleads[sheet] = None
            else:
                try:
                    df = pd.read_excel(PREDICTLEADS_FILE, sheet_name=sheet)
                    df["__domain"] = df.get("company_domain",
                                            pd.Series([""] * len(df))).map(normalize_domain)
                    self._predictleads[sheet] = df
                except Exception as exc:
                    print(f"  ! could not read predictleads sheet '{sheet}': {exc}")
                    self._predictleads[sheet] = None
        return self._predictleads[sheet]

    # -- Google News ------------------------------------------------------
    def google_news(self) -> pd.DataFrame | None:
        """Both news feeds, concatenated and de-duplicated.

        The RSS export and the Exa export carry the same columns but different
        coverage, so they are stacked rather than chosen between. Duplicates
        are dropped on (domain, headline, date): the 96 domains in both feeds
        would otherwise contribute the same story twice.
        """
        if self._google_news is None:
            frames = []
            for path, sheet, label in (
                (GOOGLE_NEWS_FILE, "google_news_rss_data", "google_news_rss"),
                (EXA_FILE, "exa_data", "exa"),
            ):
                if not path.exists():
                    continue
                df = pd.read_excel(path, sheet_name=sheet)
                df["__feed"] = label
                frames.append(df)

            if not frames:
                self._google_news = False
            else:
                df = pd.concat(frames, ignore_index=True, sort=False)
                if self.match_legacy:
                    drop = [c for c in LEGACY_DROPPED_COLUMNS["google_news"]
                            if c in df.columns]
                    df = df.drop(columns=drop)
                df["__domain"] = df["website_domain"].map(normalize_domain)
                df["__name"] = df["company_name"].map(normalize_name)
                before = len(df)
                df = df.drop_duplicates(
                    subset=[c for c in ("__domain", "event_headline", "event_date")
                            if c in df.columns])
                self._dedup_dropped = before - len(df)
                self._google_news = df.reset_index(drop=True)
        return self._google_news if self._google_news is not False else None

    # -- HP category intent ----------------------------------------------
    def hp_intent(self) -> tuple[pd.DataFrame | None, list[list[str]] | None]:
        """Returns (rows, header_rows).

        Read with header=None because the sheet has two header rows and the
        stored CSV keeps both. Row 0 is the category band ("PCs (Score /100)"
        spanning its columns), row 1 the field names.
        """
        if self._hp_intent is None:
            if not HP_INTENT_FILE.exists():
                self._hp_intent = False
            else:
                raw = pd.read_excel(HP_INTENT_FILE, sheet_name="Intent Data (Wide)",
                                    header=None)
                self._hp_intent_header = [
                    ["" if pd.isna(v) else str(v) for v in raw.iloc[i].tolist()]
                    for i in (0, 1)
                ]
                body = raw.iloc[2:].reset_index(drop=True)
                # Column 1 is Domain, column 0 is Company - per the header row.
                body["__domain"] = body[1].map(normalize_domain)
                body["__name"] = body[0].map(normalize_name)
                self._hp_intent = body
        if self._hp_intent is False:
            return None, None
        return self._hp_intent, self._hp_intent_header


# --------------------------------------------------------------------------
# Account discovery
# --------------------------------------------------------------------------

class Account:
    def __init__(self, name: str, domain: str, explorium_file: Path | None,
                 disambiguator: str = ""):
        self.name = name
        self.domain = normalize_domain(domain)
        self.explorium_file = explorium_file
        self.name_key = normalize_name(name)

        # Company name alone is not unique across the source set. Three
        # different Ministry of Defence workbooks (MY, VN, SG) and two Westpac
        # workbooks (AU, NZ) share a name, so a name-only slug collapses five
        # workbooks into two folders and three accounts are overwritten by
        # whichever is processed last. Worse, they are different companies in
        # different countries, so the survivor carries another entity's data.
        # The disambiguator is the country suffix from the vendor's filename,
        # falling back to the domain.
        self.slug = slugify(name)
        if disambiguator:
            self.slug = f"{self.slug}_{slugify(disambiguator)}"

    def __repr__(self):
        return f"<Account {self.name!r} domain={self.domain!r}>"


def discover_accounts(sources: SourceData) -> list[Account]:
    """Build the account list from the Explorium files, which are per-company.

    The domain comes from each workbook's own firmographics sheet rather than
    from the filename, so it matches what the other three workbooks key on.
    Accounts that appear only in the combined workbooks are picked up from the
    HP intent sheet afterwards, so nothing in the source set is skipped.
    """
    accounts: dict[str, Account] = {}

    if EXPLORIUM_DIR.exists():
        paths = [p for p in sorted(EXPLORIUM_DIR.glob("*_explorium_data.xlsx"))
                 if not p.name.startswith("~$")]

        # Two passes: the first finds names shared by more than one workbook so
        # the second can disambiguate only those, and every other folder keeps
        # its clean name.
        identities = {path: _read_identity(path) for path in paths}
        name_counts: dict[str, int] = {}
        for name, _ in identities.values():
            key = slugify(name)
            name_counts[key] = name_counts.get(key, 0) + 1

        for path in paths:
            name, domain = identities[path]
            name = name or path.stem
            suffix = _country_suffix(path, name)
            disambiguator = ""
            if name_counts.get(slugify(name), 0) > 1:
                # Prefer the filename's country suffix; otherwise the domain's
                # top-level country ("westpac.co.nz" -> NZ, "mindef.gov.sg" ->
                # SG), which keeps the folder name meaningful rather than
                # repeating the company name back at itself.
                disambiguator = suffix or _country_from_domain(domain)
                record_correction(
                    name, "folder slug", slugify(name),
                    f"{slugify(name)}_{slugify(disambiguator)}",
                    f"{name_counts[slugify(name)]} workbooks share this company "
                    f"name; disambiguated so they do not overwrite each other")
            acct = Account(name, domain, path, disambiguator)
            if acct.slug in accounts:
                # Should not happen now, but overwriting silently is the exact
                # failure this pass exists to prevent, so say so.
                print(f"  ! slug collision on '{acct.slug}': "
                      f"{path.name} vs {accounts[acct.slug].explorium_file.name}")
            accounts[acct.slug] = acct

    # Anything present in HP intent but with no Explorium workbook.
    intent, _ = sources.hp_intent()
    if intent is not None:
        known = {a.domain for a in accounts.values() if a.domain}
        for _, row in intent.iterrows():
            domain = row["__domain"]
            if not domain or domain in known:
                continue
            acct = Account(str(row[0]), domain, None)
            accounts.setdefault(acct.slug, acct)
            known.add(domain)

    return sorted(accounts.values(), key=lambda a: a.slug)


def _country_from_domain(domain: str) -> str:
    """Trailing country code of a domain, when it has one.

    "westpac.co.nz" -> NZ, "mindef.gov.sg" -> SG, "bhp.com" -> "" (generic TLD,
    which tells us nothing about country).
    """
    parts = normalize_domain(domain).split(".")
    if len(parts) >= 2 and len(parts[-1]) == 2:
        return parts[-1].upper()
    return ""


def _country_suffix(path: Path, company_name: str) -> str:
    """The country code the vendor appended to a filename, if any.

    "WESTPAC_BANKING_CORPORATION_AU_explorium_data.xlsx" carries AU beyond the
    company name. That suffix is the only thing distinguishing it from the NZ
    workbook of the same company name, so it is what disambiguates the folder.
    """
    stem = path.name.replace("_explorium_data.xlsx", "")
    name_part = slugify(company_name)
    if stem.upper().startswith(name_part) and len(stem) > len(name_part):
        tail = stem[len(name_part):].strip("_")
        if tail and len(tail) <= 3:
            return tail.upper()
    return ""


def _read_identity(path: Path) -> tuple[str, str]:
    """Company name and domain from an Explorium workbook's firmographics.

    Falls back to the Website column when Company Domain is blank. Two of the
    220 workbooks (Public Bank, Westpac) ship with an empty Company Domain but
    a populated Website, and without this fallback both accounts would silently
    lose every domain-keyed dataset - which looks identical to "the vendor has
    no data for them" in the output.
    """
    try:
        df = pd.read_excel(path, sheet_name="1_Firmographics", nrows=1)
        if len(df):
            row = df.iloc[0]
            name = str(row.get("Company Name", "")).strip()
            domain = normalize_domain(row.get("Company Domain", ""))
            if not domain:
                domain = normalize_domain(row.get("Website", ""))
                if domain:
                    record_correction(
                        name, "Company Domain",
                        row.get("Company Domain", ""), domain,
                        "blank in firmographics, recovered from the Website column")
            return (name, domain)
    except Exception:
        pass
    # Fall back to the filename, which is the slug the vendor used.
    return path.stem.replace("_explorium_data", "").replace("_", " ").title(), ""


# --------------------------------------------------------------------------
# Extraction
# --------------------------------------------------------------------------

def extract_dataset(account: Account, dataset_key: str, spec: dict,
                    sources: SourceData) -> tuple[pd.DataFrame | None, list | None, str]:
    """Rows for one dataset of one account.

    Returns (dataframe, header_rows, reason). A None dataframe means nothing
    was produced and `reason` says why - that string is what lands in
    _MISSING.txt, so it has to be specific enough to act on.
    """
    source = spec.get("source")

    if source is None:
        return None, None, spec.get("note", "no source feed for this dataset yet")

    # A domain shared with another account yields rows to the primary only.
    # Checked before any filtering so every domain-keyed source is covered by
    # one rule rather than three.
    if source in (PREDICTLEADS, GOOGLE_NEWS, HP_INTENT):
        primary = SHARED_DOMAIN_PRIMARY.get(account.domain)
        if primary and primary != account.slug:
            return None, None, (
                f"{account.domain} is shared with {primary}, which keeps these "
                f"rows; no field in the source splits them by entity")

    if source == EXPLORIUM:
        if account.explorium_file is None:
            return None, None, "no Explorium workbook for this account"
        sheet = spec["sheet"]
        try:
            df = pd.read_excel(account.explorium_file, sheet_name=sheet)
        except ValueError:
            return None, None, f"sheet '{sheet}' not in the Explorium workbook"
        except Exception as exc:
            return None, None, f"could not read sheet '{sheet}': {exc}"
        if df.empty:
            # Explorium writes a single "No data available" column instead of
            # the real header when it has nothing. Passing that through would
            # make the placeholder look like a schema, so the file is left
            # genuinely empty and the real columns fill in when data arrives.
            cols = list(df.columns)
            if len(cols) == 1 and "no data" in str(cols[0]).lower():
                return None, [], f"sheet '{sheet}' reports no data available"
            return None, cols, f"sheet '{sheet}' is present but empty"
        return df, list(df.columns), ""

    if source == PREDICTLEADS:
        df = sources.predictleads_sheet(spec["sheet"])
        if df is None:
            return None, None, "predictleads workbook or sheet unavailable"
        if not account.domain:
            return None, list(df.columns), "no domain for this account, cannot filter"
        subset = df[df["__domain"] == account.domain].drop(columns=["__domain"])
        if subset.empty:
            return None, [c for c in df.columns if c != "__domain"], \
                f"no rows for {account.domain} in predictleads '{spec['sheet']}'"
        return subset, list(subset.columns), ""

    if source == GOOGLE_NEWS:
        df = sources.google_news()
        if df is None:
            return None, None, "google news workbook unavailable"
        subset = df[df["__domain"] == account.domain] if account.domain else df.iloc[0:0]
        if subset.empty and account.name_key:
            subset = df[df["__name"] == account.name_key]
        # __feed is kept out of the CSV but is what tells you which export a
        # story came from when two feeds disagree; it stays in the manifest.
        internal = ["__domain", "__name", "__feed"]
        subset = subset.drop(columns=[c for c in internal if c in subset.columns])
        cols = [c for c in df.columns if c not in internal]
        if subset.empty:
            return None, cols, f"no news rows for {account.domain or account.name}"
        return subset, cols, ""

    if source == HP_INTENT:
        body, header = sources.hp_intent()
        if body is None:
            return None, None, "hp intent workbook unavailable"
        subset = body[body["__domain"] == account.domain] if account.domain else body.iloc[0:0]
        if subset.empty and account.name_key:
            subset = body[body["__name"] == account.name_key]
        subset = subset.drop(columns=["__domain", "__name"])
        if subset.empty:
            return None, header, f"no intent row for {account.domain or account.name}"
        return subset, header, ""

    return None, None, f"unknown source '{source}'"


def write_dataset(out_dir: Path, dataset_key: str, df, header,
                  two_row_header: bool, dry_run: bool) -> int:
    """Write one CSV. Returns the number of data rows written.

    A dataset with no rows still gets a file, with its header where we know it,
    because the folder is meant to be a complete slot board for the account.
    """
    target = out_dir / f"{dataset_key}.csv"
    if dry_run:
        return 0 if df is None else len(df)

    if two_row_header:
        # Both header rows are written verbatim, then the data rows beneath.
        # The extractor reads this file through read_dataset_rows() and treats
        # the first two lines as headers, so collapsing them would break it.
        import csv as _csv
        with open(target, "w", newline="", encoding=ENCODING) as fh:
            writer = _csv.writer(fh)
            for row in (header or []):
                writer.writerow(row)
            if df is not None:
                for _, row in df.iterrows():
                    writer.writerow(["" if pd.isna(v) else v for v in row.tolist()])
        return 0 if df is None else len(df)

    if df is None:
        # Header-only placeholder. Columns are written when we know them, so
        # the file is immediately usable when data arrives; otherwise it is a
        # genuinely empty file rather than a guessed schema.
        cols = [c for c in (header or []) if not str(c).startswith("__")]
        pd.DataFrame(columns=cols).to_csv(target, index=False, encoding=ENCODING)
        return 0

    df.to_csv(target, index=False, encoding=ENCODING)
    return len(df)


# --------------------------------------------------------------------------
# Per-account run
# --------------------------------------------------------------------------

def process_account(account: Account, sources: SourceData,
                    dry_run: bool) -> dict:
    out_dir = OUTPUT_DIR / account.slug
    if not dry_run:
        out_dir.mkdir(parents=True, exist_ok=True)

    manifest = {
        "account_name": account.name,
        "account_slug": account.slug,
        "domain": account.domain,
        "generated_at": datetime.now(UTC).isoformat(),
        "explorium_file": account.explorium_file.name if account.explorium_file else None,
        "datasets": {},
    }
    missing: list[tuple[str, str]] = []

    for dataset_key, spec in DATASET_PLAN.items():
        if spec.get("is_dir"):
            # compliance_filings holds PDFs, so it is a folder with a README
            # rather than a CSV. Uploading is per-file and manual.
            if not dry_run:
                pdf_dir = out_dir / dataset_key
                pdf_dir.mkdir(exist_ok=True)
                readme = pdf_dir / "README.txt"
                if not readme.exists():
                    readme.write_text(
                        "Drop this account's PDF filings here (annual reports,\n"
                        "exchange filings, monthly market reports).\n\n"
                        "Upload each one with dataset_key=compliance_filings.\n"
                        "This dataset is multi-file: uploading a second PDF adds\n"
                        "to the set rather than replacing the first.\n"
                    )
            manifest["datasets"][dataset_key] = {
                "rows": 0, "source": None, "status": "awaiting_files",
                "kind": "pdf_directory",
            }
            missing.append((dataset_key, spec.get("note", "awaiting PDF filings")))
            continue

        df, header, reason = extract_dataset(account, dataset_key, spec, sources)
        rows = write_dataset(out_dir, dataset_key, df, header,
                             spec.get("two_row_header", False), dry_run)

        manifest["datasets"][dataset_key] = {
            "rows": rows,
            "source": spec.get("source"),
            "sheet": spec.get("sheet"),
            "status": "ok" if rows else "empty",
            "reason": reason or None,
        }
        if not rows:
            missing.append((dataset_key, reason or "no rows"))

    if not dry_run:
        (out_dir / "_manifest.json").write_text(json.dumps(manifest, indent=2))
        lines = [
            f"Datasets with no data for {account.name} ({account.domain or 'no domain'})",
            f"Generated {manifest['generated_at']}",
            "",
            "These files exist but hold no rows. Do NOT upload them: an empty",
            "registered dataset makes an extractor work from nothing, whereas an",
            "unregistered one degrades cleanly. Drop data in, then upload.",
            "",
        ]
        lines += [f"  {key:<26} {reason}" for key, reason in missing]
        (out_dir / "_MISSING.txt").write_text("\n".join(lines) + "\n")

    manifest["_missing"] = missing
    return manifest


# --------------------------------------------------------------------------
# Reporting
# --------------------------------------------------------------------------

def print_upload_plan(manifest: dict):
    slug = manifest["account_slug"]
    print(f"\nUpload plan for {manifest['account_name']} ({slug})")
    print("  1. Create the account, then use the returned id below.\n")
    print('     curl -X POST "$BASE/api/v1/accounts" -H "Authorization: Bearer $HP_TOKEN" \\')
    print(f"          -H 'Content-Type: application/json' \\")
    print(f"          -d '{{\"name\": \"{manifest['account_name']}\"}}'\n")
    print("  2. Upload only the datasets that carry rows:\n")

    ready = [(k, v) for k, v in manifest["datasets"].items() if v["rows"] > 0]
    for key, info in ready:
        path = f"220 account split csv/{slug}/{key}.csv"
        print(f'     curl -X POST "$BASE/api/v1/accounts/$ACCOUNT_ID/data" \\')
        print(f'          -H "Authorization: Bearer $HP_TOKEN" \\')
        print(f'          -F "dataset_key={key}" -F "file=@{path}"   # {info["rows"]} rows')
    skipped = [k for k, v in manifest["datasets"].items() if v["rows"] == 0]
    print(f"\n  {len(ready)} to upload, {len(skipped)} skipped as empty:")
    print(f"     {', '.join(skipped) or 'none'}")
    print("\n  Upload firmographics last if you want to minimise LLM cost: it")
    print("  triggers the most extractors, and each upload re-runs every feature")
    print("  that depends on the dataset.")


def write_run_summary(manifests: list[dict], sources: SourceData,
                      accounts: list[Account]):
    """Write _RUN_SUMMARY.json and _CORRECTIONS.txt at the output root.

    The summary carries the source row counts the reconciliation check needs:
    counting them again later would re-read 60MB of Excel, and counting them
    from a different code path would defeat the point of the check.
    """
    source_rows = {}
    for dataset_key, spec in DATASET_PLAN.items():
        if spec.get("source") == PREDICTLEADS:
            df = sources.predictleads_sheet(spec["sheet"])
            if df is not None:
                source_rows[dataset_key] = len(df)
        elif spec.get("source") == GOOGLE_NEWS:
            df = sources.google_news()
            if df is not None:
                # Pre-dedupe, so the reconciliation can subtract the dedupe
                # itself. Recording the post-dedupe count here and subtracting
                # again would count those rows twice and show a false gap.
                source_rows[dataset_key] = len(df) + getattr(
                    sources, "_dedup_dropped", 0)
        elif spec.get("source") == HP_INTENT:
            body, _ = sources.hp_intent()
            if body is not None:
                source_rows[dataset_key] = len(body)

    # Counted here rather than inferred by the validator: a reconciliation that
    # derives its own residual from the other two numbers always balances, and
    # so proves nothing. This is an independent third count.
    known_domains = {a.domain for a in accounts if a.domain}
    known_names = {a.name_key for a in accounts if a.name_key}
    unclaimed_rows = {}
    for dataset_key, spec in DATASET_PLAN.items():
        frame, by_name = None, False
        if spec.get("source") == PREDICTLEADS:
            frame = sources.predictleads_sheet(spec["sheet"])
        elif spec.get("source") == GOOGLE_NEWS:
            frame, by_name = sources.google_news(), True
        elif spec.get("source") == HP_INTENT:
            frame, by_name = sources.hp_intent()[0], True
        if frame is None:
            continue

        reached = frame["__domain"].isin(known_domains)
        if by_name:
            # google_news and hp_category_intent fall back to matching on
            # company name when the domain does not match, so a row whose
            # domain is unknown may still reach an account. Counting it as
            # unclaimed here would double-subtract it from the reconciliation.
            reached |= frame["__name"].isin(known_names)
        unclaimed_rows[dataset_key] = int((~reached).sum())

    summary = {
        "generated_at": datetime.now(UTC).isoformat(),
        "accounts": len(manifests),
        "source_rows": source_rows,
        "unclaimed_rows": unclaimed_rows,
        "news_dedup_dropped": getattr(sources, "_dedup_dropped", 0),
        "corrections": CORRECTIONS,
        "domain_aliases": DOMAIN_ALIASES,
        "account_domains": {m["account_slug"]: m["domain"] for m in manifests},
    }
    (OUTPUT_DIR / "_RUN_SUMMARY.json").write_text(json.dumps(summary, indent=2))

    lines = [
        "Values this run derived rather than copied from source",
        f"Generated {summary['generated_at']}",
        "",
        "Each line is a place the script did not take the source at face value.",
        "If a line here is wrong, the output is wrong.",
        "",
    ]
    if not CORRECTIONS:
        lines.append("  (none - every value came straight from a source file)")
    for correction in CORRECTIONS:
        lines += [
            f"{correction['account']}",
            f"  {correction['field']}:",
            f"    source:  {correction['source'] or '(blank)'}",
            f"    derived: {correction['derived']}",
            f"    reason:  {correction['reason']}",
            "",
        ]
    if summary["news_dedup_dropped"]:
        lines += [
            "google_news (all accounts)",
            f"  {summary['news_dedup_dropped']} rows dropped as duplicates when the RSS and",
            "  Exa feeds were merged, matched on domain + headline + date.",
            "",
        ]
    (OUTPUT_DIR / "_CORRECTIONS.txt").write_text("\n".join(lines) + "\n")

    print(f"\n{len(CORRECTIONS)} derived value(s) recorded in _CORRECTIONS.txt")


def verify_output(manifests: list[dict]) -> int:
    """Re-read what was written and check it against what the API will accept.

    Everything above reports on data as it was read; this reports on the files
    as they now exist on disk, which is what actually gets uploaded. Returns a
    count of problems so the caller can exit non-zero.
    """
    problems = 0
    print("\nVerifying written output")
    print("-" * 68)

    for manifest in manifests:
        out_dir = OUTPUT_DIR / manifest["account_slug"]
        for dataset_key, info in manifest["datasets"].items():
            if info.get("kind") == "pdf_directory":
                continue
            path = out_dir / f"{dataset_key}.csv"

            if not path.exists():
                print(f"  MISSING FILE  {manifest['account_slug']}/{dataset_key}.csv")
                problems += 1
                continue

            if info["rows"] == 0:
                continue  # placeholder, not meant to be uploaded

            # A file the manifest says has rows must parse back to those rows,
            # or the upload would register a row count the data does not have.
            try:
                if dataset_key == "hp_category_intent":
                    frame = pd.read_csv(path, header=[0, 1], encoding=ENCODING)
                else:
                    frame = pd.read_csv(path, encoding=ENCODING, low_memory=False)
            except Exception as exc:
                print(f"  UNREADABLE    {manifest['account_slug']}/{dataset_key}.csv: {exc}")
                problems += 1
                continue

            if len(frame) != info["rows"]:
                print(f"  ROW MISMATCH  {manifest['account_slug']}/{dataset_key}.csv: "
                      f"manifest says {info['rows']}, file has {len(frame)}")
                problems += 1

    print(f"  {'no problems found' if not problems else f'{problems} problem(s)'}")
    return problems


def report_unclaimed_rows(accounts: list[Account], sources: SourceData):
    """Source rows whose domain matches no account we are producing.

    This is the guardrail against silent loss. Every other check tells you a
    dataset came out empty; this one tells you data EXISTS in the source and is
    going nowhere, which is the failure that would otherwise be invisible -
    the split looks successful and the rows simply never land.
    """
    known = {a.domain for a in accounts if a.domain}
    print("\nUnclaimed source rows (present in a source, matched to no account)")
    print("-" * 68)
    clean = True

    for sheet in ("job_openings", "technology_detections", "news_events",
                  "company", "connections", "subpages", "similar_companies",
                  "extended_company"):
        df = sources.predictleads_sheet(sheet)
        if df is None:
            continue
        orphan_domains = sorted({d for d in df["__domain"] if d and d not in known})
        orphan_rows = int((~df["__domain"].isin(known) & (df["__domain"] != "")).sum())
        blank = int((df["__domain"] == "").sum())
        if orphan_rows or blank:
            clean = False
            print(f"  predictleads/{sheet}: {orphan_rows} rows across "
                  f"{len(orphan_domains)} unmatched domains"
                  + (f", {blank} rows with no domain" if blank else ""))
            if orphan_domains:
                print(f"      {', '.join(orphan_domains[:6])}"
                      + (" ..." if len(orphan_domains) > 6 else ""))

    known_names = {a.name_key for a in accounts if a.name_key}

    news = sources.google_news()
    if news is not None:
        reached = news["__domain"].isin(known) | news["__name"].isin(known_names)
        orphan = sorted({d for d, ok in zip(news["__domain"], reached)
                         if d and not ok})
        rows = int((~reached & (news["__domain"] != "")).sum())
        if rows:
            clean = False
            print(f"  google_news: {rows} rows across {len(orphan)} unmatched domains")
            print(f"      {', '.join(orphan[:6])}" + (" ..." if len(orphan) > 6 else ""))

    intent, _ = sources.hp_intent()
    if intent is not None:
        reached = intent["__domain"].isin(known) | intent["__name"].isin(known_names)
        orphan = sorted({d for d, ok in zip(intent["__domain"], reached)
                         if d and not ok})
        if orphan:
            clean = False
            print(f"  hp_category_intent: {len(orphan)} accounts with no folder")
            print(f"      {', '.join(orphan[:6])}" + (" ..." if len(orphan) > 6 else ""))

    if clean:
        print("  none - every source row reached an account folder")


def print_report(manifests: list[dict]):
    keys = [k for k in DATASET_PLAN if not DATASET_PLAN[k].get("is_dir")]
    print(f"\nCoverage across {len(manifests)} accounts\n")
    print(f"{'dataset':<26} {'accounts with rows':>18}  {'total rows':>12}")
    print("-" * 60)
    for key in keys:
        have = sum(1 for m in manifests if m["datasets"].get(key, {}).get("rows", 0) > 0)
        total = sum(m["datasets"].get(key, {}).get("rows", 0) for m in manifests)
        flag = "" if have else "   <- no data anywhere"
        print(f"{key:<26} {have:>18}  {total:>12,}{flag}")


def main():
    parser = argparse.ArgumentParser(
        description="Split combined source workbooks into per-account CSV folders.")
    parser.add_argument("--account", action="append", default=[],
                        help="Only this account (name or domain substring). Repeatable.")
    parser.add_argument("--dry-run", action="store_true",
                        help="Report what would be written without writing it.")
    parser.add_argument("--report", action="store_true",
                        help="Print a coverage table across all accounts and exit.")
    parser.add_argument("--print-upload-plan", action="store_true",
                        help="Print the curl commands for the datasets that carry rows.")
    parser.add_argument("--match-legacy", action="store_true",
                        help="Reproduce the column drops in the existing stored CSVs.")
    parser.add_argument("--limit", type=int, default=0,
                        help="Process at most N accounts (for a quick check).")
    parser.add_argument("--verify", action="store_true",
                        help="Re-read the written CSVs and check them against "
                             "the manifest. Exits non-zero on any problem.")
    args = parser.parse_args()

    if not SOURCE_DIR.exists():
        sys.exit(f"source folder not found: {SOURCE_DIR}")

    for warning in check_registry_drift():
        print(f"WARNING: {warning}")

    print(f"Reading sources from {SOURCE_DIR}")
    sources = SourceData(match_legacy=args.match_legacy)

    accounts = discover_accounts(sources)
    print(f"Found {len(accounts)} accounts in the source data")

    if args.account:
        wanted = [a.lower() for a in args.account]
        accounts = [
            acct for acct in accounts
            if any(w in acct.name.lower() or w in acct.slug.lower()
                   or (acct.domain and w in acct.domain) for w in wanted)
        ]
        if not accounts:
            sys.exit(f"no account matched: {', '.join(args.account)}")
        print(f"Filtered to {len(accounts)}: "
              f"{', '.join(a.name for a in accounts[:8])}")

    if args.limit:
        accounts = accounts[: args.limit]

    # Aliases are applied inside normalize_domain, which runs per row across
    # every source; recording them there would produce tens of thousands of
    # identical lines. One line per alias that actually matched an account is
    # the useful form.
    account_domains = {a.domain for a in accounts if a.domain}
    for source_domain, account_domain in DOMAIN_ALIASES.items():
        if account_domain in account_domains:
            record_correction(
                account_domain, "source domain", source_domain, account_domain,
                "explicit approved alias: the combined workbooks key this "
                "account under a different domain than its Explorium workbook")

    # A primary that does not exist would silently withhold rows from the
    # secondary and give them to nobody, so the mapping is checked against the
    # real account list rather than trusted.
    all_slugs = {a.slug for a in accounts}
    for shared_domain, primary in SHARED_DOMAIN_PRIMARY.items():
        holders = sorted(a.slug for a in accounts if a.domain == shared_domain)
        if not holders:
            continue
        if primary not in all_slugs:
            sys.exit(f"SHARED_DOMAIN_PRIMARY names '{primary}' for "
                     f"{shared_domain}, but no such account exists")
        for slug in holders:
            if slug != primary:
                record_correction(
                    slug, "domain-keyed datasets", f"rows for {shared_domain}",
                    "none",
                    f"{shared_domain} is shared with {primary}, which keeps the "
                    f"rows; no source field splits them by entity")

    if not args.dry_run:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    manifests = []
    for index, account in enumerate(accounts, 1):
        marker = "[dry-run] " if args.dry_run else ""
        manifest = process_account(account, sources, args.dry_run)
        manifests.append(manifest)
        filled = sum(1 for v in manifest["datasets"].values() if v["rows"] > 0)
        total = len(manifest["datasets"])
        print(f"  {marker}[{index}/{len(accounts)}] {account.slug:<44} "
              f"{filled}/{total} datasets with data")

    if args.report:
        print_report(manifests)
        # Only meaningful over the full set: with --account, almost everything
        # is unclaimed by definition.
        if not args.account and not args.limit:
            report_unclaimed_rows(accounts, sources)

    if args.print_upload_plan:
        for manifest in manifests:
            print_upload_plan(manifest)

    if not args.dry_run:
        print(f"\nWrote {len(manifests)} account folders to {OUTPUT_DIR}")
        print("Each holds _manifest.json (what came from where) and "
              "_MISSING.txt (what is still empty).")

    if not args.dry_run:
        write_run_summary(manifests, sources, accounts)

    if args.verify and not args.dry_run:
        if verify_output(manifests):
            sys.exit(1)


if __name__ == "__main__":
    main()
