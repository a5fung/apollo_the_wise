# #702 — Pre-registration: Consolidation Breakout, the holdout read (frozen 2026-10-18)

**MEASUREMENT ONLY. $0. Nothing here changes or proposes to change a strategy, an entry or exit rule, a stop, a
size, a safeguard or any live trade state — every such change is CHANGE_PROCESS and the operator's call (THE
LINE).** This document is a REGISTRATION: it fixes, before a single HOLDOUT outcome exists, which level, entry,
stop, exit and base key the holdout is read on, which rows are the population, which numbers decide, and what each
possible result is called and leads to. The read itself is `scripts/probes/_cb_backtest/runner.py holdout` (P5); it
refuses to run unless this document, the module `agents/market_intelligence/consolidation_breakout.py`, the runner,
the five repo modules the outcome path computes with, every data file, the minute tree, the cell table and every
discovery output match the sha256 pins in §Freeze record (`freeze_check`, the #686 pattern), and it refuses a second
run once `trades_holdout.tsv.gz` exists. Written 2026-10-18 PT (P4 of the approved plan
`/Users/alvinfung/.claude/plans/soft-singing-hamster.md`).

**Blindness, stated precisely.** The daily export (`daily_closes_all.csv.gz`, 20,285 tickers, SPY sessions
2021-09-27..2026-10-16) and the minute tree (1,140 breakout dates, 95,975 (ticker, E) pairs) hold every price the
holdout read will use; nobody has joined a holdout outcome to a holdout candidate. The daily stage never walks a
holdout row (`select_close_variant_candidates`), the minute stage ran on discovery rows only (`read_candidates`
re-derives every row's split from D and raises on a mismatch), and the only holdout file opened for this document is
`entries_holdout_composition.tsv` — entry-time facts (status, abstain reason, width, fill minute) with no fill price,
stop, day-0 or exit column in its layout. Two leaks are known and stated: (1) discovery walks whose forward window
crosses 2024-12-31 read 2025 prices (7,521 filled CLOSE-variant rows; selection is by D, so no holdout trade was
chosen with hindsight, but a discovery R can contain holdout-era prices); (2) the `tl` level was added on 10-17 after
the first discovery read on the three horizontal levels, so the discovery grid was seen before the level that this
document makes primary existed — the reasons for the choice are stated in §2.1 so the reader can judge them.

**Population:** every (ticker, watch night D, level K) in `candidates.tsv` with `split = holdout` (D from
2025-01-01 to 2026-10-15: **n = 109,478 candidate rows; 36,163 first-break trades under the spec key**), entered at
the 5-minute opening-range high on E = D + 1 and walked on the primary exit arm; the decisive cell is C1 on the
trendline level (**n = 43 candidates, 31 filled at ORH5, 2 skipped too-wide, 10 never triggered**). Discovery
(D 2022-03-28..2024-12-31) is n = 118,927 candidate rows / 41,202 spec-key trades and is already read (§2).

## 0. The question and the answers it can give

- **His ask (2026-10-17):** test Qullamaggie's breakout — *"buys the breakouts after a runup and consolidation, it has
  tighter criterias"* — with RS, group RS, entry / exit timing and bull vs bear phase, strict to loose, then run it as
  a parallel shadow / paper lane named Consolidation Breakout. The shadow recorder is live since 10-17 (no money).
- **The decision this serves:** whether a PAPER lane is opened for this setup. His 10-17 ruling lifted the EP-first
  hold, so the paper decision is ours on evidence; **live stays his sign-off**, and every piece of the paper path
  (per-strategy trail mode, the day-3 partial, the ORB window, the risk multiplier) touches the order path and so
  comes back for sign-off piece by piece (plan §Paper path).
- **Possible answers, named now, per deciding cell C0..C7 on the frozen primary triple (§3):** **PASS · FAIL ·
  CAN'T TELL** (§5). The paper decision keys on **C1** (the article's own cell). A PASS in another cell while C1 does
  not pass is a LEAD for the forward read (which term of the ladder helped), never a paper trigger.
- **What a PASS leads to (pre-stated):** a paper-lane proposal (the build list from the plan's paper-path map) carrying
  the caveat of §5.3 — discovery read this rule negative, so a holdout pass is single-block evidence, and the lane's own
  forward read (`consolidation_breakout_forward_read`, ≥ 30 settled C1 primary entries) is the test that decides
  whether it stays. **FAIL:** no paper; the shadow keeps recording; the entry × exit grid is reported for the next
  design round, never as a verdict on the pattern. **CAN'T TELL:** no paper now; the shadow accrues; the forward read
  decides.

## 1. Method and population

**The pipeline (every DECIDING step is a call into the pinned module; the runner loads, schedules, joins, writes):**

| step | what | where |
|---|---|---|
| universe, per session D | common stock / ADR (unknown type admitted), ticker `^[A-Z]{1,5}$`, RAW close ≥ $5 (adjusted × the split factor), 20-session median dollar volume ≥ $10M, 130 CONSECUTIVE SPY sessions of history; exchange test symbols excluded | `cb.universe_ok`, runner `scan_ticker` |
| watch night | the C0 structural gates: prior move ≥ 30% (P = the #592 pole top in [D−45, D−10], pole low over [P−40, P]), no CLOSE above high(P) since P, close ≥ SMA50, deal-pin median range, fresh deal pin (#502), pole data-artifact, ADR20 usable | `cb.explain_watch` |
| cross-section at D | RS = percentile of the 21 / 63 / 126-session return across the universe that night (`rs_best` = the best of the three); group = SIC-2 median 63-session return, groups < 10 members → none; phase = QQQ SMA10 > SMA20 with both rising over S sessions (S = 1 primary, 5 beside); alternative phase = SPY and QQQ above their SMA50 | `cb.cross_section_one_date`, `cb.phase_*` |
| cells | post-hoc flags on the watch row (§3) | `cb.cell_flags` |
| breakout day E | the ticker's next bar, which must be the next SPY session; a breakout is high(E) > the level K(D); K ∈ {k5, k10, full, tl}; ONE TRADE PER BASE under the spec key (ticker, pole_date, K): the first break is the trade, later breaks are retriggers (the chain key — poles ≤ 3 sessions apart are one base — is stamped beside) | runner stage 3, `cb.stamp_retrigger`, `cb.stamp_base_chain` |
| entry | regular-hours SIP minutes, 0.1% slippage: ORH1 / ORH5 / ORH60 = the first minute after the k-minute range whose high exceeds max(range high, level), filled at the level or at that minute's open if it gapped through; PIVOT = the first minute above the level; CLOSE = the daily close above the level. **Stop = the low of the day AT THE FILL** (minutes 09:30..fill), skipped if wider than ADR20(D) (`too_wide`), or if at/above the fill. Abstains counted: no minutes, minute vs daily high/low off by > 1%, minute high never reaching the level | `cb.entry_variants`, `cb.close_entry` |
| breakout-day walk | the remaining minutes of E against the stop: an open below the stop exits at the open, a low at the stop exits at the stop — a full loss booked on day 0, never dropped | `cb.day0_walk` |
| exits | the daily walk from E+1 over 15 arms (§3) plus two controls; horizon 120 sessions then marked ("censored"); a walk that runs out of bars before the horizon is "degraded" = an open mark; R is measured against the ENTRY stop even after breakeven | `cb.walk_exit`, `cb.walk_arms` |
| maturity | decisive numbers use MATURE walks only: a terminal exit (stopped, stopped_day0, trailed, target, time_exit) or the horizon with ≥ 121 forward sessions behind it; everything else is an open mark, counted and never in a number | `cb.is_mature` |

**The split:** discovery = watch nights D 2022-03-28..2024-12-31 (exploratory; the whole grid was allowed and was
read, §2); holdout = D 2025-01-01..2026-10-15, untouched until this freeze, joined ONCE by P5.

**Composition (STEP 0, printed before any outcome — spec key, first-break trades; "cand" = breakouts before entry
abstains, "ORH5" = filled at the primary entry; from `scripts/probes/_cb_backtest/out/step0.txt` and
`step0_entries.txt`, both pinned):**

| cell | discovery cand k5 / k10 / full / tl | discovery ORH5 filled k5 / k10 / full / tl | HOLDOUT cand k5 / k10 / full / tl | HOLDOUT ORH5 filled k5 / k10 / full / tl |
|---|---|---|---|---|
| C0 | 12,169 / 10,194 / 6,554 / 12,285 | 9,034 / 7,280 / 4,100 / 8,989 | 10,413 / 9,010 / 6,186 / 10,554 | 7,564 / 6,170 / 3,645 / 7,570 |
| **C1** | 95 / 88 / 75 / 102 | 77 / 65 / 51 / 79 | 33 / 33 / 33 / **43** | 21 / 19 / 19 / **31** |
| C2 | 7 / 7 / 7 / 7 | 4 / 5 / 5 / 5 | 5 / 3 / 2 / 3 | 3 / 1 / 2 / 3 |
| C3 | 173 / 167 / 132 / 183 | 136 / 124 / 91 / 144 | 100 / 99 / 98 / 107 | 71 / 71 / 63 / 81 |
| C4 | 480 / 446 / 403 / 507 | 363 / 318 / 273 / 371 | 285 / 288 / 258 / 317 | 214 / 194 / 156 / 231 |
| C5 | 182 / 170 / 155 / 198 | 143 / 120 / 106 / 143 | 86 / 76 / 77 / 99 | 62 / 50 / 51 / 74 |
| C6 | 22 / 18 / 16 / 20 | 17 / 14 / 11 / 15 | 7 / 7 / 6 / 6 | 3 / 3 / 3 / 5 |
| C7 | 123 / 109 / 94 / 127 | 99 / 84 / 67 / 101 | 63 / 66 / 67 / 76 | 43 / 45 / 41 / 55 |
| C1_no_retrace (report) | 147 / 130 / 114 / 150 | 115 / 94 / 72 / 116 | 61 / 61 / 57 / 71 | 43 / 40 / 32 / 50 |
| C1_no_tightening (report) | 243 / 240 / 239 / 246 | 191 / 180 / 175 / 195 | 120 / 122 / 123 / 133 | 87 / 84 / 75 / 98 |
| HTF (report) | 575 / 428 / 340 / 601 | 419 / 271 / 211 / 440 | 576 / 468 / 402 / 638 | 407 / 312 / 240 / 460 |

- Under the CHAIN key the holdout C1 ORH5 fills are 18 / 19 / 19 / **27** (k5 / k10 / full / tl); the chain key only
  merges bases, so it is a subset.
- **Data gates (both pass):** discovery — 1,448 of 118,927 fetched candidates abstain on the data (1.22%; minute vs
  daily high/low match 98.93%); holdout — 473 of 109,478 (0.43%; match 99.59%); the limit is 5%.
- **The `tl` population is a SUBSET of the horizontal levels' (a night with no down-sloping line has no `tl`
  level):** no line on 7,649 of 129,985 discovery watch nights and 7,016 of 109,961 holdout nights; the line is
  anchored on a later wick (a base high above the pole top) on 33,629 / 27,427 of them. A `tl`-vs-`k5` difference is
  therefore the level AND the population. The line is the base's highest high projected one session ahead along the
  flattest slope that keeps every later high under it; because it sits UNDER the base high, when ORH5 > the line the
  ORH5 entry fills at the range high, not at the line (the entry rule is max(range high, level)).
- **Holdout maturity, counted from entry-time facts only:** of the 31 C1 `tl` ORH5 fills, 20 have E on or before
  2026-04-24 (≥ 121 forward sessions in the export — mature whatever happened); the other 11 are mature only if they
  reached a terminal exit by 2026-10-16. **So n = 31 is a ceiling and n < 30 is a live outcome (§5, §7).** C0 `tl`
  ORH5: 7,570 fills (2025: 3,761 · 2026: 3,809).
- Era: one rule set end to end (the module is pinned); the data are the same adjusted export for both splits; SIC
  groups are one row per ticker as of 2026-10-16 (constant in time — stated, not point-in-time).

## 2. The decisions, made on the discovery data

All tables: entry ORH5, arm `p33_s3_t10` (sell 1/3 at the close of E+3, stop to breakeven, trail to the first close
under SMA10, remainder sold at the next open), spec key, MATURE walks; R = (exit − fill) / (fill − the entry's own
stop); "ADR P&L" = P&L in units of ADR20 × price (size-free); "acct%" = account P&L at the article's sizing,
position = min(20% of the account, 1% risk ÷ stop width); CI = month-block bootstrap of the mean (calendar month of
E, 2,000 resamples, seed 702 mixed with the group key). The runner printed every table on 10-17 (`report_run_1017b.log`)
before this document was written; the rules below are stated and then applied to those numbers — the reader can check
each against its table.

### 2.1 The breakout level K (primary = `tl`, the down-sloping trendline)

**The rule, stated first (ADR 0023:51 — a plateau, not a peak):** (a) resolve on C0, where n is in the thousands: a
level whose tail share (≥ 5R) or ADR P&L is worse than the best level's by more than the bootstrap noise is off the
plateau; (b) among the plateau levels, C1 must not rank a level last on both tail share and ADR P&L; (c) tie-break
by the pre-registered go/no-go — the level must reach 30 FILLED holdout trades at the primary entry (an entry-time
fact, not an outcome) — then by his own entry description.

| cell | K | n | ≥ 5R | ≥ 10R | mean R | 95% CI | without top 5 | ADR P&L | acct% | median | win |
|---|---|---|---|---|---|---|---|---|---|---|---|
| C0 | k5 | 9,032 | 301 (3.3%) | 74 (0.8%) | −0.213 | [−0.32, −0.10] | −0.233 | −0.089 | −0.08% | −1.00 | 25.0% |
| C0 | k10 | 7,275 | 235 (3.2%) | 62 (0.9%) | −0.214 | [−0.33, −0.10] | −0.236 | −0.104 | −0.09% | −1.00 | 25.0% |
| C0 | full | 4,098 | 107 (2.6%) | 30 (0.7%) | −0.230 | [−0.35, −0.12] | −0.260 | −0.123 | −0.10% | −1.00 | 26.7% |
| C0 | **tl** | 8,985 | 322 (3.6%) | 87 (1.0%) | −0.189 | [−0.31, −0.06] | −0.224 | −0.087 | −0.08% | −1.00 | 23.5% |
| C1 | k5 | 77 | 3 (3.9%) | 1 (1.3%) | −0.213 | [−0.61, +0.25] | −0.661 | −0.104 | −0.15% | −1.00 | 23.4% |
| C1 | k10 | 65 | 2 (3.1%) | 1 (1.5%) | −0.071 | [−0.53, +0.53] | −0.547 | −0.011 | −0.01% | −1.00 | 29.2% |
| C1 | full | 51 | 1 (2.0%) | 1 (2.0%) | −0.225 | [−0.72, +0.55] | −0.691 | −0.115 | −0.13% | −1.00 | 23.5% |
| C1 | **tl** | 79 | 3 (3.8%) | 1 (1.3%) | −0.051 | [−0.44, +0.49] | −0.517 | +0.027 | +0.05% | −1.00 | 27.8% |

Chain key, C1: k5 n = 66 / −0.168 · k10 65 / −0.071 · full 51 / −0.225 · tl 69 / +0.074 (≥ 5R: 3 / 2 / 1 / 3 trades).

**Applied:** (a) on C0 the bootstrap half-width is ±0.11R and the tail-share standard error ≈ 0.2 pp: `k5`, `k10`
and `tl` are within noise of each other (−0.19 to −0.21; 3.2–3.6%) — one plateau; `full` (the whole base's high) is
the worst corner on every column (2.6% tail, −0.230, −0.123 ADR; it breaks out latest and least often) and is off it.
(b) In C1 nothing separates: the ≥ 5R trades are the SAME five (ticker, E) events across all four K (AFRM 2023-11-27,
APP 2023-06-27, IQ 2023-01-26, IAS 2023-05-22, DYN 2024-01-26 — 1 to 3 of them per K), and every CI straddles zero;
no plateau level ranks last on both columns. (c) The go/no-go decides: at ORH5 the holdout C1 fills are **21 / 19 /
19 / 31** (k5 / k10 / full / tl) — **only `tl` reaches 30**. It is also his own entry: *"a flag with a down sloping
trend line and a breakout of that trend line … may dictate a lower entry than what we call a breakout"* (his note
2026-10-17, `operator_shared_notes.md`). **Primary K = `tl`.** `k5` and `k10` (the horizontal plateau) are reported
beside under the same bar (§6); their holdout reads are CAN'T TELL on n by construction (21 / 19 fills).

**Candour:** `tl` is also the best level in the discovery C1 table. That is not the reason it is chosen — the C1
differences are noise (the same five winners, CIs ±0.5R) — but the reader should know the best-looking level and the
chosen level coincide, and §6 reports the horizontal levels so a `tl`-only pass is visible as such.

### 2.2 The phase slope S (primary = 1, the plan's default)

**Rule:** keep the plan's primary (S = 1: SMA10 > SMA20 and both above their value one session earlier) unless S = 5
is better on BOTH tail share and ADR P&L on every plateau level.

| K | cell | n | ≥ 5R | mean R | 95% CI | without top 5 | ADR P&L | trades S=5 admits that S=1 does not (n, mean R) |
|---|---|---|---|---|---|---|---|---|
| tl | C1 (S=1) | 79 | 3 (3.8%) | −0.051 | [−0.44, +0.49] | −0.517 | +0.027 | — |
| tl | C1_s5 (S=5) | 88 | 3 (3.4%) | −0.107 | [−0.49, +0.37] | −0.526 | +0.004 | 17, −0.788 |
| tl | C3 (no phase) | 144 | 5 (3.5%) | −0.222 | [−0.51, +0.10] | −0.520 | −0.082 | — |
| k5 | C1 (S=1) | 77 | 3 (3.9%) | −0.213 | [−0.61, +0.25] | −0.661 | −0.104 | — |
| k5 | C1_s5 (S=5) | 85 | 4 (4.7%) | −0.058 | [−0.42, +0.39] | −0.489 | −0.030 | 15, +0.293 |
| k5 | C3 (no phase) | 136 | 6 (4.4%) | −0.006 | [−0.36, +0.45] | −0.358 | −0.021 | — |
| k10 | C1 (S=1) | 65 | 2 (3.1%) | −0.071 | [−0.53, +0.53] | −0.547 | −0.011 | — |
| k10 | C1_s5 (S=5) | 74 | 2 (2.7%) | −0.148 | [−0.56, +0.40] | −0.568 | −0.078 | 11, −0.757 |

**Applied:** S = 5 is worse on `tl` and `k10` and better on `k5`; no consistent direction, so S = 1 stays. The phase
rule itself does not separate in discovery: C3 (no phase) splits into phase-on 79 / −0.051 and phase-off 65 / −0.431 on
`tl` but phase-on 77 / −0.213 vs phase-off 59 / +0.263 on `k5`. On C0 (n ≈ 4–5k each side) phase-on is slightly WORSE
on every level (`tl`: −0.207 vs −0.173). The forwarded QQQ 10/20 rule is kept as the article-plus-his-addition cell
C1 because that is what was asked; C3 is the "article alone" read and is reported with the same bar.

### 2.3 The entry (primary = ORH5, as planned)

| cell | K | entry | n | ≥ 5R | mean R | 95% CI | without top 5 | ADR P&L | acct% |
|---|---|---|---|---|---|---|---|---|---|
| C1 | tl | ORH1 | 87 | 4 (4.6%) | −0.008 | [−0.59, +0.75] | −0.706 | +0.025 | +0.05% |
| C1 | tl | **ORH5** | 79 | 3 (3.8%) | −0.051 | [−0.44, +0.49] | −0.517 | +0.027 | +0.05% |
| C1 | tl | ORH60 | 61 | 0 (0.0%) | −0.232 | [−0.57, +0.23] | −0.572 | −0.133 | −0.08% |
| C1 | tl | PIVOT | 94 | 4 (4.3%) | +2.744 | [−0.67, +11.49] | −0.806 | +0.025 | +0.04% |
| C1 | tl | CLOSE | 44 | 0 (0.0%) | −0.430 | [−0.73, −0.05] | −0.738 | −0.182 | −0.21% |
| C0 | tl | ORH1 | 9,919 | 370 (3.7%) | −0.217 | [−0.35, −0.07] | −0.256 | −0.078 | −0.06% |
| C0 | tl | ORH5 | 8,985 | 322 (3.6%) | −0.189 | [−0.31, −0.06] | −0.224 | −0.087 | −0.08% |
| C0 | tl | ORH60 | 5,757 | 156 (2.7%) | −0.168 | [−0.27, −0.06] | −0.187 | −0.110 | −0.09% |
| C0 | tl | PIVOT | 11,017 | 403 (3.7%) | −0.149 | [−0.44, +0.19] | −0.304 | −0.065 | −0.05% |
| C0 | tl | CLOSE | 4,663 | 138 (3.0%) | −0.284 | [−0.45, −0.12] | −0.319 | −0.134 | −0.11% |

**Applied:** no stated reason to leave ORH5. ORH1 reads the same; ORH60 and CLOSE are worse on every column (a later,
wider entry). **The PIVOT variant's R column is unreadable** — it is the #327 tight-stop class: 49% of its C0 `tl`
fills happen in the 09:30 minute, its stop is that minute's low, the 10th-percentile stop width is 0.03 ADR (ORH5:
0.24), 114 C0 trades read ≥ 20R (max 740R; the C1 maximum is 294R on a 0.026-ADR stop) while its ADR P&L is negative
(−0.065) and its account P&L at the article's sizing is −0.05%. ORH5 has 0.8% of fills under 0.1 ADR and no fill in
the first minute. The pivot variant is reported with its ADR P&L beside its R, never on R alone.

### 2.4 The stop (stays the article's: the low of the day at the fill, no wider than one ADR)

**His rule; not changed here.** What the pre-registered sensitivities show (C0 and C1 by stop-width band, same triple;
the "ALL vs ≥ 0.25" row is the plan's floor-sweep robustness check):

| cell | K | stop width / ADR | n | ≥ 5R | mean R | ADR P&L |
|---|---|---|---|---|---|---|
| C0 | tl | [0.00, 0.25) | 1,005 | 43 (4.3%) | −0.177 | −0.045 |
| C0 | tl | [0.25, 0.50) | 3,811 | 163 (4.3%) | −0.222 | −0.081 |
| C0 | tl | [0.50, 0.75) | 2,768 | 91 (3.3%) | −0.195 | −0.116 |
| C0 | tl | [0.75, 1.00] | 1,401 | 25 (1.8%) | −0.093 | −0.077 |
| C0 | k5 | [0.00, 0.25) | 675 | 25 (3.7%) | −0.413 | −0.072 |
| C0 | k5 | [0.25, 0.50) | 3,573 | 143 (4.0%) | −0.295 | −0.114 |
| C0 | k5 | [0.50, 0.75) | 3,080 | 95 (3.1%) | −0.159 | −0.088 |
| C0 | k5 | [0.75, 1.00] | 1,704 | 38 (2.2%) | −0.062 | −0.046 |
| C1 | tl | [0.00, 0.25) | 23 | 1 (4.3%) | −0.355 | −0.064 |
| C1 | tl | [0.25, 0.50) | 23 | 1 (4.3%) | −0.210 | −0.087 |
| C1 | tl | [0.50, 0.75) | 22 | 1 (4.5%) | +0.519 | +0.352 |
| C1 | tl | [0.75, 1.00] | 11 | 0 (0.0%) | −0.218 | −0.197 |
| C0 | tl | ALL vs ≥ 0.25 | 8,985 vs 7,980 | 3.6% vs 3.5% | −0.189 vs −0.190 | — |
| C1 | tl | ALL vs ≥ 0.25 | 79 vs 56 | 3.8% vs 3.6% | −0.051 vs +0.075 | — |

- **Cap-not-skip** (the 1,255 C0 `tl` and 5 C1 `tl` entries skipped as wider than one ADR, re-run with the stop pulled
  up to one ADR): C0 `tl` 8,985 / −0.189 → 10,239 / −0.177; C1 `tl` 79 / −0.051 → 84 / −0.058. **ATR14 instead of
  ADR20** as the width cap: C0 `tl` 8,878 / −0.191; C1 `tl` 78 / −0.038. **60-session horizon:** identical to 120 on
  every cell (no discovery trade on the primary arm was held past session 57 — the SMA10 trail closes them; 0 of
  29,390 mature ORH5 walks differ between the two horizons).
- **Reading:** a wider stop does NOT change the picture. The tight band loses more often but carries the tail share;
  the wide band loses less but has little tail; in ADR units every band is negative at C0 scale and no variant of the
  width rule flips a sign. The floor-sweep check holds (the ≥ 5R share survives dropping stops under 0.25 ADR). There
  is no stop question for him from this data (§10).

### 2.5 The base key (primary = the SPEC key, the plan's rule; chain key reported beside)

The approved plan's harvest row 1 fixed ONE TRADE PER BASE as (ticker, pole date P, K) before any count existed; the
runner added the CHAIN key (poles ≤ 3 sessions apart = one base) as a drift-robust diagnostic because the module's pole
top can walk 1–3 sessions inside one consolidation and re-key the same base. **The spec key is the registered rule
and stays decisive;** switching to the chain key now, with the counts in view, would be the post-hoc choice. Its
consequence is stated: under the chain key C1 `tl` has 27 ORH5 holdout fills, so **no cell reaches n ≥ 30 under the
chain key** — the key choice is load-bearing, and §6 reports the chain-key verdict beside the spec-key one. The four
spec-only `tl` trades are re-entries into a base whose pole top drifted after an earlier break (the k5 analogues:
NUTX, SATS, IREN, NEXA, INTC, APPN, DINO).

### 2.6 The cells (unchanged from the build) and the exit arms

The cell table stays exactly as built (§3): no term was added or dropped on the discovery read. Two observations are
recorded for the forward read, neither acted on: (1) the trigger-bar tightness and inside-day telemetry were not
promoted into any cell; (2) the HTF report cell (flag_detector's own ≥ 90% pole / ≤ 25% pullback geometry inside C0)
reads WORSE than C0 under this entry and exit in 2022-24 (`tl` 438 / −0.262 / 3.2% ≥ 5R; `k5` 418 / −0.250) — the
#397 HTF paper read re-opens on a grid with a positive tail, and this grid does not show one.

Exit arms, C1 `tl`, ORH5 (n = 79 mature on every arm but `stop_only` 78 and the Apollo control 74): the eight grid
arms read −0.083 (p50_s3_t10) to +0.147 (p33_s5_t20), six of eight positive, every CI straddling zero; the primary
`p33_s3_t10` −0.051; the no-breakeven control −0.081; `trail10_only` −0.044; `stop_only` −0.068; `fixed_3r_12`
+0.024 (0% ≥ 5R by construction); Family A's settle rule +0.064; Apollo's live ladder on the same fill and stop +0.151
(n 74). On `k5` all eight grid arms are negative (−0.120 to −0.240). The primary arm is the article's literal reading
and stays; the grid is reported (§6).

## 3. The frozen cell table and the primary triple

**Primary triple (every verdict in §5 is on this and nothing else):** level **`tl`** · entry **ORH5** (the first
minute after 09:35 whose high exceeds max(5-minute range high, the line's value on E), filled at that level or at the
minute's open if it gapped through, +0.1% slippage) · stop **the low of the day at the fill, skipped if wider than
ADR20(D)** · exit **`p33_s3_t10`** (sell 1/3 at the close of session E+3, move the stop to the fill, trail the rest to
the first close below SMA10 — the trail arms only after the partial — sold at the next session's open) · horizon 120
sessions · **spec base key**, first break only · MATURE walks only.

| cell | definition (every term evaluated on bars ≤ D; phase and RS at D) | deciding? |
|---|---|---|
| C0 | universe + prior move ≥ 30% + base 10–45 sessions + a level K exists + close ≥ SMA50 + deal-pin gates + pole-artifact gate | yes (baseline) |
| **C1** | C0 + close ≥ 0.98 × SMA20 + SMA50 rising over 10 sessions + higher lows (5-session low > base low) + tightening (last-5 mean range ÷ first-5 ≤ 0.75) + pole retrace ≤ 50% + RS best-of-3 ≥ 98th pct + QQQ 10/20 phase (S = 1) | **yes — the primary cell** |
| C2 | C1 + prior move ≥ 50% + RS ≥ 99 + group RS ≥ 80th pct | yes (CAN'T TELL by n: 3 holdout fills) |
| C3 | C1 without the phase term | yes |
| C4 | C1 without the RS term | yes |
| C5 | C1 with RS ≥ 95 | yes |
| C6 | C1 + group RS ≥ 80th pct | yes (CAN'T TELL by n: 5 holdout fills) |
| C7 | C1 with SPY and QQQ above their SMA50 in place of the QQQ 10/20 rule | yes |
| C1_no_retrace | C1 without the retrace term | report only |
| C1_no_tightening | C1 without the tightening term | report only |
| HTF | the high-tight-flag subset of C0 (pole ≥ 90% in 40 sessions, flag holds ≥ 75% of the pole top) | report only |

The 15 exit arms (`cb.ARMS`): the 2 × 2 × 2 grid (sell 1/3 or 1/2 × after session 3 or 5 × trail SMA10 or SMA20,
breakeven after the partial), `p33_s3_t10_early` (trail live from E+1), `p33_s3_t10_close` (trail filled at the
signal close), `p33_s3_t10_nobe` (no breakeven move), `p33_s3_t10_ifprofit` (partial only on a close above the fill),
`trail10_only`, `stop_only`, `fixed_3r_12`; plus the two controls `ctl_family_a_settle` and `ctl_apollo_today`.

## 4. The decisive metrics (computed by the pinned runner's `report` on `trades_holdout.tsv.gz`, per cell, on the primary triple)

Tail first: **the share of trades at ≥ 5R and at ≥ 10R** (and their counts); **mean R with the month-block bootstrap
95% interval**; **mean R without the top five**; **mean P&L in ADR units**; **account % at the article's sizing**;
then R per month, the by-year split (2025 / 2026), the by-phase split (for the cells without a phase term), the EP-day
split (E opens more than one ADR above the level), the dollar-volume and ADR terciles (cuts frozen on the discovery C0
distribution: dollar volume 23,129,488 / 65,721,253; ADR 3.26% / 4.75%); median and win rate reported beside, never
deciding. n on every number; open marks counted apart.

## 5. The bar — PASS · CAN'T TELL · FAIL, per deciding cell, on the primary triple, holdout only

### 5.1 PASS — all of:
1. **n ≥ 30** mature trades;
2. **the bootstrap interval's lower end > 0** (95% month-block interval of the mean R; equivalently a one-sided test
   at 2.5%);
3. **mean R without the top five > 0**;
4. **mean P&L in ADR units > 0**;
5. **beats C0 on the same triple:** the cell's mean R > C0's mean R AND the cell's ≥ 5R share > C0's ≥ 5R share
   (point estimates; C0 is the baseline cell with ≈ 7,570 fills, so its own interval is tight).

### 5.2 CAN'T TELL — n < 30 mature trades, or none of PASS / FAIL holds.
### 5.3 FAIL — the interval's upper end < 0, OR (n ≥ 30 and the cell does not beat C0 on mean R).

**The discovery clause — not dropped, re-stated with its consequence.** The plan's bar carried a sixth condition,
"the same sign in discovery". On the primary triple the primary cell C1 reads NEGATIVE on every level in discovery
(`tl` −0.051 on 79 trades, without the top five −0.517; `k5` −0.213; `k10` −0.071; `full` −0.225), so as written
C1 could never pass, whatever the holdout shows; C5 `tl` (+0.251 on 143, carried by 26 trades of 2022 at +2.23 — without
the top five −0.412) and C6 `tl` (+0.158 on 15) are the only deciding cells positive in discovery and both through a
top-heavy sample. The clause is therefore made a **REPORTED QUALIFIER**, not a gate: every verdict carries "discovery
on the same triple: agrees / contradicts (n, mean R)". A holdout PASS in a cell whose discovery read was negative is
called **PASS (discovery-contradicted)** and its consequence is fixed now: it is single-block evidence from one regime
(2025-26) that a 2022-24 read of the same rule did not show, and the §0 paper-lane proposal carries that sentence in
its first line. Reasoning: (i) a sign requirement on a C1 discovery read whose interval spans ±0.5R would make the bar
depend on noise; (ii) the discovery grid was used to fix K, S, the entry and the key, so a discovery condition on the
chosen triple is partly circular; (iii) the holdout conditions 2–5 are the confirmatory test and are strict (below).

**What a PASS takes, in plain numbers:** with ≈ 31 trades of which (on discovery's rates) about 70% stop near −1R, the
interval's lower end clears zero only at a mean of roughly +0.7R or more, and the 26 trades below the top five can
average above zero only if the setup is broadly positive — not on one or two winners. Discovery's C1 `tl` read (mean
−0.05, without the top five −0.52) came nowhere near either.

**Chance rate, stated before the data:** C2 and C6 are CAN'T TELL by n (3 and 5 fills). Of the six testable cells, each
passes condition 2 by chance with probability ≈ 2.5% under a true mean of zero (if the block bootstrap is calibrated),
so the chance that at least one does is ≈ 14%; condition 3 makes a chance pass far rarer. A pass outside C1 is a
lead (§0). The verdict is about "the setup as tested" — this encoding, this entry, this stop, this exit — never about
Qullamaggie's pattern.

**Independent re-derivation (DoD part 1):** from `trades_holdout.tsv.gz` alone, without the runner's code, P5 recomputes
C1 `tl` ORH5 `p33_s3_t10` spec-key mature **n, mean R and the ≥ 5R share** and must return VERDICT MATCH before any
number is reported (as #686 did).

## 6. Robustness rows (reported beside every verdict, never deciding)

1. the number of the eight grid exit arms with mean R > 0 (the plan's "≥ 6 of 8");
2. the ≥ 5R share after dropping stops under 0.25 ADR, against the unfiltered share (the plan's "keeps half");
3. the sign of mean R on each other entry (ORH1, ORH60, PIVOT with its ADR P&L beside it, CLOSE);
4. the same verdict under the CHAIN key (27 fills: CAN'T TELL on n is the expected reading);
5. the verdict on the horizontal plateau levels `k5` and `k10` (21 / 19 fills: CAN'T TELL on n is expected; their
   signs are reported);
6. the no-breakeven arm, the 60-session horizon, the cap-not-skip and ATR14 re-runs;
7. the two controls on the same fill and stop (Family A's settle rule; Apollo's live ladder);
8. the by-year split (2025 vs 2026) and, for C3, the by-phase split;
9. the deal check: every holdout C1 trade ≥ 5R is checked for a cash-deal / buyout print (harvest row 3); the five
   discovery names in §2.1 are the precedent.

## 7. Expectations written before the holdout is opened

- **STEP 0 (already pinned):** C1 `tl` ORH5 = 43 candidates, 31 filled, 2 too-wide, 10 no-trigger; 20 of the 31 have
  ≥ 121 forward sessions; C0 `tl` ORH5 = 7,570 filled. The holdout run's own entry tally must reproduce these counts.
- **Expected mature n in C1:** 28–31. n < 30 happens if two or more of the 11 young trades (E after 2026-04-24) are
  still open on 2026-10-16; that reads CAN'T TELL and is a sample-size result, not a null. The 60-session read on the
  same trades (26 of 31 have ≥ 61 forward sessions) is reported beside, never deciding.
- **The baseline:** discovery C0 ran mean R ≈ −0.2, ≥ 5R ≈ 3.5%, win ≈ 25%, median −1R on every level. If holdout C0
  comes in far above that, the first sentence of the result is the regime, and C1 must beat C0 (condition 5) to pass.
- **Alarms — HARD, before any outcome is read:** `freeze_check` fails; the data gate exceeds 5% (pinned 0.43%); the
  entry tally differs from the pinned composition file; `--out` is not `DATA/out`; a `.partial` holdout file exists.
  Any alarm → investigate, fix the DATA or the invocation, re-run `step0-entries` (no outcome); the registration does
  not change.

## 8. What the read may NOT do

- Change K, S, the entry, the stop rule, the exit arm, the base key, a cell term, the horizon, the 30-trade bar, the
  bootstrap seed or draw count, or the tercile cuts — after this freeze, for any reason.
- Pick among the four levels, five entries, 15 arms or two keys AFTER seeing holdout outcomes: the primary triple
  decides; everything else is a reported row.
- Drop, re-label or re-date a row after an outcome is visible; censored and degraded rows are counted, never filled.
- Run the holdout twice (the runner refuses on an existing `trades_holdout.tsv.gz` or `.partial`); a re-run is allowed
  only on identical inputs to reproduce the files byte for byte.
- Read a robustness row, a report cell (C1_no_retrace, C1_no_tightening, HTF) or a non-C1 pass as a finding.
- Edit this document above the freeze marker, the module, the runner, `constants.py`, `anticipation.py`,
  `live_fill_counterfactuals.py`, `rule_eras.py` or `broker/exit_logic.py` before P5 has run: every one is pinned
  and the holdout refuses on a changed byte.

## 9. What this does not answer

- **The pattern vs our encoding.** A FAIL says this detector + this entry + this stop + this exit lost in 2025-26; it
  says nothing about Qullamaggie's breakout traded by him, and the entry / exit of a new setup are undetermined
  (`docs/methodology/analysis_standard.md`, the new-setup clause): the grid is reported so the next design round can
  vary them, and choosing a different stop or target is his, under CHANGE_PROCESS.
- **One regime.** The holdout is 2025-01..2026-10, largely a bull tape; discovery's C1 was +0.31 to +0.39R in 2023
  and −0.35 to −0.79R in 2024 on 20–34 trades a year (across the four levels), so a single-block sign is weak evidence either way.
- **Power.** ≈ 31 trades confirm only a large, broad effect (§5); most cells will read CAN'T TELL honestly.
- **Re-entries.** One trade per base (first break); his practice of re-buying a base after a shakeout is not scored.
  The frozen report drops retriggers and the `first_C1` population (a base's first break on which C1 held: 77 holdout
  candidates) is not read by it — both are recorded in the pinned tables for a later, separately registered read.
- **Capacity.** No position cap, no overlap rule and no slot competition with EP are modelled; `overlap_open` is
  recorded for discovery only.
- **Execution realism.** SIP minutes, 0.1% slippage, a fill at the level or the minute's open, no partial fills, no
  halts inside the day; the breakeven stop and the trail are modelled, not placed.
- **Sizing.** acct% uses the article's formula only; the live risk multiplier and the 20% cap are not this setup's.
- **Group RS.** SIC is one row per ticker as of 2026-10-16 and 19% of watch rows have no group; C2 and C6 are too thin
  to read.
- **The trendline's own parameters** (anchor, slope rule, touch tolerance) are B-class and were not varied.
- **Why 2023 worked and 2024 did not** in discovery — not measured.

## 10. Decisions for the operator

| fork | the choice | rec |
|---|---|---|
| **The primary breakout level.** This freeze reads the setup on the trendline (`tl`, his 10-17 note); the horizontal base-high levels `k5` / `k10` are reported beside and have 21 / 19 holdout fills — a CAN'T TELL on n whichever way. | `tl` as frozen, or the base high (`k5`) instead | **`tl`** — it is his described entry, it sits on the discovery plateau, and it is the only level that reaches the 30-trade bar. Say so before P5 if you want `k5`; after P5 it cannot change. |
| **Stop width — answered, no fork.** The article's low-of-day stop stays primary. The band table in §2.4 shows a wider stop loses less often but has no tail, a tighter one has the tail but loses more, and in ADR units every band is negative at scale; capping instead of skipping too-wide stops and ATR14 in place of ADR20 move nothing. | — | no change; nothing to rule on from this data |

A PASS (§0) returns to him as a paper-lane proposal whose build touches the order path — each piece with its own
sign-off. Nothing in this document is flipped, proposed as decided, or pre-approves money.

## 11. What the result paragraph may say (the template — not a result)

One paragraph per deciding cell, C1 first, in plain words, every number with its n:
- **CAN'T TELL:** "C1 on the trendline: n = [x] mature of 31 filled — under the 30-trade bar [or: interval
  [lo, hi] spans zero]; the tail read [k] of [n] at ≥ 5R; discovery on the same triple read [sign, n]. No paper now;
  the shadow accrues; the forward read decides."
- **FAIL:** "C1 on the trendline lost in 2025-26 under this entry and exit: mean R [x] on [n], interval [lo, hi],
  [k] at ≥ 5R, ADR P&L [y]; C0 read [..]. This is the setup as tested, not the pattern; the grid [arms / entries with
  a positive sign, if any] is the next design round's input. No paper."
- **PASS (discovery-contradicted):** "C1 on the trendline passed the frozen bar on the holdout: mean R [x] on [n],
  interval [lo, hi] above zero, without the top five [z], ADR P&L [y], against C0 [..]. Discovery read the same rule
  at −0.05R on 79 trades, so this is single-block evidence from one regime. A paper lane is proposed [build list];
  each piece of its order path needs your sign-off; its forward read decides whether it stays."

## THE LINE

Registration only. No strategy, entry or exit rule, stop, size, safeguard or live trade state was changed or is
proposed as decided. The stop is the article's and stays his; a paper lane is proposed only on a PASS and its build is
signed piece by piece; live is his. No prod query, no ssh, no LLM call, no paid API, no deploy and no PLAN.md edit was
made in writing this; the one code edit is the module's docstring (its registry sentence was stale), proven
output-neutral by re-running the four backtest stages and matching all seven content hashes before the pins below
were taken.

<!-- FREEZE -->
## Freeze record

`runner.py holdout` verifies every pin below before it opens the holdout and refuses on any mismatch (`freeze_check`).
The "doc body" pin covers every byte of this file ABOVE the `<!-- FREEZE -->` marker (a file cannot hold its own hash).
`minutes (tree)` is one sha256 over the sorted `path<TAB>sha256` lines of every `<date>.psv.gz` and `_done.psv`. The
`code/*` pins are the five repo modules the outcome path computes with, derived by
`tests/test_cb_backtest_runner.py::TestHoldoutGuard` walking the call graph (`db.py` is the one reached module left
unpinned, with its reason in `FROZEN_CODE_EXEMPT`). The data and discovery files live outside the repo at
`/Users/alvinfung/apollo_data/cb702/`; the pins fix their exact bytes. Printed by `holdout --print-pins` on
2026-10-18 after the docstring edit:

- module sha256: `e4adebdd0d58adaa76ea7c47fc79b713b47050d6cc3e553a956a89c7a4757f7b`
- runner sha256: `c967db54f78557effef0beae8bc6385e000672d17e256f76f4384e02041bdeeb`
- cell table sha256: `59e757cacb3250066393d0395e4abe89adff3787c34d1f2f7ad5fd5e2f2a5c0b`
- code/constants.py sha256: `72dadd72503a842f593621b0868f908ab99e1d77851330c2842be7797aa99400`
- code/anticipation.py sha256: `de50113aad405e16faf2281ab6aeb1640686d1d18cbe912b78b97250efb0a242`
- code/live_fill_counterfactuals.py sha256: `6bdb44b98acf3a2146b1ae9e7245a5405f001a3fd21e06d5612ac2e61d6ef052`
- code/rule_eras.py sha256: `1975dc27d22cf93562be111ca553dd87e36580bbc6833633d75109571352a1d5`
- code/exit_logic.py sha256: `dd032c0f5115c2d811561d455ad260e8b77559415bde68ae46f4a17eb92b7976`
- data/cb702_sic.psv sha256: `0e476c4422d56648d615c48d941edb971a348dfb99821023116d0fd98e617346`
- data/cb702_splits.psv sha256: `3199d06d5fb7dcd52ebd34e8c71e148b45ec0ca4a15f7f03ea1b715718882b0b`
- data/cb702_vix.psv sha256: `9116dd1522f992ed226609b487b369540046e2dec884bb65dfd4144e459ab4f1`
- data/daily_closes_all.csv.gz sha256: `ccc0097fe535cb8de9b83d6d534744b6cbadc114d9d29ecac677ac18a52900ba`
- data/liquid_tickers.txt sha256: `a2c6c27da6555c16b3314808c73150e785c51f7743ec03f2a4d17dc98f47e3f8`
- data/small_pulls.psv sha256: `b8d37aae5ef85c25bc52479eef7f6b04a8a4e67557caaef7a426d8ae20194643`
- minutes (tree) sha256: `ab3c1c73fc47b2fabc4cc66cc4b6eb176ff6aac11a81d1bb71fbc17b93b52723`
- candidates.tsv sha256: `b75c828671171530225198f97fc1191c9bced8f9448b9b05aa46099d617ce0c7`
- minute_fetch_list.tsv sha256: `981e7c3c794552d19f4afca456c9e581a1a6d9d0c6c8b9f2850e8e881f177e91`
- gap_in_bars.tsv sha256: `be01de1ea719c9d7754ef9c903bb1bd312c0c8f149517b4d3ecd1f0e2869bb3e`
- close_variant_discovery.tsv.gz sha256: `e6ec42d601be142230688ea54659515280f8e45a49ea09cf4beabd3accea563f`
- trades_discovery.tsv.gz sha256: `9e87c60fc3d819a0af46ac2c420fd7687be1d2e3ff65d651a3e5a5e5f3e4cf45`
- entries_discovery.tsv.gz sha256: `38e343867564a9baace31c049db33799306d9605fd8c55244c3408701046a9c7`
- entries_holdout_composition.tsv sha256: `e5dbd781922a310aa62a096b7cf46a265ed6710d66d70781a9204c017ceacf9c`
- discovery_report.tsv sha256: `d555303e61d70a248fefc9cb0bf0f40ac1205b1ec8a240b880c6f90b01700124`
- discovery_report.txt sha256: `fa39e486f2b0f7b6e4a987b4c1554378e6dd5c37a0b9d72fd13e66d11dfa85f7`

- doc body sha256: `d798af44bc070dcb18bee31632a6b5b1be4e66516fd74a1a1e092148ead09d44` — this file above the `<!-- FREEZE -->` marker
- freeze commit: the commit that adds this file on `main` (`git log -- docs/analysis/cb_preregistration_2026-10-18.md`);
  the holdout (P5) runs only after it is on `main`.
