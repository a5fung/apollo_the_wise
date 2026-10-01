"""#584 verify: is the shadow minute-1 price inside the D0 daily bar's range? + split-row count without the settle restriction. Writes v7_out.txt."""
import runpy, statistics as st
g = runpy.run_path('/Users/alvinfung/apollo_the_wise/scripts/probes/_584_verify/v5_verify.py')
inw, bars, rows, splits = g['inw'], g['bars'], g['rows'], g['splits']
o = open('/Users/alvinfung/apollo_the_wise/scripts/probes/_584_verify/v7_out.txt', 'w')
def p(*a): print(*a, file=o)
for label, rs in (('rejected in-window', inw), ('admitted in-window', [r for r in rows if not r['rej'] and r['minutes_since_open_at_open'] is not None and r['minutes_since_open_at_open'] <= 15])):
    for m in (1, 5, 10, 15):
        x = [r for r in rs if r['minutes_since_open_at_open'] == m and r['scan_date'] in bars.get(r['ticker'], {})]
        if not x: continue
        out = [r for r in x if not (bars[r['ticker']][r['scan_date']][2]*0.995 <= r['today_price_at_open'] <= bars[r['ticker']][r['scan_date']][1]*1.005)]
        p(f'{label} minute {m}: shadow price outside D0 [low,high] +-0.5%: {len(out)}/{len(x)}')
p('VERA', bars['VERA'].get(__import__("datetime").date(2026,9,15)))
# split rows: execution date within (D0-0, D0+5 sessions], no settle restriction, any in-window row
cal, calidx = g['cal'], g['calidx']
import datetime as dt
hits = set()
for t, ed, aa in splits:
    for r in inw:
        if r['ticker'] != t: continue
        i = calidx.get(r['scan_date'])
        end = cal[i+5] if i is not None and i+5 < len(cal) else dt.date(2026,10,8)
        if r['scan_date'] <= ed <= end:
            hits.add((t, str(r['scan_date']), aa))
p('in-window rows with a split in D0..D0+5 (no settle restriction):', len(hits), sorted(hits))
o.close()
