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

try:
    from zoneinfo import ZoneInfo
    MTN = ZoneInfo("America/Denver")
except Exception:  # pragma: no cover - tzdata missing on an odd host
    MTN = None


def mtn_day(value):
    """Mountain calendar date for a Canvas timestamp (or a plain date).

    Canvas writes due_at in UTC, so a 11:59pm Mountain deadline is stored as
    06:59:59Z the NEXT day. Slicing the UTC date dated every such item one day
    late on the dashboard (IS 515 14.9 read Nov 5 when it closes Nov 4).
    """
    s = str(value or "")
    if not s:
        return ""
    if "T" not in s:
        return s[:10]
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return s[:10]
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    if MTN is not None:
        return dt.astimezone(MTN).date().isoformat()
    return dt.date().isoformat()  # pragma: no cover

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")

REPOS = ["hrm391-automation", "strat392-automation", "rel-c-333-automation",
         "pse390-automation", "fin201-automation", "is515-automation",
         "econ110-automation"]

# Canvas course IDs (byu.instructure.com). ECON/FIN run on Learning Suite /
# MyEducator / Cengage, so they have no Canvas course.
COURSE_IDS = {"hrm391-automation": 37899, "strat392-automation": 39131,
              "rel-c-333-automation": 38438, "pse390-automation": 38958,
              "is515-automation": 38674}


def norm(s):
    return re.sub(r"[^a-z0-9]+", " ", str(s or "").lower()).strip()


STOP = {"cengage", "mindtap", "class", "pre", "post"}


def words(s):
    out = []
    for w in norm(s).split(" "):
        if len(w) <= 2 or w in STOP:
            continue
        out.append(w)
        bare = re.sub(r"\d+", "", w)
        if len(bare) > 2 and bare != w:
            out.append(bare)  # exam2 also matches exam
    return out


def title_from(key, note):
    n = re.sub(r"^#\s*", "", str(note or ""), count=1)
    n = re.sub(r"^Canvas\s+\d+,\s*[\d.]+\s*pts?,\s*", "", n, flags=re.I)
    n = re.sub(r"\s*\[manual:[^\]]*\]", "", n, flags=re.I)
    n = re.sub(r"\s*\([^()]*\)\s*$", "", n).strip()
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
    if n:
        cut = re.split(r"(?i)\s+due(?:\s|$)", n, maxsplit=1)[0]
        cut = re.sub(r"\b\d+(?:\.\d+)?\s*pts?\b", "", cut, flags=re.I)
        cut = re.sub(r"\b\d{1,2}:\d{2}\s*(?:am|pm)?\b", "", cut, flags=re.I)
        cut = re.sub(r"\s{2,}", " ", cut).strip(" ,;:-")
        if cut:
            return cut
    return re.sub(r"\b(\w)(\w*)\b",
                  lambda m: m.group(1).upper() + m.group(2).lower(),
                  (key or "").replace("_", " "))


def load(name):
    p = os.path.join(DATA, name)
    if not os.path.exists(p):
        return {}
    with open(p) as f:
        return json.load(f)


# Deterministic evidence gate. The LLM surface judge decides what a human must
# do; this is the fallback when no verdict exists (model outage, new row before
# the next healer run). Kept deliberately narrow: a module label such as "Tues
# Oct 20 In Class" and a quiz name are NOT evidence. REAL_MANUAL mirrors
# school-healer/scripts/surface_judge.py.
REAL_MANUAL = re.compile(
    r"(?i)(\[manual:(?!verify)[a-z0-9-]+|attendance check|participation quiz|"
    r"in-class code|access code|proctor|lockdown browser|testing center|"
    r"webcam|submission_types=none|no online submission|on paper|"
    r"bring to class)")
# Attendance and participation are class presence, not a task: Zack is in the
# room anyway, so they never belong in an action list (Zack 2026-10-21).
ATTENDANCE = re.compile(
    r"(?i)\battendance\b|participation quiz|participation and engagement|"
    r"attendance check")

# A block claim that names no evidence at all (the 2026-10-21 STRAT bug).
VAGUE_BLOCK = re.compile(r"(?i)\(in-class/participation|in-class/participation")

# Optional extra credit (Zack 2026-10-25). These are real, in-person items, but
# the course says they are not required, so they must never sit on the human's
# action lists as if they were homework. ECON 110 TA Passoffs are the first
# case: the TA announcement of 2026-09-29 ("TA passoff assignments are part of
# the bonus assignments so they are extra credit and are not required") plus the
# syllabus bonus breakdown (2 of 10 weekly bonus points) settle it. The ledger
# row keeps its own [optional-ec:...] tag; the key pattern is the safety net so
# a re-added row stays hidden.
OPTIONAL_EC = re.compile(r"(?i)\[optional-ec[:/\]]|optional[- ]ec\b")
OPTIONAL_KEY = re.compile(r"(?i)(^|_)TA_PASSOFF(_|$)")


def is_optional_ec(key, note):
    return bool(OPTIONAL_EC.search(str(note or "")) or OPTIONAL_KEY.search(str(key or "")))


def manual_evidence(note):
    n = re.sub(r"^#\s*", "", str(note or ""))
    if VAGUE_BLOCK.search(n) and not re.search(
            r"(?i)(attendance|participation quiz|proctor|lockdown|testing center|"
            r"submission_types=none|no online submission)", n):
        return False
    return bool(REAL_MANUAL.search(n))


def judge_map():
    """repo -> {key: {verdict, why}} from the healer's LLM verdicts."""
    j = load("surface_judge.json")
    out = {}
    for repo, blob in (j.get("repos") or {}).items():
        out[repo] = (blob or {}).get("verdicts") or {}
    return out


def needs_scores(prepped, needs_text):
    """Overlap counts between each (row, title) and the parked needs text."""
    if not needs_text:
        return [0] * len(prepped)
    nw = set(words(needs_text))
    out = []
    for x, title in prepped:
        tw = set(words(str(title) + " " + str(x.get("key", ""))))
        out.append(sum(1 for a in tw if any(_tok_match(a, b) for b in nw)))
    return out


def _tok_match(a, b):
    if a == b:
        return True
    return len(a) >= 4 and len(b) >= 4 and (a.startswith(b) or b.startswith(a))


def overlap_count(tw, gw):
    return sum(1 for a in tw if any(_tok_match(a, b) for b in gw))


# _bwords/words strip digits, so "Unit 1 ..." and "Unit 2 ..." reduce to the
# same token set. A newly published Unit 2 checkpoint would then pair with the
# already-closed Unit 1 row and never get a row of its own (the exact way the
# HRM 391 checkpoint could be missed again). A differing number on the same
# qualifier is decisive: no pairing.
_ORDINAL_Q = (r"(unit|week|wk|exam|quiz|topic|part|module|milestone|"
              r"checkpoint|chapter|ch|round|set)[\s_\-]*#?[\s_\-]*(\d{1,2})")


def ordinals(s):
    out = {}
    for q, n in re.findall(_ORDINAL_Q, str(s or "").lower()):
        out.setdefault(q, set()).add(int(n))
    return out


def ordinal_conflict(a, b):
    """True when both strings number the same thing differently."""
    A, B = ordinals(a), ordinals(b)
    for q in set(A) & set(B):
        if A[q] != B[q]:
            return True
    return False


def canvas_deadline(g):
    """YYYY-MM-DD deadline from a Canvas truth row: due_at, else lock_at.

    A quiz can carry only a lock_at (HRM 391 Unit 1 Mid-term Checkpoint had
    due_at=null, lock_at=2026-10-07T17:00:00Z). Reading due_at alone dated such
    rows 9999-12-31 on the dashboard and hid the real deadline.
    """
    if not isinstance(g, dict):
        return ""
    v = g.get("due") or g.get("due_at") or g.get("lock_at") or g.get("deadline")
    return mtn_day(v)


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
    needs_text = (load(repo + ".needs.json") or {}).get("text")
    verdicts = (judge_map().get(repo) or {})
    # ledger file may itself be a raw dispatch payload; be lenient
    if isinstance(ledger, dict):
        ledger = ledger.get("rows", [])
    prepped = []
    syllabus_only = set()
    for x in ledger:
        key = x.get("key", "")
        if re.search(r"(^|_)(SETUP|RECON)", key):
            continue
        if re.search(r"\b0\s?pts?\b", x.get("note") or "", re.I):
            continue
        if not re.match(r"^\d{4}-\d{2}-\d{2}", x.get("date") or ""):
            continue
        # A row that exists only in the syllabus must never inherit a Canvas
        # date or link from a similarly named assignment. It once matched
        # "Exam 1" and showed a 210 pt final as already 7 days past.
        if re.search(r"(?i)syllabus[- ]only|not (?:created |published )?in canvas|"
                     r"not in canvas yet", x.get("note") or ""):
            syllabus_only.add(len(prepped))
        prepped.append((x, title_from(key, x.get("note"))))
    # Global best-first assignment: highest score wins each Canvas row, so a
    # ledger row is never silently dropped in favour of another.
    gwords = [words(g.get("name")) for g in grades]
    pairs = []
    for i, (x, title) in enumerate(prepped):
        if i in syllabus_only:
            continue
        tw = words(str(title) + " " + str(x.get("key", "")))
        for gi, g in enumerate(grades):
            if ordinal_conflict(g.get("name"), str(title) + " " + str(x.get("key", ""))):
                continue
            ov = overlap_count(tw, gwords[gi])
            # A shared due date is NEVER evidence on its own (2026-11-04). The
            # old rule let any Canvas row with a canvas_id pair at overlap 0,
            # so "HRM 391 Exam 2/3/Final" attached to "Unit 2 Group Service
            # Project (No Submission)" and "STRAT Final Exam" attached to a
            # September assignment, and the dashboard showed those exams on the
            # wrong day. Weak name overlap also needs the date to agree, unless
            # the Canvas row carries no deadline at all (then it cannot borrow
            # a wrong one).
            if ov == 0:
                continue
            gday = canvas_deadline(g)
            dbon = day_bonus(gday, x["date"])
            # Token matching is prefix-based ("finals" matches "final"), so a
            # long prose note inflates overlap. When the ledger title is prose
            # rather than a short assignment name, demand that the dates agree.
            short_title = len(str(title).split()) <= 6
            if gday and not dbon and (not short_title or ov < 3):
                continue
            score = ov * 10 + dbon
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
    # Parked `.state/needs_user` text refers to one unfinished row; flag only
    # the single best token-overlap match (>=2) among NON-done rows so the
    # dashboard's "Needs your input" section surfaces exactly that row (a done
    # row would be hidden there, silently dropping the parked item).
    nscores = needs_scores(prepped, needs_text)
    cand = [i for i, (x, _) in enumerate(prepped)
            if (x.get("status") or "") != "done"]
    nbest = max(cand, key=lambda i: nscores[i]) if (cand and nscores) else -1
    if nbest < 0 or not nscores or nscores[nbest] < 2:
        nbest = -1
    for i, (x, title) in enumerate(prepped):
        g = grades[assign[i]] if i in assign else None
        if g:
            matched_ids.add(g.get("canvas_id"))
        key = x.get("key")
        v = verdicts.get(key) or {}
        # surface: does this row belong in the human's action lists?
        #   judge verdict wins; evidence gate is the fallback.
        blocked = str(x.get("status") or "").startswith("blocked")
        # Optional extra credit: tracked, never surfaced as work Zack owes.
        optional_ec = is_optional_ec(key, x.get("note"))
        if optional_ec:
            surface = False
        elif v.get("verdict") == "manual":
            surface = True
        elif v.get("verdict") == "verify":
            surface = True
        elif v.get("verdict") == "automatable":
            surface = False
        elif str(x.get("status") or "") == "blocked_ask_zack":
            # A row parked on Zack's decision stays visible unless the judge
            # explicitly clears it; only blocked_inperson needs evidence.
            surface = True
        else:
            surface = blocked and manual_evidence(x.get("note"))
        rows.append({"key": key, "status": x.get("status"),
                     "date": x.get("date"), "note": x.get("note"),
                     "title": title, "grade": g, "drift": False,
                     "needs_zack": i == nbest,
                     "judge": v or None,
                     "optional_ec": bool(optional_ec),
                     "surface": bool(surface and blocked),
                     # Only future, non-attendance manual work is an action
                     # item. Past items are done or missed, and attendance is
                     # obvious, so neither belongs on the human's list.
                     "actionable": bool(surface and blocked and not optional_ec
                                        and not ATTENDANCE.search(
                                            str(x.get("note") or "") + " "
                                            + str(title or "")))})
    rows.sort(key=lambda r: r["date"])
    unmatched = [g for g in grades
                 if g.get("canvas_id") is not None
                 and g.get("canvas_id") not in matched_ids
                 and (g.get("points") or 0) > 0
                 # A row with no due_at and no lock_at is a gradebook total
                 # ("Participation and Engagement Grade") or an undated item.
                 # It has no deadline, so it can never be "missed" and must not
                 # sit in drift as if the runner forgot it (2026-11-04).
                 and canvas_deadline(g)
                 and not (g.get("score") is not None
                          and g.get("points") is not None
                          and g.get("score") >= g.get("points"))]
    for g in unmatched:
        rows.append({"key": "CANVAS_%s" % g.get("canvas_id"),
                     "status": "missing_from_ledger",
                     "date": canvas_deadline(g) or "9999-12-31",
                     "note": "# In Canvas but no ledger row; runner must add it",
                     "title": g.get("name"), "grade": g, "drift": True})
    rows.sort(key=lambda r: r["date"])
    out = {"repo": "zackhada/%s" % repo, "rows": rows,
           "unmatched_canvas": unmatched,
           "needs": needs_text,
           "course_id": COURSE_IDS.get(repo),
           "overall": (load(repo + ".grades.json").get("overall") or {}),
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
