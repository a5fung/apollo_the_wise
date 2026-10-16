#!/usr/bin/env python3
"""STEP 0 — composition ONLY. No outcome is computed or read here (no forward bar, no run_xadr).
Writes composition.out. Run: PYTHONDONTWRITEBYTECODE=1 python3 composition.py
"""
from __future__ import annotations

import statistics
from collections import Counter
from pathlib import Path

from common import HERE, NINE_M, load_rows

LABELLED = [("BFLY", "2026-06-18"), ("PLTR", "2026-08-04"), ("TEAM", "2026-08-07"), ("HTFL", "2026-08-14"), ("MRNA", "2026-08-19")]


def q(vals, p):
    s = sorted(vals)
    return s[min(len(s) - 1, int(p * (len(s) - 1) + 0.5))]


def main() -> None:
    rows = load_rows()
    out: list[str] = []
    p = out.append
    p("STEP 0 — composition only (no outcome read). Source: scripts/probes/_684/{features.tsv,daily.tsv.gz,orb.tsv} pulled 2026-09-28.")
    p(f"population rows {len(rows)}   names {len({r['ticker'] for r in rows})}   scan dates {len({r['scan_date'] for r in rows})}   "
      f"window {min(r['scan_date'] for r in rows)} .. {max(r['scan_date'] for r in rows)}")
    p("by month (n / alerted / scored-not-alerted):")
    for m in sorted({r['scan_date'][:7] for r in rows}):
        g = [r for r in rows if r['scan_date'][:7] == m]
        p(f"  {m}: {len(g):4d}  alerted {sum(int(r['alerted']) for r in g):4d}  not {sum(1 - int(r['alerted']) for r in g):4d}")
    for blk in ("DISCOVERY", "HELD-OUT"):
        g = [r for r in rows if r['block'] == blk]
        p(f"block {blk}: n {len(g)}  alerted {sum(int(r['alerted']) for r in g)}  ISO weeks {len({r['iso_week'] for r in g})}")
    p(f"era: {dict(Counter(r['era'] for r in rows))}")
    # share count coverage
    sc = [r for r in rows if r['SC_shares'] is not None]
    p("")
    p(f"gap-day share count present: {len(sc)} of {len(rows)} (missing: {', '.join(r['ticker'] + ' ' + r['scan_date'] for r in rows if r['SC_shares'] is None)})")
    v = [r['SC_shares'] for r in sc]
    p(f"gap-day shares: p10 {q(v, .1):,.0f}  p25 {q(v, .25):,.0f}  median {q(v, .5):,.0f}  p75 {q(v, .75):,.0f}  p90 {q(v, .9):,.0f}")
    for blk in ("ALL", "DISCOVERY", "HELD-OUT"):
        g = [r for r in sc if blk == "ALL" or r['block'] == blk]
        n9 = sum(1 for r in g if r['SC_shares'] >= NINE_M)
        al = [r for r in g if int(r['alerted'])]
        p(f"  >= 9M shares, {blk}: {n9} of {len(g)} ({100 * n9 / len(g):.1f} %)   alerted {sum(1 for r in al if r['SC_shares'] >= NINE_M)} of {len(al)}   "
          f"not-alerted {sum(1 for r in g if not int(r['alerted']) and r['SC_shares'] >= NINE_M)} of {len(g) - len(al)}")
    sm = [r for r in sc if r.get('split_mismatch') == 1.0]
    p(f"  split_mismatch rows (scan-log prev close vs adjusted bar differ > 3 %; their share counts are split-ADJUSTED): {len(sm)}: "
      + ", ".join(f"{r['ticker']} {r['scan_date']}" for r in sm))
    # by price band
    p("  >= 9M by price band (prev close): " + "; ".join(
        f"{name} {sum(1 for r in sc if lo <= (r['PRE_prev_close'] or 0) < hi and r['SC_shares'] >= NINE_M)} of {sum(1 for r in sc if lo <= (r['PRE_prev_close'] or 0) < hi)}"
        for lo, hi, name in ((0, 20, '$5-20'), (20, 100, '$20-100'), (100, 1e9, '$100+'))))
    # RVOL coverage
    p("")
    for col in ("CLOSE_vol_vs_avg50", "PRE_rel_volume_scan", "PRE_pm_rvol", "PRE_projected_vol_multiple", "O945_orb_vol_vs_20d", "CLOSE_vol_vs_max250", "PRE_dollar_vol_20d", "PRE_adr20_pct"):
        vv = [r[col] for r in rows if r.get(col) is not None]
        p(f"{col}: filled {len(vv)} of {len(rows)}   p25 {q(vv, .25):.4g}  median {q(vv, .5):.4g}  p75 {q(vv, .75):.4g}")
    # early proxy coverage + feed check
    e = [r for r in rows if r['E_orb_shares'] is not None]
    p("")
    p(f"09:30-09:44 shares (early proxy) present: {len(e)} of {len(rows)}   alerted {sum(int(r['alerted']) for r in e)} of {sum(int(r['alerted']) for r in rows)}   "
      f"not-alerted {sum(1 - int(r['alerted']) for r in e)} of {sum(1 - int(r['alerted']) for r in rows)}")
    fr = [r['E_orb_share_of_day'] for r in e if r['E_orb_share_of_day'] is not None]
    p(f"FEED CHECK — first-15-minute shares / full-day shares: p10 {q(fr, .1):.3f}  median {q(fr, .5):.3f}  p90 {q(fr, .9):.3f}  "
      f"(consolidated feed ~0.1-0.4 on a gap day; IEX-only would read ~0.01-0.03)  rows > 1.0: {sum(1 for x in fr if x > 1.0)}")
    eo = [r['E_orb_shares'] for r in e]
    p(f"09:30-09:44 shares: p25 {q(eo, .25):,.0f}  median {q(eo, .5):,.0f}  p75 {q(eo, .75):,.0f}")
    # correlations (ranks) — composition, no outcome
    def spearman(a, b):
        pairs = [(x, y) for x, y in zip(a, b) if x is not None and y is not None]
        def rk(xs):
            o = sorted(range(len(xs)), key=lambda i: xs[i]); r_ = [0.0] * len(xs)
            for k, i in enumerate(o):
                r_[i] = k
            return r_
        xa, ya = rk([x for x, _ in pairs]), rk([y for _, y in pairs])
        mx, my = statistics.mean(xa), statistics.mean(ya)
        num = sum((x - mx) * (y - my) for x, y in zip(xa, ya))
        den = (sum((x - mx) ** 2 for x in xa) * sum((y - my) ** 2 for y in ya)) ** 0.5
        return num / den, len(pairs)
    p("")
    p("rank correlations with gap-day share count (composition — what share count is made of):")
    for col in ("CLOSE_vol_vs_avg50", "PRE_vol_20d_shares", "PRE_dollar_vol_20d", "PRE_prev_close", "PRE_adr20_pct", "PRE_gap_pct_scan", "E_orb_shares", "ep_score"):
        rho, n = spearman([r['SC_shares'] for r in rows], [r.get(col) for r in rows])
        p(f"  {col}: rho {rho:+.2f} (n {n})")
    # labelled
    p("")
    p("his labelled EPs in the population (operator_labelled_eps.md; ABNB 08-07 + CHPT 09-03 never scored, PENG 10-07 outside window):")
    for t, d in LABELLED:
        r = next((r for r in rows if r['ticker'] == t and r['scan_date'] == d), None)
        if r is None:
            p(f"  {t} {d}: NOT IN")
            continue
        p(f"  {t} {d}: block {r['block']} alerted {int(r['alerted'])} shares {r['SC_shares']:,.0f} (>=9M {int(r['SC_ge9m'])})  RVOL50 {r.get('CLOSE_vol_vs_avg50'):.2f}  "
          f"09:30-09:44 shares {r['E_orb_shares'] if r['E_orb_shares'] is None else format(r['E_orb_shares'], ',.0f')}")
    text = "\n".join(out) + "\n"
    (HERE / "composition.out").write_text(text)
    print(text)


if __name__ == "__main__":
    main()
