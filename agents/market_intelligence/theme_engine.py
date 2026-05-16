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
    get_ticker_breadth_above_sma20,
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

THEME_MODEL = "claude-sonnet-4-6"

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
    """
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
                model="claude-haiku-4-5-20251001",
                max_tokens=500,
                messages=[{"role": "user", "content": PROMPT_PREFIX + "\n".join(chunk_lines)}],
            )
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

        # Remove themes that were merged/retired — not in the final list
        final_names = [t["name"] for t in themes]
        await conn.execute("""
            DELETE FROM mi_themes
            WHERE theme_date = $1 AND name != ALL($2)
        """, today, final_names)


async def _validate_theme_membership(
    theme_name: str,
    tickers: list[str],
    changelog: list[dict],
) -> list[str]:
    """
    Ask Claude Haiku whether each stock's description is consistent with the theme.
    Removes stocks that clearly don't belong. Runs on Mon/Wed/Fri during re-scoring.

    This catches stocks that were added before descriptions existed or were incorrectly
    clustered (e.g. AGRO ending up in an IP Licensing theme).
    """
    from agents.market_intelligence.universe import TICKER_DESC

    if len(tickers) < 2:
        return tickers

    # Include ALL tickers — described ones get their description, undescribed ones
    # are identified by ticker symbol alone (Haiku knows CAR=Avis, UBER=rideshare, etc.)
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
                        model="claude-haiku-4-5-20251001",
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
                        detail="429 on claude-haiku-4-5",
                    )
                    await asyncio.sleep(wait)
        # Defensive extraction — Haiku occasionally returns non-text blocks
        # or empty content, which previously surfaced as cryptic parse errors.
        if not resp.content:
            raise ValueError("empty Haiku response")
        raw_block = resp.content[0]
        raw = (getattr(raw_block, "text", "") or "").strip()
        if not raw:
            raise ValueError(f"Haiku returned no text (stop_reason={resp.stop_reason})")
        # Strip code fences if present
        if raw.startswith("```"):
            parts = raw.split("\n", 1)
            raw = parts[1].rstrip("` \n").strip() if len(parts) > 1 else raw.strip("` ")
        # Extract the outermost JSON object by tracking brace depth.
        # The naive r'\{[^{}]*\}' regex fails when Haiku adds nested objects
        # (e.g. {"remove": [], "notes": {"why": "..."}}) because [^{}] stops
        # at the inner brace. Brace-depth tracking handles arbitrary nesting.
        raw = _extract_json_object(raw)
        result = json.loads(raw)
        remove_val = result.get("remove") or []  # guard against "remove": null
        to_remove = {tk.upper() for tk in remove_val if isinstance(tk, str)}

        # Never remove so many that the theme drops below minimum
        survivable = [t for t in tickers if t not in to_remove]
        if len(survivable) < PRUNE_MIN_TICKERS:
            logger.warning(
                f"Theme '{theme_name}': re-validation would drop below {PRUNE_MIN_TICKERS} tickers — skipping removals"
            )
            return tickers

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
                        summary=f"{tk} removed from '{theme_name}' by validation",
                        detail=f"Description: '{desc}' — Haiku flagged as not matching theme",
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
        if isinstance(e, (anthropic.APIError, asyncio.TimeoutError)):
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
            f"keeping all tickers. Raw Haiku response: {raw_snippet!r}"
        )
        await log_audit_event(
            "validation_error",
            summary=f"Validation parse error for '{theme_name}' — tickers unchanged",
            detail=f"{type(e).__name__}: {e} | raw={raw_snippet!r}",
        )
        return tickers


async def _rescore_existing_theme(
    theme: dict,
    stocks_by_ticker: dict[str, dict],
    today: date,
    theme_exclusions: dict[str, set[str]] | None = None,
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
        tickers = await _validate_theme_membership(name, tickers, changelog)

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
        "tickers": list(set(tickers) | set(strong_stocks)),  # keep known + add strong
        "pct_above_20sma": pct_breadth,
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

    # Load active cooldowns and inject as a hard constraint in the prompt
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
        # Transient Anthropic failures (5xx, network, timeout) resolve next run —
        # route to a non-`_error` event_type so they don't trip the L1 invariant.
        if isinstance(e, (anthropic.APIError, asyncio.TimeoutError)) and not isinstance(e, anthropic.RateLimitError):
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

        # Validate theme exists
        theme = theme_by_name.get(theme_name)
        if not theme:
            logger.warning(f"Assignment skipped: theme '{theme_name}' not found")
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
            # Run Haiku validation on just the new additions in context of this theme
            validated = await _validate_theme_membership(theme["name"], theme.get("tickers") or [], changelog)
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
                    "REQUIRED. Write your clustering reasoning BEFORE proposing themes. "
                    "For each candidate group: (1) what shared catalyst or business model connects them, "
                    "(2) which stocks clearly belong vs. are borderline, (3) whether the group is large "
                    "enough (≥3 stocks) and coherent enough to name. Reject spurious clusters here."
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
                            "description": "Specific theme name e.g. 'Edge AI Inference', not 'Technology'",
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
            model="claude-opus-4-6",
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
        try:
            from agents.market_intelligence.spend_tracker import log_anthropic_call
            await log_anthropic_call(
                model="claude-opus-4-6",
                caller=f"theme_advisor_{caller}",
                usage=resp.usage,
            )
        except Exception as e:
            logger.warning(f"Spend log (theme_advisor_{caller}) failed: {e}")
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
                            "name": {"type": "string", "description": "Sub-theme name"},
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
) -> tuple[dict | None, int]:
    """
    Ask Sonnet (with optional Opus escalation) whether a fat theme (>MAX_THEME_STOCKS)
    has a coherent sub-group worth splitting off.

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

    prompt = f"""You are analyzing a theme that has grown too broad ({len(tickers)} stocks).
Your job: identify ONE coherent sub-group to split off as a more specific sub-theme.

Parent theme: {name}
Stocks:
{chr(10).join(stock_lines)}

SPLIT RULES:
- Propose at most ONE split
- Sub-group must have {_SPLIT_MIN_STOCKS}–{_SPLIT_MAX_STOCKS} stocks, all ideally RS >= 70
- Must represent a TIGHTER sub-industry (e.g. "compound semi wafer fabs" within a broad photonic semi theme)
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
        logger.warning(f"[fat-theme split] '{name}': failed ({e}) — skipping split")

    return None, advisor_calls


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
- A stock CAN move from an existing theme to a new sub-theme if the sub-theme is more specific
- A stock should appear in at most 2 themes. Do NOT include a stock in a new theme if it already appears in 2+ existing themes (check the list above)
- When in doubt whether a stock belongs — exclude it. A smaller, correct theme beats a larger, wrong one.
- Return zero themes if no clear cluster exists — that is the correct answer
- Focus on what the market is pricing in RIGHT NOW based on price action, not macro narratives

Before calling report_themes, ask yourself: am I genuinely uncertain about any cluster?
Consult the advisor FIRST if any of these apply:
- A stock fits multiple possible themes and you're not sure which is the better home
- You have a 2-stock cluster and aren't confident it's a real theme vs. coincidence
- Stocks share a sector label but their actual business drivers feel different to you
- You want to name a theme but can't articulate a crisp specific thesis
If none of these apply, call report_themes directly — advisor consultation is for real ambiguity only."""

    try:
        client = _get_anthropic_client()
        messages: list[dict] = [{"role": "user", "content": prompt}]
        advisor_calls = 0

        while True:
            response = await client.messages.create(
                model=THEME_MODEL,
                max_tokens=1500,
                tools=[_THEME_DISCOVERY_TOOL, _ADVISOR_TOOL],
                tool_choice={"type": "auto"},
                messages=messages,
            )

            tool_uses = [b for b in response.content if b.type == "tool_use"]

            # Model stopped without calling a tool — shouldn't happen but handle gracefully
            if not tool_uses:
                logger.warning("Theme discovery: model stopped without calling report_themes")
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

    except Exception as e:
        # Transient Anthropic failures (5xx, network, timeout) resolve next run —
        # route to a non-`_error` event_type so they don't trip the L1 invariant.
        if isinstance(e, (anthropic.APIError, asyncio.TimeoutError)) and not isinstance(e, anthropic.RateLimitError):
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


# Keyword groups for sector-level theme consolidation.
# Themes whose names match the same group are capped at MAX_THEMES_PER_SECTOR.
_SECTOR_KEYWORD_GROUPS: list[tuple[str, list[str], int]] = [
    # (group_key, keywords, max_themes)
    ("oil_gas", ["oil", "gas", "lng", "e&p", "oilfield", "petroleum", "crude",
                 "permian", "drilling", "refin", "upstream", "downstream",
                 "midstream", "completion", "pumping"], 2),
    ("biotech", ["biotech", "clinical", "orphan drug", "gene edit", "crispr",
                 "mrna", "therapeutics", "pharma", "drug"], 0),  # exclude entirely
    ("satellite", ["satellite", "space", "earth observation"], 2),
    ("optical", ["optical", "photonic"], 2),
    ("agriculture", ["agri", "fertilizer", "crop", "nitrogen", "nutrient",
                      "agricultural", "herbicide", "pesticide"], 2),
    ("chemicals", ["chemical", "polymer", "acetyl", "specialty chem",
                    "petrochemical"], 2),
    ("ip_licensing", ["ip licensing", "patent", "royalty software"], 1),
]
MAX_THEMES_PER_SECTOR_DEFAULT = 2


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


async def _merge_overlapping_themes(
    themes: list[dict],
    stocks_by_ticker: dict[str, dict],
    protected_names: set[str] | None = None,
    sub_theme_parents: dict[str, str] | None = None,
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
                if j_is_subtopic_of_i:
                    continue  # coexistence — never re-absorb a sub-theme into its parent

                j_protected = protected_names and themes[j]["name"] in protected_names
                if j_protected:
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
            # else: just drop it (shouldn't happen)

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
        get_rs_leaders(today_str, limit=60),
        get_rs_velocity(today_str, min_rs=THEME_RS_MIN, limit=30),
        get_rs_turners(today_str, max_rs_4w_ago=30.0, min_consecutive_weeks=3, limit=30),
    )

    if not leaders:
        logger.warning("Theme engine: no RS data — run RS engine first")
        return [], []

    # Enrich with sector data (concurrent, rate-limited by semaphore)
    logger.info(f"Theme engine: enriching {len(leaders)} stocks with sector data...")

    async def _enrich_sector(stock: dict) -> None:
        if not stock.get("sector"):
            async with _SECTOR_SEM:
                stock["sector"] = await _get_sector(stock["ticker"])

    await asyncio.gather(*[_enrich_sector(s) for s in leaders])

    stocks_by_ticker = {s["ticker"]: s for s in leaders}

    # --- Step 0.5: Ensure every RS leader has a description before clustering ---
    # Fetches from yfinance + Claude Haiku for any stock missing one, persists to DB.
    # Stocks that still have no description after this step are excluded from clustering.
    await _ensure_descriptions([s["ticker"] for s in leaders])

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

    rescore_results = await asyncio.gather(*[
        _rescore_existing_theme(theme, stocks_by_ticker, today, theme_exclusions=theme_exclusions)
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

    uncovered = [
        s for s in leaders[:40]
        if s["ticker"] not in covered_tickers
        and s["ticker"] not in revalidated_out
        and s.get("rs_composite", 0) >= THEME_RS_MIN
    ]
    logger.info(f"Theme engine: {len(uncovered)} uncovered RS leaders for new theme discovery")

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
    cooldown_set = await get_cooldown_set()
    await _apply_carryforward_deterministic_filter(
        updated_themes, globally_banned, cooldown_set, stocks_by_ticker,
    )

    # --- Step 2b: Assign uncovered stocks to existing themes ---
    if uncovered and updated_themes:
        uncovered, assign_log = await _assign_uncovered_to_themes(
            uncovered, updated_themes, stocks_by_ticker,
            theme_exclusions=theme_exclusions,
            globally_banned=globally_banned,
        )
        changelog.extend(assign_log)
        logger.info(f"Theme engine: {len(assign_log)} stocks assigned to existing themes, {len(uncovered)} remaining uncovered")

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
    for nt in new_themes:
        history = await _get_theme_history(nt["name"], days=30, tickers=list(nt.get("tickers") or []))
        if history:
            old_name = history[0]["name"]
            if old_name != nt["name"]:
                logger.info(f"[name inheritance] '{nt['name']}' → '{old_name}' (Jaccard match with retired theme)")
                nt["name"] = old_name

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

    all_themes = await _merge_overlapping_themes(
        updated_themes + new_themes,
        stocks_by_ticker,
        protected_names=existing_names,
        sub_theme_parents=prior_sub_parents,
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
    if fat_themes:
        logger.info(f"[fat-theme split] {len(fat_themes)} fat theme(s) eligible for splitting")

    new_sub_themes: list[dict] = []
    this_run_sub_parents: dict[str, str] = {}

    for fat in fat_themes:
        sub_raw, advisor_calls_used = await _split_fat_theme(
            fat, stocks_by_ticker, advisor_calls_used
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

    if new_sub_themes:
        combined_sub_parents = {**prior_sub_parents, **this_run_sub_parents}
        await _emit_pipeline_diagnostic(
            all_themes + new_sub_themes, "after_split", sub_theme_parents=combined_sub_parents
        )
        # Merge sub-themes into all_themes, protecting them from re-absorption
        all_themes = await _merge_overlapping_themes(
            all_themes + new_sub_themes,
            stocks_by_ticker,
            protected_names=existing_names | set(this_run_sub_parents.keys()),
            sub_theme_parents=combined_sub_parents,
        )
        await _emit_pipeline_diagnostic(all_themes, "after_merge_2", sub_theme_parents=combined_sub_parents)
        all_themes.sort(key=lambda t: (-(t.get("score") or 0), t.get("name") or ""))
        all_themes = await _enforce_max_themes_per_stock(all_themes)
        await _emit_pipeline_diagnostic(all_themes, "after_cap_2", sub_theme_parents=combined_sub_parents)

    if all_themes:
        await _save_themes(all_themes)

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
