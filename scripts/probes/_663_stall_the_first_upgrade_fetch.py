"""#663 — the 2026-09-14 CI failure, reproduced deterministically with the REAL 25s ceiling.

WHAT CI SAW (run 34865695231, test_624's admitted-alert byte-identity guard): the FIRST of the
three scans logged `catalyst_type post-scan block failed (non-critical): ` with an EMPTY message
and no yfinance line, while scans 2 and 3 logged a yfinance 404 for BIG00. `str(TimeoutError())`
is '' on 3.11+. So: the harness makes a LIVE Yahoo Finance call per scan (collector
.get_recent_upgrade_events, reached from compute_setup_class_fields inside _judge_shadow); on
a fresh runner the first call paid Yahoo's cookie/crumb bootstrap and blew the 25s post-scan
wait_for ceiling; wait_for CANCELLED the gather; CancelledError is a BaseException, so the
`except Exception` guards did not fire and `r["setup_class"]` was never assigned in scan 1 —
the key d747f414 had just moved outside the classifier's try. Scans 2 and 3 were fast (cookie
cached) and carried the key. Shape differed; the guard failed; a re-run passed.

THIS PROBE models exactly that: the first upgrade-events call in the process stalls past the
ceiling, every later call returns instantly. No code is edited; the real wait_for, the real
cancellation and the real TimeoutError path all run.

    python scripts/probes/_663_stall_the_first_upgrade_fetch.py            # both guards
    python scripts/probes/_663_stall_the_first_upgrade_fetch.py --stall 27 # override the stall

MEASURED 2026-10-03 (stall 27s, real 25s ceiling):
  BEFORE the fix (origin/main bb5450a2 ep_detector) — both guards fail on SHAPE, the CI shape:
    test_624 admitted guard   -> 1 failed  KEY PRESENT ONLY IN B: <root>[0].setup_class = 'unclassified'
    ep_theme toggle-OFF guard -> 1 failed  KEY PRESENT ONLY IN B: <root>[0].setup_class = 'unclassified'
  AFTER (seed before the post-scan try) — the SHAPE is stable; what remains is the designed
  fail-open VALUE of a timed-out advisory (None) against a completed one ('unclassified'):
    both guards               -> 1 failed  TYPE: <root>[0].setup_class is NoneType in A, str in B
  That residual is NOT a defect to fix in the scan — an advisory that times out IS None by
  design — it is why the guards themselves must never make a call that can stall. They no
  longer do: `_run_scan_once` stubs the upgrade-events fetch and records any yfinance Ticker
  construction (tests/test_663_ep_scan_result_shape.py asserts the record is empty). This probe
  forces the stall by re-patching AFTER the harness, i.e. it models the network, not the guards
  as they run today.

Takes ~2 × stall seconds. The suite's own RED-proof (tests/test_663_ep_scan_result_shape.py)
shrinks the ceiling through the hoisted constant instead of sleeping.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import textwrap

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TARGETS = (
    "tests/test_624_lowcap_lane.py::"
    "test_run_ep_scan_is_byte_identical_with_an_admitted_alert_lane_on_off_and_raising",
    "tests/test_ep_theme_belonging.py::"
    "test_toggle_off_is_byte_identical_to_a_scan_with_no_belonging_at_all",
)

PLUGIN = """
import asyncio
import pytest

_CALLS = {"n": 0}

@pytest.fixture(autouse=True)
def _stall_the_first_upgrade_fetch(monkeypatch):
    # The harness (tests/test_624_lowcap_lane.py::_run_scan_once) may itself stub this name
    # once the fix lands; install AFTER it by patching from inside the test via a wrapper
    # around the scan entry point instead.
    import agents.market_intelligence.ep_detector as ed
    import agents.market_intelligence.setup_class_classifier as scc

    async def _first_call_stalls(ticker):
        _CALLS["n"] += 1
        if _CALLS["n"] == 1:
            await asyncio.sleep(__STALL__)
        return []

    real_run = ed.run_ep_scan

    async def _run(*a, **k):
        monkeypatch.setattr(scc, "get_recent_upgrade_events", _first_call_stalls)
        return await real_run(*a, **k)

    monkeypatch.setattr(ed, "run_ep_scan", _run)
    yield
"""


def run(target: str, stall: float, plugin_dir: str) -> str:
    with open(os.path.join(plugin_dir, "_663_stall_plugin.py"), "w") as fh:
        fh.write(textwrap.dedent(PLUGIN).replace("__STALL__", repr(float(stall))))
    env = {**os.environ, "PYTHONPATH": plugin_dir + os.pathsep + ROOT}
    p = subprocess.run([sys.executable, "-m", "pytest", target, "-q", "-p", "no:cacheprovider",
                        "-p", "_663_stall_plugin"], capture_output=True, text=True, cwd=ROOT, env=env)
    lines = p.stdout.splitlines()
    verdict = next((l for l in reversed(lines) if " passed" in l or " failed" in l), "no verdict")
    why = [l.strip() for l in lines if "<root>" in l or "AssertionError:" in l]
    return verdict + ("\n      " + "\n      ".join(dict.fromkeys(why)) if why else "")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--stall", type=float, default=27.0,
                    help="seconds the FIRST upgrade-events call sleeps (real ceiling is 25s)")
    ap.add_argument("--plugin-dir", default=os.environ.get("TMPDIR", "/tmp"))
    args = ap.parse_args()
    print(__doc__.split("\n\n")[0])
    for t in TARGETS:
        print(f"  {t.split('::')[-1]}\n    -> {run(t, args.stall, args.plugin_dir)}")
