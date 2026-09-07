"""Theme-axis SHADOW measurement scaffold — meta-rubric STEP-0 (#329) + STEP-1 (#367).

PURPOSE (SHADOW ONLY — drives NOTHING). For each scored EP HIGH or MODERATE (S1
coverage-loop widen 2026-07-13, completing ADR 0015's signed sub-HIGH accrual intent;
HIGH-only before), record alongside the live judge grade the signals the live judge is
structurally blind to today:

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

This module owns ONLY the pure attribution logic + the shadow-table writer, plus two
STEP-0-completion pieces (2026-07-26 unblock): the EOD co-movement refresh (the intraday
writer runs before today's mi_daily_closes exist, so signal (4) was structurally NULL on
every live row — see refresh_co_movement_for_date) and the deterministic enrolment rule
for the themeless-winner-INCLUSIVE label cohort (classify_label_stratum, seeded by
scripts/seed_theme_relevance_cohort.py into mi_theme_relevance_cohort for #368 labeling).
It reads `r` (read-only) and writes ONLY `mi_theme_axis_shadow` (+ the mi_ticker_overrides
company-name CACHE, an additive persistent lookup, never mutated in a way that could affect
grading). It never mutates trade state, never touches the live grade/judge output, and never
raises into the caller (the writer swallows every error to an audit event — pure telemetry
throughout).

Both (2) and (3)/(4) are logged side by side — NEITHER is a flip-gate (#329 6/24: the
disagreement rate is a HEALTH GAUGE ONLY). The #368 STEP-2 weighting decision is the
operator's call, gated on a labeled cohort, not on this module.
"""
from __future__ import annotations

import asyncio
import logging
import re
import statistics
from datetime import timedelta
from typing import Any

from agents.market_intelligence.collector import get_fmp_profile
from agents.market_intelligence.db import (
    get_company_names_batch,
    get_daily_moves,
    get_theme_axis_shadow_bounded_backfill_targets,
    get_theme_heat_asof,
    get_unscored_theme_axis_population,
    log_audit_event,
    upsert_company_names_batch,
    write_theme_axis_shadow_bounded_backfill,
    write_unscored_theme_axis_row,
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
# NB (d2-review G2, resolved as CROSS-REFERENCE not shared-base): collector.py's
# _GENERIC_NAME_TOKENS covers the same corporate-token CONCEPT but serves a
# DIFFERENT rule (generic-word filtering in is_primary_subject_news — a LIVE
# protective-path filter) with deliberately different membership; unioning them
# would silently change that filter's behavior. If you add a corporate token
# HERE, check whether collector.py:596 needs it too — and vice versa.
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


_MARKET_ADJUST_TICKER = "SPY"


async def _cohort_co_movement(conn: Any, ticker: str, alert_date: Any,
                              cohort_tickers: "list[str]", spy_adjust: bool = False) -> tuple:
    """The ONE moves-fetch + co-movement derivation (subject excluded from the cohort
    side) — shared by compute_step1_signals (scan-time) and refresh_co_movement_for_date
    (EOD), same divergence rationale as compute_step1_signals' G1 note. Returns
    (ticker_move, cohort_move, co_moving).

    `spy_adjust` (theme-correctness programme Step 4, 2026-09-07): opt-in, default
    UNCHANGED (False) — every existing caller (the live shadow writer via
    compute_step1_signals, refresh_co_movement_for_date, the #367/#369 backfill
    scripts) keeps today's RAW-move behavior byte-identical. The EOD-unscored writer
    (log_unscored_theme_axis_for_date) passes True: the plan's own finding is that the
    current co_moving is NOT market-adjusted, which reads trivially True on a broad
    up day — coverage_probe's birth-gate copy already subtracts SPY's same-day
    open->close move from every leg (fork F-D, coverage_probe.market_adjust_moves)
    before the co-movement floor is applied; this matches that, rather than inventing
    a second adjustment rule. Lazy import (coverage_probe imports THIS module at
    module level — a top-level import here would be circular)."""
    peers = [t for t in cohort_tickers if (t or "").upper() != ticker.upper()]
    fetch_tickers = [ticker] + peers
    if spy_adjust:
        fetch_tickers = fetch_tickers + [_MARKET_ADJUST_TICKER]
    moves = await get_daily_moves(conn, alert_date, fetch_tickers)
    if spy_adjust:
        from agents.market_intelligence.coverage_probe import market_adjust_moves
        moves = market_adjust_moves(moves, moves.get(_MARKET_ADJUST_TICKER))
    ticker_move = moves.get(ticker.upper())
    cohort_moves = [moves[t.upper()] for t in peers if t.upper() in moves]
    cohort_move, co_moving = compute_co_movement(ticker_move, cohort_moves)
    return ticker_move, cohort_move, co_moving


async def compute_step1_signals(conn, ticker: str, alert_date, grounded_text,
                                cohort_tickers: "list[str]") -> dict:
    """The ONE #367 STEP-1 pipeline (d2-review G1): name-attribution (a) +
    co-movement (b) for a subject vs its theme cohort. Shared by the live
    shadow writer AND the backfill script so a normalization/floor tweak can
    never diverge them (that divergence would corrupt the health-read
    comparison the signals exist for)."""
    names_by_ticker = await _ensure_company_names(conn, cohort_tickers)
    name_score, name_attributable, matched_names = compute_name_attribution(
        grounded_text, subject_ticker=ticker,
        cohort_tickers=cohort_tickers, names_by_ticker=names_by_ticker,
    )
    ticker_move, cohort_move, co_moving = await _cohort_co_movement(
        conn, ticker, alert_date, cohort_tickers)
    return {
        "name_score": name_score, "name_attributable": name_attributable,
        "matched_names": matched_names, "ticker_move": ticker_move,
        "cohort_move": cohort_move, "co_moving": co_moving,
    }


def compute_bounded_theme_match(
    theme_name_7d: "str | None", unbounded_theme_name: "str | None",
) -> bool:
    """The #486 comparison: do the two as-of reads agree on an ANSWER, not on freshness?
    True when both found the same theme name, or both found none (a themeless row is
    AGREEMENT, not a mismatch — the cross-validation filters on this column, so conflating
    "neither found a theme" with "they differ" would inflate the mismatch set).

    Extracted to a shared helper (2026-09-07, #486 backfill) so the live writer
    (log_theme_axis_shadow) and the backfill (theme_axis_shadow.compute_bounded_backfill_read)
    can never diverge on what "matches" means — same discipline as compute_step1_signals' G1
    note for a different pair of signals."""
    return theme_name_7d == unbounded_theme_name


async def log_theme_axis_shadow(conn: Any, r: dict) -> None:
    """SHADOW writer (#329 STEP-0 + #367 STEP-1). For one scored EP candidate, log the as-of
    theme heat + BOTH relevance signals to mi_theme_axis_shadow:
      - STEP-0 structural attribution (ticker/keyword — kept for continuity/comparison)
      - STEP-1 (a) company-name attribution (the #369 fix)
      - STEP-1 (b) co-movement (the co-equal candidate)
    Upserts latest-scan-wins (the EP scan re-runs every 5 min). NEVER raises — every error is
    swallowed to an audit event so a telemetry failure can't disturb the grade path.

    Caller gates on the final, post-override score_tier in ('HIGH', 'MODERATE') — S1
    coverage-loop widen 2026-07-13 (HIGH-only before); this function is tier-agnostic and
    logs whatever grade it is handed. It never mutates `r` or any grade column.
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

        # #486 (2026-08-29) — RECORD BOTH READS, because they are different questions.
        # `heat` above is UNBOUNDED: get_theme_heat_asof's default has no recency floor, so it
        # walks back to the newest non-Retired snapshot containing the ticker however old that
        # is. The LIVE credit path (`in_active_theme`) is 7d-bounded. Measured 2026-08-29: 35 of
        # 107 shadow theme attributions were staler than the live path accepts, 15 of them over
        # 30 days old (avg 64) — which made a judge-vs-engine cross-validation compare two
        # definitions of "themed", and led me to mis-read five rows as a flag defect when the
        # live flag had been right every time. Capturing the bounded read alongside makes the
        # comparison like-for-like without changing what the unbounded columns have always meant.
        # Own try/except: this is a diagnostic on a diagnostic — it must never cost the caller
        # its existing row, so any failure degrades to NULL (= "not captured"), never to FALSE.
        theme_name_7d = theme_stage_7d = bounded_matches_unbounded = None
        try:
            heat_7d = await get_theme_heat_asof(conn, ticker, alert_date, recency_days=7)
            theme_name_7d = heat_7d["name"] if heat_7d else None
            theme_stage_7d = heat_7d["stage"] if heat_7d else None
            bounded_matches_unbounded = compute_bounded_theme_match(
                theme_name_7d, heat["name"] if heat else None)
        except Exception as _be:
            logger.debug(f"theme-axis shadow: bounded read failed for {ticker} — {_be}")
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

            # ── STEP-1 (a)+(b) via the ONE shared pipeline (G1) ─────────────────────
            _s1 = await compute_step1_signals(conn, ticker, alert_date,
                                              grounded_text, heat["tickers"])
            name_score, name_attributable, matched_names = (
                _s1["name_score"], _s1["name_attributable"], _s1["matched_names"])
            ticker_move, cohort_move, co_moving = (
                _s1["ticker_move"], _s1["cohort_move"], _s1["co_moving"])

        await conn.execute("""
            INSERT INTO mi_theme_axis_shadow (
                ticker, alert_date, grade, theme_name, theme_stage, theme_score,
                themeless_flag, structural_attribution_score, structural_attributable,
                matched_terms, name_attribution_score, name_attributable, matched_names,
                cohort_move, ticker_move, co_moving,
                theme_name_7d, theme_stage_7d, bounded_matches_unbounded
            ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18,$19)
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
                theme_name_7d = EXCLUDED.theme_name_7d,
                theme_stage_7d = EXCLUDED.theme_stage_7d,
                bounded_matches_unbounded = EXCLUDED.bounded_matches_unbounded,
                created_at = NOW()
        """, ticker, alert_date, grade, theme_name, theme_stage, theme_score,
             themeless, score, attributable, matched,
             name_score, name_attributable, matched_names,
             cohort_move, ticker_move, co_moving,
             theme_name_7d, theme_stage_7d, bounded_matches_unbounded)
    except Exception as _e:  # SHADOW: never disturb the grade path
        logger.warning(f"theme-axis shadow log failed for {r.get('ticker')}: {_e}")
        try:
            await log_audit_event(
                "theme_axis_shadow_failed",
                f"{r.get('ticker')} {r.get('alert_date')}: {type(_e).__name__}: {_e}",
            )
        except Exception:
            pass


# ─── STEP-1 (b) EOD refresh (#329 STEP-0 completion, 2026-07-26) ──────────────────────────
# THE INSTRUMENTATION ARTIFACT: the live writer runs inside the 7:00–10:00 AM EP scan, but
# mi_daily_closes rows for TODAY are only ingested by the 17:00 nightly pull — so
# get_daily_moves(alert_date=today) is ALWAYS empty at scan time and every live-path row logs
# co_moving=NULL, permanently. The #367 health read's "~90% not computable" was substantially
# THIS (a dark instrument, not an absent signal — memory [[shadow-zero-effect-check-
# instrumentation]]); without the refresh, the INDEPENDENT co-movement check the 6/24 decision
# requires beside the structural attributor never accrues on the live path at all.

async def refresh_co_movement_for_date(conn: Any, trade_date: Any) -> dict:
    """EOD recompute of the co-movement columns (cohort_move / ticker_move / co_moving) for
    `trade_date`'s THEMED mi_theme_axis_shadow rows, once today's closes exist. Returns
    {"refreshed": n, "skipped": m} (skipped = rows whose theme cohort can't be re-derived).
    Idempotent — recomputes unconditionally from the same inputs, so a re-run converges.

    AS-OF DISCIPLINE (lookahead + circularity): the cohort is re-derived via
    get_theme_heat_asof at `trade_date - 1 day` — STRICTLY-PRIOR theme state. This exactly
    reproduces what the scan-time writer saw (at 9:35 AM its `theme_date <= alert_date`
    read could not include today's snapshot — the nightly theme run hadn't written it yet),
    and it keeps a theme BORN FROM today's very move (tonight's run may have landed by the
    time this job fires) from grading its own co-movement — that born-today cohort would be
    trivially co-moving and would corrupt the check's independence. NEVER raises — swallows
    to an audit event (SHADOW contract, same as log_theme_axis_shadow). Writes ONLY the
    three co-movement columns of mi_theme_axis_shadow."""
    try:
        rows = await conn.fetch("""
            SELECT ticker, alert_date FROM mi_theme_axis_shadow
            WHERE alert_date = $1 AND themeless_flag = FALSE
        """, trade_date)
        refreshed = skipped = 0
        for row in rows:
            ticker, alert_date = row["ticker"], row["alert_date"]
            heat = await get_theme_heat_asof(
                conn, ticker, alert_date - timedelta(days=1))  # strictly-prior — see docstring
            if heat is None:
                skipped += 1  # cohort not re-derivable (e.g. theme first snapshotted today)
                continue
            ticker_move, cohort_move, co_moving = await _cohort_co_movement(
                conn, ticker, alert_date, heat["tickers"])
            await conn.execute("""
                UPDATE mi_theme_axis_shadow
                SET cohort_move = $3, ticker_move = $4, co_moving = $5
                WHERE ticker = $1 AND alert_date = $2
            """, ticker, alert_date, cohort_move, ticker_move, co_moving)
            refreshed += 1
        if rows:
            await log_audit_event(
                "theme_axis_co_move_refreshed",
                f"{trade_date}: {refreshed} themed row(s) recomputed, {skipped} skipped "
                f"(cohort not re-derivable strictly-prior)",
            )
        return {"refreshed": refreshed, "skipped": skipped}
    except Exception as _e:  # SHADOW: telemetry failure must never propagate
        logger.warning(f"theme-axis co-movement refresh failed for {trade_date}: {_e}")
        try:
            await log_audit_event(
                "theme_axis_co_move_refresh_failed",
                f"{trade_date}: {type(_e).__name__}: {_e}",
            )
        except Exception:  # loud-ok: fallback-of-the-fallback — the audit sink itself failed; logger.warning above already surfaced the primary failure
            pass
        return {"refreshed": 0, "skipped": 0}


# ─── #486 bounded-read backfill (2026-09-07 unblock) ───────────────────────────────────────
# theme_name_7d/theme_stage_7d/bounded_matches_unbounded were instrumented 2026-09-03 and
# capture forward only, so 588 of 592 rows sat NULL and #486 (the judge <-> theme-engine
# cross-validation) was dated to wait for rows to accrue. It does not have to wait: the
# column is a pure recomputation from data already stored on every row.
#
# FAITHFULNESS (verified 2026-09-07, not taken on faith):
#   1. `mi_themes` is dated append-only history for any date once its day has passed. Every
#      INSERT/UPDATE call site (theme_engine._save_themes, db.seed_theme, db.
#      assign_ticker_to_theme, plus the one-off scripts/probes/_reconcile_2026_05_14_bugs.py)
#      resolves its target theme_date to et_today() (or an explicit CURRENT_DATE) at CALL
#      time — grepped every UPDATE/INSERT `mi_themes` site in db.py/theme_engine.py, and
#      /assigntheme (agent.py:1750) never threads a historical scan_date through to
#      assign_ticker_to_theme. So a PAST theme_date row cannot be mutated after its day ends.
#   2. BUT append-only history is not sufficient on its own — a row can still be APPENDED
#      between when the live writer read `mi_themes` and today. mi_themes.created_at for
#      theme_date=D rows clusters at ~17:07-18:23 ET on day D (theme engine runs inside
#      _nightly_data_pull, CronTrigger hour=17 in scheduler.py), while log_theme_axis_shadow
#      only ever runs inside the 7:00-10:05 ET EP scan (its one call site, ep_detector.py).
#      So AT THE MOMENT a live row was written, theme_date=alert_date's OWN row did not exist
#      yet — the live 7d-bounded read was effectively bounded to [alert_date-7, alert_date-1],
#      not [alert_date-7, alert_date], no matter what the code passed as the upper bound.
#      Naively re-querying get_theme_heat_asof(ticker, alert_date, recency_days=7) TODAY sees
#      the now-existing alert_date row and can return a DIFFERENT theme than the live write
#      saw — proven, not hypothetical: of all 592 rows, the same-day-inclusive and prior-day
#      forms disagree on 31; and on the one live-captured row where they disagree (ALAB,
#      2026-09-04), the STORED theme_name_7d ("Optical Networking & Photonics...") matches
#      the prior-day form exactly and does NOT match the same-day form ("AI data-center power
#      buildout") — direct proof the prior-day form is the one that actually ran.
#   3. The wrinkle: mi_theme_axis_shadow ALSO holds 452 rows from the #369 mass backfill
#      (scripts/backfill_theme_axis_shadow.py, all created 2026-06-24 12:38 ET, for alert_dates
#      already months in the past by then) — those rows' `theme_name` WAS computed with the
#      same-day-inclusive form, because by 2026-06-24 every historical alert_date's own
#      theme_date row already existed. Anchoring EVERY row at `alert_date - 1` regardless of
#      when it was written would reproduce the live population's own `theme_name` correctly
#      but silently MISMATCH the backfilled population's `theme_name` (which was captured with
#      the other convention) — a self-inflicted, methodology-only mismatch, not a genuine
#      bounded-vs-unbounded engine disagreement. `same_day_write` (created_at's ET date ==
#      alert_date, computed in get_theme_axis_shadow_bounded_backfill_targets) distinguishes
#      the two populations: verified against ALL 592 rows' stored `theme_name`, the
#      conditional anchor reproduces 591/592 (99.8%); the lone residual (HUT, 2026-07-20) is a
#      same-score tie between two near-duplicate theme names on 2026-07-17
#      ("Bitcoin & Crypto Mining Infrastructure" / "Bitcoin Mining & Crypto Infrastructure
#      Operators") that get_theme_heat_asof's ORDER BY ... score DESC NULLS LAST does not
#      break deterministically — a pre-existing property of the shared accessor, not
#      introduced by this backfill, and equally present in the original live read.
#
# CONCLUSION: mi_themes' append-only-per-day property makes the backfill possible, but by
# itself is NOT sufficient for faithfulness (per the brief's own warning) — the anchor date
# must also account for same-day data latency at the ORIGINAL write time. Fixed here, not
# left for the live writer: log_theme_axis_shadow itself needs no change — at true scan
# time, alert_date's own row genuinely does not exist yet, so its calls are already
# correct by construction. Only a backfill running long after the fact needs the explicit
# adjustment.

def bounded_backfill_anchor(alert_date, same_day_write: bool):
    """The ONE place the #486 backfill's as-of anchor is decided — pure, no DB access, so
    it's cheaply unit-testable in isolation from compute_bounded_backfill_read below.
    Returns (anchor_date, recency_days) to pass to get_theme_heat_asof.

    See the module comment above for why `same_day_write` picks the anchor: a row written
    the same ET calendar day as its own alert_date (a genuine live scan write) can only have
    seen theme snapshots through alert_date-1 (mi_themes' theme_date=alert_date row is not
    written until the evening); a row written on a LATER calendar day (the #369 mass
    backfill) could see alert_date's own snapshot, matching how its stored `theme_name` was
    itself computed."""
    if same_day_write:
        return alert_date - timedelta(days=1), 6
    return alert_date, 7


async def compute_bounded_backfill_read(
    conn: Any, ticker: str, alert_date, same_day_write: bool, stored_theme_name: "str | None",
):
    """Compute (WITHOUT writing) the #486 bounded read for one historical row: the ONE
    get_theme_heat_asof call and the ONE compute_bounded_theme_match call, anchored per
    bounded_backfill_anchor. Split out from backfill_bounded_theme_reads (advisor review,
    2026-09-07) so a prod fidelity check can call this directly, read-only, against the 4
    rows already captured live — the exact same code path the backfill writes from, minus
    the write. Returns (theme_name_7d, theme_stage_7d, bounded_matches_unbounded)."""
    anchor_date, recency = bounded_backfill_anchor(alert_date, same_day_write)
    heat_7d = await get_theme_heat_asof(conn, ticker, anchor_date, recency_days=recency)
    theme_name_7d = heat_7d["name"] if heat_7d else None
    theme_stage_7d = heat_7d["stage"] if heat_7d else None
    matches = compute_bounded_theme_match(theme_name_7d, stored_theme_name)
    return theme_name_7d, theme_stage_7d, matches


async def backfill_bounded_theme_reads(conn: Any) -> dict:
    """One-time, idempotent backfill of theme_name_7d/theme_stage_7d/bounded_matches_unbounded
    for every mi_theme_axis_shadow row where bounded_matches_unbounded IS NULL. Reuses
    get_theme_heat_asof and compute_bounded_theme_match via compute_bounded_backfill_read —
    the SAME accessor and comparison the live writer uses — so a backfilled value can never
    drift from a live one for identical inputs; see bounded_backfill_anchor for the one
    deliberate difference (the as-of anchor, required for faithfulness — module comment above).

    NEVER touches the 4 rows already captured live, or any row a prior run already backfilled
    — both the SELECT (get_theme_axis_shadow_bounded_backfill_targets) and the UPDATE
    (write_theme_axis_shadow_bounded_backfill) filter on `bounded_matches_unbounded IS NULL`.
    A second run finds zero candidates: fully idempotent.

    Unlike the live writer, this does NOT swallow exceptions — it is an operator-run, offline
    migration over historical rows (not a hot path that must protect a grade), so a failure
    should stop the run and be investigated, not silently degrade a row to NULL.

    Returns {"candidates": n, "backfilled": n, "themed": n, "themeless": n} — themed/themeless
    split on the STORED unbounded theme_name (the #486 report's cohort split — 481 themeless
    always trivially agree and must not be pooled into the headline number), not on the fresh
    bounded read.
    """
    targets = await get_theme_axis_shadow_bounded_backfill_targets(conn)
    themed = themeless = backfilled = 0
    for row in targets:
        theme_name_7d, theme_stage_7d, matches = await compute_bounded_backfill_read(
            conn, row["ticker"], row["alert_date"], row["same_day_write"], row["theme_name"])
        n = await write_theme_axis_shadow_bounded_backfill(
            conn, row["id"], theme_name_7d, theme_stage_7d, matches)
        backfilled += n
        if row["theme_name"] is not None:
            themed += 1
        else:
            themeless += 1
    return {
        "candidates": len(targets), "backfilled": backfilled,
        "themed": themed, "themeless": themeless,
    }


# ─── Theme-correctness programme Step 4 (THE INSTRUMENT, 2026-09-07) ──────────────────────
# `mi_theme_axis_shadow` today records only names that SCORED ABOVE the EP bar
# (log_theme_axis_shadow, source='live_scan'). Everything filtered earlier is invisible, so
# there is no comparison group — and the reflexivity step (step 2 of the programme) needs
# exactly that group as its NULL CONTROL: without it, a themeless-alert rate can't be
# falsified against anything. Two groups were missing: (1) scored-under-bar
# (reject_stage='score_bar') and (2) — the group prior scoping missed — candidates killed
# BEFORE scoring ever ran (shortlist_cap/rvol_gate/cooldown/extension/quality_filter/
# post_grade_filter — ep_decision_vector.py:91-126), where modest-gap early theme members
# live. This EOD job (NOT in the scan loop — run once, after market close) is the write
# side; db.get_unscored_theme_axis_population is the read side.
#
# NEVER touches a grade/alert/entry/exit/size column or table (THE LINE) — writes ONLY
# mi_theme_axis_shadow (+ mi_audit_log), same SHADOW contract as log_theme_axis_shadow.

async def compute_unscored_theme_axis_row(conn: Any, ticker: str, trade_date: Any) -> dict:
    """Compute (WITHOUT writing) one EOD-unscored row's theme + co-movement fields. Split
    out from log_unscored_theme_axis_for_date (mirrors compute_bounded_backfill_read's split
    from backfill_bounded_theme_reads, same reason) so a read-only dry-run/sample check can
    call this directly — the EXACT same code path the EOD job and the historical backfill
    runner both write from, minus the write.

    Both theme reads (unbounded theme_name/theme_stage/theme_score AND the 7d-bounded
    theme_name_7d/theme_stage_7d/bounded_matches_unbounded) are anchored via
    `bounded_backfill_anchor(trade_date, same_day_write=True)` — NOT the live shadow
    writer's own anchor (bare `alert_date`). log_theme_axis_shadow runs at 7:00-10:05 AM ET,
    before that day's own mi_themes row is written (~17:07-18:23 ET), so passing alert_date
    verbatim is safe there — the row genuinely doesn't exist yet. This function is called
    from a job that runs at 18:03 ET, AFTER the 17:07 theme save has already landed
    `trade_date`'s OWN theme_date row, so it MUST be excluded or every candidate would
    trivially match a theme born from today's own move — exactly the same_day_write=True
    reasoning bounded_backfill_anchor exists for (#486, proven faithful on 591/592 rows);
    reused here rather than re-derived. The historical backfill runner calls this with the
    SAME same_day_write=True for every past date too — see its module docstring for why
    that is the faithful choice even with no live capture to diff against.

    Co-movement is computed inline via `_cohort_co_movement(..., spy_adjust=True)` against
    the BOUNDED (7d) cohort — matching coverage_probe's birth-gate copy (market-adjusted),
    not the live shadow writer's un-adjusted one (the current co_moving reads trivially True
    on a broad up day without the SPY subtraction; see _cohort_co_movement's docstring).

    Returns a dict with the exact fields write_unscored_theme_axis_row needs beyond
    (ticker, alert_date, reject_stage, ep_score): theme_name, theme_stage, theme_score,
    themeless_flag, theme_name_7d, theme_stage_7d, bounded_matches_unbounded, cohort_move,
    ticker_move, co_moving."""
    anchor_date, recency = bounded_backfill_anchor(trade_date, same_day_write=True)
    heat = await get_theme_heat_asof(conn, ticker, anchor_date)
    heat_7d = await get_theme_heat_asof(conn, ticker, anchor_date, recency_days=recency)
    theme_name = heat["name"] if heat else None
    theme_stage = heat["stage"] if heat else None
    theme_score = heat["score"] if heat else None
    theme_name_7d = heat_7d["name"] if heat_7d else None
    theme_stage_7d = heat_7d["stage"] if heat_7d else None
    bounded_matches_unbounded = compute_bounded_theme_match(theme_name_7d, theme_name)
    themeless_flag = heat is None

    cohort_move = ticker_move = co_moving = None
    if heat_7d is not None:
        ticker_move, cohort_move, co_moving = await _cohort_co_movement(
            conn, ticker, trade_date, heat_7d["tickers"], spy_adjust=True)

    return {
        "theme_name": theme_name, "theme_stage": theme_stage, "theme_score": theme_score,
        "themeless_flag": themeless_flag,
        "theme_name_7d": theme_name_7d, "theme_stage_7d": theme_stage_7d,
        "bounded_matches_unbounded": bounded_matches_unbounded,
        "cohort_move": cohort_move, "ticker_move": ticker_move, "co_moving": co_moving,
    }


async def _write_unscored_candidates(conn: Any, candidates: "list[dict]") -> dict:
    """Shared per-row compute+write+counters+error-handling loop for the step-4
    EOD-unscored population. Each candidate dict needs "ticker", "scan_date" (the
    per-candidate trade_date — the live daily job's candidates all share one date; the
    historical backfill runner's span many), "reject_stage", "ep_score". Used by BOTH
    log_unscored_theme_axis_for_date (candidates sourced from reject_stage alone, the
    live daily case) AND the historical backfill runner (candidates sourced from
    reject_stage OR the legacy filter_reason classifier) — ONE write path, never two,
    so a fix here can never apply to only one of them.

    NEVER raises past the caller — every per-row failure swallows to an audit event,
    same SHADOW contract as log_theme_axis_shadow. Returns
    {"written": n, "themed": n, "themeless": n}."""
    written = themed = themeless = 0
    for c in candidates:
        ticker = c["ticker"]
        trade_date = c["scan_date"]
        try:
            fields = await compute_unscored_theme_axis_row(conn, ticker, trade_date)
            if fields["themeless_flag"]:
                themeless += 1
            else:
                themed += 1

            n = await write_unscored_theme_axis_row(
                conn, ticker, trade_date,
                fields["theme_name"], fields["theme_stage"], fields["theme_score"],
                fields["themeless_flag"], fields["cohort_move"], fields["ticker_move"],
                fields["co_moving"], fields["theme_name_7d"], fields["theme_stage_7d"],
                fields["bounded_matches_unbounded"],
                c.get("reject_stage"), c.get("ep_score"),
            )
            written += n
        except Exception as _rowe:
            logger.warning(
                f"theme-axis EOD-unscored row failed for {ticker} {trade_date}: {_rowe}")
            try:
                await log_audit_event(
                    "theme_axis_eod_unscored_row_failed",
                    f"{ticker} {trade_date}: {type(_rowe).__name__}: {_rowe}",
                )
            except Exception:  # loud-ok: fallback-of-the-fallback — the audit sink itself failed; logger.warning above already surfaced the primary failure
                pass
    return {"written": written, "themed": themed, "themeless": themeless}


async def log_unscored_theme_axis_for_date(conn: Any, trade_date: Any) -> dict:
    """EOD writer for the step-4 null-control population: every mi_ep_scan_log candidate on
    `trade_date` that got PAST the gap floor but never became a live alert
    (db.UNSCORED_THEME_AXIS_REJECT_STAGES; see db.get_unscored_theme_axis_population for the
    exact population query + why a ticker whose FINAL state that day was a real alert can
    never appear here). Per-row fields come from compute_unscored_theme_axis_row via the
    shared _write_unscored_candidates loop (see that docstring for the anchor +
    co-movement rationale) — this function owns only the population fetch + its own
    failure handling.

    NEVER raises past the caller — every failure (population fetch, or anything inside
    the shared write loop) swallows to an audit event, same SHADOW contract as
    log_theme_axis_shadow. Returns {"candidates": n, "written": n, "themed": n,
    "themeless": n}."""
    try:
        candidates = await get_unscored_theme_axis_population(conn, trade_date, trade_date)
    except Exception as _pe:
        logger.warning(f"theme-axis EOD-unscored population fetch failed for {trade_date}: {_pe}")
        try:
            await log_audit_event(
                "theme_axis_eod_unscored_population_failed",
                f"{trade_date}: {type(_pe).__name__}: {_pe}",
            )
        except Exception:  # loud-ok: fallback-of-the-fallback — the audit sink itself failed; logger.warning above already surfaced the primary failure
            pass
        return {"candidates": 0, "written": 0, "themed": 0, "themeless": 0}

    out = await _write_unscored_candidates(conn, candidates)

    try:
        await log_audit_event(
            "theme_axis_eod_unscored_logged",
            f"{trade_date}: {out['written']}/{len(candidates)} written "
            f"({out['themed']} themed / {out['themeless']} themeless)",
        )
    except Exception:  # loud-ok: fallback-of-the-fallback, matches refresh_co_movement_for_date
        pass
    return {"candidates": len(candidates), **out}


# ─── Legacy filter_reason -> reject_stage classifier (2026-09-07 unblock) ──────────────────
# #605 (2026-08-29) added mi_ep_scan_log.reject_stage, but VERIFIED ON PROD (2026-09-07):
# it is populated only from 2026-08-31 on — every row from the table's start (2026-04-13)
# through 2026-08-30 carries reject_stage=NULL, even though `filter_reason` (the older
# free-text column) is populated back to day one (53,079 of 53,432 total rows). Without
# this, the historical backfill recovers only the ~2 weeks reject_stage covers on its own
# (38 ticker-days) instead of the ~2,700 sitting in filter_reason since April — the ONE
# group step 4 exists to supply, per the plan.
#
# EVERY PATTERN BELOW IS SOURCED FROM THE EXACT STRING LITERAL ep_detector.py builds
# (grepped, not guessed) — see the stage-by-stage citations:
#   universe_floor    <- "filter:universe_prev_close_too_low: ..." (broker/skip_reasons.py
#                         FILTER_UNIVERSE_PREV_CLOSE_TOO_LOW) / "filter:universe_prev_day_
#                         illiquid: ..." (FILTER_UNIVERSE_PREV_DAY_ILLIQUID) — EXCLUDED
#                         from the population (before the gap floor).
#   gap_floor         <- "filter:universe_below_gap_floor: ..." (FILTER_UNIVERSE_BELOW_
#                         GAP_FLOOR) — EXCLUDED (before the gap floor).
#   duplicate         <- "already scored earlier today" (ep_detector.py:3926, stage=
#                         "duplicate" explicit) — EXCLUDED (a real alert already covers it).
#   shortlist_cap     <- "outside top-N shortlist (...)" / "outside top-N gap cap (gap
#                         X%)" (ep_detector.py:3670/3674, stage="shortlist_cap").
#   rvol_gate         <- "filter:pm_rvol_too_low: ..." / "filter:session_rvol_too_low:
#                         ..." (ep_detector.py:3781, stage="rvol_gate" — the CURRENT
#                         RVOL@T message) PLUS three now-dead legacy wordings the CURRENT
#                         source no longer contains — found only by inspecting the actual
#                         pre-08-31 data, the message changed underneath the same check
#                         at least twice: "low rel volume X < Yx" (earliest, 2026-04-13),
#                         "low volume rel_vol X < Yx", "low volume projected X < Yx
#                         (post-open)".
#   cooldown          <- "EP cooldown — alerted within last N days" (ep_detector.py:3918,
#                         stage="cooldown").
#   extension         <- "already up N% in prior 5 days (extended)" (ep_detector.py:3934,
#                         stage="extension").
#   quality_filter    <- "quality filter: <check_filters skip_reason>" (ep_detector.py:
#                         3950, stage="quality_filter" — the sub-reason after the colon
#                         varies (adv_too_low/mcap_too_small/atr_too_high/adv_no_data) but
#                         the "quality filter: " prefix is constant).
#   post_grade_filter <- THREE reasons from _post_grade_filters, all stage=
#                         "post_grade_filter" (ep_detector.py:4122/4502): "M&A/buyout
#                         catalyst — no momentum trade" (:1785), "routine catalyst, gap
#                         X%" (:1809), "pre-mkt volume N < 25,000 shares" (:1846).
#   score_bar         <- "score N < 50 (catalyst=...)" (pre-#533 legacy form) / "score N
#                         < bar M (catalyst=...)" (post-#533 form) — ep_detector.py:
#                         5427/5430, stage="score_bar".
#
# VERIFIED ON PROD (2026-09-07): classifying every mi_ep_scan_log row since 2026-04-13
# this way leaves the UNMATCHED tail at ZERO (every filter_reason this table has ever
# held either matches a pattern below or belongs to a real alert with filter_reason
# NULL) — checked directly against the live table, not assumed. A future new free-text
# wording this map doesn't know about would show up as a non-empty
# get_legacy_classification_unmatched result, not a silently dropped row.
_LEGACY_FILTER_REASON_PATTERNS: "list[tuple[str, re.Pattern]]" = [
    ("universe_floor", re.compile(r"^filter:universe_prev_close")),
    ("universe_floor", re.compile(r"^filter:universe_prev_day_illiquid")),
    ("gap_floor", re.compile(r"^filter:universe_below_gap_floor")),
    ("duplicate", re.compile(r"^already scored earlier today")),
    ("shortlist_cap", re.compile(r"^outside top-\d+")),
    ("rvol_gate", re.compile(r"^filter:(pm|session)_rvol_too_low")),
    ("rvol_gate", re.compile(r"^low (rel volume|volume rel_vol|volume projected)")),
    ("cooldown", re.compile(r"^EP cooldown")),
    ("extension", re.compile(r"^already up \d+% in prior 5 days")),
    ("quality_filter", re.compile(r"^quality filter:")),
    ("post_grade_filter", re.compile(r"^M&A/buyout catalyst")),
    ("post_grade_filter", re.compile(r"^routine catalyst, gap")),
    ("post_grade_filter", re.compile(r"^pre-mkt volume")),
    ("score_bar", re.compile(r"^score -?\d+ < (bar \d+|\d+) \(catalyst=")),
]


def classify_legacy_filter_reason(filter_reason: "str | None") -> "str | None":
    """Map one pre-#605 free-text mi_ep_scan_log.filter_reason to the reject_stage it
    would have carried had #605's capture existed then. Returns None for a falsy
    filter_reason (a real alert — nothing to classify) OR for text that matches no known
    pattern (an UNMATCHED tail) — this function alone can't tell those two apart; the
    caller distinguishes them via whether filter_reason was truthy to begin with (see
    get_legacy_classification_unmatched)."""
    if not filter_reason:
        return None
    for stage, pattern in _LEGACY_FILTER_REASON_PATTERNS:
        if pattern.match(filter_reason):
            return stage
    return None


def effective_reject_stage(reject_stage: "str | None", filter_reason: "str | None") -> "str | None":
    """The ONE place a historical mi_ep_scan_log row's stage is decided: reject_stage
    when #605 already captured it (>= 2026-08-31), else the legacy classification of
    filter_reason. Shared by the backfill runner's population build and its
    unmatched-tail report so they can never diverge on what counts as classified."""
    return reject_stage or classify_legacy_filter_reason(filter_reason)


def get_legacy_classification_unmatched(rows: "list[dict]") -> "list[dict]":
    """Rows with a REAL filter_reason (not a passed/alerted row, not already
    reject_stage-tagged) that classify_legacy_filter_reason maps to nothing — the
    unmatched tail the historical backfill must report, not silently drop. `rows` are
    raw db.get_ep_scan_log_raw_population dicts."""
    return [
        r for r in rows
        if r.get("reject_stage") is None
        and r.get("filter_reason")
        and classify_legacy_filter_reason(r["filter_reason"]) is None
    ]


# ─── Part 3 (#329 STEP-0): themeless-winner-INCLUSIVE label-cohort enrolment rule ─────────
# Deterministic + documented because the #335 flip gate is grade-CORRECTNESS over the cohort
# this rule seeds (operator 6/24: "themeless-winner-INCLUSIVE labeled cohort, FULL STOP") —
# the selection itself must be auditable. "Winner" reuses the ESTABLISHED win bar (fwd_5d
# >= +5%: the same cut ADR 0015's STEP-0 calibration table and the #331 STEP-0 tables report
# as "win >= +5%"); "settled" = all 5 forward sessions accrued (mi_ep_scan_outcomes'
# n_sessions_5d, per its nightly recompute contract). Starting values, not tuned here.
LABEL_WINNER_FWD_5D_PCT = 5.0
LABEL_SETTLED_MIN_SESSIONS_5D = 5


def classify_label_stratum(
    themeless_flag: bool, fwd_5d_pct: "float | None", n_sessions_5d: "int | None",
) -> "str | None":
    """Enrolment stratum for one mi_theme_axis_shadow row (None = not enrolled).

    - 'themed'           — every themed row, REGARDLESS of outcome: the asymmetric boost's
                           only acting population (boost theme-as-driver, never penalize
                           themeless), so correctness needs its false-positive side labeled
                           — themed rows where the theme was NOT the driver.
    - 'themeless_winner' — themeless + SETTLED fwd_5d >= the win bar: the undiscovered-theme
                           blind-spot population ("not seeing a theme ≠ no theme exists",
                           operator 6/24 restated 7/26) — the false-NEGATIVE side.
    Themeless non-winners are deliberately NOT auto-enrolled (review-load: the operator
    feels the COUNT; a control stratum is an operator add at #368 if wanted)."""
    if not themeless_flag:
        return "themed"
    if (fwd_5d_pct is not None and n_sessions_5d is not None
            and n_sessions_5d >= LABEL_SETTLED_MIN_SESSIONS_5D
            and fwd_5d_pct >= LABEL_WINNER_FWD_5D_PCT):
        return "themeless_winner"
    return None
