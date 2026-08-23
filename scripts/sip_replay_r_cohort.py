"""Lever A — SIP-augmented R cohort for the Gate-3 live-cutover decision.

⚠ RETIRED FROM THE QUARTERLY SWEEP 2026-08-11 (operator-ruled). Still runnable by
hand; kept because it is the evidence behind the cutover decision. Both premises
expired: MAGNA53 went live 2026-06-22 and prod now runs ALPACA_DATA_FEED=sip, so
the IEX-vs-SIP question is closed — AND both cohorts below pin account_mode='paper',
so an auto-re-run was re-measuring a book frozen at the cutover. Do NOT re-register
it without repointing those filters first; see quarterly_review.py for the ruling.

READ-ONLY. No DB writes, no trade-state mutation. Safe to run via
`docker exec apollo-market python scripts/sip_replay_r_cohort.py [--days N]`.
Also auto-re-runs monthly via the backward-check sweep (quarterly_review.py;
registered #223) so the IEX-selection finding is re-measured as the cohort
grows — per feedback_methodology_insights_need_periodic_revalidation.

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
from datetime import datetime as _dt, time as _time
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agents.market_intelligence.collector import get_minute_bars
from agents.market_intelligence.db import get_pool
from scripts.replay_would_have_filled import replay_one  # #180 per-row SIP replay

_ET = ZoneInfo("America/New_York")
_ORB_OPEN = _time(9, 31)
_ORB_CUTOFF = _time(10, 0)

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


from agents.market_intelligence.kill_scale_bands import _risk_placed


async def _real_cohort(conn, days: int | None, signal_type: str) -> list[dict]:
    """Actually-filled, closed trades. Carries BOTH the real realized R
    (total_pnl / the risk actually PLACED — live exit logic: partials/breakeven/trailing)
    AND the entry params, so the SAME-EXIT cross-check can re-score these
    entries under the identical replay_one floor proxy used for the cancelled
    cohort (isolates IEX selection from exit-model — advisor 2026-06-06).
    pnl_attribution IS NULL = methodology-evaluation filter (db.py)."""
    where_days = f"AND alert_date >= CURRENT_DATE - INTERVAL '{int(days)} days'" if days else ""
    rows = await conn.fetch(f"""
        SELECT ticker, alert_date, total_pnl, risk_dollars, risk_dollars_actual, hold_days,
               orb_high, orb_low, entry_price, stop_price, hard_stop, entry_shares
        FROM mi_live_trades
        WHERE status = 'closed'
          AND account_mode = 'paper'
          AND signal_type = $1
          AND pnl_attribution IS NULL
          {where_days}
        ORDER BY alert_date ASC
    """, signal_type)
    out = []
    for r in rows:
        d = dict(r)
        # ONE definition of R everywhere (#586, 2026-08-23). `risk_dollars` is the
        # PRE-cap intended budget and does NOT match the #268b calibration, which divides
        # by the risk actually placed. `kill_scale_bands._risk_placed` is that single
        # derivation — reused, never re-expressed here (P15: no second definition).
        risk = _risk_placed(d)
        if not risk:
            continue
        d["r"] = float(r["total_pnl"] or 0) / risk  # real R, on risk actually placed
        d["date"] = r["alert_date"]
        out.append(d)
    return out


async def _synthetic_rs(rows: list[dict]) -> tuple[Counter, list[float], list[tuple]]:
    """Run replay_one over a cohort's entries → (classification counts,
    synthetic-R list for would_have_filled, detail tuples). SAME floor-proxy
    exit basis for whatever cohort is passed — this is what makes filled vs
    cancelled comparable."""
    cls: Counter = Counter()
    rs: list[float] = []
    detail: list[tuple] = []
    for row in rows:
        out = await replay_one(row)
        if "error" in out:
            cls["error"] += 1
            continue
        cls[out["classification"]] += 1
        if out["classification"] == "would_have_filled" and out.get("pnl") is not None:
            risk = (out["limit"] - out["stop"]) * (out["shares"] or 0)
            if risk > 0:
                r = out["pnl"] / risk
                rs.append(r)
                detail.append((out["ticker"], out["date"], r, out["pnl"]))
    return cls, rs, detail


def _trim_cross_k(rs: list[float]) -> int | None:
    """The smallest k such that dropping the top-k winners makes E[R] <= 0 —
    a one-number concentration measure for the TL;DR (the monthly-sweep digest
    only captures the first ~25 lines). High k = robust; low k = tail-carried."""
    if not rs:
        return None
    s = sorted(rs, reverse=True)
    for k in range(1, len(s)):
        if sum(s[k:]) / len(s[k:]) <= 0:
            return k
    return None


def _trim_curve(rs: list[float], k_max: int = 6) -> list[str]:
    """STANDALONE >0-bar robustness (advisor #224, 2026-06-07): drop the top-k
    winners from the synth-CANCELLED cohort and watch E[R] decay. The headline
    is NOT the selection delta (inflated by the no-partial proxy's harshness on
    synth-FILLED) — it is whether synth-CANCELLED clears 0 ON ITS OWN, and how
    concentrated that edge is. A cohort that crosses 0 after dropping only ~3
    names is 'real but concentrated' → supports START-SMALL, not full-size."""
    if not rs:
        return ["  (no would_have_filled rows to trim)"]
    n = len(rs)
    s = sorted(rs, reverse=True)
    out = [f"  full: N={n}  E[R]={sum(rs)/n:+.3f}  totR={sum(rs):+.2f}  "
           f"(win {sum(1 for r in rs if r > 0)}/{n})"]
    crossed = False
    for k in range(1, min(k_max, n - 1) + 1):
        trimmed = s[k:]
        er = sum(trimmed) / len(trimmed)
        marker = ""
        if er <= 0 and not crossed:
            marker = "   <-- E[R] crosses 0 here"
            crossed = True
        out.append(f"  drop top {k}: N={len(trimmed):<3} E[R]={er:+.3f}  "
                   f"totR={sum(trimmed):+.2f}{marker}")
    return out


async def _winner_realism(winner_rows: list[dict]) -> list[str]:
    """FILL-REALISM robustness (advisor #224 #4, 2026-06-07): the synth-CANCELLED
    edge rides on a handful of winners — interrogate whether each actually traded
    CONVINCINGLY THROUGH the limit (multiple fillable bars OR real penetration
    below limit) vs grazed it for a single print (a marginal fill the live SIP
    book might miss). Re-fetches the winners' bars only (~handful of fetches)."""
    out: list[str] = []
    conv = 0
    for row in winner_rows:
        ticker, d = row["ticker"], row["alert_date"]
        trigger = float(row["orb_high"] or row["entry_price"] or 0)
        limit = float(row["entry_price"] or row["orb_high"] or 0)
        bars = await get_minute_bars(ticker, d.isoformat(), d.isoformat())
        if not bars:
            out.append(f"    {ticker:<6} {d}  (no bars)")
            continue
        parsed = sorted((_dt.fromtimestamp(b["t"] / 1000, tz=_ET),
                         float(b["h"]), float(b["l"])) for b in bars)
        canon = [(t, h, l) for t, h, l in parsed if _ORB_OPEN <= t.time() <= _ORB_CUTOFF]
        above = [(t, h, l) for t, h, l in canon if h >= trigger]
        if not above:
            continue
        after = [(t, h, l) for t, h, l in canon if t >= above[0][0]]
        fillable = [(t, h, l) for t, h, l in after if l <= limit]
        if not fillable:
            continue
        pen_pct = (limit - min(l for _, _, l in fillable)) / limit * 100 if limit else 0.0
        convincing = len(fillable) >= 2 or pen_pct >= 0.10
        conv += int(convincing)
        out.append(f"    {ticker:<6} {d}  fillbars={len(fillable)}  "
                   f"pen={pen_pct:.2f}%  "
                   f"{'convincing' if convincing else 'GRAZE (1 bar, shallow)'}")
    out.insert(0, f"  {conv}/{len(winner_rows)} winners are convincing fills "
                  f"(>=2 fillable bars OR >=0.10% penetration below limit):")
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

    # ── COMPUTE everything up-front (one bar-fetch pass per cohort) so the
    # TL;DR can lead — the monthly sweep summarises the first ~25 lines. ──────
    # SIP recovers ONLY would_have_filled; gap_through is unrecoverable.
    cls_counts, synth_r, synth_detail = await _synthetic_rs(cancelled)
    # SAME-EXIT cross-check: re-score the FILLED entries under the identical
    # floor proxy so filled-vs-cancelled compare on ONE exit basis.
    f_cls, filled_synth_r, _ = await _synthetic_rs(real)
    real_st = _r_stats([d["r"] for d in real])           # real exits
    aug_st = _r_stats([d["r"] for d in real] + synth_r)  # real + synth (confounded)
    sf_st = _r_stats(filled_synth_r)                     # filled, synth exit
    sc_st = _r_stats(synth_r)                            # cancelled, synth exit
    wf = cls_counts.get("would_have_filled", 0)
    gt = cls_counts.get("gap_through", 0)
    # SELECTION delta (cancelled − filled, same exit basis) — the clean signal.
    # Computed once; the TL;DR and the cross-check section both read it.
    have_xcheck = bool(sf_st.get("n") and sc_st.get("n"))
    sel = (sc_st["expectancy"] - sf_st["expectancy"]) if have_xcheck else None
    # STANDALONE robustness (advisor #224) — computed up-front so the one-line
    # summary lands in the TL;DR (the monthly-sweep digest only keeps the first
    # ~25 lines; section 5 at the bottom would be dropped). Winner fill-realism
    # is the only extra bar-fetch pass — winners only (a handful).
    trim_cross = _trim_cross_k(synth_r)
    winner_keys = {(tk, dt) for tk, dt, r, _ in synth_detail if r > 0}
    winner_rows = [c for c in cancelled
                   if (c["ticker"], c["alert_date"]) in winner_keys]
    realism_lines = await _winner_realism(winner_rows) if winner_rows else []
    realism_hdr = realism_lines[0].strip() if realism_lines else ""

    print(f"\n{'='*72}")
    print(f"Lever A — SIP-augmented R cohort   [{signal_type} · paper · {win}]")
    print(f"{'='*72}")

    # ── TL;DR (leads so the monthly-sweep summary captures the verdict) ──────
    if have_xcheck:
        verdict = ("GO-supportive (paper loss = IEX feed artifact)"
                   if sel > 0.5 else
                   "AMBIGUOUS — selection signal weak/absent, do NOT file +Gate-3")
        print(f"\nTL;DR (Gate-3):  SELECTION delta = {sel:+.2f}R  "
              f"[synth-CANCELLED {sc_st['expectancy']:+.2f} vs "
              f"synth-FILLED {sf_st['expectancy']:+.2f}, same exit basis]")
        print(f"   gap_through={gt} (IEX dropped REACHABLE winners) · "
              f"real cohort {real_st.get('n',0)}@{real_st.get('expectancy',0):+.2f}R")
        # Standalone >0-bar robustness (advisor #224) — the SIZING-relevant read.
        if sc_st.get("n"):
            cross_txt = (f"crosses 0 at drop-{trim_cross} of top winners"
                         if trim_cross else "stays >0 through the trim")
            print(f"   STANDALONE: synth-CANCELLED {sc_st['expectancy']:+.2f}R "
                  f"(win {sc_st['win_rate']*100:.0f}%) {cross_txt}"
                  + (f"; {realism_hdr.split(' (')[0]}" if realism_hdr else ""))
            print(f"      => edge is real but CONCENTRATED -> START-SMALL, not full-size"
                  f" (operator owns GO/size).")
        print(f"   VERDICT: {verdict}")
        print(f"   Full reasoning + caveats: docs/analysis/sip_replay_gate3_2026-06-06.md")

    # ── 1. COHORT SPLIT — the fail-fast headline ────────────────────────────
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
    # (real_st / aug_st computed up-top)
    print(f"\n{'-'*72}")
    print("R-MULTIPLE COHORT (R = pnl / risk actually placed — #586):")
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
        print("     !! CONFOUNDED: this gap mixes IEX-selection with EXIT-MODEL.")
        print("        Real R uses live exits (partials/BE/trail, caps wins ~+1R);")
        print("        synthetic R holds to EOD-day1 (avgW ~+3R). Not pure selection.")
        print("        -> See the SAME-EXIT cross-check below for the clean signal.")

    # ── 3. SAME-EXIT CROSS-CHECK (isolates IEX selection from exit model) ────
    # Both cohorts re-scored under the SAME replay_one floor proxy. If
    # synthetic-filled stays clearly negative while synthetic-cancelled is
    # positive -> the difference is SELECTION, not exit methodology.
    # (sf_st / sc_st computed up-top)
    print(f"\n{'-'*72}")
    print("SAME-EXIT CROSS-CHECK (both on floor-proxy exit — the clean selection test):")
    print(f"{'-'*72}")
    print(_fmt_stats("  synth-FILLED", sf_st))
    print(f"     ^ the entries IEX DID fill, re-scored on the synthetic basis "
          f"(wf={f_cls.get('would_have_filled',0)}/"
          f"{sum(f_cls.values())}).")
    print(_fmt_stats("  synth-CANCELLED", sc_st))
    print("     ^ the entries IEX DROPPED, same synthetic basis.")
    if have_xcheck:
        print(f"  SELECTION delta E[R] = {sel:+.3f}  "
              f"(cancelled − filled, SAME exit basis)")
        print("     >> POSITIVE & large => IEX adverse-selection is REAL on an")
        print("        apples-to-apples basis (the headline finding survives).")
        print("     >> Near zero / negative => the +0.29 flip was EXIT-MODEL, not")
        print("        selection — do NOT file a positive Gate-3 number.")

    # ── 4. INTERPRETATION GUARD (baked in so 6/22 reads it right) ───────────
    print(f"\n{'-'*72}")
    print("READ THIS BEFORE USING AS GATE-3 EVIDENCE:")
    print("  - The SAME-EXIT cross-check (section 3) is the load-bearing number,")
    print("    NOT the SIP-augmented +E[R] (section 2 is exit-model-confounded).")
    print("  - Live trades exit on the REAL logic (caps wins ~+1R per the filled")
    print("    cohort), NOT hold-to-EOD. So synthetic +avgW likely OVERSTATES live")
    print("    R on recovered names — section 2 is an UPPER-ish bound, not a floor.")
    print("  - What IS solid regardless: gap_through=0 => IEX dropped REACHABLE")
    print("    winners; the filled cohort is adversely selected; the paper figure")
    print("    is pessimistically biased. That qualitative finding stands.")
    print(f"  - Raw paper-IEX $ baseline for context: ${_PAPER_IEX_BASELINE_USD:+,.0f}.")

    if synth_detail:
        print(f"\nRecovered (SIMULATED) names — top by R:")
        for tk, dt, r, pnl in sorted(synth_detail, key=lambda x: -x[2])[:10]:
            print(f"    {tk:<7}{str(dt):<12}{r:+.2f}R  (${pnl:+,.0f} synthetic)")

    # ── 5. STANDALONE ROBUSTNESS (advisor #224, 2026-06-07) ─────────────────
    # The selection delta (section 3) is the WEAKER 'selection exists' claim — it
    # is inflated by the no-partial proxy's harshness on synth-FILLED (every
    # non-winner lands at exactly -1.00R). The LOAD-BEARING question for sizing is
    # whether synth-CANCELLED clears 0 ON ITS OWN, and how concentrated that is.
    if synth_r:
        print(f"\n{'-'*72}")
        print("STANDALONE synth-CANCELLED robustness (the >0 bar — sizing-relevant):")
        print(f"{'-'*72}")
        print("  TRIM CURVE (drop the top-k winners; how concentrated is +E[R]?):")
        for line in _trim_curve(synth_r):
            print(line)
        # Winner fill-realism (precomputed up-front for the TL;DR — reuse, no refetch).
        if realism_lines:
            print("\n  FILL REALISM (did the winners trade THROUGH the limit, not graze?):")
            for line in realism_lines:
                print(line)
        print("\n  READ: 'selection exists' (section 3 delta) is robust; whether")
        print("  synth-CANCELLED is positive STANDALONE is concentrated in the top")
        print("  few names — supports START-SMALL sizing, not full-size. Operator")
        print("  owns the GO/size call; this is evidence, not a verdict.")
    print()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=None, help="lookback (default: all)")
    ap.add_argument("--signal-type", default="magna53",
                    help="strategy cohort (default: magna53 — the cutover strategy)")
    args = ap.parse_args()
    asyncio.run(main(args.days, args.signal_type))
