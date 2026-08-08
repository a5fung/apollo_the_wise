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
