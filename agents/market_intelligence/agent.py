"""
Market Intelligence Agent — FastAPI service on port 8006.

Handles:
- On-demand queries: "any EPs today?", "what's the market regime?", "top RS stocks?"
- POST /briefing/trigger — manually send morning briefing
- POST /data/refresh — manually run nightly data pull
- Scheduled jobs: nightly RS/regime, pre-market EP scan, morning briefing
"""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import date
from typing import Any

import anthropic
from fastapi import BackgroundTasks, Depends

# Suppress httpx INFO logs — they include full URLs with API keys
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
from pydantic import BaseModel

from agents.base import BaseAgent, verify_internal_secret
from agents.market_intelligence.db import (
    initialize_schema,
    get_today_ep_alerts,
    get_rs_leaders,
    get_latest_regime,
    get_ma_pullbacks,
    get_rs_for_tickers,
    get_ticker_extension_data,
    bulk_track_stocks,
    seed_theme,
    upsert_ticker_override,
    get_ticker_overrides,
    get_rs_history,
    get_theme_history,
    get_prior_theme_scores,
    add_theme_exclusion,
    remove_theme_exclusion,
    list_theme_exclusions,
    get_audit_log,
    get_ticker_sector,
    upsert_ticker_sectors_batch,
    get_sector_rs_rank,
    get_ep_history,
    get_ep_scan_log_history,
    get_ep_scan_log,
    get_pool,
    restore_recently_retired_themes,
    get_ep_outcomes,
    add_journal_entry,
    get_journal_entries,
)
from agents.market_intelligence.briefing import send_morning_briefing, send_evening_briefing, send_telegram_message
from agents.market_intelligence.collector import et_today, search_news_perplexity
from agents.market_intelligence.ep_detector import run_ep_scan, MIN_GAP_PCT, MIN_PREV_CLOSE, MIN_REL_VOLUME, MIN_PREMARKET_SHARES, MAX_EXTENSION_PCT, EP_COOLDOWN_DAYS
from agents.market_intelligence.rs_engine import run_rs_engine, score_single_ticker
from agents.market_intelligence.regime import run_regime_engine, get_current_regime
from agents.market_intelligence.theme_engine import (
    run_theme_engine, get_today_themes, PerplexityUnavailableError,
)
from agents.market_intelligence.scheduler import start_scheduler, stop_scheduler, check_missed_jobs
from shared.models import AgentName, AgentRequest, AgentResponse

logger = logging.getLogger(__name__)

MARKET_AGENT_MODEL = "claude-haiku-4-5-20251001"

# Common short words that match the ticker regex but are never tickers.
# Shared across all three ticker-extraction call sites in execute_task.
_PREPOSITION_SKIP: frozenset[str] = frozenset({
    "OF", "IN", "AT", "ON", "BY", "TO", "AS", "AN", "OR",
    "MY", "ME", "IT", "IS", "IF", "BE", "DO", "SO", "UP",
    "AM", "US", "WE", "NO", "GO", "HI",
})


class TeachRequest(BaseModel):
    tickers: list[str] = []
    theme_name: str = ""
    theme_thesis: str = ""
    observation: str = ""


class ExtensionRequest(BaseModel):
    tickers: list[str]


class UpdateStockInfoRequest(BaseModel):
    ticker: str
    description: str
    notes: str = ""


class TweetRequest(BaseModel):
    text: str


class ScreenerRequest(BaseModel):
    min_rs: float = 60.0
    min_eps_yoy_pct: float | None = None
    min_rev_yoy_pct: float | None = None
    require_acceleration: bool = False
    require_sales_confirms: bool = False
    theme_stage: str | None = None
    max_results: int = 20


class MarketIntelligenceAgent(BaseAgent):
    def __init__(self) -> None:
        super().__init__(AgentName.MARKET_INTELLIGENCE)
        self._claude = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))
        self._refresh_lock = asyncio.Lock()
        self._register_extra_routes()

    def _register_extra_routes(self) -> None:
        """Register additional endpoints beyond the base /task and /health."""

        @self.app.post("/briefing/morning")
        async def trigger_morning_briefing(
            background: BackgroundTasks,
            _: str = Depends(verify_internal_secret),
        ):
            background.add_task(send_morning_briefing)
            return {"status": "morning briefing queued"}

        @self.app.post("/briefing/trigger")  # legacy alias
        async def trigger_briefing(
            background: BackgroundTasks,
            _: str = Depends(verify_internal_secret),
        ):
            background.add_task(send_morning_briefing)
            return {"status": "morning briefing queued"}

        @self.app.post("/briefing/evening")
        async def trigger_evening_briefing(
            background: BackgroundTasks,
            _: str = Depends(verify_internal_secret),
        ):
            background.add_task(send_evening_briefing)
            return {"status": "evening briefing queued"}

        @self.app.post("/data/refresh")
        async def refresh_data(
            background: BackgroundTasks,
            _: str = Depends(verify_internal_secret),
        ):
            async def _refresh():
                await run_regime_engine()
                await run_rs_engine()
                await run_theme_engine()
            background.add_task(_refresh)
            return {"status": "data refresh queued"}

        @self.app.post("/theme/run")
        async def run_themes_only(
            background: BackgroundTasks,
            _: str = Depends(verify_internal_secret),
        ):
            """Re-run just the theme engine (uses existing RS data). Fast — no Polygon calls.
            Runs asynchronously and sends result via Telegram when complete.
            Prefer the /task endpoint (which uses _handle_theme_only) for synchronous results.
            """
            async def _run_and_notify():
                try:
                    themes, changelog = await run_theme_engine()
                    active = [t for t in themes if t.get("stage") != "Fading"]
                    revalidated = [e for e in changelog if e.get("type") == "ticker_revalidated_out"]
                    pruned = [e for e in changelog if e.get("type") == "ticker_pruned"]
                    summary = f"Theme engine complete — {len(active)} active themes"
                    if revalidated:
                        removed = ", ".join(f"{e['ticker']} from {e['theme']}" for e in revalidated)
                        summary += f"\nRemoved mismatched: {removed}"
                    if pruned:
                        summary += f"\nPruned {len(pruned)} weak stock(s)"
                    await send_telegram_message(summary)
                except Exception as e:
                    logger.error(f"Background theme run failed: {e}", exc_info=True)
                    await send_telegram_message(f"Theme engine failed: {e}")
            background.add_task(_run_and_notify)
            return {"status": "theme engine queued"}

        @self.app.post("/tweet")
        async def post_tweet(
            body: TweetRequest,
            _: str = Depends(verify_internal_secret),
        ):
            """Post a custom tweet to @Apollo_Trends."""
            from agents.market_intelligence.twitter import post_custom_tweet
            result = await post_custom_tweet(body.text)
            return result

        @self.app.post("/teach")
        async def teach(
            body: TeachRequest,
            _: str = Depends(verify_internal_secret),
        ):
            today = et_today()
            results: dict[str, str] = {}

            if body.tickers:
                tickers_upper = [t.upper() for t in body.tickers]
                count = await bulk_track_stocks(tickers_upper, today)
                results["tracked"] = (
                    f"Added {count} ticker(s) to RS tracking: {', '.join(tickers_upper)}. "
                    f"Scores will appear after next data refresh."
                )
                logger.info(f"Teach: tracked {tickers_upper}")

            if body.theme_name:
                tickers_for_theme = [t.upper() for t in body.tickers]
                await seed_theme(body.theme_name, body.theme_thesis, tickers_for_theme, today)
                results["theme"] = (
                    f"Seeded theme '{body.theme_name}' with {len(tickers_for_theme)} stock(s). "
                    f"Will be scored on next data refresh."
                )
                logger.info(f"Teach: seeded theme '{body.theme_name}' — {tickers_for_theme}")

            if not results:
                return {"status": "nothing to do — provide tickers or theme_name"}

            return {"status": "ok", **results}

        @self.app.post("/stocks/update_info")
        async def update_stock_info(
            body: UpdateStockInfoRequest,
            _: str = Depends(verify_internal_secret),
        ):
            """Update a stock's description — overrides static universe.py."""
            ticker = body.ticker.upper()
            await upsert_ticker_override(ticker, body.description, body.notes or None)
            # Apply immediately to in-memory lookup
            from agents.market_intelligence.universe import apply_overrides
            apply_overrides({ticker: body.description})
            logger.info(f"Stock info updated: {ticker} → {body.description}")
            return {
                "status": "ok",
                "ticker": ticker,
                "description": body.description,
            }

        @self.app.post("/ep/scan")
        async def manual_ep_scan(_: str = Depends(verify_internal_secret)):
            results = await run_ep_scan()
            return {"ep_count": len(results), "results": results}

        @self.app.post("/stocks/extension")
        async def check_extension(
            body: ExtensionRequest,
            _: str = Depends(verify_internal_secret),
        ):
            """Return 20MA extension % for each ticker + current regime."""
            data = await get_ticker_extension_data(body.tickers)
            regime = await get_latest_regime() or {}
            return {
                "extensions": data,
                "regime": regime.get("regime", "Unknown"),
            }

        @self.app.get("/market/status")
        async def market_pipeline_status(_: str = Depends(verify_internal_secret)):
            """Return pipeline health: job run times, data freshness, scheduler state."""
            from agents.market_intelligence.db import get_pipeline_status
            from agents.market_intelligence.scheduler import get_scheduler_status
            pipeline = await get_pipeline_status()
            return {**pipeline, "scheduler": get_scheduler_status()}

        @self.app.post("/screener")
        async def run_screener_endpoint(
            body: ScreenerRequest,
            _: str = Depends(verify_internal_secret),
        ):
            from agents.market_intelligence.screener import (
                ScreenerFilters,
                run_screener,
                format_screener_results,
            )
            filters = ScreenerFilters(
                min_rs=body.min_rs,
                min_eps_yoy_pct=body.min_eps_yoy_pct,
                min_rev_yoy_pct=body.min_rev_yoy_pct,
                require_acceleration=body.require_acceleration,
                require_sales_confirms=body.require_sales_confirms,
                theme_stage=body.theme_stage,
                max_results=body.max_results,
            )
            results = await run_screener(filters)
            return {"result": format_screener_results(results, filters)}

        @self.app.get("/trades/summary")
        async def trades_summary(_: str = Depends(verify_internal_secret)):
            """Return combined trade summary: live (Alpaca) + paper trades."""
            from agents.market_intelligence.db import get_pool
            from agents.market_intelligence.broker import alpaca_client as alpaca

            pool = await get_pool()
            result = {"live": None, "paper": None}

            # ── Live (Alpaca) trades ──
            try:
                async with pool.acquire() as conn:
                    stats = await conn.fetchrow("""
                        SELECT
                            COUNT(*) FILTER (WHERE status NOT IN ('skipped','cancelled','order_failed')) as total,
                            COUNT(*) FILTER (WHERE status = 'filled' AND remaining_shares > 0) as open_count,
                            COUNT(*) FILTER (WHERE status = 'closed' AND total_pnl > 0) as winners,
                            COUNT(*) FILTER (WHERE status = 'closed' AND total_pnl <= 0) as losers,
                            COALESCE(SUM(total_pnl) FILTER (WHERE status = 'closed'), 0) as realized_pnl
                        FROM mi_live_trades
                    """)
                    open_trades = await conn.fetch("""
                        SELECT id, ticker, alert_date, ep_score, entry_price,
                               remaining_shares, stop_price, hard_stop, hold_days,
                               position_size, risk_dollars, total_pnl,
                               partial_taken, breakeven_active, catalyst_quality
                        FROM mi_live_trades
                        WHERE status = 'filled' AND remaining_shares > 0
                        ORDER BY alert_date ASC
                    """)
                    recent_closed = await conn.fetch("""
                        SELECT ticker, alert_date, entry_price, total_pnl,
                               hold_days, exits, catalyst_quality, ep_score
                        FROM mi_live_trades
                        WHERE status = 'closed'
                        ORDER BY closed_at DESC LIMIT 3
                    """)

                # Fetch current prices from Alpaca for unrealized P&L
                open_details = []
                for t in open_trades:
                    t = dict(t)
                    try:
                        pos = await alpaca.get_position(t["ticker"])
                        if pos:
                            t["current_price"] = pos["current_price"]
                            t["unrealized_pnl"] = pos["unrealized_pl"]
                            t["market_value"] = pos["market_value"]
                        else:
                            t["current_price"] = None
                            t["unrealized_pnl"] = 0
                            t["market_value"] = 0
                    except Exception:
                        t["current_price"] = None
                        t["unrealized_pnl"] = 0
                        t["market_value"] = 0
                    open_details.append(t)

                # Get account equity
                try:
                    account = await alpaca.get_account()
                    equity = account["equity"]
                except Exception:
                    equity = None

                closed_count = (stats["winners"] or 0) + (stats["losers"] or 0)
                result["live"] = {
                    "total": stats["total"] or 0,
                    "open_count": stats["open_count"] or 0,
                    "winners": stats["winners"] or 0,
                    "losers": stats["losers"] or 0,
                    "win_rate": (stats["winners"] / closed_count * 100) if closed_count > 0 else 0,
                    "realized_pnl": float(stats["realized_pnl"] or 0),
                    "equity": equity,
                    "open_positions": open_details,
                    "recent_closed": [dict(r) for r in recent_closed],
                }
            except Exception as e:
                result["live"] = {"error": str(e)}

            # ── Paper (backtester) trades ──
            try:
                from agents.market_intelligence.backtester.tracker import get_paper_trading_summary
                result["paper"] = await get_paper_trading_summary()
            except Exception as e:
                result["paper"] = {"error": str(e)}

            return result

        @self.app.post("/broker/test")
        async def broker_test(_: str = Depends(verify_internal_secret)):
            """Sanity test: verify Alpaca connectivity, account info, and order placement."""
            results = {}
            try:
                from agents.market_intelligence.broker import alpaca_client as alpaca
                # 1. Account info
                account = await alpaca.get_account()
                results["account"] = {
                    "connected": True,
                    "trading_blocked": account["trading_blocked"],
                    "paper": os.environ.get("ALPACA_PAPER", "true").lower() == "true",
                }
                # 2. Get a market data bar (AAPL yesterday)
                from datetime import date, timedelta
                yesterday = date.today() - timedelta(days=1)
                bar = await alpaca.get_first_bar("AAPL", yesterday)
                results["market_data"] = {"AAPL_bar": bar}
                # 3. Check positions
                positions = await alpaca.get_all_positions()
                results["positions"] = len(positions)
                # 4. Check open orders
                orders = await alpaca.get_open_orders()
                results["open_orders"] = len(orders)
                results["status"] = "ok"
            except Exception as e:
                results["status"] = "error"
                results["error"] = str(e)
            return results

        @self.app.post("/broker/callback")
        async def broker_callback(
            body: dict,
            _: str = Depends(verify_internal_secret),
        ):
            """Handle forwarded trade callback from Telegram inline buttons."""
            from agents.market_intelligence.broker.telegram_confirm import handle_callback
            callback_data = body.get("callback_data", "")
            result = await handle_callback(callback_data)
            return result

    async def execute_task(self, request: AgentRequest) -> AgentResponse:
        task = request.task.lower()

        # Route by intent
        # Data refresh must be checked first — combined requests like "refresh then send brief"
        # would otherwise match "brief" and skip the refresh entirely.
        if any(k in task for k in ["track ", "untrack ", "drop ", "watchlist", "overnight watch"]):
            return await self._handle_watchlist(request)

        if any(k in task for k in ["exclude ", "ban from theme", "remove from theme", "kick from theme", "list exclusions", "show exclusions", "theme exclusions"]):
            return await self._handle_theme_exclusion(request)

        if any(k in task for k in ["restore retired themes", "restore themes", "unretire themes", "recover themes"]):
            return await self._handle_restore_themes(request)

        if any(k in task for k in ["theme engine", "rerun theme", "re-run theme", "run theme", "refresh theme"]):
            return await self._handle_theme_only(request)

        if any(k in task for k in ["refresh", "data pull", "nightly pull", "rerun", "re-run", "repull"]):
            return await self._handle_data_refresh(request)

        # Journal — add (colon disambiguates from query) or query
        if any(k in task for k in ["journal:", "log trade", "note trade", "add journal"]):
            return await self._handle_journal_add(request)
        if any(k in task for k in ["show journal", "my journal", "journal this week",
                                     "journal today", "journal last", "journal entries"]):
            return await self._handle_journal_query(request)

        if any(k in task for k in ["audit log", "show logs", "recent logs", "advisor log", "what happened", "engine log", "orb log", "show orb"]):
            return await self._handle_audit_log(request)

        if any(k in task for k in ["my trades", "show trades", "trade history", "paper trade", "paper trading", "paper p&l",
                                    "trade p&l", "trades today", "recent trades", "open trades", "closed trades",
                                    "trade summary", "trading summary", "entry exit", "entries exits",
                                    "filtered trades", "skipped trades", "all trades", "ep trades"]):
            return await self._handle_trades_query(request)

        # Single-ticker trade lookup — "entry/exit for TVTX", "TVTX trade", "what happened with TVTX trade"
        if any(k in task for k in ["entry", "exit", "trade"]):
            import re as _re
            _cands = _re.findall(r'\b([A-Z]{2,5})\b', request.task.upper())
            _skip = _PREPOSITION_SKIP | {"ENTRY", "EXIT", "TRADE", "THE", "FOR", "AND", "WHAT", "WITH"}
            _trade_ticker = next((t for t in _cands if t not in _skip), None)
            if _trade_ticker:
                return await self._handle_trades_query(request, ticker=_trade_ticker)

        # History must be checked before theme/RS — "when did metals theme peak?" has "theme" in it
        if any(k in task for k in ["history", "historical", "when did", "when was", "over time", "timeline", "peak", "peaked", "faded", "fade"]):
            return await self._handle_history_query(request)

        # EP history — must come before general EP route
        if any(k in task for k in ["ep history", "recent eps", "past eps", "eps last", "ep last", "ep log", "previous eps", "eps this week", "eps today and"]):
            return await self._handle_ep_history(request)

        # EP outcome table — forward returns per alert; before general "ep" route
        if any(k in task for k in ["ep outcome", "ep performance", "how are my ep",
                                     "ep returns", "ep results", "ep track"]):
            return await self._handle_ep_outcomes(request)

        # "why not EP / why wasn't X flagged" — diagnostic must come before general EP route
        if any(k in task for k in ["why not ep", "why no ep", "why wasn't", "why was not", "not flagged", "not an ep", "missed ep", "why didn't", "why did not"]):
            import re as _re
            _cands = _re.findall(r'\b([A-Z]{2,5})\b', request.task.upper())
            _skip = _PREPOSITION_SKIP | {"WHY", "NOT", "NO", "EP", "WAS", "DID", "AN", "THE", "FOR"}
            _ticker = next((t for t in _cands if t not in _skip), None)
            if _ticker:
                return await self._handle_ep_diagnostic(_ticker, request)

        if any(k in task for k in ["ep", "episodic", "gap", "pivot", "gapper"]):
            return await self._handle_ep_query(request)

        # Theme must be checked before regime and RS — "top themes by RS strength" or
        # "regime and active themes" should route to themes (the more specific intent).
        # Exception: "industry" with a ticker means single-ticker industry RS context
        # (the single-score handler already includes industry-relative RS).
        _has_ticker_for_industry = False
        if "industry" in task and "theme" not in task and "sector" not in task:
            import re as _re2
            _ind_candidates = _re2.findall(r'\b([A-Z]{2,5})\b', request.task.upper())
            _ind_skip = _PREPOSITION_SKIP | {"RS", "FOR", "THE", "AND", "ITS", "VS", "VERSUS",
                         "INDUSTRY", "SECTOR", "RELATIVE", "STRENGTH", "COMPARED", "TO",
                         "WHAT", "HOW", "DOES", "SHOW", "GET", "CHECK"}
            _has_ticker_for_industry = any(t for t in _ind_candidates if t not in _ind_skip)

        if not _has_ticker_for_industry and any(k in task for k in ["theme", "sector", "industry"]):
            logger.info(f"Routing to theme handler: {task[:80]}")
            return await self._handle_theme_query(request)

        if any(k in task for k in ["regime", "market condition", "spy", "breadth", "vix", "risk"]):
            return await self._handle_regime_query(request)

        if any(k in task for k in ["rs", "relative strength", "leader", "momentum", "top stock",
                                     "score ", "rank "]):
            # If a specific ticker is detected, route to single-ticker score
            import re as _re
            _candidate = _re.findall(r'\b([A-Z]{2,5})\b', request.task.upper())
            _skip = _PREPOSITION_SKIP | {"RS", "FOR", "SCORE", "RANK", "WHAT", "THE", "AND", "NOW",
                      "TOP", "PULL", "GET", "SHOW", "LIST", "CHECK", "FIND",
                      "STOCK", "STOCKS", "LEADER", "LEADERS"}
            _candidate = [t for t in _candidate if t not in _skip]
            if _candidate:
                return await self._handle_single_score(request)
            return await self._handle_rs_query(request)

        if any(k in task for k in ["brief", "morning", "evening", "summary", "overview"]):
            return await self._handle_briefing_query(request)

        if any(k in task for k in ["pullback", "pull back", "10ma", "20ma", "50ma", "ema", "sma", "moving average", "testing ma", "near ma"]):
            return await self._handle_pullback_query(request)

        if any(k in task for k in [
            "fundamental", "earnings growth", "eps growth", "sales growth",
            "revenue growth", "canslim", "o'neil", "oneill", "quarterly eps",
            "quarterly revenue", "gross margin", "income statement",
        ]):
            return await self._handle_fundamentals_query(request)

        # "research MRNA" / "look up AAPL" — single-ticker full analysis via market agent
        if any(k in task for k in ["research ", "look up ", "lookup ", "analyse ", "analyze "]):
            import re as _re
            _cands = _re.findall(r'\b([A-Z]{2,5})\b', request.task.upper())
            _skip = _PREPOSITION_SKIP | {"RS", "FOR", "AND", "THE", "GET", "SHOW",
                                         "LOOK", "ANALYSE", "ANALYZE", "RESEARCH"}
            if any(t for t in _cands if t not in _skip):
                return await self._handle_single_score(request)

        if any(k in task for k in [
            "screener", "screen for", "find top", "best stocks with",
            "filter stocks", "composite score", "quality stocks", "fundamental stocks",
        ]):
            return await self._handle_screener_query(request)

        # General: let Claude decide what data to pull
        return await self._handle_general(request)

    async def _handle_data_refresh(self, request: AgentRequest) -> AgentResponse:
        """Kick off regime + RS + theme engines in the background and return immediately."""
        task_lower = request.task.lower()
        wants_brief = any(k in task_lower for k in ["brief", "send", "briefing"])
        wants_morning = any(k in task_lower for k in ["morning", "pre-market"])

        async def _run():
            try:
                logger.info("Background data refresh starting...")
                await run_regime_engine()
                await run_rs_engine()
                await run_theme_engine()
                logger.info("Background data refresh complete")
                if wants_brief:
                    if wants_morning:
                        await send_morning_briefing()
                    else:
                        await send_evening_briefing()
            except Exception as e:
                logger.error(f"Background data refresh failed: {e}")

        asyncio.create_task(_run())

        if wants_brief:
            return self._ok(request, result="Data refresh running — briefing will arrive in Telegram in a few minutes.")
        return self._ok(request, result="Data refresh running — RS, regime, and themes will be updated in a few minutes.")

    async def _handle_watchlist(self, request: AgentRequest) -> AgentResponse:
        """Manage the overnight watchlist — track/untrack instruments."""
        from agents.market_intelligence.db import (
            get_overnight_watchlist,
            upsert_watchlist_item,
            deactivate_watchlist_item,
        )
        task = request.task.lower()

        # Show watchlist
        if "watchlist" in task or "overnight watch" in task:
            items = await get_overnight_watchlist(active_only=False)
            if not items:
                return self._ok(request, result="Overnight watchlist is empty.")
            lines = ["*Overnight Watchlist*"]
            for i in items:
                status = "✓" if i["active"] else "✗"
                lines.append(f"{status} `{i['symbol']}` {i['display_name']} — threshold {i['threshold_pct']}% ({i['category']}) {i.get('notes', '')}")
            return self._ok(request, result="\n".join(lines))

        # Drop/untrack
        if any(k in task for k in ["untrack", "drop "]):
            # Extract symbol — use Claude to parse, or simple heuristic
            # Look for known symbols or uppercase words
            words = request.task.upper().split()
            symbol = None
            # Common mappings
            name_to_symbol = {
                "OIL": "CL=F", "CRUDE": "CL=F", "BITCOIN": "BTC-USD", "BTC": "BTC-USD",
                "GOLD": "GC=F", "VIX": "^VIX", "SPY": "SPY", "NASDAQ": "QQQ",
            }
            for w in words:
                if w in name_to_symbol:
                    symbol = name_to_symbol[w]
                    break
                if "=" in w or w.startswith("^") or "-" in w:
                    symbol = w
                    break
            if symbol:
                found = await deactivate_watchlist_item(symbol)
                if found:
                    return self._ok(request, result=f"Removed `{symbol}` from overnight watchlist.")
                return self._ok(request, result=f"Symbol `{symbol}` not found in watchlist.")
            return self._ok(request, result="Couldn't identify which instrument to remove. Try: 'drop oil' or 'untrack BTC-USD'")

        # Track new instrument
        if "track " in task:
            words = request.task.split()
            name_to_symbol = {
                "oil": ("CL=F", "Crude Oil", 3.0, "commodity"),
                "crude": ("CL=F", "Crude Oil", 3.0, "commodity"),
                "bitcoin": ("BTC-USD", "Bitcoin", 5.0, "crypto"),
                "btc": ("BTC-USD", "Bitcoin", 5.0, "crypto"),
                "gold": ("GC=F", "Gold", 2.0, "commodity"),
                "silver": ("SI=F", "Silver", 3.0, "commodity"),
                "bonds": ("^TNX", "10Y Treasury Yield", 3.0, "rates"),
                "treasury": ("^TNX", "10Y Treasury Yield", 3.0, "rates"),
                "dollar": ("DX-Y.NYB", "US Dollar Index", 1.0, "currency"),
                "euro": ("EURUSD=X", "EUR/USD", 1.0, "currency"),
                "natural gas": ("NG=F", "Natural Gas", 5.0, "commodity"),
                "gas": ("NG=F", "Natural Gas", 5.0, "commodity"),
            }
            # Try to find threshold in the message (e.g., "track bitcoin with 5% threshold")
            import re
            threshold_match = re.search(r'(\d+(?:\.\d+)?)\s*%', request.task)
            custom_threshold = float(threshold_match.group(1)) if threshold_match else None

            # Try to match a known name
            task_lower = task
            matched = None
            for name, info in name_to_symbol.items():
                if name in task_lower:
                    matched = info
                    break

            if matched:
                symbol, display, default_thresh, cat = matched
                thresh = custom_threshold or default_thresh
                # Extract notes if "because" or "note:" is in the message
                notes = ""
                for marker in ["because ", "note: ", "reason: "]:
                    if marker in task_lower:
                        notes = request.task[task_lower.index(marker) + len(marker):].strip()
                        break
                await upsert_watchlist_item(symbol, display, thresh, cat, notes)
                return self._ok(request, result=f"Added `{symbol}` ({display}) to overnight watchlist — threshold {thresh}%{' — ' + notes if notes else ''}")

            return self._ok(request, result="Couldn't identify the instrument. Try: 'track bitcoin', 'track gold', 'track oil', or specify a Yahoo Finance symbol.")

        return self._ok(request, result="Use: 'show watchlist', 'track bitcoin with 5% threshold', or 'drop oil'")

    async def _handle_theme_exclusion(self, request: AgentRequest) -> AgentResponse:
        """
        Manage persistent theme-level ticker exclusions.
        Once excluded, a ticker will never re-enter that theme regardless of RS or Haiku decisions.

        Commands:
          "exclude CAR from [theme name]" — add exclusion
          "remove exclusion CAR from [theme name]" — undo exclusion
          "list exclusions" / "show theme exclusions" — list all
        """
        import re as _re
        task = request.task.lower()
        task_orig = request.task

        # List exclusions
        if any(k in task for k in ["list exclusions", "show exclusions", "theme exclusions"]):
            rows = await list_theme_exclusions()
            if not rows:
                return self._ok(request, result="No theme exclusions set.")
            lines = ["*Persistent Theme Exclusions*"]
            for r in rows:
                lines.append(f"• `{r['ticker']}` excluded from _{r['theme_name']}_ — {r['reason'] or 'manual'}")
            return self._ok(request, result="\n".join(lines))

        # Extract ticker — first 2-5 letter uppercase word that looks like a ticker
        tickers_found = _re.findall(r'\b([A-Z]{2,5})\b', task_orig.upper())
        skip = _PREPOSITION_SKIP | {"EXCLUDE", "REMOVE", "FROM", "THEME", "BAN", "KICK", "LIST", "SHOW"}
        ticker = next((t for t in tickers_found if t not in skip), None)
        if not ticker:
            return self._ok(request, result="Couldn't identify a ticker. Try: 'exclude CAR from [theme name]'")

        # Check if this is a removal
        is_removal = any(k in task for k in ["remove exclusion", "unexclude", "allow back", "undo exclusion"])

        # Extract theme name — everything after "from" (or "from theme")
        theme_name = ""
        m = _re.search(r'\bfrom(?:\s+theme)?\s+(.+)', task_orig, _re.IGNORECASE)
        if m:
            theme_name = m.group(1).strip()
            # Remove any trailing punctuation
            theme_name = theme_name.rstrip(".,!?")

        if not theme_name:
            return self._ok(request, result=f"Couldn't extract theme name. Try: 'exclude {ticker} from [exact theme name]'")

        if is_removal:
            removed = await remove_theme_exclusion(ticker, theme_name)
            if removed:
                return self._ok(request, result=f"Exclusion lifted: `{ticker}` can now re-enter _{theme_name}_.")
            return self._ok(request, result=f"No exclusion found for `{ticker}` in _{theme_name}_.")
        else:
            reason = f"manually excluded by user"
            await add_theme_exclusion(ticker, theme_name, reason)
            return self._ok(
                request,
                result=(
                    f"Done. `{ticker}` is now permanently excluded from _{theme_name}_.\n"
                    f"It will be stripped on the next theme engine run and can never re-enter that theme.\n"
                    f"To undo: 'remove exclusion {ticker} from {theme_name}'"
                ),
            )

    async def _handle_restore_themes(self, request: AgentRequest) -> AgentResponse:
        """
        Full recovery from auto-validation accumulating exclusions and retiring themes.
        Clears all auto-generated exclusions + unretires recently retired themes.
        Follow with 'rerun theme engine' to re-score.
        """
        from datetime import timedelta
        today = et_today()
        # Look back 5 days to catch all nightly validation damage since feature was added
        since = today - timedelta(days=5)
        result = await restore_recently_retired_themes(since)
        themes = result["themes_restored"]
        exclusions = result["exclusions_cleared"]
        if themes == 0 and exclusions == 0:
            return self._ok(request, result="Nothing to restore — no retired themes or auto-exclusions found in the last 5 days.")
        return self._ok(
            request,
            result=(
                f"Recovery complete:\n"
                f"• {exclusions} auto-generated theme exclusions cleared\n"
                f"• {themes} incorrectly retired themes restored to prior state\n\n"
                f"Run 'rerun theme engine' to re-score everything with today's RS data."
            ),
        )

    async def _handle_audit_log(self, request: AgentRequest) -> AgentResponse:
        """
        Fetch and display recent critical events from the audit log.
        Commands:
          "audit log" / "show logs" — last 20 events (48h)
          "advisor log" — only advisor_call events
          "show logs 7d" — last 7 days
        """
        import re as _re
        task = request.task.lower()

        # Parse optional time window (e.g. "7d", "24h")
        since_hours = 48
        m = _re.search(r'(\d+)\s*d\b', task)
        if m:
            since_hours = int(m.group(1)) * 24
        else:
            m = _re.search(r'(\d+)\s*h\b', task)
            if m:
                since_hours = int(m.group(1))

        # Filter by event type if specified
        event_type = None
        if "advisor" in task:
            event_type = "advisor_call"
        elif "discover" in task or "new theme" in task:
            event_type = "theme_discovered"
        elif "retire" in task:
            event_type = "theme_retired"
        elif "stage" in task:
            event_type = "stage_change"
        elif "exclusion" in task or "excluded" in task:
            event_type = "theme_excluded"
        elif "orb" in task:
            event_type = "orb_triggered"

        rows = await get_audit_log(limit=25, event_type=event_type, since_hours=since_hours)

        if not rows:
            label = f"last {since_hours}h" + (f" [{event_type}]" if event_type else "")
            return self._ok(request, result=f"No audit log entries in {label}.")

        _TYPE_EMOJI = {
            "advisor_call":     "🤖",
            "theme_discovered": "🌱",
            "theme_retired":    "🪦",
            "stage_change":     "📈",
            "theme_excluded":   "🚫",
            "ep_alert":         "⚡",
            "orb_triggered":    "🎯",
            "orb_filtered":     "⊘",
            "orb_bar_miss":     "⏳",
            "orb_bar_fetched":  "📊",
            "orb_no_bar":       "❌",
            "orb_order_placed": "✅",
            "orb_order_failed": "🚨",
        }

        lines = [f"*Audit Log* — last {since_hours}h{' · ' + event_type if event_type else ''}"]
        for r in rows:
            ts = r["created_at"].strftime("%m/%d %H:%M")
            emoji = _TYPE_EMOJI.get(r["event_type"], "•")
            lines.append(f"{emoji} `{ts}` {r['summary']}")

        # If asking for advisor log, show detail for each entry
        if event_type == "advisor_call" and len(rows) <= 10:
            lines = [f"*Advisor Log* — last {since_hours}h"]
            for r in rows:
                ts = r["created_at"].strftime("%m/%d %H:%M")
                detail = r.get("detail", "")
                # Extract verdict from detail (after "Verdict:")
                verdict = ""
                if "Verdict:" in detail:
                    verdict = detail.split("Verdict:")[-1].strip()[:300]
                lines.append(f"\n`{ts}` 🤖 *{r['summary'][:80]}*")
                if verdict:
                    lines.append(f"_{verdict}_")

        return self._ok(request, result="\n".join(lines))

    async def _handle_ep_outcomes(self, request: AgentRequest) -> AgentResponse:
        """
        Show EP outcomes grouped by what actually happened: traded, filtered by rule, or not attempted.
        Purpose: audit whether our entry filters are correctly calibrated.
        Excludes pre-Claude 'unknown' catalyst records (Jan-Feb 2026 early scans).
        """
        import re as _re
        from statistics import mean
        task = request.task.lower()

        tier = None
        if "high" in task:
            tier = "HIGH"
        elif "moderate" in task or "mod" in task:
            tier = "MODERATE"

        days = 90
        m = _re.search(r'(\d+)\s*d(?:ay)?s?', task)
        if m:
            days = min(int(m.group(1)), 180)

        include_unknown = "all" in task or "unknown" in task

        rows = await get_ep_outcomes(days_back=days, tier=tier, include_unknown=include_unknown)

        if not rows:
            return self._ok(
                request,
                result=(
                    "*EP Outcomes* — no Claude-scored alerts in window\n"
                    "_Early records (Jan-Feb) used a placeholder scorer and are excluded.\n"
                    "Add 'all' to include them: 'ep outcomes all'_"
                ),
            )

        def _pct(v, w=6) -> str:
            if v is None:
                return "—".rjust(w)
            return f"{'+'if v>=0 else ''}{v:.1f}%".rjust(w)

        def _pnl(v) -> str:
            if v is None:
                return "—"
            return f"${v:+.0f}"

        traded     = [r for r in rows if r["trade_status"] == "traded"]
        filtered   = [r for r in rows if r["trade_status"] == "filtered"]
        no_attempt = [r for r in rows if r["trade_status"] == "no_attempt"]

        tier_label = f" ({tier})" if tier else ""
        lines = [f"*EP Outcomes — last {days}d{tier_label}*"]
        lines.append("Traded = ORB entered. Filtered = rule rejected at gate. D1/D5 = fwd returns.")
        lines.append("")

        # ── Section 1: Traded ──────────────────────────────────────────────────
        lines.append(f"*TRADED ({len(traded)})*")
        if not traded:
            lines.append("None yet.")
        else:
            lines.append("```")
            lines.append("Ticker  Date        P&L      D1      D5")
            lines.append("------  ----------  -------  ------  ------")
            for r in traded:
                ticker_s = r["ticker"].ljust(6)
                dt       = str(r["alert_date"])[:10]
                pnl_s    = _pnl(r.get("total_pnl")).rjust(7)
                d1       = _pct(r.get("fwd_1d_pct"))
                d5       = _pct(r.get("fwd_1w_pct"))
                lines.append(f"{ticker_s}  {dt}  {pnl_s}  {d1}  {d5}")
            lines.append("```")
            pnl_vals = [r["total_pnl"] for r in traded if r.get("total_pnl") is not None]
            if pnl_vals:
                wins = sum(1 for v in pnl_vals if v > 0)
                lines.append(f"Win rate: {wins}/{len(pnl_vals)} · Total P&L: {_pnl(sum(pnl_vals))}")
        lines.append("")

        # ── Section 2: Filtered by rule ────────────────────────────────────────
        lines.append(f"*FILTERED ({len(filtered)})*")
        lines.append("ORB gate ran but rejected — check D1 to see if we missed good entries.")
        if not filtered:
            lines.append("None in this window.")
        else:
            lines.append("```")
            lines.append("Ticker  Date        Skip reason           D1      D5")
            lines.append("------  ----------  --------------------  ------  ------")
            for r in filtered:
                ticker_s = r["ticker"].ljust(6)
                dt       = str(r["alert_date"])[:10]
                reason_s = (r.get("skip_reason") or "?")[:20].ljust(20)
                d1       = _pct(r.get("fwd_1d_pct"))
                d5       = _pct(r.get("fwd_1w_pct"))
                lines.append(f"{ticker_s}  {dt}  {reason_s}  {d1}  {d5}")
            lines.append("```")
            filter_d1 = [r for r in filtered if r.get("fwd_1d_pct") is not None]
            if filter_d1:
                avg = mean(r["fwd_1d_pct"] for r in filter_d1)
                wins = sum(1 for r in filter_d1 if r["fwd_1d_pct"] > 0)
                flag = " — rules may be too strict" if avg > 3 else ""
                lines.append(f"Filtered avg D1: {'+'if avg>=0 else ''}{avg:.1f}% ({wins}/{len(filter_d1)} up){flag}")
        lines.append("")

        # ── Section 3: No ORB attempt ──────────────────────────────────────────
        if no_attempt:
            moderate = [r for r in no_attempt if r.get("score_tier") == "MODERATE"]
            high_missed = [r for r in no_attempt if r.get("score_tier") == "HIGH"]
            lines.append(f"*NO ORB ATTEMPT ({len(no_attempt)})*")
            if moderate:
                tickers = ", ".join(r["ticker"] for r in moderate)
                lines.append(f"MODERATE ({len(moderate)}): {tickers}")
                lines.append("  By design — system only enters HIGH alerts. MODERATE are morning briefing only.")
            if high_missed:
                tickers = ", ".join(r["ticker"] for r in high_missed)
                lines.append(f"HIGH missed ({len(high_missed)}): {tickers}")
                lines.append("  Paper tracker wasn't running on these dates (early setup period).")

        return self._ok(request, result="\n".join(lines))

    async def _handle_journal_add(self, request: AgentRequest) -> AgentResponse:
        """Log a trade observation with auto-enriched market context."""
        import re as _re
        task = request.task

        # Strip routing prefix to get the user's note
        entry_text = _re.sub(
            r'^(?:journal[:\s]+|log trade[:\s]+|note trade[:\s]+|add journal[:\s]+)',
            '', task, flags=_re.IGNORECASE
        ).strip()

        if not entry_text:
            return self._ok(
                request,
                result="Include your note after the command — e.g.\n`journal: bought NVDA at 142, EP breakout`",
            )

        today_str = et_today().strftime("%Y-%m-%d")
        regime_data, ep_alerts, themes = await asyncio.gather(
            get_current_regime(),
            get_today_ep_alerts(today_str),
            get_today_themes(today_str),
        )

        regime_str = (regime_data or {}).get("regime", "Unknown")

        ep_context = None
        if ep_alerts:
            ep_context = [
                {
                    "ticker": a["ticker"],
                    "ep_score": a.get("ep_score"),
                    "tier": a.get("score_tier"),
                    "catalyst": a.get("catalyst_quality"),
                    "gap_pct": a.get("gap_pct"),
                }
                for a in ep_alerts
            ]

        theme_context = None
        accel = [t for t in (themes or []) if t.get("stage") == "Accelerating"]
        if accel:
            from agents.market_intelligence.briefing import _conviction_suffix
            parts = []
            for t in accel[:5]:
                suffix = _conviction_suffix(t)
                parts.append(f"{t['name']}{suffix}")
            theme_context = "Accelerating: " + ", ".join(parts)

        entry_id = await add_journal_entry(
            text=entry_text,
            regime=regime_str,
            ep_context=ep_context,
            theme_context=theme_context,
        )

        lines = [f"*Journal #{entry_id} saved*", f"_{entry_text}_", ""]
        lines.append(f"*Regime:* {regime_str}")
        if ep_context:
            tickers = ", ".join(f"`{e['ticker']}`" for e in ep_context)
            lines.append(f"*EPs today:* {tickers}")
        else:
            lines.append("*EPs today:* None")
        if theme_context:
            lines.append(f"*Themes:* {theme_context}")

        return self._ok(request, result="\n".join(lines))

    async def _handle_journal_query(self, request: AgentRequest) -> AgentResponse:
        """Show recent journal entries."""
        import re as _re
        task = request.task.lower()

        days = 7
        if "today" in task:
            days = 1
        elif "this week" in task or "week" in task:
            days = 7
        elif "this month" in task or "month" in task:
            days = 30
        else:
            m = _re.search(r'(\d+)\s*d(?:ay)?s?', task)
            if m:
                days = min(int(m.group(1)), 90)

        entries = await get_journal_entries(days_back=days, limit=20)

        if not entries:
            period = "today" if days == 1 else f"the last {days} days"
            return self._ok(
                request,
                result=(
                    f"No journal entries for {period}.\n"
                    "Add one with: `journal: bought NVDA at 142, EP breakout`"
                ),
            )

        lines = [f"*Journal — last {days} day(s)* ({len(entries)} entries)"]
        for e in entries:
            created = e["created_at"]
            ts = created.strftime("%b %d %H:%M") if hasattr(created, "strftime") else str(created)[:16]
            lines.append(f"\n*#{e['id']}* _{ts}_")
            lines.append(e["entry_text"])
            meta = []
            if e.get("regime"):
                meta.append(f"Regime: {e['regime']}")
            if e.get("ep_context"):
                ep_tickers = [ep["ticker"] for ep in e["ep_context"] if ep.get("ticker")]
                if ep_tickers:
                    meta.append(f"EPs: {', '.join(ep_tickers)}")
            if e.get("theme_context"):
                meta.append(e["theme_context"])
            if meta:
                lines.append(f"  _{'  |  '.join(meta)}_")

        return self._ok(request, result="\n".join(lines))

    async def _handle_trades_query(self, request: AgentRequest, ticker: str | None = None) -> AgentResponse:
        """
        Show paper trade history with entry/exit prices, P&L, stops.
        'my trades' / 'show trades'     — recent 20 trades (all statuses)
        'open trades'                   — only open positions
        'closed trades'                 — only closed
        'paper p&l'                     — running totals only
        'entry/exit for TVTX'           — single ticker detail

        When LIVE_TRADING_ENABLED=true, queries mi_live_trades (Alpaca paper).
        When false, queries mi_paper_trades (EOD sim).
        """
        from agents.market_intelligence.constants import LIVE_TRADING_ENABLED
        task = request.task.lower()
        pool = await get_pool()

        where_clauses = ["1=1"]
        params: list = []

        if LIVE_TRADING_ENABLED:
            # mi_live_trades: "open" = filled + remaining_shares > 0
            table = "mi_live_trades"
            entry_col = "entry_price"
            if ticker:
                where_clauses.append(f"ticker = ${len(params)+1}")
                params.append(ticker.upper())
            if "open" in task and "closed" not in task:
                where_clauses.append("status IN ('filled', 'order_placed') AND remaining_shares > 0")
            elif "closed" in task and "open" not in task:
                where_clauses.append(f"status = ${len(params)+1}")
                params.append("closed")
            elif "skipped" in task or "filtered" in task:
                where_clauses.append("status IN ('skipped', 'cancelled', 'order_failed')")
            open_statuses = ("filled", "order_placed", "pending_confirmation", "confirmed")
            label = "Paper Trade History (Alpaca)"
        else:
            table = "mi_paper_trades"
            entry_col = "last_entry_price"
            if ticker:
                where_clauses.append(f"ticker = ${len(params)+1}")
                params.append(ticker.upper())
            if "open" in task and "closed" not in task:
                where_clauses.append(f"status = ${len(params)+1}")
                params.append("open")
            elif "closed" in task and "open" not in task:
                where_clauses.append(f"status = ${len(params)+1}")
                params.append("closed")
            elif "skipped" in task or "filtered" in task:
                where_clauses.append(f"status = ${len(params)+1}")
                params.append("skipped")
            open_statuses = ("open",)
            label = "Paper Trade History (EOD sim)"

        where = " AND ".join(where_clauses)

        # mi_paper_trades has entries column; mi_live_trades does not
        entries_col = "entries" if not LIVE_TRADING_ENABLED else "NULL::jsonb AS entries"
        async with pool.acquire() as conn:
            rows = await conn.fetch(f"""
                SELECT ticker, alert_date, ep_score, gap_pct, catalyst_quality, regime,
                       status, skip_reason,
                       {entry_col} AS entry_price, orb_high, orb_low, stop_price,
                       total_pnl, hold_days,
                       exits, {entries_col}
                FROM {table}
                WHERE {where}
                ORDER BY alert_date DESC
                LIMIT 20
            """, *params)

            # Running totals
            if LIVE_TRADING_ENABLED:
                totals = await conn.fetchrow("""
                    SELECT
                        COUNT(*) FILTER (WHERE status NOT IN ('skipped','cancelled','order_failed')) as total,
                        COUNT(*) FILTER (WHERE status IN ('filled','order_placed') AND remaining_shares > 0) as open_count,
                        COUNT(*) FILTER (WHERE status = 'closed' AND total_pnl > 0)  as winners,
                        COUNT(*) FILTER (WHERE status = 'closed' AND total_pnl <= 0) as losers,
                        COALESCE(SUM(total_pnl) FILTER (WHERE status = 'closed'), 0) as realized_pnl,
                        COUNT(*) FILTER (WHERE status IN ('skipped','cancelled','order_failed')) as filtered_count
                    FROM mi_live_trades
                """)
            else:
                totals = await conn.fetchrow("""
                    SELECT
                        COUNT(*) FILTER (WHERE status NOT IN ('skipped')) as total,
                        COUNT(*) FILTER (WHERE status = 'open')           as open_count,
                        COUNT(*) FILTER (WHERE status = 'closed' AND total_pnl > 0)  as winners,
                        COUNT(*) FILTER (WHERE status = 'closed' AND total_pnl <= 0) as losers,
                        COALESCE(SUM(total_pnl) FILTER (WHERE status = 'closed'), 0) as realized_pnl,
                        COUNT(*) FILTER (WHERE status = 'skipped') as filtered_count
                    FROM mi_paper_trades
                """)

        if not rows and not ticker:
            return self._ok(request, result="No paper trades recorded yet.")
        if not rows and ticker:
            return self._ok(request, result=f"No paper trades found for {ticker.upper()}.")

        from agents.market_intelligence.backtester.tracker import parse_json_list, format_trade_attempts, _attempt_count

        lines = [f"*{label}*\n"]

        is_skipped = lambda r: r["status"] not in ("open", "closed", "filled", "order_placed", "pending_confirmation", "confirmed")

        for r in rows:
            is_open = r["status"] in open_statuses
            pnl_positive = (r["total_pnl"] or 0) > 0
            status_emoji = "🟡" if is_open else ("✅" if pnl_positive else ("⊘" if is_skipped(r) else "❌"))
            date_str = r["alert_date"].strftime("%b %d")
            score = f"score={r['ep_score']:.0f}" if r["ep_score"] else ""
            gap = f"gap={r['gap_pct']:.1f}%" if r["gap_pct"] else ""

            num_attempts = _attempt_count(r.get("entries"))
            att_str = f" {num_attempts}x" if num_attempts > 1 else ""

            header = f"{status_emoji} *{r['ticker']}* {date_str} {gap} {score}{att_str}"
            lines.append(header)

            if is_skipped(r):
                lines.append(f"  Filtered: {r['skip_reason'] or 'unknown'}")
                continue

            lines += format_trade_attempts(r.get("entries"), r.get("exits"), prefix="  ")

            # Summary
            if not is_open:
                lines.append(f"  *Total P&L: ${r['total_pnl']:+,.2f}* ({r['hold_days']}d)")
            else:
                stop_str = f"  Stop: ${r['stop_price']:.2f}" if r["stop_price"] else ""
                lines.append(f"  Open — {r['hold_days']}d{stop_str}")

        # Totals footer
        t = totals
        closed_count = (t["winners"] or 0) + (t["losers"] or 0)
        win_rate = (t["winners"] / closed_count * 100) if closed_count > 0 else 0
        lines.append(
            f"\n*Totals:* {t['total']} traded · {t['open_count']} open · "
            f"{closed_count} closed ({win_rate:.0f}% win) · "
            f"P&L ${float(t['realized_pnl']):+,.2f} · {t['filtered_count']} filtered"
        )

        return self._ok(request, result="\n".join(lines))

    async def _handle_theme_only(self, request: AgentRequest) -> AgentResponse:
        """Re-run just the theme engine using existing RS data. No Polygon calls — fast.

        Awaits the full theme engine run (no background task) so the result flows back
        through the normal orchestrator→Telegram channel. Orchestrator timeout is 360s.
        Returns a stage-grouped scorecard in the same format as the evening brief.
        """
        from agents.market_intelligence.briefing import _compute_scored_themes, STAGE_EMOJI, _conviction_suffix

        task_lower = request.task.lower()
        wants_brief = any(k in task_lower for k in ["brief", "send", "briefing"])
        today_str = et_today().strftime("%Y-%m-%d")

        try:
            logger.info("Theme-only run starting...")
            themes, changelog = await run_theme_engine()
            logger.info("Theme-only run complete")

            # Get RS data for all theme tickers + prior scores (for delta)
            all_tickers = list({tk for t in themes for tk in (t.get("tickers") or [])})
            if all_tickers:
                theme_rs_data, prior_scores = await asyncio.gather(
                    get_rs_for_tickers(today_str, all_tickers),
                    get_prior_theme_scores(today_str),
                )
            else:
                theme_rs_data, prior_scores = {}, {}

            scored_themes, fading = _compute_scored_themes(themes, theme_rs_data, prior_scores or {})

            # Group by stage
            stage_order = ["Accelerating", "Nascent", "Mainstream"]
            stage_groups: dict[str, list] = {s: [] for s in stage_order}
            for st in scored_themes:
                stage_groups.setdefault(st.get("stage", "Nascent"), []).append(st)

            lines = [f"*THEME ENGINE — {len(scored_themes)} active*"]

            # Changelog notes (removals/pruning)
            revalidated = [e for e in changelog if e.get("type") == "ticker_revalidated_out"]
            pruned = [e for e in changelog if e.get("type") == "ticker_pruned"]
            if revalidated:
                removed = ", ".join(f"{e['ticker']} from {e['theme']}" for e in revalidated)
                lines.append(f"_Removed: {removed}_")
            if pruned:
                lines.append(f"_Pruned {len(pruned)} weak stock(s)_")

            for stage in stage_order:
                group = stage_groups.get(stage, [])
                if not group:
                    continue
                emoji = STAGE_EMOJI.get(stage, "")
                lines.append(f"\n{emoji} *{stage.upper()}* ({len(group)})")
                for st in group:
                    theme_emoji = STAGE_EMOJI.get(st["stage"], " ")
                    delta_str = f"  Δ{st['delta']:+.1f}" if st["delta"] is not None else ""
                    conviction = _conviction_suffix(st)
                    lines.append(f"\n{theme_emoji}*{st['name']}*{conviction}")
                    lines.append(
                        f"  RS {int(st['comp'])} (1M {int(st['rs_1m'])} | 3M {int(st['rs_3m'])} | 6M {int(st['rs_6m'])}){delta_str}"
                    )
                    ticker_rs = [
                        (tk, theme_rs_data[tk]["rs_composite"])
                        for tk in st["tickers"]
                        if theme_rs_data.get(tk, {}).get("rs_composite") is not None
                        and theme_rs_data[tk]["rs_composite"] >= 50
                    ]
                    ticker_rs.sort(key=lambda x: -x[1])
                    top = " · ".join(f"{tk} {int(rs)}" for tk, rs in ticker_rs[:5])
                    if top:
                        lines.append(f"  {top}")

            if fading:
                fading_names = " · ".join(t.get("name", "?") for t in fading[:5])
                lines.append(f"\n🔻 _Fading: {fading_names}_")

            if wants_brief:
                asyncio.create_task(send_evening_briefing())
                lines.append("\n_Evening briefing sending..._")

            return self._ok(request, result="\n".join(lines))
        except PerplexityUnavailableError as e:
            # Hard abort — Perplexity is down (401/402). Already sent Telegram alert from
            # run_theme_engine. Surface the error explicitly — no silent fallback.
            return self._error(
                request,
                error=(
                    f"🚨 Theme engine ABORTED — Perplexity API unavailable.\n\n"
                    f"{e}\n\n"
                    f"No theme data was changed. Add API credits then retry."
                ),
            )
        except Exception as e:
            logger.error(f"Theme-only run failed: {e}", exc_info=True)
            return self._error(request, error=f"Theme engine failed: {e}")

    async def _handle_ep_query(self, request: AgentRequest) -> AgentResponse:
        today_str = et_today().strftime("%Y-%m-%d")
        alerts = await get_today_ep_alerts(today_str)
        regime = await get_current_regime()

        if not alerts:
            result = (
                f"No EP alerts for {today_str}.\n"
                f"Market regime: {regime.get('regime')} (EP bar: {regime.get('ep_threshold')}+).\n"
                f"EP scanning runs every 5 min from 7:00–9:30 AM ET."
            )
        else:
            high = [e for e in alerts if e.get("score_tier") == "HIGH"]
            moderate = [e for e in alerts if e.get("score_tier") == "MODERATE"]
            lines = [f"EP alerts for {today_str}: {len(high)} HIGH, {len(moderate)} MODERATE\n"]
            for ep in alerts:
                lines.append(
                    f"• *{ep['ticker']}* — {ep['score_tier']} (score {ep['ep_score']:.0f}) "
                    f"gap {ep['gap_pct']:.1f}% | {ep.get('catalyst_quality', '?')} catalyst\n"
                    f"  {ep.get('claude_analysis', '')}"
                )
            result = "\n".join(lines)

        return self._ok(request, result=result, data={"ep_alerts": alerts})

    async def _handle_ep_diagnostic(self, ticker: str, request: AgentRequest) -> AgentResponse:
        """
        Diagnose why a specific ticker was not flagged as an EP.
        Checks scan log first (definitive), then reconstructs from current data.
        Fetches real news so the answer is specific — not generic.
        """
        from datetime import timedelta

        today = et_today()
        today_str = today.strftime("%Y-%m-%d")

        lines = [f"`{ticker}` — EP Diagnostic\n"]
        root_cause = None

        # ── Check scan log first — definitive if we have it ──────────────────
        scan_entry = None
        try:
            day_log = await get_ep_scan_log(today_str)
            scan_entry = next((r for r in day_log if r["ticker"] == ticker), None)
            if not scan_entry:
                # Check yesterday too (gap may have been yesterday's event)
                yesterday_log = await get_ep_scan_log((today - timedelta(days=1)).strftime("%Y-%m-%d"))
                scan_entry = next((r for r in yesterday_log if r["ticker"] == ticker), None)
        except Exception:
            pass

        if scan_entry:
            if scan_entry.get("filter_reason"):
                root_cause = scan_entry["filter_reason"]
                lines.append(f"❌ *Scan log says*: {root_cause}")
                if scan_entry.get("gap_pct"):
                    lines.append(f"   Gap at scan time: {scan_entry['gap_pct']:.1f}%")
            elif scan_entry.get("ep_score"):
                score = scan_entry["ep_score"]
                tier = scan_entry.get("score_tier") or "below threshold"
                lines.append(f"✅ Passed all filters — scored {score:.0f} ({tier})")
                if tier not in ("HIGH", "MODERATE"):
                    root_cause = f"score {score:.0f} was below the MODERATE threshold (50)"
            lines.append("")

        # ── Reconstruct from current data if no scan log entry ───────────────
        if not scan_entry:
            lines.append("_(No scan log entry found — reconstructing from current data)_\n")

        pool = await _pool()

        async def _get_recent_closes():
            async with pool.acquire() as conn:
                rows = await conn.fetch(
                    """SELECT trade_date, close, volume FROM mi_daily_closes
                       WHERE ticker = $1 ORDER BY trade_date DESC LIMIT 10""",
                    ticker,
                )
            return [dict(r) for r in rows]

        async def _get_recent_ep():
            async with pool.acquire() as conn:
                rows = await conn.fetch(
                    """SELECT alert_date, ep_score, score_tier, gap_pct
                       FROM mi_ep_alerts WHERE ticker = $1
                       ORDER BY alert_date DESC LIMIT 3""",
                    ticker,
                )
            return [dict(r) for r in rows]

        closes_data, recent_ep, rs_result, regime, news = await asyncio.gather(
            _get_recent_closes(),
            _get_recent_ep(),
            score_single_ticker(ticker),
            get_current_regime(),
            search_news_perplexity(
                f"What happened with {ticker} stock recently? Why did it move? Latest catalyst.",
                recency="week",
            ),
            return_exceptions=True,
        )

        if isinstance(closes_data, Exception):
            closes_data = []
        if isinstance(recent_ep, Exception):
            recent_ep = []
        if isinstance(rs_result, Exception):
            rs_result = {}
        if isinstance(regime, Exception):
            regime = {}
        if isinstance(news, Exception):
            news = ""

        ep_threshold = regime.get("ep_threshold", 70) if isinstance(regime, dict) else 70
        regime_label = regime.get("regime", "Unknown") if isinstance(regime, dict) else "Unknown"

        # ── Run filters in order, same as ep_detector.py ─────────────────────

        # 1. Price filter
        prev_close = closes_data[0]["close"] if closes_data else None
        if prev_close is not None:
            if prev_close < MIN_PREV_CLOSE:
                root_cause = f"Price ${prev_close:.2f} is below the ${MIN_PREV_CLOSE:.0f} minimum — sub-${MIN_PREV_CLOSE:.0f} stocks are filtered before any other checks."
                lines.append(f"❌ *Price filter*: ${prev_close:.2f} < ${MIN_PREV_CLOSE:.0f} minimum\n   → {root_cause}")
            else:
                lines.append(f"✅ Price: ${prev_close:.2f} (≥ ${MIN_PREV_CLOSE:.0f})")
        else:
            lines.append("⚠️ Price: no data in universe — ticker not tracked in mi_daily_closes")
            root_cause = f"{ticker} has no price history in the system. It was never scored by the RS engine and can't be evaluated by the EP scanner."

        # 2. Extension filter (already up 50%+ in prior 5 days before the gap)
        if root_cause is None and len(closes_data) >= 6:
            close_5d_ago = closes_data[5]["close"]
            prev = closes_data[0]["close"]
            if close_5d_ago and close_5d_ago > 0:
                extension_pct = (prev - close_5d_ago) / close_5d_ago * 100
                if extension_pct >= MAX_EXTENSION_PCT:
                    root_cause = f"Already up {extension_pct:.0f}% in the prior 5 days — the EP scanner skips stocks that have already run ≥{MAX_EXTENSION_PCT:.0f}% before the gap day."
                    lines.append(f"❌ *Extension filter*: up {extension_pct:.0f}% in last 5 days (max {MAX_EXTENSION_PCT:.0f}%)\n   → {root_cause}")
                else:
                    lines.append(f"✅ Extension: +{extension_pct:.1f}% over 5 days (< {MAX_EXTENSION_PCT:.0f}% limit)")

        # 3. EP cooldown (prior alert within 60 days)
        if root_cause is None and recent_ep:
            days_since = (today - recent_ep[0]["alert_date"]).days if hasattr(recent_ep[0]["alert_date"], "day") else 999
            if days_since < EP_COOLDOWN_DAYS:
                root_cause = f"EP alert was triggered {days_since} days ago (cooldown is {EP_COOLDOWN_DAYS} days). Same ticker won't re-alert until the cooldown expires."
                lines.append(f"❌ *Cooldown*: EP alert {days_since}d ago — cooldown is {EP_COOLDOWN_DAYS}d\n   → {root_cause}")
            else:
                lines.append(f"✅ Cooldown: last EP was {days_since}d ago (> {EP_COOLDOWN_DAYS}d)")
        elif root_cause is None:
            lines.append(f"✅ Cooldown: no prior EP alerts")

        # 4. RS vs regime threshold (informational — RS is not a hard filter but affects score)
        if root_cause is None:
            if isinstance(rs_result, dict) and "rs_composite" in rs_result:
                rs = rs_result["rs_composite"]
                lines.append(f"{'✅' if rs >= ep_threshold else '⚠️'} RS: {rs:.0f}  |  Regime: {regime_label} (EP bar: {ep_threshold}+)")
                if rs < ep_threshold:
                    lines.append(f"   → RS {rs:.0f} is below the {ep_threshold} threshold for {regime_label} regime. Score could still reach the bar with a strong catalyst and big gap, but it's harder.")
            else:
                lines.append(f"⚠️ RS: no score available — ticker may not be in the RS universe")

        # 5. Gap size check (if we can infer from recent closes)
        if root_cause is None and len(closes_data) >= 2:
            # Best estimate: today's close vs yesterday's close
            today_close = closes_data[0]["close"]
            prev = closes_data[1]["close"]
            implied_gap = (today_close - prev) / prev * 100 if prev else 0
            if implied_gap < MIN_GAP_PCT:
                root_cause = f"Implied gap {implied_gap:.1f}% is below the {MIN_GAP_PCT:.0f}% minimum. This may reflect a within-day move rather than an overnight gap."
                lines.append(f"❌ *Gap size*: ~{implied_gap:.1f}% (minimum is {MIN_GAP_PCT:.0f}%)\n   → {root_cause}")
            else:
                lines.append(f"✅ Gap: ~{implied_gap:.1f}% (≥ {MIN_GAP_PCT:.0f}%)")

        # ── Summary ───────────────────────────────────────────────────────────
        lines.append("")
        if root_cause:
            lines.append(f"*Root cause*: {root_cause}")
        else:
            lines.append(
                f"*No hard filter failure found.* {ticker} may have been:\n"
                f"• Ranked outside the top-20 gap candidates at scan time (only top 20 by gap% are scored)\n"
                f"• EP score below {ep_threshold} after MAGNA53 scoring (catalyst classified as routine)\n"
                f"• The gap happened after the 9:30 AM ET scan window closed"
            )

        # ── News context ──────────────────────────────────────────────────────
        if news and isinstance(news, str) and len(news) > 20:
            lines.append(f"\n*What happened*: {news[:600].strip()}")
        elif not news:
            lines.append("\n*News*: no recent catalyst found via search")

        return self._ok(request, result="\n".join(lines))

    async def _handle_ep_history(self, request: AgentRequest) -> AgentResponse:
        """Show EP alerts + filtered candidates from the past N days grouped by date."""
        import re as _re
        task = request.task.lower()

        # Parse optional day window — "last 7 days", "7d", "past 30 days"
        days = 14
        m = _re.search(r'(\d+)\s*d(?:ay)?s?', task)
        if m:
            days = min(int(m.group(1)), 90)

        alerts, scan_log = await asyncio.gather(
            get_ep_history(days),
            get_ep_scan_log_history(days),
            return_exceptions=True,
        )
        if isinstance(alerts, Exception):
            alerts = []
        if isinstance(scan_log, Exception):
            scan_log = {}

        if not alerts and not scan_log:
            return self._ok(request, result=f"No EP scan data in the past {days} days.")

        # Build per-date alert index
        from collections import defaultdict
        alerts_by_date: dict = defaultdict(list)
        for a in (alerts or []):
            alerts_by_date[str(a["alert_date"])].append(a)

        # All dates with any activity
        all_dates = sorted(set(list(alerts_by_date.keys()) + list(scan_log.keys())), reverse=True)

        lines = [f"*EP Scan Log — last {days} days*\n"]
        for dt in all_dates:
            day_alerts = alerts_by_date.get(dt, [])
            day_scan = scan_log.get(dt, [])
            # Filtered = in scan log with a filter_reason (not None)
            filtered = [r for r in day_scan if r.get("filter_reason")]

            high = [a for a in day_alerts if a.get("score_tier") == "HIGH"]
            mod  = [a for a in day_alerts if a.get("score_tier") == "MODERATE"]
            header = f"*{dt}*"
            parts = []
            if high or mod:
                parts.append(f"{len(high)} HIGH  {len(mod)} MODERATE")
            if filtered:
                parts.append(f"{len(filtered)} filtered")
            lines.append(f"{header} — " + ("  |  ".join(parts) if parts else "no activity"))

            for a in day_alerts:
                tier_icon = "🔥" if a.get("score_tier") == "HIGH" else "⚡"
                rs_str = f"  RS {a['rs_composite']:.0f}" if a.get("rs_composite") else ""
                lines.append(
                    f"  {tier_icon} `{a['ticker']}` score {a['ep_score']:.0f}"
                    f"  gap {a['gap_pct']:.1f}%  {a.get('catalyst_quality','?')}{rs_str}"
                )

            for r in filtered:
                lines.append(
                    f"  ✗ `{r['ticker']}` gap {r['gap_pct']:.1f}%"
                    f"  — {r['filter_reason']}"
                )
            lines.append("")

        return self._ok(request, result="\n".join(lines).strip(), data={"ep_alerts": alerts})

    async def _handle_regime_query(self, request: AgentRequest) -> AgentResponse:
        regime = await get_current_regime()
        label = regime.get("regime", "Unknown")
        desc = regime.get("description", "")
        threshold = regime.get("ep_threshold", 70)

        result = (
            f"Market Regime: *{label}*\n"
            f"EP threshold: {threshold}+\n\n"
            f"{desc}"
        )
        return self._ok(request, result=result, data=regime)

    async def _handle_rs_query(self, request: AgentRequest) -> AgentResponse:
        today_str = et_today().strftime("%Y-%m-%d")
        leaders = await get_rs_leaders(today_str, limit=20)

        if not leaders:
            return self._ok(
                request,
                result="No RS data yet. Run `/data/refresh` or wait for the nightly 6 AM pull.",
            )

        # Group by sector
        by_sector: dict[str, list] = {}
        no_sector = []
        for s in leaders:
            sector = s.get("sector")
            if sector:
                by_sector.setdefault(sector, []).append(s)
            else:
                no_sector.append(s)

        lines = [f"Top RS leaders ({today_str}):"]
        if by_sector:
            for sector, stocks in list(by_sector.items())[:8]:
                top = stocks[:3]
                tickers = ", ".join(f"{s['ticker']} ({(s.get('rs_composite') or 0):.0f})" for s in top)
                lines.append(f"*{sector}*: {tickers}")
        else:
            for s in no_sector[:15]:
                lines.append(f"#{s.get('rs_rank')} {s['ticker']} — RS {(s.get('rs_composite') or 0):.0f}")

        return self._ok(request, result="\n".join(lines), data={"leaders": leaders})

    async def _handle_briefing_query(self, request: AgentRequest) -> AgentResponse:
        task_lower = request.task.lower()
        wants_morning = any(k in task_lower for k in ["morning", "pre-market", "premarket", "pre market"])
        wants_evening = any(k in task_lower for k in ["evening", "eod", "end of day", "after close", "nightly"])
        if wants_evening and not wants_morning:
            await send_evening_briefing()
        else:
            await send_morning_briefing()
        return self._ok(request, result="Briefing sent.")

    async def _handle_theme_query(self, request: AgentRequest) -> AgentResponse:
        from agents.market_intelligence.briefing import _compute_scored_themes, STAGE_EMOJI, _conviction_suffix

        today_str = et_today().strftime("%Y-%m-%d")
        themes = await get_today_themes(today_str)

        if not themes:
            return self._ok(
                request,
                result="No theme data yet — themes are generated during the nightly data pull (6 AM ET) or via /data/refresh.",
            )

        data_date = themes[0].get("theme_date", today_str)
        if hasattr(data_date, "isoformat"):
            data_date = data_date.isoformat()

        all_tickers = list({tk for t in themes for tk in (t.get("tickers") or [])})
        theme_rs_data, prior_scores, regime = await asyncio.gather(
            get_rs_for_tickers(data_date, all_tickers) if all_tickers else asyncio.sleep(0),
            get_prior_theme_scores(today_str),
            get_current_regime(),
        )
        if theme_rs_data is None:
            theme_rs_data = {}

        scored_themes, fading = _compute_scored_themes(themes, theme_rs_data, prior_scores or {})

        regime_str = ""
        if regime:
            regime_str = f" — Regime: {regime.get('regime', '?')} | VIX {regime.get('vix', '?')}"

        stage_order = ["Accelerating", "Nascent", "Mainstream"]
        stage_groups: dict[str, list] = {s: [] for s in stage_order}
        for st in scored_themes:
            stage_groups.setdefault(st.get("stage", "Nascent"), []).append(st)

        lines = [f"*{len(scored_themes)} Active Themes — {data_date}{regime_str}*"]

        for stage in stage_order:
            group = stage_groups.get(stage, [])
            if not group:
                continue
            emoji = STAGE_EMOJI.get(stage, "")
            lines.append(f"\n{emoji} *{stage.upper()}* ({len(group)})")
            for st in group:
                theme_emoji = STAGE_EMOJI.get(st["stage"], " ")
                delta_str = f"  Δ{st['delta']:+.1f}" if st["delta"] is not None else ""
                conviction = _conviction_suffix(st)
                lines.append(f"\n{theme_emoji}*{st['name']}*{conviction}")
                lines.append(
                    f"  RS {int(st['comp'])} (1M {int(st['rs_1m'])} | 3M {int(st['rs_3m'])} | 6M {int(st['rs_6m'])}){delta_str}"
                )
                ticker_rs = [
                    (tk, theme_rs_data[tk]["rs_composite"])
                    for tk in st["tickers"]
                    if theme_rs_data.get(tk, {}).get("rs_composite") is not None
                    and theme_rs_data[tk]["rs_composite"] >= 50
                ]
                ticker_rs.sort(key=lambda x: -x[1])
                top = " · ".join(f"{tk} {int(rs)}" for tk, rs in ticker_rs[:5])
                if top:
                    lines.append(f"  {top}")

        if fading:
            fading_names = " · ".join(t.get("name", "?") for t in fading[:5])
            lines.append(f"\n🔻 _Fading: {fading_names}_")

        return self._ok(request, result="\n".join(lines), data={"themes": themes})

    async def _handle_history_query(self, request: AgentRequest) -> AgentResponse:
        """Handle historical RS and theme queries — 'when did metals peak?', 'RS history CIEN'."""
        import re
        from datetime import timedelta

        task = request.task
        context = request.context or {}
        today = et_today()

        # Extract tickers from task text
        tickers = re.findall(r'\b([A-Z]{2,5})\b', task.upper())
        skip_words = {
            "RS", "FOR", "SCORE", "RANK", "WHAT", "THE", "AND", "NOW", "WHEN",
            "DID", "WAS", "SHOW", "HOW", "HAS", "THEME", "HISTORY", "OVER",
            "TIME", "PEAK", "FADE", "LAST", "MONTHS", "WEEKS",
        }
        tickers = [t for t in tickers if t not in skip_words]

        # Also accept tickers from context (orchestrator may pass them structured)
        ctx_tickers = context.get("tickers") or []
        if ctx_tickers:
            tickers = [t.upper() for t in ctx_tickers]

        # Extract date range from context or default to 90 days
        from_date = context.get("from_date") or (today - timedelta(days=90)).isoformat()
        to_date = context.get("to_date") or today.isoformat()

        # Theme name from context (explicit)
        theme_name = context.get("theme_name") or ""

        # If we have tickers, always do RS history (even if task mentions "gold", "metal", etc.)
        # Only do theme history if no tickers and task looks theme-oriented
        if tickers:
            return await self._format_rs_history(request, tickers[:10], from_date, to_date)

        # Theme history — only when no explicit tickers
        if theme_name:
            return await self._format_theme_history(request, theme_name, from_date, to_date)

        # Try to detect theme name from task keywords
        for kw in ["metals", "miners", "mining", "gold", "oil", "gas",
                    "optical", "memory", "semiconductor", "solar",
                    "nuclear", "defense", "crypto", "ai memory",
                    "photonics", "satellite", "energy"]:
            if kw in task.lower():
                return await self._format_theme_history(request, kw, from_date, to_date)

        # Check for generic theme keywords
        if any(kw in task.lower() for kw in ["theme", "sector"]):
            quoted = re.findall(r'"([^"]+)"', task)
            if quoted:
                return await self._format_theme_history(request, quoted[0], from_date, to_date)

        return self._ok(request, result="Please specify tickers (e.g. 'RS history CIEN LITE') or a theme name (e.g. 'when did metals theme peak?').")

    async def _format_rs_history(
        self, request: "AgentRequest", tickers: list[str], from_date: str, to_date: str,
    ) -> "AgentResponse":
        """Format RS history as a clean monospace table per ticker."""
        history = await get_rs_history(tickers, from_date, to_date, interval="weekly")

        if not history:
            return self._ok(request, result=f"No RS history found for {', '.join(tickers)}. RS data retained 1 year.")

        lines: list[str] = []
        for tk, snapshots in history.items():
            if not snapshots:
                continue
            # Find peak
            peak = max(snapshots, key=lambda s: s["rs_composite"] or 0)
            latest = snapshots[-1]
            peak_rs = peak["rs_composite"] or 0
            curr_rs = latest["rs_composite"] or 0
            arrow = "↑" if curr_rs >= peak_rs - 5 else "↓"

            lines.append(f"*{tk}*  Peak RS {peak_rs:.0f} ({peak['date']}) → Current RS {curr_rs:.0f} {arrow}")
            lines.append("```")
            lines.append(f"{'Date':>10}  {'RS':>3}  {'1M':>3}  {'3M':>3}  {'6M':>3}  {'Price':>8}")
            for s in snapshots:
                price = f"${s['close']:.2f}" if s.get("close") else "    —"
                rs = s["rs_composite"] or 0
                r1 = s["rs_1m"] or 0
                r3 = s["rs_3m"] or 0
                r6 = s["rs_6m"] or 0
                lines.append(
                    f"{s['date']:>10}  {rs:3.0f}  "
                    f"{r1:3.0f}  {r3:3.0f}  {r6:3.0f}  "
                    f"{price:>8}"
                )
            lines.append("```")
            lines.append("")

        return self._ok(request, result="\n".join(lines), data={"rs_history": history})

    async def _format_theme_history(
        self, request: "AgentRequest", theme_name: str, from_date: str, to_date: str,
    ) -> "AgentResponse":
        """Format theme history showing stage transitions and peak."""
        history = await get_theme_history(theme_name, from_date, to_date)

        if not history:
            return self._ok(
                request,
                result=f"No theme history found matching '{theme_name}'. Theme data retained 1 year (history starts 2026-03-19).",
            )

        from collections import defaultdict
        by_name: dict[str, list[dict]] = defaultdict(list)
        for h in history:
            by_name[h["name"]].append(h)

        lines: list[str] = []
        for name, snapshots in by_name.items():
            if not snapshots:
                continue
            peak = max(snapshots, key=lambda s: s["score"] or 0)
            latest = snapshots[-1]
            peak_score = peak["score"] or 0
            latest_score = latest["score"] or 0

            lines.append(f"*{name}*")
            lines.append(f"Peak: score {peak_score:.0f} on {peak['date']} ({peak['stage']})")
            lines.append(f"Current: score {latest_score:.0f} ({latest['stage']})")

            # Stage transitions
            prev_stage = None
            lines.append("")
            lines.append("```")
            lines.append(f"{'Date':>10}  {'Stage':<13}  {'Score':>5}")
            for s in snapshots:
                score = s["score"] or 0
                marker = " ←" if s["stage"] != prev_stage and prev_stage else ""
                lines.append(f"{s['date']:>10}  {s['stage']:<13}  {score:5.0f}{marker}")
                prev_stage = s["stage"]
            lines.append("```")

            if peak.get("tickers"):
                lines.append(f"Tickers at peak: {', '.join(peak['tickers'][:10])}")
            lines.append("")

        return self._ok(request, result="\n".join(lines), data={"theme_history": history})

    async def _handle_single_score(self, request: AgentRequest) -> AgentResponse:
        """Score a single ticker on demand — RS + fundamentals + theme context."""
        import re
        from agents.market_intelligence.fundamentals import get_fundamentals, format_fundamentals

        # Extract ticker from task — look for uppercase word 2-5 chars
        tickers = re.findall(r'\b([A-Z]{2,5})\b', request.task.upper())
        # Filter out common non-ticker words
        skip = _PREPOSITION_SKIP | {"RS", "FOR", "SCORE", "RANK", "WHAT", "THE", "AND", "NOW",
                "PULL", "GET", "SHOW", "CHECK", "FIND", "FUNDAMENTAL",
                "FUNDAMENTALS", "STOCK", "ANALYSIS"}
        tickers = [t for t in tickers if t not in skip]

        if not tickers:
            return self._ok(request, result="Please specify a ticker — e.g. 'score AXTI'")

        ticker = tickers[0]

        # Fetch RS, fundamentals, theme context, cached sector, and news in parallel
        today_str = et_today().strftime("%Y-%m-%d")
        is_research = any(k in request.task.lower() for k in ["research", "look up", "lookup", "analyse", "analyze"])
        rs_task = score_single_ticker(ticker)
        fund_task = get_fundamentals(ticker)
        themes_task = get_today_themes(today_str)
        sector_task = get_ticker_sector(ticker)
        news_task = (
            search_news_perplexity(f"What is happening with {ticker} stock? Recent news, catalyst, or business developments.", recency="month")
            if is_research else asyncio.sleep(0)
        )
        rs_result, fund_result, themes, sector_cache, news_result = await asyncio.gather(
            rs_task, fund_task, themes_task, sector_task, news_task, return_exceptions=True,
        )
        if isinstance(sector_cache, Exception):
            sector_cache = {}
        news_text = news_result if isinstance(news_result, str) and len(news_result) > 20 else None

        sections: list[str] = []

        # Log raw results for debugging
        logger.info(f"RS result type={type(rs_result).__name__}: {rs_result if isinstance(rs_result, dict) else repr(rs_result)}")

        # RS section
        if isinstance(rs_result, dict) and "error" not in rs_result:
            rank = rs_result["rs_rank"]
            n = rs_result["universe_size"]
            composite = rs_result["rs_composite"]
            close = rs_result["close"]
            ma_str = "  ".join(rs_result.get("ma_context", [])) or "No MA data"
            sections.append(
                f"`{ticker}` — RS Score\n"
                f"  Composite: *{rs_result['rs_composite']:.0f}*  (#{rank} of {n})\n"
                f"  1M: {rs_result['rs_1m']:.0f}  3M: {rs_result['rs_3m']:.0f}  6M: {rs_result['rs_6m']:.0f}\n"
                f"  Raw: 1M {rs_result['raw_1m']:+.1f}%  3M {rs_result['raw_3m']:+.1f}%  6M {rs_result['raw_6m']:+.1f}%\n"
                f"  Close: {close:.2f}  |  {ma_str}"
            )
        elif isinstance(rs_result, dict):
            sections.append(f"`{ticker}` — RS: {rs_result.get('error', 'unavailable')}")
        else:
            sections.append(f"`{ticker}` — RS: unavailable")

        # Fundamentals section
        if isinstance(fund_result, dict) and "error" not in fund_result:
            sections.append("\n" + format_fundamentals(fund_result))
        elif isinstance(fund_result, dict):
            sections.append(f"\nFundamentals: {fund_result.get('error', 'unavailable')}")

        # ── Relative strength context (theme + industry layers) ──────────────
        rs_context_lines: list[str] = []

        # Layer 1: Theme RS rank (tightest peer group)
        theme_match = None
        if isinstance(themes, list):
            for t in themes:
                if ticker in (t.get("tickers") or []):
                    theme_match = t
                    break

        if theme_match:
            theme_tickers = theme_match.get("tickers") or []
            theme_name = theme_match["name"]
            stage = theme_match.get("stage", "?")
            # Rank this ticker within the theme by RS
            if isinstance(rs_result, dict) and "rs_composite" in rs_result:
                ticker_rs = rs_result["rs_composite"]
                # Fetch RS for all theme members
                try:
                    peer_rs = await get_rs_for_tickers(today_str, theme_tickers)
                    composites = [v["rs_composite"] for v in peer_rs.values() if v.get("rs_composite") is not None]
                    if composites:
                        rank_in_theme = sum(1 for c in composites if c > ticker_rs) + 1
                        rs_context_lines.append(
                            f"  Theme: *{theme_name}* ({stage})  →  "
                            f"#{rank_in_theme} of {len(composites)}"
                        )
                except Exception:
                    rs_context_lines.append(f"  Theme: *{theme_name}* ({stage})")

        # Layer 2: Industry RS (always shown; fetches sector on-demand if not cached)
        industry = sector_cache.get("industry", "")
        sector = sector_cache.get("sector", "")

        # If not cached, try fetching on-demand from yfinance and persist
        if not industry:
            try:
                from agents.market_intelligence.collector import get_fmp_profile
                profile = await get_fmp_profile(ticker)
                industry = profile.get("industry", "")
                sector = profile.get("sector", "")
                if industry or sector:
                    await upsert_ticker_sectors_batch(
                        {ticker: {"sector": sector, "industry": industry}}
                    )
            except Exception:
                pass

        if industry or sector:
            try:
                from datetime import date as _date
                score_date = None
                if isinstance(rs_result, dict) and "score_date" in rs_result:
                    sd = rs_result["score_date"]
                    score_date = _date.fromisoformat(sd) if isinstance(sd, str) else sd
                if score_date is None:
                    pool = await get_pool()
                    async with pool.acquire() as conn:
                        row = await conn.fetchrow(
                            "SELECT MAX(score_date) AS d FROM mi_stock_scores"
                        )
                    score_date = row["d"] if row else None

                if score_date and isinstance(rs_result, dict) and "rs_composite" in rs_result:
                    rank_data = await get_sector_rs_rank(
                        ticker,
                        industry=industry or sector,
                        score_date=score_date,
                        sector=sector,
                        ticker_rs=rs_result["rs_composite"],
                    )
                    if rank_data:
                        label = rank_data["label"]
                        rank = rank_data["rank"]
                        total = rank_data["total"]
                        pct = rank_data["pct"]
                        fallback = rank_data.get("fallback", False)
                        suffix = " (sector)" if fallback else ""
                        rs_context_lines.append(
                            f"  {label}{suffix}  →  {pct}th pct  (#{rank} of {total} tracked)"
                        )
                    elif industry:
                        rs_context_lines.append(f"  {industry}  →  not enough peers tracked yet")
            except Exception as e:
                logger.debug(f"Sector RS rank failed for {ticker}: {e}")

        if rs_context_lines:
            sections.append("\n*RS context*\n" + "\n".join(rs_context_lines))

        # News section — only for explicit research queries
        if news_text:
            sections.append(f"\n*Recent news*\n{news_text[:700].strip()}")

        return self._ok(request, result="\n".join(sections), data=rs_result if isinstance(rs_result, dict) else {})

    async def _handle_pullback_query(self, request: AgentRequest) -> AgentResponse:
        today_str = et_today().strftime("%Y-%m-%d")

        # Check if filtering to a specific theme's tickers
        tickers = None
        task_lower = request.task.lower()
        themes = await get_today_themes(today_str)
        for t in themes:
            theme_name_lower = t["name"].lower()
            # Check if any word from the theme name appears in the task
            words = [w for w in theme_name_lower.split() if len(w) > 4]
            if any(w in task_lower for w in words):
                tickers = t.get("tickers")
                break

        pullbacks = await get_ma_pullbacks(today_str, tickers=tickers)

        if not pullbacks:
            scope = f"stocks in {tickers}" if tickers else "RS leaders"
            return self._ok(
                request,
                result=f"No MA pullbacks found among {scope} today. Either no data yet (run /data refresh) or all stocks are extended.",
            )

        lines = [f"*MA Pullbacks* ({today_str})"]
        if tickers:
            lines[0] += f" — filtered to theme"

        for s in pullbacks[:15]:
            ticker = s["ticker"]
            close = s.get("close", 0)
            rs = s.get("rs_composite", 0)
            near = s.get("near_mas", [])
            ma_parts = []
            for m in near:
                sign = "+" if m["pct_from_ma"] >= 0 else ""
                ma_parts.append(f"{m['ma']} {sign}{m['pct_from_ma']:.1f}%")
            lines.append(
                f"  `{ticker}` RS {rs:.0f}  close {close:.2f}  —  {' | '.join(ma_parts)}"
            )

        return self._ok(request, result="\n".join(lines), data={"pullbacks": pullbacks})

    async def _handle_fundamentals_query(self, request: AgentRequest) -> AgentResponse:
        import re
        from agents.market_intelligence.fundamentals import get_fundamentals, format_fundamentals

        # Extract tickers — uppercase words 2-5 chars, skip common non-tickers
        skip = _PREPOSITION_SKIP | {"EPS", "YOY", "GET", "THE", "FOR", "AND", "NET", "REV", "ROI",
                "CEO", "IPO", "ETF", "SPY", "QQQ", "IWM", "GDP", "CPI"}
        found = re.findall(r'\b([A-Z]{2,5})\b', request.task.upper())
        tickers = [t for t in found if t not in skip]

        # Prefer tickers from context if provided
        ctx_tickers = (request.context or {}).get("tickers", [])
        all_tickers = ctx_tickers or tickers

        if not all_tickers:
            return self._ok(request, result="Please specify a ticker — e.g. 'fundamentals AXTI'")

        # Cap at 3 tickers to avoid runaway yfinance calls
        targets = all_tickers[:3]

        if len(targets) == 1:
            # Single ticker → use unified handler (RS + fundamentals + theme)
            return await self._handle_single_score(request)
        else:
            results = await asyncio.gather(*[get_fundamentals(t) for t in targets])
            text = "\n\n---\n\n".join(format_fundamentals(r) for r in results)

        return self._ok(request, result=text)

    async def _handle_screener_query(self, request: AgentRequest) -> AgentResponse:
        """Run the composite screener with filters parsed from natural language."""
        import re
        from agents.market_intelligence.screener import (
            ScreenerFilters,
            run_screener,
            format_screener_results,
        )

        task = request.task
        ctx = request.context or {}

        # Parse filters from context (set by orchestrator) or natural language fallback
        def _num(key: str, default: float | None = None) -> float | None:
            val = ctx.get(key)
            if val is not None:
                return float(val)
            # Attempt regex extraction from task text (e.g. "RS > 70", "EPS > 25%")
            patterns = {
                "min_rs": r"rs\s*[>≥]\s*(\d+)",
                "min_eps_yoy_pct": r"eps\s*(?:yoy|growth)?\s*[>≥]\s*(\d+)%?",
                "min_rev_yoy_pct": r"rev(?:enue)?\s*(?:yoy|growth)?\s*[>≥]\s*(\d+)%?",
            }
            m = re.search(patterns.get(key, ""), task, re.IGNORECASE)
            return float(m.group(1)) if m else default

        filters = ScreenerFilters(
            min_rs=_num("min_rs", 60.0),
            min_eps_yoy_pct=_num("min_eps_yoy_pct"),
            min_rev_yoy_pct=_num("min_rev_yoy_pct"),
            require_acceleration=bool(ctx.get("require_acceleration", False)),
            require_sales_confirms=bool(ctx.get("require_sales_confirms", False)),
            theme_stage=ctx.get("theme_stage"),
            max_results=int(ctx.get("max_results", 20)),
        )

        results = await run_screener(filters)
        text = format_screener_results(results, filters)
        return self._ok(request, result=text)

    async def _handle_general(self, request: AgentRequest) -> AgentResponse:
        import re as _re
        from agents.market_intelligence.fundamentals import get_fundamentals, format_fundamentals

        today_str = et_today().strftime("%Y-%m-%d")
        regime = await get_current_regime()
        ep_alerts = await get_today_ep_alerts(today_str)
        rs_leaders = await get_rs_leaders(today_str, limit=10)

        context = (
            f"Market regime: {regime.get('regime')} (EP bar: {regime.get('ep_threshold')})\n"
            f"EP alerts today: {len(ep_alerts)}\n"
            f"Top RS stocks: {', '.join(s['ticker'] for s in rs_leaders[:5])}\n"
        )

        # Detect tickers in the query and fetch their RS + fundamentals
        candidate_tickers = _re.findall(r'\b([A-Z]{2,5})\b', request.task.upper())
        skip = {"FOR", "SCORE", "RANK", "WHAT", "THE", "AND", "NOW", "HOW",
                "TOP", "PULL", "GET", "SHOW", "LIST", "CHECK", "FIND", "ANY",
                "GIVE", "YOUR", "ANALYSIS", "ABOUT", "TELL", "INFO"}
        candidate_tickers = [t for t in candidate_tickers if t not in skip][:3]

        if candidate_tickers:
            # Fetch RS scores and fundamentals in parallel
            rs_tasks = [score_single_ticker(t) for t in candidate_tickers]
            fund_tasks = [get_fundamentals(t) for t in candidate_tickers]
            results = await asyncio.gather(*rs_tasks, *fund_tasks, return_exceptions=True)

            n = len(candidate_tickers)
            for i, ticker in enumerate(candidate_tickers):
                rs_result = results[i]
                fund_result = results[n + i]

                context += f"\n--- {ticker} ---\n"
                if isinstance(rs_result, dict) and "error" not in rs_result:
                    context += (
                        f"RS Composite: {rs_result['rs_composite']:.0f} "
                        f"(#{rs_result['rs_rank']} of {rs_result['universe_size']})\n"
                        f"  1M: {rs_result['rs_1m']:.0f}  3M: {rs_result['rs_3m']:.0f}  6M: {rs_result['rs_6m']:.0f}\n"
                        f"  Raw returns: 1M {rs_result['raw_1m']:+.1f}%  3M {rs_result['raw_3m']:+.1f}%  6M {rs_result['raw_6m']:+.1f}%\n"
                        f"  Close: ${rs_result['close']:.2f}  |  {' '.join(rs_result.get('ma_context', []))}\n"
                    )
                elif isinstance(rs_result, dict):
                    context += f"RS: {rs_result.get('error', 'unavailable')}\n"

                if isinstance(fund_result, dict) and "error" not in fund_result:
                    context += format_fundamentals(fund_result) + "\n"

        response = self._claude.messages.create(
            model=MARKET_AGENT_MODEL,
            max_tokens=1024,
            system=(
                "You are a market intelligence assistant specializing in momentum/EP trading. "
                "Answer concisely using ONLY the data provided below. Format for Telegram (no markdown tables). "
                "Never invent RS scores or fundamental data — only report what is in the context. "
                "Focus on actionable intelligence, not generic advice."
            ),
            messages=[{
                "role": "user",
                "content": f"Context:\n{context}\n\nQuestion: {request.task}",
            }],
        )
        return self._ok(request, result=response.content[0].text)


# FastAPI app entry point
_agent = MarketIntelligenceAgent()
app = _agent.app


@app.on_event("startup")
async def startup():
    import os
    from logging.handlers import RotatingFileHandler
    _fmt = logging.Formatter(
        "%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    # Persist logs to host-mounted volume so rebuilds don't lose history
    log_dir = "/app/logs"
    try:
        os.makedirs(log_dir, exist_ok=True)
        _fh = RotatingFileHandler(
            f"{log_dir}/market-agent.log",
            maxBytes=50 * 1024 * 1024,   # 50 MB per file
            backupCount=10,               # 500 MB total, ~weeks of history
        )
        _fh.setFormatter(_fmt)
        logging.getLogger().addHandler(_fh)
        logging.getLogger(__name__).info(f"File logging started: {log_dir}/market-agent.log")
    except Exception as _e:
        logging.getLogger(__name__).warning(f"Could not start file logging: {_e}")
    await initialize_schema()
    # Load description overrides from DB into in-memory TICKER_DESC
    try:
        from agents.market_intelligence.universe import apply_overrides
        overrides = await get_ticker_overrides()
        if overrides:
            apply_overrides(overrides)
            logger.info(f"Loaded {len(overrides)} ticker description override(s)")
    except Exception as e:
        logger.warning(f"Failed to load ticker overrides: {e}")
    start_scheduler()
    asyncio.create_task(check_missed_jobs())  # Run in background — data pull can take 30+ min
    # Start WebSocket streams
    from agents.market_intelligence.broker.trade_stream import start_trade_stream
    from agents.market_intelligence.broker.bar_stream import start_bar_stream
    asyncio.create_task(start_trade_stream())   # fill/stop detection
    asyncio.create_task(start_bar_stream())     # real-time first-bar ORB entry
    logger.info("Market Intelligence Agent ready on port 8006")
    asyncio.create_task(send_telegram_message("🔄 Market agent online"))


@app.on_event("shutdown")
async def shutdown():
    from agents.market_intelligence.broker.trade_stream import stop_trade_stream
    from agents.market_intelligence.broker.bar_stream import stop_bar_stream
    await stop_trade_stream()
    await stop_bar_stream()
    stop_scheduler()
