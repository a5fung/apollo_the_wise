"""#416 binding-context guards (operator-signed 7/12, rulings-pack R6) — the three ratified
false-positives must be VETOED via their fire-path guard; the true-positive (SUNE) and genuine
binding deals must still FIRE. Evidence: docs/analysis/416_mna_fp_amendment_2026-07-12.md."""
import pytest

from agents.market_intelligence.ma_filter import (
    mna_context_is_binding,
    keyword_context_is_nonbinding,
    reasoning_is_exploration_only,
    text_implies_acquirer_or_completed,
    is_likely_ma,
)


# ── the shared escape ──────────────────────────────────────────────────────────
def test_binding_marker_is_the_escape():
    assert mna_context_is_binding("announcement of definitive reverse merger with Suniva")  # SUNE (TP)
    assert mna_context_is_binding("XYZ to be acquired by ABC in an all-cash deal")
    assert not mna_context_is_binding("proxy campaign seeking strategic alternatives")  # FRMI
    assert not mna_context_is_binding("takeover speculation after a reported bid")


# ── Guard A · keyword negated / speculative ────────────────────────────────────
def test_guard_a_negated_keyword_vetoes():          # MMED
    txt = "company-specific execution news, not a single dramatic takeover or earnings shock"
    assert keyword_context_is_nonbinding(txt, "takeover") is True

def test_guard_a_speculation_vetoes():              # IMAX / WEN / IMVT
    txt = "gapped up on a potential sale of the company and takeover speculation"
    assert keyword_context_is_nonbinding(txt, "takeover") is True

def test_guard_a_real_binding_deal_not_vetoed():
    txt = "entered a definitive merger agreement to be acquired by ABC in an all-cash buyout"
    assert keyword_context_is_nonbinding(txt, "buyout") is False   # binding escape → keep firing

def test_guard_a_plain_keyword_no_context_not_vetoed():
    assert keyword_context_is_nonbinding("announced a buyout of the company", "buyout") is False


# ── Guard B · polygon Path B exploration ───────────────────────────────────────
def test_guard_b_exploration_vetoes():              # FRMI
    assert reasoning_is_exploration_only(
        "Stock gained 22.6% on proxy campaign announcement seeking strategic alternatives")

def test_guard_b_definitive_not_vetoed():           # SUNE
    assert not reasoning_is_exploration_only(
        "Exploded 150% on announcement of definitive reverse merger with Suniva")

def test_guard_b_plain_merger_not_vetoed():
    assert not reasoning_is_exploration_only("shares jumped on merger news with a rival")


# ── Guard C · classifier acquirer / completed ──────────────────────────────────
def test_guard_c_acquirer_side_vetoes():            # ONDS
    assert text_implies_acquirer_or_completed(
        ["driven by the Mistral acquisition closing, giving Ondas direct prime-contract access"])

def test_guard_c_target_side_not_vetoed():
    assert not text_implies_acquirer_or_completed(
        ["XYZ completed the acquisition talks and is to be acquired by ABC"])   # target-side present

def test_guard_c_no_acquirer_language():
    assert not text_implies_acquirer_or_completed(["strong quarterly earnings beat and raised guidance"])


# ── is_likely_ma orchestration (polygon off, to isolate paths 1+2) ─────────────
@pytest.mark.asyncio
async def test_classifier_acquirer_side_not_suppressed():           # ONDS end-to-end
    is_mna, _ = await is_likely_ma(
        "ONDS", catalyst_quality="mna",
        catalyst_texts=["ONDS gapped on the Mistral acquisition closing, direct prime-contract"],
        check_polygon=False)
    assert is_mna is False

@pytest.mark.asyncio
async def test_negated_keyword_not_suppressed():                    # MMED end-to-end
    is_mna, _ = await is_likely_ma(
        "MMED", catalyst_quality="routine",
        catalyst_texts=["MiniMed rollout news, not a single dramatic takeover or earnings shock"],
        check_polygon=False)
    assert is_mna is False

@pytest.mark.asyncio
async def test_real_binding_keyword_still_fires():
    is_mna, tel = await is_likely_ma(
        "XYZ", catalyst_quality="routine",
        catalyst_texts=["XYZ entered a definitive agreement to be acquired by ABC in an all-cash buyout"],
        check_polygon=False)
    assert is_mna is True and tel["source"].startswith("keyword_in_text")

@pytest.mark.asyncio
async def test_classifier_target_side_still_suppressed():
    is_mna, tel = await is_likely_ma(
        "TGT", catalyst_quality="mna",
        catalyst_texts=["TGT to be acquired by ABC at a large premium"], check_polygon=False)
    assert is_mna is True and tel["source"] == "claude_classifier"
