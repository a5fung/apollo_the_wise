"""#584 10-15 VERIFIER: column x comparator grid (one-sided p) from counts reproduced in z4_stats.out, plus the 10-13 gap-matched p=0.66 reproduction
(counts from _584_rerun_1013/a2_sweep.out section 3). Note: z2_rows.out ends with a psql 'unterminated quoted string' from an apostrophe in an \\echo line
AFTER the COPY (444 rows) and the SPLITS query (35 rows) completed; both result sets are intact."""
import math
def fg(a, n1, c, n2):
    b, d = n1 - a, n2 - c; k = a + c; N = n1 + n2
    return sum(math.comb(n1, x) * math.comb(n2, k - x) / math.comb(N, k) for x in range(a, min(n1, k) + 1))
def bg(k, n, p=.082): return sum(math.comb(n, x) * p ** x * (1 - p) ** (n - x) for x in range(k, n + 1))
L = []
GM = (4, 44)   # gap-matched admitted, H20 clean, reach_in = reach_ex = 4
for lvl, n, kin, kex in (('$10M', 73, 15, 11), ('$25M', 40, 7, 3), ('$50M', 19, 6, 3)):
    L.append(f'{lvl} n={n}: ex x gap-matched {fg(kex, n, *GM):.3f} | ex x 8.2% {bg(kex, n):.4f} | incl x gap-matched {fg(kin, n, *GM):.3f} | incl x 8.2% {bg(kin, n):.4f}')
L.append(f'10-13 reproduction: REJ g10 $10M incl 5/49 vs ADM g10 4/38 = {fg(5, 49, 4, 38):.3f} (the recorded p=0.66 => 10-13 control read the INCL column); ex 4/49 vs 4/38 = {fg(4, 49, 4, 38):.3f}')
open('z6_grid.out', 'w').write('\n'.join(L) + '\n'); print('\n'.join(L))
