"""Let-winners-run, FAITHFULLY — and the no-stop arm's risk, priced. (2026-08-16)

PART 1 — the +36.8R "no intraday stop" number came from an ad-hoc rerun whose code was
never saved (commits d39c9bc / 00e2792 changed only the doc). The nearest surviving arm
(_reentry_vs_nostop.py "NO INTRADAY STOP" = _ext_live_exit_replay.simulate with
be_close_basis+hard_close_basis) has three infidelities vs the live ladder:
  (i)   day-0 CLOSE is never tested against the stop when hard_close_basis=True —
        a name that closes day 0 below the ORB low rides free until day 1+;
  (ii)  the SMA10/20 trail excludes TODAY's close — exit_logic.apply_daily_exit_step
        appends today's close to running_closes BEFORE computing the trail (line 249/285);
  (iii) an intraday broker stop that gaps through fills ~at the OPEN, not at the stop px.

This probe rebuilds the arms faithfully from broker/exit_logic.py +
order_manager.scan_profit_triggers (PROFIT_TRIGGER_R=2.0, live 2026-08-01):
  * +2R: 1/3 out at entry+2R on first TOUCH (minute-high day 0, daily-high after),
    then the broker stop moves to BREAKEVEN (intraday touch) — execute_partial_exit
    moves the stop first, same day.
  * daily EOD ladder: effective_stop = MAX(hard_stop, max(SMA10,SMA20) incl today's
    close over prior+running closes, entry-if-breakeven); giveback floor OFF;
    trail exits on daily CLOSE below (live_tracker passes skip_partial_decision=True —
    the Day-3-5 ladder partial is DEAD live; #508 +2R is the only partial).
  * ladder starts day 1 (apply_daily_exit_step skips today <= alert_date).
ARMS:
  LIVE   — hard stop + breakeven intraday touch at the broker; trail close-basis.
  LWR-C  — the WHOLE ladder closing-basis ("no intraday stop"): hard stop and
           breakeven fire only on a daily CLOSE below (incl day 0's close); the +2R
           partial still fills intraday (a resting limit fills at the price).
Run at 20 and 60 trading days on the same matched cohorts as the doc's table.

PART 2 — the risk of holding to the close, on the same names: max intraday adverse
excursion in R while held (minute-resolution day 0; DAILY LOWS days 1+ = a
CONSERVATIVE FLOOR that UNDERSTATES intraday excursion), sub -1/-2/-3/-5R dips that
the close-basis rule held through, and overnight gap-through-the-stop events.

READ-ONLY. Reconstructed, not lived. Exit/stop discipline = THE LINE: measured only.
"""
from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import _468_moderate_realized_r as M              # noqa: E402
import _ext_live_exit_replay as X                 # noqa: E402

M.COHORT, M.DAILY, M.MINUTE = HERE / "_468_cohort.tsv", HERE / "_468_daily_full.tsv", HERE / "_468_minute.tsv"
OUT = HERE.parent.parent / "docs" / "analysis" / "let_it_run_and_risk_2026-08-16.txt"

PROFIT_R = 2.0            # constants.PROFIT_TRIGGER_R (live 2026-08-01)
FRAC = 1.0 / 3.0


def sma(cl, n):
    return sum(cl[-n:]) / n if len(cl) >= n else None


def simulate_faithful(entry, hard_stop, day0_after_fill, fwd, prior_closes, horizon,
                      close_basis=False, want_path=False, day0_close_check=True):
    """Faithful live ladder (close_basis=False) or whole-ladder-closing-basis variant.
    Returns dict(r=..., exit_day=trading-day index 0..horizon, reason=...,
                 path=[(day_idx, low, close, open, stop_level_prevailing)] if want_path,
                 partial_day=..).
    Conservative convention at daily resolution: on a day where both the stop level and
    the +2R target were touched, the STOP is assumed first (order unknowable)."""
    risk = entry - hard_stop
    if risk <= 0:
        return None
    target = entry + PROFIT_R * risk
    held, banked, partial = 1.0, 0.0, False
    br = hard_stop                      # the broker stop level (hard stop -> breakeven)
    path = []

    def fin(r, day, reason, pd):
        return {"r": r, "exit_day": day, "reason": reason, "path": path, "partial_day": pd}

    partial_day = None
    # ---- day 0, minute by minute from the fill ----
    d0_low = min((b["l"] for b in day0_after_fill), default=None)
    for b in day0_after_fill:
        if not close_basis and b["l"] <= br:
            if want_path:
                path.append((0, b["l"], None, None, br))
            return fin(banked + held * (br - entry) / risk, 0, "hard_stop_touch", partial_day)
        if not partial and b["h"] >= target:
            banked += FRAC * PROFIT_R
            held -= FRAC
            partial, partial_day = True, 0
            br = max(br, entry)         # breakeven at the broker, same instant
    d0_close = day0_after_fill[-1]["c"] if day0_after_fill else entry
    if want_path:
        path.append((0, d0_low, d0_close, None, br))
    closes = list(prior_closes) + [d0_close]
    if close_basis and day0_close_check and d0_close < br:
        # the crude arm never tested day-0's close
        return fin(banked + held * (d0_close - entry) / risk, 0, "close_below_stop", partial_day)

    # ---- days 1..horizon, daily; EOD ladder starts day 1 (live parity) ----
    last_close = d0_close
    for di, d in enumerate(fwd[:horizon], start=1):
        if not close_basis and d["l"] <= br:
            px = d["o"] if d["o"] < br else br      # gap-through fills ~at the open
            if want_path:
                path.append((di, d["l"], d["c"], d["o"], br))
            return fin(banked + held * (px - entry) / risk, di, "hard_stop_touch", partial_day)
        if not partial and d["h"] >= target:        # resting limit fills at the price
            banked += FRAC * PROFIT_R
            held -= FRAC
            partial, partial_day = True, di
            br = max(br, entry)
        closes.append(d["c"])                        # trail INCLUDES today's close
        line = max([x for x in (sma(closes, 10), sma(closes, 20)) if x is not None],
                   default=None)
        eff = max(br, line) if line is not None else br
        if want_path:
            path.append((di, d["l"], d["c"], d["o"], br))
        if d["c"] < eff:
            return fin(banked + held * (d["c"] - entry) / risk, di,
                       "close_below_ladder", partial_day)
        last_close = d["c"]
    n_held = min(horizon, len(fwd))
    return fin(banked + held * (last_close - entry) / risk, n_held, "horizon_mark",
               partial_day)


def build_cohort():
    """HIGH alerts -> eligibility -> reconstruct fill (live geometry). Returns list of
    dicts with entry/stop/day0 minutes-after-fill/fwd daily/prior closes."""
    rows = [r for r in M.load_cohort() if r["tier"] == "HIGH"]
    daily, minute = M.load_daily(), M.load_minute()
    out, sk = [], defaultdict(int)
    for r in rows:
        why, sub = M.eligibility(r)
        if why != "ok":
            sk[why] += 1
            continue
        db = daily.get(r["ticker"], [])
        i = M.idx_of_date(db, r["alert_date"])
        raw = minute.get((r["ticker"], r["alert_date"]), [])
        if i is None or not raw:
            sk["no_bars"] += 1
            continue
        rth = M.de.polygon_to_rth_minutes(raw, r["alert_date"])
        if not rth:
            sk["no_rth"] += 1
            continue
        rec = M.reconstruct(rth, sub, M.atr14_prior_close(db, i), db[i:])
        if rec.get("outcome") != "filled":
            sk["outcome:" + str(rec.get("outcome"))] += 1
            continue
        out.append({
            "ticker": r["ticker"], "alert_date": r["alert_date"],
            "entry": rec["entry"], "stop": rec["stop"],
            "after": [b for b in rth if b["m"] >= rec["fill_minute"]],
            "fwd": db[i + 1:], "prior": [b["c"] for b in db[:i]],
        })
    return out, sk


def stats_line(label, vals, sessions):
    s = sorted(vals)
    if not s:
        return f"{label:<44} n=0"
    sh = lambda t: 100.0 * sum(1 for x in s if x >= t) / len(s)   # noqa: E731
    return (f"{label:<44} n={len(s):<3} sessions={sessions:<3} "
            f"median {M._median(s):+.2f}R  mean {sum(s)/len(s):+.2f}R  "
            f"min {s[0]:+.2f}R  max {s[-1]:+.2f}R  SUM {sum(s):+.1f}R  "
            f">=5R {sh(5):.1f}%")


def main():
    coh, sk = build_cohort()
    L = []
    P = L.append
    P("=" * 100)
    P("LET-WINNERS-RUN, FAITHFULLY — AND THE NO-STOP ARM'S RISK, PRICED   (2026-08-16)")
    P("=" * 100)
    P("")
    P("VERDICT (details + Ns in the sections below; THE LINE — measured only, nothing proposed):")
    P("  * The +36.8R SURVIVES a faithful implementation: +33.6R with the day-0 close checked,")
    P("    +37.2R with day 0 exempt (ladder parity). 11.6% reach >=5R either way. 43 trades, 17 sessions.")
    P("  * The 20-day picture CHANGES: the doc's 'no-stop looks worse at 20d' (-46.8R vs -21.1R)")
    P("    was carried by the crude arm never testing day-0's close. Checked, the close-basis arm")
    P("    is -21.0R vs live's -23.6R at 20 days (n=75) — it TIES live even at the short horizon.")
    P("  * INTC's headline was inflated by truncated data: _case_daily.tsv ends AT the 05-08 peak,")
    P("    so 'no intraday stop +14.46R' was a mark at the peak close. On full history the trail")
    P("    exits day 15 for +9.02R. Still the sharpest single case (live took -1.00R); the number is +9.02R.")
    P("  * THE RISK TERM, matched 43: median MAE -1.97R, P90 -3.95R, worst -6.80R intraday while")
    P("    held. 11 of 43 traded <= -2R intraday and closed above the stop. 7 overnight gap-throughs,")
    P("    worst -0.59R below the stop at the open. Realized worst case @60d: -3.64R (strict) /")
    P("    -5.50R (day0-exempt). On the wider 20d cohort the true worst is MANE: a 0.6%-wide stop,")
    P("    -19.6R MAE, -11.13R realized — tight ORB stops make R-denominated risk explode.")
    P("  * At live sizing ($24 median risk/trade, n=20 closed live magna53): the whole-cohort reward")
    P("    is +33.6R = +$806 over 43 trades; the worst single-name loss so far is -11.13R = -$267;")
    P("    the worst momentary drawdown -19.6R = -$470 on one position. At paper sizing ($958/trade)")
    P("    multiply by ~40: worst name -$10,663.")
    P("  * THE DIP GRADIENT (sec 4): held-through dips are where the edge LIVES — names that dipped")
    P("    <=-1R intraday and closed above the stop sum +39.3R; <=-2R dippers +13.9R (INTC-led);")
    P("    <=-3R dippers -6.5R. Holding pays through -2R and stops paying below -3R, on this N.")
    P("")
    P(f"reconstructed fills: {len(coh)} of 161 HIGH alert rows "
      f"(skips: {', '.join(f'{k}={v}' for k, v in sorted(sk.items()))})")
    c60 = [c for c in coh if len(c["fwd"]) >= 60]
    c20 = [c for c in coh if len(c["fwd"]) >= 20]
    ses = lambda cs: len({c["alert_date"] for c in cs})  # noqa: E731
    P(f"matched cohorts: >=60 fwd days n={len(c60)} (sessions={ses(c60)}) · "
      f">=20 fwd days n={len(c20)} (sessions={ses(c20)})")
    P("")

    # ---- SECTION 1: anchor — reproduce the ad-hoc numbers with the CRUDE arms ----
    P("-" * 100)
    P("1 · ANCHOR — the doc's numbers reproduced with the CRUDE arms (X.simulate), same caches")
    P("-" * 100)
    for hor, cs in ((20, c20), (60, c60), (20, c60)):
        X.HORIZON = hor
        live, nostop = [], []
        for c in cs:
            v = X.simulate(c["entry"], c["stop"], c["after"], c["fwd"], c["prior"],
                           use_partial=True, use_trail=True)
            w = X.simulate(c["entry"], c["stop"], c["after"], c["fwd"], c["prior"],
                           use_partial=True, use_trail=True,
                           be_close_basis=True, hard_close_basis=True)
            if v is not None:
                live.append(v)
            if w is not None:
                nostop.append(w)
        tag = f"@{hor}d on the >={'60' if cs is c60 else '20'}d cohort"
        P(stats_line(f"  crude LIVE {tag}", live, ses(cs)))
        P(stats_line(f"  crude NO-INTRADAY-STOP {tag}", nostop, ses(cs)))
        P("")

    # ---- SECTION 2: the faithful arms ----
    P("-" * 100)
    P("2 · FAITHFUL ARMS — live ladder rebuilt from exit_logic + scan_profit_triggers")
    P("    LIVE  = hard stop & breakeven intraday at the broker · SMA trail close-basis")
    P("    LWR-C = whole ladder CLOSING-basis (the let-winners-run fork), day-0 close included")
    P("-" * 100)
    arms2 = ((False, True, "LIVE"), (True, True, "LWR-C"),
             (True, False, "LWR-C day0-exempt"))
    for hor, cs, tag in ((20, c20, ">=20d cohort"), (60, c60, ">=60d cohort"),
                         (20, c60, ">=60d cohort")):
        for cb, d0c, name in arms2:
            vals = []
            for c in cs:
                r = simulate_faithful(c["entry"], c["stop"], c["after"], c["fwd"],
                                      c["prior"], hor, close_basis=cb,
                                      day0_close_check=d0c)
                if r is not None:
                    vals.append(r["r"])
            P(stats_line(f"  faithful {name} @{hor}d on the {tag}", vals, ses(cs)))
        P("")
    P("  (day0-exempt = the ladder-parity variant: live's EOD ladder skips the alert day,")
    P("   so a close-basis hard stop implemented THROUGH that ladder would too. The strict")
    P("   LWR-C checks day 0's close — the difference between them is entirely the 12")
    P("   names whose day-0 close finished below the ORB low.)")
    P("")

    # ---- SECTION 3: per-name @60d on the matched cohort ----
    P("-" * 100)
    P("3 · PER-NAME @60d, matched >=60d cohort — crude no-stop vs faithful LWR-C (delta = fidelity cost)")
    P("-" * 100)
    X.HORIZON = 60
    rows3 = []
    risk_rows = []
    for c in c60:
        crude = X.simulate(c["entry"], c["stop"], c["after"], c["fwd"], c["prior"],
                           use_partial=True, use_trail=True,
                           be_close_basis=True, hard_close_basis=True)
        f_live = simulate_faithful(c["entry"], c["stop"], c["after"], c["fwd"],
                                   c["prior"], 60, close_basis=False)
        f_lwr = simulate_faithful(c["entry"], c["stop"], c["after"], c["fwd"],
                                  c["prior"], 60, close_basis=True, want_path=True)
        rows3.append((c["ticker"], c["alert_date"], f_live["r"], crude, f_lwr["r"],
                      f_lwr["exit_day"], f_lwr["reason"]))
        risk_rows.append((c, f_lwr))
    rows3.sort(key=lambda x: x[4] - (x[3] if x[3] is not None else 0))
    P(f"  {'name':<6}{'alert':<12}{'faithLIVE':>10}{'crudeNoStop':>12}{'faithLWR-C':>11}"
      f"{'exitday':>8}  reason")
    for t, d, fl, cr, fw, ed, rs in rows3:
        P(f"  {t:<6}{d:<12}{fl:>+10.2f}{(cr if cr is not None else float('nan')):>+12.2f}"
          f"{fw:>+11.2f}{ed:>8}  {rs}")
    P("")

    # ---- SECTION 4: RISK of the close-basis hold (faithful LWR-C @60d, matched cohort) ----
    P("-" * 100)
    P("4 · THE RISK TERM — intraday adverse excursion while held under LWR-C @60d (n below)")
    P("    day 0 = minute resolution from the fill · days 1+ = DAILY LOWS, a conservative")
    P("    FLOOR that UNDERSTATES true intraday excursion (no minute bars exist for these")
    P("    April-May hold windows; alert-day minute capture only began 2026-07-28).")
    P("-" * 100)
    maes, dips = [], {1: [], 2: [], 3: [], 5: []}
    gap_events, gap_names = [], set()
    worst_daily = []
    for c, f in risk_rows:
        entry, stop0 = c["entry"], c["stop"]
        risk = entry - stop0
        # held window: day 0 minutes after fill + daily bars 1..exit_day
        min_px = min((b["l"] for b in c["after"]), default=entry)
        day_rows = f["path"]                     # (di, low, close, open, br_level)
        for di, lo, cl, op, br in day_rows:
            if di == 0:
                continue
            if lo is not None:
                min_px = min(min_px, lo)
        mae_r = (min_px - entry) / risk
        maes.append((mae_r, c["ticker"], c["alert_date"]))
        # sub -kR intraday dips the close-basis rule HELD THROUGH (that day's close >= br)
        for k in dips:
            hit = False
            # day 0 minutes
            d0 = [p for p in day_rows if p[0] == 0]
            if d0 and d0[0][1] is not None and (d0[0][1] - entry) / risk <= -k \
                    and d0[0][2] is not None and d0[0][2] >= d0[0][4]:
                hit = True
            for di, lo, cl, op, br in day_rows:
                if di == 0 or lo is None or cl is None:
                    continue
                if (lo - entry) / risk <= -k and cl >= br:
                    hit = True
            if hit:
                dips[k].append((c["ticker"], c["alert_date"], f["r"]))
        # overnight gap-through: close_t >= br, open_{t+1} < br (br prevailing at t+1)
        prev_cl, prev_br, prev_di = None, None, None
        for di, lo, cl, op, br in day_rows:
            if prev_cl is not None and op is not None and prev_cl >= prev_br and op < br:
                gap_events.append(((op - br) / risk, c["ticker"], c["alert_date"], di))
                gap_names.add((c["ticker"], c["alert_date"]))
            prev_cl, prev_br, prev_di = cl, br, di
        # worst single daily-low excursion day
        wl = min(((lo - entry) / risk, di) for di, lo, cl, op, br in day_rows
                 if lo is not None)
        worst_daily.append((wl[0], wl[1], c["ticker"]))
    maes.sort()
    n = len(maes)
    mae_vals = [m[0] for m in maes]
    pct = lambda p: mae_vals[max(0, min(n - 1, int(round(p / 100 * (n - 1)))))]  # noqa: E731
    P(f"  MAE while held, in R (negative = against us).  n={n} names, "
      f"sessions={ses([c for c, _ in risk_rows])}")
    P(f"    median {M._median(mae_vals):+.2f}R   P75 {pct(25):+.2f}R   P90 {pct(10):+.2f}R   "
      f"worst {mae_vals[0]:+.2f}R ({maes[0][1]} {maes[0][2]})")
    P("    5 worst excursions:")
    for m, t, d in maes[:5]:
        P(f"      {t:<6}{d}  {m:+.2f}R")
    for k in (1, 2, 3, 5):
        nm = dips[k]
        P(f"  traded <= -{k}R intraday AND that day closed above the prevailing stop: "
          f"{len(nm)} of {n} names"
          + (f"  ({', '.join(t for t, _, _ in nm[:8])}"
             + ("…" if len(nm) > 8 else "") + ")" if nm else ""))
        if nm:
            fr = [r for _, _, r in nm]
            P(f"      their final outcomes: median {M._median(fr):+.2f}R · "
              f"{sum(1 for r in fr if r > 0)}/{len(fr)} finished positive · "
              f"SUM {sum(fr):+.1f}R (did holding through the dip pay in aggregate?)")
    P(f"  overnight gap-through (closed above the stop, next OPEN below it): "
      f"{len(gap_events)} events on {len(gap_names)} of {n} names")
    for g, t, d, di in sorted(gap_events)[:8]:
        P(f"      {t:<6}{d}  day {di}: opened {g:+.2f}R below the prevailing stop")
    P("")

    # ---- SECTION 5: the same risk read on the WIDER 20d cohort (worst case lives here) ----
    P("-" * 100)
    P("5 · SAME RISK READ, WIDER >=20d COHORT @20d under LWR-C — the later names live here")
    P("-" * 100)
    maes2, worst_out = [], []
    for c in c20:
        f = simulate_faithful(c["entry"], c["stop"], c["after"], c["fwd"], c["prior"],
                              20, close_basis=True, want_path=True)
        entry, risk = c["entry"], c["entry"] - c["stop"]
        min_px = min((b["l"] for b in c["after"]), default=entry)
        for di, lo, cl, op, br in f["path"]:
            if di > 0 and lo is not None:
                min_px = min(min_px, lo)
        maes2.append(((min_px - entry) / risk, c["ticker"], c["alert_date"]))
        worst_out.append((f["r"], c["ticker"], c["alert_date"], f["exit_day"], f["reason"]))
    maes2.sort()
    mv = [m[0] for m in maes2]
    n2 = len(mv)
    pct2 = lambda p: mv[max(0, min(n2 - 1, int(round(p / 100 * (n2 - 1)))))]  # noqa: E731
    P(f"  MAE while held @20d, n={n2}, sessions={ses(c20)}: "
      f"median {M._median(mv):+.2f}R  P90 {pct2(10):+.2f}R  worst {mv[0]:+.2f}R "
      f"({maes2[0][1]} {maes2[0][2]})")
    worst_out.sort()
    P("  5 worst REALIZED outcomes under LWR-C @20d (the arm's true worst cases):")
    for r, t, d, ed, rs in worst_out[:5]:
        P(f"      {t:<6}{d}  {r:+.2f}R  (exit day {ed}, {rs})")
    P("")

    # ---- SECTION 6: gap risk is not unique to the no-stop arm ----
    P("-" * 100)
    P("6 · FOR SYMMETRY — the LIVE intraday stop also cannot cap a loss at -1R (gap-throughs)")
    P("-" * 100)
    lv = []
    for c in c20:
        f = simulate_faithful(c["entry"], c["stop"], c["after"], c["fwd"], c["prior"],
                              20, close_basis=False)
        lv.append((f["r"], c["ticker"], c["alert_date"], f["exit_day"]))
    lv.sort()
    P("  5 worst faithful-LIVE outcomes @20d (stop filled at the OPEN when gapped through):")
    for r, t, d, ed in lv[:5]:
        P(f"      {t:<6}{d}  {r:+.2f}R  (exit day {ed})")
    P("")

    # ---- SECTION 7: corrections, dollars, and what daily resolution cannot see ----
    P("-" * 100)
    P("7 · CORRECTIONS, DOLLAR TERMS, AND WHERE DAILY RESOLUTION UNDERSTATES THE RISK")
    P("-" * 100)
    P("  INTC CORRECTION — the +14.46R told to the operator twice is a truncation artifact.")
    P("    _case_daily.tsv (commit 95c9036) ends 2026-05-08 — the exact peak day — so the sim")
    P("    ran out of bars and marked the open position at the peak close $124.92. On full")
    P("    history (_468_daily_full.tsv) the SMA trail closes it day 15 (2026-05-15, close")
    P("    $108.77) for +9.02R. Still 10R better than the live rule's -1.00R; quote +9.02R.")
    P("    (SMCI's +0.40R reproduces exactly; only INTC's cache was truncated at the peak.)")
    P("")
    P("  DOLLAR TERMS at the operator's REAL sizing (prod read 2026-08-16: closed live")
    P("  magna53 trades n=20, risk/trade min $11.96 · median $24.00 · max $48.92;")
    P("  paper n=26, median $957.96):")
    P("    reward, matched 43 @60d:  +33.6R  = +$806 (live $24)  /  +$32,187 (paper $958)")
    P("    worst realized single name: MANE -11.13R = -$267 (live) / -$10,663 (paper)")
    P("    worst momentary MAE:        MANE -19.58R = -$470 (live) / -$18,758 (paper)")
    P("    typical (median) MAE:             -1.97R = -$47  (live) / -$1,887  (paper)")
    P("    ⚠ R-based sizing makes the NOTIONAL balloon on tight stops: MANE's 0.6%-wide ORB")
    P("      stop puts ~$3,900 of stock at risk for a $24 nominal R — the no-stop arm then")
    P("      exposes that whole notional to a -10.9% two-day slide. The R unit hides this;")
    P("      the dollar unit shows it.")
    P("")
    P("  WHERE DAILY RESOLUTION UNDERSTATES THE RISK (all conservative floors):")
    P("    1. Days 1+ MAE uses DAILY LOWS — the true minute-path excursion is >= the daily low")
    P("       only in timing, never magnitude, BUT sub-day sequencing is invisible: a day that")
    P("       dipped -3R then closed green counts once; multiple intraday round-trips don't.")
    P("       Magnitude itself IS the daily low, so the floor is exact per-day; what is")
    P("       understated is DURATION and path (margin calls, panic behaviour, intraday")
    P("       decision pressure are unmodelled).")
    P("    2. No minute bars exist for ANY of the 43 hold windows beyond day 0 (April-May")
    P("       cohort; alert-day minute capture began 2026-07-28 and the 08-15 backfill covers")
    P("       alert ticker-days, not 60-day hold windows). Day-0 excursions ARE minute-true.")
    P("    3. The close-basis exits assume the day's official CLOSE is attainable (MOC-style).")
    P("       Auction slippage on thin names is unmodelled, as everywhere in this work.")
    P("    4. Same-day stop-vs-target ordering at daily resolution is unknowable; the sim")
    P("       assumes stop-first (conservative for the intraday arms; the close-basis arm is")
    P("       unaffected except via the partial's bank).")
    P("    5. One regime (Apr-Aug 2026), reconstructed not lived, no slippage, and the 43-name")
    P("       60d cohort is ALL early-period — no out-of-sample half exists until October.")
    P("")
    P("  N ON EVERY HEADLINE: 43 names / 17 sessions (60d matched) · 75 names / 38 sessions")
    P("  (20d cohort) · sizing n=20 closed live trades. THE LINE: nothing proposed here.")
    return L, risk_rows, c60


if __name__ == "__main__":
    L, _, _ = main()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L))
    print(f"-> {OUT}")
