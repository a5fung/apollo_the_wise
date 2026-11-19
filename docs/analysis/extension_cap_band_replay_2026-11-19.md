# Extension-cap band replay — review `extension_cap_75_recheck`, 2026-11-19

REPORT ONLY (THE LINE: the cap is the operator's). Driver `scripts/probes/_extcap_replay_1119/run.py`, output `results.txt`, data `pull.out.gz` (read once, offline). Live rule-set `as_of_2026-11-19`, harness `scripts/ep_replay.py` (walk_campaign / _walk_leg, live stop, partial, trail), settle horizon 2026-11-18.

## Population
- Extended-rejected ticker-days since 08-23 with prior-5-day rise >= 50%: 80 (the pull's 82 includes header lines).
- 50-75% band: n = 16 ticker-days (15 distinct names; AEHL twice) — the review's subject.
- >=75% group: n = 64 ticker-days (40 distinct names).
- Entry modelled: live MAGNA53 path, ORB from the 09:30 bar, 09:31 submit, live real-time gap-floor re-check (gap >= 9% at submit), ORB validation, #500 limit-fallback and chase cap. No stored ep_score exists on any of the 1,918 scan rows (the cap rejects before scoring), so I could not find the first would-be-HIGH tick: every campaign submits at 09:31 = an UPPER BOUND on admission (names that would never have scored HIGH are included). The #715 open-floor check is not modelled (needs flip-up events not in the pull).
- Abstains (harness cannot decide the path): band 0 of 16; >=75% 4 of 64 (6%). Not entered for other reasons: band 12 (9 gap below 9% at submit, 2 never crossed ORB high, 1 ORB validation), >=75% 35.
- Sensitivity: with the gap floor OFF (every name admitted regardless): band 8 entered, 2 abstain (12%); >=75% 38 entered, 10 abstain (16%).

## Results
Live-path gates ON (headline):
- 50-75% band, n = 16: entered 4. >=3R: 0. Best: -1.00R. Full losers: 4 of 4. Total -4.00R, mean -1.00R.
  - PCLA 09-11 -1.00, BIAF 09-18 -1.00, APUS 10-12 -1.00, SAIQ 10-23 -1.00; AEHL 09-03 and USDE 09-21 never crossed the ORB high; GTBP, MKDW, AVX, GIBO, ATGL, RPGL, TANH, FLY, AEHL 11-13 failed the gap floor at submit; MF 11-10 failed ORB validation.
- >=75%, n = 64 (context only): entered 25. >=3R: 1 (SVRN 09-21 +3.65R, week 39 only). Best +3.65R. Full losers 15 of 25. Total -11.96R, mean -0.48R, median -1.00R. Without the one winner: -15.6R. Others near 0: nine breakevens (+0.00R), GRML 09-24 +1.33R, losers incl. VEEA -1.65R, MBRX -2.29R.

Gap floor OFF (upper bound, same 09:31 submit):
- 50-75% band, n = 16: entered 8. >=3R: 0. Best +0.00R (AVX breakeven). Full losers 6 of 8. Total -6.30R, mean -0.79R. Per name: PCLA -1.00, GTBP -0.30, MKDW -1.00, BIAF -1.00, AVX 0.00, APUS -1.00, SAIQ -1.00, FLY -1.00; AEHL x2, USDE, RPGL no entry; GIBO, MF, AEHL 11-13 no trade; ATGL, TANH abstain.
- >=75%, n = 64: entered 38. >=3R: 1 (same SVRN +3.65R). Total -14.92R, mean -0.39R; WFF +1.33R-class winners (WFF +1.30, OMH +1.33, SVRN +1.33, GRML +1.33) are the rest of the upside.

Per-name lines for every ticker-day are in `results.txt`.

## Meaning
- The band has no tail at all: zero campaigns at +3R, best is breakeven or a loss under either arm, and the total is negative under both arms.
- Most band names would not even trade: 9 of 16 fail the live 9% gap floor at 09:31, so the extension cap is not the gate that excludes them.
- The 09-21 answer stands (the stop binds, not the cap); admitting the band would have added losses.
- Context: the >=75% group has one +3R campaign out of 25 entered and is also net negative.

## Which reading fired
- Pre-declared REOPEN-WORTHY bar: band total R > 0 AND >= 2 campaigns at +3R across >= 2 weeks. Band total R = -4.00R (live path) / -6.30R (upper bound); +3R campaigns = 0; weeks = 0.
- NOT FIRED under either arm. The 09-21 answer stands. No fork for the operator.

## What this does not answer
- Whether the names would have scored HIGH (no stored score on extended-rejected ticks; 09:31 upper-bound submit), so true admitted count is lower than modelled.
- The #715 open-floor check and flip-up events are not modelled.
- Small samples (band 16 ticker-days, 4 entered under live gates); a null here is not a verdict on a different cap level or a different stop for extended names.
- Pre-market-spike names that fade before the open are included as-is from minute bars; no order-book or slippage beyond the harness fill model.
- Whether names rejected below 50% or in other filters carry edge.
