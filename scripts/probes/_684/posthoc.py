#!/usr/bin/env python3
"""#684 POST-HOC (after the pre-registered run; NOT one of the 63 draws) — the 09-27 extension lead
replicated under ITS OWN definition on the whole population, so its held-out read can be made.

The 09-27 lead (`hyp_rows_h5.tsv`, ERA A alerts): the least-extended third by `mi_alert_rank_shadow.
ext_xadr_eod` ran >= 5 ADR 19.5 % vs 9.1 % (n 231). That column is computed by
`alert_rank_shadow.compute_ma_distance_extension(day_open, prior_closes, adr20_frac)`: the MEDIAN over
the SMA10/20/50 (closes through D-1) that sit BELOW the gap-day OPEN of (open − SMA) / open / ADR20;
None when no SMA sits below the open. Despite its `_eod` name it uses the OPEN print — it is a 09:30
quantity. The pre-registered draw `PRE_ext_ma_mean_xadr` (mean distance to all three SMAs from the
prev close, signed) is NOT the same variable: it went the other way on the same alerted rows.
This file replicates the rank-shadow definition exactly on the captured bars, checks it against the
stored column on the alerted rows, then reads it on discovery / held-out / alerted / not-alerted.
"""
from __future__ import annotations

import math
import random
import statistics as st
from study import DRAWS, LABELLED, N_PERM, add_outcomes, load_daily, load_features, perm_p, tercile_cuts, diff_stat, fav_mask

HERE = __import__("pathlib").Path(__file__).resolve().parent


def sma(v, n):
    return sum(v[-n:]) / n if len(v) >= n else None


def ma_dist_ext(ref, prior_closes, adr_frac):
    if len(prior_closes) < 50 or not adr_frac or ref is None or ref <= 0:
        return None, None
    mas = [sma(prior_closes, k) for k in (10, 20, 50)]
    below = [m for m in mas if m is not None and m < ref]
    if not below:
        return None, True
    return st.median((ref - m) / ref / adr_frac for m in below), False


def spearman(xs, ys):
    def rk(v):
        s = sorted(range(len(v)), key=lambda i: v[i]); r = [0] * len(v)
        for k, i in enumerate(s):
            r[i] = k
        return r
    a, b = rk(xs), rk(ys); ma, mb = st.mean(a), st.mean(b)
    return sum((x - ma) * (y - mb) for x, y in zip(a, b)) / math.sqrt(sum((x - ma) ** 2 for x in a) * sum((y - mb) ** 2 for y in b))


def rate(xs):
    return sum(xs) / len(xs) if xs else float("nan")


def main():
    rows = load_features(); daily = load_daily(); add_outcomes(rows, daily)
    for r in rows:
        bars = daily.get(r["ticker"], []); dates = [b[0] for b in bars]
        r["X_ext_open_def"] = r["X_ext_open_nobelow"] = r["X_ext_pregap_def"] = None
        if r["scan_date"] not in dates:
            continue
        i0 = dates.index(r["scan_date"]); pre = bars[:i0]
        if len(pre) < 50:
            continue
        closes = [b[4] for b in pre]; adr = r.get("adr20_frac")
        e, nb = ma_dist_ext(bars[i0][1], closes, adr); r["X_ext_open_def"], r["X_ext_open_nobelow"] = e, nb
        e2, _ = ma_dist_ext(closes[-1], closes, adr); r["X_ext_pregap_def"] = e2
    sc = [r for r in rows if r["runner5"] is not None]
    out = []; p = out.append
    p("#684 POST-HOC — the 09-27 extension lead under its own definition (NOT a pre-registered draw)")
    both = [r for r in sc if r.get("RS_ext_xadr_eod") is not None and r.get("X_ext_open_def") is not None]
    p(f"replication check on alerted rows carrying the stored column: n {len(both)}, spearman {spearman([r['RS_ext_xadr_eod'] for r in both], [r['X_ext_open_def'] for r in both]):.3f}, "
      f"median |diff| {st.median(abs(r['RS_ext_xadr_eod'] - r['X_ext_open_def']) for r in both):.3f} ADR, rows within 0.1 ADR {sum(abs(r['RS_ext_xadr_eod'] - r['X_ext_open_def']) < 0.1 for r in both)}")
    both2 = [r for r in sc if r.get("RS_ext_xadr_pregap") is not None and r.get("X_ext_pregap_def") is not None]
    p(f"pregap replication: n {len(both2)}, spearman {spearman([r['RS_ext_xadr_pregap'] for r in both2], [r['X_ext_pregap_def'] for r in both2]):.3f}, rows within 0.1 ADR {sum(abs(r['RS_ext_xadr_pregap'] - r['X_ext_pregap_def']) < 0.1 for r in both2)}")
    p(f"rows with no SMA below the open (undefined, excluded as in the 09-27 read): {sum(1 for r in sc if r.get('X_ext_open_nobelow'))} of {len(sc)}")
    p("")
    rng = random.Random(684)
    disc = [r for r in sc if r["block"] == "DISCOVERY"]; held = [r for r in sc if r["block"] == "HELD-OUT"]
    for col, label in (("X_ext_open_def", "09:30 open vs the SMAs below it (the 09-27 `ext_xadr_eod` definition)"), ("X_ext_pregap_def", "prev close vs the SMAs below it (the 09-27 `ext_xadr_pregap` definition)")):
        dr = [r for r in disc if r.get(col) is not None]; cut = tercile_cuts([r[col] for r in dr])
        p(f"{label}: discovery tercile cut {cut[0]:.2f} / {cut[1]:.2f} ADR (least-extended third = <= {cut[0]:.2f})")
        for name, pop in (("discovery ALL", dr), ("discovery alerted", [r for r in dr if r["alerted"]]), ("discovery not alerted", [r for r in dr if not r["alerted"]]),
                          ("discovery alerted era-A alert-row (the 09-27 population)", [r for r in dr if r["alert_row"] == 1 and r["era"] == "A" and not r["evening_rerun_0520"]]),
                          ("HELD-OUT all", [r for r in held if r.get(col) is not None]), ("HELD-OUT alerted", [r for r in held if r.get(col) is not None and r["alerted"]]), ("HELD-OUT not alerted", [r for r in held if r.get(col) is not None and not r["alerted"]])):
            fm = fav_mask(pop, col, "cont", "LOWER", cut); lab = [int(r["runner5"]) for r in pop]
            f = [l for l, m in zip(lab, fm) if m]; rest = [l for l, m in zip(lab, fm) if not m]
            r8f = [int(r["runner8"]) for r, m in zip(pop, fm) if m]; r8r = [int(r["runner8"]) for r, m in zip(pop, fm) if not m]
            d = diff_stat(lab, fm)
            pv = perm_p(lab, fm, [r["iso_week"] for r in pop], d, rng) if (d is not None and name.startswith("discovery")) else None
            p(f"  {name}: least-extended {sum(f)}/{len(f)} = {100 * rate(f):.1f}%  vs rest {sum(rest)}/{len(rest)} = {100 * rate(rest):.1f}%  diff {100 * (d or 0):+.1f}pp"
              + (f"  week-block p {pv:.3f}" if pv is not None else "") + f"  | >= 8 ADR {100 * rate(r8f):.1f}% vs {100 * rate(r8r):.1f}%")
        labr = [r for r in sc if (r["ticker"], r["scan_date"]) in LABELLED and r.get(col) is not None]
        p("  labelled EPs: " + "; ".join(f"{r['ticker']} {r[col]:.2f} ADR ({'least-extended third' if r[col] <= cut[0] else 'rest'})" for r in labr))
        # month split on discovery
        p("  by month (least-extended vs rest): " + "; ".join(f"{m} {sum(r['runner5'] for r in dr if r['scan_date'][:7] == m and r[col] <= cut[0])}/{sum(1 for r in dr if r['scan_date'][:7] == m and r[col] <= cut[0])} vs {sum(r['runner5'] for r in dr if r['scan_date'][:7] == m and r[col] > cut[0])}/{sum(1 for r in dr if r['scan_date'][:7] == m and r[col] > cut[0])}" for m in sorted({r['scan_date'][:7] for r in dr})))
        p("")
    text = "\n".join(out) + "\n"
    (HERE / "posthoc_out.txt").write_text(text); print(text)


if __name__ == "__main__":
    main()
