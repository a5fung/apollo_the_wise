# Session HANDOFF — cross-machine bootstrap

**Written 2026-07-07 (desktop). The operator is moving to a LAPTOP for ~1 week and will start
fresh Claude Code sessions there.** This file is IN THE REPO (git-synced), so a laptop session
gets it on `git pull`. It exists because the machine-local context does NOT transfer (see §1).

---

## 1. THE transition fact — what does and does NOT cross machines

| Surface | Location | Crosses to laptop? |
|---|---|---|
| **CLAUDE.md** (rules, protocol, THE LINE, schedules, architecture) | repo root | ✅ via `git pull` |
| **PLAN.md** (every task: project · ETA · status · detail — the SoT) | repo root | ✅ via `git pull` |
| **docs/decisions/** (ADRs 0011–0024, all signed) · **docs/roadmap/** | repo | ✅ via `git pull` |
| **This file (docs/HANDOFF.md)** — the in-flight "where we are" | repo | ✅ via `git pull` |
| **The pickup + MEMORY.md + ~40 feedback/project memories** | `~/.claude/projects/.../memory/` | ❌ **machine-local — NOT on the laptop** |

**So on the laptop, the load-bearing rules (CLAUDE.md) and all tasks (PLAN.md) and all design
(ADRs) ARE present. What's missing is the accumulated memory files.** §4 backstops the most
load-bearing of those; the rest is nuance the signed ADRs + PLAN.md task detail already carry.

## 2. Laptop OPEN ritual (do this first, every session)
1. `git pull origin main`
2. `python scripts/operator_now.py` (you're **PDT**; harness clock is UTC — never trust it for dates)
3. `python scripts/check_plan.py --today` → the day's plan (this reads PLAN.md, the SoT — works fine on the laptop)
4. **Read THIS file (§3) for in-flight context** (it replaces the machine-local pickup you won't have)
5. State the day's plan before reacting.

CLOSE ritual is unchanged (reconcile PLAN.md → `check_plan.py` must pass → commit+push). Your
laptop sessions build their OWN local memory as you go; PLAN.md (synced) stays the source of truth,
so when the operator returns to the desktop, `check_plan --today` off PLAN.md gives the true state
(the desktop's week-old pickup self-heals via PLAN.md).

## 3. WHERE WE ARE (as of 2026-08-07 PT — the silent-failure week)

**Board 83.** Everything pushed to `main`, clean tree, suite **4628** green, deployed + verified in
ALL THREE containers (market-agent · orchestrator · execution). Authoritative in-flight state is
always **PLAN.md** (`python scripts/check_plan.py --today`) + the desktop pickup memory; this
section is the laptop's backstop.

**THE WEEK IN ONE LINE:** a model tier bump (sonnet-4-6 → sonnet-5) broke EP grading silently for
two days, the operator found it by noticing there were no alerts during earnings season, and the
whole class got closed on 08-07 evening. **Money impact of the entire cluster: $0, measured** — the
three corrupted grades all ended $0 (two skipped out-of-ORB, one order never filled), and Friday's
three real losses were graded HIGH by the baseline rule before the judge ran.

**WHAT SHIPPED 08-07 (all deployed, NONE yet exercised by a real run):**
- `api_usage.stop_reason` on every LLM call, both containers → truncation is now SELF-REPORTING
  instead of inferred. A 17:52 ET check Telegrams any truncating caller AND any caller whose
  stop_reason is always NULL (a missed call site announces itself).
- Ceilings raised: `theme_synthesis` + `theme_discovery` 4000→8000, `ep_grade_judge` 500→1500,
  `ep_catalyst_grade` 300→1500. Cost of all of it: **+$0.11/day**.
- A truncated judge verdict is now DISCARDED, not half-read into a grade (ADR 0011 addendum).
- `shared/llm_response.py` — ONE canonical response reader; all 10 positional `content[0]` sites
  routed through it, with a test that blocks any new one.
- Cost: Perplexity same-run dedupe (it is 22.7% of the bill, the largest line, bigger than any
  Claude caller) + sonnet-5 was priced 50% too high (8% of the bill was accounting error, not spend).

**⚠ MONDAY 2026-08-10 = a SIX-ITEM VERIFY on #544.** Nothing above has run for real. The two that
matter most: (a) `theme_synthesis` at-cap % must FALL from 60% at the new ceiling — **if it does
NOT, the cap was never the constraint** and the fix is bounding the cohort count, not raising
again; (b) the 17:52 truncation check's FIRST real firing. Full list on the #544 PLAN line.
⚠ When it flags a caller with a tiny ceiling, do NOT just add it to `_TRUNC_BY_DESIGN` — confirm
that ceiling is intentional first. Every cap raised Friday was one someone thought was fine.

**BLOCKED ON THE OPERATOR — one fork, and it is the only thing stopping a whole lane:** **#494**
(market strength map) is now `blocked` [b3]. NOT waiting on work — design doc, inventory and gaps
are done. Waiting on ONE ruling: how to mix asset-level strength (gold, BTC, oil) with its equity
expression (miners, MSTR/COIN, E&Ps), which move together. SEPARATE layers / UNIFIED frame /
**HYBRID complex (leading candidate)**. #493 and #492-B cannot be sequenced until he calls it.
**SCHEDULED SAT 2026-08-08** (his call) — pulled in from 08-14. Data availability pre-answered:
all 20 asset-class ETF proxies (GLD/SLV/GDX/USO/XLE/CPER/URA/TLT/UUP…) already carry 279 bars in
`mi_daily_closes`, so the hybrid complex is buildable with NO new data source.

**STILL OPEN on #543 (ETA 08-11):** failed extractions are still CACHED as results (the bug that
made Friday's first fix inert) · the cost watchdog still mislabels a price-per-call rise as a retry
loop · the deferred deep fix — make a forgotten `stop_reason` IMPOSSIBLE rather than detected
(22 call sites, both containers; not done at midnight on live telemetry).

**COST BASELINE to measure against —** 7 days to 08-07, **$22.30**: perplexity_news_search $5.08
(22.7%) · judge_robustness_eval $3.66 (an EVAL, not production — next lever, unexamined) ·
catalyst_metrics_extractor $2.83 · ep_catalyst_grade $2.67 · ep_grade_judge $1.87 · theme_discovery
$1.85. **Friday's 114 Perplexity searches is the before-number** for the dedupe.

**LIVE-MONEY NOTES:** ask-aware entry went live 08-07 (#541, operator-signed). Friday's 3 losses
(TEAM −$23.94 · NET −$15.39 · FIGS −$6.84) were all BULL-tape entries — `exit_tune_bull_regime_read`
is now **3 of 8, not 0**; the "zero bull trades" claim was corrected 08-07 and must not be repeated.

*(v1.0 was DECLARED 2026-07-24 — operator signed §8 of `docs/roadmap/v1-closeout-productization.md`,
all 8 FL gates green, #418/#425 closed; the board is the #419 Phase-2 program. The 7/23-24 deploy
notes below are superseded but kept for continuity.)*


### (historical) CLOSE 2026-07-13 evening PDT — the M1-d reframe + coverage-loop day

**Today (a marathon, 25 commits, all pushed):** M1-d composite-authority wire-in built DARK + Opus-verified
vs the diff + deployed (T2c drift-band now ACCRUING — first samples 16:15 ET 7/13) · M1-b regrade ran ($5) ·
the EP↔theme coverage-loop investigation → **S1-S3 shadow instrumentation built + deployed DARK (#467)** ·
/simplify pass on it (silent-failure `_error` rename + SQL dedup + reuse; 1 false-positive reverted) · all
4 overdue data-gated reviews ran + dispositioned + deployed · 2 API-failure alerts triaged (both non-issues —
Perplexity self-recovered, FMP 402 was my own probe). Board **112** (≤113 baseline, 0 overdue).

**⚠ THE M1-d REFRAME (most important for the 7/18 sitting):** the theme boost is RARE on MODERATE
(~few/quarter), UN-EVIDENCEABLE from history (MODERATE was never instrumented until S1 today), and largely
REDUNDANT (hot-theme EP names already grade HIGH, ~16:1). So **7/18 M1-d = a KEEP/SHELVE call, NOT a
mechanical flip** — wire-in stays dark; the coverage-loop (#467) is the bigger theme-axis lever. Evidence:
docs/analysis/{m1b_regrade,m1_htf_readiness,ep_theme_coverage_loop_design,theme_membership_investigation}_2026-07-13.md.

**Coverage-loop verify-lives (#1 forward item, #467 in_progress):** deployed DARK; coverage_probe job
registered + ran clean 17:55 ET (0 rows — today was a 0-alert market). On the NEXT ACTIVE MARKET DAY verify
(a) coverage_probe writes mi_coverage_probe rows, (b) S1 writes MODERATE rows to mi_theme_axis_shadow → then
#467 completes. Safety: source='coverage_probe' is carved OUT of auto-promote (2 walls, pinned).

**Review dispositions (data_gated_reviews.yaml, deployed):**
- #1 conviction_floor: NO-GO (16% label < 35% bar) → operator confirm close.
- #2 stop_too_wide: CORRECTED read via canonical mi_ep_missed_outcomes → ~break-even, N=5<10, leans keep-as-is;
  7 rejections unpopulated (missed-outcomes lag — WATCH). Re-date 8/8; realized-R decision = operator's.
- #3 yoy-missing (7/27): 149→94 real cohort; recoverability PROVEN (yfinance has it). NEXT = build+test a
  yfinance q-rev+prior-year fallback in the catalyst extractor — a GRADE-INPUT change → operator-aware + backtest.
- #4 catalyst_discovery: gate MET → big-rock C2/C3 build (ADR 0006), own session, 8/15.

**Open threads (all in PLAN.md):**
1. Coverage-loop verify-lives — next active market day (#467).
2. M1-d keep/shelve at the 7/18 sitting (reframed above); #335 note updated.
3. #3 yfinance fallback (7/27, grade-input → operator-aware + backtest).
4. WATCH: mi_ep_missed_outcomes population lag (#2); FMP per-symbol 402 (CHTR/SMPL — minor, feeds #3).
   NOTE: probing prod API helpers (`_fmp_get`) fires operator alerts — use raw calls or flag first.

## 4. Critical operating rules the laptop won't have in memory (backstop — most are also in CLAUDE.md)

- **THE LINE** (CLAUDE.md, absolute): NEVER on your own authority change/disable any strategy, sell/entry
  discipline, sizing, target, safeguard, or anything touching real money / live trade state. In doubt: STOP + ask.
- **Deploys need EXPLICIT operator authorization each time.** Not standing.
- **`deploy.sh both` does NOT recreate `apollo-execution`** — broker/ (order_manager, trade_stream,
  live_tracker, alpaca_client) needs a SECOND `deploy.sh execution`. Verify `docker ps` shows
  apollo-execution "Up <seconds>" after. (The scope guard warns, but confirm.)
- **No `docker exec python -c` for trade-state MUTATION.** Read-only SELECTs are fine. Mutations go through
  a COMMITTED, reviewed, DRY-RUN-first script (see scripts/reap_stale_pending_confirmation.py and
  scripts/fix_double_encoded_exits_287.py as the pattern) — never inline.
- **Max 1 rebump; UNBLOCK+SHIP, not re-date** (CLAUDE.md). A due task → work it, don't roll the date.
- **Never invent a `/command`** — grep `channels/telegram.py` first; a command needs handler + dispatch +
  BotCommand registration in the same commit or it's invisible.
- **Established setups (EP/9M/HTF) → use the PRIMARY methodology definition**; don't invent variants.
- **Timezones**: operator = PDT · harness "today" = UTC (never use for operator dates) · market code = ET.
- **Concise** — no essays; a decision = the fork + a 1-line rec. Never mention session length / ending.
- **`advisor` is Opus-only** — works on Opus 4.8 (the default), fails on Fable-5 as main model.
- **Model split** (operator): Fable = design/review to execution depth · Sonnet = card execution · Opus =
  main-loop verify/deploy/review. Fable window = this weekend (Block 3 DONE Sat; Sun 7/13 = the
  Lane-1 sitting #459 + Block 4 #462); after Sunday Fable is unavailable for a while — the Block-4
  card builds + everything else run Opus/Sonnet.
- **jsonb double-encode class**: the pool codec auto-`json.dumps` every jsonb param — NEVER pre-`json.dumps`
  a jsonb value (double-encodes to a string). Pass the plain object; keep the `::jsonb` cast. (#177/#287/#412.)

---
*Keep this file's §3 roughly current if you do a long stint on the laptop; but PLAN.md is always the
authoritative task state. When the operator is back on the desktop, the machine-local memory resumes.*

---

## 2026-08-16 (PT) — RESUME POINT: the EP weekend, and what is open

**Board 79 · tree clean · everything pushed · no CLOSE run.** Full detail:
`docs/roadmap/ep_profitability_program.md` (2026-08-15/16 sections) and
`docs/methodology/structure_model.md`.

### Immediate next step — a broken filter, fix before quoting numbers
The market-wide "winners we never alerted on" scan is **contaminated by leveraged ETFs** (SOXL,
YINN, KORU, MULL, MVLL, QCML, MUU, RVI, VCX). The attempted fix — requiring a non-null `sector` +
`market_cap` in `mi_stock_scores` — **does not work** (sector is stored only for the top ~300 by
rank, so it matched nothing). Find a real discriminator and re-run; until then the "141 of 149
addressable miss" is an ETF-contaminated upper bound.

### Two operator forks, both with volatility-normalised evidence
1. **The extension filter** — the cohort it cuts is worse at the median (1.74× vs 2.32× MFE/ADR) and
   better in the tail (10.1% vs 3.7% reach ≥12×ADR).
2. **The intraday stop** — over 60 days on the traded cohort: live −6.0R · no intraday stop +36.8R
   (unbounded intraday risk) · re-entry ×2 +7.5R (worst case −2R). Holding longer alone does nothing.
3. Added 08-16 — **re-check the gap floor later in the morning** (78% of tradeable missed winners
   that opened <10% crossed 10% intraday — a ceiling, not a yield) and the **liquidity/volatility
   gates** (our alerts 5.5% ADR / ~$200M; the missed winners 9.9% / $106M).

### The three findings that govern all future analysis here
- **Our score separates nothing** — 66.8 vs 65.9 on n=3,292; `game_changer` is *less* common among
  winners.
- **Raw-percentage outcomes are volatility in disguise** — price, gap and the structure verdict all
  lose their effect or reverse once divided by ADR. Re-read anything measured in raw %.
- **Extension is the one signal that survives normalising** — and our structure verdict runs
  backwards to it.

### Monday verify-live
`profit_take_oco` is OFF (operator flips). Then the first live +2R carve-out as an OCO · the 16:22 ET
alert-day path job · the first `db_growth_check` row · EROC appearing in `mi_ep_missed_outcomes` ·
consolidation entry days now getting minute bars.

⚠ Subagent cap hit (200/200) — set `CLAUDE_CODE_MAX_SUBAGENTS_PER_SESSION` before the next launch.

---

## 2026-08-16 (PT) — 🔴 RESUME HERE: an operator-SIGNED money change is half-built in the tree

**Board 79 · everything else committed and deployed · two agents were still running when the session
ended, and their work is UNCOMMITTED IN THE WORKING TREE.**

### 🛑 FIRST THING ON RESUME — verify before you commit or deploy anything

**The operator SIGNED OFF (2026-08-16, "ok let's go for it") on a live stop + sizing change:**

1. Protective stop moves from the ORB low to **`entry − 2R`** where `R = entry − ORB_low`
   (i.e. `2 × ORB_low − entry`). The ORB low still DEFINES R; it is no longer the exit.
2. **Position size halves** so dollar risk is unchanged — ⚠ **check whether the sizing formula
   already does this automatically** (shares = risk_budget ÷ stop distance). Halving twice would
   QUARTER the position.
3. 🔴 **THE PROFIT TARGET MUST NOT MOVE** — 1/3 still comes off at the ORIGINAL `entry + 2 × (entry −
   ORB_low)` price. If `scan_profit_triggers` reads the NEW stop distance the target silently drifts
   to +4R, which was never tested. **This is the primary correctness risk of the whole change.**
4. Breakeven-after-partial and the SMA trail are UNCHANGED.

**Evidence (do not re-derive):** matched 43 reconstructed HIGH trades at EQUAL dollar risk — live
ORB-low stop **SUM −6.0, median −1.00**; 2R stop at half size **SUM +11.4, median +0.33**. 3R gave
+12.2 sum but a lower median and max, so 2R was chosen. Limits: one regime (April–May), reconstructed
not lived, slippage unmodelled, no out-of-sample until the shadow accrues.

▶ **It needs: SSoT updates in `magna53_ep.md` + `exit_discipline.md`, a CHANGE_PROCESS log entry with
the reversion flag, mutation-proven tests, the full suite, and BOTH deploy scopes.** Verify all of it
yourself — this is real money.

### Also uncommitted: the alert-rank shadow

A second recorder (`mi_alert_rank_shadow`) was being built to log the selection ranking beside every
alert — BOTH the EOD version (as tested) and an as-of-09:45 version, because **the tested tightness
feature uses the full day's range and is NOT knowable at 09:45.** Plus intraday variants:
ORB-range÷ATR (the live `stop_too_wide` ratio, recorded even for rejects), ORB-range÷ADR,
close-position-in-range, and bar contraction.

### Shipped and deployed today
- **`mi_exit_path_shadow`** — records every live position's daily path so any exit rule scores
  offline later. Review gated at **20 closed positions (~early October)**, filed in
  `data_gated_reviews.yaml` as `exit_path_shadow_first_read`.
- **Detector-liveness alarm** (#543) — 2 tables confirmed dark (anticipation lifecycle 61d,
  undercut-rally 59d).
- Consolidation entry days joined the minute-path capture.

### The findings that matter (full account: `ep_profitability_program.md` §0b synthesis)
- **Ranking rule, 2.5× lift:** rank by smaller gap + tighter EP day + less extension → top quartile
  holds **16 of the 26** tradeable ≥10R winners. ⚠ No out-of-sample exists yet.
- **Intraday:** opening-range TIGHTNESS does not predict; **close-position-in-range does** (top 30%
  of the ORB → 17% reach 8×ADR vs 6.8%).
- **Expectedness axis is buildable** from stored 8-K text, no LLM: unscheduled 11.6% vs scheduled
  3.8% reach 8×ADR. Candidate, not finding.
- **Nulls indict our ENCODING, not the concepts** (his correction) — the catalyst explains the gap,
  so its explanatory content is already priced in.

---

## 2026-08-29 (Sat) — 🔴 RESUME HERE. Everything below this line supersedes the older sections.

**State: clean.** Tree clean, all pushed (`0af5142d`), plan gate green at **82 open**, suite
**6550 passed / 7 skipped**. Nothing half-built, nothing awaiting deploy.

### The one number that matters

**EP is roughly break-even, and we find the outliers but do not hold them.**
`docs/analysis/ep_backtest_run1_2026-08-29.md` — the first backtest built under TODAY's rules
from raw bars rather than replayed off stale trade rows. n=194: mean **+0.14R**, median
**+0.33R**, win 55%. **Of 106 trades that hit the +2R partial, 82 gave the runner all the way
back to breakeven** and finished at exactly +0.33R; 24 ran further (median +1.98R).

⚠ The operator corrected the framing and was right: EP *is* an outlier strategy, so
outlier-dependence is not a weakness. The finding is that we do not HOLD them — an exit
question, not a selection one.

`docs/analysis/runner_rule_sweep_2026-08-29.md`: every looser runner rule earns more on the mean
(hold-20 +0.36R vs control +0.14R) **but the median flips negative and nothing separates at
95%.** Decision: **do not change it, collect and re-review.** Registered as
`runner_rule_sweep_recut` in `data_gated_reviews.yaml`, firing on 40 more closed trades **or any
single safeguard transition** — the second arm is his "review as needed", because a rules change
makes a read stale rather than thin.

### Shipped and deployed 08-29

| # | what |
|---|---|
| **#605** | only 12% of scanned candidates carried a score/catalyst grade, so no gate could be re-asked. **19 new `mi_ep_scan_log` columns (23→42)**, below-floor capture, **bar capture now scan-log-driven at 8%** (below the 9% live floor deliberately), guard test fails if a scoring input ships unlogged. **Monday's first scan populates it — verify.** |
| **#597** | a vanished broker position no longer books a wrong P&L — broker truth, or the row stays open and loud. Never fabricates a fill price. |
| **#595** | 60% of "missed winners" were never setups. Fixed + 2,397 rows backfilled. |
| **extension cap** | reverted 75%→50%, operator-signed; both re-open triggers watched nightly. |
| **bars** | 1.1M minute bars backfilled — ORB coverage on the backtest population 14% → **97%**. |

### Standing artifacts written 08-29 — use them

- **`docs/methodology/analysis_standard.md`** — how analysis is done here, with a catalogue of 13
  real failures. **Pre-commit Gate 6** enforces the decidable parts. **§2 (the population IS the
  analysis) is the one that matters** — population errors, not arithmetic, caused every
  retraction.
- **28-word cap on operator messages** (`scripts/report_format_gate.py`). Tables, code and quotes
  are exempt — put the numbers there.
- `docs/analysis/482_geometry_counterfactual_2026-08-29.md` is **RETRACTED**. Do not cite it.

### Next

**#327** — post-day-1 re-entry, queued as a fast-follow and now unblocked: the backtest
population and the `scripts/probes/_bt_replay.py` harness both exist. **The real work is defining
"base" and "reclaimed pivot" precisely enough to detect from minute bars, BEFORE any replay.**
His framing: an opening range is a day-1 construct, so a delayed entry should reference a base or
a reclaimed pivot — day 2, 3 or later.

⚠ #327's own +2.00R finding is stale on both counts — deprecated 9M cohort, and it predates six
August rule changes. A hypothesis to re-test, not a result to build on.

Also open: #533, #516, #504, #331, #335, #488, #486, #482.

### Rules that bit hardest on 08-29

- **Replay raw bars, never old trade rows.** The system changes weekly; a trade row is the output
  of the rules live that day. Population AND outcomes are era-stamped.
- **Dead strategies are not evidence.** Check `mi_strategies.enabled/phase` first — `9m_day2`,
  `fishhook_v3`, `flag_continuation` are deprecated.
- **Expectancy, not win rate.** And know what the column IS — `fwd_5d_pct` is maximum favourable
  excursion, positive on nearly every row.
- **Retract, do not patch a fourth time.** If the defect is in the population, no re-run fixes it.

---

## 2026-08-30 (Sun) — 🔴 RESUME HERE. Supersedes everything above.

**State: clean.** `17142280`, pushed, 82 open, suite 6583, **drift zero**.

### 🗂 Start at `docs/SSoT.md`
For any topic it names the ONE file that owns it. Pointers only. Gated by
`tests/test_ssot_router_complete.py`. `docs/analysis/**` and `docs/design/**` are findings,
**never owners**.

### 🔴 The lesson of 2026-08-29 — do this before any analysis
**Run `scripts/live_rules.py` and hand its output as a file path to every card.** It prints what
is ACTUALLY live, from code and prod, never from prose. Three analyses ran that day against
remembered state and were wasted — one attributed 22 of 55 missed EPs to a shortlist ranking
deleted on 08-22; the EP doc had quoted a 75% extension cap for a day after the revert. Now
`docs/methodology/analysis_standard.md` §3b, plus a pre-push warning and a nightly 18:02 ET job.

### Shipped 08-29
- **#605** capture fix live — 19 new `mi_ep_scan_log` columns (23→42), scan-log-driven bar
  capture at 8%, anti-rot guard test. **Verify Monday 08-31.**
- **14.5M minute bars** — EP-day ORB coverage 14%→97%, forward sessions 7%→**99.8%**.
- **Drift check** now automatic (pre-push + nightly) and scans architecture docs and findings,
  not only setups.
- **`docs/SSoT.md`** router + gate; **`analysis_standard.md`** with a 13-item failure catalogue.

### Sunday's plan: `~/.claude/plans/crystalline-waddling-charm.md`
9 tasks. **#516 first** — the M&A filter is throwing away real EPs and needs no new evidence; his
ruling IS the evidence. Then #554, #573 (parallel cards), #331 Step 0 + #533 (Fable),
#197/#486/#488 (check-and-close). Delayed entry Stage 2 last.
**⏱ 15:02 PT Sunday: the nightly drift job's first firing** — verify it actually ran.

### Delayed entry lives in ONE place now
`docs/setups/delayed_ep_reentry.md` § **THE CONTEXT LEDGER** — his rulings verbatim, every study
and what it established, the open questions. Read it first; two cards skipped it on 08-29 and
returned his own ideas back to him.
- **"Near" is a BEHAVIOUR** — approach → deceleration → cessation → consolidation → turn.
- **The pivot is the FILTER, not the trigger.** 620 alone +0.04R; 620 at the EP close +0.21R.
- Stage 1: **55 missed EPs**, materially different from the 44 stopped-out names (~93% tail-free)
  — we were stopped out of names with no tail and missed the ones that had one.

### Standing
⚠ Dead strategies are not evidence — check `mi_strategies.enabled/phase` (`9m_day2`,
`fishhook_v3`, `flag_continuation` are deprecated; he has twice asked not to see 9M).
⚠ 28-word replies; tables carry the numbers.
⚠ Retract, don't patch a fourth time — a population defect survives any re-run.

---

## 2026-08-31 (Mon) — 🔴 RESUME HERE. Supersedes everything above.

**State:** clean, pushed (`0e5b9088`), suite **6692**, drift **0**, board **82**.

### 🔴 FIVE VERIFIES DUE TODAY — a passed verify-date HARD-FAILS the next commit

| # | what confirms it |
|---|---|
| **#605** | first scan writes score/catalyst columns for candidates KILLED EARLY, not just the 12% surviving to grading |
| **#516** | a suppression row carries a non-null `match_path` for a path that previously wrote none |
| **#554** | a Telegram RS/score read returns the newest COMPLETE day |
| **#327** | `mi_delayed_entry_watch` gains rows for today's gap-day names (17:57 ET) |
| **#533** | `mi_ep_slot_rank_shadow` gains rows; on a MULTI-alert morning entries follow RS order |

⚠ A single-alert morning does NOT verify #533 — no ordering to observe. It carries forward.

### What shipped Sunday
- **The delayed-entry shadow end to end** — watch lane, three entry patterns, outcome measuring
  under two exit styles, a proximity pattern, re-entry recording. 17:57 ET, silent.
- **🔑 SLOT RANKING FLIPPED TO RS (operator-signed, money path).** Revert: flip
  `ep_slot_rank_rs` off — instant, no redeploy.
- #573 closed, #554 deployed, #606 filed, plus a simplify sweep over 68 commits.

### The number that matters
**Live: n=24, expectancy −0.48R, win 17%, average winner +1.78R.** At a 17% win rate the average
winner must clear ~4R to break even. That gap is the whole problem.

### Rules that cost time this week when skipped
⚠ Run `scripts/live_rules.py` FIRST; hand it to every card. Three analyses were wasted without it.
⚠ Every analysis card gets `docs/methodology/ANALYSIS_CARD_PREAMBLE.md` verbatim.
⚠ Win rate belongs to SELECTION, never to entry/exit.
⚠ Never pipe a deploy through `tail` — it hid a failed safety gate.
⚠ Deploy windows are ET; Sunday evening PT is already Monday ET.

---

## 2026-09-02 (Wed) — 🔴 RESUME HERE. Supersedes everything above.

**Paused ~08:10 PDT at the operator's request to restart the session for a newly released Fable
model.** Nothing half-applied. **Tree clean, pushed, HEAD `2fe2f5a2`, suite 6816 green.**

### THE ONE OUTSTANDING ACTION — THE DEPLOY

Today's six commits are **committed and pushed but NOT deployed.** Production runs `ddfdcf96`.

- I proposed *"deploying at 09:00 PDT unless you say hold"*; he paused the session instead of
  answering. **That is neither a hold nor an approval — re-state it and get his nod.**
- Windows **12:00–13:00 ET** or **21:15–22:15 ET**. `APOLLO_DEPLOY_ANYTIME=1` is OPERATOR-ONLY.
- **Scope `both`** (`shared/output_ceilings.py` changed), then expect deploy.sh to demand a second
  step **`bash scripts/deploy.sh execution`** — `scheduler.py` changed and apollo-execution runs it.
- Delta read before proposing: no `broker/`, no `execution_routes`, no `entry_pipeline`. Nothing on
  the money path rides along.
- **The only live-behaviour change in the deploy:** on an `is_revenue_stage` data outage the judge
  was handed the boost gate's fail-soft `True` as a measured "pre-revenue: yes"; it now renders
  "not checked". Everything else is shadow, telemetry, wording or cleanup.

### What shipped into the tree today

- **Verifies closed:** #584, #613, #611. **#615 → 09-08** (event-gated; zero alerts fired, so
  nothing was graded). **#471** ripened as forecast but keeps a second open checkpoint → stays
  `deployed`, ETA 09-09, behind EP work.
- **`/simplify` Phase 2**, four Sonnet reviewers over yesterday's diff, three commits. The altitude
  pass found a **live bug**: yesterday's judge fix reached only the one call site its own guard
  reads, so the production chart-axis shadow grader was still being told "no direct source" on
  every ticker. Fixed, and the guard now covers the mirror too. Also: the replay harness's
  `validation_verdict()` had never once been called; a theme-engine alarm wrote an event name no
  error sweep queries; three different SEC identities collapsed to one.
- **#616 built** (shadow-only ADR-proportional stop recording in the delayed-entry lane).
  Status **`in_progress`** — flip to `deployed` with verify-date **09-03** once it ships.

### #616's verify — the "before" leg is already captured

Pre-deploy prod baseline, read-only, also written onto #616's PLAN line:
**1,981 settled triggers · incumbent md5 `6c605ce05abb7df7d655642c346ecda0` · all `settle_v2`.**
After the first nightly, re-run that md5 filtered to `settle_version = 'settle_v2'` (existing rows
keep v2; only new settles stamp v3) — it must match. Settled `realized_r_*075/100` are NOT expected
night one: variants resolve up to 20 sessions after the fire.

### Still open

**#333** verify tonight 18:12 ET · **#615** 09-08 (⚠ filter `log_caller = 'ep_grade_judge'`) ·
**#601** (a ruling filed under a theme's name is lost when the theme is renamed) · **#612** rotate
the Polygon key (his) · **#545** carries the retry idea and the missed-EP read.

### The pattern worth carrying forward

Three instances in two days of **a fix, gate or alarm that exists but never actually acts** — a fix
at one call site of two, a validation function nothing called, an alarm named so no sweep reads it,
and #616's writers missing from the gate whose own comment says to register them. Before believing
a mechanism works, find where it FIRES.
