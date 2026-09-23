"""Regression lock for the LLM model registry (#257, 2026-06-09).

Two halves (mirrors tests/test_timezone_hygiene.py):
  1. The registry itself is sane — role constants exist, ids look like Claude
     model ids, pricing tables cover every role binding.
  2. The deploy gate (preflight_model_registry) actually CATCHES a stray
     literal and honors the `# model-ok` escape — a green gate means clean.
"""
from pathlib import Path

from scripts.preflight_model_registry import check_file
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


def test_registry_prices_every_role_binding():
    # One pricing table in the registry; both spend consumers import it, so this
    # single assertion covers core/spend.py AND spend_tracker.py.
    roles = {v for k, v in vars(llm_models).items()
             if k.endswith("_MODEL") and isinstance(v, str)}
    unpriced = roles - set(llm_models.PRICING_PER_MTOK)
    assert not unpriced, f"role-bound models missing from PRICING_PER_MTOK: {unpriced}"


def test_spend_consumers_share_the_registry_table():
    # #509: both consumers route through llm_models.pricing_for (not a raw dict
    # reference) so an auto-resolved RESOLVED_ROLES id prices at its tier's rate
    # instead of the flat default — still ONE source of truth, now a function.
    from agents.market_intelligence import spend_tracker
    from core import spend
    assert spend_tracker._pricing_for is llm_models.pricing_for
    assert spend._pricing_for is llm_models.pricing_for


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


# NOTE: no full-tree scan test here — tree enforcement runs in deploy.sh [5i/7] and
# as an explicit CI workflow step (same split as test_timezone_hygiene vs its gate);
# duplicating the ~100-file AST walk inside pytest doubled CI work for no new signal.
