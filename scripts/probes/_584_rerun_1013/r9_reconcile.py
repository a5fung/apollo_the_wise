"""Reconcile pipeline A (a2_sweep.out, pandas) vs pipeline B (v5_verify_h5.out / _h20.out, pure python): every CHECK line must match."""
def load(fn, tags):
    d = {}
    for l in open(fn):
        if l.startswith('CHECK|'):
            f = l.strip().split('|')
            if f[1] in tags: d[tuple(f[1:6])] = tuple(int(x) if x != 'None' else None for x in f[6:])
    return d
A = load('a2_sweep.out', {'h5', 'h20'})
B = {}; [B.update(load(fn, {'h5', 'h20'})) for fn in ('v5_verify_h5.out', 'v5_verify_h20.out')]
bad = 0
print('A lines', len(A), 'B lines', len(B))
for k in sorted(set(A) | set(B)):
    a, b = A.get(k), B.get(k)
    if a != b:
        bad += 1; print('MISMATCH', k, 'A', a, 'B', b)
print('RECONCILE:', 'ALL', len(A), 'CHECK rows identical (n, reach count, ex-gap-day reach count, settled<=-20% count, settled>=+20% count)' if not bad else f'{bad} mismatches')
