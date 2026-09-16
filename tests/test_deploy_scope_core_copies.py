"""#656 — a `core/` file the market image COPYs must set NEED_MARKET and NEED_EXEC.

THE BUG THIS PINS, caught live 2026-09-13 and not theorised. `scripts/deploy.sh`'s scope-drift
guard routed `core/*` to NEED_ORCH and nothing else, while `docker/Dockerfile.market` COPYs
`core/notifications.py` and `core/job_audit.py` into the SHARED market/execution image. So #501's
loud-alert change touched `core/notifications.py`, `deploy.sh both` printed DEPLOY OK with no
execution warning, and `apollo-execution` kept raising AttributeError on the new symbol while
orchestrator and market both had it. Six of the eight newly-loud naked-position watchdogs are
EXECUTION_OWNED — the fix would have looked shipped and done nothing on the box that matters.

The arm was RIGHT when it was written and rotted the day those two COPY lines were added. That is
why the expectation here is DERIVED FROM THE DOCKERFILE rather than restated as a list: a
hand-written list in the test would rot exactly the same way the arm did, and would then certify
the rot. Same reasoning as `scripts/exec_loaded_modules.txt` (#456) and the #474 root-yaml COPY.

⚠ These tests EXECUTE the real shell out of `scripts/deploy.sh` — the helper and the whole
per-file `case` block are extracted verbatim and run — so they cannot pass against a
re-implementation that has drifted from the deployed script.
"""
from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
DEPLOY_SH = REPO / "scripts" / "deploy.sh"
DOCKERFILE = REPO / "docker" / "Dockerfile.market"

_HELPER = re.compile(
    r"^# >>> #656 scope helper.*?^# <<< #656 scope helper <<<$",
    re.S | re.M,
)
# The per-file classifier, verbatim: the flag reset through the end of the read loop.
_CASE_BLOCK = re.compile(
    r"^  NEED_ORCH=0; NEED_MARKET=0; NEED_EXEC=0\n(.*?^  done <<< \"\$CHANGED\")$",
    re.S | re.M,
)


def _deploy_src() -> str:
    return DEPLOY_SH.read_text(encoding="utf-8")


def _extract(pattern: re.Pattern, label: str) -> str:
    m = pattern.search(_deploy_src())
    assert m, (
        f"could not extract the {label} from scripts/deploy.sh — the markers or the block "
        f"shape changed. Fix the extraction rather than deleting the test: without it nothing "
        f"checks that a COPY'd core/ file reaches the execution container."
    )
    return m.group(0)


def core_paths_copied_into_market_image() -> set[str]:
    """The expectation, DERIVED — every `core/` path Dockerfile.market COPYs, explicit or under
    a directory COPY. Never a literal list; see the module docstring."""
    out: set[str] = set()
    for line in DOCKERFILE.read_text(encoding="utf-8").splitlines():
        parts = line.split()
        if not parts or parts[0] != "COPY" or len(parts) < 3:
            continue
        for src in parts[1:-1]:
            if src.startswith("--"):
                continue
            if src.startswith("core/"):
                out.add(src)
    return out


def _classify(changed: list[str]) -> dict[str, str]:
    """Run deploy.sh's OWN helper + case block over `changed`, return the three flags."""
    if shutil.which("bash") is None:  # pragma: no cover
        pytest.skip("bash unavailable")
    script = "\n".join([
        "set -uo pipefail",
        _extract(_HELPER, "#656 scope helper"),
        'CHANGED="' + "\n".join(changed) + '"',
        _extract(_CASE_BLOCK, "per-file case block"),
        'echo "ORCH=$NEED_ORCH MARKET=$NEED_MARKET EXEC=$NEED_EXEC"',
    ])
    r = subprocess.run(["bash", "-c", script], cwd=REPO, capture_output=True,
                       text=True, timeout=30)
    assert r.returncode == 0, f"extracted deploy.sh block failed: {r.stderr[-600:]}"
    return dict(kv.split("=", 1) for kv in r.stdout.strip().splitlines()[-1].split())


# ── the derivation itself must not go vacuous ────────────────────────────────────────────


def test_the_dockerfile_still_copies_core_files_into_the_market_image():
    """If this ever reads empty, every test below would pass by vacuity — which is how a
    guard that cannot fail reads exactly like one that passes. Fail loudly instead."""
    copied = core_paths_copied_into_market_image()
    assert copied, (
        "docker/Dockerfile.market no longer COPYs any core/ path. If that is deliberate, the "
        "#656 arm in deploy.sh is now dead code and should be removed WITH this test — do not "
        "leave a guard standing over a condition that can no longer occur."
    )


# ── the real decision, run out of deploy.sh ──────────────────────────────────────────────


def test_every_copied_core_file_reaches_market_and_execution():
    for path in sorted(core_paths_copied_into_market_image()):
        flags = _classify([path])
        assert flags == {"ORCH": "1", "MARKET": "1", "EXEC": "1"}, (
            f"{path} is COPY'd into the market/execution image but deploy.sh classified it "
            f"{flags}. This is the #656 bug: DEPLOY OK with apollo-execution left on stale code."
        )


def test_a_core_file_the_image_does_not_copy_stays_orchestrator_only():
    """The other half — the fix must not drag every core/ change into a three-service deploy.
    Without this, setting NEED_MARKET unconditionally on core/* would also pass above."""
    copied = core_paths_copied_into_market_image()
    uncopied = sorted(
        str(p.relative_to(REPO)) for p in (REPO / "core").glob("*.py")
        if str(p.relative_to(REPO)) not in copied
    )
    assert uncopied, "no un-COPY'd core/ file left to test the negative case with"
    for path in uncopied:
        flags = _classify([path])
        assert flags == {"ORCH": "1", "MARKET": "0", "EXEC": "0"}, (
            f"{path} is NOT in the market image, so it is orchestrator-only, but deploy.sh "
            f"classified it {flags} — that is deploy friction on every core/ edit."
        )


def test_the_merged_arm_that_rotted_is_gone():
    """`channels/*|core/*|main.py) NEED_ORCH=1` is the exact text that shipped the bug. Pin its
    absence: re-merging the arm would silently restore the defect and every other test here
    would still pass, because they exercise the classifier rather than its source text."""
    # source-pin-ok: this is the ONE assertion here that must read source text. Every other test
    # in this file runs the extracted classifier, so re-merging core/* into the channels arm
    # would restore the 2026-09-13 silent-dark bug while they all still passed — the behaviour
    # they check is identical either way until a core/ file actually changes in a real deploy.
    assert "core/*|main.py)" not in _deploy_src(), (
        "core/* is merged back into the channels/main.py arm — that arm grants NEED_ORCH only "
        "and is what left apollo-execution dark on 2026-09-13."
    )


def test_the_expectation_is_derived_from_the_dockerfile_not_hand_listed():
    """The DoD's actual requirement. A hand-kept list in the shell would rot the same way the
    arm did, so the arm must consult the Dockerfile at run time."""
    helper = _extract(_HELPER, "#656 scope helper")
    assert "docker/Dockerfile.market" in helper, "the helper no longer reads the Dockerfile"
    # Comments may quote a path as an EXAMPLE — that is documentation, not a list the shell
    # branches on. Only executable lines can rot into a hand-kept list, so only those count.
    code = "\n".join(l for l in helper.splitlines() if not l.lstrip().startswith("#"))
    for literal in sorted(core_paths_copied_into_market_image()):
        assert literal not in code, (
            f"{literal} is hard-coded into the helper's executable lines — that is the "
            f"hand-kept list this task exists to remove. Derive it from the COPY lines."
        )


def test_directory_copies_are_covered_too():
    """`COPY shared/ shared/` must match `shared/<anything>`, not only an exact path — a future
    `COPY core/ core/` has to be caught the same way, and prefix matching is what does it."""
    flags = _classify(["shared/some_new_module.py"])
    assert flags["MARKET"] == "1" and flags["EXEC"] == "1", (
        f"a file under a directory COPY was not recognised as image content: {flags}"
    )


# ── the DoD's own acceptance check, run rather than described ────────────────────────────

_DRIFT_BLOCK = re.compile(
    r"^  EXEC_DRIFT=0\n(.*?^  fi)$", re.S | re.M,
)


def test_touching_a_copied_core_file_warns_for_execution_on_deploy_both():
    """#656's acceptance check verbatim: *touch a COPY'd `core/` file, run `deploy.sh both`, and
    confirm it ABORTS or warns for execution.* WOULD-FAIL-IF it prints DEPLOY OK with no
    execution warning — which is exactly what it did on 2026-09-13.

    `both` resolves to SERVICES="market-agent orchestrator" (deploy.sh:104), which excludes
    apollo-execution, so the drift WARNING is the correct outcome rather than an abort: a
    core/ fix is a legitimate two-step. `docker ps` is stubbed to report the container running,
    because that is prod's state and the warning is deliberately silent when it is not."""
    copied = sorted(core_paths_copied_into_market_image())
    assert copied, "nothing to touch — see the vacuity guard above"
    script = "\n".join([
        "set -uo pipefail",
        'docker() { [ "$1" = ps ] && echo apollo-execution; }',   # prod's state
        _extract(_HELPER, "#656 scope helper"),
        'SERVICES="market-agent orchestrator"; SCOPE=both',
        'CHANGED="' + copied[0] + '"',
        _extract(_CASE_BLOCK, "per-file case block"),
        _extract(_DRIFT_BLOCK, "execution-drift warning block"),
        'echo "EXEC_DRIFT=$EXEC_DRIFT"',
    ])
    r = subprocess.run(["bash", "-c", script], cwd=REPO, capture_output=True,
                       text=True, timeout=30)
    assert r.returncode == 0, f"extracted block failed: {r.stderr[-600:]}"
    assert "EXEC_DRIFT=1" in r.stdout, (
        f"touching {copied[0]} and deploying `both` raised NO execution warning — the #656 "
        f"silent-dark path. Output:\n{r.stdout}"
    )
    assert "bash scripts/deploy.sh execution" in r.stdout, (
        "the warning fired but does not tell the operator the command to run"
    )
