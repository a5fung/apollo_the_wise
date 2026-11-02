"""score.py — JOIN RULE (written BEFORE results.json was opened, 2026-11-01):

Reference = the reconcile's final rows (results.json). The 59 AGREED rows = the rows both blind daters
dated on the same session (57) or one session apart (2: LVGO-4, OPK-1). The 24 GOOD setups = the
reconcile's PRIMARY set (both agree AND final confidence high/medium AND tier A/B). I take both sets
from the reference file's own fields, never by hand.

For each reference row: resolve the ticker to the bars symbol (OSTK->NXH, WTRH->ASAP via the same map
my TSV uses). A MATCH = my TSV has a dated row for the same ticker whose breakout_date is within ONE
SESSION of the reference date (by the session list of the bars = sessions.txt), assigned one-to-one
by nearest date (each of my rows may satisfy at most one reference row; greedy by smallest gap).
A reference row with no such row of mine (no row, undatable, forward, or > 1 session off) = MISS.
Shares are reported on all rows and again EXCLUDING the rows my seen_before_dating.txt lists as tainted.
The GO bar, stated before scoring: GO if >= 85% of the 59 agreed rows match within one session.
"""
import json, re, sys
import pandas as pd
REF = '/private/tmp/claude-501/-Users-alvinfung-apollo-the-wise/d30e3944-e07e-4b44-97de-010acba78d0b/scratchpad/qm0810_reconcile/results.json'
MINE = 'my_0810_dates.tsv'
SESS = [l.strip() for l in open('/Users/alvinfung/apollo_data/cb702_pre_v2/sessions.txt') if l.strip()]
SIDX = {d: i for i, d in enumerate(SESS)}
SYM = {'OSTK': 'NXH', 'WTRH': 'ASAP', 'GSX': 'GOTU', 'SHLL': 'HYLN'}
TAINTED = {'LVGO-4', 'OPK-1', 'TRVN', 'TRVN-1', 'CLSK', 'CLSK-1', 'ACMR-2', 'IDEX', 'IDEX-1', 'MARK', 'MARK-1', 'LVGO-1', 'IBIO-3',
           'INO-3', 'INO-4', 'NVAX', 'NVAX-1', 'RUN', 'RUN-1', 'VSLR', 'VSLR-1', 'DFS', 'DFS-1', 'QUMU', 'QUMU-now', 'SRNE-2'}

ref = json.load(open(REF))
mine = pd.read_csv(MINE, sep='\t', dtype=str).fillna('')
mine = mine[mine.breakout_date != ''].copy()
mine['sym'] = mine.bars_symbol.where(mine.bars_symbol != '', mine.ticker)
mine['si'] = mine.breakout_date.map(SIDX)
mine['used'] = False


def ref_sym(key):
    t = re.split(r'[-\s(]', key)[0].upper()
    return SYM.get(t, t)


def gap(a, b):
    return abs(SIDX[a] - SIDX[b]) if a in SIDX and b in SIDX else 99


def dated(r):
    return bool(re.match(r'\d{4}-\d{2}-\d{2}', str(r.get('final_date', ''))))


agreed = [r for r in ref if r.get('agree') and dated(r)]
primary = [r for r in agreed if r.get('final_confidence') in ('high', 'medium') and r.get('tier') in ('A', 'B') and not r.get('exclude')]
print('reference rows', len(ref), '| agreed+dated', len(agreed), '| primary A+B high/medium', len(primary))
print('agree_kind among agreed:', pd.Series([r.get('agree_kind') for r in agreed]).value_counts().to_dict())

# one-to-one greedy by smallest gap over ALL dated reference rows (so a row of mine is not spent twice)
pairs = []
for r in sorted([r for r in ref if dated(r)], key=lambda r: r['final_date']):
    sym = ref_sym(r['key'])
    cand = mine[(mine.sym == sym) & (~mine.used)]
    best = None
    for i, m in cand.iterrows():
        g = gap(m.breakout_date, r['final_date'])
        if best is None or g < best[0]:
            best = (g, i, m.breakout_date, m.setup_idx)
    if best is not None and best[0] <= 1:
        mine.loc[best[1], 'used'] = True
        pairs.append((r['key'], r['final_date'], best[2], best[0], True))
    else:
        # nearest of mine for the report even if > 1 session
        pairs.append((r['key'], r['final_date'], (best[2] if best else ''), (best[0] if best else None), False))
P = {p[0]: p for p in pairs}


def share(rows, label):
    hit = [r['key'] for r in rows if P[r['key']][4]]
    miss = [r for r in rows if not P[r['key']][4]]
    clean = [r for r in rows if r['key'] not in TAINTED]
    hitc = [r['key'] for r in clean if P[r['key']][4]]
    print(f'\n== {label}: {len(hit)}/{len(rows)} within one session = {100*len(hit)/len(rows):.0f}%  | excluding tainted rows: {len(hitc)}/{len(clean)} = {100*len(hitc)/max(1,len(clean)):.0f}%')
    for r in miss:
        p = P[r['key']]
        print(f"  MISS {r['key']:<10} final {r['final_date']} ({r.get('final_confidence')}, tier {r.get('tier')}) | mine {p[2] or 'none/undated'} gap {p[3]} | his: {r.get('his_grade','')[:60]}")
    return hit, miss


share(agreed, 'AGREED (both daters same/one-session) rows')
share(primary, 'PRIMARY 24 good setups (A+B, high/medium)')
# also: all dated reference rows
alld = [r for r in ref if dated(r)]
share(alld, 'ALL dated reference rows (incl. disputed)')
# my rows that matched nothing, with a date
print('\nMy dated rows unmatched by any reference row:')
for _, m in mine[~mine.used].iterrows():
    print(f"  {m.ticker}-{m.setup_idx} {m.breakout_date} ({m.confidence}, {m.tier}) {m.grade_words[:50]}")
# reference rows left undatable by the reconcile that I dated
print('\nReference undatable rows that I dated:')
for r in ref:
    if not dated(r):
        sym = ref_sym(r['key']); c = mine[mine.sym == sym]
        print(f"  {r['key']:<12} final={r.get('final_date')} | mine: {', '.join(c.breakout_date.tolist()) or 'none'}")
