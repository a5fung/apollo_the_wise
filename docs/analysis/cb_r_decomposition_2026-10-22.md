# #702 — why the Consolidation Breakout backtest reads flat: the three causes separated (2017–21 and 2022–24; read 2026-10-22)

**MEASUREMENT ONLY. $0, local data, no network. Nothing here changes or proposes to change a strategy, an entry or exit rule,
a stop, a size, a safeguard or any live trade state — those are the operator's (THE LINE). Every number below describes what
the published trades did and what the stocks did around them; the one "next test" named at the end is a read, not a rule.**

**The sealed 2025–26 table is untouched.** No 2025–26 file was opened and no bar after 2024-12-31 was read for any fill
(the 2022–24 export was cut at 2024-12-31 at load, asserted; the 28 fills of 2025-01-02 and every fill whose 60-session
window crosses the cut are excluded from the path numbers and said so). The registered RS-leadership read on 2025–26 stays unspent.

His question, verbatim: *"Just based on the R backtest, it's hard to tell what exactly is the problem. Are we trading bad
setups? Entry exit wrong? What is the cause."*

> **⚠ SCOPE (updated 2026-10-22, after the stop / re-entry read):** the breakout-vs-ordinary-stock comparisons on this page
> measure the stock's DRIFT over 5–60 sessions. Risk / reward AT THE ENTRY with the stop was measured the same night in
> `cb_entry_stop_retry_2026-10-22.md`. On daily bars, entered at the breakout close with the same stop on both sides, the breakout
> reaches +5R before its stop no more often than matched ordinary stocks: 17.8% vs 18.7% (1-ADR stop, 2017–21), 13.6% vs 13.7%
> (2022–24), and 14.8% vs 14.9% / 10.4% vs 10.4% at 1.5 ADR. What is NOT measured: the intraday (opening-range) entry against a
> control, and any FILTERED subset (his A+ / graded picks). So the plain-words lead below means "on daily bars, the unfiltered
> breakout entry carries no drift or race edge over ordinary stocks" — not "breakouts have no edge" (his 10-22 correction).

## 0. The answer, in plain words (rewritten 2026-10-22 after two independent verifiers; their corrections are listed in §8)

- **On daily bars, the unfiltered breakout entry carries no drift edge: after the breakout day, these stocks move like any liquid stock
  of the same volatility on the same day** (and, per the scope note above, no race edge at the same stop). This holds at every horizon measured (§2, matched on the same E date and ADR decile, from E's close):
  - next 5 sessions: +0.151 vs +0.146 ADR (2017–21), −0.120 vs −0.129 (2022–24), intervals spanning zero;
  - next 20 sessions: +0.48 vs +0.43 and −0.23 vs −0.22;
  - share reaching +5 ADR within 60: 43% vs 42% and 35% vs 36%;
  - share reaching +10 ADR: 13.9% vs 13.1% (2017–21; about +1 point under finer volatility matching, interval clear of zero —
    a small lift, roughly 8% relative) and 10.2% vs 10.4% (2022–24).

  So the C0 breakout, as detected, does not pick stocks that follow through more than ordinary stocks.
- **The big gains take weeks to build, and our trades are over in days.** Where a breakout's stock did gain 5 ADR, it REACHED
  that mark a median 26 / 28 sessions after the fill (5–6 weeks; 10 ADR at 38–40 sessions). This is when the gain was complete,
  not when the move began (corrected 10-22; the first wording said "started", which was wrong). A trade lasts a median 1 session; one
  the stop did not take lasts a median 6–9 sessions. So the stop and the exit both end the trade long before the move:
  - of every 100 big moves, the original stop fired first on 56 / 58 (bin B);
  - of the big moves the stop did NOT take, the exit still lost 81–85% (bin C, mostly out before the move began);
  - 8 / 7 of 100 were captured.

  "Stop vs exit" is an ordering, not a cost split: whichever rule fires first gets the credit, and both fire within days of a
  move that arrives in weeks.
- **What that means for "entry/exit wrong?":** a looser stop or a longer hold would ride moves that matched ordinary stocks make
  at the same rate. That gains the market's return for this volatility, not an edge of the setup:
  - 2017–21: +1.23 vs +0.92 ADR over 60 sessions, +0.16 (interval spanning zero) once matched on the stock's own prior 3-month
    strength;
  - 2022–24: about zero for both.

  Entry and exit cannot create an edge the selection does not have. They decide how much of the market's move, and how much
  noise, each trade carries.
- **The two eras differ mostly in the market:** the controls' 5-ADR rate fell 42% → 36% and their 60-session return
  +0.92 → −0.01 ADR, with the breakouts'. The bin mix explains about 70% of the mean-R drop (+0.025 → −0.206 on the 60-session
  subset). The rest is deeper losses per losing trade in 2022–24.
- **With selection made perfect by hindsight** (the 39 big winners of 2017–21, §3 — NOT evidence about selection, survivorship):
  - their fills made a 5-ADR move 58% of the time against 42% for the rest;
  - yet the same stop and exit kept 346 of 4,493 ADR (7.7%).

  If the right stocks are picked, the current stop and exit waste most of the move. But picking them is the part not yet shown.
- **Why R alone could not show this:** R measures the stop width, not the move. The ≥ 10R trades made a median 6 ADR, and 10R at
  their 0.38-ADR median stop is only 3.8 ADR. 1,730 of 1,855 fills whose stock made a 10-ADR move were not 10R trades.
- **Action: none from this data (THE LINE).** The data says the edge has to come from SELECTION (which breakouts), and none of the
  tested selectors has shown it yet:
  - C1, the A+ rating, and his discussed stream bases — CAN'T TELL;
  - RS leadership alone — the sealed read is pending.

  The next selection read is his own grades on stream (bought / best vs "needs a few more days"). Any stop or exit change is his.

## 1. The waterfall — every fill in exactly one bin (60 sessions after the fill)

**Rule, fixed before the run.** s* = the first session in 1..60 AFTER E whose high reached fill × (1 + T × ADR20), T = 5 and 10.
(A) no s* — the stock never made the move. Out before s* (our `exit_session` < s*, or = s* on a stop exit, since the walk books
the stop when a bar touches both): (B) if the exit was the ORIGINAL low-of-day stop — a stop exit with no third taken; under
`pp` the stop never moves until a third sells — the entry-day stop shook us out; (C_out) otherwise — a breakeven stop after a
third, a trail, or the session-3 cut: the exit rule took us out before the move. In at s*: (D) if the trade kept at least half
the threshold move (`pnl_adr` = realized R × width_adr ≥ T/2), else (C_in). "Big moves lost to B / to C" = B / (B+C+D) and
(C_out+C_in) / (B+C+D). Sensitivities (half the stock's own best move instead of half the threshold; a 20-session horizon) are
in the generated tables below and do not change the ordering.

| era / threshold | n fills | A never made the move | B stop hit first | C exit gave it back (out before / in but kept < half) | D captured | big moves lost to B | lost to C |
|---|---|---|---|---|---|---|---|
| 2017-21, +5 ADR | n = 13,363 | 7,607 (56.9%) | 3,194 (23.9%) | 2,077 (15.5%) = 1,768 / 309 | 485 (3.6%) | 55.5% of 5,756 | 36.1% |
| 2017-21, +10 ADR | n = 13,363 | 11,508 (86.1%) | 1,013 (7.6%) | 712 (5.3%) = 662 / 50 | 130 (1.0%) | 54.6% of 1,855 | 38.4% |
| 2022-24, +5 ADR | n = 8,047 | 5,218 (64.8%) | 1,642 (20.4%) | 979 (12.2%) = 865 / 114 | 208 (2.6%) | 58.0% of 2,829 | 34.6% |
| 2022-24, +10 ADR | n = 8,047 | 7,239 (90.0%) | 474 (5.9%) | 274 (3.4%) = 262 / 12 | 60 (0.7%) | 58.7% of 808 | 33.9% |

What each bin did in R and what was on the table (mean best 60-session move from the fill, ADR):

| era / threshold | mean R: A | B | C_out | C_in | D | mean best move (ADR): B | C_out | C_in | D | 10R trades in D / C_in / elsewhere | big movers whose daily low reached the original stop level on a session in E+1..s*−1 (whatever our stop was by then) |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 2017-21, +5 ADR (n = 13,363) | −0.50 | −1.04 | +0.85 | +3.29 | +10.20 | +9.82 | +9.34 | +7.74 | +13.63 | 158 / 4 / 3 | 4,177 of 5,756 (72.6%) |
| 2017-21, +10 ADR (n = 13,363) | −0.23 | −1.04 | +1.91 | +7.80 | +18.62 | +15.73 | +14.75 | +13.41 | +22.89 | 96 / 11 / 58 | 1,290 of 1,855 (69.5%) |
| 2022-24, +5 ADR (n = 8,047) | −0.58 | −1.09 | +0.83 | +2.92 | +10.11 | +9.39 | +8.85 | +8.56 | +12.22 | 67 / 1 / 1 | 2,130 of 2,829 (75.3%) |
| 2022-24, +10 ADR (n = 8,047) | −0.37 | −1.13 | +1.77 | +9.59 | +16.57 | +15.20 | +15.00 | +11.82 | +18.65 | 40 / 3 / 26 | 573 of 808 (70.9%) |

Reading it: the B trades booked −1.04R each while their stocks went on to a mean +9.8 ADR (≈ 20 stop-widths at the median
stop). The stop fired first; those moves began a median 29–30 sessions after the fill (§0, §8), so this is an ordering, not a shake-out of a move already under way. The C_out trades left with a small profit (+0.85R / +1.9R) and their stocks then ran +9 to +15 ADR.
The D trades are the published tail (158 of the 165 ten-R trades in 2017–21 sit in D at +5 ADR). The sum-of-R per bin (generated
table "What the bins cost in R") shows the published mean is the D bin's +4,949R minus A's −3,786R minus B's −3,336R in 2017–21.
Reconcile: the 2017–21 subset is the whole published row (+0.025 on 13,363). The 2022–24 60-session subset reads −0.206 on 8,047
against the published −0.169 on 8,984 — the 937 excluded fills (E after 2024-10-04, window crossing the 2024-12-31 cut, plus the
28 of 2025-01-02) ran better than the rest; nothing is dropped from the published number, only from the path numbers.
B split by when the stop was hit: 2017–21 +5 ADR n = 3,194 → 1,768 on the fill day / 1,426 later; 2022–24 n = 1,642 → 954 / 688.

## 2. The control — is it selection? (same E dates, the setup's universe filter, matched on volatility)

**Composition first.** 2017–21: breakouts n = 13,363 over 1,176 E dates vs 2,233,746 control ticker-dates (mean 1,899 per E);
2022–24: 8,047 over 608 E dates vs 1,387,809 (2,283 per E). The breakouts are far more volatile and far stronger than the pooled
universe (median ADR20 0.041 vs 0.023; median 63-session return +20% vs +2% in 2017–21), which is why the comparison is matched:
each fill is compared with the control stocks of the SAME E date in the SAME ADR20 decile (deciles cut on the breakouts), and,
as a second control, the same 63-session-return quintile too. Both are measured from E's close, breakouts and controls alike.

| era | matching | measure | n fills | breakouts | matched control | difference | 95% month-block interval |
|---|---|---|---|---|---|---|---|
| 2017–21 | ADR decile | share ≥ 5 ADR within 60 (from E close) | n = 13,363 | 43.2% | 42.1% | +1.1 pts | −0.6 .. +2.8 |
| 2017–21 | ADR decile | share ≥ 10 ADR within 60 | n = 13,363 | 13.9% | 13.1% | +0.8 pts | −0.2 .. +1.9 |
| 2017–21 | ADR decile | mean +60-session close return (ADR) | n = 13,260 | +1.23 | +0.92 | +0.31 | +0.11 .. +0.54 |
| 2017–21 | ADR decile × 63-session return quintile | share ≥ 5 ADR within 60 | n = 13,363 | 43.2% | 42.4% | +0.9 pts | −0.8 .. +2.6 |
| 2017–21 | ADR decile × 63-session return quintile | share ≥ 10 ADR within 60 | n = 13,363 | 13.9% | 13.4% | +0.5 pts | −0.4 .. +1.5 |
| 2017–21 | ADR decile × 63-session return quintile | mean +60-session close return (ADR) | n = 13,260 | +1.23 | +1.07 | +0.16 | −0.03 .. +0.36 |
| 2022–24 | ADR decile | share ≥ 5 ADR within 60 | n = 8,047 | 35.2% | 36.0% | −0.8 pts | −2.3 .. +0.9 |
| 2022–24 | ADR decile | share ≥ 10 ADR within 60 | n = 8,047 | 10.2% | 10.4% | −0.3 pts | −1.1 .. +0.8 |
| 2022–24 | ADR decile | mean +60-session close return (ADR) | n = 7,973 | +0.07 | −0.01 | +0.08 | −0.15 .. +0.32 |
| 2022–24 | ADR decile × 63-session return quintile | share ≥ 5 ADR within 60 | n = 8,047 | 35.2% | 34.5% | +0.7 pts | −0.8 .. +2.2 |
| 2022–24 | ADR decile × 63-session return quintile | share ≥ 10 ADR within 60 | n = 8,047 | 10.2% | 9.7% | +0.5 pts | −0.4 .. +1.6 |
| 2022–24 | ADR decile × 63-session return quintile | mean +60-session close return (ADR) | n = 7,973 | +0.07 | −0.12 | +0.19 | −0.05 .. +0.45 |

**Selection verdict (tail first):** the breakouts' big-move rate is indistinguishable from the matched control's in both eras at
both thresholds — no measurable tail edge from selection at C0 (the data rules out a lift above ~+3 points at 5 ADR and ~+2
points at 10 ADR; it does not prove zero). The only cell whose interval clears zero is the 2017–21 60-session drift under the
ADR-only match (+0.31 ADR), and it does not survive matching on the stock's own 63-session return (+0.16, −0.03 .. +0.36): a
small part of it is "we buy stocks that were already strong", not the pattern. The era drop is the market's: the controls'
+5-ADR rate fell 42% → 36% and their 60-session return +0.92 → −0.01 ADR alongside the breakouts' 43% → 35% and +1.23 → +0.07.

## 3. The 39-winner lens (2017–21; selection fixed at perfect by hindsight — NOT evidence about selection)

The 39 tickers of the A+ read's hindsight list (`THE_39` in `aplus_read.py`, cross-checked against `aplus_hindsight_pre.txt`)
have n = 527 C0 `tl` ORH5 fills in 2017–21 (all 39 appear; the whole era, not only 2020–21). Because the list was named after
the fact, their move rate says nothing about selection (survivorship); what it isolates is what the entry, stop and exit did
when the stock was, by construction, a winner.

| group | n | mean R | 10R trades | best 60-session move from the fill: ≥ 5 ADR | ≥ 10 ADR | p90 (ADR) | on the table (ADR, fills ≥ 5 ADR) | kept (ADR, same fills) | fill-day stop share |
|---|---|---|---|---|---|---|---|---|---|
| the 39's fills | n = 527 | +1.006 | 17 (3.2%) | 304 (57.7%) | 167 (31.7%) | 18.4 | 4,493 | +346 (7.7%) | 34.0% |
| all other 2017–21 fills | n = 12,836 | −0.015 | 148 (1.2%) | 5,452 (42.5%) | 1,688 (13.2%) | 11.2 | 52,375 | +1,773 (3.4%) | 36.9% |

| the 39 / threshold | n fills | A never made the move | B stop hit first | C exit gave it back (out before / in but kept < half) | D captured | big moves lost to B | lost to C |
|---|---|---|---|---|---|---|---|
| the 39, +5 ADR | n = 527 | 223 (42.3%) | 158 (30.0%) | 107 (20.3%) = 89 / 18 | 39 (7.4%) | 52.0% of 304 | 35.2% |
| the 39, +10 ADR | n = 527 | 360 (68.3%) | 89 (16.9%) | 61 (11.6%) = 54 / 7 | 17 (3.2%) | 53.3% of 167 | 36.5% |

The per-ticker table is in the generated section below (MRNA: 16 fills made 5 ADR, 7 stopped first, 7 given back, 2 captured;
ENPH 16 / 9 / 5 / 2; SHOP 21 / 7 / 10 / 4; TSLA 11 / 5 / 2 / 4).

## 4. Side rows

- **Day-0 stop-out by stop width** (generated table "Day-0 stop-out share by stop width"): the tightest quarter of stops
  (≤ 0.32 ADR, n = 3,341 in 2017–21) is stopped on the fill day 68% of the time, the widest quarter (> 0.63 ADR, n = 3,341) 12%;
  the stocks' big-move rate is the same across the quarters (39–46% make 5 ADR) — the stock's path does not depend on our stop
  width, our result does (mean R −0.12 in Q1 vs +0.10 in Q4; 2022–24 the same shape: 67% → 12% day-0 stops, n = 2,239 per quarter).
- **The stop variants (cited, not re-run — `cb_his_exit_2026-10-18.md` §0, 2022–24, `tl` C0):** capping the day-low stop at
  ½ ADR (`lod_cap05`) changes nothing (−0.083 vs −0.087 ADR per trade); flooring it at ½ ADR (`lod_floor05`) costs 0.006 ADR and
  raises the win rate as a wider stop should; the level − ½ ADR stop drops 1,149 of 8,989 fills as wider than one ADR and reads
  the same on the trades it keeps (−0.084 vs −0.085 ADR, n = 7,836); the base-low stop keeps 755 of 8,989 (the bases whose low
  is within one ADR) and reads −0.011 vs −0.047 ADR on those 755, interval spanning zero. **Every variant was capped at one
  ADR** (the registered width rule). The big movers' own pullback before their move is a median about 1.1–1.4 ADR (both verifiers, §8), so a 1–2 ADR stop is the unmeasured range.
- **The hourly-close entry (cited — `cb_hourly_entry_prereg_2026-10-19.md` RESULT):** waiting for a 60-minute close above the
  line did not avoid the same-day shake-out (fill-day stop 35.7% vs ORH5's ~35% in C0); at scale it equals ORH5 (paired
  +0.00R on 10,595 bases); C1 FAIL on 2022–24.
- **R vs ADR:** the 165 / 69 ten-R trades (complete windows) have a median stop width of 0.38 / 0.40 ADR and a median profit
  of 6.0 / 5.9 ADR; 1,730 of 1,855 (2017–21) and 759 of 808 (2022–24) fills whose stock made a 10-ADR move were not 10R trades.

## 5. Method and population

**Population:** the PUBLISHED C0 row — `trades_pre_exitpb.tsv.gz` (2017–21) and `trades_discovery_exitpb.tsv.gz` (2022–24),
rows `arm = pp`, `entry = orh5`, `K = tl`, `C0 = 1`, `mature = 1`: **n = 13,363 and n = 8,984**, reproduced first with the
published mean R (+0.0254 / −0.1691), ≥ 10R counts (165 / 85) and fill-day-stop shares (36.8% / 37.2%) to the printed digit
(`01_reproduce.txt`: MATCH both eras). The row includes the spec key's retrigger fills (2,352 / 1,659 `retrigger_chain = 1`), as
published. Window: watch nights 2017-03-01..2021-12-31 (fills 2017-03-02..2022-01-03) and 2022-03-28..2024-12-31 (fills
2022-04-01..2025-01-02).

**The stock's path** (`02_build_paths.py`): Alpaca split-adjusted daily bars from each era's `daily_closes_all.csv.gz`
(2017–21: 2016-01-04..2022-06-30; 2022–24: cut to ≤ 2024-12-31 at load). Session calendar = SPY's dates. The forward window is
**(E, E+k] in sessions — it starts the session AFTER the fill day**; E's own bar is not in the MFE/MAE because the daily bar
cannot tell what came before the fill from what came after (a flag counts fills whose E high already stood T ADR over the fill:
5 / 0 / 0 / 0 — so the "never made the move" bin is overstated by at most that). ADR units = move / (ADR20 × price), ADR20 =
the module's mean (high − low)/close over the 20 sessions ending at D, as a fraction; price = the fill (from-fill numbers) or
E's close (from-close numbers; the control's base). Completeness: a fill enters a k-session number only if E+k ≤ the last
readable session (2017–21: 13,363 / 13,363; 2022–24: 8,711 of 8,956 at 20, 8,047 at 60; 28 fills of 2025-01-02 have no readable
E bar). Fills with a missing session inside the walk (`fwd_hole`: 25 / 19) are kept with fewer bars. Checks passed before any
number: every fill lies inside E's daily bar (±1%): 13,363 / 13,363 and 8,956 / 8,956; my ADR20 at D equals the table's to a
median 1.2e-7 relative; `pnl_adr = realized_r × width_adr` to 5e-15; `width_adr = (fill − stop)/(ADR20 × fill)` to 4e-14.

**Our trade's path:** the row's own `realized_r`, `pnl_adr`, `exit_kind`, `exit_session` (E = session 0), `partial_kind`,
`fill_day_stop`; s* and the first session the low touched the original stop are computed from the bars.

**The control** (`02_build_paths.py`): at each fill's E, every ticker in the export with — at D, the session before E — adjusted
close ≥ $5, 20-session median close × volume ≥ $10M, 130 consecutive sessions, ticker `^[A-Z]{1,5}$`; tickers with a C0 fill on
that E or any watch row at D are excluded (189,924 ticker-dates in 2017–21; 126,736 counted over all 668 readable 2022–24 E dates, 113,702 over the 608 the control covers). **Deviations from the setup's filter, stated:** the
setup tests the RAW close ≥ $5 (the 2022–24 export has no raw series, so the adjusted close is used in both eras — 13,337 / 13,363
and 8,953 / 8,956 of the breakouts pass my reading); security type is not in the export, so ETFs / preferreds / warrants that
pass the ticker regex are in the control (the setup admits common stock / ADR / unknown). Matching: each fill's control rate =
the control's rate in its own (E, ADR20 decile) cell — deciles cut on the era's breakouts — and, for the second control, its
(E, decile, 63-session-return quintile) cell; empty cells fall back to (E, decile) (0 / 170 / 0 / 27 fills), none to the date
alone. Intervals: month-block bootstrap of the per-fill (breakout − matched control) difference, calendar month of E, 2,000
resamples, seed 702.

**The 39** (`03_report.py`): the `THE_39` tuple parsed from `aplus_read.py`'s source (not imported), cross-checked against
`cb702_pre/out/aplus_hindsight_pre.txt`; their fills = the population above restricted to those tickers.

**Files.** Probes (rerunnable, numbered): `scripts/probes/_702_r_decomposition_1022/01_reproduce.py` (+ `.txt`),
`02_build_paths.py` (+ `02_build_checks*.txt`, `02_build_run*.log`), `03_report.py` (+ `03_report.md` = every table below,
`03_numbers.json`). Per-fill tables: `apollo_data/cb702_pre/out/r_decomp_fills_2017-21.tsv.gz`,
`apollo_data/cb702/out/r_decomp_fills_2022-24.tsv.gz`; control rows: `r_decomp_control_<era>.tsv.gz` beside them. Nothing
pinned was written; the runner was neither run nor imported; no once-only stage ran.

## 6. What this does not answer

- **Whether a wider stop would have made money.** B says the stop was hit before the move in 56–58% of the big movers; it does
  not say what a wider stop costs on the 57–65% of fills whose stock never moved (bin A booked −0.50R / −0.58R each at the
  tight stop; a stop 4× wider is 4× the dollar loss per share there — the R unit changes and so does the size). Only a
  registered read on the same fills answers that, and the variants read so far were all capped at one ADR.
- **What the exit should be.** C says the exit left before or under the move in 35–38% of the big movers; the counterfactual
  "ridden to the top" (the "on the table" sums) is a ceiling nobody reaches, not a target.
- **Selection beyond C0.** The control compares the loosest cell; C1 and the stricter cells have 79–180 trades per era and were
  read as CAN'T TELL earlier; this doc does not re-read them.
- **Anything about 2025–26.** Unread by design (the sealed table).
- **Day-0 moves.** A move that started and was captured within the fill day (the 857 day-0 +2R thirds in 2022–24) is invisible
  to a daily-bar MFE that starts the session after E; the day-0 flag bounds the miscount at 5 / 0 fills at +5 ADR.
- **Causality of the shake-out.** "Traded below the fill-day low before the move" is a fact about the path, not a statement that
  the low-of-day stop is the wrong stop; the article's stop is his, and the trade-off against bin A is the untested half.
- **Security type and raw price in the control** (stated above). ETFs in the control move ≥ 5 ADR slightly MORE often than the rest
  (verifier, §8), so if anything they bias the control UP, against the breakouts, by a small amount.
- **The retrigger fills** are in the published row and in every number here; the first-break-only view is not separated.

## 7. The test that would decide next (a read, not a rule; whether to run it is his)

Selection first, because entry and exit cannot add an edge the selection lacks (§0). The next read is **Qullamaggie's own grades
on stream**. Do the bases he said he bought or called his best, against the ones he said "need a few more days to tighten",
follow through more than matched ordinary stocks in the first 5 / 20 sessions after the breakout? It is pre-registered before
any outcome (PLAN #705). Only if a selector shows an edge does the stop / hold question become worth a read. That read: on the
selected fills, stops 1 / 1.5 / 2 ADR under the fill (the big movers' pre-move pullback is a median about 1.1–1.4 ADR) and a
hold long enough to keep a gain that takes a median 5–6 weeks to build, scored in ADR and account percent.

## 8. Verification (2026-10-22): two independent verifiers, then the main loop

- **Recount (own code, no builder import):** the population, every waterfall count, the B day split and the control rates
  reproduce exactly. The low-touch counts differ by ≤ 7 (a touch convention).
- **Logic audit:** the waterfall is correct as a first-to-fire partition (no leak, no double count, units right). It flagged as
  BLOCKING that the first draft read the bin order as a cost ranking ("the stop is the biggest cost"). The lead above is
  rewritten: of the stop survivors the exit loses 81–85%, and the gains take weeks to build after trades that end in days.
- **Material:** the draft's "the big movers pull back 2–4 ADR" was unmeasured. The 2.8 / 3.9 ADR figure was the worst low of ALL
  fills over 60 sessions. The big movers' own pre-move pullback is a median about 1.1–1.4 ADR: 55% / 61% beyond 1 ADR, 28% / 37%
  beyond 2 ADR.
- **Minor, all applied:**
  - the 10-ADR tail lift in 2017–21 under finer matching (about +1 point);
  - the ETF bias direction;
  - 10R in ADR;
  - the 70% bin-mix share of the era drop;
  - the exclusion count's date base;
  - the 937 excluded 2022–24 fills average about +0.145R, not +0.156. Their published R values include early-2025 exits from
    the already-published discovery walk, outside the sealed 2025–26 table. "No bar after 2024-12-31" is true of this read's own
    bar reads.
- **Main loop** (`04_main_loop_checks.py` / `.txt`, from the builder's tables, no builder code):
  - the stop-survivor shares (81.1 / 84.6 / 82.5 / 82.0%);
  - the move timing (median 26 / 40 / 28 / 38 sessions);
  - holding times (median 1 session; stop survivors 6–9);
  - the 5-session matched control (+0.005 [−0.054, +0.063]; +0.009 [−0.043, +0.062]).

---

## Generated tables (`03_report.py`, verbatim; n on every row)

## Population and completeness (n on every row)

| era | published mature fills | with a readable E bar | 20-session window complete | 60-session window complete | fwd_hole rows (a missing session inside the walk) |
|---|---|---|---|---|---|
| 2017-21 | n = 13,363 | 13,363 | 13,363 | 13,363 | 25 |
| 2022-24 | n = 8,984 | 8,956 | 8,711 | 8,047 | 19 |

## 1. The stock's path after the fill, independent of our stop (ADR units; window (E, E+k] starts the session AFTER E)

| era | n (60-window complete) | max move from the fill within 60: >= 5 ADR | >= 10 ADR | p90 | median | max move within 20: >= 5 ADR | >= 10 ADR | worst low within 60 from the fill, median | fills with a 10R result (= about 4.5 ADR at the median stop) |
|---|---|---|---|---|---|---|---|---|---|
| 2017-21 | n = 13,363 | 5,756 (43.1%) | 1,855 (13.88%) | 11.46 ADR | 4.26 ADR | 2,170 (16.2%, n = 13,363) | 294 (2.20%) | -2.81 ADR | 165 (1.23%) |
| 2022-24 | n = 8,047 | 2,829 (35.2%) | 808 (10.04%) | 10.02 ADR | 3.47 ADR | 1,178 (13.5%, n = 8,711) | 167 (1.92%) | -3.90 ADR | 69 (0.86%) |

What was on the table vs what was kept, in ADR units (fills whose best 60-session move from the fill reached the threshold; 'on the table' = the sum of those best moves, a CEILING no exit reaches, not a forecast; 'kept' = the sum of realized R x width_adr on the same fills):

| era | threshold | n fills reaching it | on the table (ADR) | kept (ADR) | kept share | per fill: on the table | kept |
|---|---|---|---|---|---|---|---|
| 2017-21 | >= 5 ADR | n = 5,756 | 56,868 | +2,120 | 3.7% | 9.9 | +0.37 |
| 2017-21 | >= 10 ADR | n = 1,855 | 29,347 | +1,540 | 5.2% | 15.8 | +0.83 |
| 2022-24 | >= 5 ADR | n = 2,829 | 26,587 | +721 | 2.7% | 9.4 | +0.25 |
| 2022-24 | >= 10 ADR | n = 808 | 12,395 | +539 | 4.3% | 15.3 | +0.67 |

Same, measured from E's CLOSE (the control's base; the fill is earlier in the day, so moves from the close read smaller):

| era | n | >= 5 ADR within 60 | >= 10 ADR within 60 | p90 | mean close-to-close +20 (ADR) | mean +60 (ADR) |
|---|---|---|---|---|---|---|
| 2017-21 | n = 13,363 | 5,776 (43.2%) | 1,851 (13.85%) | 11.50 | +0.48 | +1.23 |
| 2022-24 | n = 8,047 | 2,832 (35.2%) | 819 (10.18%) | 10.11 | -0.23 | +0.07 |

## 2. The waterfall: every fill with a complete 60-session window lands in exactly one bin

**Within 60 sessions of the fill; C_in = in at the move's start but kept < half the threshold move (pnl in ADR < T/2)**

| era / threshold | n fills | A never made the move | B stop hit first | C exit gave it back (out before / in but kept < half) | D captured | big moves lost to B | lost to C |
|---|---|---|---|---|---|---|---|
| 2017-21, +5 ADR | n = 13,363 | 7,607 (56.9%) | 3,194 (23.9%) | 2,077 (15.5%) = 1,768 / 309 | 485 (3.6%) | 55.5% of 5,756 | 36.1% |
| 2017-21, +10 ADR | n = 13,363 | 11,508 (86.1%) | 1,013 (7.6%) | 712 (5.3%) = 662 / 50 | 130 (1.0%) | 54.6% of 1,855 | 38.4% |
| 2022-24, +5 ADR | n = 8,047 | 5,218 (64.8%) | 1,642 (20.4%) | 979 (12.2%) = 865 / 114 | 208 (2.6%) | 58.0% of 2,829 | 34.6% |
| 2022-24, +10 ADR | n = 8,047 | 7,239 (90.0%) | 474 (5.9%) | 274 (3.4%) = 262 / 12 | 60 (0.7%) | 58.7% of 808 | 33.9% |

B split by WHEN the original stop was hit (fill day = the ORH5 entry's own-day shake-out; later = a stop hit on sessions 1+ before the move):

| era / threshold | B total | stopped on the fill day | stopped on a later session (before s*) | share of B on the fill day |
|---|---|---|---|---|
| 2017-21, +5 ADR | n = 3,194 | 1,768 | 1,426 | 55.4% |
| 2017-21, +10 ADR | n = 1,013 | 562 | 451 | 55.5% |
| 2022-24, +5 ADR | n = 1,642 | 954 | 688 | 58.1% |
| 2022-24, +10 ADR | n = 474 | 289 | 185 | 61.0% |

Bin detail (mean realized R per bin; the stock's mean best move in the B / C bins = what was on the table; n per bin above):

| era / threshold | mean R: A | B | C_out | C_in | D | mean best move (ADR) B | C_out | C_in | D | 10R trades in D / C_in / elsewhere | same-bar stop at s* (counted in B/C_out) | big movers whose daily LOW reached the original stop level on a session in E+1..s*-1 (whatever our stop was by then) | median s* (sessions) | E's own high already >= T ADR over the fill |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 2017-21, +5 ADR (n = 13,363) | -0.50 | -1.04 | +0.85 | +3.29 | +10.20 | +9.82 | +9.34 | +7.74 | +13.63 | 158 / 4 / 3 | 0 | 4177 | 26 | 5 |
| 2017-21, +10 ADR (n = 13,363) | -0.23 | -1.04 | +1.91 | +7.80 | +18.62 | +15.73 | +14.75 | +13.41 | +22.89 | 96 / 11 / 58 | 0 | 1290 | 40 | 0 |
| 2022-24, +5 ADR (n = 8,047) | -0.58 | -1.09 | +0.83 | +2.92 | +10.11 | +9.39 | +8.85 | +8.56 | +12.22 | 67 / 1 / 1 | 0 | 2130 | 28 | 0 |
| 2022-24, +10 ADR (n = 8,047) | -0.37 | -1.13 | +1.77 | +9.59 | +16.57 | +15.20 | +15.00 | +11.82 | +18.65 | 40 / 3 / 26 | 0 | 573 | 38 | 0 |

**Sensitivity: 'small' read as kept < half of the stock's own best move (instead of half the threshold)**

| era / threshold | n fills | A never made the move | B stop hit first | C exit gave it back (out before / in but kept < half) | D captured | big moves lost to B | lost to C |
|---|---|---|---|---|---|---|---|
| 2017-21, +5 ADR, small = kept < half the stock's best 60-session move | n = 13,363 | 7,607 (56.9%) | 3,194 (23.9%) | 2,462 (18.4%) = 1,768 / 694 | 100 (0.7%) | 55.5% of 5,756 | 42.8% |
| 2017-21, +10 ADR, small = kept < half the stock's best 60-session move | n = 13,363 | 11,508 (86.1%) | 1,013 (7.6%) | 796 (6.0%) = 662 / 134 | 46 (0.3%) | 54.6% of 1,855 | 42.9% |
| 2022-24, +5 ADR, small = kept < half the stock's best 60-session move | n = 8,047 | 5,218 (64.8%) | 1,642 (20.4%) | 1,136 (14.1%) = 865 / 271 | 51 (0.6%) | 58.0% of 2,829 | 40.2% |
| 2022-24, +10 ADR, small = kept < half the stock's best 60-session move | n = 8,047 | 7,239 (90.0%) | 474 (5.9%) | 313 (3.9%) = 262 / 51 | 21 (0.3%) | 58.7% of 808 | 38.7% |

**Sensitivity: the move must come within 20 sessions (more fills have a complete window)**

| era / threshold | n fills | A never made the move | B stop hit first | C exit gave it back (out before / in but kept < half) | D captured | big moves lost to B | lost to C |
|---|---|---|---|---|---|---|---|
| 2017-21, +5 ADR within 20 sessions | n = 13,363 | 11,193 (83.8%) | 1,014 (7.6%) | 722 (5.4%) = 435 / 287 | 434 (3.2%) | 46.7% of 2,170 | 33.3% |
| 2017-21, +10 ADR within 20 sessions | n = 13,363 | 13,069 (97.8%) | 127 (1.0%) | 97 (0.7%) = 63 / 34 | 70 (0.5%) | 43.2% of 294 | 33.0% |
| 2022-24, +5 ADR within 20 sessions | n = 8,711 | 7,533 (86.5%) | 562 (6.5%) | 397 (4.6%) = 280 / 117 | 219 (2.5%) | 47.7% of 1,178 | 33.7% |
| 2022-24, +10 ADR within 20 sessions | n = 8,711 | 8,544 (98.1%) | 82 (0.9%) | 44 (0.5%) = 37 / 7 | 41 (0.5%) | 49.1% of 167 | 26.3% |

What the bins cost in R (sum of realized R per bin; the published mean R is the sum over all bins / n):

| era / threshold | n | sum R: A | B | C_out | C_in | D | total | mean R (this subset) |
|---|---|---|---|---|---|---|---|---|
| 2017-21, +5 ADR | n = 13,363 | -3,786 | -3,336 | +1,496 | +1,016 | +4,949 | +339 | +0.025 |
| 2017-21, +10 ADR | n = 13,363 | -2,686 | -1,051 | +1,265 | +390 | +2,421 | +339 | +0.025 |
| 2022-24, +5 ADR | n = 8,047 | -3,018 | -1,793 | +719 | +333 | +2,104 | -1,655 | -0.206 |
| 2022-24, +10 ADR | n = 8,047 | -2,692 | -536 | +463 | +115 | +994 | -1,655 | -0.206 |

## 3. The matched control (selection): the same E dates, the setup's universe filter at D, matched on ADR20 decile (and on the 63-session return quintile)

**2017-21 — composition first.** Breakouts n = 13,363 over 1176 E dates; control n = 2,233,746 (ticker-dates; mean 1899 per E). ADR20 deciles cut on the breakouts: [0.025, 0.0298, 0.0336, 0.0374, 0.0412, 0.0455, 0.0511, 0.0593, 0.0744]; 63-session return quintile cuts: [0.01, 0.15, 0.259, 0.428]. Breakouts' median ADR20 0.0412 vs the pooled control's 0.0229; median 63-session return +0.204 vs +0.022; median 20-session dollar volume $38M vs $47M.

Per decile, POOLED over all E dates (not date-matched - breakouts cluster in strong months; the date-matched rows below are the verdict):

| ADR20 decile | breakouts n | control n | breakout >= 5 ADR from E close within 60 | control >= 5 ADR | breakout >= 10 ADR | control >= 10 ADR | breakout mean +20 close (ADR) | control mean +20 |
|---|---|---|---|---|---|---|---|---|
| 1 | n = 1,337 | n = 1,259,285 | 47.2% | 47.5% | 18.25% | 15.44% | +0.32 | +0.06 |
| 2 | n = 1,336 | n = 253,964 | 47.9% | 43.2% | 14.15% | 11.75% | +0.54 | +0.27 |
| 3 | n = 1,336 | n = 147,921 | 46.6% | 42.9% | 15.42% | 12.14% | +0.43 | +0.27 |
| 4 | n = 1,336 | n = 110,407 | 42.6% | 42.6% | 11.08% | 12.83% | +0.31 | +0.37 |
| 5 | n = 1,337 | n = 85,860 | 44.2% | 42.2% | 12.64% | 12.80% | +0.39 | +0.38 |
| 6 | n = 1,336 | n = 75,360 | 43.9% | 41.7% | 12.80% | 12.86% | +0.55 | +0.37 |
| 7 | n = 1,336 | n = 72,703 | 43.3% | 41.4% | 13.10% | 12.59% | +0.60 | +0.41 |
| 8 | n = 1,336 | n = 71,701 | 41.2% | 40.3% | 14.15% | 12.25% | +0.57 | +0.40 |
| 9 | n = 1,336 | n = 72,572 | 40.8% | 38.7% | 14.22% | 11.95% | +0.61 | +0.47 |
| 10 | n = 1,337 | n = 83,973 | 34.6% | 35.0% | 12.72% | 10.36% | +0.45 | +0.54 |

| 2017-21: matching | measure | n fills | breakouts | matched control | difference | 95% month-block interval | fills whose cell had no control (fell back to decile / to the date) |
|---|---|---|---|---|---|---|---|
| ADR decile | share >= 5 ADR within 60 (from E close) | n = 13,363 | 43.22% | 42.08% | 1.14% | -0.64% .. 2.83% | 0 / 0 |
| ADR decile | share >= 10 ADR within 60 (from E close) | n = 13,363 | 13.85% | 13.10% | 0.75% | -0.19% .. 1.85% | 0 / 0 |
| ADR decile | mean +20-session close return (ADR) | n = 13,342 | +0.48 | +0.43 | +0.05 | -0.08 .. +0.18 | 0 / 0 |
| ADR decile | mean +60-session close return (ADR) | n = 13,260 | +1.23 | +0.92 | +0.31 | +0.11 .. +0.54 | 0 / 0 |
| ADR decile x 63-session return quintile | share >= 5 ADR within 60 (from E close) | n = 13,363 | 43.22% | 42.36% | 0.87% | -0.81% .. 2.58% | 170 / 0 |
| ADR decile x 63-session return quintile | share >= 10 ADR within 60 (from E close) | n = 13,363 | 13.85% | 13.36% | 0.49% | -0.36% .. 1.54% | 170 / 0 |
| ADR decile x 63-session return quintile | mean +20-session close return (ADR) | n = 13,342 | +0.48 | +0.45 | +0.03 | -0.09 .. +0.14 | 172 / 0 |
| ADR decile x 63-session return quintile | mean +60-session close return (ADR) | n = 13,260 | +1.23 | +1.07 | +0.16 | -0.03 .. +0.36 | 184 / 0 |

**2022-24 — composition first.** Breakouts n = 8,047 over 608 E dates; control n = 1,387,809 (ticker-dates; mean 2283 per E). ADR20 deciles cut on the breakouts: [0.0241, 0.0286, 0.0326, 0.0361, 0.0403, 0.0454, 0.0513, 0.0589, 0.0718]; 63-session return quintile cuts: [-0.01, 0.103, 0.197, 0.324]. Breakouts' median ADR20 0.0403 vs the pooled control's 0.0245; median 63-session return +0.152 vs +0.001; median 20-session dollar volume $37M vs $47M.

Per decile, POOLED over all E dates (not date-matched - breakouts cluster in strong months; the date-matched rows below are the verdict):

| ADR20 decile | breakouts n | control n | breakout >= 5 ADR from E close within 60 | control >= 5 ADR | breakout >= 10 ADR | control >= 10 ADR | breakout mean +20 close (ADR) | control mean +20 |
|---|---|---|---|---|---|---|---|---|
| 1 | n = 805 | n = 673,943 | 46.7% | 48.0% | 18.14% | 16.79% | +0.11 | +0.17 |
| 2 | n = 805 | n = 182,293 | 38.0% | 43.8% | 11.06% | 12.20% | -0.13 | +0.30 |
| 3 | n = 804 | n = 117,814 | 42.2% | 42.3% | 10.07% | 11.70% | -0.24 | +0.26 |
| 4 | n = 805 | n = 79,029 | 40.2% | 41.8% | 9.81% | 11.88% | -0.32 | +0.26 |
| 5 | n = 805 | n = 73,559 | 33.8% | 40.5% | 10.06% | 11.47% | -0.41 | +0.18 |
| 6 | n = 804 | n = 67,184 | 35.3% | 38.8% | 11.44% | 11.48% | -0.27 | +0.14 |
| 7 | n = 805 | n = 54,835 | 31.4% | 37.8% | 8.45% | 11.01% | -0.24 | +0.14 |
| 8 | n = 804 | n = 46,896 | 29.1% | 36.1% | 6.47% | 10.75% | -0.25 | +0.03 |
| 9 | n = 805 | n = 45,582 | 26.1% | 33.6% | 7.45% | 10.14% | -0.43 | -0.07 |
| 10 | n = 805 | n = 46,674 | 29.1% | 31.2% | 8.82% | 9.26% | -0.10 | -0.20 |

| 2022-24: matching | measure | n fills | breakouts | matched control | difference | 95% month-block interval | fills whose cell had no control (fell back to decile / to the date) |
|---|---|---|---|---|---|---|---|
| ADR decile | share >= 5 ADR within 60 (from E close) | n = 8,047 | 35.19% | 35.99% | -0.79% | -2.30% .. 0.90% | 0 / 0 |
| ADR decile | share >= 10 ADR within 60 (from E close) | n = 8,047 | 10.18% | 10.43% | -0.25% | -1.06% .. 0.84% | 0 / 0 |
| ADR decile | mean +20-session close return (ADR) | n = 8,026 | -0.23 | -0.22 | -0.01 | -0.11 .. +0.10 | 0 / 0 |
| ADR decile | mean +60-session close return (ADR) | n = 7,973 | +0.07 | -0.01 | +0.08 | -0.15 .. +0.32 | 0 / 0 |
| ADR decile x 63-session return quintile | share >= 5 ADR within 60 (from E close) | n = 8,047 | 35.19% | 34.53% | 0.66% | -0.77% .. 2.23% | 27 / 0 |
| ADR decile x 63-session return quintile | share >= 10 ADR within 60 (from E close) | n = 8,047 | 10.18% | 9.73% | 0.45% | -0.44% .. 1.64% | 27 / 0 |
| ADR decile x 63-session return quintile | mean +20-session close return (ADR) | n = 8,026 | -0.23 | -0.22 | -0.01 | -0.11 .. +0.10 | 28 / 0 |
| ADR decile x 63-session return quintile | mean +60-session close return (ADR) | n = 7,973 | +0.07 | -0.12 | +0.19 | -0.05 .. +0.45 | 29 / 0 |

## 4. The 39-winner lens (2017-21 only; selection held fixed at perfect by hindsight - NOT evidence about selection)

The 39 tickers (parsed from `aplus_read.py` `THE_39`, cross-checked against `aplus_hindsight_pre.txt`) have n = 527 C0 `tl` ORH5 fills in 2017-21 with a complete 60-session window (the whole era, not only 2020-21; 39 of the 39 appear).

| group | n | mean R | 10R trades | best 60-session move from the fill: >= 5 ADR | >= 10 ADR | p90 (ADR) | median (ADR) | sum of best moves (ADR, fills >= 5 ADR) | sum kept (pnl in ADR, same fills) | fill-day stop share |
|---|---|---|---|---|---|---|---|---|---|---|
| the 39's fills | n = 527 | +1.006 | 17 (3.23%) | 304 (57.7%) | 167 (31.7%) | 18.37 | 5.92 | 4,493 | +346 | 34.0% |
| all other 2017-21 fills | n = 12,836 | -0.015 | 148 (1.15%) | 5452 (42.5%) | 1688 (13.2%) | 11.20 | 4.20 | 52,375 | +1,773 | 36.9% |

**The 39's waterfall (60 sessions)**

| era / threshold | n fills | A never made the move | B stop hit first | C exit gave it back (out before / in but kept < half) | D captured | big moves lost to B | lost to C |
|---|---|---|---|---|---|---|---|
| the 39, +5 ADR | n = 527 | 223 (42.3%) | 158 (30.0%) | 107 (20.3%) = 89 / 18 | 39 (7.4%) | 52.0% of 304 | 35.2% |
| the 39, +10 ADR | n = 527 | 360 (68.3%) | 89 (16.9%) | 61 (11.6%) = 54 / 7 | 17 (3.2%) | 53.3% of 167 | 36.5% |

| the 39 / threshold | mean R: B | C_out | C_in | D | mean best move (ADR): B | C_out | C_in | D | 10R trades in D / C_in / elsewhere |
|---|---|---|---|---|---|---|---|---|---|
| the 39, +5 ADR (n = 527) | -1.03 | +0.84 | +3.35 | +17.00 | +13.98 | +11.79 | +8.01 | +27.97 | 17 / 0 / 0 |
| the 39, +10 ADR (n = 527) | -1.03 | +1.83 | +6.26 | +30.77 | +19.24 | +16.12 | +13.43 | +50.05 | 15 / 0 / 2 |

Per ticker (fills with a complete window; sorted by the sum of best moves):

| ticker | n fills | mean R | sum R | 10R | fills whose best 60-session move >= 5 ADR | of those: stop hit first (B) | exit gave it back (C) | captured (D) | sum best move (ADR) | sum kept (ADR) |
|---|---|---|---|---|---|---|---|---|---|---|
| GME | n = 10 | +5.30 | +53.0 | 1 | 2 | 1 | 0 | 1 | 606 | +49 |
| MRNA | n = 19 | +2.44 | +46.4 | 2 | 16 | 7 | 7 | 2 | 284 | +25 |
| ENPH | n = 20 | +0.16 | +3.2 | 0 | 16 | 9 | 5 | 2 | 238 | +6 |
| TSLA | n = 17 | +2.73 | +46.4 | 1 | 11 | 5 | 2 | 4 | 226 | +38 |
| SHOP | n = 27 | +3.02 | +81.4 | 2 | 21 | 7 | 10 | 4 | 202 | +27 |
| ROKU | n = 19 | +0.49 | +9.4 | 0 | 15 | 9 | 5 | 1 | 195 | +7 |
| ETSY | n = 25 | -0.19 | -4.7 | 0 | 18 | 11 | 6 | 1 | 180 | +0 |
| TTD | n = 20 | -0.34 | -6.8 | 0 | 14 | 8 | 6 | 0 | 153 | -2 |
| TDOC | n = 29 | -0.25 | -7.3 | 0 | 13 | 5 | 8 | 0 | 131 | -0 |
| NVDA | n = 18 | +0.20 | +3.6 | 1 | 12 | 8 | 3 | 1 | 130 | +2 |
| AMC | n = 22 | +1.54 | +33.9 | 1 | 4 | 3 | 0 | 1 | 123 | +21 |
| SNAP | n = 15 | -0.53 | -8.0 | 0 | 9 | 6 | 3 | 0 | 122 | -3 |
| NXH | n = 17 | +3.65 | +62.1 | 1 | 6 | 1 | 4 | 1 | 117 | +29 |
| AMD | n = 17 | +1.17 | +19.8 | 1 | 10 | 4 | 4 | 2 | 115 | +10 |
| PENN | n = 16 | -0.09 | -1.5 | 0 | 11 | 6 | 4 | 1 | 108 | +1 |
| SE | n = 17 | +2.25 | +38.3 | 2 | 10 | 3 | 5 | 2 | 101 | +18 |
| FSLY | n = 8 | +3.99 | +31.9 | 1 | 5 | 3 | 1 | 1 | 99 | +25 |
| NVAX | n = 13 | +0.49 | +6.4 | 0 | 4 | 1 | 3 | 0 | 94 | +2 |
| PINS | n = 15 | +0.84 | +12.7 | 0 | 8 | 4 | 2 | 2 | 91 | +17 |
| CVNA | n = 20 | +0.08 | +1.6 | 0 | 8 | 5 | 2 | 1 | 91 | +4 |
| NET | n = 10 | +1.07 | +10.7 | 0 | 8 | 4 | 2 | 2 | 89 | +8 |
| FVRR | n = 10 | +2.84 | +28.4 | 2 | 8 | 4 | 2 | 2 | 89 | +11 |
| PLUG | n = 4 | +14.79 | +59.2 | 1 | 3 | 2 | 0 | 1 | 80 | +24 |
| W | n = 17 | -0.69 | -11.7 | 0 | 8 | 6 | 2 | 0 | 77 | +1 |
| CRWD | n = 15 | +0.49 | +7.3 | 0 | 8 | 2 | 5 | 1 | 75 | +4 |
| BLNK | n = 9 | -0.54 | -4.9 | 0 | 3 | 3 | 0 | 0 | 75 | -2 |
| PTON | n = 10 | +0.51 | +5.1 | 0 | 6 | 2 | 3 | 1 | 72 | +2 |
| DDOG | n = 11 | +1.87 | +20.6 | 1 | 5 | 3 | 0 | 2 | 68 | +16 |
| SPCE | n = 9 | +0.63 | +5.7 | 0 | 6 | 3 | 2 | 1 | 65 | +4 |
| NIO | n = 7 | +0.26 | +1.8 | 0 | 5 | 2 | 3 | 0 | 64 | +1 |
| ZM | n = 7 | -0.14 | -1.0 | 0 | 5 | 3 | 2 | 0 | 64 | +1 |
| LULU | n = 7 | -0.61 | -4.3 | 0 | 5 | 5 | 0 | 0 | 46 | -2 |
| UPST | n = 3 | -0.44 | -1.3 | 0 | 2 | 2 | 0 | 0 | 43 | -1 |
| APPS | n = 8 | +1.72 | +13.8 | 0 | 5 | 2 | 1 | 2 | 42 | +5 |
| DOCU | n = 14 | -0.53 | -7.4 | 0 | 6 | 2 | 4 | 0 | 42 | +0 |
| LVGO | n = 7 | -0.29 | -2.0 | 0 | 2 | 2 | 0 | 0 | 41 | -1 |
| DKNG | n = 6 | -1.00 | -6.0 | 0 | 4 | 4 | 0 | 0 | 29 | -2 |
| QS | n = 5 | -0.58 | -2.9 | 0 | 2 | 1 | 1 | 0 | 27 | -0 |
| FUBO | n = 4 | -0.70 | -2.8 | 0 | 0 | 0 | 0 | 0 | 0 | +0 |

## 5. Side rows

Day-0 stop-out share by stop width (width_adr = (fill - stop) / (ADR20 x fill); quartiles cut per era on the mature population):

| era | width quartile (ADR) | n | stopped on the fill day | mean R | 10R trades | best 60-session move >= 5 ADR (complete windows) |
|---|---|---|---|---|---|---|
| 2017-21 | Q1 <= 0.32 | n = 3,341 | 68.1% | -0.119 | 54 | 39.2% (n = 3,341) |
| 2017-21 | Q2 0.32-0.45 | n = 3,341 | 42.8% | +0.074 | 56 | 43.5% (n = 3,341) |
| 2017-21 | Q3 0.45-0.63 | n = 3,340 | 24.8% | +0.047 | 35 | 43.8% (n = 3,340) |
| 2017-21 | Q4 > 0.63 | n = 3,341 | 11.6% | +0.100 | 20 | 45.8% (n = 3,341) |
| 2022-24 | Q1 <= 0.33 | n = 2,239 | 66.8% | -0.190 | 30 | 34.2% (n = 2,023) |
| 2022-24 | Q2 0.33-0.48 | n = 2,239 | 43.9% | -0.213 | 25 | 35.7% (n = 2,033) |
| 2022-24 | Q3 0.48-0.65 | n = 2,239 | 25.9% | -0.198 | 16 | 35.0% (n = 1,994) |
| 2022-24 | Q4 > 0.65 | n = 2,239 | 12.1% | -0.075 | 14 | 35.8% (n = 1,997) |

R vs ADR (why 10R is not a big move): realized R x width_adr = pnl in ADR units.

| era | n 10R trades | their median stop width (ADR) | their median pnl (ADR) | their median best 60-session move (ADR) | fills with best move >= 10 ADR that were NOT 10R trades |
|---|---|---|---|---|---|
| 2017-21 | n = 165 | 0.38 | 6.0 | 13.5 | 1730 of 1855 |
| 2022-24 | n = 69 | 0.40 | 5.9 | 12.3 | 759 of 808 |

