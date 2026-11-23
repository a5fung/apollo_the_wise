"""Liquidity read (#732) — the nightly LIQUIDITY block beside market breadth on the operator's dashboard.

DISPLAY ONLY ("context, not validated"). Nothing here feeds a trade, a grade, an alert, sizing, a safeguard or the
regime score (THE LINE; prereg §14). ``tests/test_732_liquidity_read.py`` derives every importer of this module and
fails the build if one appears outside the allowlist.

Rules (SSoT: ``docs/architecture/market_breadth_snapshot.md`` §Liquidity block; fixed and tested in
``docs/analysis/liquidity_composite_prereg_2026-11-22.md``, whose section numbers are cited below):
  - §12 leg vote = the TREND: tight when the 20-session average of X is above its 50-session average, easy when
    below, flat on an exact tie (1e-9 relative). X is oriented so that UP = TIGHTER. Fast dot = X vs its 20-day.
  - §3 / §6 publication lags and the §4.2 E1 freshness rule: a value enters a session only once it was published;
    a stale or missing source makes the leg "unavailable" (it votes 0 and stays in its group's mean, §4.3).
  - §4.3 composite: group score = mean of its legs' votes; S = the sum over the 6 groups; "N of 6 groups tight";
    the Draining state (enter S >= K/3 on 3 closes, leave S <= K/6 on 3 closes) is computed ONLY to drive the
    caution label (§14). No Easing / Neutral word and no bottom / top label leaves this module.
  - §13.1 turn rule: a new sign held 5 consecutive sessions, dated at the 5th; ties and gaps carry.

Shape: pure functions over frames (``compute`` / ``build_block``) and one I/O seam (``collect_inputs``: Alpaca daily
bars, FRED's keyless CSV). The Alpaca reader lives HERE, in the collector's own idiom and credentials, and not in
``collector.py``: that file is loaded by the execution service (``scripts/exec_loaded_modules.txt``), so editing it
would put a display-only panel behind a deploy of the service that holds the money path. The nightly export calls ``python -m
agents.market_intelligence.liquidity_read --splice`` with the breadth JSON on stdin (``scripts/
auto_export_snapshots.sh``); any failure exits non-zero and the breadth file ships without the block.
"""
from __future__ import annotations

import asyncio
import io
import json
import logging
import math
import os
import sys
from dataclasses import dataclass, field
from datetime import date, datetime, time as dtime
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
from numpy.lib.stride_tricks import sliding_window_view

logger = logging.getLogger(__name__)
_ET = ZoneInfo("America/New_York")

BLOCK_VERSION = 1
LABEL = "context, not validated"
CAUTION_TEXT = "Caution — liquidity draining"
# §14, his ruling: the one line of measured history that sits under the caution label. Fixed text (2016-24 run 2).
CAUTION_HISTORY = ("2016-24: a 10%+ small-cap drop within 3 months followed 33% of 730 draining days vs 13% of "
                   "1,207 other days — and a 10%+ rally followed 33% too; turns did not time lows.")

# A FIXED start, never a rolling window: the Draining state and the "first confirmed sign" of the turn rule depend on
# the path, so a start that moved each night could move past markers. Same start as the 11-22 reference read.
HISTORY_START = date(2025, 6, 2)
FRED_START = date(2025, 1, 1)          # FRED legs need values before the first session for the forward-fill

ADJ_TICKERS = ("JNK", "HYG", "UUP", "GLD", "SLV", "CPER", "IWM", "SPY", "QQQ", "ARKK")
RAW_TICKERS = ("JNK", "GLD", "SLV")    # the seed tiles are drawn on the raw price (what his own chart shows)
FRED_IDS = ("BAA10Y", "WALCL", "WTREGEN", "RRPONTSYD", "DFF", "DFII10", "DGS2", "BAMLH0A0HYM2")

# Publication lag per FRED series (prereg §3 "usable from" + §4.2 E1 freshness):
#   (lag in calendar days, strict = usable only from the NEXT session, freshness limit in calendar days)
PREREG_LAGS: dict[str, tuple[int, bool, int]] = {
    "BAA10Y": (0, True, 7), "DFF": (0, True, 7), "DFII10": (0, True, 7), "DGS2": (0, True, 7),
    "BAMLH0A0HYM2": (0, True, 7),
    "WALCL": (2, False, 14), "WTREGEN": (2, False, 14),     # the Wednesday level is usable on Friday
    "RRPONTSYD": (0, False, 7),                              # same day
}
# The 11-22 reference script (scripts/probes/_liquidity_1122/current_read.py) applied no lag and no freshness rule.
# This table exists ONLY so the reproduction test can run the production code the reference's way.
NO_LAGS: dict[str, tuple[int, bool, int]] = {k: (0, False, 10 ** 6) for k in PREREG_LAGS}
ETF_CARRY_SESSIONS = 3                 # §6.3: a missing ETF bar carries the last close at most 3 sessions

GROUPS: tuple[tuple[str, str], ...] = (
    ("credit", "Credit"), ("fed", "Fed and money"), ("rates", "Rates"),
    ("dollar", "Dollar"), ("metals", "Metals"), ("risk", "Risk appetite"),
)
# The 10 run-2 legs (frozen selection sha1 561b5e65…): id, plain name, group, what "tight" means.
LEGS: tuple[tuple[str, str, str, str], ...] = (
    ("C3", "Baa corporate spread", "credit", "spread widening"),
    ("F1", "Net liquidity", "fed", "net liquidity falling"),
    ("F2", "Fed funds rate", "fed", "funds rate rising"),
    ("R1", "10-year real yield", "rates", "real yield rising"),
    ("R2", "2-year yield", "rates", "2-year yield rising"),
    ("D1", "Dollar (UUP)", "dollar", "dollar rising"),
    ("M1", "Gold / silver", "metals", "gold beating silver"),
    ("M2", "Copper / gold", "metals", "copper lagging gold"),
    ("K1", "Small vs large (IWM / SPY)", "risk", "small caps lagging"),
    ("K5", "Speculative growth (ARKK / QQQ)", "risk", "speculative growth lagging"),
)
LEG_IDS = tuple(l[0] for l in LEGS)
K = len(GROUPS)
ENTER, EXIT = K / 3, K / 6
TURN_CONFIRM = 5
MARKER_SESSIONS = 126                  # composite turn markers shown: the last ~6 months
_WORD = {1: "tight", -1: "easy", 0: "flat"}


# ──────────────────────────────────────────────────────────────────────────── inputs
@dataclass
class Inputs:
    """What the I/O seam hands the pure code. A source that failed is simply absent (None / missing key)."""
    adj: pd.DataFrame | None                      # dividend-adjusted closes: index = session dates, columns = tickers
    raw: pd.DataFrame | None                      # raw closes (seed tiles)
    fred: dict[str, pd.Series] = field(default_factory=dict)   # series id -> values indexed by observation date
    errors: dict[str, str] = field(default_factory=dict)       # source -> why it is missing


# ──────────────────────────────────────────────────────────────────────────── pure maths
def _ma(a: np.ndarray, n: int) -> np.ndarray:
    """Simple average of the last n sessions by direct summation (no running-sum drift); NaN until n values exist."""
    out = np.full(len(a), np.nan)
    if len(a) >= n:
        out[n - 1:] = sliding_window_view(a, n).mean(axis=1)
    return out


def _side(p: np.ndarray, q: np.ndarray) -> np.ndarray:
    """+1 where p > q, -1 where p < q, 0 on a tie (within 1e-9 relative, prereg §4.1), NaN where either is missing."""
    with np.errstate(invalid="ignore"):
        tol = 1e-9 * np.maximum(1.0, np.maximum(np.abs(p), np.abs(q)))
        d = p - q
        out = np.where(d > tol, 1.0, np.where(d < -tol, -1.0, 0.0))
    out[np.isnan(p) | np.isnan(q)] = np.nan
    return out


def fred_on_grid(s: pd.Series, grid: pd.DatetimeIndex, lag_days: int, strict: bool, fresh_days: int
                 ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """The value usable at each session: the newest observation with obs_date + lag <= session (< when strict).
    Returns (value, fresh flag, observation date) per session. Fresh = that observation is at most fresh_days old."""
    s = s.dropna().sort_index()
    n = len(grid)
    val, fresh, obs = np.full(n, np.nan), np.zeros(n, bool), np.full(n, np.datetime64("NaT", "ns"))
    if s.empty:
        return val, fresh, obs
    od = s.index.values.astype("datetime64[ns]")
    avail = od + np.timedelta64(lag_days, "D")
    g = grid.values.astype("datetime64[ns]")
    pos = np.searchsorted(avail, g, side="left" if strict else "right") - 1
    ok = pos >= 0
    val[ok] = s.values[pos[ok]].astype(float)
    obs[ok] = od[pos[ok]]
    age = (g[ok] - od[pos[ok]]) / np.timedelta64(1, "D")
    fresh[ok] = age <= fresh_days
    return val, fresh, obs


def turns(sign: np.ndarray) -> tuple[list[tuple[int, int]], int | None]:
    """§13.1 the one turn rule. ``sign``: +1 / -1 per session, NaN or 0 = tie / missing (carries the previous sign).
    A turn = a sign different from the last CONFIRMED direction held 5 consecutive sessions, dated at the 5th; the
    first confirmed sign is a starting direction, not a turn. Returns ([(position, new sign)], confirmed sign now)."""
    out: list[tuple[int, int]] = []
    prev = math.nan
    conf: float | None = None
    run_sign, run = math.nan, 0
    for i, v in enumerate(sign):
        if not (v != v) and v != 0:
            prev = v
        if prev != prev:
            continue
        if prev == run_sign:
            run += 1
        else:
            run_sign, run = prev, 1
        if run == TURN_CONFIRM:
            if conf is None:
                conf = run_sign
            elif run_sign != conf:
                conf = run_sign
                out.append((i, int(run_sign)))
    return out, (None if conf is None else int(conf))


def _run_start(v: np.ndarray) -> tuple[int, int] | None:
    """The current run of a vote series (NaN sessions dropped, as the reference read does): (position of its first
    session, sessions AFTER that one). None when there is no value at all."""
    idx = np.flatnonzero(~np.isnan(v))
    if len(idx) == 0:
        return None
    vals = v[idx]
    j = len(vals) - 1
    while j > 0 and vals[j - 1] == vals[j]:
        j -= 1
    return int(idx[j]), int(len(vals) - 1 - j)


def draining_series(S: np.ndarray) -> np.ndarray:
    """§4.3 state machine on S (K = 6: enter 2, exit 1), exactly as run 2 judged it (r2_03): every condition reads
    the last three closes; from Draining the Easing entry is checked first, then the exit. Returns the state per
    session as 'D' / 'N' / 'E' ('' before the first state session). ONLY 'D' is ever shown, as the caution label."""
    st = np.full(len(S), "", dtype=object)
    cur, seen = "N", 0
    for i, v in enumerate(S):
        if v != v:
            continue
        seen += 1
        if seen >= 3 and not np.isnan(S[i - 2:i + 1]).any():
            w = S[i - 2:i + 1]
            dr, ea = bool((w >= ENTER).all()), bool((w <= -ENTER).all())
            xd, xe = bool((w <= EXIT).all()), bool((w >= -EXIT).all())
            if cur == "D":
                cur = "E" if ea else ("N" if xd else "D")
            elif cur == "E":
                cur = "D" if dr else ("N" if xe else "E")
            else:
                cur = "D" if dr else ("E" if ea else "N")
        st[i] = cur
    return st


@dataclass
class Computed:
    """Every series the block is cut from, on the session grid (kept whole so tests can read any date)."""
    grid: pd.DatetimeIndex
    X: pd.DataFrame            # leg value, up = tighter (NaN where the source is missing)
    fresh: pd.DataFrame        # bool: the session's value is fresh
    vote: pd.DataFrame         # +1 / -1 / 0, NaN = no vote (warm-up, stale or missing)
    fast: pd.DataFrame         # X vs its 20-day
    group: pd.DataFrame        # group score per session
    S: pd.Series               # composite score, NaN before the first state session
    n_tight: pd.Series         # groups with a score > 0
    state: pd.Series           # 'D' / 'N' / 'E' / '' — internal, drives the caution label only
    reasons: dict[str, str]    # leg id -> why it is unavailable NOW (absent = available)
    fred_last_obs: dict[str, date | None]
    parts: dict[str, np.ndarray]   # lagged FRED values on the grid (HY spread, net-liquidity parts)


def _closes(df: pd.DataFrame | None, ticker: str, grid: pd.DatetimeIndex) -> tuple[np.ndarray, np.ndarray]:
    """One ticker on the grid, the last close carried at most 3 sessions. Returns (value, fresh)."""
    if df is None or ticker not in df.columns:
        return np.full(len(grid), np.nan), np.zeros(len(grid), bool)
    s = pd.to_numeric(df[ticker], errors="coerce").reindex(grid).ffill(limit=ETF_CARRY_SESSIONS)
    return s.values.astype(float), s.notna().values


def session_grid(adj: pd.DataFrame | None) -> pd.DatetimeIndex:
    """The session grid = the dates SPY has a bar (any ticker's dates when SPY itself is missing)."""
    if adj is None or adj.empty:
        return pd.DatetimeIndex([])
    if "SPY" in adj.columns and adj["SPY"].notna().any():
        idx = adj.index[adj["SPY"].notna()]
    else:
        idx = adj.index[adj.notna().any(axis=1)]
    return pd.DatetimeIndex(sorted(set(idx)))


def compute(inp: Inputs, lags: dict[str, tuple[int, bool, int]] | None = None) -> Computed | None:
    """The whole read as series. None when there is no session grid at all (no Alpaca bars)."""
    lags = PREREG_LAGS if lags is None else lags
    grid = session_grid(inp.adj)
    if len(grid) == 0:
        return None
    n = len(grid)
    etf = {t: _closes(inp.adj, t, grid) for t in ADJ_TICKERS}
    fr: dict[str, tuple[np.ndarray, np.ndarray, np.ndarray]] = {}
    for sid in FRED_IDS:
        s = inp.fred.get(sid)
        fr[sid] = (fred_on_grid(s, grid, *lags[sid]) if s is not None
                   else (np.full(n, np.nan), np.zeros(n, bool), np.full(n, np.datetime64("NaT", "ns"))))

    def e(t): return etf[t][0]
    def ef(*ts): return np.logical_and.reduce([etf[t][1] for t in ts])
    def f(s): return fr[s][0]
    def ff(*ss): return np.logical_and.reduce([fr[s][1] for s in ss])

    with np.errstate(invalid="ignore", divide="ignore"):
        net_liq = f("WALCL") - f("WTREGEN") - f("RRPONTSYD") * 1000.0      # $ millions (RRP is in $ billions)
        X = {
            "C3": f("BAA10Y"), "F1": -net_liq, "F2": f("DFF"), "R1": f("DFII10"), "R2": f("DGS2"),
            "D1": e("UUP"), "M1": e("GLD") / e("SLV"), "M2": -(e("CPER") / e("GLD")),
            "K1": -(e("IWM") / e("SPY")), "K5": -(e("ARKK") / e("QQQ")),
        }
    FR = {
        "C3": ff("BAA10Y"), "F1": ff("WALCL", "WTREGEN", "RRPONTSYD"), "F2": ff("DFF"), "R1": ff("DFII10"),
        "R2": ff("DGS2"), "D1": ef("UUP"), "M1": ef("GLD", "SLV"), "M2": ef("CPER", "GLD"),
        "K1": ef("IWM", "SPY"), "K5": ef("ARKK", "QQQ"),
    }
    needs = {"C3": ["BAA10Y"], "F1": ["WALCL", "WTREGEN", "RRPONTSYD"], "F2": ["DFF"], "R1": ["DFII10"],
             "R2": ["DGS2"], "D1": ["UUP"], "M1": ["GLD", "SLV"], "M2": ["CPER", "GLD"], "K1": ["IWM", "SPY"],
             "K5": ["ARKK", "QQQ"]}
    vote, fast = {}, {}
    for k in LEG_IDS:
        x = np.where(FR[k], X[k], np.nan)             # a stale session has no value to vote with
        m20, m50 = _ma(X[k], 20), _ma(X[k], 50)
        v = _side(m20, m50)
        v[~FR[k]] = np.nan
        vote[k] = v
        fast[k] = _side(x, m20)
    V = pd.DataFrame(vote, index=grid)
    # the first state session = the first with any vote; before it S does not exist (§4.3)
    has = V.notna().any(axis=1).values
    first = int(np.flatnonzero(has)[0]) if has.any() else n
    Vz = V.fillna(0.0)                                 # no vote = 0, and it STAYS in its group's mean (§4.3 (2))
    G = pd.DataFrame({g: Vz[[l[0] for l in LEGS if l[2] == g]].mean(axis=1) for g, _ in GROUPS}, index=grid)
    S = G.sum(axis=1)
    nt = (G > 0).sum(axis=1).astype(float)
    S.iloc[:first] = np.nan
    nt.iloc[:first] = np.nan
    G.iloc[:first] = np.nan
    state = pd.Series(draining_series(S.values), index=grid)

    reasons: dict[str, str] = {}
    for k in LEG_IDS:
        if FR[k][-1] and not np.isnan(vote[k][-1]):
            continue
        missing = [s for s in needs[k] if (s in FRED_IDS and inp.fred.get(s) is None)
                   or (s in ADJ_TICKERS and (inp.adj is None or s not in inp.adj.columns))]
        if missing:
            reasons[k] = "source failed: " + ", ".join(missing)
        elif not FR[k][-1]:
            reasons[k] = "stale: no fresh value for " + ", ".join(needs[k])
        else:
            reasons[k] = "not enough history for a 50-day average"
    last_obs = {}
    for sid in FRED_IDS:
        o = fr[sid][2][-1]
        last_obs[sid] = None if np.isnat(o) else pd.Timestamp(o).date()
    return Computed(grid=grid, X=pd.DataFrame(X, index=grid), fresh=pd.DataFrame(FR, index=grid), vote=V,
                    fast=pd.DataFrame(fast, index=grid), group=G, S=S, n_tight=nt, state=state, reasons=reasons,
                    fred_last_obs=last_obs,
                    parts={"HY": fr["BAMLH0A0HYM2"][0], "HY_fresh": fr["BAMLH0A0HYM2"][1], "net_liq": net_liq})


# ──────────────────────────────────────────────────────────────────────────── the block
def _d(grid: pd.DatetimeIndex, pos: int) -> str:
    return grid[pos].date().isoformat()


def _r(v, nd: int):
    """A JSON-safe rounded number (None for NaN / inf / missing)."""
    try:
        v = float(v)
    except (TypeError, ValueError):
        return None
    return round(v, nd) if math.isfinite(v) else None


def _seed(series: np.ndarray, nd: int, slope: bool) -> dict | None:
    """A seed tile: latest, its 20- and 50-session averages, the 1-month change (21 sessions back), and for JNK the
    20-day's slope per week (its change over 5 sessions)."""
    if len(series) == 0 or np.isnan(series[-1]):
        return None
    m20, m50 = _ma(series, 20), _ma(series, 50)
    out = {"latest": _r(series[-1], nd), "ma20": _r(m20[-1], nd), "ma50": _r(m50[-1], nd),
           "vs_ma20": _WORD.get(int(_side(series[-1:], m20[-1:])[0])) if not np.isnan(m20[-1]) else None,
           "vs_ma50": _WORD.get(int(_side(series[-1:], m50[-1:])[0])) if not np.isnan(m50[-1]) else None,
           "ma20_vs_ma50": (_WORD.get(int(_side(m20[-1:], m50[-1:])[0]))
                            if not (np.isnan(m20[-1]) or np.isnan(m50[-1])) else None),
           "chg_1m_pct": (_r(100 * (series[-1] / series[-22] - 1), 1) if len(series) >= 22 else None)}
    # the tile's words are about the PRICE (above / below), not tight / easy
    for key in ("vs_ma20", "vs_ma50", "ma20_vs_ma50"):
        out[key] = {"tight": "above", "easy": "below", "flat": "at"}.get(out[key])
    if slope:
        out["ma20_slope_wk"] = _r(m20[-1] - m20[-6], 3) if len(series) >= 25 else None
    return out


def unavailable_block(reason: str, generated_at: datetime | None = None) -> dict:
    return {"version": BLOCK_VERSION, "label": LABEL, "status": "unavailable", "reason": reason,
            "generated_at": _stamp(generated_at)}


def _stamp(now_et: datetime | None) -> str | None:
    return None if now_et is None else now_et.astimezone(_ET).strftime("%Y-%m-%dT%H:%M:%S ET")


def build_block(inp: Inputs, generated_at: datetime | None = None,
                lags: dict[str, tuple[int, bool, int]] | None = None) -> dict:
    """The JSON block the dashboard renders. Never raises on a missing source: that leg reads "unavailable"."""
    c = compute(inp, lags)
    if c is None:
        return unavailable_block("no daily bars: " + (inp.errors.get("alpaca_adj") or "Alpaca returned nothing"),
                                 generated_at)
    grid, n = c.grid, len(c.grid)
    legs = []
    for lid, name, group, tight_when in LEGS:
        row = {"id": lid, "name": name, "group": group, "tight_when": tight_when}
        if lid in c.reasons:
            row.update(status="unavailable", reason=c.reasons[lid])
            legs.append(row)
            continue
        v = c.vote[lid].values
        rs = _run_start(v)
        tl, _conf = turns(v)
        fd = c.fast[lid].values[-1]
        row.update(status="ok", trend=_WORD[int(v[-1])], trend_since=_d(grid, rs[0]), trend_sessions=rs[1],
                   fast=_WORD[int(fd)] if not np.isnan(fd) else None,
                   turn=({"date": _d(grid, tl[-1][0]), "to": _WORD[tl[-1][1]], "sessions": n - 1 - tl[-1][0]}
                         if tl else None))
        legs.append(row)

    out: dict = {"version": BLOCK_VERSION, "label": LABEL, "status": "ok" if not c.reasons else "partial",
                 "as_of": _d(grid, n - 1), "generated_at": _stamp(generated_at),
                 "history_start": _d(grid, 0), "sessions": n,
                 "unavailable": sorted(c.reasons), "legs": legs}
    if inp.errors:
        out["errors"] = dict(sorted(inp.errors.items()))

    S = c.S.values
    if np.isnan(S[-1]):
        out.update(groups=None, groups_tight=None, score=None, composite_turns=[], caution=None,
                   composite_note="not enough history for the composite yet")
    else:
        nt = c.n_tight.values
        out["groups"] = [{"key": g, "name": nm, "score": _r(c.group[g].values[-1], 2),
                          "tight": bool(c.group[g].values[-1] > 0)} for g, nm in GROUPS]
        prev = nt[-21] if n >= 21 and not np.isnan(nt[-21]) else None
        out["groups_tight"] = {"n": int(nt[-1]), "of": K, "n_20d_ago": None if prev is None else int(prev),
                               "chg_20d": None if prev is None else int(nt[-1] - prev)}
        out["score"] = _r(S[-1], 2)
        # composite trend + turn markers: the same 20-day vs 50-day read, on S (§13.1 primary)
        sg = _side(_ma(S, 20), _ma(S, 50))
        tl, _conf = turns(sg)
        lo = n - MARKER_SESSIONS
        out["composite_turns"] = [{"date": _d(grid, p), "to": "tightening" if s > 0 else "easing",
                                   "sessions": n - 1 - p} for p, s in tl if p >= lo]
        rs = _run_start(sg)
        out["composite_trend"] = (None if rs is None or np.isnan(sg[-1]) else
                                  {"direction": {1: "tightening", -1: "easing", 0: "flat"}[int(sg[-1])],
                                   "since": _d(grid, rs[0]), "sessions": rs[1]})
        # §14: the state is computed ONLY to switch the caution label; the state word itself never leaves here
        st = c.state.values
        if st[-1] == "D":
            j = n - 1
            while j > 0 and st[j - 1] == "D":
                j -= 1
            out["caution"] = {"on": True, "text": CAUTION_TEXT, "since": _d(grid, j), "sessions": n - 1 - j,
                              "history": CAUTION_HISTORY}
        else:
            out["caution"] = {"on": False}

    def raw(t):
        return _closes(inp.raw, t, grid)[0]
    jnk, gld, slv = raw("JNK"), raw("GLD"), raw("SLV")
    with np.errstate(invalid="ignore", divide="ignore"):
        gs = gld / slv
    out["seeds"] = {"jnk": _seed(jnk, 2, slope=True), "gold_silver": _seed(gs, 2, slope=False)}

    hy, hyf = c.parts["HY"], c.parts["HY_fresh"]
    if hyf[-1] and not np.isnan(hy[-1]):
        ago = hy[-22] if n >= 22 else np.nan
        out["hy_spread"] = {"latest": _r(hy[-1], 2), "obs_date": (c.fred_last_obs["BAMLH0A0HYM2"].isoformat()
                                                                  if c.fred_last_obs["BAMLH0A0HYM2"] else None),
                            "month_ago": _r(ago, 2), "chg_1m": _r(hy[-1] - ago, 2),
                            "three_months_ago": _r(hy[-64], 2) if n >= 64 else None}
    else:
        out["hy_spread"] = None
    nl = c.parts["net_liq"]
    out["net_liquidity_tn"] = (None if "F1" in c.reasons else
                               {"latest": _r(nl[-1] / 1e6, 2),
                                "three_months_ago": _r(nl[-64] / 1e6, 2) if n >= 64 else None})
    out["definitions"] = DEFINITIONS
    return out


DEFINITIONS = {
    "label": "Context, not validated: display only. It feeds no entry, size, safeguard or regime score.",
    "trend": "Each indicator is oriented so UP = tighter. Trend = its 20-session average vs its 50-session average "
             "(tight above, easy below).",
    "fast": "Fast dot = the indicator vs its own 20-session average (the early warning; it never votes).",
    "since": "trend_since / trend_sessions = when the trend last changed side and the sessions since. turn = the "
             "last change that then held 5 sessions in a row, dated at the 5th.",
    "groups": "A group is tight when the average of its indicators' trend votes is above zero. N of 6 = groups tight "
              "now; the change is against 20 sessions ago.",
    "composite_turns": "Composite turn = the 20-session average of the group-score sum crossing its 50-session "
                       "average and holding 5 sessions. Tested 2016-24: turns did not time market lows or highs.",
    "caution": "Shown while the group-score sum has been 2 or more on 3 closes in a row, until it is 1 or less on 3 "
               "closes in a row. " + CAUTION_HISTORY,
    "lags": "Fed and Treasury series enter a session only once published (most the next session; the Fed balance "
            "sheet's Wednesday level on Friday). A stale or failed source reads unavailable and votes 0.",
    "seeds": "JNK and gold/silver tiles use raw prices (as charted); the indicator rows use dividend-adjusted closes.",
    "hy_spread": "ICE BofA US High Yield spread (FRED BAMLH0A0HYM2), percent; change against 21 sessions earlier.",
}


# ──────────────────────────────────────────────────────────────────────────── the I/O seam (network lives ONLY here)
def parse_fred_csv(text: str) -> pd.Series:
    """FRED's fredgraph.csv (observation_date,<ID>; '.' = no value) -> values indexed by observation date."""
    df = pd.read_csv(io.StringIO(text))
    if df.shape[1] < 2 or df.empty:
        raise ValueError("FRED csv has no data column")
    idx = pd.to_datetime(df.iloc[:, 0], errors="coerce")
    s = pd.Series(pd.to_numeric(df.iloc[:, 1], errors="coerce").values, index=idx)
    s = s[s.index.notna()].dropna()
    if s.empty:
        raise ValueError("FRED csv holds no numeric observation")
    return s.sort_index()


def closes_frame(rows: dict[str, list[tuple[date, float]]]) -> pd.DataFrame | None:
    """{ticker: [(session date, close)]} -> a date x ticker frame (None when empty)."""
    cols = {t: pd.Series({pd.Timestamp(d): float(c) for d, c in r}) for t, r in rows.items() if r}
    return pd.DataFrame(cols).sort_index() if cols else None


def drop_unfinished_session(df: pd.DataFrame | None, now_et: datetime) -> pd.DataFrame | None:
    """Today's bar is a close only after the session ends; before 16:15 ET it is dropped (a manual daytime run)."""
    if df is None or df.empty:
        return df
    if now_et.timetz().replace(tzinfo=None) < dtime(16, 15):
        df = df[df.index < pd.Timestamp(now_et.date())]
    return df


async def fetch_daily_closes(tickers: list[str], start_et: datetime, end_et: datetime,
                             adjustment: str = "all", timeout_s: float = 45.0
                             ) -> dict[str, list[tuple[date, float]]]:
    """DAILY closes for a small ETF set from Alpaca's consolidated (SIP) tape; ``adjustment`` = "all" (split +
    dividend adjusted: the ratio legs) or "raw" (the price as charted: the seed tiles). Returns
    ``{ticker: [(session date ET, close), ...]}`` oldest -> newest, missing symbols omitted. NEVER raises; ``{}`` on
    any failure — the caller marks those legs unavailable.

    The feed is SIP on purpose, not ALPACA_DATA_FEED: a daily close has to be the consolidated close (an IEX-only
    bar closes at IEX's last trade). Same paper-credential / run_in_executor idiom as the collector's Alpaca readers."""
    if not tickers:
        return {}
    try:
        from alpaca.data.enums import Adjustment, DataFeed
        from alpaca.data.historical import StockHistoricalDataClient
        from alpaca.data.requests import StockBarsRequest
        from alpaca.data.timeframe import TimeFrame
    except ImportError as e:
        logger.warning(f"alpaca-py daily-bars import failed: {e}")
        return {}
    api_key = os.environ.get("ALPACA_PAPER_API_KEY") or os.environ.get("ALPACA_API_KEY", "")
    secret = os.environ.get("ALPACA_PAPER_SECRET_KEY") or os.environ.get("ALPACA_SECRET_KEY", "")
    if not api_key or not secret:
        logger.warning("Alpaca credentials not set; skipping daily closes")
        return {}
    try:
        adj = {"all": Adjustment.ALL, "raw": Adjustment.RAW}[adjustment]
        client = StockHistoricalDataClient(api_key=api_key, secret_key=secret)
        req = StockBarsRequest(symbol_or_symbols=list(tickers), timeframe=TimeFrame.Day,
                               start=start_et, end=end_et, feed=DataFeed.SIP, adjustment=adj)
        loop = asyncio.get_running_loop()
        bars = await asyncio.wait_for(loop.run_in_executor(None, lambda r=req: client.get_stock_bars(r)),
                                      timeout=timeout_s)
    except Exception as e:  # noqa: BLE001 - display-only read; the legs degrade to "unavailable", never to a value
        logger.warning(f"Alpaca daily closes failed ({len(tickers)} syms, {adjustment}): {e}")
        return {}
    out: dict[str, list[tuple[date, float]]] = {}
    for sym, blist in (getattr(bars, "data", None) or {}).items():
        series: dict[date, float] = {}
        for b in blist or []:
            try:
                series[b.timestamp.astimezone(_ET).date()] = float(b.close)
            except (TypeError, ValueError, AttributeError):
                continue
        if series:
            out[sym] = sorted(series.items())
    return out


async def _fetch_fred(client, sid: str, start: date, end: date) -> pd.Series:
    r = await client.get("https://fred.stlouisfed.org/graph/fredgraph.csv",
                         params={"id": sid, "cosd": start.isoformat(), "coed": end.isoformat()})
    r.raise_for_status()
    return parse_fred_csv(r.text)


async def collect_inputs(now_et: datetime | None = None) -> Inputs:
    """Fetch everything. Each source fails on its own: a failure is recorded in ``errors`` and that source is absent."""
    import httpx

    now_et = (now_et or datetime.now(_ET)).astimezone(_ET)
    start = datetime.combine(HISTORY_START, dtime(0, 0), tzinfo=_ET)
    errors: dict[str, str] = {}

    async def bars(tickers, adjustment, key):
        try:
            rows = await fetch_daily_closes(list(tickers), start, now_et, adjustment=adjustment)
        except Exception as exc:        # noqa: BLE001 - the reader does not raise; belt and braces
            rows = {}
            errors[key] = f"{type(exc).__name__}: {exc}"
            logger.warning(f"liquidity_read: daily closes ({adjustment}) failed: {errors[key]}")
        df = drop_unfinished_session(closes_frame(rows), now_et)
        if df is None or df.empty:
            errors.setdefault(key, "Alpaca returned no daily bars")
            return None
        return df

    adj, raw = await asyncio.gather(bars(ADJ_TICKERS, "all", "alpaca_adj"), bars(RAW_TICKERS, "raw", "alpaca_raw"))
    fred: dict[str, pd.Series] = {}
    async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
        res = await asyncio.gather(*(_fetch_fred(client, sid, FRED_START, now_et.date()) for sid in FRED_IDS),
                                   return_exceptions=True)
    for sid, r in zip(FRED_IDS, res):
        if isinstance(r, BaseException):
            errors[f"fred_{sid}"] = f"{type(r).__name__}: {r}"[:200]
        else:
            fred[sid] = r
    return Inputs(adj=adj, raw=raw, fred=fred, errors=errors)


# ──────────────────────────────────────────────────────────────────────────── the splice (what the export calls)
SPLICE_KEY = "liquidity"


def splice(breadth_text: str, block: dict) -> str:
    """Add ``"liquidity": <block>`` as the LAST key of the breadth JSON object, textually, so every existing byte
    of the export is unchanged. Raises ValueError unless the input is one JSON object without the key and the
    result parses back to that object plus the key."""
    body = breadth_text.rstrip()
    base = json.loads(body)
    if not isinstance(base, dict) or not base:
        raise ValueError("breadth export is not a non-empty JSON object")
    if SPLICE_KEY in base:
        raise ValueError("breadth export already carries a liquidity key")
    if not body.endswith("}"):
        raise ValueError("breadth export does not end with '}'")
    out = body[:-1].rstrip() + "," + json.dumps(SPLICE_KEY) + ":" + json.dumps(
        block, ensure_ascii=False, allow_nan=False, separators=(",", ":")) + "}\n"
    back = json.loads(out)
    if {k: v for k, v in back.items() if k != SPLICE_KEY} != base or back.get(SPLICE_KEY) != block:
        raise ValueError("spliced JSON does not round-trip")
    return out


RUN_TIMEOUT_S = 150.0


def run_cli(argv: list[str], stdin_text: str | None, collect=None) -> tuple[int, str, str]:
    """The command without the process exit: (exit code, stdout text, stderr text). ``--splice``: the breadth JSON
    (``stdin_text``) -> the same JSON plus the liquidity block. Without it: the block alone. ANY failure = a non-zero
    code and EMPTY stdout; the caller then ships the breadth file as it is."""
    collect = collect or collect_inputs
    try:
        text = stdin_text if "--splice" in argv else None
        if "--splice" in argv:
            if not (text or "").strip():
                raise ValueError("--splice needs the breadth JSON on stdin")
            json.loads(text)            # refuse a broken breadth file before spending a fetch on it
        now_et = datetime.now(_ET)

        async def run():
            return await asyncio.wait_for(collect(now_et), RUN_TIMEOUT_S)
        block = build_block(asyncio.run(run()), generated_at=now_et)
        out = (splice(text, block) if text is not None
               else json.dumps(block, ensure_ascii=False, allow_nan=False) + "\n")
        return 0, out, ""
    except BaseException as exc:        # noqa: BLE001 - every failure is the same outcome: no block tonight
        logger.warning(f"liquidity_read: no block tonight ({type(exc).__name__}: {exc})")
        return 1, "", f"liquidity_read: FAILED ({type(exc).__name__}: {exc})\n"


def main(argv: list[str] | None = None) -> None:
    """Process entry. A fetch that outlives RUN_TIMEOUT_S ends the run, and the exit is ``os._exit`` because alpaca-py
    sets no HTTP timeout: a stuck fetch thread would otherwise keep the interpreter alive past the answer."""
    argv = sys.argv[1:] if argv is None else argv
    logging.basicConfig(level=logging.WARNING, stream=sys.stderr)
    code, out, err = run_cli(argv, sys.stdin.read() if "--splice" in argv else None)
    sys.stdout.write(out)
    sys.stdout.flush()
    sys.stderr.write(err)
    sys.stderr.flush()
    os._exit(code)


if __name__ == "__main__":
    main()
