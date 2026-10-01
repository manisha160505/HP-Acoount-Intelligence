"""The nine HP hiring themes and the O*NET codes that land in each.

Source: Hiring_Signals_Rule_Set_Final.docx, "Theme rules" (Dhruvi, 1 Oct 2026).
Each job carries an O*NET code in column P (onet_data.code), added by
PredictLeads; we never assign one. The table is read top down and the first
row that matches is the job's theme, so the order below is the rule: the exact
codes of Security, IT operations and Leadership must win over the broad
"all other 15-" / "all other 11-" rows further down.

The table covers all 703 codes in the 1 Oct file. A job with no code gets no
theme and appears on no card.
"""

from dataclasses import dataclass

# Bump on any change to the table or to how a code is matched.
THEMES_VERSION = 1


@dataclass(frozen=True)
class Theme:
    key: str
    name: str
    codes: frozenset = frozenset()      # exact codes, e.g. "15-1212.00"
    prefixes: tuple = ()                # "25-" (major group) or "41-3" (minor group)
    product: str = ""
    service: str = ""
    solution: str = ""


THEMES = (
    Theme("security", "Security",
          codes=frozenset({"15-1212.00", "15-1299.04", "15-1299.05", "15-1299.06"}),
          product="HP EliteBook 8 G2 Series (built-in Wolf Security, Sure Start / Sure Admin)",
          service="Sure Click Enterprise professional services",
          solution="Sure Click Enterprise; Wolf Security Controller; Sure Access Enterprise"),
    Theme("it_operations", "IT operations",
          codes=frozenset({"11-3021.00", "15-1231.00", "15-1232.00", "15-1241.00",
                           "15-1244.00", "15-1299.01"}),
          product="HP EliteBook 8 G2 Series",
          service="HP Imaging Service; HP Device Registration Service; Priority Access",
          solution="HP Workforce Experience Platform (WXP)"),
    Theme("leadership", "Leadership",
          codes=frozenset({"11-1011.00", "11-1011.03", "11-1031.00"}),
          product="HP EliteBook Ultra G1i",
          service="Travel Support",
          solution="Protect and Trace with Wolf Connect"),
    Theme("education", "Education",
          prefixes=("25-",),
          product="HP 200 G2 Series",
          service="Accidental Damage Protection",
          solution="WXP"),
    # Name as shown on the worked example (client answer, 1 Oct).
    Theme("technical", "Technical, engineering & design experts",
          prefixes=("15-", "17-", "19-", "27-"),
          product="HP EliteDesk 8 Tower G1i Desktop AI PC; HP EliteBook 8 G2 Series (AI PC)",
          service="HP Advanced Imaging Service; Onsite / Next Business Day support",
          solution="HP Workforce Experience Platform (WXP)"),
    Theme("mobile_sales", "Mobile & field sales",
          prefixes=("41-3", "41-4", "41-9"),
          product="HP EliteBook 8 G2 Series",
          service="Travel Support; Accidental Damage Protection; Computer Tracing",
          solution="Protect and Trace with Wolf Connect"),
    Theme("frontline", "Frontline & operations",
          prefixes=("29-", "31-", "33-", "35-", "37-", "39-", "45-", "47-", "49-",
                    "51-", "53-", "55-", "41-1", "41-2"),
          product="HP EliteStudio 8 AiO G1i / HP ProStudio 4 AiO G1i",
          service="Accidental Damage Protection",
          solution="HP Workforce Experience Platform (WXP)"),
    Theme("office_support", "Office support & customer service",
          prefixes=("43-", "23-2"),
          product="HP EliteDesk 8 Mini G1i / HP ProDesk 4 Mini G1i",
          service="Onsite / Next Business Day support",
          solution="HP Secure Print Enterprise Package Cloud; HP Access Control Scan"),
    Theme("knowledge_workers", "Office knowledge workers",
          prefixes=("11-", "13-", "21-", "23-1"),
          product="HP EliteBook 6 G2 Series",
          service="HP Imaging Service",
          solution="WXP and WXP Collaboration"),
)

THEME_ORDER = {t.key: i for i, t in enumerate(THEMES)}


def theme_for(code: str) -> Theme | None:
    """The first row of the table that matches, or None for a blank code."""
    code = str(code or "").strip()
    if not code:
        return None
    for theme in THEMES:
        if code in theme.codes or any(code.startswith(p) for p in theme.prefixes):
            return theme
    return None
