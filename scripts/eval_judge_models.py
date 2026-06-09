"""Judge model-eval harness (#250 / North Star) — READ-ONLY, NO DB writes, NO trade state.

Grades the SAME judge payload (per stored EP alert) across models via the PRODUCTION
grade_holistic call (model= override → zero call-shape drift) and surfaces where they
DISAGREE on tier or direction, with each model's rationale side-by-side for OPERATOR
labeling (the decision metric is the operator's eyeball — NOT forward returns, the
saturated-metric trap that killed the materiality R-gate, #188/ADR 0010).

Default live model stays Sonnet (#188: the grade task converges across models; the lever
is the grounded INPUT #210, not the model). This harness exists to TEST whether the
HARDER holistic-judge task diverges where the narrow catalyst-grade task didn't — built
ahead of data so it's turnkey when a real judged cohort accrues. Running it now on the
thin stored-catalyst cohort is low-info (same thin-input caveat as judge_backfill_replay);
treat a "they agree" result this week as NOT a recorded verdict.

Run: docker exec apollo-market python /app/scripts/eval_judge_models.py [--days N]
"""
import argparse
import asyncio
import os

from agents.market_intelligence.catalyst_materiality import extract_deal_value, rule_materiality
from agents.market_intelligence.collector import get_fmp_profile
from agents.market_intelligence.db import get_pool
from agents.market_intelligence.ep_grade_judge import assemble_judge_inputs, grade_holistic

# (label, model_id). Extend with haiku if a cheap-tier check is wanted; sonnet=live default.
MODELS = [
    ("sonnet", "claude-sonnet-4-6"),
    ("opus", "claude-opus-4-8"),
]

_SQL = """
SELECT ticker, alert_date,
       COALESCE(baseline_floor_tier, score_tier) AS floor_tier,
       score_tier, catalyst_quality, catalyst, claude_analysis,
       in_active_theme, in_narrative_cohort, gap_pct, pm_rvol, vol_percentile,
       ep_score, grounded_text
FROM mi_ep_alerts
WHERE alert_date >= (CURRENT_DATE - ($1::int))
  AND score_tier IN ('HIGH', 'MODERATE')
ORDER BY alert_date, ticker
"""


async def _payload_for(row) -> dict:
    """Build the judge payload once (shared across models) — same assembly as
    run_ep_scan._judge_shadow + judge_backfill_replay."""
    market_cap = sector = None
    try:
        prof = await get_fmp_profile(row["ticker"]) or {}
        market_cap, sector = prof.get("marketCap"), prof.get("sector")
    except Exception:
        pass
    try:
        _mc = float(market_cap) if market_cap is not None else None
    except (TypeError, ValueError):
        _mc = None
    rule_mat = rule_materiality(
        extract_deal_value(f"{row['catalyst'] or ''} {row['claude_analysis'] or ''}"), _mc)
    r = {
        "ticker": row["ticker"], "score_tier": row["score_tier"],
        "catalyst_quality": row["catalyst_quality"], "catalyst": row["catalyst"],
        "claude_analysis": row["claude_analysis"], "in_active_theme": row["in_active_theme"],
        "in_narrative_cohort": row["in_narrative_cohort"], "gap_pct": row["gap_pct"],
        "pm_rvol": row["pm_rvol"], "vol_percentile": row["vol_percentile"],
        "ep_score": row["ep_score"],
    }
    return assemble_judge_inputs(r, grounded_text=row["grounded_text"], market_cap=_mc,
                                sector=sector, materiality_tier=rule_mat)


async def _grade_all_models(client, sem, row) -> dict:
    payload = await _payload_for(row)
    out = {}
    for name, model in MODELS:
        async with sem:
            try:
                v = await grade_holistic(client, payload, model=model, timeout=30)
            except Exception as e:
                v = {"_err": str(e)[:60]}
        out[name] = v
    return {"ticker": row["ticker"], "alert_date": row["alert_date"],
            "floor": row["floor_tier"], "models": out}


def _tier_dir(v) -> tuple:
    if not v or "_err" in (v or {}):
        return ("ERR", "ERR")
    return (v.get("tier"), v.get("direction_vs_floor"))


async def main(days: int) -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(_SQL, days)

    print("=" * 78)
    print(f"JUDGE MODEL EVAL — last {days}d, {len(rows)} alert(s), models: "
          f"{', '.join(n for n, _ in MODELS)}")
    print("READ-ONLY. Label = operator eyeball on DISAGREEMENTS (NOT forward returns).")
    print("Thin-input caveat applies (stored catalyst, no SEC body) — low-info until a")
    print("grounded judged cohort accrues; do NOT record a verdict from a now-run.")
    print("=" * 78)
    if not rows:
        print("  No HIGH/MODERATE alerts in window — nothing to eval.")
        return

    client = None
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if api_key:
        import anthropic
        client = anthropic.AsyncAnthropic(api_key=api_key)
    sem = asyncio.Semaphore(3)

    results = []
    try:
        results = await asyncio.gather(*[_grade_all_models(client, sem, r) for r in rows])
    finally:
        if client is not None:
            try:
                await client.close()
            except Exception:
                pass

    names = [n for n, _ in MODELS]
    hdr = f"{'TICKER':7}{'DATE':12}{'FLOOR':9}" + "".join(f"{n.upper():18}" for n in names) + "FLAG"
    print(hdr)
    print("-" * len(hdr))
    ndiff = 0
    disagreements = []
    for r in results:
        cells = []
        td = {n: _tier_dir(r["models"].get(n)) for n in names}
        for n in names:
            t, d = td[n]
            cells.append(f"{(t or '?')+'/'+(d or '?'):18}")
        tiers = {td[n][0] for n in names if td[n][0] != "ERR"}
        dirs = {td[n][1] for n in names if td[n][1] != "ERR"}
        diff = len(tiers) > 1 or len(dirs) > 1
        if diff:
            ndiff += 1
            disagreements.append(r)
        print(f"{r['ticker']:7}{str(r['alert_date']):12}{str(r['floor'] or '?'):9}"
              + "".join(cells) + ("DIFF" if diff else ""))

    print(f"\n=== cross-model disagreements: {ndiff}/{len(results)} ===")
    if disagreements:
        print("\nDISAGREEMENT DETAIL (operator labels which model is right):")
        for r in disagreements:
            print(f"\n  {r['ticker']} {r['alert_date']}  floor={r['floor']}")
            for n in names:
                v = r["models"].get(n) or {}
                if "_err" in v:
                    print(f"    {n:7}: ERR {v['_err']}")
                    continue
                print(f"    {n:7}: {v.get('tier')}/{v.get('direction_vs_floor')} "
                      f"mat={v.get('materiality_tier')} — {(v.get('rationale') or '')[:170]}")
    print("\nCost note: per-grade cost ≈ each model's token rate (sonnet $3/$15, opus $15/$75 "
          "per 1M in/out); the decision lever is QUALITY on disagreements, cost = tiebreaker "
          "(feedback_model_selection_quality_over_cost). Default stays Sonnet until evidence flips it.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=14)
    args = ap.parse_args()
    asyncio.run(main(args.days))
