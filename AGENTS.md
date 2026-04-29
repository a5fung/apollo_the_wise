# Apollo the Wise — Codex Context

## Session Sync Protocol
At the start of every session: `git pull origin main`
Read "Changes Made" sections to understand prior sessions.

At the end (if code changed):
```bash
git add AGENTS.md <changed files>
git commit -m "Brief description"
git push origin main
```

## What This Is
Telegram-based trading assistant for momentum/EP trading (Qullamaggie, Pradeep Bonde, Marios Stamatoudis methodology). Orchestrator routes all trading/market tasks to the Market Intelligence agent.

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
Apollo Orchestrator (port 8000)   ← Codex-sonnet-4-6, tool-use loop
      │  POST /task  +  X-Apollo-Secret header
      ▼
Market Intelligence Agent :8006   ← Docker, owns all market/trading logic
      │
PostgreSQL (pgvector) + Redis
```
The orchestrator is kept as a thin routing layer for future expansion; currently it delegates every task to the market agent.

## Code Layout
```
core/          orchestrator.py, router.py, context.py, memory.py, confirmations.py
agents/
  market_intelligence/
    agent.py           # execute_task() routes by keyword
    db.py              # All DB queries — single source of truth for schema
    rs_engine.py       # RS scoring (~9700 stocks)
    ep_detector.py     # MAGNA53 EP scoring + Codex + Gemini
    theme_engine.py    # Theme discovery, dedup, lifecycle
    briefing.py        # Briefing formatters + send_telegram_message
    scheduler.py       # APScheduler jobs
    broker/            # Alpaca ORB trading
channels/      telegram.py, webhooks.py
shared/        models.py, registry.py, secrets.py
```

## Adding an Orchestrator Tool
1. Tool schema → `core/router.py` → `get_orchestrator_tools()`
2. Dispatch → `core/orchestrator.py` → `_dispatch_tool()`
3. Handle → `agents/market_intelligence/agent.py` → `execute_task()`

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
14. screener / 15. audit log ("audit log", "show logs", "show errors") / 16. weekly review ("weekly review", "system review", "self audit") / 17. fallback

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
- **Validation**: `_validate_theme_membership()` runs Mon/Wed/Fri. Parse Haiku response with regex to extract JSON — Haiku appends explanation text that breaks `json.loads` directly.
- **`mi_theme_exclusions`**: user-directed permanent bans ONLY. NOT auto-populated from validation removals (deliberately — bad descriptions caused TSEM to be permanently banned from semiconductor theme).
- **Fading themes**: tickers from Fading themes ARE in `covered_tickers` — prevents validation-removed stocks appearing as uncovered in the same run.
- **Post-assignment validation**: immediately validates newly assigned stocks (don't wait for Mon/Wed/Fri).
- **Tool schemas**: all three tools (assignment, discovery, split) have `analysis_scratchpad` as required first field — forces reasoning before JSON output.
- **Unknown sector fallback**: when sector is "Unknown", checks description keyword overlap (4+ letter words) before allowing assignment.
- **Description chunking**: `_ensure_descriptions()` sends max 15 tickers per Haiku call.

### EP Detection (MAGNA53)
- Alpaca bars use **IEX feed** (free), not SIP (paid) — critical for `get_first_bar()`
- **Open intensity projection**: only applied after 15 min since open (≥9:45 AM). Pre-9:45 uses raw RVOL — opening minutes are always dense and create false 30x+ projections.
- **Extension check**: uses MIN(close) over last ~5 trading days, not a single point 5 days ago.
- HIGH ≥ ep_threshold (regime-dependent) → immediate Telegram alert; MODERATE 50-69 → morning briefing

### 9M EP Detection (Parallel Track)
- **No LLM** — pure quantitative virgin 9M detection (Pradeep Bonde)
- **Quality gates** (target 2–5 alerts/day):
  - Price ≥ $5, dollar volume ≥ $50M (actual) / ≥ $30M already traded (anticipation)
  - Directional: gap ≥ 3% OR intraday gain ≥ 4%
  - Anomaly: effective_vol ≥ 3× ADV (unknown ADV passes; ratio — NOT a flat ADV ceiling)
  - Anticipation: ≥ 30 min elapsed, ≥ 3M shares already traded, projects to ≥ 12M
- **Intraday and EOD use identical filters** — both apply 3× ADV ratio, $50M turnover, $5 price, directional conviction. Any divergence creates phantom sugar babies.
- **Sugar Baby** = 9M day + green (close > open) + close in top 25% of range → Day 2 ORB candidate
- **Stop = prior day's low** (breakout day's low), NOT ORB low or ATR-based
- **Tables**: `mi_9m_ep_alerts` (intraday), `mi_9m_sugar_babies` (EOD confirmed)
- **`mi_daily_closes`** now has `open_price`, `high_price`, `low_price` — required for sugar baby filter
- **`ingest_daily_closes()`** stores o/h/l from Polygon grouped daily payload with COALESCE guard
- Do NOT import from `ep_detector.py` — use `collector.get_snapshot_all()` directly in `ninem_detector.py`

### Error Alerting
- Silent failures in theme engine now write to `mi_audit_log` with event types: `validation_error`, `assignment_error`, `discovery_error`
- After nightly run: if any `*_error` events in last 2h → immediate Telegram alert
- Morning briefing: shows overnight error count at top if any
- Telegram: `show errors 7d` pulls all error events for the period

### Paper Trading (Alpaca)
- `mi_paper_trades` = EOD simulation table (LIVE_TRADING_ENABLED=true, ALPACA_PAPER=true)
- `mi_live_trades` = actual Alpaca order table
- ORB entry at 9:31 AM; bracket order: stop-limit buy at ORB high, stop at ORB low
- Safeguards: max 4 positions, 2% daily loss limit, 5-loss circuit breaker (1-day cooldown)
- Kill switch: `LIVE_TRADING_ENABLED=false`

### Telegram Formatting
- NEVER use pipe tables — Telegram can't render them. Use monospace code blocks.
- `send_telegram_message` in `briefing.py`. Returns False on failure (never raises).
- Escape dynamic strings before passing with Markdown mode.

## Daily Schedule (ET)
| Time | Job |
|---|---|
| 7:00 AM | EP scan starts (every 5 min) |
| 9:00 AM | Morning briefing |
| 9:31 AM | ORB monitor — bracket orders |
| 9:35 AM | Stop refresh Day 2+ |
| 10:00 AM | EP scan stops |
| 4:05 PM | EOD cleanup |
| 5:00 PM | Data pull — RS + regime + themes + error check |
| 4:45 PM | Position update |
| 8:00 PM | Evening briefing |
| Sun 8:00 AM | Weekly system self-audit (7d metrics → Codex synthesis → Telegram digest; persists `mi_system_reviews`) |

## Production Deploy
- Server: `ssh apollo@87.99.134.162`, dir: `/home/apollo/apollo_the_wise/`
- Market agent only: `git pull origin main && docker compose -f docker/docker-compose.prod.yml build --no-cache market-agent && docker compose -f docker/docker-compose.prod.yml up -d market-agent`
- Both services: same but add `orchestrator` to build/up commands
- Service names: `orchestrator`, `market-agent`, `postgres`, `redis`

## Required Env Vars
```
TELEGRAM_BOT_TOKEN, TELEGRAM_ALLOWED_USER_IDS
ANTHROPIC_API_KEY, POLYGON_API_KEY, FMP_API_KEY, PERPLEXITY_API_KEY
ALPACA_API_KEY, ALPACA_SECRET_KEY, ALPACA_PAPER=true, LIVE_TRADING_ENABLED=false
POSTGRES_PASSWORD, REDIS_PASSWORD, INTERNAL_API_SECRET, TRADINGVIEW_WEBHOOK_SECRET
```

## Changes Made 2026-04-19

### 9M EP System (Pradeep Bonde "9M" tactic)

Completely parallel EP track — zero changes to existing MAGNA53 logic.

**New file:** `agents/market_intelligence/ninem_detector.py` — intraday scan (`run_9m_scan()`) + EOD sweep (`run_9m_eod_sweep()`)

**DB additions (`db.py`):**
- `mi_daily_closes` gains `open_price`, `high_price`, `low_price` (ALTER TABLE, COALESCE-guarded upsert)
- `mi_9m_ep_alerts` — intraday detection log; `UNIQUE (ticker, alert_date)`
- `mi_9m_sugar_babies` — EOD Day 2 watchlist; `UNIQUE (ticker, alert_date)`; `day2_status`: pending/traded/skipped
- New functions: `insert_9m_ep_alert`, `get_today_9m_ep_alerts`, `insert_9m_sugar_baby`, `get_eod_9m_sugar_babies`, `get_pending_9m_sugar_babies`, `update_9m_sugar_baby_status`, `get_9m_ep_history`, `get_9m_live_trades`

**Broker (new functions only, no modifications to existing):**
- `order_manager.py`: `prepare_9m_day2_orb_order()` — stop = prior day's low (not ATR-based)
- `live_tracker.py`: `submit_9m_day2_trade()` — auto-enters paper, proposes in live

**Scheduler:** `9m_ep_scan` (every 5 min 9:30–4 PM), `9m_day2_orb` (9:31 AM). EOD sweep inside `_nightly_data_pull()`.

**Agent routing:** `_handle_9m_ep_query`, `_handle_9m_ep_outcomes`, `_handle_9m_trades` (includes "trade 9m TICKER" manual trigger)

**Outcome tracking:** `_compute_9m_ep_outcomes()` in `outcome_tracker.py` — 1D/1W/1M returns → `mi_signal_outcomes` with `signal_type='9m_ep'`

**Scripts:** `scripts/backtest_9m_ep.py` (D1/D5/D10/D21 by vol/range bucket), `scripts/test_9m_ep_e2e.py` (e2e test)

**Key rules:**
- Volume ≥ 8.9M (actual) or ≥ 12M projected (after 15 min) = signal
- Sugar Baby = 9M day + green + close top 25% of range
- Stop = prior day's low; shared 4-position cap with MAGNA53

### Files Changed
`ninem_detector.py` (new), `db.py`, `briefing.py`, `scheduler.py`, `agent.py`, `broker/order_manager.py`, `broker/live_tracker.py`, `outcome_tracker.py`, `scripts/backtest_9m_ep.py` (new), `scripts/test_9m_ep_e2e.py` (new), `README.md`, `EP_TRADING_RULES.md`, `AGENTS.md`

---

## Changes Made 2026-04-20

### Bugs Fixed — Theme Validation (20 silent parse errors)

**Root cause: regex broke on Haiku's new nested-JSON responses.**
Old regex `r'\{[^{}]*\}'` scans for `{` then chars that are NOT `{` or `}`. Haiku now
returns extra fields alongside `remove`, e.g. `{"remove": [], "reasoning": {"fit": "..."}}`.
The regex hits the inner `{` of the nested object and gives up — `m` is `None`, so the full
raw prose is passed to `json.loads`, which raises `JSONDecodeError`. All 20 themes failed
the same night because it's a model behavior shift, not a theme-specific issue.

Fix (`theme_engine.py`):
- `_extract_json_object()` — replaces regex with proper brace-depth + string-escape-aware
  parser that correctly extracts the outermost `{...}` regardless of nesting depth.
- `result.get("remove") or []` — guards against Haiku returning `"remove": null` instead
  of `[]`; the old `.get("remove", [])` default only fires when key is absent, not null.
- `max_tokens` 200 → 400 to avoid mid-JSON truncation.
- Added `system` prompt: `"Respond with valid JSON only. No prose, no markdown."` to
  reduce likelihood of extra fields in the first place.

**⚠️ MUST-VALIDATE after next Mon/Wed/Fri nightly run:**
1. Check audit log for any remaining validation errors:
   - In Telegram: `show errors 1d`
   - Should show 0 `validation_error` events
2. Confirm validation is actually running and making decisions (not just silently passing):
   - In Telegram: `show errors 7d` — look for `ticker_revalidated_out` events to confirm
     Haiku is successfully removing wrong-sector stocks
3. If errors still appear, check the `detail` field — it contains `{ErrorType}: {msg} | raw={snippet}`
   which reveals exactly what Haiku returned and why parsing failed

### Bugs Fixed — Theme Assignment Cross-Sector Hallucinations (LRCX/ICHR in Oil theme)

**Root cause: sector gate had a blind spot when theme members all show "Unknown" sector.**
Oil theme stocks (XOM, CVX, OXY) often fall outside the top-300 RS leaders so they have
no sector in `stocks_by_ticker`. This made `known_sectors = []`, which bypassed the
`if known_sectors and stock_sector not in known_sectors` check entirely — even when the
incoming stock's sector (e.g. LRCX = "Electronic Technology") was perfectly clear.
Result: Codex's LLM assignments were validated only by Haiku post-assignment, which
correctly removed them but left 14-day cooldowns that pollute the briefing.

Fix (`theme_engine.py`): added `elif not known_sectors` branch — when theme sectors are
all unknown, cross-check the stock's sector against the theme name + description via
keyword overlap (4+ letter words). "Electronic Technology" shares zero words with
"Crude Oil Price Momentum ETFs & Pure-Play E&P" → rejected before reaching Haiku or DB.
Preserved the existing `else` fallback (description overlap) for when the stock's own
sector is also unknown.

**Existing bad cooldowns (LRCX/ICHR/AMPX/DOW on crude oil):** cosmetic only, expire in
~13 days. No manual cleanup needed. Fix prevents new wrong assignments going forward.

### Bugs Fixed — Broker / Live Trading

**Partial exit blocked by stop order (KURA case):**
All shares were `heldfororders` by the Alpaca stop-loss bracket, making `available=0`. Selling any shares was rejected.

Fix (`broker/order_manager.py: execute_partial_exit`):
- Step 1: cancel old full-qty stop → place new stop for `new_remaining` (2/3) → DB updated immediately
- Step 2: market sell `partial_shares` (1/3) — now available since stop no longer holds them
- On sell failure: cancel new stop, restore original-qty stop, send Telegram alert with confirmation
- On stop-cancel failure: abort cleanly (old stop still live), alert, retry next cycle
- On replacement stop failure: 🚨 urgent alert, abort

**Fractional qty rejection:**
`remaining / 3` (Python float) produced `697.333...` which Alpaca rejects. Fixed to `int(remaining) // 3`.

**Caller ignored execute_partial_exit return value (`broker/live_tracker.py`):**
Even on failure the caller set `partial_taken=True` and decremented `remaining_shares`, so the partial was marked done and never retried. Fix: only advance `partial_taken / breakeven_active / remaining` if the call returns `True`. On failure, DB state is unchanged and the next 4:45 PM run retries automatically.

**⚠️ MUST-RUN before next 4:45 PM position update — DB is wrong for KURA:**
The failed partial on 2026-04-20 wrote `partial_taken=TRUE` and `remaining_shares≈1394`
to the DB even though no shares were sold. Without this fix, KURA's partial will never
be retried and the share count/stop will be based on incorrect data.
```sql
-- Run on production DB before deploying or before 4:45 PM ET
UPDATE mi_live_trades
SET partial_taken = FALSE,
    breakeven_active = FALSE,
    remaining_shares = 2092
WHERE ticker = 'KURA' AND status = 'filled';
```

**Order skip reason opaque ("Order spec failed"):**
`prepare_orb_order` returned `None` with no reason. Changed return type to `tuple[dict|None, str|None]` — every rejection path now returns a specific human-readable string (e.g. `"stop too wide: ORB range $1.24 vs 1.5× ATR $0.83"`). The reason is shown in Telegram, stored in `mi_live_trades.skip_reason`, and written to `mi_audit_log` with ORB H/L/ATR for system evaluation.

### Key Rules Added
- **Partial exit is always stop-protected**: stop for remaining shares is placed *before* the sell order, not after.
- **SMA trailing stop timing**: runs once daily at 4:45 PM ET (EOD close-based). Activates on Day 10+ (needs 10 daily closes). Before Day 10: only ORB hard stop + breakeven (if partial taken) apply.

### Files Changed
`broker/order_manager.py`, `broker/live_tracker.py`, `scripts/cleanup_9m_false_alerts.py` (new)

**⚠️ MUST-RUN on production before deploy — 100+ false 9M EP alerts in DB:**
The 9M ETF/non-stock filter was added on 2026-04-20 (session 6), but alerts fired before
that fix are still in `mi_9m_ep_alerts` and `mi_9m_sugar_babies`. Run the cleanup script
on the server after `git pull`:
```bash
# Dry run first — review output carefully
docker compose -f docker/docker-compose.prod.yml exec market-agent \
  python scripts/cleanup_9m_false_alerts.py

# Then delete if output looks right
docker compose -f docker/docker-compose.prod.yml exec market-agent \
  python scripts/cleanup_9m_false_alerts.py --delete
```
Script checks three criteria: SKIP_TICKERS list, non-CS/ADRC in `mi_security_types`,
and bad ticker format (>5 chars or contains `.`). Also cleans derived sugar baby rows.

---

## Changes Made 2026-04-20 (session 2) — 9M quality filters (74 → 2–5/day)

### Problem
First production day of post-ETF-filter 9M detector produced **74 alerts** — unworkable
as a signal and as a Day 2 ORB candidate pool (4-position cap). Existing filters
(ETF gate, ADV ≤ 4.5M ceiling, gap ≥ 0%, price ≥ $3) let through low-dollar stocks,
flat/red tapes, and stocks doing merely 2× their normal volume.

### Fix — structural filters in `ninem_detector.py` + matching EOD SQL

Four new gates applied to both intraday `run_9m_scan()` and EOD `get_eod_9m_sugar_babies()`:

1. **Price ≥ $5.00** (was $3) — sub-$5 rarely institutional.
2. **Dollar-volume floor:**
   - Actual alert: `today_volume × current_price ≥ $50M`
   - Anticipation: `≥ $30M` already traded (self-regulates low-priced false positives)
3. **Directional conviction:** `gap ≥ 3% OR intraday_gain ≥ 4%` — catches both
   "gapped and held" and "opened flat but trending hard." Previous `gap ≥ 0%` was a no-op.
4. **Virgin 9M anomaly (ratio, not ceiling):** `effective_vol ≥ 3 × adv_20`
   - Actual uses `today_volume`; anticipation uses `projected_vol`
   - **Critical**: replaces old flat `_MAX_ADV = 4.5M` ceiling. Flat ceiling would have
     silently blocked mid-ADV genuine catalysts (4M ADV × 20M shares = $100M+ day) while
     the EOD SQL (which already used a 3× ratio) would have surfaced them as phantom
     sugar babies the next morning. Both paths now use identical ratio logic.
5. **Anticipation tightened:** min-elapsed 15 min → 30 min; require ≥ 3M shares already
   traded before projecting (prevents projection off 1–2M of open-auction flow).

### Telegram message format
Now includes dollar-volume: `9M EP: TICKER — Vol: 12.3M ($87M) | RVOL: 4.1x | $7.15 | +8.2%`.
Gap display auto-switches to intraday_gain when the intraday leg is what qualified.

### Files Changed
`ninem_detector.py` (constants + filter logic + docstrings + message), `db.py`
(`get_eod_9m_sugar_babies` WHERE clause + docstring), `AGENTS.md`

### ⚠️ Post-deploy verification
After first session with new filters:
1. Alert count should land in 2–5 on a typical day, 6–10 on a risk-on day.
2. Spot-check `mi_9m_ep_alerts` for today: no flat/red tapes, no sub-$5, no mega-caps.
3. Sugar babies count in `mi_9m_sugar_babies` for today should be ≤ 5.
4. Mid-ADV genuine catalysts (e.g. a 4M ADV name doing 15M+ shares on news) must appear
   in **both** intraday alerts **and** EOD sugar-baby query.

---

## Changes Made 2026-04-20 (session 4) — Hardening triage from architecture review

### Hardening
- **LLM rate-limit guard in `ep_detector`**: switched `_get_claude()` to `AsyncAnthropic`, added module-level `asyncio.Semaphore(5)` + one-level retry on `RateLimitError` (2–5s jitter). Earnings days with 30+ simultaneous gaps no longer silently degrade catalyst classification via 429s. Audit event `anthropic_rate_limited` on retry.
- **Correlation matrix off the event loop**: `correlation_engine.run_correlation_clustering` now wraps the `np.corrcoef` + BFS block in `asyncio.to_thread()` via new `_compute_tight_clusters_sync()`. The 2800×2800 float64 matrix no longer blocks Telegram / EP scans during nightly pull.

### Features Added
- **Theme breadth decay (`pct_above_20sma`)**: new column on `mi_themes`; computed nightly for every active theme via `get_ticker_breadth_above_sma20()` (reads `mi_stock_scores.close > sma_20`). When breadth < 40% for 2 consecutive days, theme is forced to `Fading` regardless of RS smoothed delta — catches themes where members have rolled over even while RS still looks healthy. Surfaces in briefing theme line as `brdXX%` next to `d{N}` and `🔥×{N}`. Audit event `theme_breadth_fade`.

### Backlog Added
P18 (+3R/72h partial), P19 (VIX-scaled risk), P20 (earnings IV pre-pass — blocked on data), P21 (cross-asset thematic validation). Rejected: stat-arb residual mean-reversion, dark-pool block-print integration.

### Files Changed
`ep_detector.py`, `correlation_engine.py`, `theme_engine.py`, `db.py`, `briefing.py`, `AGENTS.md`

---

## Changes Made 2026-04-20 (session 3) — Weekly system self-audit

### Features Added
- **Sunday 8 AM ET weekly review** — `system_review.py` pulls 7d from every tracking
  table, aggregates to summary stats in Python/SQL (LLM never sees raw rows — token
  trap), hands to Sonnet for synthesis, sends Telegram digest, persists to
  `mi_system_reviews` (JSONB metrics + suggestions) so next week's run grades prior
  suggestions. Four-section output: ✅ Working / ⚠️ Broken / 💡 Proposed changes / 🔁 Last week.
- On-demand trigger via Telegram: `weekly review`, `system review`, `self audit`.
- Follow-up framed as metric deltas (not "did it ship?") — LLM has no deploy visibility.

### New DB
- `mi_system_reviews` (review_date, window_days, regime, summary, metrics JSONB, suggestions JSONB) — UNIQUE (review_date, window_days).
- `get_weekly_theme_churn(days)` in `db.py` — LAG() over `mi_themes.tickers` arrays; returns high-churn (ticker, theme) pairs.

### Files Changed
`system_review.py` (new), `db.py`, `scheduler.py`, `agent.py`, `AGENTS.md`

---

## Changes Made 2026-04-17

### Bugs Fixed
- **Validation silently failing** (root cause of CAR bug): Haiku returns valid JSON then appends explanation text. `json.loads` failed with "Extra data" — `except` block kept all tickers. Fix: always extract JSON object via regex before parsing.
- **Sector always "Unknown" for fallback stocks**: Theme tickers outside top-60 RS leaders got `sector="Unknown"` hardcoded, bypassing the sector outlier check. Fix: `get_sectors_batch()` reads from `mi_ticker_overrides` (persistent cache).
- **EP projection false positives in first 15 min**: Linear extrapolation at 9:31 AM produces absurd 30-40x projected RVOL. Fix: 15-minute gate — projection only after 9:45 AM.
- **Extension check using single stale point**: Used close from exactly 5 days ago. Fix: `MIN(close)` over last ~5 trading days.
- **Auto-persist validation removals**: Re-introduced dangerous code (reverted April 10 for good reason — caused TSEM permanent ban). Reverted again.

### Features Added
- **Proactive error alerting**: Nightly Telegram alert if `*_error` audit events; morning briefing error section; `show errors Nd` command.
- **Theme engine architectural hardening**: Scratchpad in all tool schemas; Unknown sector description-overlap fallback; immediate post-assignment validation; description chunking (15/batch).
- **P4**: EP outcome table (`ep outcomes 30d`)
- **P5**: Theme conviction display (days_active, consecutive_accelerating on theme lines)
- **P6**: Trading journal (`journal: <note>`, `show journal`)

### Files Changed
`theme_engine.py`, `ep_detector.py`, `db.py`, `agent.py`, `briefing.py`, `scheduler.py`

## Changes Made 2026-04-17 (session 2)

### Hardening (live trading prep)
- **Orphaned stop remediation**: `sync_positions()` now detects filled trades with no `stop_order_id` and auto-places a protective stop using stored `stop_price`/`orb_low`. Alerts via Telegram.
- **yfinance timeout**: All 6 executor calls in `get_fundamentals()` wrapped with `asyncio.wait_for(30s)` — prevents thread pool starvation if Yahoo hangs.
- **Data pull timing**: 4:30 PM → 5:00 PM ET so volume/print data has settled before RS scoring.
- **RS leaders tweet**: Dropped `media_upload` (v1.1 API, 403 on free tier) — posts text-only thread now.

### Features Added
- **P2**: MODERATE EP alerts in morning briefing now show `rel_volume` + `claude_analysis` summary line. Previously showed only gap% and score.
- **P3 scaffold**: `validation report` / `paper performance` command. Scaffold mode (N < 10 trades) shows raw list. Full report at N ≥ 10: win rate, avg P&L, breakdowns by regime/catalyst/gap bucket.

### Files Changed
`broker/order_manager.py`, `fundamentals.py`, `scheduler.py`, `twitter.py`, `briefing.py`, `db.py`, `agent.py`

## Changes Made 2026-04-17 (session 3)

### Features Added
- **Validation cooldown**: When validation removes a stock from a theme, writes a 14-day cooldown to `mi_validation_cooldowns`. Prevents re-assignment during cooldown via: (1) Codex prompt context injection, (2) post-assignment hard filter. Full audit trail (`validation_cooldown_triggered`, `cooldown_blocked_assignment`, `validation_cooldown_bypassed`). Commands: `show cooldowns`, `bypass cooldown TICKER [theme] [reason]`. Evening briefing shows compact `🧊 Cooldowns:` footer if any active. Fixes the CAR-in-Data-Center churn bug.

### New DB Table
`mi_validation_cooldowns` (ticker, theme_name, cooldown_until, removal_count, bypassed, bypassed_reason)

### Files Changed
`db.py`, `theme_engine.py`, `agent.py`, `briefing.py`

## Changes Made 2026-04-17 (session 4)

### Features Added
- **P15 — Correlation clustering**: New `correlation_engine.py` computes beta-adjusted (SPY-residual) Pearson correlations over 20 trading days on the full liquid universe (~4–6K tickers). BFS connected components ≥ 4 stocks at pairwise corr ≥ 0.85. Two filters: chaining filter (mean_corr ≥ 0.80 on sub-matrix), theme dedup (skip if ≥ 50% members already in same theme). Clusters fed into `_discover_new_themes()` prompt as early statistical signals.
- Key correctness patches: zero-variance stocks stripped before `np.corrcoef` (halted/flat tickers → NaN rows); `ddof=1` used consistently for both `np.var` and `np.cov` (population/sample mismatch = invalid beta); chaining filter via sub-matrix `mean_corr`; prompt guardrail against "Cluster A/B" names.
- `show clusters` command in Telegram
- `scripts/backtest_clusters.py`: precision + recall metrics on historical data (target: precision ≥ 30%, recall ≥ 60%)

### New DB Table
`mi_correlation_clusters` (cluster_date, cluster_hash, ticker, member_count, mean_corr, avg_rs)

### Bugs Fixed (post-backtest)
- **ETF contamination**: Full universe included leveraged ETFs (TSLZ, TQQQ, GLD, GBTC) that cluster by construction. Fixed: JOIN `mi_security_types` WHERE `security_type IN ('CS', 'ADRC')`, with explicit SPY exemption for beta adjustment.
- **OOM on 5K universe**: 5K×5K float64 ≈ 400MB → container OOM kill (exit 137). Fixed: `min_avg_dollar_volume=$20M` default → ~2800 tickers, ~133MB total — fits 512MB container.
- **Holiday months short of 21 days**: December/January holidays → only 19–20 trading days in 30-day calendar window. Fixed: `_LOOKBACK_DAYS = 35`.
- **Backtest look-ahead cap**: `if before > to_date: continue` prevented any cluster from reaching future theme data. Removed. Recall query also extended to `to_date + 6 weeks`.

### Backtest Results
Dec 2025 → Feb 2026: precision 0.5%, recall 8.2%. **Statistically inconclusive** — theme data only starts 2026-03-19, so most cluster look-ahead windows land in a data gap. Qualitative check (2026-04-17) shows 10 coherent sector clusters (quantum computing, tankers, insurance, storage REITs, paint/coatings). Re-backtest when theme history reaches 6+ months (~June 2026).

### Files Changed
`correlation_engine.py` (new), `db.py`, `theme_engine.py`, `scheduler.py`, `agent.py`, `scripts/backtest_clusters.py` (new)

## Changes Made 2026-04-19 (session 5)

### Features Added
- **P7 — `/pregame`**: Compact trade-ready shortlist (Accelerating themes, HIGH EPs, watchlist MA pullbacks, 9M sugar babies). No LLM, instant. Added to `/pregame` slash command and `_handle_slash_command` dispatch.
- **Pinned HUD auto-refresh**: `/hud` now pins the message and stores `chat_id`/`message_id` via `POST /hud/pin`. `_hud_refresh_job` in scheduler edits the pinned message hourly during market hours (mon-fri 9 AM – 3 PM ET). On edit failure (message deleted), clears stored IDs so next `/hud` re-pins.
- **Inline keyboards**: `/eps`, `/themes`, `/trades` now send compact summary + drill-down buttons. Callbacks route through `_handle_drill_down_callback` → POST `/task` with sub-commands `/eps_detail`, `/themes_detail`, `/trades_detail`. Back button returns to summary.
- `edit_telegram_message(chat_id, message_id, text, parse_mode="Markdown")` added to `briefing.py`.
- `mi_hud_state` table + `get_hud_state()` / `set_hud_state()` in `db.py`.
- `_build_hud_text() -> str` extracted as standalone module-level function (not a method) — shared by `_handle_hud()` and `_hud_refresh_job`.

### New DB Table
`mi_hud_state` (key TEXT PRIMARY KEY, value TEXT, updated_at TIMESTAMPTZ) — stores `hud_chat_id` and `hud_message_id`.

### Files Changed
`db.py`, `briefing.py`, `agent.py`, `scheduler.py`, `channels/telegram.py`

## Changes Made 2026-04-19 (session 6)

### Bugs Fixed
- **9M EP flood (ETFs + mega-caps)**: `ninem_detector.py` had no ETF filter. Fixed with three layers: (1) `SKIP_TICKERS` check (same as EP detector), (2) `mi_security_types` non-common-stock filter (drops ETFs, leveraged products, warrants), (3) RVOL >= 2x ADV gate so AAPL/NVDA trading routine 9M+ volume don't trigger. Both the non-stock set and ADV map are cached per trading day to avoid per-scan DB overhead.
- **EP detector ETF leakage**: Hardcoded `SKIP_TICKERS` list was missing some leveraged ETFs. Added `mi_security_types` lookup at scan start as authoritative secondary gate — any ticker classified as non-CS/ADRC in reference data is skipped.
- **Catchup ORB order after ORB window**: On late restart (e.g., 11 AM), APScheduler fired the 9:31 AM EP scan which placed bracket orders past the ORB window. Fixed: `within_orb_window = market_open and now_et.hour < 10` gates all ORB order placement in `_ep_scan_job()`. Also added `misfire_grace_time=300` to EP scan jobs so APScheduler skips them entirely when restarting >5 min past their scheduled time.

### Key Rules Updated
- **9M EP RVOL threshold**: `_MIN_RVOL = 2.0` — stock must trade ≥ 2x its 20-day median volume on the day to qualify. If ADV is unknown (ticker not in RS universe), threshold is bypassed (conservative — don't filter unknowns).
- **ORB window**: `within_orb_window = market_open and now_et.hour < 10`. EP scans running outside this (catchup, stale fires) send alerts but never place orders.

### Files Changed
`ninem_detector.py`, `ep_detector.py`, `scheduler.py`

---

## Changes Made 2026-04-21 — `/trades` richer summary

### Problem
`/trades` default view rendered as a single unhelpful line (`0 live open · 0 paper open · $0 unrealized`).
When KURA stopped out, the user had no way to see the closed trade — "Live Positions" button showed
"nothing", "Closed Today" said "no data" until the stop fill propagated. And paper-trade counts were
misleading since the EOD sim was disabled when live Alpaca trading turned on.

### Changes (`agents/market_intelligence/agent.py` — `_handle_trades_detail`)
- **`summary` view** now shows:
  - All open live positions with **entry → current → stop**, shares, market value, hold days,
    unrealized P&L, and partial/breakeven flags. Current price comes from Alpaca `get_position`
    (silent fallback on failure, so a dead API doesn't break the summary).
  - **Last 5 closed** trades inline (entry → exit price, exit reason, score, P&L, hold days).
  - **Totals** row: W/L count, win rate, realized P&L (all-time).
  - Paper-trade stats intentionally dropped — sim is no longer live.
- **`closed` view** now shows today's closed + last 15 recent closed for context, each with full
  entry/exit/reason/score detail instead of just ticker + $P&L.
- **`live` view** kept as a silent alias of `summary` so older pinned messages keep working.

### Changes (`channels/telegram.py`)
- Removed "Live Positions" button (folded into summary).
- New button layout: row 1 = [Closed Trades] [Skipped], row 2 = [Paper (legacy)].
- Applied in both the initial `/trades` send and the drill-down re-render.

### Files Changed
`agents/market_intelligence/agent.py`, `channels/telegram.py`

### Bug Fixed — UTC/ET boundary hid today's closed trades
`closed_at::date = $1::date` used Postgres session TZ (UTC). After 8 PM ET the UTC date
rolls to tomorrow while `et_today()` is still today → `/trades_detail closed` and the
evening-briefing today's-closes query both returned empty even though the trade was
properly marked `status='closed'`. This is why KURA's stop-out alert fired but the
Closed Today button said "no data" afterwards.

Fix: cast via `(closed_at AT TIME ZONE 'America/New_York')::date` so the date comparison
is always evaluated in trading-floor time. Applied in:
- `agents/market_intelligence/agent.py` (`_handle_trades_detail` closed view)
- `agents/market_intelligence/broker/live_tracker.py` (evening briefing `todays_closes`)

Also converted the python-side filter that dedups today's rows from the "recent closed"
list to use `astimezone(_ET).date()` instead of the tz-naive `.date()`.

---

## Changes Made 2026-04-21 (session 2) — Briefing fixes, 9M quality + cadence

### Briefing hygiene
- **Truncated EP writeups** (`briefing.py`): new `_truncate_sentence()` helper cuts at sentence/word boundaries. MODERATE near-miss reasons compacted (`score 48 < 50 (catalyst=speculative)` → `s48 cat=spec`). `claude_analysis` cut raised 120 → 180 chars at sentence boundary.
- **Validation parse-error noise** (`briefing.py`): morning brief collapses N parse errors into a single yellow line "🟡 N theme validation parse error(s) — tickers unchanged" instead of one row each.
- **Haiku response hardening** (`theme_engine.py`): empty-content and stop_reason guard, strip ```` ``` ```` code fences, raise explicit `ValueError` with raw snippet so audit log captures actionable detail.

### Twitter 403 diagnostic
- **`twitter.py`**: disproved earlier "media_upload 403" theory (theme tweet with image posts fine; text-only RS-leaders tweet is what 403s). Added response-body capture on exception (`e.response.text`, `api_codes`, `api_messages`) to get real diagnostic on next fire. Trimmed hashtag suffix `#momentum #trading #RS #stocks` → `#momentum #stocks`.

### /pregame fixes
- **`agent.py::_handle_pregame`**: sugar babies fallback to yesterday when today's list is empty (EOD sweep writes after market close, so during the session only yesterday's babies are actionable). Parallel fetch via `asyncio.gather`.
- Accelerating themes now sorted by `rs_avg` desc (was effectively alphabetical). RS shown inline: `{theme_name} RS{avg}  TKR TKR TKR`.

### 9M quality filters — range + extension
- **Intraday range gate** (`ninem_detector.py`): `(day_high - day_low) / current_price ≥ 2%`. Rejects merger-arb pins (e.g. DBRG 0.26% range pinned to a cash deal close).
- **Extension gate — measured at prev_close, not today's close**: `prev_close ≤ 1.20 × 10d SMA`. Caught BB chase (`5.50 / 3.97 = 1.39×`) while passing fresh breakouts like VELO (`11.67 / 10.93 = 1.07×`) even when today is +30%. Measuring at today's close would wrongly reject the fresh breakout.
- **MA10 cache**: `_get_ma10_map()` once-per-day SQL over `mi_daily_closes` with `ROW_NUMBER()` window. Same gates applied in `db.py::get_eod_9m_sugar_babies` so intraday and EOD agree.

### 9M alert cadence — high-conviction anticipation carve-out
Context: 21 alerts on 2026-04-21 (5 actual + 16 anticipation) → unworkable noise floor. Cadence is a red herring — DB `UNIQUE (ticker, alert_date)` + in-memory dedup mean each ticker pings once/day regardless of scan frequency.

**Fix** (`ninem_detector.py`):
- New constants: `_ANTICIPATION_PING_GAP_PCT = 10.0`, `_ANTICIPATION_PING_PROJ_VOL = 25_000_000`.
- Gate: `should_ping = is_9m_actual or (is_9m_anticipation and (gap_pct ≥ 10 OR projected_vol ≥ 25M))`.
- Silent anticipations still hit the DB and audit log (`pinged=True/False` in detail) — `/9m` unchanged.

**Evening brief** (`briefing.py`): new `🔍 Anticipation-only today (N): TKR, TKR, ...` line below sugar babies, fed by `get_today_9m_ep_alerts(today_str)` filtered to `is_anticipation=true`.

Expected pings: ~6–7/day on typical sessions (was ~21).

### Files Changed
`briefing.py`, `theme_engine.py`, `twitter.py`, `agent.py`, `ninem_detector.py`, `db.py`, `README.md`, `AGENTS.md`

---

## Changes Made 2026-04-22 — EP entry diagnostics & performance traceability

Root: 2026-04-22 morning, event loop hung ~3h. 4 HIGH EPs detected, 0 orders placed,
2 tickers tagged `ORB window closed at 9:59 AM ET` — a string that lived only in logs,
not in any queryable table. Monthly perf review was a guessing game.

**Principle:** every HIGH EP alert has a durable, queryable terminal state by 4:10 PM ET
(post-`eod_cleanup` settlement; the EOD recap job reads it at 4:10).

### A. Bounded-vocabulary skip reasons — `broker/skip_reasons.py` (new)
18 constants in 5 categories: `filter:*` (ADV/ATR/mcap), `setup:*` (stop too wide,
size too small, account fetch), `block:*` (max positions, daily loss, circuit breaker),
`infra:*` (no_bar, subscribe_timeout/failed, order_submit_failed), `window:*`
(out_of_orb, duplicate). Prefix is machine-readable; free-form detail after `: ` preserves
human context. `split_part(skip_reason, ':', 1)` → category for monthly aggregation.

### B. Silent drops filled — every decision writes `mi_live_trades`
- `_insert_skipped_trade` now tolerates `alert=None`/`regime=None` — bar-stream
  timeout path can write a skip row without a DB join during a stuck lock.
  `/why` LEFT-JOINs `mi_ep_alerts` to recover score/catalyst/gap.
- New call sites:
  - `bar_stream.subscribe_ep_candidate` timeout → `INFRA_SUBSCRIBE_TIMEOUT`
  - `bar_stream.subscribe_ep_candidate` failure → `INFRA_SUBSCRIBE_FAILED`
  - `scheduler._ep_scan_job` post-9:59 HIGH → `WINDOW_OUT_OF_ORB`
  - `live_tracker.submit_9m_day2_trade` spec failure / no-bar / safeguard blocks
  - `order_manager.submit_entry` retry-exhausted → `INFRA_ORDER_SUBMIT_FAILED`
  - `live_tracker` ORB no-bar-after-retries → `INFRA_NO_BAR`
- `prepare_9m_day2_orb_order` refactored from `dict | None` to
  `tuple[dict | None, str | None]` — matches `prepare_orb_order` signature so skip
  reason propagates through caller to DB.
- `_check_safeguards` return strings migrated to `BLOCK_MAX_POSITIONS /
  BLOCK_DAILY_LOSS / BLOCK_CIRCUIT_BREAKER / SETUP_ACCOUNT_FETCH_FAILED`.
- Dedup path at `live_tracker.py:269` now writes `orb_duplicate` audit event
  (no DB write — row already exists).

### C. Alert hygiene — Telegram reserved for terminal events
- Bar-stream retries 1 & 2 now **audit-log only** (`bar_stream_disconnect`).
  Micro-drops at 9:30 AM are routine data-feed behaviour; alerting on
  self-healing retries creates fatigue. Telegram still fires on terminal
  3rd-retry (existing behaviour). Encoded as memory:
  `feedback_alert_vs_audit.md`.
- Post-9:59 HIGH and subscribe-failed both Telegram *once* with `⏰` / `⚠️`.

### D. Evening brief — new "📊 EP OUTCOMES TODAY" section
`briefing._format_ep_outcomes_section` — HIGH: N detected → M entered · K missed,
with entry price + fwd_1d% for entered and skip-reason prefix for missed.
MODERATE shows count + auto-enter status. `get_ep_outcomes()` extended with
`use_live` flag (auto-detected from `LIVE_TRADING_ENABLED`) — joins
`mi_live_trades` in live mode, `mi_paper_trades` in paper mode. Same CASE
logic, same return shape.

### E. `/why TICKER [YYYY-MM-DD]` — lifecycle timeline
New slash command + `trace TICKER` / `why didn't we enter` keyword routes.
Joins `mi_ep_alerts` + `mi_live_trades` + `mi_audit_log`. Audit query bounded
to the trading-day window via
`created_at >= ($1::date AT TIME ZONE 'America/New_York')` to avoid pulling
unrelated events from prior setups on the same ticker. Shows detection →
outcome → lifecycle event list.

### F. 4:10 PM EOD EP recap Telegram
New `_eod_ep_recap_job` at 16:10 ET (after 16:05 EOD cleanup settles). One-shot
summary of today's HIGH outcomes. Silent when no HIGHs detected today.

### ⚠️ Post-deploy verification

1. **Reason coverage invariant — zero silent drops.** On any trading day post-deploy:
   ```sql
   SELECT a.ticker, a.score_tier, lt.status, lt.skip_reason
   FROM mi_ep_alerts a
   LEFT JOIN mi_live_trades lt
     ON lt.ticker=a.ticker AND lt.alert_date=a.alert_date
   WHERE a.alert_date = CURRENT_DATE AND a.score_tier='HIGH';
   ```
   Every HIGH row must have a status in
   `('filled','closed','order_placed','pending_confirmation')` **or** a
   non-null `skip_reason` with one of the bounded prefixes. Zero rows with
   `(status IS NULL AND skip_reason IS NULL)`.
2. `/why TICKER` round-trip: known-entered shows entry; known-skipped shows
   skip reason; unknown shows "no EP alert, trade row, or audit events".
3. Evening brief counts must tie to query (1).
4. **Retro-fit 2026-04-22:** run the backfill script on the server so the EOD
   recap and `get_ep_outcomes` are clean for the hang day:
   ```bash
   # dry run
   docker compose -f docker/docker-compose.prod.yml exec market-agent \
     python scripts/backfill_orphan_ep_alerts.py 2026-04-22
   # apply
   docker compose -f docker/docker-compose.prod.yml exec market-agent \
     python scripts/backfill_orphan_ep_alerts.py 2026-04-22 --apply
   ```
   Inserts one skipped row per orphan HIGH with reason
   `infra:subscribe_timeout: event-loop hang — retro-fit`.
5. **Monthly aggregation:** `SELECT split_part(skip_reason, ':', 1),
   split_part(skip_reason, ':', 2), COUNT(*) FROM mi_live_trades WHERE
   status='skipped' GROUP BY 1,2` — stable vocabulary, not free-form prose.

### Files Changed
`broker/skip_reasons.py` (new), `broker/live_tracker.py`, `broker/bar_stream.py`,
`broker/order_manager.py`, `backtester/filters.py`, `scheduler.py`, `briefing.py`,
`agent.py`, `db.py`, `scripts/backfill_orphan_ep_alerts.py` (new), `AGENTS.md`

---

## Changes Made 2026-04-22 (session 2) — Humanize skip reasons + theme validation rate-limit

### Problem
Two user-visible issues after the EP diagnostics deploy:
1. **Raw prefix leak into Telegram.** EOD EP recap, Live Trade Updates, `/why`,
   `/trades_detail skipped`, etc. rendered `infra:subscribe_timeout: 5s SDK lock stuck`
   directly to the user. Machine vocabulary is great for SQL aggregation and terrible
   for reading on a phone.
2. **"20 parse errors" per validation run were actually Anthropic 429s.**
   `mi_audit_log.validation_error` rows showed
   `RateLimitError: Error code: 429 ... rate limit of 50 requests per minute`. The
   nightly `_validate_theme_membership()` fan-outs `asyncio.gather` across every
   active theme simultaneously — 20 themes × 1 Haiku call each blew the org-level
   rate cap and every one was caught by `except Exception` and mislabeled as a
   "parse error."

### A. `humanize(reason)` — single translator (`broker/skip_reasons.py`)
One `_HUMAN_LABELS` dict maps every `category:code` prefix to a short phrase
(e.g. `infra:subscribe_timeout` → `"Bar subscribe timed out"`). `humanize()`
preserves the free-form detail after the second colon as a parenthetical, and
falls through unchanged on `None`, empty, unknown prefix, or legacy free-form
strings. **Machine prefixes stay in the DB; humans see prose.**

Applied to every Telegram-facing display site:
- `broker/live_tracker.py` — ORB-skipped alert, filtered-today evening section
- `broker/bar_stream.py` — subscribe-failure Telegram
- `scheduler.py` — EOD EP recap
- `briefing.py` — evening brief EP outcomes section
- `agent.py` — `/why` outcome line, `/trades_detail skipped`, history "Filtered:"
  line, performance-report skip-reason column (widened 20 → 30 chars)
- `postmortem.py` — single-trade recap

Internal logs and `mi_audit_log` keep the raw `category:code: detail` string so
monthly `split_part()` aggregation still works.

### B. Theme validation rate-limit — root cause of "parse errors"
- New `_VALIDATION_SEMAPHORE = asyncio.Semaphore(2)` in `theme_engine.py` caps
  concurrent Haiku calls at 2 (fan-in for the nightly `asyncio.gather` of 20+
  themes). With Anthropic's 50-rpm org cap and 2–3s response time per call,
  2 concurrent × 20 themes completes in ~30s well under the cap.
- Retry-once on 429 with 8–12s jitter before giving up.
- **Split exception handling**: `RateLimitError` now writes an
  `anthropic_rate_limited` audit event during the retry and a
  `validation_rate_limited` event if the retry also fails. Non-429 exceptions
  still write `validation_error`. The morning-brief banner and nightly error
  banner now show three separate buckets (🔴 errors / 🟠 rate-limited /
  🟡 parse errors) so the user can tell at a glance which class of failure
  happened.

### ⚠️ Post-deploy verification
1. Trigger a Telegram display of any skipped trade (`/trades_detail skipped` or
   wait for next EOD recap). Output should read as English prose — no `infra:`,
   `filter:`, `window:` prefixes visible anywhere in user-facing Telegram
   messages.
2. Watch tomorrow's overnight error banner after the nightly theme validation
   run. Previous "20× parse error" collapse should no longer appear; if any
   validation failed, it should show as 🟠 rate-limited (rare) with the count,
   not 🟡 parse error.
3. DB invariant unchanged: `skip_reason` values in `mi_live_trades` still match
   the bounded-prefix regex — check with `SELECT DISTINCT split_part(skip_reason, ':', 1)
   FROM mi_live_trades WHERE status='skipped'` — categories must all be in
   `{filter, setup, block, infra, window}`.

### Files Changed
`broker/skip_reasons.py`, `broker/live_tracker.py`, `broker/bar_stream.py`,
`theme_engine.py`, `scheduler.py`, `briefing.py`, `agent.py`, `postmortem.py`,
`AGENTS.md`

---

## Changes Made 2026-04-22 (session 3) — 9M Sugar Baby going-in shape capture

### Problem
Tonight's sugar baby watchlist (FRMI, BSX, SIRI, TLRY) surfaced a gap: the
detector greenlights on intraday geometry (9M day + green close + top 25% of
range + 3× ADV) but captures nothing about **what the chart looked like going
in**. Pradeep's 9M edge assumes a stock is in an uptrend or bottoming
reversal — a falling-knife bounce and a quiet-consolidation breakout score
identically in the DB today, even though their Day 2 outcomes differ wildly.
FRMI is the canonical failure mode: down ~75% since Oct 2025 IPO, single
green day triggers, no structural basis for continuation.

**Decision:** don't tighten the filter yet — capture the metrics, bucket at
query time, build 30+ outcome dataset, then gate. Telemetry-first.

### A. New columns on `mi_9m_sugar_babies`
Six idempotent `ALTER TABLE ADD COLUMN IF NOT EXISTS` in `initialize_schema`:

| Column | Meaning |
|---|---|
| `prev_5d_pct` | % change prev_close vs close_5d_ago — short-term pre-9M move |
| `prev_20d_pct` | % change prev_close vs close_20d_ago — mid-term trend |
| `prev_vs_sma10` | prev_close / SMA-10 — ratio, <1 = below, >1 = above |
| `prev_vs_sma50` | prev_close / SMA-50 — mid-term structural position |
| `sma50_slope_pct` | % change SMA-50 vs SMA-50-5d-ago — trend direction |
| `prior_sessions` | Count of prior daily closes available (sub-30 = recent IPO) |

All computed at YESTERDAY's state (prev_close and its prior windows), not
today's close. This is the "shape going into the 9M day" measurement — a
+30% 9M day on a stock that was already extended before is a chase; a +30%
9M day on a quiet consolidation is a breakout. Distinguishable now.

### B. SQL changes — `get_eod_9m_sugar_babies`
Replaced the single-purpose `ma10` CTE with:
- `ranked` CTE: prior 60 sessions windowed by `ROW_NUMBER() OVER (PARTITION
  BY ticker ORDER BY trade_date DESC)`. Single scan.
- `ctx` CTE: `FILTER (WHERE rn = N)` picks individual prior closes (rn=1 =
  prev, rn=6 = 5d ago, rn=21 = 20d ago). `AVG(close) FILTER (WHERE rn <= N)`
  picks rolling SMAs. `HAVING COUNT(*) >= 10` keeps the IPO-reject invariant.

Six computed columns now flow through SELECT with existing NULL-safe
`CASE WHEN` divisors.

### C. Data plumbing
- `insert_9m_sugar_baby()` — `INSERT` expanded from 8 → 14 columns;
  `ON CONFLICT DO UPDATE` mirrors; `record.get("...")` pattern so legacy
  callers without shape metrics silently write NULLs.
- `run_9m_eod_sweep()` — passes all 6 metrics from the SQL dict through to
  the insert.
- `get_pending_9m_sugar_babies()` and `get_9m_ep_history()` — SELECT
  extended to return the new columns so read-side handlers can surface them.

### D. Shape tag + display
`ninem_detector._shape_tag()` — deterministic bucket from the raw metrics:

| Tag | Condition |
|---|---|
| `uptrend` | `prev_vs_sma50 ≥ 1.0 AND sma50_slope ≥ 0` |
| `pullback` | uptrend + `prev_5d_pct < 0` (healthy pullback in uptrend) |
| `extended` | uptrend + `prev_vs_sma10 ≥ 1.15 AND prev_5d_pct ≥ 15` (chase) |
| `bounce` | `prev_vs_sma50 < 0.95 AND prev_20d_pct ≤ -5 AND prev_5d_pct ≥ 10` |
| `downtrend` | `prev_vs_sma50 < 0.95 AND prev_20d_pct ≤ -5` |
| `flat` | everything else |

Surfaced in:
- Evening briefing sugar babies section: `5d +X% / 20d +Y% / tag`
- `/9m` today's candidates and yesterday's-pending listings
- `9m outcomes` history rows get `20d X% / tag` suffix

Bucket definitions live in code so they can evolve without re-migrating
historical rows — raw metrics are the source of truth on disk.

### ⚠️ Post-deploy verification
1. After next nightly `_nightly_data_pull` (5 PM ET), query
   `SELECT ticker, prev_5d_pct, prev_20d_pct, prev_vs_sma50, sma50_slope_pct,
   prior_sessions FROM mi_9m_sugar_babies WHERE alert_date = CURRENT_DATE` —
   all six columns populated for every row.
2. Evening brief 🍭 section shows `5d / 20d / tag` suffix on each ticker.
3. Historical rows (pre-deploy): columns are NULL, tag is empty, raw
   pre-shape layout still renders (backward-compatible).
4. After ~30 sugar babies tracked: run
   `SELECT CASE …_shape_tag logic… AS tag, AVG(day2_gain_pct), COUNT(*)
   GROUP BY tag` against `mi_signal_outcomes` join to see which shape
   buckets actually produce Day 2 edge. Use that to inform whether to
   add a hard filter or keep telemetry-only.

### Files Changed
`db.py` (schema ALTERs, get_eod_9m_sugar_babies SQL rewrite, insert +
read-side columns), `ninem_detector.py` (pass-through in run_9m_eod_sweep,
new `_shape_tag` helper, evening briefing section updated), `agent.py`
(`/9m` + `9m outcomes` handlers render shape), `AGENTS.md`
