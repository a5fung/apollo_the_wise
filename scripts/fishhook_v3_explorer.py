"""TI3 Fishhook V3 Explorer (Stage 0 — undercut & reclaim cohort sweep).

V1 (90-day MAGNA53-failure cohort + VCP "tight base" metric) failed on cohort
starvation (only 2 strict-cohort tuples in 180d) AND wrong primitive (the real
Fishhook is a Liquidity Trap, not a tight base). V3 reframes: anchor = Day 1
Open of an 8%+ gap-up that closes green; trap = drift below anchor; trigger =
reclaim of anchor on a forward session.

Pure SQL on `mi_daily_closes`. Read-only. No new tables. CSV only.

Output cols (per anchor):
  ticker, anchor_date, prev_close, anchor_open, anchor_close, gap_pct,
  in_top2000_universe, in_ep_alerts_universe,
  washout_low, washout_session_offset, drift_pct_max, watchlist_promoted,
  reclaim_session_offset, reclaim_session_open, reclaim_session_close,
  reclaim_open_vs_anchor_pct, actual_entry_price,
  fwd_1d_high_pct, fwd_3d_high_pct, fwd_5d_high_pct, fwd_10d_high_pct,
  fwd_1d_close_pct, fwd_3d_close_pct, fwd_5d_close_pct, fwd_10d_close_pct,
  R_5d, invalidated_within_5d, n_fwd_sessions_available,
  label

Caveat: daily-bar reclaim approximates intraday fill — `R_5d` is therefore
optimistic. v1 detector should lift to 1-min for exact fill timing.

Run on prod after 16:00 ET or before 07:00 ET:
    docker exec apollo-market python -m scripts.fishhook_v3_explorer
    docker exec apollo-market python -m scripts.fishhook_v3_explorer \\
        --days 180 --label-threshold 0.10 --out /tmp/fishhook_v3.csv
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import logging
from collections import defaultdict
from datetime import date, timedelta

from agents.market_intelligence.db import get_pool

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

CSV_COLS = [
    "ticker", "anchor_date", "prev_close", "anchor_open", "anchor_close", "gap_pct",
    "in_top2000_universe", "in_ep_alerts_universe",
    "washout_low", "washout_session_offset", "drift_pct_max", "watchlist_promoted",
    "reclaim_session_offset", "reclaim_session_open", "reclaim_session_close",
    "reclaim_open_vs_anchor_pct", "actual_entry_price",
    "fwd_1d_high_pct", "fwd_3d_high_pct", "fwd_5d_high_pct", "fwd_10d_high_pct",
    "fwd_1d_close_pct", "fwd_3d_close_pct", "fwd_5d_close_pct", "fwd_10d_close_pct",
    "R_5d", "invalidated_within_5d", "n_fwd_sessions_available",
    "label",
]


async def fetch_anchors(
    start_date: date, end_date: date, gap_floor: float, top_n: int
) -> list[dict]:
    """Returns one row per qualifying anchor.

    Gates (per V3 plan):
      - prev_close from LAG; gap_pct = (open_price - prev_close) / prev_close >= gap_floor
      - close > open_price (Day 1 institutional accumulation; with 8% gap floor
        these together close the WU 2026-04-24 wick-fill bug — gap_pct >= 0.08
        forces open above prev_close, then close > open forces close above open)
      - Security type CS/ADRC OR ticker not in mi_security_types (mirrors 9M ETF flood fix)
      - In top-N by trailing 20-session AVG(close * volume) for that anchor_date
        (close >= $10 prefilter; sub-$10 % swings pollute return labels)
        OR in mi_ep_alerts for that anchor_date (recent EP candidate carve-out)
    """
    pool = await get_pool()
    # ADV window needs ~30 trading days of history before the earliest anchor
    # for the 20-PRECEDING-1-PRECEDING window to populate.
    dv_start = start_date - timedelta(days=45)
    sql = """
        WITH dv AS (
            SELECT ticker, trade_date,
                   AVG(close * volume) OVER (
                       PARTITION BY ticker ORDER BY trade_date
                       ROWS BETWEEN 20 PRECEDING AND 1 PRECEDING
                   ) AS adv_dollar_20
            FROM mi_daily_closes
            WHERE close >= 10.00
              AND trade_date BETWEEN $4 AND $2
        ),
        ranked AS (
            SELECT ticker, trade_date,
                   ROW_NUMBER() OVER (
                       PARTITION BY trade_date
                       ORDER BY adv_dollar_20 DESC NULLS LAST
                   ) AS rk
            FROM dv WHERE adv_dollar_20 IS NOT NULL
        ),
        candidates AS (
            SELECT
                d.ticker, d.trade_date AS anchor_date,
                d.open_price AS anchor_open, d.close AS anchor_close,
                LAG(d.close) OVER (PARTITION BY d.ticker ORDER BY d.trade_date) AS prev_close
            FROM mi_daily_closes d
            WHERE d.trade_date BETWEEN ($1::date - INTERVAL '7 days') AND $2
        )
        SELECT
            c.ticker,
            c.anchor_date,
            c.anchor_open,
            c.anchor_close,
            c.prev_close,
            (c.anchor_open - c.prev_close) / c.prev_close AS gap_pct,
            COALESCE(r.rk <= $5, FALSE) AS in_top2000_universe,
            EXISTS (
                SELECT 1 FROM mi_ep_alerts ea
                WHERE ea.ticker = c.ticker AND ea.alert_date = c.anchor_date
            ) AS in_ep_alerts_universe
        FROM candidates c
        LEFT JOIN ranked r
          ON r.ticker = c.ticker AND r.trade_date = c.anchor_date
        LEFT JOIN mi_security_types st ON st.ticker = c.ticker
        WHERE c.anchor_date BETWEEN $1 AND $2
          AND c.prev_close > 0
          AND c.anchor_open IS NOT NULL
          AND c.anchor_close > c.anchor_open
          AND (c.anchor_open - c.prev_close) / c.prev_close >= $3
          AND (st.security_type IN ('CS','ADRC') OR st.ticker IS NULL)
          AND (
              COALESCE(r.rk <= $5, FALSE)
              OR EXISTS (
                  SELECT 1 FROM mi_ep_alerts ea
                  WHERE ea.ticker = c.ticker AND ea.alert_date = c.anchor_date
              )
          )
        ORDER BY c.anchor_date, c.ticker
    """
    async with pool.acquire() as conn:
        rows = await conn.fetch(sql, start_date, end_date, gap_floor, dv_start, top_n)
    return [dict(r) for r in rows]


async def fetch_forward_ohlc(
    tickers: list[str], from_date: date, to_date: date
) -> dict[str, list[dict]]:
    """One batch fetch of all OHLC for `tickers` between dates, keyed ticker -> ascending list."""
    pool = await get_pool()
    sql = """
        SELECT ticker, trade_date, open_price, high_price, low_price, close
        FROM mi_daily_closes
        WHERE ticker = ANY($1)
          AND trade_date BETWEEN $2 AND $3
        ORDER BY ticker, trade_date
    """
    async with pool.acquire() as conn:
        rows = await conn.fetch(sql, tickers, from_date, to_date)
    by_ticker: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        by_ticker[r["ticker"]].append(dict(r))
    return by_ticker


def _walk(
    anchor: dict,
    forward: list[dict],
    watch_start: int,
    watch_end: int,
    reclaim_window: int,
    label_threshold: float,
) -> dict:
    """Compute trap → reclaim → fwd returns for one anchor, return CSV row."""
    out = {k: None for k in CSV_COLS}
    out["ticker"] = anchor["ticker"]
    out["anchor_date"] = anchor["anchor_date"]
    out["prev_close"] = float(anchor["prev_close"])
    out["anchor_open"] = float(anchor["anchor_open"])
    out["anchor_close"] = float(anchor["anchor_close"])
    out["gap_pct"] = float(anchor["gap_pct"])
    out["in_top2000_universe"] = bool(anchor["in_top2000_universe"])
    out["in_ep_alerts_universe"] = bool(anchor["in_ep_alerts_universe"])

    anchor_open = float(anchor["anchor_open"])
    if not forward:
        out["label"] = "insufficient_data"
        out["n_fwd_sessions_available"] = 0
        return out

    out["n_fwd_sessions_available"] = len(forward)

    # Step 2: trap window
    # washout_low tracked from T+1 onward (drift can begin earliest possible)
    # drift_pct_max + watchlist_promoted evaluated only inside [watch_start, watch_end]
    # first_promotion_offset = first session in [watch_start, watch_end] with close < anchor_open
    washout_low = None
    washout_offset = None
    drift_pct_max = None
    watchlist_promoted = False
    first_promotion_offset = None

    for i, bar in enumerate(forward, start=1):
        low = bar["low_price"]
        close = bar["close"]
        if low is None or close is None:
            continue
        low = float(low)
        close = float(close)
        # washout_low: T+1..T_now (latest session in scope = watch_end)
        if i <= watch_end:
            if washout_low is None or low < washout_low:
                washout_low = low
                washout_offset = i
        # drift + watchlist eval: T+watch_start..T+watch_end
        if watch_start <= i <= watch_end:
            drift = (close - anchor_open) / anchor_open
            if drift_pct_max is None or drift < drift_pct_max:
                drift_pct_max = drift
            if close < anchor_open:
                watchlist_promoted = True
                if first_promotion_offset is None:
                    first_promotion_offset = i

    out["washout_low"] = washout_low
    out["washout_session_offset"] = washout_offset
    out["drift_pct_max"] = drift_pct_max
    out["watchlist_promoted"] = watchlist_promoted

    if not watchlist_promoted:
        out["label"] = "no_promotion"
        return out

    # Step 3: reclaim event — first session AT OR AFTER promotion where high >= anchor_open.
    # Search starts at first_promotion_offset (not watch_start) — pre-trap crosses don't count
    # (e.g. T+3 high $105 then T+5 promotion: the T+3 cross is not a reclaim of a trap that
    # hadn't yet formed). Window cap: reclaim_window sessions absolute (default T+25).
    reclaim_idx = None  # 0-based index into forward[]
    for i, bar in enumerate(forward, start=1):
        if i < first_promotion_offset:
            continue
        if i > reclaim_window:
            break
        high = bar["high_price"]
        if high is None:
            continue
        if float(high) >= anchor_open:
            reclaim_idx = i - 1  # forward[] is 0-based
            break

    if reclaim_idx is None:
        out["label"] = "no_reclaim"
        return out

    reclaim_bar = forward[reclaim_idx]
    reclaim_offset = reclaim_idx + 1  # T+offset
    reclaim_open = float(reclaim_bar["open_price"]) if reclaim_bar["open_price"] is not None else None
    reclaim_close = float(reclaim_bar["close"]) if reclaim_bar["close"] is not None else None
    out["reclaim_session_offset"] = reclaim_offset
    out["reclaim_session_open"] = reclaim_open
    out["reclaim_session_close"] = reclaim_close

    if reclaim_open is None:
        # malformed bar — skip forward-returns
        out["label"] = "insufficient_data"
        return out

    out["reclaim_open_vs_anchor_pct"] = (reclaim_open - anchor_open) / anchor_open
    actual_entry = max(anchor_open, reclaim_open)
    out["actual_entry_price"] = actual_entry

    # Step 4: forward returns from reclaim, inclusive of reclaim session
    # Fwd-N spans forward[reclaim_idx ... reclaim_idx + N - 1]
    fwd_window = forward[reclaim_idx : reclaim_idx + 10]
    n_fwd_after_reclaim = len(fwd_window)

    for n in (1, 3, 5, 10):
        if n_fwd_after_reclaim < n:
            continue  # leave NULL
        sub = fwd_window[:n]
        max_high = max(
            (float(b["high_price"]) for b in sub if b["high_price"] is not None),
            default=None,
        )
        nth_close = sub[-1]["close"]
        if max_high is not None and actual_entry > 0:
            out[f"fwd_{n}d_high_pct"] = (max_high - actual_entry) / actual_entry
        if nth_close is not None and actual_entry > 0:
            out[f"fwd_{n}d_close_pct"] = (float(nth_close) - actual_entry) / actual_entry

    # invalidation: any close in next 5 sessions < washout_low
    invalidated = False
    if washout_low is not None and n_fwd_after_reclaim >= 1:
        for b in fwd_window[:5]:
            c = b["close"]
            if c is not None and float(c) < washout_low:
                invalidated = True
                break
    out["invalidated_within_5d"] = invalidated if n_fwd_after_reclaim >= 1 else None

    # R_5d: (fwd_5d_max_high - actual_entry) / (actual_entry - washout_low)
    fwd_5d_high_pct = out["fwd_5d_high_pct"]
    if fwd_5d_high_pct is not None and washout_low is not None:
        fwd_5d_max_high = fwd_5d_high_pct * actual_entry + actual_entry
        risk = actual_entry - washout_low
        if risk > 0:
            out["R_5d"] = (fwd_5d_max_high - actual_entry) / risk

    # Label from 5d horizon
    if fwd_5d_high_pct is None:
        out["label"] = "insufficient_data"
    elif fwd_5d_high_pct >= label_threshold:
        out["label"] = "positive"
    else:
        out["label"] = "negative"

    return out


async def run(
    days: int,
    out_path: str,
    label_threshold: float,
    gap_floor: float,
    top_n: int,
    watch_start: int,
    watch_end: int,
    reclaim_window: int,
) -> None:
    today = date.today()
    end_date = today - timedelta(days=15)  # leave room for ≥10 fwd sessions
    start_date = today - timedelta(days=days)

    logger.info(
        f"V3 explorer: anchor window {start_date}..{end_date} "
        f"(days={days}, gap_floor={gap_floor:.0%}, top_n={top_n}, "
        f"watch=T+{watch_start}..T+{watch_end}, reclaim_window={reclaim_window}, "
        f"label≥{label_threshold:.0%})"
    )

    anchors = await fetch_anchors(start_date, end_date, gap_floor, top_n)
    logger.info(f"Anchors gated: {len(anchors)}")
    if not anchors:
        logger.warning("Empty cohort — nothing to write.")
        return

    in_top = sum(1 for a in anchors if a["in_top2000_universe"])
    in_ep = sum(1 for a in anchors if a["in_ep_alerts_universe"])
    only_ep = sum(
        1 for a in anchors
        if a["in_ep_alerts_universe"] and not a["in_top2000_universe"]
    )
    logger.info(
        f"Universe split: top2000={in_top}, ep_alerts={in_ep}, ep_only={only_ep} "
        f"(EP-only adds {only_ep / len(anchors) * 100:.1f}% incremental)"
    )

    # Forward OHLC fetch — bound to anchor tickers + anchor window + 35d trailing
    tickers = sorted({a["ticker"] for a in anchors})
    fwd_from = start_date + timedelta(days=1)
    fwd_to = end_date + timedelta(days=watch_end + reclaim_window + 15)
    logger.info(
        f"Fetching forward OHLC: {len(tickers)} tickers, "
        f"{fwd_from}..{fwd_to}"
    )
    by_ticker = await fetch_forward_ohlc(tickers, fwd_from, fwd_to)

    # Per-anchor: take all bars strictly after anchor_date
    rows: list[dict] = []
    label_counts: dict[str, int] = defaultdict(int)
    for a in anchors:
        all_bars = by_ticker.get(a["ticker"], [])
        forward = [b for b in all_bars if b["trade_date"] > a["anchor_date"]]
        forward = forward[: watch_end + reclaim_window + 11]  # cap
        row = _walk(a, forward, watch_start, watch_end, reclaim_window, label_threshold)
        rows.append(row)
        label_counts[row["label"]] += 1

    with open(out_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CSV_COLS)
        w.writeheader()
        for r in rows:
            w.writerow(r)

    logger.info(f"Wrote {len(rows)} rows to {out_path}")
    logger.info(f"Label counts: {dict(label_counts)}")

    # Headline stats
    promoted = [r for r in rows if r["watchlist_promoted"]]
    reclaimed = [r for r in promoted if r["reclaim_session_offset"] is not None]
    pos = [r for r in reclaimed if r["label"] == "positive"]
    if promoted:
        logger.info(
            f"Promotion rate: {len(promoted)}/{len(rows)} = "
            f"{len(promoted) / len(rows) * 100:.1f}%"
        )
    if reclaimed:
        logger.info(
            f"Reclaim rate among promoted: {len(reclaimed)}/{len(promoted)} = "
            f"{len(reclaimed) / len(promoted) * 100:.1f}%"
        )
    if pos:
        rs = sorted(r["R_5d"] for r in pos if r["R_5d"] is not None)
        if rs:
            med = rs[len(rs) // 2]
            logger.info(
                f"Positives: {len(pos)} (median R_5d={med:.2f}, "
                f"min={rs[0]:.2f}, max={rs[-1]:.2f})"
            )


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    p.add_argument("--days", type=int, default=180,
                   help="Trailing window for anchor sweep (default 180)")
    p.add_argument("--out", default="/tmp/fishhook_v3.csv",
                   help="Output CSV path (default /tmp/fishhook_v3.csv)")
    p.add_argument("--label-threshold", type=float, default=0.10,
                   help="Forward 5d high required for positive label (default 0.10 = 10%%)")
    p.add_argument("--gap-floor", type=float, default=0.08,
                   help="Min gap_pct for anchor (default 0.08 = 8%%)")
    p.add_argument("--top-n", type=int, default=2000,
                   help="Top N by trailing 20d $-volume (default 2000)")
    p.add_argument("--watch-window-start", type=int, default=3,
                   help="Trap watch window start session offset (default T+3)")
    p.add_argument("--watch-window-end", type=int, default=10,
                   help="Trap watch window end session offset (default T+10)")
    p.add_argument("--reclaim-window", type=int, default=25,
                   help="Reclaim search window in sessions from watch start (default 25)")
    args = p.parse_args()

    asyncio.run(run(
        days=args.days,
        out_path=args.out,
        label_threshold=args.label_threshold,
        gap_floor=args.gap_floor,
        top_n=args.top_n,
        watch_start=args.watch_window_start,
        watch_end=args.watch_window_end,
        reclaim_window=args.reclaim_window,
    ))


if __name__ == "__main__":
    main()
