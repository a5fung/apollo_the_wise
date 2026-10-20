"""Deploy gate [5p/7] — the replay-everything CI gate (ADR 0022 §3 L4, #313 / #302).

A new gate's own regression tests (test_discipline.md rule 2). Two layers:

  1. `scripts/preflight_ci_status_gate.py` in-process: every reading state (green / red / stale /
     missing / unreadable) against every scope, the override path, and the audit payload.
  2. THE REAL SHELL out of `scripts/deploy.sh`: the `[5p/7]` block is extracted verbatim (the
     #656 marker pattern) and run with `CI_STATUS_DIR` pointed at fixture files and a `docker`
     shim on PATH — so a dry-run deploy proves that a fresh red exits 21 for market-agent / both /
     execution, never for orchestrator, that stale/missing/unreadable warn and reach the build
     step, and that an override reaches the build, logs, and relays the audit payload. The
     2026-10-14 review fixes are pinned here too: a root-owned status dir warns loudly, a crash
     in the gate itself does NOT read as a RED block, and a blocked deploy re-states an owed
     `deploy.sh execution`.
"""
from __future__ import annotations

import importlib.util
import json
import os
import re
import shutil
import stat
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
DEPLOY_SH = REPO / "scripts" / "deploy.sh"

_spec = importlib.util.spec_from_file_location("preflight_ci_status_gate",
                                               REPO / "scripts" / "preflight_ci_status_gate.py")
gate = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gate)

NOW = datetime(2026, 10, 14, 16, 0, tzinfo=timezone.utc)


def _write_real_now(d: Path, job: str, status: str, age_days: float, detail: str = "d") -> Path:
    """For EVERY test that runs `gate.main` or the dry-run shell gate: both read the status against the REAL clock, so a
    fixture dated off the fixed NOW turns stale a week after NOW and the "fresh red" tests start failing on the calendar
    (2026-10-19: the dry-run tests; 2026-10-20: `test_main_exit_codes_log_and_audit_json` and the remaining dry-run tests).
    Tests that call `decide` / `read_status` with an explicit `now=NOW` keep `_write`."""
    return _write(d, job, status, age_days, detail, now=datetime.now(timezone.utc))


def _write(d: Path, job: str, status: str, age_days: float, detail: str = "d", now: datetime = NOW) -> Path:
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"{job}.json"
    p.write_text(json.dumps({"job": job, "status": status,
                             "asof": (now - timedelta(days=age_days)).isoformat(), "detail": detail}))
    return p


# ── layer 1: readings ────────────────────────────────────────────────────────────────────────

def test_missing_file_reads_missing(tmp_path):
    r = gate.read_status(tmp_path / "selection_replay.json", NOW)
    assert r["state"] == "missing" and r["job"] == "selection_replay"


@pytest.mark.parametrize("content, why", [
    ("{not json", "not JSON"),
    ("[1, 2]", "not an object"),
    (json.dumps({"status": "amber", "asof": NOW.isoformat()}), "green|red"),
    (json.dumps({"status": "red", "asof": "yesterday-ish"}), "asof unparsable"),
    (json.dumps({"status": "red"}), "asof unparsable"),
])
def test_unreadable_files_read_unreadable_never_red(tmp_path, content, why):
    p = tmp_path / "selection_replay.json"
    p.write_text(content)
    r = gate.read_status(p, NOW)
    assert r["state"] == "unreadable" and why in r["detail"]


def test_age_decides_fresh_vs_stale_at_seven_days(tmp_path):
    assert gate.read_status(_write(tmp_path, "a", "red", 6.9), NOW)["state"] == "red"
    assert gate.read_status(_write(tmp_path, "b", "red", 7.1), NOW)["state"] == "stale"
    assert gate.read_status(_write(tmp_path, "c", "green", 7.1), NOW)["state"] == "stale"
    assert gate.read_status(_write(tmp_path, "d", "green", 0.0), NOW)["state"] == "green"


def test_naive_asof_reads_as_et_and_a_future_asof_is_age_zero(tmp_path):
    p = tmp_path / "x.json"
    p.write_text(json.dumps({"status": "green", "asof": "2026-10-14T11:00:00"}))   # 11:00 ET = 15:00Z
    r = gate.read_status(p, NOW)
    assert r["state"] == "green" and abs(r["age_days"] - 1 / 24) < 1e-6
    p.write_text(json.dumps({"status": "red", "asof": (NOW + timedelta(days=3)).isoformat()}))
    assert gate.read_status(p, NOW)["age_days"] == 0.0


def test_evaluate_lists_every_expected_job_first_then_extras(tmp_path):
    _write(tmp_path, "zz_extra", "green", 1)
    _write(tmp_path, "entry_sim", "green", 1)
    (tmp_path / ".hidden.json").write_text("{}")
    jobs = [r["job"] for r in gate.evaluate(tmp_path, NOW)]
    assert jobs == list(gate.EXPECTED_JOBS) + ["zz_extra"]
    assert gate.evaluate(tmp_path / "nope", NOW)[0]["state"] == "missing"


# ── layer 1: the decision ────────────────────────────────────────────────────────────────────

def _readings(tmp_path, **jobs):
    for job, (status, age) in jobs.items():
        _write(tmp_path, job, status, age)
    return gate.evaluate(tmp_path, NOW)


@pytest.mark.parametrize("scope", ["market-agent", "both", "execution"])
def test_fresh_red_blocks_the_trading_scopes(tmp_path, scope):
    v = gate.decide(_readings(tmp_path, selection_replay=("red", 2)), scope, None)
    assert v["exit"] == gate.EXIT_BLOCK and v["blocking"] == ["selection_replay"]
    assert any("DEPLOY BLOCKED" in l for l in v["lines"])


def test_fresh_red_never_blocks_an_orchestrator_only_deploy(tmp_path):
    v = gate.decide(_readings(tmp_path, selection_replay=("red", 2)), "orchestrator", None)
    assert v["exit"] == gate.EXIT_OK and v["blocking"] == []
    assert any("never blocked" in l and "M4f" in l for l in v["lines"])


@pytest.mark.parametrize("scope", ["market-agent", "both", "execution", "orchestrator"])
def test_stale_red_warns_and_passes(tmp_path, scope):
    v = gate.decide(_readings(tmp_path, selection_replay=("red", 8)), scope, None)
    assert v["exit"] == gate.EXIT_OK and "selection_replay" in v["warns"]
    assert any("STALE-red" in l for l in v["lines"])


def test_green_passes_and_stale_green_warns(tmp_path):
    v = gate.decide(_readings(tmp_path, selection_replay=("green", 1)), "market-agent", None)
    assert v["exit"] == gate.EXIT_OK and "selection_replay" not in v["warns"]
    v = gate.decide(_readings(tmp_path, selection_replay=("green", 9)), "market-agent", None)
    assert v["exit"] == gate.EXIT_OK and "selection_replay" in v["warns"]


def test_missing_and_unreadable_warn_never_block(tmp_path):
    (tmp_path / "judge_eval.json").write_text("garbage")
    v = gate.decide(gate.evaluate(tmp_path, NOW), "execution", None)
    assert v["exit"] == gate.EXIT_OK
    # selection_replay: missing (it HAS a writer) → WARN; judge_eval: a file exists but is garbage
    # → UNREADABLE WARN even though the job is not built; entry_sim: missing + not built → info.
    assert set(v["warns"]) == {"selection_replay", "judge_eval"}
    assert any("MISSING WARN" in l for l in v["lines"]) and any("UNREADABLE WARN" in l for l in v["lines"])


def test_a_missing_unbuilt_job_prints_not_built_and_is_not_a_warn(tmp_path):
    """Review 2026-10-14: two permanent MISSING WARN lines (judge_eval, entry_sim — no writer
    exists) drowned the one that matters, a dead selection_replay writer. Fails if they warn."""
    v = gate.decide(gate.evaluate(tmp_path, NOW), "market-agent", None)
    assert v["exit"] == gate.EXIT_OK
    assert v["warns"] == ["selection_replay"]
    by_job = {l.split()[0]: l for l in v["lines"] if l.startswith("  ") and l.split()[0] in gate.EXPECTED_JOBS}
    assert "MISSING WARN" in by_job["selection_replay"]
    for job in ("judge_eval", "entry_sim"):
        assert "(not built)" in by_job[job] and "WARN" not in by_job[job]
    assert sum("MISSING WARN" in l for l in v["lines"]) == 1      # the ONE signal that matters
    assert any(l.endswith("1 warn: selection_replay).") for l in v["lines"])


def test_a_not_built_job_that_has_a_file_is_evaluated_like_any_other(tmp_path):
    """NOT_BUILT only relabels a MISSING file. The day a writer lands (or someone drops a file in
    by hand) its red must still block and its rot must still warn."""
    v = gate.decide(_readings(tmp_path, entry_sim=("red", 1)), "execution", None)
    assert v["exit"] == gate.EXIT_BLOCK and v["blocking"] == ["entry_sim"]
    v = gate.decide(_readings(tmp_path, judge_eval=("green", 9)), "market-agent", None)
    assert "judge_eval" in v["warns"] and any("STALE-green" in l for l in v["lines"])


def test_not_built_is_a_subset_of_the_expected_jobs():
    assert set(gate.NOT_BUILT) <= set(gate.EXPECTED_JOBS)
    assert "selection_replay" not in gate.NOT_BUILT             # the live writer always warns


def test_the_block_exit_code_cannot_be_what_a_crash_exits_with():
    """Review 2026-10-14: EXIT_BLOCK was 1 — the code an uncaught exception exits with — so a gate
    bug blocked every trading-scope deploy under a false 'a status is RED' message."""
    assert gate.EXIT_BLOCK == 3
    assert gate.EXIT_BLOCK not in (gate.EXIT_OK, 1, 2)          # 1 = traceback, 2 = argparse


def test_override_turns_a_block_into_a_loud_pass(tmp_path):
    v = gate.decide(_readings(tmp_path, selection_replay=("red", 1)), "market-agent", "hotfix, operator 10-14")
    assert v["exit"] == gate.EXIT_OK and v["overridden"] is True and v["blocking"] == ["selection_replay"]
    assert any("CI GATE OVERRIDDEN" in l and "hotfix, operator 10-14" in l for l in v["lines"])


def test_blank_override_is_not_an_override(tmp_path):
    v = gate.decide(_readings(tmp_path, selection_replay=("red", 1)), "market-agent", "   ")
    assert v["exit"] == gate.EXIT_BLOCK and v["overridden"] is False


def test_override_with_nothing_red_is_noted_not_logged(tmp_path):
    v = gate.decide(_readings(tmp_path, selection_replay=("green", 1)), "market-agent", "unneeded")
    assert v["exit"] == gate.EXIT_OK and v["overridden"] is False
    assert any("nothing overridden" in l for l in v["lines"])


def test_audit_payload_names_the_event_scope_job_and_reason(tmp_path):
    readings = _readings(tmp_path, selection_replay=("red", 1))
    v = gate.decide(readings, "both", "hotfix")
    p = gate.audit_payload(v, "both", readings)
    assert p["event_type"] == "ci_override_deploy"
    assert "both" in p["summary"] and "selection_replay" in p["summary"] and "hotfix" in p["summary"]
    assert p["detail"].startswith("selection_replay: ")


def test_main_exit_codes_log_and_audit_json(tmp_path, monkeypatch, capsys):
    _write_real_now(tmp_path / "ci", "selection_replay", "red", 1, "live regressed")
    log = tmp_path / "logs" / "ci_override.log"
    monkeypatch.delenv(gate.ENV_OVERRIDE, raising=False)
    assert gate.main(["--scope", "market-agent", "--dir", str(tmp_path / "ci"), "--log-file", str(log)]) == gate.EXIT_BLOCK
    assert not log.exists()
    assert gate.main(["--scope", "orchestrator", "--dir", str(tmp_path / "ci"), "--log-file", str(log)]) == 0
    monkeypatch.setenv(gate.ENV_OVERRIDE, "emergency, operator")
    assert gate.main(["--scope", "execution", "--dir", str(tmp_path / "ci"), "--log-file", str(log)]) == 0
    line = log.read_text().strip()
    assert "scope=execution" in line and "red=selection_replay" in line and "emergency, operator" in line
    capsys.readouterr()
    assert gate.main(["--scope", "execution", "--dir", str(tmp_path / "ci"), "--audit-json"]) == 0
    out = capsys.readouterr().out.strip().splitlines()
    assert len(out) == 1 and json.loads(out[0])["event_type"] == "ci_override_deploy"
    monkeypatch.delenv(gate.ENV_OVERRIDE)
    assert gate.main(["--scope", "execution", "--dir", str(tmp_path / "ci"), "--audit-json"]) == 0
    assert capsys.readouterr().out.strip() == ""           # no override → no payload line


# ── layer 2: the real deploy.sh block, dry-run ───────────────────────────────────────────────

_BLOCK = re.compile(r"^# >>> #313 ci-status gate >>>$.*?^# <<< #313 ci-status gate <<<$", re.S | re.M)


def _gate_block() -> str:
    m = _BLOCK.search(DEPLOY_SH.read_text(encoding="utf-8"))
    assert m, ("could not extract the [5p/7] block from scripts/deploy.sh — the markers moved. Fix "
               "the extraction rather than deleting the test: without it nothing proves a red "
               "status actually stops a deploy.")
    return m.group(0)


_CRASH_WRAPPER = """\
import importlib.util, sys
script = sys.argv[1]
sys.argv = sys.argv[1:]
spec = importlib.util.spec_from_file_location("gate_under_crash", script)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
def _boom(*a, **k):
    raise PermissionError(13, "simulated EACCES stat()ing the status dir")   # the reviewer's example
mod.evaluate = _boom
sys.exit(mod.main(sys.argv[1:]))
"""


def _dry_run(tmp_path: Path, scope: str, *, override: str | None = None,
             exec_drift: bool = False, crash_gate: bool = False,
             status_dir: Path | None = None) -> subprocess.CompletedProcess:
    """Run the extracted block as deploy.sh would, with the two variables it reads already bound
    (SCOPE from argv, PREFLIGHT_CONTAINER from the scope case) and a `docker` shim that records
    its argv instead of exec'ing into a container. `exec_drift` binds EXEC_DRIFT=1 the way the
    #324 drift block does (left UNBOUND otherwise, as on a deploy that pulled nothing — under
    `set -u` a bare `$EXEC_DRIFT` would die). `crash_gate` puts a `python3` shim on PATH that runs
    the real gate script with `evaluate` raising, i.e. an unexpected exception inside the gate."""
    if shutil.which("bash") is None:  # pragma: no cover
        pytest.skip("bash unavailable")
    shim_dir = tmp_path / "bin"
    shim_dir.mkdir(exist_ok=True)
    shim = shim_dir / "docker"
    shim.write_text("#!/usr/bin/env bash\nprintf '%s\\n' \"$@\" > \"$DOCKER_SHIM_LOG\"\nexit 0\n")
    shim.chmod(shim.stat().st_mode | stat.S_IEXEC)
    env = {**os.environ,
           "PATH": f"{shim_dir}:{os.environ['PATH']}",
           "CI_STATUS_DIR": str(status_dir or tmp_path / "ci"),
           "CI_OVERRIDE_LOG": str(tmp_path / "logs" / "ci_override.log"),
           "DOCKER_SHIM_LOG": str(tmp_path / "docker_args.txt")}
    env.pop("CI_OVERRIDE", None)
    if override is not None:
        env["CI_OVERRIDE"] = override
    if crash_gate:
        wrapper = tmp_path / "crash_gate.py"
        wrapper.write_text(_CRASH_WRAPPER)
        py_shim = shim_dir / "python3"
        py_shim.write_text(f'#!/usr/bin/env bash\nexec "{sys.executable}" "{wrapper}" "$@"\n')
        py_shim.chmod(py_shim.stat().st_mode | stat.S_IEXEC)
    script = "\n".join([
        "set -euo pipefail",
        f'SCOPE="{scope}"',
        'PREFLIGHT_CONTAINER="apollo-market"',
        *(["EXEC_DRIFT=1"] if exec_drift else []),
        _gate_block(),
        'echo "REACHED_BUILD"',
    ])
    return subprocess.run(["bash", "-c", script], cwd=REPO, env=env, capture_output=True, text=True, timeout=60)


@pytest.mark.parametrize("scope", ["market-agent", "both", "execution"])
def test_dry_run_deploy_a_fresh_red_exits_21_for_the_trading_scopes(tmp_path, scope):
    # source-pin-ok: deploy.sh is shell; the only way to exercise the gate's WIRING (exit code,
    # ordering before the build, the mapped block message) is to run the extracted block.
    _write_real_now(tmp_path / "ci", "selection_replay", "red", 2, "live regressed")
    r = _dry_run(tmp_path, scope)
    assert r.returncode == 21, r.stdout + r.stderr
    assert "DEPLOY BLOCKED" in r.stdout and "REACHED_BUILD" not in r.stdout
    assert "CI_OVERRIDE=" in r.stdout            # the escape is named in the block message


def test_dry_run_deploy_a_fresh_red_does_not_block_orchestrator(tmp_path):
    # source-pin-ok: same wiring check as above, the M4f negative half, run out of the real block.
    _write_real_now(tmp_path / "ci", "selection_replay", "red", 2)
    r = _dry_run(tmp_path, "orchestrator")
    assert r.returncode == 0 and "REACHED_BUILD" in r.stdout, r.stdout + r.stderr
    assert "never blocked" in r.stdout


@pytest.mark.parametrize("fixture", ["stale-red", "stale-green", "green", "missing", "unreadable"])
def test_dry_run_deploy_warn_states_reach_the_build(tmp_path, fixture):
    # source-pin-ok: wiring check — each WARN state must pass THROUGH the real shell block.
    ci = tmp_path / "ci"
    if fixture == "stale-red":
        _write_real_now(ci, "selection_replay", "red", 8)
    elif fixture == "stale-green":
        _write_real_now(ci, "selection_replay", "green", 8)
    elif fixture == "green":
        _write_real_now(ci, "selection_replay", "green", 1)
    elif fixture == "unreadable":
        ci.mkdir(); (ci / "selection_replay.json").write_text("{broken")
    r = _dry_run(tmp_path, "market-agent")
    assert r.returncode == 0 and "REACHED_BUILD" in r.stdout, r.stdout + r.stderr
    if fixture == "green":
        # a healthy writer now means a QUIET gate: the two unbuilt jobs are "(not built)"
        # information, so nothing warns (this assertion used to be satisfied by those two alone).
        assert "WARN" not in r.stdout and "0 warn: none" in r.stdout
    else:
        assert "WARN" in r.stdout
    assert not (tmp_path / "docker_args.txt").exists()      # no override → no audit relay


def test_dry_run_deploy_creates_the_host_status_dir_before_the_build(tmp_path):
    # source-pin-ok: wiring check — the mkdir must happen in the block that precedes `up -d`, or
    # docker creates the bind source as root and the uid-1000 writer fails on deploy one.
    assert not (tmp_path / "ci").exists()
    r = _dry_run(tmp_path, "market-agent")
    assert r.returncode == 0 and (tmp_path / "ci").is_dir()
    assert "MISSING WARN" in r.stdout and "REACHED_BUILD" in r.stdout
    assert "NOT WRITABLE" not in r.stdout          # a dir we just made is writable: no false alarm
    assert "(not built)" in r.stdout               # judge_eval / entry_sim are information, not WARN


@pytest.mark.skipif(hasattr(os, "geteuid") and os.geteuid() == 0, reason="root can write anywhere")
def test_dry_run_deploy_an_existing_unwritable_status_dir_warns_loudly_but_never_blocks(tmp_path):
    # source-pin-ok: wiring check. Review 2026-10-14: on the first deploy docker creates the bind
    # source root:root 0755, and `mkdir -p` then returns 0 on every later deploy (it is an existing
    # directory), so a guard keyed on mkdir's exit code never fires and the uid-1000 writer stays
    # dark, reading MISSING WARN forever like a job nobody built. Only a -w test notices.
    ci = tmp_path / "ci"
    ci.mkdir()
    ci.chmod(0o555)
    try:
        r = _dry_run(tmp_path, "market-agent")
    finally:
        ci.chmod(0o755)
    assert r.returncode == 0 and "REACHED_BUILD" in r.stdout, r.stdout + r.stderr
    assert "NOT WRITABLE" in r.stdout and "chown apollo:apollo" in r.stdout
    assert "DEPLOY BLOCKED" not in r.stdout


def test_dry_run_deploy_a_status_dir_that_cannot_be_created_warns_loudly_but_never_blocks(tmp_path):
    # source-pin-ok: wiring check — the mkdir-failure arm of the same guard (parent is a file).
    blocker = tmp_path / "not-a-dir"
    blocker.write_text("x")
    r = _dry_run(tmp_path, "market-agent", status_dir=blocker / "ci")    # mkdir -p under a file fails
    assert r.returncode == 0 and "REACHED_BUILD" in r.stdout, r.stdout + r.stderr
    assert "NOT WRITABLE" in r.stdout and "DEPLOY BLOCKED" not in r.stdout


def test_dry_run_deploy_override_passes_logs_and_relays_the_audit_row(tmp_path):
    # source-pin-ok: wiring check — the override's three LOUD outputs (banner, logs/ line, the
    # docker-exec'd audit relay) are produced by the shell block, not by the Python alone.
    _write_real_now(tmp_path / "ci", "selection_replay", "red", 1, "live regressed")
    r = _dry_run(tmp_path, "execution", override="hotfix stop-ack, operator 10-14")
    assert r.returncode == 0 and "REACHED_BUILD" in r.stdout, r.stdout + r.stderr
    assert "CI GATE OVERRIDDEN" in r.stdout and "hotfix stop-ack, operator 10-14" in r.stdout
    assert "hotfix stop-ack, operator 10-14" in (tmp_path / "logs" / "ci_override.log").read_text()
    docker_args = (tmp_path / "docker_args.txt").read_text().splitlines()
    assert docker_args[:5] == ["exec", "apollo-market", "python", "-m", "scripts.log_judge_envelope_change"]
    payload = json.loads(docker_args[5])
    assert payload["event_type"] == "ci_override_deploy" and "hotfix stop-ack" in payload["summary"]
    assert "=== [5p/7]" in r.stdout     # the block announces its slot like every other gate


# ── review 2026-10-14: a crash in the gate is not a RED status ────────────────────────────────

@pytest.mark.parametrize("scope", ["market-agent", "both", "execution"])
def test_dry_run_deploy_a_crash_inside_the_gate_is_loud_but_never_blocks(tmp_path, scope):
    # source-pin-ok: wiring check. ADR 0022: a broken CI job must not freeze deploys. Before the fix
    # deploy.sh treated ANY non-zero as a block, so an unforeseen exception in the gate (a
    # PermissionError from one stat()) exited 21 under 'a status is RED', and CI_OVERRIDE — which
    # is evaluated inside the crashed script — could not rescue it.
    _write_real_now(tmp_path / "ci", "selection_replay", "green", 1)
    r = _dry_run(tmp_path, scope, crash_gate=True)
    assert r.returncode == 0 and "REACHED_BUILD" in r.stdout, r.stdout + r.stderr
    assert "CI GATE ERROR" in r.stdout and "NOT blocking" in r.stdout
    assert "DEPLOY BLOCKED" not in r.stdout and "is RED" not in r.stdout
    assert "PermissionError" in r.stderr                  # the traceback is shown, not swallowed


def test_dry_run_deploy_a_real_red_still_blocks_when_the_gate_runs_normally(tmp_path):
    # source-pin-ok: the other half of the crash test — exit 3 must still map to 21, and the
    # crash path above must not have loosened the real block.
    _write_real_now(tmp_path / "ci", "selection_replay", "red", 1)
    r = _dry_run(tmp_path, "market-agent")
    assert r.returncode == 21 and "CI GATE ERROR" not in r.stdout


# ── review 2026-10-14: the exit-21 branch re-states an owed `deploy.sh execution` ────────────

def test_dry_run_deploy_a_block_after_an_execution_drift_pull_restates_the_owed_execution_deploy(tmp_path):
    # source-pin-ok: wiring check. A blocked deploy has already pulled; the CI_OVERRIDE retry pulls
    # nothing (BEFORE_PULL == AFTER_PULL), so the #324 drift warning and the closing 'NOT DONE' line
    # never print again and apollo-execution is left on stale code (the LZB silent-dark class).
    _write_real_now(tmp_path / "ci", "selection_replay", "red", 1)
    r = _dry_run(tmp_path, "market-agent", exec_drift=True)
    assert r.returncode == 21, r.stdout + r.stderr
    assert "EXECUTION-RUNTIME DRIFT" in r.stdout and "bash scripts/deploy.sh execution" in r.stdout
    assert "will NOT repeat" in r.stdout


def test_dry_run_deploy_a_block_without_drift_does_not_mention_it(tmp_path):
    # source-pin-ok: negative half — and proves `${EXEC_DRIFT:-0}` survives `set -u` when the
    # variable was never bound (a deploy whose pull changed nothing).
    _write_real_now(tmp_path / "ci", "selection_replay", "red", 1)
    r = _dry_run(tmp_path, "market-agent")
    assert r.returncode == 21, r.stdout + r.stderr
    assert "EXECUTION-RUNTIME DRIFT" not in r.stdout

# NOTE (deliberately no text-pin test here): that exit 21 is unique in deploy.sh and that the block
# sits BEFORE `[2/5] build` are properties of the script text; a test asserting them would be a
# source pin (#653 ratchet). The dry runs above prove the behaviour that matters — the block
# returns 21 for the trading scopes, 0 for orchestrator, and nothing after it runs on a block.
# Placement is stated in the block's own comment, ADR 0022 §3 and CHANGELOG 2026-10-14.
