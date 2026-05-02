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
- **`broker/entry_pipeline.py::submit_trade_entry`** — single funnel for both MAGNA53 EP and 9M Day 2 entries. Strategy differences (stop source, sizing) inject via `spec_builder` callback. Pipeline owns: dedup → safeguards → bar-fetch retry → fade guard → spec build → DB insert → Alpaca submit → audit log → Telegram. **Contract: every terminal failure Telegrams via `humanize()`.**
- Bounded action vocabulary: `ACTION_AUTO_ENTERED / PROPOSED / AUTO_ENTER_FAILED / PROPOSAL_SEND_FAILED / SKIPPED / BLOCKED`.
- Bounded skip-reason vocabulary in `broker/skip_reasons.py` — 18 constants across `filter:* / setup:* / block:* / infra:* / window:*`. Aggregate via `split_part(skip_reason, ':', 1)`.

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
| 5:00 PM | Data pull — RS + regime + themes + error check |
| 5:25 PM | **Continuation flag scan** (shadow — VCP/Qullamaggie tightening) |
| 5:30 PM | **Post-nightly audit** (theme/cooldown/regime L2/L3) |
| 6:00 PM (Fri) | **Friday watchlist** (curated chart-review aggregator + TV import block) |
| 8:00 PM | Evening briefing |
| 9:00 PM | **Evening position backstop** (2nd `sync_positions` — catches late EXPIRED events) |
| 2:00 AM | **Baseline refresh** (rebuild `mi_metric_baselines` 30d trailing) |
| Sun 8:00 AM | Weekly system self-audit (7d metrics + L3 drift roll-up → Telegram digest) |

## Production Deploy
- Server: `ssh apollo@87.99.134.162`, dir: `/home/apollo/apollo_the_wise/`
- Market agent only: `git pull origin main && docker compose -f docker/docker-compose.prod.yml build --no-cache market-agent && docker compose -f docker/docker-compose.prod.yml up -d market-agent`
- Both services: same but add `orchestrator` to build/up commands
- Service names: `orchestrator`, `market-agent`, `postgres`, `redis`, `uptime-kuma`

## Required Env Vars
```
TELEGRAM_BOT_TOKEN, TELEGRAM_ALLOWED_USER_IDS
ANTHROPIC_API_KEY, POLYGON_API_KEY, FMP_API_KEY, PERPLEXITY_API_KEY
ALPACA_API_KEY, ALPACA_SECRET_KEY, ALPACA_PAPER=true, LIVE_TRADING_ENABLED=false
ALPACA_DATA_FEED=iex        # "sip" only when Algo Trader Plus ($99/mo) active
POSTGRES_PASSWORD, REDIS_PASSWORD, INTERNAL_API_SECRET, TRADINGVIEW_WEBHOOK_SECRET
```

---

## Changes Made — Recent

### 2026-05-01 (session 5) — `/setup TICKER` reverse-lookup detector chronology
Apollo writes per-ticker rows to ~10 detector tables (EP, 9M intraday, 9M sugar, wick, parabolic, flag, themes, live/paper trades, weekly watchlist) but no read-only surface to ask "*what did we see in $XNDU?*" The `/why TICKER` lifecycle handler covers 3 tables; `/setup TICKER [days]` covers all 10.

**Implementation**: `db.py::get_ticker_setup_timeline(ticker, days=180)` fans out 10 small per-table SELECTs in parallel via `asyncio.gather` — each subquery wrapped in its own `async with pool.acquire()` block (asyncpg refuses concurrent queries on a single Connection). Each row normalized to `{date, source, summary, priority}`; merged list sorted by date DESC then source priority (TRADE > FLAG > EP > 9M > WICK > PARABOLIC > THEME > WATCHLIST). Per-table LIMIT 50 is the safety net; **post-merge top-60 cap** is the actual digest ceiling. Latest `mi_stock_scores` row pulled separately for the RS context line at top.

**Handler** `_handle_setup_query` mirrors `/flags` ticker mode but adds: (a) `.isdigit()` token-discrimination guard so `/setup XNDU 30` parses 30 as `days` not as a ticker named `30` (clamped 1–730); (b) TradingView chart inline-keyboard button via `_send_with_keyboard` from `friday_watchlist.py` (single button since digest is ticker-scoped) — exchange resolution via `get_security_exchange_map` + `_TV_EXCHANGE_MAP`. Routing slash-prefixed (`task.startswith("/setup ")` or `"setup "`) to avoid "setup order" / "setup complete" collisions.

**Files**: `db.py` (+1 helper, ~220 LOC), `agent.py` (+1 handler ~95 LOC, +routing block, +slash dispatch entry).

**Verification**: `/setup XNDU` should show FLAG arc (4/16 WATCH → 4/30 COILED → 5/1 TRIGGERED) + WATCHLIST entry + RS context line. `/setup AAPL` → "no detector hits". `/setup XNDU 30` → 30d window. `/setup XNDU 9999` → silently clamped to 730.

**Lesson**: parallel async DB fanout in asyncpg requires per-call connection acquisition — using `async with pool.acquire() as conn:` once and gathering 10 `conn.fetch` calls raises `another operation is in progress`. Either use the per-call pattern (this PR) or call `pool.fetch(...)` directly (asyncpg shortcut, but unused elsewhere in the repo).

### 2026-05-01 (session 4) — Authoritative split handling, drop RS heuristic
XNDU (#1 RS for multiple days) disappeared from RS list on a +24% gap-up. Root cause: `MAX_PERIOD_RETURN=300` heuristic in `rs_engine.py`. XNDU listed 2026-03-27 (25 sessions of history); 1M reference close was $7.50, today $36.12 → raw_1m=+381% > 300% cap. Heuristic was designed for stale-history reverse splits (e.g. FUBO), false-positives on recently-listed verticals.

**Pre-coding verification**: confirmed Polygon `adjusted=true` adjusts BOTH price and volume on `/v2/aggs/.../range/1/day`. TOUR (10:1 reverse 2026-04-22): pre-split adjusted close $0.65→$6.51 (×10), volume 235,767→23,576 (÷10). Post-split bars identical in both modes. No volume-handling code needed.

**Implementation (Option B — authoritative ingest, drop heuristic)**:
- `mi_splits` table (PRIMARY KEY ticker+execution_date, idempotent `adjustment_applied` flag).
- `splits_ingest.py` — Phase 0 of nightly_data_pull. Fetches `/v3/reference/splits` (paginated via `next_url`) since `today-60d`, upserts new rows, then for each unapplied row: re-fetches ~250d daily aggs with `adjusted=true`, overwrites `mi_daily_closes` via new `upsert_ticker_history` (close + volume overwritten, OHLC COALESCEd), `mark_split_applied`. Concurrency `Semaphore(5)`. Audit events: `split_detected`, `split_applied`, `split_apply_failed`, `splits_ingest_summary`.
- `rs_engine.py` — `MAX_1D_RETURN`/`MAX_PERIOD_RETURN` skip blocks **deleted**. Replaced with non-blocking `rs_extreme_return` audit event when a ticker clears 100% 1d or 300% period — surfaces splits-ingest regressions without dropping the ticker.
- `scripts/backfill_splits.py` — one-shot reconciliation, `--days N --reset --ticker TOUR`. TOUR is the positive-control verification target.
- `db.py` — five new helpers (`upsert_split`, `get_unapplied_splits`, `mark_split_applied`, `reset_split_applied`, `upsert_ticker_history`).

**Pipeline order**: splits_ingest runs BEFORE `ingest_daily` so cached history is post-split-adjusted before today's grouped daily lands. Failure is non-fatal — RS still scores; unapplied rows queue for next night.

**Lesson**: heuristic stand-ins for missing data sources eventually misfire on the exact pattern the system was built to catch. The 300% cap was indistinguishable from "recently-listed momentum vertical" — the very signal Apollo's RS engine exists to surface. Fix is always the authoritative source (Polygon splits API), not a tighter threshold.

### 2026-05-01 (session 3) — Stop-remediation hardening + fishhook EOD pass fix

**Fishhook EOD fix** (`db.py:1840`): `operator does not exist: date >= interval` — Postgres inferred `$1` as interval. Fix: `$1::date - INTERVAL '60 days'`.

**Stop-remediation pattern is correct as-is.** Bracket OTO entries are `TimeInForce.DAY`; child stop_loss inherits DAY, Alpaca auto-expires at 4:00 PM, our 4:05 PM remediation re-issues GTC. The 5-min "unprotected" window is post-close — retail stops don't trigger extended hours. `StopLossRequest` has no TIF field (parent-controlled); place-then-cancel at fill time is rejected because child reserves the qty. Keep design, ship three hardenings.

1. **Alert downgrade** (`trade_stream.py:440`): branch on `event_norm`. `expired` → ℹ️ "EOD stop expired (expected)". `cancelled`/`rejected` mid-session → ⚠️ unchanged.
2. **Bounded retry** (`order_manager.py:931`): orphan `place_stop_order` retries 3× with 2s/4s backoff. Was single-shot.
3. **Evening backstop** (`scheduler.py`): new `_evening_position_backstop_job` at 21:00 ET mon-fri. 2nd `sync_positions` pass after extended hours + all nightly jobs done. Catches late WS `EXPIRED` events that landed after 4:05 PM scan + retry-exhausted failures. Closes gap before next-day open.

**Lesson:** "Position unprotected" wording made an expected EOD pattern read like a live-fire incident, competing for attention with real cancellations. Branch on event type. Also: verify a "common pattern" is mechanically safe before adding paranoid plumbing — parent-TIF design was fine; only the post-4:05 race needed covering.

### 2026-05-01 (session 2) — Continuation Flag Detector (TI-class shadow ship)
Plan: `~/.claude/plans/shiny-mapping-locket.md`. New strategy `flag_continuation` — multi-stage daily detector for post-runup VCP / Qullamaggie tightening flags (XNDU 9-session base after 4/16 high-volume pivot, breakout 5/1). Five stages: `unqualified → WATCH → TIGHTENING → COILED → TRIGGERED` + `INVALIDATED`. Anchored per-ticker to a **pivot-high bar** (highest-volume session within 5% of 25d max-high) so detection works relative to each ticker's own base — user-stated: *"It's not the same criteria each day."*

**Three semantic calibration fixes from XNDU replay** (real fixes, not threshold tweaks):
1. **Proximity anchors on `pivot_close`, not `pivot_high`** — XNDU 4/16 was blow-off shooting-star (high $42.44, close $32.67, 24% wick). Pivot-high anchoring would structurally veto any base forming beneath the wick.
2. **State gates use closing extremes** — TRIGGERED: `close > max(close)` over base; INVALIDATED: `close < min(close)`. Early-base intraday wick (XNDU 4/22 to $39.99) shouldn't permanently veto clean closing breakout. Intraday extremes still persisted for stops/charts.
3. **Breakout vol references base `recent_5d_avg_vol`, not 20d trailing** — post-parabolic 20d mixes climax + dried-up base, denominator structurally inflated. XNDU 5/1: 1.20× 20d but 1.93× base recent. Right reference is the dry-up burst.

**ATR-14 inlined with full Wilder TR** (`max(H-L, |H-C_prev|, |L-C_prev|)`) — not `backtester/filters.py::compute_atr_14` close-only approx. VCP premise is intraday swings dry up; close-only TR lets `$100→$110→$90→$100` flat-close look "tight." OHLC available since 2026-04-25 backfill.

**Hysteresis** (theme pattern): single-day downward flips held until second-day confirms; INVALIDATED never holds; upgrades fire immediately. `held_from_stage` audit-reviewable. Event `flag_stage_flip_held` mirrors `theme_stage_flip_held`.

**Schema**: `mi_flag_candidates` (UNIQUE ticker+scan_date, persists ALL stages including `unqualified` for offline tuning). 5 helpers in `db.py`: `get_flag_universe` (top-200 RS, CS/ADRC, $5+, $5M+ ADV20, ≥60 sessions), `insert_flag_candidate`, `get_yesterday_flag_stages` (DISTINCT ON for hysteresis), `get_recent_flag_stages` (5-day stage list — needed for TRIGGERED's "was COILED in last 5"), `get_ticker_flag_history`. `get_rs_for_tickers` extended to return `rs_rank` (preserves SSoT).

**Orchestrator `run_flag_scan`**: `should_run` gate → universe → batched yesterday/recent/RS/sector via `asyncio.gather` → per-ticker compute via `Semaphore(8)` → persist all rows → audit events → per-ticker TRIGGERED Telegrams sent BEFORE digest. Digest 4 sections (TRIGGERED/COILED/NEW TIGHTENING/DROPPED OUT), zero-suppressed on quiet days. WATCH silenced from digest (~40-50/day too noisy) — drill-down via `/flags watch`.

**On-demand `/flags`**: bare → COILED+TRIGGERED today; `/flags watch` → WATCH+TIGHTENING; `/flags TICKER` → 14d stage history. Routed before generic theme route to avoid keyword overlap.

**Registry**: `flag_continuation` (phase=`shadow`, model=`telemetry_review`, thresholds `{n_triggers: 30, fwd_5d_pos_rate: 0.50}`). Adapter in `strategies/adapters.py`. Telemetry-only.

**Scheduler**: 17:25 ET mon-fri (between fishhook 17:20 and post_nightly_audit 17:30). `audit_wrap`'d, `misfire_grace_time=900`. Verification deferred to first run.

**Lesson**: pattern detectors on multi-day base structure must anchor metrics to the ticker's own recent extreme, not global thresholds. All three calibration fixes are the same shape: rigid thresholds against generic baselines silently veto the exact pattern the detector hunts. Replay-driven calibration on a known-good case (XNDU) before deploy is non-negotiable for this class.

### 2026-05-01 (session 1) — 9M Day 2 stop clobber bug (critical)
GOOGL 9M Day 2: announced stop $365.82 (prev day low), Alpaca received **$379.43** (today's ORB low). 0.8% stop vs intended 4.3%. Root cause: `broker/order_manager.py::submit_entry`, `check_fills`, `attempt_day1_reentry`, `check_day1_stopouts` all hardcoded `stop_loss_price = trade["orb_low"]` — SSoT violation from unified entry pipeline (2026-04-24 s3). MAGNA53 didn't manifest because `stop_price == orb_low` there; 9M Day 2 writes `stop_price = prior_day_low ≠ orb_low`.

**Fix:** every site reads `trade["stop_price"]` (spec-authored, persisted at INSERT). 9 sites patched. GOOGL today left at $379.43 stop (user opted not to manually adjust); code fix prevents recurrence.

**Lesson:** unified pipeline preserved spec-authored stop_price at INSERT but downstream order_manager paths still pulled `orb_low` per original MAGNA53 assumption. Two strategies sharing one funnel must read the strategy-authored stop column, not a per-strategy alias.

### 2026-04-30 (session 2) — Friday Curated Watchlist + entry-tag consistency
Plan: `~/.claude/plans/shiny-mapping-locket.md`. Apollo curates weekly chart-review list combining best ideas from EP/9M/themes/wick/parabolic/RS into a single Friday 6:00 PM ET Telegram digest with a TradingView import block + per-ticker chart-link buttons. **Trade-idea radar — does NOT trigger entries.**

**New module `friday_watchlist.py`**: six per-source curators reuse existing helpers; custom SQL only for parabolic week-window. Cross-source dedup with priority `EP > theme > 9M > wick > parabolic > RS`. Single bullet per ticker with bracketed reason chips. Top 25 by composite priority.

**TradingView integration (two depths)**: (1) Text import block `EXCHANGE:TICKER` comma-separated for TV mobile Watchlist Import (MIC mapping XNYS→NYSE, XNAS→NASDAQ, etc — sourced from `mi_security_types.exchange` via new `get_security_exchange_map(tickers)`); (2) Per-ticker chart-link inline keyboard, top 8, 4×2 layout, `url=` deep-links. **Atomicity**: import string must arrive in one Telegram message; build `body_text` + `tv_block` separately, send tv_block as separate atomic message if combined > 3900 chars. New `_send_with_keyboard()` posts directly to Bot API since `send_telegram_message` doesn't accept `reply_markup`.

**Schema**: `mi_weekly_watchlists` PRIMARY KEY (week_ending, ticker). Helpers `insert_weekly_watchlist` (DELETE+INSERT atomic) + `get_security_exchange_map`.

**Scheduler**: Fri 18:00 ET, `audit_wrap`'d, `misfire_grace_time=3600`. Detects partial-RS via `mi_job_runs.status='running'` → "_RS data refreshing — partial watchlist_" footer.

**Surface**: `/watchlist` (NLP routes checked before existing overnight-tracker watchlist that shares keyword). Curation: EP HIGH 5, 9M Sugar 5, Themes top 3 Accelerating × top 2 RS, Wick 3 with `fwd_3d_from_high_pct ≤ -0.03`, Parabolic 3 climax, RS Leaders 5 net-new. Cap 25. Quiet-week (count < 3): compact footer, no TV block. Disabled strategies (`should_run`) omitted.

**Lesson**: TV's no-write-API ceiling for third parties → text-import + chart-link buttons is highest reachable depth. Two depths protect different friction modes — bulk add vs single-tap. Cross-source dedup priority hierarchy prevents one ticker dominating multiple sections while preserving every source tag in reason chips.

### 2026-04-30 (session 1) — EP scan dead-zone telemetry beef-up
Dead-zone post-mortem showed `mi_ep_scan_log` carried only *last seen* state per (ticker, scan_date) due to UNIQUE — trajectories unrecoverable. Augmented in place: dropped UNIQUE name-agnostically via `DO $ ... pg_constraint loop`; added `scan_time_et TIMESTAMPTZ`, `rank_by_gap`, `projected_vol_multiple`, `pm_rvol`, `adv`, `adv_source`, `minutes_since_open` cols + index. Reader applies `DISTINCT ON (ticker) ORDER BY ticker, scan_time_et DESC NULLS LAST, id DESC`. `mi_ep_alerts.detected_at` insert uses `COALESCE($16::TIMESTAMPTZ, NOW())` — asyncpg can't infer through COALESCE without explicit cast.

**New `mi_ep_scan_outcomes`** caches fwd 5d/10d max-high % from baseline close. Computed nightly via ROW_NUMBER() window over fwd sessions ≤ 20d. Lookback `today - 15` to `today - 5` so 5d horizon has ≥ 5 settled sessions.

**Writers** in `ep_detector.py` use `_scan_row(c, filter_reason)` closure; `log_ep_scan_candidates` is plain INSERT (every scan appends), reader applies DISTINCT ON. Added explicit `_log_filtered` for previously-silent `already_today` skip path.

**Option B ADV probe** — bumped non-universe ADV synthesis from `[:20]` to `[:50]`, emit `ep_adv_probe_synthesized` audit event for ranks 21-50 (~400-1000 events/day). Retirement gated on data volume.

**Followups** registered in `data_gated_reviews.yaml`: `dead_zone_reevaluation` (≥2026-06-15, n≥20 trustworthy timestamps); `adv_probe_retirement` (≥2026-06-01, decide [:50] vs [:20]).

**Lesson:** UNIQUE on (scan_date, ticker) collapsed temporal trajectories silently. UPSERT looked correct but erased exactly the data needed to reconstruct dead-zone events. Append-only + DISTINCT ON for "current state" — readers and writers diverge on cardinality and that's fine.

---

## Changes Made — Historical (compressed log)

### 2026-04-28
- **session 4 — P22 Wick-Fill shadow tracker**: First strategy shipped through Strategy Maturity Framework. Negated shooting-star setup (`close_in_range_pct ∈ [0.50, 0.75)`) → Day 2+ break of `prior_high` is the short-trap fill. New `mi_wick_candidates` mirrors sugar-baby shape + adds `filled_wick BOOL` + dual fwd-return anchors (from-high conditional on fill, from-close unconditional baseline — gap = strategy edge). Reuses `_NINEM_CONTEXT_CTE` + `is_9m_directional` so WU 2026-04-24 fix stays enforced. Promotion model `telemetry_review` (n≥30, fill_rate≥0.50). Lesson: framework worked as designed — strategy #5 = config row + adapter + sweep call site.
- **session 3 — Strategy Maturity Framework (Option A)**: `agents/market_intelligence/strategies/` package (registry / adapters / promotion / telegram). `mi_strategies` table + `mi_live_trades.signal_type` column (backfilled). Phase gate at 3 entry points (entry_pipeline, shadow_orb_tracker, parabolic_detector). Three promotion evaluators (unpaired_r / paired_r / telemetry_review). Manual promotion. Lesson: thin overlay over per-strategy outcome tables is right when each has materially different telemetry semantics; schema unification first would block on backfill that doesn't pay off until ≥6 strategies.
- **session 2 — Theme Pass 1.5 protected-theme relief valve**: `protected_names` exemption made existing-vs-existing consolidation impossible once a duplicate slipped in. Replaced blanket protection skip with score-direction guard (more-established theme survives) + protection contract preserved (when t protected, target must also be protected). Lesson: protection mechanism implicitly assumed existing themes are mutually distinct.
- **session 1 — 5-min Shadow ORB tracker**: Live ORB hard-coded to 1-min; shadow records would-be 5-min entries + outcomes. Pure telemetry. Extracted `broker/exit_logic.py::apply_daily_exit_step` as SSOT (was duplicated across backtester+live). `mi_orb_shadow_trades` UNIQUE (ticker, alert_date, bar_size_minutes). Lesson: highest-risk step was exit_logic extraction — two parity gates (deterministic backtest + mocked-Alpaca call sequence) caught what unit tests can't.

### 2026-04-27
- **session 3 — Parabolic-short M&A/news exclusion**: OGN false positive (buyout-driven). Two-layer: `mi_parabolic_exclusions` (manual permanent + LLM 14-day TTL) + Perplexity news check on climax/anticipation. Three sources with precedence `manual_keep > manual > news_check`. `/parabolic exclude/include/exclusions`. Lesson: price-action detectors need news/context layer for one-shot catalysts.
- **session 2 — Audit-noise reduction**: Three L1 noise sources: (1) `validation_error` lumped 429s + 5xx + parse → split into `*_rate_limited` / `*_api_failure` / `*_error`; (2) zombie themes invariant queried `stage != 'Retired'` but codebase never writes `'Retired'` → narrowed to Mainstream + 10d; (3) `silent_audit_error_window` 30d trained dismissal → hardcoded 24h; (4) `nightly_data_pull` no-show deadline 17:30 too tight + ignored `mi_job_runs` running → bumped 18:30 + cross-check. Lesson: L1 invariants must model system's actual semantics, not textbook ideal.
- **session 1 — Tiered ORB fade guard**: midpoint pre-check stricter than Qullamaggie/Pradeep methodology, redundant with 10:00 ET cleanup + 15% stop-width gate. `check_fade_guard` takes `ratio: float | None`; MAGNA53 HIGH passes `None`, 9M Day 2 passes `0.25`. Lesson: stacked guardrails should each protect a distinct failure mode.

### 2026-04-26
- **session 3 — Job-run telemetry + `/audit job_runs`**: Closes gap between `notify_job_failure` (crashes) and data-layer audit (table invariants); slow runs and silent zeroes had no signal. New `mi_job_runs` + `core/job_audit.py::audit_run` asynccontextmanager + `audit_wrap(fn, job_id, expected_min_rows=N)`. ~30 jobs wrapped. Lesson: a wrapper that interprets return values must agree with wrapped function's failure semantics — `return None` for opt-out vs `return 0` for "wrote nothing".
- **session 2b — Theme merge min-shared-ticker gate**: Pass 1 trigger conditions (`is_subset`, `overlap_ratio ≥ 0.6`) collapse to noise on tiny themes (1/1=100%, 1/2=50%). New `MIN_SHARED_FOR_MERGE = 3` gates Pass 1. Pass 1.5 (small-theme absorption) intentionally targets ≤3-ticker themes, unchanged.
- **session 2a — Crypto RS surveillance (shadow-mode)**: Parallel crypto RS layer; nightly ingest + RS + alt-season trigger eval all run, Telegram surfaces gated by `CRYPTO_RS_ENABLED=false`. New `agents/market_intelligence/crypto/` package (Kraken + DexScreener + CoinGecko + DefiLlama, US-VPS-safe $0). Three-signal alt-season trigger (stablecoin slope + BTC.D + TOTAL3). 11 `crypto_*` tables. RS = 40/30/30 vs `close_btc` ratio. Lesson: data-source sanity check is non-trivial — rejected Polygon Crypto + CMC; DefiLlama doesn't expose BTC.D (caught mid-design).
- **session 1 — RVOL@T pre-open gate (closes INTC-class entry leak)**: Legacy `today_volume / 20d_daily_ADV` mismatched numerator/denominator (thin pre-market vs full-session). Canonical Relative Volume at Time: today's cumulative vs 20-day mean cumulative at same ET clock-minute. New `mi_minute_volume_curves` + `agents/market_intelligence/minute_volume.py`. Pre-9:30 only. Graceful degradation: not in top-500 universe → skip silently. Lesson: stacked filters with mismatched denominators are a class of "silently passes garbage" bug.

### 2026-04-25
- **session 2 — Weekend data fallback + HUD EP button**: Saturday queries returned "no data today" (handlers used `et_today()`). New `collector.last_trading_day(from_date=None)` (skips Sat/Sun → Friday). Wired into HUD/EP/9M/cluster/trades handlers. Added EP button back to HUD inline keyboard.
- **session 1 — Parabolic short detector (TI1 Stage 1)**: Telemetry-only Stamatoudis/Qullamaggie short. Three-tier state machine: `watch → anticipation → climax`. Velocity-delta gate (`roc_5d ≥ 1.10× roc_20d`) is the canonical "parabolic vs linear" discriminator. Backfill verified CAR/GME ✅, NVDA correctly rejected. New `mi_parabolic_candidates` (persists ALL stages incl. unqualified for offline tuning). 17:15 ET cron. Required one-time OHLC backfill via `scripts/backfill_ohlc.py`. Lesson: pure-compute detectors need historical replay tooling first.

### 2026-04-24
- **session 6 — Sugar baby intraday/EOD direction parity**: WU 4/24 surfaced as Day-2 sugar baby despite net −4.6% (gapped −10%, recovered close > open). Intraday filter gated net direction vs prev_close; EOD filter gated only on `close > open` (intraday recovery). Added `(d.close - m.prev_close) / m.prev_close >= 0.03` to EOD SQL. Lesson: SSoT violation — same conceptual filter, two different gates.
- **session 5 — Apollo Resilience & Self-Audit System (L1/L2/L3)**: `system_audit.py` + `audit_invariants.py` (shared invariants). L1 invariant breach → Telegram. L2 anomaly (30d trimmed median ± 3 MAD or > 5× median) → Telegram + Sonnet hypothesis. L3 drift → audit row + Sunday digest. Three jobs (16:15 / 17:30 / 02:00 ET). `/audit <topic>` on-demand. Cold-start tiers (n<7 hardcoded ceilings, 7-14 L3-only, ≥14 full L2). Backfill verification deferred until ≥30 days of baselines (~2026-05-24).
- **session 4 — Zombie theme cooldown flood**: `db.py::get_active_themes()` had no recency filter — returned every theme ever written. Fix: `get_active_themes(stale_after_days=7)`. Recency cap is de-facto retirement mechanism.
- **session 3 — Unified entry pipeline**: `broker/entry_pipeline.py::submit_trade_entry` is the single funnel for MAGNA53 EP + 9M Day 2 ORB. Strategy diffs (stop, sizing) inject via `spec_builder` callback. Bounded action vocabulary (AUTO_ENTERED/PROPOSED/etc). Per-alert work `asyncio.gather` with `Semaphore(5)`. Lesson: two near-identical entry paths drift in opposite directions; one funnel + injection is the fix.
- **session 2 — ORB late-entry & fade guard**: CHE gapped +17.9%, HIGH at 9:55 ET, bracket placed but tape had faded. Fade guard in `_submit_orb_trade`: skip if `last_price < (orb_high+orb_low)/2`. Tightened window `hour==9 and minute<45`. 10:00 ET cleanup job cancels stuck `order_placed`. Lesson: wide intraday windows let dead-cat orders linger.
- **session 1 — OTO bracket stop-leg ID capture**: INTC false UNPROTECTED + Untracked SELL traced to 4 separate "find stop leg" impls; one used strict `==`, broken under Py3.12 `str(OrderType.STOP)` → `"OrderType.STOP"`. Single canonical `alpaca_client.extract_stop_leg_id(order)` (stop_price primary, case-insensitive type fallback) at all 5 sites. Lesson: same conceptual operation in N places drifts; centralize.

### 2026-04-23
- **session 3 — Validation-window hardening**: `Dockerfile.market` now COPYs `scripts/`; `_eod_ep_recap_job` appends `📡 Feed (sip)` line + fires on zero-HIGH days when feed events present; new `scripts/readiness_check.py` encodes 6 SQL cutover gates. Cutover target 2026-05-23.
- **session 2 — Env-var-gated SIP feed**: URI ORB miss traced to IEX zero-range first-minute bars on mid-liquidity. `ALPACA_DATA_FEED` env (iex/sip), resolved by `alpaca_client.get_data_feed()`. Validated AAPL parity 0.037%, URI 4/22 IEX=$0 → SIP=$4.20. `ALPACA_DATA_FEED=sip` set in prod. Phase 2 (Polygon Advanced dual-feed) trigger: book 5–10×, feed incident, OHLC divergence > 0.2%, or 2nd broker.
- **session 1 — Broker alert gaps + bracket hardening**: BSX/GSHD/SIRI naked positions traced to `StopLimitOrderRequest(stop_loss=...)` without `order_class=OTO` — alpaca-py silently drops kwarg. Fix: always OTO + verify stop leg, cancel naked bracket. Silent state changes: 3 branches in `_handle_cancel_or_reject` (was rejected-only); untracked-sell rowcount alert; UNPROTECTED escalation in `_process_entry_fill`. Lesson: silent-drop kwargs are catastrophic — verify what came back.

Full prose lives in git history at the listed commits. Each line is "topic — key change & lesson."

### 2026-04-22
- **Strip to market/trading focus**: deleted 5 unused sub-agents + Dockerfiles + dead secrets. Lesson: rotting scaffolding is deploy surface.
- **9M Sugar Baby going-in shape telemetry**: 6 new shape cols + `_shape_tag()` bucket. Telemetry-only — promote to filter after 30+ outcomes.
- **Humanize skip reasons + theme validation rate-limit**: `humanize()` translator; `_VALIDATION_SEMAPHORE(2)` + retry on 429. Lesson: "parse errors" were really rate limits — split exception handlers.
- **EP entry diagnostics**: `broker/skip_reasons.py` (18 bounded constants); `/why TICKER [date]` lifecycle timeline; 4:10 PM EOD EP recap. Lesson: free-form skip reasons broke aggregation.

### 2026-04-21
- **Briefing fixes, 9M quality**: 9M intraday range gate (≥ 2%) + extension gate (prev_close ≤ 1.20× SMA-10), anticipation carve-out (gap ≥ 10% OR proj_vol ≥ 25M).
- **`/trades` richer summary**: open + last 5 closed + totals. UTC/ET boundary fix for `closed_at` via `AT TIME ZONE`.

### 2026-04-20
- **Hardening triage**: LLM rate-limit guard in `ep_detector`; correlation matrix off event loop; theme breadth decay (`pct_above_20sma` < 40% × 2d → forced Fading).
- **Weekly system self-audit**: `system_review.py` — Sunday 8 AM ET 7d aggregation → Sonnet synthesis → 4-section Telegram digest.
- **9M quality filters (74 → 2-5/day)**: price ≥ $5, dollar-vol ≥ $50M, directional conviction, 3× ADV ratio (not flat ceiling). Lesson: flat ceilings silently block mid-ADV genuine catalysts.
- **Theme validation + broker partials**: `_extract_json_object()` brace-depth-aware (replaces regex broken by Haiku nested JSON); cross-sector Unknown fallback. KURA partial-exit stop-first ordering.

### 2026-04-19
- **9M ETF flood + EP ETF leakage + catchup ORB orders**: 3-layer 9M ETF filter; EP secondary `mi_security_types` gate; ORB window `now_et.hour < 10` + `misfire_grace_time=300`.
- **`/pregame` + pinned HUD + inline keyboards**: compact trade-ready shortlist; HUD auto-refresh; `/eps`, `/themes`, `/trades` drill-down.
- **9M EP system (Pradeep Bonde "9M" tactic)**: parallel track, zero changes to MAGNA53. New `ninem_detector.py`, `mi_9m_ep_alerts`, `mi_9m_sugar_babies`. Day 2 ORB at 9:31, stop = prior day's low.

### 2026-04-17
- **P15 Correlation clustering**: `correlation_engine.py` — beta-adjusted SPY-residual Pearson 20d. Backtest inconclusive — revalidate ~June 2026.
- **Validation cooldown**: `mi_validation_cooldowns` (14-day cooldown on validation removal); fixes CAR-in-Data-Center churn.
- **Hardening for live trading prep**: orphaned stop remediation; yfinance 30s timeout wrapper; data pull 4:30 → 5:00 PM ET.
- **Theme engine + EP detector fixes**: scratchpad in tool schemas; Unknown sector keyword fallback; post-assignment validation. EP: 15-min projection gate (≥ 9:45 AM); extension via `MIN(close)` over 5d.

---

## Adding a "Changes Made" entry
Keep new entries in **Recent** section. After ~2 weeks, compress to **Historical** — keep one bullet (date / topic / key change & lesson). Drop "Files Changed" lists (git tells you that), drop "Post-deploy verification" once verified, drop manual cleanup SQL once applied.

Target file size: under 30k chars. Hard ceiling: 40k (warning threshold).
