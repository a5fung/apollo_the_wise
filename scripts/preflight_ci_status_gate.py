"""Preflight [5p/7] — the replay-everything CI gate (ADR 0022 §3 L4, #313 / #302).

Regressions block DEPLOYS, never trades. Runs on the HOST (stdlib-only — the [5h/7] / [5m/7]
pattern; no container, no app imports, no DB) and reads `ci_status/<job>.json` files that the
scheduled regression jobs write IN-CONTAINER through the market-agent bind mount
(`/home/apollo/backups/ci_status` ↔ `/app/ci_status`). File shape (`agents/market_intelligence/
ci_status.py`): `{"job", "status": "green"|"red", "asof": "<ET ISO>", "detail"}`.

VERDICT RULES (signed 2026-07-05 — M3f thresholds live in the writers, M4f scope + the 7-day
stale rule live here):
  red  AND age <= 7d  → BLOCK (exit 1; deploy.sh maps it to exit 21) — but ONLY for the scopes
                        that ship trading code: market-agent / both / execution. An
                        orchestrator-only deploy is NEVER blocked (M4f rec, signed).
  red  AND age  > 7d  → WARN (stale — a dead CI job must not freeze deploys).
  green AND age > 7d  → WARN (stale: the job may be dead; its freshness is the signal).
  green AND age <= 7d → OK.
  missing file        → WARN, never block (the first deploy after this ships has no files, and
                        ADR jobs (b)/(c) have no writer yet).
  unreadable          → WARN, never block (bad JSON / unknown status / bad asof — printed).
The gate names the THREE jobs the ADR expects (`EXPECTED_JOBS`) so a missing writer is a
printed line rather than a silent skip; any other `*.json` in the directory is evaluated too.

OVERRIDE — operator only, for a hotfix, LOUD by design: `CI_OVERRIDE="<reason>"` turns a
BLOCK into a PASS and (1) prints a banner naming the red job and the reason, (2) appends a line
to `logs/ci_override.log`, (3) hands deploy.sh an `mi_audit_log` payload (`--audit-json`, the
[5m/7] envelope pattern) that it relays into the running container via
`scripts/log_judge_envelope_change.py` — this script itself has no DB access by design. An
empty `CI_OVERRIDE` is not an override. An override that was not needed (nothing red) is noted
and NOT logged — nothing was overridden.

Exit codes: 0 = proceed (OK or WARN), 1 = BLOCK. Nothing else — an unexpected exception here
is a bug in this gate, and deploy.sh treats any non-zero as a block, which is the safe side for
a gate whose job is to stop regressions shipping.

Run: CI_STATUS_DIR=/home/apollo/backups/ci_status python3 scripts/preflight_ci_status_gate.py --scope market-agent
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

REPO = Path(__file__).resolve().parent.parent
_ET = ZoneInfo("America/New_York")

DEFAULT_DIR = Path("/home/apollo/backups/ci_status")
ENV_DIR = "CI_STATUS_DIR"
ENV_OVERRIDE = "CI_OVERRIDE"
ENV_LOG = "CI_OVERRIDE_LOG"          # tests point this at a temp file; prod leaves it unset
DEFAULT_LOG = REPO / "logs" / "ci_override.log"

# Kept in lock-step with agents/market_intelligence/ci_status.EXPECTED_JOBS — duplicated here on
# purpose: this script must stay import-free of the app (host-side, stdlib-only). A test pins the
# two tuples equal.
EXPECTED_JOBS = ("selection_replay", "judge_eval", "entry_sim")
BLOCKING_SCOPES = frozenset({"market-agent", "both", "execution"})   # M4f (signed)
STALE_AFTER = timedelta(days=7)                                      # M3f stale rule (signed)
STATUSES = ("green", "red")

EXIT_OK = 0
EXIT_BLOCK = 1

AUDIT_EVENT = "ci_override_deploy"


# ── reading one file ─────────────────────────────────────────────────────────────────────────

def read_status(path: Path, now: datetime) -> dict:
    """One job's reading: `{job, state, status, age_days, detail, asof}` where state is one of
    green · red · stale · missing · unreadable. Never raises — every defect is a WARN reading."""
    job = path.stem
    base = {"job": job, "status": None, "age_days": None, "detail": "", "asof": None}
    if not path.exists():
        return {**base, "state": "missing", "detail": "no status file (writer never ran, or job not built)"}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:  # noqa: BLE001 — a corrupt file is a WARN reading, printed below
        return {**base, "state": "unreadable", "detail": f"not JSON ({e.__class__.__name__}: {e})"}
    if not isinstance(raw, dict):
        return {**base, "state": "unreadable", "detail": "JSON is not an object"}
    status = raw.get("status")
    if status not in STATUSES:
        return {**base, "state": "unreadable", "detail": f"status must be green|red, got {status!r}"}
    asof_raw = raw.get("asof")
    try:
        asof = datetime.fromisoformat(str(asof_raw))
        if asof.tzinfo is None:
            asof = asof.replace(tzinfo=_ET)   # the writers stamp ET; a bare stamp reads as ET
    except Exception as e:  # noqa: BLE001 — same: unreadable, printed
        return {**base, "status": status, "state": "unreadable",
                "detail": f"asof unparsable ({asof_raw!r}: {e})"}
    age = now - asof
    age_days = max(0.0, age.total_seconds() / 86400.0)
    detail = str(raw.get("detail", ""))
    state = "stale" if age > STALE_AFTER else status
    return {"job": job, "state": state, "status": status, "age_days": age_days,
            "detail": detail, "asof": asof.isoformat(timespec="seconds")}


def evaluate(status_dir: Path, now: datetime | None = None) -> list[dict]:
    """Readings for every expected job plus any extra `*.json` present, expected first."""
    now = now or datetime.now(timezone.utc)
    seen: list[str] = list(EXPECTED_JOBS)
    if status_dir.is_dir():
        for p in sorted(status_dir.glob("*.json")):
            if p.stem not in seen and not p.name.startswith("."):
                seen.append(p.stem)
    return [read_status(status_dir / f"{job}.json", now) for job in seen]


# ── the decision ─────────────────────────────────────────────────────────────────────────────

def decide(readings: list[dict], scope: str, override: str | None) -> dict:
    """`{exit, lines, blocking: [jobs], warns: [jobs], overridden: bool}`.

    `blocking` = the fresh-red jobs that WOULD block this scope. `overridden` is True only when
    there was something to override AND a non-empty override reason was given."""
    override = (override or "").strip() or None
    fresh_red = [r for r in readings if r["state"] == "red"]
    warns = [r for r in readings if r["state"] in ("stale", "missing", "unreadable")]
    scope_blocks = scope in BLOCKING_SCOPES
    blocking = fresh_red if scope_blocks else []
    lines: list[str] = []
    for r in readings:
        age = "" if r["age_days"] is None else f"{r['age_days']:.0f}d"
        if r["state"] == "green":
            tag = "green"
        elif r["state"] == "red":
            tag = "RED"
        elif r["state"] == "stale":
            tag = f"STALE-{r['status']} (>{STALE_AFTER.days}d) WARN"
        elif r["state"] == "missing":
            tag = "MISSING WARN"
        else:
            tag = "UNREADABLE WARN"
        lines.append(f"  {r['job']:<18} {tag:<28} {age:>4}  {r['detail']}")

    if blocking and override:
        names = ", ".join(r["job"] for r in blocking)
        lines.append("")
        lines.append(f"⚠️  CI GATE OVERRIDDEN (operator) — deploying scope '{scope}' over RED {names}: "
                     f"reason \"{override}\"")
        lines.append(f"⚠️  logged to logs/ci_override.log and mi_audit_log ({AUDIT_EVENT}, relayed by deploy.sh)")
        return {"exit": EXIT_OK, "lines": lines, "blocking": [r["job"] for r in blocking],
                "warns": [r["job"] for r in warns], "overridden": True, "override": override}
    if blocking:
        names = ", ".join(f"{r['job']} ({r['age_days']:.0f}d old)" for r in blocking)
        lines.append("")
        lines.append(f"DEPLOY BLOCKED — fresh RED CI status: {names} (ADR 0022 §3: a replay "
                     f"regression blocks deploys, never trades).")
        for r in blocking:
            lines.append(f"  {r['job']}: {r['detail']}")
        return {"exit": EXIT_BLOCK, "lines": lines, "blocking": [r["job"] for r in blocking],
                "warns": [r["job"] for r in warns], "overridden": False, "override": override}
    if fresh_red and not scope_blocks:
        names = ", ".join(r["job"] for r in fresh_red)
        lines.append(f"  (RED {names} noted — scope '{scope}' ships no trading code, never blocked: M4f)")
    if override:
        lines.append(f"  (CI_OVERRIDE set but nothing is RED for scope '{scope}' — nothing overridden, not logged)")
    summary = (f"CI gate — OK (scope {scope}; {len(fresh_red)} fresh red, {len(warns)} warn: "
               f"{', '.join(r['job'] for r in warns) or 'none'}).")
    lines.append(summary)
    return {"exit": EXIT_OK, "lines": lines, "blocking": [], "warns": [r["job"] for r in warns],
            "overridden": False, "override": override}


def audit_payload(verdict: dict, scope: str, readings: list[dict]) -> dict:
    """The `{event_type, summary, detail}` row deploy.sh relays via log_judge_envelope_change.py."""
    reds = {r["job"]: r["detail"] for r in readings if r["job"] in verdict["blocking"]}
    detail = "; ".join(f"{job}: {d}" for job, d in reds.items())
    return {
        "event_type": AUDIT_EVENT,
        "summary": (f"CI gate [5p/7] OVERRIDDEN for deploy scope {scope} over RED "
                    f"{', '.join(reds)} — reason: {verdict['override']}"),
        "detail": detail[:8000],
    }


def append_override_log(log_path: Path, verdict: dict, scope: str, now: datetime) -> bool:
    """One line per override, host-side under logs/. Returns False (and prints) on failure —
    a log write must never turn an operator's override into a block."""
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as fh:
            fh.write(f"{now.astimezone(_ET).isoformat(timespec='seconds')} scope={scope} "
                     f"red={','.join(verdict['blocking'])} user={os.environ.get('USER', '?')} "
                     f"reason={verdict['override']!r}\n")
        return True
    except Exception as e:  # noqa: BLE001 — printed; the audit row + banner still carry it
        print(f"⚠️  could not append to {log_path}: {e!r}")
        return False


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--scope", required=True, help="deploy scope (market-agent|orchestrator|both|execution)")
    ap.add_argument("--dir", default=os.environ.get(ENV_DIR) or str(DEFAULT_DIR),
                    help=f"status directory (default ${ENV_DIR} or {DEFAULT_DIR})")
    ap.add_argument("--log-file", default=os.environ.get(ENV_LOG) or str(DEFAULT_LOG),
                    help=f"override log (default ${ENV_LOG} or logs/ci_override.log)")
    ap.add_argument("--audit-json", action="store_true",
                    help="print ONLY the mi_audit_log payload line iff an override was used; exit 0")
    args = ap.parse_args(argv)

    now = datetime.now(timezone.utc)
    readings = evaluate(Path(args.dir), now)
    verdict = decide(readings, args.scope, os.environ.get(ENV_OVERRIDE))

    if args.audit_json:
        if verdict["overridden"]:
            print(json.dumps(audit_payload(verdict, args.scope, readings)))
        return EXIT_OK

    print(f"status dir: {args.dir}")
    for line in verdict["lines"]:
        print(line)
    if verdict["overridden"]:
        append_override_log(Path(args.log_file), verdict, args.scope, now)
    return verdict["exit"]


if __name__ == "__main__":
    sys.exit(main())
