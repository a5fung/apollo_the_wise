"""Diagnose why NBIS 2026-03-16 fixture scored 27.0/39 strong (operator
labeled game_changer). Per-axis breakdown + caps applied + extraction
contents.

Run: docker exec apollo-market python -m scripts._nbis_rubric_diagnostic
"""
import asyncio
import json
from datetime import date


async def main():
    from agents.market_intelligence.catalyst_metrics_extractor import lookup_cached_metrics
    from agents.market_intelligence.catalyst_rubric_runtime import (
        score_ep_with_rubric, build_rubric_inputs_hybrid,
        format_rubric_full_breakdown,
    )
    from agents.market_intelligence.catalyst_rubric import score_ticker

    ticker = "NBIS"
    alert_date = date(2026, 3, 16)

    extracted = await lookup_cached_metrics(ticker, alert_date)
    if not extracted:
        print(f"No cached extraction for {ticker} {alert_date}")
        return

    print("=" * 80)
    print(f"NBIS RUBRIC DIAGNOSTIC — {alert_date}")
    print("=" * 80)
    print()
    print("EXTRACTION (q_revenue_usd, q_eps, q_margins, guidance, milestone):")
    for k in ("q_revenue_usd", "q_eps", "q_margins", "subscription_revenue_yoy_pct",
              "guidance_fy_revenue_usd", "guidance_change"):
        v = extracted.get(k)
        if v:
            print(f"  {k}: {json.dumps(v, default=str, indent=4)[:300]}")
    print()
    print(f"Extraction quality: {extracted.get('extraction_quality')}")
    print(f"Reasoning brief: {extracted.get('reasoning_brief', '')[:200]}")
    print()

    print("HYBRID RUBRIC INPUTS (q0 deltas + yfinance historical):")
    fund, beat, guidance = build_rubric_inputs_hybrid(ticker, extracted, alert_date)
    print("  fund (deltas):")
    for k, v in fund.items():
        if v is not None and v != {} and v != 0:
            print(f"    {k}: {v}")
    print(f"  beat: {beat}")
    print(f"  guidance: {guidance}")
    print()

    print("RUBRIC SCORING:")
    score_full = score_ticker(fund, beat=beat, guidance=guidance)
    for k, v in score_full.items():
        if k.startswith("a") and "_" in k:
            print(f"  {k}: {v}")
        elif k in ("composite_raw", "composite_scaled", "max_available", "label", "caps_applied"):
            print(f"  {k}: {v}")
    print()
    print(f"=> composite={score_full.get('composite_scaled')}/39, label='{score_full.get('label')}'")
    print(f"=> caps_applied: {score_full.get('caps_applied')}")
    print()
    print("INTERPRETATION:")
    label = score_full.get("label")
    caps = score_full.get("caps_applied") or []
    composite = score_full.get("composite_scaled", 0)
    if "no_milestone_low_growth" in caps:
        print("  Hard cap fired: no_milestone_low_growth")
        print("  Cap rule: Axis 6 milestone=False AND rev_yoy_q0 < 25% → cap at 'strong'")
        a6 = score_full.get("a6_score")
        rev_yoy = fund.get("rev_yoy_q0")
        print(f"    Axis 6 milestone score: {a6}")
        print(f"    rev_yoy_q0: {rev_yoy*100 if rev_yoy else 'None'}%")
        if a6 == 0:
            print("    => milestone NOT crossed; cap is methodology-correct.")
        elif rev_yoy is not None and rev_yoy < 0.25:
            print(f"    => revenue growth {rev_yoy*100:.1f}% < 25% magnitude threshold")
            print("    => Methodology requires BOTH milestone bonus AND 25%+ revenue to game_changer")
        print()
    if composite >= 30 and label != "game_changer":
        print("  Composite >= 30 but label not game_changer — investigation needed.")
    elif composite < 30:
        gap = 30 - composite
        print(f"  Composite {composite}/39 is {gap:.1f} points below game_changer threshold (30).")
        print(f"  To reach 30, need additional {gap:.1f} points somewhere.")


if __name__ == "__main__":
    asyncio.run(main())
