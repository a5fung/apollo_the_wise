"""CODX-1 / PENN-2 (Qullamaggie's graded good setups, which he read as fits on 11-02) beside MTW 10-30 (his NOT-a-breakout
label): on HIS chart's averages (EMA10/EMA21), over the base (the session after the pole top .. D) and over the last 10.
Read-only. MTW from scripts/probes/_mtw_1102/mtw_bars.csv (to 10-30, the declared exception in shape_gates_1102)."""
import csv, sys
from datetime import date
from pathlib import Path
import numpy as np
sys.path.insert(0, ".")
from scripts.probes._cb_backtest import runner

def ema(x, n):
    a, out = 2 / (n + 1), np.empty_like(x)
    out[0] = x[0]
    for i in range(1, len(x)):
        out[i] = a * x[i] + (1 - a) * out[i - 1]
    return out

def series_store(t):
    Dd = series_store.Dd = getattr(series_store, "Dd", None) or runner.load_daily(Path("/Users/alvinfung/apollo_data/cb702_pre_v2/daily_closes_all.csv.gz"))
    b, _ = runner.bars_for(Dd, Dd.tid[t])
    return list(b.dates), np.asarray(b.h, float), np.asarray(b.l, float), np.asarray(b.c, float)

def series_mtw():
    rows = list(csv.DictReader(open("scripts/probes/_mtw_1102/mtw_bars.csv")))
    return ([date.fromisoformat(r["trade_date"]) for r in rows], np.array([float(r["high_price"]) for r in rows]),
            np.array([float(r["low_price"]) for r in rows]), np.array([float(r["close"]) for r in rows]))

CASES = (("CODX-1 (QM good)", "CODX", date(2020, 4, 15)), ("PENN-2 (QM good)", "PENN", date(2020, 6, 22)),
         ("MTW 10-30 (his NO)", "MTW", date(2026, 10, 30)))
for name, t, D in CASES:
    dates, h, l, c = series_mtw() if t == "MTW" else series_store(t)
    iD = dates.index(D)
    rng = (h - l) / c
    adr = rng[iD - 19:iD + 1].mean()
    P = iD - 30 + int(np.argmax(h[iD - 30:iD - 2]))      # pole top: highest high in the 30 sessions before, at least 3 back
    e10, e21 = ema(c, 10), ema(c, 21)
    base = range(P + 1, iD + 1)
    B = min(base, key=lambda i: l[i])
    last10 = range(iD - 9, iD + 1)
    def stats(idx):
        idx = list(idx)
        u10 = sum(c[i] < e10[i] for i in idx); u21 = sum(c[i] < e21[i] for i in idx)
        cross = sum((c[i] >= e21[i]) != (c[i - 1] >= e21[i - 1]) for i in idx)
        worst = min((l[i] / e21[i] - 1) / adr for i in idx)
        return f"closes under EMA10 {u10}/{len(idx)}, under EMA21 {u21}/{len(idx)}, crosses of EMA21 {cross}, worst low {worst:+.2f} ADR vs EMA21"
    after = [i for i in range(B + 1, iD + 1)]
    sw = [i for i in range(P + 2, iD - 1) if l[i] <= l[i - 2:i + 3].min()]
    print(f"\n{name}  D {D}  ADR20 {adr:.1%}  pole top {dates[P]} {h[P]:.2f}  base {iD - P} sessions  bottom {dates[B]} {l[B]:.2f} (session {B - P} of {iD - P})")
    print(f"  base   : {stats(base)}")
    print(f"  last 10: {stats(last10)}")
    print(f"  after the bottom: {len(after)} sessions, closes all above the bottom: {all(c[i] > l[B] for i in after)}, "
          f"lowest close after it {min(c[i] for i in after) / l[B] - 1:+.1%} over the bottom" if after else "  bottom is D")
    print("  swing lows in the base:", "  ".join(f"{dates[i]:%m-%d} {l[i]:.2f}" for i in sw))
    print(f"  depth of base: bottom {l[B] / h[P] - 1:+.1%} under the pole top ({(1 - l[B] / h[P]) / adr:.1f} ADR)")

print("\nslope of HIS averages across the base (pole top -> D), and the EMA10-over-EMA21 spread at D, in ADR units")
for name, t, D in CASES:
    dates, h, l, c = series_mtw() if t == "MTW" else series_store(t)
    iD = dates.index(D); rng = (h - l) / c; adr = rng[iD - 19:iD + 1].mean()
    P = iD - 30 + int(np.argmax(h[iD - 30:iD - 2]))
    e10, e21 = ema(c, 10), ema(c, 21)
    sl21 = (e21[iD] / e21[P] - 1); sl21_10 = (e21[iD] / e21[iD - 10] - 1)
    days_e10_over_e21 = sum(e10[i] > e21[i] for i in range(P + 1, iD + 1))
    print(f"  {name:20s} EMA21 base {sl21:+.1%} ({sl21 / adr:+.1f} ADR), last 10 {sl21_10:+.1%} ({sl21_10 / adr:+.1f} ADR); "
          f"EMA10 above EMA21 on {days_e10_over_e21}/{iD - P} base days; spread at D {(e10[iD] / e21[iD] - 1) / adr:+.2f} ADR")
