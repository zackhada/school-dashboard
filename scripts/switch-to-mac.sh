#!/bin/bash
# switch-to-mac.sh — run on the machine holding these repo checkouts AFTER
# setup-mac-runners.sh has registered the spare-Mac runners.
#   1. Verifies every repo reports an online self-hosted runner.
#   2. Uncomments the schedule block in *-selfhosted.yml and commits.
#   3. Disables the cloud (ubuntu) daily + keepalive workflows.
# Existing cloud workflows are DISABLED, not deleted, so rollback is one click.
# Rollback: gh workflow enable daily.yml --repo ... (per repo), re-comment schedules.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
REPOS="econ110 fin201 hrm391 is515 pse390 rel-c-333 strat392"

echo "--- 1/3 checking Mac runners are online ---"
for R in $REPOS; do
  ONLINE=$(gh api "repos/zackhada/${R}-automation/actions/runners" -q '[.runners[] | select(.status=="online")] | length')
  if [ "$ONLINE" -lt 1 ]; then
    echo "FAIL: zackhada/${R}-automation has no online runner. Run setup-mac-runners.sh on the spare Mac first."
    exit 1
  fi
  echo "ok: ${R} ($ONLINE online)"
done

echo "--- 2/3 activating self-hosted schedules ---"
for R in $REPOS; do
  D="$ROOT/$R"
  for F in "$D/.github/workflows/daily-selfhosted.yml" "$D/.github/workflows/session-keepalive-selfhosted.yml"; do
    # Uncomment the DISABLED-FOR-MAC schedule block:
    #   "  # schedule:  # DISABLED-FOR-MAC" -> "  schedule:"
    #   "    # - cron: ..."               -> "    - cron: ..."
    #   "    # # comment"                 -> "    # comment"
    python3 - "$F" <<'PYEOF'
import re, sys
p = sys.argv[1]
lines = open(p).read().splitlines(keepends=True)
out = []
for ln in lines:
    if '# DISABLED-FOR-MAC' in ln:
        out.append(re.sub(r'^(\s*)#\s*schedule:', r'\1schedule:', ln).split('  # DISABLED')[0] + '\n')
    elif re.match(r'^\s+# - cron:', ln):
        out.append(re.sub(r'^(\s+)# (- cron:)', r'\1\2', ln))
    elif re.match(r'^\s+# # ', ln):
        out.append(re.sub(r'^(\s+)# (# )', r'\1\2', ln, count=1))
    else:
        out.append(ln)
open(p, 'w').writelines(out)
print(f'activated {p}')
PYEOF
  done
  (cd "$D" && git add .github/workflows/daily-selfhosted.yml .github/workflows/session-keepalive-selfhosted.yml \
    && git commit -m "infra: activate self-hosted Mac schedules" \
    && git push origin HEAD)
done

echo "--- 3/3 disabling cloud (ubuntu) workflows ---"
for R in $REPOS; do
  gh workflow disable daily.yml --repo "zackhada/${R}-automation"
  gh workflow disable session-keepalive.yml --repo "zackhada/${R}-automation"
  echo "disabled cloud workflows for ${R}"
done

echo
echo "DONE. All 7 classes now run on the spare Mac. Cloud workflows are disabled (not deleted)."
echo "Watch the first evening: gh run list -R zackhada/econ110-automation --limit 5"
