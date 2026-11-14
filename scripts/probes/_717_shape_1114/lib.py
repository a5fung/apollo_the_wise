"""#717 shape checks — shared loaders (the 02_score.py pattern of _717_reasons_1114, same files, same bridges) + bar windows.
Windows: (n, 4, 80) float32 o/h/l/c ending on the watch night D (index -1 = D). ERA A ONLY; cb702/ is never opened."""
import os, sys
from datetime import date
import numpy as np, pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
PREV = os.path.join(REPO, "scripts/probes/_717_reasons_1114")
sys.path.insert(0, os.path.join(REPO, "tests/fixtures"))
from breakout_list_grades import MODEL_PICK_GRADES  # noqa: E402
CAP = "/Users/alvinfung/apollo_data/bv1_pick_model_1113/list_eraA_4pct.parquet"
MEASF = "/Users/alvinfung/apollo_data/bv1_reasons_1114/fires_measures.parquet"
WINF = "/Users/alvinfung/apollo_data/bv1_shape_1114/fires_windows.npy"


def load():
    """-> f (era-A fires), sc (scorecard sessions), hi (56 listed High), gr (36 grades), nights, cal; each with column
    `w` = row of its window array (WF for f / gr, WX for sc / hi) and the previous card's measures (u50, s50_chg10, ...)."""
    df = pd.read_parquet(CAP)
    cal = [date.fromisoformat(s) for s in open(CAP + ".cal.txt").read().split()]
    assert cal[-1] < date(2025, 1, 1)
    nights = sorted(df.ci.unique())
    f = df[df.fire].join(pd.read_parquet(MEASF), rsuffix="_m")
    assert (f.base_len == f.base_len_m).all()
    f["Dd"] = [cal[c].isoformat() for c in f.ci]
    f["Ed"] = [cal[c + 1].isoformat() for c in f.ci]
    f["w"] = np.arange(len(f))
    WF = np.load(WINF, mmap_mode="r")
    assert len(WF) == len(f)
    WX = np.load(os.path.join(HERE, "fixtures_windows.npy"))
    def fx(name, keys):
        a = pd.read_csv(os.path.join(PREV, name), sep="\t", dtype={"eid": str})          # the previous card's measures
        b = pd.read_csv(os.path.join(HERE, name), sep="\t", dtype={"eid": str})          # this card's window ids (same loader, same order)
        assert len(a) == len(b) and all((a[k].astype(str) == b[k].astype(str)).all() for k in keys), name
        a["w"] = b.wid
        return a
    sc = fx("scorecard_rows.tsv", ["set", "eid", "E", "fired"])
    sc["key"] = sc.set + sc.eid
    sc["w"] = sc.w.astype(int)
    hi_all = fx("high_rows.tsv", ["set", "eid", "E", "ok"])
    hi = hi_all[hi_all.ok == 1].copy(); hi["w"] = hi.w.astype(int)
    # the key files are the truth for each graded chart's two dates: "letter|ticker|E (D)|..."
    KEYS = {}
    for k in ("_717_pick_model_1113/sheet_model_picks.png", "_717_pick_model_1113/sheet_template_picks.png", "_717_reasons_1114/sheet_stack_dollar_volume_picks.png"):
        for line in open(os.path.join(REPO, "scripts/probes", k + ".key_do_not_show.txt")).read().splitlines():
            p = line.split("|")
            if len(p) > 2 and p[2][:2] == "20":
                KEYS[("scripts/probes/" + k, p[1])] = (p[2][:10], p[2][12:22])            # (E, D)
    gr = []
    for g in MODEL_PICK_GRADES:
        E, Dn = KEYS[(g.sheet, g.ticker)]
        # FIXTURE QUIRK: `list_date` is the list night D on the two 11-13 sheets but the fire day E on the 11-14 sheet
        assert g.list_date == (E if g.sheet.endswith("sheet_stack_dollar_volume_picks.png") else Dn), g
        x = f[(f.ticker == g.ticker) & (f.Dd == Dn) & (f.Ed == E)]
        assert len(x) == 1, g
        gr.append(dict(x.iloc[0].to_dict(), grade=g.grade, card=g.sheet_card, words=g.operator_words, sheet=g.sheet))
    gr = pd.DataFrame(gr); gr["w"] = gr.w.astype(int)
    return f, sc, hi, hi_all, gr, nights, cal, WF, WX


def zigzag(h, l, thr):
    """Swing points by a reversal threshold `thr` (price units), bars in time order. A swing HIGH is the running high of an
    up-leg, fixed once a later low sits >= thr under it; a swing LOW is the running low of a down-leg, fixed once a later
    high sits >= thr over it. Returns [(index, price, +1 high / -1 low), ...] in time order; the LAST entry is the still
    running extreme of the current leg (unconfirmed). Empty when the series never moves thr."""
    n = len(h)
    hi_i = lo_i = 0
    mode = 0
    piv = []
    for i in range(1, n):
        if mode == 0:
            if h[i] > h[hi_i]:
                hi_i = i
            if l[i] < l[lo_i]:
                lo_i = i
            if h[hi_i] - l[lo_i] >= thr and hi_i != lo_i:
                if lo_i < hi_i:
                    piv.append((lo_i, float(l[lo_i]), -1)); mode = 1
                else:
                    piv.append((hi_i, float(h[hi_i]), 1)); mode = -1
        elif mode == 1:                              # up-leg: hi_i = its running high
            if h[i] > h[hi_i]:
                hi_i = i
            elif h[hi_i] - l[i] >= thr:
                piv.append((hi_i, float(h[hi_i]), 1)); mode = -1; lo_i = i
        else:                                        # down-leg: lo_i = its running low
            if l[i] < l[lo_i]:
                lo_i = i
            elif h[i] - l[lo_i] >= thr:
                piv.append((lo_i, float(l[lo_i]), -1)); mode = 1; hi_i = i
    if mode == 1:
        piv.append((hi_i, float(h[hi_i]), 1))
    elif mode == -1:
        piv.append((lo_i, float(l[lo_i]), -1))
    return piv


ZZ_LOOK = 60


def measures(W, adr, level):
    """Every shape measure, in daily ranges (u = ADR20(D) x the buy level), from bars <= D. W (n,4,80) o/h/l/c; -> DataFrame."""
    W = np.asarray(W, np.float64); adr = np.asarray(adr, float); level = np.asarray(level, float)
    h, l, c = W[:, 1], W[:, 2], W[:, 3]
    u = adr * level
    m = {}
    for n in (10, 15, 20):
        m[f"hl{n}"] = (h[:, -n:].max(1) - l[:, -n:].min(1)) / u           # the high-low box of the last n sessions
    for n in (40, 60, 80):
        m[f"off{n}"] = (np.nanmax(h[:, -n:], 1) - level) / u              # the buy level under the n-session high
    for n in (10, 15):
        m[f"near{n}"] = ((level[:, None] - c[:, -n:]) / u[:, None] <= 2.0).sum(1)   # closes of the last n within 2 daily ranges of the level
    for k in (1.5, 2.0, 3.0):
        lh, ll, nsw = np.full(len(u), np.nan), np.full(len(u), np.nan), np.zeros(len(u), int)
        for r in range(len(u)):
            hh, lw = h[r, -ZZ_LOOK:], l[r, -ZZ_LOOK:]
            ok = ~np.isnan(hh)
            piv = zigzag(hh[ok], lw[ok], k * u[r])
            H = [p[1] for p in piv if p[2] == 1]; L = [p[1] for p in piv if p[2] == -1]
            nsw[r] = len(piv)
            if len(H) >= 2:
                lh[r] = (H[-1] - H[-2]) / u[r]                            # < 0: the latest swing high (incl. the running one) is LOWER
            if len(L) >= 2:
                ll[r] = (L[-1] - L[-2]) / u[r]                            # < 0: the latest swing low is LOWER
        m[f"lh_{k}"], m[f"ll_{k}"], m[f"nsw_{k}"] = lh, ll, nsw
    return pd.DataFrame(m)
