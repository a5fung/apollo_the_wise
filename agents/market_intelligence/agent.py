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
from datetime import date, datetime
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
    assign_ticker_to_theme,
    add_parabolic_exclusion,
    remove_parabolic_exclusion,
    list_parabolic_exclusions,
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
    get_paper_trade_stats,
    get_active_cooldowns,
    bypass_cooldown,
    log_audit_event,
    get_correlation_clusters,
)
from agents.market_intelligence.briefing import send_morning_briefing, send_evening_briefing, send_telegram_message
from agents.market_intelligence.collector import et_today, search_news_perplexity
from agents.market_intelligence.ep_detector import run_ep_scan, MIN_GAP_PCT, MIN_PREV_CLOSE, MIN_PREMARKET_SHARES, MAX_EXTENSION_PCT, EP_COOLDOWN_DAYS
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
        self._claude = anthropic.AsyncAnthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))
        self._refresh_lock = asyncio.Lock()
        self._register_extra_routes()

    def _register_extra_routes(self) -> None:
        """Register additional endpoints beyond the base /task and /health."""

        @self.app.get("/account/status")
        async def account_status(
            _: str = Depends(verify_internal_secret),
        ):
            """Per-mode Alpaca account block for orchestrator `/status` rendering.

            The orchestrator container doesn't ship market-agent modules
            (see Dockerfile.orchestrator — only agents/base.py is copied).
            This endpoint is the architectural bridge: orchestrator calls
            us via HTTP, we return JSON, telegram.py renders.

            Returns:
                {
                    "live_trading_enabled": bool,    # LIVE_TRADING_ENABLED env
                    "dual_mode_enabled": bool,       # ENABLE_LIVE_MODE env
                    "modes": [
                        {
                            "mode": "paper" | "live",
                            "routed_strategies": [str, ...],
                            "account": {            # null on failure
                                "equity": float,
                                "buying_power": float,
                                "pattern_day_trader": bool,
                                "daytrade_count": int,
                            },
                            "error": str | null,
                        },
                        ...
                    ],
                }
            """
            import os
            from agents.market_intelligence.constants import (
                ENABLE_LIVE_MODE, resolve_account_mode_for_strategy,
            )
            from agents.market_intelligence.strategies.registry import load_strategies
            from agents.market_intelligence.broker import alpaca_client as alpaca

            live_enabled = os.environ.get("LIVE_TRADING_ENABLED", "false").lower() == "true"
            if not live_enabled:
                return {
                    "live_trading_enabled": False,
                    "dual_mode_enabled": ENABLE_LIVE_MODE,
                    "modes": [],
                }

            modes_to_show = ["paper"] + (["live"] if ENABLE_LIVE_MODE else [])

            strat_by_mode: dict[str, list[str]] = {"paper": [], "live": []}
            try:
                strategies = await load_strategies()
                for sid, s in sorted(strategies.items()):
                    if not s.enabled or s.phase == "shadow":
                        continue
                    try:
                        strat_by_mode[resolve_account_mode_for_strategy(s)].append(sid)
                    except Exception:
                        pass
            except Exception as e:
                logger.warning(f"/account/status: strategy routing fetch failed: {e}")

            result_modes = []
            for mode in modes_to_show:
                block: dict = {
                    "mode": mode,
                    "routed_strategies": strat_by_mode.get(mode, []),
                    "account": None,
                    "error": None,
                }
                try:
                    account = await alpaca.get_account(account_mode=mode)
                    block["account"] = {
                        "equity": float(account.get("equity", 0.0)),
                        "buying_power": float(account.get("buying_power", 0.0)),
                        "pattern_day_trader": bool(account.get("pattern_day_trader", False)),
                        "daytrade_count": int(account.get("daytrade_count", 0)),
                    }
                except Exception as e:
                    block["error"] = str(e)[:200]
                result_modes.append(block)

            return {
                "live_trading_enabled": True,
                "dual_mode_enabled": ENABLE_LIVE_MODE,
                "modes": result_modes,
            }

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

        @self.app.post("/hud/pin")
        async def hud_pin(
            body: dict,
            _: str = Depends(verify_internal_secret),
        ):
            """Store chat_id + message_id for the pinned HUD so the hourly refresh can edit it."""
            from agents.market_intelligence.db import set_hud_state
            chat_id = body.get("chat_id")
            message_id = body.get("message_id")
            if chat_id is None or message_id is None:
                return {"error": "chat_id and message_id required"}
            await set_hud_state("hud_chat_id", str(chat_id))
            await set_hud_state("hud_message_id", str(message_id))
            return {"status": "ok"}

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
                from agents.market_intelligence.constants import current_account_mode
                results["account"] = {
                    "connected": True,
                    "trading_blocked": account["trading_blocked"],
                    "paper": current_account_mode() == "paper",
                }
                # 2. Get a market data bar (AAPL one week back — reliably
                # closed even across weekends/holidays. ET-anchored so the
                # post-8-PM-ET UTC rollover doesn't shift the date.)
                from datetime import timedelta
                from agents.market_intelligence.collector import et_today
                target = et_today() - timedelta(days=7)
                bar = await alpaca.get_first_bar("AAPL", target)
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

        # Slash command fast-path — exact dispatch, bypasses NLP substring matching
        if task.strip().startswith("/"):
            return await self._handle_slash_command(request)

        # Route by intent
        # Friday curated watchlist — must come before generic "watchlist" overnight-tracker
        # route since both share the keyword. Specific NLP terms only.
        if any(k in task for k in [
            "weekly watchlist", "friday watchlist", "curated watchlist",
            "show watchlist", "weekend watchlist",
        ]):
            return await self._handle_friday_watchlist(request)

        # Data refresh must be checked first — combined requests like "refresh then send brief"
        # would otherwise match "brief" and skip the refresh entirely.
        if any(k in task for k in ["track ", "untrack ", "drop ", "watchlist", "overnight watch"]):
            return await self._handle_watchlist(request)

        # Parabolic exclusions — must come before generic theme-exclusion route
        # because both share the "exclude " keyword.
        if "parabolic" in task and any(k in task for k in [
            "exclude", "include", "unexclude", "exclusions", "remove",
        ]):
            return await self._handle_parabolic_exclusion(request)

        if any(k in task for k in ["exclude ", "ban from theme", "remove from theme", "kick from theme", "list exclusions", "show exclusions", "theme exclusions"]):
            return await self._handle_theme_exclusion(request)

        if task.startswith("/theme assign ") or task.startswith("theme assign "):
            return await self._handle_theme_assign(request)

        if any(k in task for k in ["restore retired themes", "restore themes", "unretire themes", "recover themes"]):
            return await self._handle_restore_themes(request)

        if any(k in task for k in ["theme engine", "rerun theme", "re-run theme", "run theme", "refresh theme"]):
            return await self._handle_theme_only(request)

        if any(k in task for k in ["refresh", "data pull", "nightly pull", "rerun", "re-run", "repull"]):
            return await self._handle_data_refresh(request)

        if any(k in task for k in ["weekly review", "system review", "self audit", "self-audit"]):
            return await self._handle_system_review(request)

        # On-demand audit scan — `audit cooldowns`, `audit themes`, `audit all`, etc.
        # Bare "audit" (no topic) treated as `audit all`. "audit log" stays
        # routed to _handle_audit_log below (different feature).
        if (task.startswith("audit ") or task == "audit") and "audit log" not in task:
            return await self._handle_audit_topic(request)

        # Strategy maturity registry — list, detail, enable/disable/promote/demote.
        # Bare `/strategy` → list. `/strategy <id> [action]` → detail/mutate.
        if task in ("strategy", "/strategy") or task.startswith(("strategy ", "/strategy ", "strategy:")):
            return await self._handle_strategy_command(request)

        # Journal — add (colon disambiguates from query) or query
        if any(k in task for k in ["journal:", "log trade", "note trade", "add journal"]):
            return await self._handle_journal_add(request)
        if any(k in task for k in ["show journal", "my journal", "journal this week",
                                     "journal today", "journal last", "journal entries"]):
            return await self._handle_journal_query(request)

        # Trade postmortem — joined narrative (EP alert + execution + fwd returns + theme + regime).
        # Must come before trades_query (which grabs any "trade" substring).
        if any(k in task for k in ["postmortem", "post mortem", "post-mortem", "trade review"]):
            return await self._handle_postmortem(request)

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

        # Correlation clusters
        if any(k in task for k in ["show clusters", "correlation clusters", "cluster report"]):
            return await self._handle_correlation_clusters(request)

        # Validation cooldowns
        if any(k in task for k in ["show cooldowns", "cooldown list", "validation cooldowns", "active cooldowns"]):
            return await self._handle_cooldown_query(request)
        if any(k in task for k in ["bypass cooldown", "clear cooldown"]):
            return await self._handle_cooldown_bypass(request)

        # Paper trade validation report (P3)
        if any(k in task for k in ["validation report", "paper performance",
                                     "paper report", "ep validation"]):
            return await self._handle_validation_report(request)

        # 9M EP outcomes — must come before 9M query and before general "ep" route
        if any(k in task for k in ["9m outcome", "9m performance", "9m result",
                                    "9m track", "sugar outcome"]):
            return await self._handle_9m_ep_outcomes(request)

        # 9M trades — live/paper trade log for 9M system
        if any(k in task for k in ["9m trade", "9m position", "trade 9m", "show 9m trade"]):
            return await self._handle_9m_trades(request)

        # 9M EP query — specific phrases avoid false match on e.g. "9 months of history"
        if (
            any(k in task for k in ["9m ep", "sugar baby", "sugar babies", "nine million"])
            or task.strip() == "9m"
            or "show 9m" in task
        ):
            return await self._handle_9m_ep_query(request)

        # Wick-fill (P22) — telemetry candidates listing.
        if any(k in task for k in ["wick watch", "wick fill", "wick-fill"]) or task.strip() == "wick":
            return await self._handle_wick_query(request)

        # Fishhook V3 (TI3) — gap-up undercut & reclaim shadow telemetry.
        if any(k in task for k in ["fishhook", "fish hook", "undercut reclaim", "undercut & reclaim"]) or task.strip() == "fishhook":
            return await self._handle_fishhook_query(request)

        # Continuation Flag detector — must come BEFORE the generic theme route
        # because "coiled" / "flag" are unique enough to skip the theme keyword
        # net. Routes /flags slash, NLP variants, and bare 'flags'/'coiled'.
        if (
            any(k in task for k in [
                "show flags", "flag candidate", "flag scanner",
                "coiled stock", "coiled setup", "tightening flag",
                "continuation flag",
            ])
            or task.strip() in ("flags", "flag", "coiled")
        ):
            return await self._handle_flag_query(request)

        # /setup TICKER — reverse-lookup detector chronology across ~10 tables.
        # Slash-prefixed gate avoids "setup order" / "setup complete" collisions.
        if task.startswith("/setup ") or task.startswith("setup ") or task.strip() == "/setup":
            return await self._handle_setup_query(request)

        # EP outcome table — forward returns per alert; before general "ep" route
        if any(k in task for k in ["ep outcome", "ep performance", "how are my ep",
                                     "ep returns", "ep results", "ep track"]):
            return await self._handle_ep_outcomes(request)

        # Missed EPs — opportunity-cost lookup. Must be before generic "missed ep"
        # diagnostic route (which is single-ticker "why wasn't X flagged").
        if (task.startswith("/missed") or task.strip() == "/missed"
            or "missed opportunit" in task or "missed winner" in task
            or "missed eps" in task or "what did we miss" in task
            or "what are we missing" in task or "missed list" in task):
            return await self._handle_missed_query(request)

        # Lifecycle trace: "trace TICKER" or "why didn't we enter TICKER" — execution-side diagnostic.
        # Distinct from `_handle_ep_diagnostic` (detection-side: "why wasn't X an EP at all?").
        if "trace " in task or "why didn't we enter" in task or "why didn't we trade" in task:
            return await self._handle_why_query(request)

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

        # Crypto routing must precede regime/RS — keywords like "btc dominance"
        # contain "btc" which would otherwise be ticker-extracted in _handle_single_score.
        if any(k in task for k in ["crypto", "altseason", "alt season", "btc dominance",
                                    "btc.d", "stablecoin flow", "total3", "/crypto", "/altseason"]):
            return await self._handle_crypto_query(request)

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

        # Trading config — position sizing, safeguards, account parameters
        if any(k in task for k in [
            "position size", "max position", "position sizing", "risk per trade",
            "trading config", "trading rules", "trading parameters", "trading setup",
            "account size", "how much risk", "risk amount", "dollar risk",
            "safeguard", "circuit breaker", "daily loss limit", "loss limit",
            "how many positions", "max concurrent", "entry slippage",
            "how does trading work", "trading system", "what are the rules",
        ]):
            return await self._handle_trading_config(request)

        # General: let Claude decide what data to pull
        return await self._handle_general(request)

    async def _handle_trading_config(self, request: AgentRequest) -> AgentResponse:
        """Return live trading configuration drawn directly from constants.py and the DB."""
        from agents.market_intelligence.constants import (
            ACCOUNT_SIZE, RISK_PCT, MAX_POSITION_PCT,
            MAX_CONCURRENT_LIVE_POSITIONS, DAILY_LOSS_LIMIT_PCT,
            CIRCUIT_BREAKER_CONSEC_LOSSES, CONFIRMATION_TIMEOUT_SEC,
            LIVE_TRADING_ENABLED, current_account_mode,
        )
        from agents.market_intelligence.broker import alpaca_client as alpaca
        from agents.market_intelligence.db import get_latest_regime

        regime = await get_latest_regime()
        qqq_bullish = regime.get("qqq_ema_bullish") if regime else None
        active_risk_pct = RISK_PCT if qqq_bullish is not False else RISK_PCT * 0.5

        # Display equity sourced from the live broker — what the gates ACTUALLY
        # use (sizing path reads alpaca.get_account()["equity"] at order-prep
        # time, not the ACCOUNT_SIZE constant). On a $10K live account, the old
        # constant-based display read $100K — wrong by 10×.
        equity = ACCOUNT_SIZE
        equity_source = "constant (broker fetch failed)"
        try:
            account = await alpaca.get_account()
            equity = float(account["equity"])
            equity_source = "broker (live)"
        except Exception as e:
            logger.warning(f"trading_config: broker equity fetch failed, falling back to constant: {e}")

        risk_dollars = round(equity * active_risk_pct)
        max_pos_dollars = round(equity * MAX_POSITION_PCT)
        daily_loss_dollars = round(equity * DAILY_LOSS_LIMIT_PCT)

        is_paper = current_account_mode() == "paper"
        if not LIVE_TRADING_ENABLED:
            mode = "DISABLED"
        elif is_paper:
            mode = "PAPER"
        else:
            mode = "LIVE-$"
        qqq_gate = "full risk" if qqq_bullish is not False else "half risk (QQQ 10EMA < 20EMA)"

        lines = [
            f"*Trading Configuration — {mode} mode*\n",
            "*Account*",
            f"  Equity:             ${equity:,.2f} _{equity_source}_",
            f"  Mode:               {'💰 LIVE-$' if (LIVE_TRADING_ENABLED and not is_paper) else ('📄 Paper (Alpaca)' if LIVE_TRADING_ENABLED else '⚫ Trading disabled')}",
            "",
            "*Position Sizing (per trade)*",
            f"  Risk per trade:     {RISK_PCT*100:.0f}% = ${risk_dollars:,}",
            f"  QQQ EMA gate:       {qqq_gate}",
            f"  Active risk:        ${round(equity * active_risk_pct):,}/trade right now",
            f"  Max position size:  {MAX_POSITION_PCT*100:.0f}% = ${max_pos_dollars:,}",
            f"  Sizing formula:     shares = risk_$ / (entry - stop)",
            "",
            "*Safeguards*",
            f"  Max open positions: {MAX_CONCURRENT_LIVE_POSITIONS} (shared MAGNA53 + 9M EP)",
            f"  Daily loss limit:   {DAILY_LOSS_LIMIT_PCT*100:.0f}% = ${daily_loss_dollars:,}",
            f"  Circuit breaker:    pause after {CIRCUIT_BREAKER_CONSEC_LOSSES} consecutive losses",
            f"  Confirm timeout:    {CONFIRMATION_TIMEOUT_SEC//60} min (live mode only)",
            "",
            "*MAGNA53 EP Entry Filters*",
            "  Min gap:            8%",
            "  Min price:          $5.00",
            "  Min ADV:            $1M median 20-day",
            "  Max ATR%:           15%",
            "  Min market cap:     $500M",
            "  Max stop width:     1.5× ATR-14",
            "  EP cooldown:        60 days same ticker",
            "",
            "*9M EP Entry Filters*",
            "  Volume threshold:   8.9M actual / 12M projected",
            "  Min price:          $3.00",
            "  Stop anchor:        prior day's low (breakout wall)",
            "  Max stop width:     15% of entry price",
            "  Sugar baby gate:    close in top 25% of range + green",
        ]
        return self._ok(request, "\n".join(lines))

    async def _handle_system_review(self, request: AgentRequest) -> AgentResponse:
        """Run the weekly self-audit on demand. Sends Telegram digest + persists row."""
        from agents.market_intelligence.system_review import run_weekly_review
        try:
            review = await run_weekly_review(window_days=7)
            suggestions = review.get("suggestions") or []
            summary = (
                f"System review sent — regime={review.get('regime')}, "
                f"{len(suggestions)} suggestion(s). See Telegram for full digest."
            )
            return self._ok(request, result=summary)
        except Exception as e:
            logger.exception(f"System review failed: {e}")
            return self._error(request, f"System review failed: {e}")

    async def _handle_audit_topic(self, request: AgentRequest) -> AgentResponse:
        """`/audit <topic>` — on-demand invariant + metric scan for a slice.

        Topics: `cooldowns`, `themes`, `skips`, `positions`, `feed`, `9m`,
        `job_runs`, `all`. Bare `/audit` defaults to `all`. Same diagnostic
        body as the scheduled scans; results emit Telegram on L1/L2 breach,
        audit-only on L3. `job_runs` returns a text report (no L1/L2 emission).
        """
        from agents.market_intelligence.system_audit import run_topic_audit
        raw = request.task.strip()
        parts = raw.split(maxsplit=1)
        topic = parts[1].strip().lower() if len(parts) == 2 else "all"
        try:
            result = await run_topic_audit(topic)
            if result.get("error"):
                valid = ", ".join(result.get("valid") or [])
                return self._ok(
                    request,
                    result=f"Unknown audit topic `{topic}`. Valid topics: `{valid}`.",
                )
            if result.get("report"):
                return self._ok(request, result=result["report"])
            l1 = result.get("l1", 0)
            l2 = result.get("l2", 0)
            l3 = result.get("l3", 0)
            summary = (
                f"Audit `{topic}` complete — {l1} L1 / {l2} L2 / {l3} L3 drift. "
                f"L1/L2 alerts (if any) sent to Telegram."
            )
            return self._ok(request, result=summary)
        except Exception as e:
            logger.exception(f"Audit topic failed: {e}")
            return self._error(request, f"Audit failed: {e}")

    async def _handle_dryrun(self, request: AgentRequest) -> AgentResponse:
        """`/dryrun` — pre-flight check.

        Surfaces broker account block (mode/equity/PDT/daytrades) plus, for
        every trade row inserted today, the stored spec recomputed against
        current equity. The recompute exposes sizing drift if the account
        has moved since the row was written — the moment that matters most
        is the day after a flip, when stored specs were sized at $100K
        paper but live equity is now $10K.

        Read-only: never submits. Idempotent.
        """
        import math
        from datetime import date as _date

        from agents.market_intelligence.broker import alpaca_client as alpaca
        from agents.market_intelligence.constants import (
            current_account_mode, mode_prefix,
        )
        from agents.market_intelligence.db import get_pool
        from zoneinfo import ZoneInfo

        _ET = ZoneInfo("America/New_York")
        from datetime import datetime as _dt
        today = _dt.now(_ET).date()
        mode = current_account_mode()

        # Account block — fail-soft so /dryrun stays useful even if broker
        # is unreachable (e.g. weekend Alpaca maintenance).
        equity: float | None = None
        buying_power: float | None = None
        daytrade_count: int = 0
        pdt_flag = False
        broker_err: str | None = None
        try:
            account = await alpaca.get_account()
            equity = float(account["equity"])
            buying_power = float(account["buying_power"])
            daytrade_count = int(account.get("daytrade_count") or 0)
            pdt_flag = bool(account.get("pattern_day_trader") or False)
        except Exception as e:
            broker_err = str(e)

        lines = [f"{mode_prefix()}*Pre-flight `/dryrun` — {today.isoformat()}*", ""]
        lines.append("*Account*")
        lines.append(f"  Mode:           `{mode}`")
        if broker_err:
            lines.append(f"  Equity:         _broker fetch failed: {broker_err}_")
        else:
            lines.append(f"  Equity:         ${equity:,.2f}")
            lines.append(f"  Buying power:   ${buying_power:,.2f}")
            lines.append(f"  PDT flagged:    {pdt_flag}")
            lines.append(f"  Day-trades:     {daytrade_count}/3 (rolling 5-day)")
        lines.append("")

        # Today's trades — any status, including pending/skipped/blocked rows
        # (skipped rows still show why a candidate didn't enter).
        pool = await get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id, ticker, signal_type, status, entry_price, stop_price,
                       entry_shares, risk_dollars, position_size, account_mode,
                       skip_reason
                FROM mi_live_trades
                WHERE alert_date = $1
                ORDER BY id ASC
                """,
                today,
            )

        if not rows:
            lines.append("_No alert rows today yet._")
            return self._ok(request, "\n".join(lines))

        lines.append(f"*Today's trade rows ({len(rows)})*")
        # Risk pct read at compute time (matches prepare_orb_order). 1% default;
        # halved when QQQ EMA bearish — surface that gate in the output.
        from agents.market_intelligence.constants import RISK_PCT
        from agents.market_intelligence.db import get_latest_regime
        regime = await get_latest_regime()
        qqq_bullish = regime.get("qqq_ema_bullish") if regime else None
        active_risk_pct = RISK_PCT if qqq_bullish is not False else RISK_PCT * 0.5
        if equity is not None:
            lines.append(
                f"  _Recompute basis: equity=${equity:,.0f} × "
                f"{active_risk_pct*100:.2f}% = ${equity*active_risk_pct:,.0f} risk/trade_"
            )
        lines.append("")
        for r in rows:
            ticker = r["ticker"]
            status = r["status"]
            entry = r["entry_price"]
            stop = r["stop_price"]
            stored_shares = int(r["entry_shares"] or 0)
            stored_risk = float(r["risk_dollars"] or 0)
            stored_pos = float(r["position_size"] or 0)
            row_mode = r["account_mode"] or "?"
            sig = r["signal_type"] or "?"

            head = f"  `{ticker}` [{sig}/{row_mode}] {status}"
            lines.append(head)
            if entry and stop and entry > stop:
                lines.append(
                    f"      stored: entry=${entry:.2f} stop=${stop:.2f} "
                    f"shares={stored_shares} risk=${stored_risk:,.0f} "
                    f"pos=${stored_pos:,.0f}"
                )
                if equity is not None:
                    risk_per_share = float(entry) - float(stop)
                    hyp_risk = equity * active_risk_pct
                    hyp_shares = math.floor(hyp_risk / risk_per_share) if risk_per_share > 0 else 0
                    # 20% of equity position cap
                    cap_shares = math.floor((equity * 0.20) / float(entry)) if entry > 0 else 0
                    if cap_shares > 0:
                        hyp_shares = min(hyp_shares, cap_shares)
                    hyp_pos = hyp_shares * float(entry)
                    diff = hyp_shares - stored_shares
                    diff_str = f"{diff:+d}" if diff else "0"
                    lines.append(
                        f"      @ now:  shares={hyp_shares} ({diff_str}) "
                        f"risk=${hyp_shares * risk_per_share:,.0f} pos=${hyp_pos:,.0f}"
                    )
            elif r["skip_reason"]:
                lines.append(f"      skip: {r['skip_reason']}")

        return self._ok(request, "\n".join(lines))

    async def _handle_strategy_command(self, request: AgentRequest) -> AgentResponse:
        """`/strategy` (list) or `/strategy <id> [action]` (detail / mutate).

        Actions: enable, disable, promote, demote. Promote enforces
        verdict.eligible — see strategies/telegram.py.
        """
        from agents.market_intelligence.strategies.telegram import (
            handle_strategies_command,
            handle_strategy_action,
        )
        import re as _re
        raw = request.task.strip()
        # Strip leading `/strategy` or `strategy` (colon or whitespace) and dispatch on body.
        # Empty body → list view; otherwise → detail/mutate.
        body = _re.sub(r'^\s*/?strategy(?:[:\s]+|$)', '', raw, count=1, flags=_re.IGNORECASE).strip()
        try:
            if not body:
                return self._ok(request, result=await handle_strategies_command())
            return self._ok(request, result=await handle_strategy_action(body))
        except Exception as e:
            logger.exception(f"Strategy command failed: {e}")
            return self._error(request, f"Strategy command failed: {e}")

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

    async def _handle_theme_assign(self, request: AgentRequest) -> AgentResponse:
        """Manual theme membership override — /theme assign TICKER THEME_NAME.

        Bypasses the assignment LLM + post-validation. Used when the automated
        pipeline misses obvious matches (5/9 incident: MU/SNDK/MRAM/SIMO not
        anchored to AI Memory & Storage despite top-30 RS, MXL not anchored
        to optical theme despite advisor verdict). DISTINCT-merges into
        today's mi_themes row, lifts any active cooldown for that pair,
        emits theme_manual_assignment audit event.

        Usage:
          /theme assign MU AI Memory & Storage
          theme assign MXL AI Datacenter Optical Transceivers & Components
        """
        import re as _re
        task_orig = request.task

        # Strip the leading command, leaving "TICKER THEME_NAME"
        body = _re.sub(r'^\s*/?theme\s+assign\s+', '', task_orig, count=1, flags=_re.IGNORECASE).strip()
        if not body:
            return self._ok(request, result=(
                "Usage: `/theme assign TICKER THEME_NAME`\n"
                "Example: `/theme assign MU AI Memory & Storage`"
            ))

        # First token = ticker, rest = theme name
        parts = body.split(None, 1)
        if len(parts) < 2:
            return self._ok(request, result=(
                "Need both a ticker and a theme name.\n"
                "Example: `/theme assign MU AI Memory & Storage`"
            ))
        ticker_raw, theme_name = parts
        ticker = ticker_raw.upper().strip(",.'\"")
        theme_name = theme_name.strip().rstrip(".,!?")

        if not _re.fullmatch(r'[A-Z]{1,6}', ticker):
            return self._ok(request, result=f"Couldn't parse ticker `{ticker_raw}` — expected 1-6 uppercase letters.")

        try:
            result = await assign_ticker_to_theme(ticker, theme_name)
        except Exception as e:
            return self._ok(request, result=f"Assignment failed: {type(e).__name__}: {e}")

        if not result["matched"]:
            return self._ok(request, result=(
                f"No active theme named _{theme_name}_ for today. Check the exact name "
                f"via `themes` or `/themes` — must match including punctuation."
            ))
        before = result["before"]
        after = result["after"]
        if ticker in before:
            return self._ok(request, result=f"`{ticker}` is already in _{theme_name}_.")
        lifted_note = " (active cooldown lifted)" if result["lifted_cooldown"] else ""
        return self._ok(request, result=(
            f"Done. `{ticker}` added to _{theme_name}_{lifted_note}.\n"
            f"Members now: {', '.join(after)} ({len(after)} stocks)\n"
            f"Tomorrow's nightly Haiku validation will revalidate; if it strips "
            f"`{ticker}`, that's a Haiku validator misfire — reassign or file the "
            f"audit row."
        ))

    async def _handle_parabolic_exclusion(self, request: AgentRequest) -> AgentResponse:
        """Manage parabolic-short exclusions (manual operator overrides).

        Commands (slash or natural):
          /parabolic exclude OGN buyout
          /parabolic include OGN
          /parabolic exclusions
          parabolic exclude OGN buyout
        """
        import re as _re
        task_orig = request.task
        # Strip leading slash command if present.
        body = _re.sub(r'^\s*/?parabolic\s*', '', task_orig, count=1, flags=_re.IGNORECASE).strip()
        body_lower = body.lower()

        # List
        if not body_lower or body_lower in {"exclusions", "list", "list exclusions", "show exclusions"}:
            rows = await list_parabolic_exclusions()
            if not rows:
                return self._ok(request, result="No parabolic-short exclusions set.")
            from agents.market_intelligence.collector import et_today
            today = et_today()
            lines = ["*Parabolic-short Exclusions*"]
            for r in rows:
                until = r.get("excluded_until")
                if until is None:
                    status = "permanent"
                elif until < today:
                    status = f"expired {until.isoformat()}"
                else:
                    status = f"until {until.isoformat()}"
                lines.append(
                    f"• `{r['ticker']}` [{r['source']}] — {r['reason']} _({status})_"
                )
            return self._ok(request, result="\n".join(lines))

        # Match "include" / "unexclude" / "remove" as either bare keyword or
        # prefix-with-args. `startswith("include ")` alone misses bare-form.
        is_removal = (
            body_lower in {"include", "unexclude", "remove"}
            or body_lower.startswith(("include ", "unexclude ", "remove "))
        )
        if is_removal:
            cands = _re.findall(r'\b([A-Z]{2,5})\b', body.upper())
            skip = _PREPOSITION_SKIP | {"INCLUDE", "UNEXCLUDE", "REMOVE", "EXCLUSION"}
            ticker = next((t for t in cands if t not in skip), None)
            if not ticker:
                return self._ok(request, result="Usage: `/parabolic include TICKER`")
            removed = await remove_parabolic_exclusion(ticker)
            # Write a `manual_keep` sentinel so the next news_check skips this
            # ticker entirely instead of re-running Perplexity and re-excluding
            # under `news_check`. Without this, `/parabolic include` would only
            # silence the alert until the next nightly scan.
            await add_parabolic_exclusion(
                ticker, source="manual_keep",
                reason="operator override — do not auto-exclude",
                excluded_until=None,
            )
            base = f"Removed `{ticker}` from parabolic exclusions." if removed \
                else f"No active exclusion was set for `{ticker}`."
            return self._ok(
                request,
                result=(
                    f"{base}\n"
                    f"Future news-checks will skip `{ticker}` (manual override).\n"
                    f"To re-enable auto-exclusion: `/parabolic exclude {ticker} <reason>`"
                ),
            )

        # Add — first uppercase ticker, rest of message is the reason
        if body_lower.startswith("exclude "):
            body = body[len("exclude "):].strip()
        cands = _re.findall(r'\b([A-Z]{2,5})\b', body.upper())
        skip = _PREPOSITION_SKIP | {"EXCLUDE", "PARABOLIC"}
        ticker = next((t for t in cands if t not in skip), None)
        if not ticker:
            return self._ok(
                request,
                result="Usage: `/parabolic exclude TICKER reason` (e.g. `/parabolic exclude OGN buyout by Bidder Inc`)",
            )
        # Reason = body with the ticker token stripped
        reason = _re.sub(rf'\b{ticker}\b', '', body, flags=_re.IGNORECASE).strip()
        reason = reason or "manual exclusion"
        # Clear any prior `manual_keep` so this manual ban actually takes effect
        # (manual_keep has higher precedence than manual in the active lookup).
        await remove_parabolic_exclusion(ticker, source="manual_keep")
        await add_parabolic_exclusion(
            ticker, source="manual", reason=reason, excluded_until=None,
        )
        return self._ok(
            request,
            result=(
                f"Excluded `{ticker}` from parabolic-short scans (permanent).\n"
                f"Reason: {reason}\n"
                f"To undo: `/parabolic include {ticker}`"
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
        event_type_like = None
        if "error" in task or "fail" in task:
            event_type_like = "%error%"  # matches validation_error, assignment_error, discovery_error
        # Transient API failures (validation_api_failure / assignment_api_failure /
        # discovery_api_failure) don't end in `_error` so they don't match above —
        # they're visible in the morning-briefing 4-bucket banner instead.

        rows = await get_audit_log(limit=25, event_type=event_type, event_type_like=event_type_like, since_hours=since_hours)

        if not rows:
            filter_label = event_type or event_type_like or ""
            label = f"last {since_hours}h" + (f" [{filter_label}]" if filter_label else "")
            return self._ok(request, result=f"No audit log entries in {label}.")

        _TYPE_EMOJI = {
            "advisor_call":          "🤖",
            "theme_discovered":      "🌱",
            "theme_retired":         "🪦",
            "stage_change":          "📈",
            "theme_excluded":        "🚫",
            "ticker_revalidated_out":"🗑️",
            "validation_error":      "🔴",
            "assignment_error":      "🔴",
            "discovery_error":       "🔴",
            "theme_engine_aborted":  "🔴",
            "ep_alert":              "⚡",
            "orb_triggered":         "🎯",
            "orb_filtered":          "⊘",
            "orb_bar_miss":          "⏳",
            "orb_bar_fetched":       "📊",
            "orb_no_bar":            "❌",
            "orb_order_placed":      "✅",
            "orb_order_failed":      "🚨",
        }

        filter_label = event_type or event_type_like or ""
        lines = [f"*Audit Log* — last {since_hours}h{' · ' + filter_label if filter_label else ''}"]
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

    async def _handle_9m_ep_query(self, request: AgentRequest) -> AgentResponse:
        """Show today's 9M EP intraday detections and pending Day 2 sugar babies."""
        import asyncio as _asyncio
        from datetime import timedelta
        from agents.market_intelligence.db import (
            get_today_9m_ep_alerts,
            get_all_9m_sugar_babies,
            get_eod_9m_sugar_babies,
        )
        from agents.market_intelligence.collector import et_today, prev_trading_days, last_trading_day

        today = et_today()
        query_date = last_trading_day(today)
        today_str = query_date.isoformat()
        yesterday = prev_trading_days(1, from_date=query_date)[0]
        weekend_note = "" if query_date == today else f"  _(last trading day)_"

        alerts, yday_day2, today_babies = await _asyncio.gather(
            get_today_9m_ep_alerts(today_str),
            get_all_9m_sugar_babies(yesterday),
            get_eod_9m_sugar_babies(today_str),
        )

        lines = [f"*9M EP — {today_str}*{weekend_note}\n"]

        if alerts:
            lines.append(f"*Intraday Detections ({len(alerts)})*")
            for a in alerts:
                vol_m = a["today_volume"] / 1_000_000
                proj = f" (proj {a['projected_vol']/1_000_000:.1f}M)" if a.get("projected_vol") else ""
                kind = " _(pace)_" if a.get("is_anticipation") else ""
                lines.append(
                    f"  🏦 `{a['ticker']}` — {vol_m:.1f}M{proj}{kind} | "
                    f"${a['current_price']:.2f} | +{a['gap_pct']:.1f}%"
                )
        else:
            lines.append(f"No 9M EP detections for {today_str}.")

        from agents.market_intelligence.ninem_detector import _shape_tag

        def _shape_suffix(b: dict) -> str:
            p5 = b.get("prev_5d_pct")
            p20 = b.get("prev_20d_pct")
            tag = _shape_tag(b)
            parts = []
            if p5 is not None:
                parts.append(f"5d {p5:+.0f}%")
            if p20 is not None:
                parts.append(f"20d {p20:+.0f}%")
            if tag:
                parts.append(tag)
            return f" | {' / '.join(parts)}" if parts else ""

        if today_babies:
            lines.append(f"\n*Today's Sugar Babies — Day 2 ORB Candidates ({len(today_babies)})*")
            for b in today_babies:
                vol_m = b["volume"] / 1_000_000
                rp = int(b["close_in_range_pct"] * 100)
                lines.append(
                    f"  🍬 `{b['ticker']}` Vol {vol_m:.1f}M | "
                    f"Close ${b['close_price']:.2f} | Range {rp}% | Stop ${b['low_price']:.2f}"
                    f"{_shape_suffix(b)}"
                )

        if yday_day2:
            status_icon = {"pending": "⏳", "traded": "✅", "skipped": "⏭️"}
            lines.append(f"\n*Yesterday's Day 2 Sugar Babies ({len(yday_day2)})*")
            for b in yday_day2:
                vol_m = b["volume"] / 1_000_000
                icon = status_icon.get(b.get("day2_status") or "", "❓")
                lines.append(
                    f"  🍬 {icon} `{b['ticker']}` Vol {vol_m:.1f}M | "
                    f"Stop ${b['low_price']:.2f}{_shape_suffix(b)}"
                )

        return self._ok(request, result="\n".join(lines))

    async def _handle_wick_query(self, request: AgentRequest) -> AgentResponse:
        """Show today's wick-fill candidates plus 30d telemetry roll-up.

        Wick-fill is telemetry-only (P22 shadow-phase). No entries, no orders.
        We're answering: of 9M days closing in the [0.50, 0.75) wick zone,
        what fraction break prior_high in the next 10 sessions, and what's
        the forward drift after that?
        """
        from agents.market_intelligence.db import get_wick_candidates_window
        from agents.market_intelligence.collector import et_today, last_trading_day
        from agents.market_intelligence.ninem_detector import _shape_tag

        today = et_today()
        query_date = last_trading_day(today)
        weekend_note = "" if query_date == today else "  _(last trading day)_"
        rows = await get_wick_candidates_window(30)

        today_rows = [r for r in rows if r["alert_date"] == query_date]
        settled = [r for r in rows if r.get("fwd_10d_from_close_pct") is not None]
        n_filled = sum(1 for r in settled if r.get("filled_wick"))

        lines = [f"🪝 *Wick-Fill — {query_date.isoformat()}*{weekend_note}\n"]
        if today_rows:
            lines.append(f"*Today's Candidates ({len(today_rows)})*")
            for r in today_rows:
                vol_m = float(r["volume"]) / 1_000_000
                rp = int(float(r["close_in_range_pct"]) * 100)
                tag = _shape_tag(r)
                tag_suffix = f" | {tag}" if tag else ""
                lines.append(
                    f"  🪝 `{r['ticker']}` Vol {vol_m:.1f}M | "
                    f"Close ${float(r['close_price']):.2f} | Range {rp}% | "
                    f"Prior high ${float(r['prior_high']):.2f}{tag_suffix}"
                )
        else:
            lines.append("_No wick candidates on this date._")

        if settled:
            fill_rate = n_filled / len(settled)
            lines.append("")
            lines.append(
                f"*30d Telemetry:* {len(rows)} candidates · "
                f"{len(settled)} settled · {n_filled} filled ({fill_rate*100:.0f}%)"
            )
            lines.append("_Phase: shadow. Promotion gate: n≥30 AND fill_rate≥0.50._")
        else:
            lines.append("")
            lines.append(
                f"*30d Telemetry:* {len(rows)} candidates · 0 settled "
                f"(forward returns need 10 trading sessions)"
            )

        return self._ok(request, result="\n".join(lines))

    async def _handle_fishhook_query(self, request: AgentRequest) -> AgentResponse:
        """Fishhook V3 (gap-up undercut & reclaim) — shadow-phase telemetry.

        Reframed post-Stage-0 as a base-rate harvester (R≈1.1, hit≈13-19%).
        Shows today's open anchors + 30d state distribution + median R on
        settled rows. Promotion gate is n_settled ≥ 60, median R ≥ 1.0,
        hit rate ≥ 0.13.
        """
        from datetime import timedelta
        from agents.market_intelligence.collector import et_today, last_trading_day
        from agents.market_intelligence.db import get_fishhook_outcomes_window

        today = et_today()
        query_date = last_trading_day(today)
        weekend_note = "" if query_date == today else "  _(last trading day)_"
        rows = await get_fishhook_outcomes_window(window_days=60)

        by_state: dict[str, list] = {}
        for r in rows:
            by_state.setdefault(r["state"], []).append(r)

        recent_cutoff = query_date - timedelta(days=25)
        active_today = [
            r for r in rows
            if r["state"] in ("pending", "promoted", "reclaimed")
            and r["anchor_date"] >= recent_cutoff
        ]

        settled = [r for r in rows if r["state"] in ("settled", "invalidated")]
        n_settled = len(settled)
        rs = [float(r["r_5d"]) for r in settled if r["r_5d"] is not None]
        rs.sort()
        median_r = rs[len(rs) // 2] if rs else None
        hit_rate = (sum(1 for r in rs if r > 0) / len(rs)) if rs else None

        lines = [f"🪝 *Fishhook V3 — {query_date.isoformat()}*{weekend_note}\n"]

        if active_today:
            lines.append(f"*Open Anchors ({len(active_today)})*")
            for r in active_today[:25]:
                gap_pct = float(r["gap_pct"]) * 100
                drift = r.get("drift_pct_max")
                drift_str = f"drift {float(drift)*100:+.1f}%" if drift is not None else "no drift yet"
                lines.append(
                    f"  🪝 `{r['ticker']}` {r['anchor_date']} | "
                    f"gap {gap_pct:+.1f}% | {r['state']} | {drift_str}"
                )
            if len(active_today) > 25:
                lines.append(f"  _…{len(active_today) - 25} more._")
        else:
            lines.append("_No open anchors — recent gap-up universe is quiet._")

        lines.append("")
        lines.append("*60d State Distribution*")
        order = ["pending", "promoted", "reclaimed", "settled", "invalidated",
                 "expired_no_promotion", "expired_no_reclaim"]
        for s in order:
            n = len(by_state.get(s, []))
            if n:
                lines.append(f"  {s}: {n}")

        lines.append("")
        if rs:
            lines.append(
                f"*60d Telemetry:* {n_settled} settled · "
                f"median R {median_r:.2f} · hit rate {hit_rate*100:.0f}%"
            )
            lines.append("_Phase: shadow. Promotion gate: n≥60, R≥1.0, hit≥13%._")
        else:
            lines.append(f"*60d Telemetry:* {n_settled} settled · awaiting forward window")

        return self._ok(request, result="\n".join(lines))

    async def _handle_flag_query(self, request: AgentRequest) -> AgentResponse:
        """Continuation Flag detector — combined daily stage digest.

        Two modes (2026-05-11 consolidation):
          /flags             → ALL stages (TRIGGERED + COILED + TIGHTENING +
                               WATCH names) for latest scan date
          /flags TICKER      → 14-day stage history for one ticker

        Pre-2026-05-11 had a separate `/flags watch` command for WATCH +
        TIGHTENING; merged into the single default digest since users were
        running both commands consecutively. Backward-compat: "/flags watch"
        still parses (the keyword is ignored — same combined output).

        Scan-date fallback (2026-05-11): if today's scan hasn't run yet
        (flag detector runs at 5:25 PM ET Mon-Fri), the query falls back to
        the most recent scan date that actually has data, tagged in the
        header. Mirrors the latest_market_data_date pattern from /pregame
        and /ep (2026-05-07).

        Trade-idea radar — does NOT auto-enter. User charts and decides.
        """
        import re as _re
        from agents.market_intelligence.collector import et_today
        from agents.market_intelligence.db import (
            get_flag_candidates_window, get_ticker_flag_history, get_pool,
        )

        task = request.task.lower()
        # Single-ticker history mode: `/flags XNDU` or `flags XNDU`
        cands = _re.findall(r'\b([A-Z]{2,5})\b', request.task.upper())
        skip = _PREPOSITION_SKIP | {"FLAGS", "FLAG", "COILED", "WATCH",
                                     "SHOW", "TIGHTENING", "TIGHT"}
        ticker = next((t for t in cands if t not in skip), None)
        if ticker:
            rows = await get_ticker_flag_history(ticker, days=14)
            if not rows:
                return self._ok(request, result=f"No flag-detector rows for `{ticker}` in last 14d.")
            lines = [f"🚩 *{ticker} — Flag History (14d)*\n"]
            for r in rows:
                rr = r.get("range_contraction_ratio")
                vr = r.get("vol_contraction_ratio")
                rr_s = f"r{rr:.2f}" if rr is not None else "r—"
                vr_s = f"v{vr:.2f}" if vr is not None else "v—"
                held = f" (held from {r['held_from_stage']})" if r.get("held_from_stage") else ""
                lines.append(
                    f"  {r['scan_date']}  `{r['stage']:<11}` "
                    f"age {r.get('base_age') or '—':<3}  {rr_s} {vr_s}{held}"
                )
            return self._ok(request, result="\n".join(lines))

        today = et_today()
        # Latest-scan-date fallback: flag scan runs 5:25 PM ET Mon-Fri.
        # Pre-scan weekday queries (e.g. 10 AM Monday) and weekends both
        # fall back to the most recent date with actual scan data.
        # asyncpg's prepare-time type inference rejects both
        # `scan_date >= $1 - INTERVAL '14 days'` (date vs timestamp) AND
        # `scan_date >= $1 - 14` (date vs integer mid-expression).
        # Compute the cutoff in Python so both bind params are plain dates.
        from datetime import timedelta
        cutoff_date = today - timedelta(days=14)
        pool = await get_pool()
        async with pool.acquire() as conn:
            query_date = await conn.fetchval(
                """
                SELECT MAX(scan_date)
                FROM mi_flag_candidates
                WHERE scan_date >= $1
                  AND scan_date <= $2
                """,
                cutoff_date, today,
            )
        if query_date is None:
            return self._ok(
                request,
                result="_No flag-scanner data in last 14 days._",
            )
        date_note = "" if query_date == today else f"  _(data: {query_date.isoformat()})_"

        # Pull ALL stages in one shot — consolidated digest replaces the
        # old separate /flags vs /flags watch split.
        rows = await get_flag_candidates_window(
            query_date,
            stages=["TRIGGERED", "COILED", "TIGHTENING", "WATCH"],
        )
        triggered = [r for r in rows if r["stage"] == "TRIGGERED"]
        coiled = [r for r in rows if r["stage"] == "COILED"]
        tightening = [r for r in rows if r["stage"] == "TIGHTENING"]
        watch = [r for r in rows if r["stage"] == "WATCH"]

        if not (triggered or coiled or tightening or watch):
            return self._ok(
                request,
                result=f"_No flags in any stage on {query_date.isoformat()}.{date_note}_",
            )

        lines = [f"🚩 *Flag Scanner — {query_date.isoformat()}*{date_note}\n"]

        if triggered:
            lines.append(f"🎯 *TRIGGERED ({len(triggered)})*")
            for r in triggered:
                age = r.get("base_age")
                runup = r.get("runup_pct")
                bvr = r.get("breakout_volume_ratio")
                close = r.get("breakout_close")
                bh = r.get("base_high")
                ru_s = f"{float(runup)*100:+.0f}%" if runup is not None else "—"
                if close is not None and bh is not None:
                    lines.append(
                        f"  • `{r['ticker']}` — base {age}d · runup {ru_s} · "
                        f"vol {float(bvr):.2f}× · close ${float(close):.2f} > ${float(bh):.2f}"
                    )
                else:
                    lines.append(f"  • `{r['ticker']}` — base {age}d · runup {ru_s}")

        if coiled:
            lines.append("")
            lines.append(f"🌀 *COILED — actionable setup ({len(coiled)})*")
            for r in coiled[:15]:
                age = r.get("base_age")
                rr = r.get("range_contraction_ratio")
                vr = r.get("vol_contraction_ratio")
                rr_s = f"{float(rr):.2f}" if rr is not None else "—"
                vr_s = f"{float(vr):.2f}" if vr is not None else "—"
                lines.append(
                    f"  • `{r['ticker']}` — base {age}d · range {rr_s} · vol {vr_s}"
                )
            if len(coiled) > 15:
                lines.append(f"  …{len(coiled) - 15} more")

        if tightening:
            lines.append("")
            lines.append(f"🔧 *TIGHTENING ({len(tightening)})*")
            for r in tightening[:15]:
                age = r.get("base_age")
                rr = r.get("range_contraction_ratio")
                vr = r.get("vol_contraction_ratio")
                rr_s = f"{float(rr):.2f}" if rr is not None else "—"
                vr_s = f"{float(vr):.2f}" if vr is not None else "—"
                lines.append(f"  • `{r['ticker']}` age {age}d · range {rr_s} · vol {vr_s}")
            if len(tightening) > 15:
                lines.append(f"  …{len(tightening) - 15} more")

        if watch:
            lines.append("")
            lines.append(f"👀 *WATCH ({len(watch)})*")
            names = ", ".join(r["ticker"] for r in watch[:30])
            more = f" …+{len(watch) - 30}" if len(watch) > 30 else ""
            lines.append(f"  {names}{more}")

        lines.append("")
        lines.append("_Drill-down: `/flags TICKER` for 14-day history_")
        return self._ok(request, result="\n".join(lines))

    async def _handle_sugar_babies_query(self, request: AgentRequest) -> AgentResponse:
        """`/sugarbabies` — current Pradeep-class persistent watchlist.

        Tickers that printed 9M+ EOD volume ≥3 times in trailing 180 days.
        Refreshed daily 5:22 PM ET via `_sugar_babies_cohort_refresh_job`.
        Pure observational watchlist — no auto-entry. Operator decides when
        a member shows a VCP / tight-base setup worth taking.
        """
        from agents.market_intelligence.db import get_sugar_babies_cohort_latest, get_pool

        pool = await get_pool()
        async with pool.acquire() as conn:
            latest = await conn.fetchval("SELECT MAX(cohort_date) FROM mi_sugar_babies_cohort")
        if not latest:
            return self._ok(
                request,
                result="_Sugar Babies cohort empty. Daily 5:22 PM ET refresh will populate._",
            )
        rows = await get_sugar_babies_cohort_latest(limit=60)
        if not rows:
            return self._ok(request, result=f"_No tickers in cohort on {latest}._")
        # Stage emoji vocabulary matches /flags handler conventions
        # (🎯 TRIGGERED / 🌀 COILED / 🔧 TIGHTENING). Space-pad when no
        # recent flag stage so column alignment is preserved.
        stage_emoji = {"TRIGGERED": "🎯", "COILED": "🌀", "TIGHTENING": "🔧"}
        ripe_count = sum(1 for r in rows if r.get("current_flag_stage"))
        lines = [
            f"🍬 *Sugar Babies — Pradeep persistent cohort* ({latest})",
            f"_{len(rows)} tickers · {ripe_count} ripe (🎯=breakout 🌀=coiled 🔧=tightening)_",
            "",
        ]
        for r in rows[:30]:  # Pradeep watchlist size ~25-30
            days_since = (latest - r["last_9m_alert"]).days
            gap = r.get("latest_gap_pct")
            gap_s = f" · gap {float(gap):.1f}%" if gap is not None else ""
            stage = r.get("current_flag_stage")
            emoji = stage_emoji.get(stage, " ")  # space-pad alignment
            base_age = r.get("flag_base_age")
            stage_s = (
                f" · {stage} {base_age}d"
                if stage and base_age is not None
                else (f" · {stage}" if stage else "")
            )
            lines.append(
                f"  {emoji} `{r['ticker']:<6}` {r['n']}× 9M · last {days_since}d ago{gap_s}{stage_s}"
            )
        if len(rows) > 30:
            lines.append(f"  …{len(rows) - 30} more")
        lines.append("")
        lines.append("_Watchlist only — entry via VCP/tight-base setup is operator discretion._")
        return self._ok(request, result="\n".join(lines))

    async def _handle_stocks_in_play_query(self, request: AgentRequest) -> AgentResponse:
        """`/inplay` — unified Stocks-in-Play surface (#99, ADR 0004 Phase 1).

        Surfaces active mi_stocks_in_play rows (expires_at > NOW()) grouped
        by automation_class. Phase 1: only sugar_baby_cohort sources are
        migrated. Future ships add flag stages, convergence, EP, intraday
        breaks, etc.
        """
        from agents.market_intelligence.db import get_stocks_in_play

        rows = await get_stocks_in_play(active_only=True)
        if not rows:
            return self._ok(
                request,
                result=(
                    "_No active Stocks-in-Play entries._\n\n"
                    "Daily refresh at 5:22 PM ET (Sugar Baby cohort); other "
                    "detector sources migrate in future ships."
                ),
            )

        # Group by automation_class
        from collections import defaultdict
        by_class: dict[str, list[dict]] = defaultdict(list)
        # Track distinct tickers to surface multi-detector convergence
        ticker_sources: dict[str, list[str]] = defaultdict(list)
        for r in rows:
            by_class[r["automation_class"]].append(r)
            ticker_sources[r["ticker"]].append(r["source_detector"])

        n_unique_tickers = len(ticker_sources)
        n_multi = sum(1 for srcs in ticker_sources.values() if len(srcs) > 1)

        class_emoji = {
            "apollo_eligible": "🚨",
            "operator_only": "👤",
            "informational": "ℹ️",
        }
        class_label = {
            "apollo_eligible": "*apollo_eligible*",
            "operator_only": "*operator_only* — needs your judgment",
            "informational": "*informational* — context only",
        }

        lines = [
            f"🎯 *Stocks in Play* ({n_unique_tickers} unique tickers, "
            f"{len(rows)} rows{', ' + str(n_multi) + ' multi-detector' if n_multi else ''})",
            "",
        ]

        for cls in ("apollo_eligible", "operator_only", "informational"):
            cls_rows = by_class.get(cls, [])
            if not cls_rows:
                continue
            lines.append(f"{class_emoji[cls]} {class_label[cls]} ({len(cls_rows)})")
            # Show up to 20 rows per class (cap noise for big informational tier)
            for r in cls_rows[:20]:
                src_short = r["source_detector"].replace("_", " ")
                lines.append(f"  `{r['ticker']:<6}` {src_short} — {r['reason']}")
            if len(cls_rows) > 20:
                lines.append(f"  _…{len(cls_rows) - 20} more_")
            lines.append("")

        lines.append(
            "_Phase 1: sugar_baby_cohort migrated. Future ships add flag stages, "
            "convergence, EP, intraday breaks._"
        )
        return self._ok(request, result="\n".join(lines))

    async def _handle_watchlist_query(self, request: AgentRequest) -> AgentResponse:
        """`/watch` — proactive tight-range watchlist with entry-technique
        annotations (#93, ADR 0005 §3 + memory/user_tight_range_entry_techniques).

        Shows TIGHTENING/COILED/TRIGGERED tickers from the most-recent EOD
        flag scan, with annotations indicating which of the 5 tight-range
        entry techniques are currently eligible per ticker:
            🎯 breakout-near (price within 3% of base_high)
            🛡 support-test (price within 3% of base_low)
            📉 MA-pullback (price near MA10/MA20 inside range)
            💤 low-vol-rest (vol <50% ADV + price mid-range)
            (U&R deferred — needs swing-low logic per #98)

        The detector for entry #1 (breakout-near) is the intraday flag-break
        scan (#94) shipped 2026-05-23. Other entry techniques are operator-
        judgment until #95-#98 ship.
        """
        from agents.market_intelligence.flag_detector import get_flag_watchlist

        watchlist = await get_flag_watchlist()
        if not watchlist:
            return self._ok(
                request,
                result=(
                    "_No tight-range watchlist available._\n\n"
                    "EOD flag scan runs 5:25 PM ET Mon-Fri. Try again after market close."
                ),
            )

        scan_date = watchlist[0]["scan_date"]
        n_total = len(watchlist)
        n_with_annot = sum(1 for w in watchlist if w["annotations"])
        n_breakout = sum(1 for w in watchlist
                         if any(a[0] == "breakout_near" for a in w["annotations"]))
        n_support = sum(1 for w in watchlist
                        if any(a[0] == "support_test" for a in w["annotations"]))
        n_ma = sum(1 for w in watchlist
                   if any(a[0].startswith("ma_pullback") for a in w["annotations"]))
        n_lowvol = sum(1 for w in watchlist
                       if any(a[0] == "lowvol_rest" for a in w["annotations"]))

        lines = [
            f"🎯 *Tight-Range Watchlist* ({scan_date})",
            f"_{n_total} tickers · {n_with_annot} with actionable entry annotations_",
            f"_Eligible: {n_breakout} breakout-near · {n_support} support-test · "
            f"{n_ma} MA-pullback · {n_lowvol} low-vol-rest_",
            "",
        ]

        # Group by stage for display
        stage_emoji = {"TRIGGERED": "🎯", "COILED": "🌀", "TIGHTENING": "🔧"}
        for stage in ["TRIGGERED", "COILED", "TIGHTENING"]:
            stage_rows = [w for w in watchlist if w["stage"] == stage]
            if not stage_rows:
                continue
            # Surface tickers WITH annotations first within each stage
            stage_rows.sort(key=lambda w: (not w["annotations"], -w["base_age"]))
            lines.append(f"*{stage_emoji[stage]} {stage} ({len(stage_rows)})*")
            for w in stage_rows[:15]:  # cap per stage
                annot_str = ""
                if w["annotations"]:
                    annot_str = " " + " ".join(
                        f"{emoji} {detail}" for _, emoji, detail in w["annotations"]
                    )
                lines.append(
                    f"  `{w['ticker']:<5}` ${w['current_price']:.2f} "
                    f"(base {w['base_age']}d){annot_str}"
                )
            if len(stage_rows) > 15:
                lines.append(f"  _…{len(stage_rows) - 15} more (no annotations or older base)_")
            lines.append("")

        lines.append(
            "_Annotation legend_: 🎯 breakout-near · 🛡 support-test · "
            "📉 MA-pullback · 💤 low-vol-rest"
        )
        lines.append(
            "_Detector for breakout-near = intraday flag-break (#94, shadow). "
            "Other entries = operator judgment until #95-#98 ship._"
        )
        return self._ok(request, result="\n".join(lines))

    async def _handle_flag_breaks_query(self, request: AgentRequest) -> AgentResponse:
        """`/flagbreaks` — intraday flag-break detector surface (#94, ADR 0005).

        Modes:
          /flagbreaks           — today's breaks + last 7-day summary
          /flagbreaks TICKER    — 30-day history for one ticker

        Shadow phase: telemetry-only, no entries submitted. Forward-return
        validation at N≥10 settled via monthly auto-revalidation per
        feedback_methodology_insights_need_periodic_revalidation.md.
        """
        import re as _re
        from agents.market_intelligence.db import get_pool

        # Single-ticker history mode if TICKER provided
        cands = _re.findall(r'\b([A-Z]{2,5})\b', request.task.upper())
        skip = _PREPOSITION_SKIP | {"FLAGBREAKS", "FLAGBREAK"}
        ticker = next((t for t in cands if t not in skip), None)

        from agents.market_intelligence.collector import _ET
        pool = await get_pool()
        async with pool.acquire() as conn:
            if ticker:
                rows = await conn.fetch("""
                    SELECT break_date, break_time, minutes_since_open,
                           parent_stage, base_high, break_price,
                           pct_above_base_high, volume_pct_of_adv,
                           in_sugar_baby_cohort, parent_invalidated_eod
                    FROM mi_flag_breaks
                    WHERE ticker = $1
                      AND break_date >= CURRENT_DATE - INTERVAL '30 days'
                    ORDER BY break_date DESC, break_time DESC
                """, ticker)
                if not rows:
                    return self._ok(
                        request,
                        result=f"_No intraday flag-breaks for `{ticker}` in last 30d._"
                    )
                lines = [f"🎯 *{ticker} — Intraday flag-break history (30d)*", ""]
                for r in rows:
                    et_clock = r["break_time"].astimezone(_ET).strftime("%H:%M")
                    inval = " ⚠️ invalidated_eod" if r["parent_invalidated_eod"] else ""
                    cohort = " 🍬" if r["in_sugar_baby_cohort"] else ""
                    lines.append(
                        f"  {r['break_date']} {et_clock}{cohort} — "
                        f"{r['parent_stage']} broke ${r['base_high']:.2f} "
                        f"at {r['pct_above_base_high']:+.1f}% "
                        f"(vol {r['volume_pct_of_adv']:.0f}% ADV){inval}"
                    )
                return self._ok(request, result="\n".join(lines))

            # Default: today's breaks + 7-day summary
            today_rows = await conn.fetch("""
                SELECT ticker, break_time, minutes_since_open,
                       parent_stage, base_high, break_price,
                       pct_above_base_high, volume_pct_of_adv,
                       in_sugar_baby_cohort, parent_invalidated_eod
                FROM mi_flag_breaks
                WHERE break_date = CURRENT_DATE
                ORDER BY break_time
            """)
            recent_summary = await conn.fetch("""
                SELECT break_date,
                       COUNT(*) AS n_breaks,
                       COUNT(*) FILTER (WHERE in_sugar_baby_cohort) AS n_cohort,
                       COUNT(*) FILTER (WHERE parent_invalidated_eod) AS n_invalidated
                FROM mi_flag_breaks
                WHERE break_date BETWEEN CURRENT_DATE - INTERVAL '7 days'
                                     AND CURRENT_DATE - INTERVAL '1 day'
                GROUP BY break_date
                ORDER BY break_date DESC
            """)

        lines = ["🎯 *Intraday Flag-Breaks*", ""]
        if today_rows:
            lines.append(f"*Today ({len(today_rows)})*:")
            for r in today_rows:
                et_clock = r["break_time"].astimezone(_ET).strftime("%H:%M")
                cohort = "🍬 " if r["in_sugar_baby_cohort"] else ""
                inval = " ⚠️ invalidated_eod" if r["parent_invalidated_eod"] else ""
                lines.append(
                    f"  {et_clock} {cohort}`{r['ticker']}` — "
                    f"{r['parent_stage']} broke ${r['base_high']:.2f} "
                    f"at {r['pct_above_base_high']:+.1f}% "
                    f"(vol {r['volume_pct_of_adv']:.0f}% ADV){inval}"
                )
        else:
            lines.append("_No breaks today (yet)._")

        if recent_summary:
            lines.append("")
            lines.append("*Last 7 days (excl. today):*")
            for r in recent_summary:
                inval_note = (
                    f" ({r['n_invalidated']} invalidated_eod)"
                    if r["n_invalidated"] else ""
                )
                cohort_note = (
                    f" {r['n_cohort']} 🍬"
                    if r["n_cohort"] else ""
                )
                lines.append(
                    f"  {r['break_date']}: {r['n_breaks']} breaks{cohort_note}{inval_note}"
                )

        lines.append("")
        lines.append("_Drill-down: `/flagbreaks TICKER` for 30-day history per ticker_")
        lines.append("_Shadow phase — telemetry only, no entries submitted_")
        return self._ok(request, result="\n".join(lines))

    async def _handle_support_tests_query(self, request: AgentRequest) -> AgentResponse:
        """`/supporttests` — intraday support-test detector surface (#95).

        Modes:
          /supporttests           — today's tests + last 7-day summary
          /supporttests TICKER    — 30-day history for one ticker

        Shadow phase: telemetry-only, no entries. Counter-trend entry mechanic
        per memory/user_tight_range_entry_techniques.md Entry #2.
        """
        import re as _re
        from agents.market_intelligence.db import get_pool

        cands = _re.findall(r'\b([A-Z]{2,5})\b', request.task.upper())
        skip = _PREPOSITION_SKIP | {"SUPPORTTESTS", "SUPPORTTEST"}
        ticker = next((t for t in cands if t not in skip), None)

        from agents.market_intelligence.collector import _ET
        pool = await get_pool()
        async with pool.acquire() as conn:
            if ticker:
                rows = await conn.fetch("""
                    SELECT test_date, test_time, minutes_since_open,
                           parent_stage, base_low, day_low, current_price,
                           pct_below_base_low, bounce_pct_from_low,
                           in_sugar_baby_cohort, parent_invalidated_eod
                    FROM mi_flag_support_tests
                    WHERE ticker = $1
                      AND test_date >= CURRENT_DATE - INTERVAL '30 days'
                    ORDER BY test_date DESC, test_time DESC
                """, ticker)
                if not rows:
                    return self._ok(
                        request,
                        result=f"_No intraday support-tests for `{ticker}` in last 30d._"
                    )
                lines = [f"🛡 *{ticker} — Intraday support-test history (30d)*", ""]
                for r in rows:
                    et_clock = r["test_time"].astimezone(_ET).strftime("%H:%M")
                    inval = " ⚠️ invalidated_eod" if r["parent_invalidated_eod"] else ""
                    cohort = " 🍬" if r["in_sugar_baby_cohort"] else ""
                    lines.append(
                        f"  {r['test_date']} {et_clock}{cohort} — "
                        f"{r['parent_stage']} tested ${r['base_low']:.2f} "
                        f"({r['pct_below_base_low']:+.2f}%), bounced "
                        f"+{r['bounce_pct_from_low']:.2f}%{inval}"
                    )
                return self._ok(request, result="\n".join(lines))

            today_rows = await conn.fetch("""
                SELECT ticker, test_time, parent_stage, base_low, day_low,
                       current_price, pct_below_base_low, bounce_pct_from_low,
                       in_sugar_baby_cohort, parent_invalidated_eod
                FROM mi_flag_support_tests
                WHERE test_date = CURRENT_DATE
                ORDER BY test_time
            """)
            recent_summary = await conn.fetch("""
                SELECT test_date,
                       COUNT(*) AS n_tests,
                       COUNT(*) FILTER (WHERE in_sugar_baby_cohort) AS n_cohort,
                       COUNT(*) FILTER (WHERE parent_invalidated_eod) AS n_invalidated
                FROM mi_flag_support_tests
                WHERE test_date BETWEEN CURRENT_DATE - INTERVAL '7 days'
                                    AND CURRENT_DATE - INTERVAL '1 day'
                GROUP BY test_date
                ORDER BY test_date DESC
            """)

        lines = ["🛡 *Intraday Support-Tests*", ""]
        if today_rows:
            lines.append(f"*Today ({len(today_rows)})*:")
            for r in today_rows:
                et_clock = r["test_time"].astimezone(_ET).strftime("%H:%M")
                cohort = "🍬 " if r["in_sugar_baby_cohort"] else ""
                inval = " ⚠️ invalidated_eod" if r["parent_invalidated_eod"] else ""
                lines.append(
                    f"  {et_clock} {cohort}`{r['ticker']}` — "
                    f"{r['parent_stage']} tested ${r['base_low']:.2f} "
                    f"({r['pct_below_base_low']:+.2f}%), bounced "
                    f"+{r['bounce_pct_from_low']:.2f}%{inval}"
                )
        else:
            lines.append("_No support-tests today (yet)._")

        if recent_summary:
            lines.append("")
            lines.append("*Last 7 days (excl. today):*")
            for r in recent_summary:
                inval_note = (
                    f" ({r['n_invalidated']} invalidated_eod)"
                    if r["n_invalidated"] else ""
                )
                cohort_note = (
                    f" {r['n_cohort']} 🍬"
                    if r["n_cohort"] else ""
                )
                lines.append(
                    f"  {r['test_date']}: {r['n_tests']} tests{cohort_note}{inval_note}"
                )

        lines.append("")
        lines.append("_Drill-down: `/supporttests TICKER` for 30-day history per ticker_")
        lines.append("_Shadow phase — telemetry only, no entries submitted_")
        return self._ok(request, result="\n".join(lines))

    async def _handle_undercut_rally_query(self, request: AgentRequest) -> AgentResponse:
        """`/undercutrally` (`/ur`) — intraday U&R detector surface (#98, Morales/OWL).

        Modes:
          /undercutrally           — today's U&Rs + last 7-day summary
          /undercutrally TICKER    — 30-day history for one ticker

        Shadow phase: telemetry-only, no entries. Undercut-and-rally entry mechanic
        per memory/user_tight_range_entry_techniques.md Entry #5. Stop = undercut low.
        """
        import re as _re
        from agents.market_intelligence.db import get_pool

        cands = _re.findall(r'\b([A-Z]{2,5})\b', request.task.upper())
        skip = _PREPOSITION_SKIP | {"UNDERCUTRALLY", "UR"}
        ticker = next((t for t in cands if t not in skip), None)

        from agents.market_intelligence.collector import _ET
        pool = await get_pool()
        async with pool.acquire() as conn:
            if ticker:
                rows = await conn.fetch("""
                    SELECT ur_date, ur_time, minutes_since_open,
                           parent_stage, base_low, undercut_low, undercut_pct,
                           current_price, reclaim_pct_above_base,
                           in_sugar_baby_cohort, parent_invalidated_eod
                    FROM mi_flag_undercut_rally
                    WHERE ticker = $1
                      AND ur_date >= CURRENT_DATE - INTERVAL '30 days'
                    ORDER BY ur_date DESC, ur_time DESC
                """, ticker)
                if not rows:
                    return self._ok(
                        request,
                        result=f"_No intraday U&Rs for `{ticker}` in last 30d._"
                    )
                lines = [f"🪤 *{ticker} — Intraday U&R history (30d)*", ""]
                for r in rows:
                    et_clock = r["ur_time"].astimezone(_ET).strftime("%H:%M")
                    inval = " ⚠️ invalidated_eod" if r["parent_invalidated_eod"] else ""
                    cohort = " 🍬" if r["in_sugar_baby_cohort"] else ""
                    lines.append(
                        f"  {r['ur_date']} {et_clock}{cohort} — "
                        f"{r['parent_stage']} undercut ${r['base_low']:.2f}→${r['undercut_low']:.2f} "
                        f"(-{r['undercut_pct']:.2f}%), reclaimed +{r['reclaim_pct_above_base']:.2f}%{inval}"
                    )
                return self._ok(request, result="\n".join(lines))

            today_rows = await conn.fetch("""
                SELECT ticker, ur_time, parent_stage, base_low, undercut_low,
                       undercut_pct, current_price, reclaim_pct_above_base,
                       in_sugar_baby_cohort, parent_invalidated_eod
                FROM mi_flag_undercut_rally
                WHERE ur_date = CURRENT_DATE
                ORDER BY ur_time
            """)
            recent_summary = await conn.fetch("""
                SELECT ur_date,
                       COUNT(*) AS n_urs,
                       COUNT(*) FILTER (WHERE in_sugar_baby_cohort) AS n_cohort,
                       COUNT(*) FILTER (WHERE parent_invalidated_eod) AS n_invalidated
                FROM mi_flag_undercut_rally
                WHERE ur_date BETWEEN CURRENT_DATE - INTERVAL '7 days'
                                  AND CURRENT_DATE - INTERVAL '1 day'
                GROUP BY ur_date
                ORDER BY ur_date DESC
            """)

        lines = ["🪤 *Intraday U&R — Undercut & Rally*", ""]
        if today_rows:
            lines.append(f"*Today ({len(today_rows)})*:")
            for r in today_rows:
                et_clock = r["ur_time"].astimezone(_ET).strftime("%H:%M")
                cohort = "🍬 " if r["in_sugar_baby_cohort"] else ""
                inval = " ⚠️ invalidated_eod" if r["parent_invalidated_eod"] else ""
                lines.append(
                    f"  {et_clock} {cohort}`{r['ticker']}` — "
                    f"{r['parent_stage']} undercut ${r['base_low']:.2f}→${r['undercut_low']:.2f} "
                    f"(-{r['undercut_pct']:.2f}%), reclaimed +{r['reclaim_pct_above_base']:.2f}%{inval}"
                )
        else:
            lines.append("_No U&Rs today (yet)._")

        if recent_summary:
            lines.append("")
            lines.append("*Last 7 days (excl. today):*")
            for r in recent_summary:
                inval_note = (
                    f" ({r['n_invalidated']} invalidated_eod)"
                    if r["n_invalidated"] else ""
                )
                cohort_note = (
                    f" {r['n_cohort']} 🍬"
                    if r["n_cohort"] else ""
                )
                lines.append(
                    f"  {r['ur_date']}: {r['n_urs']} U&Rs{cohort_note}{inval_note}"
                )

        lines.append("")
        lines.append("_Drill-down: `/undercutrally TICKER` for 30-day history per ticker_")
        lines.append("_Shadow phase — telemetry only, no entries submitted (stop = undercut low)_")
        return self._ok(request, result="\n".join(lines))

    async def _handle_ma_pullbacks_query(self, request: AgentRequest) -> AgentResponse:
        """`/mapullbacks` — intraday MA-pullback detector surface (#96).

        Modes:
          /mapullbacks           — today's pullbacks + last 7-day summary
          /mapullbacks TICKER    — 30-day history for one ticker

        Classic VCP/Minervini pullback to SMA10 or SMA20. Shadow phase.
        """
        import re as _re
        from agents.market_intelligence.db import get_pool

        cands = _re.findall(r'\b([A-Z]{2,5})\b', request.task.upper())
        skip = _PREPOSITION_SKIP | {"MAPULLBACKS", "MAPULLBACK"}
        ticker = next((t for t in cands if t not in skip), None)

        from agents.market_intelligence.collector import _ET
        pool = await get_pool()
        async with pool.acquire() as conn:
            if ticker:
                rows = await conn.fetch("""
                    SELECT pullback_date, pullback_time, parent_stage,
                           ma_label, ma_value, day_low, current_price,
                           pct_below_ma, bounce_pct_from_low, volume_pct_of_adv,
                           in_sugar_baby_cohort, parent_invalidated_eod
                    FROM mi_flag_ma_pullbacks
                    WHERE ticker = $1
                      AND pullback_date >= CURRENT_DATE - INTERVAL '30 days'
                    ORDER BY pullback_date DESC, pullback_time DESC
                """, ticker)
                if not rows:
                    return self._ok(
                        request,
                        result=f"_No intraday MA-pullbacks for `{ticker}` in last 30d._"
                    )
                lines = [f"📉 *{ticker} — Intraday MA-pullback history (30d)*", ""]
                for r in rows:
                    et_clock = r["pullback_time"].astimezone(_ET).strftime("%H:%M")
                    inval = " ⚠️ invalidated_eod" if r["parent_invalidated_eod"] else ""
                    cohort = " 🍬" if r["in_sugar_baby_cohort"] else ""
                    lines.append(
                        f"  {r['pullback_date']} {et_clock}{cohort} — "
                        f"{r['parent_stage']} pulled to {r['ma_label']} "
                        f"${r['ma_value']:.2f} ({r['pct_below_ma']:+.2f}%), "
                        f"bounced +{r['bounce_pct_from_low']:.2f}% "
                        f"(vol {r['volume_pct_of_adv']:.0f}% ADV){inval}"
                    )
                return self._ok(request, result="\n".join(lines))

            today_rows = await conn.fetch("""
                SELECT ticker, pullback_time, parent_stage,
                       ma_label, ma_value, day_low, current_price,
                       pct_below_ma, bounce_pct_from_low, volume_pct_of_adv,
                       in_sugar_baby_cohort, parent_invalidated_eod
                FROM mi_flag_ma_pullbacks
                WHERE pullback_date = CURRENT_DATE
                ORDER BY pullback_time
            """)
            recent_summary = await conn.fetch("""
                SELECT pullback_date,
                       COUNT(*) AS n_pullbacks,
                       COUNT(*) FILTER (WHERE in_sugar_baby_cohort) AS n_cohort,
                       COUNT(*) FILTER (WHERE parent_invalidated_eod) AS n_invalidated
                FROM mi_flag_ma_pullbacks
                WHERE pullback_date BETWEEN CURRENT_DATE - INTERVAL '7 days'
                                        AND CURRENT_DATE - INTERVAL '1 day'
                GROUP BY pullback_date
                ORDER BY pullback_date DESC
            """)

        lines = ["📉 *Intraday MA-Pullbacks*", ""]
        if today_rows:
            lines.append(f"*Today ({len(today_rows)})*:")
            for r in today_rows:
                et_clock = r["pullback_time"].astimezone(_ET).strftime("%H:%M")
                cohort = "🍬 " if r["in_sugar_baby_cohort"] else ""
                inval = " ⚠️ invalidated_eod" if r["parent_invalidated_eod"] else ""
                lines.append(
                    f"  {et_clock} {cohort}`{r['ticker']}` — "
                    f"{r['parent_stage']} pulled to {r['ma_label']} "
                    f"${r['ma_value']:.2f}, bounced "
                    f"+{r['bounce_pct_from_low']:.2f}% "
                    f"(vol {r['volume_pct_of_adv']:.0f}% ADV){inval}"
                )
        else:
            lines.append("_No MA-pullbacks today (yet)._")

        if recent_summary:
            lines.append("")
            lines.append("*Last 7 days (excl. today):*")
            for r in recent_summary:
                inval_note = (
                    f" ({r['n_invalidated']} invalidated_eod)"
                    if r["n_invalidated"] else ""
                )
                cohort_note = (
                    f" {r['n_cohort']} 🍬"
                    if r["n_cohort"] else ""
                )
                lines.append(
                    f"  {r['pullback_date']}: {r['n_pullbacks']} pullbacks{cohort_note}{inval_note}"
                )

        lines.append("")
        lines.append("_Drill-down: `/mapullbacks TICKER` for 30-day history per ticker_")
        lines.append("_Shadow phase — telemetry only, no entries submitted_")
        return self._ok(request, result="\n".join(lines))

    async def _handle_breadth_query(self, request: AgentRequest) -> AgentResponse:
        """`/breadth` — Stockbee cluster-matrix breadth view.

        Renders last 10 trading days × 6 column matrix in Telegram
        monospace, colored per breadth_color_rules.py SSoT:
          - daily 4% counts (paired up/down)
          - 5d ratio
          - 1M ±25% paired
          - 1M ±50% paired
          - T2108 (contrarian)

        Cluster signal status reported at the bottom: ≥3 red days in
        last 5 with recency filter → 'cluster deterioration' note.

        Uses existing data computed nightly; missing thrust metrics (up
        20%+/5d, up 13%+/34d) filed as separate follow-ups.
        """
        from agents.market_intelligence.db import get_breadth_history
        from agents.market_intelligence.breadth_color_rules import (
            paired_color, t2108_color, cluster_fires,
            red_count_in_window, secondary_first_red,
            CLUSTER_WINDOW, CLUSTER_RED_THRESHOLD,
        )

        monitors = await get_breadth_history(limit=10)
        if not monitors:
            return self._ok(
                request,
                result="_No breadth history available — nightly job may not have run yet._"
            )

        # Header — Telegram monospace block with fixed-width columns.
        # Paired counts allotted 4 digits each side (handles spikes like
        # 1090 down-4% days). Format: "emoji 1234/1234".
        header = "Date    4%   ↑/↓        5d    1M±25%       1M±50%       T2108"
        sep = "─" * len(header)
        lines = [
            "📊 *Breadth Matrix — last 10 trading days*",
            "",
            "```",
            header,
            sep,
        ]

        def _paired_cell(up, down):
            if up is None or down is None:
                return " " * 11  # width: emoji(1) + " "(1) + "1234/1234"(9) = 11
            emoji = paired_color(up, down) or " "
            return f"{emoji} {up:>4}/{down:<4}"

        def _t2108_cell(value):
            if value is None:
                return "  -  "
            emoji = t2108_color(value) or " "
            return f"{emoji} {value:>3.0f}%"

        for m in monitors:
            d_str = m["date"].strftime("%m/%d")
            today_cell = _paired_cell(m.get("today_up4"), m.get("today_down4"))
            r5 = m.get("ratio_5d")
            r5_cell = f"{r5:>4.2f}" if r5 is not None else "  - "
            m25_cell = _paired_cell(m.get("up_25_1m"), m.get("down_25_1m"))
            m50_cell = _paired_cell(m.get("up_50_1m"), m.get("down_50_1m"))
            t_cell = _t2108_cell(m.get("t2108"))

            lines.append(f"{d_str:6}  {today_cell}  {r5_cell}  {m25_cell}  {m50_cell}  {t_cell}")

        lines.append("```")
        lines.append("")

        # Cluster signal status
        red_count = red_count_in_window(monitors)
        if cluster_fires(monitors):
            lines.append(
                f"⚠️ *Cluster deterioration*: {red_count} red days in last "
                f"{CLUSTER_WINDOW} (threshold ≥{CLUSTER_RED_THRESHOLD}, recent)"
            )
            if secondary_first_red(monitors):
                lines.append("⚠️ *First red in secondary today* — signal-of-signals")
        else:
            lines.append(f"_Cluster status: {red_count}/{CLUSTER_WINDOW} red days (no fire)_")

        return self._ok(request, result="\n".join(lines))

    async def _handle_time_stop_command(self, request: AgentRequest) -> AgentResponse:
        """`/timestop TICKER` — operator-confirm exit of a 9M Day 2 meanderer.

        The EOD scan job (#91, 2026-05-23) flags 9M Day 2 positions held
        ≥5 trading days with highest_price_seen excursion <+3%. Operator
        reviews the alert + chart and confirms via this command, which:

        1. Re-fetches the trade row from DB (defensive: don't trust the
           alert payload; ensures highest_price_seen reflects any
           overnight WebSocket fills since the EOD alert composed)
        2. Re-checks the discriminator (defensive against stale alerts —
           if the position rallied since the alert, we DON'T exit)
        3. Submits TimeInForce.OPG market sell via alpaca_client; fills
           at next regular-session open (Alpaca queues across weekends/
           holidays — Friday submit on Memorial Day weekend fills Tuesday)
        4. Tags the exit jsonb row with reason='time_stop'
        5. Emits time_stop_executed audit event for the
           time_stop_9m_day2_effectiveness_n10 data-gated review
        """
        import re as _re
        from agents.market_intelligence.db import get_pool

        # Parse ticker from task. Strip /timestop prefix, take the first
        # 2-5 char uppercase token.
        task_text = request.task.strip()
        cands = _re.findall(r'\b([A-Z]{2,5})\b', task_text.upper())
        skip = _PREPOSITION_SKIP | {"TIMESTOP"}
        ticker = next((t for t in cands if t not in skip), None)
        if not ticker:
            return self._ok(
                request,
                result=(
                    "Usage: `/timestop TICKER`\n\n"
                    "Exits a flagged 9M Day 2 meanderer at next market open. "
                    "Candidates are surfaced via the daily 4:55 PM ET EOD scan."
                ),
            )

        pool = await get_pool()
        async with pool.acquire() as conn:
            # Re-fetch trade row fresh at command time (not from alert payload).
            row = await conn.fetchrow("""
                SELECT id, ticker, alert_date, filled_at::date AS filled_d,
                       entry_price, stop_price, remaining_shares,
                       highest_price_seen, signal_type, account_mode, status,
                       (SELECT COUNT(*)::int FROM generate_series(
                            filled_at::date + 1, CURRENT_DATE, '1 day') s
                        WHERE EXTRACT(DOW FROM s) BETWEEN 1 AND 5) AS trading_days
                FROM mi_live_trades
                WHERE ticker = $1
                  AND status = 'filled'
                  AND signal_type = '9m_day2'
                ORDER BY filled_at DESC LIMIT 1
            """, ticker)

        if row is None:
            return self._ok(
                request,
                result=(
                    f"_No open 9M Day 2 position for `{ticker}`._\n\n"
                    "`/timestop` only operates on currently-filled 9m_day2 trades. "
                    "Check `/trades` for current open positions."
                ),
            )

        if row["highest_price_seen"] is None or row["entry_price"] is None:
            return self._ok(
                request,
                result=f"_`{ticker}` has incomplete excursion tracking; cannot evaluate time-stop. Manual exit recommended._",
            )

        entry = float(row["entry_price"])
        high = float(row["highest_price_seen"])
        high_excur_pct = (high - entry) / entry * 100.0
        trading_days = row["trading_days"] or 0

        # Defensive re-check: if position rallied since the alert, DON'T exit.
        # Soft warning rather than hard reject — operator may still want to
        # exit a position that briefly rallied then died.
        if trading_days < 5 or high_excur_pct >= 3.0:
            return self._ok(
                request,
                result=(
                    f"⚠️ `{ticker}` no longer meets time-stop criteria:\n"
                    f"  • trading days held: {trading_days} (need ≥5)\n"
                    f"  • peak excursion: {high_excur_pct:+.2f}% (need <+3%)\n\n"
                    f"Position rallied since the EOD alert OR is too fresh. "
                    f"Not exiting. Re-check tomorrow if the meander resumes."
                ),
            )

        # Submit market-on-open sell via alpaca_client.
        shares = float(row["remaining_shares"]) if row["remaining_shares"] else 0
        if shares <= 0:
            return self._ok(
                request,
                result=f"_`{ticker}` has zero remaining shares — already exited?_",
            )

        try:
            from agents.market_intelligence.broker.alpaca_client import (
                place_market_on_open_sell, make_client_order_id,
            )
            account_mode = row["account_mode"] or "paper"
            coid = make_client_order_id(account_mode, "9m_day2_timestop", ticker)
            order = await place_market_on_open_sell(
                ticker, qty=shares, account_mode=account_mode,
                client_order_id=coid,
            )
        except Exception as e:
            return self._ok(
                request,
                result=(
                    f"❌ Market-on-open sell submit failed for `{ticker}`: {e}\n\n"
                    f"Common causes: outside OPG submission window "
                    f"(7 PM ET prior day → 9:25 AM ET next day), or Alpaca API issue. "
                    f"Try again pre-market or submit a manual exit during market hours."
                ),
            )

        # Audit event — load-bearing for the
        # time_stop_9m_day2_effectiveness_n10 data-gated review.
        from agents.market_intelligence.db import log_audit_event
        await log_audit_event(
            "time_stop_executed",
            f"{ticker} 9m_day2 — "
            f"trading_days={trading_days} "
            f"high_excur={high_excur_pct:+.2f}% "
            f"entry=${entry:.2f} "
            f"shares={shares:.0f} "
            f"order_id={order.get('id', '?')}",
        )

        return self._ok(
            request,
            result=(
                f"✅ *Time-stop submitted for `{ticker}`*\n\n"
                f"  • Trading days held: {trading_days}\n"
                f"  • Peak excursion: {high_excur_pct:+.2f}%\n"
                f"  • Shares: {shares:.0f} · entry ${entry:.2f}\n"
                f"  • Order: TimeInForce.OPG market sell (id `{order.get('id', '?')}`)\n"
                f"  • Account mode: {account_mode}\n\n"
                f"_Fills at next regular-session open. Slot freed once filled._"
            ),
        )

    async def _handle_partial_now_command(self, request: AgentRequest) -> AgentResponse:
        """`/partialnow TICKER [CONFIRM]` — operator-confirm immediate partial exit.

        Post-IBM-cascade follow-up (#138, 2026-05-28). Pre-fix: operator
        had to manually trigger partial exits via `docker exec python -c`
        which bypassed the credential bootstrap — caused the 2026-05-27
        sync_positions mass-close cascade. This command goes through the
        agent process + existing `execute_partial_exit` (which has the
        post-#136 atomic replace_order + same-window retry).

        After-hours guard (#141, 2026-05-28): The IBM cascade R4 root
        cause was Alpaca paper share-reservation quirks on after-hours
        retries. Outside the safe 9:30-16:50 ET window, the command
        requires explicit `CONFIRM` suffix to proceed.
        """
        import re as _re
        from agents.market_intelligence.db import get_pool, log_audit_event
        from agents.market_intelligence.broker.order_manager import execute_partial_exit
        from agents.market_intelligence.trading_calendar import is_market_hours_now_et

        task_text = request.task.strip()
        upper = task_text.upper()
        confirmed = "CONFIRM" in upper
        cands = _re.findall(r'\b([A-Z]{2,5})\b', upper)
        skip = _PREPOSITION_SKIP | {"PARTIALNOW", "PARTIAL", "CONFIRM"}
        ticker = next((t for t in cands if t not in skip), None)
        if not ticker:
            return self._ok(
                request,
                result=(
                    "Usage: `/partialnow TICKER [CONFIRM]`\n\n"
                    "Immediate partial exit (1/3 sell) for a filled position. "
                    "Goes through existing execute_partial_exit safeguards (atomic "
                    "stop replace, same-window retry, dedup against pending exits). "
                    "Replaces the docker-exec workaround that caused the 2026-05-27 cascade.\n\n"
                    "Outside 9:30-16:50 ET, append `CONFIRM` to acknowledge "
                    "the after-hours Alpaca paper share-reservation risk class "
                    "(IBM cascade R4)."
                ),
            )

        # After-hours guard (#141): /partialnow needs the 16:50 ET tail
        # buffer so the 16:45 ET scheduled partial-take still fits inside
        # the safe window. Outside that, Alpaca paper's share-reservation
        # quirks deadlock partial-exit retries (IBM cascade R4).
        if not is_market_hours_now_et(end_buffer_minutes=50) and not confirmed:
            from zoneinfo import ZoneInfo
            now_et = datetime.now(ZoneInfo("America/New_York"))
            return self._ok(
                request,
                result=(
                    f"⚠️ *`/partialnow {ticker}` blocked — outside safe window*\n\n"
                    f"Current ET: `{now_et.strftime('%a %H:%M')}`\n"
                    f"Safe window: Mon-Fri 09:30–16:50 ET\n\n"
                    f"Outside this window, Alpaca paper's share-reservation "
                    f"system can deadlock partial-exit retries (IBM cascade R4 "
                    f"root cause). Steady-state cron at 16:45 ET fills cleanly; "
                    f"random late-night attempts hit the quirk.\n\n"
                    f"Either:\n"
                    f"  • Wait for next market open\n"
                    f"  • Append `CONFIRM` if you accept the risk: "
                    f"`/partialnow {ticker} CONFIRM`"
                ),
            )

        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT id, ticker, remaining_shares, partial_taken,
                       entry_price, stop_price, signal_type, account_mode
                FROM mi_live_trades
                WHERE ticker = $1 AND status = 'filled'
                ORDER BY filled_at DESC LIMIT 1
            """, ticker)

        if row is None:
            return self._ok(
                request,
                result=f"_No open filled position for `{ticker}`. Check `/trades`._",
            )
        if row["partial_taken"]:
            return self._ok(
                request,
                result=(
                    f"_`{ticker}` already has partial_taken=TRUE._\n\n"
                    f"This position has already had its 1/3 sell. Use Alpaca web "
                    f"UI for additional exits if needed."
                ),
            )

        remaining = int(row["remaining_shares"] or 0)
        if remaining < 3:
            return self._ok(
                request,
                result=(
                    f"_`{ticker}` has only {remaining} shares — too few for 1/3 partial._"
                ),
            )
        sell_qty = remaining // 3

        try:
            # force=True: operator-confirmed attended action bypasses the #151c
            # circuit breaker (which exists to pause UNATTENDED cron retries).
            ok = await execute_partial_exit(int(row["id"]), sell_qty, force=True)
        except Exception as e:
            return self._ok(
                request,
                result=f"❌ `/partialnow {ticker}` raised: {type(e).__name__}: {e}",
            )

        from agents.market_intelligence.audit_events import PARTIAL_NOW_OPERATOR_CONFIRMED
        await log_audit_event(
            PARTIAL_NOW_OPERATOR_CONFIRMED,
            f"{ticker} trade_id={row['id']} qty={sell_qty} success={ok}",
        )

        if ok:
            return self._ok(
                request,
                result=(
                    f"✅ *Partial exit submitted for `{ticker}`*\n\n"
                    f"  • Sell: {sell_qty} of {remaining} shares (1/3)\n"
                    f"  • Strategy: `{row['signal_type']}` · mode: `{row['account_mode']}`\n"
                    f"  • Stop pre-replaced on remaining {remaining - sell_qty} shares\n\n"
                    f"_Watch Telegram for fill confirmation._"
                ),
            )
        return self._ok(
            request,
            result=(
                f"❌ Partial exit returned False for `{ticker}`. "
                f"Check `/audit partial_exit` for details."
            ),
        )

    async def _handle_sync_now_command(self, request: AgentRequest) -> AgentResponse:
        """`/syncnow [mode]` — operator-confirm DB↔Alpaca sync_positions.

        Post-IBM-cascade follow-up (#138, 2026-05-28). The 2026-05-27
        incident had Claude running sync_positions via `docker exec` to
        investigate, which bypassed the credential bootstrap; Alpaca
        returned [] and 3 trades got mass-closed before the safety guard
        was added (commit fa49304 / #137).

        This command runs the same code path through the agent process,
        with the #137 safety guard intact. Optional mode arg restricts
        to paper or live; default = both.
        """
        import re as _re
        from agents.market_intelligence.broker.order_manager import (
            sync_positions, _sync_positions_for_mode,
        )
        from agents.market_intelligence.db import log_audit_event

        task_text = request.task.lower()
        if " paper" in task_text:
            modes = ["paper"]
        elif " live" in task_text:
            modes = ["live"]
        else:
            modes = None  # use sync_positions() default

        try:
            if modes is None:
                messages = await sync_positions()
                mode_label = "all modes"
            else:
                messages = []
                for m in modes:
                    msgs = await _sync_positions_for_mode(m)
                    messages.extend([f"[{m}] {x}" for x in (msgs or [])])
                mode_label = ", ".join(modes)
        except Exception as e:
            return self._ok(
                request,
                result=f"❌ `/syncnow` raised: {type(e).__name__}: {e}",
            )

        from agents.market_intelligence.audit_events import SYNC_NOW_OPERATOR_CONFIRMED
        await log_audit_event(
            SYNC_NOW_OPERATOR_CONFIRMED,
            f"mode={mode_label} discrepancies={len(messages)}",
        )

        if not messages:
            return self._ok(
                request,
                result=f"✅ `/syncnow {mode_label}` — no DB↔broker discrepancies.",
            )
        body = "\n".join(f"  • {m}" for m in messages[:20])
        more = (
            f"\n\n_…and {len(messages) - 20} more (truncated)_"
            if len(messages) > 20 else ""
        )
        return self._ok(
            request,
            result=(
                f"⚠️ *`/syncnow {mode_label}` — {len(messages)} discrepancies handled*\n\n"
                f"{body}{more}\n\n"
                f"_Safety guard intact (won't mass-close on broker [] when DB has active trades)._"
            ),
        )

    async def _handle_setup_query(self, request: AgentRequest) -> AgentResponse:
        """`/setup TICKER [days]` — reverse-lookup detector chronology.

        Merges every detector hit (EP/9M/wick/parabolic/flag/themes/trades/
        watchlist) into a single dated timeline. Read-only.
        """
        import re as _re
        from agents.market_intelligence.db import (
            get_ticker_setup_timeline, get_security_exchange_map, get_pool,
            get_ep_scan_log_for_ticker,
        )
        from agents.market_intelligence.friday_watchlist import (
            _TV_EXCHANGE_MAP, _TG_SAFE_LIMIT,
        )
        from agents.market_intelligence.briefing import send_telegram_message
        import os as _os, httpx as _httpx

        # Plain-text variant of friday_watchlist._send_with_keyboard. Skipping
        # parse_mode entirely sidesteps the failure mode where dynamic content
        # (prev_5d, 9M_SUGAR, etc.) contains unbalanced underscores/asterisks
        # and Telegram returns 400, falling back to ugly raw rendering.
        async def _send_plain_with_keyboard(text: str, keyboard: list[list[dict]]) -> bool:
            bot_token = _os.environ.get("TELEGRAM_BOT_TOKEN")
            allowed = _os.environ.get("TELEGRAM_ALLOWED_USER_IDS", "")
            ids = [x.strip() for x in allowed.split(",") if x.strip()]
            if not bot_token or not ids:
                return False
            payload = {
                "chat_id": int(ids[0]),
                "text": text,
                "disable_web_page_preview": True,
                "reply_markup": {"inline_keyboard": keyboard},
            }
            try:
                async with _httpx.AsyncClient(timeout=15) as client:
                    r = await client.post(
                        f"https://api.telegram.org/bot{bot_token}/sendMessage",
                        json=payload,
                    )
                    r.raise_for_status()
                return True
            except Exception as e:
                logger.warning(f"setup plain send failed: {e}")
                return False

        raw = request.task.strip()
        # Strip leading slash command if present.
        if raw.lower().startswith("/setup"):
            raw_args = raw[len("/setup"):].strip()
        elif raw.lower().startswith("setup"):
            raw_args = raw[len("setup"):].strip()
        else:
            raw_args = raw

        tokens = raw_args.split()
        skip = _PREPOSITION_SKIP | {"SETUP", "SHOW", "FOR", "THE"}
        ticker: str | None = None
        days = 180
        for tok in tokens:
            up = tok.upper()
            if tok.isdigit():
                days = max(1, min(int(tok), 730))
            elif up in skip:
                continue
            elif up.replace(".", "").isalpha() and 1 <= len(up) <= 8:
                if ticker is None:
                    ticker = up
        if not ticker:
            return self._ok(request, result="Usage: `/setup TICKER [days]`")

        result = await get_ticker_setup_timeline(ticker, days=days)
        events = result["events"]
        rs_ctx = result["rs_context"]
        raw_count = result["raw_count"]
        cap = result["cap"]

        if not events and not rs_ctx:
            return self._ok(
                request,
                result=f"🔍 *{ticker}* — no detector hits in last {days}d. "
                       f"Try `/setup {ticker} 365`.",
            )

        # Compact source tags with emoji for visual scan.
        SRC_TAG = {
            "TRADE-LIVE":  "💰 LIVE",
            "TRADE-PAPER": "📝 PAPER",
            "FLAG":        "🏁 FLAG",
            "EP-MAGNA":    "🎯 EP",
            "9M-INTRADAY": "⚡ 9M",
            "9M-SUGAR":    "🍬 SUGAR",
            "WICK":        "🕯 WICK",
            "PARABOLIC":   "📈 PARA",
            "THEME":       "🎨 THEME",
            "WATCHLIST":   "📋 WATCH",
        }

        # Render in plain text — dynamic content (skip-reason details, theme
        # names, prev_5d, etc.) routinely contains underscores/asterisks that
        # unbalance Telegram Markdown and force a fallback that prints raw `*`
        # and `_`. Emojis + indentation already provide the visual structure.

        # Prefer the LLM-generated description from mi_ticker_overrides; fall
        # back to sector from mi_stock_scores or mi_ticker_overrides; omit the
        # blurb entirely when neither exists (LAC-class names that aren't in
        # any theme universe yet).
        pool = await get_pool()
        async with pool.acquire() as conn:
            ov = await conn.fetchrow(
                "SELECT description, sector FROM mi_ticker_overrides WHERE ticker = $1",
                ticker,
            )
        ov_desc = (ov["description"] if ov else None) or None
        ov_sector = (ov["sector"] if ov else None) or None
        score_sector = rs_ctx.get("sector") if rs_ctx else None
        blurb = ov_desc or ov_sector or score_sector  # description preferred

        lines = [f"🔍 {ticker} — last {days}d"]
        if rs_ctx:
            rank = rs_ctx.get("rs_rank")
            ctx_bits = []
            if rank is not None:
                ctx_bits.append(f"RS #{rank}")
            ctx_bits.append(f"{raw_count} events")
            lines.append(" · ".join(ctx_bits))
        else:
            lines.append(f"{raw_count} events")
        if blurb:
            lines.append(blurb)

        # Group events by date so the reader sees daily clusters at a glance.
        # Events are already date-DESC sorted.
        current_date = None
        for ev in events:
            d = ev["date"]
            ds = d.isoformat() if hasattr(d, "isoformat") else str(d)
            if ds != current_date:
                lines.append("")
                lines.append(f"📅 {ds}")
                current_date = ds
            tag = SRC_TAG.get(ev["source"], ev["source"])
            lines.append(f"  {tag} · {ev['summary']}")

        if raw_count > cap:
            lines.append("")
            lines.append(
                f"…{raw_count - cap} more events truncated — "
                f"narrow with /setup {ticker} 30."
            )

        # EP scan outcomes (#171) — surface WHY a ticker did/didn't alert
        # (cooldown drops etc.). The detector-hit timeline above can't show this:
        # a dropped ticker leaves no hit, so "why didn't X alert?" was a dead end.
        try:
            scan_rows = await get_ep_scan_log_for_ticker(ticker, limit=6)
        except Exception as _e:
            scan_rows = []
            logger.warning(f"/setup scan-log fetch failed for {ticker}: {_e}")
        if scan_rows:
            lines.append("")
            lines.append("📋 EP scan (recent days evaluated):")
            for r in scan_rows:
                sd = r["scan_date"]
                sds = sd.isoformat() if hasattr(sd, "isoformat") else str(sd)
                fr = r.get("filter_reason")
                sc = r.get("ep_score")
                tier = r.get("score_tier")
                if fr:
                    lines.append(f"  {sds} · dropped — {fr}")
                elif sc is not None:
                    lines.append(f"  {sds} · scored {int(sc)} {tier or ''}".rstrip())
                else:
                    lines.append(f"  {sds} · evaluated")

        body_text = "\n".join(lines)

        # TradingView chart button — single button since digest is ticker-scoped.
        try:
            ex_map = await get_security_exchange_map([ticker])
            tv_prefix = _TV_EXCHANGE_MAP.get(ex_map.get(ticker, ""), "NASDAQ")
            tv_url = f"https://www.tradingview.com/chart/?symbol={tv_prefix}:{ticker}"
            keyboard = [[{"text": f"📈 {ticker} chart", "url": tv_url}]]

            # _send_with_keyboard is a single Bot API POST (no auto-split);
            # send_telegram_message auto-splits at 4000 chars but can't attach
            # reply_markup. If the body fits, send body+keyboard in one shot;
            # otherwise send body via the auto-splitter and trail a tiny
            # button-only message.
            if len(body_text) <= _TG_SAFE_LIMIT:
                delivered = await _send_plain_with_keyboard(body_text, keyboard)
            else:
                body_ok = await send_telegram_message(body_text)
                btn_ok = await _send_plain_with_keyboard(f"📈 {ticker} chart →", keyboard)
                delivered = bool(body_ok and btn_ok)

            if delivered:
                # Empty result string makes the orchestrator's LLM loop
                # produce "(no response)" — see core/orchestrator.py:254.
                # Return a short delivery confirmation so Claude has
                # something to acknowledge instead of falling through to
                # the empty-block fallback.
                return self._ok(
                    request,
                    result=f"`/setup {ticker}` digest delivered to Telegram.",
                )
            logger.warning(f"setup delivery returned False for {ticker}")
            return self._ok(request, result=body_text)
        except Exception as e:
            logger.warning(f"setup keyboard send failed for {ticker}: {e}")
            return self._ok(request, result=body_text)

    async def _handle_9m_ep_outcomes(self, request: AgentRequest) -> AgentResponse:
        """Show 9M sugar baby history and Day 2 trade status."""
        import re as _re
        from agents.market_intelligence.db import get_9m_ep_history

        task = request.task.lower()
        m = _re.search(r'(\d+)\s*d(?:ay)?s?', task)
        days = min(int(m.group(1)), 180) if m else 90

        babies = await get_9m_ep_history(days=days)

        if not babies:
            return self._ok(request, f"No 9M EP sugar baby records in the last {days}d.")

        traded = [b for b in babies if b.get("day2_status") == "traded"]
        pending = [b for b in babies if b.get("day2_status") == "pending"]

        lines = [f"*9M EP Sugar Babies — last {days}d*\n"]
        lines.append(f"Total: {len(babies)} | Traded: {len(traded)} | Pending: {len(pending)}\n")

        from agents.market_intelligence.ninem_detector import _shape_tag

        for b in babies[:25]:
            status_icon = {"traded": "✅", "pending": "⏳", "skipped": "⏭️"}.get(
                b.get("day2_status", ""), "❓"
            )
            vol_m = b["volume"] / 1_000_000
            rp = int(b["close_in_range_pct"] * 100)
            tag = _shape_tag(b)
            p20 = b.get("prev_20d_pct")
            extra_bits = []
            if p20 is not None:
                extra_bits.append(f"20d {p20:+.0f}%")
            if tag:
                extra_bits.append(tag)
            extra = f" | {' / '.join(extra_bits)}" if extra_bits else ""
            lines.append(
                f"{status_icon} `{b['ticker']}` {b['alert_date']} — "
                f"Vol {vol_m:.1f}M | Range {rp}% | {b.get('day2_status', 'unknown')}{extra}"
            )

        return self._ok(request, result="\n".join(lines))

    async def _handle_9m_trades(self, request: AgentRequest) -> AgentResponse:
        """
        Show 9M Day 2 ORB trade log, or manually trigger a Day 2 trade for a ticker.
        Commands:
          '9m trades [Nd]'    — show recent 9M trades
          'trade 9m TICKER'   — manually queue Day 2 ORB for TICKER
        """
        import re as _re
        from agents.market_intelligence.db import get_9m_live_trades

        task = request.task.lower()

        # Manual trigger: 'trade 9m TICKER'
        manual_match = _re.search(r'trade\s+9m\s+([A-Z]{1,5})', request.task.upper())
        if manual_match:
            ticker = manual_match.group(1)
            from agents.market_intelligence.db import get_pending_9m_sugar_babies
            from agents.market_intelligence.collector import et_today, prev_trading_days
            from agents.market_intelligence.broker.live_tracker import submit_9m_day2_trade

            today = et_today()
            yesterday = prev_trading_days(1, from_date=today)[0]
            candidates = await get_pending_9m_sugar_babies(yesterday)
            match = next((c for c in candidates if c["ticker"] == ticker), None)
            if not match:
                return self._ok(
                    request,
                    f"No pending 9M sugar baby for {ticker} from {yesterday}. "
                    f"Check 'show 9m' for available candidates.",
                )
            result = await submit_9m_day2_trade(match)
            action = result.get("action", "unknown")
            return self._ok(
                request,
                f"9M Day2 `{ticker}`: {action}" + (
                    f" (trade_id={result['trade_id']})" if result.get("trade_id") else ""
                ),
            )

        # Trade log view
        m = _re.search(r'(\d+)\s*d(?:ay)?s?', task)
        days = min(int(m.group(1)), 180) if m else 30

        trades = await get_9m_live_trades(days=days)

        if not trades:
            return self._ok(request, f"No 9M EP trades in the last {days}d.")

        open_t = [t for t in trades if t["status"] == "filled"]
        closed_t = [t for t in trades if t["status"] == "closed"]
        total_pnl = sum(t["total_pnl"] or 0 for t in closed_t)
        winners = sum(1 for t in closed_t if (t["total_pnl"] or 0) > 0)

        lines = [f"*9M EP Trades — last {days}d*\n"]
        lines.append(
            f"Total: {len(trades)} | Open: {len(open_t)} | Closed: {len(closed_t)} | "
            f"Winners: {winners} | P&L: ${total_pnl:+.0f}\n"
        )

        for t in trades[:20]:
            status_icon = {"filled": "🟢", "closed": "⚪", "skipped": "⏭️",
                           "cancelled": "❌"}.get(t["status"], "❓")
            pnl_str = f" P&L: ${t['total_pnl']:+.0f}" if t.get("total_pnl") else ""
            lines.append(
                f"{status_icon} `{t['ticker']}` {t['alert_date']} — "
                f"Entry ${t['entry_price'] or 0:.2f} | Stop ${t['stop_price'] or 0:.2f}"
                f"{pnl_str} | {t['status']}"
            )

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
            from agents.market_intelligence.broker.skip_reasons import humanize
            lines.append("```")
            lines.append("Ticker  Date        Skip reason                     D1      D5")
            lines.append("------  ----------  ------------------------------  ------  ------")
            for r in filtered:
                ticker_s = r["ticker"].ljust(6)
                dt       = str(r["alert_date"])[:10]
                reason_s = (humanize(r.get("skip_reason")) or "?")[:30].ljust(30)
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

    async def _handle_missed_query(self, request: AgentRequest) -> AgentResponse:
        """Top missed EPs ranked by forward return — opportunity-cost surface.

        Routes:
          /missed              → 30d window, 5d return
          /missed 60           → 60d window, 5d return
          /missed 20d          → 30d window, 20d return horizon
          /missed by reason    → per-category roll-up
        """
        import re as _re
        from agents.market_intelligence.missed_outcomes import (
            top_missed_winners, missed_by_category,
            format_missed_telegram,
        )
        task = request.task.lower()

        # Window (days back to scan source tables): default 30, max 90
        m = _re.search(r'(?<!\d)(\d{1,3})\s*d?\b', task)
        window_days = 30
        if m:
            window_days = min(int(m.group(1)), 90)

        # Horizon (forward-return column)
        horizon = "5d"
        if "20d" in task or "20 d" in task or "month" in task:
            horizon = "20d"
        elif "1d" in task or "next day" in task:
            horizon = "1d"

        if "by reason" in task or "by category" in task or "breakdown" in task:
            cats = await missed_by_category(window_days=window_days)
            if not cats:
                return self._ok(request, result=f"🔍 No missed-EP data in last {window_days}d.")
            from agents.market_intelligence.missed_outcomes import (
                _humanize_category, _CATEGORY_KIND, _KIND_LABELS,
            )
            lines = [
                f"🔍 *Missed EPs by skip reason (last {window_days}d)*",
                "_kind: operational=we never evaluated · signal=trade-time weak ·_",
                "_       tier=scored but not entered · structural=outside trade universe_",
                "",
                "```",
                "reason                    kind          n    avg    ≥10%  top",
            ]
            for c in cats:
                cat = c.get("skip_category") or "filter_other"
                n = c.get("n") or 0
                avg = c.get("avg_ret_5d")
                avg_s = (f"{avg*100:+3.0f}%" if avg is not None else "  —").rjust(5)
                n10 = c.get("n_10pct_plus") or 0
                top_t = (c.get("top_ticker") or "—")[:5]
                top_r = c.get("top_ret_5d")
                top_s = (f"{top_r*100:+3.0f}%" if top_r is not None else "  —").rjust(5)
                label = _humanize_category(cat)[:24].ljust(24)
                kind = _KIND_LABELS.get(_CATEGORY_KIND.get(cat, "other"), "—")[:12].ljust(12)
                lines.append(f"{label}  {kind}  {n:>3}  {avg_s}  {n10:>3}   {top_t} {top_s}")
            lines.append("```")
            return self._ok(request, result="\n".join(lines))

        include_untradeable = "all" in task or "untradeable" in task or "microcap" in task
        rows = await top_missed_winners(
            window_days=window_days, horizon=horizon, per_category=3,
            include_untradeable=include_untradeable,
        )
        return self._ok(
            request,
            result=format_missed_telegram(
                rows, horizon, window_days,
                include_untradeable=include_untradeable,
            ),
        )

    async def _handle_correlation_clusters(self, request: AgentRequest) -> AgentResponse:
        """Show today's correlation clusters."""
        from agents.market_intelligence.collector import last_trading_day
        today = et_today()
        query_date = last_trading_day(today)
        today_str = query_date.strftime("%Y-%m-%d")
        weekend_note = "" if query_date == today else f"  _(last trading day)_"
        clusters = await get_correlation_clusters(today_str)
        if not clusters:
            return self._ok(
                request,
                result=f"No correlation clusters for {today_str}{weekend_note} — run nightly pipeline first, or no groups of 4+ stocks hit the 0.85 residual threshold today.",
            )
        lines = [f"*Correlation Clusters — {today_str}*{weekend_note}", f"{len(clusters)} clusters  •  20d beta-adjusted window", "```"]
        for i, c in enumerate(clusters):
            label = chr(65 + i)
            tickers_str = "  ".join(c["tickers"])
            lines.append(
                f"{label}  {tickers_str:<40}  corr {c['mean_corr']:.2f}  avg RS {c['avg_rs']:.0f}"
            )
        lines.append("```")
        return self._ok(request, result="\n".join(lines))

    async def _handle_cooldown_query(self, request: AgentRequest) -> AgentResponse:
        """Show active validation cooldowns."""
        from datetime import datetime, timezone
        cooldowns = await get_active_cooldowns()
        if not cooldowns:
            return self._ok(request, result="No active cooldowns — all stocks eligible for assignment.")

        now = datetime.now(tz=timezone.utc)
        lines = [f"*Validation Cooldowns — {len(cooldowns)} active*", "```"]
        for c in cooldowns:
            days_left = max(0, (c["cooldown_until"] - now).days)
            chronic = " ⚠️ chronic" if c["removal_count"] >= 3 else ""
            lines.append(
                f"{c['ticker']:<6} {c['theme_name'][:30]:<30} {days_left:2}d left  "
                f"removed {c['removal_count']}×{chronic}"
            )
        lines.append("```")
        return self._ok(request, result="\n".join(lines))

    async def _handle_cooldown_bypass(self, request: AgentRequest) -> AgentResponse:
        """Bypass a validation cooldown: 'bypass cooldown TICKER [theme] [reason]'."""
        import re as _re
        task = request.task

        # Extract ticker — first ALL-CAPS word after the trigger phrase
        m = _re.search(r'(?:bypass|clear)\s+cooldown\s+([A-Z]{2,5})', task.upper())
        if not m:
            return self._ok(request, result="Usage: `bypass cooldown TICKER [theme name] [reason]`")

        ticker = m.group(1)

        # Extract optional theme name — quoted or next words before any lowercase text
        theme_name: str | None = None
        reason = ""
        after = task[m.end():].strip()
        quoted = _re.match(r'"([^"]+)"', after)
        if quoted:
            theme_name = quoted.group(1)
            reason = after[quoted.end():].strip()
        elif after:
            # Heuristic: if next word(s) are uppercase/title-case, treat as theme prefix
            reason = after

        count = await bypass_cooldown(ticker, theme_name, reason=reason)
        if count == 0:
            return self._ok(request, result=f"No active cooldown found for `{ticker}`{' in ' + theme_name if theme_name else ''}.")

        scope = f"'{theme_name}'" if theme_name else "all themes"
        await log_audit_event(
            "validation_cooldown_bypassed",
            summary=f"{ticker} cooldown bypassed ({scope})",
            detail=f"reason={reason or 'none'}",
        )

        # Check if chronic — warn user
        from datetime import datetime, timezone
        cooldowns = await get_active_cooldowns()
        chronic_note = ""
        # Check bypassed row (now marked bypassed, won't show in active list)
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT removal_count FROM mi_validation_cooldowns WHERE ticker=$1"
                + (" AND theme_name=$2" if theme_name else ""),
                *(( ticker, theme_name) if theme_name else (ticker,))
            )
        if row and row["removal_count"] >= 3:
            chronic_note = f"\n⚠️ Note: removed {row['removal_count']}× — consider `exclude {ticker}` for a permanent ban if this keeps happening."

        return self._ok(
            request,
            result=f"✅ Bypass set — `{ticker}` eligible for {scope} reassignment on next nightly run.{chronic_note}"
        )

    async def _handle_validation_report(self, request: AgentRequest) -> AgentResponse:
        """
        P3 — Aggregate paper trade performance report.
        Scaffold mode (N < 10): raw trade list + "collecting data" message.
        Full mode (N >= 10): win rate, avg P&L, breakdowns by regime/catalyst/gap.
        """
        from collections import defaultdict
        trades = await get_paper_trade_stats()
        n = len(trades)
        header = f"*Paper Trade Validation — {n} closed trade{'s' if n != 1 else ''}*"

        if n == 0:
            return self._ok(request, result=(
                f"{header}\n_No closed trades yet. ORB entries accumulate automatically._"
            ))

        if n < 10:
            lines = [header, f"_Collecting data — need ~10 for meaningful stats._\n"]
            for t in trades:
                pnl = t["total_pnl"] or 0
                sign = "+" if pnl >= 0 else ""
                lines.append(
                    f"`{t['ticker']}` {t['alert_date']}  "
                    f"{sign}{pnl:.1f}%  {t['regime'] or '?'}  "
                    f"{t['catalyst_quality'] or '?'}"
                )
            return self._ok(request, result="\n".join(lines))

        # Full report
        wins = [t for t in trades if (t["total_pnl"] or 0) > 0]
        losses = [t for t in trades if (t["total_pnl"] or 0) <= 0]
        avg_pnl = sum(t["total_pnl"] or 0 for t in trades) / n
        avg_hold = sum(t["hold_days"] or 0 for t in trades) / n

        lines = [
            header,
            "```",
            f"Win rate  {len(wins)/n*100:.0f}%  ({len(wins)}W / {len(losses)}L)",
            f"Avg P&L   {avg_pnl:+.1f}%",
            f"Avg hold  {avg_hold:.1f} days",
            "```",
        ]

        def _section(label, grouped):
            out = [f"\n*{label}*", "```"]
            for key, pnls in sorted(grouped.items()):
                w = sum(1 for p in pnls if p > 0)
                out.append(f"{key:<14} {w}/{len(pnls)} wins  avg {sum(pnls)/len(pnls):+.1f}%")
            out.append("```")
            return out

        def gap_bucket(g):
            g = g or 0
            if g < 10: return "<10%"
            if g < 15: return "10-15%"
            if g < 20: return "15-20%"
            return "20%+"

        by_regime: dict = defaultdict(list)
        by_cat: dict = defaultdict(list)
        by_gap: dict = defaultdict(list)
        for t in trades:
            pnl = t["total_pnl"] or 0
            by_regime[t["regime"] or "Unknown"].append(pnl)
            by_cat[t["catalyst_quality"] or "unknown"].append(pnl)
            by_gap[gap_bucket(t["gap_pct"])].append(pnl)

        lines += _section("By Regime", by_regime)
        lines += _section("By Catalyst", by_cat)

        gap_order = ["<10%", "10-15%", "15-20%", "20%+"]
        ordered_gap = {k: by_gap[k] for k in gap_order if k in by_gap}
        lines += _section("By Gap Size", ordered_gap)

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

    async def _handle_filtered_trades_grouped(self, request: AgentRequest) -> AgentResponse:
        """Filtered trades grouped by strategy → skip-reason category → tickers.

        Default scope: today (last_trading_day). Override with `Nd` in task
        ("filtered trades 7d"). Live path uses mi_live_trades.signal_type;
        the EOD-sim path falls back to bucketing every row under magna53
        (mi_paper_trades pre-dates the strategy framework).
        """
        import re as _re
        from collections import defaultdict
        from agents.market_intelligence.constants import LIVE_TRADING_ENABLED
        from agents.market_intelligence.collector import last_trading_day, et_today
        from agents.market_intelligence.broker.skip_reasons import humanize

        task = request.task.lower()
        m = _re.search(r"\b(\d+)d\b", task)
        window_days = int(m.group(1)) if m else 1

        today = last_trading_day(et_today())
        start = today if window_days == 1 else (
            today.fromordinal(today.toordinal() - (window_days - 1))
        )

        if LIVE_TRADING_ENABLED:
            sql = """
                SELECT ticker, alert_date, signal_type, skip_reason
                FROM mi_live_trades
                WHERE alert_date BETWEEN $1 AND $2
                  AND status IN ('skipped', 'cancelled', 'order_failed')
                ORDER BY alert_date DESC, ticker
            """
        else:
            sql = """
                SELECT ticker, alert_date, NULL::text AS signal_type, skip_reason
                FROM mi_paper_trades
                WHERE alert_date BETWEEN $1 AND $2
                  AND status = 'skipped'
                ORDER BY alert_date DESC, ticker
            """

        pool = await get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(sql, start, today)

        scope_label = today.strftime("%b %d") if window_days == 1 else f"last {window_days}d"
        if not rows:
            return self._ok(
                request,
                result=f"*Filtered Trades — {scope_label}*\n\nNo filtered trades.",
            )

        # Group: signal_type → category → list[(ticker, code)]
        strategy_emoji = {
            "magna53": "📈",
            "9m_day2": "🍬",
            "shadow_orb_5m": "📐",
            "parabolic_short": "🔻",
            "wick_fill": "🔥",
            "fishhook_v3": "🪝",
        }
        strategy_label = {
            "magna53": "MAGNA53 EP",
            "9m_day2": "9M Day 2",
            "shadow_orb_5m": "Shadow ORB 5m",
            "parabolic_short": "Parabolic Short",
            "wick_fill": "Wick Fill",
            "fishhook_v3": "Fishhook V3",
        }
        # signal_type → category → list[(ticker, reason_code)]
        grouped: dict[str, dict[str, list[tuple[str, str]]]] = defaultdict(
            lambda: defaultdict(list)
        )
        for r in rows:
            sig = r["signal_type"] or "magna53"
            reason = r["skip_reason"] or ""
            parts = reason.split(":", 2)
            category = parts[0] if len(parts) >= 2 else "other"
            code = parts[1] if len(parts) >= 2 else (reason or "unknown")
            grouped[sig][category].append((r["ticker"], code))

        total = len(rows)
        collapsed = total >= 6  # threshold for compact rendering

        lines = [f"*Filtered Trades — {scope_label} ({total})*"]
        sig_order = ["magna53", "9m_day2", "shadow_orb_5m",
                     "parabolic_short", "wick_fill", "fishhook_v3"]
        seen = list(grouped.keys())
        for sig in sig_order + [s for s in seen if s not in sig_order]:
            buckets = grouped.get(sig)
            if not buckets:
                continue
            n = sum(len(v) for v in buckets.values())
            emoji = strategy_emoji.get(sig, "•")
            label = strategy_label.get(sig, sig)
            lines.append(f"\n{emoji} *{label}* ({n})")
            for category in ("filter", "setup", "block", "infra", "window", "other"):
                items = buckets.get(category)
                if not items:
                    continue
                if collapsed:
                    by_code: dict[str, list[str]] = defaultdict(list)
                    for tk, code in items:
                        by_code[code].append(tk)
                    bits = [
                        f"{code} ({len(tks)}): {', '.join(tks)}" if len(tks) > 1
                        else f"{code}: {tks[0]}"
                        for code, tks in by_code.items()
                    ]
                    lines.append(f"  • _{category}_ — {' · '.join(bits)}")
                else:
                    for tk, _code in items:
                        # Find original row to humanize the full reason
                        full = next(
                            (r["skip_reason"] for r in rows
                             if r["ticker"] == tk and (r["signal_type"] or "magna53") == sig),
                            None,
                        )
                        lines.append(f"  • `{tk}` — {humanize(full)}")

        lines.append("\n_Use `/why TICKER` for the full reason + lifecycle._")
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

        # Structured grouped view for "filtered/skipped trades" — by strategy
        # then by skip_reason category. Single-ticker drill-downs still use
        # the per-row view below.
        if (("filtered" in task or "skipped" in task) and ticker is None
                and "open" not in task and "closed" not in task):
            return await self._handle_filtered_trades_grouped(request)

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

        # mi_paper_trades has entries column; mi_live_trades has entry_attempt int instead
        entries_col = "entries" if not LIVE_TRADING_ENABLED else "NULL::jsonb AS entries"
        attempt_col = "entry_attempt" if LIVE_TRADING_ENABLED else "NULL::int AS entry_attempt"
        async with pool.acquire() as conn:
            # entry_shares pulled for live-mode timeline rendering (paper has
            # the column too via entries[0].shares, but living off the
            # mi_paper_trades column directly is simpler if it exists).
            shares_col = "entry_shares" if LIVE_TRADING_ENABLED else "NULL::float AS entry_shares"
            rows = await conn.fetch(f"""
                SELECT ticker, alert_date, ep_score, gap_pct, catalyst_quality, regime,
                       status, skip_reason,
                       {entry_col} AS entry_price, orb_high, orb_low, stop_price,
                       total_pnl, hold_days,
                       exits, {entries_col}, {attempt_col}, {shares_col}
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

        from agents.market_intelligence.backtester.tracker import (
            parse_json_list, format_trade_attempts, format_trade_attempts_live,
            _attempt_count,
        )

        lines = [f"*{label}*\n"]

        is_skipped = lambda r: r["status"] not in ("open", "closed", "filled", "order_placed", "pending_confirmation", "confirmed")

        for r in rows:
            is_open = r["status"] in open_statuses
            pnl_positive = (r["total_pnl"] or 0) > 0
            status_emoji = "🟡" if is_open else ("✅" if pnl_positive else ("⊘" if is_skipped(r) else "❌"))
            date_str = r["alert_date"].strftime("%b %d")
            score = f"score={r['ep_score']:.0f}" if r["ep_score"] else ""
            gap = f"gap={r['gap_pct']:.1f}%" if r["gap_pct"] else ""

            num_attempts = r.get("entry_attempt") or _attempt_count(r.get("entries"))
            att_str = f" {num_attempts}x" if num_attempts > 1 else ""

            header = f"{status_emoji} *{r['ticker']}* {date_str} {gap} {score}{att_str}"
            lines.append(header)

            if is_skipped(r):
                from agents.market_intelligence.broker.skip_reasons import humanize
                lines.append(f"  Filtered: {humanize(r['skip_reason']) or 'unknown'}")
                continue

            # Live trades: rebuild timeline from entry_attempt + exits[]
            # (mi_live_trades has no `entries` JSONB). Paper trades: use
            # the legacy entries-based formatter against mi_paper_trades.
            if LIVE_TRADING_ENABLED:
                lines += format_trade_attempts_live(dict(r), prefix="  ")
            else:
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
        from agents.market_intelligence.db import latest_market_data_date
        today = et_today()
        # Resolve to most recent date with EP scan data — covers weekends, holidays,
        # AND the post-midnight pre-scan window on weekdays (today exists per the
        # calendar but no scan has run yet, so strict alert_date=today is empty).
        query_date = await latest_market_data_date(today) or today
        query_str = query_date.strftime("%Y-%m-%d")
        if query_date == today:
            data_tag = ""
        else:
            data_tag = f" _(data: {query_date.strftime('%a %b %-d').lstrip('0')})_"
        alerts = await get_today_ep_alerts(query_str)
        regime = await get_current_regime()

        if not alerts:
            result = (
                f"No EP alerts for {query_str}.{data_tag}\n"
                f"Market regime: {regime.get('regime')} (EP bar: {regime.get('ep_threshold')}+).\n"
                f"EP scanning runs every 5 min from 7:00–9:30 AM ET."
            )
        else:
            high = [e for e in alerts if e.get("score_tier") == "HIGH"]
            moderate = [e for e in alerts if e.get("score_tier") == "MODERATE"]
            # Shared EP message builder so the HUD /ep view, the /eps_detail
            # drill-down, and the briefing all render identically (code-ticker /
            # bold-gap headline + truncated italic catalyst, blank-line separated).
            from agents.market_intelligence.briefing import format_ep_message
            header = f"*EP alerts for {query_str}*{data_tag} — {len(high)} HIGH, {len(moderate)} MODERATE"
            result = format_ep_message(header, alerts)

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

    async def _handle_crypto_query(self, request: AgentRequest) -> AgentResponse:
        """Route crypto sub-commands. Telegram surfaces are gated by CRYPTO_RS_ENABLED."""
        from agents.market_intelligence.crypto.briefing import (
            render_crypto_top, render_alt_season_status,
        )

        task = (request.task or "").strip().lower()

        # /altseason or "alt season" -> trigger status
        if "altseason" in task or "alt season" in task or "btc dominance" in task \
                or "btc.d" in task or "stablecoin flow" in task or "total3" in task:
            body = await render_alt_season_status()
            return self._ok(request, result=body, data={})

        # /crypto <category> -> top RS within category
        # /crypto -> top 10 overall
        category: str | None = None
        cleaned = (
            task.replace("/crypto", "")
                .replace("crypto", "")
                .strip()
        )
        if cleaned:
            # Map common phrasings to CG category slugs.
            cleaned = cleaned.split()[0]  # first remaining word
            slug_aliases = {
                "ai": "artificial-intelligence",
                "memes": "meme-token",
                "meme": "meme-token",
                "privacy": "privacy-coins",
                "defi": "decentralized-finance-defi",
                "depin": "depin",
                "rwa": "real-world-assets-rwa",
                "solana": "solana-ecosystem",
                "base": "base-ecosystem",
            }
            category = slug_aliases.get(cleaned, cleaned)

        body = await render_crypto_top(category=category, limit=10)
        return self._ok(request, result=body, data={"category": category})

    async def _handle_regime_query(self, request: AgentRequest) -> AgentResponse:
        from agents.market_intelligence.briefing import _format_regime_section

        regime = await get_current_regime()
        # Use the same rich traffic-light formatter as the evening brief —
        # SPY/QQQ MAs, VIX context, Stockbee breadth (primary + secondary),
        # momentum counts, T2108, EP filter. One source of truth for regime
        # display across briefings and on-demand queries.
        body = _format_regime_section(regime, section_num=1)
        desc = (regime.get("description") or "").strip()
        result = body + (f"\n\n_{desc}_" if desc else "")
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

        # #167 nascent narrative themes (shadow/advisory) — cross-sector / govt-policy
        # themes the RS+correlation engine structurally misses, grouped from
        # catalyst-narrative (e.g. the 5/28 drone cohort). NOT live; accruing toward a
        # promote-gate. Error-wrapped: advisory only, must never break /themes.
        try:
            from agents.market_intelligence.db import get_narrative_theme_candidates
            narr = await get_narrative_theme_candidates(days=5)
            if narr:
                lines.append("\n🌱 *Nascent narrative themes* _(shadow — experimental, not live)_")
                for n in narr[:6]:
                    tks = " · ".join((n.get("tickers") or [])[:6])
                    lines.append(f"  • *{n['name']}* ({n['run_date']}): {tks}")
        except Exception:
            pass

        return self._ok(request, result="\n".join(lines), data={"themes": themes})

    async def _handle_postmortem(self, request: AgentRequest) -> AgentResponse:
        """
        Trade postmortem — joins EP alert, execution, forward returns, theme, regime
        into an LLM-synthesized recap per ticker.
          `postmortem TICKER`            → most recent closed trade
          `postmortem TICKER YYYY-MM-DD` → specific alert date
        No ticker → list 5 most recent closed trades as hints.
        """
        import re as _re
        from datetime import date as _date
        from agents.market_intelligence.postmortem import generate_postmortem_narrative

        task = request.task
        cands = _re.findall(r'\b([A-Z]{2,5})\b', task.upper())
        skip = _PREPOSITION_SKIP | {
            "POSTMORTEM", "POST", "MORTEM", "TRADE", "REVIEW",
            "FOR", "THE", "WITH", "AND", "WHAT",
        }
        ticker = next((t for t in cands if t not in skip), None)

        if not ticker:
            pool = await get_pool()
            async with pool.acquire() as conn:
                rows = await conn.fetch("""
                    SELECT ticker, alert_date, total_pnl
                    FROM mi_live_trades
                    WHERE status = 'closed'
                    ORDER BY closed_at DESC NULLS LAST LIMIT 5
                """)
                if not rows:
                    rows = await conn.fetch("""
                        SELECT ticker, alert_date, total_pnl
                        FROM mi_paper_trades
                        WHERE status = 'closed'
                        ORDER BY alert_date DESC LIMIT 5
                    """)
            if not rows:
                return self._ok(
                    request,
                    result="No closed trades yet. Use `postmortem TICKER` after a trade closes.",
                )
            lines = ["*Recent closed trades — use `postmortem TICKER`:*"]
            for r in rows:
                pnl = f"${r['total_pnl']:+,.0f}" if r['total_pnl'] is not None else "—"
                lines.append(f"• *{r['ticker']}* {r['alert_date']} {pnl}")
            return self._ok(request, result="\n".join(lines))

        date_m = _re.search(r'(\d{4}-\d{2}-\d{2})', task)
        alert_date = _date.fromisoformat(date_m.group(1)) if date_m else None

        narrative = await generate_postmortem_narrative(ticker, alert_date)
        return self._ok(request, result=narrative)

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

    async def _handle_slash_command(self, request: AgentRequest) -> AgentResponse:
        parts = request.task.strip().split()
        cmd = parts[0].lower()
        dispatch = {
            "/hud":            self._handle_hud,
            "/eps":            self._handle_ep_query,
            "/9m":             self._handle_9m_ep_query,
            "/themes":         self._handle_theme_query,
            "/clusters":       self._handle_correlation_clusters,
            "/regime":         self._handle_regime_query,
            "/positions":      self._handle_watchlist,
            "/pregame":        self._handle_pregame,
            "/trades":         self._handle_trades_detail,
            "/trade":          self._handle_trade_query,
            "/why":            self._handle_why_query,
            "/audit":          self._handle_audit_topic,
            "/parabolic":      self._handle_parabolic_exclusion,
            "/wick":           self._handle_wick_query,
            "/fishhook":       self._handle_fishhook_query,
            "/flags":          self._handle_flag_query,
            "/flag":           self._handle_flag_query,
            "/sugarbabies":    self._handle_sugar_babies_query,
            "/sugarbaby":      self._handle_sugar_babies_query,
            "/timestop":       self._handle_time_stop_command,
            "/partialnow":     self._handle_partial_now_command,
            "/syncnow":        self._handle_sync_now_command,
            "/flagbreaks":     self._handle_flag_breaks_query,
            "/flagbreak":      self._handle_flag_breaks_query,
            "/supporttests":   self._handle_support_tests_query,
            "/supporttest":    self._handle_support_tests_query,
            "/undercutrally":  self._handle_undercut_rally_query,
            "/ur":             self._handle_undercut_rally_query,
            "/mapullbacks":    self._handle_ma_pullbacks_query,
            "/mapullback":     self._handle_ma_pullbacks_query,
            "/breadth":        self._handle_breadth_query,
            "/watch":          self._handle_watchlist_query,
            "/inplay":         self._handle_stocks_in_play_query,
            "/setup":          self._handle_setup_query,
            "/dryrun":         self._handle_dryrun,
            "/strategy":       self._handle_strategy_command,
            "/watchlist":      self._handle_friday_watchlist,
            "/missed":         self._handle_missed_query,
            "/eps_detail":     self._handle_eps_detail,
            "/themes_detail":  self._handle_themes_detail,
            "/trades_detail":  self._handle_trades_detail,
            "/rubric":         self._handle_rubric_query,
        }
        handler = dispatch.get(cmd)
        if handler:
            return await handler(request)
        available = "  ".join(sorted(k for k in dispatch if not k.endswith("_detail")))
        return self._ok(request, result=f"Unknown command: `{cmd}`\n\nAvailable:\n`{available}`")

    async def _handle_why_query(self, request: AgentRequest) -> AgentResponse:
        """`/why TICKER [YYYY-MM-DD]` — per-ticker lifecycle timeline.

        Joins mi_ep_alerts (detection) + mi_live_trades (execution) +
        mi_audit_log (lifecycle events, bounded to the trading-day window in
        America/New_York to avoid pulling unrelated prior-setup events).

        Render style mirrors `/setup`: plain text + emoji tags + TV chart
        button. Markdown asterisks/underscores break on dynamic content
        (skip-reason details, catalyst sentences) and force ugly fallback.
        """
        import re as _re
        from datetime import date as _date
        from agents.market_intelligence.collector import et_today, _ET
        from agents.market_intelligence.db import get_pool, get_security_exchange_map
        from agents.market_intelligence.friday_watchlist import (
            _TV_EXCHANGE_MAP, _TG_SAFE_LIMIT,
        )
        from agents.market_intelligence.briefing import send_telegram_message
        import os as _os, httpx as _httpx

        async def _send_plain_with_keyboard(text: str, keyboard: list[list[dict]]) -> bool:
            bot_token = _os.environ.get("TELEGRAM_BOT_TOKEN")
            allowed = _os.environ.get("TELEGRAM_ALLOWED_USER_IDS", "")
            ids = [x.strip() for x in allowed.split(",") if x.strip()]
            if not bot_token or not ids:
                return False
            payload = {
                "chat_id": int(ids[0]),
                "text": text,
                "disable_web_page_preview": True,
                "reply_markup": {"inline_keyboard": keyboard},
            }
            try:
                async with _httpx.AsyncClient(timeout=15) as client:
                    r = await client.post(
                        f"https://api.telegram.org/bot{bot_token}/sendMessage",
                        json=payload,
                    )
                    r.raise_for_status()
                return True
            except Exception as e:
                logger.warning(f"why plain send failed: {e}")
                return False

        raw = request.task.strip()
        tokens = raw.split()
        cands = _re.findall(r'\b([A-Z]{2,5})\b', raw.upper())
        skip = _PREPOSITION_SKIP | {"WHY", "TRACE", "THE", "FOR", "AND", "WHAT",
                                     "ENTRY", "EXIT", "TRADE", "EP", "ORB", "WE", "DID"}
        ticker = next((t for t in cands if t not in skip), None)
        if not ticker:
            return self._ok(request, result="Usage: /why TICKER [YYYY-MM-DD]")

        target_date: _date | None = None
        for tok in tokens[1:]:
            try:
                target_date = _date.fromisoformat(tok)
                break
            except ValueError:
                continue

        pool = await get_pool()
        if target_date is None:
            # No date given → resolve to the most-recent activity for this
            # ticker (alert / trade / audit) instead of et_today(). User asks
            # `/why TWLO` days after the alert; today's date returns empty.
            async with pool.acquire() as conn:
                latest = await conn.fetchrow("""
                    SELECT MAX(d) AS d FROM (
                        SELECT MAX(alert_date) AS d FROM mi_ep_alerts WHERE ticker = $1
                        UNION ALL
                        SELECT MAX(alert_date) FROM mi_live_trades WHERE ticker = $1
                        UNION ALL
                        SELECT MAX((created_at AT TIME ZONE 'America/New_York')::date)
                          FROM mi_audit_log WHERE summary ILIKE '%' || $1 || '%'
                    ) u
                """, ticker)
            target_date = (latest["d"] if latest else None) or et_today()
        async with pool.acquire() as conn:
            alert = await conn.fetchrow("""
                SELECT ticker, alert_date, score_tier, ep_score, gap_pct,
                       catalyst, catalyst_quality, rel_volume
                FROM mi_ep_alerts
                WHERE ticker = $1 AND alert_date = $2
                ORDER BY ep_score DESC
                LIMIT 1
            """, ticker, target_date)
            trade = await conn.fetchrow("""
                SELECT status, skip_reason, orb_high, orb_low, entry_price,
                       stop_price, entry_shares, total_pnl, proposed_at,
                       confirmed_at, closed_at
                FROM mi_live_trades
                WHERE ticker = $1 AND alert_date = $2
            """, ticker, target_date)
            events = await conn.fetch("""
                SELECT created_at, event_type, summary, detail
                FROM mi_audit_log
                WHERE created_at >= ($1::date AT TIME ZONE 'America/New_York')
                  AND created_at <  (($1::date + INTERVAL '1 day') AT TIME ZONE 'America/New_York')
                  AND summary ~* ('\m' || $2 || '\M')
                ORDER BY created_at ASC
            """, target_date, ticker)
            # #171 — was it scanned but not alerted (cooldown etc.)? answers
            # "why didn't X alert?" when there's no mi_ep_alerts row.
            scan = await conn.fetchrow("""
                SELECT filter_reason, ep_score, gap_pct, score_tier
                FROM mi_ep_scan_log
                WHERE ticker = $1 AND scan_date = $2
                ORDER BY scan_time_et DESC NULLS LAST, id DESC
                LIMIT 1
            """, ticker, target_date)

        if not alert and not trade and not events and not scan:
            return self._ok(
                request,
                result=f"🔍 {ticker} — no alert / trade / audit events on {target_date}.",
            )

        from agents.market_intelligence.broker.skip_reasons import humanize

        lines = [f"📋 {ticker} — lifecycle {target_date}"]

        # 🎯 Detection
        lines.append("")
        if alert:
            lines.append(
                f"🎯 Detected: {alert['score_tier']} score {int(alert['ep_score'] or 0)}"
            )
            lines.append(
                f"   gap {float(alert.get('gap_pct') or 0):+.1f}%, "
                f"cat={alert.get('catalyst_quality') or 'n/a'}"
            )
            cat_full = alert.get("catalyst") or ""
            if cat_full:
                if len(cat_full) > 140:
                    cat = cat_full[:140].rsplit(" ", 1)[0] + "…"
                else:
                    cat = cat_full
                lines.append(f"   {cat}")
        else:
            if scan and scan.get("filter_reason"):
                # #171 — it WAS scanned, just not alerted; show why (e.g. cooldown).
                lines.append(f"🎯 Detected: scanned, NOT alerted — {scan['filter_reason']}")
                scan_bits = [f"gap {float(scan.get('gap_pct') or 0):+.1f}%"]
                if scan.get("ep_score") is not None:
                    scan_bits.append(
                        f"scan score {int(scan['ep_score'])} {scan.get('score_tier') or ''}".rstrip()
                    )
                lines.append("   " + ", ".join(scan_bits))
            else:
                lines.append("🎯 Detected: no mi_ep_alerts row (not a recognised EP)")

        # 💰 Outcome
        lines.append("")
        if trade:
            status = trade.get("status") or "?"
            reason = trade.get("skip_reason")
            ep_pr = trade.get("entry_price")
            sp = trade.get("stop_price")
            pnl = trade.get("total_pnl")
            if status == "skipped" and reason:
                lines.append(f"💰 Outcome: skipped — {humanize(reason)}")
            elif status in ("cancelled", "rejected") and reason:
                lines.append(f"💰 Outcome: {status} — {humanize(reason)}")
                if ep_pr and sp:
                    lines.append(f"   limit ${float(ep_pr):.2f}, stop ${float(sp):.2f}")
            elif status == "closed":
                pnl_v = float(pnl or 0)
                lines.append(f"💰 Outcome: closed P&L ${pnl_v:+,.2f}")
                if ep_pr:
                    lines.append(f"   entry ${float(ep_pr):.2f}, stop ${float(sp or 0):.2f}")
            elif status in ("filled", "order_placed", "pending_confirmation", "confirmed"):
                lines.append(f"💰 Outcome: {status}")
                if ep_pr:
                    lines.append(f"   entry ${float(ep_pr):.2f}, stop ${float(sp or 0):.2f}")
            else:
                tail = f" — {humanize(reason)}" if reason else ""
                lines.append(f"💰 Outcome: {status}{tail}")
        else:
            lines.append("💰 Outcome: no mi_live_trades row (silent drop — see lifecycle)")

        # 🔍 Fill diagnosis — only meaningful for cancelled/rejected (or
        # skipped with a price-related reason). Fetches minute bars in the
        # order's lifetime so the user can see what the tape did vs the
        # limit. Answers the "but the chart shows price went above ORB high
        # — why didn't it fill?" class of question (TWLO 5/01).
        diagnosis_states = ("cancelled", "rejected", "skipped")
        if (
            trade
            and (trade.get("status") or "") in diagnosis_states
            and trade.get("entry_price")
            and trade.get("proposed_at")
        ):
            try:
                from agents.market_intelligence.collector import get_minute_bars
                from datetime import datetime as _dt, timedelta as _td

                limit = float(trade["entry_price"])
                stop = float(trade.get("stop_price") or 0)
                orb_h = trade.get("orb_high")
                orb_l = trade.get("orb_low")
                t0 = trade["proposed_at"].astimezone(_ET)
                # Window upper bound = order's actual lifetime. Use closed_at
                # only — `confirmed_at` is the placement timestamp (often
                # equal to proposed_at), which collapses the window to zero
                # bars. If closed_at is NULL, default to ORB cleanup at
                # 10:00 ET (the system's actual cancellation deadline).
                if trade.get("closed_at"):
                    t1 = trade["closed_at"].astimezone(_ET)
                else:
                    t1 = _dt.combine(target_date, _dt.min.time(), tzinfo=_ET) + _td(hours=10)
                d_str = target_date.isoformat()
                bars = await get_minute_bars(ticker, d_str, d_str)
                in_window = []
                for b in bars:
                    bar_t = _dt.fromtimestamp(b["t"] / 1000, tz=_ET)
                    if t0 <= bar_t <= t1:
                        in_window.append((bar_t, float(b["h"]), float(b["l"])))

                lines.append("")
                lines.append("🔍 Fill diagnosis")
                ctx_bits = []
                if orb_h is not None: ctx_bits.append(f"ORB H ${float(orb_h):.2f}")
                if orb_l is not None: ctx_bits.append(f"L ${float(orb_l):.2f}")
                ctx_bits.append(f"limit ${limit:.2f}")
                if stop: ctx_bits.append(f"stop ${stop:.2f}")
                lines.append("   " + " · ".join(ctx_bits))
                lines.append(
                    f"   window {t0.strftime('%H:%M:%S')}–{t1.strftime('%H:%M:%S')} "
                    f"({len(in_window)} bars)"
                )

                if not in_window:
                    lines.append("   ⚠️ No price data for this window — feed gap.")
                else:
                    max_h = max(h for _, h, _ in in_window)
                    trigger = float(orb_h) if orb_h is not None else limit
                    touches_limit = [(t, h) for t, h, _ in in_window if h >= limit]
                    touched_trigger = max_h >= trigger

                    if not touched_trigger:
                        # Price never reached the buy trigger — clean no-fire.
                        lines.append(
                            f"   🟢 Price topped at ${max_h:.2f}, never reached trigger "
                            f"${trigger:.2f} — order correctly didn't fire."
                        )
                    elif not touches_limit:
                        # Trigger fired but price stayed below limit — rare; either the
                        # order activated and oscillated in the trigger-to-limit band
                        # without a seller, or the trigger is the limit (no buffer).
                        lines.append(
                            f"   🟡 Trigger ${trigger:.2f} touched but price stayed below "
                            f"limit ${limit:.2f} (window max ${max_h:.2f}) — no seller "
                            f"at limit price."
                        )
                    else:
                        first = touches_limit[0]
                        lines.append(
                            f"   🔴 Trigger ${trigger:.2f} hit at "
                            f"{first[0].strftime('%H:%M')}, price ran to ${max_h:.2f}."
                        )
                        lines.append(
                            f"   Price moved past limit ${limit:.2f} too fast — after "
                            f"the trigger fired, it never came back to the limit so no "
                            f"seller matched. (Wider buffer or stop-market would catch "
                            f"this; current buffer is 0.5%.)"
                        )
            except Exception as e:
                logger.warning(f"why fill-diagnosis failed for {ticker}: {e}")

        # 📅 Lifecycle — filter noise + humanize per-event summary.
        # Drop multi-ticker batch summaries (where this ticker is incidental)
        # and strip machine-readable scaffolding from per-event summary.
        if events:
            # Map event_type -> short human label; fall back to event_type
            # itself for unknown types.
            _EV_LABEL = {
                "ep_alert":         "EP detected",
                "orb_triggered":    "ORB armed",
                "orb_bar_fetched":  "ORB bar in",
                "orb_order_placed": "Order placed",
                "orb_filled":       "Filled",
                "orb_cancelled":    "Cancelled",
                "orb_skipped":      "Skipped",
                "orb_blocked":      "Blocked",
                "orb_unfilled_cancelled":  "ORB unfilled (10:00 cleanup)",
                "eod_unfilled_cancelled":  "EOD cleanup",
                "stop_updated":     "Stop updated",
                "stop_update_started":     "Stop update started",
                "partial_exit_committed":  "Partial exit",
                "trade_closed":     "Trade closed",
            }

            # Per-fill broker notifications — useful for execution forensics,
            # but /why is the detection-and-outcome view. Use /trade TICKER
            # for partial-fill breakdown.
            _EXEC_NOISE_TYPES = {
                "entry_partial_fill",
                "partial_exit_sell_placed",
                "partial_exit_stop_replaced",
            }

            def _clean(ev) -> str | None:
                """Return one-line human label, or None to drop the event."""
                summary = (ev["summary"] or "").strip()
                etype = ev["event_type"]
                if etype in _EXEC_NOISE_TYPES:
                    return None
                # Drop batch-summary events that just happen to mention this
                # ticker in a list ("[bar_stream] 2 alerts: [TEAM, TWLO]").
                if summary.startswith("[") and "alerts:" in summary:
                    return None
                # Strip noisy bracketed source tags like "[bar_stream]" /
                # "[cron_9_31]" — they're tracer info, not user-facing signal.
                import re as _re_local
                summary = _re_local.sub(r"^\[[^\]]+\]\s*", "", summary)
                # Drop trade_id, range tags, internal ID-style key=value.
                summary = _re_local.sub(r"\b(trade_id|range|risk|shares)=\S+", "", summary)
                summary = _re_local.sub(r"\s+", " ", summary).strip(" -—")
                label = _EV_LABEL.get(etype, etype.replace("_", " "))
                if summary:
                    return f"{label} — {summary[:80]}"
                return label

            cleaned = []
            for ev in events:
                line = _clean(ev)
                if line is None:
                    continue
                ts = ev["created_at"].astimezone(_ET).strftime("%H:%M:%S")
                cleaned.append(f"  {ts}  {line}")
            if cleaned:
                lines.append("")
                lines.append(f"📅 Lifecycle ({len(cleaned)} events)")
                lines.extend(cleaned[:25])
                if len(cleaned) > 25:
                    lines.append(f"  …{len(cleaned) - 25} more events")

        # Rubric snapshot (Phase 5, 2026-05-19) — append if cached
        # Theme membership (C8, 2026-05-19) — append for every /why
        try:
            from agents.market_intelligence.catalyst_metrics_extractor import (
                lookup_cached_metrics,
            )
            from agents.market_intelligence.catalyst_rubric_runtime import (
                format_rubric_for_telegram,
                get_theme_membership, format_theme_for_telegram,
            )
            _ru_extracted = await lookup_cached_metrics(ticker, target_date)
            if _ru_extracted:
                _ru_text = format_rubric_for_telegram(ticker, _ru_extracted, target_date)
                if _ru_text:
                    lines.append("")
                    lines.append(_ru_text)
                    lines.append(f"_Full breakdown: `/rubric {ticker}`_")
            # Theme line — independent of rubric
            try:
                _theme = await get_theme_membership(ticker)
                lines.append(format_theme_for_telegram(_theme))
            except Exception as _te:
                logger.debug(f"why theme block failed for {ticker}: {_te}")
        except Exception as _ru_e:
            logger.debug(f"why rubric block failed for {ticker}: {_ru_e}")

        body_text = "\n".join(lines)

        # TradingView chart button — matches /setup.
        try:
            ex_map = await get_security_exchange_map([ticker])
            tv_prefix = _TV_EXCHANGE_MAP.get(ex_map.get(ticker, ""), "NASDAQ")
            tv_url = f"https://www.tradingview.com/chart/?symbol={tv_prefix}:{ticker}"
            keyboard = [[{"text": f"📈 {ticker} chart", "url": tv_url}]]

            if len(body_text) <= _TG_SAFE_LIMIT:
                delivered = await _send_plain_with_keyboard(body_text, keyboard)
            else:
                body_ok = await send_telegram_message(body_text)
                btn_ok = await _send_plain_with_keyboard(f"📈 {ticker} chart →", keyboard)
                delivered = bool(body_ok and btn_ok)

            if delivered:
                return self._ok(request, result="")
            logger.warning(f"why delivery returned False for {ticker}")
            return self._ok(request, result=body_text)
        except Exception as e:
            logger.warning(f"why keyboard send failed for {ticker}: {e}")
            return self._ok(request, result=body_text)

    async def _handle_trade_query(self, request: AgentRequest) -> AgentResponse:
        """`/trade TICKER [YYYY-MM-DD]` — full trade anatomy.

        Buys / sells / stop edits chronologically, sourced from
        mi_live_orders (every order placed), mi_live_trades.exits[]
        (committed exits), and mi_audit_log (stop_update failures +
        naked-position windows that aren't in the orders table).

        Differs from /why: /why is detection + entry diagnosis
        ("why didn't this fire / why did it skip"). /trade is
        execution anatomy ("what happened to my money").
        """
        import re as _re
        import json as _json
        from datetime import date as _date, datetime as _dt
        from agents.market_intelligence.collector import _ET
        from agents.market_intelligence.db import get_pool, get_security_exchange_map
        from agents.market_intelligence.friday_watchlist import (
            _TV_EXCHANGE_MAP, _TG_SAFE_LIMIT,
        )
        from agents.market_intelligence.briefing import send_telegram_message
        import os as _os, httpx as _httpx

        async def _send_plain_with_keyboard(text: str, keyboard: list[list[dict]]) -> bool:
            bot_token = _os.environ.get("TELEGRAM_BOT_TOKEN")
            allowed = _os.environ.get("TELEGRAM_ALLOWED_USER_IDS", "")
            ids = [x.strip() for x in allowed.split(",") if x.strip()]
            if not bot_token or not ids:
                return False
            payload = {
                "chat_id": int(ids[0]),
                "text": text,
                "disable_web_page_preview": True,
                "reply_markup": {"inline_keyboard": keyboard},
            }
            try:
                async with _httpx.AsyncClient(timeout=15) as client:
                    r = await client.post(
                        f"https://api.telegram.org/bot{bot_token}/sendMessage",
                        json=payload,
                    )
                    r.raise_for_status()
                return True
            except Exception as e:
                logger.warning(f"trade plain send failed: {e}")
                return False

        raw = request.task.strip()
        tokens = raw.split()
        cands = _re.findall(r'\b([A-Z]{2,5})\b', raw.upper())
        skip = _PREPOSITION_SKIP | {"TRADE", "THE", "FOR", "AND", "MY"}
        ticker = next((t for t in cands if t not in skip), None)
        if not ticker:
            return self._ok(request, result="Usage: /trade TICKER [YYYY-MM-DD]")

        target_date: _date | None = None
        for tok in tokens[1:]:
            try:
                target_date = _date.fromisoformat(tok)
                break
            except ValueError:
                continue

        pool = await get_pool()
        async with pool.acquire() as conn:
            if target_date:
                trade = await conn.fetchrow("""
                    SELECT id, ticker, alert_date, status, entry_price,
                           stop_price, entry_shares, remaining_shares,
                           total_pnl, hold_days, exits, closed_at, entry_attempt
                    FROM mi_live_trades
                    WHERE ticker=$1 AND alert_date=$2
                    ORDER BY id DESC LIMIT 1
                """, ticker, target_date)
            else:
                # Prefer the most recent trade that actually entered (not skipped/
                # cancelled with zero shares). Falls back to most-recent if none
                # entered — preserves the old behaviour for ticker that only has
                # skip rows. Without this, `/trade SMCI` on a day SMCI also has
                # a skipped alert returns the empty row.
                trade = await conn.fetchrow("""
                    SELECT id, ticker, alert_date, status, entry_price,
                           stop_price, entry_shares, remaining_shares,
                           total_pnl, hold_days, exits, closed_at, entry_attempt
                    FROM mi_live_trades
                    WHERE ticker=$1
                      AND status NOT IN ('skipped','cancelled','rejected')
                    ORDER BY alert_date DESC, id DESC LIMIT 1
                """, ticker)
                if not trade:
                    trade = await conn.fetchrow("""
                        SELECT id, ticker, alert_date, status, entry_price,
                               stop_price, entry_shares, remaining_shares,
                               total_pnl, hold_days, exits, closed_at, entry_attempt
                        FROM mi_live_trades
                        WHERE ticker=$1
                        ORDER BY alert_date DESC, id DESC LIMIT 1
                    """, ticker)
            if not trade:
                tail = f" on {target_date}" if target_date else ""
                return self._ok(
                    request,
                    result=f"📋 {ticker} — no trade row{tail}. Try /why for skip/cancel diagnosis.",
                )

            orders = await conn.fetch("""
                SELECT id, alpaca_order_id, side, order_type, qty, filled_qty,
                       filled_avg_price, status, purpose, exit_reason,
                       stop_price, limit_price, submitted_at, filled_at,
                       cancelled_at
                FROM mi_live_orders
                WHERE trade_id=$1
                ORDER BY submitted_at ASC, id ASC
            """, trade["id"])

            # Audit events not represented in mi_live_orders: stop-update
            # attempts that failed before producing an order row, and the
            # naked-position window detection. Bounded to alert_date → close.
            window_end = trade.get("closed_at") or _dt.now(tz=_ET)
            events = await conn.fetch(r"""
                SELECT created_at, event_type, summary
                FROM mi_audit_log
                WHERE created_at >= ($1::date - INTERVAL '1 day')
                  AND created_at <= ($2::timestamptz + INTERVAL '1 day')
                  AND summary ~* ('\m' || $3 || '\M')
                  AND event_type IN (
                      'stop_update_started','stop_update_failed',
                      'naked_position_detected'
                  )
                ORDER BY created_at ASC
            """, trade["alert_date"], window_end, ticker)

        def _parse_exits(raw):
            if isinstance(raw, list):
                return raw
            try:
                return _json.loads(raw or "[]")
            except Exception:
                return []
        exits = _parse_exits(trade.get("exits"))

        entry_date = trade["alert_date"]
        closed_at = trade.get("closed_at")
        close_str = closed_at.astimezone(_ET).strftime("%m/%d") if closed_at else "open"
        pnl_v = float(trade.get("total_pnl") or 0)
        pnl_emoji = "✅" if pnl_v > 0 else ("❌" if pnl_v < 0 else "⚪")
        status = trade.get("status") or "?"
        entry_sh = int(trade.get("entry_shares") or 0)
        remaining = int(trade.get("remaining_shares") or 0)
        attempt = trade.get("entry_attempt") or 1

        attempt_tag = f" · attempt {attempt}" if attempt and attempt > 1 else ""
        lines = [
            f"📋 {ticker} — trade #{trade['id']} · {entry_date.strftime('%m/%d')} → {close_str}{attempt_tag}",
            f"   {pnl_emoji} P&L ${pnl_v:+,.2f}  ·  status={status}  ·  {entry_sh} sh entered, {remaining} remaining",
        ]

        # ENTRY — buy orders chronologically
        entry_orders = [o for o in orders if (o["side"] or "").lower() == "buy"]
        lines.append("")
        lines.append("ENTRY")
        if not entry_orders:
            lines.append("  (no entry orders recorded)")
        for o in entry_orders:
            sub = o["submitted_at"].astimezone(_ET) if o["submitted_at"] else None
            fil = o["filled_at"].astimezone(_ET) if o["filled_at"] else None
            qty = int(o["qty"] or 0)
            fq = int(o["filled_qty"] or 0)
            avg = o["filled_avg_price"]
            trig = o["stop_price"]
            lim = o["limit_price"]
            spec_bits = []
            if trig is not None:
                spec_bits.append(f"trigger ${float(trig):.2f}")
            if lim is not None:
                spec_bits.append(f"limit ${float(lim):.2f}")
            spec = " / ".join(spec_bits) if spec_bits else (o["order_type"] or "?")
            sub_s = sub.strftime("%m/%d %H:%M:%S") if sub else "—"
            lines.append(f"  {sub_s}  placed   {qty} sh  {spec}")
            st = (o["status"] or "").lower().split(".")[-1]
            if "fill" in st and fq > 0:
                avg_s = f"${float(avg):.2f}" if avg else "?"
                elapsed = ""
                if sub and fil:
                    secs = int((fil - sub).total_seconds())
                    elapsed = f"  ({secs // 60}m {secs % 60}s)" if secs >= 60 else f"  ({secs}s)"
                fil_s = fil.strftime("%m/%d %H:%M:%S") if fil else "—"
                lines.append(f"  {fil_s}  filled   {fq} sh @ {avg_s}{elapsed}")
            elif "cancel" in st:
                cx = o["cancelled_at"].astimezone(_ET) if o["cancelled_at"] else None
                cx_s = cx.strftime("%m/%d %H:%M:%S") if cx else "—"
                lines.append(f"  {cx_s}  cancelled")

        # STOPS — sell-side stop orders + audit events (failures, naked windows)
        stop_orders = [
            o for o in orders
            if o["purpose"] == "stop_loss"
            or ((o["side"] or "").lower() == "sell"
                and (o["order_type"] or "").lower().endswith("stop"))
        ]
        stop_items: list[tuple] = []
        for o in stop_orders:
            sub = o["submitted_at"].astimezone(_ET) if o["submitted_at"] else None
            cx = o["cancelled_at"].astimezone(_ET) if o["cancelled_at"] else None
            fil = o["filled_at"].astimezone(_ET) if o["filled_at"] else None
            sp = o["stop_price"]
            qty = int(o["qty"] or 0)
            fq = int(o["filled_qty"] or 0)
            avg = o["filled_avg_price"]
            sp_s = f"${float(sp):.2f}" if sp is not None else "?"
            st = (o["status"] or "").lower().split(".")[-1]
            if "fill" in st and fq > 0:
                avg_s = f"${float(avg):.2f}" if avg else "?"
                t = fil or sub
                stop_items.append((
                    t,
                    f"  {t.strftime('%m/%d %H:%M:%S')}  🔴 STOP HIT  {fq} sh @ {avg_s} (stop was {sp_s})",
                ))
            elif "cancel" in st:
                if sub:
                    stop_items.append((
                        sub,
                        f"  {sub.strftime('%m/%d %H:%M:%S')}  placed   {qty} sh @ {sp_s}",
                    ))
                if cx:
                    stop_items.append((
                        cx,
                        f"  {cx.strftime('%m/%d %H:%M:%S')}  cancelled (was {sp_s})",
                    ))
            else:
                t = sub
                stop_items.append((
                    t,
                    f"  {t.strftime('%m/%d %H:%M:%S') if t else '—'}  placed   {qty} sh @ {sp_s}  [{st}]",
                ))
        for e in events:
            ts = e["created_at"].astimezone(_ET)
            summary = (e["summary"] or "").strip()
            # Strip the "TICKER:" prefix and other tracer scaffolding
            summary = _re.sub(rf"^\s*{ticker}:\s*", "", summary)
            if e["event_type"] == "stop_update_failed":
                stop_items.append((
                    ts,
                    f"  {ts.strftime('%m/%d %H:%M:%S')}  ⚠️ update FAILED — {summary[:90]}",
                ))
            elif e["event_type"] == "naked_position_detected":
                stop_items.append((
                    ts,
                    f"  {ts.strftime('%m/%d %H:%M:%S')}  ⚠️ NAKED window (no broker stop active)",
                ))
            elif e["event_type"] == "stop_update_started":
                stop_items.append((
                    ts,
                    f"  {ts.strftime('%m/%d %H:%M:%S')}  update started — {summary[:60]}",
                ))
        stop_items.sort(key=lambda x: x[0] or _dt.min.replace(tzinfo=_ET))
        lines.append("")
        lines.append("STOPS")
        if not stop_items:
            lines.append("  (no stop orders or stop-update events)")
        for _, s in stop_items:
            lines.append(s)

        # EXITS — prefer the canonical exits[] JSONB; fall back to deriving
        # from mi_live_orders sell-side fills when that JSONB is empty but
        # broker orders show real fills (SMCI 5/06: partial + stop-hit
        # filled but never committed to exits[] — known data-integrity bug).
        lines.append("")
        lines.append("EXITS")
        if exits:
            for ex in exits:
                t_raw = ex.get("time") or ex.get("filled_at")
                try:
                    t = _dt.fromisoformat(t_raw).replace(tzinfo=_ET) if t_raw else None
                except Exception:
                    t = None
                price = ex.get("price")
                shares = int(ex.get("shares") or 0)
                reason = (ex.get("reason") or "?").replace("_", " ")
                ex_pnl = ex.get("pnl")
                pnl_s = f"${float(ex_pnl):+,.2f}" if ex_pnl is not None else "?"
                price_s = f"${float(price):.2f}" if price is not None else "?"
                ts_s = t.strftime("%m/%d %H:%M:%S") if t else "—"
                lines.append(f"  {ts_s}  {reason}   {shares} sh @ {price_s}   {pnl_s}")
        else:
            # Fallback: derive from filled sell orders. Estimate pnl per leg
            # using entry_price (best available — actual cost basis may differ
            # per partial). Mark "[derived]" so the user knows this came from
            # the orders table, not the canonical commit log.
            entry_basis = trade.get("entry_price")
            derived_exits = [
                o for o in orders
                if (o["side"] or "").lower() == "sell"
                and "fill" in (o["status"] or "").lower().split(".")[-1]
                and (o["filled_qty"] or 0) > 0
            ]
            if not derived_exits:
                lines.append("  (no exits committed)")
            else:
                lines.append("  [derived from mi_live_orders — exits[] JSONB is empty]")
                for o in derived_exits:
                    t = o["filled_at"].astimezone(_ET) if o["filled_at"] else None
                    fq = int(o["filled_qty"] or 0)
                    avg = o["filled_avg_price"]
                    reason = (o["exit_reason"] or o["purpose"] or "?").replace("_", " ")
                    price_s = f"${float(avg):.2f}" if avg else "?"
                    ts_s = t.strftime("%m/%d %H:%M:%S") if t else "—"
                    if entry_basis and avg:
                        leg_pnl = (float(avg) - float(entry_basis)) * fq
                        pnl_s = f"${leg_pnl:+,.2f}"
                    else:
                        pnl_s = "?"
                    lines.append(f"  {ts_s}  {reason}   {fq} sh @ {price_s}   {pnl_s}")

        body_text = "\n".join(lines)

        try:
            ex_map = await get_security_exchange_map([ticker])
            tv_prefix = _TV_EXCHANGE_MAP.get(ex_map.get(ticker, ""), "NASDAQ")
            tv_url = f"https://www.tradingview.com/chart/?symbol={tv_prefix}:{ticker}"
            keyboard = [[{"text": f"📈 {ticker} chart", "url": tv_url}]]
            if len(body_text) <= _TG_SAFE_LIMIT:
                delivered = await _send_plain_with_keyboard(body_text, keyboard)
            else:
                body_ok = await send_telegram_message(body_text)
                btn_ok = await _send_plain_with_keyboard(f"📈 {ticker} chart →", keyboard)
                delivered = bool(body_ok and btn_ok)
            if delivered:
                return self._ok(request, result="")
            return self._ok(request, result=body_text)
        except Exception as e:
            logger.warning(f"trade keyboard send failed for {ticker}: {e}")
            return self._ok(request, result=body_text)

    async def _handle_hud(self, request: AgentRequest) -> AgentResponse:
        msg = await _build_hud_text()
        return self._ok(request, result=msg)

    async def _handle_friday_watchlist(self, request: AgentRequest) -> AgentResponse:
        """Curated weekly watchlist — sends Telegram digest, returns ack."""
        from agents.market_intelligence.friday_watchlist import run_friday_watchlist
        try:
            result = await run_friday_watchlist(window_days=7, persist=False)
        except Exception as e:
            return self._ok(request, result=f"Friday watchlist failed: `{e}`")
        if result["delivered"]:
            return self._ok(
                request,
                result=f"📬 Watchlist sent — {result['row_count']} tickers.",
            )
        return self._ok(
            request,
            result=f"Watchlist generated ({result['row_count']} tickers) but Telegram delivery failed — check logs.",
        )

    async def _handle_pregame(self, request: AgentRequest) -> AgentResponse:
        """Compact trade-ready shortlist: regime, Accelerating themes, HIGH EPs, watchlist MAs, 9M."""
        import asyncio as _aio
        from agents.market_intelligence.db import (
            get_active_themes,
            get_overnight_watchlist,
            get_today_9m_ep_alerts,
            get_all_9m_sugar_babies,
            latest_market_data_date,
        )
        from agents.market_intelligence.collector import et_today, prev_trading_days

        today = et_today()
        # Roll back to most recent date with EP/9M scan data — covers post-midnight
        # pre-scan window AND weekends/holidays in one shot. If today has data
        # (post 7 AM scan), data_date == today and the tag below stays empty.
        data_date = await latest_market_data_date(today) or today
        data_date_str = data_date.isoformat()
        yesterday = prev_trading_days(1, from_date=data_date)[0]

        watchlist_rows = await get_overnight_watchlist()
        watchlist_tickers = [r["symbol"] for r in watchlist_rows]

        # Sugar babies for the next open: if data_date's EOD sweep has already run,
        # data_date's confirmed babies are what we'll trade next session. Otherwise
        # fall back to the prior trading day (regardless of day2_status — so
        # traded ones stay visible after their ORB orders fire).
        regime, ep_alerts, themes, ma_rows, ninem_alerts, sugar_today, sugar_yday = await _aio.gather(
            get_latest_regime(),
            get_today_ep_alerts(data_date_str),
            get_active_themes(),
            get_ma_pullbacks(data_date_str, tickers=watchlist_tickers or None),
            get_today_9m_ep_alerts(data_date_str),
            get_all_9m_sugar_babies(data_date),
            get_all_9m_sugar_babies(yesterday),
            return_exceptions=True,
        )
        sugar_babies = sugar_today if isinstance(sugar_today, list) and sugar_today else sugar_yday

        sep = "━━━━━━━━━━━━━━━━━━━━━"
        now_et = today.strftime("%a %b %-d %I:%M %p ET").lstrip("0")
        # Tag the data date when it's not today (weekend, holiday, or pre-scan window).
        if data_date != today:
            data_tag = f" _(data: {data_date.strftime('%a %b %-d').lstrip('0')})_"
        else:
            data_tag = ""
        lines = [f"📋 *Pregame — {now_et}*{data_tag}", sep]

        # Regime
        r = regime if isinstance(regime, dict) else {}
        regime_name = r.get("regime", "Unknown")
        qqq_ok = r.get("qqq_ema_bullish")
        qqq_icon = "✅" if qqq_ok else ("❌" if qqq_ok is False else "❓")
        ep_bar = r.get("ep_threshold", "?")
        lines.append(f"📈 Regime: *{regime_name}* | QQQ {qqq_icon} | EP bar: {ep_bar}")

        # Accelerating themes only — sort by rs_avg desc (was alphabetical from DB)
        if isinstance(themes, list):
            accel = [t for t in themes if t.get("stage") == "Accelerating"]
            accel.sort(key=lambda t: t.get("rs_avg") or 0, reverse=True)
            if accel:
                lines.append("")
                lines.append("🔥 *Accelerating Themes:*")
                for t in accel[:5]:
                    tks = " ".join((t.get("tickers") or [])[:4])
                    rs = t.get("rs_avg")
                    rs_str = f" (RS {rs:.0f})" if rs is not None else ""
                    lines.append(f"  {t['name']}{rs_str}  {tks}")

        # HIGH EPs only
        if isinstance(ep_alerts, list):
            high_eps = [e for e in ep_alerts if e.get("score_tier") == "HIGH"]
            if high_eps:
                lines.append("")
                lines.append(f"🎯 *HIGH EPs today ({len(high_eps)}):*")
                for ep in high_eps[:6]:
                    lines.append(
                        f"  *{ep['ticker']}*  {ep.get('gap_pct', 0):+.1f}%  score {ep['ep_score']:.0f}"
                    )
            else:
                lines.append("")
                lines.append("🎯 No HIGH EPs today yet.")

        # Watchlist MA pullbacks
        if isinstance(ma_rows, list) and ma_rows:
            lines.append("")
            lines.append("📍 *Watchlist near MAs:*")
            for row in ma_rows[:5]:
                pct = row.get("pct_from_ma", 0)
                lines.append(f"  {row['ticker']}  {row.get('ma_label','?')}  {pct:+.1f}%")

        # 9M sugar babies
        if isinstance(sugar_babies, list) and sugar_babies:
            icon = {"pending": "⏳", "traded": "✅", "skipped": "⏭️"}
            lines.append("")
            lines.append(f"🏦 *9M Day 2 ({len(sugar_babies)}):* " +
                         " ".join(f"{icon.get(b.get('day2_status') or '', '❓')}{b['ticker']}"
                                  for b in sugar_babies[:4]))
        else:
            lines.append("")
            lines.append("🏦 No 9M sugar babies.")

        return self._ok(request, result="\n".join(lines))

    async def _handle_rubric_query(self, request: AgentRequest) -> AgentResponse:
        """`/rubric TICKER [YYYY-MM-DD]` — full catalyst rubric breakdown.

        Surfaces the 6-axis methodology score + per-axis reasoning + source
        attribution + extraction quality. Use after an EP alert to dig into
        the methodology assessment, or to inspect an already-downgraded
        catalyst.
        """
        import re as _re
        from datetime import date as _date, datetime as _datetime
        from agents.market_intelligence.collector import et_today
        from agents.market_intelligence.catalyst_metrics_extractor import (
            lookup_cached_metrics, extract_earnings_metrics,
        )
        from agents.market_intelligence.catalyst_rubric_runtime import (
            format_rubric_full_breakdown,
        )
        from agents.market_intelligence.collector import (
            get_fmp_news, search_news_perplexity,
        )

        raw = request.task.strip()
        cands = _re.findall(r'\b([A-Z]{2,5})\b', raw.upper())
        skip = _PREPOSITION_SKIP | {"RUBRIC"}
        ticker = next((t for t in cands if t not in skip), None)
        if not ticker:
            return self._ok(request, result="Usage: /rubric TICKER [YYYY-MM-DD]")

        target_date: _date | None = None
        for tok in raw.split():
            try:
                target_date = _datetime.strptime(tok, "%Y-%m-%d").date()
                break
            except ValueError:
                continue
        if target_date is None:
            target_date = et_today()

        # Try cache first
        extracted = await lookup_cached_metrics(ticker, target_date)
        if extracted is None:
            # No cache for this ticker+date — run fresh extraction
            try:
                fmp_news = await get_fmp_news(ticker, limit=5)
                perplexity_text = await search_news_perplexity(
                    f"What caused {ticker} stock to gap up? Latest catalyst.",
                    recency="week",
                )
                extracted = await extract_earnings_metrics(
                    ticker, target_date,
                    claude_analysis=None,
                    perplexity_text=perplexity_text,
                    fmp_news=fmp_news,
                )
            except Exception as e:
                return self._ok(
                    request,
                    result=f"{ticker}: extraction failed — {e}",
                )

        text = format_rubric_full_breakdown(ticker, extracted, target_date)
        # Theme membership (C8) — append for /rubric command
        try:
            from agents.market_intelligence.catalyst_rubric_runtime import (
                get_theme_membership, format_theme_for_telegram,
            )
            _theme = await get_theme_membership(ticker)
            text += "\n\n" + format_theme_for_telegram(_theme)
        except Exception as _te:
            logger.debug(f"/rubric theme block failed for {ticker}: {_te}")
        return self._ok(request, result=text)

    async def _handle_eps_detail(self, request: AgentRequest) -> AgentResponse:
        """Inline keyboard detail: /eps_detail {tier} {date_str}"""
        from agents.market_intelligence.collector import last_trading_day
        parts = request.task.strip().split()
        # parts: ['/eps_detail', tier, date_str]
        tier = parts[1].upper() if len(parts) > 1 else "HIGH"
        date_str = parts[2] if len(parts) > 2 else last_trading_day().isoformat()

        alerts = await get_today_ep_alerts(date_str)
        # Shared EP message builder so this drill-down matches the HUD/keyword
        # `_handle_ep_query` and the morning briefing exactly.
        from agents.market_intelligence.briefing import format_ep_message

        high = [a for a in alerts if a.get("score_tier") == "HIGH"]
        mod = [a for a in alerts if a.get("score_tier") == "MODERATE"]

        if tier == "SUMMARY":
            return self._ok(request, result=f"🎯 *EP Alerts — {date_str}*\n{len(high)} HIGH · {len(mod)} MODERATE")

        if tier == "ALL":
            # Unified single-message view (2026-05-29): /ep shows ALL EPs at once
            # instead of a summary + [View HIGH]/[View MODERATE] drill-down step.
            # HIGH first, then MODERATE; the block's tier emoji (🔥/⚡) marks each.
            if not (high or mod):
                return self._ok(request, result=f"No EP alerts for {date_str}.")
            header = f"🎯 *EP Alerts — {date_str}* — {len(high)} HIGH, {len(mod)} MODERATE"
            return self._ok(request, result=format_ep_message(header, high + mod))

        filtered = [a for a in alerts if a.get("score_tier") == tier]
        if not filtered:
            return self._ok(request, result=f"No {tier} EP alerts for {date_str}.")

        header = f"🎯 *{tier} EPs — {date_str}* ({len(filtered)})"
        return self._ok(request, result=format_ep_message(header, filtered))

    async def _handle_themes_detail(self, request: AgentRequest) -> AgentResponse:
        """Inline keyboard detail: /themes_detail {stage|SUMMARY}"""
        from agents.market_intelligence.briefing import _compute_scored_themes, STAGE_EMOJI, _conviction_suffix

        parts = request.task.strip().split()
        stage_filter = parts[1] if len(parts) > 1 else "All"

        today_str = et_today().isoformat()
        themes = await get_today_themes(today_str)

        if not themes:
            return self._ok(request, result="No theme data yet.")

        if stage_filter == "SUMMARY":
            accel = sum(1 for t in themes if t.get("stage") == "Accelerating")
            nascent = sum(1 for t in themes if t.get("stage") == "Nascent")
            fading = sum(1 for t in themes if t.get("stage") == "Fading")
            return self._ok(
                request,
                result=(
                    f"🗂 *Themes — {today_str}*\n"
                    f"{len(themes)} active · {accel} accelerating · {nascent} nascent · {fading} fading"
                ),
            )

        all_tickers = list({tk for t in themes for tk in (t.get("tickers") or [])})
        theme_rs_data, prior_scores = await asyncio.gather(
            get_rs_for_tickers(today_str, all_tickers) if all_tickers else asyncio.sleep(0),
            get_prior_theme_scores(today_str),
        )
        if theme_rs_data is None:
            theme_rs_data = {}

        scored_themes, _ = _compute_scored_themes(themes, theme_rs_data, prior_scores or {})

        if stage_filter != "All":
            scored_themes = [t for t in scored_themes if t.get("stage") == stage_filter]

        if not scored_themes:
            return self._ok(request, result=f"No {stage_filter} themes.")

        lines = [f"*{stage_filter} Themes* ({len(scored_themes)})"]
        for st in scored_themes[:15]:
            emoji = STAGE_EMOJI.get(st["stage"], "")
            conviction = _conviction_suffix(st)
            lines.append(f"\n{emoji}*{st['name']}*{conviction}")
            tickers = " · ".join((st.get("tickers") or [])[:4])
            lines.append(f"  RS {int(st['comp'])}  {tickers}")
        return self._ok(request, result="\n".join(lines))

    async def _handle_trades_detail(self, request: AgentRequest) -> AgentResponse:
        """Inline keyboard detail: /trades_detail {view} [{date}]"""
        import json as _json
        from agents.market_intelligence.collector import last_trading_day

        parts = request.task.strip().split()
        view = parts[1].lower() if len(parts) > 1 else "summary"
        date_str = parts[2] if len(parts) > 2 else last_trading_day().isoformat()

        pool = await get_pool()

        def _parse_exits(raw) -> list:
            if isinstance(raw, list):
                return raw
            try:
                return _json.loads(raw or "[]")
            except Exception:
                return []

        def _fmt_closed_line(r: dict, attempts: int = 0) -> list[str]:
            pnl = float(r.get("total_pnl") or 0)
            emoji = "✅" if pnl > 0 else "❌"
            exits = _parse_exits(r.get("exits"))
            last = exits[-1] if exits else {}
            exit_price = last.get("price")
            # Underscores in reason (stop_hit, partial_profit, sma_trail_stop) break
            # Telegram Markdown V1 italic parsing — swap to spaces for display.
            reason = (last.get("reason") or "?").replace("_", " ")
            entry = r.get("entry_price")
            hold = r.get("hold_days") or 0
            score = r.get("ep_score") or 0
            entry_str = f"${entry:.2f}" if entry else "?"
            exit_str = f"${exit_price:.2f}" if exit_price else "?"
            closed_at = r.get("closed_at")
            date_suffix = f" · {closed_at.strftime('%b %d')}" if closed_at else ""
            # Always show attempt count — even '1 attempt' tells the reader
            # this is a fresh name and not a multi-try grind.
            attempts_label = "attempt" if attempts == 1 else "attempts"
            attempts_suffix = f" · {attempts} {attempts_label}" if attempts else ""
            return [
                f"  {emoji} *{r['ticker']}* ${pnl:+,.0f} ({hold}d){date_suffix}{attempts_suffix}",
                f"      {entry_str} → {exit_str} · {reason} · score {score:.0f}",
            ]

        async def _build_summary() -> str:
            """Open positions (with live Alpaca prices) + last 5 closed + totals."""
            from agents.market_intelligence.broker import alpaca_client as alpaca

            async with pool.acquire() as conn:
                open_rows = await conn.fetch("""
                    SELECT ticker, alert_date, entry_price, remaining_shares,
                           stop_price, hard_stop, total_pnl, hold_days,
                           partial_taken, breakeven_active, ep_score,
                           catalyst_quality, exits, stop_order_id
                    FROM mi_live_trades
                    WHERE status = 'filled' AND remaining_shares > 0
                    ORDER BY alert_date ASC
                """)
                pending_rows = await conn.fetch("""
                    SELECT ticker, alert_date, status, entry_shares, orb_high,
                           orb_low, stop_price, ep_score, catalyst_quality
                    FROM mi_live_trades
                    WHERE status IN ('order_placed', 'pending_confirmation')
                    ORDER BY alert_date ASC, ticker
                """)
                closed_rows = await conn.fetch("""
                    SELECT ticker, entry_price, total_pnl, hold_days,
                           exits, ep_score, closed_at
                    FROM mi_live_trades
                    WHERE status = 'closed'
                    ORDER BY closed_at DESC NULLS LAST
                    LIMIT 5
                """)
                stats = await conn.fetchrow("""
                    SELECT
                        COUNT(*) FILTER (WHERE status = 'closed' AND total_pnl > 0) AS winners,
                        COUNT(*) FILTER (WHERE status = 'closed' AND total_pnl <= 0) AS losers,
                        COALESCE(SUM(total_pnl) FILTER (WHERE status = 'closed'), 0) AS realized
                    FROM mi_live_trades
                """)
                # Per-ticker closed-attempt history — feeds open-row "prior
                # P&L" and closed-row "N attempts" suffixes. Bounded query
                # over the union of currently-relevant tickers.
                relevant_tickers = list({r["ticker"] for r in open_rows} |
                                         {r["ticker"] for r in closed_rows})
                ticker_history: dict[str, dict] = {}
                if relevant_tickers:
                    hist_rows = await conn.fetch("""
                        SELECT ticker,
                               COALESCE(SUM(entry_attempt), 0)::int AS attempts,
                               COALESCE(SUM(total_pnl), 0) AS realized
                        FROM mi_live_trades
                        WHERE status = 'closed' AND ticker = ANY($1)
                        GROUP BY ticker
                    """, relevant_tickers)
                    ticker_history = {h["ticker"]: dict(h) for h in hist_rows}

            # Fetch live prices per position (fire-and-forget fallback on failure)
            enriched = []
            unreal_total = 0.0
            for r in open_rows:
                d = dict(r)
                try:
                    pos = await alpaca.get_position(d["ticker"])
                except Exception:
                    pos = None
                if pos:
                    d["current_price"] = pos.get("current_price")
                    d["unrealized_pnl"] = pos.get("unrealized_pl") or 0
                    d["market_value"] = pos.get("market_value") or 0
                else:
                    d["current_price"] = None
                    d["unrealized_pnl"] = 0
                    d["market_value"] = 0
                unreal_total += float(d["unrealized_pnl"] or 0)
                enriched.append(d)

            lines: list[str] = []
            lines.append(f"📊 *Positions — {date_str}*")

            if enriched:
                lines.append("")
                lines.append(f"*Open ({len(enriched)})* · unreal ${unreal_total:+,.0f}")
                for p in enriched:
                    ticker = p["ticker"]
                    entry = p.get("entry_price")
                    current = p.get("current_price")
                    stop = p.get("stop_price")
                    shares = p.get("remaining_shares") or 0
                    hold = p.get("hold_days") or 0
                    unreal = float(p.get("unrealized_pnl") or 0)
                    mkt_val = float(p.get("market_value") or 0)
                    realized = float(p.get("total_pnl") or 0)
                    pnl_emoji = "🟢" if unreal > 0 else "🔴" if unreal < 0 else "⚪"
                    flags = []
                    if p.get("partial_taken"):
                        flags.append("partial")
                    if p.get("breakeven_active"):
                        flags.append("BE")
                    # NAKED indicator — stop_order_id IS NULL with live shares means
                    # update_stop / partial-exit / sync_positions cleared it after a
                    # placement failure and the next sync_positions hasn't remediated
                    # yet. Surface so the operator can sanity-check the broker side.
                    if p.get("stop_order_id") is None and shares > 0:
                        flags.append("⚠️ NAKED")
                    flag_str = f" ({', '.join(flags)})" if flags else ""

                    entry_str = f"${entry:.2f}" if entry else "?"
                    current_str = f"${current:.2f}" if current else "?"
                    stop_str = f"${stop:.2f}" if stop else "?"
                    pct_str = ""
                    if entry and current:
                        pct = (current - entry) / entry * 100
                        pct_str = f" ({pct:+.1f}%)"

                    hist = ticker_history.get(ticker)
                    prior_bits: list[str] = []
                    # Day 1 re-entry pattern: prior-attempt stop-outs live in
                    # this row's `exits` JSONB (same trade_id), not as separate
                    # closed rows. Sum stop_hit exits — those belong to closed
                    # prior attempts since the current attempt is still open.
                    in_row_exits = _parse_exits(p.get("exits"))
                    in_row_prior_pnl = sum(
                        float(e.get("pnl") or 0)
                        for e in in_row_exits
                        if (e.get("reason") or "").lower() == "stop_hit"
                    )
                    in_row_prior_n = sum(
                        1 for e in in_row_exits
                        if (e.get("reason") or "").lower() == "stop_hit"
                    )
                    if in_row_prior_n:
                        prior_bits.append(
                            f"in-trade {in_row_prior_n} prior "
                            f"${in_row_prior_pnl:+,.0f}"
                        )
                    if hist and hist["attempts"]:
                        prior_bits.append(
                            f"prior {hist['attempts']} closed "
                            f"${float(hist['realized']):+,.0f}"
                        )
                    prior_str = (" · " + " · ".join(prior_bits)) if prior_bits else ""
                    lines.append(
                        f"  {pnl_emoji} *{ticker}* · {hold}d{flag_str}\n"
                        f"      Entry {entry_str} → Now {current_str}{pct_str}\n"
                        f"      {shares:.0f} sh · ${mkt_val:,.0f} · Stop {stop_str}\n"
                        f"      Unreal ${unreal:+,.0f}"
                        + (f" · Real ${realized:+,.0f}" if realized else "")
                        + prior_str
                    )
            else:
                lines.append("")
                lines.append("_No open positions._")

            if pending_rows:
                lines.append("")
                lines.append(f"*Pending Entry ({len(pending_rows)})*")
                for pr in pending_rows:
                    shares = pr.get("entry_shares") or 0
                    buy_at = pr.get("orb_high")
                    stop_at = pr.get("orb_low") or pr.get("stop_price")
                    buy_str = f"${buy_at:.2f}" if buy_at else "?"
                    stop_str = f"${stop_at:.2f}" if stop_at else "?"
                    state_icon = "⏳" if pr["status"] == "order_placed" else "📝"
                    state_label = "order placed" if pr["status"] == "order_placed" else "awaiting confirm"
                    lines.append(
                        f"  {state_icon} *{pr['ticker']}* · {state_label}\n"
                        f"      Buy stop {buy_str} · Stop {stop_str} · {shares:.0f} sh"
                    )

            if closed_rows:
                lines.append("")
                lines.append(f"*Last {len(closed_rows)} Closed*")
                for r in closed_rows:
                    rd = dict(r)
                    hist = ticker_history.get(rd["ticker"])
                    attempts = int(hist["attempts"]) if hist else 0
                    lines += _fmt_closed_line(rd, attempts=attempts)

            winners = stats["winners"] or 0
            losers = stats["losers"] or 0
            realized = float(stats["realized"] or 0)
            closed_count = winners + losers
            if closed_count > 0:
                win_rate = winners / closed_count * 100
                lines.append("")
                lines.append("*Totals*")
                lines.append(
                    f"  W/L {winners}/{losers} ({win_rate:.0f}%) · Realized ${realized:+,.0f}"
                )

            return "\n".join(lines)

        if view == "summary":
            return self._ok(request, result=await _build_summary())

        # Retained for backwards compat — callback no longer surfaces this button,
        # but the route remains so older pinned messages still work.
        if view == "live":
            return self._ok(request, result=await _build_summary())

        if view == "paper":
            async with pool.acquire() as conn:
                rows = await conn.fetch("""
                    SELECT ticker, alert_date, last_entry_price, status, total_pnl, catalyst_quality
                    FROM mi_paper_trades
                    WHERE status != 'skipped'
                    ORDER BY alert_date DESC LIMIT 15
                """)
            if not rows:
                return self._ok(request, result="No paper trades recorded yet.")
            lines = [
                "📋 *Paper Trades* (legacy EOD sim — not updating; live trading is on Alpaca)",
                "",
            ]
            for r in rows:
                pnl_str = f"  P&L ${r['total_pnl']:+,.0f}" if r['status'] == 'closed' and r['total_pnl'] else ""
                lines.append(
                    f"  {r['alert_date']}  *{r['ticker']}*  {r['status']}{pnl_str}"
                )
            return self._ok(request, result="\n".join(lines))

        if view == "skipped":
            async with pool.acquire() as conn:
                rows = await conn.fetch("""
                    SELECT ticker, alert_date, ep_score, gap_pct, catalyst_quality,
                           status, skip_reason, orb_high, orb_low, atr_14
                    FROM mi_live_trades
                    WHERE status IN ('skipped', 'cancelled', 'order_failed')
                    ORDER BY alert_date DESC, ticker
                    LIMIT 15
                """)
            if not rows:
                return self._ok(request, result="No skipped trades recorded.")
            from agents.market_intelligence.broker.skip_reasons import humanize
            lines = [f"⊘ *Skipped Trades* (last {len(rows)})"]
            for r in rows:
                d_str = r["alert_date"].strftime("%b %d")
                gap = f" gap={r['gap_pct']:.1f}%" if r['gap_pct'] else ""
                score = f" score={r['ep_score']:.0f}" if r['ep_score'] else ""
                reason = humanize(r['skip_reason']) or "unknown"
                orb_hint = ""
                if r['orb_high'] and r['orb_low']:
                    orb_hint = f"  ORB H=${r['orb_high']:.2f} L=${r['orb_low']:.2f}"
                lines.append(f"\n*{r['ticker']}* {d_str}{gap}{score}")
                lines.append(f"  {reason}{orb_hint}")
            return self._ok(request, result="\n".join(lines))

        if view == "closed":
            # Show the last 20 closed trades — simpler than splitting today vs older,
            # and sidesteps any UTC/ET date-compare edge cases.
            async with pool.acquire() as conn:
                rows = await conn.fetch("""
                    SELECT ticker, entry_price, total_pnl, hold_days,
                           exits, ep_score, closed_at
                    FROM mi_live_trades
                    WHERE status = 'closed'
                    ORDER BY closed_at DESC NULLS LAST
                    LIMIT 20
                """)
            if not rows:
                return self._ok(request, result="No closed trades recorded yet.")

            net = sum(float(r["total_pnl"] or 0) for r in rows)
            wins = sum(1 for r in rows if float(r["total_pnl"] or 0) > 0)
            losses = len(rows) - wins
            lines = [
                f"📊 *Closed Trades* (last {len(rows)})",
                f"  W/L {wins}/{losses} · net ${net:+,.0f}",
                "",
            ]
            for r in rows:
                lines += _fmt_closed_line(dict(r))

            return self._ok(request, result="\n".join(lines))

        return self._ok(request, result=f"Unknown view: {view}")

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

        response = await self._claude.messages.create(
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


async def _build_hud_text() -> str:
    """Standalone HUD text builder — returns a plain str. Shared by _handle_hud and _hud_refresh_job."""
    import asyncio as _aio
    from agents.market_intelligence.db import (
        get_active_themes,
        get_today_9m_ep_alerts,
        get_all_9m_sugar_babies,
    )
    from agents.market_intelligence.collector import et_today, prev_trading_days, last_trading_day
    from agents.market_intelligence.scheduler import get_scheduler_status

    today = et_today()
    query_date = last_trading_day(today)
    query_str = query_date.isoformat()
    yesterday = prev_trading_days(1, from_date=query_date)[0]

    regime, ep_alerts, ninem_alerts, sugar_babies, themes, clusters = await _aio.gather(
        get_latest_regime(),
        get_today_ep_alerts(query_str),
        get_today_9m_ep_alerts(query_str),
        get_all_9m_sugar_babies(yesterday),
        get_active_themes(),
        get_correlation_clusters(query_str),
        return_exceptions=True,
    )

    r = regime if isinstance(regime, dict) else {}
    regime_name = r.get("regime", "Unknown")
    qqq_ok = r.get("qqq_ema_bullish")
    qqq_icon = "✅" if qqq_ok else ("❌" if qqq_ok is False else "❓")
    ep_bar = r.get("ep_threshold", "?")
    regime_date = r.get("regime_date")
    data_age = f" · data {regime_date}" if regime_date else ""
    regime_line = f"📈 Regime: *{regime_name}* | QQQ {qqq_icon} | EP bar: {ep_bar}{data_age}"

    if isinstance(ep_alerts, list):
        high_ct = sum(1 for a in ep_alerts if a.get("score_tier") == "HIGH")
        mod_ct  = sum(1 for a in ep_alerts if a.get("score_tier") == "MODERATE")
        ep_line = f"🎯 MAGNA53: *{high_ct} HIGH* · {mod_ct} MODERATE"
    else:
        ep_line = "🎯 MAGNA53: unavailable"

    ninem_today = len(ninem_alerts) if isinstance(ninem_alerts, list) else "?"
    ninem_d2    = len(sugar_babies)  if isinstance(sugar_babies, list)  else "?"
    ninem_line  = f"🏦 9M EP: {ninem_today} intraday · {ninem_d2} Day 2 pending"

    if isinstance(themes, list):
        active_ct = len(themes)
        accel_ct  = sum(1 for t in themes if t.get("stage") == "Accelerating")
        fading_ct = sum(1 for t in themes if t.get("stage") == "Fading")
        theme_line = f"🗂 Themes: {active_ct} active ({accel_ct} accelerating · {fading_ct} fading)"
    else:
        theme_line = "🗂 Themes: unavailable"

    cluster_ct = len(clusters) if isinstance(clusters, list) else "?"
    cluster_line = f"📊 Clusters: {cluster_ct} today"

    sched = get_scheduler_status()
    health_line = "⚙️ System: scheduler running" if sched.get("scheduler_running") else "⚠️ System: scheduler NOT running"

    sep = "━━━━━━━━━━━━━━━━━━━━━"
    now_et = today.strftime("%a %b %-d")
    if query_date != today:
        header = f"📡 *Apollo HUD* — {now_et} · data {query_date.strftime('%a %b %-d')}"
    else:
        header = f"📡 *Apollo HUD* — {now_et}"
    return "\n".join([
        header,
        sep,
        regime_line,
        sep,
        ep_line,
        ninem_line,
        theme_line,
        cluster_line,
        sep,
        health_line,
    ])


# FastAPI app entry point
_agent = MarketIntelligenceAgent()
app = _agent.app


def _bootstrap_alpaca_credentials() -> tuple[str, bool]:
    """Resolve Alpaca credentials at boot for dual-account architecture (#66).

    Runs BEFORE any alpaca_client import so downstream modules consume only
    the new ALPACA_PAPER_*/ALPACA_LIVE_* env var names. Returns
    (status, fallback_used) where status ∈ {'dual_ready', 'paper_only',
    'fallback_paper'} and fallback_used flags whether the deprecated
    ALPACA_API_KEY/SECRET path was used.

    Three modes:
      ENABLE_LIVE_MODE=true (production default):
        - Hard-require ALPACA_PAPER_API_KEY/SECRET AND ALPACA_LIVE_API_KEY/SECRET.
        - Boot-blocks if either pair is missing.
      ENABLE_LIVE_MODE=false (dev / single-account):
        - Only ALPACA_PAPER_* required.
        - If ALPACA_PAPER_* missing AND legacy ALPACA_API_KEY/SECRET present,
          remap legacy to paper. Warning + audit event emitted post-init.
    """
    import os as _os
    from agents.market_intelligence.constants import ENABLE_LIVE_MODE as _ENABLE_LIVE

    fallback_used = False
    if _ENABLE_LIVE:
        for var in ("ALPACA_PAPER_API_KEY", "ALPACA_PAPER_SECRET_KEY",
                    "ALPACA_LIVE_API_KEY", "ALPACA_LIVE_SECRET_KEY"):
            if var not in _os.environ:
                raise RuntimeError(
                    f"Boot Blocked: ENABLE_LIVE_MODE=true requires {var}. "
                    f"Set ALPACA_PAPER_* and ALPACA_LIVE_* env var pairs, OR "
                    f"set ENABLE_LIVE_MODE=false to opt into single-account "
                    f"dev mode (paper-only)."
                )
        return "dual_ready", False

    # Dev / rollback path: paper-only required
    if "ALPACA_PAPER_API_KEY" not in _os.environ:
        if "ALPACA_API_KEY" in _os.environ:
            # Legacy fallback: map deprecated ALPACA_API_KEY → ALPACA_PAPER_*.
            # Boot-only remap; rest of codebase consumes new names.
            _os.environ["ALPACA_PAPER_API_KEY"] = _os.environ["ALPACA_API_KEY"]
            _os.environ["ALPACA_PAPER_SECRET_KEY"] = _os.environ.get(
                "ALPACA_SECRET_KEY", ""
            )
            fallback_used = True
        else:
            raise RuntimeError(
                "Boot Blocked: ENABLE_LIVE_MODE=false requires ALPACA_PAPER_API_KEY "
                "(or legacy ALPACA_API_KEY for one-cycle rollback fallback)."
            )
    return ("fallback_paper" if fallback_used else "paper_only"), fallback_used


@app.on_event("startup")
async def startup():
    import os
    from logging.handlers import RotatingFileHandler

    # Resolve Alpaca credentials BEFORE any alpaca_client import.
    # Raises RuntimeError on missing/misconfigured env vars (boot-blocks the
    # container start, surfaces in docker logs immediately).
    _alpaca_creds_status, _alpaca_creds_fallback = _bootstrap_alpaca_credentials()

    _fmt = logging.Formatter(
        "%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    if _alpaca_creds_fallback:
        logging.getLogger(__name__).warning(
            "LEGACY_CREDS_FALLBACK: deprecated ALPACA_API_KEY/SECRET_KEY remapped "
            "to ALPACA_PAPER_*. Migrate to ALPACA_PAPER_API_KEY/SECRET_KEY env "
            "vars within one deploy cycle (see docs/setups/safeguards.md)."
        )
    else:
        logging.getLogger(__name__).info(
            f"Alpaca credentials resolved: status={_alpaca_creds_status}"
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
    # Audit-log Alpaca credential resolution outcome (post-DB-init so
    # log_audit_event has a pool to write to).
    try:
        from agents.market_intelligence.db import log_audit_event
        await log_audit_event(
            event_type="dual_account_creds_resolved",
            summary=f"Alpaca creds status={_alpaca_creds_status}",
            detail=(
                "Legacy ALPACA_API_KEY/SECRET fallback used — migrate to "
                "ALPACA_PAPER_API_KEY/SECRET_KEY within one deploy cycle"
                if _alpaca_creds_fallback
                else f"Mode resolution: {_alpaca_creds_status}"
            ),
        )
        if _alpaca_creds_fallback:
            await log_audit_event(
                event_type="legacy_alpaca_creds_fallback",
                summary="ALPACA_API_KEY remapped to ALPACA_PAPER_*",
                detail="One-deploy-cycle rollback safety net — remove after dual-mode is verified stable",
            )
    except Exception as e:
        logger.warning(f"Failed to audit-log alpaca creds status: {e}")
    # Boot smoke test: instantiate per-mode TradingClients, verify each can
    # talk to its Alpaca account. Surfaces credential rot or live-account
    # not-yet-funded scenarios at boot, not on first trade.
    try:
        from agents.market_intelligence.broker.alpaca_client import verify_dual_account_clients
        from agents.market_intelligence.db import log_audit_event
        verify_result = await verify_dual_account_clients()
        ok_modes = [m for m, r in verify_result.items() if r.get("ok")]
        bad_modes = [m for m, r in verify_result.items() if not r.get("ok")]
        if bad_modes:
            await log_audit_event(
                event_type="dual_account_boot_failed",
                summary=f"Alpaca client init failed for modes: {bad_modes}",
                detail=str(verify_result),
            )
            logger.error(f"DUAL_ACCOUNT_BOOT_FAILED: {verify_result}")
        else:
            equities = {m: r.get("equity") for m, r in verify_result.items()}
            await log_audit_event(
                event_type="dual_account_boot_verified",
                summary=f"Alpaca clients verified for modes={ok_modes}",
                detail=f"Equities by mode: {equities}",
            )
            logger.info(f"Dual-account boot verified: {equities}")
    except Exception as e:
        logger.warning(f"Failed to verify dual-account clients at boot: {e}")

    # Strategy / mode consistency check — prevents the 2026-05-13 incident
    # where magna53 + 9m_day2 seeded as phase='live' (legacy default) but
    # ENABLE_LIVE_MODE=false meant ALPACA_LIVE_API_KEY was never set →
    # KeyError on every entry attempt. Hard-block boot if any enabled
    # strategy's phase requires a TradingClient whose credentials are
    # missing. Auto-downgrade is tempting but silent — fail loud instead.
    try:
        from agents.market_intelligence.constants import ENABLE_LIVE_MODE as _ENABLE_LIVE
        from agents.market_intelligence.db import get_pool
        pool = await get_pool()
        async with pool.acquire() as conn:
            mismatched = await conn.fetch("""
                SELECT strategy_id, phase, live_real_enabled
                FROM mi_strategies
                WHERE enabled = TRUE AND phase = 'live'
            """)
        if mismatched and not _ENABLE_LIVE:
            ids = ", ".join(r["strategy_id"] for r in mismatched)
            msg = (
                f"BOOT BLOCKED: strategies at phase='live' with ENABLE_LIVE_MODE=false: "
                f"[{ids}]. The dual-account architecture routes phase='live' through "
                f"the LIVE Alpaca client, but ALPACA_LIVE_API_KEY is not set under "
                f"ENABLE_LIVE_MODE=false. Fix: either set ENABLE_LIVE_MODE=true + "
                f"provide ALPACA_LIVE_API_KEY/SECRET_KEY, OR downgrade these "
                f"strategies via: UPDATE mi_strategies SET phase='paper' "
                f"WHERE strategy_id IN ({ids})"
            )
            await log_audit_event(
                event_type="strategy_phase_mode_mismatch",
                summary=msg[:200],
                detail=msg,
            )
            logger.error(msg)
            raise RuntimeError(msg)
    except RuntimeError:
        raise
    except Exception as e:
        logger.warning(f"Strategy phase consistency check failed (non-fatal): {e}")

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
