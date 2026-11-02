"""His 11-02 drawn CODX/PENN charts vs the 11-02 shape-gate test: the daily bars, EMA10/21 (his chart) beside SMA10/20 (the test),
and the 3 block lows G2 compared. Read-only, pre-2025 store."""
import sys
from datetime import date
from pathlib import Path
import numpy as np
sys.path.insert(0, ".")
from scripts.probes._cb_backtest import runner

Dd = runner.load_daily(Path("/Users/alvinfung/apollo_data/cb702_pre_v2/daily_closes_all.csv.gz"))

def ema(x, n):
    a, out = 2 / (n + 1), np.empty_like(x)
    out[0] = x[0]
    for i in range(1, len(x)):
        out[i] = a * x[i] + (1 - a) * out[i - 1]
    return out

for t, d0, D in (("CODX", date(2020, 3, 2), date(2020, 4, 15)), ("PENN", date(2020, 5, 18), date(2020, 6, 22))):
    bars, cidx = runner.bars_for(Dd, Dd.tid[t])
    dates = list(bars.dates)
    c, l, h = np.asarray(bars.c, float), np.asarray(bars.l, float), np.asarray(bars.h, float)
    e10, e21 = ema(c, 10), ema(c, 21)
    s10 = np.convolve(c, np.ones(10) / 10, "full")[:len(c)]; s20 = np.convolve(c, np.ones(20) / 20, "full")[:len(c)]
    i0, iD = dates.index(d0) if d0 in dates else 0, dates.index(D)
    print(f"\n{t}  D={D}   date        low     close   EMA10   EMA21   SMA10   SMA20  closeVsE10 closeVsE21 lowVsE21")
    for i in range(i0, iD + 1):
        print(f"  {dates[i]}  {l[i]:8.2f} {c[i]:8.2f} {e10[i]:7.2f} {e21[i]:7.2f} {s10[i]:7.2f} {s20[i]:7.2f}"
              f"   {'above' if c[i] >= e10[i] else 'UNDER'}      {'above' if c[i] >= e21[i] else 'UNDER'}    {100*(l[i]/e21[i]-1):+6.1f}%")
    blocks = [(dates[iD - 14 + 5 * k], dates[iD - 10 + 5 * k], l[iD - 14 + 5 * k: iD - 9 + 5 * k].min()) for k in range(3)]
    print("  G2 blocks:", "; ".join(f"{a}..{b} low {m:.2f}" for a, b, m in blocks))
    # swing lows: a low lower than the 2 sessions either side
    sw = [(dates[i], l[i]) for i in range(i0 + 2, iD - 1) if l[i] <= l[i - 2:i + 3].min()]
    print("  swing lows:", "; ".join(f"{d} {v:.2f}" for d, v in sw))
