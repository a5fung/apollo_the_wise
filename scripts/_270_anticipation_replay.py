#!/usr/bin/env python3
"""#270 step 2c (gate-free) — ANTICIPATION entry, the third entry mode (Pradeep).

The two tuned entries (FIRST5-BREAK / GDL-RECLAIM) are CONFIRMATION entries: they fire
ON the trigger day, after the breakout is underway. Pradeep's ANTICIPATION entry fires
EARLIER — at the CLOSE of a quiet, tight, low-volume day when the name has reclaimed the
pivot and is COILED ("set up / nearing ready, tightening"), betting the breakout comes
next day. Payoffs (his words): (1) you're already in BELOW any gap-up = capture the bulk;
(2) the coiled-day low is the stop = you "know fast if it failed".

A single anticipation entry is a strawman: a tight coiled-low stop entered before the
breakout gets shaken in a still-consolidating name almost every time. Pradeep RE-ENTERS
while the setup is intact — each shake is a small ~2% (-1R) loss, the eventual hold into
the breakout is a tight-stop = big-R capture. "One pays for ten losers." So the faithful
model is STOP-AND-REENTER; one-shot is reported only as the lower bound.

METHODOLOGY (advisor-hardened):
 * Evaluated over ALL ARMED names — incl. the ones that NEVER broke out (the false set =
   the COST side; dropping it would inflate the verdict via survivorship).
 * No lookahead: COILED = reclaimed gap_day_low & SMA20 + tight range + quiet volume =
   the trigger conditions MINUS the volume burst. Forward-computable; lands pre-breakout
   by construction, never "the day before the day we know was the trigger".
 * Parity: the three-way R comparison re-bases onto ONE common daily endpoint (trigger+10d)
   with ONE R definition. The prior FIRST5=3.5R / GDL=1.4R numbers were BOTH intraday and
   stay valid among themselves; mixing a multi-day MFE in would be a pure-horizon artifact.
 * Price-capture (claim #1) and R/expectancy reported SEPARATELY — a better entry price
   must not bleed into an R claim (the stop distance differs).
 * One-shot (lower bound) AND stop-and-reenter (faithful) both reported.

Read-only daily-bar replay (+ pulled trigger-day minute bars for the FIRST5 price). Gate-free.
Usage: python scripts/_270_anticipation_replay.py
"""
import importlib.util
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent


def _load(name):
    spec = importlib.util.spec_from_file_location(name.replace(".py", ""), HERE / name)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


r270 = _load("_270_delayed_ep_replay.py")        # replay() — the validated lifecycle
entry_mod = _load("_270_entry_replay.py")          # load_rth(), entry_first5() — FIRST5 price
replay = r270.replay

# ── anticipation-day criterion (tunable; OPERATOR to calibrate, not self-certified) ──
TIGHT_RANGE = 0.07     # daily (high-low)/close <= 7% = a contraction bar
VOL_CONTRACT = 1.0     # vol <= 1.0x ADV20 = the quiet "rest" before expansion
FWD_N = 10             # common forward endpoint = trigger day + 10 trading days
# MATURITY gate (operator 6/14): a coil develops over several days; entering the FIRST quiet
# day is immature. A "base day" = holds above the pivot in a contained range; a MATURE coil
# requires >= MATURE_DAYS such days have formed (the contraction is developed, nearer the apex).
BASE_RANGE = 0.12      # contained day = (high-low)/close <= 12% AND close > gap_day_low
MATURE_DAYS = 3        # require a >=3-day base before the coiled-day entry qualifies as mature


def adv(vols, i, n=20):
    return sum(vols[max(0, i - n + 1):i + 1]) / min(i + 1, n)


def sma20(closes, i):
    return sum(closes[i - 19:i + 1]) / 20 if i >= 19 else None


def median(xs):
    s = sorted(x for x in xs if x is not None)
    return s[len(s) // 2] if s else float("nan")


def mean(xs):
    s = [x for x in xs if x is not None]
    return sum(s) / len(s) if s else float("nan")


def lifecycle(bars):
    """Reuse replay() to get the first cycle that reaches ARMED → structured context."""
    idx_of = {b["date"]: i for i, b in enumerate(bars)}
    watched = armed = trig = None
    for date, state, _ in replay(bars):
        if state == "WATCHED" and armed is None:
            watched = date
        elif state == "ARMED" and armed is None and watched is not None:
            armed = date
        elif state == "TRIGGERED" and armed is not None and trig is None:
            trig = date
            break
    if armed is None or watched is None:
        return None
    return {"gap_day_low": bars[idx_of[watched]]["l"], "armed_idx": idx_of[armed],
            "trig_idx": idx_of[trig] if trig else None}


def base_run(bars, ctx, i):
    """Consecutive 'base days' ending at i: close > gap_day_low AND range <= BASE_RANGE.
    Measures how DEVELOPED the contraction is (the maturity proxy for chart-reading)."""
    n, j = 0, i
    while j > ctx["armed_idx"]:
        b = bars[j]
        rng = (b["h"] - b["l"]) / b["c"] if b["c"] else 1
        if b["c"] > ctx["gap_day_low"] and rng <= BASE_RANGE:
            n, j = n + 1, j - 1
        else:
            break
    return n


def find_coiled_days(bars, ctx, min_base=1):
    """Forward-computable COILED days in the armed window: reclaimed pivot (close > gap_day_low
    AND > SMA20) + tight range + quiet volume, no expansion yet. min_base>1 adds the MATURITY
    gate (require a >= min_base-day developed base — don't enter the first immature quiet day).
    [] if a fast undercut->trigger left no qualifying coiled day."""
    a0 = ctx["armed_idx"] + 1
    a1 = ctx["trig_idx"] if ctx["trig_idx"] is not None else min(ctx["armed_idx"] + r270.ARM_WINDOW, len(bars))
    vols = [b["v"] for b in bars]
    closes = [b["c"] for b in bars]
    out = []
    for i in range(a0, a1):
        b = bars[i]
        s20 = sma20(closes, i)
        rng = (b["h"] - b["l"]) / b["c"] if b["c"] else 1
        reclaimed = b["c"] > ctx["gap_day_low"] and (s20 is None or b["c"] > s20)
        if reclaimed and rng <= TIGHT_RANGE and b["v"] <= VOL_CONTRACT * adv(vols, i):
            if base_run(bars, ctx, i) >= min_base:
                out.append(i)
    return out


def simulate_reenter(bars, coiled, trig_idx, end_idx):
    """Faithful Pradeep: enter at each coiled close (stop = coiled low). If shaken, RE-ENTER
    at the next coiled day past the stop. Win = held (no stop) into the breakout (trig_idx) →
    capture MFE to endpoint on the tight coiled stop. Returns the list of attempts (each
    R = -1.0 if stopped, else MFE/risk on a win; 'open' = drifted to window end)."""
    attempts = []
    cursor = -1
    for ai in coiled:
        if ai <= cursor:
            continue
        entry, stop = bars[ai]["c"], bars[ai]["l"]
        risk = (entry - stop) / entry
        if risk <= 0:
            continue
        run_high, outcome, exit_i = entry, None, None
        for i in range(ai + 1, end_idx + 1):
            if trig_idx is not None and i >= trig_idx:        # reached the breakout, not stopped
                run_high = max(b["h"] for b in bars[ai + 1: end_idx + 1])
                outcome, exit_i = "win", end_idx
                break
            if bars[i]["l"] <= stop:                          # shaken first
                outcome, exit_i = "stop", i
                break
            run_high = max(run_high, bars[i]["h"])
        if outcome is None:                                   # ran out of window
            outcome, exit_i = "open", end_idx
        mfe = run_high / entry - 1
        R = -1.0 if outcome == "stop" else mfe / risk
        attempts.append({"ai": ai, "entry": entry, "stop": stop, "risk": risk,
                         "outcome": outcome, "R": R, "mfe": mfe, "exit_i": exit_i})
        if outcome != "stop":
            break                                             # win or drift → done with this setup
        cursor = exit_i                                       # re-enter only AFTER the shake
    return attempts


def mfe_R(bars, entry_idx, entry, stop, end_idx):
    """Parity MFE ceiling: max favorable high over [entry_idx .. end_idx] INCLUDING the entry
    day's own post-entry high, no stop truncation (symmetric with the anticipation 'win' MFE,
    which also runs to end_idx un-truncated). FIRST5 enters intraday on its entry day, so that
    day's high is post-entry and is exactly the breakout it exists to capture — it MUST be
    included, else FIRST5 is denied the move anticipation is credited with (advisor 6/14)."""
    risk = (entry - stop) / entry if entry > stop else None
    if not risk or risk <= 0:
        return None
    run_high = max(b["h"] for b in bars[entry_idx: end_idx + 1])
    return {"risk": risk, "R_mfe": (run_high / entry - 1) / risk}


# Harvest rules MIRRORING _270_exit_replay.py — so anticipation's WIN leg is scored on a
# REALIZED exit (banked at a target / trailed / closed out), NOT the perfect-foresight MFE
# ceiling mfe_R returns. Advisor 6/14: the entry-mode R ranking (anticipation 15R vs FIRST5
# 7.6R) was MFE-vs-MFE; until both run through the SAME harvest, no realized preference holds.
_HARVEST = {
    "all_out_+1R":   dict(partials=[(1.0, 1.0)]),
    "half_1R_trail": dict(partials=[(1.0, 0.5)], breakeven_after_first=True, trail_prior_low=True),
    "bank_1R_3R":    dict(partials=[(1.0, 0.5), (3.0, 0.5)]),
}


def harvest_realized(bars, entry_idx, entry, stop, end_idx, rule):
    """REALIZED R harvesting the anticipation entry on DAILY bars (entry = coiled close,
    forward = daily; no trigger-day minute resolution — anticipation enters at a close).
    Pessimistic intrabar (stop-first) + gap-through fill at min(stop, bar_open), matching
    _270_exit_replay's honesty conventions. Returns realized R or None."""
    risk = entry - stop
    if risk <= 0:
        return None
    partials = list(rule.get("partials", []))
    pos, realized, cur_stop = 1.0, 0.0, stop
    prior_low = bars[entry_idx]["l"]
    for i in range(entry_idx + 1, end_idx + 1):
        b = bars[i]
        if rule.get("trail_prior_low"):
            cur_stop = max(cur_stop, prior_low)
        tgt = entry + partials[0][0] * risk if partials else None
        if b["l"] <= cur_stop:                              # pessimistic: stop first
            realized += pos * (min(cur_stop, b["o"]) - entry) / risk
            pos = 0.0
            break
        if tgt is not None and b["h"] >= tgt:
            r_mult, frac = partials.pop(0)
            f = min(frac, pos)
            realized += f * r_mult
            pos -= f
            if rule.get("breakeven_after_first"):
                cur_stop = max(cur_stop, entry)
        prior_low = b["l"]
        if pos <= 0:
            break
    if pos > 0:                                             # survived: exit at endpoint close
        realized += pos * (bars[end_idx]["c"] - entry) / risk
    return realized


def realized_net(x, bars, rule):
    """Anticipation net REALIZED R for one name: the -1R shake costs (unchanged) PLUS the
    win leg harvested through `rule` instead of credited full MFE. None if no win leg."""
    if not x["win"]:
        return None
    shakes = sum(a["R"] for a in x["attempts"] if a["outcome"] == "stop")   # each -1R, real
    w = x["win"]
    h = harvest_realized(bars, w["ai"], w["entry"], w["stop"], x["end_idx"], rule)
    return None if h is None else shakes + h


def parity_threeway(names, bars_by, rth):
    """Parity-clean anticipation-vs-FIRST5 (endpoint-symmetric MFE) over the won names that have
    minute bars. Recompute at EACH maturity setting — the won-name set + the winning anticipation
    entry both change with min_base, so a parity number computed at min_base=1 does NOT describe a
    min_base=3 cohort (the basis-mismatch class). Returns the per-name pairs."""
    tw = []
    for x in [n for n in names if n["triggered"] and n["win"]]:
        t = x["t"]
        tdate = bars_by[t][x["ctx"]["trig_idx"]]["date"]
        f5 = entry_mod.entry_first5(rth.get((t, tdate), []), x["ctx"]["gap_day_low"]) if (t, tdate) in rth else None
        if not f5:
            continue
        f5w = mfe_R(bars_by[t], x["ctx"]["trig_idx"], f5[0], f5[1], x["end_idx"])
        if f5w:
            tw.append({"a_R": x["win"]["R"], "a_risk": x["win"]["risk"],
                       "f5_R": f5w["R_mfe"], "f5_risk": f5w["risk"]})
    return tw


def build_names(bars_by, min_base=1):
    """Run the lifecycle + coiled-day finder + stop-and-reenter sim per ticker for a given
    maturity gate. Returns (armed_count, [per-name dicts]). armed_count is min_base-independent."""
    armed, names = 0, []
    for t, bars in bars_by.items():
        ctx = lifecycle(bars)
        if ctx is None:
            continue
        armed += 1
        coiled = find_coiled_days(bars, ctx, min_base)
        if not coiled:
            continue
        triggered = ctx["trig_idx"] is not None
        end_idx = (ctx["trig_idx"] + FWD_N) if triggered else min(coiled[-1] + 10, len(bars) - 1)
        end_idx = min(end_idx, len(bars) - 1)
        attempts = simulate_reenter(bars, coiled, ctx["trig_idx"], end_idx)
        win = next((a for a in attempts if a["outcome"] == "win"), None)
        names.append({"t": t, "triggered": triggered, "attempts": attempts, "win": win,
                      "end_idx": end_idx, "ctx": ctx, "n_coiled": len(coiled)})
    return armed, names


def summarize(names):
    """Compact aggregates for the maturity sweep."""
    trig = [x for x in names if x["triggered"]]
    allnet = [sum(a["R"] for a in x["attempts"]) for x in names]
    trignet = [sum(a["R"] for a in x["attempts"]) for x in trig]
    db = [x["ctx"]["trig_idx"] - x["win"]["ai"] for x in trig if x["win"]]
    top = max(allnet) if allnet else 0.0
    ex = [r for r in allnet if r != top]
    return {"fired": len(names), "catch": sum(1 for x in names if x["win"]),
            "db": median(db) if db else float("nan"),
            "attempts": mean([len(x["attempts"]) for x in names]) if names else float("nan"),
            "trig_mean": mean(trignet), "full_mean": mean(allnet),
            "top_share": (top / sum(allnet) * 100 if sum(allnet) else 0.0),
            "ex_mean": mean(ex) if ex else float("nan")}


def main():
    bars_by = defaultdict(list)
    for line in (HERE / "_270_cohort_bars.tsv").read_text(encoding="utf-8").splitlines():
        p = line.rstrip("\r").split("\t")
        if len(p) != 7:
            continue
        t, d, o, h, l, c, v = p
        bars_by[t].append({"date": d, "o": float(o), "h": float(h), "l": float(l),
                           "c": float(c), "v": float(v)})
    for t in bars_by:
        bars_by[t].sort(key=lambda b: b["date"])
    rth = entry_mod.load_rth()

    armed, names = build_names(bars_by, min_base=1)   # detailed report = loose baseline
    n_fired = len(names)
    trig_fired = [x for x in names if x["triggered"]]
    print("#270 step 2c - ANTICIPATION entry replay  (cohort, daily bars; gate-free)")
    print(f"thresholds: TIGHT_RANGE<={TIGHT_RANGE:.0%}  VOL<= {VOL_CONTRACT}x ADV20  "
          f"COILED = reclaimed gap_day_low & SMA20, no expansion  fwd endpoint=trigger+{FWD_N}d\n")
    print(f"FIRE: {armed} ARMED names; a distinct COILED day fired on {n_fired} "
          f"({n_fired/armed*100:.0f}%) - {len(trig_fired)} later TRIGGERED, "
          f"{n_fired-len(trig_fired)} never did (the false-anticipation COST set).")
    db = [x["ctx"]["trig_idx"] - x["win"]["ai"] for x in trig_fired if x["win"]]
    if db:
        print(f"      WINNING coiled entry lands {median(db):.0f}d before the breakout (median), "
              f"range {min(db)}..{max(db)}d.  coiled days/name: median {median([x['n_coiled'] for x in names]):.0f}")
    if n_fired < 8:
        print("      [!] N<8 - ILLUSTRATIVE, not a verdict.")
    print()

    # ── 1. PRICE CAPTURE (claim #1) — winning anticipation entry vs FIRST5 entry ──
    pc = []
    for x in trig_fired:
        if not x["win"]:
            continue
        tdate = bars_by[x["t"]][x["ctx"]["trig_idx"]]["date"]
        f5 = entry_mod.entry_first5(rth.get((x["t"], tdate), []), x["ctx"]["gap_day_low"]) if (x["t"], tdate) in rth else None
        if f5:
            hi = max(b["h"] for b in bars_by[x["t"]][x["win"]["ai"]: x["end_idx"] + 1])
            pc.append({"a": x["win"]["entry"], "f5": f5[0], "hi": hi})
    if pc:
        head = [(p["f5"] - p["a"]) / p["a"] for p in pc]
        share = [(p["f5"] - p["a"]) / (p["hi"] - p["a"]) for p in pc if p["hi"] > p["a"]]
        print(f"1. PRICE CAPTURE (winning anticipation close vs FIRST5 entry; triggered, N={len(pc)}):")
        print(f"   anticipation enters {median(head)*100:.0f}% BELOW the FIRST5 price (median) = the gap/early move confirmation gives up.")
        print(f"   = {median(share)*100:.0f}% of the whole run to the window high captured earlier (median).\n")

    # ── 2. FAST-FAIL (claim #2) — the shake attempts ──
    shakes = [a for x in names for a in x["attempts"] if a["outcome"] == "stop"]
    if shakes:
        print(f"2. FAST-FAIL (shaken anticipation attempts across all names, N={len(shakes)}):")
        print(f"   median loss {median([a['risk'] for a in shakes])*100:.0f}% (= the coiled-stop distance, -1R) - small + fast by design.\n")

    # ── 3. EXPECTANCY: one-shot (lower bound) vs stop-and-reenter (faithful), per name ──
    oneshot = [x["attempts"][0]["R"] for x in trig_fired if x["attempts"]]          # first coiled day only
    reenter = [sum(a["R"] for a in x["attempts"]) for x in trig_fired]              # net across attempts
    winrate = sum(1 for x in trig_fired if x["win"]) / len(trig_fired) if trig_fired else 0
    print(f"3. EXPECTANCY (triggered names, N={len(trig_fired)}) - net R per name:")
    print(f"   ONE-SHOT (first coiled day, the strawman): median {median(oneshot):+.1f}R  mean {mean(oneshot):+.1f}R")
    print(f"   STOP-AND-REENTER (faithful Pradeep):       median {median(reenter):+.1f}R  mean {mean(reenter):+.1f}R  "
          f"| eventually caught the breakout: {winrate*100:.0f}% of names")
    print(f"   (re-enter R = small -1R shakes + the tight-stop capture on the hold-into-breakout. Avg "
          f"{mean([len(x['attempts']) for x in trig_fired]):.1f} attempts/name.)\n")

    # ── 3b. PARITY three-way vs FIRST5 (same daily endpoint, single entry each) ──
    tw = parity_threeway(names, bars_by, rth)
    if tw:
        print(f"3b. PARITY three-way, common daily endpoint + endpoint-symmetric MFE (won names, N={len(tw)}):")
        print(f"    {'entry':<16}{'med risk':<10}{'med R(MFE)'}")
        print(f"    {'ANTICIPATION':<16}{median([x['a_risk'] for x in tw])*100:>6.0f}%   {median([x['a_R'] for x in tw]):>6.1f}R")
        print(f"    {'FIRST5-BREAK':<16}{median([x['f5_risk'] for x in tw])*100:>6.0f}%   {median([x['f5_R'] for x in tw]):>6.1f}R")
        print("    (both MFE incl. their own entry-day high, un-truncated; the only diff = entry TIMING/price.\n"
              "     NOT comparable to the intraday 3.5R - re-based horizon. N=4, conditioned on anticipation having won.)\n")

    # ── 3c. REALIZED harvest (advisor 6/14) — the win leg run through the SAME exit rules as
    #        _270_exit_replay, NOT credited full MFE. THIS is the realized anticipation R. ──
    print("3c. REALIZED HARVEST (anticipation win leg harvested, NOT MFE; triggered names):")
    print(f"    {'rule':<16}{'med net R':<12}{'mean net R':<12}{'win%':<7}(vs MFE net below)")
    for rname, rule in _HARVEST.items():
        rz = [realized_net(x, bars_by[x["t"]], rule) for x in trig_fired]
        rz = [r for r in rz if r is not None]
        wr = sum(1 for r in rz if r > 0) / len(rz) if rz else float("nan")
        print(f"    {rname:<16}{median(rz):<+12.1f}{mean(rz):<+12.1f}{wr*100:<7.0f}")
    mfe_net = [sum(a["R"] for a in x["attempts"]) for x in trig_fired]   # MFE win leg (section 3/4)
    print(f"    {'MFE_ceiling':<16}{median(mfe_net):<+12.1f}{mean(mfe_net):<+12.1f}"
          f"{sum(1 for r in mfe_net if r>0)/len(mfe_net)*100:<7.0f}(<- the perfect-foresight "
          "upper bound; the realized rows are the honest expectancy)")
    print("    => realized anticipation R is the all_out_+1R/half_trail rows, NOT the MFE ceiling;\n"
          "       any anticipation-vs-FIRST5 preference must compare realized-to-realized.\n")

    # ── 4. FULL-COHORT cost side (all fired, incl. false anticipations) ──
    allnet = [sum(a["R"] for a in x["attempts"]) for x in names]
    catch = sum(1 for x in names if x["win"])
    print(f"4. FULL-COHORT (ALL {n_fired} fired, incl. {n_fired-len(trig_fired)} that never broke out) - stop-and-reenter net R/name:")
    print(f"   median {median(allnet):+.1f}R  mean {mean(allnet):+.1f}R  total {sum(allnet):+.1f}R  | "
          f"caught a breakout: {catch}/{n_fired} ({catch/n_fired*100:.0f}%)")
    print("   = the honest expectancy: small repeated shakes on the false set, paid back by the tight-stop captures.")
    # outlier-concentration check (W2 skip-wide-open lesson: decompose winners before trusting aggregate)
    top = max(allnet)
    ex = [r for r in allnet if r != top]
    print(f"   OUTLIER CHECK: the single best name = {top:+.1f}R = {top/sum(allnet)*100:.0f}% of total. "
          f"Ex-top: mean {mean(ex):+.1f}R/name, total {sum(ex):+.1f}R (still positive = survives outlier removal,\n"
          f"   UNLIKE the W2 skip-wide-open study) - but the headline mean IS outlier-leveraged. N small -> illustrative.\n")

    # ── per-name audit (eyeball for artifacts) ──
    print("PER-NAME (triggered): ticker  trig?  attempts[outcome:R ...]  net")
    for x in sorted(names, key=lambda y: -sum(a["R"] for a in y["attempts"])):
        seq = " ".join(f"{a['outcome'][0]}:{a['R']:+.1f}" for a in x["attempts"])
        net = sum(a["R"] for a in x["attempts"])
        print(f"   {x['t']:<6} {'TRIG' if x['triggered'] else 'none':<5} [{seq}]  net {net:+.1f}R")

    # ── MATURITY SWEEP (operator 6/14: wait for the coil to develop before entering) ──
    print("\nMATURITY SWEEP - require a >= min_base-day developed base before the coiled entry "
          f"(BASE_RANGE<={BASE_RANGE:.0%}, MATURE default {MATURE_DAYS}d):")
    print(f"  {'min_base':<9}{'fired':<7}{'caught':<8}{'entry d-before':<15}{'attempts/nm':<13}"
          f"{'trig meanR':<12}{'full meanR':<12}{'top%':<6}{'ex-top meanR'}")
    for mb in (1, 2, 3, 4):
        s = summarize(build_names(bars_by, mb)[1])
        print(f"  {mb:<9}{s['fired']:<7}{s['catch']:<8}{s['db']:<15.0f}{s['attempts']:<13.1f}"
              f"{s['trig_mean']:<+12.1f}{s['full_mean']:<+12.1f}{s['top_share']:<6.0f}{s['ex_mean']:+.1f}")
    print("  REAL SIGNAL = winner-retention asymmetry, NOT the mean-R magnitudes (those rise partly")
    print("  MECHANICALLY: a higher min_base just shrinks to a subset + drops losers first). 'caught'")
    print("  holds while 'fired' falls = winners survive the gate longer than losers; the clip point")
    print("  (where caught finally drops) marks the edge. The +R magnitudes are in-sample/leveraged.\n")

    # parity-clean anticipation-vs-FIRST5 RE-BASED at the maturity setting (advisor: the 3b above
    # is min_base=1; do NOT set the maturity net-R beside a FIRST5 number computed at min_base=1).
    for mb in (1, 3):
        tw_mb = parity_threeway(build_names(bars_by, mb)[1], bars_by, rth)
        if tw_mb:
            print(f"  PARITY @min_base={mb} (won names w/ minute bars, N={len(tw_mb)}): "
                  f"ANTICIPATION median {median([x['a_R'] for x in tw_mb]):.1f}R "
                  f"(risk {median([x['a_risk'] for x in tw_mb])*100:.0f}%)  vs  "
                  f"FIRST5 median {median([x['f5_R'] for x in tw_mb]):.1f}R "
                  f"(risk {median([x['f5_risk'] for x in tw_mb])*100:.0f}%)")
    print("  (this is the ONLY apples-to-apples anticipation-vs-confirmation read; net stop-and-reenter R is NOT.)")


if __name__ == "__main__":
    main()
