# #720 — the monthly trade review: PRE-REGISTERED plan (written 2026-11-08, before any outcome row of the first window was read; revised the same day against the 11-08 challenge, still before any read)

**What this is.** The fixed plan the monthly comprehensive trade review runs on — the first run is Sun 2026-11-29.
On run day the runner (`scripts/probes/_720_monthly/run_review.py`) captures the data once, computes every
number from this plan, and renders the one page. Nothing in this file is tuned to the data: at the time of
writing no closed-trade outcome of the first window was read beyond what the 11-06 read already published
(`docs/analysis/482_cross_arm_read_2026-11-06.md`), and that is listed under "seen before this was written".

**The 11-08 revision.** A challenge of the first draft found three lenses on wrong units or the wrong test, a
ladder no arm could climb, and several promised sections not built. Every finding is fixed here and in the
runner; the forks the challenge raised were decided by the main loop and are written into §8 as **D1–D7** —
none went to the operator. The test fixtures were moved to the units prod writes.

**What it is not.** The review PROPOSES. Any entry / stop / sizing / partial / exit change goes through
`docs/setups/CHANGE_PROCESS.md` (N ≥ 10, backtest, the change-log fields) and his sign-off — THE LINE. A
verdict here of PROPOSE means "worth writing a CHANGE_PROCESS proposal", never "change it".

**His ruling (2026-11-06):** *"this should just be part of normal periodic review and we review trades to find
areas to improve on in our setup and strategy which should be comprehensive and includes buy/stop/partial
analysis."* One review, every closed trade, five lenses, tail first, one page.

---

## 1. Population

### 1.1 Which trades

- **Identity:** `mi_live_trades.id` (the `trade_id` every recorder keys on), shown with `ticker`,
  `alert_date`, `account_mode`, `signal_type`. `(ticker, alert_date, account_mode)` is unique on the table.
- **Closed:** `status = 'closed'` with a `closed_at`.
- **In the window:** the ET date of `closed_at` is after the previous run's capture and on or before the run
  date. A trade opened before the window and closed inside it belongs to this review; one still open belongs to
  the next. The capture timestamp of each run is written to `scripts/probes/_720_monthly/runs/<date>/MANIFEST.txt`
  and is the next run's lower bound.
- **First window (D3):** trades FILLED on/after **2026-08-16** ET (the day the entry−2R stop went live = era C
  start = the counterfactual recorder's `BACKFILL_FROM`; the capture's own filter) and closed by the run date.
  Why that far back: the review has never run, the stop geometry has been one rule since then, and the 11-06 read
  covered only the arm comparison on 20 of these trades — the buy-point / partial / exit / tail reads of this plan
  are new on every one of them. The 20 fills the 11-06 read scored are flagged `read 11-06 = yes` on the per-trade
  list so nothing is re-counted as new evidence.
- **Pre-window fills closed in a window:** a trade filled before 08-16 and closed on/after it ran under the era-B
  stop and is NOT in the capture. `pre_window_closes.sql` COUNTS them per lane and the page prints the count, so
  "every trade accounted for" is not true on paper and false in fact.
- **Legacy table check:** `mi_paper_trades` (the pre-#66 paper table) rows with `closed_at` in the window are
  COUNTED and reported (expected 0). A non-zero count is reported, not read.

### 1.2 Lanes — never pooled with each other

| Lane | Filter | Recorder arms? | Since |
|---|---|---|---|
| **L1 live EP** | `account_mode='live' AND signal_type='magna53'` | yes (`mi_live_fill_counterfactuals`, all arms) | 2026-08-16 |
| **L2 small-cap paper EP** | `account_mode='paper' AND signal_type='magna53_smallcap'` | **no** — the recorder's query is `signal_type = 'magna53'` exactly (`db.get_counterfactual_fills`) | 2026-10-10 (#624) |
| **L3 breakout v1 paper** | `account_mode='paper' AND signal_type='breakout_v1'` (rows carry `exit_rule='breakout_pp'`) | **no** | 2026-10-31 deploy; paper buys only after his go (#717) |
| **L4 other paper** | `account_mode='paper'` and any other `signal_type` (e.g. a paper magna53 row, retired lanes) | magna53 paper rows: yes; others: no | — |

L2 and L3 get the stop / partials / exits lenses from the trade row, its `exits` legs and
`mi_sell_discipline_records` only (that recorder covers every account mode). L4 is counted and listed, not read.

### 1.3 Eras — from the row, never re-derived from a date, never pooled

- **L1, L2, L4-magna53:** `rule_eras.exit_era_label(alert_date, signal_type, exit_rule=row.exit_rule)`.
  Today that gives C (entry−2R stop, +2R partial; 08-16..09-05), D (+8R partial, breakeven armed at +3R;
  from 09-06 = first acting session Tue 09-08) and E (the depth exit; `exit_rule='depth'`, stamped per row,
  first acting session 10-13). `magna53_smallcap` is in `PARTIAL_8R_SIGNAL_TYPES` and `DEPTH_EXIT_SIGNAL_TYPES`,
  so it labels D/E like MAGNA53 — but it is a different lane and is read on its own.
- **L1 cross-check:** the derived era must equal the recorder's `exit_era` on every fill that has recorder rows.
  **A mismatch stops the read** (the 11-06 rule; 0 mismatches then).
- **L3 breakout:** ONE era, `bp1` = the `pp` exit as deployed 10-31 (stop at the fill's true low of day, a
  third at +2R or at the close of session 3 when above the fill, the stop to cost after any third, the 20-day
  trail from session 3, the +1R-by-session-3 stall cut). The runner REFUSES to pass a `breakout_pp` row through
  the magna53 era function (it would read `era_c`). A later breakout exit change gets `bp2` and its own rows.
- **Admission eras inside an exit era — SPLIT, never pooled (D5; the 482 YAML's "segment first by
  admission_era").** Every arm cell is also computed per `(exit era, admission era)` — the recorder's
  `admission_era` stamp where a row exists, `rule_eras.admission_era_as_of(alert_date)` where none, labelled
  "derived" — and printed in `review.out`; the admission-era mix per lane/era is printed beside every era. The
  ladder (§2) reads the exit-era cell, and a PROPOSE is quoted only when ONE admission era carries n ≥ 10 AND
  wins on its own — mechanical in `arm_lens` (a pooled PROPOSE is demoted to WATCH with the per-admission-era n
  printed in its reason; tested). **The #718 open-below-floor change** (flipped ON 2026-11-03 15:05:28 UTC, after that day's ORB; first
  acting session **2026-11-04**) is an admission change: `rule_eras.ADMISSION_SWITCHES` carries its row
  (`adm_2026-11-04_open_below_floor`, added 2026-11-08 under the module's maintenance rule), and every admission
  cell is keyed on **(admission era, before / after 2026-11-04)** — `admission_cell_key`; a PROPOSE needs ONE such
  cell with n ≥ 10 that wins (re-challenge finding 3: the 11-06 cells pooled the two sides of #718 because the
  stamp did not split them). Every era-E lens line also prints **n before / after 2026-11-04**
  (`OPEN_FLOOR_FIRST_SESSION`, derived in the tests through `rule_eras.first_acting_session_after`). ⚠ The recorder
  rows written from 11-04 until the `rule_eras` row is deployed were stamped BEFORE the row existed and carry the 08-31 label — **I16 (§8): a fill
  alerted on/after 11-04 takes the DERIVED label for its cell; the stamp prints beside it and every stamp-vs-derived
  disagreement is listed in `review.out`.** Era E's trail-arming change (10-29) is not split (no admission change).
- **Monthly window vs eras — pinned now:** a month slices an era thin forever, so every per-era lens table is
  **CUMULATIVE from the era's start** (one exit rule = one population; that is not pooling), with the trades new
  in this window flagged and counted separately. "Every trade accounted for" is judged on the WINDOW list.
  Eras C and D are closed: their tables are baselines that will not change; era E and `bp1` grow.
- **No total line anywhere.** Nothing sums across eras or lanes.

### 1.4 Excluded and flagged (always listed by ticker)

- `pnl_attribution IS NOT NULL` (P&L distorted by a system bug): listed, excluded from every number.
- `entry_attempt = 2` (a re-entry after a stop): kept and flagged.
- A trade with no R frame (`trade_risk_per_share` is None: no positive entry−stop): listed under "no R", counted,
  excluded from every R number — never a substituted stop.
- Recorder classes (L1 arm comparisons only): `abstain`, `unscoreable`, pending (no row), `horizon` (a mark,
  never a return), book-arm `no_entry:` (scores 0 in R_cap, excluded from R_own — interpretation I3 of 11-06),
  `rcap_uncomputable` (I4). Each class is counted beside every number it was removed from.
- **Recorder coverage, per era (a dead recorder must not read as a thin era):** fills · fills with any recorder
  row · settled control pairs (`live_actual` + `live_replay`), the NAME of every closed fill older than
  `live_fill_counterfactuals.GAP_RETRY_SESSIONS` (5) sessions with no rows (a recorder gap) AND the NAME of every
  closed fill that old WITH rows but no settled control pair (unsettled — finding 10) — both on the page, both
  counted into line 1's "recorder gap on N fills". **The recorder's heartbeat** (`audit_recorder.sql`: the nightly
  `live_fill_counterfactual_recorded` row the 18:04 ET job writes mon–fri, and every `_error` row) is printed as
  "ran N of M sessions since <date>; sessions with no row: …; error rows E" — so a month with no older closes can
  still show a dead recorder. The sessions counted start at the LATER of the window start and the job's first
  fire, **2026-09-04** (`RECORDER_FIRST_SESSION`: built 09-03, deployed after that night's run, first fire 09-04
  18:04 ET; it backfilled the fills from 08-16), so 08-17..09-03 are never printed as missing. **A dead recorder** (ran on
  none of its sessions, or on none of the last `GAP_RETRY_SESSIONS`) takes line 1's recorder-gap headline, not "too few trades".
- **A capture that is not whole is not an empty month (finding 2).** `build_report` checks every `capture/*.sql`
  against the run's CSVs (`REQUIRED_CAPTURES`, derived from the folder, never typed); each missing file prints
  **NOT CAPTURED** at the top of the page and in `MANIFEST.txt`, every number that reads it is `n/a — not captured`
  (the five folded rows are always rendered), the absence sentence makes no claim, and line 1 leads with "capture
  incomplete". A missing `trades.csv` stops the read.

### 1.5 Units (the shared formulas — imported, never re-typed)

- **R (the real trade):** `sell_discipline.trade_realized_r` = `total_pnl ÷ ((entry − hard_stop) × entry_shares)`,
  `orb_low` as the stop fallback. The tail sections, the partial / exit descriptives and every "real trade"
  number use this. ⚠ This is the **hard-stop frame**: under the entry−2R stop it is 2× wider than the ORB frame
  (`entry − orb_low`) the recorder's `target_r` / `breakeven_arm_r` are set in. The two are never compared
  directly (see the runner shape in §3).
- **R_cap (the arm comparisons AND "disappoints"):** `book_geometry_arms.capped_dollar_r` — an arm's R × the risk
  the live sizing would have placed (the H10 rule; the 11-06 decision unit). Stored `realized_r_capped` is used
  where present and recomputed where NULL.
- **R_own, pct, adr:** the arm's own `realized_r`, `realized_pct`, `pnl_adr` (context, as on 11-06).
- **Peak / capture / giveback:** `mi_sell_discipline_records.peak_r`, `peak_price`, `capture_pct` (= realized ÷
  peak when peak > 0), `giveback_r`; `peak_adr` / `realized_adr` beside them because R mostly measures stop width.
- **Exit legs:** `mi_live_trades.exits` — the reason vocabulary is what the FIVE writers produce
  (`order_manager.py` 1318 / 4928 / 6389 / 6551 / 6626): `stop_hit` (both stop finalizers), `partial_profit`,
  and the full-exit order's `exit_reason` — `sma_trail_stop` (the trail AND the depth next-open sale), `breakout_stall_cut`,
  the breakout width sale (a sentence starting `setup:stop_too_wide_after_fill`, bucketed by prefix) and the
  fallback `exit`. The free-share sale after a stop breach (`_sell_free_shares_after_stop_breach`, reached from
  `_retry_restore_while_shares_held`) re-uses the failed exit's own reason, so it adds no word. **`gap_through` and
  `intraday_stop` are never legs** (the only `gap_through` in that code is an action return); anything else is
  printed as `other:<reason>` (I15).

---

## 2. The verdict ladder (one ladder, every lens)

| Verdict | Meaning | Rule |
|---|---|---|
| **CAN'T TELL** | too few trades to read | fewer than **3** readable trades (paired fills for an arm lens) in the CURRENT era |
| **NOTHING** | readable, nothing beats what we run | the lens's test is not met in the CURRENT era |
| **WATCH** | worth a focused re-read next month, nothing proposed | the test is met in the CURRENT era on **3–9** trades |
| **PROPOSE** | worth a CHANGE_PROCESS proposal (still THE LINE: N ≥ 10 backtest + his sign-off) | the test is met in the CURRENT era on **≥ 10** trades (within one admission era, §1.3) |

**D1 — the verdict is judged on the CURRENT era only.** Older eras are closed baselines: they are computed and
printed beside the verdict as context (*"era_c lost (n 7); era_d won (n 6)"*), never a veto. The first draft let
any readable era's loss veto the arm; on the published 11-06 table every one of the 13 arms had lost era C or D,
and those tables never change, so no arm could ever have reached WATCH. The same shape applies to the count
lenses (slippage: every era printed, the verdict on the current one).

For an **arm lens** (an alternative stop / entry / harvest / trail recorded beside the real fill) "the test is
met" = the 11-06 six-condition **WON**, unchanged: R_cap delta sum > 0 · R_own delta sum > 0 · R_cap drop-best
> 0 · engine-check sign agrees · tail-clip count = 0 · the arm's ≥ +4R count ≥ live's. A tie is |Δ| ≤ 0.05.
Two arms that produce the same row on most fills (e.g. `stop_low_of_day` = `stop_orb_low` on 09:31 fills) count
as ONE confirmation, with the identical-row rate stated.

"The current rule is best" is a real answer and is reported as one. A verdict is never quoted without its n,
and a finding off fewer than 3 trades is always labelled "under 3 trades".

---

## 3. The five lenses

| Lens | Exact metric | Source table · column | What is tested (→ ladder) | Min n |
|---|---|---|---|---|
| **Selection** | What we did with HIS labels: for each operator-labelled EP (`shared/operator_labelled_eps.OPERATOR_LABELLED_EPS`, ticker + alert_date) in the window: traded / skipped (`skip_reason`) / **alerted, no trade row** (an `mi_ep_alerts` row exists) / never alerted (no alert row). The **declared abstentions** (`tests/fixtures/must_not_miss_eps.py` members with `excluded=True` and `label_source="operator"` — CHPT 09-03, ABNB 08-07) are listed as abstentions and never a miss. L3: his **chart-sheet grade** (`tests/fixtures/breakout_list_grades.py`, his 11-05 ruling; vocabulary good / ok / no / conditional; the latest `list_date` strictly before the breakout day; none = ungraded) on every traded breakout name with the trade's R and peak_r | `mi_live_trades` (status, skip_reason) · `mi_ep_alerts` (`ep_alerts.sql`) · `shared/operator_labelled_eps.py` · the two fixtures | L1: the labelled real EPs we skipped / never alerted / alerted without a row are the finding (the list carries the fix path per name; no returns test): **under 3 missed = CAN'T TELL with the rows still listed ("under 3 trades")**, 3+ = WATCH, never PROPOSE (labels carry no returns), 0 missed = NOTHING. L3: "his **no** names lose, his **good** names carry the winners": every graded `no` trade finished ≤ 0R AND at least one `good` trade reached ≥ +2R | labels: 3 missed for WATCH, never PROPOSE; the L3 test needs ≥ 3 graded `no` trades and is CAPPED AT WATCH — **charts support, never decide** (finding 7: a grade filter is the one thing the standing rule rules out; his EP labels carry the same cap) |
| **Buy point** | (a) fill vs trigger: `fill_vs_trigger_pct` median / max / count > +1% **with a NULL counted apart** (never a ≤ 1% fill); `real_risk_vs_trigger_risk` median / max; the **fill-minute histogram** (ET, from `filled_at`). (b) the entry arms `entry_first_hour_bar`, `book_first_hour_low_of_day` vs `live_actual` in R_cap. L3: fill vs the list `level` (%), the `breakout_v1_fill_stop_checked` **decision mix** (keep / lower / sell_all / unchecked = I10) and the **thirds mix** (a `partial_profit` leg at ≥ ~+2R = the +2R third; below it = the session-3 third; none) | recorder `fill_facts` row · `mi_live_trades.filled_at, exits` · recorder entry/book arms · `mi_breakout_v1_list.level` · `mi_audit_log` event `breakout_v1_fill_stop_checked` | (a) slippage: the fills > +1% over the trigger (n ≥ 3) have an R_cap sum < 0 while the ≤ +1% fills' sum is > 0 in the CURRENT era (→ a fill cap is an ENTRY change; PROPOSE needs ≥ 10 fills); other eras printed as context (D1). (b) the arm ladder (the hour-bar arms see only fills whose 1-min ORB high filled — stated beside them). L3: descriptive | 3 / 10 |
| **Stop** | (a) the five stop arms `stop_orb_low`, `stop_adr_050`, `stop_adr_075`, `stop_orb_3r`, `stop_low_of_day` vs `live_actual` in R_cap, paired per era. (b) descriptive: live `stop_pct` / `stop_per_adr` **medians per era**; count stopped out (a final `stop_hit` leg — the only stop reason the writers produce) and, of those, how many then printed a daily high ≥ entry + 2R within 5 sessions ("stopped, then ran"). (c) the **stop-too-wide skips** sub-table: `skip_reason LIKE 'setup:stop_too_wide%'`, magna53, both modes (no position → mode-independent), since 05-05, vs the **ADMITTED control = entered magna53 rows over the same dates** (the YAML's words: no `skip_reason`, status not cancelled/skipped — with "entered" pinned to a FILL, `filled_at IS NOT NULL`, because `mi_live_trades` also holds `order_placed` / `expired` rows that never filled; `admitted_magna53.sql`; its account-mode and admission-era split printed beside the rate). **Both cohorts scored the same way — MFE over d+1..d+5 from the gap-day open on the same raw daily bars (`mfe_5d_pct`)**, NEVER `mi_ep_missed_outcomes.max_high_5d` (a FRACTION from the gap-day open whose window includes the gap day itself; read as a price it made every rejected name −99.9%). Hit-rate ≥ +10%, median MFE, both n, **two-sided Fisher p** | recorder stop arms · `mi_sell_discipline_records.stop_pct, stop_per_adr` · `mi_live_trades.exits` · `mi_daily_closes` | (a) the arm ladder. (b) descriptive only. (c) the matrix pre-registered in `data_gated_reviews.yaml::stop_too_wide_outcome_cohort` verbatim: REVISIT (rejected hit-rate ≥ admitted AND median MFE ≥ admitted) · KEEP (below on both, p < 0.10) · CANNOT TELL (else) — REVISIT maps to WATCH (<10 rejected) / PROPOSE (≥ 10 rejected AND ≥ 10 admitted); KEEP maps to NOTHING (the current filter is right); **CANNOT TELL maps to the ladder's CAN'T TELL, never NOTHING** (finding 6: the 09-16 reading said it could not tell, and NOTHING reads as "the current rule is best"). **D2: the p is the YAML's TWO-SIDED Fisher** — on its own 09-16 numbers (4 of 11 vs 17 of 25) that is 0.141 = CANNOT TELL, the reading it published; a one-sided test gives 0.080 and would have said KEEP | 3 / 10 |
| **Partials** | (a) the harvest arms `harvest_no_breakeven`, `harvest_trail_only`, `harvest_t3`, `harvest_legacy_2r` (= the retired +2R rule, forever) vs `live_actual`. (b) descriptive per era: partial fired rate (`partial_taken`); median `capture_pct`, median `giveback_r`; **the two runner shapes, counted apart** — *partial then breakeven* (era C's: a `partial_profit` leg, then the rest stopped within 0.05R of entry, **both sides** — a stop filled at +5R is a trailed winner, not a give-back) and *armed then breakeven* (eras D/E's: no partial needed — the sell-discipline `peak_price` reached the breakeven arm, `entry + breakeven_arm_r × (entry − orb_low)` in the ORB frame the arm is set in — the arm is the recorder row's own `breakeven_arm_r` where a row exists, else the ROW's era through `rule_eras.exit_rules_as_of(alert_date, signal_type, exit_rule=row)["breakeven_at_r"]`; **None (era C, every breakout row) = the armed shape does not apply and the trade is counted "n/a"**, never given a 3R arm (finding 4) — and the position then stopped within 0.05R of entry); the count of positions with `entry_shares` ≤ 2 (where the +8R third sells 1 share or nothing — `order_manager.plus8r_partial_shares`). L3: thirds sold at +2R / at session 3 / none (the buy-point row above) | recorder harvest arms · `mi_sell_discipline_records.capture_pct, giveback_r, peak_r, peak_price, partial_taken` · `mi_live_trades.exits, entry_shares, orb_low` | (a) the arm ladder. (b) descriptive; the runner-shape counts are quoted with n as the fact behind `runner_rule_sweep_recut` | 3 / 10 |
| **Exits** | (a) the trail arms `trail_pivot_swing`, `trail_character_ma` vs `live_actual` (abstention rate of `trail_character_ma` stated). (b) descriptive per era: final reason mix in the writers' vocabulary (§1.5), median `hold_trading_days`, `peak_r` vs realized R, the **tail-clip** count (an arm exits earlier than live on a fill live rode further). (c) era E / L2 **depth sales** = `exit_rule='depth'` AND a final `sma_trail_stop` leg (the depth sale books its leg as `sma_trail_stop`, `execute_depth_open_sale`'s default; `depth_sell_pending_on` is cleared after the sale so it is not a signature): count, and the **cost of selling at the open** = the sale leg's price vs the prior session's close, in R. (d) the "disappoints" fact per era: **live `live_actual` R_cap sum < 0** (capped-dollar R, the 11-06 unit — never the trade's own R) AND no fill ≥ +4R (the parked review's word; a fact, never a decision); n/a for L2/L3 (no recorder) | recorder trail arms · `mi_sell_discipline_records.hold_trading_days, peak_r, realized_r` · `mi_live_trades.exits, exit_rule` · `mi_daily_closes.close` | (a) the arm ladder; an arm that clips the tail LOSES regardless of its mean. (b)–(d) descriptive | 3 / 10 |

Every lens prints, beside every number: the era, n, the count of each excluded class, whether the trades
are new in this window or carried from the era's start, and on era E the before / after 2026-11-04 split (§1.3).

**The regime table** (the 482 review's §5, the ONE read's section 5): every arm × entry-stamped `regime` × era
with n, R_cap delta sum and WON; every cell under 10 named thin; never pooled. In `review.out`.

**The safeguard-transition check** (`runner_rule_sweep_recut`'s void arm): every `mi_safeguard_state` row in
`live` / `global` whose `last_transition_at` is after the current era start, excluding the YAML predicate's own
list (`drawdown_breaker`, `kill_scale_band`, `manual_trading_halt`, `breakout_v1_paper`) and anything at or before
its ANSWERED-THROUGH stamp (`2026-11-03 15:05:29+00`, the #718 flip answered the same day). Each one printed =
*"the 08-29 runner read is void"*. The exclusion list is a constant the test pins to the YAML text.

---

## 4. The tail — read trade by trade, on the REAL trade

**The tail is never gated by fidelity.** Fidelity (§5) gates arm-vs-live comparisons only. On 11-06 the only two
≥ +4R winners (VICR, KOD) vanished from every table because they failed the replay check; here they are read
from their own rows.

- **≥ +4R winners** and **≤ −1.5R losers** (worse than a full loss: a gap through the stop, slippage, a widened
  stop), on `trade_realized_r`, every lane and era, each a row with these fixed fields:
  ticker · lane · era · alert_date · **fill minute ET** · entry_shares · **fill vs trigger %** · **real risk ÷
  trigger risk** · stop width (% and ADR) · peak_r **and the session it printed** (`peak_hold_day`) · realized R ·
  capture_pct · **exit legs (reason, day, price in R)** · hold days · regime at alert · **admission era** (stamp,
  or derived and labelled) · **his label** (if any) · the best and worst recorder arm on this fill (R_own, arm
  name; L1 only) · fidelity pass/fail, how it passed (stored / re-weighted) and the class (§5) · **the 10-session
  high after the exit, in R from entry** (`post_exit_high_r`: the max daily high over the 10 sessions after the
  close day) — what the chart did after we left.
- No verdict is drawn from a tail row. The tail answers "what did our big winners and bad losers have in
  common" by inspection; a pattern seen on ≥ 3 tail trades becomes a WATCH line with those tickers named.
- The ≥ +2R count per era is printed beside the tail as context (the 11-06 convention).
- **Every closed trade in the window** gets the same row (the per-trade window list, §9), so the DoD's "every
  closed trade accounted for" is a list, not a count, and `exit_tune_cohort_review`'s forensic (entry vs plan,
  MFE before exit, exit reason, hold, regime) is carried on every trade, not only the tail. The forensic class
  (variance / entry-quality / entry-mechanics / exit-discipline / regime) is written by inspection on run day in
  the list's last column; the runner prints the fields, never the class.

---

## 5. Replay fidelity — the FAIRER test, fixed now

A fill's arm comparisons are quotable only when the recorder's `live_replay` (the live rule walked on stored
bars) agrees with `live_actual` (the real result). The 11-06 bar was |Δ| ≤ 0.25R and failed 4 of 20 — including
both big winners — mostly for one reason that is not a replay defect: the replay walks ONE fractional share and
sells a third of it at the partial, while a 1–3-share live position sells whole shares (a 2-share position sells
HALF at +8R, a 1-share position sells nothing).

**The test from this review on (replaces 0.25R; the 0.25R result is printed beside it once, for continuity):**

- **Tolerance:** `tol = max(0.25, 0.10 × |live_actual R|)` — nothing added to it. (The first draft added a
  share-size bound on top; on a 1-share fill that let any replay error up to 2.67R pass.)
- A fill **passes on the stored replay** when both controls are `settled` and `|live_replay.realized_r −
  live_actual R| ≤ tol`. Its arms are compared with `live_actual`.
- Otherwise the miss is classified FIRST: if the controls' `exit_session` or final reason differ, the class is
  `exit_session_differs` and the fill FAILS — a different exit path is never a sizing artefact (era C's breakeven
  moved AT the partial, so a 0-share live partial that never armed breakeven lands here, by design).
- Else the replay is **re-weighted** to the live fraction: `live_fraction` = Σ `partial_profit` leg shares ÷
  `entry_shares` from the trade's OWN `exits` (0 when no partial leg); the replay's partial leg carries
  `live_fraction` of the position and its remaining legs the rest, in the row's own R frame. A fill whose
  re-weighted replay is within `tol` **passes "re-weighted"** — and its arms are compared with the stored
  `live_replay`, not `live_actual` (the arms carry the same 1/3 weighting the replay does), on every one of the
  six conditions. Re-weighting assumes the exit path does not depend on share count, which the session/reason
  test above has just checked.
- **Every failing fill is listed with a class:** `exit_session_differs` · `whole_share` (entry_shares ≤ 3 and the
  replay's partial fired, and re-weighting did not close the gap) · `other` · `controls_unsettled`.
- **Seen before this was written** (11-06 misses, in R, replay − actual): OKTA −1.44 (C), VICR −1.11 (D; live
  +7.30R), KOD −0.29 (D; live +5.87R), CLS +1.15 (E). Under the new rule KOD passes on the 10% arm alone
  (0.59 ≥ 0.29). **D7: whether VICR, OKTA and CLS pass re-weighted is REPORTED by the run, not decided now** —
  their share counts and legs were NOT looked up while writing this; if the big winners still fail, the arm
  tables again hold no big winner and the plan says so rather than widening the bar.

---

## 6. Breakout missed-by-slots (#717 stage 2, his "track what we miss")

- **Source:** `mi_audit_log` rows with `event_type = 'breakout_v1_missed_by_slots'`, `detail` JSON: `ticker, day,
  minute, clock_et, break_price, break_high, stop, width, break_cum_volume, break_need_volume, hold_minute,
  list_rank, order_score, vol_bar, adr20, reason, row_status, account_mode`. One row per name per day that broke
  out (level + volume pace) while held for a full paper book and never got a slot. A row whose `detail` is not
  JSON is COUNTED on the page (never dropped silently).
- **Width rule, applied from the record's own fields (no join):** `width` is a FRACTION, `(level − stop) ÷ level`
  (`breakout_v1_entry.py:530`), and `adr20` is a fraction too — keep records with **width ≤ adr20** (the entry's
  own skip rule); the dropped count is stated. (The first draft tested `width ≤ adr20 × break_price`, a fraction
  against a price, which every record passed.)
- **Forward read (a daily-bar PROXY for the pp walk, declared as such):** from `mi_daily_closes` over the 10
  sessions after `day`: `+2R before stop` = a daily high ≥ break_price + 2 × (break_price − stop) before a daily
  low ≤ stop (a session with both counts as stopped — conservative); `MFE_10` = (max high − break_price) ÷
  (break_price − stop); the day's own close vs break_price. A record younger than 10 sessions is "immature" and
  counted, never in a decisive number.
- **Comparison:** the SEATED breakout trades filled **the same days as the missed records** (`signal_type =
  'breakout_v1'`, the ET date of `filled_at` ∈ the missed days): their realized R (`trade_realized_r`) and the
  same proxy walk from their own fill and stop, so missed and seated are compared in ONE unit (the proxy), with
  the real R beside; the count of ALL seated breakout trades is printed beside the same-day count.
- **Question:** did the order score seat the right names? Test = the missed cohort's `+2R before stop` share ≥
  the seated cohort's AND its median MFE_10 ≥ the seated median. → CAN'T TELL under 3 mature missed records ·
  WATCH at 3–9 · PROPOSE at ≥ 10 mature missed records with ≥ 3 seated. The proposal would be "re-examine the
  slot count / the order score" — a capacity and sizing question, his call.
- **Absence rule (0 records is not "nothing missed"):** the runner prints the positive observables beside the
  count — `breakout_v1_entry_hold` rows with state `slots_full` in the window, the **`breakout_v1_entry_day`
  rows** (the 15:55 step's own proof of running; none = the recorder did not run), the **`breakout_v1_missed_unreadable`
  rows** (names never judged), the number of list nights, the number of seated breakout trades, the
  `breakout_v1_paper` toggle state AND the `mi_strategies` row for `breakout_v1` (`enabled`, `phase`) — the env
  default is a third on/off source that lives in no table and is stated as "not captured". So 0 reads as "the
  lane did not run", "the recorder did not run", "no name was ever held", "held but none broke out (N unreadable)",
  or "missed: 0 of N held", each a different sentence. The sentence is given the RAW record count beside the
  readable one (finding 5): when records were written and none is readable it says so — "N written, none readable —
  X dropped by the width rule, Y malformed (no day / break price / stop), Z unreadable JSON" — and never "none broke
  out while held"; the drop counts ride on every other sentence too. When `audit_breakout`, `breakout_list`,
  `strategy_toggles` or `strategies` was NOT CAPTURED the sentence names the file and makes no claim (finding 2).
  **D7: which sentence the first run prints is the run's.**

---

## 7. The five folded reviews — how each is answered here

| Review (`data_gated_reviews.yaml`) | What it asked | Answered by | What "answered" looks like each month | What stays outside this review |
|---|---|---|---|---|
| `bracket_geometry_variants_parked` (status done 11-07) | does any geometry variant (stop level, 5-min bar, established-low entry, re-entry) earn a live arm; re-open if era C reaches ~20 and "disappoints" | §3 Stop (a) + Buy point (b); §3 Exits (d) | the stop / entry arm ladder per era; the "disappoints" fact per era (capped-dollar R) printed as a fact | the 5-min shadow lane and the sweep lanes (Tiers 2–3 of 11-06) — descriptive, re-run only if an arm goes WATCH |
| `live_fill_counterfactuals_first_read_482` (THE ONE exit read; bar 20 paired era-E fills) | on fills under the CURRENT exit rule, paired, does any stop / harvest / trail arm beat what we ran; six sections (fidelity, stop, harvest, trail, regime, running); segment first by admission era | §5 + §3 Stop (a), Partials (a), Exits (a); the regime table; the admission-era cells (§1.3) | the same six sections at WHATEVER era-E n exists, verdicts from the ladder (CAN'T TELL is expected for months); its own predicate count printed so the 20-paired bar is visible | its re-arm at 40 stays in the YAML; the review quotes the predicate, it does not replace the bar |
| `exit_tune_cohort_review` (recurring n = 20/40/…) | per-trade forensic (entry vs plan, MFE before exit, exit reason, hold, regime; classify variance / entry-quality / entry-mechanics / exit-discipline / regime); the intraday partial sweep; regime segmentation | the per-trade window list (§4, §9) carries the forensic fields on EVERY window trade; §3 Partials (b) and Exits (b) carry MFE / capture / hold / reason per era; the regime table | the forensic classification written on every window trade by inspection (3–5 trades a month: cheap); the wide 34-candidate grid (`_508_exit_rule_replay.py`) is NOT re-run here | the offline grid runs when its own n = 20 era-E bar fires, and quotes the recorder arms as primary where they overlap (its own note) |
| `runner_rule_sweep_recut` (trade-count arm 40 / a live-mode safeguard flip) | does a looser runner rule beat breakeven-after-partial; a rule change voids the last read | §3 Partials (b) the two runner shapes + Exits (b) giveback; the safeguard-transition check (§3) with the YAML's own exclusion list | the fact the sweep rests on (winners that gave the runner back to breakeven — partial-then-breakeven in C, armed-then-breakeven in D/E) counted per era with n; any live/global toggle since the era start named as "the 08-29 read is void" | the Run-U replay (`_bt_replay.py`) re-runs only on its own trigger; it is $0 but it is a different population |
| `stop_too_wide_outcome_cohort` (bar 20 rejected rows) | does the ORB-range > 1.5 × ATR filter shed winners; REVISIT / KEEP / CANNOT TELL vs the admitted book | §3 Stop (c) | the rejected-vs-admitted matrix (entered magna53 rows as the control, both on raw bars, two-sided p), both n, every month, at whatever n exists; REVISIT → WATCH / PROPOSE by the ladder | nothing — this review IS its monthly run; the YAML's threshold becomes a pointer |

**Pointer edits — MADE 2026-11-08 (D6), in the same branch as this plan:** each of the five YAML entries'
`action_when_ready` now opens with *"RUNS INSIDE PLAN #720's monthly trade review (this file §7)"*, its predicate
and bar kept intact for what stays outside (the last column) — except `stop_too_wide_outcome_cohort`, whose entry
says *nothing stays outside* and marks its step 1 (the pull from `mi_ep_missed_outcomes`, the source this plan bans)
REPLACED by §3 Stop (c) (finding 9); the 482 read's *"quote nothing from a fill where they
disagree by more than 0.25R"* is replaced by this plan's §5 bar. `tests/test_720_monthly_review.py` pins all of it.
**The five rows are ALWAYS rendered** (a review absent from `predicates.csv`, or the file missing, prints
`n/a — not captured`, finding 2), and each row's verdict reads EVERY lens the review asked about (`FOLD_MAP`, finding
8): 482 → stop + partials + exits; `bracket_geometry_variants_parked` → stop + buy point; `exit_tune` → partials;
`runner_rule_sweep_recut` → descriptive (its fact is the two runner shapes; no arm answers it); `stop_too_wide` → its
own matrix verdict. The highest rung any mapped arm reached is the row's verdict.
**The predicate counts on the page are the YAML's `predicate_sql` VERBATIM:** `capture/predicates.sql` is
generated from the YAML by `run_review.py --emit-predicates` (a server-side `COPY (…) TO STDOUT`, so multi-line
predicates with comments survive; only each predicate's trailing semicolon is dropped) and a test pins the
committed file to the YAML — the first draft had re-typed two of them and dropped `exit_tune`'s `LEAST(…)` runner
gate and `runner_rule_sweep_recut`'s `+40 ×` safeguard arm.

---

## 8. Decisions and interpretations pinned before any number

**Decided by the main loop on 2026-11-08 (the challenge's forks; none is THE LINE, none went to him):**

- **D1 — arm and count verdicts are judged on the CURRENT era only;** older eras are printed as context, never
  a veto. Changes: the ladder (§2); on the 11-06 table it is the difference between "no arm can ever reach WATCH"
  and a ladder that can be climbed.
- **D2 — the stop-too-wide test uses the YAML's TWO-SIDED Fisher;** its 09-16 reading (p 0.141, CANNOT TELL)
  stands unchanged. Changes: `fisher_exact_two_sided`; the one-sided draft would have read KEEP on the same numbers.
- **D3 — the first window starts at fills on/after 2026-08-16;** the 20 fills of the 11-06 read are re-read
  under the new lenses and flagged `read 11-06 = yes` on the list.
- **D4 — breakout selection grades come from `tests/fixtures/breakout_list_grades.py`** (his chart-sheet grades,
  ruling 11-05: *"the scoring we do for pattern is much better when you show me the chart"*), not
  `mi_breakout_v1_grades` (empty since). The L3 test reads `no` / `good`, not "C/skip" / "A+/A".
- **D5 — era E prints counts before and after 2026-11-04 on every lens;** admission eras are split wherever the
  482 YAML said so — every arm cell per (exit era, admission era) in `review.out`, never pooled (§1.3).
- **D6 — the five YAML pointer edits are made in this branch** (§7); each entry's predicate is intact; the
  fidelity bar in the 482 entry is this plan's.
- **D7 — the breakout absence sentence and the VICR / KOD / OKTA / CLS fidelity outcomes are reported by the
  run, not decided now.**

**Decided 2026-11-08 against the re-challenge (findings 1–10; the plan's design held, three runner defects would
have made the 11-29 page say something false):**

- **D8 — line 1 never says "Nothing beats what we run" unless an ARM lens on the current era actually read
  NOTHING.** In order: a capture that is not whole ("capture incomplete — N file(s) NOT CAPTURED"); a PROPOSE;
  a DEAD recorder ("recorder gap — the 18:04 ET job wrote no `recorded` row on …": ran 0 of N sessions, or none of
  the last GAP_RETRY_SESSIONS); "recorder gap on N fills" (no rows, or rows with no settled control pair, past the
  retry window); "N arm(s) on watch (beat what we run, but on under 10 trades; nothing proposed); M did not beat it,
  K unreadable"; "Nothing beats what we run" ONLY when no arm is on watch and an arm read NOTHING; else **"too few
  trades to read yet"** with the closed-fill and settled-pair counts. The recorder's first session (09-04) is
  checked against the earliest `audit_recorder.csv` row at the first capture. A count lens
  reading NOTHING (none of his labels missed) is not an arm reading NOTHING. Changes: `answer_line` (finding 1).
- **D9 — the #718 change is an admission change with its own `ADMISSION_SWITCHES` row**, and admission cells are
  keyed on (admission era, before / after 11-04) (§1.3; findings 3). The row was added on this branch rather than
  main because the runner is the first reader that needs it; the recorder stamps it from the next nightly run.
- **D10 — "charts support, never decide" caps every chart- or label-based test at WATCH** (his breakout grades,
  his EP labels); the armed runner shape applies only where the row's era had a price-armed breakeven; the stop-
  too-wide CANNOT TELL is CAN'T TELL; the folded rows read every lens their review asked about and are always five
  (findings 4, 6, 7, 8); the recorder's heartbeat is captured (finding 10).

**Interpretations.** The 11-06 read pinned eight (I1–I8) where its prereg was silent; they carry over unchanged.
Any new case the data raises on run day is pinned here, numbered I16+, with the rule chosen BEFORE the affected
number is computed and the alternative's effect stated. Template: `I<n> — <case> → <rule>. Changes: <which labels>.`

Known silences settled now:
- **I9 —** a trade present in the window with no `mi_sell_discipline_records` row: peak / capture / giveback
  read "n/a (no record)", the trade stays in every other number; the armed-then-breakeven shape cannot be judged
  (no `peak_price`) and is counted as not-a-shape.
- **I10 —** a breakout row whose `breakout_day0_pp` or fill-stop marker is missing: the buy-point L3 mix counts
  it as "unchecked"; it stays in R numbers.
- **I11 —** a recorder era mismatch on a FLAGGED (`entry_attempt = 2`) fill is still a stop; the re-entry is a
  different fill, not a different era.
- **I12 —** a fill with recorder rows but no `admission_era` stamp takes the derived label and is marked
  "derived" everywhere it prints; a fill whose stamp disagrees with the derived label keeps the STAMP (the
  recorder saw the trade) and the disagreement is printed in `review.out`.
- **I13 —** a `live_replay` row whose `exits` legs cannot be read (no shares, no price) cannot be re-weighted:
  the fill fails with its classified miss; no substitute weighting is invented.
- **I14 —** the admitted control's `mfe_5d_pct` needs the gap-day open and five forward sessions on the captured
  bars; an unscored row is COUNTED beside the matrix, never filled from another column.
- **I16 —** a fill alerted on/after 2026-11-04 whose recorder `admission_era` stamp predates the #718 row (the
  08-31 label, written from 11-04 until the `rule_eras` row is deployed) takes the DERIVED label `adm_2026-11-04_open_below_floor` for its admission
  cell; the stamp prints beside it (I12) and the disagreement is listed in `review.out`. Changes: the admission
  cells of the fills alerted from 11-04 on whose stamp predates the deployed row; nothing before 11-04.
- **I15 —** an exit leg whose reason is outside the enumerated vocabulary prints as `other:<reason>` and is
  not a stop, a partial or a depth sale for any count. The five writers are complete; the REASON set flows from
  their callers (`execute_full_exit(trade_id, reason)` is also reachable from one-off operator closes — MTW's
  11-02 "reset it" is in the first window's L3 rows), so an `other:` on the page names a caller this plan did not
  enumerate, to be added to `EXIT_REASONS` with its source line — never silently re-bucketed.

---

## 9. The one page to him (format, fixed)

Plain words. Tables. n on every number. No acronyms without their plain name once. The first line is the
answer.

1. **Line 1 — the answer** (D8). e.g. *"too few trades to read yet (3 closed live fills, 0 with a settled replay
   pair that passes); big winners 0, bad losers 1; action: none."* — or *"recorder gap on 2 fills …"*, or
   *"1 arm(s) on watch (beat what we run, but on under 10 trades; nothing proposed); 12 did not beat it, 0 unreadable"*,
   or *"Nothing beats what we run"* only when no arm is on watch and an arm lens read NOTHING. Under it, one **NOT
   CAPTURED: <file>.csv** line per missing capture file (finding 2).
2. **Population table:** lane × era → closed trades in the window · carried from the era start · excluded
   (ticker list) · the pre-window closes count · recorder coverage per era (fills / with rows / settled pairs,
   gaps and unsettled fills named) · the recorder heartbeat (ran N of M sessions; missing sessions; error rows) ·
   fidelity pass / fail (L1; stored vs re-weighted; classes).
3. **Lens table:** lens · lane/era · n · the reading in one phrase (with the era-E before / after 11-04 split) ·
   verdict (CAN'T TELL / NOTHING / WATCH / PROPOSE; "context" on non-current eras).
4. **Tail table:** the ≥ +4R and ≤ −1.5R trades, one row each (§4 fields), then the one-sentence read per trade.
5. **Breakout missed-by-slots:** missed n (width-dropped, unreadable JSON) · seated n same-day (all seated beside)
   · the proxy shares · verdict · the absence observables.
6. **Folded reviews:** the five rows of §7 with this month's predicate count (verbatim SQL) and verdict; the
   safeguard transitions since the era start.
7. **Action line, always present:** *"Action: none"* or one line per PROPOSE — *"#<task> (<plain name>):
   write the CHANGE_PROCESS proposal — needs an N ≥ 10 backtest and your sign-off."* Never a fork sent as a
   one-off.
8. **Every closed trade in the window** (the appendix): one row per trade with the §4 fields, `read 11-06`, the
   before/after 11-04 flag and the forensic class column.

Everything else (every per-fill row, every excluded class, the recorder checks, the regime table, the
admission-era cells) is in the run folder's `review.out` and the dated analysis doc, not on the page.

---

## 10. The runner — contract

`scripts/probes/_720_monthly/run_review.py` (tests: `tests/test_720_monthly_review.py`, invented fixtures in the
units prod writes).

- **Capture once, read many.** `capture/*.sql`, each starting `SET default_transaction_read_only = on;` and a
  `\copy (...) TO STDOUT WITH CSV HEADER` (one line) — or, for `predicates.sql` alone, a server-side multi-line
  `COPY (...) TO STDOUT WITH CSV HEADER` — run ONCE on run day via
  `docker exec -i apollo-postgres psql -q -X -v ON_ERROR_STOP=1 ... < file.sql > runs/<date>/data/<name>.csv`;
  then `run_review.py --report runs/<date>` reads the CSVs and never the database. `MANIFEST.txt` = row counts
  + md5 per file + the capture timestamp (the thing the 11-06 plan called for and never wrote).
- Queries: `trades.sql` (every `mi_live_trades` row filled on/after the first-window start — closed and open,
  so "still open → next review" is visible) · `pre_window_closes.sql` (filled before it, closed after — a count
  per lane) · `skips_window.sql` (the unfilled rows since the start, for the label join) · `ep_alerts.sql`
  (`mi_ep_alerts` since 08-01, for "alerted, no trade row" vs "never alerted") · `legacy_paper_count.sql` ·
  `cf_arms.sql` (every recorder row for those trade ids) · `sell_discipline.sql` · `daily_bars.sql` (the
  tickers' daily bars — trades, stop-too-wide skips, the admitted control, missed-by-slots names) ·
  `skips_stop_too_wide.sql` + `admitted_magna53.sql` (the control; `mi_ep_missed_outcomes` columns are captured
  for the record and NOT read) · `breakout_list.sql` · `audit_breakout.sql` (missed-by-slots, holds, entry_day,
  unreadable, fill-stop markers, session-third events) · `strategy_toggles.sql` + `strategies.sql` ·
  `safeguard_transitions.sql` · `predicates.sql` (generated from the YAML, §7) · `audit_recorder.sql` (the
  recorder's nightly `live_fill_counterfactual_recorded` / `_error` rows, finding 10). Grades come from the fixture
  (D4); there is no grades query. **The required set is every `capture/*.sql`** (`REQUIRED_CAPTURES`, derived from
  the folder): `--manifest` writes `NOT CAPTURED` for a missing CSV and `--report` prints it on the page and reads
  nothing from it (finding 2).
- **Pure functions** over CSV dicts, each unit-tested on invented rows: `lane_of`, `era_of` (refuses
  `breakout_pp` through the magna53 function), `admission_era_of`, `post_open_floor`, `in_window`,
  `recorder_gaps`, `reason_bucket` / `final_reason` / `is_depth_sale` / `partial_fraction`, `reweight_replay_r`,
  `fidelity`, `classify_fidelity_miss`, `era_cell` (the six conditions, baseline-aware), `verdict` (the ladder,
  D1), `admission_cell_key` / `admission_cells` (finding 3), `regime_table`, `runner_shapes` / `breakeven_arm_for`
  (finding 4), `recorder_runs` / `recorder_gap_count` (finding 10), `missing_captures` / `folded_rows` (findings 2,
  8), `answer_line` (D8), `stopped_then_ran`, `post_exit_high_r`,
  `depth_sale_cost_r`, `slippage_test`, `fill_minute_histogram`, `tails` / `trade_row`, `missed_records`,
  `width_ok`, `missed_proxy_walk`, `missed_vs_seated`, `absence_observables`, `breakout_buy_point`,
  `fisher_exact_two_sided`, `stop_too_wide_matrix`, `mfe_5d_pct`, `selection_labels` / `selection_verdict` /
  `declared_abstentions`, `breakout_selection`, `safeguard_transitions_check`, `emit_predicates_sql`, `render`.
- **Output:** `runs/<date>/review.md` (the one page, §9, with the per-trade appendix) + `runs/<date>/review.out`
  (every per-era arm cell, the admission-era cells, the regime table, the fidelity result per fill, the recorder
  checks, the safeguard voids). The 11-06 fills are flagged from the id column ONLY of
  `scripts/probes/_482_read_1106/data/live_all.csv` (`--read-1106`; no outcome column is read).
- **No prod run before 11-29.** The runner is exercised on fixtures only until then.

---

## 11. What this does not answer (standing)

- **Selection beyond what we took.** The review sees fills, skips and alerts; a name that never alerted is
  visible only through his labels and the missed-by-slots record.
- **A verdict on a thin era.** Era E and `bp1` will read CAN'T TELL or WATCH for months at ~3–5 live fills a
  month; that is the honest pace and is reported as such.
- **Anything pooled across eras, admission eras or lanes.**
- **The env default of the breakout switch** — not in any table; the page says so rather than reading it.
- **Any change.** PROPOSE opens a CHANGE_PROCESS proposal; nothing here moves a rule.
