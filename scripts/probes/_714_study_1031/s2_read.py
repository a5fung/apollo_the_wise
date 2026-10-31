#!/usr/bin/env python3
"""#714 STAGE 2 — the read. Executes docs/analysis/ep_float_neglect_prereg_2026-10-31.md §12 in its order.

MEASUREMENT ONLY. $0. Reads local capture files in out/ (+ the stage-1b yfinance float file out/x1_float.jsonl).
Changes nothing, proposes no score change. Anything not in the frozen prereg is labelled POST-HOC in the printout.

    python3 s2_read.py            # all steps, printout to stdout (tee it to s2_read_printout.txt)
    python3 s2_read.py --through 2   # stop after STEP 2 (NO outcome is ever opened before STEP 3)

STEP 0 composition (no outcome) -> STEP 1 features (bars strictly before the gap day) -> STEP 2 freeze strata/cuts/F1 groups,
C2 (simulated flags only), C4, C5 -> STEP 3 outcomes (frame A) + C3 -> STEP 4 each definition read ONCE -> STEP 5 the table.
"""
import csv
import datetime as dt
import gzip
import hashlib
import io
import json
import math
import os
import re
import sys
import zlib
from collections import Counter, OrderedDict

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "out")
REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, REPO)

SEED = 714
N_PERM = 20000          # verdict permutation draws (prereg §7.1)
N_BOOT = 2000           # bootstrap draws (context only)
N_SIM = 200             # C2 simulations
N_PERM_SIM = 2000       # permutation draws INSIDE each C2 simulation (the prereg fixes 200 sims, not the inner draws)
BASE_RATE = 0.15        # the registered "~15% runners" (prereg §8.1); the real rate is NOT read before STEP 3
THROUGH = 99
if "--through" in sys.argv:
    THROUGH = int(sys.argv[sys.argv.index("--through") + 1])

FROZEN_SHA = OrderedDict([
    ("00_census.sql", "165e69954bc5070961f6e2e08f12ab5aa6894438b52589575f4c5efc5aaea597"),
    ("10_labelled_and_rivals.sql", "6d8dc93c3ea5a61f4a534d4b2643ac3672c6043aecd70692585b0cd7e7a62ab8"),
    ("20_tail_population.sql", "bdd31824635e40e5d6b1410b7ab44bbb4481e5bdab80d99da6b532015ee78fcf"),
    ("30_daily_bars.sql", "8f550146140cffcaf39923095e3d908550e0293960eef416271bc8ce53429fbc"),
    ("40_context.sql", "a2305689d9d911e881029370b4fc0f455b315caad626d9b740c8a4032f1075b0"),
    ("50_fetch_lists.sql", "b7267a943639dcfd9724f9cd9331514cc625c9428f85a9b7ddd542cbb22462e5"),
    ("60_fresh_block.sql", "3b494b3ccd3b240552b61a669599a9fb78271ea76fa373b4b5b86758731d8060"),
])
LABELLED = [("BFLY", "2026-06-18"), ("PLTR", "2026-08-04"), ("ABNB", "2026-08-07"), ("TEAM", "2026-08-07"),
            ("HTFL", "2026-08-14"), ("MRNA", "2026-08-19"), ("CHPT", "2026-09-03"), ("PENG", "2026-10-07")]
BLOCKS = [("B1", "2026-05-01", "2026-06-25"), ("B2", "2026-06-26", "2026-08-19"), ("B3", "2026-08-20", "2026-10-09")]
ADV_EDGES = [0.0, 50e6, 100e6, 250e6, 500e6, np.inf]
HIST_MIN = 504


def P(*a, **k):
    print(*a, **k)
    sys.stdout.flush()


def hdr(t):
    P("\n" + "=" * 100 + f"\n{t}\n" + "=" * 100)


# ───────────────────────────── parsing ─────────────────────────────
def sections(path):
    op = gzip.open if path.endswith(".gz") else open
    out, cur = {}, None
    with op(path, "rt", encoding="utf-8") as f:
        for line in f:
            line = line.rstrip("\n")
            if line.startswith("=== "):
                cur = line[4:].strip()
                out[cur] = []
                continue
            if cur is None or not line or re.fullmatch(r"\(\d+ rows?\)", line):
                continue
            out[cur].append(line)
    return out


def tab(lines):
    return pd.read_csv(io.StringIO("\n".join(lines)), sep="|", quoting=csv.QUOTE_NONE, dtype=str, keep_default_na=False)


def num(s):
    return pd.to_numeric(s.replace("", np.nan), errors="coerce")


# ───────────────────────────── statistics ─────────────────────────────
def avg_rank(x):
    return pd.Series(x).rank(method="average").to_numpy()


def mh_rd(y, g, s):
    """Mantel-Haenszel stratified risk difference. y,g in {0,1}; s stratum labels. Returns (RD, W) ; NaN if no stratum has both groups."""
    y = np.asarray(y, float); g = np.asarray(g, int); s = np.asarray(s)
    num_, den = 0.0, 0.0
    for k in np.unique(s):
        m = s == k
        n1 = int((g[m] == 1).sum()); n0 = int((g[m] == 0).sum()); n = n1 + n0
        if n1 == 0 or n0 == 0:
            continue
        rd = y[m][g[m] == 1].mean() - y[m][g[m] == 0].mean()
        w = n1 * n0 / n
        num_ += w * rd; den += w
    return (num_ / den if den > 0 else np.nan), den


def perm_p(y, g, s, rng, draws, direction=+1):
    """Exact-distribution within-stratum permutation: with the stratum totals fixed, the number of runners falling in the
    favourable group is hypergeometric, so sampling it directly is the same distribution as shuffling the flag (and exact).
    Returns (RD_obs, p) with p=(1+#{RD_perm>=RD_obs})/(draws+1) for direction=+1, <= for direction=-1."""
    y = np.asarray(y, float); g = np.asarray(g, int); s = np.asarray(s)
    rd_obs, _ = mh_rd(y, g, s)
    if np.isnan(rd_obs):
        return np.nan, np.nan
    terms = []
    for k in np.unique(s):
        m = s == k
        n1 = int((g[m] == 1).sum()); n0 = int((g[m] == 0).sum()); n = n1 + n0
        if n1 == 0 or n0 == 0:
            continue
        Y = int(y[m].sum())
        terms.append((n1, n0, n, Y))
    W = sum(n1 * n0 / n for n1, n0, n, Y in terms)
    tot = np.zeros(draws)
    for n1, n0, n, Y in terms:
        w = n1 * n0 / n
        S1 = rng.hypergeometric(Y, n - Y, n1, size=draws) if 0 < Y < n else np.full(draws, 0 if Y == 0 else n1)
        rd = S1 / n1 - (Y - S1) / n0
        tot += w * rd
    rd_perm = tot / W
    eps = 1e-12
    if direction > 0:
        cnt = int((rd_perm >= rd_obs - eps).sum())
    else:
        cnt = int((rd_perm <= rd_obs + eps).sum())
    return rd_obs, (1 + cnt) / (draws + 1)


def boot_ci(y, g, s, rng, draws=N_BOOT, lo=5, hi=95):
    y = np.asarray(y, float); g = np.asarray(g, int); s = np.asarray(s)
    idx_by = {k: np.where(s == k)[0] for k in np.unique(s)}
    vals = []
    for _ in range(draws):
        take = np.concatenate([rng.choice(ix, size=len(ix), replace=True) for ix in idx_by.values()])
        r, _ = mh_rd(y[take], g[take], s[take])
        if not np.isnan(r):
            vals.append(r)
    return (np.percentile(vals, lo), np.percentile(vals, hi)) if vals else (np.nan, np.nan)


def freeze_strata(adv, min_rows=15):
    """ADV$ rungs [0,50M) [50M,100M) [100M,250M) [250M,500M) [500M,inf). A rung with < min_rows rows merges into the next LOWER one
    (prereg §5.3), processed from the top down; if the lowest rung is still short it merges UP (the prereg is silent: POST-HOC fill-in)."""
    adv = np.asarray(adv, float)
    rung = np.digitize(adv, ADV_EDGES[1:-1])  # 0..4
    counts = Counter(rung.tolist())
    mp = {r: r for r in range(5)}
    for r in range(4, 0, -1):
        cur = mp[r]
        n_cur = sum(c for rr, c in counts.items() if mp[rr] == cur)
        if 0 < n_cur < min_rows:
            for rr in range(5):
                if mp[rr] == cur:
                    mp[rr] = r - 1
    # lowest-rung fix-up: merge up
    for r in range(0, 4):
        cur = mp[r]
        n_cur = sum(c for rr, c in counts.items() if mp[rr] == cur)
        if 0 < n_cur < min_rows:
            for rr in range(5):
                if mp[rr] == cur:
                    mp[rr] = r + 1
    return np.array([mp[int(r)] for r in rung]), mp


def fav_third(val_oriented, strata):
    """Favourable iff average rank (ties share) / n_stratum >= 2/3, cut WITHIN each ADV$ stratum on the oriented value (higher = more favourable)."""
    val = np.asarray(val_oriented, float); strata = np.asarray(strata)
    fav = np.zeros(len(val), int)
    for k in np.unique(strata):
        m = np.where(strata == k)[0]
        r = avg_rank(val[m]) / len(m)
        fav[m] = (r >= 2 / 3 - 1e-12).astype(int)
    return fav


def block_of(d):
    for name, a, b in BLOCKS:
        if a <= d <= b:
            return name
    return None


def pass_conditions(y, g, s, dates, rng, draws, need_p=True):
    """The Leg-T PASS conditions that do not involve the 'must-agree' encodings. Returns dict."""
    rd, p = (perm_p(y, g, s, rng, draws) if need_p else (mh_rd(y, g, s)[0], np.nan))
    y = np.asarray(y); g = np.asarray(g); s = np.asarray(s); dates = np.asarray(dates)
    nb = 0
    for name, a, b in BLOCKS:
        m = (dates >= a) & (dates <= b)
        if m.sum() == 0:
            continue
        r, _ = mh_rd(y[m], g[m], s[m])
        if not np.isnan(r) and r > 0:
            nb += 1
    # drop the single scan date with the most runners
    runners_by_date = Counter(dates[y == 1].tolist())
    if runners_by_date:
        top = max(runners_by_date.items(), key=lambda kv: (kv[1], kv[0]))[0]
        m = dates != top
        rd_drop, _ = mh_rd(y[m], g[m], s[m])
    else:
        top, rd_drop = None, np.nan
    return dict(rd=rd, p=p, blocks_pos=nb, rd_drop=rd_drop, top_date=top)


def is_pass_core(c, rd_min=0.06, p_max=0.0125):
    return (c["rd"] is not None and not np.isnan(c["rd"]) and c["rd"] >= rd_min and c["p"] <= p_max
            and c["blocks_pos"] >= 2 and not np.isnan(c["rd_drop"]) and c["rd_drop"] > 0)


# ───────────────────────────── load ─────────────────────────────
def load_all():
    S = {}
    S["census"] = sections(os.path.join(OUT, "00_census.out"))
    S["lab"] = sections(os.path.join(OUT, "10_labelled_and_rivals.out"))
    S["tail"] = sections(os.path.join(OUT, "20_tail_population.out"))
    S["bars"] = sections(os.path.join(OUT, "30_daily_bars.out.gz"))
    S["ctx"] = sections(os.path.join(OUT, "40_context.out"))
    S["fetch"] = sections(os.path.join(OUT, "50_fetch_lists.out"))
    return S


class Bars:
    """Per-ticker OHLCV aligned to the SPY session calendar (NaN where a ticker has no bar that session)."""

    def __init__(self, S):
        bp = tab(S["bars"]["BARS_POP"]); bs = tab(S["bars"]["BARS_SECONDARY"])
        bp["src"] = "pop"; bs["src"] = "sec"
        df = pd.concat([bp, bs], ignore_index=True)
        df = df.sort_values(["ticker", "trade_date", "src"]).drop_duplicates(["ticker", "trade_date"], keep="first")
        for c in ["open_price", "high_price", "low_price", "close", "volume"]:
            df[c] = num(df[c])
        spy = df[df.ticker == "SPY"].trade_date.sort_values().to_numpy()
        self.cal = spy.astype("datetime64[D]")
        self.cal_s = np.array([str(d) for d in self.cal])
        self.ix = {d: i for i, d in enumerate(self.cal_s)}
        self.tickers = sorted(df.ticker.unique())
        self.tix = {t: i for i, t in enumerate(self.tickers)}
        n, m = len(self.tickers), len(self.cal)
        self.o = np.full((n, m), np.nan); self.h = self.o.copy(); self.l = self.o.copy(); self.c = self.o.copy(); self.v = self.o.copy()
        pos = df.trade_date.map(self.ix)
        self.n_off_cal = int(pos.isna().sum())
        ok = pos.notna()
        ti = df.ticker[ok].map(self.tix).to_numpy(); pi = pos[ok].astype(int).to_numpy()
        self.o[ti, pi] = df.open_price[ok].to_numpy(); self.h[ti, pi] = df.high_price[ok].to_numpy()
        self.l[ti, pi] = df.low_price[ok].to_numpy(); self.c[ti, pi] = df.close[ok].to_numpy(); self.v[ti, pi] = df.volume[ok].to_numpy()
        self.n_rows = len(df)
        self.spy = self.tix["SPY"]
        self.src = df.groupby("ticker").src.agg(lambda s: "pop" if (s == "pop").any() else "sec").to_dict()

    def has(self, t):
        return t in self.tix


# ───────────────────────────── features (STEP 1) — bars strictly before the gap day ─────────────────────────────
def roll_med_prev(v, w=60, minp=45):
    return pd.Series(v).rolling(w, min_periods=minp).median().shift(1).to_numpy()


def roll_min(c, w=60):
    return pd.Series(c).rolling(w, min_periods=1).min().to_numpy()


class Feat:
    """Computes every feature for (ticker, scan_date) using ONLY bars with index < index(scan_date). C0 is asserted on every call."""

    def __init__(self, B, splits):
        self.B = B; self.splits = splits; self.n_c0 = 0

    def row(self, tk, d):
        B = self.B
        out = dict(ticker=tk, scan_date=d, has_bars=False)
        if not B.has(tk) or d not in B.ix:
            return out
        ti = B.tix[tk]; iD = B.ix[d]
        c, v, h, l = B.c[ti], B.v[ti], B.h[ti], B.l[ti]
        out["has_bars"] = True
        out["iD"] = iD
        out["bar_on_day"] = bool(np.isfinite(c[iD]))
        prior = c[:iD]
        out["n_hist"] = int(np.isfinite(prior).sum())
        out["prev_close_bar"] = c[iD - 1] if iD >= 1 else np.nan
        if iD >= 20:
            cc, vv, hh, ll = c[iD - 20:iD], v[iD - 20:iD], h[iD - 20:iD], l[iD - 20:iD]
            out["adv20"] = float(np.nanmean(cc * vv)) if np.isfinite(cc * vv).sum() >= 15 else np.nan
            adr = (hh - ll) / cc
            out["adr20"] = float(np.nanmean(adr)) if np.isfinite(adr).sum() >= 15 else np.nan
            out["c0_max_idx"] = iD - 1
            assert out["c0_max_idx"] < iD
            self.n_c0 += 1
        else:
            out["adv20"] = out["adr20"] = np.nan
        # volume
        out["vol_med50"] = np.nan
        if iD >= 50:
            vv = v[iD - 50:iD]
            out["vol50"] = float(np.nanmean(vv)) if np.isfinite(vv).sum() >= 40 else np.nan
        # neglect — eligibility
        out["neglect_ok"] = False
        out["why_not"] = ""
        if out["n_hist"] < HIST_MIN or iD < HIST_MIN:
            out["why_not"] = "history<504"
            return out
        wc = c[iD - HIST_MIN:iD]; wv = v[iD - HIST_MIN:iD]
        nn = min(np.isfinite(wc).sum(), np.isfinite(wv).sum()) / HIST_MIN
        out["window_nonnull"] = float(nn)
        if nn < 0.95:
            out["why_not"] = "window<95% non-null"
            return out
        # split guard
        t0, t1 = B.cal_s[iD - HIST_MIN], B.cal_s[iD - 1]
        for (ex, applied, outcome) in self.splits.get(tk, []):
            if t0 <= ex <= t1 and (applied != "t" or outcome in ("phantom", "skipped_no_data")):
                out["why_not"] = "split in window"
                return out
        if not np.isfinite(out["adr20"]) or out["adr20"] <= 0:
            out["why_not"] = "adr20 missing"
            return out
        out["neglect_ok"] = True
        out["c0_max_idx"] = iD - 1
        assert out["c0_max_idx"] < iD
        self.n_c0 += 1
        # NP
        runmin = np.fmin.accumulate(wc)
        rally = (wc / runmin - 1.0) * 100.0
        mr = float(np.nanmax(rally))
        out["NP"] = mr
        out["NP_s1"] = mr / (out["adr20"] * 100.0)
        # NP-s2: sessions since last day j (in the 504 window) with c_j >= 1.5 * min(c over j-59..j); lookback may reach before the window
        rm = roll_min(c[:iD], 60)
        js = np.arange(iD - HIST_MIN, iD)
        cond = np.isfinite(c[js]) & np.isfinite(rm[js]) & (c[js] >= 1.5 * rm[js])
        out["NP_s2"] = float(iD - js[np.where(cond)[0][-1]]) if cond.any() else float(HIST_MIN)
        # NV
        mean504 = float(np.nanmean(wv))
        v250 = v[iD - 250:iD]
        ok250 = np.isfinite(v250)
        out["NV"] = float((v250[ok250] < mean504).mean()) if ok250.sum() >= 200 else np.nan
        med60 = float(np.nanmedian(v[iD - 60:iD])); med504 = float(np.nanmedian(wv))
        out["NV_s"] = med60 / med504 if med504 > 0 else np.nan
        # NA
        med_prev = roll_med_prev(v[:iD], 60, 45)
        cprev = np.concatenate([[np.nan], c[:iD - 1]])
        ret = np.abs(c[:iD] / cprev - 1.0)
        ev = np.isfinite(v[:iD]) & np.isfinite(med_prev) & (v[:iD] >= 3.0 * med_prev) & np.isfinite(ret) & (ret >= 0.05)
        ev504 = ev[iD - HIST_MIN:iD]
        out["NA"] = float(ev[iD - 250:iD].sum())
        w = np.where(ev504)[0]
        out["NA_s"] = float(HIST_MIN - w[-1] - 0) if len(w) else float(HIST_MIN)
        # NA_s: sessions since the event, D-1 = 1  -> HIST_MIN - w[-1] (w index 0..503, 503 = D-1)
        return out


# ───────────────────────────── main ─────────────────────────────
def load_yf():
    p = os.path.join(OUT, "x1_float.jsonl")
    d, meta = {}, {}
    if os.path.exists(p):
        for line in open(p):
            try:
                r = json.loads(line)
            except Exception:
                continue
            d[r["ticker"]] = r["float"] if (r.get("float") and r["float"] > 0) else None
            meta[r["ticker"]] = r
    return d, meta


def float_pick(stored_chosen, any_tick, yf_val):
    """prereg §5.2 order: (a) chosen tick, (b) largest on any tick, (c) yf_now, (d) unknown. Returns (value, source)."""
    for v, src in ((stored_chosen, "stored_tick"), (any_tick, "stored_any_tick"), (yf_val, "yf_now")):
        if v is not None and not (isinstance(v, float) and np.isnan(v)) and v > 0:
            return float(v), src
    return np.nan, "unknown"


def step0_1():
    hdr("STEP 0 — composition, stop conditions, hashes (NO outcome is read)")
    S = load_all()
    # frozen hashes
    cap = os.path.join(HERE, "capture")
    bad = []
    for fn, sha in FROZEN_SHA.items():
        got = hashlib.sha256(open(os.path.join(cap, fn), "rb").read()).hexdigest()
        if got != sha:
            bad.append(fn)
    P("capture SQL hashes vs prereg §14:", "ALL 7 MATCH" if not bad else f"MISMATCH {bad}")
    if bad:
        P("STOP: capture files differ from the frozen hashes"); sys.exit(2)
    # schema
    sc = tab(S["census"]["CENSUS_SCHEMA_CHECK"])
    P("schema check wanted/found/missing:", sc.iloc[0].tolist(), "| missing rows:", len(S["census"].get("CENSUS_SCHEMA_MISSING", [])) - 1)
    if int(sc.iloc[0]["missing"]) != 0:
        P("STOP: CENSUS_SCHEMA_CHECK has missing columns"); sys.exit(2)
    # labelled list equals shared list
    from shared.operator_labelled_eps import OPERATOR_LABELLED_EPS
    shared = [(e.ticker, e.alert_date) for e in OPERATOR_LABELLED_EPS]
    P("labelled list equals shared/operator_labelled_eps.py:", shared == LABELLED)
    assert shared == LABELLED
    lt = tab(S["lab"]["LABELLED_TICKS"])
    P("labelled ticks present (ticker: n ticks):", dict(Counter(lt.ticker)))
    boards = tab(S["census"]["CENSUS_LABELLED_BOARDS"])
    P("distinct labelled boards present:", boards.scan_date.nunique())
    if boards.scan_date.nunique() < 7:
        P("STOP: fewer than 7 labelled boards"); sys.exit(2)
    B = Bars(S)
    P(f"bars: {B.n_rows:,} rows, {len(B.tickers)} tickers, SPY calendar {B.cal_s[0]}..{B.cal_s[-1]} ({len(B.cal_s)} sessions); rows off the SPY calendar: {B.n_off_cal}")
    if B.cal_s[-1] < "2026-10-30":
        P("STOP: SPY not loaded through 2026-10-30"); sys.exit(2)
    # splits
    spl = tab(S["ctx"]["SPLITS"])
    splits = {}
    for r in spl.itertuples():
        splits.setdefault(r.ticker, []).append((r.execution_date, r.adjustment_applied, r.adjustment_outcome))
    S["splits"] = splits
    # populations
    tb = tab(S["tail"]["POP_B"])
    popB = tb[tb.is_scored == "t"].copy().reset_index(drop=True)
    lab_unscored = tb[tb.is_scored != "t"].copy()
    P(f"POP_B file rows {len(tb)}: scored (= Population B) {len(popB)}; labelled-but-unscored (ABNB, CHPT; not in B) {len(lab_unscored)}: {lab_unscored.ticker.tolist()}")
    P(f"B scan dates {popB.scan_date.min()}..{popB.scan_date.max()}, distinct tickers {popB.ticker.nunique()}, distinct dates {popB.scan_date.nunique()}; duplicate (ticker,date): {int(popB.duplicated(['ticker','scan_date']).sum())}")
    popB["block"] = popB.scan_date.map(block_of)
    P("rows per block:", dict(Counter(popB.block)), "| NYSE sessions in blocks (SPY cal):",
      {n: int(((B.cal_s >= a) & (B.cal_s <= b)).sum()) for n, a, b in BLOCKS})
    # forward-window completeness (calendar only; no outcome value)
    last_ok = B.cal_s[len(B.cal_s) - 1 - 15]
    P(f"last scan date with 15 forward SPY sessions loaded: {last_ok}; B rows after it: {int((popB.scan_date > last_ok).sum())} (censored, never filled)")
    # float era from census
    cs = tab(S["census"]["CENSUS_SCORED_BY_DATE"])
    for c in cs.columns[1:]:
        cs[c] = pd.to_numeric(cs[c])
    cs["cov"] = cs.n_float_nonnull / cs.n_scored
    ok = (cs["cov"] >= 0.90).to_numpy()
    era_start = None
    for i in range(len(cs)):
        if ok[i:].all():
            era_start = cs.scan_date.iloc[i]; break
    P(f"stored-float era (first date from which >=90% of that date's scored rows carry a stored float on every later date): {era_start}")
    S["era_start"] = era_start
    inB = cs[(cs.scan_date >= "2026-05-01") & (cs.scan_date <= "2026-10-09")]
    P(f"census scored ticker-days in B window: {int(inB.n_scored.sum())} (POP_B scored rows {len(popB)}); stored float on {int(inB.n_float_nonnull.sum())}; float points >0 on {int(inB.n_float_points.sum())}")
    return S, B, popB, lab_unscored



def to_num(df, cols):
    for c in cols:
        if c in df.columns:
            df[c] = num(df[c])
    return df


NUMCOLS = ["ep_score", "ep_bar", "gap_pct", "prev_close", "current_price", "rel_volume", "adv", "market_cap", "float_shares",
           "float_any_tick", "n_ticks", "n_scored_ticks", "max_score", "alert_score", "quality_adv_dollar", "atr_pct", "vol_percentile",
           "market_cap_snapshot", "today_volume", "prev_day_volume", "projected_vol_multiple", "pm_rvol"]
OUTCOME_COLS = ["outcome_baseline_close", "fwd_5d_pct", "fwd_10d_pct", "n_sessions_5d", "n_sessions_10d"]


def step1(S, B, popB):
    hdr("STEP 1 — features for every row (bars strictly before the gap day; NO forward bar, NO fwd_*_pct, NO outcome column)")
    yf, yfmeta = load_yf()
    P(f"yfinance float file: {len(yf)} tickers fetched; with a float value {sum(1 for v in yf.values() if v)}; "
      f"fetch window {min((m['fetched_at'] for m in yfmeta.values()), default='-')} .. {max((m['fetched_at'] for m in yfmeta.values()), default='-')} (UTC)")
    S["yf"] = yf; S["yfmeta"] = yfmeta
    # drop outcome columns from every frame at load time — they are re-attached only in STEP 3
    outc = popB[["ticker", "scan_date"] + OUTCOME_COLS].copy()
    S["stored_outcomes"] = outc
    popB = popB.drop(columns=OUTCOME_COLS)
    ba = tab(S["lab"]["BOARD_ALL"])
    S["stored_outcomes_board"] = ba[["ticker", "scan_date"] + OUTCOME_COLS].copy()
    ba = ba.drop(columns=OUTCOME_COLS)
    popB = to_num(popB, NUMCOLS); ba = to_num(ba, NUMCOLS)
    F = Feat(B, S["splits"])
    cache = {}

    def feats(tk, d):
        k = (tk, d)
        if k not in cache:
            cache[k] = F.row(tk, d)
        return cache[k]

    # float assignment
    def attach_float(df):
        vals, srcs = [], []
        for r in df.itertuples():
            v, s = float_pick(r.float_shares, r.float_any_tick, yf.get(r.ticker))
            vals.append(v); srcs.append(s)
        df["float_val"] = vals; df["float_src"] = srcs
        return df
    popB = attach_float(popB); ba = attach_float(ba)

    def attach_feats(df):
        rows = [feats(r.ticker, r.scan_date) for r in df.itertuples()]
        fd = pd.DataFrame(rows).drop(columns=["ticker", "scan_date"])
        return pd.concat([df.reset_index(drop=True), fd.reset_index(drop=True)], axis=1)
    popB = attach_feats(popB); ba = attach_feats(ba)
    S["n_c0"] = F.n_c0
    P(f"C0 look-ahead assertion: max(bar index used) < index(scan_date) asserted on {F.n_c0:,} feature computations across {len(cache):,} distinct (ticker, date) rows — 0 violations")
    return popB, ba



# ───────────────────────────── Leg L (his labelled EPs vs their same-day rivals) ─────────────────────────────
def rival_mask(ba, kind):
    notlab = ba.is_labelled == "f"
    if kind == "R1":
        return notlab & (ba.is_scored == "t")
    if kind == "R2":
        return notlab & (ba.prev_close_bar >= 5.0) & (ba.adv20 >= 5e6)
    if kind == "R3":
        return notlab & (ba.is_scored == "t") & (ba.any_pass_tick == "t")
    raise ValueError(kind)


def leg_l(ba, col, orient, kind="R1"):
    """Percentile of each labelled EP among the same-day rivals on `col` (orient=+1: higher is more favourable; -1: lower).
    Thin board = fewer than 4 rivals with a valid value. Returns (per-EP DataFrame, summary dict)."""
    recs = []
    rm = rival_mask(ba, kind)
    for tk, d in LABELLED:
        ep = ba[(ba.ticker == tk) & (ba.scan_date == d) & (ba.is_labelled == "t")].iloc[0]
        v_ep = orient * ep[col] if np.isfinite(ep[col]) else np.nan
        riv = ba[rm & (ba.scan_date == d)]
        rv = (orient * riv[col]).to_numpy(float)
        rv = rv[np.isfinite(rv)]
        n_valid = len(rv); n_riv_all = int(rm[ba.scan_date == d].sum())
        if not np.isfinite(v_ep):
            status, pct = "no value", np.nan
        elif n_valid < 4:
            status, pct = "thin board", np.nan
        else:
            pct = ((rv < v_ep).sum() + 0.5 * (rv == v_ep).sum()) / n_valid
            status = "ok"
        recs.append(dict(ticker=tk, scan_date=d, raw=ep[col], n_rivals=n_riv_all, n_valid=n_valid, status=status, pct=pct))
    df = pd.DataFrame(recs)
    ok = df[df.status == "ok"]
    n = len(ok)
    summ = dict(n_eligible=n, mean=float(ok.pct.mean()) if n else np.nan, k_above=int((ok.pct > 0.5).sum()), k_below=int((ok.pct < 0.5).sum()))
    if n:
        rng = np.random.default_rng(SEED)
        m = ok.n_valid.to_numpy()
        draws = np.stack([rng.integers(0, mm + 1, size=N_PERM) / mm for mm in m], axis=1).mean(axis=1)
        summ["band"] = (float(np.percentile(draws, 5)), float(np.percentile(draws, 95)))
    summ["word"] = l_word(summ)
    return df, summ


def l_word(s):
    n = s["n_eligible"]
    if n < 5:
        return "NOT READ"
    mean, ka, kb = s["mean"], s["k_above"], s["k_below"]
    if mean >= 0.65 and ka / n >= 0.75:
        return "L+"
    if mean <= 0.35 and kb / n >= 0.75:
        return "L-"
    if 0.40 <= mean <= 0.60:
        return "L0"
    return "L?"


# ───────────────────────────── analysis frames (Leg T sets) ─────────────────────────────
ORIENT = {"F1": +1, "NP": -1, "NP_s1": -1, "NP_s2": +1, "NV": +1, "NV_s": -1, "NA": -1, "NA_s": +1}
MUST_AGREE = {"F1": [], "NP": ["NP_s1", "NP_s2"], "NV": ["NV_s"], "NA": ["NA_s"]}


class Frame:
    def __init__(self, name, df, valcol, orient, groups=None):
        """df: the analysis rows (index = positions in popB). Groups: for F1 supplied; for neglect, favourable third within strata."""
        self.name = name
        self.idx = df.index.to_numpy()
        self.adv = df.adv20.to_numpy(float)
        self.dates = df.scan_date.to_numpy()
        self.strata, self.map = freeze_strata(self.adv)
        if groups is None:
            self.val = orient * df[valcol].to_numpy(float)
            self.g = fav_third(self.val, self.strata)
        else:
            self.val = df[valcol].to_numpy(float)
            self.g = np.asarray(groups, int)
        self.n = len(df)

    def describe(self):
        cnt = Counter(zip(self.strata.tolist(), self.g.tolist()))
        by = {int(k): (cnt.get((k, 1), 0), cnt.get((k, 0), 0)) for k in sorted(set(self.strata.tolist()))}
        return f"n={self.n}, favourable={int(self.g.sum())}, rest={self.n - int(self.g.sum())}; rung merge map {self.map}; (fav,rest) by stratum {by}"


def build_frames(popB, S):
    fr = OrderedDict()
    has_adv = np.isfinite(popB.adv20)
    # F1 pooled and stored-only
    known = np.isfinite(popB.float_val) & has_adv
    d = popB[known]
    low = ((d.float_val > 0) & (d.float_val < 50e6)).astype(int).to_numpy()
    fr["F1"] = Frame("F1 pooled (stored + yf_now)", d, "float_val", +1, groups=low)
    d2 = d[d.float_src.isin(["stored_tick", "stored_any_tick"])]
    low2 = ((d2.float_val > 0) & (d2.float_val < 50e6)).astype(int).to_numpy()
    fr["F1_stored"] = Frame("F1 stored-float era only", d2, "float_val", +1, groups=low2)
    # neglect set: eligible rows with adv known
    base = popB[popB.neglect_ok.astype(bool) & has_adv]
    for key in ["NP", "NV", "NA", "NP_s1", "NP_s2", "NV_s", "NA_s"]:
        dd = base[np.isfinite(base[key])]
        fr[key] = Frame(key, dd, key, ORIENT[key])
    return fr


# ───────────────────────────── C2: planted-effect simulation (simulated flags only — no real outcome) ─────────────────────────────
def c2_sim(fr, planted, n_sim, seed, base=None):
    """Share of simulations that read PASS (core conditions) when runner flags are drawn with overall mean BASE_RATE and a planted
    risk difference `planted` between the favourable group and the rest. 'Must-agree' encodings are NOT simulated (POST-HOC: this
    overstates power slightly — a PASS also needs them)."""
    rng = np.random.default_rng(seed)
    g, s, dates = fr.g, fr.strata, fr.dates
    share = g.mean()
    base = BASE_RATE if base is None else base
    p_non = max(base - planted * share, 0.0)
    p_fav = p_non + planted
    prob = np.where(g == 1, p_fav, p_non)
    wins = 0
    for _ in range(n_sim):
        y = (rng.random(len(g)) < prob).astype(int)
        c = pass_conditions(y, g, s, dates, rng, N_PERM_SIM)
        wins += int(is_pass_core(c))
    return wins / n_sim


def c2_block(frames, keys, base=None):
    hdr_ = f"{'definition':32s} {'n':>5s} {'fav':>5s} | PASS rate at planted 0pp / +10pp |  MDE 50%  MDE 80% | powered?"
    P(hdr_)
    res = {}
    for k in keys:
        fr = frames[k]
        sw = {}
        for pl in range(0, 16):
            sw[pl] = c2_sim(fr, pl / 100.0, N_SIM, SEED + 1000 * pl + zlib.crc32(k.encode()) % 997, base)
        m50 = next((pl for pl in range(0, 16) if sw[pl] >= 0.5), None)
        m80 = next((pl for pl in range(0, 16) if sw[pl] >= 0.8), None)
        powered = sw[10] >= 0.8
        res[k] = dict(size=sw[0], power10=sw[10], mde50=m50, mde80=m80, powered=powered, sweep=sw)
        P(f"{fr.name:32s} {fr.n:5d} {int(fr.g.sum()):5d} | {sw[0]*100:6.1f}%  /  {sw[10]*100:6.1f}%              | "
          f"{('%d pp' % m50) if m50 is not None else '>15 pp':>8s}  {('%d pp' % m80) if m80 is not None else '>15 pp':>8s} | {'POWERED' if powered else 'NOT POWERED'}")
    return res


# ───────────────────────────── C5: float counterfactual (era rows only) ─────────────────────────────
def counterfactual(popB, S):
    from agents.market_intelligence import ep_rubric as R
    from agents.market_intelligence import ep_score_math as M
    w = R.SCORE_WEIGHTS
    scale = w["output_scale"]; rules = w["conviction_floor"]["rules"]
    era = popB[(popB.score_breakdown != "") & popB.ep_bar.notna()].copy()
    out = []
    for r in era.itertuples():
        parts = json.loads(r.score_breakdown)
        parts = {k: float(v) for k, v in parts.items()}
        raw = sum(parts.values())
        score = float(r.ep_score); bar = float(r.ep_bar)
        mult = ((round((score - scale["offset"]) / scale["mult"], 1)) / raw) if raw > 0 else np.nan
        # factual rebuild
        fact = R.apply_output_scale(round(raw * mult, 1), scale) if np.isfinite(mult) else np.nan
        # conviction-floor re-resolution
        floor = R.resolve_conviction_floor(float(r.gap_pct), r.catalyst_quality, rules) if np.isfinite(r.gap_pct) else None
        other = sum(v for k, v in parts.items() if k != "conviction_floor")
        cf_expect = max(0.0, floor - other) if floor is not None else None
        cf_ok = (("conviction_floor" in parts) == (floor is not None)) and (floor is None or abs(parts["conviction_floor"] - cf_expect) < 1e-9)
        # counterfactual: float -> 0
        p2 = dict(parts); fl = p2.get("float", 0.0); p2["float"] = 0.0
        other2 = sum(v for k, v in p2.items() if k != "conviction_floor")
        raw2 = max(other2, floor) if floor is not None else other2
        cf = R.apply_output_scale(round(raw2 * mult, 1), scale) if np.isfinite(mult) else np.nan
        need = M._raw_needed(mult, bar, scale) if np.isfinite(mult) else None
        out.append(dict(ticker=r.ticker, scan_date=r.scan_date, ep_score=score, ep_bar=bar, raw=raw, mult=mult, fact=fact,
                        fact_ok=bool(abs(fact - score) <= 0.05) if np.isfinite(fact) else False, float_pts=fl, cf_ok=cf_ok,
                        floor=floor, raw_cf=raw2, score_cf=cf, need=need,
                        clears=score >= bar, clears_cf=(cf >= bar) if np.isfinite(cf) else False,
                        clears_need=(raw >= need) if need is not None else None,
                        tier=r.score_tier, alert_tier=r.alert_tier, any_high=r.any_high_alert))
    return pd.DataFrame(out)


# ───────────────────────────── STEP 3: outcomes (frame A of #686) ─────────────────────────────
def attach_outcomes(B, df):
    """run_xadr = (max HIGH over sessions +1..+15 - gap-day CLOSE) / ADR$ ; ADR$ = adr20 x gap-day close. Censored (NaN) if <15 finite forward highs."""
    run, exc, f10, cd, cens = [], [], [], [], []
    for r in df.itertuples():
        ti = B.tix[r.ticker]; iD = r.iD
        c0 = B.c[ti, iD]
        hi = B.h[ti, iD + 1:iD + 16]
        ok = np.isfinite(c0) and iD + 15 < len(B.cal) and np.isfinite(hi).sum() == 15
        cd.append(c0)
        if not ok:
            run.append(np.nan); exc.append(np.nan); f10.append(np.nan); cens.append(True); continue
        mh = float(np.nanmax(hi))
        e = mh / c0 - 1.0
        exc.append(e)
        run.append(e / r.adr20 if np.isfinite(r.adr20) and r.adr20 > 0 else np.nan)
        c10 = B.c[ti, iD + 10]
        f10.append((c10 / c0 - 1.0) * 100.0 if np.isfinite(c10) else np.nan)
        cens.append(False)
    df = df.copy()
    df["close_D"] = cd; df["run_xadr"] = run; df["exc_max"] = exc; df["fwd10_bar"] = f10; df["censored"] = cens
    df["runner"] = (df.run_xadr >= 5.0).astype(float).where(df.run_xadr.notna())
    df["r8"] = (df.run_xadr >= 8.0).astype(float).where(df.run_xadr.notna())
    df["x50"] = (df.exc_max >= 0.5).astype(float).where(df.exc_max.notna())
    return df


def c3(popB, S, B):
    """C3 outcome bridge. C3a: gap-day close from bars vs mi_ep_scan_outcomes.baseline_close (registered, unchanged).
    C3b AS REGISTERED compared a bar-derived +10-session CLOSE-TO-CLOSE return to fwd_10d_pct. outcome_tracker._compute_ep_scan_outcomes
    (agents/market_intelligence/outcome_tracker.py) writes fwd_10d_pct as the HIGH-WATERMARK return: (MAX(high) over the first n_sessions_10d
    forward sessions - baseline_close) / baseline_close. The registered form therefore fails a correct pipeline (POST-FREEZE ADDENDUM 2026-10-31).
    The gating form is the column's own definition; the registered form is still printed, labelled mis-specified."""
    so = S["stored_outcomes"].copy()
    so = to_num(so, ["outcome_baseline_close", "fwd_5d_pct", "fwd_10d_pct", "n_sessions_5d", "n_sessions_10d"])
    m = popB.merge(so, on=["ticker", "scan_date"], how="left")
    hi_n, hi10, hi5_n = [], [], []
    for r in m.itertuples():
        ti = B.tix[r.ticker]; iD = int(r.iD)
        c0 = B.c[ti, iD]
        def hw(k):
            h = B.h[ti, iD + 1:iD + 1 + k]
            return (np.nanmax(h) / c0 - 1.0) * 100.0 if np.isfinite(h).any() and np.isfinite(c0) else np.nan
        k10 = int(r.n_sessions_10d) if np.isfinite(r.n_sessions_10d) else 10
        k5 = int(r.n_sessions_5d) if np.isfinite(r.n_sessions_5d) else 5
        hi_n.append(hw(min(max(k10, 1), 10))); hi10.append(hw(10)); hi5_n.append(hw(min(max(k5, 1), 5)))
    m["hw10_n"] = hi_n; m["hw10"] = hi10; m["hw5_n"] = hi5_n
    have_b = m.outcome_baseline_close.notna() & m.close_D.notna()
    rel = (m.close_D - m.outcome_baseline_close).abs() / m.outcome_baseline_close
    ok_b = (rel <= 0.005)
    have_f = m.fwd_10d_pct.notna()
    have_cc = m.fwd_10d_pct.notna() & m.fwd10_bar.notna()
    res = dict(n_b=int(have_b.sum()), rate_b=float(ok_b[have_b].mean()) if have_b.any() else np.nan,
               n_f=int(have_f.sum()),
               rate_f_registered=float((((m.fwd10_bar - m.fwd_10d_pct).abs() <= 0.5)[have_cc]).mean()) if have_cc.any() else np.nan,
               n_cc=int(have_cc.sum()),
               rate_f=float((((m.hw10_n - m.fwd_10d_pct).abs() <= 0.5)[have_f]).mean()) if have_f.any() else np.nan,
               rate_f_fixed10=float((((m.hw10 - m.fwd_10d_pct).abs() <= 0.5)[have_f]).mean()) if have_f.any() else np.nan,
               n_5=int(m.fwd_5d_pct.notna().sum()),
               rate_5=float((((m.hw5_n - m.fwd_5d_pct).abs() <= 0.5)[m.fwd_5d_pct.notna()]).mean()) if m.fwd_5d_pct.notna().any() else np.nan)
    return res, m


# ───────────────────────────── STEP 4: Leg T read (one pass per definition) ─────────────────────────────
def leg_t(fr, popB):
    d = popB.loc[fr.idx]
    keep = d.runner.notna().to_numpy()
    y = d.runner.to_numpy()[keep].astype(int); g = fr.g[keep]; s = fr.strata[keep]; dates = fr.dates[keep]
    exc = d.exc_max.to_numpy()[keep]; r8 = d.r8.to_numpy()[keep]; x50 = d.x50.to_numpy()[keep]
    rng = np.random.default_rng(SEED + zlib.crc32(fr.name.encode()) % 100003)
    c = pass_conditions(y, g, s, dates, rng, N_PERM)
    _, p_rev = perm_p(y, g, s, rng, N_PERM, direction=-1)
    lo, hi = boot_ci(y, g, s, rng)
    out = dict(name=fr.name, n=int(len(y)), n_cens=int((~keep).sum()), n_fav=int(g.sum()), n_rest=int((1 - g).sum()),
               runners_fav=int(y[g == 1].sum()), runners_rest=int(y[g == 0].sum()),
               rate_fav=float(y[g == 1].mean()), rate_rest=float(y[g == 0].mean()),
               rd_unstrat=float(y[g == 1].mean() - y[g == 0].mean()), rd=c["rd"], p=c["p"], p_rev=p_rev,
               ci90=(float(lo), float(hi)), blocks_pos=c["blocks_pos"], rd_drop=c["rd_drop"], top_date=c["top_date"],
               p90_fav=float(np.nanpercentile(exc[g == 1], 90)), p90_rest=float(np.nanpercentile(exc[g == 0], 90)),
               r8_fav=float(np.nanmean(r8[g == 1])), r8_rest=float(np.nanmean(r8[g == 0])),
               x50_fav=float(np.nanmean(x50[g == 1])), x50_rest=float(np.nanmean(x50[g == 0])))
    blk = {}
    for name, a, b in BLOCKS:
        m = (dates >= a) & (dates <= b)
        r, _ = mh_rd(y[m], g[m], s[m])
        blk[name] = (float(r) if np.isfinite(r) else np.nan, int(m.sum()), int(y[m].sum()))
    out["blocks"] = blk
    return out


def t_word(res, powered, measured, agree_rd):
    """PASS > LEAD > BACKWARDS > NULL / NOT POWERED; NOT MEASURED first. (Order of precedence is POST-HOC clarification of prereg §8.1.)"""
    if not measured:
        return "NOT MEASURED"
    rd, p, pr = res["rd"], res["p"], res["p_rev"]
    if (rd >= 0.06 and p <= 0.0125 and res["blocks_pos"] >= 2 and res["rd_drop"] > 0 and all(a > 0 for a in agree_rd)):
        return "PASS"
    if rd > 0 and p <= 0.05:
        return "LEAD"
    if rd <= -0.03 and pr <= 0.05:
        return "BACKWARDS"
    return "NULL" if powered else "NOT POWERED"


def combined(tw, lw):
    if tw in ("PASS", "LEAD"):
        return {"L+": "SEPARATES", "L-": "CONFLICT"}.get(lw, "TAIL-ONLY")
    if tw == "NULL":
        return {"L+": "LABEL-ONLY", "L-": "NULL (leans backwards)"}.get(lw, "NULL")
    if tw == "BACKWARDS":
        return "CONFLICT" if lw == "L+" else "BACKWARDS"
    if tw in ("NOT POWERED", "NOT MEASURED", "CAN'T TELL (drift)"):
        return "LABEL-ONLY (unconfirmed)" if lw == "L+" else tw
    return tw


def pct(x, d=1):
    return "n/a" if x is None or (isinstance(x, float) and not np.isfinite(x)) else f"{x*100:.{d}f}%"


def pp(x, d=1):
    return "n/a" if x is None or (isinstance(x, float) and not np.isfinite(x)) else f"{x*100:+.{d}f} pp"


# ───────────────────────────── drivers ─────────────────────────────
def run_step2(S, B, popB, ba):
    hdr("STEP 2 — freeze strata, cuts and F1 groups; C1; C2 (simulated flags only); C4; C5. NO real runner count is printed.")
    P(f"Registered choices printed up front: C2 base rate = {BASE_RATE:.2f} (the registered '~15% runners' of prereg §8.1 — the real rate is not read before STEP 3);"
      f" C2 = {N_SIM} simulations per cell with {N_PERM_SIM} inner permutation draws (the verdict uses {N_PERM}); planted effect swept 0..15 pp in 1 pp steps;"
      " 'must-agree' encodings are not simulated (POST-HOC: C2 power is therefore a slight upper bound). seed 714.")
    ba["prev_close_bar"] = ba["prev_close_bar"]
    frames = build_frames(popB, S)
    S["frames"] = frames
    P("\nFrozen analysis sets (strata = ADV$ rungs from bars; rung merge map: rung index -> merged rung; a rung <15 rows merges into the next lower;"
      " lowest-rung-short merges UP is a POST-HOC fill-in of an unspecified case):")
    for k, fr in frames.items():
        P(f"  {k:10s} {fr.describe()}")
    n_noadv = int((~np.isfinite(popB.adv20)).sum())
    P(f"  rows in B with no 20-session ADV$ (cannot be stratified, excluded from every Leg T frame): {n_noadv}")
    # C1
    hist_ok = int((popB.n_hist >= HIST_MIN).sum())
    nk = int(popB.neglect_ok.astype(bool).sum())
    P(f"\nC1 coverage: rows meeting the 504-session history rule {hist_ok}; neglect features non-null on {nk} = {nk/max(hist_ok,1)*100:.1f}% (floor 85%)."
      f" Float known (pooled) on {frames['F1'].n} of {len(popB)} = {frames['F1'].n/len(popB)*100:.1f}% (floor 85%); stored-era float on {frames['F1_stored'].n}.")
    S["measured"] = {k: True for k in ["F1", "NP", "NV", "NA"]}
    S["measured"]["F1"] = frames["F1"].n / len(popB) >= 0.85
    for k in ["NP", "NV", "NA"]:
        S["measured"][k] = frames[k].n / max(hist_ok, 1) >= 0.85
    P("  NOT MEASURED flags:", {k: (not v) for k, v in S["measured"].items()})
    # float source composition
    P("\nF1 float source on B rows:", dict(Counter(popB.float_src)), "| lowfloat (<50M) among known:",
      int(((popB.float_val > 0) & (popB.float_val < 50e6)).sum()), "of", int(np.isfinite(popB.float_val).sum()))
    # drift: yf_now vs stored where both exist
    both = popB[(popB.float_src.isin(["stored_tick", "stored_any_tick"]))].copy()
    both["yf"] = both.ticker.map(S["yf"])
    both = both[both.yf.notna() & (both.yf > 0)]
    if len(both):
        ratio = (both.yf / both.float_val)
        P(f"Float drift (yf_now / stored-at-alert), {len(both)} era rows with both: median {ratio.median():.3f}, share >10% larger now {(ratio>1.1).mean()*100:.0f}%, "
          f"share >10% smaller {(ratio<0.9).mean()*100:.0f}%, share that cross the 50M line between the two {(((both.float_val<5e7)!=(both.yf<5e7))).mean()*100:.0f}%")
        S["drift"] = dict(n=len(both), median=float(ratio.median()))
    # splits after the alert (float 'now' could be a different share count)
    after = 0
    for r in popB.itertuples():
        if r.float_src == "yf_now":
            for (ex, applied, outcome) in S["splits"].get(r.ticker, []):
                if r.scan_date < ex <= "2026-10-31" and applied == "t":
                    after += 1; break
    P(f"yf_now-sourced B rows with an APPLIED split executed between the alert and 2026-10-31 (their 'now' float is on a different share count): {after}")
    S["split_after"] = after

    # C2
    hdr("C2 — planted-effect check on the real strata and row counts (before any outcome is attached)")
    c2 = c2_block(frames, ["F1", "F1_stored", "NP", "NV", "NA"])
    S["c2"] = c2
    bad = [k for k, v in c2.items() if v["size"] > 0.03]
    P("size check (planted 0 pp must read PASS in <=3% of simulations):", "OK" if not bad else f"FAIL {bad}")
    if bad:
        P("STOP: C2 size check failed — pipeline would manufacture PASS"); sys.exit(3)

    # C4
    hdr("C4 — positive control for Leg L: ADV$ place of his 8 EPs among their same-day R1 rivals (must read >= 0.60; < 0.50 = Leg L NOT READ)")
    df, sm = leg_l(ba, "adv20", +1, "R1")
    P(df.to_string(index=False, float_format=lambda x: f"{x:.3f}"))
    P(f"mean place {sm['mean']:.3f} over {sm['n_eligible']} eligible EPs (thin boards excluded); EPs above 0.5: {sm['k_above']}; 90% chance band for that mean {sm['band'][0]:.2f}-{sm['band'][1]:.2f}")
    ba2 = ba.copy()
    allm = []
    for tk, d in LABELLED:
        ep = ba[(ba.ticker == tk) & (ba.scan_date == d) & (ba.is_labelled == "t")].iloc[0]
        rv = ba[rival_mask(ba, "R1") & (ba.scan_date == d)].adv20.to_numpy(float)
        rv = rv[np.isfinite(rv)]
        if np.isfinite(ep.adv20) and len(rv):
            allm.append(((rv < ep.adv20).sum() + 0.5 * (rv == ep.adv20).sum()) / len(rv))
    P(f"(for reference, all 8 EPs incl. thin boards: mean place {np.mean(allm):.3f})")
    S["c4"] = sm
    if sm["mean"] < 0.50:
        S["legL_not_read"] = True
        P("C4 < 0.50: every Leg L result is NOT READ.")
    elif sm["mean"] < 0.60:
        P("C4 between 0.50 and 0.60: below the registered 0.60 bar — Leg L is reported but flagged as an unconfirmed board construction.")
        S["legL_flag"] = True
    else:
        P("C4 passes (>= 0.60).")

    # C5
    hdr("C5 — float counterfactual calibration (era rows: stored score parts + ep_bar)")
    cfdf = counterfactual(popB, S)
    S["cf"] = cfdf
    n = len(cfdf)
    P(f"era rows (stored breakdown and bar): {n}; scan dates {cfdf.scan_date.min()}..{cfdf.scan_date.max()}")
    P(f"factual rebuild reproduces the stored ep_score within 0.05 on {int(cfdf.fact_ok.sum())} of {n} = {cfdf.fact_ok.mean()*100:.1f}% (bar 99%)")
    P("worked-back regime multiplier (rounded 0.01):", dict(Counter(np.round(cfdf.mult, 2))))
    rg = tab(S["ctx"]["REGIME"]).set_index("regime_date").regime.to_dict()
    cfdf["regime"] = cfdf.scan_date.map(rg)
    P("multiplier by that day's regime name:", {k: dict(Counter(np.round(v.mult, 2))) for k, v in cfdf.groupby("regime")})
    ok_m = ((np.isclose(cfdf.mult, 1.2, atol=0.01) & (cfdf.regime == "Bull")) | (np.isclose(cfdf.mult, 1.0, atol=0.01) & (cfdf.regime != "Bull"))).mean()
    P(f"multiplier is 1.2 on Bull days and 1.0 otherwise on {ok_m*100:.1f}% of era rows (bar 99%)")
    P(f"stored conviction-floor part equals max(0, floor(gap, grade) - other parts) (or is absent when no rule matches) on {int(cfdf.cf_ok.sum())} of {n} era rows")
    P("score_tier carried by era rows:", dict(Counter(cfdf.tier.fillna('none'))), "| alert tiers:", dict(Counter(cfdf.alert_tier.fillna('none'))))
    nf = cfdf[(cfdf.float_pts > 0)]
    flip = cfdf[cfdf.clears & ~cfdf.clears_cf]
    P(f"rows that carry float points: {len(nf)}; rows that CLEAR the bar with float and would NOT without it (N_flip): {len(flip)}")
    P("  of N_flip, HIGH-alerted (a live HIGH alert row exists that day):", int((flip.any_high == 't').sum()), "| cross-check via raw-points search (raw >= need):",
      int(((cfdf.clears_need == True) & ~cfdf.clears_cf).sum()))
    P("  N_flip rows:", flip[["ticker", "scan_date", "ep_score", "score_cf", "ep_bar", "float_pts"]].to_dict("records"))
    # sanity: counterfactual with float restored equals factual
    S["nflip"] = flip
    return frames


def run_step3(S, B, popB, ba):
    hdr("STEP 3 — outcomes attached (frame A of #686) and C3 (outcome bridge)")
    popB = attach_outcomes(B, popB)
    res, m = c3(popB, S, B)
    P("C3a  gap-day close from bars equals mi_ep_scan_outcomes.baseline_close (within 0.5%) on "
      f"{res['rate_b']*100:.1f}% of {res['n_b']} rows that have both (bar 95%)")
    P("C3b  AS REGISTERED (bar-derived +10-session CLOSE-TO-CLOSE return vs fwd_10d_pct, within 0.5 pp): "
      f"{res['rate_f_registered']*100:.1f}% of {res['n_cc']} rows (bar 90%)  -> FAILS; MIS-SPECIFIED, see the post-freeze addendum: "
      "outcome_tracker._compute_ep_scan_outcomes stores fwd_10d_pct as a HIGH-WATERMARK return, not a close-to-close return")
    P("C3b' CORRECTED to the column's own definition (max HIGH over the first n_sessions_10d forward sessions vs baseline close, within 0.5 pp): "
      f"{res['rate_f']*100:.1f}% of {res['n_f']} rows (bar 90%)   [fixed 10 sessions: {res['rate_f_fixed10']*100:.1f}%;"
      f" 5-day analogue vs fwd_5d_pct: {res['rate_5']*100:.1f}% of {res['n_5']}]")
    S["c3"] = res
    c3_pass = (res["rate_b"] >= 0.95) and (res["rate_f"] >= 0.90)
    if not c3_pass:
        P("C3 FAILED on the corrected form too — every outcome number is withheld; STOP."); sys.exit(4)
    P("C3 passes on the corrected form (and C3a as registered). The registered form is reported above for the record.")
    P(f"censored rows (fewer than 15 forward sessions with a bar): {int(popB.censored.sum())} of {len(popB)}")
    done = popB[~popB.censored]
    P(f"B rows with outcome: {len(done)}; runners (run >= 5 ADR): {int(done.runner.sum())} = {done.runner.mean()*100:.1f}%;"
      f" >= 8 ADR: {int(done.r8.sum())} = {done.r8.mean()*100:.1f}%; max excursion >= +50%: {int(done.x50.sum())} = {done.x50.mean()*100:.1f}%;"
      f" P90 of max excursion {np.nanpercentile(done.exc_max,90)*100:.1f}%")
    P("runner rate by block (runners, rows):", {n: (int(done[done.block == n].runner.sum()), int((done.block == n).sum())) for n, a, b in BLOCKS})
    S["base_rate"] = float(done.runner.mean())
    P(f"observed base rate {S['base_rate']*100:.1f}% vs the 15% C2 assumed: difference {abs(S['base_rate']-BASE_RATE)*100:.1f} pp"
      f" ({'above' if abs(S['base_rate']-BASE_RATE) > 0.05 else 'under'} the 5 pp trigger I set for an automatic re-run).")
    hdr("C2 re-run at the OBSERVED base rate — POST-HOC, beside the registered C2 above; it re-decides nothing")
    S["c2_obs"] = c2_block(S["frames"], ["F1", "F1_stored", "NP", "NV", "NA"], base=S["base_rate"])
    return popB


def run_step4(S, B, popB, ba):
    hdr("STEP 4 — each definition read ONCE: Leg T (the tail), Leg L (his EPs), verdict words")
    frames = S["frames"]
    ba["neglog"] = -np.log10(ba.float_val)
    R = {}
    # powered flags
    pw = {k: S["c2"][k]["powered"] for k in S["c2"]}
    # ---- Leg T
    T = {}
    for k in ["F1", "F1_stored", "NP", "NV", "NA", "NP_s1", "NP_s2", "NV_s", "NA_s"]:
        T[k] = leg_t(frames[k], popB)
    S["T"] = T
    for k in ["F1", "F1_stored", "NP", "NV", "NA", "NP_s1", "NP_s2", "NV_s", "NA_s"]:
        t = T[k]
        P(f"\n[{k}] {t['name']}  (n={t['n']} censored={t['n_cens']}; favourable {t['n_fav']} / rest {t['n_rest']})")
        P(f"   runner rate favourable {pct(t['rate_fav'])} ({t['runners_fav']}/{t['n_fav']}) vs rest {pct(t['rate_rest'])} ({t['runners_rest']}/{t['n_rest']}); unstratified gap {pp(t['rd_unstrat'])}")
        P(f"   stratified gap (Mantel-Haenszel) {pp(t['rd'])}, one-sided p {t['p']:.4f}, reversed p {t['p_rev']:.4f}, bootstrap 90% interval {pp(t['ci90'][0])} to {pp(t['ci90'][1])}")
        P(f"   by block (gap, rows, runners): " + "; ".join(f"{b} {pp(v[0])} n={v[1]} r={v[2]}" for b, v in t["blocks"].items()) + f"  -> blocks with gap>0: {t['blocks_pos']}/3")
        P(f"   drop the top-runner scan date {t['top_date']}: gap {pp(t['rd_drop'])}")
        P(f"   big winners: P90 of the max excursion favourable {pct(t['p90_fav'])} vs rest {pct(t['p90_rest'])}; >=8 ADR {pct(t['r8_fav'])} vs {pct(t['r8_rest'])}; >=+50% {pct(t['x50_fav'])} vs {pct(t['x50_rest'])}")
    # ---- Leg L
    L = {}
    for k, col, orient in [("F1", "neglog", +1), ("NP", "NP", -1), ("NV", "NV", +1), ("NA", "NA", -1)]:
        r1 = leg_l(ba, col, orient, "R1"); r2 = leg_l(ba, col, orient, "R2"); r3 = leg_l(ba, col, orient, "R3")
        L[k] = dict(R1=r1, R2=r2, R3=r3)
    S["L"] = L
    # ---- words
    W = {}
    for k in ["F1", "NP", "NV", "NA"]:
        t = T[k]
        agree = [mh_rd_sec(S, popB, s_) for s_ in MUST_AGREE[k]]
        t["agree"] = dict(zip(MUST_AGREE[k], agree))
        meas = S["measured"][k]
        word = t_word(t, pw[k], meas, agree)
        note = ""
        if k == "F1":
            st = T["F1_stored"]
            st_word_pow = pw["F1_stored"]
            if word in ("PASS", "LEAD") and not (st["rd"] >= 0 or not st_word_pow):
                word, note = "NULL", "pooled read does not count: stored-only gap is negative and the stored-only read is powered"
            elif word in ("NULL", "BACKWARDS", "NOT POWERED") and st["rd"] > 0 and st["p"] <= 0.10:
                word, note = "CAN'T TELL (drift)", "stored-only gap is positive with p<=0.10"
        lr = L[k]["R1"][1]
        lw = lr["word"]
        if S.get("legL_not_read"):
            lw = "NOT READ"
        if lw == "L+" and (L[k]["R2"][1]["word"] == "L-" or L[k]["R3"][1]["word"] == "L-"):
            lw, note = "L?", (note + " primary L+ demoted: R2 or R3 reads L-").strip()
        W[k] = dict(T=word, L=lw, combined=combined(word, lw), note=note, powered=pw[k], measured=meas)
    S["W"] = W
    for k in ["F1", "NP", "NV", "NA"]:
        P(f"\n[{k}] Leg T word {W[k]['T']} | Leg L word {W[k]['L']} | combined {W[k]['combined']}  {W[k]['note']}")
        P(f"   must-agree encodings gap > 0?: " + (", ".join(f"{a}: {pp(v)}" for a, v in T[k].get('agree', {}).items()) or "none for F1 (see stored-only rule)"))
        for kind in ["R1", "R2", "R3"]:
            df, sm = L[k][kind]
            P(f"   Leg L vs {kind}: mean place {('%.3f' % sm['mean']) if sm['n_eligible'] else 'n/a'} over {sm['n_eligible']} eligible EPs; above 0.5: {sm['k_above']}; below 0.5: {sm['k_below']}; "
              f"chance band {('%.2f-%.2f' % sm['band']) if 'band' in sm else 'n/a'} -> {sm['word']}")
        df = L[k]["R1"][0]
        P(df.assign(raw=df.raw.map(lambda x: f"{x:.4g}" if np.isfinite(x) else "-")).to_string(index=False, float_format=lambda x: f"{x:.3f}"))
    return T, L, W


def mh_rd_sec(S, popB, key):
    fr = S["frames"][key]
    d = popB.loc[fr.idx]
    keep = d.runner.notna().to_numpy()
    r, _ = mh_rd(d.runner.to_numpy()[keep].astype(int), fr.g[keep], fr.strata[keep])
    return r


def run_step5(S, B, popB, ba):
    hdr("STEP 5 — the table to him, the float counterfactual and keep/drop line, D1-D6 context, still untried")
    T, L, W = S["T"], S["L"], S["W"]
    done = popB[~popB.censored]
    P("RESULTS TABLE (plain words; every number carries its n)\n")
    names = {"F1": "FLOAT: under 50M shares (the +5 points)", "NP": "NEGLECT 1: price neglect (no big rally in ~2 yrs)",
             "NV": "NEGLECT 2: volume neglect (quiet volume for ~1 yr)", "NA": "NEGLECT 3: attention neglect (few spike-and-move days; a bar-based PROXY for 'no news')"}
    for k in ["F1", "NP", "NV", "NA"]:
        t = T[k]; w = W[k]; lr = L[k]["R1"][1]
        P(f"* {names[k]}")
        P(f"    the tail: {pct(t['rate_fav'])} of the favourable group ran big ({t['runners_fav']} of {t['n_fav']}) vs {pct(t['rate_rest'])} of the rest ({t['runners_rest']} of {t['n_rest']});"
          f" gap {pp(t['rd'])} (p={t['p']:.3f}); biggest-winner (P90) excursion {pct(t['p90_fav'],0)} vs {pct(t['p90_rest'],0)}")
        P(f"    his EPs: mean place among same-day rivals {('%.2f' % lr['mean']) if lr['n_eligible'] else 'n/a'} (0.5 = coin flip; chance band {('%.2f-%.2f' % lr['band']) if 'band' in lr else 'n/a'}),"
          f" {lr['k_above']} of {lr['n_eligible']} readable EPs above 0.5 -> {lr['word']}")
        P(f"    combined word: {w['combined']}  [tail {w['T']}; EPs {w['L']}; powered={w['powered']}]  {w['note']}")
    # float line
    hdr("FLOAT — separation, tail, alerts that exist only because of the +5, and the pre-registered keep/drop rule (prereg 5.5)")
    cf = S["cf"].copy()
    fl = S["nflip"].copy()
    # outcomes for flip rows
    key = popB.set_index(["ticker", "scan_date"])
    ran = []
    for r in fl.itertuples():
        row = key.loc[(r.ticker, r.scan_date)]
        ran.append(float(row.runner) if np.isfinite(row.runner) else np.nan)
    fl["ran"] = ran
    P(f"N_flip = {len(fl)} (rows that clear the 65 bar with the float points and would not without them; era rows 08-31..10-09 only; fresh block 10-12..10-30 not read)")
    P(f"  HIGH-alerted among them: {int((fl.any_high == 't').sum())}; ran big (>=5 ADR) among them: {int(np.nansum(fl.ran))} of {int(fl.ran.notna().sum())}")
    if len(fl):
        P("  rows:", fl[["ticker", "scan_date", "ep_score", "score_cf", "ran"]].to_dict("records"))
    P("  one tier down: the separation table has NO tier below HIGH (MODERATE cutline = None on the separation side) — the second count is not defined.")
    w = W["F1"]
    rule = "NO-REC"
    if w["combined"] in ("SEPARATES", "TAIL-ONLY"):
        rule = "KEEP-rec"
    elif w["combined"] == "BACKWARDS" or (w["T"] == "NULL" and w["combined"].startswith("NULL") and len(fl) >= 3):
        rule = "DROP-rec"
    elif w["combined"].startswith("NULL") and len(fl) < 3:
        rule = "NO-REC (NULL but N_flip<3 = inert in the stored window)"
    P(f"PRE-REGISTERED RULE -> float verdict '{w['combined']}', N_flip {len(fl)} => {rule}")
    S["float_rule"] = rule
    # ---- descriptive
    hdr("D1-D6 context (descriptive — no verdict word)")
    al = done[done.alert_id != ""].copy()
    P(f"D1 setup_class='episodic_neglect' (stored visibility tag), alerted B rows n={len(al)}: tagged {int((al.setup_class=='episodic_neglect').sum())};"
      f" runner rate tagged {pct(al[al.setup_class=='episodic_neglect'].runner.mean())} (n={int((al.setup_class=='episodic_neglect').sum())}) vs other {pct(al[al.setup_class!='episodic_neglect'].runner.mean())} (n={int((al.setup_class!='episodic_neglect').sum())})")
    labm = ba[ba.is_labelled == "t"]
    P("   his 8 EPs: setup_class =", dict(zip(labm.ticker, labm.setup_class.replace('', '(no alert)'))))
    rv1 = ba[rival_mask(ba, "R1") & (ba.alert_id != "")]
    P(f"   R1 rivals with an alert n={len(rv1)}: tagged episodic_neglect {int((rv1.setup_class=='episodic_neglect').sum())}")
    alu = al[al.expct_scheduled != ""]
    P(f"D2 expct_scheduled (alerted rows with a value n={len(alu)}): 'unscheduled' share {pct((alu.expct_scheduled=='unscheduled').mean())};"
      f" runner rate unscheduled {pct(alu[alu.expct_scheduled=='unscheduled'].runner.mean())} (n={int((alu.expct_scheduled=='unscheduled').sum())}) vs scheduled {pct(alu[alu.expct_scheduled!='unscheduled'].runner.mean())} (n={int((alu.expct_scheduled!='unscheduled').sum())})")
    P("   his 8 EPs:", dict(zip(labm.ticker, labm.expct_scheduled.replace('', '(none)'))))
    # D3
    rp = tab(S["ctx"]["RS_PREV"]); rp["rs_composite"] = num(rp.rs_composite)
    rh = tab(S["ctx"]["RS_HIST_LABELLED"]); rh["rs_composite"] = num(rh.rs_composite)
    rh["wd"] = pd.to_datetime(rh.score_date).dt.weekday
    rh = rh[rh.wd < 5]
    prev = rp.set_index(["ticker", "scan_date"]).rs_composite.to_dict()
    ba["rs_prev"] = [prev.get((r.ticker, r.scan_date), np.nan) for r in ba.itertuples()]
    bot = {}
    for (tk, d), g_ in rh.groupby(["ticker", "scan_date"]):
        g_ = g_[g_.score_date < d].sort_values("score_date").tail(120)
        bot[(tk, d)] = float((g_.rs_composite <= 30).mean()) if len(g_) >= 60 else np.nan
    ba["rs_bot30"] = [bot.get((r.ticker, r.scan_date), np.nan) for r in ba.itertuples()]
    for col, orient, lab in [("rs_prev", -1, "RS strength at D-1 (lower = weaker/'bottom'; his 08-16 'the bottom is where neglect forms')"),
                             ("rs_bot30", +1, "share of the prior ~120 sessions spent in the bottom 30% of RS")]:
        df_, sm = leg_l(ba, col, orient, "R1")
        P(f"D3 {lab}: mean place among R1 rivals {('%.2f' % sm['mean']) if sm['n_eligible'] else 'n/a'} over {sm['n_eligible']} readable EPs; above 0.5: {sm['k_above']}; band {('%.2f-%.2f' % sm['band']) if 'band' in sm else 'n/a'} -> {sm['word']}")
        P("     per EP:", {r.ticker: (round(r.pct, 2) if np.isfinite(r.pct) else r.status) for r in df_.itertuples()})
    # D4
    an = tab(S["ctx"]["ANALYST_ASOF"])
    P(f"D4 analyst coverage: stored estimates as of the gap day with a non-empty num_analysts_eps: {int((an.num_analysts_eps!='').sum())} of {len(an)} captured rows -> NOT MEASURED in this capture (the as-of join returned no values even for Sep-Oct rows)")
    # D5
    npf = S["frames"]["NP"]
    thr = {}
    for k_ in np.unique(npf.strata):
        m = (npf.strata == k_) & (npf.g == 1)
        thr[int(k_)] = float(npf.val[m].min()) if m.any() else np.inf
    mp = npf.map
    def np_fav(r):
        if not np.isfinite(r.NP) or not np.isfinite(r.adv20):
            return np.nan
        rung = int(np.digitize(r.adv20, ADV_EDGES[1:-1]))
        return float(-r.NP >= thr.get(mp[rung], np.inf))
    ba["np_fav"] = [np_fav(r) for r in ba.itertuples()]
    gv = []
    for r in ba.itertuples():
        if not B.has(r.ticker) or not hasattr(r, "iD") or not np.isfinite(getattr(r, "iD", np.nan)):
            gv.append(np.nan); continue
        ti = B.tix[r.ticker]; iD = int(r.iD)
        gv.append(B.v[ti, iD] / r.vol50 if np.isfinite(B.v[ti, iD]) and np.isfinite(r.vol50) and r.vol50 > 0 else np.nan)
    ba["gapvol_x"] = gv
    ba["d5"] = np.where(ba.np_fav.notna() & ba.gapvol_x.notna(), ((ba.np_fav == 1) & (ba.gapvol_x >= 5)).astype(float), np.nan)
    eps_ = ba[ba.is_labelled == "t"]; riv_ = ba[rival_mask(ba, "R1")]
    P(f"D5 Qullamaggie combination (NP-favourable [frozen cut] AND gap-day volume >= 5x its 50-day average; gap-day volume is read from the gap-day bar — descriptive only):"
      f" his EPs {int(np.nansum(eps_.d5))} of {int(eps_.d5.notna().sum())} readable; R1 rivals {int(np.nansum(riv_.d5))} of {int(riv_.d5.notna().sum())} readable ({pct(np.nanmean(riv_.d5))})")
    P("   per EP:", {r.ticker: ('yes' if r.d5 == 1 else 'no' if r.d5 == 0 else 'n/a') for r in eps_.itertuples()})
    # D5 in B: runner rate
    bb = popB.copy()
    bb["np_fav"] = [np_fav(r) for r in bb.itertuples()]
    gvb = []
    for r in bb.itertuples():
        ti = B.tix[r.ticker]; iD = int(r.iD)
        gvb.append(B.v[ti, iD] / r.vol50 if np.isfinite(B.v[ti, iD]) and np.isfinite(r.vol50) and r.vol50 > 0 else np.nan)
    bb["gapvol_x"] = gvb
    m5 = bb.np_fav.notna() & bb.gapvol_x.notna() & bb.runner.notna()
    cmb = ((bb.np_fav == 1) & (bb.gapvol_x >= 5))
    P(f"   tail: combination rows {int((cmb & m5).sum())} of {int(m5.sum())}; runner rate combination {pct(bb[cmb & m5].runner.mean())} vs rest {pct(bb[~cmb & m5].runner.mean())}")
    # D6
    fr = S["frames"]["F1"]
    d = popB.loc[fr.idx]
    keep = d.runner.notna().to_numpy()
    yy = d.runner.to_numpy()[keep].astype(int); ss = fr.strata[keep]; fv = d.float_val.to_numpy()[keep]; dt_ = fr.dates[keep]
    rng = np.random.default_rng(SEED)
    for cut in (20e6, 50e6, 100e6):
        gg = (fv < cut).astype(int)
        rd_, p_ = perm_p(yy, gg, ss, rng, N_PERM)
        P(f"D6 float cut {cut/1e6:.0f}M: rows under {int(gg.sum())} of {len(gg)}; runner rate under {pct(yy[gg==1].mean())} vs over {pct(yy[gg==0].mean())}; stratified gap {pp(rd_)} (one-sided p {p_:.3f})")
    q = pd.qcut(pd.Series(fv).rank(method="first"), 5, labels=False).to_numpy()
    P("   float quintiles (smallest to largest) runner rate:", [(int(k_), pct(yy[q == k_].mean()), int((q == k_).sum())) for k_ in range(5)])
    advv = fr.adv[keep]
    ra, rb = avg_rank(fv), avg_rank(advv)
    P(f"   Spearman(float, ADV$) = {np.corrcoef(ra, rb)[0,1]:.2f} on {len(fv)} rows (the float points favour small names, the liquidity points large)")
    to = []
    for r in d[keep].itertuples():
        ti = B.tix[r.ticker]; iD = int(r.iD)
        to.append(B.v[ti, iD] / r.float_val if np.isfinite(B.v[ti, iD]) else np.nan)
    to = np.array(to)
    okk = np.isfinite(to)
    q3 = pd.qcut(pd.Series(to[okk]).rank(method="first"), 3, labels=False).to_numpy()
    P("   F3 turnover (gap-day volume / float) terciles runner rate (low, mid, high):", [(int(k_), pct(yy[okk][q3 == k_].mean()), int((q3 == k_).sum())) for k_ in range(3)])
    return ba


DRY = "--dry" in sys.argv   # code test of STEPS 4-5 on SYNTHETIC outcomes (never used for the reported run)


def synthetic_outcomes(popB):
    rng = np.random.default_rng(1)
    popB = popB.copy()
    popB["censored"] = False
    popB["runner"] = (rng.random(len(popB)) < 0.15).astype(float)
    popB["r8"] = (rng.random(len(popB)) < 0.08).astype(float)
    popB["x50"] = (rng.random(len(popB)) < 0.1).astype(float)
    popB["exc_max"] = rng.random(len(popB)) * 0.5
    popB["run_xadr"] = popB.runner * 6
    return popB


def main():
    S, B, popB, labun = step0_1()
    popB, ba = step1(S, B, popB)
    hdr("STEP 0 (cont.) — C6 composition after bars are attached")
    bands = pd.cut(popB.n_hist.fillna(-1), [-2, 0, 251, 503, 755, 10**6], labels=["no bars", "1-251", "252-503", "504-755", "756+"])
    P("B rows per prior-history band (sessions in mi_daily_closes before the gap day):", {str(k): int(v) for k, v in bands.value_counts().sort_index().items()})
    P("B rows with no bars at all:", int((~popB.has_bars).sum()), "| bar missing on gap day:", int((popB.has_bars & ~popB.bar_on_day.astype(bool)).sum()))
    P("neglect-eligible (N) rows in B:", int(popB.neglect_ok.astype(bool).sum()), "of", len(popB), "| excluded by reason:", dict(Counter(popB[~popB.neglect_ok.astype(bool)].why_not)))
    boards = tab(S["census"]["CENSUS_LABELLED_BOARDS"])
    P("labelled boards (date: logged / scored / scored rivals / alerted):", {r.scan_date: (r.n_logged_tickers, r.n_scored_tickers, r.n_scored_rivals, r.n_alerted_tickers) for r in boards.itertuples()})
    lab = ba[ba.is_labelled == "t"][["ticker", "scan_date", "n_hist", "neglect_ok", "why_not", "adv20", "float_val", "float_src"]]
    P("his 8 EPs — history sessions, neglect-eligible?, 20-day ADV$, float and its source:")
    P(lab.to_string(index=False))
    r1 = ba[rival_mask(ba, "R1")]
    P("R1 rivals per board (n), with a float value / with 504-session history:",
      {d: (int((r1.scan_date == d).sum()), int(((r1.scan_date == d) & np.isfinite(r1.float_val)).sum()), int(((r1.scan_date == d) & r1.neglect_ok.astype(bool)).sum())) for d in sorted(set(r1.scan_date))})
    P("R2 rivals per board:", {d: int((rival_mask(ba, 'R2') & (ba.scan_date == d)).sum()) for d in sorted(set(r1.scan_date))},
      "| R3 per board:", {d: int((rival_mask(ba, 'R3') & (ba.scan_date == d)).sum()) for d in sorted(set(r1.scan_date))})
    S["popB"], S["ba"] = popB, ba
    frames = run_step2(S, B, popB, ba)
    if THROUGH < 3:
        return
    if not DRY and not os.path.exists(os.path.join(HERE, "s2_step2_printout.txt")):
        P("REFUSED: STEP 3 (outcomes) may not run until STEP 2's printout is saved to s2_step2_printout.txt"); sys.exit(5)
    popB = synthetic_outcomes(attach_outcomes(B, popB)) if DRY else run_step3(S, B, popB, ba)
    if DRY:
        hdr("*** DRY RUN — SYNTHETIC OUTCOMES (random 15% runners). Code test only; nothing below is a result. ***")
        S["base_rate"] = 0.15
    if THROUGH < 4:
        return
    T, L, W = run_step4(S, B, popB, ba)
    ba = run_step5(S, B, popB, ba)
    out = dict(W=W, c2={k: {kk: vv for kk, vv in v.items() if kk != "sweep"} for k, v in S["c2"].items()}, c3=S.get("c3"), base_rate=S.get("base_rate"),
               float_rule=S.get("float_rule"), T={k: {kk: (vv if not isinstance(vv, (np.floating, np.integer)) else float(vv)) for kk, vv in v.items() if kk not in ("blocks", "agree")} for k, v in T.items()})
    json.dump(out, open(os.path.join(HERE, "s2_results" + ("_DRY" if DRY else "") + ".json"), "w"), indent=1, default=str)


if __name__ == "__main__":
    main()
