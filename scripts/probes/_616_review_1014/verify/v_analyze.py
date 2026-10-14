"""Verifier's independent read of #616 (delayed_entry_adr_stop_variant_616). Reads v2_rows.out only."""
import csv, statistics as st
from collections import defaultdict
rows = list(csv.DictReader(open('v2_rows.out')))
def f(x):
    return None if x in ('', None) else float(x)
MAT = 20
arms = [('inc', 'realized_r_trail', 'outcome_trail', 'reached_4r', 'stop_width_pct'),
        ('075', 'realized_r_trail_075', 'outcome_trail_075', 'reached_4r_075', 'stop_width_pct_075'),
        ('100', 'realized_r_trail_100', 'outcome_trail_100', 'reached_4r_100', 'stop_width_pct_100')]
def summarize(sub, label):
    print(f'--- {label}: n={len(sub)}')
    for a, rc, oc, r4, sw in arms:
        rs = [f(r[rc]) for r in sub]
        if any(v is None for v in rs):
            print(f'  {a}: {sum(v is None for v in rs)} unsettled -> skip'); continue
        outs = defaultdict(int)
        for r in sub: outs[r[oc]] += 1
        pct = [f(r[rc]) * f(r[sw]) for r in sub]   # R x stop width% = % of entry
        best = max(sub, key=lambda r: f(r[rc]))
        print(f'  {a}: mean {st.mean(rs):+.3f} median {st.median(rs):+.3f} sum {sum(rs):+.2f} '
              f'win {sum(v>0 for v in rs)}/{len(rs)} outcomes {dict(outs)} touched4R {sum(r[r4]=="t" for r in sub)} '
              f'best {best["ticker"]} {f(best[rc]):+.3f} | mean %entry {st.mean(pct):+.2f}% median stopwidth {st.median(f(r[sw]) for r in sub):.2f}%')
        # drop-best-campaign
        rest = [f(r[rc]) for r in sub if r is not best]
        if rest:
            print(f'      drop-best ({best["ticker"]}): n={len(rest)} mean {st.mean(rest):+.3f} sum {sum(rest):+.2f}')
        pos = sum(v for v in rs if v > 0)
        if pos > 0:
            print(f'      best share of positive R: {f(best[rc])/pos:.0%}')
    # monthly
    by_m = defaultdict(list)
    for r in sub: by_m[r['fire_date'][:7]].append(r)
    for m, mr in sorted(by_m.items()):
        print('  month', m, 'n', len(mr), ' '.join(f'{a} {sum(f(r[rc]) for r in mr):+.2f}' for a, rc, *_ in arms if all(f(r[rc]) is not None for r in mr)))
    # paired vs incumbent
    for a, rc, *_ in arms[1:]:
        d = [f(r[rc]) - f(r['realized_r_trail']) for r in sub if f(r[rc]) is not None and f(r['realized_r_trail']) is not None]
        print(f'  paired {a} vs inc: better {sum(x>1e-9 for x in d)} tie {sum(abs(x)<=1e-9 for x in d)} worse {sum(x<-1e-9 for x in d)} mean diff {st.mean(d):+.3f}')

# ---- population
lr = [r for r in rows if r['rung']=='ep_low_reclaim' and r['reentry_shape']=='first']
print('ep_low_reclaim first since 09-02:', len(lr), 'months', dict(sorted(defaultdict(int, {m: sum(r['fire_date'][:7]==m for r in lr) for m in {r['fire_date'][:7] for r in lr}}).items())))
mat = [r for r in lr if int(r['spy_after']) >= MAT]
imm = [r for r in lr if int(r['spy_after']) < MAT]
print('mature (>=20 SPY sessions after fire):', len(mat), [r['ticker']+' '+r['fire_date'] for r in mat])
print('own-ticker bars agree with SPY on all 22:', all(r['spy_after']==r['own_after'] for r in lr))
print('mature with any arm unsettled:', [r['ticker'] for r in mat if any(f(r[a[1]]) is None for a in arms)])
imm_set075 = [r for r in imm if f(r['realized_r_trail_075']) is not None]
print('immature settled on 075:', len(imm_set075), 'stops', sum(r['outcome_trail_075']=='stop' for r in imm_set075),
      '| immature open on 075:', len(imm) - len(imm_set075))
print('mature 075 stop share:', sum(r['outcome_trail_075']=='stop' for r in mat), '/', len(mat))
print()
print('per-fire, mature (R: inc / 075 / 100 ; outcome M-none 075):')
for r in mat:
    print(f"  {r['id']} {r['ticker']:5s} fire {r['fire_date']} entry {f(r['entry_price']):.2f} stops {f(r['stop_price']):.2f}/{f(r['stop_price_075']):.2f}/{f(r['stop_price_100']):.2f} "
          f"R {f(r['realized_r_trail']):+.3f} / {f(r['realized_r_trail_075']):+.3f} / {f(r['realized_r_trail_100']):+.3f}  "
          f"trail-out {r['outcome_trail']}/{r['outcome_trail_075']}/{r['outcome_trail_100']} 4R {r['reached_4r']}/{r['reached_4r_075']}/{r['reached_4r_100']} "
          f"mfe075 {r['mfe_r_075']}")
print()
summarize(mat, 'ep_low_reclaim FIRST, MATURE (the pre-registered cell)')
print()
# M-none arm too, for completeness
for a, rc in [('inc','realized_r'),('075','realized_r_075'),('100','realized_r_100')]:
    rs=[f(r[rc]) for r in mat]; print(f'  M-none {a}: mean {st.mean(rs):+.3f} median {st.median(rs):+.3f} sum {sum(rs):+.2f}')
print()
# secondary rungs, first attempts, mature
for rung in ['ep_close_reclaim','ep_close_620_prox','ep_high_break']:
    sub=[r for r in rows if r['rung']==rung and r['reentry_shape']=='first' and int(r['spy_after'])>=MAT]
    if sub:
        print(rung, 'n', len(sub), ' '.join(f"{a} {st.mean(f(r[rc]) for r in sub):+.2f}" for a, rc, *_ in arms if all(f(r[rc]) is not None for r in sub)),
              '| unsettled-mature', [r['ticker'] for r in sub if any(f(r[x[1]]) is None for x in arms)])
print()
# What a naive (immature-included) read would have said
allset=[r for r in lr if all(f(r[a[1]]) is not None for a in arms)]
print('NAIVE (all 3 arms settled, incl immature) n', len(allset), ' '.join(f"{a} {st.mean(f(r[rc]) for r in allset):+.3f}" for a, rc, *_ in arms))
# accrual rate
sess_0902 = int([r for r in rows if r['fire_date']=='2026-09-02'][0]['spy_after']) + 1 if any(r['fire_date']=='2026-09-02' for r in rows) else None
print('ep_low_reclaim first fires per session since 09-02:', len(lr), '/', sess_0902, '=', round(len(lr)/sess_0902, 3) if sess_0902 else None)
