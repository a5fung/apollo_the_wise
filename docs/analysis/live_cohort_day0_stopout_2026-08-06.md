# Why 13 of 14 live trades died on day one — 2026-08-06

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
