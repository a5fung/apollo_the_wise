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
    if today is None:
        from agents.market_intelligence.collector import et_today
        today = et_today()
    entries = _load_registry()

    ready: list[dict] = []
    pending: list[dict] = []
    errored: list[dict] = []   # predicate raised — the #54 silently-broken-query class

    for e in entries:
        # Process pending AND deferred entries (deferred = previously surfaced,
        # operator chose "wait" rather than "act now," with new
        # earliest_review_date set to the deferred_until date).
        # status=done entries are skipped entirely (audit trail only).
        # 2026-05-21: added deferred status per #64 advisor flag.
        if e.get("status") not in ("pending", "deferred"):
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
                err = {
                    "review_id": review_id,
                    "title": e.get("title"),
                    "blocked_by": f"predicate_error: {type(exc).__name__}",
                }
                errored.append(err)        # surfaced for escalation (don't let a broken query rot)
                pending.append(err)         # kept in pending too for digest back-compat
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
        "errored": errored,
        "pending_count": len(pending),
        "pending_summary": pending[:5],
    }


async def escalate_overdue_reviews(
    today: date | None = None, grace_days: int = 7, reescalate_days: int = 7
) -> list[dict[str, Any]]:
    """Deterministic, stateful escalation (Prong B, #54). A review that has been READY — or whose
    predicate has been ERRORING (the #54 silently-broken-query class) — for >= grace_days gets
    surfaced via its own deduped record (re-fires every reescalate_days). The stateless
    `check_pending_reviews` can't do grace/dedup, so first-seen + last-escalated dates live in
    `mi_review_escalation_state`. Returns the escalation records (caller Telegrams + audit-logs);
    rows for resolved reviews are cleared. No LLM, DB-sourced — survives container restarts."""
    if today is None:
        from agents.market_intelligence.collector import et_today
        today = et_today()
    from agents.market_intelligence.db import (
        get_review_escalation_state, upsert_review_escalation_state,
        clear_review_escalation_state,
    )

    res = await check_pending_reviews(today)
    ready = {r["review_id"]: r for r in res["ready"]}
    errored = {r["review_id"]: r for r in res.get("errored", [])}
    state = await get_review_escalation_state()
    active = set(ready) | set(errored)

    escalations: list[dict[str, Any]] = []
    for rid in sorted(active):
        st = state.get(rid, {})
        last_esc = st.get("last_escalated_date")
        if rid in ready:                       # ready takes precedence over a stale error flag
            kind, ref = "ready", ready[rid]
            first_ready = st.get("first_ready_date") or today
            first_error = None
            anchor = first_ready
        else:
            kind, ref = "error", errored[rid]
            first_error = st.get("first_error_date") or today
            first_ready = None
            anchor = first_error
        age = (today - anchor).days
        due = age >= grace_days and (
            last_esc is None or (today - last_esc).days >= reescalate_days
        )
        if due:
            last_esc = today
            escalations.append({
                "review_id": rid, "kind": kind, "age_days": age,
                "title": ref.get("title"),
                "current_count": ref.get("current_count"), "threshold": ref.get("threshold"),
                "blocked_by": ref.get("blocked_by"),
            })
        await upsert_review_escalation_state(rid, first_ready, first_error, last_esc)

    # Reviews that resolved (no longer ready/erroring) — drop their state.
    await clear_review_escalation_state([rid for rid in state if rid not in active])
    return escalations
