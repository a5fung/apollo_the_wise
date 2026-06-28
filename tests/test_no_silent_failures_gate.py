"""Regression lock for the swallow-a-failure gate (#381).

The deploy/pre-commit gate (`preflight_no_silent_failures`) must CATCH a broad+silent
except — the FMP-403 (#380) / theme-shadow-0-rows (#173) class — honor the `# loud-ok`
escape, and leave genuine control-flow (narrow excepts, loud handlers, re-raises)
alone, so a green gate means clean, not blind. The last test locks the committed
baseline in sync with the live scan (the ratchet must not silently drift up).
"""
import ast
import json
from pathlib import Path

from scripts.preflight_no_silent_failures import (
    SilentFailureVisitor, _is_broad, _scan, _counts, BASELINE_PATH,
)


def _violations(code: str) -> list[dict]:
    tree = ast.parse(code)
    v = SilentFailureVisitor("<test>", code.splitlines())
    v.visit(tree)
    return v.violations


# ── the gate FLAGS broad + silent swallows ──────────────────────────────────

def test_flags_broad_silent_pass():
    assert _violations("try:\n    f()\nexcept Exception:\n    pass\n")


def test_flags_bare_except_pass():
    assert _violations("try:\n    f()\nexcept:\n    pass\n")


def test_flags_broad_silent_return_none():
    assert _violations(
        "def g():\n    try:\n        return f()\n    except Exception:\n        return None\n")


def test_flags_broad_tuple_containing_exception():
    assert _violations("try:\n    f()\nexcept (KeyError, Exception):\n    pass\n")


# ── the gate LEAVES genuine control-flow / loud handlers alone ───────────────

def test_allows_narrow_except():
    # a specific, expected exception is normal handling, not a swallow
    assert _violations("for x in y:\n    try:\n        f()\n    except KeyError:\n        continue\n") == []


def test_allows_loud_handler_logger():
    assert _violations(
        "try:\n    f()\nexcept Exception as e:\n    logger.error(e)\n    return None\n") == []


def test_allows_handler_that_reraises():
    assert _violations("try:\n    f()\nexcept Exception:\n    raise\n") == []


def test_allows_handler_with_audit_call():
    assert _violations(
        "try:\n    f()\nexcept Exception as e:\n    log_audit_event('x', str(e))\n") == []


def test_loud_ok_escape_suppresses():
    code = ("try:\n    f()\n"
            "except Exception:  # loud-ok: fallback-of-fallback, the alert may itself fail\n"
            "    pass\n")
    assert _violations(code) == []


# ── _is_broad classification ─────────────────────────────────────────────────

def _handler(src: str) -> ast.ExceptHandler:
    return ast.parse(src).body[0].handlers[0]


def test_is_broad_classifies():
    assert _is_broad(_handler("try:\n x\nexcept Exception:\n pass")) is True
    assert _is_broad(_handler("try:\n x\nexcept BaseException:\n pass")) is True
    assert _is_broad(_handler("try:\n x\nexcept:\n pass")) is True
    assert _is_broad(_handler("try:\n x\nexcept KeyError:\n pass")) is False
    assert _is_broad(_handler("try:\n x\nexcept (ValueError, TypeError):\n pass")) is False


# ── the committed baseline stays in sync (the ratchet cannot drift up) ───────

def test_committed_baseline_not_exceeded():
    """Live scan must not EXCEED the committed baseline anywhere — the gate's exact
    deploy contract. A new swallow added without remediation (or a baseline never
    regenerated after one) fails here, in CI, before it ever reaches prod."""
    repo_root = Path(__file__).resolve().parent.parent
    violations, _ = _scan(repo_root)
    live = _counts(violations)
    baseline = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))["per_file"]
    offenders = {rel: n for rel, n in live.items() if n > baseline.get(rel, 0)}
    assert not offenders, (
        f"NEW broad+silent swallow(s) beyond baseline: {offenders}. Fix the swallow "
        f"(raise / log+alert / failure_policy decorator), or — if genuinely remediated "
        f"down — run `python scripts/preflight_no_silent_failures.py --update-baseline`.")
