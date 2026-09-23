# #545 Phase 3 — the day-1 stop × target × runner sweep, replayed (2026-09-03)

**Read-only · $0 · pre-registered in `docs/design/545_entry_exit_program_v2_2026-09-02.md` §7 Phase 3
(the pass bar there was not moved) · harness `scripts/ep_replay.py` (validate PASS after the build,
same 44/44 · 33/33 · 29/30 · 25/30 as the 09-01 baseline) · sweep `scripts/probes/_545p3_sweep.py`
→ `_545p3_report.txt` + `_545p3_cells.tsv` (captured once) · tables `_545p3_tables.py` →
`_545p3_tables.md`.** ⚖ THE LINE: evidence and a ranking only. Nothing live was touched; any change
is CHANGE_PROCESS + the #151 harness + operator sign-off.

## 0. The answer, and the pass-bar verdict per cell

**On the names the current selector admits, the day-1 answer is the OPPOSITE of the day-2+ band: the
tighter the stop, the more money — and a stop at 0.5 × the stock's normal daily range (ADR), which is
about the width of the ORB low the operator retired on 08-16, clears every pre-registered criterion
against the live `entry − 2R` stop.** Paired on the 65 admitted campaigns that settle under the live
stop: **+14.2R** (55 pairs; **+4.6R even if every one of the 10 campaigns it cannot settle at 1-minute
grain — 9 fill-minute straddles and one same-day stop-and-target — had lost a full 1R**), +14.1R vs
−2.6R with May removed (46 / 51 campaigns), +19.5R vs +4.4R in August alone, **+4.3 in size-free ADR
units** (so it is not a position-size effect), and **four ≥4R winners (HTFL +7.2, PLTR +5.4, ABCL +4.5,
ARGX +4.2 — all August) where the live stop has none.** One sensitivity decides how clean that is: the
alert grid runs with the live `stop_too_wide` gate OFF (§1), and HTFL is a name live refused. Remove
the three gate-refused names (CORT, ATRO, HTFL) and 0.5 × ADR is **+8.5R paired (54), bound +0.5R**,
ex-May +11.7R, +4.3 ADR-units, three ≥4R — positive on every criterion, with the pessimistic bound at
zero. **The ORB low itself is the more robust of the two: +11.4R paired (bound +5.0R), and +10.3R /
bound +3.9R without the gate-refused names.** The day-2+ band's 1.0 / 1.25 × ADR stops lose (−2.2 /
−4.2R); 0.75 × sits between (+3.3R, bound +1.2R; +0.7R / −0.5R ex-gate). The order is monotone:
tighter wins.

**Why every earlier read said the opposite:** pooled over ALL 267 alerts the live stop looks best
(+11.3R on 99), and that whole margin is carried by names the current scorer REJECTS — the 21 settled
rejects are **+13.1R under the live stop (AMBQ +9.3 alone)** and lose under every tighter stop. On the
admitted 65 the live stop is **+3.5R, zero ≥4R, −2.6R ex-May.** The 08-16 widening (§2) did what it
was measured to do on the 22 names it replaced — fewer entry-day deaths, +2R at equal risk — by turning
deaths into +0.33R scratches; on the population the selector now produces it costs the winners.

**No runner rule passes.** t3 (sell the 2/3 at the third close after the partial) beats the live ladder
by +16.1R on all 55 partial-takers and +17.6R on the 35 admitted ones, and it does it the way #2 said:
three names carry 80% (FTK +6.1, RDW +3.5, EROC +3.4), 25 of 55 takers are worse, 14 of the 26 live
+0.33R scratches turn negative. Ex-May admitted takers are 25 — under the bar. Direction, not a pass.

**Retries lose at the live stop in every form** (−7.7 / −10.0 / −9.1R on the second leg; 55–65% of
fires pay a second stop). At a tight stop two signals are positive and both are THC alone.

| cell | verdict | why (one line) |
|---|---|---|
| `entry − 2R`, target pinned, live ladder (LIVE) | baseline | all alerts: +11.3R on 99, one ≥4R (AMBQ, a rejected name), −6.1R ex-May (n=67, 0 ≥4R). **Admitted only: +3.5R on 65, 0 ≥4R, −2.6R ex-May (n=51).** 26 of 54 partial-takers scratch at exactly +0.33R |
| **0.5 × ADR, pinned** | **positive on every pre-registered criterion on the admitted population (n ≥ 30, ex-May, size-free, joint with the target); the pessimistic bound is +0.5R once the names live's `stop_too_wide` gate refuses are removed — the strongest ADR cell on the board, a CHANGE_PROCESS candidate for the operator's Phase 6 fork with a bound at zero and §5b's four caveats** | admitted: +14.2R paired (55), bound +4.6R, ex-May +14.1R (n=46, 4 ≥4R), August +19.5R (n=28), +4.3 ADR-units paired; own-unit target agrees (+19.1R). Ex-gate: +8.5R (54), bound +0.5R, ex-May +11.7R, 3 ≥4R. All alerts: +8.3R paired, bound −5.2R (the rejects) |
| ORB low (the retired stop), pinned | **passes the same bar on the admitted population with the bound clear of zero even ex-gate (+3.9R); conflicts with the 08-16 read it was retired on — surfaced, not resolved (§11)** | admitted: +11.4R paired (58), bound +5.0R, ex-May +7.8R (n=46, 2 ≥4R), +3.7 ADR-units; ex-gate +10.3R (55), bound +3.9R; all alerts −3.8R paired, bound −14.3R |
| 0.75 × ADR, pinned | marginal — positive but the bound is +1.2R | admitted +3.3R paired (62), ex-May +6.5R (n=50, 2 ≥4R); all alerts −10.7R |
| 1.0 / 1.25 × ADR, pinned (the day-2+ band) | **FAIL** | admitted −2.2 / −4.2R paired, 0 ≥4R; all alerts −13.8 / −16.0R; worse in ADR units on both populations |
| any stop with the target moving with it (08-06 frame) | FAIL, mechanism confirmed | every wide stop gets worse when its target moves (adr 1.0: −4.3 → −9.3R; partials 50 → 31); the pin is worth +5R to the live stop and all of it is +0.33R scratches |
| runner: t3 · t5 · gb25 · atr1 · atr2 | direction only, no pass | beat the ladder on the sum pooled, ex-May and admitted; 3-name-carried; win rate on takers 100% → 61–76%; worst taker +0.15R → −0.36…−1.63R; admitted ex-May takers n=25 |
| runner: breakeven · hard · sma20 · t10 · t20 | FAIL | −13 to −36R vs the ladder on the same 55 takers |
| attempt 2 at the live stop (3 signals) | FAIL | second leg −7.7 to −10.0R; ex-May campaign sums −12.2 / −15.6 / −10.7R vs −6.1R one attempt |
| attempt 2 at a tight stop (ORB low · 0.5×ADR) | FAIL, THC-carried | +4.7 / +3.2 / +1.5R with THC, −5.7 / −9.0 / −10.7R without; 55–79% of fires pay a second stop |

**Ranked recommendation (evidence for the operator's Phase 6 fork "an ADR-anchored day-1 stop in the
pinned frame"; nothing pre-decided, nothing changed):**
1. **A tight day-1 stop — 0.5 × ADR or the ORB low itself, pinned +2R target, live ladder — is the one
   thing on the board with a number that clears the bar** on the current selector's names, at
   1-minute grain, bounded (ORB low bound +3.9R ex-gate; 0.5 × ADR +0.5R). It is his call: it reverses
   the 08-16 direction on a different population (§11 states the conflict and the selection-conditional
   reading), 56% of the 0.5 × ADR stops sit inside the opening range, and a stop that tight lives or
   dies inside the fill minute on 9 of 65 campaigns (already priced in the bound). A live shadow arm or tick data is the
   next-cheapest evidence; the #616 recorder pattern (record the counterfactual stop on every live
   fill) would make it forward-readable at $0.
2. Keep the pinned target whatever the stop — the joint check (§6) says the pin is what makes any
   stop tolerable, and a tight stop's own-unit target agrees with it.
3. Post-partial time / giveback / ATR exits point the same way as #2 and now hold ex-May — but n = 25
   admitted takers ex-May and three names deep. Not a candidate; re-read when runners exist.
4. Retries: closed at n = 41–56 by the same shape as n = 15 — do not re-run without a new signal.

---

## 1. Method / population — which rows, what window, what the harness does and does not see

**Population:** the 270 live-source `mi_ep_alerts` rows 2026-05-11 → 08-28 in the 09-01 capture
(`scripts/ep_replay_data/_pull2_out.txt`) = **267 distinct campaigns** — MANE 07-15, KMT 08-05 and
ACMR 08-07 were inserted twice within a millisecond (same score, same tier) and are one campaign
each; the harness's own `replay` still prints 270 rows. Every campaign is RE-SCORED under the CURRENT
admission stack (era C: separated score, bar 65 — **142 admit · 81 reject · 44 undecided** because
the float bonus is not a stored fact) but **ALL 267 are walked**; the `admit` verdict travels on every
row, and §5 reads the grid twice — all alerts, then admitted only (P8: every downstream number is
conditional on selection). Under the control the 99 settled split **65 admitted · 21 rejected · 13
undecided**. Every cell walks under the CURRENT exit stack (10:00 unfilled-cancel,
+2R partial 1/3, breakeven at the broker, the stock's-own-closes SMA trail), varying ONE axis. Minute
bars: `_pull4_min.tsv.gz` for the alert day; `scripts/probes/_562bf_minute.tsv.gz` (245 tickers,
05-08 → 08-31) ONLY for later sessions (the attempt-2 leg), so every day-1 number and `validate` are
byte-identical to the primary capture. Daily bars: `mi_daily_closes` from 2026-01-01. Horizon: last
settled session 2026-08-31; a campaign still open then carries a **mark**, labelled, never a return.

**The `stop_too_wide` gate is OFF in the alert grid** — the alert rows carry no ATR, so
`validate_orb_entry` sees `atr_14=None` and only the zero-range check runs (the 4 `setup:` rejects).
Deliberate for Phase 2 (read the names live skipped), but for a stop verdict it means every cell holds
names live would refuse: among the 65 admitted control-settled campaigns three have an ORB range over
1.5 × ATR14 by the daily-bar arithmetic — CORT 07-30 (1.58×), ATRO 08-12 (1.63×), HTFL 08-14 (1.75×,
the +7.2R under 0.5 × ADR) — and §5b reports every tight-stop delta with and without them.

**The control:** `entry − 2R` (= `2·orb_low − orb_high`), +2R target pinned to `entry − orb_low`
(`profit_target_r_per_share`), live ladder. Of 267: **99 settled · 2 open (MRNA 08-19, OKTA 08-27) ·
35 no entry · 46 abstain (17%) · 85 never a trade** (81 detected at/after 09:45 → `window_out_of_orb`,
4 `setup:` rejects). Every cell is compared PAIRED on the control's 99 settled campaigns; a cell's row
that abstains or is open is dropped and counted, and the "if every dropped row were −1R" column bounds
what the drop can hide.

**Units:** every cell is sized to 1 risk-dollar on ITS OWN stop (`shares = 1 / (entry − stop)`), so
its R is dollars at equal risk per trade — the only unit in which stops of different widths compare.
Beside it, **ADR-units** = P&L per share ÷ the stock's 20-day ADR in dollars: size-free, the column
that exposes an R-unit effect. ADR$ = mean (high − low)/close over the 20 sessions strictly before the
alert × the ORB high (the pre-fill entry proxy live itself uses in `entry − 2R`); the day-2+ lane
(#616) anchors ADR$ on the EP-day close, which is unknowable at 09:31 — stated as the one difference.

**Splits, with n stated:** pooled (99) · ex-May (67 — May is the era the operator ruled stale, and May
alone is +17.4R of the control's +11.3R) · August (41 settled — the post-partial exit era; the current
ADMISSION era (≥ 08-22) has only 3 settled campaigns and is unreadable). **Era-C n on every exit-side
number is 3 settled, 1 open.**

**Harness deviations that matter here (all stated, none silent):**
- The day-3/5 ladder partial is now ERA-SWITCHED (`RuleSet.ladder_partial`): live has stood it down
  since 08-01 (`live_tracker.py:1076`, `skip_partial_decision=bool(PROFIT_TRIGGER_R)`); the harness
  had been booking it. Fixed this card; **14 of 267 campaigns moved** (CORT, ATRO, APPS flip from small
  wins to small losses; KLAR, CSCO, SIBN, STUB, THC, HTFL improve; KTOS, PRGO, AEVA, PUBM worsen); the
  headline did not: 99 settled, +11.4 → +11.3R, median +0.30 → +0.33, one ≥4R. `validate` unchanged.
- A runner rule replaces the ladder only AFTER the partial; before it every rule shares the live ladder,
  so the runner grid is a same-trade comparison. The #2 lineage's `live_trail_be` (breakeven +
  close-below-SMA) differs from the real ladder on 15–28 of 267 campaigns per stop because the ladder
  ALSO rests yesterday's trail level as a touch stop — a fidelity gap in #2, closed by using `live`.
- The attempt-2 leg fires only after a FULL stop-out (no partial banked), in the same session
  (5-minute-range clear) or the next (open after the first five minutes / open with the stop-day low),
  each leg its own 1R, the campaign the sum. A leg whose fill bar straddles its own stop ABSTAINS
  (#5 continued it optimistically) — this is why CRCL fires in #5 and not here.
- Not seen: slot competition, the daily-loss limit, breakers, spread/venue refusals, sub-minute order
  inside a bar (the abstains), the LLM judge (stored grades are facts).

---

## 2. Prerequisite 2 — did the 08-16 widening work? (era-matched, on the 22 trades it replaced)

The 22 pre-2R closed live trades (07-06 → 08-14), re-walked from their STORED ORB under the current
stack, equal dollar risk per cell, first attempts. (Live recorded: 16 of 22 died on the entry day.)

| stop (target pinned, live ladder) | decidable | died on entry day | sum R (equal $ risk) | ≥2R | partial fired | scratched at +0.33R | abstain |
|---|---|---|---|---|---|---|---|
| era-matched replay (ORB low, no partial pre-08-01) | 19 | **13 (68%)** | −6.9 | 3 | 4 | 0 | MANE, HUT, FRMI |
| live as recorded (same 22) | 22 | 16 (73%) | −7.7 | 2 | — | — | — |
| **`entry − 2R` (live since 08-16)** | 22 | **12 (55%)** | **−4.8** | 0 | 10 | 6 | — |
| 0.5 × ADR | 20 | 13 (65%) | +3.2 | 3 (PLTR +5.4, ABCL +4.5) | 8 | 0 | WDFC, WKC |
| 0.75 × ADR | 21 | 12 (57%) | −0.3 | 2 | 10 | 2 | WKC |
| 1.0 × ADR | 21 | 12 (57%) | −3.0 | 2 | 10 | 0 | NVCR |
| 1.25 × ADR | 21 | 8 (38%) | −4.6 | 1 | 10 | 0 | NVCR |

- **Answer: the widening cut entry-day deaths from about three in four to about one in two (16 → 12
  of 22) and improved the 22 by about +2R at equal risk — by turning six deaths (MANE, SMCI, NVCR,
  QBTS, TEAM, THC) into five +0.33R scratches and one +1.1R.** It created no winner: the three real
  winners (PLTR, ABCL, ETON) halve in R because the unit doubled (+3.4 → +1.7, +2.7 → +1.4, +2.0 → +1.0).
- The live era-C split (1 of 4 died day 1) is inside the noise of the era-matched 55%: the honest
  current-stack death rate on these names is about one in two, not one in four.
- The wider ADR stops die LESS on day 1 (1.25×: 8 of 21) and lose MORE money (−4.6R) — the 08-06
  "survival is delay" mechanism, reproduced in the pinned frame: they die on day 2–5 at a wider stop.
- Per-name fates are in `_545p3_report.txt` §1 (S = died day 0, P = partial banked).

## 3. Prerequisite 1 — the baseline on disk, verified, and what was wrong about it

- `campaigns_era_c.tsv` (09-02 build): **100 settled rows · mean +0.12R · median +0.31R · sum +11.8R ·
  one ≥4R (AMBQ +9.3) · six ≥2R · 41 losers — verified.** Without AMBQ: +2.4R on 99 = break-even.
  One in a hundred converts to ≥4R.
- **Wrong in the design doc §2:** "open_at_horizon 87 — the settled mean is censored." Only **2** are
  open (MRNA, OKTA; marks +1.9R); **85 are `no_trade`** — 81 alerts detected at/after 09:45 that the
  ORB window never submits, 4 setup rejects. The censoring caveat is overstated ~40×; the real
  population fact is that only 182 of 267 campaigns were ever submittable.
- 270 rows = 267 campaigns (three same-millisecond duplicate inserts).
- After the ladder-partial fix the baseline is 99 settled · +11.3R · median +0.33 · one ≥4R · 43 losers.

## 4. Prerequisite 3 — why BAND 04-30 and STRL 05-05 are "not replayable"

- Neither was ever a live-source `mi_ep_alerts` row. In the 09-02 capture 2 (`_545p2_capture2_out.psv`
  `STOP_TOO_WIDE_ALL`) both sit in `mi_ep_missed_outcomes` as `scan_filter` rows whose CURRENT reason
  is `session_rvol_low` (BAND) and `duplicate_scan` (STRL) — they left the `stop_too_wide` bucket and
  carry only the historic flag.
- No ORB, no minute bars, no daily bars for them in any `ep_replay` capture (alerts start 05-11; the
  minute pull is keyed to alert/trade ticker-days; DAILY covers cohort tickers only). `mi_intraday_bars`
  stores alert ticker-days, so the expectation is zero rows in prod too. Their +110% / +32% are 20-day
  daily marks on names with no bracket to walk.
- **Consequence:** the `stop_too_wide` bucket's "2 of 10 mature = 20% tail → candidate" (Phase 2) rests
  on two names that cannot be walked through any bracket and are no longer in the bucket. The four
  in-capture `stop_too_wide` fills (CORT, ATRO, AEVA, HTFL) sum to +0.5R under the live path. The
  bucket verdict should read "n = 0 replayed" until the probe below says otherwise.
- **Probe (read-only, one run):** `scripts/probes/_545p3_band_strl_bars.sql` — minute-bar presence for
  the two ticker-days, the daily open gap (did they gap at the open), and their alert / missed rows.
  `ssh apollo@87.99.134.162 "docker exec -i apollo-postgres psql -U apollo -d apollo -A -F '|'" < scripts/probes/_545p3_band_strl_bars.sql > scripts/probes/_545p3_band_strl_out.psv`

---

## 5. The stop grid — target pinned, live ladder (267 campaigns)

R = each cell's own unit at equal dollar risk. ADR-units = size-free. Open rows carry marks, shown apart.

| stop | median width (ADR) | settled n | sum R | ≥4R | ≥2R | P90 | ex-best | median | win | ADR-units | open / marks | abstain |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| ORB low | 0.59 | 92 | +4.1 | 4 | 10 | +2.01 | −1.9 | −1.00 | 38% | −4.9 | 2 / +3.9 | 53 |
| **`entry − 2R` (live)** | 1.17 | 99 | **+11.3** | 1 | 6 | +1.35 | +2.0 | +0.33 | 57% | +2.3 | 2 / +1.9 | 46 |
| 0.5 × ADR | 0.50 | 86 | +19.1 | 5 | 11 | +2.88 | +9.1 | −1.00 | 44% | +9.5 | 0 | **61** |
| 0.75 × ADR | 0.75 | 98 | −0.6 | 3 | 9 | +1.92 | −7.3 | −1.00 | 46% | −0.6 | 1 / +3.3 | 48 |
| 1.0 × ADR | 1.00 | 101 | −4.3 | 1 | 7 | +1.47 | −9.4 | +0.06 | 50% | −4.4 | 2 / +3.1 | 44 |
| 1.25 × ADR | 1.25 | 102 | −6.7 | 1 | 5 | +1.54 | −10.8 | +0.07 | 53% | −8.5 | 2 / +2.5 | 43 |

**Ex-May (the era the operator ruled stale removed):**

| stop | settled n | sum R | ≥4R | ≥2R | ex-best | median | win | ADR-units |
|---|---|---|---|---|---|---|---|---|
| ORB low | 61 | −3.8 | 2 | 7 | −8.9 | −1.00 | 34% | −3.0 |
| **`entry − 2R` (live)** | 67 | **−6.1** | **0** | 3 | −8.6 | −0.10 | 49% | −5.2 |
| 0.5 × ADR | 59 | +6.9 | 4 | 7 | −0.3 | −1.00 | 41% | +3.3 |
| 0.75 × ADR | 66 | −4.3 | 2 | 7 | −9.2 | −1.00 | 42% | −3.3 |
| 1.0 × ADR | 67 | −5.8 | 0 | 6 | −9.5 | −1.00 | 46% | −6.0 |
| 1.25 × ADR | 68 | −7.7 | 0 | 4 | −10.7 | −0.27 | 49% | −9.8 |

**Paired on the control's 99 settled campaigns (the only honest comparison):**

| stop | pairs | dropped by the cell | ΔR vs live | better / worse | Δ≥4R | if every dropped row were −1R |
|---|---|---|---|---|---|---|
| ORB low | 89 | 10 | −3.8 | 37 / 20 | +3 | −14.3 |
| 0.5 × ADR | 83 | **16** | **+8.3** | 32 / 22 | +4 | **−5.2** |
| 0.75 × ADR | 94 | 5 | −10.7 | 30 / 34 | +2 | −13.0 |
| 1.0 × ADR | 97 | 2 | −13.8 | 26 / 41 | 0 | −16.0 |
| 1.25 × ADR | 98 | 1 | −16.0 | 22 / 46 | 0 | −17.4 |

- **The live stop is the widest thing on the board** — median 1.17 ADR (0.17–2.88): the 08-16 change
  doubled a stop that was already half a normal day (ORB low 0.59) into more than a full day. On the
  day-2+ rungs the working band was 0.75–1.25 ADR; on day 1, in the pinned frame, that band is the
  bottom of the table and monotone: the wider the ADR stop, the more money lost (ADR-units −0.6 → −8.5).
- **0.5 × ADR is where the tail lives** (5 ≥4R: AMBQ +10.1, HTFL +7.2, PLTR +5.4, ABCL +4.5, ARGX +4.2;
  4 of 5 ex-May) — the same moves as under the live stop (HTFL +1.4, PLTR +1.7, ABCL +1.4) held with a
  position 2–3× bigger at the same dollar risk. That is legitimate IF the stop survives the fill minute,
  and on 16 of the control's 99 campaigns it cannot be ordered at 1-minute grain (15 fill-bar straddles
  + FIG's same-day stop-and-target; the control lost 9 of those 16 and banked 7). On all alerts the
  cell is therefore bounded: +8.3R paired, −5.2R if every undecidable row lost 1R. Its 61 abstains
  (23%) stay under the harness's 30% ceiling.
- **A stop that tight is inside the opening range on most days:** 0.5 × ADR sits ABOVE the ORB low on
  59 of 105 entered campaigns (56%); 0.75 × on 40 (38%); 1.0 × on 17 (16%); 1.25 × on 6 (6%). The ORB
  low's median width is 0.59 ADR, so 0.5 × ADR is, on the median campaign, the retired stop or tighter.
- August only (41 settled, the post-partial exit era): live −1.4R (0 ≥4R), 0.5×ADR +16.0R (4 ≥4R, 11
  abstain), 0.75×ADR +6.9R (2), 1.0× +1.3R, 1.25× +0.9R — the same ordering, on the recent tape.

### 5b. The same grid on the names the current selector ADMITS (P8) — the read that decides

The era-C scorer admits 142 of the 267 alerts (81 rejected, 44 undecided on the float bonus). Under
the control 65 admitted campaigns settle. Paired on those 65:

| stop | settled | sum R | ≥4R | pairs | **ΔR vs live** | if every dropped row were −1R | ΔADR-units (size-free, paired) | ex-May n / sum / ≥4R | Aug n / sum |
|---|---|---|---|---|---|---|---|---|---|
| ORB low | 59 | +14.5 | 4 | 58 | **+11.4** | +5.0 | +3.7 | 46 / +7.8 / 2 | 27 / +14.2 |
| **`entry − 2R` (live)** | 65 | +3.5 | **0** | 65 | — | — | — | 51 / **−2.6** / 0 | 30 / +4.4 |
| **0.5 × ADR** | 57 | +16.1 | 4 | 55 | **+14.2** | **+4.6** | **+4.3** | 46 / **+14.1** / 4 | 28 / +19.5 |
| 0.75 × ADR | 64 | +5.7 | 2 | 62 | +3.3 | +1.2 | +1.7 | 50 / +6.5 / 2 | 31 / +13.9 |
| 1.0 × ADR | 66 | +1.8 | 0 | 64 | −2.2 | −3.1 | −1.0 | 51 / +0.7 / 0 | 31 / +9.6 |
| 1.25 × ADR | 67 | −0.4 | 0 | 65 | −4.2 | −4.2 | −2.9 | 52 / −0.3 / 0 | 31 / +9.4 |

And the mirror — the 81 alerts the scorer REJECTS (21 settle under the control): the live stop is
**+13.1R** on them (AMBQ +9.3, ABVX +2.1, BW +1.7) and every tighter stop is worse by −4.6 to −12.5R
paired. **The all-alert headline that made the live stop look best is the rejected names' headline.**
With the 44 undecided added back (186 alerts, 78 settled): 0.5 × ADR +12.9R paired (bound +1.3R),
ORB low +8.6R (bound +2.2R), 0.75 × −0.5R, 1.0 × −6.2R, 1.25 × −8.3R — same order, thinner bounds.

- ≥4R under the live stop on admitted names: **none.** Under 0.5 × ADR: HTFL 08-14 +7.2, PLTR 08-04 +5.4,
  ABCL 08-10 +4.5, ARGX 08-17 +4.2. Under the ORB low: INFQ 05-21 +6.0, QBTS 05-21 +5.9, ARGX +5.0, U +4.1.
- The pre-registered bar, cell by cell on this population: era-matched ✓ (current stack) · settled and
  open apart ✓ (0.5 × ADR has 0 open; ORB low 2 open, marks +3.9R) · n ≥ 30 ✓ (55–65 pairs, 46–52
  ex-May) · holds ex-May ✓ (0.5 ×: +14.1R vs −2.6R; ORB low: +7.8R vs −2.6R) · joint with the target ✓
  (pinned; the own-unit frame agrees, +19.1R) · not an R-unit-growth win ✓ (the unit SHRANK, and the
  size-free ADR-unit delta is +4.3 / +3.7). **0.5 × ADR and the ORB low pass; 0.75 × is marginal
  (bound +1.2R); 1.0 / 1.25 × fail.**
- **Four caveats that ride with the pass (none moves the bar; all are the operator's to weigh):**
  (1) 10 of the 65 control campaigns cannot be settled at 1-minute grain under 0.5 × ADR (9 fill-minute
  straddles, FIG's same-day stop-and-target) — the bound already charges them −1R each; on the whole
  admitted population 0.5 × ADR abstains on 40 of 142 (28%), under the harness's 30% ceiling but at its
  edge; (2) on 56% of campaigns the stop is inside the opening range, i.e. the retired stop or tighter —
  the 08-16 retirement rested on 43 reconstructed Apr–May trades and the live 0-for-12 era-A record, a
  different population and a different exit stack (§11); (3) the admitted population is 142 alerts
  across four admission eras re-scored, not the alerts today's scanner would have raised; (4) **the
  live `stop_too_wide` gate is off here (§1): without CORT, ATRO and HTFL the deltas are — 0.5 × ADR
  +8.5R paired (54), bound +0.5R, ex-May +11.7R (43), +4.3 ADR-units, 3 ≥4R · ORB low +10.3R (55),
  bound +3.9R, ex-May +8.3R, 4 ≥4R · 0.75 × +0.7R, bound −0.5R · 1.0 × −3.8R · 1.25 × −5.1R.** HTFL
  alone is +5.7R of 0.5 × ADR's margin; the ORB low does not depend on it.

## 6. The joint check — the target pinned vs moving with the stop (the 08-06 mechanism)

| stop | target frame | settled n | sum R | partials fired | ≥4R | ADR-units |
|---|---|---|---|---|---|---|
| `entry − 2R` | pinned (live) | 99 | +11.3 | 54 | 1 | +2.3 |
| `entry − 2R` | own unit | 98 | +6.3 | 32 | 2 | −7.4 |
| 0.75 × ADR | pinned | 98 | −0.6 | 45 | 3 | −0.6 |
| 0.75 × ADR | own unit | 98 | −1.9 | 33 | 4 | −1.5 |
| 1.0 × ADR | pinned | 101 | −4.3 | 50 | 1 | −4.4 |
| 1.0 × ADR | own unit | 100 | −9.3 | 31 | 2 | −9.5 |
| 1.25 × ADR | pinned | 102 | −6.7 | 53 | 1 | −8.5 |
| 1.25 × ADR | own unit | 102 | −8.9 | 30 | 2 | −11.3 |
| 0.5 × ADR | pinned | 86 | +19.1 | 38 | 5 | +9.5 |
| 0.5 × ADR | own unit | 85 | +23.8 | 36 | 7 | +11.7 |

- The 08-06 refutation reproduces exactly: let the +2R target move out with the stop and the partial
  stops firing (54 → 32 at the live stop, 53 → 30 at 1.25×ADR), and every wide stop loses more.
- **The pin is worth +5R to the live stop and all of it is +0.33R scratches** — 26 of 54 partial-takers
  bank 1/3 at a target that is +1R in the stop's own unit and then stop at breakeven. That is the
  live median of +0.33R: a unit effect, not a harvest.
- A stop that wins only because its R-unit grew: none of the wide cells win at all, in either frame.

## 7. The runner grid — what each post-partial rule costs and gives, on the same trades

Cohort: the campaigns that fire the +2R partial under the live stop (**55 pooled, 32 ex-May**; every
rule shares the same trade until the partial). R in the live unit; an open row carries its mark.

| runner (after the 1/3 partial) | sum R, pooled | Δ vs live | win | median | worst | ≥4R | sum ex-May (n=32) | Δ ex-May |
|---|---|---|---|---|---|---|---|---|
| **live ladder** (breakeven + trail, resting) | **+52.6** | — | 100% | +0.33 | +0.15 | 1 | +26.1 | — |
| t3 — exit at the 3rd close after the partial | +68.7 | **+16.1** | 71% | +0.95 | −0.36 | 2 | +37.8 | +11.6 |
| gb25 — exit on a 25% giveback of the peak | +57.8 | +5.2 | 76% | +0.93 | −0.36 | 2 | +31.0 | +4.8 |
| t5 | +57.8 | +5.2 | 69% | +0.80 | −1.63 | 3 | +31.5 | +5.4 |
| atr1 — trail 1 ATR under the peak | +56.2 | +3.7 | 76% | +0.89 | −0.36 | 2 | +33.0 | +6.9 |
| live_trail_be (#2's copy of the ladder) | +55.4 | +2.8 | 98% | +0.33 | −0.01 | 2 | +30.8 | +4.6 |
| atr2 | +53.8 | +1.2 | 69% | +0.67 | −1.63 | 4 | +32.0 | +5.9 |
| gb50 | +48.6 | −4.0 | 75% | +0.60 | −0.36 | 2 | +30.2 | +4.0 |
| sma10 close trail | +45.8 | −6.8 | 64% | +0.56 | −1.63 | 2 | +26.5 | +0.3 |
| t10 | +43.6 | −8.9 | 55% | +0.59 | −1.63 | 1 | +25.5 | −0.6 |
| breakeven only, no trail | +39.1 | −13.4 | 98% | +0.33 | −0.01 | 1 | +28.1 | +1.9 |
| sma20 close trail | +37.6 | −14.9 | 53% | +0.14 | −1.63 | 2 | +24.2 | −1.9 |
| t20 | +28.2 | −24.3 | 40% | −0.33 | −1.63 | 2 | +18.5 | −7.6 |
| hard stop stays, nothing else | +16.2 | −36.3 | 31% | −0.33 | −1.63 | 1 | +19.3 | −6.8 |

**The cost side, in R, as pre-registered:**
- The ladder's 100% win rate on takers is the breakeven floor; every rule that beats it on the sum
  drops that to 61–76% and its worst taker from +0.15R to −0.36R (or −1.63R where the stop is gapped
  through at the open).
- **t3's +16.1R is three names (FTK +6.1, RDW +3.5, EROC +3.4 = 80%); 25 of 55 takers are worse
  under it; of the 26 trades the ladder scratches at +0.33R, 14 go negative under t3 (median −0.2R)
  while 5 reach ≥+1R** — #2's "the median partial-taker flips" cost, reproduced, with the sum still
  positive because the five carry it.
- Ranking is stable across stops (t3 > gb25 ≈ t5 ≈ atr1 > ladder > … > hard at ORB-low and 0.5×ADR
  too; full heat map in `_545p3_tables.md` T3b) and holds ex-May — but ex-May IS the whole sample
  (32 takers) and no rule's 95% band could exclude zero at that n. On the ADMITTED takers (35, ex-May
  25): t3 +17.6R (15 of 35 worse), t5 +11.5, atr1 +10.7, atr2 +10.2, gb25 +5.6; breakeven −3.0, hard
  −14.5, t20 −12.8 — same order, n below the bar ex-May. **Direction consistent with #2,
  magnitude and ranking still unsettled; nothing here is a CHANGE_PROCESS candidate.**

## 8. Attempt 2 — one re-entry after a full stop-out, per name

| stop | signal | stop-outs | fired | 2nd stop paid | held ≥+0.5R | leg-2 sum | leg-2 without THC | campaign sum vs 1 attempt | ex-May: campaign vs 1 attempt | worst per name |
|---|---|---|---|---|---|---|---|---|---|---|
| `entry − 2R` (live) | same-day 5-min-range clear | 41 | 31 | 20 | 11 | **−7.7** | −7.7 | +3.7 vs +11.3 | −12.2 vs −6.1 | −2.27 |
| `entry − 2R` | next day, first-5-min low | 41 | 28 | 16 | 10 | **−10.0** | −10.0 | +1.4 vs +11.3 | −15.6 vs −6.1 | −2.67 |
| `entry − 2R` | next day open, stop-day low | 41 | 27 | 17 | 7 | **−9.1** | −9.1 | +3.3 vs +12.3 | −10.7 vs −5.1 | −2.01 |
| ORB low | same-day 5-min-range clear | 56 | 38 | 25 | 12 | +4.7 | **−5.7** | +8.7 vs +4.1 | −3.3 vs −3.8 | −3.84 |
| ORB low | next day, first-5-min low | 56 | 47 | 28 | 17 | +3.2 | **−9.0** | +7.3 vs +4.1 | −0.5 vs −3.8 | −2.67 |
| ORB low | next day open, stop-day low | 56 | 42 | 27 | 10 | −14.4 | −16.5 | −10.3 vs +4.1 | −14.1 vs −3.8 | −2.02 |
| 0.5 × ADR | next day, first-5-min low | 48 | 42 | 25 | 15 | +1.5 | **−10.7** | +20.6 vs +19.1 | +10.6 vs +6.9 | −2.24 |
| 0.5 × ADR | same-day / stop-day low | 48 | 33 / 37 | 26 / 22 | 6 / 7 | −20.6 / −13.0 | −19.6 / −15.1 | −0.4 / +7.1 vs +20.1 | −5.3 / +1.2 vs +7.9 | −2.96 / −2.00 |

- At the live stop a retry loses money in every form; more than half of every signal's fires pay a
  second full stop. Without THC no retry cell on the board is positive. The operator's tight-stop ×
  more-tries shape (ORB-low / 0.5×ADR rows) is where it comes closest — and it is one trade (THC
  +10–12R on a same-day re-entry the live system never took) at 55–79% second-stop rates.

## 9. Retirement — what each retiring harness's headline looks like on `ep_replay`

| harness | its headline | reproduced on `ep_replay` | retire? |
|---|---|---|---|
| **#2** `_bt_replay` + `_runner_sweep` (n=194 raw-derived) | 82 of 106 partial-takers scratch at exactly +0.33R under breakeven; every looser rule beats breakeven on the mean by flipping the median +0.33 → −0.33 and the win rate 55% → 25–44% | `breakeven` cell: 35 of 42 settled takers at +0.33R (83% vs 77%); `hard` / `t20`: median −0.33R, win 31–40%; t3 / gb25 / atr1 beat on the sum with 14 of 26 scratches flipped negative. Its `live_trail_be` ≠ the ladder on 28 of 267 (the resting-touch overlay it lacks) | **YES** — the runner axis lives in `RuleSet.runner_rule`; the 4,453-ticker-day raw population is the one thing not carried (it over-admits by design) |
| **#5** `_stop_floor_forward_replay` + `_545_reentry_sweep` + `_rerun_full17` | SD-5mclear fired 9 of 17 live stop-outs, THC the sole hold (+12.4R on a 0.67% stop), 6 second full stops, ex-THC −4.7R; NDO-o5l +8.5R = THC | on the 15 era-matched full stop-outs (3 abstain: MANE, HUT, FRMI straddle): SD-5mclear fired 6, THC +11.6R, 4 second stops, ex-THC −4.8R; NDO-o5l fired 12, 8 second stops, THC +16.2R / FTNT +6.8R / TEAM +4.1R (#5 time-stopped at session 10 and never saw FTNT run) | **YES** — signals live in `signal_sd_5m_clear` / `signal_ndo_*`, the leg in `_attempt_two`; the one loss is #5's optimistic continue-through-a-straddled-fill-bar (CRCL), which this harness refuses |
| **#8** `geometry_sweep_572` + `bracket_geometry_read_482` (30 live day-0 sessions, real fills, ATR14) | ATR-0.5× the lone ADR-positive delta; ATR-1.0× / prior-day-low lose more money while looking better in R | on the 22 pre-2R live trades: 0.5×ADR +3.2R / +1.6 ADR-units > 0.75× −0.3 / −0.3 > 1.0× −3.0 / −3.0 > 1.25× −4.6 / −5.8 — tighter better, wider loses more money, same ordering (ADR20 here, ATR14 there; reconstructed fills here, real fills there) | **YES** — the established-low entry (its lane W) is the one variant not carried; it was a fade detector, refuted at n=30 |

`python scripts/ep_replay.py validate` after the build: stop 44/44 · entry 33/33 · exit class 29/30 ·
R 25/30 — **PASS, identical to the 09-01 baseline**; `replay --ruleset era_c` abstains 17% (ceiling 30%).
Tests: `tests/test_ep_replay.py` 31 (10 new: field defaults, the ADR stop formula, the strictly-prior
ADR, the ladder-partial switch, the own-unit target, `hard` vs `breakeven`, the time exit, both
re-entry signals, the two-leg campaign sum).

## 10. What in the brief and prior statements turned out to be wrong or stale

- **"87 of 270 era-C campaigns are open at the horizon — the settled mean is censored."** Two are.
  The 85 are alerts the ORB window never submits (81 detected at or after 09:45) plus 4 setup rejects.
- **"270 alert campaigns."** 267; three rows are duplicate inserts.
- **"The +2R stop: 73% day-1 deaths pre vs 25% post (n=4)."** Era-matched on the same 22 names the
  current stop dies 55% of the time on day 1 and turns the rescued names into +0.33R scratches.
- **"On day 1 the ADR band (0.75–1.25) is an open question in the pinned frame."** Now answered: it is
  the worst region on the board; only the tight end (0.5×) is competitive and it is unreadable at
  1-minute grain.
- **"The harness's `live_trail_be` is the live ladder"** (#2): it is not — 28 of 267 campaigns differ
  because the ladder rests the trail level as a touch stop the next session.
- **"BAND and STRL are `stop_too_wide` tails."** They left that bucket (`session_rvol_low`,
  `duplicate_scan`) and cannot be bracket-replayed from anything captured.
- **The harness booked the day-3/5 ladder partial live stands down** — fixed (era-switched); 14 of 267
  campaigns moved, no verdict changed.
- The brief's "+9.32R of the +11.8R is one name, so ex-best it is roughly break-even" — verified: +2.4R
  on 99 without AMBQ. **And AMBQ is a name the current scorer rejects:** the live stop's all-alert
  margin over every tighter stop is the rejected names' margin (+13.1R on 21 rejected settled).
- **"The stop-floor question is open on day 1 in the pinned frame" — it is now answered in the
  direction NOBODY expected: tighter, not wider, on the admitted population.** Every read that said
  otherwise pooled rejected alerts (this card's all-alert grid too) or ran on pre-capture cohorts.

## 11. What this does not answer

- **Anything at sub-minute grain.** The 0.5×ADR stop lives or dies inside the fill minute on 16 of 99
  control campaigns; a 1-minute replay cannot order that, and the operator's own fills (#541 ask class)
  may refuse a stop that tight. Only tick data or a live shadow arm can read it.
- **Whether any runner rule beats the ladder out of sample.** 55 partial-takers pooled, 32 ex-May, gains
  three names deep; no confidence band excludes zero; the current admission era has 3 settled campaigns.
- **The current admission era.** Every campaign here was re-admitted under era-C scoring, but the alerts
  themselves were generated by the May–August scanners (gap floor 10 → 9, the judge, real-time gap
  authority all changed); August's 41 settled campaigns are the closest thing to today's population.
- **Portfolio interaction** — slots, the daily-loss limit attributing two stops of one name to one day,
  breakers. Every campaign is priced alone; a retry's second stop competes for a slot in reality.
- **Fill reality** — spread, LULD halts, our own impact, the venue refusing a limit. Every fill here is
  the modelled cent.
- **Which population is right — this one or 08-16's.** The `entry − 2R` stop was signed on 43
  reconstructed Apr–May trades (−6.0 → +11.4R at equal dollar risk, daily grain past day 0, the old
  admission stack) and on the live 0-for-12 era-A record. This read says the opposite on 65 admitted
  campaigns May–Aug at 1-minute grain under the current stack. They do not overlap in names, eras or
  grain; neither is out of sample. **Consistent with, not proof of, a selection-conditional result
  (P8):** the alerts the current scorer REJECTS are exactly where the wide stop wins here (+13.1R on
  21; every tighter stop loses on them, even ex-May at n=11), and the 08-16 cohort was that kind of
  population — pre-capture, old admission, Apr–May. Two populations responding differently to stop
  width is a simpler reading than a contradiction. Only a forward recorder (a #616-style counterfactual stop on every
  live fill) or a live shadow arm separates them — and the operator is the one who weighs a bounded
  +4.6R against reversing a change he signed three weeks ago.
- **BAND / STRL** — nothing captured can walk them; the probe in §4 is the next step and runs in seconds.
- **The operator's own tactic** ("the low forming, turn back up") — the three retry signals are placeable
  proxies, not his read; a proxy underperforming him is expected, not a refutation.

---
*Population statement (Gate 6): every figure names its rows and window in §1 and in its table.
Sources: `scripts/ep_replay_data/` (09-01 capture), `scripts/probes/_562bf_minute.tsv.gz` (later
sessions only), `scripts/probes/_545p3_report.txt`, `_545p3_cells.tsv`, `_545p3_tables.md`,
`_545p2_capture2_out.psv` (BAND/STRL rows). Related: PLAN #545 · #616 · #482 · #572 · #508 · #562 · #595.*
