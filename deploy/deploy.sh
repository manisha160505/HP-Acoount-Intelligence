#!/usr/bin/env bash
# Deploy one commit of main to this VM.
#
#     deploy/deploy.sh <40-character commit sha>
#
# Builds the images first - the running containers keep serving if the build
# fails - then swaps them in and waits for the site to answer. If the new
# commit does not come up healthy, the previous commit is redeployed and the
# failed one is recorded so autodeploy.sh does not retry it every tick.
#
# Rolling back by hand is the same command with an older sha from main.
#
# Everything lives in functions and the last line calls main: bash has then
# parsed the whole script before `git checkout` replaces this file on disk.

set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STATE_DIR="${HP_DEPLOY_STATE:-$HOME/.hp-deploy}"
COMPOSE_FILE="docker-compose.prod.yml"
HEALTH_TIMEOUT="${HP_HEALTH_TIMEOUT:-240}"

log() { echo "$(date -u +%FT%TZ) deploy: $*"; }
die() { log "$*"; exit 1; }
compose() { docker compose -f "$COMPOSE_FILE" "$@"; }

site_address() {
    grep -E '^SITE_ADDRESS=' .env | tail -1 | cut -d= -f2- | tr -d '"'"'"' '
}

# The backend from inside its container, then both containers through Caddy
# on the public address - the path a user's request takes.
healthy() {
    local site deadline
    site="$(site_address)"
    deadline=$((SECONDS + HEALTH_TIMEOUT))
    while ((SECONDS < deadline)); do
        if compose exec -T backend python -c \
                "import urllib.request; urllib.request.urlopen('http://localhost:8000/health', timeout=5)" \
                >/dev/null 2>&1 \
            && curl -fsS -o /dev/null --max-time 10 "https://$site/health" \
            && curl -fsS -o /dev/null --max-time 20 "https://$site/"; then
            return 0
        fi
        sleep 5
    done
    log "not healthy after ${HEALTH_TIMEOUT}s"
    compose ps || true
    compose logs --tail 40 backend frontend || true
    return 1
}

# Chained with && rather than relying on set -e, which bash suspends inside a
# function called from an `if` - a failed build would otherwise carry on.
#
# --force because a checkout that fails part-way leaves some tracked files at
# the new commit's content, and a plain checkout of any commit then refuses to
# overwrite them. Nothing on the VM edits tracked files; .env and the data
# directories are untracked and untouched.
release() {
    git checkout --quiet --force --detach "$1" &&
        compose build &&
        compose up -d --remove-orphans &&
        healthy
}

main() {
    local sha="${1:-}" previous
    [[ "$sha" =~ ^[0-9a-f]{40}$ ]] || die "usage: deploy.sh <40-character commit sha>"

    mkdir -p "$STATE_DIR"
    exec 9>"$STATE_DIR/lock"
    flock -n 9 || die "another deploy is running"

    cd "$REPO"
    [[ -f .env ]] || die "$REPO/.env is missing - copy deploy/env.prod.example and fill it in"
    git fetch --quiet origin main
    git merge-base --is-ancestor "$sha" origin/main || die "$sha is not on origin/main"

    previous="$(git rev-parse HEAD)"
    log "deploying $sha (running $previous)"

    if release "$sha"; then
        echo "$sha" >"$STATE_DIR/deployed_sha"
        docker image prune -f >/dev/null || true
        log "deployed $sha"
        return 0
    fi

    echo "$sha" >"$STATE_DIR/failed_sha"
    log "deploy of $sha FAILED - rolling back to $previous"

    # Stop the failed commit's containers while its files are still checked
    # out. A container stuck restarting would otherwise outlive the checkout
    # that deletes a file it bind-mounts, and Docker recreates a missing mount
    # source as an empty root-owned directory - which git then cannot remove,
    # so every later checkout of that commit fails. Only when the checkout got
    # that far: if it did not, the running containers are still the previous
    # commit's and stay up.
    if [[ "$(git rev-parse HEAD)" == "$sha" ]]; then
        compose down --remove-orphans || true
    fi

    if release "$previous"; then
        log "rolled back to $previous"
    else
        log "ROLLBACK FAILED - the site may be down; check: docker compose -f $COMPOSE_FILE ps"
    fi
    return 1
}

main "$@"; exit $?
