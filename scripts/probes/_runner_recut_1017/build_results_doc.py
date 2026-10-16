#!/usr/bin/env python3
"""Assemble docs/analysis/runner_recut_results_2026-10-16.md. Every table cell is generated from
run_results.json (the one run's output); the prose is fixed text that states those numbers' meaning.
Nothing here recomputes or changes a result."""
import json

P = "/Users/alvinfung/apollo_the_wise/scripts/probes/_runner_recut_1017"
OUT = "/Users/alvinfung/apollo_the_wise/docs/analysis/runner_recut_results_2026-10-16.md"
R = json.load(open(f"{P}/run_results.json"))
C = R["control"]
ARMS = R["arms"]
REFS = R["refs"]
RULES = ["t3_be", "t5_be", "t10_be", "t20_be", "close_only", "sma10_depth", "sma20_depth",
         "atr1_be", "atr2_be", "gb25_be", "gb50_be"]


def row(frame, name, m, ref=False):
    n = m["paired_n"]
    eng = "-" if ref and m.get("engaged_n") is None else m.get("engaged_n")
    xt = f"{m['n_tail']} ({100 * m['n_tail'] / n:.1f}%)"
    if ref:
        return (f"| {frame} | {name} | {n} | {eng} | {m['differ_n']} | {xt} | {m['n_be']} | {m['p90']:+.2f} | {m['total']:+.2f} | "
                f"{m['mean']:+.3f} | {m['delta_total']:+.2f} | - | - | - | - | {m['median']:+.3f} | {100 * m['win']:.1f}% | "
                f"{m['open_data_end']} |")
    return (f"| {frame} | {name} | {n} | {eng} | {m['differ_n']} | {xt} | {m['n_be']} | {m['p90']:+.2f} | {m['total']:+.2f} | "
            f"{m['mean']:+.3f} | {m['delta_total']:+.2f} | {m['delta_ex_top2']:+.2f} | {m['drop_best2']:+.2f} | "
            f"{m['h1']:+.2f} / {m['h2']:+.2f} | {m['p_weekblock']:.3f} | {m['median']:+.3f} | {100 * m['win']:.1f}% | "
            f"{m['open_data_end']} |")


HEAD = ("| frame | rule | paired n | engaged n | differ n | +4R trades (share of n) | +1.5R trades | p90 R | total R | mean R | "
        "delta vs control | delta without top 2 | drop-best-2 | H1 / H2 delta | p (week-block) | median R | win % | open at end |\n"
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")

ctrl_row = (f"| - | control (depth), n = {C['n']} | {C['n']} | - | - | {C['n_tail']} ({100 * C['n_tail'] / C['n']:.1f}%) | {C['n_be']} | "
            f"{C['p90']:+.2f} | {C['total']:+.2f} | {C['mean']:+.3f} | - | - | {C['drop_best2']:+.2f} | - | - | {C['median']:+.3f} | "
            f"{100 * C['win']:.1f}% | {C['open_e']} |")

t_main = "\n".join([HEAD, ctrl_row, row("A", "**t20_be (PRIMARY)**", ARMS["A|t20_be"])])
t_exp = "\n".join([HEAD] + [row(fr, ru, ARMS[f"{fr}|{ru}"]) for fr in "AB" for ru in RULES if f"{fr}|{ru}" != "A|t20_be"])
t_ref = "\n".join([HEAD] + [row("ref", n, REFS[n], ref=True) for n in ("t20_entry_ref", "era_d", "control_at_close")])
pr = ARMS["A|t20_be"]
V = R["verdict"]

DOC = f"""# Runner-rule re-cut against the live depth exit: RESULTS (run 2026-10-16)

**Result: STANDS.** The depth exit stays for the part of a MAGNA53 position that is already working. The pre-registered primary
(Frame A, hold 20 sessions after the +8 ORB-R partial, stop held at its resting level) cleared P1 and P6 and failed P2, P3, P4 and
P5. Nothing is flipped and no proposal is made. Action for the operator: none. (Steps 8 and 9 of the pre-registration belong to the
session; paste-ready lines are at the bottom.)

**Contract:** `docs/analysis/runner_recut_preregistration_2026-10-16.md` (not edited; its population, control, primary, measures and
decision bar were applied as written). **Owed by:** `data_gated_reviews.yaml` -> `runner_rule_sweep_recut` (FIRED 2026-10-13, the
`magna53_depth_exit` toggle) and PLAN #687 (the weekend re-cut). **Standard:** `docs/methodology/analysis_standard.md`.
Money-R throughout: profit / (entry - placed stop); the +8 ORB-R partial is +4.0 money-R, the +3 ORB-R breakeven arm +1.5 money-R.

## The answer in six lines

- **Primary vs the live depth exit, n = {pr['paired_n']} scored trades, {pr['engaged_n']} of them reaching the +8 ORB-R partial:** holding 20
  sessions after the partial is ahead by {pr['delta_total']:+.2f}R in total ({pr['delta_mean']:+.3f}R a trade; 95% week-bootstrap interval
  {pr['boot_lo']:+.3f} to {pr['boot_hi']:+.3f}R a trade), week-block p = {pr['p_weekblock']:.3f}. Not distinguishable from zero.
- **One trade carries it.** BABA 2026-07-08 adds +15.58R; without it the rule is {pr['delta_total'] - 15.5777777777779:+.2f}R behind, and without its
  two largest gains it is {pr['delta_ex_top2']:+.2f}R behind. The five largest gains are 382% of the total.
- **It buys money by losing the tail.** +4R winners: {pr['n_tail']} against the control's {pr['n_tail_ctrl']} (lost SGML 04-13, TXN 04-23, FTK 08-03;
  gained DOCN 05-05, MSFT 07-30). It is behind in H1 ({pr['h1']:+.2f}R, n = {pr['h1_n']}) and ahead only in H2 ({pr['h2']:+.2f}R, n = {pr['h2_n']}).
- **Enough trades differ to judge** (P1 holds: {pr['differ_n']} trades differ across {pr['differ_weeks']} entry weeks), so the pre-registered
  expectation "most likely TOO FEW" was wrong. The word is STANDS, not TOO FEW.
- **#687's exact rule did not replicate on this population** (`t20_entry_ref`: {REFS['t20_entry_ref']['delta_total']:+.2f}R, p = {REFS['t20_entry_ref']['p_weekblock']:.2f},
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

{t_main}

**Control (era E depth exit), n = {C['n']}:** best AOSL 2026-04-14 {C['best'][1]:+.2f}R, worst GLW 2026-07-09 {C['worst'][0]:+.2f}R, 0 losses beyond -1.5R, {C['giveback']} give-backs
(reached +1.5R, finished at or below 0). Its +4R winners: AOSL 04-14, BABA 07-08, BE 04-14, FTK 08-03, IONQ 04-14, RKLB 05-08, SGML 04-13, STM 04-23, TEAM 08-07
(a mark, still open), TXN 04-23. By entry month: Apr +43.27R (n = 45), May -11.19R (n = 62), Jun -8.84R (n = 13), Jul +3.34R (n = 24), Aug +17.69R (n = 41);
H1 +23.24R (n = 120), H2 +21.03R (n = 65).

### The primary in full (Frame A `t20_be`)

| measure | value |
|---|---|
| paired n / engaged n / differ n | {pr['paired_n']} / {pr['engaged_n']} / {pr['differ_n']} (the {pr['differ_n']} span {pr['differ_weeks']} entry weeks of {pr['n_blocks']}) |
| tail: +4R trades, arm vs control | {pr['n_tail']} ({100 * pr['n_tail'] / pr['paired_n']:.1f}%) vs {pr['n_tail_ctrl']} ({100 * pr['n_tail_ctrl'] / pr['paired_n']:.1f}%); +1.5R trades {pr['n_be']} vs {pr['n_be_ctrl']} |
| +4R winners lost / gained, by name | lost SGML 2026-04-13, TXN 2026-04-23, FTK 2026-08-03 / gained DOCN 2026-05-05, MSFT 2026-07-30 |
| p90 R; best trade | {pr['p90']:+.2f}; BABA 2026-07-08 at {pr['best'][1]:+.2f}R (the control's best is AOSL at {C['best'][1]:+.2f}R) |
| total R; mean R | {pr['total']:+.2f}; {pr['mean']:+.3f} (control {pr['ctrl_total']:+.2f}) |
| paired difference: total; per trade | {pr['delta_total']:+.2f}R; {pr['delta_mean']:+.3f}R, 95% week-clustered bootstrap interval {pr['boot_lo']:+.3f} to {pr['boot_hi']:+.3f} |
| week-block sign-flip p (5,000 draws, seed 1017, two-sided) | {pr['p_weekblock']:.4f} |
| own total without its two best trades | {pr['drop_best2']:+.2f}R (control {C['drop_best2']:+.2f}R) |
| paired difference without its two largest gains (BABA, DOCN) | {pr['delta_ex_top2']:+.2f}R; without BABA alone {pr['delta_total'] - 15.5777777777779:+.2f}R |
| top five gains, share of the paired total | BABA +15.58, DOCN +4.26, IONQ +3.66, MSFT +1.21, BE +0.87 = +25.57R = {100 * pr['top5_share']:.0f}% |
| by entry month, delta (n) | Apr {pr['by_month']['2026-04'][0]:+.2f} ({pr['by_month']['2026-04'][1]}), May {pr['by_month']['2026-05'][0]:+.2f} ({pr['by_month']['2026-05'][1]}), Jun {pr['by_month']['2026-06'][0]:+.2f} ({pr['by_month']['2026-06'][1]}), Jul {pr['by_month']['2026-07'][0]:+.2f} ({pr['by_month']['2026-07'][1]}), Aug {pr['by_month']['2026-08'][0]:+.2f} ({pr['by_month']['2026-08'][1]}) |
| by half, delta (n) | H1 {pr['h1']:+.2f} ({pr['h1_n']}); H2 {pr['h2']:+.2f} ({pr['h2_n']}) |
| capture (arm R / best close reached, ratio of sums) | {100 * pr['capture']:.1f}% (n = {pr['capture_n']} engaged trades with a positive best close) |
| costs | win {100 * pr['win']:.1f}% (identical to the control; descriptive only, an exit rule is not judged on it); median {pr['median']:+.3f}R; worst {pr['worst'][1]:+.2f}R; 0 losses beyond -1.5R; {pr['giveback']} give-backs; open at end {pr['open_data_end']} (control 12) |
| F (the stop held through the hold), engaged trades | above entry on **{pr['F_above_entry']} of {pr['engaged_n']}** (TXN 2026-04-23, F = +1.54 money-R); median F = {pr['F_median_R']:.2f}R; minimum {pr['F_min_R']:.2f}R |
| how the {pr['engaged_n']} end | primary: 8 time exits, 16 stopped at F, 5 still open; control: 13 close-below sales, 12 stop-hits, 4 still open |

**What the 29 look like:** 7 reached the partial on day 0, 22 later; 13 of the 29 are unchanged to within 0.005R (9 stopped out at the same +1.33R under both rules, i.e. the partial then
breakeven; 4 are the same still-open marks). The rule only matters on the other 16, and they split 5 up, 11 down:
BABA +15.58, DOCN +4.26, IONQ +3.66, MSFT +1.21, BE +0.87 against FTK -3.74, SGML -2.44, STM -2.34, RKLB -2.21, AOSL -2.04, RGTI -2.00, TXN -1.95, CRDO -1.07,
OKTA -0.55, FLEX -0.38, MRVL -0.17. Descriptive detail: `post_descriptive.out`.

## The pre-registered bar, applied mechanically to the primary

| # | condition | result | value |
|---|---|---|---|
| P1 | >= 10 trades differ AND >= 6 distinct entry weeks | **{V['P1']}** | {pr['differ_n']} trades, {pr['differ_weeks']} weeks |
| P2 | paired total > 0 AND week-block p < 0.05 | **{V['P2']}** | total {pr['delta_total']:+.2f}R, p = {pr['p_weekblock']:.3f} |
| P3 | still ahead without its two largest positive contributors | **{V['P3']}** | {pr['delta_ex_top2']:+.2f}R |
| P4 | ahead in BOTH halves | **{V['P4']}** | H1 {pr['h1']:+.2f}R (n = {pr['h1_n']}), H2 {pr['h2']:+.2f}R (n = {pr['h2_n']}) |
| P5 | +4R winners no fewer than the control's | **{V['P5']}** | {pr['n_tail']} vs {pr['n_tail_ctrl']} |
| P6 | orderable live | **{V['P6']}** | F >= entry at every trigger; the resting stop never stepped down in 4,268 walks (194 x 22) |

**Outcome (section 5, verbatim): STANDS (P1 holds, P2 to P5 fail).** The depth exit stands for the runner. The orderable form of the 09-29 `t20_be` lead does not
beat it, and `t20_be` is dropped as the named candidate. Whether #687's exact rule replicated is reported from `t20_entry_ref`, which is descriptive and cannot
produce a proposal. This window is not re-cut again. The tripwire stays armed on its trade arm (40 era-E live closes) and on the next exit-stack change.

## Reference rows (never candidates)

{t_ref}

- **`t20_entry_ref` (#687's exact rule, stop reset to entry at the trigger):** {REFS['t20_entry_ref']['delta_total']:+.2f}R in total, p = {REFS['t20_entry_ref']['p_weekblock']:.3f}, behind in H1
  ({REFS['t20_entry_ref']['h1']:+.2f}R), {REFS['t20_entry_ref']['delta_ex_top2']:+.2f}R without its two best, +4R winners {REFS['t20_entry_ref']['n_tail']} vs {REFS['t20_entry_ref']['n_tail_ctrl']}. It differs from the primary only on TXN
  (F was above entry there, and the reset to entry keeps the trade alive). **Not replicated at decision grade.**
- **`era_d` (the retired stop-on-the-line exit):** {REFS['era_d']['delta_total']:+.2f}R against the control over 62 differing trades (p = {REFS['era_d']['p_weekblock']:.2f}); +4R winners {REFS['era_d']['n_tail']} vs {REFS['era_d']['n_tail_ctrl']}.
  What the 10-12 switch did on this population: nothing detectable in money, three more +4R winners.
- **`control_at_close` (vehicle cost):** selling the 47 close-below exits at the deciding close instead of the next open would be {REFS['control_at_close']['delta_total']:+.2f}R better in total on this
  population (p = {REFS['control_at_close']['p_weekblock']:.2f}). The next-open sale is what shipped (mechanics study); this row only prices it.

## The other 21 arms (EXPLORATORY: cannot produce a proposal)

{t_exp}

- **None registers as the next primary:** no arm meets P1, P3, P4 and P5 together with an unadjusted p < 0.05 and a positive total.
- **Closest: Frame A `gb25_be`** (give back a quarter of the peak gain, then sell at the next open): {ARMS['A|gb25_be']['delta_total']:+.2f}R, unadjusted p = {ARMS['A|gb25_be']['p_weekblock']:.3f}, {ARMS['A|gb25_be']['delta_ex_top2']:+.2f}R
  without its two best, ahead in both halves ({ARMS['A|gb25_be']['h1']:+.2f} / {ARMS['A|gb25_be']['h2']:+.2f}). It fails P5: {ARMS['A|gb25_be']['n_tail']} winners at +4R against the control's {ARMS['A|gb25_be']['n_tail_ctrl']} (loses TXN and
  TEAM, gains NVTS; TEAM is itself a position still open at the data end). One arm in 21 under p < 0.05 is what chance gives (expected about one), so this is a
  lead to remember, not one to act on, and by the pre-registered rule it is not registered.
- **Frame B expectation (written before the data):** "wrong if any Frame B rule shows a paired gain above +0.2R a trade with p under 0.01 in both halves." **It holds, none does.**
  The best Frame B arm is `t5_be` (hold 5 sessions after the +3 ORB-R arm): {ARMS['B|t5_be']['delta_total']:+.2f}R ({ARMS['B|t5_be']['delta_mean']:+.3f}R a trade, interval {ARMS['B|t5_be']['boot_lo']:+.3f} to {ARMS['B|t5_be']['boot_hi']:+.3f}, p = {ARMS['B|t5_be']['p_weekblock']:.3f}).
  It clears P3, P4 and P5 ({ARMS['B|t5_be']['delta_ex_top2']:+.2f}R without its two largest gains COHR and LITE; ahead in both halves; {ARMS['B|t5_be']['n_tail']} winners at +4R vs {ARMS['B|t5_be']['n_tail_ctrl']}) and fails only significance, so it is the one Frame B lead to carry. By the
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
  86 (#685); here {pr['engaged_n']} of {pr['paired_n']} did. The paired differences are conditional on this runner mix.
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
"""

open(OUT, "w").write(DOC)
print("wrote", OUT, len(DOC.splitlines()), "lines")
