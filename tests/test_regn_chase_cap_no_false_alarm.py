"""REGN 2026-10-30 — a deliberate chase-cap skip ends silently after its OWN page (message only).

At 09:36:30 the chase cap skipped REGN on purpose (`entry_chase_cap_skipped`: the fallback limit
$928.33 would have risked $110.83/sh against $52.38 planned, cap 1.5x) and paged
"No entry for REGN: Ran too far past ORB high to chase". `order_manager.submit_entry` returned None,
which `submit_trade_entry` read as a failed submit and paged AGAIN: "ORB auto-enter failed — check
logs" (plus an `orb_order_failed` audit row). Nothing was wrong — the rule worked.

The fix is message-only: when `submit_entry` returns None and the trade row carries the chase-cap
skip reason, the pipeline sends no failure page, writes no `orb_order_failed` row, and returns its own
action. A genuine failure pages exactly as before. No entry decision, cap, sizing or order moves.

The skip reason used here is NOT typed in: it is captured from the REAL `order_manager.submit_entry`
(both of its chase-cap branches), so the pipeline's recognizer is tested against what the producer
actually writes.
"""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from agents.market_intelligence.broker import entry_pipeline as ep
from agents.market_intelligence.broker import order_manager as om
from agents.market_intelligence.broker.skip_reasons import (
    INFRA_ORDER_SUBMIT_FAILED, SETUP_CHASE_CAP_EXCEEDED,
)
from tests.test_461_cap_toctou_race import FakeConn, FakeDB, _submit, _wire
from tests.test_500_price_aware_entry import _wire_submit_entry


async def _real_chase_cap_write(*, retry: bool) -> tuple[str, str]:
    """Run the REAL order_manager.submit_entry into each chase-cap branch and return the
    (status, skip_reason) it wrote — first attempt writes 'cancelled', the post-retry branch
    'order_failed'. planned risk 1.0 (orb 10.5 / stop 9.5); latest 12.00 -> limit 12.02 -> 2.52 > 1.5x.
    Its own MonkeyPatch scope, so none of its wiring leaks into the pipeline half."""
    with pytest.MonkeyPatch.context() as mp:
        latest = [{"price": 10.40}, {"price": 12.00}] if retry else {"price": 12.00}
        fake, _, _ = _wire_submit_entry(mp, latest)
        if retry:
            fake.place_bracket_order = AsyncMock(side_effect=RuntimeError("transient"))
            mp.setattr(om.asyncio, "sleep", AsyncMock())
        upd = AsyncMock()
        mp.setattr(om, "_update_trade_status", upd)
        assert await om.submit_entry(7) is None
        (args, kwargs) = upd.await_args
        return args[1], kwargs["skip_reason"]


def _wire_pipeline(monkeypatch, *, status: str | None, skip_reason: str | None,
                   unreadable: bool = False):
    """The real submit_trade_entry over the #461 FakeDB, with submit_entry returning None after
    leaving the trade row as the real function would (status + skip_reason), or untouched."""
    db = FakeDB()
    sent, audit = _wire(monkeypatch, db)
    seen: dict = {"sql": [], "db": db}
    real_fetchval = FakeConn.fetchval

    async def _fetchval(self, sql, *args):
        s = " ".join(sql.split())
        if "SELECT skip_reason FROM mi_live_trades" in s:
            seen["sql"].append((s, args))
            if unreadable:
                raise RuntimeError("db down")
            row = next((r for r in db.rows if r["id"] == args[0]), None)
            return row.get("skip_reason") if row else None
        return await real_fetchval(self, sql, *args)

    monkeypatch.setattr(FakeConn, "fetchval", _fetchval)

    async def _submit_entry_none(trade_id):
        row = next(r for r in db.rows if r["id"] == trade_id)
        if status is not None:
            row["status"], row["skip_reason"] = status, skip_reason
        return None

    monkeypatch.setattr(om, "submit_entry", AsyncMock(side_effect=_submit_entry_none))
    return sent, audit, seen


def _events(audit) -> list[str]:
    return [c.args[0] for c in audit.await_args_list]


@pytest.mark.asyncio
@pytest.mark.parametrize("retry", [False, True], ids=["first-attempt", "after-retry"])
async def test_chase_cap_skip_sends_no_failure_page_and_no_failure_row(monkeypatch, retry):
    status, reason = await _real_chase_cap_write(retry=retry)
    assert status == ("order_failed" if retry else "cancelled")
    assert reason.startswith(SETUP_CHASE_CAP_EXCEEDED)

    sent, audit, seen = _wire_pipeline(monkeypatch, status=status, skip_reason=reason)
    result = await _submit("REGN")

    assert result["action"] == ep.ACTION_CHASE_CAP_SKIPPED
    assert result["reason"] == SETUP_CHASE_CAP_EXCEEDED and result["trade_id"]
    # message-only: the pipeline's own channel is silent (the chase-cap page is order_manager's)
    assert sent == []
    assert "orb_order_failed" not in _events(audit)
    # the lookup is scoped to the trade AND its account mode (dual-account invariant 3)
    (sql, args), = seen["sql"]
    assert "id = $1" in sql and "account_mode = $2" in sql
    assert args == (result["trade_id"], seen["db"].rows[0]["account_mode"])


@pytest.mark.asyncio
async def test_chase_cap_action_is_neither_a_failure_nor_a_skip_digest_line(monkeypatch):
    """`live_tracker` builds its grouped "ORB skips" Telegram from SKIPPED / BLOCKED / filtered,
    and `lowcap_paper_entry` counts AUTO_ENTER_FAILED as a failure. A chase-cap result in either
    set would put a SECOND message (or a false failure count) right back."""
    sent, audit, _ = _wire_pipeline(monkeypatch, status="cancelled",
                                    skip_reason=f"{SETUP_CHASE_CAP_EXCEEDED}: limit $1.00")
    result = await _submit("REGN")
    assert result["action"] not in ("filtered", ep.ACTION_SKIPPED, ep.ACTION_BLOCKED,
                                    ep.ACTION_AUTO_ENTER_FAILED, ep.ACTION_AUTO_ENTERED,
                                    ep.ACTION_PROPOSED)


@pytest.mark.asyncio
@pytest.mark.parametrize("status,reason", [
    ("order_failed", f"{INFRA_ORDER_SUBMIT_FAILED}: boom"),     # the broker refused the order
    ("confirmed", None),                                        # halted / not-confirmed: row untouched
    ("cancelled", "setup:stop_too_wide: ORB $1.24"),            # some OTHER skip reason
])
async def test_a_genuine_failure_still_pages_exactly_as_before(monkeypatch, status, reason):
    sent, audit, _ = _wire_pipeline(monkeypatch, status=status, skip_reason=reason)
    result = await _submit("IONQ")

    assert result["action"] == ep.ACTION_AUTO_ENTER_FAILED
    assert len(sent) == 1 and "auto-enter failed — check logs (trade_id=" in sent[0]
    assert "orb_order_failed" in _events(audit)


@pytest.mark.asyncio
async def test_an_unreadable_row_fails_open_to_the_failure_page(monkeypatch):
    """If the pipeline cannot tell WHY submit_entry returned None it must page, never swallow."""
    sent, audit, _ = _wire_pipeline(monkeypatch, status="cancelled",
                                    skip_reason=f"{SETUP_CHASE_CAP_EXCEEDED}: limit $1.00",
                                    unreadable=True)
    result = await _submit("REGN")

    assert result["action"] == ep.ACTION_AUTO_ENTER_FAILED
    assert len(sent) == 1 and "auto-enter failed" in sent[0]
