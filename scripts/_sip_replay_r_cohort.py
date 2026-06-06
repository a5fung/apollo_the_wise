"""Lever A — SIP-augmented R cohort for the Gate-3 live-cutover decision.

READ-ONLY. No DB writes, no trade-state mutation. Safe to run via
`docker exec apollo-market python scripts/_sip_replay_r_cohort.py [--days N]`.

WHY THIS EXISTS
---------------
Gate 3 (realized-R expectancy) is the single biggest live-cutover blocker. The
naive evidence — actually-filled paper trades — is biased LOW: our paper account
fills off IEX, which misses the fast clean breakouts (the best setups), so the
filled cohort is missing exactly the winners (memory:
paper_iex_vs_live_sip_gate_adjustment; the raw paper-IEX cohort ran -$9,475).

This script recovers the dropped names by replaying the CANCELLED ORB candidates
on Polygon's consolidated tape (SIP-equivalent, full-market) via the #180
`replay_one`, then expresses everything as R-multiples so it composes with the
real filled cohort. Output is three lines (advisor 2026-06-06):

  1. REAL-R-only       — actually-filled closed trades. Real evidence, biased LOW.
  2. SIP-augmented     — real + the would_have_filled synthetic recoveries.
  3. THE GAP           — (2) - (1) = the magnitude of the IEX winner-drop. This
                          is the number Lever A actually delivers.

HARD BOUNDARY (the operator's fabrication line): half of (2) is SIMULATION, not
realized fills. The REAL vs SIMULATED split is labelled unmistakably below so the
6/22 reader cannot mistake a synthetic proxy for a realized fill.

CRITICAL INTERPRETATION (baked into the output):
  - SIP can only recover `would_have_filled` (trigger hit, price pulled back to
    the limit, then ran — NBBO touched the limit even though IEX's thin book
    didn't). It CANNOT recover `gap_through` (blasted past the limit and never
    returned) — same stop-limit, same miss. So the would_have_filled : gap_through
    ratio in the cancelled cohort is itself a HEADLINE Lever-A finding: it bounds
    how much recovery is even possible.
  - The synthetic exit is a FLOOR proxy (entry@limit, exit@stop or day-1 EOD
    close, no trailing/partials). It TRUNCATES multi-day winners, so SIP-augmented
    R is a conservative LOWER BOUND. Therefore: clears the GO bar -> strong signal;
    fails the bar -> AMBIGUOUS, not a NO-GO. A sub-threshold proxy must not be
    read as disqualifying.
"""
from __future__ import annotations

import argparse
import asyncio
import statistics as _stats
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agents.market_intelligence.db import get_pool
from scripts.replay_would_have_filled import replay_one  # #180 per-row SIP replay

# Raw paper-IEX cohort baseline for context (memory: paper_iex_vs_live_sip_gate_adjustment).
_PAPER_IEX_BASELINE_USD = -9475.0


def _r_stats(rs: list[float]) -> dict:
    """Distribution summary for a list of R-multiples (chronological order assumed
    for the sequential max-drawdown)."""
    if not rs:
        return {"n": 0}
    wins = [r for r in rs if r > 0]
    losses = [r for r in rs if r <= 0]
    # Sequential max drawdown of the cumulative-R equity curve.
    cum = 0.0
    peak = 0.0
    max_dd = 0.0
    for r in rs:
        cum += r
        peak = max(peak, cum)
        max_dd = max(max_dd, peak - cum)
    return {
        "n": len(rs),
        "total_r": sum(rs),
        "expectancy": _stats.mean(rs),               # mean R = the headline edge
        "median_r": _stats.median(rs),
        "win_rate": len(wins) / len(rs),
        "avg_win_r": _stats.mean(wins) if wins else 0.0,
        "avg_loss_r": _stats.mean(losses) if losses else 0.0,
        "p10": _percentile(rs, 10),
        "p90": _percentile(rs, 90),
        "max_dd_r": max_dd,
    }


def _percentile(xs: list[float], pct: float) -> float:
    s = sorted(xs)
    if not s:
        return 0.0
    k = (len(s) - 1) * (pct / 100.0)
    lo = int(k)
    hi = min(lo + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (k - lo)


def _fmt_stats(label: str, st: dict) -> str:
    if st.get("n", 0) == 0:
        return f"  {label:<18} N=0  (no rows)"
    return (
        f"  {label:<18} N={st['n']:<3}  "
        f"E[R]={st['expectancy']:+.3f}  med={st['median_r']:+.3f}  "
        f"win={st['win_rate']*100:.0f}%  "
        f"avgW={st['avg_win_r']:+.2f}  avgL={st['avg_loss_r']:+.2f}  "
        f"totR={st['total_r']:+.1f}  maxDD={st['max_dd_r']:.1f}R  "
        f"[p10 {st['p10']:+.2f} .. p90 {st['p90']:+.2f}]"
    )


async def _real_cohort(conn, days: int | None, signal_type: str) -> list[dict]:
    """Actually-filled, closed trades. Real realized R = total_pnl / risk_dollars.
    pnl_attribution IS NULL = methodology-evaluation filter (db.py: exclude
    bug-distorted rows from Gate-3 R)."""
    where_days = f"AND alert_date >= CURRENT_DATE - INTERVAL '{int(days)} days'" if days else ""
    rows = await conn.fetch(f"""
        SELECT ticker, alert_date, total_pnl, risk_dollars, hold_days
        FROM mi_live_trades
        WHERE status = 'closed'
          AND account_mode = 'paper'
          AND signal_type = $1
          AND pnl_attribution IS NULL
          AND risk_dollars IS NOT NULL AND risk_dollars <> 0
          {where_days}
        ORDER BY alert_date ASC
    """, signal_type)
    out = []
    for r in rows:
        out.append({"ticker": r["ticker"], "date": r["alert_date"],
                    "r": float(r["total_pnl"] or 0) / float(r["risk_dollars"]),
                    "hold_days": r["hold_days"]})
    return out


async def _cancelled_rows(conn, days: int | None, signal_type: str) -> list[dict]:
    """Cancelled ORB candidates = the IEX-dropped cohort (placed then cancelled
    unfilled). Same cohort definition as #180 replay_would_have_filled.main."""
    where_days = f"AND alert_date >= CURRENT_DATE - INTERVAL '{int(days)} days'" if days else ""
    rows = await conn.fetch(f"""
        SELECT ticker, alert_date, orb_high, orb_low, entry_price,
               stop_price, entry_shares, skip_reason
        FROM mi_live_trades
        WHERE status = 'cancelled'
          AND entry_order_id IS NOT NULL
          AND orb_high IS NOT NULL
          AND account_mode = 'paper'
          AND signal_type = $1
          {where_days}
        ORDER BY alert_date ASC
    """, signal_type)
    return [dict(r) for r in rows]


async def main(days: int | None, signal_type: str):
    pool = await get_pool()
    async with pool.acquire() as conn:
        real = await _real_cohort(conn, days, signal_type)
        cancelled = await _cancelled_rows(conn, days, signal_type)

    win = f"last {days}d" if days else "all history"
    print(f"\n{'='*72}")
    print(f"Lever A — SIP-augmented R cohort   [{signal_type} · paper · {win}]")
    print(f"{'='*72}")

    # ── 1. COHORT SPLIT — the fail-fast headline ────────────────────────────
    # SIP recovers ONLY would_have_filled; gap_through is unrecoverable.
    cls_counts: Counter = Counter()
    synth_r: list[float] = []
    synth_detail: list[tuple] = []
    for row in cancelled:
        out = await replay_one(row)
        if "error" in out:
            cls_counts["error"] += 1
            continue
        cls = out["classification"]
        cls_counts[cls] += 1
        if cls == "would_have_filled" and out.get("pnl") is not None:
            risk = (out["limit"] - out["stop"]) * (out["shares"] or 0)
            if risk > 0:
                r = out["pnl"] / risk
                synth_r.append(r)
                synth_detail.append((out["ticker"], out["date"], r, out["pnl"]))

    wf = cls_counts.get("would_have_filled", 0)
    gt = cls_counts.get("gap_through", 0)
    recoverable = (wf / (wf + gt) * 100) if (wf + gt) else 0.0
    print(f"\nCANCELLED (IEX-dropped) cohort split — N={len(cancelled)}:")
    for c in ("would_have_filled", "gap_through", "clean_miss",
              "data_unavailable", "error"):
        if cls_counts.get(c):
            print(f"    {cls_counts[c]:>3}  {c}")
    print(f"\n  >> SIP-recoverable = would_have_filled / (wf+gap_through) "
          f"= {wf}/{wf+gt} = {recoverable:.0f}%")
    print(f"     gap_through ({gt}) are UNRECOVERABLE at the stop-limit — SIP")
    print(f"     can't fill a price that blasted past and never returned.")

    # ── 2. THE THREE LINES ──────────────────────────────────────────────────
    real_rs = [d["r"] for d in real]
    real_st = _r_stats(real_rs)
    aug_rs = real_rs + synth_r                    # chronological-ish; real first
    aug_st = _r_stats(aug_rs)

    print(f"\n{'-'*72}")
    print("R-MULTIPLE COHORT (R = pnl / risk_dollars):")
    print(f"{'-'*72}")
    print(_fmt_stats("1. REAL-only", real_st))
    print("     ^ actually-filled closed trades. REAL evidence, biased LOW")
    print("       (the IEX-dropped winners are absent).")
    print(_fmt_stats("2. SIP-augmented", aug_st))
    print(f"     ^ REAL ({real_st.get('n',0)}) + SIMULATED would_have_filled "
          f"({len(synth_r)}). << boundary: {len(synth_r)} of "
          f"{aug_st.get('n',0)} rows are SIMULATION, not realized fills.")
    if real_st.get("n") and aug_st.get("n"):
        d_exp = aug_st["expectancy"] - real_st["expectancy"]
        d_tot = aug_st["total_r"] - real_st["total_r"]
        print(f"  3. THE GAP           "
              f"dE[R]={d_exp:+.3f}  dTotR={d_tot:+.1f}R  "
              f"(+{len(synth_r)} recovered names)")
        print("     ^ THE Lever-A number: the magnitude of the IEX winner-drop.")

    # ── 3. INTERPRETATION GUARD (baked in so 6/22 reads it right) ───────────
    print(f"\n{'-'*72}")
    print("READ THIS BEFORE USING AS GATE-3 EVIDENCE:")
    print("  - SIP-augmented R is a conservative LOWER BOUND: the synthetic exit")
    print("    is entry@limit -> stop-or-day1-EOD, no trailing/partials, so it")
    print("    TRUNCATES multi-day winners. Clears the GO bar => strong. Fails")
    print("    the bar => AMBIGUOUS, NOT a NO-GO.")
    print("  - Line 2 is HALF SIMULATION. It is a less-biased ESTIMATE for the")
    print("    cutover decision, NOT a realized track record. The realized")
    print("    track record is Line 1 only.")
    print(f"  - Raw paper-IEX $ baseline for context: ${_PAPER_IEX_BASELINE_USD:+,.0f}.")

    if synth_detail:
        print(f"\nRecovered (SIMULATED) names — top by R:")
        for tk, dt, r, pnl in sorted(synth_detail, key=lambda x: -x[2])[:10]:
            print(f"    {tk:<7}{str(dt):<12}{r:+.2f}R  (${pnl:+,.0f} synthetic)")
    print()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=None, help="lookback (default: all)")
    ap.add_argument("--signal-type", default="magna53",
                    help="strategy cohort (default: magna53 — the cutover strategy)")
    args = ap.parse_args()
    asyncio.run(main(args.days, args.signal_type))
