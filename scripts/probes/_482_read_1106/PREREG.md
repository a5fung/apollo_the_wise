## #482 — first cross-arm read: PRE-REGISTRATION (written 2026-11-06, committed before any outcome row is read)

**What triggers it.** #482's DONE-WHEN reads: *"20 distinct trades logged AND the first cross-arm read reported to him"*. The DoD is *"a shadow lab logging realized-R per bracket variant → enough evidence for an informed operator geometry decision"*. The gate `bracket_geometry_variants_parked` counts closed live MAGNA53 trades with alert_date ≥ 2026-08-17, and it reached 20 on 2026-11-05.

**What this read is.** It is a split report, not a verdict. By exit era the cohort is about C 7 / D 8 / E 5, so no era holds the N ≥ 10 that CHANGE_PROCESS needs. **No live-arm candidate can come out of this read.** Any bracket change still goes through THE LINE: CHANGE_PROCESS, an N ≥ 10 backtest and his sign-off.

**Seen before this was written:** the per-era fill counts (11-04 sweep: C 7 / D 8 / E 4), and the 09-04 night-one arm means on 6 era-C fills (stop_adr_050 −0.661R, harvest_t3 +0.422R, stop_orb_low +0.028R). No rule below was tuned to them.

### Population
- **Cohort:** `mi_live_trades` rows with account_mode `live`, signal_type `magna53`, filled on/after 2026-08-16 ET, status `closed`. The expected count is 20; if it differs, the actual count is reported and the read proceeds.
- **Exit era comes from the trade's own row:** `exit_rule = 'depth'` → E; else alert_date ≥ 2026-09-06 → D; else C. This must equal the recorder's `exit_era` for every trade. **A mismatch stops the read.**
- **Eras are never pooled.** No total line appears anywhere.
- **Excluded and listed:** trades with a non-NULL `pnl_attribution`, and fills that fail the fidelity check below.
- **Kept and flagged:** `entry_attempt = 2` fills.
- **Admission changes inside an exit era** (e.g. #718 on 11-03) are reported as the `admission_era` mix per exit era. They are not split further.
- **Era E sub-change:** era E holds a trail-arming change from 10-29 (`exit_logic.TRAIL_ARM_LIVE_FROM`). The recorder models it; it is not split.

### Tier 1 — the recorder `mi_live_fill_counterfactuals` (the lab; decision-grade for this report)
- **Arms.**
  - Controls: `live_actual`, `live_replay`.
  - Stop arms: `stop_orb_low`, `stop_adr_050`, `stop_adr_075`, `stop_orb_3r`, `stop_low_of_day`.
  - Entry and book arms: `entry_first_hour_bar`, `book_first_hour_low_of_day`.
  - Harvest arms: `harvest_no_breakeven`, `harvest_trail_only`, `harvest_t3`, `harvest_legacy_2r`.
  - Trail arms: `trail_pivot_swing`, `trail_character_ma`.
  - `fill_facts` is descriptive only.
- **Units for each arm on each fill:**
  - **R_cap — the decision unit.** This is the capped-dollar R from `book_geometry_arms.capped_dollar_r(row)`, i.e. realized R × the risk the live sizing rule would have placed. It applies to every arm, controls included; it is the H10 rule that any stop is scored in capped dollars.
  - R_own = `realized_r`.
  - pct = `realized_pct`.
  - adr = `pnl_adr`.
- **Outcome classes:**
  - `settled` → its value.
  - `horizon` → `mark_r`, which is a mark and never a return.
  - Book-arm `unscoreable` with `final_reason` starting `no_entry:` → no trade. It scores 0 in R_cap and pct and is excluded from R_own.
  - `abstain`, any other `unscoreable`, and a missing row (still pending) → excluded and counted.
- **Fidelity check.** A fill passes when both controls are settled and |live_replay R − live_actual R| ≤ 0.25R. Arm-vs-live numbers are quoted on passing fills only, and the failures are listed.
- **"Paired fills" for an arm in an era** = live_actual settled, the fill passes fidelity, and the arm is scoreable.
- **Computed for each arm in each era, on paired fills:**
  - n, plus the count of every excluded class.
  - Tail first:
    - Count of results ≥ +2R and ≥ +4R (R_own), for the arm and for live on the same fills.
    - The maximum.
    - The count of results ≤ −1.5R (worse than a full loss).
  - Paired delta (arm − live_actual) in R_cap and in R_own:
    - Sum and median.
    - Better / worse / tie counts (a tie is |Δ| ≤ 0.05).
    - Drop-best: the sum minus the single largest delta.
  - Tail-clip: on fills where live_actual R_own ≥ +2, the count where the arm's R_cap is more than 0.5 below live's.
  - Rescues: on fills where live_actual R_own ≤ −0.9, the count where the arm's R_own > 0.
  - Engine check: Σ(arm − live_replay) in R_cap over fills where both are settled, and whether its sign agrees with the vs-actual sum.
  - pct and adr deltas (sum, median), as context.
- **Recorder checks.** These are reported and do not stop the read:
  - Follows-live rows should carry `target_r`/`breakeven_arm_r` of 2/NULL in era C and 8/3 in eras D and E. Disagreements are listed, and the fidelity check decides whether they stay.
  - In era C, `harvest_legacy_2r` should equal `live_replay`.
  - `stop_low_of_day` equals `stop_orb_low` on 09:31 fills. The rate of identical rows is stated so the two arms are not counted as two confirmations.
  - The hour-bar arms only see fills where the 1-minute ORB high filled (the selection effect). This is stated with them.

### Pre-registered label for each arm (applied mechanically)
- **Readable era:** ≥ 3 paired fills.
- **An era is WON** when all six hold:
  - The R_cap delta sum is > 0.
  - The R_own delta sum is > 0.
  - Drop-best R_cap is > 0.
  - The engine-check sign agrees.
  - The tail-clip count is 0.
  - The arm's ≥ +4R count is at least live's.
- **WATCH-LIST:** at least 2 readable eras, and every readable era WON. Era E must also be readable and WON; if E is unreadable, the label is "WATCH-LIST, pending era E".
- **NOT A CANDIDATE:** any readable era is not WON.
- **UNREADABLE:** fewer than 2 readable eras.
- **Horizon:** every label is computed twice, once with marks excluded and once with marks counted at `mark_r`. If the two differ, the label is **UNRESOLVED (horizon)**.
- **What WATCH-LIST means.** It is not a live-arm candidate. It means the arm is put to him as worth a focused re-read. Live candidacy needs the same test WON in the current exit era on ≥ 10 paired fills, then CHANGE_PROCESS, an N ≥ 10 backtest and his sign-off. "The current rule is best" is a real answer and is reported as one.
- **Harvest and trail arms** get the same label for completeness. Their decision belongs to `live_fill_counterfactuals_first_read_482` (era E, 20 paired fills), which this read does not satisfy.
- **"Disappoints"** (the parked review's own re-open word): in a given era, live_actual's R_cap sum is < 0 and no fill reached ≥ +4R. It is reported per era as a fact. Re-opening geometry work is his call.

### Tier 2 — the 5-minute ORB shadow lane (descriptive; can only nominate)
- **Source:** `mi_orb_shadow_trades`, bar size 5, closed, not quarantined, MAGNA53, alert_date ≥ 2026-08-17. Rows are paired to cohort fills on (ticker, alert_date), and the era is taken from the live twin's row.
- **Confound:** this lane exits on a daily-bar ladder, with a day-3/5 partial, no +8R partial, no price-armed breakeven and no depth rule. Entry, stop AND exit therefore all differ from live in every era.
- **Reported:** the rows for each pair, plus n and sums per era in per-share R and ADR units.
- **Nominate rule:** it may nominate a shadow arm (a 5-minute-bar entry walked on the live ladder) only if the 5-minute lane beats live in both units in every era with ≥ 3 pairs, in at least 2 such eras, and survives drop-best. Otherwise the 08-18 finding stands: widening the opening-range bar does not help.

### Tier 3 — sweep copy, for variants the recorder lacks (can only nominate)
- **Lanes read:**
  - W: entry at an established intraday low.
  - A_cons / A_opt: re-entry up to 2× with an ORB-low stop.
  - Apdl_c / Apdl_o: re-entry with a prior-day-low stop.
- C05 / C10 / CPDL are printed but not read; the recorder's ADR and ORB stop arms answer that question on the live ladder.
- **Control:** a new lane **B2** = the real entry, stop at entry − 2×(entry − ORB low), and the target pinned at entry + 2×(entry − ORB low). That is the live stop inside the sweep's engine. B0 (the ORB-low stop, retired 08-16) is **not** the control; using it is the 08-29 retraction's defect.
- **Exit:** the sweep's single policy in every era is half off at +2R → breakeven → SMA trail → 20 days. That is not the live ladder in eras D and E, so the era slices separate populations, not exits.
- **Scoring:** W is scored on every full-session day, with a no-entry day scored 0. Re-entry is scored as the increment (A − B0) on days when a re-entry fired. Conservative sequencing decides; the optimistic result is shown beside it.
- **Nominate rule:** a lane is nominated as a recorder arm (shadow only, no money) only if it beats B2 (for W), or adds over B0 (for re-entry), in BOTH R and ADR units, in every era with ≥ 3 rows, in at least 2 such eras, and survives drop-best (the INTC lesson). Otherwise nothing is nominated.

### Descriptive — fill facts
For each era: `fill_vs_trigger_pct` (median, max, count above +1%) and `real_risk_vs_trigger_risk` (median, max). There is no threshold. It is counted because PENG on 10-07 asked the lab to count it.

### What this read cannot answer
- **Any verdict:** no era holds 10.
- **Selection:** the read sees only fills we took. Skipped or never-alerted names are invisible, including to the hour-bar arms.
- **Fill realism** of simulated entries (hour bar, W, re-entry). Share rounding, breakers, position caps and the daily loss limit are not modelled either.
- **Exit-rule decisions:** those belong to the ONE exit read.
- **The book's primary entry** (the first 5-minute bar) on the live ladder: it is recorded nowhere today.
- **The 08-18 ideas that were never tested:** a first entry on a later day, the pivot ladder, proximity, and the 620 trigger. The delayed-entry lanes own those.
- **Anything pooled across eras.**