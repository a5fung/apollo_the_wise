"""Preflight [5m/7] pins — the grade-quality regression gate (ADR 0030 §4)."""
import importlib.util
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "preflight_judge_eval_gate",
    Path(__file__).parent.parent / "scripts" / "preflight_judge_eval_gate.py",
)
gate = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gate)

LIVE = {"rubric_version": "v3", "rubric_hash": "aaaa1111",
        "catalyst_grade_prompt_version": "v3", "judge_model": "claude-opus-4-8",
        "corpus_sha1": "cafe00112233"}


def _rec(**over):
    r = {**LIVE, "pass": True, "waiver": None, "run_at": "2026-07-12"}
    r.update(over)
    return r


def test_match_passes():
    ok, _ = gate.check(_rec(), LIVE)
    assert ok is True


def test_missing_record_fails():
    ok, msgs = gate.check(None, LIVE)
    assert ok is False
    assert any("no pass record" in m for m in msgs)


def test_rubric_hash_mismatch_fails():
    ok, msgs = gate.check(_rec(rubric_hash="bbbb2222"), LIVE)
    assert ok is False
    assert any("rubric_hash" in m for m in msgs)


def test_model_swap_fails():
    ok, _ = gate.check(_rec(judge_model="claude-sonnet-5"), LIVE)
    assert ok is False


def test_corpus_content_edit_fails():
    ok, _ = gate.check(_rec(corpus_sha1="dead00000000"), LIVE)
    assert ok is False


def test_record_pass_false_fails_even_when_keys_match():
    ok, msgs = gate.check(_rec(**{"pass": False}), LIVE)
    assert ok is False
    assert any("record.pass is not true" in m for m in msgs)


def test_waiver_passes_loudly():
    ok, msgs = gate.check(_rec(rubric_hash="bbbb2222", waiver="emergency deploy, operator 7/12"),
                          LIVE)
    assert ok is True
    assert any("WAIVED" in m for m in msgs)


def test_extract_live_keys_matches_the_real_module_hash():
    # the ast-recomputed hash must equal the module's own RUBRIC_HASH (import-free parity)
    live = gate.extract_live_keys()
    from agents.market_intelligence.ep_grade_judge import RUBRIC_HASH, RUBRIC_VERSION
    from shared.llm_models import JUDGE_MODEL
    assert live["rubric_hash"] == RUBRIC_HASH
    assert live["rubric_version"] == RUBRIC_VERSION
    assert live["judge_model"] == JUDGE_MODEL
