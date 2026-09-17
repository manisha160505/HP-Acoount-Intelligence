"""Strategy Chat context - the grounding line above the conversation.

Two widgets, both deterministic:

  strategy_snapshot_context  what the chat is grounded in, and the suggested
                             openers shown before the first question
  strategy_chat_interface    whether the feature can answer yet, and why not

**Read from the other features' finished widgets, not from the CSVs.** That is
the whole design of this feature - the meeting was explicit: *"now these answers
raw data can't give, because raw data we analyzed and made all the outputs. So
now we will make this rack the final one on the dashboard outputs."* An earlier
version of this file read ten raw datasets and recomputed counts that the
features had already computed differently, so the header disagreed with the
screens it claimed to summarise.

**Nothing has a fallback.** The previous version carried five:

    live_signals_count  = len(seen_headlines) if seen_headlines else 10
    stakeholders_count  = len(contacts_records) if contacts_records else 23
    intent_topics_count = len(intent_score_records) if intent_score_records else 149
    installed_vendors_count = len(full_tech_stack) if full_tech_stack else 220
    "solutions_count": 5,

Every one of those would print a confident number for an account with no data at
all - and the 23 and the 5 happened to match Astra, so they looked verified. A
count with no source is absent here, and the header shows a dash.

It also did `list(seen_headlines)[:5]` over a **set**, so "recent trigger events"
was whichever five Python happened to hash first and changed between runs.
"""

from datetime import UTC, datetime

from bson import ObjectId

from app.database.mongodb import get_db

MAX_SNAPSHOT_TOPICS = 5
MAX_SNAPSHOT_VENDORS = 15
MAX_SNAPSHOT_SIGNALS = 5


def _text(value) -> str:
    return " ".join(str(value if value is not None else "").split())


def _int(value):
    """An int, or None. Never a guess - widgets store counts as strings."""
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def _widget(db, account_id: str, widget_key: str) -> dict:
    """One widget's data, or {} when it has not been published."""
    found = db["account_widgets"].find_one(
        {"account_id": account_id, "widget_key": widget_key})
    if not found or found.get("status") != "available":
        return {}
    return found.get("data") or {}


def extract_strategy_chat(account_id: str) -> list[dict]:
    """Build the two Strategy Chat widgets from the other features' outputs."""
    db = get_db()
    now = datetime.now(UTC)

    summary = _widget(db, account_id, "exec_summary_card")
    contacts = _widget(db, account_id, "stakeholder_contacts_grid")
    plays = _widget(db, account_id, "opportunity_narrative_plays")
    techmap = _widget(db, account_id, "technographic_map")
    intent = _widget(db, account_id, "intent_topics_table")
    signals = _widget(db, account_id, "news_signals_feed")
    priorities = _widget(db, account_id, "exec_strategic_priorities")

    account = None
    if ObjectId.is_valid(account_id):
        account = db["accounts"].find_one({"_id": ObjectId(account_id)})
    company_name = (_text(summary.get("company_name"))
                    or _text((account or {}).get("name")))

    # Sourced from the widget that OWNS each count, not recounted from the raw
    # rows, so the header agrees with the screen a seller clicks through to.
    # Recounting here is how the header came to disagree with the features it
    # summarises - and both halves of this were once hardcoded to one seed
    # account's figures (10 / 23 / 149 / 220), which an account missing a
    # dataset then published as its own.
    counts = {
        "stakeholders_count": _int(contacts.get("total_contacts_count")),
        "solutions_count": (len(plays.get("opportunity_plays") or [])
                            if plays.get("opportunity_plays") is not None else None),
        "installed_vendors_count": _int(techmap.get("total_detected_technologies")),
        "live_signals_count": _int(signals.get("total_signals_count")),
        "intent_topics_count": _int(intent.get("total_topics_count")),
        "priorities_count": _int(priorities.get("priority_count")),
    }
    grounding_metadata = {
        "company_name": company_name or None,
        **counts,
        # Which of the above rest on a published widget. The chat UI reads this
        # to say "not available" rather than rendering an absent count as a
        # zero, which reads as a fact about the account.
        "unavailable_counts": sorted(k for k, v in counts.items() if v is None),
    }

    topics = [_text(t.get("topic_name"))
              for t in (intent.get("topics") or [])[:MAX_SNAPSHOT_TOPICS]
              if _text(t.get("topic_name"))]

    vendors = []
    for category in (techmap.get("categories") or []):
        for vendor in (category.get("vendors") or []):
            name = _text(vendor.get("vendor_name"))
            if name and name not in vendors:
                vendors.append(name)
            if len(vendors) >= MAX_SNAPSHOT_VENDORS:
                break
        if len(vendors) >= MAX_SNAPSHOT_VENDORS:
            break

    # In feed order - the feature already ranked and gated these. The previous
    # version took five arbitrary members of a set and called them recent.
    recent_events = [_text(s.get("headline"))
                     for s in (signals.get("signals") or [])[:MAX_SNAPSHOT_SIGNALS]
                     if _text(s.get("headline"))]

    snapshot_context = {
        "company_name": company_name or None,
        "stakeholders_count": grounding_metadata["stakeholders_count"],
        "installed_vendors": vendors,
        "top_intent_topics": topics,
        "recent_trigger_events": recent_events,
    }

    context_payload = {
        "account_id": account_id,
        "feature_key": "strategy_chat",
        "widget_key": "strategy_snapshot_context",
        "data_classification": "deterministic",
        "status": "available" if company_name else "empty",
        "data": {
            "grounding_metadata": grounding_metadata,
            "snapshot_context": snapshot_context,
            "suggested_prompts": _suggested_prompts(company_name),
            "source": ("Built from the finished widgets of the other features, "
                       "not from the raw uploads."),
        } if company_name else {},
        "source_datasets": [],
        "extracted_at": now,
        "updated_at": now,
    }

    # What the chat can actually answer from today. The index state is the
    # authority on whether a question can be asked at all; this records what the
    # corpus was built over.
    grounded_features = sorted(
        key for key, data in (
            ("Executive Dashboard", priorities), ("Stakeholder Map", contacts),
            ("Recent Signals", signals), ("Tech Landscape", techmap),
            ("Intent & Demand", intent), ("Opportunity Map", plays),
        ) if data)

    interface_payload = {
        "account_id": account_id,
        "feature_key": "strategy_chat",
        "widget_key": "strategy_chat_interface",
        "data_classification": "deterministic",
        "status": "available" if grounded_features else "empty",
        "data": {
            "grounded_features": grounded_features,
            "grounded_feature_count": len(grounded_features),
        } if grounded_features else {},
        "source_datasets": [],
        "extracted_at": now,
        "updated_at": now,
    }

    results = [context_payload, interface_payload]
    for payload in results:
        db["account_widgets"].update_one(
            {"account_id": payload["account_id"],
             "widget_key": payload["widget_key"]},
            {"$set": payload}, upsert=True)
    return results


def _suggested_prompts(company_name: str) -> list:
    """The openers shown before the first question.

    Matched to the reference's `smartStarters`, and phrased as the questions the
    meeting actually asked for - *"tell me what to do, what to sell"*, *"there
    are so many signals, tell me who to act on"*, *"who should I message for
    AIPCs"*.
    """
    name = company_name or "this account"
    return [
        {"id": "entry_point", "title": "Best entry point",
         "prompt_text": "Who is the strongest entry point at %s, and why?" % name},
        {"id": "what_to_sell", "title": "What to sell",
         "prompt_text": "Based on %s's own evidence, which HP line has the "
                        "strongest case right now?" % name},
        {"id": "who_to_act_on", "title": "Who to act on",
         "prompt_text": "There are a lot of signals for %s. Which ones should I "
                        "act on first?" % name},
        {"id": "ai_pcs", "title": "Who to message for AI PCs",
         "prompt_text": "Who should I message at %s about AI PCs, and what "
                        "should I open with?" % name},
        {"id": "objections", "title": "Objections to expect",
         "prompt_text": "What objections should I expect from %s, and how do I "
                        "handle each one?" % name},
        {"id": "revenue", "title": "Financial picture",
         "prompt_text": "Tell me about %s's revenue and what it means for our "
                        "approach." % name},
    ]
