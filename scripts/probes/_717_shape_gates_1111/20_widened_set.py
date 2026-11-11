#!/usr/bin/env python3
"""#717 round 5: WIDEN Qullamaggie's test set with the buys OUR detector left undated. No gate is changed.

The scorecard's 269 buys are the positions our own breakout / EP detector could date. 1,040 more positions of his
'A - Positions' panel are `undated_reason = no_event_in_window`: the buy window (lo .. hi) is known, our detector just
found no event in it. This builds the widened set from them, asks whether the name was on the breakout v1 list on ANY
night before a session of the window (the nights lo-1 .. hi-1), and draws 12 of the ones the list misses.

Reads (all pre-2025; nothing dated 2025 or later is opened):
  /Users/alvinfung/apollo_data/cb702/qm_streams/holdings_1024/entries.tsv      (his positions, 2017-2023)
  /Users/alvinfung/apollo_data/cb702_pre_v2/daily_closes_all.csv.gz            (daily bars 2016-01-04 .. 2022-06-30)
  /Users/alvinfung/apollo_data/qm_breakouts_1102/features_eraA.parquet         (rs_best + raw close per listable
      name-night with strength >= 30, nights 2016-12-30 .. 2022-03-31 — the 11-02 research's cross-section)
Era B (windows ending after 2022-03-31) is LEFT OUT: its bars live in the store that also holds 2025-26.

    python3 scripts/probes/_717_shape_gates_1111/20_widened_set.py > scripts/probes/_717_shape_gates_1111/20_widened_set.out
"""
import csv
import gzip
import random
import sys
from collections import Counter
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, ".")
from agents.market_intelligence import breakout_v1 as bv, consolidation_breakout as cb  # noqa: E402
from scripts.probes._cb_backtest import runner  # noqa: E402

HERE = Path("scripts/probes/_717_shape_gates_1111")
FX = Path("tests/fixtures/qm_breakout_scorecard")
DATA = Path("/Users/alvinfung/apollo_data")
EP_GAP = 0.09            # the EP dating's own gap floor (scripts/probes/_705_ep_join_1023/01_ep_join.py GAP = 0.09)
ERA_A_LAST_NIGHT = date(2022, 3, 31)
HIST = 300               # bars kept before the first night (as the scorecard fixture)

e = pd.read_csv(DATA / "cb702/qm_streams/holdings_1024/entries.tsv", sep="\t", dtype=str, keep_default_na=False)
print(f"positions {len(e)}")
u = e[e.undated_reason == "no_event_in_window"].copy()
print(f"undated because our detector found no event in the window: {len(u)}")
steps = [("window_len <= 5", lambda d: d.window_len.astype(int) <= 5), ("flicker False", lambda d: d.flicker == "False"),
         ("n_sightings >= 2", lambda d: d.n_sightings.astype(int) >= 2), ("has_bars True", lambda d: d.has_bars == "True"),
         ("not `initial`", lambda d: d.initial == "False"),
         ("window ends by 2022-04-01 (era A bars; later windows need the store that holds 2025-26)", lambda d: d.hi <= "2022-04-01")]
for name, f in steps:
    u = u[f(u)]
    print(f"  after {name}: {len(u)}")

Dd = runner.load_daily(DATA / "cb702_pre_v2/daily_closes_all.csv.gz")
assert Dd.cal[-1] < date(2025, 1, 1)
F = pd.read_parquet(DATA / "qm_breakouts_1102/features_eraA.parquet", columns=["scan_date", "ticker", "rs_best", "raw_close"])
RS = {(t, d): (r, rc) for t, d, r, rc in zip(F.ticker, F.scan_date, F.rs_best, F.raw_close)}
del F

rows, drop = [], Counter()
bars_cache = {}
for r in u.itertuples():
    t = r.sym_a or r.sym
    if t not in Dd.tid:
        drop["ticker not in the bar store"] += 1
        continue
    if t not in bars_cache:
        bars_cache[t] = runner.bars_for(Dd, Dd.tid[t])
    b, cidx = bars_cache[t]
    lo, hi = date.fromisoformat(r.lo), date.fromisoformat(r.hi)
    win = [i for i, d in enumerate(b.dates) if lo <= d <= hi]
    if not win or win[0] < 1:
        drop["no bar inside the window"] += 1
        continue
    if b.dates[win[-1] - 1] > ERA_A_LAST_NIGHT:
        drop["a night after 2022-03-31"] += 1
        continue
    if any(b.o[i] >= (1.0 + EP_GAP) * b.c[i - 1] for i in win):
        drop["EP-like gap in the window (open >= 9% over the prior close)"] += 1
        continue
    rows.append((r, t, b, cidx, win))
for k, v in drop.items():
    print(f"  dropped — {k}: {v}")
print(f"WIDENED SET: {len(rows)} buys ({len({(x[1]) for x in rows})} tickers); by year {dict(sorted(Counter(x[0].hi[:4] for x in rows).items()))}")
orig = {(r["ticker"], r["E"]) for r in csv.DictReader(open(FX / "buys.tsv"), delimiter="\t")}
print(f"  overlap with the 269 scorecard buys (same ticker, a scorecard buy day inside the window): "
      f"{sum(any((t, b.dates[i].isoformat()) in orig for i in win) for _, t, b, _, win in rows)}")

# ── the list on each night lo-1 .. hi-1 ────────────────────────────────────────────────────────────────────────
GATES = bv.GATES
res = []
for r, t, b, cidx, win in rows:
    nights = [i - 1 for i in win]
    per = []
    for D in nights:
        key = (t, b.dates[D].isoformat())
        rs, raw = RS.get(key, (None, None))
        try:
            v = bv.v1_gates(b, D, rs_best=rs, raw_close=raw, cidx=cidx)
        except Exception as ex:                                  # too little history for the pole window
            per.append({"failed": ["history"], "ok": False, "a2": False, "ranked": rs is not None, "D": D})
            continue
        a2 = False
        if v["ok"]:
            sg = bv.shape_gates(b, D, P=v["pole_idx"], adr20=v["adr20"])
            a2 = all(sg[k]["pass"] for k in bv.SHAPE_GATES_V2)
        per.append({"failed": v["failed"], "ok": v["ok"], "a2": a2, "ranked": rs is not None, "D": D})
    res.append((r, t, b, win, per))
on = sum(any(p["ok"] for p in per) for *_, per in res)
on_a2 = sum(any(p["a2"] for p in per) for *_, per in res)
n = len(res)
print("\n=== ON-LIST RATE (the name on the list on ANY night lo-1 .. hi-1) ===")
print(f"{'set':46s}{'n':>6s}{'current list':>16s}{'amendment 2':>16s}")
print(f"{'widened (undated by our detector)':46s}{n:6d}{on:9d} ({on / n:4.0%}){on_a2:9d} ({on_a2 / n:4.0%})")
print(f"{'original scorecard (the night before his buy)':46s}{269:6d}{263:9d} ({263 / 269:4.0%}){249:9d} ({249 / 269:4.0%})")
one = [x for x in res if len(x[3]) == 1]
print(f"  widened, one-session windows only (the buy day is known exactly): n = {len(one)}, current list "
      f"{sum(x[4][0]['ok'] for x in one)} ({sum(x[4][0]['ok'] for x in one) / max(1, len(one)):.0%}), amendment 2 "
      f"{sum(x[4][0]['a2'] for x in one)} ({sum(x[4][0]['a2'] for x in one) / max(1, len(one)):.0%})")

print("\n=== PER-RULE MISS TABLE of the EXISTING list gates on the widened set ===")
print("A gate 'blocks' a buy when it fails on EVERY night of the window; 'alone' = it is the only gate failing on the buy's best night")
print("(the night with the fewest failed gates). `rs` includes names the 11-02 cross-section did not rank at all (strength under")
print("30, a non-listable type such as an ETF, or too little history) — counted separately below.")
blocks, alone = Counter(), Counter()
unranked = 0
for *_, per in res:
    if any(p["ok"] for p in per):
        continue
    if not any(p["ranked"] for p in per):
        unranked += 1
    for g in GATES:
        if all(g in p["failed"] for p in per):
            blocks[g] += 1
    best = min(per, key=lambda p: len(p["failed"]))
    if len(best["failed"]) == 1:
        alone[best["failed"][0]] += 1
missed = n - on
print(f"missed by the current list: {missed} of {n}")
for g in sorted(GATES, key=lambda g: -blocks[g]):
    print(f"  {g:12s} blocks {blocks[g]:4d} ({blocks[g] / n:4.0%} of the set, {blocks[g] / max(1, missed):4.0%} of the missed)   alone {alone[g]:4d}")
print(f"  of the missed, never ranked on any night of the window (under 30 / not listable / short history): {unranked}")
print("number of gates failing on the best night, missed buys:", dict(sorted(Counter(len(min(per, key=lambda p: len(p['failed']))['failed'])
                                                                               for *_, per in res if not any(p['ok'] for p in per)).items())))

# ── the fixture: buys + bars <= hi (no bar after the window) ───────────────────────────────────────────────────
with open(FX / "buys_undated_widened.tsv", "w") as f:
    f.write("eid\tsym\tticker\tlo\thi\twindow_len\tn_sightings\ton_current_list_any_night\ton_amendment2_any_night\tfailed_best_night\n")
    for r, t, b, win, per in res:
        best = min(per, key=lambda p: len(p["failed"]))
        f.write(f"{r.eid}\t{r.sym}\t{t}\t{r.lo}\t{r.hi}\t{r.window_len}\t{r.n_sightings}\t{int(any(p['ok'] for p in per))}\t"
                f"{int(any(p['a2'] for p in per))}\t{','.join(best['failed'])}\n")
with gzip.GzipFile(FX / "bars_undated_widened.psv.gz", "wb", mtime=0) as gz:
    gz.write(b"eid|ticker|date|o|h|l|c|v\n")
    for r, t, b, win, per in res:
        for j in range(max(0, win[0] - 1 - HIST), win[-1] + 1):
            gz.write(f"{r.eid}|{t}|{b.dates[j].isoformat()}|{float(b.o[j])!r}|{float(b.h[j])!r}|{float(b.l[j])!r}|{float(b.c[j])!r}|{float(b.v[j])!r}\n".encode())

# ── the sheet: 12 random buys the current list misses, bars ending the night before lo ─────────────────────────
import matplotlib  # noqa: E402
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.ticker import NullFormatter, ScalarFormatter  # noqa: E402

miss = [x for x in res if not any(p["ok"] for p in x[4])]
pick = random.Random(1111).sample(miss, 12)


def ema(x, k):
    a, o = 2 / (k + 1), np.empty(len(x))
    o[0] = x[0]
    for i in range(1, len(x)):
        o[i] = a * x[i] + (1 - a) * o[i - 1]
    return o


fig = plt.figure(figsize=(26, 18))
gs = fig.add_gridspec(6, 4, height_ratios=[3, 1] * 3, hspace=0.45, wspace=0.12)
key = []
for k, (r, t, b, win, per) in enumerate(pick):
    L = chr(ord("A") + k)
    end = win[0] - 1                                             # the night before lo's first session
    off = max(0, end + 1 - 252)
    o, h, l, c, v = (np.asarray(x, float)[off:end + 1] for x in (b.o, b.h, b.l, b.c, b.v))
    cf = np.asarray(b.c, float)[:end + 1]
    rr, cc = divmod(k, 4)
    ax = fig.add_subplot(gs[2 * rr, cc])
    axv = fig.add_subplot(gs[2 * rr + 1, cc], sharex=ax)
    for i in range(len(c)):
        col = "#26a69a" if c[i] >= o[i] else "#ef5350"
        ax.vlines(i, l[i], h[i], color=col, lw=0.7)
        ax.add_patch(plt.Rectangle((i - 0.3, min(o[i], c[i])), 0.6, max(abs(c[i] - o[i]), 1e-9), color=col))
        axv.bar(i, v[i], color=col, width=0.7)
    s50 = np.full(len(cf), np.nan)
    if len(cf) >= 50:
        cs = np.cumsum(np.insert(cf, 0, 0.0))
        s50[49:] = (cs[50:] - cs[:-50]) / 50
    for arr, col in ((ema(cf, 10), "#1f77b4"), (ema(cf, 21), "#d62728"), (s50, "#2ca02c")):
        ax.plot(range(len(c)), arr[off:], color=col, lw=0.9)
    ax.hlines(float(h[-5:].max()), len(c) - 30, len(c) - 1, colors="black", linestyles="dashed", lw=1.0)
    ax.set_yscale("log")
    ax.yaxis.set_major_formatter(ScalarFormatter())
    ax.yaxis.set_minor_formatter(NullFormatter())
    ax.set_title(L, fontsize=13, loc="left")
    ax.tick_params(labelsize=6)
    axv.tick_params(labelsize=5)
    ax.set_xticks([])
    axv.set_xticks([])
    best = min(per, key=lambda p: len(p["failed"]))
    key.append(f"{L}|{r.sym}|{t}|{r.lo}|{r.hi}|{r.window_len}|{','.join(best['failed'])}")
fig.suptitle("12 Qullamaggie positions our detector could not date AND the breakout list misses — each chart ends the night before his buy "
             "window opens (~1 year of daily bars). Dashed = the 5-day high. EMA10 blue, EMA21 red, SMA50 green.", fontsize=12)
fig.savefig(HERE / "qm_widened_missed_sheet.png", dpi=100, bbox_inches="tight")
(HERE / "qm_widened_missed_sheet.png.key_do_not_show.txt").write_text(
    "#717 round 5: 12 drawn at random (seed 1111) from the widened buys the current list misses on every night of the window.\n"
    "letter|sym|ticker|lo|hi|window_len|gates failing on the best night\n" + "\n".join(key) + "\n")
print(f"\nsheet: {HERE / 'qm_widened_missed_sheet.png'} (12 of {len(miss)} missed)")
