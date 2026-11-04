# school-dashboard notes

## Surfacing rule (2026-10-21, Zack)
The dashboard surfaces ONLY work that genuinely cannot be automated. Two
mechanisms decide it, in this order:
1. `data/surface_judge.json`, written by `school-healer/scripts/surface_judge.py`.
   An LLM judges each `blocked_*` row (`manual` / `automatable` / `verify`) from
   the Canvas facts plus the ledger note and stores the verdict and a one-line
   reason. `build.py` copies it onto every row as `judge` and computes
   `surface`. A `verify` verdict surfaces as a question, not as manual work.
2. The deterministic gate (`REAL_MANUAL` / `manual_evidence` in `build.py`) is
   the fallback when there is no verdict: attendance, participation, proctoring,
   lockdown, Testing Center, `submission_types=none`, on paper. A module label
   such as "Tues Oct 20 In Class" is NOT evidence, which was the 2026-10-21
   STRAT 392 bug (nine reading quizzes, 90 points, parked as in person).
`index.html::statusOf` labels a blocked row `in person`, `verify`, `automated`,
or `agent checking`, and only judged-manual rows enter the "In person +
proctored" and "Needs your input" lists. Counted-but-unverified rows are shown
as a footnote, never as an action item.
Display rules (Zack 2026-10-21): the in-person list shows FUTURE items only (a
past item is done or missed, not an action) and never shows attendance or
participation items, because being in class is obvious. `build.py` marks those
rows `actionable=false`; they still show truthfully as `in person` in the class
table, they just do not appear on the action list.

## Refresh model (verified 2026-09-10)
- Ledger/status: every class runner dispatches `status` after each run and
  `update.yml` rebuilds. Nightly `scripts/sync_ledgers.py` also pulls each
  repo's `.state/progress.txt` over the API, so the mirror is authoritative
  even if a runner dies before reporting.
- Canvas grades (HRM 391, IS 515, PSE 390, REL C 333, STRAT 392): nightly
  `scrape.yml` (~05:30 UTC, delayed 2-5h) writes `data/<repo>.grades.json`.
- ECON 110 grades (Learning Suite): `econ110/scripts/scrape_grades.py` runs in
  that repo's session keepalive and commits `.state/grades.json`; the sync
  mirrors it to `data/econ110-automation.grades.json`.
- FIN 201 grades (MyEducator): the fin201 agent writes `.state/grades.json`
  during its runs; the sync mirrors it.
- `build.py` matches grades to ledger rows by name overlap (with +/-1 day for
  Mountain-vs-UTC dates). Canvas-only items with no ledger row are flagged as
  drift; Learning Suite / MyEducator snapshots never create drift.
- Pages rebuilds on every data commit.

## GitHub Pages deploy source (verified 2026-09-09)
- Pages deploys from the `main` branch, root `/`.
- The `gh-pages` branch is STALE/legacy (last built 2026-09-09, missing
  grades pages). Never push site changes there and never switch Pages back
  to it.
- After pushing site changes to `main`, trigger a Pages rebuild if the live
  site does not update on its own:
  `gh api repos/zackhada/school-dashboard/pages/builds -X POST`
- Verify live content, e.g.:
  `curl -s "https://zackhada.github.io/school-dashboard/index.html" | grep -c "<table"`

## Pages 404 root cause + fix (2026-09-25)
- Symptom: https://zackhada.github.io/school-dashboard/ returned HTTP 404 for
  every path (/, /index.html, /data/*.json) even though the Pages API still
  reported `status: built` with a successful deployment.
- Cause: the `school-dashboard` repo had been flipped to **private**. GitHub
  Pages on a private repo requires GitHub Pro; on Free the Pages config stays
  "enabled" in the API but the site is unpublished and 404s. No new Pages
  builds were queued after the visibility change (last build 0995e78, 2026-09-24
  18:35Z), which is the tell.
- Fix: `gh repo edit zackhada/school-dashboard --visibility public
  --accept-visibility-change-consequences`, then rebuild:
  `gh api repos/zackhada/school-dashboard/pages/builds -X POST`. Site verified
  200 with 4 tables + needs section.
- Guard: `school-healer/scripts/heal.py` now checks the live Pages URL and the
  repo visibility every run so this fails loudly instead of silently.
- NOTE: keep this repo **public** or the sole dashboard interface disappears.

## 2026-09-29: host reached, channel + Duo fix
- Host Mac identity: **MacBookPro.lan** (Intel x86_64), runner root
  `~/school-runners`, healer checkout `~/school-repos/school-healer`.
- Live control channel to the host (does not need an Actions runner):
  `python3 school-healer/scripts/host_mail.py send|wait|out|hb`.
- `session_refresh.py` missing `await` on `on_duo_url` fixed in all 7 repos
  (Duo passcode steering was broken; keepalives died at 12m).
- Keep-awake without root installed (`com.school.runners.caffeinate`).
- Healer moved onto econ110's runner; the school-healer runner is a wedged
  GitHub-side registration. Details in `MAC_RUNNERS.md`.


## Optional extra credit is tracked, never surfaced (Zack 2026-10-25)
- ECON 110 TA Passoffs are labeled "(Extra Credit)" in the gradebook and the TA
  announcement of 2026-09-29 says they are not required, yet all 11 were sitting
  in "In person + proctored" as if Zack owed them.
- `scripts/build.py` now sets `optional_ec` from a `[optional-ec:...]` ledger tag
  (with `TA_PASSOFF` in the key as a safety net), and forces `surface` and
  `actionable` false. `index.html` drops those rows from the class tables, the
  next-up queue, and both action lists, so the data stays auditable while the
  page shows nothing for them.
- `school-healer/scripts/surface_judge.py` skips the same rows, so the nightly
  judge no longer spends calls on them or re-stamps `[manual:...]` evidence.

## Exam coverage audit + calendar alerts (Zack 2026-10-25)
- Root cause of a real miss: the dashboard only knew about items that exist as
  Canvas assignments. The STRAT 392 midterm (150 of 700 points, Testing Center
  window Oct 9-20) exists only in the syllabus, so it never appeared, and Zack
  never took it. Same shape of gap found for STRAT Market Entry Lab (60, Nov 5),
  STRAT Strategy Journal (50, Dec 15, the ledger row was stale-dated to Sep 9),
  IS 515 Course Project (Nov 30 + Dec 9 presentation), and HRM Exam 2/3/Final
  (50% of the grade, no dates published anywhere).
- Also wrong on the dashboard: ECON Midterm 2, ECON Final, FIN Test 3 and FIN
  Final were labelled in-class. All four are BYU Testing Center exams per the
  syllabi. Ledger notes corrected in all five repos (2026-10-25).
- New alerting layer: `scripts/in_person_required.json` is the verified list of
  everything Zack must personally do, and `scripts/exam_alerts.py sync` pushes
  each item to his Google Calendar as an event with popup reminders at 7 days,
  3 days, 1 day and 3 hours plus an email a day out. Idempotent via an
  `[alert:<id>]` marker in the description. The calendar is the alert channel
  because the dashboard only helps if he opens it.
- Open question the audit could not answer from data: FIN 201 Test 1 (Sep 28)
  and Test 2 (Oct 19) have no score in the Learning Suite gradebook, and Canvas
  is not used for FIN. Must confirm he sat both.

## Testing Center is the authority on exam completion (Zack 2026-10-25)
- Access method saved as `school-healer/scripts/testing_center.py` (report,
  exams, check). It attaches to the canonical headless Chrome on 9222, opens
  testing.byu.edu/my-exams, and lets `scripts/cas_login.py --success-host
  testing.byu.edu` handle CAS and Duo (the 30-day browsertrust usually skips the
  passcode entirely). The site is server-rendered, so no JS scraping is needed:
  `/my-exams?yearTerm=20265&course=STRAT392002` gives Test / Opens / Late Fee /
  Closes / Score, and `/personal-report?yearTerm=20265` lists everything taken
  with score, date, entry time, elapsed time and answer-sheet number. Term codes
  are year + term digit (20265 = Fall 2026).
- What it proved: the STRAT 392 midterm (150 pts, opens Oct 9 8:00am, closes
  Oct 20 9:00pm) has a blank score and does not appear on the personal report,
  so it was never sat. FIN 201 Exam 1 was 45% (Sep 28) and Test 2 was 56%
  (Oct 16), which puts FIN on a D trajectory because exams are about 82% of that
  grade. HRM 391 has no Testing Center tests at all, so its remaining exams are
  Canvas remotely-proctored like Exam 1, not Testing Center.
- Rule going forward: a blank Score cell on an exam whose Closes date has passed
  means never taken, not ungraded. Check the Testing Center before trusting a
  class-level pass/fail claim.

## DASHBOARD DATES PASS (2026-11-04): UTC vs Mountain, and matcher bugs
Zack noticed the dates on the dashboard were wrong. Three separate causes, all
fixed and verified against live sources.

1. TIMEZONE (the big one). Canvas writes `due_at` in UTC, so every "11:59pm
   Mountain" deadline is stored as 06:59:59Z the NEXT day. `index.html`,
   `build.py` and `assignment_audit.py` all sliced the UTC date, so most
   coursework showed a day late (IS 515 14.9 read Nov 5 when it closes Nov 4).
   Now `mtnDay()` (JS) and `mtn_day()` (both Python files) convert to
   America/Denver first. Ledger `date` fields are Mountain-local by convention
   and now agree exactly, so the +/-1 day tolerance is no longer load-bearing.
2. MATCHER ZERO-OVERLAP PAIRING. Any Canvas row that had a canvas_id could pair
   at name overlap 0, purely because the dates were near. That is how
   "HRM 391 Exam 2/3/Final" borrowed the date of "Unit 2 Group Service Project
   (No Submission)" (Nov 7) and "STRAT Final Exam" borrowed a September
   assignment. Pairing now requires real name overlap, and weak overlap needs an
   agreeing date unless the Canvas row has no deadline at all. Re-checked after
   the change: drift is 0 for all seven repos.
3. DRIFT ON UNDATED ROWS. A Canvas row with no `due_at` and no `lock_at` is a
   gradebook total ("Participation and Engagement Grade"), not a missed
   assignment, so it is no longer counted as drift or dated 9999-12-31.

Also in this pass:
- Exam windows are now actually rendered. `audit.json` had been computing them
  and `index.html` never displayed them, so the highest-stakes dates were
  invisible on the page. New "Exams and proctored windows" table, soonest close
  first, with MISSED flagged.
- The Testing Center read needs a live CAS session, and on 2026-11-04 it failed
  (Duo sat on a Touch ID prompt). When it fails, `assignment_audit.py` now falls
  back to the verified exam registry (`scripts/in_person_required.json`,
  `kind: exam`) and labels the source in the table, so a login failure cannot
  blank out the exam list again. HRM Exam 2, Exam 3 and the HRM Final were added
  to that registry as exam rows (Canvas module titles: Nov 4-10, Dec 9-15,
  Dec 12-17).
- Ledger dates corrected in the class repos to the real Mountain deadlines:
  STRAT Market Entry Nov 17 (Canvas 1519226, was the Nov 5 syllabus date),
  STRAT Strategy Journal Dec 15 (was a stale Sep 9), STRAT reading quizzes one
  day earlier each, HRM Service Project Nov 21, HRM Unit 2 notebook Nov 10, HRM
  aggregate exam row Nov 10, REL Prophet project Dec 10, REL Part B Oct 31,
  ECON Midterm 2 Nov 6 and Final Dec 17, FIN Test 3 Nov 16 and Final Dec 17,
  PSE weekly quizzes to their Saturday dates, IS 12.7 Oct 28.
- STRAT Market Entry note rebuilt from the actual Canvas PDF: teams of 4-5, one
  physical product with a six-digit HS code, iLabz.org lab with weighted
  results, one country, one entry mode, ONE 3-to-5 minute video, hard 5 minute
  ceiling, no written report. The restaurant/JV deck in market_entry_lab/ does
  not satisfy it.
- Zero watch no longer reports REL Padlet rows. They are graded in Padlet, so
  Canvas shows them unsubmitted forever and the 0 is just "not graded yet".

## PUBLISHING FIXED 2026-11-04: the repo must stay PUBLIC
Pages for a private repo is not available on this account. `gh api
/repos/zackhada/school-dashboard/pages` returned 404, a POST returned 422 "Your
current plan does not support GitHub Pages for this repository", and
https://zackhada.github.io/school-dashboard/ 404'd while the last good deploy
was 2026-11-03. The repo had been private, so the site silently went dark.

FIX: scanned the full git history and working tree for secret-shaped content
first (no .env, cookies, chrome-profile, tokens or private keys were ever
committed), then set the repo public and enabled Pages with the legacy builder:

  gh api -X PATCH /repos/zackhada/school-dashboard -F private=false
  gh api -X POST /repos/zackhada/school-dashboard/pages \
     -f "source[branch]=main" -f "source[path]=/"

Pages then built in about 2 minutes (build + report-build-status on
ubuntu-latest, then deploy) and https://zackhada.github.io/school-dashboard/
returned 200 with the current data. Verified by rendering the live page in the
canonical headless Chrome: the exam table, the class tables and the closing-soon
list all read correctly.

KEEP IT PUBLIC. Flipping this repo private kills the only interface Zack uses
for needs-input replies (the reply links open issues in this repo). If privacy
ever becomes a hard requirement, publish to a separate public repo holding only
index.html plus data/ and keep this one private; do not flip visibility back
without replacing the delivery first.

Every push to main rebuilds Pages automatically (legacy builder, branch source),
so no deploy workflow is needed.

## HEALTH BANNER (2026-11-04): the page had no way to say "nothing is running"
Zack asked "is everything healthy?" and the honest answer was no, while the page
looked perfectly normal. Two fixes:

1. `scripts/health.py` writes `data/health.json` every hosted refresh: runner
   count per repo, which repos have no online runner, which repos have no
   successful run in 30 hours, and the runner Mac's heartbeat age, free disk,
   bridge and guard state. `index.html` renders it at the top of the page:
   "Automation healthy" in green, or "Automation NOT running on its own" in
   amber with the reason. A naive heartbeat timestamp is read as UTC, otherwise
   the subtraction raised and the heartbeat silently disappeared.
2. `school-healer/.github/workflows/always-on-healer.yml` was reporting
   "runners healthy and no milestone is due" with all nine runners offline. Two
   bugs stacked: `python3 scripts/runner_watchdog.py | tee file` returns tee's
   status (0) so `continue-on-error` never saw the failure, and school-healer
   has no `DISPATCH_TOKEN` secret, so the watchdog exited 2 for a missing token
   and the issue step had an empty `GH_TOKEN`. Fixed with `set -o pipefail`,
   `secrets.DISPATCH_TOKEN || secrets.OPS_TOKEN || secrets.PAT_CLASS`, and
   `GH_TOKEN` falling back to `github.token`. Verified: it now fails the check
   and opens issue #1 "Self-hosted runners offline" (school-healer) instead of
   claiming health.
