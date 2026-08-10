"""Alpaca tells us WHY it killed an order — capture it (2026-08-06, INSM).

⚠ WHAT THIS COST. INSM, 2026-08-06: a live entry rejected 3.4ms after submit on a stock that
then ran +33%. Diagnosing it took hours of inference across the order object, the REST payload,
account state, asset flags and a paper probe — and the answer was in Alpaca's payload the whole
time, one field away:

    "reason": "[6098] Stop Price Already Triggered/Exceeds $ Threshold"

WHERE IT HIDES, and why it was missed:
  * NOT on the order object — confirmed across every key of the raw REST response.
  * It is on the trade-updates EVENT, beside the order.
  * The SDK's `TradeUpdate` model has NO `reason` field (event/execution_id/order/timestamp/
    position_qty/price/qty). With `raw_data=False` pydantic drops it before our handler runs.

So the reason arrived on every rejection we ever had, and we discarded all of them.

FIX SHAPE — two layers, and why not the obvious one. Flipping the stream to `raw_data=True`
would recover the field, but that rewrites every handler on the FILL path — the money path — to
work on dicts, to obtain a field needed only on a terminal failure.
  1. PRIMARY (2026-08-10): capture at the parse point. The stream parses into
     `TradeUpdateWithBrokerFields` (extra="allow"), so the `reason` delivered INSIDE the event
     survives — race-free, zero extra latency, raw_data stays False. This exists because the
     lookup-only design FAILED its first live firing: QNST 2026-08-07 was cancelled with
     "Unsolicited: Bad Stop 19.8" on the stream, and the inline REST lookup 76ms later got NULL
     — Alpaca's events history had not indexed an event that recent.
  2. FALLBACK: the targeted lookup against the trade-events history, called ONLY on
     reject/cancel/expire, plus a late background re-ask — kept for events that arrive without
     the field or when the parse fell back to the SDK model.
"""
import ast
import inspect
import json
import pathlib
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

STREAM = pathlib.Path("agents/market_intelligence/broker/trade_stream.py").read_text()
CLIENT = pathlib.Path("agents/market_intelligence/broker/alpaca_client.py").read_text()


def test_the_helper_exists_and_never_raises():
    """A diagnostic must not be able to break the rejection handling it diagnoses."""
    from agents.market_intelligence.broker.alpaca_client import fetch_broker_reject_reason
    src = inspect.getsource(fetch_broker_reject_reason)
    assert "except Exception" in src
    assert "return None" in src


def test_it_matches_the_reason_to_the_RIGHT_order():
    """The events window contains every order in that second — RDW's accepted events sat beside
    INSM's rejection. Returning the first reason found would attribute another order's failure."""
    from agents.market_intelligence.broker.alpaca_client import fetch_broker_reject_reason
    src = inspect.getsource(fetch_broker_reject_reason)
    assert 'ev.get("order") or {}' in src and "order_id" in src


def test_it_uses_the_modules_own_credential_resolution():
    """A second credential path is how a paper key ends up querying the live account."""
    from agents.market_intelligence.broker.alpaca_client import fetch_broker_reject_reason
    src = inspect.getsource(fetch_broker_reject_reason)
    assert "_resolve_account_mode" in src and "_require_alpaca_env" in src
    assert "paper-api.alpaca.markets" in src, "paper must not query the live endpoint"


def test_it_is_called_ONLY_on_terminal_failure_events():
    """Never on a fill. The fill path is the money path and must not gain an API call."""
    i = STREAM.index("fetch_broker_reject_reason")
    guard = STREAM[max(0, i - 400):i]
    assert "rejected" in guard and "expired" in guard
    assert "fill" not in guard.split("if event_norm")[-1]


def test_the_reason_is_recorded_DURABLY_and_reaches_the_operator():
    """An audit row nobody reads is not the fix — INSM sat unexplained for hours."""
    assert '"broker_reason": broker_reason,' in STREAM, "must land in the audit detail"
    assert "reason_line" in STREAM, "must reach the Telegram"
    i = STREAM.index("reason_line = ")
    assert "if broker_reason else" in STREAM[i:i + 200], "absent reason must degrade silently"


def test_the_synthesised_diagnosis_is_kept_alongside_it_not_replaced():
    """`skip_reason` is OUR inference and stays — it is what humanize() renders and what the
    skip vocabulary is built on. The broker reason is added beside it, never instead of it."""
    i = STREAM.index('"broker_reason": broker_reason,')
    # the two keys are adjacent in the dict but separated by a long explanatory comment block,
    # so the window is generous on purpose — this asserts co-existence, not proximity.
    assert '"skip_reason": skip_reason' in STREAM[max(0, i - 1600):i]


def test_the_stream_still_parses_events_the_same_way():
    """Pinning the decision NOT to flip raw_data — if someone flips it later, every handler on
    the fill path changes shape and this test should force that to be deliberate."""
    assert "raw_data=False" in STREAM


# ─── Parse-point capture (#540 primary, 2026-08-10) ─────────────────────────
#
# The envelope shape Alpaca ACTUALLY sends on the trade-updates stream — the
# reason sits in `data`, BESIDE the order, exactly where the recovered INSM and
# QNST events had it. The order sub-dict carries every field the SDK's Order
# model requires, so these parse through the real pydantic path, not a stub.
#
# ⚠ REAL SDK ON PURPOSE. conftest.py stubs `alpaca.*` with MagicMocks for the
# whole suite, but the defect IS the SDK's pydantic parse dropping the field —
# a stub cannot drop anything, so a stubbed test would "pass" without the fix
# (the exact false-clear trap from the 8/07 verify failure). The fixture below
# imports the leaf module `stream_models` against the REAL alpaca-py
# (pinned in requirements/base.txt, installed in CI) and restores the stubs
# afterwards, so the rest of the suite is untouched.

_STREAM_MODELS = "agents.market_intelligence.broker.stream_models"


@pytest.fixture
def real_models():
    """Yield `stream_models` imported against the REAL alpaca-py."""
    import importlib
    import sys

    def _alpaca_keys():
        return [k for k in sys.modules
                if k == "alpaca" or k.startswith("alpaca.") or k == _STREAM_MODELS]

    saved = {k: sys.modules[k] for k in _alpaca_keys()}
    for k in saved:
        del sys.modules[k]
    try:
        try:
            mod = importlib.import_module(_STREAM_MODELS)
        except Exception:
            pytest.skip("real alpaca-py not installed")
        if not hasattr(mod.TradeUpdateWithBrokerFields, "model_fields"):
            pytest.skip("real alpaca-py not installed (stub resolved instead)")
        yield mod
    finally:
        for k in _alpaca_keys():
            del sys.modules[k]
        sys.modules.update(saved)


_INSM_REASON = "[6098] Stop Price Already Triggered/Exceeds $ Threshold"
_QNST_REASON = "Unsolicited: Bad Stop 19.8"


def _order_payload(**over):
    base = {
        "id": "3fb6dc01-8e3a-4c9f-9d5e-000000000540",
        "client_order_id": "live-insm-20260806-x1",
        "created_at": "2026-08-06T13:31:11.892606Z",
        "updated_at": "2026-08-06T13:31:11.896Z",
        "submitted_at": "2026-08-06T13:31:11.892606Z",
        "failed_at": "2026-08-06T13:31:11.896Z",
        "asset_id": "b0b6dd9d-8b9b-48a9-ba46-b9d54906e415",
        "symbol": "INSM",
        "asset_class": "us_equity",
        "qty": "7",
        "filled_qty": "0",
        "order_class": "oto",
        "type": "stop_limit",
        "side": "buy",
        "time_in_force": "day",
        "limit_price": "130.06",
        "stop_price": "129.41",
        "status": "rejected",
        "extended_hours": False,
    }
    base.update(over)
    return base


def _insm_envelope():
    """INSM 2026-08-06 — the rejection that started #540."""
    return {
        "stream": "trade_updates",
        "data": {
            "event": "rejected",
            "timestamp": "2026-08-06T13:31:11.896Z",
            "reason": _INSM_REASON,
            "order": _order_payload(),
        },
    }


def _qnst_envelope():
    """QNST 2026-08-07 — the venue CANCEL the lookup-only design missed live."""
    return {
        "stream": "trade_updates",
        "data": {
            "event": "canceled",
            "timestamp": "2026-08-07T13:31:10.777Z",
            "reason": _QNST_REASON,
            "order": _order_payload(
                id="7ab2ec44-1f2b-4d31-a2c7-000000000541",
                client_order_id="live-qnst-20260807-x1",
                symbol="QNST",
                created_at="2026-08-07T13:31:10.700Z",
                updated_at="2026-08-07T13:31:10.777Z",
                submitted_at="2026-08-07T13:31:10.700Z",
                failed_at=None,
                canceled_at="2026-08-07T13:31:10.777Z",
                limit_price="20.35",
                stop_price="20.10",
                status="canceled",
            ),
        },
    }


def _mk_stream(mod):
    return mod.ReasonPreservingTradingStream(
        api_key="k", secret_key="s", paper=True, raw_data=False)


def test_FAILS_WITHOUT_FIX_the_sdk_parse_drops_the_reason(real_models):
    """The defect itself, pinned: the bare SDK stream parses the real INSM envelope and the
    reason is GONE before any handler runs. If alpaca-py ever adds the field, this flips —
    telling us the shim is removable."""
    import sys
    sdk_stream_mod = sys.modules["alpaca.trading.stream"]  # the REAL one (fixture active)
    sdk_stream = sdk_stream_mod.TradingStream(
        api_key="k", secret_key="s", paper=True, raw_data=False)
    parsed = sdk_stream._cast(_insm_envelope())
    assert getattr(parsed, "reason", None) is None, (
        "SDK now preserves `reason` — the parse-point shim may be removable"
    )


def test_our_stream_preserves_the_reason_at_the_parse_point(real_models):
    """Same envelope, our stream: the reason survives AND the model is still a TradeUpdate —
    every downstream handler sees the same declared fields."""
    import sys
    parsed = _mk_stream(real_models)._cast(_insm_envelope())
    assert parsed.reason == _INSM_REASON
    assert isinstance(parsed, sys.modules["alpaca.trading.models"].TradeUpdate)
    assert parsed.order.symbol == "INSM"
    assert str(parsed.event) == "rejected"


def test_cancel_events_keep_their_reason_too(real_models):
    """Generalises past `rejected`: QNST was a venue CANCEL, the exact live shape the
    lookup-only design returned NULL on."""
    parsed = _mk_stream(real_models)._cast(_qnst_envelope())
    assert parsed.reason == _QNST_REASON
    assert str(parsed.event) == "canceled"


def test_absent_reason_parses_fine_and_degrades_to_none(real_models):
    """Most events (fills, accepts) carry no reason — they must parse identically."""
    env = _insm_envelope()
    del env["data"]["reason"]
    parsed = _mk_stream(real_models)._cast(env)
    assert getattr(parsed, "reason", None) is None
    assert parsed.order.symbol == "INSM"


def test_parse_failure_falls_back_to_the_sdk_parse(real_models, monkeypatch):
    """Fail-open: if OUR model ever diverges and raises, the event still arrives via the SDK's
    own parse — the shim can never lose an event."""
    import sys
    stream = _mk_stream(real_models)

    def _boom(**kw):
        raise ValueError("subclass parse broken")

    monkeypatch.setattr(real_models, "TradeUpdateWithBrokerFields", _boom)
    parsed = stream._cast(_insm_envelope())
    assert type(parsed) is sys.modules["alpaca.trading.models"].TradeUpdate
    assert parsed.order.symbol == "INSM"


def test_the_live_streams_are_built_reason_preserving():
    """_start_one_stream must construct the subclass — a bare TradingStream() there silently
    reverts the capture to lookup-only."""
    i = STREAM.index("def _start_one_stream")
    body = STREAM[i:STREAM.index("async def _run_stream_with_monitoring")]
    assert "ReasonPreservingTradingStream(" in body
    assert "TradingStream(\n" not in body.replace("ReasonPreservingTradingStream(\n", "")


# ─── The reason reaches the handler, the audit row and the operator ─────────


_INSM_ROW = {
    "id": 9, "ticker": "INSM", "gap_pct": 8.2, "ep_score": 74.0,
    "entry_price": 129.41, "stop_price": 126.15,
    "regime": "Uptrend", "signal_type": "magna53",
}


async def _run_reject(monkeypatch, data, event: str, entry_row=None,
                      lookup_returns=None):
    """Drive _handle_cancel_or_reject with the DB, audit, Telegram and REST
    lookup all captured. Returns (sent, audit, lookup)."""
    import agents.market_intelligence.broker.order_manager as om
    import agents.market_intelligence.broker.trade_stream as ts
    from tests.conftest import make_mock_pool

    pool, conn = make_mock_pool()
    conn.fetchrow = AsyncMock(
        return_value=dict(entry_row) if entry_row is not None else None)
    conn.execute = AsyncMock()
    monkeypatch.setattr(ts, "get_pool", AsyncMock(return_value=pool))
    audit = AsyncMock()
    monkeypatch.setattr(ts, "log_audit_event", audit)
    # broker_terminal_reason's price fetch — never touch the network.
    monkeypatch.setattr(
        om, "alpaca", MagicMock(get_latest_trade=AsyncMock(return_value=None)),
    )
    lookup = AsyncMock(return_value=lookup_returns)
    monkeypatch.setattr(ts.alpaca, "fetch_broker_reject_reason", lookup)
    # The late re-ask must never fire in these tests — if it is scheduled the
    # inline sources both failed, which is itself the assertion failure.
    monkeypatch.setattr(
        ts.alpaca, "fetch_broker_reject_reason_later", AsyncMock(return_value=None),
    )

    sent: list[str] = []

    async def _capture(msg, *a, **k):
        sent.append(msg)
        return True

    monkeypatch.setattr(ts, "send_telegram_message", _capture)
    await ts._handle_cancel_or_reject(data, event, "live")
    return sent, audit, lookup


def _audit_ctx(audit):
    from agents.market_intelligence.audit_events import ENTRY_ORDER_REJECTED
    calls = [c for c in audit.await_args_list if c.args[0] == ENTRY_ORDER_REJECTED]
    assert len(calls) == 1
    return json.loads(calls[0].args[2])


@pytest.mark.asyncio
async def test_event_reason_lands_in_audit_and_telegram_with_NO_lookup(
        real_models, monkeypatch):
    """End-to-end through the REAL parse: the INSM envelope goes through our stream's _cast,
    into the handler, and Alpaca's words land in the audit row AND the operator Telegram —
    with the REST lookup never called. The race is eliminated, not retried around."""
    data = _mk_stream(real_models)._cast(_insm_envelope())
    sent, audit, lookup = await _run_reject(
        monkeypatch, data, "rejected", entry_row=_INSM_ROW)

    ctx = _audit_ctx(audit)
    assert ctx["broker_reason"] == _INSM_REASON
    assert ctx["broker_reason_source"] == "event"
    assert any(_INSM_REASON in m for m in sent), "operator must see Alpaca's words"
    lookup.assert_not_awaited()


@pytest.mark.asyncio
async def test_qnst_shape_a_venue_cancel_now_carries_its_reason(
        real_models, monkeypatch):
    """The exact live shape that produced broker_reason=null on 2026-08-07."""
    data = _mk_stream(real_models)._cast(_qnst_envelope())
    row = dict(_INSM_ROW, ticker="QNST", entry_price=20.35, stop_price=20.10)
    sent, audit, lookup = await _run_reject(
        monkeypatch, data, "canceled", entry_row=row)

    ctx = _audit_ctx(audit)
    assert ctx["broker_reason"] == _QNST_REASON
    assert ctx["broker_reason_source"] == "event"
    assert any(_QNST_REASON in m for m in sent)
    lookup.assert_not_awaited()


@pytest.mark.asyncio
async def test_event_without_reason_still_falls_back_to_the_lookup(monkeypatch):
    """The shipped REST path is kept as the fallback — an event arriving without the field
    (or via the SDK-parse fallback) still gets one inline lookup attempt."""
    data = SimpleNamespace(order=SimpleNamespace(id="ord-x-1", symbol="QNST"))
    sent, audit, lookup = await _run_reject(
        monkeypatch, data, "canceled", entry_row=dict(_INSM_ROW, ticker="QNST"),
        lookup_returns=_QNST_REASON)

    ctx = _audit_ctx(audit)
    assert ctx["broker_reason"] == _QNST_REASON
    assert ctx["broker_reason_source"] == "lookup"
    lookup.assert_awaited_once()


@pytest.mark.asyncio
async def test_untracked_rejection_telegram_carries_the_reason(
        real_models, monkeypatch):
    """No matching trade row anywhere (manual/margin/PDT rejection) — the operator alert
    still says WHY instead of only 'check logs'."""
    data = _mk_stream(real_models)._cast(_insm_envelope())
    sent, _, _ = await _run_reject(monkeypatch, data, "rejected", entry_row=None)

    assert any("Order REJECTED" in m and _INSM_REASON in m for m in sent)
