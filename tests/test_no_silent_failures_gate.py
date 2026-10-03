"""Regression lock for the swallow-a-failure gate (#381, zero-tolerance since #466).

The deploy/pre-commit gate (`preflight_no_silent_failures`) must CATCH a broad+silent
except — the FMP-403 (#380) / theme-shadow-0-rows (#173) class — honor the `# loud-ok`
escape, and leave genuine control-flow (narrow excepts, loud handlers, re-raises)
alone, so a green gate means clean, not blind. Since #466 there is NO baseline: the
live tree must scan to zero, and the gate (`main`) must exit 1 on a single new
unmarked swallow in ANY in-scope file — proven below against a throwaway tree.
"""
import ast
from pathlib import Path

from scripts import preflight_no_silent_failures as gate
from scripts.preflight_no_silent_failures import (
    SilentFailureVisitor, _is_broad, _scan, main,
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


# ── zero-tolerance (#466): the live tree is clean and nothing can be allowance-listed ──

_REPO = Path(__file__).resolve().parent.parent
_SWALLOW = "def f():\n    try:\n        g()\n    except Exception:\n        pass\n"


def _tree(tmp_path: Path, rel: str, body: str) -> Path:
    """A throwaway repo root holding ONE in-scope file."""
    p = tmp_path / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body, encoding="utf-8")
    return tmp_path


def test_live_tree_has_zero_unmarked_swallows():
    """THE #466 DoD: every broad+silent except in agents/ core/ channels/ shared/ is either
    loud (logs / audits / raises) or carries a reviewed `# loud-ok: <reason>`."""
    violations, n_files = _scan(_REPO)
    assert n_files > 100, "the scan found almost nothing - the scope broke, 'zero' would be vacuous"
    assert violations == [], (
        "unmarked broad+silent except(s): "
        + ", ".join(f"{v['rel']}:{v['line']}" for v in violations)
        + ". LOG the failure (logger.warning with the exception + context) or, for genuine "
          "control-flow, tag the except line `# loud-ok: <reason>`.")


def test_the_baseline_cannot_come_back():
    """The ratchet's allowance file is gone and its machinery is gone with it: a re-added
    baseline would silently re-permit swallows, which is exactly what #466 closed."""
    assert not (_REPO / "scripts" / "no_silent_failures_baseline.json").exists()
    assert not hasattr(gate, "BASELINE_PATH")


def test_main_fails_on_one_new_unmarked_swallow_in_any_scoped_dir(tmp_path, capsys):
    """THE MUTATION: one fresh `except Exception: pass` must turn the gate red in every scoped
    dir, including files the OLD ratchet had a non-zero allowance for (telegram, ep_detector)."""
    for rel in ("agents/market_intelligence/ep_detector.py", "channels/telegram.py",
                "core/router.py", "shared/anything.py", "agents/market_intelligence/brand_new.py"):
        root = _tree(tmp_path / rel.replace("/", "_"), rel, _SWALLOW)
        assert main([], repo_root=root) == 1, f"{rel}: a new unmarked swallow did not fail the gate"
        out = capsys.readouterr().out
        assert rel in out and "DEPLOY FAILED" in out


def test_main_passes_when_the_same_swallow_is_logged_or_tagged(tmp_path):
    logged = _SWALLOW.replace("        pass\n", "        logger.warning('g failed')\n")
    tagged = _SWALLOW.replace(
        "except Exception:", "except Exception:  # loud-ok: optional-parse fallback")
    for name, body in (("logged", logged), ("tagged", tagged)):
        root = _tree(tmp_path / name, "agents/market_intelligence/x.py", body)
        assert main([], repo_root=root) == 0, name


def test_loud_ok_must_sit_on_the_except_line(tmp_path):
    """The escape is read off the `except` line only - a tag on the body line does not count."""
    body = _SWALLOW.replace("        pass\n", "        pass  # loud-ok: wrong line\n")
    root = _tree(tmp_path, "agents/market_intelligence/x.py", body)
    assert main([], repo_root=root) == 1


def test_update_baseline_is_retired_and_writes_nothing(tmp_path, capsys):
    root = _tree(tmp_path, "agents/market_intelligence/x.py", _SWALLOW)
    assert main(["--update-baseline"], repo_root=root) == 1
    assert "retired" in capsys.readouterr().out
    assert list((_REPO / "scripts").glob("no_silent_failures_baseline*")) == []


def test_strict_flag_is_still_accepted_as_a_noop(tmp_path):
    clean = _tree(tmp_path / "clean", "core/x.py", "x = 1\n")
    dirty = _tree(tmp_path / "dirty", "core/x.py", _SWALLOW)
    assert main(["--strict"], repo_root=clean) == 0
    assert main(["--strict"], repo_root=dirty) == 1
