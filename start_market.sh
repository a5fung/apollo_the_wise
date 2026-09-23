#!/usr/bin/env bash
# Start the Market Intelligence Agent on port 8006
# Run from the project root: bash start_market.sh

[[ -f ".env" ]] || { echo "Run from Apollo project root"; exit 1; }

echo "→ Starting Market Intelligence Agent on port 8006..."
python -m uvicorn agents.market_intelligence.agent:app \
    --host 0.0.0.0 \
    --port 8006 \
    --env-file .env
