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
import re
from datetime import date
from pathlib import Path
from typing import Any

import yaml

from agents.market_intelligence.db import get_pool

logger = logging.getLogger(__name__)

_REGISTRY_PATH = Path(__file__).resolve().parents[2] / "data_gated_reviews.yaml"


# ── readiness sanity check (#517, 2026-08-17) ──────────────────────────────────────────────────
# Two real failure classes measured this week, both surfacing a review as READY when it cannot
# actually be answered:
#   (1) DATE-FIRE — the "predicate" is calendar-only (no table read at all), dressed up as SQL.
#       `exposure_family_cap_promotion` was exactly this: `SELECT CASE WHEN CURRENT_DATE >= ...`.
#       It is not wrong to have a date-only gate — `predicate_sql: null` is the documented, HONEST
#       way to say that — but a fake predicate reads as an evidence gate when it is not one.
#   (2) POPULATION MISMATCH — the predicate counts a table that has a column separating genuinely
#       different questions (which SETUP, which ENTRY VARIANT, which ACCOUNT) and does not filter
#       on it. `stop_too_wide_outcome_cohort` fired ready on 13+ rows that blended MAGNA53's stop-
#       too-wide rejections with 9M Day 2's — a different setup sharing the same skip_reason prefix
#       — while the cohort the review is actually about stood at 9, below its own bar.
#
# Both checks are STATIC (regex over predicate_sql text, no DB needed) and deliberately narrow:
# they do not know whether blending a population is a bug or an intentional whole-book question
# (`kill_scale_bands_quarterly_review` is legitimately about the whole live book, not one setup —
# flagging it is still useful, but it must not be silently auto-"fixed" or hidden). The check's
# job is to make the mismatch VISIBLE (with a real breakdown of what the predicate counted), not
# to decide it — same posture as the status-vocabulary lint in preflight_yaml_dupe_keys.py.

# table -> categorical columns whose values represent DIFFERENT QUESTIONS, not just different
# rows of the same one (verified against prod information_schema.columns 2026-08-17). Excludes
# columns that are effectively unique keys (e.g. mi_strategies.strategy_id) — those don't define
# a population split, they just identify the row.
DISCRIMINATING_COLUMNS: dict[str, list[str]] = {
    "mi_account_equity_snapshots": ["account_mode"],
    "mi_alert_rank_shadow": ["account_mode"],
    "mi_consolidation_entry_shadow": ["entry_mode"],
    "mi_exit_path_shadow": ["account_mode", "signal_type"],
    "mi_giveback_shadow": ["account_mode"],
    "mi_live_trades": ["signal_type", "account_mode"],
    "mi_orb_shadow_trades": ["signal_type"],
    "mi_pending_allocations": ["strategy"],
    "mi_pivot_stop_shadow": ["account_mode"],
    "mi_position_mgmt_decisions": ["account_mode"],
    "mi_safeguard_state": ["account_mode"],
    "mi_sell_discipline_records": ["signal_type", "account_mode"],
    "mi_signal_outcomes": ["signal_type"],
    "mi_strategies": ["signal_type"],
    "mi_theme_birth_candidates": ["mode"],
}


def is_date_fire_predicate(predicate_sql: str | None) -> bool:
    """True when `predicate_sql` is SQL text with no FROM clause at all — it can only ever be a
    function of the calendar/constants, never real accrued evidence, even though it LOOKS like an
    evidence-gated predicate. `predicate_sql: null` (the documented, honest date-only gate) is NOT
    this class — it never claimed to read data. This catches the dressed-up version."""
    if not predicate_sql or not predicate_sql.strip():
        return False
    return re.search(r"\bFROM\b", predicate_sql, re.IGNORECASE) is None


def find_population_mismatch(predicate_sql: str | None) -> list[str]:
    """Return ["table.column", ...] for every FROM-referenced table with a known discriminating
    column that the predicate text never mentions. `COUNT(DISTINCT ...)` predicates are exempted
    — deduping on a non-discriminating column (e.g. a date) already collapses across whatever
    category would otherwise fan the count out, so an unfiltered category there does not inflate
    anything (verified 2026-08-17: `drawdown_breaker_promotion` / `live_cutover_decision` /
    `rt_admission_recut_post_2r_exits` all read this way and are not bugs)."""
    if not predicate_sql or not predicate_sql.strip():
        return []
    if re.search(r"COUNT\(\s*DISTINCT\b", predicate_sql, re.IGNORECASE):
        return []
    tables = {m.group(1).lower() for m in re.finditer(
        r"\bFROM\s+([a-zA-Z_][a-zA-Z0-9_]*)", predicate_sql, re.IGNORECASE)}
    out: list[str] = []
    for table in sorted(tables):
        for col in DISCRIMINATING_COLUMNS.get(table, []):
            if not re.search(r"\b" + re.escape(col) + r"\b", predicate_sql, re.IGNORECASE):
                out.append(f"{table}.{col}")
    return out


def _strip_sql_comments(sql: str) -> str:
    """Blank out `-- ...` line comments. Best-effort — good enough for this registry's
    single-statement predicates; no `--` has been observed inside a string literal here."""
    return "\n".join(re.sub(r"--.*$", "", line) for line in sql.split("\n"))


def build_population_breakdown_sql(predicate_sql: str, column: str) -> str | None:
    """Best-effort rewrite of a `SELECT COUNT(*) FROM T WHERE ...` predicate into
    `SELECT <column>, COUNT(*) FROM T WHERE ... GROUP BY <column>` so the ready-review payload
    can show what the predicate actually counted, split by the column it should have filtered on.
    Returns None for any shape that isn't a plain top-level `SELECT COUNT(*)` (CASE-wrapped,
    LEAST()-wrapped, nested-subquery-as-the-whole-query, etc.) — those fall back to "flagged, no
    breakdown available" rather than risk emitting broken SQL against prod."""
    stripped = _strip_sql_comments(predicate_sql).strip()
    m = re.match(r"^SELECT\s+COUNT\(\s*\*\s*\)\s*(?:::\w+)?\s*(FROM\s.+)$",
                 stripped, re.IGNORECASE | re.DOTALL)
    if not m:
        return None
    rest = m.group(1).split(";", 1)[0].rstrip()
    return f"SELECT {column}, COUNT(*) AS n {rest}\nGROUP BY {column}\nORDER BY n DESC"


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


async def _evaluate_breakdown(sql: str) -> list[tuple[Any, int]] | None:
    """Run a breakdown query built by `build_population_breakdown_sql`; returns
    [(category_value, count), ...]. Best-effort like the predicate itself — a broken breakdown
    must never break the digest, so any failure here is logged and swallowed by the caller."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(sql)
    return [(r[0], int(r[1])) for r in rows]


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
        # #517 2026-08-17 — readiness sanity check. See the module docstring block above for the
        # two failure classes these catch (date-fire, population mismatch) and why they're static.
        last_run_inconclusive_on = e.get("last_run_inconclusive_on")
        evidence_flags = {
            "date_fire": is_date_fire_predicate(predicate_sql),
            "population_mismatch": find_population_mismatch(predicate_sql),
        }
        entry_summary = {
            "review_id": review_id,
            "title": e.get("title"),
            "current_count": count,
            "threshold": threshold,
            "action_when_ready": (e.get("action_when_ready") or "").strip(),
            # ⚠ ADDED 2026-08-03. The #517 teeth shipped 8/02 — per-item AGE, the ≥30d stale
            # banner, and oldest-first ordering — all key off `earliest_review_date`, and this
            # payload did not carry it. So every one of them was INERT in production: `_age()`
            # returned None, the tag rendered empty, the banner never fired, and the "oldest-first"
            # sort compared 0 to 0. The unit tests passed because they fed the renderer fabricated
            # dicts that DID have the field. Same class as `/audit` and `/crypto`: correct code,
            # wrong payload, nothing failing.
            "earliest_review_date": earliest.isoformat() if hasattr(earliest, "isoformat") else earliest,
            # `kind` drives HOW age is read — see the vocabulary in data_gated_reviews.yaml.
            "kind": (e.get("kind") or "accrual"),
            # #517 2026-08-17. Must be in the payload or the renderer that reads them is inert —
            # exactly the 8/03 bug above, so pinned by the same producer-supplies-it test.
            "evidence_flags": evidence_flags,
            "last_run_inconclusive_on": (last_run_inconclusive_on.isoformat()
                                          if hasattr(last_run_inconclusive_on, "isoformat")
                                          else last_run_inconclusive_on),
            "last_run_note": e.get("last_run_note"),
        }
        # Only worth the extra DB round-trip for entries actually surfacing ready — a mismatch on
        # a still-accumulating entry isn't actionable yet. Best-effort: a broken breakdown must
        # never take the digest down with it (same posture as the predicate itself, above).
        if is_ready and predicate_sql and evidence_flags["population_mismatch"]:
            breakdown: dict[str, list] = {}
            for tag in evidence_flags["population_mismatch"]:
                col = tag.split(".", 1)[1]
                bsql = build_population_breakdown_sql(predicate_sql, col)
                if not bsql:
                    continue
                try:
                    rows = await _evaluate_breakdown(bsql)
                except Exception as exc:
                    logger.warning(f"population breakdown failed for {review_id}.{tag}: {exc}")
                    continue
                if rows:
                    breakdown[tag] = rows
            if breakdown:
                entry_summary["population_breakdown"] = breakdown
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
