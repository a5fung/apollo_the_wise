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
    briefing.py       # Evening + morning briefing formatters
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

### Paper Trading (Alpaca)
- ORB entry at 9:31 AM (first 1-min bar)
- Bracket order: stop-limit buy at ORB high, stop-loss at ORB low
- Day 2+ management: SMA 10/20 trailing stops, 1/3 partial exit on Day 3–5
- Safeguards: max 4 positions, 2% daily loss limit, 3-loss circuit breaker
- Master kill switch: `LIVE_TRADING_ENABLED=false` (env var)

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
```

## Important Conventions
- **Telegram formatting**: Use Markdown (bold, code blocks). NEVER use pipe tables (`| col |`) — Telegram can't render them. Always use monospace code blocks for tabular data.
- **Sub-agent output**: Return formatted strings in `result` field of `AgentResponse`. Orchestrator passes them through to Telegram verbatim for briefings/lists/tables.
- **Single-ticker analysis**: `_handle_single_score` returns raw data first, then orchestrator adds brief analytical commentary (4–6 lines max).
- **Confirmation gate**: Any irreversible action (trade, calendar change) must go through `request_confirmation()` before executing.
- **Auth**: All inter-service calls use `X-Apollo-Secret` header. See `shared/secrets.py`.
- **No agent-to-agent calls**: All routing goes through the orchestrator. Sub-agents are isolated.

## Production Deploy
- Target: Hetzner CPX21 Ashburn (~$8/mo)
- `docker compose -f docker/docker-compose.prod.yml up -d --build`
- Includes Uptime Kuma for self-hosted status monitoring
