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
  HIGH bar `SEPARATION_BAR` — three coupled parts, one change. Since the
  #533 RESCALE (2026-08-22) the live side also carries `output_scale`
  (presented = 1.25 x raw + 15) and the bar is expressed on that presented
  scale (65 = the old raw 40 mapped through the same function) — a
  presentation change with a proven-identical alerting set, see
  `apply_output_scale` below.
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
SINCE 2026-08-22 (the SHORTLIST PRE-SCORE flip, operator-directed) this file
ALSO carries `SHORTLIST_WEIGHTS` — the second table the plan promised: the
shortlist answers "who is worth paying to grade", the score answers "how good
is it". Both tables live in this one file so they cannot drift into two
conventions. See the SHORTLIST section at the bottom of the module.
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


def apply_output_scale(final_score: float, scale: dict | None) -> float:
    """#533 RESCALE (2026-08-22) — the ONE presentation transform.

    presented = round(mult x final + offset, 1), applied to the ALREADY-ROUNDED
    final score (raw x regime multiplier, 1 decimal) as the LAST step of
    `_score_ep`. `scale` is `weights["output_scale"]` — a dict on the
    separation table, None on the legacy table (no-op).

    WHY THIS CANNOT CHANGE WHAT ALERTS (the order-of-operations proof):
    - It sits AFTER the conviction floor (which forces a raw value BEFORE the
      regime multiplier) and AFTER the multiplier — so it acts on the single
      final number, whatever branch produced it. An affine map with mult > 0
      is strictly increasing: s1 >= s2 <-> T(s1) >= T(s2), floor-forced or not.
    - The bar goes through the SAME function (SEPARATION_BAR = T(40) = 65), so
      `score >= bar` is decided identically on either scale.
    - Rounding cannot flip the boundary: the input is already rounded to one
      decimal, so with mult=1.25 (exactly 5/4 in binary) the largest sub-bar
      input 39.9 maps to 64.875 -> rounds to 64.9 < 65, while 40.0 maps to
      exactly 65.0. Pinned exhaustively by tests/test_533_rescale_invariant.py.

    WHY: the separation change made the score's ORDERING right but left the
    NUMBERS unreadable — every score fell, the bar dropped to 40 (below the
    legacy 50 cutline), and the bands went incoherent. Operator: "the proper
    fix ... is to increase score of EPs, lower score of non EPs and keep bar
    at reasonable level". This transform does exactly that without touching a
    single weight: on the measured #533 corpus, graded real EPs present
    ~67-105 (the four alerting @known members: 67.5 / 67.5 / 90 / 105),
    routine-graded ordinary gappers present ~30-52 (median 40.5), the
    observable scale floor (a qualifying gap and nothing else) is 27.5, and
    the bar returns to a round 65. Weights, tier cuts, and the raw bar (40)
    are untouched in raw terms — ordering and the alerting set are preserved
    by construction and proven by test.
    """
    if not scale:
        return final_score
    return round(final_score * scale["mult"] + scale["offset"], 1)


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

    # Output scale — #533 RESCALE (2026-08-22): PRESENTATION ONLY, applied by
    # `apply_output_scale` as the last step of `_score_ep`. NOT a component:
    # it adds no points and re-weights nothing — a single strictly-increasing
    # affine map on the final score, with the bar (SEPARATION_BAR) expressed
    # through the same function, so the alerting set is unchanged by
    # construction (proof + measured distributions: apply_output_scale
    # docstring; identical-alert-set test: test_533_rescale_invariant.py).
    # mult=1.25 is exactly 5/4 (binary-exact — the rounding proof depends on
    # it); offset=15. Chosen on the measured #533 corpus so real EPs present
    # ~67-105, routine ordinary gappers ~30-52, bar = a round 65.
    "output_scale": {
        "mult": 1.25,
        "offset": 15,
        "source": "#533 rescale 2026-08-22 — presentation transform, "
                   "alerting set proven identical "
                   "(tests/test_533_rescale_invariant.py); legacy side is "
                   "None (old raw scale, byte-identical revert)",
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
    # No output transform on the revert side — flag OFF must present the OLD
    # RAW SCALE byte-identically (the 69-case stage-2 baseline pins it).
    # Explicit None: without this override the {**SCORE_WEIGHTS} spread would
    # silently inherit the live side's transform.
    "output_scale": None,
}

# The uniform HIGH bar that ships WITH the flat ladder + trimmed floor — the
# three parts are ONE change and revert together on the one flag. The bar is
# RAW 40, picked because it is the ONLY setting that holds today's alert
# volume (1.78 modeled HIGH/day vs 1.81 today; about one FEWER alert a month)
# while making all 18 floor-alive real EPs reachable at a top catalyst grade
# (45 cuts alerts ~55%, 50 cuts ~77%: the priced table,
# docs/analysis/score_separation_533_2026-08-22.md Result 5). Since the #533
# RESCALE (2026-08-22) the bar is EXPRESSED on the presented scale — 65 is
# exactly the raw 40 mapped through the live table's output_scale
# (1.25 x 40 + 15); the raw policy did NOT move, only its numeric expression
# (the constant below and the raw anchor are cross-pinned by
# tests/test_533_rescale_invariant.py). If the operator wants fewer alerts
# the raw 45/50 rows present as 71.25/77.5 — set the bar via
# SEPARATION_BAR_RAW and this derives. While the flag is ON this replaces the
# per-regime 65/70/75/80 (regime.py — untouched, the revert side; the
# numeric coincidence with Bull's 65 is just that — different scales).
SEPARATION_BAR_RAW = 40
SEPARATION_BAR = 65  # int (mi_ep_score_shadow.sep_bar is INT); derivation pinned:
assert SEPARATION_BAR == apply_output_scale(
    float(SEPARATION_BAR_RAW), SCORE_WEIGHTS["output_scale"]
), "SEPARATION_BAR must be exactly the raw bar through the live output_scale"

# The MODERATE cutline, per side (#533 rescale, 2026-08-22). Legacy (flag
# OFF): the historical score>=50 briefing band under the per-regime bars —
# byte-identical revert. Separation (flag ON): None — NO MODERATE band. The
# old 50 was left over from the old scale and sat ABOVE the bar (40), so the
# band was already EMPTY every day; None states that honestly instead of
# keeping a dead number ("it goes" rather than presenting as 77.5 — behaviour
# is identical either way, proven in test_533_rescale_invariant.py).
# ⚠ Re-arming a MODERATE band on the presented scale (e.g. [50, 65)) is NOT a
# presentation change: it would create a new briefing population AND re-arm
# the earnings-day MODERATE->HIGH override on names that today skip silently
# (~2.3/day on the #533 corpus) — a detection-criteria change, operator-only.
LEGACY_MODERATE_CUTLINE = 50


def resolve_score_weights(separation_enabled: bool) -> dict:
    """Which weight table ACTS this scan tick: the separation table (flag ON)
    or the legacy pre-2026-08-22 revert side. The ONLY weight switch point."""
    return SCORE_WEIGHTS if separation_enabled else SCORE_WEIGHTS_LEGACY


def resolve_ep_bar(separation_enabled: bool, regime_ep_threshold: int) -> float | int:
    """Which HIGH bar ACTS this scan tick: the uniform SEPARATION_BAR (flag
    ON, presented scale) or the per-regime bar from the regime row (flag OFF:
    65/70/75/80 on the old raw scale). The ONLY bar switch point. Each bar is
    on the same scale as the scores the matching weight table produces."""
    return SEPARATION_BAR if separation_enabled else regime_ep_threshold


def resolve_moderate_cutline(separation_enabled: bool) -> int | None:
    """Which MODERATE cutline ACTS this scan tick: None while separation is ON
    (no MODERATE band — the legacy 50 was dead letter below-the-bar anyway) or
    the historical 50 on the revert side. The ONLY cutline switch point."""
    return None if separation_enabled else LEGACY_MODERATE_CUTLINE


# ═══ SHORTLIST PRE-SCORE — who is worth paying to GRADE (2026-08-22, operator-directed) ═══
#
# WHY: `run_ep_scan` grades only the top `SHORTLIST_SIZE` candidates each tick (the
# LLM/FMP budget), and until 2026-08-22 that shortlist was ordered by GAP SIZE — the
# exact measure the same-day separation change deleted from the score for running
# BACKWARDS on real EPs (AUC 0.34). Operator, on finding gap still deciding who gets
# looked at: "how are we still using it after all this work… that's like saying this
# is completely wrong for weeks and fixing it for weeks and then say we still use it."
# The pre-score replaces gap as the shortlist sort key (`ep_shortlist_prescore`
# runtime toggle in run_ep_scan, default ON — OFF restores gap ordering exactly).
#
# HONEST SCOPE (Stage 0, docs/analysis/shortlist_survival_stage0_2026-08-22.md):
# re-ranking recovers AT MOST ONE of the 16 cap-attributed real EPs to a possible
# entry (SNOW 05-07, conditional on an ungraded catalyst) — the wall behind the cap
# is the score bar, not the cap. The justification is COHERENCE (a measure proven
# backwards must not decide who is looked at) and FUTURE-PROOFING (#584-class
# admission widening pushes more names into the same slots), NOT retention recovery.
# What it demonstrably improves: the liquidity axis ranks all five of the killed
# set's biggest R-winners (MU/SNDK/BE/ARM/SNOW) inside the top 20, where gap ranked
# them 20th to 100th+.
#
# ONLY THREE TERMS, deliberately. `extension`, `prior_3m`, `adv_trend` and
# `cooldown_proximity` stay OUT: the prior-momentum penalty was DELETED the same day
# for firing on real EPs and junk at identical rates (31% vs 32%), extension's
# unique kills are 15 rows in four months and 91% redundant with ADV/ATR/mcap, and
# the other two are wholly unmeasured. Adding them would re-import noise. A term
# enters this table only with a measured direction against the real-EP set.
# Excluded because they cost money per name: float, market cap, pm_rvol, catalyst.

SHORTLIST_WEIGHTS = {
    # component:   (max_points, weight)
    "liquidity":   (15, 3),   # 45 of 65 — deliberately dominant; ex-ante 20d ADV$ AUC 0.72
    "gap":         (10, 1),   # 10 of 65 — FLAT: presence, not magnitude (gap size AUC 0.34)
    "theme_bonus": (10, 1),   # 10 of 65 — mirrors the live score's R4 in-theme bonus
}
# Max points mirror the live score's values so the two tables stay legible side by
# side; the WEIGHTS are what encode the measured separation. A defensible starting
# point, NOT a fitted one — the Stage-5 sweep harness exists to tune them.
SHORTLIST_MAX_COMPOSITE = sum(mx * w for mx, w in SHORTLIST_WEIGHTS.values())
assert SHORTLIST_MAX_COMPOSITE == 65, "the shortlist table's documented scale"

# The ADV$ ladder for the liquidity axis. Values mirror the live score's
# SCORE_WEIGHTS["liquidity"]["adv_tiers"] as of 2026-08-22 (AUC 0.72 evidence:
# docs/analysis/score_redesign_proposal_533_2026-08-22.md) — deliberately its OWN
# constant, NOT a reference to that dict, so a future sweep can tune the shortlist
# without silently moving the score, and vice versa.
SHORTLIST_LIQUIDITY_TIERS: list[tuple[float, int]] = [
    (500_000_000, 15),
    (250_000_000, 12),
    (100_000_000, 10),
    (50_000_000, 7),
]

# How many candidates get GRADED each tick (the LLM/FMP budget) — the shortlist
# cap `run_ep_scan` applies after the sort. Cohort-shaping: registered in
# scripts/gate_provenance_registry.py (the MIN_PREV_CLOSE / EP_COOLDOWN_DAYS /
# MAX_EXTENSION_PCT class). Named 2026-08-22, replacing three bare `20` literals.
SHORTLIST_SIZE = 20


def shortlist_prescore(
    *,
    adv_dollar: "float | None",
    gap_pct: "float | None",
    in_active_theme: bool,
) -> dict:
    """The cheap pre-grading composite for ONE candidate — free inputs only.

    Missing-input handling reuses `catalyst_rubric.composite_with_scaling`'s
    shape (weighted sum of the AVAILABLE axes, rescaled to the full
    MAX_COMPOSITE by the available maximum): an unknown input must never
    silently sink a candidate (P1 — a false exclusion is invisible), the same
    contract as the score's liquidity fallback and `_check_adv_dollar_volume`.

    - `adv_dollar` = 20-day ADV shares × prev_close, or None when no REAL ADV
      exists at sort time (`adv_source == "pending"` — the prevDay.v placeholder
      must NOT be scored as liquidity evidence). None → the liquidity axis is
      missing and the composite rescales from gap + theme.
    - `gap_pct` — FLAT: any qualifying gap earns full points (every candidate at
      the sort has already passed the acting gap floor). Presence, not
      magnitude. None → axis missing (defensive; cannot happen live).
    - `in_active_theme` is always decidable (in the Accelerating/Mainstream set
      or not), so the theme axis is never "missing" — 0 is a real reading.

    Returns {"composite", "raw", "max_available"} — composite on the 0..65
    scale. Pure, no I/O.
    """
    raw: dict[str, "int | None"] = {
        "liquidity": (None if adv_dollar is None
                      else tier_points(adv_dollar, SHORTLIST_LIQUIDITY_TIERS)),
        "gap": None if gap_pct is None else SHORTLIST_WEIGHTS["gap"][0],
        "theme_bonus": SHORTLIST_WEIGHTS["theme_bonus"][0] if in_active_theme else 0,
    }
    available = [k for k, v in raw.items() if v is not None]
    if not available:
        return {"composite": 0.0, "raw": raw, "max_available": 0}
    weighted = sum(raw[k] * SHORTLIST_WEIGHTS[k][1] for k in available)
    max_available = sum(
        SHORTLIST_WEIGHTS[k][0] * SHORTLIST_WEIGHTS[k][1] for k in available)
    composite = weighted * SHORTLIST_MAX_COMPOSITE / max(1, max_available)
    return {"composite": round(composite, 2), "raw": raw,
            "max_available": max_available}


def shortlist_sort_key(
    ticker: str, composite: float, adv_dollar: "float | None",
) -> tuple:
    """The TOTAL ORDER the shortlist ranks by — composite desc, then the
    TIE-BREAK. Stage 0 measured a 9-way tie at the rank-20 cut on the 04-08
    flood board (the bucketed composite is coarse), so the boundary would be
    an arbitrary lottery without one. Policy, in order:

    1. composite DESC — the three-term pre-score.
    2. continuous ADV$ DESC — the SAME measured axis (AUC 0.72) at full
       resolution, not a new term: within a tie, the more liquid name gets the
       grading slot. Chosen over gap (would re-import the proven-backwards
       key exactly at the margin) and over any unmeasured term. Tick-stable —
       ADV$ is fixed the night before, so the boundary cannot churn between
       ticks. Unknown-ADV names (None → 0 here) lose ties to names whose
       liquidity is verified — within a tie, evidence beats absence.
    3. ticker ASC — final determinism guarantee: identical runs produce
       identical ranks, replays reproduce the live order exactly.
    """
    return (-composite, -(adv_dollar or 0.0), ticker)
