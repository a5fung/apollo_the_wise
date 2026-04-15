"""Data models for the EP gap trading backtest."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any


@dataclass
class TradeEntry:
    entry_time: datetime
    entry_price: float
    stop_price: float
    attempt_number: int
    shares: float


@dataclass
class TradeExit:
    exit_time: datetime
    exit_price: float
    exit_reason: str  # stop_hit, eod_partial, trailing_stop, data_ended
    shares_exited: float
    pnl: float
    attempt_number: int = 0  # which entry attempt this exit closes


@dataclass
class BacktestTrade:
    ticker: str
    alert_date: date
    ep_score: float
    catalyst_quality: str
    gap_pct: float
    regime: str | None
    entries: list[TradeEntry] = field(default_factory=list)
    exits: list[TradeExit] = field(default_factory=list)
    total_pnl: float = 0.0
    hold_days: int = 0
    skipped: bool = False
    skip_reason: str | None = None
    orb_high: float | None = None
    orb_low: float | None = None
    atr_14: float | None = None
    breakeven_stop: bool = False
    # Day 1 simulation state — set by _simulate_day1, consumed by simulate_trade
    remaining_shares: float = 0.0
    last_entry: TradeEntry | None = None
    day1_low: float | None = None

    @property
    def total_shares_entered(self) -> float:
        return sum(e.shares for e in self.entries)

    @property
    def total_shares_exited(self) -> float:
        return sum(e.shares_exited for e in self.exits)

    @property
    def avg_entry_price(self) -> float:
        if not self.entries:
            return 0.0
        total_cost = sum(e.entry_price * e.shares for e in self.entries)
        total_shares = sum(e.shares for e in self.entries)
        return total_cost / total_shares if total_shares else 0.0

    @property
    def return_pct(self) -> float:
        if not self.entries:
            return 0.0
        cost_basis = self.avg_entry_price * self.total_shares_entered
        return (self.total_pnl / cost_basis * 100) if cost_basis else 0.0

    @property
    def is_winner(self) -> bool:
        return self.total_pnl > 0


@dataclass
class BacktestResult:
    trades: list[BacktestTrade]
    skipped_trades: list[BacktestTrade]
    from_date: date
    to_date: date
    initial_capital: float
    position_size: float
    summary: dict[str, Any] = field(default_factory=dict)
