#!/usr/bin/env python3
"""bar_check.py (v1.1 — v1 was the version scored on 2020-08-10; v1.1 adds the kind-(b) candidates, untested) — the reader's bar tools + the AUTOMATIC BAR CHECK for the one-reader QM dating method.

Measures come from the 08-10 reconcile's rlib.py (imported, not re-implemented); only the bar LOADER is
ours, because rlib hard-codes its bar files and the 2019-09-01..2020-08-10 window. Prices are split-adjusted
(keyed by TODAY's symbol); raw closes are joined for price cues.

Sub-commands (all read-only on the bars; nothing dated 2025-01-01 or later is ever loaded — hard cap):
  extract  SYMBOLS START END OUT.csv   one awk pass over daily_closes_all.csv.gz (+ raw closes) for a ticker list
  cands    SYMBOL START END            breakout-candidate sessions in [START, END]: (a) the session's HIGH clears the
                                       highest high of the previous 10 sessions AND (range >= 1.0 ADR or vol >= 1.2x v50);
                                       (b) [v1.1] a range expansion >= 1.3 ADR whose 3 prior sessions were each < 1.0 ADR,
                                       even if it clears no prior high (kind column: a / b)
  view     SYMBOL START END [--raw]    the bars, one line a session (rlib.view format)
  check    DATES.tsv [--out FLAGS.tsv] the automatic check of a reader's TSV (see FLAGS below)

Environment: BARS_SEL (default ./bars_sel.csv) and RAW_SEL (./raw_sel.csv), the extract's outputs.

FLAGS (per dated row; any flag = the reader re-checks that row, it is NOT auto-rejected):
  not_expansion    breakout-day range < 1.0 ADR(D-1)
  not_rising_vol   breakout-day volume < 1.0x the 50-session average ending D-1
  no_base_clear    the session's high does not clear the highest high of the base (P+1..D-1) — not a breakout of the base
  no_prior_move    prior_move (high at P / lowest low of the 40 sessions before P) < 1.3
  thin_base        base shorter than 5 sessions
  words:*          his words contradict the bars —
                   words:ma20   he says it rode the 20-day but the k=1.0 low-run on sma20 is < 3 sessions (same for ma10/ma50)
                   words:tight  he says tight / narrow range but last-5-vs-prev-5 tightening > 1.2
                   words:hivol  he says high / big volume but vol < 1.2x v50
                   words:gap    he says it gapped up but open(D) <= close(D-1)
                   words:narrow he says a narrow candle the day before but range(D-1) > 0.8 ADR
                   words:weak   he says it closed weak but close sits in the top half of the day's range
  after_stream     a backward-dated ("had a setup here") row dated AFTER the stream date (or a now/forward row before it)
Rows with breakout_date empty (undatable / forming / no_breakout) are listed, not flagged.
"""
import os
import sys
import subprocess

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, '/private/tmp/claude-501/-Users-alvinfung-apollo-the-wise/d30e3944-e07e-4b44-97de-010acba78d0b/scratchpad/qm0810_reconcile')
import rlib  # noqa: E402  (measure / surf_runs / base_start / view)

SEAL = '2024-12-31'          # never read a bar after this
GZ = '/Users/alvinfung/apollo_data/cb702_pre_v2/daily_closes_all.csv.gz'
GZ_RAW = '/Users/alvinfung/apollo_data/cb702_pre_v2/daily_raw_close.csv.gz'
BARS_SEL = os.environ.get('BARS_SEL', os.path.join(HERE, 'bars_sel.csv'))
RAW_SEL = os.environ.get('RAW_SEL', os.path.join(HERE, 'raw_sel.csv'))

_all = {}


def extract(symbols, start, end, out):
    end = min(end, SEAL)
    syms = ','.join(symbols)
    awk = ('BEGIN{n=split(T,a,","); for(i=1;i<=n;i++) k[a[i]]=1} ($1 in k) && $2>="%s" && $2<="%s"' % (start, end))
    for src, dst in ((GZ, out), (GZ_RAW, out.replace('.csv', '') + '_raw.csv')):
        cmd = f'gzip -dc {src} | awk -F, -v T="{syms}" \'{awk}\' > {dst}'
        subprocess.run(cmd, shell=True, check=True)
    print('wrote', out)


def load(t, start=None, end=None):
    """Build rlib's frame for symbol t from our extract and inject it into rlib's cache."""
    key = (t, start, end)
    if key in _all:
        rlib._cache[t] = _all[key]
        return _all[key]
    if 'df' not in _all:
        df = pd.read_csv(BARS_SEL, header=None, names=['t', 'date', 'o', 'h', 'l', 'c', 'v'])
        df = df[df.date <= SEAL]
        raw = pd.read_csv(RAW_SEL, header=None, names=['t', 'date', 'rc'])
        _all['df'], _all['raw'] = df, raw
    df, raw = _all['df'], _all['raw']
    d = df[df.t == t]
    if start:
        d = d[d.date >= start]
    if end:
        d = d[d.date <= min(end, SEAL)]
    d = d.sort_values('date').reset_index(drop=True).copy()
    if d.empty:
        raise KeyError(f'no bars for {t}')
    r = raw[raw.t == t][['date', 'rc']]
    d = d.merge(r, on='date', how='left')
    d['f'] = d.rc / d.c
    d['rng'] = (d.h - d.l) / d.c
    d['adr'] = d.rng.rolling(20).mean()
    for n in (10, 20, 50):
        d[f's{n}'] = d.c.rolling(n).mean()
    d['v50'] = d.v.rolling(50).mean().shift(1)
    d['v20'] = d.v.rolling(20).mean().shift(1)
    d['chg'] = d.c.pct_change()
    _all[key] = d
    rlib._cache[t] = d
    return d


def cands(t, start, end, lookback=10):
    d = load(t)
    out = []
    for D in range(max(lookback, 60), len(d)):
        r = d.iloc[D]
        if r.date < start or r.date > end:
            continue
        prev_hi = d.h.iloc[D - lookback:D].max()
        if r.adr != r.adr or r.v50 != r.v50:
            continue
        exp = r.rng / d.adr.iloc[D - 1] >= 1.0
        vol = r.v / r.v50 >= 1.2
        kind_a = r.h > prev_hi and (exp or vol)
        tight3 = bool(((d.rng.iloc[D - 3:D] / d.adr.iloc[D - 1]) < 1.0).all())
        kind_b = (r.rng / d.adr.iloc[D - 1] >= 1.3) and tight3 and r.c > d.c.iloc[D - 1]
        if not (kind_a or kind_b):
            continue
        kind = 'a' if kind_a else 'b'
        # how long a range did it clear: sessions back whose highs are all below today's high
        n = 0
        while D - 1 - n >= 0 and d.h.iloc[D - 1 - n] < r.h:
            n += 1
        try:
            m = rlib.measure(t, r.date)
        except Exception as e:  # noqa: BLE001
            m = {}
        out.append(dict(kind=kind, date=r.date, chg=round(r.chg * 100, 1), rng_adr=round(r.rng / d.adr.iloc[D - 1], 2),
                        v50x=round(r.v / r.v50, 2), clears=n, cpos=round((r.c - r.l) / (r.h - r.l), 2) if r.h > r.l else None,
                        gap=round((r.o / d.c.iloc[D - 1] - 1) * 100, 1),
                        base_start=m.get('base_start'), base_len=m.get('base_len'), prior=m.get('prior_move'),
                        surf10=m.get('surf_low_sessions', {}).get('sma10_k1.0'), surf20=m.get('surf_low_sessions', {}).get('sma20_k1.0'),
                        surf50=m.get('surf_low_sessions', {}).get('sma50_k1.0'), tight=m.get('tightening_last5_vs_prev5'),
                        hl=m.get('higher_lows'), prev_rng=round(d.rng.iloc[D - 1] / d.adr.iloc[D - 1], 2),
                        close_raw=round(r.c * (r.f if r.f == r.f else 1), 2)))
    print(f'--- candidates {t} {start}..{end} (high clears prior {lookback}-session high; range>=1ADR or vol>=1.2x)')
    print('k date       chg%  rng/adr v50x clears cpos gap%  base_start base_len prior surf10/20/50 tight hl prev_rng close')
    for c in out:
        print(f"{c['kind']} {c['date']} {c['chg']:+6.1f} {c['rng_adr']:5.2f} {c['v50x']:5.2f} {c['clears']:4d} {c['cpos']!s:>4} {c['gap']:+5.1f} "
              f"{c['base_start']} {c['base_len']!s:>3} {c['prior']!s:>5} {c['surf10']!s:>2}/{c['surf20']!s:>2}/{c['surf50']!s:>2} "
              f"{c['tight']!s:>5} {c['hl']!s:>5} {c['prev_rng']:5.2f} {c['close_raw']}")
    return out


WORD_CHECKS = [
    ('words:ma10', ('10-day', '10 day', 'ten day'), lambda m, d, D: m['surf_low_sessions']['sma10_k1.0'] < 3),
    ('words:ma20', ('20-day', '20 day'), lambda m, d, D: m['surf_low_sessions']['sma20_k1.0'] < 3),
    ('words:ma50', ('50-day', '50 day'), lambda m, d, D: m['surf_low_sessions']['sma50_k1.0'] < 3),
    ('words:tight', ('tight', 'narrow'), lambda m, d, D: m['tightening_last5_vs_prev5'] > 1.2),
    ('words:hivol', ('high volume', 'big volume', 'on volume'), lambda m, d, D: m['bo_vol_vs_50d'] < 1.2),
    ('words:gap', ('gap', 'gapped'), lambda m, d, D: d.o.iloc[D] <= d.c.iloc[D - 1]),
    ('words:narrow', ('narrow candle', 'narrow range day', 'tight candle'), lambda m, d, D: d.rng.iloc[D - 1] / d.adr.iloc[D - 1] > 0.8),
    ('words:weak', ('closes weak', 'closed weak', 'close weak'), lambda m, d, D: (m['bo_close_pos'] or 0) > 0.5),
]


def check(tsv, out=None):
    rows = pd.read_csv(tsv, sep='\t', dtype=str).fillna('')
    res = []
    for _, r in rows.iterrows():
        flags = []
        bd = r.get('breakout_date', '')
        t = r.get('bars_symbol') or r['ticker']
        m = {}
        if bd:
            try:
                d = load(t)
                D = rlib.idx(d, bd)
                bs = r.get('base_start') or None
                m = rlib.measure(t, bd, bs)
                P = rlib.idx(d, m['base_start'])
                if m['bo_range_adr'] < 1.0:
                    flags.append('not_expansion')
                if m['bo_vol_vs_50d'] < 1.0:
                    flags.append('not_rising_vol')
                if D - P > 1 and d.h.iloc[D] <= d.h.iloc[P + 1:D].max():
                    flags.append('no_base_clear')
                if m['prior_move'] is not None and m['prior_move'] < 1.3:
                    flags.append('no_prior_move')
                if m['base_len'] < 5:
                    flags.append('thin_base')
                cues = (r.get('cues', '') + ' ' + r.get('why', '')).lower()
                for name, words, fn in WORD_CHECKS:
                    if any(w in cues for w in words):
                        try:
                            if fn(m, d, D):
                                flags.append(name)
                        except Exception:  # noqa: BLE001
                            pass
                sd = r.get('stream_date', '')
                frame = r.get('frame', '')
                if sd and frame == 'past' and bd > sd:
                    flags.append('after_stream')
                if sd and frame == 'forward' and bd < sd:
                    flags.append('after_stream')
            except Exception as e:  # noqa: BLE001
                flags.append(f'error:{e}')
        res.append(dict(ticker=r['ticker'], setup_idx=r.get('setup_idx', ''), breakout_date=bd, confidence=r.get('confidence', ''),
                        flags=';'.join(flags), rng_adr=m.get('bo_range_adr'), v50x=m.get('bo_vol_vs_50d'), prior=m.get('prior_move'),
                        base_len=m.get('base_len'), tight=m.get('tightening_last5_vs_prev5')))
    df = pd.DataFrame(res)
    print(df.to_string(index=False))
    n_dated = int((df.breakout_date != '').sum())
    n_flag = int(((df.breakout_date != '') & (df['flags'].astype(str).str.len() > 0)).sum())
    print(f'\n{n_dated} dated rows, {n_flag} flagged for re-check')
    if out:
        df.to_csv(out, sep='\t', index=False)
    return df


if __name__ == '__main__':
    a = sys.argv[1:]
    if not a:
        print(__doc__)
        sys.exit(0)
    if a[0] == 'extract':
        extract(a[1].split(','), a[2], a[3], a[4])
    elif a[0] == 'cands':
        cands(a[1], a[2], a[3])
    elif a[0] == 'view':
        load(a[1])
        rlib.view(a[1], a[2], a[3], raw='--raw' in a)
    elif a[0] == 'check':
        check(a[1], out=(a[a.index('--out') + 1] if '--out' in a else None))
    else:
        print(__doc__)
