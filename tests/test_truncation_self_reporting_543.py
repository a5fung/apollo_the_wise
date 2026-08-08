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

  1. every call site reports stop_reason (the column is worthless with holes in it), and
  2. a call site that FORGETS is itself reported — the NULL arm — so the hand-threading, which
     is the same copy-paste shape `spend_tracker`'s own docstring warns about, cannot quietly
     create the next blind spot.

Scope note: this catches the CEILING class only. It would NOT have caught the 08-06 extraction
outage — that response finished normally (`stop_reason='end_turn'`) and broke on a positional
`content[0]` assumption. Model-contract shape testing is #544, deliberately separate.
"""
import ast
import pathlib
import re

MI = pathlib.Path("agents/market_intelligence")
TRACKER = (MI / "spend_tracker.py").read_text(encoding="utf-8")
BOARD = (MI / "cost_board.py").read_text(encoding="utf-8")
SCHED = (MI / "scheduler.py").read_text(encoding="utf-8")


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
    assert '"max_tokens" if str(finish_reason) == "length"' in TRACKER, (
        "Perplexity's 'length' is no longer mapped to 'max_tokens' — the truncation check "
        "silently stops covering the Perplexity callers")


def test_perplexity_rows_are_never_null():
    """NULL is reserved to mean 'a call site forgot to report'. If Perplexity rows were NULL
    too, the NULL arm would cry wolf on them nightly and get ignored — the failure mode that
    kills every over-broad guard in this repo."""
    assert 'else (str(finish_reason) if finish_reason is not None else "n/a")' in TRACKER, (
        "Perplexity rows can write NULL stop_reason, which collides with the "
        "missing-call-site meaning of NULL")


# ── every call site reports ───────────────────────────────────────────────────────────────

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


def test_every_call_site_reports_why_the_model_stopped():
    """The column is only as good as its coverage. A site that omits the kwarg writes NULL
    and becomes un-checkable — which is precisely the state the whole system was in until
    today."""
    missing = [
        f"{f}:{ln} ({fn})" for f, ln, fn, kw in _call_sites()
        if not ({"stop_reason", "finish_reason"} & kw)
    ]
    assert not missing, (
        "these spend-tracker call sites do not report why the model stopped, so truncation "
        "there is invisible (#543): " + ", ".join(missing))


def test_a_forgotten_call_site_warns_at_runtime():
    """Belt-and-braces for the site added AFTER this test was written: the tracker itself
    logs a WARNING when stop_reason is absent, so it shows up in logs even before the
    nightly check reports it."""
    assert "no stop_reason passed" in TRACKER, (
        "log_anthropic_call no longer warns when a call site omits stop_reason")


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
    """core/spend.py writes to the SAME api_usage table from the orchestrator container. If it
    never reported stop_reason, its callers would be NULL forever and the nightly NULL arm
    would fire every single night — a guard that always fires is not a guard."""
    src = pathlib.Path("core/spend.py").read_text(encoding="utf-8")
    assert "ALTER TABLE api_usage ADD COLUMN IF NOT EXISTS stop_reason TEXT" in src, (
        "core/spend.py's schema is out of parity with spend_tracker's — whichever container "
        "boots first wins and the column may never appear")
    assert "stop_reason" in src.split("INSERT INTO api_usage")[1][:400], (
        "core/spend.py's INSERT omits stop_reason")
    import ast as _ast
    missing = []
    for path in ("core/context.py", "core/orchestrator.py", "channels/telegram.py"):
        tree = _ast.parse(pathlib.Path(path).read_text(encoding="utf-8"))
        for node in _ast.walk(tree):
            if isinstance(node, _ast.Call) and getattr(node.func, "id", None) == "log_api_usage":
                if "stop_reason" not in {k.arg for k in node.keywords if k.arg}:
                    missing.append(f"{path}:{node.lineno}")
    assert not missing, (
        "orchestrator-side spend call sites not reporting stop_reason: " + ", ".join(missing))


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
