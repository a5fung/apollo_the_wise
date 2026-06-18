"""#329 Path A — judge-PAYLOAD-ENRICH eval. Quantifies the call-site blindness the
reconciliation spec found (docs/analysis/meta_rubric_reconciliation_329_2026-06-18.md):
the LIVE judge call threads NEITHER has_direct_source NOR theme stage/score, so its prompt
always reads "Direct source present: no" and it can't weight theme heat.

READ-ONLY. No DB writes, no trade-state.

TWO modes, sizing-pass-FIRST (advisor 2026-06-18 — localize before you spend):

  --size-only  (DEFAULT, NO API SPEND): recompute has_direct_source DETERMINISTICALLY from the
      stored grounded_text section markers ([SEC … / [Benzinga … = direct; [Web summary] = not)
      — high fidelity to what the judge actually saw, no reconstruction. Report the BLAST RADIUS:
      of judge promote/materiality-leaning rows, how many had a direct source present while the
      judge was shown "no". Handful → the "likely live defect" is small (skip the spend); large →
      it justifies re-grading that at-risk subset. Pre-W1 thin-grounded rows (no markers at all)
      are segmented OUT — they can't be assessed from stored text.

  --regrade    (OPERATOR-TRIGGERED, COSTS Opus judge calls): two-arm re-grade — BLIND payload
      (today's behavior) vs ENRICHED (has_direct_source recomputed + AS-OF-DATE theme heat) —
      surfacing rows whose verdict CHANGED, for OPERATOR labeling (ADR 0011: the judge is
      load-bearing; the agent never self-scores the flip). `--replicates K` measures the judge's
      intrinsic run-to-run flip rate so an enrich-driven delta is only credited when the blind
      verdict was stable.

DISCIPLINE:
  • AS-OF theme heat — mi_themes WHERE theme_date <= alert_date (NOT get_theme_membership, which
    returns CURRENT membership = lookahead on an old alert). Same as-of rule fetch_narratives_for
    uses.
  • has_direct_source from STORED grounded_text, not grounded=True reconstruction — fidelity to
    what the judge saw; reconstruction can pull sources the live grade never had.
  • SMOKE (small --limit) validates MACHINERY + the marker-recompute, NOT efficacy.

Run (read-only, on the server — needs prod DB):
  docker exec apollo-market python /app/scripts/eval_judge_enrich.py --days 30           # sizing, no spend
  docker exec apollo-market python /app/scripts/eval_judge_enrich.py --regrade --days 30 --limit 8 --replicates 3
"""
import argparse
import asyncio
from collections import Counter

from agents.market_intelligence.db import get_pool
from agents.market_intelligence.ep_grade_judge import format_tier_transition, grade_holistic
from scripts._judge_replay_common import (
    build_judge_payload, fetch_narratives_for, fetch_profile, resolve_grounded_text,
)

# Cohort for the sizing pass — the judge decision columns + the stored corpus. score_tier is the
# (possibly judge-overridden) tier; baseline_floor_tier is the floor counterfactual.
_SIZE_SQL = """
SELECT ticker, alert_date, detected_at, score_tier,
       COALESCE(baseline_floor_tier, score_tier) AS floor_tier,
       judge_tier, judge_direction, judge_materiality_tier,
       grade_engine_authority, grounded_text
FROM mi_ep_alerts
WHERE alert_date >= (CURRENT_DATE - ($1::int))
  AND grade_engine_authority IS NOT NULL        -- judge actually rendered a verdict
ORDER BY alert_date, ticker
"""

# Materiality tiers that mean "the judge leaned on materiality" (the highest-risk pattern when
# has_direct_source was falsely "no" — ADR 0011 rubric clause 1/2).
_MATERIAL_LEAN = {"transformative", "material"}


def recompute_has_direct_source(grounded_text: str | None) -> tuple[bool, bool]:
    """(has_direct, has_markers) from the STORED corpus, deterministically. build_grounded_text
    prefixes each source: '[SEC <form> filed …]', '[Benzinga …]', '[Web summary] …'. A direct
    source = an SEC filing or a Benzinga wire present (mirrors classify_catalyst_sources'
    sec_*/benzinga_pr rule). `has_markers` is False for pre-W1 / thin-grounded rows that carry no
    section markers at all — those can't be assessed from stored text and are excluded from the
    blast-radius denominator."""
    if not grounded_text:
        return False, False
    has_markers = ("[SEC " in grounded_text or "[Benzinga " in grounded_text
                   or "[Web summary]" in grounded_text)
    has_direct = ("[SEC " in grounded_text or "[Benzinga " in grounded_text)
    return has_direct, has_markers


async def _fetch_theme_heat_asof(conn, ticker: str, alert_date):
    """(stage, score) of the hottest theme containing `ticker` AS OF alert_date — theme_date <=
    alert_date (NO lookahead; get_theme_membership would return TODAY's membership). None if
    uncovered as of that date."""
    row = await conn.fetchrow("""
        SELECT stage, score
        FROM mi_themes
        WHERE $1 = ANY(tickers)
          AND stage != 'Retired'
          AND theme_date <= $2
        ORDER BY theme_date DESC, score DESC NULLS LAST
        LIMIT 1
    """, ticker, alert_date)
    if not row:
        return None, None
    return row["stage"], (float(row["score"]) if row["score"] is not None else None)


async def run_size_only(days: int) -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(_SIZE_SQL, days)

    total = len(rows)
    no_markers = 0
    assessable = 0
    direct_present = 0          # had a direct source the judge was shown "no" for
    direct_and_material_lean = 0
    direct_and_promote = 0
    at_risk = []                # the subset worth re-grading: direct source + (promote OR material-lean)

    for r in rows:
        has_direct, has_markers = recompute_has_direct_source(r["grounded_text"])
        if not has_markers:
            no_markers += 1
            continue
        assessable += 1
        if not has_direct:
            continue
        # The judge was ALWAYS shown has_direct_source=False at the live call site → every
        # direct-source row is a row graded blind to its own source.
        direct_present += 1
        mat_lean = (r["judge_materiality_tier"] or "").lower() in _MATERIAL_LEAN
        promote = (r["judge_direction"] or "").lower() == "promote"
        if mat_lean:
            direct_and_material_lean += 1
        if promote:
            direct_and_promote += 1
        if mat_lean or promote:
            at_risk.append(r)

    print(f"\n=== #329 has_direct_source BLAST RADIUS (last {days}d, judge-graded rows) ===")
    print(f"  judge-graded rows ............................. {total}")
    print(f"  excluded (pre-W1 / thin, no corpus markers) ... {no_markers}")
    print(f"  assessable (stored corpus has markers) ........ {assessable}")
    print(f"  DIRECT source present, judge shown 'no' ....... {direct_present}"
          f"  ({(100*direct_present/assessable if assessable else 0):.0f}% of assessable)")
    print(f"    ↳ of those, judge PROMOTED .................. {direct_and_promote}")
    print(f"    ↳ of those, judge leaned MATERIAL/transformative {direct_and_material_lean}")
    print(f"  AT-RISK subset (direct + promote/material-lean) {len(at_risk)}  ← re-grade target")
    print("\n  Read: every 'direct present' row was graded blind to its own SEC/wire source;")
    print("  the freshness clause (rubric v3) applies 'no source → prefer floor' to ALL of them.")
    print("  AT-RISK is where that blindness most plausibly distorted the verdict — re-grade ONLY")
    print("  that subset (--regrade) and have the OPERATOR label the flips. Small → defect is minor.")
    if at_risk:
        print("\n  at-risk rows:")
        for r in at_risk[:40]:
            print(f"    {r['alert_date']} {r['ticker']:6s} judge={r['judge_tier']} "
                  f"dir={r['judge_direction']} mat={r['judge_materiality_tier']}")


async def run_regrade(days: int, limit: int, replicates: int) -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(_SIZE_SQL, days)
    # Re-grade only the assessable rows with a direct source the judge was blind to (the at-risk
    # signal) — that's where enrich can move the verdict. Cap by --limit for cost control.
    cohort = []
    for r in rows:
        has_direct, has_markers = recompute_has_direct_source(r["grounded_text"])
        if has_markers and has_direct:
            cohort.append((r, has_direct))
    cohort = cohort[:limit] if limit else cohort
    if not cohort:
        print("eval_judge_enrich --regrade: no direct-source rows in window — nothing to re-grade.")
        return
    print(f"eval_judge_enrich --regrade: {len(cohort)} rows × ({replicates}+1) judge calls "
          f"(BLIND ×K noise floor + 1 ENRICHED). Opus spend — operator-triggered.\n")

    flips, noise = [], []
    async with pool.acquire() as conn:
        for r, has_direct in cohort:
            mc, sector, company = await fetch_profile(r["ticker"])
            grounded, _ = await resolve_grounded_text(r, company, grounded=False)  # stored corpus
            narr = await fetch_narratives_for(r["alert_date"])
            stage, score = await _fetch_theme_heat_asof(conn, r["ticker"], r["alert_date"])

            # BLIND arm × K (today's payload — no has_direct_source, no theme heat).
            blind_tiers = []
            for _ in range(max(1, replicates)):
                p, _m = build_judge_payload(r, grounded, mc, sector, active_narratives=narr)
                v = await grade_holistic(_get_client(), p, timeout=25)
                blind_tiers.append(v.get("tier") if v else None)
            stable = len(set(blind_tiers)) == 1
            blind = blind_tiers[0]

            # ENRICHED arm (recomputed direct-source + as-of theme heat).
            pe, _m = build_judge_payload(
                r, grounded, mc, sector, active_narratives=narr,
                has_direct_source=has_direct, theme_stage=stage, theme_score=score)
            ve = await grade_holistic(_get_client(), pe, timeout=25, include_axis_reads=True)
            enriched = ve.get("tier") if ve else None

            rec = (r["ticker"], r["alert_date"], blind, enriched, stable, stage, score)
            if blind != enriched:
                (flips if stable else noise).append((rec, ve))

    print(f"--- VERDICT FLIPS (blind stable, enrich changed it) — {len(flips)}, for operator labeling ---")
    for (tk, d, b, e, _s, stage, score), ve in flips:
        heat = f"{stage}/{score}" if stage else "no-theme"
        print(f"  {d} {tk:6s} {format_tier_transition(b, e)}  theme-heat={heat}  "
              f"axes={','.join(ve.get('fire_axes') or []) if ve else '-'}")
        if ve and ve.get("rationale"):
            print(f"         \"{ve['rationale'][:160]}\"")
    print(f"\n--- NOISE (blind verdict itself unstable across K) — {len(noise)}, NOT enrich effects ---")
    for (tk, d, b, e, _s, _st, _sc), _ve in noise:
        print(f"  {d} {tk:6s} {b}->{e} (blind unstable)")


def _get_client():
    """Anthropic async client (prod creds in the container env)."""
    from agents.market_intelligence.ep_detector import _get_claude
    return _get_claude()


async def _main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=30)
    ap.add_argument("--regrade", action="store_true",
                    help="two-arm re-grade (COSTS Opus spend); default is the no-spend sizing pass")
    ap.add_argument("--limit", type=int, default=8, help="--regrade cohort cap (cost control)")
    ap.add_argument("--replicates", type=int, default=3, help="--regrade blind noise-floor reps")
    args = ap.parse_args()
    if args.regrade:
        await run_regrade(args.days, args.limit, args.replicates)
    else:
        await run_size_only(args.days)


if __name__ == "__main__":
    asyncio.run(_main())
