"""P7.3a 9M cohort delayed-EP audit + day2_status semantic check.

Two sub-steps required before P7.3b can ship:

1. Replicate Block D on mi_9m_ep_alerts cohort — for 9M EPs that
   didn't enter Day 2 (day2_status != 'traded'), walk forward 21d
   and compute capture rate via existing downstream.

2. Verify day2_status semantics: distribution of values over 60d,
   how many 'pending' rows are >1 day old? Determines whether the
   P7.3b universe-expansion query reads 'skipped' alone or also
   stale-pending.

Output: analysis/2026-05-17/ninem_delayed_ep_audit.md

Run on prod:
  docker exec apollo-market python -m scripts.ninem_delayed_ep_audit
"""
from __future__ import annotations

import asyncio
import logging
from collections import Counter
from datetime import date
from pathlib import Path

from agents.market_intelligence.db import get_pool

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

OUT_MD = Path("analysis/2026-05-17/ninem_delayed_ep_audit.md")


async def day2_status_distribution() -> dict:
    """Pull 60d distribution of day2_status values + age-of-pending.

    Returns: {distribution: {status: count}, pending_age_histogram: ...,
              stale_pending_pct: float}
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        # Distribution of day2_status values over 60d
        rows = await conn.fetch("""
            SELECT day2_status, COUNT(*) AS n
            FROM mi_9m_day2_candidates
            WHERE alert_date >= CURRENT_DATE - 60
            GROUP BY day2_status
            ORDER BY n DESC
        """)
        distribution = {r["day2_status"]: r["n"] for r in rows}

        # Among pending rows, how many are >1 day old? (alert_date < today-1)
        pending_rows = await conn.fetch("""
            SELECT alert_date, CURRENT_DATE - alert_date AS age_days
            FROM mi_9m_day2_candidates
            WHERE alert_date >= CURRENT_DATE - 60
              AND day2_status = 'pending'
            ORDER BY alert_date DESC
        """)
        n_pending = len(pending_rows)
        n_stale_pending = sum(
            1 for r in pending_rows if (r["age_days"] or 0) > 1
        )
        age_buckets = Counter()
        for r in pending_rows:
            age = r["age_days"] or 0
            if age <= 1:
                age_buckets["0-1 days"] += 1
            elif age <= 7:
                age_buckets["2-7 days"] += 1
            elif age <= 30:
                age_buckets["8-30 days"] += 1
            else:
                age_buckets["31+ days"] += 1

    return {
        "distribution": distribution,
        "n_pending": n_pending,
        "n_stale_pending": n_stale_pending,
        "stale_pending_pct": (n_stale_pending / n_pending * 100) if n_pending else 0.0,
        "age_buckets": dict(age_buckets),
    }


async def ninem_alpha_cohort_audit() -> dict:
    """Block D replication on mi_9m_ep_alerts cohort.

    For each 9M EP alert with day2_status != 'traded' (failed Day 2 or
    never entered), walk forward 21 days and compute:
      - made +5% within 21d (alpha)
      - captured downstream by any of: next 9M EP, next MAGNA53 EP,
        flag candidate, sugar baby Day 3+
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        # 9M EPs in 60d with sugar baby status NOT 'traded' (the non-trade cohort)
        rows = await conn.fetch("""
            SELECT
                e.ticker, e.alert_date, e.gap_pct,
                sb.day2_status,
                -- gap-day open
                (SELECT open_price FROM mi_daily_closes
                 WHERE ticker = e.ticker AND trade_date = e.alert_date) AS d0_open,
                -- max high over 21 trading days after alert
                (SELECT MAX(high_price) FROM mi_daily_closes
                 WHERE ticker = e.ticker
                   AND trade_date > e.alert_date
                   AND trade_date <= e.alert_date + INTERVAL '32 days')
                 AS max_high_21d,
                -- next 9M EP within 21d
                (SELECT MIN(alert_date) FROM mi_9m_ep_alerts
                 WHERE ticker = e.ticker
                   AND alert_date BETWEEN e.alert_date + 1 AND e.alert_date + 21)
                 AS next_9m_date,
                -- next MAGNA53 EP within 21d
                (SELECT MIN(alert_date) FROM mi_ep_alerts
                 WHERE ticker = e.ticker
                   AND alert_date BETWEEN e.alert_date + 1 AND e.alert_date + 21
                   AND score_tier IN ('HIGH', 'MODERATE'))
                 AS next_magna53_date,
                -- next flag candidate within 21d (COILED/TRIGGERED/WATCH)
                (SELECT MIN(scan_date) FROM mi_flag_candidates
                 WHERE ticker = e.ticker
                   AND scan_date BETWEEN e.alert_date + 1 AND e.alert_date + 21
                   AND stage IN ('COILED', 'TRIGGERED', 'WATCH'))
                 AS next_flag_date
            FROM mi_9m_ep_alerts e
            LEFT JOIN mi_9m_day2_candidates sb
              ON sb.ticker = e.ticker AND sb.alert_date = e.alert_date
            WHERE e.alert_date >= CURRENT_DATE - 60
              AND (sb.day2_status IS NULL OR sb.day2_status != 'traded')
            ORDER BY e.alert_date DESC, e.ticker
        """)
        rows = [dict(r) for r in rows]

    n_total = len(rows)
    n_alpha = 0      # made +5% within 21d
    n_captured = 0   # at least one downstream pickup
    n_alpha_captured = 0
    alpha_list = []

    for r in rows:
        if r["d0_open"] is None or r["max_high_21d"] is None:
            continue
        mfe = (r["max_high_21d"] / r["d0_open"] - 1) if r["d0_open"] > 0 else 0
        is_alpha = mfe >= 0.05
        captured = any([
            r["next_9m_date"],
            r["next_magna53_date"],
            r["next_flag_date"],
        ])
        if is_alpha:
            n_alpha += 1
            alpha_list.append({**r, "mfe_21d": mfe, "captured": captured})
            if captured:
                n_alpha_captured += 1
        if captured:
            n_captured += 1

    return {
        "n_total": n_total,
        "n_alpha": n_alpha,
        "n_alpha_captured": n_alpha_captured,
        "alpha_capture_rate": (n_alpha_captured / n_alpha * 100) if n_alpha else 0.0,
        "n_captured": n_captured,
        "alpha_list": alpha_list,
    }


def fmt_pct(v):
    return f"{v*100:+.1f}%" if v is not None else "—"


async def main() -> None:
    logger.info("Running day2_status semantic check...")
    ds = await day2_status_distribution()
    logger.info("day2_status distribution: %s", ds["distribution"])
    logger.info("Pending rows: %d, stale (>1d): %d (%.1f%%)",
                ds["n_pending"], ds["n_stale_pending"], ds["stale_pending_pct"])

    logger.info("Running 9M alpha cohort audit...")
    ac = await ninem_alpha_cohort_audit()
    logger.info("9M failed-Day-2 cohort: total=%d alpha=%d captured=%d (alpha_capture=%.1f%%)",
                ac["n_total"], ac["n_alpha"], ac["n_alpha_captured"], ac["alpha_capture_rate"])

    # ─── Compose markdown ──────────────────────────────────────────────
    lines = [
        "# P7.3a 9M Cohort Delayed-EP Audit + day2_status Semantic Check",
        "",
        "_Two analyses required before P7.3b ship: (1) Block D replication "
        "on 9M cohort, (2) day2_status field semantics over 60d._",
        "",
        "## §1 day2_status semantic check",
        "",
        "Distribution of `mi_9m_day2_candidates.day2_status` values over the "
        "last 60d:",
        "",
        "| Status | N |",
        "|---|---:|",
    ]
    for status, n in sorted(ds["distribution"].items(), key=lambda x: -x[1]):
        lines.append(f"| `{status}` | {n} |")
    lines.append("")
    lines.append(f"**Pending rows total**: {ds['n_pending']}")
    lines.append(f"**Stale pending (>1 day old)**: {ds['n_stale_pending']} "
                 f"({ds['stale_pending_pct']:.1f}% of pending)")
    lines.append("")
    lines.append("### Age distribution of pending rows")
    lines.append("")
    lines.append("| Age | N |")
    lines.append("|---|---:|")
    for bucket in ["0-1 days", "2-7 days", "8-30 days", "31+ days"]:
        lines.append(f"| {bucket} | {ds['age_buckets'].get(bucket, 0)} |")
    lines.append("")

    # P7.3b query shape decision
    lines.append("### P7.3b universe-query shape decision")
    lines.append("")
    if ds["stale_pending_pct"] > 30:
        query_shape = (
            "**'pending' LINGERS**. Use broader query form:\n"
            "```sql\n"
            "day2_status = 'skipped' OR "
            "(day2_status = 'pending' AND alert_date < CURRENT_DATE - INTERVAL '1 day')\n"
            "```"
        )
    elif ds["stale_pending_pct"] < 10:
        query_shape = (
            "**'skipped' fires reliably**. Use simple query form:\n"
            "```sql\n"
            "day2_status = 'skipped'\n"
            "```"
        )
    else:
        query_shape = (
            "**Mixed (10-30% stale)**. Use the broader (pending-stale) form to be safe:\n"
            "```sql\n"
            "day2_status IN ('skipped') OR "
            "(day2_status = 'pending' AND alert_date < CURRENT_DATE - INTERVAL '1 day')\n"
            "```"
        )
    lines.append(query_shape)
    lines.append("")

    # ─── §2 9M alpha cohort audit ──────────────────────────────────────
    lines.append("## §2 9M failed-Day-2 cohort audit (Block D replication)")
    lines.append("")
    lines.append(f"For each 9M EP alert in last 60d where `day2_status != 'traded'`:")
    lines.append(f"")
    lines.append(f"| Metric | Count |")
    lines.append(f"|---|---:|")
    lines.append(f"| Total 9M alerts (failed Day 2 or never entered) | {ac['n_total']} |")
    lines.append(f"| Of which made +5% within 21d (alpha names) | {ac['n_alpha']} |")
    lines.append(f"| Of alpha names, captured downstream | {ac['n_alpha_captured']} |")
    lines.append(f"| **Alpha capture rate** | **{ac['alpha_capture_rate']:.1f}%** |")
    lines.append("")

    # Per-name table
    lines.append("### Alpha names (failed Day 2 + made +5% within 21d, sorted by MFE desc)")
    lines.append("")
    lines.append("| Ticker | Alert | day2_status | MFE 21d | Next 9M | Next MAGNA53 | Next Flag | Captured |")
    lines.append("|---|---|---|---:|---|---|---|:---:|")
    for r in sorted(ac["alpha_list"], key=lambda x: -x["mfe_21d"]):
        mark = "✓" if r["captured"] else "✗"
        lines.append(
            f"| {r['ticker']} | {r['alert_date']} | "
            f"{r.get('day2_status') or '—'} | "
            f"{r['mfe_21d']*100:+.1f}% | "
            f"{r.get('next_9m_date') or '—'} | "
            f"{r.get('next_magna53_date') or '—'} | "
            f"{r.get('next_flag_date') or '—'} | {mark} |"
        )
    lines.append("")

    lines.append("## Implications for P7.3b")
    lines.append("")
    if ac["alpha_capture_rate"] < 50:
        lines.append(f"- 9M failed-Day-2 alpha capture is **{ac['alpha_capture_rate']:.1f}%** — "
                     "meaningful gap that P7.3b universe expansion should close")
    elif ac["alpha_capture_rate"] < 70:
        lines.append(f"- 9M failed-Day-2 alpha capture is **{ac['alpha_capture_rate']:.1f}%** — "
                     "moderate gap; P7.3b would help but ROI is lower than P7.2 MAGNA53 side")
    else:
        lines.append(f"- 9M failed-Day-2 alpha capture is **{ac['alpha_capture_rate']:.1f}%** — "
                     "existing downstream is largely catching these names; P7.3b is marginal")
    lines.append("")

    OUT_MD.parent.mkdir(parents=True, exist_ok=True)
    OUT_MD.write_text("\n".join(lines), encoding="utf-8")
    logger.info("wrote %s", OUT_MD)


if __name__ == "__main__":
    asyncio.run(main())
