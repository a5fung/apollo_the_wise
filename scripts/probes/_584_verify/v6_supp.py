"""#584 verify supplement: numpy-style P90, recall/precision vs full-day D0 $vol, premarket share, BGM split. Reads v2/v3/v4 captures; writes v6_out.txt."""
import runpy, io, contextlib, statistics as st
import numpy as np
from datetime import date
g = runpy.run_path('/Users/alvinfung/apollo_the_wise/scripts/probes/_584_verify/v5_verify.py')
inw, cl, a10, sd, bars, cal, calidx = g['inw'], g['cl'], g['a10'], g['sd'], g['bars'], g['cal'], g['calidx']
o = open('/Users/alvinfung/apollo_the_wise/scripts/probes/_584_verify/v6_out.txt', 'w')
def p(*a): print(*a, file=o)
BARS = [10e6, 25e6, 50e6, 100e6]
p('=== P90 excursion, numpy linear ===')
for bv in BARS:
    s = [r['oc']['exc'] for r in cl if r['today_dollar_volume_at_open'] >= bv and r['gap_pct_at_open'] >= 10]
    p(f'>=${bv/1e6:.0f}M n={len(s)} med {100*np.median(s):+.1f}% P90 {100*np.percentile(s,90):+.1f}%')
p('admitted g10 P90', f"{100*np.percentile([r['oc']['exc'] for r in a10],90):+.1f}%")
p('\n=== recall/precision vs D0 full-day $vol (bar volume x close) >= $50M, rejected in-window ===')
def fullday(r):
    b = bars.get(r['ticker'], {}).get(r['scan_date'])
    return None if not b else b[4] * b[3]
have = [r for r in inw if fullday(r) is not None]
p('in-window rejected with a D0 bar:', len(have), 'of', len(inw))
fin = [r for r in have if fullday(r) >= 50e6]
p('finish >= $50M rows:', len(fin), 'per day (20 sessions):', round(len(fin)/len(sd), 2))
for bv in BARS:
    clr = [r for r in have if r['today_dollar_volume_at_open'] >= bv]
    tp = sum(1 for r in clr if fullday(r) >= 50e6)
    p(f'>=${bv/1e6:.0f}M recall {tp}/{len(fin)}={tp/len(fin):.2f} precision {tp}/{len(clr)}={tp/len(clr):.2f}')
# alt: dollar vol at vwap proxy (h+l+c)/3
fin2 = [r for r in have if bars[r['ticker']][r['scan_date']][4]*sum(bars[r['ticker']][r['scan_date']][1:4])/3 >= 50e6]
p('alt (h+l+c)/3 basis: finish>=$50M per day', round(len(fin2)/len(sd), 2))
p('\n=== premarket share of the 09:31 read ($50M clearers, in-window) ===')
c50 = [r for r in inw if r['today_dollar_volume_at_open'] >= 50e6]
for r in c50[:0]: pass
late = [r for r in c50 if r['minutes_since_open_first'] is None and r['first_et'][11:16] >= '09:00' and r['today_volume_at_open']]
p('first read pre-mkt at/after 09:00:', len(late), 'of', len(c50))
if late:
    p(' median first/at_open volume:', round(st.median(r['today_volume_first']/r['today_volume_at_open'] for r in late), 3))
p(' first_et HH:MM distribution:', sorted({r['first_et'][11:16] for r in c50}))
late2 = [r for r in c50 if r['first_et'][11:16] >= '09:25' and r['minutes_since_open_first'] is None]
if late2:
    p(' first read 09:25+ n=', len(late2), 'median first/at_open:', round(st.median(r['today_volume_first']/r['today_volume_at_open'] for r in late2), 3))
p('\n=== BGM unapplied split ===')
p([ (str(r['scan_date']), r['minutes_since_open_at_open']) for r in g['rows'] if r['ticker']=='BGM'])
o.close()
