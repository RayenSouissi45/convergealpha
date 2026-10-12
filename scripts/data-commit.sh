#!/usr/bin/env bash
# Commit everything new in the data repo clone and push, rebasing on concurrent writers.
# Usage: scripts/data-commit.sh <data-dir> "<commit message>" [pathspec...]
# With pathspecs, only those paths are staged (works in sparse checkouts).
set -euo pipefail
dir="$1"
msg="$2"
shift 2
cd "$dir"
git config user.name "convergealpha-bot"
git config user.email "convergealpha-bot@users.noreply.github.com"
if [ "$#" -gt 0 ]; then
  git add --sparse -- "$@"
else
  git add -A
fi
if git diff --cached --quiet; then
  echo "data repo: nothing to commit"
  exit 0
fi
git commit -q -m "$msg"
for attempt in 1 2 3 4 5 6; do
  if git pull --rebase -q && git push -q; then
    echo "data repo: pushed ($(git rev-parse --short HEAD))"
    exit 0
  fi
  echo "data repo: push attempt $attempt failed; retrying"
  sleep $(( (RANDOM % 15) + 5 * attempt ))
done
echo "data repo: could not push after 6 attempts" >&2
exit 1
