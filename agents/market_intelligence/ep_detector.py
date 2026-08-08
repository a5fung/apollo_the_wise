"""
EP (Episodic Pivot) Detector.

Scans pre-market for gap-up stocks and scores them using the MAGNA53 model
(Pradeep Bonde / Kullamägi methodology).

Hard filters (applied BEFORE scoring — stocks that fail never reach the DB or briefing):
- Gap ≥ 8% vs previous close
- Previous close ≥ $5, previous day volume ≥ 50K shares
- Post-open only: relative volume ≥ 2x ADV. Pre-market: only 25K share floor (pre-market vol is structurally tiny vs full-day ADV even on huge news days — gap + catalyst carry the signal)
- Pre-trade quality: ADV dollar volume ≥ $1M, ATR% ≤ 15%, market cap ≥ $500M
  (same check_filters used by backtester/tracker — single source of truth)
- Extension: skip if already up ≥ 50% in last 5 trading days
- Cooldown: skip if this ticker had an EP alert in last 60 days
- No M&A/buyout catalysts

MAGNA53 scoring (0-100):
- Gap magnitude:     20%+ = 25pts, 15%+ = 20pts, 10%+ = 15pts, 8-9% = 10pts
- Catalyst quality:  game-changer = 25pts, strong = 15pts, routine = 0pts
- Relative volume:   5x+ ADV = 15pts, 2-4x = 10pts, 1-2x = 5pts
- Neglect period:    6mo+ base = 15pts, 3mo = 8pts
- Volume conviction: pre-mkt vol ≥90th pct = 5pts, ≥70th = 3pts
- Analyst upgrades:  3+ = 5pts
- Low float:         <50M shares = 5pts
- Market multiplier: Bull regime = 1.2x, Perplexity agreement = 1.2x (stack)

Max raw: 95. A 20%+ game-changer gap scores ≥70 before bonuses.
Thresholds: ≥ ep_threshold (regime-dependent) = HIGH, 50-69 = MODERATE, <50 = skip
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import random
import re
from datetime import date, datetime, timedelta
from typing import Any, NamedTuple, Optional

import anthropic

from agents.market_intelligence.collector import et_today
from agents.market_intelligence.collector import (
    get_snapshot_all,
    get_index_history,
    get_fmp_profile,
    get_fmp_earnings,
    get_fmp_news,
    get_alpaca_news,
    is_primary_subject_news,
    search_news_perplexity,
    get_sec_recent_filings,
)
from agents.market_intelligence.constants import SKIP_TICKERS
from agents.market_intelligence.db import insert_ep_alert, get_adv_map, get_latest_regime, get_volume_history, get_pool, log_ep_scan_candidates, log_audit_event, enqueue_pending_allocation, get_runtime_toggle, LIVE_SOURCE_SQL
from agents.market_intelligence.backtester.filters import check_filters
from agents.market_intelligence.minute_volume import (
    compute_rvol_at_time,
    MIN_PM_RVOL,
    MIN_SESSION_RVOL,
    MIN_BASELINE_N_FOR_GATE,
)
from agents.market_intelligence.broker.skip_reasons import (
    FILTER_MCAP_TOO_SMALL,
    FILTER_PM_RVOL_TOO_LOW,
    FILTER_SESSION_RVOL_TOO_LOW,
)
from agents.market_intelligence.ma_filter import is_likely_ma
from agents.market_intelligence.earnings_calendar import is_earnings_day, is_revenue_stage
from shared.llm_models import GROUNDED_GRADE_MODEL
# MODEL (not JUDGE_MODEL) — #509: the audit trail must record the id that
# ACTUALLY graded the call. grade_holistic()'s default `model=` is bound to
# ep_grade_judge.MODEL (resolver-tracked); shared.llm_models.JUDGE_MODEL is
# only the committed pin the deploy gate checks, and can lag the live value.
from agents.market_intelligence.ep_grade_judge import MODEL as _JUDGE_MODEL_ACTUAL
from agents.market_intelligence.ep_grade_judge import RUBRIC_HASH, RUBRIC_VERSION

logger = logging.getLogger(__name__)

# Observe-lane per-day dedup (tiny-cap movers: one audit row per ticker/day).
_tinycap_seen_date = None
_tinycap_seen: set = set()

# Catalyst-grade prompt era (operator directive 2026-06-11 — see
# ep_grade_judge.RUBRIC_VERSION for the scheme). Bump on every signed change
# to the _classify_catalyst_claude prompt; stamped on ep_grade_decision rows.
# v1 = pre-#269. v2 = #269 revenue-over-EPS + sustainable-turnaround.
CATALYST_GRADE_PROMPT_VERSION = "v3-2026-06-12-catalyst-freshness"

# Hard filters
# MIN_GAP_PCT: 2026-05-17 R2 ship — lifted 8.0 → 10.0. The 8-10% gap
# bucket had 0/8 WR over the 60d cohort (ADR 0003 §3). Env override
# available via EP_MIN_GAP_PCT for fast rollback without redeploy.
_MIN_GAP_PCT_DEFAULT = 10.0
MIN_GAP_PCT = float(os.environ.get("EP_MIN_GAP_PCT", _MIN_GAP_PCT_DEFAULT))

# #489 hybrid real-time detection (Alpaca SIP Pass-2). Master flag: when ON, Pass-1 admits at the
# (lower) superset so fast movers whose ~15-min-DELAYED Polygon gap is still <10% survive to the
# real-time Alpaca confirm, then the REAL 10% MIN_GAP_PCT floor is re-applied on the rt gap. The
# gap_pct AUTHORITY is the separate `ep_rt_gap_authoritative` runtime toggle (default off = shadow:
# rt logged alongside, delayed still decides). All OFF (default) = byte-identical to today.
EP_RT_PASS2_ENABLED = os.environ.get("EP_RT_PASS2_ENABLED", "false").lower() == "true"
EP_PASS1_SUPERSET_GAP_PCT = float(os.environ.get("EP_PASS1_SUPERSET_GAP_PCT", 5.0))
# #489 real-time MISS watchdog (observability, ALERT-ONLY — never changes what we enter): each in-window
# tick it checks the full RT universe live and LOUD-Telegrams any 10% crosser the ~15-min-delayed screen
# missed. It is the #490 Pass-0 fetch in observe mode (doubles as the full-cutover shadow). Default on
# when the RT infra (EP_RT_PASS2_ENABLED) is on; own kill switch.
EP_RT_MISS_WATCHDOG_ENABLED = os.environ.get("EP_RT_MISS_WATCHDOG_ENABLED", "true").lower() == "true"

# ── #490 FULL real-time detection — RT-1 dark build (design signed 2026-07-24,
# docs/analysis/490_full_realtime_design_2026-07-25.md). Master flag OFF (deploy default) =
# byte-identical to the #489 hybrid: Pass-0 never fetches, no overlay, no volume shadow.
# When ON: overlay real-time Alpaca SIP prices on the full ~3,325-ticker RT universe every
# scan tick. gap AUTHORITY stays the separate `ep_rt_universe_authoritative` runtime toggle
# (mi_safeguard_state, ~60s, no deploy — default off = shadow: rt logged + catch events only,
# delayed still decides). Volume authority is `ep_rt_volume_authoritative` (own toggle, §6.1,
# flipped ≥3 market days after the gap per the cutover ladder). Rollback rungs R1-R5: §8.
EP_RT_UNIVERSE_ENABLED = os.environ.get("EP_RT_UNIVERSE_ENABLED", "false").lower() == "true"
EP_RT_UNIVERSE_CONCURRENCY = int(os.environ.get("EP_RT_UNIVERSE_CONCURRENCY", "1"))
EP_RT_UNIVERSE_TIMEOUT_S = float(os.environ.get("EP_RT_UNIVERSE_TIMEOUT_S", "15"))
# §3 tick-quality guard thresholds (Q1-Q4) — env-tunable, rejections LOUD
# (`ep_rt_tick_quality_reject` + reason enum; the C1 silent-clamp lesson mechanized).
# #490 SUSTAIN rule (operator-signed 2026-08-02, N=3). A price level that holds across N
# consecutive minutes is a LEVEL; a level touched in one minute and gone is a PRINT. Same reasoning
# as the Q3 print-corroboration guard, one level up: Q3 asks "is this print real", this asks "is this
# LEVEL real". Evidence + the overfitting caveat the operator raised himself:
# docs/analysis/490_change_proposal_sustain_rule_2026-08-02.md.
# BACKWARD-looking only — a forward wait would push detection past the 09:45 ORB cutoff and recreate
# the very miss #490 exists to remove.
EP_RT_SUSTAIN_BARS = int(os.environ.get("EP_RT_SUSTAIN_BARS", "3"))
EP_RT_SUSTAIN_LOOKBACK_MIN = int(os.environ.get("EP_RT_SUSTAIN_LOOKBACK_MIN", "15"))
EP_RT_QBAND_PCT = float(os.environ.get("EP_RT_QBAND_PCT", "0.5"))                       # Q1 NBBO band width
EP_RT_QUOTE_MAX_AGE_PREOPEN_S = float(os.environ.get("EP_RT_QUOTE_MAX_AGE_PREOPEN_S", "300"))  # Q2 pre-open
EP_RT_QUOTE_MAX_AGE_RTH_S = float(os.environ.get("EP_RT_QUOTE_MAX_AGE_RTH_S", "30"))    # Q2 RTH
EP_RT_BAR_MAX_AGE_S = float(os.environ.get("EP_RT_BAR_MAX_AGE_S", "600"))               # Q3 bar age ≤ 10 min
EP_RT_INSANE_GAP_PCT = float(os.environ.get("EP_RT_INSANE_GAP_PCT", "200"))             # Q4 absolute insanity bound
EP_RT_HALT_TRADE_AGE_S = float(os.environ.get("EP_RT_HALT_TRADE_AGE_S", "90"))          # §4 halt-suspect trade age


def _pass1_gap_floor() -> float:
    """The Pass-1 (delayed universe screen) gap floor: the lower superset when the hybrid is on,
    else the real MIN_GAP_PCT. The superset only WIDENS Pass-1; the authoritative 10% floor is
    always re-applied to the decided gap in Pass 2 (`_apply_realtime_pass2`), so it can never leak."""
    return EP_PASS1_SUPERSET_GAP_PCT if EP_RT_PASS2_ENABLED else MIN_GAP_PCT
MIN_PREMARKET_SHARES = 25_000  # Absolute minimum — filters micro-float noise
MIN_PREV_CLOSE = 5.0           # Skip sub-$5 stocks — noise, not EPs
MAX_TICKER_LEN = 5             # Skip warrants/units (long symbols like ABCDW)
MIN_PREV_DAY_VOLUME = 50_000   # Skip illiquid stocks — stale quotes create phantom gaps

# Auto-disqualifiers (hard filters — applied before scoring)
MAX_EXTENSION_PCT = 50.0   # Skip if already up 50%+ in last 5 trading days before the gap
EP_COOLDOWN_DAYS = 60       # Skip if this ticker had an EP alert in last 60 days
# #170 shadow (2026-06-01): a cooldown-suppressed candidate that gapped hard
# >= this many days after its prior alert is likely a RE-SETUP (the prior EP has
# played out), not a re-fire — backward-check 2026-06-01 showed these ran ~2x
# the alerted cohort. Telemetry-only for now (cooldown_resetup_admit_shadow);
# live admission gated on realized-R per CHANGE_PROCESS (#170).
EP_COOLDOWN_RESETUP_MIN_DAYS = 10


def _is_cooldown_resetup(gap_pct: float, days_since_prior_alert: int | None,
                         min_days: int = EP_COOLDOWN_RESETUP_MIN_DAYS) -> bool:
    """#170 telemetry classifier: True if a cooldown-suppressed candidate looks
    like a RE-SETUP rather than a still-extended re-fire — a hard gap (>=15%)
    far enough (>= min_days) after the prior alert that the prior EP has played
    out. Shadow-only; does NOT change suppression."""
    return (
        days_since_prior_alert is not None
        and days_since_prior_alert >= min_days
        and gap_pct >= 15.0
    )


# Leveraged/inverse ETFs and broad ETFs — never real EPs
_SKIP_TICKERS = SKIP_TICKERS

# Catalyst cache — FMP + Claude + Perplexity results for today.
# A stock oscillating near the 15% conviction threshold (e.g. BE at 13-15%)
# gets re-scored every 5 min. The catalyst doesn't change; skip the API calls.
# filters_cleared (S6/#405, 2026-07-03): True once the ticker has passed the
# 3 post-grade filters (M&A / routine-catalyst / pm-shares floor) — the cache
# now stores a grade THE MOMENT IT COMPLETES, even for filter-failing tickers,
# so they never trigger a full LLM re-grade on a later tick. See
# `_post_grade_filters` — it re-runs the (time-sensitive) filters against the
# cached grade fields every tick with zero LLM calls.
# Resets automatically when the calendar date changes.
# The classify-failure sentinel (7/4 review F4): PROSE-COUPLED control flow —
# the producer (_classify_catalyst_claude's failure return) and BOTH #347 checks
# (the flip's APOG fallback + the repoll validity gate) key off this literal.
# Reword ONLY here.
_CLASSIFY_FAIL_SENTINEL = "Classification failed"


class CachedGrade(NamedTuple):
    """Catalyst-cache value shape (simplify GROUP 1, 2026-07-03) — was a
    positional 6-tuple; named fields + `_replace()` for the single-field
    updates at the earnings-boost / downgrade call sites. Zero behavior
    change from the prior tuple (still a tuple; positional access/unpack
    still works, but every write site now uses named fields or `_replace`)."""
    catalyst_quality: str
    confidence_multiplier: float
    news_summary: str
    claude_analysis: "str | None"
    pplx_quality: "str | None"
    filters_cleared: bool
    # 7/4 review (Finding-2): the grade-time corpus rides the cache so a
    # cached-path-fired alert no longer inserts grounded_text=NULL (15/43 of
    # 30d alerts had an empty corpus — the judge graded them blind and the
    # #367 attribution read was contaminated). Default None keeps every
    # existing positional construction/_replace valid.
    grounded_text: "str | None" = None
    # #405 Part-1 (7/9): has_direct_source rides the cache so a cached-path re-grade PRESERVES
    # the display flag. Was dropped (the cached path left `_has_direct_source=None` → the
    # catalyst discovery line was kept as the safe default even when the grade rested on a
    # direct source; #317/#405-P2 suppress-on-direct-source). Same corpus across a quality
    # re-grade, so `_replace` on other fields preserves it. Default None = flag absent (safe).
    has_direct_source: "bool | None" = None


_catalyst_cache: dict[str, CachedGrade] = {}
_catalyst_cache_date: "date | None" = None


# Prose-mismatch downgrade markers (#72, 2026-05-11). When the catalyst
# classifier returns "strong" but the prose explicitly says "no catalyst" or
# "no fresh news", the classifier is over-weighting volume/gap features
# against hedged news. MRAM 5/11 was the motivating case (-$2200 compound
# loss). Only fires when earnings backstop did NOT fire — MNDY 5/11 had
# the same prose pattern but was earnings day, the boost correctly graded
# it strong, downgrade must not fight the boost.
from agents.market_intelligence.prose_markers import NEGATIVE_CATALYST_MARKERS_BASE

# EP downgrade fires on the shared base plus the EP-specific shorter form
# "no specific news" (catches summaries that don't include " or catalyst" tail).
_PROSE_NEGATIVE_MARKERS = NEGATIVE_CATALYST_MARKERS_BASE + (
    "no specific news",
)

# Per-day audit dedupe: keys (ticker, date, event_type). EP scan runs every 5 min
# from 7:00–10:00 ET (~36 ticks); without dedup, the same ticker emits ~36 rows
# of `earnings_override_no_match` / `tape_conviction_shadow` per day.
_audit_dedupe: set[tuple[str, "date", str]] = set()
_audit_dedupe_date: "date | None" = None

def _audit_dedupe_check(ticker: str, scan_date: "date", event: str) -> bool:
    """Returns True if (ticker, date, event) hasn't been logged this session.

    In-memory only — wiped on container restart. Use the DB-backed
    `_should_log_catalyst_earnings_event_today` for events that must
    survive restarts (the catalyst-earnings family is restart-sensitive
    because _catalyst_cache also gets wiped).
    """
    global _audit_dedupe, _audit_dedupe_date
    if _audit_dedupe_date != scan_date:
        _audit_dedupe.clear()
        _audit_dedupe_date = scan_date
    key = (ticker, scan_date, event)
    if key in _audit_dedupe:
        return False
    _audit_dedupe.add(key)
    return True


# Heuristic: does Claude's analysis text describe an earnings catalyst?
# Used as a textual fallback when yfinance earnings_dates / forward calendar
# don't surface today (CRSR 2026-05-27 — clean Q1 numbers in Claude prose,
# but yfinance no_match → extraction never ran → no rubric). Catches the
# "ingest lag" class the AGYS hotfix was designed for, one layer earlier.
_EARNINGS_TEXT_SIGNAL_RE = re.compile(
    r"\b(?:"
    r"reported\s+(?:Q[1-4]|first[- ]quarter|second[- ]quarter|third[- ]quarter|fourth[- ]quarter|quarterly|annual|full[- ]year)"
    r"|Q[1-4]\s+(?:20\d{2}|FY\d{2,4})\s+earnings"
    r"|(?:beat|missed|matched)\s+(?:consensus|estimates|analyst\s+estimates)"
    r"|revenue\s+(?:of\s+)?\$[\d.]+\s*[BMK]"
    r"|EPS\s+of\s+\$[\d.]+"
    r"|earnings\s+(?:release|report|results)"
    r")\b",
    re.IGNORECASE,
)


def _claude_text_signals_earnings(claude_analysis: str | None) -> bool:
    if not claude_analysis:
        return False
    return bool(_EARNINGS_TEXT_SIGNAL_RE.search(claude_analysis))


def _should_apply_yoy_carveout(extracted: dict) -> bool:
    """Carve-out predicate (2026-05-28): when the only downgrade reason is
    missing YoY but the extraction captured a positive beat + a directional
    guidance signal with high/medium confidence, the LLM grade is more
    trustworthy than the safety net.

    Returns True iff downgrade should be SKIPPED. See
    `docs/setups/catalyst_rubric.md` 2026-05-28 entry for full spec + evidence.
    """
    qr = extracted.get("q_revenue_usd") or {}
    gc = extracted.get("guidance_change") or {}
    beat = qr.get("beat_vs_est_pct")
    g_dir = gc.get("direction")
    g_conf = gc.get("confidence")
    return (
        isinstance(beat, (int, float)) and beat > 0
        and g_dir in ("raised", "initiated", "reaffirmed")
        and g_conf in ("high", "medium")
    )


async def _revenue_weak_downgrade_logged_today(ticker: str) -> bool:
    """Returns True iff a `catalyst_earnings_revenue_weak_downgrade` audit
    row exists for `ticker` on the current ET trading day. Fail-open: any
    DB error returns False so the caller does NOT skip the override — that
    preserves the original news-ingest-lag tolerance.
    """
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT 1 FROM mi_audit_log
                WHERE event_type = 'catalyst_earnings_revenue_weak_downgrade'
                  AND summary LIKE $1
                  AND (created_at AT TIME ZONE 'America/New_York')::date
                      = (NOW() AT TIME ZONE 'America/New_York')::date
                LIMIT 1
                """,
                f"{ticker}:%",
            )
            return row is not None
    except Exception as e:
        logger.debug(f"earnings_override downgrade-check failed: {e}")
        return False


async def _should_log_catalyst_earnings_event_today(event_type: str, ticker: str) -> bool:
    """DB-backed dedup for catalyst_earnings_* family. Returns True iff no
    prior row exists for (event_type, ticker) on the current ET trading day.

    Why DB-backed instead of `_audit_dedupe_check`: the in-memory dedup is
    wiped on container restart, but _catalyst_cache is ALSO wiped, so the
    boost block re-fires on the first scan tick after each restart. 2026-05-26
    had 3 restarts and JOYY/MOD/ESLT boost-event counts of 28/15/14 (vs 1
    each expected). DB-backed dedup is restart-immune. Same shape as #89
    M&A filter and #85 convergence-alert dedups.

    Fail-open: any DB error returns True (caller proceeds to log). Better
    to over-log than silently drop a catalyst-grade decision audit.
    """
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            prior = await conn.fetchrow("""
                SELECT 1 FROM mi_audit_log
                WHERE event_type = $1
                  AND summary LIKE $2
                  AND (created_at AT TIME ZONE 'America/New_York')::date
                      = (NOW() AT TIME ZONE 'America/New_York')::date
                LIMIT 1
            """, event_type, f"{ticker}:%")
        return prior is None
    except Exception as e:
        logger.debug(f"catalyst earnings dedup check failed (non-critical): {e}")
        return True

_claude = None
# Cap concurrent Anthropic calls — earnings days can gap 30+ stocks simultaneously,
# and unbounded parallel requests → 429s → degraded catalyst classification.
_ANTHROPIC_SEMAPHORE = asyncio.Semaphore(5)
# #240 judge runs in the SAME post-loop gather as catalyst_type/fire (the live #201
# advisory). A separate semaphore keeps the larger 6000-char judge call concurrent with —
# not starving — the catalyst grader under the 9:45 ORB cutoff.
_JUDGE_SEMAPHORE = asyncio.Semaphore(3)


def _get_claude():
    global _claude
    if _claude is None:
        _claude = anthropic.AsyncAnthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))
    return _claude


def _resolve_grade_authority(judge_authority: bool, verdict: "dict | None", floor_tier):
    """Pure W2c (#243 / ADR 0011) grade-authority decision — returns
    (score_tier, grade_engine_authority, db_override). Toggle OFF → floor keeps authority,
    NO override (byte-identical to shadow). ON + verdict → the judge tier drives the grade
    (promote/hold/demote, incl. 'none' → suppression downstream). ON + None → FAIL-OPEN to
    the floor tier, authority 'fallback' (counted). Extracted pure so the load-bearing
    branch logic is unit-tested independent of the scan loop."""
    if not judge_authority:
        return floor_tier, "floor", False
    if verdict is not None:
        return verdict["tier"], "judge", True
    return floor_tier, "fallback", True


def _resolve_catalyst_text(claude_analysis, news_summary, has_direct_source, limit):
    """Pick the text persisted to the alert's `catalyst` field (#360 / CHANGE_PROCESS
    2026-06-23, operator-signed).

    WHY: the Perplexity `news_summary` is a DISCOVERY narrative — when Perplexity can't
    find the catalyst it confabulates a disclaimer ("no specific catalyst"), which then
    CONTRADICTS the grade that was grounded on a primary source. QURE alert 12310 is the
    proof case: its stored `catalyst` disclaimed a catalyst while `claude_analysis`
    (grounded on the 8-K) correctly led with the FDA AMT-130 BLA. The principle: the LLM
    is the JUDGE of grounded text, NOT a discoverer. So when a DIRECT/primary source was
    found (`has_direct_source` truthy), prefer the grounded `claude_analysis`; otherwise
    keep the existing Perplexity narrative.

    Fail-safe: the grounded branch requires a NON-EMPTY claude_analysis (it can be None on
    an LLM-call failure), so a failed grade falls back to `news_summary` rather than
    blanking the field. NEVER returns blank by construction — the fallback is exactly the
    pre-#360 line `news_summary[:limit]` (which may itself be "" if there's no news), so the
    no-direct-source path is byte-identical to prior behavior. Same clip limit as before —
    #360 changes only WHICH field sources the text, not the clip."""
    if has_direct_source and claude_analysis and claude_analysis.strip():
        return claude_analysis[:limit]
    return news_summary[:limit]


async def _emit_grade_decision(r: dict, floor_tier, verdict: "dict | None") -> None:
    """Comprehensive per-candidate grade decision trace (W2a #243 / ADR 0011 logging
    requirement — OPERATOR-signed). ONE `ep_grade_decision` audit row per graded candidate
    (verdict, hold, OR null) so any grade is fully reconstructable for review/debug/tune:
    floor vs judge tier, the engine that drove it (`authority`), the judge's load-bearing
    rationale, and the inputs. `judge_outcome` makes the fail-open ('null') case explicit +
    COUNTED (the silent-degradation guard). Error-wrapped — logging never breaks the scan."""
    try:
        v = verdict or {}
        outcome = "verdict" if verdict is not None else "null"
        direction = v.get("direction_vs_floor") or "none"
        payload = {
            "authority": r.get("grade_engine_authority", "floor"),
            "judge_outcome": outcome,
            # Prompt-era versioning (operator directive 2026-06-11): every
            # decision row records WHICH rubric/grader text produced it, so
            # evals/replays segment by era instead of silently mixing.
            "rubric_version": RUBRIC_VERSION,
            "rubric_hash": RUBRIC_HASH,
            "grade_prompt_version": CATALYST_GRADE_PROMPT_VERSION,
            "judge_model": _JUDGE_MODEL_ACTUAL,
            "floor_tier": floor_tier,
            "floor_catalyst_quality": r.get("catalyst_quality"),
            "judge_grade": v.get("grade"),
            "judge_tier": v.get("tier"),
            "judge_direction": v.get("direction_vs_floor"),
            "judge_materiality_tier": v.get("materiality_tier"),
            "fire_axes": v.get("fire_axes"),
            "confidence": v.get("confidence"),
            "rationale": v.get("rationale"),
            "gap_pct": r.get("gap_pct"),
            "ep_score": r.get("ep_score"),
            "in_active_theme": bool(r.get("in_active_theme")),
            "in_narrative_cohort": bool(r.get("in_narrative_cohort")),
            "materiality_tier": r.get("materiality_tier"),
            "market_cap": r.get("market_cap"),
            "sector": r.get("sector"),
            # #329 data-readiness: log has_direct_source so the monthly judge review can track,
            # over time, how often the judge graded WITHOUT seeing a direct source (the call-site
            # blindness this trace exposes). Available on r since #317; the judge doesn't yet
            # CONSUME it (that's the #335 flip) — logging it here makes the gap measurable.
            "has_direct_source": r.get("has_direct_source"),
            # #332 (C1 setup-class classifier, ADR 0028) — P0 VISIBILITY: rides this trace so
            # every decision row is class-splittable too. Set on `r` just above the judge
            # payload assembly in _judge_shadow; None when the classifier failed or hasn't
            # run yet (never gates/affects anything on this row).
            "setup_class": r.get("setup_class"),
        }
        detail = (f"{r.get('ticker')} floor={floor_tier} judge={v.get('tier')} "
                  f"dir={direction} outcome={outcome}")
        await log_audit_event("ep_grade_decision", detail, json.dumps(payload, default=str))
    except Exception as _e:  # noqa: BLE001 — observability must never break the scan
        logger.debug(f"ep_grade_decision emit skipped for {r.get('ticker')}: {_e}")


async def _compute_adv_from_polygon(ticker: str, trade_date: date, days: int = 20) -> Optional[float]:
    """Fetch recent daily bars from Polygon and compute 20-day median daily volume.
    Used for EP candidates not in the RS universe.
    Uses median (not mean) — consistent with get_adv_from_daily_closes in db.py."""
    from_date = (trade_date - timedelta(days=days * 2)).strftime("%Y-%m-%d")  # fetch extra for weekends/holidays
    to_date = (trade_date - timedelta(days=1)).strftime("%Y-%m-%d")  # exclude today
    bars = await get_index_history(ticker, from_date, to_date)
    volumes = sorted(b["v"] for b in bars if "v" in b and b["v"] > 0)
    if len(volumes) < 5:
        return None  # not enough data
    recent = volumes[-days:] if len(volumes) > days else volumes
    # Median: immune to single-day volume spikes that would inflate mean
    mid = len(recent) // 2
    if len(recent) % 2 == 1:
        return float(recent[mid])
    return float((recent[mid - 1] + recent[mid]) / 2)


_CATALYST_TOOL = {
    "name": "classify_catalyst",
    "description": "Classify the quality of a stock EP catalyst and provide analysis.",
    "input_schema": {
        "type": "object",
        "properties": {
            "quality": {
                "type": "string",
                "enum": ["game_changer", "strong", "routine", "mna"],
                "description": (
                    "game_changer: massive earnings beat + guidance raise, FDA approval, "
                    "transformative contract. strong: solid beat + guidance raise, analyst "
                    "upgrade cluster, major partnership. routine: in-line results, no "
                    "company-specific catalyst. mna: merger, acquisition, buyout, takeover, "
                    "going-private, tender offer, or any deal where the company is being acquired — "
                    "price is capped at deal value, no momentum trade possible."
                ),
            },
            "analysis": {
                "type": "string",
                "description": "2-3 sentences on the specific catalyst and classification rationale.",
            },
        },
        "required": ["quality", "analysis"],
    },
}


def build_grounded_text(
    sec_filing: Optional[dict],
    benzinga_items: list[dict],
    perplexity_answer: Optional[str],
) -> Optional[str]:
    """Assemble the grounded catalyst corpus the grade reasons on.

    Ordered primary-first: SEC filing body → Benzinga press wires (#210 Wave A)
    → web synthesis. Shared by run_ep_scan and the offline re-grade validation
    so both build the byte-identical string. Every input is already
    error-wrapped at fetch (returns [] / None), so this never raises.
    """
    parts: list[str] = []
    if sec_filing:
        parts.append(
            f"[SEC {sec_filing['form']} filed {sec_filing['filed']}, items {sec_filing['items']}] {sec_filing['text']}")
    for b in benzinga_items:
        created = (b.get("created_at") or "")[:10]
        body = (b.get("summary") or b.get("content") or "").strip()
        parts.append(f"[Benzinga {created}] {(b.get('title') or '').strip()}. {body}".strip())
    if perplexity_answer:
        parts.append(f"[Web summary] {perplexity_answer}")
    return "\n\n".join(parts) or None


def corpus_provenance(sec_filing: Optional[dict],
                      benzinga_items: list[dict],
                      perplexity_answer: Optional[str],
                      grounded_text: Optional[str],
                      fmp_news: list[dict]) -> dict:
    """Source-class provenance of what the GRADE actually consumed (#210 Wave B).

    Returns {"sources": {class: count}, "has_direct_source": bool}. Mirrors the
    grader's INPUT BRANCH, not build_grounded_text — they diverge in the
    fallback: `_classify_catalyst_claude` reasons on `grounded_text` (SEC +
    Benzinga + web) when present, else falls back to `all_news` = fmp headlines.
    So an fmp-only mover records `fmp_aggregator`, NOT `{}` — "aggregator-only"
    and "total silence" are different sourcing gaps for #211.

    `has_direct_source` is the load-bearing field: graded strong/game_changer
    with it False = the sourcing-gap cohort the #211 KPI drives down. Derived
    structurally (`sec_*` or `benzinga_pr`) so Wave D's `sec_425` counts direct
    automatically. Deterministic, no I/O.
    """
    sources: dict[str, int] = {}
    if grounded_text:
        if sec_filing:
            form = (sec_filing.get("form") or "").lower().replace("-", "")  # 8-K -> 8k
            sources[f"sec_{form}" if form else "sec"] = 1
        if benzinga_items:
            sources["benzinga_pr"] = len(benzinga_items)
        if perplexity_answer:
            sources["web_perplexity"] = 1
    elif fmp_news:
        # Grade fell back to all_news (fmp headlines) — aggregator-only coverage.
        sources["fmp_aggregator"] = len(fmp_news)
    has_direct = any(k.startswith("sec_") or k == "benzinga_pr" for k in sources)
    return {"sources": sources, "has_direct_source": has_direct}


# ── #344 corpus-completeness enrichment (SSoT — the replay imports these) ──────────
# Today's news alone under-grades a catalyst that is an UPDATE to an existing material
# partnership (BFLY 6/18: the $74M Midjourney co-dev license was in a prior 8-K, not the
# 6/18 PR). These helpers assemble a grade corpus that adds clearly-DATED prior
# material-agreement + revenue context for MATERIALITY sizing, with a "today" anchor so
# the freshness rule can't mis-time stale filings as today's catalyst (the date-confusion
# trap). Used in SHADOW first (web-inclusive net-correctness telemetry); the live grade
# flip is gated on shadow data + operator sign-off (CHANGE_PROCESS).
_GRADE_TODAY_WINDOW_DAYS = 10  # a filing within this many days of the gap = "today's"
# Corpus-window budgeting (the grader slices grounded_text[:max_chars]; the enriched
# corpus appends context AFTER today's news, so a long today's-news would push it past a
# 6000 window — the #238/#344 truncation bug, advisor 6/19). Cap today's news to the same
# effective window the lean live grader sees, then grade the enriched corpus with a larger
# window so the appended prior-agreement / dilution context actually reaches the model.
_GRADE_TODAY_MAX_CHARS = 6000   # today's-news cap inside the enriched corpus
_GRADE_ENRICH_MAX_CHARS = 12000  # grade window for the enriched corpus
# INVARIANT: the enriched grade window MUST exceed the today's-news cap, or the appended
# dilution/agreement context gets sliced off again (the #238/#344 truncation bug). Fail loud
# at import if a future edit lowers the enrich cap below the today cap.
assert _GRADE_ENRICH_MAX_CHARS > _GRADE_TODAY_MAX_CHARS, "enrich window must exceed today cap"

_AGREEMENT_MARKERS = (
    "entered into", "definitive agreement", "agreement (the", "license",
    "pursuant to the agreement", "co-development", "controlled equity",
    "at-the-market", "at the market", "sales agreement", "credit agreement",
    "purchase agreement",
)
_REVENUE_MARKERS = ("revenue", "net cash", "partnership contributed", "total revenue")
# #238 dilution feed: a RECENT priced takedown (424B5) or actual equity sale (8-K item
# 3.02) is a capital-raise overhang fed to the grader as DATED NEGATIVE context (not a
# deterministic skip — the LLM stays judge so a real EP that also raises capital still
# fires). Recency window keeps a stale shelf-takedown from suppressing today's gap.
_DILUTION_WINDOW_DAYS = 21
_DILUTION_MARKERS = (
    "shares of", "per share", "offering", "proceeds", "purchase price",
    "underwrit", "placement", "prospectus supplement", "registered direct",
)


def _grade_substantive_slice(text: str, markers: tuple, n: int) -> str:
    """Skip the iXBRL/cover boilerplate (the disclosure body lives past it) — a window
    around the first substantive marker, else the head."""
    if not text:
        return ""
    low = text.lower()
    best = None
    for mk in markers:
        i = low.find(mk)
        if i > 150 and (best is None or i < best):
            best = i
    start = max(0, best - 80) if best is not None else 0
    return text[start:start + n]


def _grade_age_label(alert_date: date, filed_str: str) -> str:
    try:
        d = date.fromisoformat(filed_str)
    except (ValueError, TypeError):
        return "date unknown"
    days = (alert_date - d).days
    if days >= 60:
        return f"~{days // 30} months BEFORE today's gap"
    if days >= 1:
        return f"~{days} days BEFORE today's gap"
    return "TODAY"


def recent_filing_by_item(filings: list, item_code: str, on_before: date):
    """Most recent filing whose `items` contains item_code, filed <= on_before, with text."""
    cands = []
    for f in filings or []:
        if item_code not in (f.get("items") or "") or not f.get("text"):
            continue
        try:
            fd = date.fromisoformat(f["filed"])
        except (ValueError, TypeError, KeyError):
            continue
        if fd <= on_before:
            cands.append((fd, f))
    if not cands:
        return None
    cands.sort(key=lambda x: x[0], reverse=True)
    return cands[0][1]


def nearest_today_filing(filings: list, alert_date: date):
    """The same-day / near catalyst SEC filing (filed within the today-window, <= alert)."""
    cands = []
    for f in filings or []:
        if not f.get("text"):
            continue
        try:
            fd = date.fromisoformat(f["filed"])
        except (ValueError, TypeError, KeyError):
            continue
        if alert_date - timedelta(days=_GRADE_TODAY_WINDOW_DAYS) <= fd <= alert_date:
            cands.append((fd, f))
    if not cands:
        return None
    cands.sort(key=lambda x: x[0], reverse=True)
    return cands[0][1]


def recent_dilution_filing(filings: list, on_before: date,
                           within_days: int = _DILUTION_WINDOW_DAYS):
    """#238: most recent DILUTIVE capital-raise filing — a 424B5 priced takedown OR an
    8-K item 3.02 actual unregistered equity sale — filed in (on_before - within_days,
    on_before]. POINT-IN-TIME: only PRE-grade filings; an offering filed AFTER today's gap
    is raising INTO strength, a different animal, and is excluded by the on_before cutoff.
    The recency window keeps a stale shelf-takedown from suppressing today's catalyst."""
    floor = on_before - timedelta(days=within_days)
    cands = []
    for f in filings or []:
        form = f.get("form") or ""
        items = f.get("items") or ""
        is_dilutive = form.startswith("424B5") or (form.startswith("8-K") and "3.02" in items)
        if not is_dilutive:
            continue
        try:
            fd = date.fromisoformat(f["filed"])
        except (ValueError, TypeError, KeyError):
            continue
        if floor < fd <= on_before:
            cands.append((fd, f))
    if not cands:
        return None
    cands.sort(key=lambda x: x[0], reverse=True)
    return cands[0][1]


def assemble_grade_corpus(alert_date: date, today_sec, today_benz, prior_agreement_8k,
                          recent_earnings_8k, perplexity_answer=None, *, enrich: bool,
                          dilution_filing=None) -> str:
    """SINGLE source of truth for the grounded grade corpus (live grade path + offline
    replay). Anchors the grade DATE so the freshness rule sizes prior-dated context
    correctly instead of mis-timing it as today (the #344 date-confusion root cause).
    When `enrich`, appends clearly-dated + age-labeled PRIOR material-agreement + revenue
    context — for MATERIALITY sizing only, never as today's catalyst — and, when present,
    a RECENT dilutive-filing (#238) block as dated NEGATIVE context the grader weighs
    against today's move (it stays judge; a real EP that also raises capital still fires)."""
    # Cap today's news to the SAME effective window the lean live grader sees (it slices
    # grounded_text[:6000]) so the appended prior/dilution context isn't pushed out of the
    # enriched grade window by a long 8-K body (the truncation bug, advisor 6/19).
    today_text = (build_grounded_text(today_sec, (today_benz or [])[:3], perplexity_answer)
                  or "")[:_GRADE_TODAY_MAX_CHARS]
    parts = [
        f"DATE CONTEXT: today is {alert_date.isoformat()}. Grade ONLY a catalyst that is "
        f"FRESH as of today. Items explicitly dated BEFORE today below are BACKGROUND for "
        f"sizing how MATERIAL today's news is to this company — they are NOT themselves "
        f"today's catalyst, and a stale agreement or a dilutive financing is never a buy "
        f"catalyst on its own.",
        "[TODAY'S NEWS — the catalyst to grade]\n"
        + (today_text or "(no same-day primary source found)"),
    ]
    if enrich and prior_agreement_8k:
        terms = _grade_substantive_slice(prior_agreement_8k.get("text") or "",
                                         _AGREEMENT_MARKERS, 1600)
        parts.append(
            f"[PRIOR CONTEXT — material agreement (8-K item 1.01) filed "
            f"{prior_agreement_8k.get('filed')}, "
            f"{_grade_age_label(alert_date, prior_agreement_8k.get('filed'))}; "
            f"BACKGROUND for materiality, NOT today's catalyst]\n{terms}")
    # Dilution (#238) is a SHORT, decision-critical NEGATIVE flag — emit it BEFORE the
    # lowest-value "financial scale" earnings block so it survives any window budget (advisor 6/19).
    if enrich and dilution_filing:
        form = dilution_filing.get("form") or "424B5/8-K"
        kind = ("priced offering / prospectus supplement" if form.startswith("424B")
                else "unregistered equity sale (8-K item 3.02)")
        dtxt = _grade_substantive_slice(dilution_filing.get("text") or "",
                                        _DILUTION_MARKERS, 700)
        parts.append(
            f"[RECENT DILUTIVE FILING — {form} ({kind}) filed "
            f"{dilution_filing.get('filed')}, "
            f"{_grade_age_label(alert_date, dilution_filing.get('filed'))}; a fresh "
            f"capital raise / dilution overhang. Weigh AGAINST today's move: a gap into a "
            f"freshly-priced dilutive raise is frequently a pump rather than a clean "
            f"catalyst. But do NOT auto-reject — a genuine EP catalyst can coincide with an "
            f"opportunistic raise; judge whether TODAY'S news is itself materially bullish.]"
            + (f"\n{dtxt}" if dtxt else ""))
    if enrich and recent_earnings_8k:
        rev = _grade_substantive_slice(recent_earnings_8k.get("text") or "",
                                       _REVENUE_MARKERS, 1000)
        parts.append(
            f"[PRIOR CONTEXT — most recent earnings (8-K item 2.02) filed "
            f"{recent_earnings_8k.get('filed')}, "
            f"{_grade_age_label(alert_date, recent_earnings_8k.get('filed'))}; "
            f"company financial scale, NOT today's catalyst]\n{rev}")
    return "\n\n".join(parts)


def should_repoll_shadow(cached_quality: str, grade_source_count: int,
                         current_source_count: int, already_logged: bool,
                         in_orb_window: bool) -> bool:
    """#344 re-poll trigger (pure → unit-tested). Shadow-re-grade a CACHED grade exactly
    ONCE when a NEW primary-subject direct source appears within the ORB window — but
    NEVER re-poll a grade that already fires (non-routine is terminal for the miss-class
    we fix: BFLY graded routine pre-PR, the PR arrived later, the cache pinned routine)."""
    if already_logged:
        return False                         # exactly once — no per-tick thrash
    if not in_orb_window:
        return False                         # only the ORB-actionable window
    if cached_quality != "routine":
        return False                         # never re-poll a firing/terminal grade
    return current_source_count > grade_source_count  # a NEW direct source arrived


# Re-poll shadow dedup state (module-level, mirrors _catalyst_cache lifecycle — cleared
# on a new trading day; a restart re-arming it just re-logs once, harmless for shadow).
_repoll_shadow_state: dict = {}
_repoll_shadow_date = None


def _is_premarket(now_et: datetime) -> bool:
    """True strictly before 9:30 ET. Shared guard for BOTH #344 shadows (enrichment +
    re-poll) — advisor 6/19: the shadows do extra SEC GETs + a Sonnet call SYNCHRONOUSLY
    on run_ep_scan, the order-submission path. Confining them to premarket keeps that
    work OFF the 9:30-10:00 ORB entry window; the motivating case (BFLY's PR, 8:12 ET) is
    premarket, so coverage is preserved."""
    return now_et.hour < 9 or (now_et.hour == 9 and now_et.minute < 30)


async def _build_enriched_corpus(
    ticker: str, today: date, profile: dict, *,
    ext_filings: Optional[list] = None,
    sec_filing_fallback: Optional[dict] = None,
    dilution: Optional[dict] = None,
    dilution_computed: bool = False,
    benzinga_items: Optional[list] = None,
    perplexity_answer: Optional[str] = None,
    news_for_classify: Optional[list] = None,
    state_sink: Optional[dict] = None,
):
    """#344 shared corpus pipeline — used by BOTH the enrichment shadow (uncached grade
    tick) and the re-poll shadow (cached grade tick): SEC 400d filings fetch/reuse ->
    nearest/recent-filing + dilution selection -> primary-subject Benzinga filter
    (content-bearing) -> assemble_grade_corpus -> _classify_catalyst_claude. Each shadow
    block keeps its own trigger condition and audit-log call inline; only this
    corpus-through-grade middle is shared.

    Every fetched piece can be passed in already-computed (reuse, no second
    EDGAR/Benzinga/Perplexity hit) or left None (fresh fetch). `dilution_computed`
    disambiguates "not yet computed" (dilution=None -> fetch) from "computed and
    genuinely found nothing" (dilution=None but dilution_computed=True -> don't
    re-fetch) — mirrors the cached path's `"dilution" not in _st` check.

    `state_sink`, when given, is written into AS SOON AS each piece is freshly fetched
    (not just at the end) — matches the original inline code's ordering, where
    ext_filings/dilution were cached into _repoll_shadow_state immediately so a later
    exception (e.g. in the Benzinga fetch or the classify call) doesn't lose them.

    Returns (quality, analysis, ext_filings, dilution, prior_agreement_8k,
    recent_earnings_8k).

    The 4 SEC/Benzinga/Perplexity fetches below are mutually independent (none
    consumes another's output) and premarket-only, so they run concurrently via
    asyncio.gather (simplify GROUP 5, 2026-07-03 — was 4 sequential awaits, a
    latency add on the premarket path). Each is a small wrapper coro so the
    reuse-or-fetch kwargs semantics and the `state_sink` incremental-write
    (written the moment ITS OWN fetch completes, not at the end) are unchanged;
    an already-provided piece resolves immediately with no I/O and no
    state_sink write, matching the pre-gather short-circuit. On any fetch's
    exception, gather propagates it (same as a sequential await raising) and
    any SIBLING fetch that already completed has already written its
    state_sink entry — partial-progress semantics unchanged, just concurrent."""

    async def _fetch_ext_filings():
        if ext_filings is not None:
            return ext_filings
        v = await get_sec_recent_filings(
            ticker, forms=("8-K", "6-K"), lookback_days=400,
            max_filings=8, want_text=True)
        if state_sink is not None:
            state_sink["ext_filings"] = v  # reuse on re-poll
        return v

    async def _fetch_dilution():
        # #238 dilution overhang — separate tight-window fetch (424B5 priced takedown +
        # recent 8-Ks for item 3.02); kept off the 400d agreement fetch so a recent
        # prospectus can't crowd the 7-month-old 1.01 out of max_filings. Point-in-time
        # (filed <= today).
        if dilution_computed:
            return dilution
        dil_ext = await get_sec_recent_filings(
            ticker, forms=("424B5", "8-K"), lookback_days=_DILUTION_WINDOW_DAYS,
            max_filings=8, want_text=True)
        v = recent_dilution_filing(dil_ext, today)
        if state_sink is not None:
            state_sink["dilution"] = v  # reuse on re-poll
        return v

    async def _fetch_benzinga_items():
        # F5 (2026-07-03): content-bearing Benzinga fetch — only paid here, once/ticker/day
        # (the enrichment shadow's first tick, or the re-poll shadow's one trigger); the
        # re-poll precheck that runs every tick uses a light include_content=False list to
        # count, never this.
        if benzinga_items is not None:
            return benzinga_items
        benz_full = await get_alpaca_news(ticker, include_content=True)
        return [
            n for n in (benz_full or [])
            if is_primary_subject_news(n, ticker, profile.get("companyName", ""))
        ][:3]

    async def _fetch_perplexity_answer():
        if perplexity_answer is not None:
            return perplexity_answer
        return await search_news_perplexity(
            f"What caused {ticker} stock to gap up? Latest catalyst and news.",
            recency="week")

    # return_exceptions=True + re-raise-first (7/3 review): plain gather propagates
    # the FIRST exception while sibling fetches keep running in the background —
    # they'd write state_sink entries AFTER the caller caught + moved on (orphan
    # writes into a possibly-rekeyed state dict), and a SECOND failing sibling's
    # exception would go unretrieved. Waiting for all four, then re-raising the
    # first failure, keeps the fail-fast contract with no background stragglers
    # (premarket-only path — the extra wait on failure is fine).
    _results = await asyncio.gather(
        _fetch_ext_filings(), _fetch_dilution(),
        _fetch_benzinga_items(), _fetch_perplexity_answer(),
        return_exceptions=True,
    )
    for _r in _results:
        if isinstance(_r, BaseException):
            raise _r
    ext_filings, dilution, benzinga_items, perplexity_answer = _results

    today_sec = nearest_today_filing(ext_filings, today) or sec_filing_fallback
    prior_agr = recent_filing_by_item(
        ext_filings, "1.01", today - timedelta(days=_GRADE_TODAY_WINDOW_DAYS + 1))
    recent_earn = recent_filing_by_item(ext_filings, "2.02", today)

    corpus = assemble_grade_corpus(
        today, today_sec, benzinga_items, prior_agr, recent_earn,
        perplexity_answer, enrich=True, dilution_filing=dilution)

    quality, analysis = await _classify_catalyst_claude(
        ticker, news_for_classify or [], profile, grounded_text=corpus,
        max_chars=_GRADE_ENRICH_MAX_CHARS)

    return quality, analysis, ext_filings, dilution, prior_agr, recent_earn


async def _classify_catalyst_claude(ticker: str, news: list[dict], profile: dict, grounded_text=None,
                                    max_chars: int = 6000) -> tuple[str, str]:
    """
    Use Claude to classify catalyst quality via structured tool use.
    Returns: (quality, analysis_text)
    quality: "game_changer" | "strong" | "routine" | "mna"

    Uses tool_choice to guarantee schema-valid output — no string parsing,
    no silent fallback to "routine" on format deviations.

    `max_chars` bounds the grounded corpus fed to the model. Default 6000 = the lean live
    grade path (unchanged). The enriched shadow passes a larger window so the appended
    prior-agreement / dilution context survives a long today's-news (truncation fix 6/19).
    """
    if grounded_text:
        # Grounded summary (SEC 8-K body + web synthesis), UNTRUNCATED — the catalyst body
        # lives past the first ~200 chars (after the 8-K iXBRL cover), so the old per-item
        # [:200] starved the grader and forced confabulation from raw headlines (#190 / RUM 6/4).
        news_text = grounded_text[:max_chars]
    else:
        news_text = "\n".join([f"- {n.get('title', '')} {n.get('text', '')[:200]}" for n in news[:5]])
    company_desc = profile.get("description", "")[:300]
    # #189 materiality anchor: deal/contract value is only EP-grade if SIGNIFICANT vs company size.
    _mc = profile.get("marketCap")
    try:
        mktcap_str = f"${float(_mc) / 1e9:.1f}B" if float(_mc) >= 1e9 else f"${float(_mc) / 1e6:.0f}M"
    except (TypeError, ValueError):
        mktcap_str = "unknown"

    prompt = f"""You are analyzing a stock gap-up for EP (Episodic Pivot) trading.
This stock is gapping up significantly in pre-market. Your job is to identify the catalyst.

Stock: {ticker}
Company: {profile.get('companyName', '')} — {profile.get('sector', '')}
Market cap: {mktcap_str}
Description: {company_desc}

Recent news (may include earnings announcements, guidance, contracts, upgrades):
{news_text or "No news found."}

IMPORTANT RULES:
1. Look for: earnings releases, guidance raises, FDA decisions, major contracts, analyst upgrades.
2. On GROWTH names, REVENUE growth/acceleration with a guidance raise = game_changer or strong.
   The market does not pay for EPS changes on growth stocks — an EPS beat with flat or missing
   REVENUE is "routine". EPS matters only in TURNAROUNDS (loss→profit inflection), and the
   turnaround must be SUSTAINABLE/structural — a single-quarter EPS anomaly from one-time items
   (asset sale, litigation settlement, tax benefit) is "routine".
3. If the catalyst is a MERGER, ACQUISITION, BUYOUT, TAKEOVER, TENDER OFFER, GOING-PRIVATE, or any
   deal where the company is being acquired — classify as "mna". This is a hard skip: price is capped
   at deal value, there is no momentum trade. Keywords: "definitive agreement", "to be acquired",
   "tender offer", "going private", "taken private", "strategic transaction", "buyout", "merger agreement".
4. Broad SECTOR-MOMENTUM, SHORT-SQUEEZE, or non-company-specific technical moves with no concrete
   company event = "routine" (a gap-up alone is not a catalyst).
5. MATERIALITY — weigh the catalyst's magnitude RELATIVE to the company (market cap above). A contract,
   deal, or order is game_changer/strong ONLY if its value is SIGNIFICANT vs the company's size (a
   meaningful fraction of market cap / revenue); a small or routine-sized deal for the company's scale
   is "routine" however positively worded.

CRITICAL — VERIFY THE CATALYST IS REAL:
- FRESHNESS: the catalyst must be NEW (dated today/overnight, or freshly disclosed in a filing/
  press wire). An UNDATED event, or one that predates today's gap (an old partnership/contract
  resurfacing in a web summary), is NOT today's catalyst no matter how large — classify what is
  actually fresh, or "routine" with the driver marked unidentified.
- If the news text mentions "earnings" or "quarterly results" but does NOT include specific numbers
  (revenue, EPS, guidance figures), the catalyst is likely FABRICATED. Classify as "routine".
- If the news is vague, generic, or reads like a summary with no specific details (no dates, no
  numbers, no named sources), classify as "routine" — the news source may have hallucinated.
- If none of the news items clearly explain WHY the stock gapped, classify as "routine".
- Penny stocks, biotechs with no revenue, and SPACs frequently gap on low-quality catalysts
  (press releases, conference presentations, speculative articles). Be skeptical — classify as "routine"
  unless the catalyst is concrete and verifiable.
- Do NOT assume earnings occurred just because news mentions "earnings" — look for actual reported
  numbers (EPS beat/miss, revenue figures, guidance).

In your analysis, state the SPECIFIC catalyst clearly. If you cannot identify a concrete, verifiable
catalyst, say so explicitly."""

    try:
        async with _ANTHROPIC_SEMAPHORE:
            for attempt in range(2):
                try:
                    response = await _get_claude().messages.create(
                        model=GROUNDED_GRADE_MODEL,  # #190: grade the grounded summary on Sonnet (Haiku confabulated on raw headlines)
                        # ⚠ 2026-08-07: was 300 and it became BINDING the moment this role tracked
                        # to Sonnet 5 — the SECOND cap sized for the previous model's verbosity to
                        # break the same day (the extractor's was the first). Measured in
                        # api_usage: on sonnet-4-6 this ran avg 228 / p90 265 / max 300 output
                        # tokens. On sonnet-5: avg 284, **median 298, p90 300, p99 300** — pegged.
                        # The response is a TOOL CALL whose JSON gets truncated mid-object, so
                        # `result["analysis"]` raises KeyError('analysis') and the whole grade
                        # fails open to routine. Correlation, same hour: 16 of 29 calls at the cap
                        # / 16 `live_enriched_grade_failed` rows.
                        # ⚠ SILENT, and that is the real defect (operator, 2026-08-07: "another
                        # silent failure"). It writes an audit row and alerts NOBODY; it surfaced
                        # only as a side-delta inside an unrelated L2 anomaly. Detection is #543.
                        max_tokens=1500,
                        tools=[_CATALYST_TOOL],
                        tool_choice={"type": "tool", "name": "classify_catalyst"},
                        messages=[{"role": "user", "content": prompt}],
                    )
                    break
                except anthropic.RateLimitError:
                    if attempt == 1:
                        raise
                    await log_audit_event("anthropic_rate_limited", ticker, "retrying ep catalyst")
                    await asyncio.sleep(2 + random.random() * 3)
        # S2/F9: safe wrapper — see spend_tracker.log_anthropic_call_safe
        from agents.market_intelligence.spend_tracker import log_anthropic_call_safe
        await log_anthropic_call_safe(model=GROUNDED_GRADE_MODEL, caller="ep_catalyst_grade",
                                       usage=getattr(response, "usage", None),
                                       stop_reason=getattr(response, "stop_reason", None))
        # ⚠ The SECOND shape failure of 2026-08-06, and it is a DIFFERENT bug from the
        # extractor's: `Claude catalyst classification failed for INOD: 'analysis'` — a
        # KeyError on a response KEY, not a block position. Cause: when max_tokens cuts a
        # forced tool call off, the SDK still returns a tool_use block with PARTIAL input.
        # `quality` is emitted first and survives; `analysis` gets truncated away, and
        # `result["analysis"]` raises straight into the fail-open below, grading a real
        # catalyst as routine. This ran at max_tokens=300 with 25% of calls at the cap.
        #
        # Two fixes, because the ceiling alone is not a guarantee: the cap is now 1500, AND a
        # truncated response is REJECTED outright rather than half-read (#543/#544 — same rule
        # the shared judge transport now enforces).
        if getattr(response, "stop_reason", None) == "max_tokens":
            raise ValueError(
                f"catalyst grade TRUNCATED at max_tokens for {ticker} — refusing to grade on a "
                "partial tool call")
        tool_block = next(b for b in response.content if b.type == "tool_use")
        result = tool_block.input
        # .get() with an explicit check, not [] — a missing key must read as "the model did not
        # answer", never as an exception indistinguishable from a network failure.
        quality, analysis = result.get("quality"), result.get("analysis")
        if not quality:
            raise ValueError(
                f"catalyst grade returned no quality for {ticker} "
                f"(keys: {sorted(result)}, stop_reason={getattr(response, 'stop_reason', None)})")
        return quality, analysis or ""
    except Exception as e:
        # #273: a credit-exhaustion failure here silently turns every catalyst
        # into "routine" — alert it (terminal + actionable) before failing open.
        try:
            from agents.market_intelligence.llm_health import (
                alert_credit_exhausted, is_credit_error)
            if is_credit_error(e):
                await alert_credit_exhausted("catalyst grader", e)
        except Exception:
            pass
        logger.error(f"Claude catalyst classification failed for {ticker}: {e}")
        return "routine", f"{_CLASSIFY_FAIL_SENTINEL} — treating as routine."


async def _validate_catalyst_perplexity(ticker: str, news_summary: str) -> Optional[str]:
    """
    Use Perplexity Sonar to cross-validate catalyst quality.
    Returns "game_changer", "strong", "routine", or None if unavailable.
    """
    import httpx

    api_key = os.environ.get("PERPLEXITY_API_KEY")
    if not api_key:
        return None

    prompt = f"""For stock {ticker}, classify this catalyst as GAME_CHANGER, STRONG, or ROUTINE:
{news_summary}

Respond with ONLY the classification word."""

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.post(
                "https://api.perplexity.ai/chat/completions",
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "model": "sonar",
                    "messages": [
                        {"role": "system", "content": "You classify stock catalysts. Respond with exactly one word: GAME_CHANGER, STRONG, or ROUTINE."},
                        {"role": "user", "content": prompt},
                    ],
                    "return_citations": False,
                },
            )
            r.raise_for_status()
            _data = r.json()
            try:  # #377 cost meter — additive; this path uses the cheaper "sonar"
                  # model (not sonar-pro). Never alters the validation result.
                from agents.market_intelligence.spend_tracker import log_perplexity_call
                await log_perplexity_call(
                    caller="perplexity_catalyst_validate", model="sonar",
                    usage=_data.get("usage"),
                    finish_reason=(_data.get("choices") or [{}])[0].get("finish_reason"),
                )
            except Exception:
                pass
            text = _data["choices"][0]["message"]["content"].strip().upper()
        if "GAME_CHANGER" in text or "GAME CHANGER" in text:
            return "game_changer"
        elif "STRONG" in text:
            return "strong"
        else:
            return "routine"
    except Exception as e:
        # #376: a 401/402 here is Perplexity credit exhaustion — alert (deduped).
        from agents.market_intelligence.llm_health import maybe_alert_credit_exhausted
        await maybe_alert_credit_exhausted("Perplexity catalyst validation", e,
                                           provider="perplexity")
        logger.warning(f"Perplexity validation failed for {ticker}: {e}")
        return None


def _volume_percentile(today_volume: float, adv_history: list[float]) -> float:
    """
    Percentile rank of today's pre-market volume vs the stock's historical ADV values.
    Returns 0-100.

    Interpretation: a score of 80 means today's pre-market volume already
    exceeds 80% of this stock's typical full-day average volumes — genuine
    conviction, not thin-float RVOL inflation.
    """
    if not adv_history or today_volume <= 0:
        return 50.0  # unknown — neutral
    below = sum(1 for v in adv_history if today_volume > v)
    return round(below / len(adv_history) * 100, 1)


def _score_ep(
    gap_pct: float,
    rel_volume: float,
    catalyst_quality: str,
    profile: dict,
    regime_multiplier: float,
    vol_percentile: float = 50.0,
    prior_3m_change: float | None = None,
    projected_vol_multiple: float | None = None,
    in_active_theme: bool = False,
) -> tuple[float, dict]:
    """
    Calculate MAGNA53 EP score (0-100 before multiplier).
    Returns: (final_score, score_breakdown)

    Weights emphasize the two strongest EP signals: gap size + catalyst quality.
    A 20%+ game-changer gap should score ≥70 on its own before bonuses.

    projected_vol_multiple: open intensity — raw_rvol * (390 / min_since_open).
    Measures how many times above the normal rate-for-this-time the stock is trading.
    Linear extrapolation overstates final daily RVOL (opening minutes are always dense),
    but correctly rewards early institutional conviction. Pre-market: raw RVOL used instead.

    in_active_theme: ticker is in an Accelerating or Mainstream theme on
    alert_date. Adds +10 to score breakdown (R4 ship 2026-05-17). Evidence:
    in-theme alerts had 67% WR vs 40% uncovered in label cross-tab; +27pp
    lift. Under current ep_threshold=70 the bonus is decorative (60d
    verification: 0 MODERATE-in-theme alerts would have crossed to HIGH
    with +10). Shipped for telemetry/visibility — future Phase 5 meta-
    rubric will use theme_context as a composite input with its own
    weight calibration. Env-flagged for fast rollback.
    """
    breakdown = {}

    # Gap magnitude (max 15) — scaled: bigger gaps = stronger signal
    if gap_pct >= 20:
        breakdown["gap"] = 25
    elif gap_pct >= 15:
        breakdown["gap"] = 20
    elif gap_pct >= 10:
        breakdown["gap"] = 15
    elif gap_pct >= 8:
        breakdown["gap"] = 10
    else:
        breakdown["gap"] = 0

    # Volume intensity (max 15)
    # Post-open: use projected daily multiple (pace-normalised) — 10x projected at 9:35
    # is Godzilla volume, very different from 10x raw at 2pm.
    # Pre-market: use raw RVOL — no intraday projection possible.
    vol_signal = projected_vol_multiple if projected_vol_multiple is not None else rel_volume
    if vol_signal >= 10:
        breakdown["rel_volume"] = 15
    elif vol_signal >= 5:
        breakdown["rel_volume"] = 12
    elif vol_signal >= 3:
        breakdown["rel_volume"] = 10
    elif vol_signal >= 2:
        breakdown["rel_volume"] = 7
    else:
        breakdown["rel_volume"] = 0

    # Catalyst quality (max 25) — the single most important EP signal
    # "mna" should never reach scoring (hard-filtered above), but treat as 0 if it does
    if catalyst_quality == "game_changer":
        breakdown["catalyst"] = 25
    elif catalyst_quality == "strong":
        breakdown["catalyst"] = 15
    else:
        breakdown["catalyst"] = 0

    # Low float bonus (max 5)
    float_shares = profile.get("floatShares", 0) or 0
    if float_shares > 0 and float_shares < 50_000_000:
        breakdown["float"] = 5
    else:
        breakdown["float"] = 0

    # Analyst upgrades bonus REMOVED (#332, 2026-07-18, operator-signed — CHANGE_PROCESS +
    # docs/analysis/332_analyst_bonus_backtest_2026-07-18.md). The feed (get_fmp_analyst_ratings,
    # yfinance Ticker.recommendations) has been structurally dead since 2026-03-14 — it returns
    # the AGGREGATE grade-count table, and the string-matcher can never match an integer count.
    # Verified against the real production function (NVDA/AAPL/PLTR + 20 sampled alerted
    # tickers all returned 0). Realized impact of removal: 0 alerts, 0 tier flips across all
    # 251 retained live alerts — behavior-identical BY CONSTRUCTION. A repaired feed would add
    # no measured edge either (permutation p=0.29 overall / 0.18 within-HIGH on the
    # reconstructed counterfactual) and would select analyst-coverage BREADTH (a mature-large-
    # cap proxy — TXN/QCOM/ROKU class), the opposite of this rubric's neglect thesis
    # (`breakdown["neglect"]` below already scores that axis directly).

    # Neglect period — approximate from 52-week range
    # If price < 70% of 52-week high before the gap, it was neglected
    price = profile.get("price", 0) or 0
    high_52w = profile.get("52WeekHigh", price) or price
    if high_52w > 0 and price > 0:
        pct_of_high = price / high_52w
        if pct_of_high < 0.5:
            breakdown["neglect"] = 15  # 6mo+ base
        elif pct_of_high < 0.7:
            breakdown["neglect"] = 8   # 3mo base
        else:
            breakdown["neglect"] = 0
    else:
        breakdown["neglect"] = 0

    # Volume conviction: pre-market volume vs stock's own historical ADV distribution (max 5)
    if vol_percentile >= 90:
        breakdown["vol_conviction"] = 5
    elif vol_percentile >= 70:
        breakdown["vol_conviction"] = 3
    else:
        breakdown["vol_conviction"] = 0

    # Prior momentum penalty — Qullamaggie: "best if stock has not rallied past 3-6 months"
    if prior_3m_change is not None:
        if prior_3m_change >= 50:
            breakdown["prior_momentum"] = -25
        elif prior_3m_change >= 30:
            breakdown["prior_momentum"] = -15
        else:
            breakdown["prior_momentum"] = 0
    else:
        breakdown["prior_momentum"] = 0

    # R4 in-theme bonus (2026-05-17 ship). +10 when ticker is in an
    # Accelerating or Mainstream theme on alert_date. Env-flagged.
    # Under current ep_threshold=70 this is decorative — verified via
    # pre-ship SQL (0 MODERATE-in-theme alerts in 60d would cross HIGH
    # with +10). Shipped for telemetry/visibility: score breakdown
    # surfaces the theme context, and Phase 5 meta-rubric will compose
    # theme_context as a separate scoring input with its own calibrated
    # weights. The +10 contributes to ep_score regardless of HIGH/MOD
    # outcome — useful as a paired-data signal for Phase 5 regression.
    _R4_ENABLED = os.environ.get("R4_THEME_BONUS_ENABLED", "true").lower() == "true"
    if _R4_ENABLED and in_active_theme:
        breakdown["theme_bonus"] = 10
    else:
        breakdown["theme_bonus"] = 0

    raw_score = sum(breakdown.values())

    # Conviction floor: massive gap + quality catalyst = high-conviction regardless
    # of secondary factors. The gap itself is evidence of institutional conviction.
    # 20%+ strong = same floor as 15%+ game_changer (market voted with its feet)
    # 10-15% game_changer: floor 60 → MODERATE at minimum; fires HIGH in Bull w/ Gemini
    if gap_pct >= 15 and catalyst_quality == "game_changer":
        raw_score = max(raw_score, 80)
        breakdown["conviction_floor"] = max(0, 80 - sum(v for k, v in breakdown.items() if k != "conviction_floor"))
    elif gap_pct >= 20 and catalyst_quality == "strong":
        raw_score = max(raw_score, 80)
        breakdown["conviction_floor"] = max(0, 80 - sum(v for k, v in breakdown.items() if k != "conviction_floor"))
    elif gap_pct >= 15 and catalyst_quality == "strong":
        raw_score = max(raw_score, 70)
        breakdown["conviction_floor"] = max(0, 70 - sum(v for k, v in breakdown.items() if k != "conviction_floor"))
    elif gap_pct >= 10 and catalyst_quality == "game_changer":
        raw_score = max(raw_score, 60)
        breakdown["conviction_floor"] = max(0, 60 - sum(v for k, v in breakdown.items() if k != "conviction_floor"))

    # Removed prior `min(..., 100)` cap (#42, 2026-05-09). The cap squashed
    # multiple high-conviction setups to identical 100s — 5/8 spike showed
    # 3+ MAGNA53 names tied at 100 on 3/8 sampled days. Cross-strategy
    # allocator (#31) needs ranking resolution at the top tier; uncapping
    # gives natural 100-115 spread under Bull regime (×1.2 multiplier on
    # raw_score that maxes near 95). Tier thresholds (HIGH ≥ 70-90 by
    # regime) unchanged — uncap never promotes a candidate that wasn't
    # already capped, and conviction floors apply to raw_score pre-multiplier
    # so they aren't affected.
    final_score = raw_score * regime_multiplier
    return round(final_score, 1), breakdown


# _yoy_shadow_decision (#149) removed 2026-07-02 (#400b): the #321 LIVE YoY
# recovery in the gate block supersedes the shadow — see the tombstone at the
# former post-scan block for the full rationale.


# _compute_fire_status (#201) removed 2026-06-10 (#249): the holistic judge's
# verdict carries fire_axes (catalyst/theme/narrative) on every graded alert —
# the heuristic two-pass compute is subsumed. mi_ep_alerts.fire_status is frozen
# historical (last heuristic row 2026-06-10); fire_axes is judge-written now.


async def _post_grade_filters(
    ticker: str,
    catalyst_quality: str,
    claude_analysis: str,
    news_summary: str,
    gap_pct: float,
    today_volume: int,
    pm_rvol: float | None,
    today: "date",
) -> str | None:
    """The three post-grade hard filters — M&A/buyout, routine-catalyst-low-gap,
    pm-shares floor (R6 carve-out) — extracted (S6/#405, 2026-07-03) so BOTH the
    fresh-grade tick AND a later tick re-checking a cached-but-not-yet-cleared
    grade can run them without any LLM call. ORDER + reason strings + thresholds
    are byte-identical to the pre-#405 inline checks (FROZEN — this function
    moves control flow, it does not tune criteria).

    All three inputs besides `catalyst_quality`/`claude_analysis`/`news_summary`
    (the settled grade fields) are per-tick/time-sensitive — gap_pct, today_volume,
    pm_rvol from the live snapshot, and the M&A check's own Polygon news lookup
    (`on_or_before=today`) — which is exactly why this must re-run every tick
    instead of being decided once (BFLY class: routine grade at 7:00, M&A/PR
    news lands at 8:12; pm-volume grows through the morning).

    Returns the skip-reason string (same string previously passed to
    `_log_filtered`), or None if the ticker clears all three.
    """
    # 1) M&A / buyout — price capped at deal value, no momentum trade.
    # Single-source filter (ma_filter.is_likely_ma) — same logic used by
    # flag/9M/parabolic detectors. Polygon backstop closes the Perplexity
    # coverage-gap (AVNS 5/4: Perplexity returned "no specific news" for
    # 4/14 going-private; Polygon had the headline the whole time).
    #
    # Sanitize Perplexity disclaimer text before feeding to keyword
    # scanner (2026-05-14 perplexity_hallucination_keyword_leak fix).
    # When Perplexity returns "No recent catalysts... Nearest match is X"
    # the unrelated content trips M&A keywords on the wrong company.
    from agents.market_intelligence.collector import strip_perplexity_disclaimer
    _, news_is_disclaimer = strip_perplexity_disclaimer(news_summary)
    catalyst_texts_for_filter = [claude_analysis]
    if not news_is_disclaimer:
        catalyst_texts_for_filter.append(news_summary)
    else:
        logger.info(f"{ticker}: Perplexity disclaimer in news_summary — excluding from M&A keyword scan")
        await log_audit_event(
            "perplexity_disclaimer_stripped",
            f"{ticker}: news_summary suppressed from M&A keyword scan",
            json.dumps({
                "ticker": ticker,
                "news_summary_lead": (news_summary or "")[:200],
            }),
        )
    is_mna, mna_meta = await is_likely_ma(
        ticker,
        catalyst_quality=catalyst_quality,
        catalyst_texts=catalyst_texts_for_filter,
        check_polygon=True,
        on_or_before=today,
    )
    if is_mna:
        reason = "M&A/buyout catalyst — no momentum trade"
        logger.info(f"Skip {ticker}: {reason} ({(mna_meta or {}).get('source')})")
        # Filter behavior is ALWAYS applied; only audit log is
        # deduped (#89, 2026-05-23). Summary now includes (ep)
        # suffix matching the 4 other detector sites for
        # consistent should_log_mna_filter_fired LIKE-keying.
        from agents.market_intelligence.ma_filter import should_log_mna_filter_fired
        if await should_log_mna_filter_fired(ticker, "ep"):
            await log_audit_event(
                "mna_filter_fired",
                f"{ticker} via {(mna_meta or {}).get('source', 'unknown')} (ep)",
                json.dumps({
                    "ticker": ticker,
                    "alert_date": today.isoformat(),
                    "detector": "ep",
                    "catalyst_quality": catalyst_quality,
                    "news_summary": (news_summary or "")[:200],
                    **(mna_meta or {}),
                }),
            )
        return reason

    # 2) Skip routine catalysts outright
    if catalyst_quality == "routine" and gap_pct < 12:
        reason = f"routine catalyst, gap {gap_pct:.1f}%"
        logger.info(f"Skip {ticker}: {reason}")
        return reason

    # 3) R6 pm-shares carve-out (2026-05-17 ship). Moved from pre-catalyst
    # position so we can use catalyst_quality in the carve-out condition.
    # Reject the absolute pm-shares floor UNLESS one of the carve-outs
    # bypasses it:
    #   1. pm_rvol ≥ 5x (relative anomaly — original 2026-05-08 carve-out)
    #   2. gap ≥ 10% AND catalyst_quality='strong' (high-conviction —
    #      NEW R6 carve-out; CPA 5/14 class: gap 13%, strong, but
    #      pm-shares=7K blocked entry for 24 min in old pre-catalyst
    #      position)
    # Env-flagged for fast rollback: set R6_PMSHARES_CARVEOUT_ENABLED=false
    # to disable carve-out #2 only (carve-out #1 always active).
    _R6_ENABLED = os.environ.get(
        "R6_PMSHARES_CARVEOUT_ENABLED", "true"
    ).lower() == "true"
    if today_volume < MIN_PREMARKET_SHARES:
        bypass_reason = None
        if pm_rvol is not None and pm_rvol >= 5.0:
            bypass_reason = f"pm_rvol={pm_rvol:.1f}x ≥ 5.0x"
        elif (
            _R6_ENABLED
            and gap_pct >= 10.0
            and catalyst_quality == "strong"
        ):
            bypass_reason = (
                f"R6 carve-out: gap={gap_pct:.1f}% + catalyst=strong"
            )
        if bypass_reason is None:
            reason = (
                f"pre-mkt volume {today_volume:,} < "
                f"{MIN_PREMARKET_SHARES:,} shares"
            )
            logger.info(f"Skip {ticker}: {reason} (gap={gap_pct:.1f}%)")
            return reason
        logger.info(
            f"{ticker}: pm-shares floor bypassed — {bypass_reason}"
        )

    return None


# ── Large-cap rel_volume floor SHADOW (data_gated_reviews.yaml
# `large_cap_relvol_floor_shadow_evidence`, forward-tracking successor to the
# retrospective `rel_volume_large_cap_floor_evidence` review) ──────────────────
#
# AUDIT-ONLY OBSERVER. THE LINE: this function NEVER mutates `r`, never touches
# score_tier/grade/entry, never skips the alert — it only WRITES ONE audit row
# observing that a future LIVE floor (a separate, later, operator-signed step)
# WOULD have skipped this entry. Call it AFTER score_tier is finally settled
# (post-judge-override, if any) so the observation reflects the real graded
# alert, not a pre-override intermediate value.
#
# Retrospective evidence (rel_volume_large_cap_floor_evidence, entry-aware
# mi_live_trades join): large-cap (ADV$ >= $50M) HIGH EP alerts with
# rel_volume < 0.5 at alert time underperformed sharply vs the >=0.5 control.
# Before any live gate, we need FORWARD (post-shadow-ship) confirmation that
# isn't just a timing artifact: rel_volume = today's cumulative volume / ADV
# (ep_detector.py, computed earlier this scan tick) is mechanically low in the
# first few minutes of the session regardless of real participation. This
# shadow captures rel_volume, ADV$, and the alert's clock time (now_et, the
# scan-tick timestamp) so the offline review can separate genuine
# thin-participation from an early-alert artifact — see
# `large_cap_relvol_floor_shadow_evidence` for the decision matrix.
#
# Gated on LARGE_CAP_RELVOL_FLOOR_SHADOW_ENABLED (default ON — audit-only, so
# safe to default-on; mirrors the ENRICH_SHADOW_ENABLED default-on shadow
# pattern elsewhere in this file). Flag OFF -> zero extra writes, detection
# output byte-identical. Reuses already-computed rel_volume/adv/prev_close
# off `r` — no recompute, no extra DB/API round-trip. Dedup via
# `_audit_dedupe_check` (same in-memory per-scan-day guard as the sibling
# theme/structure axis shadows) since `_judge_shadow` re-runs per 5-min tick
# for every still-open candidate.
#
# PRICE BASIS (advisor-flagged 2026-07-19, fixed before parent commit): both the
# retrospective evidence AND this shadow's own predicate_sql define large-cap as
# `mi_stock_scores.adv_20 * close` — the PRE-GAP price. Using `current_price`
# (today's already-gapped price, ~current_price = prev_close * (1 + gap_pct/100))
# would run every ADV$ figure hot by the gap size and silently admit names the
# retrospective set would have excluded (methodology drift the sibling review's
# 2026-05-18 close-to-close-vs-entry-aware correction already burned us on once).
# `r["prev_close"]` (the same prior-close ep_detector.py used to compute gap_pct
# at candidate-construction time) is the matching basis — use it, not
# current_price. Both raw `adv` and `prev_close` are captured in the payload
# (not just the derived adv_dollar) so the review can reconstruct either
# definition and reconcile against the retrospective cohort exactly.
async def _emit_large_cap_relvol_floor_shadow(r: dict, now_et: datetime) -> None:
    """SHADOW ONLY — see docs/setups/magna53_ep.md change log. Writes ONE
    `filter:large_cap_relvol_floor_shadow` mi_audit_log row when `r` is a HIGH
    alert with ADV$ (adv_20 * prev_close) >= $50M and rel_volume < 0.5. Never
    raises (log_audit_event swallows its own errors); wrapped defensively
    anyway so a bug here can never affect the live alert/entry path."""
    try:
        if os.environ.get(
            "LARGE_CAP_RELVOL_FLOOR_SHADOW_ENABLED", "true"
        ).lower() != "true":
            return
        if r.get("score_tier") != "HIGH":
            return
        adv = r.get("adv")
        prev_close = r.get("prev_close")
        rel_volume = r.get("rel_volume")
        if adv is None or prev_close is None or rel_volume is None:
            return
        # Defensive float() cast: adv/prev_close/rel_volume are plain Python floats
        # on every known path today (mi_stock_scores.adv_20 is FLOAT, not NUMERIC —
        # so asyncpg never hands back a Decimal here), but a bare `adv * prev_close`
        # would silently no-op (caught by the outer except, no shadow event) rather
        # than compute correctly if a future source ever returned Decimal.
        adv = float(adv)
        prev_close = float(prev_close)
        adv_dollar = adv * prev_close
        rel_volume = float(rel_volume)
        if adv_dollar < 50_000_000 or rel_volume >= 0.5:
            return
        ticker = r["ticker"]
        alert_date = r["alert_date"]
        if not _audit_dedupe_check(ticker, alert_date, "large_cap_relvol_floor_shadow"):
            return
        await log_audit_event(
            "filter:large_cap_relvol_floor_shadow",
            f"{ticker} HIGH rel_vol={rel_volume:.2f}x adv$={adv_dollar:,.0f} "
            f"@ {now_et.strftime('%H:%M')} ET (SHADOW — alert NOT skipped)",
            json.dumps({
                "ticker": ticker,
                "alert_date": alert_date.isoformat(),
                "rel_volume": rel_volume,
                "adv_dollar": round(adv_dollar, 0),
                "adv_20": adv,
                "prev_close": prev_close,
                "alert_timestamp_et": now_et.isoformat(),
                "alert_time_et": now_et.strftime("%H:%M"),
                "score_tier": r["score_tier"],
                "gap_pct": round(r.get("gap_pct") or 0.0, 2),
            }),
        )
    except Exception as _e:
        logger.warning(f"large_cap_relvol_floor_shadow failed for {r.get('ticker')}: {_e}")


# ── #490 RT-1 helpers (design docs/analysis/490_full_realtime_design_2026-07-25.md) ──────────

def _ts_age_s(ts, now_et: datetime) -> "float | None":
    """Age of a (tz-aware Alpaca) timestamp vs now_et, in seconds. None on any failure —
    a bad/naive timestamp must degrade the guard it feeds, never raise on the scan path."""
    if ts is None:
        return None
    try:
        return (now_et - ts).total_seconds()
    except Exception:  # loud-ok: age None → the consuming guard treats the input as stale/unknown
        return None


def _bar_date_et(ts) -> "date | None":
    """ET calendar date of an Alpaca bar timestamp (bars are stamped at bar OPEN — midnight ET
    for daily bars, so the ET date IS the trading date). None-safe."""
    if ts is None:
        return None
    try:
        from agents.market_intelligence.collector import _ET
        return ts.astimezone(_ET).date()
    except Exception:  # loud-ok: unparseable ts → no date match → the §2.1 fail-safe (no cross-check)
        return None


def _alpaca_ref_close(sn: dict, prev_trade_date: "date | None") -> "float | None":
    """§2.1 DATE-KEYED prev_close cross-check reference: whichever Alpaca bar (daily_bar OR
    previous_daily_bar) has bar-date == the known previous trading date. Pre-open that selects
    daily_bar (which still holds T-1 — proven by 190/190 T-2 matches on the OTHER field);
    post-rollover it selects previous_daily_bar. No clock heuristic — the date does the
    selection, so the Alpaca-internal rollover moment can't bite. None = no cross-check
    available (new listing / data gap / neither date matches, incl. holiday-approximation
    misses of `last_trading_day`) → caller keeps the Polygon denominator UNVERIFIED and any
    RT-only admission additionally requires Q3 bar corroboration (design O1 fail-safe)."""
    if prev_trade_date is None:
        return None
    for close_key, ts_key in (("daily_bar_close", "daily_bar_ts"),
                              ("prev_close", "prev_daily_bar_ts")):
        close = sn.get(close_key)
        if close and _bar_date_et(sn.get(ts_key)) == prev_trade_date:
            return close
    return None


# §2.2 corporate-action (split) guard — one Polygon reference call per morning, cached for the
# day. A FAILED fetch is NOT cached (retried next tick) so a transient reference outage falls
# back to the 0.5% cross-check alone for that tick only (today's protection level).
_corp_action_date: "date | None" = None
_corp_action_set: "set[str] | None" = None


async def _corp_action_holds_today(today: "date") -> "set[str] | None":
    global _corp_action_date, _corp_action_set
    if _corp_action_date == today:
        return _corp_action_set
    from agents.market_intelligence import collector
    holds = await collector.get_splits_today(today.isoformat())
    if holds is not None:
        _corp_action_date, _corp_action_set = today, holds
    return holds


# §4 halt quarantine session state — per-day in-memory set of tickers seen with a FRESH print
# this RTH session (distinguishes "halted mid-morning" from "just thin"). Wiped on date change
# and on container restart (restart → nothing is halt_suspect until re-observed — fail-open to
# today's delayed-fallback semantics, never a false quarantine).
_rt_fresh_seen_date: "date | None" = None
_rt_fresh_seen: set = set()


def _rt_track_fresh_prints(snaps: dict, now_et: datetime) -> None:
    """Record every ticker whose latest_trade is fresh (age ≤ EP_RT_HALT_TRADE_AGE_S) this RTH
    session. Called once per rt fetch BEFORE halt-suspect evaluation."""
    global _rt_fresh_seen_date, _rt_fresh_seen
    if _is_premarket(now_et):
        return
    adate = now_et.date()
    if _rt_fresh_seen_date != adate:
        _rt_fresh_seen = set()
        _rt_fresh_seen_date = adate
    for sym, sn in snaps.items():
        age = _ts_age_s(sn.get("price_ts"), now_et)
        if age is not None and age <= EP_RT_HALT_TRADE_AGE_S:
            _rt_fresh_seen.add(sym)


def _is_halt_suspect(ticker: str, sn: dict, now_et: datetime) -> bool:
    """§4: RTH-only heuristic — latest_trade frozen (age > EP_RT_HALT_TRADE_AGE_S) AND the quote
    is invalid-or-stale (Q1/Q2 fail), for a name that had a fresh print earlier this session.
    A halt_suspect cannot be RT-only admitted this tick; it re-admits naturally at the next
    5-min tick once prints/quotes refresh (post-resume ORB mechanics stay the real backstop)."""
    if _is_premarket(now_et) or ticker not in _rt_fresh_seen:
        return False
    trade_age = _ts_age_s(sn.get("price_ts"), now_et)
    if trade_age is None or trade_age <= EP_RT_HALT_TRADE_AGE_S:
        return False
    bid, ask = sn.get("bid"), sn.get("ask")
    quote_valid = bid is not None and ask is not None and bid > 0 and ask > bid
    quote_age = _ts_age_s(sn.get("quote_ts"), now_et)
    quote_fresh = quote_age is not None and quote_age <= EP_RT_QUOTE_MAX_AGE_RTH_S
    return not (quote_valid and quote_fresh)


def _q3_bar_corroborated(sn: dict, prev_close: float, now_et: datetime) -> bool:
    """Q3 — bar corroboration, REQUIRED for every RT-ONLY admission (extends the shipped
    never-loosen rule): minute_bar present, volume > 0, bar age ≤ EP_RT_BAR_MAX_AGE_S, and
    bar-close gap ≥ MIN_GAP_PCT − 0.5pp. Consolidated minute bars exclude most condition-coded
    prints per SIP aggregation rules — a phantom print cannot mint a qualifying bar with
    volume behind it. No name enters the scored cohort on one print alone."""
    mb_close = sn.get("minute_close")
    if not mb_close or not (sn.get("minute_volume") or 0) > 0 or not prev_close:
        return False
    bar_age = _ts_age_s(sn.get("minute_ts"), now_et)
    if bar_age is None or bar_age > EP_RT_BAR_MAX_AGE_S:
        return False
    return (mb_close - prev_close) / prev_close * 100 >= MIN_GAP_PCT - 0.5


def _sustain_ok(series: "list | None", prev_close: float, bars: int) -> "tuple[bool | None, dict]":
    """#490 — did the >=MIN_GAP_PCT level HOLD for the last `bars` consecutive minutes?

    `series` = [(HH:MM, close), ...] oldest->newest. Returns (verdict, detail):
      True  — the last `bars` real bars all closed >= MIN_GAP_PCT
      False — they did not
      None  — UNDECIDABLE (no series, or fewer than `bars` real bars available)

    ⚠ `None` is not a rejection and callers must not treat it as one. Pre-market bars are genuinely
    sparse (SCL had no 09:30 bar at all), and a rule that silently converted "no data" into "reject"
    would become "reject everything pre-market" — a far bigger change than the one signed.
    """
    if bars <= 1:
        return None, {"reason": "disabled"}
    if not series:
        return None, {"reason": "no_bars"}
    window = series[-bars:]
    if len(window) < bars:
        return None, {"reason": "too_few_bars", "have": len(window), "need": bars}
    gaps = [round((c - prev_close) / prev_close * 100, 2) for _hhmm, c in window]
    return (all(g >= MIN_GAP_PCT for g in gaps),
            {"gaps": gaps, "minutes": [hhmm for hhmm, _c in window]})


def _rt_quality_read(sn: dict, prev_close: float, now_et: datetime,
                     rt_only: bool) -> "tuple[float | None, str | None, dict]":
    """§3 tick-quality guards Q1-Q4 on one rt snapshot. Returns (price, reject_reason, meta).

    price None + reason None  → no usable rt read at all (silent per-ticker delayed fallback).
    price None + reason set   → a LOUD guard rejection (caller emits ep_rt_tick_quality_reject
                                with the reason enum: no_quote | crossed_quote | outside_band |
                                stale_quote | no_bar_confirm | insane_gap).
    price set                 → the accepted rt price (latest_trade, or the fresh minute-bar
                                close when Q1 rejected the print — meta['basis']).

    Q1 (NBBO band) runs only on a VALID (bid>0, ask>bid) and FRESH (Q2: ≤300s pre-open / ≤30s
    RTH) quote; without one, Q1 is unavailable and Q3 governs admission. `rt_only=True` makes
    Q3 mandatory (every universe admission); rt_only=False (an already-delayed-corroborated
    Pass-2 candidate) skips the mandatory-Q3 clause."""
    meta: dict = {"q1_pass": False, "q3_pass": False, "basis": "latest_trade",
                  "quote_state": None, "minute_close": sn.get("minute_close")}
    price = sn.get("price")
    bid, ask = sn.get("bid"), sn.get("ask")
    if bid is None or ask is None:
        quote_state = "missing"
    elif not (bid > 0 and ask > bid):
        quote_state = "invalid"   # one-sided, zero, crossed/locked — the phantom-cross vector
    else:
        q_max_age = EP_RT_QUOTE_MAX_AGE_PREOPEN_S if _is_premarket(now_et) else EP_RT_QUOTE_MAX_AGE_RTH_S
        q_age = _ts_age_s(sn.get("quote_ts"), now_et)
        quote_state = "fresh" if (q_age is not None and q_age <= q_max_age) else "stale"
    meta["quote_state"] = quote_state
    q3_pass = _q3_bar_corroborated(sn, prev_close, now_et)
    meta["q3_pass"] = q3_pass

    if not price:
        # No trade print — a fresh corroborating bar can still carry the read; else silent fallback.
        if q3_pass:
            price = sn.get("minute_close")
            meta["basis"] = "minute_bar"
        else:
            return None, None, meta
    elif quote_state == "fresh":
        mid = (bid + ask) / 2
        band = max(EP_RT_QBAND_PCT / 100 * mid, 0.01)
        if (bid - band) <= price <= (ask + band):
            meta["q1_pass"] = True
        elif q3_pass:
            # Print outside the band (likely late-reported / condition-coded / off-exchange odd
            # print) → fall through to the fresh minute-bar close.
            price = sn.get("minute_close")
            meta["basis"] = "minute_bar"
        else:
            return None, "outside_band", meta
    # quote_state stale/invalid/missing → Q1 skipped (unavailable) → Q3 governs admission below.

    rt_gap = (price - prev_close) / prev_close * 100
    meta["rt_gap"] = rt_gap
    # Q4 — absolute insanity bound (replaces the 30pp delta clamp for the universe path, which
    # structurally rejected the NVVE +95% class): hard-reject only rt_gap > EP_RT_INSANE_GAP_PCT
    # or price outside [0.25×, 4×] prev_close UNLESS Q1 AND Q3 both pass (a real +100% mover has
    # a real NBBO and real printed bars).
    if (rt_gap > EP_RT_INSANE_GAP_PCT or price < 0.25 * prev_close or price > 4 * prev_close) \
            and not (meta["q1_pass"] and q3_pass):
        return None, "insane_gap", meta
    if rt_only and not q3_pass:
        # Q3 mandatory — name the most-informative failed guard: a band-passed fresh print that
        # merely lacks the bar is no_bar_confirm; an uncheckable print is named by its quote gap.
        reason = ("no_bar_confirm" if quote_state == "fresh"
                  else {"missing": "no_quote", "invalid": "crossed_quote", "stale": "stale_quote"}[quote_state])
        return None, reason, meta
    return price, None, meta


def _delayed_gap_for(snap: "dict | None", prev_close: float) -> "float | None":
    """The delayed (Polygon snapshot) gap for a ticker — same price chain as the Pass-1 loop
    (min.c → day.o → lastTrade.p). None when no delayed price exists (the pure rt-only class)."""
    if not snap or not prev_close:
        return None
    current = (snap.get("min", {}).get("c")
               or snap.get("day", {}).get("o")
               or snap.get("lastTrade", {}).get("p", 0))
    if not current:
        return None
    return (current - prev_close) / prev_close * 100


_SESSION_MINUTES = 390  # 6.5-hour regular session (shared by Pass-1 + the Pass-0 admit path)


def _snap_candidate(ticker: str, snap: dict, prev_close: float, current_price: float,
                    gap_pct: float, adv_map: dict, minutes_since_open: "int | None") -> dict:
    """Build the Pass-1 candidate dict for one ticker (#490 RT-1 extraction — shared verbatim
    by the delayed Pass-1 loop and the Pass-0 universe admission path so the two can never
    drift). Byte-identical to the pre-#490 inline block (freeze-tested)."""
    # Volume: day.v for regular session, min.av for accumulated (includes pre-mkt)
    today_volume = snap.get("day", {}).get("v", 0) or snap.get("min", {}).get("av", 0) or 0
    adv = adv_map.get(ticker)
    # prevDay.v as temporary placeholder — proper 20-day ADV computed later for non-universe stocks
    adv_source = "rs_universe" if adv else "pending"
    if not adv:
        adv = snap.get("prevDay", {}).get("v") or None

    raw_rvol = round((today_volume / adv), 2) if adv and adv > 0 else None
    # Open intensity: projected full-day RVOL = raw_rvol * (390 / min_elapsed)
    # Gate: only project after 15 minutes (9:45 AM). The opening 15 minutes are
    # structurally dense — every stock shows 10-30x projected RVOL at 9:31 AM
    # regardless of real institutional interest. Before the gate, use raw RVOL.
    open_intensity = None
    if raw_rvol is not None and minutes_since_open and today_volume > 0:
        if minutes_since_open >= 15:
            open_intensity = round(raw_rvol * (_SESSION_MINUTES / minutes_since_open), 1)
        # else: intensity stays None — vol filter uses raw_rvol pre-9:45

    return {
        "ticker": ticker,
        "prev_close": prev_close,
        "current_price": current_price,
        "gap_pct": round(gap_pct, 2),
        "today_volume": today_volume,
        "adv": adv,
        "adv_source": adv_source,
        "rel_volume": raw_rvol,
        "projected_vol_multiple": open_intensity,  # field name kept for DB compat
        "gap_pct_delayed": round(gap_pct, 2),   # #489 Pass-1 delayed gap (both readings kept)
        "price_source": "polygon_delayed",       # Pass-2/Pass-0 overwrite when the rt gap decides
    }


async def _apply_rt_universe_overlay(candidates: list[dict], rt_universe: list, snapshots: dict,
                                     adv_map: dict, minutes_since_open: "int | None",
                                     now_et: datetime,
                                     prev_trade_date: "date | None") -> "tuple[list[dict], dict | None]":
    """#490 Pass-0 — full-universe real-time overlay (design §5.1). ONE Alpaca SIP fetch of the
    whole RT universe per tick (the watchdog + Pass-2 reuse the returned map — one fetch, not
    three). For every universe ticker NOT already a Pass-1 candidate whose rt gap crosses the
    real MIN_GAP_PCT floor: run the §2 prev_close guards (date-keyed cross-check, split hold) +
    §3 Q1-Q4 tick-quality (Q3 mandatory — RT-only admission) + §4 halt quarantine, then
      - SHADOW (`ep_rt_universe_authoritative` off, default): emit `ep_rt_universe_catch`
        audit-only (digest surfacing per the 7/21 noise ruling) — NOT admitted, no LLM spend;
      - AUTHORITATIVE (operator-flipped, RT-3): ADMIT it as a real candidate
        (price_source='alpaca_sip_universe'; rt price faces MIN_GAP_PCT directly).
    Polygon prevDay.c stays the SOLE gap denominator (§2). Every failure rung degrades to the
    hybrid path (§5.3): per-ticker miss → that ticker stays delayed; batch failure →
    ep_rt_universe_degraded; whole-fetch failure / budget breach → today's shadow-hybrid +
    deduped Telegram via maybe_alert_api_failure. NEVER raises. Returns (candidates, snaps|None).

    Master flag OFF (deploy default) → pure no-op, candidates returned unchanged (freeze-tested
    byte-identical)."""
    if not (EP_RT_UNIVERSE_ENABLED and EP_RT_PASS2_ENABLED) or not rt_universe:
        return candidates, None
    try:
        from agents.market_intelligence import collector
        authoritative = await get_runtime_toggle(
            "ep_rt_universe_authoritative", "EP_RT_UNIVERSE_AUTHORITATIVE", default=False)
        # #490 sustain rule — own toggle so it reverts in ~60s with no deploy, independent of the
        # authority flip. Default OFF = byte-identical to today.
        _sustain_on = await get_runtime_toggle(
            "ep_rt_sustain_enabled", "EP_RT_SUSTAIN_ENABLED", default=False)
        _sustain_bars: dict = {}   # per-TICK memo: one bar request per ticker, not per check
        stats: dict = {}
        try:
            snaps = await asyncio.wait_for(
                collector.get_alpaca_snapshots_batch(
                    [t for t, _ in rt_universe],
                    concurrency=EP_RT_UNIVERSE_CONCURRENCY, stats=stats),
                timeout=EP_RT_UNIVERSE_TIMEOUT_S)
        except Exception as e:
            # §5.3 rung 3 — whole-fetch failure / total budget breach → the tick runs EXACTLY
            # today's shadow-hybrid; sustained outage is loud within one dedup window (#370 idiom).
            from agents.market_intelligence.llm_health import maybe_alert_api_failure
            logger.warning(f"#490 Pass-0 universe fetch failed — hybrid tick: {e}")
            await maybe_alert_api_failure("alpaca", e, context="ep_rt_universe")
            return candidates, None
        # #490 gate-1 diagnostic (2026-08-02): per-tick RT snapshot COVERAGE, logged
        # UNCONDITIONALLY. The degraded event below only fires on a whole-BATCH failure, so a tick
        # where every batch succeeded but individual symbols came back empty was invisible — and
        # `price = sn.get("price"); if not price: continue` below drops those symbols with ZERO
        # telemetry. That silent path is the leading explanation for the 5 unexplained gate-1
        # misses (QMCO/QURE/SCL 7/29, DY 7/30, VECO 7/31), each of which passed every universe
        # filter, was liquid and CS-classified, and yet produced no ep_rt_* event of any kind.
        # Audit-only, one row per tick (~36/day in window). See
        # docs/analysis/490_rt2_shadow_packet_2026-08-02.md.
        try:
            _uni_n, _snap_n = len(rt_universe), len(snaps or {})
            _missing = [t for t, _ in rt_universe if t not in (snaps or {})]
            await log_audit_event(
                "ep_rt_universe_coverage",
                f"RT snapshot coverage {_snap_n}/{_uni_n} "
                f"({100.0 * _snap_n / _uni_n if _uni_n else 0:.1f}%), "
                f"{len(_missing)} symbol(s) absent @ {now_et:%H:%M} ET",
                json.dumps({"universe": _uni_n, "returned": _snap_n,
                            "missing_count": len(_missing),
                            "missing_sample": sorted(_missing)[:40],
                            "batches_failed": stats.get("batches_failed"),
                            "tick_et": now_et.strftime("%H:%M"),
                            "authoritative": authoritative}))
        except Exception as _ce:   # loud-ok: diagnostics must never break the scan
            logger.warning(f"#490 coverage telemetry failed (non-fatal): {_ce}")

        if stats.get("batches_failed"):
            # §5.3 rung 2 — those symbols degrade per rung 1; the rest stay RT.
            await log_audit_event(
                "ep_rt_universe_degraded",
                f"RT universe fetch degraded: {stats['batches_failed']}/{stats.get('batches_total')} "
                f"batches failed, {len(rt_universe) - len(snaps)} symbols missing @ {now_et:%H:%M} ET",
                json.dumps({"batches_failed": stats["batches_failed"],
                            "batches_total": stats.get("batches_total"),
                            "symbols_missing": len(rt_universe) - len(snaps),
                            "tick_et": now_et.strftime("%H:%M")}))
        if not snaps:
            return candidates, None
        _rt_track_fresh_prints(snaps, now_et)   # §4 — before any suspect evaluation this tick
        holds = await _corp_action_holds_today(now_et.date())
        adate = now_et.date()
        in_candidates = {c["ticker"] for c in candidates}
        for tkr, pc in rt_universe:
            if tkr in in_candidates or not pc:
                continue   # the candidate cohort is Pass-2's job (cross-check + floor, one place)
            sn = snaps.get(tkr)
            if not sn:
                continue   # rung 1: per-ticker symbology miss → hybrid semantics (fail-safe)
            price = sn.get("price")
            if not price:
                # #490: the snapshot came back for this symbol but carries no price. Distinct from
                # "absent from the response" (counted above) — both were previously silent.
                if _audit_dedupe_check(tkr, adate, "ep_rt_no_price"):
                    await log_audit_event(
                        "ep_rt_no_price",
                        f"{tkr} in RT universe but snapshot carries no price @ {now_et:%H:%M} ET",
                        json.dumps({"ticker": tkr, "tick_et": now_et.strftime("%H:%M")}))
                continue
            raw_gap = (price - pc) / pc * 100
            if raw_gap < MIN_GAP_PCT:
                continue   # guards are evaluated only on the would-be-catch set (bounded events)
            # §2.2 — corporate-action hold: a split effective today makes "settled yesterday"
            # vendor-ambiguous; no RT-only admission that day.
            if holds and tkr in holds:
                if _audit_dedupe_check(tkr, adate, "ep_rt_corp_action_hold"):
                    await log_audit_event(
                        "ep_rt_corp_action_hold",
                        f"{tkr} split effective today — RT-only admission held (delayed-path semantics)",
                        json.dumps({"ticker": tkr, "rt_gap": round(raw_gap, 2),
                                    "tick_et": now_et.strftime("%H:%M")}))
                continue
            # §4 — halt quarantine: frozen print + dead quote on a previously-fresh name.
            if _is_halt_suspect(tkr, sn, now_et):
                if _audit_dedupe_check(tkr, adate, "ep_rt_halt_suspect"):
                    await log_audit_event(
                        "ep_rt_halt_suspect",
                        f"{tkr} rt {raw_gap:.1f}% but print frozen + quote dead @ {now_et:%H:%M} ET — "
                        f"no RT-only admission this tick",
                        json.dumps({"ticker": tkr, "rt_gap": round(raw_gap, 2),
                                    "trade_age_s": _ts_age_s(sn.get("price_ts"), now_et),
                                    "tick_et": now_et.strftime("%H:%M")}))
                continue
            # §2.1 — date-keyed prev_close cross-check (Polygon prevDay.c stays the denominator).
            a_ref = _alpaca_ref_close(sn, prev_trade_date)
            if a_ref is not None and abs(a_ref - pc) / pc * 100 > 0.5:
                if _audit_dedupe_check(tkr, adate, "ep_rt_prev_close_mismatch"):
                    await log_audit_event(
                        "ep_rt_prev_close_mismatch",
                        f"{tkr} prev_close alpaca {a_ref} vs polygon {pc} (date-keyed) — using delayed",
                        json.dumps({"ticker": tkr, "alpaca": a_ref, "polygon": pc,
                                    "prev_trade_date": prev_trade_date.isoformat() if prev_trade_date else None,
                                    "tick_et": now_et.strftime("%H:%M")}))
                continue   # degrade to delayed semantics — exactly today's fail direction
            # §3 — Q1-Q4; Q3 is ALWAYS mandatory here (every one of these is an RT-only admission;
            # an unverified prev_close (a_ref None) is covered by the same mandatory Q3, per §2.1).
            rt_price, reject, meta = _rt_quality_read(sn, pc, now_et, rt_only=True)
            if rt_price is None:
                if reject and _audit_dedupe_check(tkr, adate, "ep_rt_tick_quality_reject"):
                    await log_audit_event(
                        "ep_rt_tick_quality_reject",
                        f"{tkr} rt {raw_gap:.1f}% REJECTED ({reject}) @ {now_et:%H:%M} ET",
                        json.dumps({"ticker": tkr, "reason": reject, "rt_gap": round(raw_gap, 2),
                                    "quote_state": meta.get("quote_state"),
                                    "tick_et": now_et.strftime("%H:%M")}))
                continue
            rt_gap = (rt_price - pc) / pc * 100
            if rt_gap < MIN_GAP_PCT:
                # #490: BENIGN (the name crossed, then the accepted price fell back under the
                # floor) — but previously silent, so it was indistinguishable from a data gap.
                # Naming it is what lets gate 1's misses be attributed rather than guessed at.
                if _audit_dedupe_check(tkr, adate, "ep_rt_retreated_below_floor"):
                    await log_audit_event(
                        "ep_rt_retreated_below_floor",
                        f"{tkr} raw {raw_gap:.1f}% but accepted price reads {rt_gap:.1f}% "
                        f"(< {MIN_GAP_PCT:.0f}% floor) @ {now_et:%H:%M} ET — no catch",
                        json.dumps({"ticker": tkr, "raw_gap": round(raw_gap, 2),
                                    "accepted_gap": round(rt_gap, 2),
                                    "basis": meta.get("basis"),
                                    "tick_et": now_et.strftime("%H:%M")}))
                continue
            # ── #490 SUSTAIN gate (operator-signed 2026-08-02, N=3) ──────────────────────
            # Runs HERE, at the would-be-catch, because the set is tiny (~0-3 symbols a tick) so a
            # short batched bar request is cheap — and because deciding admission anywhere else
            # would split the decision from its evidence. `_sustain_bars` memoises per TICK, so a
            # second catch in the same tick costs nothing.
            # FAIL-OPEN on an undecidable verdict: no bars / too few bars => today's behaviour.
            # That is the operator's own pre-market case; converting "no data" into "reject" would
            # silently become "reject everything pre-market".
            if _sustain_on and EP_RT_SUSTAIN_BARS > 1:
                if tkr not in _sustain_bars:
                    try:
                        from agents.market_intelligence.collector import get_alpaca_minute_closes
                        _fetched = await get_alpaca_minute_closes(
                            [tkr], now_et, lookback_min=EP_RT_SUSTAIN_LOOKBACK_MIN)
                        _sustain_bars[tkr] = _fetched.get(tkr)
                    except Exception as _se:   # loud-ok: rule unavailable -> fall through, never block
                        logger.warning(f"#490 sustain bars fetch failed for {tkr}: {_se}")
                        _sustain_bars[tkr] = None
                _held, _sd = _sustain_ok(_sustain_bars.get(tkr), pc, EP_RT_SUSTAIN_BARS)
                if _held is False:
                    # REJECTED. Logged by name so dropped candidates stay auditable — a rule whose
                    # rejects are invisible cannot be judged later (pre-committed watch item).
                    if _audit_dedupe_check(tkr, adate, "ep_rt_sustain_reject"):
                        await log_audit_event(
                            "ep_rt_sustain_reject",
                            f"{tkr} rt {rt_gap:.1f}% but the level did NOT hold "
                            f"{EP_RT_SUSTAIN_BARS} consecutive bars @ {now_et:%H:%M} ET — no catch",
                            json.dumps({"ticker": tkr, "rt_gap": round(rt_gap, 2),
                                        "bars_required": EP_RT_SUSTAIN_BARS,
                                        "tick_et": now_et.strftime("%H:%M"), **_sd}))
                    continue
                if _held is None and _audit_dedupe_check(tkr, adate, "ep_rt_sustain_undecidable"):
                    # Fail-open, but NAMED — otherwise "the rule is on" and "the rule never had
                    # data" look identical in the log, which is the instrumentation trap that made
                    # gate 1 unanswerable in the first place.
                    await log_audit_event(
                        "ep_rt_sustain_undecidable",
                        f"{tkr} sustain rule UNAVAILABLE ({_sd.get('reason')}) @ {now_et:%H:%M} ET "
                        f"— admitted on today's behaviour",
                        json.dumps({"ticker": tkr, "rt_gap": round(rt_gap, 2),
                                    "tick_et": now_et.strftime("%H:%M"), **_sd}))
            delayed_gap = _delayed_gap_for(snapshots.get(tkr), pc)
            # The shadow-proof event — fires in BOTH modes (the RT-2 proof-join and the RT-4
            # regression monitor read it). AUDIT-ONLY + morning digest (operator fork 4, 7/21
            # noise ruling) — never a per-catch Telegram. Includes the latest_trade-vs-minute_bar
            # divergence (§3 accepted-risk measurement).
            if _audit_dedupe_check(tkr, adate, "ep_rt_universe_catch"):
                await log_audit_event(
                    "ep_rt_universe_catch",
                    f"{tkr} rt {rt_gap:.1f}% ≥{MIN_GAP_PCT:.0f} vs delayed "
                    f"{'%.1f%%' % delayed_gap if delayed_gap is not None else 'n/a'} @ {now_et:%H:%M} ET"
                    + ("" if authoritative else " (SHADOW — would have caught)"),
                    json.dumps({"ticker": tkr, "rt_gap": round(rt_gap, 2),
                                "delayed_gap": round(delayed_gap, 2) if delayed_gap is not None else None,
                                "tick_et": now_et.strftime("%H:%M"), "authoritative": authoritative,
                                "basis": meta.get("basis"), "q1_pass": meta.get("q1_pass"),
                                "quote_state": meta.get("quote_state"),
                                "trade_price": price, "minute_close": meta.get("minute_close"),
                                "prev_close_verified": a_ref is not None}))
            if not authoritative:
                continue   # SHADOW: not admitted, no LLM spend
            snap = snapshots.get(tkr) or {}
            cand = _snap_candidate(tkr, snap, pc, rt_price, rt_gap, adv_map, minutes_since_open)
            cand["price_source"] = "alpaca_sip_universe"
            cand["gap_pct_rt"] = round(rt_gap, 2)
            if delayed_gap is not None:
                cand["gap_pct_delayed"] = round(delayed_gap, 2)
            else:
                del cand["gap_pct_delayed"]   # no delayed read exists — never present rt as delayed
            cand["prev_close_alpaca"] = a_ref
            cand["prev_close_verified"] = a_ref is not None
            age = _ts_age_s(sn.get("price_ts"), now_et)
            if age is not None:
                cand["rt_price_age_s"] = round(age, 1)
            candidates.append(cand)
        return candidates, snaps
    except Exception as e:
        # §5.3 rung 6 — outer belt: unexpected exception → the hybrid path, never a blind tick.
        logger.warning(f"#490 Pass-0 overlay failed — degrading to the hybrid path: {e}")
        return candidates, None


async def _apply_realtime_pass2(candidates: list[dict], now_et: datetime,
                                prev_trade_date: "date | None" = None,
                                snaps: "dict | None" = None) -> list[dict]:
    """#489 hybrid Pass 2 — real-time Alpaca SIP confirm on the superset candidates.

    When EP_RT_PASS2_ENABLED: fetch rt prices, recompute the gap on the rt price (Polygon prev_close
    stays the SOLE denominator), and under the `ep_rt_gap_authoritative` runtime toggle make the rt
    gap the decided `gap_pct`. Then RE-APPLY the real MIN_GAP_PCT floor. In shadow (toggle off) the
    decided gap stays delayed, so every superset-only admit is dropped here -> the live cohort is
    byte-identical to today; the rt reading rides along for scan-log shadow columns + floor-flip
    events. NEVER raises; every failure degrades to exactly the delayed 10%-floor path.

    #490 RT-1: `prev_trade_date` arms the §2.1 DATE-KEYED prev_close cross-check (ships as a BUG
    FIX regardless of the cutover — pre-open Alpaca's previous_daily_bar deterministically holds
    T-2, so the old field-hardcoded compare silently censored the RT read of every candidate whose
    prior day moved >0.5%). `snaps` accepts the Pass-0 pre-fetched universe map (no second fetch);
    None → Pass-2 fetches its own cohort exactly as before."""
    if not EP_RT_PASS2_ENABLED or not candidates:
        return candidates
    try:
        from agents.market_intelligence import collector
        authoritative = await get_runtime_toggle(
            "ep_rt_gap_authoritative", "EP_RT_GAP_AUTHORITATIVE", default=False)
        # #490 split (2026-08-01): the REMOVE half on its own toggle. Subsumed by full gap
        # authority — when `authoritative` is on it already removes, so this is only consulted
        # in the else-branch. Default off = byte-identical to today.
        down_authoritative = (not authoritative) and await get_runtime_toggle(
            "ep_rt_gap_down_authoritative", "EP_RT_GAP_DOWN_AUTHORITATIVE", default=False)
        if snaps is None:
            snaps = await collector.get_alpaca_snapshots_batch([c["ticker"] for c in candidates])
        adate = now_et.date()

        def _floor(cs):
            # Re-apply the REAL floor to the decided gap. A superset-only admit (delayed<10%) whose
            # rt read is MISSING under authority is DROPPED — a fetch miss must never loosen detection.
            # #490: `_rt_admit_block` extends the same never-loosen rule — an unverified-prev_close
            # flip-up without Q3 bar corroboration (§2.1) or a halt_suspect (§4) is likewise DROPPED.
            out = []
            for c in cs:
                if authoritative and c.get("gap_pct_delayed", c["gap_pct"]) < MIN_GAP_PCT:
                    if "gap_pct_rt" not in c or c.get("_rt_admit_block"):
                        continue
                if c["gap_pct"] >= MIN_GAP_PCT:
                    out.append(c)
            return out

        if not snaps:
            await log_audit_event(
                "ep_rt_pass2_degraded",
                f"EP Pass-2 ran on DELAYED data — Alpaca batch empty ({len(candidates)} syms) @ {now_et:%H:%M} ET",
                json.dumps({"tick_et": now_et.strftime("%H:%M"), "superset_count": len(candidates),
                            "authoritative": authoritative}))
            return _floor(candidates)

        _rt_track_fresh_prints({c["ticker"]: snaps[c["ticker"]] for c in candidates
                                if c["ticker"] in snaps}, now_et)   # §4 session state (RTH no-op premarket)
        for c in candidates:
            if c.get("price_source") == "alpaca_sip_universe":
                continue   # #490: Pass-0 already rt-priced + Q1-Q4-validated this one (the 30pp
                           # clamp below would structurally reject the NVVE class it carries)
            sn = snaps.get(c["ticker"])
            rt_price = sn.get("price") if sn else None
            if not rt_price:
                continue   # no rt read → per-ticker fallback to the delayed gap
            pc = c["prev_close"]
            # §2.1 date-keyed cross-check (the pre-open T-2 bug fix): select whichever Alpaca bar
            # matches the known prev trading date; None = no cross-check available → keep the
            # Polygon denominator UNVERIFIED (any authoritative flip-up then requires Q3 below).
            a_ref = _alpaca_ref_close(sn, prev_trade_date)
            if a_ref is not None and pc and abs(a_ref - pc) / pc * 100 > 0.5:
                if _audit_dedupe_check(c["ticker"], adate, "ep_rt_prev_close_mismatch"):
                    await log_audit_event("ep_rt_prev_close_mismatch",
                        f"{c['ticker']} prev_close alpaca {a_ref} vs polygon {pc} (date-keyed) — using delayed",
                        json.dumps({"ticker": c["ticker"], "alpaca": a_ref, "polygon": pc,
                                    "prev_trade_date": prev_trade_date.isoformat() if prev_trade_date else None}))
                continue
            dl = c.get("gap_pct_delayed", c["gap_pct"])
            rt_gap = (rt_price - pc) / pc * 100
            if abs(rt_gap - dl) > 30:   # bad print / odd-lot / symbology mismatch → keep delayed
                # #490 C1 fix: the clamp is LOUD now — "zero clamp events" was vacuous when it
                # silently continued. (Pass-2 delayed-fallback population keeps this clamp; the
                # universe path replaced it with Q4, see _rt_quality_read.)
                if _audit_dedupe_check(c["ticker"], adate, "ep_rt_gap_clamped"):
                    await log_audit_event("ep_rt_gap_clamped",
                        f"{c['ticker']} rt {rt_gap:.1f}% vs delayed {dl:.1f}% (Δ>30pp) — keeping delayed",
                        json.dumps({"ticker": c["ticker"], "rt_gap": round(rt_gap, 2),
                                    "delayed_gap": round(dl, 2), "tick_et": now_et.strftime("%H:%M")}))
                continue
            c["gap_pct_rt"] = round(rt_gap, 2)
            c["prev_close_alpaca"] = a_ref
            c["prev_close_verified"] = a_ref is not None
            ts = sn.get("price_ts")
            if ts is not None:
                try:
                    c["rt_price_age_s"] = round((now_et - ts).total_seconds(), 1)
                except Exception:  # loud-ok: rt_price_age_s is observability-only; a bad timestamp just omits it
                    pass
            # #490 never-loosen extensions on the RT-only (superset flip-up) admission class:
            # unverified prev_close requires Q3 bar corroboration (§2.1); a halt_suspect cannot
            # be RT-only admitted this tick (§4). Only consulted by _floor under authority;
            # in shadow they are telemetry (the reject/halt events still measure the class).
            if rt_gap >= MIN_GAP_PCT > dl:
                if a_ref is None and not _q3_bar_corroborated(sn, pc, now_et):
                    c["_rt_admit_block"] = "no_bar_confirm"
                    if _audit_dedupe_check(c["ticker"], adate, "ep_rt_tick_quality_reject"):
                        await log_audit_event("ep_rt_tick_quality_reject",
                            f"{c['ticker']} flip-up rt {rt_gap:.1f}% REJECTED (no_bar_confirm — "
                            f"prev_close unverified) @ {now_et:%H:%M} ET",
                            json.dumps({"ticker": c["ticker"], "reason": "no_bar_confirm",
                                        "rt_gap": round(rt_gap, 2), "prev_close_verified": False,
                                        "tick_et": now_et.strftime("%H:%M")}))
                elif _is_halt_suspect(c["ticker"], sn, now_et):
                    c["_rt_admit_block"] = "halt_suspect"
                    if _audit_dedupe_check(c["ticker"], adate, "ep_rt_halt_suspect"):
                        await log_audit_event("ep_rt_halt_suspect",
                            f"{c['ticker']} flip-up rt {rt_gap:.1f}% but print frozen + quote dead — "
                            f"no RT-only admission this tick",
                            json.dumps({"ticker": c["ticker"], "rt_gap": round(rt_gap, 2),
                                        "tick_et": now_et.strftime("%H:%M")}))
            if authoritative:
                c["gap_pct"] = round(rt_gap, 2)
                c["current_price"] = rt_price   # §6.4 (C5): the alert/scan-log/Telegram row renders
                                                # the price the decision actually used
                c["price_source"] = "alpaca_sip"
            elif down_authoritative and rt_gap < MIN_GAP_PCT <= dl:
                # #490 DOWN-ONLY authority — the REMOVE half of `ep_rt_gap_authoritative`, split out
                # so the stale-false-admit cleanup can run WITHOUT the flip-up expansion (which adds
                # ~+25 candidates/day to the LLM grading path and eats the 09:45 ORB latency margin;
                # evidence: docs/analysis/490_delay_missed_eps_2026-08-01.md §6).
                # STRICTLY REMOVAL: the guard `rt_gap < MIN_GAP_PCT <= dl` is the flip-DOWN condition
                # exactly, so this branch can only ever push a decided gap BELOW the floor. It can
                # never admit — a superset-only admit (dl < MIN_GAP_PCT) fails `MIN_GAP_PCT <= dl`
                # and is left on the delayed path, where `_floor` drops it as it does today.
                c["gap_pct"] = round(rt_gap, 2)
                c["current_price"] = rt_price
                c["price_source"] = "alpaca_sip"
            # #490 measurement subset (2026-08-01, telemetry-only): the day-level dedupe logs a
            # flip-down ONCE per ticker per day, so it records THAT a name went stale but not
            # whether it was STILL stale at 09:31 when the entry fires. That is exactly the number
            # the entry-time re-validation decision needs, and it is currently unmeasurable —
            # FTNT 7/30 is a single observation. Inside the pre-entry window the dedupe key carries
            # the tick, giving per-tick resolution where the entry decision is made. Outside it,
            # unchanged. Bounded: only flip-down names, only 9:15-9:35, audit-only, no Telegram.
            # Computed HERE, above the flip-up branch, so the flip-down below stays an `elif` —
            # the original control flow is preserved exactly rather than restructured.
            _fd_pre_entry = now_et.hour == 9 and 15 <= now_et.minute <= 35
            _fd_key = f"ep_rt_floor_flip_down@{now_et:%H:%M}" if _fd_pre_entry else "ep_rt_floor_flip_down"
            if rt_gap >= MIN_GAP_PCT > dl and _audit_dedupe_check(c["ticker"], adate, "ep_rt_floor_flip_up"):
                _flip_msg = (f"{c['ticker']} rt {rt_gap:.1f}% ≥10 > delayed {dl:.1f}% @ {now_et:%H:%M} ET"
                             + ("" if authoritative else " (SHADOW — would have caught)"))
                await log_audit_event("ep_rt_floor_flip_up", _flip_msg,
                    json.dumps({"ticker": c["ticker"], "rt_gap": round(rt_gap, 2), "delayed_gap": round(dl, 2),
                                "tick_et": now_et.strftime("%H:%M"), "authoritative": authoritative}))
                # #489: AUDIT-ONLY (operator 7/21 — was a per-ticker Telegram, too noisy: 10+/volatile open).
                # The hybrid-catchable class is "the fix works" shadow proof, not an actionable miss; it stays
                # in mi_audit_log for /audit + the residual dashboard. The residual class digests once/morning.
            elif rt_gap < MIN_GAP_PCT <= dl and _audit_dedupe_check(c["ticker"], adate, _fd_key):
                # `acted` distinguishes a real removal from shadow telemetry — without it the event
                # reads identically in both modes and verify-live cannot tell whether the cleanup
                # is actually running.
                _acted = authoritative or down_authoritative
                await log_audit_event("ep_rt_floor_flip_down",
                    f"{c['ticker']} delayed {dl:.1f}% >=10 > rt {rt_gap:.1f}% (stale false-admit "
                    + ("REMOVED)" if _acted else "cleaned — SHADOW, still admitted)"),
                    json.dumps({"ticker": c["ticker"], "rt_gap": round(rt_gap, 2), "delayed_gap": round(dl, 2),
                                "acted": _acted, "pre_entry": _fd_pre_entry,
                                "authoritative": authoritative,
                                "down_authoritative": down_authoritative,
                                "tick_et": now_et.strftime("%H:%M")}))
            elif rt_gap >= MIN_GAP_PCT and dl >= MIN_GAP_PCT and _audit_dedupe_check(
                    c["ticker"], adate, "ep_rt_admit"):
                # #490 leg 2, added 2026-08-03 — TELEMETRY ONLY, no control-flow change (third arm
                # of the existing chain; both branches above are untouched).
                #
                # The two branches above fire only when RT and delayed DISAGREE across the floor,
                # and the flip-UP is deduped once per DAY. So when they AGREE — the case for an
                # alert that is about to be written — nothing is recorded at all. FTK on 2026-08-03
                # made that concrete: flip-DOWN at 07:25 (rt 7.6%), alert WRITTEN at 08:45 on a
                # delayed 10.45%, flip-DOWN again at 09:20 (rt 8.75%). The overlay demonstrably ran
                # at 08:45 and did not remove it, which is consistent with a genuine recovery above
                # the floor — but NOTHING logged the passing value, so verify-live leg 2 ("removed
                # tickers absent from mi_ep_alerts") could be neither confirmed nor refuted.
                #
                # An unanswerable verify leg is worse than a failing one: it reads as a pass.
                await log_audit_event(
                    "ep_rt_admit",
                    f"{c['ticker']} rt {rt_gap:.1f}% and delayed {dl:.1f}% BOTH >=10 "
                    f"@ {now_et:%H:%M} ET — real-time AGREES with the admit",
                    json.dumps({"ticker": c["ticker"], "rt_gap": round(rt_gap, 2),
                                "delayed_gap": round(dl, 2),
                                "tick_et": now_et.strftime("%H:%M"),
                                "authoritative": authoritative}))
        return _floor(candidates)
    except Exception as e:
        logger.warning(f"Pass-2 failed, degrading to delayed 10% floor: {e}")
        return [c for c in candidates if c.get("gap_pct", 0) >= MIN_GAP_PCT]


# Strong refs for fire-and-forget watchdog tasks — asyncio only keeps a weak ref, so a task with
# no live reference can be GC'd mid-run. add on launch, discard on done.
_WATCHDOG_BG_TASKS: set = set()


async def _rt_miss_watchdog(rt_universe: list, caught: set, now_et: datetime,
                            snaps: "dict | None" = None) -> None:
    """#489 real-time MISS detector — ALERT-ONLY (records; a morning digest sends the summary). The
    hybrid structurally can't catch the residual (flat-premarket-then-explode) class in real time, but
    this CAN surface it: each in-window tick, fetch REAL-TIME Alpaca SIP prices for the full RT universe
    (every ticker that cleared the non-gap filters) and record any that has crossed the 10% floor
    real-time, PASSES the scan's mechanical EP gates (extension / mcap / ADV$ / ATR), but is NOT in
    `caught` (the PRE-Pass-2 5% superset — so the hybrid-catchable class is excluded and only the TRUE
    residual, delayed <5%, is flagged; no double-fire w/ the floor-flip). Audit-only (operator 7/21 —
    `send_rt_miss_digest` sends ONE morning summary, not a per-tick blast). #490's Pass-0 fetch in
    OBSERVE mode — never changes what we enter, not THE LINE. Deduped per ticker/day; never raises.

    #490 RT-1: `snaps` accepts the Pass-0 pre-fetched universe map (§5.1 — one universe fetch per
    tick, not two). None (universe flag off / Pass-0 degraded) → own fetch, exactly as before."""
    if not (EP_RT_MISS_WATCHDOG_ENABLED and EP_RT_PASS2_ENABLED) or not rt_universe:
        return
    mod = now_et.hour * 60 + now_et.minute
    if not (9 * 60 + 31 <= mod <= 9 * 60 + 44):   # only the ORB window — a later cross can't be entered anyway
        return
    try:
        from agents.market_intelligence import collector
        pc_map = {t: pc for t, pc in rt_universe}
        if snaps is None:
            snaps = await collector.get_alpaca_snapshots_batch(list(pc_map.keys()))
        adate = now_et.date()
        # Missed crossers = real-time ≥10% but NOT a scan candidate (the delay couldn't see them).
        missed = []
        for tkr, sn in snaps.items():
            if tkr in caught:
                continue
            price, pc = sn.get("price"), pc_map.get(tkr)
            if not price or not pc:
                continue
            rt_gap = (price - pc) / pc * 100
            if rt_gap >= MIN_GAP_PCT:
                missed.append((tkr, pc, rt_gap))
        if not missed:
            return
        # #489 (A): mechanical EP gates — alert only on a REAL EP-shaped miss, not every 10% spike.
        # Apply the same NON-LLM gates the live scan uses: already-extended (≥50% up over ~5d), then
        # check_filters (market-cap ≥$500M / ADV$ / ATR). Drops micro-cap pumps, illiquid, choppy, and
        # extended names. The full catalyst + HIGH-grade confirmation is B (the #490 shadow scoring).
        ext_low = {}
        try:
            pool = await get_pool()
            async with pool.acquire() as conn:
                rows = await conn.fetch("""
                    SELECT ticker, MIN(close) AS low_close FROM mi_daily_closes
                    WHERE ticker = ANY($1) AND trade_date >= $2 AND trade_date < $3 GROUP BY ticker
                """, [m[0] for m in missed], adate - timedelta(days=10), adate)
            ext_low = {r["ticker"]: float(r["low_close"]) for r in rows}
        except Exception as e:  # loud-ok: extension lookup best-effort; a failure just skips this one gate
            logger.warning(f"rt_miss_watchdog extension query failed (non-fatal): {e}")
        for tkr, pc, rt_gap in missed:
            low5 = ext_low.get(tkr)
            if low5 and (pc - low5) / low5 * 100 >= MAX_EXTENSION_PCT:
                continue   # already extended — the live scan would have skipped it too
            try:
                passed, _skip_reason = await check_filters(tkr, adate)
            except Exception:  # loud-ok: a filter-lookup failure must not silently drop a real miss
                passed = True
            if not passed:
                continue
            if not _audit_dedupe_check(tkr, adate, "ep_rt_live_miss"):
                continue
            await log_audit_event(
                "ep_rt_live_miss",
                f"{tkr} rt {rt_gap:.1f}% ≥10 @ {now_et:%H:%M} ET, passes mechanical EP gates but NOT a scan candidate (delay-missed EP)",
                json.dumps({"ticker": tkr, "rt_gap": round(rt_gap, 2), "tick_et": now_et.strftime("%H:%M")}))
            # #489 (operator 7/21): AUDIT-ONLY — no per-ticker Telegram (was too noisy). The residual
            # misses digest ONCE per morning via send_rt_miss_digest (~10:00 ET), not a per-tick blast.
    except Exception as e:
        logger.warning(f"rt_miss_watchdog failed (alert-only, non-fatal): {e}")


async def send_rt_miss_digest(run_date=None) -> int:
    """#489 (operator 7/21): ONE morning digest of the residual real-time EP misses. The watchdog records
    each `ep_rt_live_miss` audit-only per in-window tick; this sends a single summary after the ORB window
    instead of a per-ticker blast. No-money observability; safe no-op if none. Returns the count.

    #490 RT-1 (operator fork 4 — shadow surfacing DIGEST-ONLY): the same digest carries the day's
    `ep_rt_universe_catch` shadow events (Pass-0 would-have-caught, incl. pre-open — a window the
    watchdog never covers). Zero catch events (universe flag off, today's prod) → the message is
    byte-identical to before."""
    d = run_date or et_today()
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT detail FROM mi_audit_log WHERE event_type='ep_rt_live_miss'
                  AND (created_at AT TIME ZONE 'America/New_York')::date = $1
                ORDER BY created_at
            """, d)
            catch_rows = await conn.fetch("""
                SELECT detail FROM mi_audit_log WHERE event_type='ep_rt_universe_catch'
                  AND (created_at AT TIME ZONE 'America/New_York')::date = $1
                ORDER BY created_at
            """, d)
    except Exception as e:  # loud-ok: digest is best-effort observability; audit rows remain durable
        logger.warning(f"send_rt_miss_digest query failed (non-fatal): {e}")
        return 0

    def _parse(rs):
        out = []
        for r in rs:
            try:
                j = json.loads(r["detail"]) if isinstance(r["detail"], str) else (r["detail"] or {})
                out.append(j)
            except (ValueError, TypeError):
                continue
        return out

    miss_js = _parse(rows)
    items = [f"{j.get('ticker', '?')} +{j.get('rt_gap', '?')}% @{j.get('tick_et', '?')}" for j in miss_js]
    miss_tickers = {j.get("ticker") for j in miss_js}
    catch_items = [
        f"{j.get('ticker', '?')} +{j.get('rt_gap', '?')}% @{j.get('tick_et', '?')}"
        for j in _parse(catch_rows)
        if j.get("ticker") not in miss_tickers   # the in-window overlap is already in the miss line
    ]
    if not items and not catch_items:
        return 0
    parts = []
    if items:
        parts.append(
            f"🚨 Real-time EP misses today ({len(items)} residual — the delay-missed class the hybrid can't "
            f"catch): " + " · ".join(items) + ". No entry (observability); grade/catalyst unconfirmed = "
            f"Part B / #490 shadow.")
    if catch_items:
        parts.append(
            f"👁 #490 rt-universe shadow catches ({len(catch_items)} more, guard-passing): "
            + " · ".join(catch_items) + ".")
    try:
        from agents.market_intelligence.briefing import send_telegram_message
        await send_telegram_message(" ".join(parts))
    except Exception:  # loud-ok: Telegram best-effort; the audit rows are durable
        pass
    return len(items) + len(catch_items)


async def run_ep_scan(prev_close_date: str | None = None) -> list[dict]:
    """
    Run pre-market EP scan.
    Returns list of EP candidates with scores.

    prev_close_date: "YYYY-MM-DD" of the last trading day
    """
    today = et_today()
    today_str = today.strftime("%Y-%m-%d")
    prev_date = prev_close_date or today_str  # fallback

    # #490 §2.1 — the KNOWN previous trading date, for the date-keyed Alpaca prev_close
    # cross-check (selects daily_bar vs previous_daily_bar by bar-date, no clock heuristic).
    # last_trading_day approximates weekends only; on a post-holiday morning neither Alpaca
    # bar matches → the cross-check cleanly reports "unavailable" (§2.1/O1 fail-safe:
    # Polygon denominator kept unverified, RT-only admission requires Q3) — never a wrong-day compare.
    from shared.dates import last_trading_day
    if prev_close_date and prev_close_date != today_str:
        _prev_trade_date = date.fromisoformat(prev_close_date)
    else:
        _prev_trade_date = last_trading_day(today - timedelta(days=1))

    # Get regime for threshold adjustment
    regime = await get_latest_regime()
    regime_label = regime.get("regime", "Unknown") if regime else "Unknown"
    ep_threshold = regime.get("ep_threshold", 70) if regime else 70
    regime_multiplier = 1.2 if regime_label == "Bull" else 1.0

    # Get stored ADV map (from last RS run)
    adv_map = await get_adv_map(prev_date)

    # Authoritative ETF/non-stock filter from security_types table.
    # _SKIP_TICKERS catches known leveraged ETFs fast; this catches anything
    # classified as non-common-stock in our reference data (ETF, ETP, ETPT, etc.).
    #
    # Fix 2026-05-17 (P2.0b): also build `_known_stock_tickers` so we can
    # detect candidates that are NEITHER classified as stock NOR non-stock
    # (i.e., not in mi_security_types at all). USAX/USGG 4/20 case: the
    # weekly Monday refresh hadn't run yet for those names, so they slipped
    # through `_non_stock_tickers` (empty for unknown tickers) and got
    # admitted as EP candidates despite being ETFs. Fail-safe: skip
    # unclassified candidates entirely — the next weekly refresh adds them
    # to mi_security_types and they'll be properly admitted/excluded.
    _non_stock_tickers: set[str] = set()
    _known_stock_tickers: set[str] = set()
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            non_stock_rows = await conn.fetch(
                "SELECT ticker FROM mi_security_types WHERE security_type NOT IN ('CS', 'ADRC')"
            )
            stock_rows = await conn.fetch(
                "SELECT ticker FROM mi_security_types WHERE security_type IN ('CS', 'ADRC')"
            )
        _non_stock_tickers = {r["ticker"] for r in non_stock_rows}
        _known_stock_tickers = {r["ticker"] for r in stock_rows}
        logger.info(
            f"EP scan: security_types loaded — "
            f"{len(_known_stock_tickers)} stock, "
            f"{len(_non_stock_tickers)} non-stock"
        )
    except Exception as e:
        logger.warning(f"EP scan: could not load security_types ({e}) — relying on SKIP_TICKERS only")

    logger.info(f"EP scan: regime={regime_label}, threshold={ep_threshold}")

    # R4 (2026-05-17 ship): cache the set of tickers currently in an
    # active (Accelerating/Mainstream) theme. Built once per scan tick
    # to avoid N+1 PostgreSQL array-containment queries per ticker
    # (Gemini 2026-05-17). Per-ticker membership check is O(1) on the
    # set. Lookups against `_in_active_theme_set` happen inside
    # `_score_ep` via the new `in_active_theme` parameter.
    _in_active_theme_set: set[str] = set()
    try:
        from agents.market_intelligence.db import get_active_themes
        _active_themes = await get_active_themes(stale_after_days=7)
        for _theme in _active_themes:
            stage = (_theme.get("stage") or "").strip()
            if stage in ("Accelerating", "Mainstream"):
                for _t in (_theme.get("tickers") or []):
                    _in_active_theme_set.add(_t)
        logger.info(
            f"EP scan: {len(_in_active_theme_set)} tickers in active themes "
            f"(Accelerating/Mainstream) for R4 bonus"
        )
    except Exception as e:
        logger.warning(f"EP scan: theme set load failed ({e}) — R4 bonus disabled this tick")

    # Narrative-cohort membership set (#201 fire panel — the #167 narrative axis).
    # Built once per scan from prior-days narrative_cogap candidates (the lane is
    # EOD, so same-day cohorts don't exist at premarket; prior days are the
    # available signal). ADVISORY only — one of several fire axes. Nearly empty
    # today (lane accrual is slow); the plumbing is forward-ready for the 6/23
    # narrative promote-gate.
    # Lane-2 cohorts kept WHOLE for the judge (plan lane2-judge-theme-axis): the judge
    # matches the catalyst against narrative {name, thesis, tickers} semantically, so a
    # NEW JOINER of a spreading story lights the axis even when set-membership is false
    # (RCAT 5/28 class). One fetch; the membership set is derived from it.
    _narrative_cohorts: list[dict] = []
    _in_narrative_cohort_set: set[str] = set()
    try:
        from agents.market_intelligence.db import get_narrative_theme_candidates
        _narrative_cohorts = await get_narrative_theme_candidates(days=5)
        _in_narrative_cohort_set = {
            _t for _c in _narrative_cohorts for _t in (_c.get("tickers") or [])
        }
        logger.info(
            f"EP scan: {len(_in_narrative_cohort_set)} tickers in prior-5d "
            f"narrative cohorts (fire panel narrative axis; {len(_narrative_cohorts)} "
            f"cohort(s) fed to the judge theme axis)"
        )
    except Exception as e:
        logger.warning(f"EP scan: narrative set load failed ({e}) — narrative axis off this tick")

    # Minutes since market open — used for projected volume calculation post-open
    from agents.market_intelligence.collector import _ET
    now_et = datetime.now(_ET)
    # _SESSION_MINUTES is module-level (390) — shared with _snap_candidate since #490 RT-1.
    if now_et.hour > 9 or (now_et.hour == 9 and now_et.minute >= 30):
        _minutes_since_open = max(1, (now_et.hour - 9) * 60 + (now_et.minute - 30))
    else:
        _minutes_since_open = None  # pre-market — no projection

    # Fetch all snapshots (1 Polygon call)
    snapshots = await get_snapshot_all()
    if not snapshots:
        logger.warning("No snapshot data — market may not be open yet")
        return []

    # Find gap candidates
    candidates = []
    _unclassified_skipped = 0  # P2.0b counter
    _rt_universe = []   # #489 miss watchdog: every ticker that clears all NON-gap filters
    for ticker, snap in snapshots.items():
        try:
            # Skip warrants, units, non-standard symbols, ETFs, and leveraged products
            if len(ticker) > MAX_TICKER_LEN or ticker in _SKIP_TICKERS or "." in ticker:
                continue
            if ticker in _non_stock_tickers:
                continue
            # P2.0b 2026-05-17: fail-safe for unclassified candidates.
            # If a ticker is not in EITHER set, mi_security_types hasn't
            # classified it yet (weekly cadence — gap window up to 7 days).
            # USAX/USGG class names slipped through this gap on 4/20.
            # Skip the unknown — next weekly refresh will classify. Don't
            # per-ticker log (would flood scan_log with thousands of names);
            # the aggregate count is logged once at scan end.
            if _known_stock_tickers and ticker not in _known_stock_tickers:
                _unclassified_skipped += 1
                continue

            prev_close = snap.get("prevDay", {}).get("c", 0)
            if not prev_close or prev_close < MIN_PREV_CLOSE:
                continue

            # Skip illiquid stocks — stale/erroneous quotes create phantom gaps
            prev_volume = snap.get("prevDay", {}).get("v", 0) or 0
            if prev_volume < MIN_PREV_DAY_VOLUME:
                continue

            _rt_universe.append((ticker, prev_close))   # #489 watchdog: this ticker cleared all non-gap filters

            # Current price: min.c (latest minute bar, includes pre/post-market)
            # → day.o (regular session open) → lastTrade.p (fallback)
            # Pre-market: min.c is the only field that updates before 9:30 open
            current_price = (
                snap.get("min", {}).get("c")
                or snap.get("day", {}).get("o")
                or snap.get("lastTrade", {}).get("p", 0)
            )
            if not current_price:
                continue

            gap_pct = (current_price - prev_close) / prev_close * 100
            if gap_pct < _pass1_gap_floor():   # #489: superset floor when hybrid on; else MIN_GAP_PCT
                continue

            # Volume / ADV / open-intensity + the dict shape live in _snap_candidate (#490 RT-1
            # extraction — shared verbatim with the Pass-0 universe admission path).
            candidates.append(_snap_candidate(
                ticker, snap, prev_close, current_price, gap_pct, adv_map, _minutes_since_open))
        except Exception:
            continue

    # #489 Pass 2 — real-time Alpaca SIP confirm on the (superset) candidates BEFORE ranking/scoring,
    # so the sort, top-20 cap, _score_ep, scan_log row, and the ORB decision all read the
    # authoritative gap. No-op (candidates unchanged, byte-identical) when EP_RT_PASS2_ENABLED is off.
    # #489: capture the PRE-Pass-2 superset (the 5%-floor delayed candidates = the hybrid-catchable class)
    # so the watchdog EXCLUDES them and flags only the TRUE residual (delayed <5%, never a candidate). Else a
    # 5-10%-delayed ticker that Pass-2 shadow-drops double-fires floor-flip + watchdog (AEHR, 7/21).
    _superset = {c["ticker"] for c in candidates}
    # #490 Pass-0 — full-universe rt overlay (no-op + no fetch when EP_RT_UNIVERSE_ENABLED is off,
    # the deploy default). One universe fetch per tick: Pass-2 and the watchdog reuse `_rt_snaps`.
    candidates, _rt_snaps = await _apply_rt_universe_overlay(
        candidates, _rt_universe, snapshots, adv_map, _minutes_since_open, now_et, _prev_trade_date)
    candidates = await _apply_realtime_pass2(
        candidates, now_et, prev_trade_date=_prev_trade_date, snaps=_rt_snaps)
    # #489: launch the alert-only miss watchdog CONCURRENTLY, not inline — it fetches the full RT universe
    # (~34 sequential Alpaca calls) and must NEVER sit on the ORB-window scoring/entry critical path (its
    # result is never consumed). Audit-only (send_rt_miss_digest sends the morning summary); the task-set
    # holds a strong ref (asyncio only keeps a weak one).
    # #490: exclusion set = the pre-Pass-2 superset ∪ anything that IS a candidate now (a Pass-0
    # authoritative admit is a real scan candidate — the watchdog must not re-flag it as a miss).
    _wt = asyncio.create_task(_rt_miss_watchdog(
        _rt_universe, _superset | {c["ticker"] for c in candidates}, now_et, snaps=_rt_snaps))
    _WATCHDOG_BG_TASKS.add(_wt)
    _wt.add_done_callback(_WATCHDOG_BG_TASKS.discard)

    # Sort by gap size descending — score the biggest movers first
    candidates.sort(key=lambda c: c["gap_pct"], reverse=True)
    rank_by_gap = {c["ticker"]: i + 1 for i, c in enumerate(candidates)}
    logger.info(f"Gap candidates ≥{MIN_GAP_PCT}%: {len(candidates)}"
                + (f" (top: {candidates[0]['ticker']} {candidates[0]['gap_pct']:.1f}%)" if candidates else ""))
    # P2.0b 2026-05-17: log aggregate count of unclassified-skip — surfaces
    # when the weekly mi_security_types refresh is overdue. If this is high
    # (≥10/scan), there are many new tickers that haven't been classified;
    # consider bumping the refresh cadence from weekly to daily.
    if _unclassified_skipped > 0:
        logger.info(
            f"EP scan: {_unclassified_skipped} candidates skipped — unclassified "
            f"(not in mi_security_types). Weekly refresh runs Mondays; if "
            f"this number is high consistently, bump to daily."
        )
    if not candidates:
        return []

    # Batch-fetch volume history for all candidates (one DB query)
    candidate_tickers = [c["ticker"] for c in candidates]
    vol_history_map = await get_volume_history(candidate_tickers)

    # Batch-fetch 3-month-ago closes for prior momentum check
    prior_3m_map: dict[str, float] = {}
    try:
        pool = await get_pool()
        target_date = today - timedelta(days=90)
        async with pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT DISTINCT ON (ticker) ticker, close
                FROM mi_daily_closes
                WHERE ticker = ANY($1) AND trade_date <= $2 AND trade_date >= $3
                ORDER BY ticker, trade_date DESC
            """, candidate_tickers, target_date, target_date - timedelta(days=14))
        prior_3m_map = {r["ticker"]: float(r["close"]) for r in rows}
    except Exception as e:
        logger.warning(f"Failed to fetch 3-month closes for prior momentum: {e}")

    # Compute proper 20-day ADV for non-universe candidates.
    # Top 20 are the scored cohort. Ranks 21-50 are a telemetry-only probe
    # (Option 2): synthesize ADV → rel_volume so we can detect "did rank
    # 21-50 candidates with high rel_volume turn into winners?" Without
    # ADV those rows hit mi_ep_scan_log with placeholder prevDay.v which
    # is useless for outcome analysis. Probe-stage results emit an
    # `ep_adv_probe_synthesized` audit event — `data_gated_reviews.yaml`
    # entry `adv_probe_retirement` triggers a manual review at 30 days.
    non_universe = [c for c in candidates[:50] if c["adv_source"] == "pending"]
    if non_universe:
        logger.info(f"Fetching 20-day ADV for {len(non_universe)} non-universe candidates (incl. rank 21-50 probe)...")
        adv_tasks = [_compute_adv_from_polygon(c["ticker"], today) for c in non_universe]
        adv_results = await asyncio.gather(*adv_tasks)
        for c, computed_adv in zip(non_universe, adv_results):
            if computed_adv:
                c["adv"] = computed_adv
                c["adv_source"] = "polygon_20d"
                c["rel_volume"] = round(c["today_volume"] / computed_adv, 2) if computed_adv > 0 else None
                if c["rel_volume"] and _minutes_since_open and _minutes_since_open >= 15:
                    c["projected_vol_multiple"] = round(c["rel_volume"] * (_SESSION_MINUTES / _minutes_since_open), 1)
                logger.info(f"  {c['ticker']}: ADV={computed_adv:,.0f} → rel_vol={c.get('rel_volume')}x")
                # Probe-only event for ranks 21-50. The top-20 cohort is the
                # canonical scored set and doesn't need a separate event.
                gap_rank = rank_by_gap.get(c["ticker"])
                if gap_rank and gap_rank > 20:
                    await log_audit_event(
                        "ep_adv_probe_synthesized",
                        f"{c['ticker']} rank={gap_rank} gap={c['gap_pct']:.1f}% rel_vol={c['rel_volume']}x",
                        json.dumps({
                            "ticker": c["ticker"],
                            "scan_date": today.isoformat(),
                            "rank_by_gap": gap_rank,
                            "gap_pct": round(c["gap_pct"], 2),
                            "adv_polygon_20d": int(computed_adv),
                            "rel_volume": c.get("rel_volume"),
                            "projected_vol_multiple": c.get("projected_vol_multiple"),
                            "today_volume": int(c["today_volume"]),
                        }),
                    )

    # Batch-fetch MIN close over last 5 trading days for extension check.
    # Using MIN (not the close from exactly 5 days ago) catches stocks that surged
    # 3 days ago and are now re-extending — a single look-back point would miss this.
    extension_map: dict[str, float] = {}
    try:
        window_start = today - timedelta(days=10)  # ~5 trading days + buffer
        async with pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT ticker, MIN(close) AS low_close
                FROM mi_daily_closes
                WHERE ticker = ANY($1) AND trade_date >= $2 AND trade_date < $3
                GROUP BY ticker
            """, candidate_tickers, window_start, today)
        extension_map = {r["ticker"]: float(r["low_close"]) for r in rows}
    except Exception as e:
        logger.warning(f"Failed to fetch 5-day closes for extension check: {e}")

    # Batch-fetch recent EP alerts for cooldown check (same ticker in last 60 days)
    # Also check today — skip re-scoring tickers already alerted in an earlier scan run
    cooldown_tickers: set[str] = set()
    cooldown_last_alert: dict = {}  # #170 shadow: ticker -> most-recent prior alert_date
    already_today: set[str] = set()
    try:
        async with pool.acquire() as conn:
            # LIVE rows only (#268 review, 2026-06-11): replay batches insert
            # source='historical_scan' rows across the cooldown window —
            # unfiltered, they SUPPRESS real EP alerts (the one trade-path
            # contamination the replay could cause).
            rows = await conn.fetch(f"""
                SELECT DISTINCT ticker FROM mi_ep_alerts
                WHERE ticker = ANY($1) AND alert_date >= $2 AND alert_date < $3
                  AND {LIVE_SOURCE_SQL}
            """, candidate_tickers, today - timedelta(days=EP_COOLDOWN_DAYS), today)
            cooldown_tickers = {r["ticker"] for r in rows}
            rows_today = await conn.fetch(f"""
                SELECT DISTINCT ticker FROM mi_ep_alerts
                WHERE ticker = ANY($1) AND alert_date = $2
                  AND {LIVE_SOURCE_SQL}
            """, candidate_tickers, today)
            already_today = {r["ticker"] for r in rows_today}
    except Exception as e:
        logger.warning(f"Failed to fetch EP cooldown data: {e}")

    # #170 shadow: prior-alert dates for the re-setup classifier. SEPARATE query,
    # independently fail-open, so it can NEVER affect the cooldown suppression
    # above (on any failure the dict stays empty -> the shadow simply no-ops).
    try:
        async with pool.acquire() as conn:
            _date_rows = await conn.fetch(f"""
                SELECT ticker, MAX(alert_date) AS last_alert FROM mi_ep_alerts
                WHERE ticker = ANY($1) AND alert_date >= $2 AND alert_date < $3
                  AND {LIVE_SOURCE_SQL}
                GROUP BY ticker
            """, candidate_tickers, today - timedelta(days=EP_COOLDOWN_DAYS), today)
            cooldown_last_alert = {r["ticker"]: r["last_alert"] for r in _date_rows}
    except Exception as e:
        logger.warning(f"#170 shadow: failed to fetch cooldown last-alert dates: {e}")

    # Score each candidate (rate-limited FMP calls)
    results = []
    scan_log: list[dict] = []  # accumulated for batch DB write at end

    def _scan_row(c: dict, *, reason: str | None, ep_score: float | None,
                  tier: str | None, catalyst_quality: str | None) -> dict:
        return {
            "scan_date": today,
            "ticker": c["ticker"],
            "gap_pct": c.get("gap_pct"),
            "prev_close": c.get("prev_close"),
            "rel_volume": c.get("rel_volume"),
            "filter_reason": reason,
            "ep_score": ep_score,
            "score_tier": tier,
            "catalyst_quality": catalyst_quality,
            "scan_time_et": now_et,
            "rank_by_gap": rank_by_gap.get(c["ticker"]),
            "projected_vol_multiple": c.get("projected_vol_multiple"),
            "pm_rvol": c.get("pm_rvol"),
            "adv": c.get("adv"),
            "adv_source": c.get("adv_source"),
            "minutes_since_open": _minutes_since_open,
            # #490 G1 (design M5/C4 — REQUIRED RT-1 scope): the per-row rt-vs-delayed evidence
            # the RT-2 shadow gates read. Columns exist since #489; never threaded until now.
            "gap_pct_rt": c.get("gap_pct_rt"),
            "gap_pct_delayed": c.get("gap_pct_delayed"),
            "price_source": c.get("price_source"),
            "rt_price_age_s": c.get("rt_price_age_s"),
            "prev_close_alpaca": c.get("prev_close_alpaca"),
        }

    def _log_filtered(c: dict, reason: str) -> None:
        scan_log.append(_scan_row(
            c, reason=reason, ep_score=None, tier=None, catalyst_quality=None,
        ))

    # Log candidates beyond top-20 cap
    for c in candidates[20:]:
        _log_filtered(c, f"outside top-20 gap cap (gap {c['gap_pct']:.1f}%)")

    # #444 mode-label sweep: the catalyst-downgrade Telegram below (prose-mismatch
    # branch) is MAGNA53-bound. Resolve the owning strategy's account_mode lazily
    # (fetched at most once per scan tick, only if a downgrade actually fires) so
    # the label reflects live vs paper instead of the legacy global default —
    # without adding a DB round-trip to the common no-downgrade path.
    _magna53_mode_fetched = False
    _magna53_account_mode: str | None = None

    # ── #490 §6.1 — real-time volume/RVOL refresh (co-requisite, SEPARATE flip) ────────────
    # ONE batched Alpaca minute-bars call on the scored cohort only (≤20 syms), summed into the
    # two RVOL@T anchors. The delayed `day.v`/`min.av` hasn't seen the flat-premarket class's
    # real session volume, so the session anchor false-rejects (`session_rvol_too_low`) exactly
    # the names the RT gap admits. Authority = `ep_rt_volume_authoritative` runtime toggle
    # (default off; RT-5, operator-flipped ≥3 market days after the gap flip). Toggle off →
    # shadow telemetry only (ep_rt_volume_shadow / ep_rt_rvol_gate_flip — the named flip list).
    # Master flag off → no fetch, byte-identical.
    _rt_vol_map: dict = {}
    _rt_vol_authoritative = False
    if EP_RT_UNIVERSE_ENABLED and EP_RT_PASS2_ENABLED and candidates:
        try:
            _rt_vol_authoritative = await get_runtime_toggle(
                "ep_rt_volume_authoritative", "EP_RT_VOLUME_AUTHORITATIVE", default=False)
            from agents.market_intelligence.collector import get_alpaca_minute_cum_volumes
            _rt_vol_map = await get_alpaca_minute_cum_volumes(
                [c["ticker"] for c in candidates[:20]], now_et)
        except Exception as _ve:  # loud-ok: rt volume degrades to the delayed read — today's behavior
            logger.warning(f"#490 rt volume fetch failed (delayed volume keeps deciding): {_ve}")
            _rt_vol_map = {}

    for c in candidates[:20]:  # Cap at 20 to stay within FMP call budget
        ticker = c["ticker"]
        rel_volume = c.get("rel_volume") or 0

        # ── Volume gate (RVOL@T) ──────────────────────────────────────────
        # ONE primitive, two anchors. Pre-9:30 → pm anchor (cumulative from
        # 4:00 ET vs 22-day pre-market baseline). 9:30 onward → session
        # anchor (cumulative from 9:30 vs 22-day session baseline). RVOL@T
        # answers: "is today's pace at this clock-minute above this ticker's
        # normal pace at this clock-minute." Replaces the structurally broken
        # `today_5min_vol / 390min_ADV` ratio that mathematically rejected
        # every name in the first 15 min unless they had outsized pre-market
        # volume (HUT/BLMN/GLW false-rejects 5/6).
        #
        # Silent fallback: if the ticker has no baseline (outside dollar-vol
        # universe, or curves not yet refreshed), the gate passes — the
        # absolute-share floor below catches micro-float noise.
        try:
            if _minutes_since_open is None:
                premkt_vol, session_vol = c["today_volume"], 0
            else:
                premkt_vol, session_vol = 0, c["today_volume"]
            _rt_vols = _rt_vol_map.get(ticker)
            if _rt_vols is not None and _rt_vol_authoritative:
                # #490 §6.1 AUTHORITATIVE (RT-5, operator-flipped): the rt cumulatives replace
                # the delayed single-bucket split as the RVOL@T anchor inputs, and the
                # candidate's today-volume-derived figures follow (§6.2 — rel_volume /
                # today's $-vol / open-intensity projection all derive from today_volume).
                premkt_vol, session_vol = _rt_vols["pm_vol"], _rt_vols["session_vol"]
                c["vol_delayed"] = c["today_volume"]
                c["today_volume"] = premkt_vol + session_vol
                c["volume_source"] = "alpaca_sip_minute"
                if c.get("adv") and c["adv"] > 0:
                    c["rel_volume"] = round(c["today_volume"] / c["adv"], 2)
                    rel_volume = c["rel_volume"] or 0
                    if _minutes_since_open and _minutes_since_open >= 15 and c["today_volume"] > 0:
                        c["projected_vol_multiple"] = round(
                            c["rel_volume"] * (_SESSION_MINUTES / _minutes_since_open), 1)
            rvol_info = await compute_rvol_at_time(
                ticker=ticker,
                now_et=now_et,
                today_premkt_vol=premkt_vol,
                today_session_vol=session_vol,
            )
        except Exception as e:
            logger.warning(f"RVOL@T lookup failed for {ticker}: {e}")
            rvol_info = None
        if rvol_info:
            anchor = rvol_info["anchor"]
            threshold = MIN_PM_RVOL if anchor == "pm" else MIN_SESSION_RVOL
            reason_const = (
                FILTER_PM_RVOL_TOO_LOW if anchor == "pm" else FILTER_SESSION_RVOL_TOO_LOW
            )
            audit_event = "ep_filter_pm_rvol" if anchor == "pm" else "ep_filter_session_rvol"
            phase_label = "pre-open" if anchor == "pm" else "session"
            c["pm_rvol"] = rvol_info["rvol_at_time"]  # column reused for both anchors
            c["pm_rvol_baseline_n"] = rvol_info["baseline_n"]
            # #490 §6.1 SHADOW (toggle off): would the RVOL@T gate decide differently on the rt
            # cumulatives? Logged BEFORE the gate-skip below so false-rejected names still
            # accrue evidence. ep_rt_rvol_gate_flip = the NAMED flip list (CHANGE_PROCESS rule 3
            # — reviewed by the operator at RT-2, never self-classified). Once per ticker/day.
            _rt_vols = _rt_vol_map.get(ticker)
            if _rt_vols is not None and not _rt_vol_authoritative:
                try:
                    _rt_rvol_info = await compute_rvol_at_time(
                        ticker=ticker, now_et=now_et,
                        today_premkt_vol=_rt_vols["pm_vol"],
                        today_session_vol=_rt_vols["session_vol"],
                    )
                    if _rt_rvol_info:
                        _gate_fail_delayed = (
                            rvol_info["baseline_n"] >= MIN_BASELINE_N_FOR_GATE
                            and rvol_info["rvol_at_time"] < threshold)
                        _gate_fail_rt = (
                            _rt_rvol_info["baseline_n"] >= MIN_BASELINE_N_FOR_GATE
                            and _rt_rvol_info["rvol_at_time"] < threshold)
                        _would_flip = _gate_fail_delayed != _gate_fail_rt
                        _vol_ev = "ep_rt_rvol_gate_flip" if _would_flip else "ep_rt_volume_shadow"
                        if _audit_dedupe_check(ticker, today, _vol_ev):
                            await log_audit_event(
                                _vol_ev,
                                f"{ticker} {anchor}_rvol delayed={rvol_info['rvol_at_time']:.2f}x "
                                f"rt={_rt_rvol_info['rvol_at_time']:.2f}x"
                                + (" — GATE WOULD FLIP (SHADOW)" if _would_flip else ""),
                                json.dumps({
                                    "ticker": ticker, "alert_date": today.isoformat(),
                                    "anchor": anchor,
                                    "vol_delayed": c["today_volume"],
                                    "vol_rt_pm": _rt_vols["pm_vol"],
                                    "vol_rt_session": _rt_vols["session_vol"],
                                    "rvol_delayed": rvol_info["rvol_at_time"],
                                    "rvol_rt": _rt_rvol_info["rvol_at_time"],
                                    "would_rvol_gate_flip": _would_flip,
                                    "tick_et": now_et.strftime("%H:%M"),
                                }),
                            )
                except Exception as _vse:  # loud-ok: shadow-only — never touches the live gate
                    logger.debug(f"{ticker}: rt volume shadow skipped — {_vse}")
            if (
                rvol_info["baseline_n"] >= MIN_BASELINE_N_FOR_GATE
                and rvol_info["rvol_at_time"] < threshold
            ):
                detail = (
                    f"{anchor}_rvol={rvol_info['rvol_at_time']:.2f}x "
                    f"(today {rvol_info['today_cum_vol']:,} / "
                    f"baseline {rvol_info['baseline_mean']:,.0f} "
                    f"n={rvol_info['baseline_n']}) < {threshold}x"
                )
                reason = f"{reason_const}: {detail}"
                logger.info(f"Skip {ticker}: {detail} (gap={c['gap_pct']:.1f}%)")
                _log_filtered(c, reason)
                await log_audit_event(
                    audit_event,
                    f"{ticker} {phase_label} pace below normal",
                    f"{detail} | gap={c['gap_pct']:.1f}%",
                )
                continue

        # NOTE: pm-shares absolute-floor gate moved post-catalyst (R6 ship,
        # 2026-05-17) so we can carve out high-conviction names. The new
        # location is after catalyst classification — search for "R6 pm-shares".

        # Hard filter: EP cooldown — don't re-alert same ticker within 60 days,
        # UNLESS a fresh earnings catalyst is firing (HIMX 5/07 incident class:
        # ticker on cooldown from prior alert, but fresh earnings + qualifying
        # gap is structurally a new event — earnings are quarterly, the prior
        # alert was a different catalyst). Bypass requires both gap >= 15%
        # AND is_earnings_day to avoid bypassing on routine post-news bumps.
        if ticker in cooldown_tickers:
            cooldown_bypass = False
            if c["gap_pct"] >= 15.0:
                # Fail-soft direction (advisor alignment 2026-05-08): on
                # yfinance error, treat as earnings day → cooldown BYPASSED.
                # Defensive: rather over-allow on data outage than block a
                # real fresh-earnings EP.
                try:
                    earnings_match_cd, _ = await is_earnings_day(ticker, today)
                except Exception:
                    earnings_match_cd = True
                if earnings_match_cd:
                    cooldown_bypass = True
                    await log_audit_event(
                        "ep_cooldown_bypassed_earnings",
                        f"{ticker}: cooldown bypassed — fresh earnings + gap {c['gap_pct']:.1f}%",
                        json.dumps({
                            "ticker": ticker,
                            "alert_date": today.isoformat(),
                            "gap_pct": c["gap_pct"],
                            "cooldown_days": EP_COOLDOWN_DAYS,
                        }),
                    )
            if not cooldown_bypass:
                # #170 SHADOW (telemetry-only, fail-open): if this suppressed
                # candidate looks like a RE-SETUP (hard gap, weeks since the
                # prior alert), record it — it is STILL suppressed live; this
                # only accrues the cohort for the realized-R review. Wrapped so
                # a shadow failure can never affect the suppression below.
                try:
                    _last = cooldown_last_alert.get(ticker)
                    _dsince = (today - _last).days if _last else None
                    if _is_cooldown_resetup(c["gap_pct"], _dsince):
                        await log_audit_event(
                            "cooldown_resetup_admit_shadow",
                            f"{ticker}: SHADOW re-setup — gap {c['gap_pct']:.1f}%, "
                            f"{_dsince}d since prior alert (suppressed by "
                            f"{EP_COOLDOWN_DAYS}d cooldown; #170)",
                            json.dumps({
                                "ticker": ticker, "alert_date": today.isoformat(),
                                "gap_pct": c["gap_pct"],
                                "days_since_prior_alert": _dsince,
                                "prev_close": c.get("prev_close"),
                            }),
                        )
                except Exception as _e:
                    logger.warning(f"#170 shadow emit failed for {ticker}: {_e}")
                reason = f"EP cooldown — alerted within last {EP_COOLDOWN_DAYS} days"
                logger.info(f"Skip {ticker}: {reason}")
                _log_filtered(c, reason)
                continue

        # Skip if already scored in an earlier scan run today
        if ticker in already_today:
            logger.debug(f"Skip {ticker}: already scored today")
            _log_filtered(c, "already scored earlier today")
            continue

        # Hard filter: extension — skip if already up 50%+ before today's gap
        close_5d_ago = extension_map.get(ticker)
        if close_5d_ago and close_5d_ago > 0 and c["prev_close"]:
            extension_pct = (c["prev_close"] - close_5d_ago) / close_5d_ago * 100
            if extension_pct >= MAX_EXTENSION_PCT:
                reason = f"already up {extension_pct:.0f}% in prior 5 days (extended)"
                logger.info(f"Skip {ticker}: {reason}")
                _log_filtered(c, reason)
                continue

        # Hard filter: pre-trade quality (ADV $1M, ATR%, market cap)
        # Single source of truth — same filters used by backtester and live tracker
        passed, skip_reason = await check_filters(ticker, today)
        if not passed:
            reason = f"quality filter: {skip_reason}"
            logger.info(f"Skip {ticker}: pre-trade filter — {skip_reason}")
            _log_filtered(c, reason)
            # OBSERVE LANE (operator-approved 2026-06-11, the MNTS case): a
            # sub-$500M mover that passed every gap/RVOL gate is the tiny-cap
            # fast-runner class — auto-trade stays EXCLUDED (this skip stands),
            # but it becomes VISIBLE: one audit row per ticker per day, read by
            # the morning briefing. Themes/9M/flag lanes already see these.
            if skip_reason and skip_reason.startswith(FILTER_MCAP_TOO_SMALL):
                global _tinycap_seen_date, _tinycap_seen
                if _tinycap_seen_date != today:
                    _tinycap_seen = set()
                    _tinycap_seen_date = today
                if ticker not in _tinycap_seen:
                    _tinycap_seen.add(ticker)
                    await log_audit_event(
                        "ep_tinycap_observed",
                        f"{ticker} gap={c.get('gap_pct') or 0:.1f}% — {skip_reason} (observe-only)",
                        json.dumps({"ticker": ticker, "gap_pct": c.get("gap_pct"),
                                    "rel_volume": c.get("rel_volume"),
                                    "price": c.get("price"),
                                    "skip_reason": skip_reason}, default=str),
                    )
            continue

        # Volume conviction percentile — only valid pre-open (compares cumulative
        # to full-day ADV history). Post-open the partial-day cumulative would
        # falsely rank near 0 against full-day distributions, so return neutral.
        # Post-open conviction is captured via projected_vol_multiple (rel_volume slot).
        if _minutes_since_open is None:
            vol_pct = _volume_percentile(c["today_volume"], vol_history_map.get(ticker, []))
        else:
            vol_pct = 50.0

        # Catalyst cache check — skip FMP/Claude/Perplexity if already evaluated today.
        # A stock oscillating near the 15% threshold gets re-scored every 5 min;
        # the catalyst is the same each time. One evaluation per ticker per day —
        # S6/#405 (2026-07-03): this now holds even when the ticker fails the
        # post-grade filters. Pre-#405 the M&A / routine-catalyst / pm-shares
        # filters ran BEFORE the cache-store, so a filter-skipped ticker (CMCSA
        # hitting the routine-catalyst filter, e.g.) was never cached — full
        # LLM re-grade every 5-min tick (36x/day). Fix: cache the GRADE the
        # moment it's fully computed (Claude + Perplexity + hedge-downgrade),
        # tagged `filters_cleared`; the 3 filters re-run EVERY tick off the
        # cached grade fields (no LLM) because they're time-sensitive — M&A/
        # routine/pm-volume state changes through the morning (BFLY class).
        global _catalyst_cache, _catalyst_cache_date
        global _repoll_shadow_state, _repoll_shadow_date  # #344 re-poll shadow dedup
        if _catalyst_cache_date != today:
            _catalyst_cache.clear()
            _catalyst_cache_date = today
        if _repoll_shadow_date != today:
            _repoll_shadow_state.clear()
            _repoll_shadow_date = today

        _has_direct_source = None  # Wave C shadow (#233): set on the uncached grade tick
        grounded_text = None       # #240 judge shadow: the cached path skips the grounded build
        cached = _catalyst_cache.get(ticker)
        if cached:
            # filters_cleared: True = this grade already passed the M&A/routine/
            # pm-volume filters (pre-#405 cache semantics: only survivors were
            # ever cached, so this is "today's fast path unchanged"). False =
            # graded but still filter-failing; re-run the filters fresh
            # below (no LLM call) instead of trusting a stale pass/fail.
            catalyst_quality = cached.catalyst_quality
            confidence_multiplier = cached.confidence_multiplier
            news_summary = cached.news_summary
            claude_analysis = cached.claude_analysis
            pplx_quality = cached.pplx_quality
            filters_cleared = cached.filters_cleared
            grounded_text = cached.grounded_text  # 7/4: cached-path alerts carry the grade-time corpus (was NULL)
            _has_direct_source = cached.has_direct_source  # #405 Part-1: preserve the display flag on the cached path

            if not filters_cleared:
                skip_reason = await _post_grade_filters(
                    ticker, catalyst_quality, claude_analysis, news_summary,
                    c["gap_pct"], c["today_volume"], c.get("pm_rvol"), today,
                )
                if skip_reason:
                    logger.debug(
                        f"{ticker}: cached grade ({catalyst_quality}) still filtered — {skip_reason}"
                    )
                    _log_filtered(c, skip_reason)
                    continue
                # A time-sensitive filter input cleared since the grade tick
                # (pm-volume grew, M&A stopped matching, gap moved) — flip the
                # flag and fall through EXACTLY as a fresh survivor would.
                filters_cleared = True
                _catalyst_cache[ticker] = cached._replace(filters_cleared=True)
                logger.info(f"{ticker}: cached grade ({catalyst_quality}) now clears filters — proceeding")

            profile = await get_fmp_profile(ticker)  # still need profile for neglect/float scoring
            logger.debug(f"{ticker}: using cached catalyst ({catalyst_quality}, {confidence_multiplier}x)")

            # #344 re-poll SHADOW (cached path): if a NEW primary-subject source appeared
            # after a ROUTINE grade within the ORB window, shadow-re-grade ONCE with the
            # full enriched (web-inclusive) corpus and log what WOULD fire — telemetry only,
            # never touches the live grade or the cache. This is the BFLY mechanism (the
            # 8:12 PR after the 7:00 routine grade). Cheap per-tick check — F5 (2026-07-03):
            # the count precheck uses include_content=False (no article bodies for a len());
            # full content is fetched inside _build_enriched_corpus only when the trigger
            # actually fires, once per ticker per day.
            # PREMARKET-ONLY (advisor 6/19): same guard as the enrichment shadow — keep the
            # re-poll's SEC GET + Sonnet call OFF the ORB entry window. BFLY's PR (8:12 ET)
            # is premarket, so the late-source class is still covered.
            _st = _repoll_shadow_state.get(ticker)
            _in_window = _is_premarket(now_et)
            # NB: ENRICH_SHADOW_ENABLED is the MASTER enrichment switch — despite the
            # "shadow" name it now also gates this LIVE-acting re-poll (#347). A rename
            # is a deploy-coordination change (env lives in prod .env) — deferred.
            if (_st and not _st["logged"] and _in_window and _st["quality"] == "routine"
                    and os.environ.get("ENRICH_SHADOW_ENABLED", "true").lower() == "true"):
                try:
                    import time as _time
                    _t0 = _time.monotonic()
                    _benz_light = await get_alpaca_news(ticker, include_content=False)
                    _cur = sum(
                        1 for n in (_benz_light or [])
                        if is_primary_subject_news(n, ticker, profile.get("companyName", ""))
                    )
                    if should_repoll_shadow(catalyst_quality, _st["count"], _cur,
                                            _st["logged"], _in_window):
                        _st["logged"] = True  # exactly once
                        # Trigger fired (once/ticker/day) — pay for the content-bearing
                        # corpus build here; reuse the grade-time 400d filings / dilution
                        # fetch when available (no second EDGAR hit).
                        _rq, _ran, _ext, _dilution, _prior_agr, _recent_earn = await _build_enriched_corpus(
                            ticker, today, profile,
                            ext_filings=_st.get("ext_filings"),
                            dilution=_st.get("dilution"),
                            dilution_computed="dilution" in _st,
                        )
                        # #347 (operator-approved 2026-07-04): the re-poll acts LIVE —
                        # the BFLY mechanism. A VALID upgrade (no fail-routine sentinel,
                        # quality actually changed) rewrites the grade cache: new quality
                        # + analysis, confidence_multiplier reset to 1.0 (no stale boost,
                        # the #320 lesson), pplx_quality=None (no fresh validation ran),
                        # filters_cleared=False → the NEXT tick re-runs the filters and,
                        # if they pass, proceeds exactly as a fresh survivor (the S6
                        # machinery alerts/enters naturally). Toggle-gated with the same
                        # 'live_enriched_corpus' instant-revert; toggle off = the old
                        # shadow-only telemetry.
                        _repoll_live = await get_runtime_toggle(
                            "live_enriched_corpus", "LIVE_ENRICHED_CORPUS")
                        _valid_change = (
                            _rq != catalyst_quality
                            and _CLASSIFY_FAIL_SENTINEL not in (_ran or "")
                        )
                        if _repoll_live and _valid_change:
                            # CACHE-ONLY apply (7/4 review fix): the CHANGE takes
                            # effect on the NEXT tick (<=5 min), where the
                            # filters_cleared=False path re-runs _post_grade_filters
                            # against the NEW quality before anything can alert or
                            # enter. Applying to THIS tick's local would skip that
                            # re-filter (an upgraded 'mna' would dodge the M&A
                            # filter this tick) — the deferred-tick delay IS the
                            # designed safety semantic.
                            _catalyst_cache[ticker] = _catalyst_cache[ticker]._replace(
                                catalyst_quality=_rq,
                                claude_analysis=_ran,
                                confidence_multiplier=1.0,
                                pplx_quality=None,
                                filters_cleared=False,
                            )
                        await log_audit_event(
                            "catalyst_repoll_regraded_live" if (_repoll_live and _valid_change)
                            else "ep_repoll_shadow",
                            f"{ticker} re-poll routine → {_rq} (+{_cur - _st['count']} src)"
                            + (" [LIVE cache updated]" if (_repoll_live and _valid_change) else ""),
                            json.dumps({
                                "ticker": ticker, "alert_date": today.isoformat(),
                                "cached_quality": _st["quality"], "repoll_quality": _rq,
                                "would_change": _rq != _st["quality"],
                                "applied_live": bool(_repoll_live and _valid_change),
                                "grade_src_count": _st["count"], "current_src_count": _cur,
                                "has_prior_agreement": _prior_agr is not None,
                                "has_dilution": _dilution is not None,
                                "dilution_form": _dilution.get("form") if _dilution else None,
                                "repoll_analysis": (_ran or "")[:300],
                                "shadow_latency_s": round(_time.monotonic() - _t0, 2),
                            }),
                        )
                except Exception as _e:
                    logger.debug(f"{ticker}: repoll shadow skipped — {_e}")
        else:
            # Fetch all external data concurrently
            # #332 (2026-07-18, operator-signed): get_fmp_analyst_ratings dropped from this
            # gather — the analyst-upgrades bonus it fed was removed from _score_ep (dead
            # feed since 2026-03-14; see docs/analysis/332_analyst_bonus_backtest_2026-07-18.md
            # + docs/setups/magna53_ep.md's change log). No other consumer read `ratings`.
            profile, fmp_news, perplexity_answer, sec_filings, alpaca_news = await asyncio.gather(
                get_fmp_profile(ticker),
                get_fmp_news(ticker),
                search_news_perplexity(f"What caused {ticker} stock to gap up? Latest catalyst and news.", recency="week"),
                # 8-K (US) + 6-K (foreign issuers — SE/BABA earnings & deals, #208).
                # 6-K text is pulled from the EX-99 exhibit, not the cover boilerplate.
                get_sec_recent_filings(ticker, forms=("8-K", "6-K")),
                # Benzinga press wires via Alpaca (#210 Wave A) — the press-release-only
                # catalyst class (GRRR 6/2 $2B Supermicro deal) that both SEC (6-K lags
                # the same-day PR for foreign issuers) and Perplexity (confabulated "no
                # large contract") missed. Free, error-wrapped → [], never slows the scan.
                get_alpaca_news(ticker),
            )
            await asyncio.sleep(0.5)  # Single FMP cooldown after concurrent burst

            # Combine news sources — Perplexity synthesized answer + yfinance headlines
            all_news = fmp_news + ([{"title": "Perplexity synthesis", "text": perplexity_answer}]
                                    if perplexity_answer else [])
            news_summary = perplexity_answer[:500] if perplexity_answer else "\n".join(
                [n.get("title", "") for n in fmp_news[:3]]
            )

            # Grounded catalyst summary (#187/#190): authoritative SEC 8-K/6-K body (the catalyst
            # the LLMs were blind to — e.g. RUM 6/4 $270M GPU-cloud deal) + Benzinga press wires
            # (#210 Wave A — GRRR 6/2 class) + the web synthesis, UNTRUNCATED — the grade reasons
            # on this, not raw 200-char headlines. Every fetch is error-wrapped, so this can never
            # slow or break the scan.
            sec_filing = next((f for f in sec_filings if f.get("text")), None)
            # #210 Wave A: primary-subject-filtered Benzinga items (drops the #88/#90 multi-tag
            # bleed + roundups), capped so they don't crowd the SEC body in the 6000-char grade
            # window. Grounded-corpus only — deliberately NOT fed to the M&A keyword scan this
            # wave (avoids regressing is_likely_ma); the grade's own mna verdict still sees it.
            benzinga_items = [
                n for n in (alpaca_news or [])
                if is_primary_subject_news(n, ticker, profile.get("companyName", ""))
            ][:3]
            if sec_filing:
                news_summary = (f"[SEC {sec_filing['form']} filed {sec_filing['filed']}, items {sec_filing['items']}] "
                                + news_summary)[:600]
            grounded_text = build_grounded_text(sec_filing, benzinga_items, perplexity_answer)

            # Perplexity validation runs regardless of corpus branch (S6: both always
            # awaited; the agreement/hedge machinery below applies to whichever grade
            # wins). Grading stays capped at ONE full evaluation per ticker per day.
            pplx_task = asyncio.create_task(_validate_catalyst_perplexity(ticker, news_summary))

            # ── #347 LIVE ENRICHED CORPUS (operator-approved flip 2026-07-04; evidence +
            # CHANGE_PROCESS entry: docs/setups/magna53_ep.md).
            # VALIDATED SHAPE ONLY: premarket grades use the enriched pipeline (the shadow
            # never graded in-window); a 9:30+ first-seen name keeps the legacy corpus.
            # Instant revert: runtime toggle 'live_enriched_corpus' (#400 pattern — a
            # mi_safeguard_state row overrides, <=60s, no redeploy; LIVE_ENRICHED_CORPUS env
            # fallback). APOG guard: _classify fail-defaults to routine — LIVE treats that
            # sentinel as a FAILURE and falls back to the LEGACY grade (audited, never a
            # silent fail-to-routine).
            _use_enriched = (
                _is_premarket(now_et)
                and await get_runtime_toggle("live_enriched_corpus", "LIVE_ENRICHED_CORPUS")
            )
            _enr_sink: dict = {}
            catalyst_quality = None
            if _use_enriched:
                try:
                    _eq, _ea, _enr_ext, _enr_dil, _enr_prior, _enr_earn = await _build_enriched_corpus(
                        ticker, today, profile,
                        sec_filing_fallback=sec_filing,
                        perplexity_answer=perplexity_answer,
                        news_for_classify=all_news,
                        state_sink=_enr_sink,
                    )
                    if _CLASSIFY_FAIL_SENTINEL in (_ea or ""):
                        raise RuntimeError("enriched classify returned the fail-routine sentinel")
                    catalyst_quality, claude_analysis = _eq, _ea
                except Exception as _ee:  # loud-ok: audited + legacy fallback below — never a silent degrade
                    logger.error(
                        f"{ticker}: live enriched grade failed — legacy-corpus fallback: {_ee}")
                    try:
                        await log_audit_event(
                            "live_enriched_grade_failed",
                            f"{ticker}: {type(_ee).__name__}: {str(_ee)[:200]}",
                            json.dumps({"ticker": ticker, "alert_date": today.isoformat()}),
                        )
                    except Exception:  # loud-ok: the logger.error above already carries it
                        pass
            if catalyst_quality is None:
                claude_task = asyncio.create_task(
                    _classify_catalyst_claude(ticker, all_news, profile, grounded_text=grounded_text))
                catalyst_quality, claude_analysis = await claude_task

            # #210 Wave B — record source-class provenance of the grounded corpus that
            # produced this grade (telemetry-only; once per ticker/day on the uncached
            # path, matching the catalyst cache). Feeds the #211 unknown-rate-by-source
            # KPI: graded strong/game_changer with has_direct_source=False = a sourcing
            # gap. Error-wrapped — provenance logging can never break the scan.
            try:
                _prov = corpus_provenance(sec_filing, benzinga_items, perplexity_answer,
                                          grounded_text, fmp_news)
                _has_direct_source = _prov.get("has_direct_source")  # Wave C shadow (#233)
                await log_audit_event(
                    "ep_catalyst_provenance",
                    f"{ticker} {catalyst_quality} direct={_prov['has_direct_source']}",
                    json.dumps({
                        "ticker": ticker,
                        "alert_date": today.isoformat(),
                        "catalyst_quality": catalyst_quality,
                        **_prov,
                    }),
                )
            except Exception as _e:
                logger.debug(f"{ticker}: provenance log skipped — {_e}")

            # #344 enrichment SHADOW (once/ticker/day, uncached path) — web-INCLUSIVE
            # net-correctness telemetry: re-grade with prior material-agreement context
            # added, log current vs enriched. NEVER changes the live grade. Arms the
            # re-poll shadow state (grade-time direct-source count + quality). Fully
            # error-wrapped + flag-killable — can't break or slow-fail the scan.
            # Re-poll trigger signal = primary-subject Benzinga count (the dominant
            # late-source class is a PR arriving after a routine grade; cheap = 1 call/tick
            # to re-check). Same-day SEC-only late catalysts are a known v1 gap to measure.
            _grade_src_count = sum(
                1 for n in (alpaca_news or [])
                if is_primary_subject_news(n, ticker, profile.get("companyName", ""))
            )
            _repoll_shadow_state[ticker] = {
                "count": _grade_src_count, "quality": catalyst_quality, "logged": False,
                # reuse the live-enriched fetches when they ran (no second EDGAR hit)
                "ext_filings": _enr_sink.get("ext_filings"),
                **({"dilution": _enr_sink["dilution"]} if "dilution" in _enr_sink else {}),
            }
            # PREMARKET-ONLY guard (advisor 6/19): the shadow does extra SEC GETs + a Sonnet
            # call SYNCHRONOUSLY on run_ep_scan — the order-submission path. Confining it to
            # premarket (< 9:30 ET) keeps it OFF the 9:30–10:00 ORB entry window (no added
            # latency where orders submit; no EDGAR-budget contention with the live grade
            # fetch during entries). The motivating case (BFLY's PR, 8:12 ET) is premarket, so
            # coverage is preserved; only open-driven gappers are skipped.
            # #347: with the LIVE path already grading enriched, this shadow would compare
            # enriched-vs-enriched (pure noise + double LLM cost) — it runs only in
            # REVERSION mode (toggle off), where it resumes validating exactly as before.
            if (not _use_enriched
                    and _is_premarket(now_et)
                    and os.environ.get("ENRICH_SHADOW_ENABLED", "true").lower() == "true"):
                try:
                    import time as _time
                    _t0 = _time.monotonic()
                    _enr_q, _enr_an, _ext, _dilution, _prior_agr, _recent_earn = await _build_enriched_corpus(
                        ticker, today, profile,
                        sec_filing_fallback=sec_filing,
                        perplexity_answer=perplexity_answer,
                        news_for_classify=all_news,
                        state_sink=_repoll_shadow_state[ticker],
                    )
                    await log_audit_event(
                        "ep_grade_enrich_shadow",
                        f"{ticker} {catalyst_quality} → {_enr_q}",
                        json.dumps({
                            "ticker": ticker, "alert_date": today.isoformat(),
                            "current_quality": catalyst_quality, "enriched_quality": _enr_q,
                            "changed": _enr_q != catalyst_quality,
                            "has_prior_agreement": _prior_agr is not None,
                            "prior_agreement_filed": _prior_agr.get("filed") if _prior_agr else None,
                            "has_dilution": _dilution is not None,
                            "dilution_form": _dilution.get("form") if _dilution else None,
                            "dilution_filed": _dilution.get("filed") if _dilution else None,
                            "enriched_analysis": (_enr_an or "")[:300],
                            "shadow_latency_s": round(_time.monotonic() - _t0, 2),
                        }),
                    )
                except Exception as _e:
                    logger.debug(f"{ticker}: enrich shadow skipped — {_e}")

            pplx_quality = await pplx_task

            # Agreement logic
            confidence_multiplier = 1.0
            if pplx_quality and pplx_quality == catalyst_quality:
                confidence_multiplier = 1.2
                logger.info(f"{ticker}: Claude+Perplexity agree on {catalyst_quality} → 1.2x confidence")
            elif pplx_quality and pplx_quality != catalyst_quality:
                logger.info(f"{ticker}: Claude={catalyst_quality}, Perplexity={pplx_quality} → disagreement, no boost")

            # Hedge-phrase downgrade: when Perplexity self-acknowledges null search
            # results, both classifiers are grading a hollow news_summary. RDDT 5/1
            # case: Q1 earnings beat 4/30 AH was the real catalyst, but Perplexity
            # returned hedged synthesis → Claude classified an Evercore initiation
            # blurb as "strong". Downgrade by one notch and cancel agreement boost.
            _PPLX_HEDGE_PHRASES = (
                "no specific information",
                "couldn't find",
                "could not find",
                "search results don't contain",
                "search results do not contain",
                "no recent news",
                "unable to find",
                "i don't have",
                "i do not have",
            )
            pplx_low = (perplexity_answer or "").lower()
            hedged = any(p in pplx_low for p in _PPLX_HEDGE_PHRASES)
            if hedged and catalyst_quality in ("game_changer", "strong"):
                _DOWNGRADE = {"game_changer": "strong", "strong": "routine"}
                downgraded = _DOWNGRADE[catalyst_quality]
                logger.info(
                    f"{ticker}: Perplexity hedge detected — downgrading "
                    f"{catalyst_quality} → {downgraded}"
                )
                await log_audit_event(
                    "catalyst_pplx_hedge_downgrade",
                    f"{ticker} {catalyst_quality} → {downgraded}",
                    json.dumps({
                        "ticker": ticker,
                        "alert_date": today.isoformat(),
                        "from_quality": catalyst_quality,
                        "to_quality": downgraded,
                        "pplx_excerpt": (perplexity_answer or "")[:200],
                    }),
                )
                catalyst_quality = downgraded
                confidence_multiplier = 1.0  # cancel any agreement boost

            # Post-grade filters — S6/#405 (2026-07-03): M&A / routine-catalyst /
            # pm-shares-floor, extracted to _post_grade_filters so the IDENTICAL
            # check can re-run on a later tick against a cached-but-not-yet-
            # cleared grade with no LLM call. Order + reason strings unchanged;
            # they now read the SETTLED (post-downgrade) catalyst_quality since
            # grading (Claude + Perplexity + hedge-downgrade) completes before
            # filtering — pre-#405 the filters ran ahead of the Perplexity
            # await/downgrade block and saw the pre-downgrade value. This is a
            # narrow, MORE-conservative-only corollary (a ticker that hedge-
            # downgrades to routine+low-gap now correctly gets caught by the
            # routine filter instead of slipping through) — see commit message.
            skip_reason = await _post_grade_filters(
                ticker, catalyst_quality, claude_analysis, news_summary,
                c["gap_pct"], c["today_volume"], c.get("pm_rvol"), today,
            )

            # Store in cache AT GRADE COMPLETION regardless of filter outcome
            # (S6/#405) — filters_cleared True/False per today's check. This is
            # what makes the ticker reusable (no re-grade) on every later tick
            # this trading day, whether it cleared or not.
            _catalyst_cache[ticker] = CachedGrade(
                catalyst_quality, confidence_multiplier, news_summary, claude_analysis,
                pplx_quality, skip_reason is None,
                grounded_text=grounded_text,
                has_direct_source=_has_direct_source,  # #405 Part-1: cache the display flag
            )

            if skip_reason:
                _log_filtered(c, skip_reason)
                continue

        # Earnings-day pre-score catalyst boost (DDOG/AAON 5/07 incident class).
        # Existing earnings-day override (below) only fires for MODERATE→HIGH
        # promotion (score ≥ 50). DDOG/AAON scored 30 because catalyst='routine'
        # mathematically caps score below 50 regardless of gap/volume. The
        # classifier (Claude + Perplexity) returned 'routine' because the news
        # scrape was hedged/hollow. is_earnings_day is structurally independent
        # evidence — when yfinance confirms today is the earnings date, the
        # catalyst IS the earnings event regardless of LLM grade. Upgrade
        # routine→strong (or no-op if already strong/game_changer) so the
        # score can clear the 50 threshold.
        # Fail-soft direction (advisor alignment 2026-05-08): on yfinance
        # error, treat as earnings day → catalyst boost FIRES. Defensive:
        # rather over-boost on data outage than miss a real earnings EP.
        try:
            earnings_today_match, earnings_src = await is_earnings_day(ticker, today)
        except Exception:
            earnings_today_match, earnings_src = True, "unavailable"

        # Revenue-stage check (2026-05-20): pre-revenue companies (clinical-
        # stage biotech, SPACs, blank-check) shouldn't be earnings-boosted.
        # Their "earnings" event is really management commentary on pipeline
        # / trials, not a Q-rev catalyst. Triggering the boost makes the
        # rubric gate engage and produces misleading "Q-rev YoY un-extractable"
        # downgrades. Fail-soft to revenue-stage on data outage.
        # IMVT 2026-05-20 was the trigger case.
        if earnings_today_match:
            try:
                revenue_stage = await is_revenue_stage(ticker)
            except Exception:
                revenue_stage = True
        else:
            revenue_stage = True  # not used when not earnings day

        # Boost gate: same yfinance-or-text fallback as the extraction gate
        # (#131). If yfinance earnings_dates miss and Claude prose clearly
        # describes earnings, treat as earnings day so a real earnings EP
        # isn't silently de-classified as routine.
        _boost_earnings_signal = (
            earnings_today_match
            or _claude_text_signals_earnings(claude_analysis)
        )
        if _boost_earnings_signal and revenue_stage and catalyst_quality in ("routine", None):
            original_quality = catalyst_quality
            catalyst_quality = "strong"
            # Per-trading-day-per-ticker dedup. Without this, 3 container
            # restarts today wiped _catalyst_cache 3x; each restart's first
            # scan tick re-fired the boost for JOYY/MOD/ESLT = 57 events
            # for what should be 3. Same shape as #89 M&A filter dedup.
            if await _should_log_catalyst_earnings_event_today(
                "catalyst_earnings_boost", ticker
            ):
                await log_audit_event(
                    "catalyst_earnings_boost",
                    f"{ticker}: {original_quality} → strong (earnings_day, source={earnings_src})",
                    json.dumps({
                        "ticker": ticker,
                        "alert_date": today.isoformat(),
                        "from_quality": original_quality,
                        "to_quality": "strong",
                        "earnings_source": earnings_src,
                        "gap_pct": c["gap_pct"],
                    }),
                )
            # Also update cache so subsequent scan ticks see the boosted grade.
            # filters_cleared stays True — only reachable post-filter (S6/#405).
            _catalyst_cache[ticker] = _catalyst_cache[ticker]._replace(
                catalyst_quality=catalyst_quality,
            )
        elif earnings_today_match and not revenue_stage and catalyst_quality in ("routine", None):
            # Pre-revenue company on earnings day — log the skip so operator
            # can see WHY the boost didn't fire. Catalyst grade stays at
            # Claude's original verdict (likely routine, no HIGH alert).
            await log_audit_event(
                "catalyst_earnings_boost_skipped",
                f"{ticker}: pre-revenue company on earnings day, boost skipped "
                f"(catalyst stays {catalyst_quality}, source={earnings_src})",
                json.dumps({
                    "ticker": ticker,
                    "alert_date": today.isoformat(),
                    "catalyst_quality": catalyst_quality,
                    "earnings_source": earnings_src,
                    "reason": "pre_revenue_company",
                    "gap_pct": c["gap_pct"],
                }),
            )

        # ── Revenue-growth gate (2026-05-19, AGYS hotfix) ──────────────
        # The LLM catalyst classifier returns 'strong' based on overall
        # earnings narrative (beat %, qualitative factors like "record Q4",
        # "SaaS growth", "AI innovation"). AGYS 2026-05-19 fired HIGH on
        # 24% earnings beat + record-revenue prose despite ~1% revenue
        # growth. The Pradeep catalyst hierarchy + weekend Phase-5 rubric
        # work established: revenue growth IS the substance of earnings
        # catalysts; narrative-only "strong" without revenue substance is
        # a non-EP wearing EP clothing.
        #
        # Gate logic: for earnings catalysts (LLM 'strong' or 'game_changer'
        # on is_earnings_day=True), look up mi_fundamental_flags.sales_yoy_latest.
        # If < 5% (or missing — fail-closed; can't verify substance), downgrade
        # to 'routine'. The 50-score threshold will then filter naturally.
        #
        # 5% threshold is conservative ("company actually growing"). Refine
        # via Phase 5 calibration with operator labels. Env flag for fast
        # rollback if a real EP gets blocked.
        from agents.market_intelligence.constants import (
            EARNINGS_REVENUE_GATE_ENABLED, EARNINGS_REVENUE_GATE_MIN_YOY,
        )
        # Belt-and-suspenders: also skip the revenue gate entirely for
        # pre-revenue companies (clinical-stage biotechs, SPACs). Even if
        # Claude graded the catalyst strong on its own merit (e.g. FDA
        # news, trial readout, M&A), the Q-rev YoY check is structurally
        # inapplicable. Without this, the rubric would always downgrade
        # pre-revenue strong-catalyst names with the misleading "Q-rev YoY
        # un-extractable" reason. 2026-05-20 IMVT trigger case.
        # Extract on earnings-day OR when Claude's analysis textually signals
        # earnings (CRSR 2026-05-27 case: yfinance earnings_dates missed the
        # date, but Claude prose had revenue + Q-period markers). The earlier
        # `is_earnings_day` gate is yfinance-only; ingest lag there silently
        # skipped extraction → no rubric on real earnings EPs.
        _claude_signals_earn = _claude_text_signals_earnings(claude_analysis)
        if (EARNINGS_REVENUE_GATE_ENABLED
                and (earnings_today_match or _claude_signals_earn)
                and revenue_stage
                and catalyst_quality in ("strong", "game_changer")):
            # Multi-source FRESH extraction (2026-05-19, AGYS hotfix).
            # yfinance quarterly_financials lags announcements by 24-72h →
            # stale data on catalyst-day. Read structured numbers FROM the
            # actual press-release news corpus (Polygon + FMP + Perplexity +
            # internal Claude analysis) via Sonnet extraction → cache to
            # mi_ep_catalyst_metrics for subsequent scan ticks + /why.
            from agents.market_intelligence.catalyst_metrics_extractor import (
                extract_earnings_metrics, lookup_cached_metrics,
                persist_catalyst_metrics, get_q_revenue_yoy_pct,
            )

            _cached = await lookup_cached_metrics(ticker, today)
            if _cached:
                _extracted = _cached
                logger.info(f"{ticker}: catalyst metrics cached (extraction_quality={_extracted.get('extraction_quality')})")
            else:
                try:
                    _extracted = await extract_earnings_metrics(
                        ticker, today,
                        claude_analysis=claude_analysis,
                        perplexity_text=news_summary,
                        fmp_news=fmp_news if 'fmp_news' in dir() else None,
                    )
                    await persist_catalyst_metrics(ticker, today, _extracted)
                    logger.info(
                        f"{ticker}: catalyst metrics extracted "
                        f"(quality={_extracted.get('extraction_quality')}, "
                        f"q_rev_yoy={get_q_revenue_yoy_pct(_extracted)})"
                    )
                except Exception as e:
                    # Silent extraction failures leave the rubric gate unused
                    # (falls through to Q-rev safety net). Surface as audit
                    # event + Telegram so operator knows the gate wasn't
                    # exercised. (Item #15, 2026-05-19.)
                    logger.warning(f"{ticker}: catalyst metrics extraction failed: {e}")
                    _extracted = {"extraction_quality": "low", "extraction_error": str(e)[:200]}
                    # NOTE: do NOT do `from agents.market_intelligence.db import log_audit_event`
                    # here — log_audit_event is imported at module level (line 53) and a local
                    # import INSIDE this 1000+ line function would make `log_audit_event` a local
                    # variable, causing UnboundLocalError at ALL prior references in run_ep_scan.
                    # This is the 2026-05-20 bug class. Use the module-level import directly.
                    try:
                        await log_audit_event(
                            "extraction_error",
                            f"{ticker}: catalyst extraction failed — {str(e)[:200]} "
                            f"(rubric gate skipped; Q-rev safety-net engaged)",
                        )
                    except Exception:
                        pass
                    # Only Telegram on HIGH-tier catalysts — extraction failures
                    # on MODERATE are noise (rubric doesn't gate MODERATE anyway).
                    if catalyst_quality in ("strong", "game_changer"):
                        try:
                            from agents.market_intelligence.briefing import send_telegram_message
                            await send_telegram_message(
                                f"⚠️ *{ticker}*: catalyst extraction failed — "
                                f"rubric gate not exercised, Q-rev safety-net engaged. "
                                f"_See `/why {ticker}` for context; `mi_audit_log` for full error._"
                            )
                        except Exception:
                            pass

            _q_rev_yoy = get_q_revenue_yoy_pct(_extracted)
            _quality = _extracted.get("extraction_quality", "low")
            _reasoning = _extracted.get("reasoning_brief", "")

            # 6-axis rubric gate (Phase 5 ship 2026-05-19). Runs on fresh
            # multi-source extraction; composite_scaled < threshold →
            # downgrade. Falls through to Q-rev safety net if rubric
            # can't score.
            _downgrade_reason = None
            _rubric_result = None
            # Set when extraction FAILED and we deliberately did not downgrade
            # (operator 2026-08-07) — carried so the audit row can say so.
            _extraction_failed_no_downgrade = None
            from agents.market_intelligence.constants import (
                CATALYST_RUBRIC_GATE_ENABLED, CATALYST_RUBRIC_MIN_COMPOSITE,
            )
            if CATALYST_RUBRIC_GATE_ENABLED:
                try:
                    from agents.market_intelligence.catalyst_rubric_runtime import (
                        score_ep_with_rubric,
                    )
                    _rubric_result = score_ep_with_rubric(ticker, _extracted, today)
                    if _rubric_result:
                        _composite = _rubric_result.get("composite_scaled")
                        _label = _rubric_result.get("label")
                        _caps = _rubric_result.get("caps_applied", [])
                        logger.info(
                            f"{ticker}: rubric composite={_composite}/39 "
                            f"label={_label} caps={_caps}"
                        )
                        if _composite is not None and _composite < CATALYST_RUBRIC_MIN_COMPOSITE:
                            _downgrade_reason = (
                                f"rubric_composite_{_composite:.1f}_below_"
                                f"{CATALYST_RUBRIC_MIN_COMPOSITE:.0f}_"
                                f"label_{_label}"
                            )
                except Exception as e:
                    logger.warning(f"{ticker}: rubric scoring failed: {e}")
                    _rubric_result = None

            # Safety-net Q-rev threshold gate (fires when rubric couldn't
            # score, e.g. extraction lacks q_revenue_yoy_pct entirely).
            #
            # 2026-05-20 #51: disambiguate WHY q_rev_yoy is missing so the
            # operator-facing message names the actual cause. Three causes:
            #
            #   (a) extraction_error — the API call itself raised (Sonnet
            #       error, timeout). The rubric never got a chance.
            #   (b) sparse news corpus — extraction ran but the news scrape
            #       was thin (no press release indexed yet, e.g. pre-market
            #       on earnings day before announcement). Quality stays low.
            #   (c) non-earnings catalyst — extraction ran, news corpus had
            #       content, but no Q-rev numbers because the catalyst is
            #       FDA / M&A / partnership / pipeline rather than earnings.
            #       Quality medium+ usually (other fields populated).
            #
            # Previous reason 'q_rev_yoy_unextractable_quality_X' conflated
            # all three, leading to operator confusion (IMVT/ROIV reports).
            if _downgrade_reason is None and _rubric_result is None:
                if _q_rev_yoy is None:
                    extraction_error = _extracted.get("extraction_error")
                    _qr_block_check = _extracted.get("q_revenue_usd") or {}
                    has_q_rev_value = isinstance(_qr_block_check.get("value"), (int, float))
                    if extraction_error:
                        # ⚖ OPERATOR 2026-08-07, mid-incident: *"we shouldn't downgrade
                        # stocks due to call failure."* A failed CALL is not evidence of a
                        # weak quarter — it is the ABSENCE of evidence, and case (a) above
                        # says so in its own words ("the rubric never got a chance").
                        # Downgrading here conflated "we don't know" with "it's weak".
                        #
                        # BLAST RADIUS, measured on the morning this was found: 14 of 14
                        # earnings names knocked to `routine` on 08-07, which is what caps
                        # the score under 50 — including a whole software cohort gapping
                        # together (DOCS +178%, PUBM +36%, TEAM +33%, plus NET/TWLO/FROG)
                        # against weeks of rising software RS. Zero HIGH alerts that
                        # morning, and none of it was a judgement about the setups.
                        #
                        # Same shape as the SNOW 2026-05-28 carve-out below, which is
                        # operator-signed for exactly this class ("lost-alpha, not
                        # cosmetic") — a missing YoY there, a dead API call here. Leave the
                        # catalyst as graded and let the downstream judge rule on it; the
                        # audit row still records that extraction failed, so this is
                        # visible rather than silent.
                        _downgrade_reason = None
                        _extraction_failed_no_downgrade = extraction_error
                    elif _quality == "low" and not has_q_rev_value:
                        _downgrade_reason = "news_corpus_sparse_no_q_rev"
                    elif has_q_rev_value:
                        # Got a revenue value but no YoY — KLAR-class (IPO,
                        # no prior-year comparable). Rubric returns None
                        # because Axis 1 needs YoY.
                        _downgrade_reason = "q_rev_yoy_missing_no_prior_year_comparable"
                    else:
                        # Extraction succeeded with non-revenue content —
                        # likely non-earnings catalyst (FDA/M&A/partnership)
                        # that yfinance happens to flag as earnings_day.
                        _downgrade_reason = "non_earnings_catalyst_no_q_rev_in_news"
                elif _q_rev_yoy < EARNINGS_REVENUE_GATE_MIN_YOY:
                    _downgrade_reason = (
                        f"q_rev_yoy_{_q_rev_yoy:.1f}pct_below_"
                        f"{EARNINGS_REVENUE_GATE_MIN_YOY:.0f}pct"
                    )

            # Carve-out (2026-05-28, data-gated review
            # `rubric_safety_net_yoy_required` ripened at N=10): when the
            # downgrade reason is purely missing-YoY but OTHER positive
            # signals corroborate the catalyst strength (beat vs estimate
            # + raised/initiated/reaffirmed guidance with high/medium
            # confidence), the LLM's original game_changer/strong grade
            # is more trustworthy than the missing-data safety net.
            #
            # Cohort evidence: N=10 cases since 2026-05-14. Carve-out subset
            # = 6 (SNOW/BBWI/JOYY/RL/TATT/KLAR); mature N=3 (RL/TATT/KLAR)
            # all positive fwd_5d (+4.59 / +5.87 / +1.08%), mean +3.85%.
            # The 4 cases still downgraded (QFIN, ESLT, LION big-beat-no-
            # guidance, ROIV miss) showed flat-to-negative forward returns,
            # confirming the safety net's intended catch zone.
            #
            # Triggered by SNOW 2026-05-28 false negative: +37.5% gap on
            # a guidance-raised beat got downgraded to routine purely
            # because Q1 YoY% wasn't extracted, suppressing the HIGH-tier
            # alert + ORB pipeline. Operator-identified blast radius =
            # lost-alpha, not cosmetic.
            if (
                _downgrade_reason == "q_rev_yoy_missing_no_prior_year_comparable"
                and _should_apply_yoy_carveout(_extracted)
            ):
                qr = _extracted.get("q_revenue_usd") or {}
                gc = _extracted.get("guidance_change") or {}
                _downgrade_reason = None
                # Per-ticker-per-day dedup on the AUDIT EMIT only — the carve-out
                # DECISION above (_downgrade_reason = None) is idempotent and MUST
                # run every scan. Without this guard the event re-fires on every
                # 5-min scan for an earnings name (CLF logged 13× 2026-07-23 →
                # 9m_alerts_per_day L2 false-alarm); mirrors the weak-downgrade
                # guard below (line ~3035). DB-backed → restart-immune.
                if await _should_log_catalyst_earnings_event_today(
                    "catalyst_downgrade_carveout_applied", ticker
                ):
                    try:
                        await log_audit_event(
                            "catalyst_downgrade_carveout_applied",
                            f"{ticker}: kept {catalyst_quality} "
                            f"(beat {qr.get('beat_vs_est_pct'):.1f}% + "
                            f"{gc.get('direction')}:{gc.get('confidence')})",
                            json.dumps({
                                "ticker": ticker,
                                "alert_date": today.isoformat(),
                                "kept_quality": catalyst_quality,
                                "beat_vs_est_pct": qr.get("beat_vs_est_pct"),
                                "guidance_direction": gc.get("direction"),
                                "guidance_confidence": gc.get("confidence"),
                            }),
                        )
                    except Exception:
                        pass

            # #321 LIVE rescue (operator 6/28: it's a BUG — the gate fires "no prior-year comparable"
            # when the comparable IS available, just not in the news corpus). Recover the YoY from the
            # prior-year SAME quarter and let it DRIVE the gate: recovered >= floor -> not weak (clear the
            # downgrade); < floor -> legitimately weak (keep, with the real number); None -> stay
            # conservative. Latency-bounded (off-corpus yfinance fetch, 4s cap, fail-open) + a revert
            # toggle — #400a: DB-instant via get_runtime_toggle('live_yoy_recovery', ...) with the
            # LIVE_YOY_RECOVERY env as fallback; flipping the DB row to 'off' reverts to the
            # conservative pre-fix downgrade in ≤60s, no redeploy. Runs only on the missing-YoY reason.
            # Latency guard (advisor 6/28): the prior-year leg fetch must NOT run inside the 9:30-9:45
            # ORB-cutoff window — a few × 4s serially could push the scan past 9:45 -> WINDOW_OUT_OF_ORB on
            # the GOOD names that needed to submit. Earnings names classify pre-market, so the fetch runs
            # pre-9:30 and the rescued grade caches in _catalyst_cache for the in-window scans. A name
            # first-seen in-window stays conservative (the safe old behavior) rather than risking the cutoff.
            _in_orb_cutoff = now_et.hour == 9 and 30 <= now_et.minute <= 45
            if (_downgrade_reason == "q_rev_yoy_missing_no_prior_year_comparable"
                    and await get_runtime_toggle("live_yoy_recovery", "LIVE_YOY_RECOVERY")
                    and not _in_orb_cutoff):
                _qr2 = _extracted.get("q_revenue_usd") or {}
                try:
                    from agents.market_intelligence.fundamentals import compute_yoy_from_prior_year
                    _rec = await asyncio.wait_for(
                        compute_yoy_from_prior_year(
                            ticker, _extracted.get("fiscal_period"), _qr2.get("value")),
                        timeout=4,
                    )
                except Exception:  # loud-ok: fail-open — timeout/error -> None -> stays the conservative downgrade (safe default)
                    _rec = None
                if _rec is not None:
                    _ryoy = _rec["yoy_pct"]
                    if _ryoy >= EARNINGS_REVENUE_GATE_MIN_YOY:
                        _downgrade_reason = None   # real growth recovered — NOT a weak/missing-comparable name
                        await log_audit_event(
                            "catalyst_yoy_recovered_live",
                            f"{ticker}: kept {catalyst_quality} — recovered prior-yr YoY "
                            f"{_ryoy:+.1f}% (>= {EARNINGS_REVENUE_GATE_MIN_YOY:.0f})",
                            json.dumps({"ticker": ticker, "alert_date": today.isoformat(),
                                        "recovered_yoy_pct": _ryoy,
                                        "prior_period": _rec.get("prior_period"),
                                        "kept_quality": catalyst_quality}))
                    else:
                        _downgrade_reason = (
                            f"q_rev_yoy_{_ryoy:.1f}pct_below_"
                            f"{EARNINGS_REVENUE_GATE_MIN_YOY:.0f}pct_recovered")

            # Extraction died and we deliberately kept the grade (operator 2026-08-07).
            # Emitted BEFORE the downgrade block so it is recorded even though nothing
            # is downgraded — a silent no-downgrade would be indistinguishable from a
            # healthy extraction, which is how the 08-06/08-07 outage went unnoticed for
            # a full session. Per-ticker-per-day dedup, same idiom as the carve-out above.
            if _extraction_failed_no_downgrade:
                try:
                    if await _should_log_catalyst_earnings_event_today(
                        ticker, "catalyst_extraction_failed_grade_kept"
                    ):
                        await log_audit_event(
                            "catalyst_extraction_failed_grade_kept",
                            f"{ticker}: extraction FAILED ({_extraction_failed_no_downgrade[:60]}) "
                            f"— catalyst KEPT at {catalyst_quality}, not downgraded to routine",
                            json.dumps({
                                "ticker": ticker,
                                "extraction_error": _extraction_failed_no_downgrade,
                                "catalyst_quality_kept": catalyst_quality,
                            }),
                        )
                except Exception as _e:
                    logger.warning(f"{ticker}: could not log extraction-failed-grade-kept: {_e}")

            if _downgrade_reason:
                _original_quality = catalyst_quality
                catalyst_quality = "routine"
                confidence_multiplier = 1.0  # #320: reset the stale agreement boost on downgrade (mirrors the pplx-hedge reset ~line 2016)
                _qr_block = _extracted.get("q_revenue_usd") or {}
                _gf_block = _extracted.get("guidance_fy_revenue_usd") or {}
                # Rubric details if available (Phase 5 ship)
                _rubric_summary = None
                if _rubric_result:
                    _rubric_summary = {
                        "composite_scaled": _rubric_result.get("composite_scaled"),
                        "label": _rubric_result.get("label"),
                        "caps_applied": _rubric_result.get("caps_applied"),
                        "axes_scored": {
                            f"a{i}": _rubric_result.get(f"a{i}_score")
                            for i in range(1, 7)
                        },
                    }
                from agents.market_intelligence.audit_events import (
                    CATALYST_EARNINGS_REVENUE_WEAK_DOWNGRADE,
                )
                if await _should_log_catalyst_earnings_event_today(
                    CATALYST_EARNINGS_REVENUE_WEAK_DOWNGRADE, ticker
                ):
                    await log_audit_event(
                        CATALYST_EARNINGS_REVENUE_WEAK_DOWNGRADE,
                        f"{ticker}: {_original_quality} → routine "
                        f"(earnings catalyst, {_downgrade_reason})",
                        json.dumps({
                            "ticker": ticker,
                            "alert_date": today.isoformat(),
                            "from_quality": _original_quality,
                            "to_quality": "routine",
                            "reason": _downgrade_reason,
                            "q_revenue_yoy_pct": _q_rev_yoy,
                            "extraction_quality": _quality,
                            "extraction_reasoning": _reasoning,
                            "extraction_sources": _qr_block.get("sources"),
                            "extraction_confidence": _qr_block.get("confidence"),
                            "guidance_midpoint_yoy_pct": _gf_block.get("midpoint_yoy_pct"),
                            "rubric": _rubric_summary,
                            "earnings_source": earnings_src,
                            "gap_pct": c["gap_pct"],
                        }),
                    )
                _catalyst_cache[ticker] = _catalyst_cache[ticker]._replace(
                    catalyst_quality=catalyst_quality,
                    confidence_multiplier=confidence_multiplier,
                )
                # Per-ticker Telegram suppressed (was 5-10 noise alerts per
                # morning). Audit event above is the source of truth — the
                # 10:10 ET _catalyst_downgrade_digest_job reads mi_audit_log
                # directly so the digest survives container restart (#143
                # post-mortem 2026-05-28).

        # Prose-mismatch downgrade (#72, 2026-05-11). Strong-graded alerts
        # whose prose explicitly says "no catalyst / no fresh news" are
        # late-stage retail-driven gappers (MRAM 5/11 class). The classifier
        # over-weights volume+gap features against hedged news. Downgrade to
        # 'routine' so the score-50 threshold filters them out. Must run
        # AFTER the earnings boost so legitimate earnings-day strongs are
        # preserved (MNDY 5/11 same prose, but earnings = real catalyst).
        if catalyst_quality == "strong" and not earnings_today_match:
            matched_marker: Optional[str] = None
            matched_source: Optional[str] = None
            for src_name, text in (
                ("claude_analysis", claude_analysis or ""),
                ("news_summary", news_summary or ""),
            ):
                if not text:
                    continue
                low = text.lower()
                for marker in _PROSE_NEGATIVE_MARKERS:
                    if marker in low:
                        matched_marker = marker
                        matched_source = src_name
                        break
                if matched_marker:
                    break
            if matched_marker:
                original_quality = catalyst_quality
                catalyst_quality = "routine"
                confidence_multiplier = 1.0  # #320: reset the stale agreement boost on downgrade (mirrors the pplx-hedge reset ~line 2016)
                await log_audit_event(
                    "catalyst_prose_mismatch_downgrade",
                    f"{ticker}: strong → routine "
                    f"(prose marker '{matched_marker}' in {matched_source})",
                    json.dumps({
                        "ticker": ticker,
                        "alert_date": today.isoformat(),
                        "from_quality": original_quality,
                        "to_quality": "routine",
                        "matched_marker": matched_marker,
                        "matched_source": matched_source,
                        "gap_pct": c["gap_pct"],
                    }),
                )
                _catalyst_cache[ticker] = _catalyst_cache[ticker]._replace(
                    catalyst_quality=catalyst_quality,
                    confidence_multiplier=confidence_multiplier,
                )
                # Visibility surface (advisor 2026-05-11): user needs to see
                # the new behavior in action, not discover it by missing
                # alerts. Telegram once per (ticker, date) — already gated
                # by _catalyst_cache (one decision per ticker per day).
                try:
                    from agents.market_intelligence.briefing import send_telegram_message
                    from agents.market_intelligence.constants import mode_prefix
                    if not _magna53_mode_fetched:
                        # Shared fail-open resolver (review 7/17 dedup): loud
                        # via strategy_mode_resolve_error on failure, never
                        # raises; mode_prefix(None) falls back to the legacy
                        # global default.
                        from agents.market_intelligence.constants import (
                            resolve_strategy_mode_nonfatal,
                        )
                        _magna53_account_mode = await resolve_strategy_mode_nonfatal("magna53")
                        _magna53_mode_fetched = True
                    await send_telegram_message(
                        f"{mode_prefix(_magna53_account_mode)}📰 *Catalyst downgrade:* `{ticker}` "
                        f"gap +{c['gap_pct']:.1f}%\n"
                        f"Grade strong → routine — prose marker "
                        f"\"{matched_marker}\" in {matched_source}\n"
                        f"_Late-stage / no-fresh-news filter (#72). "
                        f"This alert will not promote to HIGH._"
                    )
                except Exception as e:
                    logger.warning(
                        f"catalyst_downgrade_telegram_failed: {ticker}: {e}"
                    )

        # Compute prior 3-month change %
        prior_3m_change = None
        close_3m_ago = prior_3m_map.get(ticker)
        if close_3m_ago and close_3m_ago > 0 and c["prev_close"]:
            prior_3m_change = (c["prev_close"] - close_3m_ago) / close_3m_ago * 100

        # Score
        ep_score, breakdown = _score_ep(
            gap_pct=c["gap_pct"],
            rel_volume=rel_volume,
            catalyst_quality=catalyst_quality,
            profile=profile,
            regime_multiplier=regime_multiplier * confidence_multiplier,
            projected_vol_multiple=c.get("projected_vol_multiple"),
            vol_percentile=vol_pct,
            prior_3m_change=prior_3m_change,
            in_active_theme=(ticker in _in_active_theme_set),
        )

        if ep_score < 50:
            reason = f"score {ep_score:.0f} < 50 (catalyst={catalyst_quality})"
            logger.info(f"Skip {ticker}: {reason} (gap={c['gap_pct']:.1f}% breakdown={breakdown})")
            scan_log.append(_scan_row(
                c, reason=reason, ep_score=ep_score, tier=None,
                catalyst_quality=catalyst_quality,
            ))
            continue

        tier = "HIGH" if ep_score >= ep_threshold else "MODERATE"
        earnings_override_fired = False  # set True if the earnings-day MOD→HIGH fires below

        # Earnings-day HIGH override. The catalyst classifier rates textual
        # news_summary; when news ingest lags the announcement (DOCN 5/05: Q1
        # beat pre-market, no headlines yet → catalyst='routine'), a qualifying
        # gap silently scores below threshold. Per Pradeep Bonde, a meaningful
        # gap on an earnings day is a qualified EP regardless of beat/miss
        # prose grade — downside bounded by ORB stop-limit + 10:00 cancel + ATR.
        if tier == "MODERATE" and c["gap_pct"] >= 10.0:
            # Fail-soft direction (advisor alignment 2026-05-08): on yfinance
            # error, treat as earnings day → MODERATE→HIGH override fires.
            # Defensive: rather over-promote than miss a real earnings EP.
            try:
                earnings_match, earnings_source = await is_earnings_day(ticker, today)
            except Exception:
                earnings_match, earnings_source = True, "unavailable"

            if earnings_match and await _revenue_weak_downgrade_logged_today(ticker):
                # Explicit data-quality downgrade present — respect it.
                # Override exists for the news-ingest-lag class (catalyst
                # stayed routine because no headlines); a same-day
                # revenue_weak downgrade is the opposite signal.
                logger.info(
                    f"{ticker}: earnings-day override SKIPPED — "
                    f"catalyst already downgraded for data-quality today"
                )
                if _audit_dedupe_check(
                    ticker, today, "earnings_override_skipped_post_downgrade",
                ):
                    await log_audit_event(
                        "earnings_override_skipped_post_downgrade",
                        f"{ticker}: MODERATE stays MODERATE — downgrade respected",
                        json.dumps({
                            "ticker": ticker,
                            "alert_date": today.isoformat(),
                            "gap_pct": round(c["gap_pct"], 2),
                            "ep_score": round(ep_score, 1),
                            "catalyst_quality": catalyst_quality,
                            "source": earnings_source,
                        }),
                    )
            elif earnings_match:
                logger.info(
                    f"{ticker}: earnings-day override MODERATE→HIGH "
                    f"(gap={c['gap_pct']:.1f}% source={earnings_source})"
                )
                await log_audit_event(
                    "earnings_override_applied",
                    f"{ticker} MODERATE→HIGH via {earnings_source}",
                    json.dumps({
                        "ticker": ticker,
                        "alert_date": today.isoformat(),
                        "gap_pct": round(c["gap_pct"], 2),
                        "ep_score": round(ep_score, 1),
                        "ep_threshold": ep_threshold,
                        "catalyst_quality": catalyst_quality,
                        "source": earnings_source,
                    }),
                )
                tier = "HIGH"
                earnings_override_fired = True
            else:
                event = (
                    "earnings_override_unavailable"
                    if earnings_source == "unavailable"
                    else "earnings_override_no_match"
                )
                if _audit_dedupe_check(ticker, today, event):
                    await log_audit_event(
                        event,
                        f"{ticker} {earnings_source}",
                        json.dumps({
                            "ticker": ticker,
                            "alert_date": today.isoformat(),
                            "gap_pct": round(c["gap_pct"], 2),
                            "ep_score": round(ep_score, 1),
                            "catalyst_quality": catalyst_quality,
                            "source": earnings_source,
                        }),
                    )

        # Theme-gated ADVISORY grade (#200) RETIRED 2026-06-10 (#249): its
        # question — should theme gate the floor? — was answered by the judge
        # going load-bearing (ADR 0011); the judge weighs the theme/narrative
        # axes on every grade. in_theme stays — it feeds the judge payload.
        in_theme = ticker in _in_active_theme_set

        # Fire panel heuristic (#201) RETIRED 2026-06-10 (#249): the judge's
        # verdict fire_axes (catalyst/theme/narrative) is the fire signal,
        # written post-scan by _judge_shadow. in_narrative stays — judge input.
        in_narrative = ticker in _in_narrative_cohort_set

        # Tape-conviction shadow — forward-only baseline for a future tape-only
        # override; one row per ticker per scan_date (deduped across cron ticks).
        proj_vol = c.get("projected_vol_multiple")
        if (
            c["gap_pct"] >= 12.0
            and proj_vol is not None
            and proj_vol >= 5.0
            and _audit_dedupe_check(ticker, today, "tape_conviction_shadow")
        ):
            await log_audit_event(
                "tape_conviction_shadow",
                f"{ticker} gap={c['gap_pct']:.1f}% proj={proj_vol:.1f}x tier={tier}",
                json.dumps({
                    "ticker": ticker,
                    "alert_date": today.isoformat(),
                    "gap_pct": round(c["gap_pct"], 2),
                    "projected_vol_multiple": round(proj_vol, 2),
                    "ep_score": round(ep_score, 1),
                    "tier": tier,
                    "catalyst_quality": catalyst_quality,
                }),
            )

        # Wave C shadow (#233) — does the Perplexity AGREEMENT BOOST manufacture
        # HIGHs with no direct primary source? confidence_multiplier==1.2 means
        # Claude+Perplexity agreed on strong/gc AND the answer did NOT self-hedge
        # (the hedge path L1496-1529 already cancels the boost) — the confident-
        # confabulation population. Record the boost-OFF score via the REAL scorer
        # (single-source-of-truth) + whether the earnings override would rescue it;
        # the offline analyzer decides "manufactured". Telemetry-only, one row per
        # ticker/day on the uncached grade tick. Pairs with Wave-B
        # ep_provenance_daily (the sole-source role). This is a LOWER BOUND on ONE
        # mechanism — the base grade is itself lifted by Perplexity-in-corpus
        # (unmeasured until the Part-2 corpus re-grade); do NOT read a small count
        # as "Perplexity demotion is low-value".
        if (
            confidence_multiplier >= 1.2
            and _has_direct_source is not None
            and _audit_dedupe_check(ticker, today, "perplexity_boost_shadow")
        ):
            try:
                _score_noboost, _ = _score_ep(
                    gap_pct=c["gap_pct"],
                    rel_volume=rel_volume,
                    catalyst_quality=catalyst_quality,
                    profile=profile,
                    regime_multiplier=regime_multiplier,  # boost OFF (×1.0)
                    projected_vol_multiple=c.get("projected_vol_multiple"),
                    vol_percentile=vol_pct,
                    prior_3m_change=prior_3m_change,
                    in_active_theme=(ticker in _in_active_theme_set),
                )
                await log_audit_event(
                    "perplexity_boost_shadow",
                    f"{ticker} {tier} boost={confidence_multiplier} direct={_has_direct_source}",
                    json.dumps({
                        "ticker": ticker,
                        "alert_date": today.isoformat(),
                        "catalyst_quality": catalyst_quality,
                        "has_direct_source": _has_direct_source,
                        "live_tier": tier,
                        "live_score": round(ep_score, 1),
                        "score_without_boost": round(_score_noboost, 1),
                        "ep_threshold": ep_threshold,
                        "earnings_override_fired": earnings_override_fired,
                    }),
                )
            except Exception as _e:
                logger.debug(f"{ticker}: perplexity_boost_shadow skipped — {_e}")

        result = {
            **c,
            "ep_score": ep_score,
            "score_tier": tier,
            "catalyst_quality": catalyst_quality,
            # #360: grounded claude_analysis when a direct source was found, else the
            # Perplexity narrative (see _resolve_catalyst_text). Same clip (500).
            "catalyst": _resolve_catalyst_text(claude_analysis, news_summary, _has_direct_source, 500),
            "claude_analysis": claude_analysis,
            # #317: whether the catalyst sources include a DIRECT/primary source (SEC filing /
            # press wire) — load-bearing for the alert's catalyst-display coherence. When True,
            # claude_analysis is grounded in it and the separate Perplexity discovery narrative
            # (the "catalyst" field) is suppressed in the alert (it sometimes contradicts the grade).
            "has_direct_source": _has_direct_source,
            "gemini_validation": pplx_quality,  # DB column name kept for compatibility
            "confidence_multiplier": confidence_multiplier,
            "vol_percentile": vol_pct,
            "score_breakdown": breakdown,
            "in_active_theme": in_theme,
            "in_narrative_cohort": in_narrative,
            "alert_date": today,
            # Holistic Grade Judge (#240) inputs threaded for the post-loop shadow call.
            "grounded_text": grounded_text,
            "market_cap": profile.get("marketCap"),
            "sector": profile.get("sector"),
            # #332 (C1 setup-class classifier, ADR 0028 §2): the REAL 52-week high (distinct
            # from structure_axis_shadow's ~13-month mi_daily_closes trailing_high — don't
            # conflate the two), threaded at detection time so the classifier is point-in-
            # time/lookahead-honest per the ADR's field-provenance paragraph. `current_price`
            # (the Polygon gap-detection price) is already on `r` via `**c` above — no
            # separate "price" field needed. (upgrades_30d is NOT threaded here — #332
            # 2026-07-18: the old get_fmp_analyst_ratings-based source was a dead feed;
            # the classifier now sources its own recent-upgrade count directly via
            # setup_class_classifier.compute_setup_class_fields, see that module.)
            "week52_high": profile.get("52WeekHigh"),
            "baseline_floor_tier": tier,
            # W2a (#243): floor drove this alert's tier (holistic_judge_enabled OFF —
            # W1/W2-dormant). The W2 flip overwrites this with 'judge'/'fallback'.
            "grade_engine_authority": "floor",
        }
        results.append(result)

        # Log to scan log as passed
        scan_log.append(_scan_row(
            c, reason=None, ep_score=ep_score, tier=tier,
            catalyst_quality=catalyst_quality,
        ))

        # Store in DB
        await insert_ep_alert({
            "ticker": ticker,
            "alert_date": today,
            "gap_pct": c["gap_pct"],
            "rel_volume": rel_volume,
            "ep_score": ep_score,
            "score_tier": tier,
            # #360: same source resolution as the in-memory result above (anti-drift).
            "catalyst": _resolve_catalyst_text(claude_analysis, news_summary, _has_direct_source, 500),
            "catalyst_quality": catalyst_quality,
            "claude_analysis": claude_analysis,
            "gemini_validation": pplx_quality,  # DB column name kept for compatibility
            "confidence_multiplier": confidence_multiplier,
            "vol_percentile": vol_pct,
            "pm_rvol": c.get("pm_rvol"),
            "pm_rvol_baseline_n": c.get("pm_rvol_baseline_n"),
            "detected_at": now_et,
            "in_active_theme": in_theme,
            "in_narrative_cohort": in_narrative,
            "grounded_text": grounded_text,
            "baseline_floor_tier": tier,
            "grade_engine_authority": "floor",  # W2a: floor authority while toggle OFF
        })

        # Cross-strategy allocator (#31) Phase 1A — shadow enqueue. HIGH and
        # MODERATE tiers are slot contenders. Legacy submission pipeline runs
        # unchanged; the 9:28 AM allocator job reads this queue, scores, and
        # writes shadow_rank for offline comparison vs actual fills. UPSERT —
        # later-tick re-scores update in place. Failure here MUST NOT block
        # the alert path; wrap defensively.
        if tier in ("HIGH", "MODERATE"):
            try:
                from agents.market_intelligence.cross_strategy_allocator import score_magna53
                cand = score_magna53(
                    ticker=ticker,
                    alert_date=today,
                    ep_score=ep_score,
                    catalyst_quality=catalyst_quality,
                    pm_rvol=c.get("pm_rvol"),
                    gap_pct=c.get("gap_pct"),
                    regime_label=regime_label,
                )
                await enqueue_pending_allocation(
                    ticker=ticker, alert_date=today, strategy="magna53",
                    composite_score=cand.composite,
                    raw_dimensions=cand.raw_dimensions,
                )
            except Exception as e:
                logger.warning(f"allocator enqueue failed for {ticker} ({tier}): {e}")

        # Telemetry for `conviction_floor_extension` review (data_gated_reviews.yaml).
        # Cell under evaluation: gap∈[10,15) + catalyst='strong'. Logs whether the
        # candidate would have been promoted to HIGH at floors 55/58/60.
        if catalyst_quality == "strong" and 10 <= c["gap_pct"] < 15:
            await log_audit_event(
                "conviction_floor_eligible",
                f"{ticker} gap={c['gap_pct']:.1f}% score={ep_score:.0f} tier={tier}",
                json.dumps({
                    "ticker": ticker,
                    "alert_date": today.isoformat(),
                    "gap_pct": round(c["gap_pct"], 2),
                    "ep_score": round(ep_score, 1),
                    "ep_threshold": ep_threshold,
                    "actual_tier": tier,
                    "would_be_high_at_55": max(ep_score, 55) >= ep_threshold,
                    "would_be_high_at_58": max(ep_score, 58) >= ep_threshold,
                    "would_be_high_at_60": max(ep_score, 60) >= ep_threshold,
                }),
            )

        proj = c.get("projected_vol_multiple")
        pm_rvol_val = c.get("pm_rvol")
        vol_parts = [f"rvol={rel_volume:.1f}x"]
        if proj:
            vol_parts.append(f"proj={proj:.0f}x")
        if pm_rvol_val is not None:
            vol_parts.append(f"pm_rvol@t={pm_rvol_val:.2f}x")
        vol_str = " ".join(vol_parts)
        logger.info(f"EP alert: {ticker} gap={c['gap_pct']:.1f}% {vol_str} score={ep_score} tier={tier}")

    results.sort(key=lambda r: r["ep_score"], reverse=True)

    # Batch-write scan log (fire and forget — never block results)
    asyncio.create_task(log_ep_scan_candidates(scan_log))

    # Summary log — always visible, even when no alerts fire. Helps verify the scan ran
    # and diagnose why candidates were filtered out.
    high = [r for r in results if r["score_tier"] == "HIGH"]
    moderate = [r for r in results if r["score_tier"] == "MODERATE"]
    logger.info(
        f"EP scan complete: {len(candidates)} gap candidates → {len(results)} scored "
        f"({len(high)} HIGH, {len(moderate)} MODERATE) | "
        f"regime={regime_label} threshold={ep_threshold}"
    )

    # ── North Star C1 (2026-05-30): catalyst-TYPE classification (ADVISORY) ──
    # Fire-identity signal (Pradeep hierarchy: theme > policy > shortage >
    # operational). Runs AFTER the candidate loop + per-candidate
    # insert/gating/alert-decision (all byte-identical + unblocked — DECOUPLED
    # from the `quality` gating call). Concurrent (semaphore-capped inside the
    # classifier) → ~one Haiku round-trip total, not per-candidate, before the
    # caller sends alerts → catalyst_type surfaces on the alert. Uses the SAME
    # day-of inputs (catalyst summary + claude_analysis) the historical backfill
    # used → backfill↔live input parity (feedback_backfill_llm_label_lookahead).
    # FAIL-OPEN: any error leaves catalyst_type NULL; NEVER blocks/breaks alerts.
    try:
        from agents.market_intelligence.catalyst_type_classifier import classify_catalyst_type
        from agents.market_intelligence.db import (
            update_ep_alert_advisory, update_ep_alert_judge_result,
            update_ep_alert_setup_class,
            get_holistic_judge_enabled, get_composite_authority_enabled,
        )
        from agents.market_intelligence.ep_grade_judge import (
            assemble_judge_inputs, grade_holistic,
        )
        from agents.market_intelligence.catalyst_materiality import (
            extract_deal_value, rule_materiality,
        )

        # W2c (#243 / ADR 0011): read the authority toggle ONCE per scan (not per
        # candidate). OFF → judge stays pure shadow (byte-identical to W1). ON → the judge
        # tier OVERWRITES the authoritative score_tier (drives alert/entry); the floor tier
        # is preserved as baseline_floor_tier. FAIL-CLOSED inside the helper (error → floor).
        _judge_authority = await get_holistic_judge_enabled()

        async def _judge_shadow(r: dict) -> None:
            # Holistic Grade Judge (#240 / ADR 0011) — Wave 1 SHADOW: records the
            # judge's bidirectional verdict (judge_tier/direction/rationale) alongside
            # the floor's baseline_floor_tier; drives NOTHING. FAIL-OPEN: a None verdict
            # leaves the columns NULL + emits ep_grade_decision with judge_outcome='null'
            # (counted, via _emit_grade_decision) — never breaks the scan. Runs in the same
            # bounded gather as catalyst_type but on its OWN
            # _JUDGE_SEMAPHORE — the larger 6000-char judge call stays concurrent with,
            # rather than starving, the catalyst grader/fire panel under the 9:45 cutoff.
            floor_tier = r.get("baseline_floor_tier")
            # ── C1 setup-class classifier (#332, ADR 0028) — OWN try/except: P0 VISIBILITY
            # ONLY (THE LINE: zero grade mutation, no salience weights, no composite/tier
            # change — that's P1/P2/P3, each its own future operator-gated flip). Computed
            # FIRST (before the judge payload is assembled below) so the tag rides the SAME
            # grading pass's judge DecisionContext from day one (ADR 0028 §2). A classify
            # failure must NEVER block judge grading or the axis shadows further down — hence
            # its own isolated try/except rather than sharing the outer one.
            _setup_class: "str | None" = None
            try:
                from agents.market_intelligence.setup_class_classifier import (
                    classify_setup_class, compute_setup_class_fields,
                )
                _sc_pool = await get_pool()
                async with _sc_pool.acquire() as _sc_conn:
                    _sc_fields = await compute_setup_class_fields(_sc_conn, r)
                _setup_class = classify_setup_class(_sc_fields)
                r["setup_class"] = _setup_class  # display-only, mirrors catalyst_type/judge_rationale
                await update_ep_alert_setup_class(r["ticker"], r["alert_date"], _setup_class)
            except Exception as _sce:
                logger.warning(f"setup-class classify failed for {r.get('ticker')}: {_sce}")
            try:
                # W4 (#245): feed the judge the DETERMINISTIC deal-size÷market-cap
                # materiality tier — the exact ratio an LLM can't compute reliably
                # (RUM $270M @ $2.5B = material). rule_materiality ONLY: the judge's own
                # call owns the soft/abstain materiality (it outputs materiality_tier over
                # the same grounded_text+cap), so we deliberately do NOT invoke
                # assess_materiality's Sonnet leg here — that'd be a redundant 2nd hot-path
                # LLM call the judge would just reproduce. Not a single-source violation:
                # the deterministic rule is the shared function; the LLM leg is subsumed
                # into the one judge by design. None ratio → judge decides materiality.
                try:
                    _mc = float(r.get("market_cap")) if r.get("market_cap") is not None else None
                except (TypeError, ValueError):
                    _mc = None
                _rule_mat = rule_materiality(
                    extract_deal_value(f"{r.get('catalyst') or ''} {r.get('claude_analysis') or ''}"),
                    _mc,
                )
                payload = assemble_judge_inputs(
                    r, grounded_text=r.get("grounded_text"),
                    market_cap=_mc, sector=r.get("sector"),
                    materiality_tier=_rule_mat,
                    active_narratives=_narrative_cohorts,
                    setup_class=_setup_class,
                )
                verdict = await grade_holistic(
                    _get_claude(), payload,
                    # THE LIVE grade path — the one caller entitled to this bucket. Passed
                    # explicitly since 2026-08-02 (the default was removed); same string, so
                    # attribution is byte-identical to every historical row.
                    log_caller="ep_grade_judge",
                    # 15→25s with the 2026-06-10 JUDGE_MODEL=OPUS flip — Opus
                    # is slower; the eval's only ERR row was an Opus timeout.
                    # A tight ceiling converts model quality into fail-open.
                    semaphore=_JUDGE_SEMAPHORE, timeout=25,
                )
                # W2c (#243): LOAD-BEARING override — only when the toggle is ON. The judge
                # tier overwrites the authoritative score_tier (the field the caller reads for
                # alert+entry, and downstream reads from the DB row). 'none' → suppression
                # (score_tier != HIGH → no alert, no ORB entry); promote MODERATE→HIGH → flows
                # into the ORB path exactly as a floor-HIGH. baseline_floor_tier is preserved
                # as the counterfactual. A None verdict FAILS OPEN to the floor (authority
                # 'fallback', floor tier kept). Toggle OFF → none of this runs (byte-identical).
                new_tier, authority, do_override = _resolve_grade_authority(
                    _judge_authority, verdict, floor_tier)
                # ── M1-d composite authority (ADR 0024 §6) — DARK: default OFF, byte-
                # identical until the operator flips the DB toggle (mi_safeguard_state
                # 'composite_authority_enabled'; the read FAILS CLOSED — missing row or
                # any error → False → this whole block is a no-op). When ON, compose the
                # theme-axis credit onto the AUTHORITATIVE tier via the pure M1-a
                # composer. base_tier == new_tier in EVERY case (_resolve_grade_authority
                # returns floor_tier whenever !do_override, judge tier otherwise). Own
                # try/except → FAIL-OPEN to the base grade: any error leaves new_tier/
                # authority/do_override exactly as _resolve_grade_authority set them +
                # emits a COUNTED composite_authority_failed audit event — a composition
                # failure NEVER blocks the base-grade write or breaks the scan. The
                # composed values flow through the SAME atomic
                # update_ep_alert_judge_result below — no new write path.
                if await get_composite_authority_enabled():
                    try:
                        from agents.market_intelligence.catalyst_rubric_runtime import (
                            compute_theme_axis_credit_live,
                        )
                        from agents.market_intelligence.meta_rubric_compose import (
                            resolve_composite_tier,
                        )
                        base_tier = new_tier  # == floor_tier when !do_override, judge tier otherwise
                        credit = await compute_theme_axis_credit_live(r)
                        if credit is not None:
                            # Stage into temps; COMMIT to new_tier/authority/do_override
                            # only as the LAST step — a failure anywhere in this block
                            # (even the trace write) leaves the base grade fully intact.
                            _c_tier, _c_auth, _c_over, _composition = resolve_composite_tier(
                                base_tier, authority, do_override, [credit])
                            if _composition is not None and _composition.final_tier != base_tier:
                                # Composed tier moved — persist an explicit trace row for
                                # verify-live + /why, and mirror it on r (display-only).
                                _trace = {
                                    "base_tier": base_tier,
                                    "final_tier": _composition.final_tier,
                                    "net_raw": _composition.net_raw,
                                    "net_capped": _composition.net_capped,
                                    "contributions": [
                                        {"axis": c.axis, "steps": c.steps,
                                         "marker": c.marker, "reason": c.reason}
                                        for c in _composition.contributions
                                    ],
                                    "credit": credit,
                                }
                                await log_audit_event(
                                    "theme_axis_composed",
                                    f"{r['ticker']} {r['alert_date']}: {base_tier} -> "
                                    f"{_composition.final_tier} "
                                    f"(net {_composition.net_capped:+d}, authority=composite)",
                                    json.dumps(_trace, default=str),
                                )
                                r["composite_trace"] = _trace  # display-only, for /why later
                            new_tier, authority, do_override = _c_tier, _c_auth, _c_over
                    except Exception as _ce:
                        # FAIL-OPEN: base grade stands untouched (temps never committed);
                        # counted (log_audit_event never raises) so silent degradation is
                        # visible in /audit + the weekly review.
                        await log_audit_event(
                            "composite_authority_failed",
                            f"{r.get('ticker')} {r.get('alert_date')}: "
                            f"{type(_ce).__name__}: {_ce}",
                        )
                if verdict is not None or do_override:
                    v = verdict or {}
                    # ONE atomic UPDATE (#247): judge_* columns + the conditional
                    # score_tier/authority override land in the same statement —
                    # no partial-write window. DB FIRST, then mutate the
                    # in-memory result — a failed write leaves BOTH on the floor
                    # tier (the caller reads r, the entry job reads the row —
                    # they must agree).
                    try:
                        await update_ep_alert_judge_result(
                            r["ticker"], r["alert_date"],
                            judge_tier=v.get("tier"),
                            judge_direction=v.get("direction_vs_floor"),
                            judge_rationale=v.get("rationale"),
                            judge_materiality_tier=v.get("materiality_tier"),
                            fire_axes=v.get("fire_axes"),
                            score_tier=new_tier if do_override else None,
                            grade_engine_authority=authority if do_override else None,
                            rubric_version=RUBRIC_VERSION if verdict is not None else None,
                        )
                    except Exception as _we:
                        # A failed judge write is the one fail-open path the DB
                        # decision trace can't show — make it COUNTED (#173
                        # silent-failure class): audit row (log_audit_event never
                        # raises) + revert to the floor in memory so r and the
                        # row agree (both floor). The delta digest stays empty,
                        # but /audit + weekly review see judge_write_failed.
                        logger.error(
                            f"judge result write failed for {r.get('ticker')}: {_we}")
                        do_override = False
                        await log_audit_event(
                            "judge_write_failed",
                            f"{r['ticker']} {r['alert_date']}: {type(_we).__name__}: {_we}",
                        )
                    else:
                        if verdict is not None:
                            # #249: the judge's fire_axes IS the fire signal —
                            # mutate r AFTER the write succeeds (DB-first), so
                            # the Telegram alert never renders axes the row lacks.
                            r["fire_axes"] = v.get("fire_axes")
                            # #329-trace (display-only): surface the JUDGE's own
                            # rationale + materiality on the alert. Same DB-first
                            # discipline as fire_axes — only after the write, so
                            # the alert never shows a "why" the row lacks. The
                            # alert italic leads with judge_rationale when the
                            # judge is authoritative (it was showing the FLOOR's
                            # analysis under an authoritative judge — same
                            # coherence gap as #319).
                            r["judge_rationale"] = v.get("rationale")
                            r["judge_materiality_tier"] = v.get("materiality_tier")
                            # ── #322 judge → narrative-radar feed ──────────────────
                            # The judge lit fire_axes theme/narrative on a ticker
                            # NEITHER lane tracks (the JBL AI-infra class) — write a
                            # surface-only mi_theme_candidates_shadow candidate
                            # (source='judge_inferred') so the gap accrues into the
                            # narrative radar instead of living only in prose the
                            # alert discards (judge_theme_gap.py has the full
                            # mechanism + the anti-circularity walls). OWN
                            # try/except: a feed failure must never disturb the
                            # judge write or the alert path (SHADOW invariant).
                            try:
                                from agents.market_intelligence.judge_theme_gap import (
                                    feed_judge_theme_gap,
                                )
                                _jtg_pool = await get_pool()
                                async with _jtg_pool.acquire() as _jtg_conn:
                                    await feed_judge_theme_gap(
                                        _jtg_conn, r["ticker"], r["alert_date"],
                                        sector=r.get("sector"),
                                        fire_axes=v.get("fire_axes"),
                                        in_active_theme=bool(r.get("in_active_theme")),
                                        in_narrative_cohort=bool(r.get("in_narrative_cohort")),
                                        rationale=v.get("rationale"),
                                    )
                            except Exception as _jtge:
                                logger.warning(
                                    f"judge theme-gap feed failed for {r.get('ticker')}: {_jtge}")
                            # ── #301 ensemble-divergence SHADOW ─────────────────────
                            # ZERO AUTHORITY (THE LINE): fire-and-forget 2nd-model
                            # (Sonnet) independent grade on the primary judge's
                            # HIGH-tier verdict, for operator visibility only — never
                            # touches r/score_tier/the alert. Placed HERE, strictly
                            # AFTER the DB-first write above succeeded (v.get('tier')
                            # is the SETTLED primary verdict), so it can only ever run
                            # once the primary path has fully completed. Gated on the
                            # once-per-ticker-per-day dedupe guard (the EP scan re-runs
                            # every 5 min; without it a HIGH alert re-fires the 2nd-
                            # model call on every tick, ~36x/day instead of the
                            # designed ~2-5/day). Dedupe key uses `today` (NOT
                            # r["alert_date"]) deliberately — _audit_dedupe_check shares
                            # ONE module-level set that CLEARS whenever its scan_date arg
                            # differs from the previous call's, regardless of event name;
                            # the sibling theme_axis_shadow_adjusted guard just below
                            # keys off `today` too, so matching it here is what keeps the
                            # two guards from clearing each other's state (r["alert_date"]
                            # == today for every candidate today, but `today` is the
                            # guaranteed-matching key, not an assumption about `r`).
                            # launch_divergence_check schedules a background asyncio.Task
                            # and returns immediately — it is NEVER awaited, so a slow/
                            # failed/timed-out 2nd-model call cannot add latency here or
                            # anywhere downstream.
                            if v.get("tier") == "HIGH" and _audit_dedupe_check(
                                r["ticker"], today, "judge_divergence_check"
                            ):
                                try:
                                    from agents.market_intelligence.judge_divergence import (
                                        launch_divergence_check,
                                    )
                                    launch_divergence_check(
                                        r["ticker"], r["alert_date"], payload, v,
                                    )
                                except Exception as _jde:
                                    logger.warning(
                                        f"judge divergence launch failed for {r.get('ticker')}: {_jde}")
                if do_override:
                    r["score_tier"] = new_tier
                    r["grade_engine_authority"] = authority
                # Comprehensive decision trace (W2a #243, OPERATOR REQUIREMENT). ONE
                # ep_grade_decision per graded candidate — verdict, hold, OR null — so a
                # grade is never a black box: review/debug/tune read this. judge_outcome
                # makes the silent-degradation case ('null': timeout/malformed → fail-open
                # to floor) explicit + COUNTED. authority='floor' while the toggle is OFF.
                await _emit_grade_decision(r, floor_tier, verdict)
                # ── Large-cap rel_volume floor SHADOW (data_gated_reviews.yaml
                # `large_cap_relvol_floor_shadow_evidence`) ─────────────────────────────
                # Placed HERE (right after the override settles + _emit_grade_decision, same
                # "final settled tier" placement rule as the theme/structure axis shadows
                # below) but BEFORE them and OUTSIDE their shared `if HIGH/MODERATE` block —
                # deliberately decoupled so a failure in either sibling shadow can never
                # suppress this one. Self-contained top-level function (defined above
                # run_ep_scan, unit-testable in isolation); internally re-checks
                # score_tier=='HIGH'/the env flag/ADV$/rel_volume, so it's safe to call
                # unconditionally here. NEVER mutates r/score_tier (THE LINE) — writes ONE
                # audit row, never raises (wrapped internally + never touches the alert path).
                await _emit_large_cap_relvol_floor_shadow(r, now_et)
                # ── Theme-axis SHADOW (#329 STEP-0) ───────────────────────────────────
                # Log the as-of theme heat + deterministic structural attribution for each
                # scored EP HIGH+MODERATE — telemetry the live judge is blind to (theme
                # stage/score), so DATA can size the theme weighting before the #335
                # load-bearing flip. Placed AFTER the override settles (2901-2903) +
                # _emit_grade_decision so we read the FINAL authoritative score_tier, not
                # the pre-override value. SHADOW: own conn, read-only on r, writes only
                # mi_theme_axis_shadow, never raises (the writer swallows to an audit event).
                # Gate = final settled tier in (HIGH, MODERATE) — S1 of the coverage loop
                # (docs/analysis/ep_theme_coverage_loop_design_2026-07-13.md §6). Widened
                # from HIGH-only 2026-07-13: this COMPLETES ADR 0015's signed "accrue incl.
                # sub-HIGH tiers" rollout intent (design C3 — the deployed gate had never
                # matched the ADR), and starts accruing the exact MODERATE population the
                # DARK M1-d credit acts on. Both shadow writers below are tier-agnostic
                # (they log whatever grade they're handed) and NEVER mutate r/score_tier —
                # they write only mi_theme_axis_shadow + mi_audit_log (THE LINE holds; the
                # once/ticker/day dedupe guards still apply: STEP-0 via its
                # (ticker, alert_date) upsert, the credit shadow via _audit_dedupe_check).
                if r.get("score_tier") in ("HIGH", "MODERATE"):
                    from agents.market_intelligence.theme_axis_shadow import (
                        log_theme_axis_shadow,
                    )
                    _pool = await get_pool()
                    async with _pool.acquire() as _tas_conn:
                        await log_theme_axis_shadow(_tas_conn, r)
                    # ── ADR 0015 (#328) theme-axis CREDIT shadow ───────────────────────
                    # SHADOW ONLY, distinct from the STEP-0 structural-attribution shadow
                    # just above: computes theme_axis_credit() (the operator-signed
                    # stage->credit table) against the SAME cached rubric result + as-of
                    # membership, and logs 'theme_axis_shadow_adjusted' when informative.
                    # Read-only on r, writes only mi_audit_log, NEVER mutates the live
                    # label/tier (THE LINE — the flip to load-bearing is a separate
                    # CHANGE_PROCESS gate, never on agent authority). Same gate/placement
                    # as the STEP-0 shadow — final settled tier, low blast radius.
                    # 7/4 review: once/ticker/day like the sibling shadows —
                    # _judge_shadow re-runs per 5-min tick; without this guard the
                    # credit shadow re-paid the rubric recompute AND wrote ~36
                    # duplicate audit rows/day into the very telemetry #368 counts.
                    if _audit_dedupe_check(r["ticker"], today, "theme_axis_shadow_adjusted"):
                        from agents.market_intelligence.catalyst_rubric_runtime import (
                            log_theme_axis_adjusted_shadow,
                        )
                        await log_theme_axis_adjusted_shadow(r)
                    # ── Structure-axis SHADOW (#330, ADR 0016) ─────────────────────────
                    # Sibling of the #329 theme-axis shadow just above — same gate/placement
                    # (final settled tier, low blast radius) and same wiring shape: there is
                    # no separate scheduler.py job for this (mirrors theme_axis_shadow.py
                    # exactly — neither rides a dedicated cron entry; both ride the existing
                    # `ep_scan` job via this call site inside _judge_shadow). Own upsert-
                    # guarded table (mi_structure_axis_shadow, UNIQUE (ticker, alert_date)) —
                    # no additional dedupe guard needed, unlike the audit-log-only credit
                    # shadow above. SHADOW ONLY: reads mi_daily_closes (read-only), writes
                    # only mi_structure_axis_shadow + mi_audit_log, NEVER mutates
                    # r/score_tier (THE LINE).
                    from agents.market_intelligence.structure_axis_shadow import (
                        log_structure_axis_shadow,
                    )
                    async with _pool.acquire() as _sas_conn:
                        await log_structure_axis_shadow(_sas_conn, r)
            except Exception as _je:
                logger.warning(f"judge shadow failed for {r.get('ticker')}: {_je}")

        async def _classify_type(r: dict) -> None:
            try:
                res = await classify_catalyst_type(
                    r["ticker"], r.get("catalyst"), r.get("claude_analysis"),
                    sector=(r.get("sector") or None),
                )
                r["catalyst_type"] = res.get("catalyst_type")
                r["catalyst_type_rationale"] = res.get("rationale")
                # Fire-panel refine RETIRED 2026-06-10 (#249) — the judge's
                # verdict fire_axes (persisted in _judge_shadow) is the fire
                # signal; catalyst_type stays a pure advisory label here.
                await update_ep_alert_advisory(
                    r["ticker"], r["alert_date"],
                    r.get("catalyst_type"), r.get("catalyst_type_rationale"),
                )
            except Exception as _te:
                logger.warning(f"catalyst_type classify failed for {r.get('ticker')}: {_te}")

        _alerted = high + moderate
        if _alerted:
            # Bounded: this advisory signal must NEVER delay the latency-sensitive
            # HIGH alert (9:45 ORB cutoff). wait_for cancels stragglers on timeout;
            # classifications that already completed keep their values (fail-open
            # on latency, not just on exception). Outer except handles TimeoutError.
            # W2c (#243): when the judge is LOAD-BEARING (toggle ON) its grade override +
            # ep_grade_decision log are correctness-critical — a straggler cancelled at the
            # 25s shadow ceiling would silently drop the override (keeps floor) AND its
            # decision row (logging hole on heavy mornings). So give the gather room
            # (≈4 _JUDGE_SEMAPHORE(3) waves × the 25s judge timeout, 2026-06-10
            # Opus flip) when ON; keep the tight latency guard for the
            # advisory-only catalyst_type when OFF. Still well inside the
            # 5-min ORB scan cadence.
            _post_loop_timeout = 110 if _judge_authority else 25
            await asyncio.wait_for(
                asyncio.gather(
                    *[_classify_type(r) for r in _alerted],
                    *[_judge_shadow(r) for r in _alerted],  # #240 — concurrent
                ),
                timeout=_post_loop_timeout,
            )
    except Exception as _e:
        logger.warning(f"catalyst_type post-scan block failed (non-critical): {_e}")

    # #149 shadow RETIRED 2026-07-02 (#400b). The #321 LIVE recovery (the
    # q_rev_yoy_missing rescue in the gate block above) supersedes it: post-fix
    # the shadow only re-fetched the same yfinance answer for names the rescue
    # had already decided — rescue-None dupes (CHTR 6/29: the same stay_down
    # logged every 5-min tick for hours) and in-ORB-window skips that stay
    # conservative BY DESIGN (the latency guard). History lives in the
    # catalyst_q_rev_yoy_shadow_recovered audit rows (last emitted 2026-07-02).

    # ── #498 TQS Stage 1 — tape-quality SHADOW annotation ─────────────────────────────────
    # (docs/design/tape_quality_score.md §4 Stage 1, operator-AUTHORIZED 2026-07-21 —
    # TELEMETRY-ONLY.) Placed as the LAST post-scan block, architecturally DOWNSTREAM of
    # every decision path: the floor score/tier (candidate loop), the judge override, the
    # composite authority, and _emit_grade_decision (post-loop block above) have ALL fully
    # settled before this runs — TQS cannot reach the grade, the entry, or sizing by
    # construction (THE LINE; the Stage-4 gate/demote decision is operator-only, never here).
    # It reads mi_daily_closes (strictly PRE-alert bars — no lookahead) and writes ONLY the
    # mi_ep_alerts tape_* columns + the display-only r['tape_quality'] key (rendered by
    # send_ep_alert; nothing in grading/entry reads it). UNIVERSAL — every scored alert row,
    # all tiers (wide-and-loose is bad across ALL EP charts, not just #331's fades cohort).
    # Bounded + fail-open: pure DB reads + arithmetic (no LLM) under a hard wait_for ceiling,
    # so a DB stall can't delay the latency-sensitive HIGH alerts the caller sends next; any
    # failure/timeout leaves tape columns NULL and the alert renders without a TAPE line.
    try:
        from agents.market_intelligence.tape_quality import annotate_ep_alerts_tape_quality
        await asyncio.wait_for(annotate_ep_alerts_tape_quality(results), timeout=20)
    except Exception as _tqe:
        logger.warning(f"tape-quality annotation failed (non-critical): {_tqe}")

    return results
