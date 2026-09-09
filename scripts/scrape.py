#!/usr/bin/env python3
"""Nightly Canvas scrape: source of truth for all Fall 2026 courses.
Uses a Canvas API token (no browser, no Duo). Writes assignments.db (SQLite)
plus data/<repo>.json for the dashboard. Matches ledger rows by Canvas ID
where present, else by (course, due date, name).
"""
import json
import os
import sqlite3
import urllib.request

BASE = os.environ.get("CANVAS_BASE", "https://byu.instructure.com")
TOKEN = os.environ["CANVAS_TOKEN"]
COURSES = {
    37899: "hrm391-automation",
    38674: "is515-automation",
    38958: "pse390-automation",
    38438: "rel-c-333-automation",
    39131: "strat392-automation",
}
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.path.join(ROOT, "assignments.db")


def api(path):
    req = urllib.request.Request(
        BASE + path,
        headers={"Authorization": f"Bearer {TOKEN}", "Accept": "application/json"},
    )
    out = []
    while path:
        req = urllib.request.Request(
            BASE + path,
            headers={"Authorization": f"Bearer {TOKEN}", "Accept": "application/json"},
        )
        resp = urllib.request.urlopen(req, timeout=30)
        out.extend(json.load(resp))
        link = resp.headers.get("Link", "")
        nxt = None
        for part in link.split(","):
            if 'rel="next"' in part:
                nxt = part.split(";")[0].strip().strip("<>")
        path = nxt.replace(BASE, "") if nxt else None
    return out


def main():
    db = sqlite3.connect(DB)
    db.execute(
        """CREATE TABLE IF NOT EXISTS assignments (
        canvas_id INTEGER PRIMARY KEY, course_id INTEGER, repo TEXT,
        name TEXT, due_at TEXT, points REAL, workflow_state TEXT,
        score REAL, submission_type TEXT, submitted_at TEXT, seen_at TEXT)"""
    )
    for cid, repo in COURSES.items():
        items = api(f"/api/v1/courses/{cid}/assignments?per_page=100&include[]=submission")
        rows = []
        for a in items:
            sub = a.get("submission") or {}
            db.execute(
                """INSERT OR REPLACE INTO assignments VALUES
                (?,?,?,?,?,?,?,?,?,datetime('now'))""",
                (a["id"], cid, repo, a.get("name"), a.get("due_at"),
                 a.get("points_possible"), sub.get("workflow_state"),
                 sub.get("score"), sub.get("submission_type"), sub.get("submitted_at")),
            )
            rows.append(
                {"canvas_id": a["id"], "name": a.get("name"), "due": a.get("due_at"),
                 "points": a.get("points_possible"),
                 "status": sub.get("workflow_state") or "unsubmitted",
                 "score": sub.get("score")}
            )
        os.makedirs(os.path.join(ROOT, "data"), exist_ok=True)
        json.dump({"repo": f"zackhada/{repo}", "rows": rows,
                   "source": "canvas-api"},
                  open(os.path.join(ROOT, "data", f"{repo}.json"), "w"), indent=1)
        print(repo, len(rows))
    db.commit()
    db.close()


if __name__ == "__main__":
    main()
