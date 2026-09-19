"""TI5 v0 — Post-EP shape explorer (decision-support only).

For every HIGH/MODERATE EP alert in the last `--days` window, walks forward
through `mi_daily_closes` and computes:

  Day-0 primitives:
    - close_in_range_pct = (close - low) / (high - low)
    - gap_pct (from mi_ep_alerts)
    - prev_5d_pct = (close_T0 / close_T-5) - 1

  Forward shape evolution at T+1, T+3, T+5, T+10:
    - close_vs_anchor_open_pct
    - close_vs_anchor_close_pct
    - first_undercut_session  (first session where close < anchor_open)
    - first_breakout_session  (first session where high > anchor_high)

  Forward R-multiple distribution at each horizon — the methodology metric.

R is computed against an explicit stop assumption:
    entry  = anchor_close (operator enters at EP-day close)
    stop   = anchor_low   (matches 9M Day 2 sugar baby stop convention)
    R(t)   = (price_t - entry) / (entry - stop)

Per anchor:
    did_stop_T+N       — did any session [T+1..T+N] have low ≤ stop?
    max_favorable_R    — peak R reached before stopping (or to horizon)
    R_at_horizon_close — R if exited at T+N close (time-stop exit)
    R_with_3R_target   — R if exited at +3R take-profit OR stopped (-1R)

Buckets by deterministic shape labels → reports per-bucket EXPECTANCY
metrics, not just positive-rate. Per Pradeep/Qullamaggie methodology:
20% win rate × 10R = +1.2R expectancy beats 60% × 1R = +0.2R. Win rate
alone is misleading; lose-small / win-big systems show their edge in R.

v1 detector candidate: bucket with median_max_favorable_R ≥ 3.0 AND
expectancy_3R_TP ≥ +0.5R AND n ≥ 30. (Stop-rate alone doesn't disqualify
— a 70% stop-out rate with +5R median favorable still has positive
expectancy if winners run.)

Usage (on Hetzner):
    docker exec apollo-market python -m scripts.ep_shape_explorer
    docker exec apollo-market python -m scripts.ep_shape_explorer --days 90 --csv /tmp/ep_shapes_90d.csv

Pure exploration. No DB writes. No entries. No detector behavior change.
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import logging
import statistics
from collections import defaultdict
from datetime import date, timedelta
from typing import Optional

import asyncpg

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# Shape thresholds (locked v0)
STRONG_CLOSE = 0.75    # close_in_range_pct ≥ → "strong"
WEAK_CLOSE   = 0.40    # close_in_range_pct < → "weak"; in-between = "mid_range"
CONT_FADE_HORIZON = 5  # measure continuation/fade at T+5 close
POSITIVE_THRESHOLD = 0.05  # fwd_5d_max_high_pct ≥ 5% = positive outcome

HORIZONS = [1, 3, 5, 10]


def _close_in_range(o: float, h: float, l: float, c: float) -> Optional[float]:
    if h is None or l is None or c is None or h <= l:
        return None
    return (c - l) / (h - l)


def _bucket(close_in_range: Optional[float], R_at_T5_close: Optional[float]) -> str:
    """Deterministic shape label given Day-0 close-in-range + T+5 R-at-close.

    R_at_T5_close ≥ 0 means forward close ≥ entry (continuation in R-space).
    None if insufficient forward data.
    """
    if close_in_range is None:
        return "no_close_in_range"
    if R_at_T5_close is None:
        return "no_forward_data"

    is_cont = R_at_T5_close >= 0

    if close_in_range >= STRONG_CLOSE:
        return "strong_close_continuation" if is_cont else "strong_close_fade"
    elif close_in_range < WEAK_CLOSE:
        return "weak_close_continuation" if is_cont else "weak_close_fade"
    else:
        return "mid_range_continuation" if is_cont else "mid_range_fade"


async def explore(conn, days: int, csv_path: Optional[str]) -> None:
    today = date.today()
    cutoff = today - timedelta(days=days)
    # Reserve a tail for forward-25d availability
    eligible_through = today - timedelta(days=10)

    # Pull every HIGH/MODERATE EP alert in the window.
    # Defensive: alert_date must be ≤ eligible_through so all horizons settle.
    alerts = await conn.fetch("""
        SELECT a.ticker, a.alert_date, a.ep_score, a.score_tier,
               a.gap_pct, a.catalyst_quality
        FROM mi_ep_alerts a
        WHERE a.alert_date >= $1
          AND a.alert_date <= $2
          AND a.score_tier IN ('HIGH', 'MODERATE')
        ORDER BY a.alert_date, a.ticker
    """, cutoff, eligible_through)

    logger.info(f"EP cohort: {len(alerts)} HIGH/MODERATE alerts in {days}d window")
    if not alerts:
        logger.warning("Empty cohort — nothing to explore.")
        return

    # Pull all daily bars for the union of tickers in one go (faster than per-ticker)
    tickers = sorted({a["ticker"] for a in alerts})
    bars = await conn.fetch("""
        SELECT ticker, trade_date, open_price, high_price, low_price, close
        FROM mi_daily_closes
        WHERE ticker = ANY($1)
          AND trade_date >= $2
        ORDER BY ticker, trade_date
    """, tickers, cutoff - timedelta(days=15))  # 15-day lead-in for prev_5d_pct

    # Bucket bars by ticker for quick lookup
    by_ticker: dict[str, list[dict]] = defaultdict(list)
    for b in bars:
        by_ticker[b["ticker"]].append(dict(b))

    rows = []
    for a in alerts:
        ticker = a["ticker"]
        anchor_date = a["alert_date"]
        history = by_ticker.get(ticker, [])
        if not history:
            continue

        # Find anchor index
        anchor_idx = next((i for i, b in enumerate(history) if b["trade_date"] == anchor_date), None)
        if anchor_idx is None:
            continue
        anchor = history[anchor_idx]
        a_open = float(anchor["open_price"]) if anchor["open_price"] else None
        a_high = float(anchor["high_price"]) if anchor["high_price"] else None
        a_low = float(anchor["low_price"]) if anchor["low_price"] else None
        a_close = float(anchor["close"]) if anchor["close"] else None
        if None in (a_open, a_high, a_low, a_close):
            continue

        # Day-0 primitives
        close_in_range = _close_in_range(a_open, a_high, a_low, a_close)
        prev_5d_pct = None
        if anchor_idx >= 5:
            t_minus_5 = float(history[anchor_idx - 5]["close"])
            if t_minus_5 > 0:
                prev_5d_pct = (a_close / t_minus_5) - 1.0

        # Forward window
        forward = history[anchor_idx + 1 : anchor_idx + 1 + 26]  # up to T+26 calendar
        if not forward:
            continue

        # Forward shape: undercut + breakout sessions
        first_undercut = None
        first_breakout = None
        for i, b in enumerate(forward, start=1):
            f_close = float(b["close"]) if b["close"] else None
            f_high = float(b["high_price"]) if b["high_price"] else None
            if first_undercut is None and f_close is not None and f_close < a_open:
                first_undercut = i
            if first_breakout is None and f_high is not None and f_high > a_high:
                first_breakout = i

        # R-based forward simulation — entry at anchor_close, stop at anchor_low.
        # For each horizon, compute: did_stop, max_favorable_R, R_at_horizon_close.
        risk_per_share = a_close - a_low
        if risk_per_share <= 0:
            continue  # zero-range / inverted — can't compute R

        fwd: dict[int, dict[str, Optional[float]]] = {}
        for h in HORIZONS:
            if h > len(forward):
                fwd[h] = {"did_stop": None, "max_favorable_R": None,
                          "R_at_close": None, "R_with_3R_TP": None}
                continue
            window = forward[:h]
            did_stop = False
            max_R = 0.0  # max favorable R reached
            R_with_3R_TP: Optional[float] = None
            for b in window:
                f_low = float(b["low_price"]) if b["low_price"] is not None else None
                f_high = float(b["high_price"]) if b["high_price"] is not None else None
                # Stop-out check first (intraday low touched stop)
                if f_low is not None and f_low <= a_low:
                    did_stop = True
                    if R_with_3R_TP is None:
                        R_with_3R_TP = -1.0
                    break
                # Track favorable R from intraday high
                if f_high is not None:
                    bar_R = (f_high - a_close) / risk_per_share
                    if bar_R > max_R:
                        max_R = bar_R
                    # 3R take-profit check (assumes intraday fills exact)
                    if R_with_3R_TP is None and bar_R >= 3.0:
                        R_with_3R_TP = 3.0
            # If no stop and no 3R hit yet → exit at horizon close
            f_close = float(window[-1]["close"]) if window[-1]["close"] else None
            R_at_close = (f_close - a_close) / risk_per_share if f_close else None
            if R_with_3R_TP is None:
                R_with_3R_TP = R_at_close if R_at_close is not None else 0.0
            fwd[h] = {
                "did_stop": did_stop,
                "max_favorable_R": max_R,
                "R_at_close": R_at_close,
                "R_with_3R_TP": R_with_3R_TP,
            }

        # Bucket — use T+5 close-vs-anchor direction
        cont_fade_R = fwd[CONT_FADE_HORIZON]["R_at_close"]
        bucket = _bucket(close_in_range, cont_fade_R)

        rows.append({
            "ticker": ticker,
            "alert_date": anchor_date.isoformat(),
            "ep_score": a["ep_score"],
            "score_tier": a["score_tier"],
            "gap_pct": a["gap_pct"],
            "catalyst_quality": a["catalyst_quality"],
            "anchor_open": a_open, "anchor_high": a_high,
            "anchor_low": a_low, "anchor_close": a_close,
            "close_in_range": close_in_range,
            "prev_5d_pct": prev_5d_pct,
            "risk_per_share": risk_per_share,
            "first_undercut_session": first_undercut,
            "first_breakout_session": first_breakout,
            # 5d R metrics (primary horizon for sugar baby methodology)
            "did_stop_5d": fwd[5]["did_stop"],
            "max_favorable_R_5d": fwd[5]["max_favorable_R"],
            "R_at_close_5d": fwd[5]["R_at_close"],
            "R_with_3R_TP_5d": fwd[5]["R_with_3R_TP"],
            # 10d R metrics (longer hold)
            "did_stop_10d": fwd[10]["did_stop"],
            "max_favorable_R_10d": fwd[10]["max_favorable_R"],
            "R_at_close_10d": fwd[10]["R_at_close"],
            "R_with_3R_TP_10d": fwd[10]["R_with_3R_TP"],
            "bucket": bucket,
        })

    logger.info(f"Computed shape for {len(rows)} of {len(alerts)} alerts (rest had insufficient history or missing OHLC)")

    # Aggregate per bucket
    by_bucket: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        by_bucket[r["bucket"]].append(r)

    print("\n" + "=" * 110)
    print(f"TI5 — POST-EP SHAPE R-EXPECTANCY ({days}d window, {len(rows)} settled alerts)")
    print("=" * 110)
    print(f"\nEntry model: anchor_close. Stop: anchor_low. R = (price − entry) / risk_per_share")
    print(f"Thresholds: strong close-in-range ≥ {STRONG_CLOSE}, weak < {WEAK_CLOSE}\n")

    def _bucket_R_stats(bucket_rows: list[dict], horizon: str) -> dict:
        """Per-bucket R aggregations at given horizon (5d or 10d)."""
        valid = [r for r in bucket_rows if r[f"R_at_close_{horizon}"] is not None]
        if not valid:
            return {}
        n = len(valid)
        stop_rate = sum(1 for r in valid if r[f"did_stop_{horizon}"]) / n
        max_R = [r[f"max_favorable_R_{horizon}"] for r in valid]
        R_close = [r[f"R_at_close_{horizon}"] for r in valid]
        R_3R = [r[f"R_with_3R_TP_{horizon}"] for r in valid]
        # Expectancy with time-stop: mean R if exited at horizon close (or stopped at -1)
        exp_time = statistics.mean(
            (-1.0 if r[f"did_stop_{horizon}"] else r[f"R_at_close_{horizon}"])
            for r in valid
        )
        # Expectancy with 3R take-profit: simulated exit at +3R or stop
        exp_3R = statistics.mean(R_3R)
        # Profit factor: sum of positive R / |sum of negative R|
        wins = sum(r for r in R_3R if r > 0)
        losses = abs(sum(r for r in R_3R if r < 0))
        pf = wins / losses if losses > 0 else float("inf") if wins > 0 else 0
        win_rate_3R = sum(1 for r in R_3R if r > 0) / n
        return {
            "n": n,
            "stop_rate": stop_rate,
            "med_max_R": statistics.median(max_R),
            "med_R_close": statistics.median(R_close),
            "exp_time": exp_time,
            "exp_3R": exp_3R,
            "pf": pf,
            "win_rate_3R": win_rate_3R,
        }

    # Overall baseline at 5d
    baseline = _bucket_R_stats(rows, "5d")
    if baseline:
        print(f"BASELINE (all settled, T+5): "
              f"n={baseline['n']}, stop_rate={baseline['stop_rate']*100:.1f}%, "
              f"med_max_R={baseline['med_max_R']:+.2f}R, "
              f"exp_3R_TP={baseline['exp_3R']:+.2f}R, pf={baseline['pf']:.2f}\n")

    # Per-bucket — show 5d AND 10d horizons side by side
    bucket_order = [
        "strong_close_continuation", "strong_close_fade",
        "mid_range_continuation",    "mid_range_fade",
        "weak_close_continuation",   "weak_close_fade",
    ]

    for horizon, h_label in [("5d", "T+5"), ("10d", "T+10")]:
        print(f"--- {h_label} horizon ---")
        header = (f"  {'bucket':<32} {'n':>5} {'stop%':>7} "
                  f"{'medMaxR':>9} {'expTime':>9} {'exp3R':>8} "
                  f"{'pf':>6} {'wr3R':>7}")
        print(header)
        print("  " + "-" * 95)
        for b in bucket_order:
            stats = _bucket_R_stats(by_bucket.get(b, []), horizon)
            if not stats:
                continue
            base_exp = baseline.get("exp_3R", 0) if horizon == "5d" else None
            lift_marker = ""
            if (stats["exp_3R"] >= 0.5 and stats["med_max_R"] >= 3.0
                    and stats["n"] >= 30):
                lift_marker = " ★"
            print(f"  {b:<32} {stats['n']:>5} {stats['stop_rate']*100:>6.1f}% "
                  f"{stats['med_max_R']:>+8.2f}R {stats['exp_time']:>+8.2f}R "
                  f"{stats['exp_3R']:>+7.2f}R {stats['pf']:>6.2f} "
                  f"{stats['win_rate_3R']*100:>6.1f}%{lift_marker}")
        print()

    print("Sanity gate (per TI5 memo): ≥ 200 total + ≥ 30 per bucket of interest")
    print("Decision rule: ★ marks buckets with med_max_R ≥ 3R AND exp_3R ≥ +0.5R AND n ≥ 30")
    print()
    print("Methodology note: per Pradeep/Qullamaggie, expectancy in R is the edge metric.")
    print("Win rate alone is misleading — 20% × 10R = +1.2R/trade beats 60% × 1R = +0.2R/trade.")
    print("medMaxR shows the favorable runway available; exp_3R shows realized R with 3R TP.")

    if csv_path:
        with open(csv_path, "w", newline="") as f:
            if rows:
                w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
                w.writeheader()
                w.writerows(rows)
        logger.info(f"Wrote {len(rows)} rows to {csv_path}")


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=180,
                        help="Lookback window in days (default 180)")
    parser.add_argument("--csv", type=str, default=None,
                        help="Output CSV path (optional)")
    args = parser.parse_args()

    import os
    pwd = os.environ.get("POSTGRES_PASSWORD", "")
    conn = await asyncpg.connect(
        user="apollo", password=pwd, database="apollo",
        host="postgres", port=5432,
    )
    try:
        await explore(conn, args.days, args.csv)
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
