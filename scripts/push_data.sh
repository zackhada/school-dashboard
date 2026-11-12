#!/bin/bash
# push_data.sh — the ONLY way a dashboard workflow commits to main.
#
# WHY THIS EXISTS (2026-11-12): every class runner dispatches a "status" event
# when it finishes, so several Dashboard update runs start within the same few
# seconds. Each one checked out main, rebuilt data/, committed and pushed. The
# first push won and every other run died with
#
#     ! [rejected]  HEAD -> main (fetch first)
#     error: failed to push some refs
#
# which GitHub turned into "Run failed: Dashboard update" email. That was 18 of
# the 20 dashboard failures on 2026-11-11/12. The data itself was never lost
# (each run rebuilds everything from the class repos), only the job failed.
#
# Contract:
#   * commits ONLY data/ (never the bot's checkout; see the 2026-11-11 revert bug)
#   * rebases onto origin and retries, so a concurrent writer is not an error
#   * a mirror write that still cannot land is a WARNING, not a failure. The
#     next run (every class run, plus the daily scrape) regenerates data/ from
#     the class repos, so nothing is lost by staying green. Failing the job here
#     only emails Zack about work that was already redone.
#
# Usage:  PUSH_TOKEN=... bash scripts/push_data.sh "dashboard update"
set -u

MSG="${1:-dashboard update $(date -u +%Y-%m-%d)}"
TOKEN="${PUSH_TOKEN:-}"
# With no token, keep the remote actions/checkout already configured (it holds
# the job credential). Never clobber it with a guessed URL.
if [ -n "$TOKEN" ]; then
  git remote set-url origin \
    "https://x-access-token:${TOKEN}@github.com/${GITHUB_REPOSITORY:-zackhada/school-dashboard}.git"
fi

git config user.name "dashboard-bot"
git config user.email "dashboard-bot@users.noreply.github.com"

# Rebase BEFORE committing so the usual case (someone else pushed a few seconds
# ago) is a clean fast-forward instead of a conflict on data/*.json.
git fetch origin main --quiet 2>/dev/null || true
git rebase --autostash origin/main >/dev/null 2>&1 || git rebase --abort >/dev/null 2>&1 || true

git add data
if git diff --cached --quiet; then
  echo "push_data: no data change"
  exit 0
fi
git commit -q -m "$MSG"

for i in 1 2 3 4 5 6 7 8; do
  if git push origin HEAD:main; then
    echo "push_data: pushed on attempt $i"
    exit 0
  fi
  echo "push_data: push rejected (attempt $i); rebasing on origin and retrying"
  sleep $((i * 2))
  git fetch origin main --quiet 2>/dev/null || true
  # Keep our regenerated data/ for any file both sides touched: this run just
  # rebuilt it from the class repos, so it is the newer truth.
  git rebase --autostash origin/main >/dev/null 2>&1 || {
    git rebase --abort >/dev/null 2>&1 || true
    git merge --no-edit -X ours origin/main >/dev/null 2>&1 || true
  }
done

echo "::warning::push_data: could not push data after 8 attempts; the next run regenerates data/ from the class repos. Not failing the job (that only emails Zack about a mirror write)."
exit 0
