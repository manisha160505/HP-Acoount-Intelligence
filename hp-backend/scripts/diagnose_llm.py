"""Diagnose why LLM-generated widgets come back empty on a given machine.

Every failure inside `generate_gpt4o_json_completion` is swallowed into a silent
`None` (app/core/llm.py), so a bad key, a corporate proxy, a wrong deployment
name and an unsupported `response_format` all look identical from the UI: a
blank widget. This script does the same work with the exception left visible.

It reads only. It creates and modifies nothing, and it never prints the API key.

    cd hp-backend
    python scripts/diagnose_llm.py

Exit codes: 0 = healthy, 1 = key not loaded, 2 = an Azure call failed.
"""

import os
import sys
import traceback
from importlib.metadata import version, PackageNotFoundError

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from app.config.settings import settings                    # noqa: E402
from app.core.llm import get_openai_client                  # noqa: E402

# The four widgets whose content is produced by GPT-4o. Everything else on the
# dashboard is deterministic and will render with or without a working key.
LLM_WIDGETS = [
    "news_relevance_summary",
    "stakeholder_talking_points",
    "opportunity_narrative_plays",
    "objection_reframe_cards",
]

# What the pipeline resolved to on a machine where it is known to work. A
# mismatch here is not proof of a fault, but it is the first thing to compare.
KNOWN_GOOD = {
    "openai": "2.38.0",
    "pydantic-settings": "2.14.1",
    "pydantic": "2.13.4",
    "pymongo": "4.17.0",
    "fastapi": "0.136.1",
}


def _rule(title: str) -> None:
    print(f"\n{'=' * 70}\n{title}\n{'=' * 70}")


def _report_context() -> None:
    _rule("1. CONTEXT")
    cwd = os.getcwd()
    print(f"  working directory : {cwd}")
    print(f"  python            : {sys.version.split()[0]}")

    # config/settings.py sets `env_file = ".env"`, which pydantic-settings
    # resolves relative to the working directory - NOT to the repo root. This is
    # the exact path it looked for.
    env_path = os.path.abspath(".env")
    print(f"  .env pydantic reads: {env_path}")
    print(f"  ...does it exist?  : {'YES' if os.path.exists(env_path) else 'NO  <-- nothing loaded from file'}")

    if not os.path.exists(env_path):
        parent = os.path.abspath(os.path.join("..", ".env"))
        if os.path.exists(parent):
            print(f"  NOTE: a .env exists one level up ({parent}) but is NOT read from here.")
            print("        Run from hp-backend/, or copy that file into hp-backend/.")

    # A real environment variable silently outranks the file, so say which won.
    if os.environ.get("OPENAI_API_KEY") is not None:
        print("  OS environment    : OPENAI_API_KEY is set in the shell (this overrides the file)")
    else:
        print("  OS environment    : OPENAI_API_KEY not set in the shell (file value is used)")


def _report_settings() -> bool:
    """Print what the app actually loaded. Returns True when a key is present."""
    _rule("2. SETTINGS AS THE APP SEES THEM")
    key = (settings.OPENAI_API_KEY or "").strip()
    if key:
        # Enough to tell two keys apart, not enough to use.
        print(f"  OPENAI_API_KEY    : loaded, length={len(key)}, ends with ...{key[-4:]}")
    else:
        print("  OPENAI_API_KEY    : EMPTY  <-- every LLM call is skipped before it is made")

    print(f"  OPENAI_ENDPOINT   : {settings.OPENAI_ENDPOINT}")
    print(f"  OPENAI_MODEL_NAME : {settings.OPENAI_MODEL_NAME}")
    print(f"  MONGODB_URI       : {settings.MONGODB_URI}")
    print(f"  DB_NAME           : {settings.DB_NAME}")

    endpoint = (settings.OPENAI_ENDPOINT or "").strip()
    if endpoint and not endpoint.rstrip("/").endswith("/openai/v1"):
        print("  WARNING: endpoint does not end in /openai/v1/ - the Azure v1 surface this app expects.")
    return bool(key)


def _report_versions() -> None:
    _rule("3. INSTALLED VERSIONS")
    print("  Dependencies are unpinned (>=) in requirements.txt, so these were")
    print("  resolved on install day and may differ from the working machine.\n")
    for pkg, good in KNOWN_GOOD.items():
        try:
            have = version(pkg)
        except PackageNotFoundError:
            print(f"  {pkg:<20} NOT INSTALLED   (known good: {good})")
            continue
        flag = "" if have == good else "   <-- differs"
        print(f"  {pkg:<20} {have:<12} (known good: {good}){flag}")


def _call(label: str, describe: str, fn) -> bool:
    """Run one live call with the real exception left visible."""
    print(f"\n  -- {label}: {describe}")
    try:
        out = fn()
        print(f"     SUCCESS. Model replied: {out!r}")
        return True
    except Exception as exc:
        print(f"     FAILED: {type(exc).__name__}: {exc}\n")
        # The whole point of this script. app/core/llm.py swallows this.
        traceback.print_exc()
        return False


def _report_live_calls() -> tuple[bool, bool]:
    _rule("4. LIVE AZURE CALLS")
    client = get_openai_client()
    if client is None:
        print("  Client could not be constructed - no API key. Skipping calls.")
        return False, False

    model = settings.OPENAI_MODEL_NAME or "gpt-4o"
    print(f"  endpoint : {settings.OPENAI_ENDPOINT}")
    print(f"  model    : {model}")

    def plain():
        r = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": "Reply with the single word: ok"}],
        )
        return r.choices[0].message.content

    def json_mode():
        # Byte-for-byte the shape generate_gpt4o_json_completion uses.
        r = client.chat.completions.create(
            model=model,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": "You reply only in JSON."},
                {"role": "user", "content": 'Return exactly {"ok": true}'},
            ],
            temperature=0.2,
        )
        return r.choices[0].message.content

    a = _call("CALL A", "plain completion (tests auth, network, proxy, model name)", plain)
    b = _call("CALL B", "JSON mode, exactly as the app calls it", json_mode)

    if a and not b:
        print("\n  >> Reachable, but JSON mode failed. This breaks the app while leaving")
        print("     a plain connectivity test passing - the deployment or API version")
        print("     does not support response_format={'type':'json_object'}.")
    return a, b


def _report_mongo() -> None:
    _rule("5. STORED WIDGET STATE")
    try:
        from pymongo import MongoClient
        # Short timeout so a missing server fails fast instead of hanging 30s.
        db = MongoClient(settings.MONGODB_URI, serverSelectionTimeoutMS=5000)[settings.DB_NAME]
        accounts = list(db["accounts"].find())
    except Exception as exc:
        print(f"  Could not reach MongoDB at {settings.MONGODB_URI}")
        print(f"  {type(exc).__name__}: {exc}")
        return

    if not accounts:
        print("  No accounts. The startup seeder did not complete - check the backend")
        print("  console for '[Startup Seeder Notice]'.")
        return

    for acc in accounts:
        aid = str(acc["_id"])
        files = db["account_data_files"].count_documents({"account_id": aid, "status": "active"})
        widgets = list(db["account_widgets"].find({"account_id": aid}))
        counts: dict[str, int] = {}
        for w in widgets:
            counts[w.get("status", "?")] = counts.get(w.get("status", "?"), 0) + 1
        print(f"\n  {acc.get('name', '?')}  ({aid})")
        print(f"    active files: {files} | widgets: {counts or 'none'}")

        by_key = {w["widget_key"]: w for w in widgets}
        for key in LLM_WIDGETS:
            doc = by_key.get(key)
            if not doc:
                print(f"    {key:<30} NOT GENERATED")
                continue
            data = doc.get("data") or {}
            size = (data.get("scored_count") or data.get("generated_count")
                    or data.get("total_plays_count") or data.get("cards_count"))
            line = f"    {key:<30} {doc.get('status', '?'):<10} items={size if size is not None else '-'}"
            print(line)
            if data.get("notice"):
                print(f"        notice: {str(data['notice'])[:110]}")


def main() -> int:
    print("HP Account Intelligence - LLM pipeline diagnostic")
    _report_context()
    has_key = _report_settings()
    _report_versions()
    plain_ok, json_ok = _report_live_calls()
    _report_mongo()

    _rule("6. VERDICT")
    if not has_key:
        print("  OPENAI_API_KEY did not load into the app.")
        if os.environ.get("OPENAI_API_KEY") == "":
            print("  An empty OPENAI_API_KEY is set in the shell, and that outranks the file.")
            print("  Fix: unset it, then re-run.")
        elif os.path.exists(os.path.abspath(".env")):
            # The file is in the right place, so this is its contents, not its location.
            print("  The .env in section 1 WAS found, so this is the file's contents:")
            print("    - is the line exactly OPENAI_API_KEY=... with no spaces around '='?")
            print("    - is the value non-empty and unquoted?")
            print("    - was it saved as UTF-8 without BOM? Notepad's default adds one.")
        else:
            print("  No .env at the path in section 1 - this process read nothing from file.")
            print("  Fix: put .env in the directory you run the server from (hp-backend/).")
        return 1
    if not plain_ok:
        print("  The key loaded, but Azure could not be reached at all.")
        print("  Read the CALL A traceback above - it names the cause (401/403 = key or")
        print("  region, 404 = deployment name, timeout/SSL = proxy or firewall).")
        return 2
    if not json_ok:
        print("  Azure is reachable but rejects the JSON-mode request the app makes.")
        print("  Read the CALL B traceback. The deployment or API version does not")
        print("  support response_format={'type':'json_object'}.")
        return 2

    print("  Both calls succeeded - the LLM path is healthy on this machine.")
    print("  If widgets are still empty, they hold stale results from an earlier run.")
    print("  Page views never re-extract, so force a refresh per feature:")
    print("    POST /api/v1/accounts/{account_id}/widgets/{feature_key}/regenerate")
    print("  Note objection_playbook is not in the startup seeder, so it needs this.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
