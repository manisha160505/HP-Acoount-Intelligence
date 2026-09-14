"""Intent & Demand Signals.

The intent flow, in four steps:

  1. hp_category_intent (the HP category intent export) gives each HP category -
     PCs, Workstations, Poly, Printers, 3D Printers - its primary score, shown
     as received on the graph and cards ("Workstation: 35/100").
  2. Explorium 11_intent_score (Bombora Company Surge, Source A) gives the
     supporting intent signals for each category, each with its exact score.
  3. Explorium sheets 4 and 5 (technographics, webstack) show which of those
     signals are backed by technology actually in use at the account.
  4. Each confirming technology is shown against its signal, and the signal
     keeps its exact 11_intent_score score.

Supporting signals never change a category's score. A category whose file score
rests on a known noisy keyword keeps its score on screen but is never picked as
the account's primary HP category. Bombora topics are also mapped to themes by
the dictionary in services/hp/intent_topic_map.py for the raw topic view and
theme summaries. Sheet 6 (workforce trends) holds role shares, not
technologies, so it takes no part in step 3.

Source B is job_openings, used for the hiring-linked demand card together with
the Bombora topics that relate to staffing.

Three widgets, all computed here in Python - nothing is generated:

  intent_topics_table     every Bombora topic as received, with the
                          dictionary's theme and HP category beside it
  intent_category_summary category scores from the category file, their
                          supporting signals and technologies, and theme
                          summaries from exactly the included topics
  intent_hiring_demand    postings seen, open postings and seniority mix

Intent is reported as research activity only. It can strengthen an opportunity
other account evidence already supports; on its own it recommends nothing.
"""

import json
import math
import re
from collections import Counter
from datetime import datetime, timezone

from bson import ObjectId

from app.database.mongodb import get_db
from app.services.extractors.datasets import (
    account_domain,
    find_file_path, read_dataset_records, read_dataset_rows,
    requires_local_datasets,
)
from app.services.hp import intent_topic_map as tm


def _find_file_path(rel_path: str) -> str | None:
    """Shared implementation - see datasets.py."""
    return find_file_path(rel_path)


def _read_dataset_records(account_id: str, dataset_key: str) -> list[dict]:
    """Rows for one dataset. Shared implementation - see datasets.py.

    Non-strict: requires_local_datasets on the entry point below has already
    established that this account's files are present, so a miss here means the
    dataset simply is not registered for this account.
    """
    return read_dataset_records(account_id, dataset_key, strict=False)


# The intent_score dataset is the Bombora Company Surge export (seeded as
# "11_Intent_Score (Bombora Composite Surge)"). The file names no provider, so
# it is recorded here once rather than guessed per row.
PROVIDER = {
    "name": "Bombora",
    "product": "Company Surge",
    "source": "Source A",
    "scoring_definition": "Bombora Composite Score (0-100)",
}

DISCLAIMER = ("Intent indicates research activity, not confirmed purchase intent. "
              "It can strengthen an opportunity that other account evidence already "
              "supports; it does not create one on its own.")

# A posting counts as open when job_openings gives it no closing status.
OPEN_STATUSES = {"", "open", "active"}

# How the category file marks an empty cell. "\ufffd" is its em dash read
# through a UTF-8 decoder that replaced it.
EMPTY_MARKERS = {"", "-", "\u2013", "\u2014", "\ufffd", "n/a", "na", "none"}

# Field row of the category file -> key. Scores are the provider's, as received.
CATEGORY_FIELDS = {
    "intent score (/100)": "score",
    "intent trend": "trend",
    "buying stage": "stage",
    "research volume": "research_volume",
    "topics researched": "topics_researched",
    "keywords matched": "keywords_matched",
    "related technologies": "related_technologies",
    "first intent date": "first_intent_date",
    "latest intent date": "latest_intent_date",
    "geo source": "geo",
}
LIST_FIELDS = {"topics_researched", "keywords_matched", "related_technologies", "geo"}


def _clean(value) -> str:
    return " ".join(str(value or "").split())


def _norm_domain(value) -> str:
    """'https://www.Astra.co.id/about' -> 'astra.co.id'."""
    d = _clean(value).lower()
    d = re.sub(r"^[a-z]+://", "", d)
    d = d.split("/")[0].split(":")[0].rstrip(".")
    return d[4:] if d.startswith("www.") else d


def _parse_date_stamp(raw: str) -> str | None:
    """Bombora's Date Stamp is YYYYMMDD. Anything else is kept raw, not guessed."""
    for fmt in ("%Y%m%d", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def _parse_score(raw):
    try:
        value = float(_clean(raw))
    except ValueError:
        return None
    if not math.isfinite(value):
        return None
    return int(value) if value.is_integer() else value


def _iso(value) -> str | None:
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value) if value else None


def _file_refreshed_at(db, account_id: str, dataset_key: str) -> str | None:
    """When this dataset was last loaded into the platform for the account."""
    doc = db["account_data_files"].find_one(
        {"account_id": account_id,
         "$or": [{"dataset_key": dataset_key}, {"category": dataset_key}],
         "status": "active"},
        {"updated_at": 1, "uploaded_at": 1})
    return _iso((doc or {}).get("updated_at") or (doc or {}).get("uploaded_at"))


def _match_provider_account(meta_records: list[dict], account_domain: str) -> tuple[dict, dict]:
    """Validate that the intent export is for this account's domain.

    Returns (account_match, observation). A similarly named company on another
    domain is a mismatch, and its topics are not attached to this account.
    When either side has no domain the match cannot be checked, and says so.
    """
    account_d = _norm_domain(account_domain)
    rows = [r for r in meta_records if _clean(r.get("Company Website"))]
    matching = [r for r in rows if _norm_domain(r.get("Company Website")) == account_d]

    match = {"status": "unverified", "account_domain": account_d or None,
             "provider_domain": None, "provider_company": None, "note": None}
    if not account_d:
        match["note"] = "The account has no domain on file to check the intent export against."
    elif not rows:
        match["note"] = "The intent export supplies no Company Website to check against the account."
    elif not matching:
        match["status"] = "mismatch"
        match["provider_domain"] = _norm_domain(rows[0].get("Company Website"))
        match["provider_company"] = _clean(rows[0].get("Company Name")) or None
        match["note"] = (f"The intent export is for {match['provider_domain']}, not "
                         f"{account_d}. Its topics are not attached to this account.")
    else:
        match["status"] = "matched"
        match["provider_domain"] = account_d
        match["provider_company"] = _clean(matching[0].get("Company Name")) or None

    source_rows = matching or rows or meta_records
    stamps = sorted({_clean(r.get("Date Stamp")) for r in source_rows if _clean(r.get("Date Stamp"))})
    observation = {"date_stamp": None, "as_of": None, "note": None}
    if len(stamps) == 1:
        observation["date_stamp"] = stamps[0]
        observation["as_of"] = _parse_date_stamp(stamps[0])
        observation["note"] = "Bombora Date Stamp. The export does not state the window length."
    elif len(stamps) > 1:
        observation["note"] = (f"The export carries {len(stamps)} Date Stamps ({', '.join(stamps)}) "
                               "and topic rows carry none, so no single window can be shown.")
    else:
        observation["note"] = "The export supplies no Date Stamp."

    first = source_rows[0] if source_rows else {}
    match["level_of_intent"] = _clean(first.get("Level Of Intent")) or None
    match["provider_topic_count"] = _clean(first.get("Topic Count")) or None
    return match, observation


def _build_topics(score_records: list[dict]) -> tuple[list[dict], list[dict]]:
    """Every topic as received, mapped, with repeats in the same export removed.

    One export is one provider and one window, so a repeated topic is a
    duplicate. The first row is kept and the repeat is listed, never averaged.
    """
    topics, duplicates, seen = [], [], {}
    for row in score_records:
        name = _clean(row.get("Topic"))
        if not name:
            continue
        raw_score = _clean(row.get("Composite Score"))
        score = _parse_score(raw_score)
        key = name.casefold()
        if key in seen:
            duplicates.append({"topic_name": name, "composite_score": score,
                               "kept_score": seen[key]["composite_score"]})
            continue

        topic = {"topic_name": name, "composite_score": score, "source": "Source A",
                 "intensity": tm.intensity(score), "included": score is not None,
                 "exclusion_reason": None, "hiring_linked": tm.is_hiring_linked(name),
                 **tm.map_topic(name)}
        if score is None:
            # Excluded rather than scored 0: a zero would read as a measured
            # absence of interest, which the provider never reported.
            topic["exclusion_reason"] = f"Composite Score '{raw_score}' is not a number"
        seen[key] = topic
        topics.append(topic)

    topics.sort(key=lambda t: (t["composite_score"] is None, -(t["composite_score"] or 0)))
    return topics, duplicates


def _stats(topics: list[dict]) -> dict:
    """Max and average of the provider's scores. score_sum and topic_count are
    kept so the average can be re-derived by hand from the listed topics."""
    scores = [t["composite_score"] for t in topics]
    total = sum(scores)
    return {
        "topic_count": len(scores),
        "score_sum": total,
        "max": max(scores) if scores else None,
        "average": round(total / len(scores), 1) if scores else None,
        "intensity": tm.intensity(max(scores)) if scores else None,
        "topics": [t["topic_name"] for t in topics],
    }


def _tech_inventory(techno_records: list[dict], webstack_records: list[dict]) -> list[dict]:
    """Every technology the account runs, from Explorium sheet 4 (technographics,
    one comma-separated list per category column) and sheet 5 (webstack, the
    website's technologies). Each keeps the sheet and column it came from."""
    inventory, seen = [], set()

    def add(raw, sheet, column):
        for item in str(raw or "").split(","):
            name = _clean(item)
            key = name.replace("_", " ").lower()
            if name and key not in seen:
                seen.add(key)
                inventory.append({"name": name, "sheet": sheet, "column": column,
                                  "match_name": name.replace("_", " ")})

    for row in techno_records[:1]:
        # Category columns first, so a technology is credited to the category it
        # is filed under rather than the catch-all Full Tech Stack.
        for column, value in sorted(row.items(), key=lambda kv: kv[0] == "Full Tech Stack"):
            add(value, "4_Technographics", column)
    for row in webstack_records[:1]:
        add(row.get("Technologies Used By Company Website"), "5_Webstack",
            "Technologies Used By Company Website")
    return inventory


def _cell(value) -> str | None:
    """A category-file cell, or None where the export marks it empty."""
    v = _clean(value)
    return None if v.lower() in EMPTY_MARKERS else v


def _cell_list(value) -> list[str]:
    v = _cell(value)
    return [p for p in (_cell(x) for x in v.split("|")) if p] if v else []


def _parse_category_file(rows: list[list[str]], account_domain: str) -> dict:
    """The HP category intent export, wide layout.

    Row 1 names each category once ("PCs (Score /100)") above the columns it
    spans; row 2 names the fields; each later row is one company. The row for
    this account is found by domain - a similarly named company on another
    domain is not attached.
    """
    result = {"status": "no_file", "source": None, "categories": {},
              "top_check": None, "note": None}
    if len(rows) < 3:
        return result

    groups, current = [], None
    for cell in rows[0]:
        name = _clean(cell)
        if name:
            m = re.match(r"^(.*?)\s*\(score\s*/\s*100\)$", name, re.I)
            current = m.group(1).strip() if m else None
        groups.append(current)
    fields = [_clean(c).lower() for c in rows[1]]

    def account_field(record, name):
        for i, (g, f) in enumerate(zip(groups, fields)):
            if g is None and f == name and i < len(record):
                return _cell(record[i])
        return None

    records = [r for r in rows[2:] if any(_clean(c) for c in r)]
    account_d = _norm_domain(account_domain)
    matching = [r for r in records if _norm_domain(account_field(r, "domain")) == account_d]
    if not account_d or not matching:
        first = records[0] if records else []
        result["status"] = "unverified" if not account_d else "mismatch"
        result["note"] = ("The account has no domain on file to check the category file against."
                          if not account_d else
                          f"The category file has no row for {account_d}"
                          + (f" (it covers {_norm_domain(account_field(first, 'domain'))})"
                             if first else "") + ". Its scores are not attached to this account.")
        return result

    # Several runs for one domain: the latest run is the current one.
    record = max(matching, key=lambda r: account_field(r, "run date") or "")
    result["status"] = "matched"
    result["source"] = {
        "dataset": "hp_category_intent",
        "label": "HP Category Intent file",
        "company": account_field(record, "company"),
        "domain": account_d,
        "run_date": account_field(record, "run date"),
        "runs_on_file": len(matching),
    }

    categories = {}
    for i, (group, field) in enumerate(zip(groups, fields)):
        key = CATEGORY_FIELDS.get(field)
        if group is None or key is None or i >= len(record):
            continue
        entry = categories.setdefault(group, {"provider_category": group})
        if key in LIST_FIELDS:
            entry[key] = _cell_list(record[i])
        elif key == "score":
            entry[key] = _parse_score(record[i])
        else:
            entry[key] = _cell(record[i])

    for group, entry in categories.items():
        stage = (entry.get("stage") or "").lower()
        # The file's own verdict on whether the category shows a signal.
        entry["has_signal"] = bool(entry.get("score")) and stage not in ("", "no signal")
        # "Trend labels require comparable prior windows from the same scoring
        # definition/provider." The file carries one run and no prior score, so
        # its Increasing/Stable/Decreasing label cannot be checked against
        # anything. It is kept as the file's own words under trend_label and is
        # never promoted to a trend the screen can draw a direction from.
        entry["trend_label"] = entry.pop("trend", None)
        entry["trend"] = None
        entry["trend_basis"] = ("The file states a direction but supplies no prior score or "
                                "window to check it against, so no trend is shown.")
        entry["quality_flags"] = [
            {"term": item, "field": label, "reason": tm.NOISY_CATEGORY_TERMS[item.lower()]}
            for label, items in (("Topics Researched", entry.get("topics_researched") or []),
                                 ("Keywords Matched", entry.get("keywords_matched") or []))
            for item in items if item.lower() in tm.NOISY_CATEGORY_TERMS
        ]
        result["categories"][tm.CATEGORY_ALIASES.get(group.lower(), group)] = entry

    # The file states its own top category; check it against its scores.
    scored = [(e["score"], name) for name, e in result["categories"].items()
              if e.get("score") is not None]
    top_name = account_field(record, "top hp category")
    top_score = _parse_score(account_field(record, "top intent score (/100)"))
    if scored:
        best_score, best_name = max(scored)
        stated = tm.CATEGORY_ALIASES.get((top_name or "").lower(), top_name)
        result["top_check"] = {
            "stated_category": top_name, "stated_score": top_score,
            "recomputed_category": best_name, "recomputed_score": best_score,
            "consistent": stated == best_name and top_score == best_score,
        }
    return result


def _supporting_signals(included: list[dict], category: str, inventory: list[dict]) -> list[dict]:
    """Steps 2-4 for one category: Bombora topics grouped by signal family, each
    with its exact score, and the account technologies that confirm the family."""
    grouped = {}
    for t in included:
        family = tm.signal_family(t["topic_name"], category)
        if family:
            grouped.setdefault(family["signal"], []).append(
                {"topic_name": t["topic_name"], "composite_score": t["composite_score"]})

    signals = []
    for family in tm.SIGNAL_FAMILIES.get(category, ()):
        topics = sorted(grouped.get(family["signal"], []), key=lambda x: -x["composite_score"])
        techs = [{k: v for k, v in t.items() if k != "match_name"}
                 for t in tm.family_technologies(family, inventory)]
        if topics or techs:
            signals.append({
                "signal": family["signal"],
                "topics": topics,
                "max": topics[0]["composite_score"] if topics else None,
                "technologies": techs,
                "confirmed": bool(topics and techs),
            })
    # Confirmed signals first, then research with no matching technology, then
    # technology with no Bombora research behind it.
    signals.sort(key=lambda s: (not s["confirmed"], not s["topics"], -(s["max"] or 0)))
    return signals


def _category_explanation(cat: dict, file_entry: dict | None, signals: list[dict]) -> str:
    """What the signals may mean for HP. Research interest only."""
    name, play = cat["category"], cat["hp_play"]
    if file_entry is None:
        parts = [f"No {name} score in the category file."]
    else:
        parts = [f"{name}: {file_entry.get('score')}/100 in the category file "
                 f"({file_entry.get('stage') or 'no stage'})."]
        if file_entry.get("quality_flags"):
            terms = ", ".join(f"'{f['term']}'" for f in file_entry["quality_flags"])
            parts.append(f"Read this score with care: it rests on noisy keyword {terms}, "
                         f"which does not mean here what the category assumes.")

    confirmed = [s for s in signals if s["confirmed"]]
    unconfirmed = [s for s in signals if s["topics"] and not s["confirmed"]]
    if confirmed:
        parts.append("Supporting research backed by the account's own technology: " + "; ".join(
            f"{s['signal']} (max {s['max']}; {', '.join(t['name'] for t in s['technologies'][:4])})"
            for s in confirmed) + ".")
    if unconfirmed:
        parts.append("Research with no matching technology: " + ", ".join(
            f"{s['signal']} ({s['max']})" for s in unconfirmed) + ".")
    if not confirmed and not unconfirmed:
        parts.append("No supporting Bombora research.")

    if confirmed:
        parts.append(f"This may strengthen an existing {play} conversation; it does not "
                     f"change the category score.")
    else:
        parts.append(f"On its own this does not support a recommendation for {play}.")
    return " ".join(parts)


def _summarise(topics: list[dict], category_file: dict, inventory: list[dict]) -> dict:
    """Category scores from the file, supporting signals from Bombora and the
    account's technology, and theme summaries from the included topics only."""
    included = [t for t in topics if t["included"]]
    file_cats = category_file["categories"] if category_file["status"] == "matched" else {}

    themes = []
    for theme in tm.THEMES:
        members = [t for t in included if t["theme"] == theme]
        entry = {"theme": theme, **_stats(members)}
        if theme == tm.THEME_OTHER:
            entry["flagged_count"] = sum(1 for t in members if t["mapping_status"] == "flagged")
        themes.append(entry)

    categories = []
    hp_names = [c["category"] for c in tm.HP_CATEGORIES]
    for cat in list(tm.HP_CATEGORIES) + [{"category": n, "hp_play": None}
                                          for n in file_cats if n not in hp_names]:
        name = cat["category"]
        file_entry = file_cats.get(name)
        signals = _supporting_signals(included, name, inventory)
        categories.append({
            "category": name,
            "hp_play": cat["hp_play"],
            # Step 1: the category's score, as received from the category file.
            "primary": file_entry,
            # Steps 2-4: Bombora signals with exact scores, and confirming technology.
            "supporting_signals": signals,
            "confirmed_max": max((s["max"] for s in signals if s["confirmed"]), default=None),
            # Bombora topics the dictionary maps straight to this category (spec Step 6:
            # shown apart from the file's score so its origin is clear).
            "bombora_mapped": _stats([t for t in included if t["hp_category"] == name]),
            "explanation": _category_explanation(cat, file_entry, signals),
        })

    # The feature spec asks for the HP-category view across PC, Workstation,
    # Poly/Collaboration, Print and 3D, "clearly distinguishing provider-supplied
    # vs internally mapped scores". It does not ask for one category to be
    # ranked above the others, so none is: the categories are ordered by the
    # file's own score and a noisy keyword is reported as a caveat on its own
    # category rather than removing that category from a ranking.
    categories.sort(key=lambda c: -((c["primary"] or {}).get("score") or 0))

    ai = next(t for t in themes if t["theme"] == tm.THEME_AI)
    if ai["topic_count"]:
        ai["explanation"] = ("The topics name no HP category, so none is mapped (Step 4). They "
                             "appear as supporting signals on the categories they relate to.")

    so_what = []
    scored = [c for c in categories if c["primary"] and c["primary"].get("score") is not None]
    signalled = [c for c in scored if c["primary"].get("has_signal")]
    if scored:
        so_what.append("HP Category Intent file scores: " + "; ".join(
            f"{c['category']} {c['primary'].get('score')}/100 "
            f"({c['primary'].get('stage') or 'no stage'})" for c in scored) + ".")
        if not signalled:
            so_what.append("The category file reports no buying stage for any category, so none "
                           "of these scores stands as a signal on its own.")
    elif file_cats:
        so_what.append("The HP Category Intent file supplies no category score for this account.")
    else:
        so_what.append("No HP Category Intent file for this account, so there are no HP category "
                       "scores.")

    confirmed_by_cat = [(c, [s for s in c["supporting_signals"] if s["confirmed"]])
                        for c in categories]
    confirmed_by_cat = [(c, sigs) for c, sigs in confirmed_by_cat if sigs]
    if confirmed_by_cat:
        so_what.append("Supporting research confirmed by the account's own technology: " + "; ".join(
            f"{c['category']} - " + ", ".join(
                f"{s['signal']} (max {s['max']}, backed by "
                f"{', '.join(t['name'] for t in s['technologies'][:3])})" for s in sigs)
            for c, sigs in confirmed_by_cat) + ".")

    noisy = [c for c in categories if c["primary"] and c["primary"].get("quality_flags")]
    if noisy:
        so_what.append("Read with care: " + "; ".join(
            f"{c['category']} ({c['primary'].get('score')}/100) rests on noisy keyword "
            + ", ".join(f"'{f['term']}'" for f in c["primary"]["quality_flags"])
            for c in noisy) + ".")

    hiring = _stats([t for t in included if t["hiring_linked"]])
    if hiring["topic_count"]:
        so_what.append(f"{hiring['topic_count']} Bombora topics relate to staffing (max "
                       f"{hiring['max']}); they sit with the hiring-linked demand below.")

    return {"themes": themes, "hp_categories": categories,
            "categories_with_signal": sum(1 for c in categories
                                          if (c["primary"] or {}).get("has_signal")),
            "hiring_linked": hiring, "so_what": so_what}


def _write(db, payload: dict) -> dict:
    db["account_widgets"].update_one(
        {"account_id": payload["account_id"], "widget_key": payload["widget_key"]},
        {"$set": payload},
        upsert=True,
    )
    return payload


def _hiring_widget(account_id: str, job_records: list[dict], now) -> dict:
    """Source B. postings_seen counts every row, the same figure the Executive
    Dashboard shows; open_postings is reported beside it, never in its place."""
    payload = {
        "account_id": account_id,
        "feature_key": "intent_demand_signals",
        "widget_key": "intent_hiring_demand",
        "data_classification": "deterministic",
        "status": "empty",
        "data": {},
        "source_datasets": ["job_openings"],
        "extracted_at": now,
        "updated_at": now,
    }
    if not job_records:
        return payload

    sen_counter, cat_counter, status_counter = Counter(), Counter(), Counter()
    for j in job_records:
        sen_counter[_clean(j.get("seniority")).lower() or "unspecified"] += 1
        status_counter[_clean(j.get("status")).lower() or "unspecified"] += 1

        cat_raw = _clean(j.get("categories"))
        if cat_raw:
            try:
                # JSON array string e.g. ["information_technology", "management"]
                cat_list = json.loads(cat_raw)
                if isinstance(cat_list, list):
                    for c in cat_list:
                        cat_counter[str(c).strip().lower()] += 1
                else:
                    cat_counter[cat_raw.lower()] += 1
            except Exception:
                cat_counter[cat_raw.lower()] += 1

    open_postings = sum(1 for j in job_records
                        if _clean(j.get("status")).lower() in OPEN_STATUSES)
    first_seen = sorted(_clean(j.get("first_seen_at")) for j in job_records if _clean(j.get("first_seen_at")))
    last_seen = sorted(_clean(j.get("last_seen_at")) for j in job_records if _clean(j.get("last_seen_at")))

    payload["status"] = "available"
    payload["data"] = {
        "source": "Source B",
        "postings_seen": len(job_records),
        "open_postings": open_postings,
        "open_postings_rule": "status blank, 'open' or 'active'",
        "status_breakdown": dict(status_counter),
        "seniority_breakdown": dict(sen_counter),
        "category_breakdown": dict(cat_counter.most_common(10)),
        "first_seen": first_seen[0][:10] if first_seen else None,
        "last_seen": last_seen[-1][:10] if last_seen else None,
    }
    return payload


@requires_local_datasets(
    "intent_score", "intent_topics", "job_openings", "hp_category_intent",
    "technographics", "webstack",
)
def extract_intent_demand_signals(account_id: str) -> list[dict]:
    db = get_db()
    now = datetime.now(timezone.utc)

    score_records = _read_dataset_records(account_id, "intent_score")
    topics_meta_records = _read_dataset_records(account_id, "intent_topics")
    job_records = _read_dataset_records(account_id, "job_openings")
    category_rows = read_dataset_rows(account_id, "hp_category_intent")
    inventory = _tech_inventory(_read_dataset_records(account_id, "technographics"),
                                _read_dataset_records(account_id, "webstack"))

    # Resolved rather than read straight off the account record: nothing
    # populates `accounts.domain`, so this reported "no domain on file" for every
    # account while firmographics held one. See datasets.account_domain.
    domain = account_domain(account_id)
    account_match, observation = _match_provider_account(topics_meta_records, domain)
    observation["refreshed_at"] = _file_refreshed_at(db, account_id, "intent_score")
    category_file = _parse_category_file(category_rows, domain)
    if category_file["source"]:
        category_file["source"]["refreshed_at"] = _file_refreshed_at(db, account_id, "hp_category_intent")

    provenance = {
        "provider": PROVIDER,
        "account_match": account_match,
        "observation": observation,
        "dictionary_version": tm.DICTIONARY_VERSION,
    }

    topics_payload = {
        "account_id": account_id,
        "feature_key": "intent_demand_signals",
        "widget_key": "intent_topics_table",
        "data_classification": "deterministic",
        "status": "empty",
        "data": {},
        "source_datasets": ["intent_score", "intent_topics"],
        "extracted_at": now,
        "updated_at": now,
    }
    summary_payload = {
        **topics_payload,
        "widget_key": "intent_category_summary",
        "data_classification": "derived",
        "source_datasets": ["hp_category_intent", "intent_score", "intent_topics",
                            "technographics", "webstack"],
        "data": {},
    }

    topics, duplicates = _build_topics(score_records)

    # Unavailable is stated, never shown as a score of zero.
    if not topics:
        source_a_unavailable = {"availability": "no_intent_data",
                                "message": "Intent unavailable: no Bombora intent topics are "
                                           "on file for this account."}
    elif account_match["status"] == "mismatch":
        source_a_unavailable = {"availability": "no_matched_signal",
                                "message": "No matched signal: " + account_match["note"]}
        topics = []
    else:
        source_a_unavailable = None

    if source_a_unavailable:
        topics_payload["data"] = {**provenance, **source_a_unavailable}
    else:
        topics_payload["status"] = "available"
        topics_payload["data"] = {
            **provenance,
            "availability": "available",
            "total_topics_count": len(topics),
            "included_topics_count": sum(1 for t in topics if t["included"]),
            "level_of_intent": account_match["level_of_intent"],
            "topics": topics,
            "duplicates_removed": duplicates,
            "disclaimer": DISCLAIMER,
        }

    if source_a_unavailable and category_file["status"] != "matched":
        summary_payload["data"] = {**provenance, **source_a_unavailable,
                                   "category_file": category_file}
    else:
        included = [t for t in topics if t["included"]]
        summary_payload["status"] = "available"
        summary_payload["data"] = {
            **provenance,
            "availability": "available",
            "source_a_status": source_a_unavailable,
            "category_file": {k: v for k, v in category_file.items() if k != "categories"},
            **_summarise(topics, category_file, inventory),
            "hp_category_total": len(tm.HP_CATEGORIES),
            "total_topics_count": len(topics),
            "included_topics_count": len(included),
            "excluded_topics_count": len(topics) - len(included),
            "trend": {
                "status": "unavailable",
                "reason": "A trend needs a prior window with the same scoring definition. "
                          "Only the current export is on file, for Bombora themes and for "
                          "the HP category file alike, so no direction is shown for either.",
            },
            "technology_sources": ["4_Technographics", "5_Webstack"],
            "technology_count": len(inventory),
            "intensity_bands": [{"min": floor, "label": label}
                                for floor, label in tm.INTENSITY_BANDS],
            "disclaimer": DISCLAIMER,
        }

    return [
        _write(db, topics_payload),
        _write(db, summary_payload),
        _write(db, _hiring_widget(account_id, job_records, now)),
    ]
