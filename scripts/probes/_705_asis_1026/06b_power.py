#!/usr/bin/env python3
"""#711 step 7b — a stronger way to sort his trades, PROVEN ON MADE-UP TRADES FIRST (docs/analysis/cb_asis_step7b_power_prereg_2026-10-27.md,
FROZEN above its marker, doc_body_7b cf2ec533; never edited here). It plugs into step 7 (cb_asis_step7_grouping_prereg_2026-10-27.md §3-§5,
frozen, doc_body b16d81fe): the population, the features, the blank rules, the rank-normal maps, the minimum group size, the runs and the
comparison machinery are IMPORTED from 06_groups.py and never widened.

WHAT IT DOES   --shape    the ONLY stage that opens real data: through 06_groups' own loaders and maps it takes the four summaries of §4.1
                          from the primary's 658 fitted rows — R (the 75 x 75 pairwise correlation of the rank-normal scores, thin pairs
                          zeroed, eigenvalues clipped at 1e-3, unit diagonal; the unclipped matrix and the shared-row counts beside it), the
                          658 blank masks with each row's hold rank, each column's run sizes of equal values (counts only), n and the column
                          names — into asis_1026/step7b_shape.npz (exactly those keys) + 06b_shape.txt. No row's values leave the stage.
               --dry-run  made-up sets only (every real-data loader is sealed inside it, R104): C5a / C5b / C5c (the shape is his; C5b on
                          the pooled latent through the rank map, BEFORE the tie step — Re-registration 1 item 1, R101; the post-tie
                          comparison a readout), C6 (the oracle reaches the target), C2 (the plant is there and survives the pipeline; 50
                          latent sets per cell), C3 (the gaps follow the hold; every set), two sets per world through every method for
                          plumbing and C7 (the projected wall time of --power on 10 cores), the N2-vs-N1 index readout -> 06b_power_dryrun.txt.
               --print-pins  the pins of §11 -> stdout + 06b_power_pins.txt.
               --power    the one power run (§4.3-§4.4's 1,420 sets, §5's seven methods, the gap-free arm on the N1 / N2 / target sets,
                          §6's scoring, the oracle, C1-C3, qualification, selection, the fresh estimate, Fallback 1 / 2, the size line) ->
                          asis_1026/step7b_power.tsv (one row per set x method x column set) + 06b_power.txt ending
                          `POWER COMPLETE: <outcome>`. Refused unless both dry runs completed with 0 MISMATCH by the modules on disk, every
                          pin sits below the 7b doc's marker, the ledger verifies, and no output or `step7b_power` ledger row exists.
               Ledger rows `step7b_*`; a stage whose row exists refuses (once means once, whatever files are deleted).

THE MADE-UP SET (§4.2, in this order; seed `rng_for("step7b_set_<world>_<cell>_<i>")`): (1) 658 latent rows from N(0, R); (2) the N2 bend;
(3) the coherent plant (an EXACT count of rows at random; delta = R[:, B] R_BB^-1 (Delta_B 1), Delta_B = sep / sqrt(1' R_BB^-1 1), delta on
hold_sessions_max set to 0); (4) masks by the LATENT pre-bend / pre-plant hold rank; (5) his repeated values by a monotone step (block means
in latent order); (6) the rank-normal maps fitted on the set itself, blanks zero-filled, then the method under test.

THE METHODS (§5; settings identical here and in 06_groups --method): M0 the registered rule (never eligible); M1 prediction strength on the
kept-unwhitened (parallel-analysis) components; M2w / M2u bootstrap stability (30 refits, mean adjusted Rand >= 0.80); M3w / M3u a split test
against 1,000 null draws (p < 0.01 / 0.005 / 0.0025, at most three levels); M4 a diagonal Gaussian mixture by BIC. One implementation serves
the power run and the real run (06_groups.py imports this module lazily for a non-default --method / --columns).

WHAT IT NEVER READS  any trade outcome (both name lists are scanned against every step-7 module and this one); the seven outcome folders;
               anything dated after 2024-12-31; the rule folders (the import belt). --dry-run / --power open no real-data file but the
               shape file (`seal_real_loaders`, tested).

READINGS where the registration is silent (numbered on from 06_groups' R75; the main loop decides):
  R76 R's diagonal is 1 by definition: the thin-pair / zero-spread rule (< 30 shared rows, or no spread on either side -> 0) is applied to
      pairs of DISTINCT columns; a column with under 30 non-blank rows keeps its unit diagonal and zero off-diagonals (an independent latent).
  R77 A column's "run sizes in sorted order" = the sizes of its runs of equal values walking from the smallest value to the largest (so step
      5 can hand them out in latent order); the shared value of a run is the MEAN of the run's latent values (monotone: block means of a
      sorted sequence are non-decreasing); the made-up column's non-blank count equals his (the masks are a permutation of his), asserted.
  R78 C2 (a)'s "others" are the rows planted on NO block (label 0): the line Phi(Delta_B / sqrt 2) is exactly the expected AUC of a group
      shifted by Delta_B against an unshifted one; in the `three` cell the other planted group is left out of the comparison (its B1
      columns carry the B3 plant's correlated shadow). The pooled AUC of a cell is the mean of its sets' AUCs (sets are independent draws).
  R79 C3's real value is Spearman(the stored tie-broken hold RANK, the row's count of non-blank exit look-backs) — the made-up coupling is
      a permutation identity with it (row at rank r takes the mask at rank r), so equality to 3 decimals is exact when wired right and
      reads otherwise when reversed or shuffled.
  R80 M0's and M1's k-means / prediction strength run in `kmeans_v` / `prediction_strength_v`: the registered k-means++ seeding (per start,
      sequentially, the same scalar draws as 06_groups.kmeans), Lloyd's iterations VECTORIZED over the starts, the best inertia kept; the
      registered 50 halves and 20 starts. On a matrix where no cluster empties mid-iteration the draws and the fixed point are the
      registered ones (a test holds labels and inertia equal to 06_groups.kmeans); an empty cluster re-seeds from a random row drawn in
      (start, cluster) order. The seed keys are §5.1's (`_starts` for the full fits, `_halves` for the halves and their fits, both consumed
      sequentially over k = 2..8), so the numbers are the registered method under 7b's keys, never a replay of a 06_groups run.
  R81 The kept-unwhitened components are M1's parallel analysis (seed `step7b_M1_<set>_perm`; the real run `step7b_real_M1_<run>_perm`) and
      are SHARED by M2u and M3u's top level, as §5 says ("M1's parallel-analysis components"); M3u's children use M3u's own `_perm`
      generator, consumed depth-first. The 95th percentile over the 50 permutations is numpy's linear interpolation; "exceeds" is strict.
  R82 M2's `_boot` generator draws the 30 resamples first, then seeds the 30 refits (batched, 10 starts each); the full-data fits of every k
      draw their starts from `_starts` sequentially over k.
  R83 M3's null draws are a deterministic function of their registered key `step7b_null_<n>_<m>` (the 1,000 draws of N(0, I_m) first, then
      the 2-means starts for M3w's index from the same generator); the cache under asis_1026/step7b_cache/ holds M3w's 1,000 indices per
      (n, m) (8 KB; a test holds cached == regenerated); the draws themselves are regenerated from the key when M3u needs them (0.2 s; a
      95 MB file per (n, m) would be slower to read than to regenerate, and the recursion makes (n, m) pairs unbounded). M3u's 2-means on
      the rescaled draws is per set (its index depends on the data's eigenvalues) and its starts come from the set's `_null` generator.
      Levels: 0.01 at the top, 0.005 for a child, 0.0025 for a grandchild; a node under twice the minimum is a leaf untested.
  R84 M4: each of the 5 starts seeds k centres by k-means++ from `_em`, hard-assigns the rows to them, takes the within-cluster variances
      per dimension (floored at 1e-3) and equal weights; the best log-likelihood of the 5 is kept; k = 1 is closed form. BIC = -2 LL +
      p ln n with p = 2km + k - 1. A k with a hard-assigned group under the minimum is skipped (k = 1 never is).
  R85 Intervals are Wilson score intervals at 95% (no scipy); a rate's "points" are percentage points of its cell.
  R86 The gap-free arm runs with the SAME method keys as the 75-column run of the set (the same halves, resamples and starts applied to the
      56-column matrix — a paired comparison); a fresh set's keys are `step7b_fresh_<world>_<cell>_<i>` (the set) and
      `step7b_<method>_fresh_<world>_<cell>_<i>_<purpose>` (inside the method).
  R87 SUPERSEDED by Re-registration 1 item 4 (R103): it had Fallback 1 fire only when NO method passed the N1 false-alarm line on the 75
      columns, and read Fallback 2 as "no qualifier where the selection was made" — which left the case "some method passes N1 on 75, none
      qualifies there, one qualifies on 56" reading Fallback 2 against §6's wording. What stands from it: the gap-free arm's qualification
      table is printed every time as a readout; on the 56 columns only the target separation was run, so Delta* there is 1.5 or "more than
      1.5 (the other separations were not run on the 56 columns)" and the 15% line reads "not run on the 56 columns"; C1's outcome (M0 at
      or above 240 of 300) takes precedence over any qualifier (§6 / §7.1).
  R88 The projected wall time (C7) = the per-world per-method seconds of the dry run's plumbing sets, multiplied out over the 1,420 sets, the
      gap-free arm's 900 and the 400 fresh sets (priced at the slowest method), divided by 10 cores at full efficiency.
  R89 --power also requires 06_groups' DEFAULT dry run complete with 0 MISMATCH by the modules on disk (it carries the reproduction claim
      of §11); the reference printout is the copy `06_groups_dryrun_ref_8352c78c.txt` whose sha must equal the pinned e578a700 (a missing
      or altered copy fails the claim). The comparison = the k-sweep block (its header through the "k chosen" line) and the reference's 32
      claim lines against the first 32 of the new run, line for line; the new run's RESULT line and the reproduction claim itself are
      outside it.
  R90 In 06_groups: the dry run under a non-default --method / --columns writes `06_groups_dryrun_<method>_<columns>.txt` (the default
      printout stays the pinned one); the DEFAULT --run is also refused when POWER COMPLETE names a carried method (§7.1 names the
      command per outcome; the registered run is the C1 / Fallback-2 command).
  R91 The noise floor under a carried method (§7.2): 5 seeded refits keyed `step7b_real_<method>_floor_seed<i>_<purpose>` and 5 bootstrap
      refits keyed `..._floor_boot<i>_<purpose>` (the refit's identity sits in the run slot, the purposes stay §5.1's closed set);
      M1 / M2 refit k-means at the primary's k with the registered 20 starts; M3 re-runs the whole split; M4 re-runs EM at the primary's k.
  R92 The shape stage's hold rank breaks ties by `rng_for("step7b_hold_ties")` through a lexsort on (hold, a uniform draw); the oracle uses
      the true shares as priors (Bayes under the true means and R).
  R93 §4.4's exact counts (197; 99; 329 / 197 / 132) are the shares 30%, 15% and 50 / 30 / 20% of the registered n = 658, rounded
      (`plant_counts`); the stages take them at the SHAPE FILE's n, which the shape stage claims is 658 (a dry-run claim and a test hold
      that the function returns the registered numbers at 658), so a synthetic shape of another n (the CI end-to-end test, n = 220) plants
      the same shares rather than more rows than it has.
  R94 "A MISMATCH on C2, C3, C5 or C6 stops the stage before any method is scored" (§6): in `--power` the C2 / C3 pass over every set
      runs FIRST and a MISMATCH stops the stage before any method runs (the printout goes to the refused file). In `--dry-run` no method is
      scored (two sets per world are plumbing and C7's timing), so the stage runs to its claims, prints every MISMATCH, and `--power` then
      refuses on the RESULT line; C5b's "50 N1 sets through the pipeline" are the C2 loop's N1 sets taken through step 6 (`DRY_C5_SETS`,
      the same count as `DRY_C2_SETS`).
  R95 (fix card, 2026-10-27, two read-only reviews) M3's null carries the spectrum of the ROWS TESTED (§5: "the data's exact unit spectrum" /
      "the data's own kept eigenvalues"). §7.2 reuses the primary's top-level reduction for a mode-A run and says nothing of the null; the
      run's rows in that reused space (1,187 / 1,588 / 347 / 330 rows under maps and components fitted on the primary's 658) have neither
      spectrum, and a toy on ONE Gaussian population read a top-level split in 16 of 16 supersets and 12 of 12 half subsets under the unit
      null (p = 0.001) against 0 of 16 / 0 of 12 under the rows' own spectrum. So `null_for_node`: in the node's own space (every power-run
      set, every child, the floor's seeded refits — the rows' covariance IS the identity / diag(lam), checked to 1e-9) the registered nulls
      serve unchanged, bit for bit; under a reused space on other rows the whitened draws are rescaled by the square roots of the tested rows'
      own eigenvalues. Reaches only `06_groups --run --method M3w | M3u`, never --power. The floor's BOOTSTRAP arm under M3 was still
      anti-conservative after this (a resample holds ~37% duplicate rows, which tighten any 2-means split against a continuous null; the toy
      read 7 of 12 / 3 of 12 below 0.01 with the rows' own spectrum) — ruled below the marker as Re-registration 1 item 3 (R102).
  R96 In 06_groups under a carried method the primary carries no `choice`: the dry run's minimum-size claim reads `min_group_size` of the
      registered rows (34), and step 7 §7's first expectation is scored on the carried method's own k ("3-5 groups by its rule", 7b §2
      item 3) with the method's sweep detail beside it; the registered strength row stays on the default path only.
  R97 Under `--columns pattern_free` (§6 Fallback 1) every run groups on its gap-free columns (§7.3) and ALSO assembles its REGISTERED
      columns on the same fitted rows, without the quarter rule (`assemble(drop=False)`, so the rows align), as the DESCRIPTION matrix:
      the group medians (every registered column, so R63's hold line can be scored), a "described, never grouped on" line per group (the
      hold and the exit look-backs) and a `described_not_grouped` column in step7_descriptions.tsv. The five farthest features and the
      profiles stay on the grouped columns (the standardized deviations exist only there).
  R98 The M3w null cache is trusted only by its key (`step7b_null_<n>_<m>`), the registered counts and a CODE STAMP — the sha256 of the source
      of every function on the null path (`_seed_pp`, `_lloyd_two`, `kmeans_many`, `_whiten_draws`, `null_draws`, `two_means_index_many`)
      with the draw and start counts and the seed — written on save and required on read; a foreign or stale file regenerates.
  R99 06_groups' two 7b gates (`named_by_power_complete`, `default_run_gate`) share `power_printout_gate`: 06b_power.txt must end POWER
      COMPLETE, carry a `- modules:` line equal to the modules on disk (§11: one implementation for the power run and the real run), be
      pinned below the 7b marker (§11's Order) and have its `step7b_power` ledger row; the default run accepts only the two registered
      default outcomes (§7.1), the non-default run only `carried <method> on <columns>`.
  R100 `--power` refuses BEFORE pass 1 when the shape file's n is not the registered 658, and after pass 2 writes NO POWER COMPLETE and no
      output on a MISMATCH of any claim but C1 (C1's MISMATCH is the registered "one style, with power" outcome, §6, never a refusal).
  R101 (finish card, 2026-10-28; Re-registration 1 item 1) C5b is read on the POOLED LATENT THROUGH THE RANK MAP: each N1 set's latent rows
      (step 1) under his masks (step 4), rank-normal maps fitted on that masked latent, pooled over the 50 N1 sets, against R on the
      well-supported pairs — lines unchanged (0.03 / 0.01). The comparison AFTER the tie step (the registered pipeline's scores) is printed
      beside as a readout: R was measured on his already-tied scores and step 5 ties the latent again, so a few-level column's correlations
      read about 7% weaker there (a disclosed consequence of the generator, not de-attenuated).
  R102 (Re-registration 1 item 3) The noise floor's BOOTSTRAP arm under M3w / M3u runs the split procedure on the resample's DISTINCT rows
      (`np.unique` of the resample's indices, about 63% of n, in row order), then assigns EVERY row by nearest leaf mean in the top-level
      space (`assign`). The resample itself is drawn as registered (`..._floor_boot<i>_boot`); only the rows handed to the test change.
      M1 / M2 / M4 refit on the full resample as registered. The distinct-row counts travel on the floor (`boot_rows`) and are printed.
  R103 (Re-registration 1 item 4) Selection: on the 75 columns first; NO qualifier there = Fallback 1 -> the selection repeats on the
      56-column arm with the same lines and order; a qualifier there is carried on `pattern_free`. Fallback 2 = no qualifier on either arm
      (§6's words); the primary is then described as one population on its REGISTERED columns (§7.1's registered run; `columns` reads
      `registered`). The size line's source under Fallback 2 is searched on the 75-column arm first (the whole curve ran there; it is the
      registered column set), then on the 56-column arm, each by §6's order (the highest-power method passing both false-alarm lines);
      M0 when none passes on either arm. R87's reading is superseded.
  R104 (review, low) The sealed set of `seal_real_loaders` is DERIVED, never hand-listed: every callable of asis_common / 01_points /
      05_tiers / 06_groups whose name starts `load_`, `read_` or `preload_`, the `MinuteStore` class and its `read_minute_file` alias on
      asis_common's `R` namespace, plus 06_groups' `build_features` (the feature builder that walks the loaded bars). The test enumerates
      the set the same way and names the members (a set that silently shrank on a rename would fail it).

Guards: no network, no production server, no paid call, no subagent. Run:
  python3 scripts/probes/_705_asis_1026/06b_power.py --shape | --dry-run | --print-pins | --power
"""
from __future__ import annotations

import os

for _v in ("OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "VECLIB_MAXIMUM_THREADS", "OMP_NUM_THREADS"):
    os.environ.setdefault(_v, "1")                      # one BLAS thread per process: --power runs 10 processes

import argparse
import collections
import hashlib
import importlib.util
import inspect
import math
import multiprocessing
import statistics
import sys
import time

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))


def _load(name: str, fname: str):
    path = os.path.join(HERE, fname)
    if name in sys.modules and os.path.abspath(getattr(sys.modules[name], "__file__", "") or "") == path:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


G = _load("asis_groups06", "06_groups.py")
C, T, P = G.C, G.T, G.P
GuardStop = C.GuardStop

# ---- paths -------------------------------------------------------------------------------------------------------------------------------
DOC7B = os.path.join(C.REPO, "docs", "analysis", "cb_asis_step7b_power_prereg_2026-10-27.md")
P06B = {"shape": os.path.join(HERE, "06b_shape.txt"), "dry": os.path.join(HERE, "06b_power_dryrun.txt"), "run": os.path.join(HERE, "06b_power.txt"),
        "refused": os.path.join(HERE, "06b_power.refused.txt"), "pins": os.path.join(HERE, "06b_power_pins.txt")}
SHAPE_NPZ = os.path.join(C.OUT_DIR, "step7b_shape.npz")
POWER_TSV = os.path.join(C.OUT_DIR, "step7b_power.tsv")
CACHE_DIR = os.path.join(C.OUT_DIR, "step7b_cache")
REF_DRY = os.path.join(HERE, "06_groups_dryrun_ref_8352c78c.txt")
REF_06_SHA = "06a3f48f1046b8a91a8bbbe8e93dd30e5c62b3a46332bc7273b5984fcf68d404"      # 06_groups.py at 8352c78c (the default path's reference)
REF_DRY_SHA = "e578a7008dc871d82df04470b24a9b120de15a9d098c199608fc22d86c4366ca"     # 06_groups_dryrun.txt at 8352c78c
MODULE_FILES_B = ("asis_common.py", "01_points.py", "05_tiers.py", "06_groups.py", "06b_power.py", "forbidden_identifiers.txt", "forbidden_outcomes.txt")
SCAN_FILES_B = ("asis_common.py", "01_points.py", "05_tiers.py", "06_groups.py", "06b_power.py")
STAGE_B = "step7b_"
N_CORES = 10

# ---- the registration, as code -----------------------------------------------------------------------------------------------------------
N_PRIMARY_FIT = 658                                      # the primary's fitted rows (§3); the made-up sets are this size
N_MIN = G.min_group_size(677)                            # 34: the primary's registered minimum (§2)
HOLD_COL = "hold_sessions_max"
BLOCKS = {"B1": ("entry_gap_pct", "entry_range_pct", "entry_vol_day_vs_10"),
          "B2": ("entry_dist_hi_10", "entry_dist_ma_13", "entry_ret_20"),
          "B3": ("exit_pos_in_day", "exit_minute", "exit_range_pct")}
BLOCK_NAMES = ("B1", "B2", "B3")
DELTAS = (1.0, 1.5, 2.0, 3.0)                            # the Delta-equivalents of the curve; sep = Delta * sqrt(3)
TARGET_DELTA = 1.5
SMALL_DELTA = 2.0
N_CURVE_ROWS, N_SMALL_ROWS, THREE_ROWS = 197, 99, (329, 197, 132)      # §4.4's exact counts at n = 658 (plant_counts reproduces them)
CURVE_SHARE, SMALL_SHARE, THREE_SHARES = 0.30, 0.15, (0.50, 0.30, 0.20)
N_NULL_SETS, N_TARGET_PER_BLOCK, N_OTHER_PER_CELL = 300, 100, 40
FRESH_N1, FRESH_TARGET_PER_BLOCK = 100, 100
METHODS = ("M0", "M1", "M2w", "M2u", "M3w", "M3u", "M4")
ELIGIBLE = METHODS[1:]
SPACE_OF = {"M0": "whitened", "M1": "pa", "M2w": "whitened", "M2u": "pa", "M3w": "whitened", "M3u": "pa", "M4": "whitened"}
COLSETS = ("registered", "pattern_free")
FA_LINES = {"N1": 15, "N2": 30}                           # of 300
TARGET_POOLED_LINE, TARGET_BLOCK_LINE, TIE_POINTS = 240, 70, 5.0
HIT_ARI = 0.5
M2_BOOTS, M2_STARTS, M2_LINE = 30, 10, 0.80
M3_LEVELS, M3_NULL, M3_STARTS = (0.01, 0.005, 0.0025), 1000, 10
M4_STARTS, M4_FLOOR, M4_TOL, M4_ITER = 5, 1e-3, 1e-6, 300
PA_PERMS, PA_MIN = 50, 2
BEND = 1.0
THIN_PAIR, WELL_SUPPORTED, EIG_FLOOR = 30, 300, 1e-3
CLIP_LINE, C5B_MAX, C5B_RMS, C5C_RANGE, C6_LINE, C2_SLACK = 0.05, 0.03, 0.01, (14, 22), 0.95, 0.02
DRY_C2_SETS, DRY_C5_SETS, DRY_C6_SETS, DRY_PLUMB = 50, 50, 200, 2
SHAPE_KEYS = ("R", "R_unclipped", "shared", "masks", "hold_rank", "run_sizes", "run_offsets", "n", "cols")
WORLDS = ("N1", "N2", "curve", "small", "three")
Say, Claims, table, pct = T.Say, T.Claims, T.table, T.pct
_ND = statistics.NormalDist()


def Phi(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def sep_of(delta: float) -> float:
    return delta * math.sqrt(3.0)


def wilson(x: int, n: int, z: float = 1.959964) -> tuple:
    """R85: the 95% Wilson score interval of x of n."""
    if n == 0:
        return (0.0, 0.0)
    p = x / n
    den = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / den
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return (max(0.0, centre - half), min(1.0, centre + half))


def rate_str(x: int, n: int) -> str:
    lo, hi = wilson(x, n)
    return f"{x} of {n} = {100 * x / n:.1f}% [{100 * lo:.1f}, {100 * hi:.1f}]" if n else "n/a"


# ---- the cells (§4.3-§4.4) ---------------------------------------------------------------------------------------------------------------
def plant_counts(n: int = N_PRIMARY_FIT) -> dict:
    """R93: §4.4's EXACT counts as shares of the shape's n — 30% and 15% rounded, `three` = (the rest, 30%, 20%); at the registered n = 658
    they are exactly 197, 99 and 329 / 197 / 132 (a test and a dry-run claim hold that), and a synthetic shape of another n gets the same
    shares (the end-to-end test runs at n = 220)."""
    curve, small = int(round(CURVE_SHARE * n)), int(round(SMALL_SHARE * n))
    t1, t2 = int(round(THREE_SHARES[1] * n)), int(round(THREE_SHARES[2] * n))
    return {"curve": curve, "small": small, "three": (n - t1 - t2, t1, t2)}


def cells(n: int = N_PRIMARY_FIT) -> list:
    """[(world, cell, n_sets, spec)] in the registered order. spec: groups [(block, count)], delta, sep, share."""
    pc = plant_counts(n)
    out = [("N1", "plain", N_NULL_SETS, {"groups": [], "delta": None, "sep": None}),
           ("N2", "curved", N_NULL_SETS, {"groups": [], "delta": None, "sep": None})]
    for delta in DELTAS:
        for b in BLOCK_NAMES:
            out.append(("curve", f"{b}_d{delta:.1f}", N_TARGET_PER_BLOCK if delta == TARGET_DELTA else N_OTHER_PER_CELL,
                        {"groups": [(b, pc["curve"])], "delta": delta, "sep": sep_of(delta), "share": "30%"}))
    for b in BLOCK_NAMES:
        out.append(("small", f"{b}_d{SMALL_DELTA:.1f}", N_OTHER_PER_CELL, {"groups": [(b, pc["small"])], "delta": SMALL_DELTA, "sep": sep_of(SMALL_DELTA), "share": "15%"}))
    out.append(("three", f"B1B3_d{TARGET_DELTA:.1f}", N_OTHER_PER_CELL,
                {"groups": [("B1", pc["three"][1]), ("B3", pc["three"][2])], "delta": TARGET_DELTA, "sep": sep_of(TARGET_DELTA),
                 "share": "/".join(str(x) for x in pc["three"])}))
    return out


def target_cells(n: int = N_PRIMARY_FIT) -> list:
    return [c for c in cells(n) if c[0] == "curve" and c[3]["delta"] == TARGET_DELTA]


def in_gap_free_arm(world: str, spec: dict) -> bool:
    return world in ("N1", "N2") or (world == "curve" and spec["delta"] == TARGET_DELTA)


# ---- pairwise statistics -----------------------------------------------------------------------------------------------------------------
def pairwise_corr(S: np.ndarray) -> tuple:
    """(corr, shared) — the Pearson correlation of every pair of columns over the rows where BOTH are non-blank (NaN = blank); NaN where
    fewer than 2 shared rows or no spread on a side."""
    M = np.isfinite(S).astype(float)
    X = np.where(M > 0, S, 0.0)
    c = M.T @ M
    sx = X.T @ M
    sy = sx.T
    sxx = (X * X).T @ M
    syy = sxx.T
    sxy = X.T @ X
    with np.errstate(invalid="ignore", divide="ignore"):
        cov = sxy - sx * sy / c
        vx = sxx - sx * sx / c
        vy = syy - sy * sy / c
        corr = cov / np.sqrt(vx * vy)
    bad = (c < 2) | ~(vx > 1e-12) | ~(vy > 1e-12)
    corr = np.where(bad, np.nan, corr)
    return corr, c.astype(int)


def rankdata(v: np.ndarray) -> np.ndarray:
    """Average ranks (1-based) with ties averaged."""
    v = np.asarray(v, dtype=float)
    order = np.argsort(v, kind="mergesort")
    sv = v[order]
    _u, inv, counts = np.unique(sv, return_inverse=True, return_counts=True)
    first = np.cumsum(counts) - counts + 1
    avg = first + (counts - 1) / 2.0
    out = np.empty(len(v))
    out[order] = avg[inv]
    return out


def auc(pos: np.ndarray, neg: np.ndarray) -> float:
    """The Mann-Whitney rank score: the share of (pos, neg) pairs with pos above neg (ties half)."""
    pos, neg = np.asarray(pos, float), np.asarray(neg, float)
    pos, neg = pos[np.isfinite(pos)], neg[np.isfinite(neg)]
    if not len(pos) or not len(neg):
        return float("nan")
    r = rankdata(np.concatenate([pos, neg]))
    return float((r[: len(pos)].sum() - len(pos) * (len(pos) + 1) / 2.0) / (len(pos) * len(neg)))


def spearman(x, y) -> float:
    rx, ry = rankdata(np.asarray(x, float)), rankdata(np.asarray(y, float))
    if rx.std() == 0 or ry.std() == 0:
        return 0.0
    return float(np.corrcoef(rx, ry)[0, 1])


def ari(a: np.ndarray, b: np.ndarray) -> float:
    """The adjusted Rand index (equal to 06_groups.adjusted_rand; bincount instead of a crosstab)."""
    a, b = np.asarray(a), np.asarray(b)
    _ua, ia = np.unique(a, return_inverse=True)
    _ub, ib = np.unique(b, return_inverse=True)
    ka, kb = ia.max() + 1, ib.max() + 1
    ct = np.bincount(ia * kb + ib, minlength=ka * kb).reshape(ka, kb).astype(float)
    comb = lambda x: x * (x - 1) / 2.0
    s_ij = comb(ct).sum()
    s_a, s_b = comb(ct.sum(1)).sum(), comb(ct.sum(0)).sum()
    n = comb(ct.sum())
    expected = s_a * s_b / n if n else 0.0
    mx = (s_a + s_b) / 2.0
    return 1.0 if mx == expected else float((s_ij - expected) / (mx - expected))


# ---- the shape (§4.1) --------------------------------------------------------------------------------------------------------------------
def clip_correlation(R0: np.ndarray, floor: float = EIG_FLOOR) -> tuple:
    """Eigenvalues below `floor` raised to it, the matrix rescaled to a unit diagonal. -> (R, eigenvalues before, after)."""
    lam, vec = np.linalg.eigh(R0)
    lam_c = np.maximum(lam, floor)
    R1 = (vec * lam_c) @ vec.T
    d = np.sqrt(np.diag(R1))
    R = R1 / np.outer(d, d)
    R = (R + R.T) / 2.0
    np.fill_diagonal(R, 1.0)
    return R, lam, np.linalg.eigvalsh(R)


def run_sizes_of(values: np.ndarray) -> np.ndarray:
    """R77: the sizes of the runs of equal values among the non-blank cells, from the smallest value to the largest."""
    v = values[np.isfinite(values)]
    if not len(v):
        return np.zeros(0, dtype=int)
    _u, counts = np.unique(v, return_counts=True)
    return counts.astype(int)


def shape_from_matrix(X: np.ndarray, cols: list, maps: dict, rng) -> dict:
    """§4.1 from the primary's raw matrix (NaN = blank) and its fitted maps: R (clipped; the unclipped one and the shared counts beside),
    the masks with the hold rank (ties broken by `rng`), each column's run sizes, n and the column names. -> the npz contents (SHAPE_KEYS)."""
    n, p = X.shape
    S = np.full(X.shape, np.nan)
    for k, c in enumerate(cols):
        S[:, k], _ex = maps[c].apply(X[:, k])
    corr, shared = pairwise_corr(S)
    off = ~np.eye(p, dtype=bool)
    thin = (shared < THIN_PAIR) & off
    zero = ~np.isfinite(corr) & ~thin & off
    R0 = np.where(thin | zero, 0.0, corr)
    R0 = np.where(np.isfinite(R0), R0, 0.0)
    np.fill_diagonal(R0, 1.0)                                      # R76
    R0 = (R0 + R0.T) / 2.0
    R, lam_before, lam_after = clip_correlation(R0)
    masks = ~np.isfinite(X)
    hold = X[:, cols.index(HOLD_COL)]
    order = np.lexsort((rng.random(n), hold))                      # R92: ties broken by the seeded draw
    hold_rank = np.empty(n, dtype=int)
    hold_rank[order] = np.arange(n)
    runs = [run_sizes_of(X[:, k]) for k in range(p)]
    offsets = np.concatenate([[0], np.cumsum([len(r) for r in runs])]).astype(int)
    d = {"R": R, "R_unclipped": R0, "shared": shared, "masks": masks, "hold_rank": hold_rank,
         "run_sizes": np.concatenate(runs).astype(int) if runs else np.zeros(0, int), "run_offsets": offsets,
         "n": np.array(n), "cols": np.array(cols)}
    d["_facts"] = {"pairs_thin": int(thin.sum() // 2), "pairs_zero_spread": int(zero.sum() // 2),
                   "thin_columns": [(cols[k], int(shared[k, k])) for k in range(p) if shared[k, k] < THIN_PAIR],
                   "eig_min_before": float(lam_before.min()), "eig_min_after": float(lam_after.min()),
                   "clip_change_300": float(np.abs(R - R0)[(shared >= WELL_SUPPORTED) & off].max()) if ((shared >= WELL_SUPPORTED) & off).any() else 0.0,
                   "clip_change_all": float(np.abs(R - R0)[off].max()), "n_blank": int(masks.sum())}
    return d


def save_shape(d: dict, path: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    np.savez(path + ".partial.npz", **{k: d[k] for k in SHAPE_KEYS})
    os.replace(path + ".partial.npz", path)


def load_shape(path: str = None) -> dict:
    with np.load(C.checked(path or SHAPE_NPZ), allow_pickle=False) as z:
        keys = tuple(z.files)
        d = {k: z[k] for k in z.files}
    if sorted(keys) != sorted(SHAPE_KEYS):
        raise GuardStop(f"the shape file holds {sorted(keys)}, not exactly §4.1's {sorted(SHAPE_KEYS)}")
    d["n"] = int(d["n"])
    d["cols"] = [str(c) for c in d["cols"]]
    return d


class ShapeContext:
    """Everything the generator, the plant, the oracle and the claims read from the shape file."""

    def __init__(self, d: dict):
        self.R, self.R0, self.shared = d["R"], d["R_unclipped"], d["shared"]
        self.n, self.cols = int(d["n"]), list(d["cols"])
        self.p = len(self.cols)
        self.ci = {c: k for k, c in enumerate(self.cols)}
        lam, vec = np.linalg.eigh(self.R)
        lam = np.maximum(lam, 1e-12)
        self.L = vec * np.sqrt(lam)                                   # rows ~ N(0, R) = g @ L.T
        self.Rinv = (vec / lam) @ vec.T
        j1 = int(np.argmax(lam))
        self.v1, self.lam1 = vec[:, j1], float(lam[j1])
        masks = np.asarray(d["masks"], dtype=bool)
        hold_rank = np.asarray(d["hold_rank"], dtype=int)
        self.masks, self.hold_rank = masks, hold_rank
        self.mask_by_rank = masks[np.argsort(hold_rank, kind="stable")]     # mask_by_rank[r] = the mask of the real row at hold rank r
        off = d["run_offsets"]
        self.runs = [np.asarray(d["run_sizes"][off[k]:off[k + 1]], dtype=int) for k in range(self.p)]
        self.j_hold = self.ci[HOLD_COL]
        self.lookback_idx = [k for k, c in enumerate(self.cols) if c.startswith("exit_") and c[5:] not in G.DAY_OWN]
        self.n_blank = int(masks.sum())
        count_by_rank = (~self.mask_by_rank[:, self.lookback_idx]).sum(1)
        self.hold_gap_spearman = spearman(np.arange(self.n), count_by_rank)            # R79: the real value, on the stored rank
        self.block_idx = {b: [self.ci[c] for c in BLOCKS[b]] for b in BLOCK_NAMES}
        self.nine = sorted(k for b in BLOCK_NAMES for k in self.block_idx[b])
        self.block_scale, self.block_dir = {}, {}
        for b in BLOCK_NAMES:
            idx = self.block_idx[b]
            RBB = self.R[np.ix_(idx, idx)]
            inv = np.linalg.inv(RBB)
            one = np.ones(len(idx))
            self.block_scale[b] = float(np.sqrt(one @ inv @ one))               # Delta_B = sep / scale
            direction = self.R[:, idx] @ inv @ one                              # the shift per unit Delta_B, every column
            direction[self.j_hold] = 0.0                                        # §4.4: the hold's delta is 0
            self.block_dir[b] = direction
        self.pattern_free = G.pattern_free_columns(self.cols)

    def delta_b(self, b: str, sep: float) -> float:
        return sep / self.block_scale[b]

    def shift(self, b: str, sep: float) -> np.ndarray:
        return self.delta_b(b, sep) * self.block_dir[b]

    def mahalanobis(self, v: np.ndarray) -> float:
        return float(np.sqrt(v @ self.Rinv @ v))


# ---- one made-up set (§4.2) --------------------------------------------------------------------------------------------------------------
def tie_step(X: np.ndarray, masks: np.ndarray, runs: list) -> np.ndarray:
    """R77 / §4.2 step 5: on each column, the non-blank rows ordered by their latent value take his run sizes in that order; a run shares
    its latent mean. NaN at the blanks. Never re-orders."""
    n, p = X.shape
    out = np.full(X.shape, np.nan)
    for k in range(p):
        idx = np.flatnonzero(~masks[:, k])
        sizes = runs[k]
        if int(sizes.sum()) != len(idx):
            raise GuardStop(f"tie step: column {k} has {len(idx)} non-blank made-up cells but his run sizes sum to {int(sizes.sum())}")
        if not len(idx):
            continue
        vals = X[idx, k]
        order = np.argsort(vals, kind="stable")
        sv = vals[order]
        starts = np.concatenate([[0], np.cumsum(sizes)[:-1]]).astype(int)
        means = np.add.reduceat(sv, starts) / sizes
        out[idx[order], k] = np.repeat(means, sizes)
    return out


def set_key(world: str, cell: str, i: int, fresh: bool = False) -> str:
    return f"step7b_{'fresh' if fresh else 'set'}_{world}_{cell}_{i}"


def set_id(world: str, cell: str, i: int, fresh: bool = False) -> str:
    return f"{'fresh_' if fresh else ''}{world}_{cell}_{i}"


def make_set(ctx: ShapeContext, world: str, cell: str, i: int, spec: dict, fresh: bool = False, through: int = 6) -> dict:
    """§4.2 steps 1..`through` for one set. -> {'latent1' (step 1), 'latent' (after bend / plant), 'labels', 'k_true', 'masks', 'X'
    (handed to the maps), 'Z' (zero-filled), 'S' (scores, NaN kept), 'maps', 'key'}."""
    key = set_key(world, cell, i, fresh)
    rng = C.rng_for(key)
    n, p = ctx.n, ctx.p
    X1 = rng.standard_normal((n, p)) @ ctx.L.T                                   # 1 draw
    X = X1.copy()
    if world == "N2":                                                             # 2 bend (§4.3)
        f = (X1 @ ctx.v1) / math.sqrt(ctx.lam1)
        X[:, ctx.nine] += BEND * ((f * f - 1.0) / math.sqrt(2.0))[:, None]
    labels = np.zeros(n, dtype=int)
    groups = spec.get("groups", [])
    if groups:                                                                    # 3 plant (§4.4): exact counts, rows at random
        perm = rng.permutation(n)
        at = 0
        for g, (b, count) in enumerate(groups, 1):
            rows = perm[at:at + count]
            X[rows] += ctx.shift(b, spec["sep"])
            labels[rows] = g
            at += count
    out = {"key": key, "world": world, "cell": cell, "i": i, "fresh": fresh, "latent1": X1, "latent": X, "labels": labels, "k_true": 1 + len(groups)}
    if through <= 3:
        return out
    order = np.argsort(X1[:, ctx.j_hold], kind="stable")                         # 4 masks by the LATENT pre-bend / pre-plant hold rank
    rank = np.empty(n, dtype=int)
    rank[order] = np.arange(n)
    masks = ctx.mask_by_rank[rank]
    out["masks"], out["hold_latent"] = masks, X1[:, ctx.j_hold]
    Xh = tie_step(X, masks, ctx.runs)                                             # 5 his repeated values
    out["X"] = Xh
    if through <= 5:
        return out
    maps = G.fit_maps(Xh, ctx.cols)                                               # 6 the same pipeline as his trades
    Z, _extra, _blanks = G.standardize(Xh, ctx.cols, maps)
    S = np.full(Xh.shape, np.nan)
    for k, c in enumerate(ctx.cols):
        S[:, k], _e = maps[c].apply(Xh[:, k])
    out["Z"], out["S"], out["maps"] = Z, S, maps
    return out


# ---- the checks on a set (C2, C3) and the oracle (§6) ------------------------------------------------------------------------------------
def check_c2(ctx: ShapeContext, st: dict, spec: dict) -> dict:
    """C2 (a): per planted group and block column, the AUC of the planted rows' LATENT values against the unplanted rows' (R78), and the
    final AUC on the values handed to the maps; (b): on every column, the handed value is non-decreasing in the latent value over the
    non-blank cells. -> {'auc': {(group, col): (latent auc, line, final auc)}, 'monotone_ok': int, 'columns': int}."""
    X, Xh, masks, labels = st["latent"], st["X"], st["masks"], st["labels"]
    out = {"auc": {}, "monotone_ok": 0, "columns": ctx.p}
    for g, (b, _count) in enumerate(spec.get("groups", []), 1):
        line = Phi(ctx.delta_b(b, spec["sep"]) / math.sqrt(2.0)) - C2_SLACK
        for c in BLOCKS[b]:
            k = ctx.ci[c]
            pos, neg = labels == g, labels == 0
            out["auc"][(g, c)] = (auc(X[pos, k], X[neg, k]), line, auc(Xh[pos, k], Xh[neg, k]))
    for k in range(ctx.p):
        idx = np.flatnonzero(~masks[:, k])
        if len(idx) < 2:
            out["monotone_ok"] += 1
            continue
        order = np.argsort(X[idx, k], kind="stable")
        if np.all(np.diff(Xh[idx[order], k]) >= 0):
            out["monotone_ok"] += 1
    return out


def check_c3(ctx: ShapeContext, st: dict) -> dict:
    """C3: the blank cells equal his (count), and Spearman(latent hold, the row's non-blank exit look-backs) equals the real value to 3 dp."""
    masks = st["masks"]
    count = (~masks[:, ctx.lookback_idx]).sum(1)
    sp = spearman(st["hold_latent"], count)
    return {"n_blank": int(masks.sum()), "blank_ok": int(masks.sum()) == ctx.n_blank, "spearman": sp,
            "spearman_ok": round(sp, 3) == round(ctx.hold_gap_spearman, 3)}


def oracle(ctx: ShapeContext, st: dict, spec: dict) -> dict:
    """§6: the best possible sorter — the true group means and R on the latent rows (Bayes with the true shares as priors, R92). -> hit, ari."""
    groups = spec.get("groups", [])
    if not groups:
        return {"hit": None, "ari": None}
    X, labels, n = st["latent"], st["labels"], ctx.n
    means = [np.zeros(ctx.p)] + [ctx.shift(b, spec["sep"]) for b, _c in groups]
    counts = [n - sum(c for _b, c in groups)] + [c for _b, c in groups]
    scores = np.empty((n, len(means)))
    for g, (mu, cnt) in enumerate(zip(means, counts)):
        diff = X - mu
        scores[:, g] = -0.5 * np.einsum("ij,ij->i", diff @ ctx.Rinv, diff) + math.log(cnt / n)
    pred = scores.argmax(1)
    a = ari(pred, labels)
    return {"hit": bool(a >= HIT_ARI), "ari": float(a)}


# ---- vectorized k-means (R80) ------------------------------------------------------------------------------------------------------------
def _seed_pp(Zb: np.ndarray, k: int, rng, starts: int) -> np.ndarray:
    """k-means++ centres for every (problem, start), the draws made per start in the registered order: a random first row, then each next
    centre by `rng.choice(n, p=d2 / d2.sum())`. -> (B, S, k, m)."""
    B, n, m = Zb.shape
    cent = np.empty((B, starts, k, m))
    for b in range(B):
        Z = Zb[b]
        for s in range(starts):
            c0 = Z[rng.integers(n)]
            cent[b, s, 0] = c0
            d2 = ((Z - c0) ** 2).sum(1)
            for j in range(1, k):
                tot = d2.sum()
                pr = d2 / tot if tot > 0 else np.full(n, 1.0 / n)
                cj = Z[rng.choice(n, p=pr)]
                cent[b, s, j] = cj
                d2 = np.minimum(d2, ((Z - cj) ** 2).sum(1))
    return cent


def _lloyd_two(Zb: np.ndarray, cent: np.ndarray, rng, max_iter: int) -> tuple:
    """Lloyd's iterations for k = 2 on (B, S) problems with one matvec per step: a row goes to centre 1 when it is strictly closer to it
    (a tie reads 0, as argmin does). -> (labels (B, S, n), cent (B, S, 2, m))."""
    B, n, m = Zb.shape
    Zb4 = Zb[:, None, :, :]
    total = Zb.sum(1)[:, None, :]                                                  # (B, 1, m)
    labels = None
    for _it in range(max_iter):
        w = cent[:, :, 1, :] - cent[:, :, 0, :]                                    # (B, S, m)
        thr = ((cent[:, :, 1, :] ** 2).sum(2) - (cent[:, :, 0, :] ** 2).sum(2)) / 2.0
        proj = (Zb4 @ w[..., None])[..., 0]                                        # (B, S, n)
        new = (proj > thr[..., None]).astype(np.int64)
        if labels is not None and np.array_equal(new, labels):
            break
        labels = new
        lab = labels.astype(float)
        n1 = lab.sum(2)                                                            # (B, S)
        s1 = (lab[:, :, None, :] @ Zb4)[:, :, 0, :]                                # (B, S, m)
        s0 = total - s1
        n0 = n - n1
        with np.errstate(invalid="ignore", divide="ignore"):
            c0 = s0 / n0[..., None]
            c1 = s1 / n1[..., None]
        cent = np.stack([c0, c1], axis=2)
        for b, s, j in zip(*np.nonzero(np.stack([n0 == 0, n1 == 0], axis=2))):
            cent[b, s, j] = Zb[b, rng.integers(n)]                                  # R55
    w = cent[:, :, 1, :] - cent[:, :, 0, :]
    thr = ((cent[:, :, 1, :] ** 2).sum(2) - (cent[:, :, 0, :] ** 2).sum(2)) / 2.0
    labels = ((Zb4 @ w[..., None])[..., 0] > thr[..., None]).astype(np.int64)
    return labels, cent


def kmeans_many(Zb: np.ndarray, k: int, rng, starts: int, max_iter: int = 300) -> dict:
    """k-means on B problems at once (Zb: (B, n, m)), `starts` seeded starts each, Lloyd's iterations vectorized over (B, S), the best
    inertia per problem kept. -> {'labels' (B, n), 'centroids' (B, k, m), 'inertia' (B,)}."""
    B, n, m = Zb.shape
    cent = _seed_pp(Zb, k, rng, starts)                                           # (B, S, k, m)
    Zb4 = Zb[:, None, :, :]                                                        # (B, 1, n, m) — broadcast over the starts in matmul (BLAS)
    zsq = (Zb * Zb).sum(2)[:, None, :, None]                                       # (B, 1, n, 1)
    ks = np.arange(k)
    labels = None
    if k == 2:
        labels, cent = _lloyd_two(Zb, cent, rng, max_iter)
        onehot = (labels[..., None] == ks).astype(float)
        counts = onehot.sum(2)
        inertia = (zsq[..., 0] * np.ones_like(labels, dtype=float)).sum(2) - 2.0 * ((onehot.transpose(0, 1, 3, 2) @ Zb4) * cent).sum((2, 3)) + (counts * (cent * cent).sum(3)).sum(2)
        best = inertia.argmin(1)
        lab = labels[np.arange(B), best]
        cb = cent[np.arange(B), best]
        exact = np.array([float(((Zb[b] - cb[b][lab[b]]) ** 2).sum()) for b in range(B)])
        return {"labels": lab, "centroids": cb, "inertia": exact}
    for _it in range(max_iter):
        csq = (cent * cent).sum(3)[:, :, None, :]                                  # (B, S, 1, k)
        d2 = zsq - 2.0 * (Zb4 @ cent.transpose(0, 1, 3, 2)) + csq                  # (B, S, n, k)
        new = d2.argmin(3)                                                         # (B, S, n)
        if labels is not None and np.array_equal(new, labels):
            break
        labels = new
        onehot = (labels[..., None] == ks).astype(float)                           # (B, S, n, k)
        counts = onehot.sum(2)                                                     # (B, S, k)
        sums = onehot.transpose(0, 1, 3, 2) @ Zb4                                  # (B, S, k, m)
        with np.errstate(invalid="ignore", divide="ignore"):
            cent = sums / counts[..., None]
        empty = counts == 0
        if empty.any():
            for b, s, j in zip(*np.nonzero(empty)):
                cent[b, s, j] = Zb[b, rng.integers(n)]                              # R55: an emptied cluster re-seeds from a random row
    csq = (cent * cent).sum(3)[:, :, None, :]
    d2 = zsq - 2.0 * (Zb4 @ cent.transpose(0, 1, 3, 2)) + csq
    labels = d2.argmin(3)
    inertia = np.take_along_axis(d2, labels[..., None], axis=3)[..., 0].sum(2)       # (B, S)
    best = inertia.argmin(1)                                                       # the first minimal start per problem
    lab = labels[np.arange(B), best]                                               # (B, n)
    cb = cent[np.arange(B), best]                                                  # (B, k, m)
    exact = np.empty(B)
    for b in range(B):                                                             # the chosen fit's inertia in the direct form
        exact[b] = float(((Zb[b] - cb[b][lab[b]]) ** 2).sum())
    return {"labels": lab, "centroids": cb, "inertia": exact}


def kmeans_v(Z: np.ndarray, k: int, rng, starts: int = G.N_STARTS, max_iter: int = 300) -> dict:
    """One matrix, `starts` starts at once (R80). The same contract as 06_groups.kmeans."""
    r = kmeans_many(Z[None, :, :], k, rng, starts, max_iter)
    return {"labels": r["labels"][0], "centroids": r["centroids"][0], "inertia": float(r["inertia"][0])}


def prediction_strength_v(Z: np.ndarray, k: int, rng, halves: int = G.N_HALVES, starts: int = G.N_STARTS) -> float:
    """§4.4 with kmeans_v: 50 random halves from `rng`, fit on A, assign B to A's nearest centroid, the smallest pair share over B's clusters."""
    n = len(Z)
    vals = []
    for _ in range(halves):
        perm = rng.permutation(n)
        a, b = perm[: n // 2], perm[n // 2:]
        fit_a = kmeans_v(Z[a], k, rng, starts)
        fit_b = kmeans_v(Z[b], k, rng, starts)
        vals.append(G.pair_share(fit_b["labels"], G.nearest(Z[b], fit_a["centroids"])))
    return float(np.mean(vals))


def group_means(Zp: np.ndarray, labels: np.ndarray, k: int) -> np.ndarray:
    return np.vstack([Zp[labels == g].mean(0) if (labels == g).any() else np.full(Zp.shape[1], np.nan) for g in range(k)])


def two_means_index(Zp: np.ndarray, rng, starts: int = M3_STARTS) -> tuple:
    """M3: the 2-means within / total sum of squares, best of `starts`. -> (index, fit)."""
    fit = kmeans_v(Zp, 2, rng, starts)
    tot = float(((Zp - Zp.mean(0)) ** 2).sum())
    return (fit["inertia"] / tot if tot > 0 else 1.0), fit


def two_means_index_many(Zb: np.ndarray, rng, starts: int = M3_STARTS, chunk: int = 100) -> np.ndarray:
    """The 2-means index of every problem in Zb (B, n, m), in chunks."""
    out = np.empty(len(Zb))
    for a in range(0, len(Zb), chunk):
        sub = Zb[a:a + chunk]
        r = kmeans_many(sub, 2, rng, starts)
        tot = ((sub - sub.mean(1, keepdims=True)) ** 2).sum((1, 2))
        out[a:a + chunk] = r["inertia"] / np.where(tot > 0, tot, 1.0)
    return out


# ---- reductions (§5: whitened = the registered PCA; kept-unwhitened = parallel analysis) -------------------------------------------------
class ParallelAnalysis:
    """M1's reduction (R81): the components of the covariance of the zero-filled Z (the matrix the registered PCA decomposes) kept while
    the j-th eigenvalue exceeds the 95th percentile of the j-th eigenvalue over 50 column-wise permutations of Z; at least 2; NOT scaled."""

    def __init__(self, Z: np.ndarray, rng, perms: int = PA_PERMS, at_least: int = PA_MIN):
        self.mean = Z.mean(0)
        xc = Z - self.mean
        n = max(1, len(Z) - 1)
        lam, vec = np.linalg.eigh(xc.T @ xc / n)
        order = np.argsort(lam)[::-1]
        lam, vec = lam[order], vec[:, order]
        null = np.empty((perms, len(lam)))
        for q in range(perms):
            Zq = np.empty_like(Z)
            for k in range(Z.shape[1]):
                Zq[:, k] = Z[rng.permutation(len(Z)), k]
            xq = Zq - Zq.mean(0)
            null[q] = np.sort(np.linalg.eigvalsh(xq.T @ xq / n))[::-1]
        self.p95 = np.percentile(null, 95, axis=0)
        m = 0
        while m < len(lam) and lam[m] > self.p95[m]:
            m += 1
        m = max(at_least, m)
        m = min(m, int((lam > 1e-12).sum()))
        self.lam_all, self.vec_all = lam, vec
        self.lam, self.vec, self.m = lam[:m], vec[:, :m], m
        self.explained = float(lam[:m].sum() / lam.sum()) if lam.sum() > 0 else 0.0
        self.kept_by_rule = int(sum(1 for j in range(len(lam)) if lam[j] > self.p95[j] and all(lam[i] > self.p95[i] for i in range(j))))

    def transform(self, Z: np.ndarray) -> np.ndarray:
        return (Z - self.mean) @ self.vec


class Spaces:
    """The two reductions of one zero-filled matrix: `whitened` (06_groups.PCA, the registered one) and `pa` (ParallelAnalysis, M1's)."""

    def __init__(self, Z: np.ndarray, perm_key: str, kinds: tuple = ("whitened", "pa")):
        self.Z = Z
        self.red = {}
        if "whitened" in kinds:
            self.red["whitened"] = G.PCA(Z)
        if "pa" in kinds:
            self.red["pa"] = ParallelAnalysis(Z, C.rng_for(perm_key))

    def transform(self, Z: np.ndarray, kind: str) -> np.ndarray:
        return self.red[kind].transform(Z)

    def m(self, kind: str) -> int:
        return self.red[kind].m


# ---- the methods (§5) --------------------------------------------------------------------------------------------------------------------
def _one_group(n: int, Zp: np.ndarray) -> dict:
    return {"k": 1, "labels": np.zeros(n, dtype=int), "means": Zp.mean(0, keepdims=True)}


def ps_rule(Zp: np.ndarray, n_min: int, key: str, halves: int = G.N_HALVES, starts: int = G.N_STARTS) -> dict:
    """M0 / M1: the registered k rule — prediction strength >= 0.80 on random halves, every group >= n_min, the LARGEST k in 2..8."""
    rng_s, rng_h = C.rng_for(key + "_starts"), C.rng_for(key + "_halves")
    sweep = {}
    for k in G.K_RANGE:
        fit = kmeans_v(Zp, k, rng_s, starts)
        sizes = np.bincount(fit["labels"], minlength=k)
        ps = prediction_strength_v(Zp, k, rng_h, halves, starts)
        sweep[k] = {"strength": ps, "sizes": sizes.tolist(), "size_ok": bool(sizes.min() >= n_min), "strength_ok": bool(ps >= G.STRENGTH_LINE), "fit": fit}
    passing = [k for k in G.K_RANGE if sweep[k]["size_ok"] and sweep[k]["strength_ok"]]
    out = {"sweep": sweep, "rule": "prediction strength"}
    if passing:
        k = max(passing)
        out.update({"k": k, "labels": sweep[k]["fit"]["labels"], "means": group_means(Zp, sweep[k]["fit"]["labels"], k)})
    else:
        out.update(_one_group(len(Zp), Zp))
    out["detail"] = "|".join(f"{k}:{s['strength']:.3f}" for k, s in sweep.items())
    return out


def bootstrap_rule(Zp: np.ndarray, n_min: int, key: str, boots: int = M2_BOOTS, starts: int = M2_STARTS) -> dict:
    """M2w / M2u: for each k, the full-data fit against 30 bootstrap refits (every row assigned to each refit's centroids); k = the largest
    with mean adjusted Rand >= 0.80 and every full-data group >= n_min; none -> 1. R82: the resamples first, then the refits' starts."""
    rng_s, rng_b = C.rng_for(key + "_starts"), C.rng_for(key + "_boot")
    n = len(Zp)
    sweep = {}
    for k in G.K_RANGE:
        full = kmeans_v(Zp, k, rng_s, starts)
        sizes = np.bincount(full["labels"], minlength=k)
        idx = np.vstack([rng_b.integers(0, n, n) for _ in range(boots)])
        refits = kmeans_many(Zp[idx], k, rng_b, starts)
        aris = [ari(full["labels"], G.nearest(Zp, refits["centroids"][b])) for b in range(boots)]
        sweep[k] = {"ari": float(np.mean(aris)), "sizes": sizes.tolist(), "size_ok": bool(sizes.min() >= n_min), "ari_ok": bool(np.mean(aris) >= M2_LINE), "fit": full}
    passing = [k for k in G.K_RANGE if sweep[k]["size_ok"] and sweep[k]["ari_ok"]]
    out = {"sweep": sweep, "rule": "bootstrap stability"}
    if passing:
        k = max(passing)
        out.update({"k": k, "labels": sweep[k]["fit"]["labels"], "means": group_means(Zp, sweep[k]["fit"]["labels"], k)})
    else:
        out.update(_one_group(n, Zp))
    out["detail"] = "|".join(f"{k}:{s['ari']:.3f}" for k, s in sweep.items())
    return out


def _whiten_draws(X: np.ndarray) -> np.ndarray:
    """Each draw (n x m) re-whitened by its own PCA, all m kept: unit sample variance on every component."""
    xc = X - X.mean(1, keepdims=True)
    n = X.shape[1]
    cov = (xc.transpose(0, 2, 1) @ xc) / max(1, n - 1)
    lam, vec = np.linalg.eigh(cov)
    lam = np.maximum(lam, 1e-12)
    return (xc @ vec) / np.sqrt(lam)[:, None, :]


def null_draws(n: int, m: int, draws: int = None) -> tuple:
    """R83: the 1,000 whitened draws of N(0, I_m) at this n from `step7b_null_<n>_<m>` and the generator positioned after them."""
    draws = M3_NULL if draws is None else draws
    rng = C.rng_for(f"step7b_null_{n}_{m}")
    X = rng.standard_normal((draws, n, m))
    return _whiten_draws(X), rng


def null_cache_path(n: int, m: int) -> str:
    return os.path.join(CACHE_DIR, f"step7b_null_{n}_{m}.npz")


def null_code_stamp() -> str:
    """R98: the sha256 of the SOURCE of every function on M3w's null path (the draws, their whitening, the vectorized 2-means) with the
    registered counts and the seed — written into every cache file and required on read, so a cache made by other code regenerates."""
    h = hashlib.sha256()
    for fn in (_seed_pp, _lloyd_two, kmeans_many, _whiten_draws, null_draws, two_means_index_many):
        h.update(inspect.getsource(fn).encode("utf-8"))
    h.update(f"|draws={M3_NULL}|starts={M3_STARTS}|seed={C.SEED}|".encode("utf-8"))
    return h.hexdigest()


def null_cache_valid(path: str, n: int, m: int) -> bool:
    """R98: a cache file is trusted only when its key is `step7b_null_<n>_<m>`, its counts are the registered ones and its code stamp is the
    current one (a file without a stamp, or with another, is foreign and regenerates)."""
    try:
        with np.load(path) as z:
            return (str(z["key"]) == f"step7b_null_{n}_{m}" and int(z["draws"]) == M3_NULL and int(z["starts"]) == M3_STARTS
                    and str(z["stamp"]) == null_code_stamp() and z["idx"].shape == (M3_NULL,))
    except Exception:
        return False


def null_indices_whitened(n: int, m: int, cache: bool = True) -> np.ndarray:
    """M3w's null: the 2-means index of each whitened draw (cached per (n, m) on disk, R83; the cache trusted only by key + code stamp, R98)."""
    path = null_cache_path(n, m)
    if cache and os.path.exists(path) and null_cache_valid(path, n, m):
        with np.load(path) as z:
            return z["idx"]
    W, rng = null_draws(n, m)
    idx = two_means_index_many(W, rng, M3_STARTS)
    if cache:
        os.makedirs(CACHE_DIR, exist_ok=True)
        tmp = path + f".{os.getpid()}.partial.npz"
        np.savez(tmp, idx=idx, draws=M3_NULL, starts=M3_STARTS, key=f"step7b_null_{n}_{m}", stamp=null_code_stamp())
        os.replace(tmp, path)
    return idx


def null_indices_unwhitened(n: int, m: int, lam_kept: np.ndarray, rng_null) -> np.ndarray:
    """M3u's null: each whitened draw rescaled by the square roots of the data's own kept eigenvalues (the data's exact spectrum), its
    2-means index with starts from the set's `_null` generator."""
    W, _r = null_draws(n, m)
    return two_means_index_many(W * np.sqrt(np.maximum(lam_kept, 1e-12))[None, None, :], rng_null, M3_STARTS)


OWN_SPACE_TOL = 1e-9


def tested_spectrum(Zp: np.ndarray) -> np.ndarray:
    """R95: the eigenvalues (descending) of the sample covariance of the rows actually tested, in the space they are tested in."""
    xc = Zp - Zp.mean(0)
    cov = xc.T @ xc / max(1, len(Zp) - 1)
    return np.sort(np.linalg.eigvalsh(cov))[::-1]


def null_for_node(Zp: np.ndarray, red, kind: str, rng_n, cache: bool) -> tuple:
    """R95: the M3 null of one node — the spectrum of the ROWS TESTED. In the node's own space (the power run, every child, the seeded
    refits) the rows' covariance is exactly the identity (whitened) or diag(red.lam) (parallel analysis), and the registered nulls serve
    unchanged: M3w's cached unit-spectrum indices, M3u's draws rescaled by `red.lam`. Under a REUSED space on other rows (the real run's
    mode-A runs, the floor's bootstrap resamples) the rows carry neither spectrum, so the whitened draws are rescaled by the square roots
    of the tested rows' own eigenvalues (the 2-means index is rotation-invariant, so this is their exact spectrum). -> (null, 'own' |
    'rescaled')."""
    n, m = Zp.shape
    ev = tested_spectrum(Zp)
    if kind == "w":
        if np.allclose(ev, 1.0, rtol=0.0, atol=OWN_SPACE_TOL):
            return null_indices_whitened(n, m, cache), "own"
    else:
        lam = np.asarray(red.lam, dtype=float)
        if lam.shape == ev.shape and np.allclose(ev, lam, rtol=OWN_SPACE_TOL, atol=OWN_SPACE_TOL):
            return null_indices_unwhitened(n, m, red.lam, rng_n), "own"
    return null_indices_unwhitened(n, m, ev, rng_n), "rescaled"


def split_rule(Z: np.ndarray, n_min: int, key: str, kind: str, cache: bool = True, top_space=None) -> dict:
    """M3w / M3u: a split against one population, recursive (levels 0.01 / 0.005 / 0.0025, at most three), the leaves the final labels,
    the means read in the TOP-LEVEL space. `top_space` (a fitted reduction) is reused for the top level when given (the real run's mode A);
    the null then carries the spectrum of the rows tested (R95, `null_for_node`)."""
    rng_s, rng_n, rng_p = C.rng_for(key + "_starts"), C.rng_for(key + "_null"), C.rng_for(key + "_perm")
    n = len(Z)
    labels = np.zeros(n, dtype=int)
    nodes = []
    top_red = [top_space]

    def test(rows: np.ndarray, depth: int, space=None) -> None:
        nonlocal labels
        if depth >= len(M3_LEVELS) or len(rows) < 2 * n_min:
            nodes.append({"depth": depth, "n": len(rows), "p": None, "index": None, "split": False, "m": None, "why": "leaf: too small or too deep"})
            return
        Zr = Z[rows]
        red = space if space is not None else (G.PCA(Zr) if kind == "w" else ParallelAnalysis(Zr, rng_p))
        if depth == 0:
            top_red[0] = red
        Zp = red.transform(Zr)
        m = red.m
        index, fit = two_means_index(Zp, rng_s, M3_STARTS)
        null, null_kind = null_for_node(Zp, red, kind, rng_n, cache)                   # R95
        p = (1 + int((null <= index).sum())) / (M3_NULL + 1.0)
        sizes = np.bincount(fit["labels"], minlength=2)
        ok = p < M3_LEVELS[depth] and sizes.min() >= n_min
        nodes.append({"depth": depth, "n": len(rows), "p": p, "index": float(index), "split": bool(ok), "m": m, "sizes": sizes.tolist(),
                      "level": M3_LEVELS[depth], "null": null_kind})
        if not ok:
            return
        new = labels.max() + 1
        labels[rows[fit["labels"] == 1]] = new
        test(rows[fit["labels"] == 0], depth + 1)
        test(rows[fit["labels"] == 1], depth + 1)

    test(np.arange(n), 0, top_space)
    _u, inv = np.unique(labels, return_inverse=True)
    labels = inv
    k = int(labels.max()) + 1
    top = top_red[0] if top_red[0] is not None else (G.PCA(Z) if kind == "w" else ParallelAnalysis(Z, C.rng_for(key + "_perm")))
    Zt = top.transform(Z)
    out = {"k": k, "labels": labels, "means": group_means(Zt, labels, k), "nodes": nodes, "rule": "split test", "top": top}
    out["detail"] = "|".join(f"d{nd['depth']}:n{nd['n']}" + (f":p{nd['p']:.4f}" if nd["p"] is not None else "") + (":S" if nd["split"] else "") for nd in nodes)
    out["top_p"] = nodes[0]["p"] if nodes else None
    out["top_index"] = nodes[0]["index"] if nodes else None
    return out


def _log_gauss_diag(Zp: np.ndarray, mu: np.ndarray, var: np.ndarray) -> np.ndarray:
    """(n, k) log densities of diagonal Gaussians."""
    d = Zp[:, None, :] - mu[None, :, :]
    return -0.5 * (np.log(2 * np.pi * var)[None, :, :] + d * d / var[None, :, :]).sum(2)


def em_diag(Zp: np.ndarray, k: int, rng, starts: int = M4_STARTS) -> dict:
    """R84: a diagonal Gaussian mixture with k groups, `starts` EM starts seeded by k-means++, the best log-likelihood kept."""
    n, m = Zp.shape
    if k == 1:
        mu = Zp.mean(0, keepdims=True)
        var = np.maximum(Zp.var(0, keepdims=True), M4_FLOOR)
        ll = float(_log_gauss_diag(Zp, mu, var).sum())
        return {"ll": ll, "w": np.ones(1), "mu": mu, "var": var, "labels": np.zeros(n, dtype=int), "resp": np.ones((n, 1))}
    best = None
    for _s in range(starts):
        mu = _seed_pp(Zp[None], k, rng, 1)[0, 0]                                   # k centres by k-means++
        lab = G.nearest(Zp, mu)
        var = np.empty((k, m))
        for j in range(k):
            mem = Zp[lab == j]
            var[j] = np.maximum(mem.var(0), M4_FLOOR) if len(mem) > 1 else np.maximum(Zp.var(0), M4_FLOOR)
        w = np.full(k, 1.0 / k)
        prev = -np.inf
        for _it in range(M4_ITER):
            lp = _log_gauss_diag(Zp, mu, var) + np.log(w)[None, :]
            mx = lp.max(1, keepdims=True)
            lse = mx[:, 0] + np.log(np.exp(lp - mx).sum(1))
            ll = float(lse.sum())
            resp = np.exp(lp - lse[:, None])
            nk = resp.sum(0)
            w = nk / n
            with np.errstate(invalid="ignore", divide="ignore"):
                mu_new = (resp.T @ Zp) / nk[:, None]
            mu = np.where(nk[:, None] > 0, mu_new, mu)
            d = Zp[:, None, :] - mu[None, :, :]
            with np.errstate(invalid="ignore", divide="ignore"):
                var_new = np.einsum("nk,nkm->km", resp, d * d) / nk[:, None]
            var = np.maximum(np.where(nk[:, None] > 0, var_new, var), M4_FLOOR)
            if abs(ll - prev) < M4_TOL:
                break
            prev = ll
        lp = _log_gauss_diag(Zp, mu, var) + np.log(np.maximum(w, 1e-300))[None, :]
        mx = lp.max(1, keepdims=True)
        lse = mx[:, 0] + np.log(np.exp(lp - mx).sum(1))
        ll = float(lse.sum())
        if best is None or ll > best["ll"]:
            best = {"ll": ll, "w": w, "mu": mu, "var": var, "labels": lp.argmax(1), "resp": np.exp(lp - lse[:, None])}
    return best


def gmm_assign(model: dict, Zp: np.ndarray) -> np.ndarray:
    lp = _log_gauss_diag(Zp, model["mu"], model["var"]) + np.log(np.maximum(model["w"], 1e-300))[None, :]
    return lp.argmax(1)


def mixture_rule(Zp: np.ndarray, n_min: int, key: str) -> dict:
    """M4: k = 1..8 by the lowest BIC (p = 2km + k - 1); a k whose hard-assigned groups include one under n_min is skipped, not merged."""
    rng = C.rng_for(key + "_em")
    n, m = Zp.shape
    sweep = {}
    for k in range(1, G.K_RANGE[-1] + 1):
        fit = em_diag(Zp, k, rng)
        p = 2 * k * m + k - 1
        bic = -2.0 * fit["ll"] + p * math.log(n)
        sizes = np.bincount(fit["labels"], minlength=k)
        sweep[k] = {"bic": bic, "ll": fit["ll"], "sizes": sizes.tolist(), "size_ok": bool(sizes.min() >= n_min) or k == 1, "fit": fit}
    eligible = [k for k in sweep if sweep[k]["size_ok"]]
    k = min(eligible, key=lambda kk: sweep[kk]["bic"])
    fit = sweep[k]["fit"]
    labels = fit["labels"]
    _u, inv = np.unique(labels, return_inverse=True)
    out = {"sweep": sweep, "rule": "mixture BIC", "k": int(inv.max()) + 1, "labels": inv, "means": group_means(Zp, inv, int(inv.max()) + 1),
           "model": {"w": fit["w"], "mu": fit["mu"], "var": fit["var"]}}
    out["detail"] = "|".join(f"{kk}:{s['bic']:.0f}" + ("" if s["size_ok"] else "x") for kk, s in sweep.items())
    return out


def run_method(name: str, spaces: Spaces, n_min: int, key: str, cache: bool = True, top_space=None, Zp_given: np.ndarray = None, Z: np.ndarray = None) -> dict:
    """One method on one matrix: `spaces` carries the reductions (the PRIMARY's shared space for a mode-A run, whose own rows come as `Z`
    zero-filled and `Zp_given` reduced); `key` = `step7b_<method>_<set>` or `step7b_real_<method>_<run>`. -> the fit (k, labels, means in
    the method's space, detail, seconds)."""
    t0 = time.time()
    kind = SPACE_OF[name]
    Z = spaces.Z if Z is None else Z
    Zp = Zp_given if Zp_given is not None else spaces.transform(Z, kind)
    if name in ("M0", "M1"):
        fit = ps_rule(Zp, n_min, key)
    elif name in ("M2w", "M2u"):
        fit = bootstrap_rule(Zp, n_min, key)
    elif name in ("M3w", "M3u"):
        fit = split_rule(Z, n_min, key, "w" if name == "M3w" else "u", cache, top_space=top_space if top_space is not None else spaces.red[kind])
    elif name == "M4":
        fit = mixture_rule(Zp, n_min, key)
    else:
        raise ValueError(name)
    fit.update({"method": name, "space": kind, "m": Zp.shape[1], "seconds": time.time() - t0})
    return fit


def assign(fit: dict, Zp: np.ndarray) -> np.ndarray:
    """§7.2: a row's group under a fitted method — the posterior argmax for M4, the nearest group / leaf mean otherwise."""
    if fit["method"] == "M4":
        return gmm_assign(fit["model"], Zp)
    return G.nearest(Zp, fit["means"])


def refit_at_k(fit: dict, spaces: Spaces, Zp: np.ndarray, Z: np.ndarray, n_min: int, key: str, cache: bool = True) -> dict:
    """§7.2's noise-floor refit (R91): k-means at the primary's k (M1 / M2, the registered 20 starts), the whole split procedure (M3), EM
    at the primary's k (M4). -> {'labels', 'means', 'method', 'model'?}. `cache`: M3's null cache on disk (tests pass False)."""
    name, k = fit["method"], fit["k"]
    if name in ("M3w", "M3u"):
        r = split_rule(Z, n_min, key, "w" if name == "M3w" else "u", cache, top_space=spaces.red[SPACE_OF[name]])
        r["method"] = name
        return r
    if name == "M4":
        rng = C.rng_for(key + "_em")
        model = em_diag(Zp, k, rng)
        return {"labels": model["labels"], "means": group_means(Zp, model["labels"], k), "method": name, "model": model, "k": k}
    km = kmeans_v(Zp, k, C.rng_for(key + "_starts"), G.N_STARTS)
    return {"labels": km["labels"], "means": group_means(Zp, km["labels"], k), "method": name, "k": k}


def noise_floor_7b(primary: dict, n_min: int, n_refits: int = G.N_REFITS, cache: bool = True) -> dict:
    """§7.2 / §5: the primary against itself under 5 seeded refits and 5 bootstrap refits of the CARRIED method (R91); the same shape as
    06_groups.noise_floor. `cache`: M3's null cache on disk (the real run; tests pass False or redirect CACHE_DIR)."""
    fit, spaces, Zp, Z = primary["fit7b"], primary["spaces7b"], primary["Zp"], primary["Z"]
    name = fit["method"]
    n = len(Zp)
    seeded, boot, boot_rows = [], [], []
    for i in range(1, n_refits + 1):
        r = refit_at_k(fit, spaces, Zp, Z, n_min, f"step7b_real_{name}_floor_seed{i}", cache)
        pairs = G.hungarian(np.sqrt(G._d2(fit["means"], r["means"])))
        match = {a: b for a, b in pairs}
        seeded.append(float(np.mean([match.get(p) != q for p, q in zip(fit["labels"], r["labels"])])))
        rng = C.rng_for(f"step7b_real_{name}_floor_boot{i}_boot")
        idx = rng.integers(0, n, n)
        if name in ("M3w", "M3u"):                        # R102 (Re-registration 1 item 3): the split test runs on the resample's DISTINCT rows
            idx = np.unique(idx)
            boot_rows.append(int(len(idx)))
        r = refit_at_k(fit, spaces, Zp[idx], Z[idx], n_min, f"step7b_real_{name}_floor_boot{i}", cache)
        r["method"] = name
        lab = assign(r, Zp)                                # every row assigned (nearest leaf mean for M3)
        pairs = G.hungarian(np.sqrt(G._d2(fit["means"], r["means"])))
        match = {a: b for a, b in pairs}
        boot.append(float(np.mean([match.get(p) != q for p, q in zip(fit["labels"], lab)])))
    return {"seeded": seeded, "bootstrap": boot, "floor_seeded": float(np.mean(seeded)), "floor_bootstrap": float(np.mean(boot)),
            "floor": max(float(np.mean(seeded)), float(np.mean(boot))), "boot_rows": boot_rows}


def print_fit(fit: dict, say, label: str, n: int, n_min: int) -> None:
    """The method's own sweep, printed the way 06_groups prints the registered k sweep."""
    name = fit["method"]
    say(f"\n### {name} — {label} (n = {n} rows in {fit['m']} {'whitened' if fit['space'] == 'whitened' else 'kept-unwhitened'} components, minimum group size {n_min})")
    if name in ("M0", "M1"):
        rows = [(k, f"{s['strength']:.3f}", "yes" if s["strength_ok"] else "no", min(s["sizes"]), "yes" if s["size_ok"] else "no", " ".join(str(x) for x in s["sizes"])) for k, s in fit["sweep"].items()]
        table(say, ["k", "prediction strength", f">= {G.STRENGTH_LINE}", "smallest group", ">= minimum", "group sizes"], rows)
    elif name in ("M2w", "M2u"):
        rows = [(k, f"{s['ari']:.3f}", "yes" if s["ari_ok"] else "no", min(s["sizes"]), "yes" if s["size_ok"] else "no", " ".join(str(x) for x in s["sizes"])) for k, s in fit["sweep"].items()]
        table(say, ["k", "mean adjusted Rand (30 bootstraps)", f">= {M2_LINE}", "smallest group", ">= minimum", "group sizes"], rows)
    elif name in ("M3w", "M3u"):
        rows = [(nd["depth"], nd["n"], nd.get("m", ""), f"{nd['index']:.4f}" if nd["index"] is not None else "", f"{nd['p']:.4f}" if nd["p"] is not None else "",
                 nd.get("level", ""), "SPLIT" if nd["split"] else "no", " ".join(str(x) for x in nd.get("sizes", [])), nd.get("null", "")) for nd in fit["nodes"]]
        table(say, ["depth", "n", "components", "2-means index", "p", "level", "split", "sizes", "null spectrum (R95)"], rows)
    elif name == "M4":
        rows = [(k, f"{s['bic']:.1f}", f"{s['ll']:.1f}", min(s["sizes"]), "yes" if s["size_ok"] else "no (skipped)", " ".join(str(x) for x in s["sizes"])) for k, s in fit["sweep"].items()]
        table(say, ["k", "BIC", "log-likelihood", "smallest group", "eligible", "group sizes"], rows)
    say(f"- k by {fit['rule']}: {fit['k']}" + (" (one group)" if fit["k"] == 1 else "") + f"; group sizes {np.bincount(fit['labels']).tolist()}")


# ---- scoring (§6) ------------------------------------------------------------------------------------------------------------------------
def score(fit: dict, st: dict) -> dict:
    k_true, labels = st["k_true"], st["labels"]
    if k_true == 1:
        return {"false_alarm": fit["k"] >= 2, "hit": None, "ari": None}
    a = ari(fit["labels"], labels)
    return {"false_alarm": None, "hit": bool(fit["k"] == k_true and a >= HIT_ARI), "ari": float(a)}


TSV_COLS = ["world", "cell", "i", "fresh", "set_key", "block", "delta", "sep", "share", "k_true", "columns", "method", "k", "false_alarm", "hit", "ari",
            "oracle_hit", "oracle_ari", "m", "seconds", "detail"]


def run_set(ctx: ShapeContext, world: str, cell: str, i: int, spec: dict, colsets: tuple, methods: tuple, fresh: bool = False, cache: bool = True) -> dict:
    """One set through the methods on each column set. -> {'rows': [tsv rows], 'c2', 'c3', 'oracle', 'timing': {(colset, method): s}, 'index_w'}."""
    st = make_set(ctx, world, cell, i, spec, fresh)
    sid = set_id(world, cell, i, fresh)
    orc = oracle(ctx, st, spec)
    out = {"rows": [], "c2": check_c2(ctx, st, spec), "c3": check_c3(ctx, st), "oracle": orc, "timing": {}, "index_w": None, "m_w": None}
    blocks = "+".join(b for b, _c in spec.get("groups", [])) or ""
    for colset in colsets:
        idx = ctx.pattern_free if colset == "pattern_free" else list(range(ctx.p))
        Z = st["Z"][:, idx]
        spaces = Spaces(Z, f"step7b_M1_{sid}_perm")
        if colset == "registered":
            out["m_w"] = spaces.m("whitened")
            out["m_pa"] = spaces.m("pa")
        for name in methods:
            fit = run_method(name, spaces, N_MIN, f"step7b_{name}_{sid}", cache)
            sc = score(fit, st)
            if name == "M3w" and colset == "registered":
                out["index_w"] = fit["top_index"]
            out["timing"][(colset, name)] = fit["seconds"]
            out["rows"].append({"world": world, "cell": cell, "i": i, "fresh": fresh, "set_key": st["key"], "block": blocks, "delta": spec.get("delta"),
                                "sep": None if spec.get("sep") is None else round(spec["sep"], 4), "share": spec.get("share", ""), "k_true": st["k_true"],
                                "columns": colset, "method": name, "k": fit["k"], "false_alarm": sc["false_alarm"], "hit": sc["hit"],
                                "ari": None if sc["ari"] is None else round(sc["ari"], 4), "oracle_hit": orc["hit"],
                                "oracle_ari": None if orc["ari"] is None else round(orc["ari"], 4), "m": fit["m"], "seconds": round(fit["seconds"], 3),
                                "detail": fit["detail"]})
    return out


# ---- the power tables, qualification, selection, the size line (§6) ----------------------------------------------------------------------
def tabulate(rows: list) -> dict:
    """{(columns, method): {'N1': (fa, n), 'N2': (fa, n), ('curve', delta, block): (hits, n), ('small', block): ..., 'three': ...}}."""
    acc = collections.defaultdict(lambda: collections.defaultdict(lambda: [0, 0]))
    for r in rows:
        if r["fresh"]:
            continue
        key = (r["columns"], r["method"])
        if r["world"] in ("N1", "N2"):
            cell = r["world"]
            val = r["false_alarm"]
        elif r["world"] == "curve":
            cell = ("curve", r["delta"], r["block"])
            val = r["hit"]
        elif r["world"] == "small":
            cell = ("small", r["block"])
            val = r["hit"]
        else:
            cell = ("three",)
            val = r["hit"]
        acc[key][cell][0] += int(bool(val))
        acc[key][cell][1] += 1
    return {k: {c: tuple(v) for c, v in d.items()} for k, d in acc.items()}


def oracle_table(rows: list) -> dict:
    """Per cell: the oracle's hit share and mean ARI (one entry per set: read from the M0 / registered rows)."""
    acc = collections.defaultdict(list)
    for r in rows:
        if r["fresh"] or r["method"] != METHODS[0] or r["columns"] != "registered" or r["oracle_hit"] is None:
            continue
        cell = ("curve", r["delta"], r["block"]) if r["world"] == "curve" else ("small", r["block"]) if r["world"] == "small" else ("three",)
        acc[cell].append((bool(r["oracle_hit"]), float(r["oracle_ari"])))
    return {c: (sum(1 for h, _a in v if h), len(v), float(np.mean([a for _h, a in v]))) for c, v in acc.items()}


def pooled(tab: dict, cells_: list) -> tuple:
    x = sum(tab.get(c, (0, 0))[0] for c in cells_)
    n = sum(tab.get(c, (0, 0))[1] for c in cells_)
    return x, n


def qualification(tabs: dict, colset: str) -> dict:
    """§6: per eligible method on one column set — the lines and the verdict."""
    out = {}
    target = [("curve", TARGET_DELTA, b) for b in BLOCK_NAMES]
    for name in ELIGIBLE:
        t = tabs.get((colset, name), {})
        n1, n2 = t.get("N1", (0, 0)), t.get("N2", (0, 0))
        tp = pooled(t, target)
        per_block = {b: t.get(("curve", TARGET_DELTA, b), (0, 0)) for b in BLOCK_NAMES}
        n1_ok = n1[1] > 0 and n1[0] <= FA_LINES["N1"]
        n2_ok = n2[1] > 0 and n2[0] <= FA_LINES["N2"]
        tp_ok = tp[1] > 0 and tp[0] >= TARGET_POOLED_LINE
        pb_ok = all(v[1] > 0 and v[0] >= TARGET_BLOCK_LINE for v in per_block.values())
        out[name] = {"N1": n1, "N2": n2, "target": tp, "per_block": per_block, "N1_ok": n1_ok, "N2_ok": n2_ok, "target_ok": tp_ok, "blocks_ok": pb_ok,
                     "qualifies": n1_ok and n2_ok and tp_ok and pb_ok, "power": (100.0 * tp[0] / tp[1]) if tp[1] else 0.0}
    return out


def select(qual: dict) -> "str | None":
    """§6: the qualifier with the highest pooled target power; within 5 points of the top -> the order M1, M2w, M2u, M3w, M3u, M4."""
    q = [n for n in ELIGIBLE if qual[n]["qualifies"]]
    if not q:
        return None
    top = max(qual[n]["power"] for n in q)
    near = [n for n in ELIGIBLE if n in q and qual[n]["power"] >= top - TIE_POINTS]
    return near[0]


def decide(tabs: dict) -> dict:
    """§6 end to end: C1, the selection on the 75 columns, Fallback 1 (no qualifier there -> the selection repeats on the gap-free arm,
    Re-registration 1 item 4 / R103), Fallback 2 (no qualifier on either arm), the size-line source. -> the decision."""
    m0 = tabs.get(("registered", "M0"), {})
    m0_target = pooled(m0, [("curve", TARGET_DELTA, b) for b in BLOCK_NAMES])
    c1_ok = m0_target[0] < TARGET_POOLED_LINE
    qual_75 = qualification(tabs, "registered")
    qual_56 = qualification(tabs, "pattern_free")
    out = {"m0_target": m0_target, "c1_ok": c1_ok, "qual": {"registered": qual_75, "pattern_free": qual_56}}
    if not c1_ok:
        out.update({"outcome": "one style with power (C1)", "carried": None, "columns": "registered", "fallback1": False, "size_source": ("M0", "registered"),
                    "size_source_why": "C1: the registered method reaches the target; its real null stands"})
        return out
    carried = select(qual_75)
    fallback1 = carried is None                                                            # R103: no qualifier on the 75 columns
    arm = "registered"
    if fallback1:
        arm = "pattern_free"
        carried = select(qual_56)                                                          # the same lines and order, on the 56-column arm
    out.update({"fallback1": fallback1, "columns": arm, "carried": carried})
    if carried is not None:
        out["outcome"] = f"carried {carried} on {arm}"
        out["size_source"] = (carried, arm)
        out["size_source_why"] = "the carried method"
        return out
    out["outcome"] = "no style we could show we would see"                                 # Fallback 2: no qualifier on either arm
    out["columns"] = "registered"                                                          # the primary described on its registered columns (§7.1)
    for arm_ in COLSETS:                                                                   # R103: the 75-column arm first (the whole curve ran there), then the 56
        passing = [n for n in ELIGIBLE if out["qual"][arm_][n]["N1_ok"] and out["qual"][arm_][n]["N2_ok"]]
        if passing:
            src = max(passing, key=lambda n: (out["qual"][arm_][n]["power"], -ELIGIBLE.index(n)))
            out["size_source"] = (src, arm_)
            out["size_source_why"] = f"the highest-power method among those passing both false-alarm lines on the {arm_} columns (none qualified on either arm)"
            break
    else:
        out["size_source"] = ("M0", "registered")
        out["size_source_why"] = "M0 (no method passes both false-alarm lines on either arm); its false-alarm rate printed beside"
    return out


def spread_all_trades(delta: float, share: float = 0.3) -> float:
    """A Delta within-group spread on a `share` group, in units of the measure's spread across ALL trades."""
    return delta / math.sqrt(1.0 + share * (1 - share) * delta * delta)


def size_line(tabs: dict, source: tuple) -> dict:
    """§6: Delta* = the smallest Delta-equivalent of the curve with pooled power >= 80% (or 'more than 3.0'); the 15% group at Delta 2.0."""
    name, arm = source
    t = tabs.get((arm, name), {})
    curve = {}
    for delta in DELTAS:
        x, n = pooled(t, [("curve", delta, b) for b in BLOCK_NAMES])
        if n:
            curve[delta] = (x, n)
    passing = [d for d, (x, n) in curve.items() if x / n >= 0.80]
    if passing:
        star = min(passing)
        star_text = f"{star:.1f}"
    elif arm == "pattern_free":
        star, star_text = None, "more than 1.5 (the other separations were not run on the 56 columns)"
    else:
        star, star_text = None, "more than 3.0"
    small = pooled(t, [("small", b) for b in BLOCK_NAMES])
    y = f"{100.0 * small[0] / small[1]:.0f} in 100" if small[1] else "not run on the 56 columns"
    x_text = f"{spread_all_trades(star):.1f}" if star is not None else "—"
    n1 = t.get("N1", (0, 0))
    text = (f"this method ({name}, {arm}) finds a hidden group of 30% of trades only when it stands apart as clearly as {star_text} within-group spreads "
            f"on three separate measures (about {x_text} of each measure's spread across all his trades); a 15% group at Delta 2.0: {y}")
    if name == "M0":
        text += f"; M0's false-alarm rate on N1: {rate_str(n1[0], n1[1])}"
    return {"delta_star": star, "text": text, "curve": curve, "small": small}


# ---- the reference reproduction (R89) ----------------------------------------------------------------------------------------------------
def reference_blocks(lines: list) -> tuple:
    """(the k-sweep block, the claim lines) of a 06_groups dry-run printout's lines."""
    sweep, claims = [], []
    i = 0
    while i < len(lines) and not lines[i].startswith("### k sweep — PRIMARY"):
        i += 1
    while i < len(lines):
        sweep.append(lines[i])
        if lines[i].startswith("- k chosen by the rule"):
            break
        i += 1
    j = 0
    while j < len(lines) and not lines[j].startswith("## Claims"):
        j += 1
    for ln in lines[j + 1:]:
        if ln.startswith("  ["):
            claims.append(ln)
        elif ln.startswith("RESULT:"):
            break
    return sweep, claims


def reproduces_reference(lines: list) -> tuple:
    """(ok, why): the new default dry run's k-sweep block and first 32 claim lines against the pinned reference copy (sha checked)."""
    if not os.path.exists(REF_DRY):
        return False, f"the reference copy is missing ({os.path.basename(REF_DRY)})"
    if C.sha(REF_DRY) != REF_DRY_SHA:
        return False, f"the reference copy's sha is not the pinned {REF_DRY_SHA[:8]}"
    with open(REF_DRY, encoding="utf-8") as fh:
        ref = fh.read().splitlines()
    rs, rc = reference_blocks(ref)
    ns, nc = reference_blocks([l for ln in lines for l in ln.split("\n")])          # Say's lines may carry a leading newline (a section header)
    nc = nc[: len(rc)]
    if not rs or not rc:
        return False, "the reference holds no k-sweep block or no claim lines"
    if rs != ns:
        for a, b in zip(rs, ns):
            if a != b:
                return False, f"k sweep differs: reference {a!r} vs new {b!r}"
        return False, f"k sweep block length differs: reference {len(rs)} lines, new {len(ns)}"
    if rc != nc:
        for a, b in zip(rc, nc):
            if a != b:
                return False, f"claim differs: reference {a!r} vs new {b!r}"
        return False, f"claim lines: reference {len(rc)}, new {len(nc)}"
    return True, ""


# ---- the real-data seal, pins, gates -----------------------------------------------------------------------------------------------------
_SEALED = []                                             # [(holder, name, the original)] while sealed
SEAL_PREFIXES = ("load_", "read_", "preload_")
SEAL_MODULES = ("asis_common", "01_points", "05_tiers", "06_groups")


def sealed_loader_names() -> list:
    """R104: the sealed set, DERIVED — every callable of asis_common / 01_points / 05_tiers / 06_groups whose name starts load_ / read_ /
    preload_, the MinuteStore class and its read_minute_file alias on asis_common's R namespace, and 06_groups' build_features.
    -> [(holder, name)] in a fixed order."""
    out = []
    for mod in (C, P, T, G):
        for nm in sorted(dir(mod)):
            if nm.startswith(SEAL_PREFIXES) and callable(getattr(mod, nm)):
                out.append((mod, nm))
        if callable(getattr(mod, "MinuteStore", None)):
            out.append((mod, "MinuteStore"))
    if callable(getattr(getattr(C, "R", None), "read_minute_file", None)):
        out.append((C.R, "read_minute_file"))
    out.append((G, "build_features"))
    return out


def seal_real_loaders() -> None:
    """The made-up stages open no real-data file but the shape file: every real-data loader of the four modules (R104, derived) raises."""
    def _raise(*_a, **_k):
        raise GuardStop("7b: the made-up stages (--dry-run / --power) open no real-data file but the shape file")
    if _SEALED:
        return
    for holder, nm in sealed_loader_names():
        _SEALED.append((holder, nm, getattr(holder, nm)))
        setattr(holder, nm, _raise)


def unseal_real_loaders() -> None:
    for holder, nm, fn in reversed(_SEALED):
        setattr(holder, nm, fn)
    _SEALED.clear()


def module_shas_line() -> str:
    return C.modules_line(MODULE_FILES_B)


def pins_b(doc: str = None, dry_path: str = None, include_outputs: bool = False) -> dict:
    """§11: step 7's pins (05's inputs and modules, both doc bodies, tiers.tsv, 06_groups.py, its default dry run) + doc_body_7b, the
    reference pair, the shape file and its printout, this module, this stage's dry run; the outputs when asked."""
    p = G.pins_g(T.DOC7, G.P06["dry"])
    p["doc_body_7b"] = C.doc_body_sha(doc or DOC7B)
    p["reference_06_groups.py"] = REF_06_SHA
    p["reference_06_groups_dryrun"] = REF_DRY_SHA
    p["step7b_shape"] = T._sha_or_absent(SHAPE_NPZ)
    p["shape7b_printout"] = T._sha_or_absent(P06B["shape"])
    p["06b_power.py"] = C.sha(os.path.join(HERE, "06b_power.py"))
    p["dryrun7b_printout"] = T._sha_or_absent(dry_path or P06B["dry"])
    if include_outputs:
        p["power7b_printout"] = T._sha_or_absent(P06B["run"])
        p["step7b_power"] = T._sha_or_absent(POWER_TSV)
    return p


def stage_pin_keys_b(pins: dict) -> list:
    base = set(C.pins(T.DOC7, include_outputs=False))
    return [k for k in pins if k not in base]


def ledger_has_stage(prefix: str) -> list:
    if not os.path.exists(C.LEDGER):
        return []
    rows = pd.read_csv(C.LEDGER, sep="\t", dtype=str, keep_default_na=False).to_dict("records")
    return [r["stage"] for r in rows if r["stage"].startswith(prefix)]


def doc_frozen(doc: str = None) -> list:
    """The reasons the 7b registration is not frozen (empty = frozen): exactly one marker and doc_body_7b pasted below it."""
    doc = doc or DOC7B
    if not os.path.exists(doc):
        return [f"the 7b registration is missing ({doc})"]
    miss = C.freeze_missing(doc, {"doc_body_7b": C.doc_body_sha(doc)})
    return ["doc_body_7b is not pinned below the 7b doc's freeze marker (freeze first)"] if miss else []


def shape_gate(doc: str = None, paths: dict = None) -> list:
    """--shape: refused until the doc is frozen; once (a ledger row or an output refuses)."""
    paths = paths or P06B
    problems = doc_frozen(doc)
    rows = ledger_has_stage(STAGE_B + "shape")
    if rows:
        problems.append("a step7b_shape ledger row exists (once means once): " + ", ".join(rows))
    existing = [q for q in (SHAPE_NPZ, paths["shape"]) if os.path.exists(q)]
    if existing:
        problems.append("outputs exist: " + ", ".join(existing))
    return problems


def _dry_run_ok(path: str, modules: str, what: str) -> list:
    problems = []
    if not C.dry_run_complete(path):
        return [f"{what} has not completed ({os.path.basename(path)})"]
    mm = C.printout_mismatches(path)
    if mm is None:
        problems.append(f"{what}: the RESULT line is missing or unreadable")
    elif mm > 0:
        problems.append(f"{what} ended with {mm} MISMATCH")
    ml = C.printout_line(path, "- modules: ")
    if ml != modules:
        problems.append(f"{what} was made by other code than the modules on disk (or carries no module line): rerun it first" + (f" ({ml})" if ml else ""))
    return problems


def power_gate(doc: str = None, paths: dict = None) -> list:
    """--power: the 7b dry run complete with 0 MISMATCH by the modules on disk (and 06_groups' default dry run, R89); every pin below the 7b
    marker, none ABSENT; the ledger verifies; no output and no step7b_power ledger row."""
    paths = paths or P06B
    doc = doc or DOC7B
    problems = _dry_run_ok(paths["dry"], module_shas_line(), "the 7b dry run")
    problems += _dry_run_ok(G.P06["dry"], G.module_shas_line(), "06_groups' default dry run")
    if not os.path.exists(doc):
        problems.append(f"the 7b registration is missing ({doc})")
        return problems
    pins = pins_b(doc, paths["dry"])
    miss = C.freeze_missing(doc, pins)
    if miss:
        problems.append("pins not below the 7b doc's freeze marker (--print-pins, paste): " + ", ".join(miss))
    absent = [k for k in stage_pin_keys_b(pins) if pins[k] == "ABSENT"]
    if absent:
        problems.append("pins reading ABSENT (the file must exist and be pinned): " + ", ".join(absent))
    bad = C.ledger_verify() if os.path.exists(C.LEDGER) else ["ledger missing"]
    if bad:
        problems.append("ledger: " + "; ".join(bad))
    rows = ledger_has_stage(STAGE_B + "power")
    if rows:
        problems.append("a step7b_power ledger row exists (once means once): " + ", ".join(rows))
    existing = [q for q in (POWER_TSV, paths["run"]) if os.path.exists(q)]
    if existing:
        problems.append("outputs exist: " + ", ".join(existing))
    return problems


def power_outcome(path: str = None) -> "str | None":
    """The outcome named by the POWER COMPLETE line (None when the printout has not completed)."""
    path = path or P06B["run"]
    if not C.printout_ends(path, "POWER COMPLETE"):
        return None
    with open(path, encoding="utf-8") as fh:
        lines = [ln for ln in fh.read().splitlines() if ln.strip()]
    last = lines[-1]
    return last.split(":", 1)[1].strip() if ":" in last else ""


DEFAULT_OUTCOMES = ("one style with power (C1)", "no style we could show we would see")        # §11: the outcomes the registered --run serves (§7.1)


def power_printout_gate(doc: str = None, path: str = None) -> list:
    """R99 — what BOTH of 06_groups' 7b gates require of 06b_power.txt beyond its outcome: it ends POWER COMPLETE; it was made by the modules
    on disk (its `- modules:` line equals theirs — §11: the power run and the real run share one implementation); its pin sits below the 7b
    doc's marker (§11's Order: the result and pins written below the marker -> the real run); the `step7b_power` ledger row exists (the run
    that wrote it is the one the ledger recorded)."""
    path = path or P06B["run"]
    doc = doc or DOC7B
    if power_outcome(path) is None:
        return ["06b_power.txt has not completed (must end POWER COMPLETE)"]
    problems = []
    ml = C.printout_line(path, "- modules: ")
    if ml != module_shas_line():
        problems.append("06b_power.txt was made by other code than the modules on disk (or carries no module line): the power run and the real run share one implementation (7b §11)"
                        + (f" ({ml})" if ml else ""))
    if not os.path.exists(doc) or C.freeze_missing(doc, {"power7b_printout": C.sha(path)}):
        problems.append("06b_power.txt's pin is not below the 7b doc's freeze marker")
    if "step7b_power" not in ledger_has_stage(STAGE_B + "power"):
        problems.append("no step7b_power ledger row (the power run that wrote 06b_power.txt is not on the ledger)")
    return problems


def named_by_power_complete(method: str, columns: str, doc: str = None, path: str = None) -> list:
    """06_groups' gate on a non-default --method / --columns (§11): 06b_power.txt ends POWER COMPLETE naming that method and column set, made
    by the modules on disk, pinned below the 7b marker and ledgered (R99)."""
    path = path or P06B["run"]
    problems = power_printout_gate(doc, path)
    if power_outcome(path) is None:
        return [f"06b_power.txt has not completed (must end POWER COMPLETE naming {method} on {columns})"]
    want = f"carried {method} on {columns}"
    outcome = power_outcome(path)
    if outcome != want:
        problems.append(f"POWER COMPLETE names {outcome!r}, not {want!r}")
    return problems


def default_run_gate(path: str = None, doc: str = None) -> list:
    """06_groups' DEFAULT --run (§11 / R90 / R99): POWER COMPLETE naming one of the two registered default outcomes (§7.1), made by the modules
    on disk, pinned below the 7b marker and ledgered; refused when it names a carried method (the registered run is the C1 / Fallback-2
    command) or anything unregistered."""
    path = path or P06B["run"]
    problems = power_printout_gate(doc, path)
    outcome = power_outcome(path)
    if outcome is None:
        return ["06b_power.txt has not completed (the --run waits for POWER COMPLETE, 7b §11)"]
    if outcome.startswith("carried "):
        problems.append(f"POWER COMPLETE names {outcome!r}: run `--run --method <carried> [--columns ...]`, not the registered run (7b §7.1)")
    elif outcome not in DEFAULT_OUTCOMES:
        problems.append(f"POWER COMPLETE names {outcome!r}, not one of the registered outcomes {DEFAULT_OUTCOMES}")
    return problems


# ---- the stages --------------------------------------------------------------------------------------------------------------------------
def _header(say, stage: str, refused_to: str) -> int:
    say(f"# #711 as-is STEP 7b (a stronger sorting method, proven on made-up trades first) — {stage} ({time.strftime('%Y-%m-%d %H:%M')})")
    say("Guards: no network, no production server, no paid call, nothing after 2024-12-31, the seven outcome folders never opened, nothing "
        "imported from the rule folders. No outcome of any trade is read, computed or printed (both name lists are scanned against every step-7 "
        "module and this one); no rule, setup name or pattern label enters.")
    hits = C.scan_identifiers([os.path.join(HERE, n) for n in SCAN_FILES_B], T.forbidden_all())
    if hits:
        say("IDENTIFIER SCAN FAILED: " + "; ".join(f"{os.path.basename(p)}:{ln} {t}" for p, ln, t in hits))
        say.write(refused_to)
        return 2
    say("- identifier scan: clean (the §3.1 names and the outcome names are absent from: " + ", ".join(SCAN_FILES_B) + ")")
    loaded = C.rule_modules_loaded()
    if loaded:
        say("RULE MODULE LOADED (guard 3): " + ", ".join(loaded))
        say.write(refused_to)
        return 2
    say("- import belt: no rule module in sys.modules")
    say("- modules: " + module_shas_line())
    return 0


def print_shape(ctx: ShapeContext, say, facts: dict = None) -> None:
    say(f"- n = {ctx.n} rows, {ctx.p} columns in run_columns('primary') order; blank cells {ctx.n_blank} of {ctx.n * ctx.p} "
        f"({100.0 * ctx.n_blank / (ctx.n * ctx.p):.1f}%); rows with no exit look-back at all: {int((ctx.mask_by_rank[:, ctx.lookback_idx].all(1)).sum())}")
    if facts:
        say(f"- pairs set to 0: {facts['pairs_thin']} sharing fewer than {THIN_PAIR} rows"
            + (f", {facts['pairs_zero_spread']} with no spread on a side" if facts.get("pairs_zero_spread") is not None else "")
            + f"; columns with under {THIN_PAIR} non-blank rows: " + (", ".join(f"{c} ({n})" for c, n in facts["thin_columns"]) or "none"))
        say(f"- eigenvalue clipping at {EIG_FLOOR:g}: smallest eigenvalue {facts['eig_min_before']:.5f} -> {facts['eig_min_after']:.5f}; largest change on pairs "
            f"sharing >= {WELL_SUPPORTED} rows {facts['clip_change_300']:.4f} (C5a line {CLIP_LINE}); on all pairs {facts['clip_change_all']:.4f}")
    off = ~np.eye(ctx.p, dtype=bool)
    say(f"- pairs sharing >= {WELL_SUPPORTED} rows: {int(((ctx.shared >= WELL_SUPPORTED) & off).sum() // 2)} of {ctx.p * (ctx.p - 1) // 2}; "
        f"|R| above 0.5 on {int(((np.abs(ctx.R) > 0.5) & off).sum() // 2)} pairs, above 0.8 on {int(((np.abs(ctx.R) > 0.8) & off).sum() // 2)}")
    say(f"- the real hold x exit-look-back coupling (R79): Spearman(hold rank, non-blank exit look-backs) = {ctx.hold_gap_spearman:.4f}")
    say(f"- the bend's factor: the first eigenvector carries {100.0 * ctx.lam1 / ctx.p:.1f}% of the variance of R")
    rows = []
    for b in BLOCK_NAMES:
        for delta in DELTAS:
            sep = sep_of(delta)
            sh = ctx.shift(b, sep)
            rows.append((b, f"{delta:.1f}", f"{sep:.2f}", f"{ctx.delta_b(b, sep):.3f}", f"{ctx.mahalanobis(sh):.3f}", f"{float(np.abs(sh).max()):.3f}",
                         ", ".join(f"{ctx.cols[k]} {sh[k]:+.2f}" for k in np.argsort(-np.abs(sh))[:5])))
    say("### the coherent shift per block (§4.4): Delta_B = sep / sqrt(1' R_BB^-1 1); every other column moves by what R implies; the hold by 0")
    table(say, ["block", "Delta-equiv", "sep", "Delta_B", "Mahalanobis after zeroing the hold", "largest |move|", "the five largest moves"], rows)
    say("### repeated values (counts only): runs of equal values per column among its non-blank cells")
    rr = [(c, int(sum(ctx.runs[k])), len(ctx.runs[k]), int(ctx.runs[k].max()) if len(ctx.runs[k]) else 0, int((ctx.runs[k] > 1).sum())) for k, c in enumerate(ctx.cols)]
    table(say, ["column", "non-blank", "distinct values", "largest run", "runs of 2+"], rr)


def stage_shape(a, say) -> int:
    rc = _header(say, "SHAPE (§4.1 — the only stage that opens real data)", P06B["refused"])
    if rc:
        return rc
    problems = shape_gate()
    if problems:
        for pr in problems:
            say("REFUSED: " + pr)
        say.write(P06B["refused"])
        return 3
    say("- shape gates: the 7b registration is frozen (doc_body_7b below its marker); no step7b_shape ledger row; no output exists")
    say("\n## Inputs (06_groups' own loaders)")
    I = G.load_inputs(say)
    tiers, ranges, L = I["tiers"], I["ranges"], I["L"]
    feats = G.build_features(L, tiers, ranges, say, modes=("middle",))
    feats.pop("_checks", None)
    cols = G.run_columns("primary")
    eids = G.run_rows("primary", tiers, feats)
    A = G.assemble(feats, eids, cols)
    maps = G.fit_maps(A["X"], cols)
    say(f"- primary rows fitted {len(A['eids'])} of {len(eids)} (dropped by the quarter rule: {len(A['dropped'])}); columns {len(cols)}")
    d = shape_from_matrix(A["X"], cols, maps, C.rng_for("step7b_hold_ties"))
    facts = d.pop("_facts")
    say("\n## The four summaries (§4.1)")
    ctx = ShapeContext(d)
    print_shape(ctx, say, facts)
    claims = Claims(say)
    say("\n## Claims")
    claims("fitted primary rows (§3: 658)", N_PRIMARY_FIT, int(d["n"]))
    claims("columns = run_columns('primary') (75)", 75, len(cols))
    claims("blank cells (structural + data) = 8,119 of 49,350", 8119, facts["n_blank"])
    claims("the shape file holds exactly §4.1's keys", sorted(SHAPE_KEYS), sorted(k for k in d))
    claims("C5a — the clipping changes no pair sharing >= 300 rows by more than 0.05", True, facts["clip_change_300"] <= CLIP_LINE)
    claims("R is positive definite after the clipping", True, facts["eig_min_after"] > 0)
    say("")
    say(claims.result())
    if any(not r[3] for r in claims.rows):
        say("SHAPE STOPPED: a MISMATCH — nothing written (the finding goes to the main loop)")
        say.write(P06B["refused"])
        return 4
    save_shape(d, SHAPE_NPZ)
    say(f"- written: {SHAPE_NPZ} ({C.sha(SHAPE_NPZ)[:16]}); no row's values leave this stage")
    say("SHAPE COMPLETE")
    say.write(P06B["shape"])
    C.ledger_append(STAGE_B + "shape", SHAPE_NPZ)
    C.ledger_append(STAGE_B + "shape_printout", P06B["shape"])
    return 0


def _pooled_corr_of_sets(S_list: list) -> tuple:
    return pairwise_corr(np.vstack(S_list))


def c5b_gaps(ctx: ShapeContext, corr: np.ndarray) -> dict:
    """The made-up correlation against R (and the unclipped R0) on pairs sharing >= 300 real rows; hold x exit look-back pairs apart."""
    off = ~np.eye(ctx.p, dtype=bool)
    well = (ctx.shared >= WELL_SUPPORTED) & off
    hold_lb = np.zeros((ctx.p, ctx.p), dtype=bool)
    for k in ctx.lookback_idx:
        hold_lb[ctx.j_hold, k] = hold_lb[k, ctx.j_hold] = True
    claim_pairs = well & ~hold_lb & np.isfinite(corr)
    gap = np.abs(corr - ctx.R)
    gap0 = np.abs(corr - ctx.R0)
    out = {"n_pairs": int(claim_pairs.sum() // 2), "max": float(gap[claim_pairs].max()) if claim_pairs.any() else 0.0,
           "rms": float(np.sqrt((gap[claim_pairs] ** 2).mean())) if claim_pairs.any() else 0.0,
           "max_unclipped": float(gap0[claim_pairs].max()) if claim_pairs.any() else 0.0,
           "rms_unclipped": float(np.sqrt((gap0[claim_pairs] ** 2).mean())) if claim_pairs.any() else 0.0}
    hl = hold_lb & well & np.isfinite(corr)
    out["hold_lookback"] = [(ctx.cols[k], int(ctx.shared[ctx.j_hold, k]), float(ctx.R[ctx.j_hold, k]), float(corr[ctx.j_hold, k])) for k in ctx.lookback_idx if hl[ctx.j_hold, k]]
    worst = sorted(((gap[i, j], i, j) for i in range(ctx.p) for j in range(i + 1, ctx.p) if claim_pairs[i, j]), reverse=True)[:12]
    out["worst"] = [(ctx.cols[i], ctx.cols[j], int(ctx.shared[i, j]), float(ctx.R[i, j]), float(corr[i, j]), float(g), len(ctx.runs[i]), len(ctx.runs[j])) for g, i, j in worst]
    return out


def stage_dry_run(a, say) -> int:
    rc = _header(say, "DRY RUN (made-up sets only)", P06B["dry"])
    if rc:
        return rc
    if not os.path.exists(SHAPE_NPZ):
        say(f"REFUSED: the shape file is missing ({SHAPE_NPZ}); run --shape first")
        say.write(P06B["dry"])
        return 3
    seal_real_loaders()
    say(f"- real-data loaders sealed (R104, derived): {len(_SEALED)} callables named load_* / read_* / preload_* across {', '.join(SEAL_MODULES)}, "
        "MinuteStore and build_features raise inside this stage")
    d = load_shape()
    ctx = ShapeContext(d)
    say(f"\n## The shape file ({C.sha(SHAPE_NPZ)[:16]}): keys {', '.join(sorted(d))}")
    off = ~np.eye(ctx.p, dtype=bool)
    well = (ctx.shared >= WELL_SUPPORTED) & off
    clip300 = float(np.abs(ctx.R - ctx.R0)[well].max()) if well.any() else 0.0
    clip_all = float(np.abs(ctx.R - ctx.R0)[off].max())
    print_shape(ctx, say, {"pairs_thin": int(((ctx.shared < THIN_PAIR) & off).sum() // 2), "pairs_zero_spread": None,
                           "thin_columns": [(ctx.cols[k], int(ctx.shared[k, k])) for k in range(ctx.p) if ctx.shared[k, k] < THIN_PAIR],
                           "eig_min_before": float(np.linalg.eigvalsh(ctx.R0).min()), "eig_min_after": float(np.linalg.eigvalsh(ctx.R).min()),
                           "clip_change_300": clip300, "clip_change_all": clip_all})
    claims = Claims(say)
    pc = plant_counts(ctx.n)
    say(f"- the plant counts at this shape's n = {ctx.n} (R93): curve {pc['curve']}, small {pc['small']}, three {pc['three']}; at the registered 658: "
        f"{plant_counts(N_PRIMARY_FIT)['curve']} / {plant_counts(N_PRIMARY_FIT)['small']} / {plant_counts(N_PRIMARY_FIT)['three']}")
    spec_of = {(w, c): s for w, c, _n, s in cells(ctx.n)}

    # ---- C6: the oracle at the target, 200 latent sets per block ----
    say(f"\n## C6 — the target is reachable: the oracle on {DRY_C6_SETS} latent target sets per block (steps 1 and 3 only)")
    c6 = {}
    t0 = time.time()
    for b in BLOCK_NAMES:
        cell = f"{b}_d{TARGET_DELTA:.1f}"
        spec = spec_of[("curve", cell)]
        hits, aris = 0, []
        for i in range(DRY_C6_SETS):
            st = make_set(ctx, "curve", cell, i, spec, through=3)
            o = oracle(ctx, st, spec)
            hits += int(o["hit"])
            aris.append(o["ari"])
        c6[b] = (hits, DRY_C6_SETS, float(np.mean(aris)))
    table(say, ["block", "oracle hits", "mean adjusted Rand", "line"], [(b, rate_str(h, n), f"{m:.3f}", f">= {C6_LINE:.0%}") for b, (h, n, m) in c6.items()])
    say(f"- {time.time() - t0:.1f}s")

    # ---- C2 / C3 on 50 latent sets per cell (steps 1-5, no method); C5b / C5c on the 50 N1 sets through the pipeline ----
    say(f"\n## C2 — the plant is there and survives the pipeline ({DRY_C2_SETS} latent sets per cell, steps 1-5; no method runs; the {DRY_C5_SETS} N1 / N2 sets "
        "go through step 6 for C5 and the index readout)")
    c2_rows, c2_fail, mono_ok, mono_all, c3_fail, c3_sets = [], 0, 0, 0, 0, 0
    S_n1, Z_n1, m_n1, idx_n1, idx_n2, pre_tie_n1 = [], [], [], [], [], []
    t0 = time.time()
    for world, cell, _n, spec in cells(ctx.n):
        aucs = collections.defaultdict(list)
        for i in range(DRY_C5_SETS if world in ("N1", "N2") else DRY_C2_SETS):
            through = 6 if world in ("N1", "N2") else 5
            st = make_set(ctx, world, cell, i, spec, through=through)
            c2 = check_c2(ctx, st, spec)
            for key, (al, line, af) in c2["auc"].items():
                aucs[key].append((al, line, af))
            mono_ok += c2["monotone_ok"]
            mono_all += c2["columns"]
            c3 = check_c3(ctx, st)
            c3_sets += 1
            c3_fail += int(not (c3["blank_ok"] and c3["spearman_ok"]))
            if world == "N1":
                S_n1.append(st["S"])
                Z_n1.append(st["Z"])
                pca = G.PCA(st["Z"])
                m_n1.append(pca.m)
                idx_n1.append(two_means_index(pca.transform(st["Z"]), C.rng_for(f"step7b_M3w_{set_id(world, cell, i)}_starts"))[0])
                pre = np.where(st["masks"], np.nan, st["latent"])
                pm = G.fit_maps(pre, ctx.cols)
                Spre = np.full(pre.shape, np.nan)
                for k, c in enumerate(ctx.cols):
                    Spre[:, k], _e = pm[c].apply(pre[:, k])
                pre_tie_n1.append(Spre)
            elif world == "N2":
                pca = G.PCA(st["Z"])
                idx_n2.append(two_means_index(pca.transform(st["Z"]), C.rng_for(f"step7b_M3w_{set_id(world, cell, i)}_starts"))[0])
        for (g, col), vals in aucs.items():
            al = float(np.mean([v[0] for v in vals]))
            line = vals[0][1]
            af = float(np.mean([v[2] for v in vals]))
            ok = al >= line
            c2_fail += int(not ok)
            c2_rows.append((world, cell, g, col, f"{al:.3f}", f"{line:.3f}", "OK" if ok else "BELOW", f"{af:.3f}"))
    table(say, ["world", "cell", "group", "block column", "AUC (latent, mean of sets)", "line Phi(Delta_B/sqrt2) - 0.02", "verdict", "final AUC (after ties and masks)"], c2_rows)
    say(f"- (b) the handed value is non-decreasing in the latent value: {mono_ok} of {mono_all} (set, column) pairs")
    say(f"- C3 over these {c3_sets} sets: {c3_fail} failing (the blank cells must be {ctx.n_blank}; Spearman(latent hold, non-blank exit look-backs) must equal {ctx.hold_gap_spearman:.3f})")
    say(f"- {time.time() - t0:.1f}s")

    say(f"\n## C5 — the shape is his: the generator against R, pooled over {len(pre_tie_n1)} N1 sets — the latent through the rank map, BEFORE the tie step "
        "(Re-registration 1 item 1, R101); the post-tie comparison beside as a readout")
    corr_pre, _c = _pooled_corr_of_sets(pre_tie_n1)
    g5 = c5b_gaps(ctx, corr_pre)
    corr_post, _cnt = _pooled_corr_of_sets(S_n1)
    g5post = c5b_gaps(ctx, corr_post)
    say(f"- (b) the pooled latent through the rank map against R on the {g5['n_pairs']} pairs sharing >= {WELL_SUPPORTED} real rows (hold x exit look-back pairs apart): "
        f"largest gap {g5['max']:.4f} (line {C5B_MAX}), root-mean-square {g5['rms']:.4f} (line {C5B_RMS})")
    say(f"- readout — the same against the UNCLIPPED real values: largest gap {g5['max_unclipped']:.4f}, rms {g5['rms_unclipped']:.4f}")
    say(f"- readout — AFTER the tie step (the registered pipeline's scores, his repeated values applied; R was measured on his already-tied scores, so a few-level "
        f"column's correlations are attenuated a second time here — a disclosed consequence, not de-attenuated): largest gap {g5post['max']:.4f}, rms {g5post['rms']:.4f}; "
        f"against the unclipped values {g5post['max_unclipped']:.4f} / {g5post['rms_unclipped']:.4f}")
    say("- readout — the hold x exit look-back pairs (the masks restrict their range twice): column, shared real rows, R, made-up before / after the tie step")
    post_hl = {c: m for c, _s, _r, m in g5post["hold_lookback"]}
    table(say, ["exit look-back", "shared rows", "R", "made-up (latent through the map)", "made-up (after the tie step)"],
          [(c, s, f"{r:.3f}", f"{m:.3f}", f"{post_hl.get(c, float('nan')):.3f}") for c, s, r, m in g5["hold_lookback"]] or [("(none sharing >= 300 rows)", "", "", "", "")])
    say("- readout — the twelve largest gaps of the claim's comparison (R vs the latent through the map; distinct values per column = how tied it is)")
    table(say, ["column a", "column b", "shared", "R", "made-up", "gap", "distinct a", "distinct b"], [(a_, b_, s, f"{r:.3f}", f"{m:.3f}", f"{g:.4f}", da, db) for a_, b_, s, r, m, g, da, db in g5["worst"]])
    say("- readout — the twelve largest gaps AFTER the tie step (where the few-level columns sit)")
    table(say, ["column a", "column b", "shared", "R", "made-up", "gap", "distinct a", "distinct b"], [(a_, b_, s, f"{r:.3f}", f"{m:.3f}", f"{g:.4f}", da, db) for a_, b_, s, r, m, g, da, db in g5post["worst"]])
    say(f"- (c) whitened components at 90% on the {len(m_n1)} N1 sets: min {min(m_n1)}, median {statistics.median(m_n1):g}, max {max(m_n1)} (his: 18; line {C5C_RANGE[0]}-{C5C_RANGE[1]})")
    say(f"- readout — the whitened 2-means index: N1 mean {np.mean(idx_n1):.4f} (sd {np.std(idx_n1):.4f}), N2 mean {np.mean(idx_n2):.4f} (sd {np.std(idx_n2):.4f})"
        + (" — the bend made the null HARDER (a lower index)" if np.mean(idx_n2) < np.mean(idx_n1) else " — the bend did not lower the index"))

    # ---- plumbing: two sets per world through every method; the gap-free arm on the first set of N1 / N2 / target; C7 ----
    say(f"\n## Plumbing and C7 — {DRY_PLUMB} sets per world through every method (75 columns); the gap-free arm on the first set of N1, N2 and the target")
    timing = collections.defaultdict(list)
    plumb_rows = []
    plumb_cells = {"N1": ("N1", "plain"), "N2": ("N2", "curved"), "curve": ("curve", f"B1_d{TARGET_DELTA:.1f}"), "small": ("small", f"B1_d{SMALL_DELTA:.1f}"),
                   "three": ("three", f"B1B3_d{TARGET_DELTA:.1f}")}
    t0 = time.time()
    for world in WORLDS:
        w, cell = plumb_cells[world]
        spec = spec_of[(w, cell)]
        for i in range(DRY_PLUMB):
            colsets = ("registered", "pattern_free") if (i == 0 and in_gap_free_arm(w, spec)) else ("registered",)
            res = run_set(ctx, w, cell, i, spec, colsets, METHODS)
            for (colset, name), s in res["timing"].items():
                timing[(world, colset, name)].append(s)
            for r in res["rows"]:
                plumb_rows.append((world, cell, i, r["columns"], r["method"], r["k"], "" if r["ari"] is None else f"{r['ari']:.2f}",
                                   "" if r["oracle_ari"] is None else f"{r['oracle_ari']:.2f}", r["m"], f"{r['seconds']:.1f}", r["detail"][:60]))
    table(say, ["world", "cell", "i", "columns", "method", "k", "ARI vs plant", "oracle ARI", "components", "seconds", "detail (truncated)"], plumb_rows)
    say(f"- {time.time() - t0:.1f}s")
    say("### C7 — per-set seconds by world and method (mean of the plumbing sets), and the projection on 10 cores (R88)")
    trow = []
    cpu = collections.defaultdict(float)
    n_by_world = collections.Counter()
    n_gap = collections.Counter()
    for world, cell, n, spec in cells(ctx.n):
        n_by_world[world] += n
        if in_gap_free_arm(world, spec):
            n_gap[world] += n
    for world in WORLDS:
        for colset in COLSETS:
            if colset == "pattern_free" and not n_gap[world]:
                continue
            per = {name: float(np.mean(timing[(world, colset, name)])) for name in METHODS if timing[(world, colset, name)]}
            tot = sum(per.values())
            n_sets = n_by_world[world] if colset == "registered" else n_gap[world]
            for name, s in per.items():
                cpu[name] += s * n_sets
            trow.append((world, colset, n_sets) + tuple(f"{per.get(nm, float('nan')):.1f}" for nm in METHODS) + (f"{tot:.1f}", f"{tot * n_sets / 3600:.2f}"))
    table(say, ["world", "columns", "sets"] + list(METHODS) + ["per set", "CPU-hours"], trow)
    per_set_max = max(float(np.mean(timing[("curve", "registered", nm)])) for nm in METHODS if timing[("curve", "registered", nm)])
    fresh_cpu = (FRESH_N1 + 3 * FRESH_TARGET_PER_BLOCK) * per_set_max
    total_cpu = sum(cpu.values()) + fresh_cpu
    say(f"- CPU-hours by method: " + ", ".join(f"{nm} {cpu[nm] / 3600:.2f}" for nm in METHODS) + f"; the fresh sets (400 at the slowest method's {per_set_max:.1f}s) {fresh_cpu / 3600:.2f}")
    say(f"- C7: total {total_cpu / 3600:.1f} CPU-hours -> projected wall time on {N_CORES} cores {total_cpu / 3600 / N_CORES:.1f} hours (the run runs in full whatever it is)")

    # ---- claims ----
    say("\n## Claims")
    claims("C5a — the clipping changes no pair sharing >= 300 real rows by more than 0.05 (largest change)", True, clip300 <= CLIP_LINE)
    claims(f"C5b — the generator samples R: largest gap <= {C5B_MAX} and rms <= {C5B_RMS} on the well-supported pairs, the pooled latent through the rank map "
           f"over {len(pre_tie_n1)} N1 sets (before the tie step, Re-registration 1 item 1)", (True, True), (g5["max"] <= C5B_MAX, g5["rms"] <= C5B_RMS))
    claims(f"C5c — whitened components at 90% on the N1 sets within {C5C_RANGE[0]}-{C5C_RANGE[1]} (min, max)", (True, True), (min(m_n1) >= C5C_RANGE[0], max(m_n1) <= C5C_RANGE[1]))
    for b in BLOCK_NAMES:
        claims(f"C6 — the oracle hits at the target on block {b} in at least 95% of {DRY_C6_SETS} latent sets", True, c6[b][0] / c6[b][1] >= C6_LINE)
    claims("C2 (a) — (cell, group, block column) triples whose latent AUC sits below Phi(Delta_B/sqrt2) - 0.02", 0, c2_fail)
    claims("C2 (b) — (set, column) pairs where the handed value is not non-decreasing in the latent value", 0, mono_all - mono_ok)
    claims(f"C3 — sets whose blank mask is not his 658 masks or whose hold x gap Spearman differs from the real {ctx.hold_gap_spearman:.3f}", 0, c3_fail)
    claims("the shape file holds exactly §4.1's keys", sorted(SHAPE_KEYS), sorted(d))
    claims("the plant counts at the registered n = 658 are §4.4's 197 / 99 / 329-197-132 (R93)", (N_CURVE_ROWS, N_SMALL_ROWS, THREE_ROWS),
           (plant_counts(N_PRIMARY_FIT)["curve"], plant_counts(N_PRIMARY_FIT)["small"], plant_counts(N_PRIMARY_FIT)["three"]))
    claims("every method ran on every plumbing set", True, len(plumb_rows) > 0 and all(len(timing[(w, "registered", nm)]) == DRY_PLUMB for w in WORLDS for nm in METHODS))
    say("")
    say(claims.result())
    if any(not r[3] for r in claims.rows):
        say("- a MISMATCH above (C2 / C3 / C5 / C6 or the plumbing) refuses --power (R94): the finding goes to the main loop; a fix is a disclosed re-registration below the marker")
    say("DRY RUN COMPLETE")
    say.write(P06B["dry"])
    return 0


# ---- the power run (multiprocessing, per-set seeds) --------------------------------------------------------------------------------------
_CTX = None


def _init_worker(npz: str) -> None:
    global _CTX
    seal_real_loaders()
    _CTX = ShapeContext(load_shape(npz))


def _work_check(task: tuple) -> dict:
    world, cell, i, spec = task
    st = make_set(_CTX, world, cell, i, spec, through=5)
    return {"world": world, "cell": cell, "i": i, "c2": check_c2(_CTX, st, spec), "c3": check_c3(_CTX, st)}


def _work_run(task: tuple) -> dict:
    world, cell, i, spec, colsets, methods, fresh = task
    res = run_set(_CTX, world, cell, i, spec, tuple(colsets), tuple(methods), fresh)
    return {"world": world, "cell": cell, "i": i, "rows": res["rows"], "index_w": res["index_w"], "m_w": res["m_w"], "m_pa": res.get("m_pa")}


def _pool_map(fn, tasks: list, say, label: str) -> list:
    out = []
    t0 = time.time()
    mp = multiprocessing.get_context("spawn")
    with mp.Pool(N_CORES, initializer=_init_worker, initargs=(SHAPE_NPZ,)) as pool:
        for k, res in enumerate(pool.imap_unordered(fn, tasks, chunksize=1), 1):
            out.append(res)
            if k % 50 == 0 or k == len(tasks):
                print(f"  [{label}] {k}/{len(tasks)} in {(time.time() - t0) / 60:.1f} min", file=sys.stderr, flush=True)
    say(f"- {label}: {len(tasks)} tasks on {N_CORES} processes in {(time.time() - t0) / 60:.1f} minutes")
    return out


def write_tsv(rows: list, cols: list, path: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    pd.DataFrame(rows, columns=cols).to_csv(path + ".partial", sep="\t", index=False)
    os.replace(path + ".partial", path)


def _cell_label(c) -> str:
    if c in ("N1", "N2"):
        return c
    if c[0] == "curve":
        return f"curve {c[2]} Delta {c[1]:.1f} (sep {sep_of(c[1]):.2f})"
    if c[0] == "small":
        return f"small (15%) {c[1]} Delta {SMALL_DELTA:.1f}"
    return "three (329 / 197 / 132) B1 + B3 at Delta 1.5"


def print_power_tables(say, tabs: dict, orc: dict, colset: str) -> None:
    say(f"\n### false alarms — {colset} columns (k >= 2 on a null set; lines: N1 <= {FA_LINES['N1']} of 300, N2 <= {FA_LINES['N2']} of 300)")
    rows = []
    for name in METHODS:
        t = tabs.get((colset, name), {})
        n1, n2 = t.get("N1", (0, 0)), t.get("N2", (0, 0))
        rows.append((name, rate_str(*n1), "yes" if n1[1] and n1[0] <= FA_LINES["N1"] else "no", rate_str(*n2), "yes" if n2[1] and n2[0] <= FA_LINES["N2"] else "no"))
    table(say, ["method", "N1 plain", "passes", "N2 curved", "passes"], rows)
    cell_list = [("curve", d_, b) for d_ in DELTAS for b in BLOCK_NAMES] + [("small", b) for b in BLOCK_NAMES] + [("three",)]
    say(f"\n### power — {colset} columns (a hit = the planted k AND adjusted Rand >= {HIT_ARI}; the oracle beside, which no method can beat)")
    rows = []
    for c in cell_list:
        o = orc.get(c)
        if not any(c in tabs.get((colset, nm), {}) for nm in METHODS):
            continue
        row = [_cell_label(c)]
        for name in METHODS:
            v = tabs.get((colset, name), {}).get(c)
            row.append(rate_str(*v) if v else "—")
        row.append(f"{rate_str(o[0], o[1])}, ARI {o[2]:.2f}" if o else "—")
        rows.append(tuple(row))
    for d_ in DELTAS:
        cs = [("curve", d_, b) for b in BLOCK_NAMES]
        if not any(c in tabs.get((colset, nm), {}) for nm in METHODS for c in cs):
            continue
        row = [f"curve pooled Delta {d_:.1f}" + (" = THE TARGET" if d_ == TARGET_DELTA else "")]
        for name in METHODS:
            x, n = pooled(tabs.get((colset, name), {}), cs)
            row.append(rate_str(x, n) if n else "—")
        po = [orc[c] for c in cs if c in orc]
        row.append(f"{rate_str(sum(p[0] for p in po), sum(p[1] for p in po))}" if po else "—")
        rows.append(tuple(row))
    table(say, ["cell"] + list(METHODS) + ["oracle"], rows)


def stage_power(a, say) -> int:
    rc = _header(say, "POWER RUN (the one run; made-up sets only)", P06B["refused"])
    if rc:
        return rc
    problems = power_gate()
    if problems:
        for pr in problems:
            say("REFUSED: " + pr)
        say.write(P06B["refused"])
        return 3
    say("- power gates: both dry runs complete with 0 MISMATCH by the modules on disk; every pin below the 7b doc's marker; the ledger verifies; "
        "no output and no step7b_power ledger row")
    seal_real_loaders()
    d = load_shape()
    ctx = ShapeContext(d)
    say(f"- the shape file ({C.sha(SHAPE_NPZ)[:16]}); n = {ctx.n}, {ctx.p} columns; {N_CORES} processes, per-set seeds (the order of tasks changes nothing)")
    if ctx.n != N_PRIMARY_FIT:                                                            # R100: a claim that can be read before the run is read before it
        say(f"REFUSED: the shape file's n is {ctx.n}, not the registered {N_PRIMARY_FIT} (§3; its plant counts would not be §4.4's)")
        say.write(P06B["refused"])
        return 4
    all_cells = cells(ctx.n)
    say(f"- sets: " + ", ".join(f"{w} {c} {n}" for w, c, n, _s in all_cells) + f" = {sum(n for _w, _c, n, _s in all_cells)}")
    claims = Claims(say)

    # ---- pass 1: C2 / C3 on every set, before any method is scored ----
    say("\n## C2 / C3 on every set (steps 1-5; no method runs until these hold)")
    tasks = [(w, c, i, s) for w, c, n, s in all_cells for i in range(n)]
    checks = _pool_map(_work_check, tasks, say, "C2/C3")
    aucs = collections.defaultdict(list)
    mono_ok = mono_all = c3_fail = 0
    for r in checks:
        for key, v in r["c2"]["auc"].items():
            aucs[(r["world"], r["cell"]) + key].append(v)
        mono_ok += r["c2"]["monotone_ok"]
        mono_all += r["c2"]["columns"]
        c3_fail += int(not (r["c3"]["blank_ok"] and r["c3"]["spearman_ok"]))
    c2_rows, c2_fail = [], 0
    for (world, cell, g, col), vals in sorted(aucs.items()):
        al, line, af = float(np.mean([v[0] for v in vals])), vals[0][1], float(np.mean([v[2] for v in vals]))
        ok = al >= line
        c2_fail += int(not ok)
        c2_rows.append((world, cell, g, col, len(vals), f"{al:.3f}", f"{line:.3f}", "OK" if ok else "BELOW", f"{af:.3f}"))
    table(say, ["world", "cell", "group", "block column", "sets", "AUC (latent)", "line", "verdict", "final AUC"], c2_rows)
    say(f"- (b) monotone: {mono_ok} of {mono_all} (set, column) pairs; C3 failing sets: {c3_fail} of {len(checks)}")
    claims("C2 (a) — (cell, group, block column) triples below the line", 0, c2_fail)
    claims("C2 (b) — (set, column) pairs not monotone", 0, mono_all - mono_ok)
    claims("C3 — sets failing the mask / hold-gap check", 0, c3_fail)
    if c2_fail or (mono_all - mono_ok) or c3_fail:
        say("")
        say(claims.result())
        say("STOPPED: a MISMATCH on C2 / C3 — no method is scored; the finding goes to the main loop (a fix is a disclosed re-registration below the marker)")
        say.write(P06B["refused"])
        return 4

    # ---- pass 2: every method on every set (and the gap-free arm) ----
    say("\n## The methods on every set")
    tasks = [(w, c, i, s, COLSETS if in_gap_free_arm(w, s) else ("registered",), METHODS, False) for w, c, n, s in all_cells for i in range(n)]
    results = _pool_map(_work_run, tasks, say, "methods")
    rows = [r for res in results for r in res["rows"]]
    idx_w = {"N1": [], "N2": []}
    m_w, m_pa = [], []
    for res in results:
        if res["world"] in idx_w and res["index_w"] is not None:
            idx_w[res["world"]].append(res["index_w"])
        if res["m_w"] is not None:
            m_w.append(res["m_w"])
        if res.get("m_pa") is not None:
            m_pa.append(res["m_pa"])
    tabs = tabulate(rows)
    orc = oracle_table(rows)
    say(f"- whitened components at 90% over the sets: min {min(m_w)}, median {statistics.median(m_w):g}, max {max(m_w)}; parallel analysis keeps min {min(m_pa)}, median {statistics.median(m_pa):g}, max {max(m_pa)}")
    say(f"- the whitened 2-means index: N1 mean {np.mean(idx_w['N1']):.4f}, N2 mean {np.mean(idx_w['N2']):.4f}" + (" — the bend made the null harder" if np.mean(idx_w["N2"]) < np.mean(idx_w["N1"]) else ""))
    say("\n## The tables (every rate with its 95% interval, R85)")
    for colset in COLSETS:
        print_power_tables(say, tabs, orc, colset)

    # ---- C1, qualification, selection, fallbacks ----
    dec = decide(tabs)
    say("\n## C1 — the premise: M0 (the registered rule) at the target")
    say(f"- M0 target power: {rate_str(*dec['m0_target'])} (the line: under {TARGET_POOLED_LINE} of 300)")
    say("\n## Qualification (§6): N1 <= 15 of 300, N2 <= 30 of 300, target >= 240 of 300 pooled AND >= 70 of 100 on each block")
    for colset in COLSETS:
        q = dec["qual"][colset]
        say(f"### {colset} columns" + ("" if colset == "registered" else " — the gap-free arm (a readout; the selection repeats here only under Fallback 1)"))
        table(say, ["method", "N1", "N2", "target pooled", "B1", "B2", "B3", "qualifies"],
              [(nm, f"{q[nm]['N1'][0]} {'ok' if q[nm]['N1_ok'] else 'FAIL'}", f"{q[nm]['N2'][0]} {'ok' if q[nm]['N2_ok'] else 'FAIL'}",
                f"{q[nm]['target'][0]} of {q[nm]['target'][1]} {'ok' if q[nm]['target_ok'] else 'FAIL'}") + tuple(f"{q[nm]['per_block'][b][0]} of {q[nm]['per_block'][b][1]}" for b in BLOCK_NAMES)
               + ("YES" if q[nm]["qualifies"] else "no",) for nm in ELIGIBLE])
    say("\n## Selection")
    if not dec["c1_ok"]:
        say("- C1 MISMATCH: M0 reaches the target — B's premise is gone; the registered method could see such a group and its real null stands: ONE STYLE, WITH POWER (reported as the result, not a stop)")
    else:
        say(f"- Fallback 1 (no method qualifies on the 75 columns — Re-registration 1 item 4): "
            f"{'FIRES — the selection repeats on the gap-free arm (56 columns) with the same lines and order' if dec['fallback1'] else 'does not fire'}")
        say(f"- carried: {dec['carried']} on {dec['columns']}" if dec["carried"] else
            "- carried: NONE on either column set -> Fallback 2: the primary is described as one population on its registered columns, NO STYLE WE COULD SHOW WE WOULD SEE")

    # ---- the fresh estimate ----
    fresh_rows = []
    if dec["carried"]:
        say(f"\n## The fresh estimate — {dec['carried']} on {FRESH_N1} fresh N1 sets and {FRESH_TARGET_PER_BLOCK} fresh target sets per block ({dec['columns']} columns)")
        spec_n1 = next(s for w, c, _n, s in all_cells if w == "N1")
        tasks = [("N1", "plain", i, spec_n1, (dec["columns"],), (dec["carried"],), True) for i in range(FRESH_N1)]
        for w, c, _n, s in target_cells(ctx.n):
            tasks += [(w, c, i, s, (dec["columns"],), (dec["carried"],), True) for i in range(FRESH_TARGET_PER_BLOCK)]
        fres = _pool_map(_work_run, tasks, say, "fresh")
        fresh_rows = [r for res in fres for r in res["rows"]]
        fa = sum(1 for r in fresh_rows if r["world"] == "N1" and r["false_alarm"])
        n_fa = sum(1 for r in fresh_rows if r["world"] == "N1")
        hits = {b: (sum(1 for r in fresh_rows if r["world"] == "curve" and r["block"] == b and r["hit"]), sum(1 for r in fresh_rows if r["world"] == "curve" and r["block"] == b)) for b in BLOCK_NAMES}
        hp = (sum(v[0] for v in hits.values()), sum(v[1] for v in hits.values()))
        say(f"- fresh false alarms (N1): {rate_str(fa, n_fa)}; fresh target power pooled: {rate_str(*hp)}; per block: " + ", ".join(f"{b} {rate_str(*hits[b])}" for b in BLOCK_NAMES))
        say("- these rates — free of the best-of-six selection — are the ones the report quotes; they do not re-qualify")
        dec["fresh"] = {"fa": (fa, n_fa), "target": hp, "blocks": hits}

    # ---- the size line ----
    sl = size_line(tabs, dec["size_source"])
    say(f"\n## The size line (source: {dec['size_source'][0]} on {dec['size_source'][1]} — {dec['size_source_why']})")
    table(say, ["Delta-equivalent", "pooled power", ">= 80%"], [(f"{d_:.1f}", rate_str(x, n), "yes" if x / n >= 0.8 else "no") for d_, (x, n) in sl["curve"].items()])
    say(f"- {sl['text']}")

    # ---- claims, outputs ----
    say("\n## Claims")
    claims("the shape file's n is the registered 658 (its plant counts are §4.4's, R93)", N_PRIMARY_FIT, ctx.n)
    claims("C1 — M0's target power below 80% (under 240 of 300)", True, dec["c1_ok"])
    claims("C2 (a) — triples below the line", 0, c2_fail)
    claims("C2 (b) — pairs not monotone", 0, mono_all - mono_ok)
    claims("C3 — sets failing", 0, c3_fail)
    claims("every set carries every method on its column sets (rows)", sum((2 if in_gap_free_arm(w, s) else 1) * len(METHODS) * n for w, c, n, s in all_cells), len(rows))
    say("")
    say(claims.result())
    bad = [r[0] for r in claims.rows if not r[3] and not r[0].startswith("C1 ")]
    if bad:                                                                               # R100: C1 is the ONLY claim whose MISMATCH is an outcome (§6)
        say("POWER RUN STOPPED: a MISMATCH other than C1 (" + "; ".join(bad) + ") — no POWER COMPLETE, no output written; the finding goes to the main loop")
        say.write(P06B["refused"])
        return 4
    write_tsv(rows + fresh_rows, TSV_COLS, POWER_TSV)
    say("\n## Outputs")
    say(f"- step7b_power.tsv: {POWER_TSV} ({C.sha(POWER_TSV)[:16]}), {len(rows) + len(fresh_rows)} rows")
    say(f"POWER COMPLETE: {dec['outcome']}")
    say.write(P06B["run"])
    C.ledger_append(STAGE_B + "dry_run", P06B["dry"])
    C.ledger_append(STAGE_B + "power_printout", P06B["run"])
    C.ledger_append(STAGE_B + "power", POWER_TSV)
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--shape", action="store_true")
    g.add_argument("--dry-run", action="store_true")
    g.add_argument("--print-pins", action="store_true")
    g.add_argument("--power", action="store_true")
    a = ap.parse_args(argv)
    if a.print_pins:
        lines = [f"{k}\t{v}" for k, v in pins_b(include_outputs=True).items()]
        print("\n".join(lines))
        with open(P06B["pins"], "w", encoding="utf-8") as fh:
            fh.write("\n".join(lines) + "\n")
        print(f"(written to {P06B['pins']})")
        return 0
    say = Say()
    if a.shape:
        return stage_shape(a, say)
    if a.dry_run:
        return stage_dry_run(a, say)
    return stage_power(a, say)


if __name__ == "__main__":
    sys.exit(main())
