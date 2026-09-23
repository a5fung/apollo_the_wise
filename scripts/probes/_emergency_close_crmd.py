"""One-shot emergency: place stop-market SELL on CRMD at the intended stop.

CRMD entry filled 2026-05-14 09:34:40 ET. WS _process_entry_fill UPDATE
failed with AmbiguousParameterError (numeric vs double precision on $2),
preventing the OTO stop from activating. Stop was canceled at broker
09:34:41. Position has been naked since.

Submitting a stop SELL at $8.45 (the original intended stop, already
breached) — triggers immediately under current ~$7.93 market.
"""
from agents.market_intelligence.broker.alpaca_client import get_trading_client
from agents.market_intelligence.agent import _bootstrap_alpaca_credentials
from alpaca.trading.requests import MarketOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce


def main() -> None:
    _bootstrap_alpaca_credentials()
    tc = get_trading_client("paper")

    pos = tc.get_open_position("CRMD")
    print(f"Pre-submit: qty={pos.qty} current={pos.current_price} unrealized_pl={pos.unrealized_pl}")

    # Market SELL — stop was already breached; closes at current.
    order = tc.submit_order(MarketOrderRequest(
        symbol="CRMD",
        qty=int(pos.qty),
        side=OrderSide.SELL,
        time_in_force=TimeInForce.DAY,
    ))
    print(f"Market SELL submitted: id={order.id} qty={order.qty} status={order.status}")


if __name__ == "__main__":
    main()
