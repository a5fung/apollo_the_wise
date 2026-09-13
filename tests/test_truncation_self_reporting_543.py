"""A max_tokens ceiling could only ever be hit SILENTLY — until now (#543, 2026-08-07).

`theme_assignment` spent exactly its 4000-token ceiling on every call from 07-28 to 08-07 and
produced not one assignment. Nothing said so. The operator found it by asking, and his words
were: *"we really need to figure out how we can miss this, a complete outage, and it's a bug
we've seen before, unacceptable."*

It IS a bug we had seen before. The same ceiling was raised 1000 → 4000 in May 2026 for the
same silent failure; raising it bought three months. `theme_synthesis`'s own source comment,
written in June, predicted this exact recurrence and named the fix — *"unless we record the
stop_reason"* — and then it recurred anyway, because the comment was a note and not a column.

So the fix is not a bigger number. It is that **the model now tells us it was cut off**:
`api_usage.stop_reason` is recorded on every call, and a daily check turns `'max_tokens'` into
a 🔴 Telegram. These tests pin the two halves that make that non-optional:

  1. a call site structurally CANNOT omit stop_reason (2026-08-08): the loggers take the RAW
     RESPONSE and derive usage + stop_reason together — the old split `usage=`/`stop_reason=`
     kwargs are REMOVED, so the forgetting bug is impossible rather than detected. The AST
     scan below fails the build on any site not passing `response=`, and the removed kwargs
     raise TypeError at runtime, and
  2. the NULL arm stays as DEFENCE IN DEPTH — it now guards the residue structure can't reach
     (a response shape that stops carrying stop_reason; a writer outside the two sanctioned
     trackers), not the primary forgetting case.

Scope note: this catches the CEILING class only. It would NOT have caught the 08-06 extraction
outage — that response finished normally (`stop_reason='end_turn'`) and broke on a positional
`content[0]` assumption. Model-contract shape testing is #544, deliberately separate.

2026-09-13 (#653 cleanup): 18 of these tests pinned SOURCE TEXT (`TRACKER`/`BOARD`/`SCHED`/
`SPEND` module-level file reads, grepped for a literal string) instead of calling the code and
checking what it does. All 18 are now CONVERTED to drive the real functions — `log_anthropic_
call`, `log_perplexity_call`, `log_api_usage`, `compute_truncation_check`, `run_truncation_
check`, `_spend_alarm_job`, `invoke_forced_tool`, `_classify_catalyst_claude` — against a mocked
DB/Telegram boundary, and assert on the REAL executed SQL, bound parameters, returned dicts, or
rendered alert text. One (`test_the_exemption_list_stays_short`) keeps a single tagged source
read: a per-entry inline comment is not observable at runtime (a frozenset value carries no
trace of the comment beside it in the file), so only that one fact stays a reviewed pin —
everything else in that test converted to a real behavioral length check on the live registry.
The 9 tests never flagged by the source-pin gate (they call `_call_sites()`/`MI`-scoped AST
scans through a `for`-loop path variable, which the gate's static heuristic doesn't trace) are
untouched — they were already behavioral in substance.
"""
import ast
import asyncio
import inspect
import pathlib
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

MI = pathlib.Path("agents/market_intelligence")


# ── the column, the inserts, the perplexity normalization (behavioral) ─────────────────────
#
# Faking the DB connection and inspecting the ACTUAL executed SQL + bound parameters is
# strictly stronger than grepping the .py source for the same literals: it proves the column
# really gets written, with the real value, by the real code path a live call takes — not
# merely that the words appear somewhere in the file (which a dead branch or a comment would
# also satisfy).

class _FakeSpendConn:
    def __init__(self):
        self.executed: list[tuple] = []

    async def execute(self, sql, *args):
        self.executed.append((sql, args))

    async def fetchrow(self, sql, *args):
        return None  # _measured_history: no diagnosis history needed by these tests


class _FakeSpendPool:
    def __init__(self, conn):
        self._conn = conn

    def acquire(self):
        conn = self._conn

        class _Ctx:
            async def __aenter__(self):
                return conn

            async def __aexit__(self, *a):
                return False
        return _Ctx()


def _wire_spend_tracker(monkeypatch):
    """`spend_tracker.get_pool` is bound at MODULE level (imported once at spend_tracker.py's
    own top), so a plain monkeypatch on the module attribute reaches every caller inside it —
    unlike `run_inert_sweep_check` elsewhere in this repo, there is no local re-import to chase
    here."""
    from agents.market_intelligence import spend_tracker as st
    conn = _FakeSpendConn()

    async def _pool():
        return _FakeSpendPool(conn)
    monkeypatch.setattr(st, "get_pool", _pool)
    monkeypatch.setattr(st, "_SCHEMA_ENSURED", False)  # force _ensure_schema to actually run
    # The LIVE truncation alarm (_maybe_alert_truncation, 2026-08-09) is a separate mechanism
    # with its own DB/Telegram reach — neutralize it so these tests exercise only the #543
    # write-path contract under test, not that alarm's own side effects.
    monkeypatch.setattr(st, "_maybe_alert_truncation", AsyncMock())
    return st, conn


def _wire_core_spend(monkeypatch):
    import core.spend as csp
    conn = _FakeSpendConn()

    async def _pool():
        return _FakeSpendPool(conn)
    monkeypatch.setattr(csp, "_get_pool", _pool)
    monkeypatch.setattr(csp, "_check_budget_alert", AsyncMock())
    return csp, conn


def _anthropic_response(*, output_tokens=10, stop_reason="end_turn", input_tokens=5):
    return {"usage": {"input_tokens": input_tokens, "output_tokens": output_tokens,
                      "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0},
            "stop_reason": stop_reason}


def _pplx_response(*, finish_reason="stop", prompt_tokens=5, completion_tokens=10):
    choices = [{"finish_reason": finish_reason}] if finish_reason is not None else [{}]
    return {"usage": {"prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens},
            "choices": choices}


def test_stop_reason_column_is_added_to_an_existing_table(monkeypatch):
    """MUTATION TARGET: the ALTER dropped from _ensure_schema (or replaced with something
    that never actually runs against an EXISTING table). CREATE TABLE IF NOT EXISTS is a
    no-op everywhere the table already exists — which is everywhere — so only the ALTER
    that's REALLY EXECUTED adds the column to prod."""
    st, conn = _wire_spend_tracker(monkeypatch)
    asyncio.run(st.log_anthropic_call(model="m", caller="c", response=_anthropic_response()))
    ddl = conn.executed[0][0]
    assert "ALTER TABLE api_usage ADD COLUMN IF NOT EXISTS stop_reason TEXT" in ddl, (
        "the real schema-ensure statement no longer adds the column")


def test_both_inserts_write_stop_reason(monkeypatch):
    """MUTATION TARGET: one of the two INSERT sites (Anthropic, Perplexity) drops
    stop_reason from its bound parameters — that provider's rows would silently write NULL
    forever, and the NULL arm would then blame a call site that is actually fine."""
    st, conn = _wire_spend_tracker(monkeypatch)
    asyncio.run(st.log_anthropic_call(model="m", caller="c",
                                       response=_anthropic_response(stop_reason="end_turn")))
    sql, params = conn.executed[-1]
    assert "stop_reason" in sql and params[-1] == "end_turn", (
        "the real Anthropic INSERT does not bind a stop_reason value")

    st2, conn2 = _wire_spend_tracker(monkeypatch)
    asyncio.run(st2.log_perplexity_call(caller="c", response=_pplx_response(finish_reason="stop")))
    sql2, params2 = conn2.executed[-1]
    assert "stop_reason" in sql2 and params2[-1] == "stop", (
        "the real Perplexity INSERT does not bind a stop_reason value")


def test_perplexity_truncation_is_normalised_to_anthropic_vocabulary(monkeypatch):
    """MUTATION TARGET: the 'length'->'max_tokens' normalization removed. Perplexity says
    finish_reason='length' for the same event Anthropic calls stop_reason='max_tokens' — if
    the two are not normalised, ONE nightly check cannot cover both providers and the cheaper
    Perplexity path becomes the blind spot."""
    st, conn = _wire_spend_tracker(monkeypatch)
    asyncio.run(st.log_perplexity_call(caller="c", response=_pplx_response(finish_reason="length")))
    _, params = conn.executed[-1]
    assert params[-1] == "max_tokens", (
        "Perplexity's 'length' finish_reason must be written as Anthropic's 'max_tokens'")


def test_perplexity_rows_are_never_null(monkeypatch):
    """MUTATION TARGET: an absent finish_reason writing a real NULL stop_reason. NULL is
    reserved to mean 'a call site forgot to report' (#543); a real Perplexity response with
    no finish_reason must still write a non-NULL sentinel, or the NULL arm cries wolf on
    healthy Perplexity rows nightly and gets ignored — the failure mode that kills every
    over-broad guard in this repo."""
    st, conn = _wire_spend_tracker(monkeypatch)
    asyncio.run(st.log_perplexity_call(caller="c", response=_pplx_response(finish_reason=None)))
    _, params = conn.executed[-1]
    assert params[-1] == "n/a" and params[-1] is not None, (
        "a Perplexity response with no finish_reason must not write NULL stop_reason")


# ── the forgetting bug is IMPOSSIBLE, not detected (2026-08-08) ──────────────────────────
#
# The loggers take the RAW RESPONSE and derive usage + stop_reason together. Three layers
# make a forgotten stop_reason impossible rather than next-morning-detected:
#   a. the functions no longer HAVE usage=/stop_reason=/finish_reason= parameters — an
#      old-style call raises TypeError at the call site (pinned by signature + probe below);
#   b. the AST scan fails the build on any call site that does not pass `response=`;
#   c. the nightly NULL arm (cost_board) stays as defence in depth for what structure cannot
#      reach.

def _call_sites():
    """Every spend_tracker invocation in the package, found by parsing rather than grepping —
    a grep for the old kwarg shape would miss a site written differently."""
    out = []
    for path in sorted(MI.rglob("*.py")):
        if path.name == "spend_tracker.py":
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:  # pragma: no cover
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            fn = node.func
            name = getattr(fn, "id", None) or getattr(fn, "attr", None)
            if name in ("log_anthropic_call", "log_anthropic_call_safe", "log_perplexity_call"):
                out.append((path.name, node.lineno, name,
                            {k.arg for k in node.keywords if k.arg}))
    return out


def test_there_are_call_sites_to_check():
    """Guards the test itself: an AST walk that finds nothing would pass every assertion
    below while proving nothing."""
    assert len(_call_sites()) >= 20, (
        f"only found {len(_call_sites())} spend-tracker call sites — the AST scan is broken, "
        "and a broken scan makes the coverage test below vacuously green")


def test_every_call_site_passes_the_raw_response():
    """The whole #543 close-out: cost and stop_reason travel as ONE object, so a site cannot
    report spend while leaving truncation invisible. A site that fails here was written
    against the pre-08-08 split-kwarg contract and would TypeError in production."""
    missing = [
        f"{f}:{ln} ({fn})" for f, ln, fn, kw in _call_sites()
        if "response" not in kw
    ]
    assert not missing, (
        "these spend-tracker call sites do not pass the raw response, so they cannot report "
        "why the model stopped (#543): " + ", ".join(missing))


def test_no_call_site_uses_the_removed_split_kwargs():
    """The old shape must not creep back in — a `usage=` site compiles fine and only fails
    when the call actually runs (inside a try/except at half the sites, i.e. silently). The
    build is where it has to die."""
    stale = [
        f"{f}:{ln} ({fn})" for f, ln, fn, kw in _call_sites()
        if {"usage", "stop_reason", "finish_reason"} & kw
    ]
    assert not stale, (
        "these call sites still use the removed usage=/stop_reason=/finish_reason= kwargs "
        "(pre-08-08 contract): " + ", ".join(stale))


def test_the_split_kwargs_are_gone_from_the_functions_themselves():
    """Signature-level pin: the impossibility lives in the function, not in reviewer
    vigilance. If someone re-adds an optional stop_reason= kwarg 'for convenience', that is
    today's bug reintroduced — the silently-optional kwarg IS the defect class."""
    from agents.market_intelligence import spend_tracker

    for fn in (spend_tracker.log_anthropic_call, spend_tracker.log_anthropic_call_safe):
        params = set(inspect.signature(fn).parameters)
        assert params == {"model", "caller", "response"}, (
            f"{fn.__name__} signature drifted to {params} — the response-only contract is "
            "what makes a forgotten stop_reason impossible")
    pplx_params = set(inspect.signature(spend_tracker.log_perplexity_call).parameters)
    assert pplx_params == {"caller", "response", "model"}, (
        f"log_perplexity_call signature drifted to {pplx_params}")


def test_an_old_style_call_raises_instead_of_writing_nulls():
    """Runtime pin of the same fact: the pre-08-08 call shape must fail LOUDLY at the call
    site (TypeError on binding, before any coroutine or DB work exists), never degrade into
    a NULL row. This is the difference between impossible and detected."""
    from agents.market_intelligence import spend_tracker

    with pytest.raises(TypeError):
        spend_tracker.log_anthropic_call(
            model="m", caller="c", usage=object(), stop_reason="end_turn")
    with pytest.raises(TypeError):
        spend_tracker.log_anthropic_call_safe(model="m", caller="c", usage=object())
    with pytest.raises(TypeError):
        spend_tracker.log_perplexity_call(caller="c", usage={}, finish_reason="stop")
    # And the response argument is not optional — "forgot entirely" is also a TypeError.
    with pytest.raises(TypeError):
        spend_tracker.log_anthropic_call_safe(model="m", caller="c")


def test_derivation_goes_through_the_canonical_response_readers(monkeypatch):
    """MUTATION TARGET: either tracker re-implementing its own usage/stop_reason extraction
    instead of calling shared.llm_response — proven by patching the SHARED reader each
    module binds at ITS OWN import time, and confirming the tracker's REAL written row
    follows the patch. A local reimplementation (hand-rolled getattr chains) would ignore
    the patch and keep computing its own answer straight from the response."""
    st, conn = _wire_spend_tracker(monkeypatch)
    monkeypatch.setattr(st, "_usage_tokens_of", lambda r: {
        "input_tokens": 1, "output_tokens": 999,
        "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0})
    monkeypatch.setattr(st, "_stop_reason_of", lambda r: "SENTINEL_STOP")
    asyncio.run(st.log_anthropic_call(model="m", caller="c", response=_anthropic_response()))
    _, params = conn.executed[-1]
    assert "SENTINEL_STOP" in params, (
        "spend_tracker.log_anthropic_call did not route stop_reason through the shared "
        "reader — the written row must reflect the patched shared.llm_response.stop_reason")
    assert 999 in params, (
        "spend_tracker.log_anthropic_call did not route usage through the shared reader")

    csp, conn2 = _wire_core_spend(monkeypatch)
    monkeypatch.setattr(csp, "_usage_tokens_of", lambda r: {
        "input_tokens": 1, "output_tokens": 777,
        "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0})
    monkeypatch.setattr(csp, "_stop_reason_of", lambda r: "SENTINEL_STOP_2")
    asyncio.run(csp.log_api_usage(model="m", caller="c", response=_anthropic_response()))
    _, params2 = conn2.executed[-1]
    assert "SENTINEL_STOP_2" in params2 and 777 in params2, (
        "core/spend.py's log_api_usage did not route usage/stop_reason through the shared "
        "reader — the orchestrator container would be re-implementing response introspection")


def test_a_shapeless_response_still_warns_at_runtime(monkeypatch, caplog):
    """MUTATION TARGET: the runtime WARNING removed from log_anthropic_call when a response
    stops carrying stop_reason (SDK/shape drift) — belt-and-braces defence in depth
    alongside the nightly NULL arm, which only catches this the NEXT morning."""
    st, conn = _wire_spend_tracker(monkeypatch)
    response = {"usage": {"input_tokens": 5, "output_tokens": 10,
                          "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0}}
    # deliberately no "stop_reason" key at all
    with caplog.at_level("WARNING"):
        asyncio.run(st.log_anthropic_call(model="m", caller="c", response=response))
    assert any("carries no stop_reason" in r.message for r in caplog.records), (
        "a response with no stop_reason must warn at runtime, not fail silently")
    _, params = conn.executed[-1]
    assert params[-1] is None, "the row must still write NULL when the shape genuinely drifted"


# ── the detection (cost_board.compute_truncation_check / run_truncation_check) ─────────────

class _FakeUsageConn:
    """Routes the shapes compute_truncation_check issues: the instrumentation-floor
    fetchval, the per-caller GROUP BY, and (when any caller crosses the truncation
    threshold) the per-caller diagnosis-history query. `rows` is filtered by the floor the
    way Postgres would, so a test exercises the actual exclusion rather than asserting an
    argument."""

    def __init__(self, floor, rows):
        self._floor, self._rows = floor, rows
        self.floor_applied = None

    async def fetchval(self, sql, *args):
        assert "min(created_at)" in sql and "stop_reason IS NOT NULL" in sql
        return self._floor

    async def fetch(self, sql, *args):
        if "caller = ANY(" in sql:
            # The per-caller diagnosis-footer history query. No test here exercises the
            # rendered diagnosis text itself (that is shared/output_ceilings.py's own
            # concern) — empty history is a safe, always-valid answer.
            return []
        assert "created_at >= $2" in sql, (
            "the per-caller query no longer applies an instrumentation floor — it will blame "
            "callers for rows written before stop_reason was ever recorded")
        self.floor_applied = args[1]
        kept = [r for r in self._rows if r["at"] >= args[1]]
        agg: dict[str, dict] = {}
        for r in kept:
            a = agg.setdefault(r["caller"], {"caller": r["caller"], "calls": 0,
                                             "truncated": 0, "unreported": 0, "cap_hit": None,
                                             "max_completed": None})
            a["calls"] += 1
            a["truncated"] += r["stop_reason"] == "max_tokens"
            a["unreported"] += r["stop_reason"] is None
            # mirrors the near-ceiling FILTER: completed = known stop_reason, not truncated
            if r["stop_reason"] not in (None, "max_tokens"):
                out_tok = r.get("output_tokens", 0)
                a["max_completed"] = max(a["max_completed"] or 0, out_tok)
        return list(agg.values())


class _FakeUsagePool:
    def __init__(self, conn):
        self._conn = conn

    def acquire(self):
        conn = self._conn

        class _Ctx:
            async def __aenter__(self):
                return conn

            async def __aexit__(self, *a):
                return False
        return _Ctx()


async def _fake_pool(conn):
    return _FakeUsagePool(conn)


def _run_check(monkeypatch, floor, rows):
    from agents.market_intelligence import cost_board as cb
    conn = _FakeUsageConn(floor, rows)
    monkeypatch.setattr(cb, "get_pool", lambda: _fake_pool(conn))
    return asyncio.run(cb.compute_truncation_check()), conn


def _run_truncation_alert(monkeypatch, floor, rows):
    """Wires the same fake pool as `_run_check`, PLUS intercepts the real Telegram send and
    audit-log calls, then drives the REAL `run_truncation_check()` end-to-end. Returns the
    list of rendered message texts actually sent."""
    from agents.market_intelligence import cost_board as cb
    conn = _FakeUsageConn(floor, rows)
    monkeypatch.setattr(cb, "get_pool", lambda: _fake_pool(conn))

    audited = []

    async def _audit(event_type, summary, detail=""):
        audited.append((event_type, summary, detail))
    monkeypatch.setattr(cb, "log_audit_event", _audit)

    import agents.market_intelligence.briefing as briefing
    sent = []

    async def _send(msg, *a, **k):
        sent.append(msg)
        return True
    monkeypatch.setattr(briefing, "send_telegram_message", _send)

    asyncio.run(cb.run_truncation_check())
    return sent


_FLOOR = datetime(2026, 8, 8, 0, 53, tzinfo=timezone.utc)   # an arbitrary instrumenting instant


def test_the_check_reports_truncation(monkeypatch):
    """MUTATION TARGET: the truncation arm stops counting stop_reason='max_tokens' rows —
    proven by driving compute_truncation_check + run_truncation_check end-to-end and reading
    the ACTUAL 'truncating' result and rendered Telegram text, not the source."""
    rows = [{"caller": "theme_synthesis", "stop_reason": "max_tokens",
             "at": _FLOOR + timedelta(hours=1)} for _ in range(3)]
    out, _ = _run_check(monkeypatch, _FLOOR, rows)
    assert [x["caller"] for x in out["truncating"]] == ["theme_synthesis"]

    sent = _run_truncation_alert(monkeypatch, _FLOOR, rows)
    assert sent and "TRUNCATED" in sent[0] and "theme_synthesis" in sent[0], (
        "a truncating caller must actually reach the rendered Telegram alert")


def test_the_check_also_reports_callers_that_never_report(monkeypatch):
    """MUTATION TARGET: the NULL/unreported arm removed. Without it a caller that never
    writes stop_reason at all goes completely unnoticed — the exact blind spot #543 exists
    to close (site 21 is silent and we are back where we started)."""
    rows = [{"caller": "ghost_caller", "stop_reason": None, "at": _FLOOR + timedelta(hours=1)}
            for _ in range(4)]
    out, _ = _run_check(monkeypatch, _FLOOR, rows)
    assert [x["caller"] for x in out["unreported"]] == ["ghost_caller"]

    sent = _run_truncation_alert(monkeypatch, _FLOOR, rows)
    assert sent and "NOT REPORTING" in sent[0] and "ghost_caller" in sent[0]
    # Post-refactor a call site structurally cannot omit stop_reason, so blaming one
    # misdirects the reader — exactly what happened the first night this fired. Checked here
    # against the REAL rendered message, not a source grep.
    assert "call site is missing stop_reason" not in sent[0], (
        "the NOT-REPORTING alert must not tell the operator a call site is missing the "
        "kwarg — impossible since 2026-08-08")


def test_a_partially_null_caller_is_not_flagged_as_a_wiring_gap(monkeypatch):
    """MUTATION TARGET: the 'ALL calls unreported' requirement loosened to 'ANY call
    unreported'. A provider omitting the field on SOME responses is not a call-site defect;
    flagging it would make the NULL arm fire constantly and get muted."""
    rows = [
        {"caller": "sometimes_silent", "stop_reason": None, "at": _FLOOR + timedelta(hours=1)},
        {"caller": "sometimes_silent", "stop_reason": "end_turn", "at": _FLOOR + timedelta(hours=2)},
    ]
    out, _ = _run_check(monkeypatch, _FLOOR, rows)
    assert out["unreported"] == [], (
        "a caller that reports SOMETIMES must not be flagged as a wiring gap")


def test_one_truncation_on_a_chatty_caller_is_not_an_alert(monkeypatch):
    """MUTATION TARGET: the min-calls/pct-floor thresholds loosened or removed. A guard that
    always fires is not a guard: one truncation among many calls is noise; two is a
    pattern; and a single truncating call on a LOW-volume caller (100%) is the real outage
    shape and must still fire."""
    chatty = [{"caller": "chatty", "stop_reason": "max_tokens" if i == 0 else "end_turn",
              "at": _FLOOR + timedelta(hours=1)} for i in range(20)]
    out, _ = _run_check(monkeypatch, _FLOOR, chatty)
    assert out["truncating"] == [], "1 truncation out of 20 calls must not alert"

    chatty2 = ([{"caller": "chatty2", "stop_reason": "max_tokens",
                "at": _FLOOR + timedelta(hours=h)} for h in (1, 2)]
              + [{"caller": "chatty2", "stop_reason": "end_turn",
                  "at": _FLOOR + timedelta(hours=3)} for _ in range(18)])
    out2, _ = _run_check(monkeypatch, _FLOOR, chatty2)
    assert [x["caller"] for x in out2["truncating"]] == ["chatty2"], (
        "2 truncations must alert regardless of how low the percentage is")

    lowvolume = [{"caller": "lowvolume", "stop_reason": "max_tokens",
                 "at": _FLOOR + timedelta(hours=1)}]
    out3, _ = _run_check(monkeypatch, _FLOOR, lowvolume)
    assert [x["caller"] for x in out3["truncating"]] == ["lowvolume"], (
        "a single call at 100% truncated is the low-volume outage shape and must alert")


def test_the_alert_is_not_deduped(monkeypatch):
    """MUTATION TARGET: a dedup layer added around the Telegram send. theme_assignment went
    quiet for ten days because its only trace looked routine — this check must keep
    shouting nightly until the ceiling is actually fixed, never suppress a repeat."""
    rows = [{"caller": "theme_synthesis", "stop_reason": "max_tokens",
             "at": _FLOOR + timedelta(hours=1)} for _ in range(3)]
    sent_1 = _run_truncation_alert(monkeypatch, _FLOOR, rows)
    sent_2 = _run_truncation_alert(monkeypatch, _FLOOR, rows)
    assert sent_1 and sent_2, "an ongoing truncation must alert on EVERY run, not just the first"


def test_the_check_actually_runs(monkeypatch):
    """MUTATION TARGET: run_truncation_check un-wired from the 17:52 spend job, or its own
    try/except removed so a failure in it blots out the (already-vetted) spend-alarm and
    cost-watchdog checks that share the job."""
    import agents.market_intelligence.cost_board as cb
    import agents.market_intelligence.scheduler as sched
    calls = []

    async def _spend_alarm(*a, **k):
        calls.append("spend_alarm")
        return False

    async def _watchdog(*a, **k):
        calls.append("watchdog")
        return False

    async def _boom():
        calls.append("truncation")
        raise RuntimeError("boom: truncation check broke")

    monkeypatch.setattr(cb, "run_daily_spend_alarm", _spend_alarm)
    monkeypatch.setattr(cb, "run_cost_watchdog", _watchdog)
    monkeypatch.setattr(cb, "run_truncation_check", _boom)
    failures = []

    async def _notify(job, err):
        failures.append(job)
    monkeypatch.setattr(sched, "notify_job_failure", _notify)

    asyncio.run(sched._spend_alarm_job())

    assert calls == ["spend_alarm", "watchdog", "truncation"], (
        "the truncation check must actually be reached by the 17:52 spend job")
    assert failures == ["truncation_check"], (
        "a broken truncation check must be reported by NAME, isolated from the other two "
        "(already-vetted) checks that share the job")


# ── the ceilings that were pegged ─────────────────────────────────────────────────────────

def test_the_three_pegged_ceilings_were_raised():
    """Measured 2026-08-07 over 7 days: theme_synthesis 60% of calls at exactly 4000,
    theme_discovery 28.6% at 4000, ep_grade_judge 14.3% at exactly 500. Raising is the
    unblock; the check above is what stops the next one hiding for three months.

    2026-08-09: the numbers moved into shared/output_ceilings.py (one registry with
    provenance) — assert the registered value holds AND the site binds from it."""
    from shared.output_ceilings import max_tokens_for

    assert max_tokens_for("theme_synthesis") >= 8000, "theme_synthesis ceiling is back below 8000"
    assert max_tokens_for("theme_discovery") >= 8000, "theme_discovery ceiling is back below 8000"
    assert max_tokens_for("ep_grade_judge") >= 1500, (
        "ep_grade_judge is back on the 500-token transport default — one entry grade in "
        "seven was decided by truncation at that ceiling (ADR 0011, load-bearing on entry)")
    for fname, caller in (("theme_synthesis.py", "theme_synthesis"),
                          ("theme_engine.py", "theme_discovery"),
                          ("ep_grade_judge.py", "ep_grade_judge")):
        src = (MI / fname).read_text(encoding="utf-8")
        assert f'max_tokens_for("{caller}")' in src, (
            f"{fname} no longer binds its ceiling from shared/output_ceilings.py — a "
            "re-hardcoded literal is the rot the registry exists to end")


# ── a truncated verdict must not become a grade ───────────────────────────────────────────

class _FakeJudgeMessages:
    def __init__(self, response):
        self._response = response

    async def create(self, **kwargs):
        return self._response


class _FakeJudgeClient:
    def __init__(self, response):
        self.messages = _FakeJudgeMessages(response)


def test_a_truncated_judge_verdict_fails_open(monkeypatch):
    """MEASURED 2026-08-07, and it is not what anyone assumed: a `max_tokens` cut on a
    forced tool call still yields a `tool_use` block with PARTIAL input. grade/tier/direction
    come first in the JSON and survive; rationale and confidence get cut. MUTATION TARGET:
    the `is_truncated(resp)` short-circuit removed (or moved AFTER normalize()), so a
    truncated tool_use block gets normalized into a complete-LOOKING verdict built from an
    incomplete answer — 7 of 49 ep_grade_judge verdicts had NULL confidence (exactly the 7
    at-cap calls) and two of them PROMOTED to HIGH with a zero-length rationale. ADR 0011
    §Fail-open already says a judge error takes the conviction floor; a response cut off IS
    a judge error."""
    import agents.market_intelligence.db as db_mod
    audited = []

    async def _audit(event_type, subject, detail):
        audited.append((event_type, subject, detail))
    monkeypatch.setattr(db_mod, "log_audit_event", _audit)

    normalize_calls = []

    def _normalize(tool_input):
        normalize_calls.append(tool_input)
        return {"grade": tool_input.get("grade")}

    resp = SimpleNamespace(
        stop_reason="max_tokens",
        content=[SimpleNamespace(type="tool_use", input={"grade": "HIGH"})])
    client = _FakeJudgeClient(resp)

    from agents.market_intelligence import judge_transport as jt
    result = asyncio.run(jt.invoke_forced_tool(
        client, "prompt", tool={}, tool_name="t", normalize=_normalize,
        label="ep_grade_judge", subject="AMRC", timeout=5, model="m"))

    assert result is None, "a truncated response must fail open, never a partial verdict"
    assert normalize_calls == [], (
        "normalize() must never see a truncated tool_use input — the check must bail out "
        "BEFORE it, not after")
    assert any(e[0] == "judge_verdict_truncated" for e in audited), (
        "a truncated verdict must leave its own audit trail")


def test_the_orchestrator_container_reports_stop_reason_too():
    """core/spend.py writes to the SAME api_usage table from the orchestrator container — it
    was missed once already on this exact task, which would have left the NULL arm firing
    nightly forever. Same response-only contract, same three enforcement layers. (The
    ALTER/INSERT/derivation halves of this contract are covered behaviorally by
    test_derivation_goes_through_the_canonical_response_readers above — this test covers the
    signature-level impossibility and the real orchestrator-side call sites.)"""
    from core.spend import log_api_usage
    params = set(inspect.signature(log_api_usage).parameters)
    assert params == {"model", "caller", "response"}, (
        f"log_api_usage signature drifted to {params} — the orchestrator container is back "
        "on the omittable-kwarg contract")
    with pytest.raises(TypeError):
        log_api_usage(model="m", caller="c", input_tokens=1, output_tokens=1)

    # Every orchestrator-side call site passes the raw response and none uses the old shape.
    bad = []
    seen = 0
    for path in ("core/context.py", "core/orchestrator.py", "channels/telegram.py"):
        tree = ast.parse(pathlib.Path(path).read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "log_api_usage":
                seen += 1
                kw = {k.arg for k in node.keywords if k.arg}
                if "response" not in kw or ({"input_tokens", "output_tokens", "stop_reason"} & kw):
                    bad.append(f"{path}:{node.lineno}")
    assert seen >= 3, f"only {seen} log_api_usage call sites found — the orchestrator scan is broken"
    assert not bad, (
        "orchestrator-side spend call sites not on the response-only contract: " + ", ".join(bad))


def test_a_caller_that_truncates_BY_DESIGN_does_not_alert(monkeypatch):
    """Found by running the check against prod, not by reasoning about it: the
    orchestrator's `healthcheck` sends the literal word "ping" with max_tokens=5 and throws
    the text away — it only cares that the API answered. It reports
    stop_reason='max_tokens' on EVERY call, forever. MUTATION TARGET: the by-design
    exemption dropped, or `healthcheck` removed from shared/output_ceilings.py's
    TRUNCATION_BY_DESIGN — proven by feeding a REAL by-design caller through the REAL
    check, not by grepping for the set's name."""
    from shared.output_ceilings import TRUNCATION_BY_DESIGN
    assert "healthcheck" in TRUNCATION_BY_DESIGN, (
        "healthcheck is no longer exempt — it pings with max_tokens=5 and would alert "
        "every night forever")
    rows = [{"caller": "healthcheck", "stop_reason": "max_tokens",
             "at": _FLOOR + timedelta(hours=1)} for _ in range(50)]
    out, _ = _run_check(monkeypatch, _FLOOR, rows)
    assert out["truncating"] == [], (
        "healthcheck truncates on EVERY call by design — the exemption must silence it "
        "even though it meets every raw threshold")


def test_the_exemption_list_stays_short():
    """It is the one place a real outage could hide. Every entry needs a stated reason."""
    from shared.output_ceilings import TRUNCATION_BY_DESIGN
    assert len(TRUNCATION_BY_DESIGN) <= 3, (
        f"{len(TRUNCATION_BY_DESIGN)} callers are exempt from the truncation alert — this "
        "list is becoming the blind spot it was meant to prevent")
    # source-pin-ok: a stated reason is a COMMENT beside the entry, which a runtime
    # frozenset value carries no trace of — the length above is checked on the live
    # registry; only "does every entry carry a reason" needs the file's actual text.
    src = pathlib.Path("shared/output_ceilings.py").read_text(encoding="utf-8")
    seg = src.split("TRUNCATION_BY_DESIGN = frozenset({")[1].split("})")[0]
    entries = [ln for ln in seg.strip().split("\n") if ln.strip().startswith('"')]
    for e in entries:
        assert "#" in e, f"exempt caller with no stated reason: {e.strip()}"


def test_both_truncation_guards_share_ONE_definition_of_truncated(monkeypatch):
    """The check was hand-copied into the shared judge transport and the catalyst grader on
    the same night, and the second copy's own comment said "same rule the shared judge
    transport now enforces" — the duplication was noticed and committed anyway. MUTATION
    TARGET: either call site re-implementing its own truncation check (e.g.
    `getattr(response, "stop_reason", None) == "max_tokens"`) instead of calling the shared
    `is_truncated` — proven by PATCHING the name each module binds at its OWN import time
    and confirming behavior FOLLOWS the patch. A local reimplementation would ignore the
    patch and keep computing the real answer straight from the response."""
    from shared.llm_response import is_truncated
    assert is_truncated({"stop_reason": "max_tokens"})
    assert not is_truncated({"stop_reason": "end_turn"})
    assert not is_truncated(None)

    # judge_transport.py: force "truncated" on a GENUINELY complete response. If the call
    # site read the raw response instead of the patched predicate, it would normalize the
    # complete tool_use block rather than failing open.
    import agents.market_intelligence.db as db_mod
    import agents.market_intelligence.judge_transport as jt
    monkeypatch.setattr(db_mod, "log_audit_event", AsyncMock())
    monkeypatch.setattr(jt, "is_truncated", lambda resp: True)
    resp = SimpleNamespace(stop_reason="end_turn",
                           content=[SimpleNamespace(type="tool_use", input={"grade": "HIGH"})])
    normalize_calls = []
    result = asyncio.run(jt.invoke_forced_tool(
        _FakeJudgeClient(resp), "prompt", tool={}, tool_name="t",
        normalize=lambda i: (normalize_calls.append(i), {"grade": i.get("grade")})[1],
        label="ep_grade_judge", subject="AMRC", timeout=5, model="m"))
    assert result is None and normalize_calls == [], (
        "judge_transport did not consult the shared is_truncated — it read the raw "
        "response's own stop_reason instead of the patched predicate")

    # ep_detector.py: the opposite direction. Force "NOT truncated" on a response that
    # genuinely IS (max_tokens). If ep_detector re-implemented its own check, this patch
    # would have no effect and the raise-then-fail-open-to-routine path would fire anyway.
    from agents.market_intelligence import ep_detector, spend_tracker as st_mod
    monkeypatch.setattr(ep_detector, "is_truncated", lambda resp: False)
    monkeypatch.setattr(st_mod, "log_anthropic_call_safe", AsyncMock())
    block = MagicMock()
    block.type = "tool_use"
    block.input = {"quality": "game_changer", "analysis": "real catalyst"}
    truncated_resp = MagicMock()
    truncated_resp.content = [block]
    truncated_resp.stop_reason = "max_tokens"

    async def _mock_create(**kwargs):
        return truncated_resp

    with patch.object(ep_detector._get_claude(), "messages") as mock_msgs:
        mock_msgs.create = _mock_create
        quality, _analysis = asyncio.run(ep_detector._classify_catalyst_claude("AXTI", [], {}))
    assert quality == "game_changer", (
        "ep_detector did not consult the shared is_truncated — a genuinely truncated "
        "response should only fail open to 'routine' via that predicate; with it patched "
        "to say false, the real quality must come through untouched")


# ── the check must not blame a call site for rows that predate the mechanism ───────────────
#
# Its FIRST live night (2026-08-08) it Telegrammed 🟠 NOT REPORTING naming `theme_synthesis`,
# on the strength of a single NULL row from the 08-07 nightly theme run — written at 22:05
# UTC, three hours BEFORE the commit that instrumented that call site existed. The call site
# was provably correct; the row simply predated it, as every row in the table necessarily did
# at that moment. The alert text then sent the reader to "fix" a correct call site.
#
# These are BEHAVIOURAL, not source-scans: the bug was in what the query counted, and a grep
# for a constant cannot see that.

def test_a_null_row_written_before_instrumentation_is_not_a_wiring_gap(monkeypatch):
    """The exact 2026-08-08 false positive, replayed."""
    floor = datetime(2026, 8, 8, 0, 53, tzinfo=timezone.utc)   # the instrumenting commit
    rows = [
        # the 08-07 nightly run — NULL because stop_reason did not exist yet
        {"caller": "theme_synthesis", "stop_reason": None, "at": floor - timedelta(hours=3)},
        # a healthy post-instrumentation call from the same caller
        {"caller": "theme_synthesis", "stop_reason": "end_turn", "at": floor + timedelta(hours=1)},
    ]
    out, conn = _run_check(monkeypatch, floor, rows)
    assert conn.floor_applied == floor
    assert out["unreported"] == [], (
        "theme_synthesis was reported as not-reporting on the strength of a row written "
        "before stop_reason existed — the false positive this fix exists to remove")


def test_a_null_row_written_AFTER_instrumentation_is_still_caught(monkeypatch):
    """The floor must not become a blanket amnesty — a genuine gap appearing after the
    mechanism exists is precisely what this check is for."""
    floor = datetime(2026, 8, 8, 0, 53, tzinfo=timezone.utc)
    rows = [
        {"caller": "some_new_writer", "stop_reason": None, "at": floor + timedelta(days=1)},
    ]
    out, _ = _run_check(monkeypatch, floor, rows)
    assert [x["caller"] for x in out["unreported"]] == ["some_new_writer"]


def test_no_row_has_EVER_reported_is_its_own_louder_signal(monkeypatch):
    """If nothing anywhere reports stop_reason the mechanism itself is dark — strictly worse
    than one unwired caller. Returning an empty result would be the silent pass this whole
    check exists to prevent."""
    out, _ = _run_check(monkeypatch, None, [])
    assert out["since"] is None   # `since=None` IS the dark signal — one shape, no flag
    assert out["truncating"] == [] and out["unreported"] == []
