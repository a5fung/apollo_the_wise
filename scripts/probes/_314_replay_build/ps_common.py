#!/usr/bin/env python3
"""#314 parabolic-short five-year replay — shared module (docs/analysis/parabolic_short_replay_prereg_2026-10-21.md, round 4,
REGISTERED, NOT FROZEN; never edited here). Paths, the seal, the registered constants as code, the freeze record's pins, the
loaders (reused BY IMPORT from scripts/probes/_705_asis_1026/asis_common.py and scripts/probes/_cb_backtest/runner.py — never
copied), the append-only ledger (ours: asis_common's `ledger_append` / `ledger_verify` are bound to the #705 ledger path), the
Say / Claims printout helpers (the house pattern, copied verbatim as the four pattern files do), the freeze gates.

Nothing is opened at import. No network, no DB, no production server, no subagent.

READINGS where the plan is silent, ambiguous or contradicts itself (numbered across the ps_* modules; the main loop decides):
  R1  Output directory. The plan names every STEP 0 file (`climax_list.tsv`, `features.tsv`, `breaks_applied.tsv`, the pulls ...)
      but no directory. Taken: `/Users/alvinfung/apollo_data/ps314/` for the data files and the pulls (the pulls are hundreds of MB,
      never in git) and THIS folder for the printouts, the pins file and the ledger (committed, like the #705 reads). Overridable
      through `Paths` so the tests run on a synthetic tree.
  R2  The ledger. asis_common's `ledger_append` / `ledger_verify` read the module global `LEDGER` (the #705 ledger). Re-implemented
      here with an explicit path and the same four columns; never pointed at the #705 file.
  R3  Say / Claims / table / pct are copied verbatim from the pattern (01_points / 02_captions / 05_tiers / 00c_windows_v2 each carry
      the same copy) — importing 05_tiers for them would execute a 40 kB module whose only use here is twenty lines.
  R4  Era A's loader cut. `load_daily_subset(cut=...)` is called with cut = 2022-06-30 (the era-A file's own last session) so the same
      "a row dated after the cut survived" assertion runs on both eras; the seal (2024-12-31) is era B's cut.
  R5  The walk-golden fixture (tests/test_parabolic_short_shadow.py) is dated 2026-08-03.., AFTER the seal. The runner's test re-dates
      the same bars into 2023 on BOTH sides (the fixture dicts handed to `replay_episode` and the export written in the layout) so
      "byte-equal to `replay_episode` on the fixture dicts" still holds under the seal. The numbers (1.200260078, 0.969079613) do
      not depend on the dates. The synthetic export's SPY series is the fixture's own weekday list (`bdays`), not an exchange calendar.
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import importlib.util
import os
import re
import sys
from dataclasses import dataclass, field, replace
from datetime import date, timedelta
from pathlib import Path

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
if REPO not in sys.path:
    sys.path.insert(0, REPO)

DOC = os.path.join(REPO, "docs", "analysis", "parabolic_short_replay_prereg_2026-10-21.md")


def _load(name: str, path: str):
    """A module by path (the pattern's loader): asis_common has no package."""
    path = os.path.abspath(path)
    if name in sys.modules and os.path.abspath(getattr(sys.modules[name], "__file__", "") or "") == path:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


C = _load("asis_common", os.path.join(REPO, "scripts", "probes", "_705_asis_1026", "asis_common.py"))
from scripts.probes._cb_backtest import runner as RUN  # noqa: E402  (block_bootstrap_ci, load_breaks, break_mask, load_raw_close)
from agents.market_intelligence import consolidation_breakout as cb  # noqa: E402  (is_test_symbol, contiguous_window_mask, raw_factor_for)

sha = C.sha
doc_body_sha = C.doc_body_sha
freeze_missing = C.freeze_missing
printout_line = C.printout_line
printout_mismatches = C.printout_mismatches
printout_ends = C.printout_ends
dry_run_complete = C.dry_run_complete
load_daily_subset = C.load_daily_subset
load_raw_close_subset = C.load_raw_close_subset
load_splits = C.load_splits               # byte-identical copy of runner.load_splits (the plan names `runner.load_splits`)
factor_by_bar = C.factor_by_bar
Sessions = C.Sessions
rng_for = C.rng_for
fnum = C.fnum
Daily = C.Daily
block_bootstrap_ci = RUN.block_bootstrap_ci
load_breaks = RUN.load_breaks
break_mask = RUN.break_mask
load_raw_close = RUN.load_raw_close
is_test_symbol = cb.is_test_symbol
contiguous_window_mask = cb.contiguous_window_mask
raw_factor_for = cb.raw_factor_for


class GuardStop(Exception):
    pass


# ═════════════════════════════════════════════════════════════════════════════════════════════
# the registration, as code (every number below is the plan's; none is tuned here)
# ═════════════════════════════════════════════════════════════════════════════════════════════
CUT_B = "2024-12-31"                     # the seal: nothing dated after this is read from any bar file (2025-26 stays for #710)
A_FIRST, A_LAST = "2016-01-04", "2022-06-30"      # era A's file span (cb702_pre_v2)
B_FIRST = "2021-09-27"                            # era B's file starts here (Polygon); read through CUT_B only
HISTORY = 120                            # `_HISTORY_DAYS` rows ending at D0, CONSECUTIVE sessions of the era's calendar
WALK_AFTER = 7                           # the sessions an episode can occupy after D0: trigger by D0+3, 5 held sessions -> D0+7
A_D0_FIRST, A_D0_LAST = "2016-06-23", "2022-03-16"
B_D0_FIRST, B_D0_LAST = "2022-03-17", "2024-12-19"
A_SESSIONS, B_SESSIONS = 1635, 821
A_SCORABLE, B_SCORABLE = 1443, 695
SPLITS_THROUGH = "2026-10-16"            # era B's adjustment basis: splits executing after the file's last day are dropped (85)
P1_RAW_FLOOR, P1_DV_FLOOR = 5.0, 10_000_000.0       # the live floors (db.get_parabolic_universe)
BAND_RAW_FLOOR, BAND_DV_FLOOR = 1.0, 2_000_000.0    # the tradable floor fixed by the plan ($1 / $2M)
P1_DOLLAR_VOL_CONST, P2_DOLLAR_VOL_CONST = 10_000_000, 2_000_000   # `_MIN_DOLLAR_VOL_TODAY` per process
TICKER_RE = re.compile(r"^[A-Z]{1,5}$")
WUR_SUFFIX = ("W", "U", "R")             # a 5-letter symbol ending so, with no type, is a warrant / unit / right
ADMITTED_TYPES_P1 = ("CS", "ADRC", "")   # P1 admits CS / ADRC / unknown as live's SQL does
ADMITTED_TYPES_P2 = ("CS", "ADRC")       # P2 requires CS / ADRC by the point-in-time type; unknown -> a counted beside row
PERIODIC_FORMS = ("10-K", "10-Q", "10-KT", "10-QT", "20-F")
EARNINGS_ITEM = "2.02"
DISPOSITION_ITEM = "2.01"
GAP_CUT = -0.25                          # a session in D0+1..D0+7 whose open / prior close - 1 <= this is a distribution suspect
CA_WINDOW = (-2, 1)                      # Alpaca corporate action ex-date within [-2, +1] sessions of the gap date
ITEM_201_WINDOW = (-10, 4)               # an 8-K item 2.01 accepted within [gap - 10, gap + 4] sessions
NEWS_PAGES_K, NEWS_PAGE_LIMIT = 3, 1000
MNA_DAYS = 30                            # row (a): Polygon news dated [D0 - 30 calendar days, D0]
N_FLOOR = 30
TAIL_R, TAIL_TRADES, TAIL_COMPANIES, TAIL_MONTHS = 3.0, 3, 3, 3
TAIL_BESIDE_R = 2.0
PAUSE_CUT = 2                            # read 2: <= 2 vs >= 3
PAUSE_RATIO_CUT = 0.20
DILUTION_CUT = 0.20                      # read 5: >= 20% vs < 20%
HAIRCUT = 1.25                           # ended_mid_walk, adverse variant: cover at 1.25 x the last close
COLLAPSE_PRICE, COLLAPSE_RET, COLLAPSE_WINDOW = 1.0, -0.50, 60
PINNED_WINDOW, PINNED_SPREAD = 10, 0.01
ONE_DAY_FALL = -0.20
SLIPPAGES = (0.0, 0.001, 0.002)
BOOT_DRAWS, BOOT_SEED = RUN.BOOT_DRAWS, RUN.BOOT_SEED     # 2,000 / 702 (asserted by a test)
TIME_STOP_PRIMARY, TIME_STOP_READ1 = 5, 3
JUMP_FAC_CHANGE = 0.01                   # era A: the raw / adjusted factor on the jump date differs from the prior bar's by > 1%
OVERLAP_DIFF = 0.005                     # the printed overlap-disagreement share: closes differing by more than 0.5%
CAP_LARGE, CAP_MID = 10_000_000_000, 2_000_000_000
PLACEHOLDER_DELISTED = "2022-06-30"      # the straggler records' fetch cut-off, never a Polygon `delisted_utc`
RAW_UNKNOWN = "raw_unknown"

CONTROLS = {
    "distribution": (("OPLN", "2019-06-28"), ("ZWS", "2021-10-05")),      # the flagger must list both; the evidence rule must class both
    "distribution_printed": (("BEP", "2020-07-30"),),
    "earlier_issuer_B": (("INBX", "2024-05-31"), ("DOC", "2024-03-04")),  # must be excluded (identity_break) in era B
    "gme": ("GME", "2021-01"),                                             # printed, expected INSIDE the population
    "nvda": ("NVDA", "2024-03"),                                           # printed, expected not climax on every session
}

# ---- the freeze record (the plan's pins; the run refuses on any mismatch) ----------------------------------------------------------------
REGISTERED_PINS = {
    "export_B": "ccc0097fe535cb8de9b83d6d534744b6cbadc114d9d29ecac677ac18a52900ba",
    "splits_B": "3199d06d5fb7dcd52ebd34e8c71e148b45ec0ca4a15f7f03ea1b715718882b0b",
    "types_B": "b8d37aae5ef85c25bc52479eef7f6b04a8a4e67557caaef7a426d8ae20194643",
    "sic_B": "0e476c4422d56648d615c48d941edb971a348dfb99821023116d0fd98e617346",
    "guard_B": "b6cb81b6c4a1f415defc5adcf236402d93cd654c33736aa0b120b78c357b5650",
    "flags_B": "8bf843859afb70ea59edf6f11cda12160020936c8df3e978b6a819590ea5c3d5",
    "export_A": "0d5d2d0eb027abc06e4186ddec7d1e8b1234fd86f92c26798a8e15f113db668d",
    "raw_A": "f978db45074e9109178a1755c232fa1e684a6f83dab96ab007a26b12008f1444",
    "dedupe_A": "223d3f360369cc009919c6fae83b3ba0bb37aa437706b45fcbbb70560477cf64",
    "types_A": "d18e925b82ede2f5d4ca9ec8993d3d81f34ff10ebebec91b16f8b20e1aab0ff8",
    "sic_A": "0e476c4422d56648d615c48d941edb971a348dfb99821023116d0fd98e617346",
    "sessions_A": "098a9b50c92a1045043bc089a4d4d600a9631bdb45a8e22969d872440672f2f0",
    "guard_A": "876a75ec6d51744579c1ea2744c1b529cbd941355ef12eb8f0451bbe7ba1af08",
    "export_stats_A": "040b50dabb0de4aacd7009e1e4cbb22b8214dab2f0579dc90169777e475ca622",
    "verdict_A": "02cbb1c0106101cb12e8d5deb9448051ae3ced67966ac11d2475d06f26538de3",
    "flags_A": "5358e31dc1b27d25c5143bdfca7a98b91a6c7a2d5b1da6c9c9d9ed9c55474c1d",
    "build_v2": "16f861798a1ea9debfe4d633c650d2d0662484b008ce8f3b3f612ab097546a0b",
    "refetch_records": "a8c563fffeffee55eef162b6724a490b8db9e43d8b2a9c6c656ece2a1963f9b6",
    "parabolic_detector.py": "7530113b4defbdd10b7b02ba32c49b57261fdd32f609f65a28779e419e69cb0b",
    "parabolic_short_shadow.py": "3059e90e07e792e48c8fcf7e2c591786fb1d5da7496396cf3afc5e3e8abebb6b",
    "consolidation_breakout.py": "e14027be38b24352dd3c19fd5a1dcd54bae2e1cf80fc58a064d1ea65c821861b",
    "test_parabolic_short_shadow.py": "f697376ef050aff431d4828e6391cf04196e908f2eb3169004c33b584d4c6d56",
}
HISTORY_PINS = {   # round 2's survivors-only file: NOT read by this replay; its guard table's symbol list is read for the refetch cross-check
    "guard_pre": "6665c69f41bff3bd6ea913c66ccb9d0eab8bed0a9f020c32fa50c85d6cb6e6fc",
}

# ---- the plan's file-only facts (the dry run's claims; every one printed, none tuned) ---------------------------------------------------
FACTS = {
    "A_rows": 12_005_007, "A_symbols": 12_532, "A_sessions": 1635, "B_rows_kept": 8_619_626, "B_symbols_kept": 15_702, "B_sessions": 821,
    "B_rows_dropped": 5_210_943, "B_rows_total": 13_830_569, "B_symbols_total": 20_285,
    "A_other_chars": 176, "A_suffix_W": 182, "A_suffix_U": 247, "A_suffix_R": 39,
    "A_breaks": 667, "A_jump_only": 209, "A_hole_only": 357, "A_both": 101, "B_breaks": 1292,
    "dedupe_pairs": 98, "dedupe_rows": 61_512, "alias_outside_symbols": 15, "alias_outside_rows": 2927, "alias_inside_rows": 0,
    "adj_events_A": 93, "adj_events_B": 67, "splits_after_file": 85,
    "types_A_rows": 17_172, "types_A_symbols": 17_028, "types_A_twice": 144, "types_A_conflicts": 0, "types_B_rows": 14_102,
    "A_untyped_symbols": 1885, "A_untyped_reach_2m": 460, "A_ended_early": 3478, "refetch_added": 2669,
    "refetch_records": 3767, "refetch_record_symbols": 3765, "straggler_records": 31, "straggler_owned": 18,
    "A_jump_symbols": 310, "A_jump_symbols_dv2m": 194,
    "sic_names": 3942, "A_refetched_nokey": 46, "A_refetched_nokey_dv2m": 19,
    # symbol-level facts of the plan (a synthetic tree passes its own; None = not claimed)
    "full_session_symbols": ("TWTR", "ATVI", "EA", "X"),
    "fac_change_checks": (("APTV", "2017-12-05", True), ("DLPH", "2017-12-05", True), ("GME", "2021-01-27", False), ("GME", "2021-02-24", False)),
    "guard_breaks_of": ("GME", "2021-01-27:jump;2021-02-24:jump"),
    # R17 (review 10-28): the era-A split test. GME's factor is constant through era A (the plan, round 4: its 4-for-1 came 2022-07);
    # AAPL's 4-for-1 executed 2020-08-31 (public). (symbol, the dates of its factor steps above 1%) and (symbol, end, filed, split?)
    "fac_step_dates": (("GME", ()), ("AAPL", ("2020-08-31",))),
    "split_between_checks": (("GME", "2020-10-31", "2020-12-08", False), ("GME", "2020-12-31", "2021-01-29", False),
                             ("AAPL", "2020-06-27", "2020-07-31", False), ("AAPL", "2020-06-27", "2020-10-30", True)),
    "alias_rows": {"AGC": 667, "XL": 678, "PTIE": 340, "BRPM": 295, "ARYA": 237, "MACQ": 162, "DDMX": 151, "SNH": 125, "VICL": 101, "BIOS": 57,
                   "RSLS": 52, "KOOL": 43, "PRTHU": 13, "CYTX": 3, "RXII": 3},
    "alias_with_break": ("KOOL", "RSLS"),
    "stragglers_owning": ("BBBY", "BHG", "CDAY", "CPSI", "DADA", "HSC", "LAZY", "LPI", "MCG", "NOVA", "OBNK", "PLYA", "RLGY", "SASR", "SCHN",
                          "VIAC", "VIACA", "X"),
    "blank_record_rows": {"VIAC": 555, "VIACA": 555},
    "distribution_controls": (("OPLN", "2019-06-28"), ("ZWS", "2021-10-05")),
}

MODULE_FILES = ("ps_common.py", "ps_population.py", "ps_features.py", "ps_walk.py", "ps_goldens.py", "ps_stages.py", "ps_replay.py",
                "ps_rederive.py", "ps_pull.py")
LIVE_MODULES = {   # pinned, never edited: key -> repo path
    "parabolic_detector.py": "agents/market_intelligence/parabolic_detector.py",
    "parabolic_short_shadow.py": "agents/market_intelligence/parabolic_short_shadow.py",
    "consolidation_breakout.py": "agents/market_intelligence/consolidation_breakout.py",
    "test_parabolic_short_shadow.py": "tests/test_parabolic_short_shadow.py",
}
RUNNER_TESTS = {"test_parabolic_short_replay.py": "tests/test_parabolic_short_replay.py"}   # the synthetic detector golden's expected values
IMPORTED_HELPERS = {"asis_common.py": "scripts/probes/_705_asis_1026/asis_common.py", "runner.py": "scripts/probes/_cb_backtest/runner.py"}


# ═════════════════════════════════════════════════════════════════════════════════════════════
# paths (R1) — every path the read opens is a field here, so the tests run the whole pipeline on a synthetic tree
# ═════════════════════════════════════════════════════════════════════════════════════════════
@dataclass(frozen=True)
class Paths:
    data: str = "/Users/alvinfung/apollo_data"
    out: str = "/Users/alvinfung/apollo_data/ps314"
    here: str = HERE
    doc: str = DOC
    # era B
    export_B: str = ""
    splits_B: str = ""
    types_B: str = ""
    sic_B: str = ""
    guard_B: str = os.path.join(REPO, "scripts", "backtest_data_audit", "runs_2026-10-23", "universe", "symbol_guard_B.tsv")
    flags_B: str = ""
    # era A
    export_A: str = ""
    raw_A: str = ""
    dedupe_A: str = ""
    types_A: str = ""
    sic_A: str = ""
    sessions_A: str = ""
    guard_A: str = ""
    export_stats_A: str = ""
    verdict_A: str = ""
    flags_A: str = ""
    build_v2: str = os.path.join(REPO, "scripts", "probes", "_705_survivorship_1023", "08_build_v2.py")
    refetch_records: str = ""
    straggler_records: str = ""
    guard_pre: str = ""          # cb702_pre's guard table: its SYMBOL LIST only (the refetch-set cross-check); the export is never opened
    pins_override: str = ""      # TESTS ONLY: a JSON file of registered pins replacing the freeze record's (a synthetic tree has its own shas)

    def __post_init__(self):
        d = self.data
        defaults = {
            "export_B": f"{d}/cb702/daily_closes_all.csv.gz", "splits_B": f"{d}/cb702/cb702_splits.psv",
            "types_B": f"{d}/cb702/small_pulls.psv", "sic_B": f"{d}/cb702/cb702_sic.psv",
            "flags_B": f"{d}/audit_runs_2026-10-23/B_flags.tsv",
            "export_A": f"{d}/cb702_pre_v2/daily_closes_all.csv.gz", "raw_A": f"{d}/cb702_pre_v2/daily_raw_close.csv.gz",
            "dedupe_A": f"{d}/cb702_pre_v2/dedupe_applied.tsv", "types_A": f"{d}/cb702_pre_v2/small_pulls.psv",
            "sic_A": f"{d}/cb702_pre_v2/cb702_sic.psv", "sessions_A": f"{d}/cb702_pre_v2/sessions.txt",
            "guard_A": f"{d}/cb702_pre_v2/symbol_guard.tsv", "export_stats_A": f"{d}/cb702_pre_v2/export_stats.tsv",
            "verdict_A": f"{d}/cb702_pre_v2/audit_1023/verdict.txt", "flags_A": f"{d}/cb702_pre_v2/audit_1023/price/A_flags.tsv",
            "refetch_records": f"{d}/cb702_pre/survivorship_1023/refetch_combined_records_1023.tsv",
            "straggler_records": f"{d}/cb702_pre/survivorship_1023/stragglers_records.tsv",
            "guard_pre": f"{d}/cb702_pre/symbol_guard.tsv",
        }
        for k, v in defaults.items():
            if not getattr(self, k):
                object.__setattr__(self, k, v)

    # ---- STEP 0 outputs and pulls (under `out`) ----
    def o(self, name: str) -> str:
        return os.path.join(self.out, name)

    @property
    def calendar_B(self): return self.o("calendar_B.txt")
    @property
    def breaks_applied(self): return self.o("breaks_applied.tsv")
    @property
    def owners(self): return self.o("owners.tsv")
    @property
    def candidate_ciks(self): return self.o("candidate_ciks.txt")
    @property
    def climax_list(self): return self.o("climax_list.tsv")
    @property
    def features(self): return self.o("features.tsv")
    @property
    def distribution_flags(self): return self.o("distribution_flags.tsv")          # the flagger over ALL bars (climax-independent)
    @property
    def distribution_suspects(self): return self.o("distribution_suspects.tsv")    # the climax-tied suspects
    @property
    def distribution_class(self): return self.o("distribution_class.tsv")
    @property
    def episodes(self): return self.o("episodes.tsv")
    @property
    def polygon_reference(self): return self.o("polygon_reference.jsonl.gz")
    @property
    def edgar_submissions(self): return self.o("edgar_submissions.jsonl.gz")
    @property
    def xbrl_facts(self): return self.o("xbrl_facts.jsonl.gz")
    @property
    def xbrl_instances(self): return self.o("xbrl_instances.jsonl.gz")
    @property
    def polygon_news(self): return self.o("polygon_news.jsonl.gz")
    @property
    def alpaca_ca(self): return self.o("alpaca_corporate_actions.jsonl.gz")
    @property
    def filings_wanted(self): return self.o("filings_wanted.tsv")
    @property
    def news_wanted(self): return self.o("news_wanted.tsv")
    @property
    def suspects_wanted(self): return self.o("suspects_wanted.tsv")

    # ---- printouts, pins, ledger (under `here`) ----
    def p(self, name: str) -> str:
        return os.path.join(self.here, name)

    @property
    def dry(self): return self.p("ps_replay_dryrun.txt")
    @property
    def pins_file(self): return self.p("ps_replay_pins.txt")
    @property
    def ledger(self): return self.p("ps_ledger.tsv")
    @property
    def refused(self): return self.p("ps_replay.refused.txt")

    def step0_printout(self, phase: str) -> str:
        return self.p(f"ps_step0_{phase}.txt")

    @property
    def result(self): return self.p("ps_replay_result.txt")
    @property
    def rederive(self): return self.p("ps_replay_rederive.txt")


LOCAL = Paths()

INPUT_PIN_KEYS = ("export_B", "splits_B", "types_B", "sic_B", "guard_B", "flags_B", "export_A", "raw_A", "dedupe_A", "types_A", "sic_A",
                  "sessions_A", "guard_A", "export_stats_A", "verdict_A", "flags_A", "build_v2", "refetch_records")
STEP0_PIN_KEYS = ("polygon_reference", "edgar_submissions", "xbrl_facts", "xbrl_instances", "polygon_news", "alpaca_ca", "calendar_B",
                  "breaks_applied", "owners", "climax_list", "features", "distribution_flags", "distribution_suspects", "distribution_class")


def sha_or_absent(path: str) -> str:
    return sha(path) if os.path.exists(path) else "ABSENT"


def pins(P: Paths = LOCAL, include_outputs: bool = True) -> dict:
    """Every pin of this read: the inputs (the freeze record's), the live modules, the imported helpers, the runner's modules, the STEP 0
    files, the dry-run printout and the ledger, the doc body."""
    p = {}
    for k in INPUT_PIN_KEYS:
        p[k] = sha_or_absent(getattr(P, k))
    p["straggler_records"] = sha_or_absent(P.straggler_records)
    p["guard_pre"] = sha_or_absent(P.guard_pre)
    for k, rel in LIVE_MODULES.items():
        p[k] = sha_or_absent(os.path.join(REPO, rel))
    for k, rel in list(IMPORTED_HELPERS.items()) + list(RUNNER_TESTS.items()):
        p[k] = sha_or_absent(os.path.join(REPO, rel))
    for name in MODULE_FILES:
        p[name] = sha_or_absent(os.path.join(HERE, name))          # the code is always THIS folder's (printouts may live elsewhere)
    for k in STEP0_PIN_KEYS:
        p[k] = sha_or_absent(getattr(P, k))
    p["episodes"] = sha_or_absent(P.episodes)
    if include_outputs:
        p["dryrun_printout"] = sha_or_absent(P.dry)
        p["ledger"] = sha_or_absent(P.ledger)
        for ph in ("derive", "climax", "features"):
            p[f"step0_{ph}_printout"] = sha_or_absent(P.step0_printout(ph))
        p["result_printout"] = sha_or_absent(P.result)
    p["doc_body"] = doc_body_sha(P.doc) if os.path.exists(P.doc) else "ABSENT"
    return p


def registered_pin_problems(P: Paths = LOCAL) -> list:
    """Every input pin of the freeze record against the file on disk (the plan: 'refuses on any mismatch')."""
    out = []
    reg = REGISTERED_PINS
    if P.pins_override:
        import json
        with open(P.pins_override) as fh:
            reg = json.load(fh)
    for k, want in reg.items():
        if k in LIVE_MODULES:
            path = os.path.join(REPO, LIVE_MODULES[k])
        else:
            path = getattr(P, k)
        got = sha_or_absent(path)
        if got != want:
            out.append(f"{k}: {got[:16]} != pinned {want[:16]}")
    return out


def modules_line(P: Paths = LOCAL) -> str:
    """'<file> <sha16> ...' of the runner's modules as they are now — the ONE builder of every printout's `- modules:` line."""
    return " ".join(f"{n} {sha_or_absent(os.path.join(HERE, n))[:16]}" for n in MODULE_FILES)


# ═════════════════════════════════════════════════════════════════════════════════════════════
# the ledger (R2) — append-only; stage, path, sha256, time
# ═════════════════════════════════════════════════════════════════════════════════════════════
def ledger_append(path_ledger: str, stage: str, path: str) -> None:
    new = not os.path.exists(path_ledger)
    with open(path_ledger, "a") as fh:
        if new:
            fh.write("stage\tpath\tsha256\ttime\n")
        fh.write(f"{stage}\t{path}\t{sha(path)}\t{_dt.datetime.now().isoformat(timespec='seconds')}\n")


def ledger_rows(path_ledger: str) -> list:
    if not os.path.exists(path_ledger):
        return []
    with open(path_ledger, encoding="utf-8") as fh:
        lines = fh.read().splitlines()
    out = []
    for ln in lines[1:]:
        f = ln.split("\t")
        if len(f) >= 4:
            out.append({"stage": f[0], "path": f[1], "sha256": f[2], "time": f[3]})
    return out


def ledger_verify(path_ledger: str) -> list:
    """Every ledger row's file must exist with the recorded sha -> the problems (a deleted or regenerated file is caught)."""
    if not os.path.exists(path_ledger):
        return ["ledger missing"]
    bad = []
    for r in ledger_rows(path_ledger):
        if not os.path.exists(r["path"]):
            bad.append(f"{r['path']}: missing")
        elif sha(r["path"]) != r["sha256"]:
            bad.append(f"{r['path']}: changed since the ledger recorded it")
    return bad


def ledger_has_stage(path_ledger: str, prefix: str) -> list:
    return [r["stage"] for r in ledger_rows(path_ledger) if r["stage"].startswith(prefix)]


# ═════════════════════════════════════════════════════════════════════════════════════════════
# printout helpers (R3 — the house pattern, verbatim)
# ═════════════════════════════════════════════════════════════════════════════════════════════
class Say:
    def __init__(self):
        self.lines = []

    def __call__(self, msg: str = "") -> None:
        print(msg, flush=True)
        self.lines.append(msg)

    def write(self, path: str) -> None:
        with open(path + ".partial", "w", encoding="utf-8") as fh:
            fh.write("\n".join(self.lines) + "\n")
        os.replace(path + ".partial", path)


def pct(a, b) -> str:
    return f"{100.0 * a / b:.1f}%" if b else "n/a"


def table(say, hdr: list, rows: list) -> None:
    w = [max(len(str(x)) for x in col) for col in zip(hdr, *rows)] if rows else [len(h) for h in hdr]
    say("  " + "  ".join(str(h).ljust(w[k]) for k, h in enumerate(hdr)))
    for r in rows:
        say("  " + "  ".join(str(x).ljust(w[k]) for k, x in enumerate(r)))


class Claims:
    """The checks against the plan's own numbers: every one printed; the RESULT line counts OK / MISMATCH (never tuned)."""

    def __init__(self, say):
        self.say, self.rows = say, []

    def __call__(self, label: str, expected, got, tol: float = 0.0) -> None:
        if isinstance(expected, (int, float)) and isinstance(got, (int, float)):
            ok = abs(float(got) - float(expected)) <= tol
        else:
            ok = expected == got
        self.rows.append((label, expected, got, ok))
        self.say(f"  [{'OK' if ok else 'MISMATCH'}] {label}: expected {expected}, got {got}")

    def result(self) -> str:
        n, k = len(self.rows), sum(1 for r in self.rows if r[3])
        return f"RESULT: {n} claims, {k} OK, {n - k} MISMATCH"


# ═════════════════════════════════════════════════════════════════════════════════════════════
# small shared helpers
# ═════════════════════════════════════════════════════════════════════════════════════════════
def seal_date(d: str, what: str = "") -> None:
    """A date read from any bar file must be <= the seal."""
    if d > CUT_B:
        raise GuardStop(f"seal: a date after {CUT_B} was requested ({d}{' ' + what if what else ''}); 2025-26 is sealed")


def iso(d) -> str:
    return d.isoformat() if isinstance(d, date) else str(d)


def ord_of(d: str) -> int:
    return date.fromisoformat(d).toordinal()


def num(x) -> float:
    """A float from a numpy scalar / a ONE-element array (never float() of an array: numpy 2 refuses it; the plan's runner rule)."""
    return fnum(x)


def write_tsv(path: str, cols: list, rows: list) -> None:
    """Atomic: .partial then rename."""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path + ".partial", "w", encoding="utf-8") as fh:
        fh.write("\t".join(cols) + "\n")
        for r in rows:
            vals = [r.get(c) for c in cols] if isinstance(r, dict) else list(r)
            fh.write("\t".join("" if v is None else str(v) for v in vals) + "\n")
    os.replace(path + ".partial", path)


def read_tsv(path: str) -> list:
    import pandas as pd
    return pd.read_csv(path, sep="\t", dtype=str, keep_default_na=False).to_dict("records")


def next_nyse_session(d: str) -> str:
    """The NYSE session after `d` (exchange_calendars, offline — a calendar, never a bar file: reading it opens no sealed row)."""
    nxt = (date.fromisoformat(d) + timedelta(days=14)).isoformat()
    return [x for x in nyse_sessions(d, nxt) if x > d][0]


def nyse_sessions(first: str, last: str) -> list:
    """The NYSE calendar (exchange_calendars XNYS, rule-based, offline) between two dates inclusive, as ISO strings."""
    import exchange_calendars as xcals
    cal = xcals.get_calendar("XNYS")
    return [d.date().isoformat() for d in cal.sessions_in_range(first, last)]


def doc_frozen(doc: str = DOC) -> list:
    """The reasons the registration is not frozen (empty = frozen): exactly one marker line and `doc_body` pasted below it."""
    if not os.path.exists(doc):
        return [f"the registration is missing ({doc})"]
    miss = freeze_missing(doc, {"doc_body": doc_body_sha(doc)})
    return ["doc_body is not pinned below the doc's freeze marker (freeze first)"] if miss else []
