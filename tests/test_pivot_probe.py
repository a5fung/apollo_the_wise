"""`scripts/probes/_491/pivot_probe.py` — the #491 pivot-migration probe's PURE parts.

The probe runs ONCE against prod (piped into the market container, read-only) to put numbers under
the #491 proposal (docs/analysis/491_pivot_migration_proposal_2026-10-03.md), so the decisions it
makes without the DB must be right before that run: the recommendation's gate ORDER
(`rehome_verdict`), the leave trigger on #655 G2's signed shape including the unjudgeable-home arm
(`g2_trigger`), the RS-pool boundary (`in_pool`), the board idiom (`latest_per_name`), the declared
pivot stems, the whole-word audit regex and the cost arithmetic. No DB, no network, no model calls.

Loaded through importlib (the `_580` probe-test idiom): the module lives under scripts/probes/, which
is not a package, and its heavy imports (theme_engine, db) sit INSIDE main() so loading it here pulls
nothing from the live stack.
"""
from __future__ import annotations

import importlib.util
import sys
from datetime import date
from pathlib import Path

import pytest

_PATH = Path(__file__).resolve().parent.parent / "scripts" / "probes" / "_491" / "pivot_probe.py"
_spec = importlib.util.spec_from_file_location("pivot_probe_491", _PATH)
pp = importlib.util.module_from_spec(_spec)
# registered BEFORE exec: the probe's frozen dataclass resolves its postponed annotations through
# sys.modules[cls.__module__], which is None for an unregistered spec-loaded module (Python 3.14)
sys.modules[_spec.name] = pp
_spec.loader.exec_module(pp)


def _base(**over):
    base = dict(covered=False, source_theme=None, target_theme="AI Compute", target_stage="Mainstream",
                target_corr=0.6, target_reason="comoves", own_corr=None, own_reason=None,
                excluded=False, protected_at_source=False, cooldown_to_target=False,
                seeded_in_window=False, orphan_age=None, pool_ok=False)
    base.update(over)
    return base


# ─── selftest + declared constants ─────────────────────────────────────────────────────────────

def test_selftest_passes(capsys):
    assert pp.selftest() == 0


def test_declared_constants_match_the_signed_bars():
    """The probe judges on the engine's signed numbers; a drift here would make its verdicts about
    a different rule than the one that runs (main() re-checks against the live module at run time)."""
    assert pp.COMOVE_BAR == 0.35
    assert pp.G2_MARGIN == 0.20
    assert (pp.POOL_FLOOR, pp.POOL_CEILING) == (70.0, 600)
    assert pp.LANE2_WINDOW_TRADING_DAYS == 10
    assert pp.PAYING_STAGES == ("Accelerating", "Mainstream")
    assert pp.COHORT == ("CIFR", "HUT", "CRWV", "IREN", "WULF", "CORZ", "CLSK", "APLD")


# ─── pivot stems (the GENERALIZE sweep's trigger, declared before the run) ─────────────────────

@pytest.mark.parametrize("text,want", [
    ("Bitcoin Miners Pivoting to AI/HPC Data Center Hosting", ["pivot"]),
    ("Emerging Bitcoin Miners Diversifying into AI/HPC Hosting", ["diversif"]),
    ("Crypto Miners Pivoting to Data Center Colocation — repurposing power", ["pivot", "repurpos"]),
    ("Bitcoin Miner to AI/HPC Data Center Conversion", ["conversion"]),
    ("Crypto miners converting power to AI compute", ["convert"]),
    ("Energy transition beneficiaries", ["transition"]),
    ("Crude & Product Tanker Shipping", []),
    (None, []),
])
def test_pivot_stems(text, want):
    assert pp.pivot_stems_in(text) == want


# ─── the leave trigger (#655 G2 shape + the unjudgeable-home arm) ──────────────────────────────

def test_g2_fires_when_misfiled_on_the_signed_margin():
    assert pp.g2_trigger(0.20, "below_bar", 0.60) == (True, "g2_misfiled")
    # exactly own + 0.20 with other at the bar: fires (>= on both)
    assert pp.g2_trigger(0.15, "below_bar", 0.35) == (True, "g2_misfiled")


def test_g2_does_not_fire_on_a_name_that_moves_with_its_own_theme():
    # the miners move together at 0.7-0.8 — a cohesive home is never a leave trigger
    assert pp.g2_trigger(0.80, "comoves", 0.65) == (False, "own_at_or_above_bar")
    assert pp.g2_trigger(0.35, "comoves", 0.90) == (False, "own_at_or_above_bar")


def test_g2_margin_not_met():
    assert pp.g2_trigger(0.20, "below_bar", 0.39) == (False, "margin_not_met")


def test_g2_unjudgeable_home_is_its_own_arm():
    """Tonight's headline case: the pivot theme has 2 members -> leave-one-out basket of 1 ->
    the engine reads `thin_basket`. A trigger needing a judgeable own tie would miss CIFR/HUT
    exactly as IREN/BTDR was missed on 2026-09-08 — so the arm is explicit and named (fork D3)."""
    assert pp.g2_trigger(None, "thin_basket", 0.60) == (True, "own_unjudgeable:thin_basket")
    assert pp.g2_trigger(None, None, 0.60) == (True, "own_unjudgeable:unknown")


def test_g2_never_fires_without_a_target_at_or_above_the_bar():
    assert pp.g2_trigger(None, "thin_basket", 0.30) == (False, "other_below_bar")
    assert pp.g2_trigger(0.10, "below_bar", None) == (False, "other_unjudgeable")


# ─── the RS-floor pool ──────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("rs,rank,want", [
    (70.0, 300, True), (69.99, 1, False), (90.0, 600, True), (90.0, 601, False),
    (90.0, None, True), (None, 5, None),
])
def test_in_pool_boundaries(rs, rank, want):
    assert pp.in_pool(rs, rank)[0] is want


def test_in_pool_rank_is_labelled_approximate():
    assert "approx" in pp.in_pool(90.0, 601)[1]


# ─── the recommendation's gate order ───────────────────────────────────────────────────────────

def test_exclusion_beats_every_other_gate():
    v = pp.rehome_verdict(**_base(excluded=True, covered=True, source_theme="P", own_reason="thin_basket",
                                  cooldown_to_target=True, target_stage="Fading"))
    assert v.verdict == "REJECT" and v.gate.startswith("operator exclusion")


def test_operator_protection_on_the_current_home_blocks_a_move():
    v = pp.rehome_verdict(**_base(covered=True, source_theme="P", protected_at_source=True, own_reason="thin_basket"))
    assert v.verdict == "REJECT" and "operator protection" in v.gate


def test_protection_is_only_read_for_a_covered_name():
    # an uncovered orphan carries no 'current home' to protect — the flag is inert
    v = pp.rehome_verdict(**_base(protected_at_source=True, orphan_age=2))
    assert v.verdict == "OFFER"


def test_never_into_a_fading_theme():
    v = pp.rehome_verdict(**_base(target_stage="Fading", orphan_age=2))
    assert v.verdict == "REJECT" and "Fading" in v.gate


def test_live_pair_cooldown_to_the_target_blocks():
    v = pp.rehome_verdict(**_base(cooldown_to_target=True, orphan_age=2))
    assert v.verdict == "REJECT" and "cooldown" in v.gate


def test_covered_name_needs_the_leave_trigger():
    stays = pp.rehome_verdict(**_base(covered=True, source_theme="P", own_corr=0.80, own_reason="comoves"))
    assert stays.verdict == "REJECT" and "leave trigger did not fire" in stays.gate
    leaves = pp.rehome_verdict(**_base(covered=True, source_theme="P", own_corr=None, own_reason="thin_basket"))
    assert leaves.verdict == "OFFER" and leaves.ticket == "covered_g2[own_unjudgeable:thin_basket]"


def test_uncovered_name_needs_an_admission_ticket_in_priority_order():
    assert pp.rehome_verdict(**_base(seeded_in_window=True)).ticket == "seeded"
    assert pp.rehome_verdict(**_base(orphan_age=14)).ticket == "orphan[14d]"      # boundary: 14 passes
    assert pp.rehome_verdict(**_base(orphan_age=15, pool_ok=True)).ticket == "pool"
    none = pp.rehome_verdict(**_base(orphan_age=15, pool_ok=False))
    assert none.verdict == "REJECT" and "no admission ticket" in none.gate
    never = pp.rehome_verdict(**_base(orphan_age=None, pool_ok=None))
    assert never.verdict == "REJECT"


def test_tape_decides_the_proposed_pair_last():
    thin = pp.rehome_verdict(**_base(orphan_age=2, target_corr=None, target_reason="thin_basket"))
    assert thin.verdict == "FALLBACK_SECTOR" and thin.ticket == "orphan[2d]"
    below = pp.rehome_verdict(**_base(orphan_age=2, target_corr=0.34))
    assert below.verdict == "REJECT" and "0.34 < 0.35" in below.gate
    at_bar = pp.rehome_verdict(**_base(orphan_age=2, target_corr=0.35))
    assert at_bar.verdict == "OFFER" and "assignment judgement decides" in at_bar.gate


def test_no_target_is_a_reject_not_a_crash():
    v = pp.rehome_verdict(**_base(target_theme=None, target_stage=None, target_corr=None, orphan_age=1))
    assert v.verdict == "REJECT" and v.ticket is None


# ─── today's path, in plain words ──────────────────────────────────────────────────────────────

def test_today_path_names_the_deciding_rule():
    assert pp.today_path(covered=True, source_themes=["P"], seeded_in_window=True, pool_ok=True).startswith("stays in P")
    assert "M2" in pp.today_path(covered=False, source_themes=[], seeded_in_window=True, pool_ok=False)
    assert "RS pool" in pp.today_path(covered=False, source_themes=[], seeded_in_window=False, pool_ok=True)
    assert "unreachable" in pp.today_path(covered=False, source_themes=[], seeded_in_window=False, pool_ok=False)


# ─── board idiom, orphan age, best-other, regex ────────────────────────────────────────────────

def test_latest_per_name_follows_get_active_themes():
    rows = [
        {"name": "A", "theme_date": date(2026, 10, 1), "stage": "Fading"},
        {"name": "A", "theme_date": date(2026, 10, 2), "stage": "Retired"},     # retired latest -> gone
        {"name": "B", "theme_date": date(2026, 9, 20), "stage": "Mainstream"},  # outside 7 days -> gone
        {"name": "C", "theme_date": date(2026, 9, 30), "stage": "Nascent"},
        {"name": "C", "theme_date": date(2026, 10, 2), "stage": "Fading"},      # latest wins
        {"name": "D", "theme_date": date(2026, 9, 26), "stage": "Mainstream"},  # exactly 7 days back stays
    ]
    out = {r["name"]: r for r in pp.latest_per_name(rows, date(2026, 10, 3))}
    assert set(out) == {"C", "D"}
    assert out["C"]["stage"] == "Fading"


def test_orphan_age():
    assert pp.orphan_age_days(date(2026, 9, 20), date(2026, 10, 3)) == 13
    assert pp.orphan_age_days(None, date(2026, 10, 3)) is None


def test_best_other_theme_skips_own_homes_and_fading():
    ties = {"Own": (0.9, "comoves", "Fading"), "Fade": (0.8, "comoves", "Fading"),
            "Live": (0.5, "comoves", "Mainstream"), "Thin": (None, "thin_basket", "Nascent")}
    assert pp.best_other_theme(ties, {"Own"}) == ("Live", 0.5, "Mainstream")
    assert pp.best_other_theme(ties, {"Own"}, exclude_fading=False) == ("Fade", 0.8, "Fading")


def test_word_regex_is_whole_word():
    import re
    # Postgres \m \M translate to Python \b for the purpose of this check
    pat = re.compile(pp.word_regex("HUT").replace(r"\m", r"\b").replace(r"\M", r"\b"))
    assert pat.search("HUT → 'Bitcoin Miners' admitted")
    assert not pat.search("the theme was shut down")


# ─── pricing arithmetic ────────────────────────────────────────────────────────────────────────

def test_price_candidates_batches_and_zero():
    assert pp.price_candidates(0, 3.0, 15.0, 120) == {"candidates": 0, "batches": 0, "usd_per_night": 0.0}
    p18 = pp.price_candidates(18, 3.0, 15.0, 120)
    p19 = pp.price_candidates(19, 3.0, 15.0, 120)
    assert p18["batches"] == 1 and p19["batches"] == 2
    assert p19["usd_per_night"] > p18["usd_per_night"] > 0
    # output tokens follow the measured fit x the sonnet-5 growth factor, per batch
    assert p18["out_tokens"] == int(3.5 * (274 + 73.4 * 18))


def test_price_fit_preview():
    assert pp.price_fit_preview(8, 3.0, 15.0) == round(8 * (1200 / 1e6 * 3.0 + 250 / 1e6 * 15.0), 4)
