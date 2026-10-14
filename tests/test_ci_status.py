"""agents/market_intelligence/ci_status.py — the replay-everything CI status writer (ADR 0022 §3
L4, #313 / #302).

First coverage of a new module (test_discipline.md rule 1). What is pinned here:
  * the selection-replay verdict at the SIGNED boundaries (M3f: drop >0.3R at n>=50) — n=49 is
    never red, n=50 with a drop of exactly 0.30R is green, 0.31R is red; n=0 is green and says so;
  * the file the writer produces (shape, ET offset-aware `asof`, atomic replace) and that a failed
    write returns None instead of raising;
  * the wiring that makes the files reach the deploy gate: the compose bind mount on the
    market-agent service, the in-container default path (`/app/ci_status` = WORKDIR + `ci_status`),
    and the gate script's expected-job list matching the module's.
"""
from __future__ import annotations

import importlib.util
import json
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
import yaml

import agents.market_intelligence.ci_status as cs

REPO = Path(__file__).resolve().parents[1]
_ET = ZoneInfo("America/New_York")
BASELINE = 0.95   # kill_scale_bands.CALIBRATION_ENVELOPE["expectancy_r"] — the #268b Phase-B number


@pytest.fixture
def status_dir(tmp_path, monkeypatch):
    monkeypatch.setenv(cs.ENV_DIR, str(tmp_path / "ci"))
    return tmp_path / "ci"


# ── the signed threshold, at its boundaries ──────────────────────────────────────────────────

@pytest.mark.parametrize("n, exp, want", [
    (0, None, "green"),      # no live trades: green, says the threshold is not armed
    (49, 0.50, "green"),     # gap 0.45R but n<50: NOT armed (M3f) — never red below 50
    (49, -1.00, "green"),
    (50, 0.65, "green"),     # gap exactly 0.30R at n=50: not > 0.3 → green (float-safe)
    (50, 0.64, "red"),       # gap 0.31R at n=50: red
    (50, 0.95, "green"),
    (120, 0.60, "red"),      # gap 0.35R at n=120: red
    (120, 1.20, "green"),    # live ABOVE calibration: never red
])
def test_selection_replay_verdict_at_the_signed_boundaries(n, exp, want):
    fp = {"n": n, "expectancy_r": exp} if exp is not None else {"n": 0}
    status, detail = cs.selection_replay_status(fp, BASELINE)
    assert status == want
    assert f"n={n}" in detail or (n == 0 and "n=0" in detail)


def test_verdict_detail_says_why_in_plain_words():
    _, below = cs.selection_replay_status({"n": 30, "expectancy_r": 0.10}, BASELINE)
    assert "n<50" in below and "not armed" in below
    _, red = cs.selection_replay_status({"n": 50, "expectancy_r": 0.10}, BASELINE)
    assert "REGRESSION" in red and "+0.85R" in red
    _, zero = cs.selection_replay_status({"n": 0}, BASELINE)
    assert "n=0" in zero and "n>=50" in zero


def test_verdict_carries_the_era_split_clause_but_it_never_changes_the_verdict():
    """#662: the pooled number is what M3f was signed against; the era split is context."""
    split = {"current": [0.5, 0.2], "older": [-1.0] * 48, "current_since": "2026-09-06"}
    status, detail = cs.selection_replay_status({"n": 50, "expectancy_r": 0.10}, BASELINE, era_split=split)
    assert status == "red"
    assert "older rules" in detail and "2 trades" in detail
    status2, _ = cs.selection_replay_status({"n": 50, "expectancy_r": 0.10}, BASELINE, era_split=None)
    assert status2 == "red"


# ── the file ─────────────────────────────────────────────────────────────────────────────────

def test_write_status_produces_the_gate_shape_with_an_et_offset_aware_asof(status_dir):
    p = cs.write_status("selection_replay", "red", "why", asof=datetime(2026, 10, 14, 15, 0, tzinfo=timezone.utc))
    assert p == status_dir / "selection_replay.json"
    raw = json.loads(p.read_text())
    assert raw == {"job": "selection_replay", "status": "red", "asof": "2026-10-14T11:00:00-04:00",
                   "detail": "why"}
    # no temp file left behind (atomic replace)
    assert sorted(x.name for x in status_dir.iterdir()) == ["selection_replay.json"]


def test_write_status_defaults_asof_to_now_in_et(status_dir):
    before = datetime.now(_ET)
    raw = json.loads(cs.write_status("entry_sim", "green", "d").read_text())
    asof = datetime.fromisoformat(raw["asof"])
    assert asof.utcoffset() == before.utcoffset() and abs((asof - before).total_seconds()) < 60


def test_write_status_rejects_bad_inputs_loudly(status_dir):
    with pytest.raises(ValueError):
        cs.write_status("x", "amber", "d")
    with pytest.raises(ValueError):
        cs.write_status("x", "green", "d", asof=datetime(2026, 1, 1))   # naive


def test_write_status_returns_none_instead_of_raising_when_the_dir_is_unwritable(tmp_path, monkeypatch, caplog):
    blocker = tmp_path / "file-not-dir"
    blocker.write_text("x")
    monkeypatch.setenv(cs.ENV_DIR, str(blocker / "ci"))   # parent is a FILE → mkdir fails
    with caplog.at_level("WARNING"):
        assert cs.write_status("selection_replay", "green", "d") is None
    assert any("could not write" in r.message for r in caplog.records)


def test_ci_status_dir_env_override_and_default(monkeypatch):
    monkeypatch.setenv(cs.ENV_DIR, "/elsewhere/ci")
    assert cs.ci_status_dir() == Path("/elsewhere/ci")
    monkeypatch.delenv(cs.ENV_DIR)
    assert cs.ci_status_dir() == cs.REPO / "ci_status"


# ── wiring: the files the writer produces are the files the deploy gate reads ────────────────

def test_compose_mounts_the_host_ci_status_dir_into_the_market_agent_writer_only():
    """The writer is weekly_system_review → replay_regression, an INTELLIGENCE-owned job that runs
    in apollo-market; the deploy gate reads the HOST path. So the mount belongs on market-agent
    and nowhere else — an execution-side mount would be a mount nothing writes to."""
    compose = yaml.safe_load((REPO / "docker/docker-compose.prod.yml").read_text(encoding="utf-8"))
    vols = compose["services"]["market-agent"]["volumes"]
    assert "/home/apollo/backups/ci_status:/app/ci_status" in vols
    for svc in ("orchestrator", "apollo-execution"):
        assert not any("ci_status" in v for v in compose["services"][svc].get("volumes", []))


def test_in_container_default_path_is_the_mount_target():
    """`ci_status_dir()` defaults to <repo>/ci_status; in the image the repo root is WORKDIR /app,
    so the default resolves to /app/ci_status — the compose mount target. A test that only
    checked the mount string could pass with the writer pointing somewhere else."""
    dockerfile = (REPO / "docker/Dockerfile.market").read_text(encoding="utf-8")
    workdir = next(l.split()[1] for l in dockerfile.splitlines() if l.startswith("WORKDIR"))
    assert workdir == "/app"
    assert cs.DEFAULT_DIR.relative_to(cs.REPO) == Path("ci_status")
    assert str(Path(workdir) / cs.DEFAULT_DIR.relative_to(cs.REPO)) == "/app/ci_status"


def test_the_weekly_replay_job_that_writes_the_file_runs_in_the_market_agent():
    from agents.market_intelligence import scheduler
    assert "weekly_system_review" in scheduler.INTELLIGENCE_OWNED_JOB_IDS
    assert "weekly_system_review" not in scheduler.EXECUTION_OWNED_JOB_IDS


def test_gate_script_expects_exactly_the_jobs_the_module_names():
    """The gate is host-side and stdlib-only, so it carries its own copy of the job list; the two
    must not drift (a job renamed in one place would read MISSING forever in the other)."""
    spec = importlib.util.spec_from_file_location("gate", REPO / "scripts" / "preflight_ci_status_gate.py")
    gate = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gate)
    assert tuple(gate.EXPECTED_JOBS) == tuple(cs.EXPECTED_JOBS)
    assert tuple(gate.STATUSES) == tuple(cs.STATUSES)
    # Review 2026-10-14: the not-built set drives "(not built)" vs "MISSING WARN"; the two copies
    # must agree, and every not-built job must be one the gate expects.
    assert tuple(gate.NOT_BUILT) == tuple(cs.NOT_BUILT_JOBS)
    assert set(cs.NOT_BUILT_JOBS) <= set(cs.EXPECTED_JOBS)
    assert cs.JOB_SELECTION_REPLAY not in cs.NOT_BUILT_JOBS     # it has the live writer
