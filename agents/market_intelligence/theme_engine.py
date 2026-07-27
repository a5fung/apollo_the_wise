"""
Theme Intelligence Engine — Marios Stamatoudis methodology.

Key insight: themes emerge bottom-up from price action, not top-down from hypothesis.

Daily process:
1. Load existing active themes from DB (re-scored, not re-clustered)
2. Find top RS stocks NOT covered by active themes
3. Claude discovers new themes from uncovered stocks (with existing themes as context)
4. Merge: updated existing themes + new discoveries
5. Lifecycle: Nascent → Accelerating → Mainstream → Fading → Retired

Themes persist for weeks. They evolve as constituent stocks change.
A Fading theme retires after 5 consecutive fading days.
New sub-themes can always emerge from uncovered RS leaders.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
import os
from datetime import date, timedelta
from typing import Any

import anthropic

# #246: the transient-failure handlers below do `isinstance(e, (anthropic.APIError, …))`.
# In some local/CI envs the `anthropic` module is stubbed/shadowed so `anthropic.APIError`
# is NOT a real class → `isinstance()` raises `TypeError: arg 2 must be a type`. Resolve the
# exception classes ONCE at import, keeping only actual types, so the guards can never
# TypeError (an empty tuple is a valid, always-False isinstance arg). Real anthropic →
# real classes (unchanged behaviour); stubbed anthropic → degrades to TimeoutError-only.
def _real_types(*candidates) -> tuple:
    return tuple(c for c in candidates if isinstance(c, type))

_THEME_TRANSIENT_EXC = _real_types(getattr(anthropic, "APIError", None), asyncio.TimeoutError)
_THEME_RATELIMIT_EXC = _real_types(getattr(anthropic, "RateLimitError", None))

# Reused across all Haiku calls in this module — avoids rebuilding the HTTP client per call.
_anthropic_client: anthropic.AsyncAnthropic | None = None

# Anthropic org limit is 50 requests/min. The nightly rescore fans out ~20 themes
# via asyncio.gather; at Semaphore(2) the theme pipeline still contends with
# _ensure_descriptions / _discover_new_themes / _assign_uncovered_to_themes at
# the 5 PM pull, and production still logs 20+ 429s per run. Serialise fully —
# validation is not latency-sensitive (the nightly pull has plenty of headroom)
# and a fully serial call rate of ~30 rpm leaves budget for the other callers.
_VALIDATION_SEMAPHORE = asyncio.Semaphore(1)


def _get_anthropic_client() -> anthropic.AsyncAnthropic:
    global _anthropic_client
    if _anthropic_client is None:
        _anthropic_client = anthropic.AsyncAnthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))
    return _anthropic_client

from agents.market_intelligence.collector import (
    get_fmp_profile, search_news_perplexity, check_perplexity_health, et_today,
)
from agents.market_intelligence.constants import trimmed_mean
from agents.market_intelligence.db import (
    get_pool, get_rs_leaders, get_active_themes, get_rs_velocity, get_rs_turners,
    get_recent_rs_batch, add_theme_exclusion, get_all_theme_exclusions, log_audit_event,
    add_validation_cooldown, get_cooldown_set, get_globally_banned_tickers,
    get_operator_protected_set, get_ticker_breadth_above_sma20,
    add_merge_distinct_cooldown, get_merge_distinct_pairs,
    get_theme_subtheme_arm_enabled,
)
# ADR 0025 (#274) — theme fragmentation controls, behind THEME_MERGE_ARM (default OFF).
# Arm A (dissolve-on-flagged-pair) + Arm B (thesis-coherence merge) both check
# merge_arm_enabled() at run time; with the toggle off every pass below is
# byte-identical to pre-ADR behavior.
from agents.market_intelligence.theme_merge_arm import (
    merge_arm_enabled, propose_merge_pairs, adjudicate_merge_pair,
    family_of,
    MAX_MERGES_PER_NIGHT, MERGE_DISTINCT_COOLDOWN_DAYS,
)

# Global ticker ban — fires when a ticker has been validation-removed from
# ≥ N distinct themes in the last D days. Closes the per-(theme, ticker)
# cooldown leak when a hallucinated name spreads across fragmented themes.
_GLOBAL_BAN_THRESHOLD = 3
_GLOBAL_BAN_LOOKBACK_DAYS = 30

# Theme breadth decay — force Fading when fewer than 40% of members trade
# above their 20-day SMA for 2 consecutive days. Lifecycle otherwise reacts
# to RS smoothed delta, which can lag member-level rollover.
_BREADTH_DECAY_THRESHOLD = 0.40

logger = logging.getLogger(__name__)

from shared.llm_models import (
    DESCRIPTION_MODEL, THEME_ADVISOR_MODEL, THEME_MODEL,
)

# ── Shared prompt/audit string contracts ─────────────────────────────────────
# Fund/ETF description rule (BOT 2026-06-09 class) — ONE copy, interpolated into BOTH
# description-generation prompts (here + scheduler's nightly pull); both feed
# mi_ticker_overrides, so the rule must not drift between them.
FUND_EXPOSURE_PROMPT_RULE = (
    "For funds/ETFs/closed-end vehicles, describe the underlying EXPOSURE (what it "
    "invests in), not the fund mechanics — e.g. a fund buying robotics companies is "
    "'Robotics & embodied-AI exposure fund', NOT 'investment management'. The exposure "
    "is what moves the price and what themes group on."
)

# Validation audit-summary formats — shared by the EMIT sites and the #214
# inheritance-guard MATCHER (_mass_evicted_patterns). One string each, so a summary
# rewording can never silently kill the fail-open guard.
_REMOVAL_SUMMARY_FMT = "{tk} removed from '{theme}' by validation"
_MASS_REMOVAL_SUMMARY_FMT = (
    "'{theme}': validation flagged {n_flagged}/{n_members} members "
    "— name likely narrower than the cluster (#214)"
)

# Stop-words to ignore when comparing theme names for fuzzy exclusion matching
_THEME_NAME_STOP = {"and", "the", "of", "in", "for", "a", "an", "with", "by", "at", "&", "-"}


def _themes_are_related(name_a: str, name_b: str, threshold: float = 0.35) -> bool:
    """
    Return True if two theme names share enough significant words to be considered
    the same theme under a different name.

    Used for exclusion matching so that renaming "Data Center Infrastructure" to
    "AI Data Center & Cloud Infrastructure" does not bypass the exclusion for CAR.

    threshold=0.35: requires ~1 shared word out of 3 — intentionally low so that
    "Data Center Infrastructure" matches "Data Center AI & Cloud" even after a rename.
    """
    def _words(name: str) -> set[str]:
        return {
            w.lower() for w in re.split(r'[\s\-&,/()]+', name)
            if len(w) > 2 and w.lower() not in _THEME_NAME_STOP
        }

    words_a = _words(name_a)
    words_b = _words(name_b)
    if not words_a or not words_b:
        return False
    jaccard = len(words_a & words_b) / len(words_a | words_b)
    return jaccard >= threshold


def _get_excluded_tickers_for_theme(
    theme_name: str,
    all_exclusions: dict[str, set[str]],
) -> set[str]:
    """
    Return the set of tickers excluded from a given theme.
    Matches by exact name AND by fuzzy word-overlap, so exclusions survive renames.

    Example: CAR excluded from "Data Center Infrastructure" also blocks it from
    "AI Data Center & Cloud Infrastructure" (same theme, renamed by Claude).
    """
    result: set[str] = set()
    for exc_theme, exc_tickers in all_exclusions.items():
        if exc_theme == theme_name or _themes_are_related(exc_theme, theme_name):
            result |= exc_tickers
    return result


class PerplexityUnavailableError(Exception):
    """
    Raised when the Perplexity API is unavailable due to an auth failure or
    exhausted credits (HTTP 401/402). This is a HARD abort — the theme engine
    must not proceed because every news_check call will return score=0, which
    would cause smooth_delta < -8 for all themes simultaneously and flip them
    all to Fading in one run.
    """
    pass


async def _preflight_perplexity() -> None:
    """
    Probe Perplexity before the theme engine runs. Raises PerplexityUnavailableError
    on 401 (invalid key) or 402 (no credits). Network/transient errors are ignored —
    they won't cause mass Fading because individual _news_check calls return api_err=True
    which now uses a neutral score=15 instead of score=0.
    """
    ok, status_code, detail = await check_perplexity_health()
    if not ok:
        msg = (
            f"Perplexity API unavailable (HTTP {status_code}) — "
            "theme engine ABORTED to prevent mass theme collapse.\n"
            f"Detail: {detail[:200]}"
        )
        raise PerplexityUnavailableError(msg)

# Signals that indicate a Perplexity response (or stored description) is garbage
_GARBAGE_SIGNALS = [
    "no specific news", "no catalysts", "search results show",
    "search results don't", "don't provide current", "results don't provide",
    "no information", "couldn't find", "unable to find", "cannot find",
    "lack timely", "i cannot", "as of my", "no news",
    "lacks real-t", "price movements or specific catalysts",
    "does not provide", "doesn't provide",
    "i don't have", "i would need access", "i recommend checking",
    "don't have search results", "no recent market news",
]


def _extract_json_object(text: str) -> str:
    r"""
    Extract the first well-formed JSON object from text by tracking brace depth.

    The naive r'\{[^{}]*\}' regex breaks when Haiku adds nested objects such as
    {"remove": [], "notes": {"why": "..."}} because [^{}] stops at the inner brace.
    Brace-depth tracking handles arbitrary nesting and ignores braces inside strings.
    Returns the extracted substring, or the original text if no object is found
    (letting json.loads produce a clear error).
    """
    in_string = False
    escape_next = False
    depth = 0
    start = -1
    for i, ch in enumerate(text):
        if escape_next:
            escape_next = False
            continue
        if ch == "\\" and in_string:
            escape_next = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0 and start != -1:
                return text[start : i + 1]
    return text  # no balanced object found — let caller's json.loads raise


def _is_garbage(text: str) -> bool:
    """Return True if the text is a known bad/garbage description."""
    if not text:
        return False
    low = text.lower()
    return any(sig in low for sig in _GARBAGE_SIGNALS)

# Min RS composite for a stock to "count" as strong within a theme
THEME_RS_MIN = 50.0
# #476 (2026-07-17): the ASSIGNMENT candidate pool uses an RS-LEVEL floor, not a
# fixed top-N count. A fixed top-40 count floats the effective quality bar with
# how crowded the RS top is — on a bunched day (50 names ≥ RS 98) the 40th slot
# sits at RS 98.4 and genuinely-strong uncovered names (RS 82-96) are shut out
# of being assigned to the existing themes they fit. Floor+ceiling: RS ≥
# ASSIGN_POOL_RS_FLOOR among the top-ASSIGN_POOL_CEILING leaders (the ceiling
# bounds the pool on a euphoric tape). ASSIGNMENT-ONLY — discovery keeps top-40
# (it has velocity/turners/clusters for emerging names, and shouldn't
# force-cluster static-strong singletons; advisor 7/17). No-money (themes);
# reversible; verify the next nightly's assignments are sane.
ASSIGN_POOL_RS_FLOOR = 90.0
ASSIGN_POOL_CEILING = 200
# A theme is "well-covered" if >= this many of its stocks still show strong RS
THEME_COVERAGE_MIN = 3
# Retire a theme after this many consecutive fading days
FADING_RETIRE_AFTER = 5
# Min uncovered RS leaders needed to attempt new theme discovery
NEW_THEME_MIN_STOCKS = 2

# Pruning thresholds — remove weak stocks from themes
PRUNE_RS_HARD = 25.0     # RS below this → prune after 1 day (crash/scandal)
PRUNE_RS_SOFT = 35.0     # RS below this → prune after 3 consecutive days (slow decay)
PRUNE_MIN_TICKERS = 2    # Never prune a theme below this many stocks
MAX_THEMES_PER_STOCK = 2 # A stock can belong to at most 2 themes (primary + sub-theme)
MIN_SHARED_FOR_MERGE = 3 # Min |intersection| before two themes can be merged on overlap.
                         # Same gate as rs-theme-dash dedup — kills tiny-alias false positives.

# ── ADR 0032 Phase 2 — theme re-granularization, behind THEME_SUBTHEME_ARM ──
# (DB toggle `get_theme_subtheme_arm_enabled`, default OFF/fail-closed). ALL of
# these pins are ILLUSTRATIVE (design doc §1.4): the arm is OFF so they gate
# nothing today; the N≥10 backtest + operator sign-off set the real values
# before any flip. Spec: docs/analysis/theme_ecosystem_phase23_design_2026-07-14.md
SUBTHEME_C_MIN = 0.8       # T4: containment |newborn ∩ parent| / |newborn| (NOT Jaccard —
                           #     both vuln-mgmt fixtures are containment 1.0, Jaccard 0.25/0.33)
SUBTHEME_C_MULTI = 0.34    # T5: max containment vs any OTHER protected incumbent (sole-parent)
SUBTHEME_MIN_MEMBERS = 3   # T6: newborn member floor (matches _SPLIT_MIN_STOCKS)
SUBTHEME_ROUTE_CAP = 2     # T7: routed adjudications per run (every routed call consumes it)
SPLIT_DOM_MIN_MEMBERS = 10 # Route B: min members for ecosystem-dominant split eligibility
SPLIT_DOM_MIN_STRONG = 8   # Route B: min RS-80+ members
DOM_SPLITS_PER_NIGHT = 2   # Route B: global nightly cap on dominant-split nominations

# Semaphore: max concurrent Perplexity search calls (5 = ~2 rounds for 10 themes vs 4 at 3)
_SEARCH_SEM = asyncio.Semaphore(5)
# Semaphore: max concurrent FMP sector lookups
_SECTOR_SEM = asyncio.Semaphore(5)

async def _news_check(theme_name: str, tickers: list[str] | None = None) -> tuple[int, str, bool]:
    """
    Query Perplexity for current catalysts driving this theme.
    Returns (score, fresh_description, api_error).
    - score=30, api_error=False: Perplexity confirmed active catalysts
    - score=0, api_error=False: Perplexity returned but found no news
    - score=0, api_error=True: Perplexity is down/rate-limited — caller should NOT penalize theme
    """
    try:
        ticker_str = " ".join(tickers[:6]) if tickers else theme_name
        query = f"What news catalyst is driving {ticker_str} higher this week? Be concise, maximum 3 sentences."
        async with _SEARCH_SEM:
            answer = await search_news_perplexity(query, recency="week")
        if not answer:
            return 0, "", False

        # Detect Perplexity "no results" responses — store nothing, don't pollute DB
        if _is_garbage(answer):
            return 0, "", False

        # Strip citations [1][2], markdown, normalize whitespace
        clean = re.sub(r"\[\d+\]", "", answer)
        clean = re.sub(r"\*+", "", clean).replace("#", "").replace("\n", " ")
        clean = re.sub(r"\s+", " ", clean).strip()

        return 30, clean, False
    except Exception as e:
        # API error (401, network, timeout) — treat as "unknown", not "no catalysts"
        logger.warning(f"[news_check] Perplexity unavailable for '{theme_name}': {e}")
        return 0, "", True


# Cache yfinance sector lookups
_sector_cache: dict[str, str] = {}


async def _get_sector(ticker: str) -> str:
    if ticker in _sector_cache:
        return _sector_cache[ticker]
    profile = await get_fmp_profile(ticker)
    sector = profile.get("sector") or profile.get("industry") or "Unknown"
    _sector_cache[ticker] = sector
    return sector


def _all_candidate_pool(
    leaders: list[dict],
    velocity_all: list[dict] | None,
    turners_all: list[dict] | None,
) -> list[dict]:
    """Union of all discovery candidate-pool stock dicts (ADR 0007 vectors c/c2).

    Sector-enrichment and description-fetch must cover EVERY pool the discovery
    LLM can see (uncovered/velocity/turners + future accelerators), not just the
    top-60 `leaders`. A velocity/turner candidate with a blank sector is
    unclusterable, and one with no description is silently dropped from discovery
    (`_discover_new_themes` ~line 2356) — which is how the igniting drone/software
    leaders below the top-60 cut never reached clustering on 5/28 (see ADR 0007).
    """
    return [*leaders, *(velocity_all or []), *(turners_all or [])]


def _should_revive_theme(
    stage: str,
    member_rs_1m: list,
    days_since_last_revive: "int | None" = None,
    *, hot_rs_1m: float = 90.0, min_hot_members: int = 2, cooldown_days: int = 10,
) -> bool:
    """ADR 0007 (b/d): revive a Fading theme ONLY on disciplined evidence — designed to
    avoid the fade->revive->fade oscillation the 2026-05-31 replay quantified (a naive
    "any member rs_1m>=90" trigger fired on 26% of Fading-theme-days). Hysteresis:
      1. stage must be 'Fading' (nothing else revives),
      2. at least `min_hot_members` (>=2) members are hot — NOT a single transient spike
         (the 26% was single-member; requiring >=2 collapses it),
      3. not within `cooldown_days` of the last revive (one-way latch) — NOT YET WIRED:
         no last-revive timestamp is persisted on `mi_themes`, so the only caller passes
         `days_since_last_revive=None` and this arm is inert. The param is here for when
         revive goes live (persist a `revived_at`, then thread the delta in).
    NB: a 2-member Fading fragment with only ONE hot member (e.g. {KYTX,SWMR}: SWMR hot,
    KYTX cold) does NOT self-revive — it must first gain hot members via accelerator
    assignment (vector a). Revive and assignment are complementary, by design.
    """
    if stage != "Fading":
        return False
    if days_since_last_revive is not None and days_since_last_revive < cooldown_days:
        return False
    hot = sum(1 for v in member_rs_1m if v is not None and v >= hot_rs_1m)
    return hot >= min_hot_members


# ── #167 Lane-2 grouping v2 — INCREMENTAL NARRATIVE REGISTRY (operator-ruled ──
# 2026-07-27; registry reframe same day, superseding the rolling-pool draft).
# Flag: mi_safeguard_state 'lane2_grouping_v2' (db.get_lane2_grouping_v2_enabled,
# FAIL-CLOSED OFF). OFF ⇒ discover_narrative_themes is byte-identical to v1
# (pinned by tests/test_lane2_grouping_v2.py). GRADE-AFFECTING when ON — the
# lane feeds the judge's active_narratives; see the flag docstring in db.py.
#
# The registry design (replaces "re-read a 10-day pool of full documents
# nightly", which re-derived — and re-NAMED — the same dominant story every
# night: 18 of the 23 pool-replay proposals were one narrative under different
# wordings, and each near-duplicate could auto-promote into live mi_themes):
#   • STATE = the lane's own persisted output. ACTIVE narratives are the
#     latest source='narrative_cogap' row per name within the memory horizon;
#     single-name stories persist as source='narrative_seed' watch-list rows
#     (1-member; see the wall notes on get_lane2_pending_seeds).
#   • Each night the model sees ONLY today's qualifying alerts WITH full
#     evidence (grounded_text→claude_analysis→catalyst, unchanged budgets),
#     plus the compact roster (names + theses + members — never the members'
#     documents), and answers ONE question per name: JOIN an active narrative,
#     BIRTH a new theme (2+ names incl. >=1 today), or SEED the watch list.
#   • Dedup is STRUCTURAL: a continuing story is a JOIN (same name, members
#     unioned) — never a fresh proposal to be de-duplicated after the fact.
#   • Drift bounds: name+thesis are FROZEN at birth (a join can never re-write
#     the story definition, so a wrong join cannot compound semantically);
#     a join must include >=1 same-day qualifying alert (a narrative cannot be
#     kept alive by re-listing old members); members are FIFO-capped
#     (LANE2_REGISTRY_MAX_MEMBERS); an untouched narrative ages out of the
#     roster after LANE2_WINDOW_TRADING_DAYS trading days (absence-based
#     expiry, the get_active_themes(stale_after_days=…) idiom — horizon below).
LANE2_WINDOW_TRADING_DAYS = 10  # REGISTRY MEMORY HORIZON in TRADING days (roster staleness for
                                # narratives AND seeds) — operator-measured on the real cohort:
                                # WULF 07-06 → HUT/IREN 07-20 is exactly 10 trading days, and the
                                # WULF→CLSK seed link (07-06→07-14) is 8 CALENDAR days, so the
                                # theme-engine's 7-calendar-day staleness idiom would have expired
                                # the seed one day short — trading-day math at 10 is the measured
                                # minimum memory (167 audit §2/§4). NOTE: unlike the superseded
                                # fixed pool, a narrative TOUCHED by a join refreshes its
                                # last-seen, so a living story is remembered indefinitely.
LANE2_GROUNDED_BUDGET = 10000   # per-ticker chars of grounded_text — a SAFETY CEILING, in practice
                                # the FULL document (era max observed 9,615; build_grounded_text is
                                # upstream-bounded by its inputs). A head-slice budget was tested on
                                # the replay pull and FALSIFIED: the SEC/XBRL boilerplate fills the
                                # head and the linking evidence sits mid-doc (CLSK 'AI'@6394,
                                # JBL 'AI'@4430, SNX 'AI'@6593, WULF 'data center'@2653), with the
                                # story-naming web synthesis LAST in build_grounded_text's order —
                                # a 2.5k head slice re-creates the exact misses this fix targets.
                                # Cost: realistic July pools (11-18 names, all grounded) ≈ 25-35k
                                # input tokens ≈ $0.08-0.11/run at Sonnet $3/MTok; worst-case pool
                                # ≈ 60k tokens ≈ $0.18/run. Once nightly: trivial.
LANE2_ANALYSIS_BUDGET = 1500    # claude_analysis fallback cap (median 722; matches the judge
                                # payload cap in ep_grade_judge.assemble_judge_inputs).
LANE2_CATALYST_BUDGET = 500     # catalyst last resort — the column is hard-truncated at 500
                                # upstream anyway (62/62 forward-era rows, 167 audit §3).
LANE2_REGISTRY_MAX_MEMBERS = 12  # FIFO member cap per narrative — a join appends new joiners and
                                 # drops the OLDEST members past the cap, so a hot macro story
                                 # cannot accrete an unbounded cohort into the judge context or
                                 # the auto-promote path (the "ever-growing re-promoting cohort"
                                 # failure mode). 12 ≈ 2-3× the largest genuine observed cohort
                                 # (WULF/CLSK/HUT/IREN = 4).
LANE2_ROSTER_MAX = 20            # prompt-side cap on roster lines (narratives / seeds each),
                                 # most-recent first — bounds prompt growth if the registry runs
                                 # hot; ~100-150 chars/line so a full roster is ~3-6k chars.
LANE2_SEED_STORY_BUDGET = 160    # chars (~25 words) for a watch-list story line — the seed is a
                                 # LINKING HOOK for a future pairing, not an evidence store; the
                                 # full document is re-fetched from the alert row if it ever
                                 # groups.

# Narrative-definition rules shared VERBATIM by the v1 and v2 prompts. Prompt
# bias was tested and DISCONFIRMED as the primary driver of the misses (167
# audit §5) — do NOT reword these as a recall lever; the v2 levers are input
# richness and the rolling window only.
_LANE2_NARRATIVE_RULES = (
    "Themes MAY span sectors and "
    "RS levels (e.g. a government-policy theme spanning Industrials + Tech + Defense). A theme "
    "must be a real shared story/catalyst, NOT a generic sector label.\n"
    "CRITICAL: a theme is a SPECIFIC shared NARRATIVE / DRIVER (a technology cycle, a "
    "government policy, a supply shortage, a product category, a specific industry catalyst) "
    "— NOT a generic CATALYST-TYPE that names coincidentally share because of the calendar. "
    "'They all beat Q1 earnings', 'broad earnings-beat momentum', 'raised guidance', or "
    "'relief rally' are NOT themes (those are catalyst categories, not narratives). A bare "
    "one-word catchall ('AI', 'software', 'tech') is also too generic — BUT a SPECIFIC "
    "AI/tech-DRIVEN narrative IS a valid theme (e.g. 'AI-native/vertical SaaS adoption', "
    "'AI data-center buildout', 'edge-AI silicon'). Group ONLY when the names share a SPECIFIC "
    "emerging story a trader would name as a theme (e.g. 'nuclear/AI power demand', 'defense "
    "drone expansion', 'quantum computing', 'GLP-1 obesity', 'edge-AI silicon', 'AI-native SaaS'). "
    "If there is NO genuine shared narrative across 2+ of these names, return an EMPTY "
    "list — do NOT force groupings.\n\n"
)
_LANE2_JSON_CONTRACT = (
    'Return ONLY JSON: {"themes":[{"name":"<=6 words","catalyst_type":"theme|govt_policy|shortage|'
    'sales_acceleration|new_product|management_change|other","tickers":["TICK","TICK"],"thesis":"one sentence"}]}. '
)
_LANE2_NAME_BREADTH_RULE = (
    "The name's breadth must match the group: every grouped ticker must individually fit the name."
)
_LANE2_REGISTRY_JSON_CONTRACT = (
    'Return ONLY JSON: {"themes":[{"name":"<=6 words","catalyst_type":"theme|govt_policy|shortage|'
    'sales_acceleration|new_product|management_change|other","tickers":["TICK","TICK"],'
    '"thesis":"one sentence"}],"seeds":[{"ticker":"TICK","story":"<=25 words"}]}. '
)


def _lane2_window_start(scan_date):
    """First alert_date inside the v2 window: scan_date minus
    LANE2_WINDOW_TRADING_DAYS trading days. Uses the repo's weekend-skipping
    prev_trading_days helper (holidays inside the window shrink the effective
    count by one — same approximation every other caller accepts). ET-frame
    dates only; callers pass et_today()-derived dates, never date.today()."""
    from agents.market_intelligence.collector import prev_trading_days
    return prev_trading_days(LANE2_WINDOW_TRADING_DAYS, from_date=scan_date)[-1]


def _lane2_qualifies(a: dict) -> bool:
    """SAME qualifying rule as v1 (ep>=50 + catalyst-or-claude_analysis) — v2
    changes the text FED and the window, never the population definition, so
    replay populations stay comparable with the 167 audit's 62-alert cohort."""
    return (a.get("ep_score") or 0) >= 50.0 and bool(a.get("catalyst") or a.get("claude_analysis"))


def _lane2_input_text(a: dict) -> tuple[str, str]:
    """Evidence text for one pooled alert + its source tag.
    Priority (operator ruling 1): grounded_text (SEC-8K-grounded body, 81%
    coverage, budgeted) → claude_analysis (grounded when a direct source
    exists, #360) → catalyst (100% hard-truncated Perplexity preamble — last
    resort). Whitespace is collapsed so each pool entry stays one prompt line.
    The tag feeds the audit summary so a degraded (fallback-heavy) day is
    distinguishable from a rich one."""
    for field, budget, tag in (
        ("grounded_text", LANE2_GROUNDED_BUDGET, "grounded"),
        ("claude_analysis", LANE2_ANALYSIS_BUDGET, "analysis"),
        ("catalyst", LANE2_CATALYST_BUDGET, "catalyst"),
    ):
        v = a.get(field)
        if v and str(v).strip():
            return " ".join(str(v)[:budget].split()), tag
    return "", "none"


def _norm_narrative_name(name: str) -> str:
    """Canonical form for narrative-name matching (JOIN detection): lowercase,
    every non-alphanumeric run collapsed to one space. Catches the observed
    drift classes — case, hyphen-vs-space ("data-center"/"data center"),
    stray punctuation — WITHOUT any fuzzy matching (a semantically different
    wording is deliberately NOT a match; the model is instructed to reuse the
    exact roster name, and a missed join surfaces in the replay/audit rather
    than being force-merged)."""
    return re.sub(r"[^a-z0-9]+", " ", str(name).lower()).strip()


def _build_lane2_registry_prompt(
    today: list[dict], active: list[dict], seeds: list[dict],
) -> str:
    """v2 REGISTRY prompt: today's qualifying alerts with full budgeted
    evidence, plus the compact state — ACTIVE narratives (name + members +
    last-seen + frozen thesis) and the single-name WATCH LIST. Cold start
    (both rosters empty) simply omits the state blocks: the prompt degrades to
    v1-plus-seeds. Narrative-definition rules are the shared
    _LANE2_NARRATIVE_RULES verbatim (prompt bias was tested and DISCONFIRMED
    as a recall lever — do not reword them)."""
    lines = []
    for a in today:
        text, _src = _lane2_input_text(a)
        lines.append(f"- {a['ticker']} (gap {a.get('gap_pct','?')}%, ep {a.get('ep_score')}): {text}")
    roster = ""
    if active:
        roster += "ACTIVE tracked narratives (from prior sessions):\n" + "\n".join(
            f'- "{n["name"]}" [members: {", ".join(n.get("tickers") or [])}; '
            f'last seen {n["run_date"]}]: {" ".join(str(n.get("thesis") or "").split())[:300]}'
            for n in active
        ) + "\n\n"
    if seeds:
        roster += "WATCH LIST (recent single-name stories, no cohort yet):\n" + "\n".join(
            f'- {s["ticker"]} ({s["run_date"]}): {s["story"]}' for s in seeds
        ) + "\n\n"
    return (
        "Below are TODAY's gap-up momentum stocks and their catalyst evidence. For each, decide "
        "whether it CONTINUES one of the ACTIVE tracked narratives, forms a NEW theme that 2 OR "
        "MORE names genuinely SHARE, or stands alone. "
        + _LANE2_NARRATIVE_RULES
        + roster
        + "Stocks TODAY:\n" + "\n".join(lines) + "\n\n"
        + _LANE2_REGISTRY_JSON_CONTRACT
        + "JOIN: if a TODAY stock continues the SAME underlying story as an ACTIVE narrative, "
        "return that narrative's name EXACTLY as listed; tickers = only the names joining it now "
        "(TODAY's, plus any WATCH LIST names sharing the story). NEVER re-propose an active "
        "narrative's story under new wording. "
        "NEW: mint a new name ONLY for a story no ACTIVE narrative covers; it needs 2+ tickers "
        "drawn from TODAY's stocks and the WATCH LIST, at least one from TODAY. "
        "SEEDS: each TODAY stock with a REAL specific story that joins nothing and pairs with "
        "nothing -> one seeds entry (<=25-word story); omit stocks with no specific story. "
        + _LANE2_NAME_BREADTH_RULE
    )


def _lane2_registry_clean(
    themes: list[dict],
    raw_seeds: list[dict],
    active: list[dict],
    offered_seeds: list[dict],
    today_set: set[str],
) -> tuple[list[dict], list[dict], list[tuple[str, str]]]:
    """Deterministic post-parse enforcement for the registry mode. Pure
    function (unit-tested directly; the replay exercises the same code).

    JOIN (model reused a roster name, matched via _norm_narrative_name):
      • identity is FROZEN — name and thesis come from the REGISTRY row, never
        the model's re-wording (a wrong join can't rewrite the story, so drift
        cannot compound);
      • additions = listed tickers that qualify TODAY or sit on the offered
        watch list; a join with NO same-day addition is DROPPED (a narrative
        cannot be kept alive by re-listing old members — staleness must bite);
      • members = registry members + additions appended in listing order,
        FIFO-trimmed to LANE2_REGISTRY_MAX_MEMBERS (oldest drop first).
    NEW: tickers filtered to today ∪ watch list; needs >=2 members and >=1
      TODAY anchor, else dropped (hallucinated tickers can't pad a cohort).
    Same-run collapse: two model themes resolving to the same canonical name
      (join or birth) merge into ONE entry — structural dedup, no heuristics.
    Overlap TRIPWIRE (surface, never rule): a NEW theme sharing >=2 members
      with an active narrative is flagged for the operator (possible duplicate
      the model failed to join) but persisted UNMERGED — over-merging two
      genuinely distinct stories on the same cohort (e.g. a miners' halving
      squeeze vs the miners' AI pivot) is as bad as under-merging.
    SEEDS: kept only for TODAY-qualifying tickers that were not placed in any
      theme tonight and are not already members of an active narrative;
      whitespace-collapsed, budgeted to LANE2_SEED_STORY_BUDGET.

    Returns (clean_themes, new_seeds, possible_dups) where possible_dups is
    [(new_name, existing_name), …]."""
    by_norm = {_norm_narrative_name(n["name"]): n for n in active}
    seed_tk = {s["ticker"] for s in offered_seeds}
    entries: dict[str, dict] = {}  # canonical-norm-name -> entry (insertion-ordered)
    for t in (themes or []):
        nm = str(t.get("name") or "").strip()
        raw_tks = [x for x in (t.get("tickers") or []) if isinstance(x, str)]
        if not nm or not raw_tks:
            continue
        reg = by_norm.get(_norm_narrative_name(nm))
        if reg is not None:
            additions = [tk for tk in dict.fromkeys(raw_tks)
                         if tk in today_set or tk in seed_tk]
            if not (set(additions) & today_set):
                continue  # join needs fresh same-day evidence — never a re-listing touch
            key = _norm_narrative_name(reg["name"])
            e = entries.get(key)
            if e is None:
                e = {"name": str(reg["name"])[:80],
                     "tickers": list(dict.fromkeys(reg.get("tickers") or [])),
                     "thesis": str(reg.get("thesis") or "")[:500],
                     "catalyst_type": t.get("catalyst_type"),
                     "joined": True}
                entries[key] = e
            for tk in additions:
                if tk not in e["tickers"]:
                    e["tickers"].append(tk)
        else:
            tks = [tk for tk in dict.fromkeys(raw_tks)
                   if tk in today_set or tk in seed_tk]
            if len(tks) < 2 or not (set(tks) & today_set):
                continue
            key = _norm_narrative_name(nm)
            e = entries.get(key)
            if e is None:
                entries[key] = {"name": nm[:80], "tickers": tks,
                                "thesis": str(t.get("thesis") or "")[:500],
                                "catalyst_type": t.get("catalyst_type"),
                                "joined": False}
            else:
                for tk in tks:
                    if tk not in e["tickers"]:
                        e["tickers"].append(tk)
    clean: list[dict] = []
    possible_dups: list[tuple[str, str]] = []
    for e in entries.values():
        if len(e["tickers"]) > LANE2_REGISTRY_MAX_MEMBERS:
            e["tickers"] = e["tickers"][-LANE2_REGISTRY_MAX_MEMBERS:]
        if not e["joined"]:
            for nrow in active:
                if len(set(e["tickers"]) & set(nrow.get("tickers") or [])) >= 2:
                    possible_dups.append((e["name"], nrow["name"]))
        clean.append(e)
    placed = {tk for e in clean for tk in e["tickers"]}
    member_set = {tk for n in active for tk in (n.get("tickers") or [])}
    new_seeds: list[dict] = []
    seen: set[str] = set()
    for s in (raw_seeds or []):
        tk = s.get("ticker")
        story = " ".join(str(s.get("story") or "").split())
        if (tk in today_set and tk not in placed and tk not in member_set
                and tk not in seen and story):
            new_seeds.append({"ticker": tk, "story": story[:LANE2_SEED_STORY_BUDGET]})
            seen.add(tk)
    return clean, new_seeds, possible_dups


async def discover_narrative_themes(scan_date=None, persist: bool = True, backfilled: bool = False) -> dict:
    """C2/C3 rung-1 NARRATIVE-theme discovery (#167, shadow/advisory).

    Groups EP alerts by SHARED CATALYST-NARRATIVE via one Sonnet call and
    writes proposals to `mi_theme_candidates_shadow` (source='narrative_cogap').
    Catches cross-sector / govt-policy themes the RS+correlation engine structurally
    misses — validated on the 2026-05-28 drone cohort (step-b + the §5 PASS, 6/2).
    Advisory ONLY: no live `mi_themes` mutation; operator confirms before
    canonization — but NOTE the proposals DO feed the judge's active_narratives
    context (get_narrative_theme_candidates → assemble_judge_inputs), so what
    this lane proposes is GRADE-AFFECTING (db.get_lane2_grouping_v2_enabled).

    Two modes, selected per-run by the 'lane2_grouping_v2' DB flag (fail-closed):
    - v1 (flag OFF, the default — byte-identical to pre-flag behavior, pinned
      by tests/test_lane2_grouping_v2.py): today's alerts only, catalyst[:280].
    - v2 (#167 REGISTRY mode, operator-ruled 2026-07-27): incremental,
      state-carrying — today's qualifying alerts with budgeted
      grounded_text→claude_analysis→catalyst evidence, evaluated against the
      lane's own ACTIVE-narrative roster + single-name watch list
      (_discover_lane2_registry; design notes at the LANE2_* constants).

    FULLY error-wrapped — never raises into the caller (the nightly pull).
    """
    import json
    from agents.market_intelligence.collector import et_today
    from agents.market_intelligence.db import (
        get_today_ep_alerts, persist_narrative_theme_candidates,
        log_audit_event, get_lane2_grouping_v2_enabled,
    )
    out = {"date": None, "alerts": 0, "themes": 0, "names": [], "error": None}
    try:
        scan_date = scan_date or et_today()
        out["date"] = scan_date if isinstance(scan_date, str) else scan_date.strftime("%Y-%m-%d")
        v2 = await get_lane2_grouping_v2_enabled()
        if v2:
            return await _discover_lane2_registry(
                scan_date, out, persist=persist, backfilled=backfilled)
        alerts = await get_today_ep_alerts(scan_date)
        cand = [a for a in alerts
                if (a.get("ep_score") or 0) >= 50.0 and (a.get("catalyst") or a.get("claude_analysis"))]
        out["alerts"] = len(cand)
        if len(cand) < 2:
            await log_audit_event("narrative_theme_discovery_ran",
                                  f"{out['date']}: {len(cand)} qualifying alert(s) (<2) — no grouping")
            return out
        lines = []
        for a in cand:
            cat = (a.get("catalyst") or a.get("claude_analysis") or "")[:280]
            lines.append(f"- {a['ticker']} (gap {a.get('gap_pct','?')}%, ep {a.get('ep_score')}): {cat}")
        prompt = (
            "Below are today's gap-up momentum stocks and their catalysts. Identify EMERGING "
            "NARRATIVE THEMES that 2 OR MORE of them genuinely SHARE. "
            + _LANE2_NARRATIVE_RULES
            + "Stocks:\n" + "\n".join(lines) + "\n\n"
            + _LANE2_JSON_CONTRACT
            + "Include a theme ONLY if 2+ of the listed tickers truly share it; otherwise themes=[]. "
            + _LANE2_NAME_BREADTH_RULE
        )
        client = _get_anthropic_client()
        msg = await client.messages.create(
            model=THEME_MODEL, max_tokens=1500,
            messages=[{"role": "user", "content": prompt}],
        )
        # S2/F9: safe wrapper — see spend_tracker.log_anthropic_call_safe
        from agents.market_intelligence.spend_tracker import log_anthropic_call_safe
        await log_anthropic_call_safe(model=THEME_MODEL, caller="narrative_theme_discovery",
                                       usage=getattr(msg, "usage", None))
        raw = _extract_json_object(msg.content[0].text if msg.content else "")
        parsed = json.loads(raw)
        themes = parsed.get("themes", []) if isinstance(parsed, dict) else []
        cand_tk = {a["ticker"] for a in cand}
        clean = []
        for t in (themes or []):
            tks = [x for x in (t.get("tickers") or []) if x in cand_tk]
            if not (t.get("name") and len(tks) >= 2):
                continue
            clean.append({"name": str(t["name"])[:80], "tickers": tks,
                          "thesis": (t.get("thesis") or "")[:500],
                          "catalyst_type": t.get("catalyst_type")})
        n = (await persist_narrative_theme_candidates(scan_date, clean, backfilled=backfilled)) if persist else len(clean)
        out["themes"] = n
        out["names"] = [t["name"] for t in clean]
        await log_audit_event("narrative_theme_discovery_ran",
                              f"{out['date']}: {len(cand)} alerts -> {n} narrative theme(s): {out['names']}")
        return out
    except Exception as e:
        # #376: a credit-exhaustion failure here silently yields no narrative
        # themes — alert it (deduped) before the fail-open.
        from agents.market_intelligence.llm_health import maybe_alert_credit_exhausted
        await maybe_alert_credit_exhausted("narrative theme discovery", e)
        logger.warning(f"discover_narrative_themes failed: {e}", exc_info=True)
        try:
            await log_audit_event("narrative_theme_discovery_failed", f"{out.get('date')}: {str(e)[:200]}")
        except Exception:
            pass
        out["error"] = str(e)[:200]
        return out


async def _discover_lane2_registry(
    scan_date, out: dict, *, persist: bool, backfilled: bool,
) -> dict:
    """#167 Lane-2 v2 REGISTRY mode (design notes at the LANE2_* constants).
    Called ONLY from discover_narrative_themes with the flag ON; runs inside
    its caller's try/except (any raise lands in the shared fail-open path).

    Nightly shape: fetch TODAY's qualifying alerts (same population rule as
    v1) → read the lane's own state (ACTIVE narratives + watch-list seeds,
    both windowed to LANE2_WINDOW_TRADING_DAYS trading days, PRIOR sessions
    only) → one Sonnet call (today's full evidence + compact roster) →
    _lane2_registry_clean enforcement → persist themes (narrative_cogap) and
    seeds (narrative_seed; skipped on backfill runs so hindsight rows can
    never enter the forward watch list).

    ANTI-CIRCULARITY: the roster readers are hard-scoped to the lane's own
    sources ('narrative_cogap' / 'narrative_seed') — judge_inferred and
    coverage_probe rows can never enter this prompt, so the judge's own
    inferences cannot reach the judge's active_narratives via this lane
    (the judge_theme_gap.py wall, preserved by construction).

    AUTO-PROMOTE interaction (narrative_cogap IS allowlisted): a JOIN writes
    a new (run_date=today, name) row, so get_shadow_theme_candidates'
    DISTINCT ON (name) sees ONE cohort per story — never a fresh near-
    duplicate name per night. A narrative re-enters the promote window only
    while genuinely touched (join = fresh same-day alert), its membership is
    FIFO-capped, and an untouched narrative leaves the roster after the
    horizon and live mi_themes via the 7d recency cap — bounded, not
    ever-growing. Seeds are 1-member rows under a NON-allowlisted source:
    structurally below _PROMOTE_MIN_MEMBERS AND outside both walls."""
    import json
    from datetime import date as _date
    from agents.market_intelligence.db import (
        get_today_ep_alerts, get_lane2_active_narratives, get_lane2_pending_seeds,
        persist_narrative_theme_candidates, persist_lane2_seeds, log_audit_event,
    )
    scan_d = _date.fromisoformat(scan_date) if isinstance(scan_date, str) else scan_date
    alerts = await get_today_ep_alerts(scan_d)
    cand = [a for a in alerts if _lane2_qualifies(a)]
    src_counts = {"grounded": 0, "analysis": 0, "catalyst": 0, "none": 0}
    for a in cand:
        src_counts[_lane2_input_text(a)[1]] += 1
    out["alerts"] = len(cand)
    out["input_sources"] = src_counts
    window_start = _lane2_window_start(scan_d)
    active = await get_lane2_active_narratives(window_start, scan_d)
    seeds = await get_lane2_pending_seeds(window_start, scan_d)
    # Roster hygiene (deterministic, here so live and replay share it):
    # a seed whose ticker already sits in an active narrative is consumed;
    # a seed alerting again TODAY is superseded by its own fresh evidence line.
    member_set = {tk for n in active for tk in (n.get("tickers") or [])}
    today_set = {a["ticker"] for a in cand}
    seeds = [s for s in seeds
             if s["ticker"] not in member_set and s["ticker"] not in today_set]
    active = active[:LANE2_ROSTER_MAX]
    seeds = seeds[:LANE2_ROSTER_MAX]
    out["registry"] = {"active": len(active), "seeds": len(seeds)}
    if not cand:
        await log_audit_event(
            "narrative_theme_discovery_ran",
            f"{out['date']}: v2reg 0 qualifying today — no evaluation "
            f"(roster {len(active)} active / {len(seeds)} seeds)")
        return out
    prompt = _build_lane2_registry_prompt(cand, active, seeds)
    out["prompt_chars"] = len(prompt)
    client = _get_anthropic_client()
    msg = await client.messages.create(
        model=THEME_MODEL, max_tokens=1500,
        messages=[{"role": "user", "content": prompt}],
    )
    # S2/F9: safe wrapper — see spend_tracker.log_anthropic_call_safe
    from agents.market_intelligence.spend_tracker import log_anthropic_call_safe
    await log_anthropic_call_safe(model=THEME_MODEL, caller="narrative_theme_discovery",
                                   usage=getattr(msg, "usage", None))
    usage = getattr(msg, "usage", None)
    if usage is not None and getattr(usage, "input_tokens", None) is not None:
        out["usage"] = {"input_tokens": usage.input_tokens,
                        "output_tokens": getattr(usage, "output_tokens", None)}
    raw = _extract_json_object(msg.content[0].text if msg.content else "")
    parsed = json.loads(raw)
    themes = parsed.get("themes", []) if isinstance(parsed, dict) else []
    raw_seeds = parsed.get("seeds", []) if isinstance(parsed, dict) else []
    clean, new_seeds, possible_dups = _lane2_registry_clean(
        themes, raw_seeds, active, seeds, today_set)
    for born_name, existing_name in possible_dups:
        await log_audit_event(
            "lane2_possible_duplicate_narrative",
            f"{out['date']}: new '{born_name}' shares >=2 members with active "
            f"'{existing_name}' — surfaced for operator review, NOT auto-merged")
    n = (await persist_narrative_theme_candidates(scan_d, clean, backfilled=backfilled)) if persist else len(clean)
    ns = (await persist_lane2_seeds(scan_d, new_seeds)) if (persist and not backfilled) else len(new_seeds)
    joined_names = [e["name"] for e in clean if e["joined"]]
    born_names = [e["name"] for e in clean if not e["joined"]]
    out["themes"] = n
    out["names"] = [e["name"] for e in clean]
    out["joined"] = joined_names
    out["born"] = born_names
    out["seeds"] = ns
    # Full per-proposal detail — the replay chains its in-memory registry off
    # these exact fields, so replay state evolves precisely as prod rows would.
    out["proposals"] = [{"name": e["name"], "tickers": list(e["tickers"]),
                         "thesis": e["thesis"], "joined": e["joined"]} for e in clean]
    out["new_seeds"] = new_seeds
    await log_audit_event(
        "narrative_theme_discovery_ran",
        f"{out['date']}: v2reg {len(cand)} today (grounded={src_counts['grounded']} "
        f"analysis={src_counts['analysis']} catalyst={src_counts['catalyst']}) "
        f"roster {len(active)} active / {len(seeds)} seeds -> "
        f"{len(joined_names)} join + {len(born_names)} new + {ns} seed(s): {out['names']}")
    return out


async def evaluate_narrative_themes(days: int = 30, include_backfill: bool = False) -> list[dict]:
    """#167 eval-harness — score the accrued narrative_cogap proposals for the
    promote-gate (data_gated_reviews::narrative_theme_discovery_promote_gate).
    Read-only. Each proposal is enriched with:
      live_unified   — does any SINGLE live theme already group >=2 of these
                       members? False = live did NOT recognize the cohort (the
                       recall value: narrative-discovery unifies what the
                       RS+sector engine fragments — the drone class).
      fwd_5d/10d_pct — fixed-horizon (run_date-anchored) avg member return; None
                       when the proposal is < ~1 trading week old (pending).
      pending        — True when too fresh for a forward read.
      backfilled     — True for the hindsight backfill population (#167
                       segregation). NOTE: on a backfilled row the run_date-anchored
                       forward returns are honest price action, but `live_unified`
                       (scored vs TODAY's themes) is ANACHRONISTIC — so the recall
                       signal is the hindsight-exposed one. The harness SURFACES
                       both nulls neither; the operator splits by `backfilled` at
                       the 6/23 gate (surface-not-prescribe).
    include_backfill=False (default) returns the forward population only, BY
    CONSTRUCTION (source-scoped), so /themes stays hindsight-free.
    """
    from agents.market_intelligence.db import (
        get_pool, get_narrative_theme_candidates, get_active_themes,
    )
    from agents.market_intelligence.collector import et_today

    proposals = await get_narrative_theme_candidates(days, include_backfill=include_backfill)
    if not proposals:
        return []
    live = await get_active_themes()
    live_sets = [set(t.get("tickers") or []) for t in live]
    today = et_today()
    pool = await get_pool()
    out = []
    for p in proposals:
        members = p.get("tickers") or []
        mset = set(members)
        # recall: did any single live theme already group >=2 of these members?
        live_unified = any(len(mset & ts) >= 2 for ts in live_sets)
        run_date = p["run_date"]
        days_elapsed = (today - run_date).days
        # #167 rework: FIXED-horizon forward returns. The old "latest close /
        # base" measured each proposal over a different elapsed window (older =
        # longer = looks better) — not comparable across proposals at the gate.
        # Measure every proposal at the SAME 5d and 10d horizon from run_date.
        # Batched: ONE query per proposal over all members (was N+1 per member).
        fwd5_rets: list[float] = []
        fwd10_rets: list[float] = []
        if members and days_elapsed >= 7:  # >=~5 trading days → 5d readable
            async with pool.acquire() as conn:
                rows = await conn.fetch(
                    """
                    SELECT b.close AS base, f5.close AS fwd5, f10.close AS fwd10
                    FROM unnest($1::text[]) AS t(ticker)
                    LEFT JOIN LATERAL (
                        SELECT close FROM mi_daily_closes
                        WHERE ticker = t.ticker AND trade_date <= $2
                        ORDER BY trade_date DESC LIMIT 1) b ON TRUE
                    LEFT JOIN LATERAL (
                        SELECT close FROM mi_daily_closes
                        WHERE ticker = t.ticker AND trade_date > $2
                        ORDER BY trade_date ASC OFFSET 4 LIMIT 1) f5 ON TRUE
                    LEFT JOIN LATERAL (
                        SELECT close FROM mi_daily_closes
                        WHERE ticker = t.ticker AND trade_date > $2
                        ORDER BY trade_date ASC OFFSET 9 LIMIT 1) f10 ON TRUE
                    """,
                    members, run_date,
                )
            for r in rows:
                if r["base"] and r["fwd5"]:
                    fwd5_rets.append((float(r["fwd5"]) / float(r["base"]) - 1) * 100)
                if r["base"] and r["fwd10"]:
                    fwd10_rets.append((float(r["fwd10"]) / float(r["base"]) - 1) * 100)
        fwd_5d = round(sum(fwd5_rets) / len(fwd5_rets), 1) if fwd5_rets else None
        fwd_10d = round(sum(fwd10_rets) / len(fwd10_rets), 1) if fwd10_rets else None
        out.append({
            "name": p["name"],
            "run_date": run_date,
            "tickers": members,
            "live_unified": live_unified,
            "fwd_5d_pct": fwd_5d,
            "fwd_10d_pct": fwd_10d,
            "avg_return_pct": fwd_5d,  # back-compat alias (now fixed-5d horizon)
            "pending": fwd_5d is None,
            "backfilled": bool(p.get("backfilled")),
        })
    return out


async def run_theme_discovery_shadow(today=None, clusters=None) -> dict:
    """ADR 0007 SHADOW PASS — DRAFT 2026-05-31; VERIFY + TUNE MONDAY on the server.

    Runs the NEW nascent-discovery selectors (a/a2) on top of the widened assembly
    (c/c2) through the EXISTING discovery prompt, and writes PROPOSED themes to
    `mi_theme_candidates_shadow` — WITHOUT touching live `mi_themes` / the brief.
    (b/d) revive is computed as a `would_revive` FLAG only (not applied). The (f)
    ignition prompt is a LATER shadow iteration — this baseline first isolates whether
    the selector + assembly fixes ALONE surface the cohorts.

    *** CANNOT be unit-tested locally (needs DB + LLM). MONDAY VERIFY CHECKLIST: ***
      1. `get_rs_accelerators` / `get_rs_recovery_slope` return sane rows on fresh data.
      2. the drone + software cohorts now ENTER `uncovered` (Step-1 recall, read the logs).
      3. shadow themes form; count themes-formed (Step-3 flood check). NB this is NOT
         apples-to-apples vs live `mi_themes`: the shadow assembly deliberately skips the
         live assignment-pass (`_assign_uncovered_to_themes`), the global-ban, and the
         carryforward strip, so shadow `uncovered` is systematically LARGER and it will
         over-form themes. Read the count as "selector recall + headroom", NOT as "live
         would have formed N" — for that comparison, add those filters to the shadow path.
      4. eyeball `mi_theme_candidates_shadow` for a drone/software theme that live missed.
      5. THEN iterate: add the (f) ignition-prompt variant + A/B vs this baseline;
         only after the N-night diff looks right, wire into the 5 PM nightly job + promote.
    Run manually first (NOT cron-wired yet — verify-before-cron):
      `python -c "import asyncio; from agents.market_intelligence.theme_engine import run_theme_discovery_shadow; print(asyncio.run(run_theme_discovery_shadow()))"`
    """
    from agents.market_intelligence.collector import et_today
    from agents.market_intelligence.db import (
        get_rs_leaders, get_rs_velocity, get_rs_turners,
        get_rs_accelerators, get_rs_recovery_slope,
        get_active_themes, persist_theme_candidates_shadow,
        log_audit_event,
    )
    today = today or et_today()
    today_str = today if isinstance(today, str) else today.strftime("%Y-%m-%d")

    # 1. base pools (same as live) + the NEW selectors (a/a2) — one gather; all five
    #    queries are independent, so there's nothing to serialize across two awaits.
    leaders, velocity_all, turners_all, accelerators, recovery = await asyncio.gather(
        get_rs_leaders(today_str, limit=60),
        get_rs_velocity(today_str, min_rs=THEME_RS_MIN, limit=30),
        get_rs_turners(today_str, max_rs_4w_ago=30.0, min_consecutive_weeks=3, limit=30),
        get_rs_accelerators(today_str),
        get_rs_recovery_slope(today_str),
    )
    if not leaders:
        logger.warning("[theme shadow] no RS data — skipping")
        return {"skipped": "no_rs_data"}

    # 2. enrich sector + descriptions for ALL pools incl. the new selectors (c/c2)
    _pool = _all_candidate_pool(leaders, velocity_all, turners_all) + list(accelerators) + list(recovery)

    async def _enrich(s: dict) -> None:
        if not s.get("sector"):
            async with _SECTOR_SEM:
                s["sector"] = await _get_sector(s["ticker"])
    await asyncio.gather(*[_enrich(s) for s in _pool])
    await _ensure_descriptions(list({s["ticker"] for s in _pool}))

    # 3. existing themes — context + covered set + revive flags
    existing = await get_active_themes()
    covered = {tk for t in existing if t.get("stage") != "Fading" for tk in (t.get("tickers") or [])}

    # 4. candidate pools for discovery (the NEW selectors fold into `uncovered`)
    stocks_by_ticker: dict = {}
    for s in _pool:
        stocks_by_ticker.setdefault(s["ticker"], s)
    _seen: set = set()
    uncovered = []
    for s in [*leaders[:40], *accelerators, *recovery]:
        tk = s["ticker"]
        if tk in covered or tk in _seen:
            continue
        if (s.get("rs_composite") or s.get("rs_now") or 0) >= THEME_RS_MIN:
            _seen.add(tk)
            uncovered.append(s)
    velocity_leaders = [s for s in velocity_all if s["ticker"] not in covered]
    turners = [s for s in turners_all if s["ticker"] not in covered]

    # 5. discovery — EXISTING prompt (baseline; (f) ignition variant is a Monday A/B step)
    new_raw = await _discover_new_themes(
        uncovered, existing, stocks_by_ticker,
        velocity_leaders=velocity_leaders, turners=turners,
        correlation_clusters=clusters, recall_mode=True,
    )

    # 6. (b/d) would_revive flags — computed only, NOT applied to live mi_themes
    would_revive: dict = {}
    for t in existing:
        if t.get("stage") == "Fading":
            rs1m = [stocks_by_ticker.get(tk, {}).get("rs_1m") for tk in (t.get("tickers") or [])]
            would_revive[t["name"]] = _should_revive_theme("Fading", rs1m)

    # 7. persist to the SHADOW table (never mi_themes / the brief)
    n = await persist_theme_candidates_shadow(today, new_raw, would_revive)
    summary = {
        "shadow_themes": n,
        "would_revive": sum(1 for v in would_revive.values() if v),
        "accelerators": len(accelerators), "recovery_slope": len(recovery),
        "uncovered_in": len(uncovered),
    }
    logger.info(f"[theme shadow] {summary}")
    # Audit the outcome so a 0-row run is never silent again (#173 wrote 0 rows for days
    # with only an INFO log that rotated out on each container restart).
    try:
        await log_audit_event(
            "theme_discovery_shadow_ran",
            summary=f"Theme discovery shadow: {n} candidate themes written",
            detail=str(summary),
        )
    except Exception:
        pass
    return summary


async def _ensure_descriptions(tickers: list[str]) -> None:
    """
    For any ticker missing a trading-relevant description, fetch from yfinance
    and generate a concise one via Claude Haiku. Persists to DB and updates
    TICKER_DESC in memory so clustering can use it immediately.

    Stocks that still have no description after the fetch attempt are logged —
    they will be excluded from clustering rather than clustered blind.
    """
    from agents.market_intelligence.universe import TICKER_DESC, apply_overrides, _STATIC_BASELINE
    from agents.market_intelligence.db import upsert_ticker_overrides_batch

    # Skip tickers with static hardcoded descriptions — even if a bad DB row has
    # overwritten the in-memory entry, we must not re-generate (and re-corrupt) them.
    # Static entries in universe.py are authoritative and should never be touched here.
    missing = [t for t in tickers if not TICKER_DESC.get(t) and t not in _STATIC_BASELINE]
    if not missing:
        return

    logger.info(f"[theme descriptions] {len(missing)} stocks missing descriptions, fetching: {missing}")

    # Fetch yfinance profiles concurrently
    sem = asyncio.Semaphore(5)
    profiles: dict[str, dict] = {}

    async def _fetch(ticker: str) -> None:
        async with sem:
            profiles[ticker] = await get_fmp_profile(ticker)

    await asyncio.gather(*[_fetch(t) for t in missing])

    # Build prompt for Claude Haiku — same style as scheduler step 4a
    stock_lines = []
    to_describe = []
    for tk in missing:
        p = profiles.get(tk, {})
        name = p.get("companyName", tk)
        industry = p.get("industry", "")
        biz = p.get("description", "")[:200]
        if not (name or industry or biz):
            logger.warning(f"[theme descriptions] {tk}: no profile data from yfinance — will be excluded from clustering")
            continue
        to_describe.append(tk)
        stock_lines.append(f"- {tk}: {name}. Industry: {industry}. {biz}")

    if not stock_lines:
        return

    PROMPT_PREFIX = (
        "Generate concise trading-relevant descriptions for these stocks.\n\n"
        "Rules:\n"
        "- 3-8 words describing the PRIMARY revenue driver only\n"
        "- Ignore 'digital transformation', 'technology investments', 'platform initiatives' "
        "unless that IS the core business\n"
        "- A car rental company is 'car & truck rental', NOT 'mobility platform'\n"
        "- A retailer is 'retail stores / e-commerce', NOT 'digital commerce platform'\n"
        "- Focus on what they SELL, not how they describe themselves in PR\n\n"
        "Examples:\n"
        "- NVDA: AI/data center GPUs, inference & training chips\n"
        "- MU: DRAM & NAND memory, HBM for AI GPUs\n"
        "- FCX: Copper & gold mining\n"
        "- AGRO: Agricultural farming, sugar, ethanol production\n"
        "- CAR: Car & truck rental (Avis, Budget brands)\n"
        "- UBER: Rideshare & food delivery marketplace\n\n"
        + FUND_EXPOSURE_PROMPT_RULE + "\n\n"
        "Return ONLY a JSON object mapping ticker to description. No markdown, no explanation.\n\n"
        "Stocks:\n"
    )

    # Chunk to ≤15 tickers — Haiku silently drops tickers on large batches
    CHUNK_SIZE = 15
    client = _get_anthropic_client()
    all_valid: dict[str, str] = {}

    for chunk_start in range(0, len(stock_lines), CHUNK_SIZE):
        chunk_lines = stock_lines[chunk_start:chunk_start + CHUNK_SIZE]
        chunk_tickers = to_describe[chunk_start:chunk_start + CHUNK_SIZE]
        try:
            resp = await client.messages.create(
                model=DESCRIPTION_MODEL,
                max_tokens=500,
                messages=[{"role": "user", "content": PROMPT_PREFIX + "\n".join(chunk_lines)}],
            )
            # S2/F9: safe wrapper — see spend_tracker.log_anthropic_call_safe
            from agents.market_intelligence.spend_tracker import log_anthropic_call_safe
            await log_anthropic_call_safe(model=DESCRIPTION_MODEL, caller="theme_descriptions",
                                           usage=getattr(resp, "usage", None))
            raw = resp.content[0].text.strip()
            if raw.startswith("```"):
                raw = raw.split("\n", 1)[1] if "\n" in raw else raw[3:]
                raw = raw.rstrip("```").strip()
            m = re.search(r'\{.*\}', raw, re.DOTALL)
            raw = m.group(0) if m else raw
            desc_map = json.loads(raw)
            if isinstance(desc_map, dict):
                for tk, desc in desc_map.items():
                    tk_up = tk.upper()
                    if not isinstance(desc, str) or not desc or tk_up not in chunk_tickers:
                        continue
                    p = profiles.get(tk_up, {})
                    sector = p.get("sector", "")
                    industry = p.get("industry", "")
                    if sector and industry and sector != industry:
                        all_valid[tk_up] = f"{sector} / {industry} — {desc}"
                    elif sector:
                        all_valid[tk_up] = f"{sector} — {desc}"
                    else:
                        all_valid[tk_up] = desc
            dropped = [tk for tk in chunk_tickers if tk not in all_valid]
            if dropped:
                logger.warning(f"[theme descriptions] Haiku dropped {len(dropped)} tickers in chunk: {dropped}")
        except Exception as e:
            # #376: credit exhaustion silently drops every description in the
            # chunk — alert it (deduped) before continuing the fail-open loop.
            from agents.market_intelligence.llm_health import maybe_alert_credit_exhausted
            await maybe_alert_credit_exhausted("theme descriptions", e)
            logger.error(f"[theme descriptions] Chunk {chunk_start//CHUNK_SIZE + 1} failed: {e}")

    if all_valid:
        # Only persist for stocks that were genuinely missing
        truly_new = {tk: desc for tk, desc in all_valid.items() if not TICKER_DESC.get(tk)}
        if truly_new:
            await upsert_ticker_overrides_batch(truly_new)
            await log_audit_event(
                "description_generated",
                summary=f"Generated {len(truly_new)} new stock descriptions",
                detail="\n".join(f"{tk}: {desc}" for tk, desc in truly_new.items()),
            )
        apply_overrides(all_valid)
        logger.info(f"[theme descriptions] Generated and persisted {len(all_valid)} descriptions: {list(all_valid.keys())}")

    still_missing = [t for t in missing if not TICKER_DESC.get(t)]
    if still_missing:
        logger.warning(
            f"[theme descriptions] {len(still_missing)} stocks still have no description after fetch — "
            f"will be excluded from clustering: {still_missing}"
        )


async def _get_theme_history(name: str, days: int = 10, tickers: list[str] | None = None) -> list[dict]:
    """Get recent daily snapshots for a named theme.

    Falls back to ticker-overlap matching when the exact name is not found —
    this handles themes that were renamed or merged by Claude.  A theme with
    Jaccard >= 0.4 against the current tickers is treated as the same theme
    so it keeps its earned stage/age rather than restarting at Nascent.
    """
    pool = await get_pool()
    cutoff = et_today() - timedelta(days=days)
    async with pool.acquire() as conn:
        # Primary: exact name match
        rows = await conn.fetch(
            "SELECT * FROM mi_themes WHERE name = $1 AND theme_date >= $2 ORDER BY theme_date DESC",
            name, cutoff,
        )
        if rows:
            return [dict(r) for r in rows]

        # Fallback: find the best-matching prior theme by ticker overlap
        if tickers:
            current_set = set(tickers)
            all_recent = await conn.fetch(
                "SELECT * FROM mi_themes WHERE name != $1 AND theme_date >= $2 ORDER BY theme_date DESC",
                name, cutoff,
            )
            # Group rows by name, then score each name by Jaccard against current tickers
            seen: dict[str, list[dict]] = {}
            for row in all_recent:
                n = row["name"]
                if n not in seen:
                    seen[n] = []
                seen[n].append(dict(row))

            best_name, best_j = None, 0.0
            for n, hist_rows in seen.items():
                hist_tickers = set(hist_rows[0].get("tickers") or [])
                if not hist_tickers:
                    continue
                j = len(current_set & hist_tickers) / len(current_set | hist_tickers)
                if j > best_j:
                    best_j, best_name = j, n

            if best_j >= 0.4 and best_name:
                logger.info(
                    f"Theme history: '{name}' not found, inheriting from '{best_name}' "
                    f"(Jaccard {best_j:.2f}) — stage/age preserved across rename"
                )
                return seen[best_name]

        return []


async def _count_consecutive_fading(name: str, tickers: list[str] | None = None) -> int:
    """Count how many consecutive recent days this theme has been Fading."""
    history = await _get_theme_history(name, days=10, tickers=tickers)
    count = 0
    for row in history:
        if row["stage"] == "Fading":
            count += 1
        else:
            break
    return count


async def _emit_pipeline_diagnostic(
    themes: list[dict],
    stage_label: str,
    *,
    sub_theme_parents: dict[str, str] | None = None,
) -> dict:
    """Stage-boundary diagnostic: emit audit rows for any pipeline-state invariant
    violations after the named stage, with one bounded remediation.

    Captures (audit-only):
      - duplicate ticker sets (two themes with identical members)
      - score-tie groups (≥2 themes at same score → sort non-deterministic)
      - empty themes (tickers list empty after a strip/cap mutation)

    Captures + remediates:
      - orphan sub-themes (parent_theme refers to a name not in the current
        list). 2026-05-13: the orphaned child's `parent_theme` is cleared in
        place and the entry is removed from `sub_theme_parents` so subsequent
        diagnostic stages don't re-fire. Sub-theme survives as a top-level
        theme; only the parent_theme metadata is lost. Chosen over
        block-parent-drop (too coupled to merge/cap logic) and drop-orphan
        (loses information). Triggered by 7 events in 14d, dominant pattern
        E&P/Fracturing oil-sector parent dropped during merge or cap stage.

    Each violation still gets its own event_type so `show errors` / topic
    queries can filter cleanly. Mutations live in this one block only.
    """
    findings: dict = {}

    # 1. Duplicate ticker sets
    dup_groups: dict[frozenset, list[str]] = {}
    for t in themes:
        tk = frozenset(t.get("tickers") or [])
        if not tk:
            continue
        dup_groups.setdefault(tk, []).append(t["name"])
    dups = [(tk, names) for tk, names in dup_groups.items() if len(names) > 1]
    findings["dup_ticker_sets"] = len(dups)
    if dups:
        logger.error(
            f"[invariant] stage='{stage_label}': {len(dups)} duplicate ticker set(s) — "
            f"{[(sorted(tk), names) for tk, names in dups]}"
        )
        detail = "\n".join(f"tickers={sorted(tk)} -> themes={names}" for tk, names in dups)
        await log_audit_event(
            "theme_dup_ticker_sets",
            summary=f"{len(dups)} duplicate ticker set(s) after stage '{stage_label}'",
            detail=f"stage={stage_label}\n{detail}",
        )

    # 2. Score-tie groups (sort order non-deterministic at ties)
    score_groups: dict[float, list[str]] = {}
    for t in themes:
        score = round(float(t.get("score") or 0), 1)
        score_groups.setdefault(score, []).append(t["name"])
    ties = [(s, names) for s, names in score_groups.items() if len(names) > 1]
    findings["score_ties"] = len(ties)
    if ties:
        detail = "\n".join(f"score={s}: {names}" for s, names in sorted(ties, reverse=True))
        await log_audit_event(
            "theme_score_ties",
            summary=f"{len(ties)} score-tie group(s) after stage '{stage_label}'",
            detail=f"stage={stage_label}\n{detail}",
        )

    # 3. Empty themes (tickers stripped to []; should have been pruned)
    empties = [t["name"] for t in themes if not (t.get("tickers") or [])]
    findings["empty_themes"] = len(empties)
    if empties:
        await log_audit_event(
            "theme_empty_tickers",
            summary=f"{len(empties)} theme(s) with empty ticker list after '{stage_label}'",
            detail=f"stage={stage_label}\nempties={empties}",
        )

    # 4. Orphan sub-themes (parent not in this list — relationship snapped).
    # Audit + remediate: clear the orphaned child's parent_theme in place
    # and drop the entry from sub_theme_parents so subsequent stages don't
    # re-fire. See function docstring for rationale.
    if sub_theme_parents:
        names_in_list = {t["name"] for t in themes}
        orphans = [
            (child, parent)
            for child, parent in sub_theme_parents.items()
            if child in names_in_list and parent not in names_in_list
        ]
        findings["orphan_sub_themes"] = len(orphans)
        if orphans:
            detail = "\n".join(f"sub='{c}' parent='{p}' (parent not in list)" for c, p in orphans)
            await log_audit_event(
                "theme_orphan_sub",
                summary=f"{len(orphans)} orphan sub-theme(s) after stage '{stage_label}'",
                detail=f"stage={stage_label}\n{detail}",
            )
            # Remediation: clear parent_theme on each orphaned child and drop
            # the entry from sub_theme_parents (caller-mutating; the same dict
            # is passed to the next stage's diagnostic so subsequent calls
            # see the cleaned-up state).
            orphan_children = {child for child, _ in orphans}
            for t in themes:
                if t["name"] in orphan_children:
                    t["parent_theme"] = None
            for child, _ in orphans:
                sub_theme_parents.pop(child, None)

    return findings


def _restore_sub_theme_links(themes: list[dict], sub_theme_parents: dict[str, str]) -> None:
    """Reconcile every continuing sub-theme's `parent_theme` against today's FINAL
    snapshot. Mutates `themes` in place. Must be the last thing that touches
    `parent_theme` before `_save_themes`.

    Root cause (#471): `_rescore_existing_theme` rebuilds each theme dict from
    scratch every night and never copies `parent_theme` forward from the loaded
    row — so a child's link to its parent survived exactly one day (the
    birth-day write) and went NULL on every save after that, even though
    nothing about the relationship changed. `_emit_pipeline_diagnostic`'s
    orphan remediation above only CLEARS a stale link mid-pipeline when it
    fires — it never restores a live one, and it can't see drops caused by
    `_run_thesis_merge_pass` (runs after the last diagnostic call, before
    save). This function is the single reconciliation point that sees the
    truly final list.

    For every theme whose name is a key in `sub_theme_parents`:
      - parent still present (non-Retired) in `themes` -> parent_theme (re)set
      - parent not present                             -> parent_theme cleared
        (genuine orphan — same semantics as the diagnostic remediation above,
        just re-checked against final state instead of a mid-pipeline one)

    Retired rows are skipped: their `parent_theme` is a deliberate successor
    pointer (`theme_auto_retired`), not a sub-theme link, and must not be
    clobbered here.
    """
    if not sub_theme_parents:
        return
    live_names = {t["name"] for t in themes if t.get("stage") != "Retired"}
    for t in themes:
        if t.get("stage") == "Retired":
            continue
        parent = sub_theme_parents.get(t["name"])
        if parent is None:
            continue
        t["parent_theme"] = parent if parent in live_names else None


# Back-compat alias — older call sites used this name. New code should call
# `_emit_pipeline_diagnostic` directly.
async def _check_unique_ticker_sets(themes: list[dict], stage_label: str) -> int:
    findings = await _emit_pipeline_diagnostic(themes, stage_label)
    return findings.get("dup_ticker_sets", 0)


async def _emit_load_diagnostic(existing: list[dict], today) -> None:
    """Run-start diagnostic: snapshot the `existing` themes loaded from DB.

    Captures:
      - stage distribution (Nascent/Accelerating/Mainstream/Fading counts)
      - theme_date distribution (any rows older than today? cohort mixing?)
      - duplicate ticker sets ALREADY PRESENT in the loaded snapshot
        (cross-run dups that bypassed save-time dedup historically)
      - sub-theme parent integrity (each `parent_theme` reference exists in `existing`)

    Always emits one summary row so we have a daily heartbeat of the load state.
    """
    if not existing:
        return

    stage_counts: dict[str, int] = {}
    date_counts: dict[str, int] = {}
    for t in existing:
        stage_counts[t.get("stage") or "?"] = stage_counts.get(t.get("stage") or "?", 0) + 1
        td = t.get("theme_date")
        td_str = td.isoformat() if hasattr(td, "isoformat") else str(td)
        date_counts[td_str] = date_counts.get(td_str, 0) + 1

    # Duplicate ticker sets in the loaded snapshot — would indicate cross-run
    # duplicates that survived save-time dedup historically.
    dup_groups: dict[frozenset, list[str]] = {}
    for t in existing:
        tk = frozenset(t.get("tickers") or [])
        if not tk:
            continue
        dup_groups.setdefault(tk, []).append(t["name"])
    dups = [(tk, names) for tk, names in dup_groups.items() if len(names) > 1]

    # Sub-theme parent integrity
    names_in_snapshot = {t["name"] for t in existing}
    orphans: list[tuple[str, str]] = []
    for t in existing:
        parent = t.get("parent_theme")
        if parent and parent not in names_in_snapshot:
            orphans.append((t["name"], parent))

    summary_parts = [
        f"n={len(existing)}",
        f"stages={stage_counts}",
        f"dates={len(date_counts)}",
    ]
    if dups:
        summary_parts.append(f"DUPS_AT_LOAD={len(dups)}")
    if orphans:
        summary_parts.append(f"ORPHAN_SUBS={len(orphans)}")

    detail_lines = [
        f"today={today}",
        f"stages={stage_counts}",
        f"date_counts={date_counts}",
    ]
    if dups:
        detail_lines.append("DUPLICATE TICKER SETS at load (cross-run survivors):")
        for tk, names in dups:
            detail_lines.append(f"  tickers={sorted(tk)} themes={names}")
    if orphans:
        detail_lines.append("ORPHAN SUB-THEMES (parent not in snapshot):")
        for child, parent in orphans:
            detail_lines.append(f"  sub='{child}' missing_parent='{parent}'")

    await log_audit_event(
        "theme_load_state",
        summary="theme_load_state " + " ".join(summary_parts),
        detail="\n".join(detail_lines),
    )


async def _emit_cross_run_dup_probe(conn, themes: list[dict], today) -> None:
    """For each theme being saved, query the last 14 days of mi_themes for rows
    with the same ticker set under a DIFFERENT name.

    Informational only — reports Sonnet's tendency to generate name variants
    for stable ticker sets across runs. Most fires are NOT real dups: today's
    name is often the earliest canonical, and `_canonicalize_theme_names`
    correctly leaves it alone. The real same-day dup signal is
    `theme_save_dedup` (line ~836), which has fired 0× in 60d.

    Event name `theme_name_variant_observed` reflects the actual semantics:
    "this ticker set has appeared under a different name in the last 14d."
    Useful telemetry for measuring Sonnet drift rate; NOT an incident.

    History: previously named `theme_cross_run_dup_candidate`. Renamed
    2026-05-13 after a 10-day audit revealed it was over-emitting (7-9
    "candidates" per day, all canonicalization-handled). YAML review
    `theme_engine_dup_incident` closed same day.
    """
    today_names = {t["name"] for t in themes}
    today_sets: dict[frozenset, str] = {}  # frozenset -> our theme name
    for t in themes:
        tk = frozenset(t.get("tickers") or [])
        if tk:
            today_sets[tk] = t["name"]
    if not today_sets:
        return

    rows = await conn.fetch(
        """
        SELECT DISTINCT ON (name) name, theme_date, tickers
        FROM mi_themes
        WHERE theme_date >= $1::date - 14
          AND theme_date < $1::date
        ORDER BY name, theme_date DESC
        """,
        today,
    )

    findings: list[tuple[str, frozenset, str, str]] = []  # (today_name, tk, prior_name, prior_date)
    for row in rows:
        prior_name = row["name"]
        if prior_name in today_names:
            continue  # same theme name — not a cross-run dup, that's normal continuity
        prior_tk = frozenset(row["tickers"] or [])
        if not prior_tk:
            continue
        match_today_name = today_sets.get(prior_tk)
        if match_today_name and match_today_name != prior_name:
            findings.append((match_today_name, prior_tk, prior_name, str(row["theme_date"])))

    if findings:
        detail = "\n".join(
            f"today='{tn}' tickers={sorted(tk)} matches prior='{pn}' last_seen={pd}"
            for tn, tk, pn, pd in findings
        )
        await log_audit_event(
            "theme_name_variant_observed",
            summary=(
                f"{len(findings)} theme(s) had a different name in last 14d for the same ticker set "
                f"(informational — Sonnet name-drift; canonicalize handles)"
            ),
            detail=detail,
        )


def _mass_evicted_patterns(theme_name: str) -> tuple[str, str]:
    """LIKE patterns matching this exact theme's audit rows (#214 guard). Built FROM the
    shared summary-format constants the emit sites use, so producer and matcher cannot
    drift (a rewording would change both or break the binding test). Quoted/anchored
    forms so 'Hydraulic Fracturing…' does not substring-match 'Pure-Play Hydraulic
    Fracturing…'."""
    tripwire = _MASS_REMOVAL_SUMMARY_FMT.format(theme=theme_name, n_flagged="%", n_members="%")
    removal = _REMOVAL_SUMMARY_FMT.format(tk="%", theme=theme_name)
    return tripwire, removal


async def _name_recently_mass_evicted(theme_name: str, days: int = 30) -> bool:
    """#214 inheritance guard: True when this theme name carries a recent mass-eviction
    signature — either the validation_mass_removal_name_suspect tripwire (forward, shipped
    2026-06-09) or >=3 ticker_revalidated_out rows on a single day (pre-tripwire history,
    e.g. the 12-major Pure-Play eviction 2026-06-08). Fail-open: errors return False so a
    DB hiccup never blocks inheritance."""
    tripwire_pat, removal_pat = _mass_evicted_patterns(theme_name)
    try:
        pool = await get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT 1 WHERE EXISTS (
                    SELECT 1 FROM mi_audit_log
                    WHERE event_type = 'validation_mass_removal_name_suspect'
                      AND summary LIKE $1
                      AND created_at > NOW() - ($3 || ' days')::interval
                ) OR EXISTS (
                    SELECT 1 FROM mi_audit_log
                    WHERE event_type = 'ticker_revalidated_out'
                      AND summary LIKE $2
                      AND created_at > NOW() - ($3 || ' days')::interval
                    GROUP BY (created_at AT TIME ZONE 'America/New_York')::date
                    HAVING count(*) >= 3
                )
                """,
                tripwire_pat, removal_pat, str(days),
            )
            return row is not None
    except Exception as e:
        logger.warning(f"#214 inheritance guard lookup failed for '{theme_name}' — failing open: {e}")
        return False


async def _canonicalize_theme_names(
    conn, themes: list[dict], today
) -> int:
    """Rename today's themes to match a prior 14d theme when ticker set is
    identical (cross-run dup canonicalization, #59 2026-05-11).

    Sonnet's theme discovery generates new descriptive names every run, so
    `[AMD, ARM, MRVL]` cycles between "AI Datacenter Silicon" and
    "Custom AI Silicon & Chip Architecture Licensing" night-over-night.
    Net effect: theme history (days_active, consecutive_accelerating)
    resets every rename; forward-returns analysis can't track stable
    cohorts; /themes output looks noisier than the underlying reality.

    Rename rules:
    - Same ticker set (exact frozenset match) under different name within
      last 14 days → use prior name.
    - If multiple prior matches, use the EARLIEST (canonical original).
    - Skip if prior name already exists in today's pending save list
      (Sonnet split today; not a rename case).

    Returns count of themes renamed. Emits one audit event with the
    full rename map for traceability.
    """
    today_names = {t["name"] for t in themes}
    today_sets: dict[frozenset, int] = {}  # ticker set -> index in themes
    for i, t in enumerate(themes):
        tk = frozenset(t.get("tickers") or [])
        if tk:
            today_sets[tk] = i
    if not today_sets:
        return 0

    # Pull EARLIEST appearance per name in last 14d (so cycling renames
    # converge on the original canonical name, not the most recent).
    rows = await conn.fetch(
        """
        SELECT DISTINCT ON (name) name, theme_date, tickers
        FROM mi_themes
        WHERE theme_date >= $1::date - 14 AND theme_date < $1::date
        ORDER BY name, theme_date ASC
        """,
        today,
    )

    # Group prior rows by ticker set → list of (prior_name, prior_date).
    by_set: dict[frozenset, list[tuple[str, str]]] = {}
    for row in rows:
        tk = frozenset(row["tickers"] or [])
        if not tk:
            continue
        by_set.setdefault(tk, []).append((row["name"], str(row["theme_date"])))

    # Probe: ticker-set-evolution gap. Track cases where today's ticker set
    # matches a prior name's LATEST snapshot but NOT its earliest. The current
    # canonicalize uses DISTINCT ON earliest, so these slip through. See
    # canonicalize_ticker_set_evolution review (filed 2026-05-13). Predicate
    # accumulates `theme_canonicalize_gap_observed` events here.
    latest_by_name: dict[str, tuple[frozenset, str]] = {}
    for row in rows:
        nm = row["name"]
        tk = frozenset(row["tickers"] or [])
        if tk:
            # rows already sorted earliest by query; latest = last per name
            latest_by_name[nm] = (tk, str(row["theme_date"]))

    renames: list[tuple[str, str, str]] = []  # (old_today_name, new_canonical_name, prior_date)
    for tk, idx in today_sets.items():
        current_name = themes[idx]["name"]
        priors = by_set.get(tk)
        if not priors:
            # Look for ticker-set-evolution gap: did any prior name's latest
            # snapshot match this ticker set even though its earliest didn't?
            for nm, (latest_tk, latest_date) in latest_by_name.items():
                if nm == current_name:
                    continue
                if latest_tk == tk:
                    await log_audit_event(
                        "theme_canonicalize_gap_observed",
                        f"today='{current_name}' tickers={sorted(tk)} matches "
                        f"prior='{nm}' latest_snapshot={latest_date}, but earliest "
                        f"snapshot had different ticker set — canonicalize missed",
                        detail=(
                            f"today_name={current_name} today_tk={sorted(tk)} "
                            f"prior_name={nm} latest_date={latest_date}"
                        ),
                    )
                    break  # one gap event per today_set is enough
            continue
        # Sort earliest first; pick the earliest prior name as canonical.
        priors_sorted = sorted(priors, key=lambda x: x[1])
        prior_name, prior_date = priors_sorted[0]
        if prior_name == current_name:
            continue  # same name already, no rename
        if prior_name in today_names:
            continue  # already a theme today with that name; don't collide
        renames.append((current_name, prior_name, prior_date))
        themes[idx]["name"] = prior_name
        today_names.discard(current_name)
        today_names.add(prior_name)

    if renames:
        detail = "\n".join(
            f"'{old}' → '{new}' (canonical from {pd})" for old, new, pd in renames
        )
        await log_audit_event(
            "theme_renamed_for_continuity",
            summary=f"{len(renames)} theme(s) renamed to prior canonical names",
            detail=detail,
        )
    return len(renames)


async def _save_themes(themes: list[dict]) -> None:
    """
    Persist today's theme snapshot.  Uses upsert by (theme_date, name)
    so manually seeded themes are updated rather than wiped.
    Deletes any themes for today that aren't in the final list (e.g. merged away).
    """
    if not themes:
        return
    today = themes[0]["theme_date"]
    pool = await get_pool()
    async with pool.acquire() as conn:
        # Cross-run uniqueness probe: query the last 14 days of `mi_themes` for
        # rows with the same ticker set as anything we're about to save BUT under
        # a DIFFERENT name. Diagnostic only; does not mutate.
        await _emit_cross_run_dup_probe(conn, themes, today)

        # Canonicalize names: rename today's themes to match prior 14d themes
        # when the ticker set is identical (#59, 2026-05-11). Preserves
        # days_active / consecutive_accelerating history through Sonnet's
        # cosmetic rephrasings. Must run AFTER the dup probe so the diagnostic
        # event captures pre-rename state, and BEFORE prior_map fetch so the
        # rebuilt name lookups pick up the canonical history.
        await _canonicalize_theme_names(conn, themes, today)

        # Fetch prior conviction counters for the (possibly renamed) theme names.
        prior_rows = await conn.fetch("""
            SELECT DISTINCT ON (name)
                name, days_active, consecutive_accelerating, stage
            FROM mi_themes
            WHERE name = ANY($1) AND theme_date < $2
            ORDER BY name, theme_date DESC
        """, [t["name"] for t in themes], today)
        prior_map = {r["name"]: dict(r) for r in prior_rows}

        # Safety net: themes with identical ticker sets are by definition the
        # same theme. Merge passes should have collapsed these upstream — when
        # this fires, an audit row is written so we can diagnose the merge gap.
        groups: dict[frozenset, list[int]] = {}
        for idx, t in enumerate(themes):
            tk = frozenset(t.get("tickers") or [])
            if not tk:
                continue
            groups.setdefault(tk, []).append(idx)

        drop_indices: set[int] = set()
        for tk_set, idxs in groups.items():
            if len(idxs) <= 1:
                continue
            # Survivor: highest prior days_active → highest score → alphabetic
            def _key(i: int) -> tuple:
                t = themes[i]
                prior = prior_map.get(t["name"]) or {}
                return (
                    -(prior.get("days_active") or 0),
                    -float(t.get("score") or 0),
                    t["name"],
                )
            ranked = sorted(idxs, key=_key)
            survivor = themes[ranked[0]]["name"]
            losers = [themes[i]["name"] for i in ranked[1:]]
            drop_indices.update(ranked[1:])
            logger.warning(
                f"[save dedup] identical ticker set {sorted(tk_set)} — "
                f"keeping '{survivor}', dropping {losers}"
            )
            await log_audit_event(
                "theme_save_dedup",
                summary=f"Duplicate ticker sets at save: kept '{survivor}' over {losers}",
                detail=f"tickers={sorted(tk_set)} survivor={survivor} dropped={losers}",
            )

        if drop_indices:
            themes = [t for i, t in enumerate(themes) if i not in drop_indices]

        # Upsert each theme
        for t in themes:
            prior = prior_map.get(t["name"])
            if prior is None:
                days_active = 1
                consec_acc = 1 if t["stage"] == "Accelerating" else 0
            else:
                prior_days = prior.get("days_active") or 0
                prior_consec = prior.get("consecutive_accelerating") or 0
                days_active = prior_days if t["stage"] == "Fading" else prior_days + 1
                consec_acc = (prior_consec + 1) if t["stage"] == "Accelerating" else 0

            await conn.execute("""
                INSERT INTO mi_themes
                    (theme_date, name, stage, score, rs_avg, description, tickers,
                     parent_theme, days_active, consecutive_accelerating, pct_above_20sma)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
                ON CONFLICT (theme_date, name) DO UPDATE SET
                    stage = EXCLUDED.stage,
                    score = EXCLUDED.score,
                    rs_avg = EXCLUDED.rs_avg,
                    description = EXCLUDED.description,
                    tickers = EXCLUDED.tickers,
                    parent_theme = EXCLUDED.parent_theme,
                    days_active = EXCLUDED.days_active,
                    consecutive_accelerating = EXCLUDED.consecutive_accelerating,
                    pct_above_20sma = EXCLUDED.pct_above_20sma
            """, t["theme_date"], t["name"], t["stage"],
                t["score"], t.get("rs_avg"), t["description"], t["tickers"],
                t.get("parent_theme"), days_active, consec_acc, t.get("pct_above_20sma"))

        # Remove LIVE themes that were merged/retired — not in the final list. Scoped to
        # source='live' so a same-day re-run can't clobber shadow_promoted rows (#226 graduation,
        # which runs AFTER this in the nightly pull and owns its own source='shadow_promoted' rows).
        final_names = [t["name"] for t in themes]
        await conn.execute("""
            DELETE FROM mi_themes
            WHERE theme_date = $1 AND name != ALL($2) AND source = 'live'
        """, today, final_names)


_PROMOTE_WINDOW_DAYS = 3
_PROMOTE_MIN_MEMBERS = 3


async def _upsert_promoted_theme(
    conn,
    name: str,
    tickers: list[str],
    thesis: str | None,
    desc_fallback: str,
    today,
    *,
    rs_avg: float | None,
    prior_days_active: int | None,
) -> bool:
    """F7 (2026-07-02 review) — the ONE shared write path for graduating a shadow cohort into
    live `mi_themes`, used by BOTH `promote_shadow_themes` (nightly auto-promote, batched lookup
    across all qualifying cohorts) and `promote_candidate_by_name` (operator `/promotetheme`,
    single-candidate lookup). Previously this guarded INSERT...ON CONFLICT was hand-copied in both
    places — a future column/guard/stage-default change to one copy would silently diverge the
    operator path from the nightly job.

    Each caller does its OWN lookup (batched vs single — that shape legitimately differs, and the
    nightly path's batched RS query is a deliberate N+1 avoidance) and passes the resolved
    `rs_avg` / `prior_days_active` in; this helper only merges them into the row and executes the
    upsert. `source='shadow_promoted'` is the ON CONFLICT guard — it makes the update fire ONLY
    when the existing row is itself a prior shadow-promotion, never a native `source='live'` theme
    that happens to share a canonicalized name. Byte-identical SQL/semantics to the pre-extraction
    copies; no behavior change.

    Returns `wrote`: True on "INSERT 0 1" (row written), False on "INSERT 0 0" (guard skipped an
    existing native live theme — the caller's `noop` case)."""
    desc = thesis or desc_fallback
    days_active = (prior_days_active or 0) + 1
    score = float(rs_avg) if rs_avg is not None else None
    res = await conn.execute("""
        INSERT INTO mi_themes
            (theme_date, name, stage, score, rs_avg, description, tickers,
             days_active, consecutive_accelerating, source)
        VALUES ($1, $2, 'Nascent', $3, $3, $4, $5, $6, 0, 'shadow_promoted')
        ON CONFLICT (theme_date, name) DO UPDATE SET
            score = EXCLUDED.score, rs_avg = EXCLUDED.rs_avg,
            description = EXCLUDED.description, tickers = EXCLUDED.tickers,
            days_active = EXCLUDED.days_active
        WHERE mi_themes.source = 'shadow_promoted'
    """, today, name, score, desc, tickers, days_active)
    return str(res).endswith(" 1")   # "INSERT 0 1" on write; "INSERT 0 0" when the guard skipped a live theme


async def _map_ecosystems_nonfatal(themes: list[dict], ctx: str) -> None:
    """ADR 0032 — assign ecosystem mappings to `themes`, never raising: every
    path that WRITES mi_themes must run this hook or its themes debut
    E-UNASSIGNED on the board (the 2026-07-16 promote-path gap). One helper so
    the swallow policy (non-fatal, warning-level) can't drift across sites."""
    try:
        # Function-level import — theme_ecosystems imports from briefing,
        # which imports back into the engine's orbit (same reason the
        # original run_theme_engine hook imported locally).
        from agents.market_intelligence.theme_ecosystems import ensure_theme_ecosystems
        await ensure_theme_ecosystems(themes)
    except Exception as e:
        logger.warning(f"[{ctx}] ecosystem mapping pass failed (non-fatal): {e}")


async def promote_shadow_themes(today) -> int:
    """#226 — graduate shadow theme cohorts into the LIVE `mi_themes` table (operator 2026-06-28:
    "we need to graduate this ASAP" — the missing promo path was the gap that let cohorts sit idle).
    Reads the FULL shadow lane (`get_shadow_theme_candidates`, all sources incl 'shadow_v2'), promotes
    every cohort with >= _PROMOTE_MIN_MEMBERS members seen in the last _PROMOTE_WINDOW_DAYS, canonicalizes
    names vs live `mi_themes` (reuse `_canonicalize_theme_names` so a promoted cohort converges to the
    canonical name when its ticker-set already exists), and upserts them as source='shadow_promoted'
    rows for `today`. The theme lifecycle (7d recency cap -> Fading/Retired) self-cleans one-offs.

    Runs AFTER `_save_themes` in the nightly pull; the live DELETE is source='live'-scoped so it can't
    clobber promoted rows, and the ON CONFLICT update is guarded (WHERE source='shadow_promoted') so it
    never overwrites a native live theme that happens to share a canonicalized name. Returns # promoted."""
    from agents.market_intelligence.db import (
        AUTO_PROMOTE_THEME_SOURCES, get_shadow_theme_candidates,
    )
    cands = await get_shadow_theme_candidates(days=_PROMOTE_WINDOW_DAYS)
    # ⚠️ AUTO-PROMOTE WALL 2 of 2 (S3 2026-07-13; ALLOWLIST-inverted #469 2026-07-16,
    # fork F-C = surface-only): the reader above already returns only the vetted
    # AUTO_PROMOTE_THEME_SOURCES by default; this re-filter is deliberate defense in
    # depth so that even a future reader-default flip can never auto-promote an
    # un-vetted source into live mi_themes (→ live judge context/R4 → THE LINE).
    # Non-allowlisted cohorts graduate ONLY via the operator's /promotetheme.
    # Pinned by tests/test_coverage_probe.py (never-promotes-probe + unknown-source pins).
    cands = [c for c in cands if c.get("source") in AUTO_PROMOTE_THEME_SOURCES]
    cohorts = [c for c in cands if len(c.get("tickers") or []) >= _PROMOTE_MIN_MEMBERS]
    if not cohorts:
        logger.info("[promote] no shadow cohort met the >=%d-member bar", _PROMOTE_MIN_MEMBERS)
        return 0
    pool = await get_pool()
    async with pool.acquire() as conn:
        # "description" mirrors thesis for the ecosystem mapper —
        # assign_theme_to_ecosystem reads description (never thesis); without
        # it Haiku classifies on name-only and an abstain persists a STICKY
        # E-UNASSIGNED row that the nightly self-heal never revisits.
        themes = [{"name": c["name"], "tickers": list(c.get("tickers") or []),
                   "thesis": c.get("thesis"),
                   "description": c.get("thesis")} for c in cohorts]
        await _canonicalize_theme_names(conn, themes, today)
        prior_rows = await conn.fetch("""
            SELECT DISTINCT ON (name) name, days_active
            FROM mi_themes WHERE name = ANY($1) AND theme_date < $2
            ORDER BY name, theme_date DESC
        """, [t["name"] for t in themes], today)
        prior_map = {r["name"]: dict(r) for r in prior_rows}
        # Batch the RS lookup — ONE query for all members across all cohorts, not N+1 per theme.
        _all_members = list({tk for t in themes for tk in t["tickers"]})
        _rs_rows = await conn.fetch("""
            SELECT ticker, rs_composite FROM mi_stock_scores
            WHERE ticker = ANY($1)
              AND score_date = (SELECT MAX(score_date) FROM mi_stock_scores)
        """, _all_members)
        _rs_by_tk = {r["ticker"]: r["rs_composite"] for r in _rs_rows if r["rs_composite"] is not None}
        n = 0
        new_grads = []  # genuinely-NEW shadow→live crossings (no prior live row); re-promotions stay silent
        written = []    # themes actually upserted — the ecosystem mapper's input
        for t in themes:
            members = t["tickers"]
            _vals = [_rs_by_tk[tk] for tk in members if tk in _rs_by_tk]
            rs_avg = sum(_vals) / len(_vals) if _vals else None
            prior = prior_map.get(t["name"])
            prior_days_active = prior.get("days_active") if prior else None
            wrote = await _upsert_promoted_theme(
                conn, t["name"], members, t.get("thesis"),
                f"Graduated from the shadow lane ({len(members)} members).", today,
                rs_avg=rs_avg, prior_days_active=prior_days_active)
            if wrote:
                n += 1
                written.append(t)
                if prior is None:          # first crossing into live under this name
                    new_grads.append(t["name"])
        await log_audit_event(
            "shadow_themes_promoted",
            summary=f"Graduated {n} shadow cohort(s) into live mi_themes ({len(new_grads)} new)",
            detail=f"promoted={[t['name'] for t in themes]} new={new_grads}")
    logger.info("[promote] graduated %d shadow cohort(s) into mi_themes", n)
    # Self-verify (#370 systematic-failure-guard) — the nightly run confirms ITSELF, no human in the
    # loop. SILENT-FAILURE (cohorts qualified but 0 written) -> alert, never a silent degrade.
    # SUCCESS -> a one-line operator confirm so "it fired" is visible (silent success is invisible).
    from agents.market_intelligence.briefing import send_telegram_message
    if len(cohorts) > 0 and n == 0:
        await log_audit_event(
            "shadow_promotion_silent_failure",
            summary=f"{len(cohorts)} shadow cohort(s) qualified but 0 graduated",
            detail=f"qualified={[c['name'] for c in cohorts]}")
        await send_telegram_message(
            f"⚠️ Theme graduation RAN but wrote 0 rows despite {len(cohorts)} qualifying "
            f"cohort(s) — check the shadow_promotion_silent_failure audit.")
    elif new_grads:
        # Noise fix (operator 7/7): ping ONLY on a genuine NEW shadow→live crossing, and NAME it.
        # Re-promotions of already-live cohorts are steady-state maintenance (still logged in the
        # shadow_themes_promoted audit above) — not actionable, so no Telegram. (Was: fired every
        # nightly run because established cohorts keep re-qualifying → "1 theme graduated" nightly.)
        n_new = len(new_grads)
        _named = ", ".join(new_grads[:6]) + (f" +{n_new - 6} more" if n_new > 6 else "")
        await send_telegram_message(
            f"🎓 {n_new} theme(s) NEWLY graduated shadow→live: {_named}. `/themes`.")
    # ADR 0032: map promoted themes to ecosystems AT promotion. This job runs
    # AFTER run_theme_engine's ensure hook (17:05 vs 17:03), so without this
    # every new promote sat E-UNASSIGNED on the board until the next nightly
    # self-heal (4 themes, 2026-07-16).
    if written:
        await _map_ecosystems_nonfatal(written, "promote")
    return n


async def promote_candidate_by_name(name_query: str, today) -> dict:
    """Operator-driven SINGLE-candidate promotion — the manual `/promotetheme` version of
    `promote_shadow_themes`. Looks up the shadow candidate whose name matches `name_query`
    (case-insensitive substring; an exact match disambiguates), validates >= _PROMOTE_MIN_MEMBERS,
    canonicalizes vs live themes, and upserts ONE mi_themes row (source='shadow_promoted', same as the
    nightly auto-promote). Returns a status dict for the Telegram confirm.

    The promoted theme then behaves EXACTLY like any other (operator 6/29, verified): the daily
    discovery re-writes it via `_canonicalize_theme_names`'s ticker-set match while its cohort
    co-moves, and the 7d recency cap ages it out only if the cohort dissolves. No special treatment,
    no pinning. The audit row records THAT it was operator-promoted; the lifecycle is identical.

    status ∈ {'promoted', 'noop' (matched an existing live theme — left intact), 'not_found',
              'ambiguous', 'too_few'}."""
    from agents.market_intelligence.db import get_shadow_theme_candidates
    q = (name_query or "").strip().strip('"').strip()
    if not q:
        return {"status": "not_found", "available": []}
    # include_probe=True: the operator one-tap IS the sanctioned graduation path for
    # source='coverage_probe' cohorts (S3 carve-out, fork F-C surface-only) — the nightly
    # auto-promote above never sees them; this deliberate human tap may.
    cands = await get_shadow_theme_candidates(days=7, include_probe=True)
    # Word-based match: every query word must appear in the candidate name (case-insensitive). More
    # forgiving than a literal substring — "rare orphan biotech" matches "Rare & Orphan Biotech ..."
    # (the literal "& " between the words would defeat a raw substring search).
    q_words = q.lower().split()
    matches = [c for c in cands if all(w in (c.get("name") or "").lower() for w in q_words)]
    if not matches:
        return {"status": "not_found", "available": [c["name"] for c in cands[:8]]}
    if len(matches) > 1:
        exact = [c for c in matches if (c.get("name") or "").lower() == q.lower()]
        if len(exact) == 1:
            matches = exact
        else:
            return {"status": "ambiguous", "matches": [c["name"] for c in matches]}
    cand = matches[0]
    members = list(cand.get("tickers") or [])
    if len(members) < _PROMOTE_MIN_MEMBERS:
        return {"status": "too_few", "name": cand["name"], "n_members": len(members)}
    pool = await get_pool()
    async with pool.acquire() as conn:
        # description mirrors thesis for the ecosystem mapper (same reason as
        # promote_shadow_themes — the mapper reads description, never thesis).
        themes = [{"name": cand["name"], "tickers": members, "thesis": cand.get("thesis"),
                   "description": cand.get("thesis")}]
        await _canonicalize_theme_names(conn, themes, today)   # converge to a live name if the set exists
        t = themes[0]
        _rs_rows = await conn.fetch("""
            SELECT ticker, rs_composite FROM mi_stock_scores
            WHERE ticker = ANY($1) AND score_date = (SELECT MAX(score_date) FROM mi_stock_scores)
        """, t["tickers"])
        _rs = {r["ticker"]: r["rs_composite"] for r in _rs_rows if r["rs_composite"] is not None}
        _vals = [_rs[tk] for tk in t["tickers"] if tk in _rs]
        rs_avg = sum(_vals) / len(_vals) if _vals else None
        prior = await conn.fetchrow("""
            SELECT days_active FROM mi_themes WHERE name = $1 AND theme_date < $2
            ORDER BY theme_date DESC LIMIT 1
        """, t["name"], today)
        prior_days_active = prior["days_active"] if prior else None
        wrote = await _upsert_promoted_theme(
            conn, t["name"], t["tickers"], t.get("thesis"),
            f"Operator-promoted ({len(t['tickers'])} members).", today,
            rs_avg=rs_avg, prior_days_active=prior_days_active)
        await log_audit_event(
            "theme_operator_promoted",
            summary=(f"Operator promoted '{t['name']}' ({len(t['tickers'])} members)"
                     + ("" if wrote else " — already a live theme, left intact")),
            detail=f"query='{q}' candidate='{cand['name']}' final='{t['name']}' "
                   f"tickers={t['tickers']} cand_source={cand.get('source')}")
    # ADR 0032: same at-promotion ecosystem mapping as the nightly auto-promote
    # (see promote_shadow_themes) — the operator path writes mi_themes outside
    # the engine's ensure hook too.
    if wrote:
        await _map_ecosystems_nonfatal([t], "promote")
    return {"status": "promoted" if wrote else "noop", "name": t["name"],
            "tickers": t["tickers"], "n_members": len(t["tickers"]),
            "canonicalized": t["name"] != cand["name"], "orig_name": cand["name"]}


async def _validate_new_themes_at_birth(
    new_themes: list[dict],
    changelog: list[dict],
    protected: set[tuple[str, str]] | None,
) -> list[dict]:
    """#266 (operator-signed 2026-06-17): run the SAME `_validate_theme_membership` on each
    newly-DISCOVERED theme's founding members BEFORE persist.

    Root cause (docs/analysis/theme_birth_validation_evidence_2026-06-17.md): the discovery path
    never ran the description-match validator, so a born theme's mismatched members sat ~6d
    (median) until the next Mon/Wed/Fri rescore. This changes WHEN the validator runs, not WHAT
    it checks — the validator's own min-survivor guard (PRUNE_MIN_TICKERS) keeps small/born-bad
    themes intact (identical to Mon/Wed/Fri semantics), and its per-ticker cooldown +
    `ticker_revalidated_out` audit make the strips land at birth (~0d on the re-run latency
    probe). Mutates `new_themes` in place; emits a `theme_birth_validated` roll-up per stripped
    theme. Sequential — new themes per run are few; `_VALIDATION_SEMAPHORE` still bounds
    concurrency inside the validator against other callers."""
    for nt in new_themes:
        tks = list(nt.get("tickers") or [])
        if len(tks) < NEW_THEME_MIN_STOCKS:
            continue
        validated = await _validate_theme_membership(
            nt["name"], tks, changelog, protected=protected)
        if len(validated) != len(tks):
            stripped = sorted(set(tks) - set(validated))
            nt["tickers"] = validated
            logger.info(f"[birth validation #266] '{nt['name']}' stripped at birth: {stripped}")
            await log_audit_event(
                "theme_birth_validated",
                summary=f"Birth-validation stripped {len(stripped)} from new theme '{nt['name']}'",
                detail=f"Removed: {', '.join(stripped)} | kept: {', '.join(validated)}",
            )
    return new_themes


async def _validate_theme_membership(
    theme_name: str,
    tickers: list[str],
    changelog: list[dict],
    protected: set[tuple[str, str]] | None = None,
    dissolve_flagged_pair: bool = False,
) -> list[str]:
    """
    Ask Claude (THEME_MODEL = Sonnet) whether each stock's description is consistent
    with the theme. Removes stocks that clearly don't belong. Runs Mon/Wed/Fri during
    re-scoring.

    dissolve_flagged_pair (ADR 0025 Arm A, #274 — callers pass merge_arm_enabled()):
    when True and the theme has exactly 2 members, a flagged removal PROCEEDS past the
    min-survivor guard (returning <PRUNE_MIN_TICKERS survivors) so the caller can
    dissolve the theme — the 2-member-immortality fix. The flagged member gets the
    normal 14d cooldown + audit rows below; the survivor gets none. Default False =
    byte-identical legacy behavior (guard skips the removals).

    Model = Sonnet, not Haiku (#213, 2026-06-06): Haiku misread narrowing
    momentum/driver qualifiers in theme names (the "AI" in "AI Memory & Storage")
    as membership filters and falsely evicted core sector members (SNDK/SIMO NAND
    flash, AXTI optical). The isolating eval (scripts/eval_theme_validation_model.py)
    showed Sonnet on the SAME prompt keeps those names while still removing genuine
    mismatches (CAR wrong-industry; XOM/CVX integrated-majors from a pure-play frac
    theme) — deterministic across 4 runs. Operator-protected (bypassed-cooldown)
    pairs are additionally shielded from removal regardless of model.

    This catches stocks that were added before descriptions existed or were incorrectly
    clustered (e.g. AGRO ending up in an IP Licensing theme).
    """
    from agents.market_intelligence.universe import TICKER_DESC

    if len(tickers) < 2:
        return tickers

    # Include ALL tickers — described ones get their description, undescribed ones
    # are identified by ticker symbol alone (the model knows CAR=Avis, UBER=rideshare, etc.)
    # Previously, undescribed tickers were silently kept, making validation blind to them.
    stock_lines_parts = []
    for tk in tickers:
        desc = TICKER_DESC.get(tk)
        if desc:
            stock_lines_parts.append(f"- {tk}: {desc}")
        else:
            stock_lines_parts.append(f"- {tk}: (use your knowledge of this ticker)")
    stock_lines = "\n".join(stock_lines_parts)

    prompt = (
        f"Theme: \"{theme_name}\"\n\n"
        f"Stocks in this theme:\n{stock_lines}\n\n"
        f"Identify stocks that DO NOT BELONG in this theme.\n"
        f"A stock does not belong if its core business is in a DIFFERENT INDUSTRY than the theme — "
        f"e.g. a car rental company in a data center theme, a mining company in a biotech theme, "
        f"a retailer in a semiconductor theme. Be DECISIVE: wrong industry = remove. "
        f"Do not keep a stock just because you are unsure — if the business sector clearly differs "
        f"from the theme, flag it.\n\n"
        f"Return JSON only: {{\"remove\": [\"TICKER1\", \"TICKER2\"]}} or {{\"remove\": []}} if all belong."
    )

    try:
        client = _get_anthropic_client()
        # Semaphore + single retry on 429 — matches the ep_detector pattern and
        # stops the asyncio.gather fan-out from detonating the 50 rpm org limit.
        import random
        async with _VALIDATION_SEMAPHORE:
            # Three attempts with escalating backoff: 30–45s, then 60–90s.
            # 50 rpm org limit refills continuously, so even a single long wait
            # frees budget reliably — previous 8–12s waits were too short when
            # other pipeline callers (descriptions, discovery) were also active.
            backoffs = [(30, 15), (60, 30)]
            for attempt in range(3):
                try:
                    resp = await client.messages.create(
                        model=THEME_MODEL,
                        max_tokens=400,
                        system="You are a JSON API. Respond with valid JSON only. No prose, no markdown, no explanation.",
                        messages=[{"role": "user", "content": prompt}],
                    )
                    break
                except anthropic.RateLimitError:
                    if attempt == len(backoffs):
                        raise
                    base, jitter = backoffs[attempt]
                    wait = base + random.random() * jitter
                    await log_audit_event(
                        "anthropic_rate_limited",
                        summary=f"Validation rate-limited for '{theme_name}' — retry {attempt+1}/{len(backoffs)} in {wait:.0f}s",
                        detail=f"429 on {THEME_MODEL}",
                    )
                    await asyncio.sleep(wait)
        # S2/F9: safe wrapper — see spend_tracker.log_anthropic_call_safe
        from agents.market_intelligence.spend_tracker import log_anthropic_call_safe
        await log_anthropic_call_safe(model=THEME_MODEL, caller="theme_validation",
                                       usage=getattr(resp, "usage", None))
        # Defensive extraction — the model occasionally returns non-text blocks
        # or empty content, which previously surfaced as cryptic parse errors.
        if not resp.content:
            raise ValueError("empty validation response")
        raw_block = resp.content[0]
        raw = (getattr(raw_block, "text", "") or "").strip()
        if not raw:
            raise ValueError(f"validation returned no text (stop_reason={resp.stop_reason})")
        # Strip code fences if present
        if raw.startswith("```"):
            parts = raw.split("\n", 1)
            raw = parts[1].rstrip("` \n").strip() if len(parts) > 1 else raw.strip("` ")
        # Extract the outermost JSON object by tracking brace depth.
        # The naive r'\{[^{}]*\}' regex fails when the model adds nested objects
        # (e.g. {"remove": [], "notes": {"why": "..."}}) because [^{}] stops
        # at the inner brace. Brace-depth tracking handles arbitrary nesting.
        raw = _extract_json_object(raw)
        result = json.loads(raw)
        remove_val = result.get("remove") or []  # guard against "remove": null
        to_remove = {tk.upper() for tk in remove_val if isinstance(tk, str)}

        # ── Mass-removal tripwire (#214) — AUDIT-ONLY, no behavior change ───
        # When validation flags >=50% of a theme's members (and >=3 names), the
        # historical cause is the theme NAME being narrower than the cluster it
        # labels (e.g. 12 integrated majors evicted from "Pure-Play Hydraulic
        # Fracturing" 2026-06-08 — the removals were CORRECT given the name; the
        # NAME was the defect). Surface that signature for the operator instead
        # of letting it masquerade as a generic cooldowns_per_day L2 anomaly.
        # Removals still proceed unchanged — validation-prompt behavior changes
        # are #215's gated lane.
        if len(to_remove) >= max(3, len(tickers) // 2):
            await log_audit_event(
                "validation_mass_removal_name_suspect",
                summary=_MASS_REMOVAL_SUMMARY_FMT.format(
                    theme=theme_name, n_flagged=len(to_remove), n_members=len(tickers)),
                detail=f"Flagged: {', '.join(sorted(to_remove))}",
            )

        # ── Operator-protection shield (#213) ───────────────────────────────
        # If the operator explicitly bypassed a (ticker, theme) cooldown, they
        # have ruled that this ticker BELONGS in this theme. The validator must
        # never re-remove it — otherwise the next Mon/Wed/Fri run silently
        # undoes the operator's correction (SNDK/SIMO re-stripped from
        # "AI Memory & Storage" on the narrowing "AI" qualifier). The shield is
        # additive + fails open: a DB error here leaves to_remove untouched.
        if to_remove:
            try:
                # #217: run-level callers pass the protected set (fetched once per
                # run); the fallback fetch keeps direct calls + tests working.
                if protected is None:
                    protected = await get_operator_protected_set()
                shielded = {tk for tk in to_remove if (tk, theme_name) in protected}
                if shielded:
                    to_remove -= shielded
                    for tk in sorted(shielded):
                        logger.info(
                            f"Theme '{theme_name}': KEPT {tk} — operator-protected "
                            f"(bypassed cooldown), validator removal vetoed"
                        )
                    await log_audit_event(
                        "validation_removal_shielded",
                        summary=f"{len(shielded)} operator-protected ticker(s) kept in '{theme_name}': {', '.join(sorted(shielded))}",
                        detail="Bypassed cooldown = operator ruled membership; re-removal vetoed (#213)",
                    )
            except Exception as e:
                logger.warning(f"Operator-protection shield lookup failed for '{theme_name}': {e}")

        # Never remove so many that the theme drops below minimum — EXCEPT the
        # ADR 0025 Arm A flagged-pair case (dissolve_flagged_pair=True + exactly
        # 2 members): the removal proceeds so the CALLER can dissolve the theme
        # on validation evidence instead of the pair living forever behind this
        # guard. A ≥3-member theme is never dissolved here (narrow by design).
        survivable = [t for t in tickers if t not in to_remove]
        if len(survivable) < PRUNE_MIN_TICKERS:
            if not (dissolve_flagged_pair and len(tickers) == 2 and to_remove):
                logger.warning(
                    f"Theme '{theme_name}': re-validation would drop below {PRUNE_MIN_TICKERS} tickers — skipping removals"
                )
                return tickers
            logger.info(
                f"Theme '{theme_name}': flagged pair — removal proceeds for Arm A dissolve (ADR 0025)"
            )

        if to_remove:
            for tk in to_remove:
                if tk in tickers:
                    desc = TICKER_DESC.get(tk, "")
                    changelog.append({
                        "type": "ticker_revalidated_out",
                        "theme": theme_name,
                        "ticker": tk,
                        "reason": f"description inconsistent with theme '{theme_name}'",
                    })
                    logger.info(
                        f"Theme '{theme_name}': removed {tk} — description '{desc}' "
                        f"does not match theme"
                    )
                    # Persistent audit record — survives image rebuilds, queryable from Telegram
                    await log_audit_event(
                        "ticker_revalidated_out",
                        summary=_REMOVAL_SUMMARY_FMT.format(tk=tk, theme=theme_name),
                        detail=f"Description: '{desc}' — validation ({THEME_MODEL}) flagged as not matching theme",
                    )
                    # Write 14-day cooldown so the stock can't be re-assigned immediately
                    count = await add_validation_cooldown(
                        tk, theme_name,
                        reason=f"Description '{desc}' does not match theme",
                    )
                    await log_audit_event(
                        "validation_cooldown_triggered",
                        summary=f"{tk} → '{theme_name}' cooldown 14d (removal #{count})",
                        detail=f"Description: '{desc}'",
                    )
                    # NOTE: do NOT auto-persist to mi_theme_exclusions here.
                    # Previously tried (commit d07a363), deliberately reverted (commit f0372ef)
                    # because bad yfinance descriptions caused TSEM to be permanently banned
                    # from semiconductor theme. Validation is in-memory only — re-runs Mon/Wed/Fri.
                    # The real fix for same-run re-assignment is covered_tickers including
                    # Fading themes (so validation-removed tickers don't appear as uncovered).
            return [t for t in tickers if t not in to_remove]

        logger.debug(f"Theme '{theme_name}': validation kept all {len(tickers)} tickers")
        return tickers

    except anthropic.RateLimitError as e:
        # Retry already exhausted — this is a rate-limit failure, NOT a parse error.
        # Mislabeling as "parse error" sent us down a days-long wrong-cause chase; be explicit.
        logger.error(f"Theme '{theme_name}': validation rate-limited (final) — keeping all tickers")
        await log_audit_event(
            "validation_rate_limited",
            summary=f"Validation rate-limited for '{theme_name}' — tickers unchanged",
            detail=f"RateLimitError after retry: {e}",
        )
        return tickers
    except Exception as e:
        # #273: credit exhaustion would silently keep all tickers (validation
        # degraded) with no alert. Detect + alert (deduped) before the fail-open.
        # Ordered before the rate-limit branch — is_credit_error excludes 429.
        from agents.market_intelligence.llm_health import maybe_alert_credit_exhausted
        await maybe_alert_credit_exhausted("theme validation", e)
        # Defensive: some anthropic SDK versions raise subclasses or proxies that
        # escape the anthropic.RateLimitError clause above. Route any rate-limit
        # error here so the audit log gives the correct cause — mislabeling 429s
        # as "parse errors" previously cost days of wrong-cause debugging.
        if isinstance(e, anthropic.RateLimitError) or type(e).__name__ == "RateLimitError":
            logger.error(f"Theme '{theme_name}': validation rate-limited (fell through to Exception) — keeping all tickers")
            await log_audit_event(
                "validation_rate_limited",
                summary=f"Validation rate-limited for '{theme_name}' — tickers unchanged",
                detail=f"RateLimitError after retry (caught via Exception fallback): {e}",
            )
            return tickers
        # Transient failures — Anthropic 5xx, network blips, timeouts. These resolve
        # by themselves on the next Mon/Wed/Fri rerun, so route to a non-`_error`
        # event_type that doesn't trip the L1 silent_audit_error_window invariant.
        # Real bugs (parse errors, unexpected schema) still hit `validation_error`.
        raw_snippet = locals().get("raw", "<not set>")[:200]
        if isinstance(e, _THEME_TRANSIENT_EXC):
            logger.warning(
                f"Theme '{theme_name}': validation transient failure "
                f"({type(e).__name__}: {e}) — keeping all tickers, will retry next run."
            )
            await log_audit_event(
                "validation_api_failure",
                summary=f"Validation API failure for '{theme_name}' — tickers unchanged",
                detail=f"{type(e).__name__}: {e}",
            )
            return tickers
        # Log the raw response so silent failures are diagnosable — this bug cost days of work
        logger.error(
            f"Theme '{theme_name}': re-validation FAILED ({type(e).__name__}: {e}) — "
            f"keeping all tickers. Raw validation response: {raw_snippet!r}"
        )
        await log_audit_event(
            "validation_error",
            summary=f"Validation parse error for '{theme_name}' — tickers unchanged",
            detail=f"{type(e).__name__}: {e} | raw={raw_snippet!r}",
        )
        return tickers


def _check_description_quality(
    name: str, tickers: list[str], description: str | None,
) -> tuple[bool, str]:
    """Validate Sonnet-generated theme description for the bug class caught
    2026-05-26 (GLW report on 'LOVE SEAT' hallucination). Returns (ok, reason).

    Three rules per advisor 2026-05-26 review, calibrated against 30d
    corpus of 26 two-member Accelerating/Mainstream themes (27% clear
    noise rate — fix shape is description guard, not 2-member cap):

      A. Concat detection — substring `"{T1} {T2}"` or `"{T2} {T1}"`
         indicates Sonnet treated two distinct tickers as one entity.
         Catches "LOVE SEAT" / "WLTH LIFE". Legit descriptions use
         "Datadog (DDOG) and Fortinet (FTNT)" style which has `and`,
         comma, or parenthetical between symbols — won't false-positive.

      B. At-least-one-member-mentioned — description must reference
         AT LEAST ONE theme ticker. Catches CLMT/CF themes where
         Sonnet's description talks about LYB/BW/DOW (totally wrong
         stocks). Strict "no non-members" would false-positive on
         legitimate peer-context mentions; relaxed lower bound avoids
         that while catching the categorical-mismatch class.

      C. Empty-description block — empty/whitespace-only description
         can't advance past Nascent. 5/5 empty-description themes in
         the 30d sample were reaching Accelerating without validation;
         this rule is load-bearing.
    """
    if not description or not description.strip():
        return False, "empty_description"

    descr = description
    # Need ticker tokens; uppercase + word-boundary-safe matching
    ticker_set = {t.upper() for t in tickers if t}
    if len(ticker_set) < 2:
        # Sub-2 themes are rare in active state but possible — concat
        # check is N/A. Only the at-least-one rule applies. Empty
        # already handled above.
        for t in ticker_set:
            if t in descr.upper():
                return True, ""
        return False, "no_member_ticker_mentioned"

    # Rule A: concat detection
    descr_upper = descr.upper()
    ticker_list = sorted(ticker_set)
    for i, t1 in enumerate(ticker_list):
        for t2 in ticker_list[i + 1:]:
            if f"{t1} {t2}" in descr_upper or f"{t2} {t1}" in descr_upper:
                return False, f"ticker_concat:{t1}_{t2}"

    # Rule B: at least one member mentioned
    if not any(t in descr_upper for t in ticker_set):
        return False, "no_member_ticker_mentioned"

    return True, ""


async def _rescore_existing_theme(
    theme: dict,
    stocks_by_ticker: dict[str, dict],
    today: date,
    theme_exclusions: dict[str, set[str]] | None = None,
    protected: set[tuple[str, str]] | None = None,
) -> tuple[dict | None, list[dict]]:
    """
    Re-score an existing theme using today's RS data.
    Returns (theme_or_None, changelog_entries). None means retired.
    theme_exclusions: mapping of theme_name → set of tickers permanently excluded from it.
    """
    name = theme["name"]
    tickers = list(theme.get("tickers") or [])
    changelog: list[dict] = []

    # --- Enforce persistent exclusions FIRST — before any pruning or validation ---
    # Uses fuzzy name matching so exclusions survive theme renames by Claude.
    if theme_exclusions:
        excluded_for_theme = _get_excluded_tickers_for_theme(name, theme_exclusions)
        if excluded_for_theme:
            excluded_present = [t for t in tickers if t in excluded_for_theme]
            if excluded_present:
                logger.info(
                    f"Theme '{name}': stripping persistently excluded tickers: {excluded_present}"
                )
                tickers = [t for t in tickers if t not in excluded_for_theme]
                for tk in excluded_present:
                    changelog.append({
                        "type": "ticker_excluded",
                        "theme": name,
                        "ticker": tk,
                        "reason": "persistent exclusion (DB)",
                    })

    # --- Pruning: remove weak stocks before scoring ---
    prune_candidates: list[tuple[str, float, str]] = []  # (ticker, rs, reason)
    soft_check_tickers: list[str] = []
    missing_rs_tickers: list[str] = []   # in theme but absent from today's RS data

    for tk in tickers:
        stock = stocks_by_ticker.get(tk)
        if not stock:
            missing_rs_tickers.append(tk)  # collect for history check instead of blindly keeping
            continue
        rs_now = stock.get("rs_composite")
        if rs_now is None:
            missing_rs_tickers.append(tk)
            continue
        if rs_now < PRUNE_RS_HARD:
            prune_candidates.append((tk, rs_now, f"RS {rs_now:.0f} < {PRUNE_RS_HARD:.0f} (hard)"))
        elif rs_now < PRUNE_RS_SOFT:
            soft_check_tickers.append(tk)

    # Stocks missing today's RS: check recent history — if consistently weak, prune them too.
    # Prevents tickers from hiding in themes by occasionally dropping out of the RS engine.
    if missing_rs_tickers:
        missing_history = await get_recent_rs_batch(missing_rs_tickers, today, days=5)
        for tk in missing_rs_tickers:
            hist = missing_history.get(tk, [])
            if hist and all(v < PRUNE_RS_HARD for v in hist):
                prune_candidates.append((tk, hist[0], f"RS {hist[0]:.0f} consistently < {PRUNE_RS_HARD:.0f} (no current data)"))

    # Soft prune: check 3-day history
    if soft_check_tickers:
        rs_history = await get_recent_rs_batch(soft_check_tickers, today, days=3)
        for tk in soft_check_tickers:
            hist = rs_history.get(tk, [])
            if len(hist) >= 3 and all(v < PRUNE_RS_SOFT for v in hist):
                rs_now = hist[0]
                prune_candidates.append((tk, rs_now, f"RS below {PRUNE_RS_SOFT:.0f} for 3 consecutive days"))

    # Enforce minimum ticker count
    if prune_candidates:
        remaining_count = len(tickers) - len(prune_candidates)
        if remaining_count < PRUNE_MIN_TICKERS:
            # Sort by RS descending to keep the least-bad ones
            prune_candidates.sort(key=lambda x: x[1], reverse=True)
            keep_count = PRUNE_MIN_TICKERS - remaining_count
            kept_back = prune_candidates[:keep_count]
            prune_candidates = prune_candidates[keep_count:]
            if kept_back:
                logger.info(f"Theme '{name}': kept {[k[0] for k in kept_back]} to maintain min {PRUNE_MIN_TICKERS} tickers")

    # Apply pruning
    pruned_tickers = {p[0] for p in prune_candidates}
    if pruned_tickers:
        tickers = [t for t in tickers if t not in pruned_tickers]
        for tk, rs, reason in prune_candidates:
            changelog.append({"type": "ticker_pruned", "theme": name, "ticker": tk, "rs": rs, "reason": reason})
            logger.info(f"Theme '{name}': pruned {tk} — {reason}")

    # Re-validation: remove stocks whose description clearly doesn't match the theme.
    # Runs Mon/Wed/Fri only (original design). With correct descriptions loaded from DB
    # (get_ticker_overrides now filters NULL rows), Haiku works from accurate data.
    today_weekday_val = today.weekday()  # 0=Mon, 2=Wed, 4=Fri
    if len(tickers) >= 2 and today_weekday_val in (0, 2, 4):
        _dissolve_arm = merge_arm_enabled()  # ADR 0025 Arm A (#274); False = legacy path
        _pre_validation = list(tickers)
        tickers = await _validate_theme_membership(
            name, tickers, changelog, protected=protected,
            dissolve_flagged_pair=_dissolve_arm)
        if _dissolve_arm and len(_pre_validation) == 2 and len(tickers) < PRUNE_MIN_TICKERS:
            # ADR 0025 Arm A: validation flagged a member of a 2-member theme →
            # the theme DISSOLVES (evidence-triggered, never a bare count). The
            # flagged member already got its 14d cooldown + ticker_revalidated_out
            # rows inside the validator; the survivor gets NO cooldown and is
            # released to the discovery pools. Returning None drops the theme
            # from emission → the engine-drop path synthesizes its Retired row
            # (theme_auto_retired, parent_theme=NULL).
            flagged = sorted(set(_pre_validation) - set(tickers))
            survivors = list(tickers)
            changelog.append({
                "type": "theme_dissolved_flagged_pair",
                "theme": name,
                "flagged": flagged,
                "survivors": survivors,
                "via": "validation",
            })
            await log_audit_event(
                "theme_dissolved_flagged_pair",
                summary=(f"Arm A dissolve: '{name}' — validation flagged "
                         f"{', '.join(flagged)} at 2 members"),
                detail=(f"via=validation flagged={flagged} survivors={survivors} "
                        f"(survivor released, no cooldown — ADR 0025 Arm A)"),
            )
            logger.info(f"Theme '{name}': dissolved on flagged pair (ADR 0025 Arm A)")
            return None, changelog

    # Check how many constituent stocks still show strong RS today
    strong_stocks = [t for t in tickers if t in stocks_by_ticker
                     and stocks_by_ticker[t].get("rs_composite", 0) >= THEME_RS_MIN]

    # Sanitize existing description — don't carry forward Haiku garbage or Perplexity failures
    existing_desc = theme.get("description", "")
    if _is_garbage(existing_desc):
        existing_desc = ""

    # A theme is Fading if it lacks strong stocks — but 2 elite stocks (RS 80+) is enough
    avg_strong_rs = (sum(stocks_by_ticker[t]["rs_composite"] for t in strong_stocks) / len(strong_stocks)) if strong_stocks else 0
    is_elite_pair = len(strong_stocks) >= 2 and avg_strong_rs >= 80

    if len(strong_stocks) < THEME_COVERAGE_MIN and not is_elite_pair:
        fading_days = await _count_consecutive_fading(name, tickers=tickers)
        if fading_days >= FADING_RETIRE_AFTER:
            logger.info(f"Theme '{name}' retired after {fading_days} fading days")
            return None, changelog  # retire it

        pct_breadth = await get_ticker_breadth_above_sma20(tickers, today)
        return {
            "theme_date": today,
            "name": name,
            "stage": "Fading",
            "score": max(0.0, (theme.get("score") or 0) * 0.8),
            "rs_avg": None,
            "description": existing_desc,
            "tickers": tickers,
            "pct_above_20sma": pct_breadth,
            # #471: carry the sub-theme link forward — this function rebuilds
            # the dict from scratch, so a copied-over `existing` field is the
            # only way it survives past birth day. `_restore_sub_theme_links`
            # (run_theme_engine, right before _save_themes) is still the final
            # authority on whether the link is genuinely still live; this is
            # belt-and-suspenders so intermediate stages (e.g. the
            # "never split a sub-theme further" guard below) see it too.
            "parent_theme": theme.get("parent_theme"),
        }, changelog

    # Momentum score (50%): trimmed mean RS composite of strong constituents
    rs_scores = [stocks_by_ticker[t].get("rs_composite", 0) for t in strong_stocks]
    momentum = trimmed_mean(rs_scores)
    momentum_score = min(momentum / 100 * 50, 50)

    prev_score = theme.get("score") or 0
    history = await _get_theme_history(name, days=7, tickers=tickers)
    age_days = len(history)

    # Estimate delta using assumed news_score=30 to decide if refresh is needed
    estimated_delta = (momentum_score + 30) - prev_score
    prev_stage = theme.get("stage", "Nascent")

    # Refresh description on Mon/Wed/Fri, or when something material changes
    today_weekday = today.weekday()  # 0=Mon, 2=Wed, 4=Fri
    is_refresh_day = today_weekday in (0, 2, 4)
    should_refresh = (
        not existing_desc
        or is_refresh_day
        or abs(estimated_delta) > 10
        or (prev_stage == "Fading" and estimated_delta >= 0)  # recovering
    )

    if should_refresh:
        news_score, fresh_desc, api_err = await _news_check(name, strong_stocks)
        if api_err:
            # Perplexity is down/rate-limited — don't penalize the theme with score=0.
            # Use neutral news_score (15, half credit) and keep existing description.
            # A 401/network error tells us nothing about whether catalysts are active.
            news_score = 15
            description = existing_desc
        else:
            description = fresh_desc
    else:
        news_score = 30
        # Not a refresh day — keep sanitized existing description
        description = existing_desc

    total_score = round(momentum_score + news_score, 1)

    # Use 3-day smoothed previous score for stage transitions.
    # Raw daily delta is too noisy: news_score swings ±30 when Perplexity finds/loses news,
    # and tiny RS shifts (delta > 3) would flip themes every day.
    history_scores = [h.get("score", 0) for h in history[-3:]] if history else []
    smoothed_prev = sum(history_scores) / len(history_scores) if history_scores else prev_score
    smooth_delta = total_score - smoothed_prev

    if smooth_delta > 8:
        stage = "Accelerating"
    elif smooth_delta < -8:
        stage = "Fading"
    elif age_days >= 5 and total_score >= 50:
        stage = "Mainstream"
    else:
        stage = prev_stage
        if stage == "Fading" and smooth_delta > 5:   # require real recovery, not noise
            stage = "Accelerating"

    # Hysteresis: require yesterday's smooth_delta to also flag the same
    # flip direction. Suppresses 1-run noise spikes — observed 5 themes
    # oscillating ≥2× in 7d. Mainstream is age-driven, not smooth_delta-driven,
    # so it's exempt. The Fading→Accelerating recovery special case (>5) is
    # also gated for symmetry. history is DESC-ordered (newest first), so
    # history[0] is yesterday's row. The shift between today's and yesterday's
    # smoothed_prev windows is one day at the tail — close enough to use today's
    # smoothed_prev as the reference for yesterday too.
    if (
        stage != prev_stage
        and stage in ("Accelerating", "Fading")
        and len(history) >= 1
    ):
        y_score = history[0].get("score") or 0
        y_delta = y_score - smoothed_prev
        confirmed = (
            (stage == "Accelerating" and y_delta > 5)
            or (stage == "Fading" and y_delta < -8)
        )
        if not confirmed:
            logger.info(
                f"Theme '{name}': flip to {stage} unconfirmed by yesterday "
                f"(y_Δ={y_delta:+.1f}); holding {prev_stage}"
            )
            await log_audit_event(
                "theme_stage_flip_held",
                f"{name}: {prev_stage}→{stage} held; y_Δ={y_delta:+.1f}",
            )
            stage = prev_stage

    # Breadth decay override — two days below threshold forces Fading regardless
    # of RS signal. Catches themes where members have rolled over even though
    # smoothed score still looks healthy.
    pct_breadth = await get_ticker_breadth_above_sma20(tickers, today)
    if (
        pct_breadth is not None
        and pct_breadth < _BREADTH_DECAY_THRESHOLD
        and (theme.get("pct_above_20sma") or 1.0) < _BREADTH_DECAY_THRESHOLD
        and stage != "Fading"
    ):
        logger.info(
            f"Theme '{name}': breadth decay {pct_breadth:.0%} (prev {theme.get('pct_above_20sma'):.0%}) — forcing Fading"
        )
        await log_audit_event(
            "theme_breadth_fade",
            f"{name}: breadth {pct_breadth:.0%}, members {len(tickers)}",
        )
        stage = "Fading"

    # Description-quality cap (#125, 2026-05-26): if Sonnet-generated
    # description fails validation (ticker concat / no member mention /
    # empty), cap stage at Nascent. Don't downgrade score — get_active_themes
    # will naturally fade Nascent themes via the 7d recency cap.
    final_tickers = list(set(tickers) | set(strong_stocks))
    descr_ok, descr_reason = _check_description_quality(name, final_tickers, description)
    if not descr_ok and stage in ("Accelerating", "Mainstream"):
        await log_audit_event(
            "theme_low_quality_description",
            f"Theme '{name}': capped {stage} → Nascent ({descr_reason})",
            f"prior_stage={stage} reason={descr_reason} "
            f"tickers={sorted(final_tickers)} description_excerpt="
            f"{(description or '')[:200]!r}",
        )
        logger.info(
            f"Theme '{name}': stage capped {stage} → Nascent "
            f"(description quality: {descr_reason})"
        )
        stage = "Nascent"

    if stage != prev_stage:
        changelog.append({
            "type": "stage_change",
            "theme": name,
            "old_stage": prev_stage,
            "new_stage": stage,
            "score": total_score,
            "smooth_delta": smooth_delta,
            "age_days": age_days,
            "ticker_count": len(tickers),
        })
        logger.info(f"Theme '{name}': {prev_stage} → {stage} (score {total_score:.1f}, Δ {smooth_delta:+.1f})")

    return {
        "theme_date": today,
        "name": name,
        "stage": stage,
        "score": total_score,
        "rs_avg": round(momentum, 1),
        "description": description,
        "tickers": final_tickers,
        "pct_above_20sma": pct_breadth,
        # #471: see the Fading-branch return above — same carry-forward.
        "parent_theme": theme.get("parent_theme"),
    }, changelog


_THEME_ASSIGNMENT_TOOL = {
    "name": "assign_stocks_to_themes",
    "description": "Assign uncovered RS leader stocks to existing themes where they clearly fit.",
    "input_schema": {
        "type": "object",
        "properties": {
            "analysis_scratchpad": {
                "type": "string",
                "description": (
                    "REQUIRED. Write your step-by-step reasoning BEFORE producing assignments. "
                    "For each uncovered stock: (1) state its core business, (2) name the candidate theme(s), "
                    "(3) explain why it fits or doesn't fit, (4) state your decision. "
                    "This reasoning is how you avoid hallucinated connections."
                ),
            },
            "assignments": {
                "type": "array",
                "description": "List of stock-to-theme assignments. Empty array if nothing fits.",
                "items": {
                    "type": "object",
                    "properties": {
                        "ticker": {"type": "string"},
                        "theme": {"type": "string", "description": "Exact existing theme name"},
                        "rationale": {"type": "string", "description": "One sentence why this stock fits"},
                    },
                    "required": ["ticker", "theme", "rationale"],
                },
            }
        },
        "required": ["analysis_scratchpad", "assignments"],
    },
}


async def _assign_uncovered_to_themes(
    uncovered_stocks: list[dict],
    existing_themes: list[dict],
    stocks_by_ticker: dict[str, dict],
    theme_exclusions: dict[str, set[str]] | None = None,
    globally_banned: set[str] | None = None,
    cooldown_set: set[tuple[str, str]] | None = None,
    protected: set[tuple[str, str]] | None = None,
) -> tuple[list[dict], list[dict]]:
    """
    Ask Claude to assign uncovered stocks to existing themes where they clearly fit.
    Returns (remaining_uncovered, changelog_entries).
    theme_exclusions: mapping of theme_name → set of tickers permanently excluded from it.
    globally_banned: tickers that have been validation-removed from ≥ N distinct themes
        in the lookback window — filtered out before reaching the LLM.
    """
    if not uncovered_stocks or not existing_themes:
        return uncovered_stocks, []

    from agents.market_intelligence.universe import TICKER_DESC

    client = _get_anthropic_client()

    # Exclude stocks with no description — clustering blind produces bogus theme assignments.
    no_desc = [s["ticker"] for s in uncovered_stocks if not TICKER_DESC.get(s["ticker"])]
    if no_desc:
        logger.warning(
            f"[theme assign] Excluding {len(no_desc)} stocks with no description from assignment: {no_desc}. "
            f"Check _ensure_descriptions — yfinance may have returned no data for these tickers."
        )
    uncovered_stocks = [s for s in uncovered_stocks if TICKER_DESC.get(s["ticker"])]

    # Global ban filter — keeps untrusted tickers out of the prompt entirely.
    if globally_banned:
        banned_in_pool = [s["ticker"] for s in uncovered_stocks if s["ticker"] in globally_banned]
        if banned_in_pool:
            logger.info(
                f"[theme assign] Globally banned tickers excluded from assignment: {banned_in_pool}"
            )
        uncovered_stocks = [s for s in uncovered_stocks if s["ticker"] not in globally_banned]

    if not uncovered_stocks:
        return [], []

    stock_lines = []
    for s in uncovered_stocks:
        ticker = s["ticker"]
        desc = TICKER_DESC.get(ticker, "")
        stock_lines.append(
            f"- {ticker} (RS {s.get('rs_composite', 0):.0f}, sector: {s.get('sector', 'Unknown')} — {desc})"
        )

    theme_lines = []
    for t in existing_themes:
        if t.get("stage") == "Fading":
            stage_note = " [Fading]"
        else:
            stage_note = ""
        theme_lines.append(
            f"- {t['name']}{stage_note}: {', '.join(t.get('tickers') or [])} — {t.get('description', '')[:120]}"
        )

    # Load active cooldowns and inject as a hard constraint in the prompt.
    # #217: run_theme_engine passes its post-rescore fetch; fallback for direct calls.
    if cooldown_set is None:
        cooldown_set = await get_cooldown_set()
    cooldown_note = ""
    if cooldown_set:
        pairs = [f"{tk} from '{th}'" for tk, th in sorted(cooldown_set)]
        cooldown_note = (
            "\n\nCOOLDOWN CONSTRAINT — DO NOT assign these stocks to these themes "
            "(recently removed by validation, 14-day cooldown active):\n"
            + "\n".join(f"- {p}" for p in pairs)
            + "\n"
        )

    prompt = f"""You are a market intelligence analyst. Assign uncovered stocks to existing themes ONLY when the fit is obvious.

EXISTING THEMES:
{chr(10).join(theme_lines)}

UNCOVERED STOCKS (RS >= 50, not in any active theme):
{chr(10).join(stock_lines)}
{cooldown_note}
Rules:
- Only assign if the stock's business CLEARLY matches the theme's thesis
- When in doubt, do NOT assign — the stock will get a chance to form its own theme
- Pick the most specific theme if multiple could fit
- Return empty array if nothing fits — that is the correct answer
- Use the EXACT theme name from the list above

OUTPUT FORMAT — IMPORTANT:
Do NOT write any free-text analysis before your tool call. All per-ticker reasoning belongs INSIDE the `assign_stocks_to_themes` tool's `analysis_scratchpad` field. Free text before the tool call wastes the output budget and can cause the response to truncate before the tool is invoked.

Call `assign_stocks_to_themes` directly with your reasoning in `analysis_scratchpad` (one short line per ticker: business + decision + theme name or "no fit"). The `assignments` array contains only the actual fits.

Consult the advisor ONLY if either of these apply:
- A stock could plausibly fit 2 different themes and you're not sure which is more specific
- A stock's description is ambiguous — it could be in this theme or something unrelated
In every other case, skip the advisor and call `assign_stocks_to_themes` immediately."""

    try:
        messages: list[dict] = [{"role": "user", "content": prompt}]
        advisor_calls = 0
        assignments = []

        while True:
            response = await client.messages.create(
                model=THEME_MODEL,
                # Bumped 1000 → 4000 (2026-05-13): silent_stop on 5/12 and 5/13
                # were caused by Sonnet exhausting max_tokens on inline analysis
                # text before reaching the tool call. 4000 gives headroom for
                # scratchpad + assignments + occasional verbose runs. Prompt
                # also restructured to push reasoning into analysis_scratchpad
                # instead of pre-tool free text.
                max_tokens=4000,
                tools=[_THEME_ASSIGNMENT_TOOL, _ADVISOR_TOOL],
                tool_choice={"type": "auto"},
                messages=messages,
            )
            # #377 cost meter — per-turn (each loop iter is a billed call).
            # S2/F9: safe wrapper — see spend_tracker.log_anthropic_call_safe
            from agents.market_intelligence.spend_tracker import log_anthropic_call_safe
            await log_anthropic_call_safe(model=THEME_MODEL, caller="theme_assignment",
                                           usage=getattr(response, "usage", None))

            tool_uses = [b for b in response.content if b.type == "tool_use"]

            if not tool_uses:
                # Silent-drop path — Sonnet returned text only after (often) an
                # advisor consultation. Log the response text so we can see
                # what reasoning the LLM offered for stopping. This was the
                # 5/4 MXL case: advisor verdicted "add to optical" but Sonnet
                # never called assign_stocks_to_themes.
                text_blocks = [
                    getattr(b, "text", "")[:500] for b in response.content
                    if getattr(b, "type", "") == "text"
                ]
                stop_text = " | ".join(t for t in text_blocks if t)[:1500] or "(no text)"
                logger.warning(
                    f"Theme assignment: model stopped without calling assign_stocks_to_themes "
                    f"(advisor_calls={advisor_calls}). Response: {stop_text[:300]}"
                )
                await log_audit_event(
                    "assignment_silent_stop",
                    summary=f"Sonnet stopped without proposing assignments after {advisor_calls} advisor call(s)",
                    detail=json.dumps({
                        "advisor_calls": advisor_calls,
                        "response_text": stop_text,
                        "candidate_pool_size": len(uncovered_stocks),
                        "candidate_tickers": [s["ticker"] for s in uncovered_stocks][:20],
                    }),
                )
                break

            assign_block = next((b for b in tool_uses if b.name == "assign_stocks_to_themes"), None)
            if assign_block:
                if advisor_calls == 0:
                    logger.info("Theme assignment: Sonnet went direct (no advisor needed)")
                else:
                    logger.info(f"Theme assignment: Sonnet used advisor {advisor_calls}x before assigning")
                assignments = assign_block.input.get("assignments", [])
                # Telemetry — log every proposal so we can compare LLM intent
                # vs final state and diagnose silent-skip filters.
                proposals = [
                    {"ticker": a.get("ticker", ""), "theme": a.get("theme", "")}
                    for a in assignments
                ]
                await log_audit_event(
                    "assignment_llm_proposed",
                    summary=f"Sonnet proposed {len(proposals)} assignment(s) (advisor_calls={advisor_calls})",
                    detail=json.dumps({
                        "advisor_calls": advisor_calls,
                        "proposals": proposals,
                        "candidate_pool_size": len(uncovered_stocks),
                        "candidate_tickers": [s["ticker"] for s in uncovered_stocks][:30],
                    }),
                )
                break

            # Handle advisor calls
            messages.append({"role": "assistant", "content": response.content})
            tool_results = []
            for block in tool_uses:
                if block.name == "consult_advisor":
                    question = block.input.get("question", "")
                    context = block.input.get("context", "")
                    if advisor_calls >= _MAX_ADVISOR_CALLS:
                        advice = "Advisor call limit reached — use your best judgment and proceed."
                        logger.warning(f"Theme assignment: advisor call limit reached — question was: {question[:120]}")
                    else:
                        advisor_calls += 1
                        logger.info(
                            f"Theme assignment: advisor call {advisor_calls}/{_MAX_ADVISOR_CALLS}\n"
                            f"  Q: {question}\n"
                            f"  Context snippet: {context[:200]}"
                        )
                        advice = await _call_advisor(question, context, caller="assignment")
                        logger.info(f"Theme assignment: advisor verdict: {advice[:300]}")
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": advice,
                    })
            messages.append({"role": "user", "content": tool_results})

    except Exception as e:
        # #273: a credit-exhaustion BadRequestError is an APIError subclass, so
        # it would otherwise be MISLABELED transient and retry forever silently.
        # Detect + alert (deduped) at the top, before any branch.
        from agents.market_intelligence.llm_health import maybe_alert_credit_exhausted
        await maybe_alert_credit_exhausted("theme assignment", e)
        # Transient Anthropic failures (5xx, network, timeout) resolve next run —
        # route to a non-`_error` event_type so they don't trip the L1 invariant.
        if isinstance(e, _THEME_TRANSIENT_EXC) and not isinstance(e, _THEME_RATELIMIT_EXC):
            logger.warning(
                f"Claude theme assignment transient failure ({type(e).__name__}: {e}) — no assignments made, will retry next run."
            )
            await log_audit_event(
                "assignment_api_failure",
                summary="Theme assignment API failure — no stocks assigned this run",
                detail=f"{type(e).__name__}: {e}",
            )
            return uncovered_stocks, []
        if isinstance(e, anthropic.RateLimitError):
            logger.error(f"Claude theme assignment rate-limited — no assignments made")
            await log_audit_event(
                "assignment_rate_limited",
                summary="Theme assignment rate-limited — no stocks assigned this run",
                detail=str(e),
            )
            return uncovered_stocks, []
        logger.error(f"Claude theme assignment FAILED ({type(e).__name__}: {e}) — no assignments made")
        await log_audit_event(
            "assignment_error",
            summary="Theme assignment error — no stocks assigned this run",
            detail=f"{type(e).__name__}: {e}",
        )
        return uncovered_stocks, []

    # Validate and apply assignments
    theme_by_name = {t["name"]: t for t in existing_themes}
    assigned_tickers: set[str] = set()
    changelog: list[dict] = []

    for a in assignments:
        ticker = a.get("ticker", "")
        theme_name = a.get("theme", "")
        rationale = a.get("rationale", "")

        # Validate theme exists. The prompt says "use the EXACT theme name from
        # the list above" — and that list renders Fading themes as
        # "Name [Fading]" (stage_note), so Sonnet faithfully echoes the suffix
        # (2026-06-10: BOT + OUST → 'Physical AI & Robotics [Fading]' both
        # silently dropped here). Strip a trailing bracketed stage label and
        # retry before giving up.
        theme = theme_by_name.get(theme_name)
        if not theme:
            stripped_name = _strip_stage_label(theme_name)
            theme = theme_by_name.get(stripped_name)
            if theme:
                theme_name = stripped_name
        if not theme:
            # AUDIT, not just a rotating log line — a dropped proposal is a
            # silent assignment failure (feedback_no_silent_failures class).
            logger.warning(f"Assignment skipped: theme '{theme_name}' not found")
            await log_audit_event(
                "assignment_theme_not_found",
                f"{ticker} → '{theme_name}' dropped: no live theme by that name",
                json.dumps({"ticker": ticker, "proposed_theme": theme_name}),
            )
            continue

        # Validate ticker is in uncovered pool
        if ticker not in {s["ticker"] for s in uncovered_stocks}:
            continue

        # Honor persistent exclusions — uses fuzzy match so renames don't bypass it
        if theme_exclusions and ticker in _get_excluded_tickers_for_theme(theme_name, theme_exclusions):
            logger.info(f"Assignment blocked: {ticker} is permanently excluded from '{theme_name}'")
            await log_audit_event(
                "assignment_skipped_exclusion",
                f"{ticker} → '{theme_name}' blocked: persistent exclusion",
                json.dumps({"ticker": ticker, "theme": theme_name}),
            )
            continue

        # Sector outlier check: reject if stock's sector is outlier vs theme
        stock_sector = stocks_by_ticker.get(ticker, {}).get("sector", "Unknown")
        theme_tickers = theme.get("tickers") or []
        theme_sectors = [stocks_by_ticker.get(tk, {}).get("sector", "Unknown") for tk in theme_tickers]
        known_sectors = [s for s in theme_sectors if s and s != "Unknown"]
        if stock_sector and stock_sector != "Unknown":
            if known_sectors and stock_sector not in known_sectors:
                logger.info(f"Assignment skipped: {ticker} sector '{stock_sector}' is outlier in '{theme_name}'")
                await log_audit_event(
                    "assignment_skipped_sector_outlier",
                    f"{ticker} ({stock_sector}) → '{theme_name}' (members: {sorted(set(known_sectors))})",
                    json.dumps({
                        "ticker": ticker, "theme": theme_name,
                        "stock_sector": stock_sector,
                        "theme_known_sectors": sorted(set(known_sectors)),
                    }),
                )
                continue
            elif not known_sectors:
                # Theme members all have unknown sectors (e.g. oil stocks outside top-300 RS).
                # The normal sector gate is blind — fall back to keyword overlap between the
                # stock's sector and the theme name+description. Zero overlap = obvious
                # cross-sector hallucination (e.g. "Electronic Technology" → "Crude Oil E&P").
                # KNOWN WEAKNESS (#46): broad sector labels like "Technology" rarely overlap
                # with specific theme keywords ("Optical", "Memory", etc.) — false-positive
                # rejections of valid Tech matches. Description-overlap fallback below is
                # the better gate; this branch should be deprecated once #46 ships the fix.
                sector_words = set(re.findall(r'\b\w{4,}\b', stock_sector.lower()))
                theme_text = (theme_name + " " + (theme.get("description") or "")).lower()
                theme_words = set(re.findall(r'\b\w{4,}\b', theme_text))
                if sector_words and theme_words and not sector_words.intersection(theme_words):
                    # Try description-overlap as a second-chance gate before rejecting.
                    # If the stock's description shares ≥2 keywords with the theme
                    # description, treat the sector-keyword check as a false rejection.
                    stock_desc = (TICKER_DESC.get(ticker) or "").lower()
                    theme_desc = (theme.get("description") or "").lower()
                    desc_words = set(re.findall(r'\b\w{4,}\b', stock_desc))
                    theme_desc_words = set(re.findall(r'\b\w{4,}\b', theme_desc))
                    desc_overlap = desc_words & theme_desc_words
                    if len(desc_overlap) >= 2:
                        logger.info(
                            f"Assignment retained: {ticker} sector '{stock_sector}' lacks theme-name "
                            f"keyword overlap but description overlaps {sorted(desc_overlap)[:5]} — "
                            f"sector-keyword check overridden by description-overlap rescue"
                        )
                        await log_audit_event(
                            "assignment_sector_kw_overridden_by_desc",
                            f"{ticker} → '{theme_name}' (desc rescue: {sorted(desc_overlap)[:5]})",
                            json.dumps({
                                "ticker": ticker, "theme": theme_name,
                                "stock_sector": stock_sector,
                                "desc_overlap_words": sorted(desc_overlap)[:10],
                            }),
                        )
                    else:
                        logger.info(
                            f"Assignment skipped: {ticker} sector '{stock_sector}' has zero keyword "
                            f"overlap with theme '{theme_name}' — likely cross-sector hallucination"
                        )
                        await log_audit_event(
                            "assignment_skipped_sector_kw",
                            f"{ticker} ({stock_sector}) → '{theme_name}' (zero kw overlap, no desc rescue)",
                            json.dumps({
                                "ticker": ticker, "theme": theme_name,
                                "stock_sector": stock_sector,
                                "theme_words_sample": sorted(theme_words)[:10],
                                "desc_overlap_words": sorted(desc_overlap)[:10] if desc_words else [],
                            }),
                        )
                        continue
        else:
            # Stock sector unknown — fall back to description keyword overlap as a sanity check.
            stock_desc = (TICKER_DESC.get(ticker) or "").lower()
            theme_desc = (theme.get("description") or "").lower()
            if stock_desc and theme_desc:
                desc_words = set(re.findall(r'\b\w{4,}\b', stock_desc))
                theme_words = set(re.findall(r'\b\w{4,}\b', theme_desc))
                if not desc_words.intersection(theme_words):
                    logger.info(
                        f"Assignment skipped: {ticker} has Unknown sector and zero "
                        f"description overlap with '{theme_name}'"
                    )
                    await log_audit_event(
                        "assignment_skipped_desc_overlap",
                        f"{ticker} → '{theme_name}' (Unknown sector + zero desc overlap)",
                        json.dumps({"ticker": ticker, "theme": theme_name}),
                    )
                    continue

        # Hard cooldown filter — safety net in case Claude ignored the prompt constraint
        if (ticker, theme_name) in cooldown_set:
            logger.info(f"Assignment blocked by cooldown: {ticker} → '{theme_name}'")
            await log_audit_event(
                "cooldown_blocked_assignment",
                summary=f"Cooldown prevented {ticker} → '{theme_name}'",
                detail="Claude ignored cooldown constraint — hard filter applied",
            )
            continue

        # Apply assignment
        if "tickers" not in theme:
            theme["tickers"] = []
        if ticker not in theme["tickers"]:
            theme["tickers"].append(ticker)
        assigned_tickers.add(ticker)
        changelog.append({
            "type": "ticker_assigned",
            "theme": theme_name,
            "ticker": ticker,
            "rationale": rationale,
        })
        logger.info(f"Assigned {ticker} → '{theme_name}': {rationale}")

    # Immediately validate net-new assignments — don't wait for Mon/Wed/Fri scheduled run.
    # This catches LLM hallucinations before they ever hit the database.
    if assigned_tickers:
        for theme in existing_themes:
            newly_added = [tk for tk in (theme.get("tickers") or []) if tk in assigned_tickers]
            if not newly_added:
                continue
            # Run membership validation (THEME_MODEL) on just the new additions in context of this theme
            validated = await _validate_theme_membership(theme["name"], theme.get("tickers") or [], changelog, protected=protected)
            removed = set(theme.get("tickers") or []) - set(validated)
            if removed:
                logger.info(f"Post-assignment validation removed {removed} from '{theme['name']}'")
                theme["tickers"] = validated
                assigned_tickers -= removed

    remaining = [s for s in uncovered_stocks if s["ticker"] not in assigned_tickers]
    return remaining, changelog


_THEME_DISCOVERY_TOOL = {
    "name": "report_themes",
    "description": "Report newly discovered investment themes from RS leader stocks.",
    "input_schema": {
        "type": "object",
        "properties": {
            "analysis_scratchpad": {
                "type": "string",
                "description": (
                    "REQUIRED but KEEP IT SHORT — one terse line per candidate cluster: the "
                    "shared catalyst + keep/drop call (e.g. 'memory makers MU/SNDK/WDC — HBM "
                    "demand, keep'). Do NOT write paragraphs or restate the rules; a verbose "
                    "scratchpad here truncates the response before the themes array is emitted "
                    "(the 6/22-24 zero-theme bug). The Rules below are the criterion — narrate, "
                    "don't re-derive."
                ),
            },
            "themes": {
                "type": "array",
                "description": "List of newly discovered themes. Empty array if none found.",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": (
                                "Specific theme name e.g. 'Edge AI Inference', not 'Technology'. "
                                "Breadth must MATCH the members: every listed ticker must "
                                "individually fit this name — if a specific label excludes some "
                                "members, broaden the name or drop those members (#214)."
                            ),
                        },
                        "thesis": {
                            "type": "string",
                            "description": "2-3 sentences on what's driving this theme and why now.",
                        },
                        "tickers": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Ticker symbols belonging to this theme (minimum 3 — do not include stocks that don't clearly fit).",
                        },
                    },
                    "required": ["name", "thesis", "tickers"],
                },
            }
        },
        "required": ["analysis_scratchpad", "themes"],
    },
}

_ADVISOR_TOOL = {
    "name": "consult_advisor",
    "description": (
        "Consult the senior advisor (Opus) for a hard judgment call. Use sparingly — "
        "only when genuinely uncertain: e.g. borderline cluster coherence, ambiguous sub-theme split, "
        "or whether stocks truly share the same catalyst vs. superficial similarity. "
        "Do NOT use for obvious decisions. Advisor gives a direct verdict."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "question": {
                "type": "string",
                "description": "The specific decision you need a second opinion on — be precise",
            },
            "context": {
                "type": "string",
                "description": "Relevant stocks, descriptions, RS scores, and your current thinking",
            },
        },
        "required": ["question", "context"],
    },
}

# Maximum advisor (Opus) calls per theme engine run — prevents runaway cost on edge cases
_MAX_ADVISOR_CALLS = 3


async def _call_advisor(question: str, context: str, caller: str = "") -> str:
    """Call Opus as a senior advisor for hard theme-clustering judgment calls."""
    client = _get_anthropic_client()
    try:
        resp = await client.messages.create(
            model=THEME_ADVISOR_MODEL,
            max_tokens=600,
            system=(
                "You are a senior market intelligence analyst (Qullamaggie/O'Neil methodology). "
                "Give direct, decisive answers. State your conclusion first, reasoning second. No hedging."
            ),
            messages=[{"role": "user", "content": f"{question}\n\nContext:\n{context}"}],
        )
        verdict = resp.content[0].text
        await log_audit_event(
            "advisor_call",
            summary=f"[{caller}] {question[:120]}",
            detail=f"Q: {question}\n\nContext: {context[:500]}\n\nVerdict: {verdict}",
        )
        # S2/F9: safe wrapper — see spend_tracker.log_anthropic_call_safe
        from agents.market_intelligence.spend_tracker import log_anthropic_call_safe
        await log_anthropic_call_safe(
            model=THEME_ADVISOR_MODEL,
            caller=f"theme_advisor_{caller}",
            usage=getattr(resp, "usage", None),
        )
        return verdict
    except Exception as e:
        logger.warning(f"Advisor call failed: {e}")
        return "Advisor unavailable — use your best judgment."


_SPLIT_TOOL = {
    "name": "propose_split",
    "description": (
        "Propose splitting one coherent sub-group out of a large theme, OR decline. "
        "Set split=null if the theme is already coherent and no clean sub-group exists."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "analysis_scratchpad": {
                "type": "string",
                "description": (
                    "REQUIRED. Reason through the split BEFORE deciding. "
                    "Which stocks share a more specific catalyst vs. the broader theme? "
                    "Is the sub-group large enough (≥3) and distinct enough to stand alone? "
                    "What would remain in the parent — is it still coherent?"
                ),
            },
            "split": {
                "description": "null if no split warranted; otherwise the sub-theme to carve out.",
                "oneOf": [
                    {"type": "null"},
                    {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string", "description": "Sub-theme name — must individually fit every ticker in the sub-group; never narrower than the members (#214)"},
                            "tickers": {"type": "array", "items": {"type": "string"}},
                            "thesis": {"type": "string", "description": "1-2 sentence thesis"},
                        },
                        "required": ["name", "tickers", "thesis"],
                    },
                ],
            }
        },
        "required": ["analysis_scratchpad", "split"],
    },
}

# Minimum stocks for a valid sub-theme split
_SPLIT_MIN_STOCKS = 3
# Maximum stocks that can be split off at once (keeps the parent coherent)
_SPLIT_MAX_STOCKS = 8
# Theme must exceed this size to be eligible for splitting
MAX_THEME_STOCKS = 20


async def _split_fat_theme(
    theme: dict,
    stocks_by_ticker: dict[str, dict],
    advisor_calls_used: int,
    reason_line: str | None = None,
) -> tuple[dict | None, int]:
    """
    Ask Sonnet (with optional Opus escalation) whether a fat theme (>MAX_THEME_STOCKS)
    has a coherent sub-group worth splitting off.

    reason_line (ADR 0032 Phase 2 Route B): optional replacement for the default
    "has grown too broad (N stocks)" opening phrase — a template arg, not a
    second prompt. None (all pre-Phase-2 callers) ⇒ the prompt is byte-identical
    to today's.

    Returns (sub_theme_dict_or_None, total_advisor_calls_used).
    The sub_theme dict has keys: name, tickers, thesis, parent_theme.
    Failures return (None, advisor_calls_used) — never block the run.
    """
    from agents.market_intelligence.universe import TICKER_DESC

    tickers = list(theme.get("tickers") or [])
    name = theme["name"]

    stock_lines = []
    for tk in sorted(tickers):
        desc = TICKER_DESC.get(tk, "")
        rs_val = (stocks_by_ticker.get(tk) or {}).get("rs_composite")
        rs_str = f" RS {int(rs_val)}" if rs_val is not None else ""
        stock_lines.append(f"  {tk}{rs_str}: {desc[:100]}")

    reason = reason_line or f"has grown too broad ({len(tickers)} stocks)"
    prompt = f"""You are analyzing a theme that {reason}.
Your job: identify ONE coherent sub-group to split off as a more specific sub-theme.

Parent theme: {name}
Stocks:
{chr(10).join(stock_lines)}

SPLIT RULES:
- Propose at most ONE split
- Sub-group must have {_SPLIT_MIN_STOCKS}–{_SPLIT_MAX_STOCKS} stocks, all ideally RS >= 70
- Must represent a TIGHTER sub-industry (e.g. "compound semi wafer fabs" within a broad photonic semi theme)
- The sub-theme NAME must fit EVERY stock in the sub-group — never a label narrower than its members (#214)
- Must NOT split by market cap, geography, or vague similarity
- Parent theme must remain coherent after the split (at least 5 stocks remaining)
- If the theme is already tight/coherent → propose split=null

Self-check before calling propose_split WITHOUT advisor:
□ Is the sub-group a clearly distinct, named sub-industry?
□ Does the parent remain coherent after the split?
□ Would a momentum trader track these separately?
If any answer is "no" or "unsure" → call consult_advisor first."""

    client = _get_anthropic_client()
    messages = [{"role": "user", "content": prompt}]
    advisor_calls = advisor_calls_used

    try:
        while True:
            response = await client.messages.create(
                model=THEME_MODEL,
                max_tokens=800,
                tools=[_SPLIT_TOOL, _ADVISOR_TOOL],
                tool_choice={"type": "auto"},
                messages=messages,
            )
            # #377 cost meter — per-turn (each loop iter is a billed call).
            # S2/F9: safe wrapper — see spend_tracker.log_anthropic_call_safe
            from agents.market_intelligence.spend_tracker import log_anthropic_call_safe
            await log_anthropic_call_safe(model=THEME_MODEL, caller="theme_split",
                                           usage=getattr(response, "usage", None))

            tool_uses = [b for b in response.content if b.type == "tool_use"]

            if not tool_uses:
                # No tool called — treat as "no split"
                logger.info(f"[fat-theme split] '{name}': Sonnet returned no tool call → no split")
                return None, advisor_calls

            messages.append({"role": "assistant", "content": response.content})
            tool_results = []

            for block in tool_uses:
                if block.name == "propose_split":
                    split = block.input.get("split")
                    if not split:
                        logger.info(f"[fat-theme split] '{name}': Sonnet declined split")
                        await log_audit_event(
                            "fat_theme_no_split",
                            summary=f"No split: {name} ({len(tickers)} stocks)",
                            detail="Sonnet found theme already coherent.",
                        )
                        return None, advisor_calls

                    sub_tickers = [t.upper() for t in split.get("tickers", [])]
                    # Validate: tickers must be in parent, count in range
                    valid_tickers = [t for t in sub_tickers if t in tickers]
                    if len(valid_tickers) < _SPLIT_MIN_STOCKS:
                        logger.warning(f"[fat-theme split] '{name}': proposed split has too few valid tickers ({valid_tickers})")
                        return None, advisor_calls

                    sub_theme = {
                        "name": split["name"],
                        "tickers": valid_tickers,
                        "thesis": split.get("thesis", ""),
                        "parent_theme": name,
                    }
                    logger.info(
                        f"[fat-theme split] '{name}' → sub-theme '{sub_theme['name']}' "
                        f"({len(valid_tickers)} stocks: {valid_tickers})"
                    )
                    await log_audit_event(
                        "theme_split",
                        summary=f"Split: '{sub_theme['name']}' from '{name}' ({len(valid_tickers)} stocks)",
                        detail=f"Tickers: {valid_tickers}\nThesis: {sub_theme['thesis']}",
                    )
                    return sub_theme, advisor_calls

                elif block.name == "consult_advisor":
                    question = block.input.get("question", "")
                    context_str = block.input.get("context", "")
                    if advisor_calls >= _MAX_ADVISOR_CALLS:
                        advice = "Advisor call limit reached — use your best judgment."
                        logger.warning(f"[fat-theme split] advisor limit reached for '{name}'")
                    else:
                        advisor_calls += 1
                        logger.info(f"[fat-theme split] advisor call {advisor_calls}/{_MAX_ADVISOR_CALLS} for '{name}'")
                        advice = await _call_advisor(question, context_str, caller="split")
                        logger.info(f"[fat-theme split] advisor verdict: {advice[:300]}")

                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": advice,
                    })

            if tool_results:
                messages.append({"role": "user", "content": tool_results})
            else:
                break

    except Exception as e:
        # #376: credit exhaustion silently skips the split — alert it (deduped).
        from agents.market_intelligence.llm_health import maybe_alert_credit_exhausted
        await maybe_alert_credit_exhausted("theme split", e)
        logger.warning(f"[fat-theme split] '{name}': failed ({e}) — skipping split")

    return None, advisor_calls


async def _nominate_dominant_split_themes(
    all_themes: list[dict],
    stocks_by_ticker: dict[str, dict],
    *,
    arm_enabled: bool,
) -> list[dict]:
    """ADR 0032 Phase 2 Route B — bounded deliberate split nomination for a
    sole-sub-theme ecosystem-dominant theme (design doc §1.2). Behind
    THEME_SUBTHEME_ARM: arm OFF → [] with NO DB access (byte-identical engine).

    Eligibility (all illustrative pins — the §1.4 Part-2 grid sets them):
      stage not Fading/Retired AND no parent_theme (existing conditions)
      AND mapped to a real ecosystem (not None / E-UNASSIGNED)
      AND the ONLY active theme mapped to that ecosystem tonight  ← self-disarms:
          after a successful split the eco has 2 themes next night
      AND ≥ SPLIT_DOM_MIN_MEMBERS members AND ≥ SPLIT_DOM_MIN_STRONG RS-80+ members
      AND not already over MAX_THEME_STOCKS (that is the existing fat trigger's job)

    Returns ≤ DOM_SPLITS_PER_NIGHT themes (≤1 split/theme is structural — one
    `_split_fat_theme` call per theme in the caller's loop). Emits
    `theme_dominant_split_eligible` per nominee BEFORE the LLM runs — the
    trigger telemetry fires even when Sonnet declines the split. Never raises."""
    if not arm_enabled:
        return []
    try:
        from agents.market_intelligence.db import get_all_theme_ecosystems
        eco_map = await get_all_theme_ecosystems()
    except Exception as e:
        logger.warning(f"[dominant split] eco mapping fetch failed — Route B skipped: {e}")
        return []
    try:
        active = [t for t in all_themes if t.get("stage") not in ("Fading", "Retired")]
        from collections import Counter
        eco_counts = Counter(
            eco_map[t["name"]] for t in active if eco_map.get(t["name"])
        )
        nominees: list[dict] = []
        for t in active:
            if len(nominees) >= DOM_SPLITS_PER_NIGHT:
                break
            if t.get("parent_theme"):
                continue  # never split a sub-theme further
            eco = eco_map.get(t["name"])
            if not eco or eco == "E-UNASSIGNED":
                continue
            if eco_counts.get(eco, 0) != 1:
                continue  # sole-sub-theme only — the self-disarm predicate
            tickers = t.get("tickers") or []
            if len(tickers) < SPLIT_DOM_MIN_MEMBERS:
                continue
            if len(tickers) > MAX_THEME_STOCKS:
                continue  # already fat — the existing >20 trigger owns it
            strong = sum(
                1 for tk in tickers
                if ((stocks_by_ticker.get(tk) or {}).get("rs_composite") or 0) >= 80
            )
            if strong < SPLIT_DOM_MIN_STRONG:
                continue  # missing RS = not strong
            nominees.append(t)
            await log_audit_event(
                "theme_dominant_split_eligible",
                summary=f"Route B: '{t['name']}' is ecosystem-dominant ({eco}) — split nominee",
                detail=(
                    f"eco={eco} members={len(tickers)} rs80_plus={strong} "
                    f"pins: members>={SPLIT_DOM_MIN_MEMBERS} strong>={SPLIT_DOM_MIN_STRONG} "
                    f"cap={DOM_SPLITS_PER_NIGHT}/night"
                ),
            )
        return nominees
    except Exception as e:
        logger.warning(f"[dominant split] Route B nomination failed — skipped: {e}")
        return []


async def _apply_carryforward_deterministic_filter(
    themes: list[dict],
    globally_banned: set[str],
    cooldown_set: set[tuple[str, str]],
    stocks_by_ticker: dict[str, dict],
) -> int:
    """Daily strip-only filter for theme carryforward members (2026-05-15).

    Closes the adds/removes asymmetry — the bug class that let 4 oncology
    biotechs (RVMD/AVBP/DAWN/AJRD) cycle through Satellite-named themes for
    ~3 weeks despite Fix B global ban + validation cooldowns. The theme
    engine ADDS daily (assignment + discovery) but historically only REMOVED
    semantically via LLM validation on Mon/Wed/Fri. Deterministic removes
    (banned tickers, active cooldowns, sector outliers) never ran against
    carryforward members at all — they survived every non-validation day.

    This filter runs daily, BEFORE assignment + discovery. For each
    carryforward theme, strip members that fail any of:
      1. Ticker is in Fix B's globally_banned set
      2. (ticker, theme_name) has an active validation cooldown
      3. Ticker is a sector outlier (singleton sector when ≥3 members)

    STRIP-ONLY: never retires themes here. Themes with 0 members may be
      a) refilled by assignment LLM (uncovered ticker fits the thesis), OR
      b) caught by existing retirement logic AFTER assignment+discovery
         (recency-cap, PRUNE_MIN_TICKERS, etc.)
    Deferring retirement avoids the "theme dies before LLM can refill it"
    bug class.

    Emits one aggregate audit event per affected theme; reuses existing
    primitives (no new schema, no new LLM call, no new write authorities).
    Returns the count of tickers stripped across all themes.
    """
    from collections import Counter

    stripped_total = 0
    for theme in themes:
        tickers = list(theme.get("tickers") or [])
        if not tickers:
            continue
        theme_name = theme["name"]

        banned_hits = [t for t in tickers if t in globally_banned]
        cooldown_hits = [
            t for t in tickers if (t, theme_name) in cooldown_set
        ]

        # Sector outliers: reuse _strip_sector_outliers logic (singleton sector
        # when ≥3 members + at least one non-Unknown sector). The existing
        # function operates per-merge; here we apply the same logic per-theme
        # without that gate.
        sector_outliers: list[str] = []
        if len(tickers) >= 3:
            sector_of = {
                t: stocks_by_ticker.get(t, {}).get("sector") or "Unknown"
                for t in tickers
            }
            known = [s for s in sector_of.values() if s != "Unknown"]
            if known:
                counts = Counter(known)
                singleton_sectors = {
                    s for s, n in counts.items() if n == 1 and len(counts) > 1
                }
                sector_outliers = [
                    t for t in tickers if sector_of[t] in singleton_sectors
                ]

        to_remove = set(banned_hits) | set(cooldown_hits) | set(sector_outliers)
        if not to_remove:
            continue

        new_tickers = [t for t in tickers if t not in to_remove]
        theme["tickers"] = new_tickers
        stripped_total += len(to_remove)

        # One aggregate audit per affected theme (mirrors theme_pass1_protect_strip
        # pattern). Per-ticker rows would balloon the audit log without adding
        # signal beyond what the reason buckets already convey.
        reason_parts = []
        if banned_hits:
            reason_parts.append(f"banned={sorted(banned_hits)}")
        if cooldown_hits:
            reason_parts.append(f"cooldown={sorted(cooldown_hits)}")
        if sector_outliers:
            reason_parts.append(f"sector_outlier={sorted(sector_outliers)}")
        await log_audit_event(
            "theme_carryforward_filter_stripped",
            summary=(
                f"{theme_name}: stripped {len(to_remove)} ticker(s) "
                f"({', '.join(p.split('=')[0] for p in reason_parts)})"
            ),
            detail=(
                f"theme={theme_name}\n"
                f"pre_size={len(tickers)} post_size={len(new_tickers)}\n"
                + "\n".join(reason_parts)
            ),
        )

    if stripped_total > 0:
        logger.info(
            f"Carryforward deterministic filter: stripped {stripped_total} "
            f"ticker(s) across themes (banned + cooldown + sector outliers)"
        )
    return stripped_total


def _strip_stage_label(name: str) -> str:
    """'Name [Fading]' → 'Name'. The assignment prompt renders Fading themes
    with a trailing stage label AND tells Sonnet to copy the EXACT name from
    that list — so the echo is the model following instructions, and the
    lookup must tolerate it (2026-06-10 BOT/OUST silent-drop class). Trailing
    alphabetic bracket groups only; bracketed years/figures mid-name survive."""
    return re.sub(r"\s*\[[A-Za-z]+\]\s*$", "", name or "")


def _strip_sector_outliers(theme: dict, stocks_by_ticker: dict[str, dict]) -> dict:
    """
    Remove tickers whose sector is a lone outlier vs the rest of the theme.

    Logic: find the majority sector group. Any ticker in a completely different
    top-level sector (e.g. Consumer Cyclical in a metals theme) gets dropped —
    unless it's Unknown (no sector data), in which case it's kept.

    A ticker is an outlier if its sector doesn't appear in the majority and it's
    the only one with that sector.
    """
    tickers = list(theme.get("tickers", []))
    if len(tickers) < 3:
        return theme

    from collections import Counter
    sector_of = {t: stocks_by_ticker.get(t, {}).get("sector") or "Unknown" for t in tickers}
    known = [s for s in sector_of.values() if s != "Unknown"]
    if not known:
        return theme

    counts = Counter(known)
    # A sector is "minority of 1" if it appears exactly once and there are other sectors
    singleton_sectors = {s for s, n in counts.items() if n == 1 and len(counts) > 1}

    clean_tickers = [t for t in tickers if sector_of[t] not in singleton_sectors]
    if len(clean_tickers) < len(tickers):
        dropped = [t for t in tickers if t not in clean_tickers]
        logger.info(f"Theme '{theme['name']}': dropped sector outliers {dropped}")

    return {**theme, "tickers": clean_tickers}


async def _discover_new_themes(
    uncovered_stocks: list[dict],
    existing_themes: list[dict],
    stocks_by_ticker: dict[str, dict],
    velocity_leaders: list[dict] | None = None,
    turners: list[dict] | None = None,
    elite_covered: list[dict] | None = None,
    theme_exclusions: dict[str, set[str]] | None = None,
    correlation_clusters: list[dict] | None = None,
    globally_banned: set[str] | None = None,
    recall_mode: bool = False,
) -> list[dict]:
    """
    Ask Claude to identify new themes from uncovered RS leaders + velocity accelerators + turners.
    Also receives elite covered stocks (RS 80+) that may need sub-theme splits.
    Uses structured tool use — output is schema-guaranteed, no JSON parsing.
    theme_exclusions: mapping of theme_name → set of tickers excluded from it.
    Exclusions are applied as a post-filter: if Claude places an excluded ticker in a
    theme whose name is semantically related to the original exclusion theme (fuzzy match),
    the ticker is silently stripped before the theme is returned. This prevents excluded
    tickers from sneaking back in via newly-discovered themes with different names.
    """
    client = _get_anthropic_client()

    from agents.market_intelligence.universe import TICKER_DESC

    # Exclude stocks with no description — clustering blind produces bogus themes.
    no_desc = [s["ticker"] for s in uncovered_stocks if not TICKER_DESC.get(s["ticker"])]
    if no_desc:
        logger.warning(
            f"[theme discover] Excluding {len(no_desc)} stocks with no description from discovery: {no_desc}. "
            f"Check _ensure_descriptions — yfinance may have returned no data for these tickers."
        )
    uncovered_stocks = [s for s in uncovered_stocks if TICKER_DESC.get(s["ticker"])]

    # Global ban filter — strip untrusted tickers from every input pool the prompt sees.
    # Velocity/turner pools come from separate data paths, so banned tickers can re-enter
    # discovery even when assignment already filtered them out of `uncovered`.
    if globally_banned:
        def _drop_banned(pool: list[dict] | None, label: str) -> list[dict]:
            if not pool:
                return pool or []
            banned_hit = [s["ticker"] for s in pool if s["ticker"] in globally_banned]
            if banned_hit:
                logger.info(
                    f"[theme discover] Globally banned tickers excluded from {label}: {banned_hit}"
                )
            return [s for s in pool if s["ticker"] not in globally_banned]

        uncovered_stocks = _drop_banned(uncovered_stocks, "uncovered")
        velocity_leaders = _drop_banned(velocity_leaders, "velocity")
        turners = _drop_banned(turners, "turners")
        # elite_covered is "stocks already in themes" — they passed historical validation,
        # don't strip them; sub-theme analysis on existing assignments stays useful.

    def _stock_line(s: dict, theme_label: str = "") -> str:
        ticker = s["ticker"]
        desc = TICKER_DESC.get(ticker, "")
        theme_part = f" [in: {theme_label}]" if theme_label else ""
        return f"- {ticker} (RS {s.get('rs_composite', 0):.0f}, rank #{s.get('rs_rank', '?')}, sector: {s.get('sector', 'Unknown')} — {desc}){theme_part}"

    stock_lines = "\n".join(_stock_line(s) for s in uncovered_stocks)

    # Elite covered stocks (RS 80+) shown with their current theme
    elite_block = ""
    if elite_covered:
        elite_lines = "\n".join(_stock_line(s, s.get("_current_theme", "")) for s in elite_covered)
        elite_block = f"""
ELITE RS LEADERS ALREADY IN THEMES (RS 80+, shown for sub-theme analysis):
These stocks are assigned to existing themes but may belong to a MORE SPECIFIC sub-theme.
Example: MU in "AI Infrastructure" might actually belong to a distinct "AI Memory & Storage" theme.
If you see a cluster of 2+ stocks here that share a specific sub-thesis different from their current theme, propose the sub-theme.
{elite_lines}
"""

    existing_block = ""
    if existing_themes:
        existing_lines = "\n".join(
            f"- {t['name']} [{t.get('stage')}] (score {t.get('score', 0):.0f}): {', '.join(t.get('tickers') or [])}"
            for t in existing_themes
        )
        existing_block = f"\nEXISTING ACTIVE THEMES (for context — do NOT re-create these, but you MAY propose sub-themes that split off a more specific cluster):\n{existing_lines}\n"

    velocity_block = ""
    if velocity_leaders:
        def _vel_profile(s: dict) -> str:
            ticker = s["ticker"]
            desc = TICKER_DESC.get(ticker, "")
            desc_part = f" — {desc}" if desc else ""
            parts = [f"RS {s.get('rs_now', 0):.0f}"]
            for wk, key in [(1, "v1w"), (2, "v2w"), (3, "v3w"), (4, "v4w")]:
                v = s.get(key)
                if v is not None:
                    parts.append(f"wk{wk}:{'+' if v >= 0 else ''}{v:.1f}")
            consistent = all(
                s.get(k, 0) >= 0 for k in ["v1w", "v2w", "v3w", "v4w"]
                if s.get(k) is not None
            )
            flag = " ↑SUSTAINED" if consistent else ""
            return f"- {ticker} ({', '.join(parts)}, sector: {s.get('sector', 'Unknown')}{desc_part}){flag}"

        vel_lines = "\n".join(_vel_profile(s) for s in velocity_leaders[:20])
        velocity_block = f"""
STOCKS WITH SUSTAINED MULTI-WEEK RS ACCELERATION (not yet in any theme):
These stocks have been quietly rising in relative strength over multiple consecutive weeks.
This is the early signal — the market may be accumulating these before the move is obvious.
wk1/wk2/wk3/wk4 = RS change each week (wk1 = most recent). ↑SUSTAINED = rising all weeks.
{vel_lines}
"""

    turners_block = ""
    if turners:
        def _turner_profile(s: dict) -> str:
            ticker = s["ticker"]
            desc = TICKER_DESC.get(ticker, "")
            desc_part = f" — {desc}" if desc else ""
            rs_now = s.get("rs_now", 0)
            rs_earliest = s.get("rs_earliest", 0)
            weeks = s.get("consecutive_up_weeks", 0)
            return f"- {ticker} (RS {rs_now:.0f}, was {rs_earliest:.0f} → {weeks}wk streak, sector: {s.get('sector', 'Unknown')}{desc_part})"

        turner_lines = "\n".join(_turner_profile(s) for s in turners[:20])
        turners_block = f"""
ROTATION CANDIDATES — TURNING FROM WEAK TO IMPROVING (not yet in any theme):
These stocks had weak RS (below 30) but have been rising for 3+ consecutive weeks.
This is the earliest rotation signal — a sector quietly turning before anyone notices.
Look for CLUSTERS here — if 3+ stocks from the same sector are all turning, that's a potential emerging theme.
{turner_lines}
"""

    # Build correlation cluster block if any clusters are relevant (have uncovered tickers)
    covered_in_themes = {tk for t in existing_themes for tk in (t.get("tickers") or [])}
    cluster_block = ""
    if correlation_clusters:
        relevant = [
            c for c in correlation_clusters
            if any(t not in covered_in_themes for t in c["tickers"])
        ]
        if relevant:
            cluster_lines = "\n".join(
                f"- Cluster {chr(65 + i)} ({c['member_count']} stocks, corr {c['mean_corr']:.2f}, "
                f"avg RS {c['avg_rs']:.0f}): {', '.join(c['tickers'])}"
                for i, c in enumerate(relevant)
            )
            cluster_block = f"""
CORRELATION CLUSTERS (beta-adjusted residual correlation ≥ 0.85, 20-day window):
These stocks have been moving together statistically before any narrative crystallized — potential emerging themes.
{cluster_lines}

If a cluster maps to a clear business thesis, propose it as a Nascent theme.
If the correlation reason is unclear, do NOT force a theme — leave the stocks uncovered.
IMPORTANT: If a cluster forms a valid theme, invent a specific descriptive business name (e.g., 'Optical Networking', 'Uranium Miners'). Do NOT name it 'Cluster A', 'Cluster B', or any placeholder — those labels are internal identifiers only.
"""

    # Disposition rules — PRECISION for the live engine (default), RECALL for the ADR-0007
    # shadow. The shadow is a human-reviewed candidate table, not live themes; instructing
    # "return zero / exclude when in doubt" (live's precision bias) made it report nothing
    # even for clean uncovered clusters (#173). recall_mode flips that for the shadow only.
    recall_disposition = (
        "- RECALL PASS — this is a shadow candidate-generation run reviewed by a human, NOT live themes.\n"
        "  Bias toward PROPOSING: surface EVERY plausible nascent cohort, including 2-stock clusters and\n"
        "  cross-sector narrative/policy themes (e.g. a drone/defense cohort on a govt-funding catalyst).\n"
        "  Over-surfacing is expected and desired here — a human prunes later.\n"
        "- Do NOT default to zero — report no themes ONLY if the stocks are genuinely unrelated."
        if recall_mode else
        "- When in doubt whether a stock belongs — exclude it. A smaller, correct theme beats a larger, wrong one.\n"
        "- Return zero themes if no clear cluster exists — that is the correct answer"
    )
    prompt = f"""You are a market intelligence analyst using Marios Stamatoudis's theme discovery methodology.

Themes emerge BOTTOM-UP from price action. The real alpha is finding sub-themes BEFORE they become common knowledge.
{existing_block}{elite_block}{velocity_block}{turners_block}{cluster_block}
RS LEADERS NOT YET IN ANY ACTIVE THEME:
{stock_lines}

Task: Identify NEW distinct investment themes from ALL the stocks above. You have two jobs:

1. DISCOVER new themes from uncovered stocks, velocity accelerators, and rotation candidates
2. SPLIT sub-themes from the elite covered stocks — if 2+ elite stocks share a specific thesis DIFFERENT from their current theme assignment, propose a new sub-theme

Use the company descriptions to understand what each stock actually does. Two stocks in the same "sector" may serve completely different markets. Conversely, stocks in different sectors may share a specific catalyst (e.g., a memory chip maker and an equipment company both driven by HBM demand).

Prioritize the VELOCITY ACCELERATORS and ROTATION CANDIDATES — a stock rising in RS for 3-4 consecutive weeks is a stronger signal than a stock with high but static RS.

Rules:
- A theme REQUIRES at least 2 stocks — a 2-stock cluster is valid as a "Nascent" early signal
- Every stock must clearly operate in the SAME specific sub-industry or share the SAME business driver
  - GOOD: DRAM/NAND memory makers, optical networking equipment, uranium miners, AI inference chips
  - BAD: mixing a REIT with a commodity stock, adding a consumer name to an industrial theme
  - BAD: grouping by vague similarity ("they're both tech", "both benefit from AI")
- Name themes specifically ("AI Memory & HBM" not "Technology" or "Semiconductors")
- NAME-BREADTH RULE: the name must be exactly as broad as the members — EVERY ticker you list must individually fit the name. If your best specific label excludes some members (e.g. "Pure-Play Hydraulic Fracturing" while the list holds XOM/CVX integrated majors), either broaden the name to what the members actually share ("Oil & Gas E&P") or drop/split the non-fitting members. Membership validation later treats the NAME as ground truth and evicts every member that doesn't match it — a name narrower than its members guarantees the cluster gets shredded.
- A stock CAN move from an existing theme to a new sub-theme if the sub-theme is more specific
- A stock should appear in at most 2 themes. Do NOT include a stock in a new theme if it already appears in 2+ existing themes (check the list above)
{recall_disposition}
- Focus on what the market is pricing in RIGHT NOW based on price action, not macro narratives

OUTPUT FORMAT — IMPORTANT:
Do NOT write any free-text analysis before your tool call. All clustering reasoning belongs INSIDE the `report_themes` tool's `analysis_scratchpad` field (kept terse — one line per cluster). Free text before the tool call wastes the output budget and can cause the response to truncate before the themes array is emitted — that is exactly the bug that produced zero new themes 6/22-24.

Consult the advisor ONLY if one of these genuinely applies:
- A stock fits multiple possible themes and you're not sure which is the better home
- You have a borderline cluster and aren't confident it's a real theme vs. coincidence
- Stocks share a sector label but their actual business drivers feel different to you
In every other case, skip the advisor and call `report_themes` immediately, with your terse reasoning in `analysis_scratchpad`."""

    try:
        client = _get_anthropic_client()
        messages: list[dict] = [{"role": "user", "content": prompt}]
        advisor_calls = 0
        force_report = False   # once True, compel report_themes so the model commits its
                               # best judgment instead of dithering on the advisor or
                               # stopping silently — the #173 shadow-death class (a real
                               # drone/UAS cluster was discovered, deliberated, then lost).
        loop_guard = 0         # hard ceiling — defense in depth against a runaway loop.

        # #325 (2026-06-18): bumped 1500→4000 — INFRA CAPACITY, not a criterion change. The
        # per-call telemetry below makes the stop_reason DURABLE (the funnel was logs-only and
        # died on container recreate).
        #
        # ROOT FIX (2026-06-25): the cap bump alone did NOT cure the truncation — telemetry showed
        # stop=max_tokens out_tok=4000 on the FORCED retry too (forced=True), so the budget was
        # being consumed INSIDE the bounded tool output, not just on pre-tool deliberation. Two
        # drivers, both now fixed by mirroring the proven assignment path (line ~2117, which had
        # the identical 5/12-13 silent_stop and stayed fixed):
        #   (1) the old `report_themes.analysis_scratchpad` demanded a HEAVY per-group 3-part
        #       structured essay; over five input pools it alone overflowed 4000 inside the tool
        #       call → truncated, unparseable themes → 0. Now a TERSE one-line-per-cluster scratchpad
        #       (schema ~2445) keeps the emitted JSON bounded.
        #   (2) the old prompt's "ask yourself… Consult the advisor FIRST" framing INDUCED pre-tool
        #       free-reasoning text on the tool_choice=auto call → it burned the budget and stopped
        #       with tool_uses=0. Replaced with assignment's recipe: a no-free-text-before-tool guard
        #       + advisor-only-on-genuine-ambiguity + reason-in-scratchpad.
        # tool_choice stays AUTO (not forced-from-start) so the #173 advisor path survives; the
        # existing force_report fallback now actually LANDS because the forced call's output is
        # bounded. Criterion is UNCHANGED — the Rules block + #214 breadth + _validate_theme_membership
        # / _strip_sector_outliers gates own rejection; only narration verbosity changed.
        _DISCOVERY_MAX_TOKENS = 4000

        while True:
            loop_guard += 1
            if loop_guard > 8:
                logger.warning("Theme discovery: loop guard tripped (>8 iterations) — returning no themes")
                return []
            response = await client.messages.create(
                model=THEME_MODEL,
                max_tokens=_DISCOVERY_MAX_TOKENS,
                tools=[_THEME_DISCOVERY_TOOL, _ADVISOR_TOOL],
                tool_choice=({"type": "tool", "name": "report_themes"} if force_report else {"type": "auto"}),
                messages=messages,
            )

            tool_uses = [b for b in response.content if b.type == "tool_use"]

            # DURABLE per-call diagnostic (mi_audit_log survives container recreate, unlike the
            # logs). stop_reason='max_tokens' = truncated before the tool call (capacity); 'end_turn'
            # with 0 tool_uses = the model chose to stop/answer in prose (criterion). The #325 fork.
            try:
                await log_audit_event(
                    "theme_discovery_llm_call",
                    summary=(f"stop={response.stop_reason} out_tok={response.usage.output_tokens} "
                             f"forced={force_report} tool_uses={len(tool_uses)} iter={loop_guard}"),
                    detail=json.dumps({
                        "stop_reason": response.stop_reason,
                        "output_tokens": response.usage.output_tokens,
                        "max_tokens": _DISCOVERY_MAX_TOKENS,
                        "force_report": force_report,
                        "n_tool_uses": len(tool_uses),
                        "tool_names": [b.name for b in tool_uses],
                        "iteration": loop_guard,
                    }),
                )
            except Exception:
                pass  # telemetry must never break the run

            # COST METER (#377). Log this turn's token cost to api_usage. Each
            # iteration of this multi-turn loop is a separate billed call, so we
            # log per-turn (not once at the end). A logging/DB failure must NEVER
            # alter discovery output (the HARD CONSTRAINT): logging is additive
            # observability only. S2/F9: safe wrapper — see
            # spend_tracker.log_anthropic_call_safe. We deliberately do NOT route
            # this loop through invoke_forced_tool / a forced-tool transport —
            # that would change tool_choice and break the #173 advisor/
            # force_report path. ADDITIVE is the correct shape for the loop.
            from agents.market_intelligence.spend_tracker import log_anthropic_call_safe
            await log_anthropic_call_safe(
                model=THEME_MODEL,
                caller="theme_discovery",
                usage=getattr(response, "usage", None),
            )

            # Model produced no tool call. Don't silently discard the whole discovery
            # pass (#173: the ADR-0007 shadow wrote 0 rows for days this way) — compel one
            # final report_themes so the model commits its best judgment first. A forced
            # report can still return themes=[] when there's genuinely no cluster, so this
            # recovers lost themes without inventing any.
            if not tool_uses:
                if not force_report:
                    logger.warning("Theme discovery: model stopped without calling report_themes — forcing a final report")
                    force_report = True
                    continue
                logger.warning("Theme discovery: no themes even when report_themes was forced — returning empty")
                return []

            # If report_themes was called, we're done
            report_block = next((b for b in tool_uses if b.name == "report_themes"), None)
            if report_block:
                if advisor_calls == 0:
                    logger.info("Theme discovery: Sonnet went direct (no advisor needed)")
                else:
                    logger.info(f"Theme discovery: Sonnet used advisor {advisor_calls}x before reporting")
                raw_themes = report_block.input.get("themes", [])
                valid = [t for t in raw_themes if len(t.get("tickers", [])) >= NEW_THEME_MIN_STOCKS]
                result_themes = []
                for t in valid:
                    t = _strip_sector_outliers(t, stocks_by_ticker)
                    # Post-LLM ban filter — catches banned tickers reintroduced via
                    # correlation_clusters or LLM ignoring the absent input.
                    if globally_banned:
                        tickers_in = t.get("tickers", [])
                        banned_hit = [tk for tk in tickers_in if tk in globally_banned]
                        if banned_hit:
                            logger.info(
                                f"Discovery post-filter: stripped globally-banned {banned_hit} "
                                f"from new theme '{t.get('name')}'"
                            )
                            t = {**t, "tickers": [tk for tk in tickers_in if tk not in globally_banned]}
                    # Post-filter: strip tickers that are excluded from any semantically
                    # related theme — catches CAR sneaking into a renamed data-center theme
                    if theme_exclusions:
                        theme_name = t.get("name", "")
                        excluded_here = _get_excluded_tickers_for_theme(theme_name, theme_exclusions)
                        if excluded_here:
                            tickers_in = t.get("tickers", [])
                            removed = [tk for tk in tickers_in if tk in excluded_here]
                            if removed:
                                logger.info(
                                    f"Discovery post-filter: stripped {removed} from new theme "
                                    f"'{theme_name}' — active exclusions match (fuzzy)"
                                )
                                t = {**t, "tickers": [tk for tk in tickers_in if tk not in excluded_here]}
                    if len(t.get("tickers", [])) >= NEW_THEME_MIN_STOCKS:
                        result_themes.append(t)
                return result_themes

            # Handle advisor calls — Opus is consulted, result returned as tool result
            messages.append({"role": "assistant", "content": response.content})
            tool_results = []
            for block in tool_uses:
                if block.name == "consult_advisor":
                    question = block.input.get("question", "")
                    context = block.input.get("context", "")
                    if advisor_calls >= _MAX_ADVISOR_CALLS:
                        advice = "Advisor call limit reached — use your best judgment and proceed."
                        logger.warning(f"Theme discovery: advisor call limit reached — question was: {question[:120]}")
                    else:
                        advisor_calls += 1
                        logger.info(
                            f"Theme discovery: advisor call {advisor_calls}/{_MAX_ADVISOR_CALLS}\n"
                            f"  Q: {question}\n"
                            f"  Context snippet: {context[:200]}"
                        )
                        advice = await _call_advisor(question, context, caller="discovery")
                        logger.info(f"Theme discovery: advisor verdict: {advice[:300]}")
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": advice,
                    })
            messages.append({"role": "user", "content": tool_results})
            # Advisor budget spent → compel a commit on the next turn rather than let the
            # model loop on "limit reached, proceed" and ultimately report nothing (#173).
            if advisor_calls >= _MAX_ADVISOR_CALLS:
                force_report = True

    except Exception as e:
        # #273: a credit-exhaustion BadRequestError is an APIError subclass, so
        # it would otherwise be MISLABELED transient and retry forever silently.
        # Detect + alert (deduped) at the top, before any branch.
        from agents.market_intelligence.llm_health import maybe_alert_credit_exhausted
        await maybe_alert_credit_exhausted("theme discovery", e)
        # Transient Anthropic failures (5xx, network, timeout) resolve next run —
        # route to a non-`_error` event_type so they don't trip the L1 invariant.
        if isinstance(e, _THEME_TRANSIENT_EXC) and not isinstance(e, _THEME_RATELIMIT_EXC):
            logger.warning(
                f"Claude new theme discovery transient failure ({type(e).__name__}: {e}) — no new themes this run, will retry next run."
            )
            await log_audit_event(
                "discovery_api_failure",
                summary="Theme discovery API failure — no new themes discovered this run",
                detail=f"{type(e).__name__}: {e}",
            )
            return []
        if isinstance(e, anthropic.RateLimitError):
            logger.error("Claude new theme discovery rate-limited — no new themes this run")
            await log_audit_event(
                "discovery_rate_limited",
                summary="Theme discovery rate-limited — no new themes discovered this run",
                detail=str(e),
            )
            return []
        logger.error(f"Claude new theme discovery FAILED ({type(e).__name__}: {e}) — no new themes this run")
        await log_audit_event(
            "discovery_error",
            summary="Theme discovery error — no new themes discovered this run",
            detail=f"{type(e).__name__}: {e}",
        )
        return []


async def _score_new_theme(
    theme: dict,
    stocks_by_ticker: dict[str, dict],
    today: date,
) -> dict:
    """Score a newly discovered theme."""
    tickers = theme.get("tickers", [])

    rs_scores = [stocks_by_ticker[t].get("rs_composite", 0) for t in tickers if t in stocks_by_ticker]
    momentum = trimmed_mean(rs_scores) if rs_scores else 0
    momentum_score = min(momentum / 100 * 50, 50)

    news_score, fresh_desc, _api_err = await _news_check(theme["name"], tickers)
    # For brand-new themes, API error → use thesis as description, neutral score
    if _api_err:
        news_score = 15

    return {
        "theme_date": today,
        "name": theme["name"],
        "stage": "Nascent",
        "score": round(momentum_score + news_score, 1),
        "rs_avg": round(momentum, 1),
        "description": fresh_desc or theme.get("thesis", ""),
        "tickers": tickers,
    }


# Sentinel cap: ONE theme per Stage-A stem family within the group (plus one
# shared slot for unstemmed names), containment-canonicalized before the cap
# (#476). Int caps behave exactly as before.
PER_FAMILY_CAP = -1

# Keyword groups for sector-level theme consolidation.
# Themes whose names match the same group are capped at MAX_THEMES_PER_SECTOR.
_SECTOR_KEYWORD_GROUPS: list[tuple[str, list[str], int]] = [
    # (group_key, keywords, max_themes)
    ("oil_gas", ["oil", "gas", "lng", "e&p", "oilfield", "petroleum", "crude",
                 "permian", "drilling", "refin", "upstream", "downstream",
                 "midstream", "completion", "pumping"], 2),
    # #476 (operator-signed 2026-07-17, replay-validated — docs/analysis/
    # 476_optionA_backtest_2026-07-16.md): biotech was cap 0 ("exclude
    # entirely", 2026-03-20) which SILENTLY killed every biotech-named theme
    # nightly while the shadow-promote resurrected the cohort — the elite-
    # orphan churn loop. Now PER_FAMILY_CAP: one keyword-theme per Stage-A
    # stem family (oncology/autoimmune/gene_cell_therapy/diagnostics/...,
    # ≤6 total incl. ONE shared unstemmed slot), with containment
    # canonicalization BEFORE the cap so daily re-cuts converge instead of
    # churning. Cross-family merges structurally refused (family-keyed).
    ("biotech", ["biotech", "clinical", "orphan drug", "gene edit", "crispr",
                 "mrna", "therapeutics", "pharma", "drug"], PER_FAMILY_CAP),
    ("satellite", ["satellite", "space", "earth observation"], 2),
    ("optical", ["optical", "photonic"], 2),
    ("agriculture", ["agri", "fertilizer", "crop", "nitrogen", "nutrient",
                      "agricultural", "herbicide", "pesticide"], 2),
    ("chemicals", ["chemical", "polymer", "acetyl", "specialty chem",
                    "petrochemical"], 2),
    ("ip_licensing", ["ip licensing", "patent", "royalty software"], 1),
]
MAX_THEMES_PER_SECTOR_DEFAULT = 2


def _build_theme_pools(
    leaders: list[dict],
    covered_tickers: set[str],
    revalidated_out: set[str],
) -> tuple[list[dict], list[dict]]:
    """Split the two candidate pools (#476, 2026-07-17). Pure — no I/O.

    - DISCOVERY pool (`uncovered`): the top-40 leaders (unchanged). New-theme
      discovery stays narrow — it has velocity/turners/correlation-clusters for
      genuinely-emerging names and shouldn't force-cluster static-strong
      singletons from a wider pool (advisor 7/17).
    - ASSIGNMENT pool: names with RS ≥ ASSIGN_POOL_RS_FLOOR among the top
      ASSIGN_POOL_CEILING leaders — a CONSISTENT quality bar, not a fixed count
      that floats with how crowded the RS top is (the top-40 bug: needed RS 98.4
      on a bunched day). It is a SUPERSET of the discovery pool (the union tail
      guards quiet days where a top-40 name sits below the floor).

    Returns (uncovered_discovery, assignment_pool).
    """
    def _ok(s):
        return s["ticker"] not in covered_tickers and s["ticker"] not in revalidated_out

    uncovered = [
        s for s in leaders[:40]
        if _ok(s) and (s.get("rs_composite", 0) or 0) >= THEME_RS_MIN
    ]
    assignment_pool = [
        s for s in leaders[:ASSIGN_POOL_CEILING]
        if _ok(s) and (s.get("rs_composite", 0) or 0) >= ASSIGN_POOL_RS_FLOOR
    ]
    seen = {s["ticker"] for s in assignment_pool}
    assignment_pool.extend(s for s in uncovered if s["ticker"] not in seen)
    return uncovered, assignment_pool


def _sector_group(theme_name: str) -> tuple[str, int] | None:
    """Return (group_key, max_themes) if the theme name matches any keyword group."""
    low = theme_name.lower()
    for group_key, keywords, max_themes in _SECTOR_KEYWORD_GROUPS:
        if any(kw in low for kw in keywords):
            return group_key, max_themes
    return None


def _strip_commodity_contradictions(themes: list[dict]) -> list[dict]:
    """
    Strip members whose descriptions obviously contradict the theme's commodity.
    Prevents gold miners ending up in uranium themes and vice versa.
    Deterministic — no Claude call needed.
    """
    from agents.market_intelligence.universe import TICKER_DESC

    # (theme_keywords_that_trigger, member_description_keywords_that_contradict)
    COMMODITY_RULES: list[tuple[list[str], list[str]]] = [
        (["uranium", "nuclear fuel", "nuclear energy"],
         ["gold", "silver", "precious metal", "gold miner", "silver miner", "zinc miner", "copper miner"]),
        (["gold miner", "silver miner", "precious metal", "gold & silver"],
         ["uranium", "nuclear", "lithium", "cobalt", "rare earth"]),
    ]

    for theme in themes:
        name_lower = theme["name"].lower()
        desc_lower = (theme.get("description") or "").lower()

        for theme_kws, contra_kws in COMMODITY_RULES:
            if not any(kw in name_lower or kw in desc_lower for kw in theme_kws):
                continue
            clean, stripped = [], []
            for tk in (theme.get("tickers") or []):
                tk_desc = (TICKER_DESC.get(tk) or "").lower()
                if any(ckw in tk_desc for ckw in contra_kws):
                    stripped.append(tk)
                else:
                    clean.append(tk)
            if stripped:
                logger.info(
                    f"[commodity filter] '{theme['name']}': stripped {stripped} "
                    f"(descriptions contradict theme commodity)"
                )
                theme["tickers"] = clean

    return themes


# ═══ ADR 0032 Phase 2 Route A — protect-strip → PARENT_CHILD adjudication ═══
# Behind THEME_SUBTHEME_ARM (default OFF). With the arm off (ctx None or
# disabled) every branch below is skipped and the merge passes are
# byte-identical to pre-Phase-2 behavior — pinned by
# tests/test_theme_subtheme_routing.py. Fail-closed everywhere: any
# non-PARENT_CHILD verdict, adjudicator error, or exception falls through to
# today's strip (never a silent coexist).
# Spec: docs/analysis/theme_ecosystem_phase23_design_2026-07-14.md §1.1.


def make_subtheme_route_ctx(
    enabled: bool,
    *,
    sectors_by_ticker: dict[str, str] | None = None,
    adjudicate=None,
    client=None,
    route_cap: int = SUBTHEME_ROUTE_CAP,
) -> dict:
    """Per-RUN Route-A context, shared across both `_merge_overlapping_themes`
    calls so the nightly adjudication budget (T7) is a single counter.
    `adjudicate`/`client` are test seams — production leaves them None and the
    router resolves the real corpus-cleared Arm-B adjudicator lazily."""
    return {
        "enabled": bool(enabled),
        "route_cap": route_cap,
        "routed": 0,               # adjudications consumed this run (any verdict)
        "sectors_by_ticker": sectors_by_ticker or {},
        "adjudicate": adjudicate,  # None → theme_merge_arm.adjudicate_merge_pair
        "client": client,          # None → _get_anthropic_client() on first route
        "routed_children": {},     # child name → parent name (this run) — merge_2 protection
    }


def _subtheme_set_match(a: set, b: set) -> bool:
    """Ticker-set identity for child canonicalization (fork F-2): the same
    sub-theme is re-discovered under a DAILY-CHURNING LLM name, so the child's
    identity is its TICKER SET, not its name. Match = containment of the
    SMALLER set in the larger ≥ SUBTHEME_C_MIN with ≥ MIN_SHARED_FOR_MERGE
    shared members (7/13 fixture: {TENB,RPD,QLYS} vs {TENB,RPD,QLYS,VRNS} →
    3/3 = 1.0 → same child)."""
    if not a or not b:
        return False
    inter = len(a & b)
    if inter < MIN_SHARED_FOR_MERGE:
        return False
    return inter / min(len(a), len(b)) >= SUBTHEME_C_MIN


async def _canonicalize_newborn_into_child(
    i: int, k: int, themes: list[dict], merged_into: dict[int, int],
) -> None:
    """Fold a re-discovered newborn (i) into the EXISTING canonical child (k):
    UPDATE the existing child (ticker union — the child keeps its name and its
    `parent_theme` link) and retire the newborn via the normal merged_into
    mechanism. Never creates a 2nd child for the same ticker set; no LLM call —
    the parent/child relationship was already adjudicated when the child was
    born."""
    newborn_tickers = set(themes[i].get("tickers") or [])
    pre = set(themes[k].get("tickers") or [])
    union = pre | newborn_tickers
    themes[k]["tickers"] = list(union)
    merged_into[i] = k
    logger.info(
        f"[subtheme route] canonicalized re-discovered child: '{themes[i]['name']}' "
        f"folded into existing child '{themes[k]['name']}' ({len(pre)}->{len(union)})"
    )
    await log_audit_event(
        "theme_subtheme_canonicalized",
        summary=(
            f"Route A: re-discovery '{themes[i]['name']}' folded into existing "
            f"child '{themes[k]['name']}' (ticker-set canonicalization)"
        ),
        detail=(
            f"newborn='{themes[i]['name']}' newborn_tickers={sorted(newborn_tickers)} "
            f"child='{themes[k]['name']}' parent='{themes[k].get('parent_theme')}' "
            f"child_size {len(pre)}->{len(union)}"
        ),
    )


def _sole_parent_of(
    i: int,
    themes: list[dict],
    merged_into: dict[int, int],
    protected_names: set[str],
    sub_theme_parents: dict[str, str],
) -> str | None:
    """T5 — the newborn's argmax-containment protected incumbent P: returns P's
    name iff containment(P) ≥ SUBTHEME_C_MIN AND every OTHER protected incumbent
    sits at containment ≤ SUBTHEME_C_MULTI or shares < MIN_SHARED_FOR_MERGE
    members (members spread across two parents ≠ a coherent subset of ONE).
    Existing CHILDREN are excluded from the disqualifier scan: a Route-A child's
    members coexist inside its parent, so counting the child as a competing
    parent would double-count the same overlap and block its own parent (the
    canonicalization path handles re-discoveries of the child itself)."""
    tickers_i = set(themes[i].get("tickers") or [])
    if not tickers_i:
        return None
    candidates: list[tuple[str, float, int]] = []  # (name, containment, |∩|)
    for m in range(len(themes)):
        if m == i or m in merged_into:
            continue
        name_m = themes[m]["name"]
        if name_m not in protected_names:
            continue
        if name_m in sub_theme_parents or themes[m].get("parent_theme"):
            continue  # children are never competing parents
        inter = len(tickers_i & set(themes[m].get("tickers") or []))
        candidates.append((name_m, inter / len(tickers_i), inter))
    if not candidates:
        return None
    candidates.sort(key=lambda c: (-c[1], c[0]))
    best_name, best_c, _ = candidates[0]
    if best_c < SUBTHEME_C_MIN:
        return None
    for name_m, c, inter in candidates[1:]:
        if inter >= MIN_SHARED_FOR_MERGE and c > SUBTHEME_C_MULTI:
            return None  # multi-parent — not a coherent subset of ONE
    return best_name


async def _route_a_subtheme(
    i: int,
    j: int,
    themes: list[dict],
    merged_into: dict[int, int],
    protected_names: set[str],
    sub_theme_parents: dict[str, str],
    ctx: dict,
) -> str | None:
    """Route A trigger + verdict handling, called at the Pass1 protect-strip
    site with a THIS-RUN pair (i, j) where j is protected and the overlap gates
    already fired. Returns:

      "coexist"       — PARENT_CHILD accepted: themes[i] persisted as a child of
                        themes[j] (parent_theme set + sub_theme_parents mutated —
                        the live dict → coexistence + Pass1.5 exemption for the
                        rest of this run). Caller skips the strip for this pair.
      "canonicalized" — themes[i] is a ticker-set re-discovery of an EXISTING
                        child (F-2): folded into it; caller breaks i's pair loop.
      None            — fall through to TODAY'S STRIP (the fail-closed default:
                        trigger not met, cap exhausted, MERGE/DISTINCT/inverted/
                        ERROR verdict, or any exception).

    NEVER raises — an exception audits theme_subtheme_route_error and returns
    None (today's strip)."""
    try:
        name_i = themes[i]["name"]
        name_j = themes[j]["name"]
        tickers_i = set(themes[i].get("tickers") or [])
        tickers_j = set(themes[j].get("tickers") or [])

        # T2 — i must be a THIS-RUN newborn, not an incumbent: leaves all 153
        # historical BOTH_PROTECTED established-pair strips untouched (G2).
        if protected_names and name_i in protected_names:
            return None
        # T3 — no chains: a child is never re-routed (mirrors "never split a
        # sub-theme further").
        if name_i in sub_theme_parents or themes[i].get("parent_theme"):
            return None
        # T6 — newborn member floor.
        if len(tickers_i) < SUBTHEME_MIN_MEMBERS:
            return None

        # ── F-2 ticker-set canonicalization (deterministic, no LLM, no cap) ──
        # Case 1: the protected theme j IS an existing child and the newborn is
        # a set-match → fold i into j.
        if name_j in sub_theme_parents:
            if _subtheme_set_match(tickers_i, tickers_j):
                await _canonicalize_newborn_into_child(i, j, themes, merged_into)
                return "canonicalized"
            return None  # j is a child but not a set-match — today's strip
        # Case 2: j is a potential parent — if an existing child OF j elsewhere
        # in the list is a set-match, fold i into it (handles the pair-order
        # case where (newborn, parent) is processed before (newborn, child)).
        for k in range(len(themes)):
            if k in (i, j) or k in merged_into:
                continue
            if sub_theme_parents.get(themes[k]["name"]) != name_j:
                continue
            if _subtheme_set_match(tickers_i, set(themes[k].get("tickers") or [])):
                await _canonicalize_newborn_into_child(i, k, themes, merged_into)
                return "canonicalized"

        # T4 — containment of the newborn in THIS protected incumbent.
        containment = len(tickers_i & tickers_j) / len(tickers_i)
        if containment < SUBTHEME_C_MIN:
            return None
        # T5 — sole parent, and the pair being processed must BE that parent
        # (a newborn overlapping a second incumbent first falls through to the
        # normal strip for THAT pair).
        sole = _sole_parent_of(i, themes, merged_into, protected_names, sub_theme_parents)
        if sole is None or sole != name_j:
            return None
        # T7 — nightly adjudication budget (shared across both merge calls).
        if ctx.get("routed", 0) >= ctx.get("route_cap", SUBTHEME_ROUTE_CAP):
            return None

        ctx["routed"] = ctx.get("routed", 0) + 1  # every routed call consumes cap
        adjudicate = ctx.get("adjudicate")
        if adjudicate is None:
            adjudicate = adjudicate_merge_pair  # the REAL corpus-cleared Arm-B adjudicator
            if ctx.get("client") is None:
                ctx["client"] = _get_anthropic_client()
        try:
            verdict = await adjudicate(
                themes[j], themes[i],  # parent = theme A, newborn = theme B
                client=ctx.get("client"),
                semaphore=_VALIDATION_SEMAPHORE,
                sectors_by_ticker=ctx.get("sectors_by_ticker") or {},
                log_spend=True,
            )
        except Exception as e:  # adjudicate returns ERROR dicts; belt-and-braces
            logger.warning(
                f"[subtheme route] adjudication raised for '{name_j}' × '{name_i}': {e}"
            )
            verdict = {"verdict": "ERROR", "reason": f"{type(e).__name__}: {e}"[:300]}

        v = verdict.get("verdict")
        scratch = str(verdict.get("analysis_scratchpad") or "")[:400]
        pair_detail = (
            f"parent='{name_j}' newborn='{name_i}' containment={containment:.2f} "
            f"newborn_tickers={sorted(tickers_i)} verdict={v!r} "
            f"reason={str(verdict.get('reason') or '')[:200]!r} scratchpad={scratch!r}"
        )

        if v == "PARENT_CHILD" and verdict.get("child", "B") != "A":
            # The D2 mechanism: members coexist in parent + child (the
            # MAX_THEMES_PER_STOCK=2 "primary + sub-theme" seat).
            themes[i]["parent_theme"] = name_j
            sub_theme_parents[name_i] = name_j
            ctx.setdefault("routed_children", {})[name_i] = name_j
            logger.info(
                f"[subtheme route] PARENT_CHILD: '{name_i}' persisted as child of "
                f"'{name_j}' (containment {containment:.2f}) — strip averted"
            )
            await log_audit_event(
                "theme_subtheme_routed",
                summary=f"Route A: '{name_i}' → child of '{name_j}' (PARENT_CHILD, strip averted)",
                detail=pair_detail,
            )
            return "coexist"
        if v == "PARENT_CHILD":
            # Inverted child claim (incumbent-as-child on a high-containment
            # pair) is a prompt failure — fail-closed, weekly review.
            await log_audit_event(
                "theme_subtheme_route_inverted",
                summary=f"Route A: inverted PARENT_CHILD (child='A') for '{name_i}' — strip as today",
                detail=pair_detail,
            )
            return None
        if v == "MERGE":
            # v2 slice-rule: the newborn is a redundant slice; the strip IS the
            # merge (its members are already inside the parent).
            await log_audit_event(
                "theme_subtheme_route_merge",
                summary=f"Route A: MERGE verdict for '{name_i}' — strip as today",
                detail=pair_detail,
            )
            return None
        if v == "DISTINCT":
            # Fail-closed (fork F-3): high-containment + different-drivers is a
            # contradiction for human eyes, not an auto-coexist.
            await log_audit_event(
                "theme_subtheme_route_distinct",
                summary=f"Route A: DISTINCT verdict for '{name_i}' — strip as today (weekly review)",
                detail=pair_detail,
            )
            return None
        await log_audit_event(
            "theme_subtheme_route_error",
            summary=f"Route A: adjudication error for '{name_i}' — strip as today",
            detail=pair_detail,
        )
        return None
    except Exception as e:
        # The arm must never break the merge pass (0025 pattern) — audit loud,
        # then fall through to today's strip.
        logger.warning(f"[subtheme route] Route A failed — fail-closed to strip: {e}")
        try:
            await log_audit_event(
                "theme_subtheme_route_error",
                summary="Route A: internal error — strip as today",
                detail=f"{type(e).__name__}: {e}"[:500],
            )
        except Exception as audit_err:  # loud-ok: audit-of-the-audit; nothing above can handle it
            logger.warning(f"[subtheme route] error-audit write failed: {audit_err}")
        return None


async def _merge_overlapping_themes(
    themes: list[dict],
    stocks_by_ticker: dict[str, dict],
    protected_names: set[str] | None = None,
    sub_theme_parents: dict[str, str] | None = None,
    subtheme_ctx: dict | None = None,
) -> list[dict]:
    """
    Two-pass theme consolidation:
    1. Ticker overlap: merge themes with Jaccard >= 0.6, subset, or 60%+ overlap
    2. Sector cap: limit themes per broad sector (oil/gas, biotech, etc.) to top 2

    protected_names: existing theme names that must not be absorbed by new clusters.
    When a protected theme would be absorbed, the overlapping stocks are stripped from
    the new cluster instead — the existing theme keeps its identity.

    sub_theme_parents: mapping of sub-theme name → parent theme name. A sub-theme is
    allowed to overlap with its parent — never merged back in.

    subtheme_ctx: ADR 0032 Phase 2 Route A context (make_subtheme_route_ctx).
    None or disabled (THEME_SUBTHEME_ARM off — the default) ⇒ every Route-A
    branch is skipped and this function is byte-identical to pre-Phase-2
    behavior.
    """
    if len(themes) <= 1:
        return themes

    # Diagnostic snapshot of merge inputs — logged for every merge call so
    # save-time dedup fires can be traced back to the merge state.
    merge_input = [
        {
            "name": t["name"],
            "n": len(t.get("tickers") or []),
            "tickers": sorted(t.get("tickers") or []),
            "score": round(float(t.get("score") or 0), 1),
            "protected": bool(protected_names and t["name"] in protected_names),
        }
        for t in themes
    ]
    logger.info(f"[theme merge input] {json.dumps(merge_input, separators=(',', ':'))}")

    # Sort by score desc, name asc as deterministic tiebreaker. Without the
    # secondary key, ties resolve by Python sort stability against insertion
    # order, which differs run-to-run when DB returns rows in non-deterministic
    # order — caused 5+3 score-tie groups in 24h post-pipeline-diagnostic.
    themes = sorted(themes, key=lambda t: (-(t.get("score") or 0), t.get("name") or ""))

    # --- Pass 1: Ticker overlap merge ---
    merged_into: dict[int, int] = {}

    for i in range(len(themes)):
        if i in merged_into:
            continue
        tickers_i = set(themes[i].get("tickers") or [])
        if not tickers_i:
            continue

        for j in range(i + 1, len(themes)):
            if j in merged_into:
                continue
            tickers_j = set(themes[j].get("tickers") or [])
            if not tickers_j:
                continue

            intersection = tickers_i & tickers_j
            union = tickers_i | tickers_j

            jaccard = len(intersection) / len(union) if union else 0
            is_subset = tickers_j <= tickers_i or tickers_i <= tickers_j
            smaller_size = min(len(tickers_i), len(tickers_j))
            overlap_ratio = len(intersection) / smaller_size if smaller_size else 0

            # Floor on absolute intersection size — overlap_ratio and is_subset both
            # collapse to noise on tiny themes (a 1-ticker theme sharing its 1 ticker
            # is 100% overlap AND a subset, but says nothing about thematic kinship).
            # Mirror of `min_shared` gate in rs-theme-dash/data.py::dedup_themes.
            if len(intersection) < MIN_SHARED_FOR_MERGE:
                continue

            if jaccard >= 0.6 or is_subset or overlap_ratio >= 0.6:
                # Sub-theme coexistence: a sub-theme is allowed to overlap with its parent
                j_is_subtopic_of_i = (
                    sub_theme_parents
                    and sub_theme_parents.get(themes[j]["name"]) == themes[i]["name"]
                )
                # §1.1-D symmetric fix (ADR 0032 Phase 2, fork F-4 — ALWAYS ON,
                # not toggle-gated): when the child out-scores its parent it
                # sorts as i and the parent lands as j; without the reverse
                # check the carve-out never fires and the BOTH_PROTECTED
                # tiebreaker guts the child the night after it is created (G4).
                # Inert until a parent_theme link exists; also protects the
                # ADR-0025 Arm-B PARENT_CHILD children once THEME_MERGE_ARM flips.
                i_is_subtopic_of_j = (
                    sub_theme_parents
                    and sub_theme_parents.get(themes[i]["name"]) == themes[j]["name"]
                )
                if j_is_subtopic_of_i or i_is_subtopic_of_j:
                    continue  # coexistence — never re-absorb a sub-theme into its parent

                j_protected = protected_names and themes[j]["name"] in protected_names
                if j_protected:
                    # ── ADR 0032 Phase 2 Route A hook (behind THEME_SUBTHEME_ARM).
                    # ctx None/disabled ⇒ skipped ⇒ the strip below runs
                    # byte-identically to pre-Phase-2. Fail-closed: any outcome
                    # other than an accepted PARENT_CHILD / canonicalization
                    # returns None and falls through to today's strip.
                    if (
                        subtheme_ctx
                        and subtheme_ctx.get("enabled")
                        and sub_theme_parents is not None
                    ):
                        routed = await _route_a_subtheme(
                            i, j, themes, merged_into, protected_names or set(),
                            sub_theme_parents, subtheme_ctx,
                        )
                        if routed == "coexist":
                            continue  # child persisted alongside its parent — no strip
                        if routed == "canonicalized":
                            break  # newborn folded into the existing child — i is retired
                    # Protected existing theme (j) would be absorbed by new cluster (i).
                    # Default: strip the overlap from i to preserve j's identity.
                    #
                    # BOTH-PROTECTED tiebreaker (2026-05-14 SNDK incident): when
                    # i is ALSO protected, both themes are returning from prior
                    # days and the iteration order shouldn't decide ownership.
                    # The more established theme (larger membership) keeps the
                    # intersection; the smaller one gets stripped.
                    #
                    # SNDK example: AI Memory & Storage (i, 8 tickers, established)
                    # vs Semiconductor Front-End Interconnect & Wafer Processing
                    # Equipment (j, 3 tickers, new-ish). Old behavior stripped i
                    # → SNDK went to the smaller new theme. New behavior: i has
                    # more members → strip from j instead, preserving SanDisk
                    # in AI Memory & Storage.
                    i_protected = bool(protected_names and themes[i]["name"] in protected_names)
                    strip_from = "i"
                    if i_protected and len(tickers_i) >= len(tickers_j):
                        # Both protected, i is the larger/equal theme → strip from j
                        strip_from = "j"

                    if strip_from == "i":
                        pre_size = len(tickers_i)
                        tickers_i = tickers_i - intersection
                        themes[i]["tickers"] = list(tickers_i)
                        post_size = len(tickers_i)
                        stripped_name = themes[i]["name"]
                        kept_name = themes[j]["name"]
                    else:
                        pre_size = len(tickers_j)
                        tickers_j = tickers_j - intersection
                        themes[j]["tickers"] = list(tickers_j)
                        post_size = len(tickers_j)
                        stripped_name = themes[j]["name"]
                        kept_name = themes[i]["name"]

                    logger.info(
                        f"Theme protect: stripped {sorted(intersection)} from "
                        f"'{stripped_name}' to preserve '{kept_name}'"
                        + (f" (BOTH_PROTECTED tiebreaker, kept larger)" if i_protected else "")
                    )
                    await log_audit_event(
                        "theme_pass1_protect_strip",
                        summary=(
                            f"Pass1: stripped {len(intersection)} ticker(s) from "
                            f"'{stripped_name}' (protect '{kept_name}')"
                        ),
                        detail=(
                            f"i='{themes[i]['name']}' i_protected={i_protected} "
                            f"i_size={len(themes[i].get('tickers') or [])} "
                            f"j='{themes[j]['name']}' j_protected=True "
                            f"j_size={len(themes[j].get('tickers') or [])} "
                            f"intersection={sorted(intersection)} "
                            f"stripped='{stripped_name}' {pre_size}->{post_size}"
                            + (" EMPTY_AFTER_STRIP" if post_size == 0 else "")
                            + (" BOTH_PROTECTED" if i_protected else "")
                            + (f" tiebreaker=size_kept_{kept_name}" if i_protected else "")
                        ),
                    )
                else:
                    logger.info(
                        f"Theme merge (overlap): '{themes[j]['name']}' → '{themes[i]['name']}' "
                        f"(Jaccard {jaccard:.2f}, {len(intersection)} shared tickers)"
                    )
                    tickers_i = tickers_i | tickers_j
                    themes[i]["tickers"] = list(tickers_i)
                    merged_into[j] = i

    after_overlap = [t for idx, t in enumerate(themes) if idx not in merged_into]

    # --- Pass 1.5: Small-theme absorption ---
    # A theme with <= 3 stocks where only 0-1 are unique (not in any other theme)
    # is not a distinct theme — absorb into the highest-scoring overlapping theme.
    # Protected existing themes were originally exempt; now allowed to absorb when
    # they're small + non-unique, but only into a higher-scored protected target —
    # this lets two near-duplicate existing themes consolidate (e.g. AI Datacenter
    # Silicon ⊃ Custom AI Silicon) without letting new clusters dissolve established
    # themes.
    from collections import Counter
    ticker_membership = Counter()
    for t in after_overlap:
        for tk in (t.get("tickers") or []):
            ticker_membership[tk] += 1

    absorbed = set()
    for idx, t in enumerate(after_overlap):
        if sub_theme_parents and t["name"] in sub_theme_parents:
            continue  # never absorb a sub-theme in pass 1.5
        tickers = set(t.get("tickers") or [])
        if len(tickers) > 3 or not tickers:
            continue
        unique_count = sum(1 for tk in tickers if ticker_membership[tk] == 1)
        if unique_count > 1:
            continue

        t_protected = bool(protected_names and t["name"] in protected_names)
        t_score = t.get("score", 0)

        # Track skipped candidates so we can audit "would-have-merged-but-for-guard"
        # cases — the strongest signal for diagnosing why two near-duplicate themes
        # survived a merge call.
        skipped_targets: list[tuple[str, str]] = []  # (target_name, reason)

        # Find highest-scoring overlapping theme to absorb into
        for target in after_overlap:
            if target["name"] == t["name"] or target["name"] in absorbed:
                continue
            target_tickers = set(target.get("tickers") or [])
            if not (tickers & target_tickers):
                continue
            # Direction guard: keep the more established theme. Without this,
            # processing order (score desc) absorbs the higher-scored theme
            # into the lower-scored one when it lands as `t` first.
            if target.get("score", 0) < t_score:
                skipped_targets.append((target["name"], f"direction:target_score={target.get('score',0)}<t_score={t_score}"))
                continue
            # When t is an existing protected theme, only dissolve it into
            # another existing protected theme. New clusters must not absorb
            # established themes (the original protection contract).
            if t_protected and not (
                protected_names and target["name"] in protected_names
            ):
                skipped_targets.append((target["name"], "protection:t_protected_target_not"))
                continue
            target["tickers"] = list(target_tickers | tickers)
            absorbed.add(t["name"])
            logger.info(
                f"Theme merge (small-theme absorption): '{t['name']}' → '{target['name']}' "
                f"({len(tickers)} stocks, {unique_count} unique"
                f"{', protected' if t_protected else ''})"
            )
            await log_audit_event(
                "theme_pass1_5_absorption",
                summary=f"Pass1.5: '{t['name']}' -> '{target['name']}'",
                detail=(
                    f"t='{t['name']}' t_score={t_score} t_protected={t_protected} "
                    f"t_size={len(tickers)} unique_count={unique_count} "
                    f"target='{target['name']}' target_score={target.get('score', 0)} "
                    f"target_protected={bool(protected_names and target['name'] in protected_names)}"
                ),
            )
            break
        else:
            # No target passed all guards — log if there were rejected candidates
            # (silent "skip" is the failure mode that lets duplicates survive).
            if skipped_targets:
                await log_audit_event(
                    "theme_pass1_5_skip",
                    summary=(
                        f"Pass1.5: '{t['name']}' eligible but no target passed "
                        f"({len(skipped_targets)} candidate(s) skipped)"
                    ),
                    detail=(
                        f"t='{t['name']}' t_score={t_score} t_protected={t_protected} "
                        f"t_size={len(tickers)} unique_count={unique_count}\n"
                        + "\n".join(f"  skip target='{n}' reason={r}" for n, r in skipped_targets)
                    ),
                )

    if absorbed:
        after_overlap = [t for t in after_overlap if t["name"] not in absorbed]

    # --- Pass 2: Sector cap — keep top N per broad sector group ---
    sector_counts: dict[str, int] = {}
    final: list[dict] = []

    for t in after_overlap:  # already sorted by score desc
        result = _sector_group(t["name"])
        if result is None:
            final.append(t)
            continue

        group, max_for_group = result

        if max_for_group == PER_FAMILY_CAP:
            # #476 per-family mode (biotech): ONE slot per Stage-A stem family
            # (unstemmed names share one). Convergence needs no code here —
            # Pass 1 merges at containment ≥0.6 with ≥3 shared, which SUBSUMES
            # the replay's 0.8 canonicalization rule, so daily re-cuts have
            # already converged upstream by the time they reach this cap; the
            # historical bug was purely that cap-0 then KILLED the converged
            # survivor. Family-keyed slots also mean this branch never runs the
            # int-cap absorb-into-top below — a biotech theme can never be
            # blind-absorbed across families (the mush guard).
            fam = family_of(t["name"]) or "_unstemmed"
            fam_key = f"{group}:{fam}"
            if sector_counts.get(fam_key, 0) < 1:
                final.append(t)
                sector_counts[fam_key] = 1
            else:
                # slot taken + Pass 1 didn't converge it = a genuinely
                # different cut of the same family — dropping matches the
                # replay's validated semantics; the audit keeps it visible.
                await log_audit_event(
                    "theme_sector_cap_dropped",
                    summary=(f"'{t['name']}' dropped by sector cap "
                             f"(group '{group}', family '{fam}' slot taken)"),
                    detail=f"tickers={','.join(t.get('tickers') or [])}",
                )
            continue

        count = sector_counts.get(group, 0)
        if count < max_for_group:
            final.append(t)
            sector_counts[group] = count + 1
        else:
            # Absorb into the top theme of this sector group (if any kept)
            top_theme = next(
                (f for f in final
                 if (sg := _sector_group(f["name"])) is not None and sg[0] == group),
                None,
            )
            if top_theme:
                existing = set(top_theme.get("tickers") or [])
                extra = set(t.get("tickers") or [])
                top_theme["tickers"] = list(existing | extra)
                logger.info(
                    f"Theme merge (sector cap): '{t['name']}' → '{top_theme['name']}' "
                    f"(sector group '{group}', {len(extra)} tickers absorbed)"
                )
            else:
                # cap-0 groups (biotech since 2026-03-20) have NO survivor to
                # absorb into — every group member lands HERE and vanishes.
                # This was a bare silent drop for 4 months; #476 (2026-07-16)
                # traced the elite-biotech orphan churn to exactly this branch
                # (the shadow-promote resurrects the cohort nightly, this kills
                # it again — source alternates shadow_promoted↔live). Pure
                # observability: the drop still happens; it is now visible.
                # log_audit_event never raises (its own contract) — no wrapper.
                await log_audit_event(
                    "theme_sector_cap_dropped",
                    summary=(f"'{t['name']}' dropped by sector cap "
                             f"(group '{group}', cap {max_for_group})"),
                    detail=f"tickers={','.join(t.get('tickers') or [])}",
                )

    return final


async def _enforce_max_themes_per_stock(themes: list[dict]) -> list[dict]:
    """
    Hard cap: a stock can appear in at most MAX_THEMES_PER_STOCK themes.
    Themes must be sorted by score descending (highest-scored = primary).
    Removes stocks from lower-scored themes when they exceed the cap.
    Drops themes that fall below PRUNE_MIN_TICKERS after removals.

    Each strip + drop emits an audit row so post-cap state changes are
    reconstructable from `mi_audit_log` alone.
    """
    from collections import defaultdict

    ticker_assignments: dict[str, list[str]] = defaultdict(list)
    theme_by_name = {t["name"]: t for t in themes}
    pre_sizes = {t["name"]: len(t.get("tickers") or []) for t in themes}

    for t in themes:  # iterate in score order (already sorted)
        for tk in (t.get("tickers") or []):
            ticker_assignments[tk].append(t["name"])

    strip_events: list[tuple[str, str, int, int]] = []  # (ticker, theme, pre, post)
    for tk, assigned_themes in ticker_assignments.items():
        if len(assigned_themes) <= MAX_THEMES_PER_STOCK:
            continue
        # Keep the top N by score (already in score order)
        excess = assigned_themes[MAX_THEMES_PER_STOCK:]
        for theme_name in excess:
            theme = theme_by_name[theme_name]
            pre = len(theme["tickers"])
            theme["tickers"] = [t for t in theme["tickers"] if t != tk]
            post = len(theme["tickers"])
            logger.info(
                f"Theme cap: removed {tk} from '{theme_name}' "
                f"(was in {len(assigned_themes)} themes, keeping top {MAX_THEMES_PER_STOCK})"
            )
            strip_events.append((tk, theme_name, pre, post))

    if strip_events:
        logger.info(f"Theme cap enforced: {len(strip_events)} ticker-theme removals")
        detail = "\n".join(
            f"removed {tk} from '{tn}' size {pre}->{post}"
            + (" EMPTY_AFTER_CAP" if post == 0 else "")
            for tk, tn, pre, post in strip_events
        )
        await log_audit_event(
            "theme_cap_strip",
            summary=f"Cap: {len(strip_events)} ticker-theme removal(s)",
            detail=detail,
        )

    # Drop themes that fell below minimum
    result = []
    drops: list[tuple[str, int, int]] = []  # (name, pre_size, post_size)
    for t in themes:
        tickers = t.get("tickers") or []
        if len(tickers) >= PRUNE_MIN_TICKERS:
            result.append(t)
        else:
            drops.append((t["name"], pre_sizes.get(t["name"], 0), len(tickers)))
            logger.info(f"Theme '{t['name']}' dropped: only {len(tickers)} ticker(s) after cap enforcement")
    if drops:
        detail = "\n".join(
            f"dropped '{n}' size {pre}->{post}" for n, pre, post in drops
        )
        await log_audit_event(
            "theme_cap_drop",
            summary=f"Cap: {len(drops)} theme(s) dropped below PRUNE_MIN_TICKERS={PRUNE_MIN_TICKERS}",
            detail=detail,
        )
    return result


async def _retro_sweep_flagged_pairs(
    updated_themes: list[dict],
    changelog: list[dict],
) -> list[dict]:
    """ADR 0025 Arm A retro-sweep (#274) — behind THEME_MERGE_ARM, nightly.

    Dissolve any active 2-member theme where a member carries a LIVE validation
    cooldown FROM THAT SAME THEME: validation already adjudicated the member OUT
    of this exact theme (the evidence), but the min-survivor guard kept the pair
    alive — the 2-member-immortality loop the evidence pack found (7 themes).
    Fires only on validation evidence, never a bare member count.

    Mechanics: the flagged member's 14d (ticker, theme) cooldown is refreshed so
    the pair can't instantly re-form; the SURVIVOR gets no cooldown (it did
    nothing wrong — released to the discovery pools next run). Dissolved themes
    drop from emission → the engine-drop path synthesizes their Retired rows
    (theme_auto_retired, parent_theme=NULL). Fail-open: any error leaves the
    themes untouched.
    """
    if not merge_arm_enabled():
        return updated_themes
    try:
        cooldown_pairs = await get_cooldown_set()
    except Exception as e:
        logger.warning(f"[Arm A sweep] cooldown fetch failed — sweep skipped: {e}")
        return updated_themes
    dissolved: set[str] = set()
    for t in updated_themes:
        tks = list(t.get("tickers") or [])
        if len(tks) != 2:
            continue
        flagged = [tk for tk in tks if (tk, t["name"]) in cooldown_pairs]
        if not flagged:
            continue
        survivors = [tk for tk in tks if tk not in flagged]
        try:
            for tk in flagged:
                await add_validation_cooldown(
                    tk, t["name"],
                    reason="ADR 0025 Arm A retro-sweep — flagged-pair theme dissolved",
                )
            await log_audit_event(
                "theme_dissolved_flagged_pair",
                summary=(f"Arm A retro-sweep dissolve: '{t['name']}' — member(s) "
                         f"{', '.join(flagged)} carry a live validation cooldown from this theme"),
                detail=(f"via=retro_sweep flagged={flagged} survivors={survivors} "
                        f"(survivor released, no cooldown — ADR 0025 Arm A)"),
            )
        except Exception as e:
            logger.warning(f"[Arm A sweep] dissolve bookkeeping failed for '{t['name']}' — kept: {e}")
            continue
        changelog.append({
            "type": "theme_dissolved_flagged_pair",
            "theme": t["name"],
            "flagged": flagged,
            "survivors": survivors,
            "via": "retro_sweep",
        })
        dissolved.add(t["name"])
    if dissolved:
        logger.info(f"[Arm A sweep] dissolved {len(dissolved)} flagged-pair theme(s): {sorted(dissolved)}")
        updated_themes = [t for t in updated_themes if t["name"] not in dissolved]
    return updated_themes


def _synthetic_retired_row(name: str, today: date, successor: str | None, note: str) -> dict:
    """Retired-row shape for themes removed outside the lifecycle (mirrors the
    engine-drop retire_rows in run_theme_engine — keep the two in lockstep)."""
    return {
        "theme_date": today,
        "name": name,
        "stage": "Retired",
        "score": 0.0,
        "rs_avg": None,
        "description": note,
        "tickers": [],
        "parent_theme": successor,
        "pct_above_20sma": None,
    }


async def _run_thesis_merge_pass(
    all_themes: list[dict],
    persisted_names: set[str],
    changelog: list[dict],
    protected: set[tuple[str, str]] | None,
    today: date,
    stocks_by_ticker: dict[str, dict] | None = None,
) -> list[dict]:
    """ADR 0025 Arm B (#274) — nightly thesis-coherence merge pass. Behind
    THEME_MERGE_ARM (default OFF → returns the list untouched).

    Runs AFTER the final Pass1/1.5/cap sequence, BEFORE the engine-drop Retired-row
    synthesis. Stage A: deterministic pairing (theme_merge_arm.propose_merge_pairs —
    the pure logic the 7/11 replay validated; ≤8 pairs/night). Stage B: Haiku
    adjudicator (temp=0, scratchpad-first tool schema, negative exemplars). Mechanics:
      MERGE        → union members into the higher-scoring theme (winner); the
                     absorbed theme gets a synthetic Retired row with
                     parent_theme=successor; the merged theme immediately
                     re-validates (#266 birth-style) so a bad union self-corrects
                     tonight; a gutted union (<2 survivors) dissolves instead of
                     merging (Arm A composition). Name = adjudicator-proposed (F1,
                     operator-signed) with a collision guard. ≤3 executed/night.
      DISTINCT     → 30d (A,B) merge_distinct cooldown + theme_merge_distinct audit.
      PARENT_CHILD → existing sub-theme machinery (child.parent_theme = parent),
                     no dissolution.
    Fail-open per pair AND for the whole pass — the arm must never break the run.
    """
    if not merge_arm_enabled():
        return all_themes
    removed: set[str] = set()
    retired_rows: list[dict] = []
    try:
        candidates = [t for t in all_themes if t.get("stage") != "Retired" and t.get("tickers")]
        try:
            cooldown_pairs = await get_merge_distinct_pairs()
        except Exception as e:
            logger.warning(f"[merge arm] distinct-cooldown fetch failed — pass skipped: {e}")
            return all_themes
        sectors_by_ticker = {
            tk: s.get("sector") for tk, s in (stocks_by_ticker or {}).items()
            if s.get("sector") and s.get("sector") != "Unknown"
        }
        pairs = propose_merge_pairs(
            candidates, cooldown_pairs=cooldown_pairs, sectors_by_ticker=sectors_by_ticker,
        )
        if not pairs:
            return all_themes
        await log_audit_event(
            "theme_merge_pairs_proposed",
            summary=f"Arm B Stage A: {len(pairs)} candidate pair(s) for adjudication",
            detail="\n".join(f"'{o['name']}' × '{a['name']}'" for a, o in pairs),
        )
        client = _get_anthropic_client()
        merges_executed = 0
        for anchor, other in pairs:
            if anchor["name"] in removed or other["name"] in removed:
                continue
            try:
                verdict = await adjudicate_merge_pair(
                    anchor, other, client=client, semaphore=_VALIDATION_SEMAPHORE,
                    sectors_by_ticker=sectors_by_ticker, log_spend=True,
                )
            except Exception as e:  # adjudicate returns ERROR dicts; belt-and-braces
                logger.warning(
                    f"[merge arm] adjudication raised for '{other['name']}' × '{anchor['name']}': {e}"
                )
                verdict = {"verdict": "ERROR", "reason": f"{type(e).__name__}: {e}"}
            v = verdict.get("verdict")

            if v == "DISTINCT":
                try:
                    await add_merge_distinct_cooldown(
                        anchor["name"], other["name"],
                        reason=(verdict.get("reason") or "")[:200],
                        days=MERGE_DISTINCT_COOLDOWN_DAYS,
                    )
                except Exception as e:
                    logger.warning(f"[merge arm] distinct-cooldown write failed: {e}")
                await log_audit_event(
                    "theme_merge_distinct",
                    summary=f"Arm B: '{other['name']}' vs '{anchor['name']}' DISTINCT — 30d pair cooldown",
                    detail=(f"driver_a={verdict.get('driver_a', '')!r} driver_b={verdict.get('driver_b', '')!r} "
                            f"reason={verdict.get('reason', '')!r}"),
                )

            elif v == "PARENT_CHILD":
                child, parent = (other, anchor) if verdict.get("child", "B") != "A" else (anchor, other)
                if child.get("parent_theme"):
                    continue  # already a sub-theme — leave the existing relationship alone
                child["parent_theme"] = parent["name"]
                changelog.append({
                    "type": "theme_merge_parent_child",
                    "theme": child["name"],
                    "parent": parent["name"],
                })
                await log_audit_event(
                    "theme_merge_parent_child",
                    summary=f"Arm B: '{child['name']}' → sub-theme of '{parent['name']}'",
                    detail=f"reason={verdict.get('reason', '')!r}",
                )

            elif v == "MERGE":
                if merges_executed >= MAX_MERGES_PER_NIGHT:
                    await log_audit_event(
                        "theme_merge_cap_deferred",
                        summary=(f"Arm B: nightly merge cap ({MAX_MERGES_PER_NIGHT}) reached — "
                                 f"deferred '{other['name']}' × '{anchor['name']}'"),
                        detail=f"reason={verdict.get('reason', '')!r}",
                    )
                    continue
                winner, absorbed = (
                    (anchor, other)
                    if float(anchor.get("score") or 0) >= float(other.get("score") or 0)
                    else (other, anchor)
                )
                winner_tickers = list(winner.get("tickers") or [])
                union = winner_tickers + [
                    tk for tk in (absorbed.get("tickers") or []) if tk not in winner_tickers
                ]
                # Post-merge validation (#266 birth-style): a bad union self-corrects
                # tonight; dissolve_flagged_pair composes Arm A for a 2-member union.
                validated = await _validate_theme_membership(
                    winner["name"], union, changelog, protected=protected,
                    dissolve_flagged_pair=True,
                )
                merges_executed += 1  # a gutted merge still consumed the night's action
                if len(validated) < PRUNE_MIN_TICKERS:
                    # Arm A composition: validation gutted the union → dissolve, don't merge.
                    for nm in (winner["name"], absorbed["name"]):
                        removed.add(nm)
                        if nm in persisted_names:
                            retired_rows.append(_synthetic_retired_row(
                                nm, today, successor=None,
                                note=(f"Auto-retired {today}: Arm B merge of '{absorbed['name']}' into "
                                      f"'{winner['name']}' gutted by post-merge validation — dissolved "
                                      f"(ADR 0025)."),
                            ))
                    await log_audit_event(
                        "theme_merge_dissolved_post_validation",
                        summary=(f"Arm B: merge '{absorbed['name']}' → '{winner['name']}' gutted by "
                                 f"post-merge validation — both dissolved (Arm A composition)"),
                        detail=f"union={union} validated={validated}",
                    )
                    continue
                old_winner_name = winner["name"]
                merged_name = (verdict.get("merged_name") or "").strip()
                taken = ({t["name"] for t in all_themes} | persisted_names) - {old_winner_name}
                if merged_name and merged_name != old_winner_name and merged_name not in taken:
                    winner["name"] = merged_name  # F1 (operator-signed): adjudicator-proposed name
                    if old_winner_name in persisted_names:
                        retired_rows.append(_synthetic_retired_row(
                            old_winner_name, today, successor=winner["name"],
                            note=(f"Auto-retired {today}: renamed to '{winner['name']}' by Arm B "
                                  f"thesis merge (ADR 0025)."),
                        ))
                winner["tickers"] = validated
                removed.add(absorbed["name"])
                if absorbed["name"] in persisted_names:
                    retired_rows.append(_synthetic_retired_row(
                        absorbed["name"], today, successor=winner["name"],
                        note=(f"Auto-retired {today}: thesis-merged into '{winner['name']}' "
                              f"(ADR 0025 Arm B)."),
                    ))
                changelog.append({
                    "type": "theme_thesis_merged",
                    "theme": absorbed["name"],
                    "into": winner["name"],
                    "tickers": validated,
                })
                await log_audit_event(
                    "theme_thesis_merged",
                    summary=f"Arm B: '{absorbed['name']}' merged into '{winner['name']}' ({len(validated)} members)",
                    detail=(f"driver_a={verdict.get('driver_a', '')!r} driver_b={verdict.get('driver_b', '')!r} "
                            f"reason={verdict.get('reason', '')!r} merged_name={merged_name!r} "
                            f"scratchpad={(verdict.get('analysis_scratchpad') or '')[:400]!r}"),
                )
                logger.info(f"[merge arm] '{absorbed['name']}' merged into '{winner['name']}'")

            else:  # ERROR / unknown — fail-open per pair, next night retries
                await log_audit_event(
                    "theme_merge_adjudication_error",
                    summary=f"Arm B: adjudication failed for '{other['name']}' × '{anchor['name']}'",
                    detail=str(verdict)[:500],
                )
    except Exception as e:
        logger.error(f"[merge arm] thesis-merge pass failed — completed actions kept, rest skipped: {e}")
        try:
            await log_audit_event(
                "theme_merge_arm_error",
                summary="Arm B pass failed mid-run — completed actions kept, rest skipped",
                detail=f"{type(e).__name__}: {e}",
            )
        except Exception:  # loud-ok: audit-of-audit fallback — the pass failure is already logger.error'd above
            pass
    if removed:
        all_themes = [t for t in all_themes if t["name"] not in removed]
    return all_themes + retired_rows


async def run_theme_engine(
    trade_date: date | None = None,
    clusters: list[dict] | None = None,
) -> tuple[list[dict], list[dict]]:
    """
    Run the full theme update cycle:
    1. Re-score existing active themes (with pruning)
    2. Assign uncovered stocks to existing themes
    3. Discover new themes from remaining uncovered RS leaders
    4. Persist results

    Returns (themes, changelog) where changelog tracks all membership changes.
    """
    today = trade_date or et_today()
    today_str = today.strftime("%Y-%m-%d")
    changelog: list[dict] = []

    # --- Preflight: verify Perplexity is reachable before touching any theme data ---
    # A 401/402 from Perplexity causes news_score=0 for EVERY theme, which produces
    # smooth_delta ≈ -30 and flips all themes to Fading in a single run.
    # Abort early and alert rather than silently corrupting the theme state.
    try:
        await _preflight_perplexity()
    except PerplexityUnavailableError as e:
        error_msg = str(e)
        logger.error(f"[theme engine] ABORTING — {error_msg}")
        # Surface to Telegram immediately — this is a critical, actionable failure
        try:
            from agents.market_intelligence.briefing import send_telegram_message
            await send_telegram_message(
                f"🚨 *Theme Engine ABORTED*\n\n"
                f"{error_msg}\n\n"
                f"No theme data was updated. Add API credits then send *rerun theme engine* to retry."
            )
        except Exception:
            pass
        await log_audit_event(
            "theme_engine_aborted",
            summary=f"Theme engine aborted — Perplexity unavailable",
            detail=error_msg,
        )
        raise  # propagate to caller (scheduler adds to failures, _handle_theme_only shows error)

    logger.info("Theme engine: fetching top RS stocks + velocity + turners...")
    leaders, velocity_all, turners_all = await asyncio.gather(
        get_rs_leaders(today_str, limit=ASSIGN_POOL_CEILING),  # #476: 60→200 so the RS-floor assignment pool has candidates (discovery still uses [:40])
        get_rs_velocity(today_str, min_rs=THEME_RS_MIN, limit=30),
        get_rs_turners(today_str, max_rs_4w_ago=30.0, min_consecutive_weeks=3, limit=30),
    )

    if not leaders:
        logger.warning("Theme engine: no RS data — run RS engine first")
        return [], []

    # Enrich with sector data (concurrent, rate-limited by semaphore)
    async def _enrich_sector(stock: dict) -> None:
        if not stock.get("sector"):
            async with _SECTOR_SEM:
                stock["sector"] = await _get_sector(stock["ticker"])

    # ADR 0007 (c): enrich sector for ALL discovery candidate pools (uncovered/
    # velocity/turners + future accelerators), not just the top-60 `leaders`. A
    # candidate with a blank sector is unclusterable — the drone/software leaders
    # below the top-60 cut were all blank-sector on 5/28. _enrich_sector no-ops on
    # already-set sectors, so this only fetches the genuinely-blank ones.
    _enrich_pool = _all_candidate_pool(leaders, velocity_all, turners_all)
    logger.info(f"Theme engine: enriching sector for {len(_enrich_pool)} candidate-pool stocks...")
    await asyncio.gather(*[_enrich_sector(s) for s in _enrich_pool])

    stocks_by_ticker = {s["ticker"]: s for s in leaders}

    # --- Step 0.5: Ensure every discovery candidate has a description before clustering ---
    # Fetches from yfinance + Claude Haiku for any stock missing one, persists to DB.
    # Stocks that still have no description after this step are excluded from clustering.
    # ADR 0007 (c2): cover ALL candidate pools, not just leaders — a velocity/turner/
    # accelerator candidate with no description is silently dropped from discovery
    # (`_discover_new_themes` ~line 2356), so an igniting name below the top-60 leader
    # cut (RCAT/AVAV/ONDS on 5/28) never reaches clustering. `_ensure_descriptions`
    # dedups + early-returns on already-described, so the wider list is cheap.
    await _ensure_descriptions(
        list({s["ticker"] for s in _enrich_pool})  # same pool the sector-enrich above built
    )

    # --- Step 1: Re-score existing themes (concurrent, Tavily rate-limited by semaphore) ---
    existing = await get_active_themes()
    await _emit_load_diagnostic(existing, today)

    # --- Step 1.1: Ensure existing theme members also have descriptions ---
    # _ensure_descriptions above only covers top RS leaders. Stocks already in themes
    # are excluded from uncovered_stocks and never get described — so _validate_theme_membership
    # silently skips them (no description = not validated = never removed even if wrong).
    existing_theme_tickers = list({tk for t in existing for tk in (t.get("tickers") or [])})
    await _ensure_descriptions(existing_theme_tickers)

    # Fetch RS data for existing theme tickers not in top leaders
    # This prevents strong themes (Optical, AI Memory) from going Fading
    # just because their constituents aren't in the top 60 by RS composite.
    from agents.market_intelligence.db import get_rs_for_tickers, get_sectors_batch
    existing_tickers = set()
    for t in existing:
        existing_tickers.update(t.get("tickers") or [])
    missing_tickers = [tk for tk in existing_tickers if tk not in stocks_by_ticker]
    if missing_tickers:
        theme_rs = await get_rs_for_tickers(today_str, missing_tickers)
        # Use persistent sector cache (mi_ticker_overrides) so the sector outlier check
        # works even when a stock dips below the RS engine's top-300 enrichment cutoff.
        cached_sectors = await get_sectors_batch(list(theme_rs.keys()))
        for tk, rs_data in theme_rs.items():
            stocks_by_ticker[tk] = {
                "ticker": tk,
                "rs_composite": rs_data.get("rs_composite", 0),
                "rs_1m": rs_data.get("rs_1m", 0),
                "rs_3m": rs_data.get("rs_3m", 0),
                "rs_6m": rs_data.get("rs_6m", 0),
                "sector": cached_sectors.get(tk, "Unknown"),
            }
        logger.info(f"Theme engine: fetched RS for {len(theme_rs)} existing theme tickers not in top leaders")

    logger.info(f"Theme engine: re-scoring {len(existing)} existing themes...")

    # Load persistent exclusions once — passed to rescore + assign to prevent re-entry
    theme_exclusions = await get_all_theme_exclusions()
    if theme_exclusions:
        total_excl = sum(len(v) for v in theme_exclusions.values())
        logger.info(f"Theme engine: loaded {total_excl} persistent ticker exclusions across {len(theme_exclusions)} themes")

    # #217: fetch the operator-protected set ONCE per run (was one DB query per
    # theme inside validation's shield). Safe to fetch early — protection never
    # expires and nothing in this run adds protected pairs (only the operator's
    # /bypass does). Fail-open: on error pass None so the per-theme fallback
    # (and its own fail-open) behaves exactly as before.
    try:
        protected_set: set[tuple[str, str]] | None = await get_operator_protected_set()
    except Exception as e:
        logger.warning(f"Theme engine: operator-protected set prefetch failed — per-theme fallback will retry: {e}")
        protected_set = None

    rescore_results = await asyncio.gather(*[
        _rescore_existing_theme(theme, stocks_by_ticker, today, theme_exclusions=theme_exclusions,
                                protected=protected_set)
        for theme in existing
    ])

    updated_themes: list[dict] = []
    covered_tickers: set[str] = set()
    for theme_result, prune_log in rescore_results:
        changelog.extend(prune_log)
        if theme_result is not None:
            updated_themes.append(theme_result)
            # Cover tickers from ALL stages including Fading — prevents a stock
            # removed by validation from being immediately re-assigned as "uncovered"
            # in the same run. Fading tickers shouldn't attract new assignment either.
            covered_tickers.update(theme_result.get("tickers") or [])

    # Log retirements
    existing_names = {t["name"] for t in existing}
    updated_names = {t["name"] for t in updated_themes}
    for name in existing_names - updated_names:
        orig = next((t for t in existing if t["name"] == name), None)
        if orig:
            changelog.append({
                "type": "theme_retired",
                "theme": name,
                "tickers": list(orig.get("tickers") or []),
            })

    # --- Step 1.5 (ADR 0025 Arm A, #274): retro-sweep flagged 2-member pairs ---
    # Behind THEME_MERGE_ARM (no-op when off). Dissolved themes drop from
    # emission here and get their synthetic Retired row in the engine-drop pass
    # below. Their tickers stay in covered_tickers this run, so the survivor is
    # released to the discovery pools NEXT run (per the ADR).
    updated_themes = await _retro_sweep_flagged_pairs(updated_themes, changelog)

    # --- Step 2: Find uncovered RS leaders + elite covered for sub-theme splits ---

    # Build theme membership lookup: ticker → theme name
    ticker_to_theme: dict[str, str] = {}
    for t in updated_themes:
        if t["stage"] != "Fading":
            for tk in (t.get("tickers") or []):
                ticker_to_theme[tk] = t["name"]

    # Tickers just removed by validation this run — don't re-assign them to any theme
    # in the same run or they'll be immediately put back where they were just kicked from.
    revalidated_out = {e["ticker"] for e in changelog if e.get("type") == "ticker_revalidated_out"}
    if revalidated_out:
        logger.info(f"Theme engine: excluding {revalidated_out} from uncovered pool (just revalidated out)")

    uncovered, assignment_pool = _build_theme_pools(
        leaders, covered_tickers, revalidated_out)
    logger.info(f"Theme engine: {len(uncovered)} uncovered RS leaders (discovery) · "
                f"{len(assignment_pool)} assignment candidates (RS≥{ASSIGN_POOL_RS_FLOOR:.0f}, #476)")

    # Elite covered: RS 80+ stocks already in themes — sent to Claude for
    # sub-theme analysis. These are strong enough to warrant checking if
    # their current theme assignment is the best fit.
    elite_covered = []
    for s in leaders[:40]:
        if (s["ticker"] in covered_tickers
                and s.get("rs_composite", 0) >= 80):
            s_copy = dict(s)
            s_copy["_current_theme"] = ticker_to_theme.get(s["ticker"], "")
            elite_covered.append(s_copy)
    logger.info(f"Theme engine: {len(elite_covered)} elite covered stocks for sub-theme analysis")

    # Filter velocity to stocks not already covered by active themes
    velocity_leaders = [s for s in velocity_all if s["ticker"] not in covered_tickers]
    logger.info(f"Theme engine: {len(velocity_leaders)} velocity accelerators for discovery")

    # Filter turners to stocks not already covered by active themes
    turners = [s for s in turners_all if s["ticker"] not in covered_tickers]
    logger.info(f"Theme engine: {len(turners)} rotation candidates (turners) for discovery")

    # Merge uncovered pools — velocity/turners may overlap with uncovered RS leaders
    all_uncovered_tickers = {s["ticker"] for s in uncovered}
    for s in [*velocity_leaders, *turners]:
        if s["ticker"] not in all_uncovered_tickers:
            stocks_by_ticker.setdefault(s["ticker"], {
                "ticker": s["ticker"],
                "rs_composite": s.get("rs_now", 0),
                "sector": s.get("sector", "Unknown"),
            })

    # Global ticker ban — pulled once and reused for both assignment + discovery.
    # Tickers that have been validation-removed from ≥ N distinct themes in the
    # last D days are treated as untrusted: their description has been pattern-
    # matching into hallucinated themes faster than per-(theme, ticker) cooldowns
    # can fence them off.
    globally_banned_map = await get_globally_banned_tickers(
        min_distinct_themes=_GLOBAL_BAN_THRESHOLD,
        lookback_days=_GLOBAL_BAN_LOOKBACK_DAYS,
    )
    globally_banned: set[str] = set(globally_banned_map.keys())
    if globally_banned:
        logger.info(
            f"Theme engine: {len(globally_banned)} globally-banned tickers "
            f"(≥{_GLOBAL_BAN_THRESHOLD} theme rejections in {_GLOBAL_BAN_LOOKBACK_DAYS}d): "
            f"{sorted(globally_banned)}"
        )
        # One roll-up audit row per run, not one per ticker — banned set changes slowly
        # and per-ticker rows would balloon mi_audit_log without adding signal.
        detail_lines = [
            f"{tk}: {', '.join(sorted(themes))}"
            for tk, themes in sorted(globally_banned_map.items())
        ]
        await log_audit_event(
            "global_ticker_ban_active",
            summary=f"{len(globally_banned)} tickers globally banned from theme assignment",
            detail="\n".join(detail_lines),
        )

    # --- Step 2a: Carryforward deterministic-remove pass (2026-05-15) ---
    # Closes the adds/removes asymmetry. The theme engine ADDS daily
    # (assignment + discovery) but previously only REMOVED via LLM validation
    # on Mon/Wed/Fri. Banned/cooldown/outlier tickers in carryforward
    # survived every non-validation day, letting wrong members persist for
    # weeks (Satellite-biotech 2026-05-15 incident, 4 tickers cycling for
    # ~3 weeks). Strip those members here, EVERY run, BEFORE assignment.
    #
    # STRIP-ONLY: retirement deferred to existing post-assignment logic so
    # a theme can be refilled by the LLM in this same run.
    #
    # #217 note: this fetch is deliberately NOT hoisted next to the
    # protected-set prefetch — it must run AFTER the rescore pass, whose
    # Mon/Wed/Fri validation ADDS cooldowns that this filter and the
    # assignment prompt below must see (same-run re-assignment guard).
    cooldown_set = await get_cooldown_set()
    await _apply_carryforward_deterministic_filter(
        updated_themes, globally_banned, cooldown_set, stocks_by_ticker,
    )

    # --- Step 2b: Assign uncovered stocks to existing themes ---
    # #476: assignment runs on the WIDER assignment_pool (RS-floor); discovery
    # below keeps the narrow top-40 `uncovered` MINUS whatever got assigned
    # (assignment-only widen — the wider pool never leaks into discovery).
    # The wider pool reaches below the top-60 the enrich pass described, so
    # ensure descriptions here (dedup + early-return makes it cheap) — the
    # assignment fn SILENTLY DROPS undescribed names, so this is load-bearing.
    if assignment_pool:
        await _ensure_descriptions([s["ticker"] for s in assignment_pool])
    if assignment_pool and updated_themes:
        _remaining, assign_log = await _assign_uncovered_to_themes(
            assignment_pool, updated_themes, stocks_by_ticker,
            theme_exclusions=theme_exclusions,
            globally_banned=globally_banned,
            cooldown_set=cooldown_set,
            protected=protected_set,
        )
        changelog.extend(assign_log)
        _assigned = {c["ticker"] for c in assign_log if c.get("type") == "ticker_assigned"}
        uncovered = [s for s in uncovered if s["ticker"] not in _assigned]
        logger.info(f"Theme engine: {len(assign_log)} stocks assigned to existing themes "
                    f"({len(_assigned)} distinct), {len(uncovered)} remaining uncovered (discovery)")

    # --- Step 3: Discover new themes ---
    new_raw: list[dict] = []
    has_enough = (len(uncovered) >= NEW_THEME_MIN_STOCKS
                  or len(velocity_leaders) >= NEW_THEME_MIN_STOCKS
                  or len(turners) >= NEW_THEME_MIN_STOCKS
                  or len(elite_covered) >= NEW_THEME_MIN_STOCKS)
    if has_enough:
        new_raw = await _discover_new_themes(
            uncovered, updated_themes, stocks_by_ticker,
            velocity_leaders, turners, elite_covered,
            theme_exclusions=theme_exclusions,
            correlation_clusters=clusters,
            globally_banned=globally_banned,
        )
        logger.info(f"Theme engine: {len(new_raw)} new themes discovered")

    new_themes: list[dict] = await asyncio.gather(*[
        _score_new_theme(raw, stocks_by_ticker, today)
        for raw in new_raw
    ])

    # Phase 1: Name inheritance — if a newly discovered theme's tickers closely match a
    # recently retired theme (Jaccard >= 0.4), inherit the old name so themes don't drift
    # after a brief retirement. _get_theme_history already implements the Jaccard fallback.
    #
    # #214 GUARD (2026-06-09, residual fired night one): do NOT inherit a name that was
    # recently MASS-EVICTED by validation — that signature means the NAME was narrower
    # than the cluster it labeled (validation correctly stripped members the name
    # excluded). Inheriting it resurrects the defect: on 6/9 the first run on the
    # breadth-rule prompt discovered 'U.S. Shale & Onshore E&P' (correct), but Jaccard
    # inheritance renamed the cohort back to 'Pure-Play Hydraulic Fracturing &
    # Completion Services' (12 majors evicted 6/8), restarting the eviction churn.
    # Fail-open: a guard error never blocks inheritance.
    for nt in new_themes:
        history = await _get_theme_history(nt["name"], days=30, tickers=list(nt.get("tickers") or []))
        if history:
            old_name = history[0]["name"]
            if old_name != nt["name"]:
                if await _name_recently_mass_evicted(old_name):
                    logger.info(
                        f"[name inheritance] BLOCKED '{nt['name']}' ← '{old_name}': "
                        f"donor name was recently mass-evicted (#214) — keeping the new name"
                    )
                    await log_audit_event(
                        "name_inheritance_blocked",
                        summary=(f"Kept '{nt['name']}' — inheritance from mass-evicted "
                                 f"'{old_name}' blocked (#214 name-narrower-than-cluster)"),
                        detail=f"Tickers: {', '.join(nt.get('tickers') or [])}",
                    )
                    continue
                logger.info(f"[name inheritance] '{nt['name']}' → '{old_name}' (Jaccard match with retired theme)")
                nt["name"] = old_name

    # --- Step 3b (#266, operator-signed 2026-06-17): validate DISCOVERED themes AT BIRTH ---
    # Run AFTER name-inheritance (the validator judges members against the FINAL name) and
    # BEFORE persist. Extracted to _validate_new_themes_at_birth for unit coverage; same
    # #213-tuned validator the Mon/Wed/Fri pass uses — changes WHEN it runs, not WHAT it checks.
    await _validate_new_themes_at_birth(new_themes, changelog, protected_set)

    # --- Birth-FUNNEL telemetry (#325, 2026-06-17) ---
    # The stage-by-stage discovery funnel was only ever in the container logs, which die on
    # every container recreate — so a 16-day birth drought (active themes 42→15) was dismissed
    # "benign retirement drift" across FOUR L2 fires because nobody could see WHERE births
    # collapsed. The only durable signal was `theme_discovered` (survivors only = 0). Emit the
    # whole funnel to mi_audit_log so the failing stage is pinnable from durable state. PURE
    # observability — no behaviour change. (Diagnosis: 28/40 top RS-100 leaders uncovered, all
    # with descriptions, NOT cooled down → not regime/desc/cooldown; the collapse is in
    # discovery-LLM → score → birth-validate, which this now makes visible.)
    try:
        _retired_n = sum(1 for e in changelog if e.get("type") == "theme_retired")
        await log_audit_event(
            "theme_engine_funnel",
            summary=(f"births: uncovered={len(uncovered)} v/t/e="
                     f"{len(velocity_leaders)}/{len(turners)}/{len(elite_covered)} "
                     f"discovery={'ON' if has_enough else 'OFF'} → LLM={len(new_raw)} "
                     f"→ survived={len(new_themes)} | retired={_retired_n}"),
            detail=json.dumps({
                "uncovered": len(uncovered), "velocity": len(velocity_leaders),
                "turners": len(turners), "elite_covered": len(elite_covered),
                "discovery_called": bool(has_enough), "new_raw_llm": len(new_raw),
                "new_themes_survived": len(new_themes), "retired": _retired_n,
                "survived_names": [nt.get("name") for nt in new_themes],
            }),
        )
    except Exception:
        pass  # telemetry must never break the run

    # Log new themes + write to audit log
    for nt in new_themes:
        tickers = list(nt.get("tickers") or [])
        changelog.append({
            "type": "theme_new",
            "theme": nt["name"],
            "tickers": tickers,
        })
        await log_audit_event(
            "theme_discovered",
            summary=f"New theme: {nt['name']} ({len(tickers)} stocks)",
            detail=f"Tickers: {', '.join(tickers)}\nThesis: {nt.get('description', nt.get('thesis', ''))}",
        )

    # Write retirements to audit log
    for entry in changelog:
        if entry.get("type") == "theme_retired":
            await log_audit_event(
                "theme_retired",
                summary=f"Retired: {entry['theme']}",
                detail=f"Last tickers: {', '.join(entry.get('tickers') or [])}",
            )

    # Write stage changes to audit log — enriched detail enables oscillation analysis
    # (transitions per theme, days_between_transitions, score-Δ at flip) via SQL tomorrow.
    for entry in changelog:
        if entry.get("type") == "stage_change":
            score = entry.get("score")
            smooth_delta = entry.get("smooth_delta")
            age_days = entry.get("age_days")
            ticker_count = entry.get("ticker_count")
            detail_parts = [
                f"score={score:.1f}" if isinstance(score, (int, float)) else f"score={score}",
                f"Δ={smooth_delta:+.1f}" if isinstance(smooth_delta, (int, float)) else None,
                f"age_days={age_days}" if age_days is not None else None,
                f"tickers={ticker_count}" if ticker_count is not None else None,
            ]
            await log_audit_event(
                "stage_change",
                summary=f"{entry['theme']}: {entry.get('old_stage')} → {entry.get('new_stage')}",
                detail=", ".join(p for p in detail_parts if p),
            )

    # --- Step 4: Deduplicate overlapping themes, merge, cap, sort, persist ---
    # Strip commodity contradictions from new clusters before merge (e.g. gold miners in uranium theme)
    new_themes = _strip_commodity_contradictions(new_themes)
    # Pass existing theme names so they can't be absorbed by new clusters
    existing_names: set[str] = {t["name"] for t in updated_themes}

    # Load sub-theme parent relationships from yesterday's DB snapshot so sub-themes
    # created in prior runs are still exempt from re-absorption by their parent.
    prior_sub_parents: dict[str, str] = {}
    for t in existing:
        pt = t.get("parent_theme")
        if pt:
            prior_sub_parents[t["name"]] = pt

    # ── ADR 0032 Phase 2: resolve THEME_SUBTHEME_ARM once per run (DB toggle,
    # fail-closed). OFF (default / any read error) ⇒ the ctx is disabled ⇒
    # every Route-A/B branch is skipped and the passes below are byte-identical
    # to pre-Phase-2 behavior.
    subtheme_arm_on = await get_theme_subtheme_arm_enabled()
    subtheme_ctx = make_subtheme_route_ctx(
        subtheme_arm_on,
        sectors_by_ticker=(
            {
                tk: s.get("sector") for tk, s in stocks_by_ticker.items()
                if s.get("sector") and s.get("sector") != "Unknown"
            }
            if subtheme_arm_on else None
        ),
    )

    all_themes = await _merge_overlapping_themes(
        updated_themes + new_themes,
        stocks_by_ticker,
        protected_names=existing_names,
        sub_theme_parents=prior_sub_parents,
        subtheme_ctx=subtheme_ctx,
    )
    await _emit_pipeline_diagnostic(all_themes, "after_merge_1", sub_theme_parents=prior_sub_parents)
    all_themes.sort(key=lambda t: (-(t.get("score") or 0), t.get("name") or ""))
    all_themes = await _enforce_max_themes_per_stock(all_themes)
    await _emit_pipeline_diagnostic(all_themes, "after_cap_1", sub_theme_parents=prior_sub_parents)

    # --- Step 4b: Fat-theme sub-theme splitting ---
    # For themes that grew too broad, ask Sonnet (+ optional Opus) to split off one sub-group.
    advisor_calls_used = 0
    fat_themes = [
        t for t in all_themes
        if len(t.get("tickers") or []) > MAX_THEME_STOCKS
        and t.get("stage") not in ("Fading",)
        and not t.get("parent_theme")  # never split a sub-theme further
    ]
    # ── ADR 0032 Phase 2 Route B (behind THEME_SUBTHEME_ARM; arm OFF ⇒ []
    # with no DB access): a sole-sub-theme ecosystem-dominant theme qualifies
    # for ONE deliberate split even below the >20 fat trigger. Same mechanics
    # (`_split_fat_theme`, removal semantics per fork F-5) — only the
    # eligibility gate widens.
    dominant_names: set[str] = set()
    for t in await _nominate_dominant_split_themes(
        all_themes, stocks_by_ticker, arm_enabled=subtheme_arm_on,
    ):
        if t["name"] not in {f["name"] for f in fat_themes}:
            fat_themes.append(t)
            dominant_names.add(t["name"])

    if fat_themes:
        logger.info(f"[fat-theme split] {len(fat_themes)} fat theme(s) eligible for splitting")

    new_sub_themes: list[dict] = []
    this_run_sub_parents: dict[str, str] = {}

    for fat in fat_themes:
        sub_raw, advisor_calls_used = await _split_fat_theme(
            fat, stocks_by_ticker, advisor_calls_used,
            reason_line=(
                f"is ecosystem-dominant with no sub-theme structure "
                f"({len(fat.get('tickers') or [])} stocks)"
                if fat["name"] in dominant_names else None
            ),
        )
        if sub_raw is None:
            continue

        valid_tickers = [tk for tk in sub_raw["tickers"] if tk in (fat.get("tickers") or [])]
        if len(valid_tickers) < _SPLIT_MIN_STOCKS:
            continue

        # Remove sub-group from parent
        fat["tickers"] = [tk for tk in (fat.get("tickers") or []) if tk not in valid_tickers]

        # Score and stage the sub-theme
        sub_scored = await _score_new_theme(
            {"name": sub_raw["name"], "tickers": valid_tickers, "thesis": sub_raw["thesis"]},
            stocks_by_ticker,
            today,
        )
        sub_scored["parent_theme"] = fat["name"]
        new_sub_themes.append(sub_scored)
        this_run_sub_parents[sub_raw["name"]] = fat["name"]
        logger.info(
            f"[fat-theme split] applied: '{sub_raw['name']}' ({len(valid_tickers)} stocks) "
            f"split from '{fat['name']}'"
        )

    # Fold today's newborn links into the running parent map regardless of
    # whether the `if new_sub_themes` block below runs — `_restore_sub_theme_links`
    # (called just before `_save_themes`) needs the union of prior-day links +
    # today's splits to reconcile every continuing child, not just ones merged
    # again this run.
    prior_sub_parents.update(this_run_sub_parents)

    if new_sub_themes:
        combined_sub_parents = {**prior_sub_parents, **this_run_sub_parents}
        await _emit_pipeline_diagnostic(
            all_themes + new_sub_themes, "after_split", sub_theme_parents=combined_sub_parents
        )
        # Merge sub-themes into all_themes, protecting them from re-absorption.
        # Route-A children born in merge_1 join the protected set here (they are
        # incumbents-of-this-run, like split children); with the arm off
        # routed_children is empty and the set is byte-identical to pre-Phase-2.
        all_themes = await _merge_overlapping_themes(
            all_themes + new_sub_themes,
            stocks_by_ticker,
            protected_names=(
                existing_names
                | set(this_run_sub_parents.keys())
                | set(subtheme_ctx.get("routed_children") or {})
            ),
            sub_theme_parents=combined_sub_parents,
            subtheme_ctx=subtheme_ctx,
        )
        await _emit_pipeline_diagnostic(all_themes, "after_merge_2", sub_theme_parents=combined_sub_parents)
        all_themes.sort(key=lambda t: (-(t.get("score") or 0), t.get("name") or ""))
        all_themes = await _enforce_max_themes_per_stock(all_themes)
        await _emit_pipeline_diagnostic(all_themes, "after_cap_2", sub_theme_parents=combined_sub_parents)

    # --- Step 4c (ADR 0025 Arm B, #274): thesis-coherence merge pass ---
    # Behind THEME_MERGE_ARM (no-op when off). Runs after the final Pass1/1.5/cap
    # sequence and BEFORE the engine-drop Retired-row synthesis: absorbed themes
    # carry their own Retired rows (parent_theme=successor), so they are in
    # final_names below and never double-retire.
    all_themes = await _run_thesis_merge_pass(
        all_themes, {t["name"] for t in existing}, changelog, protected_set, today,
        stocks_by_ticker=stocks_by_ticker,
    )

    # Synthesize Retired rows for previously-active themes that were dropped
    # during merge passes (Pass1 protect_strip → cap_drop, or Pass1.5
    # absorption). Without this, themes silently vanish from emission with
    # their last row stuck at Mainstream/Accelerating — trips the L1
    # zombie_theme invariant in system_audit.py.
    #
    # Lifecycle note: these jump directly Mainstream/Accelerating → Retired
    # (skip Fading). The normal 5-day Fading→Retired transition can't
    # complete here because once the theme stops being re-emitted, the 7d
    # recency cap in get_active_themes ages it out of `existing` before
    # day 5 of Fading can be reached. Engine-side equivalent of what
    # canonicalization (R3) would do; until R3 ships, this stub keeps
    # the lifecycle ledger consistent.
    final_names = {t["name"] for t in all_themes}
    lost = [
        t for t in existing
        if t.get("stage") != "Retired" and t["name"] not in final_names
    ]
    if lost:
        # Recover successor pointers from today's audit log so the Retired
        # row carries parent_theme. theme_pass1_5_absorption summary format:
        # "Pass1.5: '<lost>' -> '<successor>'". theme_pass1_protect_strip
        # detail format: "i='<protector>' ... j='<lost>' ...".
        successor_by_lost: dict[str, str] = {}
        pool = await get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT event_type, summary, detail
                FROM mi_audit_log
                WHERE event_type IN ('theme_pass1_5_absorption', 'theme_pass1_protect_strip')
                  AND (created_at AT TIME ZONE 'America/New_York')::date
                      = (NOW() AT TIME ZONE 'America/New_York')::date
            """)
        import re as _re
        for r in rows:
            if r["event_type"] == "theme_pass1_5_absorption":
                m = _re.search(r"'([^']+)' -> '([^']+)'", r["summary"] or "")
                if m:
                    successor_by_lost.setdefault(m.group(1), m.group(2))
            else:  # theme_pass1_protect_strip
                im = _re.search(r"i='([^']+)'", r["detail"] or "")
                jm = _re.search(r"j='([^']+)'", r["detail"] or "")
                if im and jm:
                    successor_by_lost.setdefault(jm.group(1), im.group(1))

        retire_rows = []
        for t in lost:
            successor = successor_by_lost.get(t["name"])
            note = (
                f"Auto-retired {today_str}: "
                + (f"absorbed/superseded by '{successor}'" if successor
                   else f"dropped during merge/absorption (no successor found)")
                + f" (prior stage {t.get('stage', 'Unknown')}, "
                + f"{len(t.get('tickers') or [])} tickers)."
            )
            retire_rows.append({
                "theme_date": today,
                "name": t["name"],
                "stage": "Retired",
                "score": 0.0,
                "rs_avg": None,
                "description": note,
                "tickers": [],
                "parent_theme": successor,
                "pct_above_20sma": None,
            })
        all_themes = all_themes + retire_rows
        with_successor = sum(1 for r in retire_rows if r["parent_theme"])
        await log_audit_event(
            "theme_auto_retired",
            summary=f"Auto-retired {len(lost)} theme(s) dropped during merge passes ({with_successor} with successor pointer)",
            detail="\n".join(
                f"'{r['name']}' -> parent='{r.get('parent_theme') or '(unknown)'}'"
                for r in retire_rows
            ),
        )
        logger.info(f"Theme engine: auto-retired {len(lost)} dropped theme(s), {with_successor} with successor")

    # #471: reconcile parent_theme against the truly final list right before
    # save — see _restore_sub_theme_links docstring. Must run after the
    # auto-retire block above (retire_rows can drop a parent from `all_themes`
    # too) and after _run_thesis_merge_pass, so it's the last mutation.
    _restore_sub_theme_links(all_themes, prior_sub_parents)

    if all_themes:
        await _save_themes(all_themes)

        # ADR 0032 Phase 1 — theme→ecosystem mapping (read-model only; no
        # lifecycle effect). Assign any theme in today's snapshot that has no
        # mi_theme_ecosystems row yet: new births get mapped at birth, renamed
        # themes self-heal next run, and a partial backfill converges.
        await _map_ecosystems_nonfatal(
            [t for t in all_themes if t.get("stage") != "Retired"],
            "theme ecosystems")

    # Post-save: detect constituent churn (P13). Flag (theme, ticker) pairs
    # that have re-entered the theme 2+ times in the last 10 days — symptom
    # of validation-induced flip-flop or assignment indecision.
    await _detect_theme_constituent_churn()

    logger.info(
        f"Theme engine complete: {len(updated_themes)} updated, {len(new_themes)} new, "
        f"{len(existing) - len(updated_themes)} retired — {today_str}"
    )
    return all_themes, changelog


async def _detect_theme_constituent_churn() -> None:
    """P13 — flag tickers entering a theme 2+ times in 10 days.

    Each "reentry" is a day where the ticker is in the theme today but
    was NOT in it yesterday. A ticker that's been re-added 2+ times
    inside the rolling window is high-churn — usually a Haiku validation
    flip-flop or an assignment-then-strip cycle. Auto-suggests review.

    Emits `theme_constituent_churn` audit event with (theme, ticker,
    reentry_count) for each high-churn pair. Daily nightly run; the
    review action_when_ready then surfaces the audit log.
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            WITH expanded AS (
                SELECT name, unnest(tickers) AS ticker, theme_date
                FROM mi_themes
                WHERE theme_date >= CURRENT_DATE - INTERVAL '10 days'
            ),
            with_gaps AS (
                SELECT name, ticker, theme_date,
                       LAG(theme_date) OVER (
                           PARTITION BY name, ticker ORDER BY theme_date
                       ) AS prev_date
                FROM expanded
            )
            SELECT name, ticker, COUNT(*) AS reentries
            FROM with_gaps
            WHERE prev_date IS NOT NULL
              AND theme_date > prev_date + INTERVAL '1 day'
            GROUP BY name, ticker
            HAVING COUNT(*) >= 2
            ORDER BY 3 DESC
        """)
    if not rows:
        return
    sample = ", ".join(f"{r['ticker']}↔{r['name'][:20]}({r['reentries']})" for r in rows[:5])
    detail_lines = [f"{r['name']} | {r['ticker']} | reentries={r['reentries']}" for r in rows]
    await log_audit_event(
        "theme_constituent_churn",
        f"{len(rows)} high-churn (theme,ticker) pair(s) in last 10d — sample: {sample}",
        "\n".join(detail_lines)[:2000],
    )


async def get_today_themes(d: "str | date | None" = None) -> list[dict]:
    """Fetch today's themes from DB."""
    from datetime import date as date_type
    if d is None:
        target = date_type.today()
    elif isinstance(d, str):
        target = date_type.fromisoformat(d)
    else:
        target = d

    pool = await get_pool()
    async with pool.acquire() as conn:
        # Fall back to most recent date if no theme data for requested date
        count = await conn.fetchval(
            "SELECT COUNT(*) FROM mi_themes WHERE theme_date = $1", target
        )
        if not count:
            latest = await conn.fetchval("SELECT MAX(theme_date) FROM mi_themes")
            if latest is not None:
                target = latest
        rows = await conn.fetch(
            "SELECT * FROM mi_themes WHERE theme_date = $1 ORDER BY score DESC",
            target,
        )
        return [dict(r) for r in rows]
