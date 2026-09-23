#!/usr/bin/env python3
"""#571 position sizing — consumes scripts/probes/_571_sizing_capture_out.psv (ONE prod capture).
Read-only, $0. Computes intended vs realized dollar risk per closed live trade."""
import math, statistics as st

CAP = "/Users/alvinfung/apollo_the_wise/scripts/probes/_571_sizing_capture_out.psv"
sections, cur = {}, None
for line in open(CAP):
    line = line.rstrip("\n")
    if line.startswith("===") and line.endswith("==="):
        cur = line.strip("="); sections[cur] = []
    elif cur and line and not line.startswith("(") :
        sections[cur].append(line.split("|"))

hdr = sections["Q1_LIVE_BOOK"][0]
rows = [dict(zip(hdr, r)) for r in sections["Q1_LIVE_BOOK"][1:]]
snaps = {r[0]: float(r[1]) for r in sections["Q2_EQUITY_SNAPSHOTS"][1:]}
snap_dates = sorted(snaps)

def f(x):
    try: return float(x)
    except: return None

def prior_snap(d):  # equity snapshot strictly before alert_date (the 16:12 close before entry)
    prior = [s for s in snap_dates if s < d]
    return snaps[prior[-1]] if prior else None

closed = [r for r in rows if r["status"] == "closed"]
openpos = [r for r in rows if r["status"] == "filled"]
print(f"closed={len(closed)} open={len(openpos)} cancelled={sum(1 for r in rows if r['status']=='cancelled')} skipped={sum(1 for r in rows if r['status']=='skipped')}")

def era(r):  # 2R era iff hard_stop == 2*orb_low - orb_high (tolerance), else ORB-low era
    oh, ol, hs = f(r["orb_high"]), f(r["orb_low"]), f(r["hard_stop"])
    if None in (oh, ol, hs): return "?"
    return "2R" if abs(hs - (2*ol - oh)) < 0.02 else ("ORBlow" if abs(hs - ol) < 0.02 else "OTHER")

print(f"\n{'tkr':5} {'date':10} {'era':6} {'regime':10} {'eq_prev':7} {'budget':6} {'bud%eq':6} "
      f"{'sh':4} {'planned$':8} {'actual$':8} {'act/bud':7} {'act/1%':6} {'binder':8} {'pnl':8} {'R(bud)':6}")
agg = []
for r in closed + openpos:
    oh, ol, hs = f(r["orb_high"]), f(r["orb_low"]), f(r["hard_stop"])
    ep, sh, bud, pnl = f(r["entry_price"]), f(r["entry_shares"]), f(r["risk_dollars"]), f(r["total_pnl"])
    eq = prior_snap(r["alert_date"])
    rps_plan = oh - hs            # spec-time per-share risk (ORB high -> hard stop)
    rps_fill = ep - hs            # actual per-share risk at the placed stop, from the real fill
    planned = sh * rps_plan
    actual = sh * rps_fill
    # binder: what limited shares? uncapped = floor(bud/rps_plan); cap = floor(0.2*eq/oh)
    unc = math.floor(bud / rps_plan)
    binder = "cap" if sh < unc else ("budget" if unc*rps_plan > bud*0.85 else "round")
    # rounding loss vs budget when budget-bound
    if sh >= unc: binder = "budget" if (bud - unc*rps_plan)/bud < 0.15 else "round"
    e = era(r)
    onepct = 0.01 * eq if eq else None
    agg.append(dict(t=r["ticker"], d=r["alert_date"], era=e, reg=r["regime"], eq=eq, bud=bud,
                    sh=sh, planned=planned, actual=actual, pnl=pnl, binder=binder,
                    status=r["status"], onepct=onepct))
    print(f"{r['ticker']:5} {r['alert_date']:10} {e:6} {r['regime']:10} {eq:7.0f} {bud:6.2f} "
          f"{100*bud/eq:5.2f}% {sh:4.0f} {planned:8.2f} {actual:8.2f} {actual/bud:7.2f} "
          f"{actual/onepct:6.2f} {binder:8} {pnl:8.2f} {pnl/bud:6.2f} {r['status']}")

cl = [a for a in agg if a["status"] == "closed"]
pre = [a for a in cl if a["era"] == "ORBlow"]; post = [a for a in cl if a["era"] == "2R"]
print(f"\n--- closed cohort: n={len(cl)}  pre-2R={len(pre)}  2R={len(post)}")
for name, grp in [("ALL closed", cl), ("pre-2R", pre), ("2R era (closed)", post)]:
    if not grp: continue
    ab = [a["actual"]/a["bud"] for a in grp]
    a1 = [a["actual"]/a["onepct"] for a in grp]
    print(f"{name}: actual/budget median {st.median(ab):.2f} mean {st.mean(ab):.2f} min {min(ab):.2f} max {max(ab):.2f}"
          f" | actual/(1% eq) median {st.median(a1):.2f} | actual$ median {st.median(a['actual'] for a in grp):.2f}"
          f" mean {st.mean(a['actual'] for a in grp):.2f}")
print(f"binders (closed): { {b: sum(1 for a in cl if a['binder']==b) for b in set(a['binder'] for a in cl)} }")
print(f"sum pnl closed: {sum(a['pnl'] for a in cl):.2f}   winners: {[(a['t'],round(a['pnl'],2)) for a in cl if a['pnl']>0]}")
print(f"losers n={sum(1 for a in cl if a['pnl']<0)} sum={sum(a['pnl'] for a in cl if a['pnl']<0):.2f} "
      f"median loss {st.median(a['pnl'] for a in cl if a['pnl']<0):.2f}")
print(f"open realized so far: {[(a['t'],a['era'],round(a['pnl'],2)) for a in agg if a['status']=='filled']}")
print(f"budget as % of 1%eq (closed, by month): ")
for a in cl: pass
# spread intended(1%) vs booked budget vs actual
sp = [(a["t"], a["d"], round(a["onepct"],2), round(a["bud"],2), round(a["actual"],2)) for a in cl]
print(f"total intended(1%eq) {sum(x[2] for x in sp):.0f} vs booked budget {sum(x[3] for x in sp):.0f} vs actual-at-stop {sum(x[4] for x in sp):.0f}")
