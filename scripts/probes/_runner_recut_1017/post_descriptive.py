"""Post-run DESCRIPTIVE tables for the results doc. Reads run_rows.tsv + re-walks; adds no test, changes no number."""
import sys, csv
sys.path.insert(0, "/Users/alvinfung/apollo_the_wise/scripts/probes/_runner_recut_1017")
import recut as rc
from collections import Counter

inp = rc.load_inputs(); trades, acct = rc.build_trades(inp); rows = rc.run_population(trades)
by = {r.tr.key: r for r in rows}
prim = rc.PRIMARY

print("== Frame A engaged trades (n=%d): control vs primary t20_be vs #687's exact rule, money-R ==" % sum(1 for r in rows if 'A' in r.copy0['trig']))
print(f"{'ticker':<7}{'entry':<11}{'trig_idx':>8}{'F_R':>6}{'ctrl':>8}{'t20_be':>8}{'delta':>8}{'t20_ref':>8}  control_exit / primary_exit")
eng = [r for r in rows if 'A' in r.copy0['trig']]
for r in eng:
    c, a, f = r.ctrl, r.arms[prim], r.refs['t20_entry_ref']
    F = (r.copy0['trig']['A']['F'] - r.tr.entry) / r.tr.risk
    cr = f"{c.R:+.2f}" if c.R is not None else "  n/a"
    ar = f"{a.R:+.2f}" if a.R is not None else "  n/a"
    dl = f"{a.R - c.R:+.2f}" if (a.R is not None and c.R is not None) else "  n/a"
    fr = f"{f.R:+.2f}" if f.R is not None else "  n/a"
    print(f"{r.tr.t:<7}{r.tr.d.isoformat():<11}{r.copy0['trig']['A']['idx']:>8}{F:>6.2f}{cr:>8}{ar:>8}{dl:>8}{fr:>8}  {c.final_reason or c.status}/{c.status} -> {a.final_reason or a.status}/{a.status}")
print()
print("engaged-only totals (money-R): control %.2f, primary %.2f, t20_entry_ref %.2f; engaged n=%d" % (
    sum(r.ctrl.R for r in eng), sum(r.arms[prim].R for r in eng), sum(r.refs['t20_entry_ref'].R for r in eng), len(eng)))
print("how the 29 engaged trades end under the primary:", dict(Counter((r.arms[prim].final_reason or r.arms[prim].status) for r in eng)))
print("how the 29 engaged trades end under the control:", dict(Counter((r.ctrl.final_reason or r.ctrl.status) for r in eng)))
print("trigger-session split: day0=%d, later=%d" % (sum(1 for r in eng if r.copy0['trig']['A']['idx']==0), sum(1 for r in eng if r.copy0['trig']['A']['idx']>0)))
print("entry months of the 29:", dict(sorted(Counter(r.tr.d.strftime('%Y-%m') for r in eng).items())))
print("entry weeks (distinct) of the 29:", len({r.tr.week for r in eng}), " of the 16 that differ:", len({r.tr.week for r in eng if r.arms[prim].R is not None and abs(r.arms[prim].R - r.ctrl.R) > 0.005}))
print("population: entry weeks distinct:", len({r.tr.week for r in rows}))

print("\n== why sma10_depth == control: engaged trades with SMA20 > SMA10 at any post-trigger session on the CONTROL path ==")
for fr in rc.FRAMES:
    n = 0
    for r in rows:
        if fr not in r.copy0['trig']: continue
        k = r.copy0['trig'][fr]['idx']
        closes = list(r.tr.prior); hit = False
        for idx, (d, b) in enumerate(r.tr.sessions, start=1):
            if b is None: break
            closes.append(b['c'])
            if idx >= max(k, 1):
                s10, s20 = rc.sma(closes, 10), rc.sma(closes, 20)
                if s10 and s20 and s20 > s10: hit = True
            if r.ctrl.out.get('exit_session') is not None and idx >= r.ctrl.out['exit_session']: break
        n += hit
    print(f"  Frame {fr}: {n} of {sum(1 for r in rows if fr in r.copy0['trig'])} engaged trades ever have SMA20 > SMA10 while held after the trigger")

print("\n== BABA 2026-07-08 and AOSL 2026-04-14 (the two names that carried the 08-29 read) ==")
for key in (("BABA","2026-07-08"),("AOSL","2026-04-14")):
    r = by[key]
    print(f"{key}: entry {r.tr.entry}, money-R {r.tr.risk:.3f}, sessions stored {len(r.tr.sessions)}, triggers {r.copy0['trig']}")
    print(f"   control R {r.ctrl.R:+.2f} ({r.ctrl.final_reason or r.ctrl.status}, exit_session {r.ctrl.out.get('exit_session')}); primary R {r.arms[prim].R:+.2f} ({r.arms[prim].final_reason or r.arms[prim].status}, exit_session {r.arms[prim].out.get('exit_session')}, {r.arms[prim].status})")
    print("   legs control:", [(l['reason'], round(l['price'],2), round(l['shares'],3)) for l in r.ctrl.out['exits']])
    print("   legs primary:", [(l['reason'], round(l['price'],2), round(l['shares'],3)) for l in r.arms[prim].out['exits']])

print("\n== primary without BABA: paired totals ==")
d = [(r.arms[prim].R - r.ctrl.R, r.tr.key) for r in rows if r.arms[prim].R is not None and r.ctrl.R is not None]
print("  total delta %.2f ; without BABA %.2f ; without BABA and DOCN %.2f" % (sum(x for x,_ in d), sum(x for x,k in d if k!=('BABA','2026-07-08')), sum(x for x,k in d if k not in (('BABA','2026-07-08'),('DOCN','2026-05-05')))))
print("  the 16 differing trades' deltas:", sorted([(round(x,2),k[0]) for x,k in d if abs(x)>0.005], reverse=True))

print("\n== control trades by entry half and month (n, total R) ==")
for lab, f in (("H1", lambda r: r.tr.d <= rc.H1_END), ("H2", lambda r: r.tr.d > rc.H1_END)):
    xs = [r.ctrl.R for r in rows if r.ctrl.R is not None and f(r)]
    print(f"  {lab}: n={len(xs)} total {sum(xs):+.2f} (+4R trades {sum(1 for x in xs if x>=4-1e-9)})")
mo = {}
for r in rows:
    if r.ctrl.R is not None: mo.setdefault(r.tr.d.strftime('%Y-%m'), []).append(r.ctrl.R)
for k in sorted(mo): print(f"  {k}: n={len(mo[k])} total {sum(mo[k]):+.2f}")

print("\n== era_d vs control (the switch's effect on this population) ==")
xs = [(r.refs['era_d'].R, r.ctrl.R, r.tr.key) for r in rows if r.ctrl.R is not None]
print("  n=%d, control total %.2f, era-D total %.2f, differ (>0.005R) on %d trades" % (len(xs), sum(c for _,c,_ in xs), sum(e for e,_,_ in xs), sum(1 for e,c,_ in xs if abs(e-c)>0.005)))
print("  control_at_close vs control: closing-price sale of the 47 close-below exits vs next-open:", end=" ")
cc = [(r.refs['control_at_close'].R - r.ctrl.R) for r in rows if r.ctrl.R is not None]
print("total %.2f over %d trades differing" % (sum(cc), sum(1 for x in cc if abs(x)>0.005)))
