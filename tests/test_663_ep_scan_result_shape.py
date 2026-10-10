"""#663 — the EP scan's result SHAPE is deterministic, and the guards that depend on it are hermetic.

WHAT HAPPENED (CI run 34865695231, 2026-09-14). `test_624`'s admitted-alert byte-identity guard
compared three `run_ep_scan`s and found `setup_class` present in scan 2 and absent in scan 1.
d747f414 had just moved that assignment outside the classifier's try, so an EXCEPTION could no
longer drop it — yet it dropped. The captured log says why: scan 1's post-scan block ended with
`catalyst_type post-scan block failed (non-critical): ` and an EMPTY message, and had no yfinance
line, while scans 2 and 3 each logged a yfinance 404 for BIG00. `str(TimeoutError())` is ''. The
chain is:

  compute_setup_class_fields → collector.get_recent_upgrade_events → yf.Ticker(...).upgrades_downgrades
  (a LIVE Yahoo call, in a worker thread, from inside a "unit" test)
  → first call on a fresh runner pays Yahoo's cookie/crumb bootstrap and exceeds the 25s
    post-scan wait_for ceiling
  → wait_for CANCELS the gather; CancelledError is a BaseException
  → every `except Exception` in _judge_shadow / compute_setup_class_fields / collector is bypassed
  → the post-try `r["setup_class"] = ...` never runs in scan 1; scans 2 and 3 are fast (cookie
    cached) and carry the key.

Reproduced deterministically with the REAL ceiling in scripts/probes/_663_stall_the_first_upgrade_
fetch.py (stall the first fetch 27s: both guards fail with `KEY PRESENT ONLY IN B: <root>[0]
.setup_class`). The 2026-09-14 LOCAL failure of the toggle-OFF guard ran the same harness, the same
unguarded call and the same ceiling; no log survived it, so it is inferred from the mechanism, not
observed. It was never cross-test module state: that class was ruled out on 2026-09-22 by poisoning
every derived holder, and this file keeps a guard over it anyway (test 3).

THE FIX, in three parts, each pinned below:
  1. ep_detector seeds the three advisory keys in SYNCHRONOUS code BEFORE the post-scan try (shape
     cannot depend on a cancel, an import or the toggle read). Values unchanged — readers are `.get`.
  2. the #624 harness no longer leaves the process (upgrade-events stubbed; yfinance Ticker and DNS
     lookups recorded).
  3. tests/conftest.py resets the per-run module caches before every test (the isolation half).
"""
from __future__ import annotations

import ast
import asyncio
import inspect
import logging
import re
import textwrap

import pytest

from agents.market_intelligence import ep_detector
from agents.market_intelligence import setup_class_classifier as scc
from tests._byte_identity import assert_byte_identical
from tests._module_state import WATCHED, reset_all, state_holders
from tests.test_624_lowcap_lane import (
    _DNS_LOOKUPS, _YF_TICKER_CALLS, ADMIT_TICKER, SESSION_DATE, _run_scan_once,
)

_EP_LOGGER = "agents.market_intelligence.ep_detector"


def _stall_the_first_upgrade_fetch(monkeypatch, stall_s: float) -> dict:
    """Install, AFTER the harness's own stub, an upgrade-events fetch whose FIRST call sleeps past
    the ceiling and whose later calls return at once — the 2026-09-14 shape (cold Yahoo bootstrap
    once per process, warm afterwards). Installed by wrapping `run_ep_scan`, because
    `_run_scan_once` stubs the same name inside itself and the last patch wins."""
    calls = {"n": 0}

    async def _first_call_stalls(ticker):
        calls["n"] += 1
        if calls["n"] == 1:
            await asyncio.sleep(stall_s)
        return []

    real_run = ep_detector.run_ep_scan

    async def _run(*a, **k):
        monkeypatch.setattr(scc, "get_recent_upgrade_events", _first_call_stalls)
        return await real_run(*a, **k)

    monkeypatch.setattr(ep_detector, "run_ep_scan", _run)
    return calls


# ── 1. THE RED-PROOF: a post-scan ceiling timeout keeps the keys PRESENT (as None) ───────────

@pytest.mark.asyncio
async def test_a_post_scan_ceiling_timeout_keeps_the_advisory_keys_present_as_none(monkeypatch, caplog):
    """The 2026-09-14 mechanism, driven through the REAL wait_for → cancel → TimeoutError path with
    the ceiling shrunk through the hoisted constant (a 26-second sleep is not a suite test).

    Mutation that proves this test: delete the `for _r in high + moderate: _r.setdefault(...)`
    loop ahead of the post-scan try in ep_detector.run_ep_scan — `setup_class` goes absent and
    the `in` assertion fails, while test_624's exception-path test
    (test_a_setup_class_failure_changes_the_value_not_the_result_shape) stays green, because an
    exception is NOT a cancel. That is exactly the gap d747f414 left."""
    monkeypatch.setattr(ep_detector, "_POST_SCAN_CEILING_SHADOW_S", 0.3)
    calls = _stall_the_first_upgrade_fetch(monkeypatch, stall_s=30.0)

    with caplog.at_level(logging.WARNING, logger=_EP_LOGGER):
        results, _scan_log, alerts, _lane = await _run_scan_once(monkeypatch, lane_mode="off", admit=True)

    # the ceiling REALLY fired (positive observable — a stall that never tripped it proves nothing)
    ceiling_hits = [rec for rec in caplog.records if "post-scan block failed" in rec.getMessage()]
    assert len(ceiling_hits) == 1, [rec.getMessage() for rec in caplog.records]
    assert ceiling_hits[0].getMessage().endswith(": "), (
        "expected the empty-message TimeoutError the CI log showed — got "
        f"{ceiling_hits[0].getMessage()!r}")
    assert calls["n"] == 1   # the stalled call is the only one; it was cancelled, not retried

    assert len(results) == 1 and results[0]["ticker"] == ADMIT_TICKER and len(alerts) == 1
    for key in ("setup_class", "catalyst_type", "catalyst_type_rationale"):
        assert key in results[0], (
            f"{key} vanished under a cancel — the result's SHAPE depends on the ceiling again")
        assert results[0][key] is None, (key, results[0][key])
    # and the keys the DB-first contract keeps absent until a row write succeeds stay absent — a
    # cancel must not INVENT them either
    for key in ("fire_axes", "judge_rationale", "judge_grade"):
        assert key not in results[0]


# ── 2. THE HARNESS IS HERMETIC: no scan here may wait on anything outside the process ────────

@pytest.mark.asyncio
async def test_the_admit_harness_never_leaves_the_process(monkeypatch):
    """Until 2026-10-03 every admitted scan in test_624 constructed `yf.Ticker("BIG00")` and asked
    Yahoo for its upgrade history — one 404 per scan in the captured log, and on a cold runner
    a 25-second stall. A guard over the money path may not depend on Yahoo being fast.

    Mutation that proves this test: remove the `get_recent_upgrade_events` stub from
    `_run_scan_once` — the real collector path constructs a Ticker, the recorder catches it and
    the first assertion fails (the scan itself stays green: collector swallows the error)."""
    _YF_TICKER_CALLS.clear()
    _DNS_LOOKUPS.clear()
    results, *_ = await _run_scan_once(monkeypatch, lane_mode="on", admit=True)
    assert len(results) == 1   # the admitted path really ran (the classifier was reached)
    assert _YF_TICKER_CALLS == [], (
        f"a scan constructed yfinance.Ticker for {_YF_TICKER_CALLS} — a live Yahoo call is back "
        "on the harness path; stub it where ep_detector resolves it (see _run_scan_once)")
    assert _DNS_LOOKUPS == [], (
        f"a scan resolved host(s) {_DNS_LOOKUPS} — something on the harness path reaches the "
        "network; find the caller and stub it in _run_scan_once")


# ── 3. PRIOR STATE: fresh, leftover and poisoned module state give one and the same scan ──────

#: What an earlier test could plausibly leave in each per-run holder — keyed by name so the
#: DERIVED population (tests/_module_state.state_holders) decides what must be covered; a holder
#: this table does not know FAILS the test rather than being silently skipped.
_POISON = {
    # ep_detector
    "_audit_dedupe": lambda: {(ADMIT_TICKER, SESSION_DATE, "ep_catalyst_graded")},
    "_audit_dedupe_date": lambda: SESSION_DATE,
    "_catalyst_cache": lambda: {"ZZZZ": None},          # the harness re-seeds this one itself
    "_catalyst_cache_date": lambda: SESSION_DATE,
    "_corp_action_set": lambda: {ADMIT_TICKER},
    "_corp_action_date": lambda: SESSION_DATE,
    "_repoll_shadow_state": lambda: {ADMIT_TICKER: {"count": 1, "quality": "game_changer",
                                                    "logged": True, "ext_filings": None}},
    "_repoll_shadow_date": lambda: SESSION_DATE,
    "_rt_fresh_seen": lambda: {ADMIT_TICKER},
    "_rt_fresh_seen_date": lambda: SESSION_DATE,
    "_tinycap_seen": lambda: {ADMIT_TICKER},
    "_tinycap_seen_date": lambda: SESSION_DATE,
    "_yoy_bg_started_date": lambda: SESSION_DATE,
    # ep_theme_belonging (the module indexes these by key — keep the keys, poison the values)
    "_ctx_cache": lambda: {"key": ("poisoned",), "ctx": object()},
    "_fit_cache": lambda: {(SESSION_DATE, ADMIT_TICKER, ("Grid",)): ("confirmed", "Grid", "Accelerating", "stale")},
    "_fit_day": lambda: {"date": SESSION_DATE, "calls": 3},
}


def _poison_every_holder() -> list[str]:
    import importlib
    poisoned = []
    for mod_name in WATCHED:
        mod = importlib.import_module(mod_name)
        for name in sorted(state_holders(mod)):
            assert name in _POISON, (
                f"{mod_name}.{name} is a per-run state holder this test has no poison for — add "
                "one (what would an earlier test leave in it?) so the guard keeps covering the "
                "whole derived population")
            value = _POISON[name]()
            cur = getattr(mod, name, None)
            if isinstance(cur, dict) and isinstance(value, dict):
                cur.clear(); cur.update(value)          # keep the object the module indexes
            elif isinstance(cur, set) and isinstance(value, set):
                cur.clear(); cur.update(value)
            else:
                setattr(mod, name, value)
            poisoned.append(f"{mod_name.rsplit('.', 1)[-1]}.{name}")
    return poisoned


@pytest.mark.asyncio
async def test_run_ep_scan_is_byte_identical_across_fresh_leftover_and_poisoned_module_state(monkeypatch):
    """Three scans in ONE process: after a full reset, on whatever the first scan left behind,
    and with EVERY derived per-run holder pre-populated with the admitted ticker and the session
    date. All three must be byte-identical — this is the cross-test-state class the 2026-09-22
    poisoning ruled out one holder at a time, kept as a standing guard over the whole derived
    population so a new first-call-does-X cache cannot reintroduce it unnoticed."""
    reset_all()
    fresh = await _run_scan_once(monkeypatch, lane_mode="off", admit=True)
    leftover = await _run_scan_once(monkeypatch, lane_mode="off", admit=True)   # no reset between
    poisoned_names = _poison_every_holder()
    # the table and the derived population name the SAME members, both ways — a holder with no
    # poison fails inside _poison_every_holder; a poison for a holder that no longer exists fails
    # here, so the table cannot rot in either direction (a count floor would catch neither)
    import importlib
    derived = {n for m in WATCHED for n in state_holders(importlib.import_module(m))}
    assert set(_POISON) == derived, (set(_POISON) ^ derived)
    assert sorted(n.rsplit(".", 1)[-1] for n in poisoned_names) == sorted(derived)
    assert ADMIT_TICKER in ep_detector._tinycap_seen           # the poison really is in place
    poisoned = await _run_scan_once(monkeypatch, lane_mode="off", admit=True)

    assert len(fresh[0]) == 1 and fresh[0][0]["ticker"] == ADMIT_TICKER and len(fresh[2]) == 1
    for other, what in ((leftover, "fresh vs leftover state"), (poisoned, "fresh vs poisoned state")):
        assert_byte_identical(fresh[0], other[0], f"results ({what})")
        assert_byte_identical(fresh[1], other[1], f"scan_log rows ({what})")
        assert_byte_identical(fresh[2], other[2], f"alert inserts ({what})")


# ── 4. THE GATE: no result key may be written ONLY inside a try or a cancellable coroutine ─────

#: Keys the DB-first contract keeps ABSENT until the judge's row write succeeds ("never show what
#: the row doesn't have" — tests/test_tape_quality.py pins the discipline for tape_quality /
#: vol_profile; these are the judge's). Seeding them would break that contract, so they are
#: exempt BY NAME, each with its reason; a new try-only key is not.
_ABSENT_UNTIL_WRITTEN = {
    "fire_axes": "the judge's fire signal — DB-first, written to r only after the row write",
    "judge_rationale": "judge display field, same DB-first discipline as fire_axes",
    "judge_materiality_tier": "judge display field, same DB-first discipline as fire_axes",
    "judge_direction": "judge display field, same DB-first discipline as fire_axes",
    "judge_grade": "judge display field, same DB-first discipline as fire_axes",
    "judge_grade_reason": "judge display field, same DB-first discipline as fire_axes",
    "judge_tier_reason": "judge display field, same DB-first discipline as fire_axes",
}

_RESULT_NAMES = {"r", "result", "_r"}

#: Nested defs whose body IS the plain result builder, not a cancellable side-coroutine: each is
#: awaited INLINE by the graded loop (never under a gather / wait_for), so its writes run in the
#: scan's own control flow and are walked as plain body. Named, with the reason, and pinned below.
_INLINE_AWAITED_DEFS = {
    "_grade_admitted": "the graded tail of the per-candidate loop, extracted 2026-10-10 for the "
                       "#624 paper lane; the live loop does `await _grade_admitted(c, ticker, "
                       "rel_volume)` directly — the result dict literal is built here",
}


def _result_key_writes(fn: ast.AsyncFunctionDef) -> dict:
    """{key: [(lineno, how, context)]} for every write to the result dict inside `fn`.
    context is 'seed' when the write sits in fn's OWN body outside every Try (body, handlers,
    else, finally) and outside every nested def; otherwise it names what encloses it."""
    writes: dict = {}
    try_nodes = (ast.Try, ast.TryStar) if hasattr(ast, "TryStar") else (ast.Try,)

    def add(key, lineno, how, ctx):
        writes.setdefault(key, []).append((lineno, how, ctx))

    def ctx_of(in_try, nested):
        if not in_try and not nested:
            return "seed"
        return " / ".join((["try"] if in_try else []) + [f"def {n}" for n in nested])

    def record(stmt, in_try, nested):
        if isinstance(stmt, ast.Assign):
            targets = []
            for t in stmt.targets:
                targets.extend(t.elts if isinstance(t, ast.Tuple) else [t])
            for t in targets:
                if (isinstance(t, ast.Subscript) and isinstance(t.value, ast.Name)
                        and t.value.id in _RESULT_NAMES and isinstance(t.slice, ast.Constant)):
                    add(t.slice.value, stmt.lineno, "assign", ctx_of(in_try, nested))
            if isinstance(stmt.value, ast.Dict) and any(
                    isinstance(t, ast.Name) and t.id in _RESULT_NAMES for t in stmt.targets):
                for k in stmt.value.keys:
                    if isinstance(k, ast.Constant):
                        add(k.value, stmt.lineno, "dict-literal", ctx_of(in_try, nested))
        if (isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Call)
                and isinstance(stmt.value.func, ast.Attribute) and stmt.value.func.attr == "setdefault"
                and isinstance(stmt.value.func.value, ast.Name)
                and stmt.value.func.value.id in _RESULT_NAMES
                and stmt.value.args and isinstance(stmt.value.args[0], ast.Constant)):
            add(stmt.value.args[0].value, stmt.lineno, "setdefault", ctx_of(in_try, nested))

    def walk(stmts, in_try, nested):
        """Statement-level walk: every statement is recorded exactly once, with the context it
        executes in. `r[k] = v`, `r.setdefault(k, v)` and `result = {...}` are all statements."""
        for stmt in stmts:
            if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if stmt.name in _INLINE_AWAITED_DEFS:
                    walk(stmt.body, in_try, nested)
                else:
                    walk(stmt.body, in_try, nested + [stmt.name])
                continue
            if isinstance(stmt, try_nodes):
                walk(stmt.body, True, nested)
                for h in stmt.handlers:
                    walk(h.body, True, nested)
                walk(stmt.orelse, True, nested)
                walk(stmt.finalbody, True, nested)
                continue
            record(stmt, in_try, nested)
            for field in ("body", "orelse"):            # if / for / while / with / async for / async with
                sub = getattr(stmt, field, None)
                if isinstance(sub, list):
                    walk(sub, in_try, nested)
            if isinstance(stmt, ast.Match):
                for case in stmt.cases:
                    walk(case.body, in_try, nested)

    walk(fn.body, False, [])
    return writes


def _run_ep_scan_ast() -> ast.AsyncFunctionDef:
    src = textwrap.dedent(inspect.getsource(ep_detector.run_ep_scan))
    return ast.parse(src).body[0]


def test_every_result_key_written_under_a_try_or_in_a_coroutine_is_seeded_outside_both():
    """AST gate over run_ep_scan's result builder. A key whose ONLY writers sit inside a try body
    (skipped by an exception) or inside a nested coroutine (skipped by a cancel) makes the
    result's shape depend on failure and timing — the `setup_class` class, twice. Every such key
    must also have a plain seed in run_ep_scan's own body, or be exempt by name with a reason.

    Decidable because it is SYNTACTIC: where a write sits, not whether it executes. It cannot see
    a key written by a helper that receives `r` (tape_quality.annotate_ep_alerts_tape_quality
    writes r['tape_quality'] — pinned by its own DB-first tests), and it treats a seed anywhere
    in the plain region as sufficient even if it sits after the try that it should precede; the
    RED-proof test above covers the one case where ORDER mattered.

    Mutation that proves this test: delete the seed loop ahead of the post-scan try — three keys
    (setup_class, catalyst_type, catalyst_type_rationale) are reported as try/coroutine-only."""
    # source-pin-ok: WHERE a key is written (inside a try / a cancellable coroutine) is a property of
    # the source, not of any one run — a behavioural test sees one failure mode at a time; the
    # RED-proof above exercises the ceiling path itself, this gate covers every key at once.
    # the inline-awaited exemption is real: each named def is awaited directly by the graded
    # loop, never handed to a gather / wait_for / create_task
    _src = inspect.getsource(ep_detector.run_ep_scan)
    for _name in _INLINE_AWAITED_DEFS:
        assert f"        await {_name}(c, ticker, rel_volume)" in _src, _name
        assert not re.search(rf"(gather|wait_for|create_task)\([^)]*{_name}\(", _src), _name
    writes = _result_key_writes(_run_ep_scan_ast())
    assert "ep_score" in writes and any(ctx == "seed" for _, _, ctx in writes["ep_score"]), (
        "the walker no longer sees the result dict literal — fix the gate before trusting it")
    unseeded = {k: v for k, v in writes.items()
                if not any(ctx == "seed" for _, _, ctx in v) and k not in _ABSENT_UNTIL_WRITTEN}
    assert not unseeded, (
        "result keys written ONLY inside a try or a nested coroutine, with no plain seed in "
        "run_ep_scan's own body — a failure or a cancel changes the result's SHAPE:\n  "
        + "\n  ".join(f"{k}: {v}" for k, v in sorted(unseeded.items()))
        + "\nSeed each with r.setdefault(key, None) BEFORE the block that writes it, or exempt it "
          "by name in _ABSENT_UNTIL_WRITTEN with the contract that keeps it absent.")
    # the exemptions are real: each named key IS still written try-only (a stale exemption is
    # an allowlist nobody reads)
    for k in _ABSENT_UNTIL_WRITTEN:
        assert k in writes and not any(ctx == "seed" for _, _, ctx in writes[k]), (
            f"{k} is exempt but is no longer a try-only write — drop the exemption")
    # and the three #663 keys ARE seeded, as a plain write, in the function's own body
    for k in ("setup_class", "catalyst_type", "catalyst_type_rationale"):
        assert any(ctx == "seed" and how == "setdefault" for _, how, ctx in writes[k]), writes[k]
    # The ceiling is read through the hoisted constants, not a literal put back: a literal 25
    # cannot be told apart by behaviour (same ceiling, same values) — only the RED-proof's
    # ability to shrink it would be lost, silently, as a 25-second test that still passes.
    src = inspect.getsource(ep_detector.run_ep_scan)
    assert "_POST_SCAN_CEILING_AUTHORITY_S if _judge_authority" in src
    assert "else _POST_SCAN_CEILING_SHADOW_S" in src
    assert "110 if _judge_authority else 25" not in src


def test_the_post_scan_ceiling_values_are_the_literals_they_replaced():
    """The hoist exists only so a test can shrink the ceiling; the live values must be the W2c
    (#243) numbers byte for byte."""
    assert ep_detector._POST_SCAN_CEILING_SHADOW_S == 25
    assert ep_detector._POST_SCAN_CEILING_AUTHORITY_S == 110
