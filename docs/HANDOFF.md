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

## 3. WHERE WE ARE (in-flight, as of CLOSE 2026-07-23 Thu evening PDT — the deploy-night wrap)

**Board 86** (flat this session — closed #493, filed #501). Everything pushed to `main` (HEAD d212334).
Authoritative in-flight state = **PLAN.md** (`check_plan.py --today`) + the desktop pickup memory.

**DEPLOYED tonight 7/23 (operator-approved, market-closed) — both containers green:** #500 (ORB
price-aware entry — `broker/` so it runs on apollo-**EXECUTION**, shipped via the TWO-STEP `deploy.sh
execution`, NOT market-agent alone), #498 (TQS TAPE line, apollo-market), + a carveout-dedup L2 fix. Gate 5 G
caught #500's new `_submit` writer wasn't in ALLOWED_WRITERS → registered it (operator-approved). The 2 open
live positions (NVCR/SMCI) stayed safe (broker-side stops) through the execution restart.

**7/24 verify-lives (event-gated on the market):** #500 (a violent gapper crossing orb_high in-window gets a
real fill / a named skip — or the G6 replace-smoke on the next MARKET-HOURS deploy) · #498 (TAPE line + NTR
sparkline render on a live EP alert — verify the SURFACE) · carveout dedup (logs once/ticker on the next
earnings-carveout name).

**Parked on OPERATOR (5 rebumped tonight, due-today→next week):** #357 (Sugar-Baby Stage-1 badge — role
SIGNED, BUILDABLE) · #416 (M&A FP amendment — deployed, verify-live) · #356 (HTF #397 GO/NO-GO ruling) ·
#307/#255 (precedent-retrieval, corpus-gated). **Standing:** #489 authoritative-flip (`ep_rt_gap_authoritative`
— THE LINE, operator-only, samples accruing) · the LIKELY-BUILT(20) reclassify sweep (housekeeping). *(7/13
detail below is historical.)*

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
