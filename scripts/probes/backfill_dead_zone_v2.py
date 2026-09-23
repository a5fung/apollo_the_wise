"""Dead-zone backfill v2: full missed-EP universe over 90 days, mechanism-classified.

v1 problem (2026-04-30):
  - Cohort B (mi_ep_scan_log post-open rel_vol) over 30d after CS/ADRC filter = n=5.
  - But that's only ONE failure mode. Today's FTAI/PI/GKOS were detected by the
    9:45+ projection branch and missed the ORB cutoff — they pass rel_vol but
    never appear in scan_log under that filter_reason.
  - Per user feedback: don't dismiss low-n in rare-event cohorts; widen the lens.

v2 lens:
  Cohort A — HIGH_entered: HIGH alert with successful live_trade (control / true positives).
  Cohort B — HIGH_missed:  HIGH alert that didn't get filled / never had a trade row.
                            Sub-classified by mechanism:
                              · late_detection (created_at ET >= 9:45)
                              · cancelled_unfilled (live_trade.status='cancelled')
                              · pending_aged (status stuck pending — proxy for never-filled)
                              · skip_other (skip_reason set, not late_detection)
                              · no_trade_row (HIGH detected but pipeline didn't even propose)
  Cohort C — dead_zone_neverHIGH: scan_log post-open rel_vol filter, never promoted to HIGH.

For each row: RVOL@T at 5/10/14 (session anchor) + forward-5d return label
(positive if max(close T+1..T+5) >= 10% above close at alert).

Read-only. CS/ADRC only (drops leveraged ETN/ETF noise).

Run on Hetzner after-hours:
    docker exec apollo-market python -m scripts.backfill_dead_zone_v2 --days 90
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import logging
from collections import defaultdict
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from agents.market_intelligence.collector import get_minute_bars
from agents.market_intelligence.db import get_pool, get_minute_volume_baseline

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

_ET = ZoneInfo("America/New_York")

SESSION_OPEN_MIN = 9 * 60 + 30
DECISION_OFFSETS = [5, 10, 14]
THRESHOLDS = [1.0, 1.5, 2.0, 3.0]
LABEL_THRESHOLD = 0.10
ORB_CUTOFF_MIN = 9 * 60 + 45  # 9:45 ET — ORB submission window close

CSV_COLS = [
    "cohort", "mechanism", "ticker", "alert_date",
    "score_tier", "gap_pct", "catalyst_quality",
    "et_alert_minute", "trade_status", "skip_reason", "filter_reason",
    "security_type",
    "rvol_at_5", "rvol_at_10", "rvol_at_14", "baseline_n_at_14",
    "close_at_alert", "max_close_5d", "fwd_5d_pct", "label",
]


async def fetch_cohorts(days: int) -> tuple[list[dict], list[dict]]:
    """Return (high_alerts_with_trade_state, deadzone_neverHIGH)."""
    pool = await get_pool()
    cutoff = date.today() - timedelta(days=days)
    async with pool.acquire() as conn:
        ep_rows = await conn.fetch(
            """SELECT a.ticker, a.alert_date, a.score_tier, a.gap_pct,
                      a.catalyst_quality,
                      (a.created_at AT TIME ZONE 'America/New_York')::time AS et_time,
                      lt.status AS trade_status, lt.skip_reason,
                      lt.filled_at, lt.entry_price, lt.total_pnl,
                      st.security_type
                 FROM mi_ep_alerts a
            LEFT JOIN mi_live_trades lt
                   ON lt.ticker = a.ticker AND lt.alert_date = a.alert_date
                  AND COALESCE(lt.signal_type, 'magna53') = 'magna53'
            LEFT JOIN mi_security_types st ON st.ticker = a.ticker
                WHERE a.alert_date > $1
                  AND a.score_tier = 'HIGH'
                  AND (st.security_type IN ('CS', 'ADRC') OR st.security_type IS NULL)
             ORDER BY a.alert_date DESC, a.ticker""",
            cutoff,
        )
        dz_rows = await conn.fetch(
            """SELECT s.ticker, s.scan_date AS alert_date,
                      COALESCE(s.score_tier, 'NONE') AS score_tier,
                      s.gap_pct, s.filter_reason, s.catalyst_quality,
                      st.security_type
                 FROM mi_ep_scan_log s
            LEFT JOIN mi_ep_alerts a
                   ON a.ticker = s.ticker AND a.alert_date = s.scan_date
                  AND a.score_tier = 'HIGH'
            LEFT JOIN mi_security_types st ON st.ticker = s.ticker
                WHERE s.scan_date > $1
                  AND s.filter_reason LIKE '%rel_vol%post-open%'
                  AND a.ticker IS NULL
                  AND (st.security_type IN ('CS', 'ADRC') OR st.security_type IS NULL)
             ORDER BY s.scan_date DESC, s.ticker""",
            cutoff,
        )
    return [dict(r) for r in ep_rows], [dict(r) for r in dz_rows]


def classify_high_mechanism(row: dict) -> tuple[str, str]:
    """(cohort, mechanism) for HIGH alert rows."""
    et_time = row.get("et_time")
    et_min = (et_time.hour * 60 + et_time.minute) if et_time else None
    status = row.get("trade_status")
    skip = (row.get("skip_reason") or "")

    if status in ("closed", "open", "filled") and row.get("filled_at"):
        return ("HIGH_entered", "entered_ok")

    if et_min is not None and et_min >= ORB_CUTOFF_MIN:
        return ("HIGH_missed", "late_detection")

    if status == "cancelled":
        return ("HIGH_missed", "cancelled_unfilled")
    if status in ("rejected", "skipped"):
        return ("HIGH_missed", f"skip:{skip[:40]}" if skip else "skip_other")
    if status in ("pending_confirmation", "order_placed", "pending"):
        return ("HIGH_missed", "pending_aged")
    if status is None:
        return ("HIGH_missed", "no_trade_row")
    return ("HIGH_missed", f"status:{status}")


async def fetch_close_series(ticker: str, alert_d: date, ahead_days: int = 12) -> dict[date, float]:
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

    out: dict[int, int] = {}
    cum = 0
    for offset in range(0, max(DECISION_OFFSETS) + 1):
        cum += per_minute_vol.get(SESSION_OPEN_MIN + offset, 0)
        if offset in DECISION_OFFSETS:
            out[offset] = cum
    return out


async def process_row(cohort: str, mechanism: str, row: dict) -> dict | None:
    ticker = row["ticker"]
    alert_d = row["alert_date"]
    date_str = alert_d.strftime("%Y-%m-%d")

    bars = await get_minute_bars(ticker, date_str, date_str)
    if not bars:
        return None

    cum_at = compute_cum_at_offsets(bars, alert_d)
    rvols: dict[int, float | None] = {5: None, 10: None, 14: None}
    baseline_n_14 = 0
    if cum_at and cum_at.get(14, 0) > 0:
        for offset in DECISION_OFFSETS:
            et_min = SESSION_OPEN_MIN + offset
            baseline = await get_minute_volume_baseline(ticker, "session", et_min)
            if not baseline or float(baseline["mean_cum_vol"] or 0) <= 0:
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

    et_time = row.get("et_time")
    et_min_alert = (et_time.hour * 60 + et_time.minute) if et_time else None

    return {
        "cohort": cohort,
        "mechanism": mechanism,
        "ticker": ticker,
        "alert_date": alert_d.isoformat(),
        "score_tier": row.get("score_tier"),
        "gap_pct": row.get("gap_pct"),
        "catalyst_quality": row.get("catalyst_quality"),
        "et_alert_minute": et_min_alert,
        "trade_status": row.get("trade_status"),
        "skip_reason": (row.get("skip_reason") or "")[:60],
        "filter_reason": (row.get("filter_reason") or "")[:60],
        "security_type": row.get("security_type"),
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
    by_mech: dict[str, list[dict]] = defaultdict(list)
    for r in results:
        by_mech[f"{r['cohort']}::{r['mechanism']}"].append(r)

    print("\n=== Mechanism breakdown ===")
    print(f"{'cohort::mechanism':<40} {'n':>4} {'pos':>4} {'pos%':>6} {'med_rvol14':>10}")
    for key in sorted(by_mech.keys()):
        rows = by_mech[key]
        pos = sum(1 for r in rows if r["label"] == "positive")
        rvols = sorted(r["rvol_at_14"] for r in rows if r["rvol_at_14"] is not None)
        med = rvols[len(rvols) // 2] if rvols else None
        med_s = f"{med:.2f}" if med is not None else "-"
        print(f"{key:<40} {len(rows):>4} {pos:>4} {(pos/len(rows)*100):>5.1f}% {med_s:>10}")

    # Focus: HIGH_missed × all mechanisms — where's the leak?
    missed = [r for r in results if r["cohort"] == "HIGH_missed"]
    pos_missed = [r for r in missed if r["label"] == "positive"]
    print(f"\n=== HIGH_missed total: n={len(missed)} positives={len(pos_missed)} "
          f"({len(pos_missed)/len(missed)*100:.1f}% if any) ===" if missed else "no missed")
    if pos_missed:
        print("\nTop 15 missed positives by fwd_5d_pct:")
        top = sorted(pos_missed, key=lambda r: -r["fwd_5d_pct"])[:15]
        print(f"{'mechanism':<25} {'ticker':<6} {'date':<12} {'fwd':>6} {'rvol14':>8} {'gap':>6} {'et':>5}")
        for r in top:
            rv = f"{r['rvol_at_14']:.2f}" if r["rvol_at_14"] is not None else "-"
            et = str(r["et_alert_minute"] or "-")
            print(f"{r['mechanism'][:25]:<25} {r['ticker']:<6} {r['alert_date']} "
                  f"{r['fwd_5d_pct']:>5.1f}% {rv:>8} {r['gap_pct']:>5.1f}% {et:>5}")

    # RVOL@T threshold sweep on HIGH_missed where we have rvol
    cb = [r for r in missed if r["rvol_at_14"] is not None]
    total_pos = sum(1 for r in cb if r["label"] == "positive")
    if cb:
        print(f"\n=== HIGH_missed RVOL@14 sweep (n={len(cb)}, pos={total_pos}) ===")
        print(f"{'thresh':>8} {'flagged':>8} {'tp':>4} {'prec':>8} {'recall':>8}")
        for thresh in THRESHOLDS:
            flagged = [r for r in cb if r["rvol_at_14"] >= thresh]
            tp = sum(1 for r in flagged if r["label"] == "positive")
            prec = tp / len(flagged) if flagged else 0
            rec = tp / total_pos if total_pos else 0
            print(f"{thresh:>8.1f} {len(flagged):>8} {tp:>4} {prec*100:>7.1f}% {rec*100:>7.1f}%")

    # Compare HIGH_entered (control) RVOL distribution
    entered = [r for r in results if r["cohort"] == "HIGH_entered" and r["rvol_at_14"] is not None]
    if entered:
        ent_pos = [r for r in entered if r["label"] == "positive"]
        ent_neg = [r for r in entered if r["label"] == "negative"]
        print(f"\n=== HIGH_entered (control) RVOL@14 ===")
        for label, sub in (("positive", ent_pos), ("negative", ent_neg)):
            if sub:
                vs = sorted(r["rvol_at_14"] for r in sub)
                med = vs[len(vs) // 2]
                print(f"  {label}: n={len(vs)} med={med:.2f} p25={vs[len(vs)//4]:.2f} p75={vs[(3*len(vs))//4]:.2f}")


async def main(days: int, out_path: str) -> None:
    ep_rows, dz_rows = await fetch_cohorts(days)
    logger.info(f"HIGH alerts (90d, CS/ADRC): {len(ep_rows)}")
    logger.info(f"Dead-zone never-HIGH (90d, CS/ADRC): {len(dz_rows)}")

    tasks = []
    for r in ep_rows:
        cohort, mech = classify_high_mechanism(r)
        tasks.append(process_row(cohort, mech, r))
    for r in dz_rows:
        tasks.append(process_row("dead_zone_neverHIGH", "rel_vol_post_open", r))

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
    parser.add_argument("--days", type=int, default=90)
    parser.add_argument("--out", default="/tmp/dead_zone_v2.csv")
    args = parser.parse_args()
    asyncio.run(main(days=args.days, out_path=args.out))
