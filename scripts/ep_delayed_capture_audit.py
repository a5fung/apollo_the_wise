"""EP Selectivity Phase 1 — Block D — Delayed-EP downstream capture audit.

User's R3 nuance (2026-05-16): dropping Day-1 same-day re-entry from
MAGNA53 ORB is OK provided we capture the "delayed EP" via the 9M
Day-2 ORB and continuation-flag detectors instead. This script
checks empirically whether that handoff actually works.

For each MAGNA53 HIGH alert in the 60d cohort that FAILED Day 1
(stopped out OR didn't enter OR closed loss), walk forward 21 days
and check whether the same ticker appeared in:

  - mi_9m_ep_alerts          (9M EP same-day pickup)
  - mi_9m_day2_candidates       (9M EP day → Day-2 ORB candidate)
  - mi_flag_candidates       (COILED / TRIGGERED basing pattern)
  - mi_ep_alerts (subsequent)  (a later MAGNA53 EP, e.g. TRT 4/23 → 5/15)

Also pull forward returns for each MAGNA53 HIGH that failed Day 1,
to measure "alpha left on the table" — did the stock eventually
break out within 21 days regardless of downstream capture?

Output:
  analysis/2026-05-16/delayed_ep_audit.md

Run on prod:
  docker exec apollo-market python -m scripts.ep_delayed_capture_audit
"""
from __future__ import annotations

import asyncio
import csv
import logging
from pathlib import Path

from agents.market_intelligence.db import get_pool

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

OUT_MD = Path("analysis/2026-05-16/delayed_ep_audit.md")


COHORT_SQL = """
-- MAGNA53 HIGH alerts in 60d, joined to live_trades to identify
-- "failed Day 1" — either no entry OR closed at loss.
WITH high_alerts AS (
    SELECT DISTINCT ON (a.ticker, a.alert_date)
           a.ticker, a.alert_date, a.ep_score, a.gap_pct,
           a.catalyst_quality
    FROM mi_ep_alerts a
    WHERE a.alert_date >= CURRENT_DATE - 60
      AND a.score_tier = 'HIGH'
    ORDER BY a.ticker, a.alert_date, a.ep_score DESC NULLS LAST,
             a.detected_at DESC NULLS LAST, a.id DESC
),
day1_outcome AS (
    SELECT a.ticker, a.alert_date, a.ep_score, a.gap_pct,
           a.catalyst_quality,
           lt.status AS d1_status,
           lt.total_pnl AS d1_pnl,
           CASE
               WHEN lt.status = 'closed' AND COALESCE(lt.total_pnl, 0) > 0
                   THEN 'WON_DAY1'
               WHEN lt.status = 'closed' AND COALESCE(lt.total_pnl, 0) <= 0
                   THEN 'LOST_DAY1'
               WHEN lt.status = 'cancelled' THEN 'NO_ENTRY'
               WHEN lt.status = 'skipped' THEN 'SKIPPED'
               WHEN lt.id IS NULL THEN 'NO_TRADE_ROW'
               ELSE COALESCE(lt.status, 'UNKNOWN')
           END AS day1_class
    FROM high_alerts a
    LEFT JOIN mi_live_trades lt
      ON lt.ticker = a.ticker AND lt.alert_date = a.alert_date
     AND lt.account_mode = 'paper' AND lt.pnl_attribution IS NULL
)
SELECT
    d.ticker, d.alert_date, d.ep_score, d.gap_pct, d.catalyst_quality,
    d.day1_class, d.d1_pnl,
    -- 21d-forward downstream pickups
    (SELECT MIN(alert_date) FROM mi_9m_ep_alerts
       WHERE ticker = d.ticker
         AND alert_date BETWEEN d.alert_date + 1 AND d.alert_date + 21)
        AS next_9m_ep_date,
    (SELECT MIN(alert_date) FROM mi_9m_day2_candidates
       WHERE ticker = d.ticker
         AND alert_date BETWEEN d.alert_date + 1 AND d.alert_date + 21)
        AS next_sugar_baby_date,
    (SELECT MIN(scan_date) FROM mi_flag_candidates
       WHERE ticker = d.ticker
         AND scan_date BETWEEN d.alert_date + 1 AND d.alert_date + 21
         AND stage IN ('COILED', 'TRIGGERED', 'WATCH'))
        AS next_flag_date,
    (SELECT MIN(stage) FROM mi_flag_candidates
       WHERE ticker = d.ticker
         AND scan_date BETWEEN d.alert_date + 1 AND d.alert_date + 21
         AND stage IN ('COILED', 'TRIGGERED', 'WATCH'))
        AS next_flag_stage,
    (SELECT MIN(alert_date) FROM mi_ep_alerts
       WHERE ticker = d.ticker
         AND alert_date BETWEEN d.alert_date + 1 AND d.alert_date + 21
         AND score_tier IN ('HIGH', 'MODERATE'))
        AS next_ep_date,
    -- forward 21d max-favorable from gap-day open
    (SELECT MAX(high_price) FROM mi_daily_closes
       WHERE ticker = d.ticker
         AND trade_date BETWEEN d.alert_date + 1 AND d.alert_date + 21)
        AS max_high_21d,
    (SELECT open_price FROM mi_daily_closes
       WHERE ticker = d.ticker AND trade_date = d.alert_date)
        AS d0_open
FROM day1_outcome d
ORDER BY d.alert_date DESC, d.ticker;
"""


async def main() -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(COHORT_SQL)

    rows = [dict(r) for r in rows]
    logger.info("loaded %d MAGNA53 HIGH alerts", len(rows))

    # Bucket by day1_class
    classes = {}
    for r in rows:
        classes.setdefault(r["day1_class"], []).append(r)

    # Compute capture rates per Day-1-fail subset
    fail_classes = {"LOST_DAY1", "NO_ENTRY", "SKIPPED", "NO_TRADE_ROW"}
    failed = [r for r in rows if r["day1_class"] in fail_classes]
    won = [r for r in rows if r["day1_class"] == "WON_DAY1"]

    def cap_rate(subset, key):
        if not subset:
            return 0, 0
        captured = sum(1 for r in subset if r.get(key))
        return captured, len(subset)

    def fwd_winners(subset):
        """Names whose 21d max-high exceeded gap-day open by 5%+."""
        winners = 0
        evaluated = 0
        for r in subset:
            if r.get("d0_open") and r.get("max_high_21d"):
                evaluated += 1
                if r["max_high_21d"] / r["d0_open"] - 1 > 0.05:
                    winners += 1
        return winners, evaluated

    cap_9m, n_failed = cap_rate(failed, "next_9m_ep_date")
    cap_sb, _ = cap_rate(failed, "next_sugar_baby_date")
    cap_flag, _ = cap_rate(failed, "next_flag_date")
    cap_next_ep, _ = cap_rate(failed, "next_ep_date")
    cap_any = sum(
        1 for r in failed
        if r.get("next_9m_ep_date") or r.get("next_sugar_baby_date")
        or r.get("next_flag_date") or r.get("next_ep_date")
    )
    fwd_w, fwd_n = fwd_winners(failed)

    # Fixture: TRT 4/23
    trt_row = None
    for r in rows:
        if r["ticker"] == "TRT":
            trt_row = r
            break

    # ── Compose report ─────────────────────────────────────────────────
    lines = [
        "# Delayed-EP downstream capture audit",
        "",
        f"_For each MAGNA53 HIGH alert in 60d that FAILED Day 1 "
        f"(stopped, no-entry, skipped, or no trade-row), check the "
        f"next 21 days for downstream pickup by 9M EP / sugar-baby / "
        f"continuation-flag / subsequent MAGNA53 EP detectors._",
        "",
        "## Day-1 outcome distribution",
        "",
        "| Class | N |",
        "|---|---:|",
    ]
    for cls in ["WON_DAY1", "LOST_DAY1", "NO_ENTRY", "SKIPPED",
                "NO_TRADE_ROW", "UNKNOWN"]:
        n = len(classes.get(cls, []))
        if n > 0:
            lines.append(f"| {cls} | {n} |")
    lines.append("")
    lines.append(f"Total HIGH alerts in 60d: **{len(rows)}**. Failed "
                 f"Day 1: **{n_failed}**. Won Day 1: **{len(won)}**.")
    lines.append("")

    lines.append("## Downstream capture rate for failed-Day-1 names")
    lines.append("")
    lines.append("| Downstream detector | Captured | N failed | Rate |")
    lines.append("|---|---:|---:|---:|")
    lines.append(f"| Next 9M EP within 21d | {cap_9m} | {n_failed} | "
                 f"{cap_9m / max(1, n_failed) * 100:.1f}% |")
    lines.append(f"| Next 9M sugar baby within 21d | {cap_sb} | "
                 f"{n_failed} | "
                 f"{cap_sb / max(1, n_failed) * 100:.1f}% |")
    lines.append(f"| Next flag (COILED/TRIGGERED/WATCH) within 21d | "
                 f"{cap_flag} | {n_failed} | "
                 f"{cap_flag / max(1, n_failed) * 100:.1f}% |")
    lines.append(f"| Next MAGNA53 EP within 21d | {cap_next_ep} | "
                 f"{n_failed} | "
                 f"{cap_next_ep / max(1, n_failed) * 100:.1f}% |")
    lines.append(f"| **ANY downstream pickup** | **{cap_any}** | "
                 f"**{n_failed}** | "
                 f"**{cap_any / max(1, n_failed) * 100:.1f}%** |")
    lines.append("")

    lines.append("## Alpha left on the table")
    lines.append("")
    lines.append(f"Of {fwd_n} failed-Day-1 names with 21d forward "
                 f"data, **{fwd_w} ({fwd_w / max(1, fwd_n) * 100:.1f}%)** "
                 f"made a high more than 5% above gap-day open within "
                 f"21 trading days. This is the population the "
                 f"delayed-EP capture would target.")
    lines.append("")

    # Capture rate ONLY among the alpha names (the ones that mattered)
    alpha_names = [
        r for r in failed
        if r.get("d0_open") and r.get("max_high_21d")
        and r["max_high_21d"] / r["d0_open"] - 1 > 0.05
    ]
    alpha_captured = sum(
        1 for r in alpha_names
        if r.get("next_9m_ep_date") or r.get("next_sugar_baby_date")
        or r.get("next_flag_date") or r.get("next_ep_date")
    )
    lines.append(f"**Capture rate among ALPHA names** "
                 f"(failed Day 1 BUT made +5% within 21d): "
                 f"**{alpha_captured} / {len(alpha_names)} = "
                 f"{alpha_captured / max(1, len(alpha_names)) * 100:.1f}%**")
    lines.append("")

    # Per-detector breakdown ON alpha names
    alpha_9m = sum(1 for r in alpha_names if r.get("next_9m_ep_date"))
    alpha_sb = sum(1 for r in alpha_names if r.get("next_sugar_baby_date"))
    alpha_flag = sum(1 for r in alpha_names if r.get("next_flag_date"))
    alpha_ep = sum(1 for r in alpha_names if r.get("next_ep_date"))
    lines.append("### Detector contribution on alpha names")
    lines.append("")
    lines.append("| Detector | Alpha captured | Alpha total | Rate |")
    lines.append("|---|---:|---:|---:|")
    n_alpha = len(alpha_names)
    lines.append(f"| 9M EP | {alpha_9m} | {n_alpha} | "
                 f"{alpha_9m / max(1, n_alpha) * 100:.1f}% |")
    lines.append(f"| Sugar baby | {alpha_sb} | {n_alpha} | "
                 f"{alpha_sb / max(1, n_alpha) * 100:.1f}% |")
    lines.append(f"| Continuation flag | {alpha_flag} | {n_alpha} | "
                 f"{alpha_flag / max(1, n_alpha) * 100:.1f}% |")
    lines.append(f"| Next MAGNA53 EP | {alpha_ep} | {n_alpha} | "
                 f"{alpha_ep / max(1, n_alpha) * 100:.1f}% |")
    lines.append("")

    # TRT fixture
    lines.append("## TRT 4/23 fixture (delayed-EP exemplar)")
    lines.append("")
    if trt_row:
        lines.append(f"- alert_date: {trt_row['alert_date']}")
        lines.append(f"- day1_class: {trt_row['day1_class']}")
        lines.append(f"- next_9m_ep_date: {trt_row['next_9m_ep_date']}")
        lines.append(f"- next_sugar_baby_date: {trt_row['next_sugar_baby_date']}")
        lines.append(f"- next_flag_date: {trt_row['next_flag_date']}")
        lines.append(f"- next_flag_stage: {trt_row['next_flag_stage']}")
        lines.append(f"- next_ep_date: {trt_row['next_ep_date']}")
        lines.append(f"- d0_open: {trt_row.get('d0_open')}")
        lines.append(f"- max_high_21d: {trt_row.get('max_high_21d')}")
        if trt_row.get("d0_open") and trt_row.get("max_high_21d"):
            mfe = (trt_row["max_high_21d"] / trt_row["d0_open"] - 1) * 100
            lines.append(f"- max-favorable-excursion 21d: {mfe:+.1f}%")
    else:
        lines.append("TRT not in MAGNA53 HIGH cohort — was a 9M EP "
                     "(parallel methodology). Confirmed cohort "
                     "boundary; pull a 9M-cohort version of this "
                     "audit for full TRT chronology.")
    lines.append("")

    # Per-name table for alpha-failed
    lines.append("## Failed-Day-1 alpha names — full chronology")
    lines.append("")
    lines.append("| Ticker | Alert | Day1 | 9M EP | Sugar Baby | Flag | "
                 "Next EP | MFE 21d |")
    lines.append("|---|---|---|---|---|---|---|---:|")
    for r in sorted(alpha_names, key=lambda x: x["alert_date"], reverse=True):
        mfe = ""
        if r.get("d0_open") and r.get("max_high_21d"):
            mfe = f"{(r['max_high_21d'] / r['d0_open'] - 1) * 100:+.1f}%"
        lines.append(
            f"| {r['ticker']} | {r['alert_date']} | "
            f"{r['day1_class']} | {r.get('next_9m_ep_date') or '—'} | "
            f"{r.get('next_sugar_baby_date') or '—'} | "
            f"{r.get('next_flag_date') or '—'} | "
            f"{r.get('next_ep_date') or '—'} | {mfe} |"
        )
    lines.append("")

    OUT_MD.parent.mkdir(parents=True, exist_ok=True)
    OUT_MD.write_text("\n".join(lines), encoding="utf-8")
    logger.info("wrote %s", OUT_MD)
    logger.info(
        "summary: failed=%d, any_downstream_capture=%d (%.1f%%), "
        "alpha_names=%d, alpha_captured=%d (%.1f%%)",
        n_failed, cap_any, cap_any / max(1, n_failed) * 100,
        len(alpha_names), alpha_captured,
        alpha_captured / max(1, len(alpha_names)) * 100,
    )


if __name__ == "__main__":
    asyncio.run(main())
