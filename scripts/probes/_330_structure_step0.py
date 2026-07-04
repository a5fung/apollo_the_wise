#!/usr/bin/env python3
"""#330 STEP-0 (ADR 0016 — docs/decisions/0016-structure-axis-meta-rubric.md).

Backfills the 3 structure components onto the #329 theme-axis backfill cohort
(`mi_theme_axis_shadow`, ~452-456 rows and growing) and cross-tabs them against
forward EP outcomes (`mi_ep_scan_outcomes`) — BEFORE the structure-axis shadow ships, per the
ADR's STEP-0 gate: "If the boost direction is contradicted at N>=30, the table changes before
exposure."

READ-ONLY. SELECTs only against mi_theme_axis_shadow / mi_ep_scan_outcomes / mi_daily_closes.
Writes NOTHING. Mirrors `scripts/backfill_theme_axis_shadow.py` / `scripts/_344_late_source_replay.py`
(live-DB probe pattern) rather than the scripts/probes/ convention of replaying a saved local
extract — this one is cheap enough to re-run live and benefits from always reading current data.

The 3 components (ADR 0016 table), each computed AS-OF strictly PRIOR to alert_date (no
lookahead — uses the last `mi_daily_closes` bar with trade_date < alert_date as "today"):

  (a) Stage-2 long-term trend: prior_close > 200-session SMA AND prior_close >= 0.75x the
      trailing-high. Mirrors flag_detector.py's #356 HTF Stage-2 gate (`_STAGE2_NEAR_HIGH_MIN`,
      `_SMA200_WINDOW`) EXACTLY on the threshold/predicate shape; the anchor differs (prior_close
      here vs pivot_high there) because this cohort has no "pivot" concept, only alert dates.
  (b) Base tightness: RMV over the prior ~15 sessions, via the SSoT `flag_detector._compute_rmv`
      (reference_rmv_tightness_metric) — imported directly, not reimplemented.
  (c) Extension state: prior_close / 10-session SMA. NOTE (honesty flag): the ADR's prose cites
      this as "the MAGNA53 extension check's inputs" but the live MAGNA53 gate (ep_detector.py
      MAX_EXTENSION_PCT) actually uses a 5-day MIN-close ratio, not an SMA-10 ratio — the
      prior_close/SMA-10 form as specified here is really the 9M detector's
      `_MAX_EXTENSION_FROM_MA10` (1.20x) shape. Computed exactly as the ADR/task specified;
      flagged here for the record, not silently "corrected" (ADR is ACCEPTED/signed).

TWO cross-tab variants are printed, both from the SAME underlying data:
  PRIMARY   — strict trailing-252-session high (ADR's literal "trailing-252-session" spec).
              `mi_daily_closes` currently retains only ~13 months of history (since 2025-05-27),
              so a full 252-session window is NOT available for most of the cohort's earlier
              rows -> LOW coverage, reported honestly (n_computable/n_total), never silently
              shrunk to a shorter window.
  SUPPLEMENTARY — relaxed: uses whatever history is loaded (no hard 252-bar floor on the high),
              mirroring how flag_detector.py's live Stage-2 gate actually behaves under its own
              `_HISTORY_DAYS` budget. Recovers a much larger N given the retained-history ceiling;
              disclosed as a SEPARATE, clearly-labeled read, not a substitute for the primary one.

Usage (run inside apollo-market, which has the DB pool):
    docker exec apollo-market python scripts/probes/_330_structure_step0.py
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
from agents.market_intelligence.flag_detector import _compute_rmv  # SSoT tightness primitive
from agents.market_intelligence.parabolic_detector import _sma      # SSoT SMA helper

# Thresholds mirror flag_detector.py's #356 HTF Stage-2 gate (docs/setups/htf.md) exactly.
_STAGE2_NEAR_HIGH_MIN = 0.75
_SMA200_WINDOW = 200
_SMA10_WINDOW = 10
_TRAILING_HIGH_WINDOW = 252   # ADR 0016's "trailing-252-session high" (~52 weeks of sessions)
_RMV_LOOKBACK = 15            # ADR 0016: "RMV over the prior ~15 sessions"
_WIN_THRESHOLD_PCT = 5.0

_COHORT_SQL = """
    SELECT s.ticker, s.alert_date, s.grade, s.themeless_flag, o.fwd_5d_pct
    FROM mi_theme_axis_shadow s
    LEFT JOIN mi_ep_scan_outcomes o
      ON o.ticker = s.ticker AND o.scan_date = s.alert_date
    ORDER BY s.alert_date, s.ticker
"""

_BARS_SQL = """
    SELECT ticker, trade_date, high_price, low_price, close
    FROM mi_daily_closes
    WHERE ticker = ANY($1::text[])
      AND high_price IS NOT NULL AND low_price IS NOT NULL
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


def compute_structure_features(bars: list[dict], alert_date, *, strict: bool) -> dict:
    """AS-OF (strictly prior to alert_date) structure features. See module docstring for the
    strict vs relaxed distinction."""
    out = {"prior_close": None, "stage2": None, "rmv_15": None, "extension_ratio": None}
    pidx = _prior_idx(bars, alert_date)
    if pidx is None:
        return out
    n_avail = pidx + 1
    prior_close = bars[pidx]["close"]
    out["prior_close"] = prior_close

    sma_200 = _sma(bars, pidx, _SMA200_WINDOW) if n_avail >= _SMA200_WINDOW else None
    if strict:
        hi = None
        if n_avail >= _TRAILING_HIGH_WINDOW:
            window = bars[pidx - _TRAILING_HIGH_WINDOW + 1 : pidx + 1]
            hi = max(b["high_price"] for b in window)
    else:
        hi = max(b["high_price"] for b in bars[: pidx + 1])

    if sma_200 is not None and hi is not None:
        out["stage2"] = (prior_close > sma_200) and (prior_close >= _STAGE2_NEAR_HIGH_MIN * hi)

    if n_avail >= _RMV_LOOKBACK + 1:
        out["rmv_15"] = _compute_rmv(bars, pidx, lookback=_RMV_LOOKBACK)

    if n_avail >= _SMA10_WINDOW:
        sma_10 = _sma(bars, pidx, _SMA10_WINDOW)
        if sma_10:
            out["extension_ratio"] = prior_close / sma_10

    return out


def _bucket(row: dict, median_rmv: float) -> Optional[str]:
    if row["stage2"] is None:
        return None  # coverage gap -- excluded from the cross-tab, counted separately
    if row["stage2"] is False:
        return "no-Stage2"
    if row["rmv_15"] is None:
        return "Stage2-only (RMV unknown)"
    return "Stage2+tight" if row["rmv_15"] <= median_rmv else "Stage2-only"


def _print_cross_tab(rows: list[dict], label: str) -> None:
    print(f"--- {label} (N={len(rows)}) ---")
    print(f"{'bucket':<28}{'n':>5}{'settled':>9}{'avg_fwd5d':>12}{'med_fwd5d':>12}{'win>=+5%':>14}")
    for b in ("Stage2+tight", "Stage2-only", "Stage2-only (RMV unknown)", "no-Stage2"):
        sub = [r for r in rows if r["bucket"] == b]
        if not sub:
            continue
        settled = [r["fwd_5d_pct"] for r in sub if r["fwd_5d_pct"] is not None]
        n, ns = len(sub), len(settled)
        if ns:
            avg = sum(settled) / ns
            med = statistics.median(settled)
            win = sum(1 for v in settled if v >= _WIN_THRESHOLD_PCT)
            print(f"{b:<28}{n:>5}{ns:>9}{avg:>11.1f}%{med:>11.1f}%   {win}/{ns} ({win/ns*100:.0f}%)")
        else:
            print(f"{b:<28}{n:>5}{ns:>9}{'--':>12}{'--':>12}{'--':>14}")
    print()


def _run_variant(cohort: list[dict], bars_by: dict, *, strict: bool, label: str) -> None:
    enriched = []
    for row in cohort:
        feats = compute_structure_features(bars_by.get(row["ticker"], []), row["alert_date"], strict=strict)
        enriched.append({**row, **feats})

    n_total = len(enriched)
    n_computable = sum(1 for r in enriched if r["stage2"] is not None)
    print(f"[{label}]")
    print(f"  coverage: stage2 computable {n_computable}/{n_total} ({n_computable/n_total*100:.0f}%)")
    n_rmv = sum(1 for r in enriched if r["rmv_15"] is not None)
    n_ext = sum(1 for r in enriched if r["extension_ratio"] is not None)
    print(f"  rmv_15 computable: {n_rmv}/{n_total} ({n_rmv/n_total*100:.0f}%)  "
          f"extension_ratio computable: {n_ext}/{n_total} ({n_ext/n_total*100:.0f}%)")

    stage2_true_rmvs = [r["rmv_15"] for r in enriched if r["stage2"] is True and r["rmv_15"] is not None]
    if not stage2_true_rmvs:
        print(f"  no Stage2==True rows with computable RMV -- skipping cross-tab.\n")
        return
    median_rmv = statistics.median(stage2_true_rmvs)
    print(f"  median rmv_15 among Stage2==True rows (the tight/loose cutline): {median_rmv:.1f}  (n={len(stage2_true_rmvs)})\n")

    for r in enriched:
        r["bucket"] = _bucket(r, median_rmv)

    computable = [r for r in enriched if r["bucket"] is not None]
    _print_cross_tab(computable, f"{label}: ALL")
    _print_cross_tab([r for r in computable if not r["themeless_flag"]], f"{label}: THEMED half")
    _print_cross_tab([r for r in computable if r["themeless_flag"]], f"{label}: THEMELESS half")


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

    print(f"#330 STEP-0 (ADR 0016) -- cohort N={len(cohort)}, {len(tickers)} distinct tickers\n")
    _run_variant(cohort, bars_by, strict=True,
                 label="PRIMARY (strict trailing-252-session high, per ADR 0016 literal spec)")
    _run_variant(cohort, bars_by, strict=False,
                 label="SUPPLEMENTARY (relaxed -- whatever history is loaded, mirrors flag_detector.py live behavior)")


if __name__ == "__main__":
    asyncio.run(main())
