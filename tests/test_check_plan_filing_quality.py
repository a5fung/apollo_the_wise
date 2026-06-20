"""Filing-quality gate in check_plan.py (operator 2026-06-20): a task must be filed with
actionable detail + a clear outcome, never a placeholder bucket. The gate bans the exact
'confirm scope at triage' stub class that produced 13 contentless ghosts. Pins that the gate
catches the stub shape and does NOT false-positive on real (even terse) task descriptions."""
from scripts.check_plan import parse


def _errs(title: str) -> list[str]:
    text = f"## Stocks in Play\n- #999 | 2026-12-31 | pending | {title}\n"
    _, errors = parse(text)
    return [e for e in errors if "PLACEHOLDER" in e]


def test_catches_the_original_stub_titles():
    # the exact 13-ghost shape.
    assert _errs("(SiP backlog — confirm scope/title at triage)")
    assert _errs("(judge/catalyst item — confirm scope at triage)")
    assert _errs("(op-safety item — confirm scope at triage)")


def test_no_false_positive_on_real_tasks():
    # real task descriptions — even terse ones — must NOT trip the gate.
    assert not _errs("theme_engine isinstance(anthropic.APIError) TypeError — harden the guard")
    assert not _errs("RS liquidity floor — raise floor / cap-floor (gated, N>=10 + sign-off)")
    assert not _errs("Merge /setup + /why into one observability command")
    # 'confirm' alone (not 'confirm scope') and 'triage' alone (not 'at triage') are fine.
    assert not _errs("⚠ SCOPE THIN — EP-detection calibration; OPERATOR: confirm subsumed → close")
    assert not _errs("triage the idle data-gated reviews (run/defer/ratify each)")
