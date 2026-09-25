#!/bin/sh
# Points git at the repo's committed hooks. Run once per clone:
#
#   ./scripts/install-hooks.sh
#
# core.hooksPath is used rather than copying files into .git/hooks so that a
# change to a hook reaches everyone on the next pull instead of needing a
# reinstall.

set -e
REPO_ROOT=$(git rev-parse --show-toplevel)

# The code-review-graph pre-commit hook lives in .git/hooks and would be
# bypassed by redirecting hooksPath, so it is carried across if present.
EXISTING="$REPO_ROOT/.git/hooks/pre-commit"
TARGET="$REPO_ROOT/scripts/git-hooks/pre-commit"
if [ -f "$EXISTING" ] && [ ! -f "$TARGET" ]; then
    cp "$EXISTING" "$TARGET"
    chmod +x "$TARGET"
    echo "Carried the existing pre-commit hook over to scripts/git-hooks/."
fi

git config core.hooksPath scripts/git-hooks
chmod +x "$REPO_ROOT"/scripts/git-hooks/* 2>/dev/null || true

echo "Hooks installed. A push to main is now refused, and a push requires a"
echo "clean backend lint."
echo ""
echo "The hook is a local convenience and can be skipped with --no-verify."
echo "Only GitHub branch protection enforces this for everyone - the repo owner"
echo "sets that up once; see project-documentation/07_Internal_Generated/Engineering/branch-protection.md."
echo ""
echo "Disable with: git config --unset core.hooksPath"
