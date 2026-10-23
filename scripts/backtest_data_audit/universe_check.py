#!/usr/bin/env python3
"""Universe completeness, survivorship and identity audit for a daily-bar export (READ-ONLY, $0, offline).

Why it exists (2026-10-23): the 2016-22 export was built from the symbols Alpaca lists TODAY, so every stock acquired or delisted since is
missing; the same export carries one company under two symbols, symbols that jump companies, and forward-filled bars. Each of those
quietly changes a backtest's population or its tail, and none shows up in the arithmetic. Run this BEFORE trusting any read on an export,
and again whenever an export is rebuilt.

Input format (no header): ticker,date,open,high,low,close,volume.  Any bar later than --cutoff (default 2024-12-31: the 2025-26 table is
SEALED) is dropped at read time and never examined; the script refuses a cutoff of 2025-01-01 or later.

Single-export checks (always run)         Pair checks (need --other, the RICHER export - the one that still carries delisted names)
  integrity   dup keys, NaN, OHLC order     overlap     symbols in one export and not the other, dollar-volume weighted; rename matches
  coverage    tickers per year / per day,   identity_x  per-symbol close ratio + return correlation across the two exports: a symbol
              thin sessions, missing days               that is a different COMPANY on each side is the cross-era reuse signature
  stale       zero-volume rows, carried     gone        liquid names in OTHER whose last bar is before the cutoff, and how many
              closes, frozen OHLCV copies               are missing from the primary export (+ a control group that is still alive)
  dups        one company under two         impact      what the missing names did afterwards (end-of-life return) and how many
              symbols (byte-identical bars)             of the +100%-in-60-sessions runners the primary export cannot see
  breaks      holes > 30 sessions, >70%
              jumps with no volume event, shorter-hole level shifts; compared with --guard

Usage:
  python scripts/backtest_data_audit/universe_check.py --export A.csv.gz [--label A] [--other B.csv.gz --other-label B]
        [--cutoff 2024-12-31] [--guard symbol_guard.tsv] [--splits cb702_splits.psv] [--sic cb702_sic.psv] [--raw-close raw.csv.gz]
        [--liq-dv 2000000] [--liq-px 2] [--out-dir DIR]
Writes <out-dir>/flagged_rows.tsv (check,label,ticker,first,last,n,value,detail) plus coverage_by_year.tsv, gone_list.tsv, pair_identity.tsv,
dup_pairs.tsv.  Every printed number carries its n.  Exit code 0 always (this is a report, not a gate); read the verdict lines.
"""
import argparse
import os
import re
import sys
import time

import numpy as np
import pandas as pd

COLS = ["ticker", "date", "open", "high", "low", "close", "volume"]
SEALED_FROM = pd.Timestamp("2025-01-01")
HOLE_MAX, JUMP_MAX, VOL_EVENT_X = 30, 0.70, 3.0          # the same constants as scripts/probes/_qm_streams/ext_bars.py (the existing guard)
SHORT_HOLE = 10                                          # a hole of 10..30 sessions is invisible to that guard; checked here with a level test
TEST_SYMBOL = re.compile(r"^(Z[A-Z]{0,4}Z?T|[A-Z]?TEST|ZTST|ZBZX|ZIEXT|ZXIET|ZZZZ[A-Z]?)$")   # exchange test symbols (ZVZZT, ZTEST, PTEST, ...)
FLAGS: list = []                                         # accumulated flagged rows


def say(*a):
    print(*a, flush=True)


def flag(check, label, ticker, first="", last="", n="", value="", detail=""):
    FLAGS.append((check, label, ticker, str(first)[:10], str(last)[:10], n, value, detail))


# ───────────────────────── reading ─────────────────────────
class Ex:
    """One export: rows sorted by (ticker, date), a session calendar, per-symbol boundaries."""

    def __init__(self, path, label, cutoff):
        self.path, self.label, self.cutoff = path, label, cutoff
        parts, dropped, bad_date = [], 0, 0
        for ch in pd.read_csv(path, header=None, names=COLS, usecols=range(7), chunksize=2_000_000,
                              keep_default_na=False, na_values=[""],      # a ticker "NA" must stay a ticker
                              dtype={"ticker": str, "date": str, "open": "float64", "high": "float64", "low": "float64", "close": "float64", "volume": "float64"}):
            ch["date"] = pd.to_datetime(ch["date"], format="%Y-%m-%d", errors="coerce")
            bad_date += int(ch["date"].isna().sum())
            keep = ch["date"] <= cutoff
            dropped += int((ch["date"] > cutoff).sum())
            parts.append(ch[keep])
        df = pd.concat(parts, ignore_index=True)
        df = df.dropna(subset=["date"]).sort_values(["ticker", "date"], kind="stable").reset_index(drop=True)
        self.df = df
        self.n_dropped_sealed, self.n_bad_date = dropped, bad_date
        self.t, self.names = pd.factorize(df["ticker"], sort=True)
        self.names = np.asarray(self.names, dtype=object)
        self.cal = np.sort(df["date"].unique())
        self.ci = np.searchsorted(self.cal, df["date"].values)
        t = self.t
        self.starts = np.flatnonzero(np.r_[True, t[1:] != t[:-1]])
        self.ends = np.r_[self.starts[1:], len(df)]
        self.same_prev = np.r_[False, t[1:] == t[:-1]]                 # row j has a predecessor in the same symbol
        df["dv"] = df["close"] * df["volume"]
        self.first = df["date"].values[self.starts]
        self.last = df["date"].values[self.ends - 1]
        self.nbars = self.ends - self.starts
        say(f"[{label}] {path}: {len(df):,} rows kept <= {cutoff.date()}; {dropped:,} later rows dropped at read (sealed, never examined); "
            f"{bad_date:,} unparsable dates; {len(self.names):,} symbols; {len(self.cal):,} sessions {pd.Timestamp(self.cal[0]).date()}..{pd.Timestamp(self.cal[-1]).date()}")

    def window_stats(self, lo, hi):
        """Per symbol over [lo, hi]: bars, median close, median dollar volume, sum dollar volume. Index = ticker."""
        d = self.df
        w = d[(d["date"] >= lo) & (d["date"] <= hi)]
        g = w.groupby("ticker", sort=False)
        return pd.DataFrame({"nbars": g.size(), "med_px": g["close"].median(), "med_dv": g["dv"].median(), "sum_dv": g["dv"].sum()})


def load_types(sic=None, small_pulls=None):
    """{ticker: security type} from cb702_sic.psv (ticker|date|http|sic|desc|type) and/or small_pulls.psv ('sectype|ticker|type|mic' lines)."""
    ty = {}
    if sic:
        t = pd.read_csv(sic, sep="|", header=None, usecols=[0, 5], names=["t", "type"], keep_default_na=False)
        ty.update({a: b for a, b in zip(t["t"], t["type"]) if b})
    if small_pulls:
        for ln in open(small_pulls):
            f = ln.rstrip("\n").split("|")
            if f[0] == "sectype" and len(f) >= 3 and f[2]:
                ty[f[1]] = f[2]
    return ty


def derivative_set(names, types=None):
    """Symbols that are not common equity: warrants / units / rights (suffix + the parent symbol exists), preferred ('p' in the symbol, '.', '-'),
    exchange test symbols, plus anything the `types` map labels other than CS / ADRC.  Heuristic for symbols with no type; ETFs outside the map
    cannot be told apart offline."""
    s, out = set(names), set()
    for t in names:
        if any(ch in t for ch in ".-/= ") or re.search(r"[a-z]", t) or TEST_SYMBOL.match(t):
            out.add(t); continue
        for suf in ("WS", "WT", "RT", "W", "U", "R"):
            if len(t) > len(suf) + 1 and t.endswith(suf) and t[:-len(suf)] in s:
                out.add(t); break
    if types:
        out |= {t for t in names if types.get(t, "CS") not in ("CS", "ADRC")}
    return out


# ───────────────────────── single-export checks ─────────────────────────
def check_integrity(ex):
    d, L = ex.df, ex.label
    say(f"\n== INTEGRITY [{L}] ==")
    dup = d.duplicated(["ticker", "date"], keep=False)
    bad_ohlc = (d["high"] < d["low"] - 1e-9) | (d["close"] > d["high"] * (1 + 1e-6)) | (d["close"] < d["low"] * (1 - 1e-6)) | \
               (d["open"] > d["high"] * (1 + 1e-6)) | (d["open"] < d["low"] * (1 - 1e-6))
    nonpos = (d[["open", "high", "low", "close"]] <= 0).any(axis=1)
    nan = d[["open", "high", "low", "close", "volume"]].isna().any(axis=1)
    wk = d["date"].dt.dayofweek >= 5
    for name, m in (("duplicate (ticker,date) keys", dup), ("high<low or open/close outside [low,high]", bad_ohlc), ("non-positive price", nonpos),
                    ("NaN in OHLCV", nan), ("weekend bars", wk)):
        say(f"  {name}: {int(m.sum()):,} rows of {len(d):,} on {d.loc[m, 'ticker'].nunique():,} symbols")
        for tk, g in d[m].groupby("ticker"):
            flag("integrity:" + name.split(" ")[0], L, tk, g["date"].min(), g["date"].max(), len(g), "", name)
    # business days that no symbol printed (holidays are expected; anything else is a hole in the whole export)
    allbd = pd.bdate_range(pd.Timestamp(ex.cal[0]), pd.Timestamp(ex.cal[-1]))
    miss = allbd.difference(pd.DatetimeIndex(ex.cal))
    say(f"  business days with no bar from any symbol: {len(miss)} (US holidays expected, ~9-10 a year): " + ", ".join(x.strftime("%Y-%m-%d") for x in miss[:60]) + (" ..." if len(miss) > 60 else ""))
    for x in miss:
        flag("integrity:no_session", L, "*ALL*", x, x, 0, "", "business day with no bars from any symbol (holiday or hole)")


def check_coverage(ex, liq_dv, liq_px, out, types=None):
    d, L = ex.df, ex.label
    say(f"\n== COVERAGE [{L}] ==")
    d = d.assign(y=d["date"].dt.year, liq=((d["dv"] >= liq_dv) & (d["close"] >= liq_px)))
    per_day = d.groupby("date").agg(n=("ticker", "size"), nliq=("liq", "sum"))
    per_day["y"] = per_day.index.year
    rows = []
    for y, g in per_day.groupby("y"):
        yy = d[d["y"] == y]
        rows.append((L, y, g.shape[0], yy["ticker"].nunique(), int(g.n.median()), int(g.n.min()), int(g.n.max()), int(g.nliq.median()), int(g.nliq.min()), int(g.nliq.max())))
    cov = pd.DataFrame(rows, columns=["label", "year", "sessions", "tickers_ever", "per_day_median", "per_day_min", "per_day_max",
                                      f"liquid_per_day_median(dv>={liq_dv:g},px>={liq_px:g})", "liquid_min", "liquid_max"])
    say(cov.to_string(index=False))
    cov.to_csv(os.path.join(out, f"coverage_by_year_{L}.tsv"), sep="\t", index=False)
    med = per_day["n"].rolling(21, min_periods=10).median().shift(1)
    thin = per_day[(per_day["n"] < 0.6 * med)]
    say(f"  thin sessions (symbols printed < 60% of the prior-21-session median): {len(thin)} of {len(per_day)}: " + ", ".join(f"{i.date()}({int(r.n)}/{int(med[i])})" for i, r in thin.head(12).iterrows()))
    for i, r in thin.iterrows():
        flag("coverage:thin_session", L, "*ALL*", i, i, int(r.n), f"{r.n / med[i]:.2f}", f"{int(r.n)} symbols vs prior-21 median {int(med[i])}")
    # symbols that stop printing before the export ends (the survivorship footprint), by last-bar year; a complete universe shows a roughly flat
    # yearly count of endings, an export built from a current list shows few early ones and many recent ones
    margin = ex.cal[max(0, len(ex.cal) - 1 - 5)]
    lastyr = pd.Series(pd.DatetimeIndex(ex.last).year).value_counts().sort_index()
    died = ex.last < margin
    say("  symbols by LAST-bar year, all symbols (the final year is mostly 'still alive'): " + ", ".join(f"{y}:{n}" for y, n in lastyr.items()))
    deriv = derivative_set(list(ex.names), types)
    dvv, pxx = ex.df["dv"].values, ex.df["close"].values
    rows_ = []
    for k in np.flatnonzero(died):
        s_, e_ = ex.starts[k], ex.ends[k]
        w = slice(max(s_, e_ - 60), e_)
        rows_.append((pd.Timestamp(ex.last[k]).year, ex.names[k] not in deriv, np.median(dvv[w]) >= liq_dv and np.median(pxx[w]) >= liq_px))
    dd = pd.DataFrame(rows_, columns=["year", "non_deriv", "liquid"]).astype({"non_deriv": bool, "liquid": bool})
    t = pd.DataFrame({"ended_all": dd.groupby("year").size(), "ended_non_derivative": dd[dd.non_deriv].groupby("year").size(),
                      "ended_liquid_non_deriv(last60 median dv,px)": dd[dd.non_deriv & dd.liquid].groupby("year").size()}).fillna(0).astype(int)
    say(f"  symbols whose last bar is before {pd.Timestamp(margin).date()} (stopped printing), by year of last bar:\n" + t.to_string())
    t.reset_index().to_csv(os.path.join(out, f"ended_by_year_{L}.tsv"), sep="\t", index=False)


def check_stale(ex):
    d, L = ex.df, ex.label
    say(f"\n== STALE / CARRIED BARS [{L}] ==")
    zero = d["volume"] <= 0
    prevc = d["close"].shift(1).where(ex.same_prev)
    carry = zero & (d["close"] == prevc)
    frozen = ex.same_prev & (d[["open", "high", "low", "close", "volume"]].values == d[["open", "high", "low", "close", "volume"]].shift(1).values).all(axis=1) & ~zero.values
    flat = (d["open"] == d["high"]) & (d["high"] == d["low"]) & (d["low"] == d["close"]) & ~zero
    say(f"  zero-volume rows: {int(zero.sum()):,} of {len(d):,} ({100 * zero.mean():.3f}%) on {d.loc[zero, 'ticker'].nunique():,} symbols")
    say(f"  carried closes (volume 0 and close == previous close): {int(carry.sum()):,} rows on {d.loc[carry, 'ticker'].nunique():,} symbols")
    say(f"  frozen copies (OHLCV identical to the previous bar, volume > 0): {int(frozen.sum()):,} rows on {d.loc[frozen, 'ticker'].nunique():,} symbols")
    say(f"  flat bars (O=H=L=C, volume > 0): {int(flat.sum()):,} rows on {d.loc[flat, 'ticker'].nunique():,} symbols")
    # longest carried run per symbol, and runs that touch the symbol's last bar (a delisted name printing its last close forever)
    cv = carry.values
    run = np.zeros(len(d), dtype=np.int32)
    for j in np.flatnonzero(cv):
        run[j] = (run[j - 1] if (j > 0 and ex.same_prev[j]) else 0) + 1
    rr = pd.Series(run).groupby(ex.t).max()
    tail = pd.Series(run[ex.ends - 1], index=range(len(ex.names)))
    long_ = rr[rr >= 3]
    say(f"  symbols with a carried run >= 3 sessions: {len(long_):,}; longest run {int(rr.max())}; symbols whose LAST bar is a carried bar: {int((tail > 0).sum()):,}")
    for k, v in long_.items():
        flag("stale:carried_run", L, ex.names[k], ex.first[k], ex.last[k], int(v), int(v), "longest run of volume-0 bars repeating the previous close")
    for name, m in (("stale:frozen_copy", frozen), ("stale:flat_bar", flat)):
        g = d[m].groupby("ticker").agg(n=("date", "size"), first=("date", "min"), last=("date", "max"))
        for tk, r in g[g.n >= 3].iterrows():
            flag(name, L, tk, r["first"], r["last"], int(r.n), int(r.n), "rows")
    by_year = d[zero].groupby(d["date"].dt.year).size()
    say("  zero-volume rows by year: " + (", ".join(f"{y}:{n}" for y, n in by_year.items()) or "none"))


NONEQ_NAME = re.compile(r"\b(ETF|ETN|ETP|Exchange[- ]Traded|ProShares|iShares|SPDR|Direxion|VelocityShares|Fund|Index|Ultra|Bull|Bear|Leveraged|Inverse|"
                        r"2X|3X|Warrants?|Units?|Rights?|Preferred|Depositary Shares|Notes due|Trust Units)\b", re.I)


def check_nonequity(ex, assets, types, liq_dv, liq_px, lo, hi):
    """Items in the universe that are not operating-company stocks (ETFs, leveraged/inverse ETNs, funds, warrants, units, rights, preferreds, test symbols)."""
    L = ex.label
    say(f"\n== NON-EQUITY ITEMS IN THE UNIVERSE [{L}] (window {pd.Timestamp(lo).date()}..{pd.Timestamp(hi).date()}) ==")
    st = ex.window_stats(lo, hi)
    liq = st[(st.nbars >= 60) & (st.med_dv >= liq_dv) & (st.med_px >= liq_px)]
    deriv = derivative_set(list(ex.names), types)
    byname = set()
    if assets:
        ast = pd.read_csv(assets, sep="\t", on_bad_lines="skip", quoting=3, keep_default_na=False).drop_duplicates("symbol")
        byname = set(ast.loc[ast["name"].map(lambda n: bool(NONEQ_NAME.search(str(n)))), "symbol"])
    both = deriv | byname
    if types:
        known = liq.index.isin(list(types))
        tcount = pd.Series([types.get(t, "UNKNOWN") for t in liq.index]).value_counts()
        say(f"  security type known for {int(known.sum()):,} of {len(liq):,} liquid symbols ({100 * known.mean():.1f}%); by type: " + ", ".join(f"{k} {v}" for k, v in tcount.items())
            + "  <- a symbol with NO type is admitted as unknown (every re-fetched delisted name will be one unless its Polygon type is added)")
    say(f"  liquid symbols in window: {len(liq):,}; flagged non-equity by suffix/parent/test-symbol/security-type map: {int(liq.index.isin(list(deriv)).sum()):,}; by --assets name keywords: "
        f"{int(liq.index.isin(list(byname)).sum()):,}; either: {int(liq.index.isin(list(both)).sum()):,} = {100 * liq.index.isin(list(both)).mean():.1f}% of liquid symbols, "
        f"{100 * liq.sum_dv[liq.index.isin(list(both))].sum() / max(1, liq.sum_dv.sum()):.1f}% of liquid dollar volume (keyword match is a heuristic; 'Fund'/'Index'/'Unit' also hit some operating companies)")
    for t in liq.index[liq.index.isin(list(both))]:
        flag("nonequity:in_universe", L, t, lo, hi, int(liq.at[t, "nbars"]), f"{liq.at[t, 'sum_dv']:.0f}", "suffix/test/type" if t in deriv else "name keyword")
    return both


def check_dups(ex, liq_dv, out, other=None):
    d, L = ex.df, ex.label
    say(f"\n== DUPLICATE COMPANIES [{L}] (byte-identical OHLCV on one date under >= 2 symbols) ==")
    key = ["date", "open", "high", "low", "close", "volume"]
    x = d[d["volume"] > 0]
    m = x.duplicated(key, keep=False)
    z = x[m].copy()
    if z.empty:
        say("  none"); return
    z["rep"] = z.groupby(key)["ticker"].transform("min")
    z["grp"] = z.groupby(key)["ticker"].transform("size")
    sec = z[z["ticker"] != z["rep"]]
    pairs = sec.groupby(["rep", "ticker"]).agg(n_days=("date", "size"), first=("date", "min"), last=("date", "max"), med_dv=("dv", "median")).reset_index()
    pairs["label"] = L
    if other is not None:                       # which symbol of the pair is the point-in-time one? the one the other export prints in the same dates
        ob = other.df.groupby("ticker").size()
        pairs["other_bars_rep"] = pairs["rep"].map(ob).fillna(0).astype(int)
        pairs["other_bars_dup"] = pairs["ticker"].map(ob).fillna(0).astype(int)
        pairs["other_has_more_bars"] = np.where(pairs["other_bars_dup"] > pairs["other_bars_rep"], pairs["ticker"], pairs["rep"])
    pairs.sort_values("n_days", ascending=False).to_csv(os.path.join(out, f"dup_pairs_{L}.tsv"), sep="\t", index=False)
    pers = pairs[pairs.n_days >= 20]
    nper = d["date"].nunique()
    perday = sec.groupby("date").size()
    liqdup = sec[sec["dv"] >= liq_dv]
    say(f"  duplicate ticker-days: {len(sec):,} second copies in {len(z):,} identical rows ({len(pairs):,} pairs); persistent pairs (>= 20 shared days): {len(pers):,}")
    say(f"  second copies per session: median {int(perday.median())}, max {int(perday.max())} over {len(perday):,} sessions with any; liquid second copies (dv>={liq_dv:g}): {len(liqdup):,} ticker-days = "
        f"{100 * len(liqdup) / max(1, int((d['dv'] >= liq_dv).sum())):.2f}% of all liquid ticker-days")
    say("  largest pairs: " + "; ".join(f"{r.rep}={r.ticker} {r.n_days}d" for r in pers.sort_values('n_days', ascending=False).head(10).itertuples()))
    say(f"  triples+ (a third symbol on the same bar): {int((z['grp'] >= 3).sum()):,} rows")
    for r in pers.itertuples():
        flag("dups:company_two_symbols", L, f"{r.rep}={r.ticker}", r.first, r.last, int(r.n_days), f"{r.med_dv:.0f}", "byte-identical OHLCV on the shared days")


def load_guard(path):
    g = pd.read_csv(path, sep="\t", keep_default_na=False)
    brk = {}
    for s, b in zip(g["symbol"], g["breaks"]):
        if b:
            brk[s] = [tuple(x.split(":")) for x in b.split(";")]
    return brk


def check_breaks(ex, guard, splits, rawclose, liq_dv):
    d, L = ex.df, ex.label
    say(f"\n== IDENTITY BREAKS [{L}] ==")
    c, v, dv, ci, sp = d["close"].values, d["volume"].values, d["dv"].values, ex.ci, ex.same_prev
    gap = np.where(sp, ci - np.r_[0, ci[:-1]] - 1, 0)
    ret = np.where(sp, c / np.r_[np.nan, c[:-1]] - 1.0, np.nan)
    fac_change = np.zeros(len(d), bool)
    if rawclose is not None:                                         # a raw/adjusted factor change on the same day = a corporate action the adjusted series did not absorb
        rc = pd.read_csv(rawclose, header=None, names=["ticker", "date", "raw"], parse_dates=["date"])
        mm = d[["ticker", "date"]].merge(rc, on=["ticker", "date"], how="left")["raw"].values
        f = mm / c
        fac_change = sp & (np.abs(f / np.r_[np.nan, f[:-1]] - 1) > 0.01)
    splitdays = set()
    if splits is not None:
        sdf = pd.read_csv(splits, sep="|", header=None, names=["t", "d", "to", "frm"], parse_dates=["d"])
        splitdays = set(zip(sdf["t"], sdf["d"]))
    holes = np.flatnonzero(gap > HOLE_MAX)
    shorts = np.flatnonzero((gap >= SHORT_HOLE) & (gap <= HOLE_MAX))
    big = np.flatnonzero(np.abs(np.nan_to_num(ret)) > JUMP_MAX)
    jumps, vol_ev = [], 0
    for j in big:
        s = ex.starts[ex.t[j]]
        pv = v[max(s, j - 20):j]
        ev = len(pv) >= 5 and v[j] >= VOL_EVENT_X * pv.mean()
        sd = (d["ticker"].values[j], d["date"].values[j]) in splitdays or fac_change[j]
        vol_ev += ev
        if (not ev) or sd:
            jumps.append((j, "split/spin" if sd else "no_volume_event"))
    say(f"  holes > {HOLE_MAX} sessions: {len(holes):,} on {len(set(ex.t[holes])):,} symbols | holes {SHORT_HOLE}..{HOLE_MAX}: {len(shorts):,} on {len(set(ex.t[shorts])):,} symbols")
    say(f"  >70% one-session moves: {len(big):,} on {len(set(ex.t[big])):,} symbols; with a volume event (kept as a genuine shock): {int(vol_ev):,}; "
        f"flagged jump (no volume event, or a split/spin on the day): {len(jumps):,} on {len(set(ex.t[[j for j, _ in jumps]])) if jumps else 0:,} symbols")
    # short holes: only a break if the price level AND the dollar-volume regime changed across it
    nshort_lvl = 0
    for j in shorts:
        s, e = ex.starts[ex.t[j]], ex.ends[ex.t[j]]
        b4, af = slice(max(s, j - 10), j), slice(j, min(e, j + 10))
        pr = np.median(c[af]) / np.median(c[b4])
        dr = (np.median(dv[af]) + 1) / (np.median(dv[b4]) + 1)
        if (pr >= 2 or pr <= 0.5) and (dr >= 10 or dr <= 0.1):
            nshort_lvl += 1
            flag("breaks:short_hole_level_shift", L, d["ticker"].values[j], d["date"].values[j], d["date"].values[j], int(gap[j]), f"px x{pr:.2f} dv x{dr:.2f}",
                 "hole of 10..30 sessions with a price-level and dollar-volume regime change (invisible to the >30-session guard)")
    say(f"  short holes with a price x2 / x0.5 AND dollar-volume x10 / x0.1 regime change: {nshort_lvl:,}")
    mine = {}
    for j in holes:
        mine.setdefault(d["ticker"].values[j], []).append((str(d["date"].values[j])[:10], "hole"))
        flag("breaks:hole", L, d["ticker"].values[j], d["date"].values[j], d["date"].values[j], int(gap[j]), int(gap[j]), "sessions with no bar inside the symbol's span (first bar after is the break date)")
    for j, why in jumps:
        mine.setdefault(d["ticker"].values[j], []).append((str(d["date"].values[j])[:10], "jump"))
        flag("breaks:jump", L, d["ticker"].values[j], d["date"].values[j], d["date"].values[j], 1, f"{ret[j]:+.2f}", why)
    say(f"  symbols with >= 1 break (hole or jump) by this script: {len(mine):,} of {len(ex.names):,}")
    if guard is not None:
        gs, ms = set(guard), set(mine)
        say(f"  vs --guard: guard flags {len(gs):,} symbols; this script {len(ms):,}; both {len(gs & ms):,}; only guard {len(gs - ms):,}; only this script {len(ms - gs):,}")
        # liquid weight of what only this script finds
        med = ex.window_stats(pd.Timestamp(ex.cal[0]), pd.Timestamp(ex.cal[-1]))["med_dv"]
        only = [s for s in ms - gs if s in med.index]
        say(f"  of the {len(only):,} symbols only this script flags, {int((med.loc[only] >= liq_dv).sum()):,} have a median dollar volume >= {liq_dv:g}")
    return mine


def write_guard(ex, mine, out):
    """A symbol_guard-shaped file (symbol, breaks 'YYYY-MM-DD:kind;...') the runner's --breaks accepts, built from THIS script's break test."""
    p = os.path.join(out, f"symbol_guard_{ex.label}.tsv")
    with open(p, "w") as f:
        f.write("symbol\tbreaks\n")
        for sym in sorted(mine):
            f.write(sym + "\t" + ";".join(f"{d}:{k}" for d, k in sorted(mine[sym])) + "\n")
    say(f"  wrote {p} ({len(mine):,} symbols with a break) - pass to the runner as --breaks for this export")


# ───────────────────────── pair checks ─────────────────────────
def check_overlap(P, Q, liq_dv, liq_px, lo, hi, out, deriv):
    say(f"\n== OVERLAP [{P.label} vs {Q.label}] window {lo.date()}..{hi.date()} ==")
    sp_, sq_ = P.window_stats(lo, hi), Q.window_stats(lo, hi)
    a_only, b_only, both = sp_.index.difference(sq_.index), sq_.index.difference(sp_.index), sp_.index.intersection(sq_.index)
    liq = lambda s: s[(s.nbars >= 60) & (s.med_dv >= liq_dv) & (s.med_px >= liq_px)]
    say(f"  symbols with a bar in the window: {P.label} {len(sp_):,} | {Q.label} {len(sq_):,} | both {len(both):,} | only {P.label} {len(a_only):,} | only {Q.label} {len(b_only):,}")
    for nm, s, other in ((P.label, sp_, sq_), (Q.label, sq_, sp_)):
        only = s.loc[s.index.difference(other.index)]
        lq = liq(s); lo_ = lq.loc[lq.index.difference(other.index)]
        say(f"  only {nm}: {len(only):,} symbols, {100 * only.sum_dv.sum() / s.sum_dv.sum():.2f}% of {nm}'s window dollar volume; liquid (>=60 bars, dv>={liq_dv:g}, px>={liq_px:g}) "
            f"{len(lo_):,} of {len(lq):,} liquid {nm} symbols = {100 * len(lo_) / max(1, len(lq)):.1f}%, {100 * lo_.sum_dv.sum() / max(1, lq.sum_dv.sum()):.1f}% of liquid dollar volume")
    # liquid names per session in each export, by month: the survivorship gap as a coverage ratio
    def liqcount(ex):
        w = ex.df[(ex.df.date >= lo) & (ex.df.date <= hi)]
        w = w[(w.dv >= liq_dv) & (w.close >= liq_px)]
        return w.groupby("date").size()
    cp, cq = liqcount(P), liqcount(Q)
    mt = pd.DataFrame({P.label: cp, Q.label: cq}).dropna()
    mt = mt.groupby(mt.index.to_period("M")).median().round(0).astype(int)
    mt["ratio"] = (mt[P.label] / mt[Q.label]).round(3)
    say(f"  liquid names per session (median by month; dv>={liq_dv:g}, px>={liq_px:g}; includes ETFs/warrants in both):\n" + mt.to_string())
    pd.DataFrame(mt).reset_index().to_csv(os.path.join(out, "liquid_per_session_by_month.tsv"), sep="\t", index=False)
    # rename-aware: an "only" symbol whose open+close match a symbol on the other side on >= 50% of its days is the same company under another name
    pw, qw = P.df[(P.df.date >= lo) & (P.df.date <= hi)], Q.df[(Q.df.date >= lo) & (Q.df.date <= hi)]
    rp, _ = rename_match(pw, qw, set(a_only))          # P-only symbol -> Q symbol carrying the same bars
    rq, _ = rename_match(qw, pw, set(b_only))          # Q-only symbol -> P symbol
    for nm, s, ren, other in ((P.label, sp_, rp, Q.label), (Q.label, sq_, rq, P.label)):
        lq = liq(s)
        lq = lq[lq.index.isin(a_only if nm == P.label else b_only)]
        true_only = lq[~lq.index.isin(list(ren))]
        say(f"  RENAME-AWARE: of {nm}'s {len(lq):,} liquid only-{nm} symbols, {len(lq) - len(true_only):,} are the same bars under another symbol in {other}; "
            f"{len(true_only):,} are genuinely absent from {other} ({100 * true_only.sum_dv.sum() / max(1, liq(s).sum_dv.sum()):.1f}% of {nm}'s liquid window dollar volume)")
        for tk, x in true_only.iterrows():
            flag(f"overlap:only_{nm}", f"{P.label}|{Q.label}", tk, lo, hi, int(x.nbars), f"{x.sum_dv:.0f}", f"genuinely absent from {other}; median dv {x.med_dv:.0f}")
    say(f"  rename pairs found: {len(rp):,} {P.label}-only->{Q.label} symbol, {len(rq):,} {Q.label}-only->{P.label} symbol (e.g. " + "; ".join(f"{k}->{v}" for k, v in list(rq.items())[:8]) + ")")
    return sp_, sq_, pw, qw


def rename_match(small, big, only_syms, min_match=20, frac=0.5):
    """For each symbol in `only_syms` (rows in `small`), find a symbol in `big` printing the same open+close on the same dates."""
    k = ["date", "o2", "c2"]
    s = small[small.ticker.isin(only_syms)].assign(o2=lambda x: x.open.round(2), c2=lambda x: x.close.round(2))[["ticker", *k]]
    b = big.assign(o2=lambda x: x.open.round(2), c2=lambda x: x.close.round(2))[["ticker", *k]]
    j = s.merge(b, on=k, suffixes=("", "_big"))
    j = j[j["ticker"] != j["ticker_big"]]
    cnt = j.groupby(["ticker", "ticker_big"]).size().reset_index(name="n")
    tot = s.groupby("ticker").size()
    cnt["frac"] = cnt.n / cnt.ticker.map(tot)
    best = cnt.sort_values("n", ascending=False).drop_duplicates("ticker")
    best = best[(best.n >= min_match) & (best.frac >= frac)]
    return dict(zip(best.ticker, best.ticker_big)), tot


def check_identity_x(P, Q, pw, qw, guard, out, lo, hi, liq_dv, minep=None, mineq=None):
    say(f"\n== IDENTITY ACROSS EXPORTS [{P.label} vs {Q.label}] same symbol, same dates ==")
    m = pw[["ticker", "date", "close", "volume", "dv"]].merge(qw[["ticker", "date", "close", "volume", "dv"]], on=["ticker", "date"], suffixes=("_p", "_q"))
    m = m[(m.close_p > 0) & (m.close_q > 0)]
    m["lr"] = np.log(m.close_p / m.close_q)
    m = m.sort_values(["ticker", "date"])
    cal = {d: i for i, d in enumerate(np.union1d(P.cal, Q.cal))}
    m["ci"] = m.date.map(cal)
    ok = (m.ticker == m.ticker.shift(1)) & (m.ci - m.ci.shift(1) == 1)
    m["rp"] = np.where(ok, np.log(m.close_p / m.close_p.shift(1)), np.nan)
    m["rq"] = np.where(ok, np.log(m.close_q / m.close_q.shift(1)), np.nan)
    g = m.groupby("ticker")
    r = pd.DataFrame({"n_common": g.size(), "med_ratio": g["lr"].median().apply(np.exp), "sd_logratio": g["lr"].std(), "sum_dv": g["dv_p"].sum()})
    rr = m.dropna(subset=["rp", "rq"])
    cc = rr.groupby("ticker").apply(lambda x: np.corrcoef(x.rp, x.rq)[0, 1] if len(x) >= 15 and x.rp.std() > 0 and x.rq.std() > 0 else np.nan, include_groups=False)
    r["corr"] = cc
    r["n_ret"] = rr.groupby("ticker").size()
    r = r[r.n_common >= 20].copy()
    scale = (r.med_ratio - 1).abs() > 0.02
    cls = np.where(r["corr"].isna(), "undetermined", np.where(r["corr"] < 0.9, "MISMATCH_different_series", np.where(scale | (r.sd_logratio > 0.02), "scale_or_basis_only", "same")))
    r["class"] = cls
    gd = set(guard) if guard else set()
    r["in_guard"] = r.index.isin(gd)
    r.reset_index().to_csv(os.path.join(out, "pair_identity.tsv"), sep="\t", index=False)
    vc = r["class"].value_counts()
    say(f"  common symbols with >= 20 shared days: {len(r):,}; " + "; ".join(f"{k} {v:,}" for k, v in vc.items()))
    tot = r.sum_dv.sum()
    for k in ("MISMATCH_different_series", "scale_or_basis_only", "undetermined"):
        s = r[r["class"] == k]
        say(f"  {k}: {len(s):,} symbols = {100 * s.sum_dv.sum() / tot:.2f}% of shared dollar volume; liquid (shared-day median dv>={liq_dv:g}) {int((s.sum_dv / s.n_common >= liq_dv).sum()):,}")
    mm = r[r["class"] == "MISMATCH_different_series"].sort_values("sum_dv", ascending=False)
    say("  largest mismatches by dollar volume: " + "; ".join(f"{i}(corr {x['corr']:.2f}, ratio {x.med_ratio:.3g})" for i, x in mm.head(12).iterrows()))
    # WHICH side is the odd one? a break (hole > 30 / unexplained jump) in a side's own series is evidence that side changed hands
    minep, mineq = minep or {}, mineq or {}
    mm = mm.assign(break_in_P=mm.index.isin(list(minep)), break_in_Q=mm.index.isin(list(mineq)))
    mm["side"] = np.where(mm.break_in_P & mm.break_in_Q, "break_in_both", np.where(mm.break_in_P, f"break_in_{P.label}", np.where(mm.break_in_Q, f"break_in_{Q.label}", "no_break_visible_either_side")))
    if len(mm):
        sd = mm.groupby("side").agg(n=("n_common", "size"), liquid=("sum_dv", lambda x: int(((x / mm.loc[x.index, "n_common"]) >= liq_dv).sum())))
        say(f"  side of the mismatch (a break in that side's own series): " + "; ".join(f"{k}: {r.n} ({r.liquid} liquid)" for k, r in sd.iterrows()))
        hid = mm[~mm.break_in_P]
        say(f"  mismatches with NO break in {P.label}'s own series: {len(hid):,} of {len(mm):,} -> in {P.label} these are a different company under the same symbol that no hole/jump guard can see (it is a symbol-label difference, not a corrupted series)")
        if gd:
            say(f"  GUARD RECALL on this independent sample: the guard flags {int(mm.in_guard.sum()):,} of {len(mm):,} mismatched symbols ({100 * mm.in_guard.mean():.1f}%); "
                f"of the {int(mm.break_in_P.sum()):,} with a break on the {P.label} side, {int((mm.break_in_P & mm.in_guard).sum()):,} flagged")
    elif gd:
        say("  no mismatches")
    for i, x in mm.iterrows():
        flag("identity_x:different_series", f"{P.label}|{Q.label}", i, lo, hi, int(x.n_common), f"corr={x['corr']:.2f};ratio={x.med_ratio:.3g}", f"in_guard={bool(x.in_guard)};side={x.side}")
    for i, x in r[r["class"] == "scale_or_basis_only"].iterrows():
        flag("identity_x:price_basis_diverges", f"{P.label}|{Q.label}", i, lo, hi, int(x.n_common), f"ratio={x.med_ratio:.4g};corr={x['corr']:.2f}", "same series, different adjustment (split / spin-off / special distribution)")
    # volume basis
    vr = (m.volume_p / m.volume_q.replace(0, np.nan)).replace([np.inf, -np.inf], np.nan).dropna()
    say(f"  volume {P.label}/{Q.label} on {len(vr):,} shared ticker-days: median {vr.median():.3f}, p5 {vr.quantile(.05):.3f}, p95 {vr.quantile(.95):.3f}; identical volume on {100 * (m.volume_p == m.volume_q).mean():.1f}% of rows")
    cr = (m.close_p / m.close_q)
    say(f"  close {P.label}/{Q.label}: exactly equal on {100 * (m.close_p == m.close_q).mean():.2f}% of {len(m):,} shared rows; within 0.5% on {100 * ((cr - 1).abs() < .005).mean():.2f}%")
    return r


def check_gone(P, Q, pw, qw, args, deriv_q, out, lo, hi, tail_syms_bad):
    liq_dv, liq_px, cutoff = args.liq_dv, args.liq_px, pd.Timestamp(args.cutoff)
    say(f"\n== KNOWN-GONE LIST [{Q.label} names whose last bar is before the cutoff, liquid in the overlap] vs [{P.label}] ==")
    margin = Q.cal[max(0, len(Q.cal) - 1 - args.gone_margin)]
    sq = Q.window_stats(lo, hi)
    last = pd.Series(Q.last, index=Q.names)
    sq["last"] = last.reindex(sq.index)
    sq["deriv"] = sq.index.isin(deriv_q)
    liq = sq[(sq.nbars >= 60) & (sq.med_dv >= liq_dv) & (sq.med_px >= liq_px)].copy()
    say(f"  {Q.label} liquid in window ({lo.date()}..{hi.date()}; >= 60 bars, median dv >= {liq_dv:g}, median px >= {liq_px:g}): {len(liq):,}; of which warrant/unit/right/preferred/non-CS by heuristic: {int(liq.deriv.sum()):,} (excluded below)")
    liq = liq[~liq.deriv]
    liq["gone"] = liq["last"] < margin
    pset = set(P.names)
    pn = P.window_stats(lo, hi)
    liq["p_bars"] = pn.nbars.reindex(liq.index).fillna(0).astype(int)
    liq["status"] = np.where(liq.p_bars >= 0.5 * liq.nbars, "in_primary", np.where(liq.p_bars > 0, "partial_in_primary", "missing"))
    # rename match for the not-in-primary names
    miss = liq[liq.status != "in_primary"].index
    rm, _ = rename_match(qw, pw, set(miss))
    liq.loc[[s for s in miss if s in rm], "status"] = "renamed_in_primary"
    liq["renamed_to"] = pd.Series(rm).reindex(liq.index).fillna("")
    liq["alpaca_status"] = ""
    if args.assets:
        ast = pd.read_csv(args.assets, sep="\t", on_bad_lines="skip", quoting=3, keep_default_na=False).drop_duplicates("symbol").set_index("symbol")
        liq["alpaca_status"] = [ast["status"].get(t, "absent_from_assets_list") for t in liq.index]
    # probable rename INSIDE Q (not a death): a new symbol's first bar within 3 sessions of this one's last, open or close within 6% of its last close, volume within 0.25-4x its last-20 mean
    lastrow = Q.df.iloc[Q.ends - 1].set_index("ticker")
    firstrow = Q.df.iloc[Q.starts].set_index("ticker")
    ciq = pd.Series(Q.ci[Q.starts], index=Q.names)
    cil = pd.Series(Q.ci[Q.ends - 1], index=Q.names)
    v20 = {Q.names[k]: Q.df["volume"].values[max(Q.starts[k], Q.ends[k] - 20):Q.ends[k]].mean() for k in np.flatnonzero(Q.last < margin)}
    succ = {}
    for t in liq.index[liq.gone]:
        LC, li = lastrow.at[t, "close"], cil[t]
        c = firstrow[(ciq.reindex(firstrow.index) > li) & (ciq.reindex(firstrow.index) <= li + 3) & (firstrow.index != t)]
        c = c[((c.open / LC).between(0.94, 1.06) | (c.close / LC).between(0.94, 1.06)) & (c.volume / max(v20.get(t, 1), 1)).between(0.25, 4)]
        succ[t] = ",".join(c.index[:3])
    liq["probable_rename_to"] = pd.Series(succ).reindex(liq.index).fillna("")
    liq["bucket"] = np.where(~liq.gone, "ALIVE_at_cutoff(control)", np.where(liq["last"] <= hi, "gone_inside_overlap", pd.to_datetime(liq["last"]).dt.year.astype(str).radd("gone_")))
    tab = liq.groupby(["bucket", "status"]).size().unstack(fill_value=0)
    tab["total"] = tab.sum(axis=1)
    miss_cols = [c for c in ("missing", "partial_in_primary") if c in tab]
    tab["share_not_in_primary"] = (tab[miss_cols].sum(axis=1) / tab["total"]).round(3) if miss_cols else 0.0
    say(tab.to_string())
    g, ctl = liq[liq.gone], liq[~liq.gone]
    gr = g[g.probable_rename_to == ""]
    grm = gr[gr.status.isin(["missing", "partial_in_primary"])]
    say(f"  of the {len(g):,} known-gone names, {len(g) - len(gr):,} have a probable successor symbol in {Q.label} (a rename, not a death); "
        f"excluding them: {len(gr):,} deaths, missing/partial in {P.label} {len(grm):,} = {100 * len(grm) / max(1, len(gr)):.1f}%")
    if args.assets:
        say("  Alpaca assets-list status of the known-gone names that are NOT in the primary export: " +
            ", ".join(f"{k} {v}" for k, v in g[g.status.isin(["missing", "partial_in_primary"])].alpaca_status.value_counts().items()) +
            " | of those IN the primary export: " + ", ".join(f"{k} {v}" for k, v in g[g.status == "in_primary"].alpaca_status.value_counts().items()))
    gm, cm = g[g.status.isin(["missing", "partial_in_primary"])], ctl[ctl.status.isin(["missing", "partial_in_primary"])]
    say(f"  KNOWN-GONE liquid names: {len(g):,}; missing or only partly in {P.label}: {len(gm):,} = {100 * len(gm) / max(1, len(g)):.1f}% ; their share of the gone group's window dollar volume: {100 * gm.sum_dv.sum() / max(1, g.sum_dv.sum()):.1f}%")
    say(f"  CONTROL (still alive at the cutoff, liquid in the window): {len(ctl):,}; missing/partial in {P.label}: {len(cm):,} = {100 * len(cm) / max(1, len(ctl)):.1f}%  -> the gap is a LOWER bound on survivorship: the control still contains names that died in 2025-26 (sealed, unobservable here) plus listing/identity noise")
    liq.reset_index().rename(columns={"index": "ticker"}).sort_values(["gone", "sum_dv"], ascending=False).to_csv(os.path.join(out, "gone_list.tsv"), sep="\t", index=False)
    for tk, x in gm.iterrows():
        flag("gone:missing_from_primary", f"{P.label}|{Q.label}", tk, x["last"], x["last"], int(x.nbars), f"{x.sum_dv:.0f}", f"status={x.status};med_dv={x.med_dv:.0f};last_bar={str(x['last'])[:10]}")
    # inactive coverage diagnostic: do names that died INSIDE the primary's own span get carried by it?
    ins = liq[liq.bucket == "gone_inside_overlap"]
    aft = liq[liq.bucket.str.startswith("gone_20") & ~(liq.bucket == "gone_inside_overlap")]
    if len(ins):
        say(f"  gone INSIDE the overlap (primary was still live): {len(ins):,} names, in primary {int((ins.status.isin(['in_primary', 'renamed_in_primary'])).sum()):,} = {100 * ins.status.isin(['in_primary', 'renamed_in_primary']).mean():.1f}% ; "
            f"gone AFTER the primary ended: {len(aft):,}, in primary {100 * aft.status.isin(['in_primary', 'renamed_in_primary']).mean() if len(aft) else float('nan'):.1f}%")
    return liq


def check_impact(P, Q, liq, args, lo, hi, out, mine_q):
    cutoff = pd.Timestamp(args.cutoff)
    say(f"\n== IMPACT [{Q.label} prices; every figure is descriptive, <= cutoff {cutoff.date()}; NOT a tradable return] ==")
    snap = pd.Timestamp(args.snapshot)
    d = Q.df
    snapd = d[(d.date <= snap) & (d.date > snap - pd.Timedelta(days=60))]
    sn = snapd.groupby("ticker").agg(med_dv=("dv", "median"), px=("close", "last"), last_seen=("date", "max"), nb=("date", "size"))
    sn = sn[(sn.nb >= 20) & (sn.med_dv >= args.liq_dv) & (sn.px >= args.liq_px) & (sn.last_seen >= snap - pd.Timedelta(days=5))]
    lastclose = d.groupby("ticker").agg(lc=("close", "last"), ld=("date", "max"))
    sn = sn.join(lastclose)
    sn = sn[~sn.index.isin(liq.index[liq.deriv]) if "deriv" in liq else sn.index.notna()]
    st = liq["status"].reindex(sn.index)
    sn["tot_ret"] = sn.lc / sn.px - 1
    sn["gone"] = sn.ld < Q.cal[max(0, len(Q.cal) - 1 - args.gone_margin)]
    sn["covered"] = st.fillna("not_liquid_in_window").isin(["in_primary", "renamed_in_primary"])
    sn = sn[sn.index.isin(liq.index)]                       # same population as the gone list (liquid in the window, non-derivative)
    say(f"  snapshot {snap.date()}: {len(sn):,} liquid names; end = last bar <= cutoff")
    rows = []
    for nm, s in (("covered by primary", sn[sn.covered]), ("NOT covered by primary", sn[~sn.covered]), ("  of which gone before cutoff", sn[(~sn.covered) & sn.gone]),
                  ("gone & covered", sn[sn.covered & sn.gone])):
        if len(s) == 0:
            continue
        rows.append((nm, len(s), s.tot_ret.median(), s.tot_ret.mean(), (s.tot_ret <= -0.8).mean(), (s.tot_ret <= -0.5).mean(), (s.tot_ret >= 1).mean(), (s.tot_ret >= 3).mean()))
    t = pd.DataFrame(rows, columns=["group", "n", "median_ret", "mean_ret", "share<=-80%", "share<=-50%", "share>=+100%", "share>=+300%"]).round(3)
    say(t.to_string(index=False))
    # tail: +100% close-to-close run within 60 sessions starting in the window, liquid on the start day
    cal = np.sort(Q.cal)
    lo_i, hi_i = np.searchsorted(cal, lo.to_datetime64()), np.searchsorted(cal, hi.to_datetime64(), side="right") - 1
    H = args.horizon
    dd = d[(d.date >= cal[lo_i]) & (d.date <= cal[min(len(cal) - 1, hi_i + H)])]
    pc = dd.pivot(index="date", columns="ticker", values="close")
    pdv = dd.pivot(index="date", columns="ticker", values="dv")
    P_, V_ = pc.values, pdv.values
    start_ok = pc.index >= cal[lo_i]
    runners = {}
    for i in np.flatnonzero(start_ok & (pc.index <= cal[hi_i])):
        if i + 1 >= len(P_):
            break
        fut = np.nanmax(np.where(np.isfinite(P_[i + 1:i + 1 + H]), P_[i + 1:i + 1 + H], -np.inf), axis=0)
        mult = fut / P_[i]
        hit = np.isfinite(mult) & (mult >= args.run_mult) & (V_[i] >= args.liq_dv) & (P_[i] >= args.liq_px)
        for k in np.flatnonzero(hit):
            tk = pc.columns[k]
            if tk not in runners or mult[k] > runners[tk][0]:
                runners[tk] = (float(mult[k]), pc.index[i])
    bad = set(mine_q) if mine_q else set()
    clean = {k: v for k, v in runners.items() if k not in bad}
    # coverage of a runner = does the primary carry its bars (>= 50% of the days) or the same bars under another symbol - NOT membership in the liquid list
    pwin, qwin = P.window_stats(lo, hi), Q.window_stats(lo, hi)
    cl = list(clean)
    pb = pwin.nbars.reindex(cl).fillna(0)
    qb = qwin.nbars.reindex(cl).fillna(0)
    stat = pd.Series(np.where(pb >= 0.5 * qb, "in_primary", np.where(pb > 0, "partial_in_primary", "missing")), index=cl)
    nm = [t for t in cl if stat[t] != "in_primary"]
    rm_, _ = rename_match(Q.df[(Q.df.date >= lo) & (Q.df.date <= hi)], P.df[(P.df.date >= lo) & (P.df.date <= hi)], set(nm))
    for t in nm:
        if t in rm_:
            stat[t] = "renamed_in_primary"
    cov = stat.isin(["in_primary", "renamed_in_primary"])
    say(f"  RUNNERS: names in {Q.label} that closed >= x{args.run_mult:g} of a liquid start-day close within {H} sessions, start in window: {len(runners):,} "
        f"({len(runners) - len(clean):,} dropped for an identity break in {Q.label} itself); remaining {len(clean):,}; covered by {P.label}: {int(cov.sum()):,}; "
        f"NOT covered: {int((~cov).sum()):,} = {100 * (~cov).mean() if len(cov) else 0:.1f}%  (a runner the primary export never saw cannot be recalled by anything built on it)")
    nc = [k for k in clean if not cov.get(k, False)]
    for thr in (3.0, 4.0):
        big_ = [k for k in clean if clean[k][0] >= thr]
        if big_:
            say(f"  of the {len(big_):,} runners reaching x{thr:g}+: covered {sum(bool(cov.get(k, False)) for k in big_):,}, NOT covered {sum(not cov.get(k, False) for k in big_):,} = {100 * sum(not cov.get(k, False) for k in big_) / len(big_):.1f}%")
    say("  uncovered runners (best multiple, start): " + "; ".join(f"{k} x{clean[k][0]:.1f} {clean[k][1].date()}" for k in sorted(nc, key=lambda z: -clean[z][0])[:15]))
    for k in nc:
        flag("impact:uncovered_runner", f"{P.label}|{Q.label}", k, clean[k][1], clean[k][1], H, f"x{clean[k][0]:.2f}", "runner present in the richer export, absent from the primary")
    # attrition rate by year -> extrapolation caveat
    ann = []
    for y in range(snap.year + 1, cutoff.year + 1):
        cut = min(pd.Timestamp(f"{y}-12-31"), pd.Timestamp(Q.cal[max(0, len(Q.cal) - 1 - args.gone_margin)]))
        if pd.Timestamp(f"{y}-12-31") > pd.Timestamp(Q.cal[-1]) + pd.Timedelta(days=7):
            break
        ann.append((y, int((sn.ld < cut).sum())))
    if len(sn):
        say(f"  cumulative death rate of the {len(sn):,} snapshot-liquid names (last bar before year end): " + ", ".join(f"by {y}: {n} ({100 * n / len(sn):.1f}%)" for y, n in ann))


# ───────────────────────── self-test ─────────────────────────
def selftest():
    """Two synthetic exports with one planted defect each; every check must find its own and must not flag the clean symbols."""
    import tempfile
    rng = np.random.default_rng(7)
    dates = pd.bdate_range("2020-01-02", periods=400)
    def walk(n, p0=50.0):
        return p0 * np.exp(np.cumsum(rng.normal(0, 0.01, n)))
    def bars(sym, px, vol=None, idx=None):
        n = len(px); vol = np.full(n, 100_000.0) * rng.uniform(0.8, 1.2, n) if vol is None else vol
        d = dates[:n] if idx is None else dates[idx]
        return pd.DataFrame({"ticker": sym, "date": d.strftime("%Y-%m-%d"), "open": px * 0.998, "high": px * 1.01, "low": px * 0.99, "close": px, "volume": vol.round()})
    P, Q = [], []
    for i in range(30):                                                    # 30 clean symbols present in both exports, identical bars
        b = bars(f"CLN{i}", walk(400)); P.append(b); Q.append(b)
    d1 = bars("DUP1", walk(400)); P += [d1, d1.assign(ticker="DUP2")]; Q += [d1]            # one company under two symbols in P only
    r = walk(400)
    reuse = bars("REUSE", np.r_[r[:150], r[150:] * 0.1]); reuse = reuse.drop(index=range(150, 190)); P.append(reuse); Q.append(reuse)   # 40-session hole + price level change
    j = walk(400); j[200:] *= 3.0; P.append(bars("JUMPY", j)); Q.append(bars("JUMPY", j))                                              # x3 in one session, no volume event
    c = walk(400); c[300:] = c[299]; v = np.full(400, 100_000.0); v[300:] = 0; P.append(bars("CARRY", c, v)); Q.append(bars("CARRY", c, v))  # 100 carried zero-volume bars
    g = bars("GONE", walk(250)); Q.append(g)                                                   # delisted in Q at session 250, never in P
    ren = bars("OLDNM", walk(400)); Q.append(ren); P.append(ren.assign(ticker="NEWNM"))        # same bars under two names -> not 'missing'
    P.append(bars("MISM", walk(400))); Q.append(bars("MISM", walk(400)))                       # same symbol, independent series -> a different company
    out = tempfile.mkdtemp(prefix="uc_selftest_")
    pp, qq = os.path.join(out, "P.csv"), os.path.join(out, "Q.csv")
    pd.concat(P).to_csv(pp, header=False, index=False); pd.concat(Q).to_csv(qq, header=False, index=False)
    FLAGS.clear()
    main(["--export", pp, "--label", "P", "--other", qq, "--other-label", "Q", "--snapshot", "2020-12-01", "--out-dir", out, "--gone-margin", "5"])
    fr = pd.DataFrame(FLAGS, columns=["check", "label", "ticker", "first", "last", "n", "value", "detail"])
    have = lambda chk, tk, lab=None: bool(((fr.check == chk) & fr.ticker.str.contains(tk, regex=False) & ((fr.label == lab) if lab else True)).any())
    tests = [
        ("duplicate company found", have("dups:company_two_symbols", "DUP1=DUP2", "P")),
        ("clean symbols not flagged as duplicates", not fr[(fr.check == "dups:company_two_symbols")].ticker.str.contains("CLN").any()),
        ("40-session hole found", have("breaks:hole", "REUSE", "P")),
        ("unexplained x3 jump found", have("breaks:jump", "JUMPY", "P")),
        ("carried zero-volume run found", have("stale:carried_run", "CARRY", "P")),
        ("gone name missing from primary", have("gone:missing_from_primary", "GONE")),
        ("renamed name NOT called missing", not have("gone:missing_from_primary", "OLDNM") and not have("gone:missing_from_primary", "NEWNM")),
        ("clean symbols NOT called missing", not fr[(fr.check == "gone:missing_from_primary")].ticker.str.contains("CLN").any()),
        ("different company on one symbol found", have("identity_x:different_series", "MISM")),
        ("clean symbols not a cross-export mismatch", not fr[(fr.check == "identity_x:different_series")].ticker.str.contains("CLN").any()),
    ]
    bad = [n for n, ok in tests if not ok]
    for n, ok in tests:
        say(f"  selftest {'ok  ' if ok else 'FAIL'} {n}")
    if bad:
        raise SystemExit(f"SELFTEST FAIL: {bad}")
    say("SELFTEST PASS")


# ───────────────────────── main ─────────────────────────
def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--export")
    ap.add_argument("--selftest", action="store_true", help="plant known defects in two synthetic exports and assert each check finds them")
    ap.add_argument("--label", default="P")
    ap.add_argument("--other", help="the richer export (carries delisted names)")
    ap.add_argument("--other-label", default="Q")
    ap.add_argument("--cutoff", default="2024-12-31")
    ap.add_argument("--guard"); ap.add_argument("--splits"); ap.add_argument("--sic"); ap.add_argument("--small-pulls", help="small_pulls.psv: 'sectype|TICKER|TYPE|mic' lines (the security-type table the runner uses)"); ap.add_argument("--raw-close"); ap.add_argument("--assets", help="Alpaca assets.tsv (symbol,name,status,exchange,tradable) to say WHY a gone name is absent")
    ap.add_argument("--liq-dv", type=float, default=2_000_000); ap.add_argument("--liq-px", type=float, default=2.0)
    ap.add_argument("--gone-margin", type=int, default=5, help="sessions before the other export's last session that still count as alive")
    ap.add_argument("--snapshot", default="2021-12-31"); ap.add_argument("--horizon", type=int, default=60); ap.add_argument("--run-mult", type=float, default=2.0)
    ap.add_argument("--out-dir", default="universe_audit_out")
    a = ap.parse_args(argv)
    if a.selftest:
        return selftest()
    if not a.export:
        ap.error("--export is required (or --selftest)")
    cutoff = pd.Timestamp(a.cutoff)
    if cutoff >= SEALED_FROM:
        sys.exit(f"refusing --cutoff {a.cutoff}: bars from {SEALED_FROM.date()} on are sealed")
    os.makedirs(a.out_dir, exist_ok=True)
    t0 = time.time()
    P = Ex(a.export, a.label, cutoff)
    guard = load_guard(a.guard) if a.guard else None
    Q = Ex(a.other, a.other_label, cutoff) if a.other else None
    types = load_types(a.sic, a.small_pulls)
    mine = {}
    for ex in [P] + ([Q] if Q else []):
        check_integrity(ex); check_coverage(ex, a.liq_dv, a.liq_px, a.out_dir, types); check_stale(ex); check_dups(ex, a.liq_dv, a.out_dir, (Q if ex is P else P) if Q else None)
        check_nonequity(ex, a.assets, types, a.liq_dv, a.liq_px, pd.Timestamp(max(ex.cal[0], np.datetime64("2021-09-27"))) if ex.cal[-1] >= np.datetime64("2021-09-27") else pd.Timestamp(ex.cal[0]), pd.Timestamp(min(ex.cal[-1], np.datetime64("2022-06-30"))) if ex.cal[-1] >= np.datetime64("2021-09-27") else pd.Timestamp(ex.cal[-1]))
        mine[ex.label] = check_breaks(ex, guard if ex is P else None, a.splits if ex is Q else None, a.raw_close if ex is P else None, a.liq_dv)
        write_guard(ex, mine[ex.label], a.out_dir)
    if Q:
        lo = max(pd.Timestamp(P.cal[0]), pd.Timestamp(Q.cal[0])); hi = min(pd.Timestamp(P.cal[-1]), pd.Timestamp(Q.cal[-1]))
        deriv_q = derivative_set(list(Q.names), types)
        sp_, sq_, pw, qw = check_overlap(P, Q, a.liq_dv, a.liq_px, lo, hi, a.out_dir, deriv_q)
        check_identity_x(P, Q, pw, qw, guard, a.out_dir, lo, hi, a.liq_dv, mine.get(P.label), mine.get(Q.label))
        liq = check_gone(P, Q, pw, qw, a, deriv_q, a.out_dir, lo, hi, mine.get(Q.label))
        liq["deriv"] = False
        check_impact(P, Q, liq, a, lo, hi, a.out_dir, mine.get(Q.label))
    fr = pd.DataFrame(FLAGS, columns=["check", "label", "ticker", "first", "last", "n", "value", "detail"])
    fr.to_csv(os.path.join(a.out_dir, "flagged_rows.tsv"), sep="\t", index=False)
    say(f"\nflagged rows: {len(fr):,} -> {os.path.join(a.out_dir, 'flagged_rows.tsv')}  (by check: " + ", ".join(f"{k} {v:,}" for k, v in fr.check.value_counts().items()) + f")  [{time.time() - t0:.0f}s]")


if __name__ == "__main__":
    main()
