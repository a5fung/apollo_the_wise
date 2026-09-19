"""#189/#201 load-bearing EVIDENCE assembler — fire_status × ENTRY-AWARE R (read-only).

The North Star directive (operator 2026-06-07): GAP ALONE MUST NOT = HIGH; the
real/material catalyst (the fire) must be LOAD-BEARING. The sign-off to gate/replace
the conviction floor is HARD-gated and needs EVIDENCE that *naming the fire adds R*.

The #189 materiality eval died on a SATURATED metric (fwd-return-from-gap-close,
93-97% both arms). The fix is ENTRY-AWARE R — the realized/simulated R of an actual
ORB entry — which already exists via #180 replay_would_have_filled.replay_one (+ the
#223 SIP cohort). This joins that R to the fire_status the EP scan now writes.

THE HEADLINE CONTRAST (advisor 2026-06-07) is WITHIN material HIGHs, named vs unnamed:
because fire_status is DERIVED from catalyst_quality, a raw fire-vs-no-fire split just
re-measures the grade the floor already uses. The load-bearing question is whether,
*holding grade = strong/game_changer constant*, a NAMED fire (fire_seen) out-Rs a
material-but-UNNAMED one (real_unknown / no_fire_confirmed). That maps exactly to
_compute_fire_status's refine pass. The all-HIGH baseline R is printed alongside as the
metric-saturation / spread guard (feedback_validate_metric_before_decision).

DATA POSTURE: fire_status is FORWARD-ONLY (0/297 alerts pre-2026-06-08). This script is
SCAFFOLDING built ahead of the data — it runs empty/near-empty until the Monday cohort
accrues, and is NOT sign-off-grade until N builds (Gate-3 wall: ~6 of 47 HIGHs ever
traded). It DEFERS every verdict to the operator (hard-gate: no auto-"green").

  docker exec apollo-market python scripts/fire_status_r_cohort.py
  docker exec apollo-market python scripts/fire_status_r_cohort.py 90 magna53
"""
import asyncio
import statistics
import sys

NAMED = ("fire_seen",)
UNNAMED = ("real_unknown", "no_fire_confirmed")
MATERIAL = ("strong", "game_changer")


async def _row_r(row) -> tuple:
    """Entry-aware R for one mi_live_trades row → (r_or_None, basis, classification).

    Real R for closed trades (live exit logic); else the #180 would_have_filled
    SIP synthetic R (same floor-proxy basis the #223 cohort uses). Names that did
    not fill (gap_through / clean_miss) carry no R but count in the fill denominator.
    """
    from scripts.replay_would_have_filled import replay_one
    if row["status"] == "closed" and row["risk_dollars"] and row["total_pnl"] is not None:
        return float(row["total_pnl"]) / float(row["risk_dollars"]), "real", "filled_real"
    out = await replay_one(dict(row))
    if "error" in out:
        return None, None, "error"
    cls = out["classification"]
    if cls == "would_have_filled" and out.get("pnl") is not None:
        risk = (out["limit"] - out["stop"]) * (out["shares"] or 0)
        if risk > 0:
            return out["pnl"] / risk, "synth_wf", cls
    return None, None, cls


def _stat_line(label, rs, n_total):
    """One bucket line. X/N form everywhere (N is single-digit for weeks — #110)."""
    n_r = len(rs)
    if not rs:
        return f"   {label:34} N={n_total:<3} filled=0/{n_total}  (no entry-aware R yet)"
    wins = sum(1 for r in rs if r > 0)
    mean = sum(rs) / n_r
    med = statistics.median(rs)
    return (f"   {label:34} N={n_total:<3} filled={n_r}/{n_total}  "
            f"R mean {mean:+.2f} / med {med:+.2f}  win {wins}/{n_r}")


def _compose(rows):
    """catalyst_quality + gap composition of a bucket — proves the split isn't just grade."""
    if not rows:
        return "—"
    q = {}
    for r in rows:
        q[r["catalyst_quality"] or "—"] = q.get(r["catalyst_quality"] or "—", 0) + 1
    gaps = [float(r["gap_pct"]) for r in rows if r["gap_pct"] is not None]
    gstr = f"gap med {statistics.median(gaps):.1f}%" if gaps else "gap —"
    return ", ".join(f"{k}:{v}" for k, v in sorted(q.items())) + f"  ·  {gstr}"


async def main(days, signal_type):
    from agents.market_intelligence.db import get_pool
    where_days = f"AND lt.alert_date >= CURRENT_DATE - INTERVAL '{int(days)} days'" if days else ""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(f"""
            SELECT lt.ticker, lt.alert_date, lt.status, lt.total_pnl, lt.risk_dollars,
                   lt.orb_high, lt.orb_low, lt.entry_price, lt.stop_price, lt.entry_shares,
                   a.fire_status, a.fire_axes, a.catalyst_quality, a.gap_pct, a.score_tier
            FROM mi_live_trades lt
            LEFT JOIN mi_ep_alerts a
              ON a.ticker = lt.ticker AND a.alert_date = lt.alert_date
            WHERE lt.account_mode = 'paper'
              AND lt.signal_type = $1
              AND lt.pnl_attribution IS NULL
              {where_days}
            ORDER BY lt.alert_date ASC
        """, signal_type)

    # entry-aware R per row, attached to the alert's fire_status/grade
    enriched = []
    for row in rows:
        r, basis, cls = await _row_r(row)
        enriched.append({**dict(row), "r": r, "basis": basis, "cls": cls})

    span = f"last {days}d" if days else "all-time"
    print(f"\n╔══ fire_status × ENTRY-AWARE R — {signal_type}, {span} ══╗")
    print("   READ-ONLY · entry-aware R (real exit | #180 SIP would_have_filled) · "
          "verdict is the operator's.")

    fs_known = [e for e in enriched if e["fire_status"] in NAMED + UNNAMED]
    fs_null = [e for e in enriched if e["fire_status"] not in NAMED + UNNAMED]
    if not fs_known:
        print(f"\n   ⏳ NO fire_status-classified rows in cohort yet "
              f"({len(fs_null)} rows have NULL fire_status — forward-only, accrues from "
              f"Mon 6/8). This is scaffolding; re-run as the cohort builds.")

    # ── HEADLINE: within material (strong/gc) HIGHs — NAMED vs UNNAMED fire ──
    print("\n── HEADLINE (advisor): WITHIN strong/game_changer HIGHs — named vs unnamed fire")
    print("   (the load-bearing contrast — holds grade constant, so it isn't re-measuring grade)")
    mat_high = [e for e in fs_known
                if e["catalyst_quality"] in MATERIAL and e["score_tier"] == "HIGH"]
    named = [e for e in mat_high if e["fire_status"] in NAMED]
    unnamed = [e for e in mat_high if e["fire_status"] in UNNAMED]
    print(_stat_line("named fire (fire_seen)", [e["r"] for e in named if e["r"] is not None], len(named)))
    print(f"        composition: {_compose(named)}")
    print(_stat_line("material but UNNAMED", [e["r"] for e in unnamed if e["r"] is not None], len(unnamed)))
    print(f"        composition: {_compose(unnamed)}")

    # ── BASELINE: all HIGH (spread / saturation guard) ──
    print("\n── BASELINE (saturation guard): all HIGH alerts that attempted entry")
    all_high = [e for e in enriched if e["score_tier"] == "HIGH"]
    print(_stat_line("all-HIGH baseline", [e["r"] for e in all_high if e["r"] is not None], len(all_high)))
    print("   ► If the two headline buckets sit on this baseline with no spread, the metric")
    print("     isn't discriminating on this cohort YET — not a 'no signal' verdict.")

    # ── N discipline ──
    small = max(len(named), len(unnamed)) < 5
    print("\n── status")
    if small:
        print("   ⚠️  N is single-digit — NOT sign-off-grade. X/N shown, not percentages. A 2-vs-1")
        print("      delta is noise. Sign-off is HARD-gated (CHANGE_PROCESS + N≥10-30 + operator).")
    print(f"   complementary view (NOT in this R cohort): cap-blocked HIGHs live in "
          f"mi_ep_missed_outcomes (#199) with FORWARD (not entry-aware) returns.")
    print(f"\n   cohort: {len(enriched)} entry-attempting {signal_type} rows · "
          f"fire_status-classified {len(fs_known)} · NULL {len(fs_null)}\n")


if __name__ == "__main__":
    days = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else None
    sig = sys.argv[2] if len(sys.argv) > 2 else "magna53"
    asyncio.run(main(days, sig))
