# #545 Phase 2 — the missed-EP tail read: what the skip buckets ran, and what our bracket would have paid (2026-09-02)

**THE ANSWER: one bucket clears the pre-registered bar — `stop_too_wide`, the operator's own — and it
clears it on two April/May rejects that predate the minute-bar capture (BAND 04-30 +110%, STRL 05-05 +32%
at 20 sessions: 2 of 10 mature = 20% vs the traded cohort's 13.3%); on the four fills the current bracket
CAN replay it paid **+0.5R** on the live partial path (HTFL **+1.43R**, three small losers) — a winner the
gate cost us, not a ≥4R tail.** No other bucket is a candidate on evidence that survives the two
population traps below: five scan-level buckets sit above the bar on pooled numbers that a second
read-only capture (§10) must first clean — the top of their tail lists is leveraged single-stock ETFs
from the week before the security-type filter existed (04-13→04-19) — so they are provisional, daily
grain only, and can only fall. And across everything we DID admit, the bracket turned 14 daily-grain
runners into one ≥4R (AMBQ) and one more ≥2R (ABVX); 3 could not be entered by rule (detected after
09:45), 3 are unreadable. **The tail is being lost in conversion, not at the gates.**

**⚖ THE LINE — MEASUREMENT ONLY. Nothing was flipped: no admission gate, score bar, stop, target,
sizing or safeguard. Every live change is CHANGE_PROCESS + the #151 harness + operator sign-off.**
Runs inside #545 (Phase 2, pre-registered in `docs/design/545_entry_exit_program_v2_2026-09-02.md` §7).

---

## 1. The decision this serves, and what would change it

**Decision:** which skipped-name populations, if any, deserve a P14 both-directions read as candidates
for admission into the tactics grid — i.e. whether P1 (*"it should not miss a real EP which is the true
test"*) is currently being violated by a skip filter in a way that matters to THE GOAL (≈1 converted
≥4R winner a month).

**Pre-registered pass bar (§7 Phase 2, fixed before the data):** a bucket whose tail share
(≥+20% at 20 sessions from the gap-day open, gapped-at-the-open rows only) is ≥ the traded cohort's is
a candidate; below it, closed. **What would change the decision:** a bucket above the bar whose tail
ALSO survives the live bracket (alert-level buckets, where the bracket can be replayed) — that would be a
P1 finding demanding a downstream-selectivity plan (P9). A bucket above the bar whose tail vanishes
under the bracket is answered: the tactic, not the gate, is the loss.

**What would make this document wrong:** (a) the daily-grain proxy read as realised R — it is not,
and §4 measures the gap; (b) a pooled share quoted over a population today's scan does not produce —
§2 names the contamination and §10 removes it; (c) `ret_20d` read as current — 382 of 423 August rows
are censored; (d) an alert-level bracket number quoted without its status distribution (a no-entry is
an answer, not missing data); (e) R units conflated across eras — §3 states the unit.

## 2. Method / population — read before any number

**Population:** `mi_ep_missed_outcomes` rows with `setup_at_open = true` (gapped ≥9% at the open over
the strictly-prior close, the #595 rule, imported from `ep_detector.MIN_GAP_PCT`), alert dates
2026-04-13 → 09-01, captured ONCE read-only on 2026-09-02 (`scripts/probes/_545p2_capture.sql` →
`_545p2_out.txt`, 1,419 gapped rows, 912 with `ret_20d`). Joined offline, $0, to the 09-01 captures
`scripts/ep_replay_data/_pull2_out.txt` (26 closed live + 26 closed paper magna53 trades, the 270
live-source `mi_ep_alerts` rows 05-11 → 08-31, `mi_daily_closes` for those tickers) and
`campaigns_era_c.tsv` (every one of the 270 alerts walked through the CURRENT bracket by
`scripts/ep_replay.py replay --ruleset era_c`; **`ep_replay.py validate` re-run 2026-09-02: PASS** —
stop formula 44/44, entry decision 100%, exit class 97%, realised R within 0.25R on 83%). Alert-level
skip buckets come from `scripts/probes/_ladder_missed.tsv` (alert-sourced rows to 08-14) plus the nine
MAGNA53 `stop_too_wide` rejects named in `scripts/probes/stop_too_wide_cohort.py`. Reader:
`scripts/probes/_545p2_read.py` → `_545p2_read_out.txt` (re-runnable; ingests capture 2 when present).
`scripts/live_rules.py --drift-only` run first: one drift finding, in `545_retry_test_2026-09-02.md`,
not this scope. **No new prod query was run for this document.**

**Units.** `ret_1d/5d/20d`, `open_gap_pct`, `max_high_*` are FRACTIONS (0.20 = +20%;
`missed_outcomes.py:652`). `max_high_*` is maximum favourable excursion — positive by construction —
and is never used as a return here. **R in the bracket replay = the stop distance the CURRENT bracket
places (entry − 2R at half size, i.e. 2× the ORB range), at equal dollar risk** — the unit era-C live
trades are recorded in. On that unit the +2R partial target sits at +1.0R and "≥4R" means eight ORB
ranges. Recorder R on era-A/B trades is on the ORB-low stop and reads ~2× larger (PLTR +3.31R recorded
= +1.69R here).

**Era.** Three population breaks travel with every number:
1. **The security-type filter landed 2026-04-20** (`171b03d0`; leveraged-ETF fail-safe 05-17). The
   table opens 04-13. Capture 1's Q4 tail list is led by IONL, IONX, CRDU, APLX, QPUX, QBTX, GLXU,
   LABX, BEX, BEG, MVLL, DLLL — all 04-13/14; the eight I can identify by name are leveraged
   single-stock ETFs today's scan never sees (the other four await capture 2's `security_type`;
   BRUNW 05-13/14 is a warrant; VCX 04-30 a leveraged ETF per the roadmap's own 08-25 correction).
   **Every pooled scan-level share below is therefore an upper bound on the current-scan share.**
2. **Right-censoring.** 507 of 1,419 gapped rows have no `ret_20d`; 382 are August. The 20-day read
   covers 41 of 423 August rows. HTFL (08-14) has `ret_5d = +27.4%`, `ret_20d` NULL, and is excluded
   from every `ret_20d` count — the mature window is effectively 04-13 → ~08-03.
3. **Exit stack.** The bracket half applies ONE rule-set (era_c, live since 08-16) to every campaign,
   so no exit-side number here pools eras. The ADMISSION side is era-mixed by construction (each alert
   was admitted by the gate of its day) and is stated as such.

**Buckets overlap — never sum them.** A ticker-day can carry a scan row and an alert row: HTFL is in
`duplicate_scan` AND `stop_too_wide`; ABVX and EFOR in `moderate_tier` AND `duplicate_scan`.
`duplicate_scan` ("already scored earlier today") is bookkeeping, not a gate — its tail is a shadow of
other buckets. Scan-level buckets have **no ORB bars** (the scan rejected them before any order) —
daily grain only, said in every row.

## 3. The pass bar — the traded cohort on the SAME proxy, and how little of it the bracket converted

| cohort | n | mature (`ret_20d`) | tail ≥+20% @20d | share | losers (<0) per tail | realised R on the tail names |
|---|---|---|---|---|---|---|
| **26 closed LIVE trades** (real money, first attempts, 07-06 → 08-28) | 26 | 15 | 2 (SMCI, PLTR) | **13.3%** | 5.0 | PLTR +3.31R recorded (+1.69R era_c); SMCI −0.68R recorded; **0 of 2 ≥4R** |
| 26 → 20 closed PAPER trades (first attempts, 04-17 → 07-02) | 20 | 20 | 2 (INTC, NRIX) | 10.0% | 5.0 | INTC −0.48R, NRIX −1.20R — **0 of 2 ≥2R** |
| 270 admitted alerts, all | 270 | 182 | 24 | 13.2% | 4.4 | see §4 |
| 270 admitted alerts, **gapped at the open** (the like-for-like comparator) | 199 | 131 | 14 | **10.7%** | 5.7 | see §4 |
| admitted HIGH alerts | 193 | 130 | 18 | 13.8% | 4.1 | — |

**Bar = 13.3%** (the 26 live, as the pre-registration names them); the gapped admitted pool sits at 10.7%.
Realised on the 26 live: sum −7.8R, best +3.31R, **0 of 26 ≥4R**, 21 of 26 losers (recorder R).

## 4. THE BRIDGE — proxy tail → what the current bracket actually paid (n=14, the whole admitted set)

Every admitted alert that gapped at the open AND closed ≥+20% twenty sessions later, walked through the
current bracket (`campaigns_era_c.tsv`):

| ticker | date | tier | proxy @20d | bracket outcome | bucket it sat in |
|---|---|---|---|---|---|
| ABVX | 06-03 | MOD | +78.0% | settled **+2.11R** (partial, SMA-trail exit) | moderate_tier |
| EFOR | 07-22 | MOD | +59.5% | abstain — no 09:30 bar | moderate_tier |
| VPG | 05-12 | HIGH | +45.6% | settled +0.33R (partial, then breakeven stop) | infra_skip |
| NRIX | 06-08 | HIGH | +45.4% | abstain — no minute data in the entry window | traded paper |
| AMBQ | 05-12 | HIGH | +41.4% | settled **+9.32R** — the only ≥4R campaign in all 270 | infra_skip |
| AEHR | 07-15 | HIGH | +31.7% | abstain — no minute data in the entry window | HIGH, paper-EOD-sim (not missed) |
| FET | 07-31 | HIGH | +31.2% | settled +0.33R (partial, breakeven) | breaker_blocked |
| STUB | 05-14 | HIGH | +28.8% | settled +0.48R (partial, breakeven) | cap_blocked |
| LIFE | 08-04 | HIGH | +28.1% | no entry — never crossed the ORB high | HIGH, paper-EOD-sim (not missed) |
| SMCI | 07-22 | HIGH | +26.6% | settled +0.33R (partial, breakeven) | traded live |
| KSS | 05-28 | MOD | +24.2% | no trade — detected after 09:45 (window rule) | HIGH, unentered |
| PLTR | 08-04 | HIGH | +24.0% | settled +1.69R (partial, then stop) | traded live |
| TATT | 05-20 | HIGH | +23.2% | no trade — detected after 09:45 | HIGH, unentered |
| KC | 07-08 | MOD | +20.2% | no trade — detected after 09:45 | moderate_tier |

**n=14 proxy tails → 7 entered and settled → 1 ≥4R, 2 ≥2R, sum +14.6R (of which AMBQ +9.32R); 3 unenterable
by the 09:45 window rule; 3 unreadable; 1 never crossed the ORB high.** On the live partial path (§7's
deviation corrected) the same seven read +14.8R, same counts. **Unit note:** the pre-registered "+20% at
20 sessions ≈ 4R" was calibrated on the ORB-range R; on the unit the current stop places (2× ORB range)
a +20% close is roughly +1.5–2R, so the like-for-like bridge is proxy tail → **≥2R: 2 of 7 entered**;
"≥4R" stays THE GOAL's bar because it is the unit era-C live trades are booked in. Three of the seven entered names
banked the +2R partial and were then stopped at breakeven for +0.33R (a fourth, STUB, +0.48R) — the harvest leak the design doc
already measured on n=194 (82 of 106 partial-takers round-trip to +0.33R). **This is the conversion rate
every bucket share below must be read through: on the daily proxy a "tail" is roughly one name in eight
that we admit; the bracket turns roughly one entered tail in seven into ≥4R.** And the two names that
cost us most were not lost to a skip filter at all: AMBQ to a one-day infrastructure failure
(`ALPACA_LIVE_API_KEY`, 05-12, since fixed) and three tails to the 09:45 ORB-window rule (#587's topic).

## 5. Scan-level buckets — daily grain only (no ORB bars exist for a name the scan rejected)

Pooled capture-1 numbers, gapped-at-the-open rows with a mature `ret_20d` (04-13 → ~08-03). Supply per
session is an estimate (n ÷ ~79 mature sessions); capture 2 returns exact session counts.

| bucket (the gate) | n mature | tail ≥+20% | share | vs 13.3% bar | losers (<0) per tail | est. supply / session | pre-filter / non-stock among its tails (known so far) | verdict |
|---|---|---|---|---|---|---|---|---|
| `session_rvol_low` (RVOL < 2.0×) | 129 | 29 | 22.5% | above | 2.6 | ~1.6 | **≥10 of 29 are pre-filter rows** (IONL, IONX, CRDU, APLX, LABX, BEX, BEG, MVLL, DLLL, SILC — 04-13→04-17; at least 7 of those are leveraged ETFs); Q2: the legacy pre-05-06 strings carry a disproportionate share (`0.3x` 3 of 4, `0.4x` 2 of 3) | **PROVISIONAL candidate — capture 2 can only lower it**; today's scan never sees these names |
| `mcap_low` (< $500M) | 62 | 13 | 21.0% | above | 2.8 | ~0.8 | 1 of 13 known (ALMU 04-13) | **candidate for a P14 read**, provisional |
| `duplicate_scan` | 90 | 18 | 20.0% | above | 2.8 | ~1.1 | overlaps by construction (HTFL, ABVX, EFOR) | **not a gate — closed as a bucket**; its names are judged in their real bucket |
| `adv_low` (ADV floor) | 61 | 12 | 19.7% | above | 2.9 | ~0.8 | BRUNW (warrant) 05-14 | candidate for a P14 read, provisional; #595 rated this bucket 57% fake pre-flag — the gapped-only cut here already removes that class |
| `outside_top20` (gap-rank cap) | 174 | 34 | 19.5% | above | 2.6 | ~2.2 | **≥4 of 34** (QPUX, QBTX, GLXU 04-14; VCX 04-30) | **candidate for a P14 read**, provisional; the largest supply of any bucket |
| `atr_high` (ATR > 15%) | 37 | 7 | 18.9% | above | 4.0 | ~0.5 | none known | candidate, n small; median −31.5% — the visible cost is steep |
| `score_below_50` | 109 | 17 | 15.6% | above (marginal) | 3.2 | ~1.4 | none known | marginal candidate; every tail carries `catalyst=routine` — the catalyst read, not the score, is what would have to change |
| `cooldown` (60-day re-alert) | 34 | 4 | 11.8% | below | 6.5 | ~0.4 | — | **closed** (and 75% fake pre-#595) |
| `extension_gate` (up 50% in 5d) | 64 | 6 | 9.4% | below | 8.8 | ~0.8 | JLHL, AKAN, MXL are all April | **closed** — 53 of 64 lose, median −49.6%; the fat-tail claim in v2 §3.6 #47 was MFE-based and does not survive a close-basis read |
| `ma_filter` (M&A catalyst) | 34 | 1 | 2.9% | below | 14.0 | ~0.4 | — | **closed** |
| `pm_rvol_low` | 17 | 2 | 11.8% | below | 6.0 | ~0.2 | BRUNW again | closed, n tiny |
| `catalyst_downgrade` | 10 | 2 | 20.0% | above | 2.5 | ~0.1 | — | unreadable at n=10 |

**P3 tail read, not the mean:** the pooled scan-level buckets show the SAME shape as the admitted pool —
a ~1-in-5 tail with a negative median — and on losers-per-tail (2.6–3.2) they look no worse than what we
admit (5.7 on the gapped admitted pool, 5.0 on the 26 live). **That is the P1 half of the finding and it
stands even before capture 2: the skip filters are not selecting a worse population than the alert
filters are.** What capture 2 decides is how much of that is real common stock under today's scan.

## 6. Alert-level buckets — the tail put through the live bracket

Every skipped alert 05-11 → 08-31, walked by the validated harness under era_c. Status is a first-class
result: `no_trade` = the bracket refuses by rule (window after 09:45; ORB admission) · `no_entry` = the
stop-buy never filled · `abstain` = no 09:30 bar / no minute data / fill bar straddles the stop.

| bucket | campaigns | settled / no_entry / no_trade / abstain | daily proxy tail (gapped, mature) | bracket: sum · best · ≥2R · ≥4R | what happened to its proxy tails | verdict |
|---|---|---|---|---|---|---|
| **`stop_too_wide`** (ORB range > 1.5×ATR) | **13 on record** (04-23 → 08-14, MAGNA53 format); 7 in the minute-bar capture | 4 / 3 / 0 / 0 | **2 of 10 mature = 20%** — BAND 04-30 +110%, STRL 05-05 +32% (both pre-05-11, ORB-low era, outside the campaign capture); HTFL censored (+27.4% @5d) | harness **+1.2R** · live partial path **+0.5R** · HTFL +1.28R / **+1.43R** · 0 · 0 | AIP, GO, PONY never crossed the ORB high (no fill); on the live path CORT −0.10R, ATRO −0.26R, AEVA −0.59R, HTFL +1.43R (§7) | **CANDIDATE by the pre-registered bar** (n=10, both tails pre-May) — the P14 read it earns is exactly the operator's Axis 2 cell, *size down, not skip*, and it is cheap: 13 names in four months. ⚠ Capture 1's Q1 shows this bucket at n=4 with NO tail — STRL and BAND have left the bucket in the current table (§9); capture 2 reconciles 13 → 4 |
| `moderate_tier` (score 50–65) | 55 (37 gapped) | 21 / 5 / 24 / 5 | 3 of 20 (15.0%) | +3.0R · ABVX +2.11R · 1 · 0 | ABVX +2.11R; HQ (+88.6%), BHVN, KC unenterable — detected after 09:45; EFOR no 09:30 bar | above the bar on proxy; **the bracket converts one in 21 to ≥2R, none to ≥4R** — same conversion as the live control (best +1.69R). Candidate for a P14 read ONLY as part of the window/harvest questions, not as a score-bar move |
| `high_unentered` (HIGH, no skip row — the stop-buy simply never filled) | 21 (15 gapped) | 6 / 0 / 11 / 4 | 2 of 15 (13.3%) | +3.1R · +2.96R · 1 · 0 | ARM +94%, ALAB, GH, DYN (all 05-20) are NOT gapped ≥9% at the open by the daily bars — pre-market prints, #595's class; TATT 05-20 and KSS 05-28 gapped but were detected after 09:45 (window rule) | **closed** — the bracket's own no-fill; nothing to admit |
| HIGH in no skip bucket — traded by the EOD paper simulator (`mi_paper_trades`, which `missed_outcomes`' `traded` CTE excludes) or still open live (MRNA 08-19, OKTA 08-27) | 47 (38 gapped) | 8 / 12 / 4 / 21 | 2 of 27 (7.4%) | +5.1R · +2.98R · 2 · 0 | AEHR no minute data (21 abstain = June/July days with no minute capture); LIFE never crossed the ORB high | **not a missed population** — shown so the 270 reconcile; capture 2's alert-level rows confirm the label |
| `window_missed` (detected ≥09:45) | 36 (20 gapped) | 0 / 0 / 35 / 1 | 0 of 11 gapped (3 of 22 pooled: ALOY +53.9%, PGY, IREN) | none — the bracket cannot enter these by rule | — | **closed as a skip bucket; open as the #587 window question** — the three pooled tails were not gap-at-open setups |
| `breaker_blocked` (safeguard) | 12 | 7 / 4 / 1 / 0 | 1 of 6 (FET +31.2%) | **−3.2R** · +0.33R · 0 · 0 | FET +0.33R (partial, breakeven) | closed — and a safeguard is THE LINE regardless |
| `cap_blocked` (5/5 slots) | 8 | 3 / 3 / 0 / 2 | 1 of 5 (STUB +28.8%) | +1.6R · +0.77R · 0 · 0 | STUB +0.48R | unreadable at n=3 settled; the slot cap is THE LINE |
| `infra_skip` (05-12 account-fetch failure) | 13 | 11 / 1 / 0 / 1 | 2 of 7 (VPG, AMBQ) | **+5.6R · AMBQ +9.32R · 1 · 1** | AMBQ +9.32R — the single ≥4R in the whole 270-alert replay; VPG, SIBN +0.33/+0.60 | not an admission bucket; **the one ≥4R the bracket ever produced was lost to a bug that is fixed** — recorded as the existence proof that the bracket CAN convert a tail, once in 100 settled |
| `setup_other` | 13 | 6 / 5 / 1 / 1 | 0 of 5 | +2.0R · +2.05R · 1 · 0 | — | closed |
| control: 26 TRADED live | 26 | 26 / – / – / – | 2 of 13 gapped (15.4%) | −5.4R · +1.69R · 0 · 0 (era_c unit) | SMCI +0.33R, PLTR +1.69R | the yardstick |

**Read across the table:** every alert-level bucket that the bracket could enter shows the same shape as
the control — a handful of +0.33R partial-then-breakeven scratches, one or two +2R-class winners, and
(outside a one-day infra failure) **no ≥4R**. The skip filters at alert level are not where the tail is
being lost; the bracket is. **Both bracket paths are shown because the harness books a day-3/day-5 ladder
partial that live stands down (§7); it moves 14 of 267 campaigns, the control by +0.2R, and no verdict.**

## 7. HTFL — the prompting case, leg by leg (checkable by hand) — and a harness deviation it exposed

HIGH, score 96, gap +25.1%, `game_changer`; skipped 08-14 09:31:01 on `setup:stop_too_wide: ORB range
$2.55 (7.0%) > 1.5x ATR $2.19`. Current bracket, from the harness (`walk_campaign`, era_c, 09:31 submit):

| leg | when | price | shares (1 risk unit) | P&L / unit |
|---|---|---|---|---|
| entry — stop-buy at the ORB high | 08-14 09:31 | 39.06 | 0.1961 | stop 33.96 (entry − 2R, R = 2.55); target 44.16 |
| partial 1/3 (harness: day-3 ladder at the settled close) | 08-17 close | 41.94 | 0.0654 | +0.188 |
| remainder — resting stop, raised to the SMA trail, hit | 08-31 close | 47.416 | 0.1307 | +1.092 |
| **total, harness path** | | | | **+1.28R** (on the 5.10 stop distance) |

**The deviation, and it is harness-wide, not HTFL's.** The harness books the day-3/day-5 LADDER partial
(`exit_logic.py:336`, via `apply_daily_exit_step`), and that partial moves the resting stop to entry. Live
stands that branch down while the intraday +2R trigger is on (`live_tracker.py:1076`,
`skip_partial_decision=bool(PROFIT_TRIGGER_R)`): live sells 1/3 only when the high reaches the +2R
target, and otherwise holds the whole position on the entry−2R stop and the trail. So every harness row
where a ladder partial fired and the final is a breakeven stop was closed by a partial live would not
take. The reader re-walks every campaign with the ladder stood down (`walk_live_path`; the +2R partial
itself is already modelled in the daily loop): **14 of 267 campaigns change; the 26-trade control moves
from −5.4R to −5.2R; the 14-name bridge from +14.6R to +14.8R; no verdict moves — but two of the four
`stop_too_wide` fills do:**

| name | harness path | live partial path | what live actually does |
|---|---|---|---|
| **HTFL 08-14** | +1.28R (ladder ⅓ at 41.94 on 08-17; rest 47.416 on 08-31) | **+1.43R** — ⅓ at the +2R target 44.16 the first session the high reaches it (**08-18**, high 45.33), ⅔ at the same trail exit 47.416 on 08-31: ⅓×5.10 + ⅔×8.356 = 7.27 ÷ 5.10 | a winner (+2.85R on the recorder's ORB-range unit), not a ≥4R tail |
| CORT 07-30 | +0.02R (ladder ⅓ on 08-03, breakeven stop 08-04 at entry 112.00) | **−0.10R** — never reaches 126.50; holds on the 97.50 stop until the SMA trail closes it at 110.51 on 08-13 | the harness's "+0.02R" was a breakeven exit live never places |
| ATRO 08-12 | +0.23R (ladder ⅓ on 08-17 at 93.05, breakeven stop 08-18 at 85.25) | **−0.26R** — never reaches 96.75; trail-raised stop hit at 82.21 on 08-19 | same |
| AEVA 08-06 | −0.33R (day-5 "sell regardless" ⅓ at 24.06, then the trail) | **−0.59R** — stop hit at 22.46 on 08-18 | same direction, larger |
| **four fills** | **+1.2R** | **+0.5R** (three losers, HTFL) | |

AIP, GO, PONY never traded back up through the ORB high in the 09:31–09:59 window on either path — the
finding the 08-17 read reached for GO/PONY by headroom. **For the parent to file against
`ep_replay.py`'s KNOWN DEVIATIONS:** the ladder partial is booked where live stands it down; on the 44
validation trades it never bit (they died before day 3), which is why `validate` did not see it.

## 8. P9 — what downstream tightening would have to hold to afford each candidate bucket

P9 says the answer to a real tail upstream is never "we only have five slots"; it is to state what the
downstream selector must do to absorb the extra supply. For each bucket above the bar:

| bucket | extra supply into grading (est., per session) | tail it brings (pooled, provisional) | what the downstream ranker must hold to afford it |
|---|---|---|---|
| `outside_top20` | **+2.2 names** (the largest; the grading shortlist is 20 per tick, `ep_rubric.py:448`) | ~1 in 5 | keep the forwarded set's tail rate ≥ the admitted pool's 10.7–13.3% while absorbing +2.2/session — i.e. rank the bucket's tails above its 4-in-5 non-tails at least as well as the pre-score does on today's pool |
| `session_rvol_low` | +1.6 (upper bound; the real current-scan supply is smaller — capture 2) | ≤ 1 in 5 (contaminated) | as above, PLUS the bucket's own gate must be re-expressed as a band (P2): the tails sit at 0.1–0.4× session RVOL, the rule is a 2.0× line |
| `mcap_low` | +0.8 | ~1 in 5 | as above; the tails are $194M–$464M caps — a floor band, not a line |
| `adv_low` | +0.8 | ~1 in 5 | as above; #556's ADV-floor read must be re-run on the gapped-only cut |
| `score_below_50` | +1.4 | ~1 in 6 | every tail is `catalyst=routine` — the affordable version is a catalyst re-grade, not a bar move |
| `moderate_tier` | +0.5 (already graded; competes for slots only) | 3 in 20 | the slot ranker must place a MODERATE tail above a HIGH non-tail — the 09-01 selection test found no fire-time feature that does this (NULL, 49 cuts, 569 fires) |

**The honest constraint on all six rows:** the 09-01 pre-registered selection test found nothing knowable
at fire time that separates the tail (NULL on 11 features). So today no downstream selector exists that
can absorb ANY of this supply without diluting the five slots — and §4 says that even the names that
reach a slot convert to ≥4R once in seven. **The order of work P9 prescribes therefore stands as the
program already has it: conversion (Phase 3's stop × target × runner sweep) and a ranker that clears the
8% lift bar come BEFORE any admission loosening — loosening first just moves the problem.** This read
does not argue for tightening either: on the proxy the skipped buckets are no worse than the admitted
pool (§5), which is the P14 both-sides statement — admitting them costs grading budget and slot
competition (VISIBLE, +0.5 to +2.2 names/session each), and refusing them costs at most the same
~1-in-8 daily-proxy tail we already fail to convert (INVISIBLE, now measured).

## 9. What in the brief and the prior statements turned out to be wrong or stale

- **"HTFL +29% — a missed tail."** Under the current bracket it is a +1.28R/+1.43R winner. The bracket
  entered it, banked the partial, and trailed out; the run past +21% happened on the 2/3 it still
  held. It is a real EP the gate cost us (P1 stands), but it is not evidence of a missed ≥4R.
- **"stop_too_wide = 9 rejects, 5 settled, within noise" (08-17) and "0 of 4 tails" (capture 1 Q1).**
  The 08-14 ladder capture holds **13** MAGNA53-format rejects (WST 04-23, WKC 04-24, BAND 04-30, TTMI
  04-30 precede the 08-17 doc's nine), and two ran — BAND +110%, STRL +32% at 20 sessions. Both are
  absent from the current table's `stop_too_wide` bucket (Q1: n=4, best +5.3%) — re-categorised, or
  excluded by the `traded` CTE via an `mi_paper_trades` row; unknown from here. `STOP_TOO_WIDE_ALL` in
  capture 2 reconciles 13 → 4. Until then the P1 record is the 13, not the 4.
- **Capture 1's first-cut shares** (`session_rvol_low` 29/129, `outside_top20` 34/174) are pre-filter
  numbers: the security-type filter is 04-20, the table starts 04-13, and the top of the tail list is
  leveraged ETFs. Not wrong arithmetic — the wrong population, the #595 failure one layer deeper.
- **v2 §3.6 #47 "extension filter vs the fat tail — 17.6% doubled"** was MFE-based; on the close basis
  the bucket is 6 of 64 tails, 53 losers, median −49.6% — the fat tail is a wick, not a return.
- **v2 §3.6 #46's `high_unentered` ARM 05-20 +94% class:** ARM, ALAB, GH, DYN did not gap ≥9% at the open
  by the daily bars (05-20 detections came after 09:45 or with no 09:30 bar). Removed from every gapped count here.
- **The pass bar's "0 of 26 ≥4R"** is recorder R on mixed stop units; on the era_c unit the live control
  is 0 ≥2R, best +1.69R. Both are stated; neither changes a verdict.
- **The harness books a day-3/day-5 ladder partial live stands down** — first surfaced here (HTFL 08-17
  leg), harness-wide (§7): 14 of 267 campaigns, two of the four `stop_too_wide` fills flip sign. For the
  parent to file against `ep_replay.py`'s KNOWN DEVIATIONS; not fixed in this card.

## 10. What capture 2 changes, and the command

`scripts/probes/_545p2_capture2.sql` (read-only; ~1,500 rows) adds per gapped row: `security_type`
from `mi_security_types` (+ the roadmap's ever-had-a-sector fallback), a pre-04-20 flag, month,
`ret_5d` beside `ret_20d` (so August is readable at 5 sessions), day-0 red, a bad-prior-close flag
(`open_gap_pct > 1.0`), every alert-level row to 09-01 with its bucket, a prod-side recompute of
§3's traded proxy as a cross-check, and `STOP_TOO_WIDE_ALL` — every row that ever carried the reason,
with its `mi_paper_trades` / `mi_live_trades` status, so the 13 → 4 in §9 is reconciled.

```
ssh apollo@87.99.134.162 "docker exec -i apollo-postgres psql -U apollo -d apollo -A -F '|'" \
  < scripts/probes/_545p2_capture2.sql > scripts/probes/_545p2_capture2_out.psv
python3 scripts/probes/_545p2_read.py          # §D fills in; every "provisional" cell resolves
```

Direction each verdict can move: `session_rvol_low` and `outside_top20` shares can only FALL (their
known contamination is removed); `mcap_low`, `adv_low`, `atr_high`, `score_below_50` can move either
way once August's `ret_5d` rows enter; the alert-level verdicts (§6) do not depend on it except the
alert-level labels and the `stop_too_wide` 13 → 4 reconcile. **No verdict in this document is expected
to flip from closed to candidate on capture 2; three provisional candidates may close, and
`stop_too_wide` stays a candidate unless BAND and STRL turn out not to have gapped at the open.**

## 11. What this does not answer

- **Whether any scan-level bucket's tail survives a bracket.** No ORB bars exist for a name the scan
  rejected, so §5 is daily grain only. §4 supplies the conversion rate to read it through (1 in 7
  entered tails ≥4R), but that rate was measured on admitted names and may not transfer (P8).
- **The current-scan share of the scan-level buckets.** Pending capture 2 (§10); every scan-level
  share is an upper bound until then.
- **August.** 382 of 423 gapped August rows are censored at 20 sessions; the era-C exit stack is the
  live one and the era-C admission stack (rubric v4, real-time gap authority) is only weeks old —
  nothing here is a read of the CURRENT admission system, only of the gates as they stood each day.
- **The operator's "size down, not skip" for `stop_too_wide`** (Axis 2). This read applies the current
  bracket at equal dollar risk; a wider stop at smaller size is a different cell and unmeasured — and it
  is the P14 read this bucket's candidate verdict calls for. BAND and STRL cannot be bracket-replayed
  here (no minute bars before 05-11); the 08-17 read reconstructed STRL as a winner by algebra.
- **Why the bracket converts so little of the tail** — that is Phase 3 (stop × target × runner) and
  Phase 1 (retry), not this phase. §4 only measures the size of the leak.
- **Selection at fire time.** The 09-01 NULL is carried, not re-tested.
- **n.** The alert-level buckets settle 3–21 campaigns each; nothing here is load-bearing by the v2 §2
  rule (n ≥ 30, holds ex-May, fill-reproducing harness) except the §3 control and the §4 bridge, which
  are load-bearing on the second and third criteria and short on the first.
