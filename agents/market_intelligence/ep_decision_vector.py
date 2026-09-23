"""#605 — the EP DECISION VECTOR registry: every input the admission stack and the
score consume, mapped to the `mi_ep_scan_log` column that persists it per candidate.

WHY THIS EXISTS (operator, 2026-08-29, after the EP backtest could not determine the
SIGN of the strategy's expectancy because 88% of candidates had no reconstructible
catalyst grade): *"we need to collect data properly so we don't keep running into
issues every time. every time you say we're missing this or that, we patch it and
next time we're still missing stuff, I don't want to see this again."* The recurring
failure is not any single missing column — it is that a NEW gate or scoring input
can land without its value being logged, and nothing goes red. This registry plus
`tests/test_605_decision_vector_capture.py` make that mechanical, the same move
`scripts/gate_provenance_registry.py` made for gate provenance: you cannot add a
scoring input or a gate without either wiring its inputs to a column or writing
down, HERE, why not — and that write-down is the human checkpoint where a reviewer
notices a hole.

THE CONTRACT the test enforces (all decidable from source, no DB):
  1. Every parameter of `_score_ep`, every component key of `SCORE_WEIGHTS` (and
     the LEGACY table), every parameter of `shortlist_prescore`, and every key of
     `SHORTLIST_WEIGHTS` appears in the matching map below — EXACT set equality,
     so a deleted input flags its stale entry too.
  2. Every column named below exists end-to-end: as a `"column":` key in
     ep_detector's row builders, in `db.log_ep_scan_candidates`' INSERT column
     list, and in the `mi_ep_scan_log` CREATE block (ALTER↔CREATE parity is
     pinned separately by test_schema_alter_create_parity.py).
  3. Every `stage=`/`reject_stage` literal in ep_detector equals a GATE_VECTOR
     key, and vice versa.
  4. TRIPWIRES: the counts of `continue` statements and `_log_filtered(` calls
     inside `run_ep_scan` match the EXPECTED_* constants below. A new gate is,
     textually, a new `continue` (silent kill) or a new `_log_filtered` call —
     either moves a count and goes red until this registry is consciously
     updated. A pure refactor that moves the counts updates the constants in the
     same commit; that forced touch IS the checkpoint (a tripwire, not a proof —
     stated honestly, same as gate provenance's semantic-fidelity limit).
  5. FLOOR-CENSORSHIP GUARD: the fixed capture floors sit at or below every
     acting admission floor, so no future floor change can silently re-create
     the June/July-2026 hole (zero rows in the 9-10% band while MIN_GAP_PCT was
     10) or re-open the minute-bar coverage hole the 08-29 backfill closed.

An entry's value is either a tuple of `mi_ep_scan_log` column names, or a
{"derived": "..."} dict for an input that is deliberately NOT a per-row column
because it is exactly reconstructible from persisted data + git history. Adding a
"derived" entry is a conscious, reviewable claim — make it true.
"""
from __future__ import annotations

# ── 1. `_score_ep` parameters → persisting columns ─────────────────────────────────
SCORE_EP_INPUT_COLUMNS: dict[str, "tuple[str, ...] | dict"] = {
    "gap_pct": ("gap_pct",),
    "rel_volume": ("rel_volume",),
    "catalyst_quality": ("catalyst_quality", "llm_catalyst_quality"),
    # the only profile fields the score path reads are floatShares (scored) and
    # marketCap/sector (threaded to the judge; mcap also persisted per-row).
    "profile": ("float_shares", "market_cap"),
    # regime label per date lives in mi_market_regime; confidence_multiplier is
    # pinned 1.0 (#233) and persisted on alert rows; the acting side is score_side.
    "regime_multiplier": {"derived": "mi_market_regime row for scan_date (Bull=1.2) "
                                      "x confidence_multiplier (pinned 1.0, #233)"},
    "vol_percentile": ("vol_percentile",),
    "prior_3m_change": ("prior_3m_change",),
    "projected_vol_multiple": ("projected_vol_multiple",),
    "in_active_theme": ("in_active_theme",),
    "adv_dollar": ("adv", "prev_close"),  # adv_dollar = adv shares x prev_close
    "weights": ("score_side",),  # which table acted; values live in ep_rubric + git
}

# ── 2. `SCORE_WEIGHTS` components → the columns carrying each component's input ────
SCORE_COMPONENT_COLUMNS: dict[str, "tuple[str, ...] | dict"] = {
    "gap": ("gap_pct",),
    "liquidity": ("adv", "prev_close", "projected_vol_multiple", "rel_volume"),
    "catalyst": ("catalyst_quality", "llm_catalyst_quality"),
    "float": ("float_shares",),
    "vol_conviction": ("vol_percentile",),
    "theme_bonus": ("in_active_theme",),
    "conviction_floor": ("gap_pct", "catalyst_quality"),
    "output_scale": ("score_side",),  # presentation transform — no per-row input
}

# ── 3. shortlist pre-score inputs ──────────────────────────────────────────────────
SHORTLIST_INPUT_COLUMNS: dict[str, "tuple[str, ...] | dict"] = {
    "adv_dollar": ("adv", "prev_close"),
    "gap_pct": ("gap_pct",),
    "in_active_theme": ("in_active_theme",),
}
SHORTLIST_COMPONENT_COLUMNS: dict[str, "tuple[str, ...] | dict"] = {
    "liquidity": ("adv", "prev_close"),
    "gap": ("gap_pct",),
    "theme_bonus": ("in_active_theme",),
}

# ── 4. the admission funnel: reject_stage → the inputs that stage compared ─────────
# Keys are the EXACT `stage=`/`reject_stage` literals ep_detector writes. Per-tick
# raw inputs each stage decided on; thresholds/constants live in code + git (and in
# scripts/gate_provenance_registry.py where cohort-shaping).
GATE_VECTOR: dict[str, "tuple[str, ...]"] = {
    # MIN_PREV_CLOSE / MIN_PREV_DAY_VOLUME (#570 rows)
    "universe_floor": ("prev_close", "prev_day_volume", "current_price", "gap_pct"),
    # below the acting admission floor — Pass-1 capture band + Pass-2 floor drops (#605)
    "gap_floor": ("gap_pct", "gap_pct_delayed", "gap_pct_rt", "current_price",
                  "prev_close", "price_source"),
    # outside the graded top-SHORTLIST_SIZE under the acting order
    "shortlist_cap": ("rank_by_prescore", "rank_by_gap", "adv", "gap_pct",
                      "in_active_theme"),
    # RVOL@T anchor gate (pm or session — anchor derivable from minutes_since_open)
    "rvol_gate": ("pm_rvol", "pm_rvol_baseline_n", "today_volume",
                  "minutes_since_open"),
    "cooldown": ("days_since_prior_alert", "gap_pct"),
    "duplicate": ("scan_date",),  # same-day mi_ep_alerts row is the whole input
    "extension": ("extension_pct", "prev_close"),
    # check_filters: 30d median $ADV / Wilder ATR14% / market cap
    "quality_filter": ("quality_adv_dollar", "atr_pct", "market_cap"),
    # M&A / routine-catalyst-low-gap / pm-shares floor — read the ACTING grade
    "post_grade_filter": ("catalyst_quality", "llm_catalyst_quality", "gap_pct",
                          "today_volume", "pm_rvol"),
    # scored below the acting bar
    "score_bar": ("ep_score", "ep_bar", "score_breakdown", "score_side",
                  "catalyst_quality"),
}

# ── 5. tripwires (see module docstring §4 — update ONLY with a conscious review) ───
# `continue` statements inside run_ep_scan (a new one = a possible silent kill).
EXPECTED_SCAN_CONTINUE_COUNT = 17
# `_log_filtered(` call sites inside run_ep_scan (a new one = a new logged gate —
# register its stage + inputs above).
EXPECTED_LOG_FILTERED_CALLS = 9

# Convenience: every column any entry references (the test wires each end-to-end).
def all_registered_columns() -> set[str]:
    cols: set[str] = set()
    for mapping in (SCORE_EP_INPUT_COLUMNS, SCORE_COMPONENT_COLUMNS,
                    SHORTLIST_INPUT_COLUMNS, SHORTLIST_COMPONENT_COLUMNS,
                    GATE_VECTOR):
        for v in mapping.values():
            if isinstance(v, tuple):
                cols.update(v)
    return cols
