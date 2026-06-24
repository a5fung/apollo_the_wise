"""Theme-axis SHADOW measurement scaffold — meta-rubric STEP-0 (#329).

PURPOSE (SHADOW ONLY — drives NOTHING). For each scored EP HIGH, record alongside the
live judge grade two signals the live judge is structurally blind to today:

  1. AS-OF theme heat — the stage/score of the hottest active theme containing the ticker
     as of the alert date (NO lookahead). NULL when the name is themeless.
  2. A DETERMINISTIC structural attribution score — how many of the theme's OTHER cohort
     tickers OR theme keywords (name + description, 4+ letter words) appear in the catalyst
     grounded_text. This is the traceable, auditable "is the theme the DRIVER of this move?"
     signal the 6/24 direction decided on — catalyst named-entities ∩ theme cohort — NOT the
     LLM catalyst axis (that + a judge audit would be the same LLM = circular).

This module owns ONLY the pure attribution logic + the shadow-table writer. It reads `r`
(read-only) and writes ONLY `mi_theme_axis_shadow`. It never mutates trade state, never
touches the live grade/judge output, and never raises into the caller (the writer swallows
every error to an audit event — STEP-0 is pure telemetry).

STEP-0b (the INDEPENDENT co-movement audit signal that sits beside this structural one —
needs the correlation machinery) is the DEFERRED fast-follow. See PLAN #329.
"""
from __future__ import annotations

import logging
import re
from typing import Any

from agents.market_intelligence.db import get_theme_heat_asof, log_audit_event

logger = logging.getLogger(__name__)

# Ticker shape: 2-5 uppercase letters, word-bounded, CASE-SENSITIVE (so "care" doesn't match
# CARE / "on" doesn't match ON). English-word false positives are filtered through the shared
# _PREPOSITION_SKIP frozenset (the set that exists for exactly this in agent.py).
_TICKER_RE = re.compile(r"\b[A-Z]{2,5}\b")
# Theme keyword tokens: 4+ letter words, lowercased — mirrors the existing theme-engine
# keyword-overlap tokenizer (theme_engine.py unknown-sector fallback). Theme name+description
# is short + domain-specific, so no extra stopword layer (faithful to the established pattern).
_KEYWORD_RE = re.compile(r"\b\w{4,}\b")


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


async def log_theme_axis_shadow(conn: Any, r: dict) -> None:
    """SHADOW writer (#329 STEP-0). For one scored EP candidate, log the as-of theme heat +
    structural attribution to mi_theme_axis_shadow. Read-only on `r`; upserts latest-scan-wins
    (the EP scan re-runs every 5 min). NEVER raises — every error is swallowed to an audit
    event so a telemetry failure can't disturb the grade path.

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

        await conn.execute("""
            INSERT INTO mi_theme_axis_shadow (
                ticker, alert_date, grade, theme_name, theme_stage, theme_score,
                themeless_flag, structural_attribution_score, structural_attributable,
                matched_terms
            ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)
            ON CONFLICT (ticker, alert_date) DO UPDATE SET
                grade = EXCLUDED.grade,
                theme_name = EXCLUDED.theme_name,
                theme_stage = EXCLUDED.theme_stage,
                theme_score = EXCLUDED.theme_score,
                themeless_flag = EXCLUDED.themeless_flag,
                structural_attribution_score = EXCLUDED.structural_attribution_score,
                structural_attributable = EXCLUDED.structural_attributable,
                matched_terms = EXCLUDED.matched_terms,
                created_at = NOW()
        """, ticker, alert_date, grade, theme_name, theme_stage, theme_score,
             themeless, score, attributable, matched)
    except Exception as _e:  # SHADOW: never disturb the grade path
        logger.warning(f"theme-axis shadow log failed for {r.get('ticker')}: {_e}")
        try:
            await log_audit_event(
                "theme_axis_shadow_failed",
                f"{r.get('ticker')} {r.get('alert_date')}: {type(_e).__name__}: {_e}",
            )
        except Exception:
            pass
