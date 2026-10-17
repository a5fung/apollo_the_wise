"""#702 P0: the liquid universe = tickers that, on any session from 2022-03-28, had a RAW close >= $5 and a
20-session median dollar volume >= $10M (split-invariant), ticker ^[A-Z]{1,5}$, security type CS/ADRC/unknown.
Writes liquid_tickers.txt (ticker|last liquid date = the SIC pull list) next to the data. Usage: liquid_universe.py <data_dir>"""
import sys, re, collections
import numpy as np, pandas as pd
d = sys.argv[1]
df = pd.read_csv(f"{d}/daily_closes_all.csv.gz", header=None, names=["t", "d", "o", "h", "l", "c", "v"],
                 dtype={"t": str}, keep_default_na=False)
df = df[df["t"].str.fullmatch(r"[A-Z]{1,5}")]
sect = {}
for line in open(f"{d}/small_pulls.psv"):
    f = line.rstrip("\n").split("|")
    if f[0] == "sectype":
        sect[f[1]] = f[2]
df = df[df["t"].map(lambda t: sect.get(t, "") in ("CS", "ADRC", ""))]
spl = collections.defaultdict(list)
for line in open(f"{d}/cb702_splits.psv"):
    t, ex, fr, to = line.rstrip("\n").split("|")
    if fr and to and float(fr) > 0:
        spl[t].append((ex, float(to) / float(fr)))
df.sort_values(["t", "d"], inplace=True, kind="mergesort")
df["dv"] = df["c"] * df["v"]
df["mdv"] = df.groupby("t")["dv"].transform(lambda s: s.rolling(20, min_periods=20).median())
def fac(t, dates):
    f = np.ones(len(dates))
    for ex, r in spl.get(t, []):
        f[dates < ex] *= r
    return f
raw = np.empty(len(df))
i = 0
for t, g in df.groupby("t", sort=False):
    n = len(g)
    raw[i:i + n] = g["c"].to_numpy() * fac(t, g["d"].to_numpy(dtype=str))
    i += n
df["raw"] = raw
ok = df[(df["d"] >= "2022-03-28") & (df["raw"] >= 5) & (df["mdv"] >= 10e6)]
last = ok.groupby("t")["d"].max()
names = sorted(last.index)
open(f"{d}/liquid_tickers.txt", "w").write("".join(f"{t}|{last[t]}\n" for t in names))
print("rows", len(df), "tickers", df["t"].nunique(), "liquid tickers", len(names),
      "liquid ticker-days", len(ok), "per-day median", int(ok.groupby("d").size().median()))
