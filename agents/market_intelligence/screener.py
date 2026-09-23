"""
Composite stock screener — RS leadership + theme context + O'Neil fundamentals.

Scoring formula:
  composite = rs_composite + theme_bonus + eps_bonus + accel_bonus

Theme bonus: Accelerating +15, Nascent +8, Mainstream +5, Fading 0
EPS bonus:   ≥50% YoY +10, ≥25% +5, ≥0% +2, negative 0
Accel bonus: EPS accelerating (latest > prior YoY rate) +5
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import date
from typing import Optional

from agents.market_intelligence.collector import et_today
from agents.market_intelligence.db import get_rs_leaders
from agents.market_intelligence.fundamentals import get_fundamentals_batch
from agents.market_intelligence.theme_engine import get_today_themes

logger = logging.getLogger(__name__)

_THEME_BONUS: dict[str, float] = {
    "Accelerating": 15.0,
    "Nascent": 8.0,
    "Mainstream": 5.0,
    "Fading": 0.0,
}

# Max RS leaders to run fundamentals on (limits yfinance calls)
_CANDIDATE_CAP = 50


@dataclass
class ScreenerFilters:
    min_rs: float = 60.0
    min_eps_yoy_pct: Optional[float] = None
    min_rev_yoy_pct: Optional[float] = None
    require_acceleration: bool = False
    require_sales_confirms: bool = False
    theme_stage: Optional[str] = None   # e.g. "Accelerating" — only stocks in that stage
    max_results: int = 20


@dataclass
class ScreenerResult:
    ticker: str
    rs_composite: float
    rs_rank: int
    sector: Optional[str]
    composite_score: float
    theme_name: Optional[str]
    theme_stage: Optional[str]
    theme_bonus: float
    latest_eps_yoy: Optional[float]
    latest_rev_yoy: Optional[float]
    eps_accelerating: Optional[bool]
    eps_streak_25pct: int
    eps_bonus: float
    accel_bonus: float
    next_earnings_date: Optional[str]
    gross_margin_pct: Optional[float]


async def run_screener(filters: ScreenerFilters) -> list[ScreenerResult]:
    """
    Run the composite screener and return results sorted by composite score.
    """
    today_str = et_today().strftime("%Y-%m-%d")

    # Broad RS universe — filter by min_rs before fetching fundamentals
    leaders = await get_rs_leaders(today_str, limit=200)
    if not leaders:
        return []

    leaders = [s for s in leaders if (s.get("rs_composite") or 0) >= filters.min_rs]

    # Build theme map: ticker → (name, stage) keeping the highest-bonus stage
    themes = await get_today_themes(today_str)
    theme_by_ticker: dict[str, tuple[str, str]] = {}
    for t in themes:
        stage = t.get("stage", "")
        name = t.get("name", "")
        bonus = _THEME_BONUS.get(stage, 0.0)
        for ticker in (t.get("tickers") or []):
            if ticker not in theme_by_ticker:
                theme_by_ticker[ticker] = (name, stage)
            else:
                existing_bonus = _THEME_BONUS.get(theme_by_ticker[ticker][1], 0.0)
                if bonus > existing_bonus:
                    theme_by_ticker[ticker] = (name, stage)

    # Optional theme_stage filter
    if filters.theme_stage:
        leaders = [
            s for s in leaders
            if theme_by_ticker.get(s["ticker"], (None, None))[1] == filters.theme_stage
        ]

    candidates = leaders[:_CANDIDATE_CAP]
    if not candidates:
        return []

    # Batch fetch fundamentals
    tickers = [s["ticker"] for s in candidates]
    fund_map = await get_fundamentals_batch(tickers)

    results: list[ScreenerResult] = []

    for stock in candidates:
        ticker = stock["ticker"]
        rs = float(stock.get("rs_composite") or 0)
        rank = int(stock.get("rs_rank") or 0)
        sector = stock.get("sector")

        fund = fund_map.get(ticker, {})
        flags = fund.get("quality_flags", {})
        q_eps = fund.get("quarterly_eps", [])
        q_rev = fund.get("quarterly_revenue", [])

        eps_yoy_list = [q["yoy_pct"] for q in q_eps if q.get("yoy_pct") is not None]
        rev_yoy_list = [q["yoy_pct"] for q in q_rev if q.get("yoy_pct") is not None]
        latest_eps_yoy = eps_yoy_list[-1] if eps_yoy_list else None
        latest_rev_yoy = rev_yoy_list[-1] if rev_yoy_list else None
        eps_accelerating = flags.get("eps_accelerating")
        sales_confirms = flags.get("sales_confirms")

        # Apply hard filters
        if filters.min_eps_yoy_pct is not None:
            if latest_eps_yoy is None or latest_eps_yoy < filters.min_eps_yoy_pct:
                continue
        if filters.min_rev_yoy_pct is not None:
            if latest_rev_yoy is None or latest_rev_yoy < filters.min_rev_yoy_pct:
                continue
        if filters.require_acceleration and eps_accelerating is not True:
            continue
        if filters.require_sales_confirms and sales_confirms is not True:
            continue

        # Bonuses
        theme_info = theme_by_ticker.get(ticker)
        t_name = theme_info[0] if theme_info else None
        t_stage = theme_info[1] if theme_info else None
        t_bonus = _THEME_BONUS.get(t_stage, 0.0) if t_stage else 0.0

        if latest_eps_yoy is not None:
            if latest_eps_yoy >= 50:
                eps_bonus = 10.0
            elif latest_eps_yoy >= 25:
                eps_bonus = 5.0
            elif latest_eps_yoy >= 0:
                eps_bonus = 2.0
            else:
                eps_bonus = 0.0
        else:
            eps_bonus = 0.0

        accel_bonus = 5.0 if eps_accelerating is True else 0.0
        composite = rs + t_bonus + eps_bonus + accel_bonus

        results.append(ScreenerResult(
            ticker=ticker,
            rs_composite=rs,
            rs_rank=rank,
            sector=sector,
            composite_score=composite,
            theme_name=t_name,
            theme_stage=t_stage,
            theme_bonus=t_bonus,
            latest_eps_yoy=latest_eps_yoy,
            latest_rev_yoy=latest_rev_yoy,
            eps_accelerating=eps_accelerating,
            eps_streak_25pct=int(flags.get("eps_streak_25pct") or 0),
            eps_bonus=eps_bonus,
            accel_bonus=accel_bonus,
            next_earnings_date=fund.get("next_earnings_date"),
            gross_margin_pct=fund.get("gross_margin_pct"),
        ))

    results.sort(key=lambda r: r.composite_score, reverse=True)
    return results[:filters.max_results]


def format_screener_results(results: list[ScreenerResult], filters: ScreenerFilters) -> str:
    """
    Format screener results as a Telegram-ready monospace table.

    Uses a code block so Telegram renders fixed-width columns cleanly.
    Columns: rank, ticker, RS, EPS YoY%, Rev YoY%, accel flag.
    """
    if not results:
        return "No stocks matched the screener criteria."

    filter_parts = [f"RS ≥ {filters.min_rs:.0f}"]
    if filters.min_eps_yoy_pct is not None:
        filter_parts.append(f"EPS YoY ≥ {filters.min_eps_yoy_pct:.0f}%")
    if filters.min_rev_yoy_pct is not None:
        filter_parts.append(f"Rev YoY ≥ {filters.min_rev_yoy_pct:.0f}%")
    if filters.require_acceleration:
        filter_parts.append("accel")
    if filters.require_sales_confirms:
        filter_parts.append("sales confirms")
    if filters.theme_stage:
        filter_parts.append(f"{filters.theme_stage} themes")

    header = f"*Screener — {', '.join(filter_parts)}*  _{len(results)} results_"

    # Fixed-width columns for monospace block
    # Ticker(6) RS(4) EPS%(7) Rev%(6) Flag(2)
    def _eps(v: float | None) -> str:
        if v is None:
            return "   n/a"
        s = f"{v:+.0f}%"
        return s.rjust(6)

    def _rev(v: float | None) -> str:
        if v is None:
            return "  n/a"
        s = f"{v:+.0f}%"
        return s.rjust(5)

    col_header = f"{'Ticker':<6}  {'RS':>3}  {'EPS%':>6}  {'Rev%':>5}"
    divider    = "-" * len(col_header)

    rows = [col_header, divider]
    for r in results:
        flag = "⚡" if r.eps_accelerating else "  "
        rows.append(
            f"{r.ticker:<6}  {r.rs_composite:>3.0f}  {_eps(r.latest_eps_yoy)}  {_rev(r.latest_rev_yoy)} {flag}"
        )

    table = "```\n" + "\n".join(rows) + "\n```"
    return f"{header}\n{table}"
