"""#712 DoD: replay GKOS's missed 2026-10-29 MAGNA53 EP trade over 20 sessions from stored DAILY bars.
Run from the repo root:  python3 scripts/probes/_gkos_1029/replay_20d.py > scripts/probes/_gkos_1029/replay_20d.out
Reads q7_bars.out (no DB). Uses the live #482 walker (walk_arm) + the live pure exit functions
(depth_stop_price, apply_daily_exit_step) -- nothing re-implemented. Day 0 has no minute bars here, so it is
SYNTHESISED from the daily bar (stated assumption, two variants below)."""
import os, sys
from datetime import date, datetime, timedelta
sys.path.insert(0, os.getcwd())
from agents.market_intelligence import live_fill_counterfactuals as L, rule_eras as R
from agents.market_intelligence.broker.exit_logic import (apply_daily_exit_step, depth_stop_price,
                                                          seed_exit_state, adr20_pct_from_bars)

HERE = os.path.dirname(os.path.abspath(__file__))
ALERT = date(2026, 10, 29)
ENTRY, ORB_LOW = 214.92, 207.41
HARD_STOP = 199.90
R_ORB = round(ENTRY - ORB_LOW, 2)          # 7.51 (the ORB-R frame: target / breakeven are measured in this)
RISK = round(ENTRY - HARD_STOP, 2)         # 15.02 (= 2 ORB-R, the per-share risk to the placed stop)

rows = []
for ln in open(os.path.join(HERE, "q7_bars.out")):
    p = ln.strip().split("|")
    if len(p) == 6 and p[0][:2] == "20":
        d = date.fromisoformat(p[0])
        rows.append(dict(trade_date=d, open_price=float(p[1]), high_price=float(p[2]), low_price=float(p[3]),
                         close=float(p[4]), o=float(p[1]), h=float(p[2]), l=float(p[3]), c=float(p[4])))
pre = [r for r in rows if r["trade_date"] < ALERT]
day0 = next(r for r in rows if r["trade_date"] == ALERT)
post = [r for r in rows if r["trade_date"] > ALERT][:20]
assert len(post) == 20 and post[-1]["trade_date"] == date(2026, 11, 27), post[-1]
assert day0["low_price"] > HARD_STOP and day0["high_price"] >= ENTRY and ORB_LOW == day0["low_price"]

rules = R.exit_rules_as_of(ALERT, "magna53", "depth")
target, kw = L.stack_walk_inputs(rules, ENTRY, ORB_LOW, pre)
prior_closes = [r["close"] for r in pre if r["trade_date"] >= ALERT - timedelta(days=L.PRIOR_CLOSES_CAL_DAYS)]
adr = kw["depth_adr20_pct"]
sessions = [(r["trade_date"], dict(o=r["o"], h=r["h"], l=r["l"], c=r["c"])) for r in post]
be_trig = ENTRY + rules["breakeven_at_r"] * R_ORB

print(f"GKOS 2026-10-29 missed MAGNA53 EP -- 20-session replay, DAILY bars, depth exit (stack {rules['exit_rule']}, era {R.exit_era_label(ALERT,'magna53','depth')})")
print(f"entry {ENTRY} (1-min ORB high) | ORB low {ORB_LOW} | R_orb = {R_ORB} | hard stop {HARD_STOP} | risk to stop = {RISK} (= 2 R_orb)")
print(f"+8R partial target {target:.2f} (max high over the 20 sessions {max(r['high_price'] for r in post):.2f}) | breakeven arm +{rules['breakeven_at_r']}R = {be_trig:.2f}")
print(f"ADR20 (fraction, live fn) {adr:.5f} | prior closes used {len(prior_closes)} | trail_arm_from {L.TRAIL_ARM_LIVE_FROM}")
print(f"day 0: O {day0['o']} H {day0['h']} L {day0['l']} C {day0['c']}  (high >= breakeven arm: {day0['h'] >= be_trig})")


def day0_bars(variant):
    # fill bar at the ORB high; then the run to the day's high. 'armed' = price held above entry on the way up
    # (breakeven arms on day 0); 'unarmed' = no breakeven on day 0 (hard stop only) -- the conservative bound.
    bars = [dict(m="09:31", o=ENTRY, h=ENTRY, l=ENTRY, c=ENTRY),
            dict(m="09:32", o=ENTRY, h=day0["h"], l=ENTRY + 0.01, c=day0["c"])]
    return bars


def run(be_on_day0):
    kws = dict(kw)
    if not be_on_day0:
        kws["breakeven_at_r"] = None
    res = L.walk_arm(entry=ENTRY, stop=HARD_STOP, target=target, day0_bars=day0_bars(be_on_day0), fill_idx=0,
                     sessions=sessions, prior_closes=prior_closes, harvest="live_ladder", fill_day=ALERT,
                     trail_arm_from=L.TRAIL_ARM_LIVE_FROM, entry_day_close=day0["c"], **kws)
    return res


def trace(be_on_day0):
    """Day-by-day: the live pure functions, same loop shape as walk_arm."""
    state = seed_exit_state(alert_date=ALERT, entry_price=ENTRY, hard_stop=HARD_STOP, remaining_shares=1.0,
                            partial_taken=False, breakeven_active=False, exits=[])
    resting = max(HARD_STOP, ENTRY) if be_on_day0 else HARD_STOP
    print(f"{'sess':>4} {'date':10} {'open':>7} {'high':>7} {'low':>7} {'close':>7} {'line/eff':>8} {'rest.stop':>9}  event")
    print(f"{0:>4} {str(ALERT):10} {day0['o']:7.2f} {day0['h']:7.2f} {day0['l']:7.2f} {day0['c']:7.2f} {'-':>8} {resting:9.2f}  entry {ENTRY}; breakeven {'armed (high >= %.2f)' % be_trig if be_on_day0 else 'NOT armed (variant)'}")
    last = ENTRY
    for i, (d, b) in enumerate(sessions, 1):
        last = b["c"]
        if be_on_day0 and b["h"] >= be_trig:
            resting = max(resting, ENTRY)
        state["hard_stop"] = resting
        step = apply_daily_exit_step(state, dict(l=b["l"], c=b["c"]), d, integer_partial_shares=False,
                                     skip_partial_decision=True, prior_closes=list(prior_closes),
                                     trail_arm_on_close_above=True, entry_day_close=day0["c"])
        state.update(remaining_shares=step.new_remaining, partial_taken=step.new_partial_taken,
                     breakeven_active=step.new_breakeven_active, exits=step.new_exits,
                     running_closes=step.new_running_closes)
        ev = ""
        if step.closed:
            if step.close_reason == "sma_trail_stop":
                nd, nb = (sessions[i] if i < len(sessions) else (None, None))
                ev = f"CLOSE BELOW LINE ({step.close_reason}) -> sale at next open {nd} {nb['o'] if nb else 'n/a'}"
            else:
                ev = f"{step.close_reason} at {step.close_price}"
            print(f"{i:>4} {str(d):10} {b['o']:7.2f} {b['h']:7.2f} {b['l']:7.2f} {b['c']:7.2f} {step.effective_stop:8.2f} {resting:9.2f}  {ev}")
            return
        resting = max(resting, depth_stop_price(line=step.effective_stop, hard_stop=HARD_STOP, entry_price=ENTRY,
                                                breakeven_active=bool(state["breakeven_active"]), adr20_pct=adr))
        print(f"{i:>4} {str(d):10} {b['o']:7.2f} {b['h']:7.2f} {b['l']:7.2f} {b['c']:7.2f} {step.effective_stop:8.2f} {resting:9.2f}  held")
    print(f"     open at session 20 ({sessions[-1][0]}); mark = close {last}")


for label, be in (("VARIANT A (main): breakeven armed on day 0 -- day-0 high 243.71 >= +3R arm", True),
                  ("VARIANT B (bound): breakeven NOT armed on day 0 -- hard stop 199.90 + depth stop only", False)):
    print("\n" + "=" * 100 + f"\n{label}")
    trace(be)
    res = run(be)
    pnl = res["pnl_per_share"] if res["status"] == "settled" else res["mark_pnl_per_share"]
    print(f"walk_arm (live #482 walker): status={res['status']} reason={res['reason']} final={res['final_reason']} "
          f"exit_session={res['exit_session']} sessions_walked={res['sessions_walked']} partial={res['partial_fired']}")
    for e in res["exits"]:
        print(f"   exit leg: {e}")
    print(f"   per-share P&L {pnl:+.2f} | {pnl/ENTRY*100:+.1f}% on entry | {pnl/R_ORB:+.2f} R_orb | {pnl/RISK:+.2f} R of risk-to-stop (15.02)")
print("\nReference: mi_ep_missed_outcomes (from the gap-day OPEN 211, not our entry): ret_20d +25.1%, max_high_20d +25.7%")
