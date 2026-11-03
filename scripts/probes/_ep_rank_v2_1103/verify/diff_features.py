"""Diff my recomputed features (verify_features.tsv) against the builder's build/features.tsv."""
import csv, ast
B = {}
for r in csv.DictReader(open('build/features.tsv'), delimiter='\t'):
    B.setdefault((r['ticker'], r['date']), r)
M = {(r['ticker'], r['date']): r for r in csv.DictReader(open('verify/verify_features.tsv'), delimiter='\t')}
def f(x):
    try: return None if x in ('', 'None', None) else float(x)
    except ValueError: return None
cols = [('zones_cleared','zones_cleared'),('zones_remaining','zones_remaining'),('cleared_ath','cleared_ath'),
        ('vol_ratio_252','vol_ratio_252'),('vol_highest_ever','vol_highest_ever'),('tightness_eod','tightness_eod'),
        ('tightness_asof0945','tightness_asof0945'),('pullbacks_held','pullbacks_held'),('history','history_5y_sessions')]
out=[]
for scope, keys in (('SAMPLE-25', [k for k in M if M[k]['in_sample']=='1']), ('ALL', list(M))):
    tot = {c[0]: [0,0] for c in cols}
    diffs = []
    for k in sorted(keys):
        m, b = M[k], B[k]
        for mc, bc in cols:
            a, z = f(m[mc]), f(b[bc])
            same = (a is None and z is None) or (a is not None and z is not None and abs(a - z) <= 1e-3 * max(1, abs(z)))
            tot[mc][0] += same; tot[mc][1] += 1
            if not same: diffs.append((k, mc, a, z))
    out.append(f"{scope} ({len(keys)} pairs): " + " | ".join(f"{c} {v[0]}/{v[1]}" for c, v in tot.items()))
    for d in diffs: out.append(f"   DIFF {d[0][0]} {d[0][1]} {d[1]}: mine={d[2]} builder={d[3]}")
# pullback low distances on sample
out.append("pullback lows (sample, mine min-dist vs builder low1/low2 ADR):")
for k in sorted(k for k in M if M[k]['in_sample']=='1'):
    out.append(f"   {k[0]:5s} {k[1]} mine_min={M[k]['pb_min_dist_adr'][:6]} n_sw={M[k]['n_swing_lows']} | builder low1={B[k]['pb_low1_adr']} low2={B[k]['pb_low2_adr']} n_sw={B[k]['n_swing_lows']} zc m/b={M[k]['zones_cleared']}/{B[k]['zones_cleared']} zr m/b={M[k]['zones_remaining']}/{B[k]['zones_remaining']}")
open('verify/diff_features.txt','w').write("\n".join(out)+"\n"); print("\n".join(out))
