#!/usr/bin/env python3
"""Backfill mi_theme_ecosystems for the current ACTIVE themes (ADR 0032 Phase 1).

DRY-RUN BY DEFAULT — prints the proposed theme → E-code mapping without writing
anything. Pass --execute to persist (upsert + `theme_ecosystem_assigned` audit
rows). Already-mapped theme names are always skipped (re-mapping is a manual
operator action).

OPERATOR-GATED: runs POST-DEPLOY on the server (inside the market-agent
container, where the DB + ANTHROPIC_API_KEY env live), e.g.:

    docker exec -it apollo-market-agent \
        python scripts/backfill_theme_ecosystems.py                # dry-run
    docker exec -it apollo-market-agent \
        python scripts/backfill_theme_ecosystems.py --execute      # write

Options:
  --execute         write mappings (default: dry-run, prints only)
  --keyword-only    skip the Haiku call; deterministic keyword/exemplar
                    fallback only ($0, fully offline)
  --stale-after-days N   active-theme recency window (default 7,
                    matches get_active_themes)

Read-model only — no theme lifecycle rows are touched; no money path.
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

# Repo root on sys.path when invoked as `python scripts/backfill_theme_ecosystems.py`
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


async def _run(execute: bool, keyword_only: bool, stale_after_days: int) -> int:
    from agents.market_intelligence.db import get_active_themes
    from agents.market_intelligence.theme_ecosystems import (
        E_UNASSIGNED, ensure_theme_ecosystems,
    )

    themes = await get_active_themes(stale_after_days=stale_after_days)
    if not themes:
        print("No active themes found — nothing to backfill.")
        return 0

    results = await ensure_theme_ecosystems(
        themes,
        dry_run=not execute,
        use_llm=not keyword_only,
        # Backfill is a one-shot over the whole active set — lift the nightly
        # per-run Haiku cap so the initial ~65 themes all get the primary path.
        max_llm_calls=200,
    )
    if not results:
        print(f"All {len(themes)} active theme(s) already mapped — nothing to do.")
        return 0

    mode = "EXECUTE" if execute else "DRY-RUN"
    print(f"[{mode}] {len(results)} theme(s) assigned (of {len(themes)} active):\n")
    width = min(60, max(len(r["theme_name"]) for r in results))
    for r in results:
        detail = f"  {r['detail']}" if r.get("detail") else ""
        print(f"  {r['theme_name'][:60]:<{width}}  →  {r['e_code']:<13} "
              f"[{r['method']}]{detail}")

    by_code: dict[str, int] = {}
    for r in results:
        by_code[r["e_code"]] = by_code.get(r["e_code"], 0) + 1
    print("\nBy ecosystem: " + " · ".join(f"{c}={n}" for c, n in sorted(by_code.items())))
    n_un = by_code.get(E_UNASSIGNED, 0)
    if n_un:
        print(f"\n{n_un} theme(s) landed in {E_UNASSIGNED} — they render in the "
              f"unmapped section of /themes (the Phase-3 discovery substrate).")
    if not execute:
        print("\nDry-run — NOTHING was written. Re-run with --execute to persist.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Backfill mi_theme_ecosystems for active themes (ADR 0032 Phase 1).")
    ap.add_argument("--execute", action="store_true",
                    help="write mappings + audit rows (default: dry-run)")
    ap.add_argument("--keyword-only", action="store_true",
                    help="skip Haiku; deterministic keyword/exemplar fallback only")
    ap.add_argument("--stale-after-days", type=int, default=7,
                    help="active-theme recency window (default 7)")
    args = ap.parse_args()
    return asyncio.run(_run(args.execute, args.keyword_only, args.stale_after_days))


if __name__ == "__main__":
    raise SystemExit(main())
