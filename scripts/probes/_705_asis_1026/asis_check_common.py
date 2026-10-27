#!/usr/bin/env python3
"""#705 as-is read, shared module for STEP 6b (03_check.py) and STEP 6c (04_band.py) — docs/analysis/cb_asis_reconstruction_prereg_2026-10-26.md
§4.1 step 6-7, §4.2, §4.3, §10. RULE-FREE BY CONSTRUCTION: no rule, setup name, pattern label or rule-library level enters; nothing is imported
from the four rule folders. The pinned step-5 / 6a modules (asis_common.py, 01_points.py, 02_captions.py) are loaded READ-ONLY through
importlib, exactly as 02_captions loads 01_points: their window reader, range engine (`side_rows`) and join (`join_position`) are called,
never copied and never edited (they sit under the freeze).

THE OPERATOR'S PRINCIPLE (2026-10-26): "stop trying to pigeon hole his trades, we're starting without any preconceptions, I want to reverse
eng his trades as they are, not as we want them to be and fit into our rules, that reconciliation comes later."

WHAT LIVES HERE: paths and printout names of 6b / 6c; the readers' v2 sheets (the R1 input: his own trade, ticker identified, price stated —
102 rows per the freeze record); the statement classes (fill / level, clean / garbled, the action's side); the symbol-and-day join through
02_captions' `join_position` (never by action or price); the RANGE ENGINE for the two controls (the same stock's window shifted -3..+3
sessions; another held name's window the same day) through 01_points' `side_rows` on shifted copies of the real `Window` and its two frames;
the §4.2 tolerance and containment; the pure scorers (R1 shares, the 25-point gap bar, R3 offsets, R4 implied moves, R5 side agreement) that
the tests drive on fixtures; the consequence-table labels quoted from §4.2 / §9; the pins, the run gates and the ledger stages.

READINGS where the plan is silent, ambiguous or contradicts itself (numbered on from 02_captions.py's R40-R61; the main loop decides):
  R62 [the statement's day] The v2 sheet carries a DAY CLASS (stream_day / stated_earlier / implied_recent / approx_earlier / unstated), not a
      resolved date, and the readers were told to read the words only. The join day is the STREAM DATE for every class; the one-session
      tolerance of §4.1 step 6 absorbs "yesterday"; "friday" said on a Wednesday lands `none` and is counted. No date is inferred here from
      the words (an inference by this module would be a second, unblinded reader). R3's split by day class is the measurement of this.
  R63 [fill or level, §11] Only fills enter R1. A FILL = an event action (buy, add, shorted, sell_part, sell_all, sell_unspec, stopped,
      covered) whose stated price is of kind `entry` or `exit`; `holding` with an `entry` price is a past fill and is IN. A LEVEL = the action
      `stop_level` or `result`, or a price of kind `stop` or `other` under any action — a stop-out ("got stopped out, it hit 428") states
      the level he set, and the fill may differ, so the stricter reading keeps it BESIDE. Levels are scored the same way, outside the
      primary count, and kept for step 8.
  R64 [clean] `price_garbled` is a Y-only flag in the v2 wording ("Y if the number is ambiguous"); blank and N are clean. Garbled rows are the
      §4.2 "R1 garbled" line, outside the primary count.
  R65 [the §9 floor — on the SCORED n] "under 100 T1: R1's gap bar cannot be told from noise ... marked not decidable". §4.2's own reason
      for the 25-point bar is the n of the statements SCORED ("the n (100-250 statements) tells from noise ... a 95% interval on a share near
      70% is about ±9 points"), so the floor is read on the primary count that enters the bar, never on the input count: the bar is NOT
      DECIDABLE under 100 scored statements, the would-be verdict carried beside (review F1; the first build read it on the freeze record's
      102 and would have printed a PASS on 17 statements, ±30 points). Three T1 readings are printed beside each other: the freeze record's
      102 (own + ticker Y + price stated), §4.1's own tier words (an EVENT action — buy / sell / stop / partial / short / cover — and a day
      class that names a day), and that count with `approx_earlier` and with `stop_level` added (the review's reading of "stop"). Every
      reading sits under 100. An override to the looser reading is the main loop's, written into the ledger before --run; 04's gate (R79)
      refuses on a not-decidable R1 as it stands.
  R85 [the primary, by the reader's labels only] A statement enters the primary count when its price kind MATCHES its action's side
      (buy / add / shorted with an `entry` price; sell_part / sell_all / sell_unspec / stopped / covered with an `exit` price) AND its day class
      names a day (stream_day / stated_earlier / implied_recent). `holding` + entry (a past fill: the stream date is not the fill's day), an
      entry price on a sale action or an exit price on a buy action (the price is of the OTHER side's window), and `unstated` / `approx_earlier`
      days (the stream date has no stated meaning) are scored the same way on lines BESIDE, never in the bar (review F2: 5 of the first
      build's 17 primary statements were past entry prices joined on the stream date against whichever window sat within a session of it).
      The choice is by the labels, never by where the statement landed.
  R66 [control (a)] The shifted window is the real `Window` with `lo`, `hi` AND both frames' dates moved k sessions (k in -3..+3, never 0),
      clocks and contexts kept, re-typed, re-reached and re-ranged by 01_points' own functions — so a same-day clock bracket stays a clock
      bracket on the shifted day (shifting the dates alone would widen the control to a full session and flatter the gap). The control share
      is the mean over the shifts that have a range (a shift onto a session with no bar is counted, never scored).
  R67 [control (b)] "the window of ANOTHER name he held that same day": every other panel symbol whose window the SAME join rule returns for
      the same day (symbol swapped, day kept: a unique window within one session) — not a window elsewhere in that name's hold, which would
      make the control look random and flatter the gap. The share is the mean over those names; a statement with no such name is counted,
      never scored.
  R68 [tolerance] §4.2: inside if within max(1% of price, 10% of that session's range, $0.05) of the range edge, in RAW price. "That session"
      = the join day's session (the shifted day for a shift, the same day on the other name for the cross control), its daily high-low read
      from the record's export and put in raw price with that session's factor; the join day outside the window's sessions takes the nearest
      reachable session; no bar at all -> max(1%, $0.05).
  R69 [ties] A join that ties (`ambiguous`: two windows at the same distance, most often one position's buy and sale on a day-trade day) names
      no side and is scored in NEITHER R1 nor R5 (the plan: never by action, never by price); counted and listed.
  R70 [R3's population] Only the price batch is labelled under v2 (the rest batches wait on R1 per the freeze record), so R3 runs on every
      own-trade, ticker-identified row of the v2 sheets (194), not on T2; its n is printed and the T2 read is named as not yet done.
  R71 [R4] T1b needs a share count AND a dollar result on one statement: 2 rows carry both. Printed with its n; the 70% bar is not read at
      that n (the plan's own posture for a tier under its expected n, §9).
  R72 [R5's map] stopped / sell_part / sell_all / sell_unspec / covered agree with a SALE window; buy / add / shorted with a BUY window
      (§4.2 R5 verbatim); holding / stop_level / result carry no side and are excluded and counted; ties excluded (R69).
  R73 [one side, several prices] Several clean fill statements on one (position, side) anchor it on their MEAN; the side is flagged
      `anchors_differ` when they spread by more than the tolerance (the statements are listed). Two caption hits of one utterance (the
      same price seconds apart) count as two statements in R1, as the plan counts statements; the distinct (position, side, price) count is
      printed beside.
  R74 [anchors and the ledgered ranges.tsv] ranges.tsv is a ledgered output of step 5 (`stated_price` / `stated_kind` / `stated_outside_range`
      were left blank for step 6 to fill); writing into it would fail `ledger_verify` and every later gate. The anchors are written to
      check_r1_r5.tsv (eid, side, raw price, bar-space price = raw / raw_factor, kind, `stated_outside_range`); the three columns stay blank.
  R75 [6c in bar space] The account path multiplies prices of two windows that may straddle a split; the bars are split-adjusted to one
      date, so returns are read in BAR space (adjusted entry vs adjusted exit) and an anchor is converted with the side's `raw_factor`.
  R76 [6c sizing — a constant mix, marked daily] "equal weight across the names held at the same time, full account (exposure 1.0)" is read
      literally: on EVERY session the account is exposure x (1 / N) in each of the N names held on it (held = buy window end <= session <=
      sale window end), so the money deployed is exposure x account on every session by construction, never more. Each trade is MARKED by
      session from the record's daily closes (the buy side's export, bar space): the entry session at its close over the entry price, the
      interior sessions at their closes, the exit session at the exit price; a session with no close carries the previous mark; a trade with
      no close at all spreads its return geometrically over its hold (counted). The account compounds by session on the mean of the open
      names' daily returns (a short's is negated: a constant-dollar short, which is why its realised return is near, not exactly, 1 - exit /
      entry). The review (F4) found the first build sized each entry from the WHOLE account at its entry session and never netted the money
      already committed, so staggered entries deployed about 2.3x. N counts EVERY both-sided position held on the session, the 252 with no
      range on a side included (the panel shows them held; their return is unknown and enters as 0 — a floor, as 6c is); the 26 one-sided
      positions have no exit and are out. Entry session = the buy window's END (the first frame showing it: by then he held it), exit
      session = the sale window's END.
  R77 [6c daily-only middle] A side with no minute bar has no `avg_traded_price_raw` in ranges.tsv; its middle is each reachable session's
      typical price (high + low + close) / 3 weighted by the session's volume (§4.3), computed from the record's export, flagged.
  R78 [6c side] A position is SHORT when a joined own-trade statement on it says so (`side` = short, or the action shorted / covered) — from
      03's output when present; long otherwise, the share by statement printed (§4.3).
  R79 [6c gate] "if 6b fails, 6c is not read at all": 04's --run refuses unless 03's run printout exists and carries the PASS labels of R1
      and R5. A not-decidable R1 (R65) also refuses: the plan gives no branch for it, so it is the main loop's call, not this module's.
      The 6c DRY RUN prints the sha of 03's run printout and of check_r1_r5.tsv as it saw them (ABSENT before 6b ran), and the gate refuses
      a dry run that saw either ABSENT or saw a different file than the one on disk (review F3: a 6c dry run made BEFORE 6b, pinned, would
      have opened the gate once 6b's files appeared). The order is therefore 03 --run, then 04 --dry-run AGAIN, 04 --print-pins, paste,
      04 --run. Any pin a 6b / 6c stage adds (the sheets, the wording, step 5's outputs, 6a's joins, the modules, the printouts, 6b's
      outputs) whose value is ABSENT refuses the run too — an ABSENT pin passes the freeze check trivially because the step-5 record
      already put the word below the marker.
  R80 [6c's 15 points] His dated figures are the §4.3 list, typed here as (date, low %, high %) with an open top for "or more"; a point is
      scored as the distance from the path's year-to-date return to the nearest end of his range (0 inside it).
  R82 [mid-hold statements, beside] 29 of the 102 R1-input statements fall INSIDE a hold (the day lies between the position's first and last
      window: "I bought X at 42" said while still holding) and the one-session join returns `none` for them by construction (the 102 split:
      joined 33 / tie 14, of which 9 one position's buy and sale / mid-hold 29 / another date 20 / never on the panel 6; the first build's
      report quoted the 194-row counts here — review F5). They stay out of the bar; a readout BESIDE scores the price against BOTH of that
      position's windows (buy and sale, each printed), never choosing by action — so the operator can see whether the mid-hold prices sit
      in the entry window without the join being widened after the fact.
  R86 [outside flags, two columns] `stated_outside_range` is PER STATEMENT (this statement's own price outside its window's range); the
      side's flag — any primary statement on the (position, side) outside — is `side_outside_range` and travels with the anchor (review F9:
      one flag for both marked an inside statement as outside when a neighbour on the same side fell out).
  R87 [the side of a position, in 6c] A position is read SHORT from any own-trade statement that says so and NAMES the position — a uniquely
      joined one or one placed BESIDE it (mid-hold, R82; a one-position tie, R83): the side is a fact about the position, not about the
      window (review F9: the 5 mid-hold shorted / covered statements in the R1 input alone set no position short in the first build).
  R88 [other_date, beside R3] The one-session join cannot show §4.2's R3 failure case ("a spread wider than the windows"): a statement
      further than a session from every window of its name is `other_date` and never joined. A histogram BESIDE, marked secondary, gives
      the signed distance in sessions from each `other_date` statement's day to the NEAREST window of its name (any distance), by day
      class (review F7).
  R83 [one-position ties, beside] A tie between one position's buy and sale windows (a day-trade day) is `ambiguous` (R69); the same beside
      readout prints the price against each of the two windows.
  R84 [the control share] Each statement's controls are averaged FIRST and the statement means are averaged (`control_share`): a statement
      with twelve held names weighs the same as one with one. Identical for the six shifts (every statement has six); it matters for the
      cross names, whose count varies by day.
  R81 [what the dry runs never compute] 03's dry run never calls the containment or the scorers (not merely unprinted); 04's never
      compounds an account. Both print inputs, populations, the join's counts and the pins only.

No network, no model client, no DB, no subagent. Nothing is opened at import.
"""
from __future__ import annotations

import collections
import copy
import csv
import importlib.util
import os
import sys
from dataclasses import replace as dc_replace

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))


def _load_module(name: str, path: str):
    """Load a pinned module read-only under a private name (02_captions' pattern); re-use the loaded one when it is this file's."""
    if name in sys.modules and getattr(sys.modules[name], "__file__", "") == path:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


C = _load_module("asis_common", os.path.join(HERE, "asis_common.py"))
P = _load_module("asis_points_for_check", os.path.join(HERE, "01_points.py"))
CAP = _load_module("asis_captions_for_check", os.path.join(HERE, "02_captions.py"))

Say, Claims, table, pct = CAP.Say, CAP.Claims, CAP.table, CAP.pct
GuardStop = C.GuardStop

# ---- paths ---------------------------------------------------------------------------------------------------------------------------------
SHEETS_FILLED = os.path.join(C.OUT_DIR, "sheets_filled")
V2_SHEETS = tuple(os.path.join(SHEETS_FILLED, f"reader1_t1_v2_part{k}.tsv") for k in (1, 2, 3))
WORDING_V2 = os.path.join(HERE, "reader_wording_v2.txt")
RANGES = C.OUTPUTS["ranges"]
COVERAGE = C.OUTPUTS["coverage"]
JOINS_6A = os.path.join(C.OUT_DIR, "joins.tsv")
OUT_6B = {"check_r1_r5": os.path.join(C.OUT_DIR, "check_r1_r5.tsv"), "control_ranges": os.path.join(C.OUT_DIR, "control_ranges.tsv")}
OUT_6C = {"band_by_session": os.path.join(C.OUT_DIR, "band_by_session.tsv"), "band_at_dates": os.path.join(C.OUT_DIR, "band_at_dates.tsv")}
P03 = {"dry": os.path.join(HERE, "03_check_dryrun.txt"), "run": os.path.join(HERE, "03_check.txt"), "refused": os.path.join(HERE, "03_check.refused.txt"),
       "pins": os.path.join(HERE, "03_check_pins.txt")}
P04 = {"dry": os.path.join(HERE, "04_band_dryrun.txt"), "run": os.path.join(HERE, "04_band.txt"), "refused": os.path.join(HERE, "04_band.refused.txt"),
       "pins": os.path.join(HERE, "04_band_pins.txt")}
MODULE_FILES_6B = ("asis_common.py", "01_points.py", "02_captions.py", "asis_check_common.py", "03_check.py", "forbidden_identifiers.txt",
                   os.path.join("inventory", "captions_inventory.py"))
MODULE_FILES_6C = MODULE_FILES_6B + ("04_band.py",)
STAGE_6B, STAGE_6C = "step6b_", "step6c_"

# ---- constants of §4.2 / §4.3 ---------------------------------------------------------------------------------------------------------------
SPAN = P.SPAN
SHIFTS = (-3, -2, -1, 1, 2, 3)
GAP_BAR_POINTS = 25.0            # R1: real share minus each control's share, in percentage points
R5_BAR = 0.90
R4_BAR = 0.70
T1_FLOOR = 100                   # §9: under 100 T1 the gap bar is not decidable (R65)
TOL_PCT, TOL_RANGE, TOL_ABS = 0.01, 0.10, 0.05
EVENT_ACTIONS = ("buy", "add", "shorted", "sell_part", "sell_all", "sell_unspec", "stopped", "covered")
SIDE_OF_ACTION = {"buy": "buy", "add": "buy", "shorted": "buy", "sell_part": "sale", "sell_all": "sale", "sell_unspec": "sale",
                  "stopped": "sale", "covered": "sale"}          # R72, §4.2 R5 verbatim
NO_SIDE_ACTIONS = ("holding", "stop_level", "result", "none")
FILL_KINDS = ("entry", "exit")
KIND_OF_SIDE = {"buy": "entry", "sale": "exit"}                  # R85: the price kind that matches the action's side
DAY_CLASSES = CAP.DAY_CLASSES
NAMED_DAY_CLASSES = ("stream_day", "stated_earlier", "implied_recent")     # R85: the classes that name a day; unstated / approx_earlier do not
YEAR_BLOCKS = (("2020", ("2020",)), ("2021-22", ("2021", "2022")))

# ---- the consequence table, quoted from §4.2 (and §9's floor row); the test checks each appears verbatim in the frozen doc ------------------
LABEL_R1_PASS = "R1 passes its gap bar on both controls → the windows are accepted at ballpark"
LABEL_R1_FAIL = "R1 fails on either control → stop, find the cause (window / alias / clock) in the listed failures by bracket type, fix, re-run once as a disclosed event"
LABEL_R5_FAIL = "R5 under 90% → the same"
LABEL_R1_NOT_DECIDABLE = "under 100 T1: R1's gap bar cannot be told from noise; the read reports the n and the bar is marked not decidable"
LABEL_OUTSIDE_KEPT = "the trades whose stated price falls outside our range are KEPT, anchored on the stated price"
LABEL_DENSITY_ND = ("the density check (§3.3) says \"where he acts\" is not decidable → step 7 reads the band and the continuous chart measures "
                    "only, and the point description is dropped")
LABEL_6C_FLOOR = "So 6c is a floor, never a verify."
CONSEQUENCE_LABELS = (LABEL_R1_PASS, LABEL_R1_FAIL, LABEL_R5_FAIL, LABEL_R1_NOT_DECIDABLE, LABEL_OUTSIDE_KEPT, LABEL_DENSITY_ND, LABEL_6C_FLOOR)
LINE_R1 = "R1 GAP BAR: "          # the run printout's verdict lines (04's gate reads them, R79)
LINE_R5 = "R5 BAR: "
LINE_6B_ARTEFACTS = "- 6b artefacts: "    # 04's dry-run line the 6c gate checks against the files on disk (R79, review F3)
VERDICT_PASS, VERDICT_FAIL, VERDICT_ND = "PASS", "FAIL", "NOT DECIDABLE"
NO_BAR = "beside (no bar)"        # the verdict column of every R1 row that is not the primary line (§4.2: "no separate bar"; review F6)

# ---- his 15 dated figures (§4.3; R80): (date, low %, high % or None for an open top) ----------------------------------------------------
HIS_DATED_POINTS = (
    ("2020-06-09", 150.0, None), ("2020-07-20", 200.0, None), ("2020-11-19", 300.0, 300.0), ("2020-12-07", 500.0, 700.0),
    ("2020-12-09", 710.0, 710.0), ("2020-12-22", 800.0, 900.0),
    ("2021-02-09", 60.0, 60.0), ("2021-02-18", 60.0, 60.0), ("2021-02-23", 100.0, 100.0), ("2021-02-24", 90.0, 90.0),
    ("2021-03-10", 100.0, 120.0), ("2021-03-12", 120.0, 120.0), ("2021-03-24", 90.0, 100.0), ("2021-05-06", 100.0, 100.0),
    ("2022-04-14", 15.0, 15.0),
)
DRAWDOWN_2021 = ("2021-03-12", "2021-03-24")
EXPOSURES = (1.0, 0.5, 1.5)


# ═════════════════════════════════════════════════════════════════════════════════════════════
# the readers' sheets and the statement classes
# ═════════════════════════════════════════════════════════════════════════════════════════════
def read_sheets(paths=V2_SHEETS) -> list:
    """Every row of the v2 price batch, with `part` (the sheet's basename) added; the data columns are read, never rewritten."""
    rows = []
    for p in paths:
        with open(C.checked(p), encoding="utf-8") as fh:
            for r in csv.DictReader(fh, delimiter="\t"):
                r["part"] = os.path.basename(p)[:-4]
                rows.append(r)
    return rows


def _s(r: dict, c: str) -> str:
    return (r.get(c) or "").strip()


def classify(r: dict) -> dict:
    """The statement's classes from the reader's labels alone (R62-R64): own / ident / action / side_of_action / day class / priced /
    garbled / fill-or-level / price (raw, as he saw it)."""
    own = _s(r, "his_trade").lower() == "y"
    ident = _s(r, "ticker_ident").lower()
    ident = {"y": "Y", "amb": "amb", "n": "N"}.get(ident, ident)
    action = _s(r, "action").lower()
    kind = _s(r, "price_kind").lower()
    priced = _s(r, "price_stated").upper() == "Y"
    price = CAP.parse_price(_s(r, "price_value")) if priced else None
    garbled = _s(r, "price_garbled").upper() == "Y"
    if not priced or price is None:
        fill = ""
    elif action in EVENT_ACTIONS and kind in FILL_KINDS:
        fill = "fill"
    elif action == "holding" and kind == "entry":
        fill = "fill"
    else:
        fill = "level"
    side_of_action = SIDE_OF_ACTION.get(action, "")
    day_class = _s(r, "date_pinnable").lower()
    return {"own": own, "ident": ident, "ticker": CAP.norm_ticker(_s(r, "ticker")) if ident in ("Y", "amb") else "",
            "action": action, "side_of_action": side_of_action, "side_said": _s(r, "side").lower(),
            "day_class": day_class, "priced": priced, "price": price, "garbled": garbled, "price_kind": kind,
            "fill": fill, "matched": bool(side_of_action) and KIND_OF_SIDE[side_of_action] == kind,        # R85
            "day_named": day_class in NAMED_DAY_CLASSES,                                                    # R85
            "shares": CAP.parse_price(_s(r, "shares")), "dollar_result": _dollars(_s(r, "dollar_result"))}


def is_primary_class(k: dict) -> bool:
    """R85: a clean FILL whose price kind matches the action's side, on a day class that names a day (the statement's labels alone)."""
    return k["fill"] == "fill" and not k["garbled"] and k["matched"] and k["day_named"]


def t1_readings(ks: list) -> dict:
    """R65: the T1 count under each reading, over the R1 input's classes: the freeze record's (every priced own statement, ticker Y);
    §4.1's tier words (an event action + a day class that names a day); the same with approx_earlier; the same with stop_level too."""
    ev = [k for k in ks if k["action"] in EVENT_ACTIONS]
    return {"freeze_record": len(ks),
            "s41_words": sum(1 for k in ev if k["day_named"]),
            "s41_with_approx": sum(1 for k in ev if k["day_named"] or k["day_class"] == "approx_earlier"),
            "s41_with_approx_and_stop_level": sum(1 for k in ks if (k["action"] in EVENT_ACTIONS or k["action"] == "stop_level")
                                                  and (k["day_named"] or k["day_class"] == "approx_earlier"))}


def _dollars(x: str) -> "float | None":
    v = CAP.parse_price(x)
    if v is None:
        return None
    return -v if x.strip().startswith("-") or "loss" in x.lower() else v


def r1_input(rows: list) -> list:
    """The R1 input of the freeze record: his own trade + ticker identified (Y) + price stated. -> [(row, classes)]."""
    out = []
    for r in rows:
        k = classify(r)
        if k["own"] and k["ident"] == "Y" and k["priced"]:
            out.append((r, k))
    return out


def own_identified(rows: list) -> list:
    """Every own-trade row with the ticker identified (R70: R3's and R5's population)."""
    return [(r, k) for r in rows for k in [classify(r)] if k["own"] and k["ident"] == "Y"]


def statement_day(r: dict) -> str:
    """R62: the join day is the stream date for every day class."""
    return _s(r, "stream_date")


# ═════════════════════════════════════════════════════════════════════════════════════════════
# the join (02_captions' rule: symbol and day only), the windows and ranges.tsv
# ═════════════════════════════════════════════════════════════════════════════════════════════
def read_ranges(path: str = None) -> dict:
    """{(eid, side): row} of ranges.tsv (strings as written)."""
    out = {}
    with open(C.checked(path or RANGES), encoding="utf-8") as fh:
        for r in csv.DictReader(fh, delimiter="\t"):
            out[(int(r["eid"]), r["side"])] = r
    return out


def windows_tuple(ws: list) -> list:
    """01_points Windows -> 02_captions' window tuples [(eid, side, sym, lo, hi)]."""
    return [(w.eid, w.side, w.sym, w.lo, w.hi) for w in ws]


def join(ticker: str, day: str, by_sym: dict, S) -> dict:
    """The symbol-and-day join of §4.1 step 6 through 02_captions.join_position (never the action, never the price)."""
    return CAP.join_position(ticker, day, by_sym, S)


def nearest_window_offset(ticker: str, day: str, by_sym: dict, S) -> "int | None":
    """R88: the signed distance in sessions from `day` to the NEAREST window of `ticker` at any distance (negative = the day lies before the
    window's start, positive = after its end, 0 = inside); None when the name has no window."""
    di = S.le(day)
    best = None
    for _eid, _side, lo, hi in by_sym.get(ticker, ()):
        a, b = sorted((S.ge(lo), S.le(hi)))
        off = 0 if a <= di <= b else (di - a if di < a else di - b)
        if best is None or abs(off) < abs(best):
            best = off
    return best


def cross_names(ticker: str, day: str, by_sym: dict, S) -> list:
    """R67: every OTHER panel symbol whose window the same join rule returns uniquely for `day`. -> [(sym, eid, side)]."""
    out = []
    for sym in sorted(by_sym):
        if sym == ticker:
            continue
        j = CAP.join_position(sym, day, by_sym, S)
        if j["status"] == "unique":
            out.append((sym, j["eid"], j["side"]))
    return out


# ═════════════════════════════════════════════════════════════════════════════════════════════
# the range engine: 01_points' own functions on copies of the real window (R66) and on another name (R67)
# ═════════════════════════════════════════════════════════════════════════════════════════════
def shifted_window(w, k: int, S):
    """The real Window with lo, hi and both frames' dates moved k sessions (clocks and contexts kept); None when a date leaves the calendar
    or the seal."""
    lo_i, hi_i = S.le(w.lo) + k, S.le(w.hi) + k
    if lo_i < 0 or hi_i >= len(S.cal):
        return None
    frames = []
    for f in (w.earlier, w.later):
        fi = S.le(f.date) + k
        if fi < 0 or fi >= len(S.cal):
            return None
        frames.append(dc_replace(f, date=S.date(fi)))
    w2 = copy.copy(w)
    w2.lo, w2.hi, w2.earlier, w2.later = S.date(lo_i), S.date(hi_i), frames[0], frames[1]
    w2.reach, w2.flags, w2.raw = [], set(), {}
    w2.wide = False
    w2.bracket = P.type_bracket(w2, S)
    w2.year, w2.in_span = int(w2.hi[:4]), SPAN[0] <= w2.hi <= SPAN[1]
    return w2


class RangeEngine:
    """Ranges over a Window through 01_points' `reachable` -> `assign_export` -> `raw_factors` -> `side_rows` (read-only; the candidates it
    builds are discarded). Needs the dict 01_points.load_all returns."""

    def __init__(self, L: dict):
        self.L, self.S, self.bars = L, L["S"], L["bars"]
        self.tally, self.nr = collections.Counter(), collections.Counter()
        self.by_key = {(w.eid, w.side): w for w in L["buys"] + L["sales"]}

    def window(self, eid: int, side: str):
        return self.by_key.get((int(eid), side))

    def range_row(self, w) -> dict:
        """The ranges.tsv row of `w` as side_rows writes it (the panel left out: a shifted frame has no panel cell)."""
        P.reachable(w, self.S)
        P.assign_export(w, self.bars, self.tally)
        P.raw_factors(w, self.bars, self.L["rawmap"], self.L["splits"], self.tally)
        rng, _cov, _cands = P.side_rows(w, self.bars, {}, self.S, self.tally, self.nr)
        return rng

    def session_range_raw(self, w, day: str) -> "float | None":
        """R68: the join day's daily high-low in raw price (the nearest reachable session when the day is outside the window)."""
        if not w.reach:
            return None
        ds = [d for d, _, _ in w.reach]
        d = day if day in ds else min(ds, key=lambda x: abs(self.S.le(x) - self.S.le(day)))
        b, ix = self.bars.daily(w.export, w.bar_sym)
        if b is None or d not in ix:
            return None
        j = ix[d]
        fac = w.raw.get(d, (1.0, "missing"))[0]
        return (C.fnum(b.h[j]) - C.fnum(b.l[j])) * fac

    def shifted(self, w, k: int) -> "dict | None":
        w2 = shifted_window(w, k, self.S)
        return None if w2 is None else {"window": w2, "row": self.range_row(w2)}


def raw_range(row: dict) -> "tuple | None":
    """(lo_raw, hi_raw) of a ranges.tsv row, None when the side has no range."""
    lo, hi = row.get("range_lo_raw", ""), row.get("range_hi_raw", "")
    if lo in ("", None) or hi in ("", None):
        return None
    return float(lo), float(hi)


# ═════════════════════════════════════════════════════════════════════════════════════════════
# the pure scorers (tests drive these on fixtures)
# ═════════════════════════════════════════════════════════════════════════════════════════════
def tolerance(price: float, day_range_raw: "float | None") -> float:
    """§4.2: max(1% of price, 10% of that session's range, $0.05); no session range -> max(1%, $0.05) (R68)."""
    parts = [TOL_PCT * price, TOL_ABS]
    if day_range_raw is not None and day_range_raw > 0:
        parts.append(TOL_RANGE * day_range_raw)
    return max(parts)


def contains(price: float, lo: float, hi: float, tol: float) -> bool:
    return (lo - tol) <= price <= (hi + tol)


def share(flags: list) -> "float | None":
    """The share of True in a list of booleans (None when empty), in PERCENT."""
    return None if not flags else 100.0 * sum(1 for f in flags if f) / len(flags)


def control_share(per_statement: list) -> "float | None":
    """The mean over statements of each statement's own control share (each statement's controls averaged first, so a statement with many
    held names weighs the same as one with one); statements with no control are left out."""
    vals = [share(fl) for fl in per_statement if fl]
    return None if not vals else float(np.mean(vals))


def gap_bar(real: "float | None", shifted: "float | None", cross: "float | None", n_scored: int, floor: int = T1_FLOOR) -> dict:
    """R1's bar (§4.2): real minus shifted >= 25 points AND real minus cross >= 25 points. -> {verdict, gap_shifted, gap_cross, label}.
    NOT DECIDABLE when the SCORED n < floor (R65) or a share is missing; the would-be verdict is carried beside."""
    gs = None if real is None or shifted is None else real - shifted
    gc = None if real is None or cross is None else real - cross
    if gs is None or gc is None:
        return {"verdict": VERDICT_ND, "gap_shifted": gs, "gap_cross": gc, "label": LABEL_R1_NOT_DECIDABLE, "would_be": None}
    would = VERDICT_PASS if (gs >= GAP_BAR_POINTS and gc >= GAP_BAR_POINTS) else VERDICT_FAIL
    if n_scored < floor:
        return {"verdict": VERDICT_ND, "gap_shifted": gs, "gap_cross": gc, "label": LABEL_R1_NOT_DECIDABLE, "would_be": would}
    return {"verdict": would, "gap_shifted": gs, "gap_cross": gc, "label": LABEL_R1_PASS if would == VERDICT_PASS else LABEL_R1_FAIL,
            "would_be": would}


def r5_agreement(items: list) -> dict:
    """items: [(action, landed side)] of uniquely joined own-trade statements. Actions with no side are excluded and counted (R72)."""
    scored = [(a, s) for a, s in items if a in SIDE_OF_ACTION]
    agree = sum(1 for a, s in scored if SIDE_OF_ACTION[a] == s)
    n = len(scored)
    rate = (agree / n) if n else None
    return {"n": n, "agree": agree, "rate": rate, "excluded_no_side": len(items) - n,
            "verdict": VERDICT_ND if rate is None else (VERDICT_PASS if rate >= R5_BAR else VERDICT_FAIL),
            "misses": [(a, s) for a, s in scored if SIDE_OF_ACTION[a] != s]}


def day_offsets(day: str, lo: str, hi: str, S) -> tuple:
    """R3: (stated day - window start, stated day - window end) in sessions."""
    di = S.le(day)
    return di - S.le(lo), di - S.le(hi)


def implied_move(dollar_result: float, shares: float, entry_price: float) -> "float | None":
    """R4: dollar result / shares as % of the entry price."""
    if not shares or not entry_price:
        return None
    return 100.0 * (dollar_result / shares) / entry_price


def outcome_band(buy_lo: float, buy_hi: float, sale_lo: float, sale_hi: float) -> tuple:
    """R4: the trade's band of outcomes in % (long): worst = sell at the sale low after buying at the buy high, best the reverse."""
    return 100.0 * (sale_lo / buy_hi - 1.0), 100.0 * (sale_hi / buy_lo - 1.0)


# ═════════════════════════════════════════════════════════════════════════════════════════════
# 6c: the account path (R75-R77, R80)
# ═════════════════════════════════════════════════════════════════════════════════════════════
def marks_to_daily(marks: list, side: str = "long") -> dict:
    """R76: [(session, value multiple of the entry price)] in session order -> {session: the trade's return on that session}, the first
    against 1.0 (the entry price). A short's returns are negated (a constant-dollar short)."""
    out, prev = {}, 1.0
    for d, v in marks:
        r = (v / prev - 1.0) if prev else 0.0
        out[d] = -r if side == "short" else r
        prev = v
    return out


def geometric_daily(ret: float, hold_sessions: list, side: str = "long") -> dict:
    """R76's fallback (and the fixtures'): a trade's whole return spread geometrically over its hold sessions, so the marks compound to
    1 + ret on the exit session; a short's negated. ret <= -1 is held at -1 (a wiped-out name)."""
    n = max(1, len(hold_sessions))
    g = (max(1.0 + ret, 0.0)) ** (1.0 / n)
    marks = [(d, g ** (i + 1)) for i, d in enumerate(hold_sessions)]
    return marks_to_daily(marks, side)


def account_path(trades: list, sessions: list, exposure: float = 1.0) -> dict:
    """R76: trades: [{eid, entry_session, exit_session, daily}] with `daily` = {session: the trade's return on that session} (signed for a
    short; {} for a held name with no range, which takes a slot and returns 0). sessions: the ordered session list the path is compounded
    on (ISO). -> {session: account}, 1.0 before the first session. On every session the account holds exposure x (1 / N) in each of the N
    names held on it (entry_session <= session <= exit_session), so the money deployed is exposure x account by construction; the account
    moves by exposure x the mean of the open names' daily returns, floored at a wiped-out 0."""
    idx = {d: i for i, d in enumerate(sessions)}
    held = np.zeros(len(sessions), dtype=int)
    sum_r = np.zeros(len(sessions), dtype=float)
    for t in trades:
        a, b = idx[t["entry_session"]], idx[t["exit_session"]]
        held[a:b + 1] += 1
        for d, r in (t.get("daily") or {}).items():
            j = idx.get(d)
            if j is not None and a <= j <= b:
                sum_r[j] += r
    acct, path = 1.0, {}
    for i, d in enumerate(sessions):
        if held[i] > 0:
            acct = max(0.0, acct * (1.0 + exposure * sum_r[i] / held[i]))
        path[d] = acct
    return path


def deployed_share(trades: list, sessions: list, exposure: float = 1.0) -> dict:
    """R76's invariant, for the tests: {session: the money deployed as a share of the account} = exposure on every session with a name
    held, 0 otherwise (the constant mix never nets to more)."""
    idx = {d: i for i, d in enumerate(sessions)}
    held = np.zeros(len(sessions), dtype=int)
    for t in trades:
        held[idx[t["entry_session"]]:idx[t["exit_session"]] + 1] += 1
    return {d: (exposure if held[i] > 0 else 0.0) for i, d in enumerate(sessions)}


def ytd(path: dict, sessions: list, day: str) -> "float | None":
    """The path's year-to-date return in % at `day` (the last session <= day), against the last session of the prior year (1.0 when none)."""
    at = [d for d in sessions if d <= day]
    if not at or at[-1] not in path:
        return None
    base = [d for d in sessions if d < day[:4] + "-01-01"]
    b = path[base[-1]] if base and base[-1] in path else 1.0
    return 100.0 * (path[at[-1]] / b - 1.0) if b else None


def distance_to_his(value: "float | None", lo: float, hi: "float | None") -> "float | None":
    """R80: 0 inside his range, else the distance to its nearest end (an open top counts only a shortfall)."""
    if value is None:
        return None
    if value < lo:
        return lo - value
    if hi is not None and value > hi:
        return value - hi
    return 0.0


# ═════════════════════════════════════════════════════════════════════════════════════════════
# pins, gates, printout helpers
# ═════════════════════════════════════════════════════════════════════════════════════════════
def module_shas_line(files: tuple) -> str:
    return " ".join(f"{n} {C.sha(os.path.join(HERE, n))[:16]}" for n in files)


def printout_line(path: str, prefix: str) -> "str | None":
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as fh:
        for ln in fh:
            if ln.startswith(prefix):
                return ln[len(prefix):].strip()
    return None


def dry_mismatches(path: str) -> "int | None":
    ln = printout_line(path, "RESULT:")
    if ln is None:
        return None
    try:
        return int(ln.split("MISMATCH")[0].strip().split()[-1])
    except (ValueError, IndexError):
        return None


def _sha_or_absent(path: str) -> str:
    return C.sha(path) if os.path.exists(path) else "ABSENT"


def sha16_or_absent(path: str) -> str:
    return C.sha(path)[:16] if os.path.exists(path) else "ABSENT"


def artefacts_6b_line() -> str:
    """R79: what 04 prints about 6b's files as it sees them (the 6c gate compares this line to the files on disk at --run)."""
    return f"03_check.txt {sha16_or_absent(P03['run'])} check_r1_r5.tsv {sha16_or_absent(OUT_6B['check_r1_r5'])}"


def pins_6b(doc: str = None, dry_path: str = None) -> dict:
    """Every pin 6b rests on: step 5's inputs and modules (C.pins without its outputs), 6a's module and the inventory, the three v2 sheets,
    the v2 wording, step 5's three outputs, 6a's joins, this module and 03, and 6b's dry-run printout. The keys this stage ADDS (after
    C.pins') are the ones the gate refuses at ABSENT (R79)."""
    p = C.pins(doc, include_outputs=False)
    p["02_captions.py"] = C.sha(os.path.join(HERE, "02_captions.py"))
    p["captions_inventory.py"] = C.sha(os.path.join(HERE, "inventory", "captions_inventory.py"))
    for path in V2_SHEETS:
        p[os.path.basename(path)[:-4]] = _sha_or_absent(path)
    p["reader_wording_v2"] = _sha_or_absent(WORDING_V2)
    for name, path in C.OUTPUTS.items():
        p[name] = _sha_or_absent(path)
    p["joins_6a"] = _sha_or_absent(JOINS_6A)
    p["asis_check_common.py"] = C.sha(os.path.join(HERE, "asis_check_common.py"))
    p["03_check.py"] = _sha_or_absent(os.path.join(HERE, "03_check.py"))
    p["dryrun6b_printout"] = _sha_or_absent(dry_path or P03["dry"])
    return p


def pins_6c(doc: str = None, dry_path: str = None) -> dict:
    """6b's pins (its dry run included), 03's run printout and outputs, 04 itself, and 6c's dry-run printout."""
    p = pins_6b(doc)
    p["run6b_printout"] = _sha_or_absent(P03["run"])
    for name, path in OUT_6B.items():
        p[name] = _sha_or_absent(path)
    p["04_band.py"] = _sha_or_absent(os.path.join(HERE, "04_band.py"))
    p["dryrun6c_printout"] = _sha_or_absent(dry_path or P04["dry"])
    return p


def stage_pin_keys(pins: dict, doc: str = None) -> list:
    """The pins a 6b / 6c stage adds beyond step 5's input pins (C.pins): the ones that may not read ABSENT at --run (R79)."""
    base = set(C.pins(doc, include_outputs=False))
    return [k for k in pins if k not in base]


def run_gate(stage: str, doc: str = None) -> list:
    """The reasons a --run of 03 ('6b') or 04 ('6c') is refused (empty = go), 01_points' run_gate shape (R34): the stage's dry run complete
    with 0 MISMATCH and made by the modules on disk; every pin incl. doc_body and the dry-run printout below the doc's freeze marker; the
    ledger verifying; no output present. 6c also needs 03's run printout with R1 and R5 at PASS (R79)."""
    paths, files, outs = (P03, MODULE_FILES_6B, OUT_6B) if stage == "6b" else (P04, MODULE_FILES_6C, OUT_6C)
    problems = []
    if not C.dry_run_complete(paths["dry"]):
        problems.append(f"the step-{stage} dry run has not completed ({os.path.basename(paths['dry'])})")
    else:
        mm = dry_mismatches(paths["dry"])
        if mm is None:
            problems.append("the dry run's RESULT line is missing or unreadable")
        elif mm > 0:
            problems.append(f"the dry run ended with {mm} MISMATCH")
        ml = printout_line(paths["dry"], "- modules: ")
        if ml != module_shas_line(files):
            problems.append("the dry run was made by other code than the modules on disk (or carries no module line): rerun --dry-run first"
                            + (f" (dry run: {ml})" if ml else ""))
    pins = pins_6b(doc) if stage == "6b" else pins_6c(doc)
    miss = C.freeze_missing(doc or C.DOC, pins)
    if miss:
        problems.append("pins not below the doc's freeze marker (freeze first, --print-pins, paste): " + ", ".join(miss))
    absent = [k for k in stage_pin_keys(pins, doc) if pins[k] == "ABSENT"]
    if absent:
        problems.append("pins reading ABSENT (an ABSENT pin passes the freeze check trivially; the file must exist and be pinned): " + ", ".join(absent))
    bad = C.ledger_verify() if os.path.exists(C.LEDGER) else []
    if bad:
        problems.append("ledger: " + "; ".join(bad))
    if stage == "6c":
        r1, r5 = printout_line(P03["run"], LINE_R1), printout_line(P03["run"], LINE_R5)
        if r1 is None or r5 is None:
            problems.append("step 6b has not run (03_check.txt carries no R1 / R5 verdict): 6c is not read before 6b")
        else:
            if not r1.startswith(VERDICT_PASS):
                problems.append(f"6b's R1 verdict is {r1.split(' ')[0] if r1 else '?'}: 'if 6b fails, 6c is not read at all' (a not-decidable R1 is the main loop's call)")
            if not r5.startswith(VERDICT_PASS):
                problems.append(f"6b's R5 verdict is {r5.split(' ')[0] if r5 else '?'}: 'if 6b fails, 6c is not read at all'")
        seen = printout_line(paths["dry"], LINE_6B_ARTEFACTS)
        now = artefacts_6b_line()
        if seen is None or "ABSENT" in seen:
            problems.append(f"the 6c dry run saw 6b's files absent or printed no artefact line ({seen}): rerun 04 --dry-run AFTER 03 --run, re-pin, paste")
        elif seen != now:
            problems.append(f"the 6c dry run saw other 6b files than the ones on disk (dry run: {seen}; disk: {now}): rerun 04 --dry-run, re-pin, paste")
    existing = [q for q in list(outs.values()) + [paths["run"]] if os.path.exists(q)]
    if existing:
        problems.append("outputs exist: " + ", ".join(existing))
    return problems


def preamble(say, stage: str, label: str, scan_files: tuple, module_files: tuple, refused_to: str) -> bool:
    """The three guard lines every stage prints first (scan, import belt, modules); False when a guard failed (the refusal written)."""
    say(f"# #705 as-is STEP {stage} — {label} ({__import__('time').strftime('%Y-%m-%d %H:%M')})")
    say("Guards: no network, no production server, no paid call, nothing after 2024-12-31, the seven outcome folders never opened, nothing "
        "imported from the rule folders. No rule, setup name or pattern label enters; the join reads the symbol and the day only.")
    hits = C.scan_identifiers([os.path.join(HERE, n) for n in scan_files])
    if hits:
        say("IDENTIFIER SCAN FAILED: " + "; ".join(f"{os.path.basename(p)}:{ln} {t}" for p, ln, t in hits))
        say.write(refused_to)
        return False
    say("- identifier scan: clean (the step-5/6 modules hold none of the excluded names)")
    loaded = C.rule_modules_loaded()
    if loaded:
        say("RULE MODULE LOADED (guard 3): " + ", ".join(loaded))
        say.write(refused_to)
        return False
    say("- import belt: no rule module in sys.modules")
    say("- modules: " + module_shas_line(module_files))
    return True


def write_tsv(rows: list, cols: list, path: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path + ".partial", "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, delimiter="\t", lineterminator="\n", extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({c: ("" if r.get(c) is None else r.get(c)) for c in cols})
    os.replace(path + ".partial", path)


def year_block(year) -> str:
    y = str(year)[:4]
    for name, ys in YEAR_BLOCKS:
        if y in ys:
            return name
    return "other"


def fmt(x, nd: int = 1) -> str:
    return "n/a" if x is None else f"{x:.{nd}f}"
