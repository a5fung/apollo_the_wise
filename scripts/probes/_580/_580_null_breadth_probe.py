"""#580 probe — why mi_themes.pct_above_20sma is NULL on non-Retired themes, and what filling it would do.

READ-ONLY. SELECT-only against prod via ssh + `docker exec ... psql` with
PGOPTIONS default_transaction_read_only=on (the server itself rejects any write).
Imports NOTHING from the app — the engine's breadth function is re-implemented
below, line for line, from agents/market_intelligence/db.py::get_ticker_breadth_above_sma20:

    above = COUNT(*) FILTER (WHERE close > sma_20)
    total = COUNT(*) FILTER (WHERE sma_20 IS NOT NULL AND close IS NOT NULL)
    FROM mi_stock_scores WHERE ticker = ANY(tickers) AND score_date = trade_date
    -> None if no rows / total == 0, else round(above / total, 3)

and the forcing rule from theme_engine.py::_rescore_existing_theme:

    pct_breadth is not None
    and pct_breadth < _BREADTH_DECAY_THRESHOLD                      (0.40, theme_engine.py:104)
    and (theme.get("pct_above_20sma") or 1.0) < _BREADTH_DECAY_THRESHOLD   (yesterday's stored value)
    and stage != "Fading"  ->  stage = "Fading"

Usage:  python scripts/probes/_580/_580_null_breadth_probe.py > scripts/probes/_580/_580_null_breadth_probe.out.txt
"""
from __future__ import annotations

import json
import subprocess
import sys
from collections import defaultdict

SSH = "apollo@87.99.134.162"
THRESHOLD = 0.40   # theme_engine.py:104 _BREADTH_DECAY_THRESHOLD


def psql_json(sql: str):
    """Run ONE read-only SELECT on prod, return the parsed JSON array."""
    s = sql.strip().rstrip(";")
    assert s.lower().startswith(("select", "with")), "probe is SELECT-only"
    wrapped = f"SELECT coalesce(json_agg(t), '[]'::json) FROM ({s}) t;"
    cmd = ["ssh", SSH,
           "docker exec -i -e PGOPTIONS='-c default_transaction_read_only=on' "
           "apollo-postgres psql -U apollo -d apollo -At"]
    out = subprocess.run(cmd, input=wrapped, capture_output=True, text=True, timeout=180)
    if out.returncode != 0:
        raise RuntimeError(f"psql failed: {out.stderr}")
    return json.loads(out.stdout.strip())


def engine_breadth(tickers, rows_by_ticker):
    """Exact replica of get_ticker_breadth_above_sma20 over pre-fetched (close, sma_20) rows."""
    if not tickers:
        return None
    above = total = 0
    for tk in tickers:
        r = rows_by_ticker.get(tk)
        if r is None:
            continue
        close, sma = r
        if close is not None and sma is not None:
            total += 1
            if close > sma:
                above += 1
    if not total:
        return None
    return round(above / total, 3)


def coverage(tickers, rows_by_ticker):
    have = [tk for tk in tickers if tk in rows_by_ticker
            and rows_by_ticker[tk][0] is not None and rows_by_ticker[tk][1] is not None]
    return len(have), len(tickers)


def scores_for(date, tickers):
    rows = psql_json(
        "SELECT ticker, close, sma_20 FROM mi_stock_scores "
        f"WHERE score_date = '{date}' AND ticker = ANY(ARRAY[{','.join(repr(t) for t in tickers)}]::text[])")
    return {r["ticker"]: (r["close"], r["sma_20"]) for r in rows}


def main():
    latest = psql_json("SELECT max(theme_date)::text AS d FROM mi_themes")[0]["d"]
    print(f"=== LATEST theme_date on prod: {latest} ===\n")

    # ---- 3. counts -------------------------------------------------------------
    by_stage = psql_json(
        f"SELECT stage, count(*) n, count(*) FILTER (WHERE pct_above_20sma IS NULL) n_null "
        f"FROM mi_themes WHERE theme_date='{latest}' GROUP BY stage ORDER BY stage")
    print("stage | rows | NULL breadth")
    for r in by_stage:
        print(f"{r['stage']:<12}| {r['n']:>4} | {r['n_null']:>3}")
    nonret = sum(r["n"] for r in by_stage if r["stage"] != "Retired")
    nonret_null = sum(r["n_null"] for r in by_stage if r["stage"] != "Retired")
    print(f"\nNON-RETIRED: {nonret} rows, {nonret_null} with NULL pct_above_20sma\n")

    nulls = psql_json(
        f"""SELECT t.name, t.stage, t.source, t.days_active, COALESCE(cardinality(t.tickers),0) AS members,
                   t.score, t.rs_avg,
                   (SELECT min(theme_date)::text FROM mi_themes x WHERE x.name=t.name) AS first_seen,
                   (SELECT count(*) FROM mi_themes x WHERE x.name=t.name) AS rows_total,
                   t.tickers
            FROM mi_themes t
            WHERE t.theme_date='{latest}' AND t.stage<>'Retired' AND t.pct_above_20sma IS NULL
            ORDER BY t.name""")

    # ---- 4. replicate engine breadth for each NULL theme -----------------------
    print("=== NULL-breadth themes: breadth computed EXACTLY as the engine would, "
          f"on score_date={latest} ===")
    print("name | stage | source | members | first_seen | scored/members | breadth | < 0.40 ?")
    would_flip = []
    for n in nulls:
        rows = scores_for(latest, n["tickers"])
        b = engine_breadth(n["tickers"], rows)
        have, tot = coverage(n["tickers"], rows)
        below = (b is not None and b < THRESHOLD)
        print(f"{n['name']} | {n['stage']} | {n['source']} | {n['members']} | {n['first_seen']} | "
              f"{have}/{tot} | {b} | {'BELOW' if below else 'ok'}")
        if below:
            would_flip.append((n["name"], n["stage"], b, n["members"]))
    print(f"\nBELOW-threshold NULL themes (latest date): {len(would_flip)} -> {would_flip}\n")

    # ---- validation of the replica against stored (non-NULL) breadth -----------
    print("=== REPLICA VALIDATION: recompute breadth for every NON-NULL non-Retired row on "
          f"{latest} from its stored tickers, compare to stored pct_above_20sma ===")
    stored = psql_json(
        f"SELECT name, tickers, pct_above_20sma AS stored FROM mi_themes "
        f"WHERE theme_date='{latest}' AND stage<>'Retired' AND pct_above_20sma IS NOT NULL")
    all_tk = sorted({tk for s in stored for tk in s["tickers"]})
    rows_all = {r["ticker"]: (r["close"], r["sma_20"]) for r in psql_json(
        "SELECT ticker, close, sma_20 FROM mi_stock_scores "
        f"WHERE score_date = '{latest}' AND ticker = ANY(ARRAY[{','.join(repr(t) for t in all_tk)}]::text[])")}
    exact = close_ = off = 0
    offs = []
    for s in stored:
        b = engine_breadth(s["tickers"], rows_all)
        if b is None:
            off += 1
            offs.append((s["name"], s["stored"], b))
        elif abs(b - s["stored"]) < 0.0006:
            exact += 1
        elif abs(b - s["stored"]) < 0.06:
            close_ += 1   # member set differs slightly (pruned/merged after breadth was read)
            offs.append((s["name"], s["stored"], b))
        else:
            off += 1
            offs.append((s["name"], s["stored"], b))
    print(f"stored non-NULL rows: {len(stored)} | exact match: {exact} | within 0.06: {close_} | "
          f"further off / None: {off} (a mismatch = members changed by merge/prune AFTER breadth was read)")
    for o in offs[:15]:
        print("   mismatch:", o)
    print()

    # ---- 1/2. root-cause census: WHY each historical NULL happened -------------
    since = "2026-08-01"
    hist = psql_json(
        f"""WITH r AS (
              SELECT t.theme_date::text AS theme_date, t.name, t.stage, t.source, t.tickers,
                     (SELECT p.stage FROM mi_themes p WHERE p.name=t.name AND p.theme_date<t.theme_date
                        ORDER BY p.theme_date DESC LIMIT 1) AS prev_stage,
                     (SELECT p.theme_date::text FROM mi_themes p WHERE p.name=t.name AND p.theme_date<t.theme_date
                        ORDER BY p.theme_date DESC LIMIT 1) AS prev_date
              FROM mi_themes t
              WHERE t.theme_date >= '{since}' AND t.stage<>'Retired' AND t.pct_above_20sma IS NULL)
            SELECT * FROM r ORDER BY theme_date""")
    print(f"=== ROOT-CAUSE CENSUS of every non-Retired NULL-breadth row since {since}: {len(hist)} rows ===")
    hist_tk = sorted({tk for h in hist for tk in h["tickers"]})
    hist_dates = sorted({h["theme_date"] for h in hist})
    hist_scores = defaultdict(dict)   # date -> ticker -> (close, sma)
    for r in psql_json(
            "SELECT score_date::text AS d, ticker, close, sma_20 FROM mi_stock_scores "
            f"WHERE score_date >= '{since}' AND ticker = ANY(ARRAY[{','.join(repr(t) for t in hist_tk)}]::text[])"):
        hist_scores[r["d"]][r["ticker"]] = (r["close"], r["sma_20"])

    # A "continuing" NULL (prior non-Retired row exists) can still be a REBIRTH: the rescore pass
    # returns None (-> audit 'theme_retired') and discovery re-creates the same name the same night
    # (-> audit 'theme_discovered'), which goes through _score_new_theme (no breadth). Verify from
    # mi_audit_log rather than assume.
    cont = [h for h in hist if not (h["prev_date"] is None or h["prev_stage"] == "Retired")]
    audit_hits = {}
    for h in cont:
        nm = h["name"].replace("'", "''")
        d = h["theme_date"]
        ev = psql_json(
            "SELECT event_type FROM mi_audit_log "
            f"WHERE created_at >= '{d} 00:00+00'::timestamptz AND created_at < ('{d}'::date + 1)::timestamptz "
            f"AND ((event_type='theme_discovered' AND summary LIKE 'New theme: {nm} (%') "
            f"  OR (event_type='theme_retired' AND summary = 'Retired: {nm}'))")
        audit_hits[(d, h["name"])] = sorted({e["event_type"] for e in ev})

    cats = defaultdict(int)
    for h in hist:
        if h["prev_date"] is None or h["prev_stage"] == "Retired":
            cat = "BIRTH/REBIRTH (dict from _score_new_theme or promote/seed INSERT — never calls the breadth fn)"
        else:
            rows = hist_scores.get(h["theme_date"], {})
            b = engine_breadth(h["tickers"], rows)
            hits = audit_hits.get((h["theme_date"], h["name"]), [])
            if b is None:
                cat = "CONTINUING, breadth fn returns None (no member has close+sma_20 in mi_stock_scores that date)"
            elif hits == ["theme_discovered", "theme_retired"]:
                cat = ("SAME-NIGHT retire (theme_retired) + rediscovery (theme_discovered) under the same name "
                       "-> _score_new_theme path, no breadth")
            else:
                cat = f"CONTINUING, breadth fn WOULD return a value; audit={hits} (unexplained -> inspect)"
        h["cat"] = cat
        cats[(cat, h["source"])] += 1
    for (cat, src), n in sorted(cats.items(), key=lambda kv: -kv[1]):
        print(f"{n:>4}  source={src:<16} {cat}")
    print()

    # ---- what filling would do: counterfactual 2-day rule on next night --------
    print("=== COUNTERFACTUAL: had breadth been filled at birth, would the 2-day rule have fired the NEXT night? ===")
    print("rule needs: today's breadth < 0.40 AND yesterday's STORED value < 0.40 with `(x or 1.0)` "
          "(so a stored 0.0 counts as 1.0 — theme_engine.py:3926) AND stage != Fading")
    nxt = psql_json(
        f"""SELECT a.theme_date::text AS d0, a.name, a.stage AS s0,
                   n.theme_date::text AS d1, n.stage AS s1, n.pct_above_20sma AS b1, n.source
            FROM mi_themes a
            JOIN LATERAL (SELECT * FROM mi_themes x WHERE x.name=a.name AND x.theme_date>a.theme_date
                          ORDER BY x.theme_date LIMIT 1) n ON TRUE
            WHERE a.theme_date >= '{since}' AND a.stage<>'Retired' AND a.pct_above_20sma IS NULL""")
    hmap = {(h["theme_date"], h["name"]): h for h in hist}
    n_birth_rows = n_b0_below = n_b0_zero = 0
    flips = []
    for x in nxt:
        h = hmap.get((x["d0"], x["name"]))
        if not h:
            continue
        b0 = engine_breadth(h["tickers"], hist_scores.get(x["d0"], {}))
        n_birth_rows += 1
        if b0 is not None and b0 < THRESHOLD:
            n_b0_below += 1
            if b0 == 0.0:
                n_b0_zero += 1
        b1 = x["b1"]
        # would the rule have forced Fading on d1?
        if (b0 is not None and b0 < THRESHOLD and (b0 or 1.0) < THRESHOLD
                and b1 is not None and b1 < THRESHOLD and x["s1"] not in ("Fading", "Retired")):
            flips.append((x["d0"], x["name"], x["s0"], b0, x["d1"], x["s1"], b1))
    print(f"NULL rows with a following-night row: {n_birth_rows}")
    print(f"  of those, computed birth-night breadth < 0.40: {n_b0_below} (of which exactly 0.0: {n_b0_zero})")
    print(f"  rule WOULD have forced a non-Fading, non-Retired next-night stage to Fading: {len(flips)}")
    for f in flips:
        print("   FLIP:", f)
    print()

    # ---- the `(prev or 1.0)` falsy-zero defect: measured on STORED data --------
    print("=== `(theme.get('pct_above_20sma') or 1.0) < 0.40` (theme_engine.py:3926): a stored 0.0 is FALSY -> read as 1.0 ===")
    fz = psql_json(
        f"""WITH s AS (
              SELECT name, theme_date, stage, pct_above_20sma b,
                     lag(pct_above_20sma) OVER w AS pb, lag(stage) OVER w AS ps
              FROM mi_themes WINDOW w AS (PARTITION BY name ORDER BY theme_date))
            SELECT
              count(*) FILTER (WHERE ps<>'Retired' AND pb>0 AND pb<0.40 AND b<0.40 AND stage NOT IN ('Retired','Fading')) AS rule_should_fire_but_not_fading,
              count(*) FILTER (WHERE ps<>'Retired' AND pb>0 AND pb<0.40 AND b<0.40 AND stage='Fading') AS rule_condition_met_and_fading,
              count(*) FILTER (WHERE ps<>'Retired' AND pb=0 AND b<0.40 AND stage NOT IN ('Retired','Fading')) AS prev_zero_cur_below_not_fading,
              count(*) FILTER (WHERE ps<>'Retired' AND pb=0 AND b<0.40 AND stage IN ('Accelerating','Mainstream')) AS ...bonus_stage_subset
            FROM s WHERE theme_date >= '{since}'""".replace("AS ...bonus_stage_subset", "AS prev_zero_cur_below_in_EP_bonus_stage"))
    print(json.dumps(fz[0], indent=1))
    held = psql_json(
        f"""WITH s AS (
              SELECT name, theme_date, stage, pct_above_20sma b, COALESCE(cardinality(tickers),0) n,
                     lag(pct_above_20sma) OVER w AS pb
              FROM mi_themes WINDOW w AS (PARTITION BY name ORDER BY theme_date))
            SELECT name, stage, n AS members, pb AS prev_night_breadth, b AS latest_breadth FROM s
            WHERE theme_date='{latest}' AND stage IN ('Accelerating','Mainstream') AND b<0.40 AND pb=0
            ORDER BY name""")
    print(f"Accelerating/Mainstream (EP +10 bonus stages) on {latest} with latest breadth <0.40 AND prior-night stored 0.0 "
          f"(rule suppressed by the falsy zero): {len(held)}")
    for r in held:
        print("   ", r)
    print()

    # ---- cause census on the LATEST date ---------------------------------------
    print("=== NULL rows on latest date by cause ===")
    for h in hist:
        if h["theme_date"] == latest:
            print(f"{h['name']} | {h['stage']} | {h['source']} | {h['cat'][:40]}")


if __name__ == "__main__":
    sys.exit(main())
