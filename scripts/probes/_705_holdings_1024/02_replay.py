#!/usr/bin/env python3
"""#705 — HOLDINGS 02: his panel entries (01_timeline.py) replayed under his rules and measured against the market
(docs/analysis/cb_holdings_replay_prereg_2026-10-24.md). Registration only until the freeze; the real run happens ONCE after it.

The frozen second read (02_execution_variants.py, 346516fb...) is IMPORTED read-only, and through it the frozen first read (01_replay.py,
c4478588...), the runner and the cb module: the loaders, `Event`-shaped facts, `Trade` / `make_trade` / `simulate`, the control draw, G8,
the line-anchored freeze lock and `adr_pair`. Nothing in them is edited. The walkers (`cb.entry_variants`, `cb.walk_arms`,
`cb.forward_window`) are called unchanged.

What it does (the registration's §4-§7, nothing else):
  POPULATION  the timeline's entries (`holdings_1024/entries.tsv`): DECIDING = dated (breakout / EP / both), window <= 10 sessions, not
              initial; the deciding ACCOUNT takes those with the buy day inside the WINDOW 2020-01-27 .. 2022-06-14. A name's later entry
              dated to the same buy day as its earlier one is `same_day_rebuy` (F4): it cannot reuse the earlier fill (the panel showed him
              flat in between), so it is kept out of every account and listed beside. Every count asserted against `EXPECT`.
  HIS RULES   entry ORH5 on the buy day (the candidate row's level and ADR20; an EP's level = its prior close, ADR20 ours at D), stop =
              the low of the day at the fill, skipped when wider than ADR20; exits: the SPEED TRAIL `d3_p33_tspd` (DECIDING) and the first
              replay's `p33_s3_t10` (beside); sizing: 1% risk / 30% cap / 30% per stock, no margin (DECIDING = the first replay's `cap_30`
              row) and the 20% cap beside -> a 2 x 2 grid; the PANEL'S OWN EXITS beside (no stop; sold at the close of the exit window's
              last session; an entry that did not fill is bought at its buy day's close); undated entries beside (open fill, one-ADR stop).
  DECIDING    the market comparison of 04_vs_market.py, re-implemented line for line: the deciding account's curve over every session
              of the window vs QQQ / SPY -> total, CAGR, max drawdown, Sharpe, beta, annual alpha and its t. HIS BAR (fixed before any
              outcome): alpha t >= 2 AND total above QQQ AND total above SPY AND Sharpe above QQQ's -> PASS; else FAIL = OUR
              implementation (his 2026-10-23 rule), with the beside readings naming the part.
  PANEL CLOCK beside (F5): each filled deciding trade's ORH5 fill minute against the panel's clock on E (flat at a full snapshot on E
              later than our fill, or held at the first sighting on E earlier than it) -> the contradicting count by setup and the
              deciding account without those trades; our day-0 stop-outs before the panel's first sighting (our walk out, his book in).
  BAND        beside: the same-day band of the first replay for the breakout-dated entries of era A in the window (200 draws, seed 702).

No subagent, no DB, no network. Read-only on every input. Nothing dated after 2024-12-31 is kept from any era-B file.
Run:  python3 scripts/probes/_705_holdings_1024/02_replay.py --dry-run   (loads the entries and the exports up to each buy day's D,
                                                    asserts the populations, computes ADR20 at D for the EP / undated entries, checks
                                                    minute coverage from the four trees' fetch logs, checks the calendars and the QQQ /
                                                    SPY stitch, prints the pins; it COUNTS the sessions the export holds after E
                                                    (`fwd_sessions`) and reads each ticker's last bar DATE, but reads NO price after D,
                                                    opens NO minute file, calls NO entry or exit function, reads NO outcome file,
                                                    computes NO outcome)
      python3 scripts/probes/_705_holdings_1024/02_replay.py             (the REAL run: refuses (exit 2) unless every pin incl. the
                                                    doc-body hash sits under the doc's one freeze marker line, or if the printout, a
                                                    STOPPED file or ANY file under holdings_1024/replay/ exists)
"""
from __future__ import annotations

import argparse
import bisect
import gzip
import importlib.util
import math
import os
import subprocess
import sys
import time
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
EXEC_PATH = os.path.join(REPO, "scripts", "probes", "_705_qm_replay_1023", "02_execution_variants.py")


def _load_frozen():
    spec = importlib.util.spec_from_file_location("_705_exec02_frozen_r", EXEC_PATH)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["_705_exec02_frozen_r"] = mod
    spec.loader.exec_module(mod)
    return mod


ex = _load_frozen()
rp, R, cb = ex.rp, ex.R, ex.cb

# ═════════════════════════════════════════════════════════════════════════════════════════════
# paths and pins
# ═════════════════════════════════════════════════════════════════════════════════════════════
DATA = rp.DATA
H_DIR = f"{rp.B_DIR}/qm_streams/holdings_1024"
OUT_DIR = f"{H_DIR}/replay"
DOC = os.path.join(REPO, "docs", "analysis", "cb_holdings_replay_prereg_2026-10-24.md")
PRINTOUT = os.path.join(HERE, "02_replay.txt")
DRY_PRINTOUT = os.path.join(HERE, "02_replay_dryrun.txt")
STOPPED = os.path.join(HERE, "02_replay.STOPPED.txt")
MISSING_MINUTES = f"{H_DIR}/replay_missing_minutes.tsv"       # written by the dry run: the (E, ticker) pairs to fetch before the freeze
OUT_FILES = ("trades.tsv.gz", "g8_A.tsv", "g8_B.tsv", "g8_A_impact.txt", "g8_B_impact.txt", "account_his.tsv", "account_band.tsv", "market.tsv")
VIS = f"{rp.B_DIR}/qm_streams/vision"
FILES = {**rp.FILES,
         "panel": f"{VIS}/positions_panel_all.jsonl",
         "calendar_cache": f"{VIS}/positions_pct_calendar.pkl.gz",
         "lexicon": f"{VIS}/positions_ticker_lexicon_v2.tsv",
         "dedupe_A": f"{rp.A_DIR}/dedupe_applied.tsv",
         "ep_A": f"{rp.B_DIR}/qm_streams/ep_join_1023/ep_events_A.tsv.gz",
         "ep_B": f"{rp.B_DIR}/qm_streams/ep_join_1023/ep_events_B.tsv.gz",
         "entries": f"{H_DIR}/entries.tsv", "exits": f"{H_DIR}/exits.tsv", "snapshots": f"{H_DIR}/snapshots.tsv",
         "control": f"{H_DIR}/control.tsv",
         "timeline_printout": os.path.join(HERE, "01_timeline.txt"),
         "panel_read_printout": os.path.join(REPO, "scripts", "probes", "_705_positions_panel_1024", "02_read_all.txt"),   # F7
         "done_EP": f"{rp.B_DIR}/minutes_ep_1023/_done.psv"}
MINUTES = {"A": rp.MINUTES["A"], "B": rp.MINUTES["B"], "EP": f"{rp.B_DIR}/minutes_ep_1023"}
# the fetch of the EP gap days the dry run found uncovered goes to a NEW folder (the pinned trees untouched); read when it exists
EP2_DIR = f"{rp.B_DIR}/minutes_ep_1024"
if os.path.exists(os.path.join(EP2_DIR, "_done.psv")):
    MINUTES["EP2"] = EP2_DIR
    FILES["done_EP2"] = os.path.join(EP2_DIR, "_done.psv")
CODE = {**rp.CODE,
        "exec_module": EXEC_PATH, "exec_tests": os.path.join(os.path.dirname(EXEC_PATH), "test_02_execution_variants.py"),
        "timeline_module": os.path.join(HERE, "01_timeline.py"), "timeline_tests": os.path.join(HERE, "test_01_timeline.py"),
        "holdings_module": os.path.abspath(__file__), "holdings_tests": os.path.join(HERE, "test_02_replay.py"),
        "panel_reader": os.path.join(REPO, "scripts", "probes", "_705_positions_panel_1024", "01_read_panel.py")}   # F7: the reader itself
# the second read's freeze record (docs/analysis/cb_qm_replay_execution_prereg_2026-10-23.md): its module and tests must be the frozen ones;
# the first read's pins the second already carries (rp.PINNED + replay_module / replay_tests)
SECOND_MODULE_SHA = "346516fb4c236cc552103032163b790d030b10a536e83c70d4cf2390c3f9f485"
SECOND_TESTS_SHA = "6ce013bb1d7f1521e8083d014e4221fc837f30c59f9c5e00fbc023344d1a1949"
PINNED = {**ex.PINNED, "exec_module": SECOND_MODULE_SHA, "exec_tests": SECOND_TESTS_SHA}

# ═════════════════════════════════════════════════════════════════════════════════════════════
# the registration's constants
# ═════════════════════════════════════════════════════════════════════════════════════════════
CUT_B = rp.CUT_B
HORIZON = rp.HORIZON
WINDOW = ("2020-01-27", "2022-06-14")           # the deciding account's span (registration §2 / §6, R5)
ERA_A_LAST_E = "2022-03-31"                     # era by buy day (R10)
WINDOW_CAP = 10
PRIMARY_ARM = rp.PRIMARY_ARM                    # p33_s3_t10 (beside)
SPEED_ARM = "d3_p33_tspd"                       # DECIDING exit (R6)
ARMS = {PRIMARY_ARM: cb.ARMS[PRIMARY_ARM], SPEED_ARM: cb.HIS_EXIT_ARMS[SPEED_ARM]}
assert ARMS[SPEED_ARM].trail_mode == "speed" and ARMS[SPEED_ARM].partial_session == 3 and ARMS[SPEED_ARM].breakeven
CAP30 = next(c for c in rp.CONFIGS if c.name == "cap_30")
assert CAP30.cap == 0.30 and CAP30.risk == 0.01 and CAP30.stock_limit == 0.30 and CAP30.room == "skip"
CAP20 = rp.PRIMARY_CONFIG
GRID = (("deciding", SPEED_ARM, CAP30), ("primary_exit_cap30", PRIMARY_ARM, CAP30), ("speed_cap20", SPEED_ARM, CAP20),
        ("primary_exit_cap20", PRIMARY_ARM, CAP20))
DECIDING = GRID[0]
EXIT_SLIPS = rp.EXIT_SLIPS
BAR_ALPHA_T = 2.0                                # his bar, R11: alpha t >= 2 AND total > QQQ AND total > SPY AND Sharpe > QQQ's
SEED, BAND_DRAWS, BAND_KEY = rp.SEED, rp.BAND_DRAWS, "holdings|band|A"
EXPECT = {"entries": 1874, "initial": 13, "non_initial": 1861, "dated": 344, "deciding": 294, "undated": 1517,
          "in_window": 262, "in_window_breakout": 212, "in_window_EP": 43, "in_window_both": 7,
          "deciding_A": 277, "deciding_B": 17, "deciding_flicker": 91,
          "same_day_rebuy": 30, "same_day_rebuy_deciding": 2, "same_day_rebuy_in_window": 2, "same_day_rebuy_undated": 28}
# (the timeline after F1-F4, 2026-10-24: `deciding` and its splits are the timeline's; `in_window*` is the deciding ACCOUNT after the two
#  same-day re-buys leave it - 266 at the first registration -> 265 (F1, QS) -> 264 (F2, LI) -> 262 (F4, PLUG / SNAP); §12)
SETUPS = ("breakout", "EP", "both")
ORDER_CLOSE = rp.ORDER_CLOSE


class GuardStop(Exception):
    pass


# ═════════════════════════════════════════════════════════════════════════════════════════════
# the freeze lock (the second read's line-anchored lock, unchanged) and the pins
# ═════════════════════════════════════════════════════════════════════════════════════════════
FREEZE_MARKER = ex.FREEZE_MARKER
marker_spans, doc_body_sha, freeze_missing = ex.marker_spans, ex.doc_body_sha, ex.freeze_missing


def minute_files_in(tree: str, dates: list) -> list:
    files = R.minute_date_files(MINUTES[tree])
    return [str(files[d]) for d in sorted(set(dates)) if d in files]


def pins(minute_dates: "dict | None" = None, doc: "str | None" = None) -> dict:
    p = {name: rp.sha(path) for name, path in FILES.items()}
    p.update({name: rp.sha(path) for name, path in CODE.items()})
    p["first_doc_body"] = rp.doc_body_sha(rp.DOC)
    p["second_doc_body"] = ex.doc_body_sha(ex.DOC)
    for tree, dates in (minute_dates or {}).items():
        p[f"minutes_{tree}_used"] = rp.tree_sha(minute_files_in(tree, dates))
    p["doc_body"] = doc_body_sha(doc or DOC)
    return p


def existing_outputs() -> list:
    """The printout, a STOPPED file, and ANY file under the replay output folder (not only the named outputs): the run happens once."""
    out = [p for p in (PRINTOUT, STOPPED) if os.path.exists(p)]
    if os.path.isdir(OUT_DIR):
        out += sorted(os.path.join(OUT_DIR, f) for f in os.listdir(OUT_DIR))
    return out


# ═════════════════════════════════════════════════════════════════════════════════════════════
# the entries -> events
# ═════════════════════════════════════════════════════════════════════════════════════════════
@dataclass
class HEvent:
    """One panel entry as the walk sees it. `ticker` = the bar-file symbol of its era (era A today's name via the alias, era B the panel's)."""
    eid: int
    sym: str
    ticker: str
    era: str
    setup: str                      # breakout | EP | both | undated
    E: str                          # the buy day (undated: the first session of the window)
    D: str                          # the session before E
    pivot: "float | None"           # the level: the candidate's (breakout / both), the prior close (EP), None (undated: computed at run)
    adr20: "float | None"           # the candidate's (breakout / both); ours at D for EP / undated (dry run computes it)
    base_id: str
    retrigger: int
    window_len: int
    flicker: bool
    decides: bool
    in_window: bool
    exit_hi: str                    # the panel's exit session (last of the exit window), "" when still held
    still_held: bool
    year: int = 0
    month: str = ""
    qqq: str = ""
    minutes_tree: str = ""          # A | B | EP (the tree whose fetch log carries (E, ticker) as ok) or ""
    minutes_state: str = ""         # ok | empty | missing
    history: "str | None" = None    # ex.history_reason: None when walkable
    break_pre: bool = False
    fwd_sessions: int = 0           # sessions available after E in the era's export (<= HORIZON + 1)
    fwd_cut: bool = False           # the forward window stops at a hole in the ticker's sessions
    last_bar: str = ""              # the ticker's last bar DATE in the era's export (no price)
    keep: bool = True
    first_clock_on_E: str = ""      # F3 (the timeline): the first sighting's ET clock when it is on E in session
    flat_clock_on_E: str = ""       # F3: the clock of the last full snapshot without the name when it is on E
    orh5_infeasible: bool = False   # F3: held on E before 09:35 ET
    same_day_rebuy: bool = False    # F4: a later entry of the name dated to the same E as an earlier one
    rebuy_of: int = -1              # F4: the earlier entry's eid


def era_of(E: str) -> str:
    return "A" if E <= ERA_A_LAST_E else "B"


def load_events(path: str = None) -> tuple:
    """entries.tsv -> (events, counts). Initial entries and names without bars carry no event (counted)."""
    t = pd.read_csv(path or FILES["entries"], sep="\t", dtype=str, keep_default_na=False)
    c = Counter()
    c["entries"] = len(t)
    evs = []
    for r in t.to_dict("records"):
        initial = r["initial"] == "True"
        c["initial"] += int(initial)
        if initial:
            continue
        c["non_initial"] += 1
        setup = r["setup"]
        dated = setup in SETUPS
        c["dated"] += int(dated)
        c["undated"] += int(setup == "undated")
        decides = r["decides"] == "True"
        c["deciding"] += int(decides)
        if decides:
            c[f"deciding_{r['era']}"] += 1
            c["deciding_flicker"] += int(r["flicker"] == "True")
        if r["has_bars"] != "True":
            c["skipped_no_bars"] += 1
            continue
        E = r["E"] if dated else r["lo"]
        era = r["era"] if dated else era_of(E)
        in_window = decides and WINDOW[0] <= E <= WINDOW[1]
        ev = HEvent(eid=int(r["eid"]), sym=r["sym"], ticker=r["sym_a"] if era == "A" else r["sym"], era=era, setup=setup, E=E,
                    D=r["D"] if dated else "", pivot=None, adr20=None, base_id=r.get("base_id", ""), retrigger=int(r["retrigger"] or 0),
                    window_len=int(r["window_len"]), flicker=r["flicker"] == "True", decides=decides, in_window=in_window,
                    exit_hi=r["exit_hi"], still_held=r["still_held"] == "True", year=int(E[:4]), month=E[:7],
                    first_clock_on_E=r.get("first_clock_on_E", ""), flat_clock_on_E=r.get("flat_clock_on_E", ""),
                    orh5_infeasible=r.get("orh5_infeasible", "") == "True")
        if setup in ("breakout", "both"):
            ev.pivot, ev.adr20 = float(r["pivot"]), float(r["adr20"])
        elif setup == "EP":
            ev.pivot = float(r["ep_prev_close"])
        evs.append(ev)
    mark_same_day_rebuys(evs, c)
    for k in ("in_window", "in_window_breakout", "in_window_EP", "in_window_both"):
        c[k] += 0                                    # present even when 0 (check_expect reads a missing key as NOT MEASURED)
    for ev in evs:
        if ev.in_window:
            c["in_window"] += 1
            c[f"in_window_{ev.setup}"] += 1
    return evs, c


def mark_same_day_rebuys(evs: list, c: Counter) -> None:
    """F4: a name's later entry (timeline order = eid) dated to the SAME buy day E as an earlier entry of the same bar-file name and the
    same kind (dated / undated) cannot reuse the earlier entry's fill - the panel showed him flat in between (PLUG 2021-02-03 flat at
    10:55, SNAP 2021-06-11 flat at 11:51). It is classified `same_day_rebuy`: out of the deciding set, the window and every account (the
    run does not walk it), listed beside. Counted, every key present."""
    for k in ("same_day_rebuy", "same_day_rebuy_deciding", "same_day_rebuy_in_window", "same_day_rebuy_undated"):
        c[k] += 0
    first = {}
    for ev in sorted(evs, key=lambda x: x.eid):
        k = (ev.era, ev.ticker, ev.E, ev.setup == "undated")
        if k not in first:
            first[k] = ev.eid
            continue
        ev.same_day_rebuy, ev.rebuy_of = True, first[k]
        c["same_day_rebuy"] += 1
        c["same_day_rebuy_deciding"] += int(ev.decides)
        c["same_day_rebuy_in_window"] += int(ev.in_window)
        c["same_day_rebuy_undated"] += int(ev.setup == "undated")
        ev.decides = ev.in_window = False


def check_expect(got: Counter) -> list:
    return rp.check_expect(dict(got), EXPECT)


# ═════════════════════════════════════════════════════════════════════════════════════════════
# calendars, market closes, per-event facts (outcome-free)
# ═════════════════════════════════════════════════════════════════════════════════════════════
def unify_calendars(cal_a: list, cal_b: list) -> tuple:
    """(cal_u, map_b): era A's sessions followed by era B's after A's last; the overlap asserted equal session for session.
    map_b[ci_B] = the unified index of era B's session ci_B."""
    last_a = cal_a[-1]
    k0 = bisect.bisect_left(cal_a, cal_b[0])
    overlap_a = cal_a[k0:]
    overlap_b = [d for d in cal_b if d <= last_a]
    if overlap_a != overlap_b:
        raise GuardStop(f"the two exports' sessions differ on their overlap: A {len(overlap_a)} vs B {len(overlap_b)} "
                        f"(first difference {next((x for x, y in zip(overlap_a, overlap_b) if x != y), None)})")
    cal_u = list(cal_a) + [d for d in cal_b if d > last_a]
    pos = {d: i for i, d in enumerate(cal_u)}
    map_b = np.asarray([pos[d] for d in cal_b], dtype=np.int64)
    return cal_u, map_b


def stitched_closes(DA, DB, cal_u: list, map_b: np.ndarray, tol: float = 0.005) -> dict:
    """{ticker: closes over cal_u} for QQQ and SPY: era A through its last session, era B after; the overlap compared (within `tol`)."""
    out = {}
    for tk in ("QQQ", "SPY"):
        a = np.full(len(cal_u), np.nan)
        ba, ca = R.bars_for(DA, DA.tid[tk])
        a[ca] = ba.c
        bb, cbi = R.bars_for(DB, DB.tid[tk])
        u = map_b[cbi]
        both = ~np.isnan(a[u])
        rel = np.abs(bb.c[both] / a[u][both] - 1.0)
        if len(rel) and float(rel.max()) > tol:
            raise GuardStop(f"{tk}: era A and era B closes differ by up to {100 * rel.max():.2f}% on the overlap")
        a[u[~both]] = bb.c[~both]
        if np.isnan(a).any():
            raise GuardStop(f"{tk}: {int(np.isnan(a).sum())} sessions of the unified calendar without a close")
        out[tk] = a
    return out


def event_facts(ev: HEvent, D, qqq: tuple, guards: dict, done: dict, files: dict, cal: list) -> None:
    """Outcome-free: D for undated entries, the walkability reason, ADR20 at D (EP / undated), the QQQ state, the identity break in
    (E - 130, E], the forward sessions the export holds, the minute coverage (fetch logs only)."""
    e_ci = bisect.bisect_left(cal, date.fromisoformat(ev.E))
    if not (e_ci < len(cal) and cal[e_ci].isoformat() == ev.E):
        ev.history, ev.keep = "E_not_a_session", False
        return
    if not ev.D:
        ev.D = cal[e_ci - 1].isoformat() if e_ci > 0 else ""
    tid = D.tid.get(ev.ticker)
    if tid is None:
        ev.history, ev.keep = "ticker_not_in_export", False
        return
    bars, cidx = R.bars_for(D, tid)
    ev.history = ex.history_reason(ev, bars, cidx, cal)
    if ev.history is not None:
        ev.keep = False
        return
    p = int(np.searchsorted(cidx, e_ci))
    if ev.adr20 is None:
        try:
            ev.adr20 = ex.adr_pair(bars, p - 1)[0]
        except ValueError as exc:
            ev.history, ev.keep = f"adr20: {exc}", False
            return
    if not ev.adr20 > 0:
        ev.history, ev.keep = "adr20_not_positive", False
        return
    qb, qc = qqq
    k = int(np.searchsorted(qc, e_ci - 1))
    ev.qqq = rp.qqq_state_at(qb.c, k) if (k < len(qc) and int(qc[k]) == e_ci - 1) else ""
    lo, eo, _hi = rp.window_ords(cal, e_ci, rp.BREAK_PRE, rp.BREAK_POST)
    ev.break_pre = rp.break_in(guards.get(ev.ticker), lo, eo)
    fwd, cut = cb.forward_window(bars, cidx, p, HORIZON)
    ev.fwd_sessions, ev.fwd_cut, ev.last_bar = len(fwd), bool(cut), bars.dates[-1].isoformat()
    ep_trees = tuple(t for t in ("EP", "EP2") if t in done)
    trees = ep_trees + (ev.era,) if ev.setup == "EP" else (ev.era,) + ep_trees
    ev.minutes_tree, ev.minutes_state = "", "missing"
    for tr in trees:
        st = done[tr].get((ev.E, ev.ticker))
        if st == "ok" and ev.E in files[tr]:
            ev.minutes_tree, ev.minutes_state = tr, "ok"
            break
        if st == "empty" and ev.minutes_state == "missing":
            ev.minutes_tree, ev.minutes_state = tr, "empty"
    if ev.setup == "undated":
        ev.minutes_state = "n/a"                 # the open fill needs no minutes
    ev.keep = not ev.break_pre and ev.minutes_state != "missing" and not ev.same_day_rebuy     # F4: a same-day re-buy is never walked


# ═════════════════════════════════════════════════════════════════════════════════════════════
# the walk (real run) — the module's functions, unchanged; an undated entry's open fill
# ═════════════════════════════════════════════════════════════════════════════════════════════
def undated_entry(bars, e: int, adr20: float, slippage: float = cb.ENTRY_SLIPPAGE_PCT) -> dict:
    """BESIDE only: bought at the open of the first possible session (+ slippage); stop = one ADR20 below the fill (his cap on the stop's
    width, used as the stop: a modelling choice); a day whose low touches the stop is a day-0 stop at the stop price."""
    fill = float(bars.o[e]) * (1.0 + slippage)
    stop = fill * (1.0 - float(adr20))
    stopped = float(bars.l[e]) <= stop
    return {"status": "filled", "reason": None, "fill": fill, "stop": stop, "fill_minute": 0, "width_pct": (fill - stop) / fill,
            "level": float(bars.o[e]), "day0": {"stopped": stopped, "exit_price": stop if stopped else None, "exit_minute": None}}


def minute_clock(m: int) -> str:
    """The ET clock 'HH:MM' at which minute m of the session starts (minute 0 = 09:30)."""
    t = 9 * 60 + 30 + int(m)
    return f"{t // 60:02d}:{t % 60:02d}"


def panel_vs_fill(ev: HEvent, en: dict) -> dict:
    """F5, BESIDE (registration §7): our ORH5 fill against the panel's clock on E (the timeline's F3 columns). The panel's clock is a
    minute ('HH:MM'); a fill IN that same minute is ambiguous and never counted.
      before_flat   our fill's minute ends before the clock of a full snapshot on E that shows him flat (he bought later than our fill);
      after_held    our fill's minute starts after the first snapshot on E that shows him holding (he bought earlier; every fill of an
                    `orh5_infeasible` entry is one);
      day0_out_while_held             our day-0 stop's minute ends before that first holding snapshot on E (our walk is out, his book in);
      day0_out_before_later_sighting  a day-0 stop on an entry the panel first shows after E (he still held it at that later sighting)."""
    out = dict(fill_clock="", before_flat=False, after_held=False, contradicts=False, day0_out_while_held=False,
               day0_out_before_later_sighting=False)
    if en.get("status") != "filled" or en.get("fill_minute") is None:
        return out
    fc = minute_clock(en["fill_minute"])
    out["fill_clock"] = fc
    out["before_flat"] = bool(ev.flat_clock_on_E) and fc < ev.flat_clock_on_E
    out["after_held"] = bool(ev.first_clock_on_E) and fc > ev.first_clock_on_E
    out["contradicts"] = out["before_flat"] or out["after_held"]
    d0 = en.get("day0") or {}
    if d0.get("stopped") and d0.get("exit_minute") is not None:
        if ev.first_clock_on_E:
            out["day0_out_while_held"] = minute_clock(d0["exit_minute"]) < ev.first_clock_on_E
        else:
            out["day0_out_before_later_sighting"] = True
    return out


def walk_entry(ev: HEvent, bars, cidx, e: int, mb, breaks) -> dict:
    """{entry, arms{arm: raw}, n_fwd, hole, break_cut} for one event, wired as the first replay's `walk_event` (E alignment, contiguity,
    closes through E, `forward_window`, the identity-break cut); the arms are the two of this registration."""
    assert bars.dates[e].isoformat() == ev.E, (ev.ticker, e, ev.E)
    assert e >= cb.MIN_HISTORY and int(cidx[e]) - int(cidx[e - cb.MIN_HISTORY]) == cb.MIN_HISTORY, (ev.ticker, ev.E)
    if ev.setup == "undated":
        en = undated_entry(bars, e, ev.adr20)
    else:
        en = cb.entry_variants(mb, pivot=ev.pivot, adr20=ev.adr20, day_high=float(bars.h[e]), day_low=float(bars.l[e]))["orh5"]
    closes_before = bars.c[:e + 1]
    fwd, cut = cb.forward_window(bars, cidx, e, HORIZON)
    fwd, brk = rp.cut_at_break(fwd, bars.dates[e], breaks)
    out = {"n_fwd": len(fwd), "hole": bool(cut), "break_cut": brk, "entry": en, "arms": {}}
    if en["status"] == "filled":
        out["arms"] = cb.walk_arms(en, closes_before=closes_before, fwd=fwd, adr20=ev.adr20, horizon=HORIZON, arms=ARMS)
    return out


def panel_exit_trade(ev: HEvent, en: "dict | None", bars, cidx, e: int, exit_ci: int, slippage: float = cb.ENTRY_SLIPPAGE_PCT) -> "rp.Trade":
    """BESIDE: the panel's own exit. The ORH5 fill when the entry filled, else the buy day's close (+ slippage); NO stop; one `mark` leg at
    the close of the exit session `exit_ci` (the era calendar's index), or at the ticker's last consecutive bar before it (status
    `panel_exit_truncated`). Sizing width = the ORH5 stop width when filled, else one ADR20."""
    filled = en is not None and en.get("status") == "filled"
    fill = float(en["fill"]) if filled else float(bars.c[e]) * (1.0 + slippage)
    width = float((en["fill"] - en["stop"]) / en["fill"]) if filled else float(ev.adr20)
    stop = fill * (1.0 - width)
    j = e
    while j + 1 < len(cidx) and int(cidx[j + 1]) == int(cidx[j]) + 1 and int(cidx[j + 1]) <= exit_ci:
        j += 1
    truncated = int(cidx[j]) < exit_ci
    px = float(bars.c[j])
    legs = [(int(cidx[j]), ORDER_CLOSE, 1.0, px, "mark", j - e)]
    rs = tuple(rp.r_with_slip(legs, fill, stop, s) for s in EXIT_SLIPS)
    return rp.Trade(key=(ev.era, ev.ticker, ev.E), ticker=ev.ticker, era=ev.era, e_ci=int(cidx[e]),
                    fill_minute=int(en["fill_minute"]) if filled else 0, fill=fill, stop=stop, width=width,
                    status="panel_exit_truncated" if truncated else ("panel_exit_close_fill" if not filled else "panel_exit"),
                    mature=True, realized_r=rs[0], r_slip=rs, sessions_held=j - e, legs=legs,
                    path_c=np.asarray(bars.c[e:j + 1], dtype=float), retrigger=ev.retrigger, year=ev.year, month=ev.month)


def to_unified(t: "rp.Trade", map_b: "np.ndarray | None") -> "rp.Trade":
    """An era-B trade's calendar indices moved onto the unified calendar (era A's are the unified ones already)."""
    if t.era != "B" or map_b is None:
        return t
    t.e_ci = int(map_b[t.e_ci])
    t.legs = [(int(map_b[ci]), o, f, px, k, s) for ci, o, f, px, k, s in t.legs]
    return t


# ═════════════════════════════════════════════════════════════════════════════════════════════
# the market comparison (04_vs_market.py's formulas) and his bar
# ═════════════════════════════════════════════════════════════════════════════════════════════
def curve_on_window(sim: dict, w0: int, w1: int) -> np.ndarray:
    """The account's equity on every session w0..w1 (inclusive): 1.0 before its first curve point, the last value after its last."""
    ci, eq = sim["curve"]
    out = np.ones(w1 - w0 + 1)
    if not len(ci):
        return out
    ci, eq = np.asarray(ci), np.asarray(eq, dtype=float)
    for k, c in enumerate(range(w0, w1 + 1)):
        j = int(np.searchsorted(ci, c, side="right")) - 1
        out[k] = eq[j] if j >= 0 else 1.0
    return out


def market_stats(eq: np.ndarray, qqq: np.ndarray, spy: np.ndarray) -> dict:
    """04_vs_market.py's `stats`, line for line on aligned arrays: total, CAGR, QQQ / SPY totals, max drawdown (both), Sharpe (daily, rf 0,
    x sqrt 252, sample std) for the account and QQQ, and the daily regression of the account on QQQ -> beta, annual alpha, alpha t."""
    eq, qqq, spy = (np.asarray(x, dtype=float) for x in (eq, qqq, spy))
    r, q, s = eq[1:] / eq[:-1] - 1.0, qqq[1:] / qqq[:-1] - 1.0, spy[1:] / spy[:-1] - 1.0
    yrs = len(eq) / 252
    tot, qt, st = eq[-1] / eq[0] - 1.0, qqq[-1] / qqq[0] - 1.0, spy[-1] / spy[0] - 1.0
    dd = float((eq / np.maximum.accumulate(eq) - 1.0).min())
    qdd = float((qqq / np.maximum.accumulate(qqq) - 1.0).min())
    sd, qsd = (float(np.std(x, ddof=1)) if len(x) > 1 else 0.0 for x in (r, q))
    sh = float(r.mean() / sd * math.sqrt(252)) if sd > 0 else float("nan")
    qsh = float(q.mean() / qsd * math.sqrt(252)) if qsd > 0 else float("nan")
    X = np.vstack([np.ones(len(q)), q]).T
    try:
        b, *_ = np.linalg.lstsq(X, r, rcond=None)
        e = r - X @ b
        se = math.sqrt((e @ e) / (len(e) - 2) * np.linalg.inv(X.T @ X)[0, 0]) if len(e) > 2 else float("nan")
    except np.linalg.LinAlgError:                    # a market series without variance: no regression (never in the real data)
        b, se = np.array([float("nan"), float("nan")]), float("nan")
    return dict(total=float(tot), cagr=float((1 + tot) ** (1 / yrs) - 1) if yrs > 0 and tot > -1 else float("nan"), qqq=float(qt),
                spy=float(st), maxdd=dd, qqq_dd=qdd, sharpe=sh, qqq_sharpe=qsh, beta=float(b[1]), alpha_ann=float(b[0] * 252),
                alpha_t=float(b[0] / se) if se and se > 0 else float("nan"), days=len(eq))


def bar_verdict(st: dict) -> tuple:
    """(PASS, [failed conditions]) — his bar as the registration's four conditions, all required."""
    failed = []
    if not st["alpha_t"] >= BAR_ALPHA_T:
        failed.append(f"alpha t {st['alpha_t']:.2f} < {BAR_ALPHA_T}")
    if not st["total"] > st["qqq"]:
        failed.append(f"total {100 * st['total']:.1f}% not above QQQ {100 * st['qqq']:.1f}%")
    if not st["total"] > st["spy"]:
        failed.append(f"total {100 * st['total']:.1f}% not above SPY {100 * st['spy']:.1f}%")
    if not st["sharpe"] > st["qqq_sharpe"]:
        failed.append(f"Sharpe {st['sharpe']:.2f} not above QQQ's {st['qqq_sharpe']:.2f}")
    return (not failed), failed


def fmt_stats(st: dict) -> str:
    return (f"total {100 * st['total']:+.1f}% (QQQ {100 * st['qqq']:+.1f}%, SPY {100 * st['spy']:+.1f}%) | CAGR {100 * st['cagr']:.1f}% | max DD "
            f"{100 * st['maxdd']:.1f}% (QQQ {100 * st['qqq_dd']:.1f}%) | Sharpe {st['sharpe']:.2f} (QQQ {st['qqq_sharpe']:.2f}) | beta {st['beta']:.2f} | "
            f"alpha {100 * st['alpha_ann']:+.1f}%/yr, t {st['alpha_t']:.2f} | {st['days']} sessions")


# ═════════════════════════════════════════════════════════════════════════════════════════════
# loading (dry run and real run)
# ═════════════════════════════════════════════════════════════════════════════════════════════
def load_all(say) -> dict:
    evs, got = load_events()
    bad = check_expect(got)
    say("\n## Populations (asserted against the registration §2)")
    for k in sorted(EXPECT):
        say(f"- {k}: {got.get(k, 'NOT MEASURED')}")
    say(f"- entries without bars (no event): {got['skipped_no_bars']}")
    if bad:
        raise GuardStop("POPULATION MISMATCH: " + "; ".join(bad))
    say("- every population equals the registration")
    need = {e: {ev.ticker for ev in evs if ev.era == e} | {"QQQ", "SPY"} for e in ("A", "B")}
    # the same-day band's pool (beside): every era-A tl row on his era-A breakout buy days inside the window; its tickers join the load
    his_days = {ev.E for ev in evs if ev.in_window and ev.era == "A" and ev.setup in ("breakout", "both")}
    candA, _ = rp.read_tsv(rp.FILES["cand_A"], rp.CAND_COLS, keep=rp.cand_keep_A)
    pool_rows = candA[candA["E"].isin(his_days)].reset_index(drop=True)
    need["A"] |= set(pool_rows["ticker"])
    say(f"- same-day band pool (beside): {len(pool_rows):,} era-A tl rows on {len(his_days)} of his breakout buy days ({pool_rows['ticker'].nunique():,} tickers, loaded with his)")
    t0 = time.time()
    DA, infoA = rp.load_daily_subset(FILES["export_A"], keep=need["A"])
    DB, infoB = rp.load_daily_subset(FILES["export_B"], keep=need["B"], cut=CUT_B)
    say(f"\n## Loads (era B: every row dated after {CUT_B} dropped at read)")
    say(f"- daily exports loaded in {time.time() - t0:.0f}s: era A {infoA['rows_kept']:,} of {infoA['rows_read']:,} rows kept ({len(DA.tickers):,} "
        f"tickers, calendar {DA.cal[0]}..{DA.cal[-1]}); era B {infoB['rows_kept']:,} of {infoB['rows_read']:,} rows kept ({len(DB.tickers):,} tickers, "
        f"calendar {DB.cal[0]}..{DB.cal[-1]}), rows dated after the cut DROPPED AT READ {infoB['dated_after_cut']:,}")
    assert DB.cal[-1].isoformat() <= CUT_B
    cal_u, map_b = unify_calendars(DA.cal, DB.cal)
    say(f"- unified calendar: {len(cal_u):,} sessions {cal_u[0]}..{cal_u[-1]}; the exports agree on their overlap "
        f"({sum(1 for d in DB.cal if d <= DA.cal[-1])} sessions)")
    px = stitched_closes(DA, DB, cal_u, map_b)
    say("- QQQ / SPY closes stitched at era A's last session (overlap within 0.5%, asserted); dividends excluded")
    w0, w1 = (bisect.bisect_left(cal_u, date.fromisoformat(d)) for d in WINDOW)
    assert cal_u[w0].isoformat() == WINDOW[0] and cal_u[w1].isoformat() == WINDOW[1], "the window's ends are not sessions"
    say(f"- deciding window {WINDOW[0]}..{WINDOW[1]}: {w1 - w0 + 1} sessions")
    doneA, _ = rp.load_done(FILES["done_A"])
    doneB, dropB = rp.load_done(FILES["done_B"], cut=CUT_B)
    doneEP, _ = rp.load_done(FILES["done_EP"])
    done = {"A": doneA, "B": doneB, "EP": doneEP}
    if "EP2" in MINUTES:
        done["EP2"], _ = rp.load_done(FILES["done_EP2"])
    files = {k: R.minute_date_files(v) for k, v in MINUTES.items()}
    say(f"- fetch logs: era A {len(doneA):,} pairs, era B {len(doneB):,} (dropped after the cut {dropB:,}), EP tree {len(doneEP):,}"
        + (f", EP2 tree (the pre-freeze fetch) {len(done['EP2']):,}" if "EP2" in done else ", EP2 tree (the pre-freeze fetch): absent")
        + "; date files " + ", ".join(f"{k} {len(v):,}" for k, v in files.items()))
    guards = {"A": R.load_breaks(FILES["guard_A"]), "B": R.load_breaks(FILES["guard_B"])}
    Ds = {"A": DA, "B": DB}
    qqq = {e: R.bars_for(Ds[e], Ds[e].tid["QQQ"]) for e in ("A", "B")}
    for ev in evs:
        event_facts(ev, Ds[ev.era], qqq[ev.era], guards[ev.era], done, files, Ds[ev.era].cal)
    return dict(evs=evs, got=got, Ds=Ds, cal_u=cal_u, map_b=map_b, px=px, w0=w0, w1=w1, done=done, files=files, guards=guards,
                pool_rows=pool_rows)


def describe(say, S: dict) -> None:
    evs = S["evs"]
    say("\n## Per-event facts (outcome-free: bars up to D, fetch logs, the identity guard)")
    for lab, sel in (("DECIDING in window", [e for e in evs if e.in_window]), ("deciding, all years", [e for e in evs if e.decides]),
                     ("dated, wider than the cap", [e for e in evs if e.setup in SETUPS and not e.decides and not e.same_day_rebuy]),
                     ("undated (beside)", [e for e in evs if e.setup == "undated" and not e.same_day_rebuy])):
        n = len(sel)
        say(f"- {lab}: n = {n}; by setup " + ", ".join(f"{k} {v}" for k, v in sorted(Counter(e.setup for e in sel).items()))
            + "; by era " + ", ".join(f"{k} {v}" for k, v in sorted(Counter(e.era for e in sel).items())))
        say(f"    walkable {sum(1 for e in sel if e.history is None)}; not walkable: " + (", ".join(f"{k} {v}" for k, v in sorted(Counter(e.history for e in sel if e.history).items())) or "none"))
        say(f"    minutes (fetch logs): " + ", ".join(f"{k} {v}" for k, v in sorted(Counter(f"{e.minutes_state or 'not_walkable'}{'/' + e.minutes_tree if e.minutes_tree else ''}" for e in sel).items()))
            + f"; identity break in (E-130, E] {sum(1 for e in sel if e.break_pre)}; KEEP (walked in the real run) {sum(1 for e in sel if e.keep)}")
        if n:
            say(f"    forward sessions in the export < {HORIZON + 1} (an open walk marks at the export's last bar) {sum(1 for e in sel if e.history is None and e.fwd_sessions < HORIZON + 1)}; "
                f"QQQ at D up {sum(1 for e in sel if e.qqq == 'up')} / mixed {sum(1 for e in sel if e.qqq == 'mixed')} / down {sum(1 for e in sel if e.qqq == 'down')}; "
                f"flickers {sum(1 for e in sel if e.flicker)}; retriggers {sum(1 for e in sel if e.setup != 'EP' and e.retrigger == 1)}; still held at the last stream {sum(1 for e in sel if e.still_held)}")
    win = [e for e in evs if e.in_window]
    for lab, sel in (("in the window", win), ("all years", [e for e in evs if e.decides])):
        short = [e for e in sel if e.history is None and e.fwd_sessions < HORIZON + 1]
        why = Counter("a hole in its sessions" if e.fwd_cut else ("its bars end before the export's last session (delisting / merger)"
                      if e.last_bar < S["Ds"][e.era].cal[-1].isoformat() else "the export's end") for e in short)
        say(f"- deciding, {lab}: forward window shorter than the horizon {len(short)} - " + ", ".join(f"{k} {v}" for k, v in sorted(why.items()))
            + "; " + ", ".join(f"{e.ticker} {e.E} (last bar {e.last_bar})" for e in sorted(short, key=lambda x: x.E)))
    reb = [e for e in evs if e.same_day_rebuy]
    say(f"- same-day re-buys (F4; out of every account, not walked, listed beside): {len(reb)} - "
        + ", ".join(f"{e.ticker} {e.E} #{e.eid} after #{e.rebuy_of} ({e.setup}; flat at {e.flat_clock_on_E or '-'})" for e in reb))
    say(f"- panel clocks on E (F3, the timeline; read against the fill minute in the run, F5): in the window held before 09:35 "
        f"{sum(1 for e in win if e.orh5_infeasible)} ({', '.join(f'{e.ticker} {e.E} {e.first_clock_on_E}' for e in win if e.orh5_infeasible)}); "
        f"flat at an in-session snapshot on E {sum(1 for e in win if e.flat_clock_on_E >= '09:30')}; first seen in session on E "
        f"{sum(1 for e in win if e.first_clock_on_E)}")
    adr = [e.adr20 for e in win if e.adr20]
    say(f"- deciding-window ADR20 at D: median {100 * float(np.median(adr)):.1f}%, above the speed cut {100 * cb.TRAIL_SPEED_ADR_CUT:.2f}% "
        f"(the 10-day trail) {sum(1 for a in adr if a > cb.TRAIL_SPEED_ADR_CUT)} of {len(adr)}")
    say(f"- deciding-window buy days {len({e.E for e in win})}, names {len({e.ticker for e in win})}; by year " + ", ".join(f"{k} {v}" for k, v in sorted(Counter(e.year for e in win).items()))
        + "; by month max " + str(max(Counter(e.month for e in win).values())) + " entries")
    miss = [e for e in evs if e.decides and e.minutes_state == "missing"]
    pd.DataFrame([{"eid": e.eid, "era": e.era, "ticker": e.ticker, "E": e.E, "setup": e.setup, "in_window": e.in_window} for e in miss]).to_csv(MISSING_MINUTES, sep="\t", index=False)
    say(f"- deciding entries with NO minute file in any tree: {len(miss)} (in the window {sum(1 for e in miss if e.in_window)}) -> written to "
        f"{MISSING_MINUTES} = the fetch before the freeze; any still missing at the run abstain `no_minutes` and are counted")
    # the same-day band's pool (outcome-free: candidate rows on the deciding breakout buy days, minus his held names)
    his_days = sorted({e.E for e in win if e.setup in ("breakout", "both") and e.era == "A"})
    say(f"- same-day band (beside): {len(his_days)} era-A breakout buy days in the window carry his {sum(1 for e in win if e.setup in ('breakout', 'both') and e.era == 'A')} breakout entries; "
        f"the pool is drawn from `candidates_tl_com.tsv` (K = tl) on those days in the real run, minus names he held that day")


# ═════════════════════════════════════════════════════════════════════════════════════════════
# the real run
# ═════════════════════════════════════════════════════════════════════════════════════════════
def held_names_by_day(entries_path: str, cal_u: list) -> dict:
    """{E: set of era-A names he held on E (an entry with lo <= E <= exit_hi, or still held)} for the band's exclusion."""
    t = pd.read_csv(entries_path, sep="\t", dtype=str, keep_default_na=False)
    out = defaultdict(set)
    sess = [d.isoformat() for d in cal_u]
    for r in t.to_dict("records"):
        if r["initial"] == "True" or not r["lo"]:
            continue
        lo = r["lo"]
        hi = r["exit_hi"] if r["exit_hi"] else sess[-1]
        i0, i1 = bisect.bisect_left(sess, lo), bisect.bisect_right(sess, hi)
        for d in sess[i0:i1]:
            out[d].add(r["sym_a"])
    return out


def walk_all(S: dict, evs: list, say, label: str) -> dict:
    """Walk every kept event once, by era and date (one minute file read per (tree, date)). -> {eid: walk}."""
    res, tally = {}, Counter()
    by_key = defaultdict(list)
    for ev in evs:
        if ev.keep:
            by_key[(ev.era, ev.minutes_tree or ev.era, ev.E)].append(ev)
    cache = {}
    for n, ((era, tree, d), group) in enumerate(sorted(by_key.items())):
        D = S["Ds"][era]
        path = S["files"][tree].get(d)
        want = {x.ticker for x in group if x.setup != "undated"}
        blocks = R.read_minute_file(path, want=want)[0] if (path is not None and want) else {}
        done = {(d, x.ticker): x.minutes_state for x in group}        # membership = fetched (the log says so); no block -> `no_minutes`
        for ev in group:
            mb = None
            if ev.setup != "undated":
                mb, state = R.minutes_for(blocks, done, d, ev.ticker)
                tally[f"{label}_minutes_{state}"] += 1
            key = (era, ev.ticker)
            if key not in cache:
                cache[key] = R.bars_for(D, D.tid[ev.ticker])
            bars, cidx = cache[key]
            e = R.locate_breakout_index(D.cal, cidx, ev.E)
            w = walk_entry(ev, bars, cidx, e, mb, S["guards"][era].get(ev.ticker))
            w["bars"], w["cidx"], w["e"] = bars, cidx, e
            res[ev.eid] = w
            tally[f"{label}_entry_{w['entry']['status']}_{w['entry'].get('reason') or ''}".rstrip("_")] += 1
        if (n + 1) % 50 == 0:
            print(f"  {label}: {n + 1}/{len(by_key)} (era, tree, date) groups walked", flush=True)
    return res, tally


def trades_with_events(evs: list, res: dict, arm: str, map_b) -> list:
    """[(event, Trade)] for the events whose entry filled, under `arm`, on the unified calendar (map_b None = the era's own)."""
    out = []
    for ev in evs:
        w = res.get(ev.eid)
        if not w or w["entry"]["status"] != "filled" or arm not in w["arms"]:
            continue
        t = rp.make_trade(ev, w["entry"], w["arms"][arm], w["bars"], w["cidx"], w["e"], w["n_fwd"])
        out.append((ev, to_unified(t, map_b)))
    return out


def trades_of(evs: list, res: dict, arm: str, map_b) -> list:
    return [t for _ev, t in trades_with_events(evs, res, arm, map_b)]


def panel_trades_of(evs: list, res: dict, S: dict, last_asof: str) -> tuple:
    out, c = [], Counter()
    for ev in evs:
        w = res.get(ev.eid)
        if not w:
            continue
        cal = S["Ds"][ev.era].cal
        exit_d = ev.exit_hi if (ev.exit_hi and not ev.still_held) else last_asof
        exit_ci = bisect.bisect_right(cal, date.fromisoformat(exit_d)) - 1
        if exit_ci < int(w["cidx"][w["e"]]):
            c["exit_before_buy_day_set_to_buy_day"] += 1
            exit_ci = int(w["cidx"][w["e"]])
        en = w["entry"] if w["entry"]["status"] == "filled" else None
        t = panel_exit_trade(ev, en, w["bars"], w["cidx"], w["e"], exit_ci)
        c[t.status] += 1
        out.append(to_unified(t, S["map_b"]))
    return out, c


def account_lines(say, name: str, sim: dict) -> None:
    yr = ", ".join(f"{y} {rp.pct(r)}" for y, r in sorted(sim["yearly"].items()))
    cnt = sim["counts"]
    say(f"- {name}: final {sim['final']:.3f} | by year {yr} | max DD {rp.pct(sim['max_dd'])} | entered {cnt['entered']}, skipped no room "
        f"{cnt['skipped_no_room']}, per-stock limit {cnt['skipped_stock_limit']} (trimmed {cnt['stock_limit_trimmed']}), cap-bound {cnt['cap_bound']}, "
        f"concurrent same stock {cnt['same_ticker_concurrent']} | max open {sim['max_open']}, max gross {rp.pct(sim['max_gross'])}")


def per_trade_table(say, groups: list) -> None:
    hdr = ["group", "n", ">=5R/100", ">=10R/100", ">=20R/100", "max R", "worst R", "win", "mean R", "median R", "sum R", "mean R @0.1%", "@0.2%"]
    rows = []
    for name, trades in groups:
        mt = [t for t in trades if t.mature]
        st = rp.tail_stats([t.realized_r for t in mt])
        if st["n"] == 0:
            rows.append([name, 0] + ["-"] * 11)
            continue
        rows.append([name, st["n"], rp.fmt(st["ge5"], 1), rp.fmt(st["ge10"], 1), rp.fmt(st["ge20"], 1), rp.fmt(st["max"]), rp.fmt(st["worst"]),
                     rp.pct(st["win"]), rp.fmt(st["mean"], 3), rp.fmt(st["median"], 3), rp.fmt(st["sum"], 1),
                     rp.fmt(float(np.mean([t.r_slip[1] for t in mt])), 3), rp.fmt(float(np.mean([t.r_slip[2] for t in mt])), 3)])
    for ln in rp.table(hdr, rows):
        say(ln)


def write_g8(era: str, trades: list, cal_u: list) -> tuple:
    path, txt = os.path.join(OUT_DIR, f"g8_{era}.tsv"), os.path.join(OUT_DIR, f"g8_{era}_impact.txt")
    rp.write_g8_file(path, [(SPEED_ARM, t.ticker, cal_u[t.e_ci].isoformat(), t.sessions_held, t.realized_r) for t in trades])
    cmd = [sys.executable, rp.TRADE_IMPACT, "--flags", rp.FILES[f"flags_{era}"], "--export", rp.FILES[f"export_{era}"], "--trades", path,
           "--label", era, "--kind", "r1", "--cell", SPEED_ARM, "--cutoff", CUT_B]
    res = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)
    text = res.stdout + ("\n[stderr]\n" + res.stderr if res.stderr.strip() else "")
    with open(txt, "w") as fh:
        fh.write(" ".join(cmd) + "\n\n" + text)
    if res.returncode != 0:
        raise GuardStop(f"trade_impact.py exited {res.returncode} for era {era}")
    return rp.parse_g8(text)


def run_replay(S: dict, say) -> None:
    os.makedirs(OUT_DIR, exist_ok=True)
    evs, cal_u, map_b, px, w0, w1 = S["evs"], S["cal_u"], S["map_b"], S["px"], S["w0"], S["w1"]
    snaps = pd.read_csv(FILES["snapshots"], sep="\t", dtype=str, keep_default_na=False)
    last_asof = max(snaps["asof"])
    win = [e for e in evs if e.in_window]
    say("\n## THE WALK")
    res, tally = walk_all(S, [e for e in evs if e.keep], say, "his")
    for k, v in sorted(tally.items()):
        say(f"- {k}: {v}")
    # ---- G8 BEFORE any number: the deciding arm's trades per era
    say("\n## G8 — this read's own trade list through trade_impact.py (before any number)")
    for era in ("A", "B"):
        tr = trades_of([e for e in evs if e.era == era and e.decides], res, SPEED_ARM, None)
        if not tr:
            say(f"- era {era}: no filled deciding trade; G8 not run")
            continue
        after, past = write_g8(era, tr, S["Ds"][era].cal)
        say(f"- era {era}: entered after the cutoff {after}, holds past the last bar {past} ({len(tr)} trades)")
        if era == "A" and (after or past):
            raise GuardStop(f"G8 era A reads {after} / {past}, not 0 / 0")
    # ---- the accounts: the deciding window first
    say(f"\n## ACCOUNTS — the deciding window {WINDOW[0]}..{WINDOW[1]} (start 1.0 in cash; his sizing; no margin)")
    sims = {}
    for name, arm, cfg in GRID:
        tr = trades_of(win, res, arm, map_b)
        sims[name] = rp.simulate(tr, cfg, cal_u, w0)
        account_lines(say, f"{name} ({arm}, {cfg.name})" + (" <- DECIDING" if name == "deciding" else ""), sims[name])
    ptr, pc = panel_trades_of(win, res, S, last_asof)
    sims["panel_exit"] = rp.simulate(ptr, CAP30, cal_u, w0)
    account_lines(say, f"panel_exit (the panel's own exits, cap_30; fills {dict(pc)})", sims["panel_exit"])
    # ---- THE DECIDING READOUT
    say(f"\n## THE DECIDING READOUT — vs QQQ / SPY over {WINDOW[0]}..{WINDOW[1]} (04_vs_market.py's formulas; price only, dividends excluded)")
    eqd = curve_on_window(sims["deciding"], w0, w1)
    st = market_stats(eqd, px["QQQ"][w0:w1 + 1], px["SPY"][w0:w1 + 1])
    ok, failed = bar_verdict(st)
    say(f"- DECIDING ({DECIDING[1]}, {DECIDING[2].name}): {fmt_stats(st)}")
    say(f"- HIS BAR (alpha t >= {BAR_ALPHA_T} AND total > QQQ AND total > SPY AND Sharpe > QQQ's): **{'PASS' if ok else 'FAIL'}**"
        + ("" if ok else " — not met: " + "; ".join(failed) + " -> OUR implementation (his 2026-10-23 rule), the beside readings name the part"))
    mrows = [dict(variant="deciding", window=f"{WINDOW[0]}..{WINDOW[1]}", **st, verdict="PASS" if ok else "FAIL")]
    say("- beside (deciding nothing):")
    for name in ("primary_exit_cap30", "speed_cap20", "primary_exit_cap20", "panel_exit"):
        s2 = market_stats(curve_on_window(sims[name], w0, w1), px["QQQ"][w0:w1 + 1], px["SPY"][w0:w1 + 1])
        ok2, _f = bar_verdict(s2)
        say(f"    {name}: {fmt_stats(s2)} -> bar {'met' if ok2 else 'not met'}")
        mrows.append(dict(variant=name, window=f"{WINDOW[0]}..{WINDOW[1]}", **s2, verdict="PASS" if ok2 else "FAIL"))
    # subsets of the deciding config
    for lab, sel in (("breakout-dated only", [e for e in win if e.setup in ("breakout", "both")]), ("EP-dated only", [e for e in win if e.setup == "EP"]),
                     ("without flickers", [e for e in win if not e.flicker]), ("first breaks only", [e for e in win if e.setup == "EP" or e.retrigger == 0])):
        sim = rp.simulate(trades_of(sel, res, SPEED_ARM, map_b), CAP30, cal_u, w0)
        s2 = market_stats(curve_on_window(sim, w0, w1), px["QQQ"][w0:w1 + 1], px["SPY"][w0:w1 + 1])
        say(f"    deciding config, {lab} (n = {len(sel)}): final {sim['final']:.3f} | {fmt_stats(s2)}")
        mrows.append(dict(variant=f"deciding/{lab}", window=f"{WINDOW[0]}..{WINDOW[1]}", **s2, verdict=""))
    for y in sorted({cal_u[w0].year, cal_u[w1].year} | {2020, 2021}):
        a, b = bisect.bisect_left(cal_u, date(y, 1, 1)), bisect.bisect_right(cal_u, date(y, 12, 31)) - 1
        a, b = max(a, w0), min(b, w1)
        if b - a < 20:
            continue                                  # a year the window barely touches carries no reading
        s2 = market_stats(curve_on_window(sims["deciding"], a, b), px["QQQ"][a:b + 1], px["SPY"][a:b + 1])
        say(f"    deciding config, {y} alone: {fmt_stats(s2)}")
        mrows.append(dict(variant="deciding", window=str(y), **s2, verdict=""))
    # ---- F5 (beside): the panel's clock on E against our fill minute
    say("\n## PANEL CLOCK vs OUR FILL (F5, beside, deciding nothing) — the deciding window's dated entries, ORH5 fill minute vs the panel's "
        "clock on E (same minute = ambiguous, not counted)")
    chk = [(ev, panel_vs_fill(ev, res[ev.eid]["entry"])) for ev in win if ev.eid in res]
    filled = [(ev, c) for ev, c in chk if c["fill_clock"]]
    for lab, sel in (("all", filled), ("breakout / both", [(e, c) for e, c in filled if e.setup in ("breakout", "both")]),
                     ("EP", [(e, c) for e, c in filled if e.setup == "EP"])):
        say(f"- {lab}: filled {len(sel)}; fill BEFORE a flat full snapshot on E {sum(1 for _e, c in sel if c['before_flat'])}; fill AFTER the "
            f"first holding snapshot on E {sum(1 for _e, c in sel if c['after_held'])} (held before 09:35: "
            f"{sum(1 for e, c in sel if c['after_held'] and e.orh5_infeasible)}); contradicting either way "
            f"{sum(1 for _e, c in sel if c['contradicts'])}; day-0 stop before the first holding snapshot on E "
            f"{sum(1 for _e, c in sel if c['day0_out_while_held'])}; day-0 stop on an entry first seen after E "
            f"{sum(1 for _e, c in sel if c['day0_out_before_later_sighting'])}")
    bad = {ev.eid for ev, c in filled if c["contradicts"]}
    sim_ok = rp.simulate(trades_of([e for e in win if e.eid not in bad], res, SPEED_ARM, map_b), CAP30, cal_u, w0)
    account_lines(say, f"deciding config WITHOUT the {len(bad)} contradicting fills", sim_ok)
    s2 = market_stats(curve_on_window(sim_ok, w0, w1), px["QQQ"][w0:w1 + 1], px["SPY"][w0:w1 + 1])
    ok2, _f = bar_verdict(s2)
    say(f"    {fmt_stats(s2)} -> bar {'met' if ok2 else 'not met'} (beside)")
    mrows.append(dict(variant="deciding/without panel-clock contradictions (F5)", window=f"{WINDOW[0]}..{WINDOW[1]}", **s2, verdict=""))
    pd.DataFrame(mrows).to_csv(os.path.join(OUT_DIR, "market.tsv"), sep="\t", index=False)
    # ---- per trade (tail first)
    say("\n## PER TRADE — the deciding window, the deciding arm (filled + mature; R at 0 / 0.1 / 0.2% exit slippage)")
    ET = trades_with_events(win, res, SPEED_ARM, map_b)
    T = [t for _e, t in ET]
    Tp = trades_of(win, res, PRIMARY_ARM, map_b)
    groups = [("all", T), ("breakout", [t for e, t in ET if e.setup in ("breakout", "both")]), ("EP", [t for e, t in ET if e.setup == "EP"]),
              ("flickers", [t for e, t in ET if e.flicker]), ("retriggers", [t for e, t in ET if e.setup != "EP" and e.retrigger == 1]),
              ("era A", [t for e, t in ET if e.era == "A"]), ("era B", [t for e, t in ET if e.era == "B"]),
              ("primary exit p33_s3_t10 (beside)", Tp), ("panel exits (beside)", ptr)]
    per_trade_table(say, groups)
    nm = [t for t in T if not t.mature]
    say(f"- not mature (open mark / degraded at the export's end or a break): {len(nm)}, booked R sum {sum(t.realized_r for t in nm):.1f}")
    # ---- beside: all years, the wider-window and undated additions
    say("\n## BESIDE — other spans and populations (deciding config; deciding nothing)")
    start_all = min(bisect.bisect_left(cal_u, date.fromisoformat(e.E)) for e in evs if e.decides and e.eid in res) if res else w0
    for lab, sel in (("deciding, all years 2017-2023", [e for e in evs if e.decides]),
                     ("deciding + dated wider than the cap", [e for e in evs if e.setup in SETUPS and not e.same_day_rebuy]),
                     ("deciding + undated (open fill, one-ADR stop)", [e for e in evs if e.decides or (e.setup == "undated" and not e.same_day_rebuy)]),
                     ("2022-11 .. 2023 tail alone", [e for e in evs if e.decides and e.E >= "2022-11-01"])):
        tr = trades_of(sel, res, SPEED_ARM, map_b)
        if not tr:
            say(f"- {lab}: no filled trade")
            continue
        sim = rp.simulate(tr, CAP30, cal_u, min(start_all, min(t.e_ci for t in tr)))
        account_lines(say, f"{lab} (n = {len(sel)}, filled {len(tr)})", sim)
    # ---- the same-day band (beside): era A breakout buy days in the window
    say(f"\n## SAME-DAY BAND (beside) — {BAND_DRAWS} draws, seed {SEED}, key `{BAND_KEY}`: other tl breakouts on his era-A breakout buy days")
    his_bk = [e for e in win if e.setup in ("breakout", "both") and e.era == "A"]
    his_by_date = Counter(e.E for e in his_bk)
    held = held_names_by_day(FILES["entries"], cal_u)
    DA = S["Ds"]["A"]
    qqqA = R.bars_for(DA, DA.tid["QQQ"])
    ctl_evs, ctl_by_date, excl = [], defaultdict(list), Counter()
    for r in S["pool_rows"].to_dict("records"):
        if r["ticker"] in held.get(r["E"], set()):
            excl["his_name_that_day"] += 1
            continue
        ev = HEvent(eid=-1 - len(ctl_evs), sym=r["ticker"], ticker=r["ticker"], era="A", setup="breakout", E=r["E"], D=r["D"],
                    pivot=float(r["pivot"]), adr20=float(r["adr20"]), base_id=r["base_id"], retrigger=int(r["retrigger"]), window_len=1,
                    flicker=False, decides=False, in_window=True, exit_hi="", still_held=False, year=int(r["E"][:4]), month=r["E"][:7])
        event_facts(ev, DA, qqqA, S["guards"]["A"], S["done"], S["files"], DA.cal)
        ctl_evs.append(ev)
        if ev.keep:
            ctl_by_date[ev.E].append(len(ctl_evs) - 1)
        else:
            excl[ev.history or ("break_pre" if ev.break_pre else ev.minutes_state)] += 1
    say(f"- pool: {len(S['pool_rows']):,} tl rows on {len(his_by_date)} days -> {sum(len(v) for v in ctl_by_date.values()):,} walkable control events "
        f"(per day min {min((len(v) for v in ctl_by_date.values()), default=0)}, median {int(np.median([len(v) for v in ctl_by_date.values()])) if ctl_by_date else 0}, "
        f"max {max((len(v) for v in ctl_by_date.values()), default=0)}); excluded " + ", ".join(f"{k} {v}" for k, v in sorted(excl.items())))
    cres, ctally = walk_all(S, [ev for ev in ctl_evs if ev.keep], say, "ctl")
    rng = np.random.default_rng([SEED, zlib_crc(BAND_KEY)])
    finals, yearly = [], defaultdict(list)
    his_sim = rp.simulate(trades_of(his_bk, res, SPEED_ARM, map_b), CAP30, cal_u, w0)
    draws_short = Counter()
    for _ in range(BAND_DRAWS):
        ids, c = rp.sample_control(his_by_date, ctl_by_date, rng)
        draws_short.update(c)
        tr = trades_of([ctl_evs[i] for i in ids], cres, SPEED_ARM, map_b)
        sim = rp.simulate(tr, CAP30, cal_u, w0)
        finals.append(sim["final"])
        for y, r in sim["yearly"].items():
            yearly[y].append(r)
    bs = rp.band_summary(finals)
    say(f"- his breakout-dated entries alone (n = {len(his_bk)}): final {his_sim['final']:.3f}; the band's final equity p5 {bs[5]:.3f} / p25 "
        f"{bs[25]:.3f} / p50 {bs[50]:.3f} / p75 {bs[75]:.3f} / p95 {bs[95]:.3f}; draws at or above his {100 * float(np.mean([f >= his_sim['final'] for f in finals])):.1f}%; "
        f"days short of events {draws_short['dates_short']}")
    for y in sorted(yearly):
        b2 = rp.band_summary(yearly[y])
        say(f"    {y}: his {rp.pct(his_sim['yearly'].get(y))} | band p5 {rp.pct(b2[5])} p50 {rp.pct(b2[50])} p95 {rp.pct(b2[95])}")
    pd.DataFrame({"draw": range(len(finals)), "final": finals}).to_csv(os.path.join(OUT_DIR, "account_band.tsv"), sep="\t", index=False)
    # ---- outputs
    rows = []
    for name, sim in sims.items():
        for ci, eq in zip(*sim["curve"]):
            rows.append({"config": name, "date": cal_u[ci].isoformat(), "equity": eq})
    pd.DataFrame(rows).to_csv(os.path.join(OUT_DIR, "account_his.tsv"), sep="\t", index=False)
    trows = []
    for ev in evs:
        w = res.get(ev.eid)
        if not w:
            continue
        en = w["entry"]
        base = dict(eid=ev.eid, era=ev.era, ticker=ev.ticker, E=ev.E, setup=ev.setup, decides=ev.decides, in_window=ev.in_window, flicker=ev.flicker,
                    retrigger=ev.retrigger, entry_status=en["status"], entry_reason=en.get("reason") or "", fill=en.get("fill"), stop=en.get("stop"),
                    fill_minute=en.get("fill_minute"), n_fwd=w["n_fwd"], break_cut=w["break_cut"])
        for arm, raw in w["arms"].items():
            trows.append({**base, "arm": arm, "status": raw["status"], "realized_r": raw["realized_r"], "sessions_held": raw["sessions_held"],
                          "legs": ";".join(f"{s}:{k}:{px:.4f}:{f:.4f}" for s, k, px, f in raw["events"] if k in rp.SELL_KINDS)})
        if not w["arms"]:
            trows.append({**base, "arm": "", "status": "", "realized_r": "", "sessions_held": "", "legs": ""})
    with gzip.open(os.path.join(OUT_DIR, "trades.tsv.gz"), "wt") as fh:
        pd.DataFrame(trows).to_csv(fh, sep="\t", index=False)
    say(f"\n## Outputs written under {OUT_DIR}: {', '.join(OUT_FILES)}")


def zlib_crc(key: str) -> int:
    import zlib
    return zlib.crc32(key.encode()) & 0xFFFFFFFF


# ═════════════════════════════════════════════════════════════════════════════════════════════
# main
# ═════════════════════════════════════════════════════════════════════════════════════════════
def main(argv=None) -> int:
    ap_ = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap_.add_argument("--dry-run", action="store_true")
    args = ap_.parse_args(argv)
    dry = args.dry_run
    say = rp.Say()
    if not dry:
        exo = existing_outputs()
        if exo:
            print(f"REFUSED: output(s) already on disk: {exo} (the replay runs once; after a STOPPED run, recovery = the fix, then delete the "
                  f"STOPPED file AND every file under {OUT_DIR} by hand, re-freeze if the module changed)", file=sys.stderr)
            return 2
    say(f"# #705 HOLDINGS 02 — his panel entries under his rules vs the market ({'DRY RUN: no minute file opened, no entry / exit function called, no outcome computed' if dry else 'THE REGISTERED REPLAY'})")
    say(f"# registration: {os.path.relpath(DOC, REPO)}")
    p0 = {k: rp.sha(v) for k, v in {**FILES, **CODE}.items() if k in PINNED}
    drift = [f"{k}: {p0[k]} (pinned {v})" for k, v in PINNED.items() if p0.get(k) != v]
    if drift:
        say("REFUSED: a pinned input changed: " + "; ".join(drift))
        say.write(DRY_PRINTOUT if dry else STOPPED)
        return 2
    say("- the first and second reads' pins re-checked (labels, events, candidates, exports, calendar, flags, the frozen modules and tests, "
        "the cb module = `runner.EXITPB_MODULE_SHA`): no drift")
    try:
        S = load_all(say)
        describe(say, S)
    except GuardStop as g:
        say(f"STOPPED: {g}")
        say.write(DRY_PRINTOUT if dry else STOPPED)
        return 3
    mdates = {tr: sorted({e.E for e in S["evs"] if e.keep and e.minutes_tree == tr}) for tr in MINUTES}
    p = pins(mdates)
    say("\n## Pins (sha256) — every value below goes under the doc's freeze marker line before the real run")
    for k, v in p.items():
        say(f"- {k}: {v}")
    miss = freeze_missing(DOC, p)
    say(f"- freeze record: {'every pin above is written under the freeze marker line' if not miss else 'NOT YET under the freeze marker line: ' + ', '.join(miss)}")
    if dry:
        say("\nDRY RUN COMPLETE: no minute file opened, no entry or exit function called, no outcome computed.")
        say.write(DRY_PRINTOUT)
        return 0
    if miss:
        say("REFUSED: the real replay runs only after the freeze commit records every pin above under the marker line.")
        say.write(STOPPED)
        return 2
    try:
        run_replay(S, say)
    except GuardStop as g:
        say(f"STOPPED: {g}")
        say.write(STOPPED)
        return 3
    except Exception:
        import traceback
        say("STOPPED (crash):\n" + traceback.format_exc())
        say.write(STOPPED)
        return 4
    say.write(PRINTOUT)
    return 0


if __name__ == "__main__":
    sys.exit(main())
