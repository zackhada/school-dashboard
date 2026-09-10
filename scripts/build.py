#!/usr/bin/env python3
"""Build canonical dashboard source: data/<repo>.combined.json.

Joins the two existing feeds server-side (previously fuzzy-joined in the
browser):
  - data/<repo>.json         ledger pushed by each class runner (keys/status)
  - data/<repo>.grades.json  Canvas truth from scripts/scrape.py (scores)

Output per repo: data/<repo>.combined.json:
  {"repo": ..., "rows": [{"key","status","date","note","title",
    "grade": {...}|null, "drift": false}], "unmatched_canvas": [...],
   "built_at": ...}

DRIFT = the case the user caught: a Canvas assignment (points > 0) with no
ledger row. It lands in "unmatched_canvas" AND as a synthetic row with
status "missing_from_ledger" so the dashboard shows it instead of hiding it.
Zero-point / muted Canvas items are ignored (dashboard filters those too).
"""
import json
import os
import re
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")

REPOS = ["hrm391-automation", "strat392-automation", "rel-c-333-automation",
         "pse390-automation", "fin201-automation", "is515-automation",
         "econ110-automation"]


def norm(s):
    return re.sub(r"[^a-z0-9]+", " ", str(s or "").lower()).strip()


def words(s):
    out = []
    for w in norm(s).split(" "):
        if len(w) <= 2:
            continue
        out.append(w)
        bare = re.sub(r"\d+", "", w)
        if len(bare) > 2 and bare != w:
            out.append(bare)  # exam2 also matches exam
    return out


def title_from(key, note):
    n = re.sub(r"^#\s*", "", str(note or ""), count=1)
    m = re.match(r"^(\d+\.\d+[^,]*|Topic\s+\d+[^,]*|Quiz\s+\d+[^,]*|"
                 r"Exam\s+\d+[^,]*|Assessment[^,]*)", n)
    if m:
        return m.group(1).strip()
    for pat, val in [("Questionnaire", "Student Questionnaire"),
                     ("Orientation", "Orientation Check"),
                     ("Interview", "Professional Perspective Interview")]:
        if pat in n:
            return val
    pm = re.search(r"PARTICIPATION_QUIZ_([A-Z]{3})(\d{1,2})", key or "")
    if pm:
        return "Participation Quiz %s %s" % (pm.group(1).capitalize(), pm.group(2))
    if "MEET_TA" in (key or ""):
        return "Meet TA"
    return re.sub(r"\b(\w)(\w*)\b",
                  lambda m: m.group(1).upper() + m.group(2).lower(),
                  (key or "").replace("_", " "))


def load(name):
    p = os.path.join(DATA, name)
    if not os.path.exists(p):
        return {}
    with open(p) as f:
        return json.load(f)


def match_grade(title, due_day, grows):
    tw = set(words(title))
    best, best_score = None, -1
    for g in grows:
        gday = str(g.get("due") or "")[:10]
        overlap = len(tw & set(words(g.get("name"))))
        score = overlap + (100 if gday and gday == due_day else 0)
        if score > best_score:
            best_score, best = score, g
    return best if best_score >= 1 else None


def build_repo(repo):
    ledger = load(repo + ".json").get("rows", []) if load(repo + ".json") else []
    grades = load(repo + ".grades.json").get("rows", [])
    # ledger file may itself be a raw dispatch payload; be lenient
    if isinstance(ledger, dict):
        ledger = ledger.get("rows", [])
    matched_ids = set()
    rows = []
    for x in ledger:
        key = x.get("key", "")
        if key.startswith("SETUP"):
            continue
        if re.search(r"\b0\s?pts?\b", x.get("note") or "", re.I):
            continue
        if not re.match(r"^\d{4}-\d{2}-\d{2}", x.get("date") or ""):
            continue
        title = title_from(key, x.get("note"))
        g = match_grade(title, x["date"], grades)
        if g:
            matched_ids.add(g.get("canvas_id"))
        rows.append({"key": key, "status": x.get("status"), "date": x.get("date"),
                     "note": x.get("note"), "title": title,
                     "grade": g, "drift": False})
    rows.sort(key=lambda r: r["date"])
    unmatched = [g for g in grades
                 if g.get("canvas_id") not in matched_ids
                 and (g.get("points") or 0) > 0]
    for g in unmatched:
        rows.append({"key": "CANVAS_%s" % g.get("canvas_id"),
                     "status": "missing_from_ledger",
                     "date": str(g.get("due") or "")[:10] or "9999-12-31",
                     "note": "# In Canvas but no ledger row; runner must add it",
                     "title": g.get("name"), "grade": g, "drift": True})
    rows.sort(key=lambda r: r["date"])
    out = {"repo": "zackhada/%s" % repo, "rows": rows,
           "unmatched_canvas": unmatched,
           "built_at": datetime.now(timezone.utc).isoformat()}
    with open(os.path.join(DATA, repo + ".combined.json"), "w") as f:
        json.dump(out, f, indent=1)
    print(repo, "ledger=%d grades=%d drift=%d" % (len(rows) - len(unmatched),
                                                  len(grades), len(unmatched)))
    return len(unmatched)


def main():
    total = 0
    for repo in REPOS:
        total += build_repo(repo)
    print("TOTAL DRIFT:", total)


if __name__ == "__main__":
    main()
