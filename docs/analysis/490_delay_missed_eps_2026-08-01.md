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

⚠ **This margin is conditional, and §6 shows the condition is not met by default.** The 150s ceiling
was measured on the DELAYED scan's candidate load — roughly 2 candidates per tick. Grading runs only
on admitted candidates (`ep_detector.py:1888`), so flipping `UNIVERSE_AUTHORITATIVE` adds ~19.4
names/day to the grading path. **At ~10× the load a 2.5-minute worst case has no headroom left.**

I originally wrote this as "a thing to watch on rollout, not a reason to withhold the flip." **That
was wrong** — see §6. The load increase and the latency margin are the same variable, so it is a
precondition, not a monitoring item.

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

## 6. Volume effect per toggle — measured, and none is free

**Operator, 2026-08-01:** *"with 30+ more EP that is potentially traded, that's adding a lot if true,
may mean we need more filters if we let this cohort in, not that is a reason to block them if
legit."*

The flip is three independent runtime toggles, all currently OFF in prod (`EP_RT_PASS2_ENABLED` and
`EP_RT_UNIVERSE_ENABLED` are both **true** — the RT layer runs and observes today; only the
*authoritative* flags are off). Each writes a shadow audit event that fires in **both** modes, so the
volume effect is directly measurable without flipping anything.

| toggle | shadow event | admits/day | removes/day | net |
|---|---|---|---|---|
| `EP_RT_UNIVERSE_AUTHORITATIVE` | `ep_rt_universe_catch` | **+19.4** | — | **+19.4** |
| `EP_RT_GAP_AUTHORITATIVE` | `ep_rt_floor_flip_up` / `_down` | **+25.0** | **−13.9** | **+11.1** |
| `EP_RT_VOLUME_AUTHORITATIVE` | `ep_rt_rvol_gate_flip` | 12.2 flips, **both directions** | | **±12.2** |

*(ticker-days, deduped per ticker per day by `_audit_dedupe_check`; 5-9 trading days each.)*

**Baseline for scale: 1.86 HIGH alerts/day and 0.57 live entries/day today.**

▶ **I was right to withhold a sequence. None of the three is volume-neutral** — including
`GAP_AUTHORITATIVE`, which I had guessed might be accuracy-only. It is the second-largest volume add.

⚠ **The `_down` leg is the one genuinely attractive number: −13.9/day stale false-admits** — names we
currently score, and could trade, that real-time data says never qualified. That is a pure quality
gain with *negative* volume. It was bundled with the +25.0 `_up` leg inside the same toggle.

▶ **SPLIT BUILT 2026-08-01, shipped OFF** — `ep_rt_gap_down_authoritative`. Structurally
removal-only (guarded by the flip-DOWN condition itself), pinned by a 144-case sweep, mutation-tested.
SSoT: `docs/setups/magna53_ep.md`. **The live flip needs operator sign-off — not taken.**

### What the down-leg cleanup is actually worth — and the correction that halved it

111 flip-down ticker-days → 11 scored alerts (all HIGH) → 4 live trade rows.

⚠ **My first pass reported all 4 as preventable, worth −$52.69. That was wrong.**
`live_tracker.process_new_alerts_live` selects `FROM mi_ep_alerts WHERE alert_date = $1 AND
score_tier = 'HIGH'` — **the alert ROW, not the current tick's candidate list.** Dropping a candidate
therefore prevents an entry only when the flip-down lands on the tick that WRITES the alert. Later
flip-downs are pure telemetry.

| ticker | date | delayed | RT | flip-down @ | alert written @ | prevented? | P&L |
|---|---|---|---|---|---|---|---|
| WKC | 07-24 | 11.63% | 8.91% | 08:15:00 | 08:15:00 (same tick) | ✅ **yes** | **−$23.80** |
| QBTS | 07-27 | 11.29% | 9.50% | 07:20:01 | 07:20:00 (same tick) | ✅ **yes** | **−$22.26** |
| FTNT | 07-30 | 10.79% | 7.77% | 09:30:05 | 07:00:00 | ❌ no — 2.5h late | −$6.63 |
| ARM | 07-30 | 15.46% | 8.34% | 09:45:10 | 08:55:00 | ❌ no — after entry | $0 (cancelled) |

**Defensible: −$46.06 of a −$224.01 30-day total (20.6% of the loss), from 2 of 17 trades.**
Honest N — the criterion is evaluated on 111 events, but the money rests on **2 filled trades**.

### The larger gap FTNT exposes — no real-time re-validation at entry

FTNT's alert was written at **07:00** on a stale 10.79% gap. At **09:30:05 — one minute before the
09:31 entry — the system logged its real-time gap as 7.77%, below the 10% floor.** It entered anyway.

**Nothing re-checks an alert against real-time data at submission time.** The gap-down toggle cannot
fix this: by 09:30 the alert row already exists, and the entry job reads rows. The fix is a
re-validation inside `submit_trade_entry` — an **entry-path change touching real money, so it needs
its own sign-off.** Filed under #490; deliberately not folded into the toggle split.

### The finding that changes the shape of the decision

`ep_detector.py:1888` — `if not authoritative: continue  # SHADOW: not admitted, no LLM spend`.

**Grading only runs on admitted candidates.** So flipping `UNIVERSE_AUTHORITATIVE` puts ~19.4
additional names/day through Claude + Perplexity.

**That directly attacks §2's safety margin.** The latency ceiling that made recovery look safe —
max 150s, worst case 09:40 tick + 150s = 09:42:30 against a 09:45 cutoff — was measured at today's
load of roughly 2 candidates per tick. At ~10× the candidates, a 2.5-minute worst case has **no
headroom to give**.

**So the filter question and the latency question are the same question.** "Flip now, add filters
later" does not decompose: the volume that needs filtering is also the volume that would push grading
past the ORB window and re-create the exact miss the flip is meant to fix. Filters are not a
follow-up item here — they are load-bearing for the flip working at all.

## 7. What this does and does not establish

**Established:** legitimate, fully-qualified EPs are being lost to detection latency — three of them
proven by our own logged skip reason, at a rate of roughly 1 in 4 HIGH alerts.

**Not established:** that trading them would have made money. Open→high is not what an ORB entry with
an ORB-low stop captures, and the live cohort's failure is round-tripping intraday, which these
figures cannot see. **#503 (why live trades die in 1.5 days) is untouched by this** and remains the
larger problem — the shadow ORB control shows zero winners with no broker involved.

**Decision this feeds:** the #490 real-time detection flip — **operator's call, THE LINE.**
