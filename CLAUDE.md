# Apollo the Wise — Claude Context

## 🛑 THE LINE — you do NOT control the system or the money (operator, 2026-06-22, ABSOLUTE)

**NEVER**, on your own authority, change / disable / alter any **strategy, sell or entry discipline, sizing, target, safeguard, the trading system, or anything touching real money or live trade state** — that is the operator's **SOLE** authority. **Pausing broken code to fix a bug is NOT a license to change the strategy**: say "X is paused while we fix the bug; the fix restores it" — never "we'll run without X." If a genuine fork exists ("if not fixed by date Y, gate the launch vs run without the feature?"), **surface it as the operator's decision** — never pre-decide it, never bury it in a plan. In any doubt: **STOP and ask.** This line cannot be crossed. (Crossed once 6/22 — retracted; never again.)

## Working rules (operator 2026-06-28 — HARD, override defaults)
- **Max 1 rebump.** Due/overdue task → UNBLOCK + SHIP, not re-date. A 2nd bump is FORBIDDEN without my sign-off — tag `[ok:reason]`/`[blocked:reason]`. Gated in `check_plan._rebump_gate`.
- **No conservatism unless REAL $ at risk.** Default = ship / graduate / load-bearing. Don't hedge ("shadow-first" etc.) unless it risks real money (THE LINE). Themes / grades / detectors = no money → ship full.
- **Concise — no essays; never mention session length or ending/deferring a session — keep working.** A decision = the fork + a 1-line rec.
- **📐 REPORT FORMAT — HARD, asked 5× across multiple days (operator 2026-08-02: *"how can I get the format I asked for without asking again and again"*). It lives HERE, not in memory, because memory was recalled and still drifted inside 24h — same lesson as every other prose-discipline failure in this file: only the always-loaded surface holds.** EVERY progress report / summary / status:
  1. **Header carries the SUBSTANCE** — name the thing AND the result. *"#340 — a stale data-quality threshold now surfaces in 3 days instead of never"*, NOT *"#340 — shipped and verified"* (status theatre).
  2. **Bullets. Titled blocks (problem / what shipped / result / action) once there is >1 idea. NO prose paragraphs** — a bolded lead-in followed by 3 sentences is still a paragraph, and is the exact drift that keeps recurring.
  3. **One line per bullet** where possible.
  4. **Action ALWAYS stated, including "none"** — he must never infer whether something waits on him.
  5. **Reasoning / caveats / rejected alternatives → the commit, PLAN.md or the SSoT. Not the message.** If it does not change his decision, cut it.
  6. **PLAIN WORDS. Every number carries its meaning, or it is cut** (operator 2026-08-03: *"lingo filled wordy text with no context… avoid meaningless lingo and numbers with no context"*). "0-for-9" → "the last nine live trades were all losers". Internal shorthand (excess, N=, R, cohort, precision) belongs in the commit/SSoT. **A number he cannot act on is noise — state the conclusion, not the measurement.**
  7. **🚨 LENGTH, not format (operator 2026-08-08: *"you 1) write too much 2) overcomplicates 3) hides the core most important points underneath all the rambling"*).** Bullets are still a wall of text; the hook only catches paragraphs, so the drift moved here. **FIRST LINE = THE ANSWER** — he can stop there and be right. **~6 bullets, ~1 screen, hard**; over that you are reporting PROCESS. **Mechanism / root cause / verification / caveats: DELETE BY DEFAULT** → the commit. Per line: *would he act differently without it?* No → cut.
  ⚠ Partial compliance reads as non-compliance: one paragraph undoes a well-formatted message. Template: memory `report-like-an-exec-summary`.
  🔒 **MECHANICAL SINCE 2026-08-02** (asked a 6th time the day this was written — the always-loaded surface is NOT enough alone). `scripts/report_format_gate.py` is a **Stop hook** (`.claude/settings.json`) BLOCKING any reply with a prose paragraph outside a bullet — the one drift that recurs and the only rule here objectively decidable from the text. Deliberately narrow (bullets free; short replies never gated; headings/tables/code/quotes exempt) — a guard that always fires is not a guard — and it fails OPEN so it can never wedge a session. Rules 1/4/5 stay judgement calls — no gate decides them without crying wolf.

## 🧭 Operating model — who does what (operator 2026-07-25, PERMANENT)

Work routes to the model that fits it; each carries its own responsibility. Standing default, not a per-session choice.

| Who | Owns |
|---|---|
| **Fable** (`Agent`, `model:"fable"`) | The hardest work — design, complex analysis, adversarial review, **complex implementation**, to execution depth. |
| **Sonnet cards** (`model:"sonnet"`) | Basic + mechanical implementation — scoped well-specified builds, tests, refactors, sweeps. |
| **Opus** (main loop) | Orchestration + routing, operator-facing judgment, surfacing THE LINE, **verifying everything that comes back**, session rituals, the final report. |
| **`advisor`** | Consultation BEFORE committing to an approach + the FINAL review before declaring done. |

"Implementation" is in two rows deliberately — the split is **complexity, not task type**. Don't keep hard work on Opus because the context is here; that's the failure this corrects. Trivial one-liners stay inline (card overhead > the work).

**Non-negotiables, all model-agnostic:**
- **THE LINE doesn't move.** Sign-off + CHANGE_PROCESS + backtest + verify-live apply no matter which model wrote it.
- **Never rubber-stamp a premium model** — verify against code/data before it reaches the operator (1 of 6 REDs over-rated 7/12; a "NULL bug" was a deliberate fail-safe).
- **Never manufacture work** to feed a model — the mechanism being easy doesn't make the work infinite.
- **⚠ Capacity:** subagents INHERIT the session model — a Fable-session review fleet burned 75% of capacity (7/17). Explicit `model:` on EVERY spawn; SESSION on Opus, Fable per-task.

## Session Protocol (open + close — the anti-drift ritual)

**SoT for ALL planned work = `PLAN.md`** — the ONE file: every task under a `## project` with an `ETA` date + `status`; the long-horizon plan (the 6/22 launch) lives there as dated tasks. The calendar is phone reminders only; `data_gated_reviews.yaml` keeps its runtime predicates but only references #IDs; the harness #-task list is a session scratch mirror. **On any conflict, PLAN.md wins.** Enforced by `scripts/check_plan.py` (pre-commit Gate 2): no task without project+ETA+status, no OPEN task with a PAST ETA, every open task filed — mechanical because every prose reconcile here failed; only gates hold. (Consolidated 2026-06-16 after the plan lived across ~7 hand-synced surfaces and the launch spine was missed 3×.)

**OPEN** (first actions, every session):
1. `git pull origin main`.
2. **`python scripts/check_plan.py --today`** → prints OVERDUE + due-today tasks = the day's plan. Read `next-session-pickup` for in-flight context (operator is **PDT** — `feedback-operator-timezone-pdt`). **On a fresh machine where the local `memory/` (pickup) is absent — e.g. a laptop — read `docs/HANDOFF.md` instead** (git-synced; the memory dir is machine-local).
3. STATE the day's plan + **WHO does each piece** (Fable/Sonnet/me), then **PIN it: `delegation_report.py --route "#N:fable"`**. The declaration is the ONLY decidable delegation check — a counting gate was measured on 37 session-days and does not exist (best precision 33%). (operator 2026-08-03: *"use them wisely"*; a CHECKPOINT not a gate — why it can't be gated is in commit `f578a54`).

**CLOSE** (when the operator wraps, or before ending):
1. **Update `PLAN.md` — the single reconcile step.** For every task touched this session: set its status; REBUMP any ETA now ≤ today to a real future date (or close the task). FILE every new item / deferral / finding / watch-item as a PLAN.md line under a project with an ETA — chat & pickup prose do NOT count (the pickup gets rewritten, PLAN.md doesn't). Refresh `.apollo_open_tasks.json` from the harness so the completeness cross-check stays honest.
2. **`python scripts/delegation_report.py`** (advisory ledger: inline chunks that should have been cards vs the morning `--route`), then **`python scripts/check_plan.py`** must pass — it FAILS on any missing project/ETA/status, any past ETA, or any open task not filed. Green = no gaps. Then **`check_plan.py --audit-new`** flags thin PLAN lines (short + no pointer/DoD) — it git-diffs PLAN.md vs `origin/main`, so an ADDED line is a *new OR re-titled* task (git sees both as additions); **enrich each before committing** (detail isn't hard-gateable — semantic; this scoped new-task CLOSE review is the backstop, operator 6/20).
3. If code changed: `git add <files>` → commit → `git push origin main` (pre-commit Gate 2 re-runs the check).

**"Done" = VERIFIED-LIVE, not "deployed."** A #-task → `completed` ONLY when confirmed in production (shadow writes rows · alert fires · cron checked). (Catches: gdrive backup 5/24–31, #173 theme-shadow 0-rows — all looked done, none were.) **The old "keep `in_progress` + a verify step" was PROSE that got forgotten — built tasks sat `in_progress` for weeks wearing a to-build headline and got re-checked/re-built (operator 2026-07-18: the daily-waste leak). MECHANICAL now:** on ship, flip the task's status to **`deployed`** and set its **ETA = the verify-date** (the day it's confirmable in prod, e.g. next market day). `deployed` = built+shipped-awaiting-verify — a distinct status from `in_progress` (to-build), so the headline can't lie. `check_plan.py --today` (the OPEN ritual) surfaces **VERIFY-DUE** (deployed tasks whose verify-date ≤ today → confirm in prod + close) and **LIKELY-BUILT** (in_progress lines reading as built → reclassify to `deployed` or close). A `deployed` task whose verify-date passes **HARD-FAILS** the commit (past-ETA gate) until you verify+close — verify-live is a gate now, not a prose intention.

**BURNDOWN — a session may NOT end with more open tasks than the PT-day began with** (operator 2026-07-12, HARD — after a MONTH of fake burndown: PLAN.md went 99→116 across four "exercises"; prose discipline never held, only gates do here). **MECHANICALLY GATED:** `check_plan.py --today` (the OPEN ritual, run BY HAND when the operator says "start the day" — there is no hook) pins the day-start count into `.apollo_session_baseline.json`; the plain gate (pre-commit + CLOSE) then FAILS any commit that ends the PT-day above that line. ⚠ **A skipped OPEN no longer leaves a hole (operator 2026-07-31): the day CARRIES OVER automatically** — every plain run (pre-commit *and* the CLOSE reconcile) drops a watermark of the count it saw, and a PT day that never ran `--today` arms its ceiling from the PREVIOUS day's ENDING count, saying so (`growth gate CARRIED OVER from <date>`). **So running CLOSE is not incidental — it is what sets tomorrow's ceiling.** The carry reads the previous day's watermark, NEVER today's live count: pinning "now" at the first commit would bake tasks already opened this session into the ceiling and ratchet it upward. With nothing to carry (first run on a machine) it degrades to a loud `growth gate is NOT ARMED today`. The ONLY escape is an operator-signed `python scripts/check_plan.py --carryover <N> "<reason>"` for genuinely necessary growth — **OPERATOR-ONLY; never self-authorize** (like THE LINE). Rules: (1) single SoT — NEVER reduce the count by reclassify/split/hide (roadmap, v1.x/v2.0 stay as tasks — we lost things before when they lived outside the list; **a split is NOT a burndown**). (2) Reduce ONLY by real completion (ship + **verify-live**) or legit dedup (true duplicate, pointed at where the work lives). (3) Each session take a **HARD LOOK for real closes** + bias to FINISH the doable in-session. **Never suppress capture to keep the number green:** if real must-do work is found and no honest offset closes, FILE the task and take an operator carryover — dropping it, shoving it to a notes doc, or deferring it to protect the count is the same hide the rule forbids (that's how we lose things). The gate stops GROWTH; only real completion makes the count FALL — **it is a floor, not an engine.** The carryover is operator-INITIATED + rare (never agent-proposed) — the escape mustn't become routine (the `[ok:]` rebump drift). (4) Some tasks are **event-gated** (a live fill, N=20) — they close when the event fires + you verify it; never remove them early to fake a drop, and never let them block completing what IS doable. (5) Goal: active backlog → ~0. Scope-unrecoverable ghost → `⚠ SCOPE UNRECOVERABLE` for operator recall/close, not silently deleted.

**On-demand reconcile:** "**where do we stand**" (or similar) = run `python scripts/check_plan.py --today` + read `next-session-pickup` for in-flight context, then report true state (done / in-flight / slipped). One file, one command. (Avoid colliding triggers like "sync"/"status" — those map to trade-state commands here.)

**Capture:** "**track it**" / "**track this**" = add it as a `PLAN.md` line immediately — under a project, with an `ETA` + `status` (**Miscellaneous** if no home; **propose a NEW project** if a genuine big-rock). Also route to `data_gated_reviews.yaml` if evidence-gated, or a memory if it's a fact/feedback — confirm back WHERE + the #. Default to over-capturing.

**EVERY task gets a project + ETA + ACTIONABLE DETAIL + a CLEAR OUTCOME AT CREATION** (never a bare bucket label) — `scripts/check_plan.py` (pre-commit Gate 2) FAILS the commit on any task missing a project/ETA/status, any past ETA, any open snapshot task not filed, or any **placeholder title** — the create→file-with-substance rule is a gate, not memory (operator 2026-06-20).

Older session details live in git history; see `CHANGELOG.md` for a roadmap.

## COST EFFICIENCY — HARD RULE (operator 2026-08-03)

*"cost efficiency is a must for all work going forward"* — after a $1.30 eval ran 3x (~$4), piped to `sed` instead of saved.

- **CAPTURE ONCE, READ MANY.** Anything spending money or mutating state: full output to a file on run ONE, then read the file. **Never re-run to re-read.**
- **PRICE THE WHOLE PATH UP FRONT** (operator 2026-08-09: *"a holistic view instead of piecemeal adding more cost each step of the way"*). Before the FIRST dollar: all remaining gates + the ongoing run cost, from `pricing_for()`, as ONE number. Drip-feeding the next increment is the failure.
- **TRY THE $0 PATH FIRST** — outcome-join, replay, or read what ran. [[rigor-before-paid-eval-spend]]
- **ONE PAID RUN PER QUESTION** — capture all, post-process locally.
- **Subagent fleets are real spend** — scope each card off what you hold.

## Default to DOING, not tracking (bias to action)

When you discover an issue or a worth-doing improvement, **default to fixing/building it in the same session.** Filing-to-backlog is the EXCEPTION, allowed only with a NAMED reason from this closed list:
1. Needs evidence/backtest we don't have yet (methodology / detection-criterion change → CHANGE_PROCESS).
2. Needs a validation that genuinely can't run now (e.g. market-hours-only) AND no safe shadow/subset exists.
3. Blocked on an unfinished piece or an operator decision.
4. A big-rock that needs its own scoping/sequencing session.

NOT reasons (these mean *just do it*): "it's late / after-hours," "it's minor/quick," "let me batch it," habit. When the FULL change is legitimately gated, **ship the SAFE SUBSET now** (shadow / telemetry / read-only analysis) and defer only the gated part — never the whole thing (e.g. 2026-06-01 cooldown: shipped the shadow now, gated only the live-flip on realized-R). This bias NEVER overrides the safety line (no bypassing safety gates, no untested trade-state, no fabricated evidence) — those gates route you to the safe version, NOT to the backlog. Doing-now shrinks the backlog and is the surest way to not lose things.

## 📋 Backlog / TODO / Task / "what's next" questions → `PLAN.md`

Same SoT as Session Protocol above: `PLAN.md` at repo root (projects → tasks → ETA + status; the long-horizon launch lives there as dated tasks). Run `python scripts/check_plan.py --today` for the day's plan. Only `data_gated_reviews.yaml` retains separate runtime behavior (YAML predicates, weekly auto-surface) and it references #IDs back into PLAN.md.

**"run fable weekend block N"** (operator trigger, inline-Fable design sessions) → open `docs/roadmap/fable-weekend-blocks.md` §Block N and execute it to pure-execution depth. Fable's output still clears SSoT + CHANGE_PROCESS + sign-off + backtest before any live flip (THE LINE) — scope per the operating model above, no longer design-only.

## 📛 SETUP vs FAMILY — a definition, not a preference (operator 2026-08-02, HARD)

*"continuation is NOT a setup, we went over this a thousand times, it's a family… a trading setup
needs a clear buy and stop point, continuation does not on its own… that setup needs a name and
continuation flag is not. Just cut out this confusion every time."*

- **SETUP = a named entry with a DEFINED BUY POINT AND STOP.** MAGNA53 EP (buy ORB high, stop ORB
  low) is a setup. If you cannot state where it buys and where it stops, **it is not a setup.**
- **FAMILY = a chart condition/context that can HOST several setups** but is not tradeable itself.
  **Continuation / consolidation-post-runup is a FAMILY.** So is "Family A" (ADR 0013).
- Within a family the tradeable entries each need **their own name** — buy-early-on-anticipation vs
  buy-the-breakout are DIFFERENT setups with different buy/stop, not one thing.
- ⚠ **Never call a family a setup, never call a detector/stage-board a setup.** The continuation-flag
  detector emits WATCH/TIGHTENING/COILED/TRIGGERED — those are STATES, not setups. `#354` folds it
  into Family A for exactly this reason.
- Filed here (not memory) because it has been re-litigated repeatedly; a definition that keeps
  getting re-derived belongs on the always-loaded surface.

## 🛑 Trading Setup Changes — Read SSoT First (NON-NEGOTIABLE)

**Before changing ANY detection criterion** (parabolic, EP, 9M, flag, wick, convergence, future setups) **OR portfolio safeguard** (max_positions, daily_loss_limit, circuit_breaker, drawdown_breaker, PDT — see `docs/setups/safeguards.md`):

1. **Read the setup's SSoT file** at `docs/setups/<setup>.md` — entire file, not just change log. Confirms current criteria, recent changes, and known limitations.
2. **Read `docs/setups/CHANGE_PROCESS.md`** — discipline rules including required change-log fields, reversion-flag, evidence requirements.
3. **If the change is a reversal** of a prior decision, read the prior change-log entry to understand WHY the prior reasoning was made, and articulate why it was *wrong* (not just incomplete) before reverting.
4. **HARD gates require user sign-off on the filter list.** Agent must NOT classify a filter list as "correct" / "false positive" without user judgment (see parabolic_short.md 2026-05-08 ship→revert→restore cycle — that flip-flop is exactly what this rule prevents).
5. **Backtest before deploy** for any threshold change. N≥10 historical samples evaluated. Single-case fixes ("fixed because of TICKER 5/07") flagged as such in the change log.

**Update the SSoT in the same commit as the code change** — stale SSoT is worse than no SSoT (gets cited authoritatively, contradicts the code). Rule exists after repeated overfitting/oscillation before this discipline existed (parabolic days_up_streak ship→revert→restore 2026-05-08, theme ticker bans 2026-04-29).

## What This Is
Telegram-based personal assistant ("chief of staff") for momentum/EP trading (Qullamaggie, Pradeep Bonde, Marios Stamatoudis methodology). Routes to specialized sub-agents.

## ⏰ Time Handling — ET for MARKET CODE · PT for the OPERATOR (two frames, NEVER conflate)

**🟢 OPERATOR-FACING + PLANNING = PT (Pacific), ALWAYS.** Every date/time you SAY to the operator, every
`PLAN.md` ETA, every "today / tomorrow / how-late-it-is" = the operator's **PT** day. The harness
"Today's date" is **UTC** and is NOT the operator's day — never use it for operator-facing dates, tallies,
or judging the hour. **When a date matters, RUN `python scripts/operator_now.py`** (don't guess off the
harness UTC date). Mechanical backing: `check_plan.py` compares ETAs in PT (not ET). ⚠ **There is NO SessionStart
hook — the OPEN ritual is triggered BY HAND** (the operator opens the day with "start the day");
this doc claimed a hook that was never configured on any machine (found 2026-07-31 by /doctor). [[feedback_operator_timezone_pdt]]

**🔵 MARKET/CODE = ET (the rest of this section).** Every datetime/time comparison in TRADING code is in
America/New_York (ET) — ORB windows, market hours, scan deadlines. The container runs UTC; **naive
`datetime.now()` returns UTC clock values with no tzinfo and silently breaks every ET-keyed comparison.**
This bug class has recurred many times.

**PERMANENT FIX (2026-06-05), mechanically enforced.** Root cause was **pytz** (NOT ZoneInfo — commit `8de7849`'s label was wrong): a pytz zone attached via `tzinfo=` silently applies the LMT `-04:56` offset (shifted the ORB window +56 min, #180/#183). `_ET` is now `ZoneInfo("America/New_York")` everywhere, and deploy gate `[5h/7]` (`preflight_datetime_hygiene.py`) BANS `import pytz`, naive `datetime.now()`, bare `.astimezone()`, `datetime.utcnow()`, and `date.today()` in `agents/ core/ channels/ shared/` (escape: reviewed `# tz-ok: <reason>`; offline `backtester/` excluded). **pytz is BANNED — never reintroduce it.** Full story: memory `timezone_lmt_pytz_permanent_fix` + CHANGELOG.

**Do:**
- `from zoneinfo import ZoneInfo; _ET = ZoneInfo("America/New_York")` — already imported at the top of `system_audit.py`, `audit_invariants.py`, `scheduler.py`, `crypto/ingest.py`, etc.
- `datetime.now(_ET)` for "now" comparisons (job deadlines, market hours, ORB windows).
- `et_today()` from `collector.py` for "today's date" (handles DST + container UTC).
- `last_trading_day()` for queries that must skip weekends/holidays.
- SQL: `AT TIME ZONE 'America/New_York'` when comparing TIMESTAMPTZ columns to ET date constants. Cast `TIMESTAMPTZ → DATE` only after the AT TIME ZONE conversion.
- APScheduler: `CronTrigger(..., timezone=ZoneInfo("America/New_York"))` — never UTC cron times.

**Don't:**
- ❌ `datetime.now()` — naive UTC, defeats `or datetime.now(_ET)` defensive defaults downstream.
- ❌ `datetime.utcnow()` — same problem, naive.
- ❌ `date.today()` — returns container's UTC date; after 8 PM ET it's already tomorrow. Use `et_today()`.
- ❌ Mixing tz-aware and tz-naive datetimes in the same comparison — Python raises, but only at runtime.
- ❌ Hardcoding UTC offsets — DST breaks them twice a year.

## Running Locally
```bash
bash start.sh          # Terminal 1 — orchestrator + Postgres + Redis
bash start_market.sh   # Terminal 2 — market agent
# Verify: /agents in Telegram — all green
```

## Architecture
```
User (Telegram)
      │
Apollo Orchestrator (port 8000)   ← claude-sonnet-4-6, tool-use loop
      │  POST /task  +  X-Apollo-Secret header
      ▼
Market Intelligence agent (Docker, :8006)
      │
PostgreSQL (pgvector) + Redis
```
**Key rule:** Only the market agent is exposed as a sub-agent. All trading/market features live inside it.
**`agents/market_intelligence/db.py` is the single source of truth for every DB query + the schema** — add queries there, never inline in a caller.

## Adding an Orchestrator Tool
1. Tool schema → `core/router.py` → `get_orchestrator_tools()`
2. Dispatch → `core/orchestrator.py` → `_dispatch_tool()`
3. Handler → inline in orchestrator OR delegate to market agent's `execute_task()`

## Adding a Telegram slash command (`/foo`)
Three places must be updated **in the same commit** or the command is hidden from operators:
1. **Handler** in `agents/market_intelligence/agent.py` — `_handle_foo_query(self, request)` method.
2. **Dispatch** in `agent.py` — entry in the command-to-handler dict (e.g. `"/foo": self._handle_foo_query`).
3. **Bot command list** in `channels/telegram.py::_register_commands` — `BotCommand("foo", "<short description>")`. This is what makes the command appear in the Telegram `/` menu (six commands missed this in May 2026 and were invisible).

## Market Agent Routing (`execute_task`)
Order matters — first match wins:
1. watchlist / 2. theme engine rerun / 3. refresh / 4. history
5. EP outcomes ("ep outcome", "ep performance", "ep returns", "ep results")
5a. **9M EP outcomes** ("9m outcome", "9m performance", "9m result", "sugar outcome") — before 9M query
5b. **9M trades** ("9m trade", "9m position", "trade 9m", "show 9m trade")
5c. **9M EP query** ("9m ep", "sugar baby", "sugar babies", "nine million", "show 9m", bare "9m")
5d. **Continuation flag** ("/flags", "coiled", "tightening flag", bare "flags") — see _handle_flag_query
5e. **/setup TICKER** — reverse-lookup detector chronology across ~10 detector tables
6. EP ("ep", "episodic", "gap", "pivot", "gapper")
7. journal add ("journal:", "log trade") / journal query ("show journal", "my journal")
8. theme ("theme", "sector", "industry") — before regime/RS
9. regime / 10. RS/score / 11. briefing / 12. pullback / 13. fundamentals
14. screener / 15. audit log ("audit log", "show logs", "show errors") / 16. weekly review ("weekly review", "system review", "self audit") / 17. /audit topic ("audit <topic>") / 18. fallback

## Ticker Extraction
```python
re.findall(r'\b([A-Z]{2,5})\b', request.task.upper())
```
Common English words live in the shared `_PREPOSITION_SKIP` frozenset (`agent.py`) — add new ones THERE (one place). Each ticker-extraction site extends it: `_PREPOSITION_SKIP | {site-specific command words}` (e.g. `{"RS","SCORE"}` in `_handle_single_score`). #260 (2026-06-10) deduped the former three hand-synced copies into this base; `tests/test_execute_task_routing.py` freezes the routing cascade.

## Key Domain Concepts

### RS Scoring
- Composite = 40% × 1M + 30% × 3M + 30% × 6M percentile rank
- Universe ~9,700 stocks via Polygon grouped daily (adjusted=true always)
- Sector enrichment: only top 300 by rank get sector in `mi_stock_scores`. For theme tickers outside top 60, fetch sector from `mi_ticker_overrides` (persistent cache) via `get_sectors_batch()`.

### Theme Engine
Bottom-up from price action (themes emerge from RS, not hypotheses); lifecycle Nascent → Accelerating → Mainstream → Fading → Retired. **FULL SSoT: `docs/architecture/theme_engine.md`** (validation cadence, birth validation #266, engine-drop retirement, tool schemas, Phase-2 re-granularization arms) — read it before touching theme behavior; update it in the same commit. Two rules that bite most often, kept inline:
- **`mi_theme_exclusions`** = user-directed permanent bans ONLY — NEVER auto-populate from validation removals (a bad-description removal once permanently banned TSEM from semiconductor theme).
- **`get_active_themes(stale_after_days=7)`**: the recency cap is the de-facto retirement mechanism — themes absent from daily snapshots age out after a week.

### EP Detection (MAGNA53)
- Alpaca bars use feed selected by `ALPACA_DATA_FEED` env var (`iex` default; `sip` requires Algo Trader Plus subscription) — resolved by `alpaca_client.get_data_feed()`.
- **Open intensity projection**: only applied after 15 min since open (≥9:45 AM). Pre-9:45 uses raw RVOL — opening minutes are always dense and create false 30x+ projections.
- **Extension check**: uses MIN(close) over last ~5 trading days, not a single point 5 days ago.
- HIGH ≥ ep_threshold (regime-dependent) → immediate Telegram alert; MODERATE 50-69 → morning briefing
- **ORB submission window**: `now_et.hour == 9 and now_et.minute < 45`. HIGHs at 9:45–9:59 → `WINDOW_OUT_OF_ORB`. 10:00 ET cleanup job cancels any unfilled `order_placed`. (Also documented in `docs/setups/magna53_ep.md`.)
- **Fade guard** (`entry_pipeline.py::check_fade_guard`): tiered — MAGNA53 HIGH passes `None` (skipped), 9M Day 2 passes `0.25` (skip if last < lower 25% of ORB). Stop-buy mechanics + 10:00 ET unfilled-cancel are the real backstop.

### 9M EP Detection (Parallel Track)
- **No LLM** — pure quantitative virgin 9M detection (Pradeep Bonde). Quick reference: price ≥ $5, dollar volume ≥ $50M actual (≥ $30M already-traded for anticipation), directional gap ≥ 3% OR intraday gain ≥ 4%, anomaly effective_vol ≥ 3× ADV (ratio, NOT a flat ceiling; unknown ADV passes). **Full gate list + Sugar Baby definition + stop placement are the SSoT in `docs/setups/ninem.md` (FULL parity verified 2026-07-05) — read it before touching any threshold.**
- **Intraday and EOD use identical filters** — any divergence creates phantom sugar babies.
- **Stop = prior day's low** (breakout day's low), NOT ORB low or ATR-based.
- **Tables**: `mi_9m_ep_alerts` (intraday), `mi_9m_day2_candidates` (EOD confirmed; renamed from `mi_9m_sugar_babies` 2026-05-23 #82 — the persistent Pradeep cohort is in `mi_sugar_babies_cohort` separately)
- **Anticipation cadence carve-out**: silent anticipations hit DB/audit only; Telegram only when gap ≥ 10% OR proj_vol ≥ 25M.
- Do NOT import from `ep_detector.py` — use `collector.get_snapshot_all()` directly in `ninem_detector.py`

### Entry Pipeline
**`broker/entry_pipeline.py::submit_trade_entry`** — the single funnel for both MAGNA53 EP and 9M Day 2 entries (strategy differences inject via `spec_builder`). **FULL SSoT: `docs/architecture/entry_pipeline.md`** (pipeline stages, action/skip-reason vocabularies, account_mode threading) — update it in the same commit as any pipeline change. **Contract kept inline: every terminal failure Telegrams via `humanize()`.**

### Dual-Account Architecture (#66, 2026-05-10)
One container, two Alpaca accounts (paper + live), routed per-strategy via `mi_strategies.phase` → `resolve_account_mode_for_strategy()`. **FULL SSoT: `docs/architecture/dual_account.md`** (phase→destination table, per-mode clients/streams/safeguards/sync, boot bootstrap, #65 per-strategy sizing/cap) — read it before touching any account-mode code; update it in the same commit.

**The 3 correctness invariants (safety backbone — never relax):** (1) mode-bound client order IDs (`make_client_order_id`) at EVERY submission site; (2) cross-account event rejection before any DB mutation (`_verify_event_account_mode`); (3) `account_mode` filter on every trade query.

### Stop-Leg ID Capture
`alpaca_client.extract_stop_leg_id(order)` is the canonical helper — **never re-implement the loop** (5 call sites; details in `docs/architecture/entry_pipeline.md`).

### Self-Audit System (L1/L2/L3)
- **L1** invariant breach (hard SQL guard fails) → immediate Telegram + audit row.
- **L2** anomaly (metric outside 30d trimmed median ± 3 MAD OR > 5× median) → immediate Telegram with Sonnet hypothesis.
- **L3** drift (band transition) → audit row only, surfaces in Sunday weekly digest.
- Jobs: `_post_eod_audit_job` 16:15 ET, `_post_nightly_audit_job` 17:30 ET, `_baseline_refresh_job` 02:00 ET.
- On-demand: `/audit <topic>` (cooldowns/themes/skips/positions/feed/9m/all).
- Cold-start tiers: `sample_n < 7` → hardcoded `_COLD_START_CEILINGS` only. `7 ≤ n < 14` → L3 only. `≥ 14` → full L2.
- Sonnet hypothesis call gets last 5 CLAUDE.md change headers + last 10 distinct audit event types as context.

### Error Alerting
- Silent failures in theme engine write to `mi_audit_log`: `validation_error`, `assignment_error`, `discovery_error`, plus `validation_rate_limited` / `anthropic_rate_limited` for 429s.
- After nightly run: if any `*_error` events in last 2h → immediate Telegram alert.
- Morning briefing: 3-bucket banner (🔴 errors / 🟠 rate-limited / 🟡 parse errors).
- Telegram: `show errors 7d` pulls all error events for the period.

### Paper Trading (Alpaca)
- `mi_paper_trades` = EOD simulation table (LIVE_TRADING_ENABLED=true, ALPACA_PAPER=true)
- `mi_live_trades` = actual Alpaca order table
- ORB entry at 9:31 AM; bracket order: stop-limit buy at ORB high, OTO with stop-loss at ORB low. Always `order_class=OrderClass.OTO` — alpaca-py silently drops `stop_loss` kwarg without it.
- Safeguards (SSoT `docs/setups/safeguards.md`): max 5 positions (`MAX_CONCURRENT_LIVE_POSITIONS`), 2% daily loss limit, tiered drawdown breaker (active 2026-06-03). Count-based circuit breaker (10 losses) is **KEPT** (operator-ruled 2026-07-31, cancelling its queued removal — the plan was to run ONE breaker, the drawdown one; it promoted 6/03 but has never ACTED on live money, so the swap was met in NAME only). BOTH run. ⚠ It is self-perpetuating: a loss closing during cooldown re-arms it 24h from THAT close, so its expiry can land inside the 9:31-9:45 ORB window and cancel most of a day's entries (6 alerts / 0 entries, 2026-07-31).
- Kill switch: `LIVE_TRADING_ENABLED=false` (boot-read) · `/pause` (instant runtime halt, #345)

### Telegram Formatting
- NEVER use pipe tables — Telegram can't render them. Use monospace code blocks.
- `send_telegram_message` in `briefing.py`. Returns False on failure (never raises).
- Escape dynamic strings before passing with Markdown mode.
- Skip-reason machine prefixes (`infra:subscribe_timeout: ...`) → run through `humanize()` before user display. DB keeps machine prefix; user sees prose.
- Reserve Telegram for terminal/actionable events. Self-healing/transient → `mi_audit_log` only.

## Pre-commit hooks (one-time setup per clone)
After fresh clone, activate the local pre-commit gates:
```bash
git config core.hooksPath .githooks
```
Currently enforces:
- **pre-commit — YAML dupe-key check** on `data_gated_reviews.yaml` (mirrors deploy.sh `[5e/5]`; catches the 2026-05-24 SNDK class bug at `git commit` time instead of at deploy or runtime), plus the PLAN.md single-SoT gate (Gate 2) + CLAUDE.md size ceiling (Gate 3).
- **pre-push — full `python -m pytest tests/ -q`** (mirrors CI), runs only when the pushed commits touch Python, blocks the push on failure. Added 2026-06-17 after a subset-only local test run shipped a CI-breaking regression (the downgrade-digest mock). Bypass an emergency push with `git push --no-verify`.

Pre-commit gates are vanilla shell + fast (<1s); the pre-push test gate is ~30s (Python pushes only). Bypass with `--no-verify` only if you really know what you're doing.

## Production Deploy
- Server: `ssh apollo@87.99.134.162`, dir: `/home/apollo/apollo_the_wise/`
- Service names: `orchestrator`, `market-agent`, `postgres`, `redis`, `uptime-kuma`
- **Disaster recovery**: if the host dies, follow `docs/ops/disaster_recovery.md` (operator runbook + `infra/restore.sh` driver). RTO ~95 min. Nightly cron writes pg_dump + GPG-encrypted secrets bundle to gdrive; `_backup_health_check_job` (04:33 ET) Telegrams if either blob is stale >36h. OAuth recovery (gdrive upload failing): `docs/ops/gdrive_backup_recovery.md`.

**Canonical deploy command — use the script, not raw `docker compose` commands.** It chains git pull → build → up → wait-for-boot → preflight (`set -euo pipefail`; any step failing exits non-zero with a specific code per failure mode). Scope is REQUIRED (no default, #154 tier-1) — deploy.sh also aborts (exit 11, #154 tier-2) if the pull brought changes to files owned by a service outside your chosen scope.
```bash
bash scripts/deploy.sh market-agent    # market agent only
bash scripts/deploy.sh orchestrator    # orchestrator only
bash scripts/deploy.sh both            # both services
```
Ownership map for the scope-drift guard: `channels/ core/ main.py` → orchestrator; `agents/market_intelligence/ scripts/` → market-agent; anything else (`shared/`, `docker/`, `requirements/`) → both. (New Telegram slash commands touch `channels/telegram.py`, orchestrator-owned — need `orchestrator`/`both`, not the market-agent default that silently dropped `/partialnow` on 2026-05-28.)

The preflight (`scripts/preflight_check.py`) walks every enabled non-shadow strategy through `_check_safeguards` — the exact code path that fires on real ORB entries (auth, account fetch, position cap, daily loss, drawdown breaker). Treats `setup:*` / `infra:*` as failures; only `block:*` reasons count as pass-through. Failure here = deploy is not green.

**Why this matters**: a raw `docker compose` deploy (skipping preflight) caused the 2026-05-13 outage — `phase='live'` strategy under `ENABLE_LIVE_MODE=false` raised `KeyError: 'ALPACA_LIVE_API_KEY'`, uncaught by the old boot smoke (`verify_dual_account_clients` only checks clients whose credentials happen to be present). This preflight exercises the strategy-driven path instead — the one that actually fires on a real ORB entry. Full incident detail: `CHANGELOG.md` 2026-05-13 entry.

## Required Env Vars
```
TELEGRAM_BOT_TOKEN, TELEGRAM_ALLOWED_USER_IDS
ANTHROPIC_API_KEY, POLYGON_API_KEY, FMP_API_KEY, PERPLEXITY_API_KEY

# Dual-account Alpaca (#66, 2026-05-10) — required when ENABLE_LIVE_MODE=true
ENABLE_LIVE_MODE=true       # false = dev/single-account opt-out (paper only)
ALPACA_PAPER_API_KEY, ALPACA_PAPER_SECRET_KEY     # paper-api.alpaca.markets
ALPACA_LIVE_API_KEY, ALPACA_LIVE_SECRET_KEY       # api.alpaca.markets

# Legacy (deprecated; remapped to ALPACA_PAPER_* at boot for one cycle):
ALPACA_API_KEY, ALPACA_SECRET_KEY, ALPACA_PAPER=true

LIVE_TRADING_ENABLED=false  # Master kill switch — disables ALL submits
ALPACA_DATA_FEED=iex        # "sip" only when Algo Trader Plus ($99/mo) active
POSTGRES_PASSWORD, REDIS_PASSWORD, INTERNAL_API_SECRET, TRADINGVIEW_WEBHOOK_SECRET

# Methodology calibration overrides
REVENUE_STAGE_MIN_USD=0.01  # is_revenue_stage threshold; PROVISIONAL OPERATOR PIN
                             # (code default $5M, conservative-block). Loosens to
                             # admit pre-revenue names pending backward-check
                             # evidence: 2026-05-20/21 N=2 ratchet rolled back;
                             # N=7 clean cohort still below ship threshold.
                             # Re-eval at #55 on 2026-06-20; quarterly sweep
                             # auto-runs Feb/May/Aug/Nov 1st.
```

---

## Changes Made — Recent

### 2026-08-09 — measure the guard before building it

- Specced a delegation gate, **measured 37 session-days, did NOT build it** — complaint days sit
  inside the normal range (best precision 33%). Shipped a routing declaration + ledger instead.

Older entries → `CHANGELOG.md` (search any concept).

---

## Adding a "Changes Made" entry
Keep new entries in **Recent** section above. After ~2 weeks, compress each entry to a single bullet (`topic — key change & lesson`) and **graduate it into `CHANGELOG.md`** — don't keep the compressed form in this file. Drop "Files Changed" lists (git tells you that), drop "Post-deploy verification" once verified, drop manual cleanup SQL once applied. **⚠ Always leave ≥1 dated `### YYYY-MM-DD` entry in Recent** — `system_audit._recent_changes_context` (the Sonnet-hypothesis input) + its smoke test (`test_system_audit_recent_changes`) require it; graduating the LAST entry empties the section and reds CI (2026-06-19). A docs-only push skips the pre-push pytest gate, so this only surfaces in CI — run the test before a CLAUDE.md graduation.

Older history: see `CHANGELOG.md` (compressed log, on-demand only — not auto-loaded). For genuinely architectural decisions where the *why* outlives the code, optionally write a short `docs/decisions/NNNN-topic.md` ADR.

Target CLAUDE.md size: under 30k chars. Hard ceiling: 40k (warning threshold).
