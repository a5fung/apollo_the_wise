"""Every production Anthropic client is built by shared/llm_client (2026-09-23).

Why a population test and not a count: the adapter only protects calls that go THROUGH it. A
direct `anthropic.AsyncAnthropic(...)` anywhere in agents/ core/ channels/ shared/ is a call
site the next model release can break silently — exactly what claude-opus-5-5 did to both
judges. The walk is AST-derived (not a grep) and the known members are NAMED, so the walk
cannot go blind: if it ever finds fewer factory call sites than the list below, the test fails
on the list, not on an empty set (repo rule: a count floor is not a population test).

`scripts/` is deliberately outside the walk — offline evals and probes may construct raw
clients; nothing there runs in production.
"""
from __future__ import annotations

import ast
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_SCANNED = ("agents", "core", "shared", "channels")
_FACTORY_FILE = "shared/llm_client.py"
_CTOR_NAMES = {"AsyncAnthropic", "Anthropic"}
_FACTORY_NAMES = {"make_async_anthropic", "make_anthropic"}

# The known members: every file that built a client directly before 2026-09-23 and now goes
# through the factory. A NEW production caller must be added here when it appears (the
# direct-construction half of this test is what tells you it exists).
KNOWN_FACTORY_CALLERS = {
    "agents/market_intelligence/agent.py",
    "agents/market_intelligence/catalyst_type_classifier.py",
    "agents/market_intelligence/ep_detector.py",
    "agents/market_intelligence/judge_divergence.py",
    "agents/market_intelligence/judge_named_themes.py",
    "agents/market_intelligence/model_resolution.py",
    "agents/market_intelligence/postmortem.py",
    "agents/market_intelligence/scheduler.py",
    "agents/market_intelligence/system_review.py",
    "agents/market_intelligence/theme_engine.py",
    "channels/telegram.py",
    "core/context.py",
    "core/orchestrator.py",
}


def _walk():
    """(direct_constructions, factory_callers) over the production packages."""
    direct: list[tuple[str, int]] = []
    factory: set[str] = set()
    for pkg in _SCANNED:
        for path in sorted((_ROOT / pkg).rglob("*.py")):
            rel = str(path.relative_to(_ROOT))
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"))
            except SyntaxError:  # pragma: no cover
                continue
            from_imports = {
                alias.asname or alias.name
                for node in ast.walk(tree)
                if isinstance(node, ast.ImportFrom) and node.module == "anthropic"
                for alias in node.names if alias.name in _CTOR_NAMES
            }
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                f = node.func
                if isinstance(f, ast.Attribute) and f.attr in _CTOR_NAMES \
                        and isinstance(f.value, ast.Name) and f.value.id == "anthropic":
                    direct.append((rel, node.lineno))
                elif isinstance(f, ast.Name) and f.id in from_imports:
                    direct.append((rel, node.lineno))
                elif isinstance(f, ast.Name) and f.id in _FACTORY_NAMES:
                    factory.add(rel)
                elif isinstance(f, ast.Attribute) and f.attr in _FACTORY_NAMES:
                    factory.add(rel)
    return direct, factory


def test_no_direct_anthropic_client_construction_outside_the_factory():
    direct, _ = _walk()
    stray = [(f, ln) for f, ln in direct if f != _FACTORY_FILE]
    assert not stray, (
        "Anthropic clients must come from shared.llm_client.make_async_anthropic / "
        "make_anthropic (the model-compat adapter); direct constructions at:\n  "
        + "\n  ".join(f"{f}:{ln}" for f, ln in stray)
    )


def test_the_factory_itself_is_the_only_direct_constructor():
    direct, _ = _walk()
    assert {f for f, _ in direct} == {_FACTORY_FILE}, direct
    assert len(direct) == 2  # one async, one sync


def test_every_known_caller_routes_through_the_factory():
    _, factory = _walk()
    missing = KNOWN_FACTORY_CALLERS - factory
    assert not missing, f"known production callers no longer call the factory: {sorted(missing)}"


def test_walk_did_not_go_blind():
    _, factory = _walk()
    assert len(factory) >= len(KNOWN_FACTORY_CALLERS) == 13
