"""MAGNA53 EP score rubric — Stage 2 of the score-tunability plan (2026-08-22).

Pure refactor: `_score_ep` in `ep_detector.py` used to have every weight as an
inline literal buried inside if/elif ladders — nothing could be tuned without
editing scoring logic, and nothing could be swept. `SCORE_WEIGHTS` below is
the SAME values, named and centralized so a future weight sweep (Stage 5 of
the plan) can vary them without touching control flow.

⚠ SINCE THE #533 SEPARATION CHANGE (2026-08-22, OPERATOR-SIGNED) THIS FILE
CARRIES TWO TABLES, AND WHICH ONE ACTS IS ONE RUNTIME FLAG:

- `SCORE_WEIGHTS` (LIVE side, flag ON): the gap ladder is FLAT (every
  qualifying gap = 10 pts) and the conviction floor is trimmed to the single
  gap>=10 + game_changer -> 60 rescue (branch 4). Ships WITH the uniform
  HIGH bar `SEPARATION_BAR` (40) — three coupled parts, one change.
- `SCORE_WEIGHTS_LEGACY` (revert side, flag OFF): the pre-change table,
  byte-identical to what `_score_ep` computed before 2026-08-22 — proven by
  `tests/test_ep_score_stage2_refactor.py`, which pins `_score_ep`'s outputs
  across a boundary sweep captured from the pre-refactor code and re-asserts
  them against the LEGACY table (the revert flag restores exactly the old
  scoring).

THE ONE REVERT FLAG: `ep_score_separation` runtime toggle /
`EP_SCORE_SEPARATION_ENABLED` env, default ON — read once per scan tick in
`run_ep_scan` via `db.get_runtime_toggle` (the catalyst_tier_lattice
pattern; instant no-redeploy revert, ~60s cache lag). OFF -> the LEGACY
table + the per-regime bar (65/70/75/80, regime.py) act — all three parts
revert together. `resolve_score_weights` / `resolve_ep_bar` below are the
ONLY switch points. Operator sign-off + evidence:
docs/setups/magna53_ep.md change log 2026-08-22 +
docs/analysis/score_separation_533_2026-08-22.md. Any further criterion
change: CHANGE_PROCESS + operator sign-off (THE LINE).

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
    # Gap magnitude — FLAT since #533 (2026-08-22, operator-signed): a
    # qualifying gap is ADMISSION EVIDENCE, not ranking points. The old
    # 25/20/15/10 ladder paid gap SIZE, and gap size runs BACKWARDS on real
    # EPs (AUC 0.34; real EPs' median gap is 9.9% vs ordinary gappers' 12%+)
    # — 30 of an ordinary HIGH's raw points came from this ladder. Flat 10 =
    # the modal real EP's gap credit. The 8% cut matches the old lowest tier:
    # WHAT qualifies is unchanged, what a bigger gap PAYS is.
    # Evidence: docs/analysis/score_separation_533_2026-08-22.md Result 3.
    "gap": {
        "tiers": [
            (8, 10),
        ],
        "default": 0,
        "source": "flat-10, #533 separation change, operator-signed "
                   "2026-08-22 (score_separation_533_2026-08-22.md); the "
                   "old 25/20/15/10 ladder lives in SCORE_WEIGHTS_LEGACY",
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

    # Conviction floor — TRIMMED to the single branch-4 rescue by #533
    # (2026-08-22, operator-signed). Branches 1-3 (15%+gc->80, 20%+strong->80,
    # 15%+strong->70) were built 2026-03-20 (77179405/63eda07a) explicitly so
    # a 20% gapper scores >=70 on its own — the back door that kept paying gap
    # size after the ladder flattened: they bound on 28% of ordinary
    # admissible gappers vs 8% of real EPs (mean lift +9.9 vs +2.1 pts), and
    # 93% of ordinary HIGHs needed a floor to clear their bar. DELETED.
    # ⚠ Branch 4 (gap>=10 + game_changer -> 60) SURVIVES BY DESIGN: added
    # 2026-04-14 (ed3e514e) as the scoring-dead-zone fix FOR a real EP (BE),
    # and it is what fires MRNA HIGH at its operational 10% gap read
    # (floor 60 x1.2 Bull = 72). Deleting it too gains 0.008 AUC and re-kills
    # the reference EP — pinned by tests/test_533_separation_flip.py.
    # Evidence: docs/analysis/score_separation_533_2026-08-22.md Results 2+6.
    "conviction_floor": {
        "rules": [
            {"min_gap": 10, "catalyst": "game_changer", "floor": 60},
        ],
        "source": "branches 1-3 deleted, #533 separation change, operator-"
                   "signed 2026-08-22; branch 4 kept (ed3e514e 2026-04-14, "
                   "the dead-zone fix for a real EP — the MRNA guard case); "
                   "the full old chain lives in SCORE_WEIGHTS_LEGACY",
    },
}


# ─── #533 SEPARATION — the revert side + the only switch points (2026-08-22) ───
#
# SCORE_WEIGHTS_LEGACY is the flag-OFF side: byte-identical to the pre-change
# rubric (pinned by the stage-2 boundary-sweep baseline —
# tests/test_ep_score_stage2_refactor.py re-asserts all 69 captured cases
# against it). Only the two components the operator-signed separation change
# touched differ; every other component is the SAME dict object as the live
# table (read-only at runtime — sharing keeps the two sides from drifting on
# components the change never ruled on).

SCORE_WEIGHTS_LEGACY = {
    **SCORE_WEIGHTS,
    # Pre-2026-08-22 gap ladder: paid gap size 25/20/15/10 at 20/15/10/8%
    # (tier cuts from commit 77179405, 2026-03-20).
    "gap": {
        "tiers": [
            (20, 25),
            (15, 20),
            (10, 15),
            (8, 10),
        ],
        "default": 0,
        "source": "pre-#533 ladder (77179405, 2026-03-20) — the "
                   "ep_score_separation revert side",
    },
    # Pre-2026-08-22 floor chain: all four rules, first match wins (order is
    # precedence). Rules 1-3: 77179405 + 63eda07a (2026-03-20). Rule 4:
    # ed3e514e (2026-04-14, the BE dead-zone fix).
    "conviction_floor": {
        "rules": [
            {"min_gap": 15, "catalyst": "game_changer", "floor": 80},
            {"min_gap": 20, "catalyst": "strong", "floor": 80},
            {"min_gap": 15, "catalyst": "strong", "floor": 70},
            {"min_gap": 10, "catalyst": "game_changer", "floor": 60},
        ],
        "source": "pre-#533 chain (77179405 + 63eda07a 2026-03-20; ed3e514e "
                   "2026-04-14) — the ep_score_separation revert side",
    },
}

# The uniform HIGH bar that ships WITH the flat ladder + trimmed floor — the
# three parts are ONE change and revert together on the one flag. 40 was
# picked because it is the ONLY setting that holds today's alert volume
# (1.78 modeled HIGH/day vs 1.81 today; about one FEWER alert a month) while
# making all 18 floor-alive real EPs reachable at a top catalyst grade — and
# it is ONE number to change if the operator wants fewer alerts (45 cuts
# alerts ~55%, 50 cuts ~77%: the priced table,
# docs/analysis/score_separation_533_2026-08-22.md Result 5). While the flag
# is ON this replaces the per-regime 65/70/75/80 (regime.py — untouched, the
# revert side). The separate score<50 MODERATE cutline was NOT ruled on and
# is unchanged on both sides.
SEPARATION_BAR = 40


def resolve_score_weights(separation_enabled: bool) -> dict:
    """Which weight table ACTS this scan tick: the separation table (flag ON)
    or the legacy pre-2026-08-22 revert side. The ONLY weight switch point."""
    return SCORE_WEIGHTS if separation_enabled else SCORE_WEIGHTS_LEGACY


def resolve_ep_bar(separation_enabled: bool, regime_ep_threshold: int) -> int:
    """Which HIGH bar ACTS this scan tick: the uniform SEPARATION_BAR (flag
    ON) or the per-regime bar from the regime row (flag OFF: 65/70/75/80).
    The ONLY bar switch point. The score<50 MODERATE cutline is separate and
    unchanged on both sides."""
    return SEPARATION_BAR if separation_enabled else regime_ep_threshold
