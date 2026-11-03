"""Load ../build/rank_v2.py's loaders, populations, day pools and scoring WITHOUT running its report.

rank_v2.py is a script (importing it would re-run the 11-03 report and rewrite build/rank_v2.txt and
build/features.tsv). This executes, verbatim from its own source: every top-level statement before the
report banner (data load, features(), auc/boot_ci/_pct_rank, A/B/C, context, rank_pair, run, fmt), plus four
report-section functions reused as-is (pool_line, report_bars, S_ranked_c, verdict_of). Nothing is copied
by hand, so the populations, pools and bars are the 11-03 run's own code.
"""
from __future__ import annotations

import ast
from pathlib import Path

SRC = Path("/Users/alvinfung/apollo_the_wise/scripts/probes/_ep_rank_v2_1103/build/rank_v2.py")
KEEP_AFTER = {"pool_line", "report_bars", "S_ranked_c", "verdict_of"}


def load() -> dict:
    text = SRC.read_text(encoding="utf-8")
    banner = next(i for i, ln in enumerate(text.splitlines(), 1) if ln.startswith("# ════"))
    tree = ast.parse(text)
    body = [n for n in tree.body if n.lineno < banner or
            (isinstance(n, ast.FunctionDef) and n.name in KEEP_AFTER)]
    got = {n.name for n in body if isinstance(n, ast.FunctionDef)}
    assert KEEP_AFTER <= got, KEEP_AFTER - got
    ns = {"__file__": str(SRC), "__name__": "rank_v2_defs", "__doc__": ast.get_docstring(tree)}
    exec(compile(ast.Module(body=body, type_ignores=[]), str(SRC), "exec"), ns)
    return ns
