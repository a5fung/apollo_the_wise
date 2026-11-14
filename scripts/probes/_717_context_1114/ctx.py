"""#717 context checks — loaders (a copy of _717_shape_1114/lib.load with the grade match fixed: every MODEL_PICK_GRADES
date is now the LIST NIGHT, matched on ticker + list night and cross-checked against the sheet key's fire day) and the
bar measures. ERA A ONLY; cb702/ is never opened (every input is an era-A capture of an earlier card)."""
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
TRENDF = "/Users/alvinfung/apollo_data/bv1_rank_1114/fires_trend.parquet"
WINF = "/Users/alvinfung/apollo_data/bv1_shape_1114/fires_windows.npy"
SHEET_KEYS = ("_717_pick_model_1113/sheet_model_picks.png", "_717_pick_model_1113/sheet_template_picks.png",
              "_717_reasons_1114/sheet_stack_dollar_volume_picks.png")


def ret126_of(W):
    """01_trend.py's rule on a close window: close(D) / close(D-126) - 1; the earliest bar when 120..126 exist; else NaN."""
    c = np.asarray(W[:, 3], np.float64); out = np.full(len(c), np.nan)
    for r in range(len(c)):
        x = c[r][~np.isnan(c[r])]
        if len(x) >= 120:
            out[r] = x[-1] / (x[-127] if len(x) >= 127 else x[0]) - 1
    return out


def sma200_ratio_of(W):
    """01_trend.py's rule: close(D) / mean of the last 200 closes (all that exist when >= 120; else NaN)."""
    c = np.asarray(W[:, 3], np.float64); out = np.full(len(c), np.nan)
    for r in range(len(c)):
        x = c[r][~np.isnan(c[r])]
        if len(x) >= 120:
            out[r] = x[-1] / x[-200:].mean()
    return out


def load():
    df = pd.read_parquet(CAP)
    cal = [date.fromisoformat(s) for s in open(CAP + ".cal.txt").read().split()]
    assert cal[-1] < date(2025, 1, 1)
    nights = sorted(df.ci.unique())
    f = df[df.fire].join(pd.read_parquet(MEASF), rsuffix="_m")
    assert (f.base_len == f.base_len_m).all()
    tr = pd.read_parquet(TRENDF); assert (tr.index == f.index).all()
    f = f.join(tr)
    f["Dd"] = [cal[c].isoformat() for c in f.ci]
    f["Ed"] = [cal[c + 1].isoformat() for c in f.ci]
    assert f.Dd.max() <= "2022-03-31", f.Dd.max()             # list nights end 2022-03-31 (the last fire day is 04-01, as on every earlier card)
    f["w"] = np.arange(len(f))
    WF = np.load(WINF, mmap_mode="r")
    assert len(WF) == len(f)
    WX = np.load(os.path.join(HERE, "fixtures_windows200.npy"))
    WX80 = np.load(os.path.join(REPO, "scripts/probes/_717_shape_1114/fixtures_windows.npy"))
    assert np.array_equal(WX[:, :, -80:], WX80, equal_nan=True)            # the same rows, the same bars as the shape card
    def fx(name, keys):
        a = pd.read_csv(os.path.join(PREV, name), sep="\t", dtype={"eid": str})          # the reasons card's measures
        b = pd.read_csv(os.path.join(HERE, name), sep="\t", dtype={"eid": str})          # this card's window ids (same loader, same order)
        assert len(a) == len(b) and all((a[k].astype(str) == b[k].astype(str)).all() for k in keys), name
        a["w"] = b.wid
        return a
    sc = fx("scorecard_rows.tsv", ["set", "eid", "E", "fired"])
    sc["key"] = sc.set + sc.eid
    sc["w"] = sc.w.astype(int)
    sc["ret126"] = ret126_of(WX[sc.w.to_numpy()]); sc["sma200_ratio"] = sma200_ratio_of(WX[sc.w.to_numpy()])
    assert sc.E.max() < "2025-01-01"                                  # Qullamaggie scorecard fixture (11 sessions after 2022-03, the last 2023-12, as scored by every earlier card); nothing sealed
    hi_all = fx("high_rows.tsv", ["set", "eid", "E", "ok"])
    hi = hi_all[hi_all.ok == 1].copy(); hi["w"] = hi.w.astype(int)
    hi["ret126"] = ret126_of(WX[hi.w.to_numpy()]); hi["sma200_ratio"] = sma200_ratio_of(WX[hi.w.to_numpy()])
    KEYS = {}
    for k in SHEET_KEYS:
        for line in open(os.path.join(REPO, "scripts/probes", k + ".key_do_not_show.txt")).read().splitlines():
            p = line.split("|")
            if len(p) > 2 and p[2][:2] == "20":
                KEYS[("scripts/probes/" + k, p[1])] = (p[2][:10], p[2][12:22])            # (E, D)
    gr = []
    for g in MODEL_PICK_GRADES:
        E, Dn = KEYS[(g.sheet, g.ticker)]
        assert g.list_date == Dn, g                                                       # fixture = the list night on all three sheets
        x = f[(f.ticker == g.ticker) & (f.Dd == g.list_date)]
        assert len(x) == 1 and x.Ed.iloc[0] == E, g                                       # and the fire day of the sheet key
        gr.append(dict(x.iloc[0].to_dict(), grade=g.grade, card=g.sheet_card, words=g.operator_words, sheet=g.sheet))
    gr = pd.DataFrame(gr); gr["w"] = gr.w.astype(int)
    assert len(gr) == 36
    return f, sc, hi, hi_all, gr, nights, cal, WF, WX


def measures(W, base_len):
    """Bar-size measures from bars <= D (index -1 = D). W (n,4,>=80) o/h/l/c; base_len = D - P (v1's pole top).
    TR = true range. No ADR in any denominator (the earlier card's bar-range / own-ADR cancelled itself)."""
    W = np.asarray(W, np.float64)[:, :, -80:]
    h, l, c = W[:, 1], W[:, 2], W[:, 3]
    pc = np.concatenate([np.full((len(c), 1), np.nan), c[:, :-1]], 1)
    tr = np.fmax(h - l, np.fmax(np.abs(h - pc), np.abs(l - pc)))
    ac = np.abs(c / pc - 1.0)
    bl = np.asarray(base_len, float)
    m = {}
    def base_ratio(x):                               # mean of the last 5 / mean of the base's earlier bars (P+1 .. D-5); a base with < 5 earlier bars uses the 15 sessions before the last 5
        out = np.full(len(x), np.nan)
        for r in range(len(x)):
            n = int(bl[r]) - 5 if bl[r] == bl[r] else 0
            den = x[r, -5 - n:-5] if 5 <= n <= 74 else x[r, -20:-5]
            d = np.nanmean(den) if np.isfinite(den).any() else np.nan
            out[r] = np.mean(x[r, -5:]) / d if d and d == d else np.nan
        return out
    m["tr5_base"] = base_ratio(tr)                   # B1
    m["cc5_base"] = base_ratio(ac)                   # raw only (close-to-close swing, the same windows)
    lag = np.nanmean(tr[:, -30:-10], 1)
    m["wide10"] = (tr[:, -10:] > 1.5 * lag[:, None]).sum(1).astype(float)   # B2: wide bars of the last 10 against the 20 sessions BEFORE them
    m["wide5"] = (tr[:, -5:] > 1.5 * lag[:, None]).sum(1).astype(float)
    m["tr5_prev15"] = tr[:, -5:].mean(1) / np.nanmean(tr[:, -20:-5], 1)
    m["tr10_prev20"] = tr[:, -10:].mean(1) / lag
    m["tr3_prev10"] = tr[:, -3:].mean(1) / np.nanmean(tr[:, -13:-3], 1)
    m["trmax5_med20"] = tr[:, -5:].max(1) / np.nanmedian(tr[:, -25:-5], 1)
    m["cc10_prev20"] = ac[:, -10:].mean(1) / np.nanmean(ac[:, -30:-10], 1)
    return pd.DataFrame(m)
