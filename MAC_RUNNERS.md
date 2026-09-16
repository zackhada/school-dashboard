# Self-Hosted Mac Runner Setup

**Goal:** move all 7 class runners off GitHub-hosted VMs ($0.006/min, 3,000 min
cap hit Sep 2026) onto a spare Mac. GitHub stays as scheduler; all compute
happens on the Mac. Self-hosted runners currently cost $0 extra.

**Status 2026-09-16:** duplicate workflows (`daily-selfhosted.yml`,
`session-keepalive-selfhosted.yml`) are pushed to all 7 class repos with
schedules DISABLED. Cloud workflows untouched and still live. Nothing runs on
the Mac until step 3 below.

## Step 1: prep the spare Mac

1. Install Homebrew, then: `brew install gh node python3`
2. Install Google Chrome (normal .dmg install).
3. `gh auth login` (same zackhada account).
4. Prevent sleep during run windows (5-10pm MT): System Settings > Energy >
   Prevent automatic sleeping, or `sudo pmset -c disablesleep 1`.

## Step 2: install the 7 runners

Get `scripts/setup-mac-runners.sh` from this repo onto the spare Mac, then:

```bash
bash setup-mac-runners.sh
```

It registers one runner per repo (`mac-econ110`, `mac-fin201`, ...) under
`~/school-runners/` and installs each as a launchd service (survives reboot).
~10 minutes. Verify: `gh api repos/zackhada/econ110-automation/actions/runners`.

To remove later: `~/school-runners/remove-mac-runners.sh` (written by setup).

## Step 3: flip the switch (main machine)

```bash
bash scripts/switch-to-mac.sh
```

It (1) refuses unless every repo shows an online runner, (2) uncomments the
schedules in the `*-selfhosted.yml` files and pushes, (3) DISABLES the cloud
`daily.yml` + `session-keepalive.yml` (disable, not delete).

## Rollback

Cloud workflows are disabled, not deleted: re-enable in the Actions tab or via
`gh workflow enable daily.yml -R zackhada/<repo>-automation`, then re-comment
the self-hosted schedules.

## Notes

- Runners are repo-scoped, so plain `runs-on: self-hosted` routes correctly.
- Keepalive Chrome steps use the macOS Chrome path (`/Applications/Google
  Chrome.app/...`) with a `brew` fallback; the `apt-get` line only exists in
  the cloud files.
- First-night watch: `gh run list -R zackhada/econ110-automation --limit 5`.
- `git pull` each class checkout before anything else runs; local checkouts lag
  the cloud (ECON ledger was reconciled 2026-09-16, others not yet verified).
