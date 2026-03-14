"""
Market Intelligence Agent — FastAPI service on port 8006.

Handles:
- On-demand queries: "any EPs today?", "what's the market regime?", "top RS stocks?"
- POST /briefing/trigger — manually send morning briefing
- POST /data/refresh — manually run nightly data pull
- Scheduled jobs: nightly RS/regime, pre-market EP scan, morning briefing
"""
from __future__ import annotations

import logging
import os
from datetime import date
from typing import Any

import anthropic
from fastapi import BackgroundTasks, Depends

from agents.base import BaseAgent, verify_internal_secret
from agents.market_intelligence.db import (
    initialize_schema,
    get_today_ep_alerts,
    get_rs_leaders,
    get_latest_regime,
)
from agents.market_intelligence.briefing import send_morning_briefing
from agents.market_intelligence.ep_detector import run_ep_scan
from agents.market_intelligence.rs_engine import run_rs_engine
from agents.market_intelligence.regime import run_regime_engine, get_current_regime
from agents.market_intelligence.scheduler import start_scheduler, stop_scheduler
from shared.models import AgentName, AgentRequest, AgentResponse

logger = logging.getLogger(__name__)

MARKET_AGENT_MODEL = "claude-haiku-4-5-20251001"


class MarketIntelligenceAgent(BaseAgent):
    def __init__(self) -> None:
        super().__init__(AgentName.MARKET_INTELLIGENCE)
        self._claude = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))
        self._register_extra_routes()

    def _register_extra_routes(self) -> None:
        """Register additional endpoints beyond the base /task and /health."""

        @self.app.post("/briefing/trigger")
        async def trigger_briefing(
            background: BackgroundTasks,
            _: str = Depends(verify_internal_secret),
        ):
            background.add_task(send_morning_briefing)
            return {"status": "briefing queued"}

        @self.app.post("/data/refresh")
        async def refresh_data(
            background: BackgroundTasks,
            _: str = Depends(verify_internal_secret),
        ):
            async def _refresh():
                await run_regime_engine()
                await run_rs_engine()
            background.add_task(_refresh)
            return {"status": "data refresh queued"}

        @self.app.post("/ep/scan")
        async def manual_ep_scan(_: str = Depends(verify_internal_secret)):
            results = await run_ep_scan()
            return {"ep_count": len(results), "results": results}

    async def execute_task(self, request: AgentRequest) -> AgentResponse:
        task = request.task.lower()

        # Route by intent
        if any(k in task for k in ["ep", "episodic", "gap", "pivot", "gapper"]):
            return await self._handle_ep_query(request)

        if any(k in task for k in ["regime", "market condition", "spy", "breadth", "vix", "risk"]):
            return await self._handle_regime_query(request)

        if any(k in task for k in ["rs", "relative strength", "leader", "momentum", "top stock"]):
            return await self._handle_rs_query(request)

        if any(k in task for k in ["brief", "morning", "summary", "overview"]):
            return await self._handle_briefing_query(request)

        if any(k in task for k in ["theme", "sector", "industry"]):
            return await self._handle_theme_query(request)

        # General: let Claude decide what data to pull
        return await self._handle_general(request)

    async def _handle_ep_query(self, request: AgentRequest) -> AgentResponse:
        today_str = date.today().strftime("%Y-%m-%d")
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
        today_str = date.today().strftime("%Y-%m-%d")
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
                tickers = ", ".join(f"{s['ticker']} ({s.get('rs_composite', 0):.0f})" for s in top)
                lines.append(f"*{sector}*: {tickers}")
        else:
            for s in no_sector[:15]:
                lines.append(f"#{s.get('rs_rank')} {s['ticker']} — RS {s.get('rs_composite', 0):.0f}")

        return self._ok(request, result="\n".join(lines), data={"leaders": leaders})

    async def _handle_briefing_query(self, request: AgentRequest) -> AgentResponse:
        briefing_text = await send_morning_briefing()
        return self._ok(request, result=briefing_text)

    async def _handle_theme_query(self, request: AgentRequest) -> AgentResponse:
        return self._ok(
            request,
            result=(
                "Theme clustering engine is in Phase 2 (not yet built).\n\n"
                "For now, check RS leaders by sector above — sector groupings are a "
                "proxy for theme strength. Strong sectors with multiple RS leaders = "
                "an active theme.\n\n"
                "Theme engine (Marios Stamatoudis methodology) is next milestone."
            ),
        )

    async def _handle_general(self, request: AgentRequest) -> AgentResponse:
        today_str = date.today().strftime("%Y-%m-%d")
        regime = await get_current_regime()
        ep_alerts = await get_today_ep_alerts(today_str)
        rs_leaders = await get_rs_leaders(today_str, limit=10)

        context = (
            f"Market regime: {regime.get('regime')} (EP bar: {regime.get('ep_threshold')})\n"
            f"EP alerts today: {len(ep_alerts)}\n"
            f"Top RS stocks: {', '.join(s['ticker'] for s in rs_leaders[:5])}\n"
        )

        response = self._claude.messages.create(
            model=MARKET_AGENT_MODEL,
            max_tokens=1024,
            system=(
                "You are a market intelligence assistant specializing in momentum/EP trading. "
                "Answer concisely. Format for Telegram Markdown. "
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
    await initialize_schema()
    start_scheduler()
    logger.info("Market Intelligence Agent ready on port 8006")


@app.on_event("shutdown")
async def shutdown():
    stop_scheduler()
