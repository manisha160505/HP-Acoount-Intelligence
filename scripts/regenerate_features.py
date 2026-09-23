#!/usr/bin/env python3
"""Re-run the extractors affected by the QA-fixes branch, over existing data.

Widgets are read from storage, not recomputed on a page view (see the comment
in api/v1/widgets.py at get_account_feature_widgets). So deploying new
extractor code does not change what the dashboard shows: each affected feature
has to be regenerated once, per account. No source file is re-uploaded and no
data is re-fetched - this only re-runs the extractors over data already stored.

Which features, and why:

  intent_demand_signals              changed directly (quality_flags, trend,
                                     summary text)
  executive_dashboard                imports build_urgency_score from the
                                     changed dashboard/urgency.py
  tech_landscape                     imports _parse_category_file
  solution_narrative_opportunity_map changed directly (timing gate) AND calls
                                     GPT-4o, so it costs money and its wording
                                     will differ from the stored copy

The first three are pure recomputation and free. The fourth is opt-in behind
--include-llm precisely because it is not.

Usage:
    python scripts/regenerate_features.py --base-url https://... --account <id>
    python scripts/regenerate_features.py ... --dry-run
    python scripts/regenerate_features.py ... --include-llm

Credentials come from the environment, never from arguments (an argument would
land in your shell history). Either:
    HP_TOKEN                    a bearer token copied from a browser session
    HP_EMAIL + HP_PASSWORD      a dashboard login, exchanged for a token here

HP_TOKEN wins when both are set. A token expires (typically 24h), so a failure
with HTTP 401 usually means it needs copying again rather than anything broken.
"""
import argparse
import base64
import json
import os
import sys
import time
import urllib.error
import urllib.request

FREE_FEATURES = [
    "intent_demand_signals",
    "executive_dashboard",
    "tech_landscape",
]
LLM_FEATURES = [
    "solution_narrative_opportunity_map",
]


def _call(url, token=None, payload=None, timeout=300):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data,
                                 method="POST" if data is not None else "GET")
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = resp.read().decode()
        return resp.status, (json.loads(body) if body else None)


def token_expiry(token):
    """Seconds left on a JWT, or None when the token carries no readable exp.

    Read locally, without the signing secret: the claims are base64, and only
    the signature needs the secret. This is purely so an expired token is
    reported as expired rather than as a confusing 401 mid-run.
    """
    try:
        payload = token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        exp = json.loads(base64.urlsafe_b64decode(payload)).get("exp")
        return None if exp is None else exp - time.time()
    except (IndexError, ValueError, TypeError):
        return None


def login(base_url, email, password):
    status, body = _call(f"{base_url}/api/v1/auth/login",
                         payload={"email": email, "password": password})
    if status != 200 or not body or "access_token" not in body:
        raise SystemExit(f"login failed (HTTP {status})")
    return body["access_token"]


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--base-url", required=True,
                   help="Backend root, e.g. https://hp-backend-xxxx.onrender.com")
    p.add_argument("--account", required=True, action="append", dest="accounts",
                   help="Account id; repeat for more than one")
    p.add_argument("--include-llm", action="store_true",
                   help="Also regenerate solution_narrative_opportunity_map "
                        "(calls GPT-4o: costs tokens, output will differ)")
    p.add_argument("--dry-run", action="store_true",
                   help="Print what would run and exit without changing anything")
    args = p.parse_args()

    base_url = args.base_url.rstrip("/")
    features = FREE_FEATURES + (LLM_FEATURES if args.include_llm else [])

    print(f"Backend : {base_url}")
    print(f"Accounts: {', '.join(args.accounts)}")
    print("Features:")
    for f in features:
        print(f"  - {f}" + ("   [LLM - costs tokens]" if f in LLM_FEATURES else ""))
    if not args.include_llm:
        print(f"  ({', '.join(LLM_FEATURES)} skipped; pass --include-llm to include)")

    if args.dry_run:
        print("\nDry run - nothing was changed.")
        return 0

    token = os.getenv("HP_TOKEN")
    if token:
        token = token.strip()
        remaining = token_expiry(token)
        if remaining is not None and remaining <= 0:
            raise SystemExit("HP_TOKEN has expired - log in again and re-copy it")
        if remaining is not None:
            print(f"\nUsing HP_TOKEN ({remaining / 3600:.1f}h before it expires).")
        else:
            print("\nUsing HP_TOKEN.")
    else:
        email, password = os.getenv("HP_EMAIL"), os.getenv("HP_PASSWORD")
        if not email or not password:
            raise SystemExit(
                "set HP_TOKEN, or HP_EMAIL and HP_PASSWORD, in the environment")
        token = login(base_url, email, password)
        print("\nAuthenticated.")
    print()

    failures = []
    for account_id in args.accounts:
        print(f"Account {account_id}")
        for feature in features:
            url = (f"{base_url}/api/v1/accounts/{account_id}"
                   f"/widgets/{feature}/regenerate")
            try:
                _status, body = _call(url, token=token, payload={})
                count = len(body) if isinstance(body, list) else "?"
                print(f"  OK       {feature} ({count} widget(s))")
            except urllib.error.HTTPError as exc:
                detail = exc.read().decode()[:200]
                print(f"  FAILED   {feature} -> HTTP {exc.code} {detail}")
                failures.append((account_id, feature))
            except (OSError, ValueError) as exc:
                print(f"  FAILED   {feature} -> {exc}")
                failures.append((account_id, feature))
        print()

    if failures:
        print(f"{len(failures)} regeneration(s) failed:")
        for account_id, feature in failures:
            print(f"  {account_id}  {feature}")
        return 1
    print("All regenerations succeeded.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
