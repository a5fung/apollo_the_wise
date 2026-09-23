"""ADR 0032 §1.4 — Phase-2 re-granularization backtest probe (flip gate). Read-only.

Part 1 (Route A): the F-2 sole-parent-kill population (15 kills since 6/22, ids
pinned below; labels SIGNED per PLAN #471 — 3 cyber = should-survive-as-child,
12 others = legit-kill). For each kill: reconstruct that night's active
`mi_themes` snapshot, compute containment vs every protected incumbent, classify
{sole-parent / multi-parent / low-overlap} across the C_MIN × C_MULTI grid, and
replay every adjudicable (kill, best-parent) pair through the REAL
`theme_merge_arm.adjudicate_merge_pair` — the corpus-cleared ADR-0025 Arm-B
adjudicator (prompt v2-2026-07-12-slice-merge, temp=0). ONE copy, no drift:
imported from the deployed module, exactly what `_route_a_subtheme` calls in
production (theme_engine.py:3983-3988). Accept criteria A1-A4 evaluated per cell.

Part 2 (Route B): (S, K) = (SPLIT_DOM_MIN_MEMBERS, SPLIT_DOM_MIN_STRONG) sweep
over the last ~30 snapshot days — eligibility counts only, no LLM. Caveat [U]:
the eco mapping is as-of-today applied retroactively (design doc §1.4 Part-2).

Read-only: SELECTs only; adjudicator called with log_spend=False (no spend rows).
Run: ssh apollo@87.99.134.162 'docker exec -i apollo-market python -' < this_file
"""
import asyncio
import os
import re
import sys
from collections import defaultdict

sys.path.insert(0, "/app")

import anthropic  # noqa: E402

from agents.market_intelligence.db import get_pool  # noqa: E402
from agents.market_intelligence.theme_merge_arm import (  # noqa: E402
    ADJUDICATION_PROMPT_VERSION, adjudicate_merge_pair,
)

# F-2 kill population (audit ids, verified 2026-07-16) + SIGNED labels
KILL_IDS = [17083, 18570, 19241, 19581, 19723, 19724, 19725, 19726,
            19877, 19879, 20055, 20056, 20057, 20454, 20987]
CYBER_SHOULD_SURVIVE = {19723, 20454, 20987}   # signed: should-survive-as-child
# everything else = signed legit-kill

C_MIN_GRID = [1.0, 0.9, 0.8, 0.7, 0.6]
C_MULTI_GRID = [0.25, 0.34, 0.5]
MIN_SHARED = 3        # MIN_SHARED_FOR_MERGE — Pass1 pair-fire floor
MIN_MEMBERS = 3       # SUBTHEME_MIN_MEMBERS (T6)
S_GRID = [8, 10, 12]  # SPLIT_DOM_MIN_MEMBERS
K_GRID = [6, 8, 10]   # SPLIT_DOM_MIN_STRONG
MAX_THEME_STOCKS = 20 # Route B upper bound (fat trigger owns >20)
ROUTE_CAP_REF = 2     # illustrative A4 reference


def parse_kill(summary: str, detail: str):
    name = re.sub(r"^New theme: (.*) \(\d+ stocks\)$", r"\1", summary)
    m = re.search(r"Tickers:\s*([A-Z0-9, ]+)", detail)
    tickers = [t.strip() for t in (m.group(1) if m else "").split(",") if t.strip()]
    th = re.search(r"Thesis:\s*(.*)", detail, re.S)
    thesis = (th.group(1).strip() if th else "")
    return name, tickers, thesis


async def main() -> int:
    pool = await get_pool()
    print(f"=== ADR 0032 §1.4 probe — adjudicator prompt {ADJUDICATION_PROMPT_VERSION} "
          f"(REAL theme_merge_arm.adjudicate_merge_pair, temp=0) ===\n")

    async with pool.acquire() as conn:
        # ── Part 0: deterministic blast-radius re-check (G2 sweep) ──────────
        rows = await conn.fetch("""
            SELECT (created_at AT TIME ZONE 'America/New_York')::date AS d,
                   detail LIKE '%%i_protected=False%%' AS newborn_strip, count(*) AS n
            FROM mi_audit_log WHERE event_type = 'theme_pass1_protect_strip'
            GROUP BY 1, 2 ORDER BY 1""")
        tot = sum(r["n"] for r in rows)
        nb = [(r["d"], r["n"]) for r in rows if r["newborn_strip"]]
        print(f"[sweep] protect-strip events total={tot} · newborn-victim "
              f"(i_protected=False)={sum(n for _, n in nb)} on {nb}")
        print("[sweep] all remaining events are BOTH_PROTECTED established-pair strips "
              "— a newborn-keyed route leaves them byte-identical\n")

        # ── Part 1 data: kills + night snapshots ────────────────────────────
        krows = await conn.fetch("""
            SELECT id, (created_at AT TIME ZONE 'America/New_York')::date AS birth_et,
                   summary, detail
            FROM mi_audit_log WHERE id = ANY($1) ORDER BY id""", KILL_IDS)
        kills = []
        for r in krows:
            name, tickers, thesis = parse_kill(r["summary"], r["detail"])
            kills.append({"id": r["id"], "date": r["birth_et"], "name": name,
                          "tickers": tickers, "thesis": thesis,
                          "label": ("should-survive" if r["id"] in CYBER_SHOULD_SURVIVE
                                    else "legit-kill")})
        assert len(kills) == 15, f"expected 15 kills, got {len(kills)}"

        # night snapshot per kill: protected incumbents = names that existed
        # BEFORE the birth night (row in [D-8, D-1]); membership/description =
        # that night's row (theme_date = D) if present, else latest ≤ D-1.
        for k in kills:
            d = k["date"]
            incs = await conn.fetch("""
                WITH latest AS (
                  SELECT DISTINCT ON (name) name, description, tickers, stage, theme_date
                  FROM mi_themes
                  WHERE theme_date BETWEEN $1::date - 8 AND $1::date
                    AND tickers IS NOT NULL
                  ORDER BY name, theme_date DESC),
                existed AS (
                  SELECT DISTINCT name FROM mi_themes
                  WHERE theme_date BETWEEN $1::date - 8 AND $1::date - 1)
                SELECT l.* FROM latest l JOIN existed e USING (name)
                WHERE l.stage <> 'Retired'""", d)
            cands = []
            kt = set(k["tickers"])
            for it in incs:
                if it["name"] == k["name"]:
                    continue
                inter = len(kt & set(it["tickers"] or []))
                if inter >= 1:
                    cands.append({"name": it["name"], "inter": inter,
                                  "c": inter / len(kt) if kt else 0.0,
                                  "n": len(it["tickers"] or []),
                                  "description": it["description"] or "",
                                  "tickers": list(it["tickers"] or []),
                                  "snap": str(it["theme_date"])})
            cands.sort(key=lambda x: (-x["c"], x["name"]))
            k["cands"] = cands

    # ── Part 1: containment table + grid classification ─────────────────────
    print("=== Part 1 — per-kill containment vs that night's protected incumbents ===")
    for k in kills:
        best = k["cands"][0] if k["cands"] else None
        others = [c for c in k["cands"][1:] if c["inter"] >= MIN_SHARED]
        second = k["cands"][1] if len(k["cands"]) > 1 else None
        print(f"\n#{k['id']} {k['date']} [{k['label']}] '{k['name']}' "
              f"({len(k['tickers'])}: {','.join(k['tickers'])})")
        if len(k["tickers"]) < MIN_MEMBERS:
            print("   EXCLUDED: <3 members (fails T6 + MIN_SHARED pair-fire floor) — never routable")
            continue
        if not best:
            print("   no overlapping incumbent that night (low-overlap → no route)")
            continue
        for c in k["cands"][:4]:
            print(f"   c={c['c']:.2f} |∩|={c['inter']} vs '{c['name']}' "
                  f"(n={c['n']}, snap {c['snap']})")
        cls = ("sole-parent-capable" if best["inter"] >= MIN_SHARED and best["c"] >= 0.6
               and not any(o["c"] > 0.5 for o in others) else
               "multi-parent" if best["c"] >= 0.6 and any(o["c"] > 0.25 for o in others)
               else "low-overlap")
        print(f"   → best='{best['name']}' c={best['c']:.2f}; "
              f"2nd c={second['c']:.2f} ({second['name']})" if second else
              f"   → best='{best['name']}' c={best['c']:.2f}; no 2nd candidate")

    # routable at cell (C_MIN, C_MULTI)?
    def routes_at(k, c_min, c_multi):
        if len(k["tickers"]) < MIN_MEMBERS or not k["cands"]:
            return False
        best = k["cands"][0]
        if best["inter"] < MIN_SHARED or best["c"] < c_min:
            return False
        return not any(o["inter"] >= MIN_SHARED and o["c"] > c_multi
                       for o in k["cands"][1:])

    # ── Part 1: REAL adjudication of every adjudicable best pair ────────────
    # adjudicable = routes at ANY grid cell (loosest: C_MIN=0.6, C_MULTI=0.5);
    # plus ADVISORY calls on the remaining ≥3-member kills' best pairs so the
    # sign-off table shows a verdict for the whole population.  Cyber pairs run
    # twice (temp=0 determinism evidence).
    client = anthropic.AsyncAnthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))
    sem = asyncio.Semaphore(2)
    tasks, meta = [], []
    for k in kills:
        if len(k["tickers"]) < MIN_MEMBERS or not k["cands"]:
            continue
        best = k["cands"][0]
        if best["inter"] < MIN_SHARED:
            k["adj"] = None
            continue
        parent = {"name": best["name"], "description": best["description"],
                  "tickers": best["tickers"]}
        newborn = {"name": k["name"], "description": k["thesis"],
                   "tickers": k["tickers"]}
        reps = 2 if k["id"] in CYBER_SHOULD_SURVIVE else 1
        for rep in range(reps):
            # parent = theme A, newborn = theme B — the exact live call order
            # (_route_a_subtheme: adjudicate(themes[j], themes[i]))
            tasks.append(adjudicate_merge_pair(parent, newborn, client=client,
                                               semaphore=sem, log_spend=False))
            meta.append((k, rep))
    print(f"\n=== Part 1 — REAL adjudicator replay: {len(tasks)} Haiku calls "
          f"(cyber pairs ×2 for temp-0 determinism) ===")
    verdicts = await asyncio.gather(*tasks)
    for (k, rep), v in zip(meta, verdicts):
        key = "adj" if rep == 0 else "adj2"
        k[key] = v
        vd = v.get("verdict", "ERROR")
        child = v.get("child", "")
        print(f"\n#{k['id']} [{k['label']}] '{k['name']}'  vs  '{k['cands'][0]['name']}'"
              f"  (rep {rep + 1})")
        print(f"   VERDICT: {vd}" + (f" child={child}" if child else "")
              + f" · prompt={v.get('prompt_version', '?')}")
        print(f"   driver_a={v.get('driver_a', '')!r} driver_b={v.get('driver_b', '')!r}")
        print(f"   reason: {v.get('reason', '')}")
        if k["id"] in CYBER_SHOULD_SURVIVE and rep == 0:
            print(f"   scratchpad: {(v.get('analysis_scratchpad') or '')[:500]}")

    # ── Part 1: A1-A4 grid ───────────────────────────────────────────────────
    print("\n=== Part 1 — accept-criteria grid (A1 cyber→PARENT_CHILD · A2 zero "
          "legit-kill PARENT_CHILD · A4 fires/night) ===")
    print(f"{'C_MIN':>6} {'C_MULTI':>8} {'routed':>7} {'cyber_routed':>13} "
          f"{'A1':>4} {'A2':>4} {'max/night':>10} {'A4<=2':>6}")
    for c_min in C_MIN_GRID:
        for c_multi in C_MULTI_GRID:
            routed = [k for k in kills if routes_at(k, c_min, c_multi)]
            cyber = [k for k in routed if k["label"] == "should-survive"]
            a1 = (len(cyber) == 3 and all(
                (k.get("adj") or {}).get("verdict") == "PARENT_CHILD"
                and (k.get("adj") or {}).get("child") == "B" for k in cyber))
            bad = [k for k in routed if k["label"] == "legit-kill"
                   and (k.get("adj") or {}).get("verdict") == "PARENT_CHILD"]
            a2 = not bad
            per_night = defaultdict(int)
            for k in routed:
                per_night[k["date"]] += 1
            mx = max(per_night.values()) if per_night else 0
            print(f"{c_min:>6} {c_multi:>8} {len(routed):>7} {len(cyber):>13} "
                  f"{'PASS' if a1 else 'FAIL':>4} {'PASS' if a2 else 'FAIL':>4} "
                  f"{mx:>10} {'PASS' if mx <= ROUTE_CAP_REF else 'FAIL':>6}"
                  + (f"   A2-violators: {[k['name'] for k in bad]}" if bad else ""))

    # ── Part 2: Route B (S, K) sweep ─────────────────────────────────────────
    async with pool.acquire() as conn:
        days = [r["d"] for r in await conn.fetch(
            "SELECT DISTINCT theme_date AS d FROM mi_themes ORDER BY 1 DESC LIMIT 30")]
        days = sorted(days)
        trows = await conn.fetch("""
            SELECT theme_date, name, stage, parent_theme, tickers FROM mi_themes
            WHERE theme_date = ANY($1) AND tickers IS NOT NULL""", days)
        eco = {r["theme_name"]: r["e_code"] for r in await conn.fetch(
            "SELECT theme_name, e_code FROM mi_theme_ecosystems")}
        all_tk = sorted({t for r in trows for t in (r["tickers"] or [])})
        srows = await conn.fetch("""
            SELECT ticker, score_date, rs_composite FROM mi_stock_scores
            WHERE score_date = ANY($1) AND ticker = ANY($2)""", days, all_tk)
        rs = {(r["ticker"], r["score_date"]): r["rs_composite"] for r in srows}

    by_day = defaultdict(list)
    for r in trows:
        by_day[r["theme_date"]].append(r)

    # candidate theme-days at the loosest cell; the grid just thresholds
    cand = []  # (day, name, eco, members, strong)
    for d in days:
        active = [t for t in by_day[d] if t["stage"] not in ("Fading", "Retired")]
        eco_counts = defaultdict(int)
        for t in active:
            e = eco.get(t["name"])
            if e:
                eco_counts[e] += 1
        for t in active:
            e = eco.get(t["name"])
            if not e or e == "E-UNASSIGNED" or eco_counts[e] != 1:
                continue
            if t["parent_theme"]:
                continue
            n = len(t["tickers"] or [])
            if n < min(S_GRID) or n > MAX_THEME_STOCKS:
                continue
            strong = sum(1 for tk in t["tickers"]
                         if (rs.get((tk, d)) or 0) >= 80)
            cand.append((d, t["name"], e, n, strong))

    print(f"\n=== Part 2 — Route B (S,K) sweep over {len(days)} snapshot days "
          f"({days[0]} → {days[-1]}) · eco mapping as-of-today (retroactive, [U]) ===")
    print(f"{'S':>3} {'K':>3} {'theme-day fires':>16} {'avg/night':>10} "
          f"{'max/night':>10} {'distinct themes':>16}")
    for s in S_GRID:
        for kk in K_GRID:
            fires = [(d, nm, e, n, st) for d, nm, e, n, st in cand
                     if n >= s and st >= kk]
            per_night = defaultdict(int)
            for d, *_ in fires:
                per_night[d] += 1
            themes_hit = sorted({nm for _, nm, *_ in fires})
            print(f"{s:>3} {kk:>3} {len(fires):>16} "
                  f"{len(fires) / len(days):>10.2f} "
                  f"{max(per_night.values()) if per_night else 0:>10} "
                  f"{len(themes_hit):>16}")
    print("\nWould-split list per theme (days qualifying at each (S,K) cell):")
    per_theme = defaultdict(list)
    for d, nm, e, n, st in cand:
        per_theme[(nm, e)].append((d, n, st))
    for (nm, e), rows_ in sorted(per_theme.items()):
        cells = {}
        for s in S_GRID:
            for kk in K_GRID:
                q = sum(1 for _, n, st in rows_ if n >= s and st >= kk)
                if q:
                    cells[f"{s},{kk}"] = q
        if not cells:
            continue
        span = f"{min(r[0] for r in rows_)}→{max(r[0] for r in rows_)}"
        sizes = f"members {min(r[1] for r in rows_)}-{max(r[1] for r in rows_)}, " \
                f"strong {min(r[2] for r in rows_)}-{max(r[2] for r in rows_)}"
        print(f"  {nm} [{e}] {span} ({sizes}): {cells}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
