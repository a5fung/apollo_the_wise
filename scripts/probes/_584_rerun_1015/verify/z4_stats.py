"""#584 10-15 VERIFIER: stats from z2_rows.out ONLY (SQL-computed per-row fields; csv module, no pandas, no reader code).
Definitions restated from the action + 10-13 pipeline: clean = D0 bar present, d0 open > 0, H forward bars, close at DH, ADR from 20 prior bars,
no >4x close-to-close jump D0..DH. reach_in = (peak high D0..DH / D0 open - 1) >= 8*ADR; reach_ex = same with D1..DH highs.
crash = close DH / D0 open - 1 <= -20%; win = >= +20%."""
import csv, io, math, statistics as st, sys
raw = open('z2_rows.out').read().split('\n')
lines = [l for l in raw if l and not l.startswith(('BEGIN', '===', 'ROLLBACK', 'psql'))]
start = next(i for i, l in enumerate(lines) if l.startswith('scan_date,'))
end = next(i for i, l in enumerate(lines) if l.startswith(' ticker'))
rows = list(csv.DictReader(io.StringIO('\n'.join(lines[start:end]))))
F = lambda x: float(x) if x not in ('', None) else None
for r in rows:
    for k in ('g', 'ao', 'o0', 'h0', 'c0', 'adr', 'c5', 'pk5_in', 'pk5_ex', 'maxq5', 'c20', 'pk20_in', 'pk20_ex', 'maxq20', 'p_ao', 'prev_close'):
        r[k] = F(r[k])
    for k in ('npre', 'nfwd5', 'nfwd20', 'm'):
        r[k] = int(r[k]) if r[k] else None
    r['rej'] = r['rej'] == 't'
out = []
def P(*a):
    s = ' '.join(str(x) for x in a); print(s); out.append(s)
P('rows parsed', len(rows), '| rejected (>= $10M in-window)', sum(r['rej'] for r in rows), '| admitted gap>=10 in-window', sum(not r['rej'] for r in rows))
P('NA ticker present:', any(r['ticker'] == 'NA' for r in rows))
def clean(r, H):
    return (r['o0'] or 0) > 0 and r[f'c{H}'] is not None and r[f'nfwd{H}'] == H and r['npre'] == 20 and r['adr'] is not None and (r[f'maxq{H}'] or 0) <= 4
def settled_any(r, H):  # has a close at DH (before guard / bars checks)
    return r[f'c{H}'] is not None
def ev(r, H):
    a = r['adr']; o = r['o0']
    return dict(rin=(r[f'pk{H}_in'] / o - 1) >= 8 * a, rex=(r[f'pk{H}_ex'] / o - 1) >= 8 * a,
                s=r[f'c{H}'] / o - 1)
def fisher_greater(a, b, c, d):
    # one-sided P(X >= a) for 2x2 [[a,b],[c,d]] (row1 = test group successes/failures)
    n1, n2, k = a + b, c + d, a + c
    N = n1 + n2
    def hp(x): return math.comb(n1, x) * math.comb(n2, k - x) / math.comb(N, k)
    return sum(hp(x) for x in range(a, min(n1, k) + 1))
def binom_greater(k, n, p):
    return sum(math.comb(n, x) * p ** x * (1 - p) ** (n - x) for x in range(k, n + 1))
def wilson(k, n, z=1.96):
    p = k / n; d = 1 + z * z / n; c = p + z * z / (2 * n); a = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)); return (c - a) / d, (c + a) / d

for H in (20, 5):
    P(f'\n===== H={H} =====')
    adm = [r for r in rows if not r['rej'] and clean(r, H)]
    A = [ev(r, H) for r in adm]
    ak_in = sum(e['rin'] for e in A); ak_ex = sum(e['rex'] for e in A); ac = sum(e['s'] <= -0.2 for e in A); aw = sum(e['s'] >= 0.2 for e in A)
    P(f'ADMITTED gap>=10 in-window clean: rows {len(adm)} names {len({r["ticker"] for r in adm})} | reach_in {ak_in} reach_ex {ak_ex} | crash {ac} ({ac/len(adm):.1%}) win {aw} | settled mean {st.mean(e["s"] for e in A):.1%} median {st.median(e["s"] for e in A):.1%}')
    for lvl in (10e6, 25e6, 50e6, 100e6):
        clr = [r for r in rows if r['rej'] and r['ao'] >= lvl]
        sa = [r for r in clr if settled_any(r, H)]
        cl = [r for r in clr if clean(r, H)]
        gd = [r for r in clr if settled_any(r, H) and (r['maxq%d' % H] or 0) > 4]
        E = [ev(r, H) for r in cl]; n = len(cl)
        P(f'REJ >= ${int(lvl/1e6)}M: clearing {len({r["ticker"] for r in clr})} names ({len(clr)} rows) | with D{H} close {len({r["ticker"] for r in sa})} ({len(sa)}) | CLEAN {len({r["ticker"] for r in cl})} names ({n} rows) | guard-dropped {[(r["ticker"], r["scan_date"]) for r in gd]}')
        if n == 0: continue
        kin = sum(e['rin'] for e in E); kex = sum(e['rex'] for e in E); kc = sum(e['s'] <= -0.2 for e in E); kw = sum(e['s'] >= 0.2 for e in E)
        ss = sorted(e['s'] for e in E)
        p10 = ss[int(0.1 * (n - 1))] if n else None
        P(f'   reach_in {kin}/{n} {kin/n:.1%} | reach_ex {kex}/{n} {kex/n:.1%} wilson {wilson(kex,n)[0]:.3f}-{wilson(kex,n)[1]:.3f} | crash {kc}/{n} {kc/n:.1%} | win {kw} | settled mean {st.mean(ss):.1%} median {st.median(ss):.1%}')
        P(f'   p(one-sided Fisher vs adm) reach_ex {fisher_greater(kex, n-kex, ak_ex, len(adm)-ak_ex):.3f} reach_in {fisher_greater(kin, n-kin, ak_in, len(adm)-ak_in):.3f} crash {fisher_greater(kc, n-kc, ac, len(adm)-ac):.4f}'
          f' | p(binom vs 8.2%) reach_ex {binom_greater(kex, n, .082):.3f} reach_in {binom_greater(kin, n, .082):.4f}')
        if lvl == 50e6 and H == 20:
            P('   per-row ($50M, H=20, clean):')
            for r, e in sorted(zip(cl, E), key=lambda t: (t[0]['scan_date'], t[0]['ticker'])):
                P(f'     {r["scan_date"]} {r["ticker"]:6s} ao ${r["ao"]/1e6:7.1f}M m={r["m"]} gap {r["g"]:6.1f}% adr {r["adr"]:.3f} 8xADR {8*r["adr"]:.2f} | exc_in {r["pk20_in"]/r["o0"]-1:+.2f} exc_ex {r["pk20_ex"]/r["o0"]-1:+.2f} | reach_in {int(e["rin"])} ex {int(e["rex"])} | settled {e["s"]:+.1%} | maxq {r["maxq20"]:.2f} | o0 {r["o0"]} c20 {r["c20"]}')
            no916 = [(r, e) for r, e in zip(cl, E) if r['scan_date'] != '2026-09-16']
            k = sum(e['rin'] for r, e in no916)
            P(f'   without 09-16: reach_in {k}/{len(no916)} p_fisher vs adm {fisher_greater(k, len(no916)-k, ak_in, len(adm)-ak_in):.3f}')
P('\n=== projection: $50M clean-name accrual by D0 cutoff (names with any in-window clearing row by D0) ===')
cal_rows = sorted({r['scan_date'] for r in rows})
for cut in ('2026-09-16', '2026-09-18', '2026-09-21', '2026-09-22', '2026-09-23'):
    for lvl in (50e6, 100e6):
        P(f'  D0 <= {cut} >= ${int(lvl/1e6)}M: {len({r["ticker"] for r in rows if r["rej"] and r["ao"] >= lvl and r["scan_date"] <= cut})} names')
open('z4_stats.out', 'w').write('\n'.join(out) + '\n')
