"""MAGNA53 EP score rubric — Stage 2 of the score-tunability plan (2026-08-22).

Pure refactor: `_score_ep` in `ep_detector.py` used to have every weight as an
inline literal buried inside if/elif ladders — nothing could be tuned without
editing scoring logic, and nothing could be swept. `SCORE_WEIGHTS` below is
the SAME values, named and centralized so a future weight sweep (Stage 5 of
the plan) can vary them without touching control flow.

⚠ THIS FILE CHANGES NO BEHAVIOUR. Every tier cut and point value here is
byte-identical to what `_score_ep` computed before this refactor — proven by
`tests/test_ep_score_stage2_refactor.py`, which pins `_score_ep`'s outputs
across a boundary sweep captured from the pre-refactor code and re-asserts
them against this table.

Shape follows the house precedent, `catalyst_rubric.py:66-68`
(`AXIS_MAX`/`AXIS_WEIGHT`/`MAX_COMPOSITE`): tunable values live in a plain
dict, not scattered through function bodies. `_score_ep`'s components are
heterogeneous (ordered tier ladders, categorical maps, boolean bonuses, a
multi-condition floor) rather than catalyst_rubric's uniform per-axis
max/weight, so each `SCORE_WEIGHTS[component]` entry carries whatever shape
that component needs — a `tiers` list of `(threshold, points)` pairs read
by `tier_points()` below for the ladders, a flat map for `catalyst`, a
single threshold for `float`, an ordered `rules` list for `conviction_floor`
(first match wins, mirroring the original elif chain).

Provenance: the full original inline comments (evidence, dates, operator
sign-offs, doc citations) move here with their literals rather than staying
behind in `ep_detector.py` pointing at nothing — this file is now the single
place a tunable value and the evidence for it live together. Each entry also
carries a short `"source"` one-liner for at-a-glance citation.

NOT included here (out of scope for this refactor):
- The regime multiplier (Bull=1.2x / else=1.0x) is computed at
  `ep_detector.py:2516`, OUTSIDE `_score_ep`'s body, and is already passed
  into `_score_ep` as the `regime_multiplier` parameter — i.e. already
  externalized/tunable at the call site. Per this stage's explicit scope
  ("do not touch anything outside `_score_ep`'s body"), that literal is left
  where it is. `_score_ep` itself does nothing but `raw_score *
  regime_multiplier` — there is no inline literal there to extract.
- `SHORTLIST_WEIGHTS` (the pre-grading cheap-score table) — Stage 1/3, a
  different card. Do not add it here.
"""
from __future__ import annotations


def tier_points(value: float, tiers: list[tuple[float, int]], default: int = 0) -> int:
    """Return the points for the first tier whose threshold `value` clears.

    `tiers` must be sorted descending by threshold (highest tier first) —
    every ladder below is authored in that order, matching the original
    if/elif ... else chains it replaces (first-match-wins, same as elif).
    """
    for threshold, points in tiers:
        if value >= threshold:
            return points
    return default


def resolve_conviction_floor(
    gap_pct: float, catalyst_quality: str, rules: list[dict],
) -> int | None:
    """First matching rule wins — mirrors the original if/elif/elif/elif
    chain exactly (order in `rules` IS the precedence, not just documentation).
    Returns None when no rule matches (the original left `conviction_floor`
    out of the breakdown dict entirely in that case)."""
    for rule in rules:
        if gap_pct >= rule["min_gap"] and catalyst_quality == rule["catalyst"]:
            return rule["floor"]
    return None


SCORE_WEIGHTS = {
    # Gap magnitude — scaled: bigger gaps = stronger signal.
    # (Comment previously read "max 15" while awarding 25 — docstring/code
    # mismatch, fixed in the same commit as this extraction; the point
    # values themselves are unchanged.)
    "gap": {
        "tiers": [
            (20, 25),
            (15, 20),
            (10, 15),
            (8, 10),
        ],
        "default": 0,
        "source": "these tier cuts date to commit 77179405, 2026-03-20 "
                   "('rebalance MAGNA53 scoring'); unchanged since "
                   "(git log -S verified)",
    },

    # LIQUIDITY — operator-signed 2026-08-22, replaces the RVOL tiers.
    # WHY: the old tiers scored "how unusual is today's volume vs this stock's own
    # normal". Real EPs do not look like that — the labelled cohort's MEDIAN is
    # 1.8x, which earned ZERO under the old ladder, while a sleepy micro-cap at 3x
    # scored 10. Measured on 26 labelled real EPs vs 1,074 ordinary gap days:
    # ex-ante 20-day ADV$ separates at AUC 0.72 vs day-RVOL's 0.31 (0.5 = a coin
    # flip; the old component ran BACKWARDS). It also needs no intraday projection
    # and is already computed per scan row. Evidence + tier derivation:
    # docs/analysis/score_redesign_proposal_533_2026-08-22.md. SSoT: magna53_ep.md.
    # ⚠ The separate 2.0x session-RVOL GATE is untouched — this changes RANKING only.
    #
    # ADV unknown (new listing, thin history): fall back to the OLD RVOL ladder
    # rather than award 0 — a data gap must never silently sink a candidate (P1:
    # a false exclusion is invisible). Mirrors `_check_adv_dollar_volume`, which
    # also lets an unknown-ADV name through rather than dropping it. Fallback
    # signal is `projected_vol_multiple` when known (post-open), else
    # `rel_volume` (premarket, `projected_vol_multiple is None`).
    "liquidity": {
        "adv_tiers": [
            (500_000_000, 15),
            (250_000_000, 12),
            (100_000_000, 10),
            (50_000_000, 7),
        ],
        "adv_default": 0,
        "fallback_tiers": [
            (10, 15),
            (5, 12),
            (3, 10),
            (2, 7),
        ],
        "fallback_default": 0,
        "source": "docs/analysis/score_redesign_proposal_533_2026-08-22.md; "
                   "operator-signed 2026-08-22; AUC 0.72 vs old RVOL ladder's 0.31",
    },

    # Catalyst quality — the single most important EP signal.
    # "mna" should never reach scoring (hard-filtered above), but treat as 0
    # if it does — same for any other unrecognized label (falls to else -> 0).
    "catalyst": {
        "points": {
            "game_changer": 25,
            "strong": 15,
        },
        "default": 0,
        "source": "point values date to commit 77179405, 2026-03-20 "
                   "('rebalance MAGNA53 scoring'); unchanged since "
                   "(git log -S verified)",
    },

    # Low float bonus.
    "float": {
        "max_shares": 50_000_000,
        "points": 5,
        "default": 0,
        "source": "present since the original Market Intelligence Agent POC "
                   "commit (cb289116); threshold unchanged since "
                   "(git log -S verified)",
    },

    # Volume conviction: pre-market volume vs stock's own historical ADV
    # distribution (percentile, 0-100; see `_volume_percentile`).
    "vol_conviction": {
        "tiers": [
            (90, 5),
            (70, 3),
        ],
        "default": 0,
        "source": "added commit 5c2a1dc2, 2026-03-14 ('Add pre-market volume "
                   "percentile to EP scoring'); tiers unchanged since "
                   "(git log -S verified)",
    },

    # R4 in-theme bonus (2026-05-17 ship). +10 when ticker is in an
    # Accelerating or Mainstream theme on alert_date. Env-flagged
    # (`R4_THEME_BONUS_ENABLED`, checked in `_score_ep` — control flow, not a
    # tunable value, stays there) for fast rollback. Under current
    # ep_threshold=70 this is decorative — verified via pre-ship SQL (0
    # MODERATE-in-theme alerts in 60d would cross HIGH with +10). Shipped for
    # telemetry/visibility: score breakdown surfaces the theme context, and
    # Phase 5 meta-rubric will compose theme_context as a separate scoring
    # input with its own calibrated weights. Evidence: in-theme alerts had
    # 67% WR vs 40% uncovered in label cross-tab; +27pp lift.
    "theme_bonus": {
        "points": 10,
        "default": 0,
        "source": "R4 ship 2026-05-17 — +27pp WR lift, in-theme vs uncovered",
    },

    # Conviction floor: massive gap + quality catalyst = high-conviction
    # regardless of secondary factors. The gap itself is evidence of
    # institutional conviction. Rules are evaluated IN ORDER, first match
    # wins (mirrors the original if/elif/elif/elif — order is precedence).
    # 20%+ strong = same floor as 15%+ game_changer (market voted with its feet).
    # 10-15% game_changer: floor 60 -> MODERATE at minimum; fires HIGH in
    # Bull w/ Gemini agreement.
    "conviction_floor": {
        "rules": [
            {"min_gap": 15, "catalyst": "game_changer", "floor": 80},
            {"min_gap": 20, "catalyst": "strong", "floor": 80},
            {"min_gap": 15, "catalyst": "strong", "floor": 70},
            {"min_gap": 10, "catalyst": "game_changer", "floor": 60},
        ],
        "source": "introduced commit 77179405, 2026-03-20; the 20%+ strong "
                   "-> 80 rule (rule 2) added same day, commit 63eda07a "
                   "('Raise conviction floor: 20%+ strong gap = 80 raw'); "
                   "unchanged since (git log -S verified)",
    },
}
