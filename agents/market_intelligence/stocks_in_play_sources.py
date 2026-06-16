"""Stocks-in-Play source_detector enum + automation_class enum.

Per ADR 0004 §4 (2026-05-22) — constants module to prevent magic-string
drift across N detector insert sites. Adding a new source_detector
requires updating VALID_SOURCES in the same commit (friction-by-design,
same pattern as broker/skip_reasons.py + Gate 5 G ALLOWED_WRITERS).

Two conceptual classes per ADR 0004 §4 framing (user direction 2026-05-23):

  Methodology presence — "this stock is in play under methodology X"
    Doesn't specify HOW to enter; multiple entry techniques may be valid.
    See memory/user_tight_range_entry_techniques.md for the 5-row taxonomy.

  Entry-technique trigger — "actionable trigger fired using mechanism Y"
    Each is a distinct detector class. Multiple may fire on the same
    ticker during its presence window — operator picks the entry style.
"""
from __future__ import annotations

# ── Methodology presence signals ──────────────────────────────────────
SOURCE_SUGAR_BABY_COHORT        = "sugar_baby_cohort"          # Pradeep persistent cohort
SOURCE_SUGAR_BABY_RIPE          = "sugar_baby_ripe"            # cohort × flag stage
SOURCE_FLAG_TIGHTENING          = "flag_tightening"            # in tight range, pre-breakout
SOURCE_FLAG_COILED              = "flag_coiled"                # late-base, max compression
SOURCE_WICK_FILL                = "wick_fill"
SOURCE_PARABOLIC_SHORT          = "parabolic_short"
SOURCE_FISHHOOK_V3              = "fishhook_v3"

# ── Entry-technique triggers ──────────────────────────────────────────
SOURCE_CONVERGENCE_ANTICIPATORY = "convergence_anticipatory"   # cohort × COILED/TIGHTENING × EP
SOURCE_CONVERGENCE_BREAKOUT     = "convergence_breakout"       # cohort × TRIGGERED × EP
SOURCE_FLAG_BREAK_INTRADAY      = "flag_break_intraday"        # ADR 0005 #94 — Entry #1
SOURCE_FLAG_TRIGGERED           = "flag_triggered"             # EOD post-hoc; superseded by intraday
SOURCE_FLAG_SUPPORT_TEST        = "flag_support_test"          # Future #95 — Entry #2
SOURCE_FLAG_MA_PULLBACK         = "flag_ma_pullback"           # Future #96 — Entry #3
SOURCE_FLAG_LOWVOL_REST         = "flag_lowvol_rest"           # Future #97 — Entry #4
SOURCE_FLAG_UNDERCUT_RALLY      = "flag_undercut_rally"        # Future #98 — Stamatoudis U&R
SOURCE_DELAYED_EP_REENTRY       = "delayed_ep_reentry"        # #270 delayed-EP re-entry lifecycle: ready/triggered → /watch (drill-down stays /sip)
SOURCE_MAGNA53_EP_HIGH          = "magna53_ep_high"
SOURCE_NINEM_EP_HIGH            = "ninem_ep_high"

VALID_SOURCES = frozenset({
    # Methodology presence
    SOURCE_SUGAR_BABY_COHORT, SOURCE_SUGAR_BABY_RIPE,
    SOURCE_FLAG_TIGHTENING, SOURCE_FLAG_COILED,
    SOURCE_WICK_FILL, SOURCE_PARABOLIC_SHORT, SOURCE_FISHHOOK_V3,
    # Entry-technique triggers
    SOURCE_CONVERGENCE_ANTICIPATORY, SOURCE_CONVERGENCE_BREAKOUT,
    SOURCE_FLAG_BREAK_INTRADAY, SOURCE_FLAG_TRIGGERED,
    SOURCE_FLAG_SUPPORT_TEST, SOURCE_FLAG_MA_PULLBACK,
    SOURCE_FLAG_LOWVOL_REST, SOURCE_FLAG_UNDERCUT_RALLY,
    SOURCE_DELAYED_EP_REENTRY,
    SOURCE_MAGNA53_EP_HIGH, SOURCE_NINEM_EP_HIGH,
})

# ── automation_class enum ─────────────────────────────────────────────
# Per ADR 0004 §2 axis 3 graduation model:
#   informational  → operator_only  → apollo_eligible
# Transitions defined in ADR 0004 §2.3 (informational → operator_only
# triggered by cross-detector convergence on same ticker; operator_only →
# apollo_eligible requires N≥10 settled positive outcomes AND explicit
# user UPDATE — never auto-promotes).
CLASS_INFORMATIONAL    = "informational"
CLASS_OPERATOR_ONLY    = "operator_only"
CLASS_APOLLO_ELIGIBLE  = "apollo_eligible"

VALID_CLASSES = frozenset({
    CLASS_INFORMATIONAL,
    CLASS_OPERATOR_ONLY,
    CLASS_APOLLO_ELIGIBLE,
})


def validate_source(source: str) -> str:
    """Raise ValueError if source not in VALID_SOURCES. Returns input
    unchanged on success. Use at INSERT sites for fail-fast on typos."""
    if source not in VALID_SOURCES:
        raise ValueError(
            f"Unknown source_detector {source!r}; "
            f"add to stocks_in_play_sources.py VALID_SOURCES in same commit"
        )
    return source


def validate_class(automation_class: str) -> str:
    """Raise ValueError if class not in VALID_CLASSES."""
    if automation_class not in VALID_CLASSES:
        raise ValueError(
            f"Unknown automation_class {automation_class!r}; "
            f"must be one of {sorted(VALID_CLASSES)}"
        )
    return automation_class
