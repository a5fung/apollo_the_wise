# Why live trades die on day one — 2026-08-06

> ⚠ **THIS DOC'S HEADLINE FINDING (§D) IS REFUTED BY ITS OWN §E. Read §E before acting on §A–§D.**
> §D concluded a volatility floor on the stop rescues the four biggest movers. The forward replay
> shows that survival was DELAY, not rescue: every one of those four hits the wider stop within
> 1–6 sessions, and the §D candidate k=0.75 finishes WORSE (−9.00R) than changing nothing
> (−7.33R). §A–§D are left standing as written rather than edited, so the reasoning that led to a
> wrong conclusion stays visible.
> 
> ⚠ **Two factual corrections to §A–§D, found while reconciling §E:**
> 1. **10 of 14 closed on the alert date, not 13.** I counted `hold_days = 0` (13 rows) as
>    same-day. It is not: MANE, NVCR and QBTS all carry `hold_days = 0` while closing the NEXT
>    calendar day. Verified independently against `closed_at::date > alert_date` (4 trades:
>    MANE 07-15→07-16, SMCI 07-22→07-27, NVCR 07-23→07-24, QBTS 07-27→07-28).
> 2. §B's "day-1 R" column is the day-1 **HIGH**, not the close.
> 
> Basis note: the −11.5R headline used elsewhere is pnl ÷ *planned* `risk_dollars`. On the
> replay's realized entry−stop unit the same cohort is **−13.15R**. §E compares like-for-like.

Read-only, $0. Source: prod `mi_live_trades` (14 closed live trades, cutover → 2026-08-06) joined
to `mi_daily_closes`. No change proposed, none made — stop placement is entry discipline and
belongs to the operator (THE LINE).

## The question

The live cohort is 0-for-14, average −0.82R, and **13 of the 14 closed the same day they were
entered**. Two explanations lead to opposite fixes:

* **Stop problem** — the entries found real movers and the stop amputated them.
* **Selection problem** — the stops saved us and the entries were bad.

Discriminating test: measure each stop against the stock's *own* normal daily range, then look at
what the stock did after it stopped us out.

⚠ **Operator correction, 2026-08-06, and it reframes the counterfactual:** the +2R partial exit
only went live 2026-08-05 (PLTR was its first fire). **All 14 of these ran without it.** So the
relevant counterfactual is NOT "would holding have worked" but "would the rule we now have banked
something before the stop hit" — which is the third table below.

## A. The stop, measured against the stock's own daily range

`stop as fraction of range` = (entry − stop) ÷ entry, divided by the stock's mean 20-day
high-low range as a % of close. Below 1.0 means the stop sits inside a normal day's noise.

| ticker | date | stop % of price | normal daily range % | stop ÷ range |
|---|---|---|---|---|
| MANE | 07-15 | 1.11 | 7.25 | **0.15** |
| HUT  | 07-20 | 1.96 | 9.91 | **0.20** |
| CRCL | 07-10 | 1.92 | 7.19 | **0.27** |
| BTDR | 08-04 | 2.88 | 10.10 | **0.29** |
| QBTS | 07-27 | 2.31 | 6.55 | **0.35** |
| WULF | 07-06 | 3.33 | 8.49 | **0.39** |
| TSEM | 07-14 | 2.80 | 6.91 | **0.41** |
| SMCI | 07-22 | 3.29 | 6.30 | **0.52** |
| BLZE | 08-04 | 7.85 | 8.99 | 0.87 |
| FTNT | 07-30 | 3.88 | 4.19 | 0.93 |
| THC  | 07-24 | 3.35 | 3.54 | 0.95 |
| WKC  | 07-24 | 2.89 | 2.58 | 1.12 |
| WDFC | 07-10 | 3.10 | 2.78 | 1.12 |
| NVCR | 07-23 | 6.01 | 5.11 | 1.18 |

**Eight of fourteen carried a stop under 0.55× the stock's normal daily range.** MANE's stop was
1.11% on a stock that routinely travels 7.25% in a day — one-seventh of an ordinary session.
Getting stopped there is close to arithmetically guaranteed, independent of whether the trade
was right.

✅ **Independent cross-check:** the #306 intraday-partial analysis (2026-07-25) measured this on a
different cohort and reported the range as **0.15×–1.19× of ADR20**. This cohort spans
**0.15×–1.18×**. Two separate analyses, same spread — the ORB low is one morning's bar, not the
stock's personality, and its relationship to the stock's volatility is essentially random.

## B. What the stock did after it stopped us out

R measured against each trade's own risk unit (entry − stop).

| ticker | day-0 R available | day-1 R | best over next 5 sessions |
|---|---|---|---|
| MANE | **+7.92** | +4.41 | +4.41 |
| QBTS | **+3.26** | +1.71 | **+8.88** |
| SMCI | **+2.90** | +3.21 | +3.21 |
| HUT  | +1.73 | +3.44 | **+8.32** |
| CRCL | +1.62 | −3.35 | −2.80 |
| BLZE | +1.27 | −1.18 | −1.18 |
| NVCR | +1.22 | +2.00 | +2.00 |
| WKC  | +0.90 | −0.22 | +0.59 |
| WULF | +0.65 | −3.33 | −0.05 |
| THC  | +0.64 | +0.88 | +2.60 |
| FTNT | +0.40 | −0.63 | +0.84 |
| WDFC | +0.29 | −3.14 | −3.14 |
| BTDR | +0.22 | −1.62 | −1.62 |
| TSEM | 0.00 | −0.41 | −0.41 |

**The two tables line up.** Every large move we were stopped out of sits in the tight-stop half:
MANE (+7.9R), QBTS (+8.9R), HUT (+8.3R), SMCI (+3.2R) — all four had stops at 0.15–0.52× the
stock's range. The six trades with sane stops (≥0.85×) produced nothing bigger than THC's +2.60R
and NVCR's +2.00R, and four of them simply kept falling.

**Verdict: it is a stop problem on the tight half, and a genuine no-trade on most of the wide
half.** Selection is finding real movers. The ORB-low stop is amputating them precisely when the
opening minute happened to be narrow.

## C. What the +2R partial (live since 08-05) would have changed

Trades reaching +2R on the entry day — the trigger the rule now watches:

| ticker | day-0 R available | actual result | with 1/3 out at +2R, stop to breakeven |
|---|---|---|---|
| MANE | +7.92 | −0.11R | ≈ **+0.67R** |
| QBTS | +3.26 | −0.92R | ≈ **+0.67R** |
| SMCI | +2.90 | −0.68R | ≈ **+0.67R** |

**3 of 14 (21%) would have triggered it**, converting three losses into three small gains — about
a +2.3R swing on a cohort that lost 11.5R. Real, and the rule is doing what it was built to do.

⚠ **But it does not reach the big misses.** HUT (+8.32R) and QBTS (+8.88R) made most of their move
on days 1–5, and both were stopped out on day 0 before any of it. A partial at +2R banks a third
and protects the rest at breakeven; it cannot help a trade that never survives to day 1. **The 2R
rule improves outcomes; the day-0 stop-out rate is what caps them.**

## Caveats, stated rather than buried

* `day-0 R available` uses the session high, which includes any move before the 9:31 entry. For an
  ORB-high breakout the entry sits at roughly the first minute's high, so nearly all of it is
  post-entry — but it is an upper bound, not a fill.
* You cannot sell at the exact high. These are ceilings on what was reachable, not achievable P&L.
* n=14, split 8/6 on stop tightness. Directionally strong, and it reproduces an independent
  earlier measurement, but it is not a large sample.
* Two names (WULF, BTDR) had tight stops *and* went straight down — a tight stop is not always
  wrong, and this does not say every stop should be widened.

## D. Would a volatility floor on the stop have saved them?

Replay: `stop = max(ORB low, entry − k × ADR20)`. The floor only binds on the tight half; where
the ORB low is already wider than k×ADR nothing changes. "Survives" = the entry day's LOW never
reached the floored stop, so there is no event-ordering ambiguity — it either got hit that day or
it did not.

| floor k | trades surviving day 0 (of 14) |
|---|---|
| 0.30 | 1 |
| **0.50** | **3** |
| **0.75** | **4** |
| 1.00 | 4 |

**Which four survive at k=0.75 is the whole finding:**

| ticker | stop ÷ range | day-0 R | best over 5 sessions |
|---|---|---|---|
| MANE | 0.15 | +7.92 | +4.41 |
| HUT  | 0.20 | +1.73 | **+8.32** |
| QBTS | 0.35 | +3.26 | **+8.88** |
| SMCI | 0.52 | +2.90 | +3.21 |

**The four trades a floored stop rescues are exactly the four with the largest forward moves.**
Not a subset, not a majority — the same four, ranked the same way.

The four tight-stop names it does NOT rescue (CRCL, BTDR, WULF, TSEM) get stopped even at k=1.00,
and all four were genuinely going down (−2.80R, −1.62R, −0.05R, −0.41R over five sessions). The
floor does not save bad trades, which is the correct behaviour.

**The cost is close to zero in R terms.** Sizing is risk-based (`risk_dollars ÷ stop distance =
shares`), so a wider stop buys fewer shares for the same dollars at risk. A trade that still fails
still loses ≈1R — the same money, just at a wider stop with a smaller position.

⚠ **What this does NOT establish, and it is the gap before any change:** surviving day 0 is not
the same as finishing profitably. These trades would then be open into day 1+ carrying the wider
stop, and this replay does not follow them there. HUT's +8.32R and QBTS's +8.88R arrived over five
sessions; whether either would have held the floored stop through day 2 is unmeasured.

## Path forward

1. ✅ **Done (this doc, $0):** the axis is stop WIDTH, not selection, and k≈0.75 × ADR is the
   candidate floor.
2. **Next, $0:** carry the four survivors forward past day 0 with the floored stop *and* the now-live
   +2R partial and breakeven arm, to a realized R. That is the number that decides it. Note MANE,
   QBTS and SMCI all cleared +2R on day 0 and would bank the partial; HUT reached only +1.73R on
   day 0 and would not.
3. **Operator's, then:** CHANGE_PROCESS — read `docs/setups/magna53_ep.md` in full, backtest at
   N≥10 (14 live + the paper cohort qualify), sign-off, SSoT updated in the same commit. No live
   flip before that.

⛔ **What NOT to do: add a "stop too tight" filter.** The system already refuses trades whose stop
is too WIDE (`setup:stop_too_wide` — AEVA was skipped by it on 2026-08-06 at 13.4% > 1.5× ATR).
The absent mirror-image guard looks like the obvious symmetric fix, and the data says it would be
a mistake: skipping tight-stop setups would have deleted MANE, HUT, QBTS and SMCI — the four best
opportunities in the cohort. The problem is the stop, not the setup. Widen, do not skip.

## What this does not do

It proposes no change to stop placement, sizing, or entry criteria. Any of those is
CHANGE_PROCESS + operator sign-off. The purpose here was only to settle which of the two
explanations the data supports, because the two lead to opposite fixes.

## E. Forward replay — realized R, not survival

Replay: `scripts/probes/_stop_floor_forward_replay.py` (read-only; prod trade/daily snapshots +
Polygon minute bars captured once to TSVs beside it; full output in
`_stop_floor_replay_output.txt`). Minute bars, pessimistic within-bar ordering (low before high).
Exit model = exactly three mechanisms: hard stop at `stop_k = MIN(orb-low stop, entry −
k×ADR20)` filling at the stop (slippage ignored); the +2R partial (1/3 out at `entry + 2×(entry −
stop_k)`, remainder to breakeven) — live since 08-05, so NONE of these 14 had it; remainder out
at its stop or the close of the 10th session after entry. **Deliberately NOT modeled** (they
exist live; they would confound the floor): the time-stop, the 15:45 partial window, the
giveback peak-lock, the daily SMA-trail / stop-ladder management step, re-entries, slippage.

### E1. The k=0 reconciliation — the replay reproduces reality

⚠ Two "R" bases exist: the −11.5R headline divides by the PLANNED `risk_dollars`; the replay's
unit is the realized `entry − stop`. On the realized basis the actual cohort is **−13.15R**, and
the comparison below is on that basis (apples-to-apples).

| ticker | actual R | sim R (k=0, stop only) | close session act/sim | note |
|---|---|---|---|---|
| WULF | −1.00 | −1.00 | 0 / 0 | exact |
| CRCL | −1.01 | −1.00 | 0 / 0 | slippage 1c |
| WDFC | −1.04 | −1.00 | 0 / 0 | slippage |
| TSEM | −1.00 | −1.00 | 0 / 0 | exact |
| MANE | **−0.23** | −1.00 | 1 / 1 | **stop was RAISED live** (exit 119.04 vs initial stop 118.02) |
| HUT | −1.07 | −1.00 | 0 / 0 | slippage |
| SMCI | **−0.70** | −1.00 | 3 / 3 | **stop was RAISED live** (exit 28.79 vs initial stop 28.50) |
| NVCR | −1.00 | −1.00 | 1 / 1 | exact |
| THC | −1.01 | −1.00 | 0 / 0 | slippage |
| WKC | −1.03 | −1.00 | 0 / 0 | slippage |
| QBTS | −1.00 | −1.00 | 1 / 1 | exact |
| FTNT | −1.03 | −1.00 | 0 / 0 | slippage |
| BLZE | −1.02 | −1.00 | 0 / 0 | slippage |
| BTDR | −1.03 | −1.00 | 0 / 0 | slippage |

* **Verdict: RECONCILED.** The 12 trades that actually exited at their initial stop replay to
  within 0.07R each, on the right session, and every simulated stop-hit is corroborated by the
  official daily low (no minute-only phantom prints). ADR20 ratios reproduce §A's column
  (worst deviation 0.03, a windowing difference on SMCI).
* The 2 divergences are the excluded live mechanism, named: MANE's and SMCI's stops were raised
  above the ORB low by the daily management engine before being hit — the exit prices prove it.
  The model is more pessimistic than reality on far-runners; every k column carries that equally.
* **Two corrections to this doc while reconciling:** (1) the intro's "13 of 14 closed the same
  day" is wrong — it is **10 of 14** (MANE, NVCR, QBTS closed on day 1, SMCI on day 3);
  (2) §B's "day-1 R" column is the day-1 **high**, not the close — MANE's "+4.41R day 1" was a
  morning touch inside a crash to −11R by that day's close (official 07-16: high 125.17, close
  105.83).

### E2. Per-trade realized R (the deployed ruleset: +2R partial ON)

P@ = session the partial fired (entry day = 0), cls = session the trade closed, `*` = the floor
actually widened the stop.

| ticker | stop÷range | k=0 | k=0.5 | k=0.75 | k=1.0 |
|---|---|---|---|---|---|
| WULF | 0.39 | −1.00 (cls 0) | −1.00 (cls 0)* | −1.00 (cls 0)* | −1.00 (cls 0)* |
| CRCL | 0.27 | −1.00 (cls 0) | −1.00 (cls 0)* | −1.00 (cls 0)* | −1.00 (cls 0)* |
| WDFC | 1.12 | −1.00 (cls 0) | −1.00 | −1.00 | −1.00 |
| TSEM | 0.41 | −1.00 (cls 0) | −1.00 (cls 0)* | −1.00 (cls 0)* | −1.00 (cls 0)* |
| MANE | 0.15 | **+0.67** (P@0, cls 1) | **+0.67** (P@0, cls 1)* | **−1.00** (cls 1)* | −1.00 (cls 1)* |
| HUT | 0.20 | −1.00 (cls 0) | **+0.67** (P@2, cls 5)* | **+0.67** (P@3, cls 5)* | **−1.00** (cls 6)* |
| SMCI | 0.55 | **+0.67** (P@0, cls 2) | +0.67 | +0.67 (P@0, cls 2)* | **−1.00** (cls 4)* |
| NVCR | 1.19 | **+0.67** (P@1, cls 1) | +0.67 | +0.67 | +0.67 |
| THC | 0.95 | −1.00 (cls 0) | −1.00 | −1.00 | −1.00* |
| WKC | 1.11 | −1.00 (cls 0) | −1.00 | −1.00 | −1.00 |
| QBTS | 0.35 | **+0.67** (P@0, cls 1) | **+0.67** (P@0, cls 1)* | **−1.00** (cls 1)* | −1.00 (cls 2)* |
| FTNT | 0.91 | −1.00 (cls 0) | −1.00 | −1.00 | −1.00* |
| BLZE | 0.86 | −1.00 (cls 0) | −1.00 | −1.00 | −1.00* |
| BTDR | 0.29 | −1.00 (cls 0) | −1.00* | −1.00* | −1.00* |

### E3. Cohort totals

Dollars at the trades' planned risk budgets (avg $25/trade); actual cohort dollars −$289.

| | k=0 | k=0.5 | k=0.75 | k=1.0 |
|---|---|---|---|---|
| **floor + partial: total R** | **−7.33** | **−5.67** | **−9.00** | **−12.33** |
| ≈ dollars | −$200 | −$166 | −$245 | −$314 |
| winners | 4/14 | 5/14 | 3/14 | 1/14 |
| still closing on day 0 | 10 | 9 | 9 | 9 |
| floor changed the stop | 0 | 7 | 8 | 11 |
| partial fired | 4 | 5 | 3 | 1 |
| **floor ALONE (partial off)** | **−14.00** | **−14.00** | **−14.00** | **−14.00** |

(Baselines, same model basis: actual = −13.15R; stop-only replay = −14.00R. Gap-aware stop fills
move totals ≤0.2R; no trade left unsettled — all resolved within the data window.)

### E4. The honest read

* **The floor does not turn the cohort positive at any k. It does not even reliably make it
  less negative.** The §D candidate k=0.75 (−9.00R) is WORSE than no floor at all with the
  already-live partial (k=0, −7.33R). k=1.0 is worse than doing nothing whatsoever.
* **The floor alone rescues nothing: −14.00R at every k, zero winners.** Every §D "survivor"
  that dodges the day-0 stop hits its wider stop within 1–6 sessions anyway. Survival = delay.
* **Why §D's survival story dies going forward: all four big movers gave everything back.**
  MANE crashed from +7.9R (old units) to −12.5% below entry by day-1 close; QBTS traded below
  entry−1×ADR on day 1 and below entry−1.7×ADR on day 2 BEFORE its later +8.9R rip; HUT fell to
  entry−1.7×ADR by day 9 (twice round-tripping a +16% move); SMCI bled to entry−1.3×ADR by day 4.
  §B's "R available" columns were peaks, and NO stop-width policy in this family harvests a
  peak — at every k the trade either stops on the retrace or the widened R-unit pushes the +2R
  target above the actual high (MANE and QBTS at k=0.75 lose their partial for exactly that
  reason: the same price move is worth fewer of the bigger R-units).
* **What actually moves the number is the +2R partial, which is ALREADY LIVE**: −13.15R actual →
  −7.33R (+5.8R) with no floor at all, via four trades banking 1/3 at +2R and scratching the
  rest — more than §C credited (it found only the 3 day-0 reaches; NVCR's day-1 gap-kiss also
  fires). Every winner in every column is a +0.67R partial-bank; there is not a single
  ride-to-strength winner anywhere in the sweep.
* **The one real floor benefit is a single trade**: HUT at k=0.5 (floor survives the day-0 noise
  low of 99.10 vs the 101.45 ORB stop, partial banks on day 2) = the entire +1.67R edge of
  k=0.5 over k=0. One trade, n=14. That is not evidence to change stop placement; it is
  evidence the partial needs survivors to work on.

### E5. Sensitivity — how thin is this?

* **Remove the best trade per column** and every total drops ~1.67R (k=0.5 → −7.33R); the
  RANKING of k values does not change, and nothing approaches positive.
* **k=0.5's edge over k=0 = HUT alone.** Remove HUT and they tie. A one-trade edge is noise.
* **NVCR's +0.67R (in every column) rests on a half-cent**: the +2R target 21.45 vs an official
  day-1 high of 21.4506. If that limit doesn't fill, every column drops 1.67R equally.
* **QBTS's k=0.75 stop is a 0.4-cent call** (floor 17.264 vs day-1 low 17.26) — but day 2's
  16.07 low seals the same outcome regardless, so nothing hinges on it.
* Model optimism, stated: stop fills ignore slippage (actuals slipped ~0.02R/trade against us);
  MANE/SMCI-style live stop-raises are not modeled and would only make floored columns worse.

### E6. Data quality

* No trade had missing bars; no trade was dropped; none left unsettled inside the 10-session
  horizon. Every simulated stop-hit session is corroborated by the official `mi_daily_closes`
  low for that session (the thin-name stray-print risk was checked, not assumed away).
* Fill-bar convention: on the fill minute a stop-out requires the bar to CLOSE at/below the
  stop — the bar's low can predate the fill second (MANE's live 118.02 stop sat through day 0
  untriggered while the 9:33 bar's low printed at/below it; HUT's real 51-second death is still
  caught).

**Bottom line: §D's day-0 finding was true but does not survive contact with day 1+. The four
rescued trades do not finish profitably — at best they bank the same +0.67R partial three of
them already earn without any floor, and two of the four lose even that when the floor widens
the R-unit. The realized-R case for a volatility floor on this cohort is negative at the §D
candidate (k=0.75) and at k=1.0, and worth +1.67R from one trade at k=0.5. The +2R partial —
already deployed — is what converts this cohort from −13.2R to −7.3R. No change proposed;
operator's call (THE LINE).**
