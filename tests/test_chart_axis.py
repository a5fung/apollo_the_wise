"""#343 chart-vision SHADOW — pins for the shared chart_axis core (operator-approved 6/18).

Complements test_chart_axis_grade.py (which pins grade_holistic's append + byte-identical live
path). Here:
  1. modal_stable — the judge noise-floor gate (stable iff all replicates return the SAME non-None
     tier);
  2. grade_b_c — the B(text-only) vs C(+chart) compare core: visual_changed is True ONLY when both
     arms are stable AND differ; an unstable arm or a fully-failed (None) arm never reports a delta;
  3. NOTE PIN (advisor 6/18) — the candidate notes the operator labels must keep the 5-factor body
     byte-identical across arms B/C (only the framing + the attached image differ), so the shadow's
     future deltas stay comparable to the eval's existing 2/2 operator labels.
"""
import asyncio
from unittest.mock import AsyncMock, patch

from agents.market_intelligence import chart_axis as ca
from agents.market_intelligence.chart_axis import (
    CHART_AXIS_NOTE, CHART_AXIS_NOTE_TEXT_ONLY, _AXIS_LEAD, _CHART_FACTORS, modal_stable,
)


# ── 1. modal_stable ───────────────────────────────────────────────────────────────────────────
def test_modal_stable_all_same():
    modal, stable, tiers = modal_stable([{"tier": "HIGH"}] * 3)
    assert (modal, stable, tiers) == ("HIGH", True, ["HIGH", "HIGH", "HIGH"])


def test_modal_stable_mixed_is_unstable():
    modal, stable, _ = modal_stable([{"tier": "HIGH"}, {"tier": "MODERATE"}, {"tier": "HIGH"}])
    assert stable is False
    assert modal == "HIGH"  # still reports the most-common for display, but stable=False


def test_modal_stable_with_none_is_unstable():
    _, stable, tiers = modal_stable([{"tier": "HIGH"}, None, {"tier": "HIGH"}])
    assert stable is False
    assert tiers == ["HIGH", None, "HIGH"]


def test_modal_stable_all_none():
    modal, stable, _ = modal_stable([None, None, None])
    assert modal is None and stable is False


# ── 2. grade_b_c compare core ───────────────────────────────────────────────────────────────────
def _verdict(tier):
    return None if tier is None else {
        "tier": tier, "rationale": f"r-{tier}", "direction_vs_floor": "hold"}


def _run_b_c(b_tiers, c_tiers, png=b"\x89PNG"):
    """Drive grade_b_c with grade_holistic mocked: arm C is detected by image_png being set, arm B
    by image_png=None — each pops the next canned tier for its arm. Order within an arm's gather is
    irrelevant (modal_stable is set-based)."""
    bq, cq = list(b_tiers), list(c_tiers)

    async def _fake(client, payload, *, timeout=None, image_png=None, chart_note=None, **rest):
        return _verdict((cq if image_png is not None else bq).pop(0))

    sem = asyncio.Semaphore(3)
    with patch.object(ca, "grade_holistic", new=AsyncMock(side_effect=_fake)):
        return asyncio.run(ca.grade_b_c(object(), sem, {"ticker": "X"}, png, replicates=3,
                                        log_caller="chart_axis_shadow"))


def test_grade_b_c_stable_and_differ_is_a_delta():
    r = _run_b_c(["HIGH"] * 3, ["MODERATE"] * 3)
    assert r["b_modal"] == "HIGH" and r["c_modal"] == "MODERATE"
    assert r["both_stable"] is True
    assert r["visual_changed"] is True


def test_grade_b_c_stable_and_same_is_no_delta():
    r = _run_b_c(["HIGH"] * 3, ["HIGH"] * 3)
    assert r["both_stable"] is True
    assert r["visual_changed"] is False


def test_grade_b_c_unstable_arm_is_never_a_delta():
    r = _run_b_c(["HIGH"] * 3, ["HIGH", "MODERATE", "HIGH"])  # C flips → noise, not a chart effect
    assert r["both_stable"] is False
    assert r["visual_changed"] is False


def test_grade_b_c_failed_arm_yields_none_verdict_for_retry():
    r = _run_b_c([None] * 3, ["HIGH"] * 3)  # arm B fully failed (API) → caller leaves no marker
    assert r["b_verdict"] is None
    assert r["visual_changed"] is False


# ── 3. NOTE PIN — body byte-identical, only the framing + image differ ───────────────────────────
_FACTOR_LEADS = ("Prior trend & leadership", "Base quality", "Volume",
                 "Location vs the MA stack", "Over-extension / climax")


def test_both_notes_share_the_exact_factor_body():
    # The 5-factor body + the lead sentence are the SAME bytes in both arms — only the header /
    # "chart attached" framing differs. This is what makes a B/C verdict delta a pure modality test.
    assert CHART_AXIS_NOTE.endswith(_CHART_FACTORS)
    assert CHART_AXIS_NOTE_TEXT_ONLY.endswith(_CHART_FACTORS)
    assert _AXIS_LEAD in CHART_AXIS_NOTE
    assert _AXIS_LEAD in CHART_AXIS_NOTE_TEXT_ONLY
    for lead in _FACTOR_LEADS:
        assert lead in _CHART_FACTORS


def test_only_the_chart_arm_claims_an_attached_image():
    assert "chart is attached" in CHART_AXIS_NOTE and "Read the chart." in CHART_AXIS_NOTE
    # the text-only arm must NOT reference an attached chart (would be a lie with no PNG sent)
    assert "no chart attached" in CHART_AXIS_NOTE_TEXT_ONLY
    assert "chart is attached" not in CHART_AXIS_NOTE_TEXT_ONLY
