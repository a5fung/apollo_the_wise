"""#687 INDEPENDENT CHECK (4) — drive check_walk.py's walker over every fill; compare per trade with arms_per_trade.tsv;
hand-walk logs for named trades. Writes check_exit.txt, check_walks.txt, check_mine_per_trade.tsv."""
import collections, csv, io, contextlib
from datetime import date, time, timedelta
from pathlib import Path
import check_walk as CW
HERE = Path(__file__).resolve().parent
with contextlib.redirect_stdout(io.StringIO()):
    daily, m_entry, m_held, fills, theirs = CW.main()
OX = open(HERE / "check_exit.txt", "w")
def P(*a):
    s = " ".join(str(x) for x in a); print(s); OX.write(s + "\n")
ARMS = ("A0", "A1", "D10", "T20_hs", "S20_hs", "T20_be", "S20_be")
# entry-label-only differences
lab = [k for k in theirs if k in fills and fills[k][0]["kind"] != theirs[k]["kind"]]
px_same = [k for k in lab if abs(fills[k][0]["px"] - float(theirs[k]["entry"])) < 1e-6]
P(f"# #687 CHECK (4) EXIT — own walker. Entry: {len(lab)} campaigns differ only in the fill LABEL; price identical on {len(px_same)} of them "
  f"(a bar OPENING exactly at the ORB high / the limit: the study labels it 'cross'/'limit_pullback' (fill_at_open False), I label it an open fill)")
# day 0 funnel over all fills
d0 = collections.Counter(); mine = {}
for k, (e, H, L) in fills.items():
    T, D = k
    try:
        R, fin, xd, info = CW.walk("D0ONLY", T, D, e, H, L, daily[T], m_entry[k], m_held)
        d0["settled_d0" if fin == "stop_hit" else "reached_d1"] += 1
    except CW.Abstain as ex:
        d0["abstain:" + str(ex).split(":")[0]] += 1
P(f"   DAY 0 over {len(fills)} fills (mine): {dict(sorted(d0.items()))}  | doc: 84 abstain (53 straddle, 22 stop+BE, 6 fill-bar stop+target, 3 stop+target), 651 settled, 882 reached day 1")
# all arms on every TSV campaign
res = {a: {} for a in ARMS}; abst = collections.Counter()
for k in theirs:
    T, D = k
    e, H, L = fills[k]
    for a in ARMS:
        try:
            R, fin, xd, info = CW.walk(a, T, D, e, H, L, daily[T], m_entry[k], m_held)
            res[a][k] = (R, fin, xd, info)
        except CW.Abstain as ex:
            res[a][k] = (None, "abstain:" + str(ex), None, {}); abst[a] += 1
P(f"   abstains per arm (mine) {dict(abst)}  | doc: 28 unreadable later days, identical in every arm")
cmp_ = {}
for a in ARMS:
    c = collections.Counter(); bad = []
    for k, r in theirs.items():
        mR = res[a][k][0]
        tR = float(r[f"{a}_R"]) if r[f"{a}_status"] == "settled" and r[f"{a}_R"] else (float(r[f"{a}_markR"]) if r[f"{a}_markR"] else None)
        if mR is None and tR is None:
            c["both_none"] += 1
        elif mR is None or tR is None:
            c["one_none"] += 1; bad.append((k, mR, tR, res[a][k][1], r[f"{a}_final"]))
        elif abs(mR - tR) <= 0.005:
            c["match"] += 1
        else:
            c["differ"] += 1; bad.append((k, round(mR, 3), round(tR, 3), res[a][k][1], r[f"{a}_final"], str(res[a][k][2]), r[f"{a}_exit_day"]))
    cmp_[a] = bad
    P(f"   {a:7s} per-trade vs TSV: {dict(c)}; sum|diff| {sum(abs((x[1] or 0) - (x[2] or 0)) for x in bad):.2f}R; first {bad[:6]}")
# write my per-trade
with open(HERE / "check_mine_per_trade.tsv", "w") as fh:
    fh.write("ticker|entry_day|block|" + "|".join(f"{a}_R|{a}_final|{a}_exit" for a in ARMS) + "\n")
    for k in sorted(theirs, key=lambda k: (k[1], k[0])):
        fh.write(f"{k[0]}|{k[1]}|{theirs[k]['block']}|" + "|".join(
            f"{'' if res[a][k][0] is None else round(res[a][k][0], 6)}|{res[a][k][1]}|{res[a][k][2]}" for a in ARMS) + "\n")
# the day-0 partial-then-breakeven trades: identical in every arm in the study; under T20_hs/S20_hs the floor is the hard stop
d0pb = []
for k, (e, H, L) in fills.items():
    T, D = k
    try:
        R, fin, xd, info = CW.walk("A0", T, D, e, H, L, daily[T], m_entry[k], m_held)
    except CW.Abstain:
        continue
    if fin == "stop_hit" and xd == D and info.get("partial_day") == D:
        R2, fin2 = CW.d0_hs_continuation(T, D, e, H, L, daily[T], m_entry[k])
        d0pb.append((k, round(R, 3), None if R2 is None else round(R2, 3), fin2))
P(f"   DAY-0 trades that fired the +8 partial and were then stopped at breakeven ON day 0 (treated as identical to A0 in every runner arm): {len(d0pb)}; "
  f"under the _hs definition (floor = hard stop after the partial) they would instead return: {d0pb[:20]}; "
  f"sum of (hs - A0) over them {sum((x[2] or x[1]) - x[1] for x in d0pb):+.2f}R")
OX.close()


