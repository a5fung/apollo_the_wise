"""#687 INDEPENDENT CHECK (6b) — would a BROKEN replay give the same headline? Mutations of MY walker (not the study's code):
M0 = my faithful walker; M1 = entry-day close included in the trail (off-by-one); M2 = no line-test minute bars (daily grain
only, as if round 2 had failed); M3 = depth distance mis-scaled (ADR x 0.1: a 0.1-ADR stop); M4 = the population minus the
look-ahead: trades whose full-day volume was < 3x at... (not computable) -> replaced by: drop the 217 runner trades.
Writes check_broken.txt."""
import io, contextlib, collections
from datetime import date
from pathlib import Path
import check_walk as CW
HERE = Path(__file__).resolve().parent
with contextlib.redirect_stdout(io.StringIO()):
    daily, m_entry, m_held, fills, theirs = CW.main()
O = open(HERE / "check_broken.txt", "w")
def P(*a):
    s = " ".join(str(x) for x in a); print(s); O.write(s + "\n")
ARMS = ("A0", "A1", "D10", "T20_be")
def run(held, label, adr_scale=1.0):
    orig = CW.adr20
    if adr_scale != 1.0:
        CW.adr20 = lambda db, before: (orig(db, before) or 0) * adr_scale or None
    res = {a: {} for a in ARMS}
    for k in theirs:
        e, H, L = fills[k]
        for a in ARMS:
            try:
                res[a][k] = CW.walk(a, k[0], k[1], e, H, L, daily[k[0]], m_entry[k], held)[0]
            except CW.Abstain:
                res[a][k] = None
    CW.adr20 = orig
    paired = [k for k in theirs if all(res[a][k] is not None for a in ARMS)]
    out = {}
    for blk in ("ALL", "DISC", "HELD"):
        ks = [k for k in paired if blk == "ALL" or theirs[k]["block"] == blk]
        d = {a: sum(res[a][k] - res["A0"][k] for k in ks) for a in ARMS[1:]}
        nd = sum(1 for k in ks if abs(res["D10"][k] - res["A0"][k]) > 0.005 or abs(res["A1"][k] - res["A0"][k]) > 0.005)
        out[blk] = d
        P(f"   {label:34s} {blk:4s} n={len(ks):4d} A0 {sum(res['A0'][k] for k in ks):+8.2f} | A1-A0 {d['A1']:+7.2f} D10-A0 {d['D10']:+7.2f} "
          f"D10-A1 {d['D10'] - d['A1']:+7.2f} T20_be-A0 {d['T20_be']:+7.2f} | trades where A1/D10 differ {nd}")
    return res
P("# #687 CHECK (6b) MUTATIONS of my (verified-identical) walker — which breakages would move the headline?")
r0 = run(m_held, "M0 faithful")
CW.MUT_D0_CLOSE = True
run(m_held, "M1 entry-day close in the trail")
CW.MUT_D0_CLOSE = False
run({}, "M2 no line-test minute bars (daily)")
run(m_held, "M3 depth stop at 0.1 ADR", adr_scale=0.1)
run(m_held, "M3b depth stop at 10 ADR (~close-only)", adr_scale=10.0)
O.close()
