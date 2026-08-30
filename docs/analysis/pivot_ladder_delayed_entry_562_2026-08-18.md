# #562 Pivot-ladder delayed entry — undercut-and-reclaim, the full ladder, and the proximity number

> 🗂 **DELAYED-ENTRY CONTEXT LEDGER — READ FIRST: `docs/setups/delayed_ep_reentry.md § THE CONTEXT LEDGER`.** It carries the goal, every operator ruling, every study and its result, and the open questions. Two cards ran on this subject without it on 2026-08-29 and returned nothing new. Kept complete by `tests/test_delayed_entry_ledger_complete.py`.


**2026-08-18 · read-only · $0 · probe: `scripts/probes/pivot_ladder_562.py`**
Measures the operator's entry architecture (`docs/setups/delayed_ep_reentry.md`
§"2026-08-16 — THE ENTRY ARCHITECTURE") on every EP alert day, INCLUDING the declined
names — the population every prior geometry test (#482, #572) could not see, because those
tests started from trades we actually entered. Nothing on prod written; no strategy-path
code touched. ⚖ THE LINE: this measures and proposes nothing binding; entry discipline
changes are the operator's alone.

---

## 🔴 PRE-REGISTRATION — written 2026-08-18 BEFORE any outcome data was read

The reclaim definition, entry price, stop, and look-forward window are free parameters, and
the ladder multiplies them. Sweeping them for the best cell would manufacture a finding (the
32-cell grid lesson). Everything below was fixed on structural grounds before the first
forward bar was read. Every cell is reported; no cell is promoted to "the finding" because it
performed; the primary is labeled and was chosen first.

**Facts already known when this was written (stated for honesty):** the NET 2026-08-07 case
(given in the task brief: undercut 08-10, reclaimed, ran ~295→332), the INTC 2026-04-24 case
(in the SSoT doc: limit at EP-day low never filled, bottomed 1.5% above, ran; EP-close pivot
filled +9.18R), and the T1 breach-class MFE table in `delayed_ep_reentry.md` (99 HIGH names,
aggregate). No other outcome data was consulted. NET and INTC are cohort members below,
never the evidence.

### Cohort

- **Universe:** every live `mi_ep_alerts` row (`COALESCE(source,'live')='live'` — replay rows
  excluded), deduplicated to one (ticker, alert_date) per day, all tiers (sliced HIGH vs
  MODERATE in reporting).
- **Episode dedup:** if the same ticker re-alerts within 10 trading days of an earlier alert,
  only the FIRST alert day anchors an episode (consecutive-day alerts are the same move; the
  ladder belongs to the episode's EP day). Raw and deduped counts both reported.
- **$5 floor:** EP-day open (from `mi_daily_closes`) ≥ $5 — the system's own convention
  (`missed_outcomes._DEFAULT_PRICE_FLOOR`); sub-$5 rockets inflated a number here once before.
- **Classification:** ENTERED = a filled magna53 `mi_live_trades` row exists on the episode's
  (ticker, alert_date) (status reached a fill); DECLINED = everything else. Declined skip
  reasons annotated from `mi_ep_missed_outcomes` / skip rows where available.
- **Exclusions (the denominator states them):** episodes with no EP-day row in
  `mi_daily_closes`; episodes with zero forward sessions. Episodes whose 10-day window is
  truncated by the right edge of data stay in, flagged `truncated`. Alert days only — the
  cohort is names the system ALERTED on; names it never saw are not here.

### The ladder — five pivots, fixed at the EP event, each with its own entry and stop

All levels are knowable at the end of the EP day (or, for MA10, at each later morning).
P = the pivot level. Window = the 10 trading days after the EP day (t+1..t+10), counted in
the ticker's own session series. Any pivot may trigger; cells are evaluated INDEPENDENTLY
(the operator: "any one of them can trigger and work") — no portfolio/allocation policy is
simulated.

| pivot | level | class |
|---|---|---|
| **EPL** | EP-day LOW | support |
| **EPC** | EP-day CLOSE | support |
| **PDH** | prior-day HIGH (session before the EP day) | support |
| **MA10** | 10-day SMA of closes through the PRIOR session (knowable at the open; recomputed daily) | support (moving) |
| **EPH** | EP-day HIGH | breakout |

"Reclaim levels" from the operator's list are represented by the touch-reclaim arms
themselves (a reclaimed level IS the signal here), not as a separate pivot; second-order
reclaim ladders need intraday data and are out of scope this pass. ORB-high is approximated
by EP-day HIGH (the 1-min ORB needs minute bars; for the delayed window the daily high is
the structural analog).

### Arms — the same three rules applied uniformly to every pivot of its class

**Touch-reclaim (support pivots; the NET shape). PRIMARY CELL = EPL touch-reclaim.**
- Signal: the FIRST session S in the window with low(S) < P. **First touch decides:** if
  close(S) > P → signal; if close(S) ≤ P → the pivot is dead for the episode (the SSoT
  finding "the breach is the damage" — a close through support is the invalidation). No
  later session can resurrect it in the primary definition.
- Entry: next session's OPEN (a close-based signal cannot be traded at that close), only if
  that open > P (an open back below the reclaimed level voids the reclaim; voids counted).
- Stop: low(S) — the undercut session's low.

**Zone / proximity entry (support pivots) — the arm every prior test missed.**
- Signal: the FIRST session S in the window with low(S) ≤ P + 0.5×ADR$ AND close(S) > P
  (ADR$ = ADR%×P; the band is the operator's "0.25–0.5×ADR" outer edge). First zone-session
  decides, same dead rule (close ≤ P kills it). Touches count — a zone trader is fishing the
  band around the pivot, tag or no tag.
- Entry: next session's OPEN, only if open > P.
- Stop: min(low(S), P) — the pivot is the invalidation line beneath the turn; a near-miss
  approach stops at the pivot itself.
- Daily-bar limitation, stated: the operator's actual trigger in the zone is a 620 turn on
  the 5-minute chart. Daily bars cannot see it; the close-above-P is the daily proxy. A
  close>open "up day" filter was considered and rejected to keep the parameter count down.
  **No 620 backtest is attempted in this pass** — instead the minute-pull prerequisite is
  costed (below).

**Breakout (EPH).**
- Signal: the FIRST session S in the window with high(S) ≥ P (a resting buy-stop at P fills).
- Entry: max(open(S), P) on S itself — tradeable, unlike the close-based arms. No chase cap
  (a cap would be a sixth parameter; gap-through entries fill at the open and are reported
  as-is).
- Stop: the prior session's low (the structure anchor, the same convention as the 9M stop
  and the #572 Apdl lane).

### Proximity MEASUREMENT (the deliverable on its own, entry rule or none)

Per support pivot, over the window, classify every episode:
**never-in-zone · near-miss (low entered [P, P+band] but NEVER < P in the window — the INTC
class) · touched-reclaimed · touched-dead**, at BOTH bands 0.25×ADR$ and 0.5×ADR$.
For each class: n, then forward outcome = MFE in ADR units (max high over the 20 trading
days after the classifying session, from the NEXT session's open) and share ≥8×ADR (the
SSoT T1 convention, so the tables read side by side). The near-miss class's size and outcome
IS "the value of the proximity model over a hard limit."

### Outcome simulation — identical to the #572 sweep so cells are comparable across docs

- Engine: `geometry_sweep_572.simulate()` reused (import, not copy) at daily resolution
  (`skip_day0_minutes=True`): +2R partial (half, lane's own unit) → breakeven →
  SMA10/20-max daily-close trail → 20-trading-day time stop; gap-at-open stop fills (open
  below stop fills at the open — worse-than-full losses expressible); the genuinely
  ambiguous both-touched day prints a **[conservative, optimistic]** bracket.
- Units: **realized R** (pnl / that arm's own entry−stop) AND **ADR units** (pnl /
  (entry × ADR%/100)); ADR% = mean 20-day (high−low)/close over sessions strictly before
  the ALERT date. R alone is volatility in disguise; ADR is the leveller (the CPDL mirage).
- Tail: median, P90, max, share ≥+1R/≥+2R, and summed R — EPs are rare and low-win-rate; a
  median cannot see the 10x.
- **Baselines:** DECLINED names — doing nothing = 0R (the honest baseline; a negative sum
  is worse than not trading). ENTERED names — what the live system actually realized on the
  same name-day (from `mi_live_trades`).
- **Era slices** (alert-date basis; A < 08-05 no partial · B 08-05..08-16 +2R partial ·
  C ≥ 08-17 2R-stop era): robustness slice — the sim policy is uniform, but the live
  baseline for ENTERED names is era-dependent. Any cell n<4 = "not readable", no conclusion.
- **Fill limit, stated every time:** EVERY fill here is simulated — entries and exits; for
  declined names no real fill has ever existed. Daily resolution cannot sequence intraday
  order. This is reconstruction, not fills; only a live shadow arm gives fill realism.

### Pre-registered alternatives (PRIMARY CELL ONLY — not swept across the ladder)

Reported side by side with the primary EPL touch-reclaim, labeled, regardless of what they
show: **W5** (5-day window) · **W20** (20-day window) · **LENIENT** (any later session may
reclaim — first session with low<P AND close>P even after an earlier close below P) ·
**CLOSE-ENTRY** (enter at the reclaim close — untradeable idealization bounding the
next-open lag cost). Applying these to all nine cells would be a 45-cell sweep; refused.

### 620 prerequisite costing (measured, not built)

For every zone-arm signal session (0.5×ADR band, any support pivot), count the distinct
(ticker, date) approach-days that a proximity+620 backtest would need minute bars for, vs
what `mi_intraday_bars` already holds (alert ticker-days only). Reported as a count + a
statement of pull cost.

---

## RESULTS — written after the probe ran; the pre-registration above was not edited after

### The answer, up front

**No cell earned a live shadow arm.** The primary cell (EP-day-low undercut-and-reclaim on
declined names) reads mildly positive against the doing-nothing baseline — **+6.09R / +4.79
ADR summed over 55 simulated trades (+0.11R per trade)** — but the ENTIRE positive sum is
one $5.51 stock (TE 05-12, +10.00R): **ex-TE the cell is −3.91R / −0.72 ADR.** And the
per-trade margin is a quarter of the known optimism of this exact simulator (+0.41R/trade,
the #572 B0-vs-live calibration on identical entries). Seven of the nine ladder cells are
outright negative on declined names. The proximity measurement — the deliverable that
survives regardless — says the approached-but-never-touched class is **~10% of episodes and
its forward outcomes are ordinary** (0 of 21 measurable reached ≥8×ADR): the INTC monster
is the exception even inside its own class. What DOES carry the tail is the class the
operator's own SSoT already flagged: names that **never come near the EP-day low at all**
(10.7% of them reach ≥8×ADR).

### Denominator (stated)

252 live EP alert name-days → 251 episodes (1 re-alert absorbed; dedup verified — only
BLZE 07-31→08-04 fell inside a 10-td window) → **249 eligible** (2 dropped: no forward
sessions; 0 sub-$5 EP-day opens; 0 missing ADR). **ENTERED 40 / DECLINED 209**; HIGH 175 /
MODERATE+none 74. **79 of 249 windows are right-censored** (alert within 10 td of the
08-17 data edge) — the August cohort will mature; these numbers move. Alert-day cohort
only: names the system never alerted on are outside every denominator. **Fill limit: every
fill is simulated — entries AND exits; declined names never had a real fill.** Daily bars
cannot sequence intraday order; ambiguous days carry a [cons, opt] bracket (verdicts
unchanged in every cell across the bracket).

### 1. Base rates and the proximity number (the deliverable)

Per support pivot, 10-td window, share of 249 episodes (0.5×ADR band):

| pivot | never in zone | near-miss (no touch) | touched+reclaimed | touched+dead |
|---|---|---|---|---|
| **EP-day low** | 22.5% | **10.0%** | 30.9% | 36.5% |
| EP-day close | 2.0% | 3.2% | 39.0% | 55.8% |
| prior-day high | 46.2% | 8.4% | 21.7% | 23.7% |
| 10-day MA | 22.5% | 8.8% | 30.1% | 38.6% |

- **The proximity model's incremental population at the EP-day low is 25 of 249 episodes
  (10.0%; 7.2% at the tighter 0.25×ADR band)** — real, and invisible to any hard limit.
- **But their forward outcomes are unremarkable:** 20-day MFE median +1.8×ADR, p90 +4.4,
  **0 of 21 measurable ≥8×ADR** — against +1.7 / 2.7% for touched-and-reclaimed and
  **+2.6 / 10.7% ≥8×ADR for names that never came near the low at all**. The INTC shape
  (near-miss → monster) did not recur in this cohort. n=21–25: thin, stated, and the
  direction is consistent across all four support pivots (near-miss ≥8×ADR: 0%, 0%, 5.3%,
  0%).
- The shallow-pullback finding matches the SSoT T1 table independently: strength that
  never tests the EP-day low is the tail carrier, on a different cohort and metric.
- More than a third of all alert episodes (36.5%) CLOSE below the EP-day low within 10
  days — the "EP failed" class; 55.8% close below the EP-day close pivot.

### 2. The ladder grid (declined names, cons seq; sum / median / per-trade, n)

| cell | fires (base rate) | sum R | sum ADR | med R | verdict |
|---|---|---|---|---|---|
| **EPL touch-reclaim — PRIMARY** | 64/249 (26%) | **+6.09** (n=55) | +4.79 | −0.38 | positive ONLY via TE (+10.00R, a $5.51 stock); **ex-TE −3.91R / −0.72 ADR**; margin < sim optimism |
| EPC touch-reclaim | 83/249 (33%) | −18.68 (n=71) | −20.43 | −0.68 | negative both units |
| PDH touch-reclaim | 42/249 (17%) | −15.18 (n=35) | −10.83 | −0.93 | negative both units |
| MA10 touch-reclaim | 59/249 (24%) | +15.10 (n=46) | +8.36 | −0.13 | the other positive cell; **ex-TE +5.10R / +2.85 ADR (+0.11/+0.06 per trade)** — inside the optimism band |
| EPL zone (0.5×ADR) | 114/249 (46%) | −16.89 (n=98) | −14.84 | −1.00 | negative; wide cons↔opt spread (−16.9→−0.9) = ambiguity-heavy |
| EPC zone | 104/249 (42%) | −29.08 (n=87) | −30.55 | −1.00 | worst cell |
| PDH zone | 80/249 (32%) | −21.32 (n=65) | −14.05 | −0.77 | negative both units |
| MA10 zone | 122/249 (49%) | −10.76 (n=101) | −11.76 | −0.60 | negative; fires on half of everything — not selective |
| EPH breakout | 156/249 (63%) | −13.65 (n=132) | −21.86 | −0.30 | fires on 63% (not selective); median stop 11.3% — the wide-stop R-mirage; ADR-negative deep |

ENTERED-names columns (n=7–24 per cell): every cell −5.8…+4.9R, medians ≤ −0.03; the
primary fires on only 9 of 39 entered episodes for +0.35R — **a mechanical second-look
rule does not systematically rescue our stopped-out names** (the #572 re-entry finding,
reproduced from the other side). Live realized on those 39: −26.96R — but that is
era-mixed real fills vs a uniform sim policy; not a paired comparison.

- **Tail shape, primary cell (all 64):** p90 +1.19R, max +10.00R, ≥+2R: 3 of 64; in ADR
  ≥+2: 6. The tail exists but is thin and one name deep.
- **Sim optimism bound (the #572 calibration, same engine, real entries):** +0.41R per
  trade. Primary +0.11, MA10 +0.33 (+0.11 ex-TE) — **no cell clears it.**
- **Era slices, primary:** A +8.00R (n=50) · B −1.56R (n=14) · **C n=0 — not readable**
  (era C began 08-17, the data edge; nothing here describes the bracket running today).
  Tier: HIGH +15.53R (n=39; +0.15/trade ex-TE) vs MODERATE+none −9.09R (n=25).
- 8 of 64 primary positions open at the horizon (marked to 08-17 close), NET among them.

### 3. Primary-cell alternatives (pre-registered; side by side; NEVER best-of)

| variant | fires | sum R | sum ADR | med R |
|---|---|---|---|---|
| **PRIMARY** (W10, next-open) | 64 | +6.44 | +8.48 | −0.47 |
| W5 | 60 | +5.04 | +7.92 | −0.51 |
| W20 | 67 | +7.45 | +10.16 | −0.38 |
| LENIENT (reclaim any session) | 104 | +24.01 | +30.11 | −0.32 |
| CLOSE-ENTRY (untradeable bound) | 75 | +3.71 | +8.41 | −0.55 |

(These tables pool declined+entered — the alternatives block is a definition-sensitivity
read, not a performance pick.) Window width barely matters (W5≈W10≈W20) — robustness, not
tuning. The LENIENT lane is the only one that looks different: +24R / +30 ADR over 104
fires (+0.23/trade; ex-TE +0.14) — still tail-thin, still under a 2× margin over the
optimism bound, and it fires on 42% of episodes (half again less selective). It is
REPORTED, not promoted: it is also the definition the SSoT invalidation finding argues
against (multi-day submersion below the EP low = an ordinary candidate, not a strong one).
The idealized close-entry bound shows the next-open lag costs little (+3.7 vs +6.4 — the
lag is not where the money is).

### 4. NET, as one member of the cohort

The primary cell catches NET exactly as the operator described: signal 08-10 (low 290.49
undercut 295.89, closed 310.59 above), entry 08-11 at the open 307.60, stop 290.49 (5.6%).
The stop has never been threatened (lowest low since: 295.50). As of the 08-17 data edge
the position marks **−0.03R / −0.04 ADR, still open** — its best excursion so far was
+1.4R (08-13 high 332.22), never reaching the +2R partial. **NET is currently a
flat-but-alive trade, not a winner** — the case that motivated the test sits near the
middle of its own cohort's distribution, which is exactly why one case is never the
evidence.

### 5. The 620 prerequisite, costed (measured, not built)

A proximity+620 replay needs minute bars for **583 distinct approach/entry ticker-days; 9
already exist in `mi_intraday_bars`; 574 need a targeted Polygon minute pull** (one bars
request per ticker-day, $0 marginal under the current subscription, ~rate-limit-bound
runtime). Cheap, but it is the gate between this daily-bar read and any test of the
operator's actual trigger — the daily close-above-pivot proxy used here is NOT the 620
turn, and nothing in this doc measures the 620.

### What this read cannot see (stated)

- The operator's real entry is an intraday 620 turn near a pivot; every entry here is a
  daily-bar proxy (next-session open). If the 620's timing edge is real, every cell here
  understates it — symmetric across cells, but not across arms (zone arms suffer most).
- Right-censoring: 79 of 249 windows truncated; era C empty; 8 primary positions
  (incl. NET, VOYG, KTOS) open at the horizon. The probe is $0-repeatable when the August
  cohort matures (~mid-September).
- Alert-day universe only; no slippage/borrow; ADR from a 20-day window before the alert.

### The fork (his to rule — entry discipline is THE LINE; this doc decides nothing)

1. **No shadow arm now** (recommended): no cell beats the simulator's own measured
  optimism; the one positive is one $5.51 name deep. Re-run the probe free when the
  August cohort matures; the 79 censored windows are a third of the cohort.
2. If he wants the 620/proximity question answered properly, the concrete next step is
  the 574-ticker-day minute pull (this pass costed it; it was not run) — that tests HIS
  trigger instead of a daily proxy, and it is the only arm of this architecture this
  read could not price.

---

## Appendix — probe run

Full output: `python3 scripts/probes/pivot_ladder_562.py --data-dir <capture>` (capture
CSVs + q_*_562.sql in the session scratchpad; output archived at `ladder_562_out.txt`
beside them). Spot verification performed against raw daily bars: TE +10.00R chain
(05-13 U&R, 05-14 entry 5.51, 05-18 gap-partial 6.70, 06-05 trail exit 9.43) and the NET
row reproduce hand-computed; dedup audit found exactly the one absorbable re-alert pair.
