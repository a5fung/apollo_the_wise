#!/usr/bin/env python3
"""Independent recount of the #705 Track A label->tl-event join.

Written from docs/analysis/cb_track_a_filter_prereg_2026-10-23.md section 2 / 9 ONLY (01_join_labels.py not read).
Inputs are the identifier-only extracts made by extract_cands.awk / extract_watch.awk (date filter applied at read:
era B = split 'discovery' and D,E <= 2024-12-31). No price, return, stop, exit or outcome column is touched.

Rules taken from the doc:
  era A = screen_date <= 2022-01-03 (calendar cb702_pre_v2/sessions.txt), era B = later (SPY dates of cb702 export <= 2024-12-31)
  s0 = last session <= screen_date; window E in [s0-10, s0+20]; delta = idx(E) - idx(s0)
  nearest event by |delta| (first breaks and retriggers alike), tie -> later E (larger delta)
  grades exploded (a 'best,bought' label counts under both)
"""
import csv, gzip, bisect, collections, datetime, statistics, sys, os
import numpy as np

H = os.path.dirname(os.path.abspath(__file__))
DATA = '/Users/alvinfung/apollo_data'
OUT = []
def P(*a):
    s = ' '.join(str(x) for x in a)
    print(s); OUT.append(s)

# ---------------------------------------------------------------- calendars
def load_cal(p):
    c = [l.strip() for l in open(p) if l.strip()]
    return c, {d: i for i, d in enumerate(c)}
calA, ixA = load_cal(f'{H}/spyA.txt')
calB, ixB = load_cal(f'{H}/spyB.txt')
CAL = {'A': (calA, ixA), 'B': (calB, ixB)}
ERA_CUT = '2022-01-03'

# ---------------------------------------------------------------- labels
lab_all = list(csv.DictReader(open(f'{DATA}/cb702/qm_streams/vision/grades_labels.tsv'), delimiter='\t'))
labs = [r for r in lab_all if r['status'] == 'attributed']
P('## labels: file rows', len(lab_all), '| attributed', len(labs))
gs = collections.Counter(r['grade'] for r in labs)
P('- grade strings', dict(gs))
tok = collections.Counter(t for r in labs for t in r['grade'].split(','))
P('- exploded', dict(tok), '| distinct tickers', len({r['screen_ticker'] for r in labs}),
  '| distinct (ticker, screen_date)', len({(r['screen_ticker'], r['screen_date']) for r in labs}))
P('- screen dates', min(r['screen_date'] for r in labs), max(r['screen_date'] for r in labs),
  '| by year', dict(sorted(collections.Counter(r['screen_date'][:4] for r in labs).items())))
for r in labs:
    r['era'] = 'A' if r['screen_date'] <= ERA_CUT else 'B'
    r['toks'] = r['grade'].split(',')
P('- era split', dict(collections.Counter(r['era'] for r in labs)))

# ---------------------------------------------------------------- symbol resolution
symsA = {l.strip() for l in open(f'{H}/symsA.txt') if l.strip()}
symsB = {l.strip() for l in open(f'{H}/symsB.txt') if l.strip()}
P('- export symbols A', len(symsA), 'B (<=2024-12-31)', len(symsB))
refetch = {}
for r in csv.DictReader(open(f'{DATA}/cb702_pre/survivorship_1023/merged_trial2/refetch_dropped.tsv'), delimiter='\t'):
    reason = r['reason']
    if '_twin_of_' in reason:
        tgt = reason.split('_twin_of_')[1]
        tgt = tgt.split('(')[0]
        refetch[r['symbol']] = tgt
rename = {r['polygon_ticker']: r['alpaca_symbol'] for r in
          csv.DictReader(open(f'{DATA}/cb702/qm_streams/ext_2016_2022/rename_map.tsv'), delimiter='\t')}
dedupe = {r['dropped_symbol']: r['kept_symbol'] for r in
          csv.DictReader(open(f'{DATA}/cb702_pre_v2/dedupe_applied.tsv'), delimiter='\t')}
def resolve(sym, era):
    S = symsA if era == 'A' else symsB
    if sym in S: return sym, 'own'
    for name, m in (('refetch_dropped', refetch), ('rename_map', rename), ('dedupe_applied', dedupe)):
        t = m.get(sym)
        if t and t in S: return t, name
    return None, 'unresolved'
how = {'A': collections.Counter(), 'B': collections.Counter()}
ex = collections.defaultdict(set)
for r in labs:
    r['sym'], h = resolve(r['screen_ticker'], r['era'])
    how[r['era']][h] += 1
    if h not in ('own',): ex[(r['era'], h)].add((r['screen_ticker'], r['sym']))
P('## symbol resolution', {k: dict(v) for k, v in how.items()})
for k, v in sorted(ex.items()): P('   ', k, sorted(v))

# ---------------------------------------------------------------- candidates / events
def load_events(path, kfilter, era):
    cal, ix = CAL[era]
    ev = collections.defaultdict(list)
    n = 0
    for r in csv.DictReader(open(path), delimiter='\t'):
        if r['K'] not in kfilter: continue
        iE = ix[r['E']]
        ev[(r['K'], r['ticker'])].append((iE, int(r['retrigger']), r['base_id'], r['E'], int(r['C1']) if 'C1' in r and r['C1'] != '' else -1, r['retrigger_chain']))
        n += 1
    for k in ev: ev[k].sort()
    return ev, n
EVA, nA = load_events(f'{H}/candA.tsv', {'tl', 'com'}, 'A')
EVB, nB = load_events(f'{H}/candB_main.tsv', {'tl', 'k5', 'k10', 'full'}, 'B')
EVBc, nBc = load_events(f'{H}/candB_com.tsv', {'com'}, 'B')
EVB.update(EVBc)
EV = {'A': EVA, 'B': EVB}
def count_k(ev, k):
    rows = [e for (kk, t), L in ev.items() if kk == k for e in L]
    return len(rows), sum(1 for e in rows if e[1] == 0)
for era, ev in EV.items():
    for k in sorted({kk for (kk, t) in ev}):
        n, f = count_k(ev, k)
        rng = [e[3] for (kk, t), L in ev.items() if kk == k for e in L]
        P(f'## events era {era} K={k}: rows {n} first breaks {f} E {min(rng)}..{max(rng)}')

# tl E range (index) per era
ERANGE = {}
for era in 'AB':
    iEs = [e[0] for (kk, t), L in EV[era].items() if kk == 'tl' for e in L]
    ERANGE[era] = (min(iEs), max(iEs))
P('- tl E index range', ERANGE, calA[ERANGE['A'][0]], calA[ERANGE['A'][1]], calB[ERANGE['B'][0]], calB[ERANGE['B'][1]])

# ---------------------------------------------------------------- watch rows
WATCH = {}      # era -> ticker -> {iW: [(pole_date, C0_tl)]}
WROWS = {}
for era, path in (('A', f'{H}/watchA.tsv'), ('B', f'{H}/watchB.tsv')):
    cal, ix = CAL[era]
    w = collections.defaultdict(lambda: collections.defaultdict(list))
    n = skip = 0
    for r in csv.DictReader(open(path), delimiter='\t'):
        i = ix.get(r['watch_date'])
        if i is None: skip += 1; continue
        w[r['ticker']][i].append((r['pole_date'], int(r['C0_tl'])))
        n += 1
    WATCH[era] = w; WROWS[era] = (n, skip)
    multi = sum(1 for t in w for i, L in w[t].items() if len(L) > 1)
    P(f'## watch era {era}: rows {n} (not on calendar {skip}) tickers ever {len(w)} | (ticker,date) with >1 row: {multi}')
# label-symbol-restricted watch rows (advisor checksum: 26558 / 16118 per design agent)
for era in 'AB':
    syms = {r['sym'] for r in labs if r['era'] == era and r['sym']}
    n = sum(len(L) for t in syms if t in WATCH[era] for L in WATCH[era][t].values())
    P(f'- watch rows for the {len(syms)} resolved label symbols era {era}: {n}')

# ---------------------------------------------------------------- per-label join
def nearest(evlist, i0, first_only=False):
    """events list sorted by iE; window E in [i0-10, i0+20]; nearest by |delta|, tie -> larger delta (later E)"""
    best = None
    for e in evlist:
        d = e[0] - i0
        if d < -10 or d > 20: continue
        if first_only and e[1] != 0: continue
        key = (abs(d), -d)
        if best is None or key < best[0]: best = (key, d, e)
    return None if best is None else (best[1], best[2])

def window_events(evlist, i0):
    return [e for e in evlist if -10 <= e[0] - i0 <= 20]

nonsess = collections.Counter()
for r in labs:
    cal, ix = CAL[r['era']]
    i0 = bisect.bisect_right(cal, r['screen_date']) - 1
    r['i0'] = i0; r['s0'] = cal[i0]
    if cal[i0] != r['screen_date']: nonsess[r['era']] += 1
    lo, hi = i0 - 10, i0 + 20
    Emin, Emax = ERANGE[r['era']]
    if hi < Emin or lo > Emax: r['cov'] = 'none'
    elif lo >= Emin and hi <= Emax: r['cov'] = 'full'
    else: r['cov'] = 'partial'
P('## s0 mapped from a non-session date', dict(nonsess))
for era in 'AB':
    c = collections.Counter(r['cov'] for r in labs if r['era'] == era)
    P(f'- coverage era {era}: labels {sum(c.values())}', dict(c))
    P('    coverage none by month', sorted(collections.Counter(r['screen_date'][:7] for r in labs if r['era'] == era and r['cov'] == 'none').items()))

def do_join(K, W=1):
    for r in labs:
        era = r['era']
        L = EV[era].get((K, r['sym']), []) if r['sym'] else []
        r[f'win_{K}'] = window_events(L, r['i0'])
        nb = nearest(L, r['i0'])
        r[f'near_{K}'] = nb
        nf = nearest(L, r['i0'], first_only=True)
        r[f'nearf_{K}'] = nf
for K in ('tl', 'com', 'k5', 'k10', 'full'):
    do_join(K)

# ---------------------------------------------------------------- funnel
watched_ever = {era: set(WATCH[era]) for era in 'AB'}
def watch_in_window(r, mode):
    w = WATCH[r['era']].get(r['sym'], {})
    lo, hi = (r['i0'] - 10, r['i0'] + 20) if mode == 'W1' else (r['i0'] - 11, r['i0'] + 19)
    return any(lo <= i <= hi for i in w)
for mode in ('W1', 'W2'):
    P(f'## FUNNEL (watch-row-in-window mode {mode}: ' + ('watch_date in [s0-10,s0+20]' if mode == 'W1' else 'watch_date in [s0-11,s0+19] i.e. D=E-1 for E in window') + ')')
    for era in 'AB':
        cat = collections.Counter(); matched_nowatch = 0
        for r in labs:
            if r['era'] != era: continue
            if r['cov'] == 'none': cat['none'] += 1; continue
            if r['sym'] is None: cat['unresolved'] += 1; continue
            if r['sym'] not in watched_ever[era]: cat['never_watched'] += 1; continue
            matched = r['near_tl'] is not None
            ww = watch_in_window(r, mode)
            if matched:
                cat['matched'] += 1
                if not ww: matched_nowatch += 1
            elif ww: cat['watchrow_no_tl_event'] += 1
            else: cat['no_watchrow_in_window'] += 1
        tot = sum(cat.values())
        P(f'- era {era}: labels {tot}', dict(cat), '| matched-with-no-watch-row-in-window', matched_nowatch)
# never-watched untyped count
sic = {}
for l in open(f'{DATA}/cb702_pre_v2/cb702_sic.psv'):
    p = l.rstrip('\n').split('|')
    sic[p[0]] = p
for era in 'AB':
    nw = [r for r in labs if r['era'] == era and r['cov'] != 'none' and r['sym'] and r['sym'] not in watched_ever[era]]
    untyped = [r for r in nw if r['sym'] not in sic or not (len(sic[r['sym']]) > 5 and sic[r['sym']][5])]
    P(f'- era {era} never-watched labels {len(nw)} symbols {len({r["sym"] for r in nw})} | not in SIC file / no type {len(untyped)}')
    P('   top', collections.Counter(r['sym'] for r in nw).most_common(12))

# ---------------------------------------------------------------- join rates
def rate_rows(era, grade, K='tl'):
    rs = [r for r in labs if r['era'] == era and grade in r['toks'] and r['cov'] != 'none']
    m = [r for r in rs if r[f'near_{K}'] is not None]
    full = [r for r in rs if r['cov'] == 'full']
    fm = [r for r in full if r[f'near_{K}'] is not None]
    retr = sum(1 for r in m if r[f'near_{K}'][1][1] == 1)
    fb = sum(1 for r in rs if any(e[1] == 0 for e in r[f'win_{K}']))
    multi = sum(1 for r in rs if len(r[f'win_{K}']) > 1)
    return rs, m, full, fm, retr, fb, multi
P('## JOIN RATE (tl): era grade | matched/n | full-only | >1 event | nearest retrigger | first break in window')
JR = {}
for era in 'AB':
    for g in ('bought', 'not_yet', 'best'):
        rs, m, full, fm, retr, fb, multi = rate_rows(era, g)
        JR[(era, g)] = (len(m), len(rs), len(fm), len(full), retr, fb, multi)
        pc = f'{100*len(m)/len(rs):.1f}%' if rs else '-'
        P(f'- {era} {g:8s}: {len(m)}/{len(rs)} ({pc}) | full-only {len(fm)}/{len(full)} | >1 event {multi} | nearest retrigger {retr} | first break in window {fb}')
for era in 'AB':
    rs = [r for r in labs if r['era'] == era and r['cov'] != 'none']
    m = [r for r in rs if r['near_tl'] is not None]
    P(f'- all labels era {era}: {len(m)}/{len(rs)} ({100*len(m)/len(rs):.1f}%)')
P('## JOIN RATE other levels')
for K, era in (('com', 'A'), ('com', 'B'), ('k5', 'B'), ('k10', 'B'), ('full', 'B')):
    for g in ('bought', 'not_yet'):
        rs, m, *_ = rate_rows(era, g, K)
        P(f'- {era} K={K} {g}: {len(m)}/{len(rs)}')

# ---------------------------------------------------------------- before/on/after
def split_stats(deltas, label):
    n = len(deltas)
    if n == 0: P(f'- {label}: n = 0'); return None
    d = np.array(deltas)
    b = int((d >= 1).sum()); o = int((d == 0).sum()); a = int((d <= -1).sum())
    w = int(((d >= -2) & (d <= 1)).sum()); w1 = int(((d >= -1) & (d <= 1)).sum())
    q = np.percentile(d, [25, 50, 75])
    P(f'- {label}: n = {n} | BEFORE(>=+1) {b} ({100*b/n:.1f}%) | ON(0) {o} ({100*o/n:.1f}%) | AFTER(<=-1) {a} ({100*a/n:.1f}%) | within[-1,+1] {w1} | within[-2,+1] {w} ({100*w/n:.1f}%) | median {q[1]:+.1f} quartiles {q[0]:+.1f}..{q[2]:+.1f}')
    h = collections.Counter(deltas)
    P('    hist', ' '.join(f'{k:+d}:{h[k]}' for k in sorted(h)))
    return dict(n=n, b=b, o=o, a=a, w=w)
P('## POSITION relative to E (delta>0 = label BEFORE breakout)')
SPL = {}
for era in 'AB':
    for g in ('bought', 'not_yet', 'best'):
        rs = [r for r in labs if r['era'] == era and g in r['toks'] and r['cov'] != 'none']
        SPL[(era, g, 'nearest')] = split_stats([r['near_tl'][0] for r in rs if r['near_tl'] is not None], f'{era} {g} nearest tl event')
        SPL[(era, g, 'first')] = split_stats([r['nearf_tl'][0] for r in rs if r['nearf_tl'] is not None], f'{era} {g} nearest FIRST BREAK')

# distinct events (era, sym, E)
def event_key(r, era=None): return (r['era'], r['sym'], r['near_tl'][1][3])
def distinct_events(era, g):
    d = {}
    for r in labs:
        if r['era'] != era or g not in r['toks'] or r['cov'] == 'none' or r['near_tl'] is None: continue
        d.setdefault(event_key(r), []).append(r['near_tl'][0])
    return d
P('## DISTINCT bought events (stock,E): delta rule is undefined in the doc -> variants')
for era in 'AB':
    d = distinct_events(era, 'bought')
    P(f'- era {era} distinct (stock,E) bought events: {len(d)}')
    # variants for the event's delta
    v_first = [v[0] for v in d.values()]                         # first label in file order
    v_min = [min(v, key=lambda x: (abs(x), -x)) for v in d.values()]  # label with smallest |delta|
    v_all_unique = sorted({(k, x) for k, v in d.items() for x in v})  # unique (event, delta) pairs
    split_stats(v_first, f'  {era} distinct events, delta of first label in file order')
    split_stats(v_min, f'  {era} distinct events, delta of the label closest to E')
    split_stats([x for (_, x) in v_all_unique], f'  {era} distinct (event,delta) pairs')
    mx = [x for v in d.values() for x in [max(v)]]
    split_stats(mx, f'  {era} distinct events, delta = max over labels')
    mn = [min(v) for v in d.values()]
    split_stats(mn, f'  {era} distinct events, delta = min over labels')

# ---------------------------------------------------------------- watch state on screen date
def watch_state(era, g):
    rs = [r for r in labs if r['era'] == era and g in r['toks'] and r['cov'] != 'none']
    n = len(rs)
    at = []; anyw = 0
    for r in rs:
        w = WATCH[era].get(r['sym'], {}) if r['sym'] else {}
        if r['i0'] in w: at.append(r)
        if any(r['i0'] - 10 <= i <= r['i0'] + 20 for i in w): anyw += 1
    withtl = [r for r in at if any(c0 == 1 for _, c0 in WATCH[era][r['sym']][r['i0']])]
    # base not yet broken at s0: watch row at s0 -> its pole_date -> base_id sym|pole ; no tl event of that base with iE <= i0
    nb1 = nb1_tl = nb3 = nb4 = 0
    for r in at:
        rows = WATCH[era][r['sym']][r['i0']]
        evs = EV[era].get(('tl', r['sym']), [])
        # V1: any watch row (any pole) at s0 whose base has no tl event E <= s0
        flag = False; flag_tl = False
        for pole, c0 in rows:
            bid = f"{r['sym']}|{pole}"
            broken = any(e[2] == bid and e[0] <= r['i0'] for e in evs)
            if not broken:
                flag = True
                if c0 == 1: flag_tl = True
        nb1 += flag; nb1_tl += flag_tl
        # V3: nearest matched event is same base as a watch row at s0 and E > s0
        nr = r['near_tl']
        if nr is not None and nr[0] > 0 and any(f"{r['sym']}|{pole}" == nr[1][2] for pole, c0 in rows): nb3 += 1
        # V4: nearest event exists with E > s0 (any base)
        if nr is not None and nr[0] > 0: nb4 += 1
    return dict(n=n, at=len(at), withtl=len(withtl), nb_V1=nb1, nb_V1_c0tl=nb1_tl, nb_V3=nb3, nb_V4_at=nb4, anyw=anyw)
P('## WATCH STATE at s0  (doc: A bought 624: at 176, tl 153, not-yet-broken 39, anywhere 448 | not_yet 128: 50/50/13/97 | best 60: 17/15/4/38 | B bought 28: 8/8/5/14)')
WS = {}
for era, g in (('A', 'bought'), ('A', 'not_yet'), ('A', 'best'), ('B', 'bought'), ('B', 'not_yet'), ('B', 'best')):
    WS[(era, g)] = watch_state(era, g)
    P(f'- {era} {g}:', WS[(era, g)])

# ---------------------------------------------------------------- same-day population
P('## SAME-DAY / WEEK population')
def iso(d):
    y, w, _ = datetime.date.fromisoformat(d).isocalendar(); return (y, w)
STR = {}
for era in 'AB':
    allE = collections.Counter(); firstE = collections.Counter()
    wkall = collections.Counter(); wkfirst = collections.Counter()
    for (k, t), L in EV[era].items():
        if k != 'tl': continue
        for e in L:
            allE[e[3]] += 1; wkall[iso(e[3])] += 1
            if e[1] == 0: firstE[e[3]] += 1; wkfirst[iso(e[3])] += 1
    STR[era] = (allE, firstE, wkall, wkfirst)
    P(f'- era {era} weekly stream: weeks {len(wkall)} | all tl rows median {np.median(list(wkall.values())):.0f} | first breaks median {np.median([wkfirst.get(w,0) for w in wkall]):.0f}'
      f' (first-break median over weeks with >=1 first break: {np.median(list(wkfirst.values())):.0f}, n={len(wkfirst)})')
for era, g in (('A', 'bought'), ('A', 'not_yet'), ('B', 'bought')):
    d = distinct_events(era, g)
    allE, firstE, wkall, wkfirst = STR[era]
    ev_rows = {}
    for (er, sym, E) in d:
        L = EV[era][('tl', sym)]
        row = next(e for e in L if e[3] == E)
        ev_rows[(sym, E)] = row
    oth = [allE[E] - 1 for (s, E) in ev_rows]
    othf_excl = [firstE[E] - (1 if ev_rows[(s, E)][1] == 0 else 0) for (s, E) in ev_rows]
    othf_all = [firstE[E] for (s, E) in ev_rows]
    wk_all = [wkall[iso(E)] for (s, E) in ev_rows]
    wk_first = [wkfirst[iso(E)] for (s, E) in ev_rows]
    wk_all_x = [wkall[iso(E)] - 1 for (s, E) in ev_rows]
    P(f'- {era} {g} events n={len(ev_rows)}: OTHER tl rows same day median {np.median(oth):.0f} mean {np.mean(oth):.1f} | first-break others (self excluded if first) median {np.median(othf_excl):.0f} mean {np.mean(othf_excl):.1f}'
      f' | first breaks that day incl self median {np.median(othf_all):.0f} mean {np.mean(othf_all):.1f}')
    P(f'    ISO week: all rows (incl self) median {np.median(wk_all):.0f} mean {np.mean(wk_all):.1f} | excl self median {np.median(wk_all_x):.0f} | first breaks in week median {np.median(wk_first):.0f}')

# ---------------------------------------------------------------- distinct events overall
P('## DISTINCT EVENTS (era A / era B)')
for era in 'AB':
    d = collections.defaultdict(list)
    for r in labs:
        if r['era'] != era or r['cov'] == 'none' or r['near_tl'] is None: continue
        d[(r['sym'], r['near_tl'][1][3])].append(r)
    byg = collections.Counter()
    for k, rs in d.items():
        for g in {t for r in rs for t in r['toks']}: byg[g] += 1
    both = sum(1 for rs in d.values() if {'bought', 'not_yet'} <= {t for r in rs for t in r['toks']})
    nl = collections.Counter(min(len(rs), 3) for rs in d.values())
    # alternative: count exploded tokens
    nl_tok = collections.Counter(min(sum(len(r['toks']) for r in rs), 3) for rs in d.values())
    bases = {(s, next(e for e in EV[era][('tl', s)] if e[3] == E)[2]) for (s, E) in d}
    chains_raw = {(s, next(e for e in EV[era][('tl', s)] if e[3] == E)[5]) for (s, E) in d}
    syms = {s for (s, E) in d}
    P(f'- era {era}: distinct (sym,E) events {len(d)} | by grade {dict(byg)} | bought&not_yet both {both} | distinct bases {len(bases)} | stocks {len(syms)} | labels/event {dict(nl)} (tokens: {dict(nl_tok)})')
    bought_ev = [(s, E) for (s, E), rs in d.items() if any('bought' in r['toks'] for r in rs)]
    byyear = collections.Counter(E[:4] for s, E in bought_ev)
    byyear_s0 = collections.Counter(r['screen_date'][:4] for (s, E), rs in d.items() if any('bought' in r['toks'] for r in rs) for r in rs[:1])
    days = {E for s, E in bought_ev}; weeks = {iso(E) for s, E in bought_ev}
    c1 = sum(next(e for e in EV[era][('tl', s)] if e[3] == E)[4] for s, E in bought_ev)
    P(f'    bought events {len(bought_ev)}: by E-year {dict(sorted(byyear.items()))} | distinct days {len(days)} | ISO weeks {len(weeks)} | C1 {c1}')
    tot_tl = sum(len(L) for (k, t), L in EV[era].items() if k == 'tl'); c1_tl = sum(e[4] for (k, t), L in EV[era].items() if k == 'tl' for e in L)
    P(f'    C1 share of tl stream {c1_tl}/{tot_tl} = {100*c1_tl/tot_tl:.2f}% ; among bought events {100*c1/max(1,len(bought_ev)):.1f}%')

# ---------------------------------------------------------------- placebo (outcome-free)
P('## PLACEBO (era A, symbols with a bought label): sessions t with a watch row in [t-10,t+20] and a tl event in [t-10,t+20], t not within +-20 of any label of that symbol')
def placebo(symset, label_filter, wmode='W1'):
    cal, ix = CAL['A']
    b = o = a = tot = tot_w = 0
    dl = []
    for sym in symset:
        ls = [r['i0'] for r in labs if r['era'] == 'A' and r['sym'] == sym and label_filter(r)]
        w = sorted(WATCH['A'].get(sym, {}))
        ev = EV['A'].get(('tl', sym), [])
        evi = np.array([e[0] for e in ev]) if ev else np.array([], dtype=int)
        if not w: continue
        for t in range(len(cal)):
            if any(abs(t - i) <= 20 for i in ls): continue
            lo, hi = (t - 10, t + 20) if wmode == 'W1' else (t - 11, t + 19)
            j = bisect.bisect_left(w, lo)
            if j >= len(w) or w[j] > hi: continue
            tot_w += 1
            if evi.size == 0: continue
            d = evi - t
            m = (d >= -10) & (d <= 20)
            if not m.any(): continue
            dd = d[m]
            k = np.lexsort((-dd, np.abs(dd)))[0]
            dl.append(int(dd[k]))
    return tot_w, dl
bought_syms = {r['sym'] for r in labs if r['era'] == 'A' and 'bought' in r['toks'] and r['sym']}
for lbl, flt in (('any attributed label of the symbol excluded', lambda r: True), ('only bought labels excluded', lambda r: 'bought' in r['toks'])):
    for wm in ('W1', 'W2'):
        tw, dl = placebo(bought_syms, flt, wm)
        P(f'- [{lbl}; watch window {wm}] bought symbols {len(bought_syms)}: sessions with a watch row {tw}, with a tl event {len(dl)}')
        split_stats(dl, f'  placebo ({lbl}; {wm})')

# ---------------------------------------------------------------- positive controls
P('## POSITIVE CONTROLS')
for fid in ('g_0466', 'b1_00', 'g_0957'):
    r = next(x for x in labs if x['frame_id'] == fid)
    nr = r['near_tl']
    ev = nr[1] if nr else None
    wk = WATCH[r['era']].get(r['sym'], {}).get(r['i0'])
    P(f"- {fid}: {r['screen_ticker']} screen {r['screen_date']} grade {r['grade']} era {r['era']} s0 {r['s0']} | nearest tl event "
      + (f"E {ev[3]} delta {nr[0]:+d} retrigger {ev[1]} base {ev[2]}" if nr else 'NONE')
      + f" | watch row at s0: {wk} | confirm_adr {r['confirm_adr']} confirm_price {r['confirm_price']} daily_tab {r['daily_tab']} triple_agree {r['triple_agree']} dt_s {r['dt_s']} pair {r['frame_pair']} ocr {r['ocr_ticker']}")

# ---------------------------------------------------------------- drift-robust "first break" sensitivity (retrigger_chain == 0)
P('## FIRST-BREAK DEFINITION SENSITIVITY: doc first break = retrigger==0 ; chain-first = retrigger_chain==0 (retrigger==0 & chain==1 = a drift re-fire of the same line)')
def nearest_chain_first(evlist, i0):
    best = None
    for e in evlist:
        d = e[0] - i0
        if d < -10 or d > 20 or e[5] != '0': continue
        key = (abs(d), -d)
        if best is None or key < best[0]: best = (key, d, e)
    return None if best is None else (best[1], best[2])
for era in 'AB':
    rs = [r for r in labs if r['era'] == era and 'bought' in r['toks'] and r['cov'] != 'none']
    dl = []
    for r in rs:
        L = EV[era].get(('tl', r['sym']), []) if r['sym'] else []
        nb = nearest_chain_first(L, r['i0'])
        if nb: dl.append(nb[0])
    split_stats(dl, f'{era} bought nearest CHAIN-FIRST break')
    m = [r for r in rs if r['near_tl'] is not None]
    nchain = sum(1 for r in m if r['near_tl'][1][5] == '1')
    nre = sum(1 for r in m if r['near_tl'][1][1] == 1)
    P(f'   {era} bought matched {len(m)}: nearest event retrigger==1 {nre} ({100*nre/len(m):.1f}%) | retrigger_chain==1 {nchain} ({100*nchain/len(m):.1f}%)')
    firstE_c = collections.Counter(); wk_c = collections.Counter(); wk_all = collections.Counter()
    for (k, t), L in EV[era].items():
        if k != 'tl': continue
        for e in L:
            wk_all[iso(e[3])] += 1
            if e[5] == '0': firstE_c[e[3]] += 1; wk_c[iso(e[3])] += 1
    P(f'   {era} weekly CHAIN-FIRST median {np.median([wk_c.get(w,0) for w in wk_all]):.0f} (doc first-break 53/73) ; chain-first rows {sum(wk_c.values())}')
    d = distinct_events(era, 'bought')
    othc = []
    for (er, sym, E) in d:
        e = next(x for x in EV[era][('tl', sym)] if x[3] == E)
        othc.append(firstE_c[E] - (1 if e[5] == '0' else 0))
    P(f'   {era} bought events: same-day OTHER chain-first median {np.median(othc):.0f} mean {np.mean(othc):.1f}')

# ---------------------------------------------------------------- second pass: variants chosen AFTER reading 01_join_labels.py (labelled as such)
P('## SECOND PASS (after reading the design script): no_break_yet variants, placebo range, chain count, never-watched union')
# (V5) the design script's rule: tl event of the same symbol with E <= s0 whose candidate pole_date column == the watch row's pole_date
# (V6) drift-robust: map the watch row's (symbol, pole_date) to a base_id through ANY tl candidate row with that pole_date, broken = a tl event of that base_id with E <= s0
pd2base = collections.defaultdict(set)
for (k, t), L in EV['A'].items():
    pass
# need candidate pole_date column; reload with it
import csv as _csv
cand_pole = {'A': collections.defaultdict(list), 'B': collections.defaultdict(list)}
for era, path in (('A', f'{H}/candA.tsv'), ('B', f'{H}/candB_main.tsv')):
    cal, ix = CAL[era]
    for r in _csv.DictReader(open(path), delimiter='\t'):
        if r['K'] != 'tl': continue
        cand_pole[era][r['ticker']].append((ix[r['E']], r['pole_date'], r['base_id']))
def nb_variants(era, g):
    rs = [r for r in labs if r['era'] == era and g in r['toks'] and r['cov'] != 'none']
    v5 = v6 = 0
    for r in rs:
        w = WATCH[era].get(r['sym'], {}) if r['sym'] else {}
        if r['i0'] not in w: continue
        rows = w[r['i0']]
        # the design script keys on ONE watch row (ticker, date); (ticker,date) is unique so rows has 1 element
        P_ = rows[0][0]
        evs = cand_pole[era].get(r['sym'], [])
        broke5 = any(iE <= r['i0'] and pdt == P_ for iE, pdt, bid in evs)
        v5 += (not broke5)
        bids = {bid for iE, pdt, bid in evs if pdt == P_}
        broke6 = any(iE <= r['i0'] and bid in bids for iE, pdt, bid in evs)
        v6 += (not broke6)
    return v5, v6
for era, g in (('A', 'bought'), ('A', 'not_yet'), ('A', 'best'), ('B', 'bought'), ('B', 'best')):
    v5, v6 = nb_variants(era, g)
    P(f'- no_break_yet {era} {g}: V5 (pole_date column key) {v5} | V6 (drift-robust base_id) {v6}   [doc 39/13/4/5/0]')
# placebo with t restricted so the whole window sits inside the E range
def placebo2(symset, flt):
    cal, ix = CAL['A']; Emin, Emax = ERANGE['A']
    tot_w = 0; dl = []
    for sym in symset:
        ls = [r['i0'] for r in labs if r['era'] == 'A' and r['sym'] == sym and flt(r)]
        w = sorted(WATCH['A'].get(sym, {}))
        ev = EV['A'].get(('tl', sym), [])
        if not w or not ev: continue
        evi = np.array([e[0] for e in ev])
        for t in range(Emin + 10, Emax - 20 + 1):
            if any(abs(t - i) <= 20 for i in ls): continue
            j = bisect.bisect_left(w, t - 10)
            if j >= len(w) or w[j] > t + 20: continue
            tot_w += 1
            d = evi - t; m = (d >= -10) & (d <= 20)
            if not m.any(): continue
            dd = d[m]; dl.append(int(dd[np.lexsort((-dd, np.abs(dd)))[0]]))
    return tot_w, dl
syms_cov = {r['sym'] for r in labs if r['era'] == 'A' and 'bought' in r['toks'] and r['cov'] != 'none' and r['sym']}
tw, dl = placebo2(syms_cov, lambda r: True)
P(f'- placebo, t restricted to [Emin+10, Emax-20], any attributed label excluded, bought symbols with coverage ({len(syms_cov)}): sessions {tw}, with event {len(dl)}   [doc 51,884 / 42,781]')
split_stats(dl, '  placebo restricted')
syms_ny = {r['sym'] for r in labs if r['era'] == 'A' and 'not_yet' in r['toks'] and r['cov'] != 'none' and r['sym']}
tw2, dl2 = placebo2(syms_ny, lambda r: True)
P(f'- not_yet-symbol placebo: sessions {tw2}, with event {len(dl2)}   [txt 24,735 / 19,999]')
split_stats(dl2, '  not_yet placebo restricted')
# chain count the design script reports = distinct (sym, retrigger_chain flag) ; compare with bases
for era in 'AB':
    d = {}
    for r in labs:
        if r['era'] != era or r['cov'] == 'none' or r['near_tl'] is None: continue
        e = r['near_tl'][1]
        d[(r['sym'], e[3])] = e
    flags = {(s, e[5]) for (s, E), e in d.items()}
    bases = {(s, e[2]) for (s, E), e in d.items()}
    P(f'- era {era}: distinct (sym, retrigger_chain FLAG value) = {len(flags)} ; distinct (sym, base_id) = {len(bases)} ; distinct symbols = {len({s for s,E in d})}   [doc chains 199 / 11]')
# union of never-watched symbols across eras
nw = {r['sym'] for r in labs if r['cov'] != 'none' and r['sym'] and r['sym'] not in watched_ever[r['era']]}
P(f'- never-watched symbols, union of both eras: {len(nw)}   [doc 53]')
# watch rows kept for ALL 283 label symbols (the design txt: 26558 A / 16118 B)
allsyms = {r['sym'] for r in labs if r['sym']}
for era in 'AB':
    n = sum(len(L) for t in allsyms if t in WATCH[era] for L in WATCH[era][t].values())
    P(f'- watch rows era {era} for the union of resolved label symbols ({len(allsyms)}): {n}   [txt 26558 / 16118]')

# ---------------------------------------------------------------- write per-label output
with open(f'{H}/recount_labels.tsv', 'w') as f:
    f.write('frame_id\tera\tsym\tscreen_date\ts0\tgrade\tcov\tnear_E\tdelta\tretrigger\tbase\tn_win\n')
    for r in labs:
        nr = r['near_tl']
        f.write('\t'.join(str(x) for x in (r['frame_id'], r['era'], r['sym'], r['screen_date'], r['s0'], r['grade'], r['cov'],
                nr[1][3] if nr else '', nr[0] if nr else '', nr[1][1] if nr else '', nr[1][2] if nr else '', len(r['win_tl']))) + '\n')
open(f'{H}/recount_out.txt', 'w').write('\n'.join(OUT) + '\n')
