"""Which PredictLeads job openings count for an account.

One selection, shared by every place that shows a hiring number, so the
Executive Dashboard tile and the Hiring Signals page can never disagree.
Source: Hiring_Signals_Rule_Set_Final.docx (Dhruvi, 1 Oct 2026) plus the
answers given to the open questions on it the same day:

  1. Country check. Column E (account_country_code) is converted to a country
     name and a job is dropped when column M (location) names a different
     country. A blank location is kept. A location that names no country at
     all ("Columbus, OH", "Europe") is treated as the account's own country
     and kept - client answer, 1 Oct.
  2. Two-code rows ("MY; SG", "JP; TH") belong to both accounts; the country
     check above is what sends each job to one of them.
  3. Last 12 months on column H (first_seen_at), counted back from the
     PredictLeads pull date, not from today - client answer, 1 Oct. A job with
     no first_seen_at cannot be shown to be inside the window and is dropped.
  4. Open and closed postings both count.

Location is used for the check only and is never shown.
"""

import re
from dataclasses import dataclass, field
from datetime import date, datetime

# Bump on any change to the selection below. The Executive Dashboard's regen
# node references it, so a bump marks every account's hiring tile stale.
HIRING_RULES_VERSION = 1

# The date the PredictLeads job openings file was pulled. The 12-month window
# ends here. Update it (and HIRING_RULES_VERSION) when a new pull is loaded.
PREDICTLEADS_PULL_DATE = date(2026, 9, 18)
WINDOW_MONTHS = 12

# Rule set table: the code in column E and the names to look for in column M.
ACCOUNT_COUNTRY_NAMES = {
    "AU": ("Australia",),
    "NZ": ("New Zealand",),
    "SG": ("Singapore",),
    "MY": ("Malaysia",),
    "TH": ("Thailand",),
    "ID": ("Indonesia",),
    "PH": ("Philippines",),
    "VN": ("Vietnam", "Viet Nam"),
    "JP": ("Japan",),
    "KR": ("South Korea", "Korea"),
}

# Every other country (and the territories PredictLeads writes like one), so a
# location naming one of them is recognised as foreign. Matched longest first
# on word boundaries, so "Papua New Guinea" is not read as "Guinea" and "North
# Korea" is not read as "Korea".
_OTHER_COUNTRY_NAMES = (
    "Afghanistan", "Albania", "Algeria", "Andorra", "Angola", "Argentina",
    "Armenia", "Austria", "Azerbaijan", "Bahamas", "Bahrain", "Bangladesh",
    "Barbados", "Belarus", "Belgium", "Belize", "Benin", "Bhutan", "Bolivia",
    "Bosnia and Herzegovina", "Botswana", "Brazil", "Brunei", "Bulgaria",
    "Burkina Faso", "Burundi", "Cambodia", "Cameroon", "Canada", "Chad",
    "Chile", "China", "Colombia", "Congo", "Costa Rica", "Croatia", "Cuba",
    "Cyprus", "Czechia", "Czech Republic", "Denmark", "Djibouti",
    "Dominican Republic", "Ecuador", "Egypt", "El Salvador", "Estonia",
    "Eswatini", "Ethiopia", "Fiji", "Finland", "France", "Gabon", "Gambia",
    "Georgia", "Germany", "Ghana", "Greece", "Guatemala", "Guinea", "Guyana",
    "Haiti", "Honduras", "Hong Kong", "Hungary", "Iceland", "India", "Iran",
    "Iraq", "Ireland", "Israel", "Italy", "Ivory Coast", "Jamaica", "Jordan",
    "Kazakhstan", "Kenya", "Kuwait", "Kyrgyzstan", "Laos", "Latvia", "Lebanon",
    "Liberia", "Libya", "Liechtenstein", "Lithuania", "Luxembourg", "Macao",
    "Macau", "Madagascar", "Malawi", "Maldives", "Mali", "Malta", "Mauritius",
    "Mexico", "Moldova", "Monaco", "Mongolia", "Montenegro", "Morocco",
    "Mozambique", "Myanmar", "Namibia", "Nepal", "Netherlands", "Nicaragua",
    "Niger", "Nigeria", "North Korea", "North Macedonia", "Norway", "Oman",
    "Pakistan", "Panama", "Papua New Guinea", "Paraguay", "Peru", "Poland",
    "Portugal", "Puerto Rico", "Qatar", "Romania", "Russia", "Rwanda",
    "Saudi Arabia", "Senegal", "Serbia", "Sierra Leone", "Slovakia",
    "Slovenia", "Somalia", "South Africa", "Spain", "Sri Lanka", "Sudan",
    "Sweden", "Switzerland", "Syria", "Taiwan", "Tajikistan", "Tanzania",
    "Timor-Leste", "Togo", "Trinidad and Tobago", "Tunisia", "Turkey",
    "Türkiye", "Turkmenistan", "Uganda", "Ukraine", "United Arab Emirates",
    "United Kingdom", "United States", "USA", "Uruguay", "Uzbekistan",
    "Venezuela", "Yemen", "Zambia", "Zimbabwe",
)

_NAME_TO_CODE = {name.lower(): code
                 for code, names in ACCOUNT_COUNTRY_NAMES.items()
                 for name in names}
_ALL_NAMES = sorted({*_NAME_TO_CODE, *(n.lower() for n in _OTHER_COUNTRY_NAMES)},
                    key=len, reverse=True)
_COUNTRY_RE = re.compile(
    r"(?<![\w-])(" + "|".join(re.escape(n) for n in _ALL_NAMES) + r")(?![\w-])",
    re.IGNORECASE)
_NAME_SUFFIX_RE = re.compile(r"\s-\s([A-Z]{2})\s*$")


@dataclass
class HiringJobs:
    """The selected jobs, and what each rule removed (for the payload)."""
    jobs: list
    country_code: str
    window_start: date
    window_end: date
    dropped_other_country: int = 0
    dropped_older: int = 0
    dropped_undated: int = 0
    notes: list = field(default_factory=list)

    def basis(self) -> dict:
        return {
            "rules": "Hiring_Signals_Rule_Set_Final.docx",
            "rules_version": HIRING_RULES_VERSION,
            "account_country_code": self.country_code or None,
            "window_start": self.window_start.isoformat(),
            "window_end": self.window_end.isoformat(),
            "dropped_other_country": self.dropped_other_country,
            "dropped_older_than_window": self.dropped_older,
            "dropped_no_first_seen": self.dropped_undated,
        }


def _split(value) -> list:
    return [p.strip() for p in str(value or "").split(";") if p.strip()]


def account_country_code(account_name: str, rows: list) -> str:
    """The account's own code from column E.

    Two-code rows carry both companies in column D ("JABIL CIRCUIT SDN BHD - MY;
    JABIL CIRCUIT (SINGAPORE) PTE LTD - SG") in the same order as column E, and
    the account record's name is that same Sales Territory Name, so the name
    picks the code. Then the name's own " - XX" suffix, then the single code the
    account's rows carry.
    """
    name = " ".join(str(account_name or "").split()).upper()
    single = {}
    for row in rows:
        names, codes = _split(row.get("company_name")), _split(
            row.get("account_country_code"))
        if name and len(names) == len(codes):
            for n, c in zip(names, codes):
                if " ".join(n.split()).upper() == name and c in ACCOUNT_COUNTRY_NAMES:
                    return c
        if len(codes) == 1 and codes[0] in ACCOUNT_COUNTRY_NAMES:
            single[codes[0]] = single.get(codes[0], 0) + 1
    m = _NAME_SUFFIX_RE.search(name)
    if m and m.group(1) in ACCOUNT_COUNTRY_NAMES:
        return m.group(1)
    if single:
        return max(single, key=single.get)
    return ""


def location_in_country(location, country_code: str) -> bool:
    """False only when the location names a country and none is the account's."""
    text = str(location or "").strip()
    if not text:
        return True
    found = {m.group(1).lower() for m in _COUNTRY_RE.finditer(text)}
    if not found:
        return True
    return any(_NAME_TO_CODE.get(n) == country_code for n in found)


def _first_seen(row) -> date | None:
    raw = str(row.get("first_seen_at") or "").strip()
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).date()
    except ValueError:
        try:
            return date.fromisoformat(raw[:10])
        except ValueError:
            return None


def window_start(end: date = PREDICTLEADS_PULL_DATE,
                 months: int = WINDOW_MONTHS) -> date:
    y, m = divmod(end.month - 1 - months, 12)
    year, month = end.year + y, m + 1
    for day in (end.day, 30, 29, 28):
        try:
            return date(year, month, day)
        except ValueError:
            continue
    raise ValueError(end)


def select_jobs(account_name: str, rows: list) -> HiringJobs:
    """Apply the country check, then the 12-month window, keeping file order."""
    rows = [r for r in (rows or []) if isinstance(r, dict)]
    code = account_country_code(account_name, rows)
    start = window_start()
    out = HiringJobs(jobs=[], country_code=code, window_start=start,
                     window_end=PREDICTLEADS_PULL_DATE)
    if not code:
        out.notes.append("account country code not found in job_openings; "
                         "country check not applied")
    for row in rows:
        if code and not location_in_country(row.get("location"), code):
            out.dropped_other_country += 1
            continue
        seen = _first_seen(row)
        if seen is None:
            out.dropped_undated += 1
            continue
        if seen < start:
            out.dropped_older += 1
            continue
        out.jobs.append(row)
    return out
