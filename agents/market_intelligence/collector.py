"""
Data collection layer.

Polygon.io (Massive) — EOD OHLCV, pre-market snapshots, ticker details.
FMP — company profiles, earnings, analyst ratings.

Rate limits:
- Polygon Starter: unlimited calls (snapshot returns all US tickers in one call)
- FMP free: 250 calls/day → use sparingly, cache aggressively
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
import urllib.parse
from datetime import date, datetime, timedelta
from typing import Any, Optional

import httpx

logger = logging.getLogger(__name__)

POLYGON_BASE = "https://api.polygon.io"
FMP_BASE = "https://financialmodelingprep.com/api"

# (Removed 2026-05-21: _fmp_paywall_alerted flag and FMP-paywall alerting.
# FMP news call stripped entirely — get_fmp_news now goes straight to yfinance.
# See get_fmp_news docstring.)

# Polygon Starter: unlimited calls, but keep a small delay to be polite
_polygon_lock = asyncio.Semaphore(1)
_polygon_last_call: float = 0.0
POLYGON_RATE_DELAY = 0.2  # seconds — minimal courtesy delay


async def _polygon_get(path: str, params: dict | None = None) -> Any:
    """GET request to Polygon API with retry on 429."""
    global _polygon_last_call
    api_key = os.environ.get("POLYGON_API_KEY", "")
    if not api_key:
        raise RuntimeError("POLYGON_API_KEY not set")

    async with _polygon_lock:
        # Minimal courtesy delay between calls
        now = asyncio.get_event_loop().time()
        elapsed = now - _polygon_last_call
        if elapsed < POLYGON_RATE_DELAY:
            await asyncio.sleep(POLYGON_RATE_DELAY - elapsed)

        all_params = {"apiKey": api_key, **(params or {})}
        async with httpx.AsyncClient(timeout=30) as client:
            for attempt in range(3):
                r = await client.get(f"{POLYGON_BASE}{path}", params=all_params)
                _polygon_last_call = asyncio.get_event_loop().time()
                if r.status_code == 429:
                    wait = 15 * (attempt + 1)  # 15s, 30s, 45s
                    logger.warning(f"Polygon 429 — waiting {wait}s (attempt {attempt + 1}/3)")
                    await asyncio.sleep(wait)
                    continue
                r.raise_for_status()
                return r.json()
            r.raise_for_status()  # raise on final attempt
            return r.json()


async def _fmp_get(path: str, params: dict | None = None) -> Any:
    """GET request to FMP API."""
    api_key = os.environ.get("FMP_API_KEY", "")
    if not api_key:
        raise RuntimeError("FMP_API_KEY not set")

    all_params = {"apikey": api_key, **(params or {})}
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(f"{FMP_BASE}{path}", params=all_params)
        r.raise_for_status()
        return r.json()


# ── Polygon endpoints ──────────────────────────────────────────────────────────

async def get_grouped_daily(trade_date: str) -> dict[str, dict]:
    """
    Get all US stock OHLCV for a given date.
    Returns: {ticker: {o, h, l, c, v, vw, t}} or empty dict if market closed.
    trade_date: "YYYY-MM-DD"
    """
    try:
        data = await _polygon_get(
            f"/v2/aggs/grouped/locale/us/market/stocks/{trade_date}",
            {"adjusted": "true", "include_otc": "false"},
        )
        results = data.get("results", [])
        return {r["T"]: r for r in results if "T" in r}
    except Exception as e:
        logger.error(f"Grouped daily failed for {trade_date}: {e}")
        return {}


async def get_snapshot_all() -> dict[str, dict]:
    """
    Get current snapshot for all tickers (includes pre-market data).
    Returns: {ticker: snapshot_dict}
    Pre-market price is in snapshot["lastTrade"]["p"] or snapshot["day"]["o"]
    """
    try:
        data = await _polygon_get(
            "/v2/snapshot/locale/us/markets/stocks/tickers",
            {"include_otc": "false"},
        )
        tickers = data.get("tickers", [])
        return {t["ticker"]: t for t in tickers if "ticker" in t}
    except Exception as e:
        logger.error(f"Snapshot fetch failed: {e}")
        return {}


async def fetch_all_ticker_types() -> dict[str, dict]:
    """
    Fetch security type + exchange for all US stock tickers from Polygon Reference API.
    Returns: {ticker: {"type": "CS"|"ETF"|..., "exchange": "XNYS"|...}}
    Paginated — typically 3-4 API calls for ~14K tickers.
    """
    result: dict[str, dict] = {}
    cursor = None
    page = 0
    while True:
        params = {"market": "stocks", "active": "true", "limit": "1000"}
        if cursor:
            params["cursor"] = cursor
        try:
            data = await _polygon_get("/v3/reference/tickers", params)
        except Exception as e:
            logger.error(f"Ticker types fetch failed (page {page}): {e}")
            break

        for t in data.get("results", []):
            ticker = t.get("ticker")
            if ticker:
                result[ticker] = {
                    "type": t.get("type", ""),
                    "exchange": t.get("primary_exchange", ""),
                }

        next_url = data.get("next_url")
        if not next_url:
            break
        # Extract cursor from next_url
        parsed = urllib.parse.urlparse(next_url)
        qs = urllib.parse.parse_qs(parsed.query)
        cursor = qs.get("cursor", [None])[0]
        if not cursor:
            break
        page += 1

    logger.info(f"Fetched types for {len(result)} tickers ({page + 1} pages)")
    return result


async def get_ticker_details(ticker: str) -> dict:
    """Get company details: name, sector, shares outstanding, etc."""
    try:
        data = await _polygon_get(f"/v3/reference/tickers/{ticker}")
        return data.get("results", {})
    except Exception as e:
        logger.warning(f"Ticker details failed for {ticker}: {e}")
        return {}


async def get_index_history(ticker: str, from_date: str, to_date: str) -> list[dict]:
    """
    Get daily bars for a ticker over a date range.
    Used for SPY/QQQ/VIX regime calculations.
    """
    try:
        data = await _polygon_get(
            f"/v2/aggs/ticker/{ticker}/range/1/day/{from_date}/{to_date}",
            {"adjusted": "true", "sort": "asc", "limit": 300},
        )
        return data.get("results", [])
    except Exception as e:
        logger.error(f"History failed for {ticker}: {e}")
        return []


async def get_minute_bars(ticker: str, from_date: str, to_date: str) -> list[dict]:
    """
    Fetch 1-minute aggregate bars for `ticker` over [from_date, to_date].

    Polygon returns extended-hours bars (pre/post-market) when present, which
    is required for our pre-market RVOL@T baselines. Each bar dict has at
    minimum {t: epoch_ms, v: volume}; we don't need OHLC for volume curves.

    Date strings are ISO YYYY-MM-DD. Returns up to 50,000 bars in one call —
    enough for ~30 trading days of minute data per ticker. Empty list on
    error so the caller can skip a ticker without aborting the batch.
    """
    try:
        data = await _polygon_get(
            f"/v2/aggs/ticker/{ticker}/range/1/minute/{from_date}/{to_date}",
            {"adjusted": "true", "sort": "asc", "limit": 50000},
        )
        return data.get("results", []) or []
    except Exception as e:
        logger.warning(f"Minute bars failed for {ticker} {from_date}..{to_date}: {e}")
        return []


async def get_vix_history(from_date: str, to_date: str) -> list[dict]:
    """
    Get actual VIX daily closes. Tries Polygon I:VIX first (Indices plan),
    falls back to yfinance ^VIX (free, reliable for daily bars).
    Returns list of dicts with at least {"c": float} matching get_index_history format.
    """
    # Try Polygon I:VIX (works on Indices plan, may 404 on Starter)
    try:
        data = await _polygon_get(
            f"/v2/aggs/ticker/I:VIX/range/1/day/{from_date}/{to_date}",
            {"adjusted": "true", "sort": "asc", "limit": 300},
        )
        bars = data.get("results", [])
        if bars:
            logger.debug(f"VIX history: got {len(bars)} bars from Polygon I:VIX")
            return bars
    except Exception as e:
        logger.debug(f"Polygon I:VIX unavailable ({e}), falling back to yfinance")

    # Fall back to yfinance ^VIX
    try:
        import yfinance as yf
        loop = asyncio.get_event_loop()

        # yfinance end is exclusive — add 1 day so to_date itself is included
        yf_end = (date.fromisoformat(to_date) + timedelta(days=1)).strftime("%Y-%m-%d")

        def _fetch():
            df = yf.download("^VIX", start=from_date, end=yf_end, progress=False, auto_adjust=True)
            if df.empty:
                return []
            # Normalise to Polygon bar format: {"t": epoch_ms, "c": close}
            bars = []
            for ts, row in df.iterrows():
                close = float(row["Close"].iloc[0]) if hasattr(row["Close"], "iloc") else float(row["Close"])
                bars.append({"t": int(ts.timestamp() * 1000), "c": close})
            return bars

        bars = await loop.run_in_executor(None, _fetch)
        logger.debug(f"VIX history: got {len(bars)} bars from yfinance ^VIX")
        return bars
    except Exception as e:
        logger.error(f"VIX history failed (both Polygon and yfinance): {e}")
        return []


def prev_trading_days(n: int, from_date: date | None = None) -> list[date]:
    """
    Return a list of n approximate trading dates going back from from_date.
    Approximation: skips weekends only (not holidays). Good enough for RS calc.
    """
    d = from_date or et_today()
    days = []
    while len(days) < n:
        d -= timedelta(days=1)
        if d.weekday() < 5:  # Mon-Fri
            days.append(d)
    return days


# last_trading_day moved to shared/dates.py so the orchestrator container
# (which has no agents/market_intelligence/) can import it for slash commands.
from shared.dates import last_trading_day  # noqa: F401, E402


def trading_date_n_months_ago(months: int) -> str:
    """Approximate trading date n months ago (skip weekends)."""
    d = et_today() - timedelta(days=months * 21)  # ~21 trading days/month
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d.strftime("%Y-%m-%d")


# et_today moved to shared/dates.py — kept as re-export here so the 20+
# market-side modules importing it from collector keep working.
from shared.dates import _ET, et_today  # noqa: F401, E402


# ── yfinance — company profile, analyst ratings (free, no API key) ────────────

async def get_fmp_profile(ticker: str) -> dict:
    """
    Company profile via yfinance: sector, float, market cap, 52W high, description.
    Normalised to match the field names the EP scorer expects.
    """
    try:
        import yfinance as yf
        loop = asyncio.get_event_loop()
        info = await loop.run_in_executor(None, lambda: yf.Ticker(ticker).info)
        return {
            "companyName":   info.get("longName", ticker),
            "sector":        info.get("sector", ""),
            "industry":      info.get("industry", ""),
            "description":   info.get("longBusinessSummary", "")[:500],
            "floatShares":   info.get("floatShares"),
            "marketCap":     info.get("marketCap"),
            "52WeekHigh":    info.get("fiftyTwoWeekHigh"),
            "price":         info.get("currentPrice") or info.get("regularMarketPrice"),
        }
    except Exception as e:
        logger.warning(f"yfinance profile failed for {ticker}: {e}")
        return {}


async def get_fmp_earnings(ticker: str) -> list[dict]:
    """Earnings history via yfinance."""
    try:
        import yfinance as yf
        loop = asyncio.get_event_loop()
        t = yf.Ticker(ticker)
        hist = await loop.run_in_executor(None, lambda: t.earnings_history)
        if hist is None or hist.empty:
            return []
        return hist.head(4).to_dict("records")
    except Exception as e:
        logger.warning(f"yfinance earnings failed for {ticker}: {e}")
        return []


async def get_fmp_analyst_ratings(ticker: str) -> list[dict]:
    """Analyst upgrades/recommendations via yfinance."""
    try:
        import pandas as pd
        import yfinance as yf
        loop = asyncio.get_event_loop()
        t = yf.Ticker(ticker)
        recs = await loop.run_in_executor(None, lambda: t.recommendations)
        if recs is None or (isinstance(recs, pd.DataFrame) and recs.empty):
            return []
        if not isinstance(recs, pd.DataFrame):
            return []  # yfinance API changed — bail gracefully
        recent = recs.tail(10).copy()
        # Find the grade column — yfinance has changed this across versions
        grade_col = None
        for col_name in ("To Grade", "toGrade", "strongBuy"):
            if col_name in recent.columns:
                grade_col = col_name
                break
        if grade_col:
            recent["analystRatingsStrongBuy"] = recent[grade_col].apply(
                lambda g: 1 if str(g).lower() in ("strong buy", "buy", "outperform", "overweight") else 0
            )
        else:
            recent["analystRatingsStrongBuy"] = 0
        return recent.to_dict("records")
    except Exception as e:
        logger.warning(f"yfinance analyst ratings failed for {ticker}: {e}")
        return []


async def get_fmp_news(
    ticker: str,
    limit: int = 5,
    *,
    from_date: Optional[date] = None,
    to_date: Optional[date] = None,
) -> list[dict]:
    """Stock news — historically called FMP `/stable/news/stock-latest`.

    2026-05-21: FMP news is paywalled on our plan (402). Stripped the FMP
    attempt entirely — was producing daily paywall warnings with no
    operator action available. The yfinance.news fallback (which was the
    de-facto behavior anyway) is what this function returns now.

    Naming kept as `get_fmp_news` for caller-compatibility (extract_earnings_metrics,
    backward-check scripts). The "FMP" label is now historical — implementation
    is purely yfinance.news.

    Live extraction has Polygon (date-windowed) + Alpaca News (Benzinga,
    date-windowed) as the primary sources. yfinance here adds marginal
    current-news coverage (~5 items per ticker). Historical backward
    checks should NOT rely on this function — it's current-time only.

    Date params (`from_date`/`to_date`) accepted for caller-compat but
    ignored. Future: if FMP plan is upgraded, restore the FMP call path
    (see git history pre-2026-05-21).
    """
    # FMP attempt removed 2026-05-21 — paywalled on current plan, was
    # producing daily 402 + Telegram noise with no operator action.
    # Restore the FMP try-block from git history if plan is ever upgraded.
    try:
        import yfinance as yf
        loop = asyncio.get_event_loop()
        t = yf.Ticker(ticker)
        news = await loop.run_in_executor(None, lambda: t.news)
        if not news:
            return []
        return [{"title": n.get("content", {}).get("title", ""),
                 "text":  n.get("content", {}).get("summary", "")}
                for n in news[:limit]]
    except Exception as e:
        logger.warning(f"yfinance news failed for {ticker}: {e}")
        return []


async def get_alpaca_news(
    ticker: str,
    *,
    from_date: Optional[date] = None,
    to_date: Optional[date] = None,
    lookback_days: int = 7,
    limit: int = 20,
) -> list[dict]:
    """Stock news via Alpaca News API (`alpaca.data.historical.news.NewsClient`).

    Free with any Alpaca account; Benzinga-sourced content including
    press releases, analyst notes, and aggregator stories. Supports
    historical date ranges (start/end) so this is suitable for both
    live extraction and historical re-validation / backtest.

    Returns list of {title, summary, content, author, source, url, created_at}
    dicts. Empty list on any failure — never raises.
    """
    try:
        from alpaca.data.historical.news import NewsClient
        from alpaca.data.requests import NewsRequest
        from datetime import timezone as _tz
    except ImportError as e:
        logger.warning(f"alpaca-py NewsClient import failed: {e}")
        return []

    api_key = os.environ.get("ALPACA_PAPER_API_KEY") or os.environ.get("ALPACA_API_KEY", "")
    secret = os.environ.get("ALPACA_PAPER_SECRET_KEY") or os.environ.get("ALPACA_SECRET_KEY", "")
    if not api_key or not secret:
        logger.warning("Alpaca credentials not set; skipping Alpaca News")
        return []

    end = to_date or et_today()
    start = from_date or (end - timedelta(days=lookback_days))
    start_dt = datetime(start.year, start.month, start.day, tzinfo=_tz.utc)
    end_dt = datetime(end.year, end.month, end.day, 23, 59, 59, tzinfo=_tz.utc)

    try:
        client = NewsClient(api_key=api_key, secret_key=secret)
        req = NewsRequest(
            symbols=ticker,
            start=start_dt,
            end=end_dt,
            limit=limit,
        )
        loop = asyncio.get_event_loop()
        resp = await loop.run_in_executor(None, lambda: client.get_news(req))
        items = resp.dict().get("news", []) if hasattr(resp, "dict") else resp.model_dump().get("news", [])
        out = []
        for n in items[:limit]:
            out.append({
                "title": n.get("headline", "") or "",
                "summary": n.get("summary", "") or "",
                "content": n.get("content", "") or "",
                "author": n.get("author", "") or "",
                "source": n.get("source", "") or "",
                "url": n.get("url", "") or "",
                # symbols tagged on the item — used by is_primary_subject_news()
                # to reject multi-tag bleed + roundups (#210 Wave A relevance filter)
                # and by Wave B source-provenance.
                "symbols": list(n.get("symbols", []) or []),
                "created_at": n.get("created_at", "").isoformat() if hasattr(n.get("created_at", ""), "isoformat") else str(n.get("created_at", "")),
            })
        return out
    except Exception as e:
        logger.warning(f"Alpaca News failed for {ticker} ({start}..{end}): {e}")
        return []


# Roundup / basket headlines that name many tickers and are never "about" one
# stock — the #88/#90 multi-ticker contamination class (e.g. "12 IT Stocks
# Moving", "Stocks To Watch", "Midday Movers"). Rejected before any item enters
# the grounded catalyst corpus (#210 Wave A).
_ROUNDUP_RE = re.compile(
    r"\b\d+\s+[\w\s]{0,30}?\b(stocks|stories|movers|things|tickers|names|charts|trades|picks)\b"
    r"|\bstocks?\s+(to\s+watch|to\s+buy|moving|on\s+the\s+move|in\s+focus|in\s+play)\b"
    r"|\b(midday|premarket|pre-market|after-hours|market)\s+(movers|wrap|update|roundup|recap)\b"
    r"|\bthings\s+to\s+know\b|\bwhat\s+to\s+watch\b|\bmovers\s+(&|and)\s+shakers\b",
    re.IGNORECASE,
)

# Generic/legal name tokens skipped when matching a company's lead token, so we
# don't match on "Inc"/"Group"/"Holdings". Module-scope (mirrors _ROUNDUP_RE) —
# is_primary_subject_news runs per-item per-ticker across the whole EP scan.
_GENERIC_NAME_TOKENS = frozenset({
    "THE", "INC", "INCORPORATED", "CORP", "CORPORATION", "CO", "COMPANY",
    "GROUP", "HOLDINGS", "HOLDING", "LTD", "LIMITED", "PLC", "SA", "NV",
    "AG", "TECHNOLOGIES", "TECHNOLOGY", "INTERNATIONAL", "SYSTEMS",
})


def is_primary_subject_news(item: dict, ticker: str, company_name: str = "") -> bool:
    """True if a news item is primarily ABOUT `ticker`, not a multi-tag bleed.

    Guards the grounded catalyst corpus (#210 Wave A) against the #88/#90
    contamination class: Alpaca/Benzinga returns items co-tagged with the
    query ticker even when the article's real subject is a sibling (e.g. an
    SMCI "falling 11%" headline co-tagged GRRR) or a basket roundup ("12 IT
    Stocks Moving"). Errs toward PRECISION — when in doubt, drop — because the
    grade reasons on grounded_text and an off-subject headline confabulates it.

    Keep when, AND the title is not a roundup:
      - the ticker appears as a standalone token in the title, OR
      - the company's lead name-token appears in the title, OR
      - the item is single-symbol-tagged (a clean per-ticker PR).
    """
    title = (item.get("title") or "")
    if not title:
        return False
    if _ROUNDUP_RE.search(title):
        return False

    tk = (ticker or "").strip().upper()
    if tk and re.search(rf"\b{re.escape(tk)}\b", title.upper()):
        return True

    # Company lead token (e.g. "Gorilla" from "Gorilla Technology Group, Inc.").
    # Skip generic/legal tokens so we don't match on "Inc"/"Group"/"Holdings".
    for tok in re.split(r"[^A-Za-z]+", company_name or ""):
        if len(tok) >= 4 and tok.upper() not in _GENERIC_NAME_TOKENS:
            if re.search(rf"\b{re.escape(tok)}\b", title, re.IGNORECASE):
                return True
            break  # only test the lead token — avoids matching trailing generics

    syms = item.get("symbols") or []
    if len(syms) == 1 and tk and str(syms[0]).upper() == tk:
        return True

    return False


async def get_polygon_news(
    ticker: str,
    *,
    lookback_days: int = 7,
    limit: int = 20,
    on_or_before: Optional[date] = None,
) -> list[dict]:
    """Recent news headlines via Polygon /v2/reference/news.

    Free coverage backstop for catalyst lookup when Perplexity hedges.
    Returns list of {title, description, published_utc, publisher} dicts.
    Empty list on any failure — never raises.
    """
    try:
        end = on_or_before or et_today()
        start = end - timedelta(days=lookback_days)
        params = {
            "ticker": ticker,
            "published_utc.gte": start.isoformat(),
            "published_utc.lte": end.isoformat(),
            "limit": limit,
            "order": "desc",
            "sort": "published_utc",
        }
        data = await _polygon_get("/v2/reference/news", params)
        # `tickers` and `insights` (per-ticker sentiment_reasoning) are the
        # load-bearing fields for the M&A filter's multi-ticker-tag-bleed fix
        # (#88 2026-05-23). Previously dropped these; QBTS/RGTI got M&A-
        # filtered off a Motley Fool sector roundup tagged with their symbols
        # but only insighted on IONQ. See ma_filter.polygon_news_has_mna_headline.
        return [
            {
                "title": r.get("title", ""),
                "description": r.get("description", ""),
                "published_utc": r.get("published_utc", ""),
                "publisher": (r.get("publisher") or {}).get("name", ""),
                "tickers": r.get("tickers") or [],
                "insights": r.get("insights") or [],
            }
            for r in data.get("results", [])
        ]
    except Exception as e:
        logger.warning(f"Polygon news fetch failed for {ticker}: {e}")
        return []


# ── SEC EDGAR (catalyst sourcing, #187) ──────────────────────────────────────
# Free/public. Uses the near-real-time submissions endpoint (NOT the laggy efts
# full-text index). B0 (2026-06-04) confirmed an 8-K is retrievable within ~2 min
# of acceptance; RUM's $270M GPU-cloud deal 8-K was on EDGAR at 5:04am ET — 4.5h
# before the 9:40 scan — but we never queried it. SEC requires a descriptive UA.
_SEC_UA = {
    "User-Agent": os.environ.get("SEC_USER_AGENT", "Apollo Research lastone99@gmail.com"),
    "Accept-Encoding": "gzip, deflate",
}
_sec_cik_map: Optional[dict[str, str]] = None
_sec_cik_lock = asyncio.Semaphore(1)


def _strip_html(html: str) -> str:
    """Crude HTML→text for SEC filing docs (no bs4 dependency)."""
    txt = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", html)
    txt = re.sub(r"(?s)<[^>]+>", " ", txt)
    txt = txt.replace("&#160;", " ").replace("&nbsp;", " ").replace("&amp;", "&")
    return re.sub(r"\s+", " ", txt).strip()


async def _sec_cik_for(client: httpx.AsyncClient, ticker: str) -> Optional[str]:
    """Map ticker → zero-padded CIK via SEC company_tickers.json (cached process-wide)."""
    global _sec_cik_map
    async with _sec_cik_lock:
        if _sec_cik_map is None:
            r = await client.get("https://www.sec.gov/files/company_tickers.json")
            r.raise_for_status()
            _sec_cik_map = {
                str(row["ticker"]).upper(): str(row["cik_str"]).zfill(10)
                for row in r.json().values()
            }
    return _sec_cik_map.get(ticker.upper())


# Forms whose PRIMARY document is only a cover wrapper — the substance is in an
# EX-99 exhibit (#208). 6-K = foreign private issuer current report (SE/BABA
# earnings, deals): the cover is ~1.5k chars of boilerplate, the press release is
# a 200k+ char EX-99.1. 8-K is NOT here — its body is in the primary doc.
_SEC_COVER_FORMS = ("6-K",)

# 8-K items whose disclosure substance is typically carried in an EX-99.1 press
# release rather than the (often thin/pointer) primary doc (#210 Wave D): 2.02
# results, 7.01 Reg-FD, 8.01 other events. Item 1.01 (material agreement, the RUM
# GPU-deal class) keeps its terms in the PRIMARY body — so for 8-K we CONCATENATE
# the exhibit, never replace (unlike the 6-K cover, which is pure boilerplate).
_SEC_8K_EXHIBIT_ITEMS = ("2.02", "7.01", "8.01")
_SEC_THIN_PRIMARY_CHARS = 600  # below this the primary is a pointer; pull EX-99 too


async def _sec_exhibit_url(
    client: httpx.AsyncClient, cik: str, acc_no: str, primary: str
) -> Optional[str]:
    """For cover-style filings (6-K), find the EX-99 press-release exhibit URL via
    the filing index.json. Prefers an ex99* document; falls back to the largest
    non-primary .htm. Returns None on any failure (caller keeps the cover text)."""
    try:
        idx = (await client.get(
            f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc_no}/index.json"
        )).json()
        cands: list[tuple] = []
        for it in idx.get("directory", {}).get("item", []):
            name = it.get("name") or ""
            low = name.lower()
            if not low.endswith((".htm", ".html")):
                continue
            # Skip the cover, the EDGAR index pages, and iXBRL R-render files.
            if name == primary or "index" in low or re.match(r"r\d+\.htm", low):
                continue
            try:
                size = int(it.get("size") or 0)
            except (ValueError, TypeError):
                size = 0
            # EX-99 (press release) wins; otherwise rank by size (largest body).
            is_ex99 = "ex99" in low or "ex-99" in low or "dex99" in low
            cands.append(((0 if is_ex99 else 1, -size), name))
        if not cands:
            return None
        cands.sort()
        best = cands[0][1]
        return f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc_no}/{best}"
    except Exception:
        return None


async def get_sec_recent_filings(
    ticker: str,
    *,
    forms: tuple[str, ...] = ("8-K",),
    lookback_days: int = 4,
    max_filings: int = 2,
    want_text: bool = True,
) -> list[dict]:
    """Recent SEC filings (default 8-K) for `ticker`, newest first, via the
    near-real-time submissions endpoint. Returns list of
    {form, filed, accepted, items, url, text}. Empty list on ANY failure — never
    raises, so it can't slow or break the EP scan (#187 catalyst sourcing).
    The 8-K disclosure body is in the PRIMARY doc (after the iXBRL cover header).
    For 6-K (foreign issuers, #208) the primary is only a cover — `text` is pulled
    from the EX-99 exhibit and `url` points at it."""
    try:
        async with httpx.AsyncClient(timeout=10, headers=_SEC_UA, follow_redirects=True) as client:
            cik = await _sec_cik_for(client, ticker)
            if not cik:
                return []
            sub = (await client.get(f"https://data.sec.gov/submissions/CIK{cik}.json")).json()
            recent = sub["filings"]["recent"]
            n = len(recent["form"])
            acc = recent.get("acceptanceDateTime", [""] * n)
            items = recent.get("items", [""] * n)
            cutoff = (et_today() - timedelta(days=lookback_days)).isoformat()
            out: list[dict] = []
            for i, form in enumerate(recent["form"]):
                if not any(form.startswith(f) for f in forms):
                    continue
                if recent["filingDate"][i] < cutoff:
                    continue
                acc_no = recent["accessionNumber"][i].replace("-", "")
                primary = recent["primaryDocument"][i]
                url = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc_no}/{primary}"
                # 6-K substance lives in an EX-99 exhibit, not the cover (#208).
                is_cover_form = any(form.startswith(f) for f in _SEC_COVER_FORMS)
                if is_cover_form:
                    ex_url = await _sec_exhibit_url(client, cik, acc_no, primary)
                    if ex_url:
                        url = ex_url  # point at the press release, not the cover
                rec = {
                    "form": form,
                    "filed": recent["filingDate"][i],
                    "accepted": acc[i],
                    "items": items[i],
                    "url": url,
                }
                if want_text:
                    try:
                        rec["text"] = _strip_html((await client.get(url)).text)[:4000]
                    except Exception:
                        rec["text"] = ""
                    # 8-K (#210 Wave D): the primary doc is often a thin pointer; the
                    # results/PR substance (item 2.02/7.01/8.01) lives in EX-99.1.
                    # CONCATENATE it (item 1.01 deal terms stay in the primary, so we
                    # never replace). Bounded: one extra exhibit GET, uncached path.
                    if form.startswith("8-K") and not is_cover_form:
                        item_str = items[i] or ""
                        if (len(rec["text"].strip()) < _SEC_THIN_PRIMARY_CHARS
                                or any(it in item_str for it in _SEC_8K_EXHIBIT_ITEMS)):
                            try:
                                ex_url = await _sec_exhibit_url(client, cik, acc_no, primary)
                                if ex_url and ex_url != url:
                                    ex_text = _strip_html((await client.get(ex_url)).text)
                                    if ex_text.strip():
                                        rec["text"] = (
                                            (rec["text"] + "\n\n[EX-99] " + ex_text).strip()
                                        )[:6000]
                                        rec["exhibit_url"] = ex_url
                            except Exception:
                                pass
                out.append(rec)
                if len(out) >= max_filings:
                    break
            return out
    except Exception as e:
        logger.warning(f"SEC filings fetch failed for {ticker}: {e}")
        return []


async def get_premarket_snapshot() -> dict[str, float]:
    """
    Pre-market price snapshot for SPY and QQQ via Polygon.
    Returns overnight % change keyed as spy_pct and qqq_pct.

    Uses Polygon /v2/snapshot (not yfinance — yfinance is unreliable pre-market):
      - prevDay.c  = confirmed 4 PM regular-session close (reliable reference)
      - min.c      = latest minute bar close (updates in pre-market)

    Fails gracefully — returns empty dict on any error.
    """
    try:
        data = await _polygon_get(
            "/v2/snapshot/locale/us/markets/stocks/tickers",
            {"tickers": "SPY,QQQ"},
        )
        snaps = {t["ticker"]: t for t in data.get("tickers", []) if "ticker" in t}
        result = {}
        for ticker, key in (("SPY", "spy_pct"), ("QQQ", "qqq_pct")):
            snap = snaps.get(ticker, {})
            prev = snap.get("prevDay", {}).get("c")
            current = (
                snap.get("min", {}).get("c")
                or snap.get("lastTrade", {}).get("p")
                or snap.get("day", {}).get("o")
            )
            if prev and current and prev != 0:
                pct = (current - prev) / prev * 100
                result[key] = pct
                logger.debug(f"Premarket snapshot {ticker}: current={current:.2f} prevDay.c={prev:.2f} → {pct:+.2f}%")
        return result
    except Exception as e:
        logger.warning(f"Premarket snapshot failed: {e}")
        return {}


async def get_overnight_snapshot(watchlist: list[dict]) -> list[dict]:
    """
    Fetch overnight price changes for all watchlist instruments via yfinance.
    Returns list of dicts with symbol, name, pct_change, price, threshold, triggered.
    """
    if not watchlist:
        return []
    try:
        import yfinance as yf
        loop = asyncio.get_event_loop()

        def _fetch() -> list[dict]:
            results = []
            for item in watchlist:
                symbol = item["symbol"]
                try:
                    fi = yf.Ticker(symbol).fast_info
                    price = getattr(fi, "last_price", None)
                    prev = getattr(fi, "previous_close", None)
                    if price is not None and prev is not None and prev != 0:
                        pct = (price - prev) / prev * 100
                        threshold = item.get("threshold_pct", 0.5)
                        results.append({
                            "symbol": symbol,
                            "name": item.get("display_name", symbol),
                            "price": round(price, 2),
                            "pct_change": round(pct, 2),
                            "threshold": threshold,
                            "category": item.get("category", "other"),
                            "triggered": abs(pct) >= threshold,
                        })
                except Exception:
                    pass
            return results

        return await asyncio.wait_for(loop.run_in_executor(None, _fetch), timeout=30)
    except asyncio.TimeoutError:
        logger.warning("Overnight snapshot timed out after 30s — skipping")
        return []
    except Exception as e:
        logger.warning(f"Overnight snapshot failed: {e}")
        return []


_PERPLEXITY_SYSTEM_DEFAULT = (
    "You are a financial market analyst. Give direct, specific answers "
    "about current market catalysts. "
    "Never include citation numbers like [1] or [2]. "
    "Never say 'search results show' or 'I cannot find'. "
    "Plain text only — no markdown, no bullets."
)


async def check_perplexity_health() -> tuple[bool, int, str]:
    """
    Probe Perplexity with a minimal call to verify the API key and credit balance.
    Returns (ok, status_code, error_message).

    - (True, 200, ""): API is healthy — engine may proceed
    - (False, 401, "..."): Invalid API key or no credits — HARD ABORT required
    - (False, 402, "..."): Payment required / credits exhausted — HARD ABORT required
    - (True, 0, ""): Network/transient error — treat as OK (don't abort for flakiness)
    """
    api_key = os.environ.get("PERPLEXITY_API_KEY")
    if not api_key:
        return False, 0, "PERPLEXITY_API_KEY env var not set"
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(
                "https://api.perplexity.ai/chat/completions",
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "model": "sonar-pro",
                    "messages": [{"role": "user", "content": "ping"}],
                    "max_tokens": 5,
                },
            )
            if r.status_code in (401, 402):
                return False, r.status_code, r.text[:300]
            return True, r.status_code, ""
    except Exception as e:
        # Network errors, timeouts, DNS — treat as transient, don't abort
        logger.warning(f"Perplexity health probe network error (non-fatal): {e}")
        return True, 0, ""


# Disclaimer markers that indicate Perplexity returned "no info found" rather
# than actual ticker-specific catalyst content. When these appear in the lead
# of a Perplexity response, the rest of the text is unrelated filler (often
# a "nearest match" stock or industry chatter) that should NOT be fed to
# downstream keyword scanners. See review
# `perplexity_hallucination_keyword_leak` — 11 mna_filter_fired FPs in 90d
# caused by disclaimer text matching M&A keywords on unrelated companies.
_PERPLEXITY_DISCLAIMER_MARKERS: tuple[str, ...] = (
    "no recent catalysts found",
    "no direct catalyst",
    "no specific news",
    "no direct information",
    "nearest match",
    "closest match",
    "i don't have information",
    "i dont have information",
    "no information about",
    "search results reference",
    "search results focus on",
)


def strip_perplexity_disclaimer(text: str | None) -> tuple[str, bool]:
    """Detect Perplexity 'no info found' disclaimer patterns in the LEAD of
    a response. Returns (clean_text, is_disclaimer).

    Conservative — only flags when a marker appears in the first 200 chars,
    not when it appears mid-content as a legitimate quote. Used by every
    detector that feeds Perplexity output to keyword scanners; downstream
    callers should treat the catalyst text as unusable when is_disclaimer=True.
    """
    if not text:
        return ("", False)
    lead = text[:200].lower()
    for marker in _PERPLEXITY_DISCLAIMER_MARKERS:
        if marker in lead:
            return (text, True)
    return (text, False)


async def search_news_perplexity(
    query: str, recency: str = "month", system_prompt: str | None = None,
) -> str:
    """Use Perplexity Sonar for news search. Returns a synthesized answer string.

    recency: "day" | "week" | "month" | "year" — use "week" for EP catalysts.
    system_prompt: override the default system prompt for specialized callers.
    """
    api_key = os.environ.get("PERPLEXITY_API_KEY")
    if not api_key:
        return ""
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.post(
                "https://api.perplexity.ai/chat/completions",
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "model": "sonar-pro",
                    "messages": [
                        {
                            "role": "system",
                            "content": system_prompt or _PERPLEXITY_SYSTEM_DEFAULT,
                        },
                        {"role": "user", "content": query},
                    ],
                    "search_recency_filter": recency,
                    "return_citations": False,
                },
            )
            r.raise_for_status()
            return r.json()["choices"][0]["message"]["content"]
    except Exception as e:
        logger.warning(f"Perplexity search failed: {e}")
        return ""


async def search_news_tavily(query: str) -> list[dict]:
    """Use Tavily for news search when available."""
    api_key = os.environ.get("TAVILY_API_KEY")
    if not api_key:
        return []
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.post(
                "https://api.tavily.com/search",
                json={"api_key": api_key, "query": query, "search_depth": "basic", "max_results": 5},
            )
            r.raise_for_status()
            return r.json().get("results", [])
    except Exception as e:
        logger.warning(f"Tavily search failed: {e}")
        return []
