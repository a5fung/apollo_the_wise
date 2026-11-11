#!/usr/bin/env python3
"""#717: write tests/fixtures/qm_breakout_scorecard/high_tier.tsv — the 84 high-confidence Qullamaggie buys (the rating's
High tier), each with its rated break day, buy point (split-adjusted, as the fixture bars), and the two inputs the gates
need from outside the bars at the night D before it: rs_best and the raw close (blank where the night was not in the
2026-11-02 cross-section — the strength rank is then not measurable and the test passes it). Reads ratings.tsv and the era-A
parquet (nights to 2022-03-31); nothing from 2025-26.

    python3 scripts/probes/_717_qm_confidence_1111/12_build_high_fixture.py"""
import csv
import gzip
from collections import defaultdict

import pandas as pd

F = pd.read_parquet("/Users/alvinfung/apollo_data/qm_breakouts_1102/features_eraA.parquet", columns=["scan_date", "ticker", "rs_best", "raw_close"])
assert str(F.scan_date.max())[:10] <= "2022-03-31"
RS = {(t, str(d)[:10]): (r, rc) for t, d, r, rc in zip(F.ticker, F.scan_date, F.rs_best, F.raw_close)}
FX = "tests/fixtures/qm_breakout_scorecard/"
dated = {r["eid"]: r for r in csv.DictReader(open(FX + "buys.tsv"), delimiter="\t")}
dates = defaultdict(list)
for name, key in (("bars.psv.gz", "dated"), ("bars_undated_widened.psv.gz", "widened")):
    with gzip.open(FX + name, "rt") as f:
        for r in csv.DictReader(f, delimiter="|"):
            dates[(key, r["eid"])].append(r["date"])
rows = [r for r in csv.DictReader(open("scripts/probes/_717_qm_confidence_1111/ratings.tsv"), delimiter="\t") if r["tier"] == "High"]
rows.sort(key=lambda r: (r["set"], r["day_cleared"], r["ticker"], int(r["eid"])))
n_unranked = 0
with open(FX + "high_tier.tsv", "w") as f:
    f.write("set\teid\tsym\tticker\tD\tE\tbuy_point\trange_len\trs_best\traw_close_D\n")
    for r in rows:
        ds = sorted(dates[(r["set"], r["eid"])])
        D = ds[ds.index(r["day_cleared"]) - 1]
        if r["set"] == "dated":
            assert D == dated[r["eid"]]["D"]
            rs, raw = dated[r["eid"]]["rs_best"], dated[r["eid"]]["raw_close_D"]
        else:
            v = RS.get((r["ticker"], D))
            n_unranked += v is None
            rs, raw = ("", "") if v is None else (repr(float(v[0])), repr(float(v[1])))
        f.write(f"{r['set']}\t{r['eid']}\t{r['sym']}\t{r['ticker']}\t{D}\t{r['day_cleared']}\t{r['buy_point_split_adjusted']}\t{r['range_len']}\t{rs}\t{raw}\n")
print(len(rows), "rows; unranked widened nights:", n_unranked)
