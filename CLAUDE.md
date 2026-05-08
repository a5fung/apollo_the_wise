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

### 2026-05-05 (session 5b) — Flag detector dry-volume gate hybrid + queue cleanup (#188 + #163/#164/#189 verified + #177/#179 closed)
Five queue items resolved. Dates re-checked against today (2026-05-05 Tue): "tomorrow" in the source notes was 2026-05-04, so the verifications were already actionable today, not future.

**#188 — `_compute_fresh_tightening` dry-volume gate (`flag_detector.py`)**: prior code gated on `max(2bar vol) <= ADV20`. Climax-inflated for post-parabolic names — OKLO 5/4 hit 14.65M vs ADV20 15M = 0.98 (barely passing). Switched to hybrid ceiling `max(recent_avg_vol, 0.5 × ADV20)`: anchors on the contraction floor (matches `breakout_vol_ratio` denominator at L369, same SSoT shape) with a 0.5×ADV20 fallback so a single sub-average bar in the recent window can't over-tighten the gate. `recent_avg_vol` already computed at L349 (last 5 base bars); plumbed through as a kwarg. Falls back to ADV20-only when None for safety.

**Verifications (telemetry queries against prod 87.99.134.162)**:
- **#163 wick pending** — 11 NULL `filled_wick` rows in last 7d (RDDT 5/01, BTSG 5/01, FIVN 5/01, RLYB 5/04, CYTK/EQH/FCEL 5/05, etc.). Morning briefing job ran clean 5/04 + 5/05 09:00 ET. Section wiring verified.
- **#164 hedge downgrade** — 2 events fired today (EWTX 08:00 ET strong→routine, WAT 09:55 strong→routine). Wiring confirmed live.
- **#189 flag scan** — 5/05 17:25 ET run produced 576 candidates (matches predicted ~575 smoke), 5 COILED, 36 TIGHTENING, 3 fresh_tight_fires. Burst-inclusion + fresh path both populated.

**Closed without code change**:
- **#177 update_stop atomicity** — original motivation was the GOOGL/TEAM DB drift, but #180 root-caused that as the partial-exit commit-defer issue (now shipped). Remaining naked window during cancel-then-place is bounded by single-shot retry, WS rejection handler at `trade_stream._handle_cancel_or_reject` site 2 (marks stop_order_id=NULL + Telegram + 4:05 PM remediation), and 21:00 ET evening backstop. Textbook atomic fix is `PATCH /v2/orders/{id}` for stop-price-only updates — file-worthy if it ever bites in practice, not a current correctness gap.
- **#179 split _live_position_update_job 3:45/4:45** — bug class materially mitigated by #180 (commits deferred to WS fill) + 9:00 PM evening backstop. Folded into #217 P2 cleanup; not flip-blocking.

**Lesson**: "tomorrow" / "next day" in followup notes is a relative-date trap when conversations cross sessions. Always reconcile the note's authoring date with today before deciding actionability — telemetry that the note thought was 24h out may already be 2-3 trading days settled.

### 2026-05-05 (session 5) — P0.1 enum stringification site-local fix (#211) + #187 doc honesty
Two unblocked-today items shipped after querying live telemetry from this morning's 9:35 ET cycle.

**#211 — P0.1 status enum stringification (`live_tracker.py:565`)**: plan's pre-ship gate from session 4 (CLAUDE.md) called for confirming the `stop_update_started` empirical signature before patching the wire boundary. Today's prod telemetry showed both active positions (GOOGL #56, TEAM #57) firing `stop_update_started` at 9:35 ET with **identical from→to prices** ($379.43→$379.43, $82.79→$82.79) — the exact "fires for every active position every morning" shape predicted by the hypothesis. Root cause confirmed: `live_tracker.py:565` compared `order["status"] in ("new", "accepted", "held")` but Python 3.11+ stringifies `OrderStatus.NEW` as `"OrderStatus.NEW"` not `"new"` → the gate falls through every morning → `update_stop` re-cancels and re-places an already-active stop. Advisor recommended **site-local fix** (not SSoT at `_order_to_dict`): normalize at the comparison only — `str(order.get("status", "")).split(".")[-1].lower() in ("new", "accepted", "held")`. Filed followup for SSoT consolidation gated on auditing `order_manager.py:266` and `:521` polling readers for race shapes (re-enabling those readers may surface duplicate-fill or duplicate-stop-capture races the WS path has been masking).

**#187 — `get_flag_universe` trailing-10 semantics (doc honesty)**: prior docstring described path (b) burst inclusion as "trailing-10-session **return** ≥ 25%" but the SQL is `(last_close / trailing10_min - 1) >= 0.25` where `trailing10_min = MIN(close) FILTER (WHERE rn <= 10)` — i.e. "+25% above 10-session **low**", not a 10-session return. Path attribution from this morning: top-200 RS=200, burst via rs_1m only=583, burst via trailing-10 only=8 — the trailing-10 clause is near-inert. Hypothetical 30-session widen would add ~247, but advisor: "8 vs 247 on a 30-session widen is a regime change masquerading as a tweak. Update the docstring; close the task." Rewrote docstring + inline comment to state honestly what the SQL does and that rs_1m≥80 carries the burst path.

**Deferred (not bundled today)**:
- **#182** — morning_stop_refresh DB write skew. Investigation surfaced new shape: TEAM #57 has `stop_order_id=NULL` (write skew), but GOOGL #56 has `stop_order_id=bd965746…` while today's 16:45 audit shows the placed stop was `537e5bb2…` — different IDs. Advisor: "do NOT bundle today" — investigate the divergent-ID surface before patching.
- **SSoT enum normalization at `_order_to_dict`** — wire-boundary fix ships only after sites 2/3 race-shape audit confirms it's safe to re-enable polling readers.

**Lesson**: pre-ship empirical gates pay off when the plan author writes them. Session 4's plan note explicitly called for waiting one morning for the `stop_update_started` signature — it took ~12 hours to land decisively, and the signature was so clean (every position, identical prices, all sites) that the site-local fix was the obvious right shape over a wire-boundary SSoT change that would also flip on the polling readers and risk new race surfaces. The discriminator was the discriminator.

### 2026-05-05 (session 4) — Paper→live $ flip: wave 3 ship (P0.9 staged-paper banner + P1.5 /dryrun + P0.2 partial-fill telemetry)
Plan: `~/.claude/plans/shiny-mapping-locket.md` (paper→live $ migration). Wave 3 ships the deep-correctness items gated on the wave 1/2 verification work. Three pieces:

**P0.9 — Per-strategy real-$ gate (#214)**: `mi_strategies.live_real_enabled BOOLEAN DEFAULT FALSE` shipped earlier this session. Wired through to `send_trade_proposal` (`broker/telegram_confirm.py`) — when `current_account_mode() == "live" AND not live_real_enabled`, the Telegram proposal header swaps to `🟡 STAGED-PAPER ramp — confirm to enter REAL-$:` instead of the normal `📊 TRADE PROPOSAL`. `entry_pipeline._dispatch_proposal` reads `strategy.live_real_enabled` from the registry and passes it through. Manual Confirm tap is the actual safety gate; banner is decision-support. Flip-day plan: MAGNA53 → `live_real_enabled=True`; 9M Day 2 stays `False` until 30 clean MAGNA53 fills, then promoted via SQL/admin command. **Pre-implementation spike (#213)** confirmed 9M Day 2 already routes through the unified `submit_trade_entry` proposal flow at account=live (auto-enter is paper-only), so no separate proposal-flow build needed — the spike's worst-case scenario didn't materialize.

**P1.5 — `/dryrun` pre-flight command (#216)**: read-only Telegram command (`agent.py::_handle_dryrun`) that renders pre-trade sizing math against current Alpaca equity. Shows `mode_prefix()`, equity, buying power, PDT flag, daytrade count (fail-soft on Alpaca read), then for each `mi_live_trades` row from today recomputes hypothetical shares = `floor((equity * active_risk_pct) / risk_per_share)` capped at 20% position size, comparing to stored shares. Surfaces the QQQ-EMA half-risk gate (`active_risk_pct = RISK_PCT * 0.5 if qqq_bullish is False else RISK_PCT`). Routed via slash dispatch (`/dryrun` registered in `channels/telegram.py` CommandHandler) and NL keyword. Use case: night-before-flip — verify $10K live equity produces 1/10 the share counts paper $100K does, before flipping the env.

**P0.2 — Partial-fill telemetry (#212, visibility-only scope per advisor)**: plan asked for full deferred-commit handler for multi-partial fills. **Code audit found plan-vs-reality mismatch**: `trade_stream._handle_trade_update` had `partial_fill` as a pure log no-op (single `logger.info`) — no state mutation existed to break. Paper Alpaca atomic-fills, so this code path has zero production exercise. Advisor recommended option 4: ship visibility-only (audit + Telegram), defer the actual commit/state handler to first production occurrence so the design has real fill-shape data. New `_handle_partial_fill` emits `entry_partial_fill` audit event + Telegram with event_qty / cumulative_qty / avg_price / order_id. When the first real-$ partial fires, the operator gets paged to manually verify DB ↔ broker state; the deferred-commit handler is designed against that data, not against speculation. Task #212 renamed to "P0.2 partial-fill telemetry; full handler deferred to first production occurrence" — not closed silently.

**Lesson**: when a plan describes a bug that doesn't match the actual code, stop and reconcile before shipping the fix. Building a deferred-commit handler for the WS partial-fill path would have introduced state machinery against a no-op; harness-validating it against synthesized events would test the synthesis, not Alpaca's real fill shape. Visibility-first is the right shape for any code path with zero production exercise — emit telemetry, let one production occurrence inform the real design, then ship the handler against observed shape.

### 2026-05-05 (session 3) — Defer partial/full exit DB commit + Telegram to fill event (#180)
GOOGL/TEAM 2026-05-05: 16:45 ET `_live_position_update_job` triggered partial exits. Telegram printed "📤 Partial exit: GOOGL Sold 17 @$382.61 P&L $0.00 Remaining 34" and "📤 Partial exit: TEAM Sold 76 @$85.19 P&L $0.00 Remaining 153" — but no shares were sold. Market sells were queued for next-day's open (after-hours) and DB had been written with fake P&L=$0 against entry_price. Same shape as 2026-05-04's GOOGL #56 incident; yesterday's commit (7fe93d0) was *audit-logging only* — explicit "No logic changed", purpose was to capture today's recurrence with telemetry so #180 ("defer DB commit to fill event") could be fixed against real data.

**Root cause** (`broker/order_manager.py:887-928`, `:968-999`): `execute_partial_exit` and `execute_full_exit` committed to `mi_live_trades` synchronously after `place_market_sell`. Line 888: `fill_price = order.get("filled_avg_price") or trade["entry_price"]` — for orders queued after 4:00 PM ET market close, `filled_avg_price` is None, so fill_price collapsed to entry_price → P&L=0 → DB row marked `partial_taken=TRUE remaining_shares=new_remaining`, Telegram claimed sale. Cron at 16:45 ET (`scheduler.py:1811`) runs **45 minutes after close**, so this path was guaranteed to fire on every partial-trigger day.

**Fix — defer commit + Telegram to WS fill event** (matches the 2026-05-04 entry-pipeline "Order placed" rename for the bracket-fill class):
- `mi_live_orders`: + `purpose TEXT` ('partial_exit' / 'full_exit'), + `exit_reason TEXT`, + index. Lets the WS fill handler route by intent.
- `execute_partial_exit`: insert with `purpose='partial_exit'`, exit_reason='partial_profit'. **Removed** the post-submit DB commit + "📤 Sold X" Telegram. Sends "📋 Partial exit order placed (pending fill)" on placement. Stop replacement (smaller-qty stop ahead of the sell) unchanged — that's the safe ordering and stays in place.
- `execute_full_exit`: insert with `purpose='full_exit'`, exit_reason=reason. Same defer pattern. "📋 Closing order placed (pending fill)" on placement.
- New `finalize_partial_exit(trade_id, filled_qty, filled_price, order_id)` and `finalize_full_exit(..., reason)` in order_manager.py — contain the lifted commit logic against the **real Alpaca fill price**. Idempotent (no-op if order_id already in `exits[]`).
- `trade_stream._handle_fill` step 3 rewrite: atomically claim mi_live_orders via `UPDATE ... WHERE alpaca_order_id=$1 AND status NOT IN ('filled','cancelled') RETURNING trade_id, purpose, exit_reason, qty`. Routes to the right finalizer. NULL purpose = legacy (pre-fix) row, falls through silently.
- `trade_stream._handle_cancel_or_reject` new step 3: when a pending partial-exit sell is cancelled/rejected/expired, restore the stop to full `remaining_shares` (the smaller stop placed before the sell would otherwise leave shares unprotected). Same path for full-exit cancel — re-place the stop using the persisted `mi_live_trades.stop_price`.
- Submit-time **dedup safeguard**: both executors now bail if there's already a pending partial/full exit order for the trade in mi_live_orders. Without this, a queued sell from yesterday's cron + today's cron firing again would stack a duplicate.

**Audit events**: `partial_exit_committed` and new `full_exit_committed` now fire from the finalizers on real fill, not at submit time. Submit-time `partial_exit_sell_placed` unchanged.

**Today's already-submitted GOOGL/TEAM rows** (before this fix shipped) carry `purpose=NULL` in mi_live_orders. When tomorrow's open fills them, the WS handler hits the NULL-purpose branch and silently logs — no double-commit, no FILLED Telegram. The DB rows from 16:45 ET still carry the wrong P&L=0 entries. Manual cleanup if desired; not auto-corrected because retroactively assigning purpose to legacy rows is fragile.

**Lesson**: "Order accepted" ≠ "shares sold" — most acutely when the cron runs after close. The 2026-05-04 commit (audit-logging-only) was the right intermediate step: ship telemetry, let the bug recur once with full instrumentation, then fix against real data instead of guessing. Same shape as the 2026-05-04 entry-pipeline fix ("EP entered" → "Order placed") which separated placement language from fill confirmation. Apollo's daily schedule has multiple after-close cron points (4:05/4:10/4:15/4:45/5:00 PM); any code path that places a market order from those crons must defer commit + user-visible language to the WS fill event, not the placement response.

### 2026-05-05 (session 2) — compute_atr_14: close-to-close → Wilder TR (STRL/BAND skip class)
STRL 2026-05-05 ORB skipped with `setup:stop_too_wide`: ATR-14 came back $13.55 (close-to-close approximation), 1.5× gate $20.33 < ORB range $35.02. Real Wilder TR ATR is $24.52 → 1.5× $36.78 > $35.02 → entry passes. `backtester/filters.py::compute_atr_14` was reading only `close` and using `abs(close - prev_close)` as TR — silently understated on volatile/gappy stocks where intraday range >> close-to-close. `flag_detector._atr_14` had used proper Wilder TR all along; the two had drifted out of SSoT.

**Fix**: `compute_atr_14` rewritten — reads H/L/close from `mi_daily_closes` (OHLC since 2026-04-25 backfill), computes `TR = max(H-L, |H-prev_close|, |L-prev_close|)`, simple mean of last 14 (matches `flag_detector._atr_14`). Lookback widened 30→35 days to comfortably cover 15-bar window after weekends/holidays. `len(rows) < 10` floor unchanged.

**Verification**: prod has 320,821 rows in last 40d, zero NULL H/L; cold tickers <14 rows are SPAC units (CHACU, IPCXU) filtered by ADV gate. 30d replay (`scripts/replay_stop_too_wide.py`): all 4 `setup:stop_too_wide` skips (BAND 4/30, TTMI 4/30, EVER 5/05, STRL 5/05) pass under new ATR; 2/2 settled cases positive (BAND +27.7%, TTMI +4.3% 5d max-high), today's STRL/EVER pending settlement ~5/12.

**Backtest/live asymmetry (acknowledged, parked)**: backtester reads `as_of_date` H/L too, so backtests include the alert-day gap TR. The 9:31 AM live path only has through prev close (today's bar not in `mi_daily_closes` yet). TV's $43.25 reflects today's gap; Apollo's pre-open ATR cannot. Part 2 (wire today's gap TR via ORB bar + prev_close) NOT shipped — 30d replay shows zero cases where the new Wilder TR still rejects, so no evidence base. Filed as #199; trigger: any future stop_too_wide skip the new gate also rejects on a ticker that subsequently runs.

**SMA vs RMA**: TV uses Wilder smoothing (RMA); shipped SMA to match `flag_detector` SSoT. Deliberate — one ATR shape across the codebase beats matching TV's specific number on one ticker.

**Lesson**: when two implementations of the same conceptual computation drift (flag_detector did Wilder TR; backtester did close-to-close), the stale one isn't merely "less precise" — it silently inverts the gate's coverage on the exact pattern it's supposed to surface. Volatile/gappy stocks are the EP candidates; close-to-close is the worst possible shape on that population. Fix is the SSoT alignment, not a threshold tweak.

### 2026-05-05 — Earnings-day HIGH override (DOCN miss → yfinance backstop on tier decision)
DOCN 2026-05-05: gap +30%, Q1 earnings beat pre-market → catalyst classifier rated `routine` because FMP/yfinance news ingest hadn't caught the announcement at scan time. Score landed below threshold; never alerted. Pattern is recurring: 30 settled misses since 4/14 with `gap≥10 + catalyst=routine + score-blocked`, every one of them positive at 5d max-high (+11.9% to +113.5%). The catalyst classifier grades textual news_summary; when news ingest lags the announcement, a qualifying gap silently scores below threshold even though the tape is shouting.

**Fix**: `agents/market_intelligence/earnings_calendar.py` — `is_earnings_day(ticker, scan_date) -> (bool, source)`. Combines yfinance `Ticker.earnings_dates` (historical) and `.calendar` (forward-looking next event); match if any timestamp falls within ±1 day of scan_date (covers AH-on-T-1 and BMO-on-T gap shapes). Per-process `(ticker, scan_date)` cache because the EP scan fires every 5 min from 7:00–10:00 ET — without cache the same ticker would hit yfinance ~36× per morning. yfinance calls run in `asyncio.to_thread` (sync library).

**Override** in `ep_detector.py` at the tier-decision site (post-score, before result append): when `tier == MODERATE AND gap_pct >= 10`, call `is_earnings_day`. On match → promote `tier = HIGH`. Three audit events (separate, not combined — needed to distinguish surfaces): `earnings_override_applied` (with `source` ∈ `{earnings_dates, calendar}`), `earnings_override_no_match` (yfinance returned data, no window hit), `earnings_override_unavailable` (yfinance raised on both surfaces). Extension and M&A gates are upstream — extension at `MAX_EXTENSION_PCT=50` filter (line ~757), M&A via `is_likely_ma` (line ~824) — anything reaching the tier-decision site has cleared both, so the override doesn't re-check. **No `game_changer` exclusion**: in non-Bull regimes (threshold 70), gap 10–14% + game_changer hits conviction floor 60 → MODERATE, which is exactly the textbook qualified EP the override exists to promote. Negative-path events (`no_match` / `unavailable`) are deduped per `(ticker, scan_date)` via in-process `_audit_dedupe` — without it, the same ticker would emit ~36 rows/day across the cron ticks. The `applied` event auto-dedupes (tier flips to HIGH → next tick the candidate hits `already_today` and is skipped before reaching the override).

**Tape-conviction shadow** (forward-only telemetry, no scoring change): when `gap_pct >= 12 AND projected_vol_multiple >= 5x`, emit `tape_conviction_shadow` regardless of catalyst grade. Gives a baseline for evaluating a future tape-only override after N samples — couldn't retro-validate today because `vol_proj` is NULL on 24/27 historical miss rows (universe widened 2026-05-03; pre-fix rows have no projections).

**Canary verified pre-deploy**: `is_earnings_day("DOCN", date(2026,5,5))` returns `(True, 'calendar')` — the trigger case. AAPL returns `(False, 'no_match')`. yfinance `.calendar` is the load-bearing surface; `earnings_dates` alone misses fresh announcements.

**Non-goal explicit**: ~40% of the historical miss population are deal/sympathy gaps (POET, FCEL, MANE, BB, AMD, QCOM 4/24 sympathy moves on Mag-7 catalysts). yfinance has no signal for those. Another ~6/27 are real earnings where yfinance has the wrong date (small-cap pharma drift — HTZ 4/30→5/07, BBIO 4/28→5/07). This fix targets earnings-day gaps yfinance can identify (~14/35 of misses); the remainder is out of scope and stays uncovered. Methodology claim is "gap + earnings = qualified HIGH per Pradeep Bonde framework" — downside bounded by ORB stop-limit + 10:00 ET cancel + ATR stop, not a winning predictor.

**Lesson**: chained classifiers grading textual news are coupled to ingest latency, not to the underlying event. The fix isn't a smarter classifier or a tighter threshold — it's a structurally independent second source (calendar API) that knows the event happened even when the news scrape doesn't. Same shape as the 2026-05-04 AVNS Polygon backstop and the 2026-05-03 hedge-phrase downgrade. When the LLM-only pipeline admits doubt or returns nulls, the override needs a non-LLM data source whose answer is "yes/no this event existed" — not another LLM grading the same hollow input.

### 2026-05-04 (session 7) — ORB-extension shadow telemetry (decision-support for cutoff change)
Lifecycle analysis on N=5 cancelled-ORB-window trades (`orb_extension_lifecycle_report.md`) was inconclusive — the 14:00→16:00 swing of $1,101 was a single TWLO leg. User direction: *"yes, let's shadow and put in reminder to review when data ready."* Built shadow infrastructure that records counterfactual lifecycle for every future 10:00 ET ORB cancellation across 6 cutoffs (10:00/11:00/12:00/13:00/14:00/16:00).

**Components**:
- `mi_orb_extension_shadow` table: PRIMARY KEY id, UNIQUE (trade_id, cutoff_minute), JSONB `state` for mutable resume (running_closes, partial_taken, breakeven_active, hard_stop, remaining_shares, exits). 6 rows per cancellation.
- `agents/market_intelligence/broker/orb_extension_shadow.py`: `record_shadow_for_cancellation` (Day-1 sim, 6 cutoffs share one bar fetch) + `settle_open_shadows` (resumes via `apply_daily_exit_step` from `last_evaluated_date+1`).
- Hook in `cancel_unfilled_entries` (order_manager.py) — gated on `event_type == "orb_unfilled_cancelled"` so 4:05 PM EOD cancellations are EXCLUDED (different decision question). Fire-and-forget via `asyncio.create_task` so the 10:00 ET cron isn't blocked by 6×Polygon fetches.
- Settlement appended to `_nightly_data_pull` (after mi_daily_closes refresh, before failure check). Audit event `orb_extension_shadow_settled` carries reviewed/settled/still_open/errors.
- Data-gated review `orb_cutoff_extension`: `COUNT(DISTINCT trade_id) >= 20`, earliest_review_date 2026-07-15. Decision rule (advisor): cutoff extension justified only when later cutoff dominates 10:00 on BOTH mean AND median.

**Sim honesty**: fill threshold uses `stop_limit_buy_price(stop)` (SSoT helper) — high must reach the LIMIT price, not just the stop trigger. Matches live broker semantics.

**Lesson**: a counterfactual decision needs counterfactual data. Single-anecdote cases (TWLO) generate noise that survives any aggregation small enough to compute today. The fix is not "wait until N=20 organically" — it's "record now so when N=20 arrives the data exists." Telemetry-first is the same shape as continuation flag (shipped 2026-05-01) and fishhook V3 (shipped 2026-04-30): build the recording layer before deciding the policy.

### 2026-05-04 (session 6) — Flag detector: burst-class universe + fresh-tightening COILED path (OKLO miss)
User flagged OKLO forming a visible flag with no detector hit. Replay (`scripts/backfill_flag_xndu.py --ticker OKLO`) surfaced **two structural gaps**:

**Gap 1 — universe gate excluded OKLO.** rs_rank=981 because raw_6m=-7.4% drags composite, despite rs_1m=94.3 (top 5.7%) and trailing-10 +42.5%. `get_flag_universe` was top-200 RS only; structurally inverts coverage for post-runup names whose 6M is dragged by the pre-runup downtrend (the very signal we're trying to catch).

**Gap 2 — contraction math can't fire on short bases.** With `base_age=6`, early-window (first 5 bars) and recent-window (last 5 bars) overlap 4 of 5 — ratio mechanically stuck near 1.0 even when the last 2 bars are visibly tighter. OKLO 5/4: bars 1–4 of base were whippy (4/24 reversal, 4/29 11.4%, 4/30 10.5%), 5/1 + 5/4 were 4.6% / 5.5%. User's eye picks up the recent tightening; metric can't.

**Fix**: two parallel paths, ship together.

(a) **`get_flag_universe` burst inclusion** (`db.py`): adds OR-clause `rs_1m_pct >= 80 OR (last_close / trailing10_min - 1) >= 0.25` alongside existing `rs_rank <= 200`. Uses `PERCENT_RANK() OVER (ORDER BY rs_1m)` to compute per-scan rs_1m percentile (no precomputed column). Common gates ($5+, $5M ADV20, ≥60 sessions, CS/ADRC) unchanged.

(b) **Fresh-tightening COILED path** (`flag_detector.py`): new helper `_compute_fresh_tightening(rows, today_idx, base_age)` returns `(fires, fresh_2bar_max_tr_pct, atr14_pct)`. Predicate: `base_age ≥ 4 AND max(2bar TR%) ≤ 0.6 × ATR14% AND max(2bar vol) ≤ ADV20`. Promotes to COILED via OR — either existing `(range_tight AND vol_tight)` OR `fresh_fires` qualifies. Both paths still require `bodies_tight AND ma_aligned`. Threshold 0.6 calibrated against OKLO 5/4 (ratio 0.54 fires) + XNDU 4/29-4/30 (ratio 0.62-0.64 doesn't fire — but existing path already catches XNDU; no double-fire, no regression).

**Schema**: 3 additive columns on `mi_flag_candidates` (`fresh_tight_fires BOOL`, `fresh_2bar_tr_pct FLOAT`, `atr14_pct FLOAT`). All `unqualified` rows still persist for offline tuning. ALTER TABLE IF NOT EXISTS pattern.

**Replay verified** (`scripts/replay_flag_fresh_tighten.py` + existing `backfill_flag_xndu.py`):
- XNDU progression unchanged: WATCH→TIGHTENING→COILED→TRIGGERED→INVALIDATED, every date identical
- OKLO 5/4: WATCH → **TIGHTENING** (fresh fires, but `ma_aligned` fails because close $68.60 < SMA-10 ~$70.4). Reason string: `"range_0.95 vol_0.85 fresh"`. Promotes to full COILED once price re-aligns above SMA-10 (climax bars rolling out).

**Lesson**: the user's framing ("on my watchlist, not actionable yet") matches what the system now correctly emits — TIGHTENING means "structure forming, not positioned for breakout"; COILED means "coiled AND positioned"; TRIGGERED means "go." Pre-fix the system silently gave WATCH for both "no structure" and "structure forming but base too short to detect" — same bucket, two different traders' situations. Fix isn't a threshold relaxation; it's an alternate predicate aimed at the specific shape (short base, tight tail bars, post-runup) where the original metric is mathematically blind. Same shape as the 2026-05-03 hedge-phrase downgrade and the AVNS Polygon backstop — a structurally independent second source closes a coverage gap the original gate can't see by design.

### 2026-05-04 (session 5) — Cleanup queue: zombie themes, cancel_unfilled_entries audit, #183 filed
Three small, low-risk items advisor-scoped from today's working queue:

**(a) Zombie theme retire** — 42 themes on prod with latest theme_date < CURRENT_DATE − 7d but stage NOT 'Retired'. Idempotent UPDATE via DISTINCT ON (name, theme_date) — single-shot fix for pre-recency-cap stuck rows. Recency cap (`get_active_themes(stale_after_days=7)`) is the de-facto retirement going forward. `mi_themes` has no `last_seen` column; cleanup query had to derive latest-per-name from `theme_date`.

**(b) `cancel_unfilled_entries` audit logging** — `order_manager.py:1003`. Cancel-failed path was silent `logger.warning + return False` (no audit event, no Telegram). Now emits `orb_unfilled_cancelled` / `eod_unfilled_cancelled` on success and `unfilled_cancel_failed` on failure (per-ticker), plus a grouped Telegram alert on the failure path. TEVA 4/30 anomaly investigation hook — the next time the 10:00 ET cleanup misses a row, we'll have telemetry instead of inferring from row state.

**(c) #183 filed** — `mi_live_orders` status enum stringification. `alpaca_client.py:470::_order_to_dict` returns `str(order.status)` which Python 3.11+ stringifies as `'OrderStatus.NEW'` (not `'new'`). Three reader sites silently broken: `live_tracker.py:481` (morning_stop_refresh stop-still-active gate — falls through to update_stop EVERY active stop EVERY morning, plausibly #182's root cause), `order_manager.py:266` (check_fills polling), `order_manager.py:521` (check_day1_stopouts). WS path covers sites 2/3 in practice. **Empirical signature for tomorrow 9:35 ET**: if the new `stop_update_started` audit event (shipped session 4) fires for **every** active position, site 1 is confirmed → ship the SSoT fix at the wire boundary (`str(order.status).split(".")[-1].lower()`). Fix held tonight to preserve the discriminator in tomorrow's telemetry.

**Closed false alarms**: #181 (Day-1 re-entry row reuse — `exits` JSONB preserves attempt-1 stop-out outcome; only `status` and `entry_*` are overwritten, no data loss); AEHR mi_stock_scores spot-check (RS rotation 3→7→23→71 is normal momentum-name behavior, not a coverage bug).

**Lesson**: same shape as the 2026-05-04 reconcile_orphan_stop fix — Python 3.11+ enum stringification is a single root cause masquerading as N decoupled bugs. SSoT normalization at the wire boundary (one line in `_order_to_dict`) is the right fix; per-site comparison patches would just multiply the surface area. But re-enabling polling readers may surface a separate duplicate-event problem that the WS path was masking — design call after telemetry confirms.

### 2026-05-04 (session 4) — Audit logging in `update_stop` + `execute_partial_exit` (GOOGL/TEAM 5/4 silent-failure surface)
GOOGL/TEAM 5/4 incident: TEAM #57 child stop never captured into DB after Day-1 re-entry (4/24-class OTO bug recurrence — manually reconciled today via `scripts/reconcile_orphan_stop.py`); GOOGL #56 partial-exit attempt at 16:45 ET ACCEPTED a 17-share market sell that never filled (after-hours queue), leaving DB row in inconsistent state (total_pnl=10.88 but exits=[] and partial_taken=f). Investigation surfaced that **both `update_stop` and `execute_partial_exit` had zero audit-log writes** — every failure path was silent (logger.warning + return False). Without telemetry there's no way to distinguish a genuine partial-fill drift from a benign retry.

**Fix**: purely additive `log_audit_event` instrumentation across both functions in `broker/order_manager.py`. 7 sites in `update_stop` (`stop_update_started/aborted/cancel_failed/failed/retry_succeeded/updated`); 9 sites in `execute_partial_exit` (`partial_exit_started/aborted/stop_replaced/sell_placed/sell_failed/rolled_back/rollback_failed/committed`). Each event carries trade_id, ticker, broker order IDs, and the relevant state delta as JSON detail.

No logic changed. The point is to capture tomorrow's `morning_stop_refresh` (9:35 ET) + the next partial-exit run (16:45 ET) so #180 (defer DB commit to fill event) and #182 (morning_stop_refresh DB write skew) can be investigated against real telemetry instead of post-hoc state archeology.

**Filed for follow-up**: #181 Day-1 re-entry row reuse loses original closed outcome (TEAM #57 stop-out at 10:21 vanished when 11:21 re-entry overwrote `status='filled'`); #182 morning_stop_refresh DB write skew (placed broker stop but mi_live_trades.stop_order_id stayed NULL — symptom of TEAM 5/4 surface).

**Lesson**: silent return-False paths in trading-side functions violate the no-silent-failure rule. Audit logging is the bare minimum before any defer/rollback refactor — without it, "did the rollback work?" is unanswerable.

### 2026-05-04 (session 3) — SSoT M&A filter (AVNS slip → ma_filter.py + Polygon backstop)
AVNS appeared in flag scan as COILED on 2026-05-04 — but it was a 4/14 take-private deal pinned at $24.62-72 across 14 sessions (daily ranges 4-15¢ = bid-ask noise floor, 0.16-0.6% of close). EP detector's existing M&A filter at `ep_detector.py:818-852` (`_MNA_KEYWORDS` + `catalyst_quality=='mna'`) didn't fire because Perplexity returned "no specific news or catalysts" for AVNS 4/14 → catalyst_quality='routine' → keyword scan had no text to match. **Same hedge-phrase failure mode the 5/3 catalyst_pplx_hedge_downgrade fix targeted, but the downgrade only acts when Claude *also* graded it strong; here Claude saw nothing either, so no signal to downgrade.**

Polygon news endpoint had it the whole time: Benzinga 2026-04-14 "Avanos To Go Private In $1.27 Billion All-Cash Buyout" + GlobeNewswire 4/15 Halper Sadeh shareholder-investigation followup. Both titles trivially match `_MNA_KEYWORDS` (`"buyout"`, `"go private"`).

User direction: *"We already have a way to filter out M&A, why can't we use the same everywhere? ... no point writing up the heuristic everywhere when we should filter out real M&A for all setups."* Three layers, advisor-split into now/later:

**L0 (root cause, shipped)**: `collector.py::get_polygon_news(ticker, lookback_days, on_or_before)` — wraps `/v2/reference/news`, returns headline list, fails graceful (empty list, never raises). Closes the Perplexity coverage-gap as a free backstop.

**L1 (SSoT refactor, shipped)**: new `agents/market_intelligence/ma_filter.py` with `matches_mna_keywords(text)`, `polygon_news_has_mna_headline(ticker, ...)`, and `is_likely_ma(ticker, *, catalyst_quality, catalyst_texts, check_polygon, on_or_before)`. Single canonical `_MNA_KEYWORDS` tuple (17 entries — added "to go private", "all-cash buyout", "halper sadeh"). Three layered sources, cheapest first: (1) `catalyst_quality=='mna'` Claude verdict, (2) keyword scan over supplied texts, (3) Polygon headlines. Returns `(is_mna, telemetry_dict)` with `source` field so audit events distinguish "Claude flagged it" from "we caught it via Polygon despite Perplexity hedging."

EP detector refactored to call `is_likely_ma` (~25 LOC removed; `mna_filter_fired` audit now carries `source` so post-mortem can split EP catalyst hits from Polygon-backstop hits). **Flag detector wired** at `flag_detector.py:447-481` — only COILED + TRIGGERED candidates run the check (≤20 tickers/day vs ~200 universe). Filtered candidates downgrade to `unqualified` with reason `mna_filter:<source>`, re-upserted to `mi_flag_candidates` so offline review can audit hit rate. Single-ticker TRIGGER alerts fire AFTER the flip, so M&A-flipped TRIGGEREDs no longer ping.

**L2 (deal-pin price signature, filed as data-gated review)** `flag_ma_pin_filter` in `data_gated_reviews.yaml` — predicate `COUNT(COILED) >= 30` over 60d, ready 2026-06-15. Action: query median `(H-L)/close` across 14d-base sessions; ship 0.3% gate only if ≥3 distinct names hit floor AND ≥2 confirm M&A on manual review. L0+L1 should suffice in steady state; L2 only if Polygon coverage proves leaky.

**Not wired in this PR**: 9M and parabolic detectors. Advisor blocking concern — wiring 4 detectors at once changes output distribution; ship EP+flag, watch one cycle of `mna_filter_fired` audit events, then extend.

**Lesson**: chained LLM-only catalyst lookups silently couple coverage to one provider's blind spots. The 5/3 hedge-phrase downgrade caught the case where Perplexity admits nulls; AVNS surfaced the harder case where *both* classifiers see nothing because their input is empty. The fix isn't a smarter classifier — it's a structurally independent second source (Polygon news), composed via a single SSoT filter so every detector benefits without per-detector reinvention. Same shape as the 5/4 limit-buffer SSoT cleanup: 7 hand-rolled `* 1.001` sites was six too many; one M&A keyword list per detector would be N too many.

### 2026-05-04 (session 2) — Group skip Telegrams per strategy
Skip messages from `submit_trade_entry._skip` were one Telegram per ticker, per cron run. On a heavy morning the ORB monitor could spit 6–10 individual skips into the chat — noise that buries the actual entries/blocks. Same problem on the 9M Day 2 cron at 9:31 ET.

**Fix**: new `aggregate_skips: bool = False` param on `submit_trade_entry`. When True, `_skip` writes the DB row and audit event but skips the per-ticker Telegram. Both batched callers (MAGNA53 `process_new_alerts_live`, 9M Day 2 `_9m_day2_orb_job`) pass `aggregate_skips=True` and emit one grouped digest after `asyncio.gather`:

```
⏭️ ORB skips (2026-05-04, 4)
• `TEAM` — Already have open position in ticker (open since 2026-05-01)
• `CCC`  — Stop too wide for risk budget (ORB $0.40 vs 1.5x ATR $0.21)
• `XYZ`  — No opening bar from data feed
• `ABC`  — Daily loss limit hit ($-512 >= $400)
```

Also suppressed the upstream `check_filters` per-ticker Telegram in `_process_alert` (live_tracker.py:213) — it was a parallel skip path that bypassed the pipeline `_skip` and therefore wasn't covered by the new flag. Returning `{"action": "filtered", ...}` instead, captured by the same digest. Default param is False so any future single-shot caller (manual retry, /why, etc.) keeps per-ticker pings.

**Lesson**: Telegram economy. Trading-system Telegrams should be terminal/actionable (entries, fills, cancellations, blocks worth one ping); informational batches (every-skip-with-reason) belong in a digest. The existing per-ticker pings violated that rule for fan-out flows where 5–10 evaluations are normal. The DB row + audit event remains the durable record; Telegram is the human-attention surface.

### 2026-05-04 (session 2) — Per-ticker open-position guard (TEAM 5/04 double-entry near-miss)
TEAM 5/04 9M Day 2 placed a bracket order at 09:32 ET while a MAGNA53 5/01 fill in TEAM was still open with shares. Order cancelled unfilled at 4:05 PM EOD — but if it had triggered, exposure would have doubled. Investigation: same-day dedup at `entry_pipeline.py:200` only blocks `(ticker, alert_date)` collisions; safeguards block on count cap, daily loss, circuit breaker — none check per-ticker open positions across days/strategies.

**Fix**: new check at entry_pipeline.py right after same-day dedup. SELECT for any prior `alert_date` row with `ticker=$1 AND status='filled' AND remaining_shares > 0`. If found, `_skip` with `BLOCK_TICKER_OPEN_POSITION` (new constant in `skip_reasons.py`, human label "Already have open position in ticker"). Reason carries the prior alert_date for context (e.g. `block:ticker_open_position: open since 2026-05-01`). Action = `ACTION_BLOCKED`, icon = 🚫, audit event `orb_blocked` — matches strategy-disabled / shadow-phase block semantics.

**Why `status='filled' AND remaining_shares > 0`**: canonical "we own shares" signal — matches `update_open_positions_live`. Stuck `order_placed`/`pending_confirmation` rows from prior days don't block (they're stale state, not real exposure).

**Lesson**: trade-level dedup keys ≠ exposure-level dedup keys. `(ticker, alert_date)` is the right primary key for the alert table but the wrong gate for "should we open another position." Two strategies can each see a fresh alert on the same ticker, both pass same-day-duplicate, both pass count/loss safeguards, both fire orders. The exposure check has to live at the position level (status + shares), not the alert level.

### 2026-05-04 (session 2) — Parallelize 9M Day 2 cron + drop bar-retry delay (TEAM 5/04 root cause)
Re-investigated TEAM 5/04 unfilled after track-1/2/3 ship. **Real root cause was not bar-fetch latency or TEAM-specific** — it was the 9M Day 2 cron's sequential for-loop. SOUN hit `bar_miss` at 09:31:00.150, slept 60s in `fetch_orb_bar_with_retry`, finished at 09:32:00. TEAM was queued behind it; its bar fetched at 09:32:00.654 immediately after SOUN unblocked. Architectural discrepancy: MAGNA53 fans out via `asyncio.gather` over alerts (`live_tracker.py:241`), 9M Day 2 ran a `for candidate in candidates: await submit_9m_day2_trade(c)` — same pipeline, divergent fan-out.

**Fix 1** (`scheduler.py::_9m_day2_orb_job`): replaced for-loop with `asyncio.gather(*..., return_exceptions=True)` + `Semaphore(5)`, mirroring MAGNA53. Per-candidate try/except moved inside the inner coroutine — preserves "one ticker's crash never strands the rest" semantics. Verified `submit_9m_day2_trade` is concurrent-safe: per-ticker `update_9m_sugar_baby_status(ticker, alert_date, status)` updates only, no shared state.

**Fix 2** (`entry_pipeline.py:39`): `BAR_RETRY_DELAY_SEC = 60 → 10`. Defense in depth even after parallelization. Bars settle in seconds, not minutes — 60s was wrong on its own merits. Switching 9M Day 2 to bar_stream wouldn't have helped (same `fetch_orb_bar_with_retry`; INTC 4/24 audit shows bar_stream also hits the retry path).

**Lesson**: two strategies sharing a unified pipeline must also share fan-out shape. The unification at `submit_trade_entry` (2026-04-24 s3) bundled the per-trade work but left the per-batch driver loop strategy-local — and the two drivers drifted. Anytime the same conceptual operation runs in N places (entry, bar fetch, stop-leg ID, limit buffer, fan-out), centralize or at minimum mirror; otherwise one will eventually develop a latency/correctness gap the other doesn't.

### 2026-05-04 — Bracket fill messaging + stop-limit buffer (TEAM 5/04 unfilled)
User reported "TEAM entered" Telegram 5/04 but Alpaca showed no fill. Investigated 4 unfilled-cancellations 4/28→5/04: TEAM (gap-through, cron 60s late), CCC (penny-spread, in-time but limit didn't cross), TWLO + TEVA (never retriggered — pattern failures, not code-fixable). Two-track fix.

**Track 1 — Messaging**: "auto-entered" Telegram fired at order PLACEMENT regardless of fill. Three states already wired downstream (placed in `entry_pipeline.py:341`, filled in `trade_stream.py:332`, cancelled-unfilled in `order_manager.py:850`); only the "placed" copy was misleading. Renamed `success_title` defaults: "Paper trade auto-entered" → "Order placed", "EP entered" → "EP order placed", "9M Day2 entered" → "9M Day2 order placed". Body now reads "Stop-limit BUY @ $X (pending trigger)" with footer `_Fills if price ≥ $X; cancels 10:00 ET if unfilled._` — semantics explicit.

**Track 2 — Buffer + SSoT cleanup**: 7 sites in `order_manager.py` hand-rolled `round(orb_high * 1.001, 2)` for stop-limit BUY. Penny tickers: at $5.49, 0.10% buffer = $0.0055 → rounds to $5.50 → 1¢ effective buffer; thin spreads don't cross. Single helper `stop_limit_buy_price(stop)` returns `round(max(stop * 1.005, stop + 0.02), 2)` — 0.5% with $0.02 floor. Replaced all 7 sites. CCC $5.49 → $5.52 limit (3¢ vs 1¢); TEAM $88.88 → $89.32 (44¢ vs 9¢).

**Acknowledged limit**: buffer fix doesn't address pure gap-through. TEAM 5/04 cron was 60s late (9:32:00 placement, by then last $89.58 with ask $89.59+); even at 0.5% buffer ($89.32 limit) wouldn't have crossed. Real gap-through fix is reducing `BAR_RETRY_DELAY_SEC=60` — separate followup.

**Track 3 — Filed**: TEVA 4/30 cancelled with `EOD unfilled` (4:05 PM cleanup), not `ORB window unfilled` (10:00 ET cleanup). Means 10:00 cleanup didn't pick TEVA up — investigate query filter or scheduler gap. Added to `project_next_followup.md`.

**Lesson**: misleading user-facing wording masked an existing-but-correct downstream fill confirmation pipeline. Fix was 4 string edits, not new infrastructure. Separately: any per-share buffer formula that scales linearly with price needs an absolute floor — `round()` to 2dp + sub-$5 stop = no-op buffer. SSoT: 7 hand-rolled `* 1.001` sites is six too many.

### 2026-05-03 — Catalyst hedge-phrase downgrade (Track B Layer 2)
RDDT 5/1 catalyst pipeline returned "strong" with Evercore-initiation blurb instead of identifying the real driver (Q1 earnings beat). Symptom traced: when `search_news_perplexity()` synthesis comes back hedged ("no specific information about RDDT", "couldn't find recent news"), the hollow `news_summary` still gets passed to BOTH classifiers (Claude on `all_news`, Perplexity validator). Both can return "strong" because they're grading a stub — the prompts ask for classification, not "is there enough signal here to classify."

**Fix** (`ep_detector.py` _evaluate loop, after agreement-boost block): scan `perplexity_answer` for hedge phrases (9-phrase tuple incl. "no specific information", "couldn't find", "search results don't contain", etc). When detected AND `catalyst_quality ∈ {game_changer, strong}`, downgrade one notch (`game_changer→strong`, `strong→routine`), cancel the 1.2× agreement boost, and emit `catalyst_pplx_hedge_downgrade` audit event with from/to/excerpt. Single override point at the consolidation site — both classifiers run unchanged, the downgrade is a post-hoc skepticism layer.

**FMP verification deferred**: advisor's Layer 1 was "verify RDDT actually had earnings 4/30 via FMP before describing this as a missed-earnings bug." Tested `stable/earnings-calendar` on the current subscription tier — returned ~10–14 entries/week, no RDDT in any window 4/15–5/17. Endpoint likely filtered to S&P 500 / large-caps. Layer 3 (FMP earnings-window pre-check biasing the Perplexity prompt toward earnings as catalyst) is filed in `project_next_followup.md` with the coverage caveat — needs an alternate earnings source for mid-caps before it's actionable.

**Lesson**: chained LLM calls hide their own data quality. The first call (Perplexity search) self-acknowledges nulls in prose; the second call (classifier) reads that prose as input data and grades it. Without a hedge-phrase guard in between, the system's confidence is decoupled from actual evidence. Defensive read: when an LLM in the chain admits uncertainty in natural language, downstream consumers must parse that uncertainty as a signal, not as content.

### 2026-05-03 — Forward-looking wick surfacing (Track A)
RDDT formed a wick on 5/1 (Fri close), but no surface flagged it Monday morning as a break-of-prior-high candidate. Root cause: existing wick surfaces (`friday_watchlist._fetch_wick`, evening briefing wick line) only count rows where `filled_wick = TRUE`. The `wick_tracker._wick_forward_returns_job` waits 10 forward sessions before populating `filled_wick` (line 98: `if len(session_rows) < _HORIZON_DAYS: continue`), so freshly-fired wicks remain `NULL` for ~2 weeks — invisible to the trader during the actionable window.

**Fix**: new `db.py::get_wick_pending_candidates(lookback_sessions=3)` returns `filled_wick IS NULL` rows where `prior_high` hasn't been broken yet (intraday `NOT EXISTS` clause closes the already-filled blind spot). New `WICK_PENDING` priority slot in `friday_watchlist.py` (priority=4, above settled WICK=5); section header "🪝 Wick Pending — break-of-prior-high"; reason chip format `"Pending May 01: break > $173.00"` (alert_date inline for freshness without chart pull). Morning briefing renders parallel section after EP. Both surfaces gated by `should_run("wick_fill")` strategy phase. Existing settled-wick filters intact (they serve outcome telemetry — the gap was forward visibility, not the backward analysis).

**Trading-day arithmetic** (advisor catch): lookback uses SQL `recent_sessions` CTE selecting DISTINCT trade_date from `mi_daily_closes` ORDER BY DESC LIMIT N — not `today - N calendar days`. Tue/Wed lookback would miss prior-Friday wicks if the window absorbed Sat/Sun. **Already-filled blind spot** (advisor catch): `NOT EXISTS (SELECT 1 FROM mi_daily_closes d WHERE d.ticker=w.ticker AND d.trade_date > w.alert_date AND d.high_price >= w.prior_high)` prevents stale "pending" entries between price-broke-prior-high and the 5:45 PM sweep marking the row filled.

**Lesson**: outcome-telemetry filters (`filled_wick = TRUE`) and forward-looking trader filters (`filled_wick IS NULL AND high < prior_high`) are different shapes of the same conceptual question. Reusing the telemetry filter for trader-facing surfaces silently hides actionable setups during their entire entry window. Two-purpose surfaces need two filters.

### 2026-05-03 — pm_rvol gate universe: top-500 → $5M $-vol floor
OMCL 2026-04-28 HIGH alert (gap +22%, lost $1506) prompted re-audit of the pm_rvol entry gate (RVOL@T, shipped 2026-04-26 to plug INTC-class entry leaks). 30d frequency query: **84.2% of HIGH alerts (32/38) and 97.4% of MODERATE (37/38) silently bypassed the gate** because they were outside top-500 by trailing $-vol. OMCL specifically: rank #2173, no baseline at scan time → `compute_rvol_at_time` returned None → gate silently skipped. The list of bypass victims includes OMCL, INTC, KURA, AEHR, URI, GSHD, KYTX — many became live trades. The gate was structurally non-functional for ~85% of the candidates it was designed to protect.

**Fix**: `db.py::get_top_dollar_volume_universe` swapped from `LIMIT 500` to `WHERE adv_20 * close >= $min_dollar_volume` (default $5M, with `max_tickers=5000` as a safety cap). At current scores: 2647 tickers pass, ~5.3× prior universe. `minute_volume.py` constants `UNIVERSE_LIMIT` → `UNIVERSE_MIN_DOLLAR_VOLUME` (5_000_000.0) + `UNIVERSE_MAX_TICKERS` (5000); `refresh_curves` signature updated.

**Runtime impact**: 18:30 ET `minute_volume_curves_refresh` job, prior runtime ~1 min for 500 tickers (74,873 rows written 5/01), expected ~30–60 min at 2647 tickers (Polygon API call latency dominates over DB writes; concurrency=8 unchanged). Next downstream job is the 21:00 ET evening backstop — comfortable headroom. Stale-row reaper (2h threshold, shipped earlier today) is the safety net for SIGTERM-during-job.

**Warm-up lag (expected, not a regression)**: gate fires only when `sample_n >= MIN_BASELINE_N_FOR_GATE = 10`. Newly-included tickers (rank 501–2647) start tomorrow with **zero** per-minute history, accrue ~1 day of bars per nightly refresh, and won't gate until ~10 trading days from now (mid-May 2026). Mid/small caps with sparse pre-market trade flow may take longer at specific minutes. So a HIGH alert tomorrow on a freshly-included name will *still* hit `compute_rvol_at_time → None` and bypass the gate — that's the warm-up, not the fix failing. Flagged here so the next OMCL-class slip in the May window doesn't read as a regression.

**INTC sidebar**: INTC was the 2026-04-26 motivator for shipping RVOL@T but appears on this bypass list — meaning either (a) INTC's $-vol dropped below top-500 since 4/26, or (b) the gate has been non-functional for INTC since day one. Either way, a useful reminder that the original ship verified plumbing, not coverage.

**Lesson**: a fixed-N universe is the wrong shape for a gate that exists to catch *any* gapper outside the megacap set. Pre-market gappers are systematically mid/small-cap (the megacaps don't gap +20% on news), so capping at top-500 by trailing $-vol *inverts* the intended coverage. $-vol *floor* (scope by liquidity threshold, not ranking) matches the gate's purpose. The skip-when-baseline-missing design is correct (better than fabricating a baseline) — the bug was scoping the universe so narrowly that the skip path was the dominant code path.

### 2026-05-03 — Drop `check_stuck_filled_row` invariant (duplicate of naked_position)
GOOGL + TEAM (5/01 fills, healthy multi-day holds with stops attached, +$157 / +$848 unrealized) tripped L1 `stuck_filled_row` because its 24h threshold is mismatched to a Qullamaggie/Pradeep multi-day hold system. Verified GOOGL stop=`41d1dcbe…`, TEAM stop=`eb0c94fc…` — both have `stop_order_id` set, both alive on Alpaca. The invariant assumed day-trade timeframe; structurally false-positives on every multi-day winner past 24h.

**Fix**: deleted `check_stuck_filled_row`, `INV_STUCK_FILLED_ROW`, and the registry entry in `audit_invariants.py`. The INTC OTO bug class (the original motivation, 2026-04-24) is already covered by `check_naked_position` — its SQL gates on `status='filled' AND stop_order_id IS NULL AND filled_at < NOW() - INTERVAL '60 seconds'`, which is the actual SQL-detectable signature of a missing-stop bracket. Adding `stop_order_id IS NULL` to stuck_filled_row would just delay-duplicate naked_position by 24h — same matches, later alert.

**Lesson**: two invariants targeting "the same SQL-detectable bug class" must differ in *what* they catch, not just *when*. A 24h-delayed copy of naked_position has zero net detection value and pure false-positive cost on legitimate holds. If the original concern was "did we miss a close that the broker thinks happened?" — that's a broker-vs-DB consistency problem, not a SQL-only invariant. Filed for later if the missed-close case ever surfaces.

### 2026-05-03 — Cold-start L2 gate: minimum-denominator skip for rate metrics
Five false `HIGH_ep_entry_rate` L2 alerts (4/27, 4/28, 4/29, 4/30, 5/01) — all at `sample_n < 7`, all triggered by the cold-start floor `(0.5, "low")`. Three with `current=0.0` (no detections), two with `current=0.333` (3 detected, 1 entered). Same structural-zero pattern: low-detection days where a single skip (or zero detections) collapses a rate metric to a value the floor catches regardless of pipeline health.

**Fix**: `MetricSpec.fetch_today` signature widened to `Awaitable[float | None]`. Both rate metrics (`_today_high_entry_rate`, `_today_shadow_orb_no_entry_rate`) return None when denominator < `_MIN_DETECTED_FOR_GATE = 5`. `_compute_anomaly` skips both sample recording and anomaly classification when current is None — keeps the baseline clean of structural zeros that would otherwise pollute future warm-tier comparisons too. Threshold = 5 because 60-day historical HIGH detection distribution is 1–16/day; threshold of 5 skips ~half of days but matches steady-state noise floor.

**Trade-off**: on quiet detection days (detected < 5), no L2 fires even if the entry pipeline genuinely broke. Existing ceiling was already broken on those days (false positives regardless), so net change is "noisy false positives → quieter true silence on quiet days." The regime-conditional Crisis baseline + sample-driven warm path still cover steady-state days with detected ≥ 5.

**Cleanup**: deleted 14 polluted `mi_metric_baselines` rows (all p50=0) + 5 polluted `metric_sample` audit events for both metrics. Next baseline refresh starts fresh from real samples only.

**Lesson**: rate metrics with small denominators need a minimum-N gate, not just a zero gate. A "0/0 → 0.0" guard misses the "1/3 → 0.333" case that's structurally indistinguishable from a real entry-rate degradation. The fix is to declare such days uninformative entirely (return None) rather than coerce to a number that happens to look anomalous against the floor.

### 2026-05-03 — Reap stale `mi_job_runs` 'running' rows at scheduler startup
Weekly digest surfaced `minute_volume_curves_refresh` stuck at `status='running'` from 4/30 + 5/01. Investigation found 5 stale rows across 3 jobs (`nightly_data_pull` ×2, `crypto_nightly_ingest`, `minute_volume_curves_refresh` ×2). Git-commit-vs-cron timestamps confirmed deploy-during-job for the curves cluster (commits at 18:24/29/44/47/52 ET around the 18:30 cron); 4/30 crypto run had no nearby commits (real hang). Same root cause class: SIGTERM during `await` inside `audit_run` doesn't reach the except/else paths reliably → row stays `running` forever, `mi_job_runs` accumulates zombies, stuck-job invariants stop working.

**Fix**: `_reap_stale_running_runs()` runs once at scheduler startup via `asyncio.create_task` — `UPDATE mi_job_runs SET status='aborted', finished_at=NOW(), error_message='...' WHERE status='running' AND started_at < NOW() - INTERVAL '2 hours'`. Logs `stale_runs_reaped` audit event with reaped count + job IDs (climb in count is leading indicator of real hangs vs deploy churn). 2h threshold — no legitimate job runs >1h. New status value `aborted` (schema has no CHECK constraint on `status`).

**Verified before ship**: 5/01 curves refresh actually wrote all 74,873 rows in ~1 min before being killed (latest `refreshed_at` = 5/01 18:31 ET). Only the audit row was stuck; data work completed. Monday catch-up not needed — pre-open uses 5/01 baselines, normal Friday→Monday gap RVOL@T tolerates.

**Reap is hygiene, not prevention.** Deploys must win; we accept the kill and recover next cron. Filed for follow-up: wire `scheduler.shutdown(wait=True)` on SIGTERM as actual prevention.

**Lesson**: invariants and audit-row state assume the process always reaches the finally-equivalent path. Container restarts during `await` violate that assumption silently. Reap function makes the audit table self-healing on next startup.

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

## Adding a "Changes Made" entry
Keep new entries in **Recent** section above. After ~2 weeks, compress each entry to a single bullet (`topic — key change & lesson`) and **graduate it into `CHANGELOG.md`** — don't keep the compressed form in this file. Drop "Files Changed" lists (git tells you that), drop "Post-deploy verification" once verified, drop manual cleanup SQL once applied.

Older history: see `CHANGELOG.md` (compressed log, on-demand only — not auto-loaded). For genuinely architectural decisions where the *why* outlives the code, optionally write a short `docs/decisions/NNNN-topic.md` ADR.

Target CLAUDE.md size: under 30k chars. Hard ceiling: 40k (warning threshold).
