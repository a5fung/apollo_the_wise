"""ADVERSARIAL: same cohorts as _577b_era_arms.py, but with the ACTUAL live stop
(order_manager.py:617 -> 2*orb_low - orb_high, live since 2026-08-16).
R reported in TRADE-RISK units (equal dollar risk). Read-only."""
import sys, pathlib
sys.path.insert(0,'.'); sys.path.insert(0,'../..')
import _468_moderate_realized_r as M
HERE = pathlib.Path('.')
M.DAILY, M.MINUTE = HERE/'_ext_daily.tsv', HERE/'_ext_minute.tsv'
M.COHORT = HERE/'_ext_cohort.tsv'
HORIZON = 20
def sma(c,n): return sum(c[-n:])/n if len(c)>=n else None

def sim(entry, stop0, orb_r, day0_after, fwd, prior_closes, *, partial_r, be_arm_r, frac=1/3, trail=True):
    risk = entry - stop0
    if risk <= 0: return None
    held, banked, stop, done = 1.0, 0.0, stop0, False
    tgt_p = entry + partial_r*orb_r          # target pinned to the ORB-R frame (order_manager)
    tgt_be = entry + be_arm_r*orb_r if be_arm_r else None
    for b in day0_after:
        if b['l'] <= stop: return banked + held*(stop-entry)/risk
        if tgt_be and b['h'] >= tgt_be: stop = max(stop, entry)
        if not done and b['h'] >= tgt_p:
            banked += frac*(tgt_p-entry)/risk; held -= frac; done=True; stop=max(stop,entry)
    closes = list(prior_closes) + ([day0_after[-1]['c']] if day0_after else [])
    for d in fwd[:HORIZON]:
        eff = stop
        if trail:
            s10,s20 = sma(closes,10), sma(closes,20)
            line = max([x for x in (s10,s20) if x is not None], default=None)
            if line is not None and line > eff: eff = line
        if d['l'] <= stop: return banked + held*(stop-entry)/risk
        if tgt_be and d['h'] >= tgt_be: stop = max(stop, entry)
        if not done and d['h'] >= tgt_p:
            banked += frac*(tgt_p-entry)/risk; held -= frac; done=True; stop=max(stop,entry)
        if trail and d['c'] < eff: return banked + held*(d['c']-entry)/risk
        closes.append(d['c'])
    last = fwd[:HORIZON][-1]['c'] if fwd[:HORIZON] else entry
    return banked + held*(last-entry)/risk

ext, so = {}, {}
for ln in open('_577b_mo_ext.psv'):
    p = ln.rstrip('\n').split('|')
    if len(p)<4 or not p[0] or not p[2]: continue
    ext[(p[0],p[1])]=float(p[2]); so[(p[0],p[1])]=(p[3]=='t')
daily, minute = M.load_daily(), M.load_minute()
from datetime import datetime, timedelta, timezone
for ln in open('_577b_extra_bars.tsv'):
    p = ln.rstrip('\n').split('\t')
    if len(p)<8: continue
    if p[0]=='D': daily[p[1]].append({'date':p[2],'o':float(p[3]),'h':float(p[4]),'l':float(p[5]),'c':float(p[6]),'v':float(p[7])})
    elif p[0]=='M':
        t=int(p[2]); et=datetime.fromtimestamp(t/1000, timezone.utc)-timedelta(hours=4)
        minute[(p[1],et.date().isoformat())].append({'t':t,'o':float(p[3]),'h':float(p[4]),'l':float(p[5]),'c':float(p[6]),'v':float(p[7])})
for tk in daily:
    seen,keep=set(),[]
    for b in sorted(daily[tk], key=lambda x:x['date']):
        if b['date'] in seen: continue
        seen.add(b['date']); keep.append(b)
    daily[tk]=keep

STACKS = {
 'era 09-06 LIVE 1/3@+8 ORB-R, BE arms +3 ORB-R': dict(partial_r=8.0, be_arm_r=3.0),
 'era 08-16     1/3@+2 ORB-R, BE at partial     ': dict(partial_r=2.0, be_arm_r=None),
 'no ladder     hard 2R stop only               ': dict(partial_r=1e9, be_arm_r=None, trail=False),
}
def run(pairs,label,stop_mode):
    res={k:[] for k in STACKS}; filled=0
    for tk,ad in pairs:
        db=daily.get(tk,[]); i=M.idx_of_date(db,ad); raw=minute.get((tk,ad),[])
        if i is None or not raw: continue
        rth=M.de.polygon_to_rth_minutes(raw,ad)
        if not rth: continue
        rec=M.reconstruct(rth,M.SUBMIT_MIN,M.atr14_prior_close(db,i),db[i:])
        if rec.get('outcome')!='filled': continue
        hi,lo,entry=rec['orb_high'],rec['orb_low'],rec['entry']
        stop = lo if stop_mode=='orb_low' else 2*lo-hi
        if stop <= 0: continue
        filled+=1
        after=[b for b in rth if b['m']>=rec['fill_minute']]; prior=[b['c'] for b in db[:i]]
        for k,kw in STACKS.items():
            v=sim(entry,stop,entry-lo,after,db[i+1:],prior,**kw)
            if v is not None: res[k].append(v)
    print(f"\n### {label} [{stop_mode}] — candidates {len(pairs)}, filled {filled}")
    for k in STACKS:
        v=sorted(res[k]); n=len(v)
        if not n: continue
        print(f"   {k} n={n} mean {sum(v)/n:+.2f}R median {M._median(v):+.2f}R best {v[-1]:+.2f}R SUM {sum(v):+.1f}R winners {sum(1 for x in v if x>0)}/{n}")

rows=M.load_cohort()
p75=[(r['ticker'],r['alert_date']) for r in rows if ext.get((r['ticker'],r['alert_date']),-1)>=75]
p75s=[k for k in p75 if so.get(k)]
for sm in ('orb_low','entry_minus_2r'):
    run(p75,">=75% all",sm); run(p75s,">=75% real setups at open",sm)
