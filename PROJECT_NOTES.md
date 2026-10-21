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
as a footnote, never as an action item. The in-person list also keeps the last
7 days of missed items so a reopened proctored exam cannot fall off.

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

