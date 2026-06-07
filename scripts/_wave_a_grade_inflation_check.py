"""#210 Wave A — the REAL Monday acceptance gate (advisor 2026-06-07).

Wave A is NOT telemetry-safe: Benzinga text enters grounded_text -> catalyst_quality
-> ep_score -> score_tier -> HIGH alerts -> paper ORB entries (phase=paper magna53).
Adding a *found* catalyst can only push grades UP, and press-wire text is promotional
by nature. So the risk is SYSTEMATIC GRADE INFLATION concentrated on PR-having
tickers — not "wiring failed". "Rows exist" does NOT verify that.

This read-only check (no trade state) answers the actual question: did the
game_changer / HIGH rate spike on the target day, AND is the excess concentrated in
benzinga-sourced tickers? Uses Wave B's `ep_catalyst_provenance` as the instrument.

Run Monday after the scan window:
    docker exec apollo-market python scripts/_wave_a_grade_inflation_check.py
    docker exec apollo-market python scripts/_wave_a_grade_inflation_check.py 2026-06-08
"""
import asyncio
import json
import sys
from datetime import date


async def main():
    from agents.market_intelligence.db import get_pool
    from agents.market_intelligence.collector import et_today

    target = (
        date(*(int(x) for x in sys.argv[1].split("-"))) if len(sys.argv) > 1 else et_today()
    )
    pool = await get_pool()
    async with pool.acquire() as c:
        # Trailing baseline: per-day game_changer + HIGH counts over the prior ~9
        # calendar days (pre-Wave-A history; no provenance needed).
        base = await c.fetch(
            """
            SELECT alert_date,
                   COUNT(*) FILTER (WHERE catalyst_quality = 'game_changer') gc,
                   COUNT(*) FILTER (WHERE score_tier = 'HIGH')               high
            FROM mi_ep_alerts
            WHERE alert_date >= $1::date - 9 AND alert_date < $1::date
            GROUP BY alert_date ORDER BY alert_date
            """,
            target,
        )
        tgt = await c.fetchrow(
            """
            SELECT COUNT(*) FILTER (WHERE catalyst_quality = 'game_changer') gc,
                   COUNT(*) FILTER (WHERE score_tier = 'HIGH')               high,
                   COUNT(*) total
            FROM mi_ep_alerts WHERE alert_date = $1
            """,
            target,
        )
        # Provenance for the target day: which graded tickers carried benzinga.
        prov = await c.fetch(
            "SELECT detail FROM mi_audit_log "
            "WHERE event_type = 'ep_catalyst_provenance' "
            "  AND created_at >= $1::date AND created_at < $1::date + 1",
            target,
        )

    n_base = max(len(base), 1)
    avg_gc = sum(r["gc"] for r in base) / n_base
    avg_high = sum(r["high"] for r in base) / n_base
    max_gc = max((r["gc"] for r in base), default=0)
    max_high = max((r["high"] for r in base), default=0)

    # Benzinga concentration on the target day, by grade.
    bz_gc = bz_total = gc_with_prov = 0
    for r in prov:
        try:
            d = json.loads(r["detail"] or "{}")
        except (ValueError, TypeError):
            continue
        has_bz = "benzinga_pr" in (d.get("sources") or {})
        if has_bz:
            bz_total += 1
        if d.get("catalyst_quality") == "game_changer":
            gc_with_prov += 1
            if has_bz:
                bz_gc += 1

    print(f"=== Wave A grade-inflation check — {target} ===\n")
    print(f"baseline (prior {len(base)} trading days):")
    print(f"   game_changer/day: avg {avg_gc:.1f}, max {max_gc}")
    print(f"   HIGH/day:         avg {avg_high:.1f}, max {max_high}")
    print(f"\n{target}:")
    print(f"   game_changer: {tgt['gc']}   HIGH: {tgt['high']}   (total alerts {tgt['total']})")
    print(f"   provenance rows: {len(prov)}  ·  benzinga-carrying: {bz_total}")
    print(f"   of {gc_with_prov} game_changers w/ provenance, {bz_gc} carried benzinga")

    # Heuristic verdict (operator judges — HARD gate: agent does not declare 'safe').
    gc_spike = tgt["gc"] > max_gc and tgt["gc"] >= 2
    high_spike = tgt["high"] > max_high and tgt["high"] >= 2
    concentrated = gc_with_prov > 0 and bz_gc / gc_with_prov >= 0.5
    print()
    if (gc_spike or high_spike) and concentrated:
        print("   ⚠️  POSSIBLE INFLATION — grade count above the trailing max AND the "
              "excess skews benzinga. Inspect the new game_changers' catalysts: is the "
              "PR genuinely material, or did promotional wire text lift the grade? "
              "(operator call — do NOT auto-trust)")
    elif gc_spike or high_spike:
        print("   ℹ️  Grade count above trailing max but NOT benzinga-concentrated — "
              "likely a normal busy day, not a Wave-A artifact. Confirm.")
    else:
        print("   ✅ No grade-count spike vs the trailing baseline — Wave A not inflating "
              "the HIGH/game_changer rate so far. (One day; keep watching the cohort.)")


if __name__ == "__main__":
    asyncio.run(main())
