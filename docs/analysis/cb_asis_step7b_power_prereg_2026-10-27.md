# #711 — step 7b: a stronger way to sort his trades, proven on made-up trades first — registration (2026-10-27)

**Status: REGISTERED and FROZEN 2026-10-27 (the freeze record below the marker); NOT RUN.** His ruling (2026-10-27, on the step-7 fork): *"B, that was the original ask, no
preconceptions, just look at the trades."* It answers the fork the step-7 build note (`06_groups.py`, BUILD NOTE) put to him after the
registered grouping read no stable grouping on the confident trades. The frozen step-7 consequence row for that reading (§5: *"described as
one population; his call whether to run on + ONE-STREAM (more trades) or stop"*) offered two paths; his B is a third — re-register the
grouping method, proven first — and this document is that re-registration. It rests on, and changes nothing above the marker of,
`cb_asis_step7_grouping_prereg_2026-10-27.md` (frozen, `doc_body` b16d81fe) and `cb_asis_reconstruction_prereg_2026-10-26.md` (frozen,
`doc_body` 2b330f04).

**Guards (unchanged from step 7):** no paid model call, no network, no production server, nothing dated after 2024-12-31 (the 2025-26 data
is sealed for #710), none of the seven outcome folders opened, nothing imported from the rule folders, no trade outcome read, computed or
printed (both name lists scanned against every 7b module). Nothing here changes or proposes to change a strategy, entry, stop, exit, size,
safeguard or live trade state (THE LINE).

## 0. In plain words

- **The problem:** the registered sorting method found no groups in his 658 confident trades — but on made-up trades shaped like his it
  also misses groups we planted on purpose, so its "no groups" cannot tell *one style* from *cannot see*.
- **What 7b does:** build made-up trade sets shaped like his (same number of trades, same measures, the same way the measures move together,
  the same gaps and repeated values in the data) — some with NO hidden group, some with one planted — and score seven sorting methods.
- **The pass mark, set now:** a method must (1) almost never invent groups where there are none (about 5 false alarms in 100 on plain
  made-up sets, 10 in 100 on sets where the measures curve together without any real group) and (2) find a hidden group of **30% of trades
  that stands apart as clearly as one sitting 1.5 within-group spreads away on three separate chart measures** (about 1.2 times each
  measure's spread across all his trades) at least 80 times in 100.
- **Then:** the best method that passes runs ONCE on his real trades. Two honest "one style" answers are kept apart: **one style, with
  power** (a method that would have seen such a group saw none) and **no style we could show we would see** (no method passed; the trades
  are described as one population with the size of group that would have been invisible).
- **Cost:** $0; four review cards (two done), one build card, at most one fix card; the made-up run is a few hours of local computing;
  ~10 minutes of his time for the report (§9). **Action from him: none** — §2's departures are technical and disclosed, not his call.

## 1. Disclosures — what was already seen

1. **The registered method's result on his real trades is known:** prediction strength 0.524 at k = 2, falling to 0.151 at k = 8; no k
   reaches 0.80; 658 fitted rows; 18 whitened components at 90.7% (`06_groups_dryrun.txt`). So the choice of method is made **only on
   made-up data, by the rule in §6, written before any made-up set of §4 is generated.** No candidate method of §5 has been run on the real
   matrix, and **no stage, probe or test runs M1-M4 on it** until the §7 run (gated, §11).
2. **The earlier power evidence was ad hoc** — the step-7 build note and `tests/test_asis_groups.py::test_the_k_rule_reads_no_grouping...`
   ran after the real null was seen, on worlds whose shape was cycled (that test's docstring says so), and on a 50 / 50 split only; its line
   "whitening is not the cause" does not carry to a 30% group (the review below found whitening caps a minority group's weight). It is not a
   registered check; §6's claim C1 re-establishes the registered method's power on the §4 worlds.
3. **The real matrix shapes the made-up sets:** §4.1 lists the only four summaries taken from it. They are chart measures already read by the
   step-7 dry run; no outcome is among them. The `--shape` stage runs only after this document is frozen (§11), so no shape readout can tune
   a rule here.
4. **Two read-only reviews ran on the first draft (2026-10-27)** with synthetic toys only; their findings are §12. Their toy timings and
   toy power figures were read before this revision; no made-up set of §4 existed then.

## 2. Scope — what 7b changes, and what it does not

**7b replaces step 7's §4.2-§4.4** — how the standardized trades are reduced, grouped, and how many groups are chosen. **Departures beyond
that, each disclosed here (technical, ruled by the main loop; none touches the population, the tiers, the outcome guard or a rule):**

1. **The noise floor** (step 7 §5) refits the CARRIED method's own fit (§7.2: k-means at the primary's k for M1 / M2w / M2u — as
   registered, in that method's space; the whole split procedure for M3w / M3u; EM at the primary's k for M4) under 5 other seed keys and on
   5 bootstrap resamples.
2. **Fallback 1** (§6), if it fires, grouping on the 56 gap-free columns replaces step 7's §3.3 column set for every §5 run, per the table
   in §7.3.
3. **Step 7 §7's first expectation** ("3-5 groups at strength ≥ 0.80") is scored on the carried method's own k ("3-5 groups by its rule").
4. **Step 7's own `--run` now also waits for the power result** (§11) — a tightening of its gate, so the one-population description
   is written once, after 7b has decided which reading it is.
5. **The power claim covers the primary only** — the other §5 runs differ in n (1,187 and 1,588 registered; 347 / 330) and in score tails (up to |1026|,
   `06_groups_dryrun.txt`), and their readings carry the primary's power as a guide, not a measurement.

**Unchanged and imported, never widened:** the population and tiers (§2, `tiers.tsv`), the features (§3.3, `05_tiers.py::STEP7_FEATURES`),
the missing-value rules (§3.4), the outcome guard (§3.5), the rank-normal maps (§4.1), the minimum group size per run (§4.5 as built: 34 on
the primary, max(30, 5% of the run's registered n) elsewhere), the description (§4.6, the fixed phrase table), the runs, matching, survival
and consequence table (§5) apart from item 1, and step 7 §7's other expectations. "No preconceptions" here means the method looks at all
75 registered measures and is told nothing about setups; it does not mean adding measures until something separates.

## 3. The four questions of the standard

1. **Decision served:** whether his confident trades fall into more than one chart-visible style, with a method proven able to see one if it
   is there; and, if not, how distinct a hidden style would have to be to be seen. Nothing live; no branch of the sealed test.
2. **What would change it:** C1 (the registered method already had the power — its real null stands: one style, with power); no method
   qualifying (no style we could show we would see, with the size line); a qualifying method reading groups on his real trades (step 7's §5
   comparisons then run under it).
3. **Population:** step 7's primary — HIGH + MEDIUM, 677 positions, 658 fitted after §3.4.
4. **Limits:** §10.

## 4. The made-up trade sets — shaped like his

### 4.1 The only four summaries taken from the real matrix (the `--shape` stage; pinned by hash)

Computed on the primary's 658 fitted rows through `06_groups.py`'s own loaders and maps, written to `asis_1026/step7b_shape.npz`, which
holds exactly these and nothing else (a claim and a test):

- **R — his correlations.** The 75 × 75 correlation of the rank-normal scores, each pair over the rows where BOTH cells are non-blank. A
  pair sharing fewer than 30 such rows, or with zero spread on either side, is set to 0 (the count printed — four exit look-backs are
  defined on about 3-19 rows). Then **eigenvalue clipping**: eigenvalues below 1e-3 raised to 1e-3, the matrix rescaled to a unit diagonal.
  Printed: the largest change the clipping makes on pairs sharing at least 300 rows (claim C5a: at most 0.05) and on all pairs.
  The unclipped matrix and each pair's shared-row count are kept beside R for C5.
- **The blank masks** — for each of the 658 rows, which of its 75 cells are blank (structural or data, §3.4), with that row's
  `hold_sessions_max` rank (ties broken by `rng_for("step7b_hold_ties")`).
- **The repeated values** — for each column, the sizes of its runs of equal values among its non-blank cells, in sorted order (counts only,
  no values): the integer counts (`sessions_since_hi_N`, `hold_sessions_max`), the daily-only minute, zero distances.
- **n = 658** and the 75 column names in `run_columns("primary")` order.

No row's values leave the stage. The `--power` stage reads only this file (a test makes every other real-data loader raise inside it).

### 4.2 One made-up set (seed `rng_for("step7b_set_<world>_<cell>_<i>")`), in this order

1. **Draw** 658 latent rows from N(0, R).
2. **Bend** (N2 only, §4.3).
3. **Plant** (planted worlds only, §4.4): an EXACT count of rows, chosen at random, take the coherent shift. The planted labels are kept for
   scoring only; no method sees them.
4. **Gaps like his:** rank the rows by their latent `hold_sessions_max` from step 1 (BEFORE any bend or plant, in every world); the row at
   hold rank r takes the blank mask of the real row at hold rank r. So the gaps follow the hold as in his data (a one-session hold has no
   exit look-backs) and no plant or bend moves a mask.
5. **Repeated values like his:** on each column, among its non-blank cells, the rows are ordered by their latent value and handed his run
   sizes in that order — rows falling in one of his runs take one shared value, so the column's ties match his (a monotone step: it never
   changes an order, only merges neighbours).
6. **The same pipeline as his real trades:** the rank-normal maps fitted on the made-up set itself (step 7 §4.1), blanks zero-filled, then
   the method under test.

After step 6, the structure a method can find in a null set is his correlation, his gaps (the zero-filled cells: 7,991 structural blank
cells of 49,350; 128 of the 677 registered rows have no exit look-back at all) and his repeated values. A method that "finds groups" in the
gaps or ties alone fails here, not on his real trades.

### 4.3 The worlds with NO hidden group (the false-alarm test)

- **N1, plain:** §4.2 with no bend and no plant — one population with his correlations, gaps and repeated values. 300 sets.
- **N2, curved:** after step 1, the nine block columns of §4.4 bend with one hidden factor: z ← z + 1.0 · (f² − 1) / √2, where f is the
  set's latent score on the first eigenvector of R, standardized. Still one population — a curved cloud with no subgroup — the continuum
  hazard step 7's §9 names. 300 sets. Printed beside: N2's mean whitened 2-means index against N1's, so it is visible whether the bend made
  the null harder (a readout; the N2 line applies either way).

### 4.4 The worlds WITH a hidden group (the power test) — named by chart measure, never by setup

Three blocks of three primary columns each — every column in the primary run, none an `our_length` column, none able to move a mask:

| block | in chart words | columns |
|---|---|---|
| B1 | the entry day itself: its gap, its range, its volume | `entry_gap_pct`, `entry_range_pct`, `entry_vol_day_vs_10` |
| B2 | where the entry sits after the run: near the recent high, above the average, after a climb | `entry_dist_hi_10`, `entry_dist_ma_13`, `entry_ret_20` |
| B3 | how he sells on the exit day: where in the day, what time, how wide the day | `exit_pos_in_day`, `exit_minute`, `exit_range_pct` |

**The coherent shift.** A planted row moves by δ = R[:, B] · R_BB⁻¹ · (Δ_B · 1): the block's three columns move by Δ_B each, and every other
column by what his correlations imply (a group "nearer the high" is nearer it on every length, not on one) — **except `hold_sessions_max`,
whose δ is set to 0**, so a planted row's hold stays consistent with the mask it took at step 4 (the plant is chart measures only; a method
modelling hold against the gap count cannot find planted rows through a hold the masks contradict). **The separation is fixed per
block, not the shift:** Δ_B = D / √(1ᵀ R_BB⁻¹ 1), so every block's planted group stands apart by the same distance D (the Mahalanobis
distance between the planted and other rows' latent means). D is named by its unrelated-measures equivalent: D = Δ √3 for a shift Δ on three
unrelated measures. Each block's Δ_B is printed.

| cell | share planted (exact count) | separation D (Δ-equivalent) | blocks | sets per block | role |
|---|---|---|---|---|---|
| curve | 30% (197) | 1.73, 2.60, 3.46, 5.20 (Δ 1.0, 1.5, 2.0, 3.0) | B1, B2, B3 | 100 at D 2.60, 40 otherwise | power curve; **the target = D 2.60 (300 sets)** |
| small | 15% (99) | 3.46 (Δ 2.0) | B1, B2, B3 | 40 | readout: a smaller hidden group |
| three | 329 / 197 / 132 | 2.60 (B1 on the 197, B3 on the 132) | — | 40 | readout: three groups |

**The target in his words:** *a hidden group of 30% of trades that stands apart as clearly as one sitting 1.5 within-group spreads away on
three separate chart measures* — about 1.2 times each measure's spread across all his trades (a perfect sort of 30% of trades on one measure
would be 1.66 in those units).

**Total:** 600 null sets + 660 curve + 120 small + 40 three = **1,420 sets**, every method on every set; plus §6's fresh sets for the carried
method.

## 5. The methods — a closed list, each tied to a diagnosed weakness

Settings are identical in the power run and the real run. Every method uses step 7's §4.1 maps, the minimum group size of §2, the
registered PCA to 90% of the variance of the zero-filled matrix unless stated, and seeded draws only through `rng_for` with the keys of §5.1.
**Two reductions:** *whitened* = the registered components, each scaled to unit variance; *kept-unwhitened* = M1's parallel-analysis
components, not scaled.

| | method | what it tests | settings |
|---|---|---|---|
| **M0** | the registered rule: prediction strength ≥ 0.80 on random halves, the largest k in 2..8, whitened | the reference (its real result is seen; never eligible) | the registered 50 halves, 20 starts |
| **M1** | the same prediction strength on the kept-unwhitened components | "whitening plus noise dimensions", with the half-sample rule kept | parallel analysis: keep component j while its eigenvalue (covariance of the zero-filled Z — the matrix the registered PCA decomposes) exceeds the 95th percentile of the j-th eigenvalue over 50 column-wise permutations of that same Z (each column's zeros kept); at least 2 components kept; fitted once per set on all rows, the halves reuse it; 50 halves, 20 starts |
| **M2w** | bootstrap stability on all rows, whitened: for each k in 2..8, the full-data k-means fit against 30 bootstrap refits (k-means only, on the full-data components), every row assigned to each refit's centroids; k = the largest k whose mean adjusted Rand index is ≥ 0.80 with every full-data group ≥ the minimum; none → 1 | "the half-sample rule" | 10 starts per fit |
| **M2u** | M2w on the kept-unwhitened components | both diagnoses together | as M2w |
| **M3w** | a test of a split against one population, whitened: the 2-means within / total sum of squares (best of 10 starts) against 1,000 null draws of N(0, I_m) at the same n, **each draw re-whitened by its own PCA (all m kept)** so it matches the data's exact unit spectrum (cached per (n, m)); p = (1 + #null ≤ observed) / 1,001; split when p < 0.01 and both groups ≥ the minimum | "any split beyond one population" | recursion: each group's rows of the zero-filled 75-column Z re-reduced (PCA to 90%, whitened) and tested at half the level (0.005, then 0.0025), at most three levels (≤ 8 groups); the final labels are the leaves |
| **M3u** | M3w on the kept-unwhitened components (SigClust proper): each null draw is a cached whitened draw rescaled by the square roots of the data's own kept eigenvalues, so it carries the data's exact spectrum | both diagnoses together | as M3w; children re-reduced by parallel analysis, unwhitened |
| **M4** | a Gaussian mixture with diagonal spreads on the whitened components, k = 1..8 by the lowest BIC with p = 2km + k − 1 parameters; a k whose fit has a group under the minimum (hard assignment counts) is skipped, not merged | the obvious stronger method — kept so its result is on record either way | 5 EM starts seeded from k-means++, equal weights, initial spreads = within-cluster variances of the seeding; variance floor 1e-3; stop at a log-likelihood change < 1e-6 or 300 iterations; labels = posterior argmax |

### 5.1 Seed keys (registered so every number reproduces from this document)

`step7b_set_<world>_<cell>_<i>` per made-up set; `step7b_<method>_<world>_<cell>_<i>_<purpose>` inside a method (`purpose` ∈ halves,
starts, boot, null, em, perm); `step7b_null_<n>_<m>` for the cached M3 draws; `step7b_fresh_...` for §6's fresh sets;
`step7b_real_<method>_<run>_<purpose>` in the real run.

## 6. Scoring, the claims, and the one rule that picks — written before any made-up set exists

**Per set:** the method's k and its labels. On a null set, a **false alarm** = k ≥ 2. On a planted set, a **hit** = k equals the planted
number of groups (2, or 3 in "three") AND the adjusted Rand index against the planted labels is ≥ 0.5. Beside every cell, the **oracle**
is printed: the best possible sorter (the true group means and R on the latent rows), its hit share and mean adjusted Rand index — a method
cannot beat it, so a cell the oracle cannot hit says nothing about any method.

**Every rate is printed with its 95% binomial interval.**

**The claims (each printed OK / MISMATCH):**

- **C1 — the premise (in `--power`).** M0's target power below 80% (under 240 of 300). **If M0 reaches it, B's premise is gone:** the
  registered method could see the target, its real null stands, and the answer is **one style, with power**, with M0's size line —
  reported as the result, not a stop (on power alone: a method that tends to call groups and called none on his trades is only more
  telling).
- **C2 — the plant is there and survives the pipeline (every block column; in `--power` over all sets of a cell; in the dry run over 50
  latent sets per cell, since two sets would put a correct plant under the line by chance — C2 runs no method, so this costs seconds).** (a) The
  planted rows' latent values on each block column sit above the others' with a rank score (Mann-Whitney AUC) of at least Φ(Δ_B / √2) − 0.02;
  a lost or misaligned plant reads near 0.50. (b) On every column of every set, the value handed to the map is non-decreasing in the latent value
  after steps 1-3, over the non-blank cells (100%) — the step-5 ties and the masks never re-order rows. The final AUC is printed beside (ties pull it
  toward 0.50 on the count columns).
- **C3 — the gaps follow the hold (dry run and `--power`, every null set).** The made-up rows' blank masks are his 658 masks (the blank
  share equal, 8,119 of 49,350 cells), AND the Spearman correlation between the made-up latent hold and each row's count of non-blank exit
  look-backs equals the real value computed from the shape file to 3 decimals (a reversed or shuffled coupling reads otherwise).
- **C5 — the shape is his (dry run).** (a) The clipping changes no pair sharing ≥ 300 real rows by more than 0.05. (b) The generator samples R: the
  made-up sets' rank-normal correlation through the pipeline, pooled over 50 N1 sets, against R on every pair sharing ≥ 300 real rows —
  largest gap ≤ 0.03 and root-mean-square gap ≤ 0.01 (C5a already bounds R against the unclipped real values). The comparison with the
  unclipped real values, and the hold × exit look-back pairs (the masks restrict their range twice), are printed as readouts. (c) The primary's component count at 90% on the dry run's N1 sets lies within 14-22 (his: 18).
- **C6 — the target is reachable (dry run, from R alone).** At D 2.60 the oracle hits in at least 95% of 200 latent target sets per block.
  (The target is fixed by separation for this reason: with a fixed shift, a block of correlated columns could leave even the oracle below
  the hit line.)
- **C7 — the timing (dry run).** One set per world timed through every method; the projected wall time of `--power` on 10 cores is printed.
  The power run runs in full whatever it is — no cell is cut.

A MISMATCH on C2, C3, C5 or C6 stops the stage before any method is scored; the finding comes to the main loop, and any fix is a disclosed
re-registration below the marker before the run.

**Qualification:** a method of M1, M2w, M2u, M3w, M3u, M4 qualifies when ALL hold: false alarms ≤ 5% on N1 (≤ 15 of 300); ≤ 10% on N2
(≤ 30 of 300); target power ≥ 80% pooled (≥ 240 of 300) AND ≥ 70% on each block (≥ 70 of 100). **Selection:** the qualifier with the
highest pooled target power; any qualifier within 5 points of the top is resolved by the order M1, M2w, M2u, M3w, M3u, M4 (the nearest to
the registered method first). **Fresh estimate:** the carried method then runs on 100 fresh N1 sets and 100 fresh target sets per block
(keys `step7b_fresh_...`); those rates — free of the best-of-six selection — are the ones the report quotes. They do not re-qualify.

**The gap-free arm, every time (a readout):** on the N1, N2 and target sets, every method also runs on the 56 gap-free columns
(`06_groups.pattern_free_columns`: the 40 entry columns and the 16 exit-day-own columns); its table prints beside the 75-column one. B1-B3
are identical on both column sets.

**Fallback 1 — decided now, disclosed (not a fork):** if NO method passes the N1 false-alarm line on all 75 columns (the gaps fool every
method), the selection is made on the gap-free arm with the same lines and order, and the carried method groups on the 56 columns (§7.3);
the exit look-backs and the hold are then described per group, never grouped on.

**Fallback 2:** no method qualifies on either column set → the primary is described as one population (each measure's distribution, step
7's "no stable grouping" branch), labelled **no style we could show we would see**.

**The size line, in every outcome:** taken from the carried method; when none is carried, from the highest-power method among those passing
both false-alarm lines; when none passes them, from M0 with its false-alarm rate printed beside. It reads: *"this method finds a hidden group
of 30% of trades only when it stands apart as clearly as Δ* within-group spreads on three separate measures (about X of each measure's
spread across all his trades); a 15% group at Δ 2.0: Y in 100"* — Δ* the smallest Δ-equivalent of the curve with pooled power ≥ 80%, or
"more than 3.0".

## 7. The real run — once

### 7.1 Which command, in each outcome

- **A method carried:** `06_groups.py --run --method <carried> [--columns pattern_free]` — every step-7 §5 run under the carried method.
  If it reads one group on his real trades: **one style, with power**, described by distributions, with the size line.
- **C1 (one style, with power) or Fallback 2:** `06_groups.py --run` under the registered method — the one-population description step 7's
  null branch writes, plus the size line.
- Either command is refused until `06b_power.txt` ends `POWER COMPLETE` naming the outcome (§11). The report follows step 7 §6.

### 7.2 How a carried method runs inside step 7's §5 machinery

| | the shared space (mode-A runs) | assignment of a row to a group | noise-floor refit (5 seeds + 5 bootstraps) |
|---|---|---|---|
| M1 | the primary's maps and its parallel-analysis components, reused | nearest group mean | k-means at the primary's k in M1's space, as registered |
| M2w / M2u | the primary's maps and its reduction (whitened / kept-unwhitened), reused | nearest group mean | k-means at the primary's k, as registered |
| M3w / M3u | the primary's maps and its top-level reduction, reused; each child re-reduced inside it | nearest leaf mean in the top-level space | the whole split procedure re-run (other seed keys / a bootstrap resample), its leaves matched to the primary's by the Hungarian assignment on leaf means; an unmatched primary group counts every one of its trades as moved |
| M4 | the primary's maps and whitened components, reused | posterior argmax | EM at the primary's k from the other seeds / on the resample |

Group means replace `centroids` wherever step 7's comparison code reads them (mode A, CONFIRMED). Mode-B runs (with `our_length`, entry-only,
exit-only) fit their own maps and reduction as registered; for M1 / M2u / M3u the parallel analysis uses that run's own n × p matrix as its
reference.

### 7.3 Column sets under Fallback 1 (only if it fires)

| run | columns |
|---|---|
| primary and every mode-A run | the 56 gap-free columns |
| entry-only | the 40 entry columns (unchanged) |
| exit-only | the 16 exit-day-own columns |
| with `our_length` | the 56 plus the `our_length` entry columns and exit-day-own columns (no exit look-back) |

Survival on families (step 7 §5 (c)) is read on the families present.

## 8. Expectations, written now (scored at the report; a miss changes nothing by itself)

| item | expectation | if it misses |
|---|---|---|
| C1 (M0's target power) | under 30% | 30-80%: M0 weak but not blind, B proceeds; ≥ 80%: one style, with power |
| M4 (mixture by BIC) on N1 | fails the false-alarm line — the zero-filled gaps and the count columns look like groups to it | it passes: the gaps fool it less than expected |
| the whitened methods (M2w, M3w) at the target | under 50% — whitening shrinks a minority group's weight | above: the review's toy did not carry to his spectrum |
| a qualifier on all 75 columns | M3u (the significance test on the unwhitened components) qualifies; no method reaches 80% at Δ 1.0 (the oracle cannot either) | none: Fallback 1 or 2 |
| the 15% hidden group at Δ 2.0 | under 80% for every method | above: smaller styles are visible too |
| his real trades under the carried method | 2-3 groups, the clearest difference in how he sells on the exit day and how long he held rather than on the entry day — consistent with his remark that his entries look alike | one group: one style, with power |

## 9. Cost — the whole path priced up front

| item | $ | my capacity | his time |
|---|---|---|---|
| this registration + two read-only reviews before the freeze (done) | 0 | main loop + 2 Opus reviews (~440k, spent) | — |
| `06b_power.py` (shape, worlds, the seven methods, scoring, gates) + the `--method` / `--columns` switches in `06_groups.py` + tests + dry runs | 0 | 1 Fable build (~250k) + 2 Opus reviews (~200k) + ≤ 1 Fable fix (~100k) | — |
| the power run (local, background, 10 cores; about 30 CPU-hours by the review's toy timings — about 3 hours of wall time; C7 prints the real projection) | 0 | main loop | — |
| the real run + the report | 0 | main loop | ~10 min, one reading |
| **total** | **$0** | **~1M tokens of cards, ~440k already spent** | **~10 min** |

## 10. What this does not answer

- **A style that no plant resembles** — power is measured for three blocks of three measures with a coherent shift; a style living in one
  measure, or spread thinly over twenty, has its own (unmeasured) power. The curve says how finely the method sees for the planted kinds only.
- **A style smaller than 15% of trades** — not measured.
- **The other §5 runs' power** — measured on the primary's shape only (§2 item 5).
- **Whether a group is a rule** — groups are descriptions until step 8; no rule is named, matched or rejected here.
- **Everything step 7 §9 lists** (the fill price, exits without the path, a HIGH trade being a correct trade, sizes and shorts, the thin
  2022 streams) — unchanged.

## 11. Files, guards, gates, tests

**Code (under `scripts/probes/_705_asis_1026/`):**
- `06b_power.py`:
  - `--shape` (§4.1 → `asis_1026/step7b_shape.npz` + `06b_shape.txt`), refused until `doc_body_7b` is pinned below THIS document's marker.
  - `--dry-run` (two sets per world through every method for plumbing and C7's timing; 50 latent sets per cell for C2, 50 N1 sets
    through the pipeline for C5b, 200 latent target sets per block for C6; C3 on every set → `06b_power_dryrun.txt`), made-up sets only.
  - `--print-pins`.
  - `--power` (the one power run → `asis_1026/step7b_power.tsv`, one row per set, method and column set; `06b_power.txt` with C1, every
    method's false-alarm and power tables with intervals and the oracle, the gap-free arm, the selection, the fresh estimate, the size line,
    ending `POWER COMPLETE: <outcome>` where outcome ∈ {carried <method> on <columns>, one style with power (C1), no style we could show we
    would see}), refused unless the dry run completed with 0 MISMATCH and was made by the modules on disk, every pin is below THIS
    document's marker, and no output or `step7b_power` ledger row exists.
- `06_groups.py`: `--method {registered, M1, M2w, M2u, M3w, M3u, M4}` (default registered) and `--columns {registered, pattern_free}`
  (default registered), importing the methods from `06b_power.py` so the power run and the real run share one implementation. **Every stage
  of `06_groups.py` that opens the real matrix — `--dry-run` included — refuses a non-default `--method` or `--columns` until `06b_power.txt`
  ends `POWER COMPLETE` naming that method and column set, and its pin sits below this marker.** Its `--run` (default or not) is refused until
  `06b_power.txt` ends `POWER COMPLETE`, and when a `step7_groups` ledger row already exists.
- **The reference for the default path, pinned now:** `06_groups.py` at sha256 06a3f48f1046b8a91a8bbbe8e93dd30e5c62b3a46332bc7273b5984fcf68d404
  and `06_groups_dryrun.txt` at e578a7008dc871d82df04470b24a9b120de15a9d098c199608fc22d86c4366ca (both committed in 8352c78c). After the
  switches are added, `06_groups.py --dry-run` under the defaults must reproduce that printout's k-sweep block and Claims block line for line
  (excluding the header timestamp, the modules line and timing figures) — a claim of the new dry run. The untracked `06_groups_pins.txt`
  (stale) is regenerated by `--print-pins`, never pasted.
- Ledger rows `step7b_*` in `01_ledger.tsv`; a stage whose ledger row exists refuses (once means once, whatever files are deleted).

**Order:** freeze this document (`doc_body_7b` pinned) → build → `--shape` → both dry runs → `--print-pins` of both modules, the shape
file and the dry-run printouts, pasted below this marker → `--power` → its result and pins written below this marker → the real run (§7.1)
→ the report.

**Pins:** `doc_body_7b`, step 7's `doc_body` and `doc_body_steps56`, 05_tiers' pins, the reference pair above, `step7b_shape.npz`, both
modules after the build, both name lists, both dry-run printouts, then `06b_power.txt` and `step7b_power.tsv`.

**Guards:** step 7's (the seal, the forbidden folders, the identifier scan with both name lists on `06b_power.py` too, the import belt,
seeded draws only, no network, no model client) + the `--power` stage opens no real-data file but the shape file.

**Tests (`tests/test_asis_power.py`, synthetic, CI-safe):** the shape file holds only §4.1's contents (and its thin-pair rule zeroes a pair
under 30 shared rows); the gap coupling follows the latent hold rank and survives a plant (C3's Spearman reads negative on a reversed rank);
the tie step is monotone and reproduces a run-size vector; the coherent plant moves the block columns by Δ_B and the oracle hits at D 2.60;
C2 catches a misaligned plant; each method finds a strong two-way split on a toy world and reads one group on a single population run
THROUGH the pipeline; M3w's and M3u's p-values are roughly uniform on single-population sets run through the pipeline (never raw draws);
parallel analysis keeps planted components on a toy spectrum; the selection rule on hand-made score tables (a qualifier, the per-block
line, the tie order, C1's outcome, Fallback 1, Fallback 2, the size-line source); every gate refuses (no dry run, a MISMATCH, a pin above
the marker, an existing output or ledger row, `--shape` before the freeze, a non-default `--method` on `--dry-run` or `--run` without
`POWER COMPLETE`, a default `--run` before `POWER COMPLETE`); `06_groups.py` under the defaults reproduces the pinned k-sweep and Claims
blocks; the identifier scan on `06b_power.py` with both lists.

## 12. Revisions before the freeze (2026-10-27)

Two read-only Opus reviews of the first draft (statistics / calibration; fidelity / peeking), synthetic toys only.

| source | finding | change |
|---|---|---|
| stats, high | whitening caps a 30% group's weight below the best split of pure noise in 18 dimensions — every whitened method blind at the target by construction (toy: bootstrap stability 0.03 whitened vs 0.86 unwhitened) | M2u and M3u added on M1's unwhitened components; order M1, M2w, M2u, M3w, M3u, M4; §1.2 corrects the build note's "whitening is not the cause" (50 / 50 only); §8 expects M3u |
| both, high | C2's 0.7 × Δ line fails a correct pipeline (the rank map caps a 30% group's difference at 1.656) | C2 (a) a rank score on the latent columns against Φ(Δ_B/√2) − 0.02, (b) the order kept through ties and masks; judged per block column over all sets of a cell |
| both, high | M3's null draws were never whitened, so p ≈ 1 always (25 of 25 toy sets) | null draws re-whitened by their own PCA (M3w) or rescaled to the data's spectrum (M3u); 1,000 cached draws; levels 0.01 / 0.005 / 0.0025; the recursion specified; the test runs pipeline output, never raw draws |
| stats, high | single-member plants on collinear sweeps make a group no chart style has ("near the 10-day high but not the 5- or 40-day") | the coherent shift δ = R[:,B] R_BB⁻¹ Δ_B 1 |
| stats, high | ARI ≥ 0.5 is out of reach of even the best possible sorter below a separation of ~2.0 | the target fixed by separation D (Δ_B scaled per block); the oracle printed in every cell; C6 checks it is reachable |
| both, high | planting on `hold_sessions_max` also moved the masks, so B3 was partly a gap plant | B3 = exit-day-own columns only; masks follow the latent hold BEFORE bend or plant, in every world |
| stats, high | 100 / 120 sets make the lines coin flips; best-of-four inflates the carried method's numbers; the 8-hour cut never binds and was undefined | 300 / 300 null and 100 target sets per block; 95% intervals; a fresh-seed estimate for the carried method; no cut — the run runs in full |
| fidelity, high | R is not estimable for exit look-backs defined on 3-19 rows; the clipping moved well-supported pairs by 0.15-0.22 ungated; C5 compared against the repaired R | pairs under 30 shared rows set to 0; C5a (clipping ≤ 0.05 on pairs ≥ 300 rows); C5b against the unclipped real values, pooled; hold × look-back pairs printed apart |
| fidelity, high | `06_groups.py --dry-run --method M2` would print a candidate's k on his real trades before the power result | every real-data stage refuses a non-default method or column set until `POWER COMPLETE`; §1.1 says so |
| fidelity, high | "byte for byte" could not hold (timestamp, module hash, timings) and the reference was never pinned | the reference pair pinned in §11 by sha; reproduction = the k-sweep and Claims blocks line for line |
| both, medium | C4 could not fail; C3 was tautological | C4 dropped — M0 runs at the registered 50 / 20 everywhere; C3 adds the hold × gap-count Spearman |
| stats, medium | parallel analysis, M4 and M2 left open | §5 settings: covariance of the zero-filled Z vs column-wise permutations; M4's parameter count, sizes, floor, starts, stop; M2 k-means only on the full-data components |
| stats, medium | N2's bend at 0.5 changed nothing in a toy; its order was open | coefficient 1.0, applied after the latent draw and before masks; N1 vs N2 index printed |
| both, medium / low | the count columns and daily-only minute keep repeated values that bell-shaped made-up columns lack (two near-binary columns made M4 split a toy null) | the shape file carries each column's run sizes; step 5 of §4.2 gives the made-up columns his repeated values |
| stats, medium | the gap-free arm ran only if every method failed | it runs every time as a readout; Fallback 1 unchanged |
| both, medium | the size line could come from a method that invents groups; "one style" named two opposite states | the size line's source ordered; two labels: one style, with power / no style we could show we would see; C1 reads on power alone |
| fidelity, medium | how a carried method lives in §5's machinery was open; the scope line overclaimed | §7.2 per-method table; §2 lists the departures; the minimum size stays per run; the power claim limited to the primary |
| fidelity, medium | `--shape` ungated; the default `--run` could write before the power result; "once" rested on deleted files | `--shape` after the freeze; every `--run` after `POWER COMPLETE`; ledger rows make "once" hold; §7.1 names the command per outcome |
| both, medium / low | the plain "1.5 standard deviations" overstated the visible difference by about a quarter; 19% was of 677, not 658; review cards miscounted | the within-group and all-trades units both stated; "128 of the 677"; four review cards; "sets where the measures curve together" in §0 |
| stats, low | the share was open (exact or random) and the seed keys unregistered | exact counts (197; 99; 329 / 197 / 132); §5.1 keys |
| advisor, final pass | C2(a) over the dry run's two sets and C5b against the unclipped values would MISMATCH a correct pipeline by chance | C2 in the dry run on 50 latent sets per cell; C5b tests the generator against R (0.03 / 0.01), the unclipped comparison a readout |
| advisor, final pass | the coherent shift moved the hold of planted rows while their masks stayed pre-plant | δ on `hold_sessions_max` set to 0 |
| advisor, final pass | parallel analysis could keep one component; step 7's `--run` gate tightened silently | at least 2 kept; §2 item 4 names the gate change |

<!-- FREEZE -->
## Freeze record

The main loop freezes this document (`doc_body_7b` pinned below), then the build; the `--shape` output, the modules and the dry runs are
pinned below before `--power` runs; the power result is written below before the real run. Nothing above the marker is edited after the
freeze; any edit changes `doc_body_7b` and every stage refuses.

### FREEZE 2026-10-27 (his "B"; after two read-only reviews and the advisor's final pass — §12)

Frozen before any made-up set of §4 exists, before `--shape` has run, and before any method of §5 has touched the real matrix.

- doc_body_7b: cf2ec533f2d34a2667c027865c50a692bbaa440ba6dc2727752957c00c5e2d4b
- doc_body (step 7): b16d81fea023322db3e77f4cc99c24974d3591182f98ab7a4c7d0fdeaa52b5cb
- doc_body_steps56: 2b330f044c3f59da643f248ef97723dd80534b262458a766979f5fd22d748db0
- reference 06_groups.py (8352c78c): 06a3f48f1046b8a91a8bbbe8e93dd30e5c62b3a46332bc7273b5984fcf68d404
- reference 06_groups_dryrun.txt (8352c78c): e578a7008dc871d82df04470b24a9b120de15a9d098c199608fc22d86c4366ca

### Re-registration 1 — 2026-10-27, after the build and two read-only reviews; before any method was scored on a made-up set of the power run

Seen when this was written: the `--shape` printout (§4.1's summaries) and the 7b dry run's claims (C2, C3, C5, C6, C7) and its plumbing
pass of two sets per world through every method — no power or false-alarm rate, no selection, no method on the real matrix. Each item
below is ruled by the main loop (technical; none touches the population, the features, the lines of §6 or a rule).

1. **C5b measures the generator BEFORE the tie step.** As registered, C5b compared the made-up correlation after §4.2 step 5 with R; on a
   correct pipeline it reads a largest gap of 0.0395 against the 0.03 line, because R was measured on his already-tied scores and step 5
   ties the latent again — every correlation of a few-level column is weakened a second time, by about 7% at five levels (all nine largest
   gaps are `entry_sessions_since_hi_5`, five distinct values; before the tie step the largest gap is 0.0243, rms 0.0059). Ruled: C5b is
   read on the pooled latent through the rank map (the generator samples R), lines unchanged (0.03 / 0.01); the post-tie comparison is
   printed beside as a readout. **Disclosed consequence:** the made-up sets carry about 7% less of his correlation on his few-level count
   columns than his data does. Not de-attenuated (that would change the generator after its shape was read).
2. **R95 accepted — M3's null carries the spectrum of the rows tested.** The real run's mode-A runs reuse the primary's reduction (§7.2);
   there the tested rows are not exactly unit-spectrum (M3w) or the primary's spectrum (M3u), and a toy single population read p = 0.001 on
   16 of 16 sets under the old null. The null of every node is built from the eigenvalues of the rows actually tested, in the space tested;
   in a node's own space (every node of the power run) this is numerically the registered null.
3. **The M3 noise floor's bootstrap arm tests the resample's DISTINCT rows** (about 63% of n), then assigns every row by nearest leaf mean.
   A bootstrap resample with duplicate rows makes a significance test over-split (toy: 7 of 12 single-population resamples below 0.01 even
   with their own reduction; 0 of 12 on a half subset without duplicates).
4. **Selection falls through to the gap-free arm whenever no method qualifies on the 75 columns** (R87 superseded). §6's Fallback 1 is read
   as: no qualifier on the 75 columns → the selection repeats on the 56-column arm with the same lines and order; **Fallback 2** = no
   qualifier on either arm, as §6 words it. (R87 had repeated the selection only when every method failed N1 on 75 columns, which left the
   case "some method passes N1 on 75, none qualifies there, one qualifies on 56" reading Fallback 2 against §6's wording.)
5. **Under `--columns pattern_free` the hold and the exit look-backs are described per group** (§6: "described per group, never grouped
   on"): the description reads the registered columns; the standardization, reduction and grouping read the 56.
6. **Gates tightened (review):** every real-run gate requires `06b_power.txt`'s modules line to equal the modules on disk, its pin below this
   marker, a `step7b_power` ledger row, and one of the three registered outcome strings; `--power` writes no `POWER COMPLETE` when any claim
   other than C1 reads MISMATCH; the M3 null cache carries its key and a stamp of the code that wrote it (a mismatch is a miss); a carried
   method's dry run and run reach their end (two `choice` reads guarded; §2 item 3's expectation scored on the carried method's own k).
7. **Process (review):** `06_groups.py --run` also needs the rebuilt `06_groups.py` and its new dry run pinned below the STEP-7 document's
   marker (its `run_gate` reads that document; pins below a marker do not change its `doc_body`); the reference copy
   `06_groups_dryrun_ref_8352c78c.txt` (sha e578a700…) is committed with the build.

8. **(2026-10-28, before `--power`) R103 accepted:** under Fallback 2 the size line's source is searched on the 75 columns first, then
   the 56 (§6's source order — the carried method, else the best method passing both false-alarm lines, else M0 — applied arm by arm in
   that order). It changes only the size line's wording in the "no style we could show we would see" outcome, never the outcome.
   **Correction to item 1's figures:** before the tie step the largest gap is 0.0243 and the rms 0.0052 (the 0.0059 quoted above is the
   post-tie rms); both under the lines.

### Pins before `--power` (2026-10-28) — the finished build: both dry runs 0 MISMATCH (7b 12 / 12; 06_groups default 33 / 33, reproducing the reference blocks), 92 tests, one Opus adversarial check ("could not refute ready for --power")

- entries: 6a0dda2da7932b6d54f122594df817215c1237636629f3ce6efa7cef1b9bdabf
- exits: 1ed76a2806091f7d56726c56e6b2a389dfa2e96db24c382d4296da096529b50f
- snapshots: a8987fce15fa1a968010b4290c249f2c62de24d18d1b71bca4b9b0c4f507caff
- control: 193a5b985b1d979d59b2d09e67a8caeb4fac9d4073f54b84b1f7315d69d15ccc
- panel: 2f3c5ee919fcb510c0ba31f4cb82d736c75fe3705d6d94fd16776d2a74835012
- calendar_cache: 47111a051ac101f12818fb1b2e300fd61ff953673db1286e7f1c2cbbe291b610
- lexicon: c7fb05ac383ff63f8f76702cec07ad1c08c517dbfb7a0843ee9a96a7d1e5105f
- dedupe_A: 223d3f360369cc009919c6fae83b3ba0bb37aa437706b45fcbbb70560477cf64
- sessions_A: 098a9b50c92a1045043bc089a4d4d600a9631bdb45a8e22969d872440672f2f0
- export_A: 0d5d2d0eb027abc06e4186ddec7d1e8b1234fd86f92c26798a8e15f113db668d
- export_B: ccc0097fe535cb8de9b83d6d534744b6cbadc114d9d29ecac677ac18a52900ba
- done_A: 1277e2b2e87845bd9c38d5978e1601681b0b6a89dd5afd10ba3d3b67420f0ac6
- done_B: cf60dbe4d2c514f93dec779b98db7d47054839f1b24f1e74f3fadc0133b92178
- done_EP: 0eb3548afe46feecf785e27b4b2e0839d5392c71bf4d67a1789f75e40c6ac735
- done_EP2: f8255199e52f0fa14aebcec5d50a407a1a52ac7c8b6cd4129bf41aa2f8cc591a
- done_REV: 945c41fb3618ed6b85a000232f6becc82c9d8e201b9bde99bd8673f9f7036d5e
- done_INTRA: a9dc793c33af220a2c030ae3d36f83af5d80ab91890b0e80c0deea3868d3f243
- done_ASIS: b18dea5e0e75d64991c1c0de366c7deee65d9488ebd921a6b26b37994ba598e1
- raw_close_A: f978db45074e9109178a1755c232fa1e684a6f83dab96ab007a26b12008f1444
- splits_B: 3199d06d5fb7dcd52ebd34e8c71e148b45ec0ca4a15f7f03ea1b715718882b0b
- entries_v2: 11f6ee5a7b652bdd421bde44ba8caa75dfcdc553f04280f23aefac4ae451c613
- exits_v2: 226579577eb169ada38b63a4bd320facf72ebe39a63f0141eb95d33c28c780de
- snapshots_v2: de4b8cce9a7ec6925024b467fb90c471d67a2475a141121b6fd2fa2eaffd0759
- subs_list: 99929453752cb3590b261e6928d99317312f35d9a50c0c147e33393b101a64a9
- asis_common.py: 4d36d6a42532dc782b7ccdce86a530a3b0bd948f66db74d5f1ab7af79a4562c4
- 01_points.py: aa30dc3c0402178d6b787b6e7f5957ec4921961feea39a40109b58fda66c6c65
- forbidden_identifiers.txt: ba8f4bb5f23f2325b6e1ed78e299d2044d3182313955f4509b1e16969e3ff81c
- 00c_windows_v2.py: de9ba698e9d238483f5f7a3864aa5e9ef4be9f2bf5c8307ba97659ed0bd9a6e4
- dryrun00c_printout: c08075f6727b91fa59bb19b1a0277715bf09dcc76c0b52f25a38f498872d1a4d
- write00c_printout: 49f8374b7ec6a4b9a0ea6143418037f599aff90e77d01e858b9eb4e21cd73f6c
- doc_body: b16d81fea023322db3e77f4cc99c24974d3591182f98ab7a4c7d0fdeaa52b5cb
- doc_body_steps56: 2b330f044c3f59da643f248ef97723dd80534b262458a766979f5fd22d748db0
- candidates: 5bde2911dd05a518c3460403beef4638643155e9f1f088551eb5f04cbd98b646
- ranges: 0d12cf9ab46a4fea914691cadb89e401207cd2e0c5359cf9dadeb9525f9c36c2
- coverage: 2584068b3cddb0644d47bb34c7c20ed34efd6feded84af26591852d99d6af7a2
- asis_check_common.py: c5061dca5ee2f6bef86dce38887fe27e17001635faefff93caacba85541fe200
- 03_check.py: 20ac382575b095d06e54e23fe70089ed228a34105efcdf925ff11f41e4d60496
- run6b_printout: 38678d784016b633a6053acf6a21a75e2b2f499e6dfaba50e08a3079281fc092
- check_r1_r5: 8df4521acde45b2c9ba7106271620f9e234c55d2c4a6c56aa78e74721123c958
- 05_tiers.py: 6c51b4879bced5399b725cef4b39b2a22b13d8ff7094ea9dfd9841d4772bcc03
- forbidden_outcomes.txt: bc942e6cdf95bc5e904e25a9f3f2935e0ff73ed43f08745c7f375dd1beae8d85
- dryrun7_printout: 10ab0bec0a6fdeda9029b33759a5eb6a0e00997fe9ee9d0edc476d705d87f831
- run7_tiers_printout: 5f25491df6f3c1dc39eaaa85f1285dd31c00337d265d26147a79908ae90cafdb
- tiers: c8fdfcffe40d889409fe63972931d4dcd9d84b59a79ba0577615fedb3d795b27
- 06_groups.py: c10c2fa75c69be3178929d53de3a283f79514432208aea1e0072600a1b19a1ea
- dryrun7g_printout: 6f6eb252ff5c950583dd6a9d5a0b966264e8419765fe86fcf5cff3bb951db540
- doc_body_7b: cf2ec533f2d34a2667c027865c50a692bbaa440ba6dc2727752957c00c5e2d4b
- reference_06_groups.py: 06a3f48f1046b8a91a8bbbe8e93dd30e5c62b3a46332bc7273b5984fcf68d404
- reference_06_groups_dryrun: e578a7008dc871d82df04470b24a9b120de15a9d098c199608fc22d86c4366ca
- step7b_shape: b5013f3eec4db769c7232475f0fad5fa69c52aa57f0b773423949fee2c659090
- shape7b_printout: 542b22c2c1a358735dcaac4dc9319fb8301a80ec9363c47ca6eb716556ade324
- 06b_power.py: d36e15048084003d1d3d719363010e7eeaf4e1d30954ee8b004a899cc66b4c43
- dryrun7b_printout: 02dfec90346e4154dceb418178647ae66de0c462cef37fe5502c648541731ff8

### RESULT of `--power` (2026-10-28, run once, 159.8 min on 10 processes; 9 claims, 9 OK, 0 MISMATCH)

**POWER COMPLETE: no style we could show we would see** (Fallback 2 — Fallback 1 fired and the gap-free arm qualified nothing either).

- **C1 (the premise) holds:** the registered rule (M0) finds the target group in 0 of 300 sets; the best possible sorter (the oracle) finds it in 300 of 300 — the information is in the data, no unsupervised method recovers it.
- **No method qualifies on either column set.** At the target every method hits 0-2 of 300. The methods that keep false alarms down (M0, M2w) see nothing at any separation; the ones with some reach (M1, M3u: 60% of 120 at Δ 3.0; M2u) invent groups in the null sets — M1 251 / 300 plain and 194 / 300 curved, M2u 296 / 292, M3u 224 / 300 curved, M4 279 / 300 curved.
- **The size line (from M2w, the best method passing both false-alarm lines):** it finds a hidden group of 30% of trades only when it stands apart by MORE than 3.0 within-group spreads on three separate measures; a 15% group at Δ 2.0: 0 in 100.
- Expectations (§8): C1 under 30% — met (0%); M4 fails N1 — missed (0 / 300 on N1, but 279 / 300 on N2, so it fails anyway); whitened methods under 50% at the target — met (0%); "M3u qualifies" — missed (N2 224 / 300); 15% group under 80% — met (0%); his real trades — not run (§7.1: the one-population branch).
- **Consequence (§7.1, written before the run):** `06_groups.py --run` under the registered method writes the one-population description, labelled **no style we could show we would see**, with the size line.

Pins: power7b_printout 841c3a9ecabd933e5b598cc8486766477d6cabca3202c0e0cf31179b7b7fc10a · step7b_power 6e7c71d45e9e09b07f27db8511a1ccb1edc29b4b1bffdb5d68b5d1feb325d822
