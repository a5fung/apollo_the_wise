# Apollo the Wise — Claude Context

## Session Sync Protocol
This file is the cross-device sync mechanism. Mobile and desktop sessions both commit changes here.

**At the start of every session:**
```bash
git pull origin main
```
Read the "Changes Made" sections at the bottom to understand what happened in prior sessions.

**At the end of every session (if code was changed):**
1. Append a `## Changes Made YYYY-MM-DD` section documenting bugs fixed / features added / files changed
2. Commit and push:
```bash
git add CLAUDE.md <changed files>
git commit -m "Brief description of changes"
git push origin main
```

## What This Is
A Telegram-based personal assistant ("chief of staff") built around market intelligence. Talks naturally in Telegram, delegates to specialized sub-agents. Primary use case is momentum/EP trading (Qullamaggie, Pradeep Bonde, Marios Stamatoudis methodology).

## Running Locally
```bash
# Terminal 1 — orchestrator + infra (Postgres, Redis)
bash start.sh

# Terminal 2 — market intelligence agent
bash start_market.sh

# Verify
# Send /agents in Telegram — all agents should show green
```

## Architecture
```
User (Telegram)
      │
Apollo Orchestrator (port 8000)   ← claude-sonnet-4-6, tool-use loop
      │  POST /task  +  X-Apollo-Secret header
      ▼
Sub-agents (Docker, each isolated):
  Market Intelligence :8006    Finance :8001
  Calendar :8002               Research :8003
  Browser :8004                Travel :8005
      │
PostgreSQL (pgvector) + Redis
```

**Key rule:** Sub-agents never talk to each other — only Apollo talks to sub-agents.

## Code Layout
```
core/
  orchestrator.py     # Claude tool-use loop (handle_message → _tool_use_loop)
  router.py           # HTTP routing to sub-agents + tool definitions for Claude
  context.py          # System prompt builder + conversation compression
  memory.py           # PostgreSQL + pgvector long-term memory
  confirmations.py    # YES/NO gate for irreversible actions

agents/
  base.py             # BaseAgent ABC: FastAPI app, POST /task, GET /health, _ok/_error helpers
  market_intelligence/
    agent.py          # MarketIntelligenceAgent — execute_task() routes by keyword
    db.py             # All DB queries (single source of truth for schema)
    rs_engine.py      # RS scoring (1M/3M/6M composite, full universe ~9700 stocks)
    ep_detector.py    # MAGNA53 EP scoring + Claude + Gemini cross-validation
    regime.py         # Market regime (Bull/Choppy/Correcting/Crisis)
    theme_engine.py   # Theme discovery, deduplication, lifecycle management
    trading_calendar.py  # NYSE holiday calendar (exchange-calendars lib, offline)
    briefing.py       # Evening + morning briefing formatters + send_telegram_message
    fundamentals.py   # O'Neil-style EPS/revenue tables via yfinance
    screener.py       # Composite screener (RS + theme stage + fundamentals)
    collector.py      # Polygon + yfinance + Tavily data fetching
    scheduler.py      # APScheduler jobs
    broker/           # Alpaca paper trading (ORB, stops, partials)

shared/
  models.py           # Pydantic models: AgentRequest/AgentResponse, ConversationMessage, MemoryEntry
  registry.py         # integrations.yaml loader — agent URLs, enabled providers
  secrets.py          # Env var secrets access

channels/
  telegram.py         # Telegram bot + /help
  webhooks.py         # FastAPI webhook receiver (TradingView alerts)

tests/
  test_theme_notification.py  # 13 tests verifying theme engine completion notification path
```

## Adding a Sub-Agent Tool
1. Define the tool schema in `core/router.py` → `get_orchestrator_tools()`
2. Add dispatch in `core/orchestrator.py` → `_dispatch_tool()`
3. Handle in the sub-agent's `execute_task()` in `agents/<name>/agent.py`

## Market Agent Routing (`execute_task`)
Routes by keyword match on `request.task.lower()`. **Order matters** — first match wins:
1. watchlist (`track `, `untrack `, `drop `, `watchlist`)
2. theme engine only (`theme engine`, `rerun theme`, ...)
3. refresh (`refresh`, `data pull`, `nightly pull`, ...)
4. history (`history`, `when did`, `peak`, `peaked`, ...) — before theme/RS
5. EP (`ep`, `episodic`, `gap`, `pivot`, `gapper`)
6. theme (`theme`, `sector`, `industry`) — before regime/RS
7. regime (`regime`, `market condition`, `spy`, `breadth`, `vix`, `risk`)
8. RS/score — if ticker found → `_handle_single_score`; else → `_handle_rs_query`
9. briefing (`brief`, `morning`, `evening`, `summary`, `overview`)
10. pullback (`pullback`, `10ma`, `20ma`, `50ma`, ...)
11. fundamentals (`fundamental`, `earnings growth`, `eps growth`, ...)
12. screener (`screener`, `screen for`, `find top`, ...)
13. fallback → `_handle_general` (Claude decides what data to pull)

**`_handle_single_score`** is the unified single-ticker handler — fetches RS + fundamentals + theme context in parallel. Both the RS route and fundamentals route call it for single-ticker queries.

## Ticker Extraction Pattern
All keyword-based ticker extraction uses:
```python
re.findall(r'\b([A-Z]{2,5})\b', request.task.upper())
```
Two shared constants at the top of `agents/market_intelligence/agent.py`:
- `_PREPOSITION_SKIP` — English short words (`OF`, `IN`, `AT`, `ON`, `BY`, `TO`, `AS`, `AN`, `OR`, `MY`, `ME`, `IS`, `IT`, `IF`, ...). Used by every call site.
- `_SINGLE_SCORE_QUERY_SKIP` — query-vocabulary words (`RS`, `SCORE`, `RANK`, `TOP`, `STOCK`, `LEADERS`, `FUNDAMENTALS`, ...). Used by BOTH the `execute_task` RS routing block AND `_handle_single_score` — they must stay identical or routing will admit a ticker the handler then rejects (bug fixed 2026-04-16).

`_handle_fundamentals_query` has its own skip set (`EPS`, `YOY`, `REV`, etc.) because fundamentals queries use different vocabulary.

## Key Domain Concepts

### RS Scoring
- **Composite** = 40% × 1M rank + 30% × 3M rank + 30% × 6M rank
- **Universe** ~9,700 US stocks via Polygon grouped daily endpoint
- **Filters**: price ≥ $10, ADV ≥ 500K (20-day median), skip leveraged/inverse ETFs, skip biotech < $50
- **Nightly**: `run_rs_engine()` — reads `mi_daily_closes`, ranks all stocks
- **On-demand**: `score_single_ticker(ticker)` — 1 Polygon call, ranks vs stored distribution

### Theme Engine
- Bottom-up from price action (not top-down hypothesis)
- Existing themes re-scored daily from current RS; Claude clustering only runs on uncovered RS leaders
- Lifecycle: Nascent → Accelerating → Mainstream → Fading → Retired (after 5 fading days)
- Deduplication: Jaccard ≥ 0.6 or ticker subset → auto-merge
- Trimmed mean RS (drops bottom 20% of constituents)
- **Stage transition uses 3-day smoothed score** (not raw daily delta) — thresholds ±8 pts
- **Description fetching**: `_ensure_descriptions()` fetches yfinance + Claude Haiku for any RS leader missing a description before clustering. Persists to DB via `upsert_ticker_overrides_batch`. Loaded from DB at startup via `get_ticker_overrides()` → `apply_overrides()`.
- **Re-validation**: `_validate_theme_membership()` runs Mon/Wed/Fri — asks Claude Haiku if each stock's description matches the theme, removes mismatches. Changelog type: `ticker_revalidated_out`.
- **Pruning**: hard (RS < 25, 1 day), soft (RS < 35, 3 days). Stocks absent from today's RS data are checked against 5-day history — if consistently below RS 25, still pruned.

### Theme Completion Notification
`_handle_theme_only` runs the theme engine **synchronously** and returns the result via `AgentResponse.result`. The orchestrator delivers it through the normal Telegram bot channel. No direct Telegram send from market-agent. Orchestrator timeout: `AGENT_TIMEOUT = 360s` in `core/router.py`.

On startup: market-agent sends "🔄 Market agent online" via `send_telegram_message`.

### EP Detection (MAGNA53)
- Inputs: gap %, relative volume, catalyst quality (Claude), neglect factor, float, regime multiplier
- HIGH ≥ 85 → immediate Telegram alert; MODERATE ≥ 65 → morning briefing
- Gemini cross-validation: Claude + Gemini agree → 1.2× confidence multiplier
- Scan: 7:00–9:30 AM ET every 5 min

### Market Regime
| Label | EP Bar | Signals |
|---|---|---|
| Bull | ≥70 | SPY/QQQ above 50MA + 200MA, VIX low |
| Choppy | ≥80 | Mixed signals |
| Correcting | ≥85 | Below key MAs |
| Crisis | ≥90 | Very defensive |

### NYSE Holiday Calendar
`trading_calendar.py` wraps the `exchange-calendars` library (offline, rule-based). Used in `scheduler.py` to skip nightly data pull and EP scan on market holidays. Fails open (returns `is_trading_day=True`) on library error so the 0-ingest guardrail still catches real failures.

### Paper Trading (Alpaca)
- ORB entry at 9:31 AM (first 1-min bar)
- Bracket order: stop-limit buy at ORB high, stop-loss at ORB low
- Day 2+ management: SMA 10/20 trailing stops, 1/3 partial exit on Day 3–5
- Safeguards: max 4 positions, 2% daily loss limit, 3-loss circuit breaker
- Master kill switch: `LIVE_TRADING_ENABLED=false` (env var)

### TradingView Webhooks
`channels/webhooks.py` → `POST /tradingview/alert?token=TRADINGVIEW_WEBHOOK_SECRET`
- **Markdown escaping**: strip `*`, `_`, backtick, `[]` from alert_name and message before sending — TradingView names like `RSI_Overbought_1D` break Telegram Markdown v1 → silent 400 drop
- Send base notification **immediately**, then enrichment via `_apollo.handle_message` runs as background task (separate follow-up message)
- Plain-text fallback if Markdown send fails

## Daily Schedule (ET)
| Time | Job |
|---|---|
| 7:00 AM | EP scan starts; HIGH alerts fire in real-time |
| 9:00 AM | Morning briefing → Telegram |
| 9:31 AM | ORB monitor — fetch first bar, place bracket orders |
| 9:35 AM | Stop refresh for Day 2+ positions |
| 10:00 AM | EP scan stops |
| 4:05 PM | EOD cleanup — cancel unfilled orders, sync positions |
| 4:30 PM | Data pull — RS engine + regime + themes |
| 4:45 PM | Position update — SMA trail, partials, stop updates |
| 8:00 PM | Evening briefing → Telegram |

## Data Sources
| Source | Use | Key |
|---|---|---|
| Polygon.io | Price history, RS engine, EP gap data | Starter tier ($29/mo) |
| yfinance | Fundamentals, sector, analyst data | Free |
| Tavily | News search, EP catalyst validation | Free/Pro |
| Anthropic | Orchestrator + Claude for market analysis | `ANTHROPIC_API_KEY` |
| Gemini | EP cross-validation (gemini-1.5-flash-8b) | `GEMINI_API_KEY` |
| Alpaca | Paper trading + ORB bars | `ALPACA_API_KEY` + `ALPACA_SECRET_KEY` |

## Required Env Vars
```
TELEGRAM_BOT_TOKEN
TELEGRAM_ALLOWED_USER_IDS
ANTHROPIC_API_KEY
POLYGON_API_KEY
GEMINI_API_KEY
TAVILY_API_KEY
ALPACA_API_KEY
ALPACA_SECRET_KEY
ALPACA_PAPER=true
LIVE_TRADING_ENABLED=false
POSTGRES_PASSWORD
REDIS_PASSWORD
INTERNAL_API_SECRET
TRADINGVIEW_WEBHOOK_SECRET
```

## Important Conventions
- **Telegram formatting**: Use Markdown (bold, code blocks). NEVER use pipe tables (`| col |`) — Telegram can't render them. Always use monospace code blocks for tabular data.
- **Sub-agent output**: Return formatted strings in `result` field of `AgentResponse`. Orchestrator passes them through to Telegram verbatim for briefings/lists/tables.
- **Single-ticker analysis**: `_handle_single_score` returns raw data first, then orchestrator adds brief analytical commentary (4–6 lines max).
- **Confirmation gate**: Any irreversible action (trade, calendar change) must go through `request_confirmation()` before executing.
- **Auth**: All inter-service calls use `X-Apollo-Secret` header. See `shared/secrets.py`.
- **No agent-to-agent calls**: All routing goes through the orchestrator. Sub-agents are isolated.
- **send_telegram_message**: defined in `briefing.py`. Used by scheduler for alerts/briefings. Market-agent startup sends "🔄 Market agent online". Returns `False` on failure (never raises). Always escape dynamic strings before passing if using Markdown.

## Production Deploy
- Target: Hetzner CPX21 Ashburn (~$8/mo), directory: `/home/apollo/apollo_the_wise/` (lowercase)
- SSH: `ssh apollo@87.99.134.162` (key `~/.ssh/id_ed25519`)
- Deploy market-agent only: `git pull origin main && docker compose -f docker/docker-compose.prod.yml build --no-cache market-agent && docker compose -f docker/docker-compose.prod.yml up -d market-agent`
- Deploy both (needed when changing orchestrator code like router.py): `git pull origin main && docker compose -f docker/docker-compose.prod.yml build --no-cache orchestrator market-agent && docker compose -f docker/docker-compose.prod.yml up -d orchestrator market-agent`
- Service names in docker-compose: `orchestrator`, `market-agent`, `postgres`, `redis`
- Includes Uptime Kuma for self-hosted status monitoring

## Feature State (as of 2026-04-15)

### Theme Engine — current architecture
- `mi_theme_exclusions` table: user-directed (ticker, theme_name) bans. Commands: "exclude X from [theme]", "list exclusions", "remove exclusion X from [theme]". **NOT** auto-populated from validation removals — those are self-healing.
- `mi_audit_log` table: advisor_call, theme_discovered, theme_retired, stage_change, theme_excluded. Telegram: "audit log", "advisor log", "show logs 7d".
- Advisor strategy: `_call_advisor(question, context, caller)` in `theme_engine.py`. Sonnet auto-escalates to Opus on hard decisions. `_MAX_ADVISOR_CALLS=3` per run.
- `_strip_commodity_contradictions(themes)` — prevents e.g. gold miners entering uranium theme.
- `_merge_overlapping_themes` has `protected_names` — existing themes protected from absorption by new clusters.
- Fat theme splitting: themes >20 stocks → Sonnet proposes sub-theme split (3–8 stocks). `parent_theme` column in `mi_themes`.
- Name inheritance on rediscovery: Jaccard ≥ 0.4 overlap → retired theme name reused.
- `get_ticker_overrides` filters `WHERE description IS NOT NULL` — prevents sector-only rows from overwriting descriptions (was root cause of TSEM semiconductor→oil&gas misassignment).

### EP / ORB — current architecture
- `broker/bar_stream.py`: Alpaca `StockDataStream` for real-time ORB entry. Pre-market HIGHs subscribed; order fires on first bar close at 9:30:59.
- 9:31 ORB fallback in `_ep_scan_job`: always calls `_orb_monitor_job()` at minute==31 as bar-stream safety net.
- M&A hard filter: `"mna"` catalyst enum → `is_mna=True` → hard skip before scoring.
- Conviction floor: gap ≥ 10% + game_changer → floor 60 (MODERATE). gap ≥ 15% → floor 75. Eliminates dead zone.
- Open intensity (not projected RVOL): `intensity = raw_rvol * (390 / minutes_since_open)`.
- 11 AM re-entry cutoff: `order_manager.attempt_day1_reentry` closes trade instead of re-entering after 11 AM.
- `validate_orb_entry(orb_high, orb_low, atr_14)` in `backtester/filters.py` — single source of truth for ORB stop-width check (both EOD sim and live path import this).

### Single-ticker queries
- Two-layer RS context: Layer 1 = theme rank (e.g. "#3 of 12 in AI Infrastructure"), Layer 2 = GICS industry percentile.
- EP diagnostic: "why not EP TICKER?" → `_handle_ep_diagnostic` stops at first filter failure.
- Research queries fetch Perplexity news in parallel; RS-only / fundamentals-only do not.
- VIX: Polygon `I:VIX` always fails on Starter plan; yfinance `^VIX` fallback used with end+1 day fix.

### Backtester / shared helpers
- `BacktestTrade` has proper fields: `remaining_shares`, `last_entry`, `day1_low`.
- `parse_json_list` and `format_trade_attempts` in `backtester/tracker.py` — shared by agent.py, telegram.py, tracker.py.

## Changes Made 2026-04-15
- **Bug fixed**: `ep_detector.py` missing `datetime` import — `from datetime import date` only, but `datetime.now()` used for open intensity metric. All EP scans failing since deploy. Fix: `from datetime import date, datetime, timedelta`.

## Changes Made 2026-04-16
### Design review + backlog (branch: claude/apollo-design-review-cEVYD)
- Added P17–P20 to README backlog (stop order timeout, alert reasoning traces, per-regime daily loss limit, HTTPS on webhook)

### Code review fixes (commit 608e87c)
- `agent.py`: Extracted `_SINGLE_SCORE_QUERY_SKIP` frozenset — `execute_task` RS block (line ~515) and `_handle_single_score` (line ~1612) now share the same constant. Previously they drifted: routing admitted tickers the handler then rejected (silent "please specify a ticker").
- `confirmations.py`: `datetime.utcnow()` → `datetime.now(timezone.utc)` (Python 3.12+ deprecation)
- `ep_detector.py` + `collector.py`: Explicit bounds check on Perplexity `choices[0]` — empty response now logs a clear warning instead of being swallowed as generic IndexError
- `backtester/filters.py`: ATR% guard raised from `last_close > 0` to `last_close >= 1.0` (sub-$1 penny stocks produced meaningless volatility percentages)
- `CLAUDE.md`: Updated ticker extraction section to document `_SINGLE_SCORE_QUERY_SKIP` invariant

### EP detection + ORB entry P0 fixes (commit e6408df)
- `broker/bar_stream.py`: ORB bar handler only accepted `minute==30`. Halted/delayed-open stocks send first bar at minute 31–45 — silently dropped, trade never fired. Now accepts 9:30–9:45 ET window.
- `broker/alpaca_client.py`: `get_first_bar` queried only 9:30–9:35; delayed-open retries re-queried same narrow window. Extended to 9:30–10:00 (30 min). Added `client_order_id` param to `place_bracket_order`.
- `broker/order_manager.py`: `submit_entry` had no idempotency key — network timeout + retry created duplicate Alpaca positions. Now uses `f"apollo-{trade_id}-entry"` on both calls.
- `broker/live_tracker.py`: `process_new_alerts_live` skipped tickers with any existing `mi_live_trades` row including `order_failed` — failed submissions blocked retries all day. Now detects `order_failed`, deletes stale row, re-submits.
- `ep_detector.py`: `already_today` blocked re-scoring any ticker seen earlier that day regardless of tier. Escalating MODERATE→HIGH setups were dropped. Now tracks `score_tier`; only `HIGH` blocks re-scoring.

### Theme engine flakiness fixes (commit 88d5f8a)
- `theme_engine.py`: `uncovered_stocks` was passed to Claude clustering in RS-score arrival order. RS ties broke differently each run → same leaders produced different clusters on different days. Now sorted by ticker before building both `_assign_uncovered_to_themes` and `_discover_new_themes` prompts.
- `theme_engine.py`: Missing-RS ticker pruning used `if hist and all(...)` — empty hist (no RS data for 5 days) evaluated to False, leaving delisted/acquired/halted tickers in themes as zombies that contaminated RS averages and clustering. Now explicitly prunes on empty hist with reason logged.
