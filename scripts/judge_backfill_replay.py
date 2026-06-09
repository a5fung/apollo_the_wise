"""Judge backfill replay (#250 / North Star) — INTEGRATION + MATERIALITY/STRUCTURE validator.

READ-ONLY. NO DB WRITES. Re-grades recent mi_ep_alerts through the holistic judge
(grade_holistic) on the STORED catalyst+analysis (point-in-time by construction — these
columns were computed at alert time, no lookahead) + a freshly-fetched market cap, and
prints the judge's bidirectional deltas. Built 2026-06-09 because a correction-thinned
EP tape could go weeks without a live judged alert, and we want the integration proven +
a review cohort to eyeball NOW.

WHAT THIS FAITHFULLY VALIDATES (same inputs live vs here) — flip-authorizing:
  • the run→judge INTEGRATION fires end-to-end on real rows;
  • the MATERIALITY axis (W4 deterministic deal-size÷market-cap), GAP, THEME/NARRATIVE axes.
WHAT IT DOES NOT (advisor 2026-06-09) — NOT flip-authorizing:
  • anything hinging on grounded-catalyst REALITY (hollow PR? real catalyst > headline?).
    For rows without a persisted grounded_text the judge sees the 500-char `catalyst`, NOT
    the SEC-body corpus the live judge uses — the exact thin-input failure (#187 RUM) the
    live path was built to avoid. So the grounded-judgment dimension of the flip gate STILL
    needs >=1 real LIVE judged alert (or a faithfully reconstructed corpus).

Per-row tag operationalizes the discriminating check:
  [STRUCT]  deterministic materiality anchor present (deal/cap computed) OR real grounded_text
            present → the verdict rests on faithful inputs → flip-authorizing.
  [GROUND?] no deterministic anchor and no grounded_text → the verdict leans on the thin
            catalyst summary → treat as indicative only, confirm against a live alert.

Run (read-only): docker exec apollo-market python /app/scripts/judge_backfill_replay.py [--days N]
"""
import argparse
import asyncio
import os

from agents.market_intelligence.catalyst_materiality import extract_deal_value, rule_materiality
from agents.market_intelligence.collector import get_fmp_profile
from agents.market_intelligence.db import get_pool
from agents.market_intelligence.ep_grade_judge import assemble_judge_inputs, grade_holistic

# Floor = COALESCE(baseline_floor_tier, score_tier): baseline_floor_tier is NULL on pre-W2
# rows (added ~2026-06-08 15:10 ET); score_tier is the floor verdict that actually drove them.
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


async def _replay_one(client, sem, row) -> dict:
    """Fetch cap, compute the W4 deterministic materiality, run the judge. Read-only."""
    ticker = row["ticker"]
    market_cap = sector = None
    try:
        prof = await get_fmp_profile(ticker) or {}
        market_cap, sector = prof.get("marketCap"), prof.get("sector")
    except Exception:
        pass
    try:
        _mc = float(market_cap) if market_cap is not None else None
    except (TypeError, ValueError):
        _mc = None
    rule_mat = rule_materiality(
        extract_deal_value(f"{row['catalyst'] or ''} {row['claude_analysis'] or ''}"), _mc)

    # Mirror run_ep_scan._judge_shadow: real grounded_text when persisted, else stored catalyst.
    r = {
        "ticker": ticker, "score_tier": row["score_tier"], "catalyst_quality": row["catalyst_quality"],
        "catalyst": row["catalyst"], "claude_analysis": row["claude_analysis"],
        "in_active_theme": row["in_active_theme"], "in_narrative_cohort": row["in_narrative_cohort"],
        "gap_pct": row["gap_pct"], "pm_rvol": row["pm_rvol"], "vol_percentile": row["vol_percentile"],
        "ep_score": row["ep_score"],
    }
    payload = assemble_judge_inputs(
        r, grounded_text=row["grounded_text"], market_cap=_mc, sector=sector,
        materiality_tier=rule_mat)
    async with sem:
        verdict = await grade_holistic(client, payload, timeout=30)

    has_grounded = bool(row["grounded_text"])
    # Flip-authorizing iff the verdict rests on faithful inputs (deterministic anchor or
    # real grounded corpus); otherwise it leans on the thin catalyst summary.
    faithful = (rule_mat is not None) or has_grounded
    return {
        "ticker": ticker, "alert_date": row["alert_date"], "floor": row["floor_tier"],
        "rule_mat": rule_mat, "has_grounded": has_grounded, "faithful": faithful,
        "verdict": verdict,
    }


async def main(days: int) -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(_SQL, days)

    print("=" * 78)
    print(f"JUDGE BACKFILL REPLAY — last {days}d, {len(rows)} stored alert(s) re-graded")
    print("READ-ONLY · NO DB WRITES · proxy: stored catalyst (no SEC body) unless grounded_text present")
    print("[STRUCT] = faithful inputs (deal/cap anchor OR real grounded_text) → flip-authorizing")
    print("[GROUND?] = leans on thin catalyst summary → indicative only, confirm vs a live alert")
    print("Validates: integration + materiality/gap/theme.  Does NOT validate grounded-catalyst reality.")
    print("=" * 78)
    if not rows:
        print("  No HIGH/MODERATE alerts in window — nothing to replay.")
        return

    client = None
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if api_key:
        import anthropic
        client = anthropic.AsyncAnthropic(api_key=api_key)
    sem = asyncio.Semaphore(3)

    results = []
    try:
        results = await asyncio.gather(*[_replay_one(client, sem, r) for r in rows])
    finally:
        if client is not None:
            try:
                await client.close()
            except Exception:
                pass

    promotes = demotes = holds = nulls = 0
    deltas = []
    for r in results:
        v = r["verdict"]
        if v is None:
            nulls += 1
            continue
        d = v["direction_vs_floor"]
        promotes += d == "promote"
        demotes += d == "demote"
        holds += d == "hold"
        if d in ("promote", "demote"):
            deltas.append((r, v))

    print(f"\nSummary: ▲{promotes} promote · ▼{demotes} demote · ={holds} hold · "
          f"{nulls} judge-null (fail-open to floor)\n")

    if not deltas:
        print("  No promote/demote deltas — judge held the floor on every name "
              "(or all fail-open). Integration + materiality path still exercised above.")
    else:
        print("DELTAS (the judgment-correctness review surface):")
        for r, v in deltas:
            tag = "[STRUCT]" if r["faithful"] else "[GROUND?]"
            arrow = "▲" if v["direction_vs_floor"] == "promote" else "▼"
            print(f"\n  {arrow} {tag} {r['ticker']:6} {r['alert_date']}  "
                  f"{r['floor']}→{v['tier']}  mat={v.get('materiality_tier')} "
                  f"(rule={r['rule_mat']}, grounded={'Y' if r['has_grounded'] else 'N'})")
            print(f"        {(v.get('rationale') or '')[:240]}")

    n_struct = sum(1 for r, _ in deltas if r["faithful"])
    print(f"\nOf {len(deltas)} delta(s): {n_struct} [STRUCT] (flip-authorizing) · "
          f"{len(deltas) - n_struct} [GROUND?] (confirm vs a live alert).")
    print("HARD gate: the OPERATOR reviews these; the agent never self-certifies the deltas. "
          "Grounded-judgment dimension still needs >=1 real LIVE judged alert.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=14)
    args = ap.parse_args()
    asyncio.run(main(args.days))
