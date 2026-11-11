"""Build tests/fixtures/breakout_list_grades_bars.psv.gz: the daily bars (<= the list night, up to 504 sessions) of the
29 names he graded in tests/fixtures/breakout_list_grades.py, copied from the read-only prod pulls already on disk
(mi_daily_closes; the SQL sits beside each .out). COPIES bars only — computes no gate, prints no score.

Inputs (psql output, blocks headed "== TICKER YYYY-MM-DD", rows trade_date|open|high|low|close|volume):
    scripts/probes/_717_grading_sheet_1107/q2_bars.out          (Fri 11-06 sheet, 12 names)
    scripts/probes/_717_grading_sheet_1109/q2_bars.out          (Thu 11-05 sheet, 12 names)
    <argv[1]>  the 11-10 pull bars5.out (the five paper buys, list night 11-09) — untracked in the main checkout at
               scripts/probes/_717_723_verify_1110/bars5.out; pass its path.
Run from the repo root:
    python3 scripts/probes/_717_shape_gates_1111/01_build_grades_bars_fixture.py <path to bars5.out>
"""
import gzip
import sys
from pathlib import Path

sys.path.insert(0, ".")
from tests.fixtures.breakout_list_grades import BREAKOUT_LIST_GRADES  # noqa: E402

srcs = ["scripts/probes/_717_grading_sheet_1107/q2_bars.out", "scripts/probes/_717_grading_sheet_1109/q2_bars.out", sys.argv[1]]
blocks, cur = {}, None
for p in srcs:
    for line in open(p):
        line = line.strip()
        if line.startswith("== "):
            cur = tuple(line[3:].split())
            blocks[cur] = []
        elif cur and line[:2] == "20" and line.count("|") == 5:
            blocks[cur].append(line)
out = Path("tests/fixtures/breakout_list_grades_bars.psv.gz")
n = 0
with gzip.GzipFile(out, "wb", mtime=0) as gz:
    gz.write(b"ticker|list_date|date|o|h|l|c|v\n")
    for g in BREAKOUT_LIST_GRADES:
        rows = blocks[(g.ticker, g.list_date)]
        assert rows and rows[-1].split("|")[0] == g.list_date, (g.ticker, g.list_date, rows[-1] if rows else None)
        for r in rows:
            gz.write(f"{g.ticker}|{g.list_date}|{r}\n".encode())
            n += 1
print(f"{out}: {len(BREAKOUT_LIST_GRADES)} names, {n} bars")
