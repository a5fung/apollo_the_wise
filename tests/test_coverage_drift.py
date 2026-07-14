"""Regression tests for the read-only DB<->broker coverage-drift detector
(#184, ADR 0008 increment 2, 2026-07-05).

detect_coverage_drift() must NEVER mutate trade state — its only writes are
mi_audit_log rows (log_audit_event) and Telegram (send_telegram_message).
Pins:
  - D1 untracked broker position -> HIGH, audit + Telegram
  - D2 apollo-prefixed orphan order -> HIGH, audit + Telegram
  - D2 foreign/manual client_order_id -> INFO, audit only, no Telegram
  - D2 order referenced by a TERMINAL (e.g. cancelled) row -> NOT drift
    (CLSK 2026-07-07 cancel-window false positive: broker order still open,
    DB row already `cancelled` by the 10:00 ET ORB-unfilled cleanup) — while
    a genuine orphan (NO row in ANY status references it) still fires HIGH,
    and D1 stays keyed on OPEN rows only (a cancelled row has no live
    position, so an untracked position for that ticker must still fire)
  - D3 DB-open-without-broker-presence -> INFO, audit only, no Telegram
  - clean state (broker and DB agree) -> zero audit writes, zero Telegram
  - dedup: an existing coverage_drift_alerted row within 24h suppresses the
    Telegram but the coverage_drift_detected row is still written
  - degraded broker read (raise_on_error path raises) -> coverage_drift_check_degraded
    audit row only, no drift reported, no Telegram (same for either DB read,
    including the all-status known-order-ids fetch)
"""
from unittest.mock import AsyncMock, patch

import pytest

from tests.conftest import make_mock_pool

from agents.market_intelligence.broker.coverage_drift import (
    D1_UNTRACKED_POSITION,
    D2_UNTRACKED_ORDER_HIGH,
    D2_UNTRACKED_ORDER_INFO,
    D3_DB_OPEN_NO_BROKER,
    detect_coverage_drift,
)
from agents.market_intelligence.audit_events import (
    COVERAGE_DRIFT_ALERTED,
    COVERAGE_DRIFT_CHECK_DEGRADED,
    COVERAGE_DRIFT_DETECTED,
)

MOD = "agents.market_intelligence.broker.coverage_drift"


def _setup(db_rows=None, positions=None, open_orders=None, dedup_hit=None,
           all_db_rows=None):
    """Build a mocked pool/conn + patch targets for one detect_coverage_drift call.

    dedup_hit: return value for conn.fetchval (the _already_alerted SELECT) —
    None (default) = no prior alert; 1 = an alert marker already exists (dedup).

    all_db_rows: rows for the SECOND conn.fetch (_fetch_all_known_order_ids —
    ANY-status rows, only entry_order_id/stop_order_id read). Default None =
    same as db_rows (every open row also appears in the all-status fetch).
    detect_coverage_drift issues the two fetches in a fixed order (open rows,
    then all-status known ids), so a side_effect list is deterministic.
    """
    pool, conn = make_mock_pool()
    if all_db_rows is None:
        conn.fetch = AsyncMock(return_value=db_rows or [])
    else:
        conn.fetch = AsyncMock(side_effect=[db_rows or [], all_db_rows])
    conn.fetchval = AsyncMock(return_value=dedup_hit)
    return pool, conn


@pytest.mark.asyncio
async def test_d1_detected_on_untracked_position():
    """Broker holds XYZ, no open DB row for it -> D1 HIGH, audit + Telegram."""
    pool, conn = _setup(
        db_rows=[],
        positions=[{"symbol": "XYZ", "qty": 100.0, "avg_entry_price": 10.0}],
        open_orders=[],
    )
    with patch(f"{MOD}.get_pool", new=AsyncMock(return_value=pool)), \
         patch(f"{MOD}.alpaca.get_all_positions",
               new=AsyncMock(return_value=[{"symbol": "XYZ", "qty": 100.0, "avg_entry_price": 10.0}])), \
         patch(f"{MOD}.alpaca.get_open_orders", new=AsyncMock(return_value=[])), \
         patch(f"{MOD}.log_audit_event", new=AsyncMock()) as audit, \
         patch(f"{MOD}.send_telegram_message", new=AsyncMock()) as tg:
        result = await detect_coverage_drift("paper")

    assert result["d1_count"] == 1
    assert result["alerted"] == 1
    assert result["degraded"] is False
    tg.assert_called_once()
    assert "XYZ" in tg.call_args[0][0]

    # Two audit writes expected: the detection row + the alert marker.
    event_types = [c.args[0] for c in audit.call_args_list]
    assert event_types.count(COVERAGE_DRIFT_DETECTED) == 1
    assert event_types.count(COVERAGE_DRIFT_ALERTED) == 1
    detected_call = next(c for c in audit.call_args_list if c.args[0] == COVERAGE_DRIFT_DETECTED)
    assert D1_UNTRACKED_POSITION in detected_call.args[2]


@pytest.mark.asyncio
async def test_d2_high_on_apollo_prefixed_orphan_order():
    """Open order with our apollo_{mode}_ COID, not referenced by any open DB
    row's entry/stop -> D2 HIGH, audit + Telegram."""
    order = {
        "id": "order-abc-123", "symbol": "ABC", "side": "buy", "type": "stop_limit",
        "client_order_id": "apollo_paper_magna53_ABC_1715450123456",
    }
    pool, conn = _setup(db_rows=[], positions=[], open_orders=[order])
    with patch(f"{MOD}.get_pool", new=AsyncMock(return_value=pool)), \
         patch(f"{MOD}.alpaca.get_all_positions", new=AsyncMock(return_value=[])), \
         patch(f"{MOD}.alpaca.get_open_orders", new=AsyncMock(return_value=[order])), \
         patch(f"{MOD}.log_audit_event", new=AsyncMock()) as audit, \
         patch(f"{MOD}.send_telegram_message", new=AsyncMock()) as tg:
        result = await detect_coverage_drift("paper")

    assert result["d2_high_count"] == 1
    assert result["d2_info_count"] == 0
    assert result["alerted"] == 1
    tg.assert_called_once()
    assert "ABC" in tg.call_args[0][0]

    detected_call = next(c for c in audit.call_args_list if c.args[0] == COVERAGE_DRIFT_DETECTED)
    assert D2_UNTRACKED_ORDER_HIGH in detected_call.args[2]
    assert "HIGH" in detected_call.args[2]


@pytest.mark.asyncio
async def test_d2_info_on_foreign_coid_no_telegram():
    """Open order whose COID does NOT match our apollo_{mode}_ prefix ->
    D2 INFO, audit only, no Telegram (operator may trade manually)."""
    order = {
        "id": "order-manual-1", "symbol": "DEF", "side": "sell", "type": "limit",
        "client_order_id": "manual-web-order-42",
    }
    pool, conn = _setup(db_rows=[], positions=[], open_orders=[order])
    with patch(f"{MOD}.get_pool", new=AsyncMock(return_value=pool)), \
         patch(f"{MOD}.alpaca.get_all_positions", new=AsyncMock(return_value=[])), \
         patch(f"{MOD}.alpaca.get_open_orders", new=AsyncMock(return_value=[order])), \
         patch(f"{MOD}.log_audit_event", new=AsyncMock()) as audit, \
         patch(f"{MOD}.send_telegram_message", new=AsyncMock()) as tg:
        result = await detect_coverage_drift("paper")

    assert result["d2_info_count"] == 1
    assert result["d2_high_count"] == 0
    assert result["alerted"] == 0
    tg.assert_not_called()

    audit.assert_called_once()
    assert audit.call_args.args[0] == COVERAGE_DRIFT_DETECTED
    assert D2_UNTRACKED_ORDER_INFO in audit.call_args.args[2]


@pytest.mark.asyncio
async def test_d2_harness_coid_is_info_not_high_no_telegram():
    """#439: an integration-test harness order (apollo_paper_integration_test_*) starts with the
    apollo_paper_ prefix but is KNOWN test cruft — classify INFO, never a D2-HIGH Telegram."""
    order = {
        "id": "order-harness-1", "symbol": "F", "side": "buy", "type": "stop_limit",
        "client_order_id": "apollo_paper_integration_test_1715450123456",
    }
    pool, conn = _setup(db_rows=[], positions=[], open_orders=[order])
    with patch(f"{MOD}.get_pool", new=AsyncMock(return_value=pool)), \
         patch(f"{MOD}.alpaca.get_all_positions", new=AsyncMock(return_value=[])), \
         patch(f"{MOD}.alpaca.get_open_orders", new=AsyncMock(return_value=[order])), \
         patch(f"{MOD}.log_audit_event", new=AsyncMock()) as audit, \
         patch(f"{MOD}.send_telegram_message", new=AsyncMock()) as tg:
        result = await detect_coverage_drift("paper")

    assert result["d2_info_count"] == 1 and result["d2_high_count"] == 0
    assert result["alerted"] == 0
    tg.assert_not_called()  # no D2-HIGH noise for known test cruft
    assert D2_UNTRACKED_ORDER_INFO in audit.call_args.args[2]


@pytest.mark.asyncio
async def test_d2_not_flagged_when_terminal_row_references_order():
    """The CLSK 2026-07-07 cancel-window false positive: the broker order is
    still open (cancel in flight) but a CANCELLED mi_live_trades row already
    references it as entry_order_id (row 257, `ORB window unfilled` cleanup).
    That order IS tracked -> no D2, no Telegram, no detection audit row."""
    cancelled_row = {
        "id": 257, "ticker": "CLSK",
        "entry_order_id": "96c48f58-aaaa-bbbb-cccc-1234567890ab",
        "stop_order_id": None, "status": "cancelled",
    }
    order = {
        "id": "96c48f58-aaaa-bbbb-cccc-1234567890ab", "symbol": "CLSK",
        "side": "buy", "type": "stop_limit",
        "client_order_id": "apollo_live_magna53_CLSK_1751896800000",
    }
    # Open-rows fetch: empty (the row is terminal). All-status fetch: has it.
    pool, conn = _setup(db_rows=[], positions=[], open_orders=[order],
                        all_db_rows=[cancelled_row])
    with patch(f"{MOD}.get_pool", new=AsyncMock(return_value=pool)), \
         patch(f"{MOD}.alpaca.get_all_positions", new=AsyncMock(return_value=[])), \
         patch(f"{MOD}.alpaca.get_open_orders", new=AsyncMock(return_value=[order])), \
         patch(f"{MOD}.log_audit_event", new=AsyncMock()) as audit, \
         patch(f"{MOD}.send_telegram_message", new=AsyncMock()) as tg:
        result = await detect_coverage_drift("live")

    assert result["d2_high_count"] == 0
    assert result["d2_info_count"] == 0
    assert result["d1_count"] == 0 and result["d3_count"] == 0
    assert result["alerted"] == 0
    tg.assert_not_called()
    audit.assert_not_called()  # tracked order = not drift = zero writes


@pytest.mark.asyncio
async def test_d2_genuine_orphan_still_fires_despite_terminal_rows():
    """SAFEGUARD PIN (THE LINE): the ANY-status tracking set must ONLY absorb
    orders a row actually references. An apollo-prefixed order that NO row
    (any status) references is a genuine mirror gap -> D2 HIGH still fires,
    even with terminal rows present for OTHER orders of the same ticker."""
    terminal_row_other_order = {
        "id": 300, "ticker": "ABC",
        "entry_order_id": "old-entry-1111", "stop_order_id": "old-stop-2222",
        "status": "closed",
    }
    orphan = {
        "id": "orphan-order-9999", "symbol": "ABC", "side": "buy",
        "type": "stop_limit",
        "client_order_id": "apollo_paper_magna53_ABC_1751896800000",
    }
    pool, conn = _setup(db_rows=[], positions=[], open_orders=[orphan],
                        all_db_rows=[terminal_row_other_order])
    with patch(f"{MOD}.get_pool", new=AsyncMock(return_value=pool)), \
         patch(f"{MOD}.alpaca.get_all_positions", new=AsyncMock(return_value=[])), \
         patch(f"{MOD}.alpaca.get_open_orders", new=AsyncMock(return_value=[orphan])), \
         patch(f"{MOD}.log_audit_event", new=AsyncMock()) as audit, \
         patch(f"{MOD}.send_telegram_message", new=AsyncMock()) as tg:
        result = await detect_coverage_drift("paper")

    assert result["d2_high_count"] == 1
    assert result["alerted"] == 1
    tg.assert_called_once()
    assert "ABC" in tg.call_args[0][0]
    detected_call = next(c for c in audit.call_args_list if c.args[0] == COVERAGE_DRIFT_DETECTED)
    assert D2_UNTRACKED_ORDER_HIGH in detected_call.args[2]


@pytest.mark.asyncio
async def test_d1_still_fires_when_only_a_terminal_row_exists_for_ticker():
    """SAFEGUARD PIN (THE LINE): D1 stays keyed on OPEN rows only. A cancelled
    row has no live position, so a broker position for that ticker is still
    genuinely untracked — the ANY-status set (D2-only) must NOT leak into
    D1's ticker matching and mute the untracked-position alarm."""
    cancelled_row = {
        "id": 257, "ticker": "CLSK",
        "entry_order_id": "96c48f58-aaaa-bbbb-cccc-1234567890ab",
        "stop_order_id": None, "status": "cancelled",
    }
    position = {"symbol": "CLSK", "qty": 80.0, "avg_entry_price": 12.5}
    pool, conn = _setup(db_rows=[], positions=[position], open_orders=[],
                        all_db_rows=[cancelled_row])
    with patch(f"{MOD}.get_pool", new=AsyncMock(return_value=pool)), \
         patch(f"{MOD}.alpaca.get_all_positions", new=AsyncMock(return_value=[position])), \
         patch(f"{MOD}.alpaca.get_open_orders", new=AsyncMock(return_value=[])), \
         patch(f"{MOD}.log_audit_event", new=AsyncMock()) as audit, \
         patch(f"{MOD}.send_telegram_message", new=AsyncMock()) as tg:
        result = await detect_coverage_drift("live")

    assert result["d1_count"] == 1
    assert result["alerted"] == 1
    tg.assert_called_once()
    assert "CLSK" in tg.call_args[0][0]
    detected_call = next(c for c in audit.call_args_list if c.args[0] == COVERAGE_DRIFT_DETECTED)
    assert D1_UNTRACKED_POSITION in detected_call.args[2]


@pytest.mark.asyncio
async def test_degraded_known_ids_read_no_drift_reported():
    """The SECOND DB read (_fetch_all_known_order_ids) raises -> degraded
    audit row only, no drift reported — a failed tracking-set read must never
    be interpreted as 'nothing tracked' (mass D2 false-HIGH, #137 class)."""
    order = {
        "id": "order-abc-123", "symbol": "ABC", "side": "buy", "type": "stop_limit",
        "client_order_id": "apollo_paper_magna53_ABC_1715450123456",
    }
    pool, conn = _setup()
    conn.fetch = AsyncMock(side_effect=[[], RuntimeError("db down mid-cycle")])
    with patch(f"{MOD}.get_pool", new=AsyncMock(return_value=pool)), \
         patch(f"{MOD}.alpaca.get_all_positions", new=AsyncMock(return_value=[])), \
         patch(f"{MOD}.alpaca.get_open_orders", new=AsyncMock(return_value=[order])), \
         patch(f"{MOD}.log_audit_event", new=AsyncMock()) as audit, \
         patch(f"{MOD}.send_telegram_message", new=AsyncMock()) as tg:
        result = await detect_coverage_drift("paper")

    assert result["degraded"] is True
    assert result["d2_high_count"] == 0
    tg.assert_not_called()
    audit.assert_called_once()
    assert audit.call_args.args[0] == COVERAGE_DRIFT_CHECK_DEGRADED


@pytest.mark.asyncio
async def test_d3_stays_info_no_telegram():
    """Open DB row (GHI) with no broker position and no live entry order ->
    D3 INFO, audit only, no Telegram (sync_positions/reconcile own this)."""
    db_row = {
        "id": 42, "ticker": "GHI", "entry_order_id": "eo-dead",
        "stop_order_id": "so-dead", "status": "filled",
    }
    pool, conn = _setup(db_rows=[db_row], positions=[], open_orders=[])
    with patch(f"{MOD}.get_pool", new=AsyncMock(return_value=pool)), \
         patch(f"{MOD}.alpaca.get_all_positions", new=AsyncMock(return_value=[])), \
         patch(f"{MOD}.alpaca.get_open_orders", new=AsyncMock(return_value=[])), \
         patch(f"{MOD}.log_audit_event", new=AsyncMock()) as audit, \
         patch(f"{MOD}.send_telegram_message", new=AsyncMock()) as tg:
        result = await detect_coverage_drift("paper")

    assert result["d3_count"] == 1
    assert result["alerted"] == 0
    tg.assert_not_called()
    audit.assert_called_once()
    assert audit.call_args.args[0] == COVERAGE_DRIFT_DETECTED
    assert D3_DB_OPEN_NO_BROKER in audit.call_args.args[2]


@pytest.mark.asyncio
async def test_clean_state_zero_writes():
    """Broker and DB fully agree -> zero audit writes, zero Telegram."""
    db_row = {
        "id": 7, "ticker": "OK", "entry_order_id": "eo-live",
        "stop_order_id": "so-live", "status": "filled",
    }
    position = {"symbol": "OK", "qty": 50.0, "avg_entry_price": 20.0}
    order = {
        "id": "eo-live", "symbol": "OK", "side": "sell", "type": "stop",
        "client_order_id": "apollo_paper_magna53_OK_1715450000000",
    }
    pool, conn = _setup(db_rows=[db_row], positions=[position], open_orders=[order])
    with patch(f"{MOD}.get_pool", new=AsyncMock(return_value=pool)), \
         patch(f"{MOD}.alpaca.get_all_positions", new=AsyncMock(return_value=[position])), \
         patch(f"{MOD}.alpaca.get_open_orders", new=AsyncMock(return_value=[order])), \
         patch(f"{MOD}.log_audit_event", new=AsyncMock()) as audit, \
         patch(f"{MOD}.send_telegram_message", new=AsyncMock()) as tg:
        result = await detect_coverage_drift("paper")

    assert result == {
        "account_mode": "paper", "degraded": False,
        "d1_count": 0, "d2_high_count": 0, "d2_info_count": 0, "d3_count": 0,
        "alerted": 0, "deduped": 0,
    }
    audit.assert_not_called()
    tg.assert_not_called()


@pytest.mark.asyncio
async def test_dedup_suppresses_telegram_but_still_writes_detection():
    """A coverage_drift_alerted marker already exists (within 24h) for this
    exact signature -> Telegram suppressed, but coverage_drift_detected is
    still written every time (telemetry contract)."""
    position = {"symbol": "XYZ", "qty": 100.0, "avg_entry_price": 10.0}
    pool, conn = _setup(db_rows=[], positions=[position], open_orders=[], dedup_hit=1)
    with patch(f"{MOD}.get_pool", new=AsyncMock(return_value=pool)), \
         patch(f"{MOD}.alpaca.get_all_positions", new=AsyncMock(return_value=[position])), \
         patch(f"{MOD}.alpaca.get_open_orders", new=AsyncMock(return_value=[])), \
         patch(f"{MOD}.log_audit_event", new=AsyncMock()) as audit, \
         patch(f"{MOD}.send_telegram_message", new=AsyncMock()) as tg:
        result = await detect_coverage_drift("paper")

    assert result["d1_count"] == 1
    assert result["alerted"] == 0
    assert result["deduped"] == 1
    tg.assert_not_called()

    # Detection row still written; no NEW alerted marker written (dedup found
    # an existing one via conn.fetchval, not via log_audit_event).
    event_types = [c.args[0] for c in audit.call_args_list]
    assert event_types.count(COVERAGE_DRIFT_DETECTED) == 1
    assert event_types.count(COVERAGE_DRIFT_ALERTED) == 0
    conn.fetchval.assert_called_once()


@pytest.mark.asyncio
async def test_degraded_broker_read_no_drift_reported():
    """alpaca.get_all_positions raises (raise_on_error=True path) -> degraded
    audit row only, no drift classes reported, no Telegram — an empty/failed
    broker read must never be interpreted as 'everything untracked' (#137)."""
    pool, conn = _setup()
    with patch(f"{MOD}.get_pool", new=AsyncMock(return_value=pool)), \
         patch(f"{MOD}.alpaca.get_all_positions", new=AsyncMock(side_effect=RuntimeError("503"))), \
         patch(f"{MOD}.alpaca.get_open_orders", new=AsyncMock(return_value=[])), \
         patch(f"{MOD}.log_audit_event", new=AsyncMock()) as audit, \
         patch(f"{MOD}.send_telegram_message", new=AsyncMock()) as tg:
        result = await detect_coverage_drift("paper")

    assert result["degraded"] is True
    assert result["d1_count"] == 0
    assert result["d2_high_count"] == 0
    assert result["d3_count"] == 0
    tg.assert_not_called()
    audit.assert_called_once()
    assert audit.call_args.args[0] == COVERAGE_DRIFT_CHECK_DEGRADED
    # Must not even reach the DB — conn.fetch (open DB trades query) untouched.
    conn.fetch.assert_not_called()


@pytest.mark.asyncio
async def test_degraded_db_read_no_drift_reported():
    """DB read (mi_live_trades open-trades query) raises -> degraded audit
    row only, no drift reported."""
    pool, conn = _setup()
    conn.fetch = AsyncMock(side_effect=RuntimeError("db down"))
    with patch(f"{MOD}.get_pool", new=AsyncMock(return_value=pool)), \
         patch(f"{MOD}.alpaca.get_all_positions", new=AsyncMock(return_value=[])), \
         patch(f"{MOD}.alpaca.get_open_orders", new=AsyncMock(return_value=[])), \
         patch(f"{MOD}.log_audit_event", new=AsyncMock()) as audit, \
         patch(f"{MOD}.send_telegram_message", new=AsyncMock()) as tg:
        result = await detect_coverage_drift("paper")

    assert result["degraded"] is True
    tg.assert_not_called()
    audit.assert_called_once()
    assert audit.call_args.args[0] == COVERAGE_DRIFT_CHECK_DEGRADED


@pytest.mark.asyncio
async def test_telegram_cap_rolls_overflow_into_one_summary():
    """d3 review: a mass-drift event (e.g. 6 untracked positions after an
    outage) sends only _TELEGRAM_CAP_PER_CYCLE individual alerts + ONE rollup
    line — never one message per ticker. Every detection still writes its own
    audit row, and rolled-up items still get their 24h dedup marker (the
    rollup IS their alert)."""
    from agents.market_intelligence.broker.coverage_drift import _TELEGRAM_CAP_PER_CYCLE

    positions = [
        {"symbol": f"TK{i}", "qty": 10.0, "avg_entry_price": 5.0} for i in range(6)
    ]
    pool, conn = _setup(db_rows=[], positions=positions, open_orders=[])
    with patch(f"{MOD}.get_pool", new=AsyncMock(return_value=pool)), \
         patch(f"{MOD}.alpaca.get_all_positions", new=AsyncMock(return_value=positions)), \
         patch(f"{MOD}.alpaca.get_open_orders", new=AsyncMock(return_value=[])), \
         patch(f"{MOD}.log_audit_event", new=AsyncMock()) as audit, \
         patch(f"{MOD}.send_telegram_message", new=AsyncMock()) as tg:
        result = await detect_coverage_drift("paper")

    assert result["d1_count"] == 6
    assert result["alerted"] == _TELEGRAM_CAP_PER_CYCLE
    assert result["overflowed"] == 6 - _TELEGRAM_CAP_PER_CYCLE
    # cap individual sends + exactly one rollup
    assert tg.call_count == _TELEGRAM_CAP_PER_CYCLE + 1
    rollup = tg.call_args_list[-1].args[0]
    assert "3 more" in rollup and "capped" in rollup

    event_types = [c.args[0] for c in audit.call_args_list]
    assert event_types.count(COVERAGE_DRIFT_DETECTED) == 6
    assert event_types.count(COVERAGE_DRIFT_ALERTED) == 6  # markers for ALL, incl. rolled-up
