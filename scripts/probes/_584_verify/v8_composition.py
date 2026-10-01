"""#584 verify: composition of bar-clearers on alternative subsets. Writes v8_out.txt."""
import runpy, statistics as st
g = runpy.run_path('/Users/alvinfung/apollo_the_wise/scripts/probes/_584_verify/v5_verify.py')
inw, cl = g['inw'], g['cl']
o = open('/Users/alvinfung/apollo_the_wise/scripts/probes/_584_verify/v8_out.txt', 'w')
for lab, pop in (('in-window all gaps', inw), ('in-window gap>=10', [r for r in inw if r['gap_pct_at_open']>=10]), ('settled-clean all gaps', cl), ('settled-clean gap>=10', [r for r in cl if r['gap_pct_at_open']>=10])):
    for bv in (10e6, 25e6, 50e6, 100e6):
        s = [r for r in pop if r['today_dollar_volume_at_open'] >= bv]
        print(f"{lab:24s} >=${bv/1e6:.0f}M n={len(s)} med gap {st.median(r['gap_pct_at_open'] for r in s):.1f} med prev_close {st.median(r['prev_close'] for r in s):.2f} P-only {sum(r['cls']=='P' for r in s)/len(s):.2f}", file=o)
o.close()
