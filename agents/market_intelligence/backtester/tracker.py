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

from agents.market_intelligence.backtester.filters import check_filters, compute_atr_14
from agents.market_intelligence.backtester.intraday import ensure_intraday_table, get_intraday_bars
from agents.market_intelligence.backtester.models import BacktestTrade, TradeEntry, TradeExit
from agents.market_intelligence.backtester.engine import _simulate_day1, _bar_date
from agents.market_intelligence.collector import et_today, get_index_history
from agents.market_intelligence.db import get_pool

from agents.market_intelligence.constants import ACCOUNT_SIZE, RISK_PCT, MAX_POSITION_PCT

logger = logging.getLogger(__name__)


def _position_size(
    entry_price: float,
    stop_price: float,
    regime: dict | None = None,
) -> float:
    """
    Risk-based position sizing: target 1% account risk per trade.
    Halve risk when QQQ 10 EMA < 20 EMA (soft regime gate).
    """
    risk_per_share = entry_price - stop_price
    if risk_per_share <= 0:
        return 5_000  # fallback
    base_risk = ACCOUNT_SIZE * RISK_PCT
    if regime and regime.get("qqq_ema_bullish") is False:
        base_risk *= 0.5  # half risk in weak regime
    shares = base_risk / risk_per_share
    position = shares * entry_price
    max_position = ACCOUNT_SIZE * MAX_POSITION_PCT
    return min(position, max_position)


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
                orb_high FLOAT,
                orb_low FLOAT,
                atr_14 FLOAT,
                day1_low FLOAT,
                partial_taken BOOLEAN NOT NULL DEFAULT FALSE,
                breakeven_active BOOLEAN NOT NULL DEFAULT FALSE,
                running_closes JSONB NOT NULL DEFAULT '[]',
                created_at TIMESTAMPTZ DEFAULT NOW(),
                closed_at TIMESTAMPTZ,
                UNIQUE (ticker, alert_date)
            );
            CREATE INDEX IF NOT EXISTS idx_paper_trades_status
                ON mi_paper_trades(status);
        """)
        # Add columns if table already exists (idempotent)
        for col, typ, default in [
            ("orb_high", "FLOAT", None),
            ("orb_low", "FLOAT", None),
            ("atr_14", "FLOAT", None),
            ("day1_low", "FLOAT", None),
            ("partial_taken", "BOOLEAN", "FALSE"),
            ("breakeven_active", "BOOLEAN", "FALSE"),
            ("running_closes", "JSONB", "'[]'"),
        ]:
            default_clause = f"DEFAULT {default}" if default else ""
            await conn.execute(f"""
                ALTER TABLE mi_paper_trades ADD COLUMN IF NOT EXISTS
                    {col} {typ} {default_clause}
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


async def _get_regime_record(d: date) -> dict | None:
    """Get full market regime record for a date."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM mi_market_regime WHERE regime_date <= $1 ORDER BY regime_date DESC LIMIT 1",
            d,
        )
    return dict(row) if row else None


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
                 last_entry_price, total_pnl, hold_days, skip_reason,
                 orb_high, orb_low, atr_14, day1_low,
                 partial_taken, breakeven_active, running_closes)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8::jsonb,$9::jsonb,$10,$11,$12,$13,$14,$15,
                    $16,$17,$18,$19,$20,$21,$22::jsonb)
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
            trade.get("orb_high"),
            trade.get("orb_low"),
            trade.get("atr_14"),
            trade.get("day1_low"),
            trade.get("partial_taken", False),
            trade.get("breakeven_active", False),
            json.dumps(trade.get("running_closes", [])),
        )


async def _update_paper_trade_extras(
    trade_id: int, partial_taken: bool, breakeven_active: bool, running_closes: list[float],
) -> None:
    """Update the new v2 columns on a paper trade."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            UPDATE mi_paper_trades SET
                partial_taken = $2,
                breakeven_active = $3,
                running_closes = $4::jsonb
            WHERE id = $1
        """, trade_id, partial_taken, breakeven_active, json.dumps(running_closes))


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
    Simulate Day 1 trades for today's EP alerts (ORB entry + ATR validation).
    Returns list of trade summaries for reporting.
    """
    alerts = await _get_todays_alerts(today)
    if not alerts:
        logger.info("No HIGH EP alerts today")
        return []

    await ensure_intraday_table()
    regime_record = await _get_regime_record(today)
    regime = regime_record.get("regime") if regime_record else None
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

        # Compute ATR for stop width validation
        atr_14, _atr_pct = await compute_atr_14(ticker, today)

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
                "atr_14": atr_14,
            })
            logger.warning(f"No intraday data for {ticker} on {today}")
            results.append({"ticker": ticker, "action": "skipped", "reason": "no_intraday_data"})
            continue

        # Risk-based position sizing: use ORB high/low for entry/stop
        orb_high = bars[0]["high"]
        orb_low = bars[0]["low"]
        pos_size = _position_size(orb_high, orb_low, regime_record)

        trade = _simulate_day1(ticker, bars, pos_size, atr_14=atr_14)
        if trade is None:
            await _insert_paper_trade({
                "ticker": ticker, "alert_date": today,
                "ep_score": alert["ep_score"],
                "catalyst_quality": alert.get("catalyst_quality"),
                "gap_pct": alert.get("gap_pct"),
                "regime": regime,
                "status": "skipped", "skip_reason": "No valid entry",
                "atr_14": atr_14,
            })
            results.append({"ticker": ticker, "action": "skipped", "reason": "No valid entry"})
            continue

        # Day 1 sim may return a skipped trade (No ORB breakout, Stop too wide)
        if trade.skipped:
            await _insert_paper_trade({
                "ticker": ticker, "alert_date": today,
                "ep_score": alert["ep_score"],
                "catalyst_quality": alert.get("catalyst_quality"),
                "gap_pct": alert.get("gap_pct"),
                "regime": regime,
                "status": "skipped", "skip_reason": trade.skip_reason,
                "orb_high": trade.orb_high, "orb_low": trade.orb_low,
                "atr_14": atr_14,
            })
            logger.info(f"Skipped {ticker}: {trade.skip_reason}")
            results.append({"ticker": ticker, "action": "skipped", "reason": trade.skip_reason})
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
             "reason": e.exit_reason, "shares": e.shares_exited, "pnl": e.pnl,
             "attempt": e.attempt_number}
            for e in trade.exits
        ]

        status = "open" if remaining > 0 else "closed"
        stop = day1_low if day1_low else (last_entry.stop_price if last_entry else None)
        entry_price = last_entry.entry_price if last_entry else None

        # Fetch pre-alert closes for SMA warm-up (stored for Day 2+ updates)
        pre_closes: list[float] = []
        try:
            from_str = (today - timedelta(days=35)).strftime("%Y-%m-%d")
            to_str = today.strftime("%Y-%m-%d")
            daily_bars = await get_index_history(ticker, from_str, to_str)
            pre_closes = [
                float(b.get("c", b.get("close", 0)))
                for b in daily_bars
                if _bar_date(b) <= today and b.get("c", b.get("close", 0))
            ]
        except Exception as e:
            logger.debug(f"Failed to fetch pre-alert closes for {ticker}: {e}")

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
            "orb_high": trade.orb_high,
            "orb_low": trade.orb_low,
            "atr_14": atr_14,
            "day1_low": day1_low,
            "running_closes": pre_closes,
        })

        action = "opened" if remaining > 0 else "closed_day1"
        pnl = sum(e.pnl for e in trade.exits)
        logger.info(f"Paper trade {action}: {ticker} score={alert['ep_score']:.0f} P&L=${pnl:+,.2f}")
        results.append({
            "ticker": ticker, "action": action,
            "ep_score": alert["ep_score"], "pnl": pnl,
            "remaining_shares": remaining, "stop": stop,
            "entry_price": entry_price,
            "orb_high": trade.orb_high,
            "orb_low": trade.orb_low,
            "gap_pct": alert.get("gap_pct"),
            "exits": exits_json,
            "entries": entries_json,
        })

    return results


async def update_open_positions(today: date) -> list[dict]:
    """
    Update open positions: 10/20 SMA trail + Day 3-5 partial profit.
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
        entry_price = pt["last_entry_price"]
        hard_stop = pt.get("day1_low") or pt["stop_price"]
        partial_taken = pt.get("partial_taken", False)
        breakeven_active = pt.get("breakeven_active", False)
        exits = pt["exits"] if isinstance(pt["exits"], list) else json.loads(pt["exits"] or "[]")
        running_closes = pt.get("running_closes", [])
        if isinstance(running_closes, str):
            running_closes = json.loads(running_closes or "[]")

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

        # Append today's close to running list
        running_closes.append(float(bar_close))

        # 1. Hard stop check (intraday low breaches hard stop)
        if hard_stop and bar_low <= hard_stop:
            pnl = (hard_stop - entry_price) * remaining if entry_price else 0
            exits.append({
                "time": datetime.combine(today, time(16, 0)).isoformat(),
                "price": hard_stop,
                "reason": "stop_hit",
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
            logger.info(f"Hard stop hit: {ticker} @${hard_stop:.2f} P&L=${pnl:+,.2f}")
            results.append({
                "ticker": ticker, "action": "stopped_out",
                "stop_price": hard_stop, "pnl": pnl,
                "total_pnl": total_pnl, "hold_days": hold_days,
            })
            continue

        # 2. Compute SMAs
        active_sma = None
        if len(running_closes) >= 20:
            sma_10 = sum(running_closes[-10:]) / 10
            sma_20 = sum(running_closes[-20:]) / 20
            active_sma = sma_10 if sma_10 > sma_20 else sma_20
        elif len(running_closes) >= 10:
            active_sma = sum(running_closes[-10:]) / 10

        # 3. Partial profit on Day 3-5
        if hold_days >= 3 and not partial_taken and entry_price:
            take_partial = False
            if hold_days <= 4 and bar_close > entry_price:
                take_partial = True
            elif hold_days >= 5:
                take_partial = True

            if take_partial:
                partial_shares = remaining / 3
                remaining -= partial_shares
                pnl = (bar_close - entry_price) * partial_shares
                exits.append({
                    "time": datetime.combine(today, time(16, 0)).isoformat(),
                    "price": bar_close,
                    "reason": "partial_profit",
                    "shares": partial_shares,
                    "pnl": pnl,
                })
                partial_taken = True
                breakeven_active = True
                logger.info(f"Partial profit: {ticker} sold {partial_shares:.1f} shares @${bar_close:.2f} P&L=${pnl:+,.2f}")

        # 4. SMA trail check (close-based)
        effective_stop = hard_stop or 0
        if active_sma and active_sma > effective_stop:
            effective_stop = active_sma
        if breakeven_active and entry_price and entry_price > effective_stop:
            effective_stop = entry_price

        if bar_close < effective_stop:
            pnl = (bar_close - entry_price) * remaining if entry_price else 0
            exits.append({
                "time": datetime.combine(today, time(16, 0)).isoformat(),
                "price": bar_close,
                "reason": "sma_trail_stop",
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
            await _update_paper_trade_extras(pt["id"], partial_taken, breakeven_active, running_closes)
            logger.info(f"SMA trail stop: {ticker} @${bar_close:.2f} P&L=${pnl:+,.2f}")
            results.append({
                "ticker": ticker, "action": "sma_stopped",
                "stop_price": effective_stop, "pnl": pnl,
                "total_pnl": total_pnl, "hold_days": hold_days,
            })
            continue

        # 5. Still open — update state
        total_pnl = sum(e.get("pnl", 0) for e in exits)
        await _update_paper_trade(pt["id"], {
            "status": "open",
            "exits": exits,
            "remaining_shares": remaining,
            "stop_price": effective_stop,
            "total_pnl": total_pnl,
            "hold_days": hold_days,
        })
        await _update_paper_trade_extras(pt["id"], partial_taken, breakeven_active, running_closes)

        logger.debug(f"Updated {ticker}: eff_stop=${effective_stop:.2f}, day {hold_days}, sma={active_sma}")
        results.append({
            "ticker": ticker, "action": "updated",
            "effective_stop": effective_stop,
            "hold_days": hold_days,
            "partial_taken": partial_taken,
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

        recent_trades = await conn.fetch("""
            SELECT ticker, alert_date, ep_score, total_pnl, hold_days,
                   status, last_entry_price, orb_high, orb_low, stop_price,
                   catalyst_quality, gap_pct, exits, entries
            FROM mi_paper_trades
            WHERE status IN ('open', 'closed')
            ORDER BY alert_date DESC LIMIT 5
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
        "recent_trades": [dict(r) for r in recent_trades],
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
    import json as _json
    lines = ["📊 *Paper Trade Tracker (EOD sim)*\n"]

    def _parse_json(raw) -> list:
        if not raw:
            return []
        return raw if isinstance(raw, list) else _json.loads(raw or "[]")

    def _attempt_count(entries_raw) -> int:
        entries = _parse_json(entries_raw)
        if not entries:
            return 0
        return max(e.get("attempt", i + 1) for i, e in enumerate(entries))

    def _entry_lines(entries_raw, prefix="    ") -> list[str]:
        """Format entries JSONB — one line per attempt."""
        entries = _parse_json(entries_raw)
        if not entries:
            return []
        out = []
        for e in entries:
            attempt = e.get("attempt", "?")
            price = e.get("price", e.get("entry_price", 0))
            stop = e.get("stop", e.get("stop_price", 0))
            shares = e.get("shares", "")
            shares_str = f" ×{shares:.0f}" if shares else ""
            out.append(f"{prefix}Entry #{attempt} @${price:.2f}{shares_str} stop=${stop:.2f}")
        return out

    def _exit_lines(exits_raw, prefix="    ") -> list[str]:
        """Format exits JSONB into readable lines."""
        exits = _parse_json(exits_raw)
        out = []
        for ex in exits:
            price = ex.get("price") or ex.get("exit_price", 0)
            reason = ex.get("reason", "")
            pnl = ex.get("pnl", 0)
            shares = ex.get("shares") or ex.get("shares_exited", "")
            attempt = ex.get("attempt", "")
            shares_str = f" ×{shares:.0f}" if shares else ""
            attempt_str = f" (attempt {attempt})" if attempt else ""
            out.append(f"{prefix}Exit @${price:.2f}{shares_str} {reason}{attempt_str} P&L ${pnl:+.0f}")
        return out

    # Today's new trades
    new = summary.get("today_new", [])
    if new:
        lines.append("*New today:*")
        for t in new:
            entry = t.get("entry_price") or t.get("orb_high")
            stop = t.get("stop") or t.get("orb_low")
            gap = t.get("gap_pct")
            gap_str = f" gap={gap:.1f}%" if gap else ""
            score_str = f" score={t['ep_score']:.0f}" if t.get("ep_score") else ""
            if t["action"] == "opened":
                attempts = _attempt_count(t.get("entries"))
                att_str = f" {attempts}x" if attempts > 1 else ""
                lines.append(f"  ▶ {t['ticker']}{gap_str}{score_str}{att_str}")
                lines += _entry_lines(t.get("entries"))
                lines += _exit_lines(t.get("exits"))
            elif t["action"] == "closed_day1":
                attempts = _attempt_count(t.get("entries"))
                att_str = f" {attempts}x attempts" if attempts > 1 else ""
                lines.append(f"  ⏹ {t['ticker']}{gap_str}{score_str}{att_str}")
                lines += _entry_lines(t.get("entries"))
                lines += _exit_lines(t.get("exits"))
                lines.append(f"    *Day 1 P&L: ${t['pnl']:+,.2f}*")
            elif t["action"] in ("filtered", "skipped"):
                lines.append(f"  ⊘ {t['ticker']}{gap_str}{score_str}: {t.get('reason', '')}")
        lines.append("")

    # Position updates (stops hit, SMA trails, partials)
    updates = summary.get("today_updates", [])
    stopped = [u for u in updates if u["action"] in ("stopped_out", "sma_stopped")]
    partials = [u for u in updates if u["action"] == "partial_taken"]
    if stopped:
        lines.append("*Stopped out:*")
        for u in stopped:
            reason = "stop" if u["action"] == "stopped_out" else "SMA trail"
            lines.append(
                f"  ✖ {u['ticker']} @${u['stop_price']:.2f} ({reason}) "
                f"P&L=${u['total_pnl']:+,.2f} ({u['hold_days']}d)"
            )
        lines.append("")
    if partials:
        lines.append("*Partial exits:*")
        for u in partials:
            lines.append(f"  ½ {u['ticker']} @${u.get('price', 0):.2f} P&L=${u.get('pnl', 0):+,.2f}")
        lines.append("")

    # Recent trades — show entry, stop, exits
    recent = summary.get("recent_trades", [])
    if recent:
        lines.append("*Recent trades:*")
        for t in recent:
            status_icon = "📍" if t["status"] == "open" else ("✅" if t.get("total_pnl", 0) > 0 else "❌")
            pnl = t.get("total_pnl", 0)
            hold = t.get("hold_days", 0)
            score = t.get("ep_score", 0)
            gap = t.get("gap_pct")
            attempts = _attempt_count(t.get("entries"))
            gap_str = f" +{gap:.1f}%" if gap else ""
            att_str = f" {attempts}x" if attempts > 1 else ""
            lines.append(
                f"  {status_icon} {t['ticker']}{gap_str} score={score:.0f}{att_str} "
                f"{hold}d P&L=${pnl:+,.2f}"
            )
            lines += _entry_lines(t.get("entries"), prefix="    ")
            lines += _exit_lines(t.get("exits"), prefix="    ")
        lines.append("")

    # Running totals
    lines.append("*Running totals:*")
    lines.append(f"  Trades: {summary['total_trades']} ({summary['open_positions']} open)")
    closed = summary["closed_trades"]
    if closed > 0:
        lines.append(f"  Closed: {closed} ({summary['win_rate']:.0f}% win rate)")
        lines.append(f"  Realized P&L: ${summary['realized_pnl']:+,.2f}")
    if summary.get("skipped"):
        lines.append(f"  Filtered: {summary['skipped']}")

    return "\n".join(lines)
