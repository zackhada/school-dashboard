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

DRIFT = a Canvas assignment (points > 0) with no ledger row. It lands in
"unmatched_canvas" AND as a synthetic row with status "missing_from_ledger"
so the dashboard shows it instead of hiding it. Zero-point / muted Canvas
items are ignored (dashboard filters those too).

Ledger dates are Mountain-local while Canvas due_at is UTC, so the same
deadline can be one calendar day apart; the matcher accepts +/- 1 day and
assigns best-first so two ledger rows cannot claim one Canvas row.
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


def _tok_match(a, b):
    if a == b:
        return True
    return len(a) >= 4 and len(b) >= 4 and (a.startswith(b) or b.startswith(a))


def overlap_count(tw, gw):
    return sum(1 for a in tw if any(_tok_match(a, b) for b in gw))


def day_bonus(gday, due_day):
    # Exact day wins (100); +/-1 day allowed (60) because ledger dates are
    # Mountain-local and Canvas due_at is UTC.
    if not gday or not due_day:
        return 0
    try:
        d1 = datetime.strptime(gday, "%Y-%m-%d").date()
        d2 = datetime.strptime(due_day, "%Y-%m-%d").date()
    except ValueError:
        return 0
    diff = abs((d1 - d2).days)
    return 100 if diff == 0 else (60 if diff == 1 else 0)


def build_repo(repo):
    ledger = load(repo + ".json").get("rows", []) if load(repo + ".json") else []
    grades = load(repo + ".grades.json").get("rows", [])
    # ledger file may itself be a raw dispatch payload; be lenient
    if isinstance(ledger, dict):
        ledger = ledger.get("rows", [])
    prepped = []
    for x in ledger:
        key = x.get("key", "")
        if re.search(r"(^|_)(SETUP|RECON)", key):
            continue
        if re.search(r"\b0\s?pts?\b", x.get("note") or "", re.I):
            continue
        if not re.match(r"^\d{4}-\d{2}-\d{2}", x.get("date") or ""):
            continue
        prepped.append((x, title_from(key, x.get("note"))))
    # Global best-first assignment: highest score wins each Canvas row, so a
    # ledger row is never silently dropped in favour of another.
    gwords = [words(g.get("name")) for g in grades]
    pairs = []
    for i, (x, title) in enumerate(prepped):
        tw = words(title)
        for gi, g in enumerate(grades):
            score = overlap_count(tw, gwords[gi]) * 10 + day_bonus(
                str(g.get("due") or "")[:10], x["date"])
            if score > 0:
                pairs.append((score, i, gi))
    pairs.sort(key=lambda t: -t[0])
    assign, used_g = {}, set()
    for score, i, gi in pairs:
        if i in assign or gi in used_g:
            continue
        assign[i] = gi
        used_g.add(gi)
    matched_ids = set()
    rows = []
    for i, (x, title) in enumerate(prepped):
        g = grades[assign[i]] if i in assign else None
        if g:
            matched_ids.add(g.get("canvas_id"))
        rows.append({"key": x.get("key"), "status": x.get("status"),
                     "date": x.get("date"), "note": x.get("note"),
                     "title": title, "grade": g, "drift": False})
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
