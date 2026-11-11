#!/usr/bin/env python3
"""#717 step 2c: every widened High-confidence buy the CURRENT list misses, on one outcome-blind sheet (charts end on `hi`),
plus the two-change combination. Ordered by date, lettered A..; the key carries the gates that fail on the best night.

    python3 scripts/probes/_717_qm_confidence_1111/05_missed_high_sheet.py > scripts/probes/_717_qm_confidence_1111/05_missed_high_sheet.out"""
import contextlib
import importlib
import io
import sys

sys.path.insert(0, ".")
sys.path.insert(0, "scripts/probes/_717_qm_confidence_1111")
with contextlib.redirect_stdout(io.StringIO()):
    m = importlib.import_module("03_high_vs_list")
import sheet as S  # noqa: E402

HERE = "scripts/probes/_717_qm_confidence_1111/"
miss = [x for x in m.rows if x["b"]["set"] == "widened" and x["r"]["tier"] == "High" and not any(n["ok"] for n in x["nights"])]
miss.sort(key=lambda x: (x["b"]["hi"], x["b"]["ticker"], x["b"]["eid"]))
fails = {id(x["b"]): ",".join(min(x["nights"], key=lambda n: len(n["failed"]))["failed"]) for x in miss}
S.render([(x["b"], x["r"]) for x in miss], HERE + "sheet_high_missed.png",
         f"The {len(miss)} High-confidence Qullamaggie buys (widened set) the current breakout list misses — ~8 months of daily bars ending on the "
         "last day of the buy window (shaded); dashed = the rated buy point. For each: a real breakout? yes / no",
         "#717: every widened High buy the current list misses, by date.\nletter|ticker|lo|hi|buy_point|range_len|gates failing on the best night",
         lambda b, r: f"{b['ticker']}|{b['lo']}|{b['hi']}|{r['level']:.4g}|{r['len']}|{fails[id(b)]}", bars_shown=160)
print(open(HERE + "sheet_high_missed.png.key_do_not_show.txt").read())
print("=== the two changes together (50-day X under, prior move >= Y) ===")
m.line("TODAY", m.BASE)
for s50 in (-0.02, -0.03, -0.05):
    for pr in (0.25, 0.20, 0.15):
        m.line(f"50-day {s50:+.0%} + prior move >= {pr:.0%}", dict(m.BASE, s50=s50, prior=pr))
