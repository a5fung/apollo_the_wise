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
)
from agents.market_intelligence.briefing import send_morning_briefing, send_evening_briefing, send_telegram_message
from agents.market_intelligence.collector import et_today
from agents.market_intelligence.ep_detector import run_ep_scan
from agents.market_intelligence.rs_engine import run_rs_engine, score_single_ticker
from agents.market_intelligence.regime import run_regime_engine, get_current_regime
from agents.market_intelligence.theme_engine import run_theme_engine, get_today_themes
from agents.market_intelligence.scheduler import start_scheduler, stop_scheduler, check_missed_jobs
from shared.models import AgentName, AgentRequest, AgentResponse

logger = logging.getLogger(__name__)

MARKET_AGENT_MODEL = "claude-haiku-4-5-20251001"


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
            """Re-run just the theme engine (uses existing RS data). Fast — no Polygon calls."""
            background.add_task(run_theme_engine)
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

        if any(k in task for k in ["theme engine", "rerun theme", "re-run theme", "run theme", "refresh theme"]):
            return await self._handle_theme_only(request)

        if any(k in task for k in ["refresh", "data pull", "nightly pull", "rerun", "re-run", "repull"]):
            return await self._handle_data_refresh(request)

        # History must be checked before theme/RS — "when did metals theme peak?" has "theme" in it
        if any(k in task for k in ["history", "historical", "when did", "when was", "over time", "timeline", "peak", "peaked", "faded", "fade"]):
            return await self._handle_history_query(request)

        if any(k in task for k in ["ep", "episodic", "gap", "pivot", "gapper"]):
            return await self._handle_ep_query(request)

        # Theme must be checked before regime and RS — "top themes by RS strength" or
        # "regime and active themes" should route to themes (the more specific intent)
        if any(k in task for k in ["theme", "sector", "industry"]):
            logger.info(f"Routing to theme handler: {task[:80]}")
            return await self._handle_theme_query(request)

        if any(k in task for k in ["regime", "market condition", "spy", "breadth", "vix", "risk"]):
            return await self._handle_regime_query(request)

        if any(k in task for k in ["rs", "relative strength", "leader", "momentum", "top stock",
                                     "score ", "rank "]):
            # If a specific ticker is detected, route to single-ticker score
            import re as _re
            _candidate = _re.findall(r'\b([A-Z]{2,5})\b', request.task.upper())
            _skip = {"RS", "FOR", "SCORE", "RANK", "WHAT", "THE", "AND", "NOW",
                      "TOP", "PULL", "GET", "SHOW", "LIST", "CHECK", "FIND",
                      "STOCK", "STOCKS", "LEADER", "LEADERS",
                      "OF", "IN", "AT", "ON", "BY", "TO", "AS", "AN", "OR",
                      "MY", "ME", "IT", "IS", "IF", "BE", "DO", "SO", "UP",
                      "AM", "US", "WE", "NO", "GO", "HI"}
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
                "GOLD": "GC=F", "VIX": "^VIX", "SPY": "ES=F", "NASDAQ": "NQ=F",
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

    async def _handle_theme_only(self, request: AgentRequest) -> AgentResponse:
        """Re-run just the theme engine using existing RS data. No Polygon calls — fast.

        Runs synchronously so the result flows back through the normal orchestrator→Telegram
        channel (reliable). Orchestrator timeout is set to 360s to accommodate the 2-4 min run.
        """
        task_lower = request.task.lower()
        wants_brief = any(k in task_lower for k in ["brief", "send", "briefing"])

        try:
            logger.info("Theme-only run starting...")
            themes, changelog = await run_theme_engine()
            logger.info("Theme-only run complete")
            active = [t for t in themes if t.get("stage") != "Fading"]
            revalidated = [e for e in changelog if e.get("type") == "ticker_revalidated_out"]
            pruned = [e for e in changelog if e.get("type") == "ticker_pruned"]
            summary = f"Theme engine complete — {len(active)} active themes"
            if revalidated:
                removed = ", ".join(f"{e['ticker']} from {e['theme']}" for e in revalidated)
                summary += f"\nRemoved mismatched: {removed}"
            if pruned:
                summary += f"\nPruned {len(pruned)} weak stock(s)"
            if wants_brief:
                asyncio.create_task(send_evening_briefing())
                summary += "\nEvening briefing sending..."
            return self._ok(request, result=summary)
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
        today_str = et_today().strftime("%Y-%m-%d")
        themes = await get_today_themes(today_str)

        if not themes:
            return self._ok(
                request,
                result="No theme data yet — themes are generated during the nightly data pull (6 AM ET) or via /data/refresh.",
            )

        # Show the actual data date (may differ from today on weekends)
        data_date = themes[0].get("theme_date", today_str)
        if hasattr(data_date, "isoformat"):
            data_date = data_date.isoformat()

        # Get RS data for all theme constituents (same ranking as briefing)
        all_tickers = list({tk for t in themes for tk in (t.get("tickers") or [])})
        rs_data = await get_rs_for_tickers(data_date, all_tickers)

        from agents.market_intelligence.constants import trimmed_mean

        # Compute composite RS per theme (same method as briefing scorecard)
        active_with_rs = []
        fading = []
        for t in themes:
            if t.get("stage") == "Fading":
                fading.append(t)
                continue
            tickers = t.get("tickers") or []
            comps = [rs_data[tk]["rs_composite"] for tk in tickers
                     if tk in rs_data and rs_data[tk].get("rs_composite") is not None]
            comp_rs = trimmed_mean(comps) if comps else 0
            active_with_rs.append((t, comp_rs))

        # Sort by composite RS descending (matches briefing ranking)
        active_with_rs.sort(key=lambda x: -x[1])

        # Include regime context so Claude doesn't need a separate call
        regime = await get_current_regime()
        regime_line = ""
        if regime:
            regime_line = f"\nMarket regime: {regime.get('regime', 'Unknown')} | VIX {regime.get('vix', '?')}\n"

        from agents.market_intelligence.briefing import STAGE_EMOJI as stage_emoji
        lines = [f"Active themes (data from {data_date}) — ranked by composite RS:{regime_line}"]
        for rank, (t, comp_rs) in enumerate(active_with_rs, 1):
            emoji = stage_emoji.get(t.get("stage", ""), "")
            tickers = t.get("tickers") or []
            # Show per-stock RS inline
            ticker_parts = []
            for tk in tickers:
                rs = rs_data.get(tk)
                if rs and rs.get("rs_composite") is not None:
                    ticker_parts.append(f"{tk} {rs['rs_composite']:.0f}")
                else:
                    ticker_parts.append(tk)
            ticker_str = ", ".join(ticker_parts)
            lines.append(f"\n#{rank} {emoji} *{t['name']}* — {t.get('stage')} (RS {comp_rs:.0f})")
            lines.append(f"  Stocks: {ticker_str}")
            if t.get("description"):
                lines.append(f"  {t['description'][:200]}")

        if fading:
            lines.append("\n🔻 *Fading* (score declining, do not treat as top themes):")
            for t in fading:
                lines.append(f"  {t['name']} (score {t.get('score', 0):.0f}) — {', '.join(t.get('tickers') or [])}")

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
        skip = {"RS", "FOR", "SCORE", "RANK", "WHAT", "THE", "AND", "NOW",
                "PULL", "GET", "SHOW", "CHECK", "FIND", "FUNDAMENTAL",
                "FUNDAMENTALS", "STOCK", "ANALYSIS",
                "OF", "IN", "AT", "ON", "BY", "TO", "AS", "AN", "OR",
                "MY", "ME", "IT", "IS", "IF", "BE", "DO", "SO", "UP",
                "AM", "US", "WE", "NO", "GO", "HI"}
        tickers = [t for t in tickers if t not in skip]

        if not tickers:
            return self._ok(request, result="Please specify a ticker — e.g. 'score AXTI'")

        ticker = tickers[0]

        # Fetch RS, fundamentals, and theme context in parallel
        today_str = et_today().strftime("%Y-%m-%d")
        rs_task = score_single_ticker(ticker)
        fund_task = get_fundamentals(ticker)
        themes_task = get_today_themes(today_str)
        rs_result, fund_result, themes = await asyncio.gather(
            rs_task, fund_task, themes_task, return_exceptions=True,
        )

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

        # Theme context
        if isinstance(themes, list):
            for t in themes:
                theme_tickers = t.get("tickers") or []
                if ticker in theme_tickers:
                    sections.append(
                        f"\nTheme: *{t['name']}* ({t.get('stage', '?')})"
                        f" — score {t.get('score', 0):.0f}"
                    )
                    break

        # Fundamentals section
        if isinstance(fund_result, dict) and "error" not in fund_result:
            sections.append("\n" + format_fundamentals(fund_result))
        elif isinstance(fund_result, dict):
            sections.append(f"\nFundamentals: {fund_result.get('error', 'unavailable')}")

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
        skip = {"EPS", "YOY", "GET", "THE", "FOR", "AND", "NET", "REV", "ROI",
                "CEO", "IPO", "ETF", "SPY", "QQQ", "IWM", "GDP", "CPI",
                "OF", "IN", "AT", "ON", "BY", "TO", "AS", "AN", "OR",
                "MY", "ME", "IT", "IS", "IF", "BE", "DO", "SO", "UP",
                "AM", "US", "WE", "NO", "GO", "HI"}
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
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%H:%M:%S",
    )
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
    # Start WebSocket trade stream for real-time fill/stop detection
    from agents.market_intelligence.broker.trade_stream import start_trade_stream
    asyncio.create_task(start_trade_stream())
    logger.info("Market Intelligence Agent ready on port 8006")


@app.on_event("shutdown")
async def shutdown():
    from agents.market_intelligence.broker.trade_stream import stop_trade_stream
    await stop_trade_stream()
    stop_scheduler()
