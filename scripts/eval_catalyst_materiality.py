#!/usr/bin/env python3
"""#189 materiality EVAL (READ-ONLY; NO DB writes, NO trade state, NO hot-path).

Question (advisor 2026-06-06): the fire panel (#201) lights the catalyst axis on
grade + named-type alone (projected ~95% fire_seen). If we add an EXPLICIT
materiality signal, (a) what fraction of historically graded-strong/game_changer
alerts does it reclassify as NOT material, and (b) do those reclassified names
actually have WORSE forward returns? (b) is the evidence that justifies gating the
catalyst axis — it turns "~95% too permissive" from assumption into measured fact.

This runs the materiality signal (rules from catalyst_materiality.py + a Sonnet
judgment on the STORED grounded catalyst text — point-in-time, no lookahead on the
input) over the historical strong/gc cohort in mi_ep_alerts, joined to
mi_ep_scan_outcomes for fwd_5d_pct / fwd_10d_pct. Pure measurement; ships nothing.

CAVEAT: market cap is fetched live (FMP), so it's TODAY's cap, an approximation of
alert-time cap. Caps rarely move >2x, so the material/immaterial split is robust;
treat individual borderline ratios as soft.

Run (server, read-only):
  docker exec apollo-market python scripts/eval_catalyst_materiality.py [N]
"""
import asyncio
import os
import statistics
import sys

import anthropic

from agents.market_intelligence.catalyst_materiality import (
    MATERIALITY_TIERS, extract_deal_value, rule_materiality, is_material,
    judge_materiality_llm,
)
from agents.market_intelligence.collector import get_fmp_profile
from agents.market_intelligence.db import get_pool


async def _judge(client, row, mc):
    """Sonnet materiality tier via the ONE shared judgment layer
    (catalyst_materiality.judge_materiality_llm) — the eval and the live shadow
    writer must never diverge on the prompt. None (parse/error) → 'immaterial'
    for the eval's tier tally (the live path fails OPEN instead)."""
    tier = await judge_materiality_llm(
        client, company=row["company"] or row["ticker"], sector=row["sector"],
        market_cap=mc, catalyst=row["catalyst"], analysis=row["analysis"],
    )
    return tier or "immaterial"


def _stats(vals):
    vals = [v for v in vals if v is not None]
    if not vals:
        return "n=0"
    wr = sum(1 for v in vals if v > 0) / len(vals) * 100
    return f"n={len(vals)} mean={statistics.mean(vals):+.1f}% median={statistics.median(vals):+.1f}% win={wr:.0f}%"


async def main():
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else 200
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(f"""
            SELECT a.ticker, a.alert_date, a.catalyst_quality, a.catalyst_type,
                   a.gap_pct, a.ep_score, a.catalyst, a.claude_analysis AS analysis,
                   o.fwd_5d_pct, o.fwd_10d_pct
            FROM mi_ep_alerts a
            JOIN mi_ep_scan_outcomes o ON o.ticker=a.ticker AND o.scan_date=a.alert_date
            WHERE a.catalyst_quality IN ('strong','game_changer')
              AND o.fwd_5d_pct IS NOT NULL
            ORDER BY a.alert_date DESC
            LIMIT {limit}
        """)
    rows = [dict(r) for r in rows]
    print(f"#189 materiality eval — {len(rows)} graded-strong/gc alerts with fwd returns\n")

    client = anthropic.AsyncAnthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    profile_cache: dict = {}
    material_buf, immaterial_buf = {"5d": [], "10d": []}, {"5d": [], "10d": []}
    tier_counts: dict = {}
    n_reclassified = 0

    for r in rows:
        tk = r["ticker"]
        if tk not in profile_cache:
            try:
                profile_cache[tk] = await get_fmp_profile(tk) or {}
            except Exception:
                profile_cache[tk] = {}
        prof = profile_cache[tk]
        r["company"] = prof.get("companyName")
        r["sector"] = prof.get("sector")
        mc = prof.get("marketCap")
        try:
            mc = float(mc)
            mktcap_str = f"${mc/1e9:.1f}B" if mc >= 1e9 else f"${mc/1e6:.0f}M"
        except (TypeError, ValueError):
            mc, mktcap_str = None, "unknown"

        try:
            tier = await _judge(client, r, mc)
        except Exception as e:
            print(f"  {tk} {r['alert_date']} JUDGE ERROR: {e}")
            continue

        # Deterministic cross-check (rules abstain when no deal value / cap).
        deal = extract_deal_value(f"{r['catalyst']} {r['analysis']}")
        rule_tier = rule_materiality(deal, mc)

        tier_counts[tier] = tier_counts.get(tier, 0) + 1
        mat = is_material(tier)
        if not mat:
            n_reclassified += 1
        buf = material_buf if mat else immaterial_buf
        buf["5d"].append(r["fwd_5d_pct"])
        buf["10d"].append(r["fwd_10d_pct"])

        flag = "MAT " if mat else "imm "
        rt = f" rule={rule_tier}" if rule_tier else ""
        print(f"  {flag}{tk:6s} {str(r['alert_date'])} gc={r['catalyst_quality'][:4]} "
              f"tier={tier:13s} fwd5d={r['fwd_5d_pct']:+6.1f}% mc={mktcap_str}{rt}")

    n = len(rows)
    print("\n" + "=" * 74)
    print("TIER DISTRIBUTION (of graded strong/game_changer):")
    for t in MATERIALITY_TIERS:
        c = tier_counts.get(t, 0)
        print(f"  {t:14s} {c:3d}  ({c/n*100:.0f}%)" if n else f"  {t}: 0")
    print(f"\nRECLASSIFIED not-material: {n_reclassified}/{n}  ({n_reclassified/n*100:.0f}%)" if n else "")
    print("\nFORWARD RETURNS — the evidence for gating:")
    print(f"  MATERIAL   fwd5d {_stats(material_buf['5d'])}")
    print(f"             fwd10d {_stats(material_buf['10d'])}")
    print(f"  NOT-MATERIAL fwd5d {_stats(immaterial_buf['5d'])}")
    print(f"             fwd10d {_stats(immaterial_buf['10d'])}")
    print("=" * 74)
    print("Gating is justified IF not-material names show materially WORSE fwd "
          "returns/win-rate than material. If returns are similar, materiality is "
          "NOT the lever (do not gate the catalyst axis on it).")


if __name__ == "__main__":
    asyncio.run(main())
