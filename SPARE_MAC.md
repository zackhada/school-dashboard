# Spare-Mac Portability: run the school agent on a second Mac

**Why:** everything that completes coursework runs on self-hosted GitHub
Actions runners installed on Zack's Mac. If that Mac dies, sleeps, or is
unavailable, assignments stop. This document is the exact checklist to stand
the whole pipeline up on a spare Mac.

**Architecture (what actually has to exist on the spare Mac):**
```
GitHub (schedules + state)  ->  self-hosted runner (launchd)  ->  opencode CLI
                                                                    |
                            Chrome profile (cookies)  <-----------+---> CAS/Duo
                            chat.db (Duo SMS)         <-----------+
                            OneDrive/SharePoint       <-----------+
```
The Mac is only compute + the auth bridges. GitHub keeps the schedule, the
secrets, and the dashboard. No code changes are needed to move; only host
setup plus two synced state blobs (Chrome profile, `.env` files).

## Host prerequisites (spare Mac)

1. `brew install gh node python3`, install Google Chrome (.dmg).
2. `gh auth login` as **zackhada** (needs a PAT-classic with `repo` +
   `workflow` scopes for registration tokens + secrets).
3. Keep it awake: System Settings > Energy > "Prevent automatic sleeping when
   the display is off", and `sudo pmset -c disablesleep 1`.
4. Confirm it can reach `github.com`, `byu.instructure.com`,
   `learningsuite.byu.edu`, `byu-my.sharepoint.com`, `app.myeducator.com`.

## The four Mac-specific dependencies (each has to be recreated)

### 1. Self-hosted runners
`bash scripts/setup-mac-runners.sh` (registers `mac-<class>` for the 7 class
repos; ~10 min). Verify: `gh api repos/zackhada/econ110-automation/actions/runners`.
Then flip schedules with `bash scripts/switch-to-mac.sh` (refuses unless all 7
runners show online). See `school-dashboard/MAC_RUNNERS.md` for full detail.

**Arch note:** the script must fetch the runner build matching the Mac
(`osx-arm64` for Apple Silicon, `osx-x64` for Intel). It auto-detects now;
older copies hard-coded `osx-arm64`. Confirm with `uname -m` first.

### 2. Chrome profile (the SSO cache)
The whole no-login design depends on the cached Chrome profile. Copy it from
the primary Mac to the same path on the spare:

```bash
# Path on BOTH Macs:
/Users/zackhada/.cache/chrome-devtools-mcp/chrome-profile   (~2.6 GB)

# On the PRIMARY, close the canonical Chrome, then:
rsync -a --delete \
  "$HOME/.cache/chrome-devtools-mcp/chrome-profile/" \
  spare.local:"$HOME/.cache/chrome-devtools-mcp/chrome-profile/"
```

It holds CAS TGC + JSESSIONID (cas.byu.edu), Shibboleth mellon-cookie, Duo
~30-day device trust, Microsoft ESTSAUTHPERSISTENT, Canvas canvas_session, and
the M365/Excel session. **Never** start a fresh sign-in flow on the spare if
the profile is copied; a second sign-in is a failure. Canary check after copy:
`bash school-healer/scripts/...` or the sqlite canary in `AGENTS.md`.

### 3. Duo SMS passcode reader (`chat.db`)
`scripts/read_sms_code.py` reads `~/Library/Messages/chat.db` for the Duo text
passcode. On the spare Mac:
- Sign into the **same Apple ID** in Messages, and enable
  **Settings > Messages > Text Message Forwarding** to the spare Mac (iPhone).
- Confirm the Duo text lands: `sqlite3 ~/Library/Messages/chat.db ...`.
- The reader needs Full Disk Access for the process (Terminal / the runner
  service): System Settings > Privacy & Security > Full Disk Access.
- If the code cannot be read, that is a bridge bug to fix, never a request to
  Zack (global rule). Steer Duo to "Other options -> Text message passcode".

### 4. Cloud secrets (no Mac file needed)
All 7 class repos carry identical GitHub secrets: `OPENROUTER_API_KEY`,
`ANTHROPIC_API_KEY`, `BYU_NETID`, `BYU_PASSWORD`, `CANVAS_TOKEN`,
`DASHBOARD_TOKEN`, `DISPATCH_TOKEN`, `TELEGRAM_*`, `GMAIL_SMS_CREDS`.
Nothing to copy by hand. Local `.env` files exist only for the MCOM/econ
tooling; recreate from `mcom/.env` on the spare if you run those locally.

## State that must be in sync (else double-submits / stale cookies)

- `.state/` in each repo is committed and pulled before every run, so the
  ledger + last_run_ts follow automatically. **Never run the local Mac agent
  and the spare at the same time** for the same repo; the 24h cadence gate
  lives in the ledger but two live browsers on two profiles can both submit.
- The SMS bridge (`~/.sms-watch.py`, parking) is NOT part of this pipeline.
- The dashboard is GitHub-hosted and needs nothing from the Mac.

## Handoff runbook (primary -> spare)

1. On the spare: complete host prerequisites 1-4 above.
2. Copy the Chrome profile (step 2) and confirm the canary cookies exist.
3. Enable Text Message Forwarding + Full Disk Access (step 3); send a test
   Duo text and confirm `read_sms_code.py` returns it.
4. `bash scripts/setup-mac-runners.sh` on the spare; verify 7 runners online.
5. On the PRIMARY: disable its runners (`~/school-runners/remove-mac-runners.sh`)
   so only one machine is live.
6. Run `scripts/switch-to-mac.sh` if schedules need re-pointing; otherwise the
   existing self-hosted crons follow whichever runner is online.
7. Trigger one manual run per repo and watch: `gh run list -R
   zackhada/<repo>-automation --limit 3`.
8. Re-run the canary after the first successful run and note it in
   `PROJECT_NOTES.md`.

## Known gaps / TODO
- The Chrome profile copy is manual (2.6 GB, must be done with Chrome closed).
- `pmset` disablesleep needs sudo; the runner service runs in the user session.
- A reboot requires a GUI login (FileVault, no auto-login); the spare must be
  logged in for launchd user services to run.
- OpenRouter quota is shared across 7 concurrent agents; verify the key tier
  (`GET /api/v1/key`) before running two machines' worth of agents.
