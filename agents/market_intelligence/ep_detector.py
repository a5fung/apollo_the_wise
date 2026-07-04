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
    get_fmp_analyst_ratings,
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
from shared.llm_models import GROUNDED_GRADE_MODEL, JUDGE_MODEL
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
            "judge_model": JUDGE_MODEL,
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

    ext_filings, dilution, benzinga_items, perplexity_answer = await asyncio.gather(
        _fetch_ext_filings(), _fetch_dilution(),
        _fetch_benzinga_items(), _fetch_perplexity_answer(),
    )

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
                        max_tokens=300,
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
        # #377 cost meter — additive, never alters the catalyst grade. log_anthropic_call_safe
        # is the sanctioned wrapper (S2/F9) — it swallows+warns internally, never raises.
        from agents.market_intelligence.spend_tracker import log_anthropic_call_safe
        await log_anthropic_call_safe(model=GROUNDED_GRADE_MODEL, caller="ep_catalyst_grade",
                                       usage=getattr(response, "usage", None))
        tool_block = next(b for b in response.content if b.type == "tool_use")
        result = tool_block.input
        return result["quality"], result["analysis"]
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
        return "routine", "Classification failed — treating as routine."


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
    analyst_upgrades: int,
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

    # Analyst upgrades (max 5)
    breakdown["analyst"] = min(analyst_upgrades * 2, 5) if analyst_upgrades >= 3 else 0

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


async def run_ep_scan(prev_close_date: str | None = None) -> list[dict]:
    """
    Run pre-market EP scan.
    Returns list of EP candidates with scores.

    prev_close_date: "YYYY-MM-DD" of the last trading day
    """
    today = et_today()
    today_str = today.strftime("%Y-%m-%d")
    prev_date = prev_close_date or today_str  # fallback

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
    _SESSION_MINUTES = 390  # 6.5-hour regular session
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
            if gap_pct < MIN_GAP_PCT:
                continue

            # Volume: day.v for regular session, min.av for accumulated (includes pre-mkt)
            today_volume = snap.get("day", {}).get("v", 0) or snap.get("min", {}).get("av", 0) or 0
            adv = adv_map.get(ticker)
            # prevDay.v as temporary placeholder — proper 20-day ADV computed below for non-universe stocks
            adv_source = "rs_universe" if adv else "pending"
            if not adv:
                adv = snap.get("prevDay", {}).get("v") or None

            raw_rvol = round((today_volume / adv), 2) if adv and adv > 0 else None
            # Open intensity: projected full-day RVOL = raw_rvol * (390 / min_elapsed)
            # Gate: only project after 15 minutes (9:45 AM). The opening 15 minutes are
            # structurally dense — every stock shows 10-30x projected RVOL at 9:31 AM
            # regardless of real institutional interest. Before the gate, use raw RVOL.
            open_intensity = None
            if raw_rvol is not None and _minutes_since_open and today_volume > 0:
                if _minutes_since_open >= 15:
                    open_intensity = round(raw_rvol * (_SESSION_MINUTES / _minutes_since_open), 1)
                # else: intensity stays None — vol filter uses raw_rvol pre-9:45

            candidates.append({
                "ticker": ticker,
                "prev_close": prev_close,
                "current_price": current_price,
                "gap_pct": round(gap_pct, 2),
                "today_volume": today_volume,
                "adv": adv,
                "adv_source": adv_source,
                "rel_volume": raw_rvol,
                "projected_vol_multiple": open_intensity,  # field name kept for DB compat
            })
        except Exception:
            continue

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
        }

    def _log_filtered(c: dict, reason: str) -> None:
        scan_log.append(_scan_row(
            c, reason=reason, ep_score=None, tier=None, catalyst_quality=None,
        ))

    # Log candidates beyond top-20 cap
    for c in candidates[20:]:
        _log_filtered(c, f"outside top-20 gap cap (gap {c['gap_pct']:.1f}%)")

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
            upgrades_30d = 0  # ratings don't change scan-to-scan; skip re-fetch

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
                        # corpus build here; reuse the enrichment shadow's 400d filings /
                        # dilution fetch when it already ran today (no second EDGAR hit).
                        _rq, _ran, _ext, _dilution, _prior_agr, _recent_earn = await _build_enriched_corpus(
                            ticker, today, profile,
                            ext_filings=_st.get("ext_filings"),
                            dilution=_st.get("dilution"),
                            dilution_computed="dilution" in _st,
                        )
                        await log_audit_event(
                            "ep_repoll_shadow",
                            f"{ticker} re-poll routine → {_rq} (+{_cur - _st['count']} src)",
                            json.dumps({
                                "ticker": ticker, "alert_date": today.isoformat(),
                                "cached_quality": catalyst_quality, "repoll_quality": _rq,
                                "would_change": _rq != catalyst_quality,
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
            profile, fmp_news, ratings, perplexity_answer, sec_filings, alpaca_news = await asyncio.gather(
                get_fmp_profile(ticker),
                get_fmp_news(ticker),
                get_fmp_analyst_ratings(ticker),
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
            upgrades_30d = sum(1 for r in ratings if r.get("analystRatingsStrongBuy", 0) > 0)

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

            # Claude + Perplexity in parallel — BOTH always awaited now (S6/#405).
            # The grade must be COMPLETE (Claude classification + Perplexity
            # agreement + hedge-downgrade) before the post-grade filters run, so
            # a filtered ticker's cached grade is fully reusable on a later tick
            # with zero further LLM calls. Pre-#405 this cancelled pplx_task on
            # a filter fail to save the call; that per-call saving is gone, but
            # grading is now capped at ONE full evaluation per ticker per day
            # (see the comment above) instead of the up-to-36x/day re-grade the
            # bug produced — a large net cost win.
            claude_task = asyncio.create_task(
                _classify_catalyst_claude(ticker, all_news, profile, grounded_text=grounded_text))
            pplx_task = asyncio.create_task(_validate_catalyst_perplexity(ticker, news_summary))

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
                "ext_filings": None,
            }
            # PREMARKET-ONLY guard (advisor 6/19): the shadow does extra SEC GETs + a Sonnet
            # call SYNCHRONOUSLY on run_ep_scan — the order-submission path. Confining it to
            # premarket (< 9:30 ET) keeps it OFF the 9:30–10:00 ORB entry window (no added
            # latency where orders submit; no EDGAR-budget contention with the live grade
            # fetch during entries). The motivating case (BFLY's PR, 8:12 ET) is premarket, so
            # coverage is preserved; only open-driven gappers are skipped.
            if (_is_premarket(now_et)
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
                        _downgrade_reason = f"extraction_failed_{extraction_error[:60]}"
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
                    await send_telegram_message(
                        f"{mode_prefix()}📰 *Catalyst downgrade:* `{ticker}` "
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
            analyst_upgrades=upgrades_30d,
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
                    analyst_upgrades=upgrades_30d,
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
            get_holistic_judge_enabled,
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
                )
                verdict = await grade_holistic(
                    _get_claude(), payload,
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
                if do_override:
                    r["score_tier"] = new_tier
                    r["grade_engine_authority"] = authority
                # Comprehensive decision trace (W2a #243, OPERATOR REQUIREMENT). ONE
                # ep_grade_decision per graded candidate — verdict, hold, OR null — so a
                # grade is never a black box: review/debug/tune read this. judge_outcome
                # makes the silent-degradation case ('null': timeout/malformed → fail-open
                # to floor) explicit + COUNTED. authority='floor' while the toggle is OFF.
                await _emit_grade_decision(r, floor_tier, verdict)
                # ── Theme-axis SHADOW (#329 STEP-0) ───────────────────────────────────
                # Log the as-of theme heat + deterministic structural attribution for each
                # scored EP HIGH — telemetry the live judge is blind to (theme stage/score),
                # so DATA can size the theme weighting before the #335 load-bearing flip.
                # Placed AFTER the override settles (2901-2903) + _emit_grade_decision so we
                # read the FINAL authoritative score_tier, not the pre-override value.
                # SHADOW: own conn, read-only on r, writes only mi_theme_axis_shadow, never
                # raises (the writer swallows to an audit event). Gate = final tier == HIGH
                # (face-value "scored EP HIGH"; _judge_shadow also runs on MODERATEs it could
                # promote, so the gate is explicit — not floor-HIGH-inclusive).
                if r.get("score_tier") == "HIGH":
                    from agents.market_intelligence.theme_axis_shadow import (
                        log_theme_axis_shadow,
                    )
                    _pool = await get_pool()
                    async with _pool.acquire() as _tas_conn:
                        await log_theme_axis_shadow(_tas_conn, r)
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

    return results
