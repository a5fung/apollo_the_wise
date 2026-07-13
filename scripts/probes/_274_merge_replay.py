"""#274 C4 — theme-merge arm offline replay (ADR 0025 §3). Read-only.

Stage A (deterministic): family assignment + anchor pairing — IMPORTED from
`agents.market_intelligence.theme_merge_arm` (the C1-C3 build extracted the pure logic
this probe validated on 7/11 into the engine; the probe is now a thin driver over the
REAL production path, so future replays rehearse exactly what the nightly arm runs).
Uncapped here (max_pairs=None) so the full fragmentation map prints; the nightly arm
caps at 8 pairs.

Stage B (LLM adjudicator): `theme_merge_arm.adjudicate_merge_pair` — Haiku, temp=0,
forced tool_choice, scratchpad-first schema, the ADR's LOAD-BEARING negative exemplars
(P&C vs specialty-cat = DISTINCT; office vs multifamily REIT = DISTINCT), merge on
shared DRIVER/catalyst, NEVER on sector label.

Success criteria (ADR §3): ZERO merges across the legit-kill anchors. Prints the action
list + the legit-kill verdicts. Read-only — proposes; no theme is mutated.

Run: docker cp then docker exec -w /app apollo-market python /tmp/_274_merge_replay.py
"""
import asyncio
import os
import sys

sys.path.insert(0, "/app")

from agents.market_intelligence.db import get_pool
from agents.market_intelligence.theme_merge_arm import (
    adjudicate_merge_pair, group_families, propose_merge_pairs,
)
import anthropic

# legit-kill anchors (ADR §3 success criterion — these MUST come back non-MERGE)
LEGIT_KILL = [
    ("Property & Casualty Insurance Underwriters", "Specialty Catastrophe Property Insurance Underwriters"),
    ("Office REIT Recovery & Re-Rating", "Multifamily Apartment REITs"),
]


async def main() -> int:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT DISTINCT ON (name) name, description, tickers, stage,
                   COALESCE(array_length(tickers,1),0) AS n
            FROM mi_themes
            WHERE theme_date >= (SELECT max(theme_date) FROM mi_themes) - 7
              AND stage <> 'Retired' AND tickers IS NOT NULL AND array_length(tickers,1) >= 1
            ORDER BY name, theme_date DESC
        """)
    themes = [dict(r) for r in rows]

    # Stage A: the ENGINE's pairing (uncapped, no cooldowns — full replay map)
    fams = group_families(themes)
    pairs = propose_merge_pairs(themes, cooldown_pairs=frozenset(), max_pairs=None)
    print("=== Stage A — families & anchor pairs (deterministic, engine logic) ===")
    pairs_by_anchor: dict[str, int] = {}
    for a, _o in pairs:
        pairs_by_anchor[a["name"]] = pairs_by_anchor.get(a["name"], 0) + 1
    for fam, members in sorted(fams.items()):
        if len(members) < 2:
            continue
        anchor = sorted(members, key=lambda x: (-len(x.get("tickers") or []), x.get("name") or ""))[0]
        print(f"  {fam:<18} n_themes={len(members):>2}  anchor='{anchor['name']}' ({anchor['n']})  "
              f"→ {pairs_by_anchor.get(anchor['name'], 0)} candidate pairs")
    print(f"\nTotal candidate pairs: {len(pairs)}\n")

    client = anthropic.AsyncAnthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))
    sem = asyncio.Semaphore(2)
    verdicts = await asyncio.gather(*[
        adjudicate_merge_pair(a, b, client=client, semaphore=sem) for a, b in pairs
    ])

    merges, distincts, pcs, errs = [], [], [], []
    for (a, b), v in zip(pairs, verdicts):
        vd = v.get("verdict", "ERROR")
        line = (a["name"], b["name"], v.get("driver_a", ""), v.get("driver_b", ""), v.get("reason", ""))
        (merges if vd == "MERGE" else distincts if vd == "DISTINCT"
         else pcs if vd == "PARENT_CHILD" else errs).append(line)

    print(f"=== Stage B — adjudication: {len(merges)} MERGE · {len(distincts)} DISTINCT · "
          f"{len(pcs)} PARENT_CHILD · {len(errs)} err ===\n")
    print("MERGE (the action list — themes that collapse):")
    for a, b, da, db, r in merges:
        print(f"  ⇒ '{b}'  INTO  '{a}'   [{db} = {da}] — {r}")
    print("\nPARENT_CHILD:")
    for a, b, da, db, r in pcs:
        print(f"  ↳ '{b}' child-of '{a}' — {r}")
    print(f"\nDISTINCT (kept separate): {len(distincts)}")
    for a, b, da, db, r in distincts[:40]:
        print(f"  ∥ '{b}' vs '{a}'  [{db} ≠ {da}] — {r}")
    if errs:
        print(f"\nERR/PARSE: {errs}")

    # legit-kill check
    print("\n=== LEGIT-KILL CHECK (these anchor pairs MUST be DISTINCT) ===")
    merged_names = {(a, b) for a, b, *_ in merges} | {(b, a) for a, b, *_ in merges}
    ok = True
    for x, y in LEGIT_KILL:
        killed = (x, y) in merged_names or (y, x) in merged_names
        present = any(t["name"] == x for t in themes) and any(t["name"] == y for t in themes)
        status = "N/A (not both present)" if not present else ("❌ MERGED — FAIL" if killed else "✓ DISTINCT")
        if present and killed:
            ok = False
        print(f"  {x}  ×  {y}: {status}")
    print(f"\nREPLAY SUCCESS CRITERION (zero legit-kill merges): {'✓ PASS' if ok else '❌ FAIL'}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
