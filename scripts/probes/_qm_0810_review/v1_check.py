#!/usr/bin/env python3
"""Breakout v1 checked against his dated good setups of the 2020-08-10 review — free, local, analysis only.

v1 = the operator-confirmed starting rules of 2026-10-28 (docs/setups/consolidation_breakout.md "### 2026-10-28";
scripts/probes/_qm_0810_review/dating_calibration.md). A breakout day E qualifies, with D = E - 1 and every measure on
bars <= D except E's own high and volume:
  universe   RAW close(D) >= $5 and the 20-session median dollar volume ending D >= $10M (adjusted close x volume,
             split-invariant, as cb._dollar_vol_median)
  prior move P = the pole top in [D-45, D-10] (cb._pole_top, the module's #592 walk; ties -> the latest);
             high(P) / min low[P-40, P] - 1 >= 0.30 (the module's 41-session pole window)
  base       sessions P+1..D (10..45 long by construction); the module's base anchor: no CLOSE in (P, D] above high(P)
             (`close_above_pole_high`, a named gate — the 'no anchor' variant drops it)
  higher lows min low of D-4..D > the base low (min low of P+1..D)
  SURF       >= 5 consecutive sessions ending at D whose LOW is within 1.0 x ADR(s) x close(s) of ONE of SMA10/20/50
             (ADR(s) = mean of (h-l)/c over the 20 sessions ending s; SMA of closes incl. s; the band uses each session's
             own ADR and close — exactly as the calibration's rlib.py). Variant: the run may switch averages (any-average).
  TIGHTENING mean (h-l)/c of D-4..D <= 1.1 x the mean of D-9..D-5
  LEVEL      the base high = max high of P+1..D (`pivot_full`); high(E) > level (strict)
  VOLUME     volume(E) >= 1.2 x mean volume of D-49..D
  data guard bars D-85..E are consecutive sessions of the calendar (the deepest bar any gate reads is D-85)
RS >= 98 and the market phase are NOT part of v1 here (they need the universe-wide percentile / an index read);
step 2 reports an RS stand-in beside: the 63-session return at D in the top 2% (percentile >= 98, cb.percentile_ranks)
of the names passing the two universe gates at D.

Reads only bars dated 2019-01-02..2020-08-10 (each line's date is tested before the line is kept). No network, no
server, no paid call, no git, no subagents; the only outputs are this file and its printout (v1_check.txt).
Run: PYTHONDONTWRITEBYTECODE=1 python3 v1_check.py > v1_check.txt     (--dev: the setup tickers only, no step 2)
"""
import csv
import gzip
import io
import json
import re
import sys
from collections import defaultdict
from datetime import date, timedelta

import numpy as np
import pandas as pd

sys.dont_write_bytecode = True
REPO = '/Users/alvinfung/apollo_the_wise'
sys.path.insert(0, REPO)
import agents.market_intelligence.consolidation_breakout as cb  # noqa: E402  (read-only: _pole_top, percentile_ranks)

DATA = '/Users/alvinfung/apollo_data/cb702_pre_v2/'
BARS = DATA + 'daily_closes_all.csv.gz'
RAW = DATA + 'daily_raw_close.csv.gz'
SESS = DATA + 'sessions.txt'
TSV = REPO + '/scripts/probes/_qm_0810_review/dated_setups_2020-08-10.tsv'
START, END = '2019-01-02', '2020-08-10'
WIN_LO, WIN_HI = '2020-02-03', '2020-08-10'      # his names' window (breakout day E)
WK_LO, WK_HI = '2020-02-03', '2020-08-07'        # step 2 window (E), Mon 02-03 .. Fri 08-07 = 27 weeks

MIN_PRICE, MIN_DV = 5.0, 10_000_000.0
PRIOR_MIN, POLE_LB, BASE_MIN, BASE_MAX = 0.30, 40, 10, 45
SURF_N, SURF_K, TIGHT_MAX, VOL_X, RS_TOP = 5, 1.0, 1.1, 1.2, 98.0
DEEP = BASE_MAX + POLE_LB                        # 85: the deepest look-back (pole low window) from D
GATES = ['universe', 'prior_move', 'close_above_pole_high', 'higher_lows', 'surf', 'tightening', 'level', 'volume']

# the calibration's keys, by (bars ticker, his breakout day): the TSV filter below must reproduce exactly these
PRIMARY = {('CELH', '2020-06-23'): 'CELH-1', ('CELH', '2020-08-05'): 'CELH-3', ('CODX', '2020-04-16'): 'CODX-1',
           ('CVNA', '2020-06-02'): 'CVNA-1', ('CWH', '2020-05-06'): 'CWH-2', ('LVGO', '2020-07-06'): 'LVGO-4',
           ('NVAX', '2020-06-15'): 'NVAX', ('OPK', '2020-07-17'): 'OPK-2', ('NXH', '2020-06-19'): 'OSTK-2',
           ('PLUG', '2020-06-23'): 'PLUG', ('SRNE', '2020-07-30'): 'SRNE-2', ('PRTS', '2020-07-08'): 'PRTS',
           ('DFS', '2020-05-26'): 'DFS', ('QUMU', '2020-08-10'): 'QUMU', ('ARCT', '2020-07-13'): 'ARCT',
           ('HL', '2020-08-04'): 'HL', ('IBIO', '2020-07-15'): 'IBIO-1', ('OPK', '2020-06-29'): 'OPK-1',
           ('OPK', '2020-08-06'): 'OPK-3', ('PENN', '2020-06-23'): 'PENN-2', ('PENN', '2020-08-06'): 'PENN-3',
           ('RUN', '2020-08-04'): 'RUN', ('TTOO', '2020-08-10'): 'TTOO', ('NAIL', '2020-08-10'): 'NAIL'}
SECONDARY = {('CLSK', '2020-07-22'): 'CLSK', ('INO', '2020-04-20'): 'INO-3', ('INO', '2020-06-23'): 'INO-4',
             ('TRVN', '2020-07-15'): 'TRVN'}

OUT = []


def P(*a):
    OUT.append(' '.join(str(x) for x in a))


# ───────────────────────────── the setups ─────────────────────────────
def load_setups():
    rows = list(csv.DictReader(open(TSV), delimiter='\t'))
    prim, sec, other = [], [], defaultdict(list)
    for r in rows:
        w = r['why']
        m = re.match(r'\[tier (\w)', w)
        tier = m.group(1) if m else None
        bt = re.search(r'\[bars (\w+);', w)
        tk = bt.group(1) if bt else None
        if r['final_date'] != 'undatable' and tk:
            other[tk].append((r['final_date'], tier, r['final_confidence'], r['stock'][:40]))
        if tier not in ('A', 'B') or r['final_confidence'] not in ('high', 'medium') or 'EXCLUDED' in w \
                or r['final_date'] == 'undatable':
            continue
        rec = dict(t=tk, e=r['final_date'], tier=tier, conf=r['final_confidence'], stock=r['stock'],
                   meas=json.loads(r['measures']))
        (prim if r['agree'] == 'True' else sec).append(rec)
    for lst, ref in ((prim, PRIMARY), (sec, SECONDARY)):
        got = {(x['t'], x['e']) for x in lst}
        assert got == set(ref), ('TSV filter does not reproduce the calibration set', got ^ set(ref))
        for x in lst:
            x['key'] = ref[(x['t'], x['e'])]
    order = list(PRIMARY.values())
    prim.sort(key=lambda x: order.index(x['key']))
    return prim, sec, other


# ───────────────────────────── data ─────────────────────────────
def read_lines(path, keep_t=None):
    kept = []
    with gzip.open(path, 'rt') as f:
        for line in f:
            t, d, _ = line.split(',', 2)
            if START <= d <= END and (keep_t is None or t in keep_t):
                kept.append(line)
    return kept


def load(keep_t=None):
    b = pd.read_csv(io.StringIO(''.join(read_lines(BARS, keep_t))), header=None,
                    names=['t', 'date', 'o', 'h', 'l', 'c', 'v'], na_filter=False,
                    dtype={'t': str, 'date': str, 'o': float, 'h': float, 'l': float, 'c': float, 'v': float})
    r = pd.read_csv(io.StringIO(''.join(read_lines(RAW, keep_t))), header=None, names=['t', 'date', 'rc'],
                    na_filter=False, dtype={'t': str, 'date': str, 'rc': float})
    b = b.merge(r, on=['t', 'date'], how='left').sort_values(['t', 'date']).reset_index(drop=True)
    assert b.date.max() <= END and b.date.min() >= START
    return b


def calendar():
    s = [x.strip() for x in open(SESS) if x.strip() and START <= x.strip() <= END]
    return {d: i for i, d in enumerate(s)}


def runlen(ok):
    idx = np.arange(len(ok))
    last_false = np.maximum.accumulate(np.where(~ok, idx, -1))
    return idx - last_false


def derive(g, cal):
    """Per-ticker arrays; index i = session i of this ticker."""
    d = {k: g[k].to_numpy() for k in ('o', 'h', 'l', 'c', 'v', 'rc')}
    d['dates'] = g.date.to_numpy()
    d['cal'] = np.array([cal.get(x, -10**6) for x in d['dates']])
    h, l, c, v = d['h'], d['l'], d['c'], d['v']
    S = pd.Series
    with np.errstate(invalid='ignore', divide='ignore'):
        rng = (h - l) / c
        d['rng'] = rng
        adr = S(rng).rolling(20).mean().to_numpy()
        band = SURF_K * adr * c
        ok = {}
        for n in (10, 20, 50):
            sma = S(c).rolling(n).mean().to_numpy()
            ok[n] = (np.abs(l - sma) <= band) & np.isfinite(sma) & np.isfinite(band)
            d[f'run{n}'] = runlen(ok[n])
        d['runany'] = runlen(ok[10] | ok[20] | ok[50])
        d['runbest'] = np.maximum.reduce([d['run10'], d['run20'], d['run50']])
        r5 = S(rng).rolling(5).mean().to_numpy()
        tr = np.full(len(c), np.nan)
        tr[5:] = r5[5:] / r5[:-5]
        d['tight'] = tr                                        # at D: mean rng D-4..D / mean rng D-9..D-5
        d['v50'] = S(v).rolling(50).mean().to_numpy()         # at D: mean v D-49..D
        d['dv20'] = S(c * v).rolling(20).median().to_numpy()  # at D: median of c*v over D-19..D
        r63 = np.full(len(c), np.nan)
        r63[63:] = c[63:] / c[:-63] - 1.0
        d['r63'] = r63
        d['univ'] = (d['rc'] >= MIN_PRICE) & (d['dv20'] >= MIN_DV)
    n = len(c)
    dok = np.zeros(n, bool)                                    # at D: bars D-85..D+1 consecutive sessions
    if n > DEEP + 1:
        D = np.arange(DEEP, n - 1)
        dok[D] = (d['cal'][D + 1] - d['cal'][D - DEEP]) == (DEEP + 1)
    d['dok'] = dok
    d['hist130'] = np.zeros(n, bool)
    if n >= 130:
        D = np.arange(129, n)
        d['hist130'][D] = (d['cal'][D] - d['cal'][D - 129]) == 129
    return d


def structure(d, D, plain=False):
    h, l, c = d['h'], d['l'], d['c']
    lo, hi = D - BASE_MAX, D - BASE_MIN
    if plain:
        seg = h[lo:hi + 1]
        Pp = lo + len(seg) - 1 - int(np.argmax(seg[::-1]))
    else:
        Pp = cb._pole_top(h, c, lo, hi)
    pole_high = float(h[Pp])
    pole_low = float(l[Pp - POLE_LB:Pp + 1].min())
    prior = pole_high / pole_low - 1.0 if pole_low > 0 else -1.0
    anchor_ok = not bool((c[Pp + 1:D + 1] > pole_high).any())
    base_low = float(l[Pp + 1:D + 1].min())
    hl = bool(float(l[D - 4:D + 1].min()) > base_low)
    level = float(h[Pp + 1:D + 1].max())
    return dict(P=Pp, prior=prior, prior_ok=prior >= PRIOR_MIN, anchor_ok=anchor_ok, hl=hl, level=level,
                base_len=D - Pp, pole_high=pole_high)


def gate_vector(d, D, s=None):
    """All gates for breakout day E = D+1 (bars <= D, E's high/volume)."""
    E = D + 1
    s = s or structure(d, D)
    surf1 = bool(d['runbest'][D] >= SURF_N)
    surfany = bool(d['runany'][D] >= SURF_N)
    t = d['tight'][D]
    g = dict(universe=bool(d['univ'][D]), prior_move=s['prior_ok'], close_above_pole_high=s['anchor_ok'],
             higher_lows=s['hl'], surf=surf1, surf_any=surfany,
             tightening=bool(np.isfinite(t) and t <= TIGHT_MAX), level=bool(d['h'][E] > s['level']),
             volume=bool(d['v'][E] >= VOL_X * d['v50'][D]))
    return g, s


def verdicts(g):
    setup = all(g[k] for k in GATES if k != 'universe')
    return dict(main=setup and g['universe'], setup_only=setup,
                any_surf=g['universe'] and all(g[k] for k in GATES if k not in ('universe', 'surf')) and g['surf_any'],
                no_anchor=g['universe'] and all(g[k] for k in GATES if k not in ('universe', 'close_above_pole_high')))


# ───────────────────────────── main ─────────────────────────────
def main():
    dev = '--dev' in sys.argv
    prim, sec, other = load_setups()
    setups = prim + sec
    names = sorted({x['t'] for x in setups})
    cal = calendar()
    bars = load(set(names) if dev else None)
    tick = bars.t.to_numpy()
    cuts = np.flatnonzero(tick[1:] != tick[:-1]) + 1
    starts = np.r_[0, cuts]
    ends = np.r_[cuts, len(tick)]

    named = {}                       # ticker -> derived arrays (his names only)
    rs_pool = defaultdict(list)      # D date -> [(ticker, r63)] for names in the universe at D
    cand = []                        # step 2: (ticker, E date, D date, main, any_surf, no_anchor)
    n_tick = n_dguard = 0
    for a, b in zip(starts, ends):
        t = tick[a]
        g = bars.iloc[a:b]
        if len(g) < DEEP + 2:
            continue
        d = derive(g, cal)
        n_tick += 1
        if t in names:
            named[t] = d
        dates = d['dates']
        n = len(dates)
        Dall = np.arange(DEEP, n - 1)
        if not len(Dall):
            continue
        Edates = dates[Dall + 1]
        inwin = (Edates >= WK_LO) & (Edates <= WK_HI)
        # RS pool: every D whose E is in the step-2 window or his names' window
        rsD = Dall[(Edates >= WIN_LO) & (Edates <= WIN_HI)]
        for D in rsD:
            if d['univ'][D] and np.isfinite(d['r63'][D]):
                rs_pool[dates[D]].append((t, float(d['r63'][D])))
        D = Dall[inwin]
        n_dguard += int((~d['dok'][D]).sum())
        with np.errstate(invalid='ignore'):
            cheap = d['dok'][D] & d['univ'][D] & (d['runany'][D] >= SURF_N) & (d['tight'][D] <= TIGHT_MAX) \
                & (d['v'][D + 1] >= VOL_X * d['v50'][D])
        for Di in D[cheap]:
            gv, s = gate_vector(d, int(Di))
            vv = verdicts(gv)
            if vv['main'] or vv['any_surf'] or vv['no_anchor']:
                cand.append((t, dates[Di + 1], dates[Di], vv['main'], vv['any_surf'], vv['no_anchor']))

    # RS stand-in percentiles (per D date, over the universe at D)
    rs_pct = {}
    for dd, lst in rs_pool.items():
        pct = cb.percentile_ranks([x[1] for x in lst])
        for (t, _), p in zip(lst, pct):
            rs_pct[(t, dd)] = p

    P('BREAKOUT v1 CHECK against his dated good setups (2020-08-10 review) — free, local, analysis only')
    P('Bars: cb702_pre_v2/daily_closes_all.csv.gz (split-adjusted) + daily_raw_close.csv.gz (the $5 test), rows dated',
      START, '..', END, 'only. Tickers evaluated:', n_tick, '' if not dev else '(DEV: his names only)')
    P('RS >= 98 and the market phase are NOT part of this check (they need the universe-wide percentile and an index');
    P('read); step 2 adds an RS stand-in beside (the 63-session return at D in the top 2% of the day\'s universe).')
    P('')

    # ── 0-diff check against the calibration's own measures (rlib.py, carried in the TSV) ──
    P('=== 0. Reproduction check: surf runs / tightening / volume vs the calibration (TSV measures column) ===')
    ndiff = 0
    for x in setups:
        d = named[x['t']]
        D = int(np.flatnonzero(d['dates'] == x['e'])[0]) - 1
        m = x['meas']
        sl = m['surf_low_sessions']
        mine = {'sma10_k1.0': int(d['run10'][D]), 'sma20_k1.0': int(d['run20'][D]), 'sma50_k1.0': int(d['run50'][D]),
                'any_k1.0': int(d['runany'][D])}
        diffs = [f'{k} {sl[k]}->{v}' for k, v in mine.items() if sl[k] != v]
        if round(float(d['tight'][D]), 3) != m['tightening_last5_vs_prev5']:
            diffs.append(f"tight {m['tightening_last5_vs_prev5']}->{round(float(d['tight'][D]), 3)}")
        vr = round(float(d['v'][D + 1] / d['v50'][D]), 2)
        if vr != m['bo_vol_vs_50d']:
            diffs.append(f"vol {m['bo_vol_vs_50d']}->{vr}")
        if diffs:
            ndiff += 1
            P('   DIFF', x['key'], '; '.join(diffs))
    P(f'   {len(setups)} setups x 6 measures: {ndiff} rows with a difference')
    P('')

    # ── 1. his setups ──
    def fires_for(d, which):
        dates = d['dates']
        n = len(dates)
        out = []
        for D in range(DEEP, n - 1):
            if not (WIN_LO <= dates[D + 1] <= WIN_HI) or not d['dok'][D]:
                continue
            gv, _ = gate_vector(d, D)
            if verdicts(gv)[which]:
                out.append(D + 1)
        return out

    variants = ('main', 'setup_only', 'any_surf', 'no_anchor')
    fires = {t: {w: fires_for(named[t], w) for w in variants} for t in named}

    def classify(d, E, F, Pstar):
        last = E == len(d['dates']) - 1
        if E in F:
            return 'HIT', E
        for k in (1, 2):
            if E + k in F:
                return f'LATE+{k}', E + k
        early = [f for f in F if Pstar < f < E]
        if early:
            return f'EARLY-{E - max(early)}', max(early)
        return ('MISS(8/10)' if last else 'MISS'), None

    credit = defaultdict(set)
    res = []
    for x in setups:
        d = named[x['t']]
        E = int(np.flatnonzero(d['dates'] == x['e'])[0])
        D = E - 1
        gv, s = gate_vector(d, D)
        sp = structure(d, D, plain=True)
        cls = {}
        for w in variants:
            c_, f_ = classify(d, E, fires[x['t']][w], s['P'])
            cls[w] = c_
            if w == 'main' and f_ is not None:
                credit[x['t']].add(f_)
        failed = [k for k in GATES if not gv[k]]
        res.append(dict(x=x, d=d, E=E, D=D, g=gv, s=s, sp=sp, cls=cls, failed=failed))

    def fmt_row(r):
        x, d, D, E, g, s = r['x'], r['d'], r['D'], r['E'], r['g'], r['s']
        lvl = d['h'][E] / s['level'] - 1
        rsp = rs_pct.get((x['t'], d['dates'][D]))
        return (f"{x['key']:8s} {x['tier']} {x['e']} | {r['cls']['main']:12s} | setup-only {r['cls']['setup_only']:12s} | "
                f"any-avg {r['cls']['any_surf']:12s} | no-anchor {r['cls']['no_anchor']:12s} | "
                f"failed on his day: {', '.join(r['failed']) or '-'}")

    def fmt_vals(r):
        x, d, D, E, g, s, sp = r['x'], r['d'], r['D'], r['E'], r['g'], r['s'], r['sp']
        rsp = rs_pct.get((x['t'], d['dates'][D]))
        mark = lambda k: '' if g[k] else '*'
        return (f"   {x['key']:8s} raw${d['rc'][D]:.2f}{mark('universe') if d['rc'][D] < MIN_PRICE else ''} "
                f"dv${d['dv20'][D] / 1e6:.1f}M{'*' if d['dv20'][D] < MIN_DV else ''} | prior {s['prior']:+.0%}{mark('prior_move')} "
                f"P {d['dates'][s['P']]} base {s['base_len']} | anchor {'ok' if g['close_above_pole_high'] else 'BROKEN*'} | "
                f"HL {'y' if g['higher_lows'] else 'n*'} | surf best {int(d['runbest'][D])}{mark('surf')} "
                f"(10:{int(d['run10'][D])} 20:{int(d['run20'][D])} 50:{int(d['run50'][D])}) any {int(d['runany'][D])}"
                f"{'' if g['surf_any'] else '*'} | tight {d['tight'][D]:.2f}{mark('tightening')} | "
                f"high/level {d['h'][E] / s['level'] - 1:+.1%}{mark('level')} | vol {d['v'][E] / d['v50'][D]:.2f}x{mark('volume')} | "
                f"RS63 pct {rsp if rsp is not None else 'n/a'} | 130-sess {'y' if d['hist130'][D] else 'n'}"
                f"{'' if sp['P'] == s['P'] else ' | plain-argmax P ' + d['dates'][sp['P']]}")

    def fmt_diag(r):
        # DIAGNOSTIC only (not v1): where the level sits, which smaller level E cleared, why the anchor broke
        x, d, D, E, s = r['x'], r['d'], r['D'], r['E'], r['s']
        h, c = d['h'], d['c']
        lv = (s['P'] + 1) + int(np.argmax(h[s['P'] + 1:D + 1][::-1][::-1]))
        k5, k10 = float(h[D - 4:D + 1].max()), float(h[D - 9:D + 1].max())
        top = (D - BASE_MAX) + len(h[D - BASE_MAX:D + 1]) - 1 - int(np.argmax(h[D - BASE_MAX:D + 1][::-1]))
        brk = [j for j in range(s['P'] + 1, D + 1) if c[j] > s['pole_high']]
        return (f"   {'':8s} diag: level {s['level']:.2f} set {d['dates'][lv]} | high(E) {h[E]:.2f} clears k10 "
                f"{'y' if h[E] > k10 else 'n'} ({k10:.2f}) k5 {'y' if h[E] > k5 else 'n'} ({k5:.2f}) | highest high of "
                f"[D-45, D] {d['dates'][top]} = {E - top} sessions before E"
                + (f" | first close above high(P) {d['dates'][brk[0]]}" if brk else ''))

    for title, keys in (('THE 24 (agreed, high/medium, tier A+B)', [x['key'] for x in prim]),
                        ('THE 4 SECONDARY (disputed rows settled at medium)', [x['key'] for x in sec])):
        rr = [r for r in res if r['x']['key'] in keys]
        P(f'=== 1. {title}: v1 on his breakout day ===')
        P('   verdict columns: v1 (universe + setup gates) | setup gates only (no $5 / $10M) | any-average surf | no base anchor')
        for r in rr:
            P('   ' + fmt_row(r))
        tal = defaultdict(lambda: defaultdict(int))
        for r in rr:
            for w in variants:
                c_ = r['cls'][w].split('(')[0]
                tal[w][c_.split('+')[0].split('-')[0]] += 1
        for w in variants:
            P(f"   tally {w:10s}: " + ', '.join(f'{k} {v}' for k, v in sorted(tal[w].items())))
        P('   values on his day (* = the gate failed; RS63 pct = the stand-in, NOT a v1 gate):')
        for r in rr:
            P(fmt_vals(r))
            P(fmt_diag(r))
        P('   level clears on his day (diagnostic, not v1): ' + ', '.join(
            f"{lab} {sum(1 for r in rr if r['d']['h'][r['E']] > f(r))}/{len(rr)}" for lab, f in (
                ('full (v1)', lambda r: r['s']['level']),
                ('k10', lambda r: r['d']['h'][r['D'] - 9:r['D'] + 1].max()),
                ('k5', lambda r: r['d']['h'][r['D'] - 4:r['D'] + 1].max()))))
        P('   gate failures on his day (a row can fail several): ' + ', '.join(
            f"{k} {sum(1 for r in rr if k in r['failed'])}" for k in GATES)
          + f"; any-average surf {sum(1 for r in rr if not r['g']['surf_any'])}")
        P('   MISS(8/10) = no fire on 2020-08-10, the file\'s last day, so a LATE fire cannot be observed')
        vo = [r['x']['key'] for r in rr if r['failed'] == ['volume']]
        P('   failed on VOLUME ONLY on his day:', ', '.join(vo) or 'none')
        uo = [r['x']['key'] for r in rr if r['failed'] and all(k == 'universe' for k in r['failed'])]
        P('   failed on the UNIVERSE ONLY on his day:', ', '.join(uo) or 'none')
        P('')

    # noise per name
    P('=== 1b. Noise on his own names: v1 fires (universe + setup gates) with E in 2020-02-03..2020-08-10 ===')
    P('   credited = the fire counted for one of his 28 setups (HIT / LATE / EARLY); other = every other fire.')
    P('   an other-fire date carries [his ...] when it is within 2 sessions of ANY dated row of his in the TSV (any tier).')
    tot_o = 0
    for t in sorted(named):
        d = named[t]
        F = fires[t]['main']
        cr = sorted(credit[t])
        oth = [f for f in F if f not in credit[t]]
        tot_o += len(oth)
        his = [(dd, tier, conf) for dd, tier, conf, _ in other.get(t, [])]
        hidx = []
        for dd, tier, conf in his:
            m = np.flatnonzero(d['dates'] == dd)
            if len(m):
                hidx.append((int(m[0]), tier, conf))
        lab = []
        for f in oth:
            near = [f'{tier}/{conf} {d["dates"][hi]}' for hi, tier, conf in hidx if abs(hi - f) <= 2]
            lab.append(d['dates'][f] + (f' [his {"; ".join(near)}]' if near else ''))
        P(f"   {t:5s} fires {len(F):2d} | credited {len(cr)} ({', '.join(d['dates'][f] for f in cr) or '-'}) | "
          f"other {len(oth)}: {', '.join(lab) or '-'}")
        P(f"         setup-only fires {len(fires[t]['setup_only'])} | any-avg {len(fires[t]['any_surf'])} | "
          f"no-anchor {len(fires[t]['no_anchor'])}")
    P(f'   total other fires on his {len(named)} names: {tot_o}')
    P('')

    # ── 2. the volume of names ──
    if not dev:
        P('=== 2. Volume of names: v1 over EVERY stock, every E in 2020-02-03..2020-08-07 (27 Mon-Fri weeks) ===')
        P(f'   data guard skipped {n_dguard} ticker-days (bars D-85..E not consecutive sessions)')
        mondays = []
        dd = date(2020, 2, 3)
        while dd <= date(2020, 8, 7):
            mondays.append(dd.isoformat())
            dd += timedelta(days=7)
        assert len(mondays) == 27

        def wk(e):
            x = date.fromisoformat(e)
            return (x - timedelta(days=x.weekday())).isoformat()

        sess_per_wk = defaultdict(int)
        for s_ in cal:
            if WK_LO <= s_ <= WK_HI:
                sess_per_wk[wk(s_)] += 1
        cols = {}
        for lab, idx, rs in (('v1', 3, False), ('v1+RS', 3, True), ('any-avg', 4, False), ('any-avg+RS', 4, True),
                             ('no-anchor', 5, False), ('no-anchor+RS', 5, True)):
            fd = defaultdict(int)
            un = defaultdict(set)
            for c_ in cand:
                if not c_[idx]:
                    continue
                if rs:
                    p = rs_pct.get((c_[0], c_[2]))
                    if p is None or p < RS_TOP:
                        continue
                fd[wk(c_[1])] += 1
                un[wk(c_[1])].add(c_[0])
            cols[lab] = ([fd[m] for m in mondays], [len(un[m]) for m in mondays])

        def st(v):
            a = np.array(v, float)
            return (f'median {np.median(a):.0f} | q1 {np.percentile(a, 25):.0f} | q3 {np.percentile(a, 75):.0f} | '
                    f'max {a.max():.0f} | min {a.min():.0f} | total {a.sum():.0f}')
        P('   per week, fire-days (a stock firing on 2 days counts 2) / unique names:')
        for lab, (fdv, unv) in cols.items():
            P(f'   {lab:13s} fire-days: {st(fdv)}')
            P(f'   {"":13s} names    : {st(unv)}')
        P('')
        P('   week of | sessions | ' + ' | '.join(f'{k} fd/names' for k in cols))
        for i, m in enumerate(mondays):
            P(f'   {m} | {sess_per_wk[m]} | ' + ' | '.join(f'{cols[k][0][i]}/{cols[k][1][i]}' for k in cols))
        ndays = sum(sess_per_wk.values())
        P(f'   per session (v1): {sum(cols["v1"][0]) / ndays:.1f} fires a night on average over {ndays} sessions; '
          f'with the RS stand-in {sum(cols["v1+RS"][0]) / ndays:.1f}')
        uni_sizes = [len(v) for k, v in rs_pool.items() if WK_LO <= k < WK_HI]
        P(f'   universe size at D (two gates, 63-session return known): median {np.median(uni_sizes):.0f}, '
          f'min {min(uni_sizes)}, max {max(uni_sizes)}')
        P('')

    P('=== Readings (where the v1 wording left a choice) ===')
    for line in (
        'universe = only the two named gates (RAW close >= $5 at D, 20-session median of adjusted close x volume >= $10M at D);',
        '  the SSoT row\'s security type / ticker pattern / 130-consecutive-session history are NOT applied (130-sess column shown);',
        'prior move P = cb._pole_top (the code behind the "Prior move" row, #592 walk) — a plain highest high differs where shown;',
        '  pole low = min low of [P-40, P] (41 sessions incl. P, the module) rather than "the 40 sessions before it";',
        'base anchor (no CLOSE above high(P) in (P, D]) is applied as a named gate (the module\'s base); the no-anchor column drops it;',
        'higher lows: min low D-4..D > the base low (P+1..D), strict; level = max high P+1..D, high(E) > level strict;',
        'surf band per session (each session\'s own ADR20 and close, as the calibration measured it); "within" inclusive;',
        'tightening on (h-l)/c, inclusive 1.1x; volume inclusive 1.2x of mean volume D-49..D; all three match the calibration;',
        'EARLY = a fire after his base\'s pole top P (taken at his D) and before his day; LATE = 1 or 2 sessions after;',
        'precedence HIT > LATE > EARLY > MISS; 2020-08-10 rows: the file ends that day, so LATE cannot be observed;',
        'RS stand-in measured at D (the watch night, as the module does), percentile over the day\'s two-gate universe;',
        'NAIL is a 3x leveraged ETF (Direxion homebuilders); the SSoT type filter would drop it — kept here (no type gate).'):
        P('   ' + line)


if __name__ == '__main__':
    main()
    print('\n'.join(OUT))
