"""Replay-everything CI status files — ADR 0022 §3 L4 (#313 / #302).

Each scheduled regression job writes ONE file, `ci_status/<job>.json`:

    {"job": "selection_replay", "status": "green" | "red",
     "asof": "<ET ISO-8601, offset-aware>", "detail": "<plain words>"}

and the on-host deploy gate `scripts/preflight_ci_status_gate.py` ([5p/7] in `scripts/deploy.sh`)
reads them: a RED younger than 7 days BLOCKS a market-agent / both / execution deploy (M4f);
stale, missing or unreadable files only WARN. Regressions block DEPLOYS, never trades — nothing
here is read by any trading path.

WHERE THE FILES LIVE. In the container the writers run under `/app` (Dockerfile.market WORKDIR),
so `ci_status_dir()` resolves to `/app/ci_status`, which `docker/docker-compose.prod.yml` bind-
mounts from `/home/apollo/backups/ci_status` on the host — the SAME directory the deploy gate
reads (repo-external on the host, like the watchdog state). Off-prod it is `<repo>/ci_status`
(git-ignored); `APOLLO_CI_STATUS_DIR` overrides both (the test suite points it at a temp dir).

THE SIGNED THRESHOLD (M3f, operator 2026-07-05) for the selection replay: red iff the live
realized expectancy sits more than 0.3R under the #268b Phase-B calibration (n=399) AND the live
cohort has at least 50 closed trades. Below 50 the threshold is NOT ARMED and the file says so —
it is still written, because a file that exists proves the job ran (a missing file is the
gate's dead-job signal). A writer that fails writes NOTHING (the previous file ages into WARN):
an error in the writer is not a regression and must never read as one.

Jobs (b) judge frozen-cohort eval and (c) entry-mechanics sim are NOT built (2026-10-14 — see
the ADR's L4 status line); the gate prints their absent files as "(not built)" information on
every deploy — NOT a WARN (review 2026-10-14: two permanent WARNs hid the one that matters, a
dead `selection_replay` writer, which reads MISSING WARN).
"""
from __future__ import annotations

import json
import logging
import os
import tempfile
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

_ET = ZoneInfo("America/New_York")
REPO = Path(__file__).resolve().parents[2]
ENV_DIR = "APOLLO_CI_STATUS_DIR"
# In-container this is /app/ci_status (the bind mount); on a laptop <repo>/ci_status (ignored).
DEFAULT_DIR = REPO / "ci_status"

STATUSES = ("green", "red")

# M3f (signed 2026-07-05): "replayed expectancy drop >0.3R vs baseline at N≥50".
SELECTION_REPLAY_MIN_N = 50
SELECTION_REPLAY_MAX_DROP_R = 0.3

# The three jobs ADR 0022 §3 names — the deploy gate expects each and WARNs on a missing one.
JOB_SELECTION_REPLAY = "selection_replay"
JOB_JUDGE_EVAL = "judge_eval"
JOB_ENTRY_SIM = "entry_sim"
EXPECTED_JOBS = (JOB_SELECTION_REPLAY, JOB_JUDGE_EVAL, JOB_ENTRY_SIM)
# The expected jobs with NO writer yet. The gate (which carries its own copy — host-side,
# stdlib-only; a test pins the two equal) prints their missing file as "(not built)", not WARN.
# Remove a job here AND in the gate the day its writer ships.
NOT_BUILT_JOBS = (JOB_JUDGE_EVAL, JOB_ENTRY_SIM)


def ci_status_dir() -> Path:
    """`APOLLO_CI_STATUS_DIR` if set, else `<repo>/ci_status` (= `/app/ci_status` in-container)."""
    override = os.environ.get(ENV_DIR, "").strip()
    return Path(override) if override else DEFAULT_DIR


def status_path(job: str) -> Path:
    return ci_status_dir() / f"{job}.json"


def write_status(job: str, status: str, detail: str, *, asof: datetime | None = None) -> Path | None:
    """Atomically write `ci_status/<job>.json`. Returns the path, or None when the write failed
    (logged as a WARNING — never raised: a status write must not break the job that computed
    the number, and a stale file aging into WARN is the designed failure signal)."""
    if status not in STATUSES:
        raise ValueError(f"ci_status: status must be one of {STATUSES}, got {status!r}")
    if asof is None:
        asof = datetime.now(_ET)
    elif asof.tzinfo is None:
        raise ValueError("ci_status: asof must be timezone-aware (ET)")
    payload = {
        "job": job,
        "status": status,
        "asof": asof.astimezone(_ET).isoformat(timespec="seconds"),
        "detail": detail,
    }
    path = status_path(job)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(prefix=f".{job}.", suffix=".json.tmp", dir=path.parent)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2)
            fh.write("\n")
        os.replace(tmp, path)
        return path
    except Exception as e:  # noqa: BLE001 — logged, never raised (see docstring)
        logger.warning(f"ci_status: could not write {path} for job {job!r}: {e!r}")
        return None


def selection_replay_status(fp: dict, baseline_expectancy_r: float, *, era_split: dict | None = None,
                            min_n: int = SELECTION_REPLAY_MIN_N,
                            max_drop_r: float = SELECTION_REPLAY_MAX_DROP_R) -> tuple[str, str]:
    """(status, detail) for the weekly selection replay from its fingerprint (`compute_fingerprint`)
    against the #268b calibration expectancy — exactly the ADR 0022 row, nothing more:
    red iff n ≥ `min_n` and (baseline − live expectancy) > `max_drop_r`.

    The fingerprint pools every live closed trade (that is the number M3f was signed against);
    `era_split` (#662, `rule_eras.split_current_vs_older`) is carried in the detail so a reader
    sees how many of those trades ran under today's rules — it does not change the verdict."""
    n = int(fp.get("n", 0) or 0)
    if n == 0:
        return "green", (f"no live closed trades yet (n=0); the >{max_drop_r:.1f}R threshold arms "
                         f"at n>={min_n} (M3f)")
    live = float(fp["expectancy_r"])
    drop = round(baseline_expectancy_r - live, 6)
    head = (f"live n={n} exp {live:+.2f}R vs calibration {baseline_expectancy_r:+.2f}R "
            f"(gap {drop:+.2f}R)")
    if n < min_n:
        status, verdict = "green", f"n<{min_n}: threshold not armed (M3f)"
    elif drop > max_drop_r:
        status, verdict = "red", (f"gap >{max_drop_r:.1f}R at n>={min_n}: replayed-expectancy "
                                  f"REGRESSION (M3f) — blocks market-agent/execution deploys")
    else:
        status, verdict = "green", f"gap <= {max_drop_r:.1f}R at n>={min_n}: within the signed band"
    detail = f"{head}; {verdict}"
    if era_split:
        try:
            from agents.market_intelligence.rule_eras import era_split_sentence
            detail += f"; {era_split_sentence(era_split)}"
        except Exception as e:  # noqa: BLE001 — the era clause is informational; the verdict stands
            logger.warning(f"ci_status: era clause unavailable for the selection replay: {e!r}")
    return status, detail
