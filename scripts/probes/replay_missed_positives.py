"""Day 1 catchability replay for missed-positive HIGH alerts.

For each (ticker, alert_date) where Apollo flagged HIGH but didn't enter
AND the stock went on to make ≥10% in 5 days, replay the first 15 minutes:

  - 1-min ORB = bars[0] high/low (the live entry mechanism)
  - ORB range % of open price (stop-width gate: must be ≤15%)
  - First minute price broke ORB high (proxy for "would have triggered")
  - Last close 9:30-9:44 vs ORB midpoint (fade check)
  - Fade-from-orb at any point (proxy for what live fade guard would catch)

Output: per-row Day 1 verdict — catchable / fade_dead / stop_too_wide /
no_break / no_bars. Plus Day 2 sugar-baby check (close in top 25% of range,
net up ≥3%, dollar volume ≥ $50M) so we know which ones could have been
entered as 9M Day 2 instead.

Read-only. Uses get_minute_bars (Polygon). Run on Hetzner.
"""
from __future__ import annotations

import asyncio
import csv
import logging
from collections import defaultdict
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from agents.market_intelligence.collector import get_minute_bars
from agents.market_intelligence.db import get_pool

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

_ET = ZoneInfo("America/New_York")
SESSION_OPEN_MIN = 9 * 60 + 30
ORB_WINDOW_END = 9 * 60 + 45
STOP_WIDTH_GATE = 0.15  # 15% — current Apollo gate
FADE_RATIO = 0.5  # midpoint check


async def fetch_missed_positives() -> list[dict]:
    """All HIGH alerts in 90d (CS/ADRC) where no live_trade row + fwd_5d ≥ 10%."""
    pool = await get_pool()
    cutoff = date.today() - timedelta(days=90)
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """WITH alerts AS (
                  SELECT DISTINCT ON (a.ticker, a.alert_date)
                         a.ticker, a.alert_date, a.gap_pct, a.ep_score,
                         a.catalyst_quality
                    FROM mi_ep_alerts a
               LEFT JOIN mi_security_types st ON st.ticker = a.ticker
                   WHERE a.alert_date > $1
                     AND a.score_tier = 'HIGH'
                     AND (st.security_type IN ('CS', 'ADRC') OR st.security_type IS NULL)
                ORDER BY a.ticker, a.alert_date, a.ep_score DESC
                ),
                missed AS (
                  SELECT a.* FROM alerts a
             LEFT JOIN mi_live_trades lt
                    ON lt.ticker = a.ticker AND lt.alert_date = a.alert_date
                   AND COALESCE(lt.signal_type, 'magna53') = 'magna53'
                   AND lt.status IN ('closed', 'open', 'filled')
                 WHERE lt.id IS NULL
                ),
                fwd AS (
                  SELECT m.*, c0.close AS close_at_alert,
                         (SELECT MAX(close) FROM mi_daily_closes c2
                           WHERE c2.ticker = m.ticker
                             AND c2.trade_date > m.alert_date
                             AND c2.trade_date <= m.alert_date + 7) AS max_close_5d
                    FROM missed m
               LEFT JOIN mi_daily_closes c0 ON c0.ticker = m.ticker AND c0.trade_date = m.alert_date
                )
                SELECT *,
                       (max_close_5d / NULLIF(close_at_alert, 0) - 1) * 100 AS fwd_5d_pct
                  FROM fwd
                 WHERE close_at_alert IS NOT NULL
                   AND max_close_5d IS NOT NULL
                   AND (max_close_5d / NULLIF(close_at_alert, 0) - 1) >= 0.10
              ORDER BY alert_date DESC, ticker""",
            cutoff,
        )
    return [dict(r) for r in rows]


async def fetch_day_data(ticker: str, alert_d: date) -> tuple[list[dict], dict | None, dict | None]:
    """Return (minute_bars_alert_day, day1_close, day2_close)."""
    pool = await get_pool()
    date_str = alert_d.strftime("%Y-%m-%d")
    bars = await get_minute_bars(ticker, date_str, date_str)
    async with pool.acquire() as conn:
        d_rows = await conn.fetch(
            """SELECT trade_date, open_price, high_price, low_price, close, volume
                 FROM mi_daily_closes
                WHERE ticker = $1 AND trade_date BETWEEN $2 AND $3
             ORDER BY trade_date""",
            ticker, alert_d, alert_d + timedelta(days=7),
        )
    daily = {r["trade_date"]: dict(r) for r in d_rows}
    d1 = daily.get(alert_d)
    next_dates = sorted(d for d in daily if d > alert_d)
    d2 = daily.get(next_dates[0]) if next_dates else None
    return bars or [], d1, d2


def replay_day1(bars: list[dict], alert_d: date) -> dict:
    """Bucketize bars into ET clock-minute, return Day 1 catchability verdict."""
    by_min: dict[int, dict] = {}
    for b in bars:
        try:
            t_ms = b.get("t")
            if t_ms is None:
                continue
            dt_et = datetime.fromtimestamp(int(t_ms) / 1000.0, tz=_ET)
            if dt_et.date() != alert_d:
                continue
            m = dt_et.hour * 60 + dt_et.minute
            if m < SESSION_OPEN_MIN or m >= ORB_WINDOW_END:
                continue
            by_min[m] = b
        except Exception:
            continue

    if not by_min or SESSION_OPEN_MIN not in by_min:
        return {"verdict": "no_bars", "orb_high": None, "orb_low": None,
                "orb_range_pct": None, "break_minute": None, "fade_at_944": None}

    orb_bar = by_min[SESSION_OPEN_MIN]
    orb_high = float(orb_bar["h"])
    orb_low = float(orb_bar["l"])
    orb_open = float(orb_bar["o"])
    orb_range_pct = (orb_high - orb_low) / orb_open * 100 if orb_open > 0 else None
    midpoint = (orb_high + orb_low) / 2

    # First minute price broke ORB high
    break_min = None
    for m in sorted(by_min):
        if m == SESSION_OPEN_MIN:
            continue
        if float(by_min[m]["h"]) >= orb_high:
            break_min = m
            break

    # Close at 9:44 (last minute of submission window)
    last_m = max(by_min)
    last_close = float(by_min[last_m]["c"])
    fade_at_944 = last_close < midpoint

    # Verdict
    if orb_range_pct is not None and orb_range_pct > STOP_WIDTH_GATE * 100:
        verdict = "stop_too_wide"
    elif break_min is None:
        verdict = "no_break"
    elif fade_at_944 and last_close < midpoint:
        # Even though break occurred, the stock faded by 9:44
        verdict = "broke_then_faded"
    else:
        verdict = "catchable"

    return {
        "verdict": verdict,
        "orb_open": round(orb_open, 4),
        "orb_high": round(orb_high, 4),
        "orb_low": round(orb_low, 4),
        "orb_range_pct": round(orb_range_pct, 2) if orb_range_pct is not None else None,
        "break_minute": (break_min - SESSION_OPEN_MIN) if break_min is not None else None,
        "last_close_944": round(last_close, 4),
        "fade_at_944": fade_at_944,
        "n_bars": len(by_min),
    }


def replay_day2_sugar(d1: dict | None, d2: dict | None) -> dict:
    """Day 2 9M sugar-baby qualification check."""
    if not d1 or not d2 or d1.get("close") is None or d2.get("close") is None:
        return {"sugar_baby": None, "d2_gap_pct": None, "d2_close_in_range": None}
    d1_close = float(d1["close"])
    d2_open = float(d2.get("open_price") or 0)
    d2_high = float(d2.get("high_price") or 0)
    d2_low = float(d2.get("low_price") or 0)
    d2_close = float(d2["close"])
    if d2_close <= 0 or d2_high <= d2_low or d1_close <= 0:
        return {"sugar_baby": False, "d2_gap_pct": None, "d2_close_in_range": None}
    gap_pct = (d2_open / d1_close - 1) * 100 if d2_open > 0 else None
    range_pos = (d2_close - d2_low) / (d2_high - d2_low) if (d2_high - d2_low) > 0 else None
    net_up_pct = (d2_close / d1_close - 1) * 100
    sugar = (
        range_pos is not None and range_pos >= 0.75
        and net_up_pct >= 3.0
        and d2_close > d2_open
    )
    return {
        "sugar_baby": sugar,
        "d2_gap_pct": round(gap_pct, 2) if gap_pct is not None else None,
        "d2_close_in_range": round(range_pos, 2) if range_pos is not None else None,
        "d2_net_up_pct": round(net_up_pct, 2),
    }


async def process_row(row: dict) -> dict:
    bars, d1, d2 = await fetch_day_data(row["ticker"], row["alert_date"])
    d1_replay = replay_day1(bars, row["alert_date"])
    d2_replay = replay_day2_sugar(d1, d2)
    return {**row, **d1_replay, **d2_replay}


async def main(out_path: str) -> None:
    rows = await fetch_missed_positives()
    logger.info(f"missed positives: {len(rows)}")

    sem = asyncio.Semaphore(4)

    async def _do(r):
        async with sem:
            return await process_row(r)

    results = await asyncio.gather(*[_do(r) for r in rows])
    logger.info(f"replayed {len(results)} rows")

    cols = [
        "ticker", "alert_date", "gap_pct", "ep_score", "catalyst_quality",
        "fwd_5d_pct", "verdict",
        "orb_open", "orb_high", "orb_low", "orb_range_pct",
        "break_minute", "last_close_944", "fade_at_944", "n_bars",
        "sugar_baby", "d2_gap_pct", "d2_close_in_range", "d2_net_up_pct",
    ]
    with open(out_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for r in results:
            r2 = {**r}
            r2["alert_date"] = r["alert_date"].isoformat()
            for k in ("gap_pct", "fwd_5d_pct"):
                if r2.get(k) is not None:
                    r2[k] = round(float(r2[k]), 2)
            w.writerow(r2)
    logger.info(f"wrote {out_path}")

    # Summary
    by_verdict: dict[str, list[dict]] = defaultdict(list)
    for r in results:
        by_verdict[r["verdict"]].append(r)

    print(f"\n=== Day 1 catchability for {len(results)} missed positives ===")
    print(f"{'verdict':<20} {'n':>4} {'med_fwd':>8} {'med_orb_range':>14}")
    for v in sorted(by_verdict.keys()):
        sub = by_verdict[v]
        fwds = sorted(float(r["fwd_5d_pct"]) for r in sub if r.get("fwd_5d_pct") is not None)
        ranges = sorted(r["orb_range_pct"] for r in sub if r.get("orb_range_pct") is not None)
        med_fwd = f"{fwds[len(fwds)//2]:.1f}%" if fwds else "-"
        med_rng = f"{ranges[len(ranges)//2]:.2f}%" if ranges else "-"
        print(f"{v:<20} {len(sub):>4} {med_fwd:>8} {med_rng:>14}")

    sugars = [r for r in results if r.get("sugar_baby")]
    print(f"\nDay 2 sugar babies (would have qualified for 9M Day 2 ORB): {len(sugars)}")

    print(f"\n=== Per-row replay ({len(results)} rows) ===")
    print(f"{'ticker':<6} {'date':<12} {'verdict':<18} {'fwd':>6} {'orb_rng':>8} "
          f"{'brk_m':>5} {'fade':>5} {'sugar':>5}")
    for r in sorted(results, key=lambda x: -float(x["fwd_5d_pct"])):
        rng = f"{r['orb_range_pct']:.1f}%" if r.get("orb_range_pct") is not None else "-"
        brk = str(r.get("break_minute") or "-")
        fade = "Y" if r.get("fade_at_944") else "N" if r.get("fade_at_944") is False else "-"
        sug = "Y" if r.get("sugar_baby") else "N" if r.get("sugar_baby") is False else "-"
        print(f"{r['ticker']:<6} {r['alert_date'].isoformat()} {r['verdict']:<18} "
              f"{float(r['fwd_5d_pct']):>5.1f}% {rng:>8} {brk:>5} {fade:>5} {sug:>5}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="/tmp/replay_missed.csv")
    args = parser.parse_args()
    asyncio.run(main(out_path=args.out))
