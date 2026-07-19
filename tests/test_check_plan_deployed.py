"""`deployed` status in check_plan.py (operator 2026-07-18): built + shipped, AWAITING verify-live;
its ETA = the VERIFY-DATE. Makes "done = VERIFIED-LIVE, not deployed" a STATUS with teeth (the
past-ETA gate, verify-worded) plus two recurring --today surfaces (VERIFY-DUE + LIKELY-BUILT)
instead of forgettable prose — built tasks stop sitting in_progress under a stale to-build headline
and getting re-checked/re-built. Pins: valid status; past verify-date hard-fails with the verify
wording; --today lists verify-due deployed tasks OUT of the generic OVERDUE list; the deploy-marker
regex catches built-shaped lines without tripping on plain to-build titles; deployed counts as OPEN
in the growth + dependency gates; and a normal in_progress task is untouched."""
from datetime import date, datetime, timedelta

import pytest

import scripts.check_plan as cp
from scripts.check_plan import _DEPLOY_MARKER, parse

TODAY = datetime.now(cp._OPERATOR_TZ).date()  # main() computes "today" in operator PT — mirror it
FUTURE = (TODAY + timedelta(days=30)).isoformat()
PAST = "2000-01-01"  # always past, no time-freezing needed


def _run_main(monkeypatch, tmp_path, plan_text: str, argv=None, baseline: str | None = None):
    """Run main() against a throwaway PLAN.md with the machine-local surfaces stubbed out
    (snapshot absent -> completeness check skipped; baseline in tmp -> growth gate controlled)."""
    plan = tmp_path / "PLAN.md"
    plan.write_text(plan_text, encoding="utf-8")
    monkeypatch.setattr(cp, "PLAN", plan)
    monkeypatch.setattr(cp, "SNAPSHOT", tmp_path / "no_snapshot.json")
    base = tmp_path / "baseline.json"
    if baseline is not None:
        base.write_text(baseline, encoding="utf-8")
    monkeypatch.setattr(cp, "BASELINE", base)
    return cp.main(argv or [])


# ── `deployed` is a valid status ──────────────────────────────────────────────────────────────

def test_deployed_parses_as_valid_status():
    tasks, errors = parse(f"## Ops\n- #9901 | {FUTURE} | deployed | thing shipped 7/17 — verify cron ran\n")
    assert errors == []
    assert tasks[0]["status"] == "deployed"


def test_unknown_status_still_rejected():
    # additive: the status gate itself must not have loosened.
    _, errors = parse(f"## Ops\n- #9901 | {FUTURE} | shipped | thing\n")
    assert any("bad status 'shipped'" in e and "deployed" in e for e in errors)


# ── Hard teeth: past verify-date fails the validation gate, verify-worded ─────────────────────

def test_deployed_past_verify_date_fails_with_verify_wording(monkeypatch, tmp_path, capsys):
    rc = _run_main(monkeypatch, tmp_path,
                   f"## Ops\n- #9901 | {PAST} | deployed | digest job shipped — verify 16:55 run\n")
    out = capsys.readouterr().out
    assert rc == 1
    assert "VERIFY-DATE" in out and "VERIFY-LIVE in prod + close" in out
    # the verify-worded message REPLACES the generic rebump wording for deployed tasks
    assert "rebump to a future date at CLOSE" not in out


def test_normal_task_past_eta_keeps_generic_wording(monkeypatch, tmp_path, capsys):
    rc = _run_main(monkeypatch, tmp_path,
                   f"## Ops\n- #9901 | {PAST} | in_progress | build the widget -> tests green\n")
    out = capsys.readouterr().out
    assert rc == 1
    assert "rebump to a future date at CLOSE" in out and "VERIFY-LIVE" not in out


def test_normal_in_progress_future_eta_unaffected(monkeypatch, tmp_path, capsys):
    # existing behavior pin: a plain healthy task still passes the gate clean.
    rc = _run_main(monkeypatch, tmp_path,
                   f"## Ops\n- #9901 | {FUTURE} | in_progress | build the widget -> tests green\n")
    assert rc == 0
    assert "[plan] OK" in capsys.readouterr().out


# ── --today: VERIFY-DUE surface + OVERDUE exclusion ───────────────────────────────────────────

def test_today_verify_due_lists_deployed_and_excludes_from_overdue(monkeypatch, tmp_path, capsys):
    plan = (f"## Ops\n"
            f"- #9901 | {PAST} | deployed | close digest shipped — verify 16:55 fired\n"
            f"- #9902 | {PAST} | in_progress | still to build\n")
    rc = _run_main(monkeypatch, tmp_path, plan, argv=["--today"])
    out = capsys.readouterr().out
    assert rc == 0  # --today is the OPEN helper, never a gate
    verify_sec = out.split("-- VERIFY-DUE")[1].split("-- LIKELY-BUILT")[0]
    overdue_sec = out.split("-- OVERDUE")[1].split("-- DUE TODAY")[0]
    assert "SHIPPED; verify window here" in out
    assert "#9901" in verify_sec and f"verify {PAST}" in verify_sec
    # the deployed task must NOT be conflated with rebump-overdue; the to-build one stays there
    assert "#9901" not in overdue_sec and "#9902" in overdue_sec


def test_today_deployed_future_verify_date_not_yet_due(monkeypatch, tmp_path, capsys):
    rc = _run_main(monkeypatch, tmp_path,
                   f"## Ops\n- #9901 | {FUTURE} | deployed | shipped — verify after Friday nightly\n",
                   argv=["--today"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "-- VERIFY-DUE (0)" in out  # window not here yet — quiet until the verify-date


# ── --today: LIKELY-BUILT reclassify surface ──────────────────────────────────────────────────

def test_today_likely_built_counts_and_lists_marker_tasks(monkeypatch, tmp_path, capsys):
    plan = (f"## Ops\n"
            f"- #9901 | {FUTURE} | in_progress | close digest >> BUILT 7/17, awaiting monday\n"
            f"- #9902 | {FUTURE} | pending | drawdown watch DEPLOYED, verify-live pending\n"
            f"- #9903 | {FUTURE} | in_progress | build the reconcile job -> tests green\n"
            f"- #9904 | {FUTURE} | deployed | already reclassified — verify Friday\n")
    rc = _run_main(monkeypatch, tmp_path, plan, argv=["--today"])
    out = capsys.readouterr().out
    assert rc == 0
    built_sec = out.split("-- LIKELY-BUILT")[1].split("-- GROWTH GATE")[0]
    assert "(2)" in built_sec.splitlines()[0]  # count in the header
    assert "#9901" in built_sec and "#9902" in built_sec
    assert "#9903" not in built_sec  # plain to-build title
    assert "#9904" not in built_sec  # already `deployed` — nothing to reclassify
    assert "SURFACE, not a gate" in built_sec


def test_deploy_marker_regex_shapes():
    # the built-shaped lines it must catch
    assert _DEPLOY_MARKER.search("close digest >> BUILT 7/17 — verify monday")
    assert _DEPLOY_MARKER.search(">>BUILT (no space variant)")
    assert _DEPLOY_MARKER.search("DEPLOYED 17:15 ET, first armed run friday")
    assert _DEPLOY_MARKER.search("[ok:roll — verify-live pending Monday market]")
    assert _DEPLOY_MARKER.search("VERIFY-LIVE the 16:55 run then close")
    assert _DEPLOY_MARKER.search("deployed 2026-07-16; confirm rows")
    # plain to-build titles must NOT trip it (lowercase deploy prose, undated)
    assert not _DEPLOY_MARKER.search("build the entry-watch detector + deploy market-agent")
    assert not _DEPLOY_MARKER.search("once deployed, verify the cron then close")
    assert not _DEPLOY_MARKER.search("wire the digest into the evening brief")


# ── deployed flows through the other gates as OPEN ────────────────────────────────────────────

def test_deployed_counts_as_open_in_growth_gate(monkeypatch, tmp_path, capsys):
    import json
    baseline = json.dumps({"pt_date": TODAY.isoformat(), "baseline_count": 1,
                           "carryover_allowance": 0, "carryover_reason": None})
    plan = (f"## Ops\n"
            f"- #9901 | {FUTURE} | in_progress | build the widget -> tests green\n"
            f"- #9902 | {FUTURE} | deployed | shipped — verify Friday\n")
    rc = _run_main(monkeypatch, tmp_path, plan, baseline=baseline)
    out = capsys.readouterr().out
    assert rc == 1
    assert "SESSION GROWTH GATE: 2 open tasks" in out  # deployed counted — no early-out via status


def test_deployed_blocker_still_counts_as_open_in_dependency_gate():
    errors: list = []
    tasks, perrs = parse(f"## Ops\n"
                         f"- #9901 | {FUTURE} | deployed | shipped — verify Friday\n"
                         f"- #9902 | {FUTURE} | pending | follow-up blocked_by:#9901\n")
    assert perrs == []
    cp._dependency_gate(tasks, errors, date(2026, 7, 18))
    assert errors == []  # #9901 deployed = still OPEN -> the blocker has NOT cleared
