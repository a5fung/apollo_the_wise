from common import *
import collections as C
camps, daily, cal, trig = load()
H = cal[-1]; print('last bar', H, 'calendar days', len(cal))
def sess(ep): return [d for d in cal if d > ep]
_EPS = 1e-9
def labels_for(t, ep):
    bars = daily.get(t, {}); epb = bars.get(ep); ss = sess(ep)
    out = dict(n_sess=len(ss), n15=False, fast_ran=False, fast=False, n40=False, slow=None, s40_pct=None, max15=None, s15=None, max40=None)
    if not epb: return out
    epc = epb['close']
    if len(ss) >= 15 and all(d in bars for d in ss[:15]):
        out['n15'] = True; mx = max(bars[d]['high_price'] for d in ss[:15])
        out['max15'] = (mx/epc-1)*100; out['s15'] = (bars[ss[14]]['close']/epc-1)*100
        out['fast_ran'] = mx >= 1.5*epc-_EPS; out['fast'] = out['fast_ran'] and bars[ss[14]]['close'] >= 1.3*epc-_EPS
    if len(ss) >= 40 and all(d in bars for d in ss[:40]):
        out['n40'] = True; d40 = ss[39]; closes = [bars[d]['close'] for d in sorted(bars) if d <= d40]
        sma50 = sum(closes[-50:])/50 if len(closes) >= 50 else None; c40 = bars[d40]['close']
        out['s40_pct'] = (c40/epc-1)*100; out['slow'] = c40 >= 1.25*epc-_EPS and sma50 is not None and c40 > sma50
        out['max40'] = (max(bars[d]['high_price'] for d in ss[:40])/epc-1)*100
    return out
HIS = {('PENG', D('2026-10-07'))}
print('campaigns (live alerts >= 08-22):', len(camps))
lab = {k: labels_for(*k) for k in camps}
nobar = [k for k in camps if k[1] not in daily.get(k[0], {})]; print('campaigns with no EP-day bar:', nobar)
pop = {k for k in camps if len(sess(k[1])) >= 15}
print('with >= 15 sessions by', H, ':', len(pop), ' label computable (15 complete bars):', sum(lab[k]['n15'] for k in pop))
print('last EP date with 15 sessions:', max(k[1] for k in pop), ' with 40:', max((k[1] for k in pop if len(sess(k[1])) >= 40), default=None))
tk = C.defaultdict(list)
for r in trig: tk[(r['ticker'], r['ep'])].append(r)
orphan = [k for k in tk if k not in camps]; print('lane campaigns not in live alerts:', orphan)
print()
print('group | campaigns>=15s | tiers | with lane fire | first fires (settled/open) | all fires | n40 | FAST | ran+50 | SLOW | his')
for g in GN:
    ks = [k for k in pop if group(k[1]) == g]
    ff = [r for k in ks for r in tk.get(k, []) if r['reentry_shape'] == 'first']
    af = [r for k in ks for r in tk.get(k, [])]
    print(g, '|', len(ks), '|', dict(C.Counter(camps[k]['score_tier'] for k in ks)), '|', sum(k in tk for k in ks), '|', len(ff),
          f"({sum(r['realized_r']!='' for r in ff)}/{sum(r['realized_r']=='' for r in ff)})", '|', len(af), '|', sum(lab[k]['n40'] for k in ks), '|',
          [k[0] for k in ks if lab[k]['fast']], '|', [k[0] for k in ks if lab[k]['fast_ran']], '|', [k[0] for k in ks if lab[k]['slow']], '|', [k[0] for k in ks if k in HIS])
print()
print('young campaigns (< 15 sessions, outside the population):', len(camps)-len(pop))
print('\nfirst-attempt fires per cell (pattern x group), settled+mature-20s / all:')
for g in GN:
    for rung in ['ep_low_reclaim', 'ep_close_reclaim', 'ep_close_620_prox', 'ep_high_break']:
        S = [r for r in trig if (r['ticker'], r['ep']) in pop and group(r['ep']) == g and r['rung'] == rung and r['reentry_shape'] == 'first']
        m = [r for r in S if len([d for d in cal if d > r['fd']]) >= 20]
        print(f"  {g:16s} {rung:18s} first fires {len(S):3d}  with 20 sessions after the fire {len(m):3d}  settled {sum(r['realized_r']!='' for r in S):3d}")
print('\nALL-GROUPS labelled count only: first fires by pattern', dict(C.Counter(r['rung'] for r in trig if (r['ticker'], r['ep']) in pop and r['reentry_shape']=='first')))
print('\ntop campaigns by 15-session peak:')
for k in sorted(pop, key=lambda k: -(lab[k]['max15'] or -99))[:12]:
    l = lab[k]; print('  ', k[0], k[1], group(k[1])[:2], camps[k]['score_tier'], f"max15 {l['max15']:+.0f}% s15 {l['s15']:+.0f}% n_sess {l['n_sess']}", f"s40 {l['s40_pct']:+.0f}% slow={l['slow']} max40 {l['max40']:+.0f}%" if l['n40'] else '', 'lane fires', len(tk.get(k, [])))
import json
json.dump({f"{k[0]}|{k[1]}": dict(lab[k], group=group(k[1]), in_pop=k in pop) for k in camps}, open(HERE/'labels.json', 'w'), default=str, indent=0)
