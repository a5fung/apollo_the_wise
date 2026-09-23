# #503 — 0-for-9 live cohort: per-trade forensic (variance, or an upstream defect?)

**Date:** 2026-07-25 (PT) · **Status:** EVIDENCE + READING for operator ruling — changes NOTHING live.
**Scope:** the 9 closed `mi_live_trades` rows (`account_mode='live'`, `status='closed'`, 2026-07-06 → 07-24, cum −7.50R / −$180.16). Read-only prod SELECTs run 2026-07-25; every number below is from prod rows or code, not prior-doc prose. Parent: #454. Per CHANGE_PROCESS rule 3, the per-trade classes are **my reading — the ruling is the operator's.**

**MFE source (both #503-card data traps avoided):** `mi_live_trades.highest_price_seen` — verified in code to be a legitimate MFE-before-exit tracker: seeded with the fill price by the websocket handler (`trade_stream.py` ~804), then advanced every 5 min during market hours by `track_open_position_extremes` (`order_manager.py` ~3730) over Polygon minute bars restricted to `t >= filled_at`, monotonic `GREATEST`, **open trades only** (a closed row is never touched, so post-exit bars can't leak in). Cross-validated against `mi_daily_closes`: for every trade that held to its day high, `highest_price_seen` equals the daily high **exactly** (MANE 129.80 = 7/15 high; NVCR 21.4506 = 7/24 high; THC 246.815, WKC 41.20, SMCI 32.585 = day highs). `mi_pivot_stop_shadow` and `mi_ep_delayed_residual.fwd_*` were not used.

*Granularity caveat:* 5-min polling means a sub-5-minute spike can be missed for the fast stop-outs (worst case HUT, held 51 s — likely zero polls; its true MFE is bounded by the 9:31 minute-bar high). Direction of error: MFE slightly **understated** on the ≤12-min holds. This cannot manufacture the two large-MFE trades — those are corroborated by daily highs.

## 1. The per-trade forensic table

R throughout = deployed-risk basis, risk/share = fill − initial stop (see §4 for why this differs from the official `total_pnl/risk_dollars`). Planned entry = ORB high (the bracket trigger); fill-vs-plan includes the designed 0.5% stop-limit buffer. Regime = at-alert label on the trade row (prior nightly; EOD frame differs only on 7/06: Bull).

| # | Ticker | Alert | Regime | Score (thresh) | Entry path | Plan → fill (chase) | Hold | **MFE before exit (R)** | Exit | Exit R (budget / deployed) | Post-exit (daily) | **Class (my read)** |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | WULF | 07-06 | Choppy | 96 (70) | organic HIGH | 24.61 → 24.62 (+0.04%) | 24 min | **+0.48** (25.01) | stop 23.80, no slip | −0.70 / −1.00 | closed −10% below entry; fell for days | **(a) variance** |
| 2 | CRCL | 07-10 | Choppy | 60 (70) | **judge promote** | 70.66 → 70.65 (−0.01%) | 9 min | **0.00** (fill = HWM) | stop 69.29→69.28 | −0.81 / −1.01 | post-stop pop to 72.86 (~+1.6R) then −6.4% close; lower all week | **(b) entry quality** |
| 3 | WDFC | 07-10 | Choppy | 72 (70) | organic HIGH (judge quality-read: demote, tier held) | 295.00 → 296.235 (+0.42%) | 9 min | **0.00** | stop 287.06→286.72 | −0.80 / −1.04 | closed 264.91 (−11% below entry); never recovered | **(e) regime** |
| 4 | TSEM | 07-14 | Correcting | 80 (75) | organic HIGH | 273.25 → 274.00 (+0.27%) | 12 min | **0.00** (fill = day's top tick) | stop 266.34→266.33 | −1.05 / −1.00 | closed 255.49; below entry 7 sessions later | **(e) regime** |
| 5 | MANE | 07-15 | Choppy | 72 (70) | organic HIGH | 118.75 → 119.34 (+0.50%) | 1d 0h | **+7.92** (129.80 day-1; peak CLOSE +3.30R) | day-2 open crash, stop 118.02 filled 119.04 (+slip) | −0.11 / −0.23 | day-2 low 104.46 (−13% below entry) | **(d) exit discipline** |
| 6 | HUT | 07-20 | Correcting | 72 (75) | **judge promote** | 103.48 → 103.48 (0.00%) | **51 s** | **0.00** (≤ minute-bar high) | stop 101.4482→101.31 | −0.98 / −1.07 | day-1 close < stop, but re-crossed ORB-high same day (high 107); then **+19% in 3 days** (120.38 on 7/23) | **(d) exit discipline** |
| 7 | NVCR | 07-23 | Correcting | 84 (75) | organic HIGH | 19.05 → 19.15 (+0.52%) | 1d 6h | **+2.00** (21.4506, day-2 morning) | stop 18.00→18.0008, all-day day-2 bleed | −1.07 / −1.00 | closed 17.65 below stop | **(d) exit discipline** |
| 8 | THC | 07-24 | Correcting | 60 (75) | **earnings override** (`earnings_override_applied`) | 240.47 → 241.67 (+0.50%) | 3h 12m | **+0.64** (246.815) | stop 233.58→233.53 | −0.81 / −1.01 | closed 233.2 ≈ stop | **(b) entry quality** |
| 9 | WKC | 07-24 | Correcting | 60 (75) | **earnings override** (judge quality-read: demote, tier held) | 39.995 → 40.16 (+0.41%) | 2h 29m | **+0.90** (41.20) | stop 39.00→38.97 | −1.18 / −1.03 | closed 38.14 below stop | **(b) entry quality** |

Tally: **(a)×1 · (b)×3 · (c)×0 · (d)×3 · (e)×2.** All 9 exits are `stop_hit` via websocket; zero time-stops, zero partials (none survived to Day 3). All `entry_attempt=1`; the 6 same-day stop-outs carry `block:r3_reentry_disabled` (re-entry is config-off).

**The (b)/(e) boundary is soft at n=1–3 per cell** — WDFC/TSEM could be argued (b), CRCL (a). What is NOT soft: **(c)=0 among the 9** (every fill at or below the designed `orb_high × 1.005` limit, max chase +0.52%, one fill AT trigger, one below plan) and the MFE column itself.

## 2. MFE distribution — the load-bearing evidence

```
0.00R ×4   (CRCL, WDFC, TSEM, HUT — entry was the high-water mark; stopped in 51s–12min)
+0.48R     (WULF)
+0.64R     (THC)
+0.90R     (WKC)
+2.00R     (NVCR — surrendered to −1.07R)
+7.92R     (MANE — surrendered to −0.11R)
```
Median +0.48R · mean +1.33R. Plus the **open** 10th trade: SMCI (filled 7/22 at 29.47, stop 28.50) reached **+3.21R MFE** (32.585, 7/23) and sits ≈ +0.65R unrealized at the 7/24 close with the stop still at the original −1R.

**Read against the #268b calibration** (win 30%, 13% of trades ≥ +3R): 9 trades "should" contain ~2.7 winners and ~1.2 trades ≥ +3R. **The winners occurred at the MFE level at almost exactly the expected rate** — 2 of 9 closed reached ≥ +2R (3 of 10 counting SMCI), 1 of 9 exceeded +3R (MANE +7.9R). The selector is not dead. What produced 0-for-9 is that **neither runner converted**: both were fully reclaimed by day-2 reversals before any profit-protecting exit could exist.

## 3. Why the runners could not convert — designed, not broken

Verified in `broker/exit_logic.py` + `live_tracker.py` + the audit trail:

- Days 1–2 the ONLY live exit is the original ORB-low hard stop. The SMA10/20 trail needs **≥10 daily closes since entry** to produce a value; partials start Day 3; the 9:35 "stop refresh" is housekeeping (re-places the same GTC stop — every audit row reads `$X → $X … after 0 held`). NVCR's stop was re-placed at $18.00 on day 2 *while the position was +2R* — correct per current design (prior-day low = 18.00; no other rule exists).
- The giveback/peak-lock hook (`giveback_floor`, ADR 0023 Card 1) **exists, is offline-validated (+$8,075 lock-attributable per #306), and is DEFAULT-OFF with no live caller.**
- Honest counterfactual under the SIGNED design (7/12 ruling: close-below decision-line, peak from running CLOSES): it saves **only MANE** of the 9 (day-1 close +3.30R arms it; ~50% floor ≈ 121.5 → ≈ +1.6R instead of −0.11R; cohort −7.50R → ≈ **−5.8R**). It does NOT save NVCR (peak *close* was only +0.73R; its +2R peak was intraday day-2) and would not arm on SMCI's closes to date. An **intraday-peak** variant (the code comment already anticipates wiring `highest_price_seen`) is the version that reaches NVCR/SMCI. That arm-basis fork is exactly the open #306 question, and this cohort is its first real-money evidence.

So exit discipline explains the **absence-of-winners** anomaly, but only ~1.7R of the −7.5R. The remaining ≈ −5.8R is seven fast full stops — and 62% full-stop frequency was normal even in the calibration's +0.95R Bull year.

## 4. Stale/incorrect claims found (verify-against-primary)

1. **"Mean loss −0.833R is TIGHTER than −1R ⇒ stops working as designed" (in the #503 task line) is a denominator artifact.** `risk_dollars` is the *budgeted* risk (`equity × risk_pct`, order_manager.py:163) but deployed risk is `shares × (entry − stop)` after integer floor + the 20%-notional cap — systematically smaller (WULF: $32.80 deployed vs $47.13 budgeted; CRCL 14 shares notional-capped). On deployed risk the exits are: −1.00, −1.01, −1.04, −1.00, −0.23, −1.07, −1.00, −1.01, −1.03 — **mean −0.93R, median −1.01R, 6 of 9 at or beyond −1R.** Stops ARE mechanically clean (max slippage 6.8% of R, on the 51-s HUT whipsaw; MANE got positive slippage), but nothing is "tighter than −1R." Side-effect worth knowing at band activation: the kill/scale evaluator reads the same budget-basis R, i.e. the trailing-20 it prints is **flattered ~10–17% relative to deployed risk** (observation only; bands are signed — #454's context).
2. **magna53_ep.md #500 change-log Status ("Built 2026-07-23, NOT yet deployed") is stale.** #500 WAS deployed 7/23 evening via the two-step (commit `d212334`, apollo-execution restart, Gate-5-G catch). The #503 task line ("live since 7/23") is correct.
3. Minor hygiene: MANE 2026-07-15 has **two** duplicate `mi_ep_alerts` rows (gap 11.08 / 10.66 — the #59 dedup class). And the 9:35 stop refresh's first `place_stop_order` attempt failed with APIError on **7 of 8** refresh sequences (retry succeeded every time) — benign so far but 100%-systematic; belongs to #501's silent-failure domain.

## 5. Context outside the 9 — the funnel was also adversely filtered

All live-account rows 7/01–7/24 (16): the 9 closed + SMCI (open) + DOCN 7/07 & CLSK 7/14 (ORB never broke — correct no-trigger) + IREN 7/20 & HAS 7/21 (`window:out_of_orb`, 9:50–9:51 detections — design) + **AEHR 7/15 (score 96, broker `rejected`)** + **ARWR 7/22 (score 80, in-the-money-stop broker cancel — the #500 trigger case; sim MFE +1.7–2.1R).** The two entry-MECHANICS losses in the window happened to be two of the highest-scoring candidates — the (c) bucket is empty *within* the 9 partly because mechanics failures kept those names OUT of it. #500 (live since 7/23) closes the ARWR class; AEHR's reject is the #475/LULD-adjacent class. Note AEHR closed day 1 at 87.79 vs a ~98–100 entry — that miss likely SAVED ≈1R.

Concentration (#452): 3 of 9 crypto-adjacent (WULF, CRCL, HUT) but spread across three separate weeks; max simultaneous open positions was 2 (NVCR+SMCI); same-day pairs were cross-sector. **No evidence concentration contributed to this cohort.**

## 6. Bottom line (my reading — operator rules)

**Not pure variance, and not a broken detector.** Decomposition:

1. **Selection is alive.** Fills are mechanically clean (§1), and winners appear at the MFE level at the calibration's expected rate (§2). Nothing upstream of the exit is demonstrably broken.
2. **The named structural gap is exit-side and already has an owner: #306.** Zero profit-protection exists between the ORB-low stop and Day-3 partials; the built, offline-validated giveback hook is dark. This cohort adds the first live-money evidence: 2 of 9 closed (3 of 10 with SMCI) reached ≥ +2R and none converted; the signed close-below variant recovers ~1.7R of the −7.5R; the intraday-arm variant is what reaches NVCR/SMCI-class trades. **SMCI is a live instance of the same exposure right now** (+3.2R MFE seen, stop still at −1R; the Day-3/5 partial machinery reaches it Monday 7/27).
3. **The residual ≈ −5.8R reads as regime-priced variance** — 7 fast full stops, 4 with literally zero favorable excursion, in a Choppy/Correcting tape the #268b envelope never priced. At Bull-calibrated 30% WR, P(0-for-9) ≈ 4%; at any plausible non-Bull WR (unmeasured — the envelope gap), it is unremarkable. **(e) at cohort level.**
4. **Participation-policy exposure, surfaced for the operator (no change proposed):** 4 of 9 entries (CRCL, HUT via judge promote; THC, WKC via earnings override) entered UNDER the regime-raised threshold through mechanisms that predate the #268b envelope — the regime brake exists to shrink participation in hostile tape, and in this cohort **half the trades came through its bypasses; all four lost (−3.78R), max MFE +0.90R.** n=4 proves nothing (the promotes cited real catalysts — HUT's was arguably right, it ran +19% after stopping), but at band activation (~8/20) the operator should know the non-Bull cohort composition. Both judge "demote" quality-reads (WDFC, WKC — tier held) preceded losses, 2/2. Context routes to #454's regime fork (§5b of the band review).
5. **Underdetermined at n=9, stated plainly:** whether non-Bull win rate is materially below 30% (regime effect vs unpriced variance); whether bypass entries genuinely underperform organic HIGHs; the per-trade (b)-vs-(e) splits. None of these support a retune today, and this doc proposes none.

**Routing (existing tasks only):** MFE-surrender evidence + arm-basis fork → **#306** · re-entry-disabled after the HUT whipsaw + AEHR reject class → **#414** · ARWR cancel class → **#500** (verify-live layers now watchable) · concentration null result → **#452** · regime-composition + budget-vs-deployed R basis at activation → **#454**.
