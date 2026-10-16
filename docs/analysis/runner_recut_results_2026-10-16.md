# Runner-rule re-cut against the live depth exit: RESULTS (run 2026-10-16)

**Result: STANDS.** The depth exit stays for the part of a MAGNA53 position that is already working. The pre-registered primary
(Frame A, hold 20 sessions after the +8 ORB-R partial, stop held at its resting level) cleared P1 and P6 and failed P2, P3, P4 and
P5. Nothing is flipped and no proposal is made. Action for the operator: none. (Steps 8 and 9 of the pre-registration belong to the
session; paste-ready lines are at the bottom.)

**Contract:** `docs/analysis/runner_recut_preregistration_2026-10-16.md` (not edited; its population, control, primary, measures and
decision bar were applied as written). **Owed by:** `data_gated_reviews.yaml` -> `runner_rule_sweep_recut` (FIRED 2026-10-13, the
`magna53_depth_exit` toggle) and PLAN #687 (the weekend re-cut). **Standard:** `docs/methodology/analysis_standard.md`.
Money-R throughout: profit / (entry - placed stop); the +8 ORB-R partial is +4.0 money-R, the +3 ORB-R breakeven arm +1.5 money-R.

## The answer in six lines

- **Primary vs the live depth exit, n = 185 scored trades, 29 of them reaching the +8 ORB-R partial:** holding 20
  sessions after the partial is ahead by +6.69R in total (+0.036R a trade; 95% week-bootstrap interval
  -0.096 to +0.275R a trade), week-block p = 0.902. Not distinguishable from zero.
- **One trade carries it.** BABA 2026-07-08 adds +15.58R; without it the rule is -8.89R behind, and without its
  two largest gains it is -13.15R behind. The five largest gains are 382% of the total.
- **It buys money by losing the tail.** +4R winners: 9 against the control's 10 (lost SGML 04-13, TXN 04-23, FTK 08-03;
  gained DOCN 05-05, MSFT 07-30). It is behind in H1 (-6.19R, n = 120) and ahead only in H2 (+12.88R, n = 65).
- **Enough trades differ to judge** (P1 holds: 16 trades differ across 8 entry weeks), so the pre-registered
  expectation "most likely TOO FEW" was wrong. The word is STANDS, not TOO FEW.
- **#687's exact rule did not replicate on this population** (`t20_entry_ref`: +8.05R, p = 0.90,
  behind in H1, still BABA-carried). 21 exploratory arms: none registers as the next primary.
- **Limit that matters:** the optional prod pull was REFUSED, so 12 control positions (13 under the primary) are still open at the data
  end 2026-08-28 and are marked at their last stored close. Those 12 carry +22.5R of the control's +44.3R. Their count is in every table (last column).

## Deviations from the pre-registration (dated, none touches the bar, the population or the control)

| # | deviation | effect |
|---|---|---|
| D1 | Run on **Friday 2026-10-16** (PT, mid-session), not Saturday 10-17, because the harness asked for it. | None: the read of record is the capture, which ends 2026-08-28. |
| D2 | This results document is `runner_recut_results_2026-10-16.md` (named by the task), not the pre-registration's `runner_recut_2026-10-17.md`. | None. The pre-registration file is untouched. |
| D3 | **Step 3 (the ONE optional prod read) was REFUSED by the permission system** (auto-mode classifier, "Production Reads"). I tried it once, sending the pre-registered SQL over ssh stdin instead of `scp` to a remote scratch file (so nothing would be written on the host). Not retried, no other route taken, no search for other local copies of later bars. | The pre-registered fallback is in force: the read of record is the capture alone; positions open at 2026-08-28 are marked at their last stored close and counted per arm. G-ext cannot run (below). `--ext` in `recut.py` refuses to run. |
| D4 | Step 0 (`live_rules.py --drift-only`) ran as written and its read-only prod read succeeded (server checkout `f06371f4`): 0 drift findings. | None. |
| D5 | The frozen walker copy is **generated** by `make_walker.py` (17 anchored patches against git blob `e9098c36`, which it asserts), not hand-typed. The full difference from the live walker is `walker_diff.out` (186 lines). | Makes the "one hook" auditable; G2 proves the copy with no rule equals the live walker on every row. |

**Reading choices fixed in the code before THE run** (the pre-registration left these open; none was tuned on a result; the run was executed once):
(1) F = the resting stop right after the trigger bar's own breakeven/partial update, i.e. max(prior session's depth stop, entry), before that
bar's 16:45 ratchet; (2) the trigger session is session 0 of the hold, and a day-0 trigger makes session 1 the first counted (the live job never
decides on the entry day); (3) the Frame B trigger is the first touch of entry + 3 ORB-R (day 0 or a later session); (4) the chandelier and
give-back peak is the highest held close, day-0 close included, through the deciding session, and no decision is made on day 0;
(5) "engaged" = the control path reached the frame's trigger (day-0 triggers included); (6) "paired" = both the control and the arm are scored;
(7) a data-end mark = booked legs + (last stored close - entry) x remaining size; (8) "differ" = more than 0.005R apart; the top-five share =
the five largest positive paired gains / the total paired difference; (9) p90 is the linear-interpolated percentile; the sign-flip counts
|permuted total| >= |observed|; the bootstrap resamples whole entry weeks.

## Method and population

**Population:** Run U's `replayable` rows from `docs/analysis/ep_backtest_run1_2026-08-29.md`, from the same captures (gzipped copies in
`scripts/probes/_runner_recut_1017/captures/`, sha256 prefixes checked against the pre-registered pins by G0): 295 rows on 252 tickers, entry dates
2026-04-13 to 2026-08-28. 85 never triggered, 16 had no usable bars (4 degenerate ORB, 12 with no bars after the ORB), **194 filled** (the 08-29
read also had 194). The walker abstains on 9 of the 194 (5 `day0_fill_bar_straddles_stop`, 4 `fwd_stop_and_breakeven_same_day`), identically in every
arm, so **n = 185 scored**; the 08-29 harness resolved those orderings stop-first, which is the difference the pre-registration predicted.
Entry weeks: 19 distinct. Halves: H1 = entries 04-13 to 06-30 (n = 120 scored), H2 = 07-01 to 08-28 (n = 65).

**Control (era E, exactly as live):** `live_fill_counterfactuals.walk_arm(harvest="live_ladder", trail_mode="sma", target=entry+8 ORB-R, breakeven_at_r=3.0,
r_frame_ps=ORB-R, breakeven_at_partial=True, trail_prior_closes=True, ladder_partial=False, horizon=40, depth_exit=True, depth_adr20_pct=ADR20)`;
the era-E stack read from `rule_eras.exit_rules_as_of` agrees (8.0 / 3.0 / depth / next-open sale). Code blobs pinned and verified at run time:
`live_fill_counterfactuals.py` e9098c36, `exit_logic.py` d5597612, `_bt_replay.py` 727d5f84, `_runner_sweep.py` 57e4e246.

**Candidates:** the eleven pre-registered rules in both frames, run through `walker_cand.py` (frozen copy of the live walker + one hook set).
Frame A = from the bar the +8 ORB-R partial books; Frame B = from the bar the +3 ORB-R arm first trades (exploratory). One primary: Frame A `t20_be`.

**Read of record:** the captured daily bars alone (D3). Statuses over the 194: control settled 173, abstain 9, **open at data end 12** (marked), horizon 0, internal gaps 0.

**Commands, in order, all captured under `scripts/probes/_runner_recut_1017/`:** step 0 `live_rules_drift_1017.out` (exit 0) -> step 1 `g0_hashes.out`
(7 of 7 OK, exit 0) + captures copied -> step 2 `g1_sweep_repro.out`, `g1_diff.out` (diff exit 0), `g1_hashes.out` (unchanged) -> step 3 REFUSED
(`pull_daily_ext.REFUSED.txt`) -> step 4 `selftest.out` (exit 0, 55 checks) -> step 5 `gate.out` (exit 0) -> step 6 `run.out` (exit 0), `handtrace.out` (exit 0).
Descriptive follow-ups, after the run and adding no test: `post_descriptive.out`, `diag_sma10.out`, `structure_check.out` (a pre-run accounting check that printed no outcome).
Code sha256 prefixes: `recut.py` 24b2e70aa29e6427, `walker_cand.py` 3a9e693c0db1ceb4, `make_walker.py` 840cbf1de9e58cc0; `run.out` a781524088bd3dd4.

## Gates (none prints a total)

| gate | result | evidence |
|---|---|---|
| G0 inputs | PASS | decompressed captures match the 7 pinned hashes |
| G1 the 08-29 sweep reproduces | PASS | `diff` of the re-run stdout against the stored stdout: exit 0; the rewritten JSON/TSV hashes are unchanged (no investigation needed) |
| G2 copy == live | PASS | frozen copy with no rule equals the live `walk_arm` on all 194 filled rows (status, reason, every exit leg to 1e-9) |
| **G2b depth really engaged** | PASS | see the block below |
| G3 up to the trigger | PASS | 4,656 candidate-or-reference x trade walks equal the control on every trade whose trigger never fired and match it through the trigger bar where it did (Frame A fired on 29 trades, Frame B on 75); the mutation test (the candidate applied before its trigger) turns G3 red in Frame A and in Frame B |
| G-ext | **NOT RUN** | the extension pull was refused (D3). The pre-registered requirement "open-at-end falls versus the capture-only pass" cannot be tested. |

**G2b, the positive proof that the depth stop acted (the `WOULD-FAIL-IF` of the pre-registration):**
- ADR20 is None on **0 of 194** trades, so no trade silently rested at the floor.
- **223 sessions** where the resting stop was line x (1 - ADR20) rather than the floor AND it raised the stop. Named: SGML 2026-04-13, session 7 (2026-04-22),
  line 18.3760, ADR20 0.1064, floor 15.85 -> depth stop 16.42 (was 15.85).
- **47 close-below sales, all 47 priced at a next open that differs from the deciding close.** Named: GPRE 2026-04-13 closed 15.39 below its line, sold at
  the next open 15.36 (hand-traced below).
- 6 stop-hit sales above entry (the depth-bound stop doing the selling).

**Self-tests (55 checks, synthetic bars):** one per rule (trigger fires -> that rule's exit and price), the no-trigger identity (all 22 arms equal the
control on a flat path), next-open pricing (close_only, gb25, gb50), gap-through, day-0 trigger, F above entry (the orderable form stops at F while #687's
reset-to-entry does not), the two mutations, the statistics on constructed data, and an end-to-end dry run of the reporting path on synthetic rows.

## Results: the pre-registered table (n = 185 scored trades; every arm paired with the control on the same trades)

Money-R. "open at end" = positions still open at 2026-08-28, marked at their last stored close (horizon marks: none, except sma20_depth A/B and gb50_be A/B listed in `run.out`).

| frame | rule | paired n | engaged n | differ n | +4R trades (share of n) | +1.5R trades | p90 R | total R | mean R | delta vs control | delta without top 2 | drop-best-2 | H1 / H2 delta | p (week-block) | median R | win % | open at end |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| - | control (depth), n = 185 | 185 | - | - | 10 (5.4%) | 27 | +2.38 | +44.27 | +0.239 | - | - | +13.97 | - | - | -0.530 | 28.1% | 12 |
| A | **t20_be (PRIMARY)** | 185 | 29 | 16 | 9 (4.9%) | 21 | +1.96 | +50.96 | +0.275 | +6.69 | -13.15 | +12.50 | -6.19 / +12.88 | 0.902 | -0.530 | 28.1% | 13 |

**Control (era E depth exit), n = 185:** best AOSL 2026-04-14 +17.84R, worst GLW 2026-07-09 -1.20R, 0 losses beyond -1.5R, 31 give-backs
(reached +1.5R, finished at or below 0). Its +4R winners: AOSL 04-14, BABA 07-08, BE 04-14, FTK 08-03, IONQ 04-14, RKLB 05-08, SGML 04-13, STM 04-23, TEAM 08-07
(a mark, still open), TXN 04-23. By entry month: Apr +43.27R (n = 45), May -11.19R (n = 62), Jun -8.84R (n = 13), Jul +3.34R (n = 24), Aug +17.69R (n = 41);
H1 +23.24R (n = 120), H2 +21.03R (n = 65).

### The primary in full (Frame A `t20_be`)

| measure | value |
|---|---|
| paired n / engaged n / differ n | 185 / 29 / 16 (the 16 span 8 entry weeks of 19) |
| tail: +4R trades, arm vs control | 9 (4.9%) vs 10 (5.4%); +1.5R trades 21 vs 27 |
| +4R winners lost / gained, by name | lost SGML 2026-04-13, TXN 2026-04-23, FTK 2026-08-03 / gained DOCN 2026-05-05, MSFT 2026-07-30 |
| p90 R; best trade | +1.96; BABA 2026-07-08 at +22.67R (the control's best is AOSL at +17.84R) |
| total R; mean R | +50.96; +0.275 (control +44.27) |
| paired difference: total; per trade | +6.69R; +0.036R, 95% week-clustered bootstrap interval -0.096 to +0.275 |
| week-block sign-flip p (5,000 draws, seed 1017, two-sided) | 0.9024 |
| own total without its two best trades | +12.50R (control +13.97R) |
| paired difference without its two largest gains (BABA, DOCN) | -13.15R; without BABA alone -8.89R |
| top five gains, share of the paired total | BABA +15.58, DOCN +4.26, IONQ +3.66, MSFT +1.21, BE +0.87 = +25.57R = 382% |
| by entry month, delta (n) | Apr -5.31 (45), May -0.88 (62), Jun +0.00 (13), Jul +16.61 (24), Aug -3.74 (41) |
| by half, delta (n) | H1 -6.19 (120); H2 +12.88 (65) |
| capture (arm R / best close reached, ratio of sums) | 47.5% (n = 28 engaged trades with a positive best close) |
| costs | win 28.1% (identical to the control; descriptive only, an exit rule is not judged on it); median -0.530R; worst -1.20R; 0 losses beyond -1.5R; 31 give-backs; open at end 13 (control 12) |
| F (the stop held through the hold), engaged trades | above entry on **1 of 29** (TXN 2026-04-23, F = +1.54 money-R); median F = 0.00R; minimum 0.00R |
| how the 29 end | primary: 8 time exits, 16 stopped at F, 5 still open; control: 13 close-below sales, 12 stop-hits, 4 still open |

**What the 29 look like:** 7 reached the partial on day 0, 22 later; 13 of the 29 are unchanged to within 0.005R (9 stopped out at the same +1.33R under both rules, i.e. the partial then
breakeven; 4 are the same still-open marks). The rule only matters on the other 16, and they split 5 up, 11 down:
BABA +15.58, DOCN +4.26, IONQ +3.66, MSFT +1.21, BE +0.87 against FTK -3.74, SGML -2.44, STM -2.34, RKLB -2.21, AOSL -2.04, RGTI -2.00, TXN -1.95, CRDO -1.07,
OKTA -0.55, FLEX -0.38, MRVL -0.17. Descriptive detail: `post_descriptive.out`.

## The pre-registered bar, applied mechanically to the primary

| # | condition | result | value |
|---|---|---|---|
| P1 | >= 10 trades differ AND >= 6 distinct entry weeks | **True** | 16 trades, 8 weeks |
| P2 | paired total > 0 AND week-block p < 0.05 | **False** | total +6.69R, p = 0.902 |
| P3 | still ahead without its two largest positive contributors | **False** | -13.15R |
| P4 | ahead in BOTH halves | **False** | H1 -6.19R (n = 120), H2 +12.88R (n = 65) |
| P5 | +4R winners no fewer than the control's | **False** | 9 vs 10 |
| P6 | orderable live | **True** | F >= entry at every trigger; the resting stop never stepped down in 4,268 walks (194 x 22) |

**Outcome (section 5, verbatim): STANDS (P1 holds, P2 to P5 fail).** The depth exit stands for the runner. The orderable form of the 09-29 `t20_be` lead does not
beat it, and `t20_be` is dropped as the named candidate. Whether #687's exact rule replicated is reported from `t20_entry_ref`, which is descriptive and cannot
produce a proposal. This window is not re-cut again. The tripwire stays armed on its trade arm (40 era-E live closes) and on the next exit-stack change.

## Reference rows (never candidates)

| frame | rule | paired n | engaged n | differ n | +4R trades (share of n) | +1.5R trades | p90 R | total R | mean R | delta vs control | delta without top 2 | drop-best-2 | H1 / H2 delta | p (week-block) | median R | win % | open at end |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| ref | t20_entry_ref | 185 | 29 | 16 | 9 (4.9%) | 21 | +1.96 | +52.32 | +0.283 | +8.05 | - | - | - | - | -0.530 | 28.1% | 13 |
| ref | era_d | 185 | - | 62 | 7 (3.8%) | 27 | +2.38 | +43.45 | +0.235 | -0.82 | - | - | - | - | -0.496 | 32.4% | 11 |
| ref | control_at_close | 185 | - | 47 | 9 (4.9%) | 27 | +2.41 | +48.72 | +0.263 | +4.45 | - | - | - | - | -0.585 | 30.3% | 12 |

- **`t20_entry_ref` (#687's exact rule, stop reset to entry at the trigger):** +8.05R in total, p = 0.902, behind in H1
  (-4.83R), -11.79R without its two best, +4R winners 9 vs 10. It differs from the primary only on TXN
  (F was above entry there, and the reset to entry keeps the trade alive). **Not replicated at decision grade.**
- **`era_d` (the retired stop-on-the-line exit):** -0.82R against the control over 62 differing trades (p = 0.95); +4R winners 7 vs 10.
  What the 10-12 switch did on this population: nothing detectable in money, three more +4R winners.
- **`control_at_close` (vehicle cost):** selling the 47 close-below exits at the deciding close instead of the next open would be +4.45R better in total on this
  population (p = 0.36). The next-open sale is what shipped (mechanics study); this row only prices it.

## The other 21 arms (EXPLORATORY: cannot produce a proposal)

| frame | rule | paired n | engaged n | differ n | +4R trades (share of n) | +1.5R trades | p90 R | total R | mean R | delta vs control | delta without top 2 | drop-best-2 | H1 / H2 delta | p (week-block) | median R | win % | open at end |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| A | t3_be | 185 | 29 | 23 | 13 (7.0%) | 29 | +3.08 | +47.44 | +0.256 | +3.17 | -3.83 | +29.17 | +1.58 / +1.58 | 0.670 | -0.530 | 28.1% | 8 |
| A | t5_be | 185 | 29 | 20 | 12 (6.5%) | 26 | +2.43 | +49.25 | +0.266 | +4.98 | -2.96 | +19.11 | -3.04 / +8.02 | 0.667 | -0.530 | 28.1% | 8 |
| A | t10_be | 185 | 29 | 16 | 9 (4.9%) | 24 | +2.37 | +41.94 | +0.227 | -2.33 | -5.20 | +14.18 | +0.68 / -3.01 | 0.741 | -0.530 | 28.1% | 12 |
| A | close_only | 185 | 29 | 3 | 9 (4.9%) | 27 | +2.38 | +40.14 | +0.217 | -4.13 | -4.13 | +12.43 | -2.86 / -1.27 | 0.258 | -0.530 | 28.1% | 12 |
| A | sma10_depth | 185 | 29 | 0 | 10 (5.4%) | 27 | +2.38 | +44.27 | +0.239 | +0.00 | +0.00 | +13.97 | +0.00 / +0.00 | 1.000 | -0.530 | 28.1% | 12 |
| A | sma20_depth | 185 | 29 | 15 | 8 (4.3%) | 25 | +2.40 | +46.50 | +0.251 | +2.23 | -8.92 | +15.87 | -5.52 / +7.75 | 0.852 | -0.530 | 28.1% | 13 |
| A | atr1_be | 185 | 29 | 26 | 11 (5.9%) | 32 | +3.26 | +51.46 | +0.278 | +7.19 | +1.64 | +25.31 | +4.70 / +2.49 | 0.392 | -0.530 | 28.1% | 8 |
| A | atr2_be | 185 | 29 | 22 | 9 (4.9%) | 30 | +3.03 | +50.94 | +0.275 | +6.67 | +0.40 | +20.58 | +4.09 / +2.58 | 0.488 | -0.530 | 28.1% | 10 |
| A | gb25_be | 185 | 29 | 24 | 9 (4.9%) | 32 | +3.05 | +63.98 | +0.346 | +19.72 | +10.08 | +30.31 | +13.57 / +6.14 | 0.018 | -0.530 | 28.1% | 8 |
| A | gb50_be | 185 | 29 | 18 | 8 (4.3%) | 30 | +2.44 | +47.85 | +0.259 | +3.58 | -2.70 | +17.92 | +1.67 / +1.91 | 0.507 | -0.530 | 28.1% | 12 |
| B | t3_be | 185 | 75 | 46 | 15 (8.1%) | 34 | +3.06 | +55.04 | +0.298 | +10.77 | +1.77 | +37.46 | -1.88 / +12.66 | 0.618 | -0.530 | 29.7% | 4 |
| B | t5_be | 185 | 75 | 44 | 13 (7.0%) | 38 | +3.13 | +75.87 | +0.410 | +31.61 | +18.64 | +45.52 | +5.19 / +26.42 | 0.144 | -0.530 | 29.2% | 4 |
| B | t10_be | 185 | 75 | 33 | 11 (5.9%) | 27 | +2.48 | +47.39 | +0.256 | +3.13 | -7.95 | +17.64 | -9.73 / +12.86 | 0.823 | -0.530 | 25.9% | 10 |
| B | t20_be | 185 | 75 | 31 | 10 (5.4%) | 26 | +2.88 | +67.69 | +0.366 | +23.43 | +0.23 | +27.32 | -0.42 / +23.85 | 0.353 | -0.530 | 25.9% | 15 |
| B | close_only | 185 | 75 | 6 | 9 (4.9%) | 28 | +2.38 | +38.86 | +0.210 | -5.40 | -5.80 | +11.16 | -4.13 / -1.27 | 0.198 | -0.530 | 27.6% | 12 |
| B | sma10_depth | 185 | 75 | 0 | 10 (5.4%) | 27 | +2.38 | +44.27 | +0.239 | +0.00 | +0.00 | +13.97 | +0.00 / +0.00 | 1.000 | -0.530 | 28.1% | 12 |
| B | sma20_depth | 185 | 75 | 28 | 8 (4.3%) | 28 | +2.49 | +49.73 | +0.269 | +5.46 | -5.68 | +19.10 | -3.37 / +8.83 | 0.689 | -0.530 | 25.9% | 17 |
| B | atr1_be | 185 | 75 | 53 | 10 (5.4%) | 35 | +2.65 | +59.09 | +0.319 | +14.82 | +4.73 | +32.93 | +5.24 / +9.58 | 0.496 | -0.530 | 32.4% | 4 |
| B | atr2_be | 185 | 75 | 42 | 11 (5.9%) | 30 | +3.18 | +62.36 | +0.337 | +18.10 | +9.15 | +32.00 | +5.71 / +12.38 | 0.257 | -0.530 | 30.3% | 10 |
| B | gb25_be | 185 | 75 | 48 | 10 (5.4%) | 35 | +2.87 | +64.64 | +0.349 | +20.37 | +8.98 | +30.96 | +9.12 / +11.25 | 0.302 | -0.530 | 31.4% | 4 |
| B | gb50_be | 185 | 75 | 40 | 9 (4.9%) | 30 | +2.44 | +56.15 | +0.303 | +11.88 | +2.11 | +26.22 | +2.38 / +9.50 | 0.498 | -0.530 | 31.4% | 13 |

- **None registers as the next primary:** no arm meets P1, P3, P4 and P5 together with an unadjusted p < 0.05 and a positive total.
- **Closest: Frame A `gb25_be`** (give back a quarter of the peak gain, then sell at the next open): +19.72R, unadjusted p = 0.018, +10.08R
  without its two best, ahead in both halves (+13.57 / +6.14). It fails P5: 9 winners at +4R against the control's 10 (loses TXN and
  TEAM, gains NVTS; TEAM is itself a position still open at the data end). One arm in 21 under p < 0.05 is what chance gives (expected about one), so this is a
  lead to remember, not one to act on, and by the pre-registered rule it is not registered.
- **Frame B expectation (written before the data):** "wrong if any Frame B rule shows a paired gain above +0.2R a trade with p under 0.01 in both halves." **It holds, none does.**
  The best Frame B arm is `t5_be` (hold 5 sessions after the +3 ORB-R arm): +31.61R (+0.171R a trade, interval -0.029 to +0.392, p = 0.144).
  It clears P3, P4 and P5 (+18.64R without its two largest gains COHR and LITE; ahead in both halves; 13 winners at +4R vs 10) and fails only significance, so it is the one Frame B lead to carry. By the
  pre-registered rule it cannot be registered or proposed from this read.
- `sma10_depth` equals the control on all 185 trades in both frames. That is real, not a plumbing hole: it uses a different line on the sessions where SMA20 > SMA10
  (e.g. MRVL session 1: effective stop 209.57 vs 192.07), but those occur right after entry, when no decision turns on them (`diag_sma10.out`).

## Hand-traces (picked mechanically: the first trade in entry order showing each event; recomputed from the raw bars, then compared)

- **Depth next-open sale, GPRE 2026-04-13:** entry 15.50, ORB-R 0.275, placed stop 14.95. ADR20 recomputed from the 20 prior sessions = 0.058998 (the walker's input is identical).
  Session 1 (2026-04-14) closes 15.39 below its line (SMA10 15.938, SMA20 16.041). The sale is session 2's open, 15.36; the deciding close was 15.39. R = -0.2545 by the walker and by independent arithmetic. MATCH.
- **+8 ORB-R partial then a `t20_be` exit, SGML 2026-04-13:** the +3 ORB-R arm traded on day 0, the +8 ORB-R partial (20.25) on session 3, so F = entry 15.85 and the 20th session after the partial is
  session 23 (2026-05-14), close 17.865. The partial books 1/3 at 20.25, the rest sells at 17.865. R = +2.5545 by the walker and by independent arithmetic. MATCH. (The control sold the same trade on a close below its line for +4.99R; the fixed 20-session hold
  gave back more of the run.)
Both traces are in full in `handtrace.out`.

## Marks and the refused pull (the stated limit)

- Positions open at 2026-08-28, marked at their last stored close: **control 12**, primary 13, `t3_be`/`t5_be`/`gb25_be` (Frame A) 8, `t20_be` (Frame B) 15. Per-arm counts for every arm and reference row are in `run.out`.
  Horizon marks (the 40th close) are 0 for the control and the primary.
- **The 12 marked control positions carry +22.52R of the control's +44.27R (51%)**: CHYM 08-06 +3.18, TEAM 08-07 +5.38, OMER 08-13 +0.94, ARGX 08-17 +3.89, AMLX 08-18 +1.57, MRNA 08-19 +2.49, TEM 08-19 +2.74,
  TWST 08-19 +1.10, CRM 08-27 +2.48, OKTA 08-27 -0.09, VEEV 08-27 -0.37, SOLS 08-28 -0.77. All are August entries, so they sit in H2: H2's +21.03R is entirely paper gain (the settled H2 trades net -1.49R).
- Of the 29 Frame A trades, TEAM (08-07), ARGX (08-17), MRNA (08-19) and TEM (08-19) are marks under the control, and MSFT (07-30) is a mark under the primary only. TEAM is also one of the two +4R winners
  credited as lost by `gb25_be`. Settling these needs the later bars the refused pull would have supplied; **the pull has not been replaced by anything else, by design.** The direction of the error is unknown: a mark can still be given back or extended.
- **How far the verdict leans on the marks:** the arms agree on 4 of the 5 engaged marks (TEAM, ARGX, MRNA, TEM: a paired difference of 0.00R today), and the primary's only mark that differs is MSFT (+1.21R). With later bars those five
  could settle differently under the two rules (a hold-longer rule is the one that can gain from a run that continues, as BABA did). P2 (p = 0.90) and P3 (-13.15R) are far from their lines, so a flip is unlikely, but that is a judgement and not a measurement.

## What this does not answer

- **Whether any of this transfers to the EPs we actually trade.** Run U over-admits (08-28: 5 names modelled against 1 actual) and uses the 2026-08-29 admission manifest, not today's. Real EPs reached the +8 ORB-R partial 1 time in
  86 (#685); here 29 of 185 did. The paired differences are conditional on this runner mix.
- **The live era-E record.** No depth-stamped trade has closed yet; the tripwire's trade arm (40 era-E live closes, roughly a year at today's rate) is the forward check.
- **Settled outcomes for the 12 to 15 positions still open at 2026-08-28** (the refused pull), and anything after that date.
- **Regime and concentration.** 19 entry weeks. The control's total is April (+43.27R) and August (+17.69R, mostly marks); May and June are negative. The primary's difference is July (+16.61R, BABA). One trade (BABA) decides the sign of the primary's total; the halves,
  months and top-five share address this and do not remove it.
- **Portfolio effects:** max-5 positions, the 2% daily loss limit, the 10-loss count breaker (a lower win-rate rule interacts with it), whole-share sizing and the resting profit-take third that live can leave unfilled.
- **Anything upstream of the trigger:** entries, admission, the +8 ORB-R partial level, the +3 ORB-R arm and the depth distance (1 ADR) are frozen. Hybrids outside the eleven rules (regime-switched exits, ladders, re-entries) were not tried.
- **Resolution:** only day-0 minute bars are stored; the depth-stop touch, the +8 and +3 ORB-R levels are resolved on daily high/low after day 0, and same-bar orderings abstain (9 trades, all arms alike).
- **Multiplicity:** one named primary, so its p needs no correction; the 21 exploratory arms do, and no claim here rests on one.

## For the session (the pre-registration's steps 8 and 9; I did not touch those files)

- **`data_gated_reviews.yaml` -> `runner_rule_sweep_recut`, under the FIRED 2026-10-13 note:** "Re-cut run 2026-10-16 (rule-toggle arm; toggle `magna53_depth_exit|live` on 2026-10-12): STANDS. Primary Frame A t20_be vs the depth exit,
  n = 185 scored (29 reached the +8 ORB-R partial): +6.69R total, p = 0.90, behind by 13.15R without its two best trades, behind in H1, 9 vs 10 trades at +4R; one trade (BABA) carries the sign. #687's exact rule did not replicate
  (+8.05R, p = 0.90). Depth exit stands for the runner; window not re-cut again; trade arm (40 era-E closes) stays armed. Doc: docs/analysis/runner_recut_results_2026-10-16.md."
- **PLAN #687, next sentence:** "Runner re-cut done 10-16 (STANDS): hold-20 does not beat the depth exit on Run U; closest lead (give-back-25% after the partial) fails the tail condition and is not registered; refused prod pull left 12 positions marked at 08-28."

## THE LINE

Exit discipline is the operator's sole authority. This document ran nothing live, wrote nothing to prod and changes nothing. The bar decided only whether a proposal would be brought to him; the answer is that none is.
