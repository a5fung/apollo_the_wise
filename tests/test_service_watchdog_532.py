"""tests/test_service_watchdog_532.py — coverage for infra/service_watchdog.sh's
two-tier DOWN confirmation (#532, 2026-08-06).

Context: a 30-day query of production mi_audit_log found 10 service_down
alerts and ZERO real outages — every one was a deploy restart caught in a
transient docker/HTTP state (`starting`, `created`, `removing`,
`restarting`, or the orchestrator's HTTP /health probe failing mid-restart)
that cleared on the very next 5-min cron tick. The fix: HARD-down states
(exited/dead/paused/container-not-found/inspect-timeout/docker-reported-
unhealthy) still alert on tick 1; SOFT (ambiguous) states now need 2
consecutive failing ticks before promoting to a real DOWN alert. See the
big comment above check_service() in infra/service_watchdog.sh for the
full design.

There is no shell test harness (no bats) in this repo, so this runs the
REAL script as a subprocess against a temp STATE_DIR/LOG_FILE and a fake
`docker` (+ fake `timeout`/`flock`, since this dev box doesn't ship GNU
coreutils' timeout or util-linux's flock) placed first on PATH. No
Telegram or DB credentials are put in the subprocess environment — both
`telegram_alert` (no token/chat id) and `audit_event` (docker exec routed
through the fake docker, `|| true`) already no-op safely without them, so
this also proves the script never needs real credentials to run.

The observable surface asserted on is the watchdog's LOG FILE content
(mirrors what an operator would grep in production) plus the STATE_DIR
pending-file, per the #532 task spec.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
WATCHDOG_SRC = REPO_ROOT / "infra" / "service_watchdog.sh"
OPS_LIB_SRC = REPO_ROOT / "infra" / "ops_lib.sh"

SVC = "fake-svc"

# ─── Fake external binaries ──────────────────────────────────────────────
# Content is env-var driven (FAKE_DOCKER_STATUS / FAKE_DOCKER_HEALTH /
# FAKE_DOCKER_NOTFOUND) so each subprocess.run() call can script a
# different docker-inspect answer for that one tick without any shared
# control file between ticks.
FAKE_DOCKER = """#!/usr/bin/env bash
# Fake `docker` for test_service_watchdog_532.py.
if [ "$1" = "inspect" ]; then
    if [ "${FAKE_DOCKER_NOTFOUND:-}" = "1" ]; then
        exit 1
    fi
    fmt="$3"
    case "$fmt" in
        *Health*) echo "${FAKE_DOCKER_HEALTH:-}" ;;
        *)        echo "${FAKE_DOCKER_STATUS:-running}" ;;
    esac
    exit 0
fi
if [ "$1" = "exec" ] && [ -n "${FAKE_DOCKER_CAPTURE:-}" ]; then
    # #442 write-side verification: record the REAL `docker exec ... psql
    # -c "INSERT ..."` argv audit_event() built, so a test can parse the
    # actual SQL literal it sends — not just that the call didn't crash.
    # One arg per line + a sentinel; none of these args contain embedded
    # newlines in the scenarios this harness drives.
    printf '%s\\n' "$@" >> "$FAKE_DOCKER_CAPTURE"
    printf '%s\\n' "===END_INVOCATION===" >> "$FAKE_DOCKER_CAPTURE"
fi
# Anything else (audit_event's `docker exec ... psql`, the disk-prune
# commands) — both call sites already tolerate a nonzero exit.
exit 1
"""

FAKE_TIMEOUT = """#!/usr/bin/env bash
# Fake `timeout` — this dev/CI box may not ship GNU coreutils' timeout.
# Drops the duration arg and execs the rest; no test here exercises the
# real timeout-expiry path (rc=124), so a plain passthrough suffices.
shift
exec "$@"
"""

FAKE_FLOCK = """#!/usr/bin/env bash
# Fake `flock` — this dev/CI box may not ship util-linux's flock, and
# every tick in these tests runs sequentially (nothing to guard against
# concurrently), so always succeeding is sufficient.
exit 0
"""

FAKE_CURL = """#!/usr/bin/env bash
# Fake `curl` for the orchestrator's HTTP /health probe branch in
# check_service() — the one soft-tier input not reachable through the
# fake docker (it's gated on svc == "apollo-orchestrator"). telegram_alert
# never reaches curl in these tests (no token in env → returns before its
# own curl call), so this only ever intercepts the /health probe.
if [ "${FAKE_CURL_FAIL:-}" = "1" ]; then
    exit 1
fi
exit 0
"""


def _write_exec(path: Path, content: str) -> None:
    path.write_text(content)
    mode = path.stat().st_mode
    path.chmod(mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)


@pytest.fixture
def fake_bin(tmp_path):
    bin_dir = tmp_path / "fakebin"
    bin_dir.mkdir()
    _write_exec(bin_dir / "docker", FAKE_DOCKER)
    _write_exec(bin_dir / "timeout", FAKE_TIMEOUT)
    _write_exec(bin_dir / "flock", FAKE_FLOCK)
    _write_exec(bin_dir / "curl", FAKE_CURL)
    return bin_dir


def _make_app_dir(tmp_path: Path) -> Path:
    """A hermetic APP_DIR containing only infra/ops_lib.sh — deliberately
    NOT the real repo root, and deliberately no .env file, so this test
    can never accidentally pick up real credentials regardless of what
    exists (now or later) at the repo root."""
    app_dir = tmp_path / "app"
    (app_dir / "infra").mkdir(parents=True)
    shutil.copy(OPS_LIB_SRC, app_dir / "infra" / "ops_lib.sh")
    return app_dir


def _run(script: Path, fake_bin: Path, app_dir: Path, state_dir: Path,
          log_file: Path, extra_env: dict | None = None) -> subprocess.CompletedProcess:
    base_path = os.environ.get("PATH", "/usr/bin:/bin")
    env = {
        "PATH": f"{fake_bin}:{base_path}",
        "HOME": os.environ.get("HOME", str(state_dir.parent)),
        "WATCHDOG_APP_DIR_OVERRIDE": str(app_dir),
        "WATCHDOG_STATE_DIR_OVERRIDE": str(state_dir),
        "WATCHDOG_LOG_FILE_OVERRIDE": str(log_file),
        "WATCHDOG_SERVICES_OVERRIDE": SVC,
    }
    if extra_env:
        env.update(extra_env)
    result = subprocess.run(
        ["bash", str(script)], env=env, capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, (
        f"watchdog script exited {result.returncode}\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )
    return result


@pytest.fixture
def watchdog(tmp_path, fake_bin):
    """Returns a `run(extra_env)` closure plus the log_file/state_dir paths,
    all wired to the REAL infra/service_watchdog.sh."""
    app_dir = _make_app_dir(tmp_path)
    state_dir = tmp_path / "state"
    log_file = tmp_path / "watchdog.log"

    def run(extra_env: dict | None = None) -> subprocess.CompletedProcess:
        return _run(WATCHDOG_SRC, fake_bin, app_dir, state_dir, log_file, extra_env)

    return {"run": run, "log_file": log_file, "state_dir": state_dir}


def _log_text(log_file: Path) -> str:
    """Reads the watchdog's log file and, on every read, asserts the
    internal `hard::`/`soft::` tier tag from check_service() never leaked
    into it. All log()/telegram_alert()/audit_event() calls are supposed
    to use the already-stripped `$reason`, never the raw `$raw`/`$tier`
    value — this is the operator-facing surface (verify-operator-facing-
    surface), and every existing test reads it through this helper so a
    future edit that swaps `$reason` for `$raw` at any call site fails
    every test that touches the log, not just a dedicated one."""
    text = log_file.read_text() if log_file.exists() else ""
    assert "hard::" not in text and "soft::" not in text, (
        "internal tier tag ('hard::'/'soft::') leaked into the "
        "operator-facing log/Telegram text:\n" + text
    )
    return text


# ─── Required cases ──────────────────────────────────────────────────────

def test_health_starting_then_healthy_is_the_ACTUAL_8_04_incident(watchdog):
    """⚠ THE PRODUCTION SHAPE, and it is NOT the same branch as the test below.

    The 2026-08-04 alert read `docker healthcheck: starting`, which means
    container `.State.Status` was **running** and `.State.Health.Status` was
    `starting`. That takes the HEALTH branch of check_service(). Setting
    FAKE_DOCKER_STATUS=starting (the test below) exercises the container-STATE
    branch instead — `starting` is not even a real Docker container state
    (created/running/paused/restarting/removing/exited/dead are).

    Both branches must route to the soft tier, but only this one reproduces the
    incident, so it gets its own test rather than being assumed covered. This is
    the repo's recurring defect class: a passing test on fabricated input that
    does not match the production surface.
    """
    run, log_file = watchdog["run"], watchdog["log_file"]

    run({"FAKE_DOCKER_STATUS": "running", "FAKE_DOCKER_HEALTH": "starting"})
    after_tick1 = _log_text(log_file)
    assert f"DOWN: {SVC}" not in after_tick1, "the 8/04 false alarm, reproduced"
    assert f"PENDING: {SVC}" in after_tick1
    assert "docker healthcheck: starting" in after_tick1, (
        "must reproduce the production reason string verbatim — if this drifts, "
        "the test has stopped describing the incident")

    run({"FAKE_DOCKER_STATUS": "running", "FAKE_DOCKER_HEALTH": "healthy"})
    full_log = _log_text(log_file)
    assert f"DOWN: {SVC}" not in full_log, "false alarm — the bug #532 fixes"
    assert f"PENDING CLEARED: {SVC}" in full_log


def test_health_starting_twice_alerts_on_tick_two(watchdog):
    """A container that genuinely never finishes booting still gets caught —
    just at tick 2 rather than tick 1. Health branch, matching the incident."""
    run, log_file = watchdog["run"], watchdog["log_file"]
    env = {"FAKE_DOCKER_STATUS": "running", "FAKE_DOCKER_HEALTH": "starting"}

    run(env)
    assert f"DOWN: {SVC}" not in _log_text(log_file), "must not fire on tick 1"
    run(env)
    assert f"DOWN: {SVC}" in _log_text(log_file), "must fire on the 2nd consecutive tick"


def test_mutation_health_starting_as_hard_down_restores_the_8_04_false_alarm(
        tmp_path, fake_bin):
    """Mutation proof for the HEALTH branch specifically — the branch the
    incident took. The existing mutation test below mutates the container-STATE
    branch, so on its own it would leave this one unpinned."""
    original = WATCHDOG_SRC.read_text()
    marker = 'if [ "$health" = "unhealthy" ]; then'
    assert original.count(marker) == 1, "health-tier branch shape changed — update this mutation"
    # Collapse the branch so EVERY non-healthy health status is hard-tier,
    # which is exactly the pre-#532 behaviour.
    mutated = original.replace(marker, 'if [ -n "$health" ]; then')
    assert mutated != original

    mutated_script = tmp_path / "mutated_health_watchdog.sh"
    mutated_script.write_text(mutated)
    mutated_script.chmod(0o755)

    _run(mutated_script, fake_bin, _make_app_dir(tmp_path), tmp_path / "state",
         tmp_path / "watchdog.log",
         {"FAKE_DOCKER_STATUS": "running", "FAKE_DOCKER_HEALTH": "starting"})

    assert f"DOWN: {SVC}" in _log_text(tmp_path / "watchdog.log"), (
        "with the health tier split reverted, a lone `starting` health status "
        "alerts on tick 1 again — that is the 8/04 false alarm returning, and "
        "it proves the un-mutated split is what prevents it")


def test_container_state_starting_then_healthy_produces_no_down_line(watchdog):
    """Container-STATE branch (not the incident shape — see the test above).
    Kept because the state branch's catch-all must also be soft."""
    run, log_file = watchdog["run"], watchdog["log_file"]

    run({"FAKE_DOCKER_STATUS": "starting"})
    after_tick1 = _log_text(log_file)
    assert f"DOWN: {SVC}" not in after_tick1
    assert f"PENDING: {SVC}" in after_tick1

    run({"FAKE_DOCKER_STATUS": "running"})
    full_log = _log_text(log_file)
    assert f"DOWN: {SVC}" not in full_log, "false alarm — the bug #532 fixes"
    assert f"PENDING CLEARED: {SVC}" in full_log


def test_starting_twice_alerts_on_tick_two_not_tick_one(watchdog):
    run, log_file = watchdog["run"], watchdog["log_file"]

    run({"FAKE_DOCKER_STATUS": "starting"})
    after_tick1 = _log_text(log_file)
    assert f"DOWN: {SVC}" not in after_tick1, "must not fire on tick 1"

    run({"FAKE_DOCKER_STATUS": "starting"})
    full_log = _log_text(log_file)
    assert f"DOWN: {SVC}" in full_log, "must fire on the 2nd consecutive failing tick"


def test_exited_alerts_immediately(watchdog):
    run, log_file = watchdog["run"], watchdog["log_file"]
    run({"FAKE_DOCKER_STATUS": "exited"})
    assert f"DOWN: {SVC}" in _log_text(log_file)


def test_unhealthy_alerts_immediately(watchdog):
    run, log_file = watchdog["run"], watchdog["log_file"]
    run({"FAKE_DOCKER_STATUS": "running", "FAKE_DOCKER_HEALTH": "unhealthy"})
    assert f"DOWN: {SVC}" in _log_text(log_file)


def test_container_not_found_alerts_immediately(watchdog):
    run, log_file = watchdog["run"], watchdog["log_file"]
    run({"FAKE_DOCKER_NOTFOUND": "1"})
    assert f"DOWN: {SVC}" in _log_text(log_file)


def test_recovery_path_intact_after_confirmed_down(watchdog):
    """Proves the recovery path is NOT what #532 touches — it already
    worked (verified against production watchdog.log + mi_audit_log
    before this fix) and must keep working."""
    run, log_file = watchdog["run"], watchdog["log_file"]

    run({"FAKE_DOCKER_STATUS": "exited"})
    assert f"DOWN: {SVC}" in _log_text(log_file)

    run({"FAKE_DOCKER_STATUS": "running"})
    assert f"RECOVERED: {SVC}" in _log_text(log_file)


def test_pending_file_removed_when_soft_down_clears(watchdog):
    run, state_dir = watchdog["run"], watchdog["state_dir"]
    pending_file = state_dir / f"{SVC}.pending"

    run({"FAKE_DOCKER_STATUS": "starting"})
    assert pending_file.exists()

    run({"FAKE_DOCKER_STATUS": "running"})
    assert not pending_file.exists(), "stale pending file must not survive recovery"


# ─── Additional coverage (design correctness beyond the required list) ──

@pytest.mark.parametrize("soft_state", ["created", "removing"])
def test_other_soft_states_alone_do_not_alert(tmp_path, fake_bin, soft_state):
    """The 8/02 incident states, not just `starting`: a `starting`-only fix
    would leave `created`/`removing`/`restarting` false alarms alive."""
    app_dir = _make_app_dir(tmp_path)
    state_dir = tmp_path / "state"
    log_file = tmp_path / "watchdog.log"
    _run(WATCHDOG_SRC, fake_bin, app_dir, state_dir, log_file,
         {"FAKE_DOCKER_STATUS": soft_state})
    assert f"DOWN: {SVC}" not in _log_text(log_file)


@pytest.mark.parametrize("hard_state", ["dead", "paused"])
def test_dead_paused_alert_immediately(tmp_path, fake_bin, hard_state):
    app_dir = _make_app_dir(tmp_path)
    state_dir = tmp_path / "state"
    log_file = tmp_path / "watchdog.log"
    _run(WATCHDOG_SRC, fake_bin, app_dir, state_dir, log_file,
         {"FAKE_DOCKER_STATUS": hard_state})
    assert f"DOWN: {SVC}" in _log_text(log_file)


def test_crash_loop_restarting_alerts_by_tick_two_and_stays_down(watchdog):
    """`restarting` is deliberately SOFT even though a crash-loop is a real
    outage — it stays `restarting` across ticks, so it still alerts by
    tick 2 (~10 min) rather than never, and then STAYS down on tick 3
    rather than spuriously recovering as the pending file would if it were
    re-armed every tick (the bug the `-f "$state_file"` branch guards)."""
    run, log_file = watchdog["run"], watchdog["log_file"]

    run({"FAKE_DOCKER_STATUS": "restarting"})
    assert f"DOWN: {SVC}" not in _log_text(log_file)

    run({"FAKE_DOCKER_STATUS": "restarting"})
    assert f"DOWN: {SVC}" in _log_text(log_file)

    run({"FAKE_DOCKER_STATUS": "restarting"})
    full_log = _log_text(log_file)
    assert f"RECOVERED: {SVC}" not in full_log, (
        "a persisting crash-loop must not spuriously RECOVER"
    )


def test_orchestrator_http_probe_failure_is_soft_not_hard(tmp_path, fake_bin):
    """The 8/02 22:55 incident: orchestrator HTTP /health probe fails
    mid-restart. Must behave as soft tier (2-tick confirm) — must NOT
    alert on tick 1, and must clear silently if the probe recovers. This
    is the one soft input not covered by the docker-state tests above,
    since the HTTP-probe branch in check_service() is gated on
    svc == "apollo-orchestrator" and every other test uses a fake service
    name to avoid needing a fake curl at all."""
    app_dir = _make_app_dir(tmp_path)
    state_dir = tmp_path / "state"
    log_file = tmp_path / "watchdog.log"
    base = {"WATCHDOG_SERVICES_OVERRIDE": "apollo-orchestrator", "FAKE_DOCKER_STATUS": "running"}

    _run(WATCHDOG_SRC, fake_bin, app_dir, state_dir, log_file,
         {**base, "FAKE_CURL_FAIL": "1"})
    after_tick1 = _log_text(log_file)
    assert "DOWN: apollo-orchestrator" not in after_tick1
    assert "PENDING: apollo-orchestrator" in after_tick1

    _run(WATCHDOG_SRC, fake_bin, app_dir, state_dir, log_file, base)
    full_log = _log_text(log_file)
    assert "DOWN: apollo-orchestrator" not in full_log, "false alarm — the bug #532 fixes"
    assert "PENDING CLEARED: apollo-orchestrator" in full_log


# ─── #442 write-side verification (2026-08-08) ───────────────────────────
# scripts/v1_closeout_status.py's tests prove the READ side (parsing a
# hand-written `detail` JSON string). That alone proves nothing about
# production: it doesn't catch a bash-quoting mistake in the JSON literal
# service_watchdog.sh actually builds. These tests run the REAL script +
# REAL ops_lib.sh audit_event() end to end and parse the ACTUAL SQL `-c`
# argument that would have been sent to psql — shell → SQL → JSON, no
# fabricated input.

def _captured_sql_statements(capture_file: Path) -> list[str]:
    """Parse FAKE_DOCKER_CAPTURE's one-arg-per-line log (see FAKE_DOCKER
    above) into the `-c` SQL argument string(s) audit_event() actually
    built — one per `docker exec ... psql ... -c "<sql>"` invocation."""
    if not capture_file.exists():
        return []
    blocks = capture_file.read_text().split("===END_INVOCATION===\n")
    sqls = []
    for block in blocks:
        args = block.splitlines()
        if "-c" in args:
            sqls.append(args[args.index("-c") + 1])
    return sqls


def _detail_json_for_event(capture_file: Path, event_type: str) -> dict | None:
    """The parsed `detail` JSON from the captured audit_event() SQL INSERT
    for `event_type` (None if the detail dollar-quote was empty)."""
    for sql in _captured_sql_statements(capture_file):
        if f"'{event_type}'" not in sql:
            continue
        m = re.search(r"\$apollo_detail\$(.*?)\$apollo_detail\$", sql, re.DOTALL)
        assert m, f"audit_event SQL is missing the detail dollar-quote entirely: {sql!r}"
        raw = m.group(1)
        return json.loads(raw) if raw else None
    return None


def test_service_down_audit_event_emits_parseable_structured_detail(tmp_path, fake_bin):
    """Hard-down (tick 1 alert) must produce a `service_down` audit_event()
    call whose `detail` is valid JSON carrying the container + state — the
    exact shape scripts/v1_closeout_status.py::_watchdog_target reads."""
    app_dir = _make_app_dir(tmp_path)
    state_dir = tmp_path / "state"
    log_file = tmp_path / "watchdog.log"
    capture_file = tmp_path / "docker_exec_calls.log"

    _run(WATCHDOG_SRC, fake_bin, app_dir, state_dir, log_file,
         {"FAKE_DOCKER_STATUS": "exited", "FAKE_DOCKER_CAPTURE": str(capture_file)})
    assert f"DOWN: {SVC}" in _log_text(log_file)

    detail = _detail_json_for_event(capture_file, "service_down")
    assert detail == {"container": SVC, "state": "down"}


def test_service_recovered_audit_event_emits_parseable_structured_detail(tmp_path, fake_bin):
    app_dir = _make_app_dir(tmp_path)
    state_dir = tmp_path / "state"
    log_file = tmp_path / "watchdog.log"
    capture_file = tmp_path / "docker_exec_calls.log"

    _run(WATCHDOG_SRC, fake_bin, app_dir, state_dir, log_file,
         {"FAKE_DOCKER_STATUS": "exited"})  # down first (no capture — not under test here)
    assert f"DOWN: {SVC}" in _log_text(log_file)

    _run(WATCHDOG_SRC, fake_bin, app_dir, state_dir, log_file,
         {"FAKE_DOCKER_STATUS": "running", "FAKE_DOCKER_CAPTURE": str(capture_file)})
    assert f"RECOVERED: {SVC}" in _log_text(log_file)

    detail = _detail_json_for_event(capture_file, "service_recovered")
    assert detail == {"container": SVC, "state": "recovered"}


def test_ops_lib_audit_event_two_arg_call_sends_literal_empty_detail(tmp_path, fake_bin):
    """Direct unit test of ops_lib.sh's audit_event() itself (not the full
    watchdog script — avoids depending on a wall-clock-gated code path like
    the heartbeat): every PRE-EXISTING 2-arg call site (backup.sh,
    staging_restore_check.sh, service_watchdog.sh's disk-space/heartbeat
    events) must see byte-identical SQL after #442 — a bare `''` literal
    for detail, not a (functionally-equivalent-but-changed) dollar-quoted
    empty string."""
    capture_file = tmp_path / "docker_exec_calls.log"
    base_path = os.environ.get("PATH", "/usr/bin:/bin")
    env = {"PATH": f"{fake_bin}:{base_path}", "FAKE_DOCKER_CAPTURE": str(capture_file)}
    script = f'source "{OPS_LIB_SRC}"; audit_event "test_two_arg" "a summary"'
    result = subprocess.run(["bash", "-c", script], env=env, capture_output=True,
                             text=True, timeout=10)
    assert result.returncode == 0, result.stderr

    sqls = [s for s in _captured_sql_statements(capture_file) if "'test_two_arg'" in s]
    assert len(sqls) == 1
    assert sqls[0].rstrip(";").endswith("'')"), sqls[0]


def test_ops_lib_audit_event_three_arg_call_dollar_quotes_detail(tmp_path, fake_bin):
    """The new 3rd-arg path: a real payload gets dollar-quoted and round-
    trips through psql's SQL literal syntax as valid JSON."""
    capture_file = tmp_path / "docker_exec_calls.log"
    base_path = os.environ.get("PATH", "/usr/bin:/bin")
    env = {"PATH": f"{fake_bin}:{base_path}", "FAKE_DOCKER_CAPTURE": str(capture_file)}
    script = (f'source "{OPS_LIB_SRC}"; '
              'audit_event "test_three_arg" "a summary" \'{"container":"x","state":"down"}\'')
    result = subprocess.run(["bash", "-c", script], env=env, capture_output=True,
                             text=True, timeout=10)
    assert result.returncode == 0, result.stderr

    detail = _detail_json_for_event(capture_file, "test_three_arg")
    assert detail == {"container": "x", "state": "down"}


# ─── Mutation check ───────────────────────────────────────────────────────

def test_mutation_treating_starting_as_hard_down_breaks_no_down_case(tmp_path, fake_bin):
    """Executable proof that test_starting_then_healthy_produces_no_down_line
    actually catches the regression it's meant to catch: reverting the tier
    split (routing `starting` into the hard-down case, same bucket as
    exited/dead/paused) must make a LONE `starting` tick alert immediately
    — the exact false alarm #532 measured (10 alerts / 0 outages)."""
    original = WATCHDOG_SRC.read_text()
    marker = "exited|dead|paused)"
    assert original.count(marker) == 1, "expected exactly one hard-tier case pattern"
    mutated = original.replace(marker, "exited|dead|paused|starting)")
    assert mutated != original

    mutated_script = tmp_path / "mutated_watchdog.sh"
    mutated_script.write_text(mutated)
    mutated_script.chmod(0o755)

    app_dir = _make_app_dir(tmp_path)
    state_dir = tmp_path / "state"
    log_file = tmp_path / "watchdog.log"

    _run(mutated_script, fake_bin, app_dir, state_dir, log_file,
         {"FAKE_DOCKER_STATUS": "starting"})

    assert f"DOWN: {SVC}" in _log_text(log_file), (
        "mutated script (starting treated as hard-down) should alert on "
        "tick 1 — proving the un-mutated script's tier split is what "
        "prevents that false alarm"
    )
