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
        firmographics.csv          one CSV per dataset_key, uploadable as-is
        company_hierarchy.csv
        ...
        compliance_filings/
            _filings_index.csv     this account's rows from filings 1.csv
                                   (titles, fiscal years, document URLs)
        reference/                 tables we hold that have NO dataset_key yet:
            explorium_hiring_events.csv, predictleads_products.csv, ...
                                   split per account for reference, not uploaded
        _account.json           identity from the client master list (territory
                                name, country, global parent, account type)
        _manifest.json          what was written, from where, and how many rows
        _MISSING.txt            datasets that came out empty, and why
        _READINESS.txt          per feature: which of its input datasets this
                                account has, and which are missing

and at the root:

    _ACCOUNTS.csv       one row per account: identity, datasets present/missing,
                        and whether every dataset any source supplies is present
    _READINESS.csv      account x feature matrix (complete / partial / none)
    _DATASET_USAGE.md   dataset -> the features that read it, and the reverse
    _unassigned_filings.csv   filings rows that matched no single account
    _RUN_SUMMARY.json / _CORRECTIONS.txt   as before

Every dataset in DATASET_REGISTRY gets a file, including ones we have no source
for (stakeholder-map style). Those are created with their header row where the
schema is known, and left with zero data rows otherwise. The point is that the
folder is a complete slot board: when data for a gap arrives later, it drops
into a file that already exists under the right name.

"Which feature uses this?" is answered from the backend's own dependency map
(FEATURE_MAPPINGS.dependent_datasets in api/v1/feature_mapping.py), not from a
copy kept here, so it cannot drift from what the upload endpoint regenerates.

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
import csv
import io
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
# Intent rows delivered after the main workbook, in its exact 55-column wide
# layout, each replacing that domain's row in it. NSW Department of Education
# was "Unavailable" in the 18 Sep file; the client sent this separately (Drive,
# 23 Sep, C33). Its scores are public-source estimates ("Scores measure
# evidence strength, not observed buyer research"), which its own band labels
# say; the replacement is logged in _CORRECTIONS.txt so that is not lost.
#   (path, sheet, category-band header row, first data row)
HP_INTENT_SUPPLEMENTS = [
    (SOURCE_DIR / "NSW_Education_Public_Intent.xlsx", "Intent report", 1, 3),
]
# The 25 Sep re-drop (C46-C48). Dhruvi: "Please use only this file going
# forward" for both news feeds, and the PredictLeads file with company name and
# country "populated across all sheets" is "the latest version". The 18 Sep
# files are kept in _superseded_2026-09-25/ and are not read.
GOOGLE_NEWS_FILE = SOURCE_DIR / "google_news_rss_data 2 (2)_2025-2026.xlsx"
# Same schema as the google news export, but far wider coverage: 215 domains
# against 94, so most accounts have news here and nowhere else. Merged into the
# google_news dataset rather than given its own dataset_key, because the
# registry has no key for it and the columns are identical.
EXA_FILE = SOURCE_DIR / "exa_data (3)_2025-2026.xlsx"
PREDICTLEADS_FILE = SOURCE_DIR / "predictleads_combined_219_accounts_company_country.xlsm"
# The one contact file for all 220 accounts (Dhruvi, 26 Sep 03:26 UTC: "Apollo_
# all_contacts(1) uploaded in the google drive folder … we are pulling data and
# will comeback with few more details"). Sheet "Contacts" has a four-line title
# block above its header row. Keyed by Company Name + Country Code, which is
# the master list's Sales Territory Name less its " - XX" suffix.
APOLLO_FILE = SOURCE_DIR / "Apollo_All_Contacts (1).xlsx"
APOLLO_SHEET = "Contacts"
APOLLO_HEADER_ROW = 4

# The client's news window, 25 Sep: "considering the last 12 months of data
# only". Both files start at 2025-01-01, so the window is still applied here,
# counted back from the day of the run. A row dated after the run is dropped
# too: Exa carries one dated 2026-10-19, which would sort above every real item.
NEWS_WINDOW_DAYS = 365

# Inputs without which the split would still "succeed" and silently write
# empty datasets. Checked up front in main().
REQUIRED_SOURCE_FILES = (HP_INTENT_FILE, GOOGLE_NEWS_FILE, EXA_FILE, PREDICTLEADS_FILE,
                         APOLLO_FILE)

# Inputs that live outside the vendor drop.
#
# The client's master list is the canonical account identity: Sales Territory
# Name (which is what the client calls the account), country, global parent and
# account type. The vendor workbooks only know a company name and a domain.
MASTER_LIST_FILE = (REPO_ROOT / "project-documentation" / "04_Data_and_Source_Definitions"
                    / "Account_List" / "APAC_Account_Parent_Child_Mapping.xlsx")
# The client's domain audit (DEC-052, 25 Sep): column D "Master Domain" is the
# canonical domain per account and the primary key for data mapping; column B
# is the name shown on the dashboard. 219 rows - Astra is absent because its
# data is the separate seed delivery. Only the "219 Account Audit" sheet is
# read; "Problems Only" and "Summary" are derived views of it.
DOMAIN_AUDIT_FILE = (REPO_ROOT / "project-documentation" / "04_Data_and_Source_Definitions"
                     / "Account_List" / "PredictLeads_219_Account_Domain_Audit.xlsx")
DOMAIN_AUDIT_SHEET = "219 Account Audit"
# Index of the filings crawl: 505 documents for 187 companies, each with a
# document_url. The PDFs themselves are on the crawler's machine (local_path),
# so this is what we can attach per account today.
FILINGS_INDEX_FILE = (REPO_ROOT / "project-documentation" / "04_Data_and_Source_Definitions"
                      / "Filings" / "filings 1.csv")
# Rows the client supplied after the crawl, in filings 1.csv's exact columns,
# appended to it on read. row_id "S26-n" marks them. The 26 Sep file holds the
# URLs Dhruvi sent for ANZ Holdings NZ, CIMB Group Holdings and CIMB Niaga,
# which the crawl never covered.
FILINGS_SUPPLEMENT_FILES = [
    FILINGS_INDEX_FILE.parent / "filings_client_supplement_2026-09-26.csv",
]
# Client rulings that settle a filings row whose territory and domain disagree.
# Checked before the conflict rule in assign_filings(), so a ruled row is filed
# where the client said and not parked in _unassigned_filings.csv.
#   (company, sales_territory_name) -> (account slug, authority)
FILINGS_CLIENT_RULINGS = {
    ("PT Bank Mandiri (Persero) Tbk", "PT BANK CENTRAL ASIA TBK - ID"): (
        "PT_BANK_MANDIRI_PERSERO",
        "Dhruvi 26 Sep 03:26 UTC: 'those redirect to Bank Mandiri, hence consider "
        "Bank Mandiri' (the territory column wrongly says BCA)"),
}
# The backend's dependency map, read (not copied) so readiness reflects what
# the upload endpoint will actually regenerate.
FEATURE_MAPPING_FILE = (REPO_ROOT / "hp-backend" / "src" / "app" / "api" / "v1"
                        / "feature_mapping.py")
# Accounts whose empty datasets may be filled from a benchmark seed. Astra's
# PredictLeads data was a separate delivery (client answer E2), so the combined
# workbook has no rows for astra.co.id; the seed the backend ships with is that
# delivery. Only datasets that came out empty are filled, and each fill is
# recorded in _CORRECTIONS.txt.
SEED_FILL = {
    "PT_ASTRA_INTERNATIONAL_TBK": REPO_ROOT / "hp-backend" / "seed_data" / "astra",
}
# Datasets where the seed wins even when the 220-account sources have rows.
# Astra's live Stakeholder Map runs on the pilot's 23 contacts; the 26 Sep
# Apollo file has 13 different people for Astra and none of the 23. Replacing
# the demo account's whole stakeholder list is Yogesh's call, not the split's,
# so the seed stays live and the Apollo rows are kept beside it under
# reference/apollo_prospect_contacts.csv until that is decided.
SEED_PREFERRED = {
    "PT_ASTRA_INTERNATIONAL_TBK": {"prospect_contacts"},
}
REFERENCE_DIR = "reference"

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
APOLLO = "apollo"
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
    # Apollo since 26 Sep; Explorium's 14_Prospect_Contacts (empty on all 220)
    # stays as the fallback for an account Apollo has no rows for.
    "prospect_contacts":    {"source": APOLLO, "sheet": APOLLO_SHEET,
                             "fallback": {"source": EXPLORIUM,
                                          "sheet": "14_Prospect_Contacts"}},
    # news_events is PredictLeads' news table, NOT Explorium's 13_News_Events.
    # The extractor (services/extractors/recent_news_signals.py) reads
    # summary / article_sentence / effective_date / found_at / category, which
    # are PredictLeads columns; the Astra benchmark's news_events.csv carries
    # the same columns; and Explorium's sheet (event_name, event_time, a JSON
    # payload) has none of them, so under this key every one of its rows would
    # be skipped as headline-less. An earlier version of this plan had the two
    # sheets the other way round; _RUN_SUMMARY.json "mapping_notes" records it.
    "news_events":          {"source": PREDICTLEADS, "sheet": "news_events"},

    # --- PredictLeads combined workbook, filtered by company_domain
    "company":               {"source": PREDICTLEADS, "sheet": "company"},
    "extended_company":      {"source": PREDICTLEADS, "sheet": "extended_company"},
    "job_openings":          {"source": PREDICTLEADS, "sheet": "job_openings"},
    "technology_detections": {"source": PREDICTLEADS, "sheet": "technology_detections"},
    # Explorium's event log (event_name, event_time, JSON data). No extractor
    # reads this key today - the input contract marks it not_consumed - so it
    # is kept under its registry key only to keep the slot board complete.
    "news_events_additional": {"source": EXPLORIUM, "sheet": "13_News_Events"},
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

# --------------------------------------------------------------------------
# Reference tables: data we hold per account that has no dataset_key yet
# --------------------------------------------------------------------------
# Written under <account>/reference/ and deliberately outside the upload plan:
# the backend has no dataset_key for any of these, so an upload would be
# rejected. They are split anyway so that "what do we have for this account"
# has one answer, and so the table is already per-account on the day a feature
# starts reading it. Filenames carry the vendor so provenance survives a copy.
# A file is written only when it has rows; the manifest lists the rest.
REFERENCE_PLAN = {
    # Explorium sheets the registry does not model
    "explorium_funding_rounds":  {"source": EXPLORIUM, "sheet": "3_Funding_Rounds"},
    "explorium_advisors":        {"source": EXPLORIUM, "sheet": "3_Advisors"},
    "explorium_investors":       {"source": EXPLORIUM, "sheet": "3_Investors"},
    "explorium_tech_breakdown":  {"source": EXPLORIUM, "sheet": "5_Tech_Breakdown"},
    # Explorium's own hiring signal: department-level hiring events, joins and
    # role changes. 45 accounts have no PredictLeads job openings at all; this
    # is the nearest thing we hold for them.
    "explorium_hiring_events":   {"source": EXPLORIUM, "sheet": "12_Hiring_Events"},

    # PredictLeads sheets the registry does not model
    "predictleads_financing_events":    {"source": PREDICTLEADS, "sheet": "financing_events"},
    "predictleads_products":            {"source": PREDICTLEADS, "sheet": "products"},
    # Named in the client's C1 answer: filings = filings 1.csv plus these,
    # merged on domain.
    "predictleads_sec_filings":         {"source": PREDICTLEADS, "sheet": "sec_filings"},
    "predictleads_github_repositories": {"source": PREDICTLEADS, "sheet": "github_repositories"},

    # Vendor QA sheets, keyed by domain so they split per account: what the
    # vendor could not collect, what it flagged for review, what it changed and
    # where two of its deliveries disagreed. The client's E5 answer says the
    # corrections log is a record, not a to-do list, so these are copied and
    # never applied.
    "predictleads_dataset_status":  {"source": PREDICTLEADS, "sheet": "dataset_status",
                                     "key": "domain"},
    "predictleads_review_records":  {"source": PREDICTLEADS, "sheet": "review_records"},
    "predictleads_quality_changes": {"source": PREDICTLEADS, "sheet": "quality_changes"},
    "predictleads_differences":     {"source": PREDICTLEADS,
                                     "sheet": ["Data7 differences", "Data8 differences"]},
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
# The target of every alias is the account's canonical domain from the
# client's domain audit (DEC-052), so aliases point from whatever a vendor
# used toward that sheet's column D - never the other way round.
#
#   <domain as it appears in a source workbook>: <the account's domain>
DOMAIN_ALIASES = {
    "posco-inc.com":          "posco.com",          # Posco Group (KR), Explorium
    "pilipinas.shell.com.ph": "shell.com.ph",       # Pilipinas Shell (PH), Explorium
    "shiseido.co.jp":         "corp.shiseido.com",  # Shiseido Company, Limited
    "stanley-electric.com":   "stanley.co.jp",      # Stanley Electric Co., Ltd.
    # Public Bank Bhd's Explorium workbook has a blank Company Domain; the
    # Website fallback gives publicbankgroup.com. The audit names pbebank.com,
    # and the client accepted the PredictLeads rows there that are labelled
    # "Public Bank Lao Limited" (a wholly-owned subsidiary) - DEC-052.
    "publicbankgroup.com":    "pbebank.com",        # Public Bank Bhd (MY)
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
# The news feeds and the intent file give us no field that splits those rows by
# entity, so there is no honest way to divide them. Their rows go to the
# primary account listed here and the secondary account gets none, which is
# the conservative reading: an account with no data reads as "no data",
# whereas an account with another entity's data reads as fact.
#
#   <shared domain>: <slug of the account that keeps the rows>
SHARED_DOMAIN_PRIMARY = {
    "jabil.com": "JABIL_CIRCUIT_SDN_BHD",
    "mufg.jp": "MITSUBISHI_UFJ_FINANCIAL_GROUP_INC",
}

# PredictLeads is the exception since 25 Sep (C48, D3): every sheet now carries
# `company_name`, and its values are the client's Sales Territory Names exactly
# (all 219 match). The client's rule is "take Company Name + Country into
# consideration along with the domain", so on a shared domain each row goes to
# the account(s) it names. Some rows name both entities, "; "-separated
# ("JABIL CIRCUIT SDN BHD - MY; JABIL CIRCUIT (SINGAPORE) PTE LTD - SG"): the
# vendor attributes them to both, and they go to both, as the client ruled for
# the Jabil 10-Q (DEC-054f). Set to False to give those rows to neither.
PREDICTLEADS_ENTITY_COLUMN = "company_name"
DUAL_ENTITY_ROWS_TO_BOTH = True


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
        self._master: dict | None = None
        self._audit: dict | None = None
        self._filings: pd.DataFrame | None = None

    # -- PredictLeads -----------------------------------------------------
    def predictleads_sheet(self, sheet, key_column: str = "company_domain"
                           ) -> pd.DataFrame | None:
        """One sheet, or several stacked, keyed by domain.

        `sheet` may be a list: the two "differences" sheets share a layout and
        are more useful as one table with a column saying which delivery each
        row came from. Most sheets key on company_domain; dataset_status keys
        on domain, hence key_column.
        """
        names = [sheet] if isinstance(sheet, str) else list(sheet)
        cache_key = "|".join(names)
        if cache_key not in self._predictleads:
            if not PREDICTLEADS_FILE.exists():
                self._predictleads[cache_key] = None
            else:
                try:
                    frames = []
                    for name in names:
                        frame = pd.read_excel(PREDICTLEADS_FILE, sheet_name=name)
                        if len(names) > 1:
                            frame.insert(0, "comparison", name)
                        frames.append(frame)
                    df = (pd.concat(frames, ignore_index=True, sort=False)
                          if len(frames) > 1 else frames[0])
                    # .copy() consolidates the block layout of very wide
                    # sheets (review_records has 210 columns), which otherwise
                    # makes the column add below emit a PerformanceWarning.
                    df = df.copy()
                    key = (df[key_column] if key_column in df.columns
                           else pd.Series([""] * len(df)))
                    df["__domain"] = key.map(normalize_domain)
                    if PREDICTLEADS_ENTITY_COLUMN in df.columns:
                        df["__entities"] = df[PREDICTLEADS_ENTITY_COLUMN].map(_entity_names)
                    self._predictleads[cache_key] = df
                except Exception as exc:
                    print(f"  ! could not read predictleads sheet '{cache_key}': {exc}")
                    self._predictleads[cache_key] = None
        return self._predictleads[cache_key]

    # -- Google News ------------------------------------------------------
    def google_news(self) -> pd.DataFrame | None:
        """Both news feeds, concatenated and de-duplicated.

        The RSS export and the Exa export carry the same columns but different
        coverage, so they are stacked rather than chosen between. Duplicates
        are dropped on (domain, headline, date): the domains in both feeds
        would otherwise contribute the same story twice. Exa is stacked first
        so it is the row kept - the client, 25 Sep: "consider exa news" where
        the two disagree (DEC-054a).

        Only rows inside the client's 12-month window are kept (see
        NEWS_WINDOW_DAYS); what the window removed is in RUN_STATS.
        """
        if self._google_news is None:
            frames = []
            window_end = pd.Timestamp(datetime.now(UTC).date(), tz="UTC") + pd.Timedelta(days=1)
            window_start = window_end - pd.Timedelta(days=NEWS_WINDOW_DAYS + 1)
            window = {"days": NEWS_WINDOW_DAYS,
                      "from": str(window_start.date()),
                      "to": str((window_end - pd.Timedelta(days=1)).date()),
                      "feeds": {}}
            for path, sheet, label in (
                (EXA_FILE, "exa_data", "exa"),
                (GOOGLE_NEWS_FILE, "google_news_rss_data", "google_news_rss"),
            ):
                if not path.exists():
                    continue
                df = pd.read_excel(path, sheet_name=sheet)
                dates = pd.to_datetime(df["event_date"], errors="coerce", utc=True)
                undated = dates.isna()
                older = dates < window_start
                future = dates >= window_end
                window["feeds"][label] = {
                    "file": path.name, "rows": len(df),
                    "undated": int(undated.sum()), "older": int(older.sum()),
                    "future": int(future.sum()),
                    "kept": int((~(undated | older | future)).sum()),
                }
                df = df[~(undated | older | future)].copy()
                df["__feed"] = label
                frames.append(df)
            RUN_STATS["news_window"] = window

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
                body = self._apply_intent_supplements(raw, body)
                self._hp_intent = body
        if self._hp_intent is False:
            return None, None
        return self._hp_intent, self._hp_intent_header

    @staticmethod
    def _apply_intent_supplements(raw: pd.DataFrame, body: pd.DataFrame) -> pd.DataFrame:
        """Replace a domain's intent row with a separately delivered one.

        A supplement is accepted only if its category bands sit in the same
        columns as the main workbook's; anything else would put a Poly score
        under PCs, so it stops the run rather than being read loosely.
        """
        main_bands = {i: str(v).split("(")[0].strip().lower()
                      for i, v in enumerate(raw.iloc[0].tolist()) if i > 4 and pd.notna(v)}
        for path, sheet, band_row, first_row in HP_INTENT_SUPPLEMENTS:
            if not path.exists():
                print(f"  ! intent supplement not found, main row kept: {path.name}")
                continue
            sup = pd.read_excel(path, sheet_name=sheet, header=None)
            bands = {i: str(v).split("(")[0].strip().lower()
                     for i, v in enumerate(sup.iloc[band_row].tolist())
                     if i > 4 and pd.notna(v)}
            if sup.shape[1] != raw.shape[1] or bands != main_bands:
                sys.exit(f"intent supplement {path.name}: category columns do not "
                         f"line up with {HP_INTENT_FILE.name}; not merged")
            rows = sup.iloc[first_row:].dropna(how="all").reset_index(drop=True)
            # Run Date in the main file's own format ("2026-09-17 09:20 UTC");
            # the supplement stores an Excel datetime.
            rows[2] = rows[2].map(lambda v: pd.Timestamp(v).strftime("%Y-%m-%d %H:%M UTC")
                                  if pd.notna(v) and not isinstance(v, str) else v)
            rows["__domain"] = rows[1].map(normalize_domain)
            rows["__name"] = rows[0].map(normalize_name)
            for _, row in rows.iterrows():
                domain = row["__domain"]
                replaced = body[body["__domain"] == domain]
                before = (str(replaced.iloc[0][3]) if not replaced.empty
                          else "no row")
                record_correction(
                    domain, "hp_category_intent row", f"{HP_INTENT_FILE.name}: {before}",
                    f"{path.name}: {row[3]} {row[4]}/100",
                    "separate client delivery for this account (C33); its scores are "
                    "public-source estimates, not measured buyer intent")
                # The main row's company name is kept: it is the territory
                # name the account is matched on, and the supplement's is not.
                if not replaced.empty:
                    row[0] = replaced.iloc[0][0]
                    row["__name"] = replaced.iloc[0]["__name"]
                body = pd.concat([body[body["__domain"] != domain],
                                  row.to_frame().T], ignore_index=True)
        return body

    # -- Client master list ----------------------------------------------
    def master_list(self) -> dict[str, dict] | None:
        """Rows of the client's Master List, keyed by Sales Territory Name.

        The sheet has 223 rows: 220 accounts plus three legend rows that
        explain the Account Type vocabulary and carry no country code, which
        is how they are told apart. The Parent-Child Groups and Recommended
        Merges sheets are folded in by territory name.
        """
        if self._master is None:
            if not MASTER_LIST_FILE.exists():
                self._master = False
                return None
            try:
                df = pd.read_excel(MASTER_LIST_FILE, sheet_name="Master List", dtype=str)
            except Exception as exc:
                print(f"  ! could not read master list: {exc}")
                self._master = False
                return None
            df.columns = [str(c).strip() for c in df.columns]
            rows: dict[str, dict] = {}
            for _, r in df.iterrows():
                cty = _clean(r.get("Cty"))
                territory = _clean(r.get("Sales Territory Name"))
                if not territory or not cty or len(cty) != 2:
                    continue  # legend rows
                rows[territory] = {
                    "sales_territory_name": territory,
                    "country": cty,
                    "global_parent": _clean(r.get("Global Parent / Group")),
                    "account_type": _clean(r.get("Account Type")),
                    "merge_group_id": _clean(r.get("Merge Group ID")),
                    "notes": _clean(r.get("Notes")),
                    "parent_child_group": None,
                    "parent_child_role": None,
                    "parent_child_notes": None,
                    "recommended_global_account_id": None,
                }
            for sheet, apply in (
                ("Parent-Child Groups", lambda row, r: row.update(
                    parent_child_group=_clean(r.iloc[0]),
                    parent_child_role=_clean(r.iloc[3]),
                    parent_child_notes=_clean(r.iloc[4]))),
                ("Recommended Merges", lambda row, r: row.update(
                    recommended_global_account_id=_clean(r.iloc[2]))),
            ):
                try:
                    extra = pd.read_excel(MASTER_LIST_FILE, sheet_name=sheet, dtype=str)
                except Exception:
                    continue
                member_col = 1 if sheet == "Parent-Child Groups" else 0
                for _, r in extra.iterrows():
                    member = _clean(r.iloc[member_col])
                    if member in rows:
                        apply(rows[member], r)
            self._master = rows
        return self._master if self._master is not False else None

    # -- Client domain audit ---------------------------------------------
    def domain_audit(self) -> dict[str, dict] | None:
        """Rows of the 219-account domain audit, keyed by territory name.

        Column B ("Master Company") is written the same way as the master
        list's Sales Territory Name - "NAME - XX" - so the two join on it
        directly. Whitespace is collapsed on both sides of that join.
        """
        if self._audit is None:
            if not DOMAIN_AUDIT_FILE.exists():
                self._audit = False
                return None
            try:
                df = pd.read_excel(DOMAIN_AUDIT_FILE, sheet_name=DOMAIN_AUDIT_SHEET,
                                   dtype=str)
            except Exception as exc:
                print(f"  ! could not read domain audit: {exc}")
                self._audit = False
                return None
            df.columns = [str(c).strip() for c in df.columns]
            rows: dict[str, dict] = {}
            for _, r in df.iterrows():
                company = _clean(r.get("Master Company"))
                if not company:
                    continue
                rows[_territory_key(company)] = {
                    "master_company": company,
                    "country": _clean(r.get("Country")),
                    "master_domain": normalize_domain(r.get("Master Domain")),
                    "predictleads_company": _clean(r.get("PredictLeads Company")),
                    "predictleads_domain": normalize_domain(r.get("PredictLeads Domain")),
                    "domain_check": _clean(r.get("Domain Check")),
                    "considerations": _clean(r.get("considerations to keep in mind")),
                }
            self._audit = rows
        return self._audit if self._audit is not False else None

    # -- Filings index -----------------------------------------------------
    def apollo_contacts(self) -> pd.DataFrame | None:
        """The Apollo Contacts sheet as delivered, every cell a string."""
        if getattr(self, "_apollo", None) is None:
            try:
                self._apollo = pd.read_excel(APOLLO_FILE, sheet_name=APOLLO_SHEET,
                                             header=APOLLO_HEADER_ROW, dtype=str)
                self._apollo = self._apollo.dropna(how="all")
            except Exception as exc:
                print(f"  ! could not read Apollo contacts: {exc}")
                self._apollo = False
        return self._apollo if self._apollo is not False else None

    def filings_index(self) -> pd.DataFrame | None:
        """filings 1.csv as delivered: strings only, blanks kept blank.

        Read with keep_default_na so that a blank cell is written back blank
        and a literal "NA" stays "NA" - the file round-trips byte-for-byte
        per account, which the idempotency check depends on.
        """
        if self._filings is None:
            if not FILINGS_INDEX_FILE.exists():
                self._filings = False
                return None
            try:
                frames = [pd.read_csv(path, dtype=str, keep_default_na=False,
                                      encoding="utf-8-sig")
                          for path in [FILINGS_INDEX_FILE, *FILINGS_SUPPLEMENT_FILES]
                          if path.exists()]
                # A supplement must be in the index's own columns, or its rows
                # would be written into _filings_index.csv misaligned.
                for extra in frames[1:]:
                    if list(extra.columns) != list(frames[0].columns):
                        raise ValueError("a filings supplement does not have "
                                         "filings 1.csv's columns")
                self._filings = pd.concat(frames, ignore_index=True)
            except Exception as exc:
                print(f"  ! could not read filings index: {exc}")
                self._filings = False
        return self._filings if self._filings is not False else None


def _clean(value) -> str | None:
    """A cell as a stripped string, or None when it is blank or NaN."""
    if value is None:
        return None
    if isinstance(value, float) and pd.isna(value):
        return None
    text = str(value).strip()
    return text if text and text.lower() != "nan" else None


def _territory_key(territory: str) -> str:
    """Join key for territory names: upper case, single spaces."""
    return " ".join(str(territory).upper().split())


def _territory_base(territory: str) -> str:
    """'WESTPAC BANKING CORPORATION - AU' -> 'WESTPAC BANKING CORPORATION'."""
    return re.sub(r"\s*-\s*[A-Z]{2}$", "", str(territory).strip())


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
        # The client's master-list row, attached by attach_master_list() once
        # the full account list is known. None when the list has no row.
        self.master: dict | None = None
        # The client's domain-audit row, attached by attach_domain_audit().
        # None for Astra, which the audit leaves out.
        self.audit: dict | None = None

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
# Account identity, filings index, feature dependencies
# --------------------------------------------------------------------------

# Filled once per run by assign_filings(); read per account afterwards.
FILINGS_BY_SLUG: dict[str, pd.DataFrame] = {}
UNASSIGNED_FILINGS: pd.DataFrame | None = None
# Run-level facts that belong in _RUN_SUMMARY.json but are produced outside
# write_run_summary(): master-list matching and filings assignment.
RUN_STATS: dict = {}


def attach_master_list(accounts: list[Account], sources: SourceData) -> dict:
    """Give each account its row from the client master list.

    Sales Territory Name is the vendor's company name plus a " - XX" country
    suffix. 215 match on the name alone; the three Ministry of Defence and two
    Westpac entities need the suffix, which is also what disambiguates their
    folders. A loose name match is the last resort and only counts when it is
    unique, because a wrong identity is worse than a missing one.
    """
    master = sources.master_list()
    stats = {"master_rows": 0, "matched": 0, "unmatched_territories": [],
             "accounts_without_master_row": []}
    if master is None:
        print("  ! master list not readable; _account.json carries vendor identity only")
        return stats
    stats["master_rows"] = len(master)
    by_slug = {a.slug: a for a in accounts}
    by_name_key: dict[str, list[Account]] = {}
    for acct in accounts:
        by_name_key.setdefault(acct.name_key, []).append(acct)

    taken: dict[str, str] = {}
    for territory, row in master.items():
        base_slug = slugify(_territory_base(territory))
        hit = next((c for c in (base_slug, f"{base_slug}_{row['country']}")
                    if c in by_slug), None)
        if hit is None:
            loose = by_name_key.get(normalize_name(_territory_base(territory)), [])
            if len(loose) == 1:
                hit = loose[0].slug
        if hit is None:
            stats["unmatched_territories"].append(territory)
            continue
        if hit in taken:
            print(f"  ! master list: '{territory}' and '{taken[hit]}' both resolve "
                  f"to {hit}; keeping the first")
            stats["unmatched_territories"].append(territory)
            continue
        by_slug[hit].master = row
        taken[hit] = territory
        stats["matched"] += 1
    stats["accounts_without_master_row"] = sorted(
        a.slug for a in accounts if a.master is None)
    return stats


def attach_domain_audit(accounts: list[Account], sources: SourceData) -> dict:
    """Give each account its domain-audit row and make its domain the audit's.

    Joined on the master list's territory name, so this runs after
    attach_master_list(). DOMAIN_ALIASES is expected to have already brought
    every vendor domain to the audit's column D; an account whose domain still
    differs is overridden here and reported, because its vendor rows may still
    sit under the old domain until an alias is added.
    """
    audit = sources.domain_audit()
    stats = {"audit_rows": 0, "matched": 0, "domain_overrides": [],
             "accounts_without_audit_row": [], "unmatched_audit_rows": []}
    if audit is None:
        print("  ! domain audit not readable; domains come from the vendor workbooks")
        return stats
    stats["audit_rows"] = len(audit)
    used = set()
    for acct in accounts:
        territory = (acct.master or {}).get("sales_territory_name")
        row = audit.get(_territory_key(territory)) if territory else None
        if row is None:
            stats["accounts_without_audit_row"].append(acct.slug)
            continue
        acct.audit = row
        used.add(_territory_key(territory))
        stats["matched"] += 1
        canonical = row["master_domain"]
        if canonical and acct.domain != canonical:
            record_correction(
                acct.slug, "domain", acct.domain, canonical,
                "client domain audit (DEC-052) names a different canonical "
                "domain; rows keyed under the old domain need an alias")
            stats["domain_overrides"].append(
                f"{acct.slug}: {acct.domain or '(blank)'} -> {canonical}")
            acct.domain = canonical
    stats["unmatched_audit_rows"] = sorted(
        row["master_company"] for key, row in audit.items() if key not in used)
    return stats


def assign_filings(accounts: list[Account], sources: SourceData) -> dict:
    """Attach each row of the filings index to one account, or to none.

    Keys, in order: the row's sales_territory_name against the master list
    (the crawl was driven from that list, so this is the intended link); then
    the row's domain, when exactly one account has it; then a loose company
    name match. A row whose territory and domain point at different accounts
    is not guessed at - it goes to _unassigned_filings.csv with both
    candidates named. Group-level entries ("Astra International Group",
    "Mitsubishi Group (keiretsu)") match nothing and land there too.
    """
    global UNASSIGNED_FILINGS
    df = sources.filings_index()
    stats = {"rows": 0, "by_client_ruling": 0, "by_territory": 0, "by_domain": 0,
             "by_company_name": 0, "unassigned": 0, "conflicts": []}
    if df is None:
        return stats
    stats["rows"] = int(len(df))

    terr2slug = {a.master["sales_territory_name"]: a.slug for a in accounts if a.master}
    dom2slugs: dict[str, list[str]] = {}
    name2slugs: dict[str, list[str]] = {}
    for a in accounts:
        if a.domain:
            dom2slugs.setdefault(a.domain, []).append(a.slug)
        name2slugs.setdefault(a.name_key, []).append(a.slug)

    matched_by, target, reason = [], [], []
    for _, row in df.iterrows():
        territory = str(row.get("sales_territory_name", "") or "").strip()
        domain = normalize_domain(row.get("domain", ""))
        t_slug = terr2slug.get(territory)
        d_hits = dom2slugs.get(domain, []) if domain else []
        d_slug = d_hits[0] if len(d_hits) == 1 else None
        n_hits = (name2slugs.get(normalize_name(_territory_base(territory)), [])
                  or name2slugs.get(normalize_name(row.get("company", "")), []))
        n_slug = n_hits[0] if len(n_hits) == 1 else None

        ruling = FILINGS_CLIENT_RULINGS.get((str(row.get("company", "")).strip(), territory))
        if ruling:
            matched_by.append("client_ruling"); target.append(ruling[0]); reason.append("")
            record_correction(ruling[0], "filings row",
                              f"{row.get('company', '')} under {territory}",
                              ruling[0], ruling[1])
        elif t_slug and d_slug and t_slug != d_slug:
            why = (f"territory says {t_slug}, domain {domain} says {d_slug}; "
                   f"not guessed - with the client for correction")
            stats["conflicts"].append(
                {"company": row.get("company", ""), "territory": territory,
                 "domain": domain, "territory_account": t_slug,
                 "domain_account": d_slug})
            matched_by.append(""); target.append(""); reason.append(why)
        elif t_slug:
            matched_by.append("sales_territory_name"); target.append(t_slug); reason.append("")
        elif d_slug:
            matched_by.append("domain"); target.append(d_slug); reason.append("")
        elif n_slug:
            matched_by.append("company_name"); target.append(n_slug); reason.append("")
        elif len(d_hits) > 1:
            matched_by.append(""); target.append("")
            reason.append(f"domain {domain} is shared by {', '.join(d_hits)} and the "
                          f"territory names no account")
        else:
            matched_by.append(""); target.append("")
            reason.append("no account matches the territory, domain or company name "
                          "(group-level entry, or an entity outside the 220)")

    df = df.copy()
    df["matched_by"] = matched_by
    df["__slug"] = target
    df["__reason"] = reason
    FILINGS_BY_SLUG.clear()
    assigned = df[df["__slug"] != ""]
    for slug, frame in assigned.groupby("__slug", sort=False):
        FILINGS_BY_SLUG[slug] = (frame.drop(columns=["__slug", "__reason"])
                                 .reset_index(drop=True))
    unassigned = df[df["__slug"] == ""].drop(columns=["__slug", "matched_by"])
    UNASSIGNED_FILINGS = (unassigned.rename(columns={"__reason": "reason"})
                          .reset_index(drop=True))
    for key, label in (("by_client_ruling", "client_ruling"),
                       ("by_territory", "sales_territory_name"),
                       ("by_domain", "domain"),
                       ("by_company_name", "company_name")):
        stats[key] = int((df["matched_by"] == label).sum())
    stats["unassigned"] = int(len(unassigned))
    return stats


# --------------------------------------------------------------------------
# Apollo contacts -> prospect_contacts
# --------------------------------------------------------------------------
# The Stakeholder Map reads prospect_contacts in Explorium's column layout, with
# Apollo's own fields under apollo_* (the shape of the Astra seed, where the
# pilot Apollo rows were first merged). Only what the Apollo row states is
# filled. Two things the pilot merge did are deliberately NOT repeated:
#   - buying_committee_personas: Apollo has no persona; "Requested Role" is the
#     role we asked the vendor to find, not the person's role, so it is kept
#     as apollo_requested_role and never promoted.
#   - Email Status "valid": Apollo's "Verified Work Email" carries only
#     Email Confidence "provided"; the ZeroBounce / Cleanlist verification
#     columns are empty on every row. Status is left blank.
# The contact's own location is not in the file (Country Code is the
# company's), so Prospect country_name stays blank as well.
PROSPECT_CONTACT_COLUMNS = [
    "Company Name", "Company Domain", "Business ID", "Prospect prospect_id",
    "Prospect professional_email_hashed", "Prospect first_name", "Prospect last_name",
    "Prospect full_name", "Prospect country_name", "Prospect region_name", "Prospect city",
    "Prospect linkedin", "Prospect experience", "Prospect skills", "Prospect interests",
    "Prospect company_name", "Prospect company_website", "Prospect company_linkedin",
    "Prospect job_department", "Prospect job_department_array",
    "Prospect job_department_main", "Prospect job_seniority_level",
    "Prospect job_level_array", "Prospect job_level_main", "Prospect job_title",
    "Prospect business_id", "Prospect linkedin_url_array",
    "Prospect buying_committee_personas", "Contact emails", "Contact professions_email",
    "Contact professional_email_status", "Contact phone_numbers", "Contact mobile_phone",
    "Email", "Email Status", "Mobile Phone", "Emails", "Phone Numbers", "data_source",
    "apollo_requested_contact", "apollo_matched_contact", "apollo_match_status",
    "apollo_match_rate", "apollo_personal_email", "apollo_personal_email_confidence",
    "apollo_email_confidence", "apollo_phone_confidence", "apollo_reports_to_org_chart",
    # beyond the seed's columns: the rest of the Apollo row, and our review flags
    "apollo_id", "apollo_seed_id", "apollo_country_code", "apollo_requested_role",
    "apollo_title", "apollo_seniority", "apollo_department",
    "apollo_verified_work_email", "apollo_verified_work_email_as_delivered",
    "apollo_direct_mobile_phone", "apollo_linkedin_url",
    "apollo_zerobounce_email_status", "apollo_phone_job_status", "apollo_review_reason",
    "review_flags",
]
APOLLO_DATA_SOURCE = f"Apollo ({APOLLO_FILE.name} / {APOLLO_SHEET})"

# Words that mark a "matched contact" as a team or channel rather than a person
# ("Internal Channels" came back for a Chief Digital Officer request).
NON_PERSON_WORDS = {"internal", "channels", "channel", "team", "department", "office",
                    "services", "admin", "support", "desk", "helpdesk", "centre",
                    "center", "unit", "communications", "info", "enquiries"}
# Labels too generic to say two domains belong to the same organisation.
_GENERIC_LABELS = {"www", "com", "co", "net", "org", "gov", "edu", "ac", "or", "go",
                   "au", "nz", "sg", "my", "jp", "kr", "th", "vn", "id", "ph", "hk",
                   "in", "cn", "group", "corp", "team", "mail"}

APOLLO_BY_SLUG: dict[str, pd.DataFrame] = {}


def _letters(text: str) -> str:
    return re.sub(r"[^a-z]", "", unicodedata.normalize("NFKD", str(text))
                  .encode("ascii", "ignore").decode().lower())


def _email_names_someone_else(name: str, email: str) -> bool:
    """True when nothing of the contact's name is in the email's local part.

    Passes: a name part inside the local part (rameshm@, jsy@ for Joy Sy,
    cassie.casner@ for Cassandra Lee-Casner), a local chunk that starts a name
    part (sus@ for Sussie, vijay@ for Vijaykumar), or initials only (fp@ for
    Faizal P). Fails: louise.wardley@ on "Peter Meehan", mazni@ on "Mohd Sabri".
    """
    tokens = [_letters(t) for t in re.split(r"[\s\-'.]+", str(name))]
    tokens = [t for t in tokens if t]
    chunks = [_letters(c) for c in re.split(r"[^A-Za-z]+", email.split("@")[0])]
    chunks = [c for c in chunks if c]
    local = "".join(chunks)
    if not local or not tokens:
        return False
    if any(len(t) >= 2 and t in local for t in tokens):
        return False
    if any(len(c) >= 3 and t.startswith(c) for c in chunks for t in tokens):
        return False
    initials = {t[0] for t in tokens}
    if all(len(c) <= 3 and set(c) <= initials for c in chunks):
        return False
    return True


def _domain_labels(domain: str) -> set[str]:
    return {l for l in domain.lower().split(".") if l and l not in _GENERIC_LABELS}


def apollo_review_flags(row: dict, company_domains: set[str]) -> list[str]:
    """Why a contact row should be looked at before a seller relies on it.

    company_domains: the account's domain, Apollo's Website Domain, and any
    email domain three or more of the account's contacts share (cba.com.au at
    Commonwealth Bank, woolworths.com.au at Woolworths Group) - a domain most
    of a company's staff use is that company's, whatever the website says.

    Flags are recorded, not acted on, except email_names_someone_else, where
    the email is withheld from every column the Stakeholder Map reads (see
    apollo_to_prospect); the delivered value stays in
    apollo_verified_work_email_as_delivered.
    """
    flags = []
    row = {k: _clean(v) or "" for k, v in row.items()}
    name = row.get("Matched Contact", "")
    email = row.get("Verified Work Email", "")
    if row.get("Match Status", "").lower() != "matched":
        flags.append("not_matched")
    if set(_letters(w) for w in name.split()) & NON_PERSON_WORDS:
        flags.append("name_looks_like_a_team_not_a_person")
    if email and _email_names_someone_else(name, email):
        flags.append("email_names_someone_else")
    if email:
        email_domain = email.split("@")[-1].lower()
        company = (company_domains | {normalize_domain(row.get("Website Domain"))}) - {""}
        if not any(email_domain == d or email_domain.endswith("." + d) for d in company):
            if not any(_domain_labels(email_domain) & _domain_labels(d) for d in company):
                flags.append("email_domain_not_the_company")
    if row.get("Phone Job Status", "").lower() not in ("", "result retrieved"):
        flags.append("phone_lookup_needs_review")
    return flags


def apollo_to_prospect(row: dict, company_domains: set[str], sister: bool) -> dict:
    """One Apollo row in the prospect_contacts layout."""
    def v(key):
        value = _clean(row.get(key))
        return value or ""

    flags = apollo_review_flags(row, company_domains)
    if sister:
        flags.append("same_person_listed_under_sister_account")
    name = v("Matched Contact")
    first, _, last = name.partition(" ")
    email = "" if "email_names_someone_else" in flags else v("Verified Work Email")
    phone = v("Direct Mobile Phone")
    linkedin = v("Linkedin Url")
    return {
        "Company Name": v("Company Name"),
        "Company Domain": v("Website Domain"),
        "Prospect prospect_id": v("Apollo Id"),
        "Prospect first_name": first,
        "Prospect last_name": last,
        "Prospect full_name": name,
        "Prospect linkedin": linkedin,
        "Prospect company_name": v("Company Name"),
        "Prospect company_website": v("Website Domain"),
        "Prospect job_department": v("Department"),
        "Prospect job_department_array": json.dumps([v("Department")]) if v("Department") else "",
        "Prospect job_department_main": v("Department"),
        "Prospect job_seniority_level": v("Seniority"),
        "Prospect job_level_array": json.dumps([v("Seniority")]) if v("Seniority") else "",
        "Prospect job_level_main": v("Seniority"),
        "Prospect job_title": v("Title"),
        "Prospect linkedin_url_array": json.dumps([linkedin]) if linkedin else "",
        "Contact emails": json.dumps([{"address": email}]) if email else "",
        "Contact professions_email": email,
        "Contact phone_numbers": json.dumps([{"number": phone}]) if phone else "",
        "Contact mobile_phone": phone,
        "Email": email,
        "Mobile Phone": phone,
        "Emails": email,
        "Phone Numbers": phone,
        "data_source": APOLLO_DATA_SOURCE,
        "apollo_requested_contact": v("Requested Contact"),
        "apollo_matched_contact": name,
        "apollo_match_status": v("Match Status"),
        "apollo_match_rate": v("Match Rate Per Requested Contact"),
        "apollo_personal_email": v("Personal Email"),
        "apollo_personal_email_confidence": v("Personal Email Confidence"),
        "apollo_email_confidence": v("Email Confidence"),
        "apollo_phone_confidence": v("Phone Confidence"),
        "apollo_reports_to_org_chart": v("Reports To Org Chart"),
        "apollo_id": v("Apollo Id"),
        "apollo_seed_id": v("Seed Id"),
        "apollo_country_code": v("Country Code"),
        "apollo_requested_role": v("Requested Role"),
        "apollo_title": v("Title"),
        "apollo_seniority": v("Seniority"),
        "apollo_department": v("Department"),
        # The Stakeholder Map falls back to apollo_verified_work_email when
        # the display columns are blank, so a withheld email must be blank
        # here too; the delivered value is kept under a column nothing reads.
        "apollo_verified_work_email": email,
        "apollo_verified_work_email_as_delivered": v("Verified Work Email"),
        "apollo_direct_mobile_phone": phone,
        "apollo_linkedin_url": linkedin,
        "apollo_zerobounce_email_status": v("Zerobounce Email Status"),
        "apollo_phone_job_status": v("Phone Job Status"),
        "apollo_review_reason": v("Review Reason"),
        "review_flags": "; ".join(flags),
    }


def assign_apollo_contacts(accounts: list[Account], sources: SourceData) -> dict:
    """Attach each Apollo contact row to one account, or report it.

    Keys, in order: Company Name + " - " + Country Code against the master
    list's Sales Territory Name; then the bare name where the territory has
    no suffix (Bunnings) and the master country agrees; then the domain when
    exactly one account has it. The row's domain is checked against the
    account's either way, and a disagreement is reported, not overridden.
    """
    APOLLO_BY_SLUG.clear()
    df = sources.apollo_contacts()
    stats = {"rows": 0, "by_territory": 0, "by_name_and_country": 0, "by_domain": 0,
             "unassigned": [], "domain_disagreements": [], "accounts_with_contacts": 0,
             "flags": {}, "emails_withheld": 0}
    if df is None:
        return stats
    stats["rows"] = int(len(df))

    by_territory = {_territory_key(a.master["sales_territory_name"]): a
                    for a in accounts if a.master}
    by_domain: dict[str, list[Account]] = {}
    for a in accounts:
        if a.domain:
            by_domain.setdefault(a.domain, []).append(a)

    # A person the vendor filed under both sister entities (same Apollo Id on
    # Jabil MY and SG, MUFG JP and Bangkok, UOB SG and MY) stays on both, as
    # delivered - the same rule as PredictLeads' dual-entity rows - and is
    # flagged so a seller knows the contact is shared.
    id_accounts: dict[str, set[str]] = {}
    placed: list[tuple[Account, dict]] = []
    for row in df.to_dict("records"):
        name, cc = _clean(row.get("Company Name")) or "", _clean(row.get("Country Code")) or ""
        domain = normalize_domain(row.get("Website Domain"))
        acct = by_territory.get(_territory_key(f"{name} - {cc}"))
        how = "by_territory"
        if acct is None:
            acct = by_territory.get(_territory_key(name))
            how = "by_name_and_country"
            if acct is not None and (acct.master or {}).get("country") not in ("", None, cc):
                acct = None
        if acct is None and len(by_domain.get(domain, [])) == 1:
            acct, how = by_domain[domain][0], "by_domain"
        if acct is None:
            stats["unassigned"].append(f"{name} - {cc} ({domain})")
            continue
        stats[how] += 1
        if domain and acct.domain and domain != acct.domain:
            stats["domain_disagreements"].append(
                f"{acct.slug}: Apollo {domain} vs account {acct.domain}")
        placed.append((acct, row))
        if _clean(row.get("Apollo Id")):
            id_accounts.setdefault(row["Apollo Id"], set()).add(acct.slug)

    email_domains: dict[str, dict[str, int]] = {}
    for acct, row in placed:
        email = _clean(row.get("Verified Work Email"))
        if email and "@" in email:
            counts = email_domains.setdefault(acct.slug, {})
            d = email.split("@")[-1].lower()
            counts[d] = counts.get(d, 0) + 1

    grouped: dict[str, list[dict]] = {}
    slug_to_account = {a.slug: a for a in accounts}
    for acct, row in placed:
        sister = len(id_accounts.get(row.get("Apollo Id"), ())) > 1
        company_domains = {acct.domain} | {
            d for d, n in email_domains.get(acct.slug, {}).items() if n >= 3}
        grouped.setdefault(acct.slug, []).append(
            apollo_to_prospect(row, company_domains, sister))
    for slug, rows in grouped.items():
        frame = pd.DataFrame(rows).reindex(columns=PROSPECT_CONTACT_COLUMNS).fillna("")
        APOLLO_BY_SLUG[slug] = frame
        flagged = frame[frame["review_flags"] != ""]
        if len(flagged):
            record_correction(
                slug_to_account[slug].name, "prospect_contacts review_flags",
                f"{len(flagged)} of {len(frame)} Apollo rows", "flagged, kept",
                "; ".join(f"{k} x{n}" for k, n in
                          pd.Series("; ".join(flagged["review_flags"]).split("; "))
                          .value_counts().items()))
    all_rows = pd.concat(APOLLO_BY_SLUG.values()) if APOLLO_BY_SLUG else pd.DataFrame()
    if len(all_rows):
        stats["flags"] = {k: int(n) for k, n in
                          pd.Series([f for fl in all_rows["review_flags"] if fl
                                     for f in fl.split("; ")]).value_counts().items()}
        stats["emails_withheld"] = int(all_rows["review_flags"]
                                       .str.contains("email_names_someone_else").sum())
    stats["accounts_with_contacts"] = len(APOLLO_BY_SLUG)
    stats["accounts_without_contacts"] = sorted(
        a.slug for a in accounts if a.slug not in APOLLO_BY_SLUG)
    return stats


def load_feature_dependencies() -> dict[str, dict]:
    """feature_key -> {display_name, dependent_datasets}, from the backend.

    Imported when the backend package is importable (it is, from its venv);
    otherwise parsed out of the file so the script still works from a bare
    interpreter. Either way the source of truth is feature_mapping.py, which
    is also what the upload endpoint regenerates from.
    """
    src_dir = FEATURE_MAPPING_FILE.parents[3]  # hp-backend/src
    try:
        if str(src_dir) not in sys.path:
            sys.path.insert(0, str(src_dir))
        from app.api.v1.feature_mapping import FEATURE_MAPPINGS  # type: ignore
        return {
            key: {"display_name": spec.get("display_name", key),
                  "dependent_datasets": list(spec.get("dependent_datasets", []))}
            for key, spec in FEATURE_MAPPINGS.items()
        }
    except Exception as exc:
        print(f"  (feature_mapping import failed - {exc}; parsing the file instead)")

    if not FEATURE_MAPPING_FILE.exists():
        print("  ! feature_mapping.py not found; readiness will be skipped")
        return {}
    text = FEATURE_MAPPING_FILE.read_text()
    deps: dict[str, dict] = {}
    # Feature entries sit at four-space indent inside FEATURE_MAPPINGS; the
    # nested mapped_fields dicts are deeper, so this split isolates features.
    blocks = re.split(r'\n    "(\w+)":\s*\{', text)
    for i in range(1, len(blocks) - 1, 2):
        key, body = blocks[i], blocks[i + 1]
        name = re.search(r'"display_name":\s*"([^"]+)"', body)
        lst = re.search(r'"dependent_datasets":\s*\[(.*?)\]', body, re.S)
        if not lst:
            continue
        deps[key] = {"display_name": name.group(1) if name else key,
                     "dependent_datasets": re.findall(r'"(\w+)"', lst.group(1))}
    return deps


# --------------------------------------------------------------------------
# Extraction
# --------------------------------------------------------------------------

def _entity_names(value) -> frozenset:
    """The territory names a PredictLeads row is attributed to."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return frozenset()
    return frozenset(normalize_name(part) for part in str(value).split(";")
                     if part.strip())


def _splits_by_entity(sources: SourceData, spec: dict) -> bool:
    """True when this PredictLeads sheet carries the per-row entity names."""
    df = sources.predictleads_sheet(spec["sheet"], spec.get("key", "company_domain"))
    return df is not None and "__entities" in df.columns


def _entity_match(names: frozenset, account: Account) -> bool:
    """Whether a row naming `names` belongs to this account."""
    territory = normalize_name((account.master or {}).get("sales_territory_name") or "")
    if not territory or territory not in names:
        return False
    return len(names) == 1 or DUAL_ENTITY_ROWS_TO_BOTH


def _shared_domain_fanout(frame: pd.DataFrame, accounts: list[Account]) -> tuple[int, int]:
    """(extra copies written, rows written nowhere) on the shared domains."""
    extra = unassigned = 0
    for domain in SHARED_DOMAIN_PRIMARY:
        holders = [a for a in accounts if a.domain == domain]
        if not holders:
            continue
        for names in frame.loc[frame["__domain"] == domain, "__entities"]:
            reached = sum(1 for a in holders if _entity_match(names, a))
            if reached == 0:
                unassigned += 1
            else:
                extra += reached - 1
    return extra, unassigned


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

    # A domain shared with another account yields rows to the primary only,
    # except in PredictLeads, whose rows name their entity (split below).
    # Checked before any filtering so every domain-keyed source is covered by
    # one rule rather than three.
    if source in (PREDICTLEADS, GOOGLE_NEWS, HP_INTENT):
        primary = SHARED_DOMAIN_PRIMARY.get(account.domain)
        if primary and primary != account.slug and not (
                source == PREDICTLEADS and _splits_by_entity(sources, spec)):
            return None, None, (
                f"{account.domain} is shared with {primary}, which keeps these "
                f"rows; no field in the source splits them by entity")

    if source == APOLLO:
        frame = APOLLO_BY_SLUG.get(account.slug)
        if frame is not None and len(frame):
            return frame, list(frame.columns), ""
        fallback = spec.get("fallback")
        if fallback:
            df, header, reason = extract_dataset(account, dataset_key, fallback, sources)
            if df is not None:
                return df, header, reason
        return None, PROSPECT_CONTACT_COLUMNS, (
            f"no contacts for this account in {APOLLO_FILE.name} "
            f"(Explorium's sheet is empty too)")

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
        df = sources.predictleads_sheet(spec["sheet"], spec.get("key", "company_domain"))
        label = (spec["sheet"] if isinstance(spec["sheet"], str)
                 else " + ".join(spec["sheet"]))
        if df is None:
            return None, None, "predictleads workbook or sheet unavailable"
        if not account.domain:
            return None, list(df.columns), "no domain for this account, cannot filter"
        subset = df[df["__domain"] == account.domain]
        if account.domain in SHARED_DOMAIN_PRIMARY and _splits_by_entity(sources, spec):
            subset = subset[subset["__entities"].map(
                lambda names: _entity_match(names, account))]
        subset = subset.drop(columns=[c for c in ("__domain", "__entities")
                                      if c in subset.columns])
        cols = [c for c in df.columns if c not in ("__domain", "__entities")]
        if subset.empty:
            return None, cols, f"no rows for {account.domain} in predictleads '{label}'"
        return subset, cols, ""

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
                readme.write_text(
                    "Drop this account's PDF filings here (annual reports,\n"
                    "exchange filings, monthly market reports).\n\n"
                    "_filings_index.csv, when present, lists the documents the\n"
                    "filings crawl found for this account: title, type, fiscal\n"
                    "year and document_url. The PDFs themselves are not here -\n"
                    "local_path points at the crawler's machine - so download\n"
                    "from document_url or ask for the folder, then drop them in.\n\n"
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

    # Datasets still empty that a benchmark seed can fill (Astra only, today).
    seed_dir = SEED_FILL.get(account.slug)
    preferred = SEED_PREFERRED.get(account.slug, set())
    if seed_dir is not None and seed_dir.exists():
        for dataset_key, info in manifest["datasets"].items():
            if info.get("kind") == "pdf_directory":
                continue
            if info["rows"] and dataset_key not in preferred:
                continue
            src = seed_dir / f"{dataset_key}.csv"
            if not src.exists():
                continue
            displaced = bool(info["rows"])
            if displaced:
                # Keep what the 220-account sources gave, beside the seed.
                ref_key = f"{info['source']}_{dataset_key}"
                if not dry_run:
                    kept = pd.read_csv(out_dir / f"{dataset_key}.csv", dtype=str,
                                       keep_default_na=False, encoding=ENCODING)
                    write_reference(out_dir, ref_key, kept, dry_run)
                manifest.setdefault("seed_preferred", {})[dataset_key] = {
                    "displaced_rows": info["rows"], "displaced_source": info["source"],
                    "kept_at": f"{REFERENCE_DIR}/{ref_key}.csv"}
                record_correction(
                    account.name, f"{dataset_key} source",
                    f"{info['rows']} rows from {info['source']}",
                    str(src.relative_to(REPO_ROOT)),
                    f"seed kept live (SEED_PREFERRED); the {info['source']} rows "
                    f"are in {REFERENCE_DIR}/{ref_key}.csv pending a decision")
            rows = copy_seed_dataset(src, out_dir / f"{dataset_key}.csv",
                                     dataset_key, dry_run)
            if not rows:
                continue
            info.update({"rows": rows, "source": "seed", "sheet": None,
                         "status": "ok", "reason": None,
                         "seed_file": str(src.relative_to(REPO_ROOT))})
            if displaced:
                continue
            record_correction(
                account.name, f"{dataset_key} source",
                "no rows in the 220-account sources",
                str(src.relative_to(REPO_ROOT)),
                "filled from the Astra benchmark seed; the client's E2 answer "
                "says Astra's PredictLeads data is a separate delivery, and the "
                "seed is that delivery")
        missing = [(k, r) for k, r in missing if manifest["datasets"][k]["rows"] == 0]

    # Reference tables: split for completeness, never uploaded.
    manifest["reference"] = {}
    for key, spec in REFERENCE_PLAN.items():
        df, _header, reason = extract_dataset(account, key, spec, sources)
        rows = write_reference(out_dir, key, df, dry_run)
        manifest["reference"][key] = {
            "rows": rows,
            "source": spec["source"],
            "sheet": (spec["sheet"] if isinstance(spec["sheet"], str)
                      else " + ".join(spec["sheet"])),
            "status": "ok" if rows else "empty",
            "reason": reason or None,
            "file": f"{REFERENCE_DIR}/{key}.csv" if rows else None,
        }
    if not dry_run:
        write_reference_readme(out_dir)

    manifest["filings_index"] = write_filings_index(out_dir, account.slug, dry_run)
    manifest["account"] = account_identity(account)

    if not dry_run:
        (out_dir / "_account.json").write_text(
            json.dumps(manifest["account"], indent=2, ensure_ascii=False) + "\n")
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
        hiring = manifest["reference"].get("explorium_hiring_events", {}).get("rows", 0)
        if manifest["datasets"].get("job_openings", {}).get("rows", 0) == 0 and hiring:
            lines += [
                "",
                f"  note: job_openings is empty, but {REFERENCE_DIR}/explorium_hiring_events.csv",
                f"        holds {hiring} Explorium hiring events for this account. No",
                "        dataset_key reads them yet; they are the nearest hiring signal we hold.",
            ]
        filings_rows = manifest["filings_index"]["rows"]
        if filings_rows:
            lines += [
                "",
                f"  note: compliance_filings has no PDFs, but compliance_filings/_filings_index.csv",
                f"        lists {filings_rows} document(s) found for this account, with URLs.",
            ]
        (out_dir / "_MISSING.txt").write_text("\n".join(lines) + "\n")

    manifest["_missing"] = missing
    return manifest


def copy_seed_dataset(src: Path, target: Path, dataset_key: str, dry_run: bool) -> int:
    """Copy one benchmark CSV into an account folder, re-encoded to ENCODING.

    Returns the data row count. The seed files were written by hand over
    time and two encodings are in play (hp_category_intent is Windows-1252),
    so the bytes are decoded rather than copied.
    """
    raw = src.read_bytes()
    text = None
    for encoding in ("utf-8-sig", "cp1252"):
        try:
            text = raw.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    if text is None:
        return 0
    try:
        header = [0, 1] if dataset_key == "hp_category_intent" else 0
        rows = len(pd.read_csv(io.StringIO(text), header=header, low_memory=False))
    except Exception:
        return 0
    if rows and not dry_run:
        target.write_text(text, encoding=ENCODING)
    return rows


def write_reference(out_dir: Path, key: str, df, dry_run: bool) -> int:
    """One reference table. Written only when it has rows; a stale file from
    an earlier run over different sources is removed, so the folder never
    claims data the current sources do not hold."""
    target = out_dir / REFERENCE_DIR / f"{key}.csv"
    if df is None or df.empty:
        if not dry_run and target.exists():
            target.unlink()
        return 0
    if dry_run:
        return len(df)
    target.parent.mkdir(exist_ok=True)
    df.to_csv(target, index=False, encoding=ENCODING)
    return len(df)


def write_reference_readme(out_dir: Path):
    ref_dir = out_dir / REFERENCE_DIR
    ref_dir.mkdir(exist_ok=True)
    lines = [
        "Tables we hold for this account that have NO dataset_key in the backend.",
        "They are split here so the account folder is the one place to look for",
        "everything we have, and so each table is already per-account on the day",
        "a feature starts reading it. Nothing in this folder is uploaded: the",
        "upload endpoint would reject a key it does not know.",
        "",
        "Only tables with rows are written. The full slot set is:",
        "",
    ]
    for key, spec in REFERENCE_PLAN.items():
        sheet = spec["sheet"] if isinstance(spec["sheet"], str) else " + ".join(spec["sheet"])
        lines.append(f"  {key + '.csv':<40} {spec['source']} / {sheet}")
    lines += [
        "",
        "See _manifest.json (\"reference\") for row counts and why a table is empty.",
    ]
    (ref_dir / "README.txt").write_text("\n".join(lines) + "\n")


def write_filings_index(out_dir: Path, slug: str, dry_run: bool) -> dict:
    """This account's rows from filings 1.csv, into compliance_filings/."""
    frame = FILINGS_BY_SLUG.get(slug)
    info = {"rows": 0, "documents_with_url": 0, "file": None,
            "source": " + ".join(str(p.relative_to(REPO_ROOT)) for p in
                                 [FILINGS_INDEX_FILE, *FILINGS_SUPPLEMENT_FILES]
                                 if p.exists())}
    target = out_dir / "compliance_filings" / "_filings_index.csv"
    if frame is None or frame.empty:
        if not dry_run and target.exists():
            target.unlink()
        return info
    info["rows"] = int(len(frame))
    if "document_url" in frame.columns:
        info["documents_with_url"] = int(
            frame["document_url"].astype(str).str.startswith("http").sum())
    info["file"] = "compliance_filings/_filings_index.csv"
    if not dry_run:
        target.parent.mkdir(exist_ok=True)
        frame.to_csv(target, index=False, encoding=ENCODING)
    return info


def account_identity(account: Account) -> dict:
    """What an account is called, by us and by the client.

    name_for_upload is the client's Sales Territory Name when we have it: it
    is unique across the 220 (the vendor's company name is not - see the
    Ministry of Defence and Westpac folders) and it is the name the client
    will look for.
    """
    master = account.master or {}
    return {
        "account_slug": account.slug,
        "vendor_company_name": account.name,
        "domain": account.domain,
        "name_for_upload": master.get("sales_territory_name") or account.name,
        "master_list": account.master,
        "domain_audit": account.audit,
    }


# --------------------------------------------------------------------------
# Readiness: which features each account can feed
# --------------------------------------------------------------------------

def compute_readiness(manifest: dict, deps: dict, nobody_has: set[str]) -> dict:
    rows = {k: v.get("rows", 0) for k, v in manifest["datasets"].items()}
    out = {}
    for key, spec in deps.items():
        wanted = spec["dependent_datasets"]
        present = [d for d in wanted if rows.get(d, 0) > 0]
        missing = [d for d in wanted if rows.get(d, 0) == 0]
        status = "complete" if not missing else ("none" if not present else "partial")
        out[key] = {
            "display_name": spec["display_name"],
            "status": status,
            "present": present,
            "missing": missing,
            # True when the only gaps are datasets no account has at all, so
            # this account is as complete as the sources allow.
            "complete_on_available_data": all(d in nobody_has for d in missing),
        }
    return out


def write_readiness(manifests: list[dict], deps: dict) -> set[str]:
    """Per-account _READINESS.txt, and the readiness block in each manifest.

    Runs after every account is split because "no account has this dataset"
    is only known then. With --account the set is computed over the subset,
    so read that flag with care on a partial run.
    """
    if not deps:
        return set()
    # "Nobody has it" means the 220-account sources supply nothing for it. A
    # dataset filled from a benchmark seed does not count: Astra's seeded
    # contacts must not make the other 219 accounts look specifically short
    # of contacts when the gap is the contact file nobody has received.
    nobody_has = {
        key for key in DATASET_PLAN
        if all(m["datasets"].get(key, {}).get("rows", 0) == 0
               or m["datasets"][key].get("source") == "seed"
               for m in manifests)
    }
    for manifest in manifests:
        manifest["readiness"] = compute_readiness(manifest, deps, nobody_has)
        manifest["datasets_nobody_has"] = sorted(nobody_has)
        out_dir = OUTPUT_DIR / manifest["account_slug"]
        on_disk = {k: v for k, v in manifest.items() if not k.startswith("_")}
        (out_dir / "_manifest.json").write_text(json.dumps(on_disk, indent=2))
        (out_dir / "_READINESS.txt").write_text(render_readiness(manifest, nobody_has))
    return nobody_has


def render_readiness(manifest: dict, nobody_has: set[str]) -> str:
    master = (manifest.get("account") or {}).get("master_list") or {}
    tables = manifest["datasets"]
    have = [k for k, v in tables.items() if v.get("rows", 0) > 0]
    missing = [k for k, v in tables.items() if v.get("rows", 0) == 0]
    ref = manifest.get("reference", {})
    ref_have = [k for k, v in ref.items() if v.get("rows", 0) > 0]
    filings = manifest.get("filings_index", {})

    def star(key):
        return f"{key}*" if key in nobody_has else key

    lines = [
        f"Feature readiness for {manifest['account_name']} ({manifest['account_slug']})",
        f"Territory:     {master.get('sales_territory_name') or '(no master-list row)'}",
        f"Country:       {master.get('country') or '-'}    Domain: {manifest['domain'] or '-'}",
        f"Global parent: {master.get('global_parent') or '-'}    "
        f"Account type: {master.get('account_type') or '-'}",
        "",
        f"Datasets with rows: {len(have)} of {len(tables)}",
        "Missing:            " + (", ".join(star(k) for k in missing) or "none"),
        f"Reference tables:   {len(ref_have)} of {len(ref)} with rows"
        + (f" ({', '.join(ref_have)})" if ref_have else ""),
        f"Filings index:      {filings.get('rows', 0)} document(s), "
        f"{filings.get('documents_with_url', 0)} with a URL; PDFs not yet in the folder",
        "",
        f"{'Feature':<36} {'Status':<9} Missing inputs",
        "-" * 78,
    ]
    for key, r in manifest.get("readiness", {}).items():
        miss = ", ".join(star(d) for d in r["missing"]) or "-"
        lines.append(f"{key:<36} {r['status']:<9} {miss}")
    lines += [
        "",
        "* = the 220-account sources hold this for no account (a benchmark seed",
        "    does not count): a source gap, not something specific to this account.",
        "    A feature whose only missing inputs are starred is as complete as the",
        "    sources allow.",
        "",
        "complete = every dataset the feature declares is present",
        "partial  = some are; the feature runs, and the parts fed by the missing",
        "           datasets come out empty",
        "none     = nothing it reads is present",
        "Dependencies are read from FEATURE_MAPPINGS in",
        "hp-backend/src/app/api/v1/feature_mapping.py, which is what the upload",
        "endpoint regenerates from.",
    ]
    return "\n".join(lines) + "\n"


def write_root_indexes(manifests: list[dict], deps: dict, nobody_has: set[str]):
    """_ACCOUNTS.csv, _READINESS.csv, _DATASET_USAGE.md, _unassigned_filings.csv.

    No timestamps inside any of these: the CSVs are fingerprinted by the
    validator's idempotency check, and the point of the indexes is to be
    diffable between runs.
    """
    features = list(deps)

    # -- _ACCOUNTS.csv ------------------------------------------------------
    fields = ["account_slug", "account_name", "sales_territory_name", "country",
              "domain", "global_parent", "account_type", "merge_group_id",
              "parent_child_group", "parent_child_role",
              "recommended_global_account_id",
              "audit_master_company", "audit_master_domain",
              "audit_predictleads_company", "audit_predictleads_domain",
              "audit_domain_check", "audit_considerations", "explorium_file",
              "tables_with_rows", "tables_total", "missing_tables",
              "reference_tables_with_rows", "filings_index_rows",
              "features_complete", "features_partial", "features_none",
              "complete_on_available_data"]
    with open(OUTPUT_DIR / "_ACCOUNTS.csv", "w", newline="", encoding=ENCODING) as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        for m in manifests:
            master = (m.get("account") or {}).get("master_list") or {}
            audit = (m.get("account") or {}).get("domain_audit") or {}
            tables = m["datasets"]
            have = [k for k, v in tables.items() if v.get("rows", 0) > 0]
            missing = [k for k, v in tables.items() if v.get("rows", 0) == 0]
            readiness = m.get("readiness", {})
            counts = {s: sum(1 for r in readiness.values() if r["status"] == s)
                      for s in ("complete", "partial", "none")}
            writer.writerow({
                "account_slug": m["account_slug"],
                "account_name": m["account_name"],
                "sales_territory_name": master.get("sales_territory_name") or "",
                "country": master.get("country") or "",
                "domain": m["domain"] or "",
                "global_parent": master.get("global_parent") or "",
                "account_type": master.get("account_type") or "",
                "merge_group_id": master.get("merge_group_id") or "",
                "parent_child_group": master.get("parent_child_group") or "",
                "parent_child_role": master.get("parent_child_role") or "",
                "recommended_global_account_id":
                    master.get("recommended_global_account_id") or "",
                "audit_master_company": audit.get("master_company") or "",
                "audit_master_domain": audit.get("master_domain") or "",
                "audit_predictleads_company": audit.get("predictleads_company") or "",
                "audit_predictleads_domain": audit.get("predictleads_domain") or "",
                "audit_domain_check": audit.get("domain_check") or "",
                "audit_considerations": audit.get("considerations") or "",
                "explorium_file": m.get("explorium_file") or "",
                "tables_with_rows": len(have),
                "tables_total": len(tables),
                "missing_tables": "; ".join(missing),
                "reference_tables_with_rows": sum(
                    1 for v in m.get("reference", {}).values() if v.get("rows", 0) > 0),
                "filings_index_rows": m.get("filings_index", {}).get("rows", 0),
                "features_complete": counts["complete"],
                "features_partial": counts["partial"],
                "features_none": counts["none"],
                "complete_on_available_data":
                    "yes" if all(k in nobody_has for k in missing) else "no",
            })

    # -- _READINESS.csv -----------------------------------------------------
    with open(OUTPUT_DIR / "_READINESS.csv", "w", newline="", encoding=ENCODING) as fh:
        writer = csv.writer(fh)
        writer.writerow(["account_slug", "sales_territory_name"] + features)
        for m in manifests:
            master = (m.get("account") or {}).get("master_list") or {}
            readiness = m.get("readiness", {})
            writer.writerow(
                [m["account_slug"], master.get("sales_territory_name") or ""]
                + [readiness.get(f, {}).get("status", "") for f in features])

    # -- _unassigned_filings.csv -------------------------------------------
    if UNASSIGNED_FILINGS is not None:
        UNASSIGNED_FILINGS.to_csv(OUTPUT_DIR / "_unassigned_filings.csv",
                                  index=False, encoding=ENCODING)

    # -- _DATASET_USAGE.md --------------------------------------------------
    readers: dict[str, list[str]] = {}
    for feature, spec in deps.items():
        for dataset in spec["dependent_datasets"]:
            readers.setdefault(dataset, []).append(feature)
    total = len(manifests)

    def have_count(section, key):
        return sum(1 for m in manifests if m.get(section, {}).get(key, {}).get("rows", 0) > 0)

    md = [
        "# Dataset usage across the account split",
        "",
        f"{total} account folders. 'Read by' comes from FEATURE_MAPPINGS.dependent_datasets",
        "in hp-backend/src/app/api/v1/feature_mapping.py: it is the list the upload",
        "endpoint regenerates when that dataset is uploaded, so it is also the list of",
        "features that will show something from it.",
        "",
        "## Uploadable datasets (one CSV per dataset_key at the top of each folder)",
        "",
        "| dataset_key | source | accounts with rows | read by |",
        "|---|---|---|---|",
    ]
    for key, spec in DATASET_PLAN.items():
        source = (f"{spec['source']} / {spec['sheet']}" if spec.get("source")
                  else "no feed yet (PDFs)")
        read_by = ", ".join(readers.get(key, [])) or "(no feature declares it)"
        md.append(f"| {key} | {source} | {have_count('datasets', key)} / {total} | {read_by} |")
    md += [
        "",
        "## Reference tables (reference/ in each folder; no dataset_key, not uploaded)",
        "",
        "| file | source | accounts with rows | read by |",
        "|---|---|---|---|",
    ]
    for key, spec in REFERENCE_PLAN.items():
        sheet = spec["sheet"] if isinstance(spec["sheet"], str) else " + ".join(spec["sheet"])
        md.append(f"| {REFERENCE_DIR}/{key}.csv | {spec['source']} / {sheet} | "
                  f"{have_count('reference', key)} / {total} | no feature yet |")
    filings_accounts = sum(1 for m in manifests if m.get("filings_index", {}).get("rows", 0) > 0)
    filings_rows = sum(m.get("filings_index", {}).get("rows", 0) for m in manifests)
    md += [
        "",
        "## Filings index",
        "",
        f"compliance_filings/_filings_index.csv is present in {filings_accounts} / {total} "
        f"folders ({filings_rows} documents). It is the crawl index, not the PDFs; the",
        "compliance_filings dataset is fed only once PDFs are dropped in and uploaded.",
        "Rows that matched no single account are in _unassigned_filings.csv.",
        "",
        "## Features and the datasets they read",
        "",
        "| feature | display name | inputs |",
        "|---|---|---|",
    ]
    for feature, spec in deps.items():
        md.append(f"| {feature} | {spec['display_name']} | "
                  f"{', '.join(spec['dependent_datasets'])} |")
    md += [
        "",
        "## Mapping note",
        "",
        "`news_events` holds PredictLeads' news table because that is the schema the",
        "news extractor reads (summary, article_sentence, effective_date, found_at).",
        "Explorium's `13_News_Events` event log goes to `news_events_additional`, which",
        "no feature reads. Earlier runs of the split had these two the other way round.",
        "",
        "## Datasets the 220-account sources hold for no account",
        "",
        (", ".join(sorted(nobody_has)) or "none")
        + " (a benchmark-seed fill does not count; see _CORRECTIONS.txt)",
        "",
        "## Reading an account folder",
        "",
        "- `<dataset_key>.csv` - upload these (only the ones with rows; see _MISSING.txt).",
        "- `compliance_filings/` - drop PDFs here; `_filings_index.csv` says which exist.",
        "- `reference/` - extra tables we hold; not uploaded.",
        "- `_account.json` - identity from the client master list; `name_for_upload`",
        "  is the Sales Territory Name, unique across the 220.",
        "- `_manifest.json` - every table, its source, row count and why it is empty.",
        "- `_READINESS.txt` - per feature, which inputs are present and missing.",
        "",
        "Root: `_ACCOUNTS.csv` (one row per account, with `complete_on_available_data`),",
        "`_READINESS.csv` (account x feature), `_RUN_SUMMARY.json`, `_CORRECTIONS.txt`.",
    ]
    (OUTPUT_DIR / "_DATASET_USAGE.md").write_text("\n".join(md) + "\n")


# --------------------------------------------------------------------------
# Reporting
# --------------------------------------------------------------------------

def print_upload_plan(manifest: dict):
    slug = manifest["account_slug"]
    name = (manifest.get("account") or {}).get("name_for_upload") or manifest["account_name"]
    print(f"\nUpload plan for {manifest['account_name']} ({slug})")
    print("  1. Create the account, then use the returned id below.")
    if name != manifest["account_name"]:
        print(f"     (named by the client's Sales Territory Name, which is unique across")
        print(f"      the 220; the vendor name '{manifest['account_name']}' is not)\n")
    else:
        print()
    print('     curl -X POST "$BASE/api/v1/accounts" -H "Authorization: Bearer $HP_TOKEN" \\')
    print(f"          -H 'Content-Type: application/json' \\")
    print(f"          -d '{{\"name\": \"{name}\"}}'\n")
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
    shared_domain_extra_rows = {}
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
        unclaimed = int((~reached).sum())
        if spec.get("source") == PREDICTLEADS and "__entities" in frame.columns:
            # On a shared domain a row reaches as many accounts as it names:
            # a dual-entity row is written twice, and a row naming neither
            # holder is written nowhere. Both are counted so the validator's
            # reconciliation still balances.
            extra, unassigned = _shared_domain_fanout(frame, accounts)
            if extra:
                shared_domain_extra_rows[dataset_key] = extra
            unclaimed += unassigned
        unclaimed_rows[dataset_key] = unclaimed

    reference_rows = {}
    for key, spec in REFERENCE_PLAN.items():
        if spec["source"] == PREDICTLEADS:
            df = sources.predictleads_sheet(spec["sheet"], spec.get("key", "company_domain"))
            if df is not None:
                reference_rows[key] = len(df)

    summary = {
        "generated_at": datetime.now(UTC).isoformat(),
        "accounts": len(manifests),
        "source_rows": source_rows,
        "unclaimed_rows": unclaimed_rows,
        "news_dedup_dropped": getattr(sources, "_dedup_dropped", 0),
        "news_window": RUN_STATS.get("news_window", {}),
        # Rows written to more than one account because they name both
        # entities of a shared domain (DUAL_ENTITY_ROWS_TO_BOTH).
        "shared_domain_extra_rows": shared_domain_extra_rows,
        "entity_split_domains": sorted(SHARED_DOMAIN_PRIMARY),
        "corrections": CORRECTIONS,
        "domain_aliases": DOMAIN_ALIASES,
        "account_domains": {m["account_slug"]: m["domain"] for m in manifests},
        "master_list": RUN_STATS.get("master_list", {}),
        "domain_audit": RUN_STATS.get("domain_audit", {}),
        "filings_index": RUN_STATS.get("filings_index", {}),
        "apollo_contacts": RUN_STATS.get("apollo_contacts", {}),
        "reference_source_rows": reference_rows,
        "datasets_nobody_has": manifests[0].get("datasets_nobody_has", []) if manifests else [],
        # Slot assignments that changed from an earlier version of this plan,
        # so a reader comparing two runs is not left guessing.
        "mapping_notes": [
            "news_events <- predictleads/news_events (the columns the extractor "
            "reads); news_events_additional <- explorium/13_News_Events (read by "
            "no feature). Earlier runs had these two swapped.",
        ],
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

        # Reference tables and the filings index are held to the same
        # standard: a row count the file does not have is a wrong answer to
        # "what do we hold for this account", even if nothing uploads it.
        extras = [(f"{REFERENCE_DIR}/{key}.csv", info.get("rows", 0))
                  for key, info in manifest.get("reference", {}).items()]
        filings = manifest.get("filings_index", {})
        if filings.get("file"):
            extras.append((filings["file"], filings.get("rows", 0)))
        for rel, expected in extras:
            if not expected:
                continue
            path = out_dir / rel
            if not path.exists():
                print(f"  MISSING FILE  {manifest['account_slug']}/{rel}")
                problems += 1
                continue
            try:
                frame = pd.read_csv(path, encoding=ENCODING, low_memory=False)
            except Exception as exc:
                print(f"  UNREADABLE    {manifest['account_slug']}/{rel}: {exc}")
                problems += 1
                continue
            if len(frame) != expected:
                print(f"  ROW MISMATCH  {manifest['account_slug']}/{rel}: "
                      f"manifest says {expected}, file has {len(frame)}")
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
    print(f"{'dataset':<34} {'accounts with rows':>18}  {'total rows':>12}")
    print("-" * 68)
    for key in keys:
        have = sum(1 for m in manifests if m["datasets"].get(key, {}).get("rows", 0) > 0)
        total = sum(m["datasets"].get(key, {}).get("rows", 0) for m in manifests)
        flag = "" if have else "   <- no data anywhere"
        print(f"{key:<34} {have:>18}  {total:>12,}{flag}")

    print(f"\nReference tables (no dataset_key; not uploaded)\n")
    print(f"{'table':<34} {'accounts with rows':>18}  {'total rows':>12}")
    print("-" * 68)
    for key in REFERENCE_PLAN:
        have = sum(1 for m in manifests if m.get("reference", {}).get(key, {}).get("rows", 0) > 0)
        total = sum(m.get("reference", {}).get(key, {}).get("rows", 0) for m in manifests)
        flag = "" if have else "   <- no data anywhere"
        print(f"{key:<34} {have:>18}  {total:>12,}{flag}")

    have = sum(1 for m in manifests if m.get("filings_index", {}).get("rows", 0) > 0)
    total = sum(m.get("filings_index", {}).get("rows", 0) for m in manifests)
    print(f"\n{'filings index (documents)':<34} {have:>18}  {total:>12,}")

    if manifests and manifests[0].get("readiness"):
        features = list(manifests[0]["readiness"])
        print(f"\nFeature readiness across {len(manifests)} accounts\n")
        print(f"{'feature':<36} {'complete':>9} {'partial':>9} {'none':>6}  {'complete on available data':>27}")
        print("-" * 92)
        for feature in features:
            statuses = [m["readiness"][feature]["status"] for m in manifests]
            on_avail = sum(1 for m in manifests
                           if m["readiness"][feature]["complete_on_available_data"])
            print(f"{feature:<36} {statuses.count('complete'):>9} "
                  f"{statuses.count('partial'):>9} {statuses.count('none'):>6}  {on_avail:>27}")


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
    # A missing workbook would otherwise read as "no rows" for every account.
    missing = [p.name for p in REQUIRED_SOURCE_FILES if not p.exists()]
    if missing:
        sys.exit(f"source file(s) not found in {SOURCE_DIR}: {', '.join(missing)}")

    for warning in check_registry_drift():
        print(f"WARNING: {warning}")

    print(f"Reading sources from {SOURCE_DIR}")
    sources = SourceData(match_legacy=args.match_legacy)
    sources.google_news()
    nw = RUN_STATS["news_window"]
    print(f"News window: {nw['from']} to {nw['to']} ({nw['days']} days)")
    for label, f in nw["feeds"].items():
        print(f"  {label}: {f['kept']:,} of {f['rows']:,} kept - {f['older']:,} older, "
              f"{f['future']:,} future-dated, {f['undated']:,} undated")

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

    full_run = not args.account and not args.limit

    RUN_STATS["master_list"] = attach_master_list(accounts, sources)
    ms = RUN_STATS["master_list"]
    print(f"Master list: {ms['matched']} of {ms['master_rows']} territories matched "
          f"to an account folder")
    if full_run and ms["unmatched_territories"]:
        print(f"  ! unmatched territories: {', '.join(ms['unmatched_territories'][:8])}")
    if ms["accounts_without_master_row"]:
        print(f"  ! accounts with no master-list row: "
              f"{', '.join(ms['accounts_without_master_row'][:8])}")

    # Before the alias and shared-domain checks below: the audit can change
    # an account's domain, and those checks must see the final one.
    RUN_STATS["domain_audit"] = attach_domain_audit(accounts, sources)
    da = RUN_STATS["domain_audit"]
    print(f"Domain audit: {da['matched']} of {da['audit_rows']} rows matched "
          f"to an account")
    if da["accounts_without_audit_row"]:
        print(f"  accounts with no audit row: "
              f"{', '.join(da['accounts_without_audit_row'][:8])}")
    if full_run and da["unmatched_audit_rows"]:
        print(f"  ! unmatched audit rows: {', '.join(da['unmatched_audit_rows'][:8])}")
    for line in da["domain_overrides"]:
        print(f"  ! domain overridden by audit, add an alias for the old one: {line}")

    # Aliases are applied inside normalize_domain, which runs per row across
    # every source; recording them there would produce tens of thousands of
    # identical lines. One line per alias that actually matched an account is
    # the useful form.
    account_domains = {a.domain for a in accounts if a.domain}
    for source_domain, account_domain in DOMAIN_ALIASES.items():
        if account_domain in account_domains:
            record_correction(
                account_domain, "source domain", source_domain, account_domain,
                "explicit approved alias: a source workbook keys this account "
                "under a different domain than the client domain audit")

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
                    slug, "news and intent datasets", f"rows for {shared_domain}",
                    "none",
                    f"{shared_domain} is shared with {primary}, which keeps the "
                    f"rows; no field in those sources splits them by entity")
            record_correction(
                slug, "predictleads datasets", f"rows for {shared_domain}",
                "rows naming this account's territory"
                + (" (incl. rows naming both entities)" if DUAL_ENTITY_ROWS_TO_BOTH else ""),
                f"company_name on every PredictLeads row since 25 Sep (C48, D3); "
                f"dual-entity rows go to {'both' if DUAL_ENTITY_ROWS_TO_BOTH else 'neither'}")

    RUN_STATS["filings_index"] = assign_filings(accounts, sources)
    fs = RUN_STATS["filings_index"]
    print(f"Filings index: {fs['rows']} rows - {fs['by_client_ruling']} by client ruling, "
          f"{fs['by_territory']} by territory, "
          f"{fs['by_domain']} by domain, {fs['by_company_name']} by company name, "
          f"{fs['unassigned']} unassigned")

    RUN_STATS["apollo_contacts"] = assign_apollo_contacts(accounts, sources)
    ac = RUN_STATS["apollo_contacts"]
    print(f"Apollo contacts: {ac['rows']} rows -> {ac['accounts_with_contacts']} accounts "
          f"({ac['by_territory']} by territory, {ac['by_name_and_country']} by name + "
          f"country, {ac['by_domain']} by domain), {len(ac['unassigned'])} unassigned, "
          f"{ac['emails_withheld']} emails withheld; flags {ac['flags']}")

    deps = load_feature_dependencies()
    print(f"Feature dependencies: {len(deps)} features read from feature_mapping.py")

    if not args.dry_run:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    manifests = []
    for index, account in enumerate(accounts, 1):
        marker = "[dry-run] " if args.dry_run else ""
        manifest = process_account(account, sources, args.dry_run)
        manifests.append(manifest)
        filled = sum(1 for v in manifest["datasets"].values() if v["rows"] > 0)
        total = len(manifest["datasets"])
        ref_filled = sum(1 for v in manifest["reference"].values() if v["rows"] > 0)
        filings = manifest["filings_index"]["rows"]
        print(f"  {marker}[{index}/{len(accounts)}] {account.slug:<44} "
              f"{filled}/{total} datasets, {ref_filled} reference tables, "
              f"{filings} filings")

    nobody_has: set[str] = set()
    if not args.dry_run:
        nobody_has = write_readiness(manifests, deps)
        if full_run:
            write_root_indexes(manifests, deps, nobody_has)
        else:
            print("  (root indexes _ACCOUNTS.csv / _READINESS.csv / _DATASET_USAGE.md "
                  "are written only on a full run)")

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
        print("Each holds _manifest.json (what came from where), _MISSING.txt (what is "
              "still empty),\n_READINESS.txt (which features it can feed) and "
              "_account.json (client identity).")
        if full_run:
            print("Root: _ACCOUNTS.csv, _READINESS.csv, _DATASET_USAGE.md, "
                  "_unassigned_filings.csv")

    if not args.dry_run:
        write_run_summary(manifests, sources, accounts)

    if args.verify and not args.dry_run:
        if verify_output(manifests):
            sys.exit(1)


if __name__ == "__main__":
    main()
