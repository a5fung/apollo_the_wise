"""#378 Cost-observability Phase 2 — THE TOTAL + THE ALARM (operator 6/25).

The #377 meter (spend_tracker → api_usage) counts every metered LLM call;
the weekly review's spend appendix (S-C, FL-6) shows MTD once a week. This
module adds the two missing operator surfaces:

- **/cost board** (on demand): full operating total = metered VARIABLE spend
  (Claude + Perplexity, from api_usage) + the FLAT subscriptions, with MTD,
  month projection, budget headroom and top callers.
- **THE ALARM** (daily 17:52 ET job): Telegram WARN when (a) MTD variable
  spend exceeds ANTHROPIC_MONTHLY_BUDGET (the operator's cap on the VARIABLE
  half — flat is fixed, no alarm on it, operator 6/25), or (b) today's spend
  is a >2× trailing-30d-median daily anomaly. Silent otherwise (the series
  already lives in api_usage); an audit row records every fired alarm.

Flat numbers are the operator's 6/25 figures, completed 7/17: Massive is
Polygon's rebranded product (one market-data line) and there is no FMP
subscription — the $148 stack is the full fixed cost.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import date, timedelta

from agents.market_intelligence.db import get_pool, log_audit_event
from agents.market_intelligence.system_audit import (
    _band_for as _sa_band_for,
    _directional_ratio as _sa_directional_ratio,
    _trimmed_median_mad as _sa_trimmed_median_mad,
)
from shared.llm_models import PRICING_PER_MTOK, SONNET
from shared.output_ceilings import CEILINGS, NEAR_CEILING_FRACTION, TRUNCATION_BY_DESIGN

logger = logging.getLogger(__name__)

# Operator-stated flat subscriptions (2026-06-25), USD/month.
# Operator-confirmed 7/17: Massive IS Polygon (product rebrand) — one market-
# data subscription covers the Polygon feed; there is NO FMP subscription
# (free tier). The 6/25 open question is settled; the stack is complete.
FLAT_SUBS_MONTHLY: dict[str, float] = {
    "Hetzner": 15.0,
    "Massive (Polygon)": 33.0,
    "Alpaca Algo Trader Plus": 100.0,
}
FLAT_TOTAL = sum(FLAT_SUBS_MONTHLY.values())

# Daily-anomaly floor: below this, a "2× median" trip is noise, not signal.
ANOMALY_MIN_USD = 1.00


def _budget() -> float:
    try:
        return float(os.environ.get("ANTHROPIC_MONTHLY_BUDGET", "0") or 0)
    except ValueError:
        return 0.0


# Perplexity rows log under their MODEL names ('sonar'/'sonar-pro'), not
# 'perplexity*' (7/17 prod: the split showed $0 while perplexity_news_search
# sat in top callers) — match both shapes.
async def compute_cost_board(today: date) -> dict:
    """One read of api_usage → the full picture. All date math in ET (the
    operator's billing mental model), via AT TIME ZONE on the TIMESTAMPTZ."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        # Raw-timestamp prefilter (review 7/17): the ET-date conversion inside
        # WHERE defeats idx_api_usage_created and scanned the WHOLE unboundedly-
        # growing table on every /cost + daily alarm. 46 days generously covers
        # month-start AND the 31-day daily window under any ET/UTC skew; the
        # exact ET-date logic applies AFTER the indexed cut.
        row = await conn.fetchrow("""
            WITH et AS (
                SELECT cost_usd, model, caller,
                       (created_at AT TIME ZONE 'America/New_York')::date AS d
                FROM api_usage
                WHERE created_at >= $1::date - INTERVAL '46 days'
            )
            SELECT
              COALESCE(SUM(cost_usd) FILTER (WHERE d >= date_trunc('month', $1::date)), 0) AS mtd,
              COALESCE(SUM(cost_usd) FILTER (WHERE d >= date_trunc('month', $1::date)
                                             AND (model ILIKE 'sonar%' OR model ILIKE 'perplexity%')), 0) AS mtd_pplx,
              COALESCE(SUM(cost_usd) FILTER (WHERE d = $1::date), 0)                       AS today,
              COUNT(*)  FILTER (WHERE d >= date_trunc('month', $1::date))                  AS mtd_calls
            FROM et
        """, today)
        daily = await conn.fetch("""
            SELECT (created_at AT TIME ZONE 'America/New_York')::date AS d,
                   SUM(cost_usd) AS spend
            FROM api_usage
            WHERE created_at >= $1::date - INTERVAL '32 days'
              AND (created_at AT TIME ZONE 'America/New_York')::date
                  BETWEEN $1::date - 30 AND $1::date - 1
            GROUP BY 1 ORDER BY 1
        """, today)
        callers = await conn.fetch("""
            SELECT caller, SUM(cost_usd) AS spend
            FROM api_usage
            WHERE created_at >= $1::date - INTERVAL '46 days'
              AND (created_at AT TIME ZONE 'America/New_York')::date
                  >= date_trunc('month', $1::date)
            GROUP BY caller ORDER BY spend DESC LIMIT 3
        """, today)

    # True median over ALL 30 trailing days — quiet days count as $0 (review
    # 7/17: active-days-only + upper-middle-element inflated the baseline and
    # desensitized the 2× anomaly trigger).
    import statistics
    spend_by_day = {r["d"]: float(r["spend"]) for r in daily}
    series = [spend_by_day.get(today - timedelta(days=k), 0.0) for k in range(1, 31)]
    median30 = statistics.median(series) if series else 0.0
    mtd = float(row["mtd"])
    day_of_month = today.day
    days_in_month = (date(today.year + (today.month == 12), (today.month % 12) + 1, 1)
                     - date(today.year, today.month, 1)).days
    projected = mtd / day_of_month * days_in_month if day_of_month else mtd
    return {
        "today": today.isoformat(),
        "mtd_variable": round(mtd, 2),
        "mtd_perplexity": round(float(row["mtd_pplx"]), 2),
        "mtd_claude": round(mtd - float(row["mtd_pplx"]), 2),
        "mtd_calls": int(row["mtd_calls"]),
        "today_spend": round(float(row["today"]), 2),
        "median30_daily": round(median30, 2),
        "projected_variable": round(projected, 2),
        "budget": _budget(),
        "flat_total": FLAT_TOTAL,
        "top_callers": [(r["caller"], round(float(r["spend"]), 2)) for r in callers],
    }


def render_cost_board(d: dict) -> str:
    """Operator-facing /cost board. Dynamic tokens (caller names are
    snake_case) go inside a code block — the #477 parity class."""
    b = d["budget"]
    headroom = (f"${b - d['mtd_variable']:.2f} headroom"
                if b and d["mtd_variable"] <= b else
                f"⚠️ OVER by ${d['mtd_variable'] - b:.2f}" if b else
                "no budget set (ANTHROPIC-MONTHLY-BUDGET)")
    lines = [
        f"*💰 COST BOARD — {d['today']}*",
        "```",
        f"VARIABLE (metered)   MTD ${d['mtd_variable']:.2f} / {d['mtd_calls']} calls",
        f"  Claude             ${d['mtd_claude']:.2f}",
        f"  Perplexity         ${d['mtd_perplexity']:.2f}",
        f"  today ${d['today_spend']:.2f} · 30d median ${d['median30_daily']:.2f}/day",
        f"  projected month    ${d['projected_variable']:.2f}"
        + (f" vs budget ${b:.0f}" if b else ""),
        f"FLAT (subscriptions) ${d['flat_total']:.0f}/mo",
    ]
    for name, amt in FLAT_SUBS_MONTHLY.items():
        lines.append(f"  {name:<24} ${amt:.0f}")
    lines.append(f"FULL MONTH ≈ ${d['projected_variable'] + d['flat_total']:.2f} "
                 f"(variable proj + flat)")
    if d["top_callers"]:
        lines.append("top callers MTD:")
        for c, amt in d["top_callers"]:
            lines.append(f"  {c:<28} ${amt:.2f}")
    lines.append("```")
    # Plain text, no italics: Telegram V1 fails to parse `_…_` on the line
    # after a ``` fence (operator screenshot 7/17 — the bold header parsed,
    # the italic footer showed literal underscores). Don't fight V1 quirks.
    lines.append(headroom)
    return "\n".join(lines)


async def run_daily_spend_alarm(today: date) -> dict | None:
    """17:52 ET job. Fires Telegram + audit ONLY on breach (house rule:
    actionable-only). Two triggers, operator-ruled 6/25: monthly budget cap on
    the variable half AND a 2× trailing-30d-median daily anomaly."""
    d = await compute_cost_board(today)
    reasons = []
    if d["budget"] and d["mtd_variable"] > d["budget"]:
        # Once-per-month (review 7/17): without state this re-fired every
        # weekday for the rest of the month after the first breach — repeated
        # non-actionable Telegram. The audit log IS the state. (The 2×-median
        # anomaly below is naturally day-scoped and needs no dedupe. NB: the
        # orchestrator-side core/spend.py has its own 50/80/100%-crossing
        # alerts on the same table — this alarm is the market-agent EOD net.)
        pool = await get_pool()
        async with pool.acquire() as conn:
            already = await conn.fetchval("""
                SELECT COUNT(*) FROM mi_audit_log
                WHERE event_type = 'spend_alarm_fired'
                  AND summary LIKE '%budget%'
                  AND (created_at AT TIME ZONE 'America/New_York')::date
                      >= date_trunc('month', $1::date)
            """, today)
        if not already:
            reasons.append(f"MTD variable ${d['mtd_variable']:.2f} > budget ${d['budget']:.0f}")
    if (d["today_spend"] > ANOMALY_MIN_USD
            and d["median30_daily"] > 0
            and d["today_spend"] > 2 * d["median30_daily"]):
        reasons.append(f"today ${d['today_spend']:.2f} > 2× 30d median "
                       f"(${d['median30_daily']:.2f}/day)")
    if not reasons:
        return None
    await log_audit_event(
        "spend_alarm_fired",
        summary=f"LLM spend alarm: {'; '.join(reasons)}",
        detail=json.dumps(d),
    )
    from agents.market_intelligence.briefing import send_telegram_message
    await send_telegram_message(
        "🔴 *SPEND ALARM* — " + "; ".join(reasons) + "\n/cost for the full board")
    return d


# ── #379 Cost-observability Phase 3 — THE WATCHDOG ───────────────────────────
#
# Two surfaces on top of the #378 board/alarm above:
#   (1) per-caller cost-anomaly detection — a caller's $/day spikes vs its OWN
#       trailing median (the whole-board alarm above only looks at the TOTAL,
#       so a caller doubling its own spend can hide inside a healthy total).
#   (2) cost-reduction surfacing — heuristics flagging Opus-where-Sonnet-fits,
#       oversized prompts, and a runaway-retry call-volume trend.
#
# Reuses system_audit's trimmed-median ± MAD band routing
# (_trimmed_median_mad / _band_for / _directional_ratio) rather than
# reinventing a second anomaly statistic. One deliberate divergence:
# system_audit's MAD<1 z-fallback threshold is tuned for COUNT metrics
# (theme_count_active, cooldowns_per_day) where MAD=1 is a real day-to-day
# step; a caller's daily $ MAD is routinely <1 even when perfectly healthy,
# so this module uses its own dollar-scale epsilon (_CALLER_MAD_EPS_USD)
# instead of importing system_audit's constant. Advisory only — surfaces
# opportunities, never auto-applies a model/prompt change (THE LINE).

CALLER_MIN_SAMPLE_DAYS = 5          # cold-start floor: need >=5 active history days
CALLER_ANOMALY_MIN_USD = 0.50       # per-caller noise floor (finer than the board's $1 floor)
_CALLER_MAD_EPS_USD = 0.05          # below this, a $ MAD is noise -> ratio-only band routing
_RETRY_CALLS_RATIO = 1.8            # recent-vs-baseline call-count ratio flagging a retry loop
_UNIT_COST_RATIO = 1.5              # today's $/call vs its 30d median at/above this = unit-cost driver
_RECENT_ACTIVE_DAYS = 3             # the "current regime" for call counts — a retry loop is a TODAY event
_OVERSIZED_PROMPT_TOKENS = 40_000   # avg input tokens/call above this = worth a prompt-size look
_REDUCTION_MIN_SAVINGS_USD = 0.50   # noise floor for surfacing an Opus->Sonnet estimate


async def _fetch_caller_window(today: date, lookback_days: int = 30):
    """One read of api_usage grouped by (caller, model, ET day) over the
    trailing window + today. Feeds both the per-caller anomaly detector and
    the reduction-opportunity heuristics below. Mirrors compute_cost_board's
    raw-timestamp prefilter (7/17 review) so idx_api_usage_created stays a
    bounded scan rather than the whole table."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            WITH et AS (
                SELECT cost_usd, caller, model, input_tokens, output_tokens,
                       (created_at AT TIME ZONE 'America/New_York')::date AS d
                FROM api_usage
                WHERE created_at >= $1::date - INTERVAL '32 days'
            )
            SELECT caller, model, d, SUM(cost_usd) AS spend, COUNT(*) AS calls,
                   SUM(input_tokens) AS in_tok, SUM(output_tokens) AS out_tok
            FROM et
            WHERE d BETWEEN $1::date - $2::int AND $1::date
            GROUP BY caller, model, d
        """, today, lookback_days)
    return rows


def _daily_caller_series(rows) -> dict[str, dict[date, dict[str, float]]]:
    """caller -> {day -> {"spend":, "calls":}}, summed across models."""
    out: dict[str, dict[date, dict[str, float]]] = {}
    for r in rows:
        day_map = out.setdefault(r["caller"], {})
        slot = day_map.setdefault(r["d"], {"spend": 0.0, "calls": 0})
        slot["spend"] += float(r["spend"])
        slot["calls"] += int(r["calls"])
    return out


def _caller_window_totals(rows, today: date, window_days: int = 7) -> dict[str, dict]:
    """caller -> aggregate totals (+ per-model breakdown) over the trailing
    `window_days` (incl. today) — the reduction heuristics' input. Shorter
    than the 30d anomaly baseline: reduction opportunities are about the
    CURRENT model/prompt mix, not a long trailing median."""
    cutoff = today - timedelta(days=window_days - 1)
    out: dict[str, dict] = {}
    for r in rows:
        if r["d"] < cutoff or r["d"] > today:
            continue
        c = out.setdefault(r["caller"], {
            "calls": 0, "in_tok": 0, "out_tok": 0, "spend": 0.0, "by_model": {},
        })
        c["calls"] += int(r["calls"])
        c["in_tok"] += int(r["in_tok"] or 0)
        c["out_tok"] += int(r["out_tok"] or 0)
        c["spend"] += float(r["spend"])
        m = c["by_model"].setdefault(r["model"], {
            "calls": 0, "in_tok": 0, "out_tok": 0, "spend": 0.0,
        })
        m["calls"] += int(r["calls"])
        m["in_tok"] += int(r["in_tok"] or 0)
        m["out_tok"] += int(r["out_tok"] or 0)
        m["spend"] += float(r["spend"])
    return out


def _classify_caller_band(today_spend: float, history: list[float]) -> tuple[int, float, float, float]:
    """Reuses system_audit's z/ratio/_band_for routing (band 3 = z>=3 or
    ratio>=5x, the same threshold that gates its L2 Telegram tier). Returns
    (band, p50, mad, ratio)."""
    p50, _, mad, _ = _sa_trimmed_median_mad(history)
    use_z = mad >= _CALLER_MAD_EPS_USD
    z = ((today_spend - p50) / mad) if use_z else 0.0
    ratio = _sa_directional_ratio(today_spend, p50, "high")
    band = _sa_band_for(z, ratio)
    return band, p50, mad, ratio


def _window_series(series: dict, today: date, key: str, start_k: int, end_k: int) -> list:
    """Trailing per-day values of one metric key over day-offsets [start_k, end_k) back from today
    (a missing day → 0.0). Single source for the anomaly/retry trailing windows so a change to how a
    day-offset slice is built can't drift across the call sites that need it."""
    return [series.get(today - timedelta(days=k), {}).get(key, 0.0)
            for k in range(start_k, end_k)]


def _attribute_leak(today_spend: float, today_calls: int,
                    hist_spend: list, hist_calls: list) -> dict:
    """#543 attribution fix — name the DRIVER of a spend anomaly, from the actual
    decomposition spend = calls x $/call: either call VOLUME rose, or unit COST
    ($/call) rose, or both, and the alert says which.

    The 2026-08-06 mislabel this replaces: catalyst_metrics_extractor fired 17.7x
    and was labelled "call-volume (possible retry loop)" purely because today's
    calls (29) dwarfed the 30d trimmed MEDIAN (3/day) — a median dominated by a
    stale sparse-cadence July, while the CURRENT regime (earnings season) had
    already been running 24/day for days. Call volume was FLAT vs the regime; the
    real driver was $/call jumping to a 30d high ($0.025 vs $0.014 median — the
    model change). The one true alarm pointed the diagnosis at retries.

    Hence the two baselines here are deliberately different:
      - unit cost is regime-stable (it is a price), so it compares against the 30d
        trimmed median of per-active-day $/call;
      - a retry loop is a TODAY phenomenon, so call volume compares against the
        median of the last _RECENT_ACTIVE_DAYS active days — the current regime,
        not a month-old cadence.
    `hist_spend`/`hist_calls` are the caller's zero-filled day series ordered
    yesterday-first (the shape _window_series already produces)."""
    import statistics
    unit_hist = [s / c for s, c in zip(hist_spend, hist_calls) if c > 0]
    unit_p50, _, _, _ = _sa_trimmed_median_mad(unit_hist) if unit_hist else (0.0, 0.0, 0.0, 0)
    today_unit = (today_spend / today_calls) if today_calls else 0.0
    unit_ratio = (today_unit / unit_p50) if unit_p50 > 0 else 0.0
    recent_active = [c for c in hist_calls if c > 0][:_RECENT_ACTIVE_DAYS]
    recent_med = float(statistics.median(recent_active)) if recent_active else 0.0
    recent_ratio = (today_calls / recent_med) if recent_med > 0 else 0.0
    unit_up = unit_ratio >= _UNIT_COST_RATIO
    volume_up = recent_ratio >= _RETRY_CALLS_RATIO
    if unit_up and volume_up:
        leak = (f"call-volume AND unit-cost both rose ({recent_ratio:.1f}x calls, "
                f"{unit_ratio:.1f}x $/call)")
    elif unit_up:
        leak = (f"unit-cost (${today_unit:.3f}/call vs ${unit_p50:.3f} 30d median = "
                f"{unit_ratio:.1f}x; calls flat vs recent {recent_med:.0f}/day)")
    elif volume_up:
        leak = (f"call-volume ({today_calls} calls vs recent {recent_med:.0f}/day = "
                f"{recent_ratio:.1f}x, $/call flat — retry loop or new workload?)")
    else:
        leak = (f"no single driver (calls {recent_ratio:.1f}x recent, "
                f"$/call {unit_ratio:.1f}x — gradual ramp)")
    return {
        "leak_class": leak,
        "unit_today": round(today_unit, 4), "unit_median30": round(unit_p50, 4),
        "unit_ratio": round(unit_ratio, 2),
        "recent_calls_median": round(recent_med, 1),
        "recent_calls_ratio": round(recent_ratio, 2),
    }


def _caller_cost_anomalies_from_rows(rows, today: date, lookback_days: int = 30,
                                     daily: "dict | None" = None) -> list[dict]:
    """Pure half of compute_caller_cost_anomalies — takes already-fetched
    rows so compute_cost_watchdog can share ONE api_usage read across both
    the anomaly detector and the reduction heuristics below, instead of
    each hitting the table separately. `daily` may be a pre-derived series (so
    compute_cost_watchdog computes it once for both consumers)."""
    daily = daily if daily is not None else _daily_caller_series(rows)
    out = []
    for caller, series in daily.items():
        today_slot = series.get(today, {"spend": 0.0, "calls": 0})
        today_spend = today_slot["spend"]
        today_calls = today_slot["calls"]
        if today_spend < CALLER_ANOMALY_MIN_USD:
            continue
        hist_spend = _window_series(series, today, "spend", 1, lookback_days + 1)
        hist_calls = _window_series(series, today, "calls", 1, lookback_days + 1)
        active_spend = [v for v in hist_spend if v > 0]
        active_calls = [v for v in hist_calls if v > 0]
        if len(active_spend) < CALLER_MIN_SAMPLE_DAYS:
            continue
        band, p50, mad, ratio = _classify_caller_band(today_spend, active_spend)
        if band < 3:
            continue
        calls_p50, _, _, _ = _sa_trimmed_median_mad(active_calls) if active_calls else (0.0, 0.0, 0.0, 0)
        calls_ratio = (today_calls / calls_p50) if calls_p50 > 0 else 0.0
        out.append({
            "caller": caller, "today_spend": round(today_spend, 2),
            "median30": round(p50, 2), "mad": round(mad, 4), "ratio": round(ratio, 2),
            "today_calls": today_calls, "median_calls": round(calls_p50, 1),
            "calls_ratio": round(calls_ratio, 2),
            # #543: leak_class + the decomposition fields it was derived from
            **_attribute_leak(today_spend, today_calls, hist_spend, hist_calls),
        })
    out.sort(key=lambda r: r["ratio"], reverse=True)
    return out


async def compute_caller_cost_anomalies(today: date, lookback_days: int = 30) -> list[dict]:
    """Per-caller $/day spike vs its OWN trailing median (#379). Flags a
    caller whose TODAY spend sits in system_audit's band 3 against its own
    30d history — the leak class a retry loop doubling calls, or a one-off
    prompt blowing up token count, would produce. Cold-start gated (needs
    >=CALLER_MIN_SAMPLE_DAYS active days) so a brand-new caller can't
    false-positive on day 2.

    Baseline = ACTIVE days only (spend/calls > 0), NOT zero-padded like
    compute_cost_board's whole-board median. The board's total is active
    essentially every day, so a quiet day there is real signal; many
    individual callers legitimately run on a sparse cadence (weekly/monthly
    jobs), and zero-padding those degenerates the trimmed median straight to
    0 — which makes the ratio check permanently 0 and blind for exactly the
    callers most likely to look anomalous on the one day they DO fire."""
    rows = await _fetch_caller_window(today, lookback_days)
    return _caller_cost_anomalies_from_rows(rows, today, lookback_days)


# ── NEW-LANE detection (2026-08-02) — the blind spot the two detectors above share ──
#
# Operator, after the chart-vision shadow ran 336 calls unnoticed: *"we can have hidden costs that
# provides no value that is running and no way for us to know about in time."*
#
# Neither detector above can see a lane switching ON. compute_caller_cost_anomalies is COLD-START
# GATED by design (its own docstring: "so a brand-new caller can't false-positive on day 2") and the
# reduction heuristics answer "is existing spend reducible", never "should this exist at all". A new
# lane therefore ramps invisibly until it is big enough to move a total — which for an $11/month
# experiment is never.
#
# This is the complement, and deliberately the WEAKEST possible statement: a caller that has never
# spent before is spending now. No judgement about whether it should — that is the operator's call,
# and the only thing being claimed is "this started".
_NEW_LANE_MIN_USD = 0.10      # below a dime over the window it is a smoke test, not a lane
_NEW_LANE_RECENT_DAYS = 3     # a lane that starts on a Friday is still new on Monday


def _new_lanes_from_rows(rows, today: date, recent_days: int = _NEW_LANE_RECENT_DAYS,
                         lookback_days: int = 30, daily: "dict | None" = None) -> list[dict]:
    """Callers spending in the last `recent_days` with ZERO spend across the whole baseline window.

    Pure (unit-testable without a DB). The once-ever dedupe lives in the async layer — a sparse
    monthly caller would otherwise re-announce itself every month, which is the "repeated
    non-actionable Telegram" failure run_daily_spend_alarm already learned on 7/17."""
    daily = daily if daily is not None else _daily_caller_series(rows)
    out = []
    for caller, series in daily.items():
        recent_spend = sum(_window_series(series, today, "spend", 0, recent_days))
        if recent_spend < _NEW_LANE_MIN_USD:
            continue
        baseline = sum(_window_series(series, today, "spend", recent_days,
                                      lookback_days + recent_days))
        if baseline > 0:
            continue
        recent_calls = int(sum(_window_series(series, today, "calls", 0, recent_days)))
        out.append({
            "type": "new_lane", "caller": caller,
            "recent_spend": round(recent_spend, 2), "recent_calls": recent_calls,
            "window_days": recent_days,
            "note": f"{caller} started spending — ${recent_spend:.2f} over {recent_calls} calls "
                    f"in {recent_days}d, nothing in the prior {lookback_days}d. "
                    f"Is it meant to be running, and what is it buying?",
        })
    out.sort(key=lambda r: r["recent_spend"], reverse=True)
    return out


async def _unannounced_new_lanes(candidates: list[dict]) -> list[dict]:
    """Drop lanes already announced once. The audit log IS the state (same idiom as the budget-cap
    dedupe in run_daily_spend_alarm) — no new table, and a caller is announced exactly once ever."""
    if not candidates:
        return []
    names = [c["caller"] for c in candidates]
    pool = await get_pool()
    async with pool.acquire() as conn:
        # Matched against the CANDIDATES rather than pulling every caller ever announced: the
        # result is then O(candidates) (0-3/day, already past the $0.10 + zero-baseline filter)
        # instead of O(all-lanes-ever), whatever the audit log grows to. A TIME bound would be
        # wrong here -- the dedupe means "announced once EVER", so an old lane must never age
        # back into being announceable.
        seen = {r["summary_caller"] for r in await conn.fetch(
            "SELECT DISTINCT summary AS summary_caller FROM mi_audit_log "
            "WHERE event_type = 'cost_new_lane' AND summary = ANY($1::text[])", names)}
    return [c for c in candidates if c["caller"] not in seen]


def _reduction_opportunities_from_totals(totals: dict[str, dict]) -> list[dict]:
    """Pure heuristic layer (unit-testable without a DB): Opus-where-Sonnet-
    fits + oversized prompts. Advisory surfacing ONLY — never auto-applies
    (THE LINE: no model/strategy change without operator sign-off); this
    just names the opportunity and an estimated dollar delta."""
    out = []
    sonnet_price = PRICING_PER_MTOK.get(SONNET, {"input": 3.0, "output": 15.0})
    for caller, agg in totals.items():
        calls = agg["calls"] or 0
        if calls == 0:
            continue
        # (a) Opus-where-Sonnet-fits: estimate the SAME token volume at
        # Sonnet rates and surface the delta if it clears the noise floor.
        for model, m in agg["by_model"].items():
            if "opus" not in model.lower() or m["spend"] <= 0:
                continue
            sonnet_equiv = ((m["in_tok"] / 1_000_000) * sonnet_price["input"]
                            + (m["out_tok"] / 1_000_000) * sonnet_price["output"])
            savings = m["spend"] - sonnet_equiv
            if savings >= _REDUCTION_MIN_SAVINGS_USD:
                out.append({
                    "type": "opus_where_sonnet_fits", "caller": caller, "model": model,
                    "spend": round(m["spend"], 2), "sonnet_equiv": round(sonnet_equiv, 2),
                    "est_savings": round(savings, 2),
                    "note": f"{caller} spent ${m['spend']:.2f} on {model} this window; "
                            f"same tokens at Sonnet rates ≈ ${sonnet_equiv:.2f} "
                            f"(≈${savings:.2f} saved if Sonnet fits the task).",
                })
        # (b) Oversized prompts: high avg input tokens/call.
        avg_in = agg["in_tok"] / calls
        if avg_in >= _OVERSIZED_PROMPT_TOKENS:
            out.append({
                "type": "oversized_prompt", "caller": caller,
                "avg_input_tokens": round(avg_in), "calls": calls,
                "note": f"{caller} averages {avg_in:,.0f} input tokens/call over {calls} calls "
                        f"— worth checking for prompt bloat / unneeded context.",
            })
    out.sort(key=lambda r: r.get("est_savings", 0), reverse=True)
    return out


def _retry_loop_opportunities(
    daily: dict[str, dict[date, dict]], today: date,
    recent_days: int = 3, lookback_days: int = 30,
) -> list[dict]:
    """Elevated call-VOLUME trend vs a non-overlapping baseline — catches a
    cheap-per-call (e.g. Haiku) retry loop that the $ anomaly check above
    could miss because the per-call cost never clears the $ noise floor.
    Baseline uses active days only (same rationale as compute_caller_cost_
    anomalies — a sparse-cadence caller would otherwise zero-pad its own
    median to 0)."""
    out = []
    for caller, series in daily.items():
        recent = _window_series(series, today, "calls", 0, recent_days)
        baseline_hist = _window_series(series, today, "calls", recent_days,
                                       lookback_days + recent_days)
        active_baseline = [v for v in baseline_hist if v > 0]
        if len(active_baseline) < CALLER_MIN_SAMPLE_DAYS:
            continue
        p50, _, _, _ = _sa_trimmed_median_mad(active_baseline)
        recent_avg = sum(recent) / len(recent) if recent else 0.0
        if p50 <= 0 or recent_avg < 1:
            continue
        ratio = recent_avg / p50
        if ratio >= _RETRY_CALLS_RATIO:
            out.append({
                "type": "runaway_retries", "caller": caller,
                "recent_avg_calls": round(recent_avg, 1), "baseline_calls": round(p50, 1),
                "ratio": round(ratio, 2),
                # #543 wording: this measures a multi-day VOLUME TREND vs the 30d baseline. A
                # retry loop is one explanation; a workload-level change (earnings season) is the
                # other — during the 08-06/07 incident this note named only "retry loop" for what
                # was the earnings ramp, reinforcing the anomaly alert's wrong direction.
                "note": f"{caller} call volume is {ratio:.1f}x its 30d baseline "
                        f"({recent_avg:.1f}/day vs {p50:.1f}/day median) — retry loop, "
                        f"or a new workload level?",
            })
    out.sort(key=lambda r: r["ratio"], reverse=True)
    return out


def _reduction_opportunities_from_rows(
    rows, today: date, lookback_days: int = 30, window_days: int = 7,
    daily: "dict | None" = None,
) -> list[dict]:
    """Pure half of detect_reduction_opportunities — shares one already-
    fetched row set with the anomaly detector (see _caller_cost_anomalies_
    from_rows) instead of re-reading api_usage. `daily` may be pre-derived so
    compute_cost_watchdog builds the per-caller series once for both consumers."""
    totals = _caller_window_totals(rows, today, window_days)
    daily = daily if daily is not None else _daily_caller_series(rows)
    out = _reduction_opportunities_from_totals(totals)
    out.extend(_retry_loop_opportunities(daily, today, lookback_days=lookback_days))
    return out


async def detect_reduction_opportunities(
    today: date, lookback_days: int = 30, window_days: int = 7,
) -> list[dict]:
    """Cost-reduction surfacing (#379): Opus-where-Sonnet-fits, oversized
    prompts, and a runaway-retry call-volume trend. Advisory only — no
    auto-apply."""
    rows = await _fetch_caller_window(today, lookback_days)
    return _reduction_opportunities_from_rows(rows, today, lookback_days, window_days)


async def compute_cost_watchdog(today: date, lookback_days: int = 30) -> dict:
    """Combined read for the /cost board appendix + the daily job — ONE
    api_usage fetch feeds both the anomaly detector and the reduction
    heuristics (7/17 api_usage scan-cost discipline: don't read the same
    indexed range twice per caller check)."""
    rows = await _fetch_caller_window(today, lookback_days)
    daily = _daily_caller_series(rows)  # derived ONCE here, shared by all three consumers below
    anomalies = _caller_cost_anomalies_from_rows(rows, today, lookback_days, daily=daily)
    opportunities = _reduction_opportunities_from_rows(rows, today, lookback_days, daily=daily)
    new_lanes = await _unannounced_new_lanes(
        _new_lanes_from_rows(rows, today, lookback_days=lookback_days, daily=daily))
    return {"anomalies": anomalies, "opportunities": opportunities, "new_lanes": new_lanes}


def render_cost_watchdog(w: dict) -> str:
    """Board appendix for /cost. Empty string when nothing to report — keeps
    the happy-path board tight (house style). Dynamic caller/model names
    (snake_case) sit inside the code block, mirroring render_cost_board's
    #477 parity discipline."""
    anomalies = w.get("anomalies") or []
    opportunities = w.get("opportunities") or []
    new_lanes = w.get("new_lanes") or []
    if not anomalies and not opportunities and not new_lanes:
        return ""
    lines = ["*🐕 WATCHDOG*", "```"]
    for n in new_lanes:
        lines.append(f"NEW {n['caller']:<22} ${n['recent_spend']:.2f} / {n['recent_calls']} calls "
                     f"in {n['window_days']}d - never spent before")
    for a in anomalies:
        lines.append(f"! {a['caller']:<24} today ${a['today_spend']:.2f} vs "
                     f"median ${a['median30']:.2f} ({a['ratio']:.1f}x) - {a['leak_class']}")
    for o in opportunities[:5]:
        lines.append(f"* {o['note']}")
    lines.append("```")
    return "\n".join(lines)


async def run_cost_watchdog(today: date) -> dict | None:
    """Daily watchdog check, wired alongside the #378 spend alarm (17:52 ET).
    Telegrams ONLY on a real per-caller $ anomaly (actionable-only, mirrors
    run_daily_spend_alarm's philosophy); reduction opportunities are
    advisory and surface via /cost + this audit row, not a daily push."""
    w = await compute_cost_watchdog(today)
    anomalies, opportunities = w["anomalies"], w["opportunities"]
    new_lanes = w.get("new_lanes") or []
    if not anomalies and not opportunities and not new_lanes:
        return None
    await log_audit_event(
        "cost_watchdog_check",
        summary=f"{len(anomalies)} caller anomaly(ies), {len(opportunities)} reduction opportunity(ies)"
                + (f", {len(new_lanes)} NEW lane(s)" if new_lanes else ""),
        detail=json.dumps(w),
    )
    if new_lanes:
        from agents.market_intelligence.briefing import send_telegram_message
        # Announced ONCE per caller, ever — the audit rows written here are the dedupe state, so
        # they must be written even if the Telegram fails, and BEFORE nothing else can re-announce.
        lines = ["🆕 *NEW SPEND LANE* — something started costing money:", "```"]
        for n in new_lanes[:5]:
            lines.append(f"{n['caller']:<22} ${n['recent_spend']:.2f} / {n['recent_calls']} calls "
                         f"in {n['window_days']}d")
        lines.append("```")
        lines.append("Is it meant to be running, and what is it buying?\n/cost for the full board")
        for n in new_lanes:
            await log_audit_event("cost_new_lane", summary=n["caller"], detail=json.dumps(n))
        await send_telegram_message("\n".join(lines))
    if anomalies:
        from agents.market_intelligence.briefing import send_telegram_message
        # Caller names are snake_case — the #477 parity class means they MUST
        # sit inside the code block, not the plain message body (bare
        # underscores outside a fence break Telegram Markdown V1 italics).
        lines = ["🔴 *COST WATCHDOG* — per-caller spend anomaly:", "```"]
        for a in anomalies[:3]:
            lines.append(f"{a['caller']:<24} ${a['today_spend']:.2f} vs ${a['median30']:.2f} "
                        f"median ({a['ratio']:.1f}x) - {a['leak_class']}")
        lines.append("```")
        lines.append("/cost for the full board")
        await send_telegram_message("\n".join(lines))
    return w


# ── #543 TRUNCATION CHECK — "how do we make sure we don't hit a ceiling again" ─────────────
#
# Operator, 2026-08-07, after theme_assignment ran DEAD for ten days: *"we really need to
# figure out how we can miss this, a complete outage, and it's a bug we've seen before,
# unacceptable."* It IS a bug we had seen before — the same max_tokens ceiling was raised in
# May 2026 for the same silent failure, and raising it bought three months. Raising a ceiling
# is never the answer to this class; DETECTING that a ceiling bound is.
#
# What makes it silent: a truncated forced-tool call is not an error anywhere. The JSON stops
# mid-object, the tool block is unparseable or absent, and the caller's fail-open turns that
# into "proposed 0 cohorts" / a floor grade / None. Every one of those reads as a quiet night.
#
# `api_usage.stop_reason` (this same commit) makes truncation SELF-REPORTING — the model tells
# us it was cut off — instead of inferred from output_tokens against a cap we never stored.
#
# The NULL arm is DEFENCE IN DEPTH since 2026-08-08: the spend trackers now take the raw
# response and derive stop_reason themselves, so a call site structurally cannot omit it (the
# old hand-threaded kwarg was the same copy-paste pattern spend_tracker's own docstring warns
# about, and this arm caught the omissions only next-morning). It stays because it still
# catches what structure cannot: a response whose SHAPE stopped carrying stop_reason, or a
# writer outside the two sanctioned trackers. NULL here should now be genuinely rare — and
# therefore genuinely alarming.

_TRUNC_MIN_CALLS = 2      # 1 truncation on a chatty caller is noise; 2 is a pattern
_TRUNC_PCT_FLOOR = 50.0   # ...unless the caller is low-volume, where 1-of-1 IS the outage shape

# Callers where truncation is DELIBERATE and means nothing is wrong. Found by running the
# check against prod rather than by reasoning about it: `healthcheck` sends the literal word
# "ping" with max_tokens=5 and discards the text — it only cares that the API answered. It
# therefore reports stop_reason='max_tokens' on EVERY call, forever, and would have fired this
# alert every single night. A guard that always fires is not a guard (CLAUDE.md 08-03).
# Keep this list SHORT and justified per entry — it is the one place a real outage could hide.
# Single source since 2026-08-09: shared/output_ceilings.py (the registry the call
# sites themselves import), so the exempt list and the ceilings can never drift apart.
_TRUNC_BY_DESIGN = TRUNCATION_BY_DESIGN


def _near_ceiling(rows, already: set) -> list[dict]:
    """NEAR-CEILING arm (2026-08-09): completed responses inside the last 10% of the
    registry cap (shared/output_ceilings.py). Threshold derivation: measured against
    all 6,634 api_usage rows, every healthy caller's max completed output sits at
    <=86% of its cap while every caller later caught truncating passed >=95% first —
    0.90 sits strictly between, so it is quiet on healthy traffic and fires BEFORE
    the first cut (the truncation arm only fires after corruption happened).

    `already` = callers the truncation arm is reporting this run (reported harder
    there); by-design pings and unregistered callers are skipped — no cap, no margin.
    """
    tight = []
    for r in rows:
        entry = CEILINGS.get(r["caller"])
        mc = r["max_completed"]
        if (entry is None or mc is None or r["caller"] in _TRUNC_BY_DESIGN
                or r["caller"] in already):
            continue
        if mc >= NEAR_CEILING_FRACTION * entry.max_tokens:
            tight.append({"caller": r["caller"], "max_completed": int(mc),
                          "cap": entry.max_tokens,
                          "pct_of_cap": round(100.0 * mc / entry.max_tokens, 1)})
    tight.sort(key=lambda x: -x["pct_of_cap"])
    return tight


async def compute_truncation_check(lookback_hours: int = 24) -> dict:
    """Per-caller truncation + reporting-coverage over the window. Pure read on api_usage.

    ⚠ Rows written BEFORE stop_reason instrumentation existed are excluded, and that is not a
    detail — without it this check cries wolf for a full window after every rollout. It did,
    on its first live night (2026-08-08): it named `theme_synthesis` as a missing call site
    on the strength of one NULL row from the 08-07 nightly theme run — written at 22:05 UTC,
    THREE HOURS before the commit that instrumented that very call site existed. The call
    site was correct; the rows simply predated it, as every row in the table necessarily did.
    A caller cannot be blamed for not reporting a field that had not been built yet.

    The floor is DERIVED from the data (the earliest row that ever carried a stop_reason)
    rather than pinned to a date, so it needs no maintenance and cannot rot. It is also the
    conservative choice: it only ever excludes rows from before the mechanism's very first
    success, so a genuine wiring gap that appears AFTER instrumentation exists is still
    caught in full — which is the case this check is actually for.
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        # When did stop_reason first get recorded at all? Everything before this instant is
        # pre-instrumentation and carries no information about call-site wiring.
        floor = await conn.fetchval(
            "SELECT min(created_at) FROM api_usage WHERE stop_reason IS NOT NULL")
        if floor is None:
            # No call has EVER reported a stop_reason. That is not "nothing to report" — it
            # means the mechanism itself is dark, which is strictly worse than any single
            # caller being unwired. Returning an empty result here would be the exact silent
            # pass this check exists to prevent, so it gets its own louder signal.
            # `since=None` IS that signal — one result shape, no separate boolean to keep in
            # sync with it.
            return {"window_hours": lookback_hours, "truncating": [], "unreported": [],
                    "tight": [], "since": None}

        rows = await conn.fetch("""
            SELECT caller,
                   count(*)                                                    AS calls,
                   count(*) FILTER (WHERE stop_reason = 'max_tokens')          AS truncated,
                   count(*) FILTER (WHERE stop_reason IS NULL)                 AS unreported,
                   max(output_tokens) FILTER (WHERE stop_reason = 'max_tokens') AS cap_hit,
                   max(output_tokens) FILTER (WHERE stop_reason IS NOT NULL
                                              AND stop_reason <> 'max_tokens') AS max_completed
              FROM api_usage
             WHERE created_at > now() - ($1 || ' hours')::interval
               AND created_at >= $2
             GROUP BY 1
        """, str(int(lookback_hours)), floor)

    truncating, unreported = [], []
    for r in rows:
        calls, trunc = int(r["calls"]), int(r["truncated"])
        if trunc and r["caller"] not in _TRUNC_BY_DESIGN:
            pct = round(100.0 * trunc / calls, 1)
            if trunc >= _TRUNC_MIN_CALLS or pct >= _TRUNC_PCT_FLOOR:
                truncating.append({"caller": r["caller"], "calls": calls, "truncated": trunc,
                                   "pct": pct, "cap": r["cap_hit"]})
        # Only a caller reporting NOTHING is a wiring gap. A partial NULL count means the
        # provider omitted the field on some responses, which is not a call-site defect.
        if int(r["unreported"]) == calls:
            unreported.append({"caller": r["caller"], "calls": calls})

    tight = _near_ceiling(rows, already={x["caller"] for x in truncating})

    truncating.sort(key=lambda x: (-x["pct"], -x["truncated"]))
    return {"window_hours": lookback_hours, "truncating": truncating,
            "unreported": unreported, "tight": tight, "since": floor.isoformat()}


async def run_truncation_check() -> dict | None:
    """Daily, wired into the 17:52 ET spend job.

    Takes NO `today` — unlike its two siblings in this file, which genuinely window by date.
    This one always looks at the last 24 hours, and a parameter that lies about being
    load-bearing is worse than no parameter: the next reader assumes it windows the query. Telegrams on ANY confirmed truncation
    (actionable-only house rule — a truncated response is silent data corruption, not a
    cost curiosity). Deliberately NOT deduped: the original went quiet for ten days
    precisely because its only trace looked routine, so this keeps shouting nightly until
    the ceiling is fixed."""
    t = await compute_truncation_check()
    truncating, unreported = t["truncating"], t["unreported"]
    tight = t["tight"]
    if t["since"] is None:
        # Worse than any single unwired caller: nothing anywhere is reporting stop_reason,
        # so truncation is once again undetectable. Shout, and do not dedupe.
        await log_audit_event(
            "llm_truncation_check",
            summary="stop_reason is dark — NO api_usage row has ever reported one",
            detail=json.dumps(t))
        from agents.market_intelligence.briefing import send_telegram_message
        await send_telegram_message(
            "🔴 *TRUNCATION DETECTION IS DARK*\n"
            "No API call has ever recorded why the model stopped, so a cut-off "
            "response cannot be told from a complete one. This is the outage the "
            "check exists to catch, one level up.")
        return t
    if not truncating and not unreported and not tight:
        return None
    await log_audit_event(
        "llm_truncation_check",
        summary=(f"{len(truncating)} caller(s) truncating, "
                 f"{len(unreported)} not reporting stop_reason, "
                 f"{len(tight)} within 10% of their ceiling"),
        detail=json.dumps(t),
    )
    from agents.market_intelligence.briefing import send_telegram_message
    # Caller names are snake_case — #477 parity: they MUST sit inside the code fence or bare
    # underscores break Telegram Markdown V1 italics.
    lines = []
    if truncating:
        lines += ["🔴 *TRUNCATED* — responses cut off by max_tokens (silent corruption):", "```"]
        for x in truncating[:6]:
            lines.append(f"{x['caller']:<28} {x['truncated']}/{x['calls']} calls "
                         f"({x['pct']}%) at {x['cap']} tokens")
        lines += ["```", "Raise the ceiling on these callers - a cut-off tool call "
                  "reads downstream as an empty result, not an error."]
    if tight:
        if lines:
            lines.append("")
        lines += ["🟡 *NEAR CEILING* — completed responses within 10% of their cap:", "```"]
        for x in tight[:6]:
            lines.append(f"{x['caller']:<28} {x['max_completed']} of {x['cap']} tokens "
                         f"({x['pct_of_cap']}%)")
        lines += ["```", "Raise these in `shared/output_ceilings.py` BEFORE they start "
                  "cutting responses."]
    if unreported:
        if lines:
            lines.append("")
        lines += ["🟠 *NOT REPORTING* — these callers cannot be checked for truncation:", "```"]
        for x in unreported[:6]:
            lines.append(f"{x['caller']:<28} {x['calls']} call"
                         f"{'' if x['calls'] == 1 else 's'}, stop_reason always NULL")
        # NOT "the call site is missing stop_reason" any more — since 2026-08-08 the trackers
        # derive it from the response, so a call site structurally cannot omit it. Saying
        # otherwise sends the reader to inspect a call site that is provably correct, which
        # is exactly what happened the first night this fired.
        lines += ["```", "The trackers derive stop_reason from the response, so this is NOT "
                  "a missing kwarg: either the response shape stopped carrying stop_reason, "
                  "or something outside the two spend trackers is writing api_usage rows."]
    await send_telegram_message("\n".join(lines))
    return t
