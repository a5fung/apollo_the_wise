"""#274 C4 — theme-merge arm offline replay (ADR 0025 §3). Read-only.

Stage A (deterministic): assign each active theme (recency ≤7d, has members) to a narrative FAMILY
via a curated stem list; within each family with ≥2 members, pair every theme against the family
ANCHOR (largest by member count) — the "should this small theme merge into the big one?" question.
This bounds pairs to ~(n−1)/family (vs C(n,2)) and always includes the legit-kill anchor pairs.

Stage B (LLM adjudicator, Haiku — the same rigor as validation): MERGE / DISTINCT / PARENT_CHILD
per pair. The prompt carries the ADR's LOAD-BEARING negative exemplars (P&C vs specialty-cat =
DISTINCT; office vs multifamily REIT = DISTINCT) and the instruction: merge on shared
DRIVER/catalyst, NEVER on sector label.

Success criteria (ADR §3): ZERO merges across the legit-kill anchors. Prints the action list +
the legit-kill verdicts. Read-only — proposes; no theme is mutated.

Run: docker cp then docker exec -w /app apollo-market python /tmp/_274_merge_replay.py
"""
import asyncio
import json
import os
import re
import sys

sys.path.insert(0, "/app")

from agents.market_intelligence.db import get_pool
from shared.llm_models import HAIKU
import anthropic

# curated narrative stems (Stage A only PROPOSES; precision lives in Stage B)
FAMILIES = [
    ("insurance", r"insurance|underwrit|mortgage insurance"),
    ("reit", r"\bREIT\b|apartment|self-storage|residential rental"),
    ("quantum", r"quantum"),
    ("bank", r"\bbank\b|commercial banks"),
    ("semiconductor", r"semiconductor|silicon|wafer|chip|foundry"),
    ("payments_fintech", r"fintech|payment|digital financial|digital credit|digital banking|expense management|wealth management|brokerage platforms"),
    ("oncology", r"oncology|cancer|tumor"),
    ("autoimmune", r"autoimmune|inflammatory|immunolog"),
    ("gene_cell_therapy", r"gene therapy|cell therapy|genome editing|synthetic dna|genomic"),
    ("diagnostics", r"diagnostic|biopsy|molecular|early detection"),
    ("defense_aero", r"defense|aerospace|drone|unmanned|satellite"),
    ("freight", r"freight|truckload|logistics|carriers"),
    ("energy_downstream", r"refining|petroleum|midstream|pipeline|pressure pumping|oilfield"),
]

# legit-kill anchors (ADR §3 success criterion — these MUST come back DISTINCT)
LEGIT_KILL = [
    ("Property & Casualty Insurance Underwriters", "Specialty Catastrophe Property Insurance Underwriters"),
    ("Office REIT Recovery & Re-Rating", "Multifamily Apartment REITs"),
]

PROMPT = """You adjudicate whether two stock-market THEMES should MERGE. The bar is a shared
DRIVER / catalyst — NOT a shared sector label. Two themes in the same sector with DIFFERENT
demand drivers stay DISTINCT.

NEGATIVE EXEMPLARS (these are DISTINCT, never merge):
- "P&C insurance underwriters" vs "specialty-catastrophe property underwriters" = DISTINCT
  (broad multi-line pricing cycle vs a cat-exposed reinsurance-linked driver).
- "Office REITs" vs "multifamily/apartment REITs" = DISTINCT (return-to-office recovery vs
  housing-shortage rental demand — opposite drivers).

Verdicts:
- MERGE: one thesis, one driver — the two are the same trade in two names.
- DISTINCT: genuine sub-industries with different drivers.
- PARENT_CHILD: one is strictly a sub-theme of the other (narrower slice of the same driver).

THEME A: {a_name}
  {a_desc}
THEME B: {b_name}
  {b_desc}

Return ONLY a JSON object: {{"verdict":"MERGE|DISTINCT|PARENT_CHILD","driver_a":"<≤6 words>","driver_b":"<≤6 words>","reason":"<≤25 words>"}}"""


def family_of(name):
    for fam, pat in FAMILIES:
        if re.search(pat, name, re.I):
            return fam
    return None


async def adjudicate(client, a, b):
    try:
        msg = await client.messages.create(
            model=HAIKU, max_tokens=250,
            messages=[{"role": "user", "content": PROMPT.format(
                a_name=a["name"], a_desc=(a["description"] or "")[:280],
                b_name=b["name"], b_desc=(b["description"] or "")[:280])}])
        txt = msg.content[0].text
        m = re.search(r"\{.*\}", txt, re.S)
        return json.loads(m.group(0)) if m else {"verdict": "PARSE_ERR", "reason": txt[:60]}
    except Exception as e:
        return {"verdict": "ERR", "reason": str(e)[:80]}


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
    for t in themes:
        t["family"] = family_of(t["name"])

    # Stage A: anchor pairing per family (≥2 members)
    fams = {}
    for t in themes:
        if t["family"]:
            fams.setdefault(t["family"], []).append(t)
    pairs = []
    print("=== Stage A — families & anchor pairs (deterministic) ===")
    for fam, members in sorted(fams.items()):
        if len(members) < 2:
            continue
        anchor = max(members, key=lambda x: x["n"])
        others = [m for m in members if m["name"] != anchor["name"]]
        # ADR gate: pair when one side <4 members OR the family holds ≥3 themes
        gated = [o for o in others if o["n"] < 4 or len(members) >= 3]
        print(f"  {fam:<18} n_themes={len(members):>2}  anchor='{anchor['name']}' ({anchor['n']})  "
              f"→ {len(gated)} candidate pairs")
        for o in gated:
            pairs.append((anchor, o))
    print(f"\nTotal candidate pairs: {len(pairs)}\n")

    client = anthropic.AsyncAnthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))
    verdicts = await asyncio.gather(*[adjudicate(client, a, b) for a, b in pairs])

    merges, distincts, pcs, errs = [], [], [], []
    for (a, b), v in zip(pairs, verdicts):
        vd = v.get("verdict", "ERR")
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
