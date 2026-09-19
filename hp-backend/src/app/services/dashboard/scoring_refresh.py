"""Regenerate the widgets a scoring-config change has invalidated.

`config/scoring.yaml` holds the weights and bands. Editing one changes what
every affected score *should* be — but a stored widget keeps the number it was
computed with, and nothing about it looks wrong. This closes that gap: each
scored widget records the config version that produced it, and this sweep finds
the ones whose stamp no longer matches and rebuilds them.

## Why this runs at startup and not on a page view

The config is read at import, so an edit only takes effect when the backend
restarts. That makes startup the exact moment the change becomes live, and the
one moment that cannot be missed.

The alternative was checking on read, and that is deliberately not done.
`api/v1/widgets.py` says so plainly — *"now that a page view no longer
re-extracts"* — a previous design did re-extract per view and was removed. Doing
it again through a different door would undo that decision.

## Why it is worth the code

This is not a hypothetical. The urgency formula was rewritten from a
five-driver delivery model to the client's four-driver one, the code was correct,
the tests passed — and the dashboard served the retired formula for days,
because nothing compared what a stored widget had been computed with against
what the code now did. The score looked plausible the whole time. Making the
weights editable makes that failure easier to reach, so the detection ships with
it.

## What it deliberately does not do

**It does not block startup.** Regeneration is queued, not run: several of these
extractors make model calls, and `_run_dependent_extractors` already blocks an
upload request while it does so. Repeating that on boot would make a config
typo look like a hung deploy.

**It is per section.** Retuning an urgency band rebuilds the Executive
Dashboard and nothing else. A single global version would rebuild every feature
on every edit, which is the kind of cost that gets a safety mechanism switched
off.
"""

import logging

from app.config import scoring

logger = logging.getLogger(__name__)

# Which widget carries which section's stamp, and which feature rebuilds it.
#
# The feature key is what `api/v1/account_data.py` already uses to re-run an
# extractor, so a stale widget is repaired through exactly the same path as a
# fresh upload rather than a second mechanism that could drift from it.
STAMPED_WIDGETS = (
    {"widget_key": "exec_urgency_score",
     "section": "urgency",
     "feature_key": "executive_dashboard",
     "stamp_path": ("scoring_config_version",)},
    {"widget_key": "news_relevance_summary",
     "section": "live_signal",
     "feature_key": "recent_news_signals",
     "stamp_path": ("scoring_config_version",)},
    {"widget_key": "technographic_map",
     "section": "tech_confidence",
     "feature_key": "tech_landscape",
     "stamp_path": ("confidence_report", "scoring_config_version")},
)


def _stamp_of(data: dict, path: tuple) -> str | None:
    node = data or {}
    for key in path[:-1]:
        node = node.get(key) or {}
        if not isinstance(node, dict):
            return None
    value = node.get(path[-1])
    return str(value) if value else None


def find_stale(db) -> list[dict]:
    """Widgets whose stamp does not match the config now loaded.

    A widget with **no** stamp is treated as stale. That is the case for every
    widget written before stamping existed, and it is the right default: an
    unstamped widget cannot be shown to agree with the current config, and
    assuming it does is how the urgency formula went unnoticed.
    """
    stale = []
    for spec in STAMPED_WIDGETS:
        try:
            current = scoring.version(spec["section"])
        except Exception:
            logger.exception("scoring refresh: no config section '%s'",
                             spec["section"])
            continue

        for widget in db["account_widgets"].find(
                {"widget_key": spec["widget_key"]},
                {"account_id": 1, "data": 1}):
            stamp = _stamp_of(widget.get("data") or {}, spec["stamp_path"])
            if stamp == current:
                continue
            stale.append({
                "account_id": str(widget.get("account_id")),
                "widget_key": spec["widget_key"],
                "feature_key": spec["feature_key"],
                "section": spec["section"],
                "stored": stamp,
                "current": current,
            })
    return stale


def refresh_stale_scores(db=None, apply: bool = True) -> dict:
    """Find, and optionally queue, the widgets a config change invalidated.

    `apply=False` reports without changing anything, which is what the tests
    and a dry run use.
    """
    if db is None:
        from app.database.mongodb import get_db
        db = get_db()

    try:
        stale = find_stale(db)
    except Exception:
        logger.exception("scoring refresh: could not inspect stored widgets")
        return {"checked": 0, "stale": [], "queued": [], "failed": []}

    report = {"checked": len(STAMPED_WIDGETS), "stale": stale,
              "queued": [], "failed": []}
    if not stale:
        logger.info("scoring refresh: every scored widget matches the current "
                    "config")
        return report

    logger.info("scoring refresh: %d widget(s) were scored with a different "
                "config and will be rebuilt", len(stale))
    if not apply:
        return report

    # One rebuild per (account, feature): three stale widgets on one account
    # from the same feature is still one extraction.
    wanted = {(row["account_id"], row["feature_key"]) for row in stale}
    for account_id, feature_key in sorted(wanted):
        try:
            _queue(account_id, feature_key)
            report["queued"].append({"account_id": account_id,
                                     "feature_key": feature_key})
        except Exception as exc:
            logger.exception("scoring refresh: could not queue %s for %s",
                             feature_key, account_id)
            report["failed"].append({"account_id": account_id,
                                     "feature_key": feature_key,
                                     "error": str(exc)})
    return report


def _queue(account_id: str, feature_key: str) -> None:
    """Run one feature's extractor on a worker thread.

    Threaded rather than awaited so a boot with many stale accounts does not
    hold the server closed. Each extractor already writes its own widgets and
    swallows nothing, so a failure here is logged and the stale widget simply
    stays stale until the next start - which is the safe direction.
    """
    import threading

    from app.api.v1.account_data import FEATURE_EXTRACTORS

    extractor = FEATURE_EXTRACTORS.get(feature_key)
    if not extractor:
        raise KeyError("no extractor registered for feature '%s'" % feature_key)

    def run():
        try:
            extractor(account_id)
            logger.info("scoring refresh: rebuilt %s for %s",
                        feature_key, account_id)
        except Exception:
            logger.exception("scoring refresh: %s failed for %s",
                             feature_key, account_id)

    threading.Thread(target=run, name="scoring-refresh-%s" % feature_key,
                     daemon=True).start()
