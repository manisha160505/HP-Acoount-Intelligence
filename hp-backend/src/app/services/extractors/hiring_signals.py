"""Hiring Signals: what an account is hiring for, and what HP can offer for it.

A section at the bottom of Intent & Demand Signals, not a feature of its own
(client, 1 Oct); its widgets carry that feature's key.

Source: Hiring_Signals_Rule_Set_Final.docx and the worked example "Hiring
Signals - Australia Post (desktop)" (Dhruvi, 1 Oct 2026). Entirely
deterministic - no model call. The jobs are the shared selection in
`hp/hiring_jobs.py` (country check, last 12 months to the pull date, open and
closed), the same jobs every other feature reads.

This is the one hiring output. The Executive Dashboard's job postings tile,
Strategy Chat and the Strategic Priorities evidence all read these widgets;
nothing else computes a hiring number.

Four widgets, one per block of the section:

  hiring_postings_summary  tile 1 (job postings), tile 2 (hybrid roles) and up
                           to 5 sample roles (the Executive Dashboard tile)
  hiring_family_breakdown  "What they're hiring for": O*NET families, top 6 + Other
  hiring_tech_tags         "Tech named in job ads": up to 30 tags from column W
  hiring_theme_cards       "Hiring signals for HP": one card per theme with jobs

When no job survives the selection every widget is "empty" and the page hides
the section. It never says "no data".

Ties keep PredictLeads file order (client, 1 Oct); the Australia Post example
was produced the same way.
"""

import json
import logging
import re
from collections import Counter
from datetime import UTC, datetime

from app.database.mongodb import get_db
from app.observability import pipeline
from app.services.extractors.datasets import (
    account_display_name,
    account_domain,
    requires_local_datasets,
)
from app.services.hp import hiring_jobs, hiring_themes
from app.services.regen import store as widget_store

logger = logging.getLogger(__name__)

FEATURE_KEY = "intent_demand_signals"

FAMILY_BARS = 6
TECH_TAG_LIMIT = 30
CARD_TITLES = 5

# Column F values that make a job hybrid (rule set, section 2).
HYBRID_TERMS = ("hybrid", "remote", "work from home")

# Column W tags that are not technology (rule set, section 4). The company's
# own name is removed as well - see _own_name_keys.
NON_TECH_TAGS = frozenset({"internship", "contractor", "business development",
                           "customer success", "marketing campaigns",
                           "advertising", "social media"})


def _json_list(value) -> list:
    raw = str(value or "").strip()
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
    except ValueError:
        return [raw]
    if isinstance(parsed, list):
        return [str(v).strip() for v in parsed if str(v or "").strip()]
    return [str(parsed).strip()] if str(parsed or "").strip() else []


def _onet(row) -> dict:
    raw = row.get("onet_data")
    if isinstance(raw, dict):
        return raw
    try:
        parsed = json.loads(str(raw or ""))
    except ValueError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _is_hybrid(row) -> bool:
    terms = [t.lower() for t in _json_list(row.get("contract_types"))]
    return any(any(h in t for h in HYBRID_TERMS) for t in terms)


def _key(text) -> str:
    return re.sub(r"[^a-z0-9]", "", str(text or "").lower())


def _own_name_keys(account_name: str, domain: str) -> set:
    """The company's own name, as a tag would spell it.

    The account name without its " - XX" suffix, and the domain's first label
    ("auspost" for auspost.com.au) - PredictLeads tags employers either way.
    """
    name = re.sub(r"\s-\s[A-Z]{2}\s*$", "", str(account_name or "").strip())
    keys = {_key(name)}
    host = str(domain or "").lower().strip()
    host = re.sub(r"^https?://", "", host).split("/")[0]
    if host.startswith("www."):
        host = host[4:]
    if host:
        keys.add(_key(host.split(".")[0]))
    return {k for k in keys if k}


def _is_own_name(tag: str, own: set) -> bool:
    k = _key(tag)
    if not k:
        return False
    if k in own:
        return True
    # "Toyota" for TOYOTA GROUP: a tag that is the start of the name.
    return len(k) >= 5 and any(o.startswith(k) for o in own)


def _first_seen_range(jobs: list) -> tuple:
    firsts = sorted(str(j.get("first_seen_at") or "")[:10] for j in jobs
                    if str(j.get("first_seen_at") or "").strip())
    lasts = sorted(str(j.get("last_seen_at") or "")[:10] for j in jobs
                   if str(j.get("last_seen_at") or "").strip())
    return (firsts[0] if firsts else None, lasts[-1] if lasts else None)


SAMPLE_ROLES = 5


def sample_roles(jobs: list) -> list:
    """The first distinct job titles, in file order."""
    roles = []
    for j in jobs:
        title = str(j.get("title") or j.get("normalized_title") or "").strip()
        if title and title not in roles:
            roles.append(title)
            if len(roles) == SAMPLE_ROLES:
                break
    return roles


def postings_summary(jobs: list) -> dict:
    total = len(jobs)
    hybrid = sum(1 for j in jobs if _is_hybrid(j))
    seen_from, seen_to = _first_seen_range(jobs)
    return {
        "job_postings": total,
        "window_label": "Last 12 months",
        "seen_from": seen_from,
        "seen_to": seen_to,
        "hybrid_count": hybrid,
        "hybrid_pct": round(100 * hybrid / total) if total else 0,
        "hybrid_rule": "column F contains hybrid, remote or work from home",
        "sample_roles": sample_roles(jobs),
    }


def family_breakdown(jobs: list) -> dict:
    """The six largest O*NET families; everything else, including jobs with no
    family, is "Other" so the bars add up to the job postings tile."""
    counts = Counter()
    for j in jobs:
        counts[str(_onet(j).get("family") or "").strip() or None] += 1
    named = [(f, n) for f, n in counts.most_common() if f]
    bars = [{"family": f, "count": n} for f, n in named[:FAMILY_BARS]]
    other = sum(n for _, n in named[FAMILY_BARS:]) + counts.get(None, 0)
    if other:
        bars.append({"family": "Other", "count": other})
    return {"bars": bars, "total": len(jobs),
            "unclassified": counts.get(None, 0)}


def tech_tags(jobs: list, own: set) -> dict:
    """How many jobs mention each tag, most mentioned first, at most 30."""
    counts = Counter()
    for j in jobs:
        seen = []
        for tag in _json_list(j.get("tags")):
            if tag not in seen:
                seen.append(tag)
        for tag in seen:
            counts[tag] += 1
    removed = []
    tags = []
    for tag, n in counts.most_common():
        if tag.lower() in NON_TECH_TAGS or _is_own_name(tag, own):
            removed.append(tag)
            continue
        tags.append({"tag": tag, "jobs": n})
    return {"tags": tags[:TECH_TAG_LIMIT], "removed": removed}


def theme_cards(jobs: list) -> dict:
    """One card per theme with at least one job, largest first; ties keep the
    rule set's theme order."""
    grouped = {}
    unthemed = 0
    for j in jobs:
        theme = hiring_themes.theme_for(_onet(j).get("code"))
        if theme is None:
            unthemed += 1
            continue
        grouped.setdefault(theme.key, (theme, []))[1].append(j)

    cards = []
    for theme, members in grouped.values():
        titles = Counter(str(j.get("title") or j.get("normalized_title") or "").strip()
                         for j in members)
        titles.pop("", None)
        ranked = [{"title": t, "posted": n} for t, n in titles.most_common()]
        shown = ranked[:CARD_TITLES]
        cards.append({
            "theme_key": theme.key,
            "theme": theme.name,
            "job_count": len(members),
            "titles": shown,
            "more_jobs": len(members) - sum(s["posted"] for s in shown),
            # Behind the card's "+ N more jobs" dropdown (refinements, 6 Oct).
            # Jobs with no title are counted in more_jobs but have nothing to list.
            "more_titles": ranked[CARD_TITLES:],
            "hp_product": theme.product,
            "hp_service": theme.service,
            "hp_solution": theme.solution,
        })
    cards.sort(key=lambda c: (-c["job_count"], hiring_themes.THEME_ORDER[c["theme_key"]]))
    return {"cards": cards, "unthemed_jobs": unthemed}


def _payload(account_id, widget_key, data, now, basis) -> dict:
    available = bool(data)
    return {
        "account_id": account_id,
        "feature_key": FEATURE_KEY,
        "widget_key": widget_key,
        "data_classification": "deterministic",
        "status": "available" if available else "empty",
        "data": {**data, "basis": basis} if available else {},
        "source_datasets": ["job_openings"],
        "extracted_at": now,
        "updated_at": now,
    }


@requires_local_datasets("job_openings")
@pipeline.feature("hiring_signals")
def extract_hiring_signals(account_id: str) -> list[dict]:
    db = get_db()
    now = datetime.now(UTC)

    name = account_display_name(account_id)
    selected = hiring_jobs.account_jobs(account_id)
    jobs = selected.jobs
    pipeline.step("selection", "", rows=len(jobs) + len(selected.excluded),
                  jobs=len(jobs),
                  dropped_other_country=selected.dropped_other_country,
                  dropped_older=selected.dropped_older,
                  dropped_undated=selected.dropped_undated)

    basis = {**selected.basis(), "themes_version": hiring_themes.THEMES_VERSION}
    # Column C is the PredictLeads domain the jobs were collected under.
    domain = next((str(j.get("company_domain") or "").strip().lower()
                   for j in jobs if str(j.get("company_domain") or "").strip()),
                  "") or account_domain(account_id)
    summary = families = tags = cards = {}
    if jobs:
        summary = {**postings_summary(jobs), "company": name, "domain": domain,
                   "country_code": selected.country_code or None}
        families = family_breakdown(jobs)
        tags = tech_tags(jobs, _own_name_keys(name, domain))
        cards = theme_cards(jobs)
        if not tags["tags"]:
            tags = {}
        if not cards["cards"]:
            cards = {}

    results = []
    for widget_key, data in (("hiring_postings_summary", summary),
                             ("hiring_family_breakdown", families),
                             ("hiring_tech_tags", tags),
                             ("hiring_theme_cards", cards)):
        payload = _payload(account_id, widget_key, data, now, basis)
        widget_store.put(account_id, widget_key, payload, db=db)
        results.append(payload)
    return results
