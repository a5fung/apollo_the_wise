# #327 Anticipate coil-apex entry — WHY the live shadow loses (diagnostic, 2026-07-14)

**Question (operator):** the anticipate arm's live shadow reads ≈ −1R realized on the June cohort.
The setup (Qullamaggie/Pradeep coil-breakout continuation) is discretionarily proven — so the
mechanization is MISSING something. Find the gap; do not conclude "retire."

**Status: READ-ONLY ANALYSIS.** No strategy/threshold/entry/exit/trade-state change was made. All
numbers from prod SELECTs (`mi_consolidation_entry_shadow`, `mi_market_regime`,
`mi_anticipation_consolidation`, `mi_stock_scores`, `mi_daily_closes`) + an offline read-only
replay run in the market container reusing the production functions (`anticipation.confirm_signal_at`,
`entry_bet_outcome`, `settle_row`/`SETTLE_RULE` pess-bound — re-derived settlements match the DB
byte-for-byte on all 34 rows, so the tooling is verified against production).

---

## 0. Ground truth — what the "−1.04R (N=41)" actually is

| slice | N settled | mean R | median R | total R | win% |
|---|---|---|---|---|---|
| **All settled rows (the −1.04R)** | 41 | **−1.036** | — | −42.5 | — |
| — anticipate (9m + family_a) | 34 | **−1.226** | −1.00 | −41.7 | 17.6% |
| — confirm (live-wired 6/22–6/29 only) | 7 | **−0.113** | −0.23 | −0.8 | 28.6% |

The headline −1.04R is a **mode blend**. The anticipate arm proper is −1.23R (N=34); the 7 settled
CONFIRM rows were already ~breakeven. Every settled anticipate entry is 6/18 (18), 6/22 (13) or
6/23 (3) — **three entry days in one fortnight**, all settling through the same 6/24–6/26 SPY dip.

**Replication check (important):** the shadow did NOT surprise the offline evidence — it replicated it.

| metric | offline #327 replay (6/18 doc) | live shadow (this cohort) |
|---|---|---|
| +3R capture rate (the "validated" entry-quality metric) | 44% | **41% (14/34)** ✓ |
| realized R under SETTLE_RULE (anticipate arm, 3-mode rerun) | mean −1.2R | **mean −1.23R** ✓ |

The offline 3-mode rerun already said anticipate realizes **−1.2R under the derisk-fast harvest**
("dominated by the 60% false-coil set… as much a statement about the exit rule as the entry").
What was "validated" 6/18 was the *capture/MFE entry-quality* signal (persistence N=3) — and that
replicated too. The mechanization is doing exactly what it measured offline; the miss is in what
was never mechanized (below).

---

## 1. Angle 1 — REGIME

Regime label at each `entry_date` (`mi_market_regime`), settled anticipate rows:

| regime at entry | N | mean R | median R | total R | win% |
|---|---|---|---|---|---|
| Bull | 16 | −0.69 | −1.09 | −11.0 | 31% |
| Choppy | 18 | **−1.70** | −1.00 | −30.6 | 6% |
| Correcting/Crisis | 0 | — | — | — | — |

Tape context: SPY peaked 754.83 on **6/15**, slid to 728.99 by **6/26** (−3.4%), recovered into
July. All 34 entries fired 6/18–6/23 — **mid-rollover** — and every settlement window spans the dip.

**Read:** Choppy-day entries are ~2.5× worse than Bull-day entries, but the arm loses in BOTH cells
— a naive regime-at-entry gate would NOT have saved this cohort. The deeper regime effect shows up
as the **coil-resolution base rate**: in the offline validation window (4/21–6/17), ~40% of coilers
went on to confirm a breakout (31/77); in this June fortnight only **15% (5/34)** of the anticipated
coils ever confirmed (§3). Anticipate pays ~−1R up front on every false coil; when the tape cuts the
breakout rate from ~40% to ~15%, the arithmetic cannot be positive. **What the data cannot settle:**
there are ZERO entries in a sustained trending leg — the "does it win in a trending tape" half of
the regime question is unanswerable from this cohort (all-June, one fortnight, 3 entry days).

---

## 2. Angle 2 — RUNUP / COIL QUALITY (what a discretionary trader would refuse)

### 2a. The universe is polluted — the §2 gate (runup ≥1.15 in 45 bars + tightness) admits names no discretionary coil trader would touch

Joined to `mi_stock_scores` at entry (27 of 34 have scores; the 7 unscored are **ETFs/ETPs**):

| bucket | N | R/row | total R | note |
|---|---|---|---|---|
| ETFs/ETPs (SQQQ, QTUM, UFO, PSI, RSPT, WQTM, IVES) | 7 | **−1.95** | −13.7 | incl. SQQQ, a 3× **INVERSE** QQQ fund (its +2R "win" = the market falling). 21% of the cohort. |
| Stocks BELOW the 50SMA at entry | 13 | **−1.70** | −22.1 | "runup" = a 15–25% bear-market bounce coiling UNDER a declining 50MA (FUTU −26% vs 50MA / RS 3.8; PSIX −28% / RS 6.4; PRIM −25% / RS 1.3; DRUG −21% / RS 4.1) |
| Stocks ABOVE the 50SMA at entry | 14 | **−0.42** | −5.9 | the only bucket resembling the discretionary setup |

Other pollution: 6/27 scored names have ADV20 < $1M (SENEA $0.2M, LMB $0.3M, DRUG $0.4M…) —
untradeable for a real book and noisy prints for a shadow.

### 2b. Winners vs losers within the cohort

| dimension | winners (N=6) | losers (N=28) | separates? |
|---|---|---|---|
| RS composite (median, scored subset) | **72.4** | 52.7 | YES — direction matches the leader requirement |
| RS ≥ 90 count | 1/5 | 4/22 | (both low — the cohort simply has few leaders) |
| stop distance (median % of entry) | **3.22%** | 1.70% | YES — strongest single separator (§4) |
| prior runup ratio | 1.245 | 1.267 | no |
| days peak→entry (coil age) | 15 | 16 | no |
| ATR14 % | 5.6 | 5.8 | no |
| fire-day vol ratio / range | 0.67 / 4.3% | 0.75 / 3.8% | no |

**Read:** within-cohort, the *coil-shape* telemetry (runup size, age, tightness readings) does NOT
sort winners from losers — because the whole cohort sits at the weak end (runup median 1.25 ≈ a 25%
move; Qullamaggie anticipation names carry 50–100%+ prior legs, RS 90+, riding rising MAs). What
sorts outcomes is **name quality** (RS, above/below 50MA, instrument type) and **stop geometry**.
The mechanization mechanized the *timing* (3 tight days — which works: 41% capture, replicating
44% offline) but never mechanized the *selection stack* the discretionary edge rides on.

---

## 3. Angle 3 — ANTICIPATE vs CONFIRM (head-to-head on the SAME cohort)

Read-only replay in the market container: for each of the 34 settled anticipate coils, scan
`confirm_signal_at` (close > post-peak base high + vol ≥1.5×ADV20, stop = base low) from
anchor+2 through anticipate-entry+15 bars; settle identically (`entry_bet_outcome` +
`settle_row`/SETTLE_RULE, pess bound). No fire = no trade (kept in the universe, 0R).

```
CONFIRM fired on            :  5 / 34 coils   (BKD +0.96 · ICLR +0.94 · EVC +0.17 · CMPS −0.48 · ZVRA unsettled)
CONFIRM never fired         : 29 / 34 coils   (85%) — the coil NEVER broke out upward
Confirm total (4 settled)   : +1.6R           vs anticipate on the same 34 coils: −41.7R
Full-universe mean (0R skip): ≈ +0.05R        vs anticipate −1.23R
Per-coil head-to-head       : confirm ≥ anticipate on 25 of 33 evaluable; anticipate better only on
                              its 6 winners (BKD, MGM, SENEA, DRUG, SQQQ, UTI — confirm skipped or trailed)
Live confirm shadow (different names, wired 6/22–6/29): N=7 settled, −0.11R; 96 rows still open (§6)
```

**Read — the operator's "too early" hypothesis is confirmed, but the sharper statement is
"mostly NEVER":** the anticipate loss is not paid on good coils entered a few days early — **85% of
the coils it bought never produced the breakout at all** in this tape. Confirm dominates not by
better entries but by *not paying for false coils* — it is structurally protected from exactly the
failure mode that killed anticipate here. Anticipate's compensation (entering a median ~2% below the
eventual break, per the 6/18 study) cannot pay for a 6-to-1 false-coil rate at ~−1R (and worse, §4)
per false coil.

Caveats on the confirm side: only 4 settled fires (tiny); when confirm fires AFTER a coil already
collapsed, its base_low stop is degenerate-wide (CMPS 27.6%, EVC 27.2% risk — R units near-meaningless);
and this daily close-break detector is not the live #94 intraday watcher (the Phase-B lesson: proxies
mis-time it both ways). Confirm ≈ breakeven-in-a-bad-tape is the honest claim — not "confirm has edge."

---

## 4. The trade-construction / measurement gaps (found on the way; load-bearing)

**(a) The coiled_low stop has no floor and produces broken R math.** Stop = the fire-bar's low:
median 1.95% of entry, **min 0.06%** (CNK), 0.13% (CLS), 0.40% (HEI), 0.84% (OSCR). Monotone
gradient on the same 34 rows:

| stop distance | N | mean R | win% |
|---|---|---|---|
| < 1.5% | 14 | **−2.29** | 7% |
| 1.5–3% | 10 | −1.16 | 0% |
| 3–4.5% | 8 | +0.01 | 38% |
| 4.5–6% | 2 | +0.93 | 100% |

**(b) Gap-through-stop slippage in tiny-R units is 64% of the whole loss.** `settle_row` fills a
gapped stop at `min(stop, open)` — realistic — but dividing by a ~1–2% risk unit books multi-R
losses: 13/34 rows settle below −1R (worst: PRIM **−13.98R** = one gap ≈ ⅓ of the entire cohort
loss). Clamp every stop-out at −1R and the cohort mean moves **−1.23R → −0.44R** (−26.8R of the
−41.7R total is beyond-−1R slippage).

**(c) The "validated" metric and the realized metric are measured under OPPOSITE intrabar bounds.**
`entry_bet_outcome` credits the target FIRST on a bar that spans both (optimistic); `settle_row`
settles "pess" (stop first). With +3R targets ≈ +3–6% and stops ≈ 1–2%, one ordinary daily bar
spans BOTH — so the same row reads `capture` AND realizes −1R. The 14 captures carry **mean
+6.4R uncapped MFE yet mean −0.76R realized** (only 6/14 realized > 0). Also the bet window
(12 bars) vs the harvest time-stop (5 days) diverge. At these stop widths daily bars cannot resolve
the ordering — the capture% is intrabar-optimistic, the realized R intrabar-pessimistic, and neither
is a faithful trade.

**(d) Counterfactual grid** (same 34 entries, same pess-bound settle, offline replay):

| variant | mean R | note |
|---|---|---|
| as recorded (coiled_low stop) | −1.23 | the shadow number |
| stop-outs clamped at −1R | −0.44 | isolates gap slippage |
| structural_low stop (already recorded per row) | −0.63 (−0.22 ex-PRIM) | rescues CMPS/EVC/OSCR/ZVRA/… |
| 2%-minimum stop floor | −0.76 | PRIM still −8R |
| **stocks-only + above-50SMA + structural_low stop** | **+0.41 (N=14, 8/14 win)** | quality gate alone → −0.42; stop fix alone → −0.63; **the PAIR flips the sign in the same losing fortnight** |

---

## 5. The single most-likely MECHANIZATION GAP

**We mechanized the coil's TIMING but not the trader's SELECTION STACK or RISK GEOMETRY.** The
persistence signal itself works as validated (41% vs 44% capture, +6.4R mean MFE on captures). What
the mechanical arm is missing, in evidence order:

1. **Low-quality coils taken (the biggest lever):** 21% ETFs (incl. an inverse fund), 48% of scored
   names below their 50SMA with RS as low as 1–7 — bear-bounce "coils" a discretionary trader
   auto-skips. Quality buckets are monotone: −1.95 / −1.70 / −0.42 R/row. In a chop tape these junk
   coils almost never resolve upward — the 85% never-confirm rate (§3) is the same gap seen from the
   other side, and it is why Confirm beat Anticipate here.
2. **Degenerate stop geometry as the amplifier:** a no-floor bar-low stop (median ~2%, min 0.06%)
   turns normal overnight noise into −2R…−14R prints — 64% of the entire loss is gap-slippage beyond
   −1R, and stop width is the single strongest within-cohort separator.
3. Regime is real but currently untestable: the arm loses in both observed cells, the breakout base
   rate collapsed ~40%→15% vs the validation window, and there is no trending-tape data yet.

Anticipate-vs-Confirm is partly a *symptom* of gap 1: an anticipate entry pays for every false coil
up front, so it is maximally exposed to a junk-heavy universe in a chop tape; Confirm is
breakout-conditional and structurally shielded. On this evidence, "switch to Confirm" alone would
treat the symptom; gating the universe + fixing the stop treats the cause — and the +0.41R filtered
counterfactual (same losing fortnight) is the direct evidence the setup itself is not dead.

---

## 6. RECOMMENDATION (proposal only — operator-signed; #327 is a shadow, zero execution authority, but detection-criterion changes go through CHANGE_PROCESS)

1. **Quality-gate the anticipate shadow universe** (the discretionary selection stack, mechanized):
   common stocks only (no ETF/ETP/inverse); price above the 50SMA at fire; RS composite floor
   (evidence here separates at ≥~60–70; calibrate on the labeling pass); ADV20 floor (≥$5M).
   Cheapest honest form: record a `would_pass_quality` flag on every fire and keep recording ungated
   fires — both cohorts accrue N, nothing is lost, the graduation eval compares.
2. **Fix the stop geometry:** make `structural_low` the headline settled stop (it is already recorded
   per row) and REJECT fires whose coiled_low risk is <~1% of entry (untradeable noise that poisons
   R math). Keep settling both stops for comparison.
3. **Fix the measurement honesty gaps:** flag rows where target and stop sit inside the same daily
   bar (the capture/realized bound conflict); reconcile the 12-bar bet window vs the 5-day harvest
   (report both horizons); consider settling opt+pess bounds per row so the bracket is visible.
4. **Re-wire Confirm as a tagged parallel shadow arm** (it was un-wired 6/29 for measurement purity;
   as a separately-tagged arm it is the natural control, and its 96 pending rows will settle into a
   real confirm read regardless).
5. **Record regime-at-entry in the shadow row** (one column) and keep the arm running through a
   trending leg before any regime-gate decision — the regime cell that matters has zero data.
6. **Ops:** the Family-A readiness/settlement job appears not to have run Mon 7/13 (last insert/settle
   7/10 17:37 ET; 158 rows now past-ripe: 63 anticipate + 95 confirm). Verify tonight's 17:35 ET run
   settles them; if it does not, that is a bug to chase — the confirm read depends on it.

## 7. N / power caveats (what this data can and cannot settle)

- N=34 but only **3 entry days in one fortnight**, all settling through the same 6/24–26 SPY dip —
  effective independent observations ≈ 3 day-cohorts. Treat every magnitude as directional.
- **One name is ⅓ of the loss:** PRIM −13.98R (single gap event). Ex-PRIM mean = −0.84R. The sign
  survives; the magnitude is outlier-loaded.
- The counterfactual grid (§4d) is an in-sample re-slicing of the same 34 rows chosen after seeing
  the data — hypothesis-grade, not proof. The +0.41R filtered cell is N=14. Forward-shadow it
  (recommendation 1/2) before believing the number.
- The confirm replay settled only 4 fires, with degenerate-wide stops on late fires, and its
  detector is a daily close-break proxy, not the live intraday watcher. "Confirm ≈ breakeven in this
  tape while anticipate bled" is solid; any positive confirm edge claim is NOT supported yet.
- The regime split has no Correcting-at-entry cell and no trending-leg data at all; the 40%→15%
  confirm-rate comparison crosses different universes (9M offline cohort vs mostly family_a shadow).
- rmv_15d / vol_dryup telemetry is NULL on this whole cohort (all rows pre-date the 6/27 gate move) —
  the volume-dryup quality axis could not be evaluated.

## 8. Unresolved / tooling limits

- Whether a real intraday confirm watcher (vs the daily proxy) changes the confirm read — offline
  structurally cannot answer (Phase-B lesson); only its shadow can.
- Why the 7/13 job run is missing (container logs for the window were empty of the job's lines) —
  not diagnosed here (read-only session); flagged in rec 6.
- True intrabar ordering for tight-stop rows (capture vs stop first) needs minute data; the existing
  `_327_pull_minute.py` tooling could bound it offline on this cohort if the operator wants the
  capture% de-rated honestly before re-validating the entry signal.

*Method + provenance: all SQL against prod read-only 2026-07-14; replay script (container, read-only,
production functions) reproduced every DB realized_r exactly before any counterfactual was trusted.*
