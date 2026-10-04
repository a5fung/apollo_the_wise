"""#691 — the monthly sweep tells him to "open /audit" on checks with nothing to act on, its judge
footer claims a blind spot that was fixed, and every `/audit <check>` pointer it prints is dead.

Operator 2026-10-01, on that day's digest: *"Any action from this?"* — seven of the twelve checks
(#50 #53 #54 #77 #78 #88 #94) landed in `output not auto-classified — open /audit`, and
`/audit mna_filter_accuracy_review` answered "Unknown audit topic".

WHAT THESE TESTS HOLD

(a) EVERY registered sweep script lands in a NAMED bucket — you / waiting / done — in EVERY verdict
    branch it can print. The population is DERIVED from `QUARTERLY_BACKWARD_CHECK_SCRIPTS`, never
    hand-listed: a newly registered script with no scenario below FAILS here, naming the script, so
    the next author must run their script's real formatting through the classifier before it ships.
    The scenarios execute each script's REAL `main()` against a fake DB pool with synthetic rows
    (the same text the sweep subprocess would produce), so rewording a verdict line without
    teaching `_NEEDS_YOU` / `_CONCLUDED` / `_WAITING` the new phrase goes RED here instead of
    silently asking him to open a report again.
(b) The judge footer states what it COUNTS and no longer claims the judge is blind / shown 'no'.
    (Pinned in tests/test_monthly_judge_review.py with the rest of that report.)
(c) Every `/audit <topic>` pointer the digest prints is answered by the REAL handler — never
    "Unknown audit topic" — and answers with the check's LAST STORED output (the sweep stores one
    audit row per check; the reader never re-runs a script).
"""
import asyncio
import contextlib
import importlib
import io
import json
import re
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

import pytest

from agents.market_intelligence import quarterly_review as qr

_ET = ZoneInfo("America/New_York")
_T = datetime(2026, 10, 1, 22, 0, tzinfo=timezone.utc)


# ═══════════════════════════════════════════════════════════════════════════════════════════
# (a) every registered script, every verdict branch → a named bucket
# ═══════════════════════════════════════════════════════════════════════════════════════════

class _Conn:
    """Hands back the next canned result for each fetch / fetchval, in call order."""

    def __init__(self, fetches=(), fetchvals=()):
        self._fetches, self._fetchvals = list(fetches), list(fetchvals)

    async def fetch(self, *a, **k):
        return self._fetches.pop(0)

    async def fetchval(self, *a, **k):
        return self._fetchvals.pop(0)


class _Acquire:
    def __init__(self, conn):
        self._conn = conn

    async def __aenter__(self):
        return self._conn

    async def __aexit__(self, *exc):
        return False


class _Pool:
    def __init__(self, conn):
        self._conn = conn

    def acquire(self, *a, **k):
        return _Acquire(self._conn)


def _run(monkeypatch, module, *, fetches=(), fetchvals=(), patches=None, entry=None):
    """Execute a registered script's REAL entry point against a fake pool; return its stdout."""
    mod = importlib.import_module(module)
    conn = _Conn(fetches, fetchvals)

    async def _get_pool():
        return _Pool(conn)

    async def _no_sleep(*a, **k):
        return None

    # Scripts import `get_pool` either lazily inside main() (patch the db module) or at module top
    # (patch the module's own name).
    monkeypatch.setattr("agents.market_intelligence.db.get_pool", _get_pool)
    if hasattr(mod, "get_pool"):
        monkeypatch.setattr(mod, "get_pool", _get_pool)
    monkeypatch.setattr(asyncio, "sleep", _no_sleep)          # #50 throttles 50ms per ticker
    for name, value in (patches or {}).items():
        monkeypatch.setattr(mod, name, value)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        asyncio.run(entry(mod) if entry else mod.main())
    assert not conn._fetches and not conn._fetchvals, "the script made fewer DB calls than the fixture feeds"
    return buf.getvalue()


# ── synthetic rows ─────────────────────────────────────────────────────────────────────────────

def _d(i):
    return date(2026, 9, 1 + (i % 25))


def _alerts(n, **kw):
    return [{"ticker": f"T{i}", "alert_date": _d(i), "ep_score": 80, "catalyst_quality": "strong",
             **{k: (v(i) if callable(v) else v) for k, v in kw.items()}} for i in range(n)]


def _b50(monkeypatch, rets, revenue=2_000_000):
    rows = _alerts(len(rets), ret_5d=lambda i: rets[i], ret_20d=None, max_high_5d=None)

    async def _rev(ticker):
        return revenue

    return _run(monkeypatch, "scripts._b50_revenue_stage_threshold_backward_check",
                fetches=[rows], patches={"fetch_revenue_avg": _rev})


def _b53(monkeypatch, rets):
    rows = _alerts(len(rets), gap_pct=5.0, atr14_pct=5.0, ret_5d=lambda i: rets[i])
    return _run(monkeypatch, "scripts._b53_atr_normalized_gap_backward_check", fetches=[rows])


def _b77(monkeypatch, rets):
    rows = _alerts(len(rets), pre20d_pct=0.0, ret_5d=lambda i: rets[i])
    return _run(monkeypatch, "scripts._b77_pradeep_neglect_backward_check", fetches=[rows])


def _b78(monkeypatch, rets):
    rows = _alerts(len(rets), gap_pct=12.0, pre20d_pct=-12.0, ret_5d=lambda i: rets[i])
    return _run(monkeypatch, "scripts._b78_decliner_band_bounce_signal", fetches=[rows])


def _b88(monkeypatch, paths):
    rows = [{"ticker": f"M{i}", "audit_date": _d(i),
             "detail": json.dumps({"match_path": p, "title": f"headline {i}"})}
            for i, p in enumerate(paths)]
    return _run(monkeypatch, "scripts._b88_mna_filter_path_b_fp_rate", fetches=[rows], fetchvals=[0])


def _b92(monkeypatch, n_per_stage):
    rows = []
    for stage in ("TRIGGERED", "COILED", "TIGHTENING", "WATCH"):
        rows += [{"ticker": f"{stage[:2]}{i}", "scan_date": _d(i), "stage": stage,
                  "ret_5d": 1.0, "ret_10d": 2.0} for i in range(n_per_stage)]
    return _run(monkeypatch, "scripts._b92_flag_detector_graduation_evidence", fetches=[rows])


def _b94(monkeypatch, rets):
    rows = [{"ticker": f"B{i}", "break_date": _d(i), "parent_stage": "TIGHTENING",
             "in_sugar_baby_cohort": i % 2 == 0, "ret_5d": r, "ret_10d": r}
            for i, r in enumerate(rets)]
    return _run(monkeypatch, "scripts._b94_intraday_flag_break_evidence",
                fetches=[rows], fetchvals=[0])


def _mna(monkeypatch, suppressed, passed):
    # #692 (2026-10-03) — the review reads FOUR result sets in order: suppressed, released by the
    # deal question, unanswered headline questions that passed, and #692b fail-safe rows (released
    # on price but kept blocked); each row carries `detail_full`.
    def _row(t, pk):
        return {"ticker": t, "fire_day": date(2026, 9, 10), "detail": "x", "detail_full": "x",
                "pk_vs_open": pk, "pk_vs_low": pk}
    return _run(monkeypatch, "scripts.mna_filter_accuracy_review",
                fetches=[[_row(f"S{i}", pk) for i, pk in enumerate(suppressed)],
                         [_row(f"P{i}", 1.0) for i in range(passed)],
                         [], []],
                entry=lambda mod: mod.main(35))


def _bar(i):
    """One ORB bar-1 whose high is a long upper wick (wick_ratio 0.8 >= the 0.70 outlier bar)."""
    return {"id": i, "ticker": f"W{i}", "alert_date": _d(i), "orb_high": 12.0, "orb_low": 9.5,
            "entry_price": 12.0, "stop_price": 9.5, "status": "open", "total_pnl": None,
            "closed_at": None, "bar_open": 10.0, "bar_high": 12.0, "bar_low": 9.5, "bar_close": 10.0}


def _wick(monkeypatch, n):
    return _run(monkeypatch, "scripts.orb_wick_outlier_backwardcheck",
                fetches=[[_bar(i) for i in range(n)], []])


def _cap1(monkeypatch, settled):
    rows = [{"ticker": f"G{i}", "alert_date": _d(i), "ep_score": 85.0,
             "catalyst_quality": "game_changer", "ret_5d": 0.04, "max_high_5d": 0.09}
            for i in range(settled)]
    return _run(monkeypatch, "scripts.shadow_cap_plus_one_197", fetches=[rows])


def _news(monkeypatch, drift_events):
    stats = {"Polygon": {"coverage_pct": 80.0, "density_median": 4, "attribution_pct": 30.0,
                         "n_extractions": 40, "coverage_count": 32, "attribution_count": 12}}

    async def _collect(start, end):
        return stats

    async def _drift():
        return {"drift_events": drift_events, "current_window": "2026-09-26..2026-10-02",
                "baseline_window": "2026-09-03..2026-09-25"}

    return _run(monkeypatch, "agents.market_intelligence.news_source_quality",
                patches={"collect_source_stats": _collect, "detect_drift": _drift},
                entry=lambda mod: mod.print_quarterly_summary())


_DRIFT = [{"source": "Polygon", "metric": "coverage_pct", "current_pct": 20.0, "baseline_pct": 80.0,
           "delta_pp": -60.0, "current_n": 40, "baseline_n": 90}]
_N = None   # an unsettled outcome

# (module, scenario, runner, expected bucket). ONE row per verdict branch the script can print.
# A scenario's bucket is pinned, not merely "not review": 'you' / 'waiting' / 'done' each mean
# something different to the operator.
SCENARIOS = [
    # #50 revenue bands — its own matrix: N>=10 and the $0-$5M band positive-edge / not.
    ("scripts._b50_revenue_stage_threshold_backward_check", "thin cohort",
     lambda mp: _b50(mp, [4.0, 6.0, -2.0]), "waiting"),
    ("scripts._b50_revenue_stage_threshold_backward_check", "positive-edge band",
     lambda mp: _b50(mp, [8.0] * 7 + [-2.0] * 5), "done"),
    ("scripts._b50_revenue_stage_threshold_backward_check", "band stopped paying",
     lambda mp: _b50(mp, [-3.0] * 12), "you"),
    # #53 / #77 — table-only monitors the operator already ruled on: INFORMATIONAL, not a green.
    ("scripts._b53_atr_normalized_gap_backward_check", "settled cohort",
     lambda mp: _b53(mp, [3.0, -1.0, 6.0]), "done"),
    ("scripts._b53_atr_normalized_gap_backward_check", "nothing settled",
     lambda mp: _b53(mp, [_N, _N]), "waiting"),
    ("scripts._b77_pradeep_neglect_backward_check", "settled cohort",
     lambda mp: _b77(mp, [3.0, -1.0, 6.0]), "done"),
    ("scripts._b77_pradeep_neglect_backward_check", "nothing settled",
     lambda mp: _b77(mp, [_N, _N]), "waiting"),
    # #78 decliner bounce — every arm of its N>=30 decision gate.
    ("scripts._b78_decliner_band_bounce_signal", "nothing settled",
     lambda mp: _b78(mp, [_N] * 4), "waiting"),
    ("scripts._b78_decliner_band_bounce_signal", "under 30 settled",
     lambda mp: _b78(mp, [6.0] * 5), "waiting"),
    ("scripts._b78_decliner_band_bounce_signal", "cleared its bar",
     lambda mp: _b78(mp, [8.0] * 30), "you"),
    ("scripts._b78_decliner_band_bounce_signal", "was noise",
     lambda mp: _b78(mp, [-2.0] * 30), "done"),
    ("scripts._b78_decliner_band_bounce_signal", "marginal",
     lambda mp: _b78(mp, [6.0] * 16 + [-1.0] * 14), "waiting"),
    # #88 M&A Path B — no events / only the EP classifier / too few / enough to score.
    ("scripts._b88_mna_filter_path_b_fp_rate", "no events yet",
     lambda mp: _b88(mp, []), "waiting"),
    ("scripts._b88_mna_filter_path_b_fp_rate", "only the claude classifier",
     lambda mp: _b88(mp, ["claude_classifier"] * 3), "waiting"),
    ("scripts._b88_mna_filter_path_b_fp_rate", "too few polygon fires",
     lambda mp: _b88(mp, ["title"] * 3), "waiting"),
    ("scripts._b88_mna_filter_path_b_fp_rate", "enough to score",
     lambda mp: _b88(mp, ["title"] * 4 + ["description+insights"] * 2), "you"),
    # #92 flag detector — structural no-go in every run (incl. the bright-spot arm).
    ("scripts._b92_flag_detector_graduation_evidence", "empty",
     lambda mp: _b92(mp, 0), "done"),
    ("scripts._b92_flag_detector_graduation_evidence", "tightening bright spot",
     lambda mp: _b92(mp, 60), "done"),
    # M&A accuracy review — the HARD-gate banner prints on EVERY run, so it always asks (pinned:
    # an empty month is indistinguishable from a broken audit feed, so it must not read as green).
    ("scripts.mna_filter_accuracy_review", "a suppression ran",
     lambda mp: _mna(mp, [150.0, 3.0], 1), "you"),
    ("scripts.mna_filter_accuracy_review", "empty month",
     lambda mp: _mna(mp, [], 0), "you"),
    # #94 flag break — every arm of its N>=10 gate.
    ("scripts._b94_intraday_flag_break_evidence", "nothing settled",
     lambda mp: _b94(mp, []), "waiting"),
    ("scripts._b94_intraday_flag_break_evidence", "under 10 settled",
     lambda mp: _b94(mp, [6.0] * 4), "waiting"),
    ("scripts._b94_intraday_flag_break_evidence", "cleared its bar",
     lambda mp: _b94(mp, [8.0] * 12), "you"),
    ("scripts._b94_intraday_flag_break_evidence", "weak",
     lambda mp: _b94(mp, [-4.0] * 12), "you"),
    ("scripts._b94_intraday_flag_break_evidence", "marginal",
     lambda mp: _b94(mp, [9.0] * 4 + [-2.0] * 8), "waiting"),
    # News source quality — no drift / drift.
    ("agents.market_intelligence.news_source_quality", "no drift",
     lambda mp: _news(mp, []), "done"),
    ("agents.market_intelligence.news_source_quality", "drift detected",
     lambda mp: _news(mp, _DRIFT), "you"),
    # #122 ORB wick outlier — N<10 / N>=10.
    ("scripts.orb_wick_outlier_backwardcheck", "empty cohort",
     lambda mp: _wick(mp, 0), "waiting"),
    ("scripts.orb_wick_outlier_backwardcheck", "under 10",
     lambda mp: _wick(mp, 3), "waiting"),
    ("scripts.orb_wick_outlier_backwardcheck", "enough to design a filter",
     lambda mp: _wick(mp, 12), "you"),
    # #197 cap+1 shadow — accruing / ready.
    ("scripts.shadow_cap_plus_one_197", "empty",
     lambda mp: _cap1(mp, 0), "waiting"),
    ("scripts.shadow_cap_plus_one_197", "accruing",
     lambda mp: _cap1(mp, 3), "waiting"),
    ("scripts.shadow_cap_plus_one_197", "ready",
     lambda mp: _cap1(mp, 10), "you"),
]


def _roster_modules():
    return [e[1] for e in qr.QUARTERLY_BACKWARD_CHECK_SCRIPTS]


def test_every_registered_script_has_a_scenario_and_every_scenario_a_registered_script():
    """THE POPULATION TEST. Derived from the roster, set-equal in BOTH directions, naming members.

    A new registered script with no scenario fails HERE — that is the whole point: its formatting
    has never been run through the classifier, so nobody knows whether it lands in 'review'. A
    scenario for a script that left the roster fails too (a retired check must not keep a test
    that implies it still runs)."""
    registered, covered = set(_roster_modules()), {m for m, *_ in SCENARIOS}
    assert registered - covered == set(), (
        f"registered sweep script(s) with NO scenario in tests/test_691_monthly_sweep_cleanup.py: "
        f"{sorted(registered - covered)} — add one scenario per verdict branch the script can print")
    assert covered - registered == set(), (
        f"scenario(s) for script(s) no longer in the sweep roster: {sorted(covered - registered)}")


@pytest.mark.parametrize("module,scenario,runner,expected", SCENARIOS,
                         ids=[f"{m.rsplit('.', 1)[-1]}::{s}" for m, s, *_ in SCENARIOS])
def test_each_script_branch_lands_in_its_pinned_bucket(monkeypatch, module, scenario, runner, expected):
    out = runner(monkeypatch)
    assert out.strip(), "the script printed nothing"
    bucket, note = qr._classify(out)
    assert bucket != "review", (
        f"{module} [{scenario}] prints a verdict the digest cannot read — it would land in "
        f"'output not auto-classified' and ask the operator to open a report with nothing to act on.\n"
        f"--- stdout tail ---\n" + "\n".join(out.splitlines()[-12:]))
    assert bucket == expected, f"{module} [{scenario}]: classified {bucket!r} ({note}); pinned {expected!r}"


def test_digest_run_on_every_script_output_puts_zero_checks_in_review(monkeypatch):
    """The DoD, end to end: render the REAL digest over every scenario's output."""
    results = []
    for module, scenario, runner, _ in SCENARIOS:
        label = next(e[0] for e in qr.QUARTERLY_BACKWARD_CHECK_SCRIPTS if e[1] == module)
        out = runner(monkeypatch)
        results.append({"label": f"{label} [{scenario}]", "module": module, "exit_code": 0,
                        "stdout_summary": qr._extract_summary_section(out), "stdout_full": out,
                        "stderr_tail": ""})
    digest = qr._render_digest(results, _T, 30.0)
    assert "not auto-classified" not in digest and "👀" not in digest, digest


def test_a_marker_is_red_when_removed(monkeypatch):
    """RED-PROOF of the harness: take one phrase away from the classifier and the matching branch
    must fall into 'review' — proving the scenarios exercise the markers, not just the boilerplate."""
    out = _b78(monkeypatch, [_N] * 4)                      # "No settled outcomes yet."
    assert qr._classify(out)[0] == "waiting"
    monkeypatch.setattr(qr, "_WAITING", [m for m in qr._WAITING if m[0] != "No settled outcomes yet"])
    assert qr._classify(out)[0] == "review"


def test_the_verdict_may_sit_past_the_25_line_summary():
    """#88's and #94's verdicts follow 40+ lines of tables; the classifier used to see only a
    25-line extract of them. It now reads the full stdout, and still falls back to the summary for
    results built without it (every pre-#691 test builds those)."""
    body = "\n".join(f"  row {i}  avg_5d +1.0%" for i in range(60))
    full = "BAND   N   avg_5d   win\n" + body + "\n→ N<30: KEEP OBSERVING.\n"
    assert "KEEP OBSERVING" not in qr._extract_summary_section(full)
    r = {"label": "x", "module": "m.x", "exit_code": 0, "stdout_summary": qr._extract_summary_section(full),
         "stdout_full": full, "stderr_tail": ""}
    assert "⏳" in qr._render_digest([r], _T, 1.0) and "👀" not in qr._render_digest([r], _T, 1.0)
    legacy = {"label": "x", "module": "m.x", "exit_code": 0, "stdout_summary": "KEEP OBSERVING", "stderr_tail": ""}
    assert "⏳" in qr._render_digest([legacy], _T, 1.0)


def test_unreadable_output_still_lands_in_review_never_clean():
    """The #513 invariant survives the rewrite: silence must not read as a pass."""
    assert qr._classify("some table nobody taught me to read")[0] == "review"


def test_54_is_off_the_roster_and_its_script_still_runs_by_hand():
    """#54 measures the 9M setup, which the operator ruled GONE. Retired like #223: out of the
    roster, script kept and importable (runnable by hand: `python -m scripts._b54_...`)."""
    assert "scripts._b54_9m_day2_stop_atr_distribution" not in _roster_modules()
    mod = importlib.import_module("scripts._b54_9m_day2_stop_atr_distribution")
    assert callable(mod.main)
    assert len(_roster_modules()) == 11


# ═══════════════════════════════════════════════════════════════════════════════════════════
# (c) every `/audit <topic>` pointer the digest prints works, and returns the stored output
# ═══════════════════════════════════════════════════════════════════════════════════════════

def _stored_row(topic, body="BAND  N  avg_5d\nrow ret_5d=+3.0%", bucket="done", code=0):
    return {"created_at": datetime(2026, 10, 1, 22, 5, tzinfo=timezone.utc),
            "summary": f"{topic} | exit={code} | {bucket}", "detail": body}


def _agent():
    from agents.market_intelligence.agent import MarketIntelligenceAgent
    return MarketIntelligenceAgent()


def _ask(agent, task):
    from shared.models import AgentRequest
    return asyncio.run(agent.execute_task(AgentRequest(task=task, user_id=1, conversation_id="t")))


def _pointers(digest):
    return re.findall(r"`/audit (\S+?)`", digest)


def _digest_with_every_pointer():
    """Every roster script forced into 'you' + one failed + one unreadable: every pointer shape the
    digest can print (NEEDS YOUR CALL, FAILED TO RUN, 👀 review)."""
    results = [{"label": e[0], "module": e[1], "exit_code": 0,
                "stdout_full": "<-- MATERIAL-MISS CANDIDATE", "stdout_summary": "", "stderr_tail": ""}
               for e in qr.QUARTERLY_BACKWARD_CHECK_SCRIPTS]
    results += [
        {"label": "Broken", "module": "scripts.shadow_cap_plus_one_197", "exit_code": 1,
         "stdout_full": "", "stdout_summary": "", "stderr_tail": "ImportError: boom"},
        {"label": "Unreadable", "module": "scripts.mna_filter_accuracy_review", "exit_code": 0,
         "stdout_full": "a table nobody taught me to read", "stdout_summary": "", "stderr_tail": ""}]
    return qr._render_digest(results, _T, 9.0)


def test_every_pointer_the_digest_prints_is_a_registered_check():
    topics = set(_pointers(_digest_with_every_pointer()))
    assert topics == set(qr.sweep_topics()), (
        "the digest prints a pointer that is not a registered check, or never prints one for a "
        f"registered check: {topics ^ set(qr.sweep_topics())}")


def test_sweep_topic_names_are_unique_and_do_not_shadow_a_metric_topic():
    from agents.market_intelligence.system_audit import _TOPIC_MAP
    tails = [qr.check_topic(m) for m in _roster_modules()]
    assert len(tails) == len(set(tails)), "two registered checks share a module tail"
    assert not (set(tails) & (set(_TOPIC_MAP) | {"job_runs"})), "a check name shadows a metric topic"


def test_every_digest_pointer_goes_through_the_real_handler_without_unknown_topic(monkeypatch):
    """THE DoD LINE: `/audit <topic>` for every topic the digest prints, via the real slash
    dispatch → `_handle_audit_topic` → `run_topic_audit`. Nothing stored yet (the day this ships)
    must be an honest 'no stored run', not 'Unknown audit topic'."""
    async def _none(topic):
        return None

    monkeypatch.setattr(qr, "fetch_stored_check", _none)
    agent = _agent()
    topics = _pointers(_digest_with_every_pointer())
    assert len(topics) >= 11
    for t in topics:
        res = _ask(agent, f"/audit {t}")
        assert res.success, (t, res.error)
        assert "Unknown audit topic" not in (res.result or ""), t
        assert "No stored run" in res.result, t


def test_audit_returns_the_checks_last_stored_table(monkeypatch):
    """`/audit mna_filter_accuracy_review` returns that check's last table — in a code block, so
    columns line up and `ret_5d`-style identifiers survive Telegram's formatter."""
    seen = {}

    async def _fetch(topic):
        seen["topic"] = topic
        return _stored_row(topic, body="SUPPRESSED (n=2)\n  ONDS  +24.0%  <-- MATERIAL-MISS CANDIDATE")

    monkeypatch.setattr(qr, "fetch_stored_check", _fetch)
    res = _ask(_agent(), "/audit mna_filter_accuracy_review")
    assert seen["topic"] == "mna_filter_accuracy_review"
    assert "ONDS  +24.0%" in res.result and "M&A filter accuracy review" in res.result
    assert "2026-10-01 15:05 PT" in res.result              # 22:05 UTC → PT, the operator's frame
    assert res.result.count("```") == 2


def test_a_topic_is_case_insensitive_and_unknown_topics_list_the_check_names(monkeypatch):
    async def _none(topic):
        return None

    monkeypatch.setattr(qr, "fetch_stored_check", _none)
    agent = _agent()
    assert "No stored run" in _ask(agent, "/audit MNA_Filter_Accuracy_Review").result
    bad = _ask(agent, "/audit definitely_not_a_topic").result
    assert "Unknown audit topic" in bad
    for t in qr.sweep_topics():
        assert t in bad, f"the unknown-topic reply does not list the check {t!r}"
    assert "cooldowns" in bad                                # the metric topics still work


def test_existing_metric_topics_are_unchanged():
    from agents.market_intelligence import system_audit as sa

    res = asyncio.run(sa.run_topic_audit("nonsense_topic"))
    assert res["error"] and "cooldowns" in res["valid"] and "job_runs" in res["valid"]
    assert set(qr.sweep_topics()) <= set(res["valid"])


# ── the store: one audit row per check, failures included ───────────────────────────────────────

def test_store_writes_one_row_per_check_and_keeps_failures(monkeypatch):
    rows = []

    async def _log(event, summary, detail=""):
        rows.append((event, summary, detail))

    monkeypatch.setattr("agents.market_intelligence.db.log_audit_event", _log)
    results = [
        {"label": "A", "module": "scripts.shadow_cap_plus_one_197", "exit_code": 0,
         "stdout_full": "ACCRUING (3/10 settled)", "stdout_summary": "", "stderr_tail": ""},
        {"label": "B", "module": "scripts.mna_filter_accuracy_review", "exit_code": 1,
         "stdout_full": "partial", "stdout_summary": "", "stderr_tail": "Traceback: boom"},
    ]
    n = asyncio.run(qr.store_sweep_outputs(results))
    assert n == 2 and len(rows) == 2
    assert rows[0] == (qr.SWEEP_OUTPUT_EVENT, "shadow_cap_plus_one_197 | exit=0 | waiting",
                       "ACCRUING (3/10 settled)")
    assert rows[1][1] == "mna_filter_accuracy_review | exit=1 | failed"
    assert "Traceback: boom" in rows[1][2]                  # THIS month's failure, not last month's table


def test_the_event_is_not_swept_up_by_the_failure_counters():
    """Named `*_output`: the nightly silent-error sweep matches `%error%` / `%\\_failed%`."""
    assert "error" not in qr.SWEEP_OUTPUT_EVENT and "failed" not in qr.SWEEP_OUTPUT_EVENT


def test_store_truncates_a_huge_table_and_never_raises(monkeypatch):
    rows = []

    async def _log(event, summary, detail=""):
        rows.append(detail)

    monkeypatch.setattr("agents.market_intelligence.db.log_audit_event", _log)
    big = {"label": "A", "module": "scripts.shadow_cap_plus_one_197", "exit_code": 0,
           "stdout_full": "x" * 50_000, "stdout_summary": "", "stderr_tail": ""}
    asyncio.run(qr.store_sweep_outputs([big]))
    assert len(rows[0]) < 24_100 and "truncated" in rows[0]

    async def _boom(*a, **k):
        raise RuntimeError("db down")

    monkeypatch.setattr("agents.market_intelligence.db.log_audit_event", _boom)
    assert asyncio.run(qr.store_sweep_outputs([big])) == 0          # swallowed, digest still goes out


def test_run_quarterly_sweep_stores_what_it_ran(monkeypatch):
    stored = []

    async def _store(results):
        stored.extend(results)
        return len(results)

    class _Proc:
        returncode, stdout, stderr = 0, "→ N<30: KEEP OBSERVING.\n", ""

    monkeypatch.setattr(qr, "store_sweep_outputs", _store)
    monkeypatch.setattr(qr.subprocess, "run", lambda *a, **k: _Proc())
    out = asyncio.run(qr.run_quarterly_sweep())
    assert len(stored) == len(qr.QUARTERLY_BACKWARD_CHECK_SCRIPTS) == len(out["results"])
    assert all(r["stdout_full"] == _Proc.stdout for r in stored)
    assert "👀" not in out["digest_message"]


def test_next_sweep_date():
    f = qr.next_sweep_date
    assert f(datetime(2026, 10, 3, 7, 30, tzinfo=_ET)) == "2026-11-01"
    assert f(datetime(2026, 12, 15, 9, 0, tzinfo=_ET)) == "2027-01-01"
    assert f(datetime(2026, 11, 1, 9, 0, tzinfo=_ET)) == "2026-11-01"       # before 18:00 on the day
    assert f(datetime(2026, 11, 1, 19, 0, tzinfo=_ET)) == "2026-12-01"      # after it ran


def test_no_stored_run_message_is_honest_and_dated():
    txt = qr.render_stored_check("mna_filter_accuracy_review", None,
                                 now_et=datetime(2026, 10, 3, 7, 30, tzinfo=_ET))
    assert "No stored run" in txt and "2026-11-01" in txt
    assert "Unknown" not in txt and "python -m scripts.mna_filter_accuracy_review" in txt


def test_a_fence_inside_a_stored_table_cannot_close_the_code_block():
    txt = qr.render_stored_check("news_source_quality", _stored_row(
        "news_source_quality", body="📰 *News*\n```\nPolygon  80%\n```"))
    assert txt.count("```") == 2


def test_a_failed_run_says_so():
    txt = qr.render_stored_check("shadow_cap_plus_one_197",
                                 _stored_row("shadow_cap_plus_one_197", "Traceback: boom", "failed", 1))
    assert "FAILED TO RUN" in txt and "Traceback: boom" in txt


# ═══════════════════════════════════════════════════════════════════════════════════════════
# (b) the judge footer — pinned in full in tests/test_monthly_judge_review.py; this is the
#     second pin, on the SOURCE line, so a revert of the wording fails next to the rest of #691.
# ═══════════════════════════════════════════════════════════════════════════════════════════

def test_judge_footer_no_longer_claims_the_judge_is_blind():
    from agents.market_intelligence.judge_review import aggregate_judge_review, format_judge_review
    rows = [{"ticker": "AAA", "alert_date": date(2026, 9, 1), "grounded_text": "[SEC 8-K filed 09-01] x",
             "judge_direction": "hold", "judge_tier": "HIGH", "baseline_floor_tier": "HIGH"}]
    text = format_judge_review(aggregate_judge_review(rows), 30)
    assert "Direct source on file" in text and "1/1 graded rows" in text
    for stale in ("blind", "shown 'no'", "until #335", "#329"):
        assert stale not in text, stale
