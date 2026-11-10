#!/usr/bin/env python3
"""quiet_hours.py — the runner Mac must be silent between 10pm and 10am MT.

Zack asked (2026-11-10) that the spare Mac's fan never run while he is asleep.
Fan noise comes from heavy work, not from an idle GitHub runner, so the rule is
enforced on the work that actually loads the machine: assignment runs, session
keepalives, Chrome scraping, LLM agent calls, healer drift passes.

Policy (America/Denver, DST-aware):
  QUIET    22:00 - 10:00   nothing heavy starts; in-flight work finishes
  ACTIVE   10:00 - 21:30   housekeeping (keepalive, healer, scrape) may run
  SUBMIT   17:00 - 21:30   assignment runs (unchanged 5-10pm submission window)

Usage:
  python3 scripts/quiet_hours.py            # exit 0 active, 3 quiet
  python3 scripts/quiet_hours.py --json     # machine-readable state
  python3 scripts/quiet_hours.py --submit   # exit 0 only inside 17:00-21:30

Why a script and not just cron times: crons are UTC and the Mac runs in
Mountain time, so a fixed UTC hour drifts across DST. Every workflow therefore
keeps its cron but asks this script whether it is allowed to work.
"""
import datetime
import json
import sys

QUIET_START_HOUR = 22   # 10:00pm MT
QUIET_END_HOUR = 10     # 10:00am MT
ACTIVE_END = (21, 30)   # nothing new starts after 9:30pm MT
SUBMIT_START = (17, 0)
SUBMIT_END = (21, 30)


def now_mt():
    try:
        from zoneinfo import ZoneInfo
        return datetime.datetime.now(ZoneInfo("America/Denver"))
    except Exception:
        # Fallback: MST is UTC-7, MDT is UTC-6. Close enough to pick the season.
        now = datetime.datetime.now(datetime.timezone.utc)
        offset = -6 if 3 <= now.month <= 10 else -7
        return now + datetime.timedelta(hours=offset)


def _mins(hm):
    return hm[0] * 60 + hm[1]


def state(dt=None):
    dt = dt or now_mt()
    mins = dt.hour * 60 + dt.minute
    quiet = mins >= QUIET_START_HOUR * 60 or mins < QUIET_END_HOUR * 60
    submit = _mins(SUBMIT_START) <= mins < _mins(SUBMIT_END)
    active = (not quiet) and mins < _mins(ACTIVE_END)
    return {
        "local": dt.strftime("%Y-%m-%d %H:%M %Z"),
        "quiet": quiet,
        "active": active,
        "submit_window": submit,
    }


def main():
    want_submit = "--submit" in sys.argv
    s = state()
    if "--json" in sys.argv:
        print(json.dumps(s))
    elif want_submit:
        print("quiet-hours: submit window %s (%s)" % (
            "OPEN" if s["submit_window"] else "CLOSED", s["local"]))
    elif s["quiet"]:
        print("quiet-hours: QUIET until 10:00 MT (%s)" % s["local"])
    else:
        print("quiet-hours: active (%s)" % s["local"])
    if want_submit:
        return 0 if s["submit_window"] else 3
    return 3 if s["quiet"] else 0


if __name__ == "__main__":
    sys.exit(main())
