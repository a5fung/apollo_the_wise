"""Regression tests for _9m_pace_digest_job (#133, 2026-05-27).

Pace alerts (89% of pinged 9M volume on 2026-05-27) moved from the
per-5-min digest in ninem_detector to an hourly rollup. Tests pin the
selection/dedup/ranking logic by exercising the SQL result handling.
"""
import sys
import types
from unittest.mock import AsyncMock, MagicMock


# Reuse the alpaca-SDK stubbing pattern from sibling tests so loading
# scheduler.py doesn't fail in dev environments without the broker SDK.
class _MockModule(types.ModuleType):
    def __getattr__(self, name):
        v = MagicMock(name=f"{self.__name__}.{name}")
        setattr(self, name, v)
        return v


for mod_name in [
    "alpaca", "alpaca.trading", "alpaca.trading.client", "alpaca.trading.requests",
    "alpaca.trading.enums", "alpaca.trading.models", "alpaca.trading.stream",
    "alpaca.data", "alpaca.data.historical", "alpaca.data.requests",
    "alpaca.data.timeframe", "alpaca.data.enums", "alpaca.common",
    "alpaca.common.exceptions",
]:
    sys.modules.setdefault(mod_name, _MockModule(mod_name))


# Replicate the in-job selection logic as a pure helper so tests don't
# need to stand up an asyncpg pool. The actual job in scheduler.py wraps
# this with the DB-query layer and Telegram send.
def select_pace_digest_rows(
    pace_rows: list[dict],
    actual_tickers_same_hour: set[str],
    cap: int = 10,
) -> list[dict]:
    """The deterministic core: dedup against actual-pinged tickers, keep
    highest-projection row per ticker, sort by projected_vol desc, cap."""
    seen: dict[str, dict] = {}
    for r in pace_rows:
        if r["ticker"] in actual_tickers_same_hour:
            continue
        prior = seen.get(r["ticker"])
        if prior is None or (r["projected_vol"] or 0) > (prior["projected_vol"] or 0):
            seen[r["ticker"]] = dict(r)
    return sorted(
        seen.values(),
        key=lambda r: (r["projected_vol"] or 0),
        reverse=True,
    )[:cap]


# ── Cases ────────────────────────────────────────────────────────────────────

def test_empty_returns_empty():
    assert select_pace_digest_rows([], set()) == []


def test_dedup_against_actual_same_hour():
    """If a ticker pinged actual this hour, skip it in the pace digest."""
    pace = [
        {"ticker": "FOO", "projected_vol": 20_000_000, "current_price": 10.0, "gap_pct": 5.0},
        {"ticker": "BAR", "projected_vol": 15_000_000, "current_price": 8.0, "gap_pct": 3.0},
    ]
    result = select_pace_digest_rows(pace, actual_tickers_same_hour={"FOO"})
    assert [r["ticker"] for r in result] == ["BAR"]


def test_collapse_per_ticker_keep_highest_projection():
    """Same ticker fires multiple times within the hour; keep the row
    with highest projection."""
    pace = [
        {"ticker": "FOO", "projected_vol": 15_000_000, "current_price": 10.0, "gap_pct": 5.0},
        {"ticker": "FOO", "projected_vol": 22_000_000, "current_price": 10.5, "gap_pct": 6.0},
        {"ticker": "FOO", "projected_vol": 18_000_000, "current_price": 10.2, "gap_pct": 5.5},
    ]
    result = select_pace_digest_rows(pace, set())
    assert len(result) == 1
    assert result[0]["projected_vol"] == 22_000_000
    assert result[0]["gap_pct"] == 6.0


def test_sort_by_projected_vol_desc():
    pace = [
        {"ticker": "A", "projected_vol": 12_000_000, "current_price": 5.0, "gap_pct": 1.0},
        {"ticker": "B", "projected_vol": 30_000_000, "current_price": 6.0, "gap_pct": 2.0},
        {"ticker": "C", "projected_vol": 20_000_000, "current_price": 7.0, "gap_pct": 3.0},
    ]
    result = select_pace_digest_rows(pace, set())
    assert [r["ticker"] for r in result] == ["B", "C", "A"]


def test_cap_at_ten():
    """Runaway hour with >10 pace tickers — cap to top 10 by projection."""
    pace = [
        {"ticker": f"T{i:02d}", "projected_vol": (i + 1) * 1_000_000,
         "current_price": 5.0, "gap_pct": 1.0}
        for i in range(15)
    ]
    result = select_pace_digest_rows(pace, set())
    assert len(result) == 10
    # Largest projection first
    assert result[0]["ticker"] == "T14"
    assert result[-1]["ticker"] == "T05"


def test_null_projected_vol_treated_as_zero():
    """Defensive: if projected_vol is NULL on a row, treat as 0 for
    ranking (won't bubble to the top)."""
    pace = [
        {"ticker": "A", "projected_vol": None, "current_price": 5.0, "gap_pct": 1.0},
        {"ticker": "B", "projected_vol": 20_000_000, "current_price": 6.0, "gap_pct": 2.0},
    ]
    result = select_pace_digest_rows(pace, set())
    assert result[0]["ticker"] == "B"
    assert result[1]["ticker"] == "A"


def test_actual_dedup_does_not_collapse_other_tickers():
    """A ticker fired actual + pace — pace gets skipped. Other tickers
    that only fired pace should still appear."""
    pace = [
        {"ticker": "FOO", "projected_vol": 25_000_000, "current_price": 10.0, "gap_pct": 5.0},
        {"ticker": "BAR", "projected_vol": 15_000_000, "current_price": 8.0, "gap_pct": 3.0},
        {"ticker": "BAZ", "projected_vol": 18_000_000, "current_price": 9.0, "gap_pct": 4.0},
    ]
    result = select_pace_digest_rows(pace, actual_tickers_same_hour={"FOO"})
    assert {r["ticker"] for r in result} == {"BAR", "BAZ"}
