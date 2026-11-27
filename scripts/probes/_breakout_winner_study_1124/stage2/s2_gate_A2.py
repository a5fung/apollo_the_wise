import re,hashlib,json,sys
R='/Users/alvinfung/apollo_the_wise/'
for f,h in [('docs/analysis/breakout_winner_study_prereg_DRAFT_2026-11-24.md','3eb2b9b0247bc0ba7bf0d8e6f1efd67da1078fc090373c83c1bc14599339042a'),
 ('docs/analysis/breakout_winner_study_prereg_amendment_A1_2026-11-26.md','4a7beda14378ed2dea42308d92364dd92de4907aa3c7da4aaaffdffe75d17b10'),
 ('docs/analysis/breakout_winner_study_prereg_amendment_A2_2026-11-26.md','0a6cc4174ef27d187e49100e966023340f7eb0e31cc2d552f4c5ea594f622f6b')]:
    assert hashlib.sha256(open(R+f,'rb').read()).hexdigest()==h,f
D=R+'scripts/probes/_breakout_winner_study_1124/stage2/'
lines=open(D+'2_calib.txt').read().split('\n')
sec=None;rate=None;out=[];blocking=[];listed=[];quot=[]
lo,hi=0.95,1.05
for ln in lines:
    if ln.startswith('## A.'):sec='A'
    elif ln.startswith('## B.'):sec='B'
    elif ln.startswith('## C.'):sec='C'
    elif ln.startswith('## D.'):sec='D'
    m=re.match(r'### base rate (\d)%',ln)
    if m:rate=int(m.group(1))
    if sec not in('A','B'):continue
    m=re.match(r'\s+(f\d+a?b?)\s+scored',ln)
    if not m:continue
    f=m.group(1)
    for lab,obs,exp in re.findall(r'(all|ex2020|eraA|eraB|b4|b1) (\d\.\d+)(?: \(exp (\d\.\d+)\))?',ln):
        obs=float(obs);exp=float(exp) if exp else None
        e=exp if exp is not None else 1.0
        out_band=not(lo<=obs<=hi)
        isq=(f=='f20' and not(lo<=e<=hi))
        if isq:
            q=obs/e;quot.append((sec,rate,f,lab,obs,e,q))
            if not(lo<=q<=hi):blocking.append(('QUOTIENT OUTSIDE',sec,rate,f,lab,obs,e,q))
        elif out_band:
            (listed if lab=='b1' else blocking).append((sec,rate,f,lab,obs,e))
json.dump({'quot':quot,'blocking':blocking,'listed':listed},open(D+'2_gate_A2_parsed.json','w'),default=str,indent=1)
print('QUOT');[print(x) for x in quot]
print('RAW-OUT-OF-BAND (not quotient-read)');[print(x) for x in blocking];[print('LISTED b1',x) for x in listed]
