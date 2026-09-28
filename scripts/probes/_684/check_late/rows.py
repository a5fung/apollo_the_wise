import sys
exec(open('/private/tmp/claude-501/-Users-alvinfung-apollo-the-wise/d30e3944-e07e-4b44-97de-010acba78d0b/scratchpad/recompute.py').read().split("out = []\np = out.append")[0])
late_high=[k for k in LATE if is_high(k)]
blocked={('POWI','2026-05-26'),('HUT','2026-05-06'),('CALY','2026-05-08'),('ECG','2026-08-05')}
for mech in ('live500:open','live500:prevclose'):
    print(mech)
    tot=[];tot2=[]
    for k in late_high:
        x=replay(k, detect_minute(k) or pop[k]['first_pass_time'], '10:30', mech, True)
        if x['st']=='filled':
            print('  ',k, x['kind'], x['fm'], 'px',round(x['px'],2),'H',x['H'],'L',x['L'],'R',None if x['R'] is None else round(x['R'],2),'run',None if x['run'] is None else round(x['run'],1), 'walk', x['walk'], x.get('wreason'), 'BLOCKED' if k in blocked else '')
            if x['R'] is not None:
                tot.append(x['R'])
                if k not in blocked: tot2.append(x['R'])
    print('   all settled n',len(tot),'mean',round(sum(tot)/len(tot),3),' excl safeguard-blocked n',len(tot2),'mean',round(sum(tot2)/len(tot2),3))
# control abstains / option1 abstains in study repro
print('study-repro abstain reasons:')
for k in LATE:
    x=replay(k, pop[k]['first_pass_time'], '10:30','study',False)
    if x['st']=='filled' and x['R'] is None: print('  OPT1',k,x['walk'],x.get('wreason'),'run',x['run'])
for k in CTRL:
    x=replay(k, max(pop[k]['first_pass_time'],'09:31'), '10:00' if k[1]>='2026-08-01' else None,'study',False)
    if x['st']=='filled' and x['R'] is None: print('  CTRL',k,x['walk'],x.get('wreason'),'run',None if x['run'] is None else round(x['run'],1))
