#!/usr/bin/env python3
"""Daily assignment/exam truth check. Built 2026-10-25 after the STRAT 392
midterm was missed: the dashboard only knew about Canvas rows, so a 150-point
Testing Center exam that existed only in the syllabus was invisible.

Four checks, run against live sources rather than against each other:
  1. TESTING CENTER  exams with a blank score past their close date (MISSED),
                     and upcoming unscored exams with their real window.
  2. CANVAS          assignments due in the next N days with points > 0 and no
                     submission; flags any that no ledger row covers.
  3. DATE DRIFT      ledger rows whose date disagrees with the source by > 1 day.
  4. ZERO WATCH      items already graded 0 with no submission, so a silent zero
                     never sits unnoticed.

Read-only. Canvas uses the personal token (GET only). The Testing Center read
attaches to the canonical headless Chrome and is skipped if it is not reachable.

Usage: assignment_audit.py [--days 21] [--json PATH] [--strict]
Exit 1 with --strict when anything MISSED or MISSING FROM LEDGER is found.
"""
import argparse
import asyncio
import datetime
import json
import os
import re
import sys
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(ROOT, "data")
HOME = os.path.expanduser("~")
AGENT = os.path.join(HOME, "Desktop", "school agent")

COURSES = {
    "hrm391-automation": ("HRM 391", 37899, "HRM391001"),
    "is515-automation": ("IS 515", 38674, "IS515002"),
    "pse390-automation": ("PSE 390", 38958, "PSE390009"),
    "rel-c-333-automation": ("REL C 333", 38438, "REL C 333006"),
    "strat392-automation": ("STRAT 392", 39131, "STRAT392002"),
}
# Learning Suite / MyEducator courses keep their schedule in .state/grades.json
LS_COURSES = {"econ110-automation": "ECON 110", "fin201-automation": "FIN 201"}
BASE = os.environ.get("CANVAS_BASE", "https://byu.instructure.com").rstrip("/")


def token():
    t = os.environ.get("CANVAS_TOKEN")
    if t:
        return t
    env = os.path.join(AGENT, "mcom", ".env")
    if os.path.exists(env):
        for line in open(env):
            if line.strip().startswith("CANVAS_TOKEN="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return ""


def api(path, tok):
    out, url = [], BASE + path
    while url:
        req = urllib.request.Request(url, headers={"Authorization": "Bearer " + tok})
        r = urllib.request.urlopen(req, timeout=60)
        d = json.load(r)
        out.extend(d if isinstance(d, list) else [d])
        url = None
        for part in r.headers.get("Link", "").split(","):
            if 'rel="next"' in part:
                url = part.split(";")[0].strip().strip("<>")
    return out


def load_json(name, default=None):
    p = os.path.join(DATA, name)
    if not os.path.exists(p):
        return default
    with open(p) as f:
        return json.load(f)


def words(s):
    return set(re.sub(r"[^a-z0-9 ]+", " ", str(s).lower()).split())


STOP = {"quiz", "week", "class", "reading", "assignment", "assessment", "the",
        "and", "for", "pre", "post", "study", "padlet", "sharing", "check",
        "part", "group", "project", "mid", "term", "final", "exam", "attendance",
        "online", "inclass", "what", "with", "from"}


def score_match(ledger_title, ledger_key, name):
    """Distinctive-token overlap. One shared token is not enough: 'Cost Curve'
    once matched 'INDUSTRY_5FORCES' and produced 100 phantom drifts."""
    tw = {w for w in words(str(ledger_title) + " " + str(ledger_key))
          if w not in STOP and not w.isdigit() and len(w) >= 4}
    nw = {w for w in words(name) if w not in STOP and not w.isdigit() and len(w) >= 4}
    common = tw & nw
    strong = {w for w in common if len(w) >= 6}
    score = len(common) + len(strong)
    blob = str(ledger_title) + " " + str(ledger_key)
    m = re.match(r"\s*(\d{1,2})/(\d{1,2})\b", str(name or ""))
    if m:
        a, b = m.group(1), m.group(2)
        if re.search(r"(?<![0-9])(%s)[_/\-. ](%s)(?![0-9])" % (a, b), blob):
            score += 4
    for sec in re.findall(r"\b(\d{1,2}\.\d{1,2})\b", str(name or "")):
        if sec.replace(".", ".") in blob or sec.replace(".", "_") in blob:
            score += 4
    return score


def matches(ledger_title, ledger_key, name):
    return score_match(ledger_title, ledger_key, name) >= 2


def testing_center(term="20265"):
    try:
        sys.path.insert(0, os.path.join(AGENT, "school-healer", "scripts"))
        import testing_center as tc  # noqa: E402
        return asyncio.run(tc.gather(term, tc.COURSES))
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"}


def parse_date(s):
    m = re.match(r"([A-Z][a-z]{2}) (\d{1,2}), (\d{4})", s or "")
    if not m:
        return None
    try:
        return datetime.datetime.strptime(" ".join(m.groups()), "%b %d %Y").date()
    except ValueError:
        return None


def parse_dt(s):
    m = re.match(r"([A-Z][a-z]{2}) (\d{1,2}), (\d{4}) (\d{1,2}):(\d{2}) (AM|PM)", s or "")
    if not m:
        return None
    dt = datetime.datetime.strptime("%s %s %s %s:%s %s" % m.groups(), "%b %d %Y %I:%M %p")
    return dt


def sync_alerts(windows):
    """Any unscored Testing Center exam that has a real window becomes a
    calendar alert, so a syllabus-only exam can never be invisible again."""
    reg = os.path.join(AGENT, "scripts", "in_person_required.json")
    if not os.path.exists(reg):
        return 0
    d = json.load(open(reg))
    items = d.get("items") or []
    added = 0
    for w in windows:
        start, end = parse_dt(w.get("opens")), parse_dt(w.get("closes"))
        if not start or not end:
            continue
        dup = False
        for it in items:
            try:
                s0 = datetime.datetime.fromisoformat(it["start"])
            except Exception:
                continue
            if it.get("course") == w["course"] and abs((s0 - start).days) <= 1:
                dup = True
                break
        if dup:
            continue
        slug = re.sub(r"[^a-z0-9]+", "-", (w["course"] + "-" + str(w["test"]))).strip("-")[:40].lower()
        items.append({
            "id": "tc-%s-%s" % (slug, end.date().isoformat()),
            "course": w["course"],
            "title": "%s %s (Testing Center)" % (w["course"], w["test"] or "exam"),
            "points": 0,
            "start": start.isoformat(),
            "end": end.isoformat(),
            "location": "BYU Testing Center",
            "status": "upcoming",
            "note": "Added automatically from the live Testing Center schedule on %s. Closes %s."
                    % (datetime.date.today().isoformat(), w.get("closes")),
            "source": "testing.byu.edu /my-exams (assignment_audit.py --sync-alerts)",
        })
        added += 1
    if added:
        d["items"] = items
        json.dump(d, open(reg, "w"), indent=1)
        subprocess = __import__("subprocess")
        subprocess.run([sys.executable, os.path.join(AGENT, "scripts", "exam_alerts.py"), "sync"],
                       capture_output=True, text=True, timeout=300)
    return added


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=21)
    ap.add_argument("--json", default=os.path.join(DATA, "audit.json"))
    ap.add_argument("--strict", action="store_true")
    ap.add_argument("--sync-alerts", action="store_true",
                    help="add any new unscored Testing Center exam to the alert registry")
    a = ap.parse_args()
    today = datetime.date.today()

    findings = {"generated": today.isoformat(), "missed": [], "exam_windows": [],
                "missing_from_ledger": [], "date_drift": [], "zero_watch": []}

    # 1. Testing Center
    tc = testing_center()
    if "error" in tc:
        findings["testing_center_error"] = tc["error"]
    else:
        for course, rows in (tc.get("exams") or {}).items():
            for r in rows:
                name = r.get("test") or "(unnamed, opens %s)" % r.get("opens")
                closes = parse_date(r.get("closes"))
                score = (r.get("score") or "").strip()
                rec = {"course": course, "test": name,
                       "opens": r.get("opens"), "closes": r.get("closes"),
                       "score": score}
                if score:
                    continue
                if closes and closes < today:
                    findings["missed"].append(rec)
                elif closes:
                    findings["exam_windows"].append(rec)

    # 2/3/4. Canvas + ledger
    for repo, (label, cid, _code) in COURSES.items():
        ledger = (load_json(repo + ".json") or {}).get("rows") or []
        try:
            asns = api("/api/v1/courses/%d/assignments?per_page=100&include[]=submission" % cid,
                       token())
        except Exception as e:
            findings.setdefault("canvas_errors", []).append({repo: str(e)[:120]})
            continue
        for x in asns:
            due = (x.get("due_at") or "")[:10]
            pts = x.get("points_possible") or 0
            sub = x.get("submission") or {}
            state = sub.get("workflow_state")
            score = sub.get("score")
            if not x.get("published", True) or not due or pts <= 0:
                continue
            dd = datetime.date.fromisoformat(due)
            covered = False
            drift = None
            best = None
            for row in ledger:
                sc = score_match(row.get("note"), row.get("key"), x.get("name"))
                if sc >= 2 and (best is None or sc > best[0]):
                    best = (sc, row)
            if best is not None:
                row = best[1]
                covered = True
                rd = (row.get("date") or "")[:10]
                if re.match(r"^\d{4}-\d{2}-\d{2}$", rd):
                    delta = abs((datetime.date.fromisoformat(rd) - dd).days)
                    if delta > 1 and pts >= 20:
                        drift = {"course": label, "assignment": x.get("name"),
                                 "canvas_due": due, "ledger_date": rd,
                                 "ledger_key": row.get("key")}
            if drift:
                findings["date_drift"].append(drift)
            if today <= dd <= today + datetime.timedelta(days=a.days):
                if state in (None, "unsubmitted") and not covered:
                    findings["missing_from_ledger"].append({
                        "course": label, "assignment": x.get("name"),
                        "due": due, "points": pts, "canvas_id": x.get("id")})
            nm = (x.get("name") or "").lower()
            if re.search(r"attendance|participation|clicker|passoff|check answers", nm):
                continue
            if dd < today and state == "unsubmitted" and pts > 0:
                findings["zero_watch"].append({
                    "course": label, "assignment": x.get("name"), "due": due,
                    "points": pts, "score": score})

    # Learning Suite courses: zeros and upcoming uncovered rows come from grades.json
    for repo, label in LS_COURSES.items():
        g = load_json(repo + ".grades.json") or {}
        for r in g.get("rows") or []:
            due = (r.get("due") or "")[:10]
            if not due or (r.get("points") or 0) <= 0:
                continue
            dd = datetime.date.fromisoformat(due)
            nm = (r.get("name") or "").lower()
            if re.search(r"attendance|participation|clicker|passoff|check answers|^\d+/\d+", nm):
                continue
            if dd < today and r.get("score") == 0:
                findings["zero_watch"].append({
                    "course": label, "assignment": r.get("name"), "due": due,
                    "points": r.get("points"), "score": r.get("score")})

    # report
    def show(title, rows, fmt):
        print("\n## %s (%d)" % (title, len(rows)))
        for r in rows:
            print("  " + fmt(r))

    print("AUDIT %s" % findings["generated"])
    if findings.get("testing_center_error"):
        print("  testing center unavailable:", findings["testing_center_error"])
    show("MISSED EXAMS", findings["missed"],
         lambda r: "%-10s %-40s closed %s" % (r["course"], r["test"], r["closes"]))
    show("EXAM WINDOWS (upcoming, unscored)", findings["exam_windows"],
         lambda r: "%-10s %-40s %s -> %s" % (r["course"], r["test"], r["opens"], r["closes"]))
    show("MISSING FROM LEDGER", findings["missing_from_ledger"],
         lambda r: "%-10s %-52s due %s  %spt" % (r["course"], r["assignment"][:52], r["due"], r["points"]))
    show("DATE DRIFT", findings["date_drift"],
         lambda r: "%-10s %-40s canvas %s vs ledger %s (%s)" % (
             r["course"], r["assignment"][:40], r["canvas_due"], r["ledger_date"], r["ledger_key"]))
    show("ZERO WATCH", findings["zero_watch"],
         lambda r: "%-10s %-52s due %s  %spt" % (r["course"], r["assignment"][:52], r["due"], r["points"]))

    if a.sync_alerts:
        added = sync_alerts(findings["exam_windows"])
        print("\nregistry: %d new exam alert(s)" % added)

    with open(a.json, "w") as f:
        json.dump(findings, f, indent=1)
    print("\nwrote", a.json)
    bad = len(findings["missed"]) + len(findings["missing_from_ledger"])
    if a.strict and bad:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
