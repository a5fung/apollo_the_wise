# #545 — Entry/Exit Tactics Program, v3 (2026-09-05): ranked on the TAIL first

**Status: DESIGN + READ-ONLY RE-READ — no code path changed, no threshold moved, nothing flipped,
nothing deployed, PLAN.md untouched.** Supersedes `docs/design/545_entry_exit_program_v2_2026-09-02.md`
(v2, 09-02), which supersedes the 08-07 v1. v2's inventory rows are cited by number and NOT
re-derived; this document re-grades every one of them under the objective function the operator
set tonight, adds what the three days since v2 produced (Phases 1–4, the 09-05 stop-width and
HTFL reads, the #482 recorder's first night), and re-sequences the plan.

⚖ **THE LINE.** Every stop, target, partial, sizing, entry and re-entry rule below is the
operator's SOLE authority. This is EVIDENCE and a ranked list of what to MEASURE next. Where a
fork exists it is stated as his. Every live change is CHANGE_PROCESS + the #151 harness +
operator sign-off.

**Acting rules, read from code + prod at 2026-09-05 17:44 PDT** (`python scripts/live_rules.py`,
prod reachable at server checkout `c888fc3f`): ORB 1-min stop-limit entry · protective stop
`entry − 2R` at half size (`order_manager.py:546`, operator-signed 08-16) · +2R partial (1/3) at
`entry + 2·(entry − ORB low)` via resting limit, breakeven at the broker the moment it fills
(`constants.py:332`, `order_manager.py:7717`) · day-3/5 ladder partial standing down
(`live_tracker.py:1076`) · seeded SMA10/20 close-below trail · raise-only stops · same-day
re-entry OFF (R3) · giveback peak-lock RULED OUT (08-11) · max 5 positions, 2% daily loss.
`--drift-only` reported **6 findings, all in `catalyst_rubric.md` / `htf.md` / `magna53_ep.md`
status claims — none touches a stop, target, partial, entry or re-entry rule; out of this
card's scope and NOT fixed here.**

---

## 0. The answer on one screen

**The objective function (operator, 2026-09-05, HARD — `analysis_standard.md` §THE STATISTIC):**
> *"big tail is the key ingredient, median can be somewhat managed with entry and exit."*

So every variant is ranked FIRST on tail preservation — count of ≥3R and ≥5R outcomes and the
p90 on the same names — and only THEN on the median. **A variant that lifts the median by cutting
winners short is a failure even if its mean R improves.** Applied to everything below.

**The finding, in one line: the day-1 ENTRY finds the tail; the STOP and the HARVEST give it
back — and the single rule that gives back the most is the breakeven stop placed after the +2R
partial.** Under today's full live stack, replayed on the names today's scorer admits (n=65
settled, 4 months, era-clean, 0 near-zero-stop rows): **zero campaigns ≥3R, p90 +1.43R, median
+0.21R.** The same 65 entries under a tighter stop or a non-breakeven runner produce 6–12 names
≥3R (§3). The live book agrees: 26 closed trades, none ≥4R, best +3.4R.

**Top three findings (details §2–§4):**
1. **TEAM 08-07 is decided by ONE CENT and it is the mechanism, not an anecdote.** On the actual
   fill (147.13) today's stop holds by $2.22, the partial fills 08-11, breakeven survives and the
   runner is open at 189.58. On the harness's modelled fill (146.80, the ORB high) the +2R target
   sits 99 cents lower at 153.98; the 08-10 09:31 bar prints 153.99, the partial fires, the stop
   goes to breakeven, and the 09:32 bar prints 145.00 — stopped, +0.33R. Same bars, same rules,
   33 cents of entry. **Partial-then-breakeven turns the best operator-labelled EP in the record
   into the modal +0.33R scratch on a coin flip.** (§2.1)
2. **Tail-first re-ranking inverts the harvest verdict, and the tail of every no-breakeven rule is
   in the rows Phase 3 could not settle.** Settled-only, `hard` (partial, then ride the original
   stop) shows 0 names ≥3R on the admitted population; add the open-at-horizon MARKS and it holds
   TEAM +4.7, ARGX +3.1, PLTR +2.7 with 15 names still running. Under a 0.5×ADR stop the same cell
   carries HTFL +9.1, PLTR +8.5, ABCL +6.1, ARGX +5.2 open. The same censoring trap as the #327
   lane (a stop settles instantly; a winner stays open). (§3.2)
3. **The joint cell nobody named: a tight day-1 stop × a short post-partial time exit.**
   0.5×ADR × t3 on the admitted 56: **10 names ≥3R, 5 ≥5R, p90 +4.76R, +35.6R** vs the live
   ladder's 0 / 0 / +1.43R / +3.5R on the same names; ORB-low × t3: 12 / 4 / +3.58R / +40.1R.
   Cost: median −1.00R (the tight stop), 19–22 winners of 56–59. **Direction only** — 3-name
   concentration is lower than Phase 3's t3 read (FTK/RDW/EROC carried 80% at the live stop; here
   HTFL/FTK/PLTR/ABCL/ARGX/QBTS/ZBRA spread it) but it is still one replay population, majority
   Bull, and #482's recorder on night one has `stop_adr_050` as the WORST arm at n=6. (§3.1, §3.4)

**The single biggest gap in what we can answer: population.** 267 alert campaigns → 182 ever
submittable → 145 admitted by today's scorer → 65 settle under the live stop → 46 ex-May → 4–7
tail names in the best cell. Everything the rule `stop_too_wide` refused, everything before
05-11, everything the scan skipped before it became an alert, and CHPT-class names that never
scored have NO bars in any replay capture (§5.1). A stop or harvest verdict on 4–7 tail names is a
direction; the operator asked for a sweep, and the sweep needs the bars. **$0 path exists**: the
#623 card fetched 2,399 uncaptured ticker-days of day-0 SIP bars from Alpaca at $0
(`scripts/probes/_623_fetch_bars.py`); the same method closes this gap.

**Recommended Phase 1 (§7): the DAY-1 HARVEST HOLE, $0, ~½ session.** Replay on the same 267
campaigns the two cells Phase 3 never ran — no partial at all (stop + trail only; stop + hold),
and a second partial higher up (5R / 8R / 10R) on top of a tight stop — reported tail-first with
open marks, admitted, ex-May, by regime, and on the four operator-labelled names. It is the exact
question the #482 recorder's three harvest arms answer FORWARD at n=20, so replay and recorder
can be read like-for-like when the gate fires.

---

## 1. Method / population — read before any number

**Population statement:** every figure names one of the rows/windows below. No prod query was run
for this document. Every replay number was read from files already in the repo; the one new
computation (`scripts/probes/_545v3_tail_rank.py` → `_545v3_tail_rank_out.txt`) re-reads the
Phase 3 sweep's own captured rows and adds nothing to them.

| label | rows | window | source | caveat that travels with every use |
|---|---|---|---|---|
| **P-LIVE** | 26 closed real-money `mi_live_trades` magna53 first attempts | alerts 07-06 → 08-28 | `scripts/ep_replay_data/_pull2_out.txt` (09-01 capture) | **era-split, never pooled:** A (<08-01, ORB-low stop, no partial) n=12 · B (08-01→08-15, ORB-low + partial) n=10 · C (≥08-16, `entry−2R` + partial) n=4. Entry-stamped regime (prior session's row, `live_tracker.py:523`): Bull 10 · Choppy 8 · Correcting 7 · Crisis 1. Two R bases: −7.8R on placed risk (`545p2`), −11.3R on the recorder's realized per-share R (Phase 4); best +3.3/+3.4R (PLTR); **≥4R: none** |
| **P-REPLAY** | 267 campaigns (270 rows, 3 same-millisecond duplicates) = every live-source `mi_ep_alerts` row | 05-11 → 08-28 | `scripts/ep_replay.py replay --ruleset era_c` → `campaigns_era_c.tsv`; Phase 3's 105-cell sweep `scripts/probes/_545p3_cells.tsv` | re-scored under the CURRENT admission stack: **admit 145 · reject 81 · undecided 44** (float bonus not stored). Under the live stack: **100 settled · 2 open (MRNA, OKTA) · 37 no_entry · 46 abstain (17%, missing day-0 minutes) · 85 no_trade (81 detected ≥09:45, 4 setup rejects)**. Admitted AND settled under the live stop: **65 (46 ex-May)**. Entry-stamped regime of those 65: **Bull 40 · Correcting 11 · Choppy 10 · Crisis 4** — majority Bull, the opposite of P-LIVE. **Near-zero stops: 0 of 26,348 sweep rows have `stop_width_pct < 0.5`** — the exclusion was applied and removed nothing; stated rather than assumed. Horizon 08-31: an open row carries a MARK, never a return |
| **P-623** | 3,458 `mi_ep_scan_log` ticker-days (417 ever scored, 3,041 rejection-tagged) → 1,590 settled under era_c | 06-08 → 09-03 | `scripts/probes/_623_PREREGISTERED.md`, `_623_analysis_out.txt` | **THIS is the "whole book is breakeven" population — the candidate UNIVERSE the scan sees, not the traded book.** 13 near-zero-stop rows removed → **n=1,577, sum −0.42R, mean 0.00**; two of the 13 (ATI +119.5R, AVBC +67.5R, stops of 2 and 0.4 cents) carried +187R of the raw +168R. Any replay figure that did not exclude `stop_width_pct < 0.5` is inflated by this class |
| **P-DELAYED** | 267 caught EPs × 4 delayed-entry rungs = 602 first-attempt fires, 569 settled | 05-01 → 08-31 | `scripts/probes/_562bf_*`, `_545rt_*` | mature fires only (20 post-fire sessions by 08-31) → **August unreadable until ~late September**; May is the era the operator ruled stale — every cell pooled AND ex-May |
| **P-LANE** | the LIVE #327 watch lane: 3,129 fires / 1,273 names | fires from 08-25 | `mi_delayed_entry_watch` / `_trigger` (PLAN #327, 09-05) | **nine sessions elapsed of a twenty-session window**: 2,334 settled rows are the losers by construction, 696 open rows hold any winner; **99 rows carry `stop_width_pct < 0.5`** (BCTX `mfe_r` 5499R) — exclude. First honest read 2026-09-22 |
| **P-482** | `mi_live_fill_counterfactuals`, first night 09-04: 43 rows, 8 arms, n=5–6 per arm | fills from 09-04 | PLAN #482 line, `live_fill_counterfactuals.py` | `live_actual` +0.357 · `live_replay` +0.300 · `harvest_t3` +0.422 · `stop_orb_low` +0.028 · **`stop_adr_050` −0.661R** — **n=6 settles nothing**; quoted only because it is the arm Phase 3 named first. Gate: 20 era-C fills with all three stop arms settled (`data_gated_reviews.yaml:10741`) |
| **P-194** | 194 filled trades, raw-derived 4,453 ticker-days under the 08-29 rule manifest | 04-13 → 08-28 | `docs/analysis/runner_rule_sweep_2026-08-29.md` | over-admits by design (no catalyst/judge/RVOL reconstruction); **82 of 106 partial-takers finish at exactly +0.33R** |
| **P-22** | the 22 pre-2R live trades re-walked under every stop | 07-06 → 08-14 | Phase 3 §2 | the era-matched answer to "did the 08-16 widening work" |
| **P-5m** | the 5-min ORB shadow lane, 38 closed magna53 | 05 → 08 | `scripts/probes/_482n55/read_out.txt` | 16 rows are daily-bar REPLAYS (+15.6R), 22 real-time (−14.9R, median −0.99R); ≥4R: 1 (AMBQ, a replay) |
| **P-MISSED** | `mi_ep_missed_outcomes`, `setup_at_open = true` | 02 → 08 | `545p2` (09-02) | daily-grain tail PROXY (≥+20% at 20 sessions), not realized R; **46 of 238 tail rows are non-common-stock or pre-04-20**; `ret_20d` censored on 382 of 423 August rows |
| **P-STOPWIDE** | 27 `stop_too_wide` refusal rows (the 09-05 prod read); 12 rows in the missed table; 9 MAGNA53 names (08-17) | 04-30 → 08-20 | `docs/analysis/stopwide_replay_era_c_2026-09-05.txt`, `_545p2_capture2_out.psv` §STOP_TOO_WIDE_ALL, `stop_too_wide_outcome_cohort_2026-08-17.md` | **"27" is ROWS, not deduplicated names** — both account modes, every strategy, possibly several ticks per name. Only 8 map to a P-REPLAY campaign, 4 reach an entry |
| older cohorts (v2 §2) | 15/17 live stop-outs · 75 reconstructed HIGH Apr–May · 43 matched Apr–May (the 08-16 signing set) · 14 (08-06 floor) · 55/43/23 missed-EP campaign set · 99 HIGH Apr–May (pivot proximity) | Apr → Aug | as cited per row | each is ONE cohort under an admission stack that no longer exists; usable for MECHANISM and for the tail counts they reported, never for a current level |

**Grading vocabulary (v2's, re-keyed to the tail):** a result is **LOAD-BEARING** only if (a) n ≥ 30,
(b) it reports the TAIL (≥3R / ≥5R count or p90) and not only a sum or median, (c) it holds with May
excluded or spans two eras/regimes, and (d) it comes from a harness validated against real fills or
from a live rule. **ONE-COHORT** = a real read that must not be generalised. **MEDIAN-ONLY** = a
result whose winners were never counted — it cannot rank a variant under tonight's objective and
is marked INVALID-AS-A-TAIL-VERDICT below even where its direction stands. **REFUTED** (stated n).
**RULED** (operator decision). **INVALID** = era-mixed, contaminated by the near-zero-stop class,
retracted, or MFE read as a return.

**Measurement traps carried into every table:** `fwd_5d_pct` / `max_high_*` are MFE (positive by
construction) · R is each cell's OWN unit at equal dollar risk · a stop settles instantly, a winner
stays open (censoring runs AGAINST every no-breakeven / long-hold rule and FOR every breakeven
rule) · the harness fills at the ORB high, live fills 0.24% higher on average (validate) — TEAM
shows what 0.2% can do · the harness's 1-minute grain cannot order a stop and a target inside one
bar (abstain) — 0.5×ADR abstains on 28% of admitted campaigns · **the sweep capture carries leg 1's
stop only; a re-entry leg's stop width is not screenable from `_545p3_cells.tsv`** — the two
carriers of the re-entry cell were screened by hand from the minute bars (§3.4 #34) and nothing else was.

---

## 2. What the three days since v2 established — used, not re-derived

### 2.1 TEAM 2026-08-07 under today's geometry — two fills, two outcomes, one cent apart

Both walks below use the same `_562bf_daily.tsv` / `_562bf_minute.tsv.gz` bars. ORB 146.80 / 143.21.

| | actual fill (fixture, `tests/fixtures/must_not_miss_eps.py:231`) | harness fill (`_545p3_cells.tsv`, cell `entry_minus_2r/orb/live`) |
|---|---|---|
| entry | **147.13** | **146.80** (the ORB high — every replay fills there) |
| R = entry − ORB low | 3.92 | 3.59 |
| stop `entry − 2R` | 139.29 | 139.62 |
| +2R target | **154.97** | **153.98** |
| 08-07 low | 141.51 — holds by $2.22 | holds |
| 08-10 09:31 bar (h 153.99, l 146.90) | 153.99 < 154.97: **no partial**, stop still 139.29 | **153.99 ≥ 153.98: partial fires, stop → breakeven 146.80** |
| 08-10 09:32 bar (l 145.00) | above 139.29: holds | **145.00 < 146.80: stopped at breakeven** |
| 08-11 (h 156.215, l 148.87) | partial fires, breakeven 147.13 holds | — |
| 08-12 → 09-04 | lowest 150.75; runner open at 189.58 | — |
| result | **≈ +7.9R in ORB-R units (partial +0.67 + 2/3 of +10.8R), still open** | **+0.33R, closed 08-10** |

- Neither is wrong. The harness's daily walk resolved 08-10 correctly — the minute bars confirm
  the partial minute (09:31) precedes the breakeven touch (09:32). The 33-cent fill difference
  moved the target by 99 cents, which was the distance between "no partial yet" and "partial +
  breakeven into a whipsaw".
- **This is the program's mechanism in one name:** the +2R partial is fine; the breakeven stop
  placed the same minute is what converts a runner into the modal scratch. Under the `hard`
  runner (partial, then the 2/3 rides the ORIGINAL stop) the harness holds TEAM with an open mark
  of **+4.73R**; under `t3` +2.11R; under 0.5×ADR it is stopped on day 0 (−1.00R) and only a
  next-day re-entry at that stop recovers it (+3.06R, §3.4).
- **"$2.22 of room" is thin, and so is "one cent of target".** TEAM is evidence FOR the 08-16
  widening (the old stop lost it at 143.21) and evidence AGAINST breakeven-at-partial, not proof
  that any geometry is right.

### 2.2 The book is breakeven — on the candidate universe, once the near-zero-stop class is out

P-623: **1,577 replayed ticker-days, sum −0.42R, mean 0.00** after removing 13 rows whose stops
were 0.4–10 cents wide (two of them, ATI and AVBC, were +187R of the raw +168R). That population
is every name the scan SAW since 06-08 — 3,041 of 3,458 were rejected by a filter — so it says
the universe has no edge left after the bracket, not that the admitted book is breakeven. The
admitted book is P-REPLAY's 65: **+3.5R, 0 ≥3R, −2.6R ex-May.** Both say the same thing about
conversion; they are different populations and are cited separately everywhere below.

### 2.3 HTFL 2026-08-14 and the `stop_too_wide` rule — replayed, and the population is the answer

- HTFL: 96 / HIGH / game_changer; refused at 09:31:01 by `validate_orb_entry`
  (`agents/market_intelligence/backtester/filters.py:207–222`: ORB range $2.55 = 7.0% > 1.5 ×
  ATR14 $2.19); stock 31.01 → 50.85. **Under today's stack the harness pays +1.43R** (partial,
  then trailed out); under 0.5×ADR **+7.17R**, under ORB low +2.85R.
- Of the 27 refusal rows, **8 map to a P-REPLAY campaign, 4 reach an entry**: HTFL +1.43 · CORT
  −0.10 · ATRO −0.26 · AEVA −0.59 — n=4, HTFL is the whole +0.47R. **No basis to touch 1.5× on
  four rows.** The structural objection stands on its own (the gate judges a gap-day opening
  minute against a PRE-GAP ATR; the docstring names this replay as its own revisit trigger), and
  the fix to propose, if a cost shows at n≥10, is a gap-aware yardstick or size-down — not a
  looser 1.5×.
- **19 of 27 are absent from P-REPLAY entirely** and 4 more are present but never entered. That
  gap is §5.1 and is a prerequisite, not a footnote.

### 2.4 The modal trade is +0.33R — three populations, one number

| population | partial-takers ending at the +0.33R scratch | source |
|---|---|---|
| P-194 (raw-derived) | **82 of 106 (77%)** | `runner_rule_sweep_2026-08-29.md` §0 |
| P-REPLAY, all alerts, live stop | 26 of 54 (48%) | Phase 3 §6 |
| P-REPLAY, admitted, live stack | 18 of 35 (51%) | `campaigns_era_c.tsv`, this card |
| P-REPLAY, admitted, `breakeven`-only runner | 35 of 42 (83%) | Phase 3 §9 |

(The brief's "88–94%" is not in the repo and is not cited.)

### 2.5 #482's recorder contradicts Phase 3 on night one — the reason nothing here is a recommendation to flip

`stop_adr_050`, Phase 3's leading candidate (+14.2R paired on 55), is the **worst arm on six real
fills (−0.661R)**; `harvest_t3` leads (+0.422); `live_replay` reads 0.057R PESSIMISTIC against
`live_actual` — the opposite of the +0.11R optimistic bias every replay on this board assumed.
**n=6 settles nothing**, but it is exactly why every "candidate" below is routed to a forward
gate before a fork is put to the operator.

### 2.6 Phase 1–4 results (09-02 → 09-03), one line each

- **Retry test (`545_retry_test_2026-09-02.md`):** `ep_low_reclaim` × 0.25×ADR × up to 3 tries ×
  trail: +54.4R on 46 ex-May names vs +5.3R one try at 0.75×ADR; **4 names ≥4R vs 2**; NRIX +36.3
  and EFOR +33.2 are +69.5R of it, the other 44 net −15.0R; 11 of 46 spend three stops and never
  position; charging gap-throughs the worst name is −5.8R. Candidate for a forward read, not an
  edge. Retries SUBTRACT on the 620 rung.
- **Missed-EP tail read (`545p2`):** the skip buckets' tail share is roughly the admitted cohort's
  once contamination is removed; the bracket realized ≥4R on **zero** of the proxy-tail names it
  entered. Conversion, not admission.
- **Day-1 stop × target × runner sweep (`545p3`):** on admitted names tighter wins (0.5×ADR
  +14.2R paired, ORB low +11.4R; 1.0/1.25×ADR FAIL); the target pin is worth +5R and all of it is
  +0.33R scratches; t3 +16.1R on 55 takers, three-name-carried; retries lose at the live stop.
- **Bull read (`exit_tune_bull_regime_read_2026-09-02.md`):** stop conclusions are
  tape-independent; harvest conclusions are era-confounded (Bull = eras B+C); re-keyed to
  `LEAST(Bull, 4 × non-Bull era-C) ≥ 20`.
- **Selection test (`545_selection_test_2026-09-01.md`):** pre-registered NULL — nothing knowable
  at fire time separates the 18 tail fires from the ~550 losers.
- **The 08-16 widening (Phase 3 §2, P-22):** entry-day deaths 16 → 12 of 22, +2R at equal risk,
  by turning six deaths into five +0.33R scratches; it halved PLTR / ABCL / ETON's R and created no
  winner.

---

## 3. THE INVENTORY (a) — every variant tried, re-graded under "tail first"

Rows carry v2's numbering (`545_entry_exit_program_v2_2026-09-02.md` §3, lines 109–185) so nothing
is re-derived; the two new columns are the TAIL read and the verdict under tonight's objective.
"Tail" = ≥3R / ≥5R count and p90 on the cohort named, from `_545v3_tail_rank_out.txt` where the
cohort is P-REPLAY (admitted, settled, all months unless stated). **INVALID-AS-A-TAIL-VERDICT**
means the result never counted its winners and cannot rank a variant tonight; its direction may
still stand for the mechanism it measured.

### 3.1 Day-1 stop basis — the axis with the most evidence and the sharpest reversal

| v2 # | variant | cohort · n | tail (≥3R / ≥5R / p90) | median | verdict tonight | why |
|---|---|---|---|---|---|---|
| 10 | **`entry − 2R`, pinned target, live ladder (LIVE)** | P-REPLAY admitted 65 · P-LIVE era C 4 | **0 / 0 / +1.43R**; ex-May 0 / 0 / +1.35 (n=51); P-LIVE 26 re-walked: 0 / 0 / +1.14 | +0.21 (+0.33 modal) | **the baseline — and it is the tail-poorest cell on the board** | the pin is worth +5R, all in scratches (Phase 3 §6); the widening's whole gain on P-22 was deaths → scratches; it halved every real winner's R |
| 9 | ORB low (retired 08-16) under today's ladder | P-REPLAY admitted 59 | **6 / 3 / +2.85R**; ex-May 4 / 1 / +2.69 (n=46); Bull 4 / 3 / +4.10 (n=36), non-Bull 2 / 0 / +1.54 (n=23) | −1.00 | tail-preserving here; **the 08-16 retirement read ranked on sum/median at equal dollar risk over 43 reconstructed Apr–May trades (its 60-day companion reported a ≥5R share of 2.3% for the then-live stop — `let_it_run_and_risk_2026-08-16.txt:36`) plus P-LIVE era A's 0-for-12 under a stack with no partial at all. Different population, different stack, different grain: it cannot be ranked against this read in either direction, and nothing here disturbs the signed stop — the forward recorder is what decides it** | paired vs live on 58: +11.4R, +6 names ≥3R, +3 ≥5R, p90 +1.43 higher, median −1.25 lower. Bound +3.9R ex-gate. INFQ, QBTS, ARGX, U, CLF, PLTR carry it |
| 12→P3 | **0.5×ADR, pinned** | P-REPLAY admitted 57 | **7 / 2 / +3.63R**; ex-May 6 / 2 / +3.63 (n=46); Bull 4 / 1 / +3.84 (34), non-Bull 3 / 1 / +3.63 (23) | −1.00 | tail-preserving; **candidate for a FORWARD read only** — #482 night one has it worst at n=6; 28% of admitted campaigns abstain (fill-minute straddles); 56% of its stops sit inside the opening range | HTFL +7.2, PLTR +5.4, ABCL +4.5, ARGX +4.2, CLF, QBTS, ZBRA. **Costs TEAM (stopped day 0) and MRNA (stopped, −1.00R)** — two of the four operator-labelled EPs it can see |
| 12→P3 | 0.75×ADR, pinned | admitted 64 | 3 / 0 / +2.56R | −0.76 | marginal; keeps TEAM (+0.34) and MRNA (open +3.28) that 0.5× loses | U, HTFL, PLTR |
| 12→P3 | 1.0 / 1.25×ADR, pinned (the day-2+ band on day 1) | admitted 66 / 67 | **2 / 0 / +1.83** · **0 / 0 / +1.54** | +0.10 / +0.13 | **tail-destroying by R-unit dilution — FAIL on both criteria** | the same moves pay half the R; wider stops die on day 2–5 instead (the 08-06 delay mechanism, reproduced pinned) |
| 12 | ADR floor with the target MOVING with the stop (08-06) | 14 live, minute-bar | 0 winners at every k | — | **INVALID** — the frame was removed on 08-16 (target pinned); Phase 3 §6 reproduces the mechanism and re-answers it | own-unit target: partials 54 → 32, every wide stop worse |
| 11 | ORB-multiple widening 1.25/1.5/2× | 12 live + sim 147 (08-03) | not reported | Δ 0.00 | **MEDIAN-ONLY, one era → INVALID-AS-A-TAIL-VERDICT**; superseded by the monotone Phase 3 result (wider = fewer tails) | — |
| 13 | ATR-0.5× / ATR-1.0× / prior-day-low (#572) | 30 live day-0 (08-18) | not reported | ATR-0.5× the lone positive | ONE-COHORT; Phase 3 §9 reproduces the ordering | — |
| 15 | prior-day low on day 1 | 12 live (08-03) | "5× winner shrink" | — | REFUTED — a ~20% stop dilutes every tail by construction; direction valid | — |
| 14 | **closing-basis stops** (hold through intraday breaches) | 75 reconstructed HIGH Apr–May; 43 at 60 days | **≥5R share 1.3% → 5.3%, max +20.78R; +16.8R at equal risk at 60 days** | — | **the one stop-basis variant that was measured on the tail and improved it — ONE-COHORT (old admission, daily grain past day 0), never re-run on P-REPLAY**; cost = unbounded intraday risk (MANE −19.6R excursion) | needs an `ep_replay` stop mode (§5.2) |
| 16 | stops for a re-entry leg (bar-anchored) | n=15 (08-07); n=602 rungs | dominated on every rung | — | REFUTED for bar anchors; ADR anchors are the only shape that worked | — |

### 3.2 Harvest — partial, breakeven, runner rules (the axis tonight's objective re-orders)

| v2 # | variant | cohort · n | tail (≥3R / ≥5R / p90) — settled · settled+open marks | median | verdict tonight | why |
|---|---|---|---|---|---|---|
| 17 | **+2R partial 1/3 → breakeven → SMA trail (LIVE ladder)** | P-REPLAY admitted 65 | 0 / 0 / +1.43 · +0 marks | +0.21 | **the identified tail-killer is the BREAKEVEN step, not the partial**: TEAM (§2.1); 18 of 35 admitted takers scratch; PLTR's rule cost was 0.57R = 15% as designed (v2 #17) | every cell below that removes the breakeven floor shows the tail in its OPEN rows |
| 29 | `breakeven` only (partial, breakeven, NO trail) | admitted 55 settled + 12 open | 0 / 0 / +0.33 · **2 ≥3R in marks (TEAM +4.7, ARGX +3.1)**, marks sum +21.7R | −0.26 | the trail is what BANKS the small gains (live +3.5R vs −19.2R settled here); the breakeven is what CAPS the large ones | 12 of 67 still open — censored |
| 29 | `hard` (partial, then the 2/3 rides the ORIGINAL stop; no breakeven, no trail) | admitted 52 settled + **15 open** | settled 0 / 0 / −0.33 · **+2 ≥3R in marks (TEAM +4.7, ARGX +3.1; PLTR +2.7, ABCL +1.8, HTFL +1.8 …), marks +24.8R vs settled −33.9R** | −0.70 | **cannot be graded settled-only** — the tail is exactly the 15 rows the horizon cut; the cost side is real and PAIRED: **−20.9R vs the ladder on the 52 common settled rows** (a round-trip pays −0.33R here vs +0.33R live, ≈0.67R per scratch name); `breakeven`-only is −9.1R paired on 55 | under 0.5×ADR: 7 open, **5 ≥3R in marks** (HTFL +9.1, PLTR +8.5, ABCL +6.1, ARGX +5.2, CRWD +3.6), marks +37.8R vs settled −35.2R (paired vs the 0.5×ADR ladder: −27.9R on 48) — the tail intact, the scratches paid |
| 29 | **t3** — sell the 2/3 at the 3rd close after the partial | admitted 65 | **5 / 1 / +2.23**; ex-May 3 / 1 / +1.84 (n=51); Bull 4 / 0 (41), non-Bull 1 / 1 (24) | −0.33 | direction, tail-positive vs live (+5 names, +16.3R paired); FTK, EROC, RDW, QBTS, ARGX | #482's `harvest_t3` arm reads it forward (+0.422 at n=6) |
| 29 | t5 · atr1 · atr2 · gb25 | admitted 65 / 66 / 63 / 65 | 3 / 1 · 3 / 1 · 2 / 1 · 2 / 1; p90 +1.76 to +2.02 | −0.30 to −0.33 | direction only; t5 and atr2 keep 2 names ≥4R each, the others 1 | FTK, QBTS, INFQ carry |
| 29 | sma10 · sma20 · t10 · t20 · gb50 | admitted 62 / 57 / 62 / 54 / 60 | 1 / 0 · 0 / 0 · 1 / 0 · 0 / 0 (+2 in 13 marks) · 0 / 0 | −0.33 to −0.39 | **long holds on a DAY-1 entry give it back** (t20 −29.3R settled) — consistent with the conversion-rehearsal finding that the real runs start 7–21 sessions after the EP and often from BELOW the EP-day low, i.e. through the day-1 stop | the P-194 "t20 best mean" read is on a different population and had no CI |
| 18 | partial vs FULL exit at +2R | 15 old losers · PLTR | full exit caps every tail at +2R by definition | — | **REFUTED by the objective function** — recorded so it is never adopted on a mean-R argument | — |
| 20 | exit-ALL at +2R / +3R / 1 ADR | paper runners; PLTR | BW +10.16R → +2.00 | — | REFUTED by THE GOAL (v2) — same reason | — |
| 19 | breakeven armed at +1R vs +2R | 2 paper runners | +1R arm destroys GOOGL's +8.18R | — | mechanism (n=2): a LOWER breakeven trigger is more tail-destroying; never lower it | — |
| 22 | giveback peak-lock | 28 paper · shadow 0 | a peak-lock caps the tail by construction | — | **RULED OUT 08-11 ("we let winners run") — consistent with tonight's objective; closed** | — |
| 24 | seeded SMA10/20 trail | paper 33 · 116 extension names · P-REPLAY | cut zero names by >0.5R on 116 (v2); on P-REPLAY the ladder (BE + trail) vs `breakeven` (no trail) = +22.7R settled | — | the trail is a BANKER of small gains, not the tail-killer; on the delayed rungs it keeps 6 of 25 ≥4R touches vs 13 on hold-only (v2 §9) — there it halves tail retention | — |
| 21 | trigger unit (R vs ADR vs %) | 12 live + 43 · 9 + 31 | not reported | — | MEDIAN-ONLY; blocked on runners → INVALID-AS-A-TAIL-VERDICT | — |
| 25 | **second partial higher up (5R / 8R / 10R / 15R × fraction)** | none live; P-REPLAY now has 5 names ≥5R under 0.5×ADR × t3 | — | — | **NEVER-RUN; now RUNNABLE on replay** (§5.2) — the operator's own "make sure we don't round trip a big winner" | — |
| 23, 26, 27 | day-3/5 time partial · structural take / day-2 gap sell · character time exit | — | — | — | inert · complement only · operator-deferred | — |
| 28 | management arms on DELAYED entries | missed 23 (08-30) · 267 caught EPs | missed cohort: no-management +162R vs live shape +52R (trail −72R, partial −37R); caught EPs: trail beats hold on every rung | — | DIRECTION ONLY, sign flips with population (outcome-conditioned label) — but the missed-cohort read is a tail read: **the live harvest gave back two-thirds of what the entry found** | — |
| 30, 31 | breakeven delayed 1/3/5 days; horizon 20 / 40 / 60 | 116 · 75 HIGH · 602 fires | noise on the HIGH cohort | — | ONE-COHORT; horizon unpriced (§5.2) | — |

### 3.3 Day-1 entry timing

| v2 # | variant | cohort · n | tail | verdict tonight | why |
|---|---|---|---|---|---|
| 1 | **ORB 1-min breakout (LIVE)** | P-REPLAY 267 · P-LIVE 26 | the SAME entries carry 6–12 names ≥3R under a tight stop or a non-breakeven runner (§3.1–3.2) | **the entry is not the tail-killer**; its cost is the 46 abstain / 37 no_entry / 81 detected-late campaigns (§5.1) | — |
| 2 | ORB 5-min entry + 5-min stop | P-5m 38 · 22 pairs | **≥4R: 1 of 38, and it is a daily-bar REPLAY row (AMBQ)**; real-time 0 of 22, median −0.99R | REFUTED as entry+stop (three reads, tail included); era-C pairs n=3 | — |
| 3 | ORB 5-min entry + INDEPENDENT stop | none | — | NEVER-RUN (§5.2) | — |
| 4 | `stop_too_wide` skip (1.5 × ATR14) | 4 replayable of 27 rows | HTFL +7.2R at 0.5×ADR is the only tail; n=4 | OPEN — blocked on population (§5.1) | — |
| 5 | wait-for-established-low entry (#572) | 30 live day-0 | not reported (−1.17 ADR/pair median) | MEDIAN-ONLY → INVALID-AS-A-TAIL-VERDICT; a fade detector | — |
| 6 | anticipation coil (Family A) | shadow 150 | "median reached +2.44R" is MFE | different setup; MFE-based | — |
| 8 | gap-over open on the EP-day high | none | the 09-01 grid's high-break winners GAP over the level | NEVER WRITTEN as a setup (needs a buy point + stop from the operator) | — |
| — | **the pivot-proximity split** (`docs/analysis/pivot_proximity_2026-08-16.txt`, 99 HIGH alerts, 60 sessions) | Apr–May | names that NEVER came back to the EP-day low: **66–83% reach ≥8×ADR**; names that touched it: 43% | **structural, and it is the entry-timing finding under a tail objective: the strongest names never offer a pullback entry.** Day-1 (or a high-break) is the only entry for the biggest tail; delayed entry harvests the weaker half's tail | one cohort, old era; the direction has held on every delayed-entry read since |

### 3.4 Re-entry and attempts

| v2 # | variant | cohort · n | tail | verdict tonight | why |
|---|---|---|---|---|---|
| 32 | same-day 1-min re-entry (R3) | 7 (to 05-17) | 0 | REFUTED; stale era; config off | — |
| 33 | same-day 5-min-range-clear re-entry | 17 live stop-outs (08-09) · P-REPLAY | 17: THC +12.43R on a **0.67%** stop (next door to the near-zero class — flagged), 6 second stops; P-REPLAY admitted: at the live stop +1 name ≥3R for −4.3R; at 0.5×ADR **+0 names** vs one attempt (7 vs 7) for −10.9R; at ORB low +2 names (8 vs 6) for +1.1R | ONE-COHORT at n=17; on P-REPLAY it adds tail only at the ORB-low stop and costs sum everywhere | Phase 3 §8 (all-alert): 55–65% of fires pay a second stop |
| 34 | **next-day open re-entry after a stop-out (`ndo_o5l`: open after the first 5 minutes, stop = that 5-min low)** | 14 (08-07) · **P-REPLAY admitted 57** | 14: THC-carried; **P-REPLAY, 0.5×ADR × ndo_o5l: 9 / 3 / +3.84R, +20.2R vs 7 / 2 / +3.63R, +16.1R one attempt; ORB low × ndo_o5l: 8 / 4 / +3.39R, +20.9R vs 6 / 3, +14.5R. The two names it adds are the SAME two under both stops: THC 07-24 (leg 2 +12.23R) and TEAM 08-07 (leg 2 +4.06R). THC's leg-2 stop is the 07-27 first-5-minute low 234.23 against a 235.48 entry = 0.53% wide** — one hundredth of a percent outside the near-zero-stop exclusion, the same class as its 0.67% same-day cousin (v2 #33). **TEAM's leg-2 stop is 2.23% wide and legitimate** (entry 148.30, stop 145.00). Leg 2 fires on 27 names; ex-THC-and-TEAM the second legs net **−12.2R** (ORB low: −9.9R) | **DIRECTION ONLY, THC/TEAM-carried — and THC is thin-stop-adjacent.** Honest read: the mechanical form of the operator's own TEAM re-entry adds ONE legitimate tail name on this population and pays about −12R across the other 25 second legs. Phase 3 graded the cell FAIL on the ALL-alert population by SUM; at the live stop it adds nothing (0 / 0). Worth Phase 3's per-name read, not a candidate | leg-2 stop widths are NOT in `_545p3_cells.tsv` (only leg 1's) — screened by hand for the two carriers only; per-name worst −2R by construction; gap-through charging not applied; the operator's real tactic ("the low forming, turn back up") is not this signal |
| 35 | base-then-turn proxies (higher lows / higher closes / 20–45-min base) | 15 (08-07) | 9–13 second stops per variant | ONE-COHORT; never ported to `ep_replay` (§5.2) | — |
| 36 | 620 MACD cross | 15 · 44 · 267 | noise alone; ≈ break-even at a pivot | consistent across three reads | — |
| 37 | same-day attempts 1–4 | 75 reconstructed HIGH | 2 attempts catch the one +20R name 1 attempt missed; 3–4 add cuts, no catch | ONE-COHORT; per-name accounting done; direction tail-positive at 2 | — |
| 38 | campaign policies R1 / R2 / R3 | missed 43 / 23 | R3 +12.9R at −2.5R failed-attempt cost | outcome-conditioned; direction only | — |
| 45 | **the retry test** (tight stop × ≤3 tries on the delayed rungs) | P-DELAYED 46 ex-May | **4 names ≥4R vs 2**; two names = +69.5R of +54.4R; 11 of 46 never position | candidate for the FORWARD read; `delayed_entry_adr_stop_variant_025_545` records the single-shot leg only — **the chain cannot be reconstructed forward** (the lane keys re-entries off the incumbent's stop) | §5.3 |
| 39 | the lane's bounded re-entry rows | P-LANE | accruing; ~693 rows on 09-01 | first honest read 09-22 | — |
| 40 | N-day re-entry on HIGH alerts, daily bars (wait 3 → 20 days) | 99 HIGH Apr–May | **catch of the 40 ≥5R names rises 18% → 28% with the wait — and still misses 72%** | superseded by minute-bar work, but it IS a tail read and the 72% is the pivot-proximity split in another form | — |
| 41–44 | the four delayed rungs · ADR band · selection null · day-1 group | P-DELAYED | recall 96%; **18 of ~570 fires ≥4R (3.2%)**, median −1.00R on every rung; 0.75–1.0×ADR × trail keeps 6 of 25 ≥4R touches (hold-only keeps 13); nothing at fire time separates the 18; the stopped-out group is the worst place to re-enter (1 in 60 ≥4R) | LOAD-BEARING for recall and for the null; the expectancy is a cost-per-tail question: **~30 full stops per ≥4R fire at the incumbent stops** | #616 / 025 forward gates |

### 3.5 Missed EPs

| v2 # | variant | cohort · n | tail | verdict tonight |
|---|---|---|---|---|
| 45–46 | the five skip buckets | P-MISSED | tail PROXY 19–22% vs 10.7–13.8% admitted, before contamination; after: roughly the same rate; the bracket converted **0** of the proxy-tail names it entered to ≥4R | conversion, not admission (`545p2`) |
| 4 / 46 | `stop_too_wide` | 4 replayable | HTFL | blocked on population (§5.1) |
| 47 | extension filter vs the tail | 159 names | 17.6% doubled — **MFE** | INVALID as a harvest read; population description only |

### 3.6 Headline tally under the tail objective

- **~48 variants measured; ranked on the tail, the board has ONE family with evidence: tight
  day-1 stop × non-breakeven / short-time runner** (§3.1–3.2) — every cell in it is one replay
  population and needs the forward gate. **One re-entry cell adds a single legitimate tail name**
  (next-day open at a tight stop: TEAM; its other add, THC, sits on a 0.53% stop — §3.4 #34).
  **One stop-basis variant preserved the tail on an old cohort and was never re-run**
  (closing-basis, §3.1 #14).
- **Eight prior results cannot rank a variant under tonight's objective** because they ranked on
  median or sum without counting winners, or read MFE as a return: v2 #5, #11, #12 (moving-target
  frame), #21, #29's P-194 "t20 best mean" ranking, #47 (MFE), and the two P-5m "20 of 21 losers
  rose" MFE reads. Their MECHANISM findings stand where stated. The 08-16 signing read is NOT on
  this list — it reported a ≥5R share — but it is a different population and stack (§3.1 #9).
- **Variants that have ever acted on real money: three** (v2 §3.7). Live ≥4R winners: **zero.**
- **The operator-labelled ground truth** (`operator_labelled_eps.md`) under each cell, P-REPLAY:
  the live stack pays PLTR +1.69 · TEAM +0.33 · HTFL +1.43 · MRNA open +1.64 — **none ≥3R**;
  0.5×ADR × t3 pays PLTR +5.70 · HTFL +8.70 and **loses TEAM and MRNA at −1.00**; ORB low × t3
  pays PLTR +3.58 · HTFL +3.46 · MRNA +3.09 and loses TEAM; `hard` at the live stop keeps all four
  open (TEAM +4.73 · PLTR +2.69 · HTFL +1.81 · MRNA +1.64). **No cell keeps all four AND converts
  two of them past 5R — that is the trade the operator is choosing between.**

---

## 4. THE PARAMETER SPACE (b) — the grid, stated

Every cell below is judged on: ≥3R count · ≥5R count · p90 · then median · then sum, on P-REPLAY
admitted (all months and ex-May), by entry-stamped regime, settled AND open-marks, and on the four
operator-labelled names. Levels marked **LIVE** are the acting rule; ✅ swept tail-first on
P-REPLAY (this card); ◻ hole; 🔒 operator-ruled.

| axis | levels | swept? |
|---|---|---|
| **A1 entry timing** | ORB 1-min (**LIVE**) · ORB 5-min + 5-min stop (⛔ refuted) · ORB 5-min + independent stop (◻) · same-day 5-min-range-clear re-entry (✅) · next-day open re-entry `ndo_o5l` / `ndo_pdl` (✅) · base-then-turn proxies HL2/HL3/HC2/HC3/BASE20/30/45 (◻ on P-REPLAY) · the four delayed rungs, wait 1–20 sessions (✅ on P-DELAYED) · gap-over open on the EP-day high (◻ undefined) | partial |
| **A2 stop basis (day 1)** | ORB low (✅) · `entry − 2R` (**LIVE**, ✅) · k×ADR20, k ∈ {0.25 ◻, 0.5 ✅, 0.75 ✅, 1.0 ✅, 1.25 ✅} · closing-basis (◻ on P-REPLAY) · structure: prior-day low (⛔), session low-so-far / basing low (⛔ for re-entry legs) | mostly |
| **A2b target frame** | +2R pinned to the ORB R (**LIVE**, ✅) · own unit (✅, worse in every wide cell) | done |
| **A3 profit-take** | +2R × 1/3 (**LIVE**) · none (◻ on day 1 — every Phase 3 cell takes the partial) · ADR-multiple trigger (◻) · **second partial at 5R / 8R / 10R / 15R × 1/3 (◻, operator's 08-08 variant, now runnable)** · exit-all (⛔ by objective) · giveback peak-lock (🔒) | **hole** |
| **A4 post-partial floor** | breakeven (**LIVE**, ✅) · none (✅ as `hard`, censored) | done, censored |
| **A5 runner rule** | ladder = breakeven + SMA10/20 trail (**LIVE**) · breakeven-only · hard · live_trail_be · sma10 · sma20 · atr1 · atr2 · gb25 · gb50 · t3 · t5 · t10 · t20 (✅ all 14) · trail-only with NO partial (◻ day 1; #482 arm) · regime-conditional (`rgm_*`, #508's 34-candidate family — snapshots lost, ◻) | mostly |
| **A6 hold horizon** | 20 sessions (**LIVE** by construction of the reviews) · 40 · 60 (◻; P-REPLAY's 08-31 horizon can only reach 40 for campaigns before ~07-03) | hole |
| **A7 attempts** | 1 (**LIVE**) · 2 (✅ three signals) · 3 · unlimited-in-window (✅ on P-DELAYED only) × re-entry shape same-pattern / new-high-break / either (✅ P-DELAYED) | partial |
| **A8 regime** (cross-cutting) | Bull / non-Bull, entry-stamped (✅ for 7 key cells — P-REPLAY is 40 Bull : 25 non-Bull on the admitted 65) | done |
| **A9 sizing** (named, operator-owned #571) | fixed risk-based (**LIVE**) · size-down-not-skip for `stop_too_wide` (◻, same dollar risk) | hole |

**What the sweep already covered:** Phase 3 = A2 (5 bases) × A2b (2) × A5 (14) × A7 (3 signals at
attempts=2) on P-REPLAY = 105 cells (`_545p3_cells.tsv`), now all tail-ranked. The retry test =
A2 (4) × A7 (4) × exit (2) × 4 rungs on P-DELAYED = 128 cells. **The holes that tonight's
objective makes urgent are A3 (no partial; second partial) and A4/A5 on the OPEN rows** — the
harvest side, where the tail is being given back.

**Grid discipline (pre-registered for every run in §7):** cells are compared PAIRED on the live
cell's settled rows; every cell reports its abstain and open counts and the "if every dropped row
were −1R" bound; a cell wins on the tail only if its ≥3R count exceeds the live cell's on the
paired set AND holds ex-May AND does not depend on one name (drop-best stated); the median cost is
always printed beside it, never used to rank.

---

## 5. ANSWERABLE NOW vs NEEDS CAPTURE (c) — per cell, with the harness

### 5.1 The population gap — a first-class finding, and a prerequisite

**The arithmetic:** 267 campaigns → **182** ever submittable (81 detected at/after 09:45 and 4
setup rejects never reach the ORB window) → **145** admitted by today's scorer (44 undecided on the
float bonus) → **65** settle under the live stop (46 abstain at 1-minute grain, 37 never cross the
ORB high) → **46** ex-May → **4–7** names ≥3R in the best cell → **2** of them are operator-labelled.
A stop or harvest verdict at this depth is a direction. The operator asked for a sweep.

**What is NOT in P-REPLAY at all, and why:**

| missing population | why it has no bars | size | the $0 path |
|---|---|---|---|
| `stop_too_wide` refusals: **19 of 27 rows absent; 4 more present but never entered** (AIP, PONY float-straddle abstains; GO reject; BULL admitted-no-entry) | P-REPLAY = live-source `mi_ep_alerts` 05-11 → 08-28. Refusal rows come from BOTH account modes and every strategy, some before 05-11, some on alerts that were never live-source; "27" is rows, not names — `stop_too_wide_outcome_cohort_2026-08-17.md` counts **9 MAGNA53 names** | ≤27 rows | (1) dedupe by (ticker, date, strategy), drop deprecated strategies (`9m_day2`, `fishhook_v3`, `flag_continuation` — `analysis_standard.md` §2); (2) fetch day-0 SIP minute bars for the survivors the way `_623_fetch_bars.py` did for 2,399 ticker-days at $0 |
| BAND 04-30 · STRL 05-05 · EVER 05-05 · TTMI 04-30 | never live-source alerts; predate the capture; now tagged `session_rvol_low` / `duplicate_scan` in the missed table | 4 | same fetch; their +110% / +32% are 20-day daily marks with no bracket walked |
| scan-level skip buckets (`outside_top20`, `score_below_50`, `session_rvol_low`, `mcap_low`, `adv_low`) | never alerts → no ORB, no minute bars unless the name was an alert on another day | hundreds of ticker-days | the #623 population ALREADY covers 3,458 scan-log ticker-days since 06-08 with SIP bars fetched — **the bracket replay on skip buckets is answerable from `_623_replay_out.tsv` today** for 06-08 onward; pre-06-08 needs a fetch |
| CHPT 09-03 (operator-labelled; `filter:mcap_too_small`) and every name after 08-28 | after the capture; never scored | growing | re-pull `mi_ep_alerts` + bars past 08-28 (read-only, seconds) |
| the 46 abstains and 9–16 fill-minute straddles | 1-minute grain cannot order a stop and a target inside one bar | 46 + up to 16 | tick/quote data (Alpaca SIP is subscribed; a build, not a spend) — or the #482 recorder, which sees the real fill |
| the 44 `abstain_float_band_straddles_bar` admissions | the float bonus is not a stored fact | 44 | store it at alert time (capture-only build) |

**Probe for the first row (read-only, seconds; NOT run by this card):**
`SELECT ticker, alert_date, signal_type, account_mode, COUNT(*) FROM mi_live_trades WHERE
skip_reason LIKE 'setup:stop_too_wide%' GROUP BY 1,2,3,4 ORDER BY 2;` joined to
`mi_strategies.enabled` and to `mi_ep_alerts.source` — the dedupe and the absence explanation in
one query. Then the SIP fetch for the survivors.

### 5.2 Cells answerable NOW, $0, on data already captured

| cell | harness · what exists | build needed | cost | what it cannot see |
|---|---|---|---|---|
| **no partial at all** (stop + trail only; stop + hold-to-horizon) × {`entry − 2R`, ORB low, 0.5×ADR} | `ep_replay.RuleSet(intraday_partial_r=None, trail_prior_closes=True, …)` is constructible today (era_a already uses `None`); `runner_rule="hard"` with no partial = hold | **none** — a sweep run | ~½ session | a partial that live would have taken; horizon censoring — report marks |
| **second partial at 5R / 8R / 10R × 1/3** on top of {0.5×ADR, ORB low} × {t3, t5, hard, ladder} | `RUNNER_RULES` mirror the #2 lineage; a second-rung partial is a small addition to `_walk_leg`'s runner branch (`ep_replay.py:613–803`) | small (one rule + 2 tests); `validate` must stay PASS | ~½ session | only 5–8 names ≥5R exist to test it on — a mechanism read, stated as such |
| 0.25×ADR on day 1 | `adr_k=0.25` constructible | none | minutes | abstains rise as the stop tightens (0.5× is already at 28% of admitted campaigns) — report the count against the harness's 30% ceiling |
| **tight stop × next-day re-entry, per NAME, gap-through charged, regime cut** | Phase 3's `x2:ndo_o5l` / `ndo_pdl` legs; this card's tail read (§3.4 #34) | per-name ledger + gap-through charging as the retry test did (`_545_retry_test.py` §4 method) | ~½ session | the operator's real tactic; slot competition; a third attempt (needs `attempts=3`) |
| base-then-turn re-entry proxies on P-REPLAY | signals live in `_545_reentry_sweep.py`; `REENTRY_SIGNALS` has three | port HL/HC/BASE signals into `ep_replay` (`_attempt_two`) | ~½ session build | same |
| closing-basis day-1 stop | none on `ep_replay` | `stop_mode="close_below"` in `_walk_leg` (day 0 needs the session close; later sessions the daily walk already has) | ~½ session build | unbounded intraday risk must be reported as MAE, not just R |
| horizon 40 / 60 | `LAST_SETTLED = 08-31` (`ep_replay.py:101`) | none for campaigns ≤ ~07-03 (40 sessions); a re-pull past 08-31 for the rest | minutes / one read-only pull | — |
| ORB 5-min entry + independent stop | none | an entry-range mode | ~½ session build | the 5-min lane's self-censoring |
| the bracket on scan-level skip buckets since 06-08 | `_623_replay_out.tsv` already walked 1,590 settled ticker-days under era_c and carries `nearest_filter_reason` / `reject_stage` / `ever_scored` / `best_score_tier` on every row (header verified) | none — a group-by, with the 13 near-zero-stop rows removed | ~¼ session | pre-06-08; the tag is the nearest-09:31 tick's reason |
| the regime cut on every cell | this card (`_545v3_tail_rank.py`, 7 cells) | extend to all 105 | minutes | P-REPLAY is 40 Bull : 25 non-Bull; era confound inside Bull is smaller here than in P-LIVE because every campaign runs the SAME stack |

### 5.3 Cells that need ACCRUAL (forward gates already registered — nothing to build)

| cell | gate | today | first read |
|---|---|---|---|
| tight day-1 stop vs live, PAIRED on real fills; the three harvest arms (`no_breakeven`, `trail_only`, `t3`) | `live_fill_counterfactuals_first_read_482` (`data_gated_reviews.yaml:10741`) — 20 era-C fills with `live_actual` + all three stop arms settled | 6 fills (09-04) | ~4–6 weeks at ~5 fills/month **per arm settling**; tight arms settle first — the gate counts complete sets on purpose |
| the delayed rungs' real tail rate | `delayed_entry_shadow_first_read` (`:10362`) — 30 settled triggers | fires from 08-25, 9 of 20 sessions elapsed | 2026-09-22 (PLAN #327 ETA) |
| the 0.75–1.0×ADR band out of sample | `delayed_entry_adr_stop_variant_616` (`:10398`) — 30 trail-settled `ep_low_reclaim` fires | recording since 09-02 | ~6+ weeks |
| the 0.25×ADR single-shot leg (NOT the chain) | `delayed_entry_adr_stop_variant_025_545` (`:10440`) | same | same; **a negative here does not refute the retry chain** |
| the n-milestone exit review | `exit_tune_cohort_review` (`:9025`) — 20 era-C closes | 4 era-C closes (09-02) | ~3 months at ~5/month |
| the Bull read, run 2 | `exit_tune_bull_regime_read` (`:9238`) — `LEAST(Bull, 4 × non-Bull era-C) ≥ 20` | Bull 10, non-Bull era-C 1 | non-Bull era-C accrues by trading |
| the operator's own delayed fill (TEAM 08-07, $144.39, stop = low of day 141.51) | none — one fill, a fixture | stock 189.58 on 09-04 → **+15.7R unrealized on that stop** if still held | write the outcome into `must_not_miss_eps.py` when he closes it |

### 5.4 Cells that need NEW CAPTURE or a definition (and the one that costs money)

| cell | what is missing | cost |
|---|---|---|
| the retry CHAIN forward (attempts 2–3 keyed on the VARIANT's stop) | a re-entry lane keyed on the variant, not the incumbent — "not built, not scoped, a bigger change" (PLAN #545, 09-02) | build; operator-scoped (it emits watch rows only, but it is a lane) |
| sub-minute fill reality for a 0.5×ADR stop (16 of 99 straddles) | tick/quote data at the fill; nothing stores the NBBO ask (#541 class) | Alpaca SIP is subscribed → $0 data, a build |
| gap-over open entry on the EP-day high | a buy point and a stop from the operator | his definition first |
| regime-conditional exits (`rgm_*`) | the 08-17/08-22 engine snapshots are gone; `_545p4_bull_capture.sql` re-creates the 4-TSV shape | one read-only capture |
| the catalyst re-grade (Stage 1b) | **≈ $40, ceiling $60** (`ep_backtest_spec_2026-08-29.md` §7) — the only priced item in the program; NOT needed for any phase below | operator's stop-point |

---

## 6. THE COST OF EACH CANDIDATE, IN R — stated beside the benefit

All on P-REPLAY admitted, paired on the live cell's settled rows, from `_545v3_tail_rank_out.txt`.
"Cost" = what the median / scratch names pay; "benefit" = the tail. Neither is a recommendation.

| candidate | benefit (tail) | cost (median and the names it loses) | concentration | forward arbiter |
|---|---|---|---|---|
| **remove the breakeven floor after the partial** (`hard`) at the live stop | 15 names still open incl. TEAM +4.7, ARGX +3.1, PLTR +2.7 (marks +24.8R) | **−20.9R paired on the 52 common settled rows** (`breakeven`-only: −9.1R on 55): every round-trip pays −0.33R instead of +0.33R (≈0.67R per scratch name); median −0.70 | the marks are 15 names, not 3 | #482 `harvest_no_breakeven` |
| **0.5×ADR stop, live ladder** | +7 names ≥3R, +2 ≥5R, p90 +2.41 higher; +14.2R paired (bound +0.5R ex-gate) | median −1.33 lower; **TEAM stopped on day 0, MRNA stopped (−1.00R)** — two of the four operator-labelled EPs; 28% of admitted campaigns abstain at 1-minute grain; 56% of stops sit inside the opening range; #482 night one −0.661R at n=6 | HTFL is +5.7R of the margin | #482 `stop_adr_050` |
| **ORB low, live ladder** | +6 ≥3R, +3 ≥5R, p90 +1.43 higher; +11.4R paired (bound +3.9R ex-gate); keeps MRNA | median −1.25 lower; loses TEAM; reverses a signed change on a different population (Phase 3 §11) | INFQ/QBTS/ARGX/U/CLF/PLTR | #482 `stop_orb_low` (+0.028 at n=6) |
| **t3 runner** at the live stop | +5 ≥3R, +16.3R paired | median −0.52 lower; 15 of 35 takers worse; win on takers 100% → ~70% | FTK/EROC/RDW | #482 `harvest_t3` (+0.422 at n=6) |
| **0.5×ADR × t3** | 10 ≥3R / 5 ≥5R / p90 +4.76 (+34.0R paired) | median −1.31 lower; loses TEAM and MRNA; both caveats above compound | spread over 7 names | not recorded forward — a replay-only cell until #482 gains a joint arm |
| **next-day open re-entry at 0.5×ADR** (`ndo_o5l`) | +2 ≥3R vs one attempt — TEAM (legitimate, 2.23% stop) and THC (0.53% stop, thin-stop-adjacent); +4.1R paired | the other 25 second legs net −12.2R; up to −2R per name; second-stop rate ~55% on the all-alert grid | two names; one of them an R-unit artefact | none — needs the variant-keyed lane |
| **0.25×ADR × 3 tries on `ep_low_reclaim`** (delayed) | 4 names ≥4R vs 2; +54.4R / 46 ex-May | 11 of 46 spend three stops and never position; worst name −5.8R gap-charged; 34 of 46 lose | NRIX + EFOR = +69.5R | `_025_545` single-shot only; the chain needs the lane build |
| **size down, not skip** for `stop_too_wide` | HTFL-class names enter at the same dollar risk | n=4 replayable; population gap | — | Phase 2 fetch |

---

## 7. THE PHASED, RANKED PLAN (d) — each phase one card, pass bar written before the run

**Ranking rule:** the phase that can move the operator's next decision at the lowest cost goes
first; every phase reports tail-first (≥3R / ≥5R / p90 → median → sum), paired, admitted, ex-May,
by regime, settled AND marks, and on the four operator-labelled names; nothing is a live change.

### Phase 0 — housekeeping, no card
- `orb_5m_reentry_hybrid_replay` is `status: done` in the registry (`data_gated_reviews.yaml:5020`)
  — v2 §8's "still says pending" is stale; nothing to do.
- The `stop_too_wide` dedupe probe (§5.1) — one read-only query, run by whoever holds prod next.
- **Action for the operator: none** until a phase puts a number beside a fork (§8).

### Phase 1 — THE DAY-1 HARVEST HOLE (P1; $0; ~½ session; Sonnet-grade card)
- **Question:** on the same 267 campaigns, what does each harvest shape that removes ONE element of
  the live ladder do to the TAIL — no partial (stop + trail only; stop + hold), partial without
  breakeven (`hard`, already run — read with marks), and a second partial at 5R / 8R / 10R on top
  of a tight stop — and what does each cost on the scratch names?
- **Harness:** `ep_replay.py` — no-partial rulesets are constructible today; the second partial is a
  one-rule addition to the runner branch (2 tests; `validate` must stay PASS).
- **Cost of the variants, in R (pre-stated):** removing breakeven costs ≈0.67R per round-trip name
  (§6 row 1); removing the partial forfeits the +0.33R bank on every scratch and the 1/3 at +2R on
  every winner; a second partial caps 1/3 of the runner at its rung.
- **Pass bar:** a harvest cell is a candidate only if its ≥3R count on the paired admitted set is ≥
  the live ladder's + 3, holds ex-May, does not depend on one name (drop-best), and its settled +
  marks sum is ≥ the ladder's settled sum − 5R. Report the four operator-labelled names under each.
- **Why first:** the objective function points at the breakeven step (§2.1, §3.2), no day-1 cell
  without a partial has ever been replayed, and #482's three harvest arms are exactly these cells
  forward — the replay and the recorder will be comparable like-for-like at n=20.
- **What would kill it:** if no-breakeven cells only move marks and never settle a ≥3R name by the
  horizon, the tail is a mark, not a return — then Phase 4's recorder is the only judge.

### Phase 2 — CLOSE THE POPULATION GAP (P1b; $0; ~½–1 session; Sonnet-grade)
- **Do:** the dedupe probe (§5.1) → fetch day-0 SIP minute bars for every deduped `stop_too_wide`
  refusal and for BAND/STRL/EVER/TTMI, the way `_623_fetch_bars.py` did → replay them under
  {live, ORB low, 0.5×ADR} × {ladder, t3, hard} → and read the bracket on the scan-level skip
  buckets since 06-08 straight from `_623_replay_out.tsv` (a group-by).
- **Pass bar:** n ≥ 10 replayable refusals before any word about 1.5×; a bucket is a candidate only
  if its ≥3R count per 100 entries beats the admitted cohort's (7 per 57 under 0.5×ADR).
- **Also:** re-pull alerts + bars past 08-28 so CHPT-class and September names enter P-REPLAY.

### Phase 3 — THE TIGHT-STOP RE-ENTRY, PER NAME (P2; $0; ~1 session; Fable-grade)
- **Question:** does a next-day (or base-then-turn) re-entry at a tight stop ADD tail on the
  admitted population at a bounded per-name cost — the mechanical form of the operator's TEAM
  re-entry — and does a third attempt add anything?
- **Harness:** `ep_replay` `attempts=2` legs (`ndo_o5l`, `ndo_pdl`, `sd_5m_clear`) + port the
  base-then-turn proxies + `attempts=3`; per-NAME ledger, gap-throughs charged at the open, worst
  cumulative drawdown per name, regime cut — **and write every leg's stop width into the cells
  file so the near-zero-stop screen applies to re-entry legs** (THC's 0.53% leg-2 stop is why).
- **Pass bar:** ≥ +2 names ≥3R vs one attempt on the paired admitted set, ex-May, with the worst
  name no worse than the extra attempts' nominal risk (retry-test rule).
- **Cost, in R:** up to −N R per name; the all-alert second-stop rate is 55–65%.

### Phase 4 — the accrual gates, on their own clocks (cost 0; no card until a gate fires)
- `live_fill_counterfactuals_first_read_482` at 20 complete era-C fills — **the arbiter for every
  stop and harvest candidate in §6**; read PAIRED, within one admission era.
- `delayed_entry_shadow_first_read` 09-22 · `_616` / `_025_545` at 30 · `exit_tune_cohort_review`
  at 20 era-C closes · the Bull read, run 2.

### Phase 5 — extend the day-1 owner for the remaining holes (P3; $0; ~1 session; Fable-grade build)
- `stop_mode="close_below"` (closing-basis, v2 #14 — the one stop variant that improved the tail on
  its cohort), horizon 40/60 (re-pull past 08-31), ORB 5-min entry with an independent stop, the
  regime cut on all 105 cells. `validate` must stay PASS; retire the #7 lineage after reproducing
  its +16.8R closing-basis headline.

### Phase 6 — operator forks, only once a phase puts a number beside them (each = CHANGE_PROCESS + #151 + sign-off)
See §8.

**Sequencing in one line:** Phase 1 answers the harvest question tonight's objective asks, at $0,
on data in hand; Phase 2 makes every later number a sweep instead of a direction; Phase 3 is his
own tactic in mechanical form; Phase 4 is the only thing that turns a replay cell into a candidate;
Phase 5 closes the grid.

---

## 8. THE FORKS THAT WILL REACH THE OPERATOR — none is pre-decided, none is asked today

| fork | what puts a number beside it | the cost shape he would weigh |
|---|---|---|
| keep or remove the breakeven-at-partial step (the identified tail-killer) | Phase 1 replay + #482 `harvest_no_breakeven` at n=20 | ≈0.67R per scratch name; a book whose median trade goes from +0.33R to −0.33R while the tail stays open |
| a tighter day-1 stop (0.5×ADR or the ORB low) | #482 `stop_adr_050` / `stop_orb_low` at n=20 | loses MRNA/TEAM-class names on day 0; fill-minute risk; reverses a change he signed 08-16 on a different population |
| a short post-partial time exit (t3 / t5) | #482 `harvest_t3` at n=20 | takers' win rate 100% → ~70%; three-name concentration |
| a next-day re-entry rule at a tight stop | Phase 3 | up to −2R per name; the 2% daily-loss limit attributes two stops of one name to one day |
| size-down-not-skip for wide ORBs | Phase 2 | same dollar risk, smaller position; n small |
| a NAMED delayed setup (buy = EP-low reclaim close, stop = entry − 0.75..1.0×ADR, trail) | #616 at 30 | a new order-emission site; day-2+ only |
| the 0.25×ADR × 3-try retry | a variant-keyed lane (build) | −3R nominal / −5.8R gap-charged worst name; 11 of 46 never position |
| the $40 catalyst re-grade | only if he wants the L/U band collapsed | ≈$40, ceiling $60 |

---

## 9. What in the brief and in prior statements is wrong, stale or unverifiable

| claim | what the record shows |
|---|---|
| "TEAM would have HELD by $2.22 … the runner would still be open" | true on the ACTUAL fill (147.13); on the harness's fill (146.80) the same rules stop it at breakeven on 08-10 for +0.33R — one cent of target, one minute apart (§2.1). Both are recorded; the divergence is the finding |
| "the whole book is exactly breakeven: 1,577 trades, −0.42R" | true of **P-623, the candidate universe** (3,458 scan-log ticker-days, 88% rejected by a filter), not of the admitted book (P-REPLAY 65: +3.5R, 0 ≥3R) |
| "88–94% of every name that takes a partial then stops out at breakeven" | not in the repo; the citable figures are 77% (P-194), 48% / 51% (P-REPLAY), 83% (`breakeven`-only runner) — §2.4 |
| "exclude `stop_width_pct < 0.5` from every replay read" | applied: **0 rows** in `_545p3_cells.tsv` / `campaigns_era_c.tsv`; 13 in P-623; 99 in P-LANE. The class lives in the scan-universe and lane populations, not in the alert replay |
| "only 4 of the 27 names that rule ever refused" | 27 ROWS across account modes and strategies; 9 MAGNA53 NAMES on the 08-17 read; dedupe before calling it a population |
| Phase 3: "attempt 2 at a tight stop — FAIL, THC-carried" | still THC-carried on the ADMITTED population ranked on the tail: `ndo_o5l` at 0.5×ADR adds TEAM (legitimate) and THC (0.53% leg-2 stop) and the other 25 second legs net −12.2R (§3.4 #34). Phase 3's verdict stands; what is new is that ONE legitimate name — the operator's own TEAM re-entry — is recovered by it |
| Phase 3: "no runner rule passes … t3 three-name-carried" | still true at the live stop; under a tight stop the tail spreads over 7 names (§3.2) — and settled-only reads of `hard` / `t20` are censored (15 / 13 open rows) |
| v2 §8: "`orb_5m_reentry_hybrid_replay` still says pending" | the registry entry is `status: done` (`data_gated_reviews.yaml:5020`) |
| v2 §2: "87 of 270 open at horizon" | 2 (Phase 3 §3); 85 are `no_trade` |
| "all closed live trades were non-bull" | 26 closed, 10 stamped Bull (Phase 4); P-REPLAY's admitted 65 are 40 Bull — every conclusion here is majority-Bull, the OPPOSITE caveat from July's |
| the 08-16 signing read (43 reconstructed, −6.0R → +11.4R) | ranked on sum/median at equal dollar risk; its companion read did report a ≥5R share (2.3% for the then-live stop at n=43). It and this card's replay are different populations, stacks and grains and cannot rank each other (§3.1 #9). The signed stop is not disturbed — the forward recorder is the judge |

---

## 10. What this does not answer

- **Any cell's tail under today's full stack, forward.** P-REPLAY re-admits 4 months of alerts
  under the current scorer; era C has 4 closed live trades and 3 settled replay campaigns; #482 has
  6 fills. Every tail count above is one replay population, majority Bull.
- **Whether any tight-stop tail survives the fill minute.** 28% of admitted campaigns abstain at
  0.5×ADR; 16 of 99 control campaigns cannot be ordered at 1-minute grain; #482 night one is the
  first real-fill evidence and it points the other way at n=6.
- **Marks versus returns.** Every no-breakeven / long-hold tail number is an open-at-horizon mark
  on 7–15 names; a mark can round-trip. Phase 5's horizon extension and #482's 40-session walk are
  what settle them.
- **The population it cannot see** — §5.1: refused names, pre-05-11, scan-level skips, post-08-28,
  CHPT-class, the 44 float-undecided, the 46 abstains.
- **Portfolio interaction** — slot competition, the 2% daily-loss limit attributing a re-entered
  name's two stops to one day, breakers. Every campaign is priced alone.
- **Fill reality** — spread, LULD halts, our own impact, the venue refusing a limit; the harness
  fills at the ORB high and TEAM shows what 33 cents does.
- **The operator's own tactic.** "The low forming, turn back up" is not `ndo_o5l`; every proxy is a
  modelling choice, and a proxy underperforming him is expected.
- **Whether the EP cohort is a winning cohort on OUR real fills.** Live: 0 of 26 ≥4R. Replay: the
  tail exists in the same entries under different management. The thesis is not contradicted; it
  is not demonstrated on real money.

---

## 11. ⚖ THE LINE

Nothing here changes a stop, a target, a partial, a trigger, a re-entry rule, sizing, a safeguard,
a lane, a toggle or any live table. No prod query was run. The only files this card created are
this document, `scripts/probes/_545v3_tail_rank.py` and its captured output — a read-only re-read
of an existing capture — plus a supersession banner on v2 and a pointer line in the delayed-entry
ledger. PLAN.md was not edited. Every fork in §8 is the operator's, reached only through
CHANGE_PROCESS, the #151 harness and his sign-off, and the one dollar item in the program (≈$40
Stage 1b) is his stop-point, not this card's.

---
*Population statement (Gate 6): every figure names its rows and window in §1 and in its table row.
Sources: `scripts/probes/_545p3_cells.tsv` + `_545p3_report.txt` (09-03 sweep) · `_545v3_tail_rank_out.txt`
(this card) · `scripts/ep_replay_data/campaigns_era_c.tsv`, `_pull2_out.txt` (09-01 capture) ·
`scripts/probes/_562bf_daily.tsv`, `_562bf_minute.tsv.gz` (TEAM bars) · `_623_PREREGISTERED.md`,
`_623_analysis_out.txt` (P-623) · `_482n55/read_out.txt` (P-5m) · `_545p2_capture2_out.psv`
(stop_too_wide rows) · `docs/analysis/545_retry_test_2026-09-02.md`, `545p2_…`, `545p3_…`,
`545_selection_test_2026-09-01.md`, `exit_tune_bull_regime_read_2026-09-02.md`,
`runner_rule_sweep_2026-08-29.md`, `stopwide_replay_era_c_2026-09-05.txt`, `pivot_proximity_2026-08-16.txt`
(via the ledger) · `docs/design/545_entry_exit_program_v2_2026-09-02.md` (the inventory numbering) ·
`docs/methodology/analysis_standard.md`, `operator_labelled_eps.md`, `ANALYSIS_CARD_PREAMBLE.md` ·
`docs/setups/delayed_ep_reentry.md` § CONTEXT LEDGER · `data_gated_reviews.yaml` (lines cited) ·
`tests/fixtures/must_not_miss_eps.py` · `scripts/live_rules.py` output 2026-09-05 17:44 PDT.
Related: PLAN #545 · #482 · #327 · #616 · #623 · #562 · #508 · #306 · #503 · #541 · #595 · #571.*
