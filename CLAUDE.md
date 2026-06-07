# Apollo the Wise — Claude Context

## Session Protocol (open + close — the anti-drift ritual)

**SoT for active work = the #-task tracker.** The calendar (dated/timed plan), `BACKLOG.md` (human cross-view), and `data_gated_reviews.yaml` (evidence-gated lane) all REFERENCE #IDs — they never own task state. On conflict, the #-tracker wins; reconcile the others to it. (Why: with ~7 logging surfaces and no single owner, planned work slips between them — 2026-06-01 the calendar's drawdown-breaker flip + theme-shadow verify slipped silently because nothing reconciled them.)

**OPEN** (first actions, every session):
1. `git pull origin main`.
2. Pull TODAY's calendar (operator is on **PDT** — memory `feedback-operator-timezone-pdt`; harness/git timestamps are UTC) + the `next-session-pickup` memory + read "Changes Made — Recent".
3. STATE the day's plan (timed/planned items + ready #-tasks) before reacting to the first message.

**CLOSE** (when the operator wraps, or before ending):
1. Reconcile done-vs-planned against the calendar + the day's #-tasks. If a big-rock project advanced / completed / shifted timeline, update the **Active Major Projects roster** in `BACKLOG.md` (the operator's progress + completion-timeline view). **Verify EVERY #-task opened this session is filed under a project** in `BACKLOG.md`'s "Open tasks by project" (Misc if none) — the close is the backstop, not the primary filing point (see the project-filing rule below). No loose tasks. **MECHANICAL step (not eyeballed):** refresh `.apollo_open_tasks.json` from the #-tracker (one `{"id","status"}` row per non-completed task) and run `python scripts/check_task_project_filing.py` — it FAILS on any open task not filed under a project. The pre-commit hook (Gate 2) re-runs this whenever `BACKLOG.md`/the snapshot is staged, so an unfiled task can't be committed.
2. Roll EVERY undone planned item forward — reschedule on the calendar AND/OR add to `next-session-pickup`. Name any unplanned work that displaced the plan, so nothing slips silently.
3. If code changed: `git add <files>` → commit → `git push origin main`.

**"Done" = VERIFIED-LIVE, not "deployed."** A #-task → `completed` ONLY when its effect is confirmed in production (shadow writes rows · alert fires · backup uploads · cron run checked). "Shipped/deployed" → keep `in_progress` + a verify step until confirmed. Silent-failure class this catches: gdrive backup (5/24–31), #173 theme-shadow 0-rows, FLNC-invisible — all looked done, none were.

**On-demand reconcile (operator trigger):** "**where do we stand**" (or similar) = run the OPEN reconciliation immediately, in any session phase — pull today's calendar (PDT) + `next-session-pickup` + open #-tasks + the roster, reconcile, and report true state (done / in-flight / slipped). One phrase covers every surface; the operator never has to pick "backlog vs task list." (Avoid colliding triggers like "sync"/"status" — those map to trade-state commands here.)

**Capture (operator trigger):** "**track it**" / "**track this**" = log it as a #-task immediately (the SoT). Route to `data_gated_reviews.yaml` if evidence-gated, the roster if a big-rock, or a memory if it's a fact/feedback — and confirm back WHERE it went + the #. Default to over-capturing; this is the operator's guarantee a passing idea isn't lost. (Capture should also happen automatically in-flow — this trigger is the explicit backstop for asides.)

**EVERY #-task gets a project AT CREATION — non-negotiable, not deferred to a sweep.** The moment you open a task (TaskCreate, "track it", or in-flow), file it under a project in `BACKLOG.md`'s "Open tasks by project": an existing project, **Miscellaneous** if none fits, or **propose a NEW project to the operator** if it's a genuine new big-rock. Tag the task `metadata.project` in the same action. The #-tracker owns task STATE; the project bucket is filed atomically with creation so nothing floats loose. The CLOSE ritual only VERIFIES this (backstop), it is not the primary filing point. **MECHANICAL ENFORCEMENT (shipped 2026-06-06): `scripts/check_task_project_filing.py` + pre-commit Gate 2** reconcile the open-task snapshot (`.apollo_open_tasks.json`) against BACKLOG's "Open tasks by project" and FAIL the commit on any unfiled task — the "create→file" rule is no longer prose-that-needs-memory. The one residual is "task created but snapshot never refreshed" → the CLOSE step refreshes the snapshot unconditionally, and the operator triggers CLOSE regardless (so they're never the checker). **#176's remaining piece** is the create-time bridge (a `PostToolUse`-on-`TaskCreate` hook → append `#ID` to an unfiled ledger the pre-commit refuses on) + the scheduled drift ping; not yet built (tool-hook firing for `TaskCreate` is unverified in this harness). (Why this is bolded: 2026-06-05 — 17 tasks filed since the prior sweep had NO project; 2026-06-06 — #216/#217 created with a `metadata.project` tag but absent from BACKLOG, and the OPERATOR had to catch it. A passive "a new task lands under a project" note relied on memory and failed twice — same class as the timezone bug. The CHECK existing and firing IS the codification; a paragraph alone is what failed.)

Older session details live in git history; see `CHANGELOG.md` for a roadmap.

## Default to DOING, not tracking (bias to action)

When you discover an issue or a worth-doing improvement, **default to fixing/building it in the same session.** Filing-to-backlog is the EXCEPTION, allowed only with a NAMED reason from this closed list:
1. Needs evidence/backtest we don't have yet (methodology / detection-criterion change → CHANGE_PROCESS).
2. Needs a validation that genuinely can't run now (e.g. market-hours-only) AND no safe shadow/subset exists.
3. Blocked on an unfinished piece or an operator decision.
4. A big-rock that needs its own scoping/sequencing session.

NOT reasons (these mean *just do it*): "it's late / after-hours," "it's minor/quick," "let me batch it," habit. When the FULL change is legitimately gated, **ship the SAFE SUBSET now** (shadow / telemetry / read-only analysis) and defer only the gated part — never the whole thing (e.g. 2026-06-01 cooldown: shipped the shadow now, gated only the live-flip on realized-R). This bias NEVER overrides the safety line (no bypassing safety gates, no untested trade-state, no fabricated evidence) — those gates route you to the safe version, NOT to the backlog. Doing-now shrinks the backlog and is the surest way to not lose things.

## 📋 Backlog / TODO / Task questions → `BACKLOG.md`

When the user asks about backlog, todo, tasks, what's ready, what's open,
or "what should I work on next" — consult `BACKLOG.md` at repo root FIRST.
It's the master index pointing to detail files (`data_gated_reviews.yaml`,
memory backlogs, incident docs).

Detail files retain runtime behavior (YAML predicates, memory auto-load,
etc.); `BACKLOG.md` is the cross-cutting view. When filing, closing, or
status-changing an item in its detail file, mirror in `BACKLOG.md`. If
they drift, source files own truth — but mirror back ASAP to keep the
quick-scan view honest.

At the end (if code changed):
```bash
git add CLAUDE.md <changed files>
git commit -m "Brief description"
git push origin main
```

## 🛑 Trading Setup Changes — Read SSoT First (NON-NEGOTIABLE)

**Before changing ANY detection criterion** (parabolic, EP, 9M, flag, wick, convergence, future setups) **OR portfolio safeguard** (max_positions, daily_loss_limit, circuit_breaker, drawdown_breaker, PDT — see `docs/setups/safeguards.md`):

1. **Read the setup's SSoT file** at `docs/setups/<setup>.md` — entire file, not just change log. Confirms current criteria, recent changes, and known limitations.
2. **Read `docs/setups/CHANGE_PROCESS.md`** — discipline rules including required change-log fields, reversion-flag, evidence requirements.
3. **If the change is a reversal** of a prior decision, read the prior change-log entry to understand WHY the prior reasoning was made, and articulate why it was *wrong* (not just incomplete) before reverting.
4. **HARD gates require user sign-off on the filter list.** Agent must NOT classify a filter list as "correct" / "false positive" without user judgment (see parabolic_short.md 2026-05-08 ship→revert→restore cycle — that flip-flop is exactly what this rule prevents).
5. **Backtest before deploy** for any threshold change. N≥10 historical samples evaluated. Single-case fixes ("fixed because of TICKER 5/07") flagged as such in the change log.

**Update the SSoT in the same commit as the code change.** Stale SSoT is worse than no SSoT — it'll be cited authoritatively but contradict the code.

This rule exists because we accumulated overfitting + oscillation across multiple setups before the discipline was written down (parabolic days_up_streak ship→revert→restore on 2026-05-08, theme ticker bans 2026-04-29, etc.).

## What This Is
Telegram-based personal assistant ("chief of staff") for momentum/EP trading (Qullamaggie, Pradeep Bonde, Marios Stamatoudis methodology). Routes to specialized sub-agents.

## ⏰ Time Handling — ALWAYS ET
**Rule:** every datetime/time comparison in this codebase is in America/New_York (ET). The container runs UTC; **naive `datetime.now()` returns UTC clock values with no tzinfo and silently breaks every ET-keyed comparison.** This bug class has recurred many times.

**PERMANENT FIX (2026-06-05) — root cause pinned + gated.** The recurring "wrong wall-clock time" bug was NOT a `ZoneInfo` problem (the earlier label, incl. commit `8de7849`, was wrong). It was **pytz**: `_ET` was `pytz.timezone(...)`, and a pytz zone attached via `tzinfo=` (the `datetime` constructor, `datetime.combine(..., tzinfo=_ET)`, or `.replace(tzinfo=_ET)`) silently applies the historical **LMT** offset (`-04:56` for NY) instead of EDT/EST — shifting the ORB window +56 min (#180/#183). Fixes: (1) `_ET` (`shared/dates.py`) is now `ZoneInfo("America/New_York")`, which computes the correct offset in EVERY construction path, so `tzinfo=_ET` is always safe; all module-local pytz zones migrated. (2) **Deploy gate** `scripts/preflight_datetime_hygiene.py` (`deploy.sh [5h/7]`) BANS `import pytz`, naive `datetime.now()`, and bare `.astimezone()` in `agents/ core/ channels/ shared/` — non-bypassable except a reviewed `# tz-ok: <reason>` line comment; regression-locked by `tests/test_timezone_hygiene.py` (DST-boundary asserts). **pytz is BANNED — never reintroduce it.** The gate ALSO bans `datetime.utcnow()` (→ `datetime.now(timezone.utc)`) and `date.today()` (→ `et_today()`) — all live sites migrated 2026-06-05. Offline `backtester/` is the one excluded subtree (its DB inserts are naive-UTC against `timestamp` columns). Use `# tz-ok: <reason>` only for deliberate server-paired cases (e.g. a label matching SQL `CURRENT_DATE`).

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

**Cautionary tale:** 2026-04-29 false L1 alert. `system_audit.py` passed naive `datetime.now()` (= UTC clock 20:15) to `check_job_no_show`, which compared `now_et.time() == 20:15 >= 18:30` and false-flagged `nightly_data_pull` as missing **2 hours before its actual ET deadline**. Fix was a one-line change to `datetime.now(_ET)`. Cost: one Telegram alert, ten minutes of triage. The defensive `or datetime.now(_ET)` default in the invariant didn't fire — naive dt is not None.

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
3. **Bot command list** in `channels/telegram.py::_register_commands` — `BotCommand("foo", "<short description>")`. This is what makes the command appear in the Telegram `/` menu (operator-discoverability). Multiple commands in 2026-05 shipped without this step and were invisible to the operator until called out (2026-05-24).

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
Skip sets must include common English words (OF, IN, AT, ON, BY, TO, AS, AN, OR, MY, ME, IS, IT, IF...). **Update all three skip sets** when adding words: `execute_task` routing block, `_handle_single_score`, `_handle_fundamentals_query`.

## Key Domain Concepts

### RS Scoring
- Composite = 40% × 1M + 30% × 3M + 30% × 6M percentile rank
- Universe ~9,700 stocks via Polygon grouped daily (adjusted=true always)
- Sector enrichment: only top 300 by rank get sector in `mi_stock_scores`. For theme tickers outside top 60, fetch sector from `mi_ticker_overrides` (persistent cache) via `get_sectors_batch()`.

### Theme Engine
- Bottom-up from price action — themes emerge from RS, not hypotheses
- Lifecycle: Nascent → Accelerating → Mainstream → Fading → Retired (5 fading days)
- **Engine-drop themes skip Fading**: when a theme is removed during Pass1 cap_drop (size→0 after protect_strip) or Pass1.5 absorption, `run_theme_engine` writes a synthetic Retired row directly (with `parent_theme=successor` recovered from `theme_pass1_5_absorption` / `theme_pass1_protect_strip` audit events). The normal Fading→Retired 5-day transition can't complete here — the 7d recency cap in `get_active_themes` ages the theme out of `existing` before day 5. Stub until canonicalization (R3) ships. Audit event: `theme_auto_retired`.
- **Validation**: `_validate_theme_membership()` runs Mon/Wed/Fri. `_extract_json_object()` is depth-aware (handles nested JSON Haiku appends). Concurrency capped via `_VALIDATION_SEMAPHORE(2)` + retry-once on 429.
- **`mi_theme_exclusions`**: user-directed permanent bans ONLY. NOT auto-populated from validation removals (deliberately — bad descriptions caused TSEM to be permanently banned from semiconductor theme).
- **Fading themes**: tickers from Fading themes ARE in `covered_tickers` — prevents validation-removed stocks appearing as uncovered in the same run.
- **Post-assignment validation**: immediately validates newly assigned stocks (don't wait for Mon/Wed/Fri).
- **Tool schemas**: all three tools (assignment, discovery, split) have `analysis_scratchpad` as required first field — forces reasoning before JSON output.
- **Unknown sector fallback**: when sector is "Unknown", checks description keyword overlap (4+ letter words) before allowing assignment.
- **Description chunking**: `_ensure_descriptions()` sends max 15 tickers per Haiku call.
- **`get_active_themes(stale_after_days=7)`**: recency cap is the de-facto retirement mechanism — themes that stop appearing in daily snapshots age out after a week.

### EP Detection (MAGNA53)
- Alpaca bars use feed selected by `ALPACA_DATA_FEED` env var (`iex` default; `sip` requires Algo Trader Plus subscription) — resolved by `alpaca_client.get_data_feed()`.
- **Open intensity projection**: only applied after 15 min since open (≥9:45 AM). Pre-9:45 uses raw RVOL — opening minutes are always dense and create false 30x+ projections.
- **Extension check**: uses MIN(close) over last ~5 trading days, not a single point 5 days ago.
- HIGH ≥ ep_threshold (regime-dependent) → immediate Telegram alert; MODERATE 50-69 → morning briefing
- **ORB submission window**: `now_et.hour == 9 and now_et.minute < 45`. HIGHs at 9:45–9:59 → `WINDOW_OUT_OF_ORB`. 10:00 ET cleanup job cancels any unfilled `order_placed`.
- **Fade guard** (`entry_pipeline.py::check_fade_guard`): tiered by strategy. MAGNA53 HIGH passes `fade_midpoint_ratio=None` (skipped — Sonnet+Perplexity + ATR stop width + 10:00 cleanup cover dead-cat fills). 9M Day 2 passes `0.25` (skip only if last < lower 25% of ORB). Stop-buy mechanics + 10:00 ET unfilled-cancel are the real backstop.

### 9M EP Detection (Parallel Track)
- **No LLM** — pure quantitative virgin 9M detection (Pradeep Bonde)
- **Quality gates** (target 2–5 alerts/day):
  - Price ≥ $5, dollar volume ≥ $50M (actual) / ≥ $30M already traded (anticipation)
  - Directional: gap ≥ 3% OR intraday gain ≥ 4%
  - Anomaly: effective_vol ≥ 3× ADV (unknown ADV passes; ratio — NOT a flat ADV ceiling)
  - Anticipation: ≥ 30 min elapsed, ≥ 3M shares already traded, projects to ≥ 12M
  - Range ≥ 2% intraday; prev_close ≤ 1.20× SMA-10 extension gate
- **Intraday and EOD use identical filters** — both apply 3× ADV ratio, $50M turnover, $5 price, directional conviction. Any divergence creates phantom sugar babies.
- **Sugar Baby** = 9M day + net up ≥ 3% vs prev_close + close > open + close in top 25% of range → Day 2 ORB candidate. "Green" means net up on the day (matches intraday `_MIN_GAP_PCT` floor), NOT just close > open — the latter alone admits gap-down wick-fills (e.g. WU 2026-04-24: gap −10%, recovered to net −4.6%, close > open ✓ but categorically not a breakout).
- **Stop = prior day's low** (breakout day's low), NOT ORB low or ATR-based
- **Tables**: `mi_9m_ep_alerts` (intraday), `mi_9m_day2_candidates` (EOD confirmed; carries 6 going-in shape columns + `_shape_tag()` bucket; renamed from `mi_9m_sugar_babies` 2026-05-23 #82 — the persistent Pradeep cohort is in `mi_sugar_babies_cohort` separately)
- **`mi_daily_closes`** has `open_price`, `high_price`, `low_price` — required for sugar baby filter
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
- **Legacy fallback** (one deploy cycle only): if `ALPACA_PAPER_API_KEY` missing AND old `ALPACA_API_KEY` present, remap at boot. Emits `legacy_alpaca_creds_fallback` audit + WARNING log. Remove after dual-mode is verified stable for ≥7 days.
- Post-init `verify_dual_account_clients()` smoke-tests both accounts, emits `dual_account_boot_verified` (success) or `dual_account_boot_failed` (per-mode error detail).

**Per-strategy sizing/cap** (#65, two new mi_strategies columns):
- `position_size_multiplier NUMERIC DEFAULT 1.0` — applied in entry_pipeline AFTER spec_builder so it covers both `prepare_orb_order` AND `prepare_9m_day2_orb_order` uniformly. Multiplies shares; recomputes position_size + risk_dollars.
- `max_concurrent_positions INT NULL` — per-strategy slot cap. NULL = share global `MAX_CONCURRENT_LIVE_POSITIONS`. Use case: 9M Day 2 starts at multiplier=0.5 + cap=2 when promoting to live.

**Migration deploy steps:**
1. Set new env vars on Hetzner: `ALPACA_PAPER_API_KEY`, `ALPACA_PAPER_SECRET_KEY`, `ALPACA_LIVE_API_KEY`, `ALPACA_LIVE_SECRET_KEY` (if `ENABLE_LIVE_MODE=true`) OR set `ENABLE_LIVE_MODE=false` for paper-only.
2. Restart container. Boot will fail-fast if env vars missing.
3. Watch boot logs for `dual_account_boot_verified` audit event with both equities.
4. All strategies stay at `phase='paper'` initially. Verify ≥48h regression-free paper trading before flipping any strategy to `phase='live'`.

**Critical correctness invariants:**
- Mode-bound `client_order_id`: every submit uses `make_client_order_id()`. Prevents cross-account COID collisions on concurrent same-setup submits.
- Cross-account event validation: WebSocket dispatcher refuses events whose order_id resolves to a different account_mode than the stream.
- `AND account_mode = $X` filter on every `mi_live_trades` query in trade lifecycle code.

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
- Safeguards: max 4 positions, 2% daily loss limit, 5-loss circuit breaker (1-day cooldown auto-release)
- Kill switch: `LIVE_TRADING_ENABLED=false`

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
| 4:05 PM | EOD cleanup |
| 4:10 PM | EOD EP recap (HIGH outcomes + feed telemetry) |
| 4:15 PM | **Post-EOD audit** (L1 invariants + trade-side L2/L3) |
| 4:30 PM (mon-fri) | **News source quality drift check** (#71/#72 — audit row + 24h-dedup Telegram if drift) |
| 4:45 PM | Position update |
| 9:35 AM–3:55 PM (every 5 min, mon-fri) | **Intraday flag-break scan** (shadow — catches moment TIGHTENING/COILED/TRIGGERED ticker breaks above base_high with volume confirmation; `/flagbreaks`, #94) |
| 9:00 AM–4:45 PM (every 15 min, mon-fri) + boot | **Order-status reconcile** (DB↔Alpaca silent-stop catcher; `order_status_reconciled` audit row on divergence, audit-only #123) |
| 4:00 PM (mon-fri) | **9M EP Pace EOD digest** (whole-day rollup of pace/anticipation, dedup vs same-day actuals, cap 20; #133, hourly→EOD 2026-06-07. Actual 9M still rides the prompt per-5-min digest) + **Entry-technique EOD digest** (`run_intraday_signals_eod_digest` — one roll-up of the 5 intraday shadow detectors; #168, replaced ~23/day per-tick pings now default-off) |
| 4:55 PM (mon-fri) | **Time-stop scan** (9M Day 2 meanderers ≥5 trading days + peak excursion <+3%; operator-confirm via `/timestop TICKER`, #91) |
| 5:00 PM | Data pull — RS + regime + themes + missed-EP refresh + error check |
| 5:22 PM (mon-fri) | **Sugar Babies cohort refresh** (Pradeep persistent watchlist — observational, `/sugarbabies`) |
| 5:25 PM | **Continuation flag scan** (shadow — VCP/Qullamaggie tightening) |
| 5:30 PM | **Post-nightly audit** (theme/cooldown/regime L2/L3) |
| 6:00 PM (Fri) | **Friday watchlist** (curated chart-review aggregator + TV import block) |
| 8:00 PM | Evening briefing |
| 9:00 PM | **Evening position backstop** (2nd `sync_positions` — catches late EXPIRED events) |
| 2:00 AM | **Baseline refresh** (rebuild `mi_metric_baselines` 30d trailing) |
| Sun 8:00 AM | Weekly system self-audit (7d metrics + L3 drift roll-up + news-source-quality section → Telegram digest) |
| Monthly 1st 8:00 AM | **Monthly backward-check sweep** (regime-shift monitor — re-runs #50/#53/#54/#77 + news quality 90d view) |

## Pre-commit hooks (one-time setup per clone)
After fresh clone, activate the local pre-commit gates:
```bash
git config core.hooksPath .githooks
```
Currently enforces:
- **YAML dupe-key check** on `data_gated_reviews.yaml` (mirrors deploy.sh `[5e/5]`; catches the 2026-05-24 SNDK class bug at `git commit` time instead of at deploy or runtime)

Hooks are vanilla shell + fast (<1s). Bypass with `--no-verify` only if you really know what you're doing.

## Production Deploy
- Server: `ssh apollo@87.99.134.162`, dir: `/home/apollo/apollo_the_wise/`
- Service names: `orchestrator`, `market-agent`, `postgres`, `redis`, `uptime-kuma`
- **Disaster recovery**: if the host dies, follow `docs/ops/disaster_recovery.md` (operator runbook + `infra/restore.sh` driver). RTO ~95 min. Nightly cron writes pg_dump + GPG-encrypted secrets bundle to gdrive; `_backup_health_check_job` (04:33 ET) Telegrams if either blob is stale >36h. OAuth recovery (gdrive upload failing): `docs/ops/gdrive_backup_recovery.md`.

**Canonical deploy command** — preflight is chained inside the script so the deploy fails loudly if entry-pipeline safeguards can't authenticate. **Use the script, not raw `docker compose` commands.** The 2026-05-13 outage was caused by deploying without the verification step.
```bash
# Scope is REQUIRED (no default) — #154 tier-1, so you never silently leave a
# service on stale code. deploy.sh also aborts (exit 11) if the pull brought
# changes to files owned by a service outside your chosen scope (#154 tier-2).
bash scripts/deploy.sh market-agent    # market agent only
bash scripts/deploy.sh orchestrator    # orchestrator only
bash scripts/deploy.sh both            # both services
```
Ownership map for the scope-drift guard: `channels/ core/ main.py` → orchestrator;
`agents/market_intelligence/ scripts/` → market-agent; anything else (`shared/`,
`docker/`, `requirements/`) → both. New Telegram slash commands change
`channels/telegram.py` (orchestrator-owned) → need `orchestrator` or `both`, not
the market-agent default that silently dropped `/partialnow` on 2026-05-28.

The script runs git pull → build → up → wait-for-boot → preflight in one chain with `set -euo pipefail`. Any step that fails exits non-zero (with a specific code per failure mode). The preflight (`scripts/preflight_check.py`) walks every enabled non-shadow strategy through `_check_safeguards` — the exact code path that fires on real ORB entries (auth, account fetch, position cap, daily loss, drawdown breaker). Treats `setup:*` / `infra:*` as failures; only `block:*` reasons count as pass-through. Failure here = deploy is not green.

**2026-05-13 outage would have been caught here**: magna53 + 9m_day2 at `phase='live'` under `ENABLE_LIVE_MODE=false` raised `KeyError: 'ALPACA_LIVE_API_KEY'` on `get_account('live')`. The legacy boot smoke (`verify_dual_account_clients`) didn't catch it because it only checks clients whose credentials happen to be present. The preflight exercises the strategy-driven path, which is what actually fires.

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
REVENUE_STAGE_MIN_USD=0.01  # is_revenue_stage threshold; PROVISIONAL OPERATOR PIN.
                             # Code default is $5M (conservative-block). This env
                             # override loosens to admit pre-revenue names pending
                             # backward-check evidence. 2026-05-20/21 N=2 ratchet
                             # was rolled back; N=7 clean cohort is still below
                             # ship threshold. Re-evaluate at #55 on 2026-06-20.
                             # Quarterly sweep auto-runs Feb/May/Aug/Nov 1st.
```

---

## Changes Made — Recent

### 2026-06-01 (Mon) — partial-exit hardening trio (sub-penny + false-naked + #150) + 16:45 cron RE-ENABLED

RCAT `/partialnow` surfaced a sub-penny stop bug: the stored ORB-low stop `11.955` (3 decimals) hit `replace_order` raw → Alpaca rejected (42210000) → the **atomic** replace failed leaving the old stop LIVE, but the abort handler false-flagged the position naked (the shape `replace_order`'s own comment already documented for the #136 `str(qty)` trigger). Shipped + validated (paper integration ×2, G6 ×2, 21 unit green):
- **Rounding** (`2215615`): `alpaca_client._round_stop_to_tick()` floors sub-penny stops at the `replace_order` submission boundary — the lone unrounded path (bracket/`place_stop_order`/`update_stop` already rounded).
- **False-naked** (`2215615`): `execute_partial_exit` except handler verifies `old_stop_id` liveness on the broker before declaring naked; atomic-rejection → old stop intact → calm abort (no manual-stop CTA, which risked a duplicate-stop oversell). Fail-safe to naked on verify error.
- **#150 sell-retry** (`cd7fa27`): Step-2 `place_market_sell` retries the held_for_orders share-reservation lag, narrowly matching the clean rejection only (no oversell), 3× / 0.5s.
- **16:45 `_live_position_update_job` RE-ENABLED**: paused 5/29 (#151, advisor Option D); restoration conditions met — verify-stop-live = the (a) substance, G6 (b), breaker on the `force=False` cron path (c). Banked CRSR +$1,394 + RCAT +$1,176 partials clean. **Next watch: first unattended automated partial (~FPS 6/4); breaker is the backstop.** (DB-vs-broker stop-price display drift is a known-benign residual.)

### 2026-05-29 (Fri) — #151 partial-exit hardening + #150 confirmed + #153 bot watchdog + #154 deploy guard

Push-through session closing the IBM "partial broken 2 days" P0. Detail + Monday sequence in memory `project_151_partial_exit_hardening_wip.md`; all deployed+verified on prod unless noted.

- **#151 safety TRIO** (not the originally-planned architectural split — advisor reframe: both IBM bugs were leaf-level in `alpaca_client.replace_order`, closed by G6): (1) **G6** deploy gate `scripts/preflight_replace_order_smoke.py` (deploy.sh `[5g/6]`) exercises replace_order vs real paper broker, via harness `agents/market_intelligence/integration/paper_alpaca.py`; (2) **verify-stop-live** in `execute_partial_exit` Step 1b — poll-confirm new stop live before the sell; (3) **circuit breaker** `_recent_partial_exit_failures()` (≥3/7d → refuse + Telegram; `force=True` bypass for `/partialnow`). Plus **durable integration test** `scripts/integration_test_partial_exit.py` (broker-ground-truth asserts, hardened teardown; green ×2). IBM `/partialnow` canary clean (+$226.37). **16:45 cron PAUSED until Monday**; architectural split deferred to before LIVE cutover.
- **#150 share-reservation race CONFIRMED**: Alpaca releases the share-hold ~ms after the atomic replace → immediate sell sees `available:0, held_for_orders:26`. verify-poll incidentally mitigates, not guaranteed. Explicit sell-retry fix → Monday.
- **#153 bot watchdog** (silent 7-day-outage class): `HeartbeatExtBot` writes Redis heartbeat on each successful get_updates (survives retry-forever wedge; class override — PTB 22.7 `__slots__`); market-agent `_telegram_poll_watchdog_job` (every 2 min, separate container) alarms stale>5min. Verified advances/trips/dedupes/recovers. 7d→~5min.
- **#154 deploy scope-drift guard**: no-arg deploy.sh now errors (tier-1); aborts if the pull touched files owned by a service outside scope (tier-2). Tooling — no deploy.
- **Monday opener** (memory): breaker success-aware (close-on-success, not rolling window); #150 explicit fix; grep `execute_full_exit`/`update_stop`; then re-enable cron watched. CLAUDE.md is over the 40k ceiling (pre-existing) — compress oldest Recent entries → CHANGELOG.

### Older entries graduated to CHANGELOG.md

- Compressed 2026-05-17: 2026-04-30 through 2026-05-08.
- Compressed 2026-05-24: 2026-05-10 (#66 dual-account), 2026-05-11 (missed-EP telemetry), 2026-05-13 (`ALPACA_LIVE_API_KEY` outage + M&A direction-blind + 9M sugar-baby M&A coverage + theme assignment silent_stop + theme cross_run_dup rename + preflight smoke test #84), 2026-05-14 (CRMD naked-position incident + Gate 5 + EP selectivity deep-dive + 3-parallel-bugs), 2026-05-17 (Track 1 trade-state ownership refactor + Gate 5 G column-write authority preflight), 2026-05-20 (UnboundLocalError outage + preflight `[5d/5]` import-shadowing + 4 backward-checks said don't ship), 2026-05-21 (backward-check hygiene exposed polluted-cohort verdict + 4-checks-don't-ship discipline win).
- Compressed 2026-06-07: 2026-05-22 (#109/#110 weekly-review surfacing + #92 flag-graduation NO-GO), 2026-05-23 (DR layer + #94 flag-break + #99 Stocks-in-Play Phase 1 + Polygon structural-floor), 2026-05-24 (9-commit: weekly-review + #95/#96 detectors + DR-tmpfs + #112 L3-drift + YAML-dupe gate), 2026-05-26 (#123 order-status reconcile + #122/#127/#120), 2026-05-27 (IBM partial-exit/DB mass-close incident + #142 RDW pending_new).

Search `CHANGELOG.md` for any concept above (e.g. "Continuation Flag", "M&A filter", "CRMD", "dual-account", "Gate 5", "purpose-tagged stop", "drawdown breaker", "splits_ingest premature-apply") to retrieve compressed form + git commit pointer.

---

## Adding a "Changes Made" entry
Keep new entries in **Recent** section above. After ~2 weeks, compress each entry to a single bullet (`topic — key change & lesson`) and **graduate it into `CHANGELOG.md`** — don't keep the compressed form in this file. Drop "Files Changed" lists (git tells you that), drop "Post-deploy verification" once verified, drop manual cleanup SQL once applied.

Older history: see `CHANGELOG.md` (compressed log, on-demand only — not auto-loaded). For genuinely architectural decisions where the *why* outlives the code, optionally write a short `docs/decisions/NNNN-topic.md` ADR.

Target CLAUDE.md size: under 30k chars. Hard ceiling: 40k (warning threshold).
