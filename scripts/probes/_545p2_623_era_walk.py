#!/usr/bin/env python3
"""#545 Phase 2 step 4 -- the scan-level skip buckets, era-corrected.

The design doc's own text says "read straight out of _623_replay_out.tsv with a group-by" --
literally done below (era_c, RETIRED 2026-09-06). THE ONE CORRECTION this card carries
forward (Phase 1's own 2026-09-22 finding: era_c is NOT live) means that read alone would
repeat Phase 1's mistake, so this script ALSO re-walks the SAME #623 population (3,458
scan-log ticker-days, no new fetch -- _623_bars.psv.gz / _623_have_minute_bars_out.txt /
_623_daily_bars_out.txt are all already in the repo) under era_d (LIVE since 2026-09-06) and
under a 0.5xADR stop on era_d's own harvest shape -- the two cells the pass bar in §7 needs
('7 per 57 under 0.5xADR' is an era_c number; this reproduces it against the rule we run).

Reuses _623_replay.py's OWN loaders unmodified (load_population / load_minutes_from_psv /
load_minutes_from_gz / load_daily) -- no second definition of the population. Writes to NEW
files; scripts/probes/_623_replay_out.tsv is never touched.
"""
from __future__ import annotations

import re
import statistics as st
import sys
from collections import Counter, defaultdict
from dataclasses import replace
from datetime import date, time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "scripts"))

import ep_replay as ep  # noqa: E402
from ep_replay import RULESETS, atr14_abs, walk_campaign  # noqa: E402
import importlib.util as _ilu  # noqa: E402

_spec = _ilu.spec_from_file_location("_623r", HERE / "_623_replay.py")
r623 = _ilu.module_from_spec(_spec)
# _623_replay.py runs its own main() at import under `if __name__ == "__main__"`, which is
# guarded -- importing it as a module only defines functions/constants, does not re-run
# the 2026-09-04 replay or touch _623_replay_out.tsv.
_spec.loader.exec_module(r623)

OUT_TSV = HERE / "_545p2_623_era_walk.tsv"
NEAR_ZERO_PCT = 0.5   # the 13-row near-zero-stop exclusion P-623's own doc applies


def bucket_of(reason: str | None) -> str:
    r = reason or ""
    if r.startswith("outside top-20"):
        return "outside_top20"
    if re.match(r"^score \d+ < 50", r):
        return "score_below_50"
    if "filter:session_rvol_too_low" in r:
        return "session_rvol_low"
    if "filter:mcap_too_small" in r:
        return "mcap_low"
    if "filter:adv_too_low" in r:
        return "adv_low"
    return "other"


def _p90(xs):
    xs = sorted(xs)
    return xs[max(0, int(round(0.9 * (len(xs) - 1))))] if xs else None


def stats(xs):
    xs = sorted(xs)
    n = len(xs)
    if n == 0:
        return {"n": 0, "sum": 0.0}
    return {"n": n, "sum": sum(xs), "med": st.median(xs), "p90": _p90(xs),
            "ge3": sum(x >= 3 for x in xs), "ge5": sum(x >= 5 for x in xs)}


def fmt(d):
    if d["n"] == 0:
        return "n=0"
    return (f"n={d['n']:4d} >=3R={d['ge3']:3d} >=5R={d['ge5']:2d} p90={d['p90']:+5.2f} "
            f"med={d['med']:+5.2f} sum={d['sum']:+8.1f}")


def main():
    print("=" * 90)
    print("PART 1 -- literal group-by on the EXISTING _623_replay_out.tsv (era_c, RETIRED "
          "2026-09-06). NOT re-derived, NOT re-fetched -- read straight, as the design doc "
          "text says. LABEL: RETIRED.")
    print("=" * 90)
    import csv
    with open(REPO / "scripts" / "probes" / "_623_replay_out.tsv") as fh:
        rows_c = list(csv.DictReader(fh, delimiter="\t"))
    print(f"rows: {len(rows_c)}")
    by_bucket_c = defaultdict(list)
    admitted_c = []
    for r in rows_c:
        if r["status"] != "settled" or not r["realized_r"]:
            continue
        rr = float(r["realized_r"])
        entry = float(r["entry_px"]) if r["entry_px"] else None
        stop = float(r["stop"]) if r["stop"] else None
        if entry and stop is not None and abs(entry - stop) / entry * 100 < NEAR_ZERO_PCT:
            continue  # the 13-row near-zero-stop exclusion (P-623's own doc)
        b = bucket_of(r["nearest_filter_reason"])
        by_bucket_c[b].append(rr)
        if r["ever_scored"] == "t":
            admitted_c.append(rr)
    print(f"admitted (ever_scored) reference, era_c: {fmt(stats(admitted_c))}  "
          f">=3R per 100 settled={stats(admitted_c)['ge3']/max(1,len(admitted_c))*100:5.1f}")
    for b in ("outside_top20", "score_below_50", "session_rvol_low", "mcap_low", "adv_low"):
        xs = by_bucket_c[b]
        rate = stats(xs)["ge3"] / max(1, len(xs)) * 100
        print(f"  {b:18s} {fmt(stats(xs))}   >=3R per 100 settled={rate:5.1f}")
    print(f"  other/unclassified rows: {len(by_bucket_c['other'])}")

    print("\n" + "=" * 90)
    print("PART 2 -- THE SAME #623 POPULATION, re-walked under era_d (LIVE since 2026-09-06) "
          "and 0.5xADR-on-era_d. No new fetch: _623_bars.psv.gz / _623_have_minute_bars_out.txt "
          "/ _623_daily_bars_out.txt (already in the repo) reused via _623_replay.py's own "
          "loaders, unmodified.")
    print("=" * 90)
    pop = r623.load_population(HERE / "_623_population_raw.psv")
    minutes: dict = defaultdict(list)
    n1 = r623.load_minutes_from_psv(HERE / "_623_have_minute_bars_out.txt", minutes)
    n2 = r623.load_minutes_from_gz(HERE / "_623_bars.psv.gz", minutes)
    for bars in minutes.values():
        bars.sort(key=lambda b: b["m"])
    daily = r623.load_daily(HERE / "_623_daily_bars_out.txt")
    print(f"loaded: {len(pop)} population rows, minute bars {n1}+{n2}={n1+n2}, "
          f"daily tickers {len(daily)}")

    LAST_SETTLED = date(2026, 9, 21)   # this script's own horizon (today, 09-22, excluded)
    ep.LAST_SETTLED = LAST_SETTLED

    cells = {
        "era_d_ladder": RULESETS["era_d"],
        "adr_0.5_ladder": replace(RULESETS["era_d"], name="adr_0.5_ladder",
                                  stop_mode="adr_k", adr_k=0.5),
    }

    tsv_rows = []
    for cname, rs in cells.items():
        print(f"\n----- cell: {cname} -----")
        results = []
        for r in pop:
            t, d = r["ticker"], date.fromisoformat(r["scan_date"])
            if d >= date(2026, 9, 22):
                continue  # live/incomplete session
            bars0 = minutes.get((t, d), [])
            if not bars0:
                continue
            daily_open = (daily.get(t, {}).get(d) or {}).get("o")
            orb930 = next((b for b in bars0 if b["m"].time() == time(9, 30)), None)
            if orb930 is not None and daily_open:
                div = abs(daily_open / orb930["o"] - 1)
                if div > 0.05:
                    continue  # split-artifact guard, same as _623_replay.py
            atr_14 = atr14_abs(daily.get(t, {}), d)
            res = walk_campaign(ticker=t, alert_date=d, rs=rs, minutes=minutes, daily=daily,
                                submit=time(9, 31), atr_14=atr_14)
            res["nearest_filter_reason"] = r["nearest_filter_reason"]
            res["ever_scored"] = r["ever_scored"]
            results.append(res)
            tsv_rows.append({**res, "cell": cname})

        settled = [r for r in results if r["status"] == "settled" and r["realized_r"] is not None]
        near_zero = 0
        clean = []
        for r in settled:
            if r["entry_px"] and r["stop"] is not None and \
               abs(r["entry_px"] - r["stop"]) / r["entry_px"] * 100 < NEAR_ZERO_PCT:
                near_zero += 1
                continue
            clean.append(r)
        print(f"  total rows walked: {len(results)}  settled: {len(settled)}  "
              f"near-zero-stop excluded: {near_zero}  clean settled: {len(clean)}")
        by_bucket = defaultdict(list)
        admitted = []
        for r in clean:
            b = bucket_of(r["nearest_filter_reason"])
            by_bucket[b].append(r["realized_r"])
            if r["ever_scored"] == "t":
                admitted.append(r["realized_r"])
        rate_admit = stats(admitted)["ge3"] / max(1, len(admitted)) * 100
        print(f"  admitted (ever_scored) reference: {fmt(stats(admitted))}  "
              f">=3R per 100 settled={rate_admit:5.1f}")
        for b in ("outside_top20", "score_below_50", "session_rvol_low", "mcap_low", "adv_low"):
            xs = by_bucket[b]
            rate = stats(xs)["ge3"] / max(1, len(xs)) * 100
            beats = "beats" if rate > rate_admit else "does NOT beat"
            print(f"    {b:18s} {fmt(stats(xs))}   >=3R per 100 settled={rate:5.1f}  "
                  f"-> {beats} the admitted reference ({rate_admit:.1f})")
        print(f"    other/unclassified: {len(by_bucket['other'])} rows")

    cols = ["cell", "ticker", "alert_date", "status", "reason", "entered", "entry_px", "stop",
            "realized_r", "mark_r", "nearest_filter_reason", "ever_scored"]
    with open(OUT_TSV, "w") as fh:
        fh.write("|".join(cols) + "\n")
        for r in tsv_rows:
            fh.write("|".join("" if r.get(c) is None else str(r.get(c)) for c in cols) + "\n")
    print(f"\nwritten: {OUT_TSV} ({len(tsv_rows)} rows)")


if __name__ == "__main__":
    main()
