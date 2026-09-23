"""#663 — can any UN-RESET module cache make the byte-identity guard diverge?

The guard runs two `run_ep_scan`s in ONE process and asserts they are identical. Module-level
dedupe/"seen" structures are first-call-does-X / later-calls-skip by design, so if the harness
does not clear them between the two scans, scan 1 can behave differently from scan 2 — and
whether it does depends on what earlier tests left behind. That is exactly the shape of a flake
that passes in isolation, passes on re-run, and fires once in CI.

Derived by AST (never hand-listed), `ep_detector` + `ep_theme_belonging` hold 14 module-level
mutable containers. The harness resets `_catalyst_cache`, `_audit_dedupe` and the three
`ep_theme_belonging` caches. THESE FOUR IT DOES NOT:
"""
from __future__ import annotations
import subprocess, sys, textwrap

TARGET = ("tests/test_ep_theme_belonging.py::"
          "test_toggle_off_is_byte_identical_to_a_scan_with_no_belonging_at_all")

POISONS = {
    "control (nothing poisoned)": "pass",
    "_tinycap_seen pre-populated": (
        "import agents.market_intelligence.ep_detector as ed\n"
        "from tests.test_624_lowcap_lane import ADMIT_TICKER, SESSION_DATE\n"
        "ed._tinycap_seen = {ADMIT_TICKER}\ned._tinycap_seen_date = SESSION_DATE"),
    "_rt_fresh_seen pre-populated": (
        "import agents.market_intelligence.ep_detector as ed\n"
        "from tests.test_624_lowcap_lane import ADMIT_TICKER, SESSION_DATE\n"
        "ed._rt_fresh_seen = {ADMIT_TICKER}\ned._rt_fresh_seen_date = SESSION_DATE"),
    "_repoll_shadow_state pre-populated": (
        "import agents.market_intelligence.ep_detector as ed\n"
        "from tests.test_624_lowcap_lane import ADMIT_TICKER, SESSION_DATE\n"
        "ed._repoll_shadow_state = {ADMIT_TICKER: {'poisoned': True}}\n"
        "ed._repoll_shadow_date = SESSION_DATE"),
    "_corp_action_set pre-populated": (
        "import agents.market_intelligence.ep_detector as ed\n"
        "from tests.test_624_lowcap_lane import ADMIT_TICKER, SESSION_DATE\n"
        "ed._corp_action_set = {ADMIT_TICKER}\ned._corp_action_date = SESSION_DATE"),
}

CONFTEST = """
import pytest
@pytest.fixture(autouse=True)
def _poison_before_the_guard(request):
    if request.node.nodeid.endswith("{node}"):
{body}
    yield
"""

def run(label: str, body: str) -> str:
    plugin = CONFTEST.format(node=TARGET.split("::")[-1],
                             body=textwrap.indent(body, " " * 8))
    with open("/tmp/_663_plugin.py", "w") as fh:
        fh.write(plugin)
    p = subprocess.run([sys.executable, "-m", "pytest", TARGET, "-q", "-p", "no:cacheprovider",
                        "-p", "_663_plugin"],
                       capture_output=True, text=True,
                       env={**__import__("os").environ, "PYTHONPATH": "/tmp:."})
    tail = [l for l in p.stdout.splitlines() if "passed" in l or "failed" in l]
    return (tail[-1] if tail else p.stdout.splitlines()[-1] if p.stdout else "no output")

if __name__ == "__main__":
    print(__doc__)
    for k in POISONS:
        print(f"  {k:<38s} -> {run(k, POISONS[k])}")
