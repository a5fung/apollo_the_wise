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


# ── readiness sanity check (#517, 2026-08-17; DECLARED population, #573, 2026-08-30) ───────────
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
# #573 (2026-08-30) — (2) used to be answered by looking the table up in a hand-maintained
# `table -> [column]` dict, verified ONCE against prod schema on 2026-08-17 with NO ongoing link
# to it: a new table, or a new discriminating column on an existing table, got SILENTLY ZERO
# coverage — the exact defect this detector exists to catch (#517 case 5, a MAGNA53 review firing
# on 9m_day2 rows), recreated by the detector itself. INVERTED: each YAML entry now DECLARES its
# own `discriminates_on: [table.column, ...]`, written by whoever writes the predicate, at the
# time they write it. The check becomes declared-vs-mentioned-in-SQL, which FAILS LOUD on a
# missing declaration (`is_population_declaration_missing` /
# `find_undeclared_population_entries`, wired hard into preflight_yaml_dupe_keys.py) instead of
# inferring from a dict and degrading. Declaring is required for every entry whose predicate has
# a FROM clause and isn't COUNT(DISTINCT ...) exempt (`predicate_needs_population_declaration`);
# a date-only predicate has no population to mismatch — same fixed syntactic invariant as
# `is_date_fire_predicate`, which needs no declaration.
#
# The pre-existing 66 entries that predate this requirement are NOT retroactively guessed at —
# guessing a population split without the predicate author's domain knowledge is exactly the kind
# of silent inference this fix replaces. They are named explicitly in
# `POPULATION_DECLARATION_PENDING_MIGRATION` below: a visible backlog, not a clean bill of health.
# 27 entries whose only referenced tables were already covered by the old dict (safe, ALREADY-
# VERIFIED data — not a fresh guess) were backfilled straight into the YAML in the same commit.
#
# Both static checks (regex over predicate_sql text and the entry's own declared list, no DB
# needed) are deliberately narrow: they do not know whether blending a population is a bug or an
# intentional whole-book question (`kill_scale_bands_quarterly_review` is legitimately about the
# whole live book, not one setup — flagging it is still useful, but it must not be silently
# auto-"fixed" or hidden). The check's job is to make the mismatch VISIBLE (with a real breakdown
# of what the predicate counted), not to decide it — same posture as the status-vocabulary lint
# in preflight_yaml_dupe_keys.py.

# Review_ids whose predicate needs a population declaration (`predicate_needs_population_
# declaration` is True) but predate #573 and have not yet been reviewed by someone who knows
# their population — so they are NOT flagged as a NEW gap by `find_undeclared_population_entries`.
# This is the visible backlog, not a clean bill of health: every entry on it is still silently
# uncovered for population-mismatch purposes until it gets a real `discriminates_on:` (or an
# explicit `[]` declaring "reviewed, no split applies") in data_gated_reviews.yaml.
# ⚠ Do NOT add new review_ids here to silence the gate — declare instead. Removing a review_id
# from this list requires it to already carry a real declaration in the YAML, or the
# registry-level check goes red (see test_registry_has_no_undeclared_population_gaps).
POPULATION_DECLARATION_PENDING_MIGRATION: frozenset[str] = frozenset({
    "anticipation_270_shadow_graduation",
    "anticipation_270_calibration_revalidation",
    "conviction_floor_extension",
    "dead_zone_reevaluation",
    "adv_probe_retirement",
    "narrative_theme_discovery_promote_gate",
    "fishhook_v3_first_telemetry_review",
    "fishhook_v3_promotion_check",
    "minute_volume_curves_baseline",
    "flag_proximity_band_calibration",
    "flag_proximity_bypass_hysteresis",
    "rmv_phase2_evaluation",
    "theme_assignment_telemetry_review",
    "drawdown_breaker_active_effectiveness",
    "flag_ma_pin_filter",
    "theme_orphan_sub_mechanism",
    "perplexity_hallucination_keyword_leak",
    "trade_stream_stop_placement_without_orders_row",
    "crmd_naked_position_postmortem_2026_05_14",
    "theme_assignment_sndk_class_refinement",
    "perplexity_sanitizer_verification",
    "vix_ingest_for_p19_sizing",
    "flag_detector_post_breakout_label",
    "phase3_telemetry_coverage_check",
    "phase5_meta_rubric_calibration",
    "catalyst_type_forward_signal",
    "theme_engine_narrative_blindness",
    "theme_as_ep_signal",
    "catalyst_discovery_loop_sequencing",
    "phase6_meta_rubric_gating",
    "catalyst_rubric_quarterly",
    "rel_volume_small_cap_biotech_floor_evidence",
    "theme_axis_boost_reeval",
    "gate_5g_historical_coverage",
    "extraction_pipeline_first_live_run_smoke",
    "rubric_safety_net_yoy_required",
    "yoy_missing_data_quality_investigation",
    "theme_axis_gating_logic",
    "ep_cooldown_resetup_admission",
    "b6_forward_backtest_first_eval",
    "l2_baseline_window_trending_metrics",
    "flag_detector_graduation_evidence_n30",
    "time_stop_9m_day2_effectiveness_n10",
    "intraday_flag_break_signal_n10",
    "intraday_ma_pullback_signal_n10",
    "intraday_undercut_rally_signal_n10",
    "intraday_support_test_signal_n10",
    "decliner_band_bounce_signal_n30",
    "sugar_baby_convergence_backtest_first_eval",
    "intraday_failed_break_signal_n10",
    "partial_exit_hardening_n7_clean_cycles",
    "alpaca_stop_trigger_reliability",
    "orb_entry_stuck_pending_new",
    "wave_c_part2_boost_demotion",
    "chart_vision_axis_shadow_decision",
    "htf_adr_threshold_tune",
    "perplexity_transient_timeout_alert_noise",
    "htf_breakout_paper_graduation",
    "exposure_family_cap_promotion_r2",
    "entry_order_rejections_systematic",
    "b6_gate_inversion_recheck",
    "gap_alignment_331_accrual",
    "tqs_junk_accrual",
    "lane2_narrative_grouping_quality",
    "lane2_seed_birth_calibration",
    "judge_divergence_marginal_high_signal",
})


def is_date_fire_predicate(predicate_sql: str | None) -> bool:
    """True when `predicate_sql` is SQL text with no FROM clause at all — it can only ever be a
    function of the calendar/constants, never real accrued evidence, even though it LOOKS like an
    evidence-gated predicate. `predicate_sql: null` (the documented, honest date-only gate) is NOT
    this class — it never claimed to read data. This catches the dressed-up version."""
    if not predicate_sql or not predicate_sql.strip():
        return False
    return re.search(r"\bFROM\b", predicate_sql, re.IGNORECASE) is None


def predicate_needs_population_declaration(predicate_sql: str | None) -> bool:
    """True when a predicate reads a real table (has a FROM clause) and isn't COUNT(DISTINCT...)
    exempt (see `find_population_mismatch` for why COUNT(DISTINCT...) is exempt) — i.e. it HAS a
    population that could be mismatched, so its YAML entry must declare `discriminates_on`. A
    date-only predicate (`is_date_fire_predicate`) or `predicate_sql: null` never reads a table at
    all, so there is nothing to declare — the same fixed syntactic invariant as that sibling."""
    if not predicate_sql or not predicate_sql.strip():
        return False
    if re.search(r"\bFROM\b", predicate_sql, re.IGNORECASE) is None:
        return False
    if re.search(r"COUNT\(\s*DISTINCT\b", predicate_sql, re.IGNORECASE):
        return False
    return True


def find_population_mismatch(
    predicate_sql: str | None, declared_columns: list[str] | None
) -> list[str]:
    """Return the subset of `declared_columns` (["table.column", ...], exactly as written in the
    entry's own `discriminates_on:`) that the predicate text never actually mentions/filters.

    Declaration is the source of truth (#573, 2026-08-30) — NOT a hand-maintained global
    table->column dict — so an entry that declares nothing yields [] here; that silence is a
    DIFFERENT, louder signal (`is_population_declaration_missing`), never a clean bill of health.
    `declared_columns=None` means "no declaration to check"; `[]` means "declared: reviewed, no
    discriminating column applies here" — both short-circuit to no mismatch, for different
    reasons. `COUNT(DISTINCT ...)` predicates are exempted the same way
    `predicate_needs_population_declaration` exempts them from requiring a declaration at all —
    deduping on a non-discriminating column (e.g. a date) already collapses across whatever
    category would otherwise fan the count out, so an unfiltered category there does not inflate
    anything (verified 2026-08-17: `drawdown_breaker_promotion` / `live_cutover_decision` /
    `rt_admission_recut_post_2r_exits` all read this way and are not bugs)."""
    if not predicate_needs_population_declaration(predicate_sql):
        return []
    if not declared_columns:
        return []
    out: list[str] = []
    for col_tag in declared_columns:
        col = col_tag.split(".", 1)[1] if "." in col_tag else col_tag
        if not re.search(r"\b" + re.escape(col) + r"\b", predicate_sql, re.IGNORECASE):
            out.append(col_tag)
    return out


def is_population_declaration_missing(
    predicate_sql: str | None, declared_columns: list[str] | None
) -> bool:
    """True when a predicate NEEDS a population declaration (reads a real, non-exempt table) and
    the entry carries none at all — `discriminates_on` key absent from YAML, distinct from an
    explicit `[]`. Reports the truth for EVERY such entry, including the acknowledged migration
    backlog (`POPULATION_DECLARATION_PENDING_MIGRATION`) — that backlog list controls whether the
    registry-level hard check (`find_undeclared_population_entries`) fails, not whether this
    runtime flag is honest about coverage."""
    return predicate_needs_population_declaration(predicate_sql) and declared_columns is None


def find_undeclared_population_entries(entries: list[dict]) -> list[str]:
    """Registry-level FAIL-LOUD check (#573): review_ids that need a population declaration, have
    none, and are NOT on the acknowledged `POPULATION_DECLARATION_PENDING_MIGRATION` backlog.
    Non-empty means either a brand-new entry was added without declaring its population, or an
    existing entry was pulled off the migration backlog without actually being given a
    declaration — both are exactly the silent-degradation defect #573 replaces. Wired hard into
    `scripts/preflight_yaml_dupe_keys.py`; pinned by
    `tests/test_review_readiness_sanity.py::test_registry_has_no_undeclared_population_gaps`."""
    out: list[str] = []
    for e in entries:
        if not isinstance(e, dict):
            continue
        if not is_population_declaration_missing(e.get("predicate_sql"), e.get("discriminates_on")):
            continue
        rid = e.get("review_id") or "<no id>"
        if rid not in POPULATION_DECLARATION_PENDING_MIGRATION:
            out.append(rid)
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
        declared_columns = e.get("discriminates_on")
        evidence_flags = {
            "date_fire": is_date_fire_predicate(predicate_sql),
            "population_mismatch": find_population_mismatch(predicate_sql, declared_columns),
            # #573 2026-08-30 — declaration is the source of truth now, not an inferred dict
            # lookup, so a predicate that reads a table but never declared its population must
            # say so LOUDLY rather than read as a clean "population_mismatch: []". True for every
            # such entry, including the acknowledged migration backlog — see
            # POPULATION_DECLARATION_PENDING_MIGRATION for what makes the registry-level check
            # (not this runtime flag) tolerate the backlog.
            "population_undeclared": is_population_declaration_missing(predicate_sql, declared_columns),
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
