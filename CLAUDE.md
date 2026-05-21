# Apollo the Wise — Claude Context

## Session Sync Protocol
At the start of every session: `git pull origin main`
Read "Changes Made — Recent" sections to understand prior sessions.
Older session details live in git history; see compressed log below for a roadmap.

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
- **Tables**: `mi_9m_ep_alerts` (intraday), `mi_9m_sugar_babies` (EOD confirmed; carries 6 going-in shape columns + `_shape_tag()` bucket)
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
| 4:45 PM | Position update |
| 5:00 PM | Data pull — RS + regime + themes + missed-EP refresh + error check |
| 5:25 PM | **Continuation flag scan** (shadow — VCP/Qullamaggie tightening) |
| 5:30 PM | **Post-nightly audit** (theme/cooldown/regime L2/L3) |
| 6:00 PM (Fri) | **Friday watchlist** (curated chart-review aggregator + TV import block) |
| 8:00 PM | Evening briefing |
| 9:00 PM | **Evening position backstop** (2nd `sync_positions` — catches late EXPIRED events) |
| 2:00 AM | **Baseline refresh** (rebuild `mi_metric_baselines` 30d trailing) |
| Sun 8:00 AM | Weekly system self-audit (7d metrics + L3 drift roll-up → Telegram digest) |

## Production Deploy
- Server: `ssh apollo@87.99.134.162`, dir: `/home/apollo/apollo_the_wise/`
- Service names: `orchestrator`, `market-agent`, `postgres`, `redis`, `uptime-kuma`

**Canonical deploy command** — preflight is chained inside the script so the deploy fails loudly if entry-pipeline safeguards can't authenticate. **Use the script, not raw `docker compose` commands.** The 2026-05-13 outage was caused by deploying without the verification step.
```bash
# Market agent only (default):
bash scripts/deploy.sh

# Both services:
bash scripts/deploy.sh both

# Orchestrator only:
bash scripts/deploy.sh orchestrator
```

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

### 2026-05-17 (Sun) — Track 1 trade-state ownership refactor + Gate 5 G column-write authority preflight (live-cutover blocker closed)

**Trigger**: Five trade-state corruption bugs in May (CRMD/KLAR/ARM/BW/AIXI), same root cause every time — multiple writers to the same column with no ownership rule, last-write-wins by accident. Friday's Phase 1 audit (`docs/architecture/trade-state-ownership.md`) enumerated every writer; Sunday Phase 2 refactored three hot-path bug surfaces + shipped the static-analysis gate. Gate 5 G was the final unshipped Gate 5 deliverable — composite `live_cutover_decision` review now has all four gates ready for 2026-05-22 evaluation.

**Three refactors shipped** (atomic commit chain — each deployed + Gate 5 B prepare validation re-verified between commits):
- **T1.1** (commit `68096bc` + fixup `223ec92`) — `trade_stream._process_entry_fill` no longer writes `stop_price` / `hard_stop`. Entry-fill is NOT the authorized writer; INSERT at `entry_pipeline._skip` sets initial value, `update_stop()` owns trail. KLAR/ARM bug root cause. Cuts stop_price writers 7→4. Param count 6→5.
- **T1.2** (commit `67c3257`) — `live_tracker.update_open_positions_live` partial-fired branch no longer writes `stop_price`. `update_stop()` at the same call site is the authorized writer; when it FAILED (returning False + nulling stop_order_id per naked-position protocol), the wrapping write previously falsely reported a stop_price the broker no longer held. Cuts 4→3. Param count 4→3.
- **T1.4** (commit `f3539d2`) — `live_tracker.update_open_positions_live` no-partial branch no longer writes `stop_price`, `total_pnl`, `partial_taken`, or `remaining_shares`. In this branch `step.new_X == state[X]` (no change when no partial fires), so the "idempotent no-op write" was actually a LOST UPDATE hazard if a WS fill arrived concurrently between state-load and UPDATE. Cuts 3→2 effective. Param count 8→4.

**Gate 5 G ship** (commit `fd31e5b`):
- `scripts/audit_column_writes.py check` mode + `ALLOWED_WRITERS` dict (35 columns) + `deploy.sh` step `[5c/5]` wire.
- Walks every UPDATE/INSERT site touching `mi_live_trades`, fails deploy non-zero on any (column, function) pair not in `ALLOWED_WRITERS`. Exit code 6 reserved.
- Synthetic violation test PASSED (rogue_writer correctly flagged with full diagnostic output).
- End-to-end exit-code test PASSED (check returns 1 on violation, 0 on clean — triggers `deploy.sh exit 6`).
- Friction by design: adding a new writer requires updating `ALLOWED_WRITERS` in the same commit. Explicit ack.

**Gate 5 G retroactive coverage walked** (`gate_5g_historical_coverage` data-gated review closed same day):
- 1 of 5 May bugs caught: BW under today's narrowed partial_taken allow-list.
- Other 4 are different bug classes covered by different gates: CRMD → Gate 5 B prepare validation; KLAR → wrong-value-by-authorized-writer (no current gate); ARM → routing/SELECT (purpose-tagged orders, shipped); AIXI → cross-table.
- Gate 5 G is necessary but not sufficient. Future-work proposal: "value-invariant" Gate 5 H for sensitive columns (`stop_price > 0`, `stop_price < entry_price` for long, `hard_stop <= stop_price`, etc.). Defensive belt-and-suspenders. Not blocking live cutover.

**Deferred to next session**:
- T1.3 — `live_tracker.update_open_positions_live` close path delegation. Complex (WS-vs-fallback ownership for Alpaca-confirms-gone case). ALLOWED_WRITERS entry is TEMPORARY pending T1.3 ship.
- T1.5a — `set_stop_order_id` helper consolidation. 12 solo writes (not 24 as originally framed). Per advisor: cosmetic-not-safety; Gate 5 G's enforcement value identical with or without.

**Discipline that worked at hour 3+ of fatigued architectural work**:
- Advisor consult before EVERY commit (not just at start + end)
- Deploy + Gate 5 B prepare validation between EVERY commit (catches issues before compounding)
- Atomic commit-per-refactor (T1.1 → T1.1 fixup → T1.2 → T1.4 → T1.5+SSoT)
- Honest scope reduction when investigation surfaced complexity (T1.3 deferred mid-session per drop-priority)

**Lesson**: a column-ownership bug class needs a column-ownership gate. Type-mismatch (Gate 5 B), wrong-value (no current gate), routing (purpose-tagged orders), and ownership (Gate 5 G) are DIFFERENT bug classes that need DIFFERENT gates. Single-gate thinking ("Gate 5 G will catch all DB write bugs") is wrong; layered-gate thinking is right. Today's three refactors + Gate 5 G close the multi-writer ownership class; the other classes are addressed elsewhere.

### 2026-05-14 (session 6) — 3 bugs fixed in parallel + recurring "DB tracks attempt not outcome" pattern surfaced

User flagged three issues; all three diagnosed + shipped + reconciled in one session:

**Bug 1: Phantom split check formula error (broadest impact, 10 tickers affected)**

`splits_ingest._apply_one` checked `close_pre / close_post ≈ split_from / split_to` from Polygon's `adjusted=true` fetch. **The math is wrong for adjusted-feed data**: with `adjusted=true`, real splits have pre-split bars RE-ADJUSTED to current units, so `close_pre / close_post ≈ 1.0` (not 20 for a 20:1 reverse). Phantom splits also yield ~1.0 (no adjustment applied either way). The check couldn't discriminate, and EVERY real split since 2026-05-08 ship was wrongly flagged phantom and skipped. 10 tickers affected: AIXI/ASBP/DKI/KALA/SMX (5/11), BNZI/CVNA/OLOX (5/08), MHVIY (5/13), SLMT (5/14).

**Fix**: compare the fresh adjusted-feed pre-split close against the un-adjusted (or stale) value currently in `mi_daily_closes`. Real split → new/old ≈ split_factor. Phantom → new/old ≈ 1.0. Tight 10% tolerance because comparing same-date across two fetches. Added `_get_old_close(ticker, date)` helper.

**Damage**: AIXI's RS was scored at 100 with 2-week of "below SMAs" actually showing $0.60-$1.60 raw vs corrected $12-$15 adjusted. CVNA similarly. Downstream: every detector reading `mi_daily_closes` (RS, EP, parabolic, theme) for these 10 tickers used wrong-units data for up to 6 days.

**Reconciliation**: `scripts/_reconcile_2026_05_14_bugs.py` reset `adjustment_applied=FALSE` on the 10 split rows and called `_apply_one` with the fixed check — all 10 successfully wrote 79-173 adjusted bars each. AIXI's 5/05-5/14 closes now show coherent $16.20 → $12.20 → $11.73 progression matching the user's "trending down" observation. Tomorrow's nightly RS scoring will use correct data.

**Bug 2: BW pre-fill state mutation (`live_tracker.py:591-602`)**

Post-close partial-profit logic at 16:45 ET submitted 3 orders to Alpaca (cancel old stop, partial sell 387, new stop 776) — all `ACCEPTED`, queued for next-day open. `execute_partial_exit` correctly deferred state mutation to the WS fill handler. **But the wrapping UPDATE at lines 591-602 wrote the optimistic `step` outcome unconditionally**: `partial_taken=TRUE`, `total_pnl=$1613.79`, `remaining_shares=776`. Then `sync_positions` later overwrote `remaining_shares` back to 1163 (broker truth) but didn't touch `partial_taken` or `total_pnl`. Result: Frankenstein row showing partial-done + realized P&L + full open shares.

**Fix**: when `step.partial_fired=True`, skip partial-specific fields in the UPDATE. Only update stop_price, hold_days, running_closes. The partial-specific fields will be populated by `finalize_partial_exit` on actual WS fill.

**Reconciliation**: reverted BW #119 to `partial_taken=FALSE`, `total_pnl=0`, `exits=[]`. Tomorrow's WS fill will repopulate correctly.

**Bug 3: SNDK theme misclassification (operational)**

2026-05-14 nightly theme run moved SanDisk from `AI Memory & Storage` to a new theme `Semiconductor Front-End Interconnect & Wafer Processing Equipment`. Wrong — SanDisk = memory products. Manual reassignment via SQL (remove from wrong) + `assign_ticker_to_theme` (add to correct). Filed `theme_assignment_sndk_class_refinement` review to diagnose the assignment mechanism and ship a structural fix.

---

**Recurring architectural pattern** (now sub-weekly cadence; flagged by advisor):

| Date | Bug | The flag/field tracked... | ...instead of the actual outcome |
|---|---|---|---|
| 2026-05-04 | `update_stop` audit | "we tried to update stop" | "stop is actually placed" |
| 2026-05-07 | `splits_ingest` premature-apply | `adjustment_applied=TRUE` "step ran" | "data is correctly adjusted" |
| 2026-05-13 | strategy `phase='live'` redefinition | "row says phase=live" | "Alpaca client for live mode exists" |
| 2026-05-14 (CRMD) | `_process_entry_fill` UPDATE | "UPDATE statement issued" | "DB matches broker fill state" |
| 2026-05-14 (BW) | `step.new_partial_taken` | "decision logic said partial" | "broker actually filled the partial" |
| 2026-05-14 (AIXI) | phantom check `expected_ratio` | "ratio formula matched a constant" | "Polygon actually applied the adjustment" |

Same shape every time: a flag/field semantically named for the OUTCOME (data adjusted, position filled, mode active) but mechanically gated only on the ATTEMPT (procedure ran, decision made, formula matched).

**Prophylactic discipline** (going forward, especially before live cutover):
- Every new boolean flag on a hot-path table needs a paired invariant query that surfaces the row state when the flag's mechanical condition is met but the semantic outcome ISN'T.
- Boot-time UPDATE prepare validation (Gate 5 deliverable B from CRMD post-mortem) addresses one slice. The broader principle: distinguish "we ran the step" from "the outcome is correct" by validating outcome state in a separate query, not by trusting the flag.

### 2026-05-14 (session 5) — EP selectivity review expanded to be exhaustive (user mandate)
User pushed back on initial review: needs to be MORE exhaustive, include every tracked variable already in code — specifically called out 5-min ORB shadow (`mi_orb_shadow_trades`) which has parallel telemetry running since shipped earlier this year.

Expanded the review to cover **6 lettered sections of dimensions** (was 5 numbered):
- **§A — Existing entry filters** (17 items: gap floor, RVOL@T anchors, pm-shares floor, ADV/mcap/ATR floors, extension cap, cooldown, M&A filter, stop-too-wide, fade guard, ORB window, position cap, daily-loss/circuit/drawdown — note these are gates not selectivity dials per se)
- **§B — Existing scoring weights** (12 items: gap pts, catalyst pts, rel_vol pts, neglect pts, vol conviction, analyst upgrades, low float, bull regime mult, perplexity mult, score threshold, earnings boost, MODERATE→HIGH override)
- **§C — Entry-mechanic dimensions** (7 items: 5-min vs 1-min ORB, re-entry attempts, stop placement source, sizing, order type, ORB cutoff, fade guard tier)
- **§D — NEW filter dimensions** (7 user-specified items: fundamentals magnitude, gap-above-MAs, gap-above-congestion, round-number distance, base shape, 52w-high distance, multi-quarter context)
- **§E — Setup-context dimensions** (5 items: theme membership, sector rotation, COILED overlap, 9M Day 2 comparison, missed-EP outcomes per skip-reason)
- **§F — Already-shipped recent gate changes to evaluate** (5 items: hedge-phrase downgrade, earnings boost, cooldown bypass, re-entry gap-through, pm-shares carve-out)

**Phase 1 expanded** to produce a master cohort table joining `mi_ep_alerts × mi_ep_scan_log × mi_live_trades × mi_ep_scan_outcomes × mi_orb_shadow_trades × mi_ep_missed_outcomes × mi_themes × mi_flag_candidates × mi_daily_closes`. Output: `docs/decisions/0003-ep-selectivity-overhaul.md` with cohort breakdowns + recommended filter set + scoring weight adjustments.

**Phase 1 deliverables broken into 5 substeps**: P1.1 master cohort, P1.2 per-dimension outcome breakdown, P1.3 new-dimension feasibility prototypes (D1-D6), P1.4 catalyst-prose labeled training set (~400-500 alerts hand-labeled), P1.5 score-weight recalibration via regression.

**Earliest review date**: 2026-05-17 (Friday). User signaled "tomorrow or over the weekend" → 5/15-5/17 window for Phase 1.

**Cross-references to existing reviews documented** in YAML to avoid duplication (`stop_too_wide_outcome_cohort`, `orb_cutoff_extension`, `adv_probe_retirement`, `conviction_floor_extension`, `perplexity_hallucination_keyword_leak`).

**Scope discipline warning embedded**: "this review is EXHAUSTIVE intentionally — but not every dimension ships. Phase 1 picks ~3-5 highest-signal dimensions. Avoid scope creep — shipping all 30+ filters at once is overfit and unsupportable."

### 2026-05-14 (session 4) — Filed EP selectivity deep-dive review (user mandate: rare EPs, not 100+/quarter)
User flagged that EP detection is over-firing during earnings season. Past 10 trading days: **87 HIGH alerts** (8.7/day average; 11 on 5/14 alone). Almost all graded `catalyst_quality='strong'` — near-zero `game_changer` discrimination. Extrapolated: ~180/month → **~550/quarter** vs the methodology-correct "handful per quarter."

NBIS example: 700%+ annual revenue growth = textbook game-changer, but (a) was filtered by the M&A direction-blind bug (fixed earlier today) AND (b) would have only been graded `strong` not `game_changer` by current LLM grader. The grader doesn't see fundamentals magnitude.

Filed `ep_selectivity_deep_dive` data-gated review with phased plan:
- **Phase 1 — diagnostic baseline**: cohort outcome distribution by score_tier × catalyst_quality, gap-size buckets, pm_rvol buckets, catalyst-prose labeled training set
- **Phase 2 — shadow filter telemetry**: 30 days of `ep_selectivity_filter_shadow` audit events; measure alert reduction ratio + win-rate on shadow-admitted cohort
- **Phase 3 — ship**: N≥20 shadow settled with measurably better R-expectancy

Selectivity dimensions to investigate (user-specified):
1. **Catalyst quality grading — fundamentals magnitude** (revenue growth tier, guidance raise, margin inflection — likely needs structured earnings data fetch, not just LLM-grading press release)
2. **Gap size tiers** — non-linear scoring (25%+ structurally different from 10%+)
3. **Technical structure** — gap above MAs, above congestion, distance to round numbers, prior base shape, distance from 52-week high
4. **Volume conviction floors** — raise pm_rvol min from 1.0× to 5×+
5. **Multi-quarter context** — EPs off bases vs extended uptrends (current `neglect_period` scoring is loose)

**Working hypothesis** (test before shipping): fundamentals-magnitude filter alone might drop alert volume 80%+ while keeping the best setups (NBIS-class). Technical structure adds modest further selectivity. Volume + multi-quarter are tiebreakers.

**Relation to live cutover**: NOT a hard blocker, but if Gate 3 paper_r_expectancy stays red (cohort -$2,041 over 4 trades currently), this review is the natural unblock path. Even if Gate 3 turns green at current selectivity, completing this review reduces live-$ risk meaningfully.

**Earliest review date 2026-05-21** (gated on 100 EP alerts + 30d paper trade history — both metrics likely met by then). Predicate counts EP scans + closed paper trades in lookback windows.

### 2026-05-14 (session 3) — P&L attribution column to exclude CRMD bug damage from methodology metrics
User flagged that the CRMD bug damage will distort P/L performance reviews. Shipped a generic exclusion mechanism rather than ad-hoc adjustments:

**Schema**: `mi_live_trades.pnl_attribution TEXT` (nullable, idempotent migration). NULL = methodology (default). Non-NULL names the incident (`'incident_2026_05_14_naked_position'` for CRMD #137 today). Account equity still reflects actual -$778 hit; only methodology-evaluation queries filter on this column.

**Filter applied to** (methodology evaluation):
- Gate 3 `paper_r_expectancy_validation` predicate + action SQL
- `system_review.py::_aggregate_postmortem_narratives` (weekly digest best/worst)
- `system_review.py::_aggregate_loser_breakdown` (weekly loser deep-dive)

**Filter NOT applied to** (account safety + accounting visibility — must reflect reality):
- `daily_loss_limit` safeguard (live_tracker.py:226)
- Daily Telegram summary (live_tracker.py:673)
- `/status`, `/pnl`, `/trades` user commands
- Account equity / drawdown breaker

**Why this shape over alternatives**: (a) preserves account-truth in the row; (b) one query filter applies uniformly to all methodology analytics; (c) explicitly names the incident in the column value — auditable years later; (d) handles future incidents the same way without code changes.

**Pre-fix cohort impact**: CRMD's -$778 was ~-$220 methodology + ~-$558 bug damage. Gate 3 cohort now reads -$2,041 methodology vs -$2,599 actual. Still deeply negative, but methodology evaluation is no longer distorted by bug damage going forward.

### 2026-05-14 (session 2) — Post-mortem filed + Gate 5 live-cutover blocker
Following the CRMD incident, formal post-mortem document `docs/incidents/2026-05-14-crmd-naked-position.md` written: full timeline, 5-whys, damage assessment, what-went-right/wrong, action items §6, sign-off §8. Filed as P0 live-cutover blocker.

**Gate 5 added to `live_cutover_decision` review** (`data_gated_reviews.yaml`): NO strategy may promote to `phase='live'` + `live_real_enabled=True` until 5 deliverables ship + verify:
- (A) Naked-position remediation: when entry-fill UPDATE raises ANY exception, IMMEDIATELY submit a fallback stop-market at `trade["orb_low"]` BEFORE any other action. Emit `naked_position_remediation_fired` audit event.
- (B) Boot-time DB UPDATE prepare validation: extend preflight to walk every parameterized UPDATE via `connection.prepare(sql)`. Deploy blocks on `AmbiguousParameterError` etc.
- (C) Escalated naked-position alert for `partial_fill` (fill already shipped 96fd7ee).
- (D) Stuck-fill watchdog cron: every 60s during market hours, surface `entry_order_id IS NOT NULL AND status='filling' AND filled_at IS NULL AND created_at < NOW() - INTERVAL '2 min'`.
- (E) Regression pytest for schema column-type additions against mi_live_trades.
- (F) Operator sign-off on post-mortem doc.

**Verification protocol** (must pass before status=done on `crmd_naked_position_postmortem_2026_05_14` review):
1. Paper-mode synthetic test: patch entry-fill UPDATE to raise AmbiguousParameterError; confirm remediation path submits fallback stop within 5s + Telegram escalation fires + DB reconciles.
2. Preflight test: insert a synthetic ambiguous UPDATE; confirm deploy BLOCKS.
3. Stuck-fill watchdog: insert a synthetic stuck row; confirm watchdog surfaces it.

**Why this gate is HARD-blocker**: live-$ projection on same setup = $5K-$25K loss per unstopped position at planned account sizes. `daily_loss_limit` doesn't catch a single naked position — it gates new entries, not exits. A runaway gap-down on one position could exceed account equity. The architectural lesson generalizes: boot-time preflight needs to walk hot DB-mutation paths, not just credentials.

### 2026-05-14 — INCIDENT: CRMD entered naked, bled to -$778 (asyncpg type ambiguity since 2026-05-10)
**Trigger**: User Telegram alert "Apollo entered CRMD this morning without a stop and now it's way below stop price!" Three stream-handler error alerts had fired earlier (CRMD/KLAR/CSCO) — "inconsistent types deduced for parameter $2 / numeric versus double precision" — but the generic error framing didn't convey "POSITION IS NAKED."

**Root cause** (commit `35c1f6c` 2026-05-10 — "Track worst-price / best-price per trade for setup-quality analytics"): added `lowest_price_seen` / `highest_price_seen` as **NUMERIC** columns and reused `$2` in `_process_entry_fill` UPDATE for them. `entry_price` is `double precision`. `$2` overloaded across both types → `AmbiguousParameterError` at asyncpg `prepare` time.

```sql
entry_price = $2,                                    -- double precision
lowest_price_seen = COALESCE(lowest_price_seen, $2), -- numeric ← collides
highest_price_seen = COALESCE(highest_price_seen, $2) -- numeric ← collides
```

**Silent damage** (4 trades since 2026-05-10 22:43 PT): every entry fill UPDATE in this window failed → `filled_at` NULL on MRAM/KLAR/CSCO/CRMD. KLAR/CSCO got into `status='closed'` via the stop-fill code path (different UPDATE, no type collision). CRMD got stuck — its OTO stop leg was canceled by Alpaca when the entry-fill WS callback threw, position became naked from 09:34 ET to 11:08 ET (1h34m).

**Damage assessment**:
- CRMD: 2214 sh, entry $8.36 → manual market SELL $8.01 = **-$778.02** (intended stop $8.45 would have lost -$220; bug cost ~-$558 extra)
- KLAR -$914, CSCO -$407 (stop-hit at proper price — bug didn't worsen these, just left filled_at NULL)
- Total day P&L: **-$2,099** → triggered daily_loss_limit safeguard ($1,897 cap), system correctly blocked further entries

**Fix** (commit `96fd7ee`): explicit `::numeric` casts on the two `lowest/highest_price_seen` assignments. `$2` now deduces to `double precision` (from `entry_price`); the casts handle conversion to numeric for the NUMERIC columns at write time. Verified live by re-running the same UPDATE shape on KLAR/CSCO during backfill — no error.

**Defensive escalation**: when `event=='fill'` exception fires, Telegram now says "🚨 POSITION MAY BE NAKED — INTERVENTION REQUIRED" with explicit broker-check instruction. Generic "Stream handler error" framing was easy to dismiss during today's incident.

**Reconciliation scripts** (kept for evidence):
- `scripts/_emergency_close_crmd.py` — submits market SELL for the naked position (used today)
- `scripts/_reconcile_crmd_close.py` — backfills CRMD row from Alpaca order data (entry_price, filled_at, exits, total_pnl)
- `scripts/_backfill_filled_at.py` — backfills filled_at on KLAR/CSCO from entry orders (separate run)

**This would have been a $5K+ live loss had it happened post-cutover.** The daily_loss_limit safeguard caught it in paper (correctly blocked at -$2,099), but a single naked position with no stop could blow through that on a one-name basis if the trade size were larger.

**Pre-live-cutover hardening to file as followup data-gated reviews**:
- `_process_entry_fill` (and other DB-mutation paths in `trade_stream.py`) should have an **explicit naked-position remediation** branch: if UPDATE raises any DB error, IMMEDIATELY submit a stop-market order at the intended stop price BEFORE any other action. Don't trust the OTO bracket to remain intact when the WS callback throws.
- Add a CI/test that exercises every `mi_live_trades.*` UPDATE statement against a fresh DB schema. asyncpg's AmbiguousParameter is a prepare-time error — discoverable by running each statement once at boot.
- Boot-time validation: `_bootstrap_alpaca_credentials` already runs at startup. Add a parallel `_validate_db_update_statements` that prepares each parameterized UPDATE without executing (asyncpg `connection.prepare()` is cheap) and refuses to start if any prepare fails.

**Lesson**: a column-type addition to a hot UPDATE path is a SCHEMA CHANGE that requires regression coverage. The bug was a parameter overload — same value passed for both a `double precision` and `numeric` column. asyncpg's prepare-time type deduction caught it correctly, but the error was thrown at first execution (entry fill), not at boot. Same shape as the 2026-05-13 outage where strategy `phase='live'` redefinition broke entry pipelines silently at first ORB attempt. Both classes are catchable by a preflight that walks every hot path at boot time, not just the credential check. The 2026-05-13 preflight (#84) was a first step in this direction — needs expansion to DB UPDATE prepare validation.

### 2026-05-13 (session 7) — Theme orphan_sub remediation (parent dropped → sub survives top-level)
Followup on yesterday's session 6 — filed `theme_orphan_sub_mechanism` review then immediately worked the fix. 7 firings in 14d, all oil/E&P sector: parent theme (Hydraulic Fracturing / Permian E&P) dropped during merge or cap stage while sub-theme survives with stale `parent_theme` reference. Today's case: sub `Independent E&P Operators` [37 oil tickers] points at parent `Hydraulic Fracturing & Well Completion Services` (last seen 5/11 with the same 37 tickers — semantically the same theme renamed by Sonnet).

**Fix** (`theme_engine.py::_emit_pipeline_diagnostic` orphan-detection block): after the audit event fires, mutate the orphaned child in place to clear `parent_theme=None` AND drop the entry from the `sub_theme_parents` dict (caller-mutating, so the next-stage diagnostic sees the cleaned-up state and doesn't re-fire). Sub-theme survives as a top-level theme; only the broken metadata is lost. Function docstring updated from "Non-mutating" to "diagnostic + bounded orphan remediation" with rationale.

**Why option (b) clear-parent_theme over (a) block-parent-drop or (c) drop-orphan-along-with-parent**: (a) is too coupled to merge/cap logic (each stage has valid reasons to drop themes); (c) loses real information (the E&P sub is a valid theme on its own merits). (b) is defensive and generic — handles ALL orphan classes (rename-induced AND real-merge-induced) uniformly.

**Separate review filed** `canonicalize_ticker_set_evolution`: surfaced while diagnosing — `_canonicalize_theme_names` uses `DISTINCT ON (name) ORDER BY name, theme_date ASC` (earliest snapshot per name) which misses ticker-set evolution cases. The earliest `Hydraulic Fracturing` snapshot had 5 tickers (4/23); today's `Independent E&P Operators` has 37 tickers matching the 5/11 `Hydraulic Fracturing` snapshot. Canonicalize misses because the EARLIEST snapshot doesn't share today's ticker set. Proper fix would query all snapshots, group by `frozenset(tickers)`, pick earliest unique name. Threshold N≥3 distinct days observed via a new probe event; earliest review 2026-06-01. Separate scope because it touches the canonicalize SSoT helper and needs its own backtest + advisor consult.

**C2 stays closed** — advisor confirmed: the C2 framing ("find mechanism cited by ≥2 incidents") was about the cross-run probe over-emission (which IS noise). The canonicalize gap is a different finding that surfaces only on close inspection of specific cases. Don't reopen C2 — file separately.

**Lesson**: a diagnostic that's purely "audit-only" leaves the bad state in the pipeline for downstream stages. Sometimes the right pattern is "audit + bounded remediation" — fix the local symptom uniformly while filing the root cause for proper investigation. Same shape as the 2026-05-04 update_stop audit + null-stop_order_id remediation: audit captures the failure class, but the remediation is what lets reconciliation continue working downstream.

### 2026-05-13 (session 6) — Theme `cross_run_dup_candidate` was over-firing (no fix needed); filed orphan_sub separately
C2 diagnostic walk on `theme_engine_dup_incident` review (10 days of probe events, threshold 2). 60d audit walk surfaced that the YAML's premise was wrong — **the "incidents" weren't incidents.** Zero true same-day dups exist (`mi_themes` has 0 `(theme_date, ticker_set)` pairs with multiple names in 14d; `theme_save_dedup` audit event has 0 firings in 60d). The probe `theme_cross_run_dup_candidate` was emitting 7-9 "candidates" per day, all canonicalization-handled and most being false positives — fires whenever a ticker set has had a different name in 14d, even when today's name IS the earliest canonical and `_canonicalize_theme_names` correctly leaves it alone.

Worked through the data: for AMD/ARM/MRVL, today's name `Custom AI Silicon...` matches the earliest canonical (4/29, used 11 of 13 days). The 5/12 `AI Datacenter Silicon` rename was the one-day anomaly. Canonicalize correctly kept today's name unchanged. Probe still flagged it. Same shape for DOCN/FSLY, ONTO/TER, ADEA/RYAM, and the 5 other "candidates" today. The "10 incidents" were noise.

**Action**: per the YAML's hard rule "no semantic fix until ≥2 incidents agree," zero incidents = zero fix. Just renamed the misleading probe event:
- `theme_cross_run_dup_candidate` → `theme_name_variant_observed` (honest semantic: "Sonnet name-drift telemetry"). Same data, accurate name. Summary text reframed as informational.
- Docstring rewrites explain why the probe over-emits and points to `theme_save_dedup` as the TRUE dup signal (which is correctly silent because canonicalize works).
- YAML review closed with full diagnostic outcome.

**Filed separately as new data-gated review** `theme_orphan_sub_mechanism`: 7 firings of `theme_orphan_sub` in 14d. Real bug — parent theme dropped during merge/cap leaves sub-theme stranded with `parent_theme` referencing a name not in the final list. Today: sub=`Independent E&P Operators` parent=`Hydraulic Fracturing & Well Completion Services` (parent dropped). Threshold N=14 already met; earliest review 2026-05-13 — predicate met but the right next step is reading the merge/cap code to identify the dropping branch (block parent-drop when sub references it / promote orphan / drop both — three candidate fixes).

**Advisor blocked the obvious "telemetry fix"** (silencing the probe when canonicalize would handle): the cross-run probe's current over-fire is conservative (false-positive nuisance, not false-negative blind spot). Replacing it with a tighter predicate trades a known nuisance for an unknown blind spot. Renaming is the lowest-risk move — preserves visibility into Sonnet drift rate while honest about what's reported. The TRUE dup signal (`theme_save_dedup`) was already in place since the safety net at theme_engine.py:836; we just hadn't been reading it as the right alarm.

**Lesson**: an audit event's NAME shapes how operators triage it. `theme_cross_run_dup_candidate` (with "dup" in the name) read as an active problem and accumulated a 10-day "incident" framing in the YAML review. The same data renamed `theme_name_variant_observed` reads correctly as informational drift telemetry. Naming carries authority — keep audit names honest about what they actually represent, especially when downstream tooling/YAML/digests will cite them verbatim. Same shape as the 2026-05-07 splits_ingest premature-apply lesson: a flag that names the PROCEDURE (we ran the check) rather than the OUTCOME (the data is consistent) silently misleads downstream readers.

### 2026-05-13 (session 5) — #46 theme assignment silent_stop fix (max_tokens + prompt restructure)
**Root cause** of the 2026-05-09 user-flagged under-anchoring (MU/SNDK/MRAM/SIMO/MXL missing from themes despite top-30 RS): `max_tokens=1000` truncated Sonnet's response BEFORE the `assign_stocks_to_themes` tool call could emit. Pattern surfaced by the silent-skip telemetry that shipped 5/9 (commit 6647669) — 5/12 and 5/13 both fired `assignment_silent_stop` with `advisor_calls=0` and response text "I'll systematically analyze each uncovered stock..." (21 candidates × ~50 tokens of inline analysis = ~1050 tokens, exhausting the budget). The 5/11 successful run with `advisor_calls=3, proposed=0` confirms the loop itself works when Sonnet routes through advisor instead of inline analysis — Sonnet's reasoning path is temperature-variant.

User-reported tickers (MU/SNDK/MRAM/SIMO/MXL) all anchored to AI Memory & Storage + AI Datacenter Optical Transceivers themes by 5/13 via manual `/theme assign` + subsequent nightly runs. Coverage gap closed before the fix shipped.

**Fix** (`theme_engine.py::_assign_uncovered_to_themes`):
(A) `max_tokens` 1000 → 4000 — headroom for scratchpad + verbose runs, prevents future truncation as universe grows.
(B) Prompt restructured: replaced "Before calling X, ask yourself..." (which invited pre-tool free text) with explicit "Do NOT write any free-text analysis before your tool call. All per-ticker reasoning belongs INSIDE the `assign_stocks_to_themes` tool's `analysis_scratchpad` field." Advisor consultation reserved for genuine ambiguity (2+ plausible themes / ambiguous description) — preserves the 5/11 working pattern where Sonnet uses the advisor for hard calls.

**Monitoring**: watch `assignment_silent_stop` count over next ≥7 days. Zero events = fix worked. Reappearance = look at structural loop changes (retry on silent_stop). YAML review `theme_assignment_telemetry_review` closed with full diagnostic outcome.

**Lesson**: an LLM tool-use loop without sufficient `max_tokens` headroom fails silently — the response gets truncated mid-stream, the tool_use block never materializes, the code-side "no tool call" branch treats it as legitimate "no proposals" rather than truncation. Same shape as the 2026-05-07 splits_ingest premature-apply bug: a flag (here, "Sonnet didn't call the tool") tracked the procedure-ran outcome rather than the semantic outcome (here, "the response wasn't truncated"). Defensive headroom + telemetry to detect the failure are both required. Advisor's recommendation to also restructure the prompt (B) was the structural fix — A alone would fail again at larger candidate-pool sizes.

### 2026-05-13 (session 4) — 9M sugar baby M&A coverage closure (WEN-class) + stop_too_wide cohort review filed
Followups from morning's M&A filter ship. **Coverage gap surfaced by WEN 5/13**: take-private rumor was correctly filtered on EP path (10× `mna_filter_fired` audit events) but the same name passed 9M sugar baby logging on 5/12 EOD and surfaced as a Day-2 ORB candidate on 5/13. Entry attempt only failed on `setup:faded_from_orb` shape rejection (coincidence — if WEN had held ORB high, system would have entered a take-private target with no follow-through available). Grep confirmed `is_likely_ma` not called in `ninem_detector.py` or `broker/entry_pipeline.py` — 9M Day 2 path had zero M&A coverage.

**Fix** (`ninem_detector.py::run_9m_eod_sweep`): added `is_likely_ma` check between destroyed-name trend gate and `insert_9m_sugar_baby`. Polygon-news-only path (9M is pure-quant, no LLM catalyst grading); 21-day lookback (matches flag detector). Fail-open on news fetch error — don't block sugar baby on Polygon outage. Emits `mna_filter_fired (9m_sugar_baby)` audit event. SSoT updated: `docs/setups/ninem.md` change log.

**Intraday 9M scan (`run_9m_scan`) intentionally NOT filtered** — informational alerts only, no trade triggered directly. Filed as future scope if intraday FP becomes an issue.

**Tier A telemetry reviews verified + closed** (`data_gated_reviews.yaml`, commit 113f0db):
- `dead_zone_telemetry_smoke` — all 4 writers populating (3541 scan_log rows / 0 NULL, 330 multi-row pairs, 63 alerts with detected_at, 587 outcome rows through 5/08)
- `fishhook_v3_first_eod_pass_verify` — EOD pass running daily 17:20 ET with state transitions firing (5/13: new_pending=6, invalidated=1, reclaimed=5, promoted=5); registry seeded phase=shadow
- `ep_adv_probe_volume_sanity` — emit path proven on 5/06 (1131) / 5/07 (922) in expected 400-1000/day range; thin days are universe-width driven (not a code bug). Recalibrated downstream `adv_probe_retirement` gate to cohort N≥30 instead of absolute 50/day floor.
- `ftre_partial_trail_verification` (GATE 2 live cutover) — predicate tightened to `partial_taken=true` (exits>=2 had false-positive on re-entry cases like MRAM 5/11). Status stays pending until a real partial-then-trail completes in paper.

**`stop_too_wide` cohort review filed** (`data_gated_reviews.yaml`): N=2 cases (STRL 5/05 +17%/+22% 5d, AIP 5/13 today). Per `feedback_sample_size_discipline` N=2 is below the N≥10 backtest threshold, so file rather than ship. Threshold=10 settled cases (≥20d outcomes) before review; predicate joins `mi_live_trades.skip_reason LIKE 'setup:stop_too_wide%'` to `mi_ep_missed_outcomes` for forward returns. Decision matrix in YAML: 5d hit-rate ≥30% + median max_high_5d ≥+8% → revisit (widen multiple / change stop anchor / score-conditional looseness); below those bands → keep. Earliest review 2026-06-13.

**Lesson**: a filter applied at one detector site but not its sibling sites is a coverage gap waiting to fire. Today's WEN-class was caught by the EP path while the 9M Day 2 path silently allowed it through — same as 2026-05-04 update_stop audit-logging gap and 2026-05-06 stale `stop_order_id` cleanup. When a SSoT primitive exists (`ma_filter.is_likely_ma`), every actionable detector path should call it; sibling-site coverage audit should be standard practice when shipping a filter ship.

### 2026-05-13 (session 3) — M&A filter direction-blindness: NBIS-class FP (drop bare "acquire"/"acquisition")
User flagged NBIS not flagged as EP today despite +15.79% gap, pm_rvol 6.4×. Audit log surfaced 10 `mna_filter_fired` events between 7:55 and 9:31 ET — every catalyst text described **NBIS as acquirer** (bought Eigen AI for $643M) but `ma_filter._MNA_KEYWORDS` matched bare `"acquire"` / `"acquisition"` regardless of direction. Direction-blind substring scan is the bug class.

**90d backtest** (90d `mna_filter_fired` audit events, bare `acquire`/`acquisition` matches): 16 distinct tickers — **13 false positives** (NBIS, WAT, MNST, FOUR, RKLB, IREN, VEEV, KGS, NXT, PINS, QBTS, QUBT, RAL) and **3 nominal TPs** where:
- EBAY → caught independently by Claude `catalyst_quality='mna'` classifier branch (LLM understands direction)
- WEN → recovered by adding `"take-private"` and `"private deal for"` keywords (Trian buyout rumor)
- GLIBK → keyword accidentally matched in unrelated biotech chatter (Perplexity returned "no info on GLIBK"); structurally a FP that landed on a real target by coincidence

**Fix** (`ma_filter.py`): dropped `"acquisition"` and `"acquire"` from `_MNA_KEYWORDS`; added `"take-private"` and `"private deal for"`. Other keywords (`buyout`, `takeover`, `merger`, `halper sadeh`, `to go private`, etc.) spot-checked across 90d and retained — true-positive yield holds. Inline comment documents the NBIS-class trigger.

**SSoT updated**: `docs/setups/magna53_ep.md` change log entry covers full ledger (TPs, FPs, evidence, anticipated effect, reversion-flag=REFINEMENT). Filter is also gated for flag/9M/convergence detectors via same SSoT — fix applies uniformly.

**Filed followup** (not addressed today): Perplexity hallucination leak. RAL/P caught by `merger`/`strategic transaction` keywords matched not against actual catalyst content but against "no info found... nearest match is X" filler text Perplexity returns when ticker is unknown. Separate bug class; affects every detector that feeds Perplexity output to keyword scanners. Lower priority (N=2 in 90d).

**Lesson**: a keyword-substring filter that gates trade entry must be **direction-aware**, especially for verbs whose object switches sides (acquire X vs acquired by X). The fix shape generalizes: when a substring is grammatically ambiguous about which party is which, replace it with the unambiguous phrasings (`"to be acquired"`, `"bought by"`, `"taken private"` — passive voice = ticker is target). Same shape as past SSoT lessons where a flag tracked "we ran the step" rather than "the outcome is correct" (2026-05-07 splits_ingest premature-apply, 2026-05-04 update_stop audit, 2026-05-06 stale stop_order_id).

### 2026-05-13 (session 2) — Preflight smoke test (#84) + #10 STRL/EVER outcome
**#84 ship** (commit `face09d`): new `scripts/preflight_check.py` walks every enabled non-shadow strategy through `_check_safeguards` (the exact code path that fires on real ORB entries — auth, account fetch, position cap, daily loss, drawdown breaker). Run as the final step of every deploy touching broker / strategies / safeguards / alpaca_client / entry_pipeline. CLAUDE.md "Production Deploy" section updated with the command.

Two preflight bugs the first run caught (both fixed in `face09d`):
1. `docker exec` subprocesses don't inherit the boot-time `ALPACA_API_KEY → ALPACA_PAPER_*` remap. Preflight now calls `_bootstrap_alpaca_credentials()` itself so the legacy fallback fires in the subprocess too — otherwise it false-alarms on a healthy container.
2. Initial version printed "PREFLIGHT OK" even when every strategy was BLOCKED by `setup:account_fetch_failed`. Added `_BENIGN_BLOCK_PREFIXES = ("block:",)` so only the proper portfolio safeguards (max positions, daily loss, circuit breakers, drawdown breaker) count as benign blocks; anything `setup:*` / `infra:*` is treated as an infra failure that fails the preflight.

Verified end-to-end on prod: both `magna53` and `9m_day2` now report PASS via the preflight after the morning outage was fixed.

**#10 closure** — STRL/EVER 5d outcomes (5/05 alerts, both rejected by `setup:stop_too_wide`):
- **STRL**: open $727 → 5d close $851 (**+17.0%**), 5d max $889 (**+22.2%**). Stop-too-wide rejected a clean winner.
- **EVER**: open $19.09 → 5d close $19.12 (**+0.2%**), 5d max $23.98 (**+25.6%**). Move was real intraday but fully gave back.

STRL is the trigger condition for #11 (Reconsider ATR Part 2 — fires when stop_too_wide rejects a winner). Filing for later investigation; one case (N=1) is not enough to ship a methodology change per `feedback_sample_size_discipline`, but it IS enough to start tracking the pattern.

### 2026-05-13 — Outage: every paper trade failed with `'ALPACA_LIVE_API_KEY'` KeyError (seed × dual-account mismatch)
**Incident**: 9:31 ET ORB monitor logged `0 entered, 10 skipped` across AMBQ/HLIT/PACS/SE/SIBN/TE/VG/VPG/VSTS/ZBRA. Every HIGH alert blocked with `setup:account_fetch_failed: 'ALPACA_LIVE_API_KEY'`. Live paper-trading completely down for the morning session. User flagged: "this could easily be prevented with proper test and validation."

**Root cause** — three-layer bug:
1. `_seed_strategies_registry()` (db.py:103-155) seeded magna53 and 9m_day2 with `phase='live'`. Pre-dual-account-architecture this meant "submit to the single Alpaca account configured by ALPACA_PAPER env var" (implicitly paper).
2. The 2026-05-10 dual-account ship (#66) **redefined** `phase='live'` to mean the literal LIVE Alpaca TradingClient. `resolve_account_mode_for_strategy()` now returns `'live'` for those rows.
3. Container runs with `ENABLE_LIVE_MODE=false` (per #68 deploy plan) → `ALPACA_LIVE_API_KEY` env var never set. `get_trading_client('live')` → `os.environ['ALPACA_LIVE_API_KEY']` → KeyError → safeguard returns `SETUP_ACCOUNT_FETCH_FAILED` → every entry blocked.

The 2026-05-12 deploy verification (#68) confirmed container BOOTED clean but never exercised the entry pipeline on a paper-phase strategy. A boot smoke test isn't an end-to-end test.

**Immediate fix** (SQL on prod): `UPDATE mi_strategies SET phase='paper' WHERE strategy_id IN ('magna53','9m_day2');`. Restored paper trading for the next session.

**Structural fixes** (commit 78c5fa3):
- `_seed_strategies_registry()` now seeds magna53 + 9m_day2 with `phase='paper'` so fresh installs don't repeat. Existing DBs unaffected (ON CONFLICT DO NOTHING) — operator must run the SQL above. Inline comments document why the legacy default is wrong.
- **Boot consistency check** in `agent.py` post-credential bootstrap: queries `mi_strategies WHERE enabled=TRUE AND phase='live'`. If any rows exist AND `ENABLE_LIVE_MODE=false`, raises `RuntimeError` with explicit remediation (set ENABLE_LIVE_MODE=true + creds OR demote rows). Emits `strategy_phase_mode_mismatch` audit event.

**Why fail-loud instead of silent auto-downgrade**: if an operator intended to promote magna53 to live but forgot to set ALPACA_LIVE_API_KEY, auto-downgrade silently demotes the strategy and the operator never realizes. Boot-block forces explicit acknowledgment.

**Lesson**: a feature whose semantics change (`phase='live'` meant paper, now means live) needs a database migration — not just a code change. Seeds left behind in their old denomination become live landmines. Same shape as the 2026-05-07 splits_ingest premature-apply bug where `adjustment_applied=TRUE` meant "we ran the step" but the operator-visible semantic was "the data is adjusted." Re-defining a column's meaning without migrating existing values is the foundational error.

**Deploy verification gap to fix**: post-deploy verification (#68 and future) MUST include a real entry-pipeline exercise — e.g., a `/dryrun TICKER` Telegram command that walks every gate including safeguards. Today's boot smoke test confirmed credentials worked at startup; it did NOT confirm credentials worked when `_check_safeguards()` actually queried account equity. Boot ≠ runtime.

### 2026-05-11 — Missed-EP opportunity-cost telemetry (3-step ship)
New `missed_outcomes.py` + `mi_ep_missed_outcomes` table tracks every EP the system saw but didn't enter (scan_filter, MODERATE-tier, HIGH-unentered) with forward returns from gap-day open to d+1/d+5/d+20 close plus max-favorable-excursion within each window. User flagged INOD/HIMX/FTNT/DDOG/BAND/TWLO as huge winners not entered — needed systematic surface for "which gate bled the most upside" instead of single-trade anecdotes.

**Three integration points:**
- Refresh: `refresh_missed_outcomes(window_days=30)` runs after step 7 of `_nightly_data_pull` (5pm ET) — slots between `run_outcome_tracker` and `detect_state_changes`, after `mi_daily_closes` is current. UPSERT on `(ticker, alert_date, source)`; forward returns recompute each night so newly-settled d+5/d+20 bars flow into rows written when the alert fired. Emits `missed_outcomes_refreshed` audit event with per-source counts.
- `/missed [days]` Telegram: top 15 ranked by 5d (or `20d`/`1d` horizon) return. `/missed by reason` switches to per-category roll-up (n, avg ret_5d, count of ≥10% winners, top ticker). Routes before generic "why didn't we trade" single-ticker handler.
- Weekly review appendix: `_aggregate_missed_opportunities` → `format_missed_section_for_weekly` adds "🔍 *Missed Opportunities*" block right after the loser breakdown — top 5 winners we didn't enter + per-skip-reason roll-up. Methodology-tuning context lives next to the loser-side post-mortem for symmetric review.

**Skip-category buckets** (SQL CASE mirrors `_categorize_skip_reason` Python helper): `cooldown`, `score_below_50`, `pm_rvol_low`, `session_rvol_low`, `adv_low`, `atr_high`, `mcap_low`, `catalyst_downgrade`, `extension_gate`, `outside_top20`, `duplicate_scan`, `filter_other`, plus source-derived `moderate_tier` / `high_unentered`. Stable taxonomy so weekly category counts are comparable run-over-run.

**Forward-return basis: gap-day open** — measures from `open_price[alert_date]` (what a day-2 chaser would've paid) to `close[alert_date+N]`, with `max_high_5d/20d` for max-favorable-excursion. All computed as one SQL `INSERT...SELECT` with five `LEFT JOIN LATERAL` subqueries against `mi_daily_closes` — single round-trip vs N+1 per ticker.

**Backfill**: `python -m scripts.refresh_missed_outcomes 90` for immediate population on first deploy (90d window). Nightly refresh then uses the 30-day sliding window; rows older than 30d freeze once the 20d return is settled.

**Pure observability**: zero methodology change. No new entries admitted, no filters loosened. The table only records what the existing pipeline already filtered, joined to data already in `mi_daily_closes`. Exempt from the methodology-shipping freeze per `feedback_sample_size_discipline.md`.

### 2026-05-10 — Dual-account architecture #66 + per-strategy sizing #65 (BLOCKER for live cutover)
Bundled ship of two coupled changes (advisor 2026-05-10: bundle is right call since both touch mi_strategies + safeguard/sizer paths; threading account_mode hits the same call sites where sizing multipliers apply).

**#66 dual-account**: one Apollo container subscribes to BOTH Alpaca paper + live accounts simultaneously. Strategies route per their `mi_strategies.phase`: `phase='paper'` → paper Alpaca, `phase='live' + live_real_enabled=True` → live Alpaca, `phase='live' + live_real_enabled=False` → STAGED-PAPER Telegram proposal. Enables 3-tier maturation pipeline (shadow → paper → real-$) without losing real Alpaca paper execution feedback when MAGNA53 promotes to live.

Architecture (see "Dual-Account Architecture" section above for full detail):
- `alpaca_client.get_trading_client(account_mode)` returns per-mode TradingClient singletons with independent HTTP sessions
- `make_client_order_id()` enforces strict mode-bound `apollo_{mode}_{strategy}_{ticker}_{ms_epoch}` format (cross-account COID collision prevention)
- `trade_stream.py` runs two TradingStream instances; `_dispatch_trade_event` validates `mi_live_trades.account_mode == stream_account_mode` before any DB mutation; mismatches drop the event + emit `cross_account_event_rejected` audit
- `_check_safeguards(account_mode, signal_type)` per-mode isolated (paper at-cap doesn't constrain live) + per-strategy `max_concurrent_positions` enforcement
- `sync_positions()` iterates `['paper','live']` via `_sync_positions_for_mode(mode)` helper — independent reconciliation per account
- `account_equity_snapshot_job` (16:12 ET) iterates both modes → two `mi_account_equity_snapshots` rows daily; drawdown breaker state per mode

Boot bootstrap (`agent.py::_bootstrap_alpaca_credentials`) hard-requires both `ALPACA_PAPER_*` AND `ALPACA_LIVE_*` env var pairs when `ENABLE_LIVE_MODE=true`. Dev opt-out: `ENABLE_LIVE_MODE=false` requires only paper. Legacy `ALPACA_API_KEY/SECRET` remapped to `ALPACA_PAPER_*` at boot (one-deploy-cycle rollback safety; emits `legacy_alpaca_creds_fallback` audit; remove after dual-mode is stable).

**#65 per-strategy sizing/cap**: two new `mi_strategies` columns:
- `position_size_multiplier NUMERIC DEFAULT 1.0` — applied in entry_pipeline post-spec-builder so it covers BOTH `prepare_orb_order` AND `prepare_9m_day2_orb_order` uniformly
- `max_concurrent_positions INT NULL` — per-strategy slot cap. NULL = share global `MAX_CONCURRENT_LIVE_POSITIONS`
- Use case: 9M Day 2 promotes to live with multiplier=0.5 + cap=2 (smaller size, restricted slot count)

**Migration deploy steps** (Hetzner): set `ALPACA_PAPER_API_KEY/SECRET` + `ALPACA_LIVE_API_KEY/SECRET` env vars BEFORE container restart. OR set `ENABLE_LIVE_MODE=false` for paper-only (legacy `ALPACA_API_KEY` continues working as paper). Boot will FAIL with clear message if env vars missing under `ENABLE_LIVE_MODE=true`.

**All strategies stay at `phase='paper'` initially.** Verify ≥48h regression-free paper trading before flipping any strategy to `phase='live'` (this is the dual-mode validation gate, separate from the live cutover composite gate #64). Live cutover sequencing remains: drawdown breaker active → paper R+ over N≥10 → dual-account verified → MAGNA53 phase='live' + live_real_enabled=True.

**Lesson**: the cleanest place to apply per-strategy parameters (sizing multiplier, position cap) is at the orchestration layer (entry_pipeline + _check_safeguards), NOT inside each strategy's spec_builder. Single application point covers all current and future strategies. Same architectural pattern as the 2026-05-04 limit-buffer SSoT cleanup.


### Older entries graduated to CHANGELOG.md (compressed 2026-05-17)

2026-04-30 through 2026-05-08 moved to `CHANGELOG.md` with one-liner format `topic — key change & lesson`. Search there for any concept above (e.g. "Continuation Flag", "M&A filter", "split handling", "purpose-tagged stop", "drawdown breaker", "EP earnings boost", "splits_ingest premature-apply") to retrieve compressed form + git commit pointer.

---

## Adding a "Changes Made" entry
Keep new entries in **Recent** section above. After ~2 weeks, compress each entry to a single bullet (`topic — key change & lesson`) and **graduate it into `CHANGELOG.md`** — don't keep the compressed form in this file. Drop "Files Changed" lists (git tells you that), drop "Post-deploy verification" once verified, drop manual cleanup SQL once applied.

Older history: see `CHANGELOG.md` (compressed log, on-demand only — not auto-loaded). For genuinely architectural decisions where the *why* outlives the code, optionally write a short `docs/decisions/NNNN-topic.md` ADR.

Target CLAUDE.md size: under 30k chars. Hard ceiling: 40k (warning threshold).
