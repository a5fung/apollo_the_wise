"""Stage 1a/1b shared setup. SEAL: nothing dated >= 2025-01-01 is opened. Era A bars end 2022-06-30 (asserted)."""
import hashlib, os, subprocess, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
SCR = Path("/private/tmp/claude-501/-Users-alvinfung-apollo-the-wise/d30e3944-e07e-4b44-97de-010acba78d0b/scratchpad/bws1124")
SCR.mkdir(parents=True, exist_ok=True)
os.environ["BV1_SCRATCH"] = str(SCR)          # own scratch folder (prereg 1.1)
os.environ.setdefault("APOLLO_DATA", "/Users/alvinfung/apollo_data")
DATA = Path(os.environ["APOLLO_DATA"])
for p in (str(REPO), str(REPO / "scripts/probes/_breakout_v1_replay_1101")):
    if p not in sys.path:
        sys.path.insert(0, p)

PREREG = REPO / "docs/analysis/breakout_winner_study_prereg_DRAFT_2026-11-24.md"
PREREG_SHA = "3eb2b9b0247bc0ba7bf0d8e6f1efd67da1078fc090373c83c1bc14599339042a"
PIN_FILES = [
    "agents/market_intelligence/breakout_v1.py",
    "agents/market_intelligence/breakout_v1_list.py",
    "agents/market_intelligence/consolidation_breakout.py",
    "agents/market_intelligence/breakout_v1_pick_model.py",
    "scripts/probes/_breakout_v1_replay_1101/v1_replay.py",
    "scripts/probes/_cb_backtest/runner.py",
    "scripts/probes/_717_precision_1112/01_precision.py",
    "scripts/probes/_717_pick_model_1113/01_build.py",
    "tests/fixtures/qm_breakout_scorecard/buys.tsv",
    "tests/fixtures/qm_breakout_scorecard/buys_undated_widened.tsv",
]
# informational (imported by the chain; not named in 1.1)
EXTRA_PIN_FILES = ["agents/market_intelligence/constants.py", "tests/fixtures/breakout_v1_parity/etv_names_2026-10-28.tsv"]


def sha256(p) -> str:
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def git(*a) -> str:
    return subprocess.run(["git", "-C", str(REPO), *a], capture_output=True, text=True, check=True).stdout.strip()


def assert_prereg():
    assert sha256(PREREG) == PREREG_SHA, "prereg sha256 differs - STOP"
