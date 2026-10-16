# Runner-rule re-cut against the depth exit: pre-registration (2026-10-16)

**Status: PRE-REGISTRATION ONLY. Written before any number was computed under the depth control.**
Nothing was run, changed or deployed, and there were no prod reads. The replay runs **Saturday 2026-10-17**
(after the Friday 8 PM PT capacity reset), using the commands in §9. This file fixes the population, the
control, the candidates, the measures and the decision bar before then. The results go in a separate
document (`docs/analysis/runner_recut_2026-10-17.md`), and that document may not change anything written
here. Any change has to be recorded there as a dated deviation. Standard:
`docs/methodology/analysis_standard.md`. The Saturday card prompt carries
`docs/methodology/ANALYSIS_CARD_PREAMBLE.md` verbatim (standard §0).

**Owed by:** `data_gated_reviews.yaml` → `runner_rule_sweep_recut`, 🔔 FIRED 2026-10-13. The tripwire's
rule-toggle arm fired (45 = 5 era-D live closes + 40 × one toggle). The toggle was `magna53_depth_exit|live`,
switched on 2026-10-12 at 09:39:01 ET (`scripts/probes/_runner_recut_1013/what_fired.out`); its first acting
session was Tue 2026-10-13. This is the exit-stack change that the entry says makes the last read stale. It
does not just make it thin. PLAN #687 carries the re-cut for the weekend of 10-17/18.

**Units, once.** Every outcome is in **money-R** = profit ÷ (entry − placed stop). The placed stop is
2 ORB-R under entry, so 1 money-R = 2 ORB-R. Live states its levels in ORB-R:
- the partial at "+8R" is **+4.0 money-R**;
- the breakeven arm at "+3R" is **+1.5 money-R**.

The tail threshold below, "+4.0 money-R", is the partial's own level. It is also the preamble's "4R+".

---

## §0 · The decision this serves

1. **Decision:** should a looser rule replace the depth exit for the part of a MAGNA53 position that is
   already working? The depth exit has been live since the 10-13 session. "The depth exit stays" is a real
   answer.
2. **What would change it:** one candidate rule beating the depth control on this population by enough to
   clear every condition in §5. That means more money in total, still ahead without its two best trades,
   ahead in both halves of the window, no fewer +4R winners, and a week-block p under 0.05.
3. **Population:** run 1's Run-U backtest population, replayed from stored bars (§1). It is not live trades:
   no depth-stamped trade has closed yet. The 10-15 capture shows 0 trades created since 10-12
   (`scripts/probes/_624_hb_1015/q1.out`).
4. **What would make it wrong:** §7. The big four are: an admission era that is not today's, outcomes
   concentrated in two trend months of semiconductors, daily-bar resolution after day 0, and positions still
   open when the bar data ends.

**Memory rules applied:**
- *Entries/exits undetermined for new setups:* NOT applicable. MAGNA53 is the live setup with a defined
  buy (stop-limit at the ORB high) and stop (entry − 2 ORB-R).
- *Measure the tail, not the median:* tail columns come first and are a pass condition (§4, §5).
- *Check the rule era:* the control is era E and only era E. The 08-29 control (+2R partial, breakeven
  after) and the era-D control (stop resting on the line) are both gone. They appear only as labelled
  reference rows.

## §1 · Method and population

**Population: Run U from `docs/analysis/ep_backtest_run1_2026-08-29.md`, reproduced from the same
captures.** The data comes from `/Users/alvinfung/.claude/jobs/6b173ac9/tmp/`:
- `bt_admission_result.json` → `U.replayable`: 295 rows on 252 tickers;
- `bt_out_bars.psv`: day-0 minute bars;
- `bt_out_daily.psv`: daily OHLC, 2026-02-20 → 2026-08-28.

**Entries run 2026-04-13 → 2026-08-28.** Under the 08-29 bracket, 194 of the 295 filled and were scored, 85
never triggered and 16 had no usable bars. The fill model has not changed. The scored count under the era-E
control can differ slightly, because the shared walker abstains on some same-bar orderings that the 08-29
harness resolved stop-first. The count is reported, not forced to 194.

**The inputs are machine-local and not committed.** Their sha256 hashes are pinned now in
`scripts/probes/_runner_recut_1017/input_hashes.sha256` (step 1 in §9 checks them):

| file | sha256 (first 16 hex digits) |
|---|---|
| `bt_admission_result.json` | `60febea3b5e3c87a` |
| `bt_out_bars.psv` | `7711e94e742ba235` |
| `bt_out_daily.psv` | `af539500c7ef13c9` |
| `bt_out_cov.psv` | `b351b1bfdae078bc` |
| 08-29 sweep outputs (`runner_sweep_results.json`, `runner_sweep_rows.tsv`, `runner_sweep_stdout.txt`) | `5d1c5666…`, `cb2936d6…`, `16663c02…` |

**Era:**
- **Admission is the 2026-08-29 manifest.** This is Run U's catalyst-generous arm: every name gets the
  strong-catalyst score, the judge is OFF, the 50% extension cap applies, and the sustain / RVOL /
  pre-market-share gates are not modeled.
- **The exit is era E** (§2).
- **This exact combination never traded live.** Admission has moved since 08-29: within-day slot ranking by
  RS (08-30), theme bonus keyed on belonging (09-13), the M&A-target filter rewrite (#692, 10-02/03), and the
  shortlist ranking on last night's volume (#694, 10-10). None of those touches an exit. Because the design
  is paired, an admission shift moves the levels more than the rule-versus-rule differences. Even so, those
  differences are measured on this cohort's mix of runners.

**What it is NOT:**
- not today's admission;
- not our live alerts or trades;
- not the era-E live book (empty);
- not #687's rebuilt 2024-01 → 2026-04 list of 1,505 trades;
- not #685's 79 real EPs.

Run U over-admits. On the 08-29 mechanism check, 08-28 had 5 names modeled against 1 actual. Recall is not
measured here, because every arm trades the identical names. The preamble's first ranking criterion is
therefore fixed by construction. It is stated here, not assumed.

**Bars after day 0 (pre-registered choice):**
- **Read of record:** the captured daily bars, plus ONE read-only pull of `mi_daily_closes` for the 252
  tickers, 2026-02-20 → 2026-10-16 (§9 step 3). This lets positions that were still open at 08-28 settle.
- **Overlap check:** the pull's overlap with the capture is checked per ticker. For any ticker that
  disagrees by more than 0.5% on any close in the overlap (e.g. re-adjusted for a later split), the
  extension is not used, and the ticker is listed.
- **Fallback:** if the pull is refused or fails, the read of record is the capture alone. Every position
  still open at 08-28 is marked at its last stored close, and the count of marked positions is reported per
  arm as a stated limit.

## §2 · The control, exactly as live (era E, MAGNA53, live account)

Read from code and committed prod captures on 2026-10-16, not from prose.

⚠ `docs/setups/exit_discipline.md` §"Current deployed behaviour" still says "breakeven arm OFF" and "depth
OFF". Both are stale: the 10-11 prod capture `scripts/probes/_wk1011_depth_era/q1_state.out` shows
`magna53 profit_trigger_r 8.0 / breakeven_arm_r 3.0`, and the depth toggle went on 10-12. **Fix that header
before the run** (standard §3b: drift is fixed before the analysis, not after).

| element | live rule | source |
|---|---|---|
| entry | stop-limit buy at the 09:30 bar's high; fills 09:31–09:59, otherwise no trade (frozen from Run U) | `_bt_replay._fill_entry`; magna53_ep.md 2026-08-16 |
| hard stop | entry − 2 ORB-R (= 2·ORB low − ORB high); ORB-R = entry − ORB low | `rule_eras` STOP_2R; order_manager |
| breakeven arm | stop to entry the first time price trades at entry + 3 ORB-R (+1.5 money-R), whether or not a partial fired | `rule_eras.BREAKEVEN_ARM_R_VALUE = 3.0`; prod `mi_strategies` |
| partial | 1/3 sold at entry + 8 ORB-R (+4.0 money-R) on the touch; the stop folds to entry | `rule_eras.PARTIAL_8R_VALUE = 8.0`; prod |
| trail line | max(SMA10, SMA20) of the stock's own closes, including today's close; decided at 16:45, from session 1 (never on the entry day) | `exit_logic.apply_daily_exit_step` (#548) |
| depth resting stop | max(hard stop, entry once breakeven is armed, line × (1 − ADR20)); ADR20 = mean (high − low)/close of the ≤ 20 sessions before entry, at least 10 required, otherwise the floor; raise-only | `exit_logic.depth_stop_price`, `adr20_pct_from_bars` |
| close below the line | the whole remainder sells at the **NEXT session's open** (live: opening-auction order sent 19:01 ET) | `walk_arm(depth_exit=True)`; #687 mechanics |
| horizon | 40 sessions after the fill day; still open → marked at the 40th close | `live_fill_counterfactuals.HORIZON_SESSIONS = 40` |

**The instrument is the live mirror, not a new walker.** The control is
`live_fill_counterfactuals.walk_arm(harvest="live_ladder", trail_mode="sma", target=entry+8·R_orb,
breakeven_at_r=3.0, r_frame_ps=R_orb, breakeven_at_partial=True, trail_prior_closes=True,
ladder_partial=False, horizon=40, depth_exit=True, depth_adr20_pct=ADR20)`. The 16:45 job calls the same
pure functions, and `tests/test_depth_exit_rule.py` pins the walker to them. The code is pinned at HEAD
`d4a7b8d2`, git blob hashes:
- `live_fill_counterfactuals.py` `e9098c36`
- `exit_logic.py` `d5597612`
- `_bt_replay.py` `727d5f84`
- `_runner_sweep.py` `57e4e246`

The deviations the walker states for itself are inherited and named: the next open is the daily bar's open,
and the ratchet raises on any higher stop where live requires more than 1 cent.

**The task text's "sell at the close if it closes below the line" is the superseded 09-29 wording.** The
mechanics study moved the sale to the next morning's opening auction, and that is what shipped. The control
sells at the next open. A sensitivity row prices the same sale at the deciding close (the vehicle cost); it
is not a candidate.

## §3 · The candidate rules, derived from the 08-29 set

**Derivation.** The 08-29 sweep varied only the stop on the 2/3 left after the +2R partial. Its rules were:
hard, sma10, sma20, live_trail_be, atr1, atr2, gb25, gb50, t3, t5, t10, t20 (plus two touch-sensitivity
variants).

**Dropped, with reasons:**
- **`live_trail_be`** (close below max(SMA10, SMA20), floor at entry) is NOT the era-E control. The depth
  rule adds a resting stop one ADR under the line. Without that stop, `live_trail_be` is the depth rule's
  looser sibling, "close-only" in #687's terms, so it stays as the candidate `close_only`.
- **`hard` and every `_hs` form:** the stop is already at entry by the time any runner rule takes over
  (3 ORB-R comes before 8 ORB-R). Stepping it down is not orderable under the raise-only stop. #687 excluded
  them for the same reason.
- **The touch variants:** they were error bars, not rules.

**Eleven rules, orderable forms only.** F = the stop resting at the trigger, at least entry; raise-only from
there.

| rule | governs the open remainder after the trigger by | sale priced at |
|---|---|---|
| `t3_be` `t5_be` `t10_be` `t20_be` | hold N sessions after the trigger session (which is session 0) and sell at the Nth session's close; stop F rests meanwhile; no line | the Nth close (a market-on-close order is orderable because the date is known in advance); touch of F at F, or at the open on a gap |
| `close_only` | close below max(SMA10, SMA20) → sell; only F rests (no depth stop) | next open |
| `sma10_depth` / `sma20_depth` | the depth rule on a single line (SMA10 alone / SMA20 alone) in place of the max of both | next open; depth-stop touch at the level, or at the open on a gap |
| `atr1_be` / `atr2_be` | chandelier: rest at max(F, peak close through the prior session − k × ATR14 at entry); no line | the level, or the open on a gap |
| `gb25_be` / `gb50_be` | close below entry + keep × (peak held close − entry), keep 0.75 / 0.50 → sell; F rests; no line | next open |

**Two frames.** Every rule runs in both.
- **Frame A: after the +8 ORB-R partial (the tripwire's literal question).** The trigger is the bar on which
  the 1/3 partial books. From there the rule governs the 2/3 left. **This frame answers
  `runner_rule_sweep_recut`.**
- **Frame B: from the +3 ORB-R breakeven arm.** The trigger is the bar on which the stop first reaches entry.
  This is the moment that played the 08-29 control's breakeven role. From there the rule governs the whole
  open position, and the +8R partial still books its 1/3 at the target when touched, as live. Frame B
  engages more trades, but it asks a different question (an alternative to the depth trail once a trade is
  free of risk). **It is exploratory only.**

**On the trigger bar itself, the candidate's close decision replaces the control's.** Before the trigger,
every candidate is the control by construction (gate G3, §8).

**ONE pre-registered primary: Frame A `t20_be`, in its ORDERABLE form.** Hold 20 sessions after the
partial, with the stop held at F, where F = max(the depth stop resting at the trigger, entry). This form
differs from #687's rule. By +8 ORB-R the depth stop has usually ratcheted above entry, and the raise-only
stop cannot step back down, so F can sit above entry and can end the hold before session 20. The results doc
reports how many engaged trades have F above entry at the trigger, and the median F in R.

It led both earlier reads:
- 08-29 (this population, +2R control): +0.36R a trade vs +0.14R, not significant;
- #687 backfill (the rebuilt list, era-D control): +73.5R on 217 partial-takers, p ≈ 0.066.

The 687 doc's own proposal named it as the candidate this review should test. Its discovery list
(2024-01 → 2026-04-30) overlaps Run U only from 04-13 to 04-30, so Run U is nearly out of sample for it.
The other 21 arms are exploratory.

**Reference rows (never candidates):**
- `t20_entry_ref`: #687's exact T20_be. At the trigger the stop is reset to entry (`scripts/probes/_687/
  backfill.py`, `floor = entry`), which is a step down whenever F > entry, so it is NOT orderable under the
  raise-only stop. It answers a separate question: did #687's exact rule replicate on Run U? The primary
  answers whether the orderable form beats the depth exit.
- `era_d`: the same walker with `depth_exit=False`, the retired stop resting on the line. It shows what the
  switch did on this population.
- `control_at_close`: the vehicle-cost sensitivity.

## §4 · Measures: tail first, then money, then median

Every arm is paired with the control on the trades both settle or mark.

1. **n:** paired n, engaged n (trades where the frame's trigger fired), and differ n (trades where the arm
   and the control differ by more than 0.005R). Also abstains and marks per arm.
2. **The tail (first):**
   - number and share of trades whose whole position made at least +4.0 money-R (the +8R partial's level);
   - the same at +1.5 money-R;
   - p90 of R;
   - the best trade, named;
   - **+4R winners lost or gained against the control, by name.**
3. **Money:** total R, mean R per trade, the paired difference against the control (total and per trade).
4. **Median R** (descriptive; not a pass condition).
5. **Concentration:**
   - the arm's own total minus its two best trades ("drop-best-2", #687's measure);
   - the paired difference without its two largest positive contributors;
   - the share of the paired difference carried by the top five trades, with their names.
6. **Time:**
   - the paired difference by entry month (Apr, May, Jun, Jul, Aug, n on each);
   - by fixed half: **H1 = entries 04-13 → 06-30, H2 = 07-01 → 08-28**. Each half holds one trend month,
     April in H1 and July in H2.
7. **Separation:**
   - week-block sign-flip permutation on the paired total (blocks = ISO week of entry, 5,000 draws, seed
     1017, two-sided, p = (hits + 1)/(draws + 1));
   - a week-clustered bootstrap 95% CI of the mean paired difference (10,000 resamples, seed 1017).
8. **Capture** (descriptive): on engaged trades, the arm's R as a share of the best close reached within the
   horizon, in R.
9. **Costs, described and never ranked:**
   - win rate (an exit rule cannot control it — preamble, "which layer owns it");
   - worst trade;
   - losses beyond −1.5R;
   - give-backs (trades that reached +1.5 money-R and finished at or below 0);
   - positions still open at the horizon / at the data end.

**Result tables, laid out now and filled in Saturday (no number exists yet):**

| frame | rule | paired n | engaged n | differ n | +4R trades (share) | +1.5R trades | p90 R | total R | mean R | Δ vs control | Δ without top 2 | drop-best-2 | H1 Δ / H2 Δ | p (week-block) | median R | win % | open at end |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| — | control (depth) | pending | — | — | pending | pending | pending | pending | pending | — | — | pending | — | — | pending | pending | pending |
| A | **t20_be (PRIMARY)** | pending | pending | pending | pending | pending | pending | pending | pending | pending | pending | pending | pending | pending | pending | pending | pending |
| A, B | the other 21 arms | pending | pending | pending | pending | pending | pending | pending | pending | pending | pending | pending | pending | pending | pending | pending | pending |
| ref | t20_entry_ref · era_d · control_at_close | pending | — | pending | pending | pending | pending | pending | pending | pending | — | — | — | — | pending | pending | pending |

## §5 · The decision bar, written before any number

**PROPOSAL.** A CHANGE_PROCESS proposal goes to him if, and only if, the **primary (Frame A `t20_be`)**
meets ALL of the following on the read of record:

| # | condition | why |
|---|---|---|
| P1 | at least **10** trades differ from the control **and** they span at least **6** distinct entry weeks | CHANGE_PROCESS N ≥ 10. With fewer than 6 weeks, a week-block p under 0.05 cannot be reached at all. |
| P2 | paired total > 0 **and** week-block p < 0.05 | one pre-named test, so no multiplicity correction |
| P3 | still ahead without its two largest positive contributors | not two names |
| P4 | ahead in **both** H1 and H2 | not one trend month |
| P5 | its count of trades at +4.0 money-R or more is **no lower** than the control's | the tail is the edge, so a rule may not buy money by losing big winners |
| P6 | orderable live | true by construction (stop at or above entry, raise-only; market-on-close sale) |

**The three possible outcomes for the primary:**
- **PROPOSAL** (P1–P6 all hold): the results doc carries a CHANGE_PROCESS proposal for his ruling. Nothing
  is flipped.
- **TOO FEW** (P1 fails): Run U cannot answer the runner question under the +8R partial. The re-cut owed by
  the 10-13 firing is then answered with "too few to judge", and there is no verdict either way. The
  tripwire stays armed on its trade arm (40 era-E live closes) and on the next exit-stack change. This window
  is not re-cut again.
- **STANDS** (P1 holds, any of P2–P5 fails): the depth exit stands for the runner. The orderable form of
  the 09-29 t20_be lead does not beat it, and t20_be is dropped as the named candidate. Whether #687's exact
  rule replicated is reported from `t20_entry_ref`, which is descriptive and cannot produce a proposal.
  This window is not re-cut again.

**EXPLORATORY.** The other 21 arms (Frame A's other 10, all of Frame B) cannot produce a proposal from this
read. At most ONE of them is **registered as the next primary**: the arm with the largest paired total among
those that meet P1, P3, P4 and P5 with an unadjusted p < 0.05. Its confirmation population is named now:
#687's rebuilt list (2024-01 → 2026-04-12, i.e. excluding the overlap with Run U), re-walked under the depth
control, and pre-registered separately before it is run. That list never ran Frame B. Expect about one false
lead in 21 arms at p < 0.05.

**Expectation, written before the data** (CLAUDE.md pre-registration):
- **Frame A:** the most likely outcome is TOO FEW. The published rates imply roughly 2–29 of about 194
  filled trades reach +8 ORB-R: real EPs did so 1 time in 86 (#685), the rebuilt list 15% of the time
  (#687).
- **Frame B:** looser rules gain less than they did on 08-29, because the depth trail already lets winners
  run above entry, unlike the old breakeven scratch. The median cost is about the same, and nothing
  separates. My expectation is wrong if any Frame B rule shows a paired gain above +0.2R a trade with p
  under 0.01 in both halves.

**What a broken run would show (WOULD-FAIL-IF):**
- **A depth stop that never engaged would still differ from `era_d`.** Both rules sell on a close below the
  line; era D sells AT the line on a touch and depth sells at the next open. The two would therefore differ
  on every line-test trade even if ADR20 were missing everywhere, so "differs from era D" proves nothing.
  **G2b instead requires positive evidence:** the ADR20 census (how many are None), at least one session
  where the binding resting stop is line × (1 − ADR20) and not the floor, and at least one close-below
  sale priced at a next open that differs from its deciding close.
- If the extension did not attach, the open-at-end count would not fall between the capture-only run and the
  extended run. **G-ext requires it to fall.**

## §6 · Inherited reads, so the result is read against them (not new numbers)

| read | population | n | control | runner result |
|---|---|---|---|---|
| 08-29 sweep | Run U (this one) | 194 | +2R partial, breakeven after (retired) | every looser rule ahead on the mean; best t20 +0.36R vs +0.14R a trade; no CI excludes 0 |
| #687 backfill, runner table | rebuilt list 2024-01 → 2026-04 | 217 partial-takers of 1,505 | era D (stop resting on the line) | T20_be +73.5R (p ≈ 0.066), ahead in both blocks; best of four |
| #687 backfill, trail table | the same | 1,505 | era D | depth +29.5R vs era D (p 0.33), +0.12R without BE and HL |

## §7 · Known biases

1. **Admission era:** the 08-29 manifest, with over-admission in Run U (§1). Not today's admission. The
   paired differences are conditional on this runner mix.
2. **Regime and concentration:** 20 weeks. April and July (semiconductors) carried every 08-29 rule, and May
   and June were negative under every rule. The halves, the month table and the top-five share address this.
   They do not remove it.
3. **Daily bars after day 0:**
   - Only day-0 minute bars are stored. The depth-stop touch, the +8R target and the +3R arm are resolved
     on daily high/low after that.
   - Same-day ambiguities abstain (the walker's own rules, never guessed). Abstains can differ by arm, so
     each arm's paired n is reported.
4. **Fill pricing:**
   - entry at exactly the ORB high (no slippage);
   - touch exits at the level, or at the open on a gap;
   - next-open sales at the daily bar's open;
   - the partial and the breakeven arm fire on the bar's touch, where live polls every 5 minutes.
5. **The resting profit-take third:** live rests an OCO limit at the +8R target and can leave the third
   unfilled if price falls back. That third keeps its own target and breakeven stop through a close-below
   sale (ruling 3, 09-29). The replay fills the third on the touch. This is a rare case, and it is not
   modeled.
6. **One fractional share:** live rounds to whole shares (a 2-share position sells 1 at +8R; a 1-share
   position sells nothing). Small positions differ.
7. **Marks:** 40-session horizon. Positions are marked at the 40th close or at the data end. Marks sit in the
   tail, and the hold-longer rules carry more of them (08-29: 16 for t20, 24 for the control). Counted per
   arm. The extension reduces them.
8. **Coverage:** the 16 no-bars rows (5.4%) are excluded, and they are probably bad outcomes. That flatters
   the level, equally in every arm. New gaps in the extension block the walk and are counted.
9. **No portfolio:** the max-5 positions, the 2% daily loss limit and the breakers are not modeled. A
   lower-win-rate rule interacts with the 10-loss count breaker, and that interaction is unmeasured.
10. **I have seen this population's 08-29 results and the #687 runner table.** The candidate list is not
    blind, which is why there is one pre-named primary and everything else is exploratory.
11. **Inputs for the indicators:** ADR20 and ATR14 come from the capture's daily history, which starts
    2026-02-20, so April entries have at least 35 prior sessions. P 05-11 (an IPO) has fewer than 20 prior
    closes, so the SMA20 None-guard applies and ADR20 may abstain to the floor, as live.

## §8 · Build spec for `scripts/probes/_runner_recut_1017/recut.py`

The script is built Saturday, before any population run. It prints no outcome total until `--run`.

- **Loaders:** copied from `_runner_sweep.py` (minute bars, daily rows, the global session calendar),
  reading the gzipped copies made in §9 step 1, plus the extension merge (per-ticker overlap check).
- **Per trade:**
  - ORB = the 09:30 bar; fill = `_bt_replay._fill_entry` on 09:31–09:59; entry = ORB high;
    stop = 2·ORB low − ORB high; R_orb = entry − ORB low;
  - target = entry + 8·R_orb; breakeven trigger = entry + 3·R_orb;
  - day-0 bars = 09:31 → close as `{m,o,h,l,c}` with `fill_idx`;
  - sessions = the next 40 global sessions after the entry date (None where missing);
  - prior closes = closes in [entry − 40 calendar days, entry − 1];
  - ADR20 = `adr20_pct_from_bars(last 20 sessions before entry)`;
  - ATR14 = `_runner_sweep.atr14_abs`.
- **Control:** `walk_arm(...)` as in §2. R = pnl ÷ (entry − stop). `horizon` → the walker's mark. Still
  open at the data end → marked at the last stored close and flagged.
- **Candidates:** a frozen copy of `walk_arm` (cite blob `e9098c36`) with ONE hook at the trigger bar.
- **Gates (all STOP on failure; none prints a total):**
  - **G1:** the 08-29 sweep reproduces (§9 step 2). The STOP condition is a difference in its stdout:
    the GATE PASS line and every table. A byte difference in the rewritten JSON/TSV while the stdout is
    identical (float repr or ordering under another interpreter) is logged and investigated, not a halt.
  - **G2:** the frozen copy with rule = control equals `walk_arm` on every row (status, reason, every exit
    leg to 1e-9).
  - **G2b (positive engagement):**
    - the ADR20 census (count of None);
    - at least one session whose binding resting stop is line × (1 − ADR20), not the floor;
    - at least one close-below sale priced at a next open that differs from its deciding close.

    The count of depth-stop sales is reported, not gated.
  - **G3:** each candidate equals the control on every trade whose trigger never fired, and its legs booked
    before the trigger equal the control's on every trade where it did.
  - **G-ext:** the extension passes the overlap check per ticker (failures listed), and the open-at-end count
    falls compared with the capture-only gate pass.
- **Self-tests (synthetic bars):** one per rule (trigger fires → the rule's exit and price); a no-trigger
  identity test; a next-open pricing test; a gap-through test; and a mutation that applies a candidate
  before the trigger, which must turn G3 red.
- **Hand-trace:** two trades end to end from the raw bars. One is a depth next-open sale; the other is a
  +8R partial followed by a t20 exit. Both are picked mechanically: the FIRST trade in entry order that
  shows each event. There is no cherry-picking.

## §9 · Saturday commands (2026-10-17, in order; no deploys, no subagents, captures to `.out`)

⚠ **Run this on THIS Mac.** The inputs exist only in its `~/.claude/jobs/6b173ac9/tmp/` until step 1 copies
them into the repo. On any other machine, step 1 fails, and the right response is to stop, not to
re-derive the population.

```bash
cd /Users/alvinfung/apollo_the_wise
P=scripts/probes/_runner_recut_1017; T=/Users/alvinfung/.claude/jobs/6b173ac9/tmp
# 0. state: the control must still be era E (any exit-stack drift since 10-16 -> STOP and re-register).
#    Its prod read is read-only; if it is refused, use --no-prod and confirm era E from
#    rule_eras.DEPTH_EXIT_LIVE_DATE plus the absence of any exit change-log entry after 10-16.
.venv/bin/python scripts/live_rules.py --drift-only > $P/live_rules_drift_1017.out 2>&1
# 1. inputs unchanged since this pre-registration, then copy them into the repo
shasum -a 256 -c $P/input_hashes.sha256 > $P/g0_hashes.out 2>&1      # all OK, else STOP
mkdir -p $P/captures
for f in bt_admission_result.json bt_out_bars.psv bt_out_daily.psv bt_out_cov.psv \
         runner_sweep_results.json runner_sweep_rows.tsv runner_sweep_stdout.txt; do
  gzip -c $T/$f > $P/captures/$f.gz; done
# 2. G1: the 08-29 sweep reproduces. STOP = any stdout difference (g1 diff exit != 0). The script rewrites
#    its JSON/TSV in $T (originals already saved in $P/captures); a hash change there with identical
#    stdout is logged and investigated, not a halt.
.venv/bin/python scripts/probes/_runner_sweep.py > $P/g1_sweep_repro.out 2>&1
diff $P/g1_sweep_repro.out $T/runner_sweep_stdout.txt > $P/g1_diff.out; echo "g1 diff exit $?" >> $P/g1_diff.out
shasum -a 256 -c $P/input_hashes.sha256 > $P/g1_hashes.out 2>&1
# 3. the ONE optional prod read (read-only). If the permission system refuses: do NOT retry or route
#    around it; skip --ext below and report the marks per arm as a stated limit.
scp -q $P/pull_daily_ext.sql apollo@87.99.134.162:/tmp/cwp_runner_recut_daily.sql
ssh -o BatchMode=yes -o ConnectTimeout=25 apollo@87.99.134.162 \
  'docker exec -i apollo-postgres psql -q -U apollo -d apollo -t -A -v ON_ERROR_STOP=1 < /tmp/cwp_runner_recut_daily.sql' \
  > $P/pull_daily_ext.out 2> $P/pull_daily_ext.err
date -u +"pulled_at_utc=%Y-%m-%dT%H:%M:%SZ" > $P/pull_daily_ext.pulled_at
# 4. build recut.py to §8, synthetic self-tests only
.venv/bin/python $P/recut.py --selftest > $P/selftest.out 2>&1
# 5. gates on the real population (G2, G2b, G3, G-ext; prints no totals)
.venv/bin/python $P/recut.py --gate --ext > $P/gate.out 2>&1          # drop --ext if step 3 failed
# 6. THE run, once (read of record)
.venv/bin/python $P/recut.py --run --ext > $P/run.out 2>&1            # drop --ext if step 3 failed
.venv/bin/python $P/recut.py --trace > $P/handtrace.out 2>&1
# 7. write docs/analysis/runner_recut_2026-10-17.md (outcome = §5's bar, verbatim), then gate it
.venv/bin/python scripts/check_analysis_doc.py docs/analysis/runner_recut_2026-10-17.md
```

- **Step 8:** record the outcome under the 🔔 FIRED note in `data_gated_reviews.yaml` →
  `runner_rule_sweep_recut`, including which arm fired, the toggle, and the result word: PROPOSAL / TOO FEW /
  STANDS.
- **Step 9:** add the #687 PLAN line's next sentence.
- **The session commits; the card does not push.** The extension SQL was generated by
  `$P/make_ext_sql.py` (output `$P/make_ext_sql.out`; it read the 252 ticker symbols only).

## What this does not answer

- **Whether any of this transfers to the EPs we actually trade.** Run U over-admits. Real EPs reached the +8R
  partial 1 time in 86 (#685), so a Frame A answer may describe a cohort the live book rarely produces.
- **The live era-E record:** nothing has closed under the depth exit yet. The tripwire's trade arm (40 era-E
  live closes) is the forward check, at roughly a year at today's rate.
- **Portfolio effects:** breakers, the daily loss limit, max-5, whole-share sizing, and how a lower win rate
  sits with the count breaker.
- **Anything upstream of the trigger:** entries, admission, the +8R partial level, the +3R arm and the depth
  distance (1 ADR, fixed; #687 forbids re-tuning it) are all frozen.
- **Hybrids outside the eleven rules:** regime-switched rules, partial ladders, re-entries.

## ⚖ THE LINE

Exit discipline is the operator's sole authority. This document runs nothing, changes nothing and proposes
no change. The bar in §5 decides only whether a proposal is brought to him at all. Any proposal goes through
CHANGE_PROCESS (SSoT read, his sign-off, verify-live), and a catastrophic stop always rests at the broker.
