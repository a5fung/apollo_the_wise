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

--grounded (#252): reconstructs the point-in-time corpus (SEC+wires ≤ detected_at, no
web — same helper as judge_backfill_replay.py) so the Sonnet-vs-Opus comparison runs on
the GROUNDED input the live judge actually sees. The 6/9 thin-cohort divergence is
artifact-suspect (strong models diverge most on thin input); only grounded
disagreements, operator-labeled, may update docs/model_selection_baseline.md.
#253 caveat applies: the reconstruction omits Perplexity/web (lookahead-unsafe), so
web-sourced catalysts are invisible to BOTH models — a fair pairwise comparison, but
not a statement about absolute grade quality on those names.

Run: docker exec apollo-market python /app/scripts/eval_judge_models.py [--days N] [--grounded]
"""
import argparse
import asyncio
import os

from agents.market_intelligence.db import get_pool
from agents.market_intelligence.ep_grade_judge import grade_holistic
from scripts._judge_replay_common import REPLAY_SQL as _SQL
from scripts._judge_replay_common import (
    build_judge_payload, fetch_profile, resolve_grounded_text,
)
from shared.llm_models import OPUS, SONNET

# (label, model_id). Registry constants so the model-selection eval can't itself be a
# drifted call site (the advisor-on-4-6-vs-eval-on-4-8 class). Extend with HAIKU if a
# cheap-tier check is wanted; sonnet = live default.
MODELS = [
    ("sonnet", SONNET),
    ("opus", OPUS),
]


async def _payload_for(row, grounded: bool) -> dict:
    """Build the judge payload once (shared across models) — same assembly as
    run_ep_scan._judge_shadow + judge_backfill_replay (via _judge_replay_common)."""
    _mc, sector, company = await fetch_profile(row["ticker"])
    grounded_text, _ginfo = await resolve_grounded_text(row, company, grounded)
    payload, _rule_mat = build_judge_payload(row, grounded_text, _mc, sector)
    return payload


async def _grade_all_models(client, sem, row, grounded: bool) -> dict:
    payload = await _payload_for(row, grounded)
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


async def main(days: int, grounded: bool) -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(_SQL, days)

    print("=" * 78)
    mode = "GROUNDED (reconstructed point-in-time SEC+wires corpus)" if grounded \
        else "THIN (stored catalyst proxy unless grounded_text persisted)"
    print(f"JUDGE MODEL EVAL [{mode}] — last {days}d, {len(rows)} alert(s), models: "
          f"{', '.join(n for n, _ in MODELS)}")
    print("READ-ONLY. Label = operator eyeball on DISAGREEMENTS (NOT forward returns).")
    if grounded:
        print("Grounded disagreements ARE verdict-eligible (operator labels → update")
        print("docs/model_selection_baseline.md). Corpus omits Perplexity/web (#253):")
        print("fair pairwise comparison; web-catalyst names are blind for BOTH models.")
    else:
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
        results = await asyncio.gather(*[_grade_all_models(client, sem, r, grounded) for r in rows])
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
    from shared.llm_models import PRICING_PER_MTOK as _PR
    rates = " · ".join(
        f"{n} ${_PR[m]['input']:g}/${_PR[m]['output']:g}" for n, m in MODELS if m in _PR)
    print(f"\nCost note: per-grade cost ≈ each model's token rate ({rates} per 1M in/out); "
          "the decision lever is QUALITY on disagreements, cost = tiebreaker "
          "(feedback_model_selection_quality_over_cost). Default stays Sonnet until evidence flips it.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=14)
    ap.add_argument("--grounded", action="store_true",
                    help="reconstruct the point-in-time SEC+wires corpus (≤ detected_at, "
                         "no web) instead of the thin stored catalyst (#252)")
    args = ap.parse_args()
    asyncio.run(main(args.days, args.grounded))
