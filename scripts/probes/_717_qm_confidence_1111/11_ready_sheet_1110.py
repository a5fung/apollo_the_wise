#!/usr/bin/env python3
"""#717: list night 2026-11-10 — the names with a qualifying range ready to trigger, as an outcome-blind sheet
(bought-names style: the 12 highest by tonight's list rank among the ready set, shuffled; charts end on the list night;
dashed = the range high, drawn from the range's start). Also the ready count at each X.

    python3 scripts/probes/_717_qm_confidence_1111/11_ready_sheet_1110.py > scripts/probes/_717_qm_confidence_1111/11_ready_sheet_1110.out"""
import random
import sys
from collections import defaultdict
from datetime import date

import numpy as np

sys.path.insert(0, "scripts/probes/_717_qm_confidence_1111")
import range_break as rb  # noqa: E402
import sheet as S  # noqa: E402

HERE = "scripts/probes/_717_qm_confidence_1111/"
X = 3.0                                                       # the X the 84 forced (10_initial_rules.out)
lst, bars, sec = [], defaultdict(list), None
for line in open("scripts/probes/_717_shape_gates_1111/10_sheet_latest_list.out"):
    line = line.strip()
    if line.startswith("== "):
        sec = line[3:]
    elif sec == "LIST" and line[:2] == "20":
        lst.append(line.split("|"))
    elif sec == "BARS" and line.count("|") == 6 and line.split("|")[1][:2] == "20":
        t, d, o, h, l, c, v = line.split("|")
        bars[t].append((date.fromisoformat(d), float(o), float(h), float(l), float(c), float(v)))
items, counts = [], {x: 0 for x in (1.0, 1.5, 2.0, 3.0)}
for d, t, rk, *_ in lst:
    r = bars[t]
    b = dict(ticker=t, rank=int(rk), dates=[x[0] for x in r], win=[len(r) - 1], **{k: np.array([x[i] for x in r]) for i, k in enumerate("ohlcv", 1)})
    D = len(r) - 1
    lv = rb.range_levels(b["h"], b["l"], D)
    rng = rb.avg_range(b["h"], b["l"], D)
    for x in counts:
        counts[x] += rb.ready(lv, b["c"][D], rng, x) is not None
    k = rb.ready(lv, b["c"][D], rng, X)
    if k:
        items.append((b, dict(level=k["level"], p=k["start"], len=k["len"], dist=(k["level"] - b["c"][D]) / rng)))
print(f"list night {lst[0][0]}: {len(lst)} names; ready to trigger at X = " + ", ".join(f"{x}: {n}" for x, n in counts.items()))
items.sort(key=lambda x: x[0]["rank"])
top = items[:12]
random.Random(1111).shuffle(top)
S.render(top, HERE + "ready_sheet_1110.png",
         f"Breakout list, {lst[0][0]} — 12 names with a range ready to break (the highest-ranked of {len(items)}); ~8 months of daily bars ending on "
         "the list night; dashed = the range high (the buy point). For each: a real breakout setup? good / ok / no",
         f"#717 ready-to-trigger sheet, list night {lst[0][0]}: the 12 highest by list rank among the {len(items)} ready at X = {X}, shuffled (seed 1111).\n"
         "letter|ticker|list_rank|range_high|range_len|distance_above_close_in_daily_ranges",
         lambda b, r: f"{b['ticker']}|{b['rank']}|{r['level']:.4g}|{r['len']}|{r['dist']:.2f}", bars_shown=160)
print(open(HERE + "ready_sheet_1110.png.key_do_not_show.txt").read())
