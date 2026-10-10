"""Adversarial re-derivation of docs/analysis/htf_scope_2026-10-10.md from the captured pulls.

Reads ONLY files already captured (../q*.out and ./v1_bars_and_drops.out). $0, no DB, no network.
Run: python scripts/probes/_htf_scope/verify/verify_htf_scope.py > .../verify/verify_out.txt
"""
from __future__ import annotations

import statistics as st
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
CAP = HERE.parent


def read_psv(p: Path):
    lines = [l.rstrip("\n") for l in p.read_text().splitlines()]
    hdr = lines[0].split("|")
    out = []
    for l in lines[1:]:
        if l.startswith("(") and l.endswith(")"):
            continue
        out.append(dict(zip(hdr, l.split("|"))))
    return out


def f(x):
    return float(x) if x not in ("", None) else None


print("=" * 78)
print("A. DAILY BOARD (q1) — 60 scan dates; medians exclude the 09-07 partial scan")
q1 = read_psv(CAP / "q1_daily_counts.out")
days = [r["scan_date"] for r in q1]
full = [r for r in q1 if r["scan_date"] != "2026-09-07"]
for col in ("total", "watch", "tight", "coiled", "trig"):
    v = [int(r[col]) for r in full]
    print(f"  {col:7s} median {st.median(v):6.1f}  mean {st.mean(v):5.2f}  min {min(v)} max {max(v)}")
print("  days tight==0:", sum(int(r["tight"]) == 0 for r in full), " of", len(full))
print("  days coiled>0:", sum(int(r["coiled"]) > 0 for r in full), " of", len(full))
print("  days trig>0:", sum(int(r["trig"]) > 0 for r in full), "  TRIGGERED rows:", sum(int(r["trig"]) for r in q1))
print("  scan dates:", days[0], "->", days[-1], "n =", len(days))

print("=" * 78)
print("B. STATE ROWS (q2) — distinct names, holds")
q2 = read_psv(CAP / "q2_state_rows.out")
names = defaultdict(set)
rows_by = Counter()
holds = Counter()
for r in q2:
    names[r["stage"]].add(r["ticker"])
    rows_by[r["stage"]] += 1
    if r["held_from_stage"]:
        holds[r["stage"]] += 1
for s in ("WATCH", "TIGHTENING", "COILED", "TRIGGERED", "INVALIDATED"):
    print(f"  {s:11s} rows {rows_by[s]:4d}  held {holds[s]:3d}  distinct names {len(names[s])}")
# raw (un-held) reads: a held row's raw stage is held_from_stage
raw_names = defaultdict(set)
for r in q2:
    raw = r["held_from_stage"] or r["stage"]
    raw_names[raw].add(r["ticker"])
print("  names with a RAW (un-held) read:", {k: len(v) for k, v in raw_names.items()})
print("  TIGHTENING names that ever stored COILED:", len(names["TIGHTENING"] & names["COILED"]),
      "  COILED names that ever stored TRIGGERED:", len(names["COILED"] & names["TRIGGERED"]))
real_trig = sorted((r["ticker"], r["scan_date"]) for r in q2 if r["stage"] == "TRIGGERED" and not r["held_from_stage"])
print("  real (un-held) TRIGGERED reads:", real_trig)
# held TIGHTENING (raw WATCH/other shown as TIGHTENING)
ht = [(r["ticker"], r["scan_date"], r["held_from_stage"]) for r in q2 if r["stage"] == "TIGHTENING" and r["held_from_stage"]]
print(f"  TIGHTENING rows that are holds: {len(ht)} of {rows_by['TIGHTENING']}; names {len({t for t,_,_ in ht})}")

print("=" * 78)
print("C. WATCH -> next scan day (q14 vs the 09-07-aware recount in v1)")
q14 = read_psv(CAP / "q14_watch_drop.out")
wn = [r for r in q14 if r["q"] == "watch_next"]
print("  q14 total WATCH rows with a next scan day:", sum(int(r["n"]) for r in wn))
v1 = [l.split("|") for l in (HERE / "v1_bars_and_drops.out").read_text().splitlines()[1:] if not l.startswith("(")]
drops = [x for x in v1 if x[0] == "watchdrop"]
art = [x for x in drops if x[4] == "2026-09-07" and x[3] == "2026-09-08"]
real = [x for x in drops if x not in art]
print(f"  drops as counted: {len(drops)} rows / {len({x[1] for x in drops})} names")
print(f"  of which 09-04 WATCH whose 'next scan' was the 87-name 09-07 partial and which HAD a 09-08 row: {len(art)} {[x[1] for x in art]}")
print(f"  drops excluding that artifact: {len(real)} rows / {len({x[1] for x in real})} names")

print("=" * 78)
print("D. NEXT ROW AFTER A PUSHABLE ROW (q11)")
q11 = read_psv(CAP / "q11_next_row.out")
nxt = Counter()
reset = []
for r in q11:
    if r["stage"] != "TIGHTENING":
        pass
    ns = r["ns"]
    na = r["na"]
    np_ = f(r["np"])
    p = f(r["pivot_high_price"])
    is_reset = na == "0" and np_ is not None and p is not None and np_ > p
    if is_reset:
        reset.append((r["ticker"], r["scan_date"], r["stage"], p, np_))
    if r["stage"] == "TIGHTENING":
        key = "base_age_0 pivot UP" if is_reset else (ns if ns != "unqualified" else "unq:" + r["nr"].split("_")[0])
        if r["nd"] == "":
            key = "no next row"
        nxt[key] += 1
print("  after TIGHTENING rows (n=%d):" % sum(nxt.values()), dict(nxt.most_common()))
print(f"  pushable rows whose next row is base_age_0 with a higher pivot: {len(reset)}")
for x in reset:
    print("    ", x)

print("=" * 78)
print("E. TIGHTENING EPISODES — doc's 'broke out' vs the TRIGGERED gate's own conditions")
bars = defaultdict(list)
rows = defaultdict(dict)
for x in v1:
    if x[0] == "bar":
        bars[x[1]].append(dict(d=x[2], o=float(x[3]), h=float(x[4]), l=float(x[5]), c=float(x[6]), v=float(x[7])))
    elif x[0] == "row":
        rows[x[1]][x[2]] = dict(stage=x[3], held=x[4], pivot=x[5], age=x[6], bh=f(x[7]), reason=x[8])
for t in bars:
    bars[t].sort(key=lambda b: b["d"])
ladder = days  # 60 scan dates

def episodes(stage):
    eps = []
    for t, rr in rows.items():
        cur = None
        for i, d in enumerate(ladder):
            r = rr.get(d)
            if r and r["stage"] == stage:
                if cur is None:
                    cur = dict(t=t, d0=d, days=[d])
                else:
                    cur["days"].append(d)
            elif d == "2026-09-07" and r is None and cur is not None:
                continue  # partial scan: absence is not an episode break
            else:
                if cur:
                    eps.append(cur)
                cur = None
        if cur:
            eps.append(cur)
    return eps

def gate_on(t, d, pivot):
    """TRIGGERED gate legs on bar date d for a base anchored at `pivot` (code lines 995-1011, 1210, 1255-1260)."""
    b = bars[t]
    idx = {x["d"]: i for i, x in enumerate(b)}
    if d not in idx or pivot not in idx:
        return None
    ti, pi = idx[d], idx[pivot]
    base = b[pi + 1: ti]
    if not base:
        return None
    bhc = max(x["c"] for x in base)
    win = min(5, len(base))
    rav = sum(x["v"] for x in base[-win:]) / win
    vr = b[ti]["v"] / rav if rav else None
    return dict(close=b[ti]["c"], bhc=bhc, vr=vr, price=b[ti]["c"] > bhc, vol=(vr or 0) >= 1.5)

tight = episodes("TIGHTENING")
print(f"  TIGHTENING episodes in window: {len(tight)}")
broke = []
for e in tight:
    t, d0 = e["t"], e["d0"]
    r0 = rows[t][d0]
    b = bars[t]
    idx = {x["d"]: i for i, x in enumerate(b)}
    if d0 not in idx:
        continue
    fwd = b[idx[d0] + 1: idx[d0] + 11]
    first = next((x for x in fwd if x["c"] > r0["bh"]), None)
    e["n10"] = len(fwd)
    if first:
        broke.append((e, first))
print(f"  episodes with a close > first-day base_high within 10 sessions: {len(broke)}")
buckets = Counter()
for e, first in broke:
    t, d0 = e["t"], e["d0"]
    piv = rows[t][d0]["pivot"]
    b = bars[t]
    idx = {x["d"]: i for i, x in enumerate(b)}
    fwd = b[idx[d0] + 1: idx[d0] + 11]
    trig_any = any(rows[t].get(x["d"], {}).get("stage") == "TRIGGERED" for x in fwd) or \
        any(rows[t].get(d, {}).get("stage") == "TRIGGERED" for d in e["days"])
    # same-anchor days: row on that day still carries the episode pivot (the board still has this base)
    gate_days, price_only_days, after_reset, other_gate_days = [], [], [], []
    for x in fwd:
        rr = rows[t].get(x["d"])
        same = rr is not None and rr["pivot"] == piv
        g = gate_on(t, x["d"], piv)
        if g is None:
            continue
        reached = rr is not None and rr["stage"] in ("WATCH", "TIGHTENING", "COILED", "TRIGGERED")  # an unqualified/INVALIDATED row early-returned before the TRIGGERED check
        if same and reached and g["price"] and g["vol"]:
            gate_days.append((x["d"], round(g["vr"], 2), rr["stage"], rr["held"]))
        elif same and g["price"] and g["vol"] and not reached:
            other_gate_days.append((x["d"], round(g["vr"], 2), rr["stage"], rr["reason"]))
        elif same and g["price"]:
            price_only_days.append((x["d"], round(g["vr"], 2)))
        elif (not same) and g["price"] and g["vol"]:
            after_reset.append((x["d"], round(g["vr"], 2), (rr or {}).get("stage", "NO ROW"), (rr or {}).get("pivot")))
    if trig_any:
        k = "registered TRIGGERED"
    elif gate_days:
        k = "COILED prerequisite was the ONLY missing leg"
    elif other_gate_days:
        k = "full price+volume met, but another gate rejected the row that day"
    elif price_only_days:
        k = "price leg met, VOLUME leg failed every same-base day"
    elif after_reset:
        k = "gate legs met only AFTER the base re-anchored / name off board (G3/G1)"
    else:
        k = "no day met the closing-price leg on the same base (first-day base_high crossed only)"
    buckets[k] += 1
    print(f"  {t:5s} ep {d0} ({len(e['days'])}d) first close>bh0 {first['d']} -> {k}")
    if gate_days:
        print(f"         gate days (date, vol ratio, stored stage, held_from): {gate_days}")
    if price_only_days and not gate_days:
        print(f"         price-only days (date, vol ratio): {price_only_days}")
    if other_gate_days and not gate_days:
        print(f"         other-gate days: {other_gate_days}")
    if after_reset and not gate_days:
        print(f"         after-reset gate days: {after_reset}")
print("  BUCKETS:", dict(buckets))

print("=" * 78)
print("F. CDNA by hand (q8-equivalent bars from v1)")
for d, piv in (("2026-08-25", "2026-08-03"), ("2026-09-17", "2026-08-27"), ("2026-09-22", "2026-08-27")):
    g = gate_on("CDNA", d, piv)
    print(f"  {d} on pivot {piv}: close {g['close']} > base_high_close {g['bhc']}? {g['price']}  vol ratio {g['vr']:.2f} (>=1.5? {g['vol']})"
          f"  stored row: {rows['CDNA'].get(d)}")

print("=" * 78)
print("G. HIT RATE on labelled HTFs (q4 rows) — pushable = stored TIGHTENING/COILED on label date or 5 prior scan days")
q4 = read_psv(CAP / "q4_corpus_rows.out")
cr = defaultdict(dict)
for r in q4:
    cr[r["ticker"]][r["scan_date"]] = r
alld = sorted({r["scan_date"] for r in q4} | set(days))
labels = [("CDNA", "2026-08-19"), ("CDNA", "2026-09-24"), ("HNGE", "2026-08-24"), ("MRNA", "2026-09-17"), ("MRNA", "2026-09-24")]
for t, d in labels:
    prior = [x for x in days if x <= d][-6:]
    seen = [(x, cr[t].get(x, {}).get("stage"), cr[t].get(x, {}).get("held_from_stage")) for x in prior]
    hit = [s for s in seen if s[1] in ("TIGHTENING", "COILED", "TRIGGERED")]
    raw_hit = [s for s in hit if not s[2]]
    print(f"  {t} {d}: window {prior[0]}..{prior[-1]} pushable rows {len(hit)} (un-held {len(raw_hit)}) {hit}")

print("=" * 78)
print("H. G4 coupling: does each real TRIGGERED read have an UN-HELD COILED inside its 5-calendar-day window?")
from datetime import date, timedelta
for t, d in real_trig:
    dd = date.fromisoformat(d)
    win = [(x["scan_date"], x["held_from_stage"]) for x in q2 if x["ticker"] == t and x["stage"] == "COILED"
           and dd - timedelta(days=5) <= date.fromisoformat(x["scan_date"]) < dd]
    print(f"  {t} {d}: COILED rows in window {win} -> un-held present: {any(not h for _, h in win)}")

print("=" * 78)
print("I. WDAY range% (q14 single-day (H-L)/C) — 20-session mean ending 09-08 and 09-11")
wd = [r for r in q14 if r["q"] == "wday_adr"]
wd.sort(key=lambda r: r["k"])
for end in ("2026-09-08", "2026-09-11"):
    upto = [float(r["n"]) for r in wd if r["k"] <= end][-20:]
    print(f"  ending {end}: n={len(upto)} mean {st.mean(upto):.2f}%")

print("=" * 78)
print("J. COILED blockers on the LAST TIGHTENING day of each episode (q2 metrics + MA alignment from bars)")
q2i = {(r["ticker"], r["scan_date"]): r for r in q2}
def sma(t, d, n):
    b = [x for x in bars[t] if x["d"] <= d][-n:]
    return sum(x["c"] for x in b) / n if len(b) == n else None
blk = Counter()
for e in tight:
    t, dl = e["t"], e["days"][-1]
    r = q2i.get((t, dl))
    if not r or r["held_from_stage"]:
        blk["last day is a HOLD (raw not TIGHTENING)"] += 1
        continue
    rt = f(r["range_contraction_ratio"]); vt = f(r["vol_contraction_ratio"])
    lb = f(r["last_body_pct"]); pb = f(r["prev_body_pct"])
    age = int(r["base_age"] or 0)
    c = next((x["c"] for x in bars[t] if x["d"] == dl), None)
    s10, s20 = sma(t, dl, 10), sma(t, dl, 20)
    fails = []
    if not (rt is not None and rt <= 0.75): fails.append("range")
    if not (vt is not None and vt <= 0.70): fails.append("vol")
    if not (lb is not None and pb is not None and lb <= 0.5 and pb <= 0.5): fails.append("bodies")
    if not (c and s10 and s20 and c >= s10 >= s20): fails.append("ma")
    if age < 6: fails.append("age<6")
    blk["+".join(fails) or "none(fresh path?)"] += 1
print("  ", dict(blk.most_common()), " n =", sum(blk.values()))
