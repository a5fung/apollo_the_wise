# H7 adversarial verification (2026-10-08). Read-only; $0; reads this folder's captured files only.
# Sections: (1) population + bstop chain re-derived from raw minute files; (2) +2/-1 re-walk + week-block perm;
# (3) held-out/winners/TEVA/basing/warm-up census; (4) lane-convention warm-up sensitivity; (5) ADR$ EP-close look-ahead.
import csv, gzip, sys, statistics
from collections import Counter, defaultdict
from datetime import date, datetime, timezone, timedelta
from zoneinfo import ZoneInfo
HERE = "/Users/alvinfung/apollo_the_wise/scripts/probes/_327_real_ep/"
sys.path.insert(0, "/Users/alvinfung/apollo_the_wise")
sys.path.insert(0, "/Users/alvinfung/apollo_the_wise/scripts/probes/_327_block5")
from agents.market_intelligence.delayed_entry_shadow import qualified_620_crosses, to_rth_5min, _trading_days
import p2_probe
ET = ZoneInfo("America/New_York")
def rd(p, gz=False):
    fh = gzip.open(p, 'rt') if gz else open(p)
    return list(csv.DictReader(fh, delimiter='|'))
alerts = [a for a in rd(HERE+'alerts.tsv') if a['ticker'] and (a.get('alert_date') or '')[:2]=='20']
keys = {(a['ticker'], a['alert_date']) for a in alerts}
era = {(a['ticker'], a['alert_date']): ('A' if a['alert_date'] < '2026-08-22' else 'B') for a in alerts}
tier = {(a['ticker'], a['alert_date']): a['score_tier'] for a in alerts}
def load_min(p, keyset, check_date):
    out = defaultdict(list)
    with gzip.open(p, 'rt') as fh:
        r = csv.reader(fh, delimiter='|'); hdr = next(r)
        for x in r:
            if len(x) < 8: continue
            k = (x[0], x[1])
            if k not in keyset: continue
            t = int(float(x[2])); et = datetime.fromtimestamp(t/1000, tz=timezone.utc).astimezone(ET)
            m = et.hour*60+et.minute
            if not (570 <= m < 960): continue
            if et.date().isoformat() != x[1]: continue
            out[k].append({'t': t, 'm': m, 'o': float(x[3]), 'h': float(x[4]), 'l': float(x[5]), 'c': float(x[6])})
    for v in out.values(): v.sort(key=lambda b: b['t'])
    return out
old = load_min(HERE+'minute.tsv.gz', keys, True)
sat = load_min(HERE+'sat_day0_minutes.tsv.gz', keys, True)
daily = defaultdict(dict)
for r in rd(HERE+'daily.tsv'):
    try: d = date.fromisoformat(r['trade_date'])
    except: continue
    f = lambda v: float(v) if v not in ('', None) else None
    daily[r['ticker']][d] = {'o': f(r['open_price']), 'h': f(r['high_price']), 'l': f(r['low_price']), 'c': f(r['close'])}
camps = {(r['ticker'], r['ep_date']): r for r in rd(HERE+'campaigns.tsv')}
cls_old = Counter(); cls_new = Counter(); pop = {}
for k in sorted(keys):
    n_old = len(old.get(k, []))
    co = 'none' if n_old == 0 else ('one_bar' if n_old < 100 else ('partial' if n_old < 300 else 'full'))
    cls_old[(era[k], co)] += 1
    b1 = sat[k] if k in sat else old.get(k, [])
    n = len(b1)
    cn = 'dark' if n < 100 else ('thin' if n < 300 else 'full')
    cls_new[(era[k], cn)] += 1
    if cn == 'dark': continue
    adr = float(camps[k]['adr_dollar'])
    ep = date.fromisoformat(k[1]); epb = daily[k[0]].get(ep)
    orb_low = b1[0]['l']
    brk = next((x for x in b1[1:] if x['l'] < orb_low), None)
    pop[k] = dict(b1=b1, adr=adr, epb=epb, orb_low=orb_low, brk=brk['m'] if brk else None, era=era[k], src='sat' if k in sat else 'old')
print('sat keys', len(sat), 'in non-full old?', all(k in sat for k in keys if len(old.get(k,[]))<300), sum(1 for k in keys if len(old.get(k,[]))<300))
print('old classes', sorted(cls_old.items())); print('merged', sorted(cls_new.items()))
inpop = {k: v for k, v in pop.items() if v['brk'] is not None}
print('in_pop', Counter(v['era'] for v in inpop.values()), 'no_shakeout', Counter(v['era'] for k, v in pop.items() if v['brk'] is None))
print('in_pop names A', len({k[0] for k, v in inpop.items() if v['era']=='A'}))
# EP-day range / ADR on in_pop
rngs = [(v['epb']['h']-v['epb']['l'])/v['adr'] for v in inpop.values() if v['era']=='A' and v['epb']]
print('EP-day range/ADR mean on A in_pop', round(statistics.mean(rngs),2), 'median', round(statistics.median(rngs),2))
# qualified crosses
anyq = 0; anyq_any = 0
fires = {}
rej = Counter()
for k, v in inpop.items():
    b5 = to_rth_5min(v['b1'], date.fromisoformat(k[1]))
    v['b5'] = b5
    q = qualified_620_crosses(b5, v['adr'], 0)
    q_after = [(i, c) for i, c in q if b5[i]['m'] >= 630]
    if v['era']=='A':
        anyq_any += bool(q); anyq += bool(q_after)
    # my chain (bstop)
    ep_open = v['epb']['o'] if v['epb'] else None
    live_until = -1
    for i, close in q_after:
        m = b5[i]['m']
        if v['brk'] > m + 4: rej[(v['era'], 'pre_shakeout')] += 1; continue
        near = (ep_open is not None and abs(close-ep_open) <= 0.5*v['adr']+1e-12) or abs(close-v['orb_low']) <= 0.5*v['adr']+1e-12
        if not near: rej[(v['era'], 'reach')] += 1; continue
        if m + 5 <= live_until: rej[(v['era'],'armed')] += 1; continue
        bl = min(x['l'] for x in b5[i-8:i+1]); lvl = b5[i]['h']
        st = None
        for x in v['b1']:
            if x['m'] < m+5: continue
            if x['l'] <= bl: st = ('cancel', x['m']); break
            if x['h'] >= lvl: st = ('fill', x['m'], max(lvl, x['o'])); break
        if st is None: rej[(v['era'],'expired')] += 1; break
        if st[0] == 'cancel': rej[(v['era'],'cancel')] += 1; live_until = st[1]; continue
        fires[k] = dict(cross=m, fill_m=st[1], entry=st[2], basing_low=bl, stop=min(bl, st[2]-0.5*v['adr']))
        break
print('A in_pop with any qualified cross (any time)', anyq_any, 'after 10:30', anyq)
print('rejections', sorted(rej.items()))
print('fires', Counter(era[k] for k in fires))
# compare to h7_fires
H = {(r['ticker'], r['ep_date']): r for r in rd(HERE+'h7_fires.tsv') if r['rule']=='bstop'}
print('fire key sets equal', set(H) == set(fires), len(set(H) ^ set(fires)))
bad = [(k, fires[k]['entry'], H[k]['entry'], fires[k]['fill_m'], H[k]['fill_m']) for k in fires if k in H and (abs(fires[k]['entry']-float(H[k]['entry']))>1e-3 or abs(fires[k]['stop']-float(H[k]['stop']))>1e-3)]
print('mismatched entry/stop', bad[:5])
print('MODERATE among A fires', Counter(tier[k] for k in fires if era[k]=='A'))
fires0 = fires

print('\n== (2) re-walk ==')
fires = fires0
import pickle, csv, sys, random, statistics
from collections import Counter, defaultdict
from datetime import date, timedelta
sys.path.insert(0, "/Users/alvinfung/apollo_the_wise")
from agents.market_intelligence.delayed_entry_shadow import _trading_days
HERE = "/Users/alvinfung/apollo_the_wise/scripts/probes/_327_real_ep/"
daily = defaultdict(dict)
for r in csv.DictReader(open(HERE+'daily.tsv'), delimiter='|'):
    try: d = date.fromisoformat(r['trade_date'])
    except: continue
    daily[r['ticker']][d] = (float(r['high_price']) if r['high_price'] else None, float(r['low_price']) if r['low_price'] else None)
HOR = date(2026, 9, 25)
def walk(entry, y, d0, tkr, ep):
    sess = _trading_days(ep + timedelta(days=1), HOR)[:10]
    bars = list(d0) + [daily[tkr].get(d) if daily[tkr].get(d) and daily[tkr][d][0] is not None else None for d in sess]
    for b in bars:
        if b is None: return 'abstain'
        h, l = b
        if l <= entry - y: return 'stop'
        if h >= entry + 2*y: return 'target'
    return 'open'
fo, co = {}, defaultdict(list)
for k, f in fires0.items():
    v = inpop[k]; ep = date.fromisoformat(k[1]); y = v['adr']
    fb = f['fill_m'] - ((f['fill_m'] - 570) % 5)
    d0 = [(x['h'], x['l']) for x in v['b1'] if f['fill_m'] < x['m'] < fb + 5] + [(x['h'], x['l']) for x in v['b5'] if x['m'] >= fb + 5]
    fo[k] = walk(f['entry'], y, d0, k[0], ep)
    for j, b in enumerate(v['b5']):
        if b['m'] < 630 or b['m'] == fb: continue
        co[k].append(walk(b['c'], y, [(x['h'], x['l']) for x in v['b5'][j+1:]], k[0], ep))
A = [k for k in fires0 if k[1] < '2026-08-22']
B = [k for k in fires0 if k[1] >= '2026-08-22']
def g(ks):
    fh = sum(fo[k]=='target' for k in ks); fn = sum(fo[k]!='abstain' for k in ks)
    cc = [o for k in ks for o in co[k] if o != 'abstain']
    return fh, fn, sum(o=='target' for o in cc), len(cc), 100*fh/fn - 100*sum(o=='target' for o in cc)/len(cc)
print('A', g(A)); print('B', g(B)); print('A exMay', g([k for k in A if k[1][5:7] != '05']))
H = {(r['ticker'], r['ep_date']): r['edge_pess'] for r in csv.DictReader(open(HERE+'h7_fires.tsv'), delimiter='|') if r['rule']=='bstop'}
print('fire outcome mismatches', [(k, fo[k], H[k]) for k in fires0 if fo[k] != H[k]])
# week-block perm (labels shuffled within ISO week of EP date)
rows = []
for k in A:
    wk = date.fromisoformat(k[1]).isocalendar()[:2]
    if fo[k] != 'abstain': rows.append((fo[k]=='target', True, wk))
    rows += [(o=='target', False, wk) for o in co[k] if o != 'abstain']
def gapf(rs):
    f = [x for x, l, _ in rs if l]; c = [x for x, l, _ in rs if not l]
    return 100*sum(f)/len(f) - 100*sum(c)/len(c)
obs = gapf(rows)
byw = defaultdict(list)
for i, r in enumerate(rows): byw[r[2]].append(i)
rng = random.Random(1); ge = 0; N = 2000
for _ in range(N):
    lab = [None]*len(rows)
    for wk, idx in byw.items():
        ls = [rows[i][1] for i in idx]; rng.shuffle(ls)
        for i, l in zip(idx, ls): lab[i] = l
    if gapf([(rows[i][0], lab[i], rows[i][2]) for i in range(len(rows))]) >= obs - 1e-12: ge += 1
print('obs', round(obs, 3), 'one-sided p (gap >= obs)', ge / N)

print('\n== (3) census ==')
import pickle, csv, sys, gzip
from collections import Counter, defaultdict
from datetime import date
sys.path.insert(0, "/Users/alvinfung/apollo_the_wise")
from agents.market_intelligence.delayed_entry_shadow import macd_620, _trading_days
HERE = "/Users/alvinfung/apollo_the_wise/scripts/probes/_327_real_ep/"
K = {(r['ticker'], r['ep_date']): r for r in csv.DictReader(open(HERE+'h7_campaigns.tsv'), delimiter='|')}
hoa = [r for r in K.values() if r['split']=='HOA']
print('HOA', len(hoa), Counter(r['status'] for r in hoa), [r['ticker'] for r in hoa if r['status']=='in_pop'])
for t in ('NRIX','TE','HTFL','MRNA','VPG','TEAM','TEVA'):
    for k, r in K.items():
        if k[0]==t: print(t, k[1], r['status'], 'bstop:', r.get('bstop_rejections'), r.get('bstop_status'), '| close:', r.get('close_rejections'), r.get('close_status'))
F = [r for r in csv.DictReader(open(HERE+'h7_fires.tsv'), delimiter='|')]
for r in F:
    if r['ticker'] in ('TEVA','TEAM','JBIO','VPG') : print(r['rule'], r['ticker'], r['entry'], r['basing_low'], r['stop'], r['stop_w_adr'], r['basing_w_adr'], r['trail_r'], r['unfloored_trail_r'], r['fill_m'], r['edge_pess'])
# basing-guard explanation: days with a MACD<0 bullish cross after 10:30 (no basing/hook)
nraw = nbase_fail = 0
for k, v in inpop.items():
    if k[1] >= '2026-08-22': continue
    b5 = v['b5']; c = [b['c'] for b in b5]; m, s = macd_620(c)
    crs = [i for i in range(12, len(b5)) if m[i-1] <= s[i-1] and m[i] > s[i] and m[i] < 0]
    if crs: nraw += 1
    if crs and all((max(b['h'] for b in b5[i-8:i]) - min(b['l'] for b in b5[i-8:i])) > 0.4*v['adr'] for i in crs): nbase_fail += 1
print('A in_pop days with any raw MACD<0 bull cross >=10:30:', nraw, 'of', sum(1 for k in inpop if k[1] < '2026-08-22'), '; all such crosses fail basing on', nbase_fail)
# pre-EP warm-up sessions on disk among in_pop / fires
cov = defaultdict(int)
with gzip.open(HERE+'minute.tsv.gz','rt') as fh:
    rd = csv.reader(fh, delimiter='|'); next(rd)
    for x in rd:
        if len(x) > 2: cov[(x[0], x[1])] += 1
def warm(k):
    ep = date.fromisoformat(k[1])
    prev = [d for d in _trading_days(date(2026,4,1), ep) if d < ep][-2:]
    return [cov.get((k[0], d.isoformat()), 0) for d in prev]
w_in = [k for k in inpop if any(n >= 100 for n in warm(k))]
w_f = [k for k in fires0 if any(n >= 100 for n in warm(k))]
print('in_pop with >=1 of 2 prior sessions on disk (>=100 bars):', len(w_in), '; fires:', len(w_f), sorted(w_f)[:12])

print('\n== (4) warm-up sensitivity ==')
import pickle, csv, sys, gzip
from collections import Counter, defaultdict
from datetime import date, datetime, timezone, timedelta
from zoneinfo import ZoneInfo
sys.path.insert(0, "/Users/alvinfung/apollo_the_wise")
from agents.market_intelligence.delayed_entry_shadow import qualified_620_crosses, to_rth_5min, _trading_days
HERE = "/Users/alvinfung/apollo_the_wise/scripts/probes/_327_real_ep/"
ET = ZoneInfo("America/New_York")
daily = defaultdict(dict)
for r in csv.DictReader(open(HERE+'daily.tsv'), delimiter='|'):
    try: d = date.fromisoformat(r['trade_date'])
    except: continue
    daily[r['ticker']][d] = (float(r['high_price']) if r['high_price'] else None, float(r['low_price']) if r['low_price'] else None, float(r['open_price']) if r['open_price'] else None)
need = set()
for k in inpop:
    ep = date.fromisoformat(k[1]); prev = sorted(d for d in daily[k[0]] if d < ep)[-2:]
    for d in prev: need.add((k[0], d.isoformat()))
raw = defaultdict(list)
with gzip.open(HERE+'minute.tsv.gz','rt') as fh:
    rd = csv.reader(fh, delimiter='|'); next(rd)
    for x in rd:
        if len(x) < 8 or (x[0], x[1]) not in need: continue
        t = int(float(x[2])); et = datetime.fromtimestamp(t/1000, tz=timezone.utc).astimezone(ET); m = et.hour*60+et.minute
        if not (570 <= m < 960): continue
        raw[(x[0], x[1])].append({'t': t, 'o': float(x[3]), 'h': float(x[4]), 'l': float(x[5]), 'c': float(x[6])})
min5 = {k: to_rth_5min(sorted(v, key=lambda b: b['t']), date.fromisoformat(k[1])) for k, v in raw.items() if len(v) >= 100}
HOR = date(2026, 9, 25)
def walk(entry, y, d0, tkr, ep):
    sess = _trading_days(ep + timedelta(days=1), HOR)[:10]
    bars = list(d0) + [(daily[tkr][d][0], daily[tkr][d][1]) if d in daily[tkr] and daily[tkr][d][0] is not None else None for d in sess]
    for b in bars:
        if b is None: return 'abstain'
        if b[1] <= entry - y: return 'stop'
        if b[0] >= entry + 2*y: return 'target'
    return 'open'
fires = {}; nwarm = 0
for k, v in inpop.items():
    ep = date.fromisoformat(k[1]); prev = sorted(d for d in daily[k[0]] if d < ep)[-2:]
    warm = []
    for d in prev: warm += min5.get((k[0], d.isoformat()), [])
    if warm: nwarm += 1
    b5 = v['b5']; series = warm + b5; W = len(warm)
    ep_open = daily[k[0]][ep][2]
    live_until = -1
    for gi, close in qualified_620_crosses(series, v['adr'], W):
        i = gi - W; m = b5[i]['m']
        if m < 630: continue
        if v['brk'] > m + 4: continue
        if not (abs(close-ep_open) <= 0.5*v['adr']+1e-12 or abs(close-v['orb_low']) <= 0.5*v['adr']+1e-12): continue
        if m + 5 <= live_until: continue
        bl = min(x['l'] for x in b5[max(0,i-8):i+1]); lvl = b5[i]['h']; st = None
        for x in v['b1']:
            if x['m'] < m+5: continue
            if x['l'] <= bl: st = ('cancel', x['m']); break
            if x['h'] >= lvl: st = ('fill', x['m'], max(lvl, x['o'])); break
        if st is None: break
        if st[0] == 'cancel': live_until = st[1]; continue
        fires[k] = dict(fill_m=st[1], entry=st[2]); break
A0 = {k for k in fires0 if k[1] < '2026-08-22'}; A1 = {k for k in fires if k[1] < '2026-08-22'}
print('in_pop days with warm-up seed', nwarm, '| ERA A fires no-warm', len(A0), 'with warm', len(A1), 'lost', sorted(A0-A1), 'gained', sorted(A1-A0))
changed = [k for k in A0 & A1 if abs(fires0[k]['entry']-fires[k]['entry'])>1e-6]
print('same campaign different entry', changed)
def res(F):
    fh=fn=ch=cn=0
    for k, f in F.items():
        if k[1] >= '2026-08-22': continue
        v = inpop[k]; ep = date.fromisoformat(k[1]); y = v['adr']
        fb = f['fill_m'] - ((f['fill_m'] - 570) % 5)
        d0 = [(x['h'], x['l']) for x in v['b1'] if f['fill_m'] < x['m'] < fb + 5] + [(x['h'], x['l']) for x in v['b5'] if x['m'] >= fb + 5]
        o = walk(f['entry'], y, d0, k[0], ep)
        if o != 'abstain': fn += 1; fh += o == 'target'
        for j, b in enumerate(v['b5']):
            if b['m'] < 630 or b['m'] == fb: continue
            oc = walk(b['c'], y, [(x['h'], x['l']) for x in v['b5'][j+1:]], k[0], ep)
            if oc != 'abstain': cn += 1; ch += oc == 'target'
    return fn, fh, round(100*fh/fn,1), cn, round(100*ch/cn,1), round(100*fh/fn-100*ch/cn,2)
print('no-warm', res(fires0)); print('warm', res(fires))

print('\n== (5) ADR$ look-ahead ==')
import pickle, csv, sys, statistics
from collections import Counter, defaultdict
from datetime import date, timedelta
sys.path.insert(0, "/Users/alvinfung/apollo_the_wise")
from agents.market_intelligence.delayed_entry_shadow import qualified_620_crosses, _trading_days
HERE = "/Users/alvinfung/apollo_the_wise/scripts/probes/_327_real_ep/"
daily = defaultdict(dict)
for r in csv.DictReader(open(HERE+'daily.tsv'), delimiter='|'):
    try: d = date.fromisoformat(r['trade_date'])
    except: continue
    f = lambda x: float(x) if x else None
    daily[r['ticker']][d] = {'h': f(r['high_price']), 'l': f(r['low_price']), 'o': f(r['open_price']), 'c': f(r['close'])}
# verify adr_dollar uses EP close: implied ADR% = adr/close
rat = [inpop[k]['epb']['c']/inpop[k]['epb']['o'] for k in inpop]
print('EP close/open ratio across in_pop: median', round(statistics.median(rat),3), 'p10', round(sorted(rat)[len(rat)//10],3), 'p90', round(sorted(rat)[9*len(rat)//10],3))
fr = [inpop[k]['epb']['c']/fires0[k]['entry'] for k in fires0]
print('EP close / fire entry, fires: median', round(statistics.median(fr),3), 'min', round(min(fr),3), 'max', round(max(fr),3))
HOR = date(2026, 9, 25)
def walk(entry, y, d0, tkr, ep):
    sess = _trading_days(ep + timedelta(days=1), HOR)[:10]
    bars = list(d0) + [(daily[tkr][d]['h'], daily[tkr][d]['l']) if d in daily[tkr] and daily[tkr][d]['h'] is not None else None for d in sess]
    for b in bars:
        if b is None: return 'abstain'
        if b[1] <= entry - y: return 'stop'
        if b[0] >= entry + 2*y: return 'target'
    return 'open'
def run(scale):
    fires = {}; qdays = 0
    for k, v in inpop.items():
        adr = v['adr'] * scale(k, v); b5 = v['b5']; ep_open = v['epb']['o']
        q = [(i, c) for i, c in qualified_620_crosses(b5, adr, 0) if b5[i]['m'] >= 630]
        if q and k[1] < '2026-08-22': qdays += 1
        live_until = -1
        for i, close in q:
            m = b5[i]['m']
            if v['brk'] > m + 4: continue
            if not (abs(close-ep_open) <= 0.5*adr+1e-12 or abs(close-v['orb_low']) <= 0.5*adr+1e-12): continue
            if m + 5 <= live_until: continue
            bl = min(x['l'] for x in b5[i-8:i+1]); lvl = b5[i]['h']; st = None
            for x in v['b1']:
                if x['m'] < m+5: continue
                if x['l'] <= bl: st = ('cancel', x['m']); break
                if x['h'] >= lvl: st = ('fill', x['m'], max(lvl, x['o'])); break
            if st is None: break
            if st[0] == 'cancel': live_until = st[1]; continue
            fires[k] = dict(fill_m=st[1], entry=st[2], adr=adr); break
    fh=fn=ch=cn=0
    for k, f in fires.items():
        if k[1] >= '2026-08-22': continue
        v = inpop[k]; ep = date.fromisoformat(k[1]); y = f['adr']
        fb = f['fill_m'] - ((f['fill_m'] - 570) % 5)
        d0 = [(x['h'], x['l']) for x in v['b1'] if f['fill_m'] < x['m'] < fb + 5] + [(x['h'], x['l']) for x in v['b5'] if x['m'] >= fb + 5]
        o = walk(f['entry'], y, d0, k[0], ep)
        if o != 'abstain': fn += 1; fh += o == 'target'
        for j, b in enumerate(v['b5']):
            if b['m'] < 630 or b['m'] == fb: continue
            oc = walk(b['c'], y, [(x['h'], x['l']) for x in v['b5'][j+1:]], k[0], ep)
            if oc != 'abstain': cn += 1; ch += oc == 'target'
    A = {k for k in fires if k[1] < '2026-08-22'}
    return qdays, len(A), len({k[0] for k in A}), fh, round(100*fh/fn,1), cn, round(100*ch/cn,1), round(100*fh/fn-100*ch/cn,2), A
base = run(lambda k, v: 1.0)
causal = run(lambda k, v: v['epb']['o']/v['epb']['c'])
print('EP-close ADR$ (as run): qdays, fires, names, hits, fire%, ctl n, ctl%, gap =', base[:8])
print('EP-open ADR$ (causal):  qdays, fires, names, hits, fire%, ctl n, ctl%, gap =', causal[:8])
print('lost', len(base[8]-causal[8]), 'gained', len(causal[8]-base[8]))
# decomposition: the 3 gained fires; and the original 51 under causal barriers
g = sorted(causal[8]-base[8]); print('gained', g)
def edge_on(keys, scale):
    fh=fn=ch=cn=0
    for k in keys:
        v = inpop[k]; ep = date.fromisoformat(k[1]); y = v['adr']*scale(k, v); f = fires0[k]
        fb = f['fill_m'] - ((f['fill_m'] - 570) % 5)
        d0 = [(x['h'], x['l']) for x in v['b1'] if f['fill_m'] < x['m'] < fb + 5] + [(x['h'], x['l']) for x in v['b5'] if x['m'] >= fb + 5]
        o = walk(f['entry'], y, d0, k[0], ep)
        if o != 'abstain': fn += 1; fh += o == 'target'
        for j, b in enumerate(v['b5']):
            if b['m'] < 630 or b['m'] == fb: continue
            oc = walk(b['c'], y, [(x['h'], x['l']) for x in v['b5'][j+1:]], k[0], ep)
            if oc != 'abstain': cn += 1; ch += oc == 'target'
    return fn, fh, cn, ch, round(100*fh/fn - 100*ch/cn, 2)
A51 = sorted(base[8])
print('original 51 fires, causal barriers:', edge_on(A51, lambda k, v: v['epb']['o']/v['epb']['c']))
print('original 51 fires, prior-close barriers:', edge_on(A51, lambda k, v: (sorted((d, x) for d, x in daily[k[0]].items() if d < date.fromisoformat(k[1]))[-1][1]['c'])/v['epb']['c']))
