"""Tests for the ADR 0008 increment-1 demotion fence (audit_trade_state_demotions).

The load-bearing assertion (advisor 2026-06-06): the gate must FAIL the
pre-#151 incident shape (null stop_order_id in an except, no broker read) and
PASS the post-#151 shape (same null after a confirming broker read + a
`# broker-confirmed:` tag). A gate that passes the code that caused the incident
enforces nothing.
"""
from __future__ import annotations

from scripts.audit_trade_state_demotions import audit_text


def _violations(sites):
    return [s for s in sites if s["in_except"] and not s["tagged"]]


# ── The incident shapes ────────────────────────────────────────────────────

PRE_151 = '''
async def execute_partial_exit():
    try:
        await place_new_stop(...)
    except Exception as e:
        # blind: null the stop because an op failed — the 2026-06-04 bug.
        await set_stop_order_id(trade_id, None, reason="partial_naked")
'''

POST_151 = '''
async def execute_partial_exit():
    try:
        await place_new_stop(...)
    except Exception as e:
        old_stop_live = False
        chk = await alpaca.get_order(old_stop_id)
        old_stop_live = chk and chk.get("status") in LIVE
        if old_stop_live:
            return False
        # broker-confirmed: alpaca.get_order above set old_stop_live=False,
        # i.e. the broker itself confirmed the old stop is gone.
        await set_stop_order_id(trade_id, None, reason="partial_naked")
'''

NORMAL_CLOSE = '''
async def finalize_stop_fill():
    # broker stop-fill EVENT drove this — a real close, not in an error path.
    await conn.execute("""
        UPDATE mi_live_trades SET status = 'closed', stop_order_id = NULL,
            closed_at = NOW() WHERE id = $1
    """, trade_id)
'''

PROMOTION = '''
async def cycle_stop():
    try:
        await place(...)
    except Exception:
        # sets a NEW stop id — a promotion, must NOT be flagged.
        await conn.execute(
            "UPDATE mi_live_trades SET stop_order_id = $2 WHERE id = $1",
            trade_id, new_id)
'''


def test_pre_151_shape_fails():
    # The incident shape MUST be a violation, or the gate is theater.
    sites = audit_text(PRE_151)
    assert _violations(sites), "pre-#151 null-in-except must be flagged"


def test_post_151_shape_passes():
    # Broker-read + tag → the reviewed escape, no violation.
    sites = audit_text(POST_151)
    flagged = [s for s in sites if s["in_except"]]
    assert flagged and all(s["tagged"] for s in flagged)
    assert not _violations(sites)


def test_normal_close_not_flagged():
    # A legit close outside any except path is not the gate's business.
    sites = audit_text(NORMAL_CLOSE)
    assert sites                              # it IS a demotion write
    assert all(not s["in_except"] for s in sites)
    assert not _violations(sites)


def test_promotion_not_flagged():
    # Value-aware: stop_order_id = $2 (new id) is a promotion, never flagged.
    sites = audit_text(PROMOTION)
    assert not sites


def test_tag_must_be_inside_the_except_block():
    # A tag in a DIFFERENT (earlier) block must not launder a later untagged one.
    text = '''
async def f():
    try:
        a()
    except Exception:
        # broker-confirmed: this one is fine
        await set_stop_order_id(t, None)
    try:
        b()
    except Exception:
        await set_stop_order_id(t, None)   # this one is NOT covered
'''
    sites = audit_text(text)
    assert len(_violations(sites)) == 1
