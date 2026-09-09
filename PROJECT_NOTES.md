# school-dashboard notes

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
