#!/usr/bin/env python3
"""#331 gap-alignment EVIDENCE collector (ADR 0033, operator 2026-07-21: defer — collect more
evidence across regimes + timeframes + dig into the extremes visually).

Extends the STEP-0 calibration (`_331_gap_alignment_step0.py`) with:
  1. REGIME stratification   — the alignment cross-tab within each mi_market_regime label.
  2. TIMEFRAME               — fwd-5d AND fwd-10d, side by side.
  3. EXTREME CASES           — the biggest winners/losers per alignment class, with full structure
                               detail (landing vs levels, gap, regime, both outcomes) — the list to
                               pull up charts for.

READ-ONLY. Re-run as the cohort accrues (currently ~469 rows / 71 days / 4 regimes).
Usage: docker exec apollo-market python scripts/probes/_331_gap_alignment_evidence.py
"""
from __future__ import annotations

import asyncio
import statistics
import sys
from collections import defaultdict
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from agents.market_intelligence.db import get_pool

_BASE_HIGH_LOOKBACK = 15
_WIN = 5.0

_COHORT_SQL = """
    SELECT s.ticker, s.alert_date, o.fwd_5d_pct, o.fwd_10d_pct, COALESCE(r.regime, 'Unknown') AS regime
    FROM mi_theme_axis_shadow s
    LEFT JOIN mi_ep_scan_outcomes o ON o.ticker = s.ticker AND o.scan_date = s.alert_date
    LEFT JOIN mi_market_regime r ON r.regime_date = s.alert_date
    ORDER BY s.alert_date, s.ticker
"""
_BARS_SQL = """
    SELECT ticker, trade_date, open_price, high_price, close FROM mi_daily_closes
    WHERE ticker = ANY($1::text[]) AND high_price IS NOT NULL ORDER BY ticker, trade_date
"""


def _prior_idx(bars, alert_date):
    idx = None
    for i, b in enumerate(bars):
        if b["trade_date"] < alert_date:
            idx = i
        else:
            break
    return idx


def classify(bars, alert_date):
    """Full detail (RELAXED trailing_high — the powered read). Returns a dict or {}."""
    pidx = _prior_idx(bars, alert_date)
    if pidx is None:
        return {}
    prior_close = bars[pidx]["close"]
    L = next((b["open_price"] for b in bars if b["trade_date"] == alert_date), None)
    if not L or not prior_close:
        return {}
    gap = (L / prior_close - 1) * 100
    n = pidx + 1
    if n < _BASE_HIGH_LOOKBACK:
        return {"marker": "unknown", "gap_pct": gap, "landing": L, "prior_close": prior_close}
    base_high_15 = max(b["high_price"] for b in bars[pidx - _BASE_HIGH_LOOKBACK + 1: pidx + 1])
    trailing_high = max(b["high_price"] for b in bars[: pidx + 1])
    marker = ("punch_through" if L > trailing_high
              else "clears_base_near_miss" if L > base_high_15
              else "fades_into_congestion")
    return {"marker": marker, "gap_pct": gap, "landing": L, "prior_close": prior_close,
            "base_high_15": base_high_15, "trailing_high": trailing_high,
            "over_th_pct": (L / trailing_high - 1) * 100, "over_bh_pct": (L / base_high_15 - 1) * 100}


_MARKERS = ("punch_through", "clears_base_near_miss", "fades_into_congestion")


def _xtab(rows, label, key="fwd_5d_pct"):
    print(f"  --- {label} (N={len(rows)}, {key}) ---")
    for m in _MARKERS:
        s = [r[key] for r in rows if r.get("marker") == m and r.get(key) is not None]
        if not s:
            continue
        gate = "" if len(s) >= 30 else "  (N<30)"
        win = sum(1 for v in s if v >= _WIN)
        print(f"    {m:<24} n={len(s):>3}  avg {sum(s)/len(s):>6.1f}%  med {statistics.median(s):>6.1f}%  win {win}/{len(s)} ({win/len(s)*100:.0f}%){gate}")
    print()


def _extremes(rows, marker, key="fwd_5d_pct", topn=6):
    sub = [r for r in rows if r.get("marker") == marker and r.get(key) is not None]
    sub.sort(key=lambda r: r[key])
    lo, hi = sub[:topn], sub[-topn:][::-1]
    print(f"  === {marker}: {len(sub)} settled — biggest WINNERS then LOSERS (by {key}) ===")
    print(f"    {'ticker':<7}{'alert_date':<12}{'regime':<11}{'gap%':>6}{'>th%':>7}{'>bh%':>7}{'fwd5d':>8}{'fwd10d':>8}")
    for tag, grp in (("WIN", hi), ("LOSE", lo)):
        for r in grp:
            print(f"    {r['ticker']:<7}{str(r['alert_date']):<12}{r['regime']:<11}{r['gap_pct']:>6.1f}"
                  f"{r.get('over_th_pct', 0):>7.1f}{r.get('over_bh_pct', 0):>7.1f}"
                  f"{(r['fwd_5d_pct'] if r['fwd_5d_pct'] is not None else float('nan')):>8.1f}"
                  f"{(r['fwd_10d_pct'] if r['fwd_10d_pct'] is not None else float('nan')):>8.1f}   {tag}")
    print()


async def main():
    pool = await get_pool()
    async with pool.acquire() as conn:
        cohort = [dict(r) for r in await conn.fetch(_COHORT_SQL)]
        tickers = sorted({r["ticker"] for r in cohort})
        bar_rows = await conn.fetch(_BARS_SQL, tickers)
    bars_by = defaultdict(list)
    for r in bar_rows:
        bars_by[r["ticker"]].append(dict(r))
    for t in bars_by:
        bars_by[t].sort(key=lambda b: b["trade_date"])

    rows = []
    for row in cohort:
        det = classify(bars_by.get(row["ticker"], []), row["alert_date"])
        rows.append({**row, **det})
    comp = [r for r in rows if r.get("marker") in _MARKERS]
    print(f"#331 EVIDENCE — cohort N={len(cohort)}, computable {len(comp)}\n")

    print("== TIMEFRAME (all magnitudes/regimes) ==")
    _xtab(comp, "fwd-5d", "fwd_5d_pct")
    _xtab(comp, "fwd-10d", "fwd_10d_pct")

    print("== REGIME stratification (fwd-5d) ==")
    for reg in ("Bull", "Choppy", "Correcting", "Crisis", "Unknown"):
        band = [r for r in comp if r["regime"] == reg]
        if band:
            _xtab(band, f"regime={reg}", "fwd_5d_pct")

    print("== EXTREME CASES for visual review ==")
    for m in _MARKERS:
        _extremes(comp, m)


if __name__ == "__main__":
    asyncio.run(main())
