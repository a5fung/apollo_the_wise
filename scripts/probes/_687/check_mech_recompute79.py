"""ADVERSARIAL CHECK of #687 part 3 (mechanics.py), item 4: recompute the 79-real-EP timing numbers with an
INDEPENDENT walker. $0, offline, reads only the frozen captures depth.build_states() already reads.

What is shared with mechanics.py: the INPUT population only (DP.build_states -> day-1 states, daily bars,
held minute bars) and the stored per-trade R used as a fidelity target. What is NOT shared: the walker, the
SMA/line arithmetic, the close test, the 15:45 verdict (no apply_daily_exit_step, no mechanics.walk).

Conventions re-implemented from the rule text (docs/analysis/687_*.md, study.walk_hybrid_arm docstrings):
  resting stop  A0 = the ratcheted line; D10 = max(floor, round(line_r - adr_pct*line_r, 2)) when the trail
                governs, else the floor; floor = hard, or max(hard, entry) once breakeven is armed.
  intraday      per minute bar: breakeven arm on the bar high; stop on the bar low (fill = min(open, stop));
                1/3 partial at the target on the bar high; stop+target or stop+breakeven same bar -> abstain.
  close test    SELL iff close < max(rest, max(SMA10, SMA20) of prior closes + held closes incl. today,
                entry if breakeven) -- the live ladder's step 4/5.
  timings       close (16:00 close) / open (next daily open) / 1545 (verdict on the 15:44 bar close; SELL ->
                MOC at the daily close, stop gone from 15:45) / 1545mkt (SELL -> the 15:45 bar open).
"""
from __future__ import annotations

import sys
from datetime import date, time, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "_685"))
import depth as DP  # noqa: E402

OUT = None


def P(*a):
    s = " ".join(str(x) for x in a)
    print(s)
    if OUT is not None:
        OUT.write(s + "\n")


def line_of(closes):
    """max(SMA10, SMA20) exactly as the ladder composes it (SMA20 present -> larger of the two; else SMA10)."""
    s10 = sum(closes[-10:]) / 10 if len(closes) >= 10 else None
    s20 = sum(closes[-20:]) / 20 if len(closes) >= 20 else None
    if s20 is not None:
        return s10 if s10 > s20 else s20
    return s10


def eff_stop(rest, closes_incl_p, be, entry):
    e = float(rest or 0)
    a = line_of(closes_incl_p)
    if a and a > e:
        e = a
    if be and entry > e:
        e = entry
    return e


def walk(arm, timing, k, st, daily, held, horizon, diag):
    tk, ad = k
    entry, hard = st["entry"], st["hard"]
    shares, rem = st["shares"], st["remaining"]
    pt, be = st["partial_taken"], st["be_active"]
    target, bet, adr = st["target"], st["be_trigger"], st["adr_pct"]
    pnl = sum(e["pnl"] for e in st["exits"])
    denom = shares * (entry - hard)
    db = daily.get(tk, {})
    days = sorted(db)
    prior = [db[x]["c"] for x in days if x < ad and db[x]["c"] is not None]
    held_closes = []
    line = max(hard, entry if be else hard)
    d = ad
    reason = None

    def sell(px, q):
        nonlocal pnl
        pnl += (px - entry) * q

    if rem <= 0:
        return pnl / denom, "none"
    while True:
        d += timedelta(days=1)
        if d > horizon:
            lc = held_closes[-1] if held_closes else entry
            diag["mark"] = (pnl + (lc - entry) * rem) / denom
            return None, "open_at_horizon"
        if d.weekday() >= 5:
            continue
        b = db.get(d)
        if not b or b["c"] is None or b["l"] is None or b["h"] is None:
            continue
        floor = max(hard, entry) if be else hard
        line = max(line, floor)
        lr = round(line, 2)
        gov = lr > round(floor, 2) + 1e-9
        if arm == "A0":
            rest = lr
        elif gov and adr:
            rest = max(round(floor, 2), round(lr - adr * lr, 2))
        else:
            rest = round(floor, 2)
        mb = held.get((tk, d), [])
        pre = []
        v = None
        for mbar in mb:
            if v is None and mbar["m"].time() >= time(15, 45):
                if pre:
                    p = pre[-1]["c"]
                    v = p < eff_stop(rest, prior + held_closes + [p], be, entry)
                    if timing == "close" and arm == "D10":
                        cv = b["c"] < eff_stop(rest, prior + held_closes + [b["c"]], be, entry)
                        diag[("FALSE_SELL" if v and not cv else "MISS" if cv and not v
                              else "agree_sell" if v else "agree_hold")] += 1
                    if v and timing in ("1545", "1545mkt"):
                        sell(b["c"] if timing == "1545" else mbar["o"], rem)
                        return pnl / denom, "sold_1545" + ("_closed_above" if not (
                            b["c"] < eff_stop(rest, prior + held_closes + [b["c"]], be, entry)) else "")
                else:
                    v = False
            pre.append(mbar)
            if (not be) and mbar["h"] >= bet:
                if rest < entry and mbar["l"] <= entry:
                    return None, "abstain"
                be = True
                floor = max(hard, entry)
                rest = max(rest, round(entry, 2))
                line = max(line, entry)
            hs = mbar["l"] <= rest
            ht = target is not None and not pt and mbar["h"] >= target
            if hs and ht:
                return None, "abstain"
            if hs:
                sell(min(mbar["o"], rest), rem)
                diag.setdefault("stop_notional_r", []).append(min(mbar["o"], rest) * rem / denom)
                return pnl / denom, "stop_hit"
            if ht:
                q = rem / 3
                sell(target, q)
                rem -= q
                pt = True
                be = True
                floor = max(hard, entry)
                rest = max(rest, round(entry, 2))
                line = max(line, entry)
        if v is None and pre and timing in ("1545", "1545mkt"):
            p = pre[-1]["c"]
            if p < eff_stop(rest, prior + held_closes + [p], be, entry):
                sell(b["c"], rem)
                return pnl / denom, "sold_1545_lastbar"
        if not mb:
            if (not be) and b["h"] >= bet:
                if rest < entry and b["l"] <= entry:
                    return None, "abstain"
                be = True
                floor = max(hard, entry)
                rest = max(rest, round(entry, 2))
                line = max(line, entry)
            if target is not None and not pt and b["h"] >= target:
                if b["l"] <= rest:
                    return None, "abstain"
                q = rem / 3
                sell(target, q)
                rem -= q
                pt = True
                be = True
                floor = max(hard, entry)
                rest = max(rest, round(entry, 2))
                line = max(line, entry)
            if timing in ("1545", "1545mkt") and b["l"] > rest:
                hi = b["h"] < eff_stop(rest, prior + held_closes + [b["h"]], be, entry)
                lo = b["l"] < eff_stop(rest, prior + held_closes + [b["l"]], be, entry)
                if hi:
                    vv = True
                elif not lo:
                    vv = False
                else:
                    diag["nobar_ambiguous"] += 1
                    vv = b["c"] < eff_stop(rest, prior + held_closes + [b["c"]], be, entry)
                if vv:
                    sell(b["c"], rem)
                    return pnl / denom, "sold_1545_nobar"
        # the 16:45 job
        if b["l"] <= rest:
            _px = min(b["o"], rest) if b["o"] is not None else rest
            sell(_px, rem)
            diag.setdefault("stop_notional_r", []).append(_px * rem / denom)
            return pnl / denom, "stop_hit_daily"
        e = eff_stop(rest, prior + held_closes + [b["c"]], be, entry)
        held_closes.append(b["c"])
        if b["c"] < e:
            if timing == "close":
                sell(b["c"], rem)
                return pnl / denom, "close_below"
            nxt = next(((x, db[x]["o"]) for x in days if d < x <= horizon and db[x]["o"] is not None), None)
            if nxt is None:
                sell(b["c"], rem)
                return pnl / denom, "close_below_no_next"
            if timing == "open":
                diag["overnight"].append((nxt[1] - b["c"]) * rem / denom)
            diag.setdefault("open_notional_r", []).append(nxt[1] * rem / denom)
            sell(nxt[1], rem)
            return pnl / denom, ("next_open" if timing == "open" else "miss_next_open")
        line = max(line, e)


def main():
    global OUT
    OUT = open(HERE / "check_mech_recompute79.txt", "w")
    stored, keys79 = DP.load_stored()
    daily, held, mincov, H0m, states, day0 = DP.build_states()
    import csv
    dpt = {}
    with open(HERE.parent / "_685" / "depth_per_trade.tsv") as fh:
        for r in csv.DictReader(fh, delimiter="|"):
            dpt[(r["ticker"], date.fromisoformat(r["alert_date"]))] = r
    keys = sorted(keys79, key=lambda k: (k[1], k[0]))
    P(f"# independent recompute, 79 real EPs: keys {len(keys)}, day0-settled {sum(1 for k in keys if k in day0)}, "
      f"walked {sum(1 for k in keys if k in states)}")
    R, why, diags = {}, {}, {}
    import collections
    for arm in ("A0", "D10"):
        for t in ("close", "open", "1545", "1545mkt"):
            dg = collections.Counter()
            dg["overnight"] = []
            res, rs = {}, collections.Counter()
            for k in keys:
                if k in day0:
                    res[k] = day0[k]
                    rs["day0"] += 1
                    continue
                r, w = walk(arm, t, k, states[k], daily, held, DP.HORIZON, dg)
                res[k] = r
                rs[w] += 1
            R[(arm, t)] = res
            why[(arm, t)] = rs
            diags[(arm, t)] = dg
    bad = [(arm, k, R[(arm, "close")][k], dpt[k][f"{arm}_R"]) for arm in ("A0", "D10") for k in keys
           if R[(arm, "close")][k] is None or abs(R[(arm, "close")][k] - float(dpt[k][f"{arm}_R"])) > 0.005]
    P(f"## FIDELITY: my close-timing walker vs stored depth_per_trade.tsv A0_R/D10_R: mismatches {len(bad)}")
    for b_ in bad[:10]:
        P("   ", b_)
    for (arm, t), rs in why.items():
        tot = sum(v for v in R[(arm, t)].values() if v is not None)
        P(f"   {arm}-{t:8s} total {tot:+8.2f}  exits {dict(rs)}")
    base = R[("A0", "open")]
    for a in (("D10", "close"), ("D10", "open"), ("D10", "1545"), ("D10", "1545mkt")):
        diffs = [R[a][k] - base[k] for k in keys]
        srt = sorted(diffs)
        P(f"   {a[0]}-{a[1]} vs A0-open (today live): {sum(diffs):+.2f}R  without its top-2 {sum(diffs) - sum(srt[-2:]):+.2f}R  "
          f"better/worse {sum(1 for x in diffs if x > 0.005)}/{sum(1 for x in diffs if x < -0.005)}")
    dcc = sum(R[("D10", "close")][k] - R[("A0", "close")][k] for k in keys)
    P(f"   D10-close vs A0-close (the replay-vs-replay number): {dcc:+.2f}R")
    on = diags[("D10", "open")]["overnight"]
    P(f"   D10 next-open sales {len(on)}: next open minus close {sum(on):+.2f}R, better {sum(1 for x in on if x > 0.005)}, "
      f"worse {sum(1 for x in on if x < -0.005)}; A0 next-open sales {len(diags[('A0', 'open')]['overnight'])}")
    for h in (0.0044, 0.01, 0.0141):
        row = []
        for a in (("A0", "open"), ("D10", "open"), ("D10", "1545")):
            tot = sum(R[a][k] for k in keys) - h * sum(diags[a].get("open_notional_r", []))
            row.append(f"{a[0]}-{a[1]} {tot:+.2f}")
        P(f"   79 with a {h*100:.2f}% open-fill haircut on every next-open sale: " + " | ".join(row))
    for h in (0.0044, 0.01, 0.0141):
        row = []
        for a in (("A0", "open"), ("D10", "open"), ("D10", "1545")):
            tot = sum(R[a][k] for k in keys) - h * (sum(diags[a].get("open_notional_r", [])) + sum(diags[a].get("stop_notional_r", [])))
            row.append(f"{a[0]}-{a[1]} {tot:+.2f}")
        P(f"   79 SYMMETRIC {h*100:.2f}% haircut on every next-open sale AND every stop fill: " + " | ".join(row))
    vm = {k_: v for k_, v in diags[("D10", "close")].items() if k_ not in ("overnight", "open_notional_r", "stop_notional_r")}
    P(f"   15:45 vs close verdict on D10's close-timing path (bar days): {vm}")
    P(f"   no-bar ambiguous days D10-1545: {diags[('D10', '1545')]['nobar_ambiguous']}")
    # the named runners
    for k in (("FTK", date(2026, 8, 3)), ("INFQ", date(2026, 5, 21))):
        if k in R[("D10", "open")]:
            P(f"   {k[0]} {k[1]}: " + " ".join(f"{a}-{t} {R[(a, t)][k]:+.2f}" for a in ("A0", "D10")
                                           for t in ("close", "open", "1545", "1545mkt")))
    OUT.close()


if __name__ == "__main__":
    main()
