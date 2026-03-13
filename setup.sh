#!/usr/bin/env bash
# ============================================================
# Apollo Assistant — First-Time Setup
# Run once from the project root: bash setup.sh
# ============================================================

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

log()  { echo -e "${GREEN}✔${NC} $*"; }
info() { echo -e "${CYAN}→${NC} $*"; }
warn() { echo -e "${YELLOW}⚠${NC} $*"; }
err()  { echo -e "${RED}✘ $*${NC}"; exit 1; }
header() { echo -e "\n${BOLD}$*${NC}"; }

# ── Sanity checks ──────────────────────────────────────────────────────────────

header "Checking prerequisites..."

[[ -f "main.py" ]] || err "Run this script from the Apollo project root (the folder containing main.py)"

command -v python >/dev/null 2>&1 || err "Python not found. Install Python 3.12+ and try again."
PY_VER=$(python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
python -c "import sys; sys.exit(0 if sys.version_info >= (3,12) else 1)" \
    || err "Python 3.12+ required. You have $PY_VER."
log "Python $PY_VER"

command -v docker >/dev/null 2>&1 || err "Docker not found. Install Docker Desktop and make sure it's running."
docker info >/dev/null 2>&1 || err "Docker is installed but not running. Open Docker Desktop and try again."
log "Docker"

# ── .env setup ────────────────────────────────────────────────────────────────

header "Setting up environment..."

if [[ -f ".env" ]]; then
    warn ".env already exists — skipping credential prompts. Edit it manually if needed."
else
    cp .env.example .env
    log "Created .env from .env.example"

    echo ""
    info "You'll need the following (have them ready before continuing):"
    echo "  • Telegram bot token      — from @BotFather on Telegram"
    echo "  • Your Telegram user ID   — from @userinfobot on Telegram"
    echo "  • Anthropic API key       — from console.anthropic.com"
    echo "  • Tavily API key          — from tavily.com (free tier, optional)"
    echo ""
    read -rp "Press Enter to continue..."

    # Generate secrets automatically
    INTERNAL_SECRET=$(python -c "import secrets; print(secrets.token_hex(32))")
    TV_SECRET=$(python -c "import secrets; print(secrets.token_hex(32))")
    POSTGRES_PASS=$(python -c "import secrets; print(secrets.token_hex(16))")
    REDIS_PASS=$(python -c "import secrets; print(secrets.token_hex(16))")
    log "Generated random secrets"

    # Prompt for required values
    echo ""
    read -rp "Telegram bot token: " TG_TOKEN
    read -rp "Your Telegram user ID: " TG_USER_ID
    read -rp "Anthropic API key: " ANTHROPIC_KEY
    read -rp "Tavily API key (press Enter to skip): " TAVILY_KEY

    # Write values into .env using Python (avoids sed cross-platform issues)
    python - <<PYEOF
import re, pathlib

env = pathlib.Path(".env").read_text()

replacements = {
    "your_telegram_bot_token_here": "${TG_TOKEN}",
    "123456789": "${TG_USER_ID}",
    "your_anthropic_api_key_here": "${ANTHROPIC_KEY}",
    "change_me_strong_password": "${POSTGRES_PASS}",
    "change_me_redis_password": "${REDIS_PASS}",
    "change_me_internal_secret": "${INTERNAL_SECRET}",
    "change_me_tv_secret": "${TV_SECRET}",
}
if "${TAVILY_KEY}":
    replacements["your_tavily_api_key_here"] = "${TAVILY_KEY}"

for old, new in replacements.items():
    env = env.replace(old, new)

pathlib.Path(".env").write_text(env)
PYEOF

    log "Credentials written to .env"
fi

# ── Install Python dependencies ────────────────────────────────────────────────

header "Installing Python dependencies..."
pip install -r requirements/base.txt -q
log "Dependencies installed"

header "Installing Playwright browser..."
playwright install chromium
log "Chromium installed"

# ── Start infrastructure ───────────────────────────────────────────────────────

header "Starting Postgres and Redis..."
(cd docker && docker compose up -d postgres redis)

info "Waiting for containers to be healthy..."
for i in {1..30}; do
    STATUS=$(cd docker && docker compose ps --format json 2>/dev/null | python -c "
import sys, json
lines = sys.stdin.read().strip().splitlines()
statuses = [json.loads(l).get('Health','') for l in lines if l]
all_healthy = all(s == 'healthy' for s in statuses if s)
print('ok' if all_healthy and statuses else 'wait')
" 2>/dev/null || echo "wait")
    if [[ "$STATUS" == "ok" ]]; then
        log "Postgres and Redis are healthy"
        break
    fi
    if [[ $i -eq 30 ]]; then
        err "Containers didn't become healthy in time. Run: cd docker && docker compose ps"
    fi
    sleep 2
done

# ── Done ──────────────────────────────────────────────────────────────────────

echo ""
echo -e "${GREEN}${BOLD}Setup complete!${NC}"
echo ""
echo "Next steps:"
echo "  1. To expose Apollo to Telegram, set up ngrok (see SETUP.md Step 5)"
echo "  2. Start Apollo anytime with:  bash start.sh"
echo ""
