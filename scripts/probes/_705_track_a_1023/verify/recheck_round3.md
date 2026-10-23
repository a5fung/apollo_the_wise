# #705 Track A registration, round 3 recheck (2026-10-23)

**Verdict: FIX. Two blockers (B1, B2), each a one-line edit, plus three fixes the fit module needs before it can be written (I1 to I3).** P1 to P3 and the small items all landed. Every count I recomputed matches the doc and the pins on disk.

Inputs read (outcome-free only):
- `labels_joined.tsv`: sym, s0, screen_date, era, coverage, grade, is_*, watch_at_s0, c0_tl_at_s0, delta_tl, E_tl, base_id_tl.
- `matched_events.tsv`: era, sym, E_tl, bought, not_yet, best, base_id, retrigger.
- Candidates: ticker, D, E, K, base_id, retrigger, retrigger_chain, split. Era B was cut at read to discovery rows with D and E ≤ 2024-12-31, then asserted.
- Never opened: any E-day bar column, r1/r2/bdef, any outcome.
- Scratch: `/private/tmp/claude-501/-Users-alvinfung-apollo-the-wise/d30e3944-e07e-4b44-97de-010acba78d0b/scratchpad/rc5/r3.py`, `r3b.py`, `r3c.py`, `r3.out`.

## 1. Did each fix land? (doc = `docs/analysis/cb_track_a_filter_prereg_2026-10-23.md`)

| fix | status | doc lines |
|---|---|---|
| P1: a label counts only when said on or before the row's E | **landed**; the prose elsewhere still contradicts it (B1) | :39-41, :211-221, :263-270, :308-311, :372-374; script §12 (rule + the round-2 rule printed beside) |
| P2: the unit; the mix-reweighted deciding difference; raw and one-per-base beside | **landed**; the bootstrap weights are unstated (I3) | :379-385, :430-432 |
| P3: the bar in events from 1.32% | **landed**; the new plateau rule is not "round 2 in events" (B2) | :352-359 (bar), :326-331 (plateau) |
| small: readiness 43 / 25, the 15 events | landed; 2 of the 15 are not positive (N3) | :223-226, :249-252, :343-349 |
| small: rename of the not-yet TAKE share | landed | :333-335 |
| small: column whitelist + shuffle test | **partly**: registered, but neither can run as written (I1, I2) | :361-365 |
| small: pin the printout; commit | landed (`3b90134e…` matches disk; round 3 is in `84a19c0c`) | :531, :551-552 |
| D11 residue (`:+.0f`) | not done, cosmetic | script :626 |

## 2. Recount (doc against mine; all match except one descriptive count, 72 → 75, a nit)

| quantity | doc | mine |
|---|---|---|
| era A on-or-before: other rows · excluded (fit / hold-out) | 23,598 · **410 (270 / 140)** | same |
| of the excluded: not-yet events · post-E-only | 29 · 18 | same |
| **negatives, round 3 (fit / hold-out)** | **23,188 (15,107 / 8,081)** | same |
| round-2 rule beside · rows dropped only for a later label | 654 → 22,944 · 244 (148 / 96) on 98 bases | same |
| era A all 323: excluded · negatives | 449 (296 / 153) · 28,788 (18,842 / 9,946) | same |
| era B on-or-before / all: excluded · negatives | 7 · **345** / 6 · 465 | same |
| later-label bases with a bought or best label | 72 | **75** (72 bought or best only, plus 3 that also carry not-yet), nit |
| 2021 tl rows · weeks · median a week · Σ min(6, week) | 23,632 · 52 · 372 · 312 | same |
| no-information rate · expected of 66 | **1.32% · 0.87** | 1.320% · 0.871 |
| chance P(≥ 5) · P(≤ 1) · P(≥ 3) | 0.2% · 78% · 5.8% | 0.20% · 78.3% · 5.8% |
| the 15 events with a positive and a not-yet label | 15, 12 with bought | 15 (12 bought; AHT, ROKU, TLRY best only) |
| not-yet labels at s0 after the exclusion · the {0, +1} set | **43** (of 50) · **25** (of 32) | same (removing only the 12 bought events also gives 43) |
| GRADED mix | 1.26 per base, 44% retriggers | 236 on 188 bases (1.255), 104 retriggers (44.1%) |
| UNGRADED mix (round 3) | "about 2.72, 76% (round-2 counts)" | 23,188 on 8,540 bases (2.715), 76.0%: still holds |
| pins: labels_joined, matched_events, cand_A, script, printout | as printed | sha256 equal |

Two notes from the recount, neither a defect:
- **The stated chance figure is conservative.** The 2021 positives sit in weeks with a median 810 rows, so a random 6 a week flags 0.66 of them, not 0.87 (P(≥ 5) = 0.06%). The other way: the 66 sit on 59 bases (5 with two events, 1 with three), so one flagged base can give 2–3 events and Poisson slightly understates chance. Half a sentence at :356 would cover both.
- **101 UNGRADED rows sit on a base that also has a GRADED event**: crossings he labelled only later. Keeping them is correct point-in-time. It ties the two arms together but cannot favour GRADED.

## 3. Did round 3 open new hindsight or contradictions?

| check | result |
|---|---|
| exclusion rule vs the §5.2 AUC denominator | **consistent.** A day's rows share one E, so "labelled on or before E" is one set per day. Other positives stay out of the denominator. A label used to exclude a row can only be matched through events dated on or before that row's E (the nearest-event rule never reaches past it), so the matching cannot look ahead. |
| the exclusion vs the prose of §3 / §4 | **FAIL, B1** |
| mix reweighting vs the bootstrap | consistent: one month draw for both arms, weighted difference inside each resample, abstained events kept in their group. The weights are unstated (I3). |
| PASS raised from about 3 to 5 events | **legitimate.** No fit module exists and no hold-out recall has been computed. The reason is stated and correct (chance passes the old bar 5.8% of the time, the new one 0.2%). |
| the plateau stated in events | **FAIL, B2** |
| the shuffle test and the whitelist can be built | **no, I1 and I2** |
| a round-2 number still quoted as current | none of 654 / 22,944 / 14,959 / 7,985 / 343 / 50 / 32 / ≈ 3% / ≈ 9%: each appears only as "beside" or history. Residue: "the 25%" (:367), the titles and headers (N1) |
| any 2025+ read | none (asserts in my reads; the doc's cuts unchanged) |

## 4. Blockers (each changes what the module computes, or lets hindsight in)

**B1: §3 and §4 still say the post-E-only and not-yet events are in neither class. Under the round-3 rule, 31 of them are negatives.**
- Fact: in era A, **27 post-E-only events (19 fit / 8 hold-out) and 4 not-yet events (LYFT 2021-03-03, NNDM 2020-12-21, PLUG 2020-07-21, TPIC 2020-10-07) are among the 23,188 negatives and in UNGRADED.** In era B, 1 post-E-only event is among the 345.
- Their base carried no label on or before E, so keeping them is the correct point-in-time choice, and it is what the round-2 recheck asked for.
- But :243-245 says a post-E-only event "is NEITHER positive NOR negative: it leaves both classes". And :269-270 says a not-yet event "is neither a negative … nor a positive".
- Why it blocks: a module built from those sentences drops the 31 rows because of a label said later. That is exactly the P1 hindsight, on the most loaded rows (stocks he later said he bought). §6 says "the exact n re-printed by the module", so the 23,188 is not an assert that would catch it.
- Fix :244: "…leaves the POSITIVE class; on a graded date its row stays among the same-day negatives and in UNGRADED unless its base carried an earlier label (§4; 27 in era A, 19 fit / 8 hold-out; 1 in era B)."
- Fix :269-270: "…a not-yet event whose not-yet call came on or before its E is neither… (29 excluded); one whose call came after E stays a negative (4: LYFT, NNDM, PLUG, TPIC)."
- Fix :219: add both counts as an "in the negatives" note. Fix :375-376: say that the 87 / 3 post-E-only beside row overlaps UNGRADED by 27 / 1.
- Fix §4 / §6: the module ASSERTS n = 23,188 (15,107 / 8,081) and era B 345 before fitting, instead of only re-printing it. The pin then becomes a gate, so a stale sentence cannot re-admit the 31 rows.
- Numerically tiny (31 of 23,188), so the fix is wording, but it is the one open path for hindsight.

**B2: the plateau rule (:326-329) is presented as round 2's rule restated in events. It is not: it is stricter above 7 flagged events.** Being stricter is a legitimate choice before any fit. The defect is the false claim that the two are the same rule.
- Round 3 requires every neighbour ≥ max(4, c − 1), where c is the registered subset's count. Round 2 required within 25%, i.e. ≥ ⌈0.75c⌉.
- They agree for c ≤ 7. They differ from c ≥ 8: c = 8 needs 7, not 6; c = 10 needs 9, not 8; c = 12 needs 11, not 9.
- Round 3 also drops the upper side (round 2's "within" was two-sided).
- The justification ("at these counts … a one-event tolerance anyway") and the revision row at :596 present it as a restatement.
- Why it blocks: a strong filter, the case that matters, flags 8 or more. Each leave-one-out neighbour then has to land within one event. A two-event wobble turns PASS into CAN'T TELL, and his R2 definition becomes primary (§7).
- Fix: either "every neighbour flags ≥ max(4, ⌈0.75 × c⌉) of the 66" (identical at c ≤ 7, round 2's tolerance above, one-sided stated), or keep c − 1 and say plainly that it is stricter than round 2 above 7 and why. Either option closes it; what cannot stand is calling them the same rule.
- Then update :367 ("the 25%" → "the plateau's event rule") and :596.

## 5. Fixes the fit module needs before it can be written (not blockers: no result change, no hindsight)

| # | problem | fix |
|---|---|---|
| I1 | The whitelist (:361-363) "asserts no other column is read", yet the fit must print the C1 share and the first-break / retrigger share (:336), by-phase and by-year splits (:336), and the `base_len` split (:298). Era B needs `split` for the discovery cut. None of these are whitelisted (`C1`, `base_len`, `phase_qqq_10_20`, `phase_qqq_10_20_s5`, `phase_spy_qqq_50`, `apollo_regime`, `split`, all D-night columns). The other inputs the fit reads are not named either (labels_joined / matched_events columns, `graded_moments.tsv` for the own-line subset, the DISCONTINUOUS flags). As written, the module fails its own assert or widens the list at run time. | Add those columns, stating that they feed only beside splits and the era cut, and name the other files and columns. |
| I2 | The shuffle test (:363-365) runs "before the real fit" but checks "the chosen-subset hold-out count", and no subset exists yet. Under permutation, almost no feature reaches 0.58, so the subset is nearly always empty. It is also unstated whether the 2021 flags are permuted. If only the fit set is permuted, a chance subset is scored on real 2021 positives. Label permutation also cannot detect a feature that reads bars after D: it catches only label leakage and AUC code bugs. Round 2's N2 asked for the §8 invariance test. | Split the test in two. (a) Before the fit, as written: the AUC band [0.48, 0.52] on labels permuted within each E date. (b) After the subset is chosen and before the real hold-out count is printed: score the REAL chosen subset with the 2021 positives permuted within each E date (expected about 0.66); stop if the mean exceeds 1.5. A per-permutation re-derived subset is almost always empty, which would make the check vacuous. Also add the §8 invariance test to the fit module: perturb every E-day-or-later column and every bar after D, and assert the scores are identical. |
| I3 | Bootstrap weights (:383-384): fixed GRADED shares or recomputed per resample? The stratifier column is also unnamed (`retrigger`, per §2f :189, not `retrigger_chain`; 928 of the control's "first breaks" are chain re-fires). | State: weights fixed at the full-sample GRADED shares (132 first breaks / 104 retriggers); stratify on `retrigger` 0 / 1. |

## 6. Wording nits (change no number)

| # | nit |
|---|---|
| N1 | :1 title and :3 status still say "round 2". :529 says "round 2 run" while :551-552 pin round 3. :531 "the commit after it" → `84a19c0c`. Script §12 still titles the on-or-before set "(round 2's GRADED)". |
| N2 | :357 "CAN'T TELL = 2–4" leaves "≥ 5 with 0 of 9 era-B events" unclassed. §7 sends it to R2 either way. Restore "CAN'T TELL otherwise". |
| N3 | :249-250 "15 … is POSITIVE": 2 of the 15 are post-E-only (MRNA 2020-04-15, ROKU 2020-08-04), so 13 are positive. Both leave the not-yet set either way. |
| N4 | :267 and :594 "72 of them later labelled bought or best" → 75 (72 bought or best only + 3 that also carry not-yet). |
| N5 | :381 "the round-2 recheck's counts" → "re-verified under round 3: 23,188 rows on 8,540 bases, 2.72 per base, 76.0% retriggers". |
| N6 | :356 the chance caveat in §2 (0.87 is an upper bound on chance; base clustering pulls the other way). |
| N7 | D11: script :626 `:+.0f` still prints the not-yet median 0.5 as +0. |
