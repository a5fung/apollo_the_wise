import sys, re
sys.argv=['x']
exec(open('/private/tmp/claude-501/-Users-alvinfung-apollo-the-wise/d30e3944-e07e-4b44-97de-010acba78d0b/scratchpad/recompute.py').read().split("out = []\np = out.append")[0])
late_high=[k for k in LATE if is_high(k)]
def skip_mode(k):
    for t in tby.get(k,[]):
        if t['skip_reason'].startswith('window'): return t['account_mode']
    return None
def ts(s): return s if s else None
out=[]
live_fill={k for k in late_high if replay(k, detect_minute(k) or pop[k]['first_pass_time'], '10:30','live500:open',True)['st']=='filled'}
study_fill={k for k in LATE if replay(k, pop[k]['first_pass_time'], '10:30','study',False)['st']=='filled'}
blocked=Counter(); rowsout=[]
for k in late_high:
    t,d=k; m=detect_minute(k) or pop[k]['first_pass_time']; when=f"{d} {m}:59"
    mode=skip_mode(k)
    if mode is None:
        # infer: mode of magna53 rows that day
        ms=[x['account_mode'] for kk,v in tby.items() if kk[1]==d for x in v if x['signal_type']=='magna53']
        mode=Counter(ms).most_common(1)[0][0] if ms else '?'
    openc=0; names=[]
    for kk,v in tby.items():
        for x in v:
            if x['account_mode']!=mode: continue
            if x['status']=='skipped': continue
            start = x['filled_et'] or x['created_et']
            if not start or start> when: continue
            end = x['closed_et']
            if end and end <= when: continue
            if x['status']=='cancelled' and not x['filled_et']:
                # pending order: counts only until cancelled (closed_et) - if no closed_et assume cancelled 10:00 same day
                if not end and when > f"{x['alert_date']} 10:00:00": continue
            openc+=1; names.append(x['ticker'])
    cb=any(x['skip_reason'].startswith('block:circuit_breaker') for kk,v in tby.items() if kk[1]==d for x in v if x['account_mode']==mode)
    b1=any(x['ticker']==t and x['alert_date']<d and x['filled_et'] and x['filled_et']<=when and (not x['closed_et'] or x['closed_et']>when) for x in tby_all) if False else False
    same_open=[x for kk,v in tby.items() for x in v if kk[0]==t and kk[1]<d and x['account_mode']==mode and x['filled_et'] and x['filled_et']<=when and (not x['closed_et'] or x['closed_et']>when)]
    reason = 'circuit_breaker_day' if cb else ('cap>=5' if openc>=5 else ('same_ticker_open' if same_open else 'ok'))
    blocked[(k in live_fill, reason)]+=1
    rowsout.append((k, mode, m, openc, cb, bool(same_open), reason, k in live_fill, k in study_fill))
print('late HIGH rows: (live-mech fill?, safeguard verdict) ->', dict(blocked))
for r in rowsout:
    if r[7] or r[8] or r[6]!='ok': print('  ',r)
