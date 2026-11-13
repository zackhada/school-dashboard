#!/usr/bin/env python3
"""Write data/health.json: is the automation actually alive right now?

Why (2026-11-04): Zack asked "is everything healthy?" and the honest answer was
no, but nothing on the dashboard said so. The runner fleet had been dark for a
day and a half while the page looked normal, and the watchdog that should have
caught it reported "runners healthy" because its pipeline swallowed the exit
code. Health has to be visible in the one place he actually looks.

Reads only: GitHub runners + last successful run per repo, plus the runner
Mac's heartbeat file. Never writes anything but data/health.json, never
submits coursework.

Usage: health.py [--json PATH]
Env:   DISPATCH_TOKEN (or GITHUB_TOKEN / GH_SYNC_TOKEN)
"""
import argparse
import datetime
import json
import os
import sys
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
TOKEN = (os.environ.get("DISPATCH_TOKEN") or os.environ.get("GH_SYNC_TOKEN")
         or os.environ.get("GITHUB_TOKEN") or "")
OWNER = "zackhada"

REPOS = ["econ110-automation", "fin201-automation", "hrm391-automation",
         "is515-automation", "pse390-automation", "rel-c-333-automation",
         "strat392-automation", "school-healer", "school-dashboard"]

HEADERS = {"Accept": "application/vnd.github+json", "User-Agent": "school-health"}


def get(url, raw=False):
    if not TOKEN:
        # Without a token the runner API 404s for every other repo, and this
        # script would publish "0 of 9 online" for a healthy fleet: exactly the
        # banner Zack stared at for a week (2026-11-11). Never publish a guess.
        print("health: no DISPATCH_TOKEN/GITHUB_TOKEN; refusing to fetch",
              file=sys.stderr)
        raise SystemExit(2)
    HEADERS["Authorization"] = "Bearer " + TOKEN
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            data = r.read()
            return data if raw else json.loads(data)
    except urllib.error.HTTPError as e:
        return {"_error": "%s %s" % (e.code, e.reason)}
    except Exception as e:
        return {"_error": str(e)}


def parse_ts(s):
    try:
        dt = datetime.datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except Exception:
        return None
    # The runner Mac writes the heartbeat timestamp without a zone
    # ("2026-11-03T08:05:01"). Treat a naive value as UTC or the subtraction
    # against the aware "now" raises and the heartbeat silently vanishes.
    if dt.tzinfo is None:
        # Older host agents wrote naive LOCAL time (Mountain). Reading that as
        # UTC made a fresh heartbeat look 7 hours stale and pinned the dashboard
        # to "spare Mac silent" (fixed 2026-11-10; the writer now sends an
        # offset). Naive values are therefore Mountain time, not UTC.
        try:
            from zoneinfo import ZoneInfo
            dt = dt.replace(tzinfo=ZoneInfo("America/Denver"))
        except Exception:
            dt = dt.replace(tzinfo=datetime.timezone(datetime.timedelta(hours=-7)))
        if dt > datetime.datetime.now(datetime.timezone.utc):
            dt = dt.replace(tzinfo=datetime.timezone.utc)
    return dt


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default=os.path.join(DATA, "health.json"))
    a = ap.parse_args()

    now = datetime.datetime.now(datetime.timezone.utc)
    offline, stale, errors, unverified = [], [], [], []
    online_total = 0
    queued = 0

    for repo in REPOS:
        base = "https://api.github.com/repos/%s/%s" % (OWNER, repo)
        runners = get(base + "/actions/runners")
        if "_error" in runners:
            # A 401/403 is a token problem, not an outage. Counting it as
            # "offline" is what pinned the dashboard to "spare Mac silent, 0 of
            # 9 runners online" for a week while the fleet was healthy
            # (2026-11-10). Record it as unknown instead of asserting it.
            errors.append({repo: runners["_error"]})
            unverified.append(repo)
            continue
        rs = runners.get("runners") or []
        online = sum(1 for r in rs if r.get("status") == "online")
        online_total += online
        if online == 0:
            offline.append(repo)

        q = get(base + "/actions/runs?status=queued&per_page=30")
        queued += len(q.get("workflow_runs") or [])

        runs = get(base + "/actions/runs?status=success&per_page=1")
        wr = (runs.get("workflow_runs") or [{}])[0]
        ts = parse_ts(wr.get("created_at"))
        if ts:
            hours = round((now - ts).total_seconds() / 3600, 1)
            if hours > 30 and repo not in ("school-dashboard",):
                stale.append({"repo": repo, "last_success_hours": hours})
        else:
            stale.append({"repo": repo, "last_success_hours": None})

    # Runner-Mac heartbeat: proves whether the host itself is awake, independent
    # of whether GitHub thinks the runners are online.
    hb = get("https://api.github.com/repos/%s/school-healer/contents/"
             ".state/host_heartbeat.json" % OWNER)
    heartbeat = {}
    if "content" in hb:
        try:
            import base64
            blob = json.loads(base64.b64decode(hb["content"]).decode("utf-8", "replace"))
            ts = parse_ts(blob.get("ts"))
            heartbeat = {
                "ts": blob.get("ts"),
                "age_hours": round((now - ts).total_seconds() / 3600, 1) if ts else None,
                "free_gb": blob.get("free_gb"),
                "bridge": blob.get("bridge"),
                "guard": blob.get("guard"),
            }
        except Exception as e:
            errors.append({"heartbeat": str(e)[:80]})
    else:
        errors.append({"heartbeat": hb.get("_error", "unreadable")})

    # The healer itself (2026-11-13). Its runs failed or timed out all
    # afternoon after the spare took over, yet the banner said healthy: the
    # repo had a success earlier that day, so the 30h staleness rule never
    # fired. Look at the healer's own recent conclusions, and at whether its
    # model calls silently fell back to the free model (a stale login did that).
    healer = {"recent": [], "consecutive_failures": 0, "fallback_calls": None}
    hr = get("https://api.github.com/repos/%s/school-healer/actions/workflows/"
             "healer.yml/runs?status=completed&per_page=5" % OWNER)
    for r in (hr.get("workflow_runs") or []):
        healer["recent"].append({"at": r.get("created_at"),
                                 "conclusion": r.get("conclusion")})
    for r in healer["recent"]:
        if r["conclusion"] == "success":
            break
        healer["consecutive_failures"] += 1
    sj = get("https://api.github.com/repos/%s/school-dashboard/contents/"
             "data/surface_judge.json" % OWNER)
    if "content" in sj:
        try:
            import base64
            j = json.loads(base64.b64decode(sj["content"]).decode("utf-8", "replace"))
            healer["fallback_calls"] = j.get("fallback_calls")
            healer["fallback_reason"] = j.get("fallback_reason")
            healer["judge_at"] = j.get("generated_at")
        except Exception as e:
            errors.append({"surface_judge": str(e)[:80]})
    # End-to-end self-test of the active Mac (school-healer/scripts/selftest.py,
    # every 2h outside quiet hours). Unresolved problems, or no report for 16h
    # (longer than the 12h quiet window), make the banner amber.
    st = get("https://api.github.com/repos/%s/school-healer/contents/"
             ".state/selftest.json" % OWNER)
    selftest = {"ok": None}
    if "content" in st:
        try:
            import base64
            j = json.loads(base64.b64decode(st["content"]).decode("utf-8", "replace"))
            ts = parse_ts(j.get("ts"))
            selftest = {"ok": j.get("ok"), "host": j.get("host"), "ts": j.get("ts"),
                        "age_hours": round((now - ts).total_seconds() / 3600, 1) if ts else None,
                        "problems": [{"check": p.get("check"), "detail": p.get("detail")}
                                     for p in (j.get("problems") or [])],
                        "fixed": [{"check": f.get("check"), "fixed": f.get("fixed")}
                                  for f in (j.get("fixed") or [])]}
        except Exception as e:
            errors.append({"selftest": str(e)[:80]})
    selftest_ok = (selftest.get("ok") is not False
                   and (selftest.get("age_hours") is None or selftest["age_hours"] < 16))
    healer_ok = selftest_ok and (healer["consecutive_failures"] < 2
                 and not (healer["fallback_calls"] or 0))

    out = {
        "generated": now.strftime("%Y-%m-%dT%H:%MZ"),
        "healer": healer,
        "selftest": selftest,
        "runners_online": (None if unverified and online_total == 0 else online_total),
        "runners_checked": len(REPOS),
        "unverified_repos": unverified,
        "offline_repos": offline,
        "queued_runs": queued,
        "stale_repos": stale,
        "heartbeat": heartbeat,
        "errors": errors,
        "healthy": bool(not offline and not stale and healer_ok
                        and (heartbeat.get("age_hours") is None
                             or heartbeat.get("age_hours", 99) < 1)),
    }
    if online_total == 0 and not heartbeat:
        print("health: every runner reads offline AND no heartbeat was readable. "
              "That is a credentials/permission problem, not an outage, so this "
              "snapshot is not published.", file=sys.stderr)
        raise SystemExit(3)
    if unverified and online_total == 0:
        print("health: could not read runner status (%s); publishing snapshot "
              "with runners_online=null rather than claiming an outage."
              % ", ".join(unverified[:3]), file=sys.stderr)
    os.makedirs(DATA, exist_ok=True)
    with open(a.json, "w") as f:
        json.dump(out, f, indent=1)
    print(json.dumps({k: out[k] for k in
                      ("runners_online", "runners_checked", "offline_repos",
                       "queued_runs", "healthy")}, indent=1))
    if heartbeat:
        print("heartbeat age (h):", heartbeat.get("age_hours"),
              "free_gb:", heartbeat.get("free_gb"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
