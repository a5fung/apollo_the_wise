#!/usr/bin/env python3
"""Operator-timezone clock — the durable fix for the recurring PDT/ET/CT confusion (2026-06-27).

The operator is on Pacific. Three clocks are in play and they kept getting conflated:
  - the harness "Today's date" + git timestamps = UTC,
  - the codebase logical/trading day = ET (America/New_York) — but that "ALWAYS ET" rule is for MARKET
    code (ORB windows, market hours), NOT for operator-facing or planning dates,
  - the operator's wall clock = PT.
Memories ("be careful, operator is PT") failed ~100 times. This script is the mechanical answer: a single
source of truth for the operator's current date/time, so nothing has to guess.

Modes:
  python scripts/operator_now.py          -> a human line. RUN THIS whenever a date/time matters to the
                                             operator instead of reading the harness UTC date.
  python scripts/operator_now.py --hook   -> SessionStart-hook JSON that injects the PT date into the
                                             model context at every session start (counters UTC priming).
"""
import json
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

# Single source of truth for the operator's timezone. Change ONLY here if it ever changes.
OPERATOR_TZ = ZoneInfo("America/Los_Angeles")


def operator_now() -> datetime:
    return datetime.now(OPERATOR_TZ)


def main() -> int:
    now = operator_now()
    stamp = now.strftime("%Y-%m-%d %H:%M %Z (%A)")
    line = (f"Operator's current date/time = {stamp} (Pacific). This is THE frame for every "
            f"operator-facing date/time and every PLAN.md planning ETA.")
    if "--hook" in sys.argv:
        ctx = (line + " The harness 'Today's date' is UTC and is NOT the operator's day — never use it "
               "for operator-facing dates, tallies, or 'how late it is'. The codebase 'ALWAYS ET' rule "
               "applies to market/trading code ONLY.")
        print(json.dumps({"hookSpecificOutput": {
            "hookEventName": "SessionStart", "additionalContext": ctx}}))
    else:
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
