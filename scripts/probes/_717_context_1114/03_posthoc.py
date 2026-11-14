#!/usr/bin/env python3
"""#717 context checks — POST-HOC, NOT PREREGISTERED (labelled; decides nothing, draws no sheet). After 02_score.out:
the registered A definitions (50-day fall read over 20 sessions) remove one of his ok charts (WDC 2019-02-15, whose 50-day
had turned up over the last 5 / 10 sessions); the plateau points at 5 / 10 sessions do not. This prints the stack a
10-session reading would give (10 sessions = the reading 1d itself already uses), and which Qullamaggie buys each costs.
The 10-session choice was seen against a grade -> in-sample; a fresh sheet is the only honest test.

    python3 scripts/probes/_717_context_1114/03_posthoc.py > scripts/probes/_717_context_1114/03_posthoc.out
"""
import sys, io, contextlib
sys.argv = [sys.argv[0]]
buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    exec(open(__import__("os").path.join(__import__("os").path.dirname(__import__("os").path.abspath(__file__)), "02_score.py")).read())
print(HDR)
A2_10, _, _ = sized("ret126", "min", FALL(10), 0.0)
A1_10, _, _ = sized("ret126", "min", A1F(10), 0.0)
B1 = CHECKS["B1 last-5 bars vs the base's earlier"]
DROPS.clear()
score("1d", ONE_D)
score("1d + A2 (10-session fall)", lambda d: ONE_D(d) & A2_10(d))
score("1d + A1 (10-session fall)", lambda d: ONE_D(d) & A1_10(d))
score("1d + A2 (10-session fall) + B1", lambda d: ONE_D(d) & A2_10(d) & B1(d))
score("1d + A2 (20, registered) + B1", lambda d: ONE_D(d) & CHECKS["A2 falling 50d + 126d return"](d) & B1(d))
x = pd.DataFrame(DROPS, columns=["check", "set", "eid", "ticker", "E", "tier", "big"])
for c in ("1d + A2 (10-session fall)", "1d + A2 (10-session fall) + B1"):
    y = x[(x.check == c) & ~x.eid.isin(x[x.check == "1d"].eid)]
    print(f"\n{c}: Qullamaggie fired buys lost beyond 1d = {len(y)}: " + ", ".join(f"{r.ticker} {r.E} ({r.tier})" for r in y.itertuples()))
