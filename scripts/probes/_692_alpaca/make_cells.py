"""Build cells.json for pull_news.py: the 151 replayed M&A ticker-days (input_replay_2026-10-02.jsonl,
one row per ticker-day since 05-15) + weekly windows 06-19 -> 10-09 for the five names the 10-05
anticipation board rejected as pinned buyouts (ARX, BWIN, CBZ, DV, ITGR)."""
import json
from datetime import date, timedelta

rows = [json.loads(l) for l in open("scripts/probes/_692_alpaca/input_replay_2026-10-02.jsonl")]
cells = sorted({(r["ticker"], r["date"]) for r in rows if r.get("kind") == "ticker_day"})
weekly = []
for t in ("ARX", "BWIN", "CBZ", "DV", "ITGR"):
    d = date(2026, 6, 25)
    while d <= date(2026, 10, 9):
        weekly.append([t, d.isoformat()])
        d += timedelta(days=7)
json.dump({"cells": [list(c) for c in cells], "weekly": weekly},
          open("scripts/probes/_692_alpaca/cells.json", "w"))
print(len(cells), "ticker-day cells,", len(weekly), "weekly cells")
