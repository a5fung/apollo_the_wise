# Apollo the Wise — Claude Context

## Session Sync Protocol
At the start of every session: `git pull origin main`
Read "Changes Made — Recent" sections to understand prior sessions.
Older session details live in git history; see compressed log below for a roadmap.

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
```

---

## Changes Made — Recent

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

### 2026-05-08 (session 4) — Drawdown circuit breaker shadow ship (#39)
Replaces the count-based circuit breaker with a methodology-aware drawdown-from-peak state machine. **Currently SHADOW phase** — daily 16:12 ET cron emits transition audit events; `_check_safeguards()` does not block on it. Promotes to active after ≥14d post-live-cutover telemetry by env-var flip (`DRAWDOWN_BREAKER_PHASE=active`). Plan: `~/.claude/plans/let-s-go-into-plan-glittery-graham.md`. SSoT: `docs/setups/safeguards.md`.

**Two structural flaws of count-based** (documented at length in `constants.py:37-43`): self-perpetuating (cooldown anchored to `latest_loss_at + 24h`, advances on each new loss closing in cooldown — only an open winner can break it); methodology-blind (Pradeep/Qullamaggie holds winners for days/weeks but stops losers in minutes/hours, so the trailing-N closed-trade window structurally over-weights losers and the breaker's default state is to fire).

**Architecture**: state-machine evaluated once daily, NOT per-call. Two new tables:
- `mi_account_equity_snapshots` (daily Alpaca equity per account_mode; generically reusable for analytics, /status, allocator track-record dim)
- `mi_safeguard_state` (1 row per (safeguard, mode) with state + drawdown metadata)

Daily 16:12 ET cron `account_equity_snapshot_job` runs `snapshot_account_equity` then `recompute_drawdown_state(mode)`. State transitions emit `drawdown_breaker_tripped` / `drawdown_breaker_released` audit events (single event per transition; no flood). `_check_safeguards()` in active phase does a cheap PK lookup on `mi_safeguard_state` — zero per-call compute.

**Hysteresis is state-aware** (advisor refinement): when state='OK' only the trip threshold (-5%) is checked; when state='TRIPPED' only the release threshold (-2.5%). Eliminates the `-5.1% → -4.9% → -5.1%` flap-and-spam scenario a stateless comparator would produce.

**Stale-data fail-open** (advisor refinement): if most recent snapshot is older than 48h, `sufficient_history=False` and the breaker is effectively disabled until data freshens. Protects against silent cron failures locking the system on a week-old peak. Active-phase reads see `state='OK'` because `recompute_drawdown_state` won't transition without fresh data.

**Promotion gate**: ≥14 days of post-live-cutover shadow telemetry, validated via SQL queries documented in `safeguards.md`. Acceptance: trip rate ≤ 1× per quarter, no `drawdown_check_unavailable` clusters, ≥1 release observed (proves recovery path works). Flip is a single env var change.

**Day-1 baseline seed**: `docker exec apollo-market python -m scripts.seed_drawdown_breaker` (idempotent; runs once after deploy then 16:12 cron takes over).

**Lesson**: a safeguard for a momentum strategy must be methodology-aware. "Trailing-N closed losses" was a trivially-implemented but conceptually wrong metric — the strategy's success mechanism (hold winners) created the breaker's failure mode (closed-trade window biased toward losses). The drawdown-from-peak shape uses Alpaca's mark-to-market equity which already accounts for unrealized gains — open winners lift equity, prevent false trips. Same architectural pattern as the 2026-05-04 single-source-of-truth lessons (one primitive, multiple integration points): one equity source, one peak window, one state machine.

### 2026-05-08 (session 3) — Circuit breaker threshold 5→10 (interim stand-in for drawdown-based fix)
User flagged that today's morning ORB window was blocked by the circuit breaker. Investigation surfaced TWO structural issues with the current count-based implementation that the bump alone doesn't solve, but the bump is a 5-min unblock while the proper drawdown-based replacement gets built (task #39).

**Issues** (per discussion + advisor review):
1. **Self-perpetuating**: cooldown anchored to `latest_loss_at` which advances every time another loss closes. During cooldown no new entries fire → only existing open winners can break the cycle. If they all stop out as losers, cooldown extends indefinitely until manual intervention.
2. **Methodology-blind**: "trailing-N closed trades" structurally over-weights losers because Pradeep/Qullamaggie methodology HOLDS winners until trailing stop catches them (days/weeks) while losers stop fast (minutes/hours). The closed-trade window is biased toward losses by design.

**Trigger**: 5/8 morning ORB blocked because the trailing-5 closed trades were ALL losses (AMD/ARM/TEAM/OMCL/INTC, 4/24-5/07). 6-loss streak in 14 days is not unusual in a fast-stop strategy with ~25% win rate. P(5 consec | 25%) = 24%; P(10 consec | 25%) = 5.6%. 5 was statistically too tight.

**Fix (interim)**: bumped `CIRCUIT_BREAKER_CONSEC_LOSSES` 5 → 10. Single-line constant change. Currently 7 closed trades total; len < 10 → check skipped → unblocked. When 10+ trades close, KURA's win at position 7 means `all_losses=False` → still no trip.

**Proper fix (filed as task #39)**: drawdown-based safeguard. Track account equity (realized + unrealized via Alpaca positions) over recent N days. Trip when equity drops X% from recent peak; release when drawdown recovers to within Y%. Methodology-aware (open winners' unrealized lifts equity); self-clearing (no perpetuation); magnitude-sensitive (5 small losses don't trip, 1 big one can). 4-6 hr build. Should ship before live-money cutover. SSoT location: docs/setups/safeguards.md (to be created with the build).

**Lesson**: the user observation surfaced a foundational problem, but advisor review (correctly) recommended interim threshold bump rather than disabling the safeguard entirely or jumping straight to the rewrite. Pattern: don't disable a safeguard with caveats; tune it down to non-firing while the proper fix is engineered. Daily loss limit (`DAILY_LOSS_LIMIT_PCT`) remains active as the magnitude-side backstop — count-side is what got tuned.

### 2026-05-08 (session 2) — 5/7 paper-session triage: parabolic earnings exclusion + EP earnings boost + HIMX cooldown + pm-shares floor + phantom split detection
Five additive fixes from the 5/7 paper-session debrief — see `~/.claude/plans/paper-session-5-7-triage.md`. All small, all bounded, all targeting specific user-reported missed-EP / false-climax classes.

**B. Parabolic earnings-day exclusion + days_up_streak hard gate (`parabolic_detector.py`)**: AGL flagged climax with prior_move 560% (anchored 35d back to a pre-runup low — 3-week consolidation between runup and today's earnings gap silently inflated the cumulative measure). XMTR same shape. Two additive gates added to climax tier (anticipation tier unchanged):
- `_MIN_DAYS_UP_STREAK_FOR_CLIMAX = 3` — promoted to HARD gate (was 1-of-4 burst component, AGL passed with streak=2 via gap+range+vol). XMTR had streak=3 — still passes this alone.
- `is_earnings_today` — if yfinance confirms today is the earnings date, skip climax classification entirely. Catches both AGL and XMTR. Fail-soft: yfinance error → False (don't suppress climax on data outage).
- `compute_parabolic_metrics(rows, market_cap, is_earnings_today=...)` signature extended; caller `_score()` resolves earnings_today via `is_earnings_day(ticker, trade_date)`.

**C. EP earnings-day pre-score catalyst boost (`ep_detector.py`)**: DDOG scored 30 every tick on 5/7 (gap 19-31%, pm_rvol 30-89×) — blocked by `score < 50 catalyst=routine`. AAON same (gap 11-47%, pm_rvol 32-176×). Both had earnings catalysts but the LLM classifier returned 'routine' on hedged news scrape. The existing earnings-day override at `agent.py` only fires for **MODERATE → HIGH promotion** requiring score ≥ 50 first → never fires for catalyst='routine' names since they don't reach 50. **Fix**: pre-score boost. Right after the hedge-downgrade block and BEFORE `_score_ep`, call `is_earnings_day(ticker, today)` — if confirmed AND catalyst is 'routine' or None, upgrade to 'strong'. Emits `catalyst_earnings_boost` audit event with from/to. Promotes DDOG/AAON-class names to score ~70+ → passes 50 threshold.

**D. EP cooldown bypass on fresh earnings (`ep_detector.py`)**: HIMX every tick blocked by `EP cooldown — alerted within last 60 days`. New earnings catalyst today (gap +28%, pm_rvol 65×) doesn't reset cooldown. **Fix**: bypass 60-day cooldown when `gap >= 15% AND is_earnings_day`. Earnings is structurally fresh signal regardless of prior alert (quarterly cycle). Routine post-news bumps still respect cooldown (15% gap floor + earnings_day requirement). Emits `ep_cooldown_bypassed_earnings` audit event.

**E. Pre-market shares floor relative-anomaly carve-out (`ep_detector.py`)**: AAON early ticks blocked by `pre-mkt volume X < 25,000 shares` despite pm_rvol 32-60×. Absolute floor (`MIN_PREMARKET_SHARES=25000`) is redundant with relative pm_rvol gate; low-float names always trip absolute floor regardless of relative anomaly. **Fix**: skip the absolute floor when `pm_rvol >= 5×`. Keep absolute floor as fallback for names with no pm_rvol baseline.

**F. Phantom split sanity check (`splits_ingest.py`)**: AGL `mi_splits` row reports 3/31 25:1 reverse split with `adjustment_applied=t`, but actual price data shows no break (3/31 close $7.91 → 4/01 close $9.75; would be ~$197.75 → $9.75 if real 25:1). Polygon reported the split, didn't actually execute. Yesterday's premature-apply check doesn't catch this (execution_date was real, applied_at was after). **Fix**: in `_apply_one`, after fetching adjusted history, compare `close[execution_date - 1] / close[execution_date]` against `split_from / split_to` ratio with 30% tolerance. If mismatch, emit `split_phantom_detected` audit event, skip the upsert (don't write wrong-units history), and `mark_split_applied` so we don't retry every nightly run. Operator can manually `reset_split_applied` if Polygon corrects the data.

**Lesson**: chained classifiers grading textual news (catalyst quality) silently couple coverage to one provider's blind spots. Same shape as 2026-05-04 AVNS Polygon backstop (M&A) and 2026-05-05 yfinance earnings backstop (EP). When the LLM-only pipeline admits doubt or returns nulls, the override needs a non-LLM data source whose answer is "yes/no this event existed" — not another LLM grading the same hollow input. Earnings-day check via yfinance is now wired into THREE places: parabolic climax exclusion, EP pre-score catalyst boost, EP cooldown bypass. Same independent evidence, three integration points.

### 2026-05-08 — Stop-fill state desync (ARM 5/07 + TEAM 5/06 class) — purpose-tagged routing + cleanup fix
ARM 5/07 incident: entry filled $224, stop-loss leg fired and partial-filled 87/89 sh @$219.50 (-$391.50), but `mi_live_trades` row 107 ended the day `status='cancelled'` with `exits=[]` and `total_pnl=$0` — the loss was silently dropped. Broker confirms zero ARM position; Apollo's books were lying. **User flagged as live-$ blocker.** Same bug class as TEAM 5/06 BE-stop missing exits.

**Three stacked failures:**
1. **WS partial_fill on stop-loss leg was visibility-only.** Wave 3 P0.2 telemetry handler logged the `entry_partial_fill` audit event but didn't mutate state. ARM stop sold 87/89 (odd-lot leftover never filled), so no terminal `fill` event ever came → `_handle_fill` never ran → exits never appended.
2. **WS `_handle_fill` step 2 routes by `mi_live_trades.stop_order_id` matching `status='filled'`.** Brittle when `stop_order_id` goes stale (TEAM 5/06: smaller-qty replacement stop placed without DB update propagating in time). Step 3 only routes `purpose='partial_exit'`/`'full_exit'` from `mi_live_orders` — stop legs had `purpose=NULL` → silent else branch.
3. **10:00 ET ORB cleanup overwrote the whole trade as cancelled** when the Day-1 re-entry attempt didn't fill. Cleanup queried `status='order_placed'`, didn't check whether the trade had prior fills/exits, marked status='cancelled' with empty exits[].

**Fix — purpose-tagged routing + cleanup preservation** (`broker/order_manager.py` + `broker/trade_stream.py`):

- New `finalize_stop_fill(trade_id, qty, price, order_id)` mirrors `finalize_full_exit` with `reason='stop_hit'`. Idempotent. Emits `stop_exit_committed` audit event.
- WS `_handle_fill` step 3: added `elif purpose == 'stop_loss'` branch routing to `finalize_stop_fill`. Step 2 (legacy `stop_order_id` match) still runs first for backwards compat with un-tagged historical stops.
- WS `_handle_partial_fill`: extended beyond visibility-only for sell-side legs. Claims `mi_live_orders` by order_id, routes on purpose to the matching finalizer (stop_loss / partial_exit / full_exit). Cumulative qty drives the commit. Entry-side partials remain visibility-only per Wave 3 P0.2 advisor scope.
- **Tagged all stop placements** with `purpose='stop_loss', exit_reason='stop_hit'` in `mi_live_orders`:
  - `submit_entry`: NEW — OTO bracket child stop leg now also gets a `mi_live_orders` row (was missing entirely).
  - `update_stop`: existing INSERT now tags purpose.
  - `execute_partial_exit` replacement-stop INSERT: tags purpose.
  - `execute_partial_exit` rollback-stop INSERT: tags purpose.
- **`cancel_unfilled_entries` cleanup preserves fill history**: before marking a trade `cancelled`, checks whether `exits` JSONB has any entries. If yes → status='closed' (preserve prior outcome); if no → 'cancelled' as before. Closes the ARM-class overwrite path.

**One-time backfill (prod SQL)**:
- ARM #107 patched: `status='closed'`, `total_pnl=-$391.50`, exits[] gets the missing stop_hit row.
- 3 currently-open trades (GOOGL, SMCI, FTRE) had their stop legs tagged with `purpose='stop_loss'` so the new fix applies retroactively. SMCI/FTRE had no `mi_live_orders` row at all (the OTO bracket stop-leg INSERT didn't exist before this PR).

**Lesson**: state-mutation paths in trading code must be **routable by intent**, not by identity. `stop_order_id` matching couples the routing to a single mutable column; if any path forgets to update or any race overwrites it, the routing silently fails. `purpose` tagging at placement time is durable — the order's intent doesn't change after submission. Same architectural pattern as the 2026-05-05 deferred-commit fix (`partial_exit`/`full_exit` purpose). Generalizing to `stop_loss` was the missing third leg.

**Filed followup**: trade_stream.py:367 (entry-fill stop remediation) and 600-611 (partial-exit cancel/reject restore stop) place stops without inserting `mi_live_orders` rows. Edge cases — bracket-leg-missing remediation should be rare per OTO validation, and partial-exit cancel-reject is only triggered on broker-side rejection. File for next session if either fires.

### 2026-05-07 (session 4) — `/pregame` + `/ep` show latest data with date tag (post-midnight pre-scan window)
User reported: at 12:30 AM ET on a weekday, `/pregame` returned no EPs because today (the new ET day) had no scan data yet. Existing `last_trading_day()` rolls Saturday/Sunday → Friday but doesn't catch the **post-midnight pre-scan window on weekdays** — today IS a trading day per the calendar, but the 7 AM EP scan hasn't run yet. Same shape applies to weekends and holidays — three states, one fix.

**Fix** — new resolver `db.py::latest_market_data_date(as_of)`: `SELECT MAX(d) FROM (MAX(alert_date) FROM mi_ep_alerts UNION ALL MAX(alert_date) FROM mi_9m_ep_alerts) WHERE alert_date <= as_of AND alert_date >= as_of - 14d`. Returns the actual freshest date. Cheap query — indexed alert_date column, single MAX.

**Wired sites** (`agent.py`):
- `_handle_pregame`: replaced `today_str` with `data_date` resolved via the helper. Sugar-baby today/yesterday fallback now keys off `data_date`. Header tags "_(data: Tue May 6)_" when `data_date != today`; silent when same.
- `_handle_ep_query`: replaced `last_trading_day(today)` with the resolver. Same tagging pattern. Drops the previous "showing last trading day" weekend-only note in favor of unified `data: <date>` tag.

**Generalization**: the resolver covers three states with one query — weekend, holiday, post-midnight pre-scan. Future commands following this pattern just import `latest_market_data_date` and tag accordingly. No per-handler date arithmetic.

**Verified**: at 2026-05-07 ~01:00 ET (post-midnight pre-scan), resolver returns 2026-05-06 (5/6's EP scan was the most recent) — pregame for "tomorrow" now shows 5/6 data with the date tag.

### 2026-05-07 (session 3) — Wave C #5: 9M EP per-scan digest (anticipation noise reduction)
User reported today's 9M Pace had 15+ tickers each in their own Telegram bubble. Single scan tick fired per-ticker `send_telegram_message` for every high-conviction anticipation that crossed the threshold — same shape as the per-ticker FLAG TRIGGER msgs that Wave A #4 dropped 2026-05-07.

**Fix** (`ninem_detector.py::run_9m_scan`): collect per-ticker lines into `digest_actual` / `digest_pace` lists during the scan loop. After the loop, emit ONE Telegram if either list has content. Sections by tier:

```
🏦 *9M EP — 09:35 ET*

*Actual (2)*
• `BLMN` Vol 12.3M ($246M) RVOL 4.2x $48.50 +12.5%
• `HUT` Vol 11.5M ($82M) RVOL 5.8x $7.12 +18.2%

*Pace (5)*
• `TICKER1` Vol ~15.0M proj ($45M) $48.50 +12.5%
• ...
```

Per-ticker DB inserts + `9m_ep_detected` audit events unchanged — only the user-facing Telegram is batched. Quiet scans send nothing. `_alerted_today` set still dedups across scan ticks (a ticker that fires at 9:35 won't re-fire at 9:40).

**Why digest, not threshold tightening**: the data is informational — anticipation pings are radar, not entry triggers (entries route through Day-2 ORB the next morning). User explicitly validated "digest is the right shape" in the Wave A→D triage. Same architectural pattern as the Flag Scanner's COILED digest.

### 2026-05-07 (session 2) — splits_ingest premature-apply: every split silently un-adjusted (ERNA-class data corruption)
User flagged "ERNA / VECO false climaxes" as Wave C #3. Investigation surfaced ERNA wasn't a parabolic-detector tuning issue — it was a **systemic data-integrity bug** in `splits_ingest.py`: every split row had `applied_premature=t` (apply ran *before* the split's execution date).

**Mechanism**: `get_unapplied_splits` had no filter on `execution_date <= today`. The nightly_data_pull Phase-0 splits pipeline picked up freshly-detected splits from Polygon's `/v3/reference/splits` and immediately ran `_apply_one`: re-fetch ~250d history with `adjusted=true`, overwrite `mi_daily_closes`, mark `adjustment_applied=TRUE`. **Polygon's `adjusted=true` only adjusts history for splits that have ALREADY executed** — applying a not-yet-executed split fetches un-adjusted history, marks the row applied, and never re-runs once the split actually executes. Result: pre-execution bars stay un-adjusted, post-execution daily ingest writes properly-adjusted post-split bars. Same row, mismatched units.

**ERNA 5/04 25:1 reverse split symptom**: pre-5/04 bars in DB at $0.15-$0.21 (un-adjusted; should have been ×25 → $3.75-$5.25), post-5/04 bars at $3.74-$6.04. Parabolic detector saw "+3989% prior move" and flagged climax. User's framing "ERNA's been going down for months" was correct — the apparent rally was a split-data artifact, not a real move.

**Fix** (`db.py::get_unapplied_splits`): added `AND execution_date <= CURRENT_DATE` to both query branches. Future-dated splits stay queued; they apply on/after their execution date when Polygon's adjusted feed actually reflects the split. Backfill script (`scripts/backfill_splits.py`) inherits the gate via `run_splits_ingest`, which is correct — premature applies are a bug regardless of invocation path.

**Reconciliation** (one-shot SQL on prod):
```sql
UPDATE mi_splits
SET adjustment_applied = FALSE, applied_at = NULL
WHERE applied_at < execution_date::timestamptz;
```
Resets all 15+ premature-applied rows. Splits whose execution_date has passed (ERNA 5/04, plus any with date ≤ today) re-apply on next nightly run with proper data; future splits stay queued for their own execution date.

**Verified**: ERNA pre-5/04 bars now multiplied by 25; parabolic detector no longer flags ERNA (close $6.04 / adjusted base $5.00 = +20% prior move, well below the 100%+ threshold). Wave C #3 closed incidentally — was a downstream symptom, not a gate-tuning issue.

**Affected detectors before fix**: every reader of `mi_daily_closes` — RS scoring, EP detection, parabolic, flag, friday watchlist, anything pulling daily history. ERNA-class artifacts could surface in any of them. Going forward: same data, single fix.

**Lesson**: `adjustment_applied=TRUE` was a flag on the wrong axis — it tracked "we ran the apply step" not "the data is actually adjusted." When the apply step's preconditions weren't met (split not yet executed), the flag silently lied. Same shape as past invariants that gated on procedure-ran rather than outcome-correct (the 2026-05-04 `cancel_unfilled_entries` audit-logging fix, the 2026-05-04 `update_stop` audit logging). For state-machine-style flags: the gate must reflect the *outcome*, not the *attempt*.

### 2026-05-07 — Wave B #9: TEAM attempt counter showing 1 instead of 2 (schema-migration leftover)
TEAM 5/06 /positions and /trades displayed attempt count of 1 despite the 5/01 closed row carrying `entry_attempt=2` (Day 1 re-entry: stop-out + re-entered + closed). Two distinct sites, same root cause — schema migration from old `entries` JSONB to `entry_attempt` integer column left attempt-counting on the dead column.

**Site 1 — /positions closed line** (`agent.py:4298`): `ticker_history` aggregate did `COUNT(*) AS attempts WHERE status='closed'`. Counts rows, not entries-within-row. TEAM has 1 closed row → "1 attempt".

**Site 2 — /trades row header** (`agent.py:2579, 2636`): comment "mi_paper_trades has entries column; mi_live_trades does not" already noted the schema divergence. Live path SELECTed `NULL::jsonb AS entries`, then `_attempt_count(r.get("entries"))` returned 0 → no "Nx" suffix ever rendered for live trades. User read absent suffix as "1".

**Fix**:
- /positions: `COUNT(*)` → `COALESCE(SUM(entry_attempt), 0)::int`. For TEAM: SUM=2 ✓ (verified against prod).
- /trades: added `entry_attempt` to SELECT (live: from column; paper: `NULL::int` so paper continues using `_attempt_count(entries)`). Counter prefers `entry_attempt`, falls back to `_attempt_count`.

**Filed followup**: `format_trade_attempts()` (per-attempt timeline lines under the row header) also reads from `entries` JSONB; structurally returns nothing in live mode. Out of scope for #9 — lower priority since it's display thinness, not wrong data. Could be rebuilt from `entry_attempt` count + `exits` JSONB (which carries per-attempt `attempt` keys + reason + pnl + time).

**Lesson**: a schema migration that introduces a replacement column must update every reader of the old column at the same commit. Two of three readers (`_attempt_count`, `format_trade_attempts`) were left pointing at the dead `entries` column; the third (`/positions ticker_history`) didn't reference the dead column but had its own divergent semantic (row-count instead of attempt-sum). Same shape as past SSoT slips — the right time to grep for old-column readers is at migration, not when a user notices the wrong number.

### 2026-05-06 (session 2) — Unify EP volume gate to RVOL@T (one primitive, two anchors)
HUT/BLMN/GLW HIGHs detected late at ~09:52 ET on 5/6, missing the 9:45 ORB cutoff. Investigation surfaced **three structurally distinct volume gates** in EP detection: pre-9:30 RVOL@T (pm anchor), 9:30-9:45 no gate (`compute_rvol_at_time` returned None at >=9:45), 9:45+ `today_volume / 390min_ADV` ratio vs `MIN_REL_VOLUME=2.0` (or `projected_vol_multiple` after 15 min). The post-open ratio is mathematically tiny in the first 15 minutes even on record-volume days — `today_5min_vol / 390min_ADV` is structurally < 2.0× regardless of how hot the tape is. By the time the 9:45 projection gate would have promoted them, the ORB submission window (`now_et.hour == 9 and now_et.minute < 45`) had closed.

**Discriminator validated** (Polygon minute aggs, 5/6 prod): HUT 9:31 → 7.29× session RVOL@T, BLMN 9:31 → 11.84×, GLW 9:31 → 0.72× → 9:35 → 2.41× — all clear ≥1.0× well before the cutoff.

User mandate: *"why is it so complex with 3 distinct phases and each with different criteria; if we need to distinguish than it's pre-market vs after open, that's it, having something the first 15min makes no sense at all... The concept is clear, EP comes with volume along with other criteria, how do we determine volume, figure that out and apply it. HUT is a EP, i won't accept that it didn't meet requirement first 15min, that is a clear and obvious error on the system."*

**Fix** (two surgical changes):
1. **`minute_volume.py`** — removed artificial 9:45 ET cutoff in `compute_rvol_at_time`. Both pm and session anchors are already populated by the nightly refresh for the entire 4:00-15:59 ET window. Updated docstring to reflect.
2. **`ep_detector.py`** — collapsed the conditional pre-market-only RVOL@T call AND the broken post-open `rel_volume`/`projected_vol_multiple` gate into ONE uniform RVOL@T call. Pre-9:30 → pm anchor with `today_premkt_vol = c["today_volume"]`; 9:30+ → session anchor with `today_session_vol = c["today_volume"]`. Threshold by anchor (`MIN_PM_RVOL=1.0` / `MIN_SESSION_RVOL=1.0`). Skip reasons + audit events (`FILTER_PM_RVOL_TOO_LOW` / `FILTER_SESSION_RVOL_TOO_LOW` / `ep_filter_pm_rvol` / `ep_filter_session_rvol`) distinguish the anchor. Removed unused `MIN_REL_VOLUME` constant + import.

**Re-evaluation invariant verified**: `already_today` is sourced from `mi_ep_alerts` (scored alerts only, line 643-647), NOT from `_log_filtered` (which writes to `mi_ep_scan_log`). A ticker filtered at 9:30 (e.g. GLW with 0.72× session RVOL@T) cleanly re-evaluates at the next 5-min tick when its RVOL@T clears. GLW 9:35 RVOL@T = 2.41× → would pass next tick.

**Note (filed, not blocking)**: snapshot `today_volume` includes pre-market accumulation. At 9:30:00 sharp tick (`_minutes_since_open = max(1, 0) = 1` → session branch), pre-market shares get fed into session anchor → over-passing for high-PM gappers. Error direction is permissive (favorable to user mandate), so non-blocking; can be tightened later by subtracting `pm_cum_vol` from `today_volume` if false positives appear.

**Lesson**: three structurally-distinct gates for the same conceptual question ("is volume above normal at this clock-minute") are three places for the math to drift. Two of the three were broken in different ways: the post-open ratio was structurally tiny in the first 15 min; the projection gate fired too late for the ORB cutoff. The fix is not threshold tuning — it's recognizing that `mi_minute_volume_curves` already has session baselines for the entire 4:00-16:00 window and that the existing `compute_rvol_at_time` primitive answers the volume question uniformly. Same shape as the 2026-05-04 limit-buffer SSoT cleanup (7 hand-rolled `* 1.001` sites collapsed to one helper) and the 2026-05-04 M&A filter SSoT.

### 2026-05-06 — Stale `stop_order_id` after `update_stop` failure → /trades drift + missed naked-position alerts (TEAM 5/06)
TEAM 2026-05-06: 9:32 ET partial exit filled (sold 76 @$89.51, 153 remaining). 9:35 ET `morning_stop_refresh` ran `update_stop` which cancelled the existing stop, then both `place_stop_order` attempts failed with Alpaca's "insufficient qty available — held_for_orders: 153". User reported TEAM no longer their position at the broker, but `/trades` still showed it open with no naked indicator and no stop-out Telegram fired.

**Root cause**: `update_stop` (`order_manager.py:626`) returned False after the retry exception but **never nulled `mi_live_trades.stop_order_id`** — column kept pointing to the now-cancelled old stop. Same shape in `execute_partial_exit` (line 807, place-new-stop fail) and the rollback-failed branch (line 934). Downstream consequences:
- `sync_positions` Path C orphan-remediation gated on `stop_order_id IS NULL` → never fired.
- `_handle_fill` branch 2 atomically claims via `WHERE stop_order_id = $1`; if a later closure used a different order_id (manual exit, broker risk, etc.) the match silently failed → fell through to "untracked fill" (Telegram only, no DB update).
- `/trades` rendered the position normally, masking that no broker stop was active.

**Fix** (3 sites + 1 visibility):
1. **`update_stop` retry-failed branch** — null `stop_order_id` and emit `naked_position_detected` audit event before returning False.
2. **`execute_partial_exit` place-new-stop except branch** — same null + audit event (was leaving DB pointing at the just-cancelled `old_stop_id`).
3. **`execute_partial_exit` rollback-failed branch** — null + audit event after the new smaller stop is cancelled and the full-qty rollback also fails.
4. **`sync_positions` Path C extension** — also detect non-NULL `stop_order_id` whose broker status is not in `(new, accepted, held)`. Defense in depth: if a future code path forgets to null on failure, the next 4:05 PM / 9:00 PM sync still catches it. Uses the same enum-stringification-safe normalization as `live_tracker.py:565` (#211).
5. **`/trades` view (`agent.py:_build_summary`)** — adds `stop_order_id` to the open-positions SELECT and renders `⚠️ NAKED` flag when it's NULL with live shares. Operator gets immediate visual confirmation of the unprotected state instead of inferring it from a missing Telegram.

**Why null is the right shape**: makes the DB row honest about reality. The orphan remediation (`sync_positions` Path C, scheduler.py 4:05 PM and 9:00 PM jobs) was already designed for the NULL signal — fix consolidates the failure paths to actually emit it. Doesn't change the failure semantics (function still returns False, operator still gets the original "STOP ORDER FAILED" Telegram); just lets reconciliation see the broken state.

**Lesson**: a function that returns False without normalizing its DB writes leaves callers inferring state from `None`-vs-stale-ID, and the reconciliation layer can't tell the difference. Same shape as the 2026-05-04 `cancel_unfilled_entries` audit-logging fix and the 2026-05-05 `_handle_partial_fill` visibility-only ship — terminal failure paths in trading code must (a) leave DB in a state reconciliation can act on, and (b) emit a distinct audit event that names the failure class. "Returns False on error, logs warning" is insufficient when downstream paths gate on the column value.

### Older entries graduated to CHANGELOG.md (compressed 2026-05-09)

4/30 session 1 through 5/05 session 5b moved to `CHANGELOG.md` with full one-liner format `topic — key change & lesson`. Search there for any concept above (e.g. "Continuation Flag", "M&A filter", "split handling", "stop clobber") to retrieve the compressed form + git commit pointer.

---

## Adding a "Changes Made" entry
Keep new entries in **Recent** section above. After ~2 weeks, compress each entry to a single bullet (`topic — key change & lesson`) and **graduate it into `CHANGELOG.md`** — don't keep the compressed form in this file. Drop "Files Changed" lists (git tells you that), drop "Post-deploy verification" once verified, drop manual cleanup SQL once applied.

Older history: see `CHANGELOG.md` (compressed log, on-demand only — not auto-loaded). For genuinely architectural decisions where the *why* outlives the code, optionally write a short `docs/decisions/NNNN-topic.md` ADR.

Target CLAUDE.md size: under 30k chars. Hard ceiling: 40k (warning threshold).
