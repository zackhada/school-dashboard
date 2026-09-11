#!/usr/bin/env python3
"""Sync the dashboard ledger mirrors directly from the class repos.

Pulls each repo's committed `.state/progress.txt` over the GitHub API and
writes `data/<repo>.json` (key/status/date/note), independent of whether a
runner's "Report to dashboard" step fired. Also mirrors `.state/grades.json`
(when a runner publishes one, e.g. Learning Suite / MyEducator) to
`data/<repo>.grades.json`.

Docs: `.state/needs_user` (free text parked when a runner waits on Zack,
e.g. PSE ethics public-post URL, REL video DONE) is mirrored to
`data/<repo>.needs.json` so build.py can flag the matching ledger row.
Statuses alone cannot express this: parked rows stay `pending`.

Env: DISPATCH_TOKEN (preferred; has read access to the private class repos),
falling back to GITHUB_TOKEN / GH_SYNC_TOKEN. Without a token it exits 0.
"""
import base64
import json
import os
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
REPOS = ["hrm391-automation", "strat392-automation", "rel-c-333-automation",
         "pse390-automation", "fin201-automation", "is515-automation",
         "econ110-automation"]
TOKEN = (os.environ.get("DISPATCH_TOKEN") or os.environ.get("GH_SYNC_TOKEN")
         or os.environ.get("GITHUB_TOKEN") or "")
HEADERS = {"Accept": "application/vnd.github+json",
           "User-Agent": "school-dashboard-sync"}
if TOKEN:
    HEADERS["Authorization"] = "Bearer " + TOKEN


def get_file(repo, path):
    url = ("https://api.github.com/repos/zackhada/%s/contents/%s?ref=main"
           % (repo, path))
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            d = json.load(r)
        return base64.b64decode(d["content"]).decode("utf-8", "replace")
    except Exception:
        return None


def parse_ledger(text):
    rows = []
    for line in text.splitlines():
        s = line.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        key, rest = s.split("=", 1)
        parts = rest.split()
        note = ""
        if "#" in rest:
            note = "#" + rest.split("#", 1)[1]
        rows.append({"key": key.strip(),
                     "status": parts[0] if parts else "",
                     "date": parts[1] if len(parts) > 1 else "",
                     "note": note.strip()})
    return rows


def main():
    if not TOKEN:
        print("no token; skipping ledger sync")
        return 0
    os.makedirs(DATA, exist_ok=True)
    for repo in REPOS:
        text = get_file(repo, ".state/progress.txt")
        if text is None:
            print(repo, "ledger: fetch failed (keeping existing mirror)")
            continue
        rows = parse_ledger(text)
        with open(os.path.join(DATA, repo + ".json"), "w") as f:
            json.dump({"repo": "zackhada/" + repo, "rows": rows,
                       "source": "progress.txt"}, f, indent=1)
        print(repo, "ledger:", len(rows), "rows")
        n = get_file(repo, ".state/needs_user")
        with open(os.path.join(DATA, repo + ".needs.json"), "w") as f:
            json.dump({"repo": "zackhada/" + repo,
                       "text": (n.strip() if n and n.strip() else None)}, f,
                      indent=1)
        print(repo, "needs:", "parked" if (n and n.strip()) else "none")
        g = get_file(repo, ".state/grades.json")
        if g:
            try:
                gd = json.loads(g)
                if not gd.get("rows"):
                    print(repo, "grades: empty snapshot, keeping existing")
                    continue
                with open(os.path.join(DATA, repo + ".grades.json"), "w") as f:
                    json.dump(gd, f, indent=1)
                print(repo, "grades:", len(gd.get("rows", [])))
            except Exception as e:
                print(repo, "grades parse failed:", e)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
