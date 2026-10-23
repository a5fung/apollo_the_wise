#!/usr/bin/env python3
"""Security-type contamination + filter-unit audit of a daily-bar export used by the #702 consolidation-breakout backtests.

WHAT IT ANSWERS (one run per export; read-only; no network):
  U1  Which tickers pass the setup's UNIVERSE filter (ticker ^[A-Z]{1,5}$, RAW close >= $5, 20-session median close*volume >= $10M,
      130 consecutive sessions, not an exchange test symbol) -- split by the security type the runner would resolve for them
      (mi_security_types, else the SIC pull's `type`, else UNKNOWN = ADMITTED, as prod does).
  U2  Which of those admitted tickers are NOT common stock / ADR by their own asset NAME (ETF, ETN, 3x/inverse fund, closed-end fund,
      SPAC unit/warrant/right, preferred, note) -- i.e. type-resolution failures. Includes the UNKNOWN-type leak and the
      "typed CS but named like a fund" mismatch (DWT).
  U3  Point-in-time exposure: which source decided the type (a snapshot dated 2026-10-16, not the bar's date), mi-vs-SIC disagreement.
  U4  Listing/tradability: member tickers on OTC / `tradable=False` in the Alpaca asset list (the live system cannot trade them).
  U5  SPAC trust-price signature (60-session range <= 5% around $9-11) among member nights typed CS.
  P1  Price-floor units: adjusted-vs-RAW $5 floor flips (nights admitted by one and not the other), and -- for a raw close
      derived from a split list -- agreement with an independent measured raw close on the overlap (`--vs-*`).
  P2  Dollar-volume split invariance: median(close*volume) across each detected split date (is close*volume really split-invariant?).

USAGE
  python3 scripts/backtest_data_audit/security_type_check.py --export /Users/alvinfung/apollo_data/cb702_pre/daily_closes_all.csv.gz \
      --era A --raw-close /Users/alvinfung/apollo_data/cb702_pre/daily_raw_close.csv.gz \
      --small /Users/alvinfung/apollo_data/cb702/small_pulls.psv --sic /Users/alvinfung/apollo_data/cb702/cb702_sic.psv \
      --assets /Users/alvinfung/apollo_data/cb702/qm_streams/alpaca_all_2016_2022/assets.tsv \
      --watch-start 2017-03-01 --watch-end 2021-12-31 --out /tmp/audit_A
  python3 ... --export .../cb702/daily_closes_all.csv.gz --era B --splits .../cb702/cb702_splits.psv --watch-start 2022-03-28 \
      --watch-end 2024-12-31 --cutoff 2024-12-31 --out /tmp/audit_B

Outputs (in --out): `flagged_tickers_<era>.tsv` (one row per admitted ticker with >= 1 flag; every flag reason named),
`type_table_<era>.tsv` (resolved type x admitted/excluded: tickers, member-nights), `member_by_year_<era>.tsv`, `floor_flips_<era>.tsv`.
Exit code 0, or 3 when a gate fails (`--max-unknown-share`, `--max-verified-nights`); the NUMBERS are the product -- read the printed summary. Every count states its n.
`--verified-real` is a HAND list: the name classifier proposes, a person confirms against price level / dates, and the list is passed in.
`--breaks symbol_guard.tsv` adds U8: admitted nights dated BEFORE the ticker's last identity break (the resolved type is TODAY's holder of the symbol).

HARD RULES CARRIED IN CODE: `--cutoff` (default 2024-12-31) drops every bar after it AT LOAD (the 2025-26 table is sealed; only the
export's LAST SESSION date is read from beyond the cutoff, because split dates after it must be dropped from the raw factor).
"""
from __future__ import annotations

import argparse
import re
import sys
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd

# --- the setup's universe constants (mirrors agents/market_intelligence/consolidation_breakout.py; asserted in main() if importable) ---
MIN_PRICE = 5.0
MIN_DOLLAR_VOL = 10_000_000.0
DOLLAR_VOL_WINDOW = 20
MIN_HISTORY = 130
UNIVERSE_TICKER_RE = re.compile(r"[A-Z]{1,5}")
UNIVERSE_SECURITY_TYPES = frozenset({"CS", "ADRC"})
TEST_SYMBOLS = frozenset({"ATEST", "CTEST", "MTEST", "NTEST", "PTEST", "ZTEST", "ZBZX", "ZEXIT", "ZIEXT", "ZXIET"})
TEST_FAMILY = re.compile(r"Z[A-Z]ZZ[TC]")

# --- asset-NAME classifier (Alpaca/Polygon free-text names). Order matters: first match wins. ---------------------------------------
NAME_CLASSES = [
    ("WARRANT", re.compile(r"\bwarrants?\b", re.I)),
    ("RIGHT", re.compile(r"(?<!the )\brights?\b(?! to\b)(?! of)", re.I)),            # "...representing the right to receive" is an ADR, not a right
    ("ADR", re.compile(r"american depositary|\bADRs?\b|\bADS\b", re.I)),
    ("SPAC_UNIT", re.compile(r"\bunits?\b", re.I)),              # refined below: MLP/trust "Common Units" is economically a stock
    ("PREFERRED", re.compile(r"\bpreferred\b|\bpfd\b|\d+(\.\d+)?\s?%\s+(series|cumulative|non-cumulative|fixed|noncumulative)", re.I)),
    ("NOTE_DEBT", re.compile(r"\bnotes?\b (due|\d)|\bsenior notes\b|\bsubordinated\b|\bdebentures?\b|\bbonds?\b due", re.I)),
    ("ETN", re.compile(r"\bETNs?\b|exchange[- ]traded notes?|\biPath\b|\bETRACS\b|\bVelocityShares\b", re.I)),
    ("LEVERAGED_INVERSE", re.compile(r"\b[23]x\b|\bUltra(Pro|Short|Shares)\b|\bUltra (Short|Long)\b|\binverse\b|\bdaily (long|short|bull|bear)\b|\bbull\b.*\b(2x|3x)\b|\bbear\b.*\b(2x|3x)\b", re.I)),
    ("ETF", re.compile(r"\bETFs?\b|exchange[- ]traded fund|\biShares\b|\bSPDR\b|\bProShares\b|\bDirexion\b|\bPowerShares\b|\bProFunds\b|\bXtrackers\b|\bGraniteShares\b|"
                       r"\b(Invesco|WisdomTree|VanEck|First Trust|Global X|Vanguard|Schwab|ARK|Grayscale)\b.*\b(ETF|Fund|Trust|Index|Portfolio)\b|\bIndex Fund\b|\bBitcoin Trust\b", re.I)),
    ("FUND", re.compile(r"\bfund\b|\bclosed[- ]end\b|\bmunicipal (income|bond|opportunit)", re.I)),
    ("SPAC_SHELL", re.compile(r"\bacquisition (corp|co|holdings)\b|\bblank check\b|\bmerger corp\b", re.I)),
]
MLP_UNIT_OK = re.compile(r"\b(common|trust|limited partner|partnership|LP)\b.*\bunits?\b|\bunits? representing\b.*\b(limited|beneficial)\b", re.I)
EXCLUDED_NAME_CLASSES = {"WARRANT", "RIGHT", "SPAC_UNIT", "PREFERRED", "NOTE_DEBT", "ETN", "LEVERAGED_INVERSE", "ETF", "FUND"}


def classify_name(name: str) -> str:
    """Name-based class of an asset. `COMMON?` = nothing suggests a non-common instrument (NOT proof it is one)."""
    if not name:
        return "NO_NAME"
    for cls, rx in NAME_CLASSES:
        if rx.search(name):
            if cls == "SPAC_UNIT" and MLP_UNIT_OK.search(name):
                continue
            if cls == "PREFERRED" and "%" not in name and re.search(r"common (stock|shares)", name, re.I):
                continue                                              # "Preferred Bank Common Stock": a company called Preferred, not a preferred share
            return cls
    return "COMMON?"


# --- loaders ---------------------------------------------------------------------------------------------------------------------------
def load_export(path: Path, cutoff: str):
    """headerless ticker,date,open,high,low,close,volume -> DataFrame(t, d(str), c, v) with d <= cutoff, plus the export's last session
    (read from the whole file; nothing after the cutoff is kept)."""
    parts, last = [], ""
    for ch in pd.read_csv(path, header=None, usecols=[0, 1, 5, 6], names=["t", "d", "c", "v"], dtype={"t": str, "d": str, "c": float, "v": float},
                          keep_default_na=False, chunksize=2_000_000):
        last = max(last, ch["d"].max())
        parts.append(ch[ch["d"] <= cutoff])
    df = pd.concat(parts, ignore_index=True)
    return df, last


def load_small(path: Path) -> dict:
    """small_pulls.psv `sectype|ticker|type|primary_exchange` -> {ticker: (type, mic)}."""
    out = {}
    for ln in Path(path).read_text().splitlines():
        f = ln.split("|")
        if f[0] == "sectype" and len(f) >= 3:
            out[f[1]] = (f[2], f[3] if len(f) > 3 else "")
    return out


def load_sic(path: Path) -> dict:
    """cb702_sic.psv `ticker|asof|http|sic|desc|type` -> {ticker: (sic, desc, type, asof)}."""
    out = {}
    for ln in Path(path).read_text().splitlines():
        f = ln.split("|")
        if len(f) >= 6:
            out[f[0]] = (f[3], f[4], f[5], f[1])
    return out


def load_assets(path: Path) -> dict:
    """alpaca assets.tsv `symbol name status exchange tradable` -> {symbol: (name, status, exchange, tradable)}."""
    out = {}
    for k, ln in enumerate(Path(path).read_text().splitlines()):
        f = ln.split("\t")
        if k == 0 or len(f) < 5:
            continue
        out[f[0]] = (f[1], f[2], f[3], f[4] == "True")
    return out


def load_splits(path: Path, through: str) -> dict:
    """cb702_splits.psv `ticker|exec_date|from|to|...` -> {ticker: [(exec_date, to/from)]}; splits executing AFTER `through` are dropped
    (not in the adjusted series yet), as runner.load_splits does."""
    seen, out = set(), {}
    for ln in Path(path).read_text().splitlines():
        f = ln.split("|")
        if len(f) < 4:
            continue
        key = (f[0], f[1], f[2], f[3])
        if key in seen or f[1] > through:
            continue
        seen.add(key)
        out.setdefault(f[0], []).append((f[1], float(f[3]) / float(f[2])))
    for v in out.values():
        v.sort()
    return out


def load_breaks(path: Path) -> dict:
    """symbol_guard.tsv -> {symbol: [(date, kind), ...]} (columns read by name)."""
    lines = Path(path).read_text().splitlines()
    head = lines[0].split("\t")
    k_sym, k_brk = head.index("symbol"), head.index("breaks")
    out = {}
    for ln in lines[1:]:
        f = ln.split("\t")
        if len(f) > k_brk and f[k_brk]:
            out[f[k_sym]] = sorted((x.split(":")[0], x.split(":")[1] if ":" in x else "") for x in f[k_brk].split(";") if x)
    return out


class Era:
    """Flat, (ticker, date)-sorted arrays of one export plus the per-bar raw/adjusted factor and the admission masks."""

    def __init__(self, df: pd.DataFrame, last_session: str, raw_close: Path | None, splits: Path | None):
        codes, uniq = pd.factorize(df["t"], sort=True)
        days = pd.to_datetime(df["d"], format="%Y-%m-%d").to_numpy().astype("datetime64[D]").astype(np.int64)
        order = np.lexsort((days, codes))
        self.tickers = [str(x) for x in uniq]
        self.tid = {t: k for k, t in enumerate(self.tickers)}
        self.code = codes[order].astype(np.int64)
        self.day = days[order]
        self.c = df["c"].to_numpy(dtype=float)[order]
        self.v = df["v"].to_numpy(dtype=float)[order]
        self.dstr = df["d"].to_numpy()[order]
        self.n = len(self.code)
        b = np.concatenate(([0], np.flatnonzero(np.diff(self.code)) + 1, [self.n]))
        self.start, self.stop = b[:-1], b[1:]
        self.pos = np.arange(self.n) - self.start[self.code]            # index inside the ticker's own bars
        spy = self.tid["SPY"]
        cal = self.day[self.start[spy]:self.stop[spy]]
        self.cal = cal
        ci = np.searchsorted(cal, self.day)
        self.on_cal = (ci < len(cal)) & (cal[np.minimum(ci, len(cal) - 1)] == self.day)
        self.ci = ci
        self.last_session = last_session
        self.raw_source = "NONE (adjusted close used as raw: the $5 floor is in the WRONG units)"
        self.fac = np.ones(self.n)
        if raw_close is not None:
            self._raw_from_file(raw_close, df, order)
        elif splits is not None:
            self._raw_from_splits(splits)

    def _raw_from_file(self, path: Path, df: pd.DataFrame, order: np.ndarray):
        raw = pd.read_csv(path, header=None, names=["t", "d", "r"], dtype={"t": str, "d": str, "r": float}, keep_default_na=False)
        raw = raw[raw["d"] <= self.dstr.max()]
        key = pd.MultiIndex.from_arrays([raw["t"].to_numpy(), raw["d"].to_numpy()])
        mine = pd.MultiIndex.from_arrays([np.array(self.tickers, dtype=object)[self.code], self.dstr])
        ix = key.get_indexer(mine)
        self.n_no_raw = int((ix < 0).sum())
        r = np.where(ix >= 0, raw["r"].to_numpy()[np.maximum(ix, 0)], np.nan)
        with np.errstate(invalid="ignore", divide="ignore"):
            fac = r / self.c
        self.fac = np.where(np.isfinite(fac) & (fac > 0), fac, 1.0)
        self.raw_source = f"MEASURED per bar from {path.name} ({self.n - self.n_no_raw:,} of {self.n:,} bars matched)"

    def _raw_from_splits(self, path: Path):
        sp = load_splits(path, self.last_session)
        for t, lst in sp.items():
            k = self.tid.get(t)
            if k is None:
                continue
            a, b = self.start[k], self.stop[k]
            dates = self.dstr[a:b]
            ex = np.array([d for d, _ in lst])
            ratio = np.array([r for _, r in lst])
            # factor on date x = product of ratios with exec_date > x  (the execution date itself is already post-split)
            suffix = np.concatenate((np.cumprod(ratio[::-1])[::-1], [1.0]))     # suffix[j] = product of ratio[j:]
            j = np.searchsorted(ex, dates, side="right")                          # splits with exec_date <= x are excluded
            self.fac[a:b] = suffix[j]
        self.n_split_tickers = sum(1 for t in sp if t in self.tid)
        self.raw_source = f"DERIVED from the split list {path.name} ({sum(len(v) for v in sp.values()):,} splits <= {self.last_session}, {self.n_split_tickers:,} tickers in export)"

    @property
    def raw(self) -> np.ndarray:
        return self.c * self.fac


def rolling_median_dv(E: Era) -> np.ndarray:
    """median(close*volume) over the 20 bars ending at each bar (the module's `_dollar_vol_median`); NaN until 20 bars of the same ticker."""
    from numpy.lib.stride_tricks import sliding_window_view
    dv = E.c * E.v
    out = np.full(E.n, np.nan)
    W, step = DOLLAR_VOL_WINDOW, 1_000_000
    for a in range(0, E.n - W + 1, step):
        b = min(E.n - W + 1, a + step)
        out[a + W - 1:b + W - 1] = np.median(sliding_window_view(dv[a:b + W - 1], W), axis=1)
    out[E.pos < W - 1] = np.nan
    return out


def contiguous(E: Era) -> np.ndarray:
    """130 bars ending here are consecutive SPY sessions (runner.contiguous_window_mask)."""
    out = np.zeros(E.n, dtype=bool)
    ok = (E.pos >= MIN_HISTORY - 1) & E.on_cal
    idx = np.flatnonzero(ok)
    out[idx] = (E.ci[idx] - E.ci[idx - (MIN_HISTORY - 1)]) == MIN_HISTORY - 1
    return out


def spac_like(E: Era, raw: np.ndarray) -> np.ndarray:
    """Trust-price signature at bar i: over the last 60 bars (max-min)/min of the RAW close <= 5%, their median in [9, 11], AND the median
    close*volume of those bars is BELOW the $10M universe floor (a $10 stock that flat AND illiquid is a SPAC shell; Annaly-type
    low-volatility REITs trade far above the floor and are not flagged)."""
    from numpy.lib.stride_tricks import sliding_window_view
    W, step = 60, 1_000_000
    dv = E.c * E.v
    out = np.zeros(E.n, dtype=bool)
    for a in range(0, E.n - W + 1, step):
        b = min(E.n - W + 1, a + step)
        win = sliding_window_view(raw[a:b + W - 1], W)
        dwin = sliding_window_view(dv[a:b + W - 1], W)
        mx, mn, md = win.max(axis=1), win.min(axis=1), np.median(win, axis=1)
        with np.errstate(divide="ignore", invalid="ignore"):
            flat = (mx - mn) / mn <= 0.05
        out[a + W - 1:b + W - 1] = flat & (md >= 9.0) & (md <= 11.0) & (np.median(dwin, axis=1) < MIN_DOLLAR_VOL)
    out[E.pos < W - 1] = False
    return out


def spac_in_prior(E: Era, sp: np.ndarray, window: int = MIN_HISTORY) -> np.ndarray:
    """True at bar i when a trust-price bar sits among the `window` bars BEFORE i (same ticker): the setup's 130-bar history contains a SPAC-shell phase."""
    cs = np.concatenate(([0], np.cumsum(sp.astype(np.int64))))          # cs[k] = count in [0, k)
    out = np.zeros(E.n, dtype=bool)
    i = np.flatnonzero(E.pos >= window)
    out[i] = (cs[i] - cs[i - window]) > 0                                # bars [i-window, i-1]
    return out


def fac_steps(E: Era, thr: float = 0.05) -> np.ndarray:
    """Indices of the first bar of a >thr (log) change in raw/adjusted within one ticker: a split. (Sub-0.1% steps are rounding in the raw file,
    not dividends: the Alpaca-era adjusted series is split-adjusted only -- measured below.)"""
    st = np.abs(np.log(E.fac[1:] / E.fac[:-1]))
    return np.flatnonzero((st > thr) & (E.code[1:] == E.code[:-1])) + 1


# --- the audit ------------------------------------------------------------------------------------------------------------------------
def resolve_type(t: str, small: dict, sic: dict) -> tuple[str, str]:
    """(type, source) exactly as `consolidation_breakout.resolve_sectype`: mi_security_types, else the SIC pull's type, else ''."""
    if small.get(t, ("", ""))[0]:
        return small[t][0], "mi"
    if sic.get(t, ("", "", "", ""))[2]:
        return sic[t][2], "sic"
    return "", "none"


def ticker_flags(t: str, rtype: str, src: str, name_cls: str, small: dict, sic: dict, assets: dict) -> list[str]:
    fl = []
    if rtype == "":
        fl.append("UNKNOWN_TYPE_ADMITTED")
    if rtype in UNIVERSE_SECURITY_TYPES or rtype == "":
        if name_cls in EXCLUDED_NAME_CLASSES:
            fl.append(f"NAME_SAYS_{name_cls}" + ("_BUT_TYPED_" + rtype if rtype else "_UNTYPED"))
        if name_cls == "SPAC_SHELL":
            fl.append("NAME_SAYS_SPAC_SHELL")
    mi, sc = small.get(t, ("", ""))[0], sic.get(t, ("", "", "", ""))[2]
    if mi and sc and mi != sc and ((mi in UNIVERSE_SECURITY_TYPES) != (sc in UNIVERSE_SECURITY_TYPES)):
        fl.append(f"MI_SIC_DISAGREE_{mi}_vs_{sc}")
    if len(t) == 5 and t[-1] in "UWR" and name_cls in ("SPAC_UNIT", "WARRANT", "RIGHT"):
        fl.append("SUFFIX_UWR_INSTRUMENT")
    a = assets.get(t)
    if a is not None and a[2] == "OTC":
        fl.append("OTC_TODAY" + ("_FOREIGN_SUFFIX" if re.fullmatch(r"[A-Z]{4}[FY]", t) else ""))      # today's record; a stock that fell to OTC later is NOT point-in-time OTC
    elif a is not None and a[1] == "active" and not a[3]:
        fl.append("ACTIVE_BUT_NOT_TRADABLE")
    mic = small.get(t, ("", ""))[1]
    if mic and mic not in ("XNYS", "XNAS", "XASE", "ARCX", "BATS"):
        fl.append(f"MIC_{mic}")
    if sic.get(t, ("",))[0] == "6770":
        fl.append("SIC_6770_BLANK_CHECK")
    return fl


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0], formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--export", required=True, type=Path)
    ap.add_argument("--era", required=True, help="label used in file names")
    ap.add_argument("--raw-close", type=Path, help="headerless ticker,date,raw_close (measured raw; the Alpaca-era file)")
    ap.add_argument("--splits", type=Path, help="cb702_splits.psv (raw = adjusted x product of later split ratios)")
    ap.add_argument("--small", required=True, type=Path, help="small_pulls.psv (mi_security_types)")
    ap.add_argument("--sic", required=True, type=Path, help="cb702_sic.psv")
    ap.add_argument("--assets", required=True, type=Path, help="Alpaca assets.tsv (names, status, exchange, tradable)")
    ap.add_argument("--watch-start", required=True)
    ap.add_argument("--watch-end", required=True)
    ap.add_argument("--cutoff", default="2024-12-31", help="bars after this date are dropped at load (sealed table)")
    ap.add_argument("--vs-export", type=Path, help="second export for the raw-close overlap check")
    ap.add_argument("--vs-raw-close", type=Path)
    ap.add_argument("--vs-splits", type=Path)
    ap.add_argument("--verified-real", default="", help="comma list of tickers you hand-verified as NOT common stock/ADR (adds a VERIFIED_NON_COMMON impact row)")
    ap.add_argument("--impact", action="append", default=[], metavar="FILE[::QUERY[::DATECOL[::RCOL]]]",
                    help="tab-separated (gz ok) watch/entry/trade table: counts (and R if RCOL) on flagged vs all tickers; repeatable. QUERY is a pandas query; DATECOL default D")
    ap.add_argument("--breaks", type=Path, help="symbol_guard.tsv (columns symbol, breaks='YYYY-MM-DD:kind;...'): adds the identity-break exposure of the resolved type")
    ap.add_argument("--max-unknown-share", type=float, default=None, help="exit 3 if UNKNOWN-typed nights exceed this share of admitted nights (a gate for future runs)")
    ap.add_argument("--max-verified-nights", type=int, default=None, help="exit 3 if --verified-real tickers carry more than this many admitted member nights")
    ap.add_argument("--out", required=True, type=Path)
    a = ap.parse_args(argv)
    a.out.mkdir(parents=True, exist_ok=True)
    say = lambda s="": print(s, flush=True)

    try:                                                    # keep the constants honest against the module the runner calls
        sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
        import agents.market_intelligence.consolidation_breakout as cb
        assert (cb.MIN_PRICE, cb.MIN_DOLLAR_VOL, cb.MIN_HISTORY, cb.UNIVERSE_TICKER_RE.pattern) == (MIN_PRICE, MIN_DOLLAR_VOL, MIN_HISTORY, UNIVERSE_TICKER_RE.pattern)
        assert cb.UNIVERSE_SECURITY_TYPES == UNIVERSE_SECURITY_TYPES and cb.DOLLAR_VOL_WINDOW == DOLLAR_VOL_WINDOW
        say("constants: identical to agents/market_intelligence/consolidation_breakout.py")
    except ImportError:
        say("constants: module not importable here; using the copies in this file (CHECK THEM against consolidation_breakout.py)")

    small, sic, assets = load_small(a.small), load_sic(a.sic), load_assets(a.assets)
    brk = load_breaks(a.breaks) if a.breaks else {}
    df, last = load_export(a.export, a.cutoff)
    E = Era(df, last, a.raw_close, a.splits)
    del df
    say(f"ERA {a.era}: {E.n:,} bars (<= {a.cutoff}) / {len(E.tickers):,} tickers; export last session {last}; off-calendar bars {int((~E.on_cal).sum()):,}")
    say(f"  raw close: {E.raw_source}")
    say(f"  type sources: mi_security_types {len(small):,} tickers (snapshot 2026-10-16, exchange-listed only); SIC pull {len(sic):,} tickers; Alpaca assets {len(assets):,} symbols")

    raw = E.raw
    dvmed = rolling_median_dv(E)
    contig = contiguous(E)
    rx_ok_t = np.array([bool(UNIVERSE_TICKER_RE.fullmatch(t)) for t in E.tickers])
    test_t = np.array([(t in TEST_SYMBOLS) or bool(TEST_FAMILY.fullmatch(t)) for t in E.tickers])
    in_win = (E.dstr >= a.watch_start) & (E.dstr <= a.watch_end)
    base_ok = rx_ok_t[E.code] & ~test_t[E.code] & contig & np.nan_to_num(dvmed, nan=0.0).__ge__(MIN_DOLLAR_VOL) & in_win   # everything but price
    adm = base_ok & (raw >= MIN_PRICE)
    n_base, n_adm = int(base_ok.sum()), int(adm.sum())
    say(f"\n[U0] WATCH WINDOW {a.watch_start}..{a.watch_end}: ticker-nights {int(in_win.sum()):,}; regex+not-test+130-consecutive+$10M-median-dollar-volume (no price test) {n_base:,}; "
        f"+ RAW close >= $5 = {n_adm:,} universe-member nights on {len(set(E.code[adm].tolist())):,} tickers (BEFORE the security-type filter)")
    if int((~rx_ok_t).sum()):
        rg = ~rx_ok_t[E.code] & contig & (np.nan_to_num(dvmed, nan=0.0) >= MIN_DOLLAR_VOL) & (raw >= MIN_PRICE) & in_win
        say(f"     regex-EXCLUDED (liquid, >= $5) nights: {int(rg.sum()):,} on {len(set(E.code[rg].tolist())):,} tickers (examples: {', '.join(sorted({E.tickers[k] for k in set(E.code[rg].tolist())})[:8])})")

    # ── per-ticker table over the member tickers ───────────────────────────────────────────────────────────────────────
    mem_codes = np.unique(E.code[adm])
    nights = Counter(E.code[adm].tolist())
    sp = spac_like(E, raw)
    sp_prior = spac_in_prior(E, sp)
    idx_by = pd.Series(np.flatnonzero(adm)).groupby(E.code[adm]).agg(list) if n_adm else {}
    rows = []
    for k in mem_codes:
        ix = np.array(idx_by[k])
        t = E.tickers[k]
        rtype, src = resolve_type(t, small, sic)
        nm = assets.get(t, ("", "", "", False))[0]
        ncls = classify_name(nm)
        fl = ticker_flags(t, rtype, src, ncls, small, sic, assets)
        nsp = int(sp[ix].sum()); nsp_prior = int(sp_prior[ix].sum())
        bl = brk.get(t, [])
        n_pre_break = int((E.dstr[ix] < bl[-1][0]).sum()) if bl else 0          # nights dated before the LAST identity break: the type resolved is the later holder's
        if n_pre_break:
            fl.append("IDENTITY_BREAK_AFTER_NIGHTS_TYPE_IS_LATER_HOLDERS")
        if (nsp or nsp_prior) and (rtype in UNIVERSE_SECURITY_TYPES or rtype == ""):
            fl.append("SPAC_SHELL_PHASE_IN_130BAR_HISTORY" if nsp_prior else "SPAC_TRUST_PRICE_NIGHTS")
        a_ = assets.get(t)
        rows.append({
            "ticker": t, "resolved_type": rtype or "UNKNOWN", "type_source": src, "mi_type": small.get(t, ("", ""))[0], "mi_mic": small.get(t, ("", ""))[1],
            "sic_type": sic.get(t, ("", "", "", ""))[2], "sic_code": sic.get(t, ("", "", "", ""))[0],
            "name_class": ncls, "name": nm[:60], "assets_status": a_[1] if a_ else "",
            "name_holder": ("current" if (a_ and a_[1] == "active") else ("LAST holder of a delisted symbol (reuse risk)" if a_ else "none")), "assets_exchange": a_[2] if a_ else "", "assets_tradable": a_[3] if a_ else "",
            "admitted_by_type_filter": (rtype in UNIVERSE_SECURITY_TYPES) or rtype == "",
            "member_nights": len(ix), "first_member": str(E.dstr[ix[0]]), "last_member": str(E.dstr[ix[-1]]),
            "median_raw_close": round(float(np.median(raw[ix])), 2), "median_dv20_musd": round(float(np.median(dvmed[ix])) / 1e6, 1),
            "spac_like_nights": nsp, "spac_in_prior130_nights": nsp_prior, "identity_breaks": ";".join(f"{d}:{k}" for d, k in bl), "nights_before_last_break": n_pre_break, "flag_list": ";".join(fl)})
    T = pd.DataFrame(rows)
    T.to_csv(a.out / f"members_all_{a.era}.tsv", sep="\t", index=False)

    # ── U1: resolved type x admitted ──────────────────────────────────────────────────────────────────────────────────────
    say("\n[U1] RESOLVED SECURITY TYPE of every price+liquidity-passing ticker (nights = universe-member nights BEFORE the type filter)")
    g = T.groupby(["resolved_type", "admitted_by_type_filter"]).agg(tickers=("ticker", "count"), nights=("member_nights", "sum")).reset_index().sort_values("nights", ascending=False)
    g.to_csv(a.out / f"type_table_{a.era}.tsv", sep="\t", index=False)
    say(g.to_string(index=False))
    A = T[T.admitted_by_type_filter]
    say(f"  ADMITTED by the type filter: {len(A):,} tickers / {int(A.member_nights.sum()):,} nights;  EXCLUDED by type: {int((~T.admitted_by_type_filter).sum()):,} tickers / "
        f"{int(T.loc[~T.admitted_by_type_filter, 'member_nights'].sum()):,} nights")
    unk = A[A.resolved_type == "UNKNOWN"]
    say(f"  UNKNOWN type admitted (no mi, no SIC type): {len(unk):,} tickers = {len(unk) / max(len(A), 1):.1%} of admitted tickers; {int(unk.member_nights.sum()):,} nights = "
        f"{unk.member_nights.sum() / max(A.member_nights.sum(), 1):.1%} of admitted nights")
    say(f"  type source of ADMITTED nights: " + ", ".join(f"{s}={int(v):,}" for s, v in A.groupby('type_source').member_nights.sum().items()))

    # ── U2: name class vs type among ADMITTED ────────────────────────────────────────────────────────────────────────────
    say("\n[U2] NAME CLASS (Alpaca/Polygon asset name) of ADMITTED tickers  [COMMON? = no non-common cue in the name; NO_NAME = symbol not in the asset list]")
    x = pd.crosstab(A.name_class, A.resolved_type.where(A.resolved_type.isin(["CS", "ADRC"]), "UNKNOWN"), values=A.member_nights, aggfunc="sum").fillna(0).astype(int)
    xt = pd.crosstab(A.name_class, A.resolved_type.where(A.resolved_type.isin(["CS", "ADRC"]), "UNKNOWN"))
    say("  nights:"); say(x.to_string()); say("  tickers:"); say(xt.to_string())
    bad = A[A.name_class.isin(EXCLUDED_NAME_CLASSES)]
    say(f"  ADMITTED but NAMED like a non-common instrument ({'/'.join(sorted(EXCLUDED_NAME_CLASSES))}): {len(bad):,} tickers / {int(bad.member_nights.sum()):,} nights "
        f"= {bad.member_nights.sum() / max(A.member_nights.sum(), 1):.2%} of admitted nights; of these UNTYPED {int((bad.resolved_type == 'UNKNOWN').sum()):,}, typed CS/ADRC {int((bad.resolved_type != 'UNKNOWN').sum()):,}")
    for cls, sub in bad.groupby("name_class"):
        say(f"    {cls:<18} {len(sub):>4} tickers {int(sub.member_nights.sum()):>8,} nights   e.g. " + ", ".join(f"{r.ticker}({r.resolved_type},{r.member_nights})" for r in sub.sort_values('member_nights', ascending=False).head(6).itertuples()))

    # ── U3 / U4 / U5 ─────────────────────────────────────────────────────────────────────────────────────────────────────
    dis = A[A["flag_list"].str.contains("MI_SIC_DISAGREE")]
    say(f"\n[U3] mi_security_types vs SIC-pull type DISAGREE across the admit line on {len(dis):,} admitted tickers ({int(dis.member_nights.sum()):,} nights); "
        f"both sources present on {int(((A.mi_type != '') & (A.sic_type != '')).sum()):,} admitted tickers")
    otc = A[A["flag_list"].str.contains("OTC_TODAY|ACTIVE_BUT_NOT_TRADABLE")]
    say(f"[U4] ADMITTED tickers on OTC today / active-but-not-tradable in the Alpaca asset list: {len(otc):,} tickers / {int(otc.member_nights.sum()):,} nights "
        f"({otc.member_nights.sum() / max(A.member_nights.sum(), 1):.2%} of admitted nights); not in the asset list at all: {int((A.name_class == 'NO_NAME').sum()):,} tickers / {int(A.loc[A.name_class == 'NO_NAME', 'member_nights'].sum()):,} nights")
    spa = A[(A.spac_like_nights > 0) | (A.spac_in_prior130_nights > 0)]
    say(f"[U5] ADMITTED tickers whose 130-bar history holds a SPAC trust-price phase (flat ~$10 AND below the $10M liquidity floor): {len(spa):,} tickers; "
        f"{int((spa.spac_in_prior130_nights).sum()):,} member nights carry one in their history, {int(spa.spac_like_nights.sum()):,} are themselves trust-price nights; "
        f"typed CS/ADRC {int((spa.resolved_type != 'UNKNOWN').sum()):,}, UNKNOWN {int((spa.resolved_type == 'UNKNOWN').sum()):,};  e.g. "
        + ", ".join(f"{r.ticker}({r.resolved_type},{r.spac_in_prior130_nights})" for r in spa.sort_values('spac_in_prior130_nights', ascending=False).head(10).itertuples()))
    suf = A[A["flag_list"].str.contains("SUFFIX_UWR")]
    say(f"[U6] ADMITTED 5-letter U/W/R-suffix instruments (units/warrants/rights passing ^[A-Z]{{1,5}}$): {len(suf):,} tickers / {int(suf.member_nights.sum()):,} nights")

    X = T[~T.admitted_by_type_filter]
    xs = X[X.ticker.str.fullmatch(r"[A-Z]{4}[UWR]")]
    say(f"[U6b] EXCLUDED-by-type tickers that pass regex + $5 + $10M and whose ONLY barrier is the type: {len(X):,} tickers / {int(X.member_nights.sum()):,} nights = "
        f"{X.member_nights.sum() / max(T.member_nights.sum(), 1):.1%} of all price+liquidity-passing nights; of them 5-letter U/W/R-suffix (unit/warrant/right look-alikes) {len(xs):,}"
        + (" (" + ", ".join(f"{r.ticker}:{r.resolved_type}" for r in xs.itertuples()) + ")" if len(xs) else ""))
    FALSE_EXCL = X[X.name_class.isin(["COMMON?", "ADR"]) & ~X.resolved_type.isin(["ETV", "ETF", "ETN", "ETS"])]
    say(f"[U7] EXCLUDED-by-type but named like an operating company / common units (possible FALSE exclusion; symbol re-use or REIT/MLP typed FUND/UNIT/SP): {len(FALSE_EXCL):,} tickers / {int(FALSE_EXCL.member_nights.sum()):,} nights  e.g. "
        + ", ".join(f"{r.ticker}({r.resolved_type},{r.member_nights})" for r in FALSE_EXCL.sort_values('member_nights', ascending=False).head(8).itertuples()))
    if brk:
        ib = A[A.nights_before_last_break > 0]
        kinds = Counter(k for r in ib.itertuples() for _d, k in [x.split(':') for x in r.identity_breaks.split(';')])
        say(f"[U8] ADMITTED tickers with an identity break (symbol_guard) AFTER some of their member nights: {len(ib):,} of {len(A):,} tickers; {int(ib.nights_before_last_break.sum()):,} of {int(A.member_nights.sum()):,} "
            f"admitted nights ({ib.nights_before_last_break.sum() / max(A.member_nights.sum(), 1):.2%}) are dated before the last break, so their type is the LATER holder's; break kinds {dict(kinds)}; "
            f"of these UNKNOWN-typed {int((ib.resolved_type == 'UNKNOWN').sum()):,}, typed CS/ADRC {int((ib.resolved_type != 'UNKNOWN').sum()):,}")
    flagged = A[A["flag_list"] != ""].sort_values("member_nights", ascending=False)
    flagged.to_csv(a.out / f"flagged_tickers_{a.era}.tsv", sep="\t", index=False)
    say(f"\nFLAGGED admitted tickers: {len(flagged):,} of {len(A):,} ({int(flagged.member_nights.sum()):,} of {int(A.member_nights.sum()):,} nights = {flagged.member_nights.sum() / max(A.member_nights.sum(), 1):.1%}) -> flagged_tickers_{a.era}.tsv")
    say("  flag counts (tickers / nights):")
    fc, fn = Counter(), Counter()
    for r in flagged.itertuples():
        for f in r.flag_list.split(";"):
            key = re.sub(r"_(BUT_TYPED|vs)_.*", "", f) if f.startswith(("NAME_SAYS", "MI_SIC")) else f
            fc[key] += 1; fn[key] += r.member_nights
    for k_, v in fc.most_common():
        say(f"    {k_:<40} {v:>5} tickers {fn[k_]:>9,} nights")

    # by-year unknown-type share
    yr = pd.Series(E.dstr[adm]).str[:4]
    tcodes = E.code[adm]
    isadm_t = np.array([(resolve_type(t, small, sic)[0] in UNIVERSE_SECURITY_TYPES) or (resolve_type(t, small, sic)[0] == "") for t in E.tickers])
    unk_t = np.array([resolve_type(t, small, sic)[0] == "" for t in E.tickers])
    flagged_set = set(flagged.ticker)
    flag_t = np.array([t in flagged_set for t in E.tickers])
    by = pd.DataFrame({"year": yr.to_numpy(), "adm": isadm_t[tcodes], "unk": unk_t[tcodes], "flag": flag_t[tcodes]})
    byy = by.groupby("year").agg(member_nights=("adm", "size"), admitted_by_type=("adm", "sum"), unknown_type=("unk", "sum"), flagged=("flag", "sum")).reset_index()
    byy["unknown_share_of_admitted"] = (byy.unknown_type / byy.admitted_by_type).round(4)
    byy["flagged_share_of_admitted"] = (byy.flagged / byy.admitted_by_type).round(4)
    byy.to_csv(a.out / f"member_by_year_{a.era}.tsv", sep="\t", index=False)
    say("\n[by year] universe-member nights (before type filter) / admitted by type / unknown-typed / on a flagged ticker:")
    say(byy.to_string(index=False))

    # ── impact on a downstream population (watch rows / entries / trades) ─────────────────────────────────────────────────
    if a.impact:
        groups = {"ALL_ADMITTED": set(A.ticker), "ANY_FLAG": set(flagged.ticker)}
        for k_ in sorted(fc):
            groups[k_] = {r.ticker for r in flagged.itertuples() if any(f.startswith(k_) for f in r.flag_list.split(";"))}
        if a.verified_real:
            groups["VERIFIED_NON_COMMON"] = {x.strip() for x in a.verified_real.split(",") if x.strip()}
        unk_set = set(A.loc[A.resolved_type == "UNKNOWN", "ticker"])
        groups["UNKNOWN_TYPE"] = unk_set
        for spec in a.impact:
            parts_ = spec.split("::")
            path_, query_ = parts_[0], (parts_[1] if len(parts_) > 1 else "")
            dcol, rcol = (parts_[2] if len(parts_) > 2 and parts_[2] else "D"), (parts_[3] if len(parts_) > 3 else "")
            tr = pd.read_csv(path_, sep="\t", low_memory=False)
            if query_:
                tr = tr.query(query_)
            tr = tr[(tr[dcol].astype(str) >= a.watch_start) & (tr[dcol].astype(str) <= a.watch_end)]
            if rcol:
                tr = tr[tr[rcol].notna()]
            say(f"\n[IMPACT] {Path(path_).name} [{query_ or 'all rows'}], {dcol} {a.watch_start}..{a.watch_end}: {len(tr):,} rows on {tr['ticker'].nunique():,} tickers" + (f"; R column {rcol}" if rcol else " (counts only, no outcome read)"))
            rows_ = []
            for gname, gset in groups.items():
                sub = tr[tr["ticker"].isin(gset)]
                r_ = {"group": gname, "tickers_in_group": len(gset), "rows": len(sub), "share_of_rows": round(len(sub) / max(len(tr), 1), 4)}
                if rcol:
                    r_.update({"sum_R": round(float(sub[rcol].sum()), 1), "mean_R": round(float(sub[rcol].mean()), 3) if len(sub) else float("nan"),
                               "n_ge_4R": int((sub[rcol] >= 4).sum()), "share_ge_4R_of_all": round(int((sub[rcol] >= 4).sum()) / max(int((tr[rcol] >= 4).sum()), 1), 4)})
                rows_.append(r_)
            imp_df = pd.DataFrame(rows_)
            imp_df.to_csv(a.out / f"impact_{a.era}_{Path(path_).name.split('.')[0]}.tsv", sep="\t", index=False)
            say(imp_df.to_string(index=False))

    # ── P1: price-floor units ────────────────────────────────────────────────────────────────────────────────────────────
    adj_ok, raw_ok = E.c >= MIN_PRICE, raw >= MIN_PRICE
    a_only, r_only = base_ok & adj_ok & ~raw_ok, base_ok & ~adj_ok & raw_ok
    ff = [{"flip": "adjusted>=5 but RAW<5 (adjusted floor ADMITS, raw floor excludes)", "nights": int(a_only.sum()), "tickers": len(set(E.code[a_only].tolist()))},
          {"flip": "RAW>=5 but adjusted<5 (adjusted floor EXCLUDES a real >=$5 stock)", "nights": int(r_only.sum()), "tickers": len(set(E.code[r_only].tolist()))},
          {"flip": "both pass (base)", "nights": int((base_ok & adj_ok & raw_ok).sum()), "tickers": len(set(E.code[base_ok & adj_ok & raw_ok].tolist()))}]
    pd.DataFrame(ff).to_csv(a.out / f"floor_flips_{a.era}.tsv", sep="\t", index=False)
    say("\n[P1] $5 FLOOR UNITS (nights in the watch window passing regex/test/130-consecutive/$10M-dollar-volume):")
    for r in ff:
        say(f"    {r['flip']:<75} {r['nights']:>9,} nights {r['tickers']:>5,} tickers")
    big = np.flatnonzero(a_only)
    if len(big):
        top = Counter(E.code[big].tolist()).most_common(5)
        say("    adjusted-admits/raw-excludes top: " + ", ".join(f"{E.tickers[k]}({n})" for k, n in top))
    st_all = np.abs(np.log(E.fac[1:] / E.fac[:-1])); same = E.code[1:] == E.code[:-1]
    steps = fac_steps(E)
    say(f"    raw/adjusted steps within a ticker: > 5%: {len(steps):,} on {len(set(E.code[steps].tolist())):,} tickers (splits); 0.1%-5%: {int(((st_all > 0.001) & (st_all <= 0.05) & same).sum()):,} "
        f"(dividend-sized: ~0 means the adjusted series is SPLIT-adjusted only); < 0.1%: {int(((st_all > 0) & (st_all <= 0.001) & same).sum()):,} (rounding noise); "
        f"factor range {E.fac.min():.3g}..{E.fac.max():.3g}; bars with |factor-1| > 0.1%: {int((np.abs(E.fac - 1) > 0.001).sum()):,} ({(np.abs(E.fac - 1) > 0.001).mean():.1%})")
    ext = np.flatnonzero((E.fac < 1e-3) | (E.fac > 1e3))
    say(f"    EXTREME raw/adjusted factors (< 1e-3 or > 1e3): {len(ext):,} bars on {len(set(E.code[ext].tolist())):,} tickers (repeated reverse splits; adjusted prices of 1e5 and up) -- "
        f"the floor must be read on RAW; e.g. " + ", ".join(sorted({E.tickers[k] for k in set(E.code[ext].tolist())})[:8]))

    # ── P2: dollar-volume split invariance (with a no-split control) ────────────────────────────────────────────────────
    ok = [i for i in steps if E.pos[i] >= 5 and i + 5 <= E.stop[E.code[i]]]
    if ok:
        dv = E.c * E.v
        rat = np.array([np.median(dv[i:i + 5]) / max(np.median(dv[i - 5:i]), 1.0) for i in ok])
        sr = np.array([E.fac[i] / E.fac[i - 1] for i in ok])
        inv = (rat > 1 / 1.5) & (rat < 1.5)
        with np.errstate(divide="ignore", invalid="ignore"):
            unadj = np.abs(np.log(rat * sr)) < np.log(1.3)           # ratio ~ 1/step: close*volume moved by the split => volume NOT adjusted
            over = np.abs(np.log(rat / sr)) < np.log(1.3)            # ratio ~ step: volume adjusted TWICE
        both = inv & unadj
        ctl = []
        for i in ok:                                                        # control: the same ticker 40 bars later, if no step within +-20 bars of it
            j = i + 40
            if j + 5 <= E.stop[E.code[i]] and not ((steps > j - 20) & (steps < j + 20)).any():
                ctl.append(np.median(dv[j:j + 5]) / max(np.median(dv[j - 5:j]), 1.0))
        ctl = np.array(ctl)
        say(f"\n[P2] 5-bar median close*volume after / before {len(ok):,} split steps: within 1.5x either way {inv.mean():.1%} (control, same tickers 40 bars later, n={len(ctl):,}: "
            f"{((ctl > 1/1.5) & (ctl < 1.5)).mean():.1%}); splits where the ratio moves like the split itself (volume NOT adjusted, within 1.3x of 1/step) {int((unadj & ~both).sum()):,} "
            f"of {len(ok):,} ({(unadj & ~both).mean():.1%}); over-adjusted (ratio within 1.3x of the step) {int((over & ~both).sum()):,}; median ratio {np.median(rat):.3f} (control {np.median(ctl):.3f})")
        big_ = np.abs(np.log(sr)) >= np.log(4)                              # steps >= 4x separate the three hypotheses (a 2:1 step cannot tell 'invariant' from 'adjusted twice')
        inv_b, un_b, ov_b = inv[big_], unadj[big_], over[big_]
        say(f"     BIG steps (>= 4x either way) n={int(big_.sum()):,}: dollar volume continuous (ratio within 1.5x) {int(inv_b.sum()):,}; moves like 1/step (volume NOT adjusted) {int(un_b.sum()):,}; "
            f"moves like the step (adjusted twice) {int(ov_b.sum()):,}; none of the three {int((~inv_b & ~un_b & ~ov_b).sum()):,}; median ratio {np.median(rat[big_]) if big_.any() else float('nan'):.3f}")
        fwd, rev = sr < 1, sr > 1
        say(f"     forward splits n={int(fwd.sum()):,}: median ratio {np.median(rat[fwd]) if fwd.any() else float('nan'):.3f};  reverse splits n={int(rev.sum()):,}: median ratio {np.median(rat[rev]) if rev.any() else float('nan'):.3f}")
    else:
        say("\n[P2] no split steps detected: dollar-volume invariance not testable on this export/raw source")

    # ── cross-export overlap of the raw close (independent raw sources) ────────────────────────────────────────────────────
    if a.vs_export:
        df2, last2 = load_export(a.vs_export, a.cutoff)
        E2 = Era(df2, last2, a.vs_raw_close, a.vs_splits)
        del df2
        s1 = pd.DataFrame({"t": np.array(E.tickers, dtype=object)[E.code], "d": E.dstr, "r1": raw, "a1": E.c})
        s2 = pd.DataFrame({"t": np.array(E2.tickers, dtype=object)[E2.code], "d": E2.dstr, "r2": E2.raw, "a2": E2.c})
        m = s1.merge(s2, on=["t", "d"]).sort_values(["t", "d"]).reset_index(drop=True)
        la1, la2 = np.log(m.a1.clip(lower=1e-12)), np.log(m.a2.clip(lower=1e-12))
        same_t = m.t.eq(m.t.shift(1))
        dret = ((la1 - la1.shift(1)) - (la2 - la2.shift(1))).abs().where(same_t)
        agree = dret.lt(0.002)
        frac = agree.groupby(m.t).mean()
        same_co = set(frac.index[frac >= 0.9])
        m["same_company"] = m.t.isin(same_co)
        say(f"\n[P1x] CROSS-EXPORT OVERLAP {m.d.min()}..{m.d.max()}: {len(m):,} (ticker,date) bars on {m.t.nunique():,} tickers; this export raw = {E.raw_source.split(' ')[0]}, --vs raw = {E2.raw_source.split(' ')[0]}")
        say(f"     SAME COMPANY (>= 90% of overlap days have daily returns within 0.2% of each other): {len(same_co):,} tickers; "
            f"DIFFERENT COMPANY on the same symbol (symbol reuse across the two exports): {m.t.nunique() - len(same_co):,} tickers")
        sc = m[m.same_company]
        rel = (sc.r1 / sc.r2 - 1).abs()
        fl_diff = ((sc.r1 >= MIN_PRICE) != (sc.r2 >= MIN_PRICE))
        say(f"     SAME-COMPANY raw-close agreement: {len(sc):,} bars on {sc.t.nunique():,} tickers; |raw1/raw2 - 1| > 1%: {int((rel > 0.01).sum()):,} bars ({(rel > 0.01).mean():.3%}) on {sc[rel > 0.01].t.nunique():,} tickers;  "
            f"> 10%: {int((rel > 0.10).sum()):,} bars on {sc[rel > 0.10].t.nunique():,} tickers;  $5-floor decision differs: {int(fl_diff.sum()):,} bars on {sc[fl_diff].t.nunique():,} tickers"
            + (" (" + ", ".join(sorted(sc[fl_diff].t.unique())[:12]) + ")" if fl_diff.any() else ""))
        both_liq = (m.r1 >= MIN_PRICE) & (m.r2 >= MIN_PRICE)
        dc = m[~m.same_company]
        say(f"     DIFFERENT-COMPANY symbols: {dc.t.nunique():,} tickers / {len(dc):,} bars; of which both sides >= $5 raw on {int(((dc.r1 >= MIN_PRICE) & (dc.r2 >= MIN_PRICE)).sum()):,} bars; "
            f"examples: {', '.join(sorted(dc.t.unique())[:12])}")
        m[(m.r1 / m.r2 - 1).abs() > 0.01].to_csv(a.out / f"raw_disagree_{a.era}.tsv", sep="\t", index=False)
        adjrel = (sc.a1 / sc.a2 - 1).abs()
        say(f"     SAME-COMPANY ADJUSTED-close agreement: |a1/a2 - 1| > 1% on {int((adjrel > 0.01).sum()):,} bars ({(adjrel > 0.01).mean():.3%}) on {sc[adjrel > 0.01].t.nunique():,} tickers (two providers, adjusted to the same 2026-10-16 date: a level gap here is a split-handling difference)")
    say(f"\nOutputs -> {a.out}")
    rc = 0
    unk_share = unk.member_nights.sum() / max(A.member_nights.sum(), 1)
    if a.max_unknown_share is not None and unk_share > a.max_unknown_share:
        say(f"GATE FAIL: unknown-type share of admitted nights {unk_share:.2%} > {a.max_unknown_share:.2%} -- resolve types point-in-time before reading this export"); rc = 3
    vr = {x.strip() for x in a.verified_real.split(",") if x.strip()}
    vn = int(A.loc[A.ticker.isin(vr), "member_nights"].sum()) if vr else 0
    if a.max_verified_nights is not None and vn > a.max_verified_nights:
        say(f"GATE FAIL: {vn:,} admitted nights on verified non-common tickers > {a.max_verified_nights:,}"); rc = 3
    return rc


def _selftest():
    assert classify_name("VelocityShares 3x Inverse Crude Oil ETNs") == "ETN"
    assert classify_name("Direxion Daily Russia Bull 2X Shares") == "LEVERAGED_INVERSE"
    assert classify_name("iShares MSCI Russia ETF") == "ETF"
    assert classify_name("Invesco LTD") == "COMMON?" and classify_name("Ultra Clean Holdings, Inc. Common Stock") == "COMMON?"
    assert classify_name("Preferred Bank Common Stock") == "COMMON?" and classify_name("Vodafone Group Plc American Depositary Shares") == "ADR"
    assert classify_name("America Movil S.A.B de C.V American Depositary Shares (each representing the right to receive twenty (20) Series B Shares)") == "ADR"
    assert classify_name("DJT Warrants") == "WARRANT" and classify_name("") == "NO_NAME"
    assert classify_name("Mach Natural Resources LP Common Units representing Limited Partner Interests") == "COMMON?"
    print("selftest ok")


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        _selftest()
        raise SystemExit(0)
    raise SystemExit(main())
