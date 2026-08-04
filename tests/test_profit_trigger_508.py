"""#508 — intraday profit trigger (operator-signed 2026-08-01).

Pins the properties that make this safe to run on live money:
  1. OFF by default. The shipped constant is None; the trigger is inert until the
     operator sets it. Reversion for this change is that constant, not a revert.
  2. It does NOT live inside track_open_position_extremes. That recorder is
     name-registered in the column-write authority gate; folding a money action
     into it would trip Gate 5 G and blur a pure recorder (the #500 class).
  3. It reuses execute_partial_exit — which reduces the stop BEFORE selling — so
     there is never a window where the stop over-covers the position.
  4. Detection is BAR-based (in-hold high), not spot, so a spike between 5-minute
     polls is still caught.
  5. A notification failure can never abort the sell.
"""
import ast
import pathlib

SRC = pathlib.Path("agents/market_intelligence/broker/order_manager.py").read_text()
TREE = ast.parse(SRC)


def _fn(name):
    return next(n for n in ast.walk(TREE)
                if isinstance(n, (ast.AsyncFunctionDef, ast.FunctionDef)) and n.name == name)


def test_trigger_value_matches_the_SSoT():
    """Was "must be OFF"; that froze the shipped default and would have had to be
    deleted the moment the operator flipped it — a guard you delete is not a guard.
    What actually matters is that CODE AND SSoT CANNOT DIVERGE: whatever the constant
    says, docs/setups/exit_discipline.md must say the same. Stale SSoT is worse than
    no SSoT (CHANGE_PROCESS r6)."""
    from agents.market_intelligence import constants
    ssot = pathlib.Path("docs/setups/exit_discipline.md").read_text()
    v = constants.PROFIT_TRIGGER_R
    if not v:
        assert "PROFIT_TRIGGER_R = None" in ssot, "SSoT must record that the trigger is OFF"
    else:
        assert f"PROFIT_TRIGGER_R = {v:g}" in ssot, (
            f"constant is {v:g} but the SSoT does not record that value — "
            "code and doc have diverged")


def test_trigger_returns_immediately_when_off():
    src = ast.get_source_segment(SRC, _fn("scan_profit_triggers"))
    head = src[:src.index("pool = await get_pool()")]
    assert "if not PROFIT_TRIGGER_R" in head and "return []" in head, (
        "the off-switch must short-circuit BEFORE any DB or broker work")


def test_money_action_is_NOT_inside_the_recorder():
    """Gate 5 G / #500 class: the recorder owns highest/lowest_price_seen by name."""
    rec = ast.get_source_segment(SRC, _fn("track_open_position_extremes"))
    assert "execute_partial_exit" not in rec, (
        "a partial inside the name-registered recorder would trip the column-write gate")


def test_it_reuses_execute_partial_exit_not_a_raw_sell():
    """execute_partial_exit reduces the stop FIRST under an advisory lock. Any
    bespoke sell here would re-introduce the unprotected window the design avoids."""
    src = ast.get_source_segment(SRC, _fn("scan_profit_triggers"))
    assert "await execute_partial_exit(" in src
    for forbidden in ("place_market_sell", "submit_order", "close_position"):
        assert forbidden not in src, f"{forbidden} bypasses the stop-first sequence"


def test_detection_uses_the_bar_HIGH_not_a_spot_price():
    src = ast.get_source_segment(SRC, _fn("scan_profit_triggers"))
    assert "MAX(high)" in src, "spot sampling would miss a spike between 5-minute polls"
    assert "bar_time >= $2" in src, "must scan only IN-HOLD bars"


def test_notify_failure_cannot_abort_the_sell():
    src = ast.get_source_segment(SRC, _fn("scan_profit_triggers"))
    notify = src.index("send_telegram_message")
    sell = src.index("await execute_partial_exit(")
    assert notify < sell, "operator is told before the money moves"
    assert "except Exception" in src[notify:sell], "a notify failure must not abort the sell"


def test_it_never_fires_twice_on_one_trade():
    src = ast.get_source_segment(SRC, _fn("scan_profit_triggers"))
    assert "partial_taken" in src and "FALSE" in src, (
        "must exclude trades whose partial already fired — the 3:45 job may also act")


def test_time_gate_stands_down_when_the_trigger_is_on():
    """Exactly one owner per decision. With PROFIT_TRIGGER_R set, the 3:45 time gate
    must not also take a partial — and with it None, the old rule must still run."""
    src = pathlib.Path("agents/market_intelligence/broker/live_tracker.py").read_text()
    i = src.index("async def run_partial_exits")
    seg = src[i:i + 9000]
    assert "skip_partial_decision=bool(PROFIT_TRIGGER_R)" in seg, (
        "the 3:45 job must stand down when the intraday trigger owns the partial")


def test_exit_logic_stays_pure_no_config_dependency():
    """exit_logic is the shared decision SSoT for live, paper and shadow. A config
    import there would make the same inputs produce different outputs per process."""
    src = pathlib.Path("agents/market_intelligence/broker/exit_logic.py").read_text()
    assert "PROFIT_TRIGGER_R" not in src, "keep the flag at the caller, not in pure logic"


def test_skip_flag_genuinely_suppresses_the_day5_branch():
    """BEHAVIOURAL, not a string match. Day 5 and underwater is the exact case the
    old rule fires on unconditionally — the one the operator ruled out. Prove the
    flag governs it in both directions, so 'stands down' is a fact not a comment."""
    from datetime import date
    from agents.market_intelligence.broker.exit_logic import apply_daily_exit_step
    state = {"alert_date": date(2026, 7, 20), "remaining_shares": 300, "entry_price": 100.0,
             "hard_stop": 95.0, "partial_taken": False, "breakeven_active": False,
             "exits": [], "running_closes": [99.0] * 12}
    bar = {"close": 98.0, "high": 99.0, "low": 97.0}          # underwater
    day = date(2026, 7, 25)                                    # calendar day 5
    on = apply_daily_exit_step(state, bar, day, integer_partial_shares=True,
                               skip_hard_stop_close=True, skip_partial_decision=True)
    off = apply_daily_exit_step(state, bar, day, integer_partial_shares=True,
                                skip_hard_stop_close=True, skip_partial_decision=False)
    assert off.partial_fired is True, "day-5 unconditional branch should fire when NOT skipped"
    assert on.partial_fired is False, "trigger ON must suppress the time gate entirely"


# ── the 2026-08-04 bombardment (operator: "bombarded with these msg non stop") ────────────────
# The volume was a PAIR of messages every 5 minutes. `_breaker_already_alerted` fixed one; these
# pin the other. The announcement re-fired because BOTH selection conditions are sticky while the
# partial keeps failing: `partial_taken` only flips on SUCCESS, and `MAX(high) >= target` having
# once been true is true forever. So an unharvestable position announced every cycle for hours.


def test_the_profit_target_announcement_is_deduped_per_trade():
    src = ast.get_source_segment(SRC, _fn("scan_profit_triggers"))
    notify = src.index("send_telegram_message")
    guard = src.rindex("_profit_trigger_already_announced", 0, notify)
    assert "if not await" in src[guard - 40:guard], (
        "the announcement must be gated on the per-trade dedupe, not fired unconditionally")


def test_the_dedupe_reads_DURABLE_state_not_process_memory():
    """A service restart must not re-arm the loop. Process-local state would mean every deploy
    re-bombards the operator about a condition already reported."""
    src = ast.get_source_segment(SRC, _fn("_profit_trigger_already_announced"))
    assert "mi_audit_log" in src, "the audit row is the state — it survives a restart"
    assert "set()" not in src and "global " not in src


def test_the_dedupe_counts_ANY_prior_row_not_more_than_one():
    """Ordering differs from the breaker's: this runs BEFORE the cycle writes its own audit row,
    so `> 1` would let exactly one duplicate through every time. Off-by-one is the whole bug."""
    fn = _fn("_profit_trigger_already_announced")
    body = "\n".join(ast.get_source_segment(SRC, s) or "" for s in fn.body
                     if not (isinstance(s, ast.Expr) and isinstance(s.value, ast.Constant)))
    assert "> 0" in body and "> 1" not in body, (
        "checked against the executable body — the docstring names the breaker's `> 1` "
        "deliberately, to explain the difference")


def test_the_dedupe_watches_BOTH_outcome_events():
    """`profit_trigger_failed` is the row a repeatedly-failing trade writes — miss it and the
    dedupe never engages on the exact case that caused the bombardment."""
    src = ast.get_source_segment(SRC, _fn("_profit_trigger_already_announced"))
    assert "profit_trigger_failed" in src and "profit_trigger_fired" in src


def test_the_dedupe_fails_OPEN():
    """A missed alert on a live money path is worse than a duplicate. Same direction as the
    breaker dedupe and the inert-sweep check."""
    src = ast.get_source_segment(SRC, _fn("_profit_trigger_already_announced"))
    i = src.index("except Exception")
    assert "return False" in src[i:], "on any error it must still announce"


def test_the_audit_TRAIL_is_not_deduped_only_the_telegram():
    """The durable record must stay complete every cycle — the dedupe is a notification fix, not
    a logging fix. A quiet system that also stops recording is how a real signal is lost."""
    src = ast.get_source_segment(SRC, _fn("scan_profit_triggers"))
    audit = src.index('"profit_trigger_fired" if ok else "profit_trigger_failed"')
    guard = src.index("_profit_trigger_already_announced")
    assert guard < audit, "guard is above; the audit call must sit outside it"
    assert "_profit_trigger_already_announced" not in src[audit:], (
        "the audit write must never be conditioned on the dedupe")
