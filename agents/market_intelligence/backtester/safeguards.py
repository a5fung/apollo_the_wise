"""Risk safeguards — tracked in backtest, enforced in live trading."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from agents.market_intelligence.backtester.models import BacktestTrade
from agents.market_intelligence.constants import (
    CIRCUIT_BREAKER_CONSEC_LOSSES,
    CIRCUIT_BREAKER_COOLDOWN_DAYS,
)


@dataclass
class RiskConfig:
    max_daily_loss: float = 2000.0
    max_concurrent_positions: int = 4
    max_position_pct: float = 0.10  # 10% of account
    max_same_sector: int = 2
    circuit_breaker_consecutive_losses: int = CIRCUIT_BREAKER_CONSEC_LOSSES
    circuit_breaker_cooldown_days: int = CIRCUIT_BREAKER_COOLDOWN_DAYS


@dataclass
class SafeguardTracker:
    """Track how often each safeguard would have triggered during backtest."""
    config: RiskConfig = field(default_factory=RiskConfig)

    # Counters
    daily_loss_blocks: int = 0
    concurrent_position_blocks: int = 0
    position_size_blocks: int = 0
    sector_concentration_blocks: int = 0
    circuit_breaker_blocks: int = 0

    # State
    _daily_pnl: dict[date, float] = field(default_factory=dict)
    _open_positions: list[str] = field(default_factory=list)
    _consecutive_losses: int = 0
    _cooldown_until: date | None = None

    def would_block(
        self,
        trade_date: date,
        ticker: str,
        position_value: float,
        account_value: float,
        sector: str | None = None,
        open_sectors: list[str] | None = None,
    ) -> tuple[bool, str | None]:
        """Check if any safeguard would block this trade. Returns (blocked, reason)."""

        # Circuit breaker
        if self._cooldown_until and trade_date <= self._cooldown_until:
            self.circuit_breaker_blocks += 1
            return True, f"circuit_breaker (cooldown until {self._cooldown_until})"

        # Daily loss limit
        daily_loss = self._daily_pnl.get(trade_date, 0.0)
        if daily_loss <= -self.config.max_daily_loss:
            self.daily_loss_blocks += 1
            return True, f"daily_loss_limit (${daily_loss:,.0f})"

        # Concurrent positions
        if len(self._open_positions) >= self.config.max_concurrent_positions:
            self.concurrent_position_blocks += 1
            return True, f"max_concurrent ({len(self._open_positions)})"

        # Position size
        if account_value > 0 and position_value / account_value > self.config.max_position_pct:
            self.position_size_blocks += 1
            return True, f"position_too_large ({position_value / account_value:.0%})"

        # Sector concentration
        if sector and open_sectors:
            same_sector_count = sum(1 for s in open_sectors if s == sector)
            if same_sector_count >= self.config.max_same_sector:
                self.sector_concentration_blocks += 1
                return True, f"sector_concentration ({sector}: {same_sector_count})"

        return False, None

    def record_trade_open(self, ticker: str) -> None:
        if ticker not in self._open_positions:
            self._open_positions.append(ticker)

    def record_trade_close(self, trade: BacktestTrade) -> None:
        if trade.ticker in self._open_positions:
            self._open_positions.remove(trade.ticker)

        # Update daily PnL
        for ex in trade.exits:
            d = ex.exit_time.date()
            self._daily_pnl[d] = self._daily_pnl.get(d, 0.0) + ex.pnl

        # Track consecutive losses for circuit breaker
        if trade.total_pnl < 0:
            self._consecutive_losses += 1
            if self._consecutive_losses >= self.config.circuit_breaker_consecutive_losses:
                from datetime import timedelta
                self._cooldown_until = trade.alert_date + timedelta(
                    days=self.config.circuit_breaker_cooldown_days
                )
        else:
            self._consecutive_losses = 0
            self._cooldown_until = None

    @property
    def summary(self) -> dict[str, int]:
        return {
            "daily_loss_blocks": self.daily_loss_blocks,
            "concurrent_position_blocks": self.concurrent_position_blocks,
            "position_size_blocks": self.position_size_blocks,
            "sector_concentration_blocks": self.sector_concentration_blocks,
            "circuit_breaker_blocks": self.circuit_breaker_blocks,
            "total_blocks": (
                self.daily_loss_blocks + self.concurrent_position_blocks
                + self.position_size_blocks + self.sector_concentration_blocks
                + self.circuit_breaker_blocks
            ),
        }
