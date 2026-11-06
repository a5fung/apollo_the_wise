# #482 — first cross-arm read (2026-11-06)

**Answer: none of the 13 alternative brackets beat the live bracket in every exit era it could be read in** (four won era D only: `stop_orb_low`, `stop_orb_3r`, `stop_low_of_day`, `harvest_no_breakeven`). Every arm lost at least one exit era, so every label is NOT A CANDIDATE. The current rule stays the best answer for now. Too few trades per era for a ruling either way; any bracket change is still THE LINE (CHANGE_PROCESS, an N ≥ 10 backtest, his sign-off).

- **Bar:** `scripts/probes/_482_read_1106/PREREG.md`, committed `392ab704` before any outcome row was read. Steps: `ANALYSIS_PLAN.md` in the same folder.
- **Script and output:** `scripts/probes/_482_read_1106/read_482.py` → `read_482.out` (captured once). Every number below is printed in `read_482.out`.
- **Status:** the independent recount (plan step 7) RAN blind and MATCHES (`scripts/probes/_482_read_1106/verify/recount.out`, `compare.out`) — every field that feeds a label agrees on all 39 arm-era cells.

## Population

**Rows:** `mi_live_trades`, live MAGNA53, closed, filled on/after 2026-08-16 ET, captured 2026-11-06. **Recorder:** `mi_live_fill_counterfactuals` rows for those fills.

- **n = 20 closed fills.** The gate predicate (alert_date ≥ 08-17) also counts 20. This matches the prereg's expectation.
- **By exit era:** C 7 / D 8 / E 5. The derived era matched the recorder's `exit_era` on every row (0 mismatches).
- **Fidelity failures (excluded from every arm-vs-live number):** OKTA (C), VICR (D), KOD (D), CLS (E). Their replays missed by −1.4402, −1.1119, −0.2902 and +1.1504 R.
- **Paired fills left:** C 6 of 7, D 6 of 8, E 4 of 5.
- ⚠ **VICR (+7.3029R) and KOD (+5.8721R) were the only live fills that reached +4R, and both failed fidelity.** So no paired table in any era contains a big winner. The tail test ("≥ +4R count at least live's") is therefore never under pressure: live's count is 0 on every paired set.
- **Other exclusions:**
  - Non-NULL `pnl_attribution`: none.
  - `entry_attempt = 2`: none.
  - Pending rows (no row yet): 6. These are KOD `trail_character_ma`, IRON `trail_pivot_swing`, AEHR `entry_first_hour_bar`, and APPN `stop_orb_3r`, `entry_first_hour_bar` and `book_first_hour_low_of_day`.
  - Abstain rows: HUM `stop_adr_050` and `stop_adr_075` (D), IRON `stop_adr_075` (E), and AEHR `stop_adr_050` (E). All four are `day0_fill_bar_straddles_stop`.
  - `trail_character_ma` has no character profile on most fills (unscoreable), so it is readable only in era D.
  - R_cap cannot be computed for PENG (D) on `stop_adr_050` and `stop_adr_075`. Each arm's stop (70.35006 and 69.42010) sits above the 69.2 trigger, so no live order could be sized. Both rows are kept in R_own and left out of R_cap (see interpretation I4).
- **Admission mix:** era C spans four admission eras (`adm_pre_2026-08-20` ×3, `adm_2026-08-26_rt_universe_authoritative` ×2, `adm_2026-08-28_rubric_v4_rt_gap_authority` ×1, `adm_2026-08-31_extension_cap_50_slot_rank_rs` ×1). Eras D and E are all `adm_2026-08-31_extension_cap_50_slot_rank_rs`. Not split.
- **Era E sub-change:** the trail arming went live on 2026-10-29 (`exit_logic.TRAIL_ARM_LIVE_FROM`). IRON, SMCI and CLS filled before it; AEHR and APPN filled on or after it. The recorder models it; not split.

## Method

The read follows the prereg exactly. Units:

- **R_cap** is the decision unit: `book_geometry_arms.capped_dollar_r`, imported offline. Stored `realized_r_capped` equalled the recomputed value on 39 of 39 book-module rows.
- **R_own** is the arm's own realized R.
- **pct** and **adr** are context only.

A paired fill has a settled live trade, a replay that passes fidelity, and an arm that can be scored. An era is readable with ≥ 3 paired fills (counted on the R_cap set).

An era is **WON** when all six hold:
- the R_cap delta sum is > 0;
- the R_own delta sum is > 0;
- the R_cap drop-best is > 0;
- the engine-check sign agrees;
- the tail-clip count is 0;
- the arm's ≥ +4R count is at least live's.

There are no horizon rows, so the two label passes (marks excluded / marks counted) are identical.

**Interpretations, pinned before any arm number was computed (the prereg is silent on each):**
- **I1** — When an arm's only readable era is lost, it is NOT A CANDIDATE, not UNREADABLE. This changes one label: `trail_character_ma` would read UNREADABLE under the opposite rule.
- **I2** — "Disappoints" is computed on all cohort fills, because live_actual is the real trade. The fidelity-passing version is shown beside it.
- **I3** — On the hour-bar and book arms, a fill with no entry scores 0 in R_cap. It is left out of the R_own deltas. For the tail and rescue counts, that fill is scored at 0.
- **I4** — A settled row whose R_cap cannot be computed is its own counted class, `rcap_uncomputable`. No substitute trigger is invented.
- **I5** — "Survives drop-best" in Tiers 2 and 3 is applied in both units.
- **I6** — The engine check uses fills where both rows are settled (the prereg's words). Scoring no-entry at 0 instead would flip only `entry_first_hour_bar` era D to WON, and its label would not change (still lost in C).
- **I7** — A no-entry fill scores 0 in adr as well as pct.
- **I8** — An era is readable when the R_cap set holds ≥ 3 fills.

## Labels (Tier 1 — the recorder)

| Arm | Label | Readable eras | Per-era result (n) |
|---|---|---|---|
| `stop_orb_low` | NOT A CANDIDATE | 3 | C LOST (n6) · D WON (n6) · E LOST (n4) |
| `stop_adr_050` | NOT A CANDIDATE | 3 | C LOST (n6) · D LOST (n4) · E LOST (n3) |
| `stop_adr_075` | NOT A CANDIDATE | 3 | C LOST (n6) · D LOST (n4) · E LOST (n3) |
| `stop_orb_3r` | NOT A CANDIDATE | 3 | C LOST (n6) · D WON (n6) · E LOST (n3) |
| `stop_low_of_day` | NOT A CANDIDATE | 3 | C LOST (n6) · D WON (n6) · E LOST (n4) |
| `entry_first_hour_bar` | NOT A CANDIDATE | 2 | C LOST (n6) · D LOST (n6) · E unreadable (n2) |
| `book_first_hour_low_of_day` | NOT A CANDIDATE | 3 | C LOST (n6) · D LOST (n6) · E LOST (n3) |
| `harvest_no_breakeven` | NOT A CANDIDATE | 3 | C LOST (n6) · D WON (n6) · E LOST (n4) |
| `harvest_trail_only` | NOT A CANDIDATE | 3 | C LOST (n6) · D LOST (n6) · E LOST (n4) |
| `harvest_t3` | NOT A CANDIDATE | 3 | C LOST (n6) · D LOST (n6) · E LOST (n4) |
| `harvest_legacy_2r` | NOT A CANDIDATE | 3 | C LOST (n6) · D LOST (n6) · E LOST (n4) |
| `trail_pivot_swing` | NOT A CANDIDATE | 3 | C LOST (n6) · D LOST (n6) · E LOST (n3) |
| `trail_character_ma` | NOT A CANDIDATE | 1 | C unreadable (n1) · D LOST (n4) · E unreadable (n1) |

**Reading the four era-D wins:**
- They came on six trades: five losers plus SEI's small winner.
- The two big era-D winners were not in that set (fidelity).
- `stop_low_of_day` produced the same row as `stop_orb_low` on 18 of 20 fills, so their two era-D wins count as **one** confirmation, not two.
- `harvest_trail_only` era D failed only on the engine check: it walked the same result as live_replay on all six fills, so its +0.06 over live is replay noise.
- The harvest and trail labels are for completeness only. Their decision belongs to `live_fill_counterfactuals_first_read_482` (era E, 20 paired fills), which this read does not satisfy.

## Tier 1 — every arm, every era (tail first; deltas are arm − live)

| Arm | Era | n | arm ≥+2R / ≥+4R | live ≥+2R / ≥+4R | R_cap Δ sum | R_cap drop-best | R_own Δ sum | tail-clip | engine sign | era result |
|---|---|---|---|---|---|---|---|---|---|---|
| `stop_orb_low` | C | 6 | 1 / 0 | 1 / 0 | -0.73 | -1.88 | -0.84 | 0 | agrees (-0.4353) | LOST |
| `stop_orb_low` | D | 6 | 0 / 0 | 0 / 0 | +0.46 | +0.12 | +0.01 | 0 | agrees (+0.4056) | WON |
| `stop_orb_low` | E | 4 | 0 / 0 | 0 / 0 | +0.02 | -0.26 | -1.78 | 0 | agrees (+0.0783) | LOST |
| `stop_adr_050` | C | 6 | 0 / 0 | 1 / 0 | -3.67 | -4.35 | -4.91 | 1 | agrees (-3.3763) | LOST |
| `stop_adr_050` | D | 4 | 0 / 0 | 0 / 0 | -0.19 | -0.51 | -2.50 | 0 | agrees (-0.2290) | LOST |
| `stop_adr_050` | E | 3 | 0 / 0 | 0 / 0 | +0.04 | -0.32 | -1.76 | 0 | agrees (+0.0898) | LOST |
| `stop_adr_075` | C | 6 | 1 / 0 | 1 / 0 | -1.05 | -2.19 | -0.68 | 0 | agrees (-0.7481) | LOST |
| `stop_adr_075` | D | 4 | 0 / 0 | 0 / 0 | +0.65 | +0.34 | -0.06 | 0 | agrees (+0.6093) | LOST |
| `stop_adr_075` | E | 3 | 0 / 0 | 0 / 0 | -0.04 | -0.24 | -0.47 | 0 | disagrees (+0.0173) | LOST |
| `stop_orb_3r` | C | 6 | 0 / 0 | 1 / 0 | -1.43 | -1.77 | -1.19 | 1 | agrees (-1.1303) | LOST |
| `stop_orb_3r` | D | 6 | 0 / 0 | 0 / 0 | +0.67 | +0.16 | +0.79 | 0 | agrees (+0.6135) | WON |
| `stop_orb_3r` | E | 3 | 0 / 0 | 0 / 0 | -0.26 | -0.26 | -0.33 | 0 | agrees (-0.2575) | LOST |
| `stop_low_of_day` | C | 6 | 1 / 0 | 1 / 0 | -0.73 | -1.88 | -1.14 | 0 | agrees (-0.4353) | LOST |
| `stop_low_of_day` | D | 6 | 0 / 0 | 0 / 0 | +0.46 | +0.12 | +0.01 | 0 | agrees (+0.4056) | WON |
| `stop_low_of_day` | E | 4 | 0 / 0 | 0 / 0 | +0.02 | -0.26 | -1.78 | 0 | agrees (+0.0783) | LOST |
| `entry_first_hour_bar` | C | 6 (2 no-entry) | 0 / 0 | 1 / 0 | -1.63 | -2.64 | -3.53 | 1 | agrees (-3.2730) | LOST |
| `entry_first_hour_bar` | D | 6 (5 no-entry) | 0 / 0 | 0 / 0 | +2.37 | +1.50 | +0.07 | 0 | disagrees (-0.0413) | LOST |
| `entry_first_hour_bar` | E | 2 (1 no-entry) | 0 / 0 | 0 / 0 | +0.19 | -0.15 | -0.62 | 0 | disagrees (-0.1537) | not readable |
| `book_first_hour_low_of_day` | C | 6 (2 no-entry) | 0 / 0 | 1 / 0 | -1.80 | -2.81 | -4.03 | 1 | agrees (-3.4469) | LOST |
| `book_first_hour_low_of_day` | D | 6 (5 no-entry) | 0 / 0 | 0 / 0 | +2.45 | +1.57 | -0.03 | 0 | agrees (+0.0377) | LOST |
| `book_first_hour_low_of_day` | E | 3 (1 no-entry) | 0 / 0 | 0 / 0 | +0.22 | -0.13 | -0.56 | 0 | disagrees (-0.1236) | LOST |
| `harvest_no_breakeven` | C | 6 | 0 / 0 | 1 / 0 | -0.48 | -0.49 | -0.49 | 0 | agrees (-0.1853) | LOST |
| `harvest_no_breakeven` | D | 6 | 0 / 0 | 0 / 0 | +0.20 | +0.04 | +0.27 | 0 | agrees (+0.1446) | WON |
| `harvest_no_breakeven` | E | 4 | 0 / 0 | 0 / 0 | +0.13 | -0.04 | +0.63 | 0 | agrees (+0.1858) | LOST |
| `harvest_trail_only` | C | 6 | 1 / 0 | 1 / 0 | -0.42 | -0.59 | -0.48 | 0 | agrees (-0.1224) | LOST |
| `harvest_trail_only` | D | 6 | 0 / 0 | 0 / 0 | +0.06 | +0.04 | +0.07 | 0 | disagrees (+0.0000) | LOST |
| `harvest_trail_only` | E | 4 | 0 / 0 | 0 / 0 | -0.08 | -0.08 | -0.18 | 0 | agrees (-0.0248) | LOST |
| `harvest_t3` | C | 6 | 1 / 0 | 1 / 0 | +0.32 | -0.61 | +0.32 | 1 | agrees (+0.6228) | LOST |
| `harvest_t3` | D | 6 | 0 / 0 | 0 / 0 | -0.19 | -0.20 | -0.25 | 0 | agrees (-0.2429) | LOST |
| `harvest_t3` | E | 4 | 0 / 0 | 0 / 0 | +0.13 | -0.04 | +0.63 | 0 | agrees (+0.1858) | LOST |
| `harvest_legacy_2r` | C | 6 | 0 / 0 | 1 / 0 | -0.30 | -0.30 | -0.29 | 0 | disagrees (+0.0000) | LOST |
| `harvest_legacy_2r` | D | 6 | 0 / 0 | 0 / 0 | -0.01 | -0.03 | -0.02 | 0 | agrees (-0.0717) | LOST |
| `harvest_legacy_2r` | E | 4 | 0 / 0 | 0 / 0 | +0.31 | -0.04 | +1.30 | 0 | agrees (+0.3600) | LOST |
| `trail_pivot_swing` | C | 6 | 0 / 0 | 1 / 0 | -1.51 | -1.51 | -1.49 | 1 | agrees (-1.2105) | LOST |
| `trail_pivot_swing` | D | 6 | 0 / 0 | 0 / 0 | +0.63 | -0.17 | +0.92 | 0 | agrees (+0.5750) | LOST |
| `trail_pivot_swing` | E | 3 | 0 / 0 | 0 / 0 | -0.05 | -0.06 | -0.08 | 0 | agrees (-0.0000) | LOST |
| `trail_character_ma` | C | 1 | 0 / 0 | 0 / 0 | -0.04 | +0.00 | -0.05 | 0 | disagrees (+0.0000) | not readable |
| `trail_character_ma` | D | 4 | 0 / 0 | 0 / 0 | -0.49 | -0.51 | -0.57 | 0 | agrees (-0.5383) | LOST |
| `trail_character_ma` | E | 1 | 0 / 0 | 0 / 0 | -0.05 | +0.00 | -0.07 | 0 | disagrees (+0.0000) | not readable |

Medians, better/worse/tie counts, rescues, the pct and adr deltas and every per-fill row are in `read_482.out` §3. No arm reached +4R on any paired fill in any era. The ≤ −1.5R count is 0 everywhere except `stop_adr_050` era D (1, CEG).

## "Disappoints" per era (the parked review's re-open word — a fact, not a decision)

| Era | n (all cohort fills) | live R_cap sum | fills ≥ +4R | Disappoints? | Fidelity-passing only (n · sum · result) |
|---|---|---|---|---|---|
| C | 7 | +2.41 | 0 | no | 6 · +1.39 · no |
| D | 8 | +1.77 | 2 | no | 6 · -3.06 · yes |
| E | 5 | -1.25 | 0 | **yes** | 4 · -1.11 · yes |

The depth-exit era (E) lost money in capped dollars with no big winner. Whether to re-open geometry work is his call; this read does not make it.

## Recorder checks (reported; none stops the read)

- **HOOD (era C, alert 09-03):** all 11 of its follows-live rows walked 8/3 rather than era C's 2/NULL. It passes fidelity, so it stays.
- **Era C `harvest_legacy_2r` = `live_replay`:** equal on all 7 fills.
- **`stop_low_of_day` = `stop_orb_low`:** the same row on 18 of 20 fills, and on 11 of 11 fills at 09:31.
- **Hour-bar arms (selection effect):** they see only fills whose 1-minute ORB high filled. An alert that took only the hour high is invisible to them.

## Fill facts (descriptive)

| Era | n | fill vs trigger: median / max | fills > +1% over trigger | real risk ÷ trigger risk: median / max |
|---|---|---|---|---|
| C | 7 | +0.47% / +2.13% | 2 (CRWD, HOOD) | 1.047 / 1.432 |
| D | 8 | +0.29% / +4.35% | 1 (PENG) | 1.038 / 1.430 |
| E | 5 | +0.05% / +0.51% | 0 | 1.015 / 1.074 |

## Tier 2 — the 5-minute ORB shadow lane (descriptive; can only nominate)

The 5-minute lane uses a different entry, stop and daily-bar exit from live in every era. Pairs are matched to the live twin on ticker and alert date; the era comes from the live row. Fidelity does not apply, because both sides are real rows.

| Era | pairs n | R delta (5m − live) · drop-best | ADR delta · drop-best | Beats live? |
|---|---|---|---|---|
| C | 3 | -0.37 · -0.37 | +0.11 · -0.26 | NO |
| D | 3 | -2.91 · -2.91 | -2.55 · -2.29 | NO |
| E | 2 | -0.73 · -0.71 | -2.21 · -1.20 | (under 3 pairs, not eligible) |

**Nothing is nominated.** The 08-18 finding stands: widening the opening-range bar does not help. Per-pair rows are in `read_482.out` §7.

## Tier 3 — the sweep copy (descriptive; can only nominate a recorder arm)

The sweep runs one exit policy in every era, which is not the live ladder in eras D and E. Lane W (enter at an established intraday low) is scored against B2, the live stop inside the sweep's engine; a day with no entry scores 0. Re-entry is scored as the increment over B0 on days a re-entry fired, with conservative sequencing.

| Lane | Era | n | R delta · drop-best | ADR delta · drop-best | Beats control? |
|---|---|---|---|---|---|
| W vs B2 | C | 7 | -0.83 · -1.83 | -1.02 · -2.88 | no |
| W vs B2 | D | 8 | +1.38 · +0.14 | +4.74 · +2.42 | yes |
| W vs B2 | E | 5 | -0.51 · -1.51 | -2.21 · -3.44 | no |
| A_cons − B0 (re-entry, ORB-low stop) | C | 4 | -2.82 · -5.16 | -0.61 · -2.54 | no |
| A_cons − B0 | D / E | 2 / 2 | under 3 rows | under 3 rows | not eligible |
| Apdl_c − B0 (re-entry, prior-day-low stop) | C | 4 | -5.57 · -7.92 | -1.90 · -3.83 | no |
| Apdl_c − B0 | D / E | 2 / 2 | under 3 rows | under 3 rows | not eligible |

- **Nothing is nominated.** W wins only in era D, and 5 of its 8 era-D days are no-entry days scored 0. The re-entry lanes are eligible in era C only and lose there.
- The optimistic sequencing gave the same increments on every re-entry day.
- C05, C10 and CPDL are printed in `out/s572_cde.txt` and not read.

## Deviations from the prereg and the plan

- **File names:** the script is `read_482.py` (the plan called it `cross_arm_read.py`), and every file sits in `scripts/probes/_482_read_1106/` (the plan named `_482_cross_arm_1106/`). The task that ran it set both.
- **Unspecified cases:** interpretations I1–I8 above. Only I1 changes a label (`trail_character_ma`: NOT A CANDIDATE vs UNREADABLE). Neither reading makes it a candidate.
- **PENG's ADR-arm R_cap is undefined** (the stop sits above the trigger). The prereg has no class for this; see I4.
- **B2 follows the plan's formula:** stop = fill − 2×(fill − ORB low). The real live stop is in the trigger's frame (2×ORB low − ORB high). So B2's stop differs from the real one by 2×(fill − trigger). Not changed.
- **Still to do:**
  - Plan step 2's `data/MANIFEST.txt` (row counts + md5) does not exist.
  - Plan step 7 (the independent recount): done, matches (see Status).

## What this does not answer

- **Any verdict.** No era holds 10 paired fills (6 / 6 / 4 after fidelity), so no live-arm candidate could come out of this read under any result.
- **The big winners.** The only two ≥ +4R live fills (VICR, KOD) failed the replay fidelity check, so the read cannot say how any arm treats a big winner.
  - The tail test passed trivially in every era. The fidelity misses on 4 of 20 fills are a recorder question in their own right.
- **Selection.** The read sees only fills we took. Skipped or never-alerted names are invisible, including to the hour-bar arms, which also see only fills whose 1-minute ORB high filled.
- **Fill realism** of simulated entries (hour bar, W, re-entry). Share rounding, breakers, position caps and the daily loss limit are not modelled either.
- **Exit-rule decisions.** These belong to `live_fill_counterfactuals_first_read_482` (era E only, 20 paired fills), which is not met.
- **The book's primary entry** (the first 5-minute bar on the live ladder). It is recorded nowhere.
- **Untested ideas.** The 08-18 ideas were never tested here: a first entry on a later day, the pivot ladder, proximity, and the 620 trigger.
- **Anything pooled across eras.** Nothing here sums across C, D and E.
