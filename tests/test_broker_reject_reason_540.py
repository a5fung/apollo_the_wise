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

FIX SHAPE, and why not the obvious one: flipping the stream to `raw_data=True` would recover it,
but that rewrites every handler on the FILL path — the money path — to work on dicts, to obtain a
field needed only on a terminal failure. Instead a targeted lookup against the trade-events
history, called ONLY on reject/cancel/expire.
"""
import ast
import inspect
import pathlib

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
