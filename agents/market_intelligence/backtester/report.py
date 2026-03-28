"""Backtest reporting — summary stats, breakdowns, equity curve."""
from __future__ import annotations

import csv
import io
from collections import defaultdict
from typing import Any

from agents.market_intelligence.backtester.models import BacktestResult, BacktestTrade


def generate_report(result: BacktestResult) -> str:
    """Generate formatted text report from backtest results."""
    lines: list[str] = []
    trades = result.trades

    lines.append("=" * 70)
    lines.append("  EP GAP TRADING BACKTEST REPORT")
    lines.append("=" * 70)
    lines.append(f"  Period:         {result.from_date} to {result.to_date}")
    lines.append(f"  Position size:  ${result.position_size:,.0f}")
    lines.append(f"  Initial capital: ${result.initial_capital:,.0f}")
    lines.append("")

    if not trades:
        lines.append("  No trades executed.")
        lines.append("")
        _append_skipped_summary(lines, result)
        return "\n".join(lines)

    # Compute summary stats
    stats = _compute_stats(trades, result.initial_capital)
    result.summary.update(stats)

    lines.append("─" * 70)
    lines.append("  SUMMARY")
    lines.append("─" * 70)
    lines.append(f"  Total trades:     {stats['total_trades']}")
    lines.append(f"  Winners:          {stats['winners']} ({stats['win_rate']:.1f}%)")
    lines.append(f"  Losers:           {stats['losers']}")
    lines.append(f"  Avg winner:       ${stats['avg_winner']:+,.2f} ({stats['avg_winner_pct']:+.1f}%)")
    lines.append(f"  Avg loser:        ${stats['avg_loser']:+,.2f} ({stats['avg_loser_pct']:+.1f}%)")
    lines.append(f"  Profit factor:    {stats['profit_factor']:.2f}")
    lines.append(f"  Expectancy/trade: ${stats['expectancy']:+,.2f}")
    lines.append(f"  Total P&L:        ${stats['total_pnl']:+,.2f}")
    lines.append(f"  Max drawdown:     ${stats['max_drawdown']:+,.2f} ({stats['max_drawdown_pct']:.1f}%)")
    lines.append(f"  Max consec losses: {stats['max_consecutive_losses']}")
    lines.append(f"  Avg hold days:    {stats['avg_hold_days']:.1f}")
    if stats.get("sharpe"):
        lines.append(f"  Approx Sharpe:    {stats['sharpe']:.2f}")
    lines.append("")

    # Breakdown by catalyst quality
    lines.append("─" * 70)
    lines.append("  BY CATALYST QUALITY")
    lines.append("─" * 70)
    _append_breakdown(lines, trades, key_fn=lambda t: t.catalyst_quality or "unknown")

    # Breakdown by regime
    lines.append("─" * 70)
    lines.append("  BY MARKET REGIME")
    lines.append("─" * 70)
    _append_breakdown(lines, trades, key_fn=lambda t: t.regime or "unknown")

    # Breakdown by EP score band
    lines.append("─" * 70)
    lines.append("  BY EP SCORE BAND")
    lines.append("─" * 70)
    _append_breakdown(lines, trades, key_fn=lambda t: _score_band(t.ep_score))

    # Breakdown by month
    lines.append("─" * 70)
    lines.append("  BY MONTH")
    lines.append("─" * 70)
    _append_breakdown(lines, trades, key_fn=lambda t: t.alert_date.strftime("%Y-%m"))

    # Safeguard summary
    safeguards = result.summary.get("safeguards", {})
    if safeguards and safeguards.get("total_blocks", 0) > 0:
        lines.append("─" * 70)
        lines.append("  SAFEGUARD BLOCKS (would have triggered)")
        lines.append("─" * 70)
        for k, v in safeguards.items():
            if k != "total_blocks" and v > 0:
                lines.append(f"  {k}: {v}")
        lines.append(f"  TOTAL: {safeguards['total_blocks']}")
        lines.append("")

    # Skipped trades
    _append_skipped_summary(lines, result)

    # Trade log
    lines.append("─" * 70)
    lines.append("  TRADE LOG")
    lines.append("─" * 70)
    for t in trades:
        status = "W" if t.is_winner else "L"
        exit_reasons = ", ".join(e.exit_reason for e in t.exits)
        lines.append(
            f"  [{status}] {t.alert_date} {t.ticker:6s} "
            f"score={t.ep_score:.0f} gap={t.gap_pct:+.1f}% "
            f"P&L=${t.total_pnl:+,.2f} ({t.return_pct:+.1f}%) "
            f"hold={t.hold_days}d exits={exit_reasons}"
        )
    lines.append("")

    lines.append("=" * 70)
    return "\n".join(lines)


def _compute_stats(trades: list[BacktestTrade], initial_capital: float) -> dict[str, Any]:
    """Compute summary statistics."""
    if not trades:
        return {}

    winners = [t for t in trades if t.is_winner]
    losers = [t for t in trades if not t.is_winner]

    total_pnl = sum(t.total_pnl for t in trades)
    gross_profit = sum(t.total_pnl for t in winners) if winners else 0
    gross_loss = abs(sum(t.total_pnl for t in losers)) if losers else 0

    # Max consecutive losses
    max_consec = 0
    current_consec = 0
    for t in trades:
        if not t.is_winner:
            current_consec += 1
            max_consec = max(max_consec, current_consec)
        else:
            current_consec = 0

    # Max drawdown
    equity_curve = []
    running_equity = initial_capital
    for t in trades:
        running_equity += t.total_pnl
        equity_curve.append(running_equity)

    peak = initial_capital
    max_dd = 0.0
    for eq in equity_curve:
        peak = max(peak, eq)
        dd = eq - peak
        max_dd = min(max_dd, dd)

    # Sharpe approximation (annualized)
    returns = [t.return_pct / 100 for t in trades]
    avg_ret = sum(returns) / len(returns) if returns else 0
    if len(returns) > 1:
        import math
        variance = sum((r - avg_ret) ** 2 for r in returns) / (len(returns) - 1)
        std_ret = math.sqrt(variance)
        # Annualize: assume ~250 trading days, ~2 trades/week
        trades_per_year = len(trades) / max(1, (trades[-1].alert_date - trades[0].alert_date).days) * 252
        sharpe = (avg_ret * trades_per_year) / (std_ret * math.sqrt(trades_per_year)) if std_ret > 0 else 0
    else:
        sharpe = 0

    return {
        "total_trades": len(trades),
        "winners": len(winners),
        "losers": len(losers),
        "win_rate": len(winners) / len(trades) * 100,
        "avg_winner": gross_profit / len(winners) if winners else 0,
        "avg_loser": -(gross_loss / len(losers)) if losers else 0,
        "avg_winner_pct": sum(t.return_pct for t in winners) / len(winners) if winners else 0,
        "avg_loser_pct": sum(t.return_pct for t in losers) / len(losers) if losers else 0,
        "profit_factor": gross_profit / gross_loss if gross_loss > 0 else float("inf"),
        "expectancy": total_pnl / len(trades),
        "total_pnl": total_pnl,
        "max_drawdown": max_dd,
        "max_drawdown_pct": abs(max_dd) / initial_capital * 100 if initial_capital > 0 else 0,
        "max_consecutive_losses": max_consec,
        "avg_hold_days": sum(t.hold_days for t in trades) / len(trades),
        "sharpe": sharpe,
    }


def _score_band(score: float) -> str:
    if score >= 90:
        return "90+"
    elif score >= 80:
        return "80-89"
    elif score >= 70:
        return "70-79"
    else:
        return "<70"


def _append_breakdown(
    lines: list[str],
    trades: list[BacktestTrade],
    key_fn,
) -> None:
    """Append a breakdown table grouped by key_fn."""
    groups: dict[str, list[BacktestTrade]] = defaultdict(list)
    for t in trades:
        groups[key_fn(t)].append(t)

    for group_name in sorted(groups.keys()):
        group_trades = groups[group_name]
        n = len(group_trades)
        wins = sum(1 for t in group_trades if t.is_winner)
        total = sum(t.total_pnl for t in group_trades)
        wr = wins / n * 100 if n else 0
        lines.append(
            f"  {group_name:20s}  trades={n:3d}  "
            f"win={wr:5.1f}%  P&L=${total:+10,.2f}"
        )
    lines.append("")


def _append_skipped_summary(lines: list[str], result: BacktestResult) -> None:
    """Append summary of skipped trades."""
    skipped = result.skipped_trades
    if not skipped:
        return

    lines.append("─" * 70)
    lines.append(f"  SKIPPED TRADES ({len(skipped)} total)")
    lines.append("─" * 70)

    reasons: dict[str, int] = defaultdict(int)
    for t in skipped:
        reasons[t.skip_reason or "unknown"] += 1

    for reason, count in sorted(reasons.items(), key=lambda x: -x[1]):
        lines.append(f"  {reason:30s}  {count}")
    lines.append("")


def export_csv(result: BacktestResult) -> str:
    """Export trade log as CSV string."""
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "ticker", "alert_date", "ep_score", "catalyst_quality", "gap_pct",
        "regime", "orb_high", "orb_low", "atr_14",
        "entries", "exits", "total_pnl", "return_pct",
        "hold_days", "exit_reasons",
    ])

    for t in result.trades:
        entry_info = "; ".join(
            f"#{e.attempt_number} @{e.entry_price:.2f} stop={e.stop_price:.2f}"
            for e in t.entries
        )
        exit_info = "; ".join(
            f"{e.exit_reason} @{e.exit_price:.2f} shares={e.shares_exited:.1f}"
            for e in t.exits
        )
        writer.writerow([
            t.ticker, t.alert_date, f"{t.ep_score:.0f}", t.catalyst_quality,
            f"{t.gap_pct:.1f}", t.regime or "",
            f"{t.orb_high:.2f}" if t.orb_high else "",
            f"{t.orb_low:.2f}" if t.orb_low else "",
            f"{t.atr_14:.2f}" if t.atr_14 else "",
            entry_info, exit_info,
            f"{t.total_pnl:.2f}", f"{t.return_pct:.1f}",
            t.hold_days, "/".join(e.exit_reason for e in t.exits),
        ])

    return output.getvalue()
