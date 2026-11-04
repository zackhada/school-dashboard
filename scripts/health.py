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
    if TOKEN:
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
        dt = dt.replace(tzinfo=datetime.timezone.utc)
    return dt


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default=os.path.join(DATA, "health.json"))
    a = ap.parse_args()

    now = datetime.datetime.now(datetime.timezone.utc)
    offline, stale, errors = [], [], []
    online_total = 0

    for repo in REPOS:
        base = "https://api.github.com/repos/%s/%s" % (OWNER, repo)
        runners = get(base + "/actions/runners")
        if "_error" in runners:
            errors.append({repo: runners["_error"]})
            offline.append(repo)
            continue
        rs = runners.get("runners") or []
        online = sum(1 for r in rs if r.get("status") == "online")
        online_total += online
        if online == 0:
            offline.append(repo)

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

    out = {
        "generated": now.strftime("%Y-%m-%dT%H:%MZ"),
        "runners_online": online_total,
        "runners_checked": len(REPOS),
        "offline_repos": offline,
        "stale_repos": stale,
        "heartbeat": heartbeat,
        "errors": errors,
        "healthy": bool(not offline and not stale
                        and (heartbeat.get("age_hours") is None
                             or heartbeat.get("age_hours", 99) < 1)),
    }
    os.makedirs(DATA, exist_ok=True)
    with open(a.json, "w") as f:
        json.dump(out, f, indent=1)
    print(json.dumps({k: out[k] for k in
                      ("runners_online", "runners_checked", "offline_repos",
                       "healthy")}, indent=1))
    if heartbeat:
        print("heartbeat age (h):", heartbeat.get("age_hours"),
              "free_gb:", heartbeat.get("free_gb"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
