#!/usr/bin/env python3
"""#717 context checks — how many must-keep rows carry a BLANK measure (a blank passes every check). Prints only."""
import sys, io, contextlib, os
sys.argv = [sys.argv[0]]
with contextlib.redirect_stdout(io.StringIO()):
    exec(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "02_score.py")).read())
for nm, d in (("the 56", hi), ("big-winner fired sessions", BIGF), ("fired scorecard sessions", sc[sc.fired == 1]), ("era-A fires", f)):
    print(f"{nm}: {len(d)} rows; blank " + ", ".join(f"{c} {int(d[c].isna().sum())}" for c in ("ret126", "sma200_ratio", "s50_chg20", "tr5_base", "wide10")))
