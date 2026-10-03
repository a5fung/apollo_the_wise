"""ADR 0030 — scripts/evals/write_judge_pass_record.py regenerates the pass record FROM a captured
eval run: every value copied from the RESULTS_JSON block, never typed; a failing run is refused;
the hand-seeded `envelope` section is carried forward verbatim (#547)."""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[1]
_SCRIPT = _REPO / "scripts" / "evals" / "write_judge_pass_record.py"


def _load():
    spec = importlib.util.spec_from_file_location("write_judge_pass_record", _SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


W = _load()

_KEYS = {"rubric_version": "v4-2026-08-27-axis-split-second-opinion", "rubric_hash": "d65ac7f3",
         "catalyst_grade_prompt_version": "v4-2026-10-03-deal-fields-merit-if-no-deal",
         "judge_model": "claude-opus-5", "corpus_version": "v1-2026-07-11", "corpus_sha1": "04150fdd3a5e"}


def _captured(passed: bool) -> str:
    summary = {"by_class": {"mna_as_catalyst": {"n": 3, "passed": 3, "rate": 1.0, "failed_ids": []}},
               "hard_failures": [] if passed else ["S19"], "positive_control_rate": 1.0,
               "soft_classes_below_bar": [], "overall": 1.0 if passed else 0.97, "pass": passed}
    block = {"keys": _KEYS, "summary": summary,
             "results": [{"case_id": "S19", "class": "mna_as_catalyst", "passed": passed}] * 3}
    return ("ROBUSTNESS MAP ...\nGATE: PASS\n\n=== RESULTS_JSON ===\n" + json.dumps(block)
            + "\n\n=== DIFFERENTIAL_RESULTS_JSON ===\n{\"keys\": {}}\n")


def test_extract_finds_the_block_and_ignores_what_follows():
    rj = W.extract_results_json(_captured(True))
    assert rj["keys"] == _KEYS and rj["summary"]["pass"] is True and len(rj["results"]) == 3
    with pytest.raises(ValueError):
        W.extract_results_json("no block here")


def test_record_is_built_from_the_block_and_carries_the_envelope_forward():
    existing = {"rubric_hash": "old", "envelope": {"max_tokens": 1500, "timeout": 25,
                                                   "tool_choice_type": "tool", "fail_open_hash": "b25277fd8bb6"}}
    rec = W.build_record(W.extract_results_json(_captured(True)), existing, run_at="2026-10-04T10:00:00-07:00")
    for k, v in _KEYS.items():
        assert rec[k] == v
    assert rec["pass"] is True and rec["n_cases"] == 3 and rec["overall"] == 1.0
    assert rec["per_class"]["mna_as_catalyst"]["rate"] == 1.0 and rec["hard_failures"] == []
    assert rec["envelope"] == existing["envelope"]
    assert rec["run_at"] == "2026-10-04T10:00:00-07:00"
    assert "by_class" not in rec   # the flat shape the gate reads


def test_a_failing_run_never_becomes_a_pass_record():
    with pytest.raises(ValueError, match="did NOT pass"):
        W.build_record(W.extract_results_json(_captured(False)), None)


def test_cli_dry_run_prints_and_writes_nothing(tmp_path):
    cap = tmp_path / "run.txt"
    cap.write_text(_captured(True), encoding="utf-8")
    rec = tmp_path / "record.json"
    rec.write_text(json.dumps({"envelope": {"max_tokens": 1500}}), encoding="utf-8")
    p = subprocess.run([sys.executable, str(_SCRIPT), str(cap), "--record", str(rec), "--dry-run"],
                       capture_output=True, text=True, timeout=60)
    assert p.returncode == 0 and '"rubric_hash": "d65ac7f3"' in p.stdout and '"max_tokens": 1500' in p.stdout
    assert json.loads(rec.read_text()) == {"envelope": {"max_tokens": 1500}}   # untouched
    p = subprocess.run([sys.executable, str(_SCRIPT), str(cap), "--record", str(rec)],
                       capture_output=True, text=True, timeout=60)
    assert p.returncode == 0 and "envelope carried forward" in p.stdout
    written = json.loads(rec.read_text())
    assert written["pass"] is True and written["envelope"] == {"max_tokens": 1500} and written["corpus_sha1"] == "04150fdd3a5e"


def test_the_gate_accepts_a_record_this_tool_writes(tmp_path):
    """The preflight's `check()` reads the flat keys this tool writes; a record built from a run
    whose keys equal the live surface passes the gate."""
    sys.path.insert(0, str(_REPO))
    from scripts import preflight_judge_eval_gate as g
    rec = W.build_record(W.extract_results_json(_captured(True)), {"envelope": {}}, run_at="t")
    live = dict(_KEYS)
    live.pop("corpus_version")
    ok, msgs = g.check(rec, live)
    assert ok, msgs
