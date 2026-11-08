# #720 — the monthly trade review: PRE-REGISTERED plan (written 2026-11-08, before any outcome row of the first window was read)

**What this is.** The fixed plan the monthly comprehensive trade review runs on — the first run is Sun 2026-11-29.
On run day the runner (`scripts/probes/_720_monthly/run_review.py`) captures the data once, computes every
number from this plan, and renders the one page. Nothing in this file is tuned to the data: at the time of
writing no closed-trade outcome of the first window was read beyond what the 11-06 read already published
(`docs/analysis/482_cross_arm_read_2026-11-06.md`), and that is listed under "seen before this was written".

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
- **First window:** trades FILLED on/after **2026-08-16** ET (the day the entry−2R stop went live = era C start =
  the counterfactual recorder's `BACKFILL_FROM`; the capture's own filter) and closed by the run date. A trade
  filled before 08-16 and closed after it ran under the era-B stop and is not in the capture — stated so it is
  not "accounted for" on paper and missing in fact. Why that far back: the review has never
  run, the stop geometry has been one rule since then, and the 11-06 read covered only the arm comparison on
  20 of these trades — the buy-point / partial / exit / tail reads of this plan are new on every one of them.
  The 20 fills the 11-06 read scored are flagged `read_11-06 = yes` in the trade list so nothing is re-counted
  as new evidence.
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
- **Inside an era, admission changes are reported as the `admission_era` mix** (recorder stamp) and are not
  split further (the 11-06 convention). Era E's trail-arming change (10-29) is likewise not split.
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

### 1.5 Units (the shared formulas — imported, never re-typed)

- **R (the real trade):** `sell_discipline.trade_realized_r` = `total_pnl ÷ ((entry − hard_stop) × entry_shares)`,
  `orb_low` as the stop fallback. The tail sections, the partial / exit descriptives and every "real trade"
  number use this.
- **R_cap (the arm comparisons):** `book_geometry_arms.capped_dollar_r` — an arm's R × the risk the live
  sizing would have placed (the H10 rule; the 11-06 decision unit). Stored `realized_r_capped` is used where
  present and recomputed where NULL.
- **R_own, pct, adr:** the arm's own `realized_r`, `realized_pct`, `pnl_adr` (context, as on 11-06).
- **Peak / capture / giveback:** `mi_sell_discipline_records.peak_r`, `capture_pct` (= realized ÷ peak when
  peak > 0), `giveback_r`; `peak_adr` / `realized_adr` beside them because R mostly measures stop width.

---

## 2. The verdict ladder (one ladder, every lens)

| Verdict | Meaning | Rule |
|---|---|---|
| **CAN'T TELL** | too few trades to read | fewer than **3** readable trades (paired fills for an arm lens) in the era |
| **NOTHING** | readable, nothing beats what we run | the lens's test is not met |
| **WATCH** | worth a focused re-read next month, nothing proposed | the test is met in the CURRENT era on **3–9** trades AND in every other readable era (none LOST) |
| **PROPOSE** | worth a CHANGE_PROCESS proposal (still THE LINE: N ≥ 10 backtest + his sign-off) | the test is met in the CURRENT era on **≥ 10** trades AND no readable era LOST |

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
| **Selection** | What we did with HIS labels: for each operator-labelled EP (`shared/operator_labelled_eps.OPERATOR_LABELLED_EPS`, ticker + alert_date) in the window: traded / skipped (`skip_reason`) / never alerted; for L3: his `/bgrade` grade on every traded breakout name (`mi_breakout_v1_grades.grade`, the latest `scan_date` < `alert_date` for the ticker; none = ungraded) with the trade's R and peak_r | `mi_live_trades` (status, skip_reason) · `shared/operator_labelled_eps.py` · `mi_breakout_v1_grades` | L1: a labelled real EP we skipped or never alerted = one WATCH row each (the list already carries the fix path per name; no returns test). L3: "his C/skip names lose, his A+/A names carry the winners": every graded C/skip trade finished ≤ 0R AND at least one A+/A trade reached ≥ +2R | labels: any; the L3 test needs ≥ 3 graded C/skip trades (WATCH) and ≥ 10 graded trades (PROPOSE) |
| **Buy point** | (a) fill vs trigger: `fill_vs_trigger_pct` median / max / count > +1%; `real_risk_vs_trigger_risk` median / max; fill minute (ET) histogram 09:31–09:45. (b) the entry arms `entry_first_hour_bar`, `book_first_hour_low_of_day` vs `live_actual` in R_cap. L3: fill vs the list `level` (%), and the `breakout_v1_fill_stop_checked` decision mix (lowered / sold / kept) | recorder `fill_facts` row · `mi_live_trades.filled_at` · recorder entry/book arms · `mi_breakout_v1_list.level` · `mi_audit_log` event `breakout_v1_fill_stop_checked` | (a) slippage: the fills > +1% over the trigger (n ≥ 3) have an R_cap sum < 0 while the ≤ +1% fills' sum is > 0 in the same era (→ a fill cap is an ENTRY change; PROPOSE needs ≥ 10 fills in the era). (b) the arm ladder (the hour-bar arms see only fills whose 1-min ORB high filled — stated beside them) | 3 / 10 |
| **Stop** | (a) the five stop arms `stop_orb_low`, `stop_adr_050`, `stop_adr_075`, `stop_orb_3r`, `stop_low_of_day` vs `live_actual` in R_cap, paired per era. (b) descriptive: live `stop_width_pct` / `stop_width_adr` (`stop_per_adr`) median; count stopped out (`exits` reason `stop_hit` / `gap_through`, or `final_reason` on `live_actual`) and, of those, how many then printed a daily high ≥ entry + 2R within 5 sessions ("stopped, then ran"). (c) the **stop-too-wide skips** sub-table: `skip_reason LIKE 'setup:stop_too_wide%'`, magna53, both modes (no position → mode-independent) vs the admitted fills, MFE over d+1..d+5 from the gap-day open on the same raw daily bars, hit-rate ≥ +10% and median MFE, both n, Fisher p | recorder stop arms · `mi_sell_discipline_records.stop_pct, stop_per_adr` · `mi_live_trades.exits` · `mi_daily_closes` · `mi_ep_missed_outcomes.max_high_5d, open_d0` | (a) the arm ladder. (b) descriptive only. (c) the matrix pre-registered in `data_gated_reviews.yaml::stop_too_wide_outcome_cohort` verbatim: REVISIT (rejected hit-rate ≥ admitted AND median MFE ≥ admitted) · KEEP (below on both, p < 0.10) · CANNOT TELL (else) — REVISIT maps to WATCH (<10 rejected) / PROPOSE (≥ 10 rejected AND ≥ 10 admitted) | 3 / 10 |
| **Partials** | (a) the harvest arms `harvest_no_breakeven`, `harvest_trail_only`, `harvest_t3`, `harvest_legacy_2r` (= the retired +2R rule, forever) vs `live_actual`. (b) descriptive per era: partial fired rate (`partial_taken`); median `capture_pct`, median `giveback_r`; the "runner shape" count = partial fired AND the rest stopped at breakeven (an `exits` leg `partial_profit` followed by a `stop_hit` leg at ≥ entry − 0.05R); the count of positions with `entry_shares` ≤ 2 (where the +8R third sells 1 share or nothing — `order_manager.plus8r_partial_shares`). L3: thirds sold at +2R / at session 3 / none (`exits` legs + audit `breakout_pp_session_third*`) | recorder harvest arms · `mi_sell_discipline_records.capture_pct, giveback_r, peak_r, partial_taken` · `mi_live_trades.exits, entry_shares` · `mi_audit_log` | (a) the arm ladder. (b) descriptive; the runner-shape count is quoted with n as the fact behind `runner_rule_sweep_recut` | 3 / 10 |
| **Exits** | (a) the trail arms `trail_pivot_swing`, `trail_character_ma` vs `live_actual` (abstention rate of `trail_character_ma` stated). (b) descriptive per era: final reason mix (`stop_hit` / `sma_trail_stop` / depth sale / `gap_through` / other), median `hold_trading_days`, `peak_r` vs realized R, the **tail-clip** count (an arm exits earlier than live on a fill live rode further). (c) era E / L2 depth sales: count, and the next-open sale price vs the signal close in R (the cost of selling at the open). (d) the "disappoints" fact per era: live R_cap sum < 0 AND no fill ≥ +4R (the parked review's word; a fact, never a decision) | recorder trail arms · `mi_sell_discipline_records.hold_trading_days, peak_r, realized_r` · `mi_live_trades.exits, depth_sell_pending_on` · `mi_daily_closes.close, open_price` | (a) the arm ladder; an arm that clips the tail LOSES regardless of its mean. (b)–(d) descriptive | 3 / 10 |

Every lens prints, beside every number: the era, n, the count of each excluded class, and whether the trades
are new in this window or carried from the era's start.

---

## 4. The tail — read trade by trade, on the REAL trade

**The tail is never gated by fidelity.** Fidelity (§5) gates arm-vs-live comparisons only. On 11-06 the only two
≥ +4R winners (VICR, KOD) vanished from every table because they failed the replay check; here they are read
from their own rows.

- **≥ +4R winners** and **≤ −1.5R losers** (worse than a full loss: a gap-through, slippage, a widened stop),
  on `trade_realized_r`, every lane and era, each a row with these fixed fields:
  ticker · lane · era · alert_date · fill minute ET · entry_shares · fill vs trigger % · stop width (% and ADR) ·
  peak_r (and the session it printed) · realized R · capture_pct · exit legs (reason, session, price in R) ·
  hold days · regime at alert · admission era · his label (if any) · the best and worst recorder arm on this fill
  (R_own, arm name; L1 only) · fidelity pass/fail and class (§5) · **one plain sentence of what the trade did**
  (what the chart did after our exit, from daily closes: the high within 10 sessions after the close in R).
- No verdict is drawn from a tail row. The tail answers "what did our big winners and bad losers have in
  common" by inspection; a pattern seen on ≥ 3 tail trades becomes a WATCH line with those tickers named.
- The ≥ +2R count per era is printed beside the tail as context (the 11-06 convention).

---

## 5. Replay fidelity — the FAIRER test, fixed now

A fill's arm comparisons are quotable only when the recorder's `live_replay` (the live rule walked on stored
bars) agrees with `live_actual` (the real result). The 11-06 bar was |Δ| ≤ 0.25R and failed 4 of 20 — including
both big winners — mostly for reasons that are not replay defects: a 1–3-share position sells whole shares (a
2-share position sells HALF at +8R, a 1-share position sells nothing, the replay sells a third of one share),
and the daily-bar trail fires at a close and sells at the next open while the real order fills at its own time.

**The test from this review on (replaces 0.25R; the 0.25R result is printed beside it once, for continuity):**

- A fill **passes** when both controls are `settled` and
  `|live_replay.realized_r − live_actual R| ≤ max(0.25, 0.10 × |live_actual R|) + partial_size_bound`.
- **`partial_size_bound`** (the whole-share allowance) applies only when `live_replay.partial_fired` is TRUE and
  `entry_shares ≤ 3`: `|live_fraction − 1/3| × target_r`, where `live_fraction` = the shares the LIVE sizer sold
  on that fill day ÷ `entry_shares`, and `target_r` is the row's own partial multiple (8 in eras D/E, 2 in C).
  The live sizer is dated: from **2026-10-12** (`scripts/ep_replay.PARTIAL_MIN_ONE_SHARE_FROM`, imported, never
  re-typed) it is `plus8r_partial_shares` (1 share → 0 → bound 8/3 = 2.67R; 2 → 1/2 → 1.33R; 3 → 1/3 → 0); before
  it, `int(shares // 3)` (1 or 2 shares → 0 sold → bound 1/3 × target_r = 2.67R at +8R, 0.67R at +2R; 3 → 0).
  Otherwise the bound is 0. This is the size of the mismatch the frozen recorder cannot model, not a tuning knob.
- **Every failing fill is listed with a class**, from the two control rows:
  `whole_share` (entry_shares ≤ 3 and the replay's partial fired) · `exit_session_differs` (the controls'
  `exit_session` or `final_reason` differ) · `other`. The classes have different fixes and are reported apart.
- **Seen before this was written** (11-06 misses, in R, replay − actual): OKTA −1.44 (C), VICR −1.11 (D; live
  +7.30R), KOD −0.29 (D; live +5.87R), CLS +1.15 (E). Under the new rule KOD passes on the 10% arm alone
  (0.59 ≥ 0.29). VICR (filled before 10-12) passes only if it held ≤ 2 shares with the replay's partial fired
  (0.73 + 2.67 ≥ 1.11); OKTA (era C, +2R partial: bound 0.67R at ≤ 2 shares) and CLS (era E) pass only through
  the same bound. **The share counts were NOT looked up while writing this**;
  whatever the runner finds is reported, and if the big winners still fail, the arm tables again hold no big
  winner and the plan says so rather than widening the bar.

---

## 6. Breakout missed-by-slots (#717 stage 2, his "track what we miss")

- **Source:** `mi_audit_log` rows with `event_type = 'breakout_v1_missed_by_slots'`, `detail` JSON: `ticker, day,
  minute, clock_et, break_price, break_high, stop, width, break_cum_volume, break_need_volume, hold_minute,
  list_rank, order_score, vol_bar, adr20, reason, row_status, account_mode`. One row per name per day that broke
  out (level + volume pace) while held for a full paper book and never got a slot.
- **Width rule, applied from the record's own fields (no join):** keep records with `width ≤ adr20 × break_price`
  (the entry's own skip rule); the dropped count is stated.
- **Forward read (a daily-bar PROXY for the pp walk, declared as such):** from `mi_daily_closes` over the 10
  sessions after `day`: `+2R before stop` = a daily high ≥ break_price + 2 × width before a daily low ≤ stop
  (a session with both counts as stopped — conservative); `MFE_10` = (max high − break_price) ÷ width; the day's
  own close vs break_price. A record younger than 10 sessions is "immature" and counted, never in a decisive
  number.
- **Comparison:** the SEATED breakout trades filled the same days (`signal_type='breakout_v1'`, `filled_at` on
  `day`): their realized R (`trade_realized_r`) and the same proxy walk from their own fill and stop, so missed and
  seated are compared in ONE unit (the proxy), with the real R beside.
- **Question:** did the order score seat the right names? Test = the missed cohort's `+2R before stop` share ≥
  the seated cohort's AND its median MFE_10 ≥ the seated median. → CAN'T TELL under 3 mature missed records ·
  WATCH at 3–9 · PROPOSE at ≥ 10 mature missed records with ≥ 3 seated. The proposal would be "re-examine the
  slot count / the order score" — a capacity and sizing question, his call.
- **Absence rule (0 records is not "nothing missed"):** the runner prints the positive observables beside the
  count — `breakout_v1_entry_hold` rows with state `slots_full` in the window, the number of list nights, the
  number of seated breakout trades, and the `breakout_v1_paper` toggle state — so 0 reads as "the lane did not
  run / no name was ever held", "held but none broke out", or "missed: 0 of N held", each a different sentence.

---

## 7. The five folded reviews — how each is answered here

| Review (`data_gated_reviews.yaml`) | What it asked | Answered by | What "answered" looks like each month | What stays outside this review |
|---|---|---|---|---|
| `bracket_geometry_variants_parked` (status done 11-07) | does any geometry variant (stop level, 5-min bar, established-low entry, re-entry) earn a live arm; re-open if era C reaches ~20 and "disappoints" | §3 Stop (a) + Buy point (b); §3 Exits (d) | the stop / entry arm ladder per era; the "disappoints" fact per era printed as a fact | the 5-min shadow lane and the sweep lanes (Tiers 2–3 of 11-06) — descriptive, re-run only if an arm goes WATCH |
| `live_fill_counterfactuals_first_read_482` (THE ONE exit read; bar 20 paired era-E fills) | on fills under the CURRENT exit rule, paired, does any stop / harvest / trail arm beat what we ran; six sections (fidelity, stop, harvest, trail, regime, running) | §5 + §3 Stop (a), Partials (a), Exits (a); the regime cell table (every arm × `regime` with n, cells under 10 named thin) | the same six sections at WHATEVER era-E n exists, verdicts from the ladder (CAN'T TELL is expected for months); its own predicate count printed so the 20-paired bar is visible | its re-arm at 40 stays in the YAML; the review quotes the predicate, it does not replace the bar |
| `exit_tune_cohort_review` (recurring n = 20/40/…) | per-trade forensic (entry vs plan, MFE before exit, exit reason, hold, regime; classify variance / entry-quality / entry-mechanics / exit-discipline / regime); the intraday partial sweep; regime segmentation | §4 tail rows carry the forensic fields; §3 Partials (b) and Exits (b) carry MFE / capture / hold / reason per era; the regime table | the forensic classification is written on every TAIL row (the five classes, one per trade, by inspection); the wide 34-candidate grid (`_508_exit_rule_replay.py`) is NOT re-run here | the offline grid runs when its own n = 20 era-E bar fires, and quotes the recorder arms as primary where they overlap (its own note) |
| `runner_rule_sweep_recut` (trade-count arm 40 / a live-mode safeguard flip) | does a looser runner rule beat breakeven-after-partial; a rule change voids the last read | §3 Partials (b) "runner shape" count + Exits (b) giveback; a one-line check of `mi_safeguard_state` live/global transitions since the era start | the fact the sweep rests on (winners that gave the runner back to breakeven) counted per era with n; any live-mode toggle since the era start named as "the 08-29 read is void" | the Run-U replay (`_bt_replay.py`) re-runs only on its own trigger; it is $0 but it is a different population |
| `stop_too_wide_outcome_cohort` (bar 20 rejected rows) | does the ORB-range > 1.5 × ATR filter shed winners; REVISIT / KEEP / CANNOT TELL vs the admitted book | §3 Stop (c) | the rejected-vs-admitted matrix with both n and the p, every month, at whatever n exists; REVISIT → WATCH / PROPOSE by the ladder | nothing — this review IS its monthly run; the YAML's threshold becomes a pointer |

**Pointer edits proposed (not made in this task):** each of the five YAML entries gets an
`action_when_ready` line "runs inside PLAN #720's monthly review (`docs/analysis/720_monthly_review_plan_2026-11-08.md` §7)";
`exit_tune_cohort_review` and `live_fill_counterfactuals_first_read_482` keep their own n-bars for the parts
that stay outside (the wide grid, the 40 re-arm).

---

## 8. Interpretations pinned before any number (filled on run day, BEFORE the arm tables are computed)

The 11-06 read pinned eight (I1–I8) where its prereg was silent; they carry over unchanged. Any new case the
data raises on run day is pinned here, numbered I9+, with the rule chosen BEFORE the affected number is
computed and the alternative's effect stated. Template: `I<n> — <case> → <rule>. Changes: <which labels>.`

Known silences settled now:
- **I9 —** a trade present in the window with no `mi_sell_discipline_records` row: peak / capture / giveback
  read "n/a (no record)", the trade stays in every other number.
- **I10 —** a breakout row whose `breakout_day0_pp` or fill-stop marker is missing: the buy-point L3 mix counts
  it as "unchecked"; it stays in R numbers.
- **I11 —** a recorder era mismatch on a FLAGGED (`entry_attempt = 2`) fill is still a stop; the re-entry is a
  different fill, not a different era.

---

## 9. The one page to him (format, fixed)

Plain words. Tables. n on every number. No acronyms without their plain name once. The first line is the
answer.

1. **Line 1 — the answer.** e.g. *"Nothing beats what we run; the tail says X; action: none."*
2. **Population table:** lane × era → closed trades in the window · carried from the era start · excluded
   (ticker list) · fidelity pass / fail (L1).
3. **Lens table:** lens · lane/era · n · the reading in one phrase · verdict (CAN'T TELL / NOTHING / WATCH /
   PROPOSE).
4. **Tail table:** the ≥ +4R and ≤ −1.5R trades, one row each (§4 fields), then the one-sentence read per trade.
5. **Breakout missed-by-slots:** missed n · seated n · the proxy shares · verdict · the absence observables.
6. **Folded reviews:** the five rows of §7 with this month's n and verdict.
7. **Action line, always present:** *"Action: none"* or one line per PROPOSE — *"#<task> (<plain name>):
   write the CHANGE_PROCESS proposal — needs an N ≥ 10 backtest and your sign-off."* Never a fork sent as a
   one-off.

Everything else (every per-fill row, every excluded class, the recorder checks, the regime table) is in the
run folder's `.out` and the dated analysis doc, not on the page.

---

## 10. The runner — contract

`scripts/probes/_720_monthly/run_review.py` (tests: `tests/test_720_monthly_review.py`, invented fixtures only).

- **Capture once, read many.** `capture/*.sql`, each starting `SET default_transaction_read_only = on;` and
  `\copy (...) TO STDOUT WITH CSV HEADER`, run ONCE on run day via
  `docker exec -i apollo-postgres psql -q -X -v ON_ERROR_STOP=1 ... < file.sql > runs/<date>/data/<name>.csv`;
  then `run_review.py --report runs/<date>` reads the CSVs and never the database. `MANIFEST.txt` = row counts
  + md5 per file + the capture timestamp (the thing the 11-06 plan called for and never wrote).
- Queries: `trades.sql` (every `mi_live_trades` row filled on/after the first-window start — closed and open,
  so "still open → next review" is visible) · `skips_window.sql` (the unfilled rows since the start, for the
  label join) · `legacy_paper_count.sql` · `cf_arms.sql` (every recorder row for
  those trade ids) · `sell_discipline.sql` · `daily_bars.sql` (the tickers' daily closes from 20 sessions before
  the first alert to the run date) · `skips_stop_too_wide.sql` + `missed_outcomes.sql` · `breakout_grades.sql` +
  `breakout_list.sql` · `audit_breakout.sql` (missed-by-slots, holds, fill-stop markers, session-third events) ·
  `safeguard_transitions.sql` · `predicates.sql` (the five reviews' predicate counts).
- **Pure functions** over CSV dicts, each unit-tested on invented rows: `lane_of`, `era_of` (refuses
  `breakout_pp` through the magna53 function), `in_window`, `fidelity`, `partial_size_bound`,
  `classify_fidelity_miss`, `era_cell` (the six conditions), `verdict` (the ladder), `tails`,
  `runner_shape_count`, `missed_proxy_walk`, `missed_vs_seated`, `stop_too_wide_matrix`, `render`.
- **Output:** `runs/<date>/review.md` (the one page, §9) + `runs/<date>/review.out` (every per-era arm cell,
  the fidelity result per fill, the recorder checks). The 11-06 fills are flagged from the id column ONLY of
  `scripts/probes/_482_read_1106/data/live_all.csv` (`--read-1106`; no outcome column is read).
- **No prod run before 11-29.** The runner is exercised on fixtures only until then.

---

## 11. What this does not answer (standing)

- **Selection beyond what we took.** The review sees fills and skips; a name that never alerted is visible only
  through his labels and the missed-by-slots record.
- **A verdict on a thin era.** Era E and `bp1` will read CAN'T TELL or WATCH for months at ~3–5 live fills a
  month; that is the honest pace and is reported as such.
- **Anything pooled across eras or lanes.**
- **Any change.** PROPOSE opens a CHANGE_PROCESS proposal; nothing here moves a rule.
