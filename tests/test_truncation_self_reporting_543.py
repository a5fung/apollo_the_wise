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
"""
import ast
import inspect
import pathlib
import re

import pytest

MI = pathlib.Path("agents/market_intelligence")
def _code_only(src: str) -> str:
    """Source with comments and docstrings removed.

    An ABSENCE assertion against raw source is self-defeating: the comment recording why a
    phrase was removed contains that phrase. Four tests in this repo have failed on their own
    explanation. Only executable text can honestly answer "does the code still say X?".
    """
    import io
    import tokenize
    out, prev_end, prev_tok = [], (1, 0), None
    for tok in tokenize.generate_tokens(io.StringIO(src).readline):
        if tok.type == tokenize.COMMENT:
            continue
        if tok.type == tokenize.STRING and prev_tok in (None, tokenize.INDENT,
                                                        tokenize.NEWLINE, tokenize.NL):
            continue  # a bare string expression = a docstring
        if tok.start != prev_end:
            out.append(" ")
        out.append(tok.string)
        prev_end, prev_tok = tok.end, tok.type
    return "".join(out)

TRACKER = (MI / "spend_tracker.py").read_text(encoding="utf-8")
BOARD = (MI / "cost_board.py").read_text(encoding="utf-8")
SCHED = (MI / "scheduler.py").read_text(encoding="utf-8")
SPEND = pathlib.Path("core/spend.py").read_text(encoding="utf-8")


# ── the column ────────────────────────────────────────────────────────────────────────────

def test_stop_reason_column_is_added_to_an_existing_table():
    """CREATE TABLE IF NOT EXISTS is a no-op everywhere the table already exists — which is
    everywhere. Without the ALTER, prod would keep the old 9-column table and every INSERT
    would fail on the unknown column."""
    assert "ALTER TABLE api_usage ADD COLUMN IF NOT EXISTS stop_reason TEXT" in TRACKER, (
        "the stop_reason column is only in CREATE TABLE — it will never appear on the "
        "existing prod table, and the INSERT below it will fail")


def test_both_inserts_write_stop_reason():
    """Two INSERT sites (Anthropic + Perplexity). One omitting the column silently produces
    NULLs for a whole provider, which the check would then report as a wiring gap forever."""
    inserts = re.findall(r"INSERT INTO api_usage\s*\n\s*\(([^)]*)\)", TRACKER)
    assert len(inserts) == 2, f"expected 2 api_usage INSERT sites, found {len(inserts)}"
    for cols in inserts:
        assert "stop_reason" in cols, f"an api_usage INSERT omits stop_reason: {cols!r}"


def test_perplexity_truncation_is_normalised_to_anthropic_vocabulary():
    """Perplexity says finish_reason='length' for the same event Anthropic calls
    stop_reason='max_tokens'. If the two are not normalised, ONE check cannot cover both
    providers and the cheaper Perplexity path becomes the blind spot."""
    assert '"max_tokens" if str(reason) == "length"' in TRACKER, (
        "Perplexity's 'length' is no longer mapped to 'max_tokens' — the truncation check "
        "silently stops covering the Perplexity callers")


def test_perplexity_rows_are_never_null():
    """NULL is reserved to mean 'stop_reason genuinely could not be derived'. If Perplexity
    rows were NULL too, the NULL arm would cry wolf on them nightly and get ignored — the
    failure mode that kills every over-broad guard in this repo."""
    assert 'else (str(reason) if reason is not None else "n/a")' in TRACKER, (
        "Perplexity rows can write NULL stop_reason, which collides with the "
        "unreported-caller meaning of NULL")


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


def test_derivation_goes_through_the_canonical_response_readers():
    """`shared.llm_response` is the one place that reads a response (#544). If the trackers
    re-grow their own getattr chains, the next response-shape change lands in one copy and
    not the other — the exact bug class both #543 and #544 exist to end."""
    for src, label in ((TRACKER, "spend_tracker.py"), (SPEND, "core/spend.py")):
        assert "from shared.llm_response import" in src, (
            f"{label} no longer derives usage/stop_reason via shared.llm_response — "
            "response introspection is being re-implemented locally")
    assert 'getattr(usage, "input_tokens"' not in TRACKER, (
        "spend_tracker hand-rolls usage reading again instead of using shared.llm_response")


def test_a_shapeless_response_still_warns_at_runtime():
    """Belt-and-braces: if a response stops carrying stop_reason (SDK/shape drift), the
    tracker WARNs immediately — logs first, then the nightly NULL arm the next morning."""
    assert "carries no stop_reason" in TRACKER, (
        "log_anthropic_call no longer warns when a response carries no stop_reason")


# ── the detection ─────────────────────────────────────────────────────────────────────────

def test_the_check_reports_truncation():
    assert "async def run_truncation_check" in BOARD
    assert "stop_reason = 'max_tokens'" in BOARD, (
        "the truncation check no longer counts max_tokens rows")


def test_the_check_also_reports_callers_that_never_report():
    """The half that keeps the hand-threading honest. Without it, site 21 is silent and we
    are back where we started."""
    assert "stop_reason IS NULL" in BOARD, "the NULL/unreported arm is gone"
    assert "unreported" in BOARD


def test_a_partially_null_caller_is_not_flagged_as_a_wiring_gap():
    """A provider omitting the field on SOME responses is not a call-site defect. Flagging
    those would make the NULL arm fire constantly and get muted."""
    assert 'int(r["unreported"]) == calls' in BOARD, (
        "the unreported arm no longer requires a caller to report NOTHING — it will now "
        "cry wolf on partial NULLs")


def test_one_truncation_on_a_chatty_caller_is_not_an_alert():
    """A guard that always fires is not a guard (the week's own lesson). Two truncations, or
    a majority of a low-volume caller's calls, is the bar."""
    assert "_TRUNC_MIN_CALLS = 2" in BOARD
    assert "_TRUNC_PCT_FLOOR = 50.0" in BOARD


def test_the_alert_is_not_deduped():
    """theme_assignment went quiet for ten days because its only trace looked routine. This
    one keeps shouting nightly until the ceiling is actually raised."""
    assert "Deliberately NOT deduped" in BOARD, (
        "the truncation alert appears to have been deduped — an ongoing corruption that "
        "announces once and then goes quiet is the bug, not the fix")


def test_the_check_actually_runs():
    """An inert detector is worse than none — this repo has shipped one before. The 17:52 ET
    spend job is already registered, so riding it is what makes this live."""
    assert "run_truncation_check" in SCHED, (
        "the truncation check is not wired into any scheduled job — it will never run")
    seg = SCHED.split("run_truncation_check")[-1][:600]
    assert "except Exception" in seg, (
        "the truncation check is not isolated behind its own except — a failure in it would "
        "blot out the spend alarm and cost watchdog it shares a job with")


# ── the ceilings that were pegged ─────────────────────────────────────────────────────────

def test_the_three_pegged_ceilings_were_raised():
    """Measured 2026-08-07 over 7 days: theme_synthesis 60% of calls at exactly 4000,
    theme_discovery 28.6% at 4000, ep_grade_judge 14.3% at exactly 500. Raising is the
    unblock; the check above is what stops the next one hiding for three months."""
    syn = (MI / "theme_synthesis.py").read_text(encoding="utf-8")
    eng = (MI / "theme_engine.py").read_text(encoding="utf-8")
    judge = (MI / "ep_grade_judge.py").read_text(encoding="utf-8")
    assert "max_tokens=8000" in syn, "theme_synthesis ceiling is back below 8000"
    assert "_DISCOVERY_MAX_TOKENS = 8000" in eng, "theme_discovery ceiling is back below 8000"
    m = re.search(r"max_tokens=(\d+)", judge)
    assert m and int(m.group(1)) >= 1500, (
        "ep_grade_judge is back on the 500-token transport default — one entry grade in "
        "seven was decided by truncation at that ceiling (ADR 0011, load-bearing on entry)")


# ── a truncated verdict must not become a grade ───────────────────────────────────────────

def test_a_truncated_judge_verdict_fails_open():
    """MEASURED 2026-08-07, and it is not what anyone assumed: a `max_tokens` cut on a forced
    tool call still yields a `tool_use` block with PARTIAL input. grade/tier/direction come
    first in the JSON and survive; rationale and confidence get cut. `_normalize_verdict`
    reads those with `.get()`, so it returned a complete-LOOKING verdict from an incomplete
    answer — 7 of 49 ep_grade_judge verdicts had NULL confidence (exactly the 7 at-cap calls)
    and two of them PROMOTED to HIGH with a zero-length rationale. HIGH drives the alert and
    the ORB entry.

    ADR 0011 §Fail-open already says a judge error takes the conviction floor. A response we
    cut off IS a judge error. This is that rule finally being enforceable."""
    src = (MI / "judge_transport.py").read_text(encoding="utf-8")
    assert "is_truncated(resp)" in src, (
        "the shared judge transport no longer discards truncated verdicts — a cut-off "
        "response can again be graded on, including promotions to HIGH (ADR 0011)")
    assert "judge_verdict_truncated" in src, "the truncated-verdict audit trail is gone"
    # it must bail BEFORE normalize() ever sees the partial input
    head = src.split("is_truncated(resp)")[1]
    assert head.index("return None") < head.index("normalize(tool_block.input)"), (
        "the truncation check no longer short-circuits before normalize() — a partial verdict "
        "would still be built")


def test_the_orchestrator_container_reports_stop_reason_too():
    """core/spend.py writes to the SAME api_usage table from the orchestrator container — it
    was missed once already on this exact task, which would have left the NULL arm firing
    nightly forever. Same response-only contract, same three enforcement layers."""
    assert "ALTER TABLE api_usage ADD COLUMN IF NOT EXISTS stop_reason TEXT" in SPEND, (
        "core/spend.py's schema is out of parity with spend_tracker's — whichever container "
        "boots first wins and the column may never appear")
    assert "stop_reason" in SPEND.split("INSERT INTO api_usage")[1][:400], (
        "core/spend.py's INSERT omits stop_reason")

    # Signature: response-only, so an orchestrator-side site cannot forget either.
    from core.spend import log_api_usage
    params = set(inspect.signature(log_api_usage).parameters)
    assert params == {"model", "caller", "response"}, (
        f"log_api_usage signature drifted to {params} — the orchestrator container is back "
        "on the omittable-kwarg contract")
    with pytest.raises(TypeError):
        log_api_usage(model="m", caller="c", input_tokens=1, output_tokens=1)

    # Every orchestrator-side call site passes the raw response and none uses the old shape.
    import ast as _ast
    bad = []
    seen = 0
    for path in ("core/context.py", "core/orchestrator.py", "channels/telegram.py"):
        tree = _ast.parse(pathlib.Path(path).read_text(encoding="utf-8"))
        for node in _ast.walk(tree):
            if isinstance(node, _ast.Call) and getattr(node.func, "id", None) == "log_api_usage":
                seen += 1
                kw = {k.arg for k in node.keywords if k.arg}
                if "response" not in kw or ({"input_tokens", "output_tokens", "stop_reason"} & kw):
                    bad.append(f"{path}:{node.lineno}")
    assert seen >= 3, f"only {seen} log_api_usage call sites found — the orchestrator scan is broken"
    assert not bad, (
        "orchestrator-side spend call sites not on the response-only contract: " + ", ".join(bad))


def test_a_caller_that_truncates_BY_DESIGN_does_not_alert():
    """Found by running the check against prod, not by reasoning about it: the orchestrator's
    `healthcheck` sends the literal word "ping" with max_tokens=5 and throws the text away —
    it only cares that the API answered. It reports stop_reason='max_tokens' on every single
    call, forever, and would have fired this alert nightly from day one. A guard that always
    fires is not a guard."""
    assert "_TRUNC_BY_DESIGN" in BOARD, "the by-design truncation exemption is gone"
    assert '"healthcheck"' in BOARD.split("_TRUNC_BY_DESIGN = {")[1][:300], (
        "healthcheck is no longer exempt — it pings with max_tokens=5 and will alert every "
        "night forever")
    assert 'r["caller"] not in _TRUNC_BY_DESIGN' in BOARD, (
        "the exemption is declared but never applied")


def test_the_exemption_list_stays_short():
    """It is the one place a real outage could hide. Every entry needs a stated reason."""
    seg = BOARD.split("_TRUNC_BY_DESIGN = {")[1].split("}")[0]
    entries = [ln for ln in seg.strip().split("\n") if ln.strip().startswith('"')]
    assert len(entries) <= 3, (
        f"{len(entries)} callers are exempt from the truncation alert — this list is becoming "
        "the blind spot it was meant to prevent")
    for e in entries:
        assert "#" in e, f"exempt caller with no stated reason: {e.strip()}"


def test_both_truncation_guards_share_ONE_definition_of_truncated():
    """The check was hand-copied into the shared judge transport and the catalyst grader on the
    same night, and the second copy's own comment said "same rule the shared judge transport
    now enforces" — the duplication was noticed and committed anyway. That is the
    `extract_stop_leg_id` shape, and this repo has a standing rule against it.

    The PREDICATE is shared; the HANDLING is deliberately not. `judge_transport` returns None
    into its fail-open; `ep_detector` RAISES, because its enclosing `except` is what runs the
    #273 credit-exhaustion alert. Two contracts, one definition."""
    from shared.llm_response import is_truncated
    assert is_truncated({"stop_reason": "max_tokens"})
    assert not is_truncated({"stop_reason": "end_turn"})
    assert not is_truncated(None)

    for f in ("judge_transport.py", "ep_detector.py"):
        src = (MI / f).read_text(encoding="utf-8")
        assert "from shared.llm_response import is_truncated" in src, (
            f"{f} no longer uses the shared truncation predicate — the next change to what "
            '"truncated" means will land in one copy and not the other')
    ep = (MI / "ep_detector.py").read_text(encoding="utf-8")
    assert 'getattr(response, "stop_reason", None) == "max_tokens"' not in ep, (
        "ep_detector hand-rolls the truncation check again")


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

class _FakeUsageConn:
    """Routes the two shapes compute_truncation_check issues: the instrumentation-floor
    fetchval, and the per-caller GROUP BY. `rows` is filtered by the floor the way Postgres
    would, so the test exercises the actual exclusion rather than asserting an argument."""

    def __init__(self, floor, rows):
        self._floor, self._rows = floor, rows
        self.floor_applied = None

    async def fetchval(self, sql, *args):
        assert "min(created_at)" in sql and "stop_reason IS NOT NULL" in sql
        return self._floor

    async def fetch(self, sql, *args):
        assert "created_at >= $2" in sql, (
            "the per-caller query no longer applies an instrumentation floor — it will blame "
            "callers for rows written before stop_reason was ever recorded")
        self.floor_applied = args[1]
        kept = [r for r in self._rows if r["at"] >= args[1]]
        agg: dict[str, dict] = {}
        for r in kept:
            a = agg.setdefault(r["caller"], {"caller": r["caller"], "calls": 0,
                                             "truncated": 0, "unreported": 0, "cap_hit": None})
            a["calls"] += 1
            a["truncated"] += r["stop_reason"] == "max_tokens"
            a["unreported"] += r["stop_reason"] is None
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


def _run_check(monkeypatch, floor, rows):
    import asyncio
    from agents.market_intelligence import cost_board as cb
    conn = _FakeUsageConn(floor, rows)
    monkeypatch.setattr(cb, "get_pool", lambda: _fake_pool(conn))
    return asyncio.run(cb.compute_truncation_check()), conn


async def _fake_pool(conn):
    return _FakeUsagePool(conn)


def test_a_null_row_written_before_instrumentation_is_not_a_wiring_gap(monkeypatch):
    """The exact 2026-08-08 false positive, replayed."""
    from datetime import datetime, timedelta, timezone
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
    from datetime import datetime, timedelta, timezone
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
    assert out["instrumentation_dark"] is True
    assert out["truncating"] == [] and out["unreported"] == []


def test_the_alert_no_longer_blames_a_missing_kwarg():
    """Post-refactor a call site structurally cannot omit stop_reason, so 'your call site is
    missing stop_reason' points the reader at provably correct code."""
    assert "call site is missing stop_reason" not in _code_only(BOARD), (
        "the NOT-REPORTING alert still tells the operator a call site is missing the kwarg — "
        "impossible since 2026-08-08, and it misdirected the reader the first night it fired")
