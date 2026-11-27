"""Stage 1d/1e shared setup. SEAL: no bar/row dated >= 2025-01-01 is opened (era B reads only the sealed copy). Prereg + A1 sha asserted."""
import hashlib, os, subprocess, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
SCR = Path("/private/tmp/claude-501/-Users-alvinfung-apollo-the-wise/d30e3944-e07e-4b44-97de-010acba78d0b/scratchpad/bws1124")
SCR.mkdir(parents=True, exist_ok=True)
os.environ["BV1_SCRATCH"] = str(SCR)
os.environ.setdefault("APOLLO_DATA", "/Users/alvinfung/apollo_data")
DATA = Path(os.environ["APOLLO_DATA"])
for p in (str(REPO), str(REPO / "scripts/probes/_breakout_v1_replay_1101")):
    if p not in sys.path:
        sys.path.insert(0, p)
PREREG = REPO / "docs/analysis/breakout_winner_study_prereg_DRAFT_2026-11-24.md"
PREREG_SHA = "3eb2b9b0247bc0ba7bf0d8e6f1efd67da1078fc090373c83c1bc14599339042a"
A1 = REPO / "docs/analysis/breakout_winner_study_prereg_amendment_A1_2026-11-26.md"
A1_SHA = "4a7beda14378ed2dea42308d92364dd92de4907aa3c7da4aaaffdffe75d17b10"
CUT = "2024-12-31"
OUT_DATA = DATA / "cb702"        # the only data dir this stage may write to


def sha256(p) -> str:
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def assert_docs():
    assert sha256(PREREG) == PREREG_SHA, "prereg sha256 differs - STOP"
    assert sha256(A1) == A1_SHA, "A1 sha256 differs - STOP"
    pins = __import__("json").loads((HERE.parent / "stage1ab/pins.json").read_text())
    for f, h in pins["files"].items():
        assert sha256(REPO / f) == h, f"pinned file changed: {f}"
