"""#697 item 2, review fix (2026-10-11): re-run the stored-TRIGGERED extras of `replay_extras.py` WITH THE HYSTERESIS ON.

`replay_extras.py` calls `compute_flag_metrics(yesterday_stage=None)`, so it could not see a HOLD: its "0 TRIGGERED"
extras said nothing about a carried name whose stored label was TRIGGERED and whose raw read has fallen back. This
script feeds the stored label back as `yesterday_stage="TRIGGERED"` (what the scan does for a name that HAS a row) and
prints the raw read next to the held read. Inputs are the files already filed here (q6_extra_bars.out, q1_admit_replay.out).

Run from the repo root:  PYTHONPATH=. python scripts/probes/_697/replay_extras_held.py > scripts/probes/_697/replay_extras_held.out
"""
import collections
import os
from datetime import date

from agents.market_intelligence import flag_detector as fd

HERE = os.path.dirname(os.path.abspath(__file__))

bars = collections.defaultdict(list)
for ln in open(os.path.join(HERE, "q6_extra_bars.out")):
    p = ln.rstrip("\n").split("\t")
    if p[0] == "bar":
        _, t, d, o, h, lo, c, v = p
        bars[t].append({"trade_date": date.fromisoformat(d), "open_price": float(o), "high_price": float(h),
                        "low_price": float(lo), "close": float(c), "volume": float(v) if v else 0.0})

extras = []
for ln in open(os.path.join(HERE, "q1_admit_replay.out")):
    p = ln.rstrip("\n").split("\t")
    if p[0] == "extra" and p[1] >= "2026-08-04" and p[3] == "trig5":
        extras.append((p[1], p[2], p[4]))

held_listed = 0
for d, t, last in extras:
    hist = [r for r in bars[t] if r["trade_date"] <= date.fromisoformat(d)][-fd._HISTORY_DAYS:]
    if len(hist) < 60 or hist[-1]["trade_date"] != date.fromisoformat(d):
        print(d, t, "skipped (no bar on D / < 60 bars)")
        continue
    raw = fd.compute_flag_metrics(hist, ticker=t, yesterday_stage=None, recent_stages=[])
    held = fd.compute_flag_metrics(hist, ticker=t, yesterday_stage="TRIGGERED", recent_stages=["TRIGGERED"])
    listed = held["stage"] == "TRIGGERED"
    held_listed += listed
    print(d, t, "last stored", last, "| raw", raw["stage"], raw.get("reason"),
          "| with yesterday=TRIGGERED ->", held["stage"], "held_from", held.get("held_from_stage"),
          "<-- LISTED in the digest's TRIGGERED section" if listed else "")
print(f"name-nights replayed: {len(extras)}; held-TRIGGERED (listed with no fresh breakout): {held_listed}")
