"""
Dead-zone backfill: calibrate session RVOL@T threshold for the 9:30-9:44 window.

Background
----------
Apollo's 9:30-9:44 EP volume gate uses raw `today_volume / 20d_daily_ADV`,
which compares 14 minutes of cumulative volume to a full-day average. The
ratio is structurally near-zero in the first 14 minutes and rejects valid
EPs with thin pre-market (FTAI/PI/GKOS on 2026-04-30 — all detected late
at 9:50+ after the 9:45 projection branch finally kicked in, which puts
them out of the ORB submission window).

The fix is to gate by RVOL@T (session anchor) just like pre-9:30 already
does — but the threshold must be picked from data, not by guessing. This
script replays the last N days, computes session-anchor RVOL@T at three
decision minutes (9:35/9:40/9:44) for two cohorts:

  Cohort A — HIGHs (n~50/30d): tickers that became HIGH on alert_date.
    These passed the existing gate. We want their RVOL@T distribution
    so we know what "true positive" looks like.

  Cohort B — dead-zoned (n~85/30d): tickers logged in mi_ep_scan_log
    with filter_reason matching post-open low rel_volume that did NOT
    become HIGH that day. These are the candidates the new gate could
    rescue if the threshold is set correctly.

Each row gets a forward-5d return label (positive if fwd_5d >= 10%).
The summary prints precision/recall for cohort B at thresholds
{1.0, 1.5, 2.0} so we can pick the threshold that maximizes precision
while keeping recall >= 50% of true positives.

Read-only — pulls from mi_ep_alerts, mi_ep_scan_log, mi_daily_closes,
mi_minute_volume_curves; calls Polygon for minute bars. No DB writes.

Run on prod (the global _polygon_lock is shared with live EP scans —
prefer after 16:00 ET or before 07:00 ET):

    docker exec apollo-market python -m scripts.backfill_dead_zone
    docker exec apollo-market python -m scripts.backfill_dead_zone --days 60
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import logging
from collections import defaultdict
from datetime import date, datetime, timedelta
from statistics import median
from zoneinfo import ZoneInfo

from agents.market_intelligence.collector import get_minute_bars
from agents.market_intelligence.db import get_pool, get_minute_volume_baseline

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

_ET = ZoneInfo("America/New_York")

# Decision minutes since session open (9:30 ET = ET clock minute 570)
SESSION_OPEN_MIN = 9 * 60 + 30
DECISION_OFFSETS = [5, 10, 14]  # 9:35, 9:40, 9:44 — the three pre-9:45 scan slots
THRESHOLDS = [1.0, 1.5, 2.0]
LABEL_THRESHOLD = 0.10  # forward 5d return >= 10% = positive label

CSV_COLS = [
    "cohort", "ticker", "alert_date",
    "score_tier", "gap_pct", "filter_reason",
    "rvol_at_5", "rvol_at_10", "rvol_at_14",
    "baseline_n_at_14",
    "close_at_alert", "max_close_5d", "fwd_5d_pct",
    "label",
]


async def fetch_cohorts(days: int) -> tuple[list[dict], list[dict]]:
    """Return (cohort_a_highs, cohort_b_deadzone) over trailing `days`."""
    pool = await get_pool()
    cutoff = date.today() - timedelta(days=days)
    async with pool.acquire() as conn:
        a_rows = await conn.fetch(
            """SELECT ticker, alert_date, score_tier, gap_pct, NULL::text AS filter_reason
               FROM mi_ep_alerts
               WHERE alert_date > $1 AND score_tier = 'HIGH'
               ORDER BY alert_date DESC, ticker""",
            cutoff,
        )
        b_rows = await conn.fetch(
            """SELECT s.ticker, s.scan_date AS alert_date,
                      COALESCE(s.score_tier, 'NONE') AS score_tier,
                      s.gap_pct, s.filter_reason
               FROM mi_ep_scan_log s
               LEFT JOIN mi_ep_alerts a
                 ON a.ticker = s.ticker
                AND a.alert_date = s.scan_date
                AND a.score_tier = 'HIGH'
               WHERE s.scan_date > $1
                 AND s.filter_reason LIKE '%rel_vol%post-open%'
                 AND a.ticker IS NULL
               ORDER BY s.scan_date DESC, s.ticker""",
            cutoff,
        )
    return [dict(r) for r in a_rows], [dict(r) for r in b_rows]


async def fetch_close_series(ticker: str, alert_d: date, ahead_days: int = 12) -> dict[date, float]:
    """Return {trade_date: close} for ticker on [alert_d, alert_d+ahead_days]."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT trade_date, close FROM mi_daily_closes
               WHERE ticker = $1 AND trade_date BETWEEN $2 AND $3
               ORDER BY trade_date""",
            ticker, alert_d, alert_d + timedelta(days=ahead_days),
        )
    return {r["trade_date"]: float(r["close"]) for r in rows}


def compute_cum_at_offsets(bars: list[dict], alert_d: date) -> dict[int, int]:
    """Return {minute_offset_from_open: cumulative_session_volume}.

    `bars` is the full minute-bar response; we filter to alert_d's regular
    session (9:30-15:59 ET) and accumulate by minute.
    """
    per_minute_vol: dict[int, int] = defaultdict(int)
    for b in bars:
        try:
            t_ms = b.get("t")
            v = b.get("v") or 0
            if t_ms is None or v <= 0:
                continue
            dt_et = datetime.fromtimestamp(int(t_ms) / 1000.0, tz=_ET)
            if dt_et.date() != alert_d:
                continue
            m = dt_et.hour * 60 + dt_et.minute
            if m < SESSION_OPEN_MIN or m >= 16 * 60:
                continue
            per_minute_vol[m] += int(v)
        except Exception:
            continue

    # Cumulative from open at each requested offset
    out: dict[int, int] = {}
    cum = 0
    for offset in range(0, max(DECISION_OFFSETS) + 1):
        cum += per_minute_vol.get(SESSION_OPEN_MIN + offset, 0)
        if offset in DECISION_OFFSETS:
            out[offset] = cum
    return out


async def process_row(cohort: str, row: dict) -> dict | None:
    """Compute rvol@t at 5/10/14 and forward return for one cohort row."""
    ticker = row["ticker"]
    alert_d = row["alert_date"]
    date_str = alert_d.strftime("%Y-%m-%d")

    bars = await get_minute_bars(ticker, date_str, date_str)
    if not bars:
        return None

    cum_at = compute_cum_at_offsets(bars, alert_d)
    if not cum_at or cum_at.get(14, 0) == 0:
        return None  # no session trading — likely halt or data gap

    rvols: dict[int, float | None] = {}
    baseline_n_14 = 0
    for offset in DECISION_OFFSETS:
        et_min = SESSION_OPEN_MIN + offset
        baseline = await get_minute_volume_baseline(ticker, "session", et_min)
        if not baseline or float(baseline["mean_cum_vol"] or 0) <= 0:
            rvols[offset] = None
            continue
        mean = float(baseline["mean_cum_vol"])
        rvols[offset] = cum_at[offset] / mean if mean > 0 else None
        if offset == 14:
            baseline_n_14 = int(baseline["sample_n"] or 0)

    closes = await fetch_close_series(ticker, alert_d)
    if not closes or alert_d not in closes:
        return None
    anchor_close = closes[alert_d]
    fwd_dates = sorted(d for d in closes if d > alert_d)[:5]
    if not fwd_dates or anchor_close <= 0:
        return None
    max_fwd = max(closes[d] for d in fwd_dates)
    fwd_pct = (max_fwd / anchor_close) - 1.0
    label = "positive" if fwd_pct >= LABEL_THRESHOLD else "negative"

    return {
        "cohort": cohort,
        "ticker": ticker,
        "alert_date": alert_d.isoformat(),
        "score_tier": row.get("score_tier"),
        "gap_pct": row.get("gap_pct"),
        "filter_reason": (row.get("filter_reason") or "")[:80],
        "rvol_at_5": round(rvols[5], 3) if rvols[5] is not None else None,
        "rvol_at_10": round(rvols[10], 3) if rvols[10] is not None else None,
        "rvol_at_14": round(rvols[14], 3) if rvols[14] is not None else None,
        "baseline_n_at_14": baseline_n_14,
        "close_at_alert": round(anchor_close, 4),
        "max_close_5d": round(max_fwd, 4),
        "fwd_5d_pct": round(fwd_pct * 100, 2),
        "label": label,
    }


def summarize(results: list[dict]) -> None:
    """Print median rvol@t by cohort+label, plus precision/recall for cohort B."""
    by_key: dict[tuple[str, str], list[float]] = defaultdict(list)
    for r in results:
        rv = r.get("rvol_at_14")
        if rv is None:
            continue
        by_key[(r["cohort"], r["label"])].append(rv)

    print("\n=== Median rvol@14 by cohort × label ===")
    print(f"{'cohort':<10} {'label':<10} {'n':>4} {'median':>8} {'p25':>8} {'p75':>8}")
    for (cohort, label), vals in sorted(by_key.items()):
        if not vals:
            continue
        vals_sorted = sorted(vals)
        n = len(vals_sorted)
        med = vals_sorted[n // 2]
        p25 = vals_sorted[n // 4] if n >= 4 else vals_sorted[0]
        p75 = vals_sorted[(3 * n) // 4] if n >= 4 else vals_sorted[-1]
        print(f"{cohort:<10} {label:<10} {n:>4} {med:>8.2f} {p25:>8.2f} {p75:>8.2f}")

    # Cohort B precision/recall sweep — at threshold X, what fraction of
    # gated tickers are true positives (precision), and what fraction of
    # true positives are flagged (recall).
    cohort_b = [r for r in results if r["cohort"] == "deadzone" and r.get("rvol_at_14") is not None]
    total_pos = sum(1 for r in cohort_b if r["label"] == "positive")
    print(f"\n=== Cohort B (dead-zone) precision/recall sweep ===")
    print(f"Cohort B size: {len(cohort_b)} (positives: {total_pos})")
    print(f"{'threshold':>10} {'flagged':>8} {'tp':>4} {'precision':>10} {'recall':>8}")
    for thresh in THRESHOLDS:
        flagged = [r for r in cohort_b if r["rvol_at_14"] >= thresh]
        tp = sum(1 for r in flagged if r["label"] == "positive")
        prec = tp / len(flagged) if flagged else 0.0
        rec = tp / total_pos if total_pos else 0.0
        print(f"{thresh:>10.1f} {len(flagged):>8} {tp:>4} {prec:>10.2%} {rec:>8.2%}")

    # Coverage check — fraction of cohort missing baseline
    no_baseline = sum(1 for r in results if r.get("rvol_at_14") is None)
    print(f"\n=== Coverage ===")
    print(f"Rows missing rvol@14 baseline: {no_baseline} / {len(results)} "
          f"({no_baseline / len(results) * 100:.1f}% if any)" if results else "no results")


async def main(days: int, out_path: str) -> None:
    cohort_a, cohort_b = await fetch_cohorts(days)
    logger.info(f"cohort A (HIGH): {len(cohort_a)} rows")
    logger.info(f"cohort B (deadzone): {len(cohort_b)} rows")

    tasks = (
        [process_row("high", r) for r in cohort_a]
        + [process_row("deadzone", r) for r in cohort_b]
    )
    raw = await asyncio.gather(*tasks)
    results = [r for r in raw if r is not None]
    logger.info(f"computed {len(results)} / {len(tasks)} rows")

    with open(out_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CSV_COLS)
        w.writeheader()
        for r in results:
            w.writerow(r)
    logger.info(f"wrote {out_path}")
    summarize(results)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument("--out", default="/tmp/dead_zone_backfill.csv")
    args = parser.parse_args()
    asyncio.run(main(days=args.days, out_path=args.out))
