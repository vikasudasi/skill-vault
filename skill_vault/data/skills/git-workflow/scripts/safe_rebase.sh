#!/usr/bin/env bash
# safe_rebase.sh — Safely rebase current branch onto origin/main
#
# Usage: ./safe_rebase.sh
# Performs: fetch → stash → rebase → stash pop → verify status
# Fails early if the working tree is dirty and stashing fails.

set -euo pipefail

# ── Config ──────────────────────────────────────────────────────────────

readonly REMOTE="${REMOTE:-origin}"
readonly BASE_BRANCH="${BASE_BRANCH:-main}"
readonly BRANCH="$(git rev-parse --abbrev-ref HEAD)"

# ── Safety checks ───────────────────────────────────────────────────────

echo "→ Current branch: $BRANCH"

# Don't rebase main onto itself
if [[ "$BRANCH" == "$BASE_BRANCH" ]]; then
    echo "Already on $BASE_BRANCH; nothing to rebase."
    exit 0
fi

# Check remote exists
if ! git remote get-url "$REMOTE" >/dev/null 2>&1; then
    echo "ERROR: Remote '$REMOTE' not configured." >&2
    exit 1
fi

# ── Stash uncommitted changes ───────────────────────────────────────────

STASHED=false
if ! git diff-index --quiet HEAD --; then
    echo "→ Stashing uncommitted changes ..."
    git stash push -m "auto-stash before rebase onto $BASE_BRANCH"
    STASHED=true
fi

# ── Fetch + rebase ──────────────────────────────────────────────────────

echo "→ Fetching $REMOTE/$BASE_BRANCH ..."
git fetch "$REMOTE" "$BASE_BRANCH"

echo "→ Rebasing $BRANCH onto $REMOTE/$BASE_BRANCH ..."
if git rebase "$REMOTE/$BASE_BRANCH"; then
    echo "✓ Rebase succeeded."
else
    echo "✗ Rebase has conflicts. Resolve them, then run:" >&2
    echo "    git rebase --continue" >&2
    echo "    git push --force-with-lease $REMOTE $BRANCH" >&2
    if $STASHED; then
        echo "    git stash pop  # restore your uncommitted changes" >&2
    fi
    exit 1
fi

# ── Restore stashed changes ─────────────────────────────────────────────

if $STASHED; then
    echo "→ Restoring stashed changes ..."
    if git stash pop; then
        echo "✓ Stash restored."
    else
        echo "⚠ Stash pop had conflicts; resolve manually." >&2
    fi
fi

# ── Verification ────────────────────────────────────────────────────────

echo ""
echo "→ Status:"
git status --short
echo ""
echo "Ready to push. Run:"
echo "  git push --force-with-lease $REMOTE $BRANCH"