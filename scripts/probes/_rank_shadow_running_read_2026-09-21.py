import sys, csv, statistics as st
sys.path.insert(0, "/Users/alvinfung/apollo_the_wise")
from scripts.alert_rank_shadow_running_read import (
    confidence_label, score_both_directions, CohortRead, render_running_read)

F = lambda s: None if s == "" else float(s)
rows = []
for r in csv.reader(open("/tmp/rev3/05_recomputed.psv"), delimiter="|"):
    rows.append(dict(
        tk=r[0], date=r[1], adr=F(r[2]), high=r[3]=="t", filled=r[4]=="t", tier=r[5],
        c_eod=F(r[6]), pool_eod=int(r[7]), c_945=F(r[8]), pool_945=int(r[9]),
        open0=F(r[10]), low0=F(r[11]), sess=int(r[12]),
        mh5=F(r[13]), mh20=F(r[14]), r5=F(r[15]), r20=F(r[16]), minlow=F(r[17])))

n_sessions = len({r["date"] for r in rows})
print("POPULATION")
print(f"  shadow rows out-of-sample (alert_date > 2026-08-16): {len(rows)} over {n_sessions} sessions")
print(f"  filled (traded)      : {sum(r['filled'] for r in rows)}")
print("  NOTE: mi_ep_missed_outcomes holds only NOT-ENTERED alerts (missed_outcomes.py:1-3);\n        20 of these 32 rows have a row there. This probe recomputes ALL 32 from mi_daily_closes\n        with that module's own formula, so the filled rows are no longer structurally excluded.")
print(f"  5d-matured (>=6 sessions of bars from d0): {sum(1 for r in rows if r['sess']>=6)}")
print(f" 20d-matured (>=21 sessions of bars from d0): {sum(1 for r in rows if r['sess']>=21)}")
print(f"  confidence: {confidence_label(n_sessions)}")

TOL = 1e-9
def adrx(v, adr): return None if (v is None or not adr) else v/adr
for r in rows:
    r["x5"], r["x20"] = adrx(r["mh5"], r["adr"]), adrx(r["mh20"], r["adr"])
    # loser bar, as the module names it: broke the EP-day low in d+1..d+5
    r["loser"] = (r["minlow"] is not None and r["low0"] is not None and r["minlow"] < r["low0"])

BAR = 8.0
def report(tag, key, pool_key, matured_min, xkey):
    pop = [r for r in rows if r["sess"] >= matured_min and r[xkey] is not None]
    elig = [r for r in pop if r[pool_key] >= 2]
    top = [r for r in pop if r[key] is not None and r[key] <= 0.25 + TOL]
    rest = [r for r in pop if r[key] is not None and r[key] > 0.25 + TOL]
    print(f"\n=== {tag} ===")
    print(f"  scored population n={len(pop)} (matured); quartile-ELIGIBLE (day pool>=2) n={len(elig)}; "
          f"structurally ineligible (pool=1 -> rank 0.5) n={len(pop)-len(elig)}")
    for nm, c in (("TOP-QUARTILE (composite<=0.25)", top), ("REST OF POOL", rest)):
        if not c:
            print(f"  {nm}: n=0"); continue
        w = sum(1 for r in c if r[xkey] >= BAR); l = sum(1 for r in c if r["loser"])
        xs = sorted(r[xkey] for r in c)
        print(f"  {nm}: n={len(c)} | tail>={BAR}xADR: {w}/{len(c)} | broke-d0-low: {l}/{len(c)} | "
              f"median {st.median(xs):.2f}x | best {max(xs):.2f}x")
    if top and rest:
        cand = CohortRead(len(top), sum(1 for r in top if r[xkey] >= BAR), sum(1 for r in top if r["loser"]))
        base = CohortRead(len(rest), sum(1 for r in rest if r[xkey] >= BAR), sum(1 for r in rest if r["loser"]))
        print("  score_both_directions: " + score_both_directions(cand, base))
        print("  " + render_running_read(n_sessions, cand, base))
    tails = [r for r in pop if r[xkey] >= BAR]
    for r in sorted(tails, key=lambda r: -r[xkey]):
        print(f"    TAIL: {r['tk']} {r['date']} {r[xkey]:.2f}xADR filled={r['filled']} "
              f"composite={r[key]:.4f} pool={r[pool_key]}")

report("EOD rank, 5-day horizon", "c_eod", "pool_eod", 6, "x5")
report("EOD rank, 20-day horizon", "c_eod", "pool_eod", 21, "x20")
report("AS-OF-09:45 rank, 5-day horizon", "c_945", "pool_945", 6, "x5")
report("AS-OF-09:45 rank, 20-day horizon", "c_945", "pool_945", 21, "x20")

print("\n=== TOP ADR MULTIPLES, 5d matured, all 32-row population ===")
for r in sorted([r for r in rows if r["sess"]>=6], key=lambda r: -(r["x5"] or 0))[:8]:
    print(f"  {r['tk']} {r['date']} {r['x5']:.2f}x filled={r['filled']} tier={r['tier']} "
          f"c_eod={r['c_eod']:.3f} c_945={r['c_945']:.3f} pool={r['pool_eod']}")

print("\n=== QUARTILE MEMBERSHIP (5d-matured population, n=27) ===")
for r in sorted([r for r in rows if r["sess"]>=6], key=lambda r:(r["date"],r["tk"])):
    tq_e = "TOP" if r["c_eod"]<=0.25+TOL else "rest"
    tq_9 = "TOP" if r["c_945"]<=0.25+TOL else "rest"
    print(f"  {r['tk']:5s} {r['date']} pool={r['pool_eod']} eod={r['c_eod']:.4f}({tq_e}) "
          f"0945={r['c_945']:.4f}({tq_9}) x5={r['x5']:.2f} brokeLow={r['loser']} filled={r['filled']}")
print("\n=== rows NOT 5d-matured (bars end 2026-09-18) ===")
for r in rows:
    if r["sess"]<6: print(f"  {r['tk']} {r['date']} sessions_avail={r['sess']}")
