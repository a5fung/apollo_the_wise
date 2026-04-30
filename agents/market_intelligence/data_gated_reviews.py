"""Data-gated reviews: surface pending reviews when their data threshold flips.

Registry: `data_gated_reviews.yaml` at repo root. Each entry declares a SQL
predicate (returns a count) and a threshold; when count >= threshold AND
today >= earliest_review_date AND status == 'pending', the entry is "ready"
and surfaces in the Sunday weekly system review.

Predicate-less entries (predicate_sql: null) surface purely on date.

Failure handling: any predicate that errors is logged and treated as
not-ready. The registry is best-effort surfacing; bad SQL must not break
the weekly digest.
"""
from __future__ import annotations

import logging
from datetime import date
from pathlib import Path
from typing import Any

import yaml

from agents.market_intelligence.db import get_pool

logger = logging.getLogger(__name__)

_REGISTRY_PATH = Path(__file__).resolve().parents[2] / "data_gated_reviews.yaml"


def _load_registry() -> list[dict[str, Any]]:
    if not _REGISTRY_PATH.exists():
        return []
    try:
        raw = yaml.safe_load(_REGISTRY_PATH.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError:
        logger.exception("data_gated_reviews.yaml parse failed")
        return []
    return list(raw.get("reviews") or [])


async def _evaluate_predicate(sql: str) -> int | None:
    """Run predicate SQL; expect a single-row single-column integer count."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow(sql)
    if row is None:
        return 0
    val = next(iter(row.values()), None)
    return int(val) if val is not None else 0


async def check_pending_reviews(today: date | None = None) -> dict[str, Any]:
    """Walk the registry; return ready + pending summaries for the digest."""
    today = today or date.today()
    entries = _load_registry()

    ready: list[dict] = []
    pending: list[dict] = []

    for e in entries:
        if e.get("status") != "pending":
            continue
        review_id = e.get("review_id") or "<unknown>"
        earliest = e.get("earliest_review_date")
        if earliest and isinstance(earliest, date) and today < earliest:
            pending.append({
                "review_id": review_id,
                "title": e.get("title"),
                "blocked_by": f"earliest_review_date={earliest.isoformat()}",
            })
            continue

        predicate_sql = e.get("predicate_sql")
        threshold = int(e.get("threshold") or 0)
        count: int | None = None
        if predicate_sql:
            try:
                count = await _evaluate_predicate(predicate_sql)
            except Exception as exc:
                logger.warning(f"predicate failed for {review_id}: {exc}")
                pending.append({
                    "review_id": review_id,
                    "title": e.get("title"),
                    "blocked_by": f"predicate_error: {type(exc).__name__}",
                })
                continue

        is_ready = (predicate_sql is None) or (count is not None and count >= threshold)
        entry_summary = {
            "review_id": review_id,
            "title": e.get("title"),
            "current_count": count,
            "threshold": threshold,
            "action_when_ready": (e.get("action_when_ready") or "").strip(),
        }
        if is_ready:
            ready.append(entry_summary)
        else:
            entry_summary["blocked_by"] = f"count={count} < threshold={threshold}"
            pending.append(entry_summary)

    return {
        "ready": ready,
        "pending_count": len(pending),
        "pending_summary": pending[:5],
    }
