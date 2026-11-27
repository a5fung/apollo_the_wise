"""Stage 1e: era-B volume underflow ladder (prereg 1.3 / critique 5), outcome-free, era-B nights D 2022-04-01 .. 2024-10-03, sealed copy only.
Rung 1 (literal): name-nights that are pool candidates (admitted type, 20+ sessions, 86 consecutive, derived raw price >= $2, r63 present) failing the $5M dollar-volume
  floor with a zero-volume row in the 20-session window.
Rung 2: rung 1 AND the median of the NON-ZERO-volume sessions' close x volume would pass $5M (the floor fails only because of the zeros).
Rung 3: rung 2 AND every other gate passes (failed == ['universe'] from the live v1_gates with the name's rank taken by adding it to the night's real pool).
Denominator: era-B live-list rows (all rows, not only break rows). Raw-volume sizing line: unavailable under A1."""
import json
from lib import *
from collections import Counter
S = setup_store("B"); D = S.D; facts = G["facts"]; cal = D.cal
nights = [i for i, d in enumerate(cal) if d >= date(2022, 4, 1) and i + 61 <= len(cal) - 1]
nset = set(nights)
live = pd.read_parquet(OUT_DATA / "bws1124_eraB_list_ctx.parquet"); live = live[live.failed == ""]
n_live = len(live)
W = cb.DOLLAR_VOL_WINDOW
cand = defaultdict = None
from collections import defaultdict
bynight = defaultdict(list); r1 = r2 = 0
for k, t in enumerate(D.tickers):
    f = facts[k]; a, b = f["a"], f["b"]; c, v = D.c[a:b], D.v[a:b]; cidx = f["cidx"]
    ok_type, why = bv.security_admitted(t, S.types.get(t), S.etv_names.get(t))
    if why == "ticker": continue
    n = b - a
    if n < W: continue
    zero = (v <= 0).astype(np.int64); cz = np.concatenate([[0], np.cumsum(zero)])
    for li in np.flatnonzero((cidx >= nights[0]) & (cidx <= nights[-1])):
        ci = int(cidx[li])
        if ci not in nset or li + 1 < W: continue
        zc = cz[li + 1] - cz[li + 1 - W]
        if zc == 0 or not f["hist"][li] or f["brk"][li] or np.isnan(f["r63"][li]): continue
        if not (f["raw"][li] >= bv.MIN_PRICE) or f["dv"][li] >= bv.MIN_DOLLAR_VOL: continue
        r1 += 1
        w = slice(li + 1 - W, li + 1); nz = v[w] > 0
        med = float(np.median((c[w] * v[w])[nz])) if nz.any() else 0.0
        if med >= bv.MIN_DOLLAR_VOL:
            r2 += 1; bynight[ci].append((k, li, float(c[li]), ok_type))
r3 = 0; bylevel = Counter(); bylevel_all = Counter(); pairs3 = []
lvl = lambda p: "<$10" if p < 10 else ("$10-100" if p < 100 else ("$100-1000" if p < 1000 else ">=$1000"))
for ci, lst in bynight.items():
    members, _ = R.night_members(S, facts, ci, G["rows_at"])
    mm = members + [{"r21": None if np.isnan(facts[k]["r21"][li]) else float(facts[k]["r21"][li]), "r63": float(facts[k]["r63"][li]),
                     "r126": None if np.isnan(facts[k]["r126"][li]) else float(facts[k]["r126"][li])} for k, li, _, _ in lst]
    rb = cb.cross_section_one_date([m["r21"] for m in mm], [m["r63"] for m in mm], [m["r126"] for m in mm], [None] * len(mm))[0][len(members):]
    for (k, li, cadj, ok_type), rbi in zip(lst, rb):
        bylevel_all[lvl(cadj)] += 1
        if rbi is None or rbi < bv.RS_MIN or not ok_type: continue
        bars, cidx = runner.bars_for(D, k)
        g = bv.v1_gates(bars, li, rs_best=rbi, raw_close=float(facts[k]["raw"][li]), cidx=cidx)
        if g["failed"] == ["universe"]:
            r3 += 1; bylevel[lvl(cadj)] += 1
L = [f"era-B live-list rows (denominator, all nights): {n_live:,}",
     f"rung 1 literal (pool candidate, fails the $5M floor, zero-volume row in the 20-session window): {r1:,} = {100 * r1 / n_live:.2f}% of list rows",
     f"rung 2 (and would pass the floor on the non-zero sessions only): {r2:,} = {100 * r2 / n_live:.2f}%; by adjusted price level {dict(bylevel_all)}",
     f"rung 3 (and every other gate passes, rank taken in the real night's pool): {r3:,} = {100 * r3 / n_live:.2f}%; by adjusted price level {dict(bylevel)}",
     f"TAG 'era-B population thinned by volume underflow': rung 1 {'>' if r1 > 0.01 * n_live else '<='} 1%, rung 2 {'>' if r2 > 0.01 * n_live else '<='} 1%, rung 3 {'>' if r3 > 0.01 * n_live else '<='} 1%",
     "rung that sets the tag (reading recorded): rung 3, the prereg sentence's 'failing only the dollar-volume half' with every other membership test passing; " +
     ("the rungs AGREE" if (r1 > 0.01 * n_live) == (r3 > 0.01 * n_live) else "THE RUNGS DISAGREE - flagged"),
     "raw-volume sizing line: UNAVAILABLE under A1 (the pull is discarded and never opened)"]
print("\n".join(L)); (HERE / "1e_underflow.txt").write_text("\n".join(L) + "\n")
json.dump(dict(n_live=n_live, rung1=r1, rung2=r2, rung3=r3), open(HERE / "1e_underflow_result.json", "w"))
