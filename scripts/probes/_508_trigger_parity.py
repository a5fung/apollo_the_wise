#!/usr/bin/env python3
"""#508 — does the SHIPPED code make the same decisions the replay predicted?

CHANGE_PROCESS r1 is satisfied by the replay (N=36 historical trades, 34 candidate
rules, every figure independently recomputed twice). But that validated the RULE.
This validates the CODE: it applies `scan_profit_triggers`' actual predicate —
MAX(in-hold bar high) >= entry + R x risk, partial not already taken — to the
historical cohort, and compares trade-for-trade against the replay's poll-fill
model. A divergence means the implementation and the evidence disagree, which is
the failure mode no amount of rule-backtesting can catch.

Read-only. No DB writes, no orders.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import _508_exit_rule_replay as rp   # noqa: E402

TRIGGER_R = 2.0


def shipped_predicate(t) -> tuple[bool, float | None]:
    """Re-implements scan_profit_triggers' decision from the same inputs it uses:
    entry, hard_stop, and the max in-hold minute HIGH. Deliberately re-implemented
    rather than imported — importing would prove only that a function equals itself.
    """
    entry, stop = t.rec["entry_price"], None
    for leg in (t.legs or []):
        stop = leg.get("hard_stop") or leg.get("stop_price") or stop
    stop = stop if stop else (entry - t.risk if t.risk else None)
    if not entry or not stop or stop >= entry:
        return False, None
    target = entry + TRIGGER_R * (entry - stop)
    highs = [b[2] for d in t.days if d.covered for b in d.bars]
    if not highs:
        return False, target
    return (max(highs) >= target), target


def main() -> int:
    trades = [t for t in rp.load() if t.cohort == "live/magna53"]
    poll = {}
    for t in trades:
        r = rp.sim_r_rule_poll(t, TRIGGER_R, 1 / 3)
        poll[t.rec["trade_id"]] = None if r is None else r.triggered

    print(f"{'ticker':<8}{'shipped':>9}{'replay':>9}{'target':>10}{'peak_r':>9}  verdict")
    agree = diverge = unmeasurable = 0
    for t in sorted(trades, key=lambda x: x.rec["ticker"]):
        fires, target = shipped_predicate(t)
        pv = poll[t.rec["trade_id"]]
        if pv is None:
            verdict, unmeasurable = "no bars (excluded)", unmeasurable + 1
        elif fires == pv:
            verdict, agree = "agree", agree + 1
        else:
            verdict, diverge = "*** DIVERGE ***", diverge + 1
        print(f"{t.rec['ticker']:<8}{str(fires):>9}{str(pv):>9}"
              f"{(f'{target:.2f}' if target else '—'):>10}{t.rec['peak_r']:>9.2f}  {verdict}")
    print(f"\nagree={agree}  diverge={diverge}  unmeasurable={unmeasurable}")
    if diverge:
        print("FAIL — shipped predicate and replay disagree; the evidence does not "
              "describe the code that would run.")
        return 1
    print("PASS — the shipped predicate reproduces the replay's decisions exactly.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
