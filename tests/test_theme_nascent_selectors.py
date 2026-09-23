"""ADR 0007 (a)/(a2) nascent-discovery selector predicates.

Pure-logic tests for the candidate-selection predicates, grounded in the 2026-05-31
read-only replay (drone 5/26->5/28 ranks + software 5/29 rs_1m/rs_6m). The DB wrappers
(get_rs_accelerators / get_rs_recovery_slope) are verified Monday on the server (no
local DB); these pin the threshold LOGIC + the two lessons the replay taught.
"""
from agents.market_intelligence.db import _is_rank_accelerator, _is_recovery_slope


# ── (a) rank accelerator — grounded in the 5/28 drone ignition ──────────────────
def test_rcat_passes_despite_sub60_rs():
    # RCAT 5/26->5/28: rank 3751->1619 (improve 2132), rs_composite 5.3->59.4
    assert _is_rank_accelerator(1619, 3751, 59.4, 5.3) is True  # default floor 50


def test_rs60_floor_would_wrongly_drop_rcat():
    # The bug the advisor caught: a >=60 floor excludes RCAT (59.4) — a name we traded.
    assert _is_rank_accelerator(1619, 3751, 59.4, 5.3, min_rs_now=60.0) is False


def test_umac_and_onds_accelerate():
    assert _is_rank_accelerator(50, 933, 98.8, 76.5) is True     # UMAC improve 883
    assert _is_rank_accelerator(412, 2772, 89.7, 30.0) is True   # ONDS improve 2360


def test_declining_laggard_rejected():
    # KYTX 5/28: rank 3228 (was 2717 -> declining), rs 19 (<50) — the dead fragment weight
    assert _is_rank_accelerator(3228, 2717, 19.0, 31.4) is False


def test_rs_jump_arm_is_independent_of_rank():
    # flat rank but rs jumped 40->70 (delta 30 >= 25) -> the OR arm fires
    assert _is_rank_accelerator(500, 520, 70.0, 40.0) is True


def test_below_floor_always_false():
    # huge rank move but rs_now below the floor -> rejected
    assert _is_rank_accelerator(10, 9999, 49.0, 1.0) is False


def test_none_safe():
    assert _is_rank_accelerator(None, None, None, None) is False


# ── (a2) recovery slope — grounded in the 5/29 software snapshot ────────────────
def test_recovering_software_caught():
    assert _is_recovery_slope(95, 28) is True   # ESTC
    assert _is_recovery_slope(92, 17) is True   # TEAM
    assert _is_recovery_slope(91, 5) is True    # MNDY


def test_established_software_excluded():
    # high rs_6m = already established, NOT recovering -> needs narrative layer (e), not this
    assert _is_recovery_slope(98, 94) is False  # CRWD
    assert _is_recovery_slope(95, 97) is False  # DDOG


def test_headline_defaults_clip_two_core_names_tuning_signal():
    # The 5/31 replay's headline thresholds (rs_1m>=90 AND rs_6m<=30) sit JUST outside
    # two flagship software names — a real shadow-lane tuning point, not a bug:
    #   NOW  rs_1m 97 / rs_6m 33  -> rs_6m just over 30
    #   MDB  rs_1m 88 / rs_6m 20  -> rs_1m just under 90
    assert _is_recovery_slope(97, 33) is False                              # NOW @ default
    assert _is_recovery_slope(88, 20) is False                              # MDB @ default
    assert _is_recovery_slope(97, 33, max_rs_6m=40) is True                 # loosen rs_6m -> NOW
    assert _is_recovery_slope(88, 20, min_rs_1m=85) is True                 # loosen rs_1m -> MDB
    # both caught together at the looser pair (the likely tuned setting)
    assert _is_recovery_slope(97, 33, min_rs_1m=85, max_rs_6m=40) is True
    assert _is_recovery_slope(88, 20, min_rs_1m=85, max_rs_6m=40) is True


def test_recovery_none_safe():
    assert _is_recovery_slope(None, 10) is False
    assert _is_recovery_slope(95, None) is False
