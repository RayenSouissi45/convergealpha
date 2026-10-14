#!/usr/bin/env bash
# Append today's fingerprints (the build's commitment.json) to the public `ledger-heads` branch.
# GitHub records when each commit arrived, outside the app's control: a forecast or trade changed
# later would no longer match the fingerprint published that day.
# Usage: GH_TOKEN=... GITHUB_REPOSITORY=owner/repo scripts/publish-heads.sh site-data/commitment.json
set -euo pipefail
if [ ! -f "$1" ]; then
  echo "no commitment file: nothing to publish"
  exit 0
fi
src=$(realpath "$1")
tmp=$(mktemp -d)
cd "$tmp"
git init -q
git config user.name "convergealpha-bot"
git config user.email "convergealpha-bot@users.noreply.github.com"
git remote add origin "https://x-access-token:${GH_TOKEN}@github.com/${GITHUB_REPOSITORY}.git"
if git fetch -q --depth 1 origin ledger-heads 2>/dev/null; then
  git checkout -q -b ledger-heads FETCH_HEAD
else
  git checkout -q --orphan ledger-heads
  cat > README.md <<'TXT'
# Daily fingerprints

One line per trading day in `heads.jsonl`, appended by the daily workflow: the SHA-256 of that day's
forecasts and the seal (latest hash) of every record (signals, outcomes, paper trades, incidents,
experiments). GitHub's commit times show when each line was published.
TXT
fi
day=$(jq -r .date "$src")
if [ -f heads.jsonl ] && grep -q "\"date\":\"$day\"" heads.jsonl; then
  echo "fingerprints for $day already published"
  exit 0
fi
jq -c . "$src" >> heads.jsonl
git add -A
git commit -q -m "fingerprints $day"
for attempt in 1 2 3; do
  if git push -q origin ledger-heads; then
    echo "published fingerprints for $day"
    exit 0
  fi
  sleep $((attempt * 5))
  git pull -q --rebase origin ledger-heads || true
done
echo "::warning::could not publish the fingerprints for $day"
