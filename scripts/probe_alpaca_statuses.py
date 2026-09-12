"""#488 entitlement probe (originally #386, closed) — does OUR Alpaca data feed carry the
`statuses` channel?

STATUS: this probe already PASSED against SIP on 2026-07-25 (throwaway connection, operator-
approved, off-hours) — see PLAN.md #488. Kept for re-runs if the feed/entitlement ever changes;
do not re-run it as a gate on this merge.

The dead-data-guard shadow's capture (broker/halt_status_shadow.py) piggybacks the
trading-statuses subscription onto the SHARED bar stream — the connection that fires
real-money ORB entries. On a channel the feed subscription doesn't include, the SDK
TERMINATES the stream ("insufficient subscription" ValueError → `_run_forever` returns,
alpaca/data/live/websocket.py:352-356). This probe answers the entitlement question on a
THROWAWAY connection so the capture flag (HALT_STATUS_CAPTURE_ENABLED) is only ever
flipped on a proven feed.

RUN IT OFF-PROD, or while the market-agent's stream is disconnected (pre-boot / stream
not yet connected — it idles until the first morning EP-candidate subscribe): Alpaca
allows ONE concurrent data-stream connection per account+feed; a second is refused with
"connection limit exceeded" (which this probe reports as INCONCLUSIVE, not FAIL).

Usage:
    python scripts/probe_alpaca_statuses.py [--seconds 90]

Reads ALPACA_PAPER_API_KEY / ALPACA_PAPER_SECRET_KEY (or legacy ALPACA_API_KEY /
ALPACA_SECRET_KEY) and ALPACA_DATA_FEED (iex default — probe the SAME feed prod uses).

Verdicts:
    PASS          — statuses subscription acknowledged; stream alive for the full window.
    FAIL          — stream terminated on "insufficient subscription" (feed lacks the
                    channel → do NOT flip the capture flag on this feed).
    INCONCLUSIVE  — connection refused (limit) / auth error / other infra failure.

Halt events are rare — receiving zero events during the window is still a PASS (the ack +
stream survival are the entitlement evidence, not event traffic).
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("probe_alpaca_statuses")

_events: list = []
_sub_acked = asyncio.Event()


async def _on_status(status) -> None:
    _events.append(status)
    log.info(f"STATUS EVENT: {status}")


async def main(seconds: int) -> int:
    api_key = os.environ.get("ALPACA_PAPER_API_KEY") or os.environ.get("ALPACA_API_KEY")
    secret = os.environ.get("ALPACA_PAPER_SECRET_KEY") or os.environ.get("ALPACA_SECRET_KEY")
    if not api_key or not secret:
        log.error("INCONCLUSIVE — no Alpaca credentials in env")
        return 2

    from alpaca.data.live import StockDataStream
    from alpaca.data.enums import DataFeed

    feed_name = os.environ.get("ALPACA_DATA_FEED", "iex").lower()
    feed = DataFeed.SIP if feed_name == "sip" else DataFeed.IEX
    log.info(f"Probing feed={feed.value} for the `statuses` channel ({seconds}s window)...")

    # Surface the SDK's own logs — the subscription ack ("subscribed to statuses: ['*']")
    # and any "insufficient subscription" termination arrive through them.
    class _AckWatcher(logging.Handler):
        def emit(self, record):
            msg = record.getMessage()
            if "subscribed to" in msg and "statuses" in msg:
                _sub_acked.set()

    sdk_log = logging.getLogger("alpaca.data.live.websocket")
    sdk_log.setLevel(logging.INFO)
    sdk_log.addHandler(_AckWatcher())

    stream = StockDataStream(api_key, secret, feed=feed)
    stream.subscribe_trading_statuses(_on_status, "*")

    task = asyncio.create_task(stream._run_forever())
    done, _ = await asyncio.wait({task}, timeout=seconds)

    if task in done:
        # _run_forever RETURNED inside the window — the insufficient-subscription
        # termination path (or another fatal error; the SDK logged which just above).
        exc = task.exception()
        log.error(
            "FAIL — stream terminated inside the probe window "
            f"(exception={exc!r}). If the log shows 'insufficient subscription', feed "
            f"'{feed.value}' does NOT carry `statuses`: do NOT flip HALT_STATUS_CAPTURE_ENABLED. "
            "If it shows 'connection limit exceeded', treat as INCONCLUSIVE and re-run "
            "while the market-agent stream is down."
        )
        return 1

    acked = _sub_acked.is_set()
    task.cancel()
    try:
        await task
    except (asyncio.CancelledError, Exception):
        pass

    if acked:
        log.info(
            f"PASS — statuses subscription acknowledged on feed '{feed.value}'; stream "
            f"survived {seconds}s; {len(_events)} event(s) received (zero is normal). "
            "Safe to flip HALT_STATUS_CAPTURE_ENABLED=true (operator action)."
        )
        return 0
    log.warning(
        f"INCONCLUSIVE — stream survived {seconds}s but no subscription ack was observed "
        "in the SDK logs. Check connectivity/credentials and re-run."
    )
    return 2


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--seconds", type=int, default=90)
    sys.exit(asyncio.run(main(p.parse_args().seconds)))
