#!/usr/bin/env python3
"""Theme birth RS-floor replay (2026-08-03) — READ-ONLY evidence probe.

Derives the birth-gate RS floor from the June-August 2026 birth cohort, per the
operator's ruling ("derive the final number from the replay before it ships")
and his named risk (weak-born themes that MATURE would argue for a trajectory
term, not a level). Companion doc:
    docs/analysis/theme_birth_rs_floor_replay_2026-08-03.md
Prior all-time derivation (254 births, member-level):
    docs/analysis/theme_birth_gate_derivation_2026-07-27.md

Data (two prod pulls, cached as TSV; --fetch re-pulls):
  1. mi_themes full daily history (one row per theme per day).
  2. Per-birth member-level avg rs_composite at birth + paired pre-birth
     5-session cohort delta from mi_stock_scores (what the shipped gate's
     db.get_cohort_rs_snapshot actually reads).

Measurement decisions (defended in the doc):
  - Birth RS = MEMBER-LEVEL avg at birth. Stored mi_themes.rs_avg is a
    sentinel 0.0 on 33/178 June+ births (the `rs_scores else 0` fallback);
    valid stored values track member-level closely (checked below).
  - NULL stored rs_avg is a STAGE artifact (Fading/Retired rows never carry
    it); active-stage rows always do.
  - Outcomes use the theme's FIRST lifecycle (rows before any >7-calendar-day
    absence — get_active_themes(stale_after_days=7) means absence IS death).
  - Windowed maturity (W=15 calendar days from birth) controls the
    survivorship/recency confound; births within 15d of data end are CENSORED.

Usage:
  python scripts/probes/_theme_birth_rs_floor_replay.py            # use cached TSVs
  python scripts/probes/_theme_birth_rs_floor_replay.py --fetch    # re-pull from prod
  python scripts/probes/_theme_birth_rs_floor_replay.py --data-dir DIR
"""

import argparse
import collections
import datetime as dt
import os
import statistics
import subprocess
import sys

SSH = ["ssh", "-o", "ConnectTimeout=25", "apollo@87.99.134.162"]
PSQL = 'docker exec apollo-postgres psql -U apollo -d apollo -At -F\'|\' -c '

SQL_THEMES = (
    "SELECT theme_date, name, stage, round(score::numeric,2), "
    "round(rs_avg::numeric,2), days_active, consecutive_accelerating, "
    "round(pct_above_20sma::numeric,2), source, COALESCE(cardinality(tickers),0), "
    "COALESCE(parent_theme,'') FROM mi_themes ORDER BY name, theme_date"
)

SQL_TICKERS = (
    "SELECT theme_date, name, stage, array_to_string(tickers,',') FROM mi_themes "
    "WHERE theme_date >= '2026-06-08' ORDER BY theme_date, name"
)

SQL_MEMBER = """
WITH births AS (
  SELECT DISTINCT ON (name) name, theme_date AS bdate, tickers, rs_avg AS stored_rs
  FROM mi_themes ORDER BY name, theme_date
),
jb AS (SELECT * FROM births WHERE bdate >= '2026-06-01'),
mem AS (SELECT name, bdate, stored_rs, unnest(tickers) AS ticker FROM jb),
d5 AS (
  SELECT b.bdate,
         (SELECT sd FROM (SELECT DISTINCT score_date sd FROM mi_stock_scores
                          WHERE score_date < b.bdate ORDER BY sd DESC OFFSET 4 LIMIT 1) q) AS prior5
  FROM (SELECT DISTINCT bdate FROM jb) b
),
pairs AS (
  SELECT m.name, m.bdate, m.stored_rs,
    (SELECT rs_composite FROM mi_stock_scores s WHERE s.ticker=m.ticker
       AND s.score_date<=m.bdate AND s.score_date>=m.bdate-10
       ORDER BY s.score_date DESC LIMIT 1) AS rs0,
    (SELECT rs_composite FROM mi_stock_scores s WHERE s.ticker=m.ticker
       AND s.score_date<=d.prior5 AND s.score_date>=d.prior5-10
       ORDER BY s.score_date DESC LIMIT 1) AS rs5
  FROM mem m JOIN d5 d ON d.bdate=m.bdate
)
SELECT name, bdate, round(stored_rs::numeric,1), count(*),
  count(rs0), round(avg(rs0)::numeric,1),
  count(*) FILTER (WHERE rs0 IS NOT NULL AND rs5 IS NOT NULL),
  round((avg(rs0-rs5) FILTER (WHERE rs0 IS NOT NULL AND rs5 IS NOT NULL))::numeric,1)
FROM pairs GROUP BY 1,2,3 ORDER BY 2,1
""".replace("\n", " ")

D = dt.date.fromisoformat


def fetch(data_dir):
    for fname, sql in (("_themefloor_mi_themes_full.tsv", SQL_THEMES), ("_themefloor_member_birth_rs.tsv", SQL_MEMBER),
                       ("_themefloor_tickers_rows.tsv", SQL_TICKERS)):
        out = subprocess.run(SSH + [PSQL + '"' + sql + '"'], capture_output=True, text=True, timeout=300)
        if out.returncode != 0:
            sys.exit(f"fetch failed for {fname}: {out.stderr[:500]}")
        with open(os.path.join(data_dir, fname), "w") as f:
            f.write(out.stdout)
        print(f"fetched {fname}: {len(out.stdout.splitlines())} rows")


def ffloat(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def load(data_dir):
    themes = collections.defaultdict(list)
    with open(os.path.join(data_dir, "_themefloor_mi_themes_full.tsv")) as f:
        for line in f:
            p = line.rstrip("\n").split("|")
            if len(p) != 11:
                continue
            r = dict(zip(["date", "name", "stage", "score", "rs", "days_active",
                          "cons_acc", "pct20", "source", "n_tk", "parent"], p))
            themes[r["name"]].append(r)
    for v in themes.values():
        v.sort(key=lambda r: r["date"])
    member = {}
    with open(os.path.join(data_dir, "_themefloor_member_birth_rs.tsv")) as f:
        for line in f:
            p = line.rstrip("\n").split("|")
            if len(p) != 8:
                continue
            member[p[0]] = dict(bdate=p[1], stored=ffloat(p[2]), n_tk=int(p[3]),
                                n_rs0=int(p[4]), rs0=ffloat(p[5]), n_pair=int(p[6]),
                                d5=ffloat(p[7]))
    tk = {}  # (date, name) -> (stage, frozenset(tickers))
    with open(os.path.join(data_dir, "_themefloor_tickers_rows.tsv")) as f:
        for line in f:
            p = line.rstrip("\n").split("|")
            if len(p) != 4:
                continue
            tk[(p[0], p[1])] = (p[2], frozenset(t for t in p[3].split(",") if t))
    return themes, member, tk


def auc(pos, neg):
    """Rank AUC (Mann-Whitney), ties=0.5."""
    if not pos or not neg:
        return None
    wins = ties = 0
    for a in pos:
        for b in neg:
            if a > b:
                wins += 1
            elif a == b:
                ties += 1
    return (wins + 0.5 * ties) / (len(pos) * len(neg))


def med(xs):
    xs = [x for x in xs if x is not None]
    return round(statistics.median(xs), 1) if xs else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fetch", action="store_true", help="re-pull both TSVs from prod first")
    ap.add_argument("--data-dir", default=os.path.dirname(os.path.abspath(__file__)),
                    help="dir holding/receiving the two TSVs")
    ap.add_argument("--window", type=int, default=15, help="maturity observation window, calendar days")
    args = ap.parse_args()
    if args.fetch:
        fetch(args.data_dir)

    themes, member, tkrows = load(args.data_dir)
    data_end = max(D(r["date"]) for v in themes.values() for r in v)
    W = args.window
    censor_cut = data_end - dt.timedelta(days=W)
    print(f"data end {data_end}; window W={W}d; classifiable births <= {censor_cut}")

    # ---- build per-birth records (June+ cohort, first lifecycle only) ----
    recs = []
    for name, rows in themes.items():
        birth = D(rows[0]["date"])
        if birth < dt.date(2026, 6, 1):
            continue
        # first lifecycle = rows before any >7-calendar-day absence
        life = [rows[0]]
        for prev, cur in zip(rows, rows[1:]):
            if (D(cur["date"]) - D(prev["date"])).days > 7:
                break
            life.append(cur)
        m = member.get(name)
        last = D(life[-1]["date"])
        retired_last = life[-1]["stage"] == "Retired"
        absorbed = retired_last and bool(life[-1]["parent"])
        dead = retired_last or (data_end - last).days > 7
        # windowed outcomes
        win = [r for r in life if (D(r["date"]) - birth).days <= W]
        staged = any(r["stage"] in ("Accelerating", "Mainstream") for r in win)
        lived14 = any((D(r["date"]) - birth).days >= 14 for r in life)
        rs_path = [(D(r["date"]), ffloat(r["rs"])) for r in life if ffloat(r["rs"]) is not None and ffloat(r["rs"]) >= 5]
        win_rs = [x for d, x in rs_path if (d - birth).days <= W]
        strong85 = bool(win_rs) and max(win_rs) >= 85
        birth_rs = m["rs0"] if m else None
        rose10 = bool(win_rs) and birth_rs is not None and max(win_rs) - birth_rs >= 10
        # post-birth trajectory: stored rs at 3rd valid snapshot minus birth RS
        post_d3 = rs_path[2][1] - birth_rs if len(rs_path) >= 3 and birth_rs is not None else None
        post_d5 = rs_path[4][1] - birth_rs if len(rs_path) >= 5 and birth_rs is not None else None
        recs.append(dict(
            name=name, birth=birth, n_snaps=len(life), last=last, dead=dead,
            absorbed=absorbed, alive_today=(not dead),
            censored=birth > censor_cut, staged=staged, lived14=lived14,
            parent=life[-1]["parent"] or None,
            strong85=strong85, rose10=rose10, mat=staged or lived14,
            birth_rs=birth_rs, stored=m["stored"] if m else None,
            d5pre=m["d5"] if m else None, post_d3=post_d3, post_d5=post_d5,
            n_tk=m["n_tk"] if m else None, source=rows[0]["source"],
            week=birth.isocalendar()[:2],
        ))
    recs.sort(key=lambda r: (r["birth"], r["name"]))
    print(f"June+ births: {len(recs)}; censored (born > {censor_cut}): {sum(r['censored'] for r in recs)}")

    # ---- instrument checks ----
    diffs = [abs(r["birth_rs"] - r["stored"]) for r in recs
             if r["birth_rs"] is not None and r["stored"] is not None and r["stored"] >= 5]
    sent = [r for r in recs if r["stored"] is not None and r["stored"] < 5]
    print(f"\n== instrument: stored rs_avg (valid, >=5) vs member-level birth RS ==")
    print(f"  n={len(diffs)} median|diff|={med(diffs)} p90={round(sorted(diffs)[int(.9*len(diffs))],1) if diffs else None}")
    print(f"  sentinel-0.0 stored births: {len(sent)}; their member-level RS: median {med([r['birth_rs'] for r in sent])}")
    nom = [r for r in recs if r["birth_rs"] is None]
    print(f"  births with NO member-level RS: {len(nom)} {[r['name'][:40] for r in nom]}")

    cls = [r for r in recs if not r["censored"] and r["birth_rs"] is not None]
    print(f"\nclassifiable births with birth RS: {len(cls)}")
    for k in ("staged", "lived14", "strong85", "rose10", "mat"):
        print(f"  {k}: {sum(r[k] for r in cls)}")
    print(f"  dead: {sum(r['dead'] for r in cls)} (absorbed subset: {sum(r['absorbed'] for r in cls)})")

    # ---- 1. birth RS distribution + bands vs maturity ----
    print("\n== birth RS (member-level) distribution, classifiable ==")
    bands = [(0, 40), (40, 55), (55, 65), (65, 70), (70, 75), (75, 80), (80, 85), (85, 90), (90, 95), (95, 101)]
    for lo, hi in bands:
        b = [r for r in cls if lo <= r["birth_rs"] < hi]
        if not b:
            print(f"  {lo}-{hi}: n=0")
            continue
        print(f"  {lo}-{hi}: n={len(b)} mat={sum(r['mat'] for r in b)} ({100*sum(r['mat'] for r in b)//len(b)}%) "
              f"staged={sum(r['staged'] for r in b)} lived14={sum(r['lived14'] for r in b)} strong85={sum(r['strong85'] for r in b)}")
    for grp, lab in ((True, "matured"), (False, "not-matured")):
        xs = sorted(r["birth_rs"] for r in cls if r["mat"] == grp)
        print(f"  {lab}: n={len(xs)} median={med(xs)} p25={round(xs[len(xs)//4],1)} p10={round(xs[len(xs)//10],1)}")

    # ---- 2. flat floor sweep ----
    def sweep(pred, label, defs=("mat", "staged", "lived14", "strong85")):
        print(f"\n== {label} ==")
        for mdef in defs:
            tot_m = sum(r[mdef] for r in cls)
            print(f"  [maturity={mdef}] (total matured {tot_m}/{len(cls)})")
            print(f"    cell        blocked  FN(mat)  TP(unmat)  FN%of-mat  precision")
            for cname, fn in pred:
                blocked = [r for r in cls if fn(r)]
                FN = sum(r[mdef] for r in blocked)
                TP = len(blocked) - FN
                fnp = 100 * FN / tot_m if tot_m else 0
                prec = 100 * TP / len(blocked) if blocked else 0
                print(f"    {cname:<12} {len(blocked):>6} {FN:>8} {TP:>9} {fnp:>9.1f}% {prec:>9.0f}%")
    flat = [(f"RS<{t}", (lambda r, t=t: r["birth_rs"] < t)) for t in (60, 65, 70, 75, 80)]
    sweep(flat, "FLAT floor sweep (blocked = birth RS below tau)")

    # ---- 3. weak-born (<70) deep dive ----
    print("\n== weak-born (<70) deep dive, classifiable ==")
    wb = [r for r in cls if r["birth_rs"] < 70]
    print(f"  n={len(wb)} matured={sum(r['mat'] for r in wb)} share-of-all-matured="
          f"{100*sum(r['mat'] for r in wb)/max(1,sum(r['mat'] for r in cls)):.0f}%")
    for grp, lab in ((True, "weak-born MATURED"), (False, "weak-born died/not-matured")):
        g = [r for r in wb if r["mat"] == grp]
        print(f"  {lab}: n={len(g)} | pre-birth d5 median={med([r['d5pre'] for r in g])} "
              f"rising={sum(1 for r in g if (r['d5pre'] or -1) >= 0)}/{sum(1 for r in g if r['d5pre'] is not None)} | "
              f"post-birth d3 median={med([r['post_d3'] for r in g])} d5={med([r['post_d5'] for r in g])}")
    print("  full weak-born list (name | birth | RS | d5pre | post_d3 | outcome):")
    for r in sorted(wb, key=lambda r: r["birth_rs"]):
        out = "MAT" if r["mat"] else ("absorbed" if r["absorbed"] else "died")
        parts = [k for k in ("staged", "lived14", "strong85") if r[k]]
        print(f"    {r['name'][:52]:<52} {r['birth']} rs={r['birth_rs']:>5.1f} "
              f"d5pre={'?' if r['d5pre'] is None else r['d5pre']:>5} "
              f"post_d3={'?' if r['post_d3'] is None else round(r['post_d3'],1):>5} "
              f"{out}{('[' + ','.join(parts) + ']') if parts else ''} snaps={r['n_snaps']}")

    # ---- 4. LEVEL vs TRAJECTORY: AUCs ----
    print("\n== level vs trajectory: rank AUC for predicting maturity (mat) ==")
    for key, lab, cond in (
        ("birth_rs", "birth RS level (all classifiable)", cls),
        ("d5pre", "pre-birth 5-session cohort dRS (gate-visible)", [r for r in cls if r["d5pre"] is not None]),
        ("post_d3", "post-birth dRS at 3rd snapshot (needs 3-day deferral; survival-conditioned)",
         [r for r in cls if r["post_d3"] is not None]),
        ("post_d5", "post-birth dRS at 5th snapshot (survival-conditioned)",
         [r for r in cls if r["post_d5"] is not None]),
    ):
        pos = [r[key] for r in cond if r["mat"]]
        neg = [r[key] for r in cond if not r["mat"]]
        a = auc(pos, neg)
        print(f"  {lab}: n={len(cond)} AUC={a:.3f}" if a else f"  {lab}: insufficient")
        # same, weak-born only
        wpos = [r[key] for r in cond if r["mat"] and r["birth_rs"] < 70]
        wneg = [r[key] for r in cond if not r["mat"] and r["birth_rs"] < 70]
        aw = auc(wpos, wneg)
        if aw:
            print(f"      weak-born(<70) only: n={len(wpos)+len(wneg)} AUC={aw:.3f}")

    # ---- 5. OR-cell sweep (the shipped-cell shape, fresh cohort) ----
    def orcell(t, d):
        return lambda r: r["birth_rs"] < t and not (r["d5pre"] is not None and r["d5pre"] >= d)
    cells = [("RS>=70 flat", lambda r: r["birth_rs"] < 70)]
    for t in (60, 65, 70, 75):
        cells.append((f"RS>={t}|d5>=0", orcell(t, 0.0)))
    cells.append(("RS>=70|d5>=3", orcell(70, 3.0)))
    cells.append(("RS>=70|d5>=-5", orcell(70, -5.0)))
    cells.append(("RS>=70|d5>=-8", orcell(70, -8.0)))
    sweep(cells, "OR-cell sweep (blocked = fails level AND fails rising arm)", defs=("mat", "staged", "strong85"))

    # ---- 6. survivorship / cohort checks ----
    print("\n== recency confound: alive-today by birth week (do NOT read as maturity) ==")
    byw = collections.defaultdict(list)
    for r in recs:
        byw[r["week"]].append(r)
    for w in sorted(byw):
        g = byw[w]
        print(f"  week {w}: births={len(g)} alive-today={sum(r['alive_today'] for r in g)} "
              f"censored={sum(r['censored'] for r in g)} mat(classifiable)="
              f"{sum(r['mat'] for r in g if not r['censored'])}/{sum(1 for r in g if not r['censored'])}")

    print("\n== cohort-dominance: flat-70 + OR-70 excluding each birth week ==")
    for w in sorted(set(r["week"] for r in cls)):
        sub = [r for r in cls if r["week"] != w]
        tot_m = sum(r["mat"] for r in sub)
        for cname, fn in (("RS<70 flat", lambda r: r["birth_rs"] < 70), ("OR-cell70", orcell(70, 0.0))):
            blocked = [r for r in sub if fn(r)]
            FN = sum(r["mat"] for r in blocked)
            print(f"  excl wk {w}: {cname}: blocked={len(blocked)} FN={FN} "
                  f"FN%={100*FN/tot_m:.1f}% prec={100*(len(blocked)-FN)/max(1,len(blocked)):.0f}%", end="  ")
        print()

    # ---- 7. fresh out-of-sample slice (births 07-14..07-19, censored in the 7/27 derivation) ----
    print("\n== fresh slice: births 2026-07-14..2026-07-19 (censored in the 7/27 replay, classifiable now) ==")
    fresh = [r for r in cls if dt.date(2026, 7, 14) <= r["birth"] <= dt.date(2026, 7, 19)]
    print(f"  n={len(fresh)} matured={sum(r['mat'] for r in fresh)}")
    for cname, fn in (("RS<70 flat", lambda r: r["birth_rs"] < 70), ("OR-cell70", orcell(70, 0.0))):
        blocked = [r for r in fresh if fn(r)]
        FN = [r["name"] for r in blocked if r["mat"]]
        print(f"  {cname}: blocked={len(blocked)} FN={len(FN)} {FN}")

    # ---- 8. join / rescue dissection: what does "blocked" actually cost? ----
    print("\n== join / rescue dissection (ticker-overlap, intersection-over-smaller) ==")
    print("  LIVE join = overlap >= 0.5 vs a theme with a non-Retired row in the prior 7 calendar")
    print("  days (still on the active board per the recency cap) -> suppression is free.")
    print("  Ledger-only join (8-14d stale) suppresses WITHOUT live representation -> counted LOST.")

    def bset(name, bdate):
        return tkrows.get((bdate.isoformat(), name), (None, frozenset()))[1]

    # pre-index: latest row per name per date-window is expensive; build per-name dated rows once
    name_rows = collections.defaultdict(list)
    for (d, n), (stg, s) in tkrows.items():
        name_rows[n].append((D(d), stg, s))
    for v in name_rows.values():
        v.sort()

    def join_overlap(name, bdate):
        """Returns (live_target, live_ov, ledger_target, ledger_ov).

        live  = target has a non-Retired row within the prior 7 calendar days
                (= still on the active board per get_active_themes(stale_after_days=7)).
        ledger = prior 8-14 calendar days only (candidate-ledger memory; a join here
                suppresses the birth WITHOUT live board representation)."""
        bs = bset(name, bdate)
        if not bs:
            return None, 0.0, None, 0.0
        lbest, lov, gbest, gov = None, 0.0, None, 0.0
        lo14 = bdate - dt.timedelta(days=14)
        lo7 = bdate - dt.timedelta(days=7)
        for n, rows_ in name_rows.items():
            if n == name:
                continue
            cand7 = cand14 = None
            for dd, stg, s in rows_:
                if dd >= bdate:
                    break
                if stg != "Retired" and s:
                    if lo7 <= dd:
                        cand7 = s
                    elif lo14 <= dd:
                        cand14 = s
            if cand7:
                ov = len(bs & cand7) / min(len(bs), len(cand7))
                if ov > lov:
                    lov, lbest = ov, n
            elif cand14:
                ov = len(bs & cand14) / min(len(bs), len(cand14))
                if ov > gov:
                    gov, gbest = ov, n
        return lbest, lov, gbest, gov

    jcache = {r["name"]: join_overlap(r["name"], r["birth"]) for r in recs}
    nlive = sum(1 for v in jcache.values() if v[1] >= 0.5)
    nledg = sum(1 for v in jcache.values() if v[1] < 0.5 and v[3] >= 0.5)
    print(f"  all June+ births: {nlive}/{len(recs)} join a LIVE board theme at birth; "
          f"{nledg} more join only a ledger (8-14d stale) cohort")

    def rescued(r, rulefn):
        """Later June+ birth, >=0.5 overlap with r's birth set, passing rule, matured/alive."""
        bs = bset(r["name"], r["birth"])
        if not bs:
            return None
        for r2 in recs:
            if r2["birth"] <= r["birth"] or r2["name"] == r["name"] or r2["birth_rs"] is None:
                continue
            s2 = bset(r2["name"], r2["birth"])
            if not s2:
                continue
            ov = len(bs & s2) / min(len(bs), len(s2))
            ok = r2["mat"] or (r2["censored"] and r2["alive_today"])
            if ov >= 0.5 and not rulefn(r2) and ok:
                return r2["name"], (r2["birth"] - r["birth"]).days
        return None

    for rulename, rulefn in (("RS>=70 flat", lambda r: r["birth_rs"] < 70),
                             ("RS>=70 OR d5>=0", orcell(70, 0.0))):
        blocked = [r for r in cls if rulefn(r)]
        fn = [r for r in blocked if r["mat"]]
        tp = [r for r in blocked if not r["mat"]]
        print(f"\n  [{rulename}] blocked={len(blocked)} -> FN(matured)={len(fn)}, TP(corpse)={len(tp)}")
        lost = 0
        for r in fn:
            ln, lov, gn, gov = jcache[r["name"]]
            resc = rescued(r, rulefn)
            if lov >= 0.5:
                tag = f"JOINS LIVE '{ln[:36]}' ov={lov:.2f} (free)"
            elif resc:
                tag = f"RESCUED by '{resc[0][:36]}' +{resc[1]}d (delay)"
            elif gov >= 0.5:
                lost += 1
                tag = f"ledger-only join '{gn[:30]}' ov={gov:.2f} — counted LOST (no live representation)"
            else:
                lost += 1
                tag = "LOST (real cost)"
            print(f"    FN {r['name'][:48]:<48} rs={r['birth_rs']:>5.1f} d5={r['d5pre']}: {tag}")
        tp_join = sum(1 for r in tp if jcache[r['name']][1] >= 0.5)
        tp_abs = sum(1 for r in tp if r["absorbed"])
        print(f"    TP corpses: {len(tp)} (would-have-joined anyway: {tp_join}; absorbed-in-life: {tp_abs})")
        print(f"    => real lost maturers: {lost} of {len(blocked)} blocked")

    # ---- 9. stabilisation: which day is birth RS measured ----
    print("\n== stored rs_avg stabilisation (context for 'which day measured') ==")
    d12 = []
    for name, rows in themes.items():
        if len(rows) >= 2:
            a, b = ffloat(rows[0]["rs"]), ffloat(rows[1]["rs"])
            if a is not None and a >= 5 and b is not None and b >= 5:
                d12.append(abs(b - a))
    print(f"  valid day1 vs day2 |delta|: n={len(d12)} median={med(d12)} "
          f"p90={round(sorted(d12)[int(.9*len(d12))],1)}")
    print("  (member-level birth-day RS is the measurement used throughout; it is what the gate reads.)")


if __name__ == "__main__":
    main()
