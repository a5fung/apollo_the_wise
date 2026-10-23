# #701 verify, Fri 2026-10-23 (after the 17:35 ET coil scan). Read-only. Checker: Sonnet.

## VERDICT: EVENT-GATED. (a) MET, (c) MET, (b) not yet observable; nothing can close it early.
DoD judged against (verbatim): "DoD: (a) met on the 10-16 read; (b) each branch read on its first real firing or explicitly carried; (c) fixed or ruled out."
- (b) has 0 firings: `anticipation_mna_pin_held` ever = 0, `mna_release_merit_grade` ever = 0 (all-time count over mi_audit_log, query V).
- The PLAN line's "SYNA leaves the lookback ~10-23" is off by one scan: SYNA was re-nominated by news tonight (see b1). First exit scan = Mon 10-26 17:35 ET.

## (a) Alpaca/Benzinga source, week 10-19..10-23: MET (again; first met on 10-16)
- EXPECT "at least one news_source=alpaca row": 5 of 5 days have them. Fired: CCC (anticipation, nightly x5), BMBL (flag, x4), MAT (10-22). Released: NU, SAIQ, MAT x2, SIG x2. Unanswered: SAIQ, MAT. (Query C/D)
- EXPECT "every Alpaca block checked buyer vs target": all 3 blocked names are the TARGET, read from the detail JSON titles:
  - CCC "Agrees To Be Acquired By GTCR, Elliott" (10-15); BMBL "To Be Taken Private By Ithaca Holdings" (10-13); MAT "Takeover Talks" with Authentic Brands (10-01).
  - Buyers were released, not blocked: NU (buying Monzo, role=buyer) and SIG (joining a consortium to buy De Beers, role=buyer). 0 fired rows with role=buyer. (Query q2 detail)
- EXPECT "cap_hit and error-type unanswered at most ~2/week": `mna_headline_cap_hit` ever = 0; 2 unanswered this week, both `article_cap` (not error-type); 0 error/fail audit rows on the M&A path (query O).
- WOULD-FAIL-IF "a full week with zero alpaca rows while deal wires existed": not triggered (rows every day). "Alpaca block on a buyer": not triggered (above).
- Discrimination: the alpaca rows and the buyer-released rows are positive evidence (an unread feed or a bidder-blocking bug would not produce them). The cap_hit = 0 and error = 0 reads are absence-only; they would read the same on a system that never reaches the cap, so they only bound the failure, they do not prove health.
- Side read: `mna_headline_question` calls 16-18/day this week vs 10-12/day the week of 10-12 ($0.06/day). Not in EXPECT; noted only.

## (b) the two never-fired branches: NOT YET OBSERVABLE (event-gated)
- b1 `anticipation_mna_pin_held` (SYNA). Tonight's scan re-nominated SYNA by news: fired row 61181 (10-23 17:35), headline "Stock Market Midday, Oct. 2" published 2026-10-02T16:20Z, day range 0.4343%.
  - Why it could not hold: the lookback window starts at scan date minus 21 days (`collector.get_polygon_news`, published_utc.gte). On 10-23 that is 10-02, so the 10-02 headline was still in. The hold block (scheduler.py ~5100) runs only when news does NOT nominate (the `continue` after a fired row skips it).
  - Earliest exit scan: Mon 10-26 17:35 ET (window starts 10-05; the coil scan writes weekday rows only: 0 mna/anticipation rows on Sat-Sun 10-17/18, query W). That is inference from the code and the headline date; Monday's row is the proof.
  - SYNA is a live candidate: board row (anchor 10-02, mna_screened_on 10-08) rewritten tonight; closes 117.04-117.55 over the last 8 sessions. Outcomes Monday: `pin_held` if no other headline nominates, SYNA is still a coil candidate and range <= 2.0%; `pin_released` if range > 2.0%; another fired row if a newer headline nominates.
  - Fallback first-firing candidates: PTC and RXO (headlines 10-06; first exit Wed 10-28). CCC 11-05, BMBL 11-03.
  - Sibling branch proven live: `anticipation_mna_pin_released` fired 2x (RXO 10-20, MAT 10-23: "back on the coil board ... price moved", marks cleared), so the marked-name block executes in prod; only the held outcome is unseen.
- b2 `mna_release_merit_grade`: needs an EP-scan name graded 'mna' that is then released pin_free. This week's EP-side mna names (SLN 10-19, BRZE 10-20) were blocked, not released; GRRR was released but graded a non-pinning buyer, not 'mna'. No eligible event, so 0 rows is expected, not a defect. No date; it fires on the first such name.

## (c) QRVO stale-bar skip: MET (fixed and verified, 5 straight nights)
- Each night 10-19..10-23: exactly one `anticipation_stale_bars_skipped` row and each names "QRVO (last bar 2026-10-02)" (query M). `anticipation_mna_price_unread` for QRVO since 10-17: 0 (it was 10 of 10 nights before the fix, query N). mi_daily_closes max bar for QRVO still 10-02.
- WOULD-FAIL-IF "a name with a bar from the last 3 sessions is skipped": not triggered. The newest last-bar among skipped names is below the cutoff every night (10-23: cutoff 10-20; ATKR 10-16, ACVA 10-15). List grew 9 -> 11 (ACVA from 10-21, ATKR from 10-22); both confirmed barless in mi_daily_closes (query S).
- Discrimination: a non-working skip would keep writing QRVO price_unread (it did 10/10 nights); the 0 is paired with the positive skip row naming QRVO, so this check discriminates.
- Observation, not in the DoD: `anticipation_mna_check_capped` still fires 5 of 5 nights (cap of 40 still trips without QRVO).

## For the main loop (decisions, not actions taken)
- Do not close #701: (b) has no firing. "Explicitly carried" needs a home; this task already moved 10-16 -> 10-23 once, so a move to Mon 10-26 is a 2nd bump and needs the operator's sign-off or a `[blocked:event-gated SYNA exit 10-26]` tag. A deployed line past its verify-date hard-fails commits from Sat 10-24.
- Mon 10-26 17:35 ET read: audit rows for SYNA (`anticipation_mna_pin_held` / `_released` / `mna_filter_fired`) plus any `mna_release_merit_grade`.
- Not actioned (outside this read-only verify): the relayed alert that OPUS_PIN (shared/llm_models.py:129, "claude-opus-5") lags the served claude-opus-5-5. That constant is a model-selection commit (its comment says operator-confirmed and eval-gated), so it needs your call, not a checker's edit.

Evidence: ssh apollo@server, read-only psql via docker exec on apollo-postgres; queries v1023_701_q1..q4.sql (outputs kept in the session scratchpad, not the repo). Prior baseline: scripts/probes/_eve_1016/q701_2.out.
