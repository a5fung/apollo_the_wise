"""Materiality SHADOW writer (#189 / ADR 0010) — OFFLINE evidence-accrual.

The fire panel (#201) lights the catalyst axis on grade + named-type alone, which
runs ~95% `fire_seen` (the conviction floor already required strong/gc, so the axis
mostly re-encodes the untrusted grade). #189 materiality — "news existence != EP
grade" — is the signal that can say "graded big BUT not a real fire," giving the
fire-discovery guardrail something to discriminate. The LIVE flip (wiring materiality
into `_compute_fire_status`) is CHANGE_PROCESS-gated on entry-aware R evidence that is
weeks out (ADR 0010).

This job is that evidence ACCRUING from day one — never the flip. It runs post-EOD,
reads the day's catalyst-ONLY fires (`fire_axes == ['catalyst']` — the scope-corrected
denominator: a name that is fire_seen via theme/narrative is unaffected by an immaterial
catalyst), computes the #189 materiality tier (rule-first, Sonnet on abstain — the ONE
shared layer in catalyst_materiality.assess_materiality), and writes three shadow
columns: `materiality_tier`, `materiality_source`, `fire_status_mat_shadow` (the
fire_status the activated rule WOULD produce). The live `fire_status` is NEVER touched.

HOW the would-be status is derived WITHOUT modifying the frozen hot-path function:
`_compute_fire_status` is called UNCHANGED, but with `catalyst_type` forced to a
NON_FIRE type when the catalyst is CONFIRMED immaterial. That makes its catalyst axis
go dark exactly as the staged ADR 0010 diff (`and is_material(materiality_tier)`)
would — same had-inputs tail, no duplication, no edit to the firing path during its
first-verify-day freeze (#115). FAIL-OPEN: a None/abstain tier is treated as material
(is_material(None) is True) — a sourcing/judgment gap never silently demotes a real EP.

NOT the hot path: never imported by run_ep_scan. Error-wrapped end to end.
"""
from __future__ import annotations

import asyncio
import logging
import os

from agents.market_intelligence.catalyst_materiality import (
    assess_materiality, is_material,
)
from agents.market_intelligence.collector import et_today, get_fmp_profile
from agents.market_intelligence.db import (
    ensure_materiality_shadow_columns, get_pool,
    update_ep_alert_materiality_shadow,
)
from agents.market_intelligence.ep_detector import _compute_fire_status

logger = logging.getLogger(__name__)


async def _shadow_one(client, row) -> dict:
    """Compute materiality + would-be fire_status for one catalyst-only fire and
    write the shadow columns. Returns a small result dict for the run summary."""
    ticker = row["ticker"]
    catalyst = row["catalyst"]
    analysis = row["claude_analysis"]

    market_cap = None
    try:
        prof = await get_fmp_profile(ticker) or {}
        market_cap = prof.get("marketCap")
        company, sector = prof.get("companyName"), prof.get("sector")
    except Exception:
        company, sector = None, None

    tier, source = await assess_materiality(
        client, company=company, sector=sector, market_cap=market_cap,
        catalyst=catalyst, analysis=analysis,
    )

    # Would-be fire_status: call the UNCHANGED hot-path function with catalyst_type
    # forced non-fire when CONFIRMED immaterial (mirrors the ADR 0010 flip without
    # editing it). in_theme/in_narrative are False by construction here (denominator
    # is fire_axes == ['catalyst']) but we pass the row's real flags defensively.
    effective_type = row["catalyst_type"] if is_material(tier) else "unknown"
    would_fs, _would_axes = _compute_fire_status(
        in_theme=bool(row["in_active_theme"]),
        in_narrative=bool(row["in_narrative_cohort"]),
        catalyst_quality=row["catalyst_quality"],
        catalyst_text=catalyst,
        catalyst_type=effective_type,
    )

    await update_ep_alert_materiality_shadow(
        ticker, row["alert_date"], tier, source, would_fs,
    )
    return {"ticker": ticker, "tier": tier, "source": source,
            "would_fire_status": would_fs,
            "demoted": would_fs != "fire_seen"}


async def run_materiality_shadow(target_date=None) -> dict:
    """Accrue materiality shadow columns for the day's catalyst-ONLY fires.
    Returns {date, n_catalyst_only, n_demoted, results}. Never raises."""
    day = target_date or et_today()
    await ensure_materiality_shadow_columns()  # turnkey first-fire (own the schema)
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT ticker, alert_date, catalyst_quality, catalyst_type,
                   catalyst, claude_analysis, in_active_theme, in_narrative_cohort
            FROM mi_ep_alerts
            WHERE alert_date = $1
              AND catalyst_quality IN ('strong', 'game_changer')
              AND fire_status = 'fire_seen'
              AND fire_axes = ARRAY['catalyst']::text[]
            ORDER BY ticker
        """, day)

    if not rows:
        logger.info(f"materiality shadow {day}: 0 catalyst-only fires — nothing to accrue")
        return {"date": str(day), "n_catalyst_only": 0, "n_demoted": 0, "results": []}

    client = None
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if api_key:
        import anthropic
        client = anthropic.AsyncAnthropic(api_key=api_key)

    results = []
    try:
        for r in rows:
            try:
                results.append(await _shadow_one(client, r))
            except Exception as e:
                logger.warning(f"materiality shadow failed for {r['ticker']}: {e}")
    finally:
        if client is not None:
            try:
                await client.close()  # don't leak the httpx pool in the daily job
            except Exception:
                pass

    n_demoted = sum(1 for r in results if r["demoted"])
    logger.info(
        f"materiality shadow {day}: {len(results)}/{len(rows)} catalyst-only fires "
        f"scored, {n_demoted} would-demote (immaterial)"
    )
    return {"date": str(day), "n_catalyst_only": len(rows),
            "n_demoted": n_demoted, "results": results}


async def summarize_materiality_shadow(days: int = 7) -> str:
    """Plain-text digest line for the weekly review. Reports the catalyst-only
    denominator + how many materiality would demote, over the window. Degrades
    gracefully: it SURFACES counts + an explicit insufficient-evidence banner; it
    does NOT produce a demotion verdict (the deciding output — entry-aware R of
    demoted-vs-kept — needs the paper-R cohort to mature, weeks out). Mirrors
    fire_status_r_cohort.py's not-a-verdict posture."""
    await ensure_materiality_shadow_columns()  # safe if digest runs before first writer
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(f"""
            SELECT materiality_tier, materiality_source, fire_status_mat_shadow
            FROM mi_ep_alerts
            WHERE alert_date >= (CURRENT_DATE - INTERVAL '{int(days)} days')
              AND catalyst_quality IN ('strong', 'game_changer')
              AND fire_status = 'fire_seen'
              AND fire_axes = ARRAY['catalyst']::text[]
              AND materiality_tier IS NOT NULL
        """)
    n = len(rows)
    if n == 0:
        return (f"Materiality shadow ({days}d): 0 catalyst-only fires scored yet "
                f"(#189 accruing — fire_status started 2026-06-08).")
    demoted = [r for r in rows if (r["fire_status_mat_shadow"] or "") != "fire_seen"]
    tier_counts: dict = {}
    for r in rows:
        t = r["materiality_tier"] or "abstain"
        tier_counts[t] = tier_counts.get(t, 0) + 1
    tiers = " ".join(f"{t}={c}" for t, c in sorted(tier_counts.items()))
    return (
        f"Materiality shadow ({days}d): {n} catalyst-only fires · "
        f"{len(demoted)} would-demote (immaterial) · tiers[{tiers}]. "
        f"⚠️ counts only — entry-aware R of demoted-vs-kept pending paper-R maturity "
        f"(NOT a demotion verdict; flip stays CHANGE_PROCESS-gated, ADR 0010)."
    )


async def _main():
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "summary":
        print(await summarize_materiality_shadow(int(sys.argv[2]) if len(sys.argv) > 2 else 7))
        return
    res = await run_materiality_shadow()
    print(f"date={res['date']} catalyst_only={res['n_catalyst_only']} "
          f"would_demote={res['n_demoted']}")
    for r in res["results"]:
        print(f"  {r['ticker']:6}  tier={r['tier']}  src={r['source']}  "
              f"would_fire={r['would_fire_status']}  demoted={r['demoted']}")


if __name__ == "__main__":
    asyncio.run(_main())
