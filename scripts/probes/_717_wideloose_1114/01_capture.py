#!/usr/bin/env python3
"""#717 wide-and-loose: the CAPTURE (2026-11-14; offline, $0, read-only, ERA A ONLY; research, no rule changed).

Captures ONCE the last W=200 daily bars (o/h/l/c/v, NaN-padded on the left) ending on the night BEFORE the buy day:
  graded : the operator's 48 MODEL_PICK_GRADES charts (fixture date = the LIST NIGHT D; matched on ticker + D in the era-A
           capture, cross-checked against the four sheet keys; bars = cb702_pre_v2 via P.setup(), calendar asserted < 2025)
  qm     : ALL 757 Qullamaggie scorecard buys through rating.load() (NOT the 571 listed sessions — an unlisted buy is the
           likeliest loose chart). One row per candidate buy session t in the window, D = t-1. `fixed` = 1 when the buy day
           is fixed: a dated buy (E), a one-session window, or the session ratings.tsv rated (day_cleared).
`cb702/` is never opened.
    python3 scripts/probes/_717_wideloose_1114/01_capture.py > scripts/probes/_717_wideloose_1114/01_capture.out
"""
import csv, importlib.util, os, sys
from datetime import date
import numpy as np, pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__)); REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
os.chdir(REPO)
W = 200
PM = os.path.join(REPO, "scripts/probes/_717_pick_model_1113")
spec = importlib.util.spec_from_file_location("m", os.path.join(PM, "02_fit_test.py"))
M = importlib.util.module_from_spec(spec); spec.loader.exec_module(M); P = M.P
sys.path.insert(0, os.path.join(REPO, "tests/fixtures")); from breakout_list_grades import MODEL_PICK_GRADES  # noqa
sys.path.insert(0, os.path.join(REPO, "scripts/probes/_717_qm_confidence_1111")); import rating as R  # noqa
CAP = "/Users/alvinfung/apollo_data/bv1_pick_model_1113/list_eraA_4pct.parquet"
SHEET_KEYS = ("_717_pick_model_1113/sheet_model_picks.png", "_717_pick_model_1113/sheet_template_picks.png",
              "_717_reasons_1114/sheet_stack_dollar_volume_picks.png", "_717_context_1114/sheet_context_a2_dollar_volume_picks.png")


def window(arrs, D):
    out = np.full((5, W), np.nan, np.float64)
    a = max(0, D - W + 1)
    for j, x in enumerate(arrs):
        seg = np.asarray(x[a:D + 1], float); out[j, W - len(seg):] = seg
    return out


# ── graded
df = pd.read_parquet(CAP); cal = [date.fromisoformat(s) for s in open(CAP + ".cal.txt").read().split()]
assert cal[-1] < date(2025, 1, 1)
ix = {d.isoformat(): i for i, d in enumerate(cal)}
KEYS = {}
for k in SHEET_KEYS:
    for line in open(os.path.join(REPO, "scripts/probes", k + ".key_do_not_show.txt")).read().splitlines():
        p = line.split("|")
        if len(p) > 2 and p[2][:2] == "20":
            KEYS[("scripts/probes/" + k, p[1])] = (p[2][:10], p[2][12:22])
S, _ = P.setup(); D = S.D
assert D.cal[-1] < date(2025, 1, 1)
tid = {}
for k, t in enumerate(D.tickers):
    tid.setdefault(t, []).append(k)
WG, rows = [], []
for g in MODEL_PICK_GRADES:
    E, Dn = KEYS[(g.sheet, g.ticker)]
    assert g.list_date == Dn, g
    ci = ix[Dn]; assert cal[ci + 1].isoformat() == E
    x = df[(df.ticker == g.ticker) & (df.ci == ci) & df.fire]; assert len(x) == 1, g
    r = x.iloc[0]
    for k in tid[g.ticker]:
        bb, cidx = P.runner.bars_for(D, k)
        hit = np.flatnonzero(np.asarray(cidx) == ci)
        if len(hit) and abs(float(bb.c[hit[0]]) - r.close) < 1e-6 * max(1.0, r.close):
            WG.append(window((bb.o, bb.h, bb.l, bb.c, bb.v), int(hit[0]))); break
    else:
        raise AssertionError(g)
    rows.append(dict(ticker=g.ticker, D=Dn, E=E, grade=g.grade, words=g.operator_words, level=r.level, adr20=r.adr20, wid=len(WG) - 1,
                     sheet=os.path.basename(g.sheet)))
gr = pd.DataFrame(rows); assert len(gr) == 48
gr.to_csv(os.path.join(HERE, "graded_rows.tsv"), sep="\t", index=False)
np.save(os.path.join(HERE, "graded_windows200.npy"), np.stack(WG))
print(f"graded: {len(gr)} charts; grades {gr.grade.value_counts().to_dict()}")

# ── Qullamaggie's 757
RT = {(r["set"], r["eid"]): r for r in csv.DictReader(open("scripts/probes/_717_qm_confidence_1111/ratings.tsv"), delimiter="\t")}
WQ, rows = [], []
for b in R.load():
    assert b["dates"][-1] < date(2025, 1, 1)
    rt = RT[(b["set"], b["eid"])]
    ds = [d.isoformat() for d in b["dates"]]
    if b["set"] == "dated" or len(b["win"]) == 1:
        fixed_t, how = b["win"][0], ("dated" if b["set"] == "dated" else "one_session_window")
        assert len(b["win"]) == 1
    elif rt["day_cleared"]:
        fixed_t, how = ds.index(rt["day_cleared"]), "rated_session"
    else:
        fixed_t, how = None, "window_not_fixed"
    for t in b["win"]:
        Dn = t - 1
        lvl = float(rt["buy_point_split_adjusted"]) if rt["buy_point_split_adjusted"] and rt["day_cleared"] == ds[t] else np.nan
        WQ.append(window((b["o"], b["h"], b["l"], b["c"], b["v"]), Dn))
        rows.append(dict(set=b["set"], eid=b["eid"], ticker=b["ticker"], sym=b["sym"], E=ds[t], D=ds[Dn], tier=rt["tier"], reason=rt["reason"],
                         big=int(b["row"].get("big_winner") == "1"), fixed=int(fixed_t == t), how=how, level=lvl, nbars=Dn + 1,
                         win_len=len(b["win"]), wid=len(WQ) - 1))
qm = pd.DataFrame(rows)
qm.to_csv(os.path.join(HERE, "qm_rows.tsv"), sep="\t", index=False)
np.save(os.path.join(HERE, "qm_windows200.npy"), np.stack(WQ))
key = qm.set + qm.eid
print(f"qm: {len(qm)} candidate sessions of {key.nunique()} buys; buy day fixed for {key[qm.fixed == 1].nunique()} "
      f"({qm[qm.fixed == 1].how.value_counts().to_dict()}); not fixed {key.nunique() - key[qm.fixed == 1].nunique()} buys")
f1 = qm[qm.fixed == 1]
print("fixed-day buys by tier:", f1.tier.value_counts().to_dict(), "| big winners:", int(f1.big.sum()), "| E range", qm.E.min(), qm.E.max())
print("bars to the night before (fixed): min", int(f1.nbars.min()), "under 60:", int((f1.nbars < 60).sum()), "under 189:", int((f1.nbars < 189).sum()))
lv = f1[f1.level.notna()]
cl = np.array([WQ[w][3, -1] for w in lv.wid])
print("level / close(D) on fixed rows with a level: n", len(lv), "min %.3f median %.3f max %.3f" % (np.min(lv.level / cl), np.median(lv.level / cl), np.max(lv.level / cl)))
