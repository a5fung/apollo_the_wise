"""Every kwarg we pass to `messages.create` must exist in the INSTALLED SDK.

2026-08-20: an image rebuild pulled `anthropic` 1.0.0 (the requirement was an
unbounded `>=0.40.0`). 1.0 removed `temperature` from `AsyncMessages.create` and
carries no `**kwargs`, so `theme_merge_arm` raised
`TypeError: unexpected keyword argument 'temperature'` on EVERY call — the theme
merge arm returned verdict=ERROR for 100% of pairs. Last good adjudication was
2026-08-19 17:17 ET; the failure was invisible to the whole test suite because
every test mocks the client, and invisible locally because this machine still had
0.117.0, where `temperature` is valid.

This reads the real signature of the installed SDK, so it fails wherever the
mismatch actually exists — including CI, which installs from requirements/.
"""
from __future__ import annotations

import ast
import inspect
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent
_SCANNED = ("agents", "core", "shared", "channels")


def _accepted_kwargs() -> tuple[set[str], bool] | None:
    """Signature of the REAL installed SDK.

    conftest.py stubs `anthropic` in sys.modules (heavy install, most tests mock
    the client), which is exactly what let the 08-20 break through. Drop the stub
    for the duration of this import, then put it back so no other test is
    affected. Returns None when the SDK genuinely is not installed.
    """
    import importlib
    import sys

    saved = {k: v for k, v in sys.modules.items()
             if k == "anthropic" or k.startswith("anthropic.")}
    for k in saved:
        del sys.modules[k]
    try:
        mod = importlib.import_module("anthropic.resources.messages")
        sig = inspect.signature(mod.AsyncMessages.create)
        has_var_kw = any(p.kind is p.VAR_KEYWORD for p in sig.parameters.values())
        return set(sig.parameters) - {"self"}, has_var_kw
    except Exception:
        return None
    finally:
        for k in [k for k in sys.modules
                  if k == "anthropic" or k.startswith("anthropic.")]:
            del sys.modules[k]
        sys.modules.update(saved)


def _call_sites() -> list[tuple[str, int, str]]:
    """(file, line, kwarg) for every `<something>.messages.create(...)` call."""
    out: list[tuple[str, int, str]] = []
    for pkg in _SCANNED:
        for path in (_ROOT / pkg).rglob("*.py"):
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"))
            except SyntaxError:                      # pragma: no cover
                continue
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                    continue
                if node.func.attr != "create":
                    continue
                owner = node.func.value
                if not (isinstance(owner, ast.Attribute) and owner.attr == "messages"):
                    continue
                for kw in node.keywords:
                    if kw.arg:                        # skip **spread
                        out.append((str(path.relative_to(_ROOT)), node.lineno, kw.arg))
    return out


def test_call_sites_were_actually_found():
    """Guard the guard — an AST change that finds nothing must not read as pass."""
    assert len({f for f, _, _ in _call_sites()}) >= 3


def test_every_messages_create_kwarg_exists_in_the_installed_sdk():
    got = _accepted_kwargs()
    if got is None:
        pytest.skip("real anthropic SDK not importable in this environment")
    accepted, has_var_kw = got
    if has_var_kw:
        pytest.skip("SDK accepts **kwargs — signature cannot reject anything")
    bad = [(f, ln, kw) for f, ln, kw in _call_sites() if kw not in accepted]
    assert not bad, (
        "these kwargs are NOT accepted by the installed anthropic SDK and will "
        "raise TypeError at runtime:\n  "
        + "\n  ".join(f"{f}:{ln} passes {kw!r}" for f, ln, kw in bad)
        + f"\naccepted: {sorted(accepted)}"
    )


def test_temperature_is_not_passed_anywhere():
    """The specific 2026-08-20 regression, pinned by name so a revert is loud."""
    bad = [(f, ln) for f, ln, kw in _call_sites() if kw == "temperature"]
    assert not bad, f"anthropic 1.0 removed `temperature`; still passed at {bad}"
