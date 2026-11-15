"""Research market data — the READ-ONLY bars fetch behind `POST /data/bars` (2026-11-15).

WHY. Since the live cutover the Alpaca keys live only in apollo-execution; the market-agent
container has them blanked (creds isolation), so a research script run with
`docker exec apollo-market python ...` cannot read Alpaca market data. This module is the one
sanctioned read path: apollo-execution fetches historical bars and hands them back as JSON.
The market-container side is `agents/market_intelligence/research_data.py::fetch_bars`.

READ-ONLY BY CONSTRUCTION — pinned by `tests/test_research_bars.py` (AST):
  * no `alpaca.trading` import; no order / position / account call;
  * the only name taken from `alpaca_client` is `_get_data_client` (the
    StockHistoricalDataClient singleton, paper data creds, no account or billing implication);
  * the only method called on that client is `get_stock_bars`.

ISOLATION FROM THE MONEY PATH. alpaca-py sets no HTTP timeout, so a hung page keeps its thread.
The fetch therefore runs on ITS OWN one-thread executor — never `_sdk`'s shared pool (live order
calls queue there) and never the breakout v1 batch executor (its in-flight flag is single-caller;
a research page on it would make the entry tick skip). SINGLE-FLIGHT: while a page is still on the
thread the next request is refused (429 `busy`), so research can hold one thread and nothing more.

The caps and the request-error type live in `execution_client` (the seam both services load), so
the client-side paging in `research_data.py` cannot drift from what this module enforces.
"""
from __future__ import annotations

import asyncio
import concurrent.futures
import json
import logging
import re
from datetime import datetime, timedelta, timezone

from alpaca.data.enums import Adjustment, DataFeed
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame, TimeFrameUnit

from agents.market_intelligence.broker.alpaca_client import _get_data_client
from agents.market_intelligence.execution_client import (
    RESEARCH_BARS_MAX_RANGE_DAYS,
    RESEARCH_BARS_MAX_ROWS,
    RESEARCH_BARS_MAX_SYMBOLS,
    ResearchBarsRequestError,
    get_data_feed_name,
)

logger = logging.getLogger(__name__)

RESEARCH_BARS_TIMEOUT_S = 120.0     # a hang breaker for one request (up to RESEARCH_BARS_MAX_ROWS rows, ~10k per page)
RESEARCH_BARS_THREAD_PREFIX = "alpaca-research-bars"

_TIMEFRAMES = {
    "1Min": TimeFrame(1, TimeFrameUnit.Minute),
    "5Min": TimeFrame(5, TimeFrameUnit.Minute),
    "15Min": TimeFrame(15, TimeFrameUnit.Minute),
    "1Hour": TimeFrame(1, TimeFrameUnit.Hour),
    "1Day": TimeFrame(1, TimeFrameUnit.Day),
}
_FEEDS = {"iex": DataFeed.IEX, "sip": DataFeed.SIP}
_ADJUSTMENTS = {"raw": Adjustment.RAW, "split": Adjustment.SPLIT,
                "dividend": Adjustment.DIVIDEND, "all": Adjustment.ALL}
_SYMBOL_RE = re.compile(r"^[A-Z0-9][A-Z0-9.\-]{0,11}$")

_EXECUTOR = concurrent.futures.ThreadPoolExecutor(max_workers=1, thread_name_prefix=RESEARCH_BARS_THREAD_PREFIX)
_page: concurrent.futures.Future | None = None   # the last fetch submitted; not done = the thread is still inside alpaca-py


def research_bars_in_flight() -> bool:
    """True while the last research fetch has not returned from alpaca-py (its `wait_for` budget may
    already have fired — the THREAD is what is busy)."""
    page = _page
    return page is not None and not page.done()


def _bad(code: str, message: str) -> ResearchBarsRequestError:
    return ResearchBarsRequestError(400, code, message)


def _parse_ts(name: str, raw) -> datetime:
    if not isinstance(raw, str) or not raw.strip():
        raise _bad("bad_time", f"{name} must be an ISO-8601 string with a timezone, e.g. 2026-11-13T09:30:00-05:00")
    text = raw.strip()
    if text.endswith(("Z", "z")):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        raise _bad("bad_time", f"{name}={raw!r} is not ISO-8601") from None
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise _bad("naive_time", f"{name}={raw!r} carries no timezone — send an offset (e.g. -05:00) or Z")
    return dt.astimezone(timezone.utc)


def validate_request(payload) -> dict:
    """PURE. The request body -> a normalised dict (feed / adjustment as their lowercase NAMES), or `ResearchBarsRequestError` (400) naming the violation."""
    if not isinstance(payload, dict):
        raise _bad("bad_body", "body must be a JSON object")
    unknown = set(payload) - {"symbols", "timeframe", "start", "end", "feed", "adjustment"}
    if unknown:
        raise _bad("unknown_field", f"unknown field(s): {sorted(unknown)}")

    raw_symbols = payload.get("symbols")
    if not isinstance(raw_symbols, list) or not raw_symbols:
        raise _bad("bad_symbols", "symbols must be a non-empty list of tickers")
    symbols: list[str] = []
    for s in raw_symbols:
        sym = s.strip().upper() if isinstance(s, str) else ""
        if not _SYMBOL_RE.match(sym):
            raise _bad("bad_symbols", f"not a stock/ETF ticker: {s!r}")
        if sym not in symbols:
            symbols.append(sym)
    if len(symbols) > RESEARCH_BARS_MAX_SYMBOLS:
        raise _bad("too_many_symbols", f"{len(symbols)} symbols; the limit is {RESEARCH_BARS_MAX_SYMBOLS} per call")

    timeframe = payload.get("timeframe")
    if timeframe not in _TIMEFRAMES:
        raise _bad("bad_timeframe", f"timeframe={timeframe!r}; allowed: {list(_TIMEFRAMES)}")

    start = _parse_ts("start", payload.get("start"))
    end = _parse_ts("end", payload.get("end"))
    if end <= start:
        raise _bad("bad_range", "end must be after start")
    max_days = RESEARCH_BARS_MAX_RANGE_DAYS[timeframe]
    if end - start > timedelta(days=max_days):
        raise _bad("range_too_long",
                   f"{timeframe} allows at most {max_days} calendar days per call "
                   f"(asked {(end - start).total_seconds() / 86400:.1f}); page over the range")

    feed_raw = payload.get("feed")
    if feed_raw is None:
        feed = get_data_feed_name()          # the configured ALPACA_DATA_FEED ('iex' / 'sip')
    elif isinstance(feed_raw, str) and feed_raw.strip().lower() in _FEEDS:
        feed = feed_raw.strip().lower()
    else:
        raise _bad("bad_feed", f"feed={feed_raw!r}; allowed: {list(_FEEDS)} (omit for the configured feed)")

    adj_raw = payload.get("adjustment")
    if adj_raw is None:
        adjustment = "raw"
    elif isinstance(adj_raw, str) and adj_raw.strip().lower() in _ADJUSTMENTS:
        adjustment = adj_raw.strip().lower()
    else:
        raise _bad("bad_adjustment", f"adjustment={adj_raw!r}; allowed: {list(_ADJUSTMENTS)}")

    return {"symbols": symbols, "timeframe": timeframe, "start": start, "end": end,
            "feed": feed, "adjustment": adjustment}


def _num(x):
    f = float(x)
    return int(f) if f.is_integer() else f


def _fetch_body(client, req: dict) -> bytes:
    """Runs ON the research thread, start to finish: one SDK call (the SDK pages inside it, capped by
    `limit`), the bar -> dict conversion AND the JSON encoding — so a 50,000-row answer costs the
    execution event loop nothing but handing the bytes back. Rows are HALF-OPEN on time:
    start <= ts < end.

    The row cap is judged on what Alpaca RETURNED, before the half-open filter: Alpaca's `end` is
    inclusive, so a fetch cut off at cap+1 that holds a bar exactly on `end` would otherwise filter
    back under the cap and pass as complete with the later symbols missing."""
    request = StockBarsRequest(
        symbol_or_symbols=req["symbols"],
        timeframe=_TIMEFRAMES[req["timeframe"]],
        start=req["start"],
        end=req["end"],
        feed=_FEEDS[req["feed"]],
        adjustment=_ADJUSTMENTS[req["adjustment"]],
        limit=RESEARCH_BARS_MAX_ROWS + 1,   # one past the cap: "more than the cap" is detectable without fetching it all
    )
    bars = client.get_stock_bars(request)
    data = bars.data if hasattr(bars, "data") else bars
    fetched = sum(len(data.get(sym, []) or []) for sym in req["symbols"])
    if fetched > RESEARCH_BARS_MAX_ROWS:
        raise _bad("row_cap", f"more than {RESEARCH_BARS_MAX_ROWS} rows; ask for a shorter range or fewer symbols")
    rows: list[dict] = []
    for sym in req["symbols"]:
        for b in data.get(sym, []) or []:
            if b.timestamp is None:
                continue
            ts = b.timestamp.astimezone(timezone.utc)
            if not (req["start"] <= ts < req["end"]):
                continue
            rows.append({"symbol": sym, "ts": ts.isoformat(),
                         "o": float(b.open), "h": float(b.high), "l": float(b.low), "c": float(b.close),
                         "v": _num(b.volume)})
    rows.sort(key=lambda r: (r["symbol"], r["ts"]))
    return json.dumps({
        "bars": rows, "count": len(rows), "symbols": req["symbols"], "timeframe": req["timeframe"],
        "feed": req["feed"], "adjustment": req["adjustment"],
        "start": req["start"].isoformat(), "end": req["end"].isoformat(),
    }, separators=(",", ":")).encode("utf-8")


async def fetch_research_bars(payload) -> bytes:
    """The whole `POST /data/bars` body, as encoded JSON: {"bars": [...], "count", "symbols",
    "timeframe", "feed", "adjustment", "start", "end"}; raises `ResearchBarsRequestError` carrying the
    HTTP status: 400 (a named request violation, incl. `row_cap`), 429 (`busy`), 502 (`upstream`),
    504 (`timeout`)."""
    global _page
    req = validate_request(payload)
    if research_bars_in_flight():
        raise ResearchBarsRequestError(429, "busy", "a research bars request is still running; retry shortly")
    try:
        client = _get_data_client()
        _page = page = _EXECUTOR.submit(_fetch_body, client, req)
        return await asyncio.wait_for(asyncio.wrap_future(page), RESEARCH_BARS_TIMEOUT_S)
    except ResearchBarsRequestError:
        raise                                   # the row cap, judged on the research thread
    except (asyncio.TimeoutError, TimeoutError):
        logger.error(f"research bars: no answer in {RESEARCH_BARS_TIMEOUT_S:.0f}s "
                     f"({len(req['symbols'])} symbols, {req['timeframe']}) — the research thread stays busy until "
                     f"alpaca-py returns; requests until then get 429")
        raise ResearchBarsRequestError(504, "timeout",
                                       f"Alpaca did not answer in {RESEARCH_BARS_TIMEOUT_S:.0f}s") from None
    except Exception as e:  # loud-ok: logged and re-shaped into a 502 the caller sees with the upstream message
        logger.error(f"research bars: upstream failure {type(e).__name__}: {e}")
        raise ResearchBarsRequestError(502, "upstream", f"{type(e).__name__}: {str(e)[:500]}") from e
