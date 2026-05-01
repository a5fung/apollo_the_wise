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
| 5:30 PM | **Post-nightly audit** (theme/cooldown/regime L2/L3) |
| 6:00 PM (Fri) | **Friday watchlist** (curated chart-review aggregator + TV import block) |
| 8:00 PM | Evening briefing |
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

### 2026-04-30 (session 2) — Friday Curated Watchlist + entry-tag consistency
Plan: `~/.claude/plans/shiny-mapping-locket.md`. Goal: Apollo curates a weekly chart-review list combining the best ideas from EP/9M/themes/wick/parabolic/RS into a single Friday 6:00 PM ET Telegram digest with a TradingView import block + per-ticker chart-link buttons. **Trade-idea radar — does NOT trigger entries**, separate from auto-trading flow.

**New module `agents/market_intelligence/friday_watchlist.py`** (~470 lines): six per-source curators (`_fetch_ep_high` / `_fetch_9m_sugar` / `_fetch_themes` / `_fetch_wick` / `_fetch_parabolic` / `_fetch_rs_ambient`) reuse existing helpers (`get_ep_outcomes`, `get_eod_9m_sugar_babies`, `get_active_themes` + `get_rs_for_tickers`, `get_wick_candidates_window`, `get_rs_leaders`). Custom SQL only for parabolic week-window query (`mi_parabolic_candidates`). All buckets gated by `should_run()` where applicable (parabolic_short, wick_fill).

**Cross-source dedup with priority hierarchy** (EP > theme > 9M > wick > parabolic > RS): `_merge_sources` collapses by ticker; primary = lowest-priority source seen. Single bullet per ticker with bracketed reason chips: `• NVDA — [EP HIGH Mon $128 (entered +210)] | [Theme: AI Datacenter Silicon (RS 91)] | [RS rank 3 · sector: Semiconductors]`. Top 25 by composite priority.

**TradingView integration (two depths)**:
1. **Text import block** — `EXCHANGE:TICKER` comma-separated for paste into TV mobile Watchlist Import. MIC mapping (XNYS→NYSE, XNAS→NASDAQ, ARCX→AMEX, BATS, IEXG→IEX). Sourced from `mi_security_types.exchange` via new `get_security_exchange_map(tickers)` helper. Empty/unknown MIC → omit prefix (TV resolves US equities).
2. **Per-ticker chart-link inline keyboard** — top 8 by composite priority, 4×2 layout, `url=` deep-links to `https://www.tradingview.com/chart/?symbol={prefix}:{ticker}`. Single-tap on phone opens TV chart.

**TV import atomicity (critical)**: import string must arrive in one Telegram message — splitting `NASDAQ:NVDA,NYSE:TWLO,...` mid-block forces double paste. Strategy: build `body_text` + `tv_block` separately. If `len(body) + len(tv) ≤ 3900` → single message. Else → body via `send_telegram_message` (auto-splits at section boundaries), tv_block as a separate atomic message. Inline keyboard attaches to whichever message holds the TV block. New `_send_with_keyboard()` posts directly to Bot API since `send_telegram_message` doesn't accept `reply_markup`.

**Schema**: `mi_weekly_watchlists (week_ending, ticker, sources jsonb, composite_priority, reason_chip, generated_at)` PRIMARY KEY (week_ending, ticker). New helpers `insert_weekly_watchlist(week_ending, rows)` (DELETE+INSERT atomic, supports mid-week reruns), `get_security_exchange_map(tickers)` (single-batch MIC lookup).

**Scheduler**: `_friday_watchlist_job` cron Fri 18:00 ET, `audit_wrap`'d, `misfire_grace_time=3600`. Sits between 17:30 post_nightly_audit and 20:00 evening_briefing. Detects partial-RS state via `mi_job_runs.status='running' AND job_id='nightly_data_pull'` → footer "_RS data refreshing — partial watchlist_".

**Telegram surface**: `/watchlist` slash command (specific NLP routes `weekly watchlist` / `friday watchlist` / `curated watchlist` / `show watchlist` checked **before** the existing overnight-tracker watchlist route which shares the keyword). On-demand persists=False; cron persists=True.

**Curation rules**: EP HIGH 5 by ep_score; 9M Sugar Baby 5 by volume (close_in_range_pct ≥ 0.85); Themes top 3 Accelerating × top 2 RS tickers each; Wick 3 settled with `fwd_3d_from_high_pct ≤ -0.03` (real short-trap edge); Parabolic 3 climax-stage; RS Leaders 5 net-new (excludes tickers from other buckets). Total cap 25 tickers.

**Quiet-week handling**: rcount < 3 → compact "_Quiet week — minimal high-conviction setups._" footer, no TV block, no keyboard.

**Strategy-disabled gate**: `should_run('parabolic_short')` and `should_run('wick_fill')` checked at bucket entry — disabled strategies omitted entirely (not partial).

**Verification deferred to deploy**: 8-step suite per plan — on-demand `/watchlist` sanity, per-bucket parity vs source tables, TV import format paste test, TV chart button deep-link, Friday 18:00 cron run, holiday handling (Thursday fallback via `last_trading_day()`), strategy-disabled gate (`/strategy wick_fill disable` → empty wick bucket), cross-source dedup (NVDA-class).

**Lesson**: TradingView's no-write-API ceiling for third parties means text-import + chart-link buttons is the highest reachable integration depth. The two depths protect against different friction modes — text import is mass-add-once (low-friction batch), chart buttons are single-tap-per-ticker (mobile-friendly). Cross-source dedup priority hierarchy prevents the same ticker dominating multiple sections while preserving every source tag in the reason chip.

### 2026-04-30 (session 1) — EP scan dead-zone telemetry beef-up (C1/C2/C3 + Option B ADV probe)
Dead-zone post-mortem (analyze_late_detection_v3.py) showed `mi_ep_scan_log` carried only the *last seen* state per (ticker, scan_date) due to the UNIQUE constraint, so candidates that flipped through filter/pass/filter trajectories during the morning were unrecoverable. Augmented in place rather than forking a new table (single-source-of-truth) — re-evaluation queries the same log with `DISTINCT ON (ticker) ORDER BY ticker, scan_time_et DESC NULLS LAST, id DESC`.

**Schema migrations on `mi_ep_scan_log`:** name-agnostic UNIQUE drop via `DO $ ... pg_constraint loop` (auto-generated names drift), then `ADD COLUMN IF NOT EXISTS scan_time_et TIMESTAMPTZ`, `rank_by_gap INT`, `projected_vol_multiple FLOAT`, `pm_rvol FLOAT`, `adv FLOAT`, `adv_source TEXT`, `minutes_since_open INT`. Index `idx_ep_scan_log_scan_time` on `scan_time_et DESC`. Plus `mi_ep_alerts.detected_at TIMESTAMPTZ` (insert with `COALESCE($16::TIMESTAMPTZ, NOW())` — explicit cast required, asyncpg can't infer parameter type through COALESCE).

**New table `mi_ep_scan_outcomes`** (UNIQUE ticker+scan_date) caches forward 5d/10d max-high % from baseline close + n_sessions per horizon. Computed nightly in `outcome_tracker._compute_ep_scan_outcomes(today)` via single batched SQL with ROW_NUMBER() window over forward sessions ≤ 20d. Lookback `today - 15` to `today - 5` so 5d horizon has at least 5 settled sessions before snapshot.

**Writers (`ep_detector.py`):** after `candidates.sort(key=gap, reverse=True)` build `rank_by_gap` dict; new `_scan_row(c, filter_reason)` closure captures all 7 new fields per row. `_log_filtered` simplified to `_scan_row(c, reason)`. Two passing-row append sites swapped to `_scan_row(c, None)`. Added explicit `_log_filtered(c, "already scored earlier today")` for the previously-silent `already_today` skip path. `log_ep_scan_candidates` is now plain INSERT (16 fields), not UPSERT — every scan appends a row; reader applies DISTINCT ON.

**Option B ADV probe** — bumped non-universe ADV synthesis from `candidates[:20]` to `candidates[:50]` and emit `ep_adv_probe_synthesized` audit event for ranks 21-50 (~400-1000 events/day, intentional volume — telemetry to assess whether tier 2 ranks would have surfaced the dead-zone misses). Retirement gated on data volume — see registry.

**Followups registered in `data_gated_reviews.yaml`** (Sunday weekly review auto-surfaces when ready):
- `dead_zone_reevaluation` — earliest 2026-06-15, threshold n≥20 trustworthy timestamps in window. Re-run analyze_late_detection_v3 against `scan_time_et` instead of broken `created_at`.
- `adv_probe_retirement` — earliest 2026-06-01, threshold ≥1 dead-zone case. Decide: keep [:50] tier or revert to [:20].

**Lesson:** UNIQUE on (scan_date, ticker) collapsed temporal trajectories silently. UPSERT looked correct but erased exactly the data needed to reconstruct dead-zone events. The fix is append-only writes + DISTINCT ON for "current state" reads — readers and writers diverge on cardinality and that's fine. Asyncpg type inference also can't see through COALESCE wrappers — explicit `::TYPE` casts are non-optional for nullable TIMESTAMPTZ params.

### 2026-04-28 (session 4) — P22 Wick-Fill shadow tracker (telemetry-only)
First strategy shipped *through* the Strategy Maturity Framework. Negated shooting star setup (Bonde / Kristjan): 9M day closes mid-range with green body — close_in_range_pct ∈ [0.50, 0.75) — trapping shorts on the upper-wick close. Day 2+ break of `prior_high` is the canonical short-trap fill. Three-way EOD branching off the shared 9M context CTE: `≥ 0.75 →` sugar baby (existing), `[0.50, 0.75) →` wick (new), `< 0.50 →` distribution (ignored).

**New table `mi_wick_candidates`** mirrors sugar baby shape columns + adds `filled_wick BOOL`, `fill_date`, `fwd_{1,3,10}d_from_high_pct` (conditional on fill — measures the actual short-cover impulse), `fwd_{1,3,10}d_from_close_pct` (unconditional drift baseline). Two anchors are load-bearing: the gap between them is the strategy's edge.

**Single source of truth** — wick query reuses `_NINEM_CONTEXT_CTE` and the `is_9m_directional` + `is_green_close` Python post-filter from `ninem_detector.py`. So the WU 2026-04-24 fix (net up ≥ 3% vs prev_close, NOT just `close > open`) is enforced for wicks too without re-implementing the rule. Range-position branch is the *only* difference vs sugar baby selection.

**New module `wick_tracker.py`**: `run_wick_sweep(today)` (gated by `should_run('wick_fill')`, wired into `ninem_detector` EOD branch alongside sugar baby write) + `update_forward_returns(today)` (NOT gated — disabling mid-cycle would orphan in-flight measurements; sweep gate halts new candidates, fwd-returns gate would only lose telemetry). Forward-returns walks `mi_daily_closes` for ≤10 trailing sessions; rows without enough horizon left untouched.

**Promotion model `telemetry_review`** — generalized from parabolic_short to also handle wick_fill via `_eval_telemetry_review`. Wick gates: `n_candidates >= 30 AND fill_rate >= 0.50`. No R, no PnL — strategy is signal-quality validation, not P&L tracking. Adapter `_adapter_wick_fill` maps each row to `OutcomeRow(status='settled'|'pending', extras={fill_rate, median_fwd_3d_from_high, ...})`.

**Telegram surface**: `/wick` lists today's candidates + 30d telemetry footer (n_total · n_settled · n_filled / fill_rate). Evening brief 🪝 *Wick Watch:* line surfaces today's count + intraday tags. Weekly review 🪝 *Wick:* line cites n_total + fill_rate + post-fill drift vs baseline drift gap (the strategy's edge in one number) when n_settled ≥ 10; omits when too sparse.

**Scheduler**: existing EOD ninem cron writes wick rows alongside sugar babies (zero new entry-point job). New `_wick_forward_returns_job` 17:35 ET mon-fri walks unsettled rows.

**POET 2026-04-21 verification PASSED** via `scripts/backfill_wick_replay.py` (yfinance, no DB): cirp=0.602 ∈ [0.50, 0.75) ✓, green ✓, net +19.3% ✓, vol_ratio 4.7× ✓, dollar_vol $606M ✓. Day 2 (4/22) high $12.95 broke prior_high $11.09 — wick filled day 1. Continued +40% by 4/24, then pulled back. Full 10-session replay deferred (only 5 fwd sessions elapsed by 4/28 — exercises organically).

**Promotion gate semantics** — when n=30 AND fill_rate ≥ 0.50, eligibility flags; user manually `/strategy wick_fill promote shadow→paper`. No auto-promotion. Telemetry phase is open-ended; strategy stays in shadow until eligibility + manual review of the post-fill drift gap.

**Lesson:** the framework worked as designed — adding strategy #5 = config row in `strategies.py` seed list + adapter function + a sweep call site, no plumbing across system_review / agent / telegram / audit topics. The single-source-of-truth pattern (CTE reuse + Python predicate reuse) prevented re-introducing the exact WU bug fixed on the parallel cohort 4 days earlier. Three-way EOD branching off one shared filter is much cleaner than two parallel detectors with their own gates.

### 2026-04-28 (session 3) — Strategy Maturity Framework (Option A)
Plan: `~/.claude/plans/shiny-mapping-locket.md`. Five strategies (MAGNA53, 9M Day 2, Shadow ORB 5m, Parabolic Short, P22 backlog) were each wired ad-hoc — own outcomes table, own scheduler hooks, own audit topic, own weekly aggregator, own Telegram routes. Adding strategy #6 = copy-paste across 5 subsystems. Built a thin overlay registry: each strategy declares phase (shadow → paper → live), KPI promotion thresholds, enable flag. Per-strategy outcome tables stay as-is; adapter pattern layers on top.

**New package `agents/market_intelligence/strategies/`** — registry.py (Strategy dataclass + `_CACHE` + `should_run()` enable-gate helper), adapters.py (per-strategy `OutcomeRow` adapters; `magna53`/`9m_day2` collapsed via `functools.partial`), promotion.py (3 evaluators: `unpaired_r` / `paired_r` / `telemetry_review`; verdict shape dispatches on `promotion_model`), telegram.py (`/strategies` table + `/strategy <id> [enable|disable|promote|demote]`).

**Schema additions** (additive only): `mi_strategies` table; `mi_live_trades.signal_type TEXT` column + `idx_live_trades_signal_type`. **Backfill** classifies pre-framework rows: row in `mi_9m_sugar_babies` for same (ticker, alert_date) → `9m_day2`, else `magna53`. Backfill is `WHERE signal_type IS NULL` so subsequent startups are no-ops. Adapters then filter `WHERE signal_type = ?` — no joins, no ambiguity.

**Phase gate at three entry points** (without all three the registry is a no-op for half the strategies):
1. `broker/entry_pipeline.py::submit_trade_entry` — full enabled / shadow / paper-on-live check; returns BLOCK_STRATEGY_DISABLED / BLOCK_STRATEGY_IN_SHADOW / BLOCK_PAPER_STRATEGY_ON_LIVE via `_skip` (Telegram + audit row). Pipeline contract preserved.
2. `broker/shadow_orb_tracker.py::run_shadow_pass` — `should_run("shadow_orb_5m")` at top, logs `strategy_disabled_skip` and returns 0-row counts.
3. `parabolic_detector.py::run_parabolic_scan` — same pattern for `parabolic_short`.

**Promotion check is manual** — verdict flags eligibility, user runs `/strategy <id> promote`. Promote refuses if `verdict.eligible == False`. All phase transitions write `strategy_phase_change` to `mi_audit_log` with JSON-encoded `detail` (matches `system_audit._emit_l*` convention).

**Weekly review integration** (`system_review.py`): new `_aggregate_promotion_checks()` rolls up per-strategy verdicts; system prompt appends "📈 *Strategy promotion check:*" line citing each non-top-of-ladder strategy.

**Seed rows (idempotent)** at startup via `_seed_strategies_registry` (`executemany` + `ON CONFLICT DO NOTHING`):
| strategy_id | phase | model |
|---|---|---|
| `magna53` | live | `unpaired_r` |
| `9m_day2` | live | `unpaired_r` |
| `shadow_orb_5m` | shadow | `paired_r` |
| `parabolic_short` | shadow | `telemetry_review` |

**Three-pass review during build:** advisor flagged bare `/strategy` (no args) regex bug — fixed before commit. Two simplify passes landed: (1) `executemany` for seed loop, `partial` for adapter wrappers, `should_run` shared helper, `update_strategy` raises on no-args, audit `detail` JSON-encoded; (2) `render_strategy_detail` fetches 90d once and slices 30d (was 2 separate roundtrips), dropped dead `_DEMOTE_BACK["shadow"]: None`.

**Verification deferred to Hetzner deploy** — 6-step suite: signal_type backfill row-count parity (highest blast radius — if EXISTS classifier is wrong, every adapter produces wrong numbers from day one), adapter parity vs existing aggregators, phase gate fires across all 4 strategies (disable/re-enable for each), promotion verdict dispatch (paired vs unpaired vs telemetry shapes), seed migration idempotency, backwards compat (`/eps`, `/9m`, `/trades`, `/audit`).

**Out of scope** (deliberately): auto-promotion, cross-strategy risk pooling, schema unification, P22 build (P22 is the first strategy to *use* the framework once it ships).

**Lesson:** thin overlay over per-strategy outcome tables is the right factoring when each strategy has materially different telemetry semantics (R-based vs paired vs telemetry-only). Forcing schema unification first would have blocked the framework on a backfill exercise that doesn't pay off until you have ≥6 strategies. The registry + adapter pattern lets you add strategy #5 with a config row + adapter function instead of plumbing across 5 subsystems.

### 2026-04-28 (session 2) — Theme Pass 1.5 protected-theme relief valve
Two near-duplicate themes ("AI Datacenter Silicon" {ARM, AMD, MRVL} Nascent + "Custom AI Silicon & Chip Architecture Licensing" {ARM, MRVL} Accelerating) couldn't consolidate. Root cause: only 2 shared tickers → blocked by Pass 1's `MIN_SHARED_FOR_MERGE = 3` gate (added 2026-04-26 to fix Single-Cell Genomics over-merge). Pass 1.5 (small-theme absorption) would have caught it via subset overlap, but its `protected_names` exemption (line 2087) bailed out for any theme already in DB — making existing-vs-existing consolidation impossible once a duplicate slipped in.

**Fix in `theme_engine.py::_merge_overlapping_themes` Pass 1.5:** removed the blanket protection skip; replaced with two narrower gates inside the target-finding loop: (1) **direction guard** — `target.score >= t.score` ensures the more-established theme survives regardless of iteration order (without it, processing-order made the higher-scored theme absorb into the lower-scored one when it landed as `t` first); (2) **protection contract preserved** — when t is protected, target must also be protected, so new clusters still cannot dissolve existing themes (the original Single-Cell Genomics protection contract). Existing small protected themes (size ≤ 3, ≤ 1 unique ticker) can now consolidate into a higher-scored existing peer; new clusters → existing remains untouched. AI Datacenter Silicon now absorbs into Custom AI Silicon → {ARM, MRVL, AMD}.

**Followup (separate):** "Chip Architecture Licensing & CPU/GPU Compute Revival" name-persistence-after-membership-drift bug (name set when constituents were ARM+AMD; now contains INFQ/STM, name stuck). Not addressed here — different mechanism.

**Lesson:** the original protection mechanism implicitly assumed existing themes are mutually distinct. Once two near-duplicates coexist in DB, there's no remediation path without a relief valve. Score-direction + protected-target gates are the minimum-invasive fix that preserves the original protection contract.

### 2026-04-28 — 5-min Shadow ORB tracker (telemetry)
Plan: `~/.claude/plans/shiny-mapping-locket.md`. Apollo's live ORB is hard-coded to a 1-min bar. Added a shadow tracker that records would-be 5-min ORB entries + outcomes alongside live 1-min trades — same alert universe, same gates, same exit logic; only the bar size differs. Pure telemetry, no real orders, no new alerts. After ≥30 closed paired trades, weekly digest will surface "5m beats 1m by X R for {bounce/pullback}" type findings; promotion to live is an explicit follow-up.

**Step 1 — `broker/exit_logic.py` extraction (SSOT for daily exit step).** Pure function `apply_daily_exit_step(state, daily_bar, today)` extracted from the two existing copies in `backtester/tracker.py` and `broker/live_tracker.py`. Implements hard-stop → SMA10/20 → Day 3-5 partial → effective_stop max → SMA trail close ladder. `skip_partial_decision` / `skip_hard_stop_close` flags accommodate live-side divergences (Alpaca side-effects sequenced separately at the call site). 16 unit tests (`tests/test_exit_logic.py`) covering every branch — all passing. Mocked-Alpaca parity test confirmed the live call site's recorded order sequence is unchanged after refactor.

**Step 2 — `mi_orb_shadow_trades` schema.** UNIQUE (ticker, alert_date, bar_size_minutes) so 5m and future 30m coexist. Mirrors `mi_paper_trades` exit-state columns (so exit_logic.py operates on both via column-name contract) plus shadow-specific fields: bar_size_minutes, signal_type, shape_tag, score_tier, trigger_minute_et, status (no_entry/open/closed/gate_blocked). Helpers: `insert_shadow_trade`, `update_shadow_trade`, `get_open_shadow_trades`, `get_shadow_outcomes_window`.

**Step 3 — `broker/shadow_orb_tracker.py`.** `run_shadow_pass(today)` at 10:00 ET: fetches HIGH MAGNA53 alerts (filtered `created_at::time < 09:31 ET` — race-correct, mirrors live's submission window) + yesterday's 9M Day-2 sugar babies (all statuses — by 10:00 ET live's 9:31 job has already flipped pending→traded/skipped, so filtering 'pending' would yield the inverse universe). For each: fetch 9:30-10:00 1-min bars via new `alpaca_client.get_minute_bars_window`, compute 5-min ORB from bars[0:5], scan bars[5:30] for first `b['high'] >= orb_high` (symmetric stop-buy semantics — wick-fills count, matches live bracket fill mechanics). Apply identical fade guard (None for magna53 HIGH, 0.25 for 9m_day2) + 15% stop-width gate via shared `prepare_*_orb_order` spec builders. `update_shadow_positions(today)` at 4:50 PM ET walks open shadow rows, fetches today's daily bar, calls `exit_logic.apply_daily_exit_step`, persists.

**Step 4 — Scheduler.** `_shadow_orb_entry_job` at 10:00 ET mon-fri (`misfire_grace_time=600`); `_shadow_orb_exit_job` at **4:50 PM ET** mon-fri (after `live_position_update` 4:45 — Polygon daily aggregate must be settled; running pre-aggregate sees partial/zero data). Both `audit_wrap`'d with `expected_min_rows=None` (telemetry opt-out — return int counts but no empty_result alerts).

**Step 5 — `/audit shadow_orb` topic.** Three metrics: `shadow_orb_entries_per_day`, `shadow_orb_no_entry_rate`, `shadow_vs_live_r_delta_30d` (returns 0 if paired n<5 — cold-start protection). Standard MetricSpec → `_TOPIC_MAP["shadow_orb"]` plumbing.

**Step 6 — Weekly review.** `_aggregate_shadow_orb_outcomes(window_days=30)` — INNER JOIN `mi_orb_shadow_trades` (5m) ↔ `mi_live_trades` (1m) on (ticker, alert_date) so per-alert deltas surface (population averages mask "5m wins on bounce, loses on extended"). R computed inline as `total_pnl / NULLIF(risk_dollars, 0)` — neither table stores r_multiple. Slice by signal_type × shape_tag (NULL for MAGNA53 — system prompt notes "by-shape deltas only available for 9M cohort"). Sonnet cites top by_shape entry's per_alert_delta in 📐 *Shadow ORB:* line when paired_closed_total ≥ 10. Graceful degradation via `to_regclass` schema check.

**Verification deferred to Hetzner deploy:** first 10:00 ET shadow pass writes rows; lookahead spot-check (no 1-min close above 5m ORB high in 'no_entry' rows); fade-guard gate parity; daily exit pass closes rows correctly. Step 1 backtest parity gate (`diff backtest_results.csv` before/after extraction) deferred to deploy time — local has no DB.

**Lesson:** the highest-risk step in the plan was the exit_logic extraction; mishandled state mutation would silently drift trade outcomes. Two parity gates (deterministic backtest + mocked-Alpaca call sequence) caught what the unit tests can't — the live call site's I/O ordering with cancel/replace/sell sequences is independent of the pure-function output.

### 2026-04-27 (session 3) — Parabolic-short M&A / news exclusion
OGN parabolic-short alert was a false positive — buyout-driven price spike, not parabolic momentum. Stock pinned to deal price, won't mean-revert. Detector was purely price-action; same shape applies to FDA approvals, lawsuit wins, earnings beats. Two-layer fix:

**1. `mi_parabolic_exclusions` table** (composite PK `ticker, source`) — manual operator overrides AND auto LLM verdicts coexist. Manual: permanent, no TTL. News-check: 14-day TTL so deals-fall-through / news-ages get re-checked. New columns on `mi_parabolic_candidates`: `excluded_reason` / `excluded_source` / `excluded_detail` — preserve the price-action stage so OGN-class filters are reviewable historically (`SELECT ... WHERE excluded_reason IS NOT NULL`).

**2. Perplexity news check** in `parabolic_detector.py::_apply_exclusions` — runs on **climax + anticipation only** (watch stage skipped, not alert-worthy + API spend). Cache hits via `mi_parabolic_exclusions` short-circuit before the API call. Prompt asks specifically for buyout/acquisition/merger/FDA/lawsuit/earnings catalysts → Perplexity returns JSON `{is_event_driven, event_type, reason}`. Verdicts persisted with TTL + raw response for review. Concurrency `Semaphore(3)`, fail-open on parse / API errors.

**Telegram surface**: `/parabolic exclude OGN buyout by Bidder Inc` (manual, permanent), `/parabolic include OGN` (drop existing rows AND write a `manual_keep` sentinel so future news_check skips the ticker — without the sentinel the LLM would re-exclude under `news_check` on the next scan), `/parabolic exclusions` (list). Three sources with precedence `manual_keep > manual > news_check` in `get_active_parabolic_exclusions`. `/parabolic exclude` first removes any prior `manual_keep` so the new ban actually takes effect (otherwise the higher-precedence sentinel would shadow it). Routing: slash command in `agent.py::_handle_slash_command` + NLP route checked before generic theme-exclusion (both share "exclude" keyword).

**Digest formatting**: 🚫 *FILTERED (N)* footer in `send_parabolic_digest` lists what was excluded and why — operator sees the system worked, didn't silently eat alerts. Empty-after-filter case shows "_No parabolic-short setups today after filtering._" rather than suppressing the digest entirely.

**Lesson**: price-action detectors need a news/context layer for one-shot catalysts. The two layers protect against different failure modes — manual exclusion is the operator's "I know more than the model" override; news-check is the recurring noise reducer.

### 2026-04-27 (session 2) — Audit-noise reduction: validation/zombie/job-no-show
Apollo fired four L1/L2 alerts in one batch today — three of them noise. Diagnosis below; in each case the underlying telemetry was correct but the alerting threshold confused operator. **Fix theme: align invariant semantics with the codebase's actual definitions; differentiate transient failures from real bugs.**

**1. 228 `validation_error` events since 2026-03-28** — single audit bucket lumped together: rate-limited 429s (mostly fixed 2026-04-23), Anthropic 5xx/network blips, and genuine JSON parse errors. The `silent_audit_error_window` invariant uses `LIKE '%_error'` so transient API noise tripped it. Fix: split exception handlers in `theme_engine.py::_validate_theme_membership`, `_assign_uncovered_to_themes`, `_discover_new_themes` into three event_types — `*_rate_limited` (existing), `*_api_failure` (new — `anthropic.APIError` + `asyncio.TimeoutError`, no `_error` suffix → not flagged), `*_error` (real bugs only — JSONDecodeError, ValueError, unexpected exceptions). Banner logic in `briefing.py` + `scheduler.py` updated for the 4-bucket view (🟠 RL / 🔵 transient / 🟡 parse / 🔴 other).

**2. 31 zombie themes "stale > 7d but not Retired"** — `check_zombie_theme` queried `WHERE stage != 'Retired' GROUP BY name HAVING (CURRENT_DATE - MAX(theme_date)) > 7`. But the codebase intentionally NEVER writes `'Retired'` rows — recency cap IS retirement (per `get_active_themes(stale_after_days=7)`). So the invariant was always-fires-by-design. Fix: rewrote query as CTE picking LATEST row per theme + excluded `'Fading'` from the alert (Fading → drop is the de-facto retirement path). **Follow-up needed (2026-04-28):** the same invariant fired again with 27 zombies (18 Nascent + 11 Accelerating + 0 Mainstream) — recency-cap retirement applies to *every* stage, not just Fading. Re-narrowed `WHERE latest_stage = 'Mainstream'` and bumped threshold to 10d (Mainstream can stretch a holiday-shortened week). Only Mainstream drop-outs are load-bearing enough to be a bug; Accelerating-drop-out churn is potential L2 telemetry, not L1.

**3. `silent_audit_error_window` lookback was 30 days** — coupled to `_BASELINE_LOOKBACK_DAYS` in `system_audit.py`. Meant once an error fired, it kept tripping the L1 alert for 30 days even after the fix landed — poor operator UX, trains dismissal. Fix: hardcoded `_RECENT_ERROR_WINDOW_HOURS = 24` inside `check_audit_error_window`. `since` kwarg kept for signature compat with `all_invariants(...)` but ignored.

**4. `nightly_data_pull` flagged missing at 17:30** — `_EXPECTED_JOBS["nightly_data_pull"] = time(17, 30)` was 30 min after the 17:00 cron, but Polygon sector + Claude description calls can stretch the run past 17:30. Worse: `mi_job_log` row only writes after `notify_job_success` at the END, so a slow run looks identical to a no-show. Fix in `audit_invariants.py::check_job_no_show`: bumped deadline to 18:30, added `mi_job_runs` cross-check (`status = 'running'` today → "still running" not "missing"). Summary now reports both states distinctly.

**Lesson:** L1 invariants must model the system's actual semantics, not a textbook ideal. The codebase's "active theme" definition is recency-based, not stage-based; the codebase's "job ran" definition needs to handle in-progress (per `mi_job_runs`), not just completed (per `mi_job_log`). Same for "error" — transient vendor blips aren't bugs and shouldn't share an event_type with parse failures.

### 2026-04-27 — Tiered ORB fade guard by EP type
Today's HIGH EPs all blocked by the midpoint rule (`last_price < (orb_high+orb_low)/2`) despite looking fine to the user. OGN (double-gap-up, textbook "too extended" Pradeep skip) was also blocked by midpoint — but the principled 15% stop-width gate (`order_manager.py:998`) would have caught it on R/R math regardless. Diagnosis: midpoint pre-check is stricter than Qullamaggie/Pradeep methodology and redundant with the `_orb_window_cleanup_job` 10:00 ET cancel that already handles CHE-class dead-cat fills.

**Fix** (`entry_pipeline.py::check_fade_guard`): added `ratio: float | None`; `None` skips the check. MAGNA53 HIGH (`live_tracker.py:206`) now passes `None` (Sonnet + Perplexity + ATR 1.5× stop-width is enough). 9M Day 2 (`live_tracker.py:674`) passes `0.25` — pure quant, no LLM, keep protection but only skip on real weakness. The 15% stop-width gate is the R/R backstop. Lesson: stacked guardrails should each protect a distinct failure mode; redundant pre-checks are overhead, not safety.

### 2026-04-26 (session 3) — Job-run telemetry + `/audit job_runs`
Plan: `~/.claude/plans/audit-job-runs.md`. Closes the gap between `notify_job_failure` (hard crashes) and the data-layer audit (table invariants): **slow runs** (no exception, ran 8× normal) and **silent zeroes** (clean exit, wrote 0 rows) had no signal. Crypto nightly's CG 429 backoffs were the trigger.

**New table `mi_job_runs`** + new module `core/job_audit.py`: `audit_run` asynccontextmanager + `audit_wrap(fn, job_id, expected_min_rows=N)` registration-site sugar. On exception → status='failed', re-raises. On clean exit with `rows_written < expected_min_rows` → status='empty_result' + Telegram. Conventions: `rows_written is None` = opt-out; `bool` excluded from `isinstance(int)` so True/False can't silently set rows_written=1.

**Scheduler wired** (~30 jobs): expected_min_rows declared on data-writing jobs only (nightly_data_pull 5000, crypto_nightly_ingest 10, crypto_category_refresh 50, minute_volume_curves_refresh 50000). Five jobs return their row count. `check_fills` uses single audit id (not per-HHMM) so 7 fires/day aggregate to one baseline.

**`/audit job_runs` topic**: last 24h status counts + problem rows + slowest 5 vs 30d p95. Surfaced via `report` shortcut in `_handle_audit_topic`.

**Correctness fix from simplify pass**: 3 jobs with inline `notify_job_failure → return 0` would have double-Telegrammed (crash + spurious "empty_result"). Switched to `return None` so wrapper sees opt-out. Lesson: a wrapper that interprets return values must agree with the wrapped function's failure semantics.

### 2026-04-26 (session 2b) — Theme merge: min-shared-ticker gate
rs-theme-dash dashboard surfaced Single-Cell Genomics (1 ticker) and IT Infrastructure (2 tickers) being absorbed into Satellite Imagery via a single coincidental shared ticker. `_merge_overlapping_themes` Pass 1 had three trigger conditions (`jaccard ≥ 0.6`, `is_subset`, `overlap_ratio ≥ 0.6`) — `is_subset` and `overlap_ratio` both collapse to noise on tiny themes (1/1 = 100%, 1/2 = 50% overlap). New constant `MIN_SHARED_FOR_MERGE = 3` (theme_engine.py:211) gates Pass 1 with `len(intersection) < MIN_SHARED_FOR_MERGE: continue` before the trigger conditions evaluate. Pass 1.5 (small-theme absorption) intentionally targets ≤3-ticker themes and stays unchanged — it's a separate cleanup path with different semantics. Same gate principle implemented in `rs-theme-dash/data.py::dedup_themes` (min_shared=3 default); cross-referenced via comment so the two implementations stay in sync conceptually without sharing a module across repos.

### 2026-04-26 (session 2a) — Crypto RS surveillance (shadow-mode launch)
Full design + decisions in `CRYPTO_RS_DESIGN.md`. Parallel crypto RS layer that accumulates history during dormancy + fires high-conviction wake-up when capital rotates to alts. **Shadow-mode default** (`CRYPTO_RS_ENABLED=false`): nightly ingest + RS + trigger eval all run, Telegram surfaces gated by flag.

**Module**: `agents/market_intelligence/crypto/` — 11 files: 4 source clients (kraken/dexscreener/coingecko/defillama) + `data_router.py`, `rs_engine.py`, `triggers.py`, `categories.py`, `resolver.py`, `ingest.py`, `briefing.py`, `watchlist_seed.py`, `db.py`. Reuses `_percentile_ranks` / `_pct_return` from equity `rs_engine.py`.

**Data sources (US-VPS-safe, $0)** — Binance public REST 403s on US IPs:
- Kraken `/0/public/OHLC` → ~50 majors
- DexScreener `/tokens/v1/{chain}/{addr}` → long-tail current snapshot ($15M-$500M on-chain)
- CoinGecko → universe + historical OHLC + categories + `/global` (BTC.D + total mcap → derive TOTAL3)
- DefiLlama `/stablecoins` → stablecoin total mcap ONLY (does NOT expose BTC.D — caught and corrected mid-design)
- Rejected: Polygon Crypto (separate sub, long-tail gap), CoinMarketCap (no historical OHLCV on free tier)

**Three-signal alt-season trigger** (`triggers.py`) — each answers distinct question; ALL must hold + 30d cooldown:
1. Stablecoin 30d slope > 0 ← capital entering
2. BTC.D 30d slope < 0 for 5+ days AND BTC.D < 55% ← rotating out of core
3. TOTAL3 30d slope > 0 for 5+ days AND TOTAL3 > 90d SMA ← reaching long tail

**RS**: 40/30/30 1m/3m/6m vs `close_btc` ratio (NOT raw USD — that's the whole point). `rs_overall` + `rs_in_bucket` (mega/large/mid/micro). Wash gate: vol/mcap ∈ [0.01, 5.0], 7d median vol ≥ $10M, age ≥ 90d. $15M universe floor; watchlist exempt.

**Watchlist seed (27 coins)** — AI/DePIN cluster heaviest (TAO, RENDER, AKT, FET, VIRTUAL, VVV). KNX, COPPERINU, ASTER seeded as `_unresolved_<symbol>` placeholders; resolver fills chain+contract on first ingest via CG search → DexScreener fallback within trusted chains.

**Schema**: 11 `crypto_*` tables. `crypto/db.py::initialize_crypto_schema()` called from main `initialize_schema()` in try/except.

**Scheduler**:
- `_crypto_nightly_ingest_job` cron 18:00 ET daily (crypto 24/7), grace=3600s
- `_crypto_category_refresh_job` cron Sun 19:00 ET (weekly CG taxonomy)

**Telegram**: `/crypto [<category>]`, `/altseason`. **Slash dispatcher fix**: was dropping args (`/audit cooldowns` lost topic too); now preserves full message text.

**Date convention**: ET via `ZoneInfo("America/New_York")` everywhere — matches `et_today()`. Source UTC bars converted: 00:00 UTC = 8 PM ET prior day → tagged as prior-day bar (equity "after the close" semantics).

**Two advisor passes (general-purpose subagent)** caught: CG `market_chart` silent volume/mcap join loss on ms drift, 3× N+1 patterns in ingest (~50k stmts/run → ~3), `source` provenance lie, TIMESTAMPTZ→ET miss in cooldown, resolver per-coin universe redundancy, deprecated `asyncio.get_event_loop().time()`, DexScreener input mutation + URL injection, DefiLlama field-name lie.

**Verify pre-flip**: `scripts/verify_crypto_sources.py` smoke-tests all 4 sources end-to-end with sane-range assertions.

**Out of scope** (defer until alt season fires): intraday setup, on-chain, social, execution, orchestrator tool integration, multi-quote pairs.

### 2026-04-26 (session 1) — RVOL@T pre-open gate (closes INTC-class entry leak)
Apr 19–26 weekly self-audit flagged INTC entered at `rel_volume = 0.09` — institutional conviction visibly absent pre-open. Root cause: legacy `today_volume / 20d_daily_ADV` mismatches numerator (thin pre-market slice) against denominator (full-session total). Pre-9:30 the only gate was `MIN_PREMARKET_SHARES = 25_000` (absolute floor, not ratio); INTC trivially cleared 25k pre-market.

**Fix: Relative Volume at Time (RVOL@T)** — canonical TradingView/MarketChameleon/VWAP-execution primitive. Compares today's cumulative volume at the current ET clock-minute against the 20-day mean cumulative volume *at the same clock-minute* (per-ticker). U-shaped intraday volume curve auto-baked into the denominator → 0.09 rejected, 2.0× stays interpretable.

**Schema:** `mi_minute_volume_curves (ticker, anchor, et_clock_minute, mean_cum_vol, stddev_cum_vol, sample_n)`. Two anchors per ticker: `pm` (cumulative from 4:00 ET, minutes 240..569) and `session` (from 9:30 ET, minutes 570..959). New columns on `mi_ep_alerts`: `pm_rvol`, `pm_rvol_baseline_n` so passing alerts also persist their volume signal.

**New module: `agents/market_intelligence/minute_volume.py`**
- `refresh_curves(today, universe_limit=500, lookback_days=30)` — nightly job. Fetches Polygon `/v2/aggs/ticker/{T}/range/1/minute/{from}/{to}` for top-500-by-dollar-volume universe (from `mi_stock_scores`), bucketizes by ET clock-minute, computes mean/stddev per (anchor, minute). Concurrency `Semaphore(8)` outside the global `_polygon_lock`. Lookback ends at yesterday — only closed sessions baselined.
- `compute_rvol_at_time(ticker, now_et, today_premkt_vol, today_session_vol)` — runtime lookup. Returns `None` if before 4:00 ET, at/past 9:45 ET, or no baseline row. Past 9:45 the existing `projected_vol_multiple` extrapolation handles full-day RVOL — RVOL@T window is intentionally 4:00–9:44 ET to avoid double-gating.

**Constants:** `MIN_PM_RVOL = 1.0`, `MIN_SESSION_RVOL = 1.0` (today's pace ≥ normal pace at this minute), `MIN_BASELINE_N_FOR_GATE = 10` (don't gate against shaky baselines), `MIN_SAMPLE_N = 5` (don't publish curves with < 5 days history).

**Gate placement (`ep_detector.py`):** pre-9:30 only. The 9:30–9:44 window is left to the existing rel_volume check (over-gates if anything, not the audit's complaint). Rejected candidates write `filter:pm_rvol_too_low: pm_rvol=0.18x (today 12,400 / baseline 67,500 n=18) < 1.0x` to `mi_ep_scan_log.filter_reason` AND fire `log_audit_event('ep_filter_pm_rvol', ...)` for L2/L3 visibility.

**New skip reasons:** `FILTER_PM_RVOL_TOO_LOW`, `FILTER_SESSION_RVOL_TOO_LOW` in `broker/skip_reasons.py` with humanize labels "Pre-market pace below normal" / "Session pace below normal".

**New scheduler job:** `_minute_volume_curves_refresh_job` cron 18:30 ET mon-fri (after 18:00 evening_briefing, before midnight). `notify_job_failure` wrapped, `misfire_grace_time=1800`. Idempotent — loss → next run rebuilds.

**Graceful degradation:** ticker not in top-500 universe → no baseline → gate silently skipped, falls through to existing 25k absolute floor. Curves can be missing on first run / after deploy / for halt-suspended tickers without breaking the scan. Sample-n threshold (≥10 days) prevents gating on shaky baselines.

**Logging on alerts:** alerts that PASS the gate now log `pm_rvol@t=2.34x` alongside existing `rvol=` and `proj=` in the EP alert info line. Persisted to `mi_ep_alerts.pm_rvol` / `pm_rvol_baseline_n`.

**Out of scope (deliberately):** outcome-tracker date/tz fix (`outcome_tracker.py:223-226` — separate audit follow-up), 154 validation_error mislabel diagnosis (separate), `_process_entry_fill` remediation hard-close escalation (judgment call, not pulling the trigger without explicit ask). Audit's Proposal #1 (OTO bracket hard block) was already shipped 2026-04-23/24 — confirmed in code review.

### 2026-04-25 (session 2) — Weekend data fallback + HUD EP button
On Saturday all `/eps`, `/9m`, `/clusters`, `/trades`, and `/hud` queries returned "no data today" because handlers used `et_today()` which yielded a non-trading date. Fix: new `collector.last_trading_day(from_date=None)` helper (skips Sat/Sun back to Friday — matches `prev_trading_days` weekend-only approximation; holidays not handled). Wired into `_build_hud_text`, `_handle_ep_query`, `_handle_9m_ep_query`, `_handle_correlation_clusters`, and the default branches of `_handle_eps_detail` / `_handle_trades_detail`. Telegram-side `/ep` and `/trades` commands also switched from `date.today().isoformat()` to `last_trading_day().isoformat()` so the date in the task string + drill-down callback_data lines up. HUD header now shows "Sat Apr 25 · data Fri Apr 24" when query date != today; per-handler messages get a `_(last trading day)_` suffix. Also added an **EP** button back to the HUD inline keyboard (was missing) — keyboard reflowed to 3+3 rows: `[Regime, Themes, EP] / [9M, Clusters, Watchlist]`. Routes via `task_map["ep"] = "/eps"` in `_handle_hud_drill_down`.

### 2026-04-25 (session 1) — Parabolic short detector (TI1 Stage 1) deployed
Plan: `~/.claude/plans/shiny-mapping-locket.md`. New telemetry-only detector for the Stamatoudis/Qullamaggie textbook short setup (TI1 in trading-ideas backlog). Three-tier state machine: `watch` (qualifying gates pass) → `anticipation` (burst checklist 4/4) → `climax` (anticipation + climax candle 2/2). Velocity-delta gate (daily-compound `roc_5d` ≥ 1.10× `roc_20d`) is the canonical "parabolic vs linear" discriminator — pullback count is telemetry-only, not a gate.

**Backfill verification (CAR / GME / NVDA):** all three case studies via `scripts/backfill_parabolic_car.py --source yf --end-date YYYY-MM-DD`. CAR ✅ (2 climaxes 4/7+4/21), GME ✅ (3 anticipations 1/25-1/27 Robinhood squeeze), NVDA ✅ correctly rejected (uptrend ~0.8%/day, not parabolic). User scope: hunt CAR/GME-class only.

**New files:** `agents/market_intelligence/parabolic_detector.py` (compute + `run_parabolic_scan` orchestrator + `send_parabolic_digest` 2-section Telegram with zero-suppression), `scripts/backfill_parabolic_car.py` (verification tool), `scripts/backfill_ohlc.py` (one-time OHLC backfill — see below).

**Schema:** `mi_parabolic_candidates` (UNIQUE ticker+scan_date, persists ALL stages incl. `unqualified` so thresholds re-tune offline), `mi_market_caps` (30-day-stale FMP cache).

**Scheduler:** `_parabolic_scan_job` cron 17:15 ET mon-fri, slots between 17:00 nightly_data_pull and 17:30 post_nightly_audit. `notify_job_failure()` wrapped, `misfire_grace_time=900`.

**OHLC backfill blocker:** older `mi_daily_closes` rows were close+volume only — `open/high/low` columns added later, never backfilled. Detector needs 60+ sessions of full OHLC. Polygon grouped-daily 1 call per date × 58 dates = ~57 sec, 683K rows upserted via existing `ingest_daily_closes()` (its ON CONFLICT COALESCE leaves close/volume untouched, fills NULL OHLC). One-time, but `scripts/backfill_ohlc.py` is idempotent and safe to re-run.

**Bug found and fixed mid-deploy:** `get_recent_daily_history(ticker, days)` always returned rows ending today, not bounded by scan_date. For prod (scan_date=today) fine, but historical replay was broken — CAR on 2026-04-21 came back as `unqualified` because the window's "today" row was 2026-04-24 (post-crash $204). Added `end_date` kwarg (default `None` → today) so replay works. Production cron unaffected.

**Production sanity check (2026-04-24 scan):** 4 climax (ARM, INTC, AMD, RMBS — large-cap semi cluster, ~80-98% prior move), 1 anticipation (MRVL). CAR/MXL replay on 4/21 also correct. Worth observing whether large-cap semi sweep is sector beta vs CAR/GME-class parabola — tunable from telemetry. Stage 1 is telemetry only; promote to paper after 2-3 months of shadow data.

### 2026-04-24 (session 6) — Sugar baby intraday/EOD direction parity
WU 2026-04-24 surfaced as a Day-2 ORB sugar baby despite being net −4.6% on the day (gapped −10%, recovered to close > open). Diagnosis: intraday filter (`ninem_detector.py:187-189`) gates on **net direction** vs prev_close (`gap_pct ≥ 3 OR intraday_gain_pct ≥ 4`), correctly rejecting WU all session — `mi_9m_ep_alerts` had 0 rows. EOD filter (`db.py:999`, `get_eod_9m_sugar_babies`) gated on **intraday recovery** (`close > open`) — different concept entirely. Wick-fill on a gap-down passes recovery but fails direction, so EOD wrote a sugar baby that intraday had unanimously rejected. Single-source-of-truth violation per `feedback_single_source_of_truth.md`.

**Fix:** added `AND (d.close - m.prev_close) / m.prev_close >= 0.03` to the EOD SQL alongside the existing `close > open` (kept as a clean-close follow-through filter; both gates now coexist). The CTE already computes `m.prev_close` so no schema/JOIN change. Manual cleanup: deleted WU's row from `mi_9m_sugar_babies`. CLAUDE.md key rule updated: "green" = net up ≥ 3% vs prev_close, NOT just close > open.

### 2026-04-24 (session 5) — Apollo Resilience & Self-Audit System + advisor cleanups
Plan: `~/.claude/plans/shiny-mapping-locket.md`. Goal: Apollo surfaces invariant breaches and metric anomalies itself instead of the user pattern-matching daily output. Workflow: Apollo detect → Telegram → user judges → paste alert into Claude Code → Opus mitigates → commit. Auto-remediation explicitly OFF.

**New files:** `agents/market_intelligence/system_audit.py` (L1/L2/L3 ladder, post-EOD/post-nightly/baseline-refresh entry points, `run_topic_audit` for `/audit <topic>`, `_compute_anomalies` with cold-start tiers + MAD<1 fallback + regime-conditional baselines for trade-throughput metrics, `_synthesize_hypothesis` with CLAUDE.md+audit-event context injection, threshold-crossing L3 dedup), `agents/market_intelligence/audit_invariants.py` (11 shared invariant functions; `readiness_check.py` refactored to import from it — single source of truth).

**Schemas:** `mi_metric_baselines (metric_name, as_of_date, p50, p95, mad, sample_n)`, `mi_baseline_resets (metric_name, reset_at, reason)`.

**Scheduler:** registered three jobs (16:15 / 17:30 / 02:00 ET).

**Weekly review (`system_review.py`):** new `_aggregate_anomalies()` pulls 7d `anomaly_detected` rows, buckets by level, filters L3 to band transitions (`from_band != to_band`). System prompt updated to append "📉 *Drift:*" line + cite L1/L2 in ⚠️ Broken section.

**Agent / Telegram:** `/audit <topic>` slash command (cooldowns/themes/skips/positions/feed/9m/all); keyword route `audit <topic>` excludes pre-existing `audit log` handler. CommandHandler binding for `audit` in `channels/telegram.py`. Stale `_handle_audit` retired-stub deleted. Defensive prefix-strip in `_handle_audit_topic` removed (advisor flagged dead code).

**⚠️ Backfill verification deferred** to backlog P24 — needs ≥30 days of `mi_metric_baselines` history. Earliest run ~2026-05-24. Without it the system has the same blind spot it was built to close — must run before declaring the audit layer trusted.

### 2026-04-24 (session 4) — Zombie theme cooldown flood
Nightly validation wrote 135 cooldowns (vs ~1/day baseline). Root cause: `db.py::get_active_themes()` had no recency filter — returned every theme name ever written with `stage != 'Retired'`. 98 themes loaded vs ~37 in today's snapshot; weeks-old hallucinations (e.g. LRCX in oil) re-triggered cooldown removal repeatedly. Fix: `get_active_themes(stale_after_days=7)` filters `theme_date >= CURRENT_DATE - 7 days`. Recency cap is the de-facto retirement mechanism — covers normal weekend/holiday gaps with margin. Manual cleanup applied in prod.

---

## Changes Made — Historical (compressed log)

### 2026-04-24
- **session 3 — Unified entry pipeline**: `broker/entry_pipeline.py::submit_trade_entry` is the single funnel for MAGNA53 EP + 9M Day 2 ORB. Strategy diffs (stop, sizing) inject via `spec_builder` callback. Bounded action vocabulary (AUTO_ENTERED/PROPOSED/etc). Per-alert work `asyncio.gather` with `Semaphore(5)`. Lesson: two near-identical entry paths drift in opposite directions; one funnel + injection is the fix.
- **session 2 — ORB late-entry & fade guard**: CHE gapped +17.9%, HIGH at 9:55 ET, bracket placed but tape had faded. Fade guard in `_submit_orb_trade`: skip if `last_price < (orb_high+orb_low)/2`. Tightened window `hour==9 and minute<45`. 10:00 ET cleanup job cancels stuck `order_placed`. Lesson: wide intraday windows let dead-cat orders linger.
- **session 1 — OTO bracket stop-leg ID capture**: INTC false UNPROTECTED + Untracked SELL traced to 4 separate "find stop leg" impls; one used strict `==`, broken under Py3.12 `str(OrderType.STOP)` → `"OrderType.STOP"`. Single canonical `alpaca_client.extract_stop_leg_id(order)` (stop_price primary, case-insensitive type fallback) at all 5 sites. Lesson: same conceptual operation in N places drifts; centralize.

### 2026-04-23
- **session 3 — Validation-window hardening**: `Dockerfile.market` now COPYs `scripts/`; `_eod_ep_recap_job` appends `📡 Feed (sip)` line + fires on zero-HIGH days when feed events present; new `scripts/readiness_check.py` encodes 6 SQL cutover gates. Cutover target 2026-05-23.
- **session 2 — Env-var-gated SIP feed**: URI ORB miss traced to IEX zero-range first-minute bars on mid-liquidity. `ALPACA_DATA_FEED` env (iex/sip), resolved by `alpaca_client.get_data_feed()`. Validated AAPL parity 0.037%, URI 4/22 IEX=$0 → SIP=$4.20. `ALPACA_DATA_FEED=sip` set in prod. Phase 2 (Polygon Advanced dual-feed) trigger: book 5–10×, feed incident, OHLC divergence > 0.2%, or 2nd broker.
- **session 1 — Broker alert gaps + bracket hardening**: BSX/GSHD/SIRI naked positions traced to `StopLimitOrderRequest(stop_loss=...)` without `order_class=OTO` — alpaca-py silently drops kwarg. Fix: always OTO + verify stop leg, cancel naked bracket. Silent state changes: 3 branches in `_handle_cancel_or_reject` (was rejected-only); untracked-sell rowcount alert; UNPROTECTED escalation in `_process_entry_fill`. Lesson: silent-drop kwargs are catastrophic — verify what came back.

Full prose lives in git history at the listed commits. Each line is "topic — key change & lesson."

### 2026-04-22
- **session 4 — Strip to market/trading focus** (commit before `cb39045` lineage): deleted 5 unused sub-agents (finance/calendar/research/browser/travel), Dockerfiles, compose blocks, tool schemas, AgentName enum values, 4 provider getters, 9 dead secrets, `tests/test_ibkr.py`. Orchestrator kept for future expansion. Env vars dropped: `GEMINI_API_KEY`, `TAVILY_API_KEY`, `IBKR_*`, `GOOGLE_*`, `APPLE_CALDAV_*`. Added to canonical: `PERPLEXITY_API_KEY`, `FMP_API_KEY`. Lesson: rotting scaffolding is deploy surface — delete dead code aggressively.
- **session 3 — 9M Sugar Baby going-in shape telemetry**: 6 new columns on `mi_9m_sugar_babies` (prev_5d_pct, prev_20d_pct, prev_vs_sma10, prev_vs_sma50, sma50_slope_pct, prior_sessions); `_shape_tag()` bucket (uptrend/pullback/extended/bounce/downtrend/flat). Telemetry-only — promote to filter after 30+ outcomes. Lesson: capture metrics first, gate later.
- **session 2 — Humanize skip reasons + theme validation rate-limit**: `humanize(reason)` translator (machine prefixes in DB, prose in Telegram). `_VALIDATION_SEMAPHORE(2)` caps concurrent Haiku; retry-once on 429. Three-bucket error banner (🔴/🟠/🟡). Lesson: "20 parse errors" turned out to be 20 rate-limit errors — split exception handlers.
- **session 1 — EP entry diagnostics & performance traceability**: `broker/skip_reasons.py` (18 bounded constants); every HIGH EP gets durable terminal state by 4:10 PM ET; `/why TICKER [date]` lifecycle timeline; 4:10 PM EOD EP recap; evening brief "EP OUTCOMES TODAY". Lesson: free-form skip reasons broke monthly aggregation — bounded vocabulary.

### 2026-04-21
- **session 2 — Briefing fixes, 9M quality + cadence**: truncate EP writeups at sentence boundaries, parse-error noise collapsed, Haiku response hardening, /pregame yesterday-fallback for sugar babies, 9M intraday range gate (≥ 2%) + extension gate (prev_close ≤ 1.20× SMA-10 measured at prev_close not today), high-conviction anticipation carve-out (gap ≥ 10% OR proj_vol ≥ 25M).
- **session 1 — `/trades` richer summary**: open positions with entry→current→stop, last 5 closed inline, totals row. UTC/ET boundary fix for `closed_at` (after 8 PM ET UTC date rolls but `et_today()` still today; cast via `AT TIME ZONE 'America/New_York'`).

### 2026-04-20
- **session 4 — Hardening triage**: LLM rate-limit guard in `ep_detector` (`AsyncAnthropic` + `Semaphore(5)` + retry); correlation matrix off event loop (`asyncio.to_thread()`); theme breadth decay (`pct_above_20sma` < 40% × 2d → forced Fading).
- **session 3 — Weekly system self-audit**: `system_review.py` — Sunday 8 AM ET 7d aggregation → Sonnet synthesis → 4-section Telegram digest; persists `mi_system_reviews` (JSONB metrics + suggestions). Follow-up framed as metric deltas.
- **session 2 — 9M quality filters (74 → 2-5/day)**: price ≥ $5, dollar-vol ≥ $50M actual / $30M anticipation, directional conviction (gap ≥ 3% OR intraday ≥ 4%), 3× ADV ratio (not flat ceiling). Lesson: flat ceilings silently block mid-ADV genuine catalysts.
- **session 1 — Theme validation parse errors + cross-sector hallucinations + broker partials**: `_extract_json_object()` brace-depth-aware (replaces regex broken by Haiku nested JSON); `max_tokens` 200→400; "Respond with valid JSON only" system prompt. Cross-sector gate Unknown-sector fallback (keyword overlap 4+ letter). KURA partial-exit blocked-by-stop bug: stop-first ordering (cancel full-qty stop → place 2/3 stop → market sell 1/3); fractional qty fix (`int(remaining)//3`); caller honors return value.

### 2026-04-19
- **session 6 — 9M ETF flood + EP ETF leakage + catchup ORB orders**: 3-layer 9M ETF filter (SKIP_TICKERS / `mi_security_types` non-CS/ADRC / RVOL ≥ 2× ADV with caching); EP detector secondary `mi_security_types` gate; ORB window `now_et.hour < 10` + `misfire_grace_time=300` so APScheduler skips stale fires.
- **session 5 — `/pregame` + pinned HUD + inline keyboards**: compact trade-ready shortlist (no LLM); HUD auto-refresh hourly via `editMessageText` (`mi_hud_state` table); `/eps`, `/themes`, `/trades` summary + drill-down buttons.
- **session 1 — 9M EP system (Pradeep Bonde "9M" tactic)**: parallel EP track, zero changes to MAGNA53. New `ninem_detector.py`, `mi_9m_ep_alerts`, `mi_9m_sugar_babies` (UNIQUE per ticker/date), Day 2 ORB at 9:31, outcome tracking `signal_type='9m_ep'`. Sugar Baby = 9M day + green + close top 25% range. Stop = prior day's low. Backtest + e2e scripts.

### 2026-04-17
- **session 4 — P15 Correlation clustering**: `correlation_engine.py` — beta-adjusted SPY-residual Pearson 20d on liquid universe; BFS components ≥ 4 stocks at corr ≥ 0.85; chaining filter (sub-matrix mean_corr ≥ 0.80); theme dedup. Backtest precision 0.5% / recall 8.2% — statistically inconclusive (theme history < 6 months); revalidate ~June 2026. Bug fixes: ETF contamination (CS/ADRC filter), OOM at 5K universe ($20M dollar-vol filter → 2800 tickers), holiday-month 21-day shortfall (`_LOOKBACK_DAYS = 35`).
- **session 3 — Validation cooldown**: `mi_validation_cooldowns` (14-day cooldown on validation removal); Claude prompt context injection + post-assignment hard filter; `show cooldowns`, `bypass cooldown TICKER`. Fixes the CAR-in-Data-Center churn bug.
- **session 2 — Hardening for live trading prep**: orphaned stop remediation in `sync_positions()`; yfinance 30s `asyncio.wait_for` wrapper; data pull 4:30 → 5:00 PM ET; RS leaders tweet text-only (dropped `media_upload` 403). Features: P2 (MODERATE EP recap), P3 (validation report scaffold).
- **session 1 — Theme engine architectural hardening + EP detector fixes**: scratchpad in all tool schemas; Unknown sector keyword-overlap fallback; immediate post-assignment validation; 15-ticker description chunking. EP: 15-min projection gate (≥ 9:45 AM); extension via `MIN(close)` over 5d; reverted dangerous auto-persist. P4-P6 (EP outcomes, theme conviction display, journal).

---

## Adding a "Changes Made" entry
Keep new entries in **Recent** section. After ~2 weeks, compress to **Historical** — keep one bullet (date / topic / key change & lesson). Drop "Files Changed" lists (git tells you that), drop "Post-deploy verification" once verified, drop manual cleanup SQL once applied.

Target file size: under 30k chars. Hard ceiling: 40k (warning threshold).
