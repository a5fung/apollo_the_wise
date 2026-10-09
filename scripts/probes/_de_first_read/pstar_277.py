"""Restate break-even tail rate p* on the 277 real-EP campaigns (327_real_ep rerun files, $0).
p* solves p*mean_tail + (1-p)*mean_nontail = 0, tail = harvested realized_r >= 4 on the M-none arm
(the arm the live lane's realized_r measures), incumbent stop."""
import csv,collections,statistics as st
D='../_327_real_ep/'
F=[r for r in csv.DictReader(open(D+'fires.tsv'),delimiter='|') if r['settle_status']=='settled' and r['realized_r']!='']
def pstar(rs):
    t=[x for x in rs if x>=4]; n=[x for x in rs if x<4]
    if not t or not n: return None,len(t),None,None
    mt,mn=st.mean(t),st.mean(n)
    p=None if mn>=0 else -mn/(mt-mn)
    return p,len(t),mt,mn
def show(label,groups):
    print(label)
    for k in sorted(groups):
        rs=groups[k]; p,nt,mt,mn=pstar(rs)
        obs=nt/len(rs)
        print(f"  {str(k):42s} n={len(rs):4d} tails={nt:3d} obs_rate={obs*100:5.1f}% mean_all={st.mean(rs):+.3f} mean_tail={mt if mt is None else round(mt,2)} mean_nontail={mn if mn is None else round(mn,3)} p*={'positive at p=0' if (mn is not None and mn>=0) else (f'{p*100:.1f}%' if p is not None else 'n/a')}")
g=collections.defaultdict(list)
for r in F: g[(r['era'],r['rung'])].append(float(r['realized_r']))
for r in F: g[('A+B',r['rung'])].append(float(r['realized_r']))
for r in F: g[('A+B','ALL')].append(float(r['realized_r']))
show('FIRST ATTEMPTS, M-none, incumbent stop (fires.tsv)',g)
R=[r for r in csv.DictReader(open(D+'reentry_rows.tsv'),delimiter='|') if r['stop']=='incumbent' and r['arm']=='none' and r['status']=='settled']
g2=collections.defaultdict(list)
for r in R:
    g2[('all_attempts',r['rung'])].append(float(r['r'])); g2[('all_attempts','ALL')].append(float(r['r']))
    g2[('shape',r['shape'])].append(float(r['r']))
show('ALL ATTEMPTS incl. re-entries, M-none, incumbent (reentry_rows.tsv, settled only)',g2)
# cross-check first attempts match
fr={(r['ticker'],r['ep_date'],r['rung']):float(r['realized_r']) for r in F}
mm=[(k,fr[k],float(r['r'])) for r in R if r['attempt']=='1' for k in [(r['ticker'],r['ep_date'],r['rung'])] if k in fr and abs(fr[k]-float(r['r']))>1e-6]
print('first-attempt mismatches fires.tsv vs reentry_rows:',len(mm),mm[:5])
