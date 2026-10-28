#!/usr/bin/env python3
"""#711 step 7, part 2 — his trades GROUPED by what the chart shows, by confidence tier (docs/analysis/cb_asis_step7_grouping_prereg_2026-10-27.md,
§3-§7; the document is FROZEN above its marker and never edited here). Steps 5-6 stay frozen in cb_asis_reconstruction_prereg_2026-10-26.md.

WHAT IT DOES   one row per position (the tiers of tiers.tsv): the ENTRY side's chart measures, the EXIT side's chart measures and the hold
               length — the §3.3 columns registered in 05_tiers.py::STEP7_FEATURES (imported, never widened), recomputed at each side's
               MIDDLE MINUTE (§3.2: the volume-median reachable minute; the largest-volume reachable session at its typical price when the
               side is daily-only) through step 5's own `day_context` / `features` (01_points.py, loaded by path; its `load_all` gives the
               windows' reachable minutes and the bars). The method of §4 (rank-normal with linear tails frozen on the primary, PCA to 90%
               whitened, seeded k-means, k by prediction strength >= 0.80 with every group >= max(30, 5%)), the runs of §5 (primary = HIGH
               + MEDIUM; + ONE-STREAM; + LOW; CONFIRMED; with `our_length`; the band's edges; the buy-year split; entry-only / exit-only),
               the two comparison modes, the noise floor, description survival on the 13 families and the consequence table — all stated
               before the groups are seen. The phrase table (PHRASES) is fixed here, before the run.

WHAT IT NEVER READS  any trade outcome (§3.5): no return, R, gain, win / loss or "worked" is read, computed or printed; the exit side carries
               no `ret_N` and a look-back only when N < hold_sessions_min (05_tiers.exit_lookbacks_defined); `forbidden_outcomes.txt` and
               `forbidden_identifiers.txt` are both scanned against the step-7 modules (this one, 05_tiers, 01_points, asis_common);
               check_r1_r5.tsv is never opened here (`confirmed` comes from tiers.tsv); the candidate points, the family / direction tags,
               the point-level columns and the band width are held out (05_tiers.HELD_OUT); nothing dated after 2024-12-31; none of the seven
               outcome folders; nothing imported from the rule folders.

STAGES  --dry-run     loads tiers.tsv + ranges.tsv + step 5's bars, builds every feature row, prints the feature coverage per tier, the
                      blank counts (data / structural), the extrapolated counts per tier under the primary's maps AND how large the scores get
                      (R72), the same-session readout (R73), the primary's PCA size and the primary's k sweep (prediction strengths, sizes,
                      the k the rule picks) — no group description, no cross-tier comparison; asserts the CLAIMS (every count the
                      registration states as a fact) and ends DRY RUN COMPLETE with a RESULT line; writes 06_groups_dryrun.txt and nothing else.
        --print-pins  the sha256 pins: 05's pins (step 5's inputs and modules, both doc bodies, step 5's outputs, 6b's files, 05_tiers.py, the
                      outcome-name list, 05's dry-run printout) plus 05's run printout, tiers.tsv, this module and this stage's dry-run
                      printout -> stdout and 06_groups_pins.txt.
        --run         writes step7_features.tsv / step7_groups.tsv / step7_descriptions.tsv / step7_stability.tsv under asis_1026/ and
                      06_groups.txt; refused unless the dry run completed with 0 MISMATCH and was made by the modules on disk, 05's run ended
                      RUN COMPLETE, every pin (incl. the step-7 doc body and this dry run's printout) sits below the step-7 doc's
                      <!-- FREEZE --> marker (none ABSENT), the ledger verifies (tiers.tsv unchanged since written) and no output exists.
                      Ledger rows `step7_groups_*`.

READINGS where the registration is silent or ambiguous (the stricter reading each time; numbered on from 01_points' R47; the main loop decides):
  R48 The price of a minute-resolved side at its middle minute is that minute bar's CLOSE (a bar holds no trade print; the close is the one
      price a minute bar reports as "the price at a time"); features are computed at it. A daily-only side's price is (high + low + close) / 3
      as §3.2 says.
  R49 A side whose resolution is `partial` (some reachable sessions without minute bars; 1 buy side in the primary, 5 + 5 overall) or a minute
      side whose reachable minutes hold no bar (`no_minute_bar_in_reach`, 4 sides) is described as DAILY-ONLY (the largest-volume reachable
      session, typical price, minute blank) and flagged `partial_resolution` / `no_minute_bar_in_reach`; a minute side whose reachable volume
      totals zero takes its middle minute by count. A side with no reachable range (no bars) has no features (the row is listed, R62).
  R50 The volume-median minute is the FIRST reachable minute (sessions in order, minutes in order) at which the cumulative volume reaches half
      of the total.
  R51 `minute` on a daily-only side = the session's midpoint in minutes since 09:30 (195; 105 on a 13:00 close), the side flagged
      `daily_only`; `vol_sofar_vs_N` is then a DATA blank (no minute bars), counted toward the quarter rule like any other data blank.
  R52 The sweep ratios `range_vs_avgrange_N`, `vol_day_vs_N`, `vol_sofar_vs_N` (N = 5, 10, 20, 40, 60) are computed here exactly as step 5's
      `day_context` / `features` compute the 20-session ones (the mean of the prior N sessions' ranges / volumes; the day's range / volume /
      the minute volume so far over them); a dry-run claim holds the N = 20 column equal to the frozen column on every described side.
  R53 The edges run describes each side at the (session, minute) of the band's lowest low and, separately, of its highest high — re-derived the
      way side_rows found them and claimed equal to ranges.tsv's `range_lo_minute` / `range_hi_minute` on every primary side — at that low /
      high price (the minute blank on a daily session). The §7 line names the low-vs-high pair, so that comparison is printed beside the two
      against the primary (R66).
  R54 Seeded draws beyond the registered k-means key: the 50 halves of a (run, k) come from ONE generator `rng_for("step7_ps_<run>_k<k>")`
      which also seeds the two fits of each half (sequential draws); the refits `rng_for("step7_refit_<i>")`, the bootstrap resamples
      `rng_for("step7_boot_<i>")` (i = 1..5), the examples as registered. The halves' fits use the same 20 starts as the full fit.
  R55 Nearest-centroid ties go to the lowest group index (np.argmin); a k-means start that empties a cluster re-seeds it from a random row.
  R56 The noise floor's seeded and bootstrap refits are at the PRIMARY's k (a refit, not a re-choice); the floors are the mean moved share of
      the five, and the lines read as excess over the larger of the two.
  R57 CONFIRMED is an ASSIGNMENT readout (§2.4 / the §5 row: the 33 primary rows by their fitted group, the 14 others by the nearest primary
      centroid), not a k-means run: n = 47 cannot hold two groups of 30, so a k choice would always read "no stable grouping". k is not
      re-chosen for it; its shares are compared to the primary's and the 15-point / empty-group consequences applied.
  R58 The 13 families are the ones the registration names, side-agnostic (`entry_dist_hi_10` and `exit_dist_hi_5` are both "from recent
      highs"); the family -> column map is printed by the dry run. A family's signed value is its column of largest |standardized mean
      deviation|. Survival: the same five (family, sign) pairs AND Spearman >= 0.8 -> survives; Spearman < 0.5, or the pairs differing with
      Spearman < 0.8 -> lost; otherwise partial.
  R59 Mode B has no added tier, so its "new group" is an other-run group left UNMATCHED by the Hungarian assignment (its k above the
      primary's); in mode A an unmatched other-run group is a new group as well, beside the two registered tests.
  R60 The minimum group size is max(30, ceil(5% of the run's n)) (34 for the primary, as §4.5 states).
  R61 A description's "run's mean" is the mean of that run's own standardized matrix (zero-filled); survival is measured against the
      PRIMARY's frozen means (§5 (c)), the other run's rows standardized with the primary's maps over the common columns.
  R62 A position with no features on a side (no reachable range / no bars) is the quarter rule's extreme (100% blank) and is dropped and
      listed by reason; the + LOW run's 153 rangeless positions are among them (a claim).
  R63 The §7 description expectation is scored mechanically on group MEDIANS: "an early-day buy near a recent high after a run-up" = entry
      minute < 120, entry dist_hi_10 >= -3%, entry ret_10 > 5%; "a sale within two sessions near the day's low" = exit pos_in_day < 0.3 and
      hold_sessions_max <= 2. The §7 table is scored at the run, never claimed in the dry run.
  R64 The real-data test re-runs the dry run into a temporary printout (as the tiers test does), never reading the pinned one.
  R65 A group's tier mix, confirmed count and band width come from tiers.tsv (buy / sale `range_width_pct`); the examples' dates from ranges.tsv.
  R66 See R53: the edges comparison is printed three ways (low vs primary, high vs primary, low vs high).
  R67 --run also requires 05_tiers.txt to end RUN COMPLETE and the ledger to verify (so tiers.tsv is the file 05 wrote, unchanged).
  R68 The hold feature for the year split and the edges run is the same `hold_sessions_max`; the year split halves are 347 / 330 (a claim);
      their minimum group size is 30 (5% of either half is under 30).
  R69 A run whose rows are a SUBSET of the primary (the year split) measures the moved share over its own rows; a run that ADDS rows measures
      it over the primary rows it contains; the edges run over all 677.
  R70 The minimum group size is 5% of the run's REGISTERED n (its rows before the quarter rule drops any — 677 for the primary, so 34 as §4.5
      states), not of the rows that survive the drop (658: the 19 primary positions with a short history — IPOs with fewer than 60 prior
      sessions — carry over a quarter of their non-structural features blank and are listed); the larger minimum is the stricter reading.
      The drop count is a readout, not a claim: the registration states no number for it.
  R71 §5 (d) names TWO conditions for an artefact — a new group that forms on the blank pattern alone AND does not separate on the entry side or
      the exit day's own columns (review F3: the first build tested the 80% pattern alone). A structural new group (§3.4) is an ARTEFACT only
      when no entry column and no exit DAY_OWN column carries a |standardized mean deviation| >= 0.5 (half the run's spread) from the run's
      mean (`artefact_groups`); the exit look-backs (the pattern's own columns) and the hold (the pattern's own fact — the 220 same-day trades
      are the hold-0 trades) are not consulted, so a group that separates on the hold alone stays an artefact (the stricter reading). A
      structural group that separates there is a real new group and reads under the "he decides" row. The §3.4 flag (the exit description read
      on the day-own columns only) is unchanged.
  R72 Beside the extrapolated COUNTS (§4.1), both stages print how LARGE the scores get under the primary's maps — the maximum |score| per
      column with the knot count of its map, the rows carrying any |score| beyond 4 and beyond 10, the columns with a value beyond 10 — for
      the primary, ONE-STREAM and LOW (review F4: the tail rule continues the outermost pair's slope, so a map whose outer knots sit close, or
      that rests on a few long-hold knots, scores a value beyond them in the hundreds; the first dry run reads ONE-STREAM to |1026| on
      exit_vol_sofar_vs_5, 61 of 484 rows beyond |4|, and LOW to |16099| on one exit_pos_in_day row — eid 1881 CBIO 2022-06-06, a minute close
      236 day-ranges above the day's low: that day's minute closes run 958-1110 while the daily bar reads 16.95-21.00, the two sources on
      different scales by a factor near 55 (checked; the cause — an adjustment applied on one source only — is not traced here; a step-5
      artefact carried as is, a wide_window LOW row). ⚠ R71 reads separation on the pattern-free columns, and the exit volume ratios are
      among them, so a same-day group's mean there can be carried by its rows beyond |10| — the run prints the group's largest |score| and
      the count beyond |10| on the separating column beside the R71 verdict. A readout, never a clip: changing the tail rule is a
      re-registration below the marker, his call before + ONE-STREAM / + LOW.
  R73 A same-session round trip (hold_sessions_max = 0) has EVERY exit look-back defined by §3.3 (b), and its entry and exit are described on
      the same session (220 of 220 in ONE-STREAM), so the two sides share each reference (the prior close, the N-session highs / lows / averages,
      the day's range) and an entry look-back minus the matching exit look-back is the entry-to-exit move as a linear combination — the thing
      §3.5 says §3.3 removes (review F5). The code follows the registration exactly and computes no such difference; the primary holds no
      such trade (a claim); both stages print the count per tier; a remedy (blanking the same-session exit look-backs as structural, or an
      entry + unsigned-exit grouping) is a re-registration below the marker — surfaced for his decision before + ONE-STREAM or + LOW runs.
  R74 step7_features.tsv carries no price column (the first build wrote entry_price and exit_price on one row — one subtraction from the
      forbidden quantity; review F6): the side's date and minute stay, ranges.tsv already holds both bands. The stricter reading of §3.5.
  R75 A wording slip, noted here (the frozen text and 05's docstring stay as they are): §3.3 (b) and `exit_lookbacks_defined` say a look-back
      with N < hold_sessions_min "ends before the entry day"; it STARTS after the entry day (the prior N sessions of the exit, E-N..E-1, all
      lie after the buy session B when N < E-B). The rule is right — the window never reaches the entry — the words are wrong (review F8).

STEP 7b (2026-10-27, docs/analysis/cb_asis_step7b_power_prereg_2026-10-27.md §7 / §11; the methods live in 06b_power.py and are imported
  LAZILY, only for a non-default switch — the default path is the registered one above, unchanged): `--method {registered, M1, M2w, M2u,
  M3w, M3u, M4}` and `--columns {registered, pattern_free}`. EVERY stage that opens the real matrix (--dry-run included) refuses a non-default
  method or column set until 06b_power.txt ends `POWER COMPLETE: carried <method> on <columns>` naming them and its pin sits below the 7b
  doc's marker; --run (default or not) is refused until POWER COMPLETE, and when a `step7_groups` ledger row exists. Under a carried method:
  group means replace the centroids wherever the comparison code reads them; a row is assigned by the method's rule (nearest group / leaf
  mean; the posterior argmax for M4); the noise floor refits the carried method (06b R91); mode-A runs reuse the primary's maps and its
  reduction in the method's space (whitened PCA, or M1's parallel-analysis components, unwhitened); mode-B runs fit their own. Under
  `pattern_free`: the primary and every mode-A run on the 56 gap-free columns, entry-only unchanged (40), exit-only the 16 exit-day-own
  columns, with `our_length` the entry columns plus the exit-day-own ones (69). The default dry run also CLAIMS that its k-sweep block and
  32 claim lines reproduce the pinned reference printout (8352c78c; 06b R89). A non-default dry run writes `06_groups_dryrun_<method>_<columns>.txt`
  (06b R90). Fix card (2026-10-27, two read-only reviews; the readings are 06b's R95-R100): a carried method carries no `choice`, so the
  dry run's minimum-size claim and step 7 §7's first expectation read the method's own fit (R96); under `pattern_free` the hold and the
  exit look-backs are DESCRIBED per group from the run's registered columns, never grouped on (R97, `assemble(drop=False)`); both 7b gates
  also require 06b_power.txt made by the modules on disk, pinned below the 7b marker and ledgered (R99). Finish card (2026-10-28, 7b
  Re-registration 1; 06b R101-R104): under a carried M3w / M3u the noise floor's bootstrap refits test each resample's DISTINCT rows and
  then assign every row by nearest leaf mean (R102; the counts are printed).

BUILD NOTE (2026-10-27, disclosed — made AFTER the first real-data dry run read the primary's k sweep; no method or line changed; the
  synthetic checks below were run after that null was seen, so they are a reading of it, not a pre-registered test): the first dry run read
  NO STABLE GROUPING on the primary (prediction strength 0.52 at k = 2, falling with k; 658 fitted rows, 18 whitened components at 90.7%).
  The null cannot tell LOW POWER of the registered k rule at this size from a real ABSENCE of groups: §4.4 fits k-means on random halves
  (about 329 rows in 18 dimensions) and asks the halves to agree, and on synthetic worlds shaped like the real matrix (11-22 components at
  90%, a two-way split planted on the entry side) the full-data fit often recovered the planted split exactly while the half-sample strength
  still read 0.50-0.60 (the review's check: ARI 1.00 in 5 of 9 worlds; half-sample ARI 0.00 / 0.00 / 0.95 / 0.07 / 0.01 in 5 draws).
  Whitening is NOT the cause — the first build's note said it was and offered the unwhitened components as a remedy; at the real data's
  shape those read ARI about 0.00 in every configuration, and its "split perfect on every entry column" world was perfect on 8 of 40 entry
  columns (the others shifted by about 0.6 sd) and needed 38 components, a special case (tests/test_asis_groups.py now says so). So the
  null on the primary stands under §1.2 AS REGISTERED, with no remedy pre-decided; the fork is his: run + ONE-STREAM as registered (knowing
  R72 / R73), re-register §4.4 (a new section BELOW the marker, never an edit above it — and a synthetic power check matched to the real
  spectrum, about 18 components at 90% and n = 658, pinned before it), or stop. Nothing here was changed to fit.

Guards: no network, no production server, no paid call, no subagent. Run:
  python3 scripts/probes/_705_asis_1026/06_groups.py --dry-run | --print-pins | --run
"""
from __future__ import annotations

import argparse
import collections
import importlib.util
import itertools
import math
import os
import statistics
import sys
import time

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))


def _load(name: str, fname: str):
    path = os.path.join(HERE, fname)
    if name in sys.modules and getattr(sys.modules[name], "__file__", "") == path:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


C = _load("asis_common", "asis_common.py")
T = _load("asis_tiers05", "05_tiers.py")          # the tiers, the feature registration, the exit look-back rule, 05's pins
P = _load("asis_points01", "01_points.py")        # step 5's loader, day_context, features (never a rule module)
GuardStop, fnum = C.GuardStop, C.fnum

# ---- paths -------------------------------------------------------------------------------------------------------------------------------
DOC7 = T.DOC7
P06 = {"dry": os.path.join(HERE, "06_groups_dryrun.txt"), "run": os.path.join(HERE, "06_groups.txt"),
       "refused": os.path.join(HERE, "06_groups.refused.txt"), "pins": os.path.join(HERE, "06_groups_pins.txt"),
       "power": os.path.join(HERE, "06b_power.txt")}                                   # 7b: the power run's printout (its POWER COMPLETE line gates)
OUT_G = {k: os.path.join(C.OUT_DIR, f"step7_{k}.tsv") for k in ("features", "groups", "descriptions", "stability")}
MODULE_FILES_G = ("asis_common.py", "01_points.py", "05_tiers.py", "06_groups.py", "06b_power.py", "forbidden_identifiers.txt", "forbidden_outcomes.txt")
SCAN_FILES_G = ("asis_common.py", "01_points.py", "05_tiers.py", "06_groups.py", "06b_power.py")
STAGE_G = "step7_groups_"
METHODS_7B = ("registered", "M1", "M2w", "M2u", "M3w", "M3u", "M4")                    # 7b §11: the --method switch
COLUMNS_7B = ("registered", "pattern_free")                                           # 7b §11: the --columns switch


def power_module():
    """7b: 06b_power.py, loaded lazily (never at import; the default path never touches it)."""
    sys.modules.setdefault("asis_groups06", sys.modules[__name__])
    return _load("asis_power06b", "06b_power.py")


def dry_path_for(method: str = "registered", columns: str = "registered") -> str:
    """06b R90: the default dry run's printout is the pinned one; a non-default configuration writes its own, beside it (so a test that
    redirects P06 never writes into this folder)."""
    if method == "registered" and columns == "registered":
        return P06["dry"]
    return os.path.join(os.path.dirname(P06["dry"]), f"06_groups_dryrun_{method}_{columns}.txt")

# ---- the registration, as code (imported from 05_tiers; never widened) ------------------------------------------------------------------
FEATURES = T.STEP7_FEATURES
RATIO_N = T.RATIO_N
DAY_OWN = T.DAY_OWN
LOOKBACKS = T.LOOKBACKS
PRIMARY_TIERS = ("HIGH", "MEDIUM")
K_RANGE = tuple(range(2, 9))
STRENGTH_LINE = 0.80
VARIANCE_KEPT = 0.90
N_STARTS, N_HALVES, N_REFITS = 20, 50, 5
MOVE_LINES = (0.10, 0.25)
NEW_GROUP_TIER_SHARE = 0.60
STRUCTURAL_LINE = 0.80
DATA_BLANK_DROP = 0.25
TOP_FEATURES = 5
RUNS = ("primary", "plus_one_stream", "plus_low", "confirmed", "with_our_length", "edges_low", "edges_high", "year_2020", "year_2021_22",
        "entry_only", "exit_only")
RUN_TIERS = {"primary": PRIMARY_TIERS, "plus_one_stream": PRIMARY_TIERS + ("ONE-STREAM",), "plus_low": T.TIERS,
             "with_our_length": PRIMARY_TIERS, "edges_low": PRIMARY_TIERS, "edges_high": PRIMARY_TIERS, "year_2020": PRIMARY_TIERS,
             "year_2021_22": PRIMARY_TIERS, "entry_only": PRIMARY_TIERS, "exit_only": PRIMARY_TIERS, "confirmed": T.TIERS}
MODE_B = ("with_our_length", "entry_only", "exit_only")
FAMILY_NAMES = ("position in day", "minute", "gap", "range", "range ratio", "distance from the prior session", "from recent highs",
                "from recent lows", "from averages", "run-up", "volume", "sessions since the high", "hold")      # the 13 of §5 (c)


def family_of(col: str) -> str:
    """R58: the family of a feature column (the side prefix stripped)."""
    c = col.split("_", 1)[1] if col.startswith(("entry_", "exit_")) else col
    if c == "pos_in_day":
        return "position in day"
    if c == "minute":
        return "minute"
    if c == "gap_pct":
        return "gap"
    if c == "range_pct":
        return "range"
    if c.startswith("range_vs_avgrange_"):
        return "range ratio"
    if c.startswith("dist_prev_"):
        return "distance from the prior session"
    if c.startswith("dist_hi_"):
        return "from recent highs"
    if c.startswith("dist_lo_"):
        return "from recent lows"
    if c.startswith("dist_ma_"):
        return "from averages"
    if c.startswith("ret_"):
        return "run-up"
    if c.startswith("vol_"):
        return "volume"
    if c.startswith("sessions_since_hi_"):
        return "sessions since the high"
    if c == "hold_sessions_max":
        return "hold"
    raise ValueError(f"no family for {col}")


def run_columns(run: str, columns: str = "registered") -> list:
    """The matrix columns of a run: `entry_<c>` / `exit_<c>` / the trade-level column, from the registered sets. `columns = pattern_free`
    (7b §7.3, only under Fallback 1): the gap-free columns — every entry column and the exit day's own; the exit look-backs and the hold out."""
    fs = FEATURES["with_our_length" if run == "with_our_length" else "primary"]
    ent = [f"entry_{c}" for c in fs["entry"]]
    exi = [f"exit_{c}" for c in fs["exit"]]
    tr = list(fs["trade"])
    if columns == "pattern_free":
        exi = [c for c in exi if c[5:] in DAY_OWN]
        tr = []
    elif columns != "registered":
        raise ValueError(f"unknown column set {columns!r}")
    if run == "entry_only":
        return ent
    if run == "exit_only":
        return exi + tr
    return ent + exi + tr


# ---- the fixed phrase table (written before the run; §4.6) --------------------------------------------------------------------------------
N_WORDS = {3: "three-session", 5: "one-week", 10: "two-week", 20: "one-month", 40: "two-month", 60: "three-month"}


def _n_of(c: str) -> int:
    return int(c.rsplit("_", 1)[1])


def phrase(col: str, med) -> str:
    """Plain chart words for a feature's group median (the FIXED table of §4.6). `col` carries its side prefix."""
    side = "bought" if col.startswith("entry_") else "sold" if col.startswith("exit_") else ""
    c = col.split("_", 1)[1] if side else col
    if med is None or (isinstance(med, float) and not np.isfinite(med)):
        return f"{side} ({c}: no value)".strip()
    x = float(med)
    if c == "pos_in_day":
        w = "near the day's low" if x < 0.25 else "near the day's high" if x > 0.75 else "mid-range of the day"
    elif c == "minute":
        w = "in the first half hour" if x < 30 else "in the morning" if x < 120 else "around midday" if x < 300 else "in the last hour and a half"
    elif c == "gap_pct":
        w = ("on a gap up of over 5%" if x > 5 else "on a gap up" if x > 1 else "on a gap down of over 5%" if x < -5 else "on a gap down" if x < -1
             else "with little gap")
    elif c == "range_pct":
        w = "on a wide-range day (over 10% of price)" if x > 10 else "on a narrow-range day (under 3%)" if x < 3 else "on an ordinary-range day"
    elif c.startswith("range_vs_avgrange_"):
        w = ("on a day's range twice the recent average" if x > 2 else "on a range tighter than the recent average" if x < 0.7
             else "on a range near the recent average")
    elif c.startswith("dist_prev_"):
        what = c.rsplit("_", 1)[1]
        w = (f"at the prior session's {what}" if abs(x) <= 1 else f"above the prior session's {what}" if x > 0 else f"below the prior session's {what}")
    elif c.startswith("dist_hi_"):
        nw = N_WORDS[_n_of(c)]
        w = f"at the {nw} high" if abs(x) <= 1 else f"above the {nw} high" if x > 1 else f"well below the {nw} high" if x < -10 else f"below the {nw} high"
    elif c.startswith("dist_lo_"):
        nw = N_WORDS[_n_of(c)]
        w = f"at the {nw} low" if abs(x) <= 1 else f"well above the {nw} low" if x > 10 else f"above the {nw} low" if x > 1 else f"below the {nw} low"
    elif c.startswith("dist_ma_"):
        n = _n_of(c)
        w = (f"at the {n}-day average" if abs(x) <= 1 else f"well above the {n}-day average" if x > 5 else f"above the {n}-day average" if x > 1
             else f"well below the {n}-day average" if x < -5 else f"below the {n}-day average")
    elif c.startswith("ret_"):
        nw = N_WORDS[_n_of(c)]
        w = (f"after a {nw} run-up of over 15%" if x > 15 else f"after a {nw} run-up" if x > 5 else f"after a {nw} drop of over 15%" if x < -15
             else f"after a {nw} drop" if x < -5 else f"after a flat {nw} stretch")
    elif c.startswith("vol_day_vs_"):
        w = "on twice the usual volume" if x > 2 else "on above-usual volume" if x > 1.2 else "on light volume" if x < 0.7 else "on usual volume"
    elif c.startswith("vol_sofar_vs_"):
        w = ("with a full usual day's volume already traded" if x > 1 else "with half a usual day's volume traded so far" if x > 0.5
             else "with little of the day's volume traded so far")
    elif c.startswith("sessions_since_hi_"):
        nw = N_WORDS[_n_of(c)]
        w = (f"the {nw} high set in the last session or two" if x <= 1 else f"the {nw} high set within the past week" if x <= 5
             else f"the {nw} high set over a week ago")
    elif c == "hold_sessions_max":
        w = ("a same-day round trip" if x <= 0 else "held overnight (one session)" if x <= 1 else "held two to five sessions" if x <= 5
             else "held one to four weeks" if x <= 20 else "held over a month")
        return w
    else:
        raise ValueError(f"no phrase for {col}")
    return f"{side} {w}"


# ---- printing ----------------------------------------------------------------------------------------------------------------------------
Say, Claims, table, pct = T.Say, T.Claims, T.table, T.pct


def f4(x) -> str:
    return "" if x is None or x == "" or (isinstance(x, float) and not np.isfinite(x)) else f"{float(x):.4g}"


# ---- the side descriptions (§3.2) --------------------------------------------------------------------------------------------------------
def side_sessions(w, bars) -> list:
    """The reachable sessions of a side with their daily context and, where minute bars exist and reach, the day's minute arrays — the same
    per-session facts side_rows (01_points) read. [] when the side has no bars."""
    b, ix = bars.daily(w.export, w.bar_sym)
    if b is None or not w.reach:
        return []
    out = []
    for d, m0, m1 in w.reach:
        if ix.get(d) is None:
            continue
        ctx = P.day_context(b, ix, d)
        end = C.session_end_minute(d)
        mb = None
        if not w.wide and bars.store.state(d, w.bar_sym).split("/")[0] == "ok":
            mb = bars.store.get(d, w.bar_sym)
        arrays, i0, i1 = None, None, None
        if mb is not None:
            sel = mb.minute < end
            m, o, h, l, c, v = (np.asarray(x[sel]) for x in (mb.minute, mb.o, mb.h, mb.l, mb.c, mb.v))
            mlo, mhi = (0 if m0 is None else m0), (end - 1 if m1 is None else m1)
            idx = np.flatnonzero((m >= mlo) & (m <= mhi))
            if len(idx):
                i0, i1 = int(idx[0]), int(idx[-1])
                arrays = (m, o, h, l, c, v)
        out.append({"d": d, "ctx": ctx, "end": end, "arrays": arrays, "i0": i0, "i1": i1, "bars": b})
    return out


def side_range(sessions: list) -> tuple:
    """(lo, lo_at, hi, hi_at) the way side_rows computes the bars-only range: minute lows / highs over the reach where minute bars reach, the
    day's low / high otherwise; `at` = (date, minute | '')."""
    lo_v, hi_v, lo_at, hi_at = np.inf, -np.inf, None, None
    for s in sessions:
        if s["arrays"] is not None:
            m, _o, h, l, _c, _v = s["arrays"]
            i0, i1 = s["i0"], s["i1"]
            lo_d, hi_d = fnum(l[i0:i1 + 1].min()), fnum(h[i0:i1 + 1].max())
            lo_m, hi_m = int(m[i0 + int(np.argmin(l[i0:i1 + 1]))]), int(m[i0 + int(np.argmax(h[i0:i1 + 1]))])
        else:
            lo_d, hi_d, lo_m, hi_m = s["ctx"]["l"], s["ctx"]["h"], "", ""
        if lo_d < lo_v:
            lo_v, lo_at = lo_d, (s["d"], lo_m)
        if hi_d > hi_v:
            hi_v, hi_at = hi_d, (s["d"], hi_m)
    return lo_v, lo_at, hi_v, hi_at


def middle_point(sessions: list, resolution: str) -> dict:
    """R48-R50: the side's reference point: {'session', 'i' (minute index | None), 'price', 'flags'}."""
    flags = set()
    if resolution == "minute":
        reach = [(s, i) for s in sessions if s["arrays"] is not None for i in range(s["i0"], s["i1"] + 1)]
        if reach:
            vols = np.array([fnum(s["arrays"][5][i]) for s, i in reach])
            total = fnum(vols.sum())
            if total > 0:
                k = int(np.flatnonzero(np.cumsum(vols) >= total / 2.0)[0])
            else:
                k = (len(reach) - 1) // 2
                flags.add("zero_volume_reach")
            s, i = reach[k]
            return {"session": s, "i": i, "price": fnum(s["arrays"][4][i]), "flags": flags}
        flags.add("no_minute_bar_in_reach")
    elif resolution == "partial":
        flags.add("partial_resolution")
    flags.add("daily_only")
    s = max(sessions, key=lambda q: q["ctx"]["v"])            # the first on ties (max keeps the first maximal element)
    ctx = s["ctx"]
    return {"session": s, "i": None, "price": (ctx["h"] + ctx["l"] + ctx["c"]) / 3.0, "flags": flags}


def edge_point(sessions: list, which: str) -> dict:
    """R53: the side at its band's lowest low ('low') or highest high ('high')."""
    best = None
    for s in sessions:
        if s["arrays"] is not None:
            _m, _o, h, l, _c, _v = s["arrays"]
            i0, i1 = s["i0"], s["i1"]
            seg = l[i0:i1 + 1] if which == "low" else h[i0:i1 + 1]
            k = int(np.argmin(seg)) if which == "low" else int(np.argmax(seg))
            val, i = fnum(seg[k]), i0 + k
        else:
            val, i = (s["ctx"]["l"] if which == "low" else s["ctx"]["h"]), None
        better = best is None or (val < best[0] if which == "low" else val > best[0])
        if better:
            best = (val, s, i)
    val, s, i = best
    flags = {"daily_only"} if i is None else set()
    return {"session": s, "i": i, "price": val, "flags": flags}


def point_features(pt: dict, cols: tuple) -> dict:
    """The registered columns of one side at one point: step 5's `features` at the point (the day's own measures, the look-backs, the
    run-up) plus the sweep ratios (R52) and `minute` (R51). Blank = ''."""
    s, i, price = pt["session"], pt["i"], pt["price"]
    ctx, b = s["ctx"], s["bars"]
    if i is None:
        p = P.Point(s["d"], None, price, "mid", "level", "", "", False, "daily_only", None, None)
        f = P.features(p, ctx, None, (price, price))
        minute, v_sofar = s["end"] // 2, None
    else:
        m, o, h, l, c, v = s["arrays"]
        p = P.Point(s["d"], int(m[i]), price, "mid", "level", "", "", False, "minute", i, None)
        f = P.features(p, ctx, (m, o, h, l, c, v, np.zeros(1), s["i0"]), (price, price))
        minute, v_sofar = int(m[i]), fnum(v[:i + 1].sum())
    f["minute"] = minute
    # review F2: the frozen 20-session columns are captured BEFORE the sweep loop, which writes `vol_day_vs_20` / `vol_sofar_vs_20` under the
    # same keys (the first build read the check after the loop, so two of its three columns compared with themselves)
    check20 = (f.get("range_vs_avgrange20", ""), f.get("vol_day_vs_20", ""), f.get("vol_sofar_vs_20", ""))
    j = ctx["j"]
    rng = ctx["h"] - ctx["l"]
    for n in RATIO_N:
        if j >= n:
            avg_r = fnum((b.h[j - n:j] - b.l[j - n:j]).mean())
            vol_n = fnum(b.v[j - n:j].mean())
        else:
            avg_r = vol_n = None
        f[f"range_vs_avgrange_{n}"] = round(rng / avg_r, 4) if avg_r else ""
        f[f"vol_day_vs_{n}"] = round(ctx["v"] / vol_n, 4) if vol_n else ""
        f[f"vol_sofar_vs_{n}"] = round(v_sofar / vol_n, 4) if (vol_n and v_sofar is not None) else ""
    out = {c: f.get(c, "") for c in cols}
    out["_check20"] = check20
    return out


ENTRY_COLS_ALL = FEATURES["with_our_length"]["entry"]
EXIT_COLS_ALL = FEATURES["with_our_length"]["exit"]


def structural_pattern(hold_min, hold_max) -> str:
    return ",".join(str(n) for n in T.exit_lookbacks_defined(hold_min, hold_max)) or "(none)"


def apply_structural(exit_feats: dict, hold_min, hold_max) -> tuple:
    """(features with the undefined exit look-backs blanked, the set of structural-blank columns) — §3.3 (b), never filled from the bars."""
    ok = set(T.exit_lookbacks_defined(hold_min, hold_max))
    struct = set()
    out = dict(exit_feats)
    for n, cols in LOOKBACKS.items():
        if n in ok:
            continue
        for c in cols:
            if c in out:
                out[c] = ""
                struct.add(c)
    return out, struct


def build_features(L: dict, tiers: list, ranges: dict, say, modes: tuple = ("middle", "low", "high")) -> dict:
    """eid -> {mode: {'entry': {...}, 'exit': {...}, 'trade': {...}, 'flags': {...}} | None} plus the per-side checks (R52 / R53)."""
    S, bars = L["S"], L["bars"]
    by = {("buy", w.eid): w for w in L["buys"]}
    by.update({("sale", w.eid): w for w in L["sales"]})
    out, checks = {}, collections.Counter()
    t0 = time.time()
    for tr in tiers:
        eid = int(tr["eid"])
        rec = {"meta": tr}
        for mode in modes:
            if mode != "middle" and tr["tier"] not in PRIMARY_TIERS:
                continue
            sides = {}
            for side, prefix in (("buy", "entry"), ("sale", "exit")):
                w = by.get((side, eid))
                rrow = ranges.get((str(eid), side))
                if w is None or rrow is None or rrow["range_lo"] == "":
                    sides[prefix] = None
                    continue
                sess = side_sessions(w, bars)
                if not sess:
                    sides[prefix] = None
                    continue
                if mode == "middle":
                    lo_v, lo_at, hi_v, hi_at = side_range(sess)
                    checks[("range_ok" if (round(lo_v, 4) == float(rrow["range_lo"]) and round(hi_v, 4) == float(rrow["range_hi"])) else "range_mismatch")] += 1
                    pt = middle_point(sess, rrow["resolution"])
                elif mode == "low":
                    pt = edge_point(sess, "low")
                    at = f"{pt['session']['d']}:{'' if pt['i'] is None else int(pt['session']['arrays'][0][pt['i']])}"
                    checks["lo_at_ok" if at == rrow["range_lo_minute"] else "lo_at_mismatch"] += 1
                else:
                    pt = edge_point(sess, "high")
                    at = f"{pt['session']['d']}:{'' if pt['i'] is None else int(pt['session']['arrays'][0][pt['i']])}"
                    checks["hi_at_ok" if at == rrow["range_hi_minute"] else "hi_at_mismatch"] += 1
                cols = ENTRY_COLS_ALL if prefix == "entry" else EXIT_COLS_ALL
                f = point_features(pt, cols)
                c20 = f.pop("_check20")
                for mine, frozen in ((f.get("range_vs_avgrange_20", ""), c20[0]), (f.get("vol_day_vs_20", ""), c20[1]), (f.get("vol_sofar_vs_20", ""), c20[2])):
                    checks["sweep20_ok" if mine == frozen else "sweep20_mismatch"] += 1
                sides[prefix] = {"feats": f, "flags": pt["flags"], "date": pt["session"]["d"], "minute": f["minute"], "price": pt["price"]}
            if sides["entry"] is None or sides["exit"] is None:
                rec[mode] = None
                continue
            ex, struct = apply_structural(sides["exit"]["feats"], tr["hold_sessions_min"], tr["hold_sessions_max"])
            rec[mode] = {"entry": sides["entry"]["feats"], "exit": ex, "struct": struct,
                         "trade": {"hold_sessions_max": tr["hold_sessions_max"]},
                         "flags": {"entry": sides["entry"]["flags"], "exit": sides["exit"]["flags"]},
                         "at": {"entry": (sides["entry"]["date"], sides["entry"]["minute"], sides["entry"]["price"]),
                                "exit": (sides["exit"]["date"], sides["exit"]["minute"], sides["exit"]["price"])}}
        out[eid] = rec
    say(f"- feature rows built for {len(out):,} positions in {time.time() - t0:.0f}s; range re-derivation vs ranges.tsv: "
        f"{checks['range_ok']} sides equal, {checks['range_mismatch']} differ; sweep N=20 vs the frozen column: {checks['sweep20_ok']} equal, "
        f"{checks['sweep20_mismatch']} differ; band ends (R53): low {checks['lo_at_ok']} / {checks['lo_at_mismatch']}, high {checks['hi_at_ok']} / "
        f"{checks['hi_at_mismatch']} (equal / differ)")
    out["_checks"] = checks
    return out


# ---- matrices (§3.4) ---------------------------------------------------------------------------------------------------------------------
def _fv(x):
    try:
        v = float(x)
    except (TypeError, ValueError):
        return np.nan
    return v if np.isfinite(v) else np.nan


def assemble(feats: dict, eids: list, cols: list, mode: str = "middle", drop: bool = True) -> dict:
    """The raw matrix of a run: X (n x p, NaN = blank), `struct` mask (structural blanks), the rows dropped by the quarter rule (listed with
    their blank share) and the structural pattern per row. `drop=False` (7b, the description matrix under `pattern_free` — 06b R97): the
    quarter rule is NOT applied, so the rows are exactly `eids` in order (a row without features on the side is still dropped)."""
    X, SM, keep, dropped, patterns = [], [], [], [], []
    for eid in eids:
        rec = feats[eid].get(mode)
        if rec is None:
            dropped.append((eid, 1.0, "no features on a side"))
            continue
        row, sm = [], []
        for c in cols:
            if c.startswith("entry_"):
                v, s = rec["entry"].get(c[6:], ""), False
            elif c.startswith("exit_"):
                v, s = rec["exit"].get(c[5:], ""), c[5:] in rec["struct"]
            else:
                v, s = rec["trade"].get(c, ""), False
            row.append(_fv(v))
            sm.append(s)
        row, sm = np.array(row), np.array(sm)
        non_struct = ~sm
        share = float(np.isnan(row[non_struct]).mean()) if non_struct.any() else 0.0
        if drop and share > DATA_BLANK_DROP:
            dropped.append((eid, share, "over a quarter of the non-structural features blank"))
            continue
        X.append(row)
        SM.append(sm)
        keep.append(eid)
        patterns.append(structural_pattern(feats[eid]["meta"]["hold_sessions_min"], feats[eid]["meta"]["hold_sessions_max"]))
    X = np.array(X) if X else np.zeros((0, len(cols)))
    SM = np.array(SM, dtype=bool) if SM else np.zeros((0, len(cols)), dtype=bool)
    return {"X": X, "struct": SM, "eids": keep, "cols": cols, "dropped": dropped, "patterns": patterns}


# ---- the method (§4) ---------------------------------------------------------------------------------------------------------------------
_ND = statistics.NormalDist()


class RankMap:
    """§4.1: the rank-normal (van der Waerden) map of ONE feature, fitted on the present values of the fit rows; piecewise-linear through the
    (value, score) knots (ties averaged), the outermost pair's slope continued beyond either end — never a clip."""

    def __init__(self, values):
        v = np.sort(np.asarray(values, dtype=float))
        n = len(v)
        if n == 0:
            self.x = self.y = np.zeros(0)
            return
        scores = np.array([_ND.inv_cdf((r + 1) / (n + 1)) for r in range(n)])
        uniq, inv = np.unique(v, return_inverse=True)
        self.x = uniq
        self.y = np.bincount(inv, weights=scores) / np.bincount(inv)

    def apply(self, vals) -> tuple:
        """-> (scores with NaN kept, the boolean mask of extrapolated values)."""
        vals = np.asarray(vals, dtype=float)
        out = np.full(vals.shape, np.nan)
        extra = np.zeros(vals.shape, dtype=bool)
        ok = np.isfinite(vals)
        if len(self.x) == 0:
            return out, extra
        if len(self.x) == 1:
            out[ok] = 0.0
            extra[ok] = vals[ok] != self.x[0]
            return out, extra
        out[ok] = np.interp(vals[ok], self.x, self.y)
        below, above = ok & (vals < self.x[0]), ok & (vals > self.x[-1])
        s0 = (self.y[1] - self.y[0]) / (self.x[1] - self.x[0])
        s1 = (self.y[-1] - self.y[-2]) / (self.x[-1] - self.x[-2])
        out[below] = self.y[0] + (vals[below] - self.x[0]) * s0
        out[above] = self.y[-1] + (vals[above] - self.x[-1]) * s1
        extra[below | above] = True
        return out, extra


def fit_maps(X: np.ndarray, cols: list) -> dict:
    return {c: RankMap(X[:, k][np.isfinite(X[:, k])]) for k, c in enumerate(cols)}


SCORE_LINES = (4.0, 10.0)                                                 # R72: the sizes printed beside the extrapolated counts (review F4)


def score_sizes(Z: np.ndarray, cols: list, maps: dict = None, eids: list = None, top: int = 10) -> dict:
    """R72: how LARGE the standardized scores get — the maximum |score| over the matrix, the rows carrying any |score| beyond each line, the
    columns with a value beyond the larger line, and the `top` columns by maximum |score| with the knot count of their map (the linear tail's
    slope is the outermost pair's, so a map whose outer knots sit close scores a value beyond them very large). A readout, never a clip."""
    if not len(Z):
        return {"max": 0.0, "rows_beyond": {s: 0 for s in SCORE_LINES}, "cols_beyond_top": 0, "top": [], "row_max_eid": None}
    A = np.abs(Z)
    colmax, rowmax = A.max(0), A.max(1)
    order = np.argsort(-colmax)[:top]
    tops = [(cols[k], float(colmax[k]), (len(maps[cols[k]].x) if maps else None)) for k in order]
    rm = int(np.argmax(rowmax))
    return {"max": float(A.max()), "rows_beyond": {s: int((rowmax > s).sum()) for s in SCORE_LINES}, "cols_beyond_top": int((colmax > SCORE_LINES[-1]).sum()),
            "top": tops, "row_max_eid": (eids[rm] if eids else None), "row_max_col": cols[int(np.argmax(A[rm]))]}


def say_score_sizes(say, label: str, ss: dict) -> None:
    say(f"- {label}: max |score| {ss['max']:.4g}" + (f" (eid {ss['row_max_eid']}, {ss['row_max_col']})" if ss.get("row_max_eid") is not None else "")
        + "; rows with any |score| beyond " + ", ".join(f"{s:g}: {n}" for s, n in ss["rows_beyond"].items()) + f"; columns with a value beyond {SCORE_LINES[-1]:g}: {ss['cols_beyond_top']}")


def standardize(X: np.ndarray, cols: list, maps: dict) -> tuple:
    """-> (Z zero-filled, the extrapolated count per column, the blank count per column)."""
    Z = np.zeros_like(X)
    extra, blanks = {}, {}
    for k, c in enumerate(cols):
        sc, ex = maps[c].apply(X[:, k])
        blanks[c] = int(np.isnan(sc).sum())
        Z[:, k] = np.where(np.isnan(sc), 0.0, sc)
        extra[c] = int(ex.sum())
    return Z, extra, blanks


class PCA:
    """§4.2: principal components to 90% of the variance, whitened; fitted once, applied to every run in the same space."""

    def __init__(self, Z: np.ndarray, kept: float = VARIANCE_KEPT):
        self.mean = Z.mean(0)
        xc = Z - self.mean
        cov = xc.T @ xc / max(1, len(Z) - 1)
        lam, vec = np.linalg.eigh(cov)
        order = np.argsort(lam)[::-1]
        lam, vec = lam[order], vec[:, order]
        pos = lam > 1e-12
        lam, vec = lam[pos], vec[:, pos]
        cum = np.cumsum(lam) / lam.sum()
        m = int(np.searchsorted(cum, kept - 1e-12) + 1)
        self.lam, self.vec, self.m, self.explained = lam[:m], vec[:, :m], m, float(cum[m - 1])

    def transform(self, Z: np.ndarray) -> np.ndarray:
        return (Z - self.mean) @ self.vec / np.sqrt(self.lam)


def _d2(Z: np.ndarray, cent: np.ndarray) -> np.ndarray:
    return ((Z[:, None, :] - cent[None, :, :]) ** 2).sum(2)


def nearest(Z: np.ndarray, cent: np.ndarray) -> np.ndarray:
    return _d2(Z, cent).argmin(1)                                          # R55: ties to the lowest index


def kmeans(Z: np.ndarray, k: int, rng, starts: int = N_STARTS, max_iter: int = 300) -> dict:
    """§4.3: k-means++ seeded starts through `rng`, Lloyd's iterations, the best inertia kept. -> {'labels', 'centroids', 'inertia'}."""
    n = len(Z)
    best = None
    for _ in range(starts):
        cent = np.empty((k, Z.shape[1]))
        cent[0] = Z[rng.integers(n)]
        d2 = ((Z - cent[0]) ** 2).sum(1)
        for j in range(1, k):
            tot = d2.sum()
            pr = d2 / tot if tot > 0 else np.full(n, 1.0 / n)
            cent[j] = Z[rng.choice(n, p=pr)]
            d2 = np.minimum(d2, ((Z - cent[j]) ** 2).sum(1))
        labels = None
        for _it in range(max_iter):
            dd = _d2(Z, cent)
            new = dd.argmin(1)
            if labels is not None and np.array_equal(new, labels):
                break
            labels = new
            for j in range(k):
                mem = Z[labels == j]
                cent[j] = mem.mean(0) if len(mem) else Z[rng.integers(n)]
        dd = _d2(Z, cent)
        labels = dd.argmin(1)
        inertia = float(dd[np.arange(n), labels].sum())
        if best is None or inertia < best["inertia"] - 1e-12:
            best = {"labels": labels.copy(), "centroids": cent.copy(), "inertia": inertia}
    return best


def pair_share(own: np.ndarray, other: np.ndarray) -> float:
    """§4.4: the smallest, over the clusters of `own`, of the share of that cluster's pairs that `other` also puts together."""
    worst = 1.0
    for j in np.unique(own):
        mem = other[own == j]
        sz = len(mem)
        if sz < 2:
            continue
        pairs = sz * (sz - 1) / 2.0
        same = sum(c * (c - 1) / 2.0 for c in collections.Counter(mem.tolist()).values())
        worst = min(worst, same / pairs)
    return worst


def prediction_strength(Z: np.ndarray, k: int, rng, halves: int = N_HALVES, starts: int = N_STARTS) -> float:
    n = len(Z)
    vals = []
    for _ in range(halves):
        perm = rng.permutation(n)
        a, b = perm[: n // 2], perm[n // 2:]
        fit_a = kmeans(Z[a], k, rng, starts)
        fit_b = kmeans(Z[b], k, rng, starts)
        vals.append(pair_share(fit_b["labels"], nearest(Z[b], fit_a["centroids"])))
    return float(np.mean(vals))


def min_group_size(n: int) -> int:
    return max(30, int(math.ceil(0.05 * n)))                              # R60


def choose_k(Z: np.ndarray, run: str, k_range: tuple = K_RANGE, halves: int = N_HALVES, starts: int = N_STARTS, n_registered: int = None) -> dict:
    """§4.4-4.5: every k's strength, sizes and verdict; k = the LARGEST passing both lines (None = no stable grouping). The minimum size is
    5% of the run's registered n (R70; the fitted rows when not given)."""
    n = len(Z)
    nmin = min_group_size(n if n_registered is None else n_registered)
    sweep = {}
    for k in k_range:
        fit = kmeans(Z, k, C.rng_for(f"step7_{run}_k{k}"), starts)
        sizes = np.bincount(fit["labels"], minlength=k)
        ps = prediction_strength(Z, k, C.rng_for(f"step7_ps_{run}_k{k}"), halves, starts)
        sweep[k] = {"strength": ps, "sizes": sizes.tolist(), "min_size": int(sizes.min()), "size_ok": bool(sizes.min() >= nmin),
                    "strength_ok": bool(ps >= STRENGTH_LINE), "fit": fit}
    passing = [k for k in k_range if sweep[k]["size_ok"] and sweep[k]["strength_ok"]]
    return {"sweep": sweep, "k": max(passing) if passing else None, "n_min": nmin, "n": n, "n_registered": n if n_registered is None else n_registered}


# ---- the comparisons (§5) ----------------------------------------------------------------------------------------------------------------
def hungarian(cost: np.ndarray) -> list:
    """The minimum-cost one-to-one assignment of rows to columns (k <= 8 on both sides: every permutation is tried). -> [(row, col)]."""
    p, q = cost.shape
    if p == 0 or q == 0:
        return []
    best, best_pairs = None, None
    if p <= q:
        for perm in itertools.permutations(range(q), p):
            s = sum(cost[i, perm[i]] for i in range(p))
            if best is None or s < best - 1e-12:
                best, best_pairs = s, [(i, perm[i]) for i in range(p)]
    else:
        for perm in itertools.permutations(range(p), q):
            s = sum(cost[perm[j], j] for j in range(q))
            if best is None or s < best - 1e-12:
                best, best_pairs = s, [(perm[j], j) for j in range(q)]
    return best_pairs


def adjusted_rand(a: np.ndarray, b: np.ndarray) -> float:
    ct = pd.crosstab(pd.Series(a), pd.Series(b)).to_numpy()
    comb = lambda x: x * (x - 1) / 2.0
    s_ij = comb(ct).sum()
    s_a, s_b = comb(ct.sum(1)).sum(), comb(ct.sum(0)).sum()
    n = comb(ct.sum())
    expected = s_a * s_b / n if n else 0.0
    mx = (s_a + s_b) / 2.0
    return 1.0 if mx == expected else float((s_ij - expected) / (mx - expected))


def spearman(x, y) -> float:
    rx, ry = pd.Series(x).rank().to_numpy(), pd.Series(y).rank().to_numpy()
    if rx.std() == 0 or ry.std() == 0:
        return 0.0
    return float(np.corrcoef(rx, ry)[0, 1])


def profile(Zp: np.ndarray, labels: np.ndarray, g: int, ref_mean: np.ndarray) -> np.ndarray:
    """The standardized-mean deviation of group g's rows from `ref_mean`, per column."""
    return Zp[labels == g].mean(0) - ref_mean


def top_families(prof: np.ndarray, cols: list, top: int = TOP_FEATURES) -> list:
    """R58: [(family, sign)] of the `top` families by |deviation|, a family's value = its column of largest |deviation|."""
    fam = {}
    for k, c in enumerate(cols):
        f = family_of(c)
        if f not in fam or abs(prof[k]) > abs(fam[f]):
            fam[f] = float(prof[k])
    ranked = sorted(fam.items(), key=lambda kv: (-abs(kv[1]), kv[0]))[:top]
    return [(f, 1 if v >= 0 else -1) for f, v in ranked]


def survival(prof_primary: np.ndarray, prof_other: np.ndarray, cols: list) -> dict:
    fp, fo = top_families(prof_primary, cols), top_families(prof_other, cols)
    rho = spearman(prof_primary, prof_other)
    same = set(fp) == set(fo)
    if same and rho >= 0.8:
        verdict = "survives"
    elif rho < 0.5 or (not same and rho < 0.8):
        verdict = "lost"
    else:
        verdict = "partial"
    return {"verdict": verdict, "spearman": rho, "families_primary": fp, "families_other": fo, "same_families": same}


def median_intercentroid(cent: np.ndarray) -> float:
    ds = [float(np.sqrt(((cent[i] - cent[j]) ** 2).sum())) for i in range(len(cent)) for j in range(i + 1, len(cent))]
    return float(np.median(ds)) if ds else 0.0


def compare_mode_a(primary: dict, other: dict, primary_rows: set, added_tiers: set, tier_of_eid: dict) -> dict:
    """§5 mode A: the other run's groups matched to the primary's by the Hungarian assignment on centroid distance in the shared space; (b)
    the share of primary trades whose group changes (an unmatched primary group counts every one of its trades); (c) survival per matched
    pair against the primary's frozen means; (d) new groups."""
    cp, co = primary["centroids"], other["centroids"]
    cost = np.sqrt(_d2(cp, co))
    pairs = hungarian(cost)
    match = {i: j for i, j in pairs}
    rmatch = {j: i for i, j in pairs}
    lab_p = dict(zip(primary["eids"], primary["labels"].tolist()))
    lab_o = dict(zip(other["eids"], other["labels"].tolist()))
    common = [e for e in other["eids"] if e in lab_p and e in primary_rows]
    moved = [e for e in common if match.get(lab_p[e]) != lab_o[e]]
    unmatched_primary = [i for i in range(len(cp)) if i not in match]
    med = median_intercentroid(cp)
    new_groups = []
    for j in range(len(co)):
        rows_j = [e for e in other["eids"] if lab_o[e] == j]
        added = sum(1 for e in rows_j if tier_of_eid.get(e) in added_tiers)
        added_share = added / len(rows_j) if rows_j else 0.0
        far = (j not in rmatch) or (cost[rmatch[j], j] > med)
        if far or added_share >= NEW_GROUP_TIER_SHARE:
            new_groups.append({"group": j, "unmatched": j not in rmatch, "centroid_distance": None if j not in rmatch else float(cost[rmatch[j], j]),
                               "added_share": added_share, "n": len(rows_j)})
    surv = {}
    for i, j in pairs:
        surv[i] = survival(primary_profile_on(primary, i, other["common_cols"]), other["profiles_common"][j], other["common_cols"])
    return {"pairs": pairs, "moved": len(moved), "n_common": len(common), "moved_share": (len(moved) / len(common)) if common else 0.0,
            "unmatched_primary": unmatched_primary, "median_intercentroid": med, "new_groups": new_groups, "survival": surv, "cost": cost}


def compare_mode_b(primary: dict, other: dict) -> dict:
    """§5 mode B: the two partitions of the same rows on their contingency table; the Hungarian assignment (maximised overlap) gives the
    share that changes group; the adjusted Rand index beside; survival over the common columns (R61)."""
    lab_p = dict(zip(primary["eids"], primary["labels"].tolist()))
    common = [e for e in other["eids"] if e in lab_p]
    a = np.array([lab_p[e] for e in common])
    b = np.array([dict(zip(other["eids"], other["labels"].tolist()))[e] for e in common])
    kp, ko = len(primary["centroids"]), len(other["centroids"])
    ct = np.zeros((kp, ko))
    for x, y in zip(a, b):
        ct[x, y] += 1
    pairs = hungarian(-ct)
    matched = sum(ct[i, j] for i, j in pairs)
    surv = {i: survival(primary_profile_on(primary, i, other["common_cols"]), other["profiles_common"][j], other["common_cols"]) for i, j in pairs}
    new_groups = [{"group": j, "unmatched": True, "n": int(ct[:, j].sum())} for j in range(ko) if j not in {j for _i, j in pairs}]
    return {"pairs": pairs, "moved": int(len(common) - matched), "n_common": len(common), "moved_share": float(1 - matched / len(common)) if common else 0.0,
            "ari": adjusted_rand(a, b), "survival": surv, "new_groups": new_groups, "contingency": ct,
            "unmatched_primary": [i for i in range(kp) if i not in {i for i, _j in pairs}]}


def noise_floor(Zp: np.ndarray, primary: dict) -> dict:
    """§5: the primary against itself under 5 seeded refits and 5 bootstrap refits at its k (R56) -> the moved shares and the two floors."""
    k = len(primary["centroids"])
    n = len(Zp)
    seeded, boot = [], []
    for i in range(1, N_REFITS + 1):
        fit = kmeans(Zp, k, C.rng_for(f"step7_refit_{i}"))
        pairs = hungarian(np.sqrt(_d2(primary["centroids"], fit["centroids"])))
        match = {a: b for a, b in pairs}
        seeded.append(float(np.mean([match.get(p) != q for p, q in zip(primary["labels"], fit["labels"])])))
        rng = C.rng_for(f"step7_boot_{i}")
        idx = rng.integers(0, n, n)
        fit = kmeans(Zp[idx], k, rng)
        lab = nearest(Zp, fit["centroids"])
        pairs = hungarian(np.sqrt(_d2(primary["centroids"], fit["centroids"])))
        match = {a: b for a, b in pairs}
        boot.append(float(np.mean([match.get(p) != q for p, q in zip(primary["labels"], lab)])))
    return {"seeded": seeded, "bootstrap": boot, "floor_seeded": float(np.mean(seeded)), "floor_bootstrap": float(np.mean(boot)),
            "floor": max(float(np.mean(seeded)), float(np.mean(boot)))}


def consequence(cmp: dict, floor: float, artefact_new: set) -> dict:
    """§5's consequence table, applied: the moved share read as EXCESS over the floor; the descriptions; a new group that is not an artefact.
    `artefact_new` = the groups of the other run that read as an ARTEFACT under BOTH conditions of §5 (d) (artefact_groups, R71) — not merely
    the structural ones."""
    excess = cmp["moved_share"] - floor
    verdicts = [s["verdict"] for s in cmp["survival"].values()]
    lost = any(v == "lost" for v in verdicts) or bool(cmp["unmatched_primary"])
    partial = any(v == "partial" for v in verdicts)
    new_real = [g for g in cmp["new_groups"] if g["group"] not in artefact_new]
    new_art = [g for g in cmp["new_groups"] if g["group"] in artefact_new]
    if excess > MOVE_LINES[1] or lost or new_real:
        reading, meaning, action = ("> 25% move, a description lost, or a new group that is not an artefact",
                                    "the added rows carry a different behaviour or noise",
                                    "the new / changed groups are described; he decides whether the tier is included")
    elif excess > MOVE_LINES[0] or partial:
        reading, meaning, action = ("10-25% move, or one description partial", "the tier bends the groups",
                                    "both pictures are reported; which to carry to step 8 is his call")
    else:
        reading, meaning, action = ("<= 10% of primary trades move (over the floor) and every description survives",
                                    "the added tier does not change the picture", "INCLUDED in step 8's shares; its trades carry their tier label")
    return {"excess": excess, "reading": reading, "meaning": meaning, "action": action, "lost": lost, "partial": partial,
            "new_real": new_real, "new_artefact": new_art}


# ---- the runs ----------------------------------------------------------------------------------------------------------------------------
def run_rows(run: str, tiers: list, feats: dict) -> list:
    """The eids of a run (sorted), by its tiers and, for the year split / CONFIRMED, its extra condition."""
    rows = [tr for tr in tiers if tr["tier"] in RUN_TIERS[run]]
    if run == "year_2020":
        rows = [tr for tr in rows if tr["year"] == "2020"]
    elif run == "year_2021_22":
        rows = [tr for tr in rows if tr["year"] != "2020"]
    elif run == "confirmed":
        rows = [tr for tr in rows if T._b(tr["confirmed"])]
    return sorted(int(tr["eid"]) for tr in rows)


def fit_run(run: str, feats: dict, tiers: list, primary: dict | None, say, dry: bool = False, method: str = "registered", columns: str = "registered") -> dict:
    """One run end to end: assemble, standardize (the primary's maps / PCA in mode A; own in mode B), choose k, fit, profiles. Under a 7b
    `method` (never the default): the method's own reduction and k rule, group means as the centroids, its assignment rule for CONFIRMED."""
    mode = "low" if run == "edges_low" else "high" if run == "edges_high" else "middle"
    cols = run_columns(run, columns)
    eids = run_rows(run, tiers, feats)
    A = assemble(feats, eids, cols, mode)
    desc = None
    if columns == "pattern_free":                    # 7b §6 Fallback 1: the hold and the exit look-backs are DESCRIBED per group, never grouped on (06b R97)
        dcols = run_columns(run)
        desc = {"cols": dcols, "X": assemble(feats, A["eids"], dcols, mode, drop=False)["X"]}      # the run's registered columns on the SAME fitted rows
        if desc["X"].shape[0] != len(A["eids"]):
            raise GuardStop(f"{run}: the description matrix holds {desc['X'].shape[0]} rows for {len(A['eids'])} fitted rows (R97)")
    own = primary is None or run in MODE_B
    if own:
        maps = fit_maps(A["X"], cols)
    else:
        maps = primary["maps"]
    Z, extra, blanks = standardize(A["X"], cols, maps)
    if method != "registered":
        return _fit_run_7b(run, A, Z, cols, eids, maps, extra, blanks, own, primary, method, desc)
    pca = PCA(Z) if own else primary["pca"]
    Zp = pca.transform(Z)
    R = {"run": run, "cols": cols, "eids": A["eids"], "X": A["X"], "Z": Z, "Zp": Zp, "maps": maps, "pca": pca, "extra": extra, "blanks": blanks,
         "dropped": A["dropped"], "patterns": A["patterns"], "struct": A["struct"], "mode_b": run in MODE_B, "own_space": own, "desc": desc}
    if run == "confirmed":                                                                      # R57: assignment, no k choice
        R["labels"] = nearest(Zp, primary["centroids"])
        R["centroids"] = primary["centroids"]
        R["k"] = len(primary["centroids"])
        R["choice"] = None
    else:
        ch = choose_k(Zp, run, n_registered=len(eids))                                       # R70: the minimum from the registered n
        R["choice"] = ch
        R["k"] = ch["k"]
        if ch["k"] is not None:
            fit = ch["sweep"][ch["k"]]["fit"]
            R["labels"], R["centroids"] = fit["labels"], fit["centroids"]
    _profiles(R, Z, A, cols, own, primary)
    return R


def _fit_run_7b(run: str, A: dict, Z: np.ndarray, cols: list, eids: list, maps: dict, extra: dict, blanks: dict, own: bool, primary: dict | None, method: str,
                desc: dict | None = None) -> dict:
    """7b §7.2: the run under a carried method — the shared space of the primary (mode A) or the run's own (mode B), the method's k rule,
    group means as `centroids`, the method's assignment for CONFIRMED. The fit and the spaces travel on the run (`fit7b`, `spaces7b`);
    `desc` = the description matrix under `pattern_free` (06b R97)."""
    PW = power_module()
    kind = PW.SPACE_OF[method]
    if own:
        spaces = PW.Spaces(Z, f"step7b_real_M1_{run}_perm")                                    # 06b R81: the components are M1's
    else:
        spaces = primary["spaces7b"]
    red = spaces.red[kind]
    Zp = red.transform(Z)
    R = {"run": run, "cols": cols, "eids": A["eids"], "X": A["X"], "Z": Z, "Zp": Zp, "maps": maps, "pca": red, "extra": extra, "blanks": blanks,
         "dropped": A["dropped"], "patterns": A["patterns"], "struct": A["struct"], "mode_b": run in MODE_B, "own_space": own, "spaces7b": spaces,
         "method7b": method, "desc": desc}
    if run == "confirmed":                                                                      # R57 under the method's assignment rule
        R["labels"] = PW.assign(primary["fit7b"], Zp)
        R["centroids"] = primary["centroids"]
        R["k"] = len(primary["centroids"])
        R["choice"] = None
        R["fit7b"] = primary["fit7b"]
    else:
        n_min = min_group_size(len(eids))                                                       # R70
        fit = PW.run_method(method, spaces, n_min, f"step7b_real_{method}_{run}", True, top_space=red, Zp_given=Zp, Z=Z)
        R["fit7b"], R["choice"] = fit, None
        R["k"] = fit["k"] if fit["k"] >= 2 else None
        if R["k"] is not None:
            R["labels"], R["centroids"] = fit["labels"], fit["means"]
    _profiles(R, Z, A, cols, own, primary)
    return R


def _profiles(R: dict, Z: np.ndarray, A: dict, cols: list, own: bool, primary: dict | None) -> None:
    """The group profiles of a fitted run (R61: survival on the common columns against the primary's frozen means). `run_mean` is set
    whatever the fit read (a group-less primary still carries the mean the other runs' common-column profiles are measured against)."""
    R["run_mean"] = Z.mean(0)
    if R.get("labels") is not None:
        R["profiles"] = {g: profile(Z, R["labels"], g, R["run_mean"]) for g in range(R["k"])}
        if primary is not None:                      # R61: survival on the common columns, the primary's maps, against the primary's frozen means
            common = [c for c in cols if c in primary["cols"]]
            if own:
                Xc = A["X"][:, [cols.index(c) for c in common]]
                Zc, _e, _b = standardize(Xc, common, {c: primary["maps"][c] for c in common})
            else:
                Zc = Z[:, [cols.index(c) for c in common]]
            pref = np.array([primary["run_mean"][primary["cols"].index(c)] for c in common])
            R["profiles_common"] = {g: profile(Zc, R["labels"], g, pref) for g in range(R["k"])}
            R["common_cols"] = common


def primary_profile_on(primary: dict, i: int, common: list) -> np.ndarray:
    """The primary group's frozen profile restricted to the common columns."""
    src = primary["profiles_common"] if "profiles_common" in primary else primary["profiles"]        # an edge run standing in as "primary" (R66)
    cols = primary["common_cols"] if "profiles_common" in primary else primary["cols"]
    return src[i][[cols.index(c) for c in common]]


def structural_groups(R: dict) -> dict:
    """§3.4: per group, the share of rows under each structural pattern; 'structural' when one pattern holds 80% or more."""
    out = {}
    if R.get("labels") is None:
        return out
    for g in range(R["k"]):
        pats = [p for p, l in zip(R["patterns"], R["labels"]) if l == g]
        cnt = collections.Counter(pats)
        top = cnt.most_common(1)[0] if cnt else ("", 0)
        out[g] = {"patterns": cnt, "n": len(pats), "top_pattern": top[0], "top_share": (top[1] / len(pats)) if pats else 0.0,
                  "structural": bool(pats) and top[1] / len(pats) >= STRUCTURAL_LINE}
    return out


ARTEFACT_SEPARATION = 0.5                                                 # R71: half the run's spread (rank-normal scores have unit spread)


def pattern_free_columns(cols: list) -> list:
    """The columns the structural blank pattern does NOT drive: every entry column and the exit day's own columns (DAY_OWN). The exit
    look-backs (the pattern's own columns) and the hold (the pattern's own fact) are left out."""
    return [k for k, c in enumerate(cols) if c.startswith("entry_") or (c.startswith("exit_") and c[5:] in DAY_OWN)]


def artefact_groups(R: dict, structural: dict) -> dict:
    """R71 (§5 (d), BOTH conditions — review F3): a group is an ARTEFACT of the feature set's hold-dependence only when it is structural (§3.4:
    one blank pattern holds 80% or more) AND it does not separate on the entry side or the exit day's own columns — no pattern-free column
    carries a |standardized mean deviation| >= ARTEFACT_SEPARATION from the run's mean. A structural group that DOES separate there is a real
    group (it reads under the '> 25% / lost / new group' row, his decision). -> {g: {'structural', 'max_dev', 'max_col', 'separates', 'artefact'}}."""
    out = {}
    if R.get("labels") is None:
        return out
    free = pattern_free_columns(R["cols"])
    for g in range(R["k"]):
        prof = R["profiles"][g]
        if free:
            kk = max(free, key=lambda k: abs(prof[k]))
            max_dev, max_col = float(abs(prof[kk])), R["cols"][kk]
        else:
            max_dev, max_col = 0.0, ""
        sep = max_dev >= ARTEFACT_SEPARATION
        out[g] = {"structural": structural[g]["structural"], "max_dev": max_dev, "max_col": max_col, "separates": sep,
                  "artefact": structural[g]["structural"] and not sep}
    return out


def describe_group(R: dict, g: int, tiers_by_eid: dict, ranges: dict, structural: dict) -> dict:
    """§4.6: share; the five features farthest from the run's mean (standardized), the sign, the raw median in chart words; tier mix; band
    width; three examples (seeded); the structural pattern. A structural group's exit side is read on the day-own columns only."""
    labels, cols, X = R["labels"], R["cols"], R["X"]
    mem = labels == g
    eids = [e for e, m in zip(R["eids"], mem) if m]
    prof = R["profiles"][g]
    allowed = list(range(len(cols)))
    if structural[g]["structural"]:
        allowed = [k for k, c in enumerate(cols) if not (c.startswith("exit_") and c[5:] not in DAY_OWN)]
    order = sorted(allowed, key=lambda k: (-abs(prof[k]), cols[k]))[:TOP_FEATURES]
    feats = []
    for k in order:
        vals = X[mem, k]
        vals = vals[np.isfinite(vals)]
        med = float(np.median(vals)) if len(vals) else None
        feats.append({"column": cols[k], "deviation": float(prof[k]), "sign": "+" if prof[k] >= 0 else "-", "median": med,
                      "words": phrase(cols[k], med), "family": family_of(cols[k])})
    tier_mix = collections.Counter(tiers_by_eid[e]["tier"] for e in eids)
    conf = sum(1 for e in eids if T._b(tiers_by_eid[e]["confirmed"]))
    daily = sum(1 for e in eids if tiers_by_eid[e]["minute_coverage"] != "both")
    bw = {}
    for side, col in (("buy", "buy_range_width_pct"), ("sale", "sale_range_width_pct")):
        v = [float(tiers_by_eid[e][col]) for e in eids if tiers_by_eid[e][col] != ""]
        bw[side] = float(np.median(v)) if v else None
    rng = C.rng_for(f"step7_examples_{R['run']}_{g}")
    pick = sorted(rng.choice(len(eids), size=min(3, len(eids)), replace=False).tolist()) if eids else []
    examples = []
    for i in pick:
        e = eids[i]
        tr = tiers_by_eid[e]
        rb, rs = ranges.get((str(e), "buy"), {}), ranges.get((str(e), "sale"), {})
        examples.append(f"{e} {tr['sym']} buy {rb.get('lo', '')}..{rb.get('hi', '')} sale {rs.get('lo', '')}..{rs.get('hi', '')}")
    medians = {}
    dcols, dX = (R["desc"]["cols"], R["desc"]["X"]) if R.get("desc") else (cols, X)     # 7b R97: under pattern_free the medians cover the run's REGISTERED columns
    for k, c in enumerate(dcols):
        vals = dX[mem, k]
        vals = vals[np.isfinite(vals)]
        medians[c] = float(np.median(vals)) if len(vals) else None
    described_only = {c: medians[c] for c in dcols if c not in cols}                     # described per group, never grouped on (7b §6 Fallback 1)
    return {"group": g, "n": len(eids), "share": len(eids) / len(labels), "features": feats, "tier_mix": dict(tier_mix), "confirmed": conf,
            "daily_only_rows": daily, "band_width": bw, "examples": examples, "structural": structural[g], "medians": medians, "eids": eids,
            "described_only": described_only}


def expectation_descriptions(descs: list) -> dict:
    """R63: the §7 description expectation on group medians."""
    def med(d, c, missing):
        v = d["medians"].get(c)
        return missing if v is None else v
    early_buy = any(med(d, "entry_minute", 1e9) < 120 and med(d, "entry_dist_hi_10", -1e9) >= -3 and med(d, "entry_ret_10", -1e9) > 5 for d in descs)
    low_sale = any(med(d, "exit_pos_in_day", 1e9) < 0.3 and med(d, "hold_sessions_max", 1e9) <= 2 for d in descs)
    return {"early_buy_near_high_after_runup": early_buy, "sale_within_two_sessions_near_low": low_sale}


# ---- inputs ------------------------------------------------------------------------------------------------------------------------------
def load_inputs(say) -> dict:
    tiers = T.read_tsv(T.OUT_7["tiers"])
    ranges_rows = T.read_tsv(C.OUTPUTS["ranges"])
    for r in ranges_rows:
        for col in ("lo", "hi"):
            if r.get(col):
                C.seal_date(r[col], f"ranges.tsv eid {r['eid']} {col}")
    ranges = {(str(r["eid"]), str(r["side"])): r for r in ranges_rows}
    say(f"- tiers.tsv: {len(tiers)} positions ({C.sha(T.OUT_7['tiers'])[:16]}); 05's run printout ends RUN COMPLETE: {C.printout_ends(T.P05['run'], 'RUN COMPLETE')}")
    say(f"- ranges.tsv: {len(ranges_rows)} rows ({C.sha(C.OUTPUTS['ranges'])[:16]}) — the reachable band of every side (its resolution, range, band ends)")
    say("- check_r1_r5.tsv: never opened here (`confirmed` comes from tiers.tsv)")
    tally = collections.Counter()
    L = P.load_all(say, tally)
    P.preload_minutes(L, say)
    return {"tiers": tiers, "ranges": ranges, "L": L}


# ---- the printout ------------------------------------------------------------------------------------------------------------------------
def print_registration(say) -> None:
    say("\n## The features (05_tiers.STEP7_FEATURES, imported — never widened here)")
    for run in ("primary", "with_our_length"):
        f = FEATURES[run]
        say(f"- {run}: entry {len(f['entry'])}, exit {len(f['exit'])}, trade-level {', '.join(f['trade'])}; exit ret_N columns "
            f"{sum(1 for c in f['exit'] if c.startswith('ret_'))}; our_length columns {sum(1 for c in f['entry'] + f['exit'] if c in T.OUR_LENGTH)}")
    say("- held out: " + ", ".join(T.HELD_OUT) + "; every outcome column by the identifier scan (both name lists)")
    say("- the reference minute (§3.2): the volume-median reachable minute, its close (R48); daily-only: the largest-volume reachable session at "
        "(high + low + close) / 3, minute = the session's midpoint, flagged (R51)")
    say(f"- the method (§4): rank-normal with linear tails frozen on the primary; PCA to {VARIANCE_KEPT:.0%} whitened; k-means {N_STARTS} seeded starts; "
        f"k = the largest of {K_RANGE[0]}..{K_RANGE[-1]} with prediction strength >= {STRENGTH_LINE} over {N_HALVES} halves AND every group >= max(30, 5%)")
    say("### the 13 families (§5 (c)) -> columns (R58, side-agnostic)")
    fam = collections.defaultdict(list)
    for c in run_columns("with_our_length"):
        fam[family_of(c)].append(c)
    for f in FAMILY_NAMES:
        say(f"- {f}: {len(fam[f])} columns — " + ", ".join(fam[f]))


def print_coverage(feats: dict, tiers: list, say, claims) -> dict:
    """The feature coverage per tier, the blank counts (data / structural), the daily-only sides, the rows without features."""
    cols = run_columns("with_our_length")
    by_tier = collections.defaultdict(list)
    for tr in tiers:
        by_tier[tr["tier"]].append(int(tr["eid"]))
    say("\n## Feature rows per tier (the middle-minute description)")
    rows = []
    facts = {}
    for t in T.TIERS:
        es = by_tier[t]
        have = [e for e in es if feats[e].get("middle") is not None]
        fl = collections.Counter()
        for e in have:
            for side in ("entry", "exit"):
                for f in feats[e]["middle"]["flags"][side]:
                    fl[(side, f)] += 1
        none_side = len(es) - len(have)
        facts[t] = {"n": len(es), "with_features": len(have), "no_features": none_side, "flags": fl}
        rows.append((t, len(es), len(have), none_side, fl[("entry", "daily_only")], fl[("exit", "daily_only")], fl[("entry", "partial_resolution")] + fl[("exit", "partial_resolution")],
                     fl[("entry", "no_minute_bar_in_reach")] + fl[("exit", "no_minute_bar_in_reach")]))
    table(say, ["tier", "positions", "with features", "no features (no reachable range on a side)", "entry daily-only", "exit daily-only", "partial sides", "no minute bar in reach"], rows)
    say("\n### coverage per feature column per tier — share of the tier's feature rows with a value (exit look-backs: among the rows where the look-back is DEFINED; the structural share beside)")
    cov_rows = []
    for c in cols:
        r = [c]
        for t in T.TIERS:
            have = [e for e in by_tier[t] if feats[e].get("middle") is not None]
            if not have:
                r.append("n/a")
                continue
            if c.startswith("entry_"):
                vals = [feats[e]["middle"]["entry"].get(c[6:], "") for e in have]
                present = sum(1 for v in vals if v != "")
                r.append(pct(present, len(have)))
            elif c.startswith("exit_"):
                defined = [e for e in have if c[5:] not in feats[e]["middle"]["struct"]]
                present = sum(1 for e in defined if feats[e]["middle"]["exit"].get(c[5:], "") != "")
                r.append(f"{pct(present, len(defined))} (struct {pct(len(have) - len(defined), len(have))})" if len(defined) < len(have) else pct(present, len(defined)))
            else:
                r.append(pct(sum(1 for e in have if feats[e]["middle"]["trade"].get(c, "") != ""), len(have)))
        cov_rows.append(tuple(r))
    table(say, ["column"] + list(T.TIERS), cov_rows)
    say("\n### structural blank patterns (the exit look-backs defined, by hold) per tier — share of feature rows")
    pat_rows = []
    for t in T.TIERS:
        have = [e for e in by_tier[t] if feats[e].get("middle") is not None]
        cnt = collections.Counter(structural_pattern(feats[e]["meta"]["hold_sessions_min"], feats[e]["meta"]["hold_sessions_max"]) for e in have)
        for k_, v_ in sorted(cnt.items(), key=lambda kv: -kv[1]):
            pat_rows.append((t, k_, v_, pct(v_, len(have))))
    table(say, ["tier", "exit look-backs defined (N)", "n", "share"], pat_rows)
    return facts


def print_sweep(choice: dict, say, label: str) -> None:
    say(f"\n### k sweep — {label} (n = {choice['n']} fitted rows of {choice['n_registered']} registered, minimum group size {choice['n_min']} = max(30, 5% of the registered n) — R70)")
    rows = [(k, f"{s['strength']:.3f}", "yes" if s["strength_ok"] else "no", s["min_size"], "yes" if s["size_ok"] else "no", " ".join(str(x) for x in s["sizes"]))
            for k, s in choice["sweep"].items()]
    table(say, ["k", "prediction strength", f">= {STRENGTH_LINE}", "smallest group", ">= minimum", "group sizes"], rows)
    say(f"- k chosen by the rule (the largest passing both lines): {choice['k'] if choice['k'] is not None else 'NONE — no stable grouping (§1.2)'}")


def print_run_sweep(R: dict, say, label: str, tiers: list, feats: dict) -> None:
    """The run's k sweep: the registered prediction-strength table, or the carried 7b method's own (06b print_fit)."""
    if R.get("method7b"):
        power_module().print_fit(R["fit7b"], say, label, len(R["eids"]), min_group_size(len(run_rows(R["run"], tiers, feats))))
    else:
        print_sweep(R["choice"], say, label)


def print_descriptions(R: dict, descs: list, structural: dict, say) -> None:
    for d in descs:
        s = d["structural"]
        say(f"\n### {R['run']} — group {d['group']}: {d['n']} trades ({d['share']:.1%})" + (" — STRUCTURAL (exit read on the day-own columns only)" if s["structural"] else ""))
        for f in d["features"]:
            say(f"- {f['words']}  [{f['column']} {f['sign']}{abs(f['deviation']):.2f} sd, median {f4(f['median'])}; family: {f['family']}]")
        say(f"- tier mix: {', '.join(f'{k} {v}' for k, v in sorted(d['tier_mix'].items()))}; confirmed by his words: {d['confirmed']}; daily-only on a side: {d['daily_only_rows']}"
            + (" — MOSTLY DAILY-ONLY (a feature artefact, not a behaviour)" if d["n"] and d["daily_only_rows"] / d["n"] > 0.5 else ""))
        say(f"- band width (median % of price): buy {f4(d['band_width']['buy'])}, sale {f4(d['band_width']['sale'])}")
        say(f"- structural pattern: {s['top_pattern']!r} holds {s['top_share']:.0%} (" + ", ".join(f"{k!r} {v}" for k, v in s["patterns"].most_common(4)) + ")")
        if d.get("described_only"):                                                       # 7b §6 Fallback 1 (06b R97): never grouped on, described here
            say("- described, never grouped on (7b §6 Fallback 1 — the hold and the exit look-backs; group medians): "
                + ", ".join(f"{c} {f4(m)}" for c, m in d["described_only"].items()))
        say("- examples (for him to pull up): " + "; ".join(d["examples"]))


def print_comparison(name: str, cmp: dict, cons: dict | None, R: dict, primary: dict, say) -> None:
    say(f"\n### stability — {name} (k = {R['k']} vs the primary's {primary['k']}; {'mode B, partition-based' if R['mode_b'] else 'mode A, centroid-matched'})")
    say(f"- matched pairs (primary -> other): " + ", ".join(f"{i}->{j}" for i, j in cmp["pairs"]) + (f"; primary groups left unmatched: {cmp['unmatched_primary']} (every trade counted as moved)" if cmp["unmatched_primary"] else ""))
    say(f"- primary trades whose group changes: {cmp['moved']} of {cmp['n_common']} = {cmp['moved_share']:.1%}" + (f"; adjusted Rand {cmp['ari']:.3f}" if "ari" in cmp else ""))
    for i, s in cmp["survival"].items():
        say(f"- group {i}: description {s['verdict'].upper()} (Spearman {s['spearman']:.2f}; primary families {[f'{f}{'+' if sg > 0 else '-'}' for f, sg in s['families_primary']]}; "
            f"other {[f'{f}{'+' if sg > 0 else '-'}' for f, sg in s['families_other']]})")
    if cmp["new_groups"]:
        for g in cmp["new_groups"]:
            say(f"- NEW group {g['group']} of the other run: n = {g['n']}" + ("" if g.get("unmatched") else f", centroid distance {g['centroid_distance']:.2f} vs the primary's median inter-centroid {cmp.get('median_intercentroid', 0):.2f}")
                + (f", rows from the added tier {g['added_share']:.0%}" if "added_share" in g else ""))
    else:
        say("- no new group")
    if cons is not None:
        say(f"- read as EXCESS over the floor: {cons['excess']:+.1%} -> {cons['reading']} => {cons['meaning']}; consequence: {cons['action']}"
            + (f"; structural new group(s) {[g['group'] for g in cons['new_artefact']]} reported as an artefact of the feature set's hold-dependence" if cons["new_artefact"] else ""))


# ---- pins, gates, main -------------------------------------------------------------------------------------------------------------------
def module_shas_line() -> str:
    return C.modules_line(MODULE_FILES_G)


def pins_g(doc: str = None, dry_path: str = None) -> dict:
    """05's pins (step 5's inputs and modules, both doc bodies, step 5's outputs, 6b's files, 05_tiers.py, the outcome-name list, 05's dry-run
    printout) plus 05's run printout, tiers.tsv, 01_points.py (already among 05's), this module and this stage's dry-run printout."""
    p = T.pins_7(doc or DOC7, T.P05["dry"])
    p["run7_tiers_printout"] = T._sha_or_absent(T.P05["run"])
    p["tiers"] = T._sha_or_absent(T.OUT_7["tiers"])
    p["06_groups.py"] = C.sha(os.path.join(HERE, "06_groups.py"))
    p["dryrun7g_printout"] = T._sha_or_absent(dry_path or P06["dry"])
    return p


def stage_pin_keys(pins: dict, doc: str = None) -> list:
    base = set(C.pins(doc or DOC7, include_outputs=False))
    return [k for k in pins if k not in base]


def ledger_stage_rows(prefix: str) -> list:
    """The ledger's stages starting with `prefix` (7b §11: a --run is refused when a `step7_groups` row exists)."""
    if not os.path.exists(C.LEDGER):
        return []
    rows = pd.read_csv(C.LEDGER, sep="\t", dtype=str, keep_default_na=False).to_dict("records")
    return [r["stage"] for r in rows if r["stage"].startswith(prefix)]


def run_gate(doc: str = None, paths: dict = None, method: str = "registered", columns: str = "registered") -> list:
    """The reasons a --run is refused (empty = go). 7b §11 adds: 06b_power.txt ends POWER COMPLETE (naming the method and columns when
    non-default; not naming a carried method when default — 06b R90) and no `step7_groups` ledger row exists."""
    paths = paths or P06
    doc = doc or DOC7
    problems = []
    if method != "registered" or columns != "registered":
        problems += power_module().named_by_power_complete(method, columns, path=paths.get("power", P06["power"]))
    else:
        problems += power_module().default_run_gate(paths.get("power", P06["power"]))
    rows = ledger_stage_rows(STAGE_G)
    if rows:
        problems.append("a step7_groups ledger row exists (the run happens once): " + ", ".join(rows))
    if not C.dry_run_complete(paths["dry"]):
        problems.append(f"the step-7 groups dry run has not completed ({os.path.basename(paths['dry'])})")
    else:
        mm = C.printout_mismatches(paths["dry"])
        if mm is None:
            problems.append("the dry run's RESULT line is missing or unreadable")
        elif mm > 0:
            problems.append(f"the dry run ended with {mm} MISMATCH")
        ml = C.printout_line(paths["dry"], "- modules: ")
        if ml != module_shas_line():
            problems.append("the dry run was made by other code than the modules on disk (or carries no module line): rerun --dry-run first"
                            + (f" (dry run: {ml})" if ml else ""))
    if not C.printout_ends(T.P05["run"], "RUN COMPLETE"):
        problems.append("05_tiers.py --run has not completed (05_tiers.txt must end RUN COMPLETE)")          # R67
    if not os.path.exists(doc):
        problems.append(f"the step-7 registration is missing ({doc})")
        return problems
    pins = pins_g(doc, paths["dry"])
    miss = C.freeze_missing(doc, pins)
    if miss:
        problems.append("pins not below the step-7 doc's freeze marker (freeze first, --print-pins, paste): " + ", ".join(miss))
    absent = [k for k in stage_pin_keys(pins, doc) if pins[k] == "ABSENT"]
    if absent:
        problems.append("pins reading ABSENT (the file must exist and be pinned): " + ", ".join(absent))
    bad = C.ledger_verify() if os.path.exists(C.LEDGER) else ["ledger missing (05's run writes it)"]
    if bad:
        problems.append("ledger: " + "; ".join(bad))
    existing = [q for q in list(OUT_G.values()) + [paths["run"]] if os.path.exists(q)]
    if existing:
        problems.append("outputs exist: " + ", ".join(existing))
    return problems


def write_tsv(rows: list, cols: list, path: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    pd.DataFrame(rows, columns=cols).to_csv(path + ".partial", sep="\t", index=False)
    os.replace(path + ".partial", path)


FEATURE_OUT_COLS = ["eid", "sym", "tier", "confirmed", "mode", "entry_date", "entry_minute", "exit_date", "exit_minute",
                    "entry_flags", "exit_flags", "structural_pattern"] + run_columns("with_our_length")     # R74: no price column (review F6)


def feature_out_rows(feats: dict, tiers: list) -> list:
    out = []
    for tr in tiers:
        e = int(tr["eid"])
        for mode in ("middle", "low", "high"):
            rec = feats[e].get(mode)
            if rec is None:
                continue
            row = {"eid": e, "sym": tr["sym"], "tier": tr["tier"], "confirmed": tr["confirmed"], "mode": mode,
                   "entry_date": rec["at"]["entry"][0], "entry_minute": rec["at"]["entry"][1],                    # R74: the prices stay out of every
                   "exit_date": rec["at"]["exit"][0], "exit_minute": rec["at"]["exit"][1],                        # step-7 output (ranges.tsv holds the bands)
                   "entry_flags": "|".join(sorted(rec["flags"]["entry"])), "exit_flags": "|".join(sorted(rec["flags"]["exit"])),
                   "structural_pattern": structural_pattern(tr["hold_sessions_min"], tr["hold_sessions_max"])}
            for c in run_columns("with_our_length"):
                row[c] = rec["entry"].get(c[6:], "") if c.startswith("entry_") else rec["exit"].get(c[5:], "") if c.startswith("exit_") else rec["trade"].get(c, "")
            out.append(row)
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry-run", action="store_true")
    g.add_argument("--print-pins", action="store_true")
    g.add_argument("--run", action="store_true")
    ap.add_argument("--method", choices=METHODS_7B, default="registered", help="7b §11: the carried method (refused until POWER COMPLETE names it)")
    ap.add_argument("--columns", choices=COLUMNS_7B, default="registered", help="7b §7.3: the column set (refused until POWER COMPLETE names it)")
    a = ap.parse_args(argv)
    if a.print_pins:
        lines = [f"{k}\t{v}" for k, v in pins_g().items()]
        print("\n".join(lines))
        with open(P06["pins"], "w", encoding="utf-8") as fh:
            fh.write("\n".join(lines) + "\n")
        print(f"(written to {P06['pins']})")
        return 0
    say = Say()
    stage = "DRY RUN" if a.dry_run else "RUN"
    default_7b = a.method == "registered" and a.columns == "registered"
    dry_path = dry_path_for(a.method, a.columns)
    say(f"# #711 as-is STEP 7 (part 2, the groups) — {stage} ({time.strftime('%Y-%m-%d %H:%M')})")
    say("Guards: no network, no production server, no paid call, nothing after 2024-12-31, the seven outcome folders never opened, nothing "
        "imported from the rule folders. No outcome of any trade is read, computed or printed (both name lists are scanned); no rule, setup "
        "name or pattern label enters; the groups are descriptions in chart words, never a rule.")
    refused_to = dry_path if a.dry_run else P06["refused"]
    hits = C.scan_identifiers([os.path.join(HERE, n) for n in SCAN_FILES_G], T.forbidden_all())
    if hits:
        say("IDENTIFIER SCAN FAILED: " + "; ".join(f"{os.path.basename(p)}:{ln} {t}" for p, ln, t in hits))
        say.write(refused_to)
        return 2
    say("- identifier scan: clean (the §3.1 names and the outcome names are absent from the step-7 modules: " + ", ".join(SCAN_FILES_G) + ")")
    loaded = C.rule_modules_loaded()
    if loaded:
        say("RULE MODULE LOADED (guard 3): " + ", ".join(loaded))
        say.write(refused_to)
        return 2
    say("- import belt: no rule module in sys.modules")
    say("- modules: " + module_shas_line())
    if not default_7b:                                                                       # 7b §11: EVERY real-data stage, the dry run included
        problems = power_module().named_by_power_complete(a.method, a.columns, path=P06["power"])
        if problems:
            for pr in problems:
                say("REFUSED: " + pr)
            say.write(refused_to)
            return 3
        say(f"- 7b gate: 06b_power.txt ends POWER COMPLETE naming {a.method} on {a.columns}, pinned below the 7b doc's marker")
    if a.run:
        problems = run_gate(paths=dict(P06, dry=dry_path), method=a.method, columns=a.columns)
        if problems:
            for pr in problems:
                say("REFUSED: " + pr)
            say.write(P06["refused"])
            return 3
        say("- run gates: the dry run completed with 0 MISMATCH; 05's run complete; every pin (inputs, modules, both doc bodies, tiers.tsv, the "
            "dry-run printouts) is below the step-7 doc's freeze marker; the ledger verifies; no output exists; 06b_power.txt ends POWER COMPLETE; "
            "no step7_groups ledger row")
    say("\n## Inputs")
    I = load_inputs(say)
    tiers, ranges, L = I["tiers"], I["ranges"], I["L"]
    tiers_by_eid = {int(tr["eid"]): tr for tr in tiers}
    tier_of_eid = {e: tr["tier"] for e, tr in tiers_by_eid.items()}
    print_registration(say)
    if not default_7b:
        say(f"- 7b (§7): the carried method {a.method} on the {a.columns} columns — 06b_power.py's implementation, the registered settings; group means stand "
            f"where centroids are read; the noise floor refits the carried method; primary columns {len(run_columns('primary', a.columns))}")
    feats = build_features(L, tiers, ranges, say)
    checks = feats.pop("_checks")
    claims = Claims(say) if a.dry_run else None
    facts = print_coverage(feats, tiers, say, claims)

    # ---- the primary: assemble, standardize, reduce, the k sweep ----
    say("\n## The primary run (HIGH + MEDIUM) — standardization, reduction, the k sweep")
    primary = fit_run("primary", feats, tiers, None, say, method=a.method, columns=a.columns)
    say(f"- rows {len(primary['eids'])} of {len(run_rows('primary', tiers, feats))} (dropped by the quarter rule: {len(primary['dropped'])}"
        + (": " + "; ".join(f"{e} ({s:.0%}, {why})" for e, s, why in primary["dropped"][:12]) if primary["dropped"] else "") + ")")
    dropped_short = sum(1 for e, _s, _w in primary["dropped"] if "short_history" in (ranges.get((str(e), "buy"), {}).get("flags", "") + ranges.get((str(e), "sale"), {}).get("flags", "")))
    say(f"- the dropped rows carry `short_history` on a side (fewer than 60 prior sessions — a recent listing): {dropped_short} of {len(primary['dropped'])} (a readout; the registration states no count)")
    say(f"- columns {len(primary['cols'])}; blanks after the maps (zero-filled): {sum(primary['blanks'].values())} cells "
        f"({sum(int(primary['struct'][:, k].sum()) for k in range(len(primary['cols'])))} structural, the rest data)")
    if default_7b:
        say(f"- PCA: {primary['pca'].m} components carry {primary['pca'].explained:.1%} of the variance (whitened)")
        print_sweep(primary["choice"], say, "PRIMARY")
    else:
        say(f"- reduction ({primary['fit7b']['space']}): {primary['pca'].m} components carry {primary['pca'].explained:.1%} of the variance")
        power_module().print_fit(primary["fit7b"], say, "PRIMARY", len(primary["eids"]), min_group_size(len(run_rows("primary", tiers, feats))))

    # ---- extrapolation under the primary's maps, per tier (a fact about the maps, printed in both stages) ----
    say("\n## Values outside the primary's range under its maps (linear tails, never clipped), per added tier")
    ex_rows = []
    sizes = {}
    for t in ("ONE-STREAM", "LOW"):
        es = sorted(int(tr["eid"]) for tr in tiers if tr["tier"] == t)
        A = assemble(feats, es, primary["cols"])
        Zt, extra, _b = standardize(A["X"], primary["cols"], primary["maps"])
        n = len(A["eids"])
        over = [(c, v) for c, v in extra.items() if v]
        for c, v in sorted(over, key=lambda cv: -cv[1])[:15]:
            ex_rows.append((t, n, c, v, pct(v, n), "over 5%" if n and v / n > 0.05 else ""))
        facts[t]["extrapolated"] = {c: v for c, v in over}
        facts[t]["n_fit_rows"] = n
        facts[t]["dropped"] = A["dropped"]
        sizes[t] = score_sizes(Zt, primary["cols"], primary["maps"], A["eids"])
    table(say, ["tier", "fit rows", "feature", "extrapolated", "share", "flag"], ex_rows)
    for t in ("ONE-STREAM", "LOW"):
        over5 = [c for c, v in facts[t]["extrapolated"].items() if facts[t]["n_fit_rows"] and v / facts[t]["n_fit_rows"] > 0.05]
        say(f"- {t}: {len(facts[t]['dropped'])} rows dropped by the quarter rule ({collections.Counter(w for _e, _s, w in facts[t]['dropped'])}); "
            f"features with over 5% of the rows extrapolated: {over5 or 'none'}")
    say("\n### how large the extrapolated scores get (R72 — review F4; the tail rule is the registered one, this is a readout for his fork, never a clip)")
    say_score_sizes(say, "PRIMARY (its own maps; no value is outside its range)", score_sizes(primary["Z"], primary["cols"], primary["maps"], primary["eids"]))
    for t in ("ONE-STREAM", "LOW"):
        say_score_sizes(say, f"{t} under the primary's maps", sizes[t])
    size_rows = [(t, c, f"{v:.4g}", kn) for t in ("ONE-STREAM", "LOW") for c, v, kn in sizes[t]["top"]]
    table(say, ["tier", "feature", "max |score|", "knots in the primary's map"], size_rows)
    say("- a map resting on few knots (short exit look-backs defined on few primary holds) or whose outer knots sit close carries a steep tail; run as registered, a row "
        "beyond |10| on several columns owns its distance in the whitened space — one of the three facts his fork on + ONE-STREAM / + LOW rests on (R72, R73)")

    # ---- entry and exit described on ONE session (R73 — review F5): a readout for his fork, printed in both stages ----
    say("\n## Entry and exit described on the same session (R73 — review F5)")
    say("- a same-session round trip (hold_sessions_max = 0) has every exit look-back DEFINED by the registered rule (§3.3 (b)); its entry and exit then share each reference "
        "(the prior close, the N-session highs / lows / averages, the day's range), so an entry look-back minus the matching exit look-back is the entry-to-exit move. Nothing "
        "here computes it; the primary holds no such trade; the + ONE-STREAM and + LOW runs would — surfaced for his decision before either runs, a remedy is a "
        "re-registration below the marker")
    ss_rows = []
    for t in T.TIERS:
        es = [int(tr["eid"]) for tr in tiers if tr["tier"] == t]
        have = [e for e in es if feats[e].get("middle") is not None]
        same_d = [e for e in have if feats[e]["middle"]["at"]["entry"][0] == feats[e]["middle"]["at"]["exit"][0]]
        all_def = [e for e in same_d if not feats[e]["middle"]["struct"]]
        h0 = sum(1 for e in es if T.hold_bucket(tiers_by_eid[e]["hold_sessions_max"]) == "0")
        facts[t]["same_session"] = {"described_same_session": len(same_d), "all_lookbacks_defined": len(all_def), "hold0_tiers": h0}
        ss_rows.append((t, len(have), len(same_d), len(all_def), h0))
    table(say, ["tier", "feature rows", "entry and exit on one session", "of those, every exit look-back defined (hold 0)", "hold 0 in tiers.tsv (with or without features)"], ss_rows)

    if claims is not None:
        prim_eids = run_rows("primary", tiers, feats)
        say("\n## Claims")
        claims("in-span positions (tiers.tsv rows)", 1588, len(tiers))
        for t, n in T.PROPOSED.items():
            claims(f"tier {t} = the locked count", n, sum(1 for tr in tiers if tr["tier"] == t))
        claims("primary rows (HIGH + MEDIUM)", 677, len(prim_eids))
        claims("primary rows by buy year 2020 / 2021-22", (347, 330), (len(run_rows("year_2020", tiers, feats)), len(run_rows("year_2021_22", tiers, feats))))
        claims("+ ONE-STREAM rows", 1187, len(run_rows("plus_one_stream", tiers, feats)))
        claims("+ LOW rows", 1588, len(run_rows("plus_low", tiers, feats)))
        claims("primary feature columns (entry / exit)", (40, 34), (len(FEATURES["primary"]["entry"]), len(FEATURES["primary"]["exit"])))
        claims("with our_length feature columns (entry / exit)", (50, 44), (len(FEATURES["with_our_length"]["entry"]), len(FEATURES["with_our_length"]["exit"])))
        claims("exit feature sets carry no ret_N", 0, sum(1 for run in FEATURES for c in FEATURES[run]["exit"] if c.startswith("ret_")))
        claims("primary feature set carries no our_length column", 0, sum(1 for c in FEATURES["primary"]["entry"] + FEATURES["primary"]["exit"] if c in T.OUR_LENGTH))
        claims("the 13 families cover every column", 13, len({family_of(c) for c in run_columns("with_our_length")}))
        claims("minimum group size for the primary (5% of the registered 677, R70)", 34,
               primary["choice"]["n_min"] if primary.get("choice") else min_group_size(len(prim_eids)))      # 7b: a carried method carries no `choice` (06b R96)
        claims("every primary position has features on both sides", 677, sum(1 for e in prim_eids if feats[e]["middle"] is not None))
        claims("primary positions with NO exit look-back defined / the prior session only", (128, 196),
               (sum(1 for e in prim_eids if structural_pattern(tiers_by_eid[e]["hold_sessions_min"], tiers_by_eid[e]["hold_sessions_max"]) == "(none)"),
                sum(1 for e in prim_eids if structural_pattern(tiers_by_eid[e]["hold_sessions_min"], tiers_by_eid[e]["hold_sessions_max"]) == "1")))
        claims("primary rows daily-only on one side / both (tiers.tsv minute coverage)", (22, 2),
               (sum(1 for e in prim_eids if tiers_by_eid[e]["minute_coverage"] == "one"), sum(1 for e in prim_eids if tiers_by_eid[e]["minute_coverage"] == "none")))
        claims("primary same-session round trips", 0, sum(1 for e in prim_eids if T.hold_bucket(tiers_by_eid[e]["hold_sessions_max"]) == "0"))
        claims("LOW rows minute coverage one side / none", (147, 191), (sum(1 for tr in tiers if tr["tier"] == "LOW" and tr["minute_coverage"] == "one"),
                                                                        sum(1 for tr in tiers if tr["tier"] == "LOW" and tr["minute_coverage"] == "none")))
        low_none = collections.Counter(tr["tier_reason"] for tr in tiers if tr["tier"] == "LOW" and feats[int(tr["eid"])]["middle"] is None)
        claims("LOW positions without features = EXACTLY the 153 rangeless (no bars) + the 31 inverted (no reachable range) and no other reason (§2.1; review F8)",
               (153, 31, 184), (low_none["no_range"], low_none["inverted"], sum(low_none.values())))
        claims("same-session round trips (hold 0) by tier HIGH / MEDIUM / ONE-STREAM / LOW (§2.3: 220 + 39 = 259)", (0, 0, 220, 39),
               tuple(facts[t]["same_session"]["hold0_tiers"] for t in T.TIERS))
        claims("ONE-STREAM feature rows with entry and exit described on one session AND every exit look-back defined = its 220 same-session round trips (R73)", 220,
               facts["ONE-STREAM"]["same_session"]["all_lookbacks_defined"])
        conf = [tr for tr in tiers if T._b(tr["confirmed"])]
        claims("confirmed positions", 53, len(conf))
        claims("confirmed by tier HIGH / MEDIUM / ONE-STREAM / LOW", (18, 15, 4, 16), tuple(sum(1 for tr in conf if tr["tier"] == t) for t in T.TIERS))
        with_f = [tr for tr in conf if feats[int(tr["eid"])]["middle"] is not None]
        claims("confirmed positions with features (assignable)", 47, len(with_f))
        claims("assignable confirmed daily-only on a side / unassignable with no bars on a side (§2.4: 9 / 6 no_range)", (9, 6),
               (sum(1 for tr in with_f if tr["minute_coverage"] != "both"), sum(1 for tr in conf if feats[int(tr["eid"])]["middle"] is None and tr["tier_reason"] == "no_range")))
        claims("assignable confirmed inside the primary / outside", (33, 14), (sum(1 for tr in with_f if tr["tier"] in PRIMARY_TIERS), sum(1 for tr in with_f if tr["tier"] not in PRIMARY_TIERS)))
        claims("re-derived band equals ranges.tsv on every described side (lo, hi)", 0, checks["range_mismatch"])
        claims("sweep N = 20 equals the frozen 20-session column on every described side", 0, checks["sweep20_mismatch"])
        claims("re-derived band ends equal ranges.tsv's range_lo_minute / range_hi_minute on the primary's sides", (0, 0), (checks["lo_at_mismatch"], checks["hi_at_mismatch"]))
        claims("hold_sessions_max of the primary never below 1 (so a same-day hold extrapolates below the lowest knot)", True,
               float(np.nanmin(primary["X"][:, primary["cols"].index("hold_sessions_max")])) >= 1 if "hold_sessions_max" in primary["cols"]
               else float(min(float(tr["hold_sessions_max"]) for tr in tiers if tr["tier"] in PRIMARY_TIERS)) >= 1)
        if default_7b:                                                                    # 7b §11 (06b R89): the default path reproduces the pinned reference
            ok, why = power_module().reproduces_reference(say.lines)
            claims("the k-sweep block and the 32 claim lines above reproduce the reference dry run (8352c78c, sha e578a700) line for line (7b §11)", True, ok)
            if not ok:
                say(f"  first difference: {why}")
        say("")
        say(claims.result())
        say("DRY RUN COMPLETE")
        say.write(dry_path)
        return 0

    # ---- the RUN: every run of §5, the descriptions, the stability tables, the consequence table, the §7 scoring ----
    results = {"primary": primary}
    if primary["k"] is None:
        say("\n## NO STABLE GROUPING on the primary (§1.2): the confident trades are described as one population — the distribution of each feature")
        rows = []
        for k, c in enumerate(primary["cols"]):
            v = primary["X"][:, k]
            v = v[np.isfinite(v)]
            if len(v):
                rows.append((c, len(v), f4(np.percentile(v, 25)), f4(np.median(v)), f4(np.percentile(v, 75))))
        table(say, ["feature", "n", "q1", "median", "q3"], rows)
        say("- the other runs are not compared (no primary groups to compare against); his call whether to run on + ONE-STREAM or stop")
    structural_p = structural_groups(primary) if primary["k"] is not None else {}
    descs_all, stab_rows, group_rows = {}, [], []
    if primary["k"] is not None:
        say(f"\n## The groups of the primary run (k = {primary['k']})")
        descs = [describe_group(primary, g, tiers_by_eid, ranges, structural_p) for g in range(primary["k"])]
        descs_all["primary"] = descs
        print_descriptions(primary, descs, structural_p, say)
        if default_7b:
            floor = noise_floor(primary["Zp"], primary)
        else:
            floor = power_module().noise_floor_7b(primary, min_group_size(len(run_rows("primary", tiers, feats))))      # 7b §7.2 (06b R91)
        say("\n## The noise floor — the primary against itself" + ("" if default_7b else f" (the carried method {a.method} refitted)"))
        say(f"- 5 seeded refits (other starts, same rows): moved {', '.join(f'{x:.1%}' for x in floor['seeded'])} -> floor {floor['floor_seeded']:.1%}")
        say(f"- 5 bootstrap refits (fit on a resample, every row assigned): moved {', '.join(f'{x:.1%}' for x in floor['bootstrap'])} -> floor {floor['floor_bootstrap']:.1%}")
        if floor.get("boot_rows"):                                                   # 06b R102 (7b Re-registration 1 item 3): the split test on the resample's distinct rows
            say(f"- the carried split test refits on each resample's DISTINCT rows ({', '.join(str(x) for x in floor['boot_rows'])} of {len(primary['eids'])}), "
                "then assigns every row by nearest leaf mean (7b Re-registration 1 item 3)")
        say(f"- the lines below read as EXCESS over the larger floor: {floor['floor']:.1%}")
        results["floor"] = floor
        prim_set = set(primary["eids"])
        for run in RUNS[1:]:
            say(f"\n## Run: {run}")
            R = fit_run(run, feats, tiers, primary, say, method=a.method, columns=a.columns)
            results[run] = R
            say(f"- rows {len(R['eids'])} (dropped by the quarter rule: {len(R['dropped'])}" + (f"; by reason {collections.Counter(w for _e, _s, w in R['dropped'])}" if R["dropped"] else "") + ")"
                + (f"; own maps and reduction on these rows ({R['pca'].m} components, {R['pca'].explained:.1%})" if R["own_space"] else "; the primary's frozen maps and reduction")
                + f"; values extrapolated beyond the primary's range: {sum(R['extra'].values())} cells" + (f" (top: {', '.join(f'{c} {v}' for c, v in sorted(R['extra'].items(), key=lambda cv: -cv[1])[:5] if v)})" if sum(R["extra"].values()) else ""))
            say_score_sizes(say, "score sizes (R72)", score_sizes(R["Z"], R["cols"], R["maps"], R["eids"]))
            if run == "confirmed":
                shares_p = np.bincount(primary["labels"], minlength=primary["k"]) / len(primary["labels"])
                shares_c = np.bincount(R["labels"], minlength=primary["k"]) / max(1, len(R["labels"]))
                inside = [e for e in R["eids"] if e in prim_set]
                say(f"- {len(inside)} confirmed trades are rows of the primary fit (their fitted group), {len(R['eids']) - len(inside)} placed by the nearest primary centroid (R57)")
                rows = []
                flagged = []
                for g_ in range(primary["k"]):
                    d = (shares_c[g_] - shares_p[g_]) * 100
                    n_c = int((R["labels"] == g_).sum())
                    fl = "UNCHECKED BY HIS WORDS" if n_c == 0 else ("differs by over 15 points" if abs(d) > 15 else "")
                    if fl:
                        flagged.append((g_, fl))
                    rows.append((g_, f"{shares_p[g_]:.1%}", n_c, f"{shares_c[g_]:.1%}", f"{d:+.1f}", fl))
                table(say, ["group", "primary share", "confirmed n", "confirmed share", "difference (points)", "flag"], rows)
                say("- consequence: " + ("the groups are not evenly checked by his words — flagged, nothing dropped: " + "; ".join(f"group {g_} {f}" for g_, f in flagged) if flagged else "every group holds confirmed trades within 15 points of the primary's share"))
                results[run]["flagged"] = flagged
                for e, l in zip(R["eids"], R["labels"]):
                    group_rows.append({"run": run, "eid": e, "group": int(l), "matched_primary_group": int(l)})
                continue
            if R["k"] is None:
                print_run_sweep(R, say, run, tiers, feats)
                say("- no stable grouping in this run: no comparison can be made; reported as such")
                stab_rows.append({"run": run, "k": "", "moved": "", "n_common": "", "moved_share": "", "excess_over_floor": "", "survival": "", "new_groups": "", "reading": "no stable grouping"})
                continue
            print_run_sweep(R, say, run, tiers, feats)
            st = structural_groups(R)
            descs = [describe_group(R, g_, tiers_by_eid, ranges, st) for g_ in range(R["k"])]
            descs_all[run] = descs
            added = set(RUN_TIERS[run]) - set(PRIMARY_TIERS)
            cmp = compare_mode_b(primary, R) if R["mode_b"] else compare_mode_a(primary, R, prim_set, added, tier_of_eid)
            art = artefact_groups(R, st)                                                           # R71: both conditions of §5 (d)
            artefact_new = {g_ for g_ in range(R["k"]) if art[g_]["artefact"]}
            cons = consequence(cmp, floor["floor"], artefact_new)
            if run == "with_our_length":
                cons["lengths_finding"] = (R["k"] != primary["k"]) or cons["lost"]
            results[run]["cmp"], results[run]["cons"] = cmp, cons
            print_descriptions(R, descs, st, say)
            print_comparison(run, cmp, cons, R, primary, say)
            if run == "with_our_length":
                say("- with our_length: " + ("another k or a lost description — the groups LEAN on our old lengths when offered (a finding about the lengths; the primary stays the no-our_length picture)" if cons["lengths_finding"]
                                           else "the same k and every description survives — the sweep carries the same information"))
            for g in cmp["new_groups"]:
                a_ = art[g["group"]]
                if a_["artefact"]:
                    say(f"- new group {g['group']} is STRUCTURAL ({st[g['group']]['top_pattern']!r} holds {st[g['group']]['top_share']:.0%}) and does NOT separate on the entry side or the exit "
                        f"day's own columns (largest |deviation| there {a_['max_dev']:.2f} sd on {a_['max_col']}, under {ARTEFACT_SEPARATION}): the feature set's hold-dependence, not him — an "
                        "artefact; the tier is judged on the moved share alone (R71)")
                elif a_["structural"]:
                    zc = np.abs(R["Z"][R["labels"] == g["group"], R["cols"].index(a_["max_col"])])                     # R71 x R72: is the separation a tail?
                    say(f"- new group {g['group']} is STRUCTURAL ({st[g['group']]['top_pattern']!r} holds {st[g['group']]['top_share']:.0%}) but SEPARATES on {a_['max_col']} "
                        f"({a_['max_dev']:.2f} sd, at or over {ARTEFACT_SEPARATION}): a real new group, not an artefact (§5 (d), both conditions — R71); on that column the "
                        f"group's rows score up to |{zc.max():.4g}|, {int((zc > SCORE_LINES[-1]).sum())} of them beyond |{SCORE_LINES[-1]:g}| (R72 — a mean carried by a few "
                        "extrapolated rows is a tail of the map, not a behaviour)")
            match = {i: j for i, j in cmp["pairs"]}
            rmatch = {j: i for i, j in cmp["pairs"]}
            for e, l in zip(R["eids"], R["labels"]):
                group_rows.append({"run": run, "eid": e, "group": int(l), "matched_primary_group": rmatch.get(int(l), "")})
            stab_rows.append({"run": run, "k": R["k"], "moved": cmp["moved"], "n_common": cmp["n_common"], "moved_share": round(cmp["moved_share"], 4),
                              "excess_over_floor": round(cons["excess"], 4), "survival": "; ".join(f"{i}:{s['verdict']}" for i, s in cmp["survival"].items()),
                              "new_groups": "; ".join(f"{g['group']}{' artefact' if g['group'] in artefact_new else ' structural-separates' if art[g['group']]['structural'] else ''}" for g in cmp["new_groups"]),
                              "reading": cons["reading"], "ari": round(cmp["ari"], 4) if "ari" in cmp else ""})
        if "edges_low" in results and "edges_high" in results and results["edges_low"]["k"] and results["edges_high"]["k"]:      # R66
            lo, hi = results["edges_low"], results["edges_high"]
            cmp_lh = compare_mode_a(lo, hi, set(lo["eids"]), set(), tier_of_eid)
            say(f"\n### edges — low end vs high end directly: {cmp_lh['moved']} of {cmp_lh['n_common']} = {cmp_lh['moved_share']:.1%} change group (k {lo['k']} vs {hi['k']})")
            results["edges_low_vs_high"] = cmp_lh
        for e, l in zip(primary["eids"], primary["labels"]):
            group_rows.append({"run": "primary", "eid": e, "group": int(l), "matched_primary_group": int(l)})

        # ---- §7 expectations, scored ----
        say("\n## Expectations (§7), scored at the report — a miss changes nothing by itself")
        kk = primary["k"]
        if primary.get("method7b"):                                                       # 7b §2 item 3: scored on the carried method's OWN k (06b R96)
            f7 = primary["fit7b"]
            exp_rows = [("primary k", f"3-5 groups by its rule ({f7['rule']}; 7b §2 item 3)", f"k = {kk} by {f7['rule']}; {f7['detail']}", "met" if 3 <= kk <= 5 else "missed")]
        else:
            ps_k = primary["choice"]["sweep"][kk]["strength"]
            exp_rows = [("primary k", "3-5 groups at strength >= 0.80", f"k = {kk}, strength {ps_k:.3f}", "met" if 3 <= kk <= 5 else "missed")]
        exp_rows.append(("noise floor", "seeded < 5%, bootstrap < 10%", f"{floor['floor_seeded']:.1%} / {floor['floor_bootstrap']:.1%}",
                         "met" if floor["floor_seeded"] < 0.05 and floor["floor_bootstrap"] < 0.10 else "missed" + (" (floor above 15%: the tier comparisons read as excess over it)" if floor["floor"] > 0.15 else "")))

        def _exp(run, line, met_fn):
            R = results.get(run)
            if R is None or R.get("cons") is None:
                return (run, line, "no stable grouping", "missed")
            got = f"excess {R['cons']['excess']:+.1%}, survival {[s['verdict'] for s in R['cmp']['survival'].values()]}, new {[g['group'] for g in R['cmp']['new_groups']]}"
            return (run, line, got, "met" if met_fn(R) else "missed")
        exp_rows.append(_exp("plus_one_stream", "under 15% move (over the floor); a NEW non-structural group (the same-day trades)",
                             lambda R: R["cons"]["excess"] < 0.15 and bool(R["cons"]["new_real"])))
        exp_rows.append(_exp("plus_low", "under 10% move; no new group", lambda R: R["cons"]["excess"] < 0.10 and not R["cmp"]["new_groups"]))
        exp_rows.append(_exp("with_our_length", "the same k and descriptions", lambda R: not R["cons"]["lengths_finding"] and all(s["verdict"] == "survives" for s in R["cmp"]["survival"].values())))
        over5 = []
        for run in RUNS[1:]:
            R = results.get(run)
            if R is None or not len(R["eids"]):
                continue
            over5 += [f"{run}:{c}" for c, v in R["extra"].items() if v / len(R["eids"]) > 0.05 and c != "hold_sessions_max"]
        exp_rows.append(("extrapolated values", "only hold_sessions_max and a handful per feature", f"features over 5%: {over5 or 'none'}", "met" if not over5 else "missed (flagged in the descriptions)"))
        lh = results.get("edges_low_vs_high")
        exp_rows.append(("edges", "under 20% move between the low-end and high-end descriptions", f"{lh['moved_share']:.1%}" if lh else "no stable grouping on an edge", "met" if lh and lh["moved_share"] < 0.20 else "missed"))
        ys = [results.get("year_2020"), results.get("year_2021_22")]
        ok_y = all(R is not None and R.get("cmp") is not None and all(s["verdict"] == "survives" for s in R["cmp"]["survival"].values()) and not R["cmp"]["unmatched_primary"] for R in ys)
        exp_rows.append(("2020 vs 2021-22", "the same groups by description", "; ".join(f"{r}: {[s['verdict'] for s in results[r]['cmp']['survival'].values()] if results.get(r, {}).get('cmp') else 'none'}" for r in ("year_2020", "year_2021_22")), "met" if ok_y else "missed (a finding about him or the captions, not a test)"))
        cf = results.get("confirmed", {})
        exp_rows.append(("CONFIRMED", "within 15 points in every group; at least one confirmed trade in every group", f"flags: {cf.get('flagged', [])}", "met" if not cf.get("flagged") else "missed"))
        ed = expectation_descriptions(descs_all["primary"])
        exp_rows.append(("descriptions", "one early-day buy near a recent high after a run-up; one sale within two sessions near the day's low (R63)", str(ed), "met" if all(ed.values()) else "missed"))
        table(say, ["item", "expectation", "observed", "verdict"], exp_rows)

    # ---- outputs ----
    desc_rows = []
    for run, descs in descs_all.items():
        for d in descs:
            desc_rows.append({"run": run, "group": d["group"], "n": d["n"], "share": round(d["share"], 4), "structural": d["structural"]["structural"],
                              "top_pattern": d["structural"]["top_pattern"], "top_pattern_share": round(d["structural"]["top_share"], 4),
                              "tier_mix": "; ".join(f"{k} {v}" for k, v in sorted(d["tier_mix"].items())), "confirmed": d["confirmed"],
                              "daily_only_rows": d["daily_only_rows"], "band_width_buy": f4(d["band_width"]["buy"]), "band_width_sale": f4(d["band_width"]["sale"]),
                              "description": " | ".join(f["words"] for f in d["features"]),
                              "features": "; ".join(f"{f['column']} {f['sign']}{abs(f['deviation']):.2f} med {f4(f['median'])}" for f in d["features"]),
                              "examples": "; ".join(d["examples"]),
                              "described_not_grouped": "; ".join(f"{c} med {f4(m)}" for c, m in d.get("described_only", {}).items())})      # 7b R97
    write_tsv(feature_out_rows(feats, tiers), FEATURE_OUT_COLS, OUT_G["features"])
    write_tsv(group_rows, ["run", "eid", "group", "matched_primary_group"], OUT_G["groups"])
    write_tsv(desc_rows, ["run", "group", "n", "share", "structural", "top_pattern", "top_pattern_share", "tier_mix", "confirmed", "daily_only_rows",
                          "band_width_buy", "band_width_sale", "description", "features", "examples", "described_not_grouped"], OUT_G["descriptions"])
    write_tsv(stab_rows, ["run", "k", "moved", "n_common", "moved_share", "excess_over_floor", "survival", "new_groups", "reading", "ari"], OUT_G["stability"])
    say("\n## Outputs")
    for k, p in OUT_G.items():
        say(f"- {k}: {p} ({C.sha(p)[:16]})")
    say("RUN COMPLETE")
    say.write(P06["run"])
    C.ledger_append(STAGE_G + "dry_run", dry_path)                                   # 7b (06b R90 / R96): the dry run that gated THIS run (the method's own under a carried method)
    C.ledger_append(STAGE_G + "printout", P06["run"])
    for k, p in OUT_G.items():
        C.ledger_append(STAGE_G + k, p)
    return 0


if __name__ == "__main__":
    sys.exit(main())
