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

--grounded CAVEAT (#253, RCAT 2026-05-28): the reconstructed corpus is SEC+wires ONLY —
Perplexity/web is omitted because it can't be fetched point-in-time (lookahead). Web-sourced
catalysts (RCAT's Japan drone contract + Quaze acquisition lived only in Perplexity/web) are
therefore INVISIBLE in grounded replay, so --grounded is a CONSERVATIVE LOWER BOUND that can
over-demote web-sourced/theme-driven names. The LIVE judge is NOT blind there: it gets the
point-in-time Perplexity text inside grounded_text at alert time. Treat grounded demotes on
web-catalyst names as replay artifacts until cross-checked against the stored live grade.

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

from agents.market_intelligence.db import get_pool
from agents.market_intelligence.ep_grade_judge import grade_holistic
from scripts._grounded_reconstruct import reconstruct_grounded_text
from scripts._judge_replay_common import REPLAY_SQL as _SQL
from scripts._judge_replay_common import (
    build_judge_payload, fetch_narratives_for, fetch_profile,
)


async def _replay_one(client, sem, row, grounded: bool, narratives=None) -> dict:
    """Fetch cap, compute the W4 deterministic materiality, run the judge. Read-only.
    grounded=True reconstructs the point-in-time corpus (SEC+wires ≤ detected_at, no web)
    instead of using the thin stored catalyst — closes #252's thin-input caveat.
    `narratives` = point-in-time PRIOR-day Lane-2 cohorts (lane2-judge-theme-axis)."""
    ticker = row["ticker"]
    _mc, sector, company = await fetch_profile(ticker)

    # grounded=True → reconstruct point-in-time corpus; else use stored grounded_text
    # (real on post-W1 rows, else assemble falls back to the thin stored catalyst).
    ginfo = None
    if grounded:
        grounded_text, ginfo = await reconstruct_grounded_text(
            ticker, row["alert_date"], row["detected_at"], company_name=company or "")
    else:
        grounded_text = row["grounded_text"]

    payload, rule_mat = build_judge_payload(row, grounded_text, _mc, sector,
                                            active_narratives=narratives)
    async with sem:
        verdict = await grade_holistic(client, payload, timeout=30)

    has_grounded = bool(grounded_text)
    # Flip-authorizing iff the verdict rests on faithful inputs (deterministic anchor or
    # a real/reconstructed grounded corpus); otherwise it leans on the thin catalyst summary.
    faithful = (rule_mat is not None) or has_grounded
    return {
        "ticker": ticker, "alert_date": row["alert_date"], "floor": row["floor_tier"],
        "rule_mat": rule_mat, "has_grounded": has_grounded, "faithful": faithful,
        "ginfo": ginfo, "verdict": verdict,
        "n_narr": len(narratives or []),
        "narr_backfilled": any(n.get("backfilled") for n in (narratives or [])),
    }


async def main(days: int, grounded: bool, ticker: str | None = None,
               narratives: bool = False) -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(_SQL, days)
        if ticker:
            rows = [r for r in rows if r["ticker"] == ticker.upper()]
        # Point-in-time PRIOR-day Lane-2 cohorts per alert_date (one query per distinct
        # date; replay-only — includes tagged backfill rows, see _judge_replay_common).
        narr_by_date: dict = {}
        if narratives:
            for d in {r["alert_date"] for r in rows}:
                narr_by_date[d] = await fetch_narratives_for(conn, d)

    print("=" * 78)
    mode = "GROUNDED (point-in-time SEC+wires ≤ detected_at, no web)" if grounded \
        else "THIN (stored catalyst proxy unless grounded_text persisted)"
    print(f"JUDGE BACKFILL REPLAY [{mode}] — last {days}d, {len(rows)} alert(s) re-graded")
    print("READ-ONLY · NO DB WRITES (reconstruction is in-memory, never persisted)")
    if grounded:
        print("Grounded mode CLOSES the thin-input caveat → deltas are grade-FAITHFUL for review.")
        print("Still validates GRADE faithfulness ONLY — NOT the live run_ep_scan write path")
        print("(needs ≥1 real live alert). [STRUCT]=reconstructed corpus or deal/cap anchor present.")
        print("⚠ LOWER BOUND (#253): corpus omits Perplexity/web (lookahead-unsafe) — web-sourced")
        print("  catalysts are invisible here and can be over-demoted (RCAT 5/28 class). The LIVE")
        print("  judge gets point-in-time Perplexity in grounded_text and is NOT blind to them.")
    else:
        print("[STRUCT] = faithful inputs (deal/cap anchor OR real grounded_text) → flip-authorizing")
        print("[GROUND?] = leans on thin catalyst summary → indicative only (re-run --grounded).")
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
        results = await asyncio.gather(*[
            _replay_one(client, sem, r, grounded, narratives=narr_by_date.get(r["alert_date"]))
            for r in rows
        ])
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

    # direction_vs_floor is the judge's own qualitative call and can disagree with the
    # tier outcome (#253: ASAN/SAIC/PHR direction=promote, tier stayed MODERATE — a
    # quality read, NOT a tier upgrade). Count + display tier changes explicitly.
    tier_changes = sum(1 for r, v in deltas if v["tier"] != r["floor"])
    print(f"\nSummary: ▲{promotes} promote · ▼{demotes} demote · ={holds} hold · "
          f"{nulls} judge-null (fail-open to floor) · {tier_changes} TIER change(s)\n")

    if not deltas:
        print("  No promote/demote deltas — judge held the floor on every name "
              "(or all fail-open). Integration + materiality path still exercised above.")
    else:
        print("DELTAS (the judgment-correctness review surface):")
        for r, v in deltas:
            tag = "[STRUCT]" if r["faithful"] else "[GROUND?]"
            arrow = "▲" if v["direction_vs_floor"] == "promote" else "▼"
            src = ""
            if r.get("ginfo"):
                g = r["ginfo"]
                src = f", corpus[sec={'Y' if g['has_sec'] else 'N'} wires={g['n_benzinga']}]"
            tier_part = (f"TIER {r['floor']}→{v['tier']}" if v["tier"] != r["floor"]
                         else f"tier unchanged ({r['floor']}; {v['direction_vs_floor']} = quality read only)")
            narr_part = ""
            if r.get("n_narr"):
                narr_part = f", narr={r['n_narr']}{'(incl. backfill)' if r.get('narr_backfilled') else ''}"
            print(f"\n  {arrow} {tag} {r['ticker']:6} {r['alert_date']}  "
                  f"{tier_part}  mat={v.get('materiality_tier')} "
                  f"(rule={r['rule_mat']}, grounded={'Y' if r['has_grounded'] else 'N'}{src}{narr_part})")
            print(f"        {(v.get('rationale') or '')[:240]}")

    n_struct = sum(1 for r, _ in deltas if r["faithful"])
    print(f"\nOf {len(deltas)} delta(s): {n_struct} [STRUCT] (flip-authorizing) · "
          f"{len(deltas) - n_struct} [GROUND?] (confirm vs a live alert).")
    print("HARD gate: the OPERATOR reviews these; the agent never self-certifies the deltas. "
          "Grounded-judgment dimension still needs >=1 real LIVE judged alert.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=14)
    ap.add_argument("--grounded", action="store_true",
                    help="reconstruct point-in-time SEC+wires corpus (≤ detected_at, no web) "
                         "instead of the thin stored catalyst — grade-faithful review cohort")
    ap.add_argument("--ticker", type=str, default=None,
                    help="replay a single ticker only (cheap acceptance runs)")
    ap.add_argument("--narratives", action="store_true",
                    help="feed point-in-time PRIOR-day Lane-2 narrative cohorts into the "
                         "judge theme axis (lane2-judge-theme-axis; backfill rows tagged, "
                         "replay-only admissibility)")
    args = ap.parse_args()
    asyncio.run(main(args.days, args.grounded, ticker=args.ticker, narratives=args.narratives))
