"""Theme-axis SHADOW measurement scaffold — meta-rubric STEP-0 (#329) + STEP-1 (#367).

PURPOSE (SHADOW ONLY — drives NOTHING). For each scored EP HIGH, record alongside the
live judge grade the signals the live judge is structurally blind to today:

  1. AS-OF theme heat — the stage/score of the hottest active theme containing the ticker
     as of the alert date (NO lookahead). NULL when the name is themeless.
  2. STEP-0 structural attribution (ticker-based) — how many of the theme's OTHER cohort
     TICKERS OR theme keywords (name + description, 4+ letter words) appear in the catalyst
     grounded_text. Kept for continuity/comparison, but the #369 backfill finding (6/24)
     showed this is the WRONG INSTRUMENT: grounded_text is the raw SEC 8-K, which names peers
     by COMPANY NAME, not ticker — so ticker-intersection can structurally never match a peer
     regardless of relevance.
  3. STEP-1 (a) company-NAME attribution — the #369 fix: same shape as (2), but matches
     normalized COMPANY NAMES (not tickers) against grounded_text.
  4. STEP-1 (b) co-movement — is the ticker moving WITH its theme cohort that day (same-day
     pct move, subject vs. the cohort median)? The CO-EQUAL candidate signal (6/24 correction
     walked this back from "primary" to co-equal with (3) — neither is assumed to dominate;
     the STEP-1 health read measures which one actually separates "theme is the driver" from
     "uses theme vocabulary").

This module owns ONLY the pure attribution logic + the shadow-table writer. It reads `r`
(read-only) and writes ONLY `mi_theme_axis_shadow` (+ the mi_ticker_overrides company-name
CACHE, an additive persistent lookup, never mutated in a way that could affect grading). It
never mutates trade state, never touches the live grade/judge output, and never raises into
the caller (the writer swallows every error to an audit event — pure telemetry throughout).

Both (2) and (3)/(4) are logged side by side — NEITHER is a flip-gate (#329 6/24: the
disagreement rate is a HEALTH GAUGE ONLY). The #368 STEP-2 weighting decision is the
operator's call, gated on a labeled cohort, not on this module.
"""
from __future__ import annotations

import asyncio
import logging
import re
import statistics
from typing import Any

from agents.market_intelligence.collector import get_fmp_profile
from agents.market_intelligence.db import (
    get_company_names_batch,
    get_daily_moves,
    get_theme_heat_asof,
    log_audit_event,
    upsert_company_names_batch,
)

logger = logging.getLogger(__name__)

# Ticker shape: 2-5 uppercase letters, word-bounded, CASE-SENSITIVE (so "care" doesn't match
# CARE / "on" doesn't match ON). English-word false positives are filtered through the shared
# _PREPOSITION_SKIP frozenset (the set that exists for exactly this in agent.py).
_TICKER_RE = re.compile(r"\b[A-Z]{2,5}\b")
# Theme keyword tokens: 4+ letter words, lowercased — mirrors the existing theme-engine
# keyword-overlap tokenizer (theme_engine.py unknown-sector fallback). Theme name+description
# is short + domain-specific, so no extra stopword layer (faithful to the established pattern).
_KEYWORD_RE = re.compile(r"\b\w{4,}\b")

# ─── STEP-1 (a): company-NAME matching (#367 / #369 fix) ──────────────────────────────────
# Normalization rule (documented here, not tuned — a starting rule for a HEALTH GAUGE, not a
# flip-gate): lowercase, drop punctuation, drop a leading "the", strip TRAILING corporate-
# suffix tokens (repeatedly, e.g. "Foo Holdings Inc" -> "foo"), then require the remainder be
# either >=2 tokens, or exactly 1 token that is long (>=6 chars) AND not a generic business
# word that would false-positive standing alone in ordinary catalyst prose (e.g. "Group",
# "Global", "Solutions"). Ambiguous/too-short remainders are EXCLUDED from matching entirely
# — deliberately conservative (under-count over false-match), mirroring the STEP-0 ticker
# signal's own subject-exclusion asymmetry.
_CORPORATE_SUFFIX_TOKENS: frozenset[str] = frozenset({
    "inc", "incorporated", "corp", "corporation", "co", "company",
    "ltd", "limited", "llc", "plc", "holdings", "holding", "group",
    "sa", "nv", "ag", "se", "pte", "gmbh", "spa", "srl", "kk",
})
_LEADING_ARTICLE_TOKENS: frozenset[str] = frozenset({"the"})
_AMBIGUOUS_SINGLE_TOKENS: frozenset[str] = frozenset({
    "group", "holdings", "holding", "systems", "solutions", "technologies", "technology",
    "industries", "international", "global", "capital", "partners", "resources",
    "enterprises", "ventures", "brands", "energy", "financial", "health", "media", "labs",
    "networks", "digital", "national", "united", "american", "world", "star", "sun",
})
_MIN_SINGLE_TOKEN_LEN = 6
_PUNCT_RE = re.compile(r"[.,'’]")


def compute_structural_attribution(
    grounded_text: str | None,
    subject_ticker: str,
    cohort_tickers: list[str] | None,
    theme_name: str | None,
    theme_description: str | None,
) -> tuple[int, bool, list[str]]:
    """Count distinct theme-cohort tickers OR theme keywords appearing in the catalyst
    grounded_text. Returns (score, attributable, matched_terms).

    The subject ticker is EXCLUDED from the cohort before matching — the corpus is ABOUT the
    subject ticker (it appears trivially), so attribution asks "does the catalyst reference the
    REST of the theme?", not "does it mention itself." Without this exclusion every themed EP
    would score >=1 and the metric would be meaningless.

    `matched_terms` are TAGGED by kind: 'ticker:FRND' (a PEER cohort ticker — STRONG evidence
    the theme is the driver) vs 'kw:lithium' (a theme keyword — WEAKER: a themed name's catalyst
    almost always uses the theme's vocabulary even when the rest of the cohort isn't driving the
    move, so a keyword-only match is trivially common). STEP-0 keeps BOTH (the #329 6/24 spec is
    "cohort tickers OR keywords") but PRESERVES the distinction so the later data-sizing pass can
    down-weight keyword-only attribution — this is the "auditable" requirement the bare int can't
    meet. The keyword pass shares the subject's own-vocabulary triviality the ticker exclusion
    closes; tagging is the mitigation, not silent dropping (operator's call to down-weight).

    score = |distinct peer cohort tickers in text| + |distinct theme keywords in text|.
    attributable = score > 0. Themeless / no-match -> (0, False, []).
    """
    if not grounded_text:
        return 0, False, []

    # Lazy import: agent.py imports ep_detector at module load and ep_detector imports this
    # module, so a top-level `from ...agent import _PREPOSITION_SKIP` would be circular. Import
    # inside the function to keep the SHARED single source of the English-word skip set
    # (CLAUDE.md: add new prepositions THERE, one place) without the module-load cycle.
    from agents.market_intelligence.agent import _PREPOSITION_SKIP

    matched: list[str] = []

    # ── Ticker pass (case-sensitive, word-bounded, English-word filtered) ──────────────
    # PEER cohort tickers in the catalyst = strong theme-as-driver evidence. Tagged 'ticker:'.
    text_tickers = {
        t for t in _TICKER_RE.findall(grounded_text)
        if t not in _PREPOSITION_SKIP
    }
    subject = (subject_ticker or "").upper()
    cohort = {(t or "").upper() for t in (cohort_tickers or [])}
    cohort.discard(subject)  # exclude the subject ticker — see docstring
    matched.extend(f"ticker:{t}" for t in sorted(text_tickers & cohort))

    # ── Keyword pass (lowercased, 4+ letter, theme name + description) ─────────────────
    # Theme vocabulary in the catalyst = weaker (own-vocabulary trivial); tagged 'kw:'.
    theme_text = f"{theme_name or ''} {theme_description or ''}".lower()
    theme_words = set(_KEYWORD_RE.findall(theme_text))
    if theme_words:
        text_words = set(_KEYWORD_RE.findall(grounded_text.lower()))
        matched.extend(f"kw:{w}" for w in sorted(theme_words & text_words))

    score = len(matched)
    return score, (score > 0), matched


def _normalize_company_name(name: str | None) -> str | None:
    """Normalize a company name into the literal phrase STEP-1(a) searches for in
    grounded_text, or None when the name has no USABLE remainder. See the module-level
    comment above `_CORPORATE_SUFFIX_TOKENS` for the full documented rule; short version:
    lowercase -> strip punctuation -> drop a leading "the" -> strip trailing corporate-suffix
    tokens -> require >=2 tokens left, or exactly 1 token that's long + non-generic.
    """
    if not name:
        return None
    cleaned = _PUNCT_RE.sub("", name.lower())
    tokens = cleaned.split()
    if tokens and tokens[0] in _LEADING_ARTICLE_TOKENS:
        tokens = tokens[1:]
    while tokens and tokens[-1] in _CORPORATE_SUFFIX_TOKENS:
        tokens.pop()
    if not tokens:
        return None
    if len(tokens) == 1:
        tok = tokens[0]
        if len(tok) < _MIN_SINGLE_TOKEN_LEN or tok in _AMBIGUOUS_SINGLE_TOKENS:
            return None
    return " ".join(tokens)


def compute_name_attribution(
    grounded_text: str | None,
    subject_ticker: str,
    cohort_tickers: list[str] | None,
    names_by_ticker: dict[str, str] | None,
) -> tuple[int, bool, list[str]]:
    """STEP-1 (a) (#367 / #369 fix): count distinct COHORT COMPANIES (subject excluded, same
    rationale as compute_structural_attribution) whose NORMALIZED NAME appears as a
    word-bounded phrase in the catalyst grounded_text. Returns (score, attributable, matched)
    with matched entries tagged 'name:TICKER:normalized phrase' for auditability — the sibling
    signal to compute_structural_attribution, but matching names instead of tickers because
    grounded_text is the raw 8-K (names peers by company name, not ticker).

    Unresolvable names (no cached/fetched company name, or a name too ambiguous to normalize —
    see _normalize_company_name) are simply skipped, not counted as a non-match against a
    different signal; the caller (log_theme_axis_shadow) still logs 0/False for those days —
    a NULL company-name cache is functionally identical to "no match" for this shadow read.
    """
    if not grounded_text or not names_by_ticker:
        return 0, False, []
    subject = (subject_ticker or "").upper()
    cohort = {(t or "").upper() for t in (cohort_tickers or [])}
    cohort.discard(subject)  # exclude the subject ticker — see docstring

    text_norm = _PUNCT_RE.sub("", grounded_text.lower())
    matched: list[str] = []
    for t in sorted(cohort):
        norm = _normalize_company_name(names_by_ticker.get(t))
        if not norm:
            continue
        if re.search(r"\b" + re.escape(norm) + r"\b", text_norm):
            matched.append(f"name:{t}:{norm}")

    score = len(matched)
    return score, (score > 0), matched


# ─── STEP-1 (b): co-movement (#367, the CO-EQUAL candidate) ───────────────────────────────
# Starting value, NOT tuned (a health-gauge signal, not a flip-gate) — the cohort's own median
# move must clear this floor for "same-sign" to mean anything; a cohort that barely moved
# makes same-sign agreement uninformative either way.
CO_MOVEMENT_FLOOR_PCT = 1.0


def compute_co_movement(
    ticker_move: float | None, cohort_moves: list[float],
) -> tuple[float | None, bool | None]:
    """cohort_move = median of the OTHER cohort members' same-day pct move (subject already
    excluded by the caller). co_moving = ticker_move and cohort_move share a sign AND
    |cohort_move| clears CO_MOVEMENT_FLOOR_PCT.

    Returns (cohort_move, co_moving). Either half can be None when not computable — no cohort
    price data (cohort_move None) or no subject price data (co_moving None even though
    cohort_move might be known). None is deliberately distinct from a computed False: a health
    read must not conflate "we don't know" with "measured, not co-moving."
    """
    if not cohort_moves:
        return None, None
    cohort_move = statistics.median(cohort_moves)
    if ticker_move is None:
        return cohort_move, None
    if abs(cohort_move) < CO_MOVEMENT_FLOOR_PCT:
        return cohort_move, False
    same_sign = (ticker_move > 0 and cohort_move > 0) or (ticker_move < 0 and cohort_move < 0)
    return cohort_move, same_sign


async def _ensure_company_names(conn: Any, tickers: list[str]) -> dict[str, str]:
    """Cache-first company-name resolver for STEP-1 (a). Reads the mi_ticker_overrides cache
    for `tickers`; any still missing are fetched via yfinance (collector.get_fmp_profile — the
    SAME source theme_engine._ensure_descriptions already uses to build its Haiku prompt) and
    persisted so later callers hit the cache instead of re-fetching. Best-effort: a fetch
    failure (get_fmp_profile already swallows its own errors, returning {}) just leaves that
    ticker absent from the result — compute_name_attribution treats an absent name as unusable,
    not as a non-match against a different signal.
    """
    if not tickers:
        return {}
    upper = sorted({(t or "").upper() for t in tickers if t})
    if not upper:
        return {}
    cached = await get_company_names_batch(conn, upper)
    missing = [t for t in upper if t not in cached]
    if not missing:
        return cached

    sem = asyncio.Semaphore(5)
    fetched: dict[str, str] = {}

    async def _fetch(t: str) -> None:
        async with sem:
            profile = await get_fmp_profile(t)
            name = profile.get("companyName")
            if name and name != t:
                fetched[t] = name

    await asyncio.gather(*[_fetch(t) for t in missing])
    if fetched:
        await upsert_company_names_batch(conn, fetched)
    return {**cached, **fetched}


async def log_theme_axis_shadow(conn: Any, r: dict) -> None:
    """SHADOW writer (#329 STEP-0 + #367 STEP-1). For one scored EP candidate, log the as-of
    theme heat + BOTH relevance signals to mi_theme_axis_shadow:
      - STEP-0 structural attribution (ticker/keyword — kept for continuity/comparison)
      - STEP-1 (a) company-name attribution (the #369 fix)
      - STEP-1 (b) co-movement (the co-equal candidate)
    Upserts latest-scan-wins (the EP scan re-runs every 5 min). NEVER raises — every error is
    swallowed to an audit event so a telemetry failure can't disturb the grade path.

    Caller gates on "scored EP HIGH" (final, post-override score_tier == 'HIGH'); this function
    logs whatever grade it is handed.
    """
    try:
        ticker = r.get("ticker")
        alert_date = r.get("alert_date")
        if not ticker or not alert_date:
            return
        grade = r.get("score_tier")
        grounded_text = r.get("grounded_text")

        heat = await get_theme_heat_asof(conn, ticker, alert_date)
        themeless = heat is None
        if themeless:
            theme_name = theme_stage = theme_score = None
            score, attributable, matched = 0, False, []
            name_score, name_attributable, matched_names = 0, False, []
            cohort_move = ticker_move = co_moving = None
        else:
            theme_name = heat["name"]
            theme_stage = heat["stage"]
            theme_score = heat["score"]
            score, attributable, matched = compute_structural_attribution(
                grounded_text,
                subject_ticker=ticker,
                cohort_tickers=heat["tickers"],
                theme_name=theme_name,
                theme_description=heat["description"],
            )

            # ── STEP-1 (a): company-name attribution ────────────────────────────────
            names_by_ticker = await _ensure_company_names(conn, heat["tickers"])
            name_score, name_attributable, matched_names = compute_name_attribution(
                grounded_text,
                subject_ticker=ticker,
                cohort_tickers=heat["tickers"],
                names_by_ticker=names_by_ticker,
            )

            # ── STEP-1 (b): co-movement ──────────────────────────────────────────────
            cohort_tickers = [
                t for t in heat["tickers"] if (t or "").upper() != ticker.upper()
            ]
            moves = await get_daily_moves(conn, alert_date, [ticker] + cohort_tickers)
            ticker_move = moves.get(ticker.upper())
            cohort_moves = [moves[t.upper()] for t in cohort_tickers if t.upper() in moves]
            cohort_move, co_moving = compute_co_movement(ticker_move, cohort_moves)

        await conn.execute("""
            INSERT INTO mi_theme_axis_shadow (
                ticker, alert_date, grade, theme_name, theme_stage, theme_score,
                themeless_flag, structural_attribution_score, structural_attributable,
                matched_terms, name_attribution_score, name_attributable, matched_names,
                cohort_move, ticker_move, co_moving
            ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16)
            ON CONFLICT (ticker, alert_date) DO UPDATE SET
                grade = EXCLUDED.grade,
                theme_name = EXCLUDED.theme_name,
                theme_stage = EXCLUDED.theme_stage,
                theme_score = EXCLUDED.theme_score,
                themeless_flag = EXCLUDED.themeless_flag,
                structural_attribution_score = EXCLUDED.structural_attribution_score,
                structural_attributable = EXCLUDED.structural_attributable,
                matched_terms = EXCLUDED.matched_terms,
                name_attribution_score = EXCLUDED.name_attribution_score,
                name_attributable = EXCLUDED.name_attributable,
                matched_names = EXCLUDED.matched_names,
                cohort_move = EXCLUDED.cohort_move,
                ticker_move = EXCLUDED.ticker_move,
                co_moving = EXCLUDED.co_moving,
                created_at = NOW()
        """, ticker, alert_date, grade, theme_name, theme_stage, theme_score,
             themeless, score, attributable, matched,
             name_score, name_attributable, matched_names,
             cohort_move, ticker_move, co_moving)
    except Exception as _e:  # SHADOW: never disturb the grade path
        logger.warning(f"theme-axis shadow log failed for {r.get('ticker')}: {_e}")
        try:
            await log_audit_event(
                "theme_axis_shadow_failed",
                f"{r.get('ticker')} {r.get('alert_date')}: {type(_e).__name__}: {_e}",
            )
        except Exception:
            pass
