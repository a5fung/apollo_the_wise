"""Pre-coding spike for cross-strategy unified allocator (#31).

Simulates Phase 1 scoring (40/30/20/10 setup/catalyst/volume/regime) against
multiple paper-session days. Per advisor 2026-05-08: n=1 (5/7) isn't enough
evidence to lock the normalization spec — extend to 5-10 days, see whether
the MAGNA53 cap-clustering at ep_score=96 is typical or 5/7-specific.

Outputs per-day:
  - candidate counts per strategy
  - in-pool setup-quality mean+sd per strategy (calibration sanity)
  - top-5 picks under RAW vs Z-NORM scoring
  - strategy mix at top-5 (e.g. 3M+2N)

Aggregates across days:
  - how many days the schemes diverge in top-2 / top-5
  - typical MAGNA53 ep_score top-3 distribution (cap-saturated or spread?)

Run on Hetzner:
  docker exec apollo-market python -m scripts.spike_unified_allocator
"""
from __future__ import annotations

import asyncio
import logging
import statistics
from datetime import date, timedelta

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

W_SETUP = 0.40
W_CATALYST = 0.30
W_VOLUME = 0.20
W_REGIME = 0.10

CATALYST_GRADE = {"game_changer": 100.0, "strong": 70.0, "routine": 30.0, "mna": 0.0}


def score_magna53(row: dict) -> dict:
    setup = float(row.get("ep_score") or 0)
    catalyst = CATALYST_GRADE.get(row.get("catalyst_quality") or "routine", 30.0)
    pm_rvol = float(row.get("pm_rvol") or 0)
    volume = min(50.0, pm_rvol) / 50.0 * 100.0
    regime = 100.0
    composite = W_SETUP * setup + W_CATALYST * catalyst + W_VOLUME * volume + W_REGIME * regime
    return {"setup": setup, "catalyst": catalyst, "volume": volume,
            "regime": regime, "composite": composite}


def score_9m_day2(row: dict, adv: float | None = None) -> dict:
    close_pct = float(row.get("close_in_range_pct") or 0) * 100
    gap = float(row.get("gap_proxy") or 0)
    gap_score = min(30.0, max(0.0, gap)) / 30.0 * 100.0
    setup = 0.5 * close_pct + 0.5 * gap_score
    catalyst = 100.0
    volume = float(row.get("volume") or 0)
    if adv and adv > 0:
        vol_ratio = volume / adv
    else:
        vol_ratio = 5.0
    volume_score = min(10.0, vol_ratio) / 10.0 * 100.0
    regime = 100.0
    composite = W_SETUP * setup + W_CATALYST * catalyst + W_VOLUME * volume_score + W_REGIME * regime
    return {"setup": setup, "catalyst": catalyst, "volume": volume_score,
            "regime": regime, "composite": composite}


def zscore(x: float, mean: float, sd: float) -> float:
    if sd <= 0:
        return 0.0
    return (x - mean) / sd


async def score_one_day(conn, target: date, sugar_date: date) -> dict:
    """Score all candidates for one paper-session day. Returns summary dict."""
    ma_rows = await conn.fetch("""
        SELECT ticker, ep_score, gap_pct, pm_rvol, catalyst_quality, score_tier
        FROM mi_ep_alerts WHERE alert_date = $1 AND score_tier IN ('HIGH','MODERATE')
        ORDER BY ep_score DESC
    """, target)

    sb_rows = await conn.fetch("""
        SELECT ticker, open_price, close_price, high_price, low_price,
               volume, close_in_range_pct, prev_20d_pct,
               (close_price-open_price)/NULLIF(open_price,0)*100 AS gap_proxy
        FROM mi_9m_day2_candidates WHERE alert_date = $1
    """, sugar_date)

    sb_tickers = [r["ticker"] for r in sb_rows]
    adv_map = {}
    if sb_tickers:
        adv_rows = await conn.fetch("""
            SELECT ticker, AVG(volume)::FLOAT AS adv20
            FROM (
                SELECT ticker, volume,
                       ROW_NUMBER() OVER (PARTITION BY ticker ORDER BY trade_date DESC) AS rn
                FROM mi_daily_closes
                WHERE ticker = ANY($1) AND trade_date <= $2
            ) t WHERE rn <= 20
            GROUP BY ticker
        """, sb_tickers, sugar_date)
        adv_map = {r["ticker"]: float(r["adv20"]) for r in adv_rows}

    scored = []
    for r in ma_rows:
        d = dict(r)
        scored.append({**d, "strategy": "magna53", **score_magna53(d)})
    for r in sb_rows:
        d = dict(r)
        scored.append({**d, "strategy": "9m_day2", **score_9m_day2(d, adv=adv_map.get(d["ticker"]))})

    if not scored:
        return {"date": target, "n_total": 0, "skip": True}

    by_strat: dict[str, list[float]] = {}
    for c in scored:
        by_strat.setdefault(c["strategy"], []).append(c["setup"])
    stats = {}
    for s, vals in by_strat.items():
        m = statistics.mean(vals) if vals else 0
        sd = statistics.stdev(vals) if len(vals) >= 2 else 1.0
        stats[s] = (m, sd)

    for c in scored:
        m, sd = stats[c["strategy"]]
        z = zscore(c["setup"], m, sd)
        setup_z = max(0.0, min(100.0, 50.0 + 15.0 * z))
        c["setup_z"] = setup_z
        c["composite_z"] = (
            W_SETUP * setup_z + W_CATALYST * c["catalyst"]
            + W_VOLUME * c["volume"] + W_REGIME * c["regime"]
        )

    raw_sorted = sorted(scored, key=lambda x: -x["composite"])
    z_sorted = sorted(scored, key=lambda x: -x["composite_z"])
    raw_top5 = [(c["ticker"], c["strategy"]) for c in raw_sorted[:5]]
    z_top5 = [(c["ticker"], c["strategy"]) for c in z_sorted[:5]]

    # MAGNA53 ep_score top-3 — cap-saturation check
    ma_scores = sorted([float(r["ep_score"] or 0) for r in ma_rows], reverse=True)[:3]
    ties_at_top = sum(1 for s in ma_scores if s == ma_scores[0]) if ma_scores else 0

    return {
        "date": target,
        "n_magna53": len(ma_rows),
        "n_9m_day2": len(sb_rows),
        "magna_mean": stats.get("magna53", (None, None))[0],
        "magna_sd": stats.get("magna53", (None, None))[1],
        "ninem_mean": stats.get("9m_day2", (None, None))[0],
        "ninem_sd": stats.get("9m_day2", (None, None))[1],
        "raw_top5": raw_top5,
        "z_top5": z_top5,
        "magna_top3_scores": ma_scores,
        "ties_at_top": ties_at_top,
        "skip": False,
    }


async def main():
    import asyncpg
    import os
    pwd = os.environ.get("POSTGRES_PASSWORD")
    conn = await asyncpg.connect(
        user="apollo", password=pwd, database="apollo",
        host="postgres", port=5432,
    )

    # Sample 7 trading days ending 2026-05-07 (advisor: 5-10 days).
    # Skip weekends — sugar_date should be the trading day before target.
    sample_days = [
        (date(2026, 4, 28), date(2026, 4, 25)),  # Mon (after weekend)
        (date(2026, 4, 29), date(2026, 4, 28)),
        (date(2026, 4, 30), date(2026, 4, 29)),
        (date(2026, 5, 1),  date(2026, 4, 30)),
        (date(2026, 5, 2),  date(2026, 5, 1)),   # Fri
        (date(2026, 5, 5),  date(2026, 5, 2)),   # Mon
        (date(2026, 5, 6),  date(2026, 5, 5)),
        (date(2026, 5, 7),  date(2026, 5, 6)),
    ]

    print("\n=== UNIFIED ALLOCATOR MULTI-DAY SPIKE ===\n")
    print(f"{'date':<12}{'M':>3}{'9M':>3}  "
          f"{'M_mean':>8}{'M_sd':>6}  "
          f"{'9M_mean':>8}{'9M_sd':>6}  "
          f"{'top3_ma':>14}{'div@2':>6}{'div@5':>6}")
    print("-" * 100)

    results = []
    for target, sugar in sample_days:
        s = await score_one_day(conn, target, sugar)
        if s["skip"]:
            continue
        results.append(s)
        # Divergence flags
        raw2 = set(t for t, _ in s["raw_top5"][:2])
        z2 = set(t for t, _ in s["z_top5"][:2])
        div2 = "Y" if raw2 != z2 else "."
        raw5 = set(t for t, _ in s["raw_top5"])
        z5 = set(t for t, _ in s["z_top5"])
        div5 = "Y" if raw5 != z5 else "."
        m_mean = s["magna_mean"] or 0
        m_sd = s["magna_sd"] or 0
        n_mean = s["ninem_mean"] or 0
        n_sd = s["ninem_sd"] or 0
        top3_str = "/".join(f"{x:.0f}" for x in s["magna_top3_scores"]) or "—"
        print(f"{s['date'].isoformat():<12}{s['n_magna53']:>3}{s['n_9m_day2']:>3}  "
              f"{m_mean:>8.1f}{m_sd:>6.1f}  "
              f"{n_mean:>8.1f}{n_sd:>6.1f}  "
              f"{top3_str:>14}{div2:>6}{div5:>6}")
    print()

    # Per-day strategy mix at top-5
    print("Top-5 strategy mix per day (RAW / Z-NORM):")
    for s in results:
        raw_mix = (sum(1 for _, st in s["raw_top5"] if st == "magna53"),
                   sum(1 for _, st in s["raw_top5"] if st == "9m_day2"))
        z_mix = (sum(1 for _, st in s["z_top5"] if st == "magna53"),
                 sum(1 for _, st in s["z_top5"] if st == "9m_day2"))
        raw_str = f"{raw_mix[0]}M+{raw_mix[1]}N"
        z_str = f"{z_mix[0]}M+{z_mix[1]}N"
        print(f"  {s['date'].isoformat()}: raw={raw_str:7s} z={z_str:7s}  raw_top5={[t for t,_ in s['raw_top5']]}")

    # Aggregate stats
    print()
    days = len(results)
    div2_count = sum(1 for s in results if set(t for t,_ in s["raw_top5"][:2]) != set(t for t,_ in s["z_top5"][:2]))
    div5_count = sum(1 for s in results if set(t for t,_ in s["raw_top5"]) != set(t for t,_ in s["z_top5"]))
    cap_saturated_days = sum(1 for s in results if s["ties_at_top"] >= 3)

    print(f"=== AGGREGATE (n={days} days) ===")
    print(f"Top-2 picks differ between RAW and Z-NORM: {div2_count}/{days} days")
    print(f"Top-5 picks differ between RAW and Z-NORM: {div5_count}/{days} days")
    print(f"MAGNA53 days with ≥3 ties at top score (cap saturation): {cap_saturated_days}/{days}")

    avg_m_sd = statistics.mean([s["magna_sd"] or 0 for s in results if s["magna_sd"]])
    avg_n_sd = statistics.mean([s["ninem_sd"] or 0 for s in results if s["ninem_sd"]])
    print(f"Avg MAGNA53 setup sd: {avg_m_sd:.1f}  /  Avg 9M Day 2 setup sd: {avg_n_sd:.1f}")

    await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
