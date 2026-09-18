# Self-Hosted Mac Runner Setup

**Goal:** move all 7 class runners off GitHub-hosted VMs ($0.006/min, 3,000 min
cap hit Sep 2026) onto a spare Mac. GitHub stays as scheduler; all compute
happens on the Mac. Self-hosted runners currently cost $0 extra.

**Status 2026-09-17: LIVE on this Mac (Intel x86_64, macOS 15.7.7).** All 7
runners (`mac-econ110` ... `mac-strat392`, v2.337.0) installed under
`~/school-runners/` as launchd services and online. Self-hosted schedules
active (daily 3x UTC crons + keepalive 1x cron per repo); cloud `daily.yml` +
`session-keepalive.yml` DISABLED (not deleted) in all 7 repos. Session
keepalive verified green on all 7 local runners 2026-09-17 (ECON 5m18s, others
~6min). Stay-awake: `com.school.runners.caffeinate` LaunchAgent runs
`caffeinate -dimsu` (KeepAlive + RunAtLoad); `pmset` confirms sleep prevented.
Canonical local checkouts for git ops: `~/school-repos/<class>` (the old
Desktop checkouts lost TCC approval for background shells; use
`~/school-repos/<class>`).

**Status 2026-09-17 late: auth bootstrap complete.** All 7 runner Chrome
profiles verified `ok:true, seeded` with Duo remember-device trust accepted
(rel-c-333, strat392, pse390, is515, fin201, hrm391, econ110). No Duo taps
should be needed for ~30 days; the nightly keepalive holds sessions warm and
nudges via Telegram if a trust ever lapses. Fixes landed in all 7 repos:
unique CDP debug ports 9230-9236 (concurrent keepalives shared 9222 and drove
each other's browsers), Duo Universal Prompt steering (headless has no Touch
ID: Other options -> Duo Push -> Yes this is my device), `REFRESH_RC`
tool-cache path, jammed keepalive cron lines, and no session stamp on
all-visit-fail.

**Prior status 2026-09-16:** duplicate workflows (`daily-selfhosted.yml`,
`session-keepalive-selfhosted.yml`) were pushed to all 7 class repos with
schedules DISABLED. Cloud workflows untouched and still live. Nothing ran on
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
- `setup-mac-runners.sh` auto-detects arch (`osx-arm64` vs `osx-x64`) and uses
  `gh api -X POST` for registration tokens (GET 404s). Runner v2.337.0.
- `switch-to-mac.sh` accepts class checkouts beside or under school-dashboard.
- Self-hosted fixes applied 2026-09-17 (all 7 repos): job-level
  `AGENT_TOOLSDIRECTORY: ~/school-runners/_tools` (lets setup-node work);
  keepalive uses system python3 + `pip --break-system-packages` because
  `setup-python@v5` hardcodes `/Users/runner` on macOS. Keepalive keep the
  jammed `# - cron:` single-line form out: one repo family had the cron
  appended to a prose comment, which uncommented to an empty `schedule:` and
  422s dispatches; fixed to a real `- cron:` entry.
- Keepalive Chrome steps use the macOS Chrome path (`/Applications/Google
  Chrome.app/...`) with a `brew` fallback; the `apt-get` line only exists in
  the cloud files.
- First-night watch: `gh run list -R zackhada/econ110-automation --limit 5`.
- `git pull` each class checkout before anything else runs; local checkouts lag
  the cloud (ECON ledger was reconciled 2026-09-16, others not yet verified).
- Adversarial audit 2026-09-18 (4 subagents: runners, LLM limits, dashboard
  pipeline, machine durability). Landed in all 7 class repos: answer.yml
  retargeted to live daily-selfhosted.yml with force_key (old target 422d and
  destroyed replies); IS515 daily off setup-python/apt-get onto system python
  + macOS Chrome check; excel fallback Chrome uses isolated per-process
  profile; keepalive fails red + pages Telegram on bad REFRESH_RC/GRADES_RC;
  stable `-v1` profile cache keys (back-compat restore prefix) + Chrome
  teardown + per-port logs + pre-save prune of regenerable bulk;
  run_in_progress self-reaps after 3h. Still needs Zack (sudo/money/decisions):
  `sudo pmset -c sleep 0`, disable macOS auto-install until 30Gi free, lid-OPEN
  policy (lid-close sleeps despite caffeinate), reboot requires GUI login
  (FileVault, no auto-login), free 20Gi+ (Messages 20G, dup dmgs, old
  projects), OpenRouter key tier check (`GET /api/v1/key`, fund $10+ if free
  tier; 7 concurrent agents share one account quota), UPS. Deferred (flagged,
  not changed): Telegram single-poller, stamp-key validation, needs_user
  lifecycle, agent-side guard removal, dashboard staleness banners, healer
  self-hosted coverage, update.yml push-race retry.
