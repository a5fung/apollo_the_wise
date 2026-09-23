"""#540: keep Alpaca's OWN WORDS at the trade-stream parse point.

Alpaca delivers the reason it killed an order INSIDE the trade-updates event,
beside the order — `"reason": "[6098] Stop Price Already Triggered/Exceeds $
Threshold"` (INSM 2026-08-06, a live rejection on a stock that ran +33%),
`"Unsolicited: Bad Stop 19.8"` (QNST 2026-08-07). The SDK's `TradeUpdate`
model declares no `reason` field, so with raw_data=False pydantic silently
DROPS it at `TradingStream._cast` — the reason arrived on every rejection we
ever had and was discarded before our handler ran.

The REST events-history lookup that shipped first (`fetch_broker_reject_reason`)
races Alpaca's indexing: on QNST it returned NULL 76ms after the cancel while
the identical query by hand, minutes later, returned the reason immediately.
The event itself is the only race-free source — so capture it where the event
is parsed.

This is a LEAF module on purpose: it imports only the SDK + pydantic, so tests
can import it against the REAL alpaca-py (the conftest stubs the SDK for
everything else) and prove the reason survives the real pydantic parse — the
live mechanism, not a lookalike.
"""
from __future__ import annotations

import logging

from alpaca.trading.models import TradeUpdate
from alpaca.trading.stream import TradingStream
from pydantic import ConfigDict

logger = logging.getLogger(__name__)


class TradeUpdateWithBrokerFields(TradeUpdate):
    """TradeUpdate that KEEPS undeclared keys (extra="allow") instead of
    dropping them — `reason` on rejects/cancels, plus anything Alpaca adds
    later. Still a TradeUpdate: downstream handlers see the exact same declared
    fields; extras ride along as attributes and are never validated, so a
    weird extra value cannot fail the parse."""

    model_config = ConfigDict(extra="allow", validate_assignment=True)


class ReasonPreservingTradingStream(TradingStream):
    """Overrides the SDK's exact drop point (`_cast`). raw_data stays False —
    the fill path keeps receiving parsed models, NOT dicts (the rejected
    alternative, raw_data=True, would rewrite every money-path handler to
    recover a field needed only on terminal failures). Fail-open: ANY problem
    in our parse falls back to the SDK's own, so this shim can never lose or
    delay an event."""

    def _cast(self, msg):
        if not self._raw_data:
            try:
                return TradeUpdateWithBrokerFields(**(msg.get("data") or {}))
            except Exception as e:  # loud-ok: SDK parse below is the fallback
                logger.warning(
                    f"reason-preserving parse failed, using SDK parse: {e}"
                )
        return super()._cast(msg)
