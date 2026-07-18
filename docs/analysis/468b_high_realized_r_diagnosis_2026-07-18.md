# #468b — WHY live MAGNA53 HIGH realized-R is −19.1R: the decomposition (2026-07-18)

**⛔ THE LINE — READ-ONLY DIAGNOSIS.** This document changes NO strategy, entry, exit, stop,
sizing, or selection code. Every fix named in §7 is DESIGN-ONLY: operator sign-off +
`docs/setups/CHANGE_PROCESS.md` + N≥10 backtest before anything live moves.

**Inputs (all local, re-runnable offline):** the #468 TSVs
(`scripts/probes/_468_{trades,cohort,daily,minute}.tsv`) + the #468 probe machinery
(`scripts/probes/_468_moderate_realized_r.py`, reconstruction reused verbatim).
**Generator for every number here:** `scripts/probes/_468b_high_diagnosis.py` (pure local
computation; no prod access this session). Companion study:
`docs/analysis/468_moderate_vs_high_realized_r_2026-07-18.md` (its §3 report was run this
session — numbers now live in both docs).

---

## 0. TL;DR — where the −19.1R actually went

31 closed `mi_live_trades` magna53 rows: **−19.1R total, mean −0.62R (SE 0.22), median
−0.79R, 6 winners / 25 losers.** $ view: −$9,473 (paper-mode −$9,377; real-live only −$96 —
the RED-3 start-small clamp kept real damage trivial; this diagnosis is cheap tuition).

The leak is **NOT selection** (20 of the 21 losers with a known 5-day outcome were on stocks
that went UP afterwards, −22.3R lost on rising names; cohort raw fwd_5d avg +8.5%). It decomposes as:

| # | Bucket | R attributed | One-line mechanism | Addressed? |
|---|---|---|---|---|
| 1 | **EXIT/MANAGEMENT** (winner giveback + no harvest before day 3) | **≈ −9.0R gross** (−5.9R giveback on 5 recon-winners + ≈ −3.1R "recon banked the +1R half, live rode the round trip") | The #306 hole exactly: no trail days ~1-9, partial only day 3-5, nothing reads the peak | **YES — #306 W3 design** (peak-lock, +$8,075 sweep-attributed); this doc is its realized-R corroboration |
| 2 | **ENTRY+STOP GEOMETRY** (chase ORB-high, stop at 1-min ORB-low) | **−6.3R** (idealized-exit reconstruction of the SAME 28 trades; 20 negative day-0 exits, median 12-minute hold) | Geometry converts a +8.5%-in-5-days cohort into ≈ 0R expected (recon full-universe +0.02R, win 29%, profit 449% in top-3) — near-zero-edge before any execution cost | **PARTLY** — day-0 stop-out lane = W2/#414; the quantified "geometry ≈ all of the raw edge" statement is NEW |
| 3 | **STOP EXECUTION** (fills beyond −1R) | **−6.7R over 9 trades** — SYRE −4.0 alone (overnight gap-through), MRAM −1.2 (suspected DOUBLE-COUNTED exit legs, §4), 7 others −1.5 combined (fast-tape slip) | Stops are floors, not prevention; overnight holds carry gap risk | SYRE = **#450 F1 realized**; MRAM = data-quality check (SELECT in §8) |
| 4 | SELECTION | **small at n=31** — only NAVN (−1.1R) was a genuinely failing stock; quality gradient exists (score 90+ mean −0.17R vs sub-70 −1.55R; `strong` −0.30R vs `game_changer` −1.12R; engine-authored −0.39R vs judge −1.17R) but every cell is negative | Direction consistent with B6/meta-rubric; cells are n=4-13 | #328/#330/#331 territory |
| 5 | REGIME | **unresolved locally** (SELECT in §8); per #454 the window is ~94% Bull → stratification likely degenerate | June cluster (−10.2R over 7 trades) coincides with judge-era + `game_changer` concentration, not an identified regime shift | #454 |

Arithmetic reconciliation (exact): −19.1R = paired-recon −6.3R (geometry, n=28)
+ live-vs-recon delta −11.3R (management −9.0 gross + stop-execution −6.6 + partial-fill
accounting credit +4.3) + unpaired −1.4R (TSEM/MANE too recent to settle, BSX pre-cohort).

**Primary leak = exit/management (#306), with geometry a close structural second.** The
highest-leverage already-designed fix is the #306 W3 peak-lock; the genuinely NEW finding
is that even perfect SETTLE-rule exits only get this entry geometry to ≈ breakeven — an
operator-level fork about the bracket itself, not a parameter tune (§7).

---

## 1. The 31 trades (sorted by realized R)

R = `total_pnl / risk_dollars` (risk_dollars = INTENDED risk at submission — see the
partial-fill caveat in §3). `recon` = the same (ticker, date) through the #468 idealized
reconstruction (identical entry/stop geometry, SETTLE_RULE exits, pess bound).
`Δ` = actual − recon = what live execution+management cost vs the idealized exits.

```
ticker date        mode      R   d0? hold    r3  stop%  score cq        fwd5d%  recon      Δ
SYRE   2026-06-22  paper -5.02    .  2d       .   3.5     60 game_chg    +1.7   -1.85  -3.16
MRAM   2026-05-11  paper -2.23    Y  9min     .   6.7    115 strong     +29.2   +0.00  -2.23
OMCL   2026-04-28  paper -1.52    Y  19min    .   2.2     96 strong      +2.0   -1.00  -0.52
JBL    2026-06-17  paper -1.50    Y  22min    Y   1.6     60 game_chg    +4.0   -1.00  -0.50
NRIX   2026-06-08  paper -1.20    Y  9min     Y   5.0     76 game_chg   +20.9   +0.00  -1.20
NAVN   2026-06-11  paper -1.10    Y  17min    Y   5.6     80 game_chg    -2.3   -1.00  -0.10
RUM    2026-06-04  paper -1.07    Y  5min     Y   5.4     84 strong      +1.7   -1.00  -0.07
TSEM   2026-07-14  live  -1.05    Y  12min    Y   2.8     80 game_chg      ?    (unset)
MNDY   2026-05-11  paper -1.03    Y  ?        .   4.7    101 strong      +2.0   -1.00  -0.03
KLAR   2026-05-14  paper -0.95    Y  8min     .   4.6     84 strong      +1.1   -1.00  +0.05
NVTS   2026-06-03  paper -0.86    Y  7min     Y   3.9     84 strong      +2.3   -1.04  +0.17
AMD    2026-05-06  paper -0.84    .  1d       .   1.9     96 game_chg   +11.3   +0.00  -0.84
CRMD   2026-05-14  paper -0.81    Y  93min    .    ?      65 strong      +3.5   -1.00  +0.19
CRCL   2026-07-10  live  -0.81    Y  9min     Y   1.9     60 game_chg    +1.1   +0.00  -0.81
WDFC   2026-07-10  live  -0.80    Y  9min     Y   3.1     72 game_chg    +0.9   -1.00  +0.20
RLAY   2026-05-21  paper -0.79    Y  5min     Y   3.3     72 game_chg    +8.9   -1.00  +0.21
WULF   2026-07-06  live  -0.70    Y  24min    Y   3.3     96 game_chg   +10.7   -1.00  +0.30
SMCI   2026-05-06  paper -0.64    .  6d       .   4.0     65 strong      +4.9   -1.00  +0.36
DY     2026-05-27  paper -0.53    Y  112min   Y   2.0     50 strong      +4.3   -1.00  +0.47
INTC   2026-04-24  paper -0.48    Y  132min   .   2.4    100 strong        ?    -1.00  +0.52
CSCO   2026-05-14  paper -0.42    Y  20min    .   2.1    101 strong      +3.3   -1.00  +0.58
DELL   2026-05-29  paper -0.29    Y  7min     Y   1.0    115 strong     +11.5   -1.00  +0.71
TEAM   2026-05-01  paper -0.28    .  5d       .   2.8    100 strong      +8.4   +0.00  -0.28
BSX    2026-04-23  paper -0.25    Y  132min   .   1.8      ?  ?            ?    (absent)
MANE   2026-07-15  live  -0.11    .  1d       .   1.1     72 game_chg      ?    (unset)
KURA   2026-04-17  paper +0.02    .  4d       .   0.8    100 strong        ?    +2.00  -1.98
FTRE   2026-05-05  paper +0.14    .  7d       .   2.4     84 strong     +11.5   +2.00  -1.86
QURE   2026-06-17  paper +0.51    .  15d      .   4.9     80 game_chg    +4.8   +1.56  -1.05
RCAT   2026-05-28  paper +1.30    .  8d       .   4.9    101 strong     +11.6   +2.00  -0.70
CRSR   2026-05-27  paper +1.69    .  12d      .   4.2    101 strong     +33.4   +2.00  -0.31
BW     2026-05-11  paper +2.52    .  16d      .   3.3     96 strong     +16.5   +2.00  +0.52
```

Texture that matters:
- **20 day-0 negative exits (−18.4R gross), median hold 12 MINUTES.** The bracket buys the
  ORB-high break at 9:33-9:53 and is dead before 10:00 on most losers. 13 carry
  `block:r3_reentry_disabled` — the Day-1-stop-out marker (R3 ship 5/17), not a distinct
  failure; it just labels the day-0 stop path.
- **Ticker concentration:** SYRE alone is −5.0R (26% of the leak); SYRE+MRAM+OMCL+JBL =
  −10.3R (54%). Strip the top-3 winners (BW/CRSR/RCAT +5.5R) and the rest is −24.6R/28.
- **Entry-fill slippage is NOT the story:** mean +0.09% / median +0.19% above the ORB-high
  trigger ≈ −0.03..−0.06R per trade. The "entry" problem is the design (chasing the ORB
  high of an already-gapped name), which is bucket 2 — not bad fills at the trigger.
- **Score >100 rows (MRAM 115, DELL 115, CSCO/MNDY/RCAT/CRSR 101…) are the pre-rubric-era
  scale** — score-band cuts mix eras; read directionally only.

## 2. The waterfall — from raw stock edge to −19.1R

| Step | Value | Meaning |
|---|---|---|
| Raw material | filled-name fwd_5d **avg +8.5%** (n=67 recon HIGH fills) | The detector finds stocks that go up — the Q4-parity result replicated inside this cohort |
| Idealized geometry, full universe | recon n=72 fills: **+0.02R mean**, win 29%, median −1R, top-3 = 449% of total | The ORB-high-chase / 1-min-ORB-low-stop bracket alone consumes essentially ALL of the raw edge; what survives is a lottery on ~3/72 tail winners |
| Idealized geometry, the 28 that live entered-and-closed | **−6.3R (−0.22R mean)** | The entered subset held NO tail winner ≥ +2R beyond the two the live book caught; also mildly adverse vs the full universe (see funnel note below) |
| Live actual on the same 28 | **−17.7R** → **delta −11.3R (−0.40R/trade, SE 0.18)** | What the live exit engine + fills cost vs SETTLE_RULE exits |
| Unpaired 3 (TSEM, MANE too recent; BSX pre-cohort) | **−1.4R** | Completes −19.1R |

**Funnel side-note (context, owned by #446):** the 44 recon-fills the live book did NOT
close net out ≈ +5.7R recon. Composition is telling: safeguard/ops skips accidentally SAVED
R (`account_fetch_failed` n=10 → recon −2.9R; `max_positions` n=8 → −2.1R) while cancels +
`stop_too_wide` + zero-range MISSED recon winners (+11.7R across ~16 rows, e.g. FLEX, INFQ,
MLTX, EVER +2.0R each). Net ≈ −0.24R/trade of adverse selection into what actually entered —
real but second-order, and already the #446/#290 lane.

### Delta decomposition (the −11.3R live-vs-recon gap, mutually overlapping lenses made exact in `_468b_high_diagnosis.py`)

| Mechanism | R | Trades |
|---|---|---|
| Winner giveback (recon settled >0, live kept less) | **−5.9R** | KURA −1.98 (recon +2.0 → live +0.02), FTRE −1.86, QURE −1.05, RCAT −0.70, CRSR −0.31 |
| No-early-harvest residual (recon banked the +1R half day-0/1, live had NO partial before day 3 and rode to the stop) | **≈ −3.1R** | AMD −0.84, CRCL −0.81, TEAM −0.28, NRIX/MRAM components |
| Beyond-stop fills (loss past −1R) | **−6.6R paired** (−6.7R with TSEM) | SYRE −4.0, MRAM −1.2 (suspect, §4), OMCL −0.5, JBL −0.5, five others −0.4 combined |
| Partial-fill accounting credit (losers read < 1R of INTENDED risk) | **+4.3R** | DELL +0.71, CSCO +0.58, INTC +0.52, DY +0.47… — see §3: this is NOT loss-cutting skill |

## 3. The partial-fill distortion (read before trusting any per-trade R)

The entry is a stop-LIMIT (limit = max(hi×1.005, hi+$0.02)). Fast tape blows through the
limit → partial fill; `risk_dollars` records INTENDED risk. For a day-0 loser stopped AT the
ORB-low, implied fill fraction = −R. The sub-−1R "small" losers are mostly **FULL stops on
partial positions**: DELL 29% filled, CSCO 42%, INTC 48%, DY 53% (DY: 40 of ~75 intended
shares × $10.96/share risk = the −$438 observed, exit exactly at the 535.5 stop). Fractions
>100% (RUM 107, NAVN 110, NRIX 120, JBL 150, OMCL 152, TSEM 105, MNDY 103) are slip past
the stop — the −1.5R "fast-tape slip" line in §2 (ex-SYRE/MRAM).

Two consequences:
1. The **+4.3R "live beat recon on losers" is largely an accounting artifact**, not exit
   skill — the position was smaller than the R denominator assumes.
2. **Negative convexity at entry:** the hardest-running names (the would-be winners) fill
   LEAST through the limit (or not at all — the 36 cancelled rows, the #446 36.7%-winner
   lane), while grinders fill fully and then stop out. The stop-limit buffer creates
   adverse selection ON TOP of the chase geometry. This sub-mechanism is NEW (not in #306,
   #414, or #446 — #446 sees its no-fill edge, not its partial-fill half).

## 4. Forensics on the anomalous rows

- **SYRE −5.02R (the single largest leak item).** Filled 6/22 9:52 @98.49, stop 95. 6/23
  high 102.06 (recon banked its +1R half there — live had no day-1 partial). 6/24 **opened
  83.22, −12.4% BELOW the stop**; stop-market filled ≈ 81 (first-minutes range low 81.65).
  The stock then recovered to ~88-91 by 6/26 (fwd_5d +1.7%). This is **#450 F1 realized**
  (overnight gap through a resting stop) + the #306 no-early-harvest hole (a +1R-open profit
  existed on day 1 and nothing banked it). Even idealized exits lost −1.85R here.
- **MRAM −2.23R — suspected PHANTOM ≈ −1.1R.** Filled 5/11 9:50 @36.50 (the literal day-high
  print, 36.4999); stop 34.07; closed 9:59:15. The −2.23R implies exit ≈ $31.09 — **the tape
  never traded below 33.66 in that window** (9:59 bar low 33.79). −$2,199.7 is almost exactly
  2 × (−$1,100 = a stop fill at ~33.80, the actual 9:59 low). Hypothesis: **duplicate
  stop_hit legs in `exits` jsonb** summed by `total_pnl_so_far = sum(ex.pnl)` (the
  order_manager stop-out path) — the WS handler + a reconcile both recording one fill.
  True loss ≈ −1.11R. Verify with §8-Q2 before this row is ever used in calibration.
- **MNDY −1.03R with EMPTY `filled_at`,** closed at exactly 10:00:00 — a fill whose event
  was missed (pre-#123 silent-stop class); loss itself looks real.
- **CRMD −0.81R with entry 8.36 BELOW the 8.45 stop** — the known 5/14 emergency-close
  incident (`scripts/probes/_emergency_close_crmd.py`); ops event, not strategy signal.
- **KURA +0.02R / FTRE +0.14R** — recon +2.0R each. FTRE ran +11.5% in 5 days; live exited
  ~flat after 7 days. The purest #306 shape in the cohort (trail-less early days, late ⅓
  partial, breakeven-after-partial round-trip).

## 5. Cross-reference — already known, or new?

| Prior work | Relationship to this leak |
|---|---|
| **#306 exit-management leak** (STEP-0: 18% MFE capture; W3 design 7/18: peak-lock +$8,075 sweep-attributed) | **SAME LEAK, now corroborated in realized-R:** −5.9R giveback + ≈−3.1R no-early-harvest ≈ −9R gross of this cohort's delta. #306's mechanism list (no trail days 1-9, nothing reads the peak, partial late/small/blocked) explains every giveback row incl. SYRE's un-banked day-1 profit. This diagnosis ADDS: the leak is not only winner-giveback — the missing day-0/1 harvest also turns recon-scratches into full stops. |
| **#450 premortem F1** (correlated/overnight gap risk; "safeguards strongest at entry, weakest while held") | SYRE = the realized single-name instance: −4.0R of the −19.1R is one overnight gap through a resting stop. |
| **#446 cancelled-unfilled diagnosis** | Adjacent, not this cohort: our funnel note (+11.7R recon missed to cancels/too-wide) is its lane. The **partial-fill negative convexity (§3) is the new bridge** between the two docs — same stop-limit mechanism, fill side. |
| **B6 / #468 / meta-rubric #328-331** ("the lever is score composition, not thresholds") | Selection gradient here points the SAME direction (higher score / `strong` catalyst / engine-authored = less bad) but every cell is still negative and cells are n=4-13 — selection tuning cannot fix a geometry+management leak of this size. |
| **#450-premortem R3 calibration / #454 regime envelope** | The #268b envelope (+0.95R mean, 30% win) is Bull-conditional AND SETTLE-idealized; live actual −0.62R sits ~1.6R/trade below it. This doc's waterfall says: ≈0.6R of that gap is geometry-subset+idealization, ≈0.4R is execution/management — the envelope was never a live-exit-engine promise. Regime stratification of the 31 needs §8-Q1 (expect degenerate: ~94% Bull window). |
| **R3 same-day re-entry ban (5/17)** | Orthogonal: it labels 13 of the day-0 stops but caused none of them. |

## 6. How much to trust n=31 (pre-committed honesty)

- **The typical trade is robustly bad:** 25/31 losers; against a 50% null p≈0.0004. BUT the
  right null is the geometry's own expected win rate (recon: 29%): observed 19% gives
  binomial p≈0.16 — **the live win RATE is statistically consistent with the bracket
  geometry working as designed.** What n=31 cannot tell you is the tail: recon's entire
  edge is 449%-concentrated in its top-3 of 72; a 31-trade live sample missing one or two
  +2R-to-+3R tails swings the mean by +0.3-0.5R. So "mean −0.62R" ≠ proof the strategy's
  true mean is −0.62R.
- **The delta (execution+management) −0.40R/trade, SE 0.18** (paired n=28, t≈−2.2) — real
  but tail-sensitive: excluding SYRE (a genuine but singular gap event) and MRAM (suspect
  accounting) it is −0.23R/trade over 26. Read: the management leak is present and material;
  its precise per-trade magnitude is soft.
- **The mechanism accounting (§1-§4) is exact, not statistical** — which trades, which
  exits, which fills. That part does not need more N.
- **Selection/regime cells (score bands, catalyst, month) are n=4-13 — directional only.**
  Do NOT re-tune any filter from this table (the parabolic 5/08 lesson).

## 7. Recommendation (DESIGN ONLY — every item is operator + CHANGE_PROCESS + backtest)

Ranked by R attributed on THIS cohort:

1. **Ship-path priority = the #306 W3 peak-lock / early-harvest package** (already designed,
   sweep-validated +$8,075 on the 28-trade replay; targets the ≈ −9R gross management
   bucket, incl. SYRE's un-banked day-1 +1R). This diagnosis is the realized-R
   corroboration that #306's backtest asked for. **No new design work needed — it needs its
   operator gate.**
2. **The NEW operator fork — the bracket geometry itself:** even with idealized exits, the
   ORB-high-chase/1-min-ORB-low-stop bracket monetizes a +8.5%-in-5-days cohort at ≈ +0.02R
   mean (win 29%, tail-dependent). Perfect management fixes ≈ half the leak; the other half
   is structural. The fork to surface (NOT pre-decide): keep the bracket and accept
   lottery-shaped P&L (needs the #306 fix + patience for tails), vs commission a backtest of
   an alternative entry/stop placement (e.g. pullback-entry or wider structural stop — pure
   CHANGE_PROCESS + N≥10 territory). Cheap first evidence: the existing 5-min shadow ORB
   lane (#94) already accrues alternative-geometry data without touching money.
3. **Data-hygiene before ANY recalibration** (no strategy content): §8-Q2 the exits-jsonb
   audit — if MRAM's double-count confirms, the true book is ≈ −18.0R not −19.1R and any
   future envelope/calibration join must exclude phantom legs. Same query verifies MNDY's
   missing fill event and CRMD's emergency-close labeling.
4. **Overnight-gap exposure (SYRE class):** already #450 F1 / #452 lane
   (`exposure_family_cap_promotion` review 7/27); this cohort adds one realized −4R data
   point to that operator decision. Nothing new to design here.
5. **Do NOT touch selection thresholds off this table** (§6) — the gradient agrees with the
   meta-rubric direction and that thread (#328-331) owns it.

## 8. Prod SELECTs for the orchestrator (read-only; this session had no prod path)

**Q1 — regime join for the 31 closed (finishes §5's regime row):**
```sql
SELECT t.ticker, t.alert_date, r.regime,
       ROUND((t.total_pnl / t.risk_dollars)::numeric, 2) AS r_mult
FROM mi_live_trades t
JOIN mi_market_regime r ON r.regime_date = t.alert_date
WHERE t.signal_type = 'magna53' AND t.status = 'closed' AND t.risk_dollars > 0
ORDER BY t.alert_date, t.ticker;
```

**Q2 — exit-leg audit for the anomalous rows (MRAM double-count hypothesis, MNDY missing
fill, CRMD emergency close, SYRE gap fill):**
```sql
SELECT t.ticker, t.alert_date, t.entry_price, t.stop_price, t.risk_dollars, t.total_pnl,
       jsonb_pretty(t.exits::jsonb) AS exits
FROM mi_live_trades t
WHERE t.signal_type = 'magna53' AND t.status = 'closed'
  AND t.ticker IN ('SYRE','MRAM','OMCL','MNDY','CRMD','JBL','NRIX','DY','CSCO')
ORDER BY t.alert_date;
```

**Q3 — MFE capture on the giveback five + round-trippers (quantifies §2's giveback bucket
against #306's 18% capture number on THIS cohort):**
```sql
SELECT t.ticker, t.alert_date, t.entry_price, t.highest_price_seen,
       t.total_pnl, t.risk_dollars
FROM mi_live_trades t
WHERE t.signal_type = 'magna53' AND t.status = 'closed'
  AND t.ticker IN ('KURA','FTRE','QURE','RCAT','CRSR','BW','AMD','SMCI','TEAM','SYRE')
ORDER BY t.alert_date;
```
*(If `highest_price_seen` is not a `mi_live_trades` column, it lives wherever the #91
time-stop excursion read gets it — adjust the column, keep the intent.)*

**Q4 — entry-fill fractions, direct (replaces §3's inference with ground truth):**
```sql
SELECT t.ticker, t.alert_date, t.risk_dollars, t.entry_price, t.orb_low,
       ROUND((t.risk_dollars / NULLIF(t.entry_price - t.orb_low, 0))::numeric, 0)
         AS intended_shares,
       t.exits::jsonb -> 0 ->> 'shares' AS first_exit_shares
FROM mi_live_trades t
WHERE t.signal_type = 'magna53' AND t.status = 'closed'
ORDER BY t.alert_date;
```

---

*Written 2026-07-18 under THE LINE: read-only, no strategy/entry/exit/stop/selection change,
not committed. Generator: `scripts/probes/_468b_high_diagnosis.py`.*
