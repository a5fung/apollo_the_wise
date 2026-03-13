# Apollo Assistant

A fully autonomous personal assistant that acts as an orchestration layer — a "chief of staff" that delegates specialized tasks to isolated sub-agents. You interact via Telegram.

## Architecture

```
User (Telegram)
      ↓
Apollo Orchestrator          ← Claude Sonnet — plans, reasons, delegates
      ↓ internal REST API (FastAPI)
┌──────────────────────────────────────────────────────────────────┐
│  Sub-agents (each in own Docker container)                        │
│                                                                   │
│  Finance Agent    Calendar Agent   Research Agent                 │
│  (IBKR read-only, (Google + iCloud  (Tavily web search,          │
│  TradingView)      CalDAV)          summarization)               │
│                                                                   │
│  Browser Agent    Travel Agent                                    │
│  (Playwright)     (flights, hotels,                               │
│                    Amex Platinum                                   │
│                    perks optimizer)                               │
└──────────────────────────────────────────────────────────────────┘
```

## Quick Start (Phase 1)

### 1. Prerequisites

- Python 3.12+
- Docker + Docker Compose
- PostgreSQL with pgvector extension
- Redis

### 2. Setup

```bash
# Clone and enter the project
cd Apollo_Assistant

# Install dependencies
pip install -r requirements/base.txt

# Install Playwright browsers
playwright install chromium

# Copy and fill in your environment
cp .env.example .env
# Edit .env with your Telegram token, Anthropic API key, etc.
```

### 3. Configure credentials in `.env`

Required for Phase 1 (Core + Telegram):
- `TELEGRAM_BOT_TOKEN` — from [@BotFather](https://t.me/botfather)
- `TELEGRAM_ALLOWED_USER_IDS` — your Telegram user ID (find it from [@userinfobot](https://t.me/userinfobot))
- `ANTHROPIC_API_KEY` — from console.anthropic.com
- `POSTGRES_PASSWORD` — set a strong password
- `REDIS_PASSWORD` — set a strong password
- `INTERNAL_API_SECRET` — random secret for inter-service auth
- `TRADINGVIEW_WEBHOOK_SECRET` — random secret for TV webhooks

### 4. Start with Docker Compose

```bash
# From project root (docker-compose.yml reads ../.env)
cd docker
docker compose up -d

# Or without Docker (local dev):
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

### 5. Set Telegram webhook

Once running, register your webhook with Telegram:

```bash
# If running locally with ngrok:
ngrok http 8000
# Then set WEBHOOK_BASE_URL=https://your-ngrok-url.ngrok.io in .env

# Or curl directly:
curl "https://api.telegram.org/bot<YOUR_TOKEN>/setWebhook?url=https://your-domain.com/telegram/webhook"
```

### 6. Talk to Apollo

Open Telegram, find your bot, and say hello!

```
/start
What's on my calendar tomorrow?
Research the top S&P 500 ETFs
Show me my IBKR portfolio
Plan a 4-day trip to Tokyo in October
```

## Project Structure

```
apollo/
├── core/
│   ├── orchestrator.py    # Main Apollo brain (Claude tool-use loop)
│   ├── memory.py          # PostgreSQL + pgvector
│   ├── router.py          # Routes tasks to sub-agents
│   ├── confirmations.py   # Confirmation gate (YES/NO blocking)
│   └── context.py         # Context compression
├── channels/
│   ├── telegram.py        # Telegram bot (webhook mode)
│   └── webhooks.py        # FastAPI — Telegram + TradingView webhooks
├── agents/
│   ├── base.py            # Base sub-agent class
│   ├── finance/           # IBKR + TradingView
│   ├── calendar/          # Google + Apple CalDAV
│   ├── research/          # Tavily web search
│   ├── browser/           # General Playwright automation
│   └── travel/            # Flights + hotels + Amex Platinum perks
├── shared/
│   ├── secrets.py         # Centralized env var loading
│   ├── models.py          # Pydantic models
│   ├── audit.py           # Append-only audit log
│   └── registry.py        # integrations.yaml reader
├── docker/                # Dockerfiles + docker-compose files
├── infra/                 # Deployment scripts
├── requirements/          # Per-service requirements
├── tests/                 # Test scripts
├── integrations.yaml      # Active integrations registry
├── .env.example           # Environment variable template
└── main.py                # Entry point
```

## Adding New Integrations

Edit `integrations.yaml` to add providers — no core code changes needed:

```yaml
calendar:
  - provider: google
    account: work@company.com
    credentials_env: GOOGLE_CAL_WORK_TOKEN
    label: "Work Calendar"
    enabled: true
```

Then add the corresponding credential to `.env`.

## Security Model

| Concern | Mitigation |
|---|---|
| IBKR trading | Read-only API — no trading operations implemented |
| Sub-agent isolation | Each container has only its own secrets |
| Telegram access | Allowlist: only your user ID can send messages |
| TradingView webhooks | Verified via shared secret in query param |
| Irreversible actions | Confirmation gate: must reply YES before execution |
| Audit trail | Append-only `audit.log` — every action logged |
| Secrets | Only in env vars, never in code or logs |

## Tests

```bash
# Unit tests
pytest tests/test_confirmation_gate.py -v

# Integration tests (requires running services)
python tests/test_ibkr.py
python tests/test_tradingview_webhook.py
python tests/test_end_to_end.py
```

## Production Deploy

```bash
# Set VPS_HOST in env or edit infra/deploy.sh
./infra/deploy.sh
```

See `docker/docker-compose.prod.yml` for production configuration.

## Build Phases

- **Phase 1** ✅ — Core orchestrator, Telegram, PostgreSQL memory, confirmation gate
- **Phase 2** ✅ — Research agent (Tavily web search + summarization)
- **Phase 3** ✅ — Finance agent (IBKR read-only + TradingView webhooks + browser)
- **Phase 4** ✅ — Calendar agent (Google + Apple CalDAV)
- **Phase 5** ✅ — Travel agent + Amex Platinum perks + production deploy

Explicitly deferred: X/Twitter integration, stock trade execution
