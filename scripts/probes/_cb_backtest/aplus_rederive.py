"""#705 (b) - the INDEPENDENT re-derivation of the A+ rating (WOULD-FAIL-IF check 11 / data check 6): pandas from the SOURCE files, NO runner
code - this module imports neither `runner`, `aplus_read`, `registered_read` nor `consolidation_breakout` (a test asserts it by AST). Every
CSV / TSV is read with `float_precision="round_trip"`; the daily export is sorted by (ticker, date) first. Its own minute reader (gzip members
parsed one by one, the LAST block per (date, ticker) kept), its own chain-at-D, its own pandas-rank percentiles, its own bootstrap on the
same generator keys. The read calls `rederive(...)` and requires VERDICT MATCH before the result is written: first the identical (ticker, E)
A+ set per N for the core, +grp and the reversed stair-step row; then n / mean R / the interval / both paired deltas / every PASS component /
the +grp reading; and the profile re-derived from the 2017-21 tree equal to the pinned file to 1e-9.
"""
from __future__ import annotations

import datetime as dt
import zlib
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

# the registration's constants, restated here (the re-derivation shares no constant object with the read)
POOL, STAIR, FLOOR = 20, 120, 30
RANK = {1: 4, 3: 12, 5: 20}
DRAWS, SEED = 2000, 702
MIN_N, TAIL_R, TAIL_W, TAIL_T, TAIL_M = 30, 10.0, 0.25, 3, 3
ERA = {"pre": (dt.date(1900, 1, 1), dt.date(2021, 12, 31)), "discovery": (dt.date(2022, 1, 1), dt.date(2024, 12, 31)), "holdout": (dt.date(2025, 1, 1), dt.date(2099, 12, 31))}
FEAT = [("tightening_ratio", -1), ("wk_ratio", -1), ("pb_ratio", -1), ("vol_dry5", -1), ("rs_best", 1), ("prior_move", 1), ("stair_n", -1), ("exp_up_adr", 1),
        ("vol_sofar_x", 1), ("grp_pct", 1)]
STR = {"ticker": str, "D": str, "E": str, "K": str, "split": str, "pole_date": str, "watch_date": str, "entry": str, "arm": str, "stop_variant": str, "fill_month": str}


def _read(path, usecols):
    return pd.read_csv(path, sep="\t", usecols=usecols, dtype={k: v for k, v in STR.items() if k in usecols}, keep_default_na=False, na_values=[""],
                       low_memory=False, float_precision="round_trip")


def _in_era(e: str, period: str) -> bool:
    d = dt.date.fromisoformat(e)
    m = d - dt.timedelta(days=d.weekday())
    lo, hi = ERA[period]
    return lo <= m <= hi


def _week(e: str) -> str:
    y, w, _ = dt.date.fromisoformat(e).isocalendar()
    return f"{y}-W{w:02d}"


# ═══ the minute files: our own reader ════════════════════════════════════════════════════════════════════════════════════════════════
def gz_members(path) -> list:
    """The decompressed text of every COMPLETE gzip member of a multi-member file (a truncated tail member dropped)."""
    raw = Path(path).read_bytes()
    out, pos = [], 0
    while pos < len(raw):
        d = zlib.decompressobj(wbits=31)
        try:
            text = d.decompress(raw[pos:])
        except zlib.error:
            break
        if not d.eof:
            break
        out.append(text.decode("utf-8", "replace"))
        consumed = len(raw) - pos - len(d.unused_data)
        pos += consumed
    return out


def minute_blocks(path, want: "set | None" = None) -> dict:
    """{ticker: DataFrame(minute, o, h, l, c, v)} - a block = a run of consecutive lines for one ticker inside ONE member; the LAST block per
    ticker replaces the earlier ones."""
    blocks = {}
    for text in gz_members(path):
        cur_t, cur = None, []
        for line in text.split("\n"):
            f = line.split("|")
            if len(f) != 7:
                if cur_t is not None and cur:
                    blocks[cur_t] = cur
                cur_t, cur = None, []
                continue
            if f[0] != cur_t:
                if cur_t is not None and cur:
                    blocks[cur_t] = cur
                cur_t, cur = f[0], []
            cur.append(f)
        if cur_t is not None and cur:
            blocks[cur_t] = cur
    out = {}
    for t, rows in blocks.items():
        if want is not None and t not in want:
            continue
        df = pd.DataFrame(rows, columns=["ticker", "minute", "o", "h", "l", "c", "v"])
        try:
            df = df.assign(minute=df["minute"].astype(int), o=df["o"].astype(float), h=df["h"].astype(float), l=df["l"].astype(float), c=df["c"].astype(float), v=df["v"].astype(float))
        except ValueError:
            continue
        if df["minute"].min() < 0 or df["minute"].max() > 389 or not df["minute"].is_monotonic_increasing or df["minute"].duplicated().any() \
                or not np.isfinite(df[["o", "h", "l", "c", "v"]].to_numpy()).all():
            continue
        out[t] = df
    return out


def profile_from_tree(minutes_dir: Path, early_close: set, population: set, log=print) -> tuple:
    """The PROFILE block's rule re-derived with pandas: every pair logged ok in `_done.psv`, CUM(m) over 391 slots, kept = ok - zero-volume days -
    early-close sessions - the population's own pairs; the pointwise median."""
    done = pd.read_csv(minutes_dir / "_done.psv", sep="|", header=None, names=["date", "ticker", "n", "status"], dtype=str, keep_default_na=False)
    ok = done[done["status"] == "ok"]
    by_date = ok.groupby("date")["ticker"].apply(list).to_dict()
    cum, flags = [], []
    for k, (d, tks) in enumerate(sorted(by_date.items())):
        p = minutes_dir / f"{d}.psv.gz"
        blocks = minute_blocks(p) if p.exists() else {}
        for t in tks:
            vec = np.zeros(390)
            b = blocks.get(t)
            if b is not None:
                vec[b["minute"].to_numpy()] = b["v"].to_numpy()
            tot = vec.sum()
            cum.append(np.concatenate([[0.0], np.cumsum(vec)]) / tot if tot > 0 else np.full(391, np.nan))
            flags.append((tot > 0, d in early_close, (d, t) in population))
        if k % 200 == 0:
            log(f"  re-derivation profile: {k + 1}/{len(by_date)} dates")
    M = np.vstack(cum) if cum else np.zeros((0, 391))
    fl = pd.DataFrame(flags, columns=["nonzero", "early", "pop"])
    keep = (fl["nonzero"] & ~fl["early"] & ~fl["pop"]).to_numpy()
    tally = {"ok": int(len(fl)), "zero": int((~fl["nonzero"]).sum()), "early": int((fl["nonzero"] & fl["early"]).sum()),
             "population": int((fl["nonzero"] & ~fl["early"] & fl["pop"]).sum()), "kept": int(keep.sum())}
    return (np.median(M[keep], axis=0) if keep.any() else np.full(391, np.nan)), tally


# ═══ the features ═════════════════════════════════════════════════════════════════════════════════════════════════════════════════════
def weekly(h: np.ndarray, l: np.ndarray, c: np.ndarray, base_len: int):
    k = base_len // 5
    if k < 3:
        return None
    n = len(h)
    blocks = np.arange(1, k + 1)
    starts = n - 5 * blocks
    env = np.array([(h[s:s + 5].max() - l[s:s + 5].min()) / c[s + 4] if c[s + 4] > 0 else np.nan for s in starts])
    if np.isnan(env).any():
        return None
    m = k // 2
    early = env[k - m:].mean()
    return float(env[:m].mean() / early) if early > 0 else None


def pullbacks(h: np.ndarray, l: np.ndarray):
    n = len(h)
    if n < 3:
        return None
    s = pd.Series(h)
    j = np.arange(2, n - 2)
    cond = (s.shift(1)[j] < s[j]) & (s.shift(2)[j] < s[j]) & (s.shift(-1)[j] <= s[j]) & (s.shift(-2)[j] <= s[j])
    highs = [0] + list(j[cond.to_numpy()])
    pb = [(h[a] - l[a + 1:b].min()) / h[a] for a, b in zip(highs[:-1], highs[1:])]
    if len(pb) < 2 or pb[0] <= 0:
        return None
    return float(pb[-1] / pb[0])


def chain(poles: pd.DataFrame, D: str, drift: int) -> dict:
    """{pole_ci: base} over the ticker's watch rows with watch_date <= D."""
    p = poles[poles["watch_date"] <= D].drop_duplicates("pole_ci").sort_values("pole_ci")
    out, base, prev = {}, None, None
    for pci, pdt in zip(p["pole_ci"], p["pole_date"]):
        if prev is None or pci - prev > drift:
            base = pdt
        out[int(pci)] = base
        prev = pci
    return out


def pct_against(S: pd.Series, x: float) -> float:
    return float(((S < x).sum() + 0.5 * (S == x).sum()) / len(S))


# ═══ the bars ═════════════════════════════════════════════════════════════════════════════════════════════════════════════════════════
def boot_ci(values: np.ndarray, months: np.ndarray, key: str) -> tuple:
    df = pd.DataFrame({"v": values, "m": months})
    g = df.groupby("m")["v"].agg(["sum", "count"]).sort_index()
    sums, cnts = g["sum"].to_numpy(), g["count"].to_numpy(dtype=float)
    m = len(g)
    rng = np.random.default_rng([SEED, zlib.crc32(key.encode())])
    idx = rng.integers(0, m, size=(DRAWS, m))
    means = sums[idx].sum(axis=1) / cnts[idx].sum(axis=1)
    return float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))


def paired(ra, ma, rb, mb, key: str) -> dict:
    months = sorted(set(ma) | set(mb))
    m = len(months)
    if len(ra) == 0 or len(rb) == 0 or m == 0:
        return {"mean": float("nan"), "lo": float("nan"), "hi": float("nan"), "reading": "can't tell"}
    A = pd.DataFrame({"r": ra, "m": ma}).groupby("m")["r"].agg(["sum", "count"]).reindex(months).fillna(0)
    B = pd.DataFrame({"r": rb, "m": mb}).groupby("m")["r"].agg(["sum", "count"]).reindex(months).fillna(0)
    rng = np.random.default_rng([SEED, zlib.crc32(key.encode())])
    diffs = []
    while len(diffs) < DRAWS:
        d = rng.integers(0, m, size=m)
        na, nb = A["count"].to_numpy()[d].sum(), B["count"].to_numpy()[d].sum()
        if na == 0 or nb == 0:
            continue
        diffs.append(A["sum"].to_numpy()[d].sum() / na - B["sum"].to_numpy()[d].sum() / nb)
    lo, hi = float(np.percentile(diffs, 2.5)), float(np.percentile(diffs, 97.5))
    return {"mean": float(np.mean(ra) - np.mean(rb)), "lo": lo, "hi": hi, "reading": "separates" if lo > 0 else ("picks worse" if hi < 0 else "can't tell")}


def verdict(g: dict, c0: dict) -> str:
    if g["n"] < MIN_N:
        return "CAN'T TELL"
    if g["ci_hi"] < 0 or not g["mean_r"] > c0["mean_r_exact"]:
        return "FAIL"
    unmet = (not g["ci_lo"] > 0) or (not g["mean_pnl_adr"] > 0) or (not g["ge5_per100"] > c0["ge5_exact"])
    tail = (g["count_ge10"] * c0["n"] >= 2 * c0["ge10"] * g["n"]) and g["tail_tickers"] >= TAIL_T and g["tail_months"] >= TAIL_M
    if not unmet and tail:
        return "PASS"
    return "CAN'T TELL (positive, no tail)" if not unmet else "CAN'T TELL"


# ═══ the re-derivation ══════════════════════════════════════════════════════════════════════════════════════════════════════════════
def rederive(paths: dict, period: str, pool_only_min_e, early_close: set, drift_max: int, pre_minutes: Path, pre_fills: Path, c0: dict, log=print) -> dict:
    cols = ["ticker", "D", "E", "K", "entry", "arm", "fill", "fill_minute", "fill_month", "adr20", "width_adr", "mature", "realized_r", "pnl_adr"]
    f = _read(paths["fills"], cols)
    f = f[(f["arm"] == "pp") & (f["entry"] == "orh5") & (f["K"] == "tl")].copy()
    r0 = f.loc[f["mature"] == 1, "realized_r"].to_numpy(dtype=float)            # C0 = every mature row of the table, the edge fills included
    c0 = dict(c0, mean_r_exact=float(r0.mean()) if len(r0) else float("nan"), ge5_exact=float(100 * (r0 >= 5).mean()) if len(r0) else float("nan"))
    f["eligible"] = [_in_era(e, period) for e in f["E"]]
    if period == "pre":
        f = f[f["eligible"]]
    if period == "holdout":
        g = _read(paths["pool_fills"], cols)
        g = g[(g["arm"] == "pp") & (g["entry"] == "orh5") & (g["K"] == "tl") & (g["E"] >= pool_only_min_e)].copy()
        g["eligible"] = False
        f = pd.concat([g, f], ignore_index=True)
    f = f.sort_values(["E", "fill_minute", "ticker"]).reset_index(drop=True)
    log(f"  re-derivation: {len(f):,} rows ({int(f['eligible'].sum()):,} eligible)")
    # the export, sorted by (ticker, date); the SPY calendar
    ex = pd.read_csv(paths["export"], header=None, names=["ticker", "date", "o", "h", "l", "c", "v"], dtype={"ticker": str, "date": str}, keep_default_na=False,
                     float_precision="round_trip").sort_values(["ticker", "date"]).reset_index(drop=True)
    cal = ex.loc[ex["ticker"] == "SPY", "date"].tolist()
    ci_of = {d: k for k, d in enumerate(cal)}
    ex["ci"] = ex["date"].map(ci_of)
    by_t = {t: g[["ci", "h", "l", "c", "v"]].to_numpy() for t, g in ex.groupby("ticker", sort=False)}
    del ex
    # the candidates (never base_id, never an E-day column), the watch rows, the P5 rows
    cc = _read(paths["cands"], ["ticker", "D", "E", "K", "retrigger", "pole_date", "pole_ci", "adv20_vol_D", "prior_move", "base_len", "tightening_ratio", "rs_best", "grp_pct"])
    cc = cc[cc["K"] == "tl"]
    first_e_ci = min(ci_of.get(e, 10**9) for e in cc["E"]) if len(cc) else 10**9
    f = f.merge(cc[["ticker", "D", "E", "K", "pole_date", "pole_ci", "adv20_vol_D", "prior_move", "base_len", "tightening_ratio", "rs_best", "grp_pct"]],
                on=["ticker", "D", "E", "K"], how="left", validate="one_to_one")
    w = _read(paths["watch"], ["ticker", "watch_date", "close", "pole_ci", "pole_date"])
    f = f.merge(w[["ticker", "watch_date", "close"]].rename(columns={"watch_date": "D", "close": "close_D"}), on=["ticker", "D"], how="left", validate="many_to_one")
    poles_of = {t: g[["watch_date", "pole_ci", "pole_date"]] for t, g in w.groupby("ticker", sort=False)}
    fb = cc[cc["retrigger"] == 0].copy()
    fb["E_ci"] = fb["E"].map(ci_of)
    fb = fb.dropna(subset=["E_ci"])
    fb_of = {t: g[["E_ci", "pole_ci"]].to_numpy(dtype=int) for t, g in fb.groupby("ticker", sort=False)}
    f["E_ci"] = f["E"].map(ci_of).astype(int)
    f["D_ci"] = f["D"].map(ci_of).astype(int)
    # the export-derived features and the stair step
    wk, pb, vd, sn = [], [], [], []
    for r in f.itertuples(index=False):
        a = by_t.get(r.ticker)
        pci, dci = ci_of.get(r.pole_date), r.D_ci
        if a is None or pci is None:
            wk.append(None); pb.append(None); vd.append(None)
        else:
            seg = a[(a[:, 0] >= pci) & (a[:, 0] <= dci)]
            h, l, c = seg[:, 1], seg[:, 2], seg[:, 3]
            if len(seg) == int(r.base_len) + 1:
                wk.append(weekly(h, l, c, int(r.base_len))); pb.append(pullbacks(h, l))
            else:
                wk.append(None); pb.append(None)
            upto = a[a[:, 0] <= dci]
            if len(upto) >= 10 and upto[-1, 0] == dci and upto[-10:-5, 4].mean() > 0:
                vd.append(float(upto[-5:, 4].mean() / upto[-10:-5, 4].mean()))
            else:
                vd.append(None)
        lo, hi = r.E_ci - STAIR, r.E_ci - 1
        if lo < first_e_ci:
            sn.append(None)
        else:
            ch = chain(poles_of.get(r.ticker, pd.DataFrame(columns=["watch_date", "pole_ci", "pole_date"])), r.D, drift_max)
            rows = fb_of.get(r.ticker, np.zeros((0, 2), dtype=int))
            rows = rows[(rows[:, 0] >= lo) & (rows[:, 0] <= hi)]
            bases = {ch[int(p)] for p in rows[:, 1]}
            bases.discard(ch.get(int(r.pole_ci)))
            sn.append(len(bases))
    f["wk_ratio"], f["pb_ratio"], f["vol_dry5"], f["stair_n"] = wk, pb, vd, sn
    # the minute windows against the pinned profile (READ, never rebuilt)
    prof = pd.read_csv(paths["profile"], sep="\t", float_precision="round_trip")["profile"].to_numpy(dtype=float)
    f["exp_up_adr"] = [((fl - cd) / (cd * adr)) if (cd == cd and cd > 0 and adr > 0) else None for fl, cd, adr in zip(f["fill"], f["close_D"], f["adr20"])]
    vs = pd.Series([None] * len(f), dtype=object)
    for e, idx in f.groupby("E").indices.items():
        p = Path(paths["minutes"]) / f"{e}.psv.gz"
        blocks = minute_blocks(p, set(f["ticker"].iloc[idx])) if p.exists() else {}
        for i in idx:
            b = blocks.get(f["ticker"].iat[i])
            fm = int(f["fill_minute"].iat[i])
            if b is None:
                continue
            s = float(b.loc[b["minute"] < fm, "v"].sum())
            adv = f["adv20_vol_D"].iat[i]
            vs.iat[i] = (s / (adv * prof[fm])) if (s > 0 and adv == adv and adv > 0) else None
    f["vol_sofar_x"] = vs.to_numpy()
    f["week"] = [_week(e) for e in f["E"]]
    # the rating: pools per E date, pandas ranks for the members, the cutoff, the cap in fill order
    X = pd.DataFrame({k: pd.to_numeric(f[k], errors="coerce") * d for k, d in FEAT})
    specs = {"core": {"req": ["c1", "c2", "c3", "c4", "c6", "c7"], "opt": ["c5"], "rev": []}, "grp": {"req": ["c1", "c2", "c3", "c4", "c6", "c7", "grp"], "opt": ["c5"], "rev": []},
             "rev_stair": {"req": ["c1", "c2", "c3", "c4", "c6", "c7"], "opt": ["c5"], "rev": ["c5"]}}
    keymap = {"c1_daily": "tightening_ratio", "c1_wk": "wk_ratio", "c1_pb": "pb_ratio", "c2": "vol_dry5", "c3": "rs_best", "c4": "prior_move", "c5": "stair_n",
              "c6": "exp_up_adr", "c7": "vol_sofar_x", "grp": "grp_pct"}

    def score(P: pd.DataFrame, sp: dict) -> np.ndarray:
        parts, ok = [], np.ones(len(P), dtype=bool)
        for k in sp["req"] + sp["opt"]:
            if k == "c1":
                v = (P["c1_daily"] + P["c1_wk"].fillna(0.5) + P["c1_pb"].fillna(0.5)) / 3
            else:
                v = P[k]
                if k in sp["rev"]:
                    v = 1 - v
            if k in sp["req"]:
                ok &= v.notna().to_numpy()
            parts.append(v)
        M = pd.concat(parts, axis=1)
        s = M.mean(axis=1, skipna=True).to_numpy(dtype=float, copy=True)
        s[~ok] = np.nan
        return s
    E_ci = f["E_ci"].to_numpy()
    score_cols = {s: np.full(len(f), np.nan) for s in specs}
    cutoff = {(s, N): np.full(len(f), np.nan) for s in specs for N in ((1, 3, 5) if s == "core" else (3,))}
    for e in sorted(set(E_ci)):
        day = np.flatnonzero(E_ci == e)
        pool = np.flatnonzero((E_ci >= e - POOL) & (E_ci <= e - 1))
        own, ref = pd.DataFrame(index=day, columns=list(keymap), dtype=float), pd.DataFrame(index=pool, columns=list(keymap), dtype=float)
        for key, col in keymap.items():
            S = X[col].iloc[pool].dropna()
            if len(S) >= FLOOR:
                own[key] = [pct_against(S, x) if x == x else np.nan for x in X[col].iloc[day]]
            if len(S) - 1 >= FLOOR:
                rk = (S.rank(method="average") - 1) / (len(S) - 1)
                ref.loc[rk.index, key] = rk.to_numpy()
        for s, sp in specs.items():
            score_cols[s][day] = score(own, sp)
            rs = score(ref, sp)
            rs = np.sort(rs[~np.isnan(rs)])[::-1]
            for N in ((1, 3, 5) if s == "core" else (3,)):
                cutoff[(s, N)][day] = rs[RANK[N] - 1] if len(rs) >= RANK[N] else np.nan
    aplus = {}
    el = f["eligible"].to_numpy()
    for (s, N) in cutoff:
        taken, chosen = defaultdict(int), set()
        for i in range(len(f)):
            if not el[i]:
                continue
            sc, cu = score_cols[s][i], cutoff[(s, N)][i]
            if sc == sc and cu == cu and sc >= cu:
                wk_ = f["week"].iat[i]
                if taken[wk_] < N:
                    taken[wk_] += 1
                    chosen.add((f["ticker"].iat[i], f["E"].iat[i]))
        aplus[(s, N)] = chosen
    # the bars on the core at N = 3
    key3 = {(f["ticker"].iat[i], f["E"].iat[i]): i for i in range(len(f))}
    ap_idx = np.array(sorted(key3[k] for k in aplus[("core", 3)]), dtype=int)
    mat = (f["mature"].to_numpy() == 1) & el
    a = ap_idx[mat[ap_idx]] if len(ap_idx) else ap_idx
    r = f["realized_r"].to_numpy(dtype=float)
    core = {"n": int(len(a))}
    if len(a):
        ra = r[a]
        wa = f["width_adr"].to_numpy(dtype=float)[a]
        tail = ra >= TAIL_R
        tw = tail & (wa >= TAIL_W)
        core.update(mean_r=float(ra.mean()), ge5_per100=float(100 * (ra >= 5).mean()), mean_pnl_adr=float(f["pnl_adr"].to_numpy(dtype=float)[a].mean()),
                    count_ge10=int(tail.sum()), tail_tickers=int(f["ticker"].iloc[a[tw]].nunique()), tail_months=int(f["fill_month"].iloc[a[tw]].nunique()))
        core["ci_lo"], core["ci_hi"] = boot_ci(ra, f["fill_month"].to_numpy()[a].astype(str), f"aplus|{period}|3|core") if len(a) >= 2 else (float("nan"), float("nan"))
        core["verdict"] = verdict(core, c0)
    rated = ~np.isnan(score_cols["core"]) & ~np.isnan(cutoff[("core", 3)]) & el & mat
    in_ap = np.zeros(len(f), dtype=bool)
    in_ap[ap_idx] = True
    rest = np.flatnonzero(rated & ~in_ap)
    months = f["fill_month"].to_numpy().astype(str)
    pr = paired(r[a], months[a], r[rest], months[rest], f"aplus_pair|{period}|3|core")
    gp = np.array([x == x for x in pd.to_numeric(f["grp_pct"], errors="coerce")])
    ga = np.array(sorted(key3[k] for k in aplus[("grp", 3)]), dtype=int)
    ga = ga[mat[ga] & gp[ga]] if len(ga) else ga
    ca = a[gp[a]] if len(a) else a
    gd = paired(r[ga], months[ga], r[ca], months[ca], f"aplus_pair_grp|{period}|3")
    gd["reading"] = "ADDS" if gd["lo"] > 0 else ("SUBTRACTS" if gd["hi"] < 0 else "CAN'T TELL")
    # the profile re-derived from the 2017-21 tree (the population = the pre fills after the edge rule)
    pf = _read(pre_fills, ["ticker", "E", "K", "entry", "arm"])
    pf = pf[(pf["arm"] == "pp") & (pf["entry"] == "orh5") & (pf["K"] == "tl")]
    population = {(e, t) for t, e in zip(pf["ticker"], pf["E"]) if _in_era(e, "pre")}
    pv, tally = profile_from_tree(Path(pre_minutes), set(early_close), population, log)
    return {"aplus": aplus, "core": core, "paired": pr, "grp": gd, "profile": {"values": pv, "tally": tally}, "n_rows": int(len(f))}


# ═══ #705 (c): the RS-leadership-ALONE re-derivation (rs-alone-read, spec check 8) ═══════════════════════════════════════════════════════
ALONE_FILL_COLS = ["ticker", "D", "E", "K", "entry", "arm", "fill_minute", "fill_month", "width_adr", "mature"]
ALONE_OUTCOME_COLS = ["realized_r", "pnl_adr"]


def spy_calendar(path) -> list:
    """The sorted SPY session dates of the daily export - the ticker and date columns only, in chunks (the export is not date-ordered)."""
    dates = []
    for df in pd.read_csv(path, header=None, usecols=[0, 1], names=["ticker", "date"], dtype=str, keep_default_na=False, chunksize=2_000_000):
        dates += df.loc[df["ticker"] == "SPY", "date"].tolist()
    return sorted(dates)


def rederive_alone_c3(paths: dict, period: str, c0: dict, outcomes: bool = True, log=print) -> dict:
    """The `alone_c3` A+ set (RS leadership, `rs_best` alone, N = 3) computed ITSELF from the source files with pandas - no runner code, no shared
    arithmetic - and, with `outcomes`, n / mean R / the PASS interval / the paired interval / every PASS component. `outcomes=False` (the dry run's
    self-check) opens no outcome column: the A+ set, every eligible fill's score and cutoff only.

    The pool of a fill on E = every fill (the period's table AND, for the sealed era, the trailing fills of the discovery table, pool-only) with E' in
    [E - 20, E - 1] on the SPY calendar; the fill's pct = (worse + 0.5 x equal) / |S|; a member's reference score = (average rank - 1) / (|S| - 1) against
    the pool minus itself; the cutoff = the 12th-highest reference score; A+ = pct >= cutoff and fewer than 3 A+ already taken in the ISO week, in
    (E, fill_minute, ticker) order. Returns {"aplus": {(ticker, E)}, "score": {(ticker, E): pct}, "cutoff": {...}, "core": stats, "paired": {...}}."""
    cols = ALONE_FILL_COLS + (ALONE_OUTCOME_COLS if outcomes else [])
    f = _read(paths["fills"], cols)
    f = f[(f["arm"] == "pp") & (f["entry"] == "orh5") & (f["K"] == "tl")].copy()
    if outcomes:
        r0 = f.loc[f["mature"] == 1, "realized_r"].to_numpy(dtype=float)               # C0 = every mature row of the table, the edge fills included
        c0 = dict(c0, mean_r_exact=float(r0.mean()) if len(r0) else float("nan"), ge5_exact=float(100 * (r0 >= 5).mean()) if len(r0) else float("nan"))
    f["eligible"] = [_in_era(e, period) for e in f["E"]]
    if period == "pre":
        f = f[f["eligible"]]
    if period == "holdout":
        first = f.loc[f["eligible"], "E"].min()
        cut = (dt.date.fromisoformat(first) - dt.timedelta(days=45)).isoformat()           # its own pool-only boundary: any cut >= 20 sessions is the same
        g = _read(paths["pool_fills"], cols)
        g = g[(g["arm"] == "pp") & (g["entry"] == "orh5") & (g["K"] == "tl") & (g["E"] >= cut)].copy()
        g["eligible"] = False
        f = pd.concat([g, f], ignore_index=True)
    f = f.sort_values(["E", "fill_minute", "ticker"]).reset_index(drop=True)
    log(f"  re-derivation (alone_c3): {len(f):,} rows ({int(f['eligible'].sum()):,} eligible)")
    cal = spy_calendar(paths["export"])
    ci_of = {d: k for k, d in enumerate(cal)}
    f["E_ci"] = f["E"].map(ci_of).astype(int)
    cc = _read(paths["cands"], ["ticker", "D", "E", "K", "rs_best"])
    cc = cc[cc["K"] == "tl"]
    f = f.merge(cc, on=["ticker", "D", "E", "K"], how="left", validate="one_to_one")
    vals = pd.to_numeric(f["rs_best"], errors="coerce").to_numpy(dtype=float)
    E_ci = f["E_ci"].to_numpy()
    el = f["eligible"].to_numpy()
    score, cutoff = np.full(len(f), np.nan), np.full(len(f), np.nan)
    for e in sorted(set(E_ci[el])):
        day = np.flatnonzero(E_ci == e)
        pool = np.flatnonzero((E_ci >= e - POOL) & (E_ci <= e - 1))
        S = pd.Series(vals[pool]).dropna()
        n = len(S)
        if n >= FLOOR:
            score[day] = [pct_against(S, x) if x == x else np.nan for x in vals[day]]
        if n - 1 >= FLOOR:
            ref = np.sort(((S.rank(method="average") - 1) / (n - 1)).to_numpy())[::-1]
            if len(ref) >= RANK[3]:
                cutoff[day] = ref[RANK[3] - 1]
    taken, chosen = defaultdict(int), set()
    weeks = [_week(e) for e in f["E"]]
    for i in range(len(f)):
        if not el[i]:
            continue
        if score[i] == score[i] and cutoff[i] == cutoff[i] and score[i] >= cutoff[i] and taken[weeks[i]] < 3:
            taken[weeks[i]] += 1
            chosen.add((f["ticker"].iat[i], f["E"].iat[i]))
    out = {"aplus": chosen, "n_rows": int(len(f)),
           "score": {(f["ticker"].iat[i], f["E"].iat[i]): float(score[i]) for i in np.flatnonzero(el)},
           "cutoff": {(f["ticker"].iat[i], f["E"].iat[i]): float(cutoff[i]) for i in np.flatnonzero(el)}}
    if not outcomes:
        return out
    key3 = {(f["ticker"].iat[i], f["E"].iat[i]): i for i in range(len(f))}
    ap_idx = np.array(sorted(key3[k] for k in chosen), dtype=int)
    mat = (f["mature"].to_numpy() == 1) & el
    a = ap_idx[mat[ap_idx]] if len(ap_idx) else ap_idx
    r = f["realized_r"].to_numpy(dtype=float)
    core = {"n": int(len(a))}
    if len(a):
        ra = r[a]
        wa = f["width_adr"].to_numpy(dtype=float)[a]
        tail = ra >= TAIL_R
        tw = tail & (wa >= TAIL_W)
        core.update(mean_r=float(ra.mean()), ge5_per100=float(100 * (ra >= 5).mean()), mean_pnl_adr=float(f["pnl_adr"].to_numpy(dtype=float)[a].mean()),
                    count_ge10=int(tail.sum()), tail_tickers=int(f["ticker"].iloc[a[tw]].nunique()), tail_months=int(f["fill_month"].iloc[a[tw]].nunique()))
        core["ci_lo"], core["ci_hi"] = boot_ci(ra, f["fill_month"].to_numpy()[a].astype(str), f"aplus|{period}|3|alone_c3") if len(a) >= 2 else (float("nan"), float("nan"))
        core["verdict"] = verdict(core, c0)
    rated = ~np.isnan(score) & ~np.isnan(cutoff) & el & mat
    in_ap = np.zeros(len(f), dtype=bool)
    in_ap[ap_idx] = True
    rest = np.flatnonzero(rated & ~in_ap)
    months = f["fill_month"].to_numpy().astype(str)
    out.update(core=core, paired=paired(r[a], months[a], r[rest], months[rest], f"aplus_pair|{period}|3|alone_c3"))
    return out
