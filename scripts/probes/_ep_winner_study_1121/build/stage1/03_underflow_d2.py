#!/usr/bin/env python3
"""STAGE 1 / step 1c — era-B volume underflow (prereg §1 "Era-B volume underflow", critique D2). OUTCOME-FREE.
Era-B rows after 2024-12-31 are dropped at read (asserted). The split list (dates + ratios, through 2026-10-16) is read ONLY
to reproduce 01_ep_join.py's raw price exactly (the inherited post-cut input disclosed in prereg §8); it is NOT used for the
mechanism test (part 1), which uses in-cut rows only.

Part 2 copies scripts/probes/_705_ep_join_1023/01_ep_join.py::wide_table's filter lines (265-343) with ONE change: the row
selection keeps every row with 20 CONSECUTIVE baseline sessions (the original also needs the baseline zero-free), so the days
excluded only by a zero in the baseline can be counted. The original selection is reproduced as a sub-mask and asserted = 1,964.
Run: python3 03_underflow_d2.py > 03_underflow_d2.txt"""
import re
import sys
from collections import Counter
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import common as C

sys.path.insert(0, str(C.REPO))
from agents.market_intelligence import consolidation_breakout as cb      # constants + raw_factor_for (read-only, as 01_ep_join.py)
from scripts.probes._cb_backtest import runner as R                     # load_splits / load_sic (read-only)

GAP, VR, VOL_WIN = 0.09, 3.0, 20
MIN_PRICE, MIN_DV = cb.MIN_PRICE, cb.MIN_DOLLAR_VOL
ADMIT_TYPES = set(cb.UNIVERSE_SECURITY_TYPES) | {""}
TICK_RE = re.compile(r"^[A-Z]{1,5}$")
EXPORT_B_LAST = date(2026, 10, 16)
cal = C.calendars()["B"]
print("# STAGE 1 / 03 era-B volume underflow (D2). No outcome is read.")
# ---- load (01_ep_join.py::load_daily, era B) ----
parts = []; n_read = n_drop = 0
for ch in pd.read_csv(C.DAILY["B"], header=None, names=["ticker", "d", "o", "h", "l", "c", "v"], usecols=["ticker", "d", "o", "c", "v"],
                      dtype={"ticker": str, "d": str, "o": "float64", "c": "float64", "v": "float64"}, keep_default_na=False, chunksize=2_000_000):
    n_read += len(ch)
    m = ch.d <= C.CUT_B
    n_drop += int((~m).sum())
    parts.append(ch[m])
df = pd.concat(parts, ignore_index=True); del parts
assert df.d.max() <= C.CUT_B
dv_ = df.d.to_numpy(dtype="U10")
ci = np.searchsorted(cal, dv_)
on_cal = (ci < len(cal)) & (cal[np.minimum(ci, len(cal) - 1)] == dv_)
df = df[on_cal].copy(); df["ci"] = ci[on_cal].astype(np.int64)
df.sort_values(["ticker", "ci"], inplace=True, kind="mergesort"); df.reset_index(drop=True, inplace=True)
assert not df.duplicated(["ticker", "ci"]).any()
print(f"era B daily: rows read {n_read}, dropped after {C.CUT_B} {n_drop}, kept {len(df)}, symbols {df.ticker.nunique()}")
assert (n_read, n_drop, len(df)) == (13830569, 5210943, 8619626)

# ---- PART 1: mechanism test, in-cut inputs only ----
c = df.c.to_numpy(); v = df.v.to_numpy()
zero = (v <= 0) | ~np.isfinite(v)
big = c >= 1000.0
nz, nzb, na, nab = int(zero.sum()), int((zero & big).sum()), len(df), int(big.sum())
s_zero, s_all = nzb / nz, nab / na
ratio = s_zero / s_all if s_all > 0 else float("inf")
print("\n## PART 1 — mechanism test (era-B rows dated <= 2024-12-31 only)")
print(f"zero-volume rows: {nz}; of them adjusted close >= $1,000: {nzb} = {100 * s_zero:.3f}%")
print(f"all rows:         {na}; of them adjusted close >= $1,000: {nab} = {100 * s_all:.3f}%")
print(f"ratio of the two shares: {ratio:.2f}  (frozen bar: >= 5 = 'mechanism supported')")
verdict1 = "mechanism supported" if ratio >= 5 else "not supported by this test"
print(f"PART 1 VERDICT: {verdict1}")
print(f"(beside) tickers with a zero-volume row {df.ticker[zero].nunique()}; tickers with a close >= $1,000 row {df.ticker[big].nunique()};"
      f" tickers with both on the same row {df.ticker[zero & big].nunique()}")
for thr in (100.0, 10000.0):
    b2 = c >= thr
    print(f"(beside, not the bar) threshold ${thr:,.0f}: zero-volume rows {100 * (zero & b2).sum() / nz:.3f}% vs all rows {100 * b2.sum() / na:.3f}%"
          f" -> ratio {((zero & b2).sum() / nz) / (b2.sum() / na):.2f}")
fl = pd.read_csv(C.FLAGS["B"], sep="\t", usecols=["klass", "ticker", "date", "close"], dtype=str, keep_default_na=False)
fz = fl[fl.klass == "zero_volume_underflow"]
fzc = fz[fz.date <= C.CUT_B]
cc = pd.to_numeric(fzc.close, errors="coerce")
print(f"(beside) audit flag rows klass zero_volume_underflow: {len(fz)} in the flag file (the prereg's 22,658), {len(fzc)} dated <= {C.CUT_B};"
      f" of those in-cut flag rows close >= $1,000: {int((cc >= 1000).sum())} = {100 * (cc >= 1000).mean():.3f}% -> ratio vs all rows {((cc >= 1000).mean()) / s_all:.2f}")

# ---- PART 2: wide_table filter lines (01_ep_join.py 259-343), selection widened to dirty baselines ----
_, sectype = R.load_sic(Path(f"{C.DATA}/cb702/cb702_sic.psv"))
flagged = set()
f = fl[fl.klass.isin(C.FLAG_KLASSES) & (fl.date <= C.CUT_B)]
flagged = set(zip(f.ticker, f.date))
breaks = C.load_breaks()["B"]
splits = R.load_splits(Path(f"{C.DATA}/cb702/cb702_splits.psv"), through=EXPORT_B_LAST)
t = df.ticker.to_numpy(); ci = df.ci.to_numpy(); o = df.o.to_numpy()
n = len(df)
new = np.ones(n, dtype=bool); new[1:] = t[1:] != t[:-1]
g0 = np.maximum.accumulate(np.where(new, np.arange(n), 0))
hist = np.arange(n) - g0
prev_ok = (hist >= 1)
prev_ci = np.empty(n, dtype=np.int64); prev_ci[0] = -99; prev_ci[1:] = ci[:-1]
prev_ok &= (ci - prev_ci) == 1
prev_c = np.empty(n); prev_c[0] = np.nan; prev_c[1:] = c[:-1]
prev_ok &= np.isfinite(prev_c) & (prev_c > 0)
cv = np.concatenate([[0.0], np.cumsum(v)])
cz = np.concatenate([[0], np.cumsum((v <= 0) | ~np.isfinite(v))])
idx = np.arange(n)
has20 = hist >= VOL_WIN
i20 = np.where(has20, idx - VOL_WIN, 0)
consec20 = has20 & ((ci - ci[i20]) == VOL_WIN)
zeros20 = cz[idx] - cz[i20]
clean20 = consec20 & (zeros20 == 0)
mean20 = np.where(has20, (cv[idx] - cv[i20]) / VOL_WIN, np.nan)
nzcount = VOL_WIN - zeros20
with np.errstate(divide="ignore", invalid="ignore"):
    mean20_nz = np.where(has20 & (nzcount > 0), (cv[idx] - cv[i20]) / np.maximum(nzcount, 1), np.nan)   # mean of the NON-ZERO baseline sessions
    gap = o / prev_c - 1.0
valid = prev_ok & (o > 0) & (v > 0) & np.isfinite(gap)
ok_gap_all = 100.0 * gap >= 100.0 * GAP - 1e-9
sel = np.flatnonzero(valid & ok_gap_all & consec20)                    # WIDENED: clean20 not required here
dvv = c * v
med_dv = np.array([np.median(dvv[i - VOL_WIN:i]) for i in sel])
tk = t[sel]
prev_dates = [date.fromisoformat(x) for x in cal[prev_ci[sel]]]
raw_prev = np.array([prev_c[i] * cb.raw_factor_for(pd_, splits.get(tk[k], [])) for k, (i, pd_) in enumerate(zip(sel, prev_dates))])
E = cal[ci[sel]]; D = cal[prev_ci[sel]]
W = pd.DataFrame({"ticker": tk, "E": E, "D": D, "clean20": clean20[sel], "zeros20": zeros20[sel], "vol_E": v[sel],
                  "mean_v20": mean20[sel], "mean_v20_nonzero": mean20_nz[sel], "med_dv20": med_dv, "prev_close_raw": raw_prev})
W["ok_vol"] = (W.vol_E / W.mean_v20) >= VR - 1e-12
W["ok_vol_nz"] = (W.vol_E / W.mean_v20_nonzero) >= VR - 1e-12
W["ok_price"] = W.prev_close_raw >= MIN_PRICE
W["ok_liq"] = W.med_dv20 >= MIN_DV
W["ok_tick"] = W.ticker.map(lambda x: bool(TICK_RE.match(x)))
W["ok_type"] = W.ticker.map(lambda x: sectype.get(x, "")).isin(ADMIT_TYPES)
W["flag_adj"] = [(a_, b_) in flagged for a_, b_ in zip(W.ticker, W.E)]
W["break_on_E_or_D"] = [bool(breaks.get(a_) and (b_ in breaks[a_] or c_ in breaks[a_])) for a_, b_, c_ in zip(W.ticker, W.E, W.D)]
W["ok_excl"] = ~W.flag_adj & ~W.break_on_E_or_D
prim = W[W.clean20 & W.ok_vol & W.ok_price & W.ok_liq & W.ok_tick & W.ok_type & W.ok_excl]
print("\n## PART 2 — days excluded ONLY because the 20-session baseline holds a zero")
print(f"reproduction of the era-B primaries from the copied filter lines: {len(prim)} (frozen: 1,964)")
assert len(prim) == 1964, len(prim)
evB = pd.read_csv(f"{C.EVDIR}/ep_events_B.tsv.gz", sep="\t", dtype=str, keep_default_na=False)
assert set(zip(prim.ticker, prim.E)) == set(zip(evB.ticker, evB.E)), "reproduced keys differ from ep_events_B"
print("  the 1,964 (ticker, E) keys are identical to ep_events_B.tsv.gz: ASSERT OK")
dirty = W[~W.clean20 & (W.zeros20 > 0)]
listed = dirty[dirty.ok_vol_nz & dirty.ok_price & dirty.ok_liq & dirty.ok_type]                   # the terms the frozen sentence lists
strict = listed[listed.ok_tick & listed.ok_excl]                                               # + ticker pattern + exclusions (every OTHER primary term)
print(f"era-B gap >= 9% days with 20 consecutive baseline sessions holding >= 1 zero-volume session: {len(dirty)}")
print(f"  passing raw price, liquidity, type and volume(E) >= 3 x the mean of the NON-ZERO baseline sessions (the frozen sentence's terms): {len(listed)}")
print(f"  ... and also the ticker pattern + the adjustment / identity exclusions (every other primary term): {len(strict)}")
print(f"  frozen trigger: more than 20 (1% of 1,964)")
for nm, g in (("listed terms", listed), ("all other primary terms", strict)):
    y = Counter(g.E.str[:4])
    inwin = int(((g.E > C.E_MAX_A) & (g.E <= C.E_MAX_B)).sum())
    print(f"  [{nm}] n {len(g)}: per year {dict(sorted(y.items()))}; inside the study's era-B window ({C.E_MAX_A} < E <= {C.E_MAX_B}): {inwin};"
          f" distinct tickers {g.ticker.nunique()}; zeros in the baseline: median {g.zeros20.median() if len(g) else 0:g}, max {g.zeros20.max() if len(g) else 0}")
vz = dirty[dirty.ok_vol_nz]
print(f"  breakdown (added after run 1 as a check on the zero; no rule changed): of the {len(dirty)} dirty-baseline gap days, volume(E) >= 3 x the non-zero mean: {len(vz)};"
      f" of those — raw price >= $5: {int(vz.ok_price.sum())} | median $vol >= $10M: {int(vz.ok_liq.sum())} | type ok: {int(vz.ok_type.sum())}"
      f" | price AND liquidity: {int((vz.ok_price & vz.ok_liq).sum())} | largest median $vol among them ${vz.med_dv20.max():,.0f}"
      f" | liquidity ok ignoring volume: {int(dirty.ok_liq.sum())} of {len(dirty)}")
trig_l, trig_s = len(listed) > 20, len(strict) > 20
verdict2 = "TAG APPLIES" if trig_s else "tag does not apply"
print(f"PART 2 VERDICT: listed terms {len(listed)} -> {'> 20' if trig_l else '<= 20'}; all other primary terms {len(strict)} -> {'> 20' if trig_s else '<= 20'}"
      f"{' — THE TWO READINGS DISAGREE (ambiguity, reported)' if trig_l != trig_s else ''}")
if trig_l or trig_s:
    print('  => every era-B result line carries the tag "era-B population thinned of later reverse-splitters". Counted, NOT added to the population.')
else:
    print("  => no tag.")
strict.to_csv(C.HERE / "d2_excluded_days.tsv", sep="\t", index=False, float_format="%.6g")
print(f"\nD2 SUMMARY: part 1 = {verdict1} (ratio {ratio:.2f}); part 2 = {len(listed)} / {len(strict)} days vs trigger 20")
print(f"d2_excluded_days.tsv sha256 {C.sha(C.HERE / 'd2_excluded_days.tsv')}")
