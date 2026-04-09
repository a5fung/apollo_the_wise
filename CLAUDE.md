# Apollo the Wise — Claude Context

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
Skip sets must include common English short words (`OF`, `IN`, `AT`, `ON`, `BY`, `TO`, `AS`, `AN`, `OR`, `MY`, `ME`, `IS`, `IT`, `IF`, ...) to prevent prepositions from being parsed as tickers. Bug fixed 2026-04-06 — always update all three skip sets when adding words:
- `execute_task` routing block (line ~415)
- `_handle_single_score` skip set (line ~883)
- `_handle_fundamentals_query` skip set (line ~999)

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
| 9:35 AM | EP scan stops; stop refresh for Day 2+ positions |
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
- Target: Hetzner CPX21 Ashburn (~$8/mo), directory: `/home/Apollo/apollo_the_wise/`
- Server runs as root; git ownership fix: `git config --global --add safe.directory /home/Apollo/apollo_the_wise`
- Deploy market-agent only: `git pull origin main && docker compose -f docker/docker-compose.prod.yml build --no-cache market-agent && docker compose -f docker/docker-compose.prod.yml up -d market-agent`
- Deploy both (needed when changing orchestrator code like router.py): `git pull origin main && docker compose -f docker/docker-compose.prod.yml build --no-cache orchestrator market-agent && docker compose -f docker/docker-compose.prod.yml up -d orchestrator market-agent`
- Service names in docker-compose: `orchestrator`, `market-agent`, `postgres`, `redis`
- Includes Uptime Kuma for self-hosted status monitoring

## Changes Made 2026-04-08 (mobile session, desktop died)

### Bugs Fixed
1. **Ticker extraction** (`agent.py`): Regex `\b([A-Z]{2,5})\b` matched prepositions like "OF" in "fundamentals of VIAV". Fixed by adding `OF`, `IN`, `AT`, `ON`, `BY`, `TO`, `AS`, `AN`, `OR`, `MY`, `ME`, `IS`, `IT`, `IF` etc. to skip sets in all 3 locations.

2. **Good Friday false alert** (`scheduler.py` + new `trading_calendar.py`): `weekday() < 5` didn't know NYSE holidays. Fixed with `exchange_calendars` library. Added `get_market_status(date)` in `trading_calendar.py` — used in `_nightly_data_pull`, `check_missed_jobs`, `_ep_scan_watchdog`.

3. **Theme engine completion notification** (`agent.py`): Was using `asyncio.create_task` (background task) that called `send_telegram_message` directly — silently failed. Fixed by running theme engine synchronously in `_handle_theme_only` and returning result via `AgentResponse.result` (flows through orchestrator → Telegram bot). Required raising `AGENT_TIMEOUT` to 360s in `core/router.py`.

4. **TradingView alerts** (`channels/webhooks.py`): Alert names with underscores (e.g. `RSI_Overbought_1D`) broke Telegram Markdown → silent 400 → no notification. Fixed by stripping Markdown chars from dynamic fields. Also moved enrichment to background task so base notification sends immediately.

5. **Theme state instability** (`theme_engine.py`): `delta > 3` threshold caused 8-12 daily theme state changes (noise from binary Perplexity news_score ±30). Fixed with 3-day smoothed score baseline and ±8 thresholds. Fading recovery now requires `smooth_delta > 5` (was `>= 0`).

6. **KTOS perpetual pruning** (`theme_engine.py`): Stocks absent from today's RS data were kept in themes ("no data → keep"). KTOS (RS 10) oscillated based on whether RS engine captured it. Fixed by checking 5-day RS history for missing tickers — if consistently < RS 25, prune regardless.

7. **Bogus theme membership** (`theme_engine.py`): Added `_ensure_descriptions()` to fetch descriptions for RS leaders before clustering. Added `_validate_theme_membership()` (Mon/Wed/Fri) to remove stocks whose description doesn't match theme via Claude Haiku.

8. **Market agent startup notification** (`agent.py`): No notification on container restart. Added `send_telegram_message("🔄 Market agent online")` at end of `startup()`.

### Files Changed
- `agents/market_intelligence/agent.py` — ticker skip sets, sync theme handler, startup notification
- `agents/market_intelligence/theme_engine.py` — _ensure_descriptions, _validate_theme_membership, smooth stage transitions, KTOS fix
- `agents/market_intelligence/scheduler.py` — holiday checks in 3 jobs
- `agents/market_intelligence/trading_calendar.py` — NEW: NYSE calendar wrapper
- `core/router.py` — AGENT_TIMEOUT raised to 360s
- `channels/webhooks.py` — TradingView Markdown escaping, immediate send
- `requirements/base.txt` — added exchange-calendars>=4.5
- `tests/test_theme_notification.py` — NEW: 13 tests, all passing
- `CLAUDE.md` — this file

## Changes Made 2026-04-09

### Bugs Fixed

1. **Overnight brief still showed futures names (`ES=F`/`NQ=F`)** (`db.py`, `agent.py`, `briefing.py`, `collector.py`): The 2026-04-08 rename to SPY/QQQ was incomplete — the DB watchlist table still seeded `ES=F`/`NQ=F`, `name_to_symbol` in `_handle_watchlist` still mapped `"SPY"→"ES=F"`, and briefing still used old key names. Full migration:
   - `db.py` `initialize_schema()`: Added inline migration `DELETE FROM mi_overnight_watchlist WHERE symbol IN ('ES=F', 'NQ=F')` followed by `INSERT ... ('SPY', ...), ('QQQ', ...)` seed.
   - `agent.py` `name_to_symbol`: Changed `"SPY": "ES=F"` → `"SPY": "SPY"`, `"NASDAQ": "NQ=F"` → `"NASDAQ": "QQQ"`.
   - `collector.py`: Renamed `get_premarket_futures()` → `get_premarket_snapshot()`, return keys `es_pct`/`nq_pct` → `spy_pct`/`qqq_pct`, fixed log messages.
   - `briefing.py`: Updated all call sites and key references (`futures`→`premarket`, `es_pct`/`nq_pct`→`spy_pct`/`qqq_pct`, label "Futures:"→"Pre-market:", comment example `ES -1.8% | NQ -2.3%`→`SPY -1.8% | QQQ -2.3%`). Added Polygon override for SPY/QQQ in overnight snapshot (yfinance is stale pre-market, Polygon data is accurate):
     ```python
     polygon_map = {"SPY": premarket.get("spy_pct"), "QQQ": premarket.get("qqq_pct")}
     for item in snapshot:
         pct = polygon_map.get(item["symbol"])
         if pct is not None:
             item["pct_change"] = round(pct, 2)
             item["triggered"] = abs(pct) >= item["threshold"]
     ```

2. **VIX showing 41 when actual VIX <20** (`collector.py`, `regime.py`): `regime.py` was using UVXY (a leveraged inverse VIX ETF) as a VIX proxy — UVXY price ≠ VIX index value. Fixed by adding `get_vix_history(from_date, to_date)` in `collector.py` that fetches actual VIX index via Polygon `I:VIX`, with yfinance `^VIX` fallback. `regime.py` updated to call `get_vix_history()` instead of `get_index_history("UVXY", ...)`.

3. **Theme validation not removing bogus members (CAR in data center theme)** (`theme_engine.py`): `_validate_theme_membership()` used `json.loads()` on raw Haiku response. Haiku sometimes prepends explanation text before the JSON object, causing parse failure. The `except` block silently kept all tickers unchanged — CAR was never removed. Fixed with regex fallback extraction:
   ```python
   raw = resp.content[0].text.strip()
   if raw.startswith("```"):
       raw = raw.split("\n", 1)[1].rstrip("` \n").strip()
   if not raw.startswith("{"):
       m = re.search(r'\{.*\}', raw, re.DOTALL)
       raw = m.group(0) if m else raw
   result = json.loads(raw)
   ```

4. **`_discover_new_themes` bypassing shared Anthropic client** (`theme_engine.py`): Line 752 used `anthropic.AsyncAnthropic(api_key=...)` directly instead of the shared `_get_anthropic_client()` lazy initializer. This bypassed any shared client config/retry logic and wasted connection resources. Fixed to use `_get_anthropic_client()`.

5. **Tests broken by `get_premarket_futures` rename** (`tests/test_recent_changes.py`): Rewrote all affected test classes to use the new function name, new key names (`spy_pct`/`qqq_pct`), and Polygon mock instead of yfinance mock.

### Key Design Decisions

- **SPY/QQQ pre-market accuracy**: For the overnight watchlist display, yfinance returns stale previous-close data before market open. Polygon's snapshot endpoint returns actual pre-market trading data. The Polygon override for SPY/QQQ is intentional — always prefer Polygon for these two specific symbols in morning brief context.
- **Actual VIX only**: Do not use any ETF (UVXY, VXX, VIXY) as a VIX proxy. These products have tracking error, leverage decay, and roll costs that make their price completely disconnected from VIX index levels. Always use `I:VIX` (Polygon) or `^VIX` (yfinance).
- **Theme validation parsing**: Haiku (claude-haiku-4-5) frequently adds explanation text before returning JSON. All Haiku JSON responses must use the regex extraction fallback pattern. Do not rely on raw `json.loads()` for Haiku responses.

### Files Changed
- `agents/market_intelligence/db.py` — DB migration to replace ES=F/NQ=F with SPY/QQQ in overnight watchlist
- `agents/market_intelligence/agent.py` — name_to_symbol drop/untrack mapping fix (SPY→SPY, NASDAQ→QQQ)
- `agents/market_intelligence/collector.py` — renamed get_premarket_futures→get_premarket_snapshot, keys es_pct/nq_pct→spy_pct/qqq_pct, added get_vix_history()
- `agents/market_intelligence/briefing.py` — all futures→SPY/QQQ references updated, Polygon override for pre-market accuracy
- `agents/market_intelligence/regime.py` — VIX: UVXY proxy → actual VIX via get_vix_history()
- `agents/market_intelligence/theme_engine.py` — JSON parsing robustness for Haiku responses, _discover_new_themes client fix
- `tests/test_recent_changes.py` — updated for premarket snapshot rename + new key names
- `CLAUDE.md` — this file
