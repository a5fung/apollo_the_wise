# Liquidity composite: indicator set and composite read (PRE-REGISTERED 2026-11-22, before any outcome is read)

Status: **registration, not a finding and not an owner.** Nothing in this doc has been measured. It fixes the candidate indicators, the rule that picks among them, the composite rule and the pass bar, so a builder can run it with no open choice. It replaces §3 (the four-leg composite) and the "fail = do not show" line of §5 in `docs/analysis/market_liquidity_research_2026-11-22.md`; that draft was never computed, so nothing is lost.

⚖ **THE LINE:** this is a display and context read for his own market read. It gates no entry, changes no sizing, and does not feed the regime score or `ep_threshold`. Any such use is his decision under `docs/setups/CHANGE_PROCESS.md`. Nothing was flipped.

Tags in square brackets say where each element came from: **[A]** practitioner design, **[B]** quant design, **[C]** trader-use design, **[J]** added or changed when the three were judged.

## Summary for the operator

- **One rule for every indicator, and it is the read you already use:** an indicator says "tight" when it is on the tight side of its 20-day average and its 20-day is on the tight side of its 50-day (Caruso's JNK read, applied to all of them).
- **17 candidates across six groups** (credit, Fed and money, rates, dollar, metals, risk appetite) are cut to at most 12 (two per group) by a fixed rule that never looks at what the market did next; your two seeds (JNK, gold/silver) stay on screen whatever the rule decides.
- **The composite is a count:** each group votes tight, flat or easy; the screen always shows the count ("4 of 6 groups tight") and every indicator's dot.
- **The one word (Draining / Neutral / Easing) appears only if it passes a test on 2016-2024:** it must match known history, mark roughly 1.5 times more 10% small-cap drops in the next three months, and add something beyond SPY's trend, VIX and breadth. With only four or five real stress periods in those years, "cannot tell" is a likely result, and then the dots and the count ship without the word.
- critic: **the test is now stricter** (it must also beat IWM's own trend and the plain 20/50-day reads of SPY, IWM, VIX and breadth, and beat a timing-shuffle check), which makes "cannot tell" or a fail more likely still; the dots and count ship either way.
- **Action for you: three calls, none blocking the build** (§10): start the daily junk-spread snapshot now, whether the live screen may show 2025-26 history, and the go to ship any screen (critic: §10 also lists opening the 2025-26 holdout, and call 2 now includes how a launch-day screen gets its first 50 days).

## Method and population

- **Method:** three independent designs (practitioner, quant, trader use) were scored and merged on 2026-11-22. Only data coverage was probed (first and last dates, column names). No forward return, drawdown, EP outcome or breakout outcome was read to write this.
- **Population, legs and selection:** every US trading session 2016-01-04 → 2024-12-31 (about 2,264 sessions, n printed by the build), from Alpaca daily ETF bars, keyless FRED and the local daily closes. States start after a 50-session warm-up (about 2016-03-15).
- **Population, validation:** state days from the first session the rebuilt breadth baseline exists (about 2017-01-18) to the last session whose 63-session forward window ends by 2024-12-31 (about 2024-09-27); roughly 1,930 sessions, n printed by the build.
- **Population, momentum check:** the EP event list of `docs/analysis/ep_winner_study_prereg_2026-11-21.md`, n = 4,665 events 2016-02-02 → 2024-09-30, of which 554 (11.9%, n = 4,665) are big winners; and the breakout replay trades 2017-03 → 2021-12 and 2022-03 → 2024-09 (n printed at build).
- **Era:** this is a market-level read, so no Apollo rule era applies to the legs. The EP and breakout populations are replays under one rule set each (their own docs), never stored live trade rows.
- **Every percentage below is a pre-registered bar, not a result,** unless it carries an n. Every result table the build writes prints n beside each percentage.
- **Sealed years (#710):** 2025-26 is never read. See §8.

## 1. His goal (quoted)

- 11-22: *"I've been looking to add market liquidity along with market breath but don't have a sure fire way to look at it ... There's a thousand other things to look at, bonds, interest rate, yields comparison, Fed action, market dynamics, etc, so this needs full research"*
- 11-22: *"Liquidity is not just for EP, it's indicator I want to see along with market breadth for me own use as well. On JNK, I see Caruso look at it vs 20d as well, and it's trend. Another indicator I've seen is gold/silver ratio, rising is tighter monetary condition, dropping opposite"*
- 11-22: *"Before building, I want to find the right set of indicatiors and for to build a composite read"*

**The decision this serves:** which indicators go on his liquidity screen beside breadth, and whether a single composite word has earned a place on it. **What would change it:** the word is shown only if §5 passes; the indicator rows and the count ship either way (his §0 ruling in the research doc: it is a display).

**Stated goal for the composite (written before data):** when the read says Draining, the next one to three months carry clearly more downside risk for the small-cap, high-momentum side of the market than when it does not, and it says so by more than SPY's trend, VIX or breadth already show.

## 2. How the three designs scored

Scores are 1 (weak) to 5 (strong); for overfitting risk, 5 = lowest risk.

| Design | Channel coverage | Simple / explainable | Testable on $0 data | Overfitting risk | Fit to his goal | Total (of 25) |
|---|---|---|---|---|---|---|
| A practitioner | 5 | 5 | 4 | 4 | 5 | **23** |
| C trader use | 4 | 4 | 4 | 3 | 4 | 19 |
| B quant | 5 | 2 | 3 | 3 | 3 | 16 |

- **A is the base.** Its one leg rule is his own JNK read applied everywhere, the dot on screen and the vote are the same read, and a 50-session warm-up keeps 2016 and all of 2018.
- **B loses on fit and simplicity.** A year of history goes to its 252-day warm-up, it has seven frozen parameters he cannot check by eye, and its evidence rank puts his gold/silver seed 13th of 16. Its validation discipline is the strongest of the three and is grafted.
- **C loses on two points.** Its vote (50-day plus 20-day slope) is a different read from the seed tile beside it, and its 3 → 5 → 8 confirmation ladder is a tuning path. Its trader-use tests (timing, recovery, press as well as defend) are grafted.

| Taken from | Element |
|---|---|
| A | leg rule; six channels and the candidate list; outcome-blind eligibility and redundancy; channel-mean composite with thresholds scaled by the number of live channels; quarter-block bootstrap; "legs ship whatever happens" |
| B | tail statistic (frequency of a 10% drawdown) instead of a mean gap; numeric episode bars; the lagged re-run and "coincident" label; "warns while VIX is quiet"; selection log committed before outcomes; stress indices as benchmarks, never legs; separate job and table |
| C | 2-year minus funds rate and ARKK/QQQ as candidates; vote-agreement redundancy test; mechanical episode onset, lead and recovery; press must work as well as defend; overall Draining share band; survivorship check on the breadth universe; fast dot per leg; one-line Telegram form |
| J (judge) | one sign convention; STLFSI4 moved to display-only; a single JNK history rule; measured dividend tolerance; four added episode rows; the count always shows and only the word is conditional; flicker as a fixed outcome-blind gate with no ladder; the holdout rule; cut-and-assert on every file |

Rejected, with the reason: B's robust z-scores (warm-up cost, not checkable by eye); C's confirmation ladder (tuning path); C's "one instrument per leg" rule (replaced by the measured redundancy test, shared instruments are reported); the Amihud series as a leg (kept as a separate stand-alone test, §5.5, so the academic question gets its own answer and the composite does not depend on universe bars being in prod); TLT and TLT realised volatility (the rates channel already has two cleaner legs; shown on the display strip only).

## 3. Candidate set (17 legs, six channels)

Conventions, fixed [A][J]:
- **X is the series oriented so that UP = TIGHTER.** A vote of +1 is tight, −1 is easy. Every table and threshold in this doc uses this one convention.
- ETF legs use dividend-adjusted (total-return) closes; ratios use adjusted numerator and denominator (§6).
- "Usable from" is the first close at which the value may enter a state (publication lag, §6).

| ID | Channel (his words) | Name | X (up = tighter) | Tighter when | Source | History | Usable from | From |
|---|---|---|---|---|---|---|---|---|
| C1 | Credit (bonds) | Junk bonds, his seed | −JNK | junk bonds fall | Alpaca (HYG if §6 check fails) | 2016 | same day | A |
| C2 | Credit (yield comparison) | Junk vs Treasuries | −(HYG / IEI) | junk lags Treasuries | Alpaca | 2016 | same day | A |
| C3 | Credit (yield comparison) | Baa corporate spread | BAA10Y | spread widens | FRED | 1986 | next session | A |
| F1 | Fed and money (Fed action) | Net liquidity | −(WALCL − WTREGEN − RRPONTSYD × 1000), $ millions | net liquidity falls | FRED | 2003 | Friday for the Wednesday level; RRP same day | A |
| F2 | Fed and money (Fed action) | Fed funds rate | DFF | funds rate rises | FRED | 1954 | next session | A |
| F3 | Fed and money (Fed action) | Hikes or cuts priced | DGS2 − DFF | 2-year rises above the funds rate | FRED | 1976 | next session | B, C |
| R1 | Rates (interest rate) | 10-year real yield | DFII10 | real yield rises | FRED | 2003 | next session | A |
| R2 | Rates (interest rate) | 2-year yield | DGS2 | 2-year yield rises | FRED | 1976 | next session | A |
| D1 | Dollar | Dollar fund | UUP | dollar rises | Alpaca | 2016 | same day | A |
| D2 | Dollar | Broad dollar index | DTWEXBGS | dollar rises | FRED | 2006 | observation date + 7 calendar days | A |
| D3 | Dollar | Yen (carry unwind) | FXY | yen rises | Alpaca | 2016 | same day | A |
| M1 | Metals | Gold/silver ratio, his seed | GLD / SLV | ratio rises (his note) | Alpaca | 2016 | same day | A |
| M2 | Metals and commodities | Copper vs gold | −(CPER / GLD) | copper lags gold | Alpaca | 2016 | same day | A |
| K1 | Risk appetite (market dynamics) | Small vs large | −(IWM / SPY) | small caps lag | Alpaca | 2016 | same day | A |
| K2 | Risk appetite (market dynamics) | High beta vs low volatility | −(SPHB / SPLV) | high beta lags | Alpaca | 2016 | same day | A |
| K3 | Risk appetite (market dynamics) | Regional banks vs market | −(KRE / SPY) | banks lag | Alpaca | 2016 | same day | A |
| K5 | Risk appetite (market dynamics) | Speculative growth | −(ARKK / QQQ) | speculative growth lags | Alpaca | 2016 | same day | C |

All 17 legs are computed for the whole history whether or not selection keeps them; the episode checks in §5.2 read named legs even when they are not in the composite.

**Display-only, never voting** (reason) [A][B][C][J]:
- Junk-bond spread BAMLH0A0HYM2 and its 20-day change: free history starts 2023-11-21 and the licence limits display; internal only, and only with his go (§10).
- STLFSI4, NFCI, ANFCI, OFR stress index, excess bond premium: revised after release and built partly from equity and volatility inputs; they are benchmarks beside the read. [J] moves STLFSI4 here: design A let it vote while barring NFCI for the same defect.
- 10-year minus 2-year curve: direction is ambiguous. SOFR minus IORB: history too short. Reserves (WRESBAL): the same quantity as F1. TLT and TLT 20-day realised volatility, VIX: context strip.
- Out of reach at $0 or too slow: MOVE, Howell global liquidity, M2, margin debt.
- critic: **Funding stress (repo / commercial paper) is a whole channel with no voting leg, and cannot get one cleanly at $0:** TEDRATE ends 2022-01-21; 3-month financial commercial paper (DCPF3M) minus the T-bill (DTB3) is blank on 540 of 2,348 FRED rows 2016-24 (about 1 day in 5 on top of holidays); SOFR starts 2018-04-03 and IORB 2021-07-29. It stays out of the vote and is named in §9; SOFR − IORB stays on the display strip.
- critic: **Bitcoin (FRED CBBTCUSD, from 2014-12-01)** is a common practitioner liquidity gauge; not added as a leg (prints on weekends, and it would enter after the three designs were scored). Display-strip candidate only.

**Always-on seed tiles** (his ruling, whatever selection decides) [A]: JNK vs its 20-day and 50-day, with the 20-day slope; gold/silver ratio vs its 20-day and 50-day.

## 4. Rules (all fixed now)

### 4.1 Leg rule: one rule for every leg [A]
- MA20 and MA50 = simple averages of X over the last 20 and 50 sessions, on the trading-day grid after lags and forward-fill.
- **TIGHT (+1):** X > MA20 and MA20 > MA50.
- **EASY (−1):** X < MA20 and MA20 < MA50.
- **Otherwise 0.** Any tie counts as 0.
- Fast dot, display only [C]: X vs MA20.

### 4.2 Selection rule: outcome-blind [A, with C and J grafts]
Inputs allowed: leg-versus-leg facts only. No forward return, drawdown, breadth, EP or breakout column may be loaded by the selection script. Halves: H1 = first state → 2020-12-31, H2 = 2021-01-04 → 2024-12-31.

1. **Eligibility, must pass in BOTH halves** [A]:
   - E1: the leg's vote is non-missing (X, MA20 and MA50 all exist; a vote of 0 counts) on at least 95% of sessions.
   - critic: E1 is measured on FRESH values, before forward-fill (after forward-fill it cannot fail for a FRED leg). One staleness rule for every source (it replaces any other tolerance): a session's value is fresh when the newest observation that is USABLE by that session (§3 "usable from" already applied) has an observation date at most 7 calendar days earlier for a daily series and at most 14 for the weekly ones (WALCL, WTREGEN); an ETF close is fresh when it is that session's own bar or a carried close at most 3 sessions old. F1 is fresh only when all three of its parts are. A stale value is a missing vote. Coverage probed 2026-11-22: the daily FRED legs (incl. DTWEXBGS) are blank only on holidays (98-106 of 2,348 rows); WALCL and WTREGEN, weekly, have no gaps.
   - E2: share of TIGHT days and share of EASY days are each between 10% and 70%.
   - E3: median run length of the three-state vote is at least 5 sessions.
   - A failure sends the leg to display-only. Stated in advance [J]: F2 (the funds rate moves in steps and sits flat for long stretches) is expected to fail E2; F3 is in the list for that case.
2. **Redundancy** [A][C][J]:
   - Trend gap g is computed on the raw, un-negated series P and then signed: ratio form g = sign × (MA20(P) / MA50(P) − 1) for C1, C2, F1, D1, D2, D3, M1, M2, K1, K2, K3, K5; difference form g = sign × (MA20(P) − MA50(P)) for C3, F2, F3, R1, R2. sign = +1 where a rising P is tighter, −1 where a falling P is tighter.
   - Two legs are redundant if EITHER test holds in BOTH halves: (i) the Pearson correlation of their g is at least 0.80 for a same-channel pair or 0.85 for a cross-channel pair; (ii) their votes agree on at least 85% of the sessions where both are non-zero.
   - Order, deterministic: walk the eligible legs in priority order (item 3) and keep each one unless it is redundant with a leg already kept.
3. **Priority, breaks every tie** [A, two inserted by J]: C1, M1, F1, F2, R1, D1, K1, C2, C3, R2, F3, K5, D3, M2, K2, K3, D2. (His named seeds and asks first, then longer clean history, then fewer steps.)
4. **Per channel** [A]: keep the top 2 survivors by priority. critic: the cap is applied DURING the item-2 walk, not after it: a leg whose channel already holds 2 kept legs is skipped and never becomes a "leg already kept", so it cannot prune a leg in another channel and then be dropped itself. A channel with no survivor is shown as "uncovered" and the composite runs on K < 6 channels. If fewer than 4 channels survive, no composite is built and the result is reported.
   - critic, stated in advance: F3 (2-year minus funds rate) tracks R2 (2-year) whenever the funds rate is flat, and R2 is walked first, so F3 is likely pruned; with F2 expected to fail E2, the Fed and money channel may end as F1 alone. That is a recorded outcome, not a reason to reorder.
5. **A pruned seed** (JNK or gold/silver) is reported as pruned; its tile stays.
6. **Sign and lag audit, a build check and not selection** [A]: a leg that reads EASY on most sessions of both 2018-12-03 → 12-21 and 2020-03-09 → 03-20 gets its sign and lag audited. If the code is right, the leg stays.
7. **Freeze** [B]: commit the kept list, the E1-E3 table per half (with n sessions), both correlation matrices, the vote-agreement table and the pruning log BEFORE any outcome file is opened.

### 4.3 Composite rule [A, J]
- **Channel score** c = mean of its kept legs' votes (−1, −0.5, 0, +0.5, +1). A channel is "tight" when c > 0, "easy" when c < 0.
- **Composite** S = sum of c over the K live channels (−K … +K).
- critic, closing three forks: (1) K = the number of channels holding at least one kept leg, fixed at the freeze; it never varies by day. (2) A kept leg with no vote on a day (no fresh value inside the forward-fill limit, §6.3) votes 0 and stays in its channel's mean; the mean is never re-weighted over the legs that happen to be present. (3) The state starts NEUTRAL on the first state session; the "3 consecutive closes" counters read the last three closes regardless of the current state; each close is checked in this order: from DRAINING, the EASING entry condition first, then the exit to NEUTRAL; from EASING, the mirror; from NEUTRAL, DRAINING entry then EASING entry (both cannot hold at once).
- **Thresholds scale with K:** enter T = K / 3, exit K / 6 (for K = 6: enter 2, exit 1).
- **State machine, evaluated each close:**
  - Enter DRAINING when S ≥ +T on 3 consecutive closes. Leave to NEUTRAL when S ≤ +K/6 on 3 consecutive closes.
  - Enter EASING when S ≤ −T on 3 consecutive closes. Leave to NEUTRAL when S ≥ −K/6 on 3 consecutive closes.
  - A direct flip needs the opposite entry condition for 3 closes. Otherwise NEUTRAL.
- **Always shown, whatever validation says** [J]: "N of K groups tight" and S. Only the WORD is conditional (§5.6).
- Nothing here is tuned after the freeze. Share of days per state, changes per year, median dwell and each channel's share of Draining days are measured and reported.

### 4.4 The screen (built only with his go, §10) [A][C]
- Line 1: the word (if earned), "4 of 6 groups tight", S, days in state, "changed from X on date".
- One row per leg: name, dot (tight / flat / easy), days in the current vote, fast dot, the reason in plain words ("JNK below 20-day, 20-day below 50-day").
- Seed tiles; display strip (junk spread and 20-day change, VIX, NFCI, curve, SOFR − IORB, Amihud state).
- Everything on one screen, nothing behind a tap.
- Telegram form, one monospace line: `Liquidity: 4 of 6 tight (credit, real yield, dollar, small caps)`.
- Storage: its own job and table (`mi_liquidity_state`), never inside `regime.py` [B].
- Footer: "market-price and Fed read; partly reflects the market itself".

## 5. Validation (one pass, after the freeze)

Order is fixed: W0 and W1 are run and written down BEFORE any forward return is loaded. Then W2 and W3 once. The word needs W0, W1, W2 and W3. Bootstrap seed 20261122.

### 5.1 W0: flicker (outcome-blind) [C, J]
- At most 8 state changes per calendar year (median over 2017-2023) and a median dwell of at least 10 sessions.
- Draining on 10% to 35% of validation sessions [C].
- Fail → no word. No ladder, no retune.

### 5.2 W1: episodes expected in advance
Written before any data was read. critic: a build-bug audit may change only code that disagrees with this doc's text; every audit change is logged with the W0 and W1 tables before and after it, and W0 is re-run. A miss is first audited as a build bug; a miss that stands is recorded as a miss and never licenses retuning. "Share" = share of sessions in the window, n = sessions in the window, printed.

| # | Type | Window | SCORED (this alone decides the row) | Context, not scored | From |
|---|---|---|---|---|---|
| S1 | must drain | 2018-10-10 → 12-24 | Draining share ≥ 50% | credit, risk appetite, Fed and money, dollar tight; rates tight in October then easing; out of Draining by 2019-02-28 | A, B, C |
| S2 | must drain | 2020-02-28 → 04-03 | Draining share ≥ 50% | credit, risk appetite, metals tight; Fed and money easy from mid-March; Neutral or Easing by 2020-06-30 | A, B, C |
| S3 | must drain | 2022-01-18 → 10-14 | Draining share ≥ 50% | rates, dollar, Fed and money tight; credit tight on and off; Neutral mid-July → mid-August | A, B, C |
| S4 | must drain | 2023-08-15 → 10-27 | Draining share ≥ 40% | rates, dollar and small caps tight; credit mildly tight | J |
| L1 | leg only | 2023-03-10 → 03-24 (bank failures) | K3 banks TIGHT share ≥ 80% AND Draining ≤ 10 sessions | Fed and money easy | A, B, C |
| L2 | leg only | 2024-08-01 → 08-09 (yen carry) | D3 yen TIGHT share ≥ 80% AND Draining ≤ 5 sessions | credit quiet | A, B, C |
| L3 | leg only | 2018-02-05 → 02-16 (volatility shock) | R1 real yield TIGHT share ≥ 60% AND Draining ≤ 5 sessions | credit dips briefly | J |
| L4 | leg only | 2021-02-16 → 03-19 (yield spike, growth sold) | R1 real yield TIGHT share ≥ 70% AND Draining ≤ 10 sessions | speculative growth turns tight in March | J |
| Q1 | calm | 2017-01-18 → 12-29 | Draining share ≤ 10% | | A, B, C |
| Q2 | calm | 2019-01-07 → 04-30 (after the Fed pivot) | Draining share ≤ 15% | | J |
| Q3 | calm | 2019-07-01 → 2020-01-31 (cuts, bill purchases) | Draining share ≤ 15% | | A, B, C |
| Q4 | calm | 2020-06-01 → 2021-01-29 | Easing share ≥ 50% AND Draining share ≤ 10% | | A, C |
| Q5 | calm | 2023-11-01 → 2024-03-28 (pivot rally) | Easing share ≥ 40% AND Draining share ≤ 10% | | A, B, C |

- **Bar:** at least 3 of 4 "must drain" rows, at least 3 of 4 "leg only" rows, at least 4 of 5 "calm" rows.
- critic: **W1 and W2 are not independent tests.** The four must-drain windows are the known small-cap selloffs, so a W1 pass largely implies W2's ratio; together they rest on about four independent stress periods, not on about 1,930 sessions.
- **Known design risk, stated in advance [J]:** in March 2020 yields collapsed and the Fed cut, so the rates and Fed channels will likely vote easy while credit, small caps and metals vote tight; S may sit just under the entry line. If S2 misses for that reason it is a recorded miss, not a reason to change the rule.

### 5.3 W2: forward risk (the tail, one statistic) [B, C]
- **Statistic:** share of days on which IWM's lowest adjusted close over the next 63 sessions is at least 10% below that day's close. Compared: DRAINING days vs all other days (Neutral + Easing).
- **Bar, all of:**
  - (a) ratio of the two shares is at least 1.5;
  - (b) the 95% interval of the difference from a calendar-quarter block bootstrap (10,000 resamples) excludes 0 [A]; critic: a resample with no Draining day or no other day is dropped and counted; more than 5% dropped → "cannot tell";
  - (b2) critic: **circular-shift null**, because 63-session windows straddle the quarter blocks and the bootstrap interval is too narrow: shift the whole state series circularly over the validation window by each offset from 126 sessions to (n − 126), recompute the ratio, and the observed ratio must exceed the 95th percentile of the shifted ratios. This keeps the state's own run structure and asks only whether its timing matters;
  - (c) ratio at least 1.2 in H1 and in H2 separately;
  - (d) press works too [C]: the share on EASING days is at or below the share on NEUTRAL days.
- critic: an **episode** is a run of 5 or more Draining (or Easing) sessions, and runs separated by fewer than 63 sessions are merged into one episode, so one stress period that drops out and re-enters counts once. An episode belongs to the half that holds its first session (this keeps the Q4 Easing period, 2020-06 → 2021-01, in H1 only; if a builder finds that choice ambiguous for a given episode, it goes to whichever half makes the floor HARDER to meet).
- **Floor [J]:** Draining needs at least 2 episodes (runs of 5 or more sessions) and 60 sessions in each half, and at least 4 episodes pooled; Easing the same. Otherwise the result is "cannot tell", which is not a pass. (Designs A and B asked for 3 per half; the §5.2 table itself only requires two Draining periods before 2021, so 3 would have pre-decided "cannot tell". Set before any data.) critic, an expectation and not a result: with merged episodes, each half most likely holds only its two must-drain periods (S1 and S2 before 2021, S3 and S4 after), so a period that never reaches a 5-session run would likely leave that half "cannot tell", and so the word. Draining outside the four windows also counts toward the floor.
- **Reported, not judged** (each with n): SPY and QQQ; the 21-session horizon (month blocks); mean and median forward return; share of days with a 10% forward GAIN (the upside tail).

### 5.4 W3: adds to what he already sees [A, B, C]
Baselines on the same window, each flagged on the same number of days k as Draining, by ranking its own variable:
- B1 SPY trend: lowest SPY / MA50 − 1.
- B2 VIX alone: highest VIXCLS (FRED; never the local file, which starts 2021-06 and runs into sealed years).
- B3 breadth: lowest 10-day mean of (new 252-session highs − new lows) / N, over common stock (`cb702_sic.psv` last column `CS`), price ≥ $5, 20-day average dollar volume ≥ $5M. Print N per year; the `CS` list is dated 2026-10-16, so the build states whether the universe is survivors-only [C].

- critic: **B4 IWM trend:** lowest IWM / MA50 − 1 (the outcome is IWM, and leg K1 already reads IWM).
- critic: **Same-rule forms.** The k-matched flags above take the most extreme days over the whole sample, which cluster at crash lows after the damage, and so are easy to beat on a forward-drawdown statistic. Each of B1, B2, B3 and B4 is ALSO read with the §4.1 leg rule (SPY falling, IWM falling, VIX rising, breadth falling: X > MA20 and MA20 > MA50), flagged on every TIGHT day. A same-rule baseline with fewer than 60 flagged sessions in the window is reported with its n and not judged.

**Bar, all of:**
- (a) the composite's W2 ratio is at least B1's ratio; critic: and at least B4's, and at least the same-rule form of B1, B3 and B4 (VIX is judged in (b));
- (b) either it is at least B2's ratio, or its ratio is at least 1.3 on days when VIX is below its trailing 252-session median ("warns while VIX is quiet") [B]; critic: this escape covers BOTH VIX forms (k-matched and same-rule), so (a) does not judge VIX: the same-rule VIX comparison is judged here, with the same escape;
- (c) the composite's ratio is at least B3's ratio, AND within breadth < 0 days Draining vs the rest is at least 1.25 [C][J]. Fewer than 60 Draining sessions with breadth < 0 reads "cannot tell". The breadth ≥ 0 stratum is reported with its n and not judged, because Draining days with healthy breadth may be too few to judge at all.

**Reported, not judged:** overlap of Draining with the B3 flag (above 85% is flagged as "close to breadth by another name") [A]; the W2 ratio with the state lagged 5 and 10 sessions, and if it falls below 1.2 at 10 sessions the screen says "coincident" [B]; lead and recovery [C], using mechanical episodes (onset = first close with SPY at least 7% below its trailing 252-session closing high; low = the minimum close before SPY recovers to 3% below that high): sessions from the first Draining close in the 63 sessions before onset to onset, the same for B1, and sessions from the low to leaving Draining.

### 5.5 P2: momentum check (decides one label only) [A, B, C; research doc §5 Steps 1-3]
Run once, after W2 and W3, whatever they say. It never decides the word.
- **EP:** `scripts/probes/_ep_winner_study_1121/build/stage6_minutes/02b_events.tsv.gz`, n = 4,665 events before exclusions. Drop non-common-stock tickers (the `CS` flag; removes inverse, leveraged and volatility funds) and print n. State = the state at the close before E. Statistic: `big_winner` share over ALL remaining events, Draining vs the rest.
- **Breakout:** `~/apollo_data/cb702_pre/out/trades_pre_exitpb.tsv.gz` + `~/apollo_data/cb702/out/trades_discovery_exitpb.tsv.gz`, filter arm `pp`, entry `orh5`, K `tl`, C0 = 1, mature = 1, D ≤ 2024-09-30, and drop (and count) any trade whose exit date falls after 2024-12-31. `exit_session` and `sessions_held` are session counts, not dates: exit date = the session max(`exit_session`, `sessions_held`) + 1 sessions after `E` on the trading-day grid (the extra session is margin for the count's unknown base). State joined on D. Statistic: share with `realized_r` ≥ 10.
- **Bar, per setup:** Draining share at most two-thirds of the rest; month-block bootstrap 95% interval excludes 0; same sign in both eras; same sign and at least half the pooled gap within SPY above and below its 50-day; beats the k-matched B1 flag; survives the SPY 126-session realised-volatility top-third control. Fewer than 40 big winners in Draining → "cannot tell".
- **Amihud stand-alone** [A][B]: 20-day mean of the daily cross-sectional median of |return| / (close × volume) on the B3 universe, read with the §4.1 leg rule; the same EP and breakout statistic, tight vs not. Reported separately.
- R figures (mean, median, from `02b_rows`, the arm matching the live opening range in `docs/setups/magna53_ep.md`, mode PRIMARY) are secondary and never judged.

### 5.6 What each result means (fixed now)

| Result | What ships |
|---|---|
| Always | leg rows, seed tiles, "N of K groups tight", display strip |
| W0-W3 all pass | the word, labelled "tested 2016-24, unconfirmed on 2025-26" |
| Any of W0-W3 fails or "cannot tell" | no word on any surface; rows and count labelled "context, not validated" |
| P2 passes on a setup (and the word is shown) | the extra label "context for EPs" and/or "context for breakouts" |
| P2 fails | "market read only" |

- **Expected in advance [J]:** 2016-24 holds four or five real stress periods and the bar has many parts, so "cannot tell" or a narrow fail is the likely outcome. That is a result, not a reason to loosen the bar.
- No result licenses re-tuning a leg, a window or a threshold on 2016-24.

## 6. Data steps (builder, in order)

0. **Card preamble:** paste `docs/methodology/ANALYSIS_CARD_PREAMBLE.md` verbatim; capture `python scripts/live_rules.py` to a file once and read from it (only the live opening-range arm for the P2 secondary depends on it). Work in `scripts/probes/_liquidity_composite_1122/`. One Sonnet card, $0 data, every fetch saved to a file on the first run and never re-fetched.
1. **Do not start until this doc is committed** (the registration is the commit).
2. **Cut and assert, every source [B][C][J]:** the local `cb702` file and every FRED pull run into 2026. critic: so do the outcome files: `trades_discovery_exitpb.tsv.gz` holds 234 rows with D after 2024-12-31 (max D 2025-01-30, checked 2026-11-22 on the date column only); every trade and event file is cut on load with the same assert, before any filter. Cut each at 2024-12-31 on load and assert max(date) ≤ 2024-12-31 on every frame; fetch Alpaca with `end=2024-12-31`; forward windows require t + horizon ≤ 2024-12-31.
3. **ETF closes:** Alpaca daily bars, `adjustment=all`, 2016-01-04 → 2024-12-31, for JNK HYG IEI UUP FXY GLD SLV CPER IWM SPY QQQ SPHB SPLV KRE ARKK (and TLT for the strip). Local closes (`~/apollo_data/cb702_pre_v2` to 2022-06-30, `~/apollo_data/cb702` from 2021-09-27; headerless ticker,date,o,h,l,c,v; split- not dividend-adjusted) are the cross-check only.
   - **Adjustment check:** for HYG, adjusted / local raw must step only on ex-dates and drift 3% to 8% a year. critic: and the adjustment must be proportional (a constant factor between ex-dates), so later 2025-26 distributions scale history uniformly and leave every ratio and vote unchanged. If either fails, the build STOPS and reports; no fallback source is chosen inside the build (the earlier "issuer distribution history" fallback named no file and was a fork).
   - critic: **missing ETF bars** (local CPER lacks 47 of 1,635 sessions to 2022-06-30, ARKK 8): carry the last close forward at most 3 sessions; longer, the leg has no vote (votes 0 in its channel, counts against E1). FRED series follow the one staleness rule in §4.2 E1.
   - **JNK rule [J]:** local JNK starts 2019-05 (a reverse split, recalled, unchecked). Use Alpaca JNK if, in every calendar year 2016-2024, its daily return correlates at least 0.90 with HYG's and no single day differs from HYG by more than 3 percentage points. Otherwise C1 uses HYG for the whole history (no splice) and JNK appears only on the seed tile.
4. **FRED:** `https://fred.stlouisfed.org/graph/fredgraph.csv?id=<ID>&cosd=2000-01-01&coed=2024-12-31`, keyless. Apply the "usable from" lag of §3, then forward-fill onto the trading-day grid. Net liquidity units: WALCL and WTREGEN in $ millions, RRPONTSYD in $ billions.
5. **Dividend handling, the answer [J]:**
   - **Price-only is NOT acceptable for the bond, credit and dollar-fund legs (C1, C2, D1).** A fund paying about 5-6% a year in monthly distributions sits roughly 0.2% lower against its 20-day average and 0.6% lower against its 50-day in a price-only series, and its 20-day sits about 0.35% lower against its 50-day. Those are the same size as an ordinary day's move in junk bonds, so price-only leans those legs toward "tight" every day. UUP's year-end distributions (recalled, to be read from the adjusted series) create a one-day false drop.
   - **Price-only is acceptable for GLD/SLV, CPER/GLD and FXY** (no or negligible distributions) **and for the equity ratios** (the two sides' dividend yields differ by a fraction of a percent a year).
   - **Measured, not assumed:** the build reports, per ETF leg, the share of sessions (with n) on which the price-only vote differs from the adjusted vote. Up to 2% → a live job may use price-only closes for that leg; above 2% → adjusted closes are required live.
   - **Seed tiles** show the price chart (what he sees on his own screen) with the adjusted vote dot beside it, so a disagreement is visible.
6. **Selection (§4.2), then the freeze commit.** The selection script must not import or open any outcome file.
7. **Composite (§4.3), W0, W1** written to the result file. Then load forward closes and run W2, W3, P2 once.
8. **Result doc:** `docs/analysis/liquidity_composite_result_<date>.md`, passing `python scripts/check_analysis_doc.py <path>`, with n beside every percentage, the tail before any mean, and a "what this does not answer" section. Verify before reporting: recount every headline number from the saved frames by a second route.

## 7. What a builder may not decide
Nothing. Any ambiguity found during the build is written into the result doc as an ambiguity and resolved in the direction that makes the word HARDER to earn. No surface, schema, cron or deploy is part of this card (§10).

## 8. The sealed 2025-26 holdout (#710)
- No row dated after 2024-12-31 is read for selection, the composite, the episodes or any validation step.
- Any pass is discovery-grade until confirmed on 2025-26, and only the operator opens that data.
- **The confirm test is fixed now [J]:** the same frozen legs, rules and thresholds; the same W0, W2 and W3 bars; run once on 2025-01-02 → the last session with a full 63-session forward window; warm-up taken from 2024. Floor: at least 2 Draining episodes and 60 Draining sessions, otherwise "cannot tell". Pass → the "unconfirmed" label is removed. Fail → the word is removed. No retune in either case.
- A live screen needs each day's values going forward; whether it may also draw 2025-26 history (a one-year chart at launch is exactly the sealed period) is his call (§10).

## 9. What this does not answer
- **Whether the November 2026 selloff is a liquidity event:** 2025-26 is sealed; only a live screen, going forward, can show it. He expects momentum not to work in this bear phase, so a 2016-24 result is a baseline and not a verdict on today.
- **When the market bottoms or when a Fed pivot marks the low:** pivots were not reliable bottoms (2001, 2007-08); nothing here calls one.
- **Cause versus effect:** credit and risk-appetite legs fall WITH the market, so the read partly measures the market itself; W3 measures how much is left after trend, VIX and breadth, it does not prove a lead.
- **Anything firm from so few episodes:** 2016-24 holds four or five independent stress periods, and they differ in kind (rate-driven 2022, credit and funding 2020, banks 2023). A pass is weak evidence.
- **Caruso's actual rule:** his thresholds are unread (no transcript); this is built from his inputs, not a copy of his read.
- critic: **Funding stress (repo, commercial paper):** no voting leg; no clean $0 daily history for 2016-24 (§3).
- **Global liquidity, China, private credit, flows:** not covered. The true junk-bond spread before 2023-11 is not available free; the Baa spread stands in.
- **Regime breaks:** net liquidity may behave differently now that the reverse-repo balance is near zero; a mix of balance-sheet runoff with rate cuts can split the Fed and rates channels.
- **Single-stock outcomes:** a strong EP can work on a Draining day; this is market context only.
- **Whether it should gate EPs or breakouts or change sizing:** THE LINE, his call only. Exit questions belong to the periodic trade review (#720).
- **Whether the right set was found in an absolute sense:** selection here removes duplicates and dead legs without looking at outcomes; it does not rank legs by how well they predict, by design (that would be fitting on about five episodes).

## 10. His calls (the only open forks; none blocks the build)
1. **Start the daily junk-bond spread snapshot now?** FRED keeps three years and the history is lost each day it waits. Rec: yes, internal storage only.
2. **May the live screen draw 2025-26 history,** or only values from the day it launches? Rec: from launch day only, so the seal stays intact. critic: even "launch day only" needs the prior 50 sessions (2026, sealed) for the 50-day averages; the call is therefore (a) read 50 sessions of 2026 closes for warm-up only, never displayed or tested, or (b) show no dots or count for the first 50 sessions after launch.
3. **The go to ship** any screen, table, cron or Telegram line after the result is in. Rec: decide once the result doc exists.
4. **Opening the 2025-26 holdout** for the §8 confirm test: his, whenever #710 allows.

## Data facts checked 2026-11-22 (coverage only, no outcome)
- Local closes: `cb702_pre_v2` 2016-01-04 → 2022-06-30; `cb702` 2021-09-27 → 2026-10-16 (sealed rows present, hence step 2). UUP, ARKK, CPER present from 2016-01-04; JNK from 2019-05-06 only.
- `cb702_sic.psv`: 3,942 tickers, 3,642 flagged `CS`, dated 2026-10-16.
- Breakout trade file columns include `D`, `E`, `arm`, `entry`, `K`, `C0`, `mature`, `realized_r`, `sessions_held`, `exit_session`. EP events file columns include `era`, `ticker`, `E`, `big_winner`.
- FRED keyless endpoint and first dates: reported by the three designs' probes (BAA10Y, DFII10, DGS2, DFF, WALCL, WTREGEN, RRPONTSYD, DTWEXBGS, VIXCLS all reach back before 2016; BAMLH0A0HYM2 from 2023-11-21 only). critic: re-probed 2026-11-22 (first value): BAA10Y 1986-01-02, WALCL and WTREGEN 2002-12-18, RRPONTSYD 2003-02-07, DFF 1954-07-01, DGS2 1976-06-01, DFII10 2003-01-02, DTWEXBGS 2006-01-02, VIXCLS 1990-01-02, BAMLH0A0HYM2 2023-11-21, STLFSI4 1993-12-31, NFCI and ANFCI 1971-01-08, SOFR 2018-04-03, IORB 2021-07-29. All run into 2026 (hence §6.2). Units match §6.4 (WALCL 6,741,452 and WTREGEN 916,613 $ millions; RRPONTSYD 0.401 $ billions, 2026-11).
- critic, checked 2026-11-22 on rows ≤ 2024-12-31: all 16 ETFs (incl. TLT) are in the local files; `cb702_pre_v2` 1,635 sessions to 2022-06-30 except CPER 1,588 and ARKK 1,627; JNK 796 from 2019-05-06. The trading-day grid 2016-01-04 → 2024-12-31 has 2,264 sessions; the validation window 2017-01-18 → 2024-09-27 has 1,937. `cb702_sic.psv` has 3,942 tickers, 3,642 with last column `CS`. Breakout filter (pp, orh5, tl, C0 = 1, mature = 1) keeps 13,363 pre-file trades (D 2017-03-01 → 2021-12-31) and 8,984 discovery trades with D ≤ 2024-12-31 (from 2022-03-31), counts only. EP `big_winner` is E..E+60 sessions, so events to 2024-09-30 end inside 2024. The card preamble, `check_analysis_doc.py`, `live_rules.py` and `research_bars.py` exist.
- Alpaca `adjustment` is a supported request field in `agents/market_intelligence/broker/research_bars.py`; that `adjustment=all` is dividend-adjusted is NOT yet verified (step 3 checks it).

## 11. His rulings on §10 (2026-11-22, "yes on recs")
- Call 1: start the daily junk-bond spread snapshot now — yes (internal storage only).
- Call 2: the live screen may use 2025-26 prices for its averages and display; the TEST never reads them (the #710 seal is a research seal, not a display seal).
- Call 3 (run the test now): yes.

## 12. AMENDMENT — the leg vote is the TREND (20-day vs 50-day); price vs 20-day is a display dot (2026-11-22, his "go with rec"; written after the eligibility table was seen, BEFORE any outcome is read)
**What was seen (disclosed):** run 1 (`scripts/probes/_liquidity_1122/02_selection.txt`, freeze sha1 `2e5970a0…`, kept with its outputs) stopped at selection: 16 of 17 legs failed E3 (median run ≥ 5 sessions in both halves). Diagnosis (`build/legs_X.csv`, no outcome read): the price-vs-20-day part flips every 3-4 sessions in every leg, the 20-day-vs-50-day part runs 20-48 sessions, and the gate fails on SPY / QQQ / IWM themselves (rule median 4-5) — so E3 was unpassable for §4.1's rule class, a calibration defect of the gate, not a finding about the indicators. No forward return, breadth, EP or breakout value has been computed.
**The rule from a principle (his note "vs 20d as well, and its trend"; the trend is the durable read, the 20-day the early warning):**
- **§4.1 leg vote (replaces the combined rule):** tight (+1) when the 20-day average of X is above its 50-day average, easy (−1) when below, flat (0) only on an exact tie or missing data. A two-state trend vote.
- **Display only (never votes):** each leg's fast dot = X vs its 20-day average, shown beside the vote as the early warning; his two seed tiles keep JNK/HYG vs 20-day and 50-day and the 20-day slope.
- **§4.2 selection gates, unchanged in wording, now read on the trend vote:** E1 coverage; E2 tight share 10-70% in both halves; E3 median run ≥ 5 sessions in both halves; redundancy by trend-gap correlation or 85% vote agreement; fixed priority order; ≤ 2 legs per channel; ≥ 4 channels or no composite.
- **§4.3 composite, unchanged:** channel score = mean of its legs' votes; sum over K channels; Draining when the sum ≥ +K/3 for 3 consecutive closes, exits below +K/6; Easing mirrors. With two-state votes most days carry a non-zero score, so Neutral is rarer than the draft assumed — disclosed now, not tuned.
- **§5 validation, unchanged:** W0 flicker (≤ 8 word changes a year, median dwell ≥ 10 sessions, Draining 10-35% of days), W1 episodes as written in advance, W2 forward risk, W3 baselines, P2. If W0's Draining band fails under the two-state vote, that is a fail reported as such, never a retune.
- **Run once more** in the same folder with a new freeze file and hash; run 1 stays on disk.

## RESULT — run 2 under §12 (2026-11-22; one run; independent recount MATCH on every vote, state, row and baseline; `scripts/probes/_liquidity_1122/r2_*`, `build_r2/`, `r2_verify.txt`)
- **Selection (frozen sha1 `561b5e65…` before any outcome):** 10 legs, all 6 channels — credit: Baa corporate spread; Fed: net liquidity, funds rate; rates: 10-year real yield, 2-year yield; dollar: UUP; metals: gold/silver (his seed), copper/gold; risk appetite: IWM/SPY, ARKK/QQQ. His junk-bond seed (C1 on HYG) failed E2: its dividend-adjusted trend reads easy on 78.3% of 1,210 sessions in 2016-20 (total return climbs with the interest paid). Its tile stays by his ruling.
- **Composite:** Draining 37.7% of 1,937 test-window days, Neutral 38.4%, Easing 23.9%; median stay 18.5 sessions; ~8 word changes a year.
- **§5.6 verdict: no word ships** — four tests fail, each narrowly: W0 Draining share 37.7% vs the 35% ceiling; W1 calm rows 3 of 5 vs 4 (Q1 by 2 sessions; Q5 late-2023 rally read 29% Draining); W2(d) Easing followed by a 10% IWM drop on 14.7% of 463 days vs Neutral 12.0% of 744 (driven by the pre-Covid Easing spell); W3(c) within negative-breadth days ratio 1.244 vs 1.25. P2 fails on both setups (EP big-winner share 12.3% of 1,256 Draining vs 12.0% of 2,250 other; breakout 0.94% vs 1.15%) → **"market read only"**: the composite does not separate which EPs or breakouts become big winners.
- **What it does show (described, not a pass):** all four must-drain episodes caught (2018 Q4 85%, 2020-03 81%, 2022 85%, 2023-08..10 91%); a 10% IWM drawdown within 63 sessions follows 32.9% of 730 Draining days vs 13.0% of 1,207 other days (ratio 2.53, beats SPY trend 1.32, IWM trend 1.56, VIX 1.37, breadth 1.73, holds in both halves and a timing shuffle); but a 10% IWM GAIN also follows 33.4% of Draining days vs 21.4% of Neutral — Draining marks volatile, two-way markets, not only drops.
- **Per §5.6:** the indicator rows and "N of 6 groups tight" may ship as a display labelled "context, not validated", with no Draining / Neutral / Easing word; his JNK and gold/silver tiles beside them.

## 13. HIS GO 2026-11-22: test TURNING POINTS ("The turning points and trends is also important" → "Go")
Run 2 judged daily STATES; this asks whether TURNS in the liquidity read mark TURNS in the market and in his setups. §13.1 (the turning-point pre-registration) is written and frozen by a separate design step BEFORE any turn-to-outcome number is computed; the run-2 legs and composite are reused unchanged.
