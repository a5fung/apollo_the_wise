#!/usr/bin/env python3
"""#327 — ANTICIPATE entry arm (the 3rd-mode rerun, operator 2026-06-18).

The original #327 replay tested 9M Day-2 ORB vs only the CONFIRM/FIRST5 entry (buy the
breakout). Operator: the consolidation play has THREE entry modes and the one we're building is
ANTICIPATE — enter IN the coil, BEFORE the break. This arm reruns the comparison for that mode.

Method (advisor-hardened 2026-06-18): PORT the advisor-hardened _270 anticipation machinery
(find_coiled_days + simulate_reenter + realized_net + the maturity sweep) WHOLESALE, only
RE-ANCHORED from the Family-B gap_day_low to the #327 9M-day anchor. Minimal new code = the
anchor swap (gap_day_low → the 9M breakout-day low; armed_idx → alert_date; trig_idx → the
consolidation_scan breakout, or None). Two traps the port avoids by construction:
  • SURVIVORSHIP: the universe = EVERY 9M name that COILS, breakout or NOT — the false set
    (coiled → shaken → never confirmed) realizes its −1R shakes and is the whole reason
    anticipation lands at ≈0R. (simulate_reenter handles trig_idx=None → open/drift.)
  • MATURITY: the 6/14 verdict was entirely maturity-dependent → report the min_base 1→4 SWEEP,
    never a single number.
Yardsticks (ADR-0013 / 6-14): anticipation is judged on PRICE-CAPTURE + COMPLEMENTARITY +
realized-with-reentry — NOT standalone R alone (grading it only on R buries what it's for).
This is a small-N, in-sample, DIRECTIONAL read that CORRECTS THE RECORD + gives per-mode numbers
on the 9M cohort — not a ship verdict. Read-only, gate-safe, runs off the pulled #327 TSVs.
"""
import importlib.util
from pathlib import Path

HERE = Path(__file__).resolve().parent


def _load(name):
    spec = importlib.util.spec_from_file_location(name.replace(".py", ""), HERE / name)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


r327 = _load("_327_replay.py")            # cohort/daily/minute loaders + consolidation_scan + de
anticip = _load("_270_anticipation_replay.py")  # find_coiled_days/simulate_reenter/realized_net/harvest
de = r327.de
median, mean = anticip.median, anticip.mean


# ── the anchor swap: build the _270-shaped ctx from the #327 9M cohort ────────
def ctx_for(c, bars):
    """{gap_day_low, armed_idx, trig_idx} from a 9M cohort row. The 9M day (alert_date) is the
    anchor; its low is the reclaim pivot (analogous to the EP gap_day_low); the consolidation_scan
    daily-close breakout is the trigger (None if the name never confirmed = a survivorship name)."""
    ai = r327.idx_of_date(bars, c["alert_date"])
    if ai is None:
        return None
    bo, _scan = r327.consolidation_scan(bars, ai)
    return {"gap_day_low": c["low"], "armed_idx": ai,
            "trig_idx": bo["breakout_idx"] if bo else None}


def build_names(cohort, daily, min_base):
    """Per-name lifecycle → coiled days (find_coiled_days, the maturity-gated anticipation coil)
    → stop-and-reenter. armed = every name that reaches an armed window (min_base-independent);
    a name with ≥1 coiled day is in the anticipate universe whether or not it ever breaks out."""
    armed, names = 0, []
    for c in cohort:
        bars = daily.get(c["ticker"])
        if not bars:
            continue
        ctx = ctx_for(c, bars)
        if ctx is None:
            continue
        armed += 1
        coiled = anticip.find_coiled_days(bars, ctx, min_base)
        # settleable guard (the anticipate analog of arm2_fwd_ok): a coiled entry needs ≥5 forward
        # daily bars to harvest — drop in-flight coils in the last 5 bars (recent 9M names) so a
        # terminal leg never gets an empty path. Triggered names' coils sit well before trig+10d.
        coiled = [ci for ci in coiled if ci <= len(bars) - 6]
        if not coiled:
            continue
        triggered = ctx["trig_idx"] is not None
        end_idx = (ctx["trig_idx"] + anticip.FWD_N) if triggered else min(coiled[-1] + 10, len(bars) - 1)
        end_idx = min(end_idx, len(bars) - 1)
        attempts = anticip.simulate_reenter(bars, coiled, ctx["trig_idx"], end_idx)
        win = next((a for a in attempts if a["outcome"] == "win"), None)
        names.append({"t": c["ticker"], "triggered": triggered, "attempts": attempts, "win": win,
                      "end_idx": end_idx, "ctx": ctx, "n_coiled": len(coiled)})
    return armed, names


def first5_price(ticker, date, base_or_pivot, minute):
    """The CONFIRM/FIRST5 entry price on the breakout day (for the price-capture comparison) —
    reuse the #327 detector on the pulled RTH minute bars. None if no minute / no break."""
    raw = minute.get((ticker, date))
    if not raw:
        return None
    rth = de.polygon_to_rth_minutes(raw, date)
    res = de.detect_first5_break(rth, gdl=base_or_pivot or 0.0)
    return res[0] if res else None


def main():
    cohort = r327.load_cohort()
    daily = r327.load_daily()
    minute = r327.load_minute()

    armed, names = build_names(cohort, daily, min_base=1)
    trig = [x for x in names if x["triggered"]]
    print("#327 — ANTICIPATE entry arm (9M cohort; ported _270 machinery, re-anchored)\n")
    print("DIRECTIONAL, small-N, in-sample — corrects the record (the prior #327 tested only "
          "Confirm/FIRST5), not a ship verdict.\n")
    print(f"COMPLEMENTARITY: {armed} 9M names reach an armed window; a coiled day formed on "
          f"{len(names)} ({len(names)/max(armed,1)*100:.0f}%) at min_base=1 — "
          f"{len(trig)} later confirmed a breakout, {len(names)-len(trig)} never did "
          f"(the false-anticipation COST set, kept).")
    if armed:
        print(f"   = anticipation only has an entry on the ~{len(names)/max(armed,1)*100:.0f}% that coil; "
              f"the rest are fast runners Confirm/FIRST5 must cover (the modes are complementary).")

    # ── PRICE-CAPTURE (claim #1): winning anticipate entry vs the FIRST5 breakout price ──
    pc = []
    for x in trig:
        if not x["win"]:
            continue
        bars = daily[x["t"]]
        tdate = bars[x["ctx"]["trig_idx"]]["date"]
        f5 = first5_price(x["t"], tdate, x["ctx"]["gap_day_low"], minute)
        if f5:
            hi = max(b["h"] for b in bars[x["win"]["ai"]: x["end_idx"] + 1])
            pc.append({"a": x["win"]["entry"], "f5": f5, "hi": hi})
    if pc:
        head = [(p["f5"] - p["a"]) / p["a"] for p in pc]
        share = [(p["f5"] - p["a"]) / (p["hi"] - p["a"]) for p in pc if p["hi"] > p["a"]]
        print(f"\nPRICE-CAPTURE (winning anticipate close vs FIRST5 price; triggered, N={len(pc)}):")
        print(f"   anticipate enters {median(head)*100:.0f}% BELOW the FIRST5 price (median) = "
              f"{median(share)*100:.0f}% of the run to the window high captured earlier.")

    # ── REALIZED HARVEST (the win leg through the exit math). The PRIMARY row uses the SAME rule
    #    the Confirm/FIRST5 arm settles on — anticipation.SETTLE_RULE = +1R/+3R halves WITH a 5-day
    #    time stop — so it's truly apples-to-apples (the _270_harvest 'bank_1R_3R' has NO time stop,
    #    letting the runner half ride to the path end and give everything back → too negative). The
    #    other _270 rules follow for the speed spectrum. ──
    settle_match = dict(partials=[(1.0, 0.5), (3.0, 0.5)], time_stop_days=5)  # == Confirm SETTLE_RULE
    harvest_rules = [("bank_1R_3R+5d (==Confirm)", settle_match)] + [
        (rn, anticip.harvest.RULES[rn]) for rn in anticip._HARVEST_RULES]
    print(f"\nREALIZED HARVEST — net R/name, full universe ({len(names)} coilers incl. the cost set):")
    print(f"   {'rule':<26}{'med R':<9}{'mean R':<9}{'win%':<7}{'total':<9}{'top%':<7}{'ex-top mean'}")
    for label, rule in harvest_rules:
        rz = [anticip.realized_net(x, daily[x["t"]], rule) for x in names]
        rz = [r for r in rz if r is not None]
        if not rz:
            continue
        tot = sum(rz)
        top = max(rz)
        ex = [r for r in rz if r != top]
        wr = sum(1 for r in rz if r > 0) / len(rz) * 100
        print(f"   {label:<26}{median(rz):<+9.1f}{mean(rz):<+9.1f}{wr:<7.0f}{tot:<+9.1f}"
              f"{(top/tot*100 if tot else 0):<7.0f}{(mean(ex) if ex else float('nan')):+.1f}")
    print("   (top row == the Confirm arm's SETTLE_RULE → directly comparable to FIRST5's realized.")
    print("    caveat: this arm harvests via _270_harvest.simulate; the Confirm arm via "
          "anticipation.simulate — same extracted logic, but a residual impl drift would bias the cross-arm gap.)")

    # ── MATURITY SWEEP (the 6/14 verdict was maturity-dependent — never read one row) ──
    print("\nMATURITY SWEEP (require a ≥min_base-day developed base before the coiled entry):")
    print(f"   {'min_base':<9}{'coiled':<8}{'caught':<8}{'entry d-before':<15}{'attempts/nm':<13}"
          f"{'trig meanR':<12}{'full meanR':<12}{'top%':<6}{'ex-top meanR'}")
    for mb in (1, 2, 3, 4):
        _a, nm = build_names(cohort, daily, mb)
        s = anticip.summarize(nm)
        print(f"   {mb:<9}{s['fired']:<8}{s['catch']:<8}{s['db']:<15.0f}{s['attempts']:<13.1f}"
              f"{s['trig_mean']:<+12.1f}{s['full_mean']:<+12.1f}{s['top_share']:<6.0f}{s['ex_mean']:+.1f}")
    print("   REAL SIGNAL = winner-retention (caught holds while coiled falls), NOT the +R magnitudes")
    print("   (those rise mechanically as the gate drops losers first; in-sample/leveraged).")

    # ── per-name audit (eyeball for artifacts) ──
    print("\nPER-NAME (min_base=1): ticker  trig?  attempts[outcome:R ...]  net")
    for x in sorted(names, key=lambda y: -sum(a["R"] for a in y["attempts"])):
        seq = " ".join(f"{a['outcome'][0]}:{a['R']:+.1f}" for a in x["attempts"])
        net = sum(a["R"] for a in x["attempts"])
        print(f"   {x['t']:<6} {'TRIG' if x['triggered'] else 'none':<5} [{seq}]  net {net:+.1f}R")


if __name__ == "__main__":
    main()
