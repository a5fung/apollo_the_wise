"""#702 P4b extension - C0 base detection on ALPACA split-adjusted daily bars for talks dated before 2022-03-28 ($0: numpy only).

Mirrors `runner.scan_ticker`'s per-night loop (the runner's own function takes a split list; here the raw/split factor is
measured per bar as raw close / split close) and calls the SAME frozen module functions: `cb.universe_ok`,
`cb.contiguous_window_mask`, `cb.explain_watch`. Read-only on `agents/market_intelligence/consolidation_breakout.py`.

Per night, in the runner's order:  test symbol -> universe (type, ticker regex, raw close >= $5, 20-session median dollar volume
>= $10M, >= 130 bars) -> identity break inside the 130 bars -> 130 CONSECUTIVE SPY sessions -> explain_watch (C0 gates).
RS / group / phase are NOT computed: every row is "C0-only, Alpaca bars". Only the nights a talk needs are evaluated
(28 calendar days up to the talk, +10 after), plus a forward walk from the last matching night so the first breakout of that
base can be read (existence + first entry day only; no trade outcome).

ELIGIBILITY is reported apart from "no base": a talk is ELIGIBLE when at least one night in its window passed the universe,
the break rule and the 130-consecutive-session rule; otherwise `elig_reason` (priority) is
  no_alpaca_series | no_bar_at_talk | identity_break | history_lt130 | sectype | price_lt5 | dollar_vol_lt10m | test_symbol
"""
import datetime as dt
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(REPO, "scripts", "probes", "_cb_backtest"))
sys.path.insert(0, REPO)

import pandas as pd  # noqa: E402

import ext_bars  # noqa: E402
import match_bars  # noqa: E402
import runner  # noqa: E402  (read-only import: load_small / load_sic)

cb = runner.cb
DATA = "/Users/alvinfung/apollo_data/cb702"
WIN_DAYS = match_bars.WIN_DAYS
AFTER_DAYS = 10
FWD_MAX = 60
KS = ("k5", "k10", "full", "tl")
FEAT = match_bars.FEAT
ALP_START = dt.date(2016, 1, 1)             # match_one's gate: every Alpaca-era talk is assessed (eligibility is reported apart)
REASON_ORDER = ["no_alpaca_series", "no_bar_at_talk", "identity_break", "history_lt130", "test_symbol", "sectype", "price_lt5", "dollar_vol_lt10m"]


class Series:
    """One spoken ticker's Alpaca bars, prepared once; nights evaluated lazily and cached."""

    def __init__(self, ev, spoken, sym):
        self.spoken, self.sym = spoken, sym
        a = ev.a
        b = ext_bars.sym_bars(a, ev.idx[sym])
        d = b["d"]
        ci = np.searchsorted(ev.cal, d)
        ok = (ci < len(ev.cal)) & (ev.cal[np.minimum(ci, len(ev.cal) - 1)] == d)
        ev.off_calendar += int((~ok).sum())
        d, ci = d[ok], ci[ok].astype(np.int32)
        self.d, self.cidx = d, ci
        self.dates = [dt.date.fromordinal(int(x)) for x in d]
        self.bars = cb.daily_bars_from_arrays(self.dates, b["o"][ok], b["h"][ok], b["l"][ok], b["c"][ok], b["v"][ok])
        self.fac = b["c_raw"][ok] / b["c"][ok]
        self.contig = cb.contiguous_window_mask(ci, cb.MIN_HISTORY)
        self.brk = np.array(sorted(ev.breaks.get(sym, [])), dtype=np.int64)
        self.sectype = runner.resolve_sectype(spoken, ev.mi_types, ev.sic_types)
        self.test = cb.is_test_symbol(spoken)
        self.cache = {}

    def break_in(self, i):
        if not len(self.brk) or i < cb.MIN_HISTORY - 1:
            return False
        return bool(np.searchsorted(self.brk, self.d[i], "right") - np.searchsorted(self.brk, self.d[i - cb.MIN_HISTORY + 1], "right") > 0)

    def universe_reason(self, i):
        """None when `cb.universe_ok` passes, else the first failing test (decomposed; asserted equal to universe_ok)."""
        bars = self.bars
        if i < cb.MIN_HISTORY - 1:
            why = "history_lt130"
        elif not cb.UNIVERSE_TICKER_RE.fullmatch(self.spoken):
            why = "regex"
        elif self.sectype and self.sectype not in cb.UNIVERSE_SECURITY_TYPES:
            why = "sectype"
        elif not float(bars.c[i]) * float(self.fac[i]) >= cb.MIN_PRICE:
            why = "price_lt5"
        elif not cb._dollar_vol_median(bars, i) >= cb.MIN_DOLLAR_VOL:
            why = "dollar_vol_lt10m"
        else:
            why = None
        ok = cb.universe_ok(bars, i, raw_factor=float(self.fac[i]), ticker=self.spoken, security_type=self.sectype)
        assert ok == (why is None), (self.spoken, i, why, ok)
        return why

    def night(self, i):
        """(status, features): status in pass | c0:<gate> | test_symbol | <universe reason> | identity_break | history_lt130."""
        if i in self.cache:
            return self.cache[i]
        if self.test:
            r = ("test_symbol", None)
        else:
            why = self.universe_reason(i)
            if why:
                r = (why, None)
            elif self.break_in(i):
                r = ("identity_break", None)
            elif not self.contig[i]:
                r = ("history_lt130", None)                        # fewer than 130 CONSECUTIVE sessions (a hole <= 30 sessions)
            else:
                feat, gate = cb.explain_watch(self.bars, i)
                if feat is None:
                    r = ("c0:" + gate, None)
                else:
                    assert feat["watch_date"] == self.dates[i].isoformat()
                    feat["base_id"] = f"{self.spoken}|{feat['pole_date']}"
                    r = ("pass", feat)
        self.cache[i] = r
        return r


class Evaluator:
    def __init__(self, ext):
        self.ext = ext
        self.a = ext_bars.load(ext)
        self.idx = ext_bars.sym_index(self.a)
        self.cal = ext_bars._calendar(self.a)
        self.off_calendar = 0
        g = pd.read_csv(os.path.join(ext, "symbol_guard.tsv"), sep="\t", keep_default_na=False)
        self.guard = {r["symbol"]: r for r in g.to_dict("records")}
        self.breaks = {}
        for s, r in self.guard.items():
            if r["breaks"]:
                self.breaks[s] = [dt.date.fromisoformat(x.split(":")[0]).toordinal() for x in r["breaks"].split(";")]
        self.ren = {}
        p = os.path.join(ext, "rename_map.tsv")
        for ln in open(p).read().splitlines()[1:]:
            old, new, _ = ln.split("\t")
            if old not in self.idx:
                self.ren[old] = new
        self.mi_types, _ = runner.load_small(runner.Path(DATA) / "small_pulls.psv")
        _, self.sic_types = runner.load_sic(runner.Path(DATA) / "cb702_sic.psv")
        self._series = {}

    def symbol_of(self, spoken):
        if spoken in self.idx:
            return spoken
        return self.ren.get(spoken)

    def series(self, spoken):
        if spoken not in self._series:
            sym = self.symbol_of(spoken)
            self._series[spoken] = Series(self, spoken, sym) if sym else None
        return self._series[spoken]

    # ------------------------------------------------------------------------------------------------------
    def eval_row(self, spoken, ref):
        """-> dict of match columns (the `match_bars.match_one` schema) + eligibility columns, for one talk date `ref` (a date)."""
        S = self.series(spoken)
        sym = self.symbol_of(spoken)
        g = self.guard.get(sym or "", {})
        base = dict(bars_symbol=sym or "", sym_flags=g.get("flags", ""), n_breaks=len(self.breaks.get(sym or "", [])),
                    literal_flag=int(bool(g) and (g.get("n_holes", 0) > 0 or g.get("n_move70_nosplit", 0) > 0 or "overlap" in g.get("flags", ""))),
                    bars_source="alpaca_split_c0only")
        r = ref.toordinal()
        if S is None:
            m = match_bars.match_one(None, {}, ref, ALP_START, "alpaca_c0")
            m.update(base, elig=0, elig_reason="no_alpaca_series", elig_nights=0, n_nights_eval=0)
            return m
        d = S.d
        lo_i = int(np.searchsorted(d, r - WIN_DAYS, "left"))
        hi_i = int(np.searchsorted(d, r + AFTER_DAYS, "right"))
        i_ref = int(np.searchsorted(d, r, "right")) - 1
        for i in range(lo_i, hi_i):
            S.night(i)
        # the nights up to the talk
        win = [i for i in range(lo_i, hi_i) if d[i] <= r]
        statuses = [S.night(i)[0] for i in win]
        elig_nights = sum(1 for s in statuses if s == "pass" or s.startswith("c0:"))
        # forward walk from the last matching night: the first breakout of that base. EVERY night in (last, last + FWD_MAX] is evaluated
        # (a base can lapse and re-emerge, exactly as in the runner's candidates) and only those nights feed the breakout test, so the
        # answer does not depend on which other talks of the same ticker happened to be evaluated first.
        passes = [i for i in win if S.night(i)[0] == "pass"]
        fwd_hi = None
        if passes:
            fwd_hi = min(len(d) - 1, passes[-1] + FWD_MAX)
            for j in range(passes[-1] + 1, fwd_hi + 1):
                S.night(j)
        # watch frame + candidate dict for match_one
        rows, cg_rows = [], {}
        for i, (st, ft) in sorted(S.cache.items()):
            if st != "pass":
                continue
            row = {"ticker": spoken, "wd": int(d[i]), "base_id": ft["base_id"]}
            for f in FEAT:
                row[f] = ft.get(f) if f != "split" else ""
            rows.append(row)
            if fwd_hi is not None and i <= fwd_hi and i + 1 < len(d) and int(S.cidx[i + 1]) == int(S.cidx[i]) + 1:
                for k in KS:
                    if cb.breaks_out(float(S.bars.h[i + 1]), ft[f"pivot_{k}"]):
                        cg_rows.setdefault(ft["base_id"], []).append((int(d[i]), int(d[i + 1]), k))
        wg = pd.DataFrame(rows, columns=["ticker", "wd", "base_id"] + FEAT) if rows else pd.DataFrame(columns=["ticker", "wd", "base_id"] + FEAT)
        cg = {b: pd.DataFrame(v, columns=["dd", "ed", "K"]).sort_values("dd") for b, v in cg_rows.items()}
        m = match_bars.match_one(wg, cg, ref, ALP_START, "alpaca_c0")
        # eligibility
        if elig_nights:
            reason = ""
        elif i_ref < 0 or r - int(d[i_ref]) > 7:
            reason = "no_bar_at_talk"
        else:
            reason = S.night(i_ref)[0]
            reason = {"regex": "ticker_format"}.get(reason, reason)
            if reason.startswith("c0:") or reason == "pass":
                reason = ""
        m.update(base, elig=int(elig_nights > 0), elig_reason=reason, elig_nights=elig_nights, n_nights_eval=len(win))
        return m


def stream_dates(df, col):
    return [dt.date.fromisoformat(x) for x in df[col]]
