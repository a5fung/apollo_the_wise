# #705 — Qullamaggie's calls, round 3: the structural stop, holding winners longer, market-strength sizing (2026-10-24)

**Status: REGISTERED, NOT FROZEN, NOT RUN.** No fill, stop, exit, R or return of any variant below has been computed. The first two
replays' outcomes ARE known (`docs/analysis/cb_qm_replay_prereg_2026-10-23.md` §RESULT: his 236 calls under his rules 1.85x, the
30% cap 2.044x; `docs/analysis/cb_qm_replay_execution_prereg_2026-10-23.md` §RESULT: NEXT GAPS — buy-stop at the level 1.27x, TC2000
ADR 1.84x, re-entries 1.63x, 30% cap 2.04x, combined 1.51x). §1 lists exactly what was seen and what that does to this read. The
module's dry run (`scripts/probes/_705_qm_replay_1023/03_round3_dryrun.txt`) loaded the inputs, asserted the populations, read the
base low at D from daily bars up to D only, read the fetch logs and hashed the first two reads' output files without parsing them.
It parsed no minute file (it hashed the 193 + 8 minute date files' bytes for the walk-set pin) and called no entry or exit
function. Measurement and registration only. Nothing here changes or proposes
to change a strategy, an entry, a stop, an exit, a size, a safeguard or any live trade state. Those are the operator's (THE LINE).

His words this read serves (verbatim, `docs/methodology/operator_shared_notes.md`):
- 2026-10-22 (l.2435): *"If the issue is getting stopped out to really it's either a stop placement problem or a reentry problem,
  or entry timing but not that there's no edge in breakouts which is my point"* — and the notes' own table under it (l.2442, our
  words): the stop *"wider than 1
  ADR, or structural (the base low uncapped)"* is **NOT TESTED**.
- 2026-10-22 (l.2494): *"the really good setup ones we shouldn't miss or stopped before the run, even if we need to retry"*.
- 2026-10-23 standing rule: a backtest that does not reproduce profit over his years is a defect in OUR implementation or
  interpretation to be found — never a finding that the setup does not work.

**Said plainly, before anything else: every variant here was chosen AFTER seeing the first two reads.** The first read showed 134 of
174 trades stopped out and the 20-day trail lifting the mean but not the curve; the second read showed the level entry, the ADR
formula and the re-entries making his calls WORSE and only the size cap helping. The variants below are the next levers on the
10-22 list, not fresh hypotheses. A lift here is in-sample until it holds on calls not used here.

## 0. In plain words

- **Where we are:** his 236 stream calls, traded his way and compounded in one account, make 1.85x (2.04x with a 30% position cap).
  That beats 99.5% of same-day random pick sets but is far below his audited record. The second read's four execution fixes did not
  close the gap.
- **The question:** do three untested levers close it — a wider, STRUCTURAL stop (the base low) with the position sized down to
  match; holding the winners longer (the slower 20-day trail, the 10-day only for fast stocks); and risking less when the market is
  not strong?
- **The variants (fixed now, §4):** W1 the base-low stop; W2 the 20-day trail with the 10-day for fast stocks; W3 half the risk when
  QQQ is not above both its 10- and 20-day averages; COMBINED = all three on top of the 30% cap. Margin and adds (W4) are printed
  beside only and decide nothing.
- **Every variant is applied to the same day's other breakouts too**, so the reference band moves with it.
- **What decides (§7, fixed now):** COMBINED reaches +50% in BOTH 2020 and 2021 and the same-day band sits at or above it in at
  most 5% of draws — then these gaps explain most of the shortfall. Otherwise we name the next gaps (§7). "The setup does not
  work" is never a reading.
- **Action from him: none now.** One open question is noted at §4 W4 (margin / adds); it is NOT needed for this read.

## 1. The four questions of the standard, and what was seen before this registration

1. **Decision served:** whether the remaining shortfall is mostly these three levers (then each gets validated on unused calls), or
   whether the next gaps must be tested: the EPs and parabolic shorts in his record, the trades he never mentioned on stream, and
   adds / margin if still beside. What to do with either is his.
2. **What would change it:** the fork in §7.
3. **Population:** the first read's, unchanged (§2). No re-entry rows: no variant here chains.
4. **What would make this wrong:**
   - (a) **In-sample choice.** Chosen after two reads. Validated only on calls not used here (era B, the sealed 2025–26 table, new
     stream labels).
   - (b) **W1's R is not the first read's unit.** R = fill − the base low, a stop mostly wider than one ADR, so W1's and COMBINED's
     per-trade R runs smaller for the same move. The account and the band are the comparable numbers; the per-trade tables carry
     the stop width in ADR beside them.
   - (c) **W2's speed cut is ours, and his calls are mostly above it.** "Faster stocks" is his; 4.79% ADR is the module's reading of
     it, fixed 2026-10-18 as the top tercile of the discovery C0 ADR distribution — before this read, not on his calls, but still a
     parameter. 181 of his 236 calls are above it (the dry run, §2), so the speed arm IS the baseline's 10-day exit on 77% of his
     calls; a null on W2 says little about "hold longer" — the plain 20-day beside it carries that reading.
   - (d) **W3's "strong market" is a reading.** His article says only bullish / *"fewer or no trades"*, his 10-22 words *"size down
     or reduce trading"* (l.2469); the QQQ state (D's close above both its 10- and 20-day averages) is the first read's §7
     definition, not the rule attributed on 10-17 (l.1952: the 10-day above the 20-day, both rising), which is not used here. The
     10-22 market-split probes on C0 found
     2020's best breakouts were taken while the lagging averages pointed DOWN, so W3 may cut the best year.
   - (e) Every caveat of the first read's §1.4 still holds: 109 calls rest only on a label said on E; the calls are a stream slice;
     the joins are noisy and 104 calls sit on a retrigger; the rules are our reading of his article; EPs and shorts are not here;
     2020 holds 156 of the 236 calls.
- **Seen before this registration:**
  - the first read's printout, in full: the verdict EXECUTION / data; 174 of 236 filled; 134 stopped out; the account rows for every
    config incl. `cap_30` final 2.044 (2020 +62.8%, 2021 +26.2%, band share 0.5%); the beside table of the other exits at the
    PRIMARY (20%) cap — **including `orh5 p33_s3_t20`: mean R +0.821 on his 174 trades, curve 2020 +47.7%, 2021 +11.5%, final
    1.762.** That is W2's plain-20-day half at the wrong cap. It is re-run here beside W2, at the 30% cap, as a near-known row;
  - the second read's printout, in full: V0–V4 and COMBINED, the minute-0 own-low convention's size (§1.4b there);
  - the his-exit read of 2026-10-18 (`docs/analysis/cb_his_exit_2026-10-18.md`): the `tspd` speed arm and a `base_low` stop CAPPED
    at one ADR, on the 2022-24 DISCOVERY first breaks (watch nights 2022-03-28..2024-12-31): none of era A's 236 calls is in that
    population (era B's 6 first breaks may be, unidentified). The capped base-low stop kept 755 of 8,989 trades and read −0.011
    ADR against −0.047 ADR for the registered stop on the same 755 (ADR units, not R). The UNCAPPED base low has never been
    walked, on any population;
  - the 10-22 market-split probes (`_702_race_1022/02_market_phase_split.txt`, `03_market_trend_split.txt`) on C0 trades: no simple
    market filter separated them; the 2020 rebound's best trades came under the lagging averages.
- **Not seen:** any number of W1, W1b, W2 (the speed arm on his calls), W2b, W3, W3b, COMBINED or W4; `p33_s3_t20` at the 30% cap.

## 2. POPULATION — the first read's, asserted again

- **His calls, the control and the beside groups are the first read's, derived by its frozen code** (`01_replay.py`, pinned
  `c4478588…`, imported read-only through the frozen second read) and asserted again by its `describe_population`:
  - era A: his calls n = 236 (127 strictly before E, 87 post-E-only beside);
  - the control: n = 23,188 same-day other tl breakouts (round-3 exclusion: 410 rows);
  - era B: n = 9 calls and 345 control events, descriptive.
- **The walk set is the first read's** (the two data exclusions, unchanged): the minute date files it opens are the first read's 193
  (era A) and 8 (era B), and their tree hashes must equal the first read's pins (asserted; a drift refuses the dry run).
- **New outcome-free fact per event: the base low at D** = the lowest low of the base sessions (P, D], P = the candidate's `pole_date`
  (the module's `explain_watch` formula, `runner.base_low_at`), from daily bars up to D only. Cross-checked against the candidate's
  stored `base_depth` (= 1 − base_low ÷ high(P)) on every event; a mismatch is counted and printed, and a non-zero count stops the
  read. The dry run prints, per group: the width of a stop at the base low from the LEVEL, (pivot − base_low) ÷ pivot in ADR20
  units (median, 90th percentile, the shares above 1 / 2 / 3 ADR), and the events whose base low sits at or above the level (they
  cannot fill with a stop under the fill at the level and will abstain under W1 if filled there).
- **Outcome-free, also printed:** his calls / the control above the W2 speed cut (ADR20 at D > 4.79%), and the QQQ state at D
  (up / mixed / down / unknown) per group — the first read's counts (his up 163 / mixed 35 / down 38).
- **Dry-run facts (2026-10-24, `03_round3_dryrun.txt`; bars up to D only, no outcome):**
  - the base low reproduces the stored `base_depth` on all 23,840 events (0 mismatches);
  - a stop at the base low, measured from the level, is **2.28 ADR20 wide at the median on his 236 calls** (90th percentile 4.18;
    wider than 1 / 2 / 3 ADR on 88% / 60% / 28%); the control's median is 2.81. **No call's base low sits at or above its level**;
    56 control events' do — under W1 such an event abstains when its base low is at or above the FILL (level × 1.001, or the open
    above it), else it FILLS with a stop under 0.1% wide. That is the second read's unit artifact (§1.4b there) in a new place: 1R a
    fraction of a percent, a 5% move reading 50R. The account bounds it by the cap; the per-trade rows and the interval are re-read
    beside without stops under 0.25 ADR (§5), and the dry run counts, per group, the events whose base low lies within 0.25 ADR under
    the level or above it (only among them can a W1 stop be that narrow): **2 of his 236 calls, 130 of the 23,188 control events**;
  - **181 of his 236 calls (77%) have ADR20 at D above the speed cut**, so under W2 the speed arm trails the 10-day on them — the
    baseline's own exit — and the 20-day on 55 calls only. The control is 36% above the cut. W2's speed arm therefore moves his
    calls little by construction; the plain 20-day (W2_t20) is the stronger "hold longer" reading and is printed beside it;
  - QQQ at D on his calls: up 163 (W3 risk 1%), mixed 35 and down 38 (0.5%; W3b drops the 38); on the control up 17,282 / mixed
    3,123 / down 2,783.

## 3. CONTROL — the same day's other breakouts, under the same variant

- **Unchanged from the first read:** every other tl breakout on his calls' E dates, with the round-3 exclusion.
- **Every variant is applied to the control exactly as to his calls:** the same stop, the same exit arm, the same sizing rule, the
  same margin / adds when W4 is read.
- **The band reuses the first read's 200 same-day draws** (seed 702, key `qm_replay|band|A|same-day (registered)`; on every date as
  many control events as his calls that day). Each drawn control event is mapped to its trade under the variant (and its add under
  W4a). The same draws under every variant make the variant-to-variant comparison paired. Under the baseline they reproduce the
  first read's `cap_30` band exactly, and this is asserted.

## 4. THE VARIANTS — fixed now, each tagged S (his words, quoted with the line) or B (this registration's choice)

Every variant runs at the **30% cap**: risk 1% of equity per trade, position capped at 30% of equity, at most 30% of equity at cost in
one stock, no margin (W4 excepted). That is the first read's `cap_30` row (= the second read's V4), the best account seen so far.
The entry is ORH5 in every variant (**S** l.1941 *"Enter on the opening range highs"*). Every fill pays 0.1% (`cb.ENTRY_SLIPPAGE_PCT`).
The horizon is 120 sessions.

| variant | tag | the rule | code |
|---|---|---|---|
| **B0** (baseline) | the first read's | ORH5; stop = the module's low of the day at the fill; skipped when wider than ADR20; exit `p33_s3_t10`; 1% / 30% / 30% | `cb.entry_variants(...)["orh5"]`, `cb.ARMS["p33_s3_t10"]`, `rp.Config("cap_30")` |
| **W1** structural stop | **B** — his article's stop is the day low (**S** l.1943 *"Stop is always lows of the day and stop should not be wider than the ATR or ADR of the stock"*); his 10-22 words name the lever (l.2435 *"a stop placement problem"*). The structural base low, uncapped, is the untested row of the notes' own table under them (l.2442, our words, not his). | the ORH5 fill, stop = the base low at D (§2). **No one-ADR skip:** a base-low stop is wider than one ADR on most bases (the his-exit read), so the registered skip would abstain W1 away; the 20 calls the baseline skipped as too wide fill under W1 at their fill with the base-low stop. The only abstain: base low at or above the fill (`stop_at_or_above_fill`, counted). The day-0 walk is re-run on the new stop. Sized at 1% risk: a wider stop is a smaller position | `with_stop`, `cb.day0_walk`, `cb.walk_arms` |
| W1b (beside) | **B** | stop = the LOWER of (a) the low of the day through the minute BEFORE the fill minute and (b) one ADR20 below the fill: min(lod_prior, fill × (1 − ADR20)). At least one ADR wide by construction, so no one-ADR skip (as W1); the too-wide calls fill at their lod_prior | `with_stop` |
| **W2** hold winners longer | **S** l.1946–1947 *"The rest 'trailed with the 10- or the 20-day moving average... You wait for the first CLOSE below the 10-day'"*; l.2095–2096 *"Depends on how fast the stock is. If a beginner stick to the 10-day"*; the operator's 10-18 correction, l.2046-2047, *"trail rest at break of 10 or 20d, I recall he mentioned 10d for faster stocks and 20d for slower stocks"*. **The cut is B:** `cb.TRAIL_SPEED_ADR_CUT` = 4.79%, fixed 2026-10-18 as the top tercile of the discovery C0 ADR20 distribution at D (before this read; never fitted to his calls). **The day-3 partial is B:** his correction sells the first third at +2R (l.2046 *"sell 1/3 at 2R"*). The session-3 close is kept as the baseline's, on his follow-up l.2060 *"The day thing is also correct, it may be a combo and depends"*. | B0's entry and stop; exit = sell 1/3 at the session-3 close, stop to breakeven, trail the rest on the **20-day** average, or on the **10-day** when ADR20 at D is above 4.79%; first CLOSE below, filled at the next open | `cb.HIS_EXIT_ARMS["d3_p33_tspd"]` (its day-3 partial IS `p33_s3_t10`'s, tested equal in the SSoT) |
| W2_t20 (beside; seen at the 20% cap) | **S** the same lines, the plain 20-day | B0's entry and stop; exit `p33_s3_t20` | `cb.ARMS["p33_s3_t20"]` |
| W2b (beside) | **B** — his words sell a third first (l.1946 *"sell 1/3 to 1/2 of the position after 3-5 days"*) | no partial at all: the whole position trails on the 10-day from session 1, no breakeven move | `cb.ARMS["trail10_only"]` |
| **W3** market-strength sizing | **S** for the words: the operator, 10-22, l.2469 *"Breakouts tend to fail during bear phase, which should mean we either size down or reduce trading"* (W3 = size down, W3b = reduce trading); the article, l.1940 *"fewer or no trades"*. **B** for the numbers and the reading: 0.5% risk is "size down", and "not up" is QQQ at D's close NOT above both its 10- and 20-day simple averages (the first read's §7 state). This is NOT the rule attributed on 10-17 (l.1952: the 10-day above the 20-day, both rising), which is not used here. | B0's trades; risk 1% when QQQ at D is "up" (above both averages), 0.5% otherwise (mixed, down, or unknown — counted apart) | `risk_qqq`, `simulate3` |
| W3b (beside) | **S** the same words ("no trades"); **B** the reading | B0's trades; risk 1% when up, 0.5% when mixed, NO trade when QQQ is below both (the trade is not offered; counted) | `risk_qqq`, `drop_down` |
| **COMBINED** | — | W1's stop, W2's exit, W3's sizing, at the 30% cap: ORH5 fill, stop at the base low, sell 1/3 at the session-3 close then breakeven and the speed trail, risk 1% / 0.5% by the QQQ state | the fork variant |
| W4 (BESIDE ONLY; decides nothing) | **B** — nothing in his breakout words sets margin or adds; the only "adds" he describes are the parabolic-short pyramid (l.2200), a different setup | W4m: **margin up to 2x gross exposure** — a trade may borrow: it is skipped only when its value exceeds the free cash plus one times the previous close's equity (so positions at cost may reach twice the equity), no interest charged; on B0 and on COMBINED. W4a: **one add per trade on a new high after the day-3 partial** — on the first session j ≥ 4, before the remainder's exit session, whose high exceeds the highest high since E (E's own high included), the add fills at that prior high (or at the open when the session opened above it) plus 0.1%, its stop is the position's stop in force (the fill, i.e. breakeven), it is sized at the variant's risk on the previous close's equity inside the same caps, and it exits with the remainder at the remainder's final price and date; on COMBINED. W4ma: both | `simulate3(gross_max=2)`, `add_for` |

- **The own-low rule (the second read's §1.4b: a stop that IS the fill minute's own low — minute 0, or a fill minute that made a
  new low of the day):** no NEW stop is set there. W1's (and COMBINED's) base low comes from daily bars up to D. W1b's lod_prior
  reads 09:30 through the minute BEFORE the fill minute (ORH5 fills at minute 5 or later, so that range is never empty; asserted).
  B0, W2, W2_t20, W2b, W3, W3b and W4m_B0 inherit the registered ORH5 stop, the low of the day THROUGH the fill minute. When that
  minute made a new low of the day, their stop IS its low. That is the registered baseline, which the parity gate needs. It is
  counted per group, printed beside (`own_low_flag`, print-only), and the fork variant never uses it. Only the minute-0 form cannot
  occur: ORH5 never fills in minute 0 (asserted on every walked fill).
- **W1 abstains, named and counted:** `stop_at_or_above_fill` (base low ≥ fill). Every other abstain of the ORH5 entry (`no_minutes`,
  `minute_daily_mismatch`, `minute_high_below_pivot`, `no_opening_range_minutes`) is the same under every variant: there is no fill
  to re-stop.
- **Every stop × every exit is walked** (3 stops × 4 arms), so the grid is printed beside (account final, per-trade mean) for the
  next registration. Only the rows above are read; only COMBINED decides.

## 5. MEASURES — the first read's, tail first (era A decides; era B, n = 9, descriptive)

- **Per trade** (mature walks only; R = fill − the variant's entry stop):
  - ≥5R / ≥10R / ≥20R per 100 trades, max, worst, win rate, mean, median; per 100 events beside; at 0 / 0.1 / 0.2% exit slippage.
  - **The stop width in ADR20 units beside every W1 / W1b / COMBINED row** (median, 90th percentile): their R is in a wider unit.
  - **Beside, the near-zero-stop re-read (the second read's R16):** the W1 / W1b / COMBINED rows (B0 for scale) again over trades
    whose stop is at least 0.25 × our ADR20 wide, with the count removed per group, and the date-matched mean-R line for the same
    three variants over those trades (key `qm_round3|A|<variant>|floor|mean R`). A base low just under the fill makes R a unit
    artifact; the account bounds such a trade by the cap, the per-trade rows do not. Decides nothing; no trade is removed from the
    account, the band or the fork.
  - W3 is sizing-only: its per-trade numbers ARE B0's and are not reprinted as new. W3b removes the down-state trades from both
    arms, so it has its own per-trade row and interval.
- **By year of E**, by QQQ state at D (COMBINED), first breaks / retriggers, the 127 strictly-before calls, one event per base,
  post-E-only (hindsight), and the not-mature count with its booked R.
- **His minus control, DATE-MATCHED** (the first read's `paired_block_diff`, unchanged): per trade, in the cell (date of E, first
  break / retrigger), weighted by his filled mature trades; month blocks, 2,000 resamples, seed 702, key
  `qm_round3|A|<variant>|mean R`; ≥10R per 100 beside. B0 uses the first read's key `qm_replay|A|orh5|p33_s3_t10|mean R` and must
  print +0.543 [−0.132, +1.424] again (asserted; per-trade R does not depend on sizing).
- **Corporate actions:** the first read printed them for the baseline trades and they are not repeated. G8 (§9) covers every trade,
  adds included.

## 6. ACCOUNT CURVE and BAND — the first read's simulation, extended by two switches it does not use in the baseline

- **`simulate3`** is the first read's `simulate`, line for line, with two additions that are OFF in the baseline: a per-trade risk
  (`risk_of`; the baseline's is the config's 1% on every trade) and `gross_max` (1.0 = the first read's no-margin rule, exactly:
  the room is the free cash; 2.0 = W4m). **Parity is asserted in the real run:** the baseline's curve through `simulate3` equals the
  first read's `simulate` on the same trades day by day, and both equal the stored `cap_30` curve. A synthetic test asserts the
  same on random trade lists.
- **Reported per variant:** yearly return 2017–21, 2022 (exits only), final equity, max drawdown; trades offered, entered, skipped
  for no room, skipped or trimmed by the stock limit, cap-bound; max open positions, max gross exposure; for W3 the trades at 1% /
  0.5%; for W3b the trades not offered; for W4 the adds taken and the deepest borrowing.
- **The band per variant (§3):** the 5th / 50th / 95th percentile of the 2020 and 2021 returns, the final equity and the max
  drawdown, and the share of draws at or above his (for max drawdown, as deep or deeper, which is worse).
- **Beside:** COMBINED on the 127 strictly-before calls against their own band (the first read's strictly-before draws, key
  `qm_replay|band|A|strictly-before (beside)`); era B's curve per variant; the 3 × 4 stop-by-exit grid at the 30% cap.
- **THE BASELINE-PARITY GATE (real run, before any variant number is printed; a miss STOPS the run, exit 3).** B0 must BE the first
  read's `cap_30` row:
  - every ORH5 entry and every `p33_s3_t10` AND `p33_s3_t20` walk of the first read's 23,840 events equals the first read's
    `trades.tsv.gz` (status, reason, fill, stop, fill minute, maturity, sessions held, R) — two arms, so the exit walker is checked on
    a 20-day trail too;
  - his `cap_30` curve equals `account_his.tsv` day by day, through both `simulate` and `simulate3`;
  - its final equity prints **2.044** (the registered baseline, asserted on the 3-decimal string), 2020 +62.8%, 2021 +26.2%;
  - the band's five percentiles and its share equal `account_band.tsv` (`cap_30`, final);
  - the re-entry count is 134 / 91 / 358 / 33 and the date-matched line reads +0.543 [−0.132, +1.424];
  - every walked ORH5 fill has a fill minute ≥ 5 (no minute-0 fill exists in any variant).
  - Without this gate, a wrong import would read as a "stop placement gap".

## 7. THE FORK — written now, before any variant outcome

| reading (era A; COMBINED = W1 + W2 + W3 at the 30% cap, applied to his calls and to the control) | → | the next work |
|---|---|---|
| his COMBINED curve returns **≥ +50% in BOTH 2020 and 2021** AND **at most 5% of the 200 band draws** (COMBINED applied to the control) end at or above his final equity | **EXPLAINED** — the structural stop, holding winners longer and market-strength sizing explain most of the shortfall | validate each variant on calls not used here (era B, the sealed 2025–26 table, new stream labels) before anything is built on it; any live use is his call (THE LINE) |
| anything else | **NEXT GAPS** — these three do not explain it alone | register the next gaps, each on its own: the EPs and parabolic shorts in his record; the trades he never mentioned on stream; adds / margin if still beside. Never "the setup does not work" (his rule, 10-23) |

- **Each variant alone is printed beside, against B0 and against COMBINED,** for his calls and the control: tail first, the account
  by year, the band. No variant alone decides. W4 decides nothing in any reading.
- **COMBINED on his calls is mostly W1 + W3,** since 77% of his calls sit above the speed cut where the speed arm IS the
  baseline's 10-day.
- **Read honestly — 2021 is the hard year.** The baseline's 2021 was +26.2% at the 30% cap; his calls lost per trade in 2021
  (−0.199R over 50 trades) while the control earned +0.207R. At 1% risk with no cap binding, +50% in a year needs about 50R net; a
  base-low stop sized at 1% risks the same 1% on a wider stop, so its R per trade is smaller and its position smaller.
- **Both arms are printed apart**, so a NEXT GAPS reading says which one failed.
- **What neither outcome shows:** his returns; that he traded these calls this way; that a lift transfers out of sample; anything
  about exits beyond the four arms here.

## 8. Expectations, written now (a miss changes no rule)

- **W1:** every baseline fill and all 20 too-wide calls fill (no call's base low sits at or above its level, §2); the median stop is
  about 2.3 ADR wide from the level and a little more from the fill, so positions are a third to a half of the baseline's and far
  fewer trades are cap-bound (the baseline's cap binds whenever the stop is under 3.3% wide); the stop-out
  rate falls from 77% toward half; per-trade mean R (in the wider unit) is near the baseline's; the curve is NOT higher than 2.044 —
  the smaller positions give back what the fewer stop-outs save. Day-0 stop-outs nearly vanish.
- **W1b:** between B0 and W1.
- **W2:** the speed arm changes only the 55 slower calls (77% of his calls are above the cut and keep the 10-day, §2), so its
  per-trade mean and its curve sit close to the baseline's; the plain 20-day (W2_t20) moves more: per-trade mean R above the
  baseline's (the first read saw +0.82 against +0.64), more ≥10R trades, but a curve near or below the baseline's — the 20-day trail
  gives back more on the losers it holds (1.762 at the 20% cap against 1.850). On the control (36% above the cut) the speed arm
  reads closer to the 20-day.
- **W2b:** fewer trades reach a partial; the mean falls; the curve is below the baseline's.
- **W3:** 2020 falls (the rebound's breakouts were taken in mixed / down states); 2021 changes little; the final is below 2.044.
  W3b falls further.
- **COMBINED:** 2020 below +50%, 2021 below +50%, so the expected reading is **NEXT GAPS**, with the band share small (under 5%).
- **W4:** margin lifts the baseline's curve and its drawdown together (44 of his calls were skipped for no room at the 30% cap; 28 at the 20% primary); the adds
  fire on a minority of trades and add little.
- **Era B** (9 calls, all losers in the first read) stays negative under every variant.

## 9. DATA GATE (STEP 0) and the point in time — the first read's

- **Era A = `cb702_pre_v2`** (S0, G1–G7 and G9 PASS, pinned verdict). Era B = `cb702`: every row after 2024-12-31 is dropped at read
  and asserted (the first read's loader, unchanged).
- **G8 = this read's own trade list:** the union of every (stop, exit) walk's trades, adds included, each (ticker, entry date, hold)
  once, written as attempt 0 from its own entry date. `trade_impact.py --kind r1 --cell p33_s3_t10 --cutoff 2024-12-31` runs on each
  era before any number. Era A must read 0 entered after the cutoff and 0 holds past the last bar (asserted, else STOP). Era B is
  censored.
- **Point in time:** the base low and the pole are from bars up to D; the QQQ state from QQQ closes up to D (an add's state from the
  session before the add); the speed cut reads ADR20 at D. Nothing from E's bar enters a selection. E's minutes enter the entry, and the
  day-low stops only up to the fill: B0's through the fill minute (registered), W1b's through the minute before it. W1's stop
  reads no E data.

## 10. Method / population — files, the module, its guards, the readings chosen

- **Inputs (pinned):** every input of the first read, with its pins; the first read's outputs (`trades.tsv.gz`, `account_his.tsv`,
  `account_band.tsv`, `01_replay.txt`), read by the parity gate in the real run only and hashed by the dry run; the second read's
  outputs under `apollo_data/cb702/qm_streams/qm_exec_1023/` and `02_execution_variants.txt`, hashed only (never read: this read
  reuses nothing of V1–V4); the first registration's frozen text (`aaaadd29…`) and the second's (`329ac865…`); the candidates'
  `pole_date` and `base_depth` columns (D-night features, re-read from the pinned candidate files).
- **Code (pinned):**
  - `scripts/probes/_705_qm_replay_1023/03_round3.py`, its tests `test_03_round3.py` (synthetic: the base low from bars and its
    `base_depth` cross-check; W1 from a filled and from a too-wide entry with a fresh day-0 walk, the base-low-above-fill abstain;
    W1b never the fill minute's own low; the speed arm equal to the 10-day above the cut and to the 20-day below it on bars where
    they differ; `trail10_only` with no partial; `simulate3` equal to the first read's `simulate` on random trade lists; W3's risk
    by state and the down-state drop; margin entering what no-margin skips; one add per trade, never on a stop day, never before
    session 4; the fork; the NEXT GAPS text word for word; the line-anchored freeze lock; the parity readers; a tampered first-read R
    stopping the run; an end-to-end run that first runs the frozen first read on the same world and then this read through the
    parity gate);
  - the frozen `01_replay.py` / `test_01_replay.py` (`c4478588…` / `37c918a0…`) and the frozen `02_execution_variants.py` /
    `test_02_execution_variants.py` (`346516fb…` / `6ce013bb…`), imported read-only: the loaders, populations, walk wiring, trade
    builder, simulation, control draw, date-matched difference, G8, the line-anchored lock, the parity readers, the own-low flag,
    the fork function;
  - the runner, the cb module (`cb.ARMS`, `cb.HIS_EXIT_ARMS["d3_p33_tspd"]`, `cb.TRAIL_SPEED_ADR_CUT`), `constants.py`, the Track A
    fit and join modules, `aplus_read.py`, `registered_read.py`, `trade_impact.py` (the first read's pins).
- **The module's guards:**
  1. **Freeze lock, line-anchored:** the doc-body hash covers every byte above the ONE line that is exactly the freeze marker. Zero
     such lines, or two, refuses (exit 2). The marker text appears nowhere else in this document.
  2. Refuses (exit 2) if `03_round3.txt`, a STOPPED file or any output under `apollo_data/cb702/qm_streams/qm_round3_1024/` exists.
  3. Populations asserted (the first read's EXPECT); the walk set's minute trees equal the first read's pins; the base-low
     cross-check count is 0; a miss stops before any minute file is opened.
  4. G8 before numbers; the baseline-parity gate before numbers.
  5. Per trade, the R recomputed from the dated legs equals the walk's own (the first read's `make_trade`).
  6. A crash after the walk writes a STOPPED file with the traceback (never a silent re-run).
- **Readings chosen where the brief was open (B = this registration's choice):**
  - **R1:** W1 drops the one-ADR skip (uncapped, the 10-22 table's words); the too-wide calls fill under W1 and W1b.
  - **R2:** W1b = min(lod_prior, fill × (1 − ADR20)), lod_prior through the minute before the fill minute; no skip.
  - **R3:** W2 is the speed arm `d3_p33_tspd` (20-day default, 10-day above the cut); the plain 20-day and `trail10_only` are beside.
  - **R4:** the speed cut is the module's 4.79% (fixed 10-18), not re-chosen here.
  - **R5:** W3's "otherwise" = mixed, down AND unknown state (the QQQ state is the first read's, at D's close); W3b drops "down" only.
  - **R6:** W3 and W3b size on the previous close's equity, as the first read.
  - **R7:** COMBINED = base-low stop × speed arm × QQQ sizing; W4 is never in COMBINED.
  - **R8:** margin = borrowing up to one times the previous close's equity (gross at cost up to 2x), no interest; one add per trade,
    at the prior high (or the open above it) plus 0.1%, stop at the breakeven fill, exiting with the remainder; an add whose stop is
    at or above its fill is skipped and counted.
  - **R9:** every (stop, exit) combination is walked and the grid printed beside; only the registered rows are read.
  - **R10:** era B is descriptive (9 calls).
  - **R11:** G8 covers every walked trade of every combination and every add, each written as attempt 0.
  - **R12:** the baseline is re-walked and gated against the first read's stored outputs on two exit arms.
  - **R13:** the near-zero-stop re-read is beside only, at the second read's 0.25 × ADR20 floor (`WIDTH_FLOOR_ADR`, `floor_ok`,
    imported); no trade is removed from the account, the band or the fork.
- **Outputs (real run):**
  - `scripts/probes/_705_qm_replay_1023/03_round3.txt`;
  - under `apollo_data/cb702/qm_streams/qm_round3_1024/`: `trades.tsv.gz` (one row per event × stop × exit), `adds.tsv`,
    `g8_{A,B}.tsv`, `g8_{A,B}_impact.txt`, `account_his.tsv` and `account_band.tsv`.
- **Cost:** $0 — local compute only, no paid API. The dry run takes about 10 s; the real run walks about 23,840 events once under
  3 stops × 4 exits.

## 11. What this does not answer

- **His actual returns.** This is our walk of a stream-confirmed slice of his calls under our reading of his rules. His record also
  holds EPs, parabolic shorts, his own fills, his adds and his sizing.
- **Whether a variant generalizes.** All were chosen after two reads. A lift here is in-sample until it holds on era B, the sealed
  2025–26 table or new stream labels.
- **Stops between the day low and the base low** (two ADR, the level minus one ADR). Only the two ends are read here.
- **Re-entries under a structural stop.** The second read's chains were on the day-low stop; a base-low stop is stopped out less
  often, and its re-entry question is a separate registration.
- **What "fewer or no trades" means in his practice.** W3 reads it as half the risk; W3b as no trades below both averages. His
  actual exposure rule is not in the article.
- **Adds and margin as he used them.** W4 is one reading of each, beside only; the operator's answer on how he sized adds and used
  margin is open and not needed here.
- **Whether our stream's bases are the bases he saw.** The base low is our structure's low.
- **2022+ beyond 9 descriptive calls, and anything about 2025–26** (sealed, unread).

<!-- FREEZE -->
## Freeze record

Empty until the freeze commit. The main loop pastes, below the freeze marker line above, every pin that
`03_round3.py --dry-run` prints under "## Pins (sha256)", including `doc_body` (the sha256 of the bytes above that line). It then
commits, and then runs `python3 scripts/probes/_705_qm_replay_1023/03_round3.py` once. Any edit above the marker line after that
changes `doc_body`, and the run refuses.

Recovery after a STOPPED run: a stop after the walk leaves files under `apollo_data/cb702/qm_streams/qm_round3_1024/`, and each one
blocks a re-run. Recovery = fix, delete `03_round3.STOPPED.txt` AND those files, and re-freeze if the module changed. Any outcome the
stopped run printed is recorded as seen. The `g8_A.tsv` / `g8_B.tsv` files are written BEFORE the parity gate and carry every
variant's per-trade R. After a STOPPED run they are deleted unread.

### FREEZE 2026-10-24 (this commit; the one real run follows it)

- labels_joined: d0299beba6f2d0def7947bb6e77eac008ced4586450bb260ceed51f7b0fdca3b  /Users/alvinfung/apollo_data/cb702/qm_streams/track_a_1023/labels_joined.tsv
- matched_events: 4d07d6e542bf5064cacf5e446a20566e9a1cb17fd126efee560634a2f6cd11fc  /Users/alvinfung/apollo_data/cb702/qm_streams/track_a_1023/matched_events.tsv
- moments: f2c81633de6c6765477368876e300c4636d34222b43a5b13245cdf96b8d3add0  /Users/alvinfung/apollo_data/cb702/qm_streams/vision/graded_moments.tsv
- cand_A: 3c5a66dc3052d0a284cbfee8202f74deb4e5bb75c74565dd8147df015e1baa5a  /Users/alvinfung/apollo_data/cb702_pre_v2/out/candidates_tl_com.tsv
- cand_B: b75c828671171530225198f97fc1191c9bced8f9448b9b05aa46099d617ce0c7  /Users/alvinfung/apollo_data/cb702/out/candidates.tsv
- export_A: 0d5d2d0eb027abc06e4186ddec7d1e8b1234fd86f92c26798a8e15f113db668d  /Users/alvinfung/apollo_data/cb702_pre_v2/daily_closes_all.csv.gz
- export_B: ccc0097fe535cb8de9b83d6d534744b6cbadc114d9d29ecac677ac18a52900ba  /Users/alvinfung/apollo_data/cb702/daily_closes_all.csv.gz
- sessions_A: 098a9b50c92a1045043bc089a4d4d600a9631bdb45a8e22969d872440672f2f0  /Users/alvinfung/apollo_data/cb702_pre_v2/sessions.txt
- guard_A: 876a75ec6d51744579c1ea2744c1b529cbd941355ef12eb8f0451bbe7ba1af08  /Users/alvinfung/apollo_data/cb702_pre_v2/symbol_guard.tsv
- guard_A_audit: 729741b4cfc5759b6ea5d81da6afdd36c11d806bbcad845964b2b37c72d94057  /Users/alvinfung/apollo_data/cb702_pre_v2/audit_1023/universe/symbol_guard_A.tsv
- guard_B: b6cb81b6c4a1f415defc5adcf236402d93cd654c33736aa0b120b78c357b5650  /Users/alvinfung/apollo_the_wise/scripts/backtest_data_audit/runs_2026-10-23/universe/symbol_guard_B.tsv
- flags_A: 5358e31dc1b27d25c5143bdfca7a98b91a6c7a2d5b1da6c9c9d9ed9c55474c1d  /Users/alvinfung/apollo_data/cb702_pre_v2/audit_1023/price/A_flags.tsv
- flags_B: 8bf843859afb70ea59edf6f11cda12160020936c8df3e978b6a819590ea5c3d5  /Users/alvinfung/apollo_data/audit_runs_2026-10-23/B_flags.tsv
- verdict_A: 02cbb1c0106101cb12e8d5deb9448051ae3ced67966ac11d2475d06f26538de3  /Users/alvinfung/apollo_data/cb702_pre_v2/audit_1023/verdict.txt
- done_A: 1277e2b2e87845bd9c38d5978e1601681b0b6a89dd5afd10ba3d3b67420f0ac6  /Users/alvinfung/apollo_data/cb702_pre_v2/minutes/_done.psv
- done_B: cf60dbe4d2c514f93dec779b98db7d47054839f1b24f1e74f3fadc0133b92178  /Users/alvinfung/apollo_data/cb702/minutes/_done.psv
- first_trades: 6526b2f41c93178b5f3f59de9851514d21730b82d3e8dd18bd982d8cd2c27156  /Users/alvinfung/apollo_data/cb702/qm_streams/qm_replay_1023/trades.tsv.gz
- first_account_his: 8932011eb9571bd1107df286af0e49673eac483a4a98cff053feedb8d565ccad  /Users/alvinfung/apollo_data/cb702/qm_streams/qm_replay_1023/account_his.tsv
- first_account_band: 6d02bd226d55d769c0b9f573bbe744c53bfdf7b78e2b066e008914ee8a4ec44a  /Users/alvinfung/apollo_data/cb702/qm_streams/qm_replay_1023/account_band.tsv
- first_printout: 3fc01120f8f8002e9da7d183cbc1685475d214f9c0e3db72815847b048a1817f  /Users/alvinfung/apollo_the_wise/scripts/probes/_705_qm_replay_1023/01_replay.txt
- second_trades: f7ddad7a51a3907c3addf4e0269759cce8101e54adb898e4d6e1103b67e14767  /Users/alvinfung/apollo_data/cb702/qm_streams/qm_exec_1023/trades.tsv.gz
- second_chains: fad70d5c2aef78d057ceebf14fd679c17576e9327f6814f1b0f501bbe17ca5ed  /Users/alvinfung/apollo_data/cb702/qm_streams/qm_exec_1023/chains.tsv
- second_account_his: 2a9eceb5a045429ddb0209cdbe25961cb3c47cd32959e12e7717c04ee05736cb  /Users/alvinfung/apollo_data/cb702/qm_streams/qm_exec_1023/account_his.tsv
- second_account_band: 6c7b074b300c8ac30e90e0628cd2e6788c1013982ad2544789467b2669eb7b80  /Users/alvinfung/apollo_data/cb702/qm_streams/qm_exec_1023/account_band.tsv
- second_printout: 5fe24f66859f643d15dee2836867377a6a7c9a2bc97549fe0129d752cb32c6c2  /Users/alvinfung/apollo_the_wise/scripts/probes/_705_qm_replay_1023/02_execution_variants.txt
- runner: 213cbe6ddf0ff05555a11c347efd14bfa37f99096fd83961e9f5127f6c7c8dcf  /Users/alvinfung/apollo_the_wise/scripts/probes/_cb_backtest/runner.py
- registered_read: 28fbc47f862f205071ab921af3a29f6093fca95e2d41e3a0f4a0f7afcd9aa449  /Users/alvinfung/apollo_the_wise/scripts/probes/_cb_backtest/registered_read.py
- cb_module: e14027be38b24352dd3c19fd5a1dcd54bae2e1cf80fc58a064d1ea65c821861b  /Users/alvinfung/apollo_the_wise/agents/market_intelligence/consolidation_breakout.py
- constants: 72dadd72503a842f593621b0868f908ab99e1d77851330c2842be7797aa99400  /Users/alvinfung/apollo_the_wise/agents/market_intelligence/constants.py
- fit_module: 3fca7bf4f26ffcdf7152ddc9d4180c295aafe29067591def812fcc6884f38d27  /Users/alvinfung/apollo_the_wise/scripts/probes/_705_track_a_1023/02_fit_filter.py
- join_script: 6889819c41342c60831b0d62b277d47b677e4deaeab3443cbdde7a05d56b112c  /Users/alvinfung/apollo_the_wise/scripts/probes/_705_track_a_1023/01_join_labels.py
- aplus_read: e344277817db88de7af2e65ad8858d4ca515c3cc3a647b3e0a67e0df9f7ec9ee  /Users/alvinfung/apollo_the_wise/scripts/probes/_cb_backtest/aplus_read.py
- trade_impact: 9b7cce415479c1abfda422c432c6de1f3a6d591f298a1167fa637a578051e146  /Users/alvinfung/apollo_the_wise/scripts/backtest_data_audit/trade_impact.py
- replay_module: c44785889670b31f3e9baf1ac0e1563aeacfefacc5de5ef426ee7b15724e7bfa  /Users/alvinfung/apollo_the_wise/scripts/probes/_705_qm_replay_1023/01_replay.py
- replay_tests: 37c918a08329b138f6c37c5787af3c95e0ea2abeceb100209cd0f5f0dd0a96ad  /Users/alvinfung/apollo_the_wise/scripts/probes/_705_qm_replay_1023/test_01_replay.py
- exec_module: 346516fb4c236cc552103032163b790d030b10a536e83c70d4cf2390c3f9f485  /Users/alvinfung/apollo_the_wise/scripts/probes/_705_qm_replay_1023/02_execution_variants.py
- exec_tests: 6ce013bb1d7f1521e8083d014e4221fc837f30c59f9c5e00fbc023344d1a1949  /Users/alvinfung/apollo_the_wise/scripts/probes/_705_qm_replay_1023/test_02_execution_variants.py
- round3_module: cbddc0b134b5862da539589f4d72d8a74ea6109041d9bc9716b2ca3fc6a94a8f  /Users/alvinfung/apollo_the_wise/scripts/probes/_705_qm_replay_1023/03_round3.py
- round3_tests: 6f09a89e72042440fbdd20abe1d74e4b59f5c69ee554bd7dc6645c275ce43492  /Users/alvinfung/apollo_the_wise/scripts/probes/_705_qm_replay_1023/test_03_round3.py
- first_doc_body: aaaadd295aba5a9de534a738410ebe391ac4993637faa7ead0cab78e2b7a9dab  the first registration's text above its marker (frozen)
- second_doc_body: 329ac865f814de0909332ff516ea5d52dea525fbef7b5fdcf1c9208a521143fe  the second registration's text above its marker line (frozen)
- minutes_A_used: b6a99cdf084ad42c1a4d846e05d10b48404f8225499253583ff78170e95b592a  the 193 minute date files the walk set opens
- minutes_B_used: d548f85679b9ded20bfa4650c45535d685d820d4dd2040fce84d01bae7b2b652  the 8 minute date files the walk set opens
- doc_body: 8d9b248c19e12db941a556a3c7cbcfb4df578dda2325f2daad1f6d9a5f243cdb  this registration's text above its marker line

## RESULT — the one real run, 2026-10-24 after the freeze commit (printout `scripts/probes/_705_qm_replay_1023/03_round3.txt`)

- **Registered verdict: NEXT GAPS.** COMBINED (base-low stop + speed trail + QQQ sizing, 30% cap): 2020 +16.6%, 2021 +7.9%, final
  1.305 (the band arm met at 5.0%, the curve arm not). Baseline parity held (B0 = the first read's 30%-cap row, 2.044).
- **Per lever, his calls, account at the 30% cap (B0 2.044):** the base-low stop 1.427 (wider stops = smaller positions); the speed
  trail 2.201 (the only registered gain); QQQ sizing 1.532 (his calls in mixed markets were his best, and it halved them).
  Beside: the 20-day trail 1.865; no partial, 10-day trail on the whole 2.196 (2021 +37.8%); **2× margin on his rules 2.306 (2020
  +74.5%, 2021 +32.8%)**; adds on a new high after the partial 1.241 (on COMBINED).
- **Read with it:** chosen after the first two reads; nothing here is validated. The registered next gaps: the EPs and parabolic
  shorts in his record, the trades he never mentioned on stream, and adds / margin (still beside until his answer). Independent
  recount: running.
