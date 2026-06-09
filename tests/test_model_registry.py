"""Regression lock for the LLM model registry (#257, 2026-06-09).

Two halves (mirrors tests/test_timezone_hygiene.py):
  1. The registry itself is sane — role constants exist, ids look like Claude
     model ids, pricing tables cover every role binding.
  2. The deploy gate (preflight_model_registry) actually CATCHES a stray
     literal and honors the `# model-ok` escape — a green gate means clean.
"""
import ast
from pathlib import Path

from scripts.preflight_model_registry import check_file, main as gate_main
from shared import llm_models


def test_all_registry_values_look_like_model_ids():
    for name, val in vars(llm_models).items():
        if name.startswith("_") or not isinstance(val, str):
            continue
        assert val.startswith("claude-"), f"{name} = {val!r} is not a Claude model id"


def test_role_constants_exist():
    for role in ("ORCHESTRATOR_MODEL", "MARKET_AGENT_MODEL", "THEME_MODEL",
                 "THEME_ADVISOR_MODEL", "JUDGE_MODEL", "GROUNDED_GRADE_MODEL",
                 "MATERIALITY_MODEL", "METRICS_EXTRACTION_MODEL",
                 "CATALYST_TYPE_MODEL", "POSTMORTEM_MODEL", "SYSTEM_REVIEW_MODEL",
                 "DESCRIPTION_MODEL", "COMPRESSION_MODEL", "HEALTHCHECK_MODEL"):
        assert hasattr(llm_models, role), f"registry missing role constant {role}"


def test_spend_tracker_prices_every_role_binding():
    from agents.market_intelligence.spend_tracker import _PRICING
    roles = {v for k, v in vars(llm_models).items()
             if k.endswith("_MODEL") and isinstance(v, str)}
    unpriced = roles - set(_PRICING)
    assert not unpriced, f"role-bound models missing from spend_tracker pricing: {unpriced}"


def test_gate_catches_stray_literal(tmp_path: Path):
    bad = tmp_path / "bad.py"
    bad.write_text('MODEL = "claude-sonnet-4-6"\n', encoding="utf-8")
    violations = check_file(bad)
    assert len(violations) == 1 and violations[0]["literal"] == "claude-sonnet-4-6"


def test_gate_honors_model_ok_escape(tmp_path: Path):
    ok = tmp_path / "ok.py"
    ok.write_text('MODEL = "claude-sonnet-4-6"  # model-ok: migration shim\n', encoding="utf-8")
    assert check_file(ok) == []


def test_gate_skips_docstrings(tmp_path: Path):
    doc = tmp_path / "doc.py"
    doc.write_text('def f():\n    """Example: claude-sonnet-4-6."""\n    return 1\n',
                   encoding="utf-8")
    assert check_file(doc) == []


def test_gate_ignores_non_model_strings(tmp_path: Path):
    f = tmp_path / "f.py"
    f.write_text('x = "claude is great"\ny = "not-claude-sonnet-4-6 suffix"\n', encoding="utf-8")
    assert check_file(f) == []


def test_live_tree_is_clean():
    # The actual enforcement: agents/ core/ channels/ shared/ carry no stray ids.
    assert gate_main() == 0
