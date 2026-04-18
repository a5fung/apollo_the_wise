# Apollo the Wise — Claude Context

## Session Sync Protocol
At the start of every session: `git pull origin main`
Read "Changes Made" sections to understand prior sessions.

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
core/          orchestrator.py, router.py, context.py, memory.py, confirmations.py
agents/
  market_intelligence/
    agent.py           # execute_task() routes by keyword
    db.py              # All DB queries — single source of truth for schema
    rs_engine.py       # RS scoring (~9700 stocks)
    ep_detector.py     # MAGNA53 EP scoring + Claude + Gemini
    theme_engine.py    # Theme discovery, dedup, lifecycle
    briefing.py        # Briefing formatters + send_telegram_message
    scheduler.py       # APScheduler jobs
    broker/            # Alpaca ORB trading
channels/      telegram.py, webhooks.py
shared/        models.py, registry.py, secrets.py
```

## Adding a Sub-Agent Tool
1. Tool schema → `core/router.py` → `get_orchestrator_tools()`
2. Dispatch → `core/orchestrator.py` → `_dispatch_tool()`
3. Handle → `agents/<name>/agent.py` → `execute_task()`

## Market Agent Routing (`execute_task`)
Order matters — first match wins:
1. watchlist / 2. theme engine rerun / 3. refresh / 4. history
5. EP outcomes ("ep outcome", "ep performance", "ep returns", "ep results")
6. EP ("ep", "episodic", "gap", "pivot", "gapper")
7. journal add ("journal:", "log trade") / journal query ("show journal", "my journal")
8. theme ("theme", "sector", "industry") — before regime/RS
9. regime / 10. RS/score / 11. briefing / 12. pullback / 13. fundamentals
14. screener / 15. audit log ("audit log", "show logs", "show errors") / 16. fallback

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

### Error Alerting
- Silent failures in theme engine now write to `mi_audit_log` with event types: `validation_error`, `assignment_error`, `discovery_error`
- After nightly run: if any `*_error` events in last 2h → immediate Telegram alert
- Morning briefing: shows overnight error count at top if any
- Telegram: `show errors 7d` pulls all error events for the period

### Paper Trading (Alpaca)
- `mi_paper_trades` = EOD simulation table (LIVE_TRADING_ENABLED=true, ALPACA_PAPER=true)
- `mi_live_trades` = actual Alpaca order table
- ORB entry at 9:31 AM; bracket order: stop-limit buy at ORB high, stop at ORB low
- Safeguards: max 4 positions, 2% daily loss limit, 3-loss circuit breaker
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

## Production Deploy
- Server: `ssh apollo@87.99.134.162`, dir: `/home/apollo/apollo_the_wise/`
- Market agent only: `git pull origin main && docker compose -f docker/docker-compose.prod.yml build --no-cache market-agent && docker compose -f docker/docker-compose.prod.yml up -d market-agent`
- Both services: same but add `orchestrator` to build/up commands
- Service names: `orchestrator`, `market-agent`, `postgres`, `redis`

## Required Env Vars
```
TELEGRAM_BOT_TOKEN, TELEGRAM_ALLOWED_USER_IDS
ANTHROPIC_API_KEY, POLYGON_API_KEY, GEMINI_API_KEY, TAVILY_API_KEY
ALPACA_API_KEY, ALPACA_SECRET_KEY, ALPACA_PAPER=true, LIVE_TRADING_ENABLED=false
POSTGRES_PASSWORD, REDIS_PASSWORD, INTERNAL_API_SECRET, TRADINGVIEW_WEBHOOK_SECRET
```

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
