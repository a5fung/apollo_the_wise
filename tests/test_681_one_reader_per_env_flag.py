"""The kill switch and the paper/live routing decision each had TWO independent parsers.

FOUND 2026-09-21 by the day's simplify review (altitude angle). `shared/env_flags.py` had shipped
the day before to be the ONE reading of "is this env flag on" — and had been adopted by exactly
the two callers it was written for, while ~30 hand-rolled `os.environ.get(X, "false").lower() ==
"true"` parses stayed put. Two of those pairs are not cosmetic:

  · `LIVE_TRADING_ENABLED` — parsed in `constants.py` AND in `agent.py`
  · `ALPACA_PAPER`         — parsed in `constants.py` AND in `broker/bar_stream.py`

That is the master trading switch and the decision of WHICH ACCOUNT an order goes to, each read
by two expressions that nothing kept in agreement. They happened to agree. Nothing made them.

⚠ WHY THE FIX IS `env_is_true` AND NOT `env_flag_on`. The permissive reader accepts
`{1,true,yes,on,enabled}`; every one of these sites accepted the literal `"true"` alone. Migrating
them onto the permissive reader would have WIDENED what turns real trading on — THE LINE, not a
cleanup. `env_is_true` replicates the old expression exactly, including the two edges that decide
real behaviour: a variable set to the EMPTY string is OFF even where the default is True (only an
ABSENT variable takes the default), and whitespace is not stripped, so `" true"` stays OFF.

⚠ AND WHY `TRUTHY` GREW `"enabled"`. `theme_merge_arm` held a THIRD copy of the truthy set that
accepted `"enabled"`. Folding it in without widening the shared set would have silently narrowed
a live operator toggle whose own docstring says the flip is his decision. Consolidation must not
drop a spelling someone may already be using.
"""
from __future__ import annotations

import ast
import os
from pathlib import Path

import pytest

from shared.env_flags import TRUTHY, env_flag_on, env_is_true

REPO = Path(__file__).resolve().parents[1]
ROOTS = ("agents", "core", "channels", "shared", "scripts")

#: Flags where a second reader, or a widened spelling, changes what happens to real money.
MONEY_FLAGS = (
    "LIVE_TRADING_ENABLED", "ALPACA_PAPER", "ENABLE_LIVE_MODE",
    "REGIME_SIZING_ENABLED", "R3_DAY1_REENTRY_ENABLED", "STOP_ACK_TIMEOUT_GATE_ENABLED",
)


def _env_name(node: ast.AST):
    """Unwrap `.lower()/.strip()/.upper()` down to an `os.environ.get(...)` / `os.getenv(...)`."""
    while (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
           and node.func.attr in ("lower", "strip", "upper") and not node.args):
        node = node.func.value
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
        f = node.func
        if f.attr == "get" and isinstance(f.value, ast.Attribute) and f.value.attr == "environ":
            return node.args[0].value if node.args and isinstance(node.args[0], ast.Constant) else "<dyn>"
        if f.attr == "getenv":
            return node.args[0].value if node.args and isinstance(node.args[0], ast.Constant) else "<dyn>"
    return None


def _hand_rolled_parses() -> "list[tuple[str, int, str]]":
    """DERIVED, never hand-listed — the rule this repo keeps relearning. Every comparison of an
    env var against a string literal or a literal collection, across the whole tree."""
    out = []
    for root in ROOTS:
        for f in sorted((REPO / root).rglob("*.py")):
            try:
                tree = ast.parse(f.read_text(encoding="utf-8"))
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                if not isinstance(node, ast.Compare) or len(node.ops) != 1:
                    continue
                if not isinstance(node.ops[0], (ast.Eq, ast.NotEq, ast.In, ast.NotIn)):
                    continue
                name = _env_name(node.left)
                if name:
                    out.append((str(f.relative_to(REPO)), node.lineno, name))
    return out


def test_no_money_flag_is_parsed_by_hand_anywhere():
    """The finding itself. Re-inline any of these and this names the file and line."""
    offenders = [(f, ln, n) for f, ln, n in _hand_rolled_parses() if n in MONEY_FLAGS]
    assert not offenders, (
        "a money-path env flag is being parsed by hand again instead of through "
        "`shared.env_flags.env_is_true`: "
        + "; ".join(f"{n} at {f}:{ln}" for f, ln, n in offenders)
    )


def test_every_money_flag_has_exactly_one_reader():
    """Not just "no hand-rolled parse" — ONE call site per flag, so the two readers cannot come
    back as two `env_is_true` calls that later disagree about the default."""
    calls: "dict[str, list[str]]" = {f: [] for f in MONEY_FLAGS}
    for root in ROOTS:
        for f in sorted((REPO / root).rglob("*.py")):
            try:
                tree = ast.parse(f.read_text(encoding="utf-8"))
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                        and node.func.id in ("env_is_true", "env_flag_on")
                        and node.args and isinstance(node.args[0], ast.Constant)
                        and node.args[0].value in calls):
                    calls[node.args[0].value].append(f"{f.relative_to(REPO)}:{node.lineno}")
    dupes = {k: v for k, v in calls.items() if len(v) > 1}
    assert not dupes, (
        "a money flag is read at more than one call site again — the defect this file exists "
        f"for, one layer up: { {k: v for k, v in dupes.items()} }"
    )


def test_the_remaining_hand_rolled_comparisons_are_not_booleans():
    """The scan cannot tell `== "true"` from `== "sip"`, so this states what is LEFT and why it
    is allowed to be: enum-valued variables and the two gates' own off-switches. A new boolean
    appearing here is the thing to catch — it shows up as an unexpected name."""
    allowed = {"ALPACA_DATA_FEED", "DELEGATION_GATE", "REPORT_FORMAT_GATE", "LAT_SMA_N", "<dyn>"}
    left = {n for _, _, n in _hand_rolled_parses()}
    assert left <= allowed, (
        f"a new hand-rolled env comparison appeared: {sorted(left - allowed)}. If it is a "
        f"boolean flag, route it through `env_is_true`; if it is genuinely enum-valued, add it "
        f"to `allowed` with a word about why."
    )


# ── the exact semantics, exercised rather than asserted from the source ──────────────────────

@pytest.mark.parametrize("raw,default,want", [
    (None, False, False), (None, True, True),          # ABSENT takes the default
    ("", False, False), ("", True, False),             # ⚠ EMPTY is OFF even when default=True
    ("true", False, True), ("TRUE", False, True), ("True", False, True),
    ("false", True, False), ("1", False, False), ("yes", False, False), ("on", False, False),
    (" true", False, False),                           # ⚠ whitespace does NOT turn a flag on
])
def test_env_is_true_matches_the_expression_it_replaced(monkeypatch, raw, default, want):
    """Byte-for-byte against `os.environ.get(NAME, "true"|"false").lower() == "true"` — the
    expression every one of these ~30 call sites used before today."""
    monkeypatch.delenv("APOLLO_T", raising=False)
    if raw is not None:
        monkeypatch.setenv("APOLLO_T", raw)
    legacy = os.environ.get("APOLLO_T", "true" if default else "false").lower() == "true"
    assert env_is_true("APOLLO_T", default=default) is want
    assert env_is_true("APOLLO_T", default=default) is legacy, (
        f"env_is_true diverged from the expression it replaced for {raw!r} (default={default})"
    )


def test_the_permissive_reader_still_accepts_every_spelling_the_folded_copy_did(monkeypatch):
    """`theme_merge_arm`'s own third copy accepted `"enabled"`. Dropping it would have silently
    stopped an operator toggle from taking."""
    for spelling in ("1", "true", "yes", "on", "enabled", "ENABLED", " on "):
        monkeypatch.setenv("APOLLO_T2", spelling)
        assert env_flag_on("APOLLO_T2"), f"{spelling!r} no longer turns a permissive flag on"
    assert "enabled" in TRUTHY


def test_the_theme_merge_arm_toggle_still_reads_the_same_spellings(monkeypatch):
    """End-to-end on the real toggle whose set was folded in — default OFF is load-bearing."""
    from agents.market_intelligence import theme_merge_arm as tma
    monkeypatch.delenv(tma.THEME_MERGE_ARM_ENV, raising=False)
    assert tma.merge_arm_enabled() is False, "the merge arm defaults ON — it must default OFF"
    for spelling in ("1", "true", "on", "yes", "enabled"):
        monkeypatch.setenv(tma.THEME_MERGE_ARM_ENV, spelling)
        assert tma.merge_arm_enabled() is True, f"{spelling!r} stopped arming the merge"


def test_paper_is_the_default_account_when_the_variable_is_absent(monkeypatch):
    """The single most dangerous direction in this whole migration: `env_flag_on` returns False
    for an unset variable, so routing `ALPACA_PAPER` through it — instead of `env_is_true` with
    default=True — would have sent an unset environment to the LIVE account."""
    from agents.market_intelligence import constants
    monkeypatch.delenv("ALPACA_PAPER", raising=False)
    assert constants.current_account_mode() == "paper"
    monkeypatch.setenv("ALPACA_PAPER", "")
    assert constants.current_account_mode() == "live", (
        "an EMPTY ALPACA_PAPER used to resolve to live; the migration must not have changed that "
        "silently in either direction"
    )
    monkeypatch.setenv("ALPACA_PAPER", "false")
    assert constants.current_account_mode() == "live"
