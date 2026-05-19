"""Runtime adapter wiring the 6-axis catalyst rubric into ep_detector.

Bridges the fresh multi-source extraction (mi_ep_catalyst_metrics) into
the rubric scorer's expected input shape (deltas + beat + guidance dicts).

Hybrid sourcing (intentional, named in function for honesty):
- q0 (latest quarter, just-announced): FROM fresh extraction. Catalyst-day
  data that yfinance lags by 24-72h.
- q1, q2, q3 (older quarters): from yfinance (settled data, reliable).
- margins: from yfinance (settled, reliable).
- beat: from fresh extraction's q_eps.beat_vs_est_pct (revenue beat not
  yet in extraction schema — would need prompt update for full Axis 4
  coverage; current state scores Axis 4 as None when rev_beat missing).
- guidance: from fresh extraction's guidance_fy_revenue_usd.midpoint_yoy_pct.

Failure modes (per advisor 2026-05-19 plan):
- Both succeed: full 6-axis rubric runs, gate on composite_scaled
- Fresh OK + yfinance fails: rubric runs on q0-only data (accel-unknown
  branches in rubric handle this). Composite scaled by available axes.
- Fresh fails: caller's safety-net Q-rev threshold gate takes over.

The gate is composite-based (CATALYST_RUBRIC_MIN_COMPOSITE, env-tunable).
Labels are calibrated against operator labels from the weekend's labeling
work — fixtures may need re-validation post-ship.
"""
from __future__ import annotations

import logging
from datetime import date
from typing import Any

logger = logging.getLogger(__name__)


def _extracted_to_q0_deltas(extracted: dict[str, Any]) -> dict[str, Any]:
    """Convert mi_ep_catalyst_metrics extraction to rubric's q0 deltas.

    Extraction stores yoy_pct as PERCENT (11.7 = 11.7%). Rubric expects
    FRACTION (0.117). Convert here.

    Sources the q0 margins block from extraction's q_margins (already in
    decimal fraction form per the prompt schema).
    """
    deltas: dict[str, Any] = {
        "rev_yoy_q0": None,
        "rev_yoy_q1": None, "rev_yoy_q2": None, "rev_yoy_q3": None,
        "eps_yoy_q0": None,
        "eps_yoy_q1": None, "eps_yoy_q2": None,
        "rev_qoq_q0": None,
        "rev_accel": None, "rev_accel_streak": 0,
        "eps_accel": None,
        "rev_yoy_max_prior_7q": None,
        "eps_qm4": None,
        "margins_q0": {}, "margins_q1": {}, "margins_q2": {},
        "data_quality_flag": "fresh_q0_only",
    }
    qr = extracted.get("q_revenue_usd") or {}
    if isinstance(qr, dict):
        yoy = qr.get("yoy_pct")
        if isinstance(yoy, (int, float)):
            deltas["rev_yoy_q0"] = yoy / 100.0

    qe = extracted.get("q_eps") or {}
    if isinstance(qe, dict):
        yoy = qe.get("yoy_pct")
        if isinstance(yoy, (int, float)):
            deltas["eps_yoy_q0"] = yoy / 100.0

    # q0 margins from extraction (prompt returns decimal fractions 0-1).
    # Filter out None entries to keep the dict clean for Axis 3 scoring.
    qm = extracted.get("q_margins") or {}
    if isinstance(qm, dict):
        m0 = {}
        for k in ("gross_margin", "op_margin", "net_margin"):
            v = qm.get(k)
            if isinstance(v, (int, float)):
                m0[k] = float(v)
        if m0:
            deltas["margins_q0"] = m0
    return deltas


def _augment_with_yfinance_historical(ticker: str, deltas: dict[str, Any]) -> dict[str, Any]:
    """Best-effort augmentation: pull yfinance quarterlies for older quarters.

    yfinance lags announcements by 24-72h, so its latest row is q1 (the
    quarter BEFORE the just-announced one). We use yfinance rows for
    q1/q2/q3 YoY + margins. If yfinance is fresh enough that q0 is
    available there too, we ignore it — extraction is authoritative for q0.

    Failure: returns deltas unchanged (rubric handles missing axes).
    """
    try:
        import yfinance as yf
        t = yf.Ticker(ticker)
        qf = t.quarterly_financials
        if qf is None or qf.empty:
            return deltas

        # quarterly_financials returns most-recent-first columns
        cols = list(qf.columns)
        if len(cols) < 5:
            return deltas

        # yfinance line names use SPACES ("Total Revenue" not "TotalRevenue") —
        # debugged 2026-05-19 for AGYS. Both forms tried for cross-version
        # compatibility, but space-form is the modern shape.
        rev_row = None
        for line in ("Total Revenue", "Revenue", "Operating Revenue",
                     "TotalRevenue", "OperatingRevenue"):
            if line in qf.index:
                rev_row = qf.loc[line]
                break
        if rev_row is None:
            return deltas

        # The most-recent yfinance column may or may not be q0. If announced
        # within the last 48h, it likely hasn't been picked up yet — yfinance
        # row 0 = q1 from our perspective. If announced longer ago, yfinance
        # may have it. We're conservative: use yfinance rows for q1+ only
        # (skip index 0 to be safe; treat row 0 as q1).
        # YoY math: row[i] vs row[i+4] (same fiscal quarter year ago).
        def _yoy(i: int) -> float | None:
            if i + 4 >= len(cols):
                return None
            new = rev_row.iloc[i]
            old = rev_row.iloc[i + 4]
            if new and old and old > 0:
                return (new - old) / old
            return None

        deltas["rev_yoy_q1"] = _yoy(0)  # yfinance row 0 = q1 (last quarter)
        deltas["rev_yoy_q2"] = _yoy(1)
        deltas["rev_yoy_q3"] = _yoy(2)

        # Acceleration: q0 (from extraction) vs q1 (from yfinance)
        if deltas["rev_yoy_q0"] is not None and deltas["rev_yoy_q1"] is not None:
            deltas["rev_accel"] = deltas["rev_yoy_q0"] - deltas["rev_yoy_q1"]

        # EPS YoY hybrid: extraction's q0 (if present) + yfinance for q1+
        # so Axis 2 can score even when LLM doesn't compute EPS YoY from
        # raw numbers. yfinance uses 'Diluted EPS' (or 'Basic EPS').
        eps_row = None
        for line in ("Diluted EPS", "Basic EPS", "DilutedEPS", "BasicEPS"):
            if line in qf.index:
                eps_row = qf.loc[line]
                break
        if eps_row is not None:
            def _eps_yoy(i: int) -> float | None:
                if i + 4 >= len(cols):
                    return None
                new_e = eps_row.iloc[i]
                old_e = eps_row.iloc[i + 4]
                if new_e is not None and old_e is not None and abs(float(old_e)) > 0.001:
                    return (float(new_e) - float(old_e)) / abs(float(old_e))
                return None
            # If extraction didn't get eps_yoy_q0, leave it None (yfinance
            # row 0 isn't the just-announced q0 — it's q1). q1/q2 from yfinance.
            deltas["eps_yoy_q1"] = _eps_yoy(0)
            deltas["eps_yoy_q2"] = _eps_yoy(1)
            # Small-base guardrail value (eps_qm4 = EPS 4 quarters ago,
            # i.e. same fiscal quarter prior year — yfinance row 3 since
            # row 0 = q1 from our perspective so q-4-of-q1 is row 4...
            # Actually q0's prior-year is yfinance row 3 (q1=last quarter,
            # q1-of-q1=row 4 = same-q-of-prior-year-as-q1 — but for q0
            # specifically, prior-year same quarter would be row 3 since
            # yfinance lacks q0). Use row 3 as eps_qm4 for the just-
            # announced q0 quarter.
            if 3 < len(cols):
                qm4_val = eps_row.iloc[3]
                if qm4_val is not None:
                    deltas["eps_qm4"] = float(qm4_val)

            # EPS acceleration if BOTH q0 (set by build_rubric_inputs_hybrid
            # post-process) and q1 (set just above) are present. The q0
            # derivation happens AFTER augment returns — see
            # build_rubric_inputs_hybrid below.
            if deltas["eps_yoy_q0"] is not None and deltas["eps_yoy_q1"] is not None:
                deltas["eps_accel"] = deltas["eps_yoy_q0"] - deltas["eps_yoy_q1"]

        # prior_max for milestone axis (use yfinance q1-q7 since q0 is the catalyst)
        prior_yoys = []
        for i in range(0, min(7, len(cols) - 4)):
            v = _yoy(i)
            if v is not None:
                prior_yoys.append(v)
        if prior_yoys:
            deltas["rev_yoy_max_prior_7q"] = max(prior_yoys)

        # Margins from yfinance (gross/op/net). yfinance line names use
        # spaces ("Gross Profit"). Try modern form first, fall back to
        # concatenated for older yfinance versions.
        def _safe_div_any(num_lines: tuple[str, ...], den_lines: tuple[str, ...], idx: int) -> float | None:
            try:
                num_val = None
                for ln in num_lines:
                    if ln in qf.index:
                        num_val = qf.loc[ln].iloc[idx]
                        break
                den_val = None
                for ln in den_lines:
                    if ln in qf.index:
                        den_val = qf.loc[ln].iloc[idx]
                        break
                if num_val is not None and den_val and den_val > 0:
                    return float(num_val) / float(den_val)
            except Exception:
                return None
            return None

        # yfinance shape for AGYS Q3 FY26 (confirmed 2026-05-19):
        #   Gross Profit / Total Revenue → ~62%
        #   Operating Income / Total Revenue → ~14%
        #   Net Income / Total Revenue → ~12%
        _rev_lines = ("Total Revenue", "TotalRevenue", "Operating Revenue")
        _gp_lines = ("Gross Profit", "GrossProfit")
        _oi_lines = ("Operating Income", "OperatingIncome")
        _ni_lines = ("Net Income", "NetIncome", "Net Income Common Stockholders")

        # margins_q1 / q2 = the 2 most-recent yfinance quarters (which are
        # q1, q2 from our perspective since q0 is the just-announced
        # catalyst not yet in yfinance). The rubric's score_axis_3 will
        # use these to compute QoQ deltas.
        for q_key, idx in (("margins_q1", 0), ("margins_q2", 1)):
            deltas[q_key] = {
                "gross_margin": _safe_div_any(_gp_lines, _rev_lines, idx),
                "op_margin": _safe_div_any(_oi_lines, _rev_lines, idx),
                "net_margin": _safe_div_any(_ni_lines, _rev_lines, idx),
            }
        # margins_q0 (just-announced quarter):
        # - If extraction captured them from the press release, _extracted_to_q0_deltas
        #   has already set them in deltas["margins_q0"].
        # - If not (common — press releases often quote only "record margins"
        #   without numbers), fall back to approximating q0 from yfinance q1
        #   with explicit data_quality_flag so the rubric's Axis 3 can score
        #   (better than score=None). The approximation says "assume margins
        #   continue at last quarter's level" — conservative for trajectory
        #   analysis. Acceleration signal lost in this case but level signal
        #   preserved.
        if not deltas.get("margins_q0") and deltas.get("margins_q1"):
            # Only copy non-None values; preserve transparency
            approx_q0 = {
                k: v for k, v in deltas["margins_q1"].items()
                if v is not None
            }
            if approx_q0:
                deltas["margins_q0"] = approx_q0
                deltas["data_quality_flag"] = (
                    "fresh_q0_plus_yfinance_historical_and_margin_proxy"
                )

        deltas["data_quality_flag"] = "fresh_q0_plus_yfinance_historical"

    except Exception as e:
        logger.warning(f"yfinance augmentation failed for {ticker}: {e}")
    return deltas


def _extracted_to_beat(extracted: dict[str, Any]) -> dict[str, Any] | None:
    """Build the beat dict for Axis 4 from extraction.

    Both q_revenue.beat_vs_est_pct and q_eps.beat_vs_est_pct are now captured
    by the expanded extraction prompt (2026-05-19). Return None if BOTH are
    missing; rubric returns 'partial_consensus_data' (score=None) if only
    one is present.
    """
    qr = extracted.get("q_revenue_usd") or {}
    qe = extracted.get("q_eps") or {}
    rev_beat = qr.get("beat_vs_est_pct") if isinstance(qr, dict) else None
    eps_beat = qe.get("beat_vs_est_pct") if isinstance(qe, dict) else None
    if rev_beat is None and eps_beat is None:
        return None
    return {
        "rev_beat_pct": rev_beat / 100.0 if isinstance(rev_beat, (int, float)) else None,
        "eps_beat_pct": eps_beat / 100.0 if isinstance(eps_beat, (int, float)) else None,
    }


def _extracted_to_guidance(extracted: dict[str, Any]) -> dict[str, Any] | None:
    """Build the guidance dict for Axis 5 from extraction.

    Primary source: extracted["guidance_change"] (new 2026-05-19 field with
    explicit direction + raise_pct_vs_consensus).

    Fallback: extracted["guidance_fy_revenue_usd"].midpoint_yoy_pct as a
    proxy when guidance_change is missing but FY guidance midpoint is.
    """
    gc = extracted.get("guidance_change")
    if isinstance(gc, dict) and gc.get("direction"):
        direction = gc.get("direction")
        raise_pct = gc.get("raise_pct_vs_consensus")
        return {
            "direction": direction,
            "raise_pct_vs_consensus": (
                raise_pct / 100.0
                if isinstance(raise_pct, (int, float))
                else None
            ),
        }

    # Fallback to midpoint_yoy_pct proxy
    gf = extracted.get("guidance_fy_revenue_usd")
    if not isinstance(gf, dict):
        return None
    midpoint_yoy = gf.get("midpoint_yoy_pct")
    if not isinstance(midpoint_yoy, (int, float)):
        return None
    direction = "raised" if midpoint_yoy > 0 else "lowered"
    return {
        "direction": direction,
        "raise_pct_vs_consensus": midpoint_yoy / 100.0 if midpoint_yoy > 0 else None,
    }


def build_rubric_inputs_hybrid(
    ticker: str,
    extracted: dict[str, Any],
    today: date,
) -> tuple[dict[str, Any], dict[str, Any] | None, dict[str, Any] | None]:
    """Build (fund, beat, guidance) inputs for catalyst_rubric.score_ticker.

    Honestly-named hybrid: q0 from fresh extraction, q1+ and margins from
    yfinance. See module docstring for rationale.
    """
    deltas = _extracted_to_q0_deltas(extracted)
    deltas = _augment_with_yfinance_historical(ticker, deltas)

    # Post-process: derive eps_yoy_q0 if extraction has q_eps.value but
    # not yoy_pct, AND yfinance gave us eps_qm4 (prior-year same quarter).
    # Common case: AGYS-class where LLM extracts $0.63 EPS but doesn't
    # state YoY %; we can compute from $0.63 / prior-year $0.14 → +350%.
    qe = extracted.get("q_eps") or {}
    if (deltas.get("eps_yoy_q0") is None
            and isinstance(qe, dict)
            and isinstance(qe.get("value"), (int, float))
            and isinstance(deltas.get("eps_qm4"), (int, float))
            and abs(deltas["eps_qm4"]) > 0.001):
        q0_eps = float(qe["value"])
        qm4 = float(deltas["eps_qm4"])
        deltas["eps_yoy_q0"] = (q0_eps - qm4) / abs(qm4)
        # Now also compute eps_accel if q1 is present
        if deltas.get("eps_yoy_q1") is not None:
            deltas["eps_accel"] = deltas["eps_yoy_q0"] - deltas["eps_yoy_q1"]

    fund = {
        "ticker": ticker,
        "deltas": deltas,
        "source_chain": "extraction_q0+yfinance_historical",
        "n_quarters_with_revenue": (
            4 if deltas.get("rev_yoy_q3") is not None
            else 3 if deltas.get("rev_yoy_q2") is not None
            else 2 if deltas.get("rev_yoy_q1") is not None
            else 1 if deltas.get("rev_yoy_q0") is not None
            else 0
        ),
    }
    beat = _extracted_to_beat(extracted)
    guidance = _extracted_to_guidance(extracted)
    return fund, beat, guidance


def score_ep_with_rubric(
    ticker: str,
    extracted: dict[str, Any],
    today: date,
) -> dict[str, Any] | None:
    """Run the 6-axis rubric on the fresh-extracted catalyst.

    Returns the rubric output dict (composite_raw, composite_scaled,
    max_available, label, caps_applied, per-axis details) OR None if
    inputs can't be built (no q_revenue_yoy_pct extracted).
    """
    qr = extracted.get("q_revenue_usd")
    if not isinstance(qr, dict) or qr.get("yoy_pct") is None:
        # Can't score without q0 revenue YoY
        return None
    try:
        from agents.market_intelligence.catalyst_rubric import score_ticker
        fund, beat, guidance = build_rubric_inputs_hybrid(ticker, extracted, today)
        return score_ticker(fund, beat=beat, guidance=guidance)
    except Exception as e:
        logger.warning(f"Rubric scoring failed for {ticker}: {e}")
        return None


# ── Theme membership (Pradeep #1 catalyst type) ──────────────────────────────


async def get_theme_membership(ticker: str) -> dict[str, Any] | None:
    """Look up active theme membership for `ticker`.

    Returns dict with {name, stage, score, theme_date} of the most recent
    active theme containing this ticker, or None if not in any active theme.

    Pradeep methodology ranks theme membership as the #1 catalyst type
    (above policy / shortage / sales acceleration). Currently surfaced as
    METADATA only on EP alerts — does not modify the rubric gate threshold
    pending forward calibration. Future iteration: theme-stage may adjust
    the composite threshold (Accelerating → lower threshold, etc).

    Query semantics:
    - Active = stage != 'Retired' AND theme_date within last 7 days
    - Ticker present in the theme's `tickers` ARRAY column
    - If multiple active themes contain the ticker, returns the one with
      highest score (most heat)
    """
    from agents.market_intelligence.db import get_pool
    pool = await get_pool()
    async with pool.acquire() as conn:
        row = await conn.fetchrow("""
            SELECT DISTINCT ON (name) name, stage, score, theme_date
            FROM mi_themes
            WHERE stage != 'Retired'
              AND theme_date >= CURRENT_DATE - INTERVAL '7 days'
              AND $1 = ANY(tickers)
            ORDER BY name, theme_date DESC, score DESC NULLS LAST
        """, ticker)
        if not row:
            return None
        # If multiple themes contain ticker, get all and pick highest score
        rows = await conn.fetch("""
            SELECT DISTINCT ON (name) name, stage, score, theme_date
            FROM mi_themes
            WHERE stage != 'Retired'
              AND theme_date >= CURRENT_DATE - INTERVAL '7 days'
              AND $1 = ANY(tickers)
            ORDER BY name, theme_date DESC
        """, ticker)
        # Sort by score descending (treat None as -inf for ordering)
        best = max(rows, key=lambda r: (r["score"] if r["score"] is not None else -1e9))
        return {
            "name": best["name"],
            "stage": best["stage"],
            "score": float(best["score"]) if best["score"] is not None else None,
            "theme_date": best["theme_date"].isoformat() if best["theme_date"] else None,
        }


_THEME_STAGE_EMOJI = {
    "Nascent":      "🌱",
    "Accelerating": "🔥",
    "Mainstream":   "📈",
    "Fading":       "🍂",
    "Retired":      "💤",
}


def format_theme_for_telegram(theme: dict[str, Any] | None) -> str:
    """One-line theme membership snippet for EP alert.

    Examples:
      Theme: 🔥 Custom AI Silicon & Hyperscale Datacenter (Accelerating, score 92)
      Theme: 🍂 GLP-1 / Obesity Therapeutics (Fading, score 41)
      Theme: — (no active theme membership)
    """
    if not theme:
        return "Theme: —"
    stage = theme.get("stage", "")
    emoji = _THEME_STAGE_EMOJI.get(stage, "")
    name = theme.get("name", "")
    score = theme.get("score")
    score_txt = f", score {score:.0f}" if score is not None else ""
    return f"Theme: {emoji} {name} ({stage}{score_txt})"


# ── Operator surfaces (human-readable formatting) ────────────────────────────


_LABEL_EMOJI = {
    "game_changer":    "🚀",
    "strong":          "✅",
    "routine_correct": "⚠️",
    "weak":            "🚫",
}


def _fmt_pct(v, places=1) -> str:
    """Format fraction as percent. None → '—'."""
    if v is None:
        return "—"
    return f"{v*100:+.{places}f}%" if abs(v) < 10 else f"{v:+.{places}f}%"


def _fmt_pct_raw(v, places=1) -> str:
    """Format percent (already in % units) as string. None → '—'."""
    if v is None:
        return "—"
    return f"{v:+.{places}f}%"


def format_rubric_for_telegram(
    ticker: str,
    extracted: dict[str, Any],
    today: date,
) -> str | None:
    """Compact human-readable rubric snapshot for the EP alert message.

    Format (multi-line, Markdown for Telegram):
        🧪 *Rubric: 16/39 (routine_correct ⚠️)*
        Revenue: 2/5 (+11.7% YoY, decelerating from +15.6%)
        Margins: 2/5 (flat)
        Beat: 2/5 (rev +1.7%, EPS +26%)
        Guidance: 3/5 (raised +1.0%)
        EPS / Milestone: not scored
        Caps: no_milestone_low_growth

    Returns None if extraction can't be scored.
    """
    result = score_ep_with_rubric(ticker, extracted, today)
    if not result:
        return None

    comp = result.get("composite_scaled")
    label = result.get("label", "?")
    label_e = _LABEL_EMOJI.get(label, "")
    caps = result.get("caps_applied") or []

    lines = []
    if comp is not None:
        lines.append(f"🧪 *Rubric: {comp:.1f}/39 ({label} {label_e})*")
    else:
        lines.append(f"🧪 *Rubric: not scored*")

    # Per-axis readable lines — only show axes that scored OR were materially
    # informative. Skip None axes unless they're "no_X_data" worth surfacing.
    deltas = (extracted.get("q_revenue_usd") or {})
    fund_deltas = {}  # rebuilt for display below

    # Axis 1 — Revenue
    a1_score = result.get("a1_score")
    a1_reason = result.get("a1_reason", "")
    if a1_score is not None:
        # Pull current yoy + prior for human reading
        # The reason string already has the numbers; surface a cleaner version
        qr = extracted.get("q_revenue_usd") or {}
        yoy = qr.get("yoy_pct")
        # Try to extract accel reading from reason string
        accel_text = ""
        if "decelerating" in a1_reason.lower():
            accel_text = ", decelerating"
        elif "accel=+" in a1_reason or "accel_streak" in a1_reason:
            accel_text = ", accelerating"
        elif "accel unknown" in a1_reason:
            accel_text = " (accel unknown)"
        yoy_txt = _fmt_pct_raw(yoy) if yoy is not None else "—"
        lines.append(f"Revenue: *{a1_score}/5* ({yoy_txt} YoY{accel_text})")

    # Axis 2 — EPS
    a2_score = result.get("a2_score")
    if a2_score is not None:
        qe = extracted.get("q_eps") or {}
        yoy = qe.get("yoy_pct")
        yoy_txt = _fmt_pct_raw(yoy) if yoy is not None else "—"
        lines.append(f"EPS: *{a2_score}/5* ({yoy_txt} YoY)")

    # Axis 3 — Margin
    a3_score = result.get("a3_score")
    a3_reason = result.get("a3_reason", "")
    if a3_score is not None:
        # The reason string captures it well
        lines.append(f"Margins: *{a3_score}/5* ({a3_reason[:60]})")

    # Axis 4 — Beat
    a4_score = result.get("a4_score")
    if a4_score is not None:
        qr = extracted.get("q_revenue_usd") or {}
        qe = extracted.get("q_eps") or {}
        rev_beat = qr.get("beat_vs_est_pct")
        eps_beat = qe.get("beat_vs_est_pct")
        rb_txt = _fmt_pct_raw(rev_beat) if rev_beat is not None else "—"
        eb_txt = _fmt_pct_raw(eps_beat) if eps_beat is not None else "—"
        lines.append(f"Beat: *{a4_score}/5* (rev {rb_txt}, EPS {eb_txt})")

    # Axis 5 — Guidance
    a5_score = result.get("a5_score")
    a5_reason = result.get("a5_reason", "")
    if a5_score is not None:
        lines.append(f"Guidance: *{a5_score}/5* ({a5_reason[:60]})")

    # Axis 6 — Milestone
    a6_score = result.get("a6_score")
    if a6_score and a6_score > 0:
        a6_reason = result.get("a6_reason", "")
        lines.append(f"Milestone bonus: *+{a6_score}* ({a6_reason[:60]})")

    # Missing axes — collapse into one note
    missing = []
    label_map = {"a1": "Revenue", "a2": "EPS", "a3": "Margins",
                 "a4": "Beat", "a5": "Guidance", "a6": "Milestone"}
    for ax_key, ax_label in label_map.items():
        if result.get(f"{ax_key}_score") is None:
            missing.append(ax_label)
    if missing:
        lines.append(f"_Not scored: {', '.join(missing)}_")

    if caps:
        lines.append(f"_Caps: {', '.join(caps)}_")

    return "\n".join(lines)


def format_rubric_full_breakdown(
    ticker: str,
    extracted: dict[str, Any],
    today: date,
) -> str:
    """Verbose readable breakdown for /rubric TICKER command.

    Includes everything in the snapshot PLUS source attribution + reasoning
    + extraction quality + disagreement flags.
    """
    result = score_ep_with_rubric(ticker, extracted, today)

    lines = [f"*{ticker} — Catalyst Rubric*"]

    if not result:
        lines.append("Rubric could not score (q_revenue_yoy_pct not extracted).")
        eq = extracted.get("extraction_quality", "low")
        lines.append(f"Extraction quality: {eq}")
        if extracted.get("reasoning_brief"):
            lines.append(f"Notes: {extracted['reasoning_brief']}")
        return "\n".join(lines)

    comp = result.get("composite_scaled")
    label = result.get("label", "?")
    label_e = _LABEL_EMOJI.get(label, "")
    threshold_ok = "PASS" if (comp is not None and comp >= 22) else "DOWNGRADE"

    lines.append(f"Composite: *{comp:.1f} / 39* → *{label}* {label_e} → *{threshold_ok}*")
    lines.append("")

    # Per-axis detail
    axis_meta = [
        ("a1", "Revenue trajectory", 5),
        ("a2", "EPS trajectory",     5),
        ("a3", "Margin trajectory",  5),
        ("a4", "Beat vs consensus",  5),
        ("a5", "Guidance change",    5),
        ("a6", "Milestone bonus",    4),
    ]
    for ax_key, ax_name, ax_max in axis_meta:
        score = result.get(f"{ax_key}_score")
        reason = result.get(f"{ax_key}_reason", "")
        if score is None:
            lines.append(f"  {ax_name}: _not scored_ — {reason}")
        else:
            lines.append(f"  {ax_name}: *{score}/{ax_max}* — {reason}")

    caps = result.get("caps_applied") or []
    if caps:
        lines.append("")
        lines.append(f"Caps applied: {', '.join(caps)}")

    # Extraction context
    eq = extracted.get("extraction_quality", "low")
    lines.append("")
    lines.append(f"Extraction quality: *{eq}*")

    qr = extracted.get("q_revenue_usd") or {}
    if isinstance(qr, dict):
        src = qr.get("sources") or []
        conf = qr.get("confidence", "—")
        lines.append(f"Q-rev sources: {', '.join(src) if src else '—'} (confidence: {conf})")

    if extracted.get("reasoning_brief"):
        lines.append(f"Reasoning: _{extracted['reasoning_brief']}_")

    disagreements = extracted.get("disagreement_flags") or []
    if disagreements:
        lines.append("")
        lines.append("⚠️ Disagreement flags:")
        for d in disagreements[:5]:
            lines.append(f"  • {d}")

    return "\n".join(lines)
