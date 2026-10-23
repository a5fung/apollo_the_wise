# #705 Track A registration, round 2 recheck (2026-10-23)

**Verdict: FIX, 3 exact fixes (P1 to P3 below).** All 21 checker fixes landed except 2 partial ones (L5, L10) and 1 cosmetic (D11). Every count I recomputed matches the doc. Three new problems remain. One lets hindsight into the control arm. One is a free choice in §6 that can move the deciding difference. One misstates the fit's bar by about 2×.

Inputs read (outcome-free only):
- `labels_joined.tsv`, columns sym, s0, era, coverage, grade, is_*, watch_at_s0, c0_tl_at_s0, delta_tl, E_tl, base_id_tl, retrigger_tl, D_tl, frame_id.
- `matched_events.tsv`, columns era, sym, E_tl, bought, not_yet, best, base_id, retrigger, week_all.
- The candidates files, `usecols` ticker, D, E, K, base_id, retrigger, split. Era B was cut at read to discovery rows with D and E ≤ 2024-12-31, then asserted.
- Never opened: r1_status, r2, r1_off_from_E, delta_r1, any `bdef_*` file, any E-day bar column.

Scratch scripts: `/private/tmp/claude-501/-Users-alvinfung-apollo-the-wise/d30e3944-e07e-4b44-97de-010acba78d0b/scratchpad/rc2.py`, `rc3.py`, `rc4.py`.

## 1. Each checker fix: landed or not

| fix | status | doc lines (`cb_track_a_filter_prereg_2026-10-23.md`) |
|---|---|---|
| L1 on-or-before positives 236 (170 / 66) | landed | :35-40, :63-66, :205-208, :237-242, :301-305, :355-361, :468-470 |
| L2 R2 out of fit and §6 | landed | :175-176, :241-242, :265, :332-333; R2 survives only as a descriptive share at :360 |
| L3 labelled-base rows excluded and counted | landed as written; **see P1** | :210-218, :259-263, :301-304, :356 |
| L4 no not-yet row in §6 | landed | :243-244, :357 (no other not-yet in §6-§8) |
| L5 readiness contrast at s0 | **partly** | :334-342 at s0, with 32 / 138 beside; "same bases" fixed at :340-342; the 12-event reason fixed at :245-248. Residue: N1 |
| L6 entry / stop / re-entry | landed | :362-374; the level formula matches `_down_trendline` (module :367) and `h60_anchor_high` (runner :4181-4186) |
| L7 G8 / costs / G10 / point-in-time / DISCONTINUOUS | landed | :293-298, :383-405 |
| L8 timing rewrite + limits + beside AUCs | landed | :24-34, :66-70, :130-137, :233-236, :327-332, :471-478 |
| L9 empty subset, 1-feature plateau, per-100 denominator, abstain = 0 R, same-month resampling | landed | :310-311, :321-323, :363-364, :378-382 |
| L10 numbers / wording / commit | **partly** | wording landed (:5-8, :45-46, :215, :273-289, :443-444, :484-485); commit not done (:507-509), which is a freeze precondition, not a doc fix |
| R1 54 symbols | landed | :95, :490 |
| R2 "199 chains" deleted | landed | :180-181; script item removed |
| R3 the "not yet broken" key, plus the base_id key | landed | :148-160 |
| R4 placebo's three conditions | landed | :127, :454-458; script header |
| R5 distinct-event delta rule | landed | :122-123, :135-137 |
| R6 "horizontal levels mixed" | landed | :112-113 |
| R7 SQM / ROKU controls | landed | :196-197 |
| R8 94.0%; before-share below placebo | landed | :26-28, :130-131, :443-444 |
| R9 drift re-fire note; stale header | landed | :188-190, :492-497; script :30-33 |
| D11 one-decimal medians | **partly, cosmetic** | `split()` fixed; the txt §8 per-K line still prints the not-yet median 0.5 as "+0" |

## 2. Recount (mine against the doc; every one matches)

| quantity | doc | mine |
|---|---|---|
| era A positive events (fit / 2021) | 323 (228 / 95) | 323 (228 / 95) |
| ≥ 1 positive label on or before E | **236 (170 / 66)** | **236 (170 / 66)** |
| every positive label after E | 87 (58 / 29) | 87 (58 / 29) |
| strictly before E | 127 (90 / 37) | 127 (90 / 37) |
| a positive label at delta 0 | 119 | 119 |
| era B positive / on-or-before / post / strict / at 0 | 12 / 9 / 3 / 6 / 3 | same |
| bought-only, era A / on-or-before | 297 / 216 | same |
| all 323: dates · other tl rows (fit / 2021) | 193 · 29,237 (19,138 / 10,099) | same |
| all 323: excluded (fit / 2021) · of them not-yet | 704 (450 / 254) · 36 | same |
| on-or-before 236: dates · other rows | 156 · 23,598 (15,377 / 8,221) | same |
| on-or-before: **excluded** · not-yet · post-E-only | **654 (418 / 236)** · 33 · 45 | same |
| on-or-before: **negatives** | **22,944 (14,959 / 7,985)** | same |
| era B all / on-or-before: rows · excluded · negatives | 471 · 7 · 464 / 352 · 9 · 343 | same |
| pins: script, both outputs, labels, moments, cand_A, watch_A | as printed | sha256 on disk equal |

## 3. Trying to break the revised doc (the 9 checks)

| # | check | result | evidence |
|---|---|---|---|
| 1 | outcome-conditioned? | **FAIL (new, P1)** | Exclusions from the control use labels said AFTER the row's E. 244 of the 654 excluded rows (148 fit / 96 hold-out, on 98 bases, 27 of them post-E-only positive events) are on bases whose every label came after that row's E. On 72 of those bases he bought or graded it best later. Era B: 2 of 9. |
| 2 | any 2025+ read? | PASS | Era-B walker cut plus two asserts (:388-390); candidates / watch / bdef cut at read (script); `pit_lint.py` refuses dates > 2024-12-31 (:28). |
| 3 | control = same-day ungraded, same rules? | **FAIL (P1, P2)** | Counts reproduce. Note: 105 negatives (73 fit) are rows of a stock with any label within ±20 sessions, on another or unmatched base (9 within ±10). That is 0.46%, not result-changing. |
| 4 | target vs label timing | PASS | :24-34, :233-242. The third branch alone; post-E out of positives; the delta-0 caveat at :65-66 and :469-470. |
| 5 | best / not-yet roles | PASS, minor N1 | best merged (:244); no not-yet arm (:357). |
| 6 | free choices, plateau, split, pins | **FIX (P3)** | Plateau holes closed (:310-311, :321-323); split 170 / 66 / 9; pins match. The bar's stated numbers are wrong. |
| 7 | sanity read complete? | **FIX (P2)** | Entry / stop / re-entry / costs / G8 / G10 / point-in-time / abstain all stated. Not stated: the unit when several rows hit one base, and the arms' first-break / retrigger mix. |
| 8 | limits honest? | PASS except P3 | After-the-fact selection, timing noise, phrase attribution, 94.0%, "upper bound" all stated (:63-70, :466-500). |
| 9 | `check_analysis_doc.py` | PASS | Exit 0 on the explicit path. |

## 4. Exact fixes (blocking)

**P1: the control is conditioned on his later labels (hindsight in the deciding arm).**
- Problem: §4 / §6 drop a same-day row if its base carries a label "of any grade", whenever said. 244 rows (148 / 96) are dropped only because of labels said after their E. Those are stocks he went on to show, plausibly because they worked. Removing them pushes the control down, and the doc itself expects post-E events to read better (:358-359). Round 1 removed this after-the-fact selection from GRADED; round 2 moves it into UNGRADED.
- Fix: make the exclusion point-in-time. Exclude a row only if a label of its base was said on or before that row's E (410 rows: 270 fit / 140 hold-out; era B 7).
- Fix: keep the 244 in UNGRADED and in the fit's negatives. That gives **23,188 rows (fit 15,107 / hold-out 8,081); era B 345**.
- Fix: report the current all-time exclusion beside. Add both counts to script §12 and to doc :39, :216-218, :261-262, :302-304 and :356.

**P2: in §6, the unit and the arms' mix are left to the module.**
- Problem: GRADED is 236 events on 188 bases (1.26 per base, 104 retriggers = 44%). UNGRADED is 22,944 rows on 8,442 bases (2.72 per base, 17,445 retriggers = 76%). The skew is built in: a labelled base gives only its nearest event, while an unlabelled base gives every row on the 156 dates.
- Problem: §6 borrows "Track B's §D mechanics", but Track B trades once per base (`h60_select`, per-base chain R). §6 never says whether overlapping rows of one base are walked independently.
- Fix: state "every event is walked independently; overlapping walks of one base are allowed".
- Fix: register the deciding `pp` / T0 difference stratified by first break vs retrigger, with UNGRADED reweighted to GRADED's 44 / 56 mix. Rec: that stratified difference decides. Report the raw per-event difference and a one-row-per-base reading (each base's earliest row on a graded date, both arms) beside.
- Fix: an abstained event keeps its stratum (0 R, in that stratum's per-100-events denominator), so the reweighting and the denominator agree.

**P3: the fit's bar (:343-347) is about 2× off what its own rule gives.**
- Problem: the rule as written passes on **3 of 66 events** (PASS ≥ about 4.0%), fails at **≤ 1** (FAIL ≤ about 2.0%), and reads CAN'T TELL at 2. The 25% plateau tolerance at 3-4 flagged events is a single event.
- Why: 2021 has 23,632 tl rows in 52 weeks (median 372 a week), so at most 6 TAKE a week is ≤ 1.32% of the stream. The doc's "about 6 of 205 a week ≈ 3%" uses the 2017-21 weekly median.
- For scale: the 2021 positives sit in weeks with a median 810 tl rows, so a random flag catches about 1.0% of them (0.66 events). The 2017-20 rate is 2.1%.
- Fix: replace "≈ 3% / ≈ 9% / about 6 events / about 3" with these numbers, and say that PASS can rest on 3 events and the plateau on 1. Rec: state the bar and the plateau in events, so that thinness is visible.

## 5. Notes (non-blocking; do them in the freeze commit)

| # | note |
|---|---|
| N1 | Readiness contrast n: of the 50 not-yet labels at s0, 2 are mixed-grade (TLRY `g_0356` best,not_yet; OPK `g_0234` bought,not_yet, which also sits in the bought 176). 5 more sit on a both-label event. The not-yet side after §3's exclusion is **43** (beside set: **25** of 32). The exclusion should name the **15** events carrying not-yet and bought-or-best, not 12. :326 calls the not-yet EVENTS' recall at D "the readiness contrast"; rename it, since the contrast is defined at s0 (:334). |
| N2 | The fit module has no column whitelist. The candidates file carries E-day columns (open_E..close_E, vol_E, breakout_vol_x, gap_open_pct, gap_over_1adr, overlap_open). Register for `02_fit_filter.py` the same shuffle-invariance test as §8 (:432-433), plus an explicit `usecols`. |
| N3 | Commit the round-2 doc and script before the freeze. The script hash `7fc6452c…` and "fixed before the first run" mean nothing until committed. Pin `01_join_labels.txt` (`5cae11f4…`) too. |
| N4 | D11 residue: the script §8 per-K print still uses `:+.0f`. |
| N5 | `trigger_bar_range_adr` is D's bar (`explain_watch`, module :730-733), so the doc's definition at :289 is right. No positive event sits on E 2022-01-03, so "2021 hold-out" is exact. |
