# #490 — do the delay-missed candidates pass as tradable EPs?

**Operator question, 2026-08-01:** *"I want to know if they actually pass as tradable EPs, fitting all
criteria, is it easy to analyze this?"*

**Short answer: for 3 of 32 the system already answered YES, in its own records — no modelling
involved. For the other 29 the question is open and only ~75% cheaply answerable.**

---

## 1. The three that ARE proven — our own pipeline scored and then refused them

These were not "would they have passed." They went through the **full** EP pipeline — quantitative
score, catalyst grading, judge — and cleared every gate:

| ticker | date | ep_score | tier | catalyst | judge | detected |
|---|---|---|---|---|---|---|
| BLZE | 2026-07-31 | 72 | HIGH | game_changer | HIGH | 09:55 ET |
| HAS | 2026-07-21 | 72 | HIGH | game_changer | HIGH | 09:50 ET |
| NNE | 2026-07-27 | 57 | HIGH | strong | HIGH | 09:55 ET |

**And `mi_live_trades` carries the refusal, in live mode:**

```
BLZE 2026-07-31  status=skipped  skip=window:out_of_orb: detected 09:56 ET  mode=live
HAS  2026-07-21  status=skipped  skip=window:out_of_orb: detected 09:50 ET  mode=live
NNE  2026-07-27  status=skipped  skip=window:out_of_orb: detected 09:56 ET  mode=live
```

The ORB submission window is `now_et.hour == 9 and now_et.minute < 45` (`CLAUDE.md`, MAGNA53 section).
All three landed 5-11 minutes past it. **The only thing that disqualified them was arrival time.**

Their outcomes, from that day's open:

| | open→close | open→high | open→low |
|---|---|---|---|
| HAS | +5.1% | +10.1% | −0.7% |
| BLZE | +1.9% | +9.2% | −0.5% |
| NNE | +1.1% | +5.4% | −2.2% |

All three green, all three with a shallow low — the profile our live book has none of.

## 2. Would the flip actually RECOVER them? Yes — measured, with margin

Proving the loss is not the decision. The decision is whether real-time detection gets them back.
Two numbers settle it.

**(a) The real-time layer saw all three, 15-20 minutes before the scan did.** `tick_et` from the
`ep_rt_live_miss` audit payload, against the scan's own `detected_at`:

| ticker | RT tick | scan detected | RT lead |
|---|---|---|---|
| HAS | 09:35 | 09:50 | **15 min** |
| BLZE | 09:35 | 09:55 | **20 min** |
| NNE | 09:40 | 09:55 | **15 min** |

Across all 32 delay-missed events the RT tick is **only ever 09:31, 09:35 or 09:40** (10 / 9 / 13).
Never later.

**(b) Grading fits in the remaining window, with room to spare.** `detected_at` is bound once at the
top of `run_ep_scan` (`ep_detector.py:2309`) — it is the scan tick's START. So `created_at −
detected_at` is the **full** end-to-end path: candidate detection, Claude catalyst grade, Perplexity,
row write. Measured over 30 days:

| | n | median | p90 | p99 | max |
|---|---|---|---|---|---|
| all alerts | 41 | 27s | 57s | 143s | **150s** |
| HIGH only | 36 | 29s | 65s | — | 150s |

The three proven names: HAS **35s**, BLZE **31s**, NNE **87s**.

**Worst case arithmetic: latest RT tick (09:40) + slowest observed grading (150s) = 09:42:30 —
inside the 09:45 ORB cutoff.** Every one of the 32 clears it, not just the median case.

▶ **The flip recovers these. This is not a modelling assumption — both legs are measured.**

⚠ **One residual risk, stated plainly:** the 150s ceiling was measured on the DELAYED scan's
candidate load. Real-time detection produces a larger candidate set (621 RT events in 7 days), and
grading cost scales with candidates, so per-tick wall clock could rise. That is the thing to watch on
rollout — not a reason to withhold the flip, but it is the failure mode if one appears.

## 3. Supporting aggregate — late arrivals are not weaker setups

All HIGH-tier alerts, last 14 days, split by whether detection beat the 09:45 cutoff:

| bucket | n | median gap | median ep_score | median open→close | median open→high |
|---|---|---|---|---|---|
| in ORB window (<09:45) | 20 | 12.8% | 60 | **−0.9%** | +5.0% |
| **too late (≥09:45)** | **6** | 12.2% | **72** | **+2.5%** | +7.6% |

**Same gap size, HIGHER score, better outcome.** The delay is not filtering out marginal names — by
our own scoring the ones we cannot reach are the better-graded ones. **23% of HIGH alerts (6 of 26)
are lost to arrival time.**

⚠ **This is NOT independent of §1 — the three names above are three of these six.** It is the same
finding plus its aggregate, not corroboration. (`rel_volume` is deliberately omitted from this table:
its median is 0.0/0.2, i.e. the column is effectively unpopulated in `mi_ep_alerts`, so presenting it
as a matched covariate would imply a check that did not happen.)

⚠ **n=6. Do not treat the outcome gap as a measured edge** — it is directional support, not proof.
A plausible non-noise mechanism also exists: a name the scan notices later may be building through
the morning rather than gapping at the open, and that shape has more room left. That mechanism would
survive a bigger sample; it should be re-checked as n grows rather than assumed.

## 4. The other 29 — never scored at all, and only partly cheap to settle

29 of the 32 have **no `mi_ep_alerts` row**. The delayed scan never made them candidates, so there is
no score, no catalyst grade, no judge verdict. Nothing to look up.

**Is it easy to analyze? Partly — the split is ~75/25.**

`_score_ep` (`ep_detector.py:1103`) composes the score from:

| component | max pts | cost to recompute historically |
|---|---|---|
| gap | 25 | **free** — Polygon |
| rel_volume | 15 | **free** — Polygon |
| neglect | 15 | **free** — price history |
| prior_momentum | −25..0 | **free** — price history |
| theme_bonus | 10 | **free** — our own tables |
| float | 5 | **free** — FMP |
| vol_conviction | 5 | **free** — Polygon |
| **catalyst** | **25** | **LLM (Claude + Perplexity)** |

So ~75 of the ~100 points are recomputable for **$0** from data we already pull.

**But the catalyst layer is the swing, not a rounding error:**
- It is worth 25 points directly (`game_changer` 25 / `strong` 15 / `routine` 0).
- It drives the **conviction floors** — `gap ≥ 15% AND game_changer → score floored at 80`;
  `gap ≥ 10% AND game_changer → floored at 60` (`ep_detector.py:1248-1258`).
- It **gates the trade outright**: `routine` with `gap < 12%` is filtered before anything else
  (`ep_detector.py:1368`).

**A quant-only pass therefore yields an upper bound, not a verdict.**

⚠ **And the paid version is methodologically contaminated.** Grading a 7/21 catalyst today means the
news search reads coverage published *after* the move. That is hindsight leakage straight into the
one component that decides the outcome — it would inflate the pass rate in exactly the direction we
want the answer to go. Per `rigor-before-paid-eval-spend`, this fails the "exercises the live
mechanism" test: the live grader sees pre-move news; a retro grader cannot.

**Recommendation: do not buy the regrade.** The $0 quantitative pass is worth running (it can only
*eliminate* names — anything failing on quant alone is settled), but the surviving names would stay
unresolved, and §1 already answers the operator's question without them.

## 5. What this does and does not establish

**Established:** legitimate, fully-qualified EPs are being lost to detection latency — three of them
proven by our own logged skip reason, at a rate of roughly 1 in 4 HIGH alerts.

**Not established:** that trading them would have made money. Open→high is not what an ORB entry with
an ORB-low stop captures, and the live cohort's failure is round-tripping intraday, which these
figures cannot see. **#503 (why live trades die in 1.5 days) is untouched by this** and remains the
larger problem — the shadow ORB control shows zero winners with no broker involved.

**Decision this feeds:** the #490 real-time detection flip — **operator's call, THE LINE.**
