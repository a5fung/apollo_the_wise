# #720 monthly trade review — 2026-11-21

**4 arm(s) on watch (beat what we run, but on under 10 trades; nothing proposed); 8 did not beat it, 1 unreadable; big winners 2, bad losers 1; action: none.**

Window: trades closed 2026-08-16 to 2026-11-21 (ET). Eras are cumulative from each era's start; nothing is pooled across eras or lanes.

## Population

| Lane | Era | closed in window | carried from era start | still open | excluded | no R frame | re-entries |
|---|---|---|---|---|---|---|---|
| L1 | era_c | 7 | 0 | 0 | — | — | — |
| L1 | era_d | 8 | 0 | 0 | — | — | — |
| L1 | era_e | 7 | 0 | 0 | — | — | — |
| L3 | bp1 | 17 | 0 | 3 | MTW, ABCL, OUST, AMLX, ZYME | — | — |

Trades filled before the first window start and closed inside a window (era-B stop; not in the capture): live/magna53 2.

Legacy `mi_paper_trades` rows closed in the window: 0.0 (expected 0).

Recorder coverage (L1): era_c: 7 fills, 7 with recorder rows, 7 settled control pairs; era_d: 8 fills, 8 with recorder rows, 8 settled control pairs; era_e: 7 fills, 7 with recorder rows, 7 settled control pairs.
Recorder heartbeat: the 18:04 ET job wrote its nightly row on 54 of 55 sessions since 2026-09-04 (the job's first session; the window starts earlier) (last 2026-11-20); sessions with no row: 2026-09-18; error rows 0.

Replay fidelity (§5: within max(0.25R, 10% of the real R); the replay's partial re-weighted to the shares the live sizer sold): 20 of 22 fills pass — 19 on the stored replay, 1 only after re-weighting (their arms are compared with the replay) — 18 under the old 0.25R bar; failures by class: exit_session_differs 2.

## Lenses

| Lens | Lane / era | n | reading | verdict |
|---|---|---|---|---|
| buy_point: entry_first_hour_bar | L1 / era_e | 4 | era_e WON on n 4 (< 10); context: era_c lost (n 6); era_d lost (n 8); pre-11-04 3 / post 1 | WATCH |
| buy_point: book_first_hour_low_of_day | L1 / era_e | 4 | era_e lost on n 4; context: era_c lost (n 6); era_d lost (n 8); pre-11-04 3 / post 1 | NOTHING |
| stop: stop_orb_low | L1 / era_e | 6 | era_e lost on n 6; context: era_c lost (n 6); era_d won (n 8); pre-11-04 3 / post 3 | NOTHING |
| stop: stop_adr_050 | L1 / era_e | 5 | era_e lost on n 5; context: era_c lost (n 6); era_d won (n 6); pre-11-04 2 / post 3 | NOTHING |
| stop: stop_adr_075 | L1 / era_e | 5 | era_e lost on n 5; context: era_c lost (n 6); era_d won (n 6); pre-11-04 2 / post 3 | NOTHING |
| stop: stop_orb_3r | L1 / era_e | 6 | era_e lost on n 6; context: era_c lost (n 6); era_d lost (n 8); pre-11-04 3 / post 3 | NOTHING |
| stop: stop_low_of_day | L1 / era_e | 6 | era_e lost on n 6; context: era_c lost (n 6); era_d won (n 8); pre-11-04 3 / post 3 | NOTHING |
| partials: harvest_no_breakeven | L1 / era_e | 6 | era_e WON on n 6 (< 10); context: era_c lost (n 6); era_d lost (n 8); pre-11-04 3 / post 3 | WATCH |
| partials: harvest_trail_only | L1 / era_e | 6 | era_e lost on n 6; context: era_c lost (n 6); era_d won (n 8); pre-11-04 3 / post 3 | NOTHING |
| partials: harvest_t3 | L1 / era_e | 6 | era_e WON on n 6 (< 10); context: era_c lost (n 6); era_d lost (n 8); pre-11-04 3 / post 3 | WATCH |
| partials: harvest_legacy_2r | L1 / era_e | 6 | era_e WON on n 6 (< 10); context: era_c lost (n 6); era_d lost (n 8); pre-11-04 3 / post 3 | WATCH |
| exits: trail_pivot_swing | L1 / era_e | 6 | era_e lost on n 6; context: era_c lost (n 6); era_d lost (n 8); pre-11-04 3 / post 3 | NOTHING |
| exits: trail_character_ma | L1 / era_e | 2 | era_e: n 2 < 3; context: era_d lost (n 5); pre-11-04 0 / post 2 | CAN'T TELL |
| selection: his EP labels | L1 | 2 | MRNA traded, CHPT abstention, PENG traded | NOTHING |
| selection: his breakout grades (chart sheets) | L3 / bp1 | 0 | graded 0 of 12 (ungraded 12) | CAN'T TELL |
| buy point: fill vs trigger | L1 / era_c | 7 | median +0.47% max +2.13% over +1%: 2 (R_cap sum -0.23 vs +2.64); fill vs trigger unknown on 0; real risk ÷ trigger risk median +1.047 max +1.432; fill minutes 09:31 1, 09:32 2, 09:33 1, 09:34 1, 09:36 1, 09:49 1 | context (CAN'T TELL) |
| buy point: fill vs trigger | L1 / era_d | 8 | median +0.29% max +4.35% over +1%: 1 (R_cap sum -0.87 vs +2.65); fill vs trigger unknown on 0; real risk ÷ trigger risk median +1.038 max +1.430; fill minutes 09:31 5, 09:33 1, 09:35 2 | context (CAN'T TELL) |
| buy point: fill vs trigger | L1 / era_e | 7 | median +0.25% max +0.51% over +1%: 0 (R_cap sum +0.00 vs -2.44); fill vs trigger unknown on 0; real risk ÷ trigger risk median +1.042 max +1.149; fill minutes 09:31 7 | CAN'T TELL |
| stop: stopped out, then ran | L1 / era_c | 7 | 2 of 7 stop-outs printed +2R within 5 sessions (0 not judgeable); stop width median +6.92% / +1.58 ADR | descriptive |
| partials: fired / kept | L1 / era_c | 7 | partial fired 3; median capture +0.30; median giveback +1.30R; runner shape — partial then breakeven 1 (era C's), armed then breakeven 0 (eras D/E's, the row's own arm; n/a on 6 with no price-armed breakeven); ≤2-share positions 1; no record 0 | descriptive |
| exits: how trades ended | L1 / era_c | 7 | stop_hit 7; depth sales 0; median hold 8.0 days; median peak +1.31R vs kept +0.40R; disappoints (live R_cap sum +2.41 on 7): no | descriptive |
| stop: stopped out, then ran | L1 / era_d | 8 | 2 of 8 stop-outs printed +2R within 5 sessions (0 not judgeable); stop width median +7.80% / +1.71 ADR | descriptive |
| partials: fired / kept | L1 / era_d | 8 | partial fired 1; median capture -0.99; median giveback +1.42R; runner shape — partial then breakeven 0 (era C's), armed then breakeven 0 (eras D/E's, the row's own arm; n/a on 0 with no price-armed breakeven); ≤2-share positions 3; no record 0 | descriptive |
| exits: how trades ended | L1 / era_d | 8 | stop_hit 8; depth sales 0; median hold 5.0 days; median peak +0.64R vs kept -0.91R; disappoints (live R_cap sum +1.77 on 8): no | descriptive |
| stop: stopped out, then ran | L1 / era_e | 6 | 0 of 6 stop-outs printed +2R within 5 sessions (1 not judgeable); stop width median +7.21% / +1.18 ADR; pre-11-04 4 / post 3 | descriptive |
| partials: fired / kept | L1 / era_e | 7 | partial fired 0; median capture -1.12; median giveback +1.80R; runner shape — partial then breakeven 0 (era C's), armed then breakeven 0 (eras D/E's, the row's own arm; n/a on 0 with no price-armed breakeven); ≤2-share positions 1; no record 0; pre-11-04 4 / post 3 | descriptive |
| exits: how trades ended | L1 / era_e | 7 | stop_hit 6, sma_trail_stop 1; depth sales 1 (next-open sale vs signal close median +0.10R on 1); median hold 2.0 days; median peak +1.31R vs kept -0.98R; disappoints (live R_cap sum -2.44 on 7): yes; pre-11-04 4 / post 3 | descriptive |
| stop: stopped out, then ran | L3 / bp1 | 0 | 0 of 0 stop-outs printed +2R within 5 sessions (12 not judgeable); stop width median +3.28% / +0.78 ADR | descriptive |
| partials: fired / kept | L3 / bp1 | 12 | partial fired 1; median capture -4.52; median giveback +1.27R; runner shape — partial then breakeven 1 (era C's), armed then breakeven 0 (eras D/E's, the row's own arm; n/a on 12 with no price-armed breakeven); ≤2-share positions 0; no record 0 | descriptive |
| exits: how trades ended | L3 / bp1 | 12 | stop_hit 12; depth sales 0; median hold 1.5 days; median peak +0.21R vs kept -1.03R; disappoints (live R_cap sum n/a on 0): n/a (no recorder) | descriptive |
| stop: the stop-too-wide filter | magna53 skips vs admitted (both modes, since 05-05) | 11 | rejected 11 hit +0.36 median MFE +9.51% vs admitted 34 hit +0.71 median +14.71%; KEEP (two-sided p 0.072); unscored 1 / 0; admitted modes live 22, paper 12; admitted admission eras adm_2026-08-26_rt_universe_authoritative 2, adm_2026-08-28_rubric_v4_rt_gap_authority 1, adm_2026-08-31_extension_cap_50_slot_rank_rs 10, adm_2026-11-04_open_below_floor 1, adm_pre_2026-08-20 20 | NOTHING |
| buy point: fill vs list level / fill-stop decision / thirds | L3 / bp1 | 20 | fill vs level median +0.42% max +3.07% on 20; fill-stop decisions kept 19, unchecked 1; thirds +2R 2, none 18 | descriptive |
| breakout: missed by slots vs seated | L3 / bp1 | 0 | +2R-before-stop share missed n/a vs seated n/a; median MFE missed n/aR vs seated n/aR | CAN'T TELL |

## The tail (the real trades; never gated by fidelity)

**≥ +4R winners: 2**

| Ticker | Lane | Era | alert | fill min | shares | fill vs trigger | stop % / ADR | peak R (session) | R | capture | exit legs | hold | regime | admission era | label | best / worst arm | fidelity | 10-session high after exit (R) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| VICR | L1 | era_d | 2026-09-17 | 09:31 | 1.0 | -0.22% | +4.90 / +0.77 | +11.52 (11.0) | +7.30 | +0.63 | stop_hit@+7.30R 2026-10-07 | 15.0 | Crisis | adm_2026-08-31_extension_cap_50_slot_rank_rs | — | stop_orb_low +12.97 / trail_character_ma +2.54 | pass (reweighted) | +6.34 |
| KOD | L1 | era_d | 2026-09-28 | 09:31 | 5.0 | +0.40% | +8.03 / +1.46 | +8.06 (4.0) | +5.87 | +0.73 | partial_profit@+4.34R 2026-09-28; stop_hit@+6.26R 2026-10-13 | 12.0 | Correcting | adm_2026-08-31_extension_cap_50_slot_rank_rs | — | stop_adr_050 +16.24 / entry_first_hour_bar +0.13 | pass (stored) | +6.51 |

**≤ -1.5R losers: 1**

| Ticker | Lane | Era | alert | fill min | shares | fill vs trigger | stop % / ADR | peak R (session) | R | capture | exit legs | hold | regime | admission era | label | best / worst arm | fidelity | 10-session high after exit (R) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| CRWV | L1 | era_e | 2026-11-11 | 09:31 | 14.0 | +0.25% | +6.22 / +0.67 | +1.43 (1.0) | -1.60 | -1.12 | stop_hit@-1.60R 2026-11-12 | 2.0 | Correcting | adm_2026-11-04_open_below_floor | — | harvest_t3 -0.79 / harvest_trail_only -1.71 | pass (stored) | n/a |

## Breakout: names that broke out but never got a paper slot

Missed records 91 (mature 0; 0 dropped by the width rule, 0 unreadable JSON), seated trades the same days 15 (mature 0; all seated breakout trades 20); +2R-before-stop share missed n/a vs seated n/a; median MFE (R) missed n/a vs seated n/a. Verdict: CAN'T TELL.
Absence check: missed 91 of 111 held rows (observables: {'hold_rows': 695, 'slots_full_holds': 111, 'seated_trades': 20, 'list_nights': 16, 'toggle': 'on', 'entry_day_rows': 4, 'unreadable_rows': 0, 'strategy_enabled': True, 'strategy_phase': 'paper', 'env_default': 'not captured'}).

## The five folded reviews

| Review | predicate count (its own bar) | verdict here |
|---|---|---|
| bracket_geometry_variants_parked | 22 | WATCH |
| live_fill_counterfactuals_first_read_482 | 7 | WATCH |
| exit_tune_cohort_review | 7 | WATCH |
| runner_rule_sweep_recut | 7 | descriptive |
| stop_too_wide_outcome_cohort | 11 | NOTHING |

Live/global safeguard transitions since the current era start (each one = the 08-29 runner read is void): none.

**Action: none**

## Every closed trade in the window (the forensic fields; the classification is written by inspection on run day)

39 trade(s).

| id | Ticker | Lane | Era | alert | fill min | shares | fill vs trigger | stop % / ADR | peak R | R | exit | legs | hold | regime | admission era | post-11-04 | label | read 11-06 | fidelity | 10-session high after (R) | class |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 372 | AMLX | L1 | era_c | 2026-08-18 | 09:32 | 16.0 | +0.47% | +10.33 / +1.58 | +3.50 | +1.26 | stop_hit | partial_profit@+1.04R 2026-08-18; stop_hit@+1.36R 2026-08-31 | 10.0 | Bull | adm_pre_2026-08-20 | no | — | yes | pass | +1.69 | exit-discipline: winner; kept +1.26R of a +3.50R peak (36%) via partial then trail stop, 10 days |
| 373 | MRVL | L1 | era_c | 2026-08-19 | 09:32 | 4.0 | -0.01% | +4.70 / +0.72 | +0.35 | -0.95 | stop_hit | stop_hit@-0.95R 2026-08-19 | 1.0 | Bull | adm_pre_2026-08-20 | no | — | yes | pass | +1.15 | entry-mechanics: stop 0.72 ADR hit 31 min after fill at -0.95R; price then reached +1.15R within 10 sessions |
| 374 | MRNA | L1 | era_c | 2026-08-19 | 09:33 | 4.0 | +0.50% | +9.03 / +1.61 | +5.13 | +2.08 | stop_hit | partial_profit@+1.62R 2026-08-19; stop_hit@+2.23R 2026-09-03 | 12.0 | Bull | adm_pre_2026-08-20 | no | his EP | yes | pass | +3.78 | exit-discipline: his EP; kept +2.08R of +5.13R peak (41%); stopped at +2.23R, then +3.78R high within 10 sessions |
| 383 | CRWD | L1 | era_c | 2026-08-27 | 09:31 | 3.0 | +1.13% | +5.64 / +1.26 | +1.31 | +0.40 | stop_hit | partial_profit@+1.20R 2026-08-27; stop_hit@-0.00R 2026-08-28 | 2.0 | Choppy | adm_2026-08-26_rt_universe_authoritative | no | — | yes | pass | +2.17 | exit-discipline: partial at +1.20R, remainder stopped at breakeven next day; price then reached +2.17R |
| 382 | OKTA | L1 | era_c | 2026-08-27 | 09:49 | 2.0 | -0.00% | +10.34 / +2.30 | +2.57 | +1.36 | stop_hit | stop_hit@+1.36R 2026-09-28 | 22.0 | Choppy | adm_2026-08-26_rt_universe_authoritative | no | — | yes | fail: exit_session_differs | +3.87 | exit-discipline: kept +1.36R of +2.57R peak over 22 days; +3.87R high after exit; replay fidelity failed |
| 388 | SOLS | L1 | era_c | 2026-08-28 | 09:34 | 12.0 | +0.03% | +6.11 / +1.71 | +0.18 | -1.00 | stop_hit | stop_hit@-1.00R 2026-08-31 | 2.0 | Bull | adm_2026-08-28_rubric_v4_rt_gap_authority | no | — | yes | pass | -0.27 | variance: clean fill and stop, peak +0.18R, stopped day 2 at -1.00R in Bull; no defect in the fields |
| 392 | HOOD | L1 | era_c | 2026-09-03 | 09:36 | 4.0 | +2.13% | +6.92 / +1.42 | +0.84 | -0.84 | stop_hit | stop_hit@-0.84R 2026-09-15 | 8.0 | Correcting | adm_2026-08-31_extension_cap_50_slot_rank_rs | no | — | yes | pass | +1.02 | entry-mechanics: filled +2.13% above trigger; peak +0.84R, stopped at -0.84R after 8 days in Correcting |
| 394 | PHVS | L1 | era_d | 2026-09-08 | 09:31 | 3.0 | +0.29% | +8.33 / +1.75 | +0.36 | -1.02 | stop_hit | stop_hit@-1.02R 2026-09-08 | 1.0 | Choppy | adm_2026-08-31_extension_cap_50_slot_rank_rs | no | — | yes | pass | -0.40 | variance: clean fill, peak +0.36R, stopped day 0 at -1.02R in Choppy; no defect in the fields |
| 396 | SEI | L1 | era_d | 2026-09-08 | 09:35 | 2.0 | +0.04% | +7.94 / +1.38 | +1.72 | +0.41 | stop_hit | stop_hit@+0.41R 2026-09-22 | 11.0 | Choppy | adm_2026-08-31_extension_cap_50_slot_rank_rs | no | — | yes | pass | +3.50 | exit-discipline: kept +0.41R of +1.72R peak over 11 days; +3.50R high after exit |
| 399 | DFTX | L1 | era_d | 2026-09-14 | 09:33 | 7.0 | +0.34% | +7.66 / +1.67 | +0.00 | -1.01 | stop_hit | stop_hit@-1.01R 2026-09-14 | 1.0 | Correcting | adm_2026-08-31_extension_cap_50_slot_rank_rs | no | — | yes | pass | -0.99 | regime: clean fill (+0.34%), never traded above entry (peak +0.00R), stopped day 0 in Correcting; no mechanics defect |
| 400 | VICR | L1 | era_d | 2026-09-17 | 09:31 | 1.0 | -0.22% | +4.90 / +0.77 | +11.52 | +7.30 | stop_hit | stop_hit@+7.30R 2026-10-07 | 15.0 | Crisis | adm_2026-08-31_extension_cap_50_slot_rank_rs | no | — | yes | pass | +6.34 | variance: winner: +7.30R of +11.52R peak (63%); post-exit high +6.34R is below the exit, so exit was not early |
| 404 | KOD | L1 | era_d | 2026-09-28 | 09:31 | 5.0 | +0.40% | +8.03 / +1.46 | +8.06 | +5.87 | stop_hit | partial_profit@+4.34R 2026-09-28; stop_hit@+6.26R 2026-10-13 | 12.0 | Correcting | adm_2026-08-31_extension_cap_50_slot_rank_rs | no | — | yes | pass | +6.51 | variance: winner: +5.87R of +8.06R peak (73%); partial at +4.34R; post-exit high +6.51R |
| 409 | CEG | L1 | era_d | 2026-10-06 | 09:31 | 3.0 | +0.08% | +6.53 / +1.81 | +0.45 | -1.00 | stop_hit | stop_hit@-1.00R 2026-10-08 | 3.0 | Choppy | adm_2026-08-31_extension_cap_50_slot_rank_rs | no | — | yes | pass | +0.04 | variance: clean fill, peak +0.45R, stopped day 3 at -1.00R in Choppy; no defect in the fields |
| 414 | PENG | L1 | era_d | 2026-10-07 | 09:35 | 10.0 | +4.35% | +13.86 / +2.73 | +0.83 | -0.82 | stop_hit | stop_hit@-0.82R 2026-10-15 | 7.0 | Choppy | adm_2026-08-31_extension_cap_50_slot_rank_rs | no | his EP | yes | pass | -1.05 | entry-mechanics: his EP; filled +4.35% above trigger on a 13.86% / 2.73 ADR stop; peak +0.83R, ended -0.82R after 7 days |
| 419 | HUM | L1 | era_d | 2026-10-09 | 09:31 | 1.0 | +0.29% | +7.55 / +2.10 | +0.13 | -1.01 | stop_hit | stop_hit@-1.01R 2026-10-13 | 3.0 | Correcting | adm_2026-08-31_extension_cap_50_slot_rank_rs | no | — | yes | pass | -0.42 | regime: clean fill (+0.29%), peak +0.13R, stopped day 3 at -1.01R in Correcting; no mechanics defect |
| 422 | IRON | L1 | era_e | 2026-10-19 | 09:31 | 3.0 | -0.10% | +10.68 / +2.44 | +1.40 | +0.70 | sma_trail_stop (depth sale) | sma_trail_stop@+0.70R 2026-11-03 | 12.0 | Crisis | adm_2026-08-31_extension_cap_50_slot_rank_rs | no | — | yes | pass | +1.72 | exit-discipline: sma_trail_stop depth sale at +0.70R of +1.40R peak after 12 days (Crisis); +1.72R high after exit |
| 424 | SMCI | L1 | era_e | 2026-10-21 | 09:31 | 27.0 | +0.05% | +3.44 / +0.65 | +0.72 | -1.01 | stop_hit | stop_hit@-1.01R 2026-10-21 | 1.0 | Correcting | adm_2026-08-31_extension_cap_50_slot_rank_rs | no | — | yes | pass | -0.11 | variance: stop only 0.65 ADR, hit day 0 after a +0.72R peak; price never recovered (post-exit high -0.11R) |
| 429 | CLS | L1 | era_e | 2026-10-27 | 09:31 | 2.0 | -0.27% | +7.99 / +1.35 | +1.67 | -0.29 | stop_hit | stop_hit@-0.29R 2026-10-30 | 4.0 | Correcting | adm_2026-08-31_extension_cap_50_slot_rank_rs | no | — | yes | fail: exit_session_differs | -0.12 | exit-discipline: peak +1.67R then stopped at -0.29R on day 4, no partial; post-exit high -0.12R; replay fidelity failed |
| 440 | MTW | L3 | bp1 | 2026-11-02 | 09:46 | 752.0 | n/a% | +2.25 / +0.55 | +0.80 | +0.37 | other:operator close 2026-11-02: not a breakout in his read (choppy around the 10/20-day, no higher lows); breakout v1 paper paused for the gate fix | other:operator close 2026-11-02: not a breakout in his read (choppy around the 10/20-day, no higher lows); breakout v1 paper paused for the gate fix@+0.37R 2026-11-02 | 1.0 | Correcting | n/a | no | — | no | n/a | +2.46 | can't tell: operator close on 11-02 (gate-fix pause), +0.37R; not a stop or signal exit; no mechanics fields (fill vs trigger n/a) |
| 455 | AEHR | L1 | era_e | 2026-11-03 | 09:31 | 3.0 | +0.51% | +11.60 / +1.25 | +1.31 | -0.98 | stop_hit | stop_hit@-0.98R 2026-11-05 | 3.0 | Crisis | adm_2026-08-31_extension_cap_50_slot_rank_rs | no | — | yes | pass | +1.63 | exit-discipline: peak +1.31R then stopped at -0.98R over 3 days, no profit lock; +1.63R high after exit (Crisis) |
| 462 | APPN | L1 | era_e | 2026-11-05 | 09:31 | 17.0 | +0.50% | +7.21 / +1.18 | +0.02 | -0.93 | stop_hit | stop_hit@-0.93R 2026-11-05 | 1.0 | Choppy | adm_2026-08-31_extension_cap_50_slot_rank_rs | yes | — | yes | pass | +0.24 | variance: clean fill, peak +0.02R, stopped day 0 at -0.93R in Choppy; no defect in the fields |
| 593 | ABCL | L3 | bp1 | 2026-11-10 | 09:38 | 1412.0 | n/a% | +4.61 / +0.64 | +0.29 | -1.08 | stop_hit | stop_hit@-1.08R 2026-11-10 | 1.0 | Correcting | n/a | yes | — | no | n/a | n/a | regime: peak +0.29R, stopped day 0 at -1.08R in Correcting; stop fill within noise; excluded from L3 stats |
| 603 | OUST | L3 | bp1 | 2026-11-10 | 09:44 | 461.0 | n/a% | +5.94 / +0.79 | +0.41 | -1.00 | stop_hit | stop_hit@-1.00R 2026-11-10 | 1.0 | Correcting | n/a | yes | — | no | n/a | n/a | regime: peak +0.41R, stopped day 0 at -1.00R in Correcting; clean stop fill; excluded from L3 stats |
| 610 | AMLX | L3 | bp1 | 2026-11-10 | 10:11 | 583.0 | n/a% | +3.38 / +0.64 | +1.03 | -1.17 | stop_hit | stop_hit@-1.17R 2026-11-13 | 4.0 | Correcting | n/a | yes | — | no | n/a | n/a | exit-discipline: peak +1.03R then stopped day 4 at -1.17R (0.17R through the stop) in Correcting; excluded from L3 stats |
| 613 | ZYME | L3 | bp1 | 2026-11-10 | 10:16 | 565.0 | n/a% | +2.95 / +0.76 | +0.40 | -0.61 | stop_hit | stop_hit@-0.61R 2026-11-11 | 2.0 | Correcting | n/a | yes | — | no | n/a | n/a | exit-discipline: after-hours stop refusal sale at -0.61R (fixed 11-21, d6796470); mechanics defect, not a market outcome; excluded |
| 614 | CRWV | L1 | era_e | 2026-11-11 | 09:31 | 14.0 | +0.25% | +6.22 / +0.67 | +1.43 | -1.60 | stop_hit | stop_hit@-1.60R 2026-11-12 | 2.0 | Correcting | adm_2026-11-04_open_below_floor | yes | — | no | pass | n/a | exit-discipline: peak +1.43R on day 1, then stop filled -1.60R, 0.60R through the stop (gap); Correcting |
| 615 | RSKD | L1 | era_e | 2026-11-11 | 09:31 | 91.0 | +0.47% | +3.64 / +0.74 | +0.80 | -1.00 | stop_hit | stop_hit@-1.00R 2026-11-11 | 1.0 | Correcting | adm_2026-11-04_open_below_floor | yes | — | no | pass | n/a | regime: clean fill (+0.47%), peak +0.80R, stopped day 0 at -1.00R in Correcting; no mechanics defect |
| 773 | ANDG | L3 | bp1 | 2026-11-17 | 09:38 | 257.0 | n/a% | +3.33 / +0.80 | +0.00 | -1.00 | stop_hit | stop_hit@-1.00R 2026-11-17 | 1.0 | Crisis | n/a | yes | — | no | n/a | n/a | regime: peak +0.00R, stopped day 0 at -1.00R in Crisis; clean stop fill |
| 775 | ARDT | L3 | bp1 | 2026-11-17 | 09:39 | 947.0 | n/a% | +2.01 / +0.43 | +0.00 | -1.27 | stop_hit | stop_hit@-1.27R 2026-11-17 | 1.0 | Crisis | n/a | yes | — | no | n/a | n/a | exit-discipline: peak +0.00R, stop filled -1.27R, 0.27R through a 0.43 ADR stop, in Crisis |
| 788 | CAKE | L3 | bp1 | 2026-11-17 | 09:46 | 154.0 | n/a% | +1.99 / +0.45 | +4.00 | +0.65 | stop_hit | partial_profit@+2.03R 2026-11-18; stop_hit@-0.03R 2026-11-19 | 3.0 | Crisis | n/a | yes | — | no | n/a | n/a | exit-discipline: peak +4.00R; partial +2.03R, remainder stopped -0.03R; kept +0.65R (16%); stop 0.45 ADR |
| 791 | ACHC | L3 | bp1 | 2026-11-17 | 09:50 | 445.0 | n/a% | +1.98 / +0.38 | +0.23 | -1.06 | stop_hit | stop_hit@-1.06R 2026-11-17 | 1.0 | Crisis | n/a | yes | — | no | n/a | n/a | regime: peak +0.23R, stopped day 0 at -1.06R in Crisis; stop fill within noise |
| 826 | PPC | L3 | bp1 | 2026-11-17 | 10:50 | 588.0 | n/a% | +3.07 / +0.76 | +0.02 | -1.00 | stop_hit | stop_hit@-1.00R 2026-11-17 | 1.0 | Crisis | n/a | yes | — | no | n/a | n/a | regime: peak +0.02R, stopped day 0 at -1.00R in Crisis; fill 10:50; clean stop fill |
| 833 | GSHD | L3 | bp1 | 2026-11-17 | 14:43 | 260.0 | n/a% | +3.73 / +0.65 | +0.33 | -1.12 | stop_hit | stop_hit@-1.12R 2026-11-18 | 2.0 | Crisis | n/a | yes | — | no | n/a | n/a | regime: fill 14:43, peak +0.33R, stopped next session at -1.12R (0.12R through) in Crisis |
| 995 | LYFT | L3 | bp1 | 2026-11-18 | 09:36 | 913.0 | n/a% | +3.31 / +0.79 | +1.81 | -1.00 | stop_hit | stop_hit@-1.00R 2026-11-20 | 3.0 | Crisis | n/a | yes | — | no | n/a | n/a | exit-discipline: peak +1.81R (under the +2R third) then full -1.00R stop over 3 days in Crisis; no lock below +2R |
| 1003 | KNSA | L3 | bp1 | 2026-11-18 | 09:52 | 179.0 | n/a% | +2.30 / +0.44 | +0.02 | -1.12 | stop_hit | stop_hit@-1.12R 2026-11-18 | 1.0 | Crisis | n/a | yes | — | no | n/a | n/a | regime: peak +0.02R, stopped day 0 at -1.12R in Crisis; stop fill within noise (0.12R) |
| 994 | BRKR | L3 | bp1 | 2026-11-18 | 10:02 | 148.0 | n/a% | +4.88 / +0.88 | +0.54 | -1.44 | stop_hit | stop_hit@-1.44R 2026-11-20 | 3.0 | Crisis | n/a | yes | — | no | n/a | n/a | exit-discipline: peak +0.54R, stop filled -1.44R, 0.44R through the stop (3 days, Crisis) |
| 1019 | LTH | L3 | bp1 | 2026-11-18 | 14:37 | 324.0 | n/a% | +3.25 / +0.82 | +0.24 | -1.03 | stop_hit | stop_hit@-1.03R 2026-11-19 | 2.0 | Crisis | n/a | yes | — | no | n/a | n/a | regime: fill 14:37, peak +0.24R, stopped next session at -1.03R in Crisis; clean stop fill |
| 1235 | RZLT | L3 | bp1 | 2026-11-19 | 15:43 | 1203.0 | n/a% | +8.35 / +0.99 | +0.11 | -1.00 | stop_hit | stop_hit@-1.00R 2026-11-20 | 2.0 | Crisis | n/a | yes | — | no | n/a | n/a | entry-quality: stop 8.35% (L3 median 3.3%) on a 15:43 fill, 1203 shares; peak +0.11R, stopped next session at -1.00R; cannot separate from Crisis |
| 1443 | AAP | L3 | bp1 | 2026-11-20 | 10:25 | 220.0 | n/a% | +4.16 / +0.96 | +0.19 | -1.03 | stop_hit | stop_hit@-1.03R 2026-11-20 | 1.0 | Crisis | n/a | yes | — | no | n/a | n/a | regime: peak +0.19R, stopped day 0 at -1.03R in Crisis; fill 10:25; clean stop fill |
