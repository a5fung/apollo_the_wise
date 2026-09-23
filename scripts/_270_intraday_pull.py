#!/usr/bin/env python3
"""#270 step 2b helper (throwaway) — pull trigger-day minute bars from Polygon for the
cohort's TRIGGERED names. Runs on the prod box (POLYGON_API_KEY in env). Prints TSV:
ticker<TAB>t_ms<TAB>o<TAB>h<TAB>l<TAB>c<TAB>v  (one row per minute bar, all sessions)."""
import json
import os
import sys
import time
import urllib.request

KEY = os.environ["POLYGON_API_KEY"]

# (ticker, trigger_date) from the cohort TRIGGERED set + MNTS as the validation case.
PAIRS = [
    ("ZD", "2026-03-20"), ("CNTA", "2026-04-14"), ("SILO", "2026-04-16"),
    ("RLMD", "2026-04-17"), ("CMPS", "2026-04-24"), ("ROLR", "2026-04-27"),
    ("MXL", "2026-04-29"), ("HCAI", "2026-04-30"), ("RLYB", "2026-05-04"),
    ("CAMP", "2026-05-13"), ("EVC", "2026-05-13"), ("TRT", "2026-05-14"),
    ("ASTI", "2026-05-22"), ("STRL", "2026-05-28"), ("BLZE", "2026-05-29"),
    ("KFRC", "2026-05-29"), ("HCAI", "2026-06-10"), ("MNTS", "2026-06-11"),
]

for t, d in PAIRS:
    url = (f"https://api.polygon.io/v2/aggs/ticker/{t}/range/1/minute/{d}/{d}"
           f"?adjusted=true&sort=asc&limit=50000&apiKey={KEY}")
    try:
        r = json.load(urllib.request.urlopen(url, timeout=25))
        for b in r.get("results", []):
            print(f"{t}\t{b['t']}\t{b['o']}\t{b['h']}\t{b['l']}\t{b['c']}\t{b['v']}")
    except Exception as e:
        print(f"# ERR {t} {d}: {e}", file=sys.stderr)
    time.sleep(0.2)
