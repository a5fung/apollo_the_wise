#!/usr/bin/env python3
"""Breakout v1 PARITY FIXTURE builder + the port check — free, local, analysis only (#711 build, component B1).

Builds `tests/fixtures/breakout_v1_parity/` (CI has no apollo_data) from the SAME reference code that produced
`scripts/probes/_qm_0810_review/v1_check_variant_rs.txt`: `v1_check` + `v1_check_variant` are IMPORTED (their main()
does not run), so the bars, the calendar, the data guard and the $2/$5M RS pool are theirs, in their ticker order
(`cb.percentile_ranks` breaks ties in input order — a different order would move 98.0-boundary rows such as CELH-1).

What it does, in one pass over the 2019-01-02..2020-08-10 universe (v1_check.load):
  1. the RS pool exactly as v1_check_variant (names with >= 87 bars, a known 63-session return at D, the $2/$5M
     universe at D, every D whose E is in 2020-02-03..2020-08-10) -> rs_best per (ticker, D) via cb.cross_section_one_date;
  2. for his 28 dated setups' tickers: the reference's per-D gate vector (V3: universe_loose, prior_move, higher_lows,
     surf, tightening, level_k5, volume) beside `breakout_v1.v1_gates` + `breakout_triggered` on every evaluated D,
     compared gate by gate;
  3. the classification (HIT / LATE / EARLY / MISS) per setup, V3 + RSbest by the reference and by breakout_v1, with
     and without the breakdown check;
  4. universe-wide (every stock, E in 2020-02-03..2020-08-07, the reference's fires-per-week window): V3 + RSbest fires
     by the reference vs breakout_v1 on every prefiltered candidate, and the names a night with the breakdown check.
Writes the fixture (bars + sessions + rs_best + setups + expected + the reference gate vectors) and prints a report.
Run once: PYTHONDONTWRITEBYTECODE=1 .venv/bin/python scripts/probes/_breakout_v1_build/build_parity_fixture.py > <scratch>/fixture_build.txt
No network, no server, no paid call, no git.
"""
import csv
import gzip
import json
import math
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

sys.dont_write_bytecode = True
REPO = Path('/Users/alvinfung/apollo_the_wise')
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / 'scripts/probes/_qm_0810_review'))

import numpy as np  # noqa: E402

import v1_check as v1  # noqa: E402
import v1_check_variant as vv  # noqa: E402
from agents.market_intelligence import breakout_v1 as bv  # noqa: E402

cb = v1.cb
OUT_DIR = REPO / 'tests/fixtures/breakout_v1_parity'
# v1_check_variant_rs.txt's "V3+RSbest" column, transcribed (the acceptance bar)
EXPECTED_RS_COLUMN = {
    'CELH-1': 'HIT', 'CELH-3': 'HIT', 'CODX-1': 'HIT', 'CVNA-1': 'MISS', 'CWH-2': 'MISS', 'LVGO-4': 'HIT',
    'NVAX': 'MISS', 'OPK-2': 'HIT', 'OSTK-2': 'LATE+2', 'PLUG': 'MISS', 'SRNE-2': 'LATE+1', 'PRTS': 'HIT',
    'DFS': 'MISS', 'QUMU': 'MISS(8/10)', 'ARCT': 'HIT', 'HL': 'HIT', 'IBIO-1': 'HIT', 'OPK-1': 'MISS',
    'OPK-3': 'MISS', 'PENN-2': 'HIT', 'PENN-3': 'EARLY-31', 'RUN': 'MISS', 'TTOO': 'MISS(8/10)', 'NAIL': 'MISS(8/10)',
    'CLSK': 'HIT', 'INO-3': 'MISS', 'INO-4': 'HIT', 'TRVN': 'MISS'}
REF_GATES = ('universe_loose', 'prior_move', 'higher_lows', 'surf', 'tightening', 'level_k5', 'volume')

OUT = []


def P(*a):
    OUT.append(' '.join(str(x) for x in a))


def to_bars(d):
    """cb.DailyBars over the reference's per-ticker arrays (same doubles; no re-parse)."""
    return cb.DailyBars([date.fromisoformat(x) for x in d['dates']], d['o'].astype(float), d['h'].astype(float),
                        d['l'].astype(float), d['c'].astype(float), d['v'].astype(float))


def mine_vector(bars, d, D, rs):
    """breakout_v1's gates on the reference's axes, plus the breakdown check and the two RS-gated fire flags."""
    g = bv.v1_gates(bars, D, rs_best=rs, raw_close=float(d['rc'][D]) if np.isfinite(d['rc'][D]) else float('nan'),
                    cidx=d['cal'])
    E = D + 1
    t = bv.breakout_triggered({'h': float(d['h'][E]), 'v': float(d['v'][E])}, g)
    G = g['gates']
    vec = {'universe_loose': G['universe']['pass'], 'prior_move': G['prior_move']['pass'],
           'higher_lows': G['higher_lows']['pass'], 'surf': G['surf']['pass'], 'tightening': G['tightening']['pass'],
           'level_k5': t['level_pass'], 'volume': t['volume_pass']}
    shape = all(vec.values())
    return vec, shape and G['rs']['pass'], shape and G['rs']['pass'] and G['breakdown']['pass'], g


def ref_vector(d, D):
    s = v1.structure(d, D)
    gb = vv.base_gates(d, D, s)
    return {k: bool(gb[k]) for k in REF_GATES}, vv.fires(gb, 'V3'), s


def main():
    prim, sec, other = v1.load_setups()
    setups = prim + sec
    names = sorted({x['t'] for x in setups})
    cal = v1.calendar()
    bars = v1.load(None)
    tick = bars.t.to_numpy()
    cuts = np.flatnonzero(tick[1:] != tick[:-1]) + 1
    starts, ends = np.r_[0, cuts], np.r_[cuts, len(tick)]

    pool = defaultdict(list)              # D date -> [(t, r21, r63, r126)] (the loose pool, ticker order)
    named, named_rows = {}, {}
    cand = []                             # (t, E date, D date, ref_V3, None) - RS applied after
    cand_mine = {}                        # (t, D date) -> (mine_noBD_shape, breakdown_pass)
    cand_mismatch = []
    nan2none = lambda x: float(x) if np.isfinite(x) else None
    for a, b in zip(starts, ends):
        t = tick[a]
        g = bars.iloc[a:b]
        if len(g) < v1.DEEP + 2:
            continue
        d = vv.derive2(g, cal)
        if t in names:
            named[t] = d
            named_rows[t] = g
        dates = d['dates']
        n = len(dates)
        Dall = np.arange(v1.DEEP, n - 1)
        if not len(Dall):
            continue
        Edates = dates[Dall + 1]
        for D in Dall[(Edates >= v1.WIN_LO) & (Edates <= v1.WIN_HI)]:
            if not np.isfinite(d['r63'][D]):
                continue
            if d['univ_loose'][D]:
                pool[dates[D]].append((t, nan2none(d['r21'][D]), float(d['r63'][D]), nan2none(d['r126'][D])))
        D = Dall[(Edates >= v1.WK_LO) & (Edates <= v1.WK_HI)]
        with np.errstate(invalid='ignore'):
            cheap = d['dok'][D] & d['univ_loose'][D] & (d['runbest'][D] >= v1.SURF_N) & (d['tight'][D] <= v1.TIGHT_MAX) \
                & (d['v'][D + 1] >= v1.VOL_X * d['v50'][D]) & (d['h'][D + 1] > d['k5'][D])
        if cheap.any():
            bb = to_bars(d)
            for Di in D[cheap]:
                Di = int(Di)
                rv, rfire, _ = ref_vector(d, Di)
                mv, _, _, gg = mine_vector(bb, d, Di, 99.0)      # RS applied below; 99 only to read the shape
                mshape = all(mv.values())
                if mshape != rfire or mv != rv:
                    cand_mismatch.append((t, dates[Di], rv, mv))
                if rfire:
                    cand.append((t, dates[Di + 1], dates[Di]))
                    cand_mine[(t, dates[Di])] = (mshape, bool(gg['gates']['breakdown']['pass']))

    rsbest = {}
    for dd, lst in pool.items():
        best, _, _, _ = cb.cross_section_one_date([x[1] for x in lst], [x[2] for x in lst], [x[3] for x in lst],
                                                  [None] * len(lst))
        for x, bst in zip(lst, best):
            rsbest[(x[0], dd)] = bst

    # ── his names: every evaluated D, gate by gate ──
    gate_rows, fires_ref, fires_mine, fires_bd, mism = [], defaultdict(list), defaultdict(list), defaultdict(list), []
    for t in names:
        d = named[t]
        bb = to_bars(d)
        dates = d['dates']
        for D in range(v1.DEEP, len(dates) - 1):
            if not (v1.WIN_LO <= dates[D + 1] <= v1.WIN_HI) or not d['dok'][D]:
                continue
            rs = rsbest.get((t, dates[D]))
            rv, rfire, _ = ref_vector(d, D)
            mv, mfire, mfire_bd, _ = mine_vector(bb, d, D, rs)
            rfire_rs = rfire and rs is not None and rs >= v1.RS_TOP
            if rv != mv or rfire_rs != mfire:
                mism.append((t, dates[D], rv, mv, rfire_rs, mfire))
            gate_rows.append((t, dates[D], ''.join('1' if rv[k] else '0' for k in REF_GATES)))
            if rfire_rs:
                fires_ref[t].append(D + 1)
            if mfire:
                fires_mine[t].append(D + 1)
            if mfire_bd:
                fires_bd[t].append(D + 1)

    cls = {}
    for x in setups:
        d = named[x['t']]
        E = int(np.flatnonzero(d['dates'] == x['e'])[0])
        Pstar = v1.structure(d, E - 1)['P']
        cls[x['key']] = {w: vv.classify(d, E, F[x['t']], Pstar)[0]
                         for w, F in (('ref', fires_ref), ('mine', fires_mine), ('mine_bd', fires_bd))}

    P('BREAKOUT v1 PARITY — breakout_v1.py vs the reference (v1_check_variant V3 + RSbest), 2019-01-02..2020-08-10')
    P(f'his names: {len(names)} tickers, {len(gate_rows)} evaluated nights; gate-vector or fire mismatches: {len(mism)}')
    for m in mism[:20]:
        P('   MISMATCH', m)
    P(f'universe-wide prefiltered candidates (E 2020-02-03..08-07): ref V3 fires {len(cand)}; candidates where the '
      f'gate vectors differ: {len(cand_mismatch)}')
    for m in cand_mismatch[:20]:
        P('   CAND MISMATCH', m)
    P('')
    P('=== per setup: V3 + RSbest (rs.txt column) | reference re-run | breakout_v1 | breakout_v1 + breakdown check ===')
    tal = {w: defaultdict(int) for w in ('txt', 'ref', 'mine', 'mine_bd')}
    changed = []
    for x in setups:
        k = x['key']
        c = cls[k]
        grp = 'prim' if x in prim else 'sec'
        flag = '' if c['mine_bd'] == c['mine'] else '   <-- the breakdown check CHANGED this row'
        if flag:
            changed.append((k, c['mine'], c['mine_bd']))
        P(f"   {k:8s} {grp} {x['e']} | {EXPECTED_RS_COLUMN[k]:11s} | {c['ref']:11s} | {c['mine']:11s} | {c['mine_bd']:11s}{flag}")
        if grp == 'prim':
            tal['txt'][vv.bucket(EXPECTED_RS_COLUMN[k])] += 1
            for w in ('ref', 'mine', 'mine_bd'):
                tal[w][vv.bucket(c[w])] += 1
    for w in ('txt', 'ref', 'mine', 'mine_bd'):
        tl = tal[w]
        P(f"   THE 24 {w:8s} HIT {tl['HIT']} | LATE {tl['LATE']} | EARLY {tl['EARLY']} | MISS {tl['MISS']} | "
          f"caught {tl['HIT'] + tl['LATE']}/24")
    ok_txt = all(cls[k]['ref'] == v and cls[k]['mine'] == v for k, v in EXPECTED_RS_COLUMN.items())
    P(f"   reference re-run AND breakout_v1 == v1_check_variant_rs.txt on all 28 rows: {'PASS' if ok_txt else 'FAIL'}")
    P(f"   rows the breakdown check changed: {changed or 'none'}")
    P('')

    # ── names a night, universe-wide ──
    sess = [s for s in cal if v1.WK_LO <= s <= v1.WK_HI]
    fd_rs = [c for c in cand if (rsbest.get((c[0], c[2])) or -1) >= v1.RS_TOP]
    fd_bd = [c for c in fd_rs if cand_mine[(c[0], c[2])][1]]
    lost = sorted({(c[0], c[1]) for c in fd_rs} - {(c[0], c[1]) for c in fd_bd})
    P('=== names a night, every stock, E in 2020-02-03..2020-08-07 (the reference window, no type filter) ===')
    P(f'   V3 + RSbest: {len(fd_rs)} fire-days over {len(sess)} sessions = {len(fd_rs) / len(sess):.2f} a night '
      f'(v1_check_variant.txt: 486 = 3.7)')
    P(f'   + the breakdown check: {len(fd_bd)} fire-days = {len(fd_bd) / len(sess):.2f} a night; removed {len(lost)}: '
      + ', '.join(f'{t} {e}' for t, e in lost))
    P('')

    # ── the fixture ──
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with gzip.open(OUT_DIR / 'bars.csv.gz', 'wt', newline='') as f:
        w = csv.writer(f)
        w.writerow(['t', 'date', 'o', 'h', 'l', 'c', 'v', 'rc'])
        for t in names:
            g = named_rows[t]
            for r in g.itertuples(index=False):
                rc = '' if not np.isfinite(r.rc) else repr(float(r.rc))
                w.writerow([t, r.date, repr(float(r.o)), repr(float(r.h)), repr(float(r.l)), repr(float(r.c)),
                            repr(float(r.v)), rc])
    rs_out = defaultdict(dict)
    for t in names:
        d = named[t]
        dates = d['dates']
        for D in range(v1.DEEP, len(dates) - 1):
            if v1.WIN_LO <= dates[D + 1] <= v1.WIN_HI:
                rs_out[t][dates[D]] = rsbest.get((t, dates[D]))
    meta = {
        'source': 'scripts/probes/_breakout_v1_build/build_parity_fixture.py over /Users/alvinfung/apollo_data/cb702_pre_v2 '
                  '(v1_check.load: rows dated 2019-01-02..2020-08-10); rs_best = cb.cross_section_one_date over '
                  'v1_check_variant\'s $2/$5M pool (no type filter) at D',
        'win_lo': v1.WIN_LO, 'win_hi': v1.WIN_HI,
        'sessions': [s for s in sorted(cal, key=cal.get)],
        'setups': [{'key': x['key'], 't': x['t'], 'e': x['e'], 'tier': x['tier'], 'group': 'prim' if x in prim else 'sec'}
                   for x in setups],
        'expected_v3_rsbest': EXPECTED_RS_COLUMN,
        'expected_with_breakdown': {k: cls[k]['mine_bd'] for k in EXPECTED_RS_COLUMN},
        'rs_best': rs_out,
        'ref_gate_order': list(REF_GATES),
        'ref_gates': {f'{t}|{dd}': bits for t, dd, bits in gate_rows},
    }
    with gzip.open(OUT_DIR / 'meta.json.gz', 'wt') as f:
        json.dump(meta, f, sort_keys=True, separators=(',', ':'))
    sz = sum(p.stat().st_size for p in OUT_DIR.iterdir())
    P(f'fixture written: {OUT_DIR} ({sz:,} bytes): {len(names)} tickers, {len(gate_rows)} reference gate vectors')


if __name__ == '__main__':
    main()
    print('\n'.join(OUT))
