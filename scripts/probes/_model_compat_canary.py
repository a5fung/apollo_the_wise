#!/usr/bin/env python3
"""Model-compat canary probe (2026-09-23): does the transport adapter (shared/llm_client) make
every production request shape work on every current model?

Run INSIDE the production container (ANTHROPIC_API_KEY is only reachable there):

    docker compose exec market-agent python scripts/probes/_model_compat_canary.py
    docker compose exec market-agent python scripts/probes/_model_compat_canary.py claude-opus-5-5

For each model it sends, THROUGH a factory client, the same four checks the nightly refresh's
pre-adoption canary sends (shared/llm_client.run_canary): a forced single tool, thinking
explicitly disabled, a plain call, and "any" over two tools. Prints PASS/FAIL per check per
model, with the adapter rewrites the model needed. Read-only: no DB writes, no trade state.
Cost: four ~100-token calls per model (~16 calls, well under a cent).
"""
from __future__ import annotations

import asyncio
import os
import sys

sys.path.insert(0, "/app")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from shared import llm_models  # noqa: E402
from shared.llm_client import (  # noqa: E402
    adopted_rewrites,
    make_async_anthropic,
    run_canary,
)

# The four models measured live on 2026-09-23. The three tier pins come from the registry;
# opus-5-5 is the release that broke the judges and is the one this probe exists to prove.
DEFAULT_MODELS = [
    "claude-opus-5-5",   # model-ok: the probe's subject — the release the resolver adopted 09-22
    llm_models.OPUS_PIN,
    llm_models.SONNET_5,
    llm_models.HAIKU_PIN,
]


async def main(models: list[str]) -> int:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("FAIL: ANTHROPIC_API_KEY is not set — run this inside the production container")
        return 2
    client = make_async_anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    failures = 0
    try:
        for model in models:
            results = await run_canary(client, model)
            ok = all(r.ok for r in results)
            failures += 0 if ok else 1
            print(f"\n{'PASS' if ok else 'FAIL'}  {model}  rewrites={sorted(adopted_rewrites(model)) or '-'}")
            for r in results:
                print(f"    {'PASS' if r.ok else 'FAIL'}  {r.check:<18} {r.detail}")
    finally:
        await client.close()
    print(f"\n{len(models) - failures}/{len(models)} models pass every production request shape")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main(sys.argv[1:] or DEFAULT_MODELS)))
