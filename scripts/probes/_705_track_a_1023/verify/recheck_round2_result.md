FIX: 3 new problems block the freeze (P1 the control depends on labels said later, P2 §6 leaves the trade unit and first-break mix open, P3 the fit's bar is about 2× off). Of the checkers' 20 fixes, 17 landed, L5 and L10 are partial and D11 is cosmetic. Every count I recomputed matches the doc.

**1. Checker fixes** (doc = `docs/analysis/cb_track_a_filter_prereg_2026-10-23.md`)

| fix | status | doc lines |
|---|---|---|
| L1 positives = on-or-before E, 236 (170 / 66) | landed | :35-40, :63-66, :205-208, :237-242, :301-305, :355-361, :468-470 |
| L2 R2 out of the fit and §6 | landed | :175-176, :241-242, :265, :332-333, :360 |
| L3 rows on labelled bases excluded and counted | landed as written; opens P1 | :210-218, :259-263, :301-304, :356 |
| L4 no not-yet arm in §6 | landed | :243-244, :357 |
| L5 readiness contrast scored at the label date | partly | :334-342 and :245-248 fixed; :326 still calls the not-yet events' recall "the readiness contrast"; stated n 50 / 32 should be 43 / 25 |
| L6 entry / stop / re-entry, sloping line | landed | :362-374; formula checked against the module (:367) and the runner (:4181-4186) |
| L7 G8 / costs / G10 / point-in-time / DISCONTINUOUS | landed | :293-298, :383-405 |
| L8 timing rewrite, limits, beside AUCs | landed | :24-34, :66-70, :130-137, :327-332, :471-478 |
| L9 plateau holes, per-100 denominator, abstain, resampling | landed | :310-311, :321-323, :363-364, :378-382 |
| L10 numbers / wording / commit | partly | wording landed; the commit is not done (:507-509) and is a freeze precondition |
| R1-R9 | landed | :95, :180-181, :148-160, :127 + :454-458, :122-123, :112-113, :196-197, :443-444, :188-190 + :492-497 |
| D11 one-decimal medians | partly, cosmetic | script §8 still prints the not-yet median 0.5 as "+0" |

**2. Recount** (outcome-free columns only; era B cut at read to rows ≤ 2024-12-31)

| quantity | doc | mine |
|---|---|---|
| positive events with a label on or before E (fit / hold-out) | 236 (170 / 66) | 236 (170 / 66) |
| positive events labelled only after E / strictly before E | 87 (58 / 29) / 127 (90 / 37) | same |
| same-day rows excluded as labelled bases (fit / hold-out) | 654 (418 / 236), 33 not-yet, 45 after-E-only | same |
| negatives that remain | 22,944 (14,959 / 7,985) | same |
| era B: positives / excluded / negatives | 9 / 9 / 343 | same |
| pinned hashes (script, both outputs, labels, moments) | as printed | match on disk |

**3. Attack on the revised doc (the same 9 checks)**

| # | check | result |
|---|---|---|
| 1 | anything outcome-conditioned | FAIL (P1) |
| 2 | any read of 2025+ | PASS |
| 3 | same-day ungraded control | FAIL (P1, P2) |
| 4 | target vs label timing | PASS |
| 5 | roles of best / not-yet | PASS (minor: L5 residue) |
| 6 | free choices, plateau, split, pins | FIX (P3) |
| 7 | sanity read complete | FIX (P2) |
| 8 | limits stated honestly | PASS, except P3 |
| 9 | `check_analysis_doc.py` | PASS (exit 0) |

**4. Exact fixes**

| # | problem | fix |
|---|---|---|
| P1 | 244 of the 654 excluded rows (148 fit / 96 hold-out, 98 bases) are dropped only because of labels said after that row's breakout day. On 72 of those bases the later label is bought or best, so the control loses stocks he showed later, plausibly because they worked. That is hindsight in the deciding comparison. | Exclude a row only if its base was labelled on or before its own day (410 rows). The control becomes 23,188 rows (fit 15,107 / hold-out 8,081; era B 345); show the current rule beside. Update script §12 and doc :39, :216-218, :261-262, :302-304, :356. |
| P2 | §6 never says whether several rows of one base are traded separately (Track B trades once per base). The arms also differ by construction: labelled events are 1.26 per base and 44% retriggers, the control is 2.72 per base and 76% retriggers. | State "every event is walked independently; overlapping walks allowed". Make the deciding difference split by first break vs retrigger, with the control reweighted to the labelled arm's mix; an abstained event stays in its group. Show the raw difference and a one-row-per-base reading beside. |
| P3 | As written, the fit's bar passes on 3 of 66 hold-out events, fails at ≤ 1, and the 25% plateau tolerance is a single event. The doc's "≈ 3% / ≈ 9% / about 6 events" uses the 2017-21 weekly median; 2021 runs 372 a week, so the true rate is ≤ 1.32%. | Replace the stated numbers with these and state the bar and plateau in events. |

Non-blocking items for the freeze commit:
- Correct the readiness-contrast counts and rename :326.
- Add a column whitelist and the shuffle test to the fit module.
- Commit the round-2 doc and script, and pin `01_join_labels.txt`.

Full report: `/Users/alvinfung/apollo_the_wise/scripts/probes/_705_track_a_1023/verify/recheck_round2.md`