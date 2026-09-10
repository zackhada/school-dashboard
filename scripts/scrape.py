#!/usr/bin/env python3
"""Nightly Canvas scrape: grades truth for the dashboard grades page.
Writes data/<repo>.grades.json (NEVER touches data/<repo>.json ledger files).
Includes score, workflow_state, missing flag, submission comments, and
submitted body preview for past + future assignments.
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
    out = []
    while path:
        req = urllib.request.Request(
            BASE + path,
            headers={"Authorization": f"Bearer {TOKEN}", "Accept": "application/json"},
        )
        resp = urllib.request.urlopen(req, timeout=30)
        data = json.load(resp)
        out.extend(data if isinstance(data, list) else [data])
        link = resp.headers.get("Link", "")
        nxt = None
        for part in link.split(","):
            if 'rel="next"' in part:
                nxt = part.split(";")[0].strip().strip("<>")
        path = nxt.replace(BASE, "") if nxt else None
    return out


def self_id():
    req = urllib.request.Request(
        BASE + "/api/v1/users/self",
        headers={"Authorization": f"Bearer {TOKEN}", "Accept": "application/json"},
    )
    return json.load(urllib.request.urlopen(req, timeout=30))["id"]


def main():
    uid = self_id()
    db = sqlite3.connect(DB)
    db.execute(
        """CREATE TABLE IF NOT EXISTS assignments (
        canvas_id INTEGER PRIMARY KEY, course_id INTEGER, repo TEXT,
        name TEXT, due_at TEXT, points REAL, workflow_state TEXT,
        score REAL, grade TEXT, missing INTEGER, submission_type TEXT,
        submitted_at TEXT, body TEXT, comments TEXT, seen_at TEXT)"""
    )
    for cid, repo in COURSES.items():
        items = api(f"/api/v1/courses/{cid}/assignments?per_page=100&include[]=submission")
        subs = api(
            f"/api/v1/courses/{cid}/students/submissions?student_ids[]={uid}"
            f"&per_page=100&include[]=assignment&include[]=submission_comments"
            f"&include[]=submission_history"
        )
        by_aid = {s.get("assignment_id"): s for s in subs}
        rows = []
        for a in items:
            sub = dict(a.get("submission") or {})
            full = by_aid.get(a["id"]) or {}
            # prefer the full submission record (has comments/history)
            for k in ("workflow_state", "score", "grade", "missing",
                      "submission_type", "submitted_at", "body", "preview_url"):
                if full.get(k) is not None and sub.get(k) is None:
                    sub[k] = full.get(k)
            comments = [
                {"author": (c.get("author") or {}).get("display_name"),
                 "comment": c.get("comment"), "created": c.get("created_at")}
                for c in (full.get("submission_comments") or sub.get("submission_comments") or [])
            ]
            hist = full.get("submission_history") or []
            my_text = ""
            if hist:
                last = hist[-1].get("submission") or {}
                my_text = (last.get("body") or last.get("url") or "")[:2000]
            elif sub.get("body"):
                my_text = str(sub.get("body"))[:2000]
            ws = sub.get("workflow_state") or "unsubmitted"
            missing = bool(sub.get("missing") or ws == "unsubmitted"
                           and a.get("due_at") is not None)
            db.execute(
                """INSERT OR REPLACE INTO assignments
                (canvas_id, course_id, repo, name, due_at, points,
                 workflow_state, score, grade, missing, submission_type,
                 submitted_at, body, comments, seen_at) VALUES
                (?,?,?,?,?,?,?,?,?,?,?,?,?,?,datetime('now'))""",
                (a["id"], cid, repo, a.get("name"), a.get("due_at"),
                 a.get("points_possible"), ws, sub.get("score"),
                 sub.get("grade"), int(missing),
                 sub.get("submission_type"), sub.get("submitted_at"),
                 my_text, json.dumps(comments)),
            )
            rows.append(
                {"canvas_id": a["id"], "name": a.get("name"),
                 "due": a.get("due_at"), "points": a.get("points_possible"),
                 "status": ws, "score": sub.get("score"),
                 "grade": sub.get("grade"), "missing": missing,
                 "submitted_at": sub.get("submitted_at"),
                 "submission_type": sub.get("submission_type"),
                 "my_submission": my_text, "comments": comments}
            )
        rows.sort(key=lambda r: (r["due"] is None, r["due"] or ""))
        os.makedirs(os.path.join(ROOT, "data"), exist_ok=True)
        json.dump({"repo": f"zackhada/{repo}", "rows": rows,
                   "source": "canvas-api"},
                  open(os.path.join(ROOT, "data", f"{repo}.grades.json"), "w"), indent=1)
        print(repo, len(rows))
    db.commit()
    db.close()


if __name__ == "__main__":
    main()
