#!/usr/bin/env python3
"""#705 as-is read, STEP 6c: the account BAND against his stated numbers (docs/analysis/cb_asis_reconstruction_prereg_2026-10-26.md §4.3).
A FLOOR, NEVER A VERIFY — 6c has NO pass bar, and this printout says so in the plan's words. RULE-FREE BY CONSTRUCTION: no rule, setup name
or pattern label enters; the pinned step-5 / 6a / 6b modules are loaded read-only through asis_check_common.

WHAT IT DOES (per round trip = a position with a buy window and a sale window that both carry a range in ranges.tsv)
  readings  WORST (buy at the highest reachable price, sell at the lowest), BEST (the reverse), MIDDLE (the volume-weighted average price over
            the reachable minutes; a daily-only side takes each reachable session's typical price (high + low + close) / 3 weighted by volume,
            flagged — asis_check_common R77). In BAR space (R75); where 6b anchored a side on a clean stated price, that price (÷ raw_factor)
            replaces the middle on that side (the anchors arm).
  sizing    OUR convention (§4.3): equal weight across the names held at the same time — a CONSTANT MIX re-set every session, so the money
            deployed is exposure x account on every session and never more (R76; the first build sized each entry from the whole account
            and netted nothing, review F4); each trade is marked by session from the record's daily closes, entry price to exit price;
            every both-sided position held takes a slot in N, the 252 with no range included (their return enters as 0, a floor).
            Exposure 1.0 (middle) with 0.5 and 1.5 as the band arms; a position is SHORT when an own-trade statement joined to it OR placed
            beside it (mid-hold, a one-position tie) says so (R78, R87), long otherwise; flickers run in and out.
  readouts  (1) the middle path's year-to-date return at his 15 dated points with his figure beside; (2) the same with the T1 anchors; (3) the
            same on the windows shifted -3..+3 sessions (R1 control (a)) — a COUNT of the 15 points where the real windows sit closer to his
            figure than most shifted ones; (4) the 2021 drawdown 03-12 -> 03-24 as a shape; (5) the sizing and flicker arms as the spread.

STAGES  --dry-run    inputs, populations (round trips, resolutions, flickers, sides and anchors from 6b when present), the 15 points and the
                     convention; the claims -> 04_band_dryrun.txt ending 'DRY RUN COMPLETE'. NO account is compounded (R81). It prints
                     the sha of 03's run printout and of check_r1_r5.tsv as it saw them (ABSENT before 6b ran) — the gate checks that line.
        --print-pins -> 04_band_pins.txt (6b's pins, 03's run printout and outputs, this module, this dry run).
        --run        REFUSES (04_band.refused.txt) unless run_gate '6c' is clear — incl. 03's run printout carrying R1 and R5 at PASS (R79:
                     "if 6b fails, 6c is not read at all"), no pin reading ABSENT, and this dry run having seen the SAME 6b files that sit
                     on disk; otherwise writes band_by_session.tsv, band_at_dates.tsv, 04_band.txt and the step6c_* ledger rows.

ORDER (R79, review F3): 03 --run  ->  04 --dry-run (again, after 6b)  ->  04 --print-pins  ->  paste below the marker  ->  04 --run.
A 04 dry run or pins file made before 03 ran is stale by construction and the gate refuses it.

Run:  python3 scripts/probes/_705_asis_1026/04_band.py --dry-run | --print-pins | --run
No subagent, no network, no production server, no paid call, nothing after 2024-12-31, none of the seven outcome folders.
"""
from __future__ import annotations

import argparse
import collections
import csv
import importlib.util
import os
import statistics
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))


def _load_check_common():
    name, path = "asis_check_common", os.path.join(HERE, "asis_check_common.py")
    if name in sys.modules and getattr(sys.modules[name], "__file__", "") == path:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


K = _load_check_common()
C, P, CAP = K.C, K.P, K.CAP
Say, Claims, table, pct, fmt = K.Say, K.Claims, K.table, K.pct, K.fmt

SCAN_FILES = ("asis_common.py", "01_points.py", "02_captions.py", "asis_check_common.py", "03_check.py", "04_band.py")
ARMS = tuple((e, fl, an) for e in K.EXPOSURES for fl in ("flickers_in", "flickers_out") for an in ("middle", "anchored"))


def arm_name(e: float, fl: str, an: str) -> str:
    return f"x{e:g}_{fl}_{an}"


# ═════════════════════════════════════════════════════════════════════════════════════════════
# the trades
# ═════════════════════════════════════════════════════════════════════════════════════════════
def typical_price(w, bars) -> "float | None":
    """R77: the daily-only middle — each reachable session's (high + low + close) / 3 weighted by the session's volume, bar space."""
    if w is None or not w.reach:
        return None
    b, ix = bars.daily(w.export, w.bar_sym)
    if b is None:
        return None
    num = den = 0.0
    for d, _, _ in w.reach:
        j = ix.get(d)
        if j is None:
            continue
        v = C.fnum(b.v[j])
        num += (C.fnum(b.h[j]) + C.fnum(b.l[j]) + C.fnum(b.c[j])) / 3.0 * v
        den += v
    return (num / den) if den > 0 else None


def side_reading(row: dict, w, bars) -> "dict | None":
    """One side's three readings in bar space from its ranges.tsv row (None when the side has no range)."""
    if row is None or row.get("range_lo") in ("", None) or row.get("range_hi") in ("", None):
        return None
    lo, hi = float(row["range_lo"]), float(row["range_hi"])
    if row.get("avg_traded_price") not in ("", None):
        mid, src = float(row["avg_traded_price"]), "minute_vwap"
    else:
        mid, src = typical_price(w, bars), "daily_typical"
    if mid is None:
        return None
    return {"lo": lo, "hi": hi, "mid": mid, "mid_source": src}


def read_check(path: str = None) -> "list | None":
    """03's output when it exists (the anchors and the sides by statement); None before 6b has run."""
    path = path or K.OUT_6B["check_r1_r5"]
    if not os.path.exists(path):
        return None
    with open(C.checked(path), encoding="utf-8") as fh:
        return list(csv.DictReader(fh, delimiter="\t"))


def anchors_and_sides(check: "list | None") -> tuple:
    """-> ({(eid, side): bar-space anchor}, {eid: 'short'}) from 03's rows: the anchor is the row's anchor_price_bar on a uniquely joined
    row (R73); a position is short when any own-trade statement that NAMES it — joined uniquely, or placed beside it (`beside_eid`: mid-hold
    or a one-position tie) — says `short` or has the action shorted / covered (R78, R87)."""
    anchors, shorts = {}, {}
    for r in check or []:
        unique = r.get("join_status") == "unique" and bool(r.get("eid"))
        eid = int(r["eid"]) if unique else (int(r["beside_eid"]) if r.get("beside_eid") else None)
        if eid is None:
            continue
        if unique and r.get("anchor_price_bar") not in ("", None):
            anchors[(eid, r["side"])] = float(r["anchor_price_bar"])
        if (r.get("side_said") or "").strip().lower() == "short" or (r.get("action") or "").strip().lower() in ("shorted", "covered"):
            shorts[eid] = "short"
    return anchors, shorts


def marks_for(bars, export: str, bar_sym: str, entry: str, exit_: str, mid_entry: float, mid_exit: float, S) -> tuple:
    """R76: -> ([(session, value multiple of the entry price)] from the entry session to the exit session, source). The entry and interior
    sessions are marked at the record's close over the entry price (bar space, the buy side's export), the exit session at the exit price;
    a session with no close carries the previous mark. With no close at all on a hold longer than a session the return is spread
    geometrically ('geometric'); otherwise 'closes'."""
    b, ix = bars.daily(export, bar_sym)
    i0, i1 = S.le(entry), S.le(exit_)
    out, prev, any_close = [], 1.0, False
    for i in range(i0, i1 + 1):
        d = S.date(i)
        if i == i1:
            v = mid_exit / mid_entry
        else:
            j = ix.get(d) if ix else None
            c = C.fnum(b.c[j]) if j is not None else None
            if c is not None and c > 0:
                v, any_close = c / mid_entry, True
            else:
                v = prev
        out.append((d, v))
        prev = v
    if len(out) > 1 and not any_close:
        hold = [d for d, _ in out]
        g = (mid_exit / mid_entry) ** (1.0 / len(hold))
        return [(d, g ** (k + 1)) for k, d in enumerate(hold)], "geometric"
    return out, "closes"


def build_trades(ranges: dict, engine, anchors: dict, shorts: dict, S=None) -> tuple:
    """-> (trades, slots, counts). A trade: eid, sym, entry/exit sessions (R76), flicker, side, the two sides' readings, the returns of each
    arm and the daily returns of the middle and anchored arms (marked from the closes). A SLOT: a both-sided position with no range on a
    side — held, so it takes a place in N, with no return (R76)."""
    S = S or engine.S
    eids = sorted({e for (e, _s) in ranges})
    trades, slots, n = [], [], collections.Counter()
    for eid in eids:
        b, x = ranges.get((eid, "buy")), ranges.get((eid, "sale"))
        if b is None or x is None:
            n["one_side_only"] += 1
            continue
        n["round_trips"] += 1
        if b["hi"] > x["hi"]:
            n["exit_before_entry_end"] += 1
            continue
        rb = side_reading(b, engine.window(eid, "buy"), engine.bars)
        rx = side_reading(x, engine.window(eid, "sale"), engine.bars)
        if rb is None or rx is None:
            n["no_range_on_a_side"] += 1
            slots.append({"eid": eid, "sym": b["sym"], "entry_session": b["hi"], "exit_session": x["hi"], "flicker": b["flicker"] == "True", "daily": {}})
            continue
        side = shorts.get(eid, "long")
        n[side] += 1
        n["flicker"] += b["flicker"] == "True"
        n[f"mid_{rb['mid_source']}/{rx['mid_source']}"] += 1
        ab, ax = anchors.get((eid, "buy")), anchors.get((eid, "sale"))
        n["anchored_sides"] += (ab is not None) + (ax is not None)
        wb, wx = engine.window(eid, "buy"), engine.window(eid, "sale")
        n["export_mixed"] += (wb is not None and wx is not None and wb.export != wx.export)
        t = {"eid": eid, "sym": b["sym"], "entry_session": b["hi"], "exit_session": x["hi"], "flicker": b["flicker"] == "True", "side": side,
             "year": int(x["hi"][:4]), "buy": rb, "sale": rx, "anchor_buy": ab, "anchor_sale": ax}
        t["ret_middle"] = trade_return(rb["mid"], rx["mid"], side)
        t["ret_anchored"] = trade_return(ab if ab is not None else rb["mid"], ax if ax is not None else rx["mid"], side)
        t["ret_worst"] = trade_return(rb["hi"], rx["lo"], side) if side == "long" else trade_return(rb["lo"], rx["hi"], side)
        t["ret_best"] = trade_return(rb["lo"], rx["hi"], side) if side == "long" else trade_return(rb["hi"], rx["lo"], side)
        marks, src = marks_for(engine.bars, wb.export, wb.bar_sym, b["hi"], x["hi"], rb["mid"], rx["mid"], S)
        t["daily_middle"], t["marks_source"] = K.marks_to_daily(marks, side), src
        n[f"marks_{src}"] += 1
        marks_a, _ = marks_for(engine.bars, wb.export, wb.bar_sym, b["hi"], x["hi"], ab if ab is not None else rb["mid"], ax if ax is not None else rx["mid"], S)
        t["daily_anchored"] = K.marks_to_daily(marks_a, side)
        trades.append(t)
    return trades, slots, n


def trade_return(entry: float, exit_: float, side: str) -> float:
    """Long: exit / entry - 1; short: 1 - exit / entry (the cover against the short's entry)."""
    if not entry:
        return 0.0
    return (exit_ / entry - 1.0) if side == "long" else (1.0 - exit_ / entry)


def path_sessions(trades: list, S, pad: int = max(abs(k) for k in K.SHIFTS)) -> list:
    """The sessions the path is compounded on: from the first entry's year start to the last exit, padded by the widest shift on each end so
    a shifted trade (readout 3) still lands inside it; anything a shift pushes further out is dropped and counted (`within_sessions`)."""
    if not trades:
        return []
    first = min(t["entry_session"] for t in trades)
    last = max(t["exit_session"] for t in trades)
    i0 = S.le(first[:4] + "-01-01")
    i0 = i0 if S.date(i0) >= first[:4] + "-01-01" else i0 + 1
    return [S.date(i) for i in range(max(0, i0 - pad), min(len(S.cal) - 1, S.le(last) + pad) + 1)]


def within_sessions(trades: list, sessions: list) -> tuple:
    """-> (the trades whose entry and exit sessions are both on the path, the number dropped)."""
    have = set(sessions)
    kept = [t for t in trades if t["entry_session"] in have and t["exit_session"] in have]
    return kept, len(trades) - len(kept)


def arm_path(trades: list, sessions: list, e: float, fl: str, an: str, slots: list = ()) -> dict:
    """One arm's account path (R76): the trades' daily returns of the arm, the slots (held, no return) in N, flickers in or out of both."""
    ts = trades if fl == "flickers_in" else [t for t in trades if not t["flicker"]]
    sl = list(slots) if fl == "flickers_in" else [s for s in slots if not s["flicker"]]
    key = "daily_middle" if an == "middle" else "daily_anchored"
    return K.account_path([{"eid": t["eid"], "entry_session": t["entry_session"], "exit_session": t["exit_session"], "daily": t[key]} for t in ts]
                          + [{"eid": s["eid"], "entry_session": s["entry_session"], "exit_session": s["exit_session"], "daily": {}} for s in sl], sessions, e)


def shifted_slots(slots: list, S, k: int) -> list:
    """The slots moved k sessions (R66 applied to the held names with no range); a slot that leaves the calendar is dropped."""
    out = []
    for s in slots:
        a, b = S.le(s["entry_session"]) + k, S.le(s["exit_session"]) + k
        if 0 <= a and b < len(S.cal):
            out.append({"eid": s["eid"], "entry_session": S.date(a), "exit_session": S.date(b), "flicker": s["flicker"], "daily": {}})
    return out


# ═════════════════════════════════════════════════════════════════════════════════════════════
# readout (3): the shifted windows' middle path (R1 control (a) on the whole book)
# ═════════════════════════════════════════════════════════════════════════════════════════════
def shifted_trades(trades: list, engine, S, k: int, say) -> list:
    """Every trade's two windows shifted k sessions and re-ranged by 01_points' functions; the middle reading only (R66)."""
    t0 = time.time()
    ws, pairs = {}, set()
    for t in trades:
        for side in ("buy", "sale"):
            w2 = K.shifted_window(engine.window(t["eid"], side), k, S)
            if w2 is None:
                continue
            P.reachable(w2, S)
            P.assign_export(w2, engine.bars, engine.tally)
            ws[(t["eid"], side)] = w2
            if not w2.wide:
                pairs |= {(d, w2.bar_sym) for d, _, _ in w2.reach}
    engine.bars.store.preload(sorted(pairs))
    out, dropped = [], 0
    for t in trades:
        wb, wx = ws.get((t["eid"], "buy")), ws.get((t["eid"], "sale"))
        if wb is None or wx is None:
            dropped += 1
            continue
        rb = side_reading(engine.range_row(wb), wb, engine.bars)
        rx = side_reading(engine.range_row(wx), wx, engine.bars)
        if rb is None or rx is None or wb.hi > wx.hi:
            dropped += 1
            continue
        marks, _src = marks_for(engine.bars, wb.export, wb.bar_sym, wb.hi, wx.hi, rb["mid"], rx["mid"], S)
        out.append({"eid": t["eid"], "entry_session": wb.hi, "exit_session": wx.hi, "flicker": t["flicker"], "ret_middle": trade_return(rb["mid"], rx["mid"], t["side"]),
                    "daily": K.marks_to_daily(marks, t["side"])})
    say(f"- shift {k:+d}: {len(out):,} trades re-ranged, {dropped:,} dropped (no range or off the calendar); {len(pairs):,} pairs preloaded ({time.time() - t0:.0f}s)")
    return out


# ═════════════════════════════════════════════════════════════════════════════════════════════
# the printouts
# ═════════════════════════════════════════════════════════════════════════════════════════════
def report_populations(say, ranges: dict, trades: list, slots: list, counts: collections.Counter, check: "list | None", anchors: dict, shorts: dict, claims) -> None:
    say("\n## Populations")
    say(f"- ranges.tsv: {len(ranges):,} sides; positions {len({e for (e, _s) in ranges}):,}; round trips (both sides) {counts['round_trips']:,}; one side only {counts['one_side_only']:,}")
    say(f"- trades with a range on both sides: {len(trades):,}; held with no range on a side (a SLOT in N, no return; R76) {len(slots):,}; dropped: sale window ending "
        f"before the buy window {counts['exit_before_entry_end']:,}")
    say("- middle sources (buy/sale): " + ", ".join(f"{k[4:]} {v:,}" for k, v in sorted(counts.items()) if k.startswith("mid_")))
    say(f"- daily marks (R76): from the closes {counts['marks_closes']:,}, spread geometrically (no close on the hold) {counts['marks_geometric']:,}; "
        f"trades whose two sides sit in different exports (the last mark mixes their bar spaces, R75) {counts['export_mixed']:,}")
    say(f"- flickers among the trades: {counts['flicker']:,} (run in and out)")
    by_year = collections.Counter(t["year"] for t in trades)
    say("- trades by exit year: " + ", ".join(f"{y} {n:,}" for y, n in sorted(by_year.items())))
    if check is None:
        say("- 6b's output (check_r1_r5.tsv): ABSENT — sides by statement and anchors are 0 until 03 --run; every position reads long (R78)")
    else:
        say(f"- 6b's output: {len(check):,} statements; positions read SHORT by statement (joined or beside, R87) {len(shorts):,} ({pct(counts['short'], len(trades))} of the trades); "
            f"anchored sides {len(anchors):,} (on {counts['anchored_sides']:,} trade sides)")
    say(f"- sizing (OUR convention, §4.3; R76): a constant mix — on every session exposure x 1 / N in each of the N names held (trades + slots), the money "
        f"deployed never above exposure x account; exposure {' / '.join(f'{e:g}' for e in K.EXPOSURES)}; arms: {len(ARMS)} (exposure x flickers in/out x middle/anchored)")
    say("- his dated figures (§4.3, n = 15): " + "; ".join(f"{d} {fmt(lo, 0)}{'+' if hi is None else ('' if hi == lo else '-' + fmt(hi, 0))}%" for d, lo, hi in K.HIS_DATED_POINTS))
    say(f"- {K.LABEL_6C_FLOOR} 6c has NO pass bar (§4.3)")
    if claims is not None:
        say("\n## Claims (the plan)")
        eids = collections.defaultdict(set)
        for (e, sd) in ranges:
            eids[e].add(sd)
        claims("round trips (§2: 1,848)", 1848, sum(1 for v in eids.values() if len(v) == 2))
        claims("ranges.tsv sides (§3.1: 1,861 per side)", 3722, len(ranges))
        claims("his dated points (§4.3: n = 15)", 15, len(K.HIS_DATED_POINTS))
        claims("exposure arms (§4.3: 1.0 middle, 0.5 and 1.5 band)", [1.0, 0.5, 1.5], list(K.EXPOSURES))
        claims("every trade's exit session is on or after its entry session", 0, sum(1 for t in trades + slots if t["exit_session"] < t["entry_session"]))
        claims("every trade's middle lies inside its own worst..best band", 0,
               sum(1 for t in trades if not (min(t["ret_worst"], t["ret_best"]) - 1e-9 <= t["ret_middle"] <= max(t["ret_worst"], t["ret_best"]) + 1e-9)))
        claims("every long trade's daily marks compound to its middle return (R76)", 0,
               sum(1 for t in trades if t["side"] == "long" and abs(_compound(t["daily_middle"]) - t["ret_middle"]) > 1e-6))
        claims("trades + slots = the round trips whose sale window ends on or after the buy window's", counts["round_trips"] - counts["exit_before_entry_end"], len(trades) + len(slots))


def _compound(daily: dict) -> float:
    v = 1.0
    for r in daily.values():
        v *= 1.0 + r
    return v - 1.0


def report_readouts(say, trades: list, sessions: list, paths: dict, shifted: dict) -> tuple:
    """-> (rows at his dates, per-session rows)."""
    say("\n## Readouts (no pass bar)")
    mid, anc = paths[arm_name(1.0, "flickers_in", "middle")], paths[arm_name(1.0, "flickers_in", "anchored")]
    rows, at_rows = [], []
    for d, lo, hi in K.HIS_DATED_POINTS:
        his = f"{fmt(lo, 0)}{'+' if hi is None else ('' if hi == lo else '-' + fmt(hi, 0))}%"
        ym, ya = K.ytd(mid, sessions, d), K.ytd(anc, sessions, d)
        sh = {k: K.ytd(p, sessions, d) for k, p in shifted.items()}
        dm = K.distance_to_his(ym, lo, hi)
        closer = sum(1 for v in sh.values() if v is not None and dm is not None and dm < K.distance_to_his(v, lo, hi))
        rows.append([d, his, fmt(ym), fmt(ya), " ".join(f"{k:+d}:{fmt(v, 0)}" for k, v in sorted(sh.items())), f"{closer}/{len(sh)}"])
        at_rows.append({"date": d, "his_lo": lo, "his_hi": "" if hi is None else hi, "middle_ytd": fmt(ym, 4), "anchored_ytd": fmt(ya, 4),
                        **{f"shift_{k:+d}_ytd": fmt(v, 4) for k, v in sorted(sh.items())}, "real_closer_than_shifts": f"{closer}/{len(sh)}",
                        **{arm_name(*a) + "_ytd": fmt(K.ytd(paths[arm_name(*a)], sessions, d), 4) for a in ARMS}})
    say("### (1)-(3) the middle path's year-to-date return at his 15 dated points, the anchors arm, the shifted windows' paths")
    table(say, ["date", "his figure", "middle ytd %", "anchored ytd %", "shifted ytd % by k", "real closer than shifts"], rows)
    n_closer = sum(1 for r in rows if int(r[5].split("/")[0]) > int(r[5].split("/")[1]) // 2)
    say(f"- the real windows sit closer to his figure than MOST shifted paths at {n_closer} of {len(rows)} points (a count, not a bar: 15 correlated points)")
    d0, d1 = K.DRAWDOWN_2021
    v0, v1 = K.ytd(mid, sessions, d0), K.ytd(mid, sessions, d1)
    say(f"### (4) the 2021 drawdown {d0} -> {d1}: middle ytd {fmt(v0)}% -> {fmt(v1)}% ({'falls' if (v0 is not None and v1 is not None and v1 < v0) else 'does not fall'}; "
        f"his +120% -> +90-100% from a +130% peak)")
    say("### (5) the arms as the spread — year-end account multiple per arm")
    years = sorted({d[:4] for d in sessions})
    arm_rows = []
    for a in ARMS:
        p = paths[arm_name(*a)]
        arm_rows.append([arm_name(*a)] + [fmt(K.ytd(p, sessions, f"{y}-12-31")) for y in years])
    table(say, ["arm"] + [f"{y} ytd %" for y in years], arm_rows)
    say(f"- worst / best per trade (bar space): median worst {fmt(100 * statistics.median(t['ret_worst'] for t in trades))}%, median best "
        f"{fmt(100 * statistics.median(t['ret_best'] for t in trades))}%, median middle {fmt(100 * statistics.median(t['ret_middle'] for t in trades))}% over {len(trades):,} trades")
    say("- WOULD-FAIL-IF (§4.3): a wrong reconstruction and a correct-but-blind one produce the SAME shortfall; read with 6b only")
    per_session = [{"session": d, **{arm_name(*a): fmt(paths[arm_name(*a)][d], 6) for a in ARMS}, **{f"shift_{k:+d}": fmt(p.get(d), 6) for k, p in sorted(shifted.items())}}
                   for d in sessions]
    return at_rows, per_session


# ═════════════════════════════════════════════════════════════════════════════════════════════
# main
# ═════════════════════════════════════════════════════════════════════════════════════════════
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry-run", action="store_true")
    g.add_argument("--print-pins", action="store_true")
    g.add_argument("--run", action="store_true")
    a = ap.parse_args(argv)
    if a.print_pins:
        lines = [f"{k}\t{v}" for k, v in K.pins_6c().items()]
        print("\n".join(lines))
        with open(K.P04["pins"], "w", encoding="utf-8") as fh:
            fh.write("\n".join(lines) + "\n")
        print(f"(written to {K.P04['pins']})")
        return 0
    say = Say()
    refused_to = K.P04["dry"] if a.dry_run else K.P04["refused"]
    if not K.preamble(say, "6c (the account floor)", "DRY RUN" if a.dry_run else "RUN", SCAN_FILES, K.MODULE_FILES_6C, refused_to):
        return 2
    if a.run:
        problems = K.run_gate("6c")
        if problems:
            for pr in problems:
                say("REFUSED: " + pr)
            say.write(K.P04["refused"])
            return 3
        say("- run gates: the dry run completed with 0 MISMATCH by these modules; every pin is below the doc's freeze marker; the ledger verifies; "
            "03's run printout carries R1 and R5 at PASS; no output exists")
    say("\n## Inputs")
    ranges = K.read_ranges()
    say(f"- ranges.tsv {C.sha(K.RANGES)[:16]} ({len(ranges):,} sides)")
    check = read_check()
    say(K.LINE_6B_ARTEFACTS + K.artefacts_6b_line() + ("" if check is not None else "  (6b not run: this dry run is stale once it has; rerun it after 03 --run)"))
    tally = collections.Counter()
    L = P.load_all(say, tally)
    engine = K.RangeEngine(L)
    S = L["S"]
    anchors, shorts = anchors_and_sides(check)
    trades, slots, counts = build_trades(ranges, engine, anchors, shorts, S)
    claims = Claims(say) if a.dry_run else None
    report_populations(say, ranges, trades, slots, counts, check, anchors, shorts, claims)
    if a.dry_run:
        say("")
        say(claims.result())
        say("DRY RUN COMPLETE")
        say.write(K.P04["dry"])
        return 0
    sessions = path_sessions(trades, S)
    slots_on, off_slots = within_sessions(slots, sessions)
    say(f"\n## The path: {len(sessions):,} sessions {sessions[0]}..{sessions[-1]}, compounded by session; slots on the path {len(slots_on):,} ({off_slots} outside it)")
    paths = {arm_name(*arm): arm_path(trades, sessions, *arm, slots=slots_on) for arm in ARMS}
    P.preload_minutes(L, say)
    shifted = {}
    for k in K.SHIFTS:
        st, off = within_sessions(shifted_trades(trades, engine, S, k, say), sessions)
        sl, _off2 = within_sessions(shifted_slots(slots, S, k), sessions)
        if off:
            say(f"  - shift {k:+d}: {off} trades fall outside the path's sessions and are left out")
        shifted[k] = K.account_path([{"eid": t["eid"], "entry_session": t["entry_session"], "exit_session": t["exit_session"], "daily": t["daily"]} for t in st]
                                    + [{"eid": s["eid"], "entry_session": s["entry_session"], "exit_session": s["exit_session"], "daily": {}} for s in sl], sessions, 1.0)
    at_rows, per_session = report_readouts(say, trades, sessions, paths, shifted)
    K.write_tsv(at_rows, list(at_rows[0].keys()), K.OUT_6C["band_at_dates"])
    K.write_tsv(per_session, list(per_session[0].keys()), K.OUT_6C["band_by_session"])
    say("\n## Outputs")
    for k, p in K.OUT_6C.items():
        say(f"- {k}: {p} ({C.sha(p)[:16]})")
    say("RUN COMPLETE")
    say.write(K.P04["run"])
    C.ledger_append(K.STAGE_6C + "dry_run", K.P04["dry"])
    C.ledger_append(K.STAGE_6C + "band", K.P04["run"])
    for k, p in K.OUT_6C.items():
        C.ledger_append(K.STAGE_6C + k, p)
    return 0


if __name__ == "__main__":
    sys.exit(main())
