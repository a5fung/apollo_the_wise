"""Stage 4 part 1 — BLIND RECOUNT, shared plumbing (written from the frozen prereg text + amendments A1/A2 alone).
Nothing here reads a stage 1/2/3 script or output. Live code is CALLED (the pinned chain), never re-coded.
SEAL: no bar/row dated >= 2025-01-01 is read (the sealed copy is rebuilt by v1_replay.sealed_copy_of_daily)."""
import os, sys, json, hashlib, gzip
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
OUTD = HERE / "out"
OUTD.mkdir(exist_ok=True)
DATA = Path("/Users/alvinfung/apollo_data")
BIG = DATA / "cb702"            # allowed write area for big captures (prefix r4_)
SCR = HERE / "scratch"          # own scratch folder (inside the allowed tree); sealed era-B copy lands here
SCR.mkdir(exist_ok=True)
os.environ["BV1_SCRATCH"] = str(SCR)
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "scripts/probes/_breakout_v1_replay_1101"))

SEAL = date(2025, 1, 1)
PRE = DATA / "cb702_pre_v2"
CB = DATA / "cb702"
GUARD_A = PRE / "symbol_guard.tsv"
GUARD_B = REPO / "scripts/backtest_data_audit/runs_2026-10-23/universe/symbol_guard_B.tsv"
FLAGS_A = PRE / "audit_1023/price/A_flags.tsv"
FLAGS_B = DATA / "audit_runs_2026-10-23/B_flags.tsv"
FLAG_KLASSES = {"known_adjustment_event", "discontinuous_across_known_adjustment"}
SPLITS_B = CB / "cb702_splits.psv"
BUYS = REPO / "tests/fixtures/qm_breakout_scorecard/buys.tsv"
BUYS_W = REPO / "tests/fixtures/qm_breakout_scorecard/buys_undated_widened.tsv"
SIC = {"A": PRE / "cb702_sic.psv", "B": CB / "cb702_sic.psv"}

PREREG_SHA = "3eb2b9b0247bc0ba7bf0d8e6f1efd67da1078fc090373c83c1bc14599339042a"
A1_SHA = "4a7beda14378ed2dea42308d92364dd92de4907aa3c7da4aaaffdffe75d17b10"


def sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def assert_pins():
    assert sha(REPO / "docs/analysis/breakout_winner_study_prereg_DRAFT_2026-11-24.md") == PREREG_SHA, "PREREG SHA DIFFERS - STOP"
    assert sha(REPO / "docs/analysis/breakout_winner_study_prereg_amendment_A1_2026-11-26.md") == A1_SHA, "A1 SHA DIFFERS - STOP"


def load_guard(path, era):
    """{symbol: sorted list of (date, kind)}; era B rows dated > 2024-12-31 dropped at read and counted."""
    out, dropped = {}, 0
    lines = Path(path).read_text().splitlines()
    head = lines[0].split("\t")
    ks, kb = head.index("symbol"), head.index("breaks")
    for ln in lines[1:]:
        f = ln.split("\t")
        if len(f) <= kb or not f[kb]:
            continue
        for x in f[kb].split(";"):
            d, k = x.split(":")
            if d >= SEAL.isoformat():
                dropped += 1
                continue
            out.setdefault(f[ks], []).append((date.fromisoformat(d), k))
    for s in out:
        out[s].sort()
    return out, dropped


def load_flags(path):
    """{ticker: sorted [date]} for the two adjustment klasses; dates >= 2025-01-01 dropped at read (string compare)."""
    import pandas as pd
    f = pd.read_csv(path, sep="\t", usecols=["klass", "ticker", "date"], dtype=str, keep_default_na=False)
    f = f[f.klass.isin(FLAG_KLASSES)]
    n0 = len(f)
    f = f[f.date < SEAL.isoformat()]
    out = {}
    for t, d in zip(f.ticker, f.date):
        out.setdefault(t, []).append(date.fromisoformat(d))
    for t in out:
        out[t].sort()
    return out, n0 - len(f)


FIX = os.environ.get("R4_FIX", "") == "1"      # post-trace variant: the two traced readings applied (see readings.md "POST-TRACE")
SUF = "_fix" if FIX else ""
