#!/usr/bin/env python3
"""#705 — QULLAMAGGIE REPLAY 02: the execution gaps. His 236 stream calls (era A; era B 9 descriptive) and the same day's other
breakouts, re-walked under four execution variants fixed from HIS WORDS before this run
(docs/analysis/cb_qm_replay_execution_prereg_2026-10-23.md). Registration only until the freeze; the real run happens ONCE after it.

The first replay (01_replay.py, frozen 2c080f19, run once) is IMPORTED read-only for its loaders, populations, walk wiring, trade
builder, account simulation, control draw, date-matched difference and G8; nothing in it is edited. The runner's walkers
(`cb.entry_variants`, `cb.day0_walk`, `cb.walk_arms`, `cb.forward_window`) are called unchanged.

What it does (the registration's §4-§7, nothing else):
  V0          the first read's primary, re-walked: ORH5, the low of the day at the fill, too-wide over OUR ADR20 skipped, exit
              p33_s3_t10, no re-entry, 1% risk / 20% cap / 30% per stock. A BASELINE-PARITY GATE: V0's trades, account curve,
              band and re-entry count must equal the first read's stored outputs before any variant number is printed.
  V1          "buy as it breaks out": the module's own `pivot` entry row (a buy-stop at the breakout level from the open: filled
              at the first minute whose high clears the level, at the level, or at that minute's open when it opened above it,
              0.1% slippage); stop = the lowest minute low from 09:30 through the fill minute, THAT MINUTE'S OWN LOW INCLUDED
              (the registration's §1.4b: a fill whose stop is its own minute's low — every fill in minute 0 — cannot be stopped
              inside that minute, and the too-wide skip and the size read that same low; counted beside every V1 / COMBINED table).
  V2          the stop-width rule on HIS screen's ADR: too-wide judged against TC2000's ADR% = mean(H / L) - 1 over the 20
              sessions ending D, not ours (mean((H - L) / C)). BESIDE: the runner's CAP-NOT-SKIP (a too-wide entry kept with its
              stop pulled to fill x (1 - our ADR20)).
  V3          re-entries ("even if we need to retry"): after a stop-out (`stopped` / `stopped_day0`, incl. a breakeven stop),
              the next break of the same (ticker, base_id) in the tl stream strictly after the exit day and within 20 sessions
              of E, under the same entry and stop; at most 2 re-entries; each its own trade in the account.
  V4          sizing: the 30% position cap at 1% risk (BESIDE: 0.5% risk at the 30% cap).
  COMBINED    V1 + V2 + V3 + V4 (BESIDE: at 0.5% risk).
  Every variant is applied to the control too; the band reuses the FIRST READ'S 200 same-day draws (same seed, same key), each
  drawn control event mapped to its trades under the variant.
  FORK        written before any outcome: COMBINED returns >= +50% in BOTH 2020 and 2021 at 1% risk AND at most 5% of the band's
              draws end at or above his final equity -> the execution gaps named here explain most of the shortfall; otherwise
              -> name the next gaps (NEXT_GAPS: stop placement beyond one ADR / the structural stop, adds / pyramiding, exit
              timing, market exposure, and the EPs and parabolic shorts in his record).

No subagent, no DB, no network. Read-only on every input. Nothing dated after 2024-12-31 is kept from any era-B file.

Run:  python3 scripts/probes/_705_qm_replay_1023/02_execution_variants.py --dry-run   (loads, asserts the populations and the
                                                    re-entry rows, reads ADR20 at D from bars up to D only, checks minute coverage
                                                    from the fetch logs, prints the pins; opens NO minute file, calls NO entry or
                                                    exit function, reads NO first-read outcome file, computes NO outcome)
      python3 scripts/probes/_705_qm_replay_1023/02_execution_variants.py             (the REAL run: refuses (exit 2) unless every
                                                    pin incl. the doc-body hash sits under the doc's one line-anchored freeze
                                                    marker line `<!-- FREEZE -->`, or if any output exists)
"""
from __future__ import annotations

import argparse
import bisect
import gzip
import hashlib
import importlib.util
import math
import os
import re
import sys
import time
import zlib
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
FIRST_PATH = os.path.join(HERE, "01_replay.py")


def _load_first():
    """The FROZEN first replay (pinned c4478588…), imported read-only."""
    spec = importlib.util.spec_from_file_location("_705_replay01_frozen", FIRST_PATH)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["_705_replay01_frozen"] = mod
    spec.loader.exec_module(mod)
    return mod


rp = _load_first()
R, cb, FIT = rp.R, rp.cb, rp.FIT

# ═════════════════════════════════════════════════════════════════════════════════════════════
# paths and pins
# ═════════════════════════════════════════════════════════════════════════════════════════════
DOC = os.path.join(REPO, "docs", "analysis", "cb_qm_replay_execution_prereg_2026-10-23.md")
PRINTOUT = os.path.join(HERE, "02_execution_variants.txt")
DRY_PRINTOUT = os.path.join(HERE, "02_execution_variants_dryrun.txt")
STOPPED = os.path.join(HERE, "02_execution_variants.STOPPED.txt")
OUT_DIR = f"{rp.B_DIR}/qm_streams/qm_exec_1023"
OUT_FILES = ("trades.tsv.gz", "chains.tsv", "g8_A.tsv", "g8_B.tsv", "g8_A_impact.txt", "g8_B_impact.txt", "account_his.tsv",
             "account_band.tsv")
# the first read's stored outputs: the baseline-parity gate reads them in the REAL run only (already-seen outcomes); the dry run hashes
# their bytes for the pins and parses nothing
FIRST = {
    "first_trades": f"{rp.OUT_DIR}/trades.tsv.gz",
    "first_account_his": f"{rp.OUT_DIR}/account_his.tsv",
    "first_account_band": f"{rp.OUT_DIR}/account_band.tsv",
    "first_printout": rp.PRINTOUT,
}
FILES = {**rp.FILES, **FIRST}
CODE = {**rp.CODE,
        "exec_module": os.path.abspath(__file__),
        "exec_tests": os.path.join(HERE, "test_02_execution_variants.py")}
# the first read's freeze record (docs/analysis/cb_qm_replay_prereg_2026-10-23.md, commit 2c080f19): the imported module, its tests and
# its doc body must be exactly the frozen ones; with the Track A pins 01 already carries
FIRST_MODULE_SHA = "c44785889670b31f3e9baf1ac0e1563aeacfefacc5de5ef426ee7b15724e7bfa"
FIRST_TESTS_SHA = "37c918a08329b138f6c37c5787af3c95e0ea2abeceb100209cd0f5f0dd0a96ad"
FIRST_DOC_BODY = "aaaadd295aba5a9de534a738410ebe391ac4993637faa7ead0cab78e2b7a9dab"
PINNED = {**rp.PINNED, "replay_module": FIRST_MODULE_SHA, "replay_tests": FIRST_TESTS_SHA}

# ═════════════════════════════════════════════════════════════════════════════════════════════
# the registration's constants
# ═════════════════════════════════════════════════════════════════════════════════════════════
CUT_B = rp.CUT_B
HORIZON = rp.HORIZON
PRIMARY_ARM = rp.PRIMARY_ARM                     # p33_s3_t10, the only exit walked here
EXIT_SLIPS = rp.EXIT_SLIPS
SEED = rp.SEED
BOOT_DRAWS = rp.BOOT_DRAWS
BAND_DRAWS = rp.BAND_DRAWS
BAND_KEY = f"qm_replay|band|A|{rp.BAND_REGISTERED}"          # the FIRST read's registered draws, reused (same seed, same key)
STRICT_BAND_KEY = "qm_replay|band|A|strictly-before (beside)"   # the first read's strictly-before draws
FIRST_DIFF_KEY = f"qm_replay|A|{rp.ENTRY}|{PRIMARY_ARM}|mean R"  # V0's date-matched difference = the first read's, same key
REENTRY_WINDOW = 20                              # a re-entry's break E2 satisfies exit day < E2 <= the session E + 20 (of the ORIGINAL E)
MAX_REENTRIES = 2
STOP_OUT = frozenset({"stopped", "stopped_day0"})  # what earns a retry (the original stop or the breakeven stop after the third)
FORK_YEARS = (2020, 2021)                        # BOTH must reach ...
FORK_RET = 0.50                                  # ... +50% (COMBINED, 1% risk, 30% cap) ...
BAND_SHARE_MAX = 0.05                            # ... AND at most 5% of the same-day band's draws at or above his final equity
ADR_PARITY_TOL = 1e-12                           # our ADR20 recomputed at D must equal the candidate's stored value
WIDTH_FLOOR_ADR = 0.25                           # BESIDE only: a stop narrower than 0.25 x our ADR20 makes R a unit artifact (#702's
TINY_WIDTH = 0.005                               # 10-22 floor); counted, and per-trade tables re-read without them; a 0.5% count beside
TC_ADR = "tc2000"
OURS_ADR = "ours"
ADR_GAP_LIST_PP = 2.0                            # DRY RUN, listed only: events where TC2000's ADR sits more than 2 points above ours (a
                                                 # bad low in the 20-day window opens the V2 / COMBINED too-wide gate on them)

EXPECT_SUPERSET = {                              # the re-entry rows, MEASURED by this module's dry run (2026-10-23) and asserted (outcome-free)
    "A_reentry_rows": 31272, "A_reentry_rows_already_events": 14564, "A_reentry_rows_already_events_excluded": 0,
    "A_new_rows": 16708, "A_new_rows_minutes_ok": 16708, "A_new_rows_break_pre": 0, "A_new_rows_kept": 16708,
    "B_reentry_rows": 638, "B_reentry_rows_already_events": 102, "B_reentry_rows_already_events_excluded": 0,
    "B_new_rows": 536, "B_new_rows_minutes_ok": 536, "B_new_rows_break_pre": 0, "B_new_rows_kept": 536,
}


@dataclass(frozen=True)
class EntrySet:
    """One entry rule: the `cb.entry_variants` row read, the ADR the too-wide rule is judged on, and what a too-wide entry does."""
    name: str
    variant: str        # "orh5" | "pivot" (the module's own rows)
    adr: str            # "ours" (the candidate's ADR20) | "tc2000" (mean(H / L) - 1, his screen)
    wide: str           # "skip" (the registered rule) | "cap" (the runner's CAP-NOT-SKIP: stop pulled to fill x (1 - our ADR20))


ENTRY_SETS = {
    "orh5": EntrySet("orh5", "orh5", OURS_ADR, "skip"),            # V0 / V3 / V4: the first read's primary entry
    "level": EntrySet("level", "pivot", OURS_ADR, "skip"),         # V1
    "orh5_tc": EntrySet("orh5_tc", "orh5", TC_ADR, "skip"),        # V2
    "orh5_cap": EntrySet("orh5_cap", "orh5", OURS_ADR, "cap"),     # V2 beside
    "level_tc": EntrySet("level_tc", "pivot", TC_ADR, "skip"),     # COMBINED's entry (V1 + V2)
}

CAP30 = rp.Config("cap_30", cap=0.30)                              # = the first read's `cap_30` row (1% risk, 30% cap, 30% per stock)
CAP30_R05 = rp.Config("cap_30_risk_0.5", cap=0.30, risk=0.005)


@dataclass(frozen=True)
class Variant:
    name: str
    label: str
    entry: str          # an ENTRY_SETS key
    chain: bool         # V3's re-entries
    cfg: "rp.Config"
    beside: bool = False


VARIANTS = (
    Variant("V0", "first read's primary (ORH5, our ADR, skip; no re-entry; 1% risk, 20% cap)", "orh5", False, rp.PRIMARY_CONFIG),
    Variant("V1", "buy as it breaks out (buy-stop at the level from the open)", "level", False, rp.PRIMARY_CONFIG),
    Variant("V2", "too-wide on his screen's ADR (TC2000 mean(H/L) - 1)", "orh5_tc", False, rp.PRIMARY_CONFIG),
    Variant("V2b", "CAP-NOT-SKIP: a too-wide stop pulled to one ADR (beside)", "orh5_cap", False, rp.PRIMARY_CONFIG, True),
    Variant("V3", "re-entries: up to 2, within 20 sessions of E", "orh5", True, rp.PRIMARY_CONFIG),
    Variant("V4", "30% position cap, 1% risk", "orh5", False, CAP30),
    Variant("V4b", "30% position cap, 0.5% risk (beside)", "orh5", False, CAP30_R05, True),
    Variant("COMBINED", "V1 + V2 + V3 + V4", "level_tc", True, CAP30),
    Variant("COMBINED_r05", "V1 + V2 + V3 at the 30% cap, 0.5% risk (beside)", "level_tc", True, CAP30_R05, True),
)
VMAP = {v.name: v for v in VARIANTS}
SAME_TRADES = {"V4": "V0", "V4b": "V0", "COMBINED_r05": "COMBINED"}   # sizing-only variants: the source's trades, another config
TRADE_VARIANTS = tuple(v.name for v in VARIANTS if v.name not in SAME_TRADES)   # the ones with their own per-trade numbers
FORK_VARIANT = "COMBINED"
assert all(VMAP[s].entry == VMAP[v].entry and VMAP[s].chain == VMAP[v].chain for v, s in SAME_TRADES.items())


class GuardStop(Exception):
    pass


# ═════════════════════════════════════════════════════════════════════════════════════════════
# the freeze lock — the marker is matched ONLY as its own line, exactly once (the first read's round-3 blocker: a split on the first
# occurrence anywhere let an inline mention cut the hash short)
# ═════════════════════════════════════════════════════════════════════════════════════════════
FREEZE_MARKER = "<!-- FREEZE -->"
_MARKER_LINE = re.compile(rb"^" + re.escape(FREEZE_MARKER.encode()) + rb"[ \t]*\r?$", re.M)


def marker_spans(raw: bytes) -> list:
    return [m.span() for m in _MARKER_LINE.finditer(raw)]


def doc_body_sha(doc: str) -> str:
    """sha256 of the doc's BYTES above its one line-anchored marker line (the whole file when there is not exactly one). At RUN time."""
    with open(doc, "rb") as fh:
        raw = fh.read()
    sp = marker_spans(raw)
    return hashlib.sha256(raw[:sp[0][0]] if len(sp) == 1 else raw).hexdigest()


def freeze_missing(doc: str, p: dict) -> list:
    """The pins NOT yet written below the doc's marker line. Not exactly one line-anchored marker -> every pin is missing (refused)."""
    with open(doc, "rb") as fh:
        raw = fh.read()
    sp = marker_spans(raw)
    if len(sp) != 1:
        return list(p)
    tail = raw[sp[0][1]:].decode("utf-8", errors="replace")
    return [k for k, v in p.items() if v not in tail]


def pins(minute_dates: "dict | None" = None, doc: "str | None" = None) -> dict:
    p = {name: rp.sha(path) for name, path in FILES.items()}
    p.update({name: rp.sha(path) for name, path in CODE.items()})
    p["first_doc_body"] = rp.doc_body_sha(rp.DOC)
    for era, dates in (minute_dates or {}).items():
        p[f"minutes_{era}_used"] = rp.tree_sha(rp.minute_files_used(era, dates))
    p["doc_body"] = doc_body_sha(doc or DOC)
    return p


def existing_outputs() -> list:
    out = [p for p in (PRINTOUT, STOPPED) if os.path.exists(p)]
    out += [os.path.join(OUT_DIR, f) for f in OUT_FILES if os.path.exists(os.path.join(OUT_DIR, f))]
    return out


# ═════════════════════════════════════════════════════════════════════════════════════════════
# outcome-free facts: ADR20 at D (ours and TC2000's), the re-entry rows, their data facts
# ═════════════════════════════════════════════════════════════════════════════════════════════
def adr_pair(bars, d_idx: int) -> tuple:
    """(ours, TC2000's) ADR20 at D from the 20 bars ENDING at D (index d_idx) — bars up to D only. Ours = mean((H - L) / C), the
    detector's `adr20_pct_from_bars` (the candidate's stored `adr20`); TC2000's = mean(H / L) - 1 (the ADR% on his screen,
    03_frame_check §3). Per bar (H - L) / L >= (H - L) / C because L <= C, so TC2000's is never below ours."""
    lo = d_idx - cb.ADR_WINDOW + 1
    if lo < 0:
        raise ValueError(f"ADR20 needs {cb.ADR_WINDOW} bars ending D, got {d_idx + 1}")
    h = np.asarray(bars.h[lo:d_idx + 1], dtype=float)
    l = np.asarray(bars.l[lo:d_idx + 1], dtype=float)
    c = np.asarray(bars.c[lo:d_idx + 1], dtype=float)
    if not ((l > 0).all() and (c > 0).all()):
        raise ValueError("ADR20 window holds a non-positive low or close")
    return float(np.mean((h - l) / c)), float(np.mean(h / l)) - 1.0


def d_index(bars, ev) -> int:
    """D's index inside the ticker's bars (asserted to be the bar right before E's)."""
    k = bisect.bisect_left(bars.dates, date.fromisoformat(ev.D))
    if not (k < len(bars.dates) and bars.dates[k].isoformat() == ev.D):
        raise ValueError(f"{ev.ticker}: no bar on D {ev.D}")
    return k


def history_reason(ev, bars, cidx, cal) -> "str | None":
    """Outcome-free (calendar indices only): None when the walk's wiring holds — a bar on E, 130 consecutive sessions ending E (the
    first read's `walk_event` assert), D = the bar before E — else the reason the row cannot be walked."""
    e_ci = bisect.bisect_left(cal, date.fromisoformat(ev.E))
    p = int(np.searchsorted(cidx, e_ci))
    if not (p < len(cidx) and int(cidx[p]) == e_ci):
        return "no_bar_on_E"
    if not (p >= cb.MIN_HISTORY and int(cidx[p]) - int(cidx[p - cb.MIN_HISTORY]) == cb.MIN_HISTORY):
        return "history_not_contiguous"
    if bars.dates[p - 1].isoformat() != ev.D:
        return "D_not_the_bar_before_E"
    return None


def event_facts(ev, D, qqq: tuple, guards: dict, done: dict, files: dict) -> None:
    """The first read's per-event facts (01_replay.load_all, the loop at l.1025-1037, line for line): the QQQ state at D, the identity
    break inside (E - 130, E], the fetch-log minute state, `keep`."""
    e_ci = bisect.bisect_left(D.cal, date.fromisoformat(ev.E))
    assert D.cal[e_ci].isoformat() == ev.E
    qb, qc = qqq
    d_ci = e_ci - 1
    p = int(np.searchsorted(qc, d_ci))
    ev.qqq = rp.qqq_state_at(qb.c, p) if (p < len(qc) and int(qc[p]) == d_ci) else ""
    lo, eo, _hi = rp.window_ords(D.cal, e_ci, rp.BREAK_PRE, rp.BREAK_POST)
    ev.break_pre = rp.break_in(guards.get(ev.ticker), lo, eo)
    st = done.get((ev.E, ev.ticker))
    ev.minutes_state = "ok" if (st == "ok" and ev.E in files) else ("empty" if st == "empty" else "missing")
    ev.keep = ev.minutes_state != "missing" and not ev.break_pre


def later_rows(ns) -> dict:
    """{(ticker, base_id): [(E, row index), ...] sorted by E} over EVERY row of one era's tl stream (the first read's re-entry count
    used the same rows)."""
    out = defaultdict(list)
    for i, (tk, b, E) in enumerate(zip(ns.ticker, ns.base_id, ns.E)):
        out[(str(tk), str(b))].append((str(E), i))
    for k in out:
        out[k].sort()
    return out


def prepare(S: dict, done: dict) -> dict:
    """The walk set: every kept event of the first read (his / control / post-E-only) PLUS every later row of a walked base within 20
    sessions of its E (the re-entry rows V3 may reach — which ones it reaches depends on the stop-outs, so all are walked). New rows
    get the first read's data facts and the walk-wiring check; a row that fails either is excluded (counted) and can never be a
    re-entry. Outcome-free: candidate keys, the calendar, the fetch logs, the identity-break files, labels. -> dict."""
    allev = {(x.era, x.ticker, x.E): x for x in S["evs"]}
    walk = {k: x for k, x in allev.items() if x.keep}
    later, lab, facts, new = {}, {}, Counter(), []
    bars_cache = {}
    for e in ("A", "B"):
        ns = S["eras"][e]
        D = S["Ds"][e]
        cal = D.cal
        later[e] = later_rows(ns)
        lab[e] = {(e, str(t), str(E)): bool(x) for t, E, x in zip(ns.ticker, ns.E, ns.cls["lab_by_E"])}
        need = set()
        for ev in [x for x in walk.values() if x.era == e]:
            e_ci = bisect.bisect_left(cal, date.fromisoformat(ev.E))
            lim = cal[min(len(cal) - 1, e_ci + REENTRY_WINDOW)].isoformat()
            for E2, i in later[e].get((ev.ticker, ev.base_id), []):
                if ev.E < E2 <= lim:
                    need.add(i)
        facts[f"{e}_reentry_rows"] = len(need)
        for i in sorted(need):
            k = (e, str(ns.ticker[i]), str(ns.E[i]))
            if k in allev:
                facts[f"{e}_reentry_rows_already_events"] += 1
                facts[f"{e}_reentry_rows_already_events_excluded"] += int(not allev[k].keep)
                continue
            E = str(ns.E[i])
            ev = rp.Event(era=e, ticker=str(ns.ticker[i]), D=str(ns.D[i]), E=E, base_id=str(ns.base_id[i]),
                          retrigger=int(ns.retrigger[i]), pivot=float(ns.pivot[i]), adr20=float(ns.adr20[i]), year=int(E[:4]),
                          month=E[:7], early_close=E in rp.EARLY_CLOSE)
            event_facts(ev, D, S["qqq"][e], S["guards"][e], done[e], S["files"][e])
            if (e, ev.ticker) not in bars_cache:                         # per ERA: the two eras' exports are different bars
                bars_cache[(e, ev.ticker)] = R.bars_for(D, D.tid[ev.ticker])
            bars, cidx = bars_cache[(e, ev.ticker)]
            why = history_reason(ev, bars, cidx, cal)
            if why:
                facts[f"{e}_new_rows_excluded_{why}"] += 1
                ev.keep = False
            facts[f"{e}_new_rows"] += 1
            facts[f"{e}_new_rows_minutes_{ev.minutes_state}"] += 1
            facts[f"{e}_new_rows_break_pre"] += int(ev.break_pre)
            facts[f"{e}_new_rows_kept"] += int(ev.keep)
            new.append(ev)
            if ev.keep:
                walk[k] = ev
    return dict(walk=walk, allev=allev, later=later, lab=lab, new=new, facts=facts)


def adr_facts(S: dict, X: dict) -> dict:
    """ADR20 at D for every event of the walk set, from bars ENDING at D (outcome-free): ours recomputed (must equal the stored
    `adr20`: the window is right), TC2000's, the gap. -> {key: (ours, tc)} and a Counter of parity failures."""
    out, bad, cache = {}, Counter(), {}
    for k, ev in X["walk"].items():
        D = S["Ds"][ev.era]
        if (ev.era, ev.ticker) not in cache:
            cache[(ev.era, ev.ticker)] = R.bars_for(D, D.tid[ev.ticker])
        bars, _cidx = cache[(ev.era, ev.ticker)]
        ours, tc = adr_pair(bars, d_index(bars, ev))
        if abs(ours - ev.adr20) > ADR_PARITY_TOL:
            bad[ev.era] += 1
        out[k] = (ours, tc)
    return out, bad


def widest_bar(bars, d_idx: int) -> tuple:
    """(date, H / L - 1) of the widest bar by H / L among the 20 bars ending D (bars up to D only): the bar that drives a large
    TC2000-minus-ours gap (one bad low lifts mean(H / L) by (H / L) / 20). Outcome-free."""
    lo = d_idx - cb.ADR_WINDOW + 1
    r = np.asarray(bars.h[lo:d_idx + 1], dtype=float) / np.asarray(bars.l[lo:d_idx + 1], dtype=float)
    j = int(np.argmax(r))
    return bars.dates[lo + j].isoformat(), float(r[j]) - 1.0


def adr_gap_events(S: dict, X: dict, adr: dict, era: str, pp: float = ADR_GAP_LIST_PP) -> dict:
    """DRY RUN, listed only (registration §4): {group: [(gap in points, ticker, E, widest bar date, its H / L - 1), ...], largest gap
    first} over the era's walk-set events where TC2000's ADR20 at D minus ours exceeds `pp` percentage points. Groups as the ADR
    summary (his / ctl / post / reentry rows; an event can sit in two). Outcome-free: bars up to D."""
    out, cache = {}, {}
    D = S["Ds"][era]
    for nm in ("his", "ctl", "post", "reentry rows"):
        rows = []
        for k, x in X["walk"].items():
            if x.era != era or not (getattr(x, nm) if nm != "reentry rows" else not (x.his or x.ctl or x.post)):
                continue
            gap = 100.0 * (adr[k][1] - adr[k][0])
            if gap <= pp:
                continue
            if x.ticker not in cache:
                cache[x.ticker] = R.bars_for(D, D.tid[x.ticker])
            bars, _cidx = cache[x.ticker]
            wd, wr = widest_bar(bars, d_index(bars, x))
            rows.append((gap, x.ticker, x.E, wd, wr))
        out[nm] = sorted(rows, key=lambda r: (-r[0], r[1], r[2]))
    return out


# ═════════════════════════════════════════════════════════════════════════════════════════════
# THE WALK (real run only)
# ═════════════════════════════════════════════════════════════════════════════════════════════
def cap_not_skip(entry: dict, minutes, adr20: float) -> dict:
    """The runner's CAP-NOT-SKIP (`runner.cap_sensitivity`, l.1420): a `too_wide` entry kept at its fill, the stop pulled up to
    fill x (1 - adr20) (one of OUR ADR20), the module's own `day0_walk` re-run on that stop. Built here (not called) because the
    account needs the walk's dated exit events, which the runner's row drops; parity with `runner.cap_sensitivity` is tested."""
    fill = float(entry["fill"])
    stop_c = fill * (1.0 - adr20)
    return {"status": "filled", "reason": None, "fill": fill, "stop": stop_c, "fill_minute": entry["fill_minute"],
            "width_pct": (fill - stop_c) / fill, "level": entry["level"],
            "day0": cb.day0_walk(minutes, fill_minute=entry["fill_minute"], stop=stop_c)}


def own_low_flag(mb, en: dict) -> "tuple | None":
    """PRINT-ONLY (registration §1.4b). For an entry that carries a fill minute — a fill, or a `too_wide` abstain — (own_low,
    first_bar): own_low = its stop IS the fill minute's own low (m == 0, or l[m] < l[:m].min(), m = the fill minute's index in the
    day's bars), so no stop-out can happen inside that minute, and the too-wide skip and the size read that same low; first_bar =
    m == 0 (the day's first minute bar: minute 0 whenever the stock traded at 09:30). None for any other entry. Decides nothing."""
    if not (en["status"] == "filled" or (en["status"] == "abstain" and en["reason"] == "too_wide")):
        return None
    if en.get("fill_minute") is None:
        return None
    m = int(np.searchsorted(mb.minute, en["fill_minute"]))
    assert m < len(mb.minute) and int(mb.minute[m]) == int(en["fill_minute"]), (en["fill_minute"], m)
    own = m == 0 or float(mb.l[m]) < float(mb.l[:m].min())
    assert not own or float(en["stop"]) == float(mb.l[m]), (en["stop"], float(mb.l[m]))   # the stop IS that minute's low
    return bool(own), m == 0


def walk_event2(ev, bars, cidx, e: int, mb, breaks: "np.ndarray | None", adr_tc: float) -> dict:
    """{"sets": {entry set: {"entry", "raw", "capped", "own_low"}}, n_fwd, hole, break_cut} for ONE event, wired exactly as the first
    read's `walk_event` (E alignment, the 130-session contiguity, closes_before through E, `forward_window`, the cut at an identity
    break after E), walking the PRIMARY arm only. `cb.entry_variants` runs twice: on our ADR20 and on TC2000's (only the too-wide rule
    reads it); every walk passes OUR ADR20 (it feeds only the ADR-unit column). `own_low` (print-only, `own_low_flag`) is set on the
    level / level_tc sets (V1's entry) and None on the others."""
    assert bars.dates[e].isoformat() == ev.E, (ev.ticker, e, ev.E)
    assert e >= cb.MIN_HISTORY and int(cidx[e]) - int(cidx[e - cb.MIN_HISTORY]) == cb.MIN_HISTORY, (ev.ticker, ev.E)
    kw = dict(pivot=ev.pivot, day_high=float(bars.h[e]), day_low=float(bars.l[e]))
    ent = {OURS_ADR: cb.entry_variants(mb, adr20=ev.adr20, **kw), TC_ADR: cb.entry_variants(mb, adr20=adr_tc, **kw)}
    closes_before = bars.c[:e + 1]
    assert float(closes_before[-1]) == float(bars.c[e])
    fwd, cut = cb.forward_window(bars, cidx, e, HORIZON)
    fwd, brk = rp.cut_at_break(fwd, bars.dates[e], breaks)
    out = {"n_fwd": len(fwd), "hole": bool(cut), "break_cut": brk, "sets": {}}
    arm = {PRIMARY_ARM: cb.ARMS[PRIMARY_ARM]}
    for name, es in ENTRY_SETS.items():
        en = ent[es.adr][es.variant]
        capped = False
        if es.wide == "cap" and en["status"] == "abstain" and en["reason"] == "too_wide":
            en = cap_not_skip(en, mb, ev.adr20)
            capped = True
        raw = None
        if en["status"] == "filled":
            raw = cb.walk_arms(en, closes_before=closes_before, fwd=fwd, adr20=ev.adr20, horizon=HORIZON, arms=arm)[PRIMARY_ARM]
        own = own_low_flag(mb, en) if es.variant == "pivot" else None
        out["sets"][name] = {"entry": en, "raw": raw, "capped": capped, "own_low": own}
    return out


def walk_all2(S: dict, X: dict, adr: dict) -> tuple:
    """Walk every event of the walk set once (his / control / post-E-only and the re-entry rows). -> (results, tally)."""
    res, tally = {}, Counter()
    for e in ("A", "B"):
        D = S["Ds"][e]
        by_date = defaultdict(list)
        for k, ev in X["walk"].items():
            if ev.era == e:
                by_date[ev.E].append(ev)
        cache = {}
        for di, (d, evs) in enumerate(sorted(by_date.items())):
            path = S["files"][e].get(d)
            if path is None:
                blocks, info = {}, {"truncated": False}
                tally[f"{e}_minute_date_file_absent"] += 1
            else:
                blocks, info = R.read_minute_file(path, want={x.ticker for x in evs})
            tally[f"{e}_minute_truncated"] += int(info["truncated"])
            done = {(d, x.ticker): x.minutes_state for x in evs}
            for ev in evs:
                mb, state = R.minutes_for(blocks, done, d, ev.ticker)
                tally[f"{e}_minutes_{state}"] += 1
                if ev.ticker not in cache:
                    cache[ev.ticker] = R.bars_for(D, D.tid[ev.ticker])
                bars, cidx = cache[ev.ticker]
                eidx = R.locate_breakout_index(D.cal, cidx, ev.E)
                k = (e, ev.ticker, ev.E)
                w = walk_event2(ev, bars, cidx, eidx, mb, breaks=S["guards"][e].get(ev.ticker), adr_tc=adr[k][1])
                if w["break_cut"]:
                    tally[f"{e}_forward_window_cut_at_a_break"] += 1
                w["bars"], w["cidx"], w["e"] = bars, cidx, eidx
                res[k] = w
            if (di + 1) % 100 == 0:
                print(f"  era {e}: {di + 1}/{len(by_date)} dates walked", flush=True)
    return res, tally


def trades_for_set(X: dict, res: dict, set_name: str) -> dict:
    """{(era, ticker, E): Trade} for every FILLED walk under one entry set (the first read's `make_trade`, unchanged)."""
    out = {}
    for k, w in res.items():
        s = w["sets"][set_name]
        if s["raw"] is None:
            continue
        out[k] = rp.make_trade(X["walk"][k], s["entry"], s["raw"], w["bars"], w["cidx"], w["e"], w["n_fwd"])
    return out


# ═════════════════════════════════════════════════════════════════════════════════════════════
# V3 — the re-entry chain
# ═════════════════════════════════════════════════════════════════════════════════════════════
def chain_of(origin: tuple, T: dict, rows: list, cal: list, refuse, counts: Counter) -> list:
    """The trades of ONE event's campaign: [origin] + up to MAX_REENTRIES re-entries. After a trade whose status is a stop-out
    (`STOP_OUT`), the re-entry is the first row of `rows` (the base's tl rows, sorted by E, as (E2, key)) with exit day < E2 <=
    the session ORIGINAL E + 20 that `refuse(key)` lets through (None) and that FILLED under the entry set (`key in T`); a row
    refused or not filled is passed (counted) and uses no slot. The chain ends at a non-stop exit, after MAX_REENTRIES re-entries,
    or when no row is left in the window. An origin that did not fill has no campaign ([])."""
    t = T.get(origin)
    if t is None:
        return []
    chain = [origin]
    lim = cal[min(len(cal) - 1, t.e_ci + REENTRY_WINDOW)].isoformat()
    cur, n_re = t, 0
    while n_re < MAX_REENTRIES and cur.status in STOP_OUT:
        exit_d = cal[cur.e_ci + cur.sessions_held].isoformat()
        nxt = None
        for E2, k2 in rows:
            if not (exit_d < E2 <= lim):
                continue
            why = refuse(k2)
            if why:
                counts[f"passed_{why}"] += 1
                continue
            t2 = T.get(k2)
            if t2 is None:
                counts["passed_not_filled"] += 1
                continue
            nxt = (k2, t2)
            break
        if nxt is None:
            break
        chain.append(nxt[0])
        cur = nxt[1]
        n_re += 1
        counts[f"reentry_{n_re}"] += 1
    return chain


def make_refuse(X: dict, era: str, control_rule: bool):
    """The rows a chain may NOT re-enter on: a row outside the walk set (a data exclusion: minutes missing, an identity break in
    (E - 130, E], the walk wiring) and, for a CONTROL chain only, a row the control's own round-3 rule excludes (its (stock, base)
    carries a matched label said on or before that row's E — the control stays 'not shown on stream by that day')."""
    walk, lab = X["walk"], X["lab"][era]

    def refuse(k2):
        if k2 not in walk:
            return "data_excluded"
        if control_rule and lab.get(k2, False):
            return "control_rule"
        return None
    return refuse


def campaigns(events: list, T: dict, X: dict, cal: list, chain: bool, control_rule: bool) -> tuple:
    """{origin key: [trade keys]} for every event of a group (chain False: the event's own trade, if filled) and the chain counts."""
    out, counts = {}, Counter()
    if not events:
        return out, counts
    era = events[0].era
    refuse = make_refuse(X, era, control_rule)
    for ev in events:
        k = (ev.era, ev.ticker, ev.E)
        if not chain:
            out[k] = [k] if k in T else []
            continue
        out[k] = chain_of(k, T, [(E2, (era, ev.ticker, E2)) for E2, _i in X["later"][era].get((ev.ticker, ev.base_id), [])],
                          cal, refuse, counts)
    return out, counts


def union_trades(camps: dict, keys, T: dict) -> list:
    """The account's trade list for a set of events: every trade of their campaigns, each (ticker, E) once."""
    seen, out = set(), []
    for k in keys:
        for t in camps.get(k, []):
            if t not in seen:
                seen.add(t)
                out.append(T[t])
    return out


def reentry_count_01(his: list, T: dict, X: dict, cal: list) -> tuple:
    """The first read's re-entry count (01_replay.run_replay, l.1393-1412), recomputed for the parity gate: (his trades stopped out,
    of them with a later break of the same base after the exit day and within 20 sessions of E, such breaks, of them his calls)."""
    n_stop = n_with = n_rows = n_his = 0
    his_keys = {(x.ticker, x.E) for x in his}
    for x in his:
        k = (x.era, x.ticker, x.E)
        if k not in T or T[k].status not in STOP_OUT:
            continue
        t = T[k]
        n_stop += 1
        exit_d = cal[t.e_ci + t.sessions_held].isoformat()
        lim = cal[min(len(cal) - 1, t.e_ci + REENTRY_WINDOW)].isoformat()
        nxt = [E for E, _i in X["later"][x.era].get((x.ticker, x.base_id), []) if exit_d < E <= lim]
        n_with += int(bool(nxt))
        n_rows += len(nxt)
        n_his += sum(1 for E in nxt if (x.ticker, E) in his_keys)
    return n_stop, n_with, n_rows, n_his


# ═════════════════════════════════════════════════════════════════════════════════════════════
# measures
# ═════════════════════════════════════════════════════════════════════════════════════════════
STAT_HDR = ["variant", "group", "events n", "trades n", "mature n", ">=5R /100 trades", ">=10R /100", ">=20R /100", "max R", "worst R",
            "win rate", "mean R", "median R", ">=10R /100 events", "mean R /event"]


def floor_ok(t, walk: dict) -> bool:
    """BESIDE: the trade's stop is at least WIDTH_FLOOR_ADR x our ADR20 wide (a near-zero stop — a gap fill whose first minute's low
    sits at its open — makes 1R a fraction of a percent, so its R is a unit artifact; the account bounds it by the cap)."""
    return t.width >= WIDTH_FLOOR_ADR * walk[t.key].adr20


def own_low_line(res: dict, G: dict, era: str, camps: dict) -> str:
    """PRINT-ONLY, beside every V1 / COMBINED table (registration §1.4b): per V1 entry set (level, level_tc) and group (his calls,
    the control), the fills and the too-wide skips whose stop is the fill minute's own low (`own_low_flag`), of all its fills / skips,
    and COMBINED's trades (re-entries included) so flagged. Decides nothing."""
    parts = []
    for s in ("level", "level_tc"):
        for nm in ("his", "ctl"):
            nf = ff = nw = fw = 0
            for x in G[nm]:
                cell = res[(x.era, x.ticker, x.E)]["sets"][s]
                fl = cell["own_low"]
                if fl is None:
                    continue
                if cell["entry"]["status"] == "filled":
                    nf, ff = nf + 1, ff + int(fl[0])
                else:
                    nw, fw = nw + 1, fw + int(fl[0])
            parts.append(f"{s} {nm}: fills {ff} of {nf}, too-wide skips {fw} of {nw}")
    ent = VMAP[FORK_VARIANT].entry
    for nm in ("his", "ctl"):
        tk = {t for x in G[nm] for t in camps[(era, FORK_VARIANT, nm)].get((x.era, x.ticker, x.E), [])}
        parts.append(f"COMBINED trades {nm} (re-entries included) {sum(1 for k in tk if res[k]['sets'][ent]['own_low'][0])} of {len(tk)}")
    return (f"- beside (§1.4b, decides nothing; era {era}): entries whose stop is the fill minute's own low (minute 0, or a fill "
            f"minute that made a new low of the day: no stop-out can happen inside that minute; the too-wide skip and the size read "
            f"that low): " + "; ".join(parts))


def without_first_bar(T: dict, res: dict, set_name: str) -> dict:
    """PRINT-ONLY (registration §6, beside): the entry set's trades minus every fill on the day's first minute bar (`own_low_flag`'s
    first_bar, m == 0). Such a fill is treated as not filled: a chain passes its row (no slot) and an origin so filled has no
    campaign."""
    out = {}
    for k, t in T.items():
        fl = res[k]["sets"][set_name]["own_low"]
        assert fl is not None, (k, set_name)
        if not fl[1]:
            out[k] = t
    return out


def trade_row(vname: str, group: str, n_events: int, trades: list, slip_i: int = 0) -> list:
    """Per TRADE, tail first, over mature trades; the per-100-events beside counts a trade that is not mature in neither denominator."""
    mat = [t for t in trades if t.mature]
    r = [t.r_slip[slip_i] for t in mat]
    st = rp.tail_stats(r, n_events=n_events - (len(trades) - len(mat)))
    return [vname, group, n_events, len(trades), len(mat), rp.fmt(st.get("ge5"), 1), rp.fmt(st.get("ge10"), 1),
            rp.fmt(st.get("ge20"), 1), rp.fmt(st.get("max")), rp.fmt(st.get("worst")), rp.pct(st.get("win")), rp.fmt(st.get("mean"), 3),
            rp.fmt(st.get("median"), 3), rp.fmt(st.get("ge10_ev"), 1), rp.fmt(st.get("mean_ev"), 3)]


def campaign_values(events: list, camps: dict, T: dict, slip_i: int = 0) -> tuple:
    """Per EVENT: the campaign R = the sum of its trades' R (each trade risks the same fraction of the account), for campaigns whose
    every trade is mature. -> (values, events used (list), filled n, mature n)."""
    vals, used, nf = [], [], 0
    for ev in events:
        ch = camps.get((ev.era, ev.ticker, ev.E)) or []
        if not ch:
            continue
        nf += 1
        ts = [T[k] for k in ch]
        if not all(t.mature for t in ts):
            continue
        vals.append(sum(t.r_slip[slip_i] for t in ts))
        used.append(ev)
    return vals, used, nf, len(used)


def campaign_row(vname: str, group: str, events: list, camps: dict, T: dict) -> list:
    vals, _used, nf, nm = campaign_values(events, camps, T)
    st = rp.tail_stats(vals, n_events=len(events) - (nf - nm))
    return [vname, group, len(events), nf, nm, rp.fmt(st.get("ge5"), 1), rp.fmt(st.get("ge10"), 1), rp.fmt(st.get("ge20"), 1),
            rp.fmt(st.get("max")), rp.fmt(st.get("worst")), rp.pct(st.get("win")), rp.fmt(st.get("mean"), 3),
            rp.fmt(st.get("median"), 3), rp.fmt(st.get("ge10_ev"), 1), rp.fmt(st.get("mean_ev"), 3)]


def date_matched(his_ev: list, ctl_ev: list, camps_h: dict, camps_c: dict, T: dict, key: str) -> dict:
    """His minus control, DATE-MATCHED (the first read's `paired_block_diff`, unchanged): per event the campaign R (a single trade
    when there is no chain), in the cell (date of the ORIGINAL event, first break / retrigger); weights = his filled mature campaigns'
    stratum shares; month blocks, 2,000 resamples, seed 702, `key`. Mean R, and >= 10R per 100 beside."""
    hv, hu, _nf, _nm = campaign_values(his_ev, camps_h, T)
    cv, cu, _nf2, _nm2 = campaign_values(ctl_ev, camps_c, T)
    nf = Counter(x.retrigger for x in hu)
    w = {s: nf[s] / len(hu) for s in (0, 1)} if hu else {0: 0.5, 1: 0.5}
    out = {}
    for meas, f in (("mean R", lambda r: r), (">=10R /100", lambda r: rp.PER * (r >= 10.0))):
        k = key if meas == "mean R" else key.replace("|mean R", "") + f"|{meas}"
        out[meas] = rp.paired_block_diff(
            f(np.array(hv, dtype=float)), [x.month for x in hu], [x.retrigger for x in hu],
            f(np.array(cv, dtype=float)), [x.month for x in cu], [x.retrigger for x in cu], w,
            a_date=[x.E for x in hu], b_date=[x.E for x in cu], key=k)
    return out


def fork_exec(yearly: dict, band_share: float) -> tuple:
    """The registered fork (era A, COMBINED at 1% risk and the 30% cap): his COMBINED curve returns >= +50% in BOTH 2020 and 2021
    AND at most 5% of the band's draws (the same-day registered draws, COMBINED applied to the control) end at or above his final
    equity -> "EXPLAINED"; otherwise -> "NEXT GAPS". A band share that is not a number is a refusal (raises), never a silent arm.
    -> (verdict, years_met, band_met, {year: return})."""
    if band_share is None or not math.isfinite(band_share):
        raise ValueError(f"the band's share at or above his final equity is not a number ({band_share}): the fork is unreadable")
    yrs = {y: yearly.get(y) for y in FORK_YEARS}
    years_met = all(v is not None and math.isfinite(v) and v >= FORK_RET for v in yrs.values())
    band_met = band_share <= BAND_SHARE_MAX
    return ("EXPLAINED" if (years_met and band_met) else "NEXT GAPS"), years_met, band_met, yrs


# the registration's §7 NEXT GAPS list, word for word (a test asserts it sits in the doc's §7 row and in FORK_TEXT)
NEXT_GAPS = ("stop placement beyond one ADR / the structural stop, adds / pyramiding, exit timing, market exposure, and the EPs and "
             "parabolic shorts in his record")
FORK_TEXT = {
    "EXPLAINED": "the execution gaps named here explain most of the shortfall: each one still has to be validated on calls not "
                 "used here (era B, the sealed 2025-26 table, new stream labels) before anything else is built on it",
    "NEXT GAPS": "the execution gaps named here do not explain the shortfall on their own: the next gaps to test are " + NEXT_GAPS
                 + " (his rule, 10-23: a replay that does not reproduce his years is a defect in our implementation, never 'the "
                 "setup does not work')",
}


# ═════════════════════════════════════════════════════════════════════════════════════════════
# the baseline-parity gate (real run): V0 must BE the first read
# ═════════════════════════════════════════════════════════════════════════════════════════════
def _close(a: float, b: float, rtol: float = 1e-9, atol: float = 1e-8) -> bool:
    return abs(a - b) <= atol + rtol * abs(b)


def parity_trades(first_trades_path: str, orig_keys: set, res: dict, T0: dict) -> list:
    """V0's ORH5 entries and p33_s3_t10 walks against the first read's `trades.tsv.gz` (written at 10 significant digits): the same
    event set, every entry status / reason, and for every fill the fill, stop, fill minute, status, maturity, sessions held and R.
    -> list of mismatch strings (empty = parity)."""
    t = pd.read_csv(first_trades_path, sep="\t", dtype=str, keep_default_na=False)
    t = t[(t["variant"] == rp.ENTRY) & ((t["arm"] == PRIMARY_ARM) | (t["entry_status"] != "filled"))]
    bad = []
    keys = set(zip(t["era"], t["ticker"], t["E"]))
    if keys != orig_keys:
        bad.append(f"event set differs: first read {len(keys)}, V0 {len(orig_keys)}, only-first {len(keys - orig_keys)}, "
                   f"only-V0 {len(orig_keys - keys)}")
    for r in t.itertuples(index=False):
        k = (r.era, r.ticker, r.E)
        if k not in res:
            continue
        en = res[k]["sets"]["orh5"]["entry"]
        if en["status"] != r.entry_status or (en["reason"] or "") != r.entry_reason:
            bad.append(f"{k}: entry {en['status']}:{en['reason']} vs {r.entry_status}:{r.entry_reason}")
            continue
        if r.entry_status != "filled":
            continue
        tr = T0.get(k)
        if tr is None:
            bad.append(f"{k}: filled in the first read, no V0 trade")
            continue
        for nm, mine, theirs in (("fill", tr.fill, float(r.fill)), ("stop", tr.stop, float(r.stop)),
                                 ("realized_r", tr.realized_r, float(r.realized_r))):
            if not _close(mine, theirs):
                bad.append(f"{k}: {nm} {mine!r} vs {theirs!r}")
        if (tr.fill_minute != int(r.fill_minute) or tr.status != r.status or int(tr.mature) != int(r.mature)
                or tr.sessions_held != int(r.sessions_held)):
            bad.append(f"{k}: fill minute / status / mature / held {tr.fill_minute}/{tr.status}/{int(tr.mature)}/{tr.sessions_held} "
                       f"vs {r.fill_minute}/{r.status}/{r.mature}/{r.sessions_held}")
    return bad


def parity_curve(first_account_his: str, config: str, sim: dict, cal: list) -> list:
    """V0 / V4's his-calls account curve against the first read's `account_his.tsv` (10 decimals) for the same config, day by day."""
    a = pd.read_csv(first_account_his, sep="\t", dtype={"config": str, "date": str})
    a = a[a["config"] == config]
    ci, eq = sim["curve"]
    mine = [(cal[c].isoformat(), float(v)) for c, v in zip(ci, eq)]
    theirs = list(zip(a["date"], a["equity"].astype(float)))
    if len(mine) != len(theirs):
        return [f"{config}: curve length {len(mine)} vs {len(theirs)}"]
    return [f"{config} {d}: {v!r} vs {w!r}" for (d, v), (d2, w) in zip(mine, theirs) if d != d2 or abs(v - w) > 1e-9][:10]


def parity_band(first_account_band: str, config: str, finals: list, his_final: float) -> list:
    """The band under V0 / V4 against the first read's `account_band.tsv` (the registered same-day band, this config, final equity):
    the five percentiles and the share at or above his final, to 1e-12."""
    b = pd.read_csv(first_account_band, sep="\t", dtype=str, keep_default_na=False)
    b = b[(b["band"] == rp.BAND_REGISTERED) & (b["config"] == config) & (b["measure"] == "final")]
    if len(b) != 1:
        return [f"{config}: {len(b)} first-read band rows"]
    r = b.iloc[0]
    bs = rp.band_summary(finals)
    share = sum(1 for v in finals if v >= his_final) / len(finals)
    bad = []
    for q in (5, 25, 50, 75, 95):
        if not _close(bs[q], float(r[f"p{q}"]), rtol=1e-12, atol=1e-12):
            bad.append(f"{config} band p{q}: {bs[q]!r} vs {r[f'p{q}']}")
    if not _close(share, float(r["share_ge_his"]), rtol=1e-12, atol=1e-12):
        bad.append(f"{config} band share: {share!r} vs {r['share_ge_his']}")
    return bad


RE_FIRST_REENTRY = re.compile(r"of (\d+) his-call trades stopped out, (\d+) have a later break of the same base after the exit day and "
                              r"within 20 sessions of E \((\d+) such breaks; (\d+) of them are themselves his calls\)")
RE_FIRST_DIFF = re.compile(r"^- mean R: DATE-MATCHED ([+-]\d+\.\d+) \[([+-]\d+\.\d+), ([+-]\d+\.\d+)\]", re.M)


def parse_first_printout(text: str) -> dict:
    """The first read's printed re-entry count and date-matched mean-R difference (the parity gate's two printed-only numbers)."""
    a, b = RE_FIRST_REENTRY.search(text), RE_FIRST_DIFF.search(text)
    if a is None or b is None:
        raise ValueError("the first read's printout carries no re-entry count or no date-matched line (refusal, never a PASS)")
    return {"reentry": tuple(int(x) for x in a.groups()), "diff": tuple(b.groups())}


# ═════════════════════════════════════════════════════════════════════════════════════════════
# main
# ═════════════════════════════════════════════════════════════════════════════════════════════
def check_superset(facts: Counter, expect: dict) -> list:
    return [f"{k}: {facts.get(k, 0)} (registered {v})" for k, v in expect.items() if facts.get(k, 0) != v]


def describe_superset(say, S: dict, X: dict, adr: dict, adr_bad: Counter) -> None:
    f = X["facts"]
    say("\n## The re-entry rows (V3's walk set; outcome-free: candidate keys, calendar, fetch logs, identity-break files, labels)")
    for e in ("A", "B"):
        say(f"- era {e}: later tl rows of a walked base within {REENTRY_WINDOW} sessions of its E: {f[f'{e}_reentry_rows']:,} "
            f"(already one of the first read's events {f[f'{e}_reentry_rows_already_events']:,}, of them excluded by its data rules "
            f"{f[f'{e}_reentry_rows_already_events_excluded']}); new rows {f[f'{e}_new_rows']:,}: minutes ok "
            f"{f[f'{e}_new_rows_minutes_ok']:,} / empty {f[f'{e}_new_rows_minutes_empty']} / MISSING {f[f'{e}_new_rows_minutes_missing']}, "
            f"identity break in (E - 130, E] {f[f'{e}_new_rows_break_pre']}, walk wiring fails "
            + (", ".join(f"{k.split('_excluded_')[1]} {v}" for k, v in sorted(f.items()) if k.startswith(f"{e}_new_rows_excluded_"))
               or "0")
            + f"; kept {f[f'{e}_new_rows_kept']:,}")
        # which groups' bases the rows serve (a row can serve several)
        walk_e = [x for x in X["walk"].values() if x.era == e and (x.his or x.ctl or x.post)]
        cal = S["Ds"][e].cal
        for nm in ("his", "ctl", "post"):
            grp = [x for x in walk_e if getattr(x, nm)]
            n_rows, n_ev = 0, 0
            for ev in grp:
                e_ci = bisect.bisect_left(cal, date.fromisoformat(ev.E))
                lim = cal[min(len(cal) - 1, e_ci + REENTRY_WINDOW)].isoformat()
                m = sum(1 for E2, _i in X["later"][e].get((ev.ticker, ev.base_id), []) if ev.E < E2 <= lim)
                n_rows += m
                n_ev += int(m > 0)
            say(f"    {nm}: {n_ev} of {len(grp)} events have at least one later row of their base in the window ({n_rows:,} rows, "
                f"counted per event)")
        if e == "A":
            his = [x for x in walk_e if x.his]
            ctl_lab = 0
            for ev in [x for x in walk_e if x.ctl]:
                e_ci = bisect.bisect_left(cal, date.fromisoformat(ev.E))
                lim = cal[min(len(cal) - 1, e_ci + REENTRY_WINDOW)].isoformat()
                ctl_lab += sum(1 for E2, _i in X["later"][e].get((ev.ticker, ev.base_id), [])
                               if ev.E < E2 <= lim and X["lab"][e].get((e, ev.ticker, E2), False))
            say(f"    control rows a control chain may never re-enter on (the round-3 rule on the row's own E): {ctl_lab:,}; "
                f"his-call bases: no label rule ({len(his)} events)")
        last = cal[-1]
        late = [x for x in X["walk"].values() if x.era == e
                and bisect.bisect_left(cal, date.fromisoformat(x.E)) + HORIZON + 1 > len(cal) - 1]
        say(f"- era {e}: walk-set events whose E + {HORIZON + 1} sessions run past the era's last session {last} (calendar only; "
            f"such a walk can end not mature): {len(late)}"
            + (f" ({', '.join(sorted({x.E for x in late})[:3])} .. {max(x.E for x in late)}; his-call / control originals among them "
               f"{sum(1 for x in late if x.his or x.ctl)})" if late else ""))
        dates_e = sorted({x.E for x in X["walk"].values() if x.era == e})
        orig = sorted({x.E for x in X["walk"].values() if x.era == e and (x.his or x.ctl or x.post)})
        say(f"- era {e}: minute date files the walk set opens {len(dates_e)} (the first read's {len(orig)} + {len(dates_e) - len(orig)} "
            f"for re-entry rows only)")
    say("\n## ADR20 at D — ours vs TC2000's (bars up to D only; outcome-free)")
    say(f"- our ADR20 recomputed from the 20 bars ending D equals the candidate's stored `adr20` (to {ADR_PARITY_TOL:g}): "
        + ", ".join(f"era {e} failures {adr_bad.get(e, 0)}" for e in ("A", "B")))
    for e in ("A", "B"):
        for nm in ("his", "ctl", "post", "reentry rows"):
            grp = [k for k, x in X["walk"].items() if x.era == e
                   and (getattr(x, nm) if nm != "reentry rows" else not (x.his or x.ctl or x.post))]
            if not grp:
                continue
            gap = np.array([100.0 * (adr[k][1] - adr[k][0]) for k in grp])
            ours = np.array([100.0 * adr[k][0] for k in grp])
            say(f"- era {e} {nm} (n = {len(grp):,}): our ADR20 median {np.median(ours):.2f}%; TC2000 minus ours, percentage points: "
                f"median {np.median(gap):.3f}, p90 {np.percentile(gap, 90):.3f}, max {gap.max():.3f}, min {gap.min():.3f} "
                f"(never negative: {bool((gap >= -1e-12).all())})")
    for e in ("A", "B"):
        big = adr_gap_events(S, X, adr, e)
        say(f"- era {e}: events where TC2000 minus ours exceeds {ADR_GAP_LIST_PP:g} points (the V2 / COMBINED too-wide gate is that "
            f"much looser than ours on them; listed, decides nothing; each with the window's widest bar, date and H / L - 1): "
            + "; ".join(f"{nm} {len(v)}" + (" (" + ", ".join(f"{tk} {E} {g:.1f} [{wd} {100 * wr:.0f}%]" for g, tk, E, wd, wr in v)
                                            + ")" if v else "")
                        for nm, v in big.items()))


def main(argv=None) -> int:
    ap_ = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap_.add_argument("--dry-run", action="store_true", help="load + populations + re-entry rows + ADR at D + coverage + pins; no outcome")
    args = ap_.parse_args(argv)
    dry = args.dry_run
    say = rp.Say()
    if not dry:
        ex = existing_outputs()
        if ex:
            print(f"REFUSED: output(s) already on disk: {ex} (this read runs once; after a STOPPED run, recovery = the fix, then delete "
                  f"the STOPPED file AND every file under {OUT_DIR} by hand, re-freeze if the module changed)", file=sys.stderr)
            return 2
    t0 = time.time()
    say(f"# #705 QM replay — 02_execution_variants ({'DRY RUN: no minute file opened, no entry / exit function called, no first-read outcome file read, no outcome computed' if dry else 'THE REGISTERED READ'})")
    say(f"# registration: {os.path.relpath(DOC, REPO)}")
    p0 = {k: rp.sha(v) for k, v in {**FILES, **CODE}.items() if k in PINNED}
    drift = [f"{k}: {p0[k]} (pinned {v})" for k, v in PINNED.items() if p0.get(k) != v]
    fdb = rp.doc_body_sha(rp.DOC) if os.path.exists(rp.DOC) else ""
    if fdb != FIRST_DOC_BODY:
        drift.append(f"first_doc_body: {fdb} (frozen {FIRST_DOC_BODY})")
    missing_first = [k for k, v in FIRST.items() if not os.path.exists(v)]
    if drift or missing_first:
        say("REFUSED: " + ("a pinned input changed: " + "; ".join(drift) if drift else "")
            + (f" the first read's outputs are missing: {missing_first}" if missing_first else ""))
        say.write(DRY_PRINTOUT if dry else STOPPED)
        return 2
    say("- pins re-checked: the Track A inputs, the cb module, the frozen first replay (module c4478588…, tests 37c918a0…, doc body "
        "aaaadd29…): no drift; the first read's outputs are on disk (hashed below, not parsed)")
    say("\n## Loads (the first read's loader; era B: every row dated after 2024-12-31 dropped at read)")
    S = rp.load_all(say, dry)
    done = {"A": rp.load_done(rp.FILES["done_A"])[0], "B": rp.load_done(rp.FILES["done_B"], cut=CUT_B)[0]}
    rp.describe_population(say, S)
    X = prepare(S, done)
    adr, adr_bad = adr_facts(S, X)
    describe_superset(say, S, X, adr, adr_bad)
    bad = check_superset(X["facts"], EXPECT_SUPERSET)
    if bad:
        raise AssertionError("RE-ENTRY ROWS ASSERT FAILED: " + "; ".join(bad))
    if sum(adr_bad.values()):
        raise AssertionError(f"our ADR20 at D does not reproduce the stored adr20 on {dict(adr_bad)} events: the ADR window is wrong")
    say(f"- the re-entry rows equal the registration ({len(EXPECT_SUPERSET)} counts asserted)")
    mdates = {e: sorted({x.E for x in X["walk"].values() if x.era == e}) for e in ("A", "B")}
    p = pins(mdates)
    say("\n## Pins (sha256) — every value below goes under the doc's freeze marker line before the real run")
    for k, v in p.items():
        what = FILES.get(k) or CODE.get(k) or {"first_doc_body": "the first registration's text above its marker (frozen)",
                                               "doc_body": "this registration's text above its marker line"}.get(k) \
            or f"the {len(mdates[k[8]])} minute date files the walk set opens"
        say(f"- {k}: {v}  {what}")
    miss = freeze_missing(DOC, p)
    say(f"- freeze record: {'every pin above is written under the freeze marker line' if not miss else 'NOT YET under the freeze marker line: ' + ', '.join(miss)}")
    if dry:
        say(f"\n## DRY RUN ends here: no minute file opened, no entry / exit / R / return computed, no first-read outcome read. "
            f"({time.time() - t0:.0f}s)")
        say.write(DRY_PRINTOUT)
        return 0
    if miss:
        say("REFUSED: the real read runs only after the freeze commit records every pin above under the marker line.")
        print("\n".join(say.lines[-2:]), file=sys.stderr)
        return 2
    try:
        run_exec(S, X, adr, say)
    except GuardStop as g:
        say(f"\nSTOPPED: {g} ({time.time() - t0:.0f}s)")
        say.write(STOPPED)
        return 3
    except Exception:
        import traceback
        say("\nCRASHED:\n" + traceback.format_exc())
        say.write(STOPPED)
        return 3
    say(f"\n({time.time() - t0:.0f}s)")
    say.write(PRINTOUT)
    return 0


# ═════════════════════════════════════════════════════════════════════════════════════════════
# the real run (after the freeze only)
# ═════════════════════════════════════════════════════════════════════════════════════════════
def compute(S: dict, X: dict, res: dict) -> dict:
    """Every number of the read, computed before anything is printed (the parity gate runs on it first)."""
    TT = {s: trades_for_set(X, res, s) for s in ENTRY_SETS}
    groups = {}
    for e in ("A", "B"):
        evs = [x for x in S["evs"] if x.era == e and x.keep]
        groups[e] = {"his": [x for x in evs if x.his], "ctl": [x for x in evs if x.ctl], "post": [x for x in evs if x.post]}
    C = {"TT": TT, "groups": groups, "camps": {}, "chain_counts": {}}
    for e in ("A", "B"):
        cal = S["Ds"][e].cal
        for v in VARIANTS:
            for g, control_rule in (("his", False), ("ctl", True), ("post", False)):
                key = (e, v.name, g)
                src = SAME_TRADES.get(v.name)
                if src is not None:                                     # a sizing-only variant: the source variant's trades
                    C["camps"][key], C["chain_counts"][key] = C["camps"][(e, src, g)], Counter()
                    continue
                C["camps"][key], C["chain_counts"][key] = campaigns(groups[e][g], TT[v.entry], X, cal, v.chain, control_rule)
    return C


def run_exec(S: dict, X: dict, adr: dict, say) -> None:
    os.makedirs(OUT_DIR, exist_ok=True)
    res, tally = walk_all2(S, X, adr)
    C = compute(S, X, res)
    TT, groups, camps = C["TT"], C["groups"], C["camps"]
    calA = S["Ds"]["A"].cal
    GA = groups["A"]
    startA = bisect.bisect_left(calA, date.fromisoformat(min(x.E for x in GA["his"] + GA["ctl"])))
    orig_keys = {(x.era, x.ticker, x.E) for e in ("A", "B") for g in ("his", "ctl", "post") for x in groups[e][g]}

    # ---- G8 on the union of every trade of this read, BEFORE any number
    g8 = {}
    for e in ("A", "B"):
        rows, seen = [], set()
        for s in ENTRY_SETS:
            for k, t in sorted(TT[s].items()):
                if k[0] == e and (k[1], k[2], t.sessions_held) not in seen:    # G8's two counts read only (ticker, E, hold)
                    seen.add((k[1], k[2], t.sessions_held))
                    rows.append((PRIMARY_ARM, k[1], k[2], t.sessions_held, t.realized_r))
        path = os.path.join(OUT_DIR, f"g8_{e}.tsv")
        rp.write_g8_file(path, rows)
        g8[e] = rp.run_g8(e, path, os.path.join(OUT_DIR, f"g8_{e}_impact.txt"))
    if g8["A"] != (0, 0):
        raise GuardStop(f"G8 era A {g8['A']} != (0, 0): the read does not quote a number")

    # ---- accounts and bands (computed before printing; the parity gate reads V0 / V4)
    sims, band = {}, {}
    his_by_date = Counter(x.E for x in GA["his"])
    ctl_by_date = defaultdict(list)
    for x in GA["ctl"]:
        ctl_by_date[x.E].append((x.era, x.ticker, x.E))
    rng = np.random.default_rng([SEED, zlib.crc32(BAND_KEY.encode())])
    draws = [rp.sample_control(his_by_date, ctl_by_date, rng)[0] for _ in range(BAND_DRAWS)]
    for v in VARIANTS:
        T = TT[v.entry]
        tr = union_trades(camps[("A", v.name, "his")], [(x.era, x.ticker, x.E) for x in GA["his"]], T)
        sims[v.name] = rp.simulate(tr, v.cfg, calA, startA)
        cc = camps[("A", v.name, "ctl")]
        band[v.name] = [rp.simulate(union_trades(cc, ids, T), v.cfg, calA, startA) for ids in draws]

    # ---- THE BASELINE-PARITY GATE: V0 (and V4 = the first read's cap_30) must BE the first read
    bad = parity_trades(FIRST["first_trades"], orig_keys, res, TT["orh5"])
    bad += parity_curve(FIRST["first_account_his"], rp.PRIMARY_CONFIG.name, sims["V0"], calA)
    bad += parity_curve(FIRST["first_account_his"], CAP30.name, sims["V4"], calA)
    bad += parity_band(FIRST["first_account_band"], rp.PRIMARY_CONFIG.name, [s["final"] for s in band["V0"]], sims["V0"]["final"])
    bad += parity_band(FIRST["first_account_band"], CAP30.name, [s["final"] for s in band["V4"]], sims["V4"]["final"])
    with open(FIRST["first_printout"]) as fh:
        fp = parse_first_printout(fh.read())
    rc = reentry_count_01(GA["his"], TT["orh5"], X, calA)
    if rc != fp["reentry"]:
        bad.append(f"re-entry count {rc} vs the first read's {fp['reentry']}")
    d0 = date_matched(GA["his"], GA["ctl"], camps[("A", "V0", "his")], camps[("A", "V0", "ctl")], TT["orh5"], FIRST_DIFF_KEY)["mean R"]
    if tuple(f"{x:+.3f}" for x in (d0["matched"], d0["m_lo"], d0["m_hi"])) != fp["diff"]:
        bad.append(f"date-matched {d0['matched']:+.3f} [{d0['m_lo']:+.3f}, {d0['m_hi']:+.3f}] vs the first read's {fp['diff']}")
    adr_bad = [k for k in res if abs(adr[k][0] - X["walk"][k].adr20) > ADR_PARITY_TOL]
    if adr_bad:
        bad.append(f"our ADR20 at D != stored on {len(adr_bad)} events")
    mono = [k for k in res for a, b in (("orh5", "orh5_tc"), ("level", "level_tc"))
            if res[k]["sets"][a]["raw"] is not None and (res[k]["sets"][b]["raw"] is None
                                                       or res[k]["sets"][b]["entry"]["fill"] != res[k]["sets"][a]["entry"]["fill"]
                                                       or res[k]["sets"][b]["entry"]["stop"] != res[k]["sets"][a]["entry"]["stop"])]
    if mono:
        bad.append(f"a fill under our ADR is not the same fill under TC2000's on {len(mono)} walks (V2 must only ADD fills)")
    if bad:
        raise GuardStop("BASELINE PARITY FAILED (V0 is not the first read; no variant number is printed): " + " | ".join(bad[:20]))

    say("\n## The walk")
    say("- " + ", ".join(f"{k} {v:,}" for k, v in sorted(tally.items())))
    say(f"\n## G8 — trade_impact.py on the union of every trade of this read (every entry set, re-entries included, each written as "
        f"its own trade from its own E), run BEFORE any number below")
    say(f"- era A: entered after the cutoff {g8['A'][0]}, holds past the last bar kept {g8['A'][1]} (registered: both 0, asserted)")
    say(f"- era B: entered after the cutoff {g8['B'][0]}, holds past the last bar kept {g8['B'][1]} (censored: a walk not mature is in no number)")
    say("\n## BASELINE PARITY — V0 re-walked equals the first read (asserted before any variant number)")
    say(f"- trades: every ORH5 entry and p33_s3_t10 walk of the {len(orig_keys):,} events equal `trades.tsv.gz`; his account curve "
        f"(primary {sims['V0']['final']:.3f}, cap_30 = V4 {sims['V4']['final']:.3f}) equal `account_his.tsv` day by day; the band's "
        f"five percentiles and share equal `account_band.tsv` (primary and cap_30); re-entry count {rc}; date-matched mean R "
        f"{d0['matched']:+.3f} [{d0['m_lo']:+.3f}, {d0['m_hi']:+.3f}]; our ADR20 at D = the stored one on every walked event; every "
        f"fill under our ADR is the same fill under TC2000's")

    # ---- the minute-0 stop convention (§1.4b), counted once per era and printed beside every V1 / COMBINED table (decides nothing)
    OL = {e: own_low_line(res, groups[e], e, camps) for e in ("A", "B")}

    # ---- entry facts per entry set
    say("\n## Entry facts per entry set (era A)")
    for s in ENTRY_SETS:
        for nm in ("his", "ctl", "post"):
            st = Counter(res[k]["sets"][s]["entry"]["status"] + ":" + (res[k]["sets"][s]["entry"]["reason"] or "")
                         for k in ((x.era, x.ticker, x.E) for x in GA[nm]) if k in res)
            capped = sum(1 for x in GA[nm] if res[(x.era, x.ticker, x.E)]["sets"][s]["capped"])
            late = sum(1 for x in GA[nm] if x.early_close and res[(x.era, x.ticker, x.E)]["sets"][s]["raw"] is not None
                       and res[(x.era, x.ticker, x.E)]["sets"][s]["entry"]["fill_minute"] >= rp.EARLY_CUT)
            say(f"- {s} {nm}: " + ", ".join(f"{k} {v}" for k, v in sorted(st.items()))
                + (f" | too-wide kept with a one-ADR stop {capped}" if ENTRY_SETS[s].wide == "cap" else "")
                + f" | fills after 13:00 on a 13:00-close day {late}")
    for s in ("level", "level_tc"):
        for nm in ("his", "ctl"):
            fl = [res[(x.era, x.ticker, x.E)]["sets"][s]["entry"] for x in GA[nm] if res[(x.era, x.ticker, x.E)]["sets"][s]["raw"] is not None]
            at_open = sum(1 for en in fl if en["fill"] != en["level"] * (1.0 + cb.ENTRY_SLIPPAGE_PCT))
            w = np.array([en["width_pct"] for en in fl]) if fl else np.array([np.nan])
            d0n = sum(1 for en in fl if en["day0"]["stopped"])
            ad = [x.adr20 for x in GA[nm] if res[(x.era, x.ticker, x.E)]["sets"][s]["raw"] is not None]
            n_floor = sum(1 for en, a in zip(fl, ad) if en["width_pct"] < WIDTH_FLOOR_ADR * a)
            n_tiny = sum(1 for en in fl if en["width_pct"] < TINY_WIDTH)
            say(f"- {s} {nm}: fills {len(fl)}: at the minute's open (it opened above the level) {at_open}, at the level "
                f"{len(fl) - at_open}; stop width median {100 * np.nanmedian(w):.2f}% of the fill, 10th pct "
                f"{100 * np.nanpercentile(w, 10):.2f}%; under {WIDTH_FLOOR_ADR:g} x our ADR20 {n_floor}, under "
                f"{100 * TINY_WIDTH:.1f}% of the fill {n_tiny}; stopped on day 0 {d0n}")
    say(OL["A"])
    for s in ("orh5",):
        for nm in ("his", "ctl"):
            fl = [(res[(x.era, x.ticker, x.E)]["sets"][s]["entry"], x.adr20) for x in GA[nm]
                  if res[(x.era, x.ticker, x.E)]["sets"][s]["raw"] is not None]
            say(f"- {s} {nm} (V0, for scale): fills {len(fl)}; stop width under {WIDTH_FLOOR_ADR:g} x our ADR20 "
                f"{sum(1 for en, a in fl if en['width_pct'] < WIDTH_FLOOR_ADR * a)}, under {100 * TINY_WIDTH:.1f}% of the fill "
                f"{sum(1 for en, a in fl if en['width_pct'] < TINY_WIDTH)}")
    w0 = [x for x in GA["his"] if res[(x.era, x.ticker, x.E)]["sets"]["orh5"]["raw"] is None]
    say(f"- his calls NOT filled under the first read's ORH5 ({len(w0)}), and what each entry set does with them:")
    for x in sorted(w0, key=lambda z: (z.E, z.ticker)):
        cells = []
        for s in ENTRY_SETS:
            en = res[(x.era, x.ticker, x.E)]["sets"][s]["entry"]
            cells.append(f"{s} {en['status'] if en['status'] == 'filled' else (en['reason'] or en['status'])}"
                         + (f" {100 * en['width_pct']:.1f}%" if en.get("width_pct") is not None else ""))
        say(f"    {x.ticker} {x.E} (our ADR {100 * x.adr20:.2f}%, TC2000 {100 * adr[(x.era, x.ticker, x.E)][1]:.2f}%): " + "; ".join(cells))

    # ---- chain facts
    say("\n## V3 re-entry chains (era A)")
    for vn in ("V3", "COMBINED"):
        for g in ("his", "ctl"):
            cc = camps[("A", vn, g)]
            n_re = Counter(len(ch) - 1 for ch in cc.values() if ch)
            orig = {(x.era, x.ticker, x.E) for x in GA[g]}
            re_keys = {k for ch in cc.values() for k in ch[1:]}
            say(f"- {vn} {g}: campaigns with 0 / 1 / 2 re-entries {n_re.get(0, 0)} / {n_re.get(1, 0)} / {n_re.get(2, 0)}; re-entry trades "
                f"{len(re_keys)} (of them already one of this group's events, entered once {len(re_keys & orig)}); "
                + ", ".join(f"{k} {v}" for k, v in sorted(C["chain_counts"][("A", vn, g)].items())))

    # ---- per-trade tables, tail first
    say("\n## HEADLINE — per trade R, tail first (era A; exit p33_s3_t10; mature trades; exit slippage 0). A chain variant's trades = "
        "every trade of every campaign, each (ticker, E) once; events n = his calls / control events + the re-entry trades taken")
    rows = []
    for v in VARIANTS:
        if v.name not in TRADE_VARIANTS:
            continue
        T = TT[v.entry]
        for g, lab_ in (("his", "his calls"), ("ctl", "control (same day)")):
            keys = [(x.era, x.ticker, x.E) for x in GA[g]]
            tr = union_trades(camps[("A", v.name, g)], keys, T)
            n_extra = len({t.key for t in tr} - set(keys))
            rows.append(trade_row(v.name, lab_, len(keys) + n_extra, tr))
    for ln in rp.table(STAT_HDR, rows):
        say(ln)
    say("- V4 / V4b change only the sizing: their per-trade numbers are V0's")
    say(OL["A"])
    say(f"\n### beside — the same table over trades whose stop is at least {WIDTH_FLOOR_ADR:g} x our ADR20 wide (a near-zero stop "
        f"makes R a unit artifact; under V1 / COMBINED the per-trade R is NOT in V0's unit, the account and the band are the comparable "
        f"numbers)")
    rows = []
    for v in VARIANTS:
        if v.name not in TRADE_VARIANTS:
            continue
        for g, lab_ in (("his", "his calls"), ("ctl", "control (same day)")):
            keys = [(x.era, x.ticker, x.E) for x in GA[g]]
            tr = union_trades(camps[("A", v.name, g)], keys, TT[v.entry])
            fl = [t for t in tr if floor_ok(t, X["walk"])]
            rows.append(trade_row(v.name, lab_ + f" (stop >= {WIDTH_FLOOR_ADR:g} ADR)", len(fl), fl))
    for ln in rp.table(STAT_HDR, rows):
        say(ln)
    say(OL["A"])
    for v in VARIANTS:
        if v.name not in TRADE_VARIANTS:
            continue
        parts = []
        for g in ("his", "ctl"):
            keys = [(x.era, x.ticker, x.E) for x in GA[g]]
            op = [t for t in union_trades(camps[("A", v.name, g)], keys, TT[v.entry]) if not t.mature]
            parts.append(f"{g} {len(op)} (degraded {sum(1 for t in op if t.status == 'degraded')}; summed booked R "
                         f"{sum(t.realized_r for t in op):+.2f})")
        say(f"- {v.name}: trades NOT mature (the bars ended inside the horizon: booked in the account at their last close, in no "
            f"per-trade number): " + "; ".join(parts))
    for si, s in enumerate(EXIT_SLIPS[1:], start=1):
        parts = []
        for v in VARIANTS:
            if v.name not in TRADE_VARIANTS:
                continue
            for g in ("his", "ctl"):
                keys = [(x.era, x.ticker, x.E) for x in GA[g]]
                r = trade_row(v.name, g, len(keys), union_trades(camps[("A", v.name, g)], keys, TT[v.entry]), si)
                parts.append(f"{v.name} {g} {r[11]}")
        say(f"- exit slippage {100 * s:.1f}% per leg, mean R: " + "; ".join(parts))
    say("\n### per EVENT (campaign R = the sum of a call's trades: the call plus its re-entries), chain variants beside V0")
    rows = []
    for vn in ("V0", "V3", "COMBINED"):
        v = VMAP[vn]
        for g, lab_ in (("his", "his calls"), ("ctl", "control (same day)")):
            rows.append(campaign_row(vn, lab_, GA[g], camps[("A", vn, g)], TT[v.entry]))
    for ln in rp.table(STAT_HDR, rows):
        say(ln)
    say(OL["A"])
    say("\n### beside — COMBINED on the splits (per trade)")
    rows = []
    v = VMAP["COMBINED"]
    T = TT[v.entry]
    splits = [("his first breaks", [x for x in GA["his"] if x.retrigger == 0], "his"),
              ("his retriggers", [x for x in GA["his"] if x.retrigger == 1], "his"),
              ("his strictly-before", [x for x in GA["his"] if x.strict], "his"),
              ("his one event per base", [x for x in GA["his"] if x.first_of_base], "his"),
              ("control first breaks", [x for x in GA["ctl"] if x.retrigger == 0], "ctl"),
              ("control retriggers", [x for x in GA["ctl"] if x.retrigger == 1], "ctl"),
              ("post-E-only (hindsight)", GA["post"], "post")]
    splits += [(f"{nm} QQQ {q} at D", [x for x in GA[g] if x.qqq == q], g)
               for g, nm in (("his", "his"), ("ctl", "control")) for q in ("up", "mixed", "down")]
    for lab_, evs_, g in splits:
        keys = [(x.era, x.ticker, x.E) for x in evs_]
        tr = union_trades(camps[("A", "COMBINED", g)], keys, T)
        rows.append(trade_row("COMBINED", lab_, len(keys) + len({t.key for t in tr} - set(keys)), tr))
    for ln in rp.table(STAT_HDR, rows):
        say(ln)
    say(OL["A"])

    # ---- by year
    say("\n## By year of the trade's E (era A; per trade: n mature / mean R / >=10R per 100)")
    by_v = {}
    for v in VARIANTS:
        if v.name not in TRADE_VARIANTS:
            continue
        for g in ("his", "ctl"):
            keys = [(x.era, x.ticker, x.E) for x in GA[g]]
            by_v[(v.name, g)] = [t for t in union_trades(camps[("A", v.name, g)], keys, TT[v.entry]) if t.mature]
    yrs = sorted({t.year for tr in by_v.values() for t in tr})
    rows = []
    for v in VARIANTS:
        if v.name not in TRADE_VARIANTS:
            continue
        for g in ("his", "ctl"):
            tr = by_v[(v.name, g)]
            cells = []
            for y in yrs:
                r = np.array([t.realized_r for t in tr if t.year == y])
                cells.append(f"{len(r)} / {r.mean():+.3f} / {100 * (r >= 10).mean():.1f}" if len(r) else "-")
            rows.append([v.name, g] + cells)
    for ln in rp.table(["variant", "group"] + [str(y) for y in yrs], rows):
        say(ln)
    say(OL["A"])

    # ---- date-matched differences
    say("\n## HIS minus CONTROL, DATE-MATCHED (era A; per event: the campaign R in the cell (date of the call, first break / retrigger); "
        "month-block, 2,000 resamples, seed 702; V0 uses the first read's key and reproduces it)")
    diffs = {}
    for v in VARIANTS:
        if v.name not in TRADE_VARIANTS:
            continue
        key = FIRST_DIFF_KEY if v.name == "V0" else f"qm_exec|A|{v.name}|mean R"
        d = date_matched(GA["his"], GA["ctl"], camps[("A", v.name, "his")], camps[("A", v.name, "ctl")], TT[v.entry], key)
        diffs[v.name] = d
        a, b = d["mean R"], d[">=10R /100"]
        say(f"- {v.name}: mean R {a['matched']:+.3f} [{a['m_lo']:+.3f}, {a['m_hi']:+.3f}]; >=10R per 100 {b['matched']:+.2f} "
            f"[{b['m_lo']:+.2f}, {b['m_hi']:+.2f}] | cells uncovered {a['cells_uncovered']} ({a['his_uncovered']} of his), "
            f"resamples dropped {a['dropped_m']}")
    say(OL["A"])

    # ---- the account
    say("\n## ACCOUNT CURVE — his calls, chronological (era A; start 1.0; no margin; 30% per stock at cost)")
    hdr = ["variant", "risk", "cap"] + [f"{y} return" for y in rp.FORK_YEARS] + ["2022 (exits only)", "final equity", "max drawdown",
                                                                                 "trades offered", "of them re-entries", "entered",
                                                                                 "skipped no room", "skipped stock limit",
                                                                                 "trimmed to the stock limit", "cap bound", "max open",
                                                                                 "max gross"]
    rows = []
    for v in VARIANTS:
        sim = sims[v.name]
        keys = [(x.era, x.ticker, x.E) for x in GA["his"]]
        tr = union_trades(camps[("A", v.name, "his")], keys, TT[v.entry])
        n_re = len({t.key for t in tr} - set(keys))
        c = sim["counts"]
        rows.append([v.name + (" (beside)" if v.beside else ""), v.cfg.risk, v.cfg.cap] + [rp.pct(sim["yearly"].get(y)) for y in rp.FORK_YEARS]
                    + [rp.pct(sim["yearly"].get(2022)), f"{sim['final']:.3f}", rp.pct(sim["max_dd"]), len(tr), n_re, c["entered"],
                       c["skipped_no_room"], c["skipped_stock_limit"], c["stock_limit_trimmed"], c["cap_bound"], sim["max_open"],
                       rp.pct(sim["max_gross"])])
    for ln in rp.table(hdr, rows):
        say(ln)
    say(OL["A"])
    for v in VARIANTS:
        sim = sims[v.name]
        say(f"- {v.name}: year-end equity " + ", ".join(f"{y} {q:.3f}" for y, q in sorted(sim["year_end"].items()))
            + "; entered per year " + ", ".join(f"{y} {n}" for y, n in sorted(sim["entered_by_year"].items()))
            + "; skipped per year " + ", ".join(f"{y} {n}" for y, n in sorted(sim["skipped_by_year"].items())))

    # ---- the band
    say(f"\n## CONTROL BAND — the first read's {BAND_DRAWS} same-day draws (seed {SEED}, key `{BAND_KEY}`), each drawn control event "
        f"mapped to its trades under the variant (its campaign under V3 / COMBINED, each (ticker, E) once per draw)")
    rows, band_out, shares = [], [], {}
    for v in VARIANTS:
        bs_sims = band[v.name]
        hs = sims[v.name]
        for y in FORK_YEARS + ("final", "max_dd"):
            vals = [s["yearly"].get(y) for s in bs_sims] if isinstance(y, int) else [s[y] for s in bs_sims]
            hv = hs["yearly"].get(y) if isinstance(y, int) else hs[y]
            bsum = rp.band_summary(vals)
            share = (sum(1 for q in vals if q is not None and hv is not None and q >= hv) / len(vals)) if (hv is not None and vals) else float("nan")
            shares[(v.name, y)] = share
            band_out.append((v.name, y, bsum, hv, share))
            rows.append([v.name, {"final": "final equity", "max_dd": "max drawdown (higher = WORSE)"}.get(y, f"{y} return"),
                         rp.fmt(hv, 3), rp.fmt(bsum.get(5), 3), rp.fmt(bsum.get(50), 3), rp.fmt(bsum.get(95), 3), rp.pct(share)])
    for ln in rp.table(["variant", "year / measure", "his calls", "control 5th pct", "control median", "control 95th pct",
                        "share of draws >= his (for max drawdown: as deep or DEEPER, i.e. worse)"], rows):
        say(ln)
    say(OL["A"])

    # ---- the fork
    fv = VMAP[FORK_VARIANT]
    verdict, years_met, band_met, yrs = fork_exec(sims[FORK_VARIANT]["yearly"], shares[(FORK_VARIANT, "final")])
    say(f"\n## THE FORK (registered before any outcome; era A, COMBINED = V1 + V2 + V3 + V4 at {100 * fv.cfg.risk:.0f}% risk and the "
        f"{100 * fv.cfg.cap:.0f}% cap, applied to his calls and to the control)")
    say(f"- yearly return >= +{100 * FORK_RET:.0f}% in BOTH 2020 and 2021: " + ", ".join(f"{y} {rp.pct(r)}" for y, r in yrs.items())
        + f" -> {'MET' if years_met else 'not met'}")
    say(f"- the same-day band at or above his final equity ({sims[FORK_VARIANT]['final']:.3f}) in {rp.pct(shares[(FORK_VARIANT, 'final')])} "
        f"of {BAND_DRAWS} draws (needs <= {rp.pct(BAND_SHARE_MAX, 0)}) -> {'MET' if band_met else 'not met'}")
    say(f"- VERDICT: **{verdict}** — {FORK_TEXT[verdict]}")
    say("- read with it: every variant here was chosen AFTER the first read's fills were seen (the 42 unfilled, the 20 too wide, the "
        "re-entry count, the 30%-cap row); a variant that helps must still be validated on calls not used here")

    # ---- beside: the strictly-before calls under COMBINED
    strict = [x for x in GA["his"] if x.strict]
    T = TT[fv.entry]
    st_sim = rp.simulate(union_trades(camps[("A", FORK_VARIANT, "his")], [(x.era, x.ticker, x.E) for x in strict], T), fv.cfg, calA, startA)
    rng = np.random.default_rng([SEED, zlib.crc32(STRICT_BAND_KEY.encode())])
    st_draws = [rp.sample_control(Counter(x.E for x in strict), ctl_by_date, rng)[0] for _ in range(BAND_DRAWS)]
    st_fin = [rp.simulate(union_trades(camps[("A", FORK_VARIANT, "ctl")], ids, T), fv.cfg, calA, startA)["final"] for ids in st_draws]
    st_share = sum(1 for q in st_fin if q >= st_sim["final"]) / len(st_fin) if st_fin else float("nan")
    say(f"- BESIDE (decides nothing): COMBINED on the {len(strict)} strictly-before calls (clean of E's bar): yearly "
        + ", ".join(f"{y} {rp.pct(q)}" for y, q in sorted(st_sim["yearly"].items()) if y in rp.FORK_YEARS)
        + f", final {st_sim['final']:.3f}; their own same-day band (the first read's strictly-before draws) at or above it in "
          f"{rp.pct(st_share)}")

    # ---- beside: COMBINED with every fill on the day's first minute bar dropped, his calls AND the control (§1.4b's minute-0 stop
    # convention made visible on the fork variant; decides nothing — the fork above is the registered one)
    T_m0 = without_first_bar(T, res, fv.entry)
    his_keys = [(x.era, x.ticker, x.E) for x in GA["his"]]
    reg_h = union_trades(camps[("A", FORK_VARIANT, "his")], his_keys, T)
    reg_c = union_trades(camps[("A", FORK_VARIANT, "ctl")], [(x.era, x.ticker, x.E) for x in GA["ctl"]], T)
    ch_h, _cnt_h = campaigns(GA["his"], T_m0, X, calA, fv.chain, False)            # the chains re-resolve: a dropped row is passed
    ch_c, _cnt_c = campaigns(GA["ctl"], T_m0, X, calA, fv.chain, True)
    m0_sim = rp.simulate(union_trades(ch_h, his_keys, T_m0), fv.cfg, calA, startA)
    m0_fin = [rp.simulate(union_trades(ch_c, ids, T_m0), fv.cfg, calA, startA)["final"] for ids in draws]
    m0_share = sum(1 for q in m0_fin if q >= m0_sim["final"]) / len(m0_fin) if m0_fin else float("nan")
    say(f"- BESIDE (decides nothing; the fork above is unchanged): COMBINED with every fill in minute 0 (the day's first minute bar) "
        f"DROPPED from his calls and the control alike (treated as not filled: a chain passes that row, an origin so filled has no "
        f"campaign), so the minute-0 stop convention's effect on the fork variant shows: of the registered COMBINED trades, his "
        f"{sum(1 for t in reg_h if t.key not in T_m0)} of {len(reg_h)} and the control's {sum(1 for t in reg_c if t.key not in T_m0)} "
        f"of {len(reg_c)} fill in minute 0; his curve yearly "
        + ", ".join(f"{y} {rp.pct(m0_sim['yearly'].get(y))}" for y in FORK_YEARS)
        + f", final {m0_sim['final']:.3f}, max drawdown {rp.pct(m0_sim['max_dd'])} (registered COMBINED: "
        + ", ".join(f"{y} {rp.pct(sims[FORK_VARIANT]['yearly'].get(y))}" for y in FORK_YEARS)
        + f", final {sims[FORK_VARIANT]['final']:.3f}); the same {BAND_DRAWS} same-day draws at or above his final in "
          f"{rp.pct(m0_share)} (registered {rp.pct(shares[(FORK_VARIANT, 'final')])})")

    # ---- era B, descriptive
    GB = groups["B"]
    calB = S["Ds"]["B"].cal
    say("\n## Era B (descriptive; 9 calls, 345 control events)")
    rows = []
    for v in VARIANTS:
        if v.name not in TRADE_VARIANTS:
            continue
        for g in ("his", "ctl"):
            keys = [(x.era, x.ticker, x.E) for x in GB[g]]
            tr = union_trades(camps[("B", v.name, g)], keys, TT[v.entry])
            rows.append(trade_row(v.name, g, len(keys) + len({t.key for t in tr} - set(keys)), tr))
    for ln in rp.table(STAT_HDR, rows):
        say(ln)
    say(OL["B"])
    for v in VARIANTS:
        keys = [(x.era, x.ticker, x.E) for x in GB["his"]]
        tr = union_trades(camps[("B", v.name, "his")], keys, TT[v.entry])
        if tr:
            sB = rp.simulate(tr, v.cfg, calB, min(t.e_ci for t in tr))
            say(f"- era B his {v.name}: {len(tr)} trades, yearly " + ", ".join(f"{y} {rp.pct(q)}" for y, q in sorted(sB["yearly"].items()))
                + f", final {sB['final']:.3f}, max drawdown {rp.pct(sB['max_dd'])}")

    # ---- outputs
    write_outputs(S, X, res, C, sims, band_out, adr)


def write_outputs(S: dict, X: dict, res: dict, C: dict, sims: dict, band_out: list, adr: dict) -> None:
    TT = C["TT"]
    cols = ["era", "ticker", "D", "E", "base_id", "retrigger", "is_his", "is_ctl", "is_post", "is_strict", "reentry_row_only", "adr20",
            "adr20_tc2000", "entry_set", "entry_status", "entry_reason", "capped", "fill", "stop", "fill_minute", "width_pct", "status",
            "mature", "sessions_held", "realized_r", "r_exit_slip_0.1", "r_exit_slip_0.2", "legs"]
    with gzip.open(os.path.join(OUT_DIR, "trades.tsv.gz"), "wt") as fh:
        fh.write("\t".join(cols) + "\n")
        for k, w in sorted(res.items()):
            ev = X["walk"][k]
            for s in ENTRY_SETS:
                en = w["sets"][s]["entry"]
                base = [ev.era, ev.ticker, ev.D, ev.E, ev.base_id, ev.retrigger, int(ev.his), int(ev.ctl), int(ev.post), int(ev.strict),
                        int(not (ev.his or ev.ctl or ev.post)), ev.adr20, adr[k][1], s, en["status"], en["reason"] or "",
                        int(w["sets"][s]["capped"]), en.get("fill"), en.get("stop"), en.get("fill_minute"), en.get("width_pct")]
                t = TT[s].get(k)
                if t is None:
                    row = base + [""] * 7
                else:
                    legs = ";".join(f"{lg[5]}:{lg[4]}:{lg[2]:.6f}:{lg[3]:.6f}" for lg in t.legs)
                    row = base + [t.status, int(t.mature), t.sessions_held, t.realized_r, t.r_slip[1], t.r_slip[2], legs]
                fh.write("\t".join("" if x is None else (f"{x:.10g}" if isinstance(x, float) else str(x)) for x in row) + "\n")
    with open(os.path.join(OUT_DIR, "chains.tsv"), "w") as fh:
        fh.write("era\tvariant\tgroup\torigin_ticker\torigin_E\tn_trades\ttrade_Es\n")
        for (e, vn, g), cc in sorted(C["camps"].items()):
            if not VMAP[vn].chain or vn == "COMBINED_r05":
                continue
            for (era, tk, E), ch in sorted(cc.items()):
                if ch:
                    fh.write(f"{e}\t{vn}\t{g}\t{tk}\t{E}\t{len(ch)}\t{','.join(k[2] for k in ch)}\n")
    calA = S["Ds"]["A"].cal
    with open(os.path.join(OUT_DIR, "account_his.tsv"), "w") as fh:
        fh.write("variant\tdate\tequity\n")
        for vn, sim in sims.items():
            for ci, eq in zip(*sim["curve"]):
                fh.write(f"{vn}\t{calA[ci]}\t{eq:.10f}\n")
    with open(os.path.join(OUT_DIR, "account_band.tsv"), "w") as fh:
        fh.write("variant\tmeasure\this\tp5\tp25\tp50\tp75\tp95\tshare_ge_his\n")
        for vn, y, bs, hv, sg in band_out:
            fh.write("\t".join(str(x) for x in (vn, y, hv, bs.get(5), bs.get(25), bs.get(50), bs.get(75), bs.get(95), sg)) + "\n")


if __name__ == "__main__":
    sys.exit(main())
