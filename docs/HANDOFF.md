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
