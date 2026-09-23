"""Live auto-entry decision (operator-signed 2026-06-20, START-SMALL launch).

`entry_pipeline._should_auto_enter` is the single predicate that decides whether
`submit_trade_entry` auto-submits the bracket immediately or sends a manual-confirm
Telegram proposal. This is the REAL-money gate, so it gets a frozen truth table:

  - paper                          -> auto (paper always auto-confirms)
  - live + live_real_enabled=True  -> auto REAL money (the Monday launch behavior)
  - live + live_real_enabled=False -> proposal (the staged-paper ramp stays manual)

If this table ever changes silently, real money would either auto-fire when it
shouldn't (live+False) or fail to fire when it should (live+True) — both are
launch-critical regressions, hence the explicit pin.
"""
import pytest

from agents.market_intelligence.broker.entry_pipeline import _should_auto_enter


@pytest.mark.parametrize(
    "account_mode,live_real_enabled,expected",
    [
        ("paper", False, True),   # paper auto-confirms regardless of the flag
        ("paper", True, True),
        ("live", True, True),     # REAL-money auto-entry — the GO behavior
        ("live", False, False),   # staged-paper ramp — manual confirm, NOT auto
    ],
)
def test_auto_enter_truth_table(account_mode, live_real_enabled, expected):
    assert _should_auto_enter(account_mode, live_real_enabled) is expected


def test_live_requires_real_enabled_flag_to_auto_fire():
    # The core safety pin: a phase=live strategy does NOT auto-fire real money
    # until live_real_enabled is explicitly True. The ramp (False) stays a proposal.
    assert _should_auto_enter("live", False) is False
    assert _should_auto_enter("live", True) is True


def test_truthy_flag_is_coerced_to_bool():
    # strategy.live_real_enabled comes from the DB row; guard against a truthy
    # non-bool (e.g. 1/0) silently changing behavior.
    assert _should_auto_enter("live", 1) is True
    assert _should_auto_enter("live", 0) is False
