#!/usr/bin/env python3
"""Stage 0 of the signed-off breakout rebuild (docs/analysis/cb_rebuild_from_qm_trades_2026-11-02.md, "Open before the
Saturday build" 1-3): three free checks on local data, read-only, nothing dated 2025+ read, no returns anywhere.
Runs s0_features.py (capture once: skipped when its outputs exist), s0_check1.py, s0_check23.py; writes s0.txt."""
import os, subprocess, sys
HERE = os.path.dirname(os.path.abspath(__file__))
if not (os.path.exists(f"{HERE}/s0_rowfeat.parquet") and os.path.exists(f"{HERE}/s0_buyfacts.tsv")):
    subprocess.run([sys.executable, f"{HERE}/s0_features.py"], check=True, cwd=HERE)
for s in ("s0_check1.py", "s0_check23.py"):
    subprocess.run([sys.executable, f"{HERE}/{s}"], check=True, cwd=HERE, stdout=subprocess.DEVNULL)
head = ("STAGE 0 — three free checks before the Saturday build (Qullamaggie's 269 dated breakout buys are the scorecard;\n"
        "scores = his buys caught and names a day; no returns read; nothing dated 2025-01-01 or later read)\n"
        "files: s0_lib.py s0_features.py s0_check1.py s0_check23.py | s0_rowfeat.parquet s0_buyfacts.tsv s0_check1_buys.tsv s0_check3_ranks.tsv\n")
body = "".join(open(f"{HERE}/{t}").read() for t in ("s0_check23.txt", "s0_check1.txt"))
open(f"{HERE}/s0.txt", "w").write(head + body)
print(open(f"{HERE}/s0.txt").read())
