#!/usr/bin/env python3
"""#331 STEP-0 (ADR 0033 — docs/decisions/0033-gap-structure-alignment-axis.md).

Backfills the gap-vs-structure ALIGNMENT classification onto the #329 theme-axis cohort
(`mi_theme_axis_shadow`) ⋈ forward EP outcomes (`mi_ep_scan_outcomes`), and cross-tabs vs fwd-5d
outcomes — BEFORE any gap-alignment shadow ships (ADR 0033 STEP-0; operator greenlit 7/19: run
STEP-0 to PRODUCE the table, sign-off downstream).

READ-ONLY. SELECTs mi_theme_axis_shadow / mi_ep_scan_outcomes / mi_daily_closes. Writes NOTHING.

Definitions (ADR 0033 §30-60):
  Landing L    = alert-DAY open_price (§85 honesty flag: the only stored landing point; the live
                 shadow will use current_price at 9:3x — a flagged live-vs-backfill difference).
  trailing_high= as-of strictly-prior overhead ceiling. STRICT = trailing-252-session high (§32,
                 low coverage under retained history); RELAXED = whatever history is loaded (§37,
                 the powered read). No lookahead — bars with trade_date < alert_date only.
  base_high_15 = max(high) over the prior ~15 sessions — the congestion zone the RMV base window
                 covers (§44).
  gap magnitude= (L/prior_close - 1) — the BACKFILL proxy for the ep_score gap tier (flagged; live
                 credits the detection gap). Used ONLY to stratify, never in the credit.

Alignment (§55):
  L > trailing_high                    -> punch_through          (blue sky; +1 in the live table)
  base_high_15 < L <= trailing_high    -> clears_base_near_miss   (0 until evidence)
  L <= base_high_15                    -> fades_into_congestion   (0, never negative)
  insufficient prior history           -> unknown

The load-bearing table (§91-95): the SAME cross-tab STRATIFIED by gap-magnitude band. Alignment
earns its keep ONLY if it separates outcomes WITHIN a magnitude band — else it is magnitude in a
costume and MUST NOT ship (that finding goes to the operator as "drop the axis").

Usage: docker exec apollo-market python scripts/probes/_331_gap_alignment_step0.py
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

_TRAILING_HIGH_WINDOW = 252   # ADR 0033 §32 (via 0016) — trailing-252-session high
_BASE_HIGH_LOOKBACK = 15      # ADR 0033 §44 — the RMV base window
_WIN_THRESHOLD_PCT = 5.0
_N_GATE = 30                  # §99 — cells under this are direction-checks only, never ship evidence
_MAG_BANDS = [("<10%", lambda g: g < 10.0),
              ("10-15%", lambda g: 10.0 <= g < 15.0),
              (">=15%", lambda g: g >= 15.0)]

_COHORT_SQL = """
    SELECT s.ticker, s.alert_date, o.fwd_5d_pct
    FROM mi_theme_axis_shadow s
    LEFT JOIN mi_ep_scan_outcomes o
      ON o.ticker = s.ticker AND o.scan_date = s.alert_date
    ORDER BY s.alert_date, s.ticker
"""
_BARS_SQL = """
    SELECT ticker, trade_date, open_price, high_price, close
    FROM mi_daily_closes
    WHERE ticker = ANY($1::text[]) AND high_price IS NOT NULL
    ORDER BY ticker, trade_date
"""


def _prior_idx(bars: list[dict], alert_date) -> Optional[int]:
    """Index of the last bar strictly BEFORE alert_date (no lookahead). None if none exists."""
    idx = None
    for i, b in enumerate(bars):
        if b["trade_date"] < alert_date:
            idx = i
        else:
            break
    return idx


def _alert_day_open(bars: list[dict], alert_date):
    for b in bars:
        if b["trade_date"] == alert_date:
            return b["open_price"]
    return None


def classify(bars: list[dict], alert_date, *, strict: bool):
    """Returns (marker, gap_pct). marker=None if landing/prior unavailable; 'unknown' if a level
    can't be computed. Landing = alert-day open; levels strictly prior (no lookahead)."""
    pidx = _prior_idx(bars, alert_date)
    if pidx is None:
        return None, None
    prior_close = bars[pidx]["close"]
    L = _alert_day_open(bars, alert_date)
    if not L or not prior_close:
        return None, None
    gap_pct = (L / prior_close - 1.0) * 100.0
    n_avail = pidx + 1
    if n_avail < _BASE_HIGH_LOOKBACK:
        return "unknown", gap_pct
    base_high_15 = max(b["high_price"] for b in bars[pidx - _BASE_HIGH_LOOKBACK + 1: pidx + 1])
    if strict:
        if n_avail < _TRAILING_HIGH_WINDOW:
            return "unknown", gap_pct
        trailing_high = max(b["high_price"] for b in bars[pidx - _TRAILING_HIGH_WINDOW + 1: pidx + 1])
    else:
        trailing_high = max(b["high_price"] for b in bars[: pidx + 1])
    if L > trailing_high:
        return "punch_through", gap_pct
    if L > base_high_15:                     # base_high_15 < L <= trailing_high
        return "clears_base_near_miss", gap_pct
    return "fades_into_congestion", gap_pct  # L <= base_high_15


def _xtab(rows: list[dict], label: str) -> None:
    print(f"--- {label} (N={len(rows)}) ---")
    print(f"{'alignment':<26}{'n':>5}{'settled':>9}{'avg_fwd5d':>12}{'med_fwd5d':>12}{'win>=+5%':>14}")
    for m in ("punch_through", "clears_base_near_miss", "fades_into_congestion", "unknown"):
        sub = [r for r in rows if r["marker"] == m]
        if not sub:
            continue
        settled = [r["fwd_5d_pct"] for r in sub if r["fwd_5d_pct"] is not None]
        n, ns = len(sub), len(settled)
        gate = "" if ns >= _N_GATE else "  (N<30 direction-check)"
        if ns:
            avg = sum(settled) / ns
            med = statistics.median(settled)
            win = sum(1 for v in settled if v >= _WIN_THRESHOLD_PCT)
            print(f"{m:<26}{n:>5}{ns:>9}{avg:>11.1f}%{med:>11.1f}%   {win}/{ns} ({win / ns * 100:.0f}%){gate}")
        else:
            print(f"{m:<26}{n:>5}{ns:>9}{'--':>12}{'--':>12}{'--':>14}")
    print()


def _run(cohort: list[dict], bars_by: dict, *, strict: bool, label: str) -> None:
    enriched = []
    for row in cohort:
        marker, gap = classify(bars_by.get(row["ticker"], []), row["alert_date"], strict=strict)
        enriched.append({**row, "marker": marker, "gap_pct": gap})
    n_total = len(enriched)
    n_comp = sum(1 for r in enriched if r["marker"] not in (None, "unknown"))
    print(f"[{label}]")
    print(f"  alignment computable: {n_comp}/{n_total} ({n_comp / n_total * 100:.0f}%)\n")
    comp = [r for r in enriched if r["marker"] is not None]
    _xtab(comp, f"{label}: PRIMARY (all magnitudes)")
    print("  === MAGNITUDE-INDEPENDENCE CHECK — does alignment separate outcomes WITHIN a gap band? ===\n")
    for bname, bfn in _MAG_BANDS:
        band = [r for r in comp if r["gap_pct"] is not None and bfn(r["gap_pct"])]
        if band:
            _xtab(band, f"{label}: gap {bname}")


async def main() -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        cohort = [dict(r) for r in await conn.fetch(_COHORT_SQL)]
        tickers = sorted({r["ticker"] for r in cohort})
        bar_rows = await conn.fetch(_BARS_SQL, tickers)
    bars_by: dict[str, list[dict]] = defaultdict(list)
    for r in bar_rows:
        bars_by[r["ticker"]].append(dict(r))
    for t in bars_by:
        bars_by[t].sort(key=lambda b: b["trade_date"])

    print(f"#331 STEP-0 (ADR 0033) — cohort N={len(cohort)}, {len(tickers)} distinct tickers\n")
    _run(cohort, bars_by, strict=False,
         label="RELAXED (whatever history is loaded — the powered read, mirrors live behavior)")
    _run(cohort, bars_by, strict=True,
         label="STRICT (trailing-252-session high — low coverage under retained history)")


if __name__ == "__main__":
    asyncio.run(main())
