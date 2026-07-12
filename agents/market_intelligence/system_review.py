"""
Weekly system self-audit.

Pulls 7 days from every tracking system, aggregates to summary statistics
(the LLM never sees raw rows — that's a token trap), hands the summary to
Claude Sonnet for synthesis, sends a Telegram digest, persists to
mi_system_reviews so next week's run can grade its own prior suggestions.

Entry points:
  run_weekly_review() — called by scheduler and on-demand route.
"""
from __future__ import annotations

import json
import logging
import os
from collections import Counter, defaultdict
from datetime import date, timedelta

import anthropic

from agents.market_intelligence.briefing import send_telegram_message
from agents.market_intelligence.failure_policy import advisory_fail_open
from agents.market_intelligence.db import (
    get_active_cooldowns,
    get_audit_log,
    get_correlation_clusters,
    get_ep_outcomes,
    get_latest_regime,
    get_latest_system_review,
    get_paper_trade_stats,
    get_weekly_theme_churn,
    insert_system_review,
)

logger = logging.getLogger(__name__)

_WINDOW_DAYS = 7
from shared.llm_models import SYSTEM_REVIEW_MODEL as _MODEL
_MAX_TOKENS = 1200

_SYSTEM_PROMPT = """You are Apollo's weekly self-auditor. You review metrics from \
a momentum/EP trading assistant and surface, FACTUALLY, what's working and what \
telemetry anomalies merit a look. You do NOT diagnose bugs or propose code/threshold \
changes — this review repeatedly produced confident-but-WRONG "bugs" and regressive \
"fixes" off telemetry it can't fully interpret (a DESIGNED earnings-override read as an \
"enforcement bug"; an already-hotfixed scan error re-flagged as open). Your job is to \
SURFACE anomalies for the operator to verify, NOT to PRESCRIBE.

Methodology context (NON-NEGOTIABLE — proposals contradicting these get rejected):
- Pradeep Bonde / Qullamaggie momentum doctrine: lose-small / win-big.
  20% win rate × 10R per winner is excellent; win-rate alone is misleading.
  Edge is measured in R-expectancy and profit factor, not pos_rate.
- HOLD WINNERS, stop losers fast. Do NOT propose mandatory partials based
  on gap size — Pradeep methodology lets winners run; auto-partial on
  a +15% gap is a methodology violation regardless of how the math looks.
- Tight defined stop on Day 0; manage via SMA trail + breakeven, not
  time-based exits.
- N=3 trade samples are statistical noise — do not propose changes from
  single-week trade outcomes; require ≥30 closed trades or ≥60 days of
  telemetry for any cohort-driven recommendation.

Rules for flagging anomalies (you SURFACE facts; you do NOT diagnose bugs or prescribe fixes):
- Before proposing a "new" guardrail, check `recent_changes` in the metrics
  JSON. If the change shipped within the last 30 days, do NOT re-propose;
  instead note it shipped and observe whether the metric improved.
- Do NOT speculate on bugs from circumstantial data (e.g. "this loss might
  be a duplicate-exit bug"). Only flag bugs that are SUPPORTED by audit
  events in `audit_errors`. If audit log is silent on a behavior, the
  behavior was nominal.
- Distinguish skipped/blocked alerts from actual trade attempts. If `36`
  EPs were 33 max_positions blocks + 3 actual entries, the cohort is N=3,
  not N=36. Cite the active cohort, not the alert volume.
- An anomaly may be (a) a DESIGNED mechanism (earnings-override admitting a sub-65
  name; conviction-floor flooring gap+catalyst to HIGH; r3 blocking a Day-1 RE-ENTRY
  AFTER a stop; partial-exit retries), (b) ALREADY RESOLVED (a hotfix may have landed
  mid-week — if an error type's count drops to 0 after a date, treat it as likely-resolved,
  NOT open), or (c) KNOWN-IN-FLIGHT (an open task / data-gated review). For EVERY anomaly:
  cite the count, then state it is UNVERIFIED and must be checked against audit ground
  truth + designed-mechanism + resolution status before any action. NEVER assert a bug;
  NEVER propose a fix.

Output exactly this structure, in this order, with these exact section headers:

✅ *Working*
• 3 bullets, each grounded in a specific number from the data

⚠️ *Anomalies to verify* — UNVERIFIED; do NOT act before checking ground truth
• Up to 3 bullets, each grounded in a specific number. State the OBSERVATION only. For
  each, note it may be a designed mechanism / already-resolved / known-in-flight and needs
  verification. NO bug assertions, NO proposed fixes.

🔁 *Last week:*
One sentence: did last week's flagged anomalies persist or clear this week? \
If the relevant metric improved, say so with the delta. If unchanged, assume \
the change was not implemented. Do NOT claim you know whether code was deployed.

Rules:
- No fluff, no filler headers beyond the three above (✅ Working, ⚠️ Anomalies to verify, 🔁 Last week).
- Max 350 words total.
- Every bullet must cite a number from the metrics JSON.
- Keep Telegram Markdown: *bold*, `code`, no tables.
- When `postmortem_best` or `postmortem_worst` is present, weave one concrete insight from each into the ✅/⚠️ sections (e.g. "{ticker}'s exit followed through {pnl}…"). Do not paste the full postmortem — extract the takeaway.
- A CLOSED trade's `skip_reason` is a POST-ENTRY re-entry block (the trade already entered AND exited) — NEVER the entry gate. Do NOT infer "blocked signal traded through" / "block fired but didn't prevent fill" / a missing enforcement from it: a fill-then-reentry-block ordering is enforcement working as designed (#228). The postmortem already labels this explicitly — read its "Post-entry note" line and do not re-cast it as an anomaly.
- When `anomalies.l3_drifts.count > 0`, append a "📉 *Drift:*" line after 🔁 listing up to 3 metrics whose from_band → to_band transition this week (silent during the week, surfaces here only). Use the format `metric_name: from_band→to_band (current vs p50)`. If a transition has `recent_change_hint`, append `— ⚠ may be intentional (improvement landed {hint})` to that line so the operator interprets the drift as deliberate-improvement-settle rather than regression. Do not invent transitions if the count is 0; omit the line entirely.
- `anomalies.l1_invariants` and `anomalies.l2_anomalies` already pinged Telegram during the week — cite their counts in ⚠️ *Anomalies to verify* if non-zero so the user sees the week's invariant/anomaly footprint at a glance.
- The `crypto` field in the metrics is surfaced separately as a deterministic appendix below your output. Do NOT mention crypto in the four sections above — that surface is handled.
- The `mfe_capture` field (W3 winner-harvest KPI) is likewise surfaced as a deterministic appendix. Do NOT restate it in the four sections above, and do NOT propose management/exit changes from it — it is an operator-gated tuning input.
- When `strategy_promotions.checks` is non-empty AND any entry has `next_phase` != null, append a "📈 *Strategy promotion check:*" line after 🔁 listing each non-top-of-ladder strategy on its own indented bullet: `<strategy_id>: <eligible '✓ ready' OR top blocking_reason>` (e.g. `shadow_orb_5m: need 30 paired closed (have 12)`). Skip strategies already at the top of the ladder. Omit the section entirely if every strategy is at top-of-ladder.
- When `shadow_orb.paired_closed_total >= 10`, append a "📐 *Shadow ORB:*" line after 🔁 summarizing 5-min vs 1-min ORB telemetry. Cite `entered` / `no_entry` counts and the top `by_shape` entry's `per_alert_delta` (e.g. "12 5m entries, 4 no-entry; bounce 9m delta +0.4 R over 8 paired"). Note: by-shape deltas are 9M-cohort only — `shape_tag` is NULL on MAGNA53 rows. If `paired_closed_total < 10`, omit the line entirely (insufficient signal).
- When `wick.n_settled >= 10`, append a "🪝 *Wick:*" line after 🔁 summarizing wick-fill telemetry. Cite `n_total` candidates, `fill_rate`, and the gap between `median_fwd_3d_from_high` (filled cohort, conditional drift after fill) and `median_fwd_3d_from_close` (all-settled drift baseline) — the gap is the strategy's actual edge. Format: `12 candidates, 58% fill rate; +1.2% 3d post-fill vs +0.4% baseline drift`. If `n_settled < 10`, omit the line entirely (insufficient signal).
- When `fishhook.n_settled >= 10`, append a "🪝 *Fishhook:*" line after 🔁 summarizing gap-up undercut & reclaim telemetry. Cite `n_total` anchors, `n_settled`, `median_r`, `hit_rate`, and the shallow-vs-deep slice when both have data: `45 anchors, 12 settled; R 1.18, hit 17%; shallow R 1.31 (n=8) vs deep R 0.61 (n=4)`. The shallow-vs-deep gap matters — Stage-0 evidence said deeper drift inverts the edge; if deep starts winning, threshold revisit. If `n_settled < 10`, omit the line entirely.
- The `pending_reviews` field (data-gated "Reviews ready") is surfaced separately as a deterministic appendix below your output (#412 — the titles are actionable and must not be truncated). Do NOT render a Reviews-ready section yourself.
- When `audit_errors.total > 0`, append a "🔴 *Silent failures (7d):*" section after 🔁 listing each `top_types` entry on its own line: `<event_type> ×<count> (last seen <last_seen>, <days_ago>d ago)`. **Use `days_ago` to judge live-vs-resolved: if a type's `days_ago` is STALE relative to the 7-day window (it stopped firing days back), label it LIKELY-RESOLVED and do NOT treat it as a live concern — a mid-week hotfix shows up exactly as a count that went silent (e.g. ep_scan_failed last 5/26). Only call a type live-concerning when `days_ago` is small (fired in the last day or two).** These are non-fatal errors caught by try/except in jobs that didn't crash hard. If `audit_errors.total == 0`, omit the section entirely.
- When `strategy_promotions.checks` includes a strategy with `eligible=false` AND its top blocking_reason references a 0-count metric (e.g. "have 0"), the line MUST include the diagnostic context from `metrics.cohort_breakdown` if present (e.g. `shadow_orb_5m: have 0 paired closed (1 shadow vs 3 live, zero overlap)`). The 0-count number alone forces a follow-up question; the breakdown answers it inline.
"""


async def run_weekly_review(window_days: int = _WINDOW_DAYS) -> dict:
    """Execute the weekly review: gather, aggregate, synthesize, persist, send."""
    from agents.market_intelligence.collector import et_today
    today = et_today()
    window_start = today - timedelta(days=window_days)

    metrics = await _gather_and_aggregate(window_start, today, window_days)
    prior = await get_latest_system_review(window_days=window_days)

    summary = await _synthesize(metrics, prior)

    review = {
        "review_date": today.isoformat(),
        "window_days": window_days,
        "regime": metrics.get("regime", {}).get("current"),
        "summary": summary,
        "metrics": metrics,
        # legacy key/column name — now holds last week's ⚠️ anomalies for the 🔁 check
        "suggestions": _extract_anomalies(summary),
    }
    await insert_system_review(review)

    header = f"🧠 *Weekly System Review — {window_start.strftime('%b')} {window_start.day}–{today.day}*"
    regime_label = metrics.get("regime", {}).get("current") or "Unknown"
    message = f"{header}\n*Regime:* {regime_label}\n\n{summary}"

    # Losers post-mortem (#76, 2026-05-11) — deterministic appendix above
    # crypto so the methodology-tuning signals land near the top of the
    # appendix block, right where the eye looks after reading the LLM
    # summary. Empty string if no losing trades in window (skipped clean).
    loser_section = _format_loser_section(metrics.get("loser_breakdown") or {})
    if loser_section:
        message = f"{message}\n\n{loser_section}"

    # W3 winner-harvest KPI (#306, 2026-07-05) — deterministic appendix right
    # after the losers post-mortem: the two sides of the expectancy leak
    # (entry-mechanics losses · management giveback) land adjacent.
    try:
        mfe_section = _format_mfe_capture_section(metrics.get("mfe_capture") or {})
        if mfe_section:
            message = f"{message}\n\n{mfe_section}"
    except Exception:
        logger.exception("mfe capture section render failed")

    # Data-gated Reviews-ready (#412, 2026-07-06) — deterministic so actionable
    # review titles can't be LLM-truncated (the "ADV" nit); was an LLM-prompt section.
    try:
        pr_section = _format_pending_reviews_section(metrics.get("pending_reviews") or {})
        if pr_section:
            message = f"{message}\n\n{pr_section}"
    except Exception:
        logger.exception("pending-reviews section render failed")

    # Holistic judge weekly roll-up (#240/#249) — replaced the retired #200
    # theme-gated + #201 fire-panel advisory sections (judge load-bearing 6/10).
    try:
        judge_section = _format_judge_section(metrics.get("judge_weekly") or {})
        if judge_section:
            message = f"{message}\n\n{judge_section}"
    except Exception:
        logger.exception("judge section render failed")

    # Missed-opportunity appendix (Step 3 of #missed-EP-tracking, 2026-05-11).
    # Top winners we didn't enter + per-skip-reason roll-up. Tells the
    # methodology-tuning side which filter bled the most upside in the window.
    try:
        from agents.market_intelligence.missed_outcomes import format_missed_section_for_weekly
        missed_section = format_missed_section_for_weekly(
            metrics.get("missed_opportunities") or {}
        )
        if missed_section:
            message = f"{message}\n\n{missed_section}"
    except Exception:
        logger.exception("missed_opportunities section render failed")

    # Crypto RS readiness — deterministic appendix (not LLM-interpreted).
    # Surfaces "ready to flip" verdict so the user doesn't forget about
    # the shadow-mode module accumulating in the background.
    crypto_section = _format_crypto_section(metrics.get("crypto") or {})
    if crypto_section:
        message = f"{message}\n\n{crypto_section}"

    # Kill/scale band verdict (#275) — a SECTION of the weekly digest (not a new
    # surface). SURFACES the live-money band + numbers + any active override; the
    # mechanical evaluation (the weekly layer of safeguards.md condition #1).
    try:
        from agents.market_intelligence.kill_scale_bands import band_digest_section
        band_lines = await band_digest_section("live")
        if band_lines:
            message = f"{message}\n" + "\n".join(band_lines)
    except Exception:
        logger.exception("kill/scale band section render failed")

    # Cost envelope (FL-6 / #378 S-C, 2026-07-12) — the deterministic MTD-spend line: the
    # ONE routine surface that completes FL-6 (the /status board + budget alert already exist).
    try:
        spend_section = await _spend_envelope_section()
        if spend_section:
            message = f"{message}\n\n{spend_section}"
    except Exception:
        logger.exception("spend-envelope section render failed")

    # Replay-regression (#302) — the live R-dist beside the #268b calibration card; the P6
    # "weekly report" input (b) to the quarterly band review. SURFACES + persists a snapshot;
    # never verdicts (the divergence statistic isn't valid at low N). persist=True so the
    # quarterly review reads the accruing distribution over time.
    try:
        from agents.market_intelligence.replay_regression import run_replay_regression
        rr = await run_replay_regression("live", persist=True)
        if rr.get("lines"):
            message = f"{message}\n" + "\n".join(rr["lines"])
    except Exception:
        logger.exception("replay-regression section render failed")

    await send_telegram_message(message)

    logger.info(f"Weekly review complete: {window_start}..{today}")
    return review


# ── Gather + aggregate ────────────────────────────────────────────────────────


async def _gather_and_aggregate(
    window_start: date, today: date, window_days: int
) -> dict:
    """Pull from every tracking table, aggregate to summary stats only."""
    ep = await _aggregate_ep_outcomes(window_days)
    nine_m = await _aggregate_9m_outcomes(window_days)
    paper = await _aggregate_paper_trades(window_start)
    errors = await _aggregate_audit_errors(window_days)
    churn = await _aggregate_theme_churn(window_days)
    cooldowns = await _aggregate_cooldowns(window_start)
    clusters = await _aggregate_clusters(today)
    regime = await _aggregate_regime(window_days)
    postmortems = await _aggregate_trade_postmortems(window_start)
    loser_breakdown = await _aggregate_loser_breakdown(window_start)
    anomalies = await _aggregate_anomalies(window_days)
    crypto = await _aggregate_crypto_readiness(window_days)
    shadow_orb = await _aggregate_shadow_orb_outcomes(window_days)
    wick = await _aggregate_wick_outcomes(window_days)
    fishhook = await _aggregate_fishhook_outcomes(window_days)
    strategy_promotions = await _aggregate_promotion_checks()
    pending_reviews = await _aggregate_pending_reviews(today)
    missed_opps = await _aggregate_missed_opportunities(window_days)
    news_quality = await _aggregate_news_source_quality(window_days)
    judge_weekly = await _aggregate_judge_decisions(window_days)
    mfe_capture = await _aggregate_mfe_capture(window_start)

    return {
        "window": {"start": window_start.isoformat(), "end": today.isoformat(), "days": window_days},
        "ep_outcomes": ep,
        "nine_m_outcomes": nine_m,
        "paper_trades": paper,
        "audit_errors": errors,
        "theme_churn": churn,
        "cooldowns": cooldowns,
        "clusters": clusters,
        "regime": regime,
        "anomalies": anomalies,
        "postmortem_best": postmortems.get("best"),
        "postmortem_worst": postmortems.get("worst"),
        "loser_breakdown": loser_breakdown,
        "crypto": crypto,
        "shadow_orb": shadow_orb,
        "wick": wick,
        "fishhook": fishhook,
        "strategy_promotions": strategy_promotions,
        "pending_reviews": pending_reviews,
        "missed_opportunities": missed_opps,
        "news_source_quality": news_quality,
        "judge_weekly": judge_weekly,
        "mfe_capture": mfe_capture,
    }


async def _aggregate_news_source_quality(window_days: int) -> dict:
    """Roll up per-source quality (coverage/density/attribution) for the
    weekly window + drift detection vs trailing baseline. Surfaces
    silent-quality-degradation per 2026-05-21 user-stated discipline."""
    try:
        from agents.market_intelligence.news_source_quality import (
            collect_source_stats, detect_drift,
        )
        from agents.market_intelligence.collector import et_today
        today_d = et_today()
        current_start = today_d - timedelta(days=window_days - 1)
        current = await collect_source_stats(current_start, today_d)
        drift = await detect_drift()
        return {
            "current_stats": current,
            "drift_events": drift.get("drift_events") or [],
            "current_window": drift.get("current_window"),
            "baseline_window": drift.get("baseline_window"),
        }
    except Exception:
        logger.exception("news_source_quality aggregator failed")
        return {"current_stats": {}, "drift_events": []}


async def _aggregate_missed_opportunities(window_days: int) -> dict:
    """Top missed EPs in the window + per-skip-reason roll-up. Surfaces
    opportunity cost so the weekly digest can flag filters that bled the
    most upside (e.g. cooldown skipped 4 trades that ran >30%)."""
    try:
        from agents.market_intelligence.missed_outcomes import aggregate_missed_for_weekly
        return await aggregate_missed_for_weekly(window_days=window_days)
    except Exception:
        logger.exception("missed_opportunities aggregator failed")
        return {"window_days": window_days, "top_winners": [], "by_category": []}


# _aggregate_theme_gated_divergence (#200) removed 2026-06-10 (#249) — the judge
# (ADR 0011) owns the theme axis; theme_gated_* columns are frozen historical.


async def _aggregate_judge_decisions(window_days: int) -> dict:
    """Holistic judge weekly roll-up (#240/#249) — replaced the retired #200/#201
    advisory sections (theme-gated divergence + fire panel) when the judge went
    load-bearing 2026-06-10. DB ground truth from mi_ep_alerts judge columns
    (never in-process state): how many alerts the judge graded, the ▲/▼ split,
    fail-open count (judge_tier NULL = fell back to floor), and the judge's
    fire-axes distribution (empty axes = judge saw no fire on any axis).
    """
    from agents.market_intelligence.db import get_pool
    from agents.market_intelligence.collector import et_today
    today_d = et_today()
    window_start = today_d - timedelta(days=window_days)
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT
                    COUNT(*)::INT AS total,
                    COUNT(*) FILTER (WHERE judge_tier IS NOT NULL)::INT AS judged,
                    COUNT(*) FILTER (WHERE judge_direction = 'promote')::INT AS promotes,
                    COUNT(*) FILTER (WHERE judge_direction = 'demote')::INT AS demotes,
                    COUNT(*) FILTER (WHERE grade_engine_authority = 'judge')::INT AS judge_driven,
                    COUNT(*) FILTER (WHERE grade_engine_authority = 'fallback')::INT AS fallbacks,
                    COUNT(*) FILTER (WHERE fire_axes IS NOT NULL
                                       AND fire_axes <> '{}')::INT AS fire_seen,
                    COUNT(*) FILTER (WHERE fire_axes = '{}')::INT AS no_fire
                FROM mi_ep_alerts
                WHERE alert_date >= $1
                  AND COALESCE(source, 'live') = 'live'
            """, window_start)
        return {
            "total": row["total"], "judged": row["judged"],
            "promotes": row["promotes"], "demotes": row["demotes"],
            "judge_driven": row["judge_driven"], "fallbacks": row["fallbacks"],
            "fire_seen": row["fire_seen"], "no_fire": row["no_fire"],
            "window_days": window_days,
        }
    except Exception:
        logger.exception("judge_decisions aggregator failed")
        return {"total": 0, "judged": 0, "window_days": window_days}


@advisory_fail_open(
    default=lambda: {"ready": [], "pending_count": 0, "pending_summary": []},
    label="pending_reviews aggregator")
async def _aggregate_pending_reviews(today: date) -> dict:
    """Walk data_gated_reviews.yaml; surface entries whose data threshold
    has flipped to ready. Surfaces in the Sunday digest as a 📅 line.
    (#259 exemplar: policy-only except block → declared via decorator.)"""
    from agents.market_intelligence.data_gated_reviews import check_pending_reviews
    return await check_pending_reviews(today)


async def _aggregate_promotion_checks() -> dict:
    """Per-strategy promotion eligibility snapshot for the weekly digest.

    Returns one entry per registered strategy with current phase, model,
    eligibility, headline metric, and blocking reasons (if any). The
    weekly review prompt cites this so the user sees which strategies
    are accumulating signal vs ready to graduate.
    """
    try:
        from agents.market_intelligence.strategies.promotion import check_all_strategies
        verdicts = await check_all_strategies()
    except Exception:
        logger.exception("promotion aggregator failed")
        return {"checks": []}
    out: list[dict] = []
    for v in verdicts:
        out.append({
            "strategy_id": v.strategy_id,
            "current_phase": v.current_phase,
            "next_phase": v.next_phase,
            "model": v.model,
            "eligible": v.eligible,
            "metrics": v.metrics,
            "blocking_reasons": v.blocking_reasons[:3],
        })
    return {"checks": out}


def _token_variants(token: str) -> tuple[str, ...]:
    """Return search variants for a metric-name token to absorb plural/singular
    variance ('cooldowns' should match 'cooldown' in change text). Conservative —
    only strips a trailing 's' when removal leaves ≥4 chars to avoid over-
    matching short tokens.
    """
    if len(token) >= 5 and token.endswith("s"):
        return (token, token[:-1])
    return (token,)


def _match_drift_to_recent_changes(metric_key: str, recent_changes: list[str]) -> str | None:
    """Detect whether a drifting metric's subsystem has a recent improvement
    in CLAUDE.md (#112, 2026-05-24). The audit layer can't distinguish good
    drift (deliberate improvement settling into new norm) from regression;
    cross-referencing the metric name against recent change descriptions
    gives the operator the context to interpret correctly.

    Tightened post-/simplify (2026-05-24): a single-token match on short
    common words like "entry" or "rate" produced false positives — almost
    every change in the codebase mentions "entry" in some form. Require:
      (a) the FIRST token (subsystem prefix) to match, OR
      (b) ≥2 tokens to match in the same change line.

    Tokens absorb plural/singular variance via `_token_variants`
    ('cooldowns' → ['cooldowns', 'cooldown']).

    Returns the matching change entry (date + first line) or None.
    """
    if not metric_key or not recent_changes:
        return None
    tokens = [t.lower() for t in metric_key.split("_") if len(t) >= 4]
    if not tokens:
        return None

    def _token_in(token: str, hay: str) -> bool:
        return any(v in hay for v in _token_variants(token))

    first_token = tokens[0]
    for change in recent_changes:
        change_lower = change.lower()
        if _token_in(first_token, change_lower):
            return change
        # Fallback: require ≥2 token hits in the same change
        hits = sum(1 for t in tokens if _token_in(t, change_lower))
        if hits >= 2:
            return change
    return None


async def _aggregate_anomalies(days: int) -> dict:
    """Roll up the week's L1/L2/L3 anomaly_detected audit rows.

    L1/L2 already pinged Telegram during the week. L3 drift was silent —
    Sunday digest is the only place it surfaces. Body shape mirrors what
    system_audit._emit_l1/l2/l3 writes.

    Each L3 drift transition is annotated with `recent_change_hint` when
    the metric name matches a recent CLAUDE.md change — distinguishes
    deliberate-improvement drift from regression (#112).
    """
    since_hours = days * 24
    rows = await get_audit_log(
        limit=500, since_hours=since_hours, event_type="anomaly_detected"
    )
    by_level: dict[int, list[dict]] = {1: [], 2: [], 3: []}
    for r in rows:
        raw = r.get("detail") or "{}"
        try:
            body = json.loads(raw) if isinstance(raw, str) else raw
        except (json.JSONDecodeError, TypeError):
            continue
        lvl = int(body.get("level") or 0)
        if lvl not in by_level:
            continue
        by_level[lvl].append({
            "key": body.get("key"),
            "current": body.get("current"),
            "p50": body.get("baseline_p50"),
            "from_band": body.get("from_band"),
            "to_band": body.get("to_band"),
        })

    def _summarize(items: list[dict]) -> dict:
        keys = Counter(i["key"] for i in items if i.get("key"))
        return {
            "count": len(items),
            "by_key": [{"key": k, "count": c} for k, c in keys.most_common(8)],
        }

    # Recent CLAUDE.md change context for drift-vs-improvement disambiguation (#112).
    try:
        from agents.market_intelligence.system_audit import _recent_changes_context
        recent_changes = _recent_changes_context(limit=7)
    except Exception as e:
        logger.warning(f"Recent-changes context fetch failed: {e}")
        recent_changes = []

    l3_drifts = []
    for i in by_level[3]:
        if i.get("from_band") == i.get("to_band"):
            continue
        item = {
            "key": i["key"],
            "from_band": i.get("from_band"),
            "to_band": i.get("to_band"),
            "current": i.get("current"),
            "p50": i.get("p50"),
        }
        hint = _match_drift_to_recent_changes(i["key"] or "", recent_changes)
        if hint:
            item["recent_change_hint"] = hint
        l3_drifts.append(item)

    return {
        "l1_invariants": _summarize(by_level[1]),
        "l2_anomalies": _summarize(by_level[2]),
        "l3_drifts": {
            "count": len(l3_drifts),
            "transitions": l3_drifts[:10],
        },
    }


@advisory_fail_open(default=dict, label="mfe_capture aggregator")
async def _aggregate_mfe_capture(window_start: date) -> dict:
    """W3 management KPI (#306 STEP-0 → weekly KPI, 2026-07-05; read-only).

    Aggregate MFE capture on closed partial-taken trades: total_pnl kept vs
    the peak excursion (highest_price_seen − entry_price) × entry_shares.
    Cohort is CUMULATIVE (not window-sliced) so the number stays directly
    comparable to the STEP-0 baseline — 18% on N=10, 2026-07-04
    (docs/analysis/w3_winner_harvest_step0_2026-07-04.md); the v2.0 tier-one
    bar is >50%. Trades that CLOSED inside the window are listed as the
    week's new datapoints. pnl_attribution IS NULL excludes bug-attributable
    rows (methodology KPI, not account accounting). highest_price_seen is a
    post-fill high-water mark — it can UNDERSTATE MFE, so true capture is if
    anything worse than shown. SURFACES only; any tune is trade-state
    (CHANGE_PROCESS + operator sign-off).
    """
    from agents.market_intelligence.db import get_pool

    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT ticker, account_mode, total_pnl,
                   (highest_price_seen - entry_price) * entry_shares AS mfe_dollars,
                   (closed_at AT TIME ZONE 'America/New_York')::date AS closed_et
            FROM mi_live_trades
            WHERE status = 'closed'
              AND partial_taken = TRUE
              AND pnl_attribution IS NULL
              AND total_pnl IS NOT NULL
              AND highest_price_seen IS NOT NULL
              AND entry_price IS NOT NULL
              AND entry_shares IS NOT NULL
              AND (highest_price_seen - entry_price) * entry_shares > 0
            ORDER BY closed_at DESC
        """)

    if not rows:
        return {"n": 0}

    mfe_total = sum(float(r["mfe_dollars"]) for r in rows)
    kept_total = sum(float(r["total_pnl"]) for r in rows)
    window_closes = [
        {
            "ticker": r["ticker"],
            "account_mode": r["account_mode"],
            "capture_pct": round(float(r["total_pnl"]) / float(r["mfe_dollars"]) * 100),
            "kept": round(float(r["total_pnl"])),
            "mfe": round(float(r["mfe_dollars"])),
        }
        for r in rows
        if r["closed_et"] and r["closed_et"] >= window_start
    ]
    return {
        "n": len(rows),
        "mfe_dollars": round(mfe_total),
        "kept_dollars": round(kept_total),
        "capture_pct": round(kept_total / mfe_total * 100),
        "bar_pct": 50,  # v2.0 tier-one bar (roadmap PART II)
        "window_closes": window_closes[:5],
    }


async def _aggregate_trade_postmortems(window_start: date) -> dict:
    """
    Pick the window's best and worst closed trade (by total_pnl) and generate
    one-paragraph postmortem narratives. Sources mi_live_trades when available,
    falls back to mi_paper_trades. Returns {} if neither has closed trades.
    """
    from agents.market_intelligence.db import get_pool
    from agents.market_intelligence.postmortem import generate_postmortem_narrative

    pool = await get_pool()
    async with pool.acquire() as conn:
        # pnl_attribution IS NULL: exclude bug-attributable trades from
        # methodology evaluation. Real P&L still hit the account; the weekly
        # postmortem is about strategy fitness, not account safety.
        rows = await conn.fetch("""
            SELECT ticker, alert_date, total_pnl FROM mi_live_trades
            WHERE status = 'closed' AND alert_date >= $1 AND total_pnl IS NOT NULL
              AND pnl_attribution IS NULL
            ORDER BY alert_date DESC
        """, window_start)
        if not rows:
            rows = await conn.fetch("""
                SELECT ticker, alert_date, total_pnl FROM mi_paper_trades
                WHERE status = 'closed' AND alert_date >= $1 AND total_pnl IS NOT NULL
                ORDER BY alert_date DESC
            """, window_start)

    if not rows:
        return {}

    best = max(rows, key=lambda r: float(r["total_pnl"]))
    worst = min(rows, key=lambda r: float(r["total_pnl"]))

    out: dict = {}
    try:
        out["best"] = {
            "ticker": best["ticker"],
            "alert_date": best["alert_date"].isoformat(),
            "pnl": round(float(best["total_pnl"]), 2),
            "narrative": await generate_postmortem_narrative(
                best["ticker"], best["alert_date"]
            ),
        }
    except Exception as e:
        logger.warning(f"Weekly postmortem (best) failed: {e}")
    if worst["ticker"] != best["ticker"] or worst["alert_date"] != best["alert_date"]:
        try:
            out["worst"] = {
                "ticker": worst["ticker"],
                "alert_date": worst["alert_date"].isoformat(),
                "pnl": round(float(worst["total_pnl"]), 2),
                "narrative": await generate_postmortem_narrative(
                    worst["ticker"], worst["alert_date"]
                ),
            }
        except Exception as e:
            logger.warning(f"Weekly postmortem (worst) failed: {e}")
    return out


from agents.market_intelligence.prose_markers import NEGATIVE_CATALYST_MARKERS_BASE

# Post-mortem loser grading adds retrospective signals (litigation language,
# "or catalyst" tail) that the live EP downgrade gate intentionally doesn't fire on.
_LOSER_NEGATIVE_PROSE_MARKERS = NEGATIVE_CATALYST_MARKERS_BASE + (
    "no specific news or catalyst",
    "class action",
    "lawsuit",
)


async def _aggregate_loser_breakdown(window_start: date) -> dict:
    """Per-loser systematic post-mortem for the weekly digest (#76, 2026-05-11).

    For each closed losing trade in the window, joins to mi_ep_alerts +
    mi_orb_shadow_trades + mi_audit_log to surface methodology-tuning
    signals invisible in aggregate P&L: catalyst-prose vs grade mismatch,
    1-min vs 5-min ORB comparison, gap-through severity, time-to-stop,
    re-entry compound-loss pattern.

    Returns {"losers": [...], "aggregates": {...}}. Empty dict when no
    losing closed trades in window.
    """
    from agents.market_intelligence.db import get_pool

    pool = await get_pool()
    async with pool.acquire() as conn:
        # pnl_attribution IS NULL: exclude bug-attributable trades. The
        # loser breakdown is methodology-tuning telemetry — counting a
        # bug-induced loss as a methodology miss would lead to false fixes.
        losers = await conn.fetch("""
            SELECT
                t.id, t.ticker, t.alert_date, t.signal_type, t.entry_attempt,
                t.account_mode, t.total_pnl, t.entry_price, t.stop_price,
                t.orb_high, t.orb_low, t.filled_at, t.closed_at, t.exits,
                a.ep_score, a.catalyst_quality, a.catalyst AS catalyst_prose,
                a.pm_rvol, a.gap_pct
            FROM mi_live_trades t
            LEFT JOIN mi_ep_alerts a
                ON a.ticker = t.ticker AND a.alert_date = t.alert_date
            WHERE t.status = 'closed'
              AND t.alert_date >= $1
              AND t.total_pnl < 0
              AND t.pnl_attribution IS NULL
            ORDER BY t.total_pnl ASC
        """, window_start)

        if not losers:
            return {}

        # 5-min ORB shadow for the same (ticker, alert_date) pairs.
        shadow_rows = await conn.fetch("""
            SELECT ticker, alert_date,
                   orb_high::numeric AS s5_orb_high,
                   orb_low::numeric AS s5_orb_low,
                   status AS s5_status,
                   skip_reason AS s5_skip_reason
            FROM mi_orb_shadow_trades
            WHERE bar_size_minutes = 5
              AND alert_date >= $1
        """, window_start)
        shadow_idx = {
            (r["ticker"], r["alert_date"]): dict(r) for r in shadow_rows
        }

        # Earnings-boost audit events keyed by ticker+alert_date.
        boost_rows = await conn.fetch("""
            SELECT summary, (created_at AT TIME ZONE 'America/New_York')::date AS et_date
            FROM mi_audit_log
            WHERE event_type = 'catalyst_earnings_boost'
              AND created_at::date >= $1
        """, window_start)
        # Summary format: "MNDY: routine → strong (earnings_day, source=...)"
        boosted: set[tuple] = set()
        for r in boost_rows:
            summary = r["summary"] or ""
            tick = summary.split(":")[0].strip()
            if tick:
                boosted.add((tick, r["et_date"]))

    def _negative_prose(prose: str | None) -> list[str]:
        if not prose:
            return []
        lower = prose.lower()
        hits = []
        for marker in _LOSER_NEGATIVE_PROSE_MARKERS:
            if marker in lower:
                hits.append(marker)
        return hits

    losers_out: list[dict] = []
    n_blocked_by_5m = 0
    n_wider_stop_5m = 0
    n_prose_mismatch = 0
    n_fast_stop = 0
    n_compound_attempt2 = 0
    gap_through_cents: list[float] = []

    for row in losers:
        trade = dict(row)
        ticker = trade["ticker"]
        alert_d = trade["alert_date"]

        # Parse exits[] for stop fill details.
        exits = trade["exits"]
        if isinstance(exits, str):
            try:
                exits = json.loads(exits)
            except Exception as e:
                logger.debug(f"exits[] JSON parse failed for {ticker} {alert_d}: {e}")
                exits = []
        if not isinstance(exits, list):
            exits = []
        # Pair the stop with its OWN attempt. The trade's filled_at reflects
        # the CURRENT (latest) attempt's fill — so for time-to-stop and
        # gap-through we want the stop_hit that BELONGS to that attempt,
        # not attempt 1's stop on a re-entered trade. exits[] is chronological;
        # the last stop_hit corresponds to the most recent attempt and
        # therefore pairs with the current filled_at.
        stop_hits = [e for e in exits if e.get("reason") == "stop_hit"]
        last_stop = stop_hits[-1] if stop_hits else None

        # Gap-through severity: fill price vs stop price (positive = past stop).
        stop_price = float(trade["stop_price"]) if trade.get("stop_price") else None
        gap_through_dollars: float | None = None
        if last_stop and stop_price:
            try:
                gap_through_dollars = round(
                    float(stop_price) - float(last_stop.get("price") or 0), 4
                )
                if gap_through_dollars > 0:
                    gap_through_cents.append(gap_through_dollars)
            except Exception as e:
                logger.debug(f"Gap-through calc failed for {ticker} {alert_d}: {e}")

        # Time-to-stop: filled_at → matching attempt's stop_hit time.
        time_to_stop_min: float | None = None
        if last_stop and trade.get("filled_at"):
            try:
                from datetime import datetime as _dt
                ts_raw = last_stop.get("time")
                if ts_raw:
                    ts = _dt.fromisoformat(ts_raw.replace("Z", "+00:00")) if isinstance(ts_raw, str) else ts_raw
                    if ts.tzinfo is None:
                        from datetime import timezone as _tz
                        ts = ts.replace(tzinfo=_tz.utc)
                    fa = trade["filled_at"]
                    if fa.tzinfo is None:
                        from datetime import timezone as _tz
                        fa = fa.replace(tzinfo=_tz.utc)
                    time_to_stop_min = round((ts - fa).total_seconds() / 60.0, 1)
                    if time_to_stop_min < 10:
                        n_fast_stop += 1
            except Exception as e:
                logger.debug(f"Time-to-stop calc failed for {ticker} {alert_d}: {e}")

        # Catalyst prose vs grade.
        prose_markers = _negative_prose(trade.get("catalyst_prose"))
        earnings_boosted = (ticker, alert_d) in boosted
        # Mismatch flag: graded strong but prose has negative markers AND
        # no earnings backstop fired. The earnings boost is a legitimate
        # reason for "strong" without specific-news prose, so excluding
        # boosted tickers avoids false positives (MNDY 5/11 class).
        prose_mismatch = (
            trade.get("catalyst_quality") == "strong"
            and bool(prose_markers)
            and not earnings_boosted
        )
        if prose_mismatch:
            n_prose_mismatch += 1

        # 5-min ORB comparison.
        s5 = shadow_idx.get((ticker, alert_d))
        s5_verdict = "no_shadow_data"
        if s5:
            s5_status = (s5.get("s5_status") or "").lower()
            if s5_status == "gate_blocked":
                s5_verdict = "would_block"
                n_blocked_by_5m += 1
            elif s5.get("s5_orb_low") is not None and trade.get("orb_low") is not None:
                if float(s5["s5_orb_low"]) + 0.01 < float(trade["orb_low"]):
                    s5_verdict = "wider_stop"
                    n_wider_stop_5m += 1
                else:
                    s5_verdict = "similar_stop"
            else:
                s5_verdict = "shadow_no_levels"

        # Compound-loss check: if attempt 2 exists, are the two stop losses
        # within 15% of each other (i.e., paid the same loss twice)?
        is_compound = False
        if int(trade.get("entry_attempt") or 1) >= 2:
            stop_hits = [e for e in exits if e.get("reason") == "stop_hit"]
            if len(stop_hits) >= 2:
                p1 = float(stop_hits[0].get("pnl") or 0)
                p2 = float(stop_hits[1].get("pnl") or 0)
                if p1 < 0 and p2 < 0:
                    ratio = abs((p2 - p1) / p1) if p1 != 0 else 1.0
                    if ratio < 0.15:
                        is_compound = True
                        n_compound_attempt2 += 1

        losers_out.append({
            "ticker": ticker,
            "alert_date": alert_d.isoformat(),
            "signal_type": trade.get("signal_type"),
            "account_mode": trade.get("account_mode"),
            "entry_attempt": int(trade.get("entry_attempt") or 1),
            "total_pnl": round(float(trade["total_pnl"]), 2),
            "entry_price": float(trade["entry_price"]) if trade.get("entry_price") else None,
            "stop_price": stop_price,
            "ep_score": float(trade["ep_score"]) if trade.get("ep_score") else None,
            "catalyst_quality": trade.get("catalyst_quality"),
            "earnings_boost_fired": earnings_boosted,
            "prose_negative_markers": prose_markers,
            "prose_mismatch": prose_mismatch,
            "orb1_low": float(trade["orb_low"]) if trade.get("orb_low") else None,
            "orb1_high": float(trade["orb_high"]) if trade.get("orb_high") else None,
            "orb5_low": float(s5["s5_orb_low"]) if s5 and s5.get("s5_orb_low") is not None else None,
            "orb5_high": float(s5["s5_orb_high"]) if s5 and s5.get("s5_orb_high") is not None else None,
            "orb5_verdict": s5_verdict,
            "orb5_skip_reason": s5.get("s5_skip_reason") if s5 else None,
            "gap_through_dollars": gap_through_dollars,
            "time_to_stop_min": time_to_stop_min,
            "is_compound_loss": is_compound,
        })

    n = len(losers_out)
    total_loss = sum(L["total_pnl"] for L in losers_out)
    aggregates = {
        "n_losers": n,
        "total_loss": round(total_loss, 2),
        # Raw counts surfaced alongside pcts so the formatter can switch to
        # "X/N" form at low N (single-trade "100%" reads as statistically
        # significant when it's literally one trade — see #110).
        "n_5m_would_block": n_blocked_by_5m,
        "n_5m_wider_stop": n_wider_stop_5m,
        "n_prose_mismatch": n_prose_mismatch,
        "n_fast_stop_lt_10min": n_fast_stop,
        "pct_5m_would_block": round(100.0 * n_blocked_by_5m / n, 1) if n else 0.0,
        "pct_5m_wider_stop": round(100.0 * n_wider_stop_5m / n, 1) if n else 0.0,
        "pct_prose_mismatch": round(100.0 * n_prose_mismatch / n, 1) if n else 0.0,
        "pct_fast_stop_lt_10min": round(100.0 * n_fast_stop / n, 1) if n else 0.0,
        "n_compound_attempt2": n_compound_attempt2,
        "median_gap_through_dollars": (
            round(sorted(gap_through_cents)[len(gap_through_cents) // 2], 4)
            if gap_through_cents else None
        ),
    }
    return {"losers": losers_out, "aggregates": aggregates}


async def _aggregate_ep_outcomes(days: int) -> dict:
    rows = await get_ep_outcomes(days_back=days)
    by_tier: dict[str, dict] = defaultdict(lambda: {"total": 0, "green": 0, "fwd_1w_sum": 0.0, "fwd_1w_n": 0})
    by_catalyst: dict[str, dict] = defaultdict(lambda: {"total": 0, "green": 0})
    trade_status_counts: Counter = Counter()
    for r in rows:
        tier = r.get("score_tier") or "unknown"
        catalyst = r.get("catalyst_quality") or "unknown"
        fwd = r.get("fwd_1w_pct")
        green = fwd is not None and fwd > 0
        by_tier[tier]["total"] += 1
        by_catalyst[catalyst]["total"] += 1
        trade_status_counts[r.get("trade_status") or "unknown"] += 1
        if green:
            by_tier[tier]["green"] += 1
            by_catalyst[catalyst]["green"] += 1
        if fwd is not None:
            by_tier[tier]["fwd_1w_sum"] += float(fwd)
            by_tier[tier]["fwd_1w_n"] += 1
    return {
        "total": len(rows),
        "by_tier": {t: _finalize_bucket(b) for t, b in by_tier.items()},
        "by_catalyst": {c: _finalize_bucket(b) for c, b in by_catalyst.items()},
        "trade_status": dict(trade_status_counts),
    }


async def _aggregate_9m_outcomes(days: int) -> dict:
    # 9M outcomes live in mi_signal_outcomes with signal_type='9m_ep'.
    # Reuse get_ep_outcomes shape by querying the joined table inline via the
    # audit log? No — simpler: reuse the history endpoint + outcomes join.
    from agents.market_intelligence.db import get_pool
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT a.ticker, a.alert_date, a.is_anticipation,
                   o.fwd_1d_pct, o.fwd_1w_pct
            FROM mi_9m_ep_alerts a
            LEFT JOIN mi_signal_outcomes o
                ON o.signal_type = '9m_ep'
                AND o.signal_date = a.alert_date
                AND o.identifier = a.ticker
            WHERE a.alert_date >= CURRENT_DATE - $1::int
        """, days)
    total = len(rows)
    with_outcome = [r for r in rows if r["fwd_1w_pct"] is not None]
    green = sum(1 for r in with_outcome if r["fwd_1w_pct"] > 0)
    avg_1w = (sum(float(r["fwd_1w_pct"]) for r in with_outcome) / len(with_outcome)) if with_outcome else None
    return {
        "total": total,
        "with_outcome": len(with_outcome),
        "green": green,
        "win_rate": (green / len(with_outcome)) if with_outcome else None,
        "avg_fwd_1w_pct": round(avg_1w, 2) if avg_1w is not None else None,
    }


async def _aggregate_paper_trades(window_start: date) -> dict:
    all_rows = await get_paper_trade_stats()
    rows = [r for r in all_rows if r.get("alert_date") and r["alert_date"] >= window_start]
    if not rows:
        return {"total_closed": 0, "win_rate": None, "avg_pnl_pct": None, "best": None, "worst": None}
    pnls = [float(r["total_pnl"]) for r in rows if r.get("total_pnl") is not None]
    wins = [p for p in pnls if p > 0]
    best = max(rows, key=lambda r: float(r.get("total_pnl") or 0))
    worst = min(rows, key=lambda r: float(r.get("total_pnl") or 0))
    return {
        "total_closed": len(rows),
        "win_rate": round(len(wins) / len(pnls), 3) if pnls else None,
        "avg_pnl_pct": round(sum(pnls) / len(pnls), 2) if pnls else None,
        "best": {"ticker": best["ticker"], "pnl": round(float(best.get("total_pnl") or 0), 2)},
        "worst": {"ticker": worst["ticker"], "pnl": round(float(worst.get("total_pnl") or 0), 2)},
    }


async def _aggregate_audit_errors(days: int) -> dict:
    """Silent-failure surface — captures *_error AND *_failed event types
    across the past `days`. The 2026-05-10 EP scan outcomes typo lurked
    for weeks because it logged only via logger.error and never hit
    audit. Going forward, any try/except path that catches a job-level
    failure must emit an audit event ending in _error or _failed —
    this aggregator surfaces them unconditionally in the weekly digest.

    Synthetic test events (rows whose summary starts with 'SYNTHETIC TEST'
    — emitted by #48/#49 preflight verifications) are filtered out so the
    digest doesn't false-alarm on operator-triggered exception drills.
    """
    since_hours = days * 24
    err_rows = await get_audit_log(limit=500, since_hours=since_hours, event_type_like="%error%")
    failed_rows = await get_audit_log(limit=500, since_hours=since_hours, event_type_like="%_failed%")

    def _is_real(r: dict) -> bool:
        s = (r.get("summary") or "").upper()
        return not s.startswith("SYNTHETIC TEST")

    err_rows = [r for r in err_rows if _is_real(r)]
    failed_rows = [r for r in failed_rows if _is_real(r)]
    # Merge + de-dup (a single event_type matching both globs counts once)
    # Recency per type (weekly-review fix 2026-05-31): the narrator needs last-seen
    # to apply its "count dropped to 0 after a date → likely resolved" rule — e.g.
    # ep_scan_failed hotfixed mid-week 5/26 should read as resolved, not re-surfaced
    # as open. Track max(created_at) per event_type alongside the count.
    # CAVEAT: days_ago is a "hasn't-fired-recently" proxy, NOT a true resolution signal —
    # a weekly-recurring error reads as stale mid-week. Safe because every anomaly line is
    # tagged UNVERIFIED downstream, but don't treat days_ago as proof an error was fixed.
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)

    def _ts(r: dict):
        t = r.get("created_at")
        if isinstance(t, str):
            try:
                t = datetime.fromisoformat(t.replace("Z", "+00:00"))
            except Exception:  # loud-ok: genuine optional-parse fallback — an
                return None    # unparseable timestamp just drops out of the
                               # recency ordering, nothing to alert on.
        if t is not None and getattr(t, "tzinfo", None) is None:
            t = t.replace(tzinfo=timezone.utc)
        return t

    merged: dict[str, int] = {}
    last_seen: dict = {}

    def _bump_last(et: str, r: dict) -> None:
        t = _ts(r)
        if t and (et not in last_seen or t > last_seen[et]):
            last_seen[et] = t

    for r in err_rows:
        merged[r["event_type"]] = merged.get(r["event_type"], 0) + 1
        _bump_last(r["event_type"], r)
    seen_err_types = {er["event_type"] for er in err_rows}
    for r in failed_rows:
        # Avoid double-counting events that match both filters
        if r["event_type"] not in seen_err_types:
            merged[r["event_type"]] = merged.get(r["event_type"], 0) + 1
        _bump_last(r["event_type"], r)
    top5 = sorted(merged.items(), key=lambda kv: -kv[1])[:5]

    def _entry(t: str, c: int) -> dict:
        ls = last_seen.get(t)
        return {
            "event_type": t, "count": c,
            "last_seen": ls.date().isoformat() if ls else None,
            "days_ago": (now - ls).days if ls else None,
        }
    return {
        "total": sum(merged.values()),
        "top_types": [_entry(t, c) for t, c in top5],
    }


async def _aggregate_theme_churn(days: int) -> dict:
    rows = await get_weekly_theme_churn(days=days)
    return {
        "total_high_churn_pairs": len(rows),
        "top": [
            {
                "ticker": r["ticker"],
                "theme": r["theme_name"],
                "adds": r["add_count"],
                "removes": r["remove_count"],
                "events": r["event_count"],
            }
            for r in rows[:10]
        ],
    }


async def _aggregate_cooldowns(window_start: date) -> dict:
    active = await get_active_cooldowns()
    recent = [
        c for c in active
        if c.get("removed_at") and c["removed_at"].date() >= window_start
    ]
    return {
        "active_count": len(active),
        "triggered_this_week": len(recent),
        "recent": [
            {
                "ticker": r["ticker"],
                "theme": r["theme_name"],
                "reason": (r.get("removal_reason") or "")[:120],
            }
            for r in recent[:3]
        ],
    }


async def _aggregate_clusters(today: date) -> dict:
    rows = await get_correlation_clusters(today)
    if not rows:
        return {"count_today": 0, "avg_cohesion": None}
    cohesions = [float(r["mean_corr"]) for r in rows if r.get("mean_corr") is not None]
    return {
        "count_today": len({r["cluster_hash"] for r in rows}),
        "avg_cohesion": round(sum(cohesions) / len(cohesions), 3) if cohesions else None,
    }


async def _aggregate_regime(days: int) -> dict:
    current = await get_latest_regime()
    since_hours = days * 24
    transitions = await get_audit_log(
        limit=50, since_hours=since_hours, event_type="regime_transition"
    )
    return {
        "current": (current or {}).get("regime"),
        "ep_threshold": (current or {}).get("ep_threshold"),
        "transitions_this_week": len(transitions),
    }


async def _aggregate_crypto_readiness(window_days: int) -> dict:
    """Deterministic readiness audit of the crypto RS shadow-mode module.

    Returns a dict consumed by both Sonnet (for context) and the deterministic
    `_format_crypto_section` appendix. Verdict computed here, not by the LLM —
    "ready to flip" is binary; LLM judgment would muddy it.

    Returns empty dict if crypto schema isn't installed (graceful degradation
    for environments where the module hasn't been deployed yet).
    """
    from agents.market_intelligence.db import get_pool
    pool = await get_pool()
    try:
        async with pool.acquire() as conn:
            schema_check = await conn.fetchval(
                "SELECT to_regclass('public.crypto_universe')"
            )
            if schema_check is None:
                return {}

            from agents.market_intelligence.constants import CRYPTO_RS_ENABLED

            universe_size = await conn.fetchval("SELECT COUNT(*) FROM crypto_universe")
            watchlist_total = await conn.fetchval("SELECT COUNT(*) FROM crypto_watchlist")
            watchlist_unresolved = await conn.fetchval(
                "SELECT COUNT(*) FROM crypto_watchlist WHERE coin_id LIKE '_unresolved_%'"
            )
            categories_pairs = await conn.fetchval("SELECT COUNT(*) FROM crypto_categories")
            rs_history_days = await conn.fetchval(
                "SELECT COUNT(DISTINCT score_date) FROM crypto_rs_scores"
            ) or 0
            macro_history_days = await conn.fetchval(
                "SELECT COUNT(DISTINCT date) FROM crypto_total3"
            ) or 0
            stablecoin_history_days = await conn.fetchval(
                "SELECT COUNT(DISTINCT date) FROM crypto_stablecoin_flows"
            ) or 0

            ingest_attempts_7d = await conn.fetchval(
                """
                SELECT COUNT(*) FROM mi_audit_log
                WHERE event_type = 'crypto_ingest_completed'
                  AND created_at >= NOW() - INTERVAL '7 days'
                """
            ) or 0
            ingest_errors_7d = await conn.fetchval(
                """
                SELECT COUNT(*) FROM mi_audit_log
                WHERE event_type = 'crypto_ingest_error'
                  AND created_at >= NOW() - INTERVAL '7 days'
                """
            ) or 0
            last_trigger_row = await conn.fetchrow(
                """
                SELECT triggered_at, alert_type FROM crypto_dominance_alerts
                ORDER BY triggered_at DESC LIMIT 1
                """
            )
            pre_arm_7d = await conn.fetchval(
                """
                SELECT COUNT(*) FROM mi_audit_log
                WHERE event_type = 'crypto_trigger_pre_arm'
                  AND created_at >= NOW() - INTERVAL '7 days'
                """
            ) or 0
    except Exception as e:
        logger.exception("crypto readiness audit failed")
        # Write to mi_audit_log so the daily error-check surface picks it up;
        # otherwise a dropped table or schema rename makes this section silently
        # disappear from weekly digests forever.
        try:
            from agents.market_intelligence.db import log_audit_event
            await log_audit_event(
                "crypto_readiness_audit_error",
                f"weekly review crypto aggregator crashed: {type(e).__name__}",
                str(e)[:4000],
            )
        except Exception:  # loud-ok: double-failure — nothing more we can do
            pass
        return {}

    # Hard gates for "ready to flip"
    blockers: list[str] = []
    if rs_history_days < 30:
        blockers.append(f"need {30 - rs_history_days} more days of RS history (have {rs_history_days}d)")
    if macro_history_days < 90:
        blockers.append(f"need {90 - macro_history_days} more days of macro history for trigger SMA90 (have {macro_history_days}d)")
    if watchlist_unresolved and watchlist_unresolved > 0:
        blockers.append(f"{watchlist_unresolved} watchlist coin(s) still unresolved")
    if categories_pairs == 0:
        blockers.append("crypto_categories empty (Sunday refresh hasn't populated yet)")
    if ingest_errors_7d > 0:
        blockers.append(f"{ingest_errors_7d} crypto_ingest_error events in last 7d")
    if ingest_attempts_7d < 6:
        blockers.append(f"only {ingest_attempts_7d}/7 nightly ingests succeeded (job may not be registered or running)")

    is_live = bool(CRYPTO_RS_ENABLED)
    if blockers:
        verdict_emoji = "⚠️" if (ingest_errors_7d > 0 or watchlist_unresolved > 0) else "⏳"
        verdict = f"{verdict_emoji} not ready: " + "; ".join(blockers)
    elif is_live:
        # Already flipped; gates clean = ongoing health, not a call to action.
        verdict = "✅ live; gates clean"
    else:
        verdict = "✅ ready to flip CRYPTO_RS_ENABLED=true"

    return {
        "shadow_mode": not CRYPTO_RS_ENABLED,
        "universe_size": universe_size,
        "watchlist_total": watchlist_total,
        "watchlist_unresolved": watchlist_unresolved,
        "categories_pairs": categories_pairs,
        "rs_history_days": rs_history_days,
        "macro_history_days": macro_history_days,
        "stablecoin_history_days": stablecoin_history_days,
        "ingest_attempts_7d": ingest_attempts_7d,
        "ingest_errors_7d": ingest_errors_7d,
        "pre_arm_7d": pre_arm_7d,
        "last_trigger_at": last_trigger_row["triggered_at"].isoformat() if last_trigger_row else None,
        "blockers": blockers,
        "verdict": verdict,
    }


async def _aggregate_shadow_orb_outcomes(window_days: int) -> dict:
    """Compare 5-min shadow ORB outcomes to live 1-min ORB on the same alerts.

    Joins `mi_orb_shadow_trades` (5m ORB, telemetry-only) to `mi_live_trades`
    on `(ticker, alert_date)` so per-alert R deltas surface — population
    averages would mask "5m wins on bounce, loses on extended" because
    bucket-level dilutes the per-alert truth.

    Returns empty dict if `mi_orb_shadow_trades` doesn't exist (graceful
    degradation for environments where the schema migration hasn't run).

    Slice caveat: `shape_tag` is populated only on `signal_type='9m_day2'`
    rows. MAGNA53 rows store NULL — by-shape deltas are 9M-cohort only.
    """
    from agents.market_intelligence.db import get_pool
    pool = await get_pool()
    try:
        async with pool.acquire() as conn:
            schema_check = await conn.fetchval(
                "SELECT to_regclass('public.mi_orb_shadow_trades')"
            )
            if schema_check is None:
                return {}

            counts = await conn.fetchrow(
                """
                SELECT
                  COUNT(*) FILTER (WHERE status='open' OR status='closed') AS entered,
                  COUNT(*) FILTER (WHERE status='no_entry')                AS no_entry,
                  COUNT(*) FILTER (WHERE status='gate_blocked')            AS gate_blocked
                FROM mi_orb_shadow_trades
                WHERE bar_size_minutes = 5
                  AND alert_date >= CURRENT_DATE - ($1::int * INTERVAL '1 day')
                """,
                window_days,
            )

            paired = await conn.fetch(
                """
                WITH paired AS (
                  SELECT
                    shadow.ticker,
                    shadow.alert_date,
                    shadow.signal_type,
                    shadow.shape_tag,
                    live.total_pnl   / NULLIF(live.risk_dollars,   0) AS r_1m,
                    shadow.total_pnl / NULLIF(shadow.risk_dollars, 0) AS r_5m
                  FROM mi_orb_shadow_trades shadow
                  JOIN mi_live_trades live
                    ON live.ticker = shadow.ticker
                   AND live.alert_date = shadow.alert_date
                  WHERE shadow.bar_size_minutes = 5
                    AND shadow.alert_date >= CURRENT_DATE - ($1::int * INTERVAL '1 day')
                    AND shadow.status = 'closed'
                    AND live.status   = 'closed'
                    AND shadow.risk_dollars > 0
                    AND live.risk_dollars > 0
                )
                SELECT
                  signal_type,
                  shape_tag,
                  COUNT(*)            AS n_paired,
                  AVG(r_1m)           AS avg_r_1m,
                  AVG(r_5m)           AS avg_r_5m,
                  AVG(r_5m - r_1m)    AS per_alert_delta
                FROM paired
                GROUP BY signal_type, shape_tag
                ORDER BY per_alert_delta DESC NULLS LAST
                """,
                window_days,
            )
    except Exception:
        logger.exception("shadow_orb aggregator failed")
        return {}

    paired_rows = [dict(r) for r in paired]
    total_paired = sum(int(r["n_paired"] or 0) for r in paired_rows)

    by_shape = [
        {
            "signal_type": r["signal_type"],
            "shape_tag": r["shape_tag"],
            "n": int(r["n_paired"] or 0),
            "avg_r_1m": round(float(r["avg_r_1m"] or 0), 2),
            "avg_r_5m": round(float(r["avg_r_5m"] or 0), 2),
            "per_alert_delta": round(float(r["per_alert_delta"] or 0), 2),
        }
        for r in paired_rows
        if (r["n_paired"] or 0) >= 5
    ]

    return {
        "entered": int(counts["entered"] or 0),
        "no_entry": int(counts["no_entry"] or 0),
        "gate_blocked": int(counts["gate_blocked"] or 0),
        "paired_closed_total": total_paired,
        "by_shape": by_shape[:5],
    }


async def _aggregate_wick_outcomes(window_days: int) -> dict:
    """Wick-fill (P22) telemetry roll-up — pure forward-return cohort stats.

    Two anchors per candidate (see wick_tracker.update_forward_returns):
      * `fwd_3d_from_high_pct`  — close − prior_high, conditional on fill
        (NULL on rows that never broke prior_high in the 10-session window)
      * `fwd_3d_from_close_pct` — close − Day1 close, unconditional
        (the all-settled drift baseline)

    The gap between the two medians IS the strategy's edge. If filled cohort
    drift ≈ baseline drift, wick-fill isn't doing anything special.

    Returns empty dict if `mi_wick_candidates` doesn't exist.
    """
    from agents.market_intelligence.db import get_pool
    pool = await get_pool()
    try:
        async with pool.acquire() as conn:
            schema_check = await conn.fetchval(
                "SELECT to_regclass('public.mi_wick_candidates')"
            )
            if schema_check is None:
                return {}

            row = await conn.fetchrow(
                """
                SELECT
                  COUNT(*)                                                AS n_total,
                  COUNT(*) FILTER (WHERE fwd_10d_from_close_pct IS NOT NULL) AS n_settled,
                  COUNT(*) FILTER (WHERE filled_wick = TRUE)              AS n_filled,
                  PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY fwd_3d_from_high_pct)
                    FILTER (WHERE fwd_3d_from_high_pct IS NOT NULL)       AS median_fwd_3d_from_high,
                  PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY fwd_3d_from_close_pct)
                    FILTER (WHERE fwd_3d_from_close_pct IS NOT NULL)      AS median_fwd_3d_from_close
                FROM mi_wick_candidates
                WHERE alert_date >= CURRENT_DATE - ($1::int * INTERVAL '1 day')
                """,
                window_days,
            )
    except Exception:
        logger.exception("wick aggregator failed")
        return {}

    n_total = int(row["n_total"] or 0)
    n_settled = int(row["n_settled"] or 0)
    n_filled = int(row["n_filled"] or 0)
    fill_rate = round(n_filled / n_settled, 3) if n_settled else None
    med_high = row["median_fwd_3d_from_high"]
    med_close = row["median_fwd_3d_from_close"]
    return {
        "n_total": n_total,
        "n_settled": n_settled,
        "n_filled": n_filled,
        "fill_rate": fill_rate,
        "median_fwd_3d_from_high": round(float(med_high), 2) if med_high is not None else None,
        "median_fwd_3d_from_close": round(float(med_close), 2) if med_close is not None else None,
    }


async def _aggregate_fishhook_outcomes(window_days: int) -> dict:
    """Fishhook V3 (TI3) telemetry roll-up — gap-up undercut & reclaim.

    Reframed post-Stage-0 as a base-rate harvester (R≈1.1, hit≈13-19%),
    NOT the original "deep-drift = explosive reclaim" thesis. Surfaces:
      * state distribution (anchor count, promotion/reclaim/settle rates)
      * R + hit-rate on settled rows (settled = reclaimed and held 5d)
      * shallow vs deep drift slice — confirms the inverted-edge finding
        as data accrues; if deep drift starts winning, threshold revisit.

    Returns empty dict if `mi_fishhook_anchors` doesn't exist.
    """
    from agents.market_intelligence.db import get_pool
    pool = await get_pool()
    try:
        async with pool.acquire() as conn:
            schema_check = await conn.fetchval(
                "SELECT to_regclass('public.mi_fishhook_anchors')"
            )
            if schema_check is None:
                return {}

            row = await conn.fetchrow(
                """
                WITH w AS (
                    SELECT * FROM mi_fishhook_anchors
                    WHERE anchor_date >= CURRENT_DATE - ($1::int * INTERVAL '1 day')
                ),
                settled AS (
                    SELECT * FROM w
                    WHERE state IN ('settled','invalidated') AND r_5d IS NOT NULL
                ),
                shallow AS (
                    SELECT r_5d FROM settled WHERE drift_pct_max > -0.05
                ),
                deep AS (
                    SELECT r_5d FROM settled WHERE drift_pct_max <= -0.08
                )
                SELECT
                  (SELECT COUNT(*) FROM w)                                        AS n_total,
                  (SELECT COUNT(*) FROM w WHERE state='pending')                  AS n_pending,
                  (SELECT COUNT(*) FROM w WHERE state='promoted')                 AS n_promoted,
                  (SELECT COUNT(*) FROM w WHERE state='reclaimed')                AS n_reclaimed,
                  (SELECT COUNT(*) FROM w WHERE state='settled')                  AS n_settled,
                  (SELECT COUNT(*) FROM w WHERE state='invalidated')              AS n_invalidated,
                  (SELECT COUNT(*) FROM w WHERE state='expired_no_promotion')     AS n_no_promotion,
                  (SELECT COUNT(*) FROM w WHERE state='expired_no_reclaim')       AS n_no_reclaim,
                  (SELECT PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY r_5d) FROM settled) AS median_r,
                  (SELECT 1.0 * COUNT(*) FILTER (WHERE r_5d > 0) / NULLIF(COUNT(*), 0) FROM settled) AS hit_rate,
                  (SELECT PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY r_5d) FROM shallow) AS shallow_median_r,
                  (SELECT COUNT(*) FROM shallow)                                  AS n_shallow,
                  (SELECT PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY r_5d) FROM deep)    AS deep_median_r,
                  (SELECT COUNT(*) FROM deep)                                     AS n_deep
                """,
                window_days,
            )
    except Exception:
        logger.exception("fishhook aggregator failed")
        return {}

    n_total = int(row["n_total"] or 0)
    n_settled = int(row["n_settled"] or 0)
    return {
        "n_total": n_total,
        "n_pending": int(row["n_pending"] or 0),
        "n_promoted": int(row["n_promoted"] or 0),
        "n_reclaimed": int(row["n_reclaimed"] or 0),
        "n_settled": n_settled,
        "n_invalidated": int(row["n_invalidated"] or 0),
        "n_no_promotion": int(row["n_no_promotion"] or 0),
        "n_no_reclaim": int(row["n_no_reclaim"] or 0),
        "median_r": round(float(row["median_r"]), 2) if row["median_r"] is not None else None,
        "hit_rate": round(float(row["hit_rate"]), 3) if row["hit_rate"] is not None else None,
        "shallow_median_r": round(float(row["shallow_median_r"]), 2) if row["shallow_median_r"] is not None else None,
        "n_shallow": int(row["n_shallow"] or 0),
        "deep_median_r": round(float(row["deep_median_r"]), 2) if row["deep_median_r"] is not None else None,
        "n_deep": int(row["n_deep"] or 0),
    }


def _format_judge_section(data: dict) -> str:
    """Holistic judge weekly roll-up (#240/#249). Deterministic — SURFACES the
    judge's week (graded count, ▲/▼ split, fail-open rate, fire-axes spread);
    never prescribes. N=0 heartbeat keeps a dead writer distinguishable from a
    quiet week (#173 insurance). Per-delta detail lives in the 16:25 digest +
    judge_delta_review.py."""
    total = data.get("total") or 0
    if not total:
        return "⚖️ *Holistic judge (#240):* 0 live alerts in window"
    judged = data.get("judged") or 0
    holds = max(judged - (data.get("promotes") or 0) - (data.get("demotes") or 0), 0)
    lines = [
        "⚖️ *Holistic judge (#240 — load-bearing since 6/10)*",
        "```",
        f"Graded {judged}/{total} alerts   "
        f"▲{data.get('promotes', 0)} ▼{data.get('demotes', 0)} ={holds}",
        f"Fail-open to floor: {total - judged}   "
        f"(authority judge:{data.get('judge_driven', 0)} "
        f"fallback:{data.get('fallbacks', 0)})",
        f"Fire axes: seen {data.get('fire_seen', 0)} · none {data.get('no_fire', 0)}",
        "```",
        "_Per-delta review: `judge_delta_review.py` + the 16:25 digest._",
    ]
    return "\n".join(lines)


def _format_loser_section(loser_breakdown: dict) -> str:
    """Deterministic per-loser breakdown for the weekly digest (#76).

    Surfaces methodology-tuning signals (catalyst-prose mismatch, 1m vs
    5m ORB, gap-through, fast stops, compound losses) verbatim — no LLM
    paraphrasing so exact stop prices and verdicts land in the digest.
    """
    if not loser_breakdown:
        return ""
    losers = loser_breakdown.get("losers") or []
    agg = loser_breakdown.get("aggregates") or {}
    if not losers:
        return ""

    lines = [
        f"❌ *Losers post-mortem ({agg.get('n_losers', 0)} trades · "
        f"${agg.get('total_loss', 0):+,.0f})*",
        "_5m refs the `shadow_orb_5m` strategy — telemetry-only 5-min ORB "
        "tracker. Per-row 🪜 / ⛔ flags show what that strategy would have "
        "done differently vs. the live 1-min ORB._",
    ]
    # Per-trade rows — most recent / largest loss first (already sorted ASC by pnl).
    # Cap to top 10 to keep digest scannable; aggregates capture the tail.
    for L in losers[:10]:
        flags = []
        if L.get("prose_mismatch"):
            flags.append("📰 prose↔grade")
        if L.get("orb5_verdict") == "would_block":
            flags.append("⛔ 5m blocked")
        elif L.get("orb5_verdict") == "wider_stop":
            flags.append(f"🪜 5m stop ${L['orb5_low']:.2f}")
        if (L.get("time_to_stop_min") or 999) < 10:
            flags.append(f"⏱ {L['time_to_stop_min']:.1f}m")
        if L.get("is_compound_loss"):
            flags.append("🔁 compound")
        if (L.get("gap_through_dollars") or 0) > 0.05:
            flags.append(f"⚡ gap-thru ${L['gap_through_dollars']:.2f}")
        if L.get("earnings_boost_fired"):
            flags.append("📅 earnings")
        attempt_marker = f" att{L['entry_attempt']}" if L.get("entry_attempt", 1) > 1 else ""
        flag_str = (" · " + " · ".join(flags)) if flags else ""
        lines.append(
            f"• `{L['ticker']}` {L['alert_date']}{attempt_marker} "
            f"${L['total_pnl']:+,.0f}{flag_str}"
        )
    if len(losers) > 10:
        lines.append(f"_(+ {len(losers) - 10} more losers, see DB row)_")

    # Aggregate roll-up — week-over-week methodology signals.
    # At N<5, single-trade "100%" is misleading; show raw counts instead.
    n = agg.get("n_losers", 0)
    median_gt = agg.get("median_gap_through_dollars")

    def _agg(label: str, count_key: str, pct_key: str) -> str:
        cnt = agg.get(count_key, 0)
        if n < 5:
            return f"{label}: {cnt}/{n}"
        return f"{label}: {agg.get(pct_key, 0):.0f}%"

    agg_bits = [
        _agg("5m-blocked",     "n_5m_would_block",     "pct_5m_would_block"),
        _agg("5m-wider",       "n_5m_wider_stop",      "pct_5m_wider_stop"),
        _agg("prose-mismatch", "n_prose_mismatch",     "pct_prose_mismatch"),
        _agg("fast-stop<10m",  "n_fast_stop_lt_10min", "pct_fast_stop_lt_10min"),
    ]
    if median_gt is not None:
        agg_bits.append(f"med gap-thru ${median_gt:.2f}")
    if agg.get("n_compound_attempt2", 0):
        agg_bits.append(f"compound att2: {agg['n_compound_attempt2']}")
    lines.append("_" + " · ".join(agg_bits) + "_")
    lines.append(
        f"_Legend: 📰=catalyst grade vs prose mismatch · ⛔=5m ORB would block · "
        f"🪜=5m ORB stop wider · ⏱=stopped <10m post-fill · 🔁=att2 loss within 15% "
        f"of att1 · ⚡=fill past stop · 📅=earnings backstop fired_"
    )
    return "\n".join(lines)


def _format_pending_reviews_section(pending: dict) -> str:
    """Deterministic Reviews-ready appendix (#412) — data-gated reviews whose
    threshold flipped this week. Rendered in code (not the LLM) so an actionable
    title can't be truncated (the 'ADV top-50 probe…' → 'ADV' nit). Omitted
    entirely when nothing is ready."""
    ready = (pending or {}).get("ready") or []
    if not ready:
        return ""
    lines = ["📅 *Reviews ready* — data-gated thresholds flipped; action needed:"]
    for r in ready:
        title = (r.get("title") or r.get("review_id") or "?").strip()
        action = (r.get("action_when_ready") or "").strip()
        first = action.split(". ")[0].rstrip(".") if action else ""
        lines.append(f"• *{title}*" + (f" — {first}." if first else ""))
    return "\n".join(lines)


async def _spend_envelope_section() -> str:
    """FL-6 / #378 S-C — the cost-envelope appendix: month-to-date Anthropic LLM spend
    (from the #377 `api_usage` meter) vs `ANTHROPIC_MONTHLY_BUDGET`, top callers, a ceiling
    flag, and the fixed-subs reminder. Deterministic (no LLM); the ONE routine surface that
    completes FL-6 (the /status board + the budget alert already exist). Fails to '' so a
    meter/DB hiccup never breaks the digest."""
    from agents.market_intelligence.db import get_pool
    pool = await get_pool()
    async with pool.acquire() as conn:
        total = await conn.fetchrow(
            "SELECT COUNT(*) AS calls, COALESCE(SUM(cost_usd), 0) AS cost "
            "FROM api_usage WHERE created_at >= date_trunc('month', now())"
        )
        callers = await conn.fetch(
            "SELECT caller, COALESCE(SUM(cost_usd), 0) AS cost FROM api_usage "
            "WHERE created_at >= date_trunc('month', now()) "
            "GROUP BY caller ORDER BY cost DESC LIMIT 3"
        )
    cost = float(total["cost"] or 0) if total else 0.0
    calls = int(total["calls"] or 0) if total else 0
    budget = float(os.environ.get("ANTHROPIC_MONTHLY_BUDGET", "0") or 0)

    lines = ["💵 *Cost envelope (MTD)*"]
    if budget > 0:
        pct = (cost / budget) * 100
        flag = " 🔴 OVER" if cost > budget else (" 🟠" if pct >= 80 else " ✓")
        lines.append(f"LLM: ${cost:.2f} / ${budget:.0f} ({pct:.0f}%){flag} · {calls} calls")
    else:
        lines.append(f"LLM: ${cost:.2f} · {calls} calls (no budget set — set ANTHROPIC_MONTHLY_BUDGET)")
    for r in callers:
        lines.append(f"  {r['caller'].replace('_', ' ')}: ${float(r['cost'] or 0):.2f}")
    # fixed-subs note (not in the LLM meter — keeps the envelope honest, #378 S-C)
    lines.append("_+ fixed infra/data subs (server · Polygon · FMP) not metered here — see the cost-envelope doc._")
    return "\n".join(lines)


def _format_mfe_capture_section(data: dict) -> str:
    """W3 winner-harvest KPI (#306) — deterministic; SURFACES the cumulative
    MFE-capture number against the v2.0 tier-one bar, never prescribes.
    Omitted entirely until the cohort exists (no misleading 0-line)."""
    if not data or not data.get("n"):
        return ""
    pct = data.get("capture_pct")
    if pct is None:
        return ""
    lines = [
        f"🎯 *MFE capture (W3 KPI):* {pct}% cumulative — "
        f"${data.get('kept_dollars', 0):+,.0f} kept of "
        f"${data.get('mfe_dollars', 0):,.0f} peak "
        f"(n={data['n']} partial-taken closed · bar >{data.get('bar_pct', 50)}%)",
    ]
    for w in data.get("window_closes") or []:
        lines.append(
            f"• `{w['ticker']}` closed this week: {w['capture_pct']}% "
            f"(${w['kept']:+,} of ${w['mfe']:,})"
        )
    return "\n".join(lines)


def _format_crypto_section(crypto: dict) -> str:
    """Render the deterministic crypto-readiness appendix for the weekly digest.

    Returns empty string if the module isn't installed (skips the section
    entirely rather than emitting a misleading "0 days" line).
    """
    if not crypto:
        return ""

    # Telegram parse_mode="Markdown" (legacy) does NOT support `**bold**` — use
    # single asterisks. Unbalanced ** would also break the whole appendix.
    mode = "shadow mode" if crypto.get("shadow_mode") else "LIVE"
    universe = crypto.get("universe_size") or 0
    wl_total = crypto.get("watchlist_total") or 0
    wl_unresolved = crypto.get("watchlist_unresolved") or 0
    wl_marker = "all resolved ✓" if wl_unresolved == 0 else f"{wl_unresolved} unresolved ⚠"
    cats = crypto.get("categories_pairs") or 0
    cats_marker = "" if cats > 0 else " ⚠"
    rs_days = crypto.get("rs_history_days") or 0
    macro_days = crypto.get("macro_history_days") or 0
    attempts = crypto.get("ingest_attempts_7d") or 0
    errors = crypto.get("ingest_errors_7d") or 0
    pre_arm = crypto.get("pre_arm_7d") or 0

    lines = [
        f"🪙 *Crypto RS — {mode}*",
        f"History: {rs_days}d RS · {macro_days}d macro",
        f"Universe: {universe} coins · {wl_total} watchlist ({wl_marker})",
        f"Categories: {cats} pairs{cats_marker}",
        f"Last 7d: {attempts}/7 ingests · {errors} errors",
    ]
    if pre_arm > 0:
        lines.append(f"Pre-arm: stables flowing in but alts not rotating ({pre_arm} of last 7 days)")
    if crypto.get("last_trigger_at"):
        lines.append(f"Last trigger fire: {crypto['last_trigger_at'][:10]}")
    lines.append(f"Verdict: {crypto.get('verdict') or '(unknown)'}")
    return "\n".join(lines)


def _finalize_bucket(b: dict) -> dict:
    total = b["total"]
    out = {"total": total, "green": b["green"]}
    if total:
        out["win_rate"] = round(b["green"] / total, 3)
    if b.get("fwd_1w_n"):
        out["avg_fwd_1w_pct"] = round(b["fwd_1w_sum"] / b["fwd_1w_n"], 2)
    return out


# ── LLM synthesis ─────────────────────────────────────────────────────────────


async def _synthesize(metrics: dict, prior: dict | None) -> str:
    client = anthropic.AsyncAnthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))
    prior_block = ""
    if prior:
        prior_block = (
            f"\n\nPREVIOUS REVIEW ({prior['review_date']}, window={prior['window_days']}d):\n"
            f"Anomalies flagged last week: {prior.get('suggestions')}\n"
            f"Metrics last week: {prior.get('metrics')}\n"
        )
    user_prompt = (
        f"THIS WEEK'S METRICS (window={metrics['window']['days']}d, "
        f"{metrics['window']['start']} → {metrics['window']['end']}):\n"
        f"{json.dumps(metrics, default=str, indent=2)}"
        f"{prior_block}"
    )
    resp = await client.messages.create(
        model=_MODEL,
        max_tokens=_MAX_TOKENS,
        system=_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_prompt}],
    )
    # S2/F9: safe wrapper — see spend_tracker.log_anthropic_call_safe
    from agents.market_intelligence.spend_tracker import log_anthropic_call_safe
    await log_anthropic_call_safe(
        model=_MODEL, caller="system_review_weekly", usage=getattr(resp, "usage", None),
    )
    return "".join(block.text for block in resp.content if hasattr(block, "text")).strip()


def _extract_anomalies(summary: str) -> list[str]:
    """Parse the '⚠️ Anomalies to verify' block — its • bullets — so next week's run can
    feed them into the 🔁 persistence check (did they clear?). Replaces the removed
    '💡 Proposed changes' parser (2026-05-31: the review surfaces facts, never prescribes)."""
    out: list[str] = []
    in_block = False
    for line in summary.splitlines():
        stripped = line.strip()
        if "Anomalies to verify" in stripped:
            in_block = True
            continue
        if in_block:
            if stripped.startswith(("🔁", "⚠️", "✅")) or not stripped:
                if out:  # end of block
                    break
                continue
            # Strip leading "1.", "2.", "-", "•"
            cleaned = stripped.lstrip("0123456789.•- \t")
            if cleaned:
                out.append(cleaned)
    return out
