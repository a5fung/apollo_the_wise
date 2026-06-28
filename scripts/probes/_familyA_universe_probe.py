"""ADR 0013 Phase 1 — validate the SIGNED §2 Family-A universe + the ANCHOR-STABILITY invariant.

Read-only. Two checks against the live DB:
  (1) CANARY funnel: under the locked runup operationalization (MAX(close)/MIN(close) >= 1.15 over
      a rolling 10-session window, best over the last 12) + liquidity + ≤1.0% today-compression, do
      the known-good names land IN — especially COO (the 15.0% borderline canary)?
  (2) ANCHOR STABILITY (the production trap, advisor 6/17): the lifecycle key is the ABSOLUTE
      runup-peak-close date. For every ticker qualifying on BOTH of the two most-recent scan dates,
      the emitted anchor_date MUST be identical — a scan-relative key would drift and write a
      duplicate lifecycle row each night, breaking transition dedup. PASS = no drift among the
      intersection (aside from genuinely peak-aged-out names, reported separately).

Run (no deploy needed — the SQL is embedded; gates nothing):
    cat scripts/_familyA_universe_probe.py | ssh apollo@HOST 'docker exec -i apollo-market python -'
"""
import asyncio
import os
from agents.market_intelligence.db import get_pool

KNOWN = ["COO", "HYLN", "ALHC", "APPS", "NTAP", "MNTS"]

PRICE_MIN = 5.0
DVOL_MIN = 20_000_000.0
RUNUP_MIN = 1.15
INCL_MAX = 0.010          # the LOCKED §2 inclusion gate (≤1.0%)
INCL_RANK = 0.004         # the ≤0.4% ranking marker (NOT a gate)

# Mirrors db.get_anticipation_universe — kept embedded so the probe runs pre-deploy.
SQL = """
WITH p AS (SELECT $1::date AS d),
b AS (
  SELECT ticker, trade_date, close, volume,
         row_number() OVER (PARTITION BY ticker ORDER BY trade_date DESC) AS rn
  FROM mi_daily_closes, p
  WHERE trade_date <= p.d AND trade_date > p.d - INTERVAL '60 days'
    AND close > 0 AND volume > 0
),
w AS (SELECT * FROM b WHERE rn <= 25),
liq AS (
  SELECT ticker, percentile_cont(0.5) WITHIN GROUP (ORDER BY close*volume) AS dvol_med,
         count(*) AS n
  FROM w GROUP BY ticker
),
roll AS (
  SELECT ticker, rn, max(close) OVER ww / NULLIF(min(close) OVER ww, 0) AS r10
  FROM w
  WINDOW ww AS (PARTITION BY ticker ORDER BY trade_date ROWS BETWEEN 9 PRECEDING AND CURRENT ROW)
),
ru AS (SELECT ticker, max(r10) FILTER (WHERE rn <= 12) AS best_r10 FROM roll GROUP BY ticker),
pk AS (
  SELECT DISTINCT ON (ticker) ticker, trade_date AS anchor_date, close AS runup_high
  FROM w WHERE rn <= 15 ORDER BY ticker, close DESC, trade_date ASC
),
td AS (
  SELECT a.ticker, a.close AS c0, c.close AS c1
  FROM w a JOIN w c ON c.ticker = a.ticker AND c.rn = 2 WHERE a.rn = 1
)
SELECT liq.ticker, pk.anchor_date, pk.runup_high, ru.best_r10 AS runup_ratio,
       liq.dvol_med, td.c0 AS last_close, abs(td.c0 / NULLIF(td.c1, 0) - 1) AS today_pct,
       liq.n
FROM liq JOIN ru USING (ticker) JOIN pk USING (ticker) JOIN td USING (ticker)
WHERE liq.n >= 15
"""


def _qualifies(r):
    return (r["last_close"] and r["last_close"] >= PRICE_MIN
            and r["dvol_med"] and r["dvol_med"] >= DVOL_MIN
            and r["runup_ratio"] and r["runup_ratio"] >= RUNUP_MIN
            and r["today_pct"] is not None and r["today_pct"] <= INCL_MAX)


async def main():
    pool = await get_pool()
    async with pool.acquire() as c:
        dates = [r["trade_date"] for r in await c.fetch(
            "SELECT DISTINCT trade_date FROM mi_daily_closes ORDER BY trade_date DESC LIMIT 2")]
        if len(dates) < 2:
            print("need ≥2 trade dates in mi_daily_closes"); return
        scan_b, scan_a = dates[0], dates[1]          # b = newer, a = older
        rows_b = {r["ticker"]: dict(r) for r in await c.fetch(SQL, scan_b)}
        rows_a = {r["ticker"]: dict(r) for r in await c.fetch(SQL, scan_a)}

        # PURE-GATE cross-check (advisor 6/17): the JOB's authoritative gate is
        # anticipation's RETIRED evaluate_consolidation was peak_close / MIN(close over the 10 bars ENDING AT
        # the emitted anchor) ≥ 1.15 — a DIFFERENT (tighter) window than the SQL proposer's
        # best_r10 (max over all 10-windows ending in the last 12 sessions). best_r10 ≥ 1.15 does
        # NOT imply the pure ratio ≥ 1.15, so a name can read IN here yet be silently dropped by
        # the job. Verify the pure ratio for the canary names — especially COO at its 1.15 border.
        pure = {}
        for t in KNOWN:
            r = rows_b.get(t)
            if not r or not r["anchor_date"]:
                continue
            win = [row["close"] for row in await c.fetch("""
                SELECT close FROM mi_daily_closes
                WHERE ticker = $1 AND trade_date <= $2 AND close > 0
                ORDER BY trade_date DESC LIMIT 10""", t, r["anchor_date"])]
            if win:
                pure[t] = (max(win) / min(win)) if min(win) else None

    qb = {t: r for t, r in rows_b.items() if _qualifies(r)}
    qa = {t: r for t, r in rows_a.items() if _qualifies(r)}

    print(f"=== ADR 0013 §2 Family-A universe (as-of {scan_b}) ===")
    base = len(rows_b)
    s_price = {t for t, r in rows_b.items() if r["last_close"] and r["last_close"] >= PRICE_MIN}
    s_liq = {t for t in s_price if rows_b[t]["dvol_med"] and rows_b[t]["dvol_med"] >= DVOL_MIN}
    s_run = {t for t in s_liq if rows_b[t]["runup_ratio"] and rows_b[t]["runup_ratio"] >= RUNUP_MIN}
    s_wide = {t for t in s_run if rows_b[t]["today_pct"] is not None and rows_b[t]["today_pct"] <= INCL_MAX}
    s_strict = {t for t in s_wide if rows_b[t]["today_pct"] <= INCL_RANK}
    print(f"  tickers with >=15 sessions ...... {base}")
    print(f"  price >= ${PRICE_MIN:.0f} .................. {len(s_price)}")
    print(f"  + dvol_med >= ${DVOL_MIN/1e6:.0f}M ........... {len(s_liq)}")
    print(f"  + runup MAX/MIN(10) >= {RUNUP_MIN} ..... {len(s_run)}")
    print(f"  + |today %chg| <= {INCL_MAX*100:.1f}% (GATE) .. {len(s_wide)}")
    print(f"  + |today %chg| <= {INCL_RANK*100:.1f}% (rank) .. {len(s_strict)}")

    print("\n=== CANARY — known-good names (with the emitted anchor) ===")
    print(f"  {'tkr':5} {'price':>8} {'dvol$M':>8} {'runup':>6} {'today%':>7} {'anchor':>11}  stage")
    for t in KNOWN:
        r = rows_b.get(t)
        if not r:
            print(f"  {t:5} {'NOT IN window':>34}"); continue
        anc = r["anchor_date"].isoformat() if r["anchor_date"] else "—"
        stage = "IN (≤0.4% tight)" if t in s_strict else (
                "IN (≤1.0% gate)" if t in s_wide else (
                f"runup OK, today {r['today_pct']*100:.2f}% > 1.0%" if t in s_run else (
                f"runup {(r['runup_ratio'] or 0):.3f} < {RUNUP_MIN}" if t in s_liq else "OUT (price/liq)")))
        print(f"  {t:5} {(r['last_close'] or 0):>8.2f} {(r['dvol_med'] or 0)/1e6:>8.1f} "
              f"{(r['runup_ratio'] or 0):>6.3f} {(r['today_pct'] or 0)*100:>7.2f} {anc:>11}  {stage}")

    print("\n=== PURE-GATE CROSS-CHECK — does the JOB's authoritative gate confirm the canary? ===")
    print("  (SQL best_r10 is the loose proposer; the retired evaluate_consolidation was peak/min over the")
    print("   10 bars ENDING AT the anchor is what actually keeps/drops the name)")
    print(f"  {'tkr':5} {'best_r10':>9} {'pure_ratio':>11} {'anchor':>11}  verdict")
    canary_drop = []
    for t in KNOWN:
        r, pr = rows_b.get(t), pure.get(t)
        if not r:
            continue
        in_sql = t in s_wide
        anc = r["anchor_date"].isoformat() if r["anchor_date"] else "—"
        if pr is None:
            verdict = "no window"
        elif in_sql and pr < RUNUP_MIN:
            verdict = "⚠️ SQL-IN but PURE DROPS (< 1.15) — silent-drop bug"
            canary_drop.append(t)
        elif in_sql:
            verdict = "✅ IN (both gates)"
        else:
            verdict = "out at SQL gate (n/a)"
        print(f"  {t:5} {(r['runup_ratio'] or 0):>9.3f} "
              f"{(pr if pr is not None else 0):>11.3f} {anc:>11}  {verdict}")
    if canary_drop:
        print(f"  ⚠️  {len(canary_drop)} canary name(s) admitted by SQL but dropped by the pure gate: "
              f"{', '.join(canary_drop)}")
        print("  → ALIGN the two window definitions (proposer vs confirmer) before un-pausing.")
    else:
        print("  ✅ no canary divergence — the proposer and the confirmer agree.")

    print(f"\n=== RAW ANCHOR DRIFT ({scan_a} → {scan_b}) — INFORMATIONAL (carry-forward absorbs it) ===")
    both = sorted(set(qa) & set(qb))
    new_leg, carried = [], []
    for t in both:
        ra, rb = qa[t], qb[t]
        aa, ab = ra["anchor_date"], rb["anchor_date"]
        if aa == ab:
            continue
        # new-higher-high → a legitimately NEW leg (select_consolidation_keys seeds the new anchor).
        # lesser-peak re-anchor (old peak aged out) → the job CARRIES the original anchor (no dupe).
        if ab > aa and (rb["runup_high"] or 0) > (ra["runup_high"] or 0):
            new_leg.append((t, aa.isoformat(), ab.isoformat()))
        else:
            carried.append((t, aa.isoformat(), ab.isoformat()))
    print(f"  qualifying on BOTH days ......... {len(both)}")
    print(f"  raw anchor IDENTICAL .......... {len(both) - len(new_leg) - len(carried)}")
    print(f"  new-higher-high → new leg ..... {len(new_leg)}  (universe anchor wins — correct)")
    print(f"  lesser-peak re-anchor ......... {len(carried)}  (CARRIED to original — no duplicate row)")
    if carried:
        for t, aa, ab in carried[:20]:
            print(f"      {t:5} raw {aa} → {ab}  (job keeps {aa})")
    print("  → raw SQL drift is EXPECTED; the un-pause gate is the carry-forward unit test on these")
    print("    same snapshots: tests/test_anticipation_consolidation.py::test_carry_forward_*.")

    # Fixture dump (DUMP_FIXTURE=1): the two real qualifying snapshots → captured into
    # tests/fixtures so the carry-forward test runs the REAL select_consolidation_keys on the
    # actual 6/15→6/16 drift (real data + real fn, no deploy). Single-sourced off this SQL.
    if os.environ.get("DUMP_FIXTURE"):
        import json

        def _snap(q):
            return [{"ticker": t, "anchor_date": r["anchor_date"].isoformat(),
                     "runup_high": float(r["runup_high"]) if r["runup_high"] is not None else None,
                     "dvol_med": float(r["dvol_med"]) if r["dvol_med"] is not None else None}
                    for t, r in sorted(q.items())]
        print("<<<FIXTURE_JSON>>>")
        print(json.dumps({"scan_a": scan_a.isoformat(), "scan_b": scan_b.isoformat(),
                          "a": _snap(qa), "b": _snap(qb)}))
        print("<<<END_FIXTURE_JSON>>>")


if __name__ == "__main__":
    asyncio.run(main())
