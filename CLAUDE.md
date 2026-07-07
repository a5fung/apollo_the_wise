# Apollo the Wise — Claude Context

## 🛑 THE LINE — you do NOT control the system or the money (operator, 2026-06-22, ABSOLUTE)

**NEVER**, on your own authority, change / disable / alter any **strategy, sell or entry discipline, sizing, target, safeguard, the trading system, or anything touching real money or live trade state** — that is the operator's **SOLE** authority. **Pausing broken code to fix a bug is NOT a license to change the strategy**: say "X is paused while we fix the bug; the fix restores it" — never "we'll run without X." If a genuine fork exists ("if not fixed by date Y, gate the launch vs run without the feature?"), **surface it as the operator's decision** — never pre-decide it, never bury it in a plan. In any doubt: **STOP and ask.** This line cannot be crossed. (Crossed once 6/22 — retracted; never again.)

## Working rules (operator 2026-06-28 — HARD, override defaults)
- **Max 1 rebump.** Due/overdue task → UNBLOCK + SHIP, not re-date. A 2nd bump is FORBIDDEN without my sign-off — tag `[ok:reason]`/`[blocked:reason]`. Gated in `check_plan._rebump_gate`.
- **No conservatism unless REAL $ at risk.** Default = ship / graduate / load-bearing. Don't hedge ("shadow-first" etc.) unless it risks real money (THE LINE). Themes / grades / detectors = no money → ship full.
- **Concise — no essays; never mention session length or ending/deferring a session — keep working.** A decision = the fork + a 1-line rec.

## Session Protocol (open + close — the anti-drift ritual)

**SoT for ALL planned work = `PLAN.md`** — the ONE file: every task under a `## project` with an `ETA` date + `status`; the long-horizon plan (the 6/22 launch) lives there as dated tasks. The calendar is phone reminders only; `data_gated_reviews.yaml` keeps its runtime predicates but only references #IDs; the harness #-task list is a session scratch mirror. **On any conflict, PLAN.md wins.** Mechanically enforced by `scripts/check_plan.py` (pre-commit Gate 2): no task without project+ETA+status, no OPEN task with a PAST ETA, every open task filed — mechanical because every prose-discipline reconcile here has failed, only gates hold. (Consolidated 2026-06-16 after the plan lived across ~7 hand-synced surfaces and the launch-runway spine was missed 3× — `feedback-runway-not-in-open-ritual`.)

**OPEN** (first actions, every session):
1. `git pull origin main`.
2. **`python scripts/check_plan.py --today`** → prints OVERDUE + due-today tasks = the day's plan. Read `next-session-pickup` for in-flight context (operator is **PDT** — `feedback-operator-timezone-pdt`). **On a fresh machine where the local `memory/` (pickup) is absent — e.g. a laptop — read `docs/HANDOFF.md` instead** (git-synced; the memory dir is machine-local).
3. STATE that day's plan before reacting to the first message.

**CLOSE** (when the operator wraps, or before ending):
1. **Update `PLAN.md` — the single reconcile step.** For every task touched this session: set its status; REBUMP any ETA now ≤ today to a real future date (or close the task). FILE every new item / deferral / finding / watch-item as a PLAN.md line under a project with an ETA — chat & pickup prose do NOT count (the pickup gets rewritten, PLAN.md doesn't). Refresh `.apollo_open_tasks.json` from the harness so the completeness cross-check stays honest.
2. **`python scripts/check_plan.py`** must pass — it FAILS on any missing project/ETA/status, any past ETA, or any open task not filed. Green = no gaps. Then **`check_plan.py --audit-new`** flags thin PLAN lines (short + no pointer/DoD) — it git-diffs PLAN.md vs `origin/main`, so an ADDED line is a *new OR re-titled* task (git sees both as additions); **enrich each before committing** (detail isn't hard-gateable — semantic; this scoped new-task CLOSE review is the backstop, operator 6/20).
3. If code changed: `git add <files>` → commit → `git push origin main` (pre-commit Gate 2 re-runs the check).

**"Done" = VERIFIED-LIVE, not "deployed."** A #-task → `completed` ONLY when its effect is confirmed in production (shadow writes rows · alert fires · backup uploads · cron run checked). "Shipped/deployed" → keep `in_progress` + a verify step until confirmed. (Catches: gdrive backup 5/24–31, #173 theme-shadow 0-rows, FLNC-invisible — all looked done, none were.)

**BURNDOWN — the open-task count must trend DOWN** (operator directive 2026-06-20, reversing a close-some/open-more drift): (1) single SoT stays — over-counting a bit is fine; NEVER reduce the count by reclassifying/splitting/hiding (roadmap, v1.x/v2.0 stay as tasks — we lost things before when they lived outside the list). (2) Reduce ONLY by real completion (ship + verify-live) or legit dedup (true duplicate/already-done, pointed at where the work lives). (3) Bias to COMPLETE the doable in-session over deferring — every session aims NET-NEGATIVE (close ≥ open); defer only with a named reason (see closed list below). (4) Goal: active backlog → ~0. A scope-unrecoverable ghost task gets flagged `⚠ SCOPE UNRECOVERABLE` for operator recall/close, not silently deleted.

**On-demand reconcile:** "**where do we stand**" (or similar) = run `python scripts/check_plan.py --today` + read `next-session-pickup` for in-flight context, then report true state (done / in-flight / slipped). One file, one command. (Avoid colliding triggers like "sync"/"status" — those map to trade-state commands here.)

**Capture:** "**track it**" / "**track this**" = add it as a `PLAN.md` line immediately — under a project, with an `ETA` + `status` (**Miscellaneous** if no home; **propose a NEW project** if a genuine big-rock). Also route to `data_gated_reviews.yaml` if evidence-gated, or a memory if it's a fact/feedback — confirm back WHERE + the #. Default to over-capturing.

**EVERY task gets a project + ETA + ACTIONABLE DETAIL + a CLEAR OUTCOME AT CREATION** (never a bare bucket label) — `scripts/check_plan.py` (pre-commit Gate 2) FAILS the commit on any task missing a project/ETA/status, any past ETA, any open snapshot task not filed, or any **placeholder title** — the create→file-with-substance rule is a gate, not memory (operator 2026-06-20).

Older session details live in git history; see `CHANGELOG.md` for a roadmap.

## Default to DOING, not tracking (bias to action)

When you discover an issue or a worth-doing improvement, **default to fixing/building it in the same session.** Filing-to-backlog is the EXCEPTION, allowed only with a NAMED reason from this closed list:
1. Needs evidence/backtest we don't have yet (methodology / detection-criterion change → CHANGE_PROCESS).
2. Needs a validation that genuinely can't run now (e.g. market-hours-only) AND no safe shadow/subset exists.
3. Blocked on an unfinished piece or an operator decision.
4. A big-rock that needs its own scoping/sequencing session.

NOT reasons (these mean *just do it*): "it's late / after-hours," "it's minor/quick," "let me batch it," habit. When the FULL change is legitimately gated, **ship the SAFE SUBSET now** (shadow / telemetry / read-only analysis) and defer only the gated part — never the whole thing (e.g. 2026-06-01 cooldown: shipped the shadow now, gated only the live-flip on realized-R). This bias NEVER overrides the safety line (no bypassing safety gates, no untested trade-state, no fabricated evidence) — those gates route you to the safe version, NOT to the backlog. Doing-now shrinks the backlog and is the surest way to not lose things.

## 📋 Backlog / TODO / Task / "what's next" questions → `PLAN.md`

Same SoT as Session Protocol above: `PLAN.md` at repo root (projects → tasks → ETA + status; the long-horizon launch lives there as dated tasks). Run `python scripts/check_plan.py --today` for the day's plan. Only `data_gated_reviews.yaml` retains separate runtime behavior (YAML predicates, weekly auto-surface) and it references #IDs back into PLAN.md.

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
harness UTC date). Mechanical backing: `check_plan.py` compares ETAs in PT (not ET); a SessionStart hook
injects the PT date each session. [[feedback_operator_timezone_pdt]]

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

## Code Layout
```
core/          orchestrator.py, router.py, context.py, memory.py, confirmations.py
agents/
  market_intelligence/
    agent.py           # execute_task() routes by keyword
    db.py              # All DB queries — single source of truth for schema
    rs_engine.py       # RS scoring (~9700 stocks)
    ep_detector.py     # MAGNA53 EP scoring + Claude + Perplexity validation
    theme_engine.py    # Theme discovery, dedup, lifecycle
    briefing.py        # Briefing formatters + send_telegram_message
    scheduler.py       # APScheduler jobs
    system_audit.py    # L1/L2/L3 anomaly + invariant scans
    audit_invariants.py # Shared invariant library (used by readiness_check.py)
    broker/
      entry_pipeline.py # Single funnel for ORB bracket entries (MAGNA53 + 9M Day 2)
      ...
channels/      telegram.py, webhooks.py
shared/        models.py, registry.py, secrets.py
```

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
- Bottom-up from price action — themes emerge from RS, not hypotheses
- Lifecycle: Nascent → Accelerating → Mainstream → Fading → Retired (5 fading days)
- **Engine-drop themes skip Fading**: Pass1 cap_drop / Pass1.5 absorption removals get a synthetic Retired row (`theme_auto_retired` audit; `parent_theme=successor` recovered from the pass audit events) — the 5-day Fading→Retired path can't complete under the 7d recency cap. Stub until canonicalization (R3).
- **Validation**: `_validate_theme_membership()` runs Mon/Wed/Fri. `_extract_json_object()` is depth-aware (handles nested JSON Haiku appends). Concurrency capped via `_VALIDATION_SEMAPHORE(2)` + retry-once on 429.
- **`mi_theme_exclusions`**: user-directed permanent bans ONLY. NOT auto-populated from validation removals (deliberately — a bad-description removal once permanently banned TSEM from semiconductor theme).
- **Fading themes**: tickers from Fading themes ARE in `covered_tickers` — prevents validation-removed stocks appearing as uncovered in the same run.
- **Post-assignment validation**: immediately validates newly assigned stocks (don't wait for Mon/Wed/Fri).
- **Birth validation (#266, 2026-06-17, operator-signed)**: newly DISCOVERED themes run the SAME `_validate_theme_membership` on their founding members before `_save_themes` — discovery previously skipped it, so bad members sat ~6d until the next Mon/Wed/Fri (evidence: `docs/analysis/theme_birth_validation_evidence_2026-06-17.md`). Changes WHEN, not WHAT; min-survivor guard keeps small/born-bad themes intact; emits `theme_birth_validated`.
- **Tool schemas**: all three tools (assignment, discovery, split) have `analysis_scratchpad` as required first field — forces reasoning before JSON output.
- **Unknown sector fallback**: when sector is "Unknown", checks description keyword overlap (4+ letter words) before allowing assignment.
- **Description chunking**: `_ensure_descriptions()` sends max 15 tickers per Haiku call.
- **`get_active_themes(stale_after_days=7)`**: recency cap is the de-facto retirement mechanism — themes that stop appearing in daily snapshots age out after a week.

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
- **`broker/entry_pipeline.py::submit_trade_entry`** — single funnel for both MAGNA53 EP and 9M Day 2 entries. Strategy differences (stop source, sizing) inject via `spec_builder` callback. Pipeline owns: dedup → safeguards → bar-fetch retry → fade guard → spec build → per-strategy sizing multiplier → DB insert → Alpaca submit → audit log → Telegram. **Contract: every terminal failure Telegrams via `humanize()`.**
- `account_mode` resolved at safeguard step from `strategy.phase` via `resolve_account_mode_for_strategy()` and threaded through spec_builder, alpaca client calls, DB inserts, and Telegram surfaces. SpecBuilder type alias takes account_mode as 4th positional arg.
- Bounded action vocabulary: `ACTION_AUTO_ENTERED / PROPOSED / AUTO_ENTER_FAILED / PROPOSAL_SEND_FAILED / SKIPPED / BLOCKED`.
- Bounded skip-reason vocabulary in `broker/skip_reasons.py` — 19 constants across `filter:* / setup:* / block:* / infra:* / window:*`. Aggregate via `split_part(skip_reason, ':', 1)`. New: `block:strategy_position_cap` for per-strategy slot limit (#65).

### Dual-Account Architecture (#66, 2026-05-10)
**One Apollo container, two Alpaca accounts** (paper + live), routed per-strategy via `mi_strategies.phase`:

| phase | live_real_enabled | account_mode | Submit destination |
|---|---|---|---|
| shadow | – | (n/a) | No submit; audit telemetry only |
| paper | – | paper | Alpaca paper account (real fills, fake $) |
| live | False | live | 🟡 STAGED-PAPER Telegram proposal; no auto-submit |
| live | True | live | Alpaca live account (real fills, real $) |

**Key components:**
- `constants.resolve_account_mode_for_strategy(strategy)` — SSoT mode resolver. Pre-dual-account global `current_account_mode()` kept for non-trade contexts (`/status`, boot audit).
- `alpaca_client.get_trading_client(account_mode)` — per-mode TradingClient singletons, independent HTTP sessions (no shared pool). Every wrapper accepts optional `account_mode`.
- `alpaca_client.make_client_order_id(account_mode, strategy_id, ticker)` — strict mode-bound `apollo_{mode}_{strategy}_{ticker}_{ms_epoch}` format. **Required at every order submission site** to prevent cross-account COID collisions.
- `trade_stream.py` — two TradingStream instances (one per mode), each handler closure-bound to its account_mode. `_dispatch_trade_event` runs `_verify_event_account_mode` before any DB mutation; mismatches drop the event + emit `cross_account_event_rejected` audit (defense in depth even with mode-bound COIDs).
- `_check_safeguards(account_mode, signal_type)` — per-mode isolated (paper at-cap doesn't constrain live). Per-strategy `max_concurrent_positions` enforced WITHIN per-mode envelope. NULL = share global cap.
- `sync_positions()` iterates `['paper','live']` (or `['paper']` if `ENABLE_LIVE_MODE=false`) — runs `_sync_positions_for_mode(account_mode)` per mode. Each mode's mi_live_trades query carries `AND account_mode = $1`.
- `account_equity_snapshot_job` (16:12 ET) iterates both modes; drawdown breaker state per mode (`mi_safeguard_state` PK = `(safeguard, account_mode)`).

**Boot bootstrap** (`agent.py::_bootstrap_alpaca_credentials`):
- `ENABLE_LIVE_MODE=true` (default): hard-requires `ALPACA_PAPER_API_KEY/SECRET` AND `ALPACA_LIVE_API_KEY/SECRET`. Boot-blocks if either pair missing.
- `ENABLE_LIVE_MODE=false`: only `ALPACA_PAPER_*` required. Strategies at `phase='live'` blocked. Dev / single-account opt-out.
- Legacy `ALPACA_API_KEY`→paper remap still in code (`legacy_alpaca_creds_fallback` audit; was "one cycle only" from 5/10 — removable).
- Post-init `verify_dual_account_clients()` smoke-tests both accounts, emits `dual_account_boot_verified` (success) or `dual_account_boot_failed` (per-mode error detail).

**Per-strategy sizing/cap** (#65, two new mi_strategies columns):
- `position_size_multiplier NUMERIC DEFAULT 1.0` — applied in entry_pipeline AFTER spec_builder so it covers both `prepare_orb_order` AND `prepare_9m_day2_orb_order` uniformly. Multiplies shares; recomputes position_size + risk_dollars.
- `max_concurrent_positions INT NULL` — per-strategy slot cap. NULL = share global `MAX_CONCURRENT_LIVE_POSITIONS`. Use case: 9M Day 2 starts at multiplier=0.5 + cap=2 when promoting to live.

*(The 3 correctness invariants — mode-bound COID, cross-account event rejection, `account_mode` filter on every trade query — are the facts already stated in Key components above; this is the safety backbone, don't relax any of the three.)*

### Stop-Leg ID Capture
- `alpaca_client.extract_stop_leg_id(order)` is the canonical helper — uses `stop_price` as primary signal, case-insensitive `"stop" in type_str` fallback. Robust against Python 3.11+ Enum stringification (`str(OrderType.STOP)` → `"OrderType.STOP"`).
- Used in: `place_bracket_order` (naked-order guard), `submit_entry`, `check_fills`, `attempt_day1_reentry`, `_process_entry_fill`. Never re-implement the loop.
- `_process_entry_fill` checks 3 sources before remediation: WS event legs, DB `stop_order_id`, REST refetch.

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
- Safeguards (SSoT `docs/setups/safeguards.md`): max 5 positions (`MAX_CONCURRENT_LIVE_POSITIONS`), 2% daily loss limit, tiered drawdown breaker (active 2026-06-03). Count-based circuit breaker (10 losses) is DEPRECATED — superseded by the drawdown breaker.
- Kill switch: `LIVE_TRADING_ENABLED=false` (boot-read) · `/pause` (instant runtime halt, #345)

### Telegram Formatting
- NEVER use pipe tables — Telegram can't render them. Use monospace code blocks.
- `send_telegram_message` in `briefing.py`. Returns False on failure (never raises).
- Escape dynamic strings before passing with Markdown mode.
- Skip-reason machine prefixes (`infra:subscribe_timeout: ...`) → run through `humanize()` before user display. DB keeps machine prefix; user sees prose.
- Reserve Telegram for terminal/actionable events. Self-healing/transient → `mi_audit_log` only.

## Daily Schedule (ET)
| Time | Job |
|---|---|
| 7:00 AM | EP scan starts (every 5 min) |
| 9:00 AM | Morning briefing |
| 9:31 AM | ORB monitor — bracket orders |
| 9:35 AM | Stop refresh Day 2+ |
| 10:00 AM | EP scan stops + ORB unfilled-entry cleanup |
| 3:45 PM (mon-fri) | **Partial-exit scan** (`partial_exit_scan` — Day 3-5 partial-profit; runs intraday so the stop-replace settles same day instead of parking in `pending_replace` after the close, #361 split from the 4:45 job) |
| 4:05 PM | EOD cleanup |
| 4:10 PM | EOD EP recap (HIGH outcomes + feed telemetry) |
| 4:15 PM | **Post-EOD audit** (L1 invariants + trade-side L2/L3) |
| 4:25 PM (mon-fri) | **EP Judge delta digest** (`_judge_delta_digest_job` — PUSH of the holistic judge's promote/demote deltas vs the floor; subtitle reflects shadow-vs-load-bearing toggle; empty day → no Telegram; #240/W3) |
| 4:30 PM (mon-fri) | **News source quality drift check** (#71/#72 — audit row + 24h-dedup Telegram if drift) |
| 4:45 PM | Position update (SMA trail + stop updates + daily summary — partials moved to the 3:45 scan, #361) |
| 4:55 PM (mon-fri) | **Time-stop scan** (9M Day 2 meanderers ≥5 trading days + peak excursion <+3%; operator-confirm via `/timestop TICKER`, #91) |
| 9:35 AM–3:55 PM (every 5 min, mon-fri) | **Intraday flag-break scan** (shadow — catches the moment a TIGHTENING/COILED/TRIGGERED ticker breaks above base_high with volume confirmation; `/flagbreaks`, #94) |
| 9:00 AM–4:45 PM (every 15 min, mon-fri) + boot | **Order-status reconcile** (DB↔Alpaca silent-stop catcher; `order_status_reconciled` audit row on divergence, audit-only #123) |
| 4:00 PM (mon-fri) | **9M EP Pace EOD digest** (whole-day pace/anticipation rollup, dedup vs same-day actuals, cap 20; #133, hourly→EOD 2026-06-07 — actual 9M still rides the per-5-min digest) + **Entry-technique EOD digest** (`run_intraday_signals_eod_digest` — roll-up of the 5 intraday shadow detectors, replacing ~23/day per-tick pings now default-off; #168) |
| 5:00 PM | Data pull — RS + regime + themes + missed-EP refresh + error check |
| 5:22 PM (mon-fri) | **Sugar Babies cohort refresh** (Pradeep persistent watchlist — observational, `/sugarbabies`) |
| 5:25 PM | **Continuation flag scan** (shadow — VCP/Qullamaggie tightening) |
| 5:30 PM | **Post-nightly audit** (theme/cooldown/regime L2/L3) |
| 6:00 PM (Fri) | **Friday watchlist** (curated chart-review aggregator + TV import block) |
| 8:00 PM | Evening briefing |
| 9:00 PM | **Evening position backstop** (2nd `sync_positions` — catches late EXPIRED events) |
| 2:00 AM | **Baseline refresh** (rebuild `mi_metric_baselines` 30d trailing) |
| Sun 8:00 AM | Weekly system self-audit (7d metrics + L3 drift roll-up + news-source-quality section → Telegram digest) |
| Monthly 1st 6:00 PM | **Monthly backward-check sweep** (regime-shift monitor — re-runs #50/#53/#54/#77 + news quality 90d view) |

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

### 2026-07-05 — day 3: hardening lane CLEARED (sprint CLOSE)

- #225 ([5l/7] demotion-fence gate) · #382 (money-path swallows resolved, baseline 95→81, zero control-flow) · #184a coverage-drift detector · F10 shared client · #256 restore-check + watchdog crons (**run-1 caught the dashboard_ro DR roles gap** → roles.sql now rides the encrypted bundle) · #417 pass-1 (→37.8k). Lessons: fence dynamic text in Telegram legacy-Markdown (an unpaired `_` silently 400s the alert); 3 shell-helper copies drifted same-day → `infra/ops_lib.sh`.

### 2026-07-04 — day 2: #347 FLIPPED LIVE · axes built

- **#347 flip live** + same-day hardening · ADRs 0015/0016 signed, #328 shadow deployed · 8 reviews closed · labels banked · #381→95.

Older entries → `CHANGELOG.md` (search any concept).

---

## Adding a "Changes Made" entry
Keep new entries in **Recent** section above. After ~2 weeks, compress each entry to a single bullet (`topic — key change & lesson`) and **graduate it into `CHANGELOG.md`** — don't keep the compressed form in this file. Drop "Files Changed" lists (git tells you that), drop "Post-deploy verification" once verified, drop manual cleanup SQL once applied. **⚠ Always leave ≥1 dated `### YYYY-MM-DD` entry in Recent** — `system_audit._recent_changes_context` (the Sonnet-hypothesis input) + its smoke test (`test_system_audit_recent_changes`) require it; graduating the LAST entry empties the section and reds CI (2026-06-19). A docs-only push skips the pre-push pytest gate, so this only surfaces in CI — run the test before a CLAUDE.md graduation.

Older history: see `CHANGELOG.md` (compressed log, on-demand only — not auto-loaded). For genuinely architectural decisions where the *why* outlives the code, optionally write a short `docs/decisions/NNNN-topic.md` ADR.

Target CLAUDE.md size: under 30k chars. Hard ceiling: 40k (warning threshold).
