"""Breakout v1 PAPER phase 2 (F1, his ruling 2026-10-29): build the intraday cumulative-volume curve ONCE.

F1 (RULED, "ok" to the rec): the breakout-volume check at the intraday buy = volume so far vs the stock's normal
volume BY THAT MINUTE >= 1.2x. "Normal volume by minute m" = the 50-day average daily volume x the share of a day's
volume that is normally done by the END of minute m. This script measures that share ONCE from the stored minute
bars and writes it as a constant table (390 regular-hours minutes) into
`agents/market_intelligence/broker/breakout_v1_volume_curve.py`.

ONE curve for every stock (pooled across every stored ticker-day), not a per-stock curve — a per-stock curve is a
later refinement.

SOURCE: /Users/alvinfung/apollo_data/cb702_pre_v2/minutes/<YYYY-MM-DD>.psv.gz, one row per (ticker, minute):
    ticker|minute|open|high|low|close|volume      minute = 0..389 from 09:30 ET (regular hours only)
This is the minute export the consolidation-breakout backtest (#702, pre-v2) fetched: the backtest's candidate
ticker-days, 2017-03-02 .. 2022-01-03 (SIP feed). The population and date range are printed below.

THE DENOMINATOR IS THE DAY'S FULL DAILY VOLUME (fix 2026-10-30, review finding: the first build divided by the day's
REGULAR-HOURS volume and forced [389] = 1.0, while the live bar `vol_bar` = 1.2 x the 50-session mean of FULL daily volume
from `mi_daily_closes` (Polygon grouped daily: extended hours + the 16:00 closing cross included) — a units mismatch that
made F1 ask ~1.45-1.6x normal instead of his 1.2x). The live numerator is regular-hours minute volume only
(`breakout_v1_entry.bars_by_minute`), so the like-for-like share is regular-hours volume through m / FULL daily volume:
volume so far >= vol_bar x share[m]  <=>  volume so far >= 1.2 x (the 50-day average x the share normally done by m).
DAILY SOURCE: /Users/alvinfung/apollo_data/cb702_pre_v2/daily_closes_all.csv.gz (ticker,date,o,h,l,c,volume — the same
Polygon grouped-daily family as `mi_daily_closes`; split-adjusted like the minute export, checked on AAPL 2020-06-01).

METHOD (stated, not tuned):
  * a session is FULL when its longest ticker-day reaches minute 389 (15:59); early-close sessions are dropped so a
    210-minute day cannot bend the curve;
  * per ticker-day: cum_share[m] = regular-hours volume through the END of minute m / the day's FULL daily volume
    (a minute with no bar adds 0). Dropped (counts printed): no daily row, daily volume <= 0, zero regular-hours volume,
    and regular-hours volume > 1.02 x daily volume (impossible for one tape — a data mismatch between the two exports);
  * the curve = the MEAN over ticker-days of cum_share[m] (every ticker-day weighs the same — the ratio-of-sums
    alternative would let a few huge days set the curve); the median is printed beside it for reference;
  * monotone non-decreasing (a mean of monotone series already is; asserted). NOT forced to 1.0 at 15:59: the last
    value is the share of a day's full volume done in regular hours (~0.8).

Run:  .venv/bin/python scripts/probes/_breakout_v1_phase2/build_volume_curve.py
Writes the module and prints the stats; output captured in build_volume_curve.out beside this file.
"""
from __future__ import annotations

import gzip
import sys
from collections import Counter
from pathlib import Path

import numpy as np

SRC = Path("/Users/alvinfung/apollo_data/cb702_pre_v2/minutes")
DAILY = Path("/Users/alvinfung/apollo_data/cb702_pre_v2/daily_closes_all.csv.gz")
MISMATCH_TOL = 1.02   # regular-hours volume above this x the daily volume = the two exports disagree -> dropped
REPO = Path(__file__).resolve().parents[3]
OUT_MODULE = REPO / "agents" / "market_intelligence" / "broker" / "breakout_v1_volume_curve.py"
N_MIN = 390


def _read_day(path: Path):
    """{ticker: np.ndarray(390) volume per minute} for one session file."""
    vols: dict[str, np.ndarray] = {}
    with gzip.open(path, "rt") as f:
        for line in f:
            p = line.rstrip("\n").split("|")
            if len(p) < 7:
                continue
            m = int(p[1])
            if not 0 <= m < N_MIN:
                continue
            arr = vols.get(p[0])
            if arr is None:
                arr = vols[p[0]] = np.zeros(N_MIN, dtype=np.float64)
            arr[m] += float(p[6])
    return vols


def main() -> int:
    files = sorted(SRC.glob("*.psv.gz"))
    if not files:
        print(f"no minute files under {SRC}")
        return 1
    import pandas as pd
    first_day, last_day = files[0].name[:10], files[-1].name[:10]
    print(f"loading daily volumes {DAILY} ({first_day} .. {last_day})", file=sys.stderr)
    dly = pd.read_csv(DAILY, header=None, usecols=[0, 1, 6], names=["t", "d", "v"],
                      dtype={"t": str, "d": str, "v": np.float64})
    dly = dly[(dly["d"] >= first_day) & (dly["d"] <= last_day)]
    daily_by_day = {d: dict(zip(g["t"], g["v"])) for d, g in dly.groupby("d")}
    del dly
    n_no_daily = n_daily_zero = n_mismatch = 0
    sum_share = np.zeros(N_MIN, dtype=np.float64)
    shares_for_median: list[np.ndarray] = []
    n_days_used = n_days_early = 0
    n_td = n_td_zero = 0
    tickers: set[str] = set()
    per_year: dict[str, list] = {}
    for i, path in enumerate(files):
        day = path.name[:10]
        vols = _read_day(path)
        if not vols:
            continue
        last_minute = max(int(np.flatnonzero(v > 0).max()) if (v > 0).any() else -1 for v in vols.values())
        if last_minute < N_MIN - 1:
            n_days_early += 1
            continue
        n_days_used += 1
        dvol = daily_by_day.get(day, {})
        for t, v in vols.items():
            tot = v.sum()
            if tot <= 0:
                n_td_zero += 1
                continue
            dv = dvol.get(t)
            if dv is None or not np.isfinite(dv):
                n_no_daily += 1
                continue
            if dv <= 0:
                n_daily_zero += 1
                continue
            if tot > MISMATCH_TOL * dv:
                n_mismatch += 1
                continue
            cs = np.cumsum(v) / dv
            sum_share += cs
            n_td += 1
            tickers.add(t)
            per_year.setdefault(day[:4], []).append(cs[[4, 29, 149, 329]])
            if n_td % 7 == 0:          # a deterministic 1-in-7 sample for the printed median (memory)
                shares_for_median.append(cs.astype(np.float32))
        if (i + 1) % 200 == 0:
            print(f"  {i + 1}/{len(files)} files, {n_td:,} ticker-days", file=sys.stderr)

    curve = sum_share / n_td
    assert np.all(np.diff(curve) >= -1e-12), "mean curve not monotone"
    curve = np.maximum.accumulate(curve)
    med = np.median(np.vstack(shares_for_median), axis=0)

    first, last = files[0].name[:10], files[-1].name[:10]
    print(f"source        {SRC}")
    print(f"sessions      {len(files)} files {first} .. {last}; FULL sessions used {n_days_used}, "
          f"early-close sessions dropped {n_days_early}")
    print(f"ticker-days   {n_td:,} used ({len(tickers):,} distinct tickers); dropped: zero regular-hours volume "
          f"{n_td_zero:,}, no daily row {n_no_daily:,}, daily volume <= 0 {n_daily_zero:,}, regular-hours > "
          f"{MISMATCH_TOL}x daily {n_mismatch:,}")
    print(f"denominator   the day's FULL daily volume ({DAILY.name}); curve[389] = {curve[-1]:.4f} = the mean share of a "
          f"day's full volume done in regular hours")
    print("population    the consolidation-breakout backtest's (#702 pre-v2) stored candidate ticker-days, SIP minutes")
    print("method        mean over ticker-days of (regular-hours volume through the end of minute m / the day's FULL "
          "daily volume); monotone; not forced to 1.0")
    print()
    print("minute  ET     mean_share  median_share")
    for m in (0, 4, 9, 14, 29, 59, 89, 119, 179, 239, 299, 329, 359, 379, 389):
        hh, mm = divmod(570 + m, 60)
        print(f"{m:>6}  {hh:02d}:{mm:02d}  {curve[m]:.4f}      {med[m]:.4f}")
    print()
    print("per-year stability (mean share by the end of 09:34 / 09:59 / 11:59 / 14:59):")
    for y, rows in sorted(per_year.items()):
        a = np.vstack(rows).mean(axis=0)
        print(f"  {y}  n={len(rows):>6,}  " + "  ".join(f"{x:.4f}" for x in a))

    vals = ",\n".join("    " + ", ".join(f"{x:.6f}" for x in curve[k:k + 10]) for k in range(0, N_MIN, 10))
    OUT_MODULE.write_text(f'''"""GENERATED by scripts/probes/_breakout_v1_phase2/build_volume_curve.py — do not hand-edit; re-run the builder.

Breakout v1 F1 (his ruling 2026-10-29): the share of a day's FULL daily volume (the unit of the list's 50-day average,
`mi_daily_closes`) normally done in regular hours by the END of each minute, minute 0 = 09:30 ET .. minute 389 = 15:59 ET.
ONE curve for every stock (pooled), not a per-stock curve (a per-stock curve is a later refinement).

Source: the stored SIP minute bars of the consolidation-breakout backtest (#702 pre-v2,
apollo_data/cb702_pre_v2/minutes): {n_td:,} ticker-days ({len(tickers):,} tickers), {n_days_used} full sessions
{first} .. {last} ({n_days_early} early-close sessions dropped); daily volumes from
apollo_data/cb702_pre_v2/daily_closes_all.csv.gz. Method: the mean over ticker-days of cumulative regular-hours volume /
the day's FULL daily volume (each ticker-day weighs the same); monotone; NOT forced to 1.0 — CUM_SHARE[389] = {curve[-1]:.4f}
is the share of a day's full volume done in regular hours (the rest is extended hours + the 16:00 closing cross).
"""
from __future__ import annotations

SOURCE = "apollo_data/cb702_pre_v2/minutes (#702 pre-v2 backtest candidate ticker-days, SIP)"
DATE_RANGE = ("{first}", "{last}")
N_TICKER_DAYS = {n_td}
N_TICKERS = {len(tickers)}
N_SESSIONS = {n_days_used}
METHOD = ("mean over ticker-days of cumulative regular-hours volume / the day's FULL daily volume; full sessions only; "
          "monotone; not forced to 1.0")
DENOMINATOR = "full daily volume (Polygon grouped daily, the unit of mi_daily_closes / the list's vol_bar)"

CUM_SHARE: tuple[float, ...] = (
{vals},
)

assert len(CUM_SHARE) == 390
''')
    print(f"\nwrote {OUT_MODULE.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
