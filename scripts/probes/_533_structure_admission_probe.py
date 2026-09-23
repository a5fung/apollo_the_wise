#!/usr/bin/env python3
"""#533 — "What is a REAL EP" structure/admission probe (READ-ONLY; STUDY ONLY).

Operator reframe 2026-08-12 (docs/methodology/operator_shared_notes.md §2026-08-12):
a gap is the SIGNAL that an EP might be there, not the EP itself. Question = ADMISSION
("was this alert a real EP at all?"), NOT ranking. THE LINE: this changes NO detection
criterion, no threshold, no code path. Measurement only.

Outcome variable = the ALERT (not the fill): forward return / MFE / MAE at 1/3/5/10
trading days from alert-day OPEN, computed from mi_daily_closes bars — every alert
including skips and stop-outs (the mi_ep_missed_outcomes shape, re-derived so entered
names are included under one convention).

Inputs (captured ONCE from prod 2026-08-12, per COST EFFICIENCY rule):
  _533_alerts.tsv     one row per (ticker, alert_date), HIGH+MODERATE, 2026-05-11..08-11,
                      DISTINCT ON keeping max ep_score; LATERAL join to latest
                      mi_stock_scores row strictly BEFORE alert_date
                      (query: scratchpad _533_q1.sql, reproduced in the findings section
                      of docs/roadmap/ep_profitability_program.md 2026-08-12).
  _533_bars.tsv       mi_daily_closes full retention (2025-07-07..2026-08-11) for all
                      cohort tickers.
  _533_livetrades.tsv mi_live_trades account_mode='live', 19 closed + 2 open (filled).

Features per alert (all computed from bars STRICTLY BEFORE alert day, except the
gap-day OPEN which is the 9:30 print — knowable at decision time):
  A. structure position:  prev_close vs SMA10/20/50 (bar-computed as-of t-1)
  B. key levels:          open vs prior 20d/60d/all-available high; overhead density
                          (frac of last 120 bars whose high >= gap-day open)
  C. neglect:             vol_5d/vol_50d, days since last |>=5%| daily move,
                          prev_close distance below all-available high, 20d pre-return
  D. existing:            gap_pct, ep_score, catalyst grade, rs_composite, rs_rank

Populations reported separately (operator addition 2026-08-12): ALL alerts pooled
(admission — n=1 sessions included) · within-session multi-alert days (choosing) ·
the 19 closed live losers + 2 open winners as labelled cases.
"""
from __future__ import annotations

import math
from collections import defaultdict
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
ALERTS = HERE / "_533_alerts.tsv"
BARS = HERE / "_533_bars.tsv"
TRADES = HERE / "_533_livetrades.tsv"

# ---------- load ----------
def f(x):
    try:
        return float(x)
    except (ValueError, TypeError):
        return None

bars = defaultdict(list)  # ticker -> [(date, o,h,l,c,v)]
for ln in BARS.read_text().splitlines():
    p = ln.split("|")
    if len(p) < 7:
        continue
    bars[p[0]].append((p[1], f(p[2]), f(p[3]), f(p[4]), f(p[5]), f(p[6])))
for t in bars:
    bars[t].sort()
bidx = {t: {r[0]: i for i, r in enumerate(rs)} for t, rs in bars.items()}

alerts = []
for ln in ALERTS.read_text().splitlines():
    p = ln.split("|")
    if len(p) < 15:
        continue
    alerts.append(dict(
        ticker=p[0], d=p[1], tier=p[2], ep_score=f(p[3]), gap=f(p[4]), cq=p[5],
        det=p[6], sdate=p[7], rs=f(p[8]), rank=f(p[9]),
        s10=f(p[10]), s20=f(p[11]), s50=f(p[12]), sclose=f(p[13]), adv=f(p[14])))

trades = {}
for ln in TRADES.read_text().splitlines():
    p = ln.split("|")
    if len(p) >= 4:
        trades[(p[0], p[1])] = dict(status=p[2], pnl=f(p[3]))

# ---------- features + outcomes ----------
LOOK = 120
for a in alerts:
    t, d = a["ticker"], a["d"]
    rs = bars.get(t, [])
    i = bidx.get(t, {}).get(d)
    a["has_bar"] = i is not None
    if i is None or i == 0:
        continue
    prior = rs[max(0, i - LOOK):i]           # up to 120 bars strictly before t
    closes = [r[4] for r in prior]
    a["nprior"] = i                           # total bars available before t
    o = rs[i][1]
    a["open"] = o
    pc = rs[i - 1][4]
    a["prev_close"] = pc
    # A. SMAs from bars as-of t-1
    for k in (10, 20, 50):
        if i >= k:
            sma = sum(r[4] for r in rs[i - k:i]) / k
            a[f"sma{k}"] = sma
            a[f"abv{k}"] = pc > sma
    if all(f"abv{k}" in a for k in (10, 20, 50)):
        a["abv_all"] = a["abv10"] and a["abv20"] and a["abv50"]
        a["blw_all"] = (not a["abv10"]) and (not a["abv20"]) and (not a["abv50"])
    # B. key levels (vs gap-day open)
    if o:
        hs = [r[2] for r in prior if r[2] is not None]
        if len(prior) >= 20:
            a["clears20"] = o > max(r[2] for r in prior[-20:])
        if len(prior) >= 60:
            a["clears60"] = o > max(r[2] for r in prior[-60:])
        if hs:
            hi_all = max(h for h in (r[2] for r in rs[:i]) if h is not None)
            a["clears_all"] = o > hi_all          # gaps through every prior high we hold
            a["dist_allhigh_open"] = o / hi_all - 1
            a["overhead"] = sum(1 for h in hs if h >= o) / len(hs)  # congestion above open
    # C. neglect
    vols = [r[5] for r in prior if r[5] is not None]
    if len(vols) >= 50:
        a["volratio"] = (sum(vols[-5:]) / 5) / (sum(vols[-50:]) / 50)
    big = None
    for j in range(len(closes) - 1, 0, -1):
        if closes[j - 1] and abs(closes[j] / closes[j - 1] - 1) >= 0.05:
            big = len(closes) - 1 - j
            break
    a["days_since_big"] = big if big is not None else (len(closes) if len(closes) >= 2 else None)
    if closes:
        hi_all_c = max(h for h in (r[2] for r in rs[:i]) if h is not None) if any(r[2] for r in rs[:i]) else None
        if hi_all_c:
            a["dist_below_high"] = pc / hi_all_c - 1
    if i >= 21:
        a["ret20"] = pc / rs[i - 21][4] - 1
    # outcomes, ref = alert-day open
    if o:
        a["day0"] = rs[i][4] / o - 1
        for k in (1, 3, 5, 10):
            if i + k < len(rs):
                a[f"fwd{k}"] = rs[i + k][4] / o - 1
        fw5 = rs[i + 1:i + 6]
        if len(fw5) == 5 and all(r[2] and r[3] for r in fw5):
            a["mfe5"] = max(r[2] for r in fw5) / o - 1
            a["mae5"] = min(r[3] for r in fw5) / o - 1
            a["ran5"] = a["mfe5"] >= 0.05
        fw10 = rs[i + 1:i + 11]
        if len(fw10) == 10 and all(r[2] for r in fw10):
            a["mfe10"] = max(r[2] for r in fw10) / o - 1

# ---------- stats helpers (stdlib only) ----------
def med(xs):
    xs = sorted(xs)
    n = len(xs)
    if n == 0:
        return None
    return xs[n // 2] if n % 2 else (xs[n // 2 - 1] + xs[n // 2]) / 2

def ranks(xs):
    order = sorted(range(len(xs)), key=lambda i: xs[i])
    rk = [0.0] * len(xs)
    i = 0
    while i < len(xs):
        j = i
        while j + 1 < len(xs) and xs[order[j + 1]] == xs[order[i]]:
            j += 1
        r = (i + j) / 2 + 1
        for k2 in range(i, j + 1):
            rk[order[k2]] = r
        i = j + 1
    return rk

def mw_z(a_, b_):
    """Mann-Whitney rank-sum z (normal approx, tie-corrected denominator omitted — fine at these n)."""
    n1, n2 = len(a_), len(b_)
    if n1 < 3 or n2 < 3:
        return None
    rk = ranks(list(a_) + list(b_))
    r1 = sum(rk[:n1])
    u = r1 - n1 * (n1 + 1) / 2
    mu = n1 * n2 / 2
    sd = math.sqrt(n1 * n2 * (n1 + n2 + 1) / 12)
    return (u - mu) / sd if sd else None

def spearman(pairs):
    xs = [p[0] for p in pairs]
    ys = [p[1] for p in pairs]
    if len(xs) < 5:
        return None
    rx, ry = ranks(xs), ranks(ys)
    mx, my = sum(rx) / len(rx), sum(ry) / len(ry)
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    den = math.sqrt(sum((a - mx) ** 2 for a in rx) * sum((b - my) ** 2 for b in ry))
    return num / den if den else None

def sess(rows):
    return len({r["d"] for r in rows})

def pct(x):
    return f"{100 * x:+.1f}%"

# ---------- report ----------
HIGH = [a for a in alerts if a["tier"] == "HIGH" and a.get("has_bar")]
MOD = [a for a in alerts if a["tier"] == "MODERATE" and a.get("has_bar")]
nobar = [a for a in alerts if not a.get("has_bar")]

print(f"cohort: {len(alerts)} alert ticker-days 2026-05-11..08-11 "
      f"({len(HIGH)} HIGH / {len(MOD)} MODERATE with bars; {len(nobar)} no alert-day bar)")
print(f"HIGH sessions: {sess(HIGH)}; alerts with full 5d-forward: "
      f"{sum(1 for a in HIGH if 'fwd5' in a)} over {sess([a for a in HIGH if 'fwd5' in a])} sessions")
print(f"insufficient history (<50 prior bars, SMA50/vol undefined): "
      f"{sum(1 for a in HIGH if a.get('nprior', 0) < 50)} of {len(HIGH)} HIGH")
print()

def split(rows, key, label, out="fwd5"):
    A = [r for r in rows if r.get(key) is True and out in r]
    B = [r for r in rows if r.get(key) is False and out in r]
    if not A or not B:
        print(f"{label}: insufficient data (yes={len(A)} no={len(B)})")
        return
    za = mw_z([r[out] for r in A], [r[out] for r in B])
    ra = [r for r in A if "ran5" in r]
    rb = [r for r in B if "ran5" in r]
    print(f"{label}")
    print(f"  YES n={len(A)} ({sess(A)} sess): median {out} {pct(med([r[out] for r in A]))}, "
          f"P(high>=+5% in 5d) {sum(r['ran5'] for r in ra)}/{len(ra)}"
          f"  | NO n={len(B)} ({sess(B)} sess): median {pct(med([r[out] for r in B]))}, "
          f"P {sum(r['ran5'] for r in rb)}/{len(rb)}"
          f"  | rank z={za:+.2f}" if za is not None else "")

print("=== A. STRUCTURE POSITION (HIGH cohort, pooled admission view) ===")
split(HIGH, "abv_all", "prev close ABOVE all of SMA10/20/50 vs not")
split(HIGH, "blw_all", "prev close BELOW all three SMAs vs not")
split(HIGH, "abv50", "above SMA50 vs not")
split(HIGH, "abv20", "above SMA20 vs not")
print()
print("=== B. KEY LEVELS — what the gap CLEARS (HIGH) ===")
split(HIGH, "clears20", "open CLEARS prior 20d high vs lands inside")
split(HIGH, "clears60", "open CLEARS prior 60d high vs lands inside")
split(HIGH, "clears_all", "open CLEARS all-available prior high (blue sky) vs lands inside")
oh = [(a["overhead"], a["fwd5"]) for a in HIGH if "overhead" in a and "fwd5" in a]
print(f"overhead congestion density (frac of last 120 bars traded >= open): "
      f"spearman vs fwd5 = {spearman(oh):+.2f} (n={len(oh)})")
lo = [a for a in HIGH if a.get("overhead") is not None and a["overhead"] <= 0.10 and "fwd5" in a]
hi_ = [a for a in HIGH if a.get("overhead") is not None and a["overhead"] > 0.50 and "fwd5" in a]
print(f"  clean overhead (<=10% of bars above): n={len(lo)} ({sess(lo)} sess) median fwd5 {pct(med([r['fwd5'] for r in lo]))}"
      f"  vs heavy (>50%): n={len(hi_)} ({sess(hi_)} sess) median {pct(med([r['fwd5'] for r in hi_]))}")
print()
print("=== C. NEGLECT BEFORE THE GAP (HIGH) ===")
for key, lab in [("volratio", "prior 5d/50d volume ratio"),
                 ("days_since_big", "days since last >=5% daily move"),
                 ("dist_below_high", "prev close distance below all-time-available high"),
                 ("ret20", "20d pre-gap return")]:
    pr = [(a[key], a["fwd5"]) for a in HIGH if a.get(key) is not None and "fwd5" in a]
    print(f"{lab}: spearman vs fwd5 = {spearman(pr):+.2f} (n={len(pr)})")
print()
print("=== D. THE FEATURES WE ALREADY HAVE (HIGH) ===")
for key, lab in [("gap", "gap %"), ("ep_score", "ep_score"), ("rs", "RS composite"),
                 ("rank", "RS rank (lower=stronger)")]:
    pr = [(a[key], a["fwd5"]) for a in HIGH if a.get(key) is not None and "fwd5" in a]
    print(f"{lab}: spearman vs fwd5 = {spearman(pr):+.2f} (n={len(pr)})")
for grade in ("game_changer", "strong", "routine"):
    g = [a for a in HIGH if a["cq"] == grade and "fwd5" in a]
    if g:
        print(f"grade={grade}: n={len(g)} ({sess(g)} sess) median fwd5 {pct(med([r['fwd5'] for r in g]))}, "
              f"P(ran5) {sum(r.get('ran5', False) for r in g)}/{sum(1 for r in g if 'ran5' in r)}")
print()
print("=== MFE/MAE by structure (HIGH, 5d) ===")
for key, lab in [("abv_all", "above all 3 SMAs"), ("blw_all", "below all 3 SMAs")]:
    A = [a for a in HIGH if a.get(key) is True and "mfe5" in a]
    if A:
        print(f"{lab}: n={len(A)} ({sess(A)} sess) median MFE5 {pct(med([r['mfe5'] for r in A]))} "
              f"median MAE5 {pct(med([r['mae5'] for r in A]))}")
print()
print("=== WITHIN-SESSION (choosing view): multi-alert HIGH days with both buckets ===")
wins = losses = ties = 0
days = []
for d in sorted({a["d"] for a in HIGH}):
    day = [a for a in HIGH if a["d"] == d and "fwd5" in a]
    A = [a["fwd5"] for a in day if a.get("abv_all") is True]
    B = [a["fwd5"] for a in day if a.get("abv_all") is not True]
    if A and B:
        ma, mb = med(A), med(B)
        days.append((d, len(A), len(B), ma, mb))
        if ma > mb:
            wins += 1
        elif ma < mb:
            losses += 1
        else:
            ties += 1
print(f"sessions with >=1 above-all-3 AND >=1 not: {len(days)}")
print(f"above-all-3 bucket beat the rest (median fwd5): {wins} sessions; lost: {losses}; tied: {ties}")
for d, na, nb, ma, mb in days:
    print(f"  {d}: above n={na} med {pct(ma)}  vs rest n={nb} med {pct(mb)}")
print()
print("=== MODERATE robustness (above-all-3 split) ===")
split(MOD, "abv_all", "MODERATE: above all 3 SMAs vs not")
print()
print("=== LABELLED CASES: 19 closed live losers + 2 open winners ===")
hdr = f"{'ticker':<6} {'date':<11} {'pnl':>8}  {'abv10/20/50':<12} {'clears20/60/all':<16} {'ovhd':>5} {'volr':>5} {'rank':>5} {'gap%':>6} {'fwd5':>7} {'mfe5':>7}"
print(hdr)
al_by_key = {(a["ticker"], a["d"]): a for a in alerts}
n_struct = n_nostruct = 0
for (tk, dd), tr in sorted(trades.items(), key=lambda kv: kv[0][1]):
    a = al_by_key.get((tk, dd))
    if not a:
        print(f"{tk:<6} {dd:<11} {tr['pnl']:>8.2f}  -- no alert row in cohort --")
        continue
    ab = "".join("Y" if a.get(f"abv{k}") else ("N" if a.get(f"abv{k}") is False else "?") for k in (10, 20, 50))
    cl = "".join("Y" if a.get(k2) else ("N" if a.get(k2) is False else "?") for k2 in ("clears20", "clears60", "clears_all"))
    ov = f"{a['overhead']:.2f}" if a.get("overhead") is not None else "?"
    vr = f"{a['volratio']:.1f}" if a.get("volratio") is not None else "?"
    rk = f"{int(a['rank'])}" if a.get("rank") is not None else "?"
    fw = pct(a["fwd5"]) if "fwd5" in a else "?"
    mf = pct(a["mfe5"]) if "mfe5" in a else "?"
    print(f"{tk:<6} {dd:<11} {tr['pnl']:>8.2f}  {ab:<12} {cl:<16} {ov:>5} {vr:>5} {rk:>5} {a['gap']:>6.1f} {fw:>7} {mf:>7}")
    if tr["status"] == "closed":
        if a.get("abv_all"):
            n_struct += 1
        elif a.get("abv_all") is False:
            n_nostruct += 1
print(f"\nclosed losers with prev close above all 3 SMAs: {n_struct}; not above all 3: {n_nostruct}")
base = [a for a in HIGH if a.get("abv_all") is not None]
print(f"cohort base rate above-all-3 (HIGH): {sum(a['abv_all'] for a in base)}/{len(base)}")

# ---------- PART 2: adversarial check — session-mix confound ----------
print()
print("=== PART 2: SESSION CONFOUND CHECK (is the pooled reverse-separation just the tape?) ===")
smed = {}
for d in {a["d"] for a in HIGH}:
    xs = [a["fwd5"] for a in HIGH if a["d"] == d and "fwd5" in a]
    if xs:
        smed[d] = med(xs)
for a in HIGH:
    if "fwd5" in a and a["d"] in smed:
        a["fwd5_dm"] = a["fwd5"] - smed[a["d"]]

print("month mix (HIGH with fwd5): month | n | median fwd5 | share above-all-3")
bym = defaultdict(list)
for a in HIGH:
    if "fwd5" in a:
        bym[a["d"][:7]].append(a)
for m in sorted(bym):
    rows = bym[m]
    ab = [a for a in rows if a.get("abv_all") is not None]
    print(f"  {m}: n={len(rows)} ({sess(rows)} sess) median fwd5 {pct(med([r['fwd5'] for r in rows]))}, "
          f"above-all-3 {sum(a['abv_all'] for a in ab)}/{len(ab)}")
print()
print("session-demeaned splits (fwd5 minus own-session median):")
split(HIGH, "abv_all", "  above all 3 SMAs (demeaned)", out="fwd5_dm")
split(HIGH, "clears60", "  clears prior 60d high (demeaned)", out="fwd5_dm")
split(HIGH, "clears_all", "  clears all-available high (demeaned)", out="fwd5_dm")
oh2 = [(a["overhead"], a["fwd5_dm"]) for a in HIGH if "overhead" in a and "fwd5_dm" in a]
print(f"  overhead density: spearman vs demeaned fwd5 = {spearman(oh2):+.2f} (n={len(oh2)})")
vr2 = [(a["volratio"], a["fwd5_dm"]) for a in HIGH if a.get("volratio") is not None and "fwd5_dm" in a]
print(f"  prior 5d/50d volume ratio: spearman vs demeaned fwd5 = {spearman(vr2):+.2f} (n={len(vr2)})")
g2 = [(a["gap"], a["fwd5_dm"]) for a in HIGH if a.get("gap") is not None and "fwd5_dm" in a]
print(f"  gap %: spearman vs demeaned fwd5 = {spearman(g2):+.2f} (n={len(g2)})")
print()
print("horizon check — above-all-3 split on fwd10 and MFE10 (pooled):")
split(HIGH, "abv_all", "  above all 3 SMAs vs not (fwd10)", out="fwd10")
A10 = [a for a in HIGH if a.get("abv_all") is True and "mfe10" in a]
B10 = [a for a in HIGH if a.get("abv_all") is False and "mfe10" in a]
if A10 and B10:
    print(f"  MFE10: above n={len(A10)} median {pct(med([r['mfe10'] for r in A10]))}"
          f"  vs not n={len(B10)} median {pct(med([r['mfe10'] for r in B10]))}")
