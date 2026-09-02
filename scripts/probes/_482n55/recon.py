#!/usr/bin/env python3
import csv, re
from statistics import median
def load(name):
    rows = list(csv.DictReader(open(name), delimiter="|"))
    return [r for r in rows if not re.match(r"^\(\d+ rows?\)$", r[list(r)[0]] or "")]
def f(v):
    try: return float(v) if v not in (None,"") else None
    except ValueError: return None
live = load("live.psv"); fwd = load("fwd.psv")
from collections import defaultdict
fmap = defaultdict(list)
for r in fwd: fmap[(r["ticker"], r["alert_date"])].append((r["trade_date"], f(r["close"]), f(r["high_price"])))
lv = [r for r in live if r["status"]=="closed" and f(r["total_pnl"]) is not None and f(r["risk_dollars"])]
print("live-mode closed magna53, R = pnl/risk_dollars vs pnl/risk_dollars_actual:")
for mode in ("live","paper"):
    sub = [r for r in lv if r["account_mode"]==mode]
    r1 = [f(r["total_pnl"])/f(r["risk_dollars"]) for r in sub]
    r2 = [f(r["total_pnl"])/(f(r["risk_dollars_actual"]) or f(r["risk_dollars"])) for r in sub]
    na = sum(1 for r in sub if not f(r["risk_dollars_actual"]))
    print(f"  {mode}: n={len(sub)} planned-risk mean {sum(r1)/len(r1):+.3f}R "
          f"actual-risk mean {sum(r2)/len(r2):+.3f}R (rows lacking actual: {na}) "
          f"win {sum(1 for x in r1 if x>0.05)}/{len(r1)}")
# the losers that offered >=4R within 5 sessions
print("\nlosers whose stock offered >=2R past entry within 5 sessions (per-share risk = risk$/shares):")
for r in lv:
    rr = f(r["total_pnl"])/f(r["risk_dollars"])
    if rr >= -0.05: continue
    e, rd, es = f(r["entry_price"]), f(r["risk_dollars"]), f(r["entry_shares"])
    if not (e and rd and es): continue
    psr = rd/es
    rows = [x for x in fmap.get((r["ticker"], r["alert_date"]),[]) if x[0] >= r["alert_date"]]
    highs = [x[2] for x in rows[1:6] if x[2] is not None]
    if not highs: continue
    ar = (max(highs)-e)/psr
    if ar >= 2:
        print(f"  {r['ticker']:<6} {r['alert_date']} mode={r['account_mode']:<5} realized {rr:+.2f}R "
              f"avail {ar:+.1f}R (entry {e}, mfe5 {max(highs)})")
