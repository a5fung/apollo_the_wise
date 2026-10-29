#!/usr/bin/env python3
"""Breakout v1 VARIANTS scored against his dated good setups of the 2020-08-10 review — free, local, analysis only.

Re-uses v1_check.py's helpers by import (v1_check.py is NOT edited; its main() is not run). Five variants, three
axes moved, every other gate exactly as v1_check.py (prior move via cb._pole_top, higher lows, SURF = >= 5 sessions
within 1.0 ADR of ONE of SMA10/20/50, tightening <= 1.1x, volume >= 1.2x the 50-session mean, the data guard):

            base anchor   LEVEL (high(E) > it, strict)          universe (at D)
  V0        on            the base high = max high P+1..D       raw close >= $5, 20-session median $vol >= $10M
  V1        off           the base high                         $5 / $10M
  V2        off           max high D-4..D  (last 5 sessions)     $5 / $10M
  V3        off           max high D-4..D                       raw close >= $2, 20-session median $vol >= $5M
  V4        off           max high D-9..D  (last 10 sessions)    $2 / $5M

V0 must reproduce v1_check.txt's v1 column and V1 its no-anchor column (asserted below, and printed PASS/FAIL).
RS stand-ins (NOT v1 gates), measured at D over the names passing THAT VARIANT's universe gates at D:
  RS63   = the 63-session return's percentile >= 98 (v1_check.py's stand-in; cb.percentile_ranks)
  RSbest = the best of the 21-, 63- and 126-session return percentiles >= 98 (cb.cross_section_one_date's rs_best)
Reads only bars dated 2019-01-02..2020-08-10 (v1_check.load). No network, no server, no paid call, no git, no
subagents. Run: PYTHONDONTWRITEBYTECODE=1 python3 v1_check_variant.py > v1_check_variant.txt   (--dev: his names only)
"""
import sys

sys.dont_write_bytecode = True
HERE = '/Users/alvinfung/apollo_the_wise/scripts/probes/_qm_0810_review'
sys.path.insert(0, HERE)

from collections import defaultdict  # noqa: E402
from datetime import date, timedelta  # noqa: E402

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

import v1_check as v1  # noqa: E402  (read-only import: helpers + constants)

cb = v1.cb
LOOSE_PRICE, LOOSE_DV = 2.0, 5_000_000.0
VARS = ['V0', 'V1', 'V2', 'V3', 'V4']
SPEC = {'V0': dict(anchor=True, level='base', univ='strict'),
        'V1': dict(anchor=False, level='base', univ='strict'),
        'V2': dict(anchor=False, level='k5', univ='strict'),
        'V3': dict(anchor=False, level='k5', univ='loose'),
        'V4': dict(anchor=False, level='k10', univ='loose')}
GATE_ORDER = ['universe', 'prior_move', 'close_above_pole_high', 'higher_lows', 'surf', 'tightening', 'level', 'volume']
# v1_check.txt's totals (the reproduction targets)
TARGET = {
    'V0': dict(prim={'HIT': 3, 'LATE': 1, 'MISS': 20}, sec={'HIT': 1, 'MISS': 3},
               wk=dict(median=17, q1=6, q3=28, max=95, total=647), names_total=603,
               wk_rs=dict(median=2, q1=0, q3=3, max=6, total=47)),
    'V1': dict(prim={'HIT': 7, 'LATE': 3, 'MISS': 14}, sec={'HIT': 1, 'LATE': 1, 'MISS': 2},
               wk=dict(median=38, q1=14, q3=68, max=229, total=1479), names_total=1264,
               wk_rs=dict(median=5, q1=3, q3=10, max=16, total=166))}

OUT = []


def P(*a):
    OUT.append(' '.join(str(x) for x in a))


def derive2(g, cal):
    d = v1.derive(g, cal)
    c, h = d['c'], d['h']
    n = len(c)
    for hz in (21, 126):
        r = np.full(n, np.nan)
        if n > hz:
            r[hz:] = c[hz:] / c[:-hz] - 1.0
        d[f'r{hz}'] = r
    with np.errstate(invalid='ignore'):
        d['univ_loose'] = (d['rc'] >= LOOSE_PRICE) & (d['dv20'] >= LOOSE_DV)
    S = pd.Series
    d['k5'] = S(h).rolling(5).max().to_numpy()          # at D: max high D-4..D
    d['k10'] = S(h).rolling(10).max().to_numpy()        # at D: max high D-9..D
    return d


def base_gates(d, D, s):
    """Every gate under every reading, for breakout day E = D + 1 (bars <= D, E's high/volume)."""
    E = D + 1
    h = d['h']
    t = d['tight'][D]
    k5, k10 = float(h[D - 4:D + 1].max()), float(h[D - 9:D + 1].max())   # the exact fmt_diag expressions
    return dict(universe_strict=bool(d['univ'][D]), universe_loose=bool(d['univ_loose'][D]),
                prior_move=s['prior_ok'], close_above_pole_high=s['anchor_ok'], higher_lows=s['hl'],
                surf=bool(d['runbest'][D] >= v1.SURF_N), tightening=bool(np.isfinite(t) and t <= v1.TIGHT_MAX),
                level_base=bool(h[E] > s['level']), level_k5=bool(h[E] > k5), level_k10=bool(h[E] > k10),
                volume=bool(d['v'][E] >= v1.VOL_X * d['v50'][D]), k5=k5, k10=k10)


def vgates(g, v):
    sp = SPEC[v]
    out = {'universe': g['universe_' + sp['univ']], 'prior_move': g['prior_move']}
    if sp['anchor']:
        out['close_above_pole_high'] = g['close_above_pole_high']
    out.update(higher_lows=g['higher_lows'], surf=g['surf'], tightening=g['tightening'],
               level=g['level_' + sp['level']], volume=g['volume'])
    return out


def fires(g, v):
    return all(vgates(g, v).values())


def classify(d, E, F, Pstar):
    """Copied from v1_check.main (nested there): HIT > LATE+1/+2 > EARLY (after his P, before E) > MISS."""
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


def bucket(c_):
    return c_.split('(')[0].split('+')[0].split('-')[0]


def wk(e):
    x = date.fromisoformat(e)
    return (x - timedelta(days=x.weekday())).isoformat()


def stats(v):
    a = np.array(v, float)
    return dict(median=float(np.median(a)), q1=float(np.percentile(a, 25)), q3=float(np.percentile(a, 75)),
                max=float(a.max()), min=float(a.min()), total=float(a.sum()))


def fmt_st(s):
    return (f"median {s['median']:.0f} | middle half {s['q1']:.0f}-{s['q3']:.0f} | max {s['max']:.0f} | "
            f"min {s['min']:.0f} | total {s['total']:.0f}")


def main():
    dev = '--dev' in sys.argv
    prim, sec, other = v1.load_setups()
    setups = prim + sec
    names = sorted({x['t'] for x in setups})
    cal = v1.calendar()
    bars = v1.load(set(names) if dev else None)
    tick = bars.t.to_numpy()
    cuts = np.flatnonzero(tick[1:] != tick[:-1]) + 1
    starts, ends = np.r_[0, cuts], np.r_[cuts, len(tick)]

    named = {}
    pool = {'strict': defaultdict(list), 'loose': defaultdict(list)}   # D date -> [(t, r21, r63, r126)]
    cand = []            # (t, E date, D date, {v: fired})
    n_tick = n_cand = n_eq = 0
    eq_bad = []
    nan2none = lambda x: float(x) if np.isfinite(x) else None
    for a, b in zip(starts, ends):
        t = tick[a]
        g = bars.iloc[a:b]
        if len(g) < v1.DEEP + 2:
            continue
        d = derive2(g, cal)
        n_tick += 1
        if t in names:
            named[t] = d
        dates = d['dates']
        n = len(dates)
        Dall = np.arange(v1.DEEP, n - 1)
        if not len(Dall):
            continue
        Edates = dates[Dall + 1]
        # RS pools: every D whose E is in his names' window (as v1_check), ticker order = v1_check's
        for D in Dall[(Edates >= v1.WIN_LO) & (Edates <= v1.WIN_HI)]:
            if not np.isfinite(d['r63'][D]):
                continue
            row = (t, nan2none(d['r21'][D]), float(d['r63'][D]), nan2none(d['r126'][D]))
            if d['univ'][D]:
                pool['strict'][dates[D]].append(row)
            if d['univ_loose'][D]:
                pool['loose'][dates[D]].append(row)
        D = Dall[(Edates >= v1.WK_LO) & (Edates <= v1.WK_HI)]
        # prefilter: gates every variant requires (the loose universe is a superset of the strict one; the base
        # high >= max high D-9..D >= max high D-4..D because P <= D-10, so high(E) > k5 is necessary for all five)
        with np.errstate(invalid='ignore'):
            cheap = d['dok'][D] & d['univ_loose'][D] & (d['runbest'][D] >= v1.SURF_N) & (d['tight'][D] <= v1.TIGHT_MAX) \
                & (d['v'][D + 1] >= v1.VOL_X * d['v50'][D]) & (d['h'][D + 1] > d['k5'][D])
        for Di in D[cheap]:
            Di = int(Di)
            s = v1.structure(d, Di)
            gb = base_gates(d, Di, s)
            fv = {v: fires(gb, v) for v in VARS}
            n_cand += 1
            # equivalence vs v1_check's own verdicts on every candidate
            gv, _ = v1.gate_vector(d, Di, s)
            vv = v1.verdicts(gv)
            if fv['V0'] != vv['main'] or fv['V1'] != vv['no_anchor']:
                eq_bad.append((t, dates[Di + 1]))
            else:
                n_eq += 1
            if any(fv.values()):
                cand.append((t, dates[Di + 1], dates[Di], fv))

    # RS percentiles per pool per D date
    rs63, rsbest = {}, {}
    for pk, pp in pool.items():
        for dd, lst in pp.items():
            r21 = [x[1] for x in lst]
            r63 = [x[2] for x in lst]
            r126 = [x[3] for x in lst]
            p63 = cb.percentile_ranks(r63)
            best, _, _, _ = cb.cross_section_one_date(r21, r63, r126, [None] * len(lst))
            for x, p, bst in zip(lst, p63, best):
                rs63[(pk, x[0], dd)] = p
                rsbest[(pk, x[0], dd)] = bst

    def rs_ok(v, t, Ddate, which):
        pk = SPEC[v]['univ']
        p = (rs63 if which == 'RS63' else rsbest).get((pk, t, Ddate))
        return p is not None and p >= v1.RS_TOP

    P('BREAKOUT v1 VARIANTS against his dated good setups (2020-08-10 review) — free, local, analysis only')
    P('Bars: cb702_pre_v2 daily_closes_all + daily_raw_close, rows dated', v1.START, '..', v1.END,
      'only (v1_check.load). Tickers evaluated:', n_tick, '(DEV: his names only)' if dev else '')
    P('Variants (everything else exactly v1_check.py: prior move, higher lows, SURF one-average >= 5 within 1.0 ADR,')
    P('tightening <= 1.1x, volume >= 1.2x the 50-session mean, data guard):')
    P('   V0 = v1 as checked: base anchor on | level = base high | universe raw close >= $5, 20-session median $vol >= $10M')
    P('   V1 = V0 without the base anchor')
    P('   V2 = V1 with level = the highest high of the last 5 sessions to D (D-4..D)')
    P('   V3 = V2 with universe raw close >= $2, 20-session median $vol >= $5M')
    P('   V4 = V3 with level = the highest high of the last 10 sessions to D (D-9..D)')
    P('RS >= 98 and the market phase are NOT gates of any variant; the fires-per-week block shows two RS stand-ins beside.')
    P('')
    at_repro = len(OUT)

    # ── his setups ──
    def fires_for(d):
        dates = d['dates']
        out = {v: [] for v in VARS}
        bad = 0
        for D in range(v1.DEEP, len(dates) - 1):
            if not (v1.WIN_LO <= dates[D + 1] <= v1.WIN_HI) or not d['dok'][D]:
                continue
            s = v1.structure(d, D)
            gb = base_gates(d, D, s)
            gv, _ = v1.gate_vector(d, D, s)
            vv = v1.verdicts(gv)
            fv = {v: fires(gb, v) for v in VARS}
            bad += int(fv['V0'] != vv['main'] or fv['V1'] != vv['no_anchor'])
            for v in VARS:
                if fv[v]:
                    out[v].append(D + 1)
        return out, bad

    fz, bad_named = {}, 0
    for t in named:
        fz[t], b_ = fires_for(named[t])
        bad_named += b_

    credit = {v: defaultdict(set) for v in VARS}
    res = []
    for x in setups:
        d = named[x['t']]
        E = int(np.flatnonzero(d['dates'] == x['e'])[0])
        D = E - 1
        s = v1.structure(d, D)
        gb = base_gates(d, D, s)
        cls, failed = {}, {}
        for v in VARS:
            c_, f_ = classify(d, E, fz[x['t']][v], s['P'])
            cls[v] = c_
            if f_ is not None:
                credit[v][x['t']].add(f_)
            vg = vgates(gb, v)
            failed[v] = [k for k in GATE_ORDER if k in vg and not vg[k]]
        res.append(dict(x=x, d=d, E=E, D=D, s=s, gb=gb, cls=cls, failed=failed))

    tallies = {}
    for title, grp, keys in (('THE 24 (agreed, high/medium, tier A+B)', 'prim', [x['key'] for x in prim]),
                             ('THE 4 SECONDARY (disputed rows settled at medium)', 'sec', [x['key'] for x in sec])):
        rr = [r for r in res if r['x']['key'] in keys]
        P(f'=== 1. {title}: each variant on his breakout day ===')
        P('   cell = HIT / LATE+k (k sessions after his day) / EARLY-k (k sessions before, same base) / MISS; '
          'MISS(8/10) = his day is the file\'s last')
        P(f"   {'setup':8s} t {'his day':10s} | " + ' | '.join(f'{v:11s}' for v in VARS))
        for r in rr:
            P(f"   {r['x']['key']:8s} {r['x']['tier']} {r['x']['e']} | " + ' | '.join(f"{r['cls'][v]:11s}" for v in VARS))
        P('   failed gates on his day, per variant (- = all pass):')
        for r in rr:
            P(f"   {r['x']['key']:8s} " + ' | '.join(f"{v}: {','.join(r['failed'][v]) or '-'}" for v in VARS))
        tallies[grp] = {}
        for v in VARS:
            tl = defaultdict(int)
            for r in rr:
                tl[bucket(r['cls'][v])] += 1
            tallies[grp][v] = dict(tl)
        P('   TALLY            ' + ' | '.join(f'{k:5s}' for k in ('HIT', 'LATE', 'EARLY', 'MISS')) + ' | caught (HIT+LATE)')
        for v in VARS:
            tl = tallies[grp][v]
            P(f'   {v}               ' + ' | '.join(f'{tl.get(k, 0):5d}' for k in ('HIT', 'LATE', 'EARLY', 'MISS'))
              + f" | {tl.get('HIT', 0) + tl.get('LATE', 0)}/{len(rr)}")
        P('   gate failures on his day (a row can fail several): ')
        for v in VARS:
            cnt = defaultdict(int)
            for r in rr:
                for k in r['failed'][v]:
                    cnt[k] += 1
            P(f'   {v}: ' + (', '.join(f'{k} {cnt[k]}' for k in GATE_ORDER if k in cnt) or 'none'))
        P('')

    # ── universe-wide fires per week ──
    mondays = []
    dd = date(2020, 2, 3)
    while dd <= date(2020, 8, 7):
        mondays.append(dd.isoformat())
        dd += timedelta(days=7)
    assert len(mondays) == 27
    sess_per_wk = defaultdict(int)
    for s_ in cal:
        if v1.WK_LO <= s_ <= v1.WK_HI:
            sess_per_wk[wk(s_)] += 1
    ndays = sum(sess_per_wk.values())
    cols = {}
    if not dev:
        P('=== 2. Fires per week, EVERY stock, every E in 2020-02-03..2020-08-07 (27 Mon-Fri weeks) ===')
        P('   fire-days = a stock firing on 2 days counts 2; names = unique stocks that week. RS percentiles over the')
        P('   names passing THAT variant\'s universe gates at D (V0-V2: $5/$10M pool; V3-V4: $2/$5M pool).')
        for v in VARS:
            for rs in ('', 'RS63', 'RSbest'):
                fd, un = defaultdict(int), defaultdict(set)
                for t, Ed, Dd, fv in cand:
                    if not fv[v] or (rs and not rs_ok(v, t, Dd, rs)):
                        continue
                    fd[wk(Ed)] += 1
                    un[wk(Ed)].add(t)
                cols[(v, rs)] = ([fd[m] for m in mondays], [len(un[m]) for m in mondays])
        P(f"   {'variant':16s} fire-days per week")
        for v in VARS:
            for rs in ('', 'RS63', 'RSbest'):
                lab = v + (' + ' + rs if rs else ' (no RS)')
                st_ = stats(cols[(v, rs)][0])
                P(f'   {lab:16s} {fmt_st(st_)} | {st_["total"] / ndays:.1f} a night')
        P(f"   {'variant':16s} unique names per week")
        for v in VARS:
            for rs in ('', 'RS63', 'RSbest'):
                lab = v + (' + ' + rs if rs else ' (no RS)')
                P(f'   {lab:16s} {fmt_st(stats(cols[(v, rs)][1]))}')
        P('')
        P('   week of | sess | ' + ' | '.join(f'{v} -/63/best' for v in VARS) + '   (fire-days)')
        for i, m in enumerate(mondays):
            P(f'   {m} | {sess_per_wk[m]} | ' + ' | '.join(
                '/'.join(str(cols[(v, rs)][0][i]) for rs in ('', 'RS63', 'RSbest')).ljust(13) for v in VARS))
        for pk in ('strict', 'loose'):
            sz = [len(v_) for k, v_ in pool[pk].items() if v1.WK_LO <= k < v1.WK_HI]
            P(f'   RS pool size at D ({"$5/$10M" if pk == "strict" else "$2/$5M"}): median {np.median(sz):.0f}, '
              f'min {min(sz)}, max {max(sz)}')
        P(f'   candidates evaluated after the shared prefilter: {n_cand}')
        P('')

        # ── noise on his own names (universe-wide fires, step-2 window) ──
        P('=== 3. Noise on his 23 names: universe-wide fires (E 2020-02-03..2020-08-07) NOT credited to his 28 setups ===')
        P('   credited = the fire counted HIT / LATE / EARLY for one of his 28 setups under that variant (v1_check 1b\'s rule).')
        P('   of the rest: "on" = E is a date of ANY dated TSV row of his on that name (any tier/confidence); "near" = within')
        P('   1-2 sessions of one; "unnamed" = neither. 2020-08-10 fires sit outside this window (fires-per-week window).')
        hisd = {}
        for t in named:
            dts = named[t]['dates']
            hisd[t] = []
            for ddt, tier, conf, _ in other.get(t, []):
                m_ = np.flatnonzero(dts == ddt)
                if len(m_):
                    hisd[t].append((int(m_[0]), tier, conf, ddt))
        xcheck = []
        for v in VARS:
            mine = [(t, Ed, Dd) for t, Ed, Dd, fv in cand if fv[v] and t in named]
            # cross-check: the universe-wide list on his names == the per-name scan restricted to the window
            scan = sorted((t, named[t]['dates'][f]) for t in named for f in fz[t][v]
                          if named[t]['dates'][f] <= v1.WK_HI)
            same = sorted((t, Ed) for t, Ed, _ in mine) == scan
            xcheck.append(f'{v} {"PASS" if same else "FAIL"} ({len(mine)} universe-wide vs {len(scan)} per-name)')
            cr = [m for m in mine if int(np.flatnonzero(named[m[0]]['dates'] == m[1])[0]) in credit[v][m[0]]]
            rest = [m for m in mine if m not in cr]
            lab = {}
            for t, Ed, Dd in rest:
                ei = int(np.flatnonzero(named[t]['dates'] == Ed)[0])
                dist = [(abs(hi - ei), f'{tier}/{conf} {ddt}') for hi, tier, conf, ddt in hisd[t] if abs(hi - ei) <= 2]
                lab[(t, Ed)] = ('on' if any(x[0] == 0 for x in dist) else 'near' if dist else 'unnamed',
                                '; '.join(x[1] for x in sorted(dist)))
            on = sum(1 for k in lab.values() if k[0] == 'on')
            near = sum(1 for k in lab.values() if k[0] == 'near')
            unn = sum(1 for k in lab.values() if k[0] == 'unnamed')
            rs_c = {rs: sum(1 for t, Ed, Dd in rest if rs_ok(v, t, Dd, rs)) for rs in ('RS63', 'RSbest')}
            P(f'   {v}: fires on his names {len(mine)} | credited {len(cr)} | NOT credited {len(rest)} '
              f'(on a dated row of his {on}, near one {near}, unnamed {unn}) | not-credited passing RS63 {rs_c["RS63"]}, '
              f'RSbest {rs_c["RSbest"]}')
            if v == 'V3':
                P('   V3 per name (not-credited fires; [his ...] = his dated rows within 2 sessions):')
                by_t = defaultdict(list)
                for t, Ed, Dd in rest:
                    k_, near_ = lab[(t, Ed)]
                    rsm = ('+63' if rs_ok(v, t, Dd, 'RS63') else '') + ('+best' if rs_ok(v, t, Dd, 'RSbest') else '')
                    by_t[t].append(Ed + (f' [{k_}: his {near_}]' if near_ else '') + (f' (RS{rsm})' if rsm else ''))
                crt = defaultdict(list)
                for t, Ed, _ in cr:
                    crt[t].append(Ed)
                for t in sorted(named):
                    P(f"     {t:5s} credited {len(crt[t])} ({', '.join(crt[t]) or '-'}) | not credited {len(by_t[t])}: "
                      f"{', '.join(by_t[t]) or '-'}")
        P('   prefilter cross-check (universe-wide fires on his names == the unfiltered per-name scan, E <= 08-07): '
          + '; '.join(xcheck))
        P('')

    # ── reproduction (spliced in after the header) ──
    tail = len(OUT)
    P('=== 0. Reproduction of v1_check.txt ===')
    P(f'   V0 == v1_check verdict "main" and V1 == "no_anchor" on every evaluated day: his names {"PASS" if not bad_named else f"FAIL ({bad_named})"}'
      + ('' if dev else f'; universe-wide candidates {n_eq} equal, {len(eq_bad)} differ'
         + (' PASS' if not eq_bad else ' FAIL ' + str(eq_bad[:10]))))
    allok = not bad_named and not eq_bad
    for v in ('V0', 'V1'):
        tg = TARGET[v]
        chk = []
        chk.append(('24 tally', tallies['prim'][v] == tg['prim'], tallies['prim'][v], tg['prim']))
        chk.append(('4 tally', tallies['sec'][v] == tg['sec'], tallies['sec'][v], tg['sec']))
        if not dev:
            s0 = stats(cols[(v, '')][0])
            sr = stats(cols[(v, 'RS63')][0])
            got = {k: s0[k] for k in tg['wk']}
            gotr = {k: sr[k] for k in tg['wk_rs']}
            chk.append(('fire-days/week', all(round(got[k]) == tg['wk'][k] for k in got), got, tg['wk']))
            chk.append(('names total', stats(cols[(v, '')][1])['total'] == tg['names_total'],
                        stats(cols[(v, '')][1])['total'], tg['names_total']))
            chk.append(('+RS63 fire-days/week', all(round(gotr[k]) == tg['wk_rs'][k] for k in gotr), gotr, tg['wk_rs']))
        for lab, ok, got, want in chk:
            allok &= ok
            P(f'   {v} {lab:22s} {"PASS" if ok else "FAIL"}  got {got}  v1_check.txt {want}')
    P(f'   OVERALL: {"V0 and V1 REPRODUCE v1_check.txt" if allok else "REPRODUCTION FAILED — read the FAIL lines"}')
    P('')
    rep = OUT[tail:]
    del OUT[tail:]
    OUT[at_repro:at_repro] = rep

    P('=== Readings ===')
    for line in (
        'all gates other than the three moved axes are v1_check.py\'s own functions (structure, derive, the run/tight/volume',
        '  arrays) — imported, not re-implemented; V0/V1 are checked against v1_check.verdicts on every evaluated day;',
        'level k5/k10 = max high of D-4..D / D-9..D, high(E) strictly above (the same expressions v1_check printed as diag);',
        'the prior move, the base (P+1..D, 10..45 sessions) and higher lows still hang off the module\'s pole top P in every',
        '  variant — only the breakout LEVEL moves; EARLY = a fire after his P and before his day (as v1_check);',
        '$2/$5M universe: RAW close >= $2 at D and the 20-session median of adjusted close x volume >= $5M at D;',
        'RS pools: names with >= 87 bars, a known 63-session return at D, and the variant\'s universe at D, in ticker order',
        '  (v1_check\'s pool, reproduced); RSbest = max of the available 21/63/126 percentiles (a missing horizon is skipped);',
        'V3 noise counts fires with E <= 2020-08-07 (the fires-per-week window); a 2020-08-10 fire is not in it.'):
        P('   ' + line)


if __name__ == '__main__':
    main()
    print('\n'.join(OUT))
