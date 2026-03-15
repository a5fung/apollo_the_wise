#!/usr/bin/env bash
# ============================================================
# Apollo Assistant — Start
# Run from the project root: bash start.sh
# ============================================================

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

log()  { echo -e "${GREEN}✔${NC} $*"; }
info() { echo -e "${CYAN}→${NC} $*"; }
err()  { echo -e "${RED}✘ $*${NC}"; exit 1; }

[[ -f "main.py" ]] || err "Run this script from the Apollo project root (the folder containing main.py)"
[[ -f ".env" ]]    || err ".env not found — run bash setup.sh first"

docker info >/dev/null 2>&1 || err "Docker is not running. Open Docker Desktop and try again."

info "Starting Postgres and Redis..."
(cd docker && docker compose --env-file ../.env up -d postgres redis)

info "Waiting for containers..."
for i in {1..20}; do
    STATUS=$(cd docker && docker compose --env-file ../.env ps --format json 2>/dev/null | python -c "
import sys, json
lines = sys.stdin.read().strip().splitlines()
statuses = [json.loads(l).get('Health','') for l in lines if l]
all_healthy = all(s == 'healthy' for s in statuses if s)
print('ok' if all_healthy and statuses else 'wait')
" 2>/dev/null || echo "wait")
    [[ "$STATUS" == "ok" ]] && break
    if [[ $i -eq 20 ]]; then
        err "Containers didn't become healthy. Run: cd docker && docker compose ps"
    fi
    sleep 2
done
log "Postgres and Redis ready"

# Track sub-agent PIDs for clean shutdown on Ctrl+C
AGENT_PIDS=()

cleanup() {
    echo ""
    info "Shutting down agents..."
    for pid in "${AGENT_PIDS[@]}"; do
        kill "$pid" 2>/dev/null || true
    done
    wait 2>/dev/null || true
    info "Done."
}
trap cleanup EXIT INT TERM

mkdir -p logs

info "Starting Research agent (port 8003)..."
python -m uvicorn agents.research.agent:app --host 0.0.0.0 --port 8003 \
    --log-level warning >> logs/research.log 2>&1 &
AGENT_PIDS+=($!)

info "Starting Market Intelligence agent (port 8006)..."
python -m uvicorn agents.market_intelligence.agent:app --host 0.0.0.0 --port 8006 \
    --log-level warning >> logs/market.log 2>&1 &
AGENT_PIDS+=($!)

# Give agents a moment to bind their ports
sleep 2
log "Agents started (logs in logs/)"

echo ""
echo -e "${GREEN}${BOLD}Starting Apollo...${NC} (Ctrl+C to stop everything)"
echo ""

python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
