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
   - `briefing.py`: Updated all call sites and key references. Added Polygon override for SPY/QQQ in overnight snapshot (yfinance is stale pre-market).

2. **VIX showing 41 when actual VIX <20** (`collector.py`, `regime.py`): `regime.py` was using UVXY (a leveraged inverse VIX ETF) as a VIX proxy. Fixed by adding `get_vix_history()` that fetches actual VIX index via Polygon `I:VIX`, with yfinance `^VIX` fallback.

3. **Theme validation not removing bogus members** (`theme_engine.py`): `_validate_theme_membership()` used `json.loads()` on raw Haiku response. Haiku sometimes prepends explanation text → parse failure → silent keep-all. Fixed with regex fallback extraction before `json.loads()`.

4. **`_discover_new_themes` bypassing shared Anthropic client** (`theme_engine.py`): Fixed to use `_get_anthropic_client()` lazy initializer.

### Files Changed
- `agents/market_intelligence/db.py`, `agent.py`, `collector.py`, `briefing.py`, `regime.py`, `theme_engine.py`
- `tests/test_recent_changes.py`, `CLAUDE.md`

## Changes Made 2026-04-09 (second session)

### Bugs Fixed

1. **Theme engine rerun silently broken** (`channels/telegram.py`): `_try_fast_path` intercepted "theme engine" keywords before orchestrator and called old `/theme/run` background endpoint (no result delivery). Fix: deleted the fast-path block. Rerun now flows through orchestrator → `_handle_theme_only` which awaits synchronously and returns the full scorecard.

2. **Theme rerun returned only a short summary** (`agent.py`): `_handle_theme_only` returned one line, so orchestrator Claude would ask "Want me to pull the full breakdown?" Fixed to return a full stage-grouped scorecard (same format as evening brief).

3. **"Show themes" returning pipe tables** (`agent.py`): `_handle_theme_query` format caused Claude to reformat as pipe tables. Replaced with stage-grouped brief-style format.

4. **Theme stage resetting to Nascent after rename** (`theme_engine.py`): `_get_theme_history` used exact name match. Fixed with Jaccard ticker-overlap fallback (threshold 0.4) — renamed themes inherit history from prior name.

5. **Orchestrator Claude reformatting theme results** (`core/context.py`): Added explicit system prompt instruction to output theme rerun result verbatim, no follow-up questions.

### Files Changed
- `channels/telegram.py`, `channels/webhooks.py`, `agents/market_intelligence/agent.py`
- `agents/market_intelligence/theme_engine.py`, `core/context.py`, `CLAUDE.md`
## Changes Made 2026-04-09 (third session)

### Bug Fixed

**CAR (Avis Budget Group) perpetually stuck in data center theme** — three prior fix attempts all failed because they relied on Haiku `_validate_theme_membership` to make the correct decision each run. Haiku is inconsistent: it sometimes decides CAR does belong in an IT/data-center theme (or fails with a caught exception), so the ticker is never reliably removed. The fix needed to be at the enforcement layer, not the decision layer.

### Solution: Persistent Theme Exclusion Table

New `mi_theme_exclusions` DB table stores (ticker, theme_name) pairs that are permanently banned from re-entering that theme, regardless of RS score or Haiku decisions.

**Enforcement is two-layer:**
1. `_rescore_existing_theme`: strips excluded tickers BEFORE pruning and BEFORE Haiku validation. Excluded tickers simply never reach the validation step.
2. `_assign_uncovered_to_themes`: skips excluded tickers when Claude tries to re-assign uncovered stocks to existing themes. Prevents re-entry via the discovery path.

**Automatic persistence:** When `_validate_theme_membership` successfully removes a ticker, it now writes to `mi_theme_exclusions` via `add_theme_exclusion()`. This means future runs don't depend on Haiku making the same decision again.

**User command:** "exclude CAR from [theme name]" → immediate DB insert, no engine run needed. Next theme engine run strips it. "list exclusions" shows all active bans. "remove exclusion CAR from [theme]" undoes it.

### Files Changed
- `agents/market_intelligence/db.py` — added `mi_theme_exclusions` table (CREATE TABLE + index in `initialize_schema`), plus `add_theme_exclusion`, `get_all_theme_exclusions`, `remove_theme_exclusion`, `list_theme_exclusions` functions
- `agents/market_intelligence/theme_engine.py` — updated imports; `_validate_theme_membership` now persists removals to DB; `_rescore_existing_theme` accepts `theme_exclusions` kwarg and strips excluded tickers first; `_assign_uncovered_to_themes` accepts `theme_exclusions` kwarg and blocks excluded assignments; `run_theme_engine` loads exclusions once via `get_all_theme_exclusions()` and passes to both functions
- `agents/market_intelligence/agent.py` — added imports for exclusion functions; new route in `execute_task` for "exclude"/"ban from theme"/"list exclusions" keywords; new `_handle_theme_exclusion` handler
- `CLAUDE.md` — this file

### Key Design Decision
The fix is enforcement, not persuasion. We don't ask Haiku again — we don't let the ticker reach Haiku at all. The exclusion is stored at the DB layer and applied at the top of `_rescore_existing_theme` before any scoring logic runs. This is the only approach that is robust against Haiku inconsistency, network failures, or edge cases in description parsing.

## Changes Made 2026-04-10

### Features Added

**1. Advisor Strategy — Opus consultation for hard theme clustering decisions**

`_discover_new_themes` and `_assign_uncovered_to_themes` now use a multi-turn tool-use loop with two tools: the output tool (same as before) + `consult_advisor` (new). Sonnet decides when to escalate. If confident → calls `report_themes` directly. If genuinely uncertain → calls `consult_advisor`, Opus returns a decisive verdict, Sonnet continues.

- `_ADVISOR_TOOL` definition + `_call_advisor(question, context, caller)` helper in `theme_engine.py`
- Both functions switched from `tool_choice={"type": "tool", "name": ...}` (forced single call) to `tool_choice={"type": "auto"}` with a loop
- `_MAX_ADVISOR_CALLS = 3` per function — hard cap on Opus spend
- Advisor failures return a graceful fallback string — Sonnet is never blocked
- Self-assessment checklist added to both prompts: concrete conditions that should trigger advisor call (borderline cluster, 2-stock uncertainty, multi-theme fit, vague thesis)

**2. Audit Log — critical engine events queryable from Telegram**

New `mi_audit_log` DB table captures: `advisor_call`, `theme_discovered`, `theme_retired`, `stage_change`, `theme_excluded`. No SSH needed, persists across restarts.

- `log_audit_event(event_type, summary, detail)` in `db.py` — never raises
- `get_audit_log(limit, event_type, since_hours)` in `db.py`
- Written from: `_call_advisor` (question + verdict), `add_theme_exclusion` (auto + manual), `run_theme_engine` (discoveries + retirements + stage changes)
- New Telegram commands via `_handle_audit_log`: "audit log", "advisor log", "show logs 7d", "show logs [type]"

**3. Full decision logging in theme engine**

Both advisor loops log:
- "Sonnet went direct (no advisor needed)" when skipped — confirms it's calibrated, not broken
- Full question + 200-char context snippet on each advisor call
- Full Opus verdict (up to 300 chars)
- "advisor call limit reached" with the question that hit the cap

**4. Help command updated**

`_handle_help` in `channels/telegram.py` now includes Theme Management and Audit & Diagnostics sections with all new commands.

### Files Changed
- `agents/market_intelligence/theme_engine.py` — `_ADVISOR_TOOL`, `_call_advisor`, multi-turn loops in `_discover_new_themes` + `_assign_uncovered_to_themes`, self-assessment checklist in prompts, full decision logging, audit log writes for discoveries/retirements/stage changes
- `agents/market_intelligence/db.py` — `mi_audit_log` table in `initialize_schema`, `log_audit_event`, `get_audit_log` functions; `add_theme_exclusion` now also writes to audit log
- `agents/market_intelligence/agent.py` — `get_audit_log` import, "audit log"/"advisor log"/"show logs" route, `_handle_audit_log` handler
- `channels/telegram.py` — updated `_handle_help` with Theme Management + Audit & Diagnostics sections
- `README.md` — theme engine section updated with all new features, Audit Log section added, security model updated
- `CLAUDE.md` — this file

### Advisor Strategy — Key Architecture Notes
- Both functions use `tool_choice="auto"` not forced tool choice — Sonnet decides when to escalate
- The self-assessment checklist in the prompt gives Sonnet concrete criteria vs. vague "use sparingly" instructions
- `_call_advisor` takes a `caller` param ("discovery" or "assignment") for audit log attribution
- Loop exits when the output tool is called OR when no tool_use blocks in response (graceful fallback)
- Each advisor call writes to `mi_audit_log` — queryable from Telegram with "advisor log"

## Changes Made 2026-04-10 (second session)

### Features Added

**1. Industry-relative RS — two-layer context on every single-ticker query**

Every RS/fundamentals/research query on a single ticker now appends an *RS context* section:
- **Layer 1 (Theme RS)**: If the ticker is in an active theme, shows its rank within that theme's constituents by RS score (e.g. "#3 of 12 in AI Infrastructure")
- **Layer 2 (Industry RS)**: GICS industry-level percentile rank among all same-industry stocks with cached sector data (e.g. "Biotechnology → 71st pct (#95 of 340 tracked)")
- Falls back to sector-level if industry bucket has < 10 peers
- Suppresses industry line if theme signal is available and industry is too coarse (< 30 peers)

**Data pipeline:**
- `mi_ticker_overrides` gained `sector` and `industry` columns (ALTER TABLE migration)
- Nightly RS engine now enriches top 300 leaders: fetches sectors from yfinance for any not yet cached, updates `mi_ticker_overrides` (persistent) and `mi_stock_scores.sector` (for screener/leaders queries). Only missing tickers fetched — near-zero cost on subsequent runs.
- Single-ticker queries also fetch+cache sector on-demand from yfinance if not already in `mi_ticker_overrides`

**2. EP Diagnostic handler — "why not EP ARAI?"**

New `_handle_ep_diagnostic(ticker, request)` runs the actual filter checks in sequence and stops at the first failure:
1. Price floor ($5 minimum) — immediate skip for sub-$5 stocks
2. Extension filter (already up ≥50% in prior 5 days)
3. EP cooldown (prior alert within 60 days)
4. RS vs regime threshold (informational)
5. Gap size check (inferred from recent closes)

Also fetches Perplexity news to include what actually happened with the stock. Returns a specific answer, not a list of generic possibilities.

Example: "why not EP ARAI?" → `❌ Price filter: $0.67 < $5 minimum` + Perplexity summary of the patent catalyst.

Routing triggers: "why not ep", "why no ep", "why wasn't", "not flagged", "not an ep", "missed ep", "why didn't".

**3. News on research queries**

"research MRNA", "look up NVDA", "analyze COIN" now fetch a Perplexity news summary (recent catalyst, business developments) in parallel with RS + fundamentals. Appended as *Recent news* section. Only fires for explicit research/lookup queries — not for RS-only or fundamentals-only queries.

**4. Fixed "research [ticker]" routing**

Was routing to non-existent research agent → error. Now routes to market agent `_handle_single_score` which returns RS + fundamentals + RS context + news.

### Files Changed
- `agents/market_intelligence/db.py` — sector/industry columns in `mi_ticker_overrides` (migration), `upsert_ticker_sectors_batch`, `get_ticker_sector`, `get_sector_rs_rank`
- `agents/market_intelligence/rs_engine.py` — `_enrich_sectors()` helper, called at end of `run_rs_engine()` for top 300 leaders
- `agents/market_intelligence/agent.py` — imports `search_news_perplexity` + EP filter constants; "research/look up/analyze" routing to `_handle_single_score`; "why not EP" routing to `_handle_ep_diagnostic`; `_handle_single_score` fetches sector + news in parallel; `_handle_ep_diagnostic` new method

### Key Design Decisions
- **Industry RS uses GICS Industry level** (e.g. "Biotechnology"), not Sector ("Healthcare") — right granularity for momentum work. Falls back to Sector if industry bucket < 10.
- **Theme RS is Layer 1** because it's the tightest, most relevant peer group for a momentum trader. Industry RS is always shown as Layer 2.
- **EP diagnostic stops at first failure** — the goal is root cause, not a checklist. Once the price filter fails, nothing else matters.
- **News only on research queries** — not added to RS-only or fundamentals-only queries to avoid bloating those responses.

## Changes Made 2026-04-11

### Bugs Fixed

**1. VIX one-day stale in yfinance fallback** (`collector.py`): Polygon `I:VIX` always fails on Starter plan (requires Indices add-on), so the fallback to yfinance `^VIX` always runs. yfinance `end` is exclusive; passing `to_date="2026-04-09"` returns data only through April 8. Nightly run at 4:30 PM was capturing yesterday's close, not today's. Fix: add 1 day to `to_date` for the yfinance call.

**2. Industry RS missing for on-demand scored tickers** (`db.py`, `agent.py`): `get_sector_rs_rank` JOIN'd `mi_stock_scores` to find the ticker's own RS score. On-demand scored tickers (`score_single_ticker`) are not written to `mi_stock_scores` — `ticker_rs = composites.get(ticker_up)` returned None and bailed. Fix: added `ticker_rs` parameter to `get_sector_rs_rank`; caller passes the already-known RS composite, skipping the DB lookup.

**3. "industry" keyword hijacking single-ticker queries** (`agent.py`): `"industry"` in execute_task routing unconditionally triggered the theme handler before RS/single-score. "What about RS vs its industry for MRNA?" → theme scorecard instead of per-ticker context. Fix: only route to theme if no ticker is found alongside "industry". Also added system prompt instruction for Apollo to always include the ticker explicitly when asking about industry RS.

**4. NULL description rows overwriting TICKER_DESC baseline** (`db.py`): Root cause of TSEM moving from semiconductor theme to oil & gas. `upsert_ticker_sectors_batch` creates rows in `mi_ticker_overrides` with `description=NULL` (sector/industry only). `get_ticker_overrides()` was fetching ALL rows, so `apply_overrides({"TSEM": None})` overwrote the correct static description with None. Next run, `_ensure_descriptions` saw None → fetched fresh → bad description persisted → Haiku removed TSEM from semi → assigned to oil & gas. Fix: `get_ticker_overrides` now filters `WHERE description IS NOT NULL AND description != ''`.

**5. Validation removals auto-persisted as permanent exclusions** (`theme_engine.py`): `_validate_theme_membership` was writing removed tickers to `mi_theme_exclusions`, which blocked re-entry even after fixing the underlying description. The exclusion table is for user-directed bans only. Validation removals are already self-healing (runs Mon/Wed/Fri). Fix: removed the `add_theme_exclusion` call from `_validate_theme_membership`.

**6. EP scan log wired into morning briefing** (`briefing.py`): `_format_ep_section` already had `scan_log` param but `send_morning_briefing` was not fetching it. Fixed: `get_ep_scan_log(today_str)` added to `asyncio.gather`, passed through `_format_morning_briefing` → `_format_ep_section`. Morning EP section now shows candidate count and near-miss line.

**7. Apollo reformatting single-ticker output** (`core/context.py`): Apollo was prepending "Here's what the system has on X:" and rewriting the market agent data as prose. Tightened system prompt to explicitly ban preambles and require starting directly with the verbatim data block.

### Files Changed
- `agents/market_intelligence/collector.py` — VIX yfinance end+1 fix
- `agents/market_intelligence/db.py` — `get_sector_rs_rank` accepts `ticker_rs` param; `get_ticker_overrides` filters NULL descriptions
- `agents/market_intelligence/agent.py` — pass `ticker_rs` to `get_sector_rs_rank`; "industry" routing fix; "industry RS" system prompt instruction
- `agents/market_intelligence/theme_engine.py` — removed auto-persist of validation removals to exclusion table
- `agents/market_intelligence/briefing.py` — fetch + wire `ep_scan_log` into morning briefing
- `core/context.py` — industry RS routing instruction; ban on single-ticker preambles

### Deploy Notes
- market-agent only: collector.py, db.py, agent.py, theme_engine.py, briefing.py

## Changes Made 2026-04-14

### Bugs Fixed

**1. `/rules` Telegram command silently failing** (`channels/telegram.py`): Telegram Markdown v1 rejects backtick-wrapped underscores and escaped underscores inside italic spans (`_text_`). Both patterns caused silent HTTP 400 errors with no user-visible output. Fixed: removed backtick formatting from `stop_too_wide`, `orb_no_breakout`, `effective_stop` identifiers; changed `_Full doc: EP\_TRADING\_RULES.md_` to plain `Full doc: EP_TRADING_RULES.md`; replaced `≥`/`≤`/`×`/`⅓`/`→` with ASCII equivalents.

**2. Theme Transitions: flat list replaced with Improving/Deteriorating groups** (`state_alerts.py`): Added `_stage_rank` dict (`Fading=0, Nascent=1, Mainstream=2, Accelerating=3`). Alerts with increasing rank go under `_Improving_` header; decreasing rank under `_Deteriorating_` header.

**3. Theme scorecard stage grouping regression** (`briefing.py`): `_format_theme_scorecard` was outputting a flat list. The stage grouping fix (Accelerating/Mainstream/Nascent headers) had only landed in `agent.py` in April 9. Re-applied stage group headers to `_format_theme_scorecard` in briefing.py to match.

**4. Gold miners absorbed into uranium theme** (`theme_engine.py`): Claude clusters by price momentum without commodity specificity — SSRM, ORLA (gold/silver miners) were assigned to the uranium nuclear theme. Added `_strip_commodity_contradictions(themes)` with `COMMODITY_RULES` keyword pairs; runs after merge, strips any theme member whose description contains a contradicting commodity keyword.

**5. Photonics theme absorbed by new large cluster** (`theme_engine.py`): `overlap_ratio = intersection / smaller_size` = 1.0 for a 3-stock subset fully inside a 25-stock cluster → small theme absorbed. Fixed `_merge_overlapping_themes` with `protected_names: set[str]` parameter: existing themes are protected; new clusters have the overlap stripped instead of absorbing the existing theme.

### Features Added

**6. Phase 1 — Name inheritance on rediscovery** (`theme_engine.py`): After `_discover_new_themes`, each new theme now calls `_get_theme_history` (which has Jaccard >= 0.4 fallback). If a retired theme matches by ticker overlap, the old name is substituted. Fixes "Compound Semi & Specialty Photonic Materials" → "Independent Foundry" drift when theme briefly retires.

**7. Phase 2 — Fat theme splitting with Sonnet + Opus advisor** (`theme_engine.py`): Themes with >20 stocks (excluding Fading) are candidates for a sub-theme split. Sonnet analyzes the stock list with `propose_split` tool; uncertain cases escalate to Opus advisor (`consult_advisor` tool). Split produces a focused sub-theme of 3–8 stocks with a more specific thesis. `sub_theme_parents` dict in `_merge_overlapping_themes` protects sub-themes from re-absorption by their parent. All split decisions logged to `mi_audit_log`.

**8. `parent_theme` column in `mi_themes`** (`db.py`): New `ALTER TABLE ... ADD COLUMN IF NOT EXISTS parent_theme TEXT` migration. `_save_themes` writes parent relationship; `get_today_themes` returns it. Nightly run loads prior sub-theme relationships to protect them in next run.

**9. CLAUDE.md EP scan stop time corrected**: Was `9:35 AM | EP scan stops`. Actual scheduler: `hour='7-9', minute='*/5'` (runs through 9:55 AM), stop cron at `hour='10', minute='0'`. Split into `9:35 AM | Stop refresh for Day 2+ positions` and `10:00 AM | EP scan stops`.

### Files Changed
- `channels/telegram.py` — `/rules` Markdown v1 formatting fixes
- `agents/market_intelligence/state_alerts.py` — theme transitions Improving/Deteriorating split
- `agents/market_intelligence/briefing.py` — stage group headers in `_format_theme_scorecard`
- `agents/market_intelligence/theme_engine.py` — `_strip_commodity_contradictions`; `protected_names` + `sub_theme_parents` in `_merge_overlapping_themes`; Phase 1 name inheritance; Phase 2 fat-theme split (`_split_fat_theme`, `MAX_THEME_STOCKS=20`); `_save_themes` parent_theme write
- `agents/market_intelligence/db.py` — `parent_theme` column migration

### Deploy Notes
- market-agent + telegram only: state_alerts.py, briefing.py, theme_engine.py, db.py, telegram.py
- monitor tonight's 4:30 PM ET nightly run for `[name inheritance]` log lines
- watch for fat-theme split proposals in `mi_audit_log` (query: "audit log" in Telegram)
- Both containers: core/context.py (orchestrator system prompt)

## Changes Made 2026-04-14 (second session)

### Features Added / Bugs Fixed

**1. Real-time ORB entry via Alpaca bar WebSocket** (`broker/bar_stream.py` NEW, `scheduler.py`, `agent.py`):
Root cause of missed ORB entries: standalone ORB monitor cron at 9:32 AM ran before the 9:35 first-complete-bar EP scan. Pre-market HIGH alerts had no path to ORB entry.

Architecture fix:
- New `broker/bar_stream.py`: wraps `alpaca-py` `StockDataStream` (separate from `TradingStream`). `subscribe_ep_candidate(ticker)` registers a handler; `_handle_bar` fires on first bar close (9:30 ET), calls `process_new_alerts_live()` immediately.
- `_ep_scan_job` (scheduler): pre-market HIGH alerts → `bar_stream.subscribe_ep_candidate()`; post-open new HIGHs (9:31+ scan) → `await _orb_monitor_job()` inline.
- Removed standalone ORB cron (9:32). Added dedicated 9:31 EP scan (`ep_scan_open`). Added 9:35 `bar_stream_cleanup` cron (`unsubscribe_all()`).
- `agent.py` startup: `asyncio.create_task(start_bar_stream())` alongside trade stream.

Result: EP fires at 9:25 AM → ticker subscribed to bar stream → bar closes 9:30:59 → order placed at 9:31:00.

**2. M&A hard filter** (`ep_detector.py`): Added `"mna"` as 4th Claude catalyst enum. M&A/tender offer/going-private → classified as `"mna"` → `is_mna = True` → hard skip before scoring. Expanded `_MNA_KEYWORDS` list: "definitive agreement", "tender offer", "going private", "taken private", "strategic transaction", "merger agreement", "to be acquired". Fixes AVNS-type buyouts slipping through as `"routine"` + big gap.

**3. 11 AM re-entry cutoff** (`broker/order_manager.py`): `attempt_day1_reentry` now checks `datetime.now(_ET).hour >= 11` before placing a new limit buy. After 11 AM, closes the trade instead of re-entering.

**4. Open intensity metric (not projected volume)** (`ep_detector.py`, `briefing.py`): Post-open RVOL extrapolated to full day is misleading (TVTX: 78x intensity but ~4x actual RVOL). Renamed to "open intensity": `intensity = raw_rvol * (390 / minutes_since_open)`. Used in `_score_ep()` as `vol_signal` when available (post-open scans). Briefing shows `RVOL: 2.0x (intensity 78x)`. Label change is intentionally honest — intensity ≠ projected daily volume.

**5. ADV median fix for non-universe stocks** (`ep_detector.py`): `_compute_adv_from_polygon` was using `mean(volumes)`. RS engine uses `PERCENTILE_CONT(0.5)` (median). Fixed to `statistics.median(volumes)` for consistency.

### Key Investigation (TVTX)
Server logs confirmed TVTX RVOL accumulated gradually: 1.83x at 9:25, 1.88x at 9:30, 1.97x at 9:35, 2.01x at 9:40. First crossed threshold AT open, not pre-market. Bar stream would not have helped TVTX (wasn't a pre-market HIGH). New bar stream architecture helps stocks that ARE confirmed pre-market and need real-time ORB order placement.

### Server Path Correction
CLAUDE.md had wrong path `/home/Apollo/apollo_the_wise/` (capital A). Actual path: `/home/apollo/apollo_the_wise/` (lowercase). SSH user: `apollo`, not `root`.

### Files Changed
- `agents/market_intelligence/broker/bar_stream.py` — NEW: StockDataStream wrapper, subscribe/handle/cleanup
- `agents/market_intelligence/scheduler.py` — removed ORB cron, added 9:31 scan + 9:35 cleanup, pre/post-open EP handling
- `agents/market_intelligence/agent.py` — start_bar_stream in startup, stop_bar_stream in shutdown
- `agents/market_intelligence/broker/order_manager.py` — 11 AM re-entry cutoff
- `agents/market_intelligence/ep_detector.py` — mna enum + hard filter, open intensity metric, ADV median fix
- `agents/market_intelligence/briefing.py` — intensity display in EP alert

### Deploy Notes
- market-agent only: broker/bar_stream.py, scheduler.py, agent.py, broker/order_manager.py, ep_detector.py, briefing.py

## Changes Made 2026-04-14 (third session)

### Bugs Fixed / Features Added

**1. 9:31 ORB fallback for pre-market HIGHs** (`scheduler.py`):
The 9:31 `ep_scan_open` job only called `_orb_monitor_job()` when NEW post-open HIGHs were detected. Pre-market HIGHs (already in `mi_ep_alerts`, in `already_alerted` set) were skipped even if the bar stream missed them. Fixed: when `now_et.minute == 31` and no post-open new HIGHs detected, always call `_orb_monitor_job()` as a fallback. `process_new_alerts_live` checks `mi_live_trades` for existing entries → safe, idempotent.

**2. Bar stream reconnect re-subscription** (`broker/bar_stream.py`):
On reconnect after WebSocket drop, server-side subscriptions are lost. Added explicit `subscribe_bars` re-call for all tickers in `_subscribed` on each retry. Also added warning log when stream dies with active subscriptions so production logs make the failure visible.

**3. Scoring dead zone eliminated** (`ep_detector.py`):
10–14.9% gap + `game_changer` catalyst scored ~40–48pts (below MODERATE threshold 50) — a real EP like BE at 13.4% was completely invisible until it crossed 15%. Root cause: conviction floor only kicked in at `gap >= 15%`. Fix: added new floor tier `gap >= 10% + game_changer → floor 60 (MODERATE)`. Impact by regime:
- Bull + Gemini: 60 × 1.2 × 1.2 = 86.4 → HIGH ✓
- Bull only: 60 × 1.2 = 72 → HIGH ✓
- Choppy/Correcting/Crisis + Gemini: 60 × 1.2 = 72 → MODERATE (morning briefing) ✓
- Crisis no Gemini: 60 → MODERATE ✓
Previously these stocks were invisible (scored 0-48 → skip).

**4. Critical finding: paper trading has never placed an order** (investigation only, no fix needed):
Queried `mi_live_trades` — only 2 records, both `skipped`:
- TH (2026-04-01): HIGH 96pts, 35% gap → `no_orb_bar` (first bar unavailable on IEX feed — one-time issue)
- EEIQ (2026-03-30): HIGH 96pts, 54% gap → `adv_too_low ($70,931)` — correct filter, EEIQ had $70K ADV
The RVOL pre-market bug (from the same session) explains why most pre-market EPs like BE never reached `mi_live_trades` at all — they were filtered before scoring. After fixes from session 2 + 3, the full ORB entry path should finally execute.

### Files Changed
- `agents/market_intelligence/ep_detector.py` — new conviction floor tier: `gap >= 10% + game_changer → floor 60`
- `agents/market_intelligence/scheduler.py` — 9:31 ORB fallback always fires when `now_et.minute == 31`
- `agents/market_intelligence/broker/bar_stream.py` — reconnect re-subscription + active-subscription warning log

### Deploy Notes
- market-agent only: ep_detector.py, scheduler.py, broker/bar_stream.py

## Changes Made 2026-04-14 (fourth session)

### Bugs Fixed / Features Added

**1. Structural ORB entry rule enforcement — single source of truth**

Two code paths were implementing the same ORB stop-width check independently:
- EOD sim (`engine.py` `_simulate_day1`): `orb_range > 1.5 * atr_14` (dollar-based)
- Live path (`order_manager.py` `prepare_orb_order`): `orb_range > 1.5 * atr_14` (dollar-based)

Even though they matched after the previous session's fix, having two inline implementations means future edits to one won't propagate to the other — divergence is a matter of time.

Fix: extracted `validate_orb_entry(orb_high, orb_low, atr_14) -> (bool, skip_reason)` to `backtester/filters.py`. Both paths now import and call this single function. Divergence is structurally impossible.

Also cleaned up: removed dead `atr_pct` parameter from `_simulate_day1` and its call site in `simulate_trade`.

**2. Trade query routing fix**

"show filtered trades", "skipped trades", "all trades", "ep trades" were falling through to the finance agent (not configured). Added these keywords to the `_handle_trades_query` routing block in `agent.py`.

**3. TVTX verdict**

TVTX today: ORB range $1.28, 1.5x ATR = $2.62. Passes `validate_orb_entry`. Both EOD sim (confirmed traded) and live Alpaca path (after RVOL bug fix + structural fix) would enter this trade.

### Files Changed
- `agents/market_intelligence/backtester/filters.py` — new `validate_orb_entry` function
- `agents/market_intelligence/backtester/engine.py` — `_simulate_day1` calls `validate_orb_entry`; dead `atr_pct` param removed
- `agents/market_intelligence/broker/order_manager.py` — `prepare_orb_order` calls `validate_orb_entry`
- `agents/market_intelligence/agent.py` — added trade routing keywords

### Deploy Notes
- market-agent only — deployed 2026-04-15
