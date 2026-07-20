"""T2c (Block 3, built Block 4 flex 7/12) — the judge runtime-drift MetricSpecs.

The premortem-R5 precondition for the 7/18 authority flip: judge_high_rate_daily +
judge_demote_share_daily as L2-banded metrics. Python-side detail parse (TEXT column;
malformed rows skipped, never crash)."""
import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from agents.market_intelligence import system_audit as sa


def _rows(*details):
    return [{"detail": d} for d in details]


def _decision(tier="HIGH", direction="demote"):
    return json.dumps({"judge_tier": tier, "judge_direction": direction,
                       "authority": "judge", "rubric_hash": "eef69fa4"})


@pytest.mark.asyncio
async def test_high_rate_and_demote_share_computed():
    # >= _MIN_DETECTED_FOR_GATE (5) decisions so the N-floor lets the rate compute.
    conn = MagicMock()
    conn.fetch = AsyncMock(return_value=_rows(
        _decision("HIGH", "demote"),
        _decision("HIGH", "hold"),
        _decision("MODERATE", "demote"),
        _decision("none", "demote"),
        _decision("HIGH", "promote"),
    ))
    assert await sa._today_judge_high_rate(conn) == 3 / 5      # 3/5 HIGH (rows 1,2,5)
    assert await sa._today_judge_demote_share(conn) == 3 / 5   # 3/5 demote (rows 1,3,4)


@pytest.mark.asyncio
async def test_below_floor_returns_none_not_zero():
    # N-floor (2026-07-20, evidenced by the HUT false L2): < _MIN_DETECTED_FOR_GATE
    # decisions -> None, so a tiny denominator can't fire L2 AND no structural zero
    # pollutes the baseline. Covers 0, 1, and floor-1 decisions.
    for rows in ([],
                 _rows(_decision("HIGH", "promote")),
                 _rows(*[_decision("HIGH", "promote")] * (sa._MIN_DETECTED_FOR_GATE - 1))):
        conn = MagicMock()
        conn.fetch = AsyncMock(return_value=rows)
        assert await sa._today_judge_high_rate(conn) is None
        assert await sa._today_judge_demote_share(conn) is None


@pytest.mark.asyncio
async def test_malformed_detail_rows_skipped_never_crash():
    # 5 valid dicts (>= floor) + malformed rows that must be skipped, never crash.
    conn = MagicMock()
    conn.fetch = AsyncMock(return_value=_rows(
        "not json at all {",
        json.dumps(["a", "list", "not", "a", "dict"]),
        None,
        _decision("HIGH", "promote"),
        _decision("HIGH", "promote"),
        _decision("HIGH", "promote"),
        _decision("MODERATE", "demote"),
        _decision("MODERATE", "demote"),
    ))
    # only the 5 valid dicts count: 3/5 HIGH, 2/5 demote
    assert await sa._today_judge_high_rate(conn) == 3 / 5
    assert await sa._today_judge_demote_share(conn) == 2 / 5


def test_registered_in_trade_metrics_with_cold_start_ceilings():
    names = {m.name for m in sa._TRADE_METRICS}
    assert {"judge_high_rate_daily", "judge_demote_share_daily"} <= names
    assert sa._COLD_START_CEILINGS["judge_high_rate_daily"] == (0.85, "high")
    assert sa._COLD_START_CEILINGS["judge_demote_share_daily"] == (0.90, "high")
    # deliberately NOT regime-conditional at introduction (T2c spec)
    assert "judge_high_rate_daily" not in sa._REGIME_CONDITIONAL_METRICS
    assert "judge_demote_share_daily" not in sa._REGIME_CONDITIONAL_METRICS
    # both are in _ALL_METRICS (the scan actually runs them)
    all_names = {m.name for m in sa._ALL_METRICS}
    assert {"judge_high_rate_daily", "judge_demote_share_daily"} <= all_names
