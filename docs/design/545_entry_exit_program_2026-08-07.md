> ⏭ **SUPERSEDED 2026-09-02 by `docs/design/545_entry_exit_program_v2_2026-09-02.md`** — v2 carries the delta since this document (the 08-07/08-09 re-entry sweep this doc filed as never-run, the 08-16 stop change, the 267-EP delayed-entry replays, the stop grid, the selection null, the harness census) plus the consolidated grid and the sequenced plan. This file is kept as the 08-07 inventory it cites; do not extend it.

# #545 — Entry/Exit Tactics Program: design doc (2026-08-07)

**Status: DESIGN ONLY — no code changed, no threshold moved, nothing flipped.**
⛔ **THE LINE:** every variant below is entry/exit/stop/sizing discipline = strategy. This document
collects evidence and ranks work; any live change is CHANGE_PROCESS + N≥10 backtest + #151 harness +
operator sign-off, per `docs/setups/CHANGE_PROCESS.md`. No trigger level, stop basis, or entry rule
is declared "correct" here.

**The thesis under test (operator, verbatim):** *"EP stocks is a winning cohort overall (not high
win rate, but major winners can be found here) however, entry/exit tactics is the big challenge… I
want to run multiple variations of all the parameters including some more novel approaches like
re-enter next day, which is similar to delayed EP, or even next few days when some delayed setup
hits."* Restated: a low-win-rate / fat-right-tail population is one you HARVEST, not one you filter
harder — the leverage is in WHEN you enter and HOW you hold, not in tightening what qualifies.

**Relationship to the accrual vehicles (both wired 2026-08-07 in `data_gated_reviews.yaml`):**
`exit_tune_cohort_review` (fires at n=20/40/60/80/100 closed live trades; today 14 closed as of
08-06, 15 with TEAM's 08-07 stop-out) and `exit_tune_bull_regime_read` (fires at 8 live closes in a
Bull tape; today 0). **They are the sample clock; this doc is the frame.** Their future runs execute
inside §B's grid and report into #545.

---

## A. INVENTORY — every entry/exit variant already tried, what it showed, on which cohort

Status vocabulary: **LIVE** (acting on real money) · **SHIPPED** (deployed, non-strategy) ·
**REFUTED** (tested, failed) · **BUILT-DARK** (code exists, default-off, no live caller) ·
**NEVER-RUN** (registered or specified, no result) · **EVIDENCE-ONLY** (measured, no build).

**Cohort legend — read this first, it is load-bearing.** Four distinct populations recur below and
they do NOT interchange:

| cohort | what it is | regime | caveat |
|---|---|---|---|
| **LIVE** | 14 closed real-money MAGNA53 trades 07-06→08-06 (−13.15R realized basis / −11.5R planned basis, **0 winners**; 15 with TEAM 08-07) | Correcting 7 · Choppy 6 · Crisis 1 · **Bull 0** | every conclusion from it is a non-bull conclusion |
| **PAPER** | 24–32 closed paper magna53 trades 04-17→07-02 (the only cohort containing multi-day winners) | 22 of 24 Bull | double-confounded: Bull era AND old entry mechanics — 19 of 24 predate the 06-05 ORB-window fix, fills as late as 11:35 ET that today's system cancels at 10:00 |
| **SHADOW ORB** | `mi_orb_shadow_trades` — same alerts, same gates, same exit ladder, NO broker, since 04-29 (16 closed) | spans Bull + Correcting | **0 winners in every month including two Bull months**; holds 1.3–2.5d matching live's 1.5, not paper's 3.2 — implicates the setup spec (ORB entry, ORB-low stop), not execution or tape |
| **SIM-B / #268** | simulated alert-entry cohorts (162 HIGH-alert replays, 83% May-era; the 1,307-candidate #268 Phase-B year) | mostly one era each | no real fills; the sim flatters tight stops and cannot see tick noise or spread |

### A1. Entry timing

| variant | cohort | result | status |
|---|---|---|---|
| **ORB 1-min breakout** (buy stop-limit at ORB high ×1.005, 9:31–9:44 window, stop = ORB low) | live baseline | 0-for-14 live; but #268b-calibrated at +0.95R/trade, 30% WR on the SIM-B year (Bull); winners appear at the MFE level at the calibrated rate (#503 §2) | **LIVE** |
| **ORB 5-min** (entry + stop both from the 5-min range) | #268 Phase-B judged year, n=300 vs 399 | +0.15R vs baseline +0.95R — win rate rises, expectancy collapses (wider range = higher entry + deeper stop crushes winner R). *5m-entry with a non-5m stop was never tested* (`w2_entry_study1_2026-06-12.md`) | **REFUTED** (as entry+stop pair) |
| **Skip-wide-open filter** (skip if ORB range > K×ATR) | same, honest ATR-covered window | trades removed were BETTER than trades kept (+0.34R vs +0.25R); full-year "lift" was 91% top-5-outlier-carried; initial +49% headline was a coverage artifact | **REFUTED** |
| **Same-day 1-min re-entry after stop-out** (pre-R3 `attempt_day1_reentry`) | live/paper 60d pre-05-17 | killed **0-for-7** (R3 ship 2026-05-17; the #483 trace records the pre-R3 double-leg cohort as 0/6 over 60d — counts differ by one across records, zero wins either way). `R3_DAY1_REENTRY_ENABLED` confirmed unset in prod; every same-day stop-out since carries `block:r3_reentry_disabled` | **REFUTED / config-off** |
| **Same-day 5-min-range re-entry** (re-enter only if price clears the post-stop 5-min range — the more-selective mechanism R3 never tested) | none | `orb_5m_reentry_hybrid_replay` registered in `data_gated_reviews.yaml` (2026-05-30), predicate 20 closed magna53 — **never run**. The full Day-1-stop-out set now exists to run it on | **NEVER-RUN** |
| **Next-day / N-day-later re-entry after stop-out** | none | **never tested anywhere — the biggest open cell in the grid** (§B). First real fixture 08-07: operator re-entered TEAM at $144.39 ~11:50 ET (stop = low-so-far) hours after Apollo's ORB entry ($147.13) stopped at $143.21; outcome open. The raw material is measured: §B of `live_cohort_day0_stopout_2026-08-06.md` gives every stop-out's day-1 and best-5-session forward R (QBTS +8.88R, HUT +8.32R, MANE +4.41R day-1 high — all HIGHS, not closes; MANE's "+4.41 day 1" was a morning touch inside a crash to −11R by that close) | **NEVER-RUN** |
| **Delayed-EP composition** (#270: WATCHED gap → ARMED on undercut of gap-day low → TRIGGERED on reclaim + volume; entries FIRST5-BREAK / GDL-RECLAIM / anticipation-on-coil) | 134-seed tiny-cap huge-gap cohort (gap ≥+40%), Mar–May 2026, offline | lifecycle selective (26% complete); FIRST5-BREAK entry fills 15/18 at median 3% stop, **median +3.5R MFE**; buy-and-hold loses the median name (−1R, 27% win) → fast harvest empirically necessary; anticipation entry realized ≈0R (below FIRST5) despite +2.9R MFE ceilings. **Different population from ours** — see §C on reuse | **EVIDENCE-ONLY** (deployable shadow was gated, never built) |
| **Anticipation vs confirm entries** (Family A consolidation shadow) | `mi_consolidation_entry_shadow`, n=150 settled | −0.217R expectancy, 36.7% WR → operator ruled NO-GO on real entries 7/12. Anticipate's stop is ~6× TIGHTER than confirm (median 1.61% vs 9.78%) on 5–8%-range names, yet median anticipate trade still reaches +2.44R excursion — both failures are exit-side (too tight to survive the wait; nothing banks the move) | **REFUTED for graduation; shadow accruing** |
| **620-chart timing layer** (5-min bars, 6/20 EMA + 6/20 MACD; MACD cross = signal, EMA cross = late confirmation) | none | spec captured 08-07 (`docs/methodology/620_chart.md`) with a worked TEAM example computed from real bars. ⚠ **It is a TIMING layer, not a selector** (operator: *"620 is used to fine-tune entry, not stock selection… I used 620 to pick entry after all this already lined up"*) — its honest test population is names ALREADY qualified, i.e. the Day-1 stop-out set, never a standalone sweep across all names. Periods (6,20) are an AXIS (author: lower = earlier + falser), and a 620-only proxy is expected to underperform what the operator actually does | **NEVER-RUN** |

### A2. Entry mechanics (broker-side — the fills the tape refused)

| variant | cohort | result | status |
|---|---|---|---|
| **#500 price-aware limit fallback** (price already above ORB high at submit → limit at last×1.002, chase cap 1.5× risk inflation) | full cancelled-entry history N=11; in-the-money-stop class N=2 (ARWR live, CADL paper) | live since 07-23. The failure class concentrates in the strongest gappers (ARWR +19.6% gap, MFE +1.7–2.1R missed) | **SHIPPED** |
| **#541 trigger-vs-ASK venue cancel** | INSM 08-06 (`[6098]`), QNST 08-07 (canceled in 6.2 ms, Alpaca: `"Unsolicited: Bad Stop 19.8"`) | root cause found 08-07: **we validate the trigger against the last TRADE; the venue validates against the ASK** — QNST's trigger $19.80 sat under a $19.83 ask (last trade $19.50) on a thin gapper open. Cost: 2 high-quality entries in 2 days (INSM ran +33%). Four earlier hypotheses refuted; **paper could not reproduce it because paper fills against a tight synthetic spread** — the canonical false-clear (see §C). Fix fork is open, operator's call | **EVIDENCE-ONLY / operator fork open** |
| **#414 gap/no-trigger class** (widen entry limit offset or stop-market with chase cap) | orb-cancellation classification: gap_through N=3 | parked by its own pre-committed bar (needs gap_through ≥10); D1 stop-ownership signed but confirmed NOT shipped as of 07-24 | **PARKED (event-gated)** |

### A3. Stop basis — tested exhaustively on the non-bull cohort, every widening refuted

| variant | cohort | result | status |
|---|---|---|---|
| **ORB low (current)** | live + all replays | width vs the stock's own ADR20 is essentially **random**: 0.15–1.19× (measured independently on two cohorts, 07-25 and 08-06). 8 of 14 live stops sat under 0.55× a normal day's range; ~80% of stop-outs fire within 30 min of open. The four biggest forward movers (MANE/QBTS/HUT/SMCI) all sat in the tight-stop half | **LIVE** |
| **ORB-multiple widening 1.25×/1.5×/2.0×** | 12 live replayed + SIM-B n=147 | live day-5: every trade still −1R at 1.25×/1.5×; 2.0× rescues exactly one (THC +0.81R). SIM-B: win% rises 32→47% but **every positive total flips negative when the top-5 per-trade deltas are removed**; median delta 0.00 (`stop_width_replay_2026-08-03.md`) | **REFUTED** |
| **ATR-anchored widening 0.5/0.75/1.0×** | same | worst family — hands the most width to exactly the wrong trades (biggest winners have the tightest ORBs); all rows ex-top-5 negative at both horizons | **REFUTED** |
| **Prior-day low (9M geometry)** | same | a different trade, not a wider stop: ~20% distance, 5× winner shrink; live −7.6R with 6 of 12 stopped anyway within 5 days | **REFUTED** |
| **ATR floor / day-low (risk-sized, full exit ladder)** | #268 window n=44 | monotonic degradation +0.66→+0.48→+0.27→+0.14R vs baseline +1.40R, in the sim-honest (wider) direction (`w2_entry_study2_2026-06-18.md`) | **REFUTED** |
| **ADR volatility floor k=0.5/0.75/1.0** (`max(ORB low, entry − k×ADR20)`) | 14 live, minute-bar forward replay | §D of the 08-06 doc looked decisive (the 4 floored survivors were exactly the 4 biggest movers) and **§E refuted it the same night: survival was DELAY** — all four hit the wider stop within 1–6 sessions; k=0.75 (−9.00R) is WORSE than no floor (−7.33R with the live +2R partial); floor alone = −14.00R at every k, zero winners. **Mechanism, and it generalises: widening the stop widens the R-unit, which RAISES the +2R target above the actual peak** (MANE's target moved 121.98→132.32 vs a 129.80 high). **Stop width and profit-take trigger are NOT independent axes — sweep jointly or not at all** | **REFUTED** (non-bull; re-test condition on first bull read stands) |

### A4. Profit-take / harvest

| variant | cohort | result | status |
|---|---|---|---|
| **Day-3/5 time-gated partial** (operator's own 2026-03-27 v2 rule) | live | **inert**: live holds 1.5d, 1 of 12 ever reached day 3, 0 partials ever fired, worth +0.09R/trade — last of 34 candidates. Not mis-specified — inapplicable to how live trades behave (they die first). Day-5 unconditional sell ruled out by operator 08-01 | superseded (reachable via reversion) |
| **+2R partial: 1/3 out, stop to breakeven** | live (signed off the 36-trade replay) | **LIVE — the only exit variant that has ever ACTED on real money.** Signed + constant set 08-01; first fire PLTR 08-04 was REJECTED by Alpaca (bracket-leg qty replace, 42210000) — the rule was "live" for 3 days and could not execute; leg-safe cancel-then-new shipped 08-04; **first successful partial 08-05 (PLTR +$33.27, first realized profit of the live program)**. Counterfactual on the 14-trade cohort: −13.15R → −7.33R (+5.8R); 4 fires, every winner a +0.67R bank. ⚠ Cost side unpriced: zero live winners exist; on paper the incumbent BEAT it (+0.36 vs +0.27), and no ride-to-strength winner exists anywhere in the floor sweep | **LIVE** |
| **The 34-candidate exit grid** (`_508_exit_rule_replay.py`: 1/3–1/2–all at +1R/+2R/+3R, 0.5/1/2×ADR, close-based MOC + next-open, day-1/2/3 closes, regime-conditional `rgm_bull/chop/corr` family incl. "none in Bull") | 36 magna53 (12 live + 24 paper) | level and unit are **inside single-trade noise** (NVCR's +2R capture cleared by half a cent; SYRE alone flips the paper ADR ranking; KURA's +3R IS 0.50 ADR — the units are the same print). What survives every cut: **near triggers tax the trades that run; far/slow ones do not.** Regime-conditional family built and scored but **unreadable** — regime is confounded with cohort (zero live Bull closes) | **EVIDENCE-ONLY**, re-runs at each n-milestone |
| **Trigger-unit question (R vs ADR vs %)** | 12 live + 43 records | **firm: R is not a consistent unit** — entry-to-stop spans 0.15–1.17× the stock's own ADR (7.7×), so "+2R" fires after 0.31 of a normal day on MANE and 2.35 days on NVCR. Fixed-% is wrong by construction (cohort ADR 2.6–9.7%). ADR-multiple is the only basis whose paper benefit survives removing the single SYRE gap-dodge; directionally best live (1 ADR: +0.69R vs +2R's +0.47R). WHICH unit is better remains unresolved — the data cannot resolve it until runners exist | **EVIDENCE-ONLY** |
| **Intraday partial sweep** (sell 1/3 at L, BE the rest; L over %, R, ADR bases) | 9 live + 31 paper, minute-bar sim | on the dead live cohort EVERY level helps and cost = 0 — **but that 0 is structural** (a 0-for-9 cohort has no winners to damage). On the 10 paper winners the SAME low levels scratch 6 of 10 at breakeven on days 1–8 of holds that paid up to +3.8R (winner cohort −2.46R at +3%). **The u-shaped tension is the central finding: levels that rescue the dead cohort are the levels that scratch the winners.** ADR mid-levels (~1–2×ADR20) are the only variants positive on BOTH cohorts without leaning on one catastrophe dodge | **EVIDENCE-ONLY** |
| **Giveback peak-lock (+6% arm / 60% floor, close-below decision line)** | 28-trade paper replay (11 harvest + 17 control) | +$8,075 lock-attributable, capture 23%→52%, losers untouched, direction operator-RULED 7/9 with shadow-first validation. `giveback_floor` hook + `giveback_shadow` deployed — **`mi_giveback_shadow` = 0 rows** because it writes only on a round-trip WINNER close and the live cohort has none. The signed close-below variant saves only MANE of the 9 (~+1.7R); the intraday-arm variant (unbuilt) is what reaches NVCR/SMCI-class givebacks | **BUILT-DARK** (hook default-off; shadow live but structurally starved) |
| **Trail-by-character (pivot/MA-respect arms, ADR 0031)** | `mi_pivot_stop_shadow` | shadow accruing (2 rows; same-day-drop bug fixed 07-25); global-MA sub-axis DEAD (sma vs ema vs handoff indistinguishable). **Hard-sequenced BEHIND the giveback fork** — never two concurrent live stop changes | **BUILT-DARK / shadow accruing** |
| **Partial size 1/3 → 1/2** | 28-trade sweep | second-order: +$612 standalone, +$1,180 stacked on the lock; bundle with the lock's flip sitting | **EVIDENCE-ONLY** |
| **Structural-level take (prior high / 20d / 52wk)** | 10 live | **zero fires for geometric reasons** — an EP entry either already stands above nearby structure or sits 10%+ below the prior high; nothing usable lives in the +3–10% band. Follows from the setup's definition; expect it to hold | **REFUTED as primary** |
| **Sell-into-day-2-gap** (open ≥ +2% above prior close and entry → sell 1/3 at open) | 41 trades | fires 6/41 (~15%); when it fires it banks near local tops (NVCR d2: +1.33R within pennies of the day's best). Complement only — MANE gapped DOWN on day 2 | **EVIDENCE-ONLY (complement)** |
| **Fast-harvest ladder on delayed-EP triggers** (all-out +1R / scale +1R/+3R, day-0 minute resolution) | #270 N=15 | scale-out beats single-target (median +2R vs +1R); 87–93% of position banks on the trigger day; the +137% tail is NOT systematically harvestable | **EVIDENCE-ONLY** (different population) |

### A5. Hold / time rules

| variant | cohort | result | status |
|---|---|---|---|
| **SMA10/20 trail** (close-below, needs ≥10 post-entry closes) | live | structurally absent for days ~1–9 — with the pre-08-01 rules, days 1–2 had NO protection above the hard stop, which is the mechanical reason 10 of 12 live losses printed exactly −1R | **LIVE** (day ≥10 only) |
| **9M time-stop** (≥5 trading days, excursion <+3%, alert-only `/timestop`) | 9M day-2 | alert-only, operator-confirmed; MAGNA53 dead-money tier (D1: ≥10d, <+3%, no partial) proposed — **replay never run** | D1 **NEVER-RUN** |
| **Calendar→trading-day `hold_days` fix (D2)** | — | asymmetry randomizes which trades get the day-3-4 test (a Friday fill's "day 3" is Monday); replay-gated, **never run** | **NEVER-RUN** |
| **Character-conditioned time exit** (e.g. biotech runs days, per Pradeep) | — | operator-deferred 08-01 ("later not now"); same axis as segmentation item (c) of the cohort review | **DEFERRED** |

### A6. Instrumentation corrections that bound every number above

- **`highest_price_seen` is blind under ~10 minutes** (5-min polls) — corrupted #503's first MFE
  table (CRCL's true peak was +1.62R vs a recorded 0.00). Every recorded peak is a FLOOR; every
  candidate's measured edge is biased DOWN.
- The intraday tracker's Polygon-delay + selection-predicate defects were fixed by the **path
  recorder (deployed 07-25)** — `mi_intraday_bars` now holds 1-min RTH bars for open + closed-today
  positions (121,604 rows as of 08-03), resampleable to 5-min for the 620.
- The **sell-discipline recorder** (`mi_sell_discipline_records`, 43 rows) derived stop width from
  the *trailed* stop until 08-01 — every paper trade that ran recorded garbage; fixed at root and
  backfilled, 43/43 consistent. Data accruing from 08-01 is sound.
- `mi_ep_scan_outcomes.fwd_5d_pct` is a **high-watermark**, not a close-to-close return —
  differencing it against a close benchmark was retracted once already (08-03).

### A7. Headline tally

- **~25 distinct entry/stop variants** measured (plus the 34-candidate exit grid) across four
  non-interchangeable cohorts.
- **Exactly ONE variant has ever acted on live money: the +2R partial** (live 08-01, executable
  08-05). Everything else is replay, paper, shadow, or dark.
- **ZERO variants of anything have been measured on a bull tape with real fills.** The tape turned
  Bull ~08-04; the cell starts filling now.
- Three variants the operator's ask names have **no result at all**: next-day re-entry, N-day
  delayed setup on OUR cohort, and the 620 timing layer.

---

## B. THE PARAMETER GRID

Axes and cell status. ✅ = answered (cohort noted) · ⚠ = partial/confounded · ⛔ = refuted ·
◻ = open. **Regime is a first-class axis: every ✅/⛔ below is a NON-BULL answer unless marked.**

### Axis 1 — entry timing

| cell | status |
|---|---|
| ORB 1m at open (baseline) | ✅ live: finds movers, dies at the open-whipsaw; shadow control says the spec, not execution |
| ORB 5m (entry+stop) | ⛔ SIM-B year |
| ORB 5m entry with independent stop | ◻ never tested (the w2 refutation does not cover it) |
| next-day open re-entry after stop-out | ◻ **biggest open cell** — answerable offline now (§C) |
| N-day delayed re-entry on a setup signal (base-then-turn / undercut-reclaim / coil) | ◻ for our cohort; ✅ mechanism-validated on the #270 tiny-cap population |
| same-day re-entry, 1m | ⛔ R3 0-for-7 |
| same-day re-entry, 5m-range-clear | ◻ registered (`orb_5m_reentry_hybrid_replay`), never run |
| 620 MACD-cross timing (on already-qualified names) | ◻ never run; spec + fixture exist |
| anticipation (pre-breakout coil close) | ⛔ for graduation (n=150 shadow, −0.217R); ✅ as evidence that the too-tight-stop failure is exit-side |

### Axis 2 — stop basis

| cell | status |
|---|---|
| ORB low | ✅ live baseline; width-vs-character measured random (0.15–1.19× ADR, twice) |
| ORB-multiple widening | ⛔ (3 independent tests) |
| ATR/ADR multiple (floor or anchor) | ⛔ non-bull, incl. the §E forward refutation; **re-test condition: first bull read** |
| structure (prior-day low) | ⛔ |
| joint stop×take-profit sweep | ◻ — mandatory for any future stop candidate (the R-unit coupling mechanism) |
| stop basis for a RE-ENTRY leg (low-of-day / 5m low / 620 basing low) | ◻ — new sub-axis the re-entry variants introduce; the operator's TEAM fill used low-of-day-so-far |

### Axis 3 — profit-take

| cell | status |
|---|---|
| none (ride) | ✅ loses the median everywhere measured (live, shadow, #270) |
| time-gated (day 3/5) | ✅ inert on live holds |
| fixed R level + fraction + BE | ⚠ +2R/⅓ LIVE; level/fraction inside single-trade noise; cost side unpriced (no live winners) |
| ADR-multiple trigger | ⚠ directionally best live; blocked on runners (T3) |
| fixed-% trigger | ⛔ wrong by construction (2.6–9.7% ADR spread) |
| structural level | ⛔ as primary; complement only |
| sell-into-day-2-gap | ⚠ complement, fires ~15% |
| giveback peak-lock (close-armed) | ⚠ ruled 7/9, built-dark, shadow starved of winners |
| giveback peak-lock (intraday-armed) | ◻ — the variant that reaches NVCR/SMCI-class givebacks; unbuilt |
| trail-by-character | ⚠ shadow accruing, hard-sequenced behind the giveback fork |
| regime-conditional take ("aggressive in bear, none in bull") | ◻ encoded + scored, **unreadable until bull closes exist** |

### Axis 4 — hold rules

| cell | status |
|---|---|
| breakeven after partial | ✅ live |
| day-5 unconditional sell | ✅ operator-removed 08-01 |
| time-stop (MAGNA53 dead-money tier) | ◻ replay never run |
| calendar→trading-day alignment | ◻ replay never run |
| character-keyed time exit | ◻ operator-deferred |
| max-hold / hold-through-day-2 rules | ◻ — moot until trades survive day 0; becomes real if re-entry or a bull tape lengthens holds |

### Axis 5 — regime (cross-cutting)

| cell | status |
|---|---|
| non-bull, live | ✅ 14 trades — the entire evidence base |
| bull, live | ◻ **empty since the program began**; `exit_tune_bull_regime_read` fires at 8; tape Bull since ~08-04, so TEAM/PLTR-era trades start filling it |
| bull, no-broker control | ✅ shadow ORB: 0 winners in 2 bull months — the one bull data point we own, and it points upstream of tactics |

---

## C. ANSWERABLE NOW vs NEEDS CAPTURE

### C1. Existing harnesses — REUSE these; do not mint a fourth minute-bar replayer

| harness | contract | reuse for |
|---|---|---|
| `scripts/probes/_306_intraday_partial_sim.py` | offline minute-bar replay off cached TSVs; fill-bar excluded from trigger scan; partial fills AT trigger (limit-at-level); BE fills at entry or gap-open; pessimistic tie-breaks | trigger-level/basis sweeps; the frozen fill contract every new sweep should inherit for comparability |
| `scripts/probes/_508_exit_rule_replay.py` | 34 candidate rules vs do-nothing baseline; bar-covered days bar-by-bar, else pessimistic daily; per-regime cells; fill-realism tags; twice-verified | every future exit-rule re-run (the n-milestone reviews); adding candidates = adding a lambda, not a harness |
| `scripts/probes/_stop_floor_forward_replay.py` | minute-bar, 10 sessions forward, models exactly hard stop + the live +2R partial + BE; k=0 reconciles to reality within 0.07R/trade | **the natural base for the re-entry replay** — it already walks each stop-out forward with the live exit rules; a re-entry variant is a second simulated leg in the same walk |
| `scripts/_270_delayed_ep_replay.py` (+ `_270_entry_replay.py`, `_270_exit_replay.py`, `_270_harvest.py`) | daily-bar WATCHED→ARMED→TRIGGERED state machine, validated vs MNTS; minute-bar FIRST5-BREAK/GDL-RECLAIM entry replay; shared harvest evaluator (speed-spectrum exits, opt/pess intrabar bounds) | see C2 — the delayed-setup machinery exists |

### C2. Does the existing delayed-EP replay cover the operator's next-day ask? **Partly — mechanism yes, population no.**

- **What it does:** detects a huge-gap day (close ≥ +40%, ≥3× ADV20, above SMA200), ARMS on an
  undercut of the gap-day low within 15 days, TRIGGERS on a volume-confirmed reclaim; then replays
  tuned intraday entries (first-5-min-high break beat gap-day-low reclaim 2.5× on R) and a
  fast-harvest exit ladder. All offline, thresholds explicitly operator-calibration knobs.
- **What transfers:** the state-machine shape IS the operator's "next few days when some delayed
  setup hits" — undercut-then-reclaim is exactly what TEAM did on 08-07 (stopped Apollo out, based,
  turned). The entry layer (FIRST5-BREAK) and the harvest ladder are directly reusable.
- **What does not:** the cohort. It was seeded on +40% tiny-cap gappers (MNTS-class), not MAGNA53
  EPs (~+10–20% gaps, larger caps); its ARM event keys on the *gap-day low*, not on *our stop-out*;
  and its forward numbers are MFE-ceilings on N≤17 in one window. **Re-seeding it on the MAGNA53
  Day-1 stop-out set with recalibrated gates is a re-run, not a rebuild.**

### C3. Answerable NOW, $0, from data already captured

1. **The Day-1 stop-out re-entry sweep** — the program's first deliverable (§D Phase 1). Population:
   all 15 live Day-1 stop-outs (14 + TEAM). Variants in one harness run, all as a second leg in the
   `_stop_floor_forward_replay` walk, all under the frozen fill contract, all exiting via the LIVE
   ruleset (+2R partial + BE + stop):
   - next-day-open unconditional re-entry (stop = prior-day low and re-entry-day low variants);
   - same-day 5m-range-clear re-entry (finally runs `orb_5m_reentry_hybrid_replay`);
   - base-then-turn proxies — **sweep several, per the PLAN line's honesty note** (N consecutive
     higher lows off the session low · M-minute basing range then break · first higher-close
     sequence), because any single proxy is a modelling choice, not the operator;
   - the 620 family — 6/20 MACD cross on 5-min resampled bars, plus the author's own (8,24)/(12,26)
     sensitivity axis, entry on the cross with stop at the basing low.
   Bars: `mi_intraday_bars` covers trades from 07-25 (QBTS, FTNT, BTDR, BLZE, TEAM, PLTR); the
   `_306`/`_stop_floor` probe caches already hold Polygon minute bars for the July cohort; anything
   missing is a free Polygon refetch. Post-stop-out afternoons for closed-same-day trades are
   captured by the 16:10 sweep since 07-25.
2. **The #270 re-seed** on MAGNA53 EP alerts (delayed-setup detection on our population) — daily
   bars only, `mi_daily_closes` has them.
3. **Each n-milestone / bull re-run of the 34-rule grid** — harness exists; waits only on the
   sample clock, not on tools.

### C4. What each of those tests CANNOT see — stated per the two false-clears this week

Paper and replay both cleared things that failed live twice this week: the ask-through-trigger
cancel could not reproduce on paper (paper fills against a tight synthetic spread — 3 months of
probes chased it), and a broker-reason lookup passed on a historical replay while failing live. So,
per proposed test:

- **Every minute-bar replay** cannot see: the SPREAD (the #541 class — a thin gapper's first-minute
  ask sat 33c above the last trade; a simulated fill at the bar price may be a fill the venue
  refuses); tick-level stop hunts inside bars; borrow/HTB; slippage beyond the modelled cent;
  LULD halts; and our own market impact.
- **Re-entry replays specifically** cannot see: that a re-entry order competes with the day's
  safeguards state (position cap, 2% daily loss limit — a re-entered name can lose 2 risk units in
  one day and the daily-loss safeguard attributes by CLOSE day); and that the R3-era whipsaw
  (MRAM: stopped 13:42, re-filled 13:50, stopped 13:59) is exactly what a bar-level basing proxy
  can misread as a turn.
- **The 620 proxy** cannot see the operator's daily-chart / theme / fundamentals context — the
  source itself subordinates the tool to price. A 620-only replay UNDERPERFORMING the operator's
  discretionary result is expected, not a refutation of the layer.
- **The shadow ORB control** cannot see fills at all — it is the clean setup-vs-execution
  discriminator, never an expectancy estimate.
- **Anything measured before a rule's first live fire is not evidence the rule can ACT** — the +2R
  partial was "live" for 3 days while structurally unable to execute on every MAGNA53 bracket.
  Verify-live means the operator-facing surface, on real order plumbing.

### C5. NEEDS CAPTURE — no offline substitute exists

1. **Live bull-tape closes.** The single most valuable data the program can acquire; nothing
   replays it. `exit_tune_bull_regime_read` fires at 8. Accrues from live trading already
   authorized — no new risk decision needed to fill it.
2. **Live runners** (peak_adr ≥ 1.5) — what prices the COST side of every take-profit candidate.
   T3 accrual; instrumentation is already correct post-08-01.
3. **NBBO/quote capture at submission** — the #541 class showed trade-vs-ask divergence decides
   entry survival on thin opens; nothing in our stores records the ask. Without it, every
   entry-timing replay silently assumes fills the venue may refuse. (A capture-only build; filed as
   a Phase-2 candidate, not assumed.)
4. **The operator's own discretionary fills** (TEAM-class) — recorded as they happen in the #545
   PLAN line; one fill is a fixture, not evidence, but each one calibrates the base-then-turn
   proxies against what he actually does.

---

## D. PHASED PLAN — for the operator to sequence (benefit AND cost, in R)

**Phase 0 — already running; cost 0R.**
- +2R partial live; incumbent + all 34 candidates scored counterfactually on every new close
  automatically (the recorder makes shipping one rule not cost the comparison).
- Accrual clocks: n=20 cohort review (15/20 after TEAM), bull read (0/8, tape now Bull),
  T3 runners (2), giveback shadow (starved until a round-trip winner exists).
- Action: none. This phase is why no waiting decision is needed to keep learning.

**Phase 1 — the offline re-entry sweep (C3.1 + C3.2). Cost: $0, 0R at risk. ~One session of work.**
- Deliverable: one table over the 15-trade stop-out set — per variant: fires, fill rate, realized R
  under the live exit ruleset, and **the cost column: extra −1R legs paid on names that kept
  falling.** That cost is not hypothetical: 8 of 14 stop-outs never went green and 4 of the 8
  tight-stop names fell at every width — an unconditional next-open re-entry pays a second full
  risk unit on most of those. The winners it must clear that bar with are highs, not closes
  (QBTS's +8.88R and HUT's +8.32R are best-5-session HIGHS; MANE's day-1 "+4.41R" was a touch
  inside a crash). Expect the honest number to be much smaller than §B of the 08-06 doc suggests —
  that is the point of running it.
- Includes the 620 family as one factor among several, on the already-qualified population only.
- Gate on itself: if every re-entry variant is net-negative after the cost column (the R3 outcome
  repeated), the cell closes and says so — that is a legitimate end state.

**Phase 2 — forward capture, log-only. Cost: 0R (no order path). Small build, operator-approved
scope only.**
- IF Phase 1 shows signal: a log-only evaluator that marks re-entry triggers (5m-range-clear /
  base-then-turn / 620 cross) on live Day-1 stop-outs as they happen, writing rows beside the path
  recorder — the same shadow-first pattern as the giveback shadow. No orders, no THE LINE exposure;
  it exists to price the variants on forward tape instead of 15 replayed trades.
- Optional capture add-on (operator's call): persist the NBBO ask at entry submission (C5.3) so
  entry-timing replays stop assuming fills the venue refuses.

**Phase 3 — the bull-tape reads. Cost: 0 incremental R (the live program's existing ~−1R/trade
losing cost is already authorized and is what buys this data).**
- At 8 bull closes (`exit_tune_bull_regime_read`): do trades still die on day 0? Does +2R start
  capping runners (the operator's own hypothesis — let winners run in bull)? Does the stop-floor
  refutation hold when things trend? Every one of these is a re-run of an existing harness on the
  new cell.
- At n=20 (`exit_tune_cohort_review`): full grid re-run inside this frame, cells (a)–(e) as wired.

**Phase 4 — operator forks, only after Phases 1–3 put numbers on the table. Each is
CHANGE_PROCESS + sign-off; costs stated per candidate when proposed. The known shapes:**
- **Re-entry rule (if Phase 1–2 shows signal):** a NEW rule, not an R3 reversal (R3 killed
  *same-day 1m* re-entry; next-day is a different mechanism — no reversal burden). Cost shape: up
  to +1 risk unit per stop-out day per name; interacts with the daily-loss limit and the 5-slot
  cap; needs its own entry-mechanics review (the #541 ask-validation class applies to any new
  order).
- **Giveback intraday-arm variant:** reaches the NVCR/SMCI giveback class the signed close-armed
  version cannot; cost shape = the paper winner-scratch numbers (§A4); blocked behind the A-fork
  per ADR 0031 sequencing (never two concurrent live stop changes).
- **Trigger unit (R→ADR):** one-column change, replay re-run in ATR first; blocked on runners (T3)
  — do not rule on loss-only evidence.
- **Stop geometry:** stays REFUTED unless the bull read reopens it, and any candidate must sweep
  jointly with the take-profit level (the R-unit coupling).

**Sequencing rationale in one line:** Phase 1 is the only place a genuinely new answer exists at $0;
Phases 2–3 make the two empty columns (forward re-entry evidence, bull) fill themselves; Phase 4
spends operator attention only where a number already exists.

---

## E. The thesis, tested against the inventory

**The tactical half of the operator's thesis is strongly supported.**
- Selection finds movers at the calibrated rate; the four biggest 5-session forward moves in the
  live cohort were all names we entered and got stopped out of.
- Every "filter harder" variant tested (skip-wide-open, 5m OR, tighter anything) refuted or
  tail-carried; the ONE harvest rule shipped (+2R partial) is the only intervention that measurably
  improved the live cohort (+5.8R on 14 trades) — harvest beat filter everywhere they were compared.
- The peaks live intraday and die unprotected; entry timing (ORB-at-open, ORB-low stop) is
  maximally exposed to opening whipsaw. WHEN you enter and HOW you hold is exactly where the
  measured leverage sits.

**The cohort half — "EP stocks is a winning cohort overall" — is not yet demonstrated on our
data, and the honest statement is narrower:**
- The cohort reliably produces EXCURSION (alerts beat the market's own best excursion ~6% at the
  median, 82% of the time) but finishes five days later ~1% BEHIND it at a 44% win rate — movement,
  not persistence, on the corrected basis.
- The shadow ORB control — no broker, no execution — shows **zero winners including two bull
  months**, which points at the setup specification itself, upstream of every tactic in this
  program. The re-entry/delayed-entry axis is partly a response to exactly that (a second, better-
  timed entry into the same qualified name), which is why it is Phase 1.
- And every conclusion held today is a non-bull conclusion, on a bull-market methodology. The
  thesis is not contradicted — but it is UNTESTED in the one regime it presumes, and the program
  should say so rather than assume it.

---

*Cross-references: PLAN #545 (frame + TEAM fixture + 620 capture) · #306 (harvest tune) · #508
(exit discipline SSoT + state doc) · #541 (ask-validation class) · #500 (price-aware entry) · #414
(gap/no-trigger, parked) · `exit_tune_cohort_review` + `exit_tune_bull_regime_read` +
`orb_5m_reentry_hybrid_replay` in `data_gated_reviews.yaml` · `docs/methodology/620_chart.md` ·
`docs/setups/exit_discipline.md`. Every number above carries its source doc inline; nothing here
was re-measured.*
