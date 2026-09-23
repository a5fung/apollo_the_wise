#!/usr/bin/env python3
"""first_live_winner review — the cost of a profit-take rule, priced on the FIRST two
live MAGNA53 green closes (PLTR 307, ETON 367).  MEASUREMENT ONLY.

THE LINE: read-only, offline. Changes no rule, no threshold, no trade state.

Inputs (captured once, 2026-08-24, read-only prod):
  _508e_winner_capture_out.psv   trades / exit legs / orders / audit
  _508e_winner_bars_out.csv      COMPLETE RTH minute bars, PLTR 08-04..08-20, ETON 08-14
  _508e_winner_fwd_daily.psv     forward daily bars (post-close path)
  _508e_winner_2026-08-24/*.tsv  the 2026-08-22 replay snapshot (verified == prod today)
"""
from __future__ import annotations
import csv, importlib.util, sys
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
SNAP = HERE / "_508e_winner_2026-08-24"

spec = importlib.util.spec_from_file_location("replay508", HERE / "_508_exit_rule_replay.py")
replay = importlib.util.module_from_spec(spec); sys.modules["replay508"] = replay
spec.loader.exec_module(replay)
replay.HERE = SNAP

W = {307: "PLTR", 367: "ETON"}
ORB = {307: (148.63, 143.28), 367: (55.4427, 53.01)}   # (orb_high, orb_low)

def bars():
    txt = (HERE / "_508e_winner_bars_out.csv").read_text().split("\n", 1)[1]
    return list(csv.DictReader(txt.splitlines()))

def line(c="-"): print(c * 96)

B = bars()
trades = {t.rec["trade_id"]: t for t in replay.load()}

print("=" * 96)
print("first_live_winner — what a profit-take rule COST on the two live green closes (2026-08-24)")
print("=" * 96)

# ── 1. TRUE HIGH-WATER MARK from complete RTH minute bars ────────────────────
line("=")
print("1. TRUE HIGH-WATER MARK — reconstructed minute by minute (not the recorded peak)")
line()
hwm = {}
for tid, tkr in W.items():
    t = trades[tid]
    fd, cd = t.rec["fill_day"], t.rec["close_day"]
    fill_hhmm = t.rec["filled_at"].astimezone(replay.ET).strftime("%H:%M")
    close_hhmm = t.rec["closed_at"].astimezone(replay.ET).strftime("%H:%M")
    rows = [r for r in B if r["ticker"] == tkr
            and fd.isoformat() <= r["et"][:10] <= cd.isoformat()
            and not (r["et"][:10] == fd.isoformat() and r["et"][11:] < fill_hhmm)
            and not (r["et"][:10] == cd.isoformat() and r["et"][11:] > close_hhmm)]
    top = max(rows, key=lambda r: float(r["high"]))
    hwm[tid] = (float(top["high"]), top["et"])
    e, rps = t.entry, t.risk
    print(f"  {tkr} (id {tid})  entry ${e:.4f}  ORB-R ${rps:.4f}  shares {t.rec['entry_shares']:.0f}"
          f"  hold {fd} {fill_hhmm} -> {cd} {close_hhmm} ET")
    print(f"     minute bars in hold : {len(rows)}   (recorder used {t.rec['peak_bars_n']})")
    print(f"     TRUE in-hold HWM    : ${float(top['high']):.4f} at {top['et']} ET"
          f"  = +{(float(top['high'])-e)/rps:.4f} ORB-R")
    print(f"     recorded peak_price : ${t.rec['peak_price']:.4f}  (+{t.rec['peak_r']:.4f} R)"
          f"   -> {'MATCHES' if abs(float(top['high'])-t.rec['peak_price'])<0.005 else 'DIFFERS'}")
    print(f"     unrealised $ at HWM : ${(float(top['high'])-e)*t.rec['entry_shares']:+.2f}"
          f"   booked ${t.rec['realized_pnl']:+.2f}"
          f"   give-back ${(float(top['high'])-e)*t.rec['entry_shares']-t.rec['realized_pnl']:+.2f}")
    print()

# ── 2. WHAT ACTUALLY HAPPENED — the observed legs ────────────────────────────
line("=")
print("2. WHAT THE DEPLOYED +2R PARTIAL ACTUALLY DID (observed legs — no model)")
line()
for tid, tkr in W.items():
    t = trades[tid]
    oh, ol = ORB[tid]
    tgt = t.entry + 2 * (t.entry - ol)
    print(f"  {tkr}: ORB H ${oh} L ${ol}   +2R target (ORB-anchored) = ${tgt:.4f}"
          f"  = +{(tgt-t.entry)/t.risk:.2f} ORB-R")
    for lg in t.legs:
        et = lg["time"].astimezone(replay.ET).strftime("%m-%d %H:%M")
        print(f"     {et} ET  {lg['reason']:<15} {lg['shares']:>4.0f} sh @ ${lg['price']:>9.4f}"
              f"  = {(lg['price']-t.entry)/t.risk:+.3f} R/sh")
    print()

# ── 3. PLTR — the clean observed cost ────────────────────────────────────────
line("=")
print("3. PLTR — the ONE clean observed price for a profit-take rule")
line()
t = trades[307]; e, rps, sh = t.entry, t.risk, 6
r_dollar = rps * sh
partial_px, term_px = 165.6895, 170.3875
tgt = e + 2 * (e - 143.28)
print(f"  1R on the whole position = ${r_dollar:.3f}   (ORB-R ${rps:.4f}/sh x {sh} sh)")
print(f"  do-nothing ride: all {sh} sh exit on the trail stop @ ${term_px}  "
      f"= ${(term_px-e)*sh:+.2f} = {(term_px-e)/rps:+.3f} R")
print(f"     (the ORB-low stop $143.28 was never touched after the fill — post-fill low "
      f"${min(float(r['low']) for r in B if r['ticker']=='PLTR' and r['et'][:10]>='2026-08-05'):.2f};")
print(f"      the trail is price-driven, so its ladder is identical at 6 sh or 4 sh)")
print(f"  as-run       : 2 sh @ ${partial_px} + 4 sh @ ${term_px} = ${t.rec['realized_pnl']:+.2f}"
      f" = {t.rec['realized_r']:+.4f} R")
cost_run = (term_px - partial_px) * 2
print(f"  OBSERVED COST of the partial   = 2 sh x (${term_px} - ${partial_px}) = ${cost_run:.2f}"
      f"  = {cost_run/r_dollar:.3f} R")
cost_design = (term_px - tgt) * 2
print(f"  cost had it filled AT the ${tgt:.4f} target on 08-04 (3 aborted API attempts, "
      f"12:15/12:20/12:25 ET)")
print(f"                                 = 2 sh x (${term_px} - ${tgt:.4f}) = ${cost_design:.2f}"
      f"  = {cost_design/r_dollar:.3f} R")
print(f"  the 1-day execution delay was WORTH  ${cost_design-cost_run:+.2f}"
      f"  (filled ${partial_px-tgt:+.4f}/sh above target)")

# ── 4. per-candidate cost, PLTR ──────────────────────────────────────────────
line("=")
print("4. PER-CANDIDATE COST ON PLTR — R and dollars given up vs riding to the trail stop")
line()
cands = replay.candidates()
nothing_r = (term_px - e) / rps
print(f"  baseline 'do nothing' = {nothing_r:+.3f} R = ${(term_px-e)*sh:+.2f}\n")
print(f"  {'candidate rule':<34} {'fires?':>6} {'kept R':>8} {'kept $':>9} {'cost R':>8} {'cost $':>9}")
rows = []
for name, fn in cands.items():
    if name in ("actual", "nothing"):
        continue
    res = fn(t)
    if res is None:
        rows.append((name, "n/a", None, None)); continue
    rows.append((name, "yes" if res.triggered else "no", res.kept_r, nothing_r - res.kept_r))
for name, fires, kept, cost in sorted(rows, key=lambda x: (x[3] is None, -(x[3] or 0))):
    if kept is None:
        print(f"  {name:<34} {fires:>6} {'—':>8} {'—':>9} {'—':>8} {'—':>9}")
    else:
        print(f"  {name:<34} {fires:>6} {kept:>+8.3f} {kept*r_dollar:>+9.2f} "
              f"{cost:>+8.3f} {cost*r_dollar:>+9.2f}")
print(f"\n  as-run (deployed +2R partial, late fill)      {t.rec['realized_r']:>+8.3f} "
      f"{t.rec['realized_pnl']:>+9.2f} {nothing_r-t.rec['realized_r']:>+8.3f} "
      f"{(nothing_r-t.rec['realized_r'])*r_dollar:>+9.2f}")

# ── 5. ETON — why no candidate cost can be priced ────────────────────────────
line("=")
print("5. ETON — the baseline does not exist, and the accounting is off by $0.76")
line()
t2 = trades[367]; e2, rps2, sh2 = t2.entry, t2.risk, 17
r_dollar2 = rps2 * sh2
print(f"  1R on the whole position = ${r_dollar2:.3f}")
print(f"  BOOKED  : exits[] says stop_hit 17 sh @ $55.05 + partial 5 sh @ $59.58 = 22 sh on a "
      f"17-sh entry")
print(f"  ORDERS  : the stop order filled 12 sh @ $55.05 (id 296); the limit filled 5 @ $59.58 (id 295)")
true_pnl = 5 * (59.58 - e2) + 12 * (55.05 - e2)
print(f"  booked P&L ${t2.rec['realized_pnl']:+.4f} ({t2.rec['realized_r']:+.4f} R)   "
      f"TRUE P&L ${true_pnl:+.4f} ({true_pnl/r_dollar2:+.4f} R)   over-counted loss "
      f"${t2.rec['realized_pnl']-true_pnl:+.4f}")
e14 = [r for r in B if r["ticker"] == "ETON"]
post = [r for r in e14 if r["et"][11:] >= "09:32"]
print(f"\n  the ORB-low stop $53.01 was NEVER touched after the fill "
      f"(post-fill low ${min(float(r['low']) for r in post):.2f}).")
print(f"  what ejected the other 12 shares was the BREAKEVEN stop the partial ARMED "
      f"(${e2:.4f}, 09:35:01 ET), hit at 09:45:11 ET.")
print(f"  => there is no do-nothing terminal exit to price against: without the rule the "
      f"position was still open.")
print(f"\n  forward path of the same 17 shares (daily closes, ORB-R units off ${e2:.4f}):")
for r in open(HERE / "_508e_winner_fwd_daily.psv").read().splitlines():
    p = r.split("|")
    if len(p) > 5 and p[0] == "ETON" and p[1] >= "2026-08-14":
        c = float(p[5])
        print(f"     {p[1]}  H ${float(p[3]):>7.2f}  C ${c:>7.2f}  = {(c-e2)/rps2:+.2f} R  "
              f"mark-to-market on 17 sh ${(c-e2)*sh2:+8.2f}")
print(f"\n  what the rule's breakeven leg gave up, marked at the last close: "
      f"12 sh x ($63.47 - $55.05) = ${12*(63.47-55.05):+.2f}  (UNREALISED, a model, not an observation)")

# ── 6. ERA TRANSLATION ───────────────────────────────────────────────────────
line("=")
print("6. ERA — what carries over to the 2R-stop world and what does not")
line()
for tid, tkr in W.items():
    t3 = trades[tid]; oh, ol = ORB[tid]
    orb_r = t3.entry - ol
    new_stop = 2 * ol - oh
    new_r = t3.entry - new_stop
    pk = hwm[tid][0]
    print(f"  {tkr}: placed stop ${t3.rec['entry_price']-t3.risk:.4f} == ORB low ${ol} -> R was the ORB-R")
    print(f"     under the 2026-08-16 rule the stop would be 2*{ol}-{oh} = ${new_stop:.4f},"
          f"  R = ${new_r:.4f} = {new_r/orb_r:.3f}x the old R")
    print(f"     the +2R TARGET PRICE is unchanged (ORB-anchored): ${t3.entry+2*orb_r:.4f}")
    print(f"     the same peak relabels: +{(pk-t3.entry)/orb_r:.2f} ORB-R  ->  "
          f"+{(pk-t3.entry)/new_r:.2f} placed-stop-R")
    print()
print("Done. THE LINE: nothing above changes any rule, threshold, or trade state.")
