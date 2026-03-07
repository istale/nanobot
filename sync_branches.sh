#!/usr/bin/env bash
set -euo pipefail

MAIN_BRANCH="main"
CUSTOM_BRANCH="custom"
UPSTREAM_REMOTE="upstream"
ORIGIN_REMOTE="origin"

echo "[sync] repo: $(pwd)"

# Basic sanity checks
if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo "[error] Not inside a git repository." >&2
  exit 1
fi

if ! git remote get-url "$UPSTREAM_REMOTE" >/dev/null 2>&1; then
  echo "[error] Missing remote '$UPSTREAM_REMOTE'. Add it first:" >&2
  echo "       git remote add upstream <upstream-url>" >&2
  exit 1
fi

if ! git remote get-url "$ORIGIN_REMOTE" >/dev/null 2>&1; then
  echo "[error] Missing remote '$ORIGIN_REMOTE'." >&2
  exit 1
fi

# Ensure clean working tree
if [[ -n "$(git status --porcelain)" ]]; then
  echo "[error] Working tree is not clean. Commit/stash first." >&2
  exit 1
fi

# Ensure branches exist locally
if ! git show-ref --verify --quiet "refs/heads/$MAIN_BRANCH"; then
  echo "[error] Local branch '$MAIN_BRANCH' not found." >&2
  exit 1
fi
if ! git show-ref --verify --quiet "refs/heads/$CUSTOM_BRANCH"; then
  echo "[error] Local branch '$CUSTOM_BRANCH' not found." >&2
  exit 1
fi

echo "[sync] fetching $UPSTREAM_REMOTE ..."
git fetch "$UPSTREAM_REMOTE"

echo "[sync] updating $MAIN_BRANCH from $UPSTREAM_REMOTE/$MAIN_BRANCH ..."
git checkout "$MAIN_BRANCH"
git pull "$ORIGIN_REMOTE" "$MAIN_BRANCH"
git merge --ff-only "$UPSTREAM_REMOTE/$MAIN_BRANCH"
git push "$ORIGIN_REMOTE" "$MAIN_BRANCH"

echo "[sync] rebasing $CUSTOM_BRANCH onto $MAIN_BRANCH ..."
git checkout "$CUSTOM_BRANCH"
git rebase "$MAIN_BRANCH"
git push --force-with-lease "$ORIGIN_REMOTE" "$CUSTOM_BRANCH"

echo "[done] branches synced successfully."
