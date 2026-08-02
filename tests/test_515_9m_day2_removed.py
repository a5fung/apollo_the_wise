"""#515 — the 9M Day 2 ENTRY strategy is REMOVED (2026-08-02). This file guards the removal.

Operator 2026-08-01: *"9m is a stock character, 9m day2 is dead and needs to be gone period."*

Replaces `test_9m_day2_deprecated_gate.py`, which tested a GATE that stopped the deprecated
`_9m_day2_orb_job` from scanning and Telegramming. The job itself is gone now, so a gate on it is
moot — these are regression guards that the removal STAYS removed and, just as importantly, that it
did not OVERSHOOT.

**The distinction this file exists to hold**: the Day-2 ENTRY STRATEGY is retired; the 9M CHARACTER
detection is NOT. Over-deletion is the real risk here and it is easy to reach by grepping `9m` or
`sugar_bab` — `mi_9m_day2_candidates` was renamed FROM `mi_9m_sugar_babies`, while
`mi_sugar_babies_cohort` is the persistent Pradeep cohort that STAYS.
"""
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]


def _src(rel: str) -> str:
    return (_ROOT / rel).read_text()


# ── the entry strategy is gone ───────────────────────────────────────────────────────────────

def test_the_day2_orb_job_no_longer_exists():
    from agents.market_intelligence import scheduler
    assert not hasattr(scheduler, "_9m_day2_orb_job")


def test_job_id_is_gone_from_registration_AND_the_role_partition():
    """Both must go together. A registered id missing from the role sets fails the boot guard;
    an owned id with no registration fails it the other way. Either is a 3am crash."""
    s = _src("agents/market_intelligence/scheduler.py")
    assert '"9m_day2_orb"' not in s


def test_the_entry_function_is_gone_from_the_broker():
    from agents.market_intelligence.broker import live_tracker
    assert not hasattr(live_tracker, "submit_9m_day2_trade")


def test_it_is_gone_from_the_execution_facade():
    """The facade asserts route/client parity at boot, so a half-removal fails loudly — assert it
    here too, so the failure is a red test rather than a boot crash."""
    from agents.market_intelligence import execution_client
    assert not hasattr(execution_client, "submit_9m_day2_trade")
    assert "submit_9m_day2_trade" not in _src("agents/market_intelligence/execution_client.py")


def test_the_manual_telegram_trigger_cannot_submit():
    """`trade 9m TICKER` must answer with a pointer, never reach a submit path."""
    assert "submit_9m_day2_trade" not in _src("agents/market_intelligence/agent.py")


# ── the 9M CHARACTER survived — the anti-over-deletion guard ─────────────────────────────────

def test_the_9m_character_scan_job_still_exists():
    assert '"9m_ep_scan"' in _src("agents/market_intelligence/scheduler.py"), \
        "the 9M CHARACTER scan must survive the Day-2 removal"


def test_the_prior_day_low_geometry_survived_under_its_real_name():
    """It is a GEOMETRY, not the strategy. The #482 shadow lane runs it (105 acted rows); the
    rename is precisely what let the strategy be deleted without taking the geometry with it."""
    from agents.market_intelligence.broker import order_manager
    assert hasattr(order_manager, "prepare_prior_day_low_orb_order")
    assert not hasattr(order_manager, "prepare_9m_day2_orb_order")


def test_the_shadow_lane_still_calls_that_geometry():
    assert "prepare_prior_day_low_orb_order" in \
        _src("agents/market_intelligence/broker/shadow_orb_tracker.py"), \
        "#482 evidence lane must keep accruing"


@pytest.mark.parametrize("table", ["mi_9m_ep_alerts", "mi_sugar_babies_cohort",
                                   "mi_9m_day2_candidates"])
def test_character_and_history_tables_keep_their_references(table):
    """mi_9m_day2_candidates the TABLE is retained for history — only its WRITER goes."""
    hits = [p for p in (_ROOT / "agents").rglob("*.py") if table in p.read_text()]
    assert hits, f"{table} lost all references — over-deletion"
