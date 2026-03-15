# Apollo Assistant

A Telegram-based personal assistant that acts as a "chief of staff" — it plans, reasons, and delegates to specialized sub-agents. Built around market intelligence as its core capability, with calendar, research, travel, and browser automation alongside.

---

## What Apollo Does

**Talk to it naturally in Telegram. It figures out the rest.**

### Market Intelligence (primary)

Apollo runs a full market intelligence stack focused on momentum/EP trading methodology (Qullamaggie, Pradeep Bonde, Marios Stamatoudis).

| Ask Apollo | What happens |
|---|---|
| "Send evening briefing" | Regime + RS leaders + active themes + MA pullbacks |
| "Send morning briefing" | EP alerts recap + regime context (pre-market) |
| "Any EPs today?" | EP alerts with MAGNA53 score, catalyst quality, Gemini cross-validation |
| "What's the market regime?" | Bull/Choppy/Correcting/Crisis + VIX + breadth + MA context |
| "Top RS stocks" | Momentum leaders ranked by 1M/3M/6M composite RS |
| "What themes are active?" | Persistent themes with lifecycle stage + constituent stocks |
| "Optical stocks near 20MA?" | MA pullback scan filtered to a theme's tickers |
| "Score AXTI" | On-demand RS rank for any ticker (1 API call, exact percentile) |
| "AXTI is working, track it" | Apollo asks questions, adds to tracking + seeds theme |
| Any stock/investment question | Apollo consults market agent before answering |

**Two daily briefings (automatic):**
- **5:00 PM PT (8 PM ET)** — Evening briefing: full EOD review package. Sent after close when you sit down to review charts.
- **6:00 AM PT (9 AM ET)** — Morning briefing: EP recap + regime context, 30 min before open.
- HIGH EP alerts fire in real-time during pre-market scan (4–6:30 AM PT). No waiting for briefing.

### General capabilities

- **Finance** — IBKR portfolio/P&L (read-only), TradingView price alerts pushed to Telegram
- **Calendar** — Google Calendar + iCloud events, create/reschedule/cancel (with confirmation)
- **Research** — Web search with synthesized answers, article summarization
- **Travel** — Flight/hotel research, trip itineraries, Amex Platinum perks optimizer
- **Browser** — General website automation via Playwright

---

## Architecture

```
User (Telegram)
      │
      ▼
Apollo Orchestrator (port 8000)     ← Claude Sonnet — plans, reasons, delegates
      │ internal REST API
      ▼
┌─────────────────────────────────────────────────────────────────┐
│  Sub-agents (each isolated in Docker)                           │
│                                                                 │
│  Market Intelligence :8006    Finance Agent :8001               │
│  RS engine, EP detection,     IBKR read-only,                   │
│  theme clustering, regime     TradingView webhooks              │
│                                                                 │
│  Calendar Agent :8002         Research Agent :8003              │
│  Google + iCloud CalDAV       Tavily web search                 │
│                                                                 │
│  Travel Agent :8005           Browser Agent :8004               │
│  Flights, hotels,             Playwright automation             │
│  Amex Platinum perks                                            │
└─────────────────────────────────────────────────────────────────┘
      │
      ▼
PostgreSQL (pgvector)  +  Redis
Persistent memory          Caching + confirmations
```

---

## Market Intelligence — How It Works

### RS Scoring

Momentum ranking in the style of Marios Stamatoudis (not IBD RS Rating).

- **Timeframes:** 1M / 3M / 6M price returns
- **Composite:** 40% × 1M rank + 30% × 3M rank + 30% × 6M rank
- **Score:** 0–100 percentile rank within the scored universe
- **Universe:** 148 curated liquid US stocks + all actively tracked stocks
- **On-demand:** "Score AXTI" → 1 Polygon call, ranks against today's stored distribution

### RS Persistence

Once a stock shows RS leadership it stays tracked nightly. Top 50 RS leaders each run are added to `mi_tracked_stocks`. A stock is deactivated after 7 consecutive weak days (RS composite < 40).

### Theme Engine

Bottom-up from price action (Marios Stamatoudis methodology). Themes emerge from which stocks move together — not top-down hypothesis.

- Existing themes are **re-scored daily** from current RS data (no redundant re-clustering)
- Claude clustering only runs on **uncovered RS leaders** (stocks not in any active theme)
- Lifecycle: 🌱 Nascent → ⚡ Accelerating → 📊 Mainstream → 🔻 Fading → Retired (after 5 fading days)
- Themes survive across days — persist until price action says otherwise

### EP Detection

MAGNA53 scoring (Pradeep Bonde / Kullamägi methodology).

- **Inputs:** Gap %, relative volume, catalyst quality (Claude), neglect factor, float, regime multiplier
- **HIGH (≥85):** Immediate Telegram alert during pre-market scan
- **MODERATE (≥65):** Shown in morning briefing
- **Gemini cross-validation:** When Claude + Gemini agree on catalyst → 1.2x confidence multiplier
- **Scan schedule:** 7:00–9:30 AM ET, every 5 minutes

### Market Regime

| Label | EP Threshold | Meaning |
|---|---|---|
| Bull | ≥70 | Standard criteria |
| Choppy | ≥80 | Raise your bar |
| Correcting | ≥85 | Exceptional setups only |
| Crisis | ≥90 | Very selective |

Signals: SPY/QQQ vs 50MA + 200MA, VIX, breadth (% stocks above 40MA), B/O:B/D ratio.

### Teaching Apollo

When you spot something the system isn't tracking:

1. Tell Apollo: *"AXTI is working — it's a photonics play"*
2. Apollo asks: which tickers? new theme or existing? one-line thesis?
3. Apollo calls `/teach` → tickers added to RS tracking + theme seeded
4. Offer to run data refresh → new tickers scored immediately

---

## Daily Schedule

| Time (ET) | Time (PT) | What |
|---|---|---|
| 4:30 PM | 1:30 PM | Data pull — RS engine + regime + themes (right after close) |
| 8:00 PM | 5:00 PM | Evening briefing → Telegram |
| 7:00 AM | 4:00 AM | EP scan starts; HIGH alerts fire in real-time |
| 9:00 AM | 6:00 AM | Morning briefing → Telegram |
| 9:35 AM | 6:35 AM | EP scan stops |

---

## Data Sources

| Source | Used For | Tier |
|---|---|---|
| Polygon.io | Price history, RS engine, EP gap data | Free (5 req/min) |
| yfinance | Company profile, sector, analyst ratings, news | Free |
| Tavily | EP catalyst news search, theme confirmation | Free/Pro |
| Anthropic | Orchestrator, catalyst classification, theme clustering | Pay-per-use |
| Gemini | EP catalyst cross-validation | Free (gemini-1.5-flash-8b) |
| Telegram | Bot delivery | Free |

---

## Project Structure

```
Apollo_Assistant/
├── main.py                          # Entry point
├── core/
│   ├── orchestrator.py              # Claude tool-use loop
│   ├── router.py                    # Tool definitions + sub-agent routing
│   ├── context.py                   # System prompt (market intelligence instructions)
│   ├── notifications.py             # Direct Telegram alerts (startup, job failures)
│   ├── memory.py                    # PostgreSQL + pgvector memory
│   └── confirmations.py             # YES/NO gate for irreversible actions
├── channels/
│   ├── telegram.py                  # Telegram bot + /help command
│   └── webhooks.py                  # FastAPI webhook receiver
├── agents/
│   └── market_intelligence/
│       ├── agent.py                 # FastAPI app on port 8006
│       ├── db.py                    # Schema + all DB queries
│       ├── collector.py             # Polygon + yfinance + Tavily data fetching
│       ├── rs_engine.py             # RS scoring + MA computation + single-ticker score
│       ├── ep_detector.py           # MAGNA53 EP scoring + Claude + Gemini
│       ├── regime.py                # Market regime engine
│       ├── briefing.py              # Evening + morning briefing formatters
│       ├── theme_engine.py          # Theme discovery + persistence + lifecycle
│       ├── scheduler.py             # APScheduler jobs (4:30pm data, 8pm evening, 9am morning)
│       ├── universe.py              # 148-stock curated universe
│       └── backtest_ep.py           # EP backtest against historical dates
├── docker/
│   ├── docker-compose.yml           # Local dev
│   ├── docker-compose.prod.yml      # Production (all services + Uptime Kuma)
│   ├── Dockerfile.orchestrator
│   └── Dockerfile.market            # Market Intelligence agent
├── shared/
│   ├── models.py                    # Pydantic models
│   ├── secrets.py                   # Secrets access
│   └── registry.py                  # Agent URL registry
├── integrations.yaml                # Agent URL config
├── start.sh                         # Start Apollo locally
└── start_market.sh                  # Start market agent locally
```

---

## Quick Start

See **`SETUP.md`** for the full setup guide.

```bash
# Terminal 1 — Apollo orchestrator + infrastructure
bash start.sh

# Terminal 2 — Market Intelligence Agent
bash start_market.sh

# Verify everything is up
# Send /agents in Telegram → all agents should show green
```

**Required `.env` keys:**
- `TELEGRAM_BOT_TOKEN` — from @BotFather
- `TELEGRAM_ALLOWED_USER_IDS` — your Telegram user ID
- `ANTHROPIC_API_KEY`
- `POLYGON_API_KEY`
- `GEMINI_API_KEY`
- `TAVILY_API_KEY`
- `POSTGRES_PASSWORD`, `REDIS_PASSWORD`, `INTERNAL_API_SECRET`

---

## Production Deploy

Target: Hetzner CX22 (~$6/mo), Docker Compose, Nginx + Let's Encrypt, Telegram webhooks.

```bash
docker compose -f docker/docker-compose.prod.yml up -d --build
```

Includes Uptime Kuma (self-hosted status dashboard) + Apollo self-reports startup health and scheduler failures directly to Telegram.

**Monthly cost:** ~$20–40 (server + APIs). Jumps to ~$50–70 with Polygon Starter.

See `docker/docker-compose.prod.yml` and the deployment notes in the project memory for the full checklist.

---

## Security Model

| Concern | Mitigation |
|---|---|
| Telegram access | Allowlist — only configured user IDs can interact |
| IBKR | Read-only API — no trade execution implemented |
| Irreversible actions | YES/NO confirmation gate before execution |
| Sub-agent isolation | Each container has only its own secrets |
| TradingView webhooks | Verified via shared secret header |
| Audit trail | Append-only `audit.log` — every action logged |
| Secrets | Env vars only, never in code or logs |

---

## Backlog / Upgrade Path

**Highest leverage:**
- **Polygon Starter ($29/mo)** → grouped daily endpoint → full US universe → real T2108 breadth → proper IBD-style RS (12M component, 8,000+ stocks)
- Full Pradeep Market Monitor once full universe is available

**Morning briefing enrichments (planned):**
- S&P/QQQ/NQ futures overnight move
- Economic calendar ("Fed decision 2 PM today", "CPI 8:30 AM")
- Major pre-market news via Tavily
- Earnings calendar for tracked stocks
