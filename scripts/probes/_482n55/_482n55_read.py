#!/usr/bin/env python3
"""#482 n=55 re-read — 5-min ORB shadow lane vs live 1-min baseline (READ-ONLY).

Loads the one-shot prod capture (q1_capture.out, split into shadow.psv /
live.psv / fwd.psv). No prod access at run time. THE LINE holds: this
produces evidence only.

Findings doc: docs/analysis/482_bracket_geometry_n55_2026-09-01.md
"""
from __future__ import annotations

import csv
import json
import re
from collections import defaultdict
from pathlib import Path
from statistics import median

HERE = Path(__file__).resolve().parent


def load(name):
    with open(HERE / name) as f:
        rows = list(csv.DictReader(f, delimiter="|"))
    return [r for r in rows if not re.match(r"^\(\d+ rows?\)$", r[list(r)[0]] or "")]


def fnum(v):
    try:
        return float(v) if v not in (None, "",) else None
    except ValueError:
        return None


def era(d):  # alert_date string — system_review.py convention (#585):
    # _PROFIT_TRIGGER_ERA_START=2026-08-01, _STOP_GEOMETRY_ERA_START=2026-08-16.
    # C sub-split is POPULATION (admission), not exit: score rework 08-22, RS slot rank 08-30.
    if d < "2026-08-01":
        return "A <08-01 no-partial ORBlow-stop"
    if d < "2026-08-16":
        return "B 08-01..15 partial ORBlow-stop"
    if d < "2026-08-22":
        return "C1 08-16..21 2R-stop oldscore"
    if d < "2026-08-30":
        return "C2 08-22..29 2R-stop newscore"
    return "C3 08-30+ 2R-stop RSrank"


def stats(rs):
    if not rs:
        return "n=0"
    w = sum(1 for r in rs if r > 0.05)
    t4 = sum(1 for r in rs if r >= 4)
    return (f"n={len(rs)} sum={sum(rs):+.1f}R mean={sum(rs)/len(rs):+.2f}R "
            f"med={median(rs):+.2f}R win={w}/{len(rs)} ge4R={t4}")


shadow = load("shadow.psv")
live = load("live.psv")
fwd = load("fwd.psv")

# forward closes: per (ticker, alert_date) ordered list of (date, close)
fmap = defaultdict(list)
for r in fwd:
    fmap[(r["ticker"], r["alert_date"])].append((r["trade_date"], fnum(r["close"]),
                                                 fnum(r["high_price"])))


def fwd5(ticker, ad):
    """close 5 trading days after alert day; None if unavailable."""
    rows = fmap.get((ticker, ad), [])
    rows = [x for x in rows if x[0] >= ad]
    if len(rows) >= 6:
        return rows[0][1], rows[5][1]        # alert-day close, +5d close
    return (rows[0][1] if rows else None), None


print("=" * 78)
print("1. SHADOW LANE CENSUS (bar_size=5)")
print("=" * 78)
cen = defaultdict(int)
for r in shadow:
    q = "QUAR" if r["quarantined"] == "t" else "ok"
    cen[(q, r["status"], r["signal_type"])] += 1
for k in sorted(cen):
    print(f"  {k[0]:<5} {k[1]:<14} {k[2]:<10} {cen[k]}")

sh_closed = [r for r in shadow if r["status"] == "closed" and r["quarantined"] == "f"]
print(f"\nclosed non-quarantined total: {len(sh_closed)}")
for sig in ("magna53", "9m_day2"):
    sub = [r for r in sh_closed if r["signal_type"] == sig]
    rep = sum(1 for r in sub if r["was_replayed"] == "t")
    print(f"  {sig}: {len(sub)} ({rep} replayed from daily bars, {len(sub)-rep} real-time-accrued)")

# in-lane R for the magna53 shadow rows
sh = []
for r in sh_closed:
    if r["signal_type"] != "magna53":
        continue
    pnl, risk = fnum(r["total_pnl"]), fnum(r["risk_dollars"])
    if pnl is None or not risk:
        continue
    sh.append({"ticker": r["ticker"], "ad": r["alert_date"], "r": pnl / risk,
               "replayed": r["was_replayed"] == "t",
               "partial": r["partial_taken"] == "t",
               "entry": fnum(r["entry_price"]), "stop": fnum(r["stop_price"]),
               "orb_low": fnum(r["orb_low"]), "orb_high": fnum(r["orb_high"])})

print("\n" + "=" * 78)
print("2. 5-MIN LANE (magna53 only, closed, non-quarantined) — realized R")
print("=" * 78)
rs = [x["r"] for x in sh]
print("ALL   ", stats(rs))
for e in sorted({era(x["ad"]) for x in sh}):
    print(f"  {e:<36}", stats([x["r"] for x in sh if era(x["ad"]) == e]))
for m in sorted({x["ad"][:7] for x in sh}):
    print(f"  month {m:<30}", stats([x["r"] for x in sh if x["ad"][:7] == m]))
print("  replayed-only ", stats([x["r"] for x in sh if x["replayed"]]))
print("  realtime-only ", stats([x["r"] for x in sh if not x["replayed"]]))
big = sorted(sh, key=lambda x: -x["r"])[:8]
print("  top rows:", ", ".join(f"{x['ticker']} {x['ad']} {x['r']:+.2f}R"
                               f"{' (replay)' if x['replayed'] else ''}" for x in big))

print("\n" + "=" * 78)
print("3. LIVE 1-MIN BASELINE (magna53, closed, filled) — realized R")
print("=" * 78)
lv = []
for r in live:
    if r["status"] != "closed":
        continue
    pnl, risk = fnum(r["total_pnl"]), fnum(r["risk_dollars"])
    if pnl is None or not risk:
        continue
    lv.append({"ticker": r["ticker"], "ad": r["alert_date"], "r": pnl / risk,
               "mode": r["account_mode"], "attempt": r["entry_attempt"],
               "partial": r["partial_taken"] == "t",
               "entry": fnum(r["entry_price"])})
for mode in ("live", "paper"):
    sub = [x for x in lv if x["mode"] == mode]
    print(f"{mode.upper():<6}", stats([x["r"] for x in sub]))
    for e in sorted({era(x["ad"]) for x in sub}):
        print(f"  {e:<36}", stats([x["r"] for x in sub if era(x["ad"]) == e]))
for m in sorted({x["ad"][:7] for x in lv}):
    for mode in ("live", "paper"):
        sub = [x["r"] for x in lv if x["ad"][:7] == m and x["mode"] == mode]
        if sub:
            print(f"  month {m} {mode:<6}", stats(sub))

print("\n  re-entry rows (entry_attempt>1), the ONLY variant with real accrual:")
re2 = [x for x in lv if x["attempt"] not in ("1", "", None)]
print("  ", stats([x["r"] for x in re2]),
      "->", ", ".join(f"{x['ticker']} {x['ad']} {x['r']:+.2f}" for x in re2))

print("\n" + "=" * 78)
print("4. PAIRED — same ticker-day in BOTH lanes (closed+filled both sides)")
print("=" * 78)
lv_by = defaultdict(list)
for x in lv:
    lv_by[(x["ticker"], x["ad"])].append(x)
pairs = []
for x in sh:
    k = (x["ticker"], x["ad"])
    if k in lv_by:
        l = lv_by[k][0]  # first live row for the key
        pairs.append({"k": k, "sh_r": x["r"], "lv_r": l["r"], "mode": l["mode"],
                      "d": x["r"] - l["r"], "replayed": x["replayed"],
                      "sh_partial": x["partial"], "lv_partial": l["partial"]})
print(f"pairs n={len(pairs)}")
if pairs:
    ds = [p["d"] for p in pairs]
    print(f"  pair delta (5min − live): sum={sum(ds):+.2f}R median={median(ds):+.2f}R "
          f"5min better on {sum(1 for d in ds if d > 0.02)}/{len(ds)}")
    for e in sorted({era(p["k"][1]) for p in pairs}):
        sub = [p["d"] for p in pairs if era(p["k"][1]) == e]
        print(f"  {e:<36} n={len(sub)} sum={sum(sub):+.2f}R med={median(sub):+.2f}R")
    for mode in ("live", "paper"):
        sub = [p["d"] for p in pairs if p["mode"] == mode]
        if sub:
            print(f"  live-side mode={mode:<6} n={len(sub)} sum={sum(sub):+.2f}R med={median(sub):+.2f}R")
    pt = sum(1 for p in pairs if p["lv_partial"] and not p["sh_partial"])
    tp = sum(1 for p in pairs if p["sh_partial"] and not p["lv_partial"])
    bb = sum(1 for p in pairs if p["sh_partial"] and p["lv_partial"])
    print(f"  partial fired: both {bb} · live-only {pt} · 5min-only {tp} (mechanism-5 check)")
    print("  largest |delta| rows:")
    for p in sorted(pairs, key=lambda p: -abs(p["d"]))[:8]:
        print(f"    {p['k'][0]:<6} {p['k'][1]} 5min {p['sh_r']:+.2f} vs live {p['lv_r']:+.2f} "
              f"d={p['d']:+.2f} {'(replay)' if p['replayed'] else ''} mode={p['mode']}")

print("\n  ASYMMETRY (what each lane does on the other's entries):")
lv_keys = {(x["ticker"], x["ad"]) for x in lv}
sh_all_by = {(r["ticker"], r["alert_date"]): r for r in shadow
             if r["signal_type"] == "magna53" and r["quarantined"] == "f"}
miss = defaultdict(int)
for k in lv_keys:
    r = sh_all_by.get(k)
    miss[r["status"] if r else "NO SHADOW ROW"] += 1
print("  live closed+filled ticker-days, shadow status:", dict(miss))
sh_keys = {(x["ticker"], x["ad"]) for x in sh}
lv_all_by = defaultdict(list)
for r in live:
    lv_all_by[(r["ticker"], r["alert_date"])].append(r["status"])
miss2 = defaultdict(int)
for k in sh_keys:
    sts = lv_all_by.get(k)
    miss2[",".join(sorted(set(sts))) if sts else "NO LIVE ROW"] += 1
print("  shadow-entered ticker-days, live status:", dict(miss2))

print("\n" + "=" * 78)
print("5. #468b RE-TEST — losers vs what the stock did next (5 trading days)")
print("=" * 78)
for label, pop in (("LIVE lane losers", [x for x in lv if x["r"] < -0.05]),
                   ("5-MIN lane losers", [x for x in sh if x["r"] < -0.05])):
    for e in sorted({era(x["ad"]) for x in pop}):
        sub = [x for x in pop if era(x["ad"]) == e]
        up_e = dn_e = na = 0
        ups = []
        for x in sub:
            c0, c5 = fwd5(x["ticker"], x["ad"])
            ref = x["entry"] or c0
            if c5 is None or ref is None:
                na += 1
                continue
            pct = 100 * (c5 - ref) / ref
            if c5 > ref:
                up_e += 1
                ups.append((x["ticker"], x["ad"], pct))
            else:
                dn_e += 1
        n_res = up_e + dn_e
        print(f"  {label:<18} {e:<36} rose-past-entry {up_e}/{n_res}"
              f" (no-data {na})")
        if ups and n_res <= 40:
            print("      up:", ", ".join(f"{t} {d} +{p:.0f}%" for t, d, p in
                                         sorted(ups, key=lambda u: -u[2])[:10]))

print("\n" + "=" * 78)
print("6. TAIL — trades reaching >=4R realized, either lane")
print("=" * 78)
for label, pop in (("LIVE", lv), ("5-MIN", sh)):
    t = [x for x in pop if x["r"] >= 4]
    print(f"  {label}: {len(t)} of {len(pop)}",
          "->" if t else "", ", ".join(f"{x['ticker']} {x['ad']} {x['r']:+.1f}R" for x in t))


# ── PART 2 — definition-controlled #468b re-test + paired hygiene ──────────

def mfe5(ticker, ad):
    """(day0 close, +5-session settled close, max HIGH over sessions 1..5)."""
    rows = [x for x in fmap.get((ticker, ad), []) if x[0] >= ad]
    c0 = rows[0][1] if rows else None
    c5 = rows[5][1] if len(rows) >= 6 else None
    highs = [x[2] for x in rows[1:6] if x[2] is not None]
    return c0, c5, (max(highs) if highs else None)


# per-share risk for available-R (consistent with realized R = pnl/risk_dollars)
for pop, src in ((lv, live), (sh, [r for r in sh_closed if r["signal_type"] == "magna53"])):
    by_id = {}
for x in lv:
    x["psr"] = None
live_by_key = {}
for r in live:
    if r["status"] == "closed":
        live_by_key.setdefault((r["ticker"], r["alert_date"]), r)
for x in lv:
    r = live_by_key.get((x["ticker"], x["ad"]))
    if r:
        rd, es = fnum(r["risk_dollars"]), fnum(r["entry_shares"])
        x["psr"] = rd / es if rd and es else None
sh_by_key = {}
for r in sh_closed:
    if r["signal_type"] == "magna53":
        sh_by_key.setdefault((r["ticker"], r["alert_date"]), r)
for x in sh:
    r = sh_by_key.get((x["ticker"], x["ad"]))
    x["psr"] = None
    if r:
        rd, es = fnum(r["risk_dollars"]), fnum(r["entry_shares"])
        x["psr"] = rd / es if rd and es else None

print("\n" + "=" * 78)
print("5b. #468b RE-TEST, DEFINITION-CONTROLLED (losers = realized R < -0.05)")
print("    orig metric = MFE: max HIGH of next 5 sessions vs day-0 CLOSE")
print("=" * 78)
for label, pop, modes in (("1-MIN lane (live$)", [x for x in lv if x["mode"] == "live"], 1),
                          ("1-MIN lane (paper)", [x for x in lv if x["mode"] == "paper"], 1),
                          ("5-MIN lane", sh, 1)):
    losers = [x for x in pop if x["r"] < -0.05]
    for e in sorted({era(x["ad"]) for x in losers}):
        sub = [x for x in losers if era(x["ad"]) == e]
        mfe_up = settled_up = entry_up = n_ok = 0
        avail2 = avail4 = n_avail = 0
        for x in sub:
            c0, c5, mh = mfe5(x["ticker"], x["ad"])
            if c0 is None or mh is None:
                continue
            n_ok += 1
            if mh > c0:
                mfe_up += 1                       # the ORIGINAL definition
            if c5 is not None and c0 and c5 > c0:
                settled_up += 1                   # settled close vs day-0 close
            if c5 is not None and x["entry"] and c5 > x["entry"]:
                entry_up += 1                     # settled close vs our entry
            if x["psr"] and x["entry"] and mh is not None:
                n_avail += 1
                ar = (mh - x["entry"]) / x["psr"]
                if ar >= 2:
                    avail2 += 1
                if ar >= 4:
                    avail4 += 1
        print(f"  {label:<20} {e:<34} losers n={len(sub)} (data {n_ok})")
        print(f"      MFE>close0 (orig defn): {mfe_up}/{n_ok} · settled c5>c0: {settled_up}/{n_ok}"
              f" · settled c5>entry: {entry_up}/{n_ok}")
        print(f"      within 5d the stock offered >=2R past our entry: {avail2}/{n_avail}"
              f" · >=4R: {avail4}/{n_avail}")

print("\n" + "=" * 78)
print("7. PAIRED HYGIENE — SYRE artifact + realtime-vs-replay split")
print("=" * 78)
p_nosyre = [p for p in pairs if p["k"][0] != "SYRE"]
ds = [p["d"] for p in p_nosyre]
print(f"  pairs excl SYRE: n={len(ds)} sum={sum(ds):+.2f}R median={median(ds):+.2f}R "
      f"5min better on {sum(1 for d in ds if d > 0.02)}/{len(ds)}")
for lab, subp in (("realtime-accrued shadow", [p for p in p_nosyre if not p["replayed"]]),
                  ("daily-bar replay shadow", [p for p in p_nosyre if p["replayed"]])):
    if subp:
        dd = [p["d"] for p in subp]
        print(f"  {lab:<26} n={len(dd)} sum={sum(dd):+.2f}R med={median(dd):+.2f}R")

print("\n" + "=" * 78)
print("8. BOTH DIRECTIONS (P14) — what each lane misses")
print("=" * 78)
print("  Of live closed+filled ticker-days, by the 5-min lane's verdict on the SAME day:")
for st in ("closed", "gate_blocked", "no_entry", None):
    if st is None:
        sub = [x for x in lv if sh_all_by.get((x["ticker"], x["ad"])) is None]
        lab = "NO SHADOW ROW"
    else:
        sub = [x for x in lv
               if (sh_all_by.get((x["ticker"], x["ad"])) or {}).get("status") == st]
        lab = st
    if sub:
        print(f"    5min={lab:<13}", stats([x["r"] for x in sub]),
              "| live winners here:",
              ", ".join(f"{x['ticker']} {x['r']:+.1f}" for x in sub if x["r"] > 0.5) or "none")
print("\n  Of 5-min-entered ticker-days where live has NO closed fill:")
sub = [x for x in sh if not any(r["status"] == "closed"
       for r in live if (r["ticker"], r["alert_date"]) == (x["ticker"], x["ad"]))]
print("   ", stats([x["r"] for x in sub]),
      "->", ", ".join(f"{x['ticker']} {x['ad']} {x['r']:+.1f}" for x in
                      sorted(sub, key=lambda x: -x["r"])[:6]))

print("\n" + "=" * 78)
print("9. LIVE-MODE AUGUST BY EXIT/POPULATION ERA (the one positive month)")
print("=" * 78)
for e in sorted({era(x["ad"]) for x in lv if x["ad"][:7] == "2026-08" and x["mode"] == "live"}):
    sub = [x["r"] for x in lv if x["ad"][:7] == "2026-08" and x["mode"] == "live"
           and era(x["ad"]) == e]
    print(f"  {e:<36}", stats(sub))
print("  open live trades not in any table above:",
      sum(1 for r in live if r["status"] == "open"), "(status=open, excluded everywhere)")
