"""Haiku 5.5 on the Arm B merge adjudicator (forced tool_choice + scratchpad-first schema) before the HAIKU pin moves.
READ-ONLY: reads the live board, calls adjudicate_merge_pair with log_spend=False, writes nothing. ~15 calls, < $0.01."""
import asyncio, json
import anthropic
from agents.market_intelligence.theme_engine import get_active_themes
from agents.market_intelligence.theme_merge_arm import adjudicate_merge_pair

PAIRS = [
    ("Auto Aftermarket, Powertrain & Preventive Maintenance Services", "Leisure, Hospitality & Travel Cyclical Recovery"),
    ("U.S. Homebuilders & Manufactured Housing", "Leisure, Hospitality & Travel Cyclical Recovery"),
    ("Online Consumer Marketplaces & Performance Marketing Platforms", "Leisure, Hospitality & Travel Cyclical Recovery"),
]
MODELS = [("claude-haiku-4-5-20251001", 1), ("claude-haiku-5-5", 3)]

async def main():
    themes = {t["name"]: t for t in await get_active_themes()}
    client = anthropic.AsyncAnthropic()
    for a, b in PAIRS:
        if a not in themes or b not in themes:
            print(json.dumps({"pair": [a, b], "skip": "not on the live board"})); continue
        for model, n in MODELS:
            for i in range(n):
                r = await adjudicate_merge_pair(themes[a], themes[b], client=client, model=model, log_spend=False)
                print(json.dumps({"pair": [a[:30], b[:30]], "model": model, "run": i,
                                  "verdict": r.get("verdict"), "reason": str(r.get("reason"))[:160]}), flush=True)

asyncio.run(main())
