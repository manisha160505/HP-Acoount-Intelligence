#!/usr/bin/env python3
"""Translate the stored News text of every account into English, in place.

Part of the 9 Oct English release (regen/english_release.py). News is not
rebuilt for it: a rebuild re-scores every story with the model, ~88K tokens an
account. Its stored headline, evidence sentence and publisher are translated
instead, with the same translator and cache PR 82's extractor uses, and the
original kept beside each field for the hover. Scores, order and everything
else stay exactly as generated; the section's fingerprint and output hash are
not touched, so nothing downstream goes stale.

Dry run by default: lists what would change and how much is already in the
translation cache, and calls no model. --apply translates what is missing and
writes. Safe to run again: translated fields are English and are skipped.

    python scripts/translate_stored_news.py
    python scripts/translate_stored_news.py --apply
    python scripts/translate_stored_news.py --apply --account "SOFTBANK GROUP CORP. - JP"
"""
import argparse
import copy
import json
import os
import sys
from datetime import UTC, datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from app.database.mongodb import connect_to_mongo, get_db  # noqa: E402
from app.services.hp import translate  # noqa: E402
from app.services.regen import english_release, state  # noqa: E402
from app.services.regen.graph import DEFAULT  # noqa: E402

NODE = "news"


def _cached(db, kind: str, texts: list) -> int:
    keys = [translate._key(kind, t) for t in set(texts)]
    return db[translate.COLLECTION].count_documents(
        {"_id": {"$in": keys}, "prompt_version": translate.TRANSLATE_PROMPT_VERSION})


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true", help="translate and write")
    ap.add_argument("--account", help="only this account (exact name)")
    args = ap.parse_args()

    connect_to_mongo()
    db = get_db()
    query = {"name": args.account} if args.account else {}
    accounts = list(db["accounts"].find(query, {"name": 1}))
    if args.account and not accounts:
        sys.exit("no account named %r" % args.account)

    total = {"accounts": 0, "strings": 0, "cached": 0, "changed": 0, "skipped": 0}
    for account in accounts:
        account_id = str(account["_id"])
        doc = db[state.COLLECTION].find_one({"_id": state.state_id(account_id, NODE)},
                                            {"current": 1})
        current = (doc or {}).get("current") or {}
        widgets = current.get("widgets") or {}
        texts: dict = {}
        for key in DEFAULT[NODE].widgets:
            for kind, values in english_release.news_texts(
                    (widgets.get(key) or {}).get("data") or {}).items():
                texts.setdefault(kind, []).extend(values)
        n = sum(len(set(v)) for v in texts.values())
        if not n:
            continue
        cached = sum(_cached(db, kind, values) for kind, values in texts.items())
        total["accounts"] += 1
        total["strings"] += n
        total["cached"] += cached
        if not args.apply:
            print("  would translate %-55s %4d string(s), %4d cached" % (account["name"], n, cached))
            continue

        english = {kind: translate.to_english(values, db, kind) for kind, values in texts.items()}
        updates, changed = {}, 0
        for key in DEFAULT[NODE].widgets:
            widget = widgets.get(key)
            if not widget:
                continue
            data = copy.deepcopy(widget.get("data") or {})
            count = english_release.translate_news(data, english)
            if count:
                updates[key] = data
                changed += count
        if not updates:
            continue
        sets = {"current.widgets.%s.data" % k: v for k, v in updates.items()}
        sets["current.translated_in_place"] = {
            "at": datetime.now(UTC), "strings": changed,
            "by": "translate_stored_news (9 Oct English release)"}
        # Only the generation that was read: one committed meanwhile is newer
        # and was built in English already.
        res = db[state.COLLECTION].update_one(
            {"_id": state.state_id(account_id, NODE),
             "current.generation_id": current.get("generation_id")},
            {"$set": sets})
        if not res.modified_count:
            total["skipped"] += 1
            print("  skipped   %-55s (a newer generation was committed)" % account["name"])
            continue
        # The rollback copy, where one exists.
        for key, data in updates.items():
            db["account_widgets"].update_one({"account_id": account_id, "widget_key": key},
                                             {"$set": {"data": data}})
        total["changed"] += changed
        print("  translated %-55s %4d string(s)" % (account["name"], changed))

    print(json.dumps({"mode": "apply" if args.apply else "dry run", **total}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
