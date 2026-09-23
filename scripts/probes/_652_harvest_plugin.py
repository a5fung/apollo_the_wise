"""#652 — pytest plugin that harvests every message body the test suite pushes through
`send_telegram_message`, attributed to the PRODUCTION call site that sent it.

WHY: prod stores almost no full message bodies (the fallback audit row keeps 300 chars),
and running the builders inside the prod container would spend money and write rows. The
test suite already drives the real builders with fixture data — much of it copied from
real prod rows — and every body reaches the send boundary through a fake. This plugin
wraps each fake (monkeypatch.setattr AND unittest.mock.patch/patch.object) with a recorder
that forwards to the original, so `call_args` / `await_count` assertions still hold.

Run ONCE, read many (cost rule):
    APOLLO_652_HARVEST=/tmp/652_corpus_tests.jsonl \\
      python -m pytest tests -q -p scripts.probes._652_harvest_plugin
Each line: {"test", "site" (first non-test repo frame = the sender), "site_any", "parse_mode",
"body"}. Nothing in the repo is modified; the recorder is process-local.
"""
from __future__ import annotations

import inspect
import json
import os
import sys
from pathlib import Path
from unittest import mock

_OUT = os.environ.get("APOLLO_652_HARVEST", "/tmp/652_corpus_tests.jsonl")
_ROOT = str(Path(__file__).resolve().parents[2])
_TARGET = "send_telegram_message"
_fh = open(_OUT, "a", encoding="utf-8")
_current_test: str | None = None
_seen = 0


def pytest_runtest_setup(item):
    global _current_test
    _current_test = item.nodeid


def _site_of(frame) -> tuple[str | None, str | None]:
    """Walk outward from the recorder: first repo frame at all, first repo frame outside tests/."""
    site_any = None
    f = frame
    for _ in range(60):
        if f is None:
            break
        fn = f.f_code.co_filename
        if fn.startswith(_ROOT) and "_652_harvest_plugin" not in fn:
            rel = f"{os.path.relpath(fn, _ROOT)}:{f.f_lineno}"
            if site_any is None:
                site_any = rel
            if not rel.startswith("tests/"):
                return rel, site_any
        f = f.f_back
    return None, site_any


def _record(args, kwargs, frame):
    global _seen
    text = args[0] if args else kwargs.get("text")
    if not isinstance(text, str):
        return
    pm = kwargs.get("parse_mode", "<default>")
    site, site_any = _site_of(frame)
    rec = {
        "test": _current_test, "site": site, "site_any": site_any,
        "parse_mode": pm if isinstance(pm, str) else repr(pm), "body": text,
    }
    _fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    _fh.flush()
    _seen += 1


def _wrap(fake):
    if fake is None or getattr(fake, "_652_wrapped", False):
        return fake
    if isinstance(fake, mock.AsyncMock) or inspect.iscoroutinefunction(fake):
        async def w(*a, **k):
            _record(a, k, sys._getframe(1))
            return await fake(*a, **k)
    else:
        def w(*a, **k):
            _record(a, k, sys._getframe(1))
            return fake(*a, **k)
    w._652_wrapped = True  # type: ignore[attr-defined]
    w._652_orig = fake  # type: ignore[attr-defined]
    w.__name__ = getattr(fake, "__name__", "send_telegram_message")
    return w


# ── hook 1: monkeypatch.setattr(module, "send_telegram_message", fake) ─────────
from _pytest.monkeypatch import MonkeyPatch  # noqa: E402

try:  # pytest 9 renamed the sentinel; accept either
    from _pytest.monkeypatch import NOTSET as _NOTSET  # type: ignore[attr-defined]
except ImportError:  # pragma: no cover
    from _pytest.monkeypatch import notset as _NOTSET  # type: ignore[attr-defined]

_orig_setattr = MonkeyPatch.setattr


def _setattr(self, target, name, value=_NOTSET, raising=True):
    _orig_setattr(self, target, name, value, raising)
    try:
        if isinstance(target, str) and value is _NOTSET:
            obj_path, attr = target.rsplit(".", 1)
            import importlib
            obj = importlib.import_module(obj_path) if obj_path in sys.modules else None
            if obj is None:
                return
        else:
            obj, attr = target, name
        if attr == _TARGET:
            setattr(obj, attr, _wrap(getattr(obj, attr)))
    except Exception:  # never let the harvest break a test
        pass


MonkeyPatch.setattr = _setattr  # type: ignore[method-assign]

# ── hook 2: unittest.mock.patch / patch.object(module, "send_telegram_message") ──
_orig_enter = mock._patch.__enter__


def _enter(self):
    res = _orig_enter(self)
    try:
        if self.attribute == _TARGET:
            target = self.getter()
            setattr(target, self.attribute, _wrap(getattr(target, self.attribute)))
    except Exception:
        pass
    return res


mock._patch.__enter__ = _enter  # type: ignore[method-assign]


# ── hook 3: the REAL sender (tests that never fake it) — record, then delegate ─────
def pytest_collection_finish(session):
    try:
        import agents.market_intelligence.briefing as briefing
    except Exception:
        return
    real = getattr(briefing, _TARGET, None)
    if real is None or getattr(real, "_652_wrapped", False):
        return
    wrapped = _wrap(real)
    briefing.send_telegram_message = wrapped  # type: ignore[attr-defined]
    for mod in list(sys.modules.values()):
        try:
            if getattr(mod, _TARGET, None) is real:
                setattr(mod, _TARGET, wrapped)
        except Exception:
            continue


def pytest_sessionfinish(session, exitstatus):
    _fh.flush()
    print(f"\n[652 harvest] {_seen} bodies -> {_OUT}", file=sys.stderr)
