#!/bin/bash
# setup-mac-runners.sh — run ONCE on the spare Mac.
# Registers one self-hosted GitHub Actions runner per class repo and installs
# each as a launchd service so jobs run even after reboot.
#
# Prerequisites on the spare Mac:
#   1. Install Homebrew + packages:  brew install gh node python3
#   2. Install Google Chrome (normal .dmg install is fine).
#   3. Authenticate:  gh auth login   (same zackhada account)
#   4. Keep this Mac awake: System Settings > Energy > Prevent automatic sleeping,
#      or run:  sudo pmset -c disablesleep 1
#
# Usage:  bash setup-mac-runners.sh
# To remove later: ./remove-mac-runners.sh (written by this script).

set -euo pipefail

REPOS="econ110 fin201 hrm391 is515 pse390 rel-c-333 strat392"
BASE="$HOME/school-runners"
RUNNER_VERSION="2.329.0"

mkdir -p "$BASE"

for R in $REPOS; do
  REPO="zackhada/${R}-automation"
  DIR="$BASE/$R"
  echo "=== $REPO ==="
  mkdir -p "$DIR"
  cd "$DIR"
  if [ ! -f ./run.sh ]; then
    curl -sSLo actions-runner.tar.gz \
      "https://github.com/actions/runner/releases/download/v${RUNNER_VERSION}/actions-runner-osx-arm64-${RUNNER_VERSION}.tar.gz"
    tar xzf actions-runner.tar.gz
    rm -f actions-runner.tar.gz
  fi
  if [ ! -f .runner ]; then
    TOKEN=$(gh api "repos/${REPO}/actions/runners/registration-token" -q .token)
    ./config.sh --unattended --url "https://github.com/${REPO}" \
      --token "$TOKEN" --name "mac-${R}" --labels self-hosted,mac \
      --work "_work" --replace
  else
    echo "already configured, skipping config."
  fi
  ./svc.sh install 2>/dev/null || true
  ./svc.sh start
  echo "runner mac-${R} installed + started."
done

cat > "$BASE/remove-mac-runners.sh" <<'EOF'
#!/bin/bash
# Stops + unregisters all school runners (run on the spare Mac).
set -euo pipefail
for D in "$HOME"/school-runners/*/; do
  [ -f "$D/svc.sh" ] || continue
  cd "$D"
  ./svc.sh stop 2>/dev/null || true
  ./svc.sh uninstall 2>/dev/null || true
  TOKEN=$(gh api "repos/zackhada/$(basename $D)-automation/actions/runners/registration-token" -q .token)
  ./config.sh remove --unattended --token "$TOKEN" || true
  echo "removed $(basename $D)"
done
EOF
chmod +x "$BASE/remove-mac-runners.sh"

echo
echo "ALL RUNNERS UP. Verify at: gh api repos/zackhada/econ110-automation/actions/runners -q '.runners[].name'"
echo "Next: on your main machine, run scripts/switch-to-mac.sh to move schedules over."
