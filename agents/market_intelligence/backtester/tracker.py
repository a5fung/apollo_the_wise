"""
Live paper trade tracker — runs daily after market close.

Automatically simulates trades on new EP alerts and manages open positions
with trailing stops. Stores all state in mi_paper_trades for ongoing P&L tracking.

Schedule: 4:45 PM ET Mon-Fri (after nightly data pull completes at ~4:30).
"""
from __future__ import annotations

import json
import logging
from datetime import date, datetime, timedelta, time
from typing import Any

from agents.market_intelligence.backtester.filters import check_filters
from agents.market_intelligence.backtester.intraday import ensure_intraday_table, get_intraday_bars
from agents.market_intelligence.backtester.models import BacktestTrade, TradeEntry, TradeExit
from agents.market_intelligence.backtester.engine import _simulate_day1, _simulate_trailing_stop, _bar_date
from agents.market_intelligence.collector import et_today, get_index_history
from agents.market_intelligence.db import get_pool

logger = logging.getLogger(__name__)

POSITION_SIZE = 10_000  # $10K per trade


# ── DB helpers ────────────────────────────────────────────────────────────────


async def ensure_paper_trades_table() -> None:
    """Create the mi_paper_trades table if it doesn't exist."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS mi_paper_trades (
                id SERIAL PRIMARY KEY,
                ticker TEXT NOT NULL,
                alert_date DATE NOT NULL,
                ep_score FLOAT NOT NULL,
                catalyst_quality TEXT,
                gap_pct FLOAT,
                regime TEXT,
                status TEXT NOT NULL DEFAULT 'open',
                entries JSONB NOT NULL DEFAULT '[]',
                exits JSONB NOT NULL DEFAULT '[]',
                remaining_shares FLOAT NOT NULL DEFAULT 0,
                stop_price FLOAT,
                last_entry_price FLOAT,
                total_pnl FLOAT NOT NULL DEFAULT 0,
                hold_days INT NOT NULL DEFAULT 0,
                skip_reason TEXT,
                created_at TIMESTAMPTZ DEFAULT NOW(),
                closed_at TIMESTAMPTZ,
                UNIQUE (ticker, alert_date)
            );
            CREATE INDEX IF NOT EXISTS idx_paper_trades_status
                ON mi_paper_trades(status);
        """)


async def _get_open_trades() -> list[dict]:
    """Get all open paper trades."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT * FROM mi_paper_trades WHERE status = 'open'
            ORDER BY alert_date ASC
        """)
    return [dict(r) for r in rows]


async def _get_todays_alerts(today: date) -> list[dict]:
    """Get today's HIGH EP alerts (deduped by ticker)."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT DISTINCT ON (ticker)
                   ticker, alert_date, gap_pct, rel_volume, ep_score,
                   score_tier, catalyst, catalyst_quality, vol_percentile
            FROM mi_ep_alerts
            WHERE alert_date = $1 AND score_tier = 'HIGH'
            ORDER BY ticker, ep_score DESC
        """, today)
    return [dict(r) for r in rows]


async def _get_regime(d: date) -> str | None:
    """Get market regime for a date."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT regime FROM mi_market_regime WHERE regime_date <= $1 ORDER BY regime_date DESC LIMIT 1",
            d,
        )
    return row["regime"] if row else None


async def _trade_already_exists(ticker: str, alert_date: date) -> bool:
    """Check if we already have a paper trade for this ticker+date."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        exists = await conn.fetchval(
            "SELECT EXISTS(SELECT 1 FROM mi_paper_trades WHERE ticker = $1 AND alert_date = $2)",
            ticker, alert_date,
        )
    return exists


async def _insert_paper_trade(trade: dict) -> None:
    """Insert a new paper trade record."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO mi_paper_trades
                (ticker, alert_date, ep_score, catalyst_quality, gap_pct, regime,
                 status, entries, exits, remaining_shares, stop_price,
                 last_entry_price, total_pnl, hold_days, skip_reason)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8::jsonb,$9::jsonb,$10,$11,$12,$13,$14,$15)
            ON CONFLICT (ticker, alert_date) DO NOTHING
        """,
            trade["ticker"], trade["alert_date"], trade["ep_score"],
            trade.get("catalyst_quality"), trade.get("gap_pct"), trade.get("regime"),
            trade["status"],
            json.dumps(trade.get("entries", [])),
            json.dumps(trade.get("exits", [])),
            trade.get("remaining_shares", 0),
            trade.get("stop_price"),
            trade.get("last_entry_price"),
            trade.get("total_pnl", 0),
            trade.get("hold_days", 0),
            trade.get("skip_reason"),
        )


async def _update_paper_trade(trade_id: int, updates: dict) -> None:
    """Update an existing paper trade."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            UPDATE mi_paper_trades SET
                status = $2,
                exits = $3::jsonb,
                remaining_shares = $4,
                stop_price = $5,
                total_pnl = $6,
                hold_days = $7,
                closed_at = $8
            WHERE id = $1
        """,
            trade_id,
            updates["status"],
            json.dumps(updates["exits"]),
            updates["remaining_shares"],
            updates.get("stop_price"),
            updates["total_pnl"],
            updates["hold_days"],
            updates.get("closed_at"),
        )


# ── Core tracking logic ──────────────────────────────────────────────────────


async def process_new_alerts(today: date) -> list[dict]:
    """
    Simulate Day 1 trades for today's EP alerts.
    Returns list of trade summaries for reporting.
    """
    alerts = await _get_todays_alerts(today)
    if not alerts:
        logger.info("No HIGH EP alerts today")
        return []

    await ensure_intraday_table()
    regime = await _get_regime(today)
    results = []

    for alert in alerts:
        ticker = alert["ticker"]

        if await _trade_already_exists(ticker, today):
            logger.debug(f"Paper trade already exists for {ticker} on {today}")
            continue

        # Apply pre-trade filters
        passed, skip_reason = await check_filters(ticker, today)
        if not passed:
            await _insert_paper_trade({
                "ticker": ticker, "alert_date": today,
                "ep_score": alert["ep_score"],
                "catalyst_quality": alert.get("catalyst_quality"),
                "gap_pct": alert.get("gap_pct"),
                "regime": regime,
                "status": "skipped", "skip_reason": skip_reason,
            })
            logger.info(f"Filtered {ticker}: {skip_reason}")
            results.append({"ticker": ticker, "action": "filtered", "reason": skip_reason})
            continue

        # Fetch intraday bars and simulate Day 1
        bars = await get_intraday_bars(ticker, today)
        if not bars:
            await _insert_paper_trade({
                "ticker": ticker, "alert_date": today,
                "ep_score": alert["ep_score"],
                "catalyst_quality": alert.get("catalyst_quality"),
                "gap_pct": alert.get("gap_pct"),
                "regime": regime,
                "status": "skipped", "skip_reason": "no_intraday_data",
            })
            logger.warning(f"No intraday data for {ticker} on {today}")
            results.append({"ticker": ticker, "action": "skipped", "reason": "no_intraday_data"})
            continue

        trade = _simulate_day1(ticker, bars, POSITION_SIZE)
        if trade is None:
            await _insert_paper_trade({
                "ticker": ticker, "alert_date": today,
                "ep_score": alert["ep_score"],
                "catalyst_quality": alert.get("catalyst_quality"),
                "gap_pct": alert.get("gap_pct"),
                "regime": regime,
                "status": "skipped", "skip_reason": "no_valid_entry",
            })
            results.append({"ticker": ticker, "action": "skipped", "reason": "no_valid_entry"})
            continue

        remaining = getattr(trade, "_remaining_shares", 0.0)
        last_entry = getattr(trade, "_last_entry", None)
        day1_low = getattr(trade, "_day1_low", None)

        entries_json = [
            {"time": e.entry_time.isoformat(), "price": e.entry_price,
             "stop": e.stop_price, "attempt": e.attempt_number, "shares": e.shares}
            for e in trade.entries
        ]
        exits_json = [
            {"time": e.exit_time.isoformat(), "price": e.exit_price,
             "reason": e.exit_reason, "shares": e.shares_exited, "pnl": e.pnl}
            for e in trade.exits
        ]

        status = "open" if remaining > 0 else "closed"
        stop = day1_low if day1_low else (last_entry.stop_price if last_entry else None)
        entry_price = last_entry.entry_price if last_entry else None

        await _insert_paper_trade({
            "ticker": ticker, "alert_date": today,
            "ep_score": alert["ep_score"],
            "catalyst_quality": alert.get("catalyst_quality"),
            "gap_pct": alert.get("gap_pct"),
            "regime": regime,
            "status": status,
            "entries": entries_json,
            "exits": exits_json,
            "remaining_shares": remaining,
            "stop_price": stop,
            "last_entry_price": entry_price,
            "total_pnl": sum(e.pnl for e in trade.exits),
            "hold_days": 0,
        })

        action = "opened" if remaining > 0 else "closed_day1"
        pnl = sum(e.pnl for e in trade.exits)
        logger.info(f"Paper trade {action}: {ticker} score={alert['ep_score']:.0f} P&L=${pnl:+,.2f}")
        results.append({
            "ticker": ticker, "action": action,
            "ep_score": alert["ep_score"], "pnl": pnl,
            "remaining_shares": remaining, "stop": stop,
        })

    return results


async def update_open_positions(today: date) -> list[dict]:
    """
    Update trailing stops for open positions using today's daily bar.
    Returns list of position updates for reporting.
    """
    open_trades = await _get_open_trades()
    if not open_trades:
        return []

    results = []

    for pt in open_trades:
        ticker = pt["ticker"]
        alert_date = pt["alert_date"]
        remaining = pt["remaining_shares"]
        stop_price = pt["stop_price"]
        entry_price = pt["last_entry_price"]
        exits = pt["exits"] if isinstance(pt["exits"], list) else json.loads(pt["exits"] or "[]")

        if remaining <= 0:
            continue

        # Skip Day 1 — intraday simulation already handled it
        if today <= alert_date:
            continue

        # Fetch today's daily bar
        today_str = today.strftime("%Y-%m-%d")
        daily_bars = await get_index_history(ticker, today_str, today_str)

        if not daily_bars:
            logger.debug(f"No daily bar for {ticker} on {today}")
            results.append({"ticker": ticker, "action": "no_data"})
            continue

        bar = daily_bars[0]
        bar_low = bar.get("l", 0)
        bar_close = bar.get("c", 0)
        hold_days = (today - alert_date).days

        if stop_price and bar_low <= stop_price:
            # Stop hit — close remaining position
            pnl = (stop_price - entry_price) * remaining if entry_price else 0
            exits.append({
                "time": datetime.combine(today, time(16, 0)).isoformat(),
                "price": stop_price,
                "reason": "trailing_stop",
                "shares": remaining,
                "pnl": pnl,
            })
            total_pnl = sum(e.get("pnl", 0) for e in exits)

            await _update_paper_trade(pt["id"], {
                "status": "closed",
                "exits": exits,
                "remaining_shares": 0,
                "stop_price": None,
                "total_pnl": total_pnl,
                "hold_days": hold_days,
                "closed_at": datetime.utcnow(),
            })
            logger.info(f"Trailing stop hit: {ticker} @${stop_price:.2f} P&L=${pnl:+,.2f} (total ${total_pnl:+,.2f})")
            results.append({
                "ticker": ticker, "action": "stopped_out",
                "stop_price": stop_price, "pnl": pnl,
                "total_pnl": total_pnl, "hold_days": hold_days,
            })
        else:
            # Ratchet stop up (never lower)
            new_stop = max(stop_price or 0, bar_low)
            await _update_paper_trade(pt["id"], {
                "status": "open",
                "exits": exits,
                "remaining_shares": remaining,
                "stop_price": new_stop,
                "total_pnl": sum(e.get("pnl", 0) for e in exits),
                "hold_days": hold_days,
            })
            logger.debug(f"Updated {ticker}: stop ${stop_price:.2f}→${new_stop:.2f}, day {hold_days}")
            results.append({
                "ticker": ticker, "action": "updated",
                "old_stop": stop_price, "new_stop": new_stop,
                "hold_days": hold_days,
            })

    return results


async def get_paper_trading_summary() -> dict[str, Any]:
    """Get summary of all paper trades for reporting."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        stats = await conn.fetchrow("""
            SELECT
                COUNT(*) FILTER (WHERE status != 'skipped') as total_trades,
                COUNT(*) FILTER (WHERE status = 'open') as open_positions,
                COUNT(*) FILTER (WHERE status = 'closed' AND total_pnl > 0) as winners,
                COUNT(*) FILTER (WHERE status = 'closed' AND total_pnl <= 0) as losers,
                COALESCE(SUM(total_pnl) FILTER (WHERE status = 'closed'), 0) as realized_pnl,
                COUNT(*) FILTER (WHERE status = 'skipped') as skipped
            FROM mi_paper_trades
        """)

        open_positions = await conn.fetch("""
            SELECT ticker, alert_date, ep_score, remaining_shares,
                   stop_price, last_entry_price, total_pnl, hold_days
            FROM mi_paper_trades WHERE status = 'open'
            ORDER BY alert_date ASC
        """)

        recent_closed = await conn.fetch("""
            SELECT ticker, alert_date, ep_score, total_pnl, hold_days,
                   catalyst_quality, gap_pct
            FROM mi_paper_trades WHERE status = 'closed'
            ORDER BY closed_at DESC LIMIT 10
        """)

    total = stats["total_trades"] or 0
    closed = (stats["winners"] or 0) + (stats["losers"] or 0)
    win_rate = (stats["winners"] / closed * 100) if closed > 0 else 0

    return {
        "total_trades": total,
        "open_positions": stats["open_positions"] or 0,
        "closed_trades": closed,
        "winners": stats["winners"] or 0,
        "losers": stats["losers"] or 0,
        "win_rate": win_rate,
        "realized_pnl": float(stats["realized_pnl"] or 0),
        "skipped": stats["skipped"] or 0,
        "open_details": [dict(r) for r in open_positions],
        "recent_closed": [dict(r) for r in recent_closed],
    }


# ── Main entry point (called by scheduler) ───────────────────────────────────


async def run_paper_trade_tracker() -> dict[str, Any]:
    """
    Daily paper trade tracking job.
    1. Create table if needed
    2. Simulate Day 1 for today's new EP alerts
    3. Update trailing stops on open positions
    4. Return summary for Telegram notification
    """
    today = et_today()
    logger.info(f"Paper trade tracker running for {today}")

    await ensure_paper_trades_table()

    # Process new alerts from today
    new_results = await process_new_alerts(today)

    # Update open positions
    position_results = await update_open_positions(today)

    # Build summary
    summary = await get_paper_trading_summary()
    summary["today_new"] = new_results
    summary["today_updates"] = position_results

    return summary


def format_tracker_telegram(summary: dict) -> str:
    """Format paper trade summary for Telegram notification."""
    lines = ["📊 *Paper Trade Tracker*\n"]

    # Today's new trades
    new = summary.get("today_new", [])
    if new:
        lines.append("*New today:*")
        for t in new:
            if t["action"] == "opened":
                lines.append(
                    f"  ▶ {t['ticker']} opened (score={t['ep_score']:.0f}) "
                    f"stop=${t['stop']:.2f}"
                )
            elif t["action"] == "closed_day1":
                lines.append(
                    f"  ⏹ {t['ticker']} closed Day 1 P&L=${t['pnl']:+,.2f}"
                )
            elif t["action"] == "filtered":
                lines.append(f"  ⊘ {t['ticker']} filtered: {t['reason']}")
            elif t["action"] == "skipped":
                lines.append(f"  ⊘ {t['ticker']} skipped: {t['reason']}")
        lines.append("")

    # Position updates
    updates = summary.get("today_updates", [])
    stopped = [u for u in updates if u["action"] == "stopped_out"]
    if stopped:
        lines.append("*Stopped out:*")
        for u in stopped:
            lines.append(
                f"  ✖ {u['ticker']} @${u['stop_price']:.2f} "
                f"P&L=${u['total_pnl']:+,.2f} ({u['hold_days']}d)"
            )
        lines.append("")

    # Open positions
    open_details = summary.get("open_details", [])
    if open_details:
        lines.append("*Open positions:*")
        for p in open_details:
            lines.append(
                f"  📍 {p['ticker']} entry=${p['last_entry_price']:.2f} "
                f"stop=${p['stop_price']:.2f} day {p['hold_days']}"
            )
        lines.append("")

    # Running totals
    lines.append("*Running totals:*")
    lines.append(f"  Trades: {summary['total_trades']} ({summary['open_positions']} open)")
    closed = summary["closed_trades"]
    if closed > 0:
        lines.append(
            f"  Closed: {closed} "
            f"({summary['win_rate']:.0f}% win rate)"
        )
        lines.append(f"  Realized P&L: ${summary['realized_pnl']:+,.2f}")
    if summary.get("skipped"):
        lines.append(f"  Filtered: {summary['skipped']}")

    return "\n".join(lines)
