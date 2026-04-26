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

## Logging Discipline (always-on rule)
**Every new action, filter, gate, or failure mode MUST be observable from the data alone.** Apollo surfaces problems by querying its own tables; if a code path is silent, the weekly self-audit can't see it. Apply this whenever you ship code:

1. **New filter / gate (no-trade reason)** — write a structured reason to the relevant scan/skip table:
   - EP path: `mi_ep_scan_log.filter_reason` using a bounded prefix from `broker/skip_reasons.py` (`category:code: detail`). Add a new constant if no existing one fits, plus its `_HUMAN_LABELS` entry. Never invent free-form prefixes — they break monthly aggregation (`split_part(skip_reason, ':', 1)`).
   - Broker path: `mi_live_trades.skip_reason` with the same bounded vocabulary.
2. **New action (trade attempt, entry, cancel, remediation)** — use the bounded action vocabulary in the entry pipeline (`ACTION_AUTO_ENTERED / PROPOSED / AUTO_ENTER_FAILED / PROPOSAL_SEND_FAILED / SKIPPED / BLOCKED`). Don't add a 7th without explicit discussion.
3. **New trade-passing telemetry** — when an alert/trade carries a *new* signal value (e.g. `pm_rvol`), persist it as a column on the relevant table (`mi_ep_alerts`, `mi_live_trades`, `mi_9m_sugar_babies`) so it's queryable later, not just stuffed into a log line.
4. **New failure mode (silent until now)** — fire `log_audit_event(event_type, summary, detail)`. Use a stable `event_type` string that the system audit can aggregate (existing examples: `validation_error`, `ep_filter_pm_rvol`, `assignment_error`). Never let a try/except swallow an exception with only a `logger.warning` — the audit table needs the row.
5. **Telegram or audit-only?** — terminal/actionable events (entry submitted, position blocked, naked stop) get Telegram via `briefing.send_telegram_message`. Self-healing/transient/per-candidate filter rejections stay in `mi_audit_log` only. Reserve Telegram for things the user must act on; everything else is observable but quiet.
6. **Translate machine prefixes for users** — when surfacing skip reasons in Telegram, run them through `broker/skip_reasons.humanize()`. DB keeps the machine prefix; user sees prose.
7. **Log the value, not just the verdict** — `Skip TICKER: pm_rvol=0.18x (today 12,400 / baseline 67,500 n=18) < 1.0x` is debuggable; `Skip TICKER: low volume` is not. Include the inputs that drove the decision.

If you ship a feature that *can't* answer "why did/didn't this fire?" from `psql` alone, it's incomplete.

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
- **Fade guard**: before placing ORB bracket, fetch latest trade. If `last_price < (orb_high+orb_low)/2`, skip with `SETUP_FADED_FROM_ORB`.

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
- Jobs: `_post_eod_audit_job` 16:15 ET, `_post_nightly_audit_job` 17:30 ET, `_baseline_refresh_job` 02:00 ET. Each ends with kuma heartbeat (`KUMA_AUDIT_*_URL` env).
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
- Safeguards: max 4 positions, 2% daily loss limit, 3-loss circuit breaker
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
KUMA_AUDIT_EOD_URL, KUMA_AUDIT_NIGHTLY_URL, KUMA_AUDIT_BASELINE_URL  # optional heartbeats
```

---

## Changes Made — Recent

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

**Scheduler:** registered three jobs (16:15 / 17:30 / 02:00 ET) each ending with `_kuma_heartbeat()` ping (env-gated). Three new env vars: `KUMA_AUDIT_EOD_URL`, `KUMA_AUDIT_NIGHTLY_URL`, `KUMA_AUDIT_BASELINE_URL`.

**Weekly review (`system_review.py`):** new `_aggregate_anomalies()` pulls 7d `anomaly_detected` rows, buckets by level, filters L3 to band transitions (`from_band != to_band`). System prompt updated to append "📉 *Drift:*" line + cite L1/L2 in ⚠️ Broken section.

**Agent / Telegram:** `/audit <topic>` slash command (cooldowns/themes/skips/positions/feed/9m/all); keyword route `audit <topic>` excludes pre-existing `audit log` handler. CommandHandler binding for `audit` in `channels/telegram.py`. Stale `_handle_audit` retired-stub deleted. Defensive prefix-strip in `_handle_audit_topic` removed (advisor flagged dead code).

**⚠️ Backfill verification deferred** to backlog P24 — needs ≥30 days of `mi_metric_baselines` history. Earliest run ~2026-05-24. Without it the system has the same blind spot it was built to close — must run before declaring the audit layer trusted.

### 2026-04-24 (session 4) — Zombie theme cooldown flood
Nightly validation wrote 135 cooldowns (vs ~1/day baseline). Root cause: `db.py::get_active_themes()` had no recency filter — returned every theme name ever written with `stage != 'Retired'`. 98 themes loaded vs ~37 in today's snapshot; weeks-old hallucinations (e.g. LRCX in oil) re-triggered cooldown removal repeatedly. Fix: `get_active_themes(stale_after_days=7)` filters `theme_date >= CURRENT_DATE - 7 days`. Recency cap is the de-facto retirement mechanism — covers normal weekend/holiday gaps with margin. Manual cleanup applied in prod.

### 2026-04-24 (session 3) — Unified entry pipeline + silent-failure hardening
New `broker/entry_pipeline.py::submit_trade_entry` is the single funnel for MAGNA53 EP + 9M Day 2 ORB entries. Strategy differences (stop source, sizing) inject via `spec_builder` callback; everything else lives in the pipeline once. **Contract: every terminal failure Telegrams via `humanize()`.** `live_tracker._submit_orb_trade` deleted (~130 lines); `submit_9m_day2_trade` shrunk 150→50 lines; `process_new_alerts_live` shrunk 170→80 lines. Per-alert work now in `asyncio.gather` with `Semaphore(5)` (was strictly serial — 20 alerts × 3×60s bar-fetch retry could stack 60 min past cron). Bounded action vocabulary: `ACTION_AUTO_ENTERED / PROPOSED / AUTO_ENTER_FAILED / PROPOSAL_SEND_FAILED / SKIPPED / BLOCKED`. Silent-failure sweep: `_process_alert` crash handler now writes audit row first then attempts Telegram; `_record_subscribe_failure` Telegram-fail now logs; scheduler `_9m_scan_job` and `_9m_day2_orb_job` wrap with `notify_job_failure()` + per-candidate try/except; sugar baby state mismatch fixed (`auto_enter_failed` / `proposal_send_failed` now write `skipped` since they bypass `_on_skip`).

### 2026-04-24 (session 2) — ORB late-entry & fade guard
CHE gapped +17.9%, first crossed HIGH at 9:55 ET. Bracket placed at ORB high but tape had already faded — order would only fill on dead-cat retest hours later. Two fixes: (1) **Fade guard** in `_submit_orb_trade` — fetch latest trade before order; if `last_price < (orb_high + orb_low) / 2` skip with `SETUP_FADED_FROM_ORB`. Silent-on-feed-failure (don't block on data hiccup). (2) **Tightened submission window**: `now_et.hour == 9 and now_et.minute < 45` (was `< 10:00`). HIGHs at 9:45–9:59 → existing `WINDOW_OUT_OF_ORB` branch. (3) **10:00 AM ET cleanup job** `_orb_window_cleanup_job` cancels any `order_placed` still pending. New `SETUP_FADED_FROM_ORB` constant + `humanize()` entry. CHE order cancelled, INTC stuck-`filled` row cleaned up.

### 2026-04-24 (session 1) — OTO bracket stop-leg ID capture
INTC entered, 🚨 UNPROTECTED alert fired falsely, stop fired as `💱 Untracked SELL` not `❌ Stopped out`, no Day 1 re-entry. Root cause: four separate "find the stop leg" implementations, only one robust. `submit_entry` used strict `leg.get("type") == "stop"` — under Python 3.12 `str(OrderType.STOP)` returns `"OrderType.STOP"`, check silently fails, `stop_order_id` written as NULL. Cascade: WS fill handler can't match on NULL → routes to Untracked SELL → no `_process_stop_fill` → no re-entry. Fix: single canonical `alpaca_client.extract_stop_leg_id(order)` — uses `stop_price` as primary signal, case-insensitive `"stop" in type_str` fallback. Applied to all 5 sites. Defense-in-depth in `_process_entry_fill`: checks 3 sources (WS legs, DB stop_order_id, REST refetch) before standalone-stop remediation. Eliminates false UNPROTECTED alerts.

### 2026-04-23 (session 3) — Validation-window hardening
Three follow-ups for the 3-4 week paper validation window (target cutover 2026-05-23). (A) `Dockerfile.market` now `COPY scripts/ scripts/` so recovery scripts survive container rebuilds. (B) `_eod_ep_recap_job` now appends `📡 Feed (sip): N bars · M zero-range · K subscribe-fail · D disconnect`. Recap fires even on zero-HIGH days if any feed events occurred (catches silent SIP auth lapses). (C) New `scripts/readiness_check.py` encodes the 6 cutover gates as concrete SQL pass/fail (naked positions, reason-coverage invariant, silent audit errors, paper trade sample ≥ 10, regime not Crisis, feed health 24h).

### 2026-04-23 (session 2) — Env-var-gated SIP feed for ORB entry
URI ORB miss on 2026-04-22 traced to IEX feed (~2-3% of US consolidated volume) showing zero-range first-minute bars on mid-liquidity tickers. Phase 1: Alpaca Algo Trader Plus ($99/mo) → realtime CTA/UTP SIP consolidated tape. Env-var-gated via `ALPACA_DATA_FEED` (unset/`iex`/`sip`); resolved by new `alpaca_client.get_data_feed()` helper used by `get_first_bar()` and `start_bar_stream`. Code ships inert; flip activates when subscription is live. `scripts/verify_sip_parity.py` (hard-wires SIP independent of env) runs 4 pre-flip checks. **Validated: AAPL parity 0.037%, URI 2026-04-22 IEX=$0 → SIP=$4.20, 90d replay 1/1 recovered.** `ALPACA_DATA_FEED=sip` set in prod 2026-04-23. Polygon stays for grouped-daily/VIX/reference/backtester. Phase 2 trigger (Polygon Advanced $199 dual-feed): book size 5–10×, feed incident, OHLC reconciliation > 0.2% divergence, or second broker.

### 2026-04-23 (session 1) — Broker alert gaps + bracket-order hardening
**Naked positions (BSX/GSHD/SIRI):** `StopLimitOrderRequest(...stop_loss=...)` was submitted without `order_class=OrderClass.OTO` — alpaca-py silently drops `stop_loss` kwarg without it. Fix: `place_bracket_order` always uses `OTO` + verifies returned order has stop leg, cancels naked bracket if missing. **Silent state changes:** `_handle_cancel_or_reject` only alerted on `rejected`; manual Alpaca actions / `close_position` were logged and discarded. Three branches now: entry cancel/expire/reject, stop-leg cancel (clears `stop_order_id`, alert), untracked reject. `_handle_fill` untracked-sell branch parses `UPDATE N` rowcount → fires `💱 Untracked SELL/BUY` if 0 affected. `_process_entry_fill` belt-and-suspenders: places standalone stop or alerts UNPROTECTED. Managed exits in `order_manager` now `INSERT INTO mi_live_orders ON CONFLICT DO NOTHING` to avoid double-fire on the new untracked-sell alert.

---

## Changes Made — Historical (compressed log)

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
