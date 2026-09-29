#!/usr/bin/env python3
"""Create the accounts, upload their data, and wait for the features to build.

The 220 accounts are onboarded one at a time by hand today: create the account
in the admin UI, then upload about twenty-five files into it. This does the
whole wave - create, upload, trigger, wait, report - over the same HTTP API.

    python scripts/onboard_accounts.py --base-url http://localhost:8000 --check
    python scripts/onboard_accounts.py --base-url ... --accounts ACCENTURE_INC --dry-run
    python scripts/onboard_accounts.py --base-url ... --limit 1
    python scripts/onboard_accounts.py --base-url ... --accounts-in-parallel 2

Credentials come from the environment, never from an argument:

    HP_TOKEN                 a bearer token from a browser session
    HP_EMAIL + HP_PASSWORD   a dashboard login, exchanged for a token here

Both account creation and data upload are admin-only, so the login has to be
an administrator's.

What it uploads
---------------
Each account folder in the split carries `_manifest.json`, which records every
dataset with its row count. **Only datasets with rows are uploaded.** The
split's own `_MISSING.txt` says why, and it is the rule that governs this
script: "an empty registered dataset makes an extractor work from nothing,
whereas an unregistered one degrades cleanly."

Files go up with `defer_extraction=true` so a feature that reads seven datasets
is not rebuilt seven times while the account is still half loaded. Every
feature is triggered once, afterwards, when all of its inputs are in.

Where it runs
-------------
Wherever the backend it points at can see its own uploaded files - in practice
the VM, which is also the only host with the regeneration worker running. This
script queues work; something else has to drain the queue. Pointed at a backend
with `REGEN_WORKER_ENABLED` unset it will upload happily and then tell you that
nothing is building, rather than waiting for an hour on a queue nobody reads.

Stopping and resuming
---------------------
Every completed step is appended to a ledger (JSONL). A re-run skips what the
ledger already has. This matters most for filings: `compliance_filings` is a
multi-file dataset, so posting the same PDF twice adds a second copy rather
than replacing the first.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent
                       / "hp-backend" / "src"))

import hp_api  # noqa: E402
from app.observability import pipeline  # noqa: E402  - stdlib-only, no settings
from app.observability.context import get_account, get_feature  # noqa: E402

logger = logging.getLogger("onboard")


class _Prefixed(logging.Formatter):
    """`LEVEL    [account] feature  message`, as the backend prints it.

    The account and the feature are context vars that pipeline sets, not part
    of the message - so a line from this script and a line from the engine
    read the same way in the same log.
    """

    def format(self, record):
        account, feature = get_account(), get_feature()
        where = ("[%s]" % account) if account else ""
        if where and feature:
            where = "%s %s" % (where, feature)
        message = record.getMessage()
        if record.exc_info:
            message = message + "\n" + self.formatException(record.exc_info)
        return ("%-8s %s %s" % (record.levelname, where, message) if where
                else "%-8s %s" % (record.levelname, message))


DEFAULT_ROOT = "220 account split csv"
LEDGER_DEFAULT = "onboard_ledger.jsonl"

# The features the regeneration graph actually schedules. `content_messaging`
# is in FEATURE_MAPPINGS but left the graph on 28 Sep, so asking for it is a
# 404 per account.
FEATURES = (
    "executive_dashboard",
    "stakeholder_map",
    "tech_landscape",
    "solution_narrative_opportunity_map",
    "recent_news_signals",
    "intent_demand_signals",
    "objection_playbook",
    "content_studio",
    "message_evaluator",
    "strategy_chat",
)

# Node lifecycles, from services/regen/state.py. Repeated rather than imported:
# this script talks HTTP and must not need the backend package to run.
CURRENT, STALE, GENERATING, FAILED, NEVER = (
    "CURRENT", "STALE", "GENERATING", "FAILED", "NEVER_GENERATED")

# Two accounts is what production runs (docker-compose.prod.yml): "More would
# outrun the Vertex quota (429s)." On a 4 GB box the other limit is memory -
# each index build holds its workspace vectors and LightRAG's graph resident,
# and Mongo has already reserved 750 MB.
PARALLEL_DEFAULT = 2
PARALLEL_WARN = 2
PARALLEL_MAX = 4


# ---------------------------------------------------------------------------
# Reading the split - no network, no side effects, all of it testable
# ---------------------------------------------------------------------------

def dataset_registry_keys(repo_root: Path) -> set:
    """The dataset_keys the upload endpoint will accept.

    Parsed out of the schema rather than imported: importing it pulls in
    pydantic and the settings module, and this script is meant to run on a host
    that has neither.
    """
    source = (repo_root / "hp-backend" / "src" / "app" / "schemas"
              / "account_data.py")
    keys, inside = set(), False
    for line in source.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("DATASET_REGISTRY"):
            inside = True
            continue
        if inside:
            if stripped.startswith("}") and not stripped.startswith("},"):
                break
            if stripped.startswith('"') and stripped.endswith(": {"):
                keys.add(stripped.split('"')[1])
    return keys


class AccountPlan:
    """What one account needs, read from its folder. Nothing is sent yet."""

    def __init__(self, slug, folder, name="", datasets=None, filings=None,
                 skipped=None, problems=None, readiness=None):
        self.slug = slug
        self.folder = folder
        self.name = name
        self.datasets = datasets or []      # [(dataset_key, Path, rows)]
        self.filings = filings or []        # [Path] - one POST each
        self.skipped = skipped or []        # [(dataset_key, reason)]
        self.problems = problems or []      # [str] - hard, account is not run
        self.readiness = readiness or {}    # feature -> {status, missing[]}

    @property
    def ok(self) -> bool:
        return not self.problems

    @property
    def upload_count(self) -> int:
        return len(self.datasets) + len(self.filings)

    def features_missing_data(self) -> list:
        return [(f, r.get("missing") or [])
                for f, r in sorted(self.readiness.items())
                if (r.get("missing") or [])]


def read_plan(folder: Path, registry: set) -> AccountPlan:
    """One account's upload plan, with every problem found rather than raised.

    A missing file or an unknown dataset_key is a 400 at upload time, halfway
    through a wave. Both are cheaper to find here.
    """
    plan = AccountPlan(folder.name, folder)

    try:
        account = json.loads((folder / "_account.json").read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        plan.problems.append("_account.json unreadable: %s" % exc)
        return plan
    try:
        manifest = json.loads((folder / "_manifest.json").read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        plan.problems.append("_manifest.json unreadable: %s" % exc)
        return plan

    plan.name = str(account.get("name_for_upload") or "").strip()
    if not plan.name:
        plan.problems.append("_account.json has no name_for_upload")
    elif len(plan.name) > 100:
        plan.problems.append("name is %d characters; the API allows 100"
                             % len(plan.name))

    plan.readiness = manifest.get("readiness") or {}

    for key, info in sorted((manifest.get("datasets") or {}).items()):
        rows = info.get("rows") or 0
        if key not in registry:
            plan.problems.append("%s is not a dataset_key the API accepts" % key)
            continue
        if key == "compliance_filings":
            # A directory of PDFs, not a CSV, and multi-file: one POST each.
            pdfs = sorted((folder / "compliance_filings").glob("*.pdf"))
            if pdfs:
                plan.filings = pdfs
            else:
                plan.skipped.append((key, "no PDF in compliance_filings/"))
            continue
        if rows <= 0:
            plan.skipped.append((key, info.get("reason") or "no rows"))
            continue
        path = folder / ("%s.csv" % key)
        if not path.exists():
            plan.problems.append("%s: manifest says %d row(s), file is missing"
                                 % (key, rows))
            continue
        if path.stat().st_size == 0:
            plan.problems.append("%s: file is empty (0 bytes)" % key)
            continue
        plan.datasets.append((key, path, rows))

    if not plan.datasets and not plan.filings and not plan.problems:
        plan.problems.append("nothing to upload - every dataset is empty")
    return plan


def select_slugs(root: Path, wanted: list, limit: int) -> list:
    """Account folders to run, in a stable order."""
    folders = sorted(p.name for p in root.iterdir()
                     if p.is_dir() and not p.name.startswith(("_", "."))
                     and p.name != "__MACOSX")
    if wanted:
        asked = [w.strip() for part in wanted for w in part.split(",") if w.strip()]
        known = set(folders)
        missing = [a for a in asked if a not in known]
        if missing:
            sys.exit("no folder for: %s" % ", ".join(missing))
        folders = [f for f in folders if f in set(asked)]
    return folders[:limit] if limit else folders


# ---------------------------------------------------------------------------
# Knowing when an account has finished
# ---------------------------------------------------------------------------

def node_settled(entry: dict) -> bool:
    """Has this node stopped moving?

    Not "is it CURRENT": a FAILED node sits out a 1h/6h/24h backoff and a
    blocked one never retries until an input changes, so waiting for either is
    waiting forever. A queued-but-unstarted node reads STALE with a job
    attached, which is why the job is checked and not just the lifecycle.
    """
    if entry.get("job"):
        return False
    life = entry.get("lifecycle")
    if life in (CURRENT, FAILED):
        return True
    if life in (GENERATING, NEVER):
        return False
    # STALE: settled only when nothing is going to pick it up.
    return bool(entry.get("blocked")) or bool(entry.get("blocked_by"))


def node_outcome(entry: dict) -> str:
    """One word for the report."""
    life = entry.get("lifecycle")
    if life == CURRENT:
        return "degraded" if entry.get("quality") == "degraded" else "ok"
    if life == FAILED:
        return "failed"
    if entry.get("blocked") or entry.get("blocked_by"):
        return "blocked"
    return str(life or "unknown").lower()


def wanted_nodes(nodes: dict, skip_indexes: bool) -> dict:
    return {nid: e for nid, e in nodes.items()
            if not (skip_indexes and e.get("kind") == "index")}


# ---------------------------------------------------------------------------
# The ledger
# ---------------------------------------------------------------------------

class Ledger:
    """Append-only record of completed steps, so a re-run resumes.

    Filings are the reason this exists: `compliance_filings` is multi-file, so
    a second POST of the same PDF adds a copy rather than replacing it.
    """

    def __init__(self, path: Path, force: bool = False):
        self.path = path
        self.force = force
        self.done = set()
        self._lock = threading.Lock()
        if path.exists() and not force:
            for line in path.read_text(encoding="utf-8").splitlines():
                try:
                    row = json.loads(line)
                except ValueError:
                    continue
                if row.get("key"):
                    self.done.add(row["key"])

    def has(self, *parts) -> bool:
        return not self.force and "|".join(str(p) for p in parts) in self.done

    def add(self, *parts, **fields) -> None:
        key = "|".join(str(p) for p in parts)
        row = {"key": key, "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
        row.update(fields)
        with self._lock:
            self.done.add(key)
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")


# ---------------------------------------------------------------------------
# One account, end to end
# ---------------------------------------------------------------------------

class Wave:
    """Shared state for the run. One instance, many account threads."""

    def __init__(self, args, token: str):
        self.args = args
        self.token = token
        self._token_lock = threading.Lock()
        self._create_lock = threading.Lock()
        self.ledger = Ledger(Path(args.ledger), force=args.force)
        self.results = {}
        self._results_lock = threading.Lock()

    def auth(self) -> str:
        """The bearer token, renewed when it is close to lapsing.

        A wave runs longer than the 24h token, and there is no refresh
        endpoint - a renewal is a second login.
        """
        with self._token_lock:
            self.token = hp_api.renewed(self.args.base_url, self.token)
            return self.token

    def record(self, slug: str, outcome: str, detail: str = "") -> None:
        with self._results_lock:
            self.results[slug] = (outcome, detail)

    # -- the steps ---------------------------------------------------------

    def create(self, plan: AccountPlan) -> str:
        """The account id. Serialised: the uniqueness check has no index."""
        with self._create_lock:
            account_id, how = hp_api.find_or_create_account(
                self.args.base_url, self.auth(), plan.name, self.args.dry_run)
        pipeline.step("account", "%s (id=%s)" % (how, account_id or "-"))
        if account_id:
            self.ledger.add(plan.slug, "account", id=account_id, name=plan.name)
        return account_id

    def upload(self, plan: AccountPlan, account_id: str) -> int:
        """Every dataset with rows, then every filing PDF. Returns failures."""
        failed = 0
        url = "%s/api/v1/accounts/%s/data" % (self.args.base_url, account_id)

        for key, path, rows in plan.datasets:
            if self.ledger.has(plan.slug, "upload", key):
                pipeline.step("upload", "%-28s %s" % (path.name, "skipped (ledger)"))
                continue
            if self.args.dry_run:
                pipeline.step("upload", "%-28s %6d row(s)  would send"
                              % (path.name, rows))
                continue
            status, body = hp_api.api_upload(url, self.auth(), key, path)
            if status in (200, 201):
                pipeline.step("upload", "%-28s %6d row(s)  ok" % (path.name, rows))
                self.ledger.add(plan.slug, "upload", key,
                                file_id=(body or {}).get("id"))
            else:
                failed += 1
                detail = (body or {}).get("detail") or body
                pipeline.step("upload", "%-28s FAILED HTTP %s: %s"
                              % (path.name, status, str(detail)[:120]))
                logger.error("%s: upload of %s failed (HTTP %s): %s",
                             plan.name, key, status, detail)

        for pdf in plan.filings:
            if self.ledger.has(plan.slug, "filing", pdf.name):
                pipeline.step("filing", "%-28s %s" % (pdf.name[:28], "skipped (ledger)"))
                continue
            if self.args.dry_run:
                pipeline.step("filing", "%-28s would send" % pdf.name[:28])
                continue
            status, body = hp_api.api_upload(url, self.auth(),
                                             "compliance_filings", pdf)
            if status in (200, 201):
                pipeline.step("filing", "%-28s ok" % pdf.name[:28])
                self.ledger.add(plan.slug, "filing", pdf.name,
                                file_id=(body or {}).get("id"))
            else:
                failed += 1
                detail = (body or {}).get("detail") or body
                pipeline.step("filing", "%-28s FAILED HTTP %s: %s"
                              % (pdf.name[:28], status, str(detail)[:120]))
        return failed

    def trigger(self, account_id: str) -> int:
        """Queue every feature once. Returns the number of nodes queued."""
        queued, refused = 0, []
        for feature in FEATURES:
            if self.args.dry_run:
                continue
            url = ("%s/api/v1/accounts/%s/features/%s/regenerate"
                   % (self.args.base_url, account_id, feature))
            status, body = hp_api.api(url, self.auth(), payload={})
            if status in (200, 202):
                queued += len((body or {}).get("nodes") or [])
            else:
                refused.append("%s HTTP %s" % (feature, status))
        if refused:
            pipeline.step("trigger", "refused: %s" % "; ".join(refused))
        pipeline.step("trigger", "%d feature(s), %d node(s) queued"
                      % (len(FEATURES), queued))
        return queued

    def wait(self, plan: AccountPlan, account_id: str) -> dict:
        """Poll until every node has settled. Returns node id -> outcome."""
        url = ("%s/api/v1/accounts/%s/features/status"
               % (self.args.base_url, account_id))
        started = time.time()
        seen, reported = {}, set()
        moved_at = started

        while True:
            status, body = hp_api.api(url, self.auth())
            if status != 200 or not isinstance(body, dict):
                pipeline.step("wait", "status unavailable (HTTP %s)" % status)
                time.sleep(self.args.poll_seconds)
                if time.time() - started > self.args.account_timeout:
                    return seen
                continue

            nodes = wanted_nodes(body.get("nodes") or {}, self.args.skip_indexes)
            live = 0
            for nid, entry in sorted(nodes.items()):
                if node_settled(entry):
                    if nid not in reported:
                        outcome = node_outcome(entry)
                        seen[nid] = outcome
                        reported.add(nid)
                        moved_at = time.time()
                        extra = ""
                        if outcome == "failed":
                            err = entry.get("last_error") or {}
                            extra = "  %s - previous output kept" % err.get("code", "")
                        elif outcome == "blocked":
                            extra = "  waiting on %s" % ", ".join(
                                entry.get("blocked_by") or [])
                        pipeline.step("node", "%-28s %-9s %s"
                                      % (nid, outcome, extra.strip()))
                        self.ledger.add(plan.slug, "node", nid, outcome=outcome)
                else:
                    live += 1

            if not live:
                return seen

            # Nothing is draining the queue - say so rather than wait an hour.
            if (not reported and self.args.idle_timeout
                    and time.time() - moved_at > self.args.idle_timeout):
                pipeline.step("wait", "nothing has started in %ds - is the "
                                      "regeneration worker running on this host? "
                                      "(REGEN_WORKER_ENABLED=1)"
                              % self.args.idle_timeout)
                moved_at = time.time()

            if time.time() - started > self.args.account_timeout:
                pipeline.step("wait", "gave up after %.0fm with %d node(s) still "
                                      "working" % ((time.time() - started) / 60, live))
                return seen

            time.sleep(self.args.poll_seconds)

    # -- the whole account -------------------------------------------------

    def run(self, plan: AccountPlan) -> None:
        with pipeline.account_scope(plan.slug, label=plan.name):
            with pipeline.feature_scope("onboard"):
                try:
                    pipeline.step("preflight", "%d dataset(s), %d filing PDF(s), "
                                              "%d skipped as empty"
                                  % (len(plan.datasets), len(plan.filings),
                                     len(plan.skipped)))
                    account_id = self.create(plan)
                    failures = self.upload(plan, account_id)
                    if failures:
                        pipeline.guardrail(failures, "upload(s) failed")
                    if self.args.dry_run or not account_id:
                        pipeline.step("trigger", "%d feature(s) would be queued"
                                      % len(FEATURES))
                        self.record(plan.slug, "dry-run")
                        return

                    self.trigger(account_id)
                    outcomes = self.wait(plan, account_id)

                    bad = sorted(n for n, o in outcomes.items()
                                 if o in ("failed", "blocked"))
                    if bad:
                        self.record(plan.slug, "partial",
                                    "%d node(s) not built: %s"
                                    % (len(bad), ", ".join(bad)))
                    elif not outcomes:
                        self.record(plan.slug, "timeout", "no node settled")
                    else:
                        self.record(plan.slug, "ok", "%d node(s)" % len(outcomes))
                except Exception as exc:                        # noqa: BLE001
                    logger.exception("%s: onboarding failed", plan.name)
                    self.record(plan.slug, "error", repr(exc)[:200])


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

def print_check(plans: list) -> int:
    """The preflight table. Returns the number of accounts with a problem."""
    print("%-34s %6s %6s %8s  %s"
          % ("account", "files", "pdfs", "skipped", "problems"))
    print("-" * 96)
    bad = 0
    for plan in plans:
        problems = "; ".join(plan.problems) if plan.problems else ""
        if plan.problems:
            bad += 1
        print("%-34s %6d %6d %8d  %s"
              % (plan.slug[:34], len(plan.datasets), len(plan.filings),
                 len(plan.skipped), problems[:40]))

    print()
    print("%d account(s), %d with a problem" % (len(plans), bad))
    gaps = [(p, p.features_missing_data()) for p in plans]
    gaps = [(p, g) for p, g in gaps if g]
    if gaps:
        print()
        print("Features that will run without one of their datasets:")
        for plan, missing in gaps[:20]:
            for feature, keys in missing:
                print("  %-30s %-36s missing %s"
                      % (plan.slug[:30], feature, ", ".join(keys)))
        if len(gaps) > 20:
            print("  ... and %d more account(s)" % (len(gaps) - 20))
    return bad


def print_summary(wave: Wave, plans: list) -> int:
    print()
    print("=" * 72)
    counts = {}
    for slug, (outcome, detail) in sorted(wave.results.items()):
        counts[outcome] = counts.get(outcome, 0) + 1
        if outcome != "ok":
            print("  %-34s %-8s %s" % (slug[:34], outcome, detail))
    print("%d account(s): %s"
          % (len(plans), ", ".join("%d %s" % (n, k)
                                   for k, n in sorted(counts.items()))))
    return counts.get("ok", 0) != len(plans)


# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--base-url", default=os.getenv("HP_BASE_URL",
                                                        "http://localhost:8000"),
                        help="Backend to talk to (default $HP_BASE_URL)")
    parser.add_argument("--root", default=DEFAULT_ROOT,
                        help="The split folder (default %r)" % DEFAULT_ROOT)
    parser.add_argument("--accounts", action="append", default=[],
                        help="Folder name; repeat or comma-separate for more")
    parser.add_argument("--limit", type=int, default=0,
                        help="Only the first N accounts")
    parser.add_argument("--check", action="store_true",
                        help="Preflight only: read the folders, send nothing")
    parser.add_argument("--dry-run", action="store_true",
                        help="Create nothing and upload nothing; print the plan")
    parser.add_argument("--accounts-in-parallel", type=int,
                        default=int(os.getenv("ONBOARD_ACCOUNTS_PARALLEL",
                                              str(PARALLEL_DEFAULT))),
                        help="How many accounts in flight at once (default %d)"
                             % PARALLEL_DEFAULT)
    parser.add_argument("--skip-indexes", action="store_true",
                        help="Do not wait on the retrieval index nodes")
    parser.add_argument("--ledger", default=LEDGER_DEFAULT,
                        help="Resume file (default %r)" % LEDGER_DEFAULT)
    parser.add_argument("--force", action="store_true",
                        help="Ignore the ledger and re-send everything")
    parser.add_argument("--poll-seconds", type=int, default=15)
    parser.add_argument("--account-timeout", type=int, default=4 * 3600,
                        help="Give up on one account after this many seconds")
    parser.add_argument("--idle-timeout", type=int, default=120,
                        help="Warn when nothing has started in this long")
    args = parser.parse_args()

    os.environ.setdefault("LOG_FORMAT", "plain")
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(_Prefixed())
    logging.basicConfig(level=logging.INFO, handlers=[handler])

    repo_root = Path(__file__).resolve().parent.parent
    root = Path(args.root)
    if not root.is_absolute():
        root = repo_root / root
    if not root.is_dir():
        sys.exit("no split folder at %s" % root)

    registry = dataset_registry_keys(repo_root)
    if not registry:
        sys.exit("could not read DATASET_REGISTRY from the backend schema")

    slugs = select_slugs(root, args.accounts, args.limit)
    plans = [read_plan(root / slug, registry) for slug in slugs]

    if args.check:
        return 1 if print_check(plans) else 0

    runnable = [p for p in plans if p.ok]
    for plan in plans:
        if not plan.ok:
            logger.error("%s: %s", plan.slug, "; ".join(plan.problems))
    if not runnable:
        sys.exit("nothing to do - every selected account has a problem")

    parallel = max(1, min(args.accounts_in_parallel, PARALLEL_MAX))
    if args.accounts_in_parallel > PARALLEL_MAX:
        logger.warning("--accounts-in-parallel %d is above the ceiling of %d; "
                       "using %d", args.accounts_in_parallel, PARALLEL_MAX, parallel)
    elif parallel > PARALLEL_WARN:
        logger.warning("%d accounts in parallel is above what production runs "
                       "(%d). Expect 429s from the model, and memory pressure "
                       "while the retrieval indexes build.",
                       parallel, PARALLEL_WARN)

    token = "" if args.dry_run else hp_api.api_token(args.base_url)
    if args.dry_run:
        token = os.getenv("HP_TOKEN", "")
    wave = Wave(args, token)

    print("%d account(s), %d in parallel, %s"
          % (len(runnable), parallel,
             "DRY RUN - nothing will be sent" if args.dry_run else args.base_url))
    started = time.time()
    if parallel == 1:
        for plan in runnable:
            wave.run(plan)
    else:
        with ThreadPoolExecutor(max_workers=parallel) as pool:
            list(pool.map(wave.run, runnable))
    print("finished in %.0fm" % ((time.time() - started) / 60))
    return print_summary(wave, runnable)


if __name__ == "__main__":
    sys.exit(main())
