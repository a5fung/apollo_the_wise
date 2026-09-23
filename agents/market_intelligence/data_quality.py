"""
Data quality gates for the nightly pipeline.

Validates each pipeline step against expected counts (rolling avg of last 5 successful runs).
Surfaces warnings in briefings when data is degraded.
"""
from __future__ import annotations

import logging
from datetime import date

from agents.market_intelligence.db import (
    upsert_data_quality,
    get_data_quality_expected,
    get_data_quality_issues,
)

logger = logging.getLogger(__name__)


async def check_ingest_quality(ingested_count: int, trade_date: date) -> dict:
    """Validate daily ingest count against rolling average. Default expected ~7000."""
    expected = await get_data_quality_expected("ingest", "ticker_count") or 7000.0
    passed = ingested_count >= expected * 0.9

    record = {
        "run_date": trade_date,
        "step": "ingest",
        "metric": "ticker_count",
        "value": float(ingested_count),
        "expected": expected,
        "passed": passed,
    }
    await upsert_data_quality(record)

    if not passed:
        logger.warning(
            f"Data quality: ingest {ingested_count} tickers (expected ~{expected:.0f})"
        )
    return record


async def check_rs_quality(scored_count: int, trade_date: date) -> dict:
    """Validate RS scored count against rolling average. Default expected ~5000."""
    expected = await get_data_quality_expected("rs_engine", "stocks_scored") or 5000.0
    passed = scored_count >= expected * 0.9

    record = {
        "run_date": trade_date,
        "step": "rs_engine",
        "metric": "stocks_scored",
        "value": float(scored_count),
        "expected": expected,
        "passed": passed,
    }
    await upsert_data_quality(record)

    if not passed:
        logger.warning(
            f"Data quality: RS scored {scored_count} stocks (expected ~{expected:.0f})"
        )
    return record


async def check_sector_quality(
    top_200_with_sector: int, total_top_200: int, trade_date: date,
) -> dict:
    """Validate sector coverage of top 200 RS stocks. Passes if >= 80%."""
    pct = (top_200_with_sector / max(total_top_200, 1)) * 100
    passed = pct >= 80.0

    record = {
        "run_date": trade_date,
        "step": "sector",
        "metric": "pct_with_sector",
        "value": round(pct, 1),
        "expected": 80.0,
        "passed": passed,
    }
    await upsert_data_quality(record)

    if not passed:
        logger.warning(
            f"Data quality: sector coverage {pct:.1f}% ({top_200_with_sector}/{total_top_200})"
        )
    return record


async def get_quality_warnings(trade_date: date) -> list[str]:
    """Return warning strings for any failed quality checks. Used by briefings."""
    issues = await get_data_quality_issues(trade_date)
    warnings = []
    for row in issues:
        step = row["step"]
        metric = row["metric"]
        value = row["value"]
        expected = row["expected"]

        if step == "ingest" and metric == "ticker_count":
            warnings.append(f"Ingest: {value:.0f} tickers (expected ~{expected:.0f})")
        elif step == "rs_engine" and metric == "stocks_scored":
            warnings.append(f"RS engine: {value:.0f} stocks scored (expected ~{expected:.0f})")
        elif step == "sector" and metric == "pct_with_sector":
            warnings.append(f"Sector coverage: {value:.0f}% (threshold 80%)")
        else:
            warnings.append(f"{step}/{metric}: {value} (expected {expected})")

    return warnings
