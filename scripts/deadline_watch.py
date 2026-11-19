#!/usr/bin/env python3
"""Independent deadline watch: never let an automated item's close pass unseen.

Why (Zack 2026-11-19): "make sure all the automated tasks get done completely,
this absolutely cannot fail." The class runners all live on one Mac that sleeps,
so a single skipped evening can lose an item whose close is not at midnight. FIN
201 is the live example: its two remaining quizzes close at 10:00am MT, so the
last usable window is the night before, and its course has no Canvas API at all,
so the Canvas-only audit in assignment_audit.py cannot see it.

This runs on a GitHub-hosted runner (not the Mac), reads the ledger mirrors that
sync_ledgers.py just refreshed, and for every pending row:

  1. computes the true close time (`closes=YYYY-MM-DDTHH:MM` in the note, else
     the ledger date at 23:59 Mountain),
  2. inside 72h, adds it to data/audit.json `closing_soon` so it shows on the
     dashboard even though there is no Canvas row for it,
  3. inside 48h, dispatches that repo's daily workflow, at most once per item
     per day, oldest close first and only ONE repo per pass (the hosts share a
     single Duo account, so logins must never burst).

Reads ledgers, writes data/ only, never submits anything.

Usage:
    python3 scripts/deadline_watch.py            # apply
    python3 scripts/deadline_watch.py --dry-run  # report only, no API writes
"""
import argparse
import datetime as dt
import json
import os
import sys
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
MT = dt.timezone(dt.timedelta(hours=-7), "MT")
REPOS = ["fin201-automation", "econ110-automation", "hrm391-automation",
         "is515-automation", "pse390-automation", "rel-c-333-automation",
         "strat392-automation"]
WATCH_HOURS = 72
DISPATCH_HOURS = 48
CLOSES = "closes="


def token():
    return (os.environ.get("DISPATCH_TOKEN") or os.environ.get("GH_SYNC_TOKEN")
            or os.environ.get("GITHUB_TOKEN") or "")


def load(path, default=None):
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return default if default is not None else {}


def close_time(row):
    """True close: a closes= token beats the ledger date (which is a day)."""
    note = row.get("note") or ""
    i = note.find(CLOSES)
    if i >= 0:
        raw = note[i + len(CLOSES):].strip()
        raw = raw.split()[0].rstrip(".,;")
        try:
            return dt.datetime.strptime(raw, "%Y-%m-%dT%H:%M").replace(tzinfo=MT)
        except ValueError:
            try:
                return dt.datetime.strptime(raw, "%Y-%m-%d").replace(
                    hour=23, minute=59, tzinfo=MT)
            except ValueError:
                pass
    try:
        d = dt.date.fromisoformat(str(row.get("date"))[:10])
    except Exception:
        return None
    return dt.datetime(d.year, d.month, d.day, 23, 59, tzinfo=MT)


def pending_items(now):
    items = []
    for repo in REPOS:
        led = load(os.path.join(DATA, repo + ".json"), {})
        for row in led.get("rows", []):
            if (row.get("status") or "") != "pending":
                continue
            c = close_time(row)
            if not c:
                continue
            hrs = (c - now).total_seconds() / 3600.0
            if hrs > WATCH_HOURS:
                continue
            items.append({
                "repo": repo,
                "key": row.get("key"),
                "title": (row.get("note") or "").lstrip("# ").split("\n")[0][:90]
                         or row.get("key"),
                "close": c.strftime("%Y-%m-%dT%H:%M%z"),
                "close_local": c.strftime("%Y-%m-%d %H:%M MT"),
                "hours": round(hrs, 1),
                "level": "LATE" if hrs <= 0 else ("CRITICAL" if hrs <= 24 else
                                                  ("DISPATCH" if hrs <= DISPATCH_HOURS else "WATCH")),
            })
    items.sort(key=lambda x: x["close"])
    return items


def patch_audit(items, now):
    """Show ledger-only deadlines on the dashboard alongside Canvas truth."""
    path = os.path.join(DATA, "audit.json")
    audit = load(path, {})
    if not audit:
        return 0
    kept = [x for x in audit.get("closing_soon", []) if x.get("source") != "ledger"]
    for it in items:
        kept.append({
            "course": it["repo"].replace("-automation", "").upper(),
            "assignment": it["title"],
            "due": it["close_local"][:10],
            "points": None,
            "deadline_kind": "ledger close " + it["close_local"][11:16],
            "owner": "agent",
            "covered": True,
            "ledger_key": it["key"],
            "ledger_status": "pending",
            "source": "ledger",
            "level": it["level"],
            "note": it["note"] if "note" in it else "",
        })
    audit["closing_soon"] = kept
    audit["ledger_deadlines"] = {"generated": now.isoformat(), "items": items}
    with open(path, "w") as f:
        json.dump(audit, f, indent=1)
    return len(kept)


def dispatch(repo, tok, now, state):
    """Ask the class repo for a run. One repo per pass, once per item per day."""
    done = state.get("dispatches", {})
    url = "https://api.github.com/repos/zackhada/%s/actions/workflows/daily-selfhosted.yml/dispatches" % repo
    body = json.dumps({"ref": "main"}).encode()
    req = urllib.request.Request(url, data=body, method="POST", headers={
        "Authorization": "Bearer " + tok,
        "Accept": "application/vnd.github+json",
        "User-Agent": "deadline-watch"})
    try:
        urllib.request.urlopen(req, timeout=30)
        return "dispatched"
    except Exception as e:
        return "dispatch failed: %s" % e


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    now = dt.datetime.now(MT)
    items = pending_items(now)
    for it in items:
        print("%-8s %-18s %-20s closes %s (%6.1fh) %s"
              % (it["level"], it["repo"].replace("-automation", ""), it["key"],
                 it["close_local"], it["hours"], it["title"][:40]))
    if not items:
        print("no pending ledger item closes within %dh" % WATCH_HOURS)

    state = load(os.path.join(DATA, "deadline_watch.json"), {})
    if args.dry_run:
        return 0

    patch_audit(items, now)

    # Dispatch only when a run can still save the item, and never two repos at
    # once (shared Duo account: concurrent CAS logins cross-consume text codes).
    todays = state.get("dispatches", {})
    cutoff = now - dt.timedelta(hours=20)
    dispatched = None
    for it in items:
        if it["level"] not in ("DISPATCH", "CRITICAL", "LATE"):
            continue
        last = todays.get(it["repo"] + "/" + it["key"])
        if last:
            try:
                if dt.datetime.fromisoformat(last) > cutoff:
                    continue
            except Exception:
                pass
        tok = token()
        if not tok:
            print("no token; cannot dispatch %s" % it["repo"])
            break
        r = dispatch(it["repo"], tok, now, state)
        print("%s %s: %s" % (it["repo"], it["key"], r))
        if r == "dispatched":
            todays[it["repo"] + "/" + it["key"]] = now.isoformat()
            dispatched = it
        break
    state["dispatches"] = todays
    state["generated"] = now.isoformat()
    state["items"] = items
    with open(os.path.join(DATA, "deadline_watch.json"), "w") as f:
        json.dump(state, f, indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
