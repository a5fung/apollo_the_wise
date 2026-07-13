"""ADR 0025 C3 — pins for the golden-corpus gate (T2b) on the Stage-B adjudicator.

Three layers:
  1. Pure scorer/summarize truth tables — the bars (hard pairs 100%, others ≥85%)
     can't drift silently.
  2. Corpus integrity — 14 pairs, valid verdict vocabulary, the hard set present.
  3. The pass-record pin — if scripts/evals/theme_merge_eval_pass_record.json exists
     it must be PASSING and match the LIVE corpus + adjudication surface (prompt +
     tool schema) hashes; editing either without re-running the eval reds CI. While
     no record exists the gate test SKIPS loudly: the THEME_MERGE_ARM flip is
     forbidden until the eval runs green on prod (ADR 0025 §4).
"""
from __future__ import annotations

import asyncio
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

_EVALS = Path(__file__).parent.parent / "scripts" / "evals"
_spec = importlib.util.spec_from_file_location(
    "run_theme_merge_corpus_eval", _EVALS / "run_theme_merge_corpus_eval.py")
harness = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(harness)

CORPUS_PATH = _EVALS / "theme_merge_corpus_v1.json"
RECORD_PATH = _EVALS / "theme_merge_eval_pass_record.json"


# ── 1. pure scorer + bars ────────────────────────────────────────────────────

@pytest.mark.parametrize("golden,accept_also,verdict,expect", [
    ("DISTINCT", [], "DISTINCT", True),
    ("DISTINCT", [], "MERGE", False),
    ("PARENT_CHILD", ["DISTINCT"], "DISTINCT", True),      # accept_also honored
    ("PARENT_CHILD", ["DISTINCT"], "MERGE", False),
    ("MERGE", ["PARENT_CHILD"], "PARENT_CHILD", True),
    ("MERGE", [], None, False),                            # no verdict = fail
    ("MERGE", [], "ERROR", False),
])
def test_score_pair_truth_table(golden, accept_also, verdict, expect):
    case = {"golden_verdict": golden, "accept_also": accept_also}
    assert harness.score_pair(case, verdict) is expect


def _r(pid, hard, passed):
    return {"pair_id": pid, "hard": hard, "passed": passed}


def test_one_hard_failure_fails_gate_regardless_of_overall():
    results = [_r("M01", True, False)] + [_r(f"S{i}", False, True) for i in range(20)]
    s = harness.summarize(results)
    assert s["hard_failures"] == ["M01"]
    assert s["overall"] > 0.9
    assert s["pass"] is False


def test_others_bar_at_85_percent():
    hard_ok = [_r(f"H{i}", True, True) for i in range(5)]
    # 6/7 soft = 0.857 ≥ 0.85 → PASS
    s = harness.summarize(hard_ok + [_r(f"S{i}", False, i > 0) for i in range(7)])
    assert s["others_rate"] >= 0.85 and s["pass"] is True
    # 5/6 soft = 0.833 < 0.85 → FAIL
    s2 = harness.summarize(hard_ok + [_r(f"S{i}", False, i > 0) for i in range(6)])
    assert s2["others_rate"] < 0.85 and s2["pass"] is False


def test_all_hard_no_others_passes_when_clean():
    s = harness.summarize([_r(f"H{i}", True, True) for i in range(4)])
    assert s["pass"] is True and s["others_rate"] == 1.0


def test_run_eval_wires_adjudicator_and_scores():
    cases = [
        {"id": "C1", "hard": True, "golden_verdict": "DISTINCT",
         "theme_a": {"name": "A", "description": "a"}, "theme_b": {"name": "B", "description": "b"}},
        {"id": "C2", "hard": False, "golden_verdict": "MERGE", "accept_also": ["PARENT_CHILD"],
         "theme_a": {"name": "C", "description": "c"}, "theme_b": {"name": "D", "description": "d"}},
    ]

    async def fake_adjudicate(theme_a, theme_b, *, client=None, semaphore=None, **kw):
        return {"verdict": "DISTINCT" if theme_a["name"] == "A" else "PARENT_CHILD",
                "driver_a": "x", "driver_b": "y", "reason": "r", "analysis_scratchpad": "s"}

    results = asyncio.run(harness.run_eval(cases, fake_adjudicate, client=None))
    by_id = {r["pair_id"]: r for r in results}
    assert by_id["C1"]["passed"] is True
    assert by_id["C2"]["passed"] is True          # accept_also honored end-to-end
    assert harness.summarize(results)["pass"] is True


# ── 2. corpus integrity ──────────────────────────────────────────────────────

def test_corpus_integrity():
    corpus = json.loads(CORPUS_PATH.read_text())
    pairs = corpus["pairs"]
    assert len(pairs) == 14
    ids = [p["id"] for p in pairs]
    assert len(set(ids)) == 14
    vocab = {"MERGE", "DISTINCT", "PARENT_CHILD"}
    for p in pairs:
        assert p["golden_verdict"] in vocab, p["id"]
        assert set(p.get("accept_also", [])) <= vocab, p["id"]
        for side in ("theme_a", "theme_b"):
            assert p[side].get("name") and p[side].get("description"), p["id"]
    hard = [p["id"] for p in pairs if p.get("hard")]
    # the zero-tolerance set includes both legit-kill anchors + the adversarial traps
    assert {"M01", "M02", "M09", "M11", "M14"} <= set(hard)


# ── 3. the pass-record pin (the flip gate) ───────────────────────────────────

def test_pass_record_gates_the_flip():
    """No record → the eval hasn't run green → the flip is forbidden (skip loudly).
    Record present → it must be PASSING and match the live corpus + adjudication
    surface; any drift means re-run the eval, never hand-edit the record."""
    if not RECORD_PATH.exists():
        pytest.skip(
            "no theme_merge_eval_pass_record.json yet — the corpus eval has not run green; "
            "the THEME_MERGE_ARM flip is FORBIDDEN until it does (ADR 0025 §4)."
        )
    record = json.loads(RECORD_PATH.read_text())
    assert record.get("pass") is True, (
        "the last corpus-eval run FAILED — the THEME_MERGE_ARM flip is forbidden; "
        "fix the adjudicator and re-run scripts/evals/run_theme_merge_corpus_eval.py"
    )
    live_corpus_sha = hashlib.sha1(CORPUS_PATH.read_bytes()).hexdigest()[:12]
    assert record.get("corpus_sha1") == live_corpus_sha, (
        "corpus changed since the last passing eval — re-run the corpus eval"
    )
    assert record.get("prompt_sha1") == harness.adjudication_surface_sha1(), (
        "adjudication surface (prompt/tool schema) changed since the last passing eval — "
        "re-run the corpus eval"
    )
    assert not record.get("hard_failures"), "hard-pair failures in the pass record"
