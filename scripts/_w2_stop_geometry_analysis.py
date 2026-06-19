#!/usr/bin/env python3
"""W2 study #2 — stop-geometry comparison (#276). READ-ONLY analysis of per-arm replay CSVs.

Run on the server (needs prod DB for the judge cohort + the /tmp arm CSVs from selection_replay_268
--simulate --stop-model ...). Each arm holds selection/entry/exit FIXED and varies ONLY the day-1
stop (threaded into sizing AND exit so R is comparable — advisor 6/18).

Carries the W2 study-1 disciplines:
  • COVERAGE — % of trades the model actually CHANGED the stop on (a model that no-ops on most
    trades and acts on a few manufactures lift; study-1 lesson #1).
  • OUTLIER DECOMPOSITION — drop the top-5 winners; the edge must survive (study-1's skip-wide-open
    died here: top-5 carried 91% of R).
  • FIDELITY ASYMMETRY (pre-registered) — 1-min IEX bars under-count intra-bar stop-outs → the sim
    FLATTERS tighter stops. A WIDER-direction win is trustworthy; a TIGHTER one is suspect.
  • stopout-proxy (frac r<=-0.9) next to expectancy = the mechanism (fewer noise stop-outs).

  python scripts/_w2_stop_geometry_analysis.py --from 2025-06-09 --to 2026-05-04 \
      --arm baseline:/tmp/selection_replay_268_2025-06-09_2026-05-04.csv \
      --arm atr_floor1.0:/tmp/..._stopatr_floor1.0.csv  --arm day_low:/tmp/..._stopday_low.csv
"""
import argparse
import asyncio
import csv
from datetime import date

_SOURCE = "historical_scan"


def _load(path: str) -> dict:
    rows = {}
    with open(path, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            rows[(r["ticker"], str(r["alert_date"]))] = r
    return rows


def _stats(rows: dict, keys: list) -> dict:
    recs = [rows[k] for k in keys if k in rows and (rows[k].get("skipped") or "").lower() not in ("true", "1")]
    rs = [float(x["r_multiple"]) for x in recs]
    pnls = [float(x["total_pnl"]) for x in recs]
    if not rs:
        return {"n": 0}
    n = len(rs)
    wins = sum(1 for r in rs if r > 0)
    stopouts = sum(1 for r in rs if r <= -0.9)
    changed = sum(1 for x in recs
                  if abs(float(x.get("entry_stop") or 0) - float(x.get("orb_low") or 0)) > 1e-4)
    srt = sorted(rs, reverse=True)
    drop5 = srt[5:]
    return {
        "n": n, "exp": sum(rs) / n, "win": wins / n, "sumR": sum(rs),
        "totaldollar": sum(pnls), "stopout": stopouts / n, "coverage": changed / n,
        "exp_drop5": (sum(drop5) / len(drop5)) if drop5 else 0.0,
        "sumR_drop5": sum(drop5),
        "top5R": sum(srt[:5]),
    }


async def main(date_from, date_to, arms):
    from agents.market_intelligence.db import get_pool
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(f"""
            SELECT ticker, alert_date, baseline_floor_tier, judge_tier
            FROM mi_ep_alerts
            WHERE source = '{_SOURCE}' AND alert_date BETWEEN $1 AND $2
              AND judge_tier IS NOT NULL
        """, date_from, date_to)
    judge_high = [(r["ticker"], str(r["alert_date"])) for r in rows if r["judge_tier"] == "HIGH"]
    print(f"=== W2 STUDY #2 — STOP GEOMETRY · {date_from}..{date_to} · judge-HIGH n_keys={len(judge_high)} ===")
    print("pre-registered: WIDER-stop win = trustworthy; TIGHTER (atr_cap) = suspect (1-min sim "
          "under-counts intra-bar stop-outs). Shippable = +ΔR AND +Δ$ vs baseline, survives drop-top-5,")
    print("in the wider direction, coverage shown, kill/scale bands re-derived (they were calibrated on orb_low).\n")
    hdr = (f"{'arm':16} {'n':>4} {'exp':>7} {'win':>5} {'sumR':>8} {'total$':>11} "
           f"{'stopout':>7} {'cover':>6} {'expDrop5':>8} {'sumRDrop5':>9}")
    print(hdr)
    print("-" * len(hdr))
    base = None
    for label, path in arms:
        try:
            s = _stats(_load(path), judge_high)
        except FileNotFoundError:
            print(f"{label:16}  (CSV not found: {path})")
            continue
        if s["n"] == 0:
            print(f"{label:16}  n=0")
            continue
        if base is None:
            base = s
        d_r = s["exp"] - base["exp"]
        d_dollar = s["totaldollar"] - base["totaldollar"]
        flag = ""
        if label != arms[0][0]:
            flag = f"  ΔR={d_r:+.2f} Δ$={d_dollar:+,.0f}"
        print(f"{label:16} {s['n']:>4} {s['exp']:>+7.2f} {s['win']:>5.0%} {s['sumR']:>+8.1f} "
              f"{s['totaldollar']:>+11,.0f} {s['stopout']:>7.0%} {s['coverage']:>6.0%} "
              f"{s['exp_drop5']:>+8.2f} {s['sumR_drop5']:>+9.1f}{flag}")
    print("\nRead: exp/sumR/total$ must ALL improve vs baseline; expDrop5 must stay positive (edge "
          "not top-5-carried); coverage>0 confirms the model actually operated; stopout shows the "
          "mechanism. atr_cap improvements are sim artifacts unless confirmed off 1-min bars.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="date_from", type=date.fromisoformat, required=True)
    ap.add_argument("--to", dest="date_to", type=date.fromisoformat, required=True)
    ap.add_argument("--arm", action="append", default=[], help="LABEL:CSVPATH (repeatable; first = baseline)")
    a = ap.parse_args()
    arms = [(x.split(":", 1)[0], x.split(":", 1)[1]) for x in a.arm]
    asyncio.run(main(a.date_from, a.date_to, arms))
