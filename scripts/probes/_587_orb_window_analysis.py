#!/usr/bin/env python3
"""#587 — ORB 9:45 window analysis. Reads the one-time prod capture
(_587_q*.psv, pulled 2026-08-23 by _587_orb_window_capture.sql) and prints
every number used in docs/analysis/orb_window_587_2026-08-23.md.

Measurement only. Nothing here changes any window, threshold or trade state.
"""
from __future__ import annotations

import csv
import re
import statistics as st
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
WINDOW_START = date(2026, 6, 24)   # 60 calendar days back from 2026-08-23
TWO_R_LIVE = date(2026, 8, 18)     # first live fill under the 2R stop (AMLX)


def load(name):
    with open(HERE / name, newline="") as f:
        return list(csv.DictReader(f, delimiter="|"))


def f(x):
    return float(x) if x not in (None, "") else None


def d(x):
    return date.fromisoformat(x)


# ── Load captures ────────────────────────────────────────────────────────────
q1 = load("_587_q1_oob.psv")
q2 = load("_587_q2_alerts.psv")
q3 = load("_587_q3_missed.psv")
q4 = load("_587_q4_trades.psv")
q5 = load("_587_q5_daily.psv")
q7 = load("_587_q7_minute_full.psv")

# Daily bars: ticker -> sorted [(date, open, high, low, close)]
daily = defaultdict(list)
for r in q5:
    daily[r["ticker"]].append((d(r["trade_date"]), f(r["open_price"]),
                               f(r["high_price"]), f(r["low_price"]), f(r["close"])))
for t in daily:
    daily[t].sort()

# Minute bars for the 25: (ticker, date) -> sorted [(HH:MM, o, h, l, c)]
minute = defaultdict(list)
for r in q7:
    day, hm = r["bar_et"].split(" ")
    minute[(r["ticker"], d(day))].append((hm, f(r["open"]), f(r["high"]),
                                          f(r["low"]), f(r["close"])))
for k in minute:
    minute[k].sort()

# Missed-outcomes rows keyed (ticker, date)
missed = {(r["ticker"], d(r["alert_date"])): r for r in q3}

# Earliest HIGH detection time per (ticker, date) from alerts
det_time = {}
for r in q2:
    if r["score_tier"] != "HIGH" or not r["detected_et"]:
        continue
    k = (r["ticker"], d(r["alert_date"]))
    t = r["detected_et"][11:16]
    if k not in det_time or t < det_time[k]:
        det_time[k] = t


def fwd_from_daily(ticker, d0):
    """Replicate missed_outcomes definitions from q5 daily bars.
    Returns dict or None if no d0 bar. Basis = d0 open."""
    bars = [b for b in daily.get(ticker, []) if b[0] >= d0]
    if not bars or bars[0][0] != d0 or not bars[0][1]:
        return None
    o0 = bars[0][1]
    def ret(n):  # close of d0+n trading days
        return (bars[n][4] - o0) / o0 if len(bars) > n else None
    def mh(n):   # max high over d0..d0+n (n+1 bars)
        w = bars[: n + 1]
        return (max(b[2] for b in w) - o0) / o0
    return {
        "open_d0": o0,
        "ret_1d": ret(1), "ret_5d": ret(5), "ret_20d": ret(20),
        "max_high_5d": mh(5) if len(bars) >= 1 else None,
        "max_high_20d": mh(20) if len(bars) >= 1 else None,
        "n_fwd_days": len(bars) - 1,
    }


# ── The 25 ───────────────────────────────────────────────────────────────────
oob = [r for r in q1 if d(r["alert_date"]) >= WINDOW_START]
print(f"=== out-of-orb rows in window (>= {WINDOW_START}): {len(oob)} "
      f"({len(set(r['ticker'] for r in oob))} tickers); all-time: {len(q1)}")

det_re = re.compile(r"detected (\d{2}:\d{2}) ET")
rows25 = []
for r in oob:
    t, ad = r["ticker"], d(r["alert_date"])
    dt = det_re.search(r["skip_reason"]).group(1)
    mo = missed.get((t, ad))
    fw = fwd_from_daily(t, ad)
    rows25.append({
        "ticker": t, "date": ad, "det": dt, "mode": r["account_mode"],
        "gap": f(r["gap_pct"]), "score": f(r["ep_score"]),
        "cat": r["catalyst_quality"], "mo": mo, "fw": fw,
    })
rows25.sort(key=lambda x: (x["date"], x["ticker"]))

print("\n=== the 25, named (outcome basis: d0 open, missed_outcomes definitions)")
hdr = ("ticker date       det   gap%  score cat          ret5d   mh5d   mh20d  ret20d  refreshed")
print(hdr)
for r in rows25:
    mo = r["mo"]
    def pc(v):
        return f"{100*v:+6.1f}" if v is not None else "   n/a"
    if mo:
        vals = (pc(f(mo["ret_5d"])), pc(f(mo["max_high_5d"])),
                pc(f(mo["max_high_20d"])), pc(f(mo["ret_20d"])),
                mo["refreshed_et"][:10])
    else:
        vals = ("MISSING", "", "", "", "")
    print(f"{r['ticker']:6} {r['date']} {r['det']} {r['gap']:5.1f} {r['score']:5.1f}"
          f" {r['cat'] or '?':12} {vals[0]} {vals[1]} {vals[2]} {vals[3]}  {vals[4]}")

# Cross-check q3 vs independent daily-bar computation
print("\n=== cross-check: mi_ep_missed_outcomes vs fresh compute from daily bars")
bad = 0
for r in rows25:
    mo, fw = r["mo"], r["fw"]
    if not mo or not fw:
        print(f"  {r['ticker']} {r['date']}: missing {'outcome row' if not mo else 'daily bars'}")
        bad += 1
        continue
    for k in ("ret_5d", "max_high_5d", "max_high_20d"):
        a, b = f(mo[k]), fw[k]
        if a is not None and b is not None and abs(a - b) > 0.005:
            print(f"  {r['ticker']} {r['date']} {k}: stored {a:+.4f} vs recomputed {b:+.4f}")
            bad += 1
if not bad:
    print("  all stored values match recomputation within 0.5pp (or are jointly n/a)")


# ── Cohort statistics helper ────────────────────────────────────────────────
def stats(name, recs, key_ret5="ret_5d", key_mh5="max_high_5d", key_mh20="max_high_20d"):
    r5 = [x[key_ret5] for x in recs if x.get(key_ret5) is not None]
    m5 = [x[key_mh5] for x in recs if x.get(key_mh5) is not None]
    m20 = [x[key_mh20] for x in recs if x.get(key_mh20) is not None]
    print(f"\n--- {name}: n={len(recs)} (ret5 settled n={len(r5)})")
    if r5:
        pos = sum(1 for v in r5 if v > 0)
        print(f"  ret_5d: median {100*st.median(r5):+.1f}%  mean {100*st.mean(r5):+.1f}%  "
              f"positive {pos}/{len(r5)}")
    if m5:
        print(f"  max_high_5d: median {100*st.median(m5):+.1f}%  "
              f">=10%: {sum(1 for v in m5 if v >= .10)}/{len(m5)}  "
              f">=20%: {sum(1 for v in m5 if v >= .20)}/{len(m5)}  "
              f">=30%: {sum(1 for v in m5 if v >= .30)}/{len(m5)}")
    if m20:
        print(f"  max_high_20d: median {100*st.median(m20):+.1f}%  "
              f">=20%: {sum(1 for v in m20 if v >= .20)}/{len(m20)}  "
              f">=50%: {sum(1 for v in m20 if v >= .50)}/{len(m20)}")
    if m20:
        top = sorted(m20, reverse=True)[:5]
        print(f"  top max_high_20d: {', '.join(f'{100*v:+.0f}%' for v in top)}")


def as_recs(rows):
    out = []
    for r in rows:
        mo = r.get("mo")
        fw = r.get("fw")
        src = {k: f(mo[k]) for k in ("ret_5d", "max_high_5d", "max_high_20d")} if mo else \
              ({k: fw[k] for k in ("ret_5d", "max_high_5d", "max_high_20d")} if fw else {})
        out.append(src)
    return out


# ── Entered cohort, same window ─────────────────────────────────────────────
entered = [r for r in q4 if r["filled_et"] and r["signal_type"] == "magna53"
           and d(r["alert_date"]) >= WINDOW_START]
# one row per (ticker, alert_date): prefer live over paper if both
seen = {}
for r in entered:
    k = (r["ticker"], d(r["alert_date"]))
    if k not in seen or r["account_mode"] == "live":
        seen[k] = r
entered = list(seen.values())
print(f"\n=== entered MAGNA53 trades in window: {len(entered)} "
      f"(modes: {sorted(set(r['account_mode'] for r in entered))})")

ent_recs = []
for r in entered:
    t, ad = r["ticker"], d(r["alert_date"])
    fw = fwd_from_daily(t, ad)
    dt = det_time.get((t, ad), "?")
    pnl = f(r["total_pnl"]) or 0.0
    risk = f(r["risk_dollars"])
    ent_recs.append({"ticker": t, "date": ad, "det": dt,
                     "status": r["status"], "pnl": pnl,
                     "risk": risk, "fw": fw, "mode": r["account_mode"]})

print("ticker date       det   status   pnl$    R      ret5d   mh5d   mh20d")
for r in sorted(ent_recs, key=lambda x: (x["date"], x["ticker"])):
    fw = r["fw"] or {}
    def pc(v):
        return f"{100*v:+6.1f}" if v is not None else "   n/a"
    rr = f"{r['pnl']/r['risk']:+5.2f}" if r["risk"] else "  n/a"
    print(f"{r['ticker']:6} {r['date']} {r['det']:5} {r['status']:8} "
          f"{r['pnl']:+8.2f} {rr} {pc(fw.get('ret_5d'))} {pc(fw.get('max_high_5d'))} "
          f"{pc(fw.get('max_high_20d'))}")

# name-quality comparison uses the SAME fwd basis for both cohorts
def fwrecs(rs):
    return [r["fw"] for r in rs if r["fw"]]

stats("REJECTED 25 (window_missed)", as_recs(rows25))
stats("ENTERED (all, same window)", fwrecs(ent_recs))

post_open_ent = [r for r in ent_recs if r["det"] != "?" and "09:31" <= r["det"] <= "09:44"]
pre_open_ent = [r for r in ent_recs if r["det"] != "?" and r["det"] < "09:31"]
stats(f"ENTERED subset detected 09:31-09:44 (closest analog)", fwrecs(post_open_ent))
stats(f"ENTERED subset detected pre-9:31", fwrecs(pre_open_ent))
print(f"\n  entered detection split: pre-open {len(pre_open_ent)}, "
      f"09:31-09:44 {len(post_open_ent)}, unknown {len(ent_recs)-len(pre_open_ent)-len(post_open_ent)}")

# realized R of entered cohort
closed = [r for r in ent_recs if r["status"] == "closed" and r["risk"]]
rs = [r["pnl"] / r["risk"] for r in closed]
if rs:
    print(f"  entered realized (closed n={len(closed)}): sum {sum(rs):+.1f}R, "
          f"median {st.median(rs):+.2f}R, winners>{0}: {sum(1 for v in rs if v > 0)}")

# ── Era split ────────────────────────────────────────────────────────────────
print("\n=== era split (2R stop live from 2026-08-18; selection rebuild deploys 08-23 → "
      "ALL rows are old-selection era)")
pre = [r for r in rows25 if r["date"] < TWO_R_LIVE]
post = [r for r in rows25 if r["date"] >= TWO_R_LIVE]
print(f"  rejected 25: pre-2R {len(pre)}, 2R-era {len(post)} "
      f"({', '.join(r['ticker'] for r in post)})")
epre = [r for r in ent_recs if r["date"] < TWO_R_LIVE]
epost = [r for r in ent_recs if r["date"] >= TWO_R_LIVE]
print(f"  entered: pre-2R {len(epre)}, 2R-era {len(epost)} "
      f"({', '.join(r['ticker'] for r in epost)})")
stats("REJECTED pre-2R", as_recs(pre))
stats("ENTERED pre-2R", fwrecs(epre))

# ── Tradability ─────────────────────────────────────────────────────────────
print("\n=== tradability at detection (minute bars; ORB = 09:30 bar)")
print("ticker date       det   orb_high  det_close  vs_orbH%  chase_preR2 chase_2R  "
      "retest<=H*1.005 after det?")
trad = []
for r in rows25:
    k = (r["ticker"], r["date"])
    bars = minute.get(k, [])
    orb = next((b for b in bars if b[0] == "09:30"), None)
    if not orb:
        print(f"{r['ticker']:6} {r['date']} {r['det']}  NO MINUTE BARS")
        trad.append({**r, "cov": False})
        continue
    H, L = orb[2], orb[3]
    det_bar = next((b for b in bars if b[0] >= r["det"]), None)
    det_close = det_bar[4]
    limit = det_close * 1.002
    # chase cap: limit - stop <= 1.5 * (orb_high - stop)
    stop_old, stop_2r = L, 2 * L - H
    ok_old = (limit - stop_old) <= 1.5 * (H - stop_old) if H > stop_old else False
    ok_2r = (limit - stop_2r) <= 1.5 * (H - stop_2r) if H > stop_2r else False
    after = [b for b in bars if b[0] > det_bar[0]]
    retest = next((b for b in after if b[3] <= H * 1.005), None)
    vs = 100 * (det_close - H) / H
    print(f"{r['ticker']:6} {r['date']} {r['det']}  {H:8.2f}  {det_close:9.2f}  {vs:+7.1f}  "
          f"{'pass' if ok_old else 'CAPPED':10} {'pass' if ok_2r else 'CAPPED':8}  "
          f"{retest[0] if retest else 'no (by close)'}")
    trad.append({**r, "cov": True, "H": H, "L": L, "det_close": det_close,
                 "vs": vs, "ok_old": ok_old, "ok_2r": ok_2r,
                 "retest": retest[0] if retest else None, "bars": bars,
                 "det_hm": det_bar[0]})

cov = [t for t in trad if t["cov"]]
above = [t for t in cov if t["det_close"] > t["H"]]
print(f"\n  coverage {len(cov)}/25; above ORB high at detection: {len(above)}/{len(cov)}; "
      f"median vs ORB high {st.median([t['vs'] for t in cov]):+.1f}%")
print(f"  chase-cap pass (pre-2R stop): {sum(1 for t in cov if t['ok_old'])}/{len(cov)}; "
      f"(2R stop): {sum(1 for t in cov if t['ok_2r'])}/{len(cov)}")
print(f"  ORB-high retest (stop-limit would fill on pullback) same day: "
      f"{sum(1 for t in cov if t['retest'])}/{len(cov)}")

# ── Counterfactual late-entry sim (labeled, pessimistic) ────────────────────
print("\n=== counterfactual sim — entry at detection close ×1.002, 2R stop "
      "(stop=2L−H), stop checked BEFORE target within a bar/day (pessimistic).")
print("    Exit rule simplified to: −1R if stop touched; else mark at close_d5. "
      "Reached +2R before stop also reported (the live partial target).")
print("ticker date       entry    stop    R/sh   outcome        reached+2R  maxR(5d)")
sim = []
for t in cov:
    E = t["det_close"] * 1.002
    S = 2 * t["L"] - t["H"]
    R = E - S
    if R <= 0:
        print(f"{t['ticker']:6} {t['date']}  degenerate geometry (E<=S), skipped")
        continue
    tgt = E + 2 * R
    # d0 minutes after detection
    path = [(b[2], b[3], b[4]) for b in t["bars"] if b[0] > t["det_hm"]]
    # d1..d5 daily
    dbars = [b for b in daily.get(t["ticker"], []) if b[0] > t["date"]][:5]
    path += [(b[2], b[3], b[4]) for b in dbars]
    stopped = hit2r = False
    maxhi = E
    final = path[-1][2] if path else E
    for hi, lo, cl in path:
        if not stopped and lo <= S:
            stopped = True   # pessimistic: stop first
        if not stopped:
            maxhi = max(maxhi, hi)
            if hi >= tgt:
                hit2r = True
        if stopped:
            break
    outR = -1.0 if stopped else (final - E) / R
    maxR = (maxhi - E) / R
    sim.append({"t": t["ticker"], "outR": outR, "hit2r": hit2r, "maxR": maxR,
                "stopped": stopped, "date": t["date"]})
    print(f"{t['ticker']:6} {t['date']}  {E:7.2f} {S:7.2f} {R:6.2f}  "
          f"{'stopped -1.0R' if stopped else f'hold5d {outR:+.1f}R':14} "
          f"{'YES' if hit2r else 'no ':10} {maxR:+.1f}")
if sim:
    tot = sum(s["outR"] for s in sim)
    print(f"\n  sim n={len(sim)}: stopped {sum(1 for s in sim if s['stopped'])}, "
          f"sum {tot:+.1f}R, reached +2R first {sum(1 for s in sim if s['hit2r'])}, "
          f"median maxR {st.median([s['maxR'] for s in sim]):+.1f}")

# ── Detection-minute distribution ───────────────────────────────────────────
mins = sorted(r["det"] for r in rows25)
print(f"\n=== detection minutes of the 25: {', '.join(mins)}")
print("    (scan cron = every 5 min; last in-window tick ≈ 9:40 + latency; "
      "a name first qualifying 9:41-9:45 lands on the 9:45 tick)")
