"""EP Selectivity Phase 1 — Block B — Late-fire latency audit (P1.7).

CPA 5/14: user flagged that the EP detector fired AFTER 9:45 ET
despite a pre-open earnings catalyst and clean technicals. This
script quantifies: how many HIGH alerts in 60d fired LATE (after
9:45 ET), and which gate held them.

For each HIGH alert in the 60d cohort, pulls:
  - detected_at (first emit time of the HIGH alert)
  - the earliest scan_time_et for that ticker on alert_date
    (= when the system first SAW the candidate, regardless of grade)
  - filter_reason at the earliest scan (= what was blocking it)
  - filter_reasons of subsequent ticks BEFORE the HIGH emit (=
    chain of gates that gradually released)

Output:
  analysis/2026-05-16/latency_audit.md

Run on prod:
  docker exec apollo-market python -m scripts.ep_latency_audit
"""
from __future__ import annotations

import asyncio
import logging
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from agents.market_intelligence.db import get_pool

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

_ET = ZoneInfo("America/New_York")
OUT_MD = Path("analysis/2026-05-16/latency_audit.md")


COHORT_SQL = """
-- HIGH alerts in 60d with their first emit time + earliest scan
-- tick (any grade) for the same ticker on alert_date.
WITH high_alerts AS (
    SELECT DISTINCT ON (a.ticker, a.alert_date)
           a.ticker, a.alert_date, a.ep_score, a.gap_pct,
           a.catalyst_quality, a.detected_at
    FROM mi_ep_alerts a
    WHERE a.alert_date >= CURRENT_DATE - 60
      AND a.score_tier = 'HIGH'
      AND a.detected_at IS NOT NULL
    ORDER BY a.ticker, a.alert_date, a.detected_at ASC, a.id ASC
)
SELECT
    h.ticker, h.alert_date,
    h.ep_score, h.gap_pct, h.catalyst_quality,
    h.detected_at,
    (SELECT MIN(scan_time_et) FROM mi_ep_scan_log
       WHERE ticker = h.ticker AND scan_date = h.alert_date)
        AS first_scan_time_et,
    (SELECT filter_reason FROM mi_ep_scan_log
       WHERE ticker = h.ticker AND scan_date = h.alert_date
       ORDER BY scan_time_et ASC NULLS LAST, id ASC LIMIT 1)
        AS first_filter_reason,
    (SELECT COUNT(*) FROM mi_ep_scan_log
       WHERE ticker = h.ticker AND scan_date = h.alert_date
         AND scan_time_et < h.detected_at)
        AS n_pre_emit_ticks
FROM high_alerts h
ORDER BY h.alert_date DESC, h.ticker;
"""


def categorize_reason(fr: str) -> str:
    """Same taxonomy as breakdowns.py."""
    if not fr:
        return "(no reason)"
    fr = fr.lower()
    if "outside top-20" in fr:
        return "outside_top20"
    if "pre-mkt volume" in fr or "premkt volume" in fr or "pm volume" in fr:
        return "pm_shares_floor"
    if "already up" in fr or "extension" in fr:
        return "extension_gate"
    if "low rel volume" in fr or "low volume" in fr or "rel_vol" in fr:
        return "rel_vol_low"
    if "score " in fr and "< 50" in fr:
        return "score_below_50"
    if "ep cooldown" in fr or "cooldown" in fr:
        return "cooldown"
    if "routine catalyst" in fr:
        return "routine_catalyst"
    if "m&a" in fr or "buyout" in fr:
        return "ma_filter"
    if "duplicate" in fr or "already scored" in fr:
        return "duplicate_scan"
    if "atr" in fr:
        return "atr_high"
    if "mcap" in fr:
        return "mcap_low"
    if "adv" in fr:
        return "adv_low"
    return f"other"


def to_et(ts):
    if ts is None:
        return None
    return ts.astimezone(_ET)


def hhmm(ts):
    et = to_et(ts)
    return et.strftime("%H:%M:%S") if et else "—"


def bucket_emit_time(ts):
    et = to_et(ts)
    if et is None:
        return "(no timestamp)"
    m = et.hour * 60 + et.minute
    if m < 9 * 60 + 30:
        return "pre-market"
    if m < 9 * 60 + 45:
        return "9:30-9:44"
    if m < 10 * 60:
        return "9:45-9:59"
    if m < 11 * 60:
        return "10:00-10:59"
    return "11:00+"


async def main() -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(COHORT_SQL)
    rows = [dict(r) for r in rows]
    logger.info("loaded %d HIGH alerts with detected_at", len(rows))

    # Bucket by emit time
    bucket_counts = Counter()
    bucket_first_reason: dict[str, Counter] = defaultdict(Counter)
    for r in rows:
        bk = bucket_emit_time(r["detected_at"])
        bucket_counts[bk] += 1
        cat = categorize_reason(r.get("first_filter_reason") or "")
        bucket_first_reason[bk][cat] += 1

    total = len(rows)
    late_threshold = 9 * 60 + 45  # 9:45 ET in minutes

    # Late = emitted >= 9:45 ET
    late_alerts = [
        r for r in rows
        if r["detected_at"] is not None
        and to_et(r["detected_at"]).hour * 60 + to_et(r["detected_at"]).minute >= late_threshold
    ]
    # Pre-market = before 9:30 ET
    pre_mkt = [
        r for r in rows
        if r["detected_at"] is not None
        and to_et(r["detected_at"]).hour * 60 + to_et(r["detected_at"]).minute < 9 * 60 + 30
    ]
    in_window = [
        r for r in rows
        if r["detected_at"] is not None
        and 9 * 60 + 30 <= to_et(r["detected_at"]).hour * 60 + to_et(r["detected_at"]).minute < late_threshold
    ]

    # CPA fixture
    cpa = next((r for r in rows
                if r["ticker"] == "CPA" and str(r["alert_date"]) == "2026-05-14"),
               None)

    # Latency: detected_at − first_scan_time_et (minutes)
    latencies = []
    for r in rows:
        if r["detected_at"] and r["first_scan_time_et"]:
            delta = (r["detected_at"] - r["first_scan_time_et"]).total_seconds() / 60
            latencies.append((r, delta))

    latencies.sort(key=lambda x: -x[1])  # longest first

    lines = [
        "# EP detector latency audit (P1.7)",
        "",
        f"_N={total} HIGH alerts in 60d with `detected_at` populated. "
        f"Quantifies how many fired AFTER the ORB submission window "
        f"closed (9:45 ET cutoff) — the CPA 5/14 class._",
        "",
        "## Emit-time distribution",
        "",
        "| Bucket | N | Share |",
        "|---|---:|---:|",
    ]
    for bk in ["pre-market", "9:30-9:44", "9:45-9:59",
               "10:00-10:59", "11:00+"]:
        n = bucket_counts.get(bk, 0)
        lines.append(f"| {bk} | {n} | {n / max(1, total) * 100:.1f}% |")
    lines.append("")
    lines.append(f"**Late-fire rate** (emit ≥ 9:45 ET, past the ORB "
                 f"submission window): **{len(late_alerts)} / {total} "
                 f"= {len(late_alerts) / max(1, total) * 100:.1f}%**")
    lines.append("")
    lines.append(f"**In-window rate** (9:30-9:44 inclusive — "
                 f"actionable for ORB): **{len(in_window)} / {total} "
                 f"= {len(in_window) / max(1, total) * 100:.1f}%**")
    lines.append("")
    lines.append(f"**Pre-market rate** (before open — best window): "
                 f"**{len(pre_mkt)} / {total} = "
                 f"{len(pre_mkt) / max(1, total) * 100:.1f}%**")
    lines.append("")

    # First-filter-reason per bucket
    lines.append("## What filter held the LATE-fire alerts at first scan")
    lines.append("")
    lines.append("First `filter_reason` recorded for each LATE alert "
                 "(emit ≥ 9:45 ET) — i.e. what was blocking the candidate "
                 "the moment the system first saw it.")
    lines.append("")
    lines.append("| Category | N |")
    lines.append("|---|---:|")
    late_reasons = Counter()
    for r in late_alerts:
        cat = categorize_reason(r.get("first_filter_reason") or "")
        late_reasons[cat] += 1
    for cat, n in sorted(late_reasons.items(), key=lambda x: -x[1]):
        lines.append(f"| {cat} | {n} |")
    lines.append("")

    # Latency distribution
    lines.append("## Detected-vs-first-scan latency (minutes)")
    lines.append("")
    if latencies:
        deltas = [d for _, d in latencies]
        lines.append(f"- N with both timestamps: {len(deltas)}")
        lines.append(f"- median: {sorted(deltas)[len(deltas) // 2]:.1f} min")
        lines.append(f"- 90th pct: {sorted(deltas)[int(len(deltas) * 0.9)]:.1f} min")
        lines.append(f"- max: {max(deltas):.1f} min")
        lines.append("")
        lines.append("### Top 15 longest detection latencies")
        lines.append("")
        lines.append("| Ticker | Alert | 1st scan ET | Detected ET | "
                     "Latency (min) | 1st filter reason |")
        lines.append("|---|---|---|---|---:|---|")
        for r, d in latencies[:15]:
            lines.append(
                f"| {r['ticker']} | {r['alert_date']} | "
                f"{hhmm(r['first_scan_time_et'])} | "
                f"{hhmm(r['detected_at'])} | {d:.1f} | "
                f"{(r.get('first_filter_reason') or '')[:60]} |"
            )
        lines.append("")

    # CPA fixture detail
    lines.append("## CPA 5/14 fixture")
    lines.append("")
    if cpa:
        lines.append(f"- alert_date: {cpa['alert_date']}")
        lines.append(f"- score: {cpa['ep_score']}, gap: {cpa['gap_pct']}%, "
                     f"catalyst: {cpa['catalyst_quality']}")
        lines.append(f"- first scan time (ET): {hhmm(cpa['first_scan_time_et'])}")
        lines.append(f"- detected at (ET): {hhmm(cpa['detected_at'])}")
        if cpa["detected_at"] and cpa["first_scan_time_et"]:
            latency_min = (cpa["detected_at"] - cpa["first_scan_time_et"]).total_seconds() / 60
            lines.append(f"- latency: {latency_min:.1f} min")
        lines.append(f"- pre-emit scan ticks: {cpa['n_pre_emit_ticks']}")
        lines.append(f"- first filter reason: {cpa.get('first_filter_reason') or '—'}")
    else:
        lines.append("CPA 2026-05-14 not found in HIGH cohort with "
                     "populated detected_at.")
    lines.append("")

    # Late-fire alpha — did these names actually move?
    # (Could enrich with forward returns later; for now just count
    # share-of-late.)
    lines.append("## Implications")
    lines.append("")
    late_pct = len(late_alerts) / max(1, total) * 100
    if late_pct >= 20:
        lines.append(
            f"- **Late-fire is a material problem** ({late_pct:.1f}% "
            f"of HIGH alerts fired after 9:45 ET). These alerts CANNOT "
            f"be acted on under the current 9:31-9:45 ORB submission "
            f"window. CPA-class. Each late-fire is a missed Class A "
            f"entry."
        )
    else:
        lines.append(
            f"- Late-fire rate ({late_pct:.1f}%) is modest. CPA-class "
            f"is a tail issue rather than a systemic gate problem."
        )
    lines.append("")
    lines.append("- The top first-filter-reasons on late alerts surface "
                 "WHICH gate the system spends the most time waiting on. "
                 "If `rel_vol_low` or `pm_shares_floor` dominates, "
                 "pre-market volume curve building is the bottleneck "
                 "and a relaxed early-window threshold could pull "
                 "detections earlier.")
    lines.append("")
    lines.append("- The latency distribution (median + 90th pct) tells "
                 "us how long the typical alert spends in the scan "
                 "queue before promoting to HIGH. A long tail (>30 min) "
                 "suggests catalyst-grader round-trip or snapshot stale.")
    lines.append("")

    OUT_MD.parent.mkdir(parents=True, exist_ok=True)
    OUT_MD.write_text("\n".join(lines), encoding="utf-8")
    logger.info("wrote %s", OUT_MD)
    logger.info("late-fire %d/%d (%.1f%%), in-window %d, pre-market %d",
                len(late_alerts), total, len(late_alerts) / max(1, total) * 100,
                len(in_window), len(pre_mkt))


if __name__ == "__main__":
    asyncio.run(main())
