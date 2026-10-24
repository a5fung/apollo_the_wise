# #705 — Qullamaggie's calls, the execution gaps: pre-registration of four variants from his words (2026-10-23)

**Status: REGISTERED, NOT FROZEN, NOT RUN.** No fill, stop, exit, R or return of any variant below has been computed. The FIRST
replay's outcomes ARE known (`docs/analysis/cb_qm_replay_prereg_2026-10-23.md` §RESULT, `scripts/probes/_705_qm_replay_1023/01_replay.txt`);
§1 lists exactly what was seen and what that does to this read. The module's dry run
(`scripts/probes/_705_qm_replay_1023/02_execution_variants_dryrun.txt`) loaded the inputs, asserted the populations and the re-entry
rows, read ADR20 at D from bars up to D only, read the fetch logs, and hashed the first read's output files without parsing them. It
opened no minute file and called no entry or exit function. Measurement and registration only. Nothing here changes or proposes to
change a strategy, an entry, a stop, an exit, a size, a safeguard or any live trade state. Those are the operator's (THE LINE).

His words this read serves (verbatim, `docs/methodology/operator_shared_notes.md`):
- 2026-10-22: *"If the issue is getting stopped out to really it's either a stop placement problem or a reentry problem, or entry
  timing but not that there's no edge in breakouts which is my point"*.
- 2026-10-22: *"the really good setup ones we shouldn't miss or stopped before the run, even if we need to retry"*.
- 2026-10-23 standing rule: a backtest that does not reproduce profit over his years is a defect in OUR implementation or
  interpretation to be found — never a finding that the setup does not work.

## 0. In plain words

- **Where we are:** the first replay traded his 236 stream calls (2017–21) his way and compounded them in one account: 1.85x, 2020
  +48%, 2021 +25%. That beat 99.5% of same-day random pick sets, but it is far below his audited record.
- **The question:** which of OUR execution choices leak? Four leaks showed in the first read, and each variant below closes one of
  them using his own words:
  - **V1 entry** — 42 of his buys never traded above OUR level after the 5-minute opening range. His words also allow *"simply buy
    as the daily chart starts to break out"*: a buy-stop at the breakout level from the open.
  - **V2 stop width** — 20 were skipped as a stop wider than the ADR. Measure the ADR the way HIS screen does (TC2000).
  - **V3 re-entry** — 91 of the 134 stopped-out bases broke again within 20 sessions. *"Even if we need to retry"*: up to two
    re-entries.
  - **V4 sizing** — 28 calls were skipped for no room at a 20% position cap. Use his 30% ceiling.
- **Every variant is applied to the same day's other breakouts too**, so the reference band moves with it.
- **What decides (§7, fixed now):** the four together reach +50% in BOTH 2020 and 2021, and his curve stays above 95% of the band.
  Then these gaps explain most of the shortfall. Otherwise we name the next gaps to test. "The setup does not work" is never a
  reading.
- **Said plainly:** these variants were chosen AFTER seeing which trades did not fill. Anything that helps here must still be
  validated on calls not used here.
- **Action from him: none now.**

## 1. The four questions of the standard, and what was seen before this registration

1. **Decision served:** whether the first read's shortfall is mostly these four execution gaps (then each gets validated on unused
   calls), or whether the next gaps must be tested: stop placement beyond one ADR / the structural stop, adds / pyramiding, exit
   timing, market exposure, and the EPs and parabolic shorts in his record. What to do with either is his.
2. **What would change it:** the fork in §7.
3. **Population:** the first read's, unchanged (§2), plus the later breaks of each walked base that V3 may re-enter on.
4. **What would make this wrong:**
   - (a) **In-sample choice.** The variants were picked after the first read's fills were seen (below). A lift here is an
     in-sample lift; it is validated only on calls not used here (era B, the sealed 2025–26 table, new stream labels).
   - (b) **V1's stop at an open fill.** When the stock opens above the level, the fill is the open, and the low of the day at that
     instant is the fill itself. The module's convention takes the first minute's low instead. That low is known only when the
     minute closes, so the stop is placed one minute late, and no stop-out can happen inside minute 0. The first read's ORH fills
     carry the same convention on their fill minute. **Its true size:**
     - every fill in minute 0 is exempt from a minute-0 stop-out by construction, because its stop is that minute's own low;
     - the too-wide skip reads the same low, so a fill whose first minute fell more than one ADR is skipped, and that loss is never
       booked;
     - the size reads it whenever the width is above 1% ÷ the cap (3.3% at COMBINED's 30% cap);
     - the effect favours V1 and COMBINED only, and COMBINED is the fork variant. An EXPLAINED reading will be questioned on this
       point first.
     - **The real run sizes it (printed, decides nothing):**
       - per V1 entry set, the fills at the minute's open and the trades stopped on day 0;
       - beside every V1 / COMBINED table, for his calls and the control: the fills and the too-wide skips whose stop is the fill
         minute's own low (minute 0, or a fill minute that made a new low of the day);
       - COMBINED's account curve and band share again, with every fill in minute 0 dropped from his calls and the control (§6).
     - **And it can make the stop near zero:** a first minute that never trades below its open puts the stop AT the open, 0.1%
       under the fill. Then 1R is a fraction of a percent and a 5% move reads as 50R. So **V1's and COMBINED's per-trade R is not
       in V0's unit.** The account and the band are the comparable numbers. The account bounds such a trade by the cap: 30% ×
       its width. The per-trade tables are printed again, beside, without stops under 0.25 × our ADR20 (#702's 10-22 floor), and
       the count of such stops is printed. The fork reads only the account and the band.
   - (c) **V3's "break" is our stream's, not his eye.** A tl retrigger is emitted on many consecutive days: his 236 calls have 775
     later rows of their own base within 20 sessions (dry run). So a re-entry is often the very next session.
   - (d) **V4 reads his "at most 30% in one stock" as a position ceiling.** His stated position range is 10–20%.
   - (e) Every caveat of the first read's §1.4 still holds:
     - 109 calls rest only on a label said on E;
     - the calls are a stream slice of his trades;
     - the joins are noisy, and 104 calls sit on a retrigger;
     - the rules are our reading of his article;
     - EPs and shorts are not in this read;
     - 2020 holds 156 of the 236 calls.
- **Seen before this registration (the first read's printout, 2026-10-23):**
  - the verdict EXECUTION / data, and every number in `01_replay.txt`;
  - 174 of 236 calls filled. 42 never traded above our level after the opening range (MRNA ×5, SHOP ×2, DKNG ×2, NVDA, AMD, ETSY,
    SPOT, NIO, JD, FSLY …). 20 were too wide (TSLA 2020-06-29, PTON, SHOP, COUP, FSLY …), with stop widths 3.9–15.4% of the fill;
  - 134 of 174 trades stopped out. 91 of those bases break again within 20 sessions of E (358 breaks; 33 of them are his calls);
  - 28 skipped for no room at the 20% cap; 2021 per trade −0.199R (his) vs +0.207R (control);
  - **the first read's `cap_30` beside row IS V4 alone:**
    - his curve: final 2.044, 2020 +62.8%, 2021 +26.2%;
    - the registered band at or above his final: 0.5% of the 200 draws.
    - **V4 alone is therefore NOT a new outcome.** It is re-run here as a parity check. (The brief that ordered this registration
      said no per-variant return exists yet; for V4 that is wrong, and this line corrects it.)
- **Not seen:** any number of V1, V2, V2b, V3, V4b or COMBINED.
  - The `pivot` row (V1's entry) is computed inside `cb.entry_variants` on every call. The first read never wrote it or walked it:
    its trade table holds the ORH5 / ORH1 / ORH60 rows only.
  - Per call, it is now possible to tell whether TC2000's ADR would pass a too-wide stop: the stop widths are known from the
    first read's recount, and the dry run prints the ADR at D. That count was not computed. §8 states the expectation instead.

## 2. POPULATION — the first read's, plus the re-entry rows

- **His calls, the control and the beside groups are the first read's, derived by its frozen code** (`01_replay.py`, pinned
  `c4478588…`, imported read-only) and asserted again by its `describe_population`:
  - era A: his calls n = 236 (127 strictly before E, 87 post-E-only beside);
  - the control: n = 23,188 same-day other tl breakouts (round-3 exclusion: 410 rows);
  - era B: n = 9 calls and 345 control events, descriptive.
- **The re-entry rows (V3), outcome-free, asserted by the module.** These are every later tl row of a walked base within 20 sessions
  of the walked event's E. Which ones a chain reaches depends on the stop-outs, so all of them are walked.

| era | rows in the window n | already one of the first read's events | new rows | new rows kept (fetch log ok, no identity break in (E − 130, E], walk wiring holds) | minute date files opened |
|---|---|---|---|---|---|
| A | 31,272 | 14,564 (0 of them excluded) | 16,708 | 16,708 | 584 (the first read's 193 + 391) |
| B | 638 | 102 (0 excluded) | 536 | 536 | 50 (8 + 42) |

- **Per group, era A** (a row can serve several events):
  - his calls: 185 of 236 have a later row of their base in the window (775 rows);
  - the control: 18,259 of 23,188 (70,354 rows);
  - post-E-only: 12 of 87 (36 rows).
- **560 rows are ones a CONTROL chain may never re-enter on** (§3).
- **Calendar:** every walk-set event has E + 121 sessions inside its era (0 run past 2022-06-30 / 2024-12-31), so no re-entry walk
  is cut by the end of the data.

## 3. CONTROL — the same day's other breakouts, under the same variant

- **Unchanged from the first read:** every other tl breakout on his calls' E dates, with the round-3 exclusion.
- **Every variant is applied to the control exactly as to his calls:** the same entry set, ADR rule, chain and sizing.
- **A control chain obeys the control's own rule on every re-entry row.** A row whose (stock, base) carries a matched label said on
  or before THAT row's E is never re-entered: the control stays "not shown on stream by that day". His chains, and the post-E-only
  chains, have no label rule.
  - **The asymmetry has a direction:** the 560 refused control rows can only lower the band, so they ease the band arm for his
    calls.
- **The band reuses the first read's 200 same-day draws** (seed 702, key `qm_replay|band|A|same-day (registered)`; on every date as
  many control events as his calls that day).
  - Each drawn control event is mapped to its trades under the variant: its own trade, or its whole campaign under V3 / COMBINED.
  - Each (ticker, E) counts once per draw.
  - The same draws under every variant make the variant-to-variant comparison paired.
  - Under V0 / V4 they reproduce the first read's band exactly, and this is asserted.

## 4. THE VARIANTS — each from his words (fixed now)

The exit is the same in every variant: the first read's primary `p33_s3_t10`, walked by `cb.walk_arms` unchanged. Sell 1/3 at the
session-3 close, move the stop to breakeven, and sell the rest at the next open after the first close under the 10-day average, with a
120-session horizon. Every fill pays 0.1% (`cb.ENTRY_SLIPPAGE_PCT`).

| variant | his words | the rule | code |
|---|---|---|---|
| **V0** (baseline) | the first read's | ORH5; stop = the low of the day at the fill; skipped when the stop is wider than OUR ADR20 at D; no re-entry; risk 1%, position cap 20%, 30% per stock, no margin | `cb.entry_variants(...)["orh5"]` |
| **V1** entry | *"Or simply buy as the daily chart starts to break out"* (the notes' summary of his article, written outside the quotation marks, so a paraphrase) | a buy-stop at the breakout level (the trendline projected to E, the candidate's `pivot`) from the open. It fills on the first minute whose high is strictly above the level: at the level, or at that minute's open when it opened above it (a gap at 09:30). Stop = the lowest minute low from 09:30 through the fill minute. Too wide on our ADR20; the rest is V0's | the module's own `pivot` row, `cb.entry_variants(...)["pivot"]` (SSoT: *"`pivot` = the first minute above the pivot"*) |
| **V2** stop width | *"stop should not be wider than the ATR or ADR of the stock"*, on HIS screen's ADR | ORH5 as V0. Too wide = width > TC2000's ADR% = mean(H / L) − 1 over the 20 sessions ending D, instead of ours (mean((H − L) / C)). Only the gate reads it; the walk keeps ours | `adr_pair`; `cb.entry_variants` called on each ADR |
| V2b (beside) | the same quote | the runner's CAP-NOT-SKIP: an entry too wide on OUR ADR is kept at its fill, the stop pulled up to fill × (1 − our ADR20), and the day-0 walk re-run on that stop | `cap_not_skip` (= `runner.cap_sensitivity`, parity tested) |
| **V3** re-entry | *"even if we need to retry"*; *"a reentry problem"* | ORH5 as V0, plus the chain below | `chain_of`, `campaigns` |
| **V4** sizing | *"positions 10-20% of the account; risk 0.25-1% a trade …; at most 30% of the account in one stock overnight"* | V0's trades; position cap 30%, risk 1%, 30% per stock, no margin | `Config("cap_30", cap=0.30)` = the first read's `cap_30` row |
| V4b (beside) | the same | the 30% cap at 0.5% risk | `Config(cap=0.30, risk=0.005)` |
| **COMBINED** | all four | V1's entry, V2's ADR gate, V3's chain, V4's sizing | entry set `level_tc`, chain, `cap_30` |
| COMBINED_r05 (beside) | — | COMBINED at 0.5% risk | — |

- **What V2 can and cannot do:** for every bar, (H − L) / L ≥ (H − L) / C, because L ≤ C. So TC2000's ADR is never below ours, and V2
  can only ADD fills. Every fill under our ADR must be the same fill under TC2000's, and the real run asserts this.
  - **The gap is small at the median, not at the maximum.** TC2000 sits above ours by a median of 0.22 percentage points on his
    calls (90th percentile 0.81), but by up to 8.5 points on his calls and 59.9 on the control and the re-entry rows.
  - **The 59.9 comes from one extreme bar inside the 20-day window:** ORPH on 2021-06-10, whose high is more than 15 times its low.
    One such bar lifts mean(H / L) by tens of points. On such an event TC2000's ADR is huge, so the V2 / COMBINED too-wide gate
    passes almost any stop.
  - **The dry run lists every event where TC2000 sits more than 2 points above ours**, by group, with the window's widest bar:
    - era A: 8 of his calls, 181 control events, 2 post-E-only events, 164 re-entry rows; era B: 1 control event;
    - the 3 control events and 3 re-entry rows above 50 points all sit on two bars: ORPH 2021-06-10 and SPI 2020-09-23 (high
      14 times the low). The next largest control gap is 12.6 points;
    - his 8 sit at 2.3–8.5 points, on bars that rose 49–196% from low to high (IHT, AHPIQ, AMC ×2, BTBT, XNET, WKHS, ACB).
- **Why TC2000's formula** (`scripts/probes/_705_grades_1022/03_frame_check.txt` §3): on 896 frames where the caption matched the
  screen, formula (mean(H / L) − 1) × 100 matched the ADR on his screen with a median error of 0.07 points, against 0.11 for ours.
- **V3's chain, rule by rule:**
  - A retry is earned only by a stop-out: `stopped` (the original stop, or the breakeven stop after the third) or `stopped_day0`.
    A trail exit, a horizon mark or a degraded walk earns none.
  - The re-entry is the next later tl row of the same (ticker, `base_id`) whose E2 is strictly after the exit day and at most the
    session E + 20, where E is the ORIGINAL call's (the window the first read counted in).
  - It is walked under the same entry set and stop rule, on that row's own level and its own ADR at its own D.
  - A row that does not fill, or that is refused (a data exclusion, or the control rule of §3), is passed. It uses no slot, and the
    chain moves to the next row.
  - At most 2 re-entries (filled trades) per call.
  - Each re-entry is its own trade in the account, sized like any other trade on the previous close's equity.
  - A re-entry that is itself one of the arm's own events is entered once (counted).
- **Not walked here:** ORH1 / ORH60, `pp` and the other exits, and any combination other than COMBINED.

## 5. MEASURES — the first read's, tail first (era A decides; era B, n = 9, descriptive)

- **Per trade** (mature walks only; R = fill − the entry stop):
  - ≥5R / ≥10R / ≥20R per 100 trades, max, worst, win rate, mean, median;
  - per 100 events beside;
  - every R headline also at 0.1% / 0.2% exit slippage per leg.
  - A chain variant's trades are every trade of every campaign, each (ticker, E) once.
- **Per event (V0, V3, COMBINED):** the campaign R = the sum of the call's trades. Each trade risks the same fraction of the account.
  A campaign counts only when every one of its trades is mature.
  - **The per-event numbers are not independent:** a re-entry that is itself one of the group's events (33 of the 358 later breaks
    of his stopped-out bases are his calls) lands in two campaigns, so the per-event table and the date-matched line count it
    twice. The account dedupes it, so the fork is untouched.
- **By year of the trade's E**, and the not-mature count with its booked R.
- **Beside, the near-zero-stop re-read (§1.4b):**
  - every per-trade row again, over trades whose stop is at least 0.25 × our ADR20;
  - per entry set, the count of stops under 0.25 × ADR20 and under 0.5% of the fill, with V0's counts for scale.
- **COMBINED on the splits:** first breaks / retriggers, the 127 strictly-before calls, one event per base, post-E-only
  (hindsight), and QQQ at D.
- **His minus control, DATE-MATCHED** (the first read's `paired_block_diff`, unchanged):
  - per event, the campaign R (a single trade when there is no chain);
  - each in its cell (the call's date, first break / retrigger), weighted by his filled mature campaigns;
  - month blocks, 2,000 resamples, seed 702, key `qm_exec|A|<variant>|mean R`; ≥10R per 100 beside.
  - V0 uses the first read's key `qm_replay|A|orh5|p33_s3_t10|mean R` and must print +0.543 [−0.132, +1.424] again (asserted).
- **Corporate actions:** the first read printed them for V0 and they are not repeated. G8 (§9) covers every trade.

## 6. ACCOUNT CURVE and BAND — the first read's simulation, unchanged

- **`rp.simulate`, called unchanged:**
  - start 1.0 at the close before the first E;
  - sized on the previous close's marked equity, position = equity × min(risk ÷ width, cap);
  - 30% per stock at cost, no margin (a trade that does not fit the free cash is skipped and counted);
  - the first read's order inside a day; each sell leg at its own price and date.
- **Configs:** V0–V3 at 1% / 20% / 30%; V4 and COMBINED at 1% / 30% / 30%; V4b and COMBINED_r05 at 0.5% / 30% / 30%.
- **Reported per variant:**
  - yearly return 2017–21, 2022 (exits only), final equity, max drawdown;
  - trades offered and how many are re-entries, entered, skipped for no room, skipped or trimmed by the stock limit, cap-bound;
  - max open positions, max gross exposure.
- **The band per variant (§3):** the 5th / 50th / 95th percentile of the 2020 and 2021 returns, the final equity and the max
  drawdown, and the share of draws at or above his (for max drawdown, as deep or deeper, which is worse).
- **Beside:**
  - COMBINED on the 127 strictly-before calls against their own band (the first read's strictly-before draws, key
    `qm_replay|band|A|strictly-before (beside)`);
  - era B's curve per variant;
  - **COMBINED with every fill in minute 0 dropped** (§1.4b), from his calls and the control alike. A dropped fill counts as not
    filled: a chain passes its row and an origin so filled has no campaign. Printed: how many of COMBINED's trades fill in minute
    0, his yearly 2020 / 2021 returns, final equity and max drawdown, and the share of the same 200 draws at or above his final,
    each beside the registered COMBINED. It decides nothing; the fork reads the registered COMBINED only.
- **THE BASELINE-PARITY GATE (real run, before any variant number is printed; a miss STOPS the run, exit 3).** V0 must BE the
  first read:
  - every ORH5 entry and p33_s3_t10 walk of the first read's 23,840 events (era A 23,484, era B 356) equals the first read's `trades.tsv.gz` (status, reason, fill, stop,
    fill minute, status, maturity, sessions held, R);
  - his primary and `cap_30` curves equal `account_his.tsv` day by day;
  - the band's five percentiles and its share equal `account_band.tsv` (primary and `cap_30`);
  - the re-entry count is 134 / 91 / 358 / 33, and the date-matched line reads +0.543 [−0.132, +1.424];
  - our ADR20 at D equals the stored one on every walked event;
  - every fill under our ADR is the same fill under TC2000's.
  - Without this gate, a wrong import would read as an "execution gap".

## 7. THE FORK — written now, before any variant outcome

| reading (era A; COMBINED = V1 + V2 + V3 + V4 at 1% risk and the 30% cap, applied to his calls and to the control) | → | the next work |
|---|---|---|
| his COMBINED curve returns **≥ +50% in BOTH 2020 and 2021** AND **at most 5% of the 200 band draws** (COMBINED applied to the control) end at or above his final equity | **EXPLAINED** — the execution gaps named here explain most of the shortfall | validate each variant on calls not used here (era B, the sealed 2025–26 table, new stream labels) before anything is built on it; any live use is his call (THE LINE) |
| anything else | **NEXT GAPS** — these four do not explain it alone | register the next gaps, each on its own: stop placement beyond one ADR / the structural stop, adds / pyramiding, exit timing, market exposure, and the EPs and parabolic shorts in his record. Never "the setup does not work" (his rule, 10-23) |

- **Each variant alone is printed beside, against V0 and against COMBINED,** for his calls and the control: tail first, the
  account by year, the band. No variant alone decides.
- **Read honestly — 2021 is the hard year.**
  - The first read's 2021 was +25.3% (V4 alone +26.2%, already seen).
  - In 2021 his calls lost per trade (−0.199R over 50 trades) while the control earned +0.207R.
  - At 1% risk with no cap binding, +50% in a year needs about 50R net. A capped trade risks less: 30% × its stop width.
- **Both the years arm and the band arm are printed apart**, so a NEXT GAPS reading says which one failed. A pass on the years with
  the band above 5% would mean these variants lift the same day's other breakouts as much as his picks.
- **What neither outcome shows:**
  - his returns (this is our walk of a stream slice of his calls);
  - that he traded these calls this way;
  - that a lift transfers out of sample, since these variants were chosen after seeing the fills;
  - anything about exits other than p33_s3_t10.

## 8. Expectations, written now (a miss changes no rule)

- **V1** fills nearly all of the 42 no-trigger calls: every call's high clears its level, and the 42 traded above it only inside
  the opening range. Some of the 20 too-wide calls fill too, because an earlier fill at the level has a different stop.
  - His fills rise from 174 to at least 210.
  - The stops are tighter (a median under 2% of the fill), and there are more day-0 stop-outs.
  - Some gap fills carry a near-zero stop, so V1's ≥10R rate and max R run above V0's for reasons of unit; the floored re-read
    sits much closer to V0. Per-trade mean R is uncertain.
- **V2** rescues at most 3 of the 20 too-wide calls. TC2000 sits only 0.22 points above ours at the median, while those 20 stops are
  3.9–15.4% wide.
- **V2b** brings in all 20 of his too-wide entries and the control's 1,502, with a one-ADR stop.
- **V3** adds about 100 to 180 re-entry trades to his calls (91 stopped trades had a later break). Per-trade mean R falls a little;
  the curve rises. The control gains less per event than his calls.
- **V4** reproduces 2.044 (2020 +62.8%, 2021 +26.2%, band share 0.5%).
- **COMBINED:**
  - 2020 above +50%; 2021 below +50%, so the expected reading is **NEXT GAPS**, with the band at or under 5%;
  - his COMBINED final above 2.044;
  - the strictly-before 127 read at or below all 236.
- **Era B** (9 calls, all losers in the first read) stays negative under every variant.

## 9. DATA GATE (STEP 0) and the point in time — the first read's, extended to the re-entry rows

- **Era A = `cb702_pre_v2`** (S0, G1–G7 and G9 PASS, pinned verdict). Era B = `cb702`: every row after 2024-12-31 is dropped at read
  and asserted.
- **G8 = this read's own trade list.** The union of every entry set's trades, re-entry rows included, each written as its own trade
  from its own E (`--kind r1` reads attempt 0 only, so each trade is written as attempt 0).
  - `trade_impact.py --cell p33_s3_t10 --cutoff 2024-12-31` runs on each era before any number.
  - Era A must read 0 entered after the cutoff and 0 holds past the last bar (asserted, else STOP). Era B is censored.
- **The re-entry rows' data rules** are the first read's: the fetch log decides minute coverage; an identity break in (E − 130, E]
  excludes; one after E cuts the forward window. Also the walk wiring: a bar on E, 130 consecutive sessions ending E, and D as the
  bar before E. The dry run excluded 0 rows in either era.
- **ADR at D:** both ADRs come from the 20 bars ending D, so nothing from E's bar enters the gate. Ours recomputed equals the stored
  `adr20` on every walked event (0 failures, tolerance 1e-12).
- **Point in time:** unchanged from the first read's §10.

## 10. Method / population — files, the module, its guards, the readings chosen

- **Inputs (pinned):**
  - every input of the first read, with its pins;
  - the first read's outputs, read by the parity gate in the real run only and hashed by the dry run: `trades.tsv.gz`,
    `account_his.tsv`, `account_band.tsv` under `apollo_data/cb702/qm_streams/qm_replay_1023/`, and `01_replay.txt`;
  - the first registration's text above its marker (`aaaadd29…`, its frozen `doc_body`).
- **Code (pinned):**
  - `scripts/probes/_705_qm_replay_1023/02_execution_variants.py`;
  - its tests `test_02_execution_variants.py` (39, synthetic). They cover:
    - V1 gap vs level fill, and the near-zero stop at an open fill;
    - the own-low flag of §1.4b (a fill in minute 0, a fill minute that made a new low, the same entry as a too-wide skip, a day
      whose first bar is not 09:30, a fill whose stop is an earlier minute's low), set on the V1 entry sets only, and the
      minute-0 drop;
    - V2's known answers, TC2000 ≥ ours, and too wide on ours but filled on TC2000 with the same fill; the window's widest bar and
      the 2-point listing;
    - V2b equal to `runner.cap_sensitivity`; V0's walk equal to the first read's `walk_event`;
    - the V3 chain (window, strictly after the exit day, refusals and no-fills using no slot, max 2, no retry after a trail, an
      unfilled call); the control rule; the union dedupe with each re-entry its own trade in the account; campaign R;
    - V4's 30% cap; the fork; the NEXT GAPS list word for word with §7's row and §11;
    - the walk-wiring and event facts; each era's own bars; the line-anchored freeze lock; the parity readers;
    - an end-to-end run that first runs the frozen first read on the same world, then passes the parity gate and prints the §1.4b
      lines (the own-low counts beside every V1 / COMBINED table, and COMBINED with minute-0 fills dropped); and one where a
      tampered first-read R stops the run;
  - the frozen `01_replay.py` and `test_01_replay.py` (`c4478588…`, `37c918a0…`), imported read-only;
  - the runner, the cb module, `constants.py`, the Track A fit and join modules, `aplus_read.py`, `registered_read.py`,
    `trade_impact.py` (the first read's pins).
- **The module's guards:**
  1. **Freeze lock, line-anchored:** the doc-body hash covers every byte above the ONE line that is exactly the freeze marker. Zero
     such lines, or two, refuses (exit 2). The marker text appears nowhere else in this document.
  2. Refuses (exit 2) if `02_execution_variants.txt`, a STOPPED file or any output under
     `apollo_data/cb702/qm_streams/qm_exec_1023/` exists.
  3. Populations asserted (the first read's EXPECT) and the re-entry rows asserted (`EXPECT_SUPERSET`, §2); a miss stops before any
     minute file is opened.
  4. G8 before numbers; the baseline-parity gate before numbers.
  5. Per trade, the R recomputed from the dated legs equals the walk's own (the first read's `make_trade`).
  6. A crash after the walk writes a STOPPED file with the traceback (never a silent re-run).
- **Readings chosen where the brief was open (B = this registration's choice):**
  - **R1:** V1 is the module's `pivot` row unchanged, including the one-minute stop convention at an open fill (§1.4b).
  - **R2:** V2 changes only the too-wide gate; the walk passes our ADR (it feeds only the ADR-unit column, not R).
  - **R3:** V2b uses OUR ADR, as the runner's CAP-NOT-SKIP does, not TC2000's.
  - **R4:** V3's window runs from the ORIGINAL E (the brief's wording and the first read's count). #702's 10-22 retry read ran its
    window from the stop-out instead.
  - **R5:** V3's "break" = a later tl row of the same (ticker, `base_id`) in the stream. #702 used a close above the base high.
  - **R6:** a breakeven stop after the third earns a retry ("stopped out", as #702 read it).
  - **R7:** at most 2 FILLED re-entries; a passed row uses no slot.
  - **R8:** a control chain obeys the round-3 rule on each re-entry row's own E; his and post-E-only chains have no label rule.
  - **R9:** each (ticker, E) at most once per account and per band draw.
  - **R10:** campaign R = the sum of its trades' R; the date-matched cell is the call's date and stratum.
  - **R11:** the band reuses the first read's draws (paired across variants).
  - **R12:** V4 = a 30% POSITION cap at 1% risk, with the per-stock limit still 30% and no margin.
  - **R13:** era B is descriptive (9 calls).
  - **R14:** G8 covers every walked trade of every entry set, each written as attempt 0.
  - **R15:** V0 is re-walked and gated against the first read's stored outputs.
  - **R16:** the near-zero-stop re-read is beside only, at #702's 0.25 × ADR20 floor. No trade is removed from the account, the
    band or the fork.
  - **R17:** "minute 0" (§1.4b, §6) = the day's first minute bar, which is 09:30 whenever the stock traded then. That is where the
    stop exemption is built in. The own-low counts and COMBINED with minute-0 fills dropped are beside only: no trade is removed
    from the account, the band or the fork.
- **Outputs (real run):**
  - `scripts/probes/_705_qm_replay_1023/02_execution_variants.txt`;
  - under `apollo_data/cb702/qm_streams/qm_exec_1023/`: `trades.tsv.gz` (one row per event × entry set), `chains.tsv` (every
    campaign of V3 / COMBINED), `g8_{A,B}.tsv`, `g8_{A,B}_impact.txt`, `account_his.tsv` and `account_band.tsv`.
- **Cost:** $0 — local compute only, no paid API. The dry run takes about 10 s; the real run walks about 40,300 era-A events once.

## 11. What this does not answer

- **His actual returns.** This is our walk of a stream-confirmed slice of his calls under our reading of his rules. His record also
  holds EPs, parabolic shorts, adds, his own fills and his own sizing.
- **Whether a variant generalizes.** All four were chosen after the first read's fills were seen. A lift here is in-sample until
  it holds on era B, the sealed 2025–26 table or new stream labels.
- **Stop placement beyond one ADR / the structural stop.** His 10-22 note names *"a stop placement problem"*, and its table marks
  a stop wider than one ADR, and the uncapped base-low stop, NOT TESTED. Both stay untested here: V2 only swaps the ADR formula
  under the same one-ADR skip, and V2b caps the stop at one ADR. It is the first of the next gaps (§7).
- **Exit timing.** Only `p33_s3_t10` is walked; the other exits are the next gaps if this read routes there.
- **Adds / pyramiding and market exposure.** Neither is modelled; both are next gaps.
- **Whether our stream's retrigger rows are the breaks he would re-buy.** A row is emitted on many consecutive days (§1.4c).
- **2022+ beyond 9 descriptive calls, and anything about 2025–26** (sealed, unread).

<!-- FREEZE -->
## Freeze record

Empty until the freeze commit. The main loop pastes, below the freeze marker line above, every pin that
`02_execution_variants.py --dry-run` prints under "## Pins (sha256)", including `doc_body` (the sha256 of the bytes above that line).
It then commits, and then runs `python3 scripts/probes/_705_qm_replay_1023/02_execution_variants.py` once. Any edit above the marker
line after that changes `doc_body`, and the run refuses.

Recovery after a STOPPED run: a stop after the walk leaves files under `apollo_data/cb702/qm_streams/qm_exec_1023/`, and each one
blocks a re-run. Recovery = fix, delete `02_execution_variants.STOPPED.txt` AND those files, and re-freeze if the module changed.
Any outcome the stopped run printed is recorded as seen.

### FREEZE 2026-10-23 (this commit; the one real run follows it)

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
- first_doc_body: aaaadd295aba5a9de534a738410ebe391ac4993637faa7ead0cab78e2b7a9dab  the first registration's text above its marker (frozen)
- minutes_A_used: eae318e06d192fcfa4042a1f18efe5338d018185be3c4b7a56284af8b8577643  the 584 minute date files the walk set opens
- minutes_B_used: fe83918a9f5d318cc1bd50e0390cded203ac721eab3b68dbb1d9dcfa382ccde8  the 50 minute date files the walk set opens
- doc_body: 329ac865f814de0909332ff516ea5d52dea525fbef7b5fdcf1c9208a521143fe  this registration's text above its marker line

## RESULT — the one real run, 2026-10-23 after the freeze commit (printout `scripts/probes/_705_qm_replay_1023/02_execution_variants.txt`)

- **Registered verdict: NEXT GAPS.** COMBINED (V1 + V2 + V3 + V4) at 1% risk / 30% cap: 2020 +38.5%, 2021 +13.7%, final 1.507;
  the same-day band at or above it in 10.0% of draws. Baseline parity held (V0 re-walked = the first read, day by day).
- **The fixes as written made his calls WORSE, except the size cap:** V0 (his rules) 1.850 → V1 buy-stop at the level 1.268, V2
  TC2000 ADR 1.838, V3 re-entries 1.631, **V4 30% cap 2.044** (the only gain), COMBINED 1.507.
  - V1 fills 216 of 236 (42 more), but the win rate falls to 21.8% and 2021 to +0.8%: the extra fills are mostly gap-and-fade
    opens. The control's V1 row (max +590R, worst −94R) is the minute-0 own-low stop convention at work (§1.4b) — not a result.
  - V3: 114 re-entry trades at a lower mean R (+0.32 per trade) and 58 skipped for no room.
- **Read with it:** these variants were chosen after the first read's fills were seen; none is validated. The registered next
  gaps, in his words and the operator's: stop placement beyond one ADR / the structural stop, adds / pyramiding, exit timing,
  market exposure, and the EPs and parabolic shorts in his record. Independent recount (Sonnet, `verify/recount_exec/recount_exec.py` + `_out.txt`, from the stored trades, simulation re-implemented): 50 of 50 checks match. The V1 control extremes are the minute-0 own-low stop: 9 of the 10 largest |R| fill in minute 0 with a stop of 0.1–0.2% (six are the 0.1% slippage alone); minute-0 fills are 352 of the 400 trades beyond ±20R. In the account these trades are cap-bound, so the account and band are the comparable numbers.
