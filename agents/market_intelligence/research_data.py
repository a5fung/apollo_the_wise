"""Research market data from the MARKET container — `fetch_bars` (2026-11-15).

The Alpaca keys live only in apollo-execution, so a research script run with
`docker exec apollo-market python ...` cannot call Alpaca itself. This helper asks
apollo-execution's READ-ONLY `POST /data/bars` route instead and stitches the pages:

    docker exec apollo-market python -c "
    from agents.market_intelligence.research_data import fetch_bars
    df = fetch_bars(['SPY', 'TLT'], '1Min', '2026-11-09T09:30:00-05:00', '2026-11-13T16:00:00-05:00')
    print(df.head())"

Reads market data only: it knows one URL (`/data/bars`) and imports no broker module
(pinned by tests/test_research_bars.py). Contract + caps: docs/architecture/dual_account.md
§Research market data. Synchronous on purpose — it is for scripts, not for the service loop.
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone

from agents.market_intelligence.execution_client import (
    RESEARCH_BARS_MAX_RANGE_DAYS,
    RESEARCH_BARS_MAX_SYMBOLS,
    ExecutionUnreachable,
    ResearchBarsRequestError,
)

logger = logging.getLogger(__name__)

PAUSE_SECONDS = 0.4            # between pages — research shares Alpaca's rate limit with the live data reads
MAX_ATTEMPTS = 5               # per page, for busy / upstream / transport failures
BACKOFF_BASE_SECONDS = 2.0     # 2, 4, 8, 16
_CONNECT_TIMEOUT_SECONDS = 5.0
_READ_TIMEOUT_SECONDS = 150.0  # above the route's own 120s Alpaca budget
_MIN_CHUNK = timedelta(minutes=30)
_RETRY_STATUSES = frozenset({429, 500, 502, 503, 504})
ORB_WINDOW_CODE = "orb_window"  # the route's 429 for 09:20-10:05 ET weekdays: never retried (fail fast)

_sleep = time.sleep            # tests replace this


def _as_utc(name: str, value) -> datetime:
    if isinstance(value, str):
        text = value.strip()
        if text.endswith(("Z", "z")):
            text = text[:-1] + "+00:00"
        value = datetime.fromisoformat(text)
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be a timezone-aware datetime or ISO string (got {value!r})")
    return value.astimezone(timezone.utc)


def _service_url() -> str:
    """The apollo-execution base URL, or a loud config error (never retried)."""
    from agents.market_intelligence.constants import EXECUTION_SERVICE_URL
    if not EXECUTION_SERVICE_URL:
        raise RuntimeError(
            "EXECUTION_SERVICE_URL is unset — fetch_bars must run where apollo-execution is "
            "reachable (e.g. docker exec apollo-market ...)")
    return EXECUTION_SERVICE_URL


def _post(body: dict) -> dict:
    """ONE `POST /data/bars`. -> the response dict; raises `ResearchBarsRequestError` for any
    non-200 answer and `ExecutionUnreachable` when the service could not be reached."""
    import httpx

    from shared.secrets import get_secrets

    base_url = _service_url()
    timeout = httpx.Timeout(connect=_CONNECT_TIMEOUT_SECONDS, read=_READ_TIMEOUT_SECONDS,
                            write=_CONNECT_TIMEOUT_SECONDS, pool=_CONNECT_TIMEOUT_SECONDS)
    try:
        resp = httpx.post(
            f"{base_url}/data/bars", json=body, timeout=timeout,
            headers={"X-Apollo-Secret": get_secrets().internal_api_secret})
    except Exception as e:
        raise ExecutionUnreachable(f"/data/bars failed over HTTP: {type(e).__name__}: {e}") from e
    if resp.status_code == 200:
        return resp.json()
    try:
        detail = (resp.json() or {}).get("detail")
    except Exception:  # loud-ok: a non-JSON error body still raises below, with the raw text
        detail = None
    if isinstance(detail, dict) and detail.get("code"):
        raise ResearchBarsRequestError(resp.status_code, str(detail["code"]), str(detail.get("message", "")))
    raise ResearchBarsRequestError(resp.status_code, "http_error", str(detail or resp.text)[:500])


def _post_with_retry(body: dict) -> dict:
    """A page with backoff. Retries busy / upstream / transport failures; a 400 (the request
    itself is wrong) is raised at once. So is `orb_window` (09:20-10:05 ET on weekdays): the
    window outlasts every backoff, so retrying only sent more requests into the ORB entries and
    then threw the pull away. It fails on the FIRST refusal — run the script again after 10:05."""
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            return _post(body)
        except ResearchBarsRequestError as e:
            if e.code == ORB_WINDOW_CODE:
                raise ResearchBarsRequestError(
                    e.status, e.code,
                    f"{e.message} — not retried; nothing was returned (a pull that was part-way is discarded). "
                    "Run it again after 10:05 ET.") from e
            if e.status not in _RETRY_STATUSES or attempt == MAX_ATTEMPTS:
                raise
            why = f"{e.status} {e.code}"
        except ExecutionUnreachable as e:
            if attempt == MAX_ATTEMPTS:
                raise
            why = str(e)[:120]
        wait = BACKOFF_BASE_SECONDS * 2 ** (attempt - 1)
        logger.warning(f"/data/bars attempt {attempt}/{MAX_ATTEMPTS} failed ({why}); retrying in {wait:.0f}s")
        _sleep(wait)
    raise AssertionError("unreachable")  # pragma: no cover


def fetch_bars(symbols, timeframe: str, start, end, feed: str | None = None, *,
               adjustment: str | None = None, as_frame: bool = True):
    """Historical bars for `symbols` over [start, end) — start inclusive, end exclusive.

    symbols     a ticker or a list (any number; sent 50 per call)
    timeframe   "1Min" | "5Min" | "15Min" | "1Hour" | "1Day"
    start, end  timezone-aware datetimes or ISO strings with an offset
    feed        "iex" | "sip"; None = the feed apollo-execution is configured with
    adjustment  "raw" (default) | "split" | "dividend" | "all"

    Pages over the range in the chunks the route allows (halving a chunk the route says is
    over its row cap), pauses between pages, retries with backoff.
    -> a pandas DataFrame [symbol, ts (UTC), o, h, l, c, v] sorted by symbol then ts; a list of
    dicts (ts an ISO UTC string) when pandas is missing or `as_frame=False`.
    Raises `ResearchBarsRequestError` (the route refused: bad request, the 09:20-10:05 ET
    weekday `orb_window` — at once, no retry — or still failing after the retries),
    `ExecutionUnreachable`, or RuntimeError when EXECUTION_SERVICE_URL is unset — never a
    silent partial result.
    """
    if isinstance(symbols, str):
        symbols = [symbols]
    names = list(dict.fromkeys(s.strip().upper() for s in symbols if s and s.strip()))
    if not names:
        raise ValueError("fetch_bars needs at least one symbol")
    if timeframe not in RESEARCH_BARS_MAX_RANGE_DAYS:
        raise ValueError(f"timeframe={timeframe!r}; allowed: {list(RESEARCH_BARS_MAX_RANGE_DAYS)}")
    start_utc, end_utc = _as_utc("start", start), _as_utc("end", end)
    if end_utc <= start_utc:
        raise ValueError("end must be after start")
    _service_url()                           # a config error fails here, at once, not after the retries

    span = timedelta(days=RESEARCH_BARS_MAX_RANGE_DAYS[timeframe])
    seen: dict[tuple[str, str], dict] = {}   # (symbol, ts) -> row: a bar on a chunk seam is kept once
    first = True
    for i in range(0, len(names), RESEARCH_BARS_MAX_SYMBOLS):
        batch = names[i:i + RESEARCH_BARS_MAX_SYMBOLS]
        cursor = start_utc
        while cursor < end_utc:
            chunk_end = min(cursor + span, end_utc)
            body = {"symbols": batch, "timeframe": timeframe,
                    "start": cursor.isoformat(), "end": chunk_end.isoformat()}
            if feed is not None:
                body["feed"] = feed
            if adjustment is not None:
                body["adjustment"] = adjustment
            if not first:
                _sleep(PAUSE_SECONDS)
            first = False
            try:
                page = _post_with_retry(body)
            except ResearchBarsRequestError as e:
                if e.code == "row_cap" and (chunk_end - cursor) / 2 >= _MIN_CHUNK:
                    span = (chunk_end - cursor) / 2   # stays halved for the rest of the run
                    continue
                raise
            for row in page.get("bars", []):
                seen.setdefault((row["symbol"], row["ts"]), row)
            cursor = chunk_end

    rows = [seen[k] for k in sorted(seen)]
    if not as_frame:
        return rows
    try:
        import pandas as pd
    except ImportError:
        return rows
    df = pd.DataFrame(rows, columns=["symbol", "ts", "o", "h", "l", "c", "v"])
    df["ts"] = pd.to_datetime(df["ts"], utc=True)
    return df
