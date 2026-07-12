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
    conn = MagicMock()
    conn.fetch = AsyncMock(return_value=_rows(
        _decision("HIGH", "demote"),
        _decision("HIGH", "hold"),
        _decision("MODERATE", "demote"),
        _decision("none", "demote"),
    ))
    assert await sa._today_judge_high_rate(conn) == 0.5      # 2/4 HIGH
    assert await sa._today_judge_demote_share(conn) == 0.75  # 3/4 demote


@pytest.mark.asyncio
async def test_zero_decisions_returns_zero_not_crash():
    conn = MagicMock()
    conn.fetch = AsyncMock(return_value=[])
    assert await sa._today_judge_high_rate(conn) == 0.0
    assert await sa._today_judge_demote_share(conn) == 0.0


@pytest.mark.asyncio
async def test_malformed_detail_rows_skipped_never_crash():
    conn = MagicMock()
    conn.fetch = AsyncMock(return_value=_rows(
        "not json at all {",
        json.dumps(["a", "list", "not", "a", "dict"]),
        None,
        _decision("HIGH", "promote"),
    ))
    # only the one valid dict counts: 1/1 HIGH, 0/1 demote
    assert await sa._today_judge_high_rate(conn) == 1.0
    assert await sa._today_judge_demote_share(conn) == 0.0


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
