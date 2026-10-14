"""Deploy gate [5p/7] — the replay-everything CI gate (ADR 0022 §3 L4, #313 / #302).

A new gate's own regression tests (test_discipline.md rule 2). Two layers:

  1. `scripts/preflight_ci_status_gate.py` in-process: every reading state (green / red / stale /
     missing / unreadable) against every scope, the override path, and the audit payload.
  2. THE REAL SHELL out of `scripts/deploy.sh`: the `[5p/7]` block is extracted verbatim (the
     #656 marker pattern) and run with `CI_STATUS_DIR` pointed at fixture files and a `docker`
     shim on PATH — so a dry-run deploy proves that a fresh red exits 21 for market-agent / both /
     execution, never for orchestrator, that stale/missing/unreadable warn and reach the build
     step, and that an override reaches the build, logs, and relays the audit payload.
"""
from __future__ import annotations

import importlib.util
import json
import os
import re
import shutil
import stat
import subprocess
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


def _write(d: Path, job: str, status: str, age_days: float, detail: str = "d") -> Path:
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"{job}.json"
    p.write_text(json.dumps({"job": job, "status": status,
                             "asof": (NOW - timedelta(days=age_days)).isoformat(), "detail": detail}))
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
    assert set(v["warns"]) == {"selection_replay", "judge_eval", "entry_sim"}
    assert any("MISSING WARN" in l for l in v["lines"]) and any("UNREADABLE WARN" in l for l in v["lines"])


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
    _write(tmp_path / "ci", "selection_replay", "red", 1, "live regressed")
    log = tmp_path / "logs" / "ci_override.log"
    monkeypatch.delenv(gate.ENV_OVERRIDE, raising=False)
    assert gate.main(["--scope", "market-agent", "--dir", str(tmp_path / "ci"), "--log-file", str(log)]) == 1
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


def _dry_run(tmp_path: Path, scope: str, *, override: str | None = None) -> subprocess.CompletedProcess:
    """Run the extracted block as deploy.sh would, with the two variables it reads already bound
    (SCOPE from argv, PREFLIGHT_CONTAINER from the scope case) and a `docker` shim that records
    its argv instead of exec'ing into a container."""
    if shutil.which("bash") is None:  # pragma: no cover
        pytest.skip("bash unavailable")
    shim_dir = tmp_path / "bin"
    shim_dir.mkdir(exist_ok=True)
    shim = shim_dir / "docker"
    shim.write_text("#!/usr/bin/env bash\nprintf '%s\\n' \"$@\" > \"$DOCKER_SHIM_LOG\"\nexit 0\n")
    shim.chmod(shim.stat().st_mode | stat.S_IEXEC)
    env = {**os.environ,
           "PATH": f"{shim_dir}:{os.environ['PATH']}",
           "CI_STATUS_DIR": str(tmp_path / "ci"),
           "CI_OVERRIDE_LOG": str(tmp_path / "logs" / "ci_override.log"),
           "DOCKER_SHIM_LOG": str(tmp_path / "docker_args.txt")}
    env.pop("CI_OVERRIDE", None)
    if override is not None:
        env["CI_OVERRIDE"] = override
    script = "\n".join([
        "set -euo pipefail",
        f'SCOPE="{scope}"',
        'PREFLIGHT_CONTAINER="apollo-market"',
        _gate_block(),
        'echo "REACHED_BUILD"',
    ])
    return subprocess.run(["bash", "-c", script], cwd=REPO, env=env, capture_output=True, text=True, timeout=60)


@pytest.mark.parametrize("scope", ["market-agent", "both", "execution"])
def test_dry_run_deploy_a_fresh_red_exits_21_for_the_trading_scopes(tmp_path, scope):
    # source-pin-ok: deploy.sh is shell; the only way to exercise the gate's WIRING (exit code,
    # ordering before the build, the mapped block message) is to run the extracted block.
    _write(tmp_path / "ci", "selection_replay", "red", 2, "live regressed")
    r = _dry_run(tmp_path, scope)
    assert r.returncode == 21, r.stdout + r.stderr
    assert "DEPLOY BLOCKED" in r.stdout and "REACHED_BUILD" not in r.stdout
    assert "CI_OVERRIDE=" in r.stdout            # the escape is named in the block message


def test_dry_run_deploy_a_fresh_red_does_not_block_orchestrator(tmp_path):
    # source-pin-ok: same wiring check as above, the M4f negative half, run out of the real block.
    _write(tmp_path / "ci", "selection_replay", "red", 2)
    r = _dry_run(tmp_path, "orchestrator")
    assert r.returncode == 0 and "REACHED_BUILD" in r.stdout, r.stdout + r.stderr
    assert "never blocked" in r.stdout


@pytest.mark.parametrize("fixture", ["stale-red", "stale-green", "green", "missing", "unreadable"])
def test_dry_run_deploy_warn_states_reach_the_build(tmp_path, fixture):
    # source-pin-ok: wiring check — each WARN state must pass THROUGH the real shell block.
    ci = tmp_path / "ci"
    if fixture == "stale-red":
        _write(ci, "selection_replay", "red", 8)
    elif fixture == "stale-green":
        _write(ci, "selection_replay", "green", 8)
    elif fixture == "green":
        _write(ci, "selection_replay", "green", 1)
    elif fixture == "unreadable":
        ci.mkdir(); (ci / "selection_replay.json").write_text("{broken")
    r = _dry_run(tmp_path, "market-agent")
    assert r.returncode == 0 and "REACHED_BUILD" in r.stdout, r.stdout + r.stderr
    assert "WARN" in r.stdout
    assert not (tmp_path / "docker_args.txt").exists()      # no override → no audit relay


def test_dry_run_deploy_creates_the_host_status_dir_before_the_build(tmp_path):
    # source-pin-ok: wiring check — the mkdir must happen in the block that precedes `up -d`, or
    # docker creates the bind source as root and the uid-1000 writer fails on deploy one.
    assert not (tmp_path / "ci").exists()
    r = _dry_run(tmp_path, "market-agent")
    assert r.returncode == 0 and (tmp_path / "ci").is_dir()
    assert "MISSING WARN" in r.stdout and "REACHED_BUILD" in r.stdout


def test_dry_run_deploy_override_passes_logs_and_relays_the_audit_row(tmp_path):
    # source-pin-ok: wiring check — the override's three LOUD outputs (banner, logs/ line, the
    # docker-exec'd audit relay) are produced by the shell block, not by the Python alone.
    _write(tmp_path / "ci", "selection_replay", "red", 1, "live regressed")
    r = _dry_run(tmp_path, "execution", override="hotfix stop-ack, operator 10-14")
    assert r.returncode == 0 and "REACHED_BUILD" in r.stdout, r.stdout + r.stderr
    assert "CI GATE OVERRIDDEN" in r.stdout and "hotfix stop-ack, operator 10-14" in r.stdout
    assert "hotfix stop-ack, operator 10-14" in (tmp_path / "logs" / "ci_override.log").read_text()
    docker_args = (tmp_path / "docker_args.txt").read_text().splitlines()
    assert docker_args[:5] == ["exec", "apollo-market", "python", "-m", "scripts.log_judge_envelope_change"]
    payload = json.loads(docker_args[5])
    assert payload["event_type"] == "ci_override_deploy" and "hotfix stop-ack" in payload["summary"]
    assert "=== [5p/7]" in r.stdout     # the block announces its slot like every other gate

# NOTE (deliberately no text-pin test here): that exit 21 is unique in deploy.sh and that the block
# sits BEFORE `[2/5] build` are properties of the script text; a test asserting them would be a
# source pin (#653 ratchet). The dry runs above prove the behaviour that matters — the block
# returns 21 for the trading scopes, 0 for orchestrator, and nothing after it runs on a block.
# Placement is stated in the block's own comment, ADR 0022 §3 and CHANGELOG 2026-10-14.
