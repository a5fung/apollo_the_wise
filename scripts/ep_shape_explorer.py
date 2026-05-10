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

  Forward returns at each horizon: fwd_close_pct, fwd_max_high_pct.

Buckets by deterministic shape labels (8 total) → reports base rates per
bucket vs overall EP cohort baseline. Bucket with materially higher
forward-5d positive rate is a candidate for v1 detector promotion (per
TI5 backlog memo + advisor refinements).

Sanity gate before any v1 ship: ≥ 200 anchors total + ≥ 30 anchors per
bucket of interest. If a shape shows ≥ 5pp lift over baseline forward-5d
positive rate, build a one-pattern detector.

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


def _bucket(close_in_range: Optional[float], cont_fade_pct: Optional[float]) -> str:
    """Deterministic shape label given Day-0 close-in-range + T+5 close-vs-anchor.

    cont_fade_pct = (close_T+5 / close_T+0) - 1. None if insufficient forward data.
    """
    if close_in_range is None:
        return "no_close_in_range"
    if cont_fade_pct is None:
        return "no_forward_data"

    # Continuation if forward close ≥ anchor close, fade if below
    is_cont = cont_fade_pct >= 0

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

        # Forward returns at each horizon
        fwd: dict[int, dict[str, Optional[float]]] = {}
        for h in HORIZONS:
            if h <= len(forward):
                window = forward[:h]
                f_close = float(window[-1]["close"]) if window[-1]["close"] else None
                f_max_high = max(
                    (float(b["high_price"]) for b in window if b["high_price"] is not None),
                    default=None,
                )
                fwd[h] = {
                    "fwd_close_pct": (f_close / a_close - 1.0) if f_close else None,
                    "fwd_max_high_pct": (f_max_high / a_close - 1.0) if f_max_high else None,
                }
            else:
                fwd[h] = {"fwd_close_pct": None, "fwd_max_high_pct": None}

        # Bucket
        cont_fade = fwd[CONT_FADE_HORIZON]["fwd_close_pct"]
        bucket = _bucket(close_in_range, cont_fade)

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
            "first_undercut_session": first_undercut,
            "first_breakout_session": first_breakout,
            "fwd_1d_close_pct": fwd[1]["fwd_close_pct"],
            "fwd_3d_close_pct": fwd[3]["fwd_close_pct"],
            "fwd_5d_close_pct": fwd[5]["fwd_close_pct"],
            "fwd_10d_close_pct": fwd[10]["fwd_close_pct"],
            "fwd_1d_max_high_pct": fwd[1]["fwd_max_high_pct"],
            "fwd_3d_max_high_pct": fwd[3]["fwd_max_high_pct"],
            "fwd_5d_max_high_pct": fwd[5]["fwd_max_high_pct"],
            "fwd_10d_max_high_pct": fwd[10]["fwd_max_high_pct"],
            "bucket": bucket,
        })

    logger.info(f"Computed shape for {len(rows)} of {len(alerts)} alerts (rest had insufficient history or missing OHLC)")

    # Aggregate per bucket
    by_bucket: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        by_bucket[r["bucket"]].append(r)

    print("\n" + "=" * 100)
    print(f"TI5 — POST-EP SHAPE BUCKETS ({days}d window, {len(rows)} settled alerts)")
    print("=" * 100)
    print(f"\nThresholds: strong ≥ {STRONG_CLOSE}, weak < {WEAK_CLOSE}, "
          f"continuation = fwd_{CONT_FADE_HORIZON}d close ≥ anchor close")
    print(f"Positive outcome: fwd_5d_max_high_pct ≥ {POSITIVE_THRESHOLD*100:.0f}%\n")

    # Overall baseline
    valid_5d = [r for r in rows if r["fwd_5d_max_high_pct"] is not None]
    baseline_pos_rate = sum(1 for r in valid_5d if r["fwd_5d_max_high_pct"] >= POSITIVE_THRESHOLD) / max(1, len(valid_5d))
    baseline_med_high = statistics.median(r["fwd_5d_max_high_pct"] for r in valid_5d) if valid_5d else 0
    baseline_med_close = statistics.median(r["fwd_5d_close_pct"] for r in valid_5d if r["fwd_5d_close_pct"] is not None) if valid_5d else 0
    print(f"BASELINE (all settled): n={len(valid_5d)}, "
          f"pos_rate={baseline_pos_rate*100:.1f}%, "
          f"med_5d_high={baseline_med_high*100:+.1f}%, "
          f"med_5d_close={baseline_med_close*100:+.1f}%\n")

    # Per-bucket rows
    header = f"  {'bucket':<32} {'n':>5} {'pos%':>7} {'lift':>7} {'med5dHi':>9} {'med5dCl':>9} {'medGap':>7}"
    print(header)
    print("  " + "-" * 80)
    bucket_order = [
        "strong_close_continuation", "strong_close_fade",
        "mid_range_continuation",    "mid_range_fade",
        "weak_close_continuation",   "weak_close_fade",
        "no_forward_data", "no_close_in_range",
    ]
    for b in bucket_order:
        bucket_rows = by_bucket.get(b, [])
        if not bucket_rows:
            continue
        valid = [r for r in bucket_rows if r["fwd_5d_max_high_pct"] is not None]
        if not valid:
            continue
        pos_rate = sum(1 for r in valid if r["fwd_5d_max_high_pct"] >= POSITIVE_THRESHOLD) / len(valid)
        med_high = statistics.median(r["fwd_5d_max_high_pct"] for r in valid)
        cls = [r["fwd_5d_close_pct"] for r in valid if r["fwd_5d_close_pct"] is not None]
        med_close = statistics.median(cls) if cls else 0
        gaps = [r["gap_pct"] for r in valid if r["gap_pct"] is not None]
        med_gap = statistics.median(gaps) if gaps else 0
        lift = pos_rate - baseline_pos_rate
        marker = " ★" if abs(lift) >= 0.05 and len(valid) >= 30 else ""
        print(f"  {b:<32} {len(valid):>5} {pos_rate*100:>6.1f}% {lift*100:>+6.1f} "
              f"{med_high*100:>+8.1f}% {med_close*100:>+8.1f}% {med_gap:>6.1f}%{marker}")

    print()
    print("Sanity gate (per TI5 memo): ≥ 200 total + ≥ 30 per bucket of interest")
    print("Decision rule: ★ marks buckets with ≥5pp lift AND n ≥ 30 → v1 detector candidate")

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
