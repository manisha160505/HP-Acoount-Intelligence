#!/usr/bin/env bash
# Deploy the tip of origin/main once GitHub CI has passed on it.
#
# Run by hp-autodeploy.timer every two minutes (deploy/install-autodeploy.sh
# sets that up). Pull-based on purpose: the VM needs no inbound SSH from
# GitHub and the repository needs no deploy secrets - it is public, so the
# code and the CI results can both be read without credentials.
#
# A commit is deployed only when every GitHub Actions check run on it has
# completed and none failed. A commit whose CI failed, or whose deploy failed
# and was rolled back, is not retried; the next merge to main moves on.
#
#     journalctl -u hp-autodeploy -f        # watch it
#     deploy/deploy.sh <sha>                # deploy or roll back by hand

set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STATE_DIR="${HP_DEPLOY_STATE:-$HOME/.hp-deploy}"

log() { echo "$(date -u +%FT%TZ) autodeploy: $*"; }

github_repo() {
    git -C "$REPO" remote get-url origin | sed -E 's#^.*github\.com[:/]##; s#\.git$##'
}

# success | pending | failure, from the check runs GitHub Actions left on the commit.
ci_status() {
    curl -fsS --max-time 20 -H "Accept: application/vnd.github+json" \
        "https://api.github.com/repos/$(github_repo)/commits/$1/check-runs?per_page=100" |
        python3 -c '
import json, sys
runs = [r for r in json.load(sys.stdin).get("check_runs", [])
        if (r.get("app") or {}).get("slug") == "github-actions"]
if not runs or any(r["status"] != "completed" for r in runs):
    print("pending")
elif all(r["conclusion"] in ("success", "skipped", "neutral") for r in runs):
    print("success")
else:
    print("failure")
'
}

main() {
    local tip status
    mkdir -p "$STATE_DIR"
    tip="$(git -C "$REPO" ls-remote origin refs/heads/main | cut -f1)"
    [[ "$tip" =~ ^[0-9a-f]{40}$ ]] || { log "could not read origin/main"; return 1; }

    [[ "$tip" == "$(cat "$STATE_DIR/deployed_sha" 2>/dev/null)" ]] && return 0
    [[ "$tip" == "$(cat "$STATE_DIR/failed_sha" 2>/dev/null)" ]] && return 0

    status="$(ci_status "$tip")" || { log "could not read CI status for $tip"; return 1; }
    case "$status" in
        success) exec "$REPO/deploy/deploy.sh" "$tip" ;;
        pending) log "waiting for CI on $tip" ;;
        failure)
            log "CI failed on $tip - not deploying it"
            echo "$tip" >"$STATE_DIR/failed_sha"
            ;;
    esac
}

main "$@"; exit $?
