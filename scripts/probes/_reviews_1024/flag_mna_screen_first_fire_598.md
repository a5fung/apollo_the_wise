# flag_mna_screen_first_fire_598 — read 2026-10-24 (Sat, PT), read-only

## Verdict
- The flag board's buyout screen fired for the first time since the 10-03 rebuild, on BMBL (Bumble), and the block is CORRECT. Action: none for the operator.

## Predicate now
- 4 (threshold 1) = 4 name-nights, 1 distinct name (BMBL): 10-20, 10-21, 10-22, 10-23, each at 17:25 ET. Ever: 40 (36 + 4, consistent with the old 36 up to 08-12).
- All-detector `mna_filter_fired` since 10-17 = 24; the other 20 are the 17:35 coil scan (anticipation) and 08:45 EP, not counted.

## What the action asked, checked per night (n = 4 audit rows, 4 flag rows)
- Deal TARGET, not the bidder: audit detail role=target, status=signed, cash, counterparty Ithaca Holdings; headline "Bumble Confirms To Be Taken Private By Ithaca Holdings For $6.05/Share In Cash" (Benzinga, 10-13).
- Price agrees (the screen's own second leg): BMBL closed 5.94-5.96 on 10-19..10-23 vs the $6.05 offer; own-day range 0.25-0.34% each night; `mna_pin_confirmed` written 4 of 4 nights.
- Flag row `unqualified`, reason `mna_filter:alpaca_headline_model` on 4 of 4 nights (10-20..10-23). Stage before the block was COILED (audit detail `stage`).
- Not in the digest: 10-21 digest new_today=[KOD], coiled=[]; 10-22 new_today=[CAI], coiled=[]. 10-20 and 10-23 have no `flag_digest_sent` row, so no digest to carry it; the `unqualified` flag row is also excluded from digest sections by construction.
- Why it first fired 10-20: 10-19 BMBL was WATCH (unscreened by design); it reached COILED 10-20. Unblocked, that WATCH to COILED move is a stage-up push (flag_detector.py:2236-2260); no digest row exists for 10-20, consistent with the block.

## What a BROKEN system would show
- Dead screen: count 0 and BMBL listed under COILED in the 10-21/10-22 digests. Observed: 4 rows and coiled=[] with BMBL held at original stage COILED, so the screen is alive.
- Misfire on a bidder/non-deal name: role would read bidder or the price would not be pinned. Observed: target, signed, price pinned under the offer.
- Residual: 4 hits on 1 name is n=1 name. This proves the path works and was right once; it is not a hit-rate.

## This also closes the gap #598's close recorded
- docs/task_closes.md #598 said a zero "cannot show a working screen from a dead one" and the flag-scan positive trace was unproven. 10-20 17:25 is that trace.

## Main-loop update (YAML, review flag_mna_screen_first_fire_598)
```
    status: done
    closed_on: 2026-10-24
    outcome: >-
      FIRED 2026-10-20 17:25 ET on BMBL (4 name-nights 10-20..10-23, 1 name), and the block is correct: deal
      TARGET (signed, $6.05 cash, Ithaca Holdings), price pinned 5.94-5.96 with own-day range 0.25-0.34%,
      flag row unqualified with mna_filter:alpaca_headline_model all 4 nights, absent from the 10-21 and 10-22
      digests (coiled=[]). First live positive trace of the 17:25 flag screen. No wrong block.
```
- PLAN.md: no line to change (#598 closed 10-16, no open task).
- Optional: one line under docs/task_closes.md #598 "What the zero cannot show": "Positive trace 2026-10-20 17:25 ET, BMBL (flag), see data_gated_reviews.yaml flag_mna_screen_first_fire_598."
- Operator decision: none.

## Ran (prod read-only; output in session scratchpad, remote files /tmp/rv1024_flag_mna_screen_first_fire_598_{1..5}.sql)
- Predicate widened to the date and with B/C/D counts; audit detail for the 4 rows; mi_flag_candidates BMBL 10-13..10-23; mi_daily_closes BMBL 10-08..10-23; flag_digest_sent rows 10-17..10-23; TIGHTENING counts per scan date (1,1,2,2,2 for 10-19..10-23, screened nightly).
- Predicate SQL as run:
  `SELECT count(*) FROM mi_audit_log WHERE event_type='mna_filter_fired' AND created_at >= DATE '2026-10-17' AND (summary LIKE '%(flag)%' OR detail LIKE '%''detector'': ''flag''%')` -> 4
