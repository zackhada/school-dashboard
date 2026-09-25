# school-dashboard notes

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
