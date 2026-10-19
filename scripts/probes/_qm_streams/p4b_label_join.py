#!/usr/bin/env python3
"""#702 P4b step 5 - label join: which level did he draw? ($0: local files only; no model, API or network call).

Input (used AS GIVEN, no row re-scored, widened or dropped): QM/vision/p4b_label_lines.tsv - 93 lines he drew, on 60 bases.
Line prices are AS SHOWN ON THE SCREEN DATE; this script converts them to the scale of the bars the frozen module ran on.

Per base (ticker|pole date):
  1. PRICE SCALE. r(screen) = raw close / split-adjusted close on the last bar <= the screen date (`Series.fac`, the same array the
     module ran on; cross-checked against `vision_score.series_asof`). bar-scale price = screen price / r. Alpaca era: the
     split-adjusted bars as fetched. The one post-2022-06 base (CVNA 2023-01-26) uses the Polygon export, where r = the product of
     the `cb702_splits.psv` ratios dated after the screen (CVNA's 2026 5:1 -> r = 5), exactly `series_asof`'s factor.
  2. COMPARISON NIGHT = the last C0 watch night <= the screen date whose base_id == the base (ext_c0's Alpaca loader, its watch-night
     evaluation = `Series.night`, which calls `cb.explain_watch`; never a hand-recomputed level). Comparison session = the next bar
     (the module acts at i+1). No such night -> `no_watch_night`, row kept. Polygon base: `cb.explain_watch` on the Polygon bars at the
     night the production watch table lists (asserted equal to its four pivots); the universe / identity gates are NOT re-run there.
  3. HIS LINE'S VALUE at the comparison session: a straight line through its two end points in SESSION INDEX (dates -> index of the
     first bar on/after the date, via searchsorted on the bars' own dates), evaluated at index i+1. A `level` line = the mean of
     its two prices (slope still reported from the end points). Slope = (p2 - p1) / (s2 - s1) / p1, in % per session;
     |slope| < 0.1 %/session = flat.
  4. CANDIDATE LEVELS on that night: pivot_k5, pivot_k10, pivot_full, pivot_tl (as the module returns them; pivot_tl is already
     projected to i+1) plus three settled-high variants over the SAME window as pivot_full, (pole top P, night i], i.e. sessions
     P+1..i: highest CLOSE (high_close), highest body top max(open, close) (high_body), second-highest HIGH (high_2nd; the second bar
     in descending order, so a tie for the top counts).
  5. MATCH: the nearest candidate to his line's value within 1 / 2 / 3 %. Equal-price ties (k5 = k10 = full is common in a tight
     base) are NOT resolved by chance: every candidate within the tolerance is kept in `match_set_*pct`, and `match_*pct` is the
     nearest by a stated rule: candidates within 0.1 % of the nearest one's price are tied and the broadest window wins
     (priority full > k10 > k5 > tl > high_close > high_body > high_2nd). `match_module_*pct` = the same restricted to the four
     module levels.
  6. CHARACTER features of that night + his line's slope, and the number of base highs above his line (per session: each base high
     in (P, i] against the line's value AT THAT session).
  7. ADR distance = (pivot_full - L) / pivot_full / adr20   (adr20 is a fraction: 0.129 = 12.9 %). Positive = his line sits below
     pivot_full by that many ADRs (the size of the wick he ignored).
  Primary line of a base = among its top / level lines the one minimising |end session index - (i+1)|; ties -> bar_verified, then
  the longer span. Bases with only bottom lines keep a row with `primary_role = none`.

    python p4b_label_join.py [--out DIR]
Outputs (OUT = QM/vision/p4b_labels): labels_p4b.tsv (one row per base), lines_p4b.tsv (every drawn line, converted),
summary_p4b_labels.txt, spot/*.png (five spot-check images).
"""
import argparse
import collections
import datetime as dt
import json
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import ext_c0  # noqa: E402  (adds the repo + _cb_backtest to sys.path; read-only on the module)
import vision_score as vsc  # noqa: E402

cb = ext_c0.cb
QM = vsc.QM
CB = vsc.CB
EXT = f"{QM}/ext_2016_2022"
VIS = f"{QM}/vision"
OUT = f"{VIS}/p4b_labels"
POLY = f"{CB}/daily_closes_all.csv.gz"
SPLITS = f"{CB}/cb702_splits.psv"
WATCH = f"{CB}/out/watch.tsv.gz"

CAND = ["pivot_full", "pivot_k10", "pivot_k5", "pivot_tl", "high_close", "high_body", "high_2nd"]   # tie priority, broadest first
MODULE = CAND[:4]
TOLS = (0.01, 0.02, 0.03)
TIE = 0.001                       # candidates within 0.1 % of the nearest one's price are "the same level"
FLAT = 0.1                        # |slope| < 0.1 % per session = flat
BACK = 60                         # nights searched back from the screen date
FEATS = ["base_len", "base_depth", "tightening_ratio", "tl_slope_pct", "tl_interior_touches", "retrace", "higher_lows",
         "range_recent5", "range_early5", "adr20"]


# ───────────────────────────── helpers ─────────────────────────────
def sess(d_arr, date_str):
    """index of the first bar on / after the date (exact for a session date)."""
    return int(np.searchsorted(d_arr, dt.date.fromisoformat(date_str).toordinal(), "left"))


def line_at(role, p1, p2, s1, s2, j):
    """his line's price (bar scale in -> bar scale out) at session index/indices j."""
    j = np.asarray(j, dtype=float)
    if role == "level" or s2 == s1:
        return np.full(j.shape, (p1 + p2) / 2.0)
    return p1 + (p2 - p1) * (j - s1) / (s2 - s1)


def slope_pct(p1, p2, s1, s2):
    return 0.0 if s2 == s1 else (p2 - p1) / (s2 - s1) / p1 * 100.0


def slope_class(s):
    return "flat" if abs(s) < FLAT else ("falling" if s < 0 else "rising")


def pick(L, cands, names, tol):
    """-> (primary label, set of names within tol). See the module docstring, item 5."""
    pr = {n: cands[n] for n in names if cands.get(n) is not None and np.isfinite(cands[n])}
    if not pr:
        return "none", []
    within = [n for n in names if n in pr and abs(pr[n] - L) / L <= tol]
    near = min(pr, key=lambda n: (abs(pr[n] - L), names.index(n)))
    tied = [n for n in names if n in pr and abs(pr[n] - pr[near]) / pr[near] <= TIE]
    primary = tied[0]
    return (primary if abs(pr[near] - L) / L <= tol else "none"), within


def tie_set(cands):
    """the largest cluster of candidate levels that sit within 0.1 % of each other (the coincidence count; priority order)."""
    pr = {n: cands[n] for n in CAND if cands.get(n) is not None and np.isfinite(cands[n])}
    best = []
    for n in pr:
        c = [m for m in CAND if m in pr and abs(pr[m] - pr[n]) / pr[n] <= TIE]
        if len(c) > len(best):
            best = c
    return best


def load_polygon(ticker):
    parts = []
    for ch in pd.read_csv(POLY, header=None, names=["t", "d", "o", "h", "l", "c", "v"], dtype={"t": str, "d": str},
                          keep_default_na=False, chunksize=2_000_000):
        parts.append(ch[ch.t == ticker])
    g = pd.concat(parts).drop_duplicates("d").sort_values("d").reset_index(drop=True)
    return g


def polygon_factor(ticker, screen):
    f = 1.0
    for ln in open(SPLITS):
        t, d, x, y = ln.strip().split("|")[:4]
        if t == ticker and d > screen:
            f *= float(y) / float(x)
    return f


def fnum(x, nd=6):
    if x is None or (isinstance(x, float) and not np.isfinite(x)):
        return ""
    return round(float(x), nd)


# ───────────────────────────── per-base context ─────────────────────────────
def alpaca_ctx(ev, base, ticker, screen):
    S = ev.series(ticker)
    if S is None:
        return None
    sd = dt.date.fromisoformat(screen).toordinal()
    i_scr = int(np.searchsorted(S.d, sd, "right")) - 1
    if i_scr < 0:
        return None
    ctx = dict(kind="alpaca", S=S, sym=S.sym, d=S.d, dates=S.dates, o=S.bars.o, h=S.bars.h, l=S.bars.l, c=S.bars.c,
               i_scr=i_scr, r=float(S.fac[i_scr]), night=None, feat=None, status_counts=collections.Counter())
    for k in range(i_scr, max(-1, i_scr - BACK), -1):
        st, ft = S.night(k)
        ctx["status_counts"][st] += 1
        if st == "pass" and ft["base_id"] == base:
            ctx["night"], ctx["feat"] = k, ft
            break
    return ctx


def polygon_ctx(base, ticker, screen):
    g = load_polygon(ticker)
    dates = [dt.date.fromisoformat(x) for x in g.d]
    bars = cb.daily_bars_from_arrays(dates, g.o, g.h, g.l, g.c, g.v)
    d = np.array([x.toordinal() for x in dates], dtype=np.int64)
    i_scr = int(np.searchsorted(d, dt.date.fromisoformat(screen).toordinal(), "right")) - 1
    ctx = dict(kind="polygon", S=None, sym=ticker, d=d, dates=dates, o=bars.o, h=bars.h, l=bars.l, c=bars.c, i_scr=i_scr,
               r=polygon_factor(ticker, screen), night=None, feat=None, status_counts=collections.Counter())
    wt = None
    for k in range(i_scr, max(129, i_scr - BACK) - 1, -1):
        feat, gate = cb.explain_watch(bars, k)
        ctx["status_counts"]["pass" if feat is not None else "c0:" + gate] += 1
        if feat is not None and f"{ticker}|{feat['pole_date']}" == base:
            feat["base_id"] = base
            ctx["night"], ctx["feat"] = k, feat
            break
    if ctx["night"] is not None:                                           # parity with the production watch table
        want = dates[ctx["night"]].isoformat()
        parts = []
        for ch in pd.read_csv(WATCH, sep="\t", usecols=["ticker", "watch_date"] + [f"pivot_{k}" for k in ("k5", "k10", "full", "tl")],
                              chunksize=500_000):
            parts.append(ch[(ch.ticker == ticker) & (ch.watch_date == want)])
        wt = pd.concat(parts)
        ctx["watch_parity"] = "no production row for that night" if wt.empty else "ok"
        if not wt.empty:
            for k in ("k5", "k10", "full", "tl"):
                a, b = float(wt.iloc[0][f"pivot_{k}"]), float(ctx["feat"][f"pivot_{k}"])
                assert abs(a - b) <= 1e-9 * max(1.0, abs(a)), (ticker, want, k, a, b)
    return ctx


# ───────────────────────────── the join ─────────────────────────────
def join_base(base, g, ctx):
    """-> (base row dict, [per-line row dicts])"""
    first = g.iloc[0]
    row = dict(base=base, ticker=first.ticker, frame_id=first.frame_id, screen=first.screen, ref_date=first.ref_date,
               year=first.screen[:4], w_pole_date=first.w_pole_date, w_base_len=int(first.w_base_len),
               n_lines=len(g), n_top=int((g.role == "top").sum()), n_level=int((g.role == "level").sum()),
               n_bottom=int((g.role == "bottom").sum()), sources_all="+".join(sorted(set(g.source))),
               bars_source=("" if ctx is None else ctx["kind"]), bars_symbol=("" if ctx is None else ctx["sym"]))
    lines = []
    have_night = ctx is not None and ctx["night"] is not None
    row["watch_night_status"] = "ok" if have_night else "no_watch_night"
    if ctx is not None:
        row["r_screen"] = repr(float(ctx["r"]))
        row["screen_bar_date"] = ctx["dates"][ctx["i_scr"]].isoformat()
    if not have_night:
        row["night_status_counts"] = json.dumps(dict(ctx["status_counts"])) if ctx else "no_series"
        # keep every line, converted when a series exists, without a comparison session
        for k, ln in enumerate(g.itertuples()):
            lines.append(dict(base=base, frame_id=ln.frame_id, role=ln.role, source=ln.source, color=ln.color,
                              start_date=ln.start_date, start_price=ln.start_price, end_date=ln.end_date, end_price=ln.end_price,
                              primary=0, line_value_cmp="", note="no_watch_night"))
        row["primary_role"] = "none"
        return row, lines
    i, feat, r = ctx["night"], ctx["feat"], ctx["r"]
    d, h, l, c, o = ctx["d"], ctx["h"], ctx["l"], ctx["c"], ctx["o"]
    P = feat["pole_idx"]
    cmp_j = i + 1
    cmp_date = dt.date.fromordinal(int(d[cmp_j])) if cmp_j < len(d) else None
    row.update(cmp_night=ctx["dates"][i].isoformat(), cmp_session=(cmp_date.isoformat() if cmp_date else ""),
               nights_before_screen=ctx["i_scr"] - i, pole_date=feat["pole_date"], pole_idx=P)
    # candidate levels (bar scale)
    bh, bc, bo = h[P + 1:i + 1], c[P + 1:i + 1], o[P + 1:i + 1]
    cands = {"pivot_k5": feat["pivot_k5"], "pivot_k10": feat["pivot_k10"], "pivot_full": feat["pivot_full"],
             "pivot_tl": feat["pivot_tl"], "high_close": float(bc.max()), "high_body": float(np.maximum(bo, bc).max()),
             "high_2nd": float(np.sort(bh)[::-1][1]) if len(bh) > 1 else None}
    assert abs(cands["pivot_full"] - float(bh.max())) < 1e-9 * cands["pivot_full"], "settled window != pivot_full's window"
    for n in CAND:
        row["c_" + n] = fnum(cands[n])
    coin = tie_set(cands)
    row["n_coincident_levels"] = len(coin)
    row["coincident_levels"] = "=".join(coin) if len(coin) > 1 else ""
    for f in FEATS:
        v = feat.get(f)
        row[f] = (bool(v) if isinstance(v, (bool, np.bool_)) else fnum(v, 5)) if v is not None else ""
    row["adr20_pct"] = fnum(feat["adr20"] * 100, 3)
    # lines
    prim, prim_key = None, None
    for k, ln in enumerate(g.itertuples()):
        p1, p2 = ln.start_price / r, ln.end_price / r
        s1, s2 = sess(d, ln.start_date), sess(d, ln.end_date)
        sl = slope_pct(p1, p2, s1, s2)
        L = float(line_at(ln.role, p1, p2, s1, s2, cmp_j))
        rec = dict(base=base, frame_id=ln.frame_id, role=ln.role, source=ln.source, color=ln.color, start_date=ln.start_date,
                   start_price=ln.start_price, end_date=ln.end_date, end_price=ln.end_price, start_price_bar=fnum(p1),
                   end_price_bar=fnum(p2), s1=s1, s2=s2, slope_pct_session=fnum(sl, 4), slope_class=slope_class(sl),
                   line_value_cmp=fnum(L), r_screen=repr(float(r)), end_gap_sessions=cmp_j - max(s1, s2), primary=0, note="")
        lines.append(rec)
        if ln.role in ("top", "level"):
            key = (abs(max(s1, s2) - cmp_j), ln.source != "bar_verified", -(abs(s2 - s1)), k)
            if prim_key is None or key < prim_key:
                prim, prim_key = (k, ln, p1, p2, s1, s2, sl, L), key
    bot = [x for x in lines if x["role"] == "bottom"]
    if bot:        # a bottom line, for the character picture (wide vs tight): its value at the comparison session, bar scale
        b0 = bot[0]
        row["bottom_value_cmp"] = fnum(line_at("bottom", b0["start_price_bar"], b0["end_price_bar"], b0["s1"], b0["s2"], cmp_j)[()])
    else:
        row["bottom_value_cmp"] = ""
    if prim is None:
        row["primary_role"] = "none"
        return row, lines
    k, ln, p1, p2, s1, s2, sl, L = prim
    lines[k]["primary"] = 1
    row.update(primary_role=ln.role, primary_source=ln.source, primary_color=ln.color, p_start_date=ln.start_date,
               p_start_price=ln.start_price, p_end_date=ln.end_date, p_end_price=ln.end_price, p_start_bar=fnum(p1),
               p_end_bar=fnum(p2), line_value_cmp=fnum(L), line_slope_pct_session=fnum(sl, 4), slope_class=slope_class(sl),
               line_over_pivot_full=fnum(L / cands["pivot_full"], 4))
    j = np.arange(P + 1, i + 1)
    Lj = line_at(ln.role, p1, p2, s1, s2, j)
    row["n_base_highs"] = len(j)
    row["n_base_highs_above_line"] = int((bh > Lj).sum())
    row["n_base_highs_above_line_2pct"] = int((bh > Lj * 1.02).sum())
    row["end_gap_sessions"] = cmp_j - max(s1, s2)       # > 0: his line ENDS that many sessions before the comparison session (extrapolated)
    row["wick_adr"] = fnum((cands["pivot_full"] - L) / cands["pivot_full"] / feat["adr20"], 3)
    for n in CAND:
        row["dpct_" + n] = fnum((cands[n] - L) / L * 100, 3) if cands[n] is not None else ""
    for tol in TOLS:
        t = int(tol * 100)
        m, within = pick(L, cands, CAND, tol)
        mm, _ = pick(L, cands, MODULE, tol)
        row[f"match_{t}pct"], row[f"match_set_{t}pct"], row[f"match_module_{t}pct"] = m, "+".join(within), mm
    near = min((n for n in CAND if cands[n] is not None), key=lambda n: (abs(cands[n] - L), CAND.index(n)))
    row["nearest_level"] = near
    row["nearest_dist_pct"] = fnum((cands[near] - L) / L * 100, 3)
    others = [x for x in lines if not x["primary"]]
    row["other_lines"] = " | ".join(f"{x['role']}:{x['color']}:{x['start_date']} {x['start_price']}->{x['end_date']} {x['end_price']}"
                                    for x in others)
    ctx["_prim"] = dict(L=L, p1=p1, p2=p2, s1=s1, s2=s2, role=ln.role, cands=cands, ln=ln)
    return row, lines


# ───────────────────────────── spot images ─────────────────────────────
COL = {"pivot_full": "#f59e0b", "pivot_k10": "#a855f7", "pivot_k5": "#ec4899", "pivot_tl": "#14b8a6",
       "high_close": "#eab308", "high_body": "#84cc16", "high_2nd": "#f97316"}


def spot_image(n, row, ctx, panel, outdir):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from PIL import Image, ImageDraw
    pr = ctx["_prim"]
    r, i = ctx["r"], ctx["night"]
    P = int(row["pole_idx"])
    d, h, l, c, o = ctx["d"], ctx["h"], ctx["l"], ctx["c"], ctx["o"]
    lo_j, hi_j = max(0, P - 45), ctx["i_scr"]
    x = d[lo_j:hi_j + 1].astype(float)
    hh, ll, cc = h[lo_j:hi_j + 1] * r, l[lo_j:hi_j + 1] * r, c[lo_j:hi_j + 1] * r
    x_cmp = float(d[i + 1]) if i + 1 < len(d) else float(d[i] + 1)
    fig, ax = plt.subplots(figsize=(10, 7.5), dpi=100)
    fig.patch.set_facecolor("black"); ax.set_facecolor("black")
    up = cc >= np.r_[cc[0], cc[:-1]]
    ax.vlines(x, ll, hh, color=np.where(up, "#22c55e", "#ef4444"), linewidth=1.2)
    x0 = float(d[P + 1])
    for nme in CAND:
        v = pr["cands"][nme]
        if v is None:
            continue
        if nme == "pivot_tl":
            A = int(row.get("tl_anchor_idx", ctx["feat"]["tl_anchor_idx"]))
            ax.plot([float(d[A]), x_cmp], [h[A] * r, v * r], color=COL[nme], lw=1.4, ls=(0, (4, 2)), label=f"{nme} {v * r:.2f}")
        else:
            ax.plot([x0, x_cmp], [v * r, v * r], color=COL[nme], lw=1.2, ls=(0, (2, 2)), label=f"{nme} {v * r:.2f}")
    ln = pr["ln"]
    d1, d2 = dt.date.fromisoformat(ln.start_date).toordinal(), dt.date.fromisoformat(ln.end_date).toordinal()
    ax.plot([d1, d2], [ln.start_price, ln.end_price], color="#38bdf8", lw=2.6,
            label=f"HIS {ln.role} {ln.start_price}->{ln.end_price}; at next session {pr['L'] * r:.2f}")
    ax.plot([x_cmp], [pr["L"] * r], marker="o", color="#38bdf8", ms=7, ls="")
    ax.axvline(float(d[i]), color="#64748b", lw=0.8, ls=":")
    ax.set_xlim(x.min() - 3, x_cmp + 4)
    lo_y, hi_y = ll.min(), max(hh.max(), max(v for v in pr["cands"].values() if v is not None) * r)
    pad = (hi_y - lo_y) * 0.06
    ax.set_ylim(lo_y - pad, hi_y + pad)
    ax.legend(loc="upper left", facecolor="black", labelcolor="white", fontsize=8, framealpha=0.85)
    ticks = [t for t in range(int(x.min()), int(x_cmp) + 1) if dt.date.fromordinal(t).day == 1]
    ax.set_xticks(ticks, [dt.date.fromordinal(t).strftime("%b %y") for t in ticks], color="white", fontsize=8)
    ax.tick_params(axis="y", colors="white"); ax.yaxis.tick_right()
    ax.set_title(f"#{n}  {row['ticker']}  our bars as shown on {row['screen']} (prices x r={r:g}); match 2%: {row['match_2pct']}; "
                 f"night {row['cmp_night']}", color="white", fontsize=9)
    tmp = os.path.join(outdir, f"_bars_{n}.png")
    fig.savefig(tmp, facecolor="black", bbox_inches="tight"); plt.close(fig)
    frame = Image.open(f"{VIS}/frames_p4b/{row['frame_id']}.png").convert("RGB")
    left = frame.crop((0, 55, 1000, 1000)) if panel == "left" else frame.resize((1280, 720))
    bars = Image.open(tmp).convert("RGB")
    hmax = max(left.height, bars.height)
    out = Image.new("RGB", (left.width + bars.width + 20, hmax + 40), (255, 255, 255))
    out.paste(left, (0, 40)); out.paste(bars, (left.width + 20, 40))
    ImageDraw.Draw(out).text((10, 10), f"#{n}  {row['ticker']} {row['screen']} ({row['frame_id']})  LEFT: his chart on stream   RIGHT: our bars, HIS line (blue) "
                                       f"and all 7 candidate levels   match 1/2/3%: {row['match_1pct']}/{row['match_2pct']}/{row['match_3pct']}  "
                                       f"nearest {row['nearest_level']} {row['nearest_dist_pct']}%", fill=(0, 0, 0))
    name = f"spot_{n}_{row['ticker']}_{row['screen']}_{row['match_2pct']}.png"
    path = os.path.join(outdir, name)
    out.save(path)
    os.remove(tmp)
    return path


# ───────────────────────────── summary ─────────────────────────────
def q(a):
    a = np.asarray(a, dtype=float)
    a = a[np.isfinite(a)]
    return "n=0" if not len(a) else f"n={len(a)} median {np.median(a):.2f}  quartiles {np.percentile(a, 25):.2f} / {np.percentile(a, 75):.2f}"


def build_summary(lab, lines, examples, xcheck, polygon_note):
    P = lab[lab.primary_role.isin(["top", "level"])].copy()
    L = []
    w = L.append
    w("P4B STEP 5 - LABEL JOIN: WHICH LEVEL DID HE DRAW?   ($0; label list used as given)")
    w("")
    m2 = P[P.match_2pct != "none"]
    n2 = P[P.match_2pct == "none"]
    sv = {s: (int((P[P.primary_source == s].match_2pct != "none").sum()), int((P.primary_source == s).sum()))
          for s in ("bar_verified", "eyeball_confirmed")}
    w("FINDING")
    w(f"- {len(m2)} of {len(P)} lines match one of the 7 levels within 2% (" +
      ", ".join(f"{k} {n}" for k, n in m2.match_2pct.value_counts().items()) + f"; pivot_full {int((P.match_2pct == 'pivot_full').sum())}); "
      f"{len(n2)} match none, and the nearest level sits ABOVE his line in {int((n2.nearest_dist_pct.astype(float) > 0).sum())} of {len(n2)} "
      f"(median {np.median(n2.nearest_dist_pct.astype(float).abs()):.1f}% away).")
    w(f"- by source the wick-ignored lines match BETTER: eyeball_confirmed {sv['eyeball_confirmed'][0]} of {sv['eyeball_confirmed'][1]}, "
      f"bar_verified {sv['bar_verified'][0]} of {sv['bar_verified'][1]}.")
    w("")
    w("POPULATION")
    w(f"- {len(lab)} bases, {len(lines)} drawn lines ({int((lines.role=='top').sum())} top, {int((lines.role=='level').sum())} level, "
      f"{int((lines.role=='bottom').sum())} bottom); {len(P)} bases carry a top or level line and are matched; "
      f"{len(lab) - len(P)} have only a bottom line (kept, not matched).")
    w(f"- screen years: " + ", ".join(f"{y} {n}" for y, n in sorted(lab.year.value_counts().items())) +
      f"   bars: {', '.join(f'{k} {n}' for k, n in lab.bars_source.value_counts().items())}")
    w("- most frequent tickers: " + ", ".join(f"{t} {n}" for t, n in lab.ticker.value_counts().head(6).items()))
    ls = lines.source.value_counts()
    ps = P.primary_source.value_counts()
    w(f"- source, all lines: bar_verified {ls.get('bar_verified', 0)}, eyeball_confirmed {ls.get('eyeball_confirmed', 0)};  "
      f"source of the matched (primary) line: bar_verified {ps.get('bar_verified', 0)}, eyeball_confirmed {ps.get('eyeball_confirmed', 0)}")
    nw = int((lab.watch_night_status != 'ok').sum())
    w(f"- no watch night: {nw} base(s).  comparison night = the screen date for {int((lab.nights_before_screen==0).sum())}, one session earlier "
      f"for {int((lab.nights_before_screen==1).sum())}.  {polygon_note}")
    w("- SELECTION MECHANISM (step 6 must weight both): the bars check requires >= 2 touches and few closes crossing the line, so it rejects")
    w("  a line drawn THROUGH an ignored upper wick. bar_verified therefore leans to wick-touching lines; eyeball_confirmed holds the")
    w("  wick-ignored ones (the main loop matched them to his chart by eye). The two sources are not draws from the same population.")
    w(f"- price scale: r(screen) != 1 for {int((lab.r_screen.astype(float) != 1).sum())} bases; cross-check of r vs vision_score.series_asof: {xcheck}")
    w("")
    w("WHICH LEVEL HIS LINE MATCHES   (nearest of 7 levels; level counts by tolerance, then at 2% by slope and by source)")
    names = CAND + ["none"]
    hdr = f"{'level':<11}{'1%':>4}{'2%':>4}{'3%':>4} |{'falling':>8}{'flat':>6}{'rising':>7} |{'bar_verif':>10}{'eyeball':>8}"
    w(hdr)
    for nm in names:
        c1, c2, c3 = (int((P[f"match_{t}pct"] == nm).sum()) for t in (1, 2, 3))
        s2 = P[P.match_2pct == nm]
        w(f"{nm:<11}{c1:>4}{c2:>4}{c3:>4} |{int((s2.slope_class=='falling').sum()):>8}{int((s2.slope_class=='flat').sum()):>6}"
          f"{int((s2.slope_class=='rising').sum()):>7} |{int((s2.primary_source=='bar_verified').sum()):>10}"
          f"{int((s2.primary_source=='eyeball_confirmed').sum()):>8}")
    w(f"{'total':<11}{len(P):>4}{len(P):>4}{len(P):>4} |{int((P.slope_class=='falling').sum()):>8}{int((P.slope_class=='flat').sum()):>6}"
      f"{int((P.slope_class=='rising').sum()):>7} |{int((P.primary_source=='bar_verified').sum()):>10}{int((P.primary_source=='eyeball_confirmed').sum()):>8}")
    w("module levels only (k5 / k10 / full / tl), 1% 2% 3%: " + "; ".join(
        f"{nm} " + "/".join(str(int((P[f'match_module_{t}pct'] == nm).sum())) for t in (1, 2, 3)) for nm in MODULE + ["none"]))
    w("inside 2% (not exclusive - a base counts under EVERY level within 2%): " + ", ".join(
        f"{nm} {int(P.match_set_2pct.fillna('').map(lambda s, nm=nm: nm in s.split('+')).sum())}" for nm in CAND))
    coin = int((P.n_coincident_levels >= 2).sum())
    w(f"COINCIDENCE: on {coin} of {len(P)} matched bases at least two of the 7 levels sit within 0.1% of each other, so 'which level' is "
      f"ambiguous there; the full set is in match_set_*pct. Most common coincidences: " +
      ", ".join(f"{k} {n}" for k, n in P[P.coincident_levels != ""].coincident_levels.value_counts().head(4).items()))
    w(f"slope of his line: falling {int((P.slope_class=='falling').sum())}, flat {int((P.slope_class=='flat').sum())}, "
      f"rising {int((P.slope_class=='rising').sum())}  (flat = |slope| < {FLAT}% per session; every `level` line is flat)")
    ext = P[P.end_gap_sessions.astype(float) > 5]
    near = P[P.end_gap_sessions.astype(float) <= 5]
    far = P[P.line_over_pivot_full.astype(float) < 0.8]
    nn = P[P.match_2pct == "none"]
    w(f"CAVEATS: {len(ext)} of {len(P)} lines END more than 5 sessions before the comparison session, so their value there is an extrapolation "
      f"(matched within 2%: {int((ext.match_2pct != 'none').sum())} of {len(ext)}; lines ending within 5 sessions: {int((near.match_2pct != 'none').sum())} of {len(near)}); "
      f"{len(far)} lines sit more than 20% below pivot_full (long-range levels or an earlier high), which no candidate can match.")
    w(f"the {len(nn)} 'none' at 2%: nearest level " + ", ".join(f"{k} {n}" for k, n in nn.nearest_level.value_counts().items()) +
      f"; median distance to it {np.median(nn.nearest_dist_pct.astype(float).abs()):.1f}% (that level sits ABOVE his line in "
      f"{int((nn.nearest_dist_pct.astype(float) > 0).sum())} of {len(nn)})")
    w("")
    w("HOW FAR BELOW pivot_full HIS LINE SITS   (ADR20 units = wick-ignore size; negative = his line above pivot_full)")
    for src in ("bar_verified", "eyeball_confirmed"):
        w(f"- {src:<18} {q(P[P.primary_source == src].wick_adr)}")
    w(f"- all                {q(P.wick_adr)}   lines above pivot_full: {int((P.wick_adr.astype(float) < 0).sum())}")
    for sc in ("falling", "flat"):
        w(f"- {sc + ' lines':<18} {q(P[P.slope_class == sc].wick_adr)}")
    w("")
    w("RECORDED EXAMPLE (a labelled example, not a rule)")
    w(examples["amd"])
    w("")
    w("PRICE-SCALE CONVERSION EXAMPLES (screen price / r = bar-scale price; bar-scale prices in the TSV follow Alpaca's adjustment, e.g. WKHS r=0.000333")
    w("gives ~75,000 after its later reverse splits, LCID r=0.1; every comparison is relative so the join is unaffected)")
    for e in examples["conv"]:
        w("- " + e)
    return "\n".join(L) + "\n"


# ───────────────────────────── main ─────────────────────────────
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=OUT)
    a = ap.parse_args()
    os.makedirs(os.path.join(a.out, "spot"), exist_ok=True)
    lab_in = pd.read_csv(f"{VIS}/p4b_label_lines.tsv", sep="\t", keep_default_na=False,
                         dtype={"start_price": float, "end_price": float})
    panel = {}
    for run in json.load(open(f"{VIS}/p4b_reads_all.json")):
        for f in run["frames"]:
            panel.setdefault(f["frame_id"], collections.Counter())[f.get("daily_panel")] += 1
    panel = {k: max(v, key=v.get) for k, v in panel.items()}
    assert lab_in["base"].nunique() == 60 and len(lab_in) == 93, (lab_in["base"].nunique(), len(lab_in))
    ev = ext_c0.Evaluator(EXT)
    rows, lrows, ctxs = [], [], {}
    for base, g in lab_in.groupby("base", sort=False):
        g = g.reset_index(drop=True)
        t, scr = g.ticker.iloc[0], g.screen.iloc[0]
        ctx = polygon_ctx(base, t, scr) if scr > "2022-06-30" else alpaca_ctx(ev, base, t, scr)
        row, lines = join_base(base, g, ctx)
        rows.append(row)
        lrows += lines
        ctxs[base] = ctx
    lab = pd.DataFrame(rows)
    lines = pd.DataFrame(lrows)
    assert len(lab) == 60 and len(lines) == 93, (len(lab), len(lines))
    lab["daily_panel"] = lab.frame_id.map(panel)

    # ── scale cross-check vs vision_score.series_asof (same ratio, independent loader) ──
    sub = lab[lab.bars_source == "alpaca"]
    A, Pp, Sp = vsc.load_bars(set(sub.bars_symbol))
    worst, n_cmp = 0.0, 0
    for rw in sub.itertuples():
        ser = vsc.series_asof(rw.bars_symbol, rw.screen, A, Pp, Sp)
        ctx = ctxs[rw.base]
        k = np.nonzero(ser[0] == ctx["dates"][ctx["i_scr"]].isoformat())[0]
        assert len(k) == 1, ("screen bar missing in vision_score's series", rw.base)
        r_vs = float(ser[1][k[0]]) / float(ctx["h"][ctx["i_scr"]])       # series_asof returns high x r(screen)
        worst = max(worst, abs(r_vs / ctx["r"] - 1))
        n_cmp += 1
    xcheck = f"{n_cmp} of {len(sub)} Alpaca bases compared, max relative difference {worst:.1e}"
    assert n_cmp == len(sub) and worst < 1e-9, xcheck
    pg = lab[lab.bars_source == "polygon"]
    par = {b: ctxs[b].get("watch_parity", "not checked") for b in pg["base"]}
    polygon_note = (f"bars: {len(sub)} Alpaca, {len(pg)} Polygon ({', '.join(pg['base'])}; four pivots vs the production watch row: {par})"
                    if len(pg) else f"bars: {len(sub)} Alpaca")

    # ── conversion examples ──
    conv = []
    def ex(rw, why):
        ln = lines[(lines["base"] == rw["base"]) & (lines.primary == 1)].iloc[0] if (lines["base"] == rw["base"]).any() and (
            (lines["base"] == rw["base"]) & (lines.primary == 1)).any() else lines[lines["base"] == rw["base"]].iloc[0]
        conv.append(f"{why}: {rw['base']} screen {rw.screen}, r={rw.r_screen}: {ln.role} line {ln.start_date} {ln.start_price} -> {ln.end_date} "
                    f"{ln.end_price} on screen = {ln.start_price_bar} -> {ln.end_price_bar} on the bars; value at next session {ln.line_value_cmp}")
    lab["_r"] = lab.r_screen.astype(float)
    alp = lab[(lab.bars_source == "alpaca") & (lab.watch_night_status == "ok")]
    ex(alp[alp._r == 1].iloc[0], "no later split")
    if (alp._r > 1.0000001).any():
        ex(alp.sort_values("_r").iloc[-1], "split after the stream (Alpaca)")
    if len(pg):
        ex(pg.iloc[0], "split after the stream (Polygon: the 2026 split)")
    amd_row = lab[lab.frame_id == "p4b_110"].iloc[0]
    amd_line = lines[(lines.frame_id == "p4b_110") & (lines.primary == 1)].iloc[0]
    amd = (f"- AMD 2021-12-16 (frame p4b_110, base {amd_row['base']}): on his screen the context menu reads 'Buy Stop @ Trendline', i.e. his entry sits ON "
           f"the drawn line.  Line {amd_line.start_date} {amd_line.start_price} -> {amd_line.end_date} {amd_line.end_price} ({amd_line.source}, "
           f"{amd_row.slope_class}, {amd_row.line_slope_pct_session}%/session); value at the next session {amd_row.line_value_cmp} (bar scale), "
           f"pivot_full {amd_row.c_pivot_full}, pivot_tl {amd_row.c_pivot_tl}, high_2nd {amd_row.c_high_2nd}; match at 1/2/3%: "
           f"{amd_row.match_1pct}/{amd_row.match_2pct}/{amd_row.match_3pct}; every level inside 1%: {amd_row.match_set_1pct}; "
           f"nearest {amd_row.nearest_level} ({amd_row.nearest_dist_pct}%); "
           f"{amd_row.wick_adr} ADR below pivot_full.")
    examples = dict(conv=conv, amd=amd)

    # ── spot images: five different 2% outcomes, one of them `none`; AMD p4b_110 is the pick for its own outcome ──
    P = lab[lab.primary_role.isin(["top", "level"])].copy()
    P["nd"] = P.nearest_dist_pct.astype(float).abs()
    cnt = P.match_2pct.value_counts()
    picks = []
    outcomes = [o for o in cnt.index if o != "none"][:4] + (["none"] if "none" in cnt.index else [])
    for oc in outcomes:
        s = P[P.match_2pct == oc].sort_values(["nd", "base"])
        pk = s[s.frame_id == "p4b_110"] if (s.frame_id == "p4b_110").any() else s.iloc[[len(s) // 2]]
        picks.append(pk.iloc[0])
    spot_paths = []
    for n, rw in enumerate(picks, 1):
        spot_paths.append(spot_image(n, rw, ctxs[rw["base"]], panel.get(rw.frame_id, "left"), os.path.join(a.out, "spot")))
        print("spot", n, spot_paths[-1])

    lab = lab.drop(columns=["_r"])
    lead = ["base", "ticker", "frame_id", "screen", "ref_date", "year", "bars_source", "watch_night_status", "cmp_night", "cmp_session",
            "nights_before_screen", "primary_role", "primary_source", "sources_all", "slope_class", "line_value_cmp",
            "match_1pct", "match_2pct", "match_3pct", "match_set_1pct", "match_set_2pct", "match_set_3pct",
            "match_module_1pct", "match_module_2pct", "match_module_3pct", "nearest_level", "nearest_dist_pct", "wick_adr"]
    lab = lab[lead + [c for c in lab.columns if c not in lead]]
    lab.to_csv(os.path.join(a.out, "labels_p4b.tsv"), sep="\t", index=False)
    lines.to_csv(os.path.join(a.out, "lines_p4b.tsv"), sep="\t", index=False)
    summ = build_summary(lab, lines, examples, xcheck, polygon_note)
    summ += "\nSPOT-CHECK IMAGES (five different 2% outcomes)\n" + "\n".join(f"- {p}" for p in spot_paths) + "\n"
    open(os.path.join(a.out, "summary_p4b_labels.txt"), "w").write(summ)
    print(summ)


if __name__ == "__main__":
    sys.exit(main())
