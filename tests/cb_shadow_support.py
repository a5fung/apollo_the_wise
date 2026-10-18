"""Shared fixtures for the #702 P6 Consolidation Breakout shadow tests (`tests/test_cb_shadow*.py`).

NOT a test file (no `test_` prefix). Three things live here:

  * `build_market()` - a small deterministic market on MRNA's REAL calendar (the labelled fixture,
    `tests/fixtures/htf_labelled_bars.psv`: holiday-aware sessions, 2025-08-11 .. 2026-09-17): the real MRNA
    bars (the module's canary - a C0 watch night on 2026-09-16, a breakout day on 2026-09-17), synthetic SPY /
    QQQ, and filler tickers so the RS cross-section has a universe. Optional FUTURE sessions continue every
    ticker past 09-17 so the exit walks have something to walk.
  * `synth_minutes()` - a regular-hours minute path consistent with a daily bar (its high / low / close are the
    day's EXACTLY), in the shape `collector.get_alpaca_minute_bars_window` returns.
  * `FakeStore` - the shadow's db surface in memory, with the SAME write guards the SQL has, so the job can run
    end to end with no database. `tests/test_cb_shadow_pg.py` runs the same scenarios against a REAL Postgres
    and asserts the two agree.
"""
from __future__ import annotations

import datetime as dt
from collections import defaultdict
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np

ET = ZoneInfo("America/New_York")
FIXTURE = Path(__file__).resolve().parent / "fixtures" / "htf_labelled_bars.psv"
WATCH_NIGHT = dt.date(2026, 9, 16)          # MRNA passes C0 here
BREAK_DAY = dt.date(2026, 9, 17)            # and clears its pivots here


def mrna_rows() -> list:
    out = []
    for ln in FIXTURE.read_text().splitlines():
        f = ln.split("|")
        if f[0] == "MRNA":
            out.append((dt.date.fromisoformat(f[1]), *[float(x) for x in f[2:7]]))
    return out


def _weekdays_after(d: dt.date, n: int) -> list:
    out, cur = [], d
    while len(out) < n:
        cur += dt.timedelta(days=1)
        if cur.weekday() < 5:
            out.append(cur)
    return out


# MRNA after 09-17: a rally, then a roll-over through its SMA10 (so the trail arms fire inside the window).
MRNA_FUTURE_CLOSES = [160.0, 163.5, 167.0, 170.0, 172.0, 171.0, 168.0, 164.0, 160.0, 155.0, 150.0, 146.0,
                      143.0, 141.0, 140.0, 142.0, 141.5, 139.0, 138.0, 137.0, 136.0, 135.0, 134.0, 133.5]


class Market:
    def __init__(self, cal: list, bars: dict):
        self.cal = cal
        self.bars = bars                    # {ticker: [(date, o, h, l, c, v), ...]}
        self.sectypes = {t: "CS" for t in bars if t not in ("SPY", "QQQ")}
        self.sectypes.update({"SPY": "ETF", "QQQ": "ETF"})


def build_market(*, n_filler: int = 20, future: int = 0, seed: int = 702, clone_mrna: bool = False) -> Market:
    base = mrna_rows()
    cal = [r[0] for r in base]
    fut_dates = _weekdays_after(cal[-1], future) if future else []
    rng = np.random.default_rng(seed)
    allcal = cal + fut_dates
    n = len(allcal)

    def walk(start, drift, sigma, shares):
        c = start * np.exp(np.cumsum(rng.normal(drift, sigma, n)))
        o = np.concatenate(([start], c[:-1])) * (1 + rng.normal(0, 0.002, n))
        h = np.maximum(o, c) * (1 + rng.uniform(0.002, 0.012, n))
        l = np.minimum(o, c) * (1 - rng.uniform(0.002, 0.012, n))
        v = np.full(n, float(shares))
        return [(allcal[k], float(o[k]), float(h[k]), float(l[k]), float(c[k]), float(v[k])) for k in range(n)]

    bars = {"SPY": walk(450.0, 0.0006, 0.007, 8_000_000), "QQQ": walk(380.0, 0.0008, 0.009, 6_000_000)}
    for k in range(n_filler):
        # letters only: the universe's ticker pattern is ^[A-Z]{1,5}$
        bars["F" + chr(65 + k // 26) + chr(65 + k % 26)] = walk(
            20.0 + 3 * k, float(rng.normal(0.0, 0.0004)), 0.009, 3_000_000)

    mrna = list(base)
    prev_c = mrna[-1][4]
    for d, c in zip(fut_dates, MRNA_FUTURE_CLOSES[:future]):
        o = prev_c * 1.002
        h, l = max(o, c) * 1.012, min(o, c) * 0.988
        mrna.append((d, o, h, l, c, 9_000_000.0))
        prev_c = c
    bars["MRNA"] = mrna
    if clone_mrna:
        # MRNB: MRNA at half the price and double the volume - every gate is scale-invariant, so it is a SECOND
        # watch name with the same pole / pivots / breakout day (the dollar volume is unchanged)
        bars["MRNB"] = [(d, o / 2, h / 2, l / 2, c / 2, v * 2) for d, o, h, l, c, v in mrna]
    return Market(allcal, bars)


def synth_minutes(day: dt.date, o: float, h: float, l: float, c: float, *, low_minute: int = 3,
                  high_minute: int = 60, dip_after: int | None = None) -> list:
    """Alpaca-shaped minute bars (`ts` UTC-aware) for ONE session whose extremes are the daily bar's EXACTLY.
    Default path: open -> day low at `low_minute` -> day high at `high_minute` -> close (no break of the morning
    low after a fill). With `dip_after`: open -> a quick rise (an early fill) -> the DAY LOW at `dip_after`
    (the morning low broken after the fill) -> the day high at minute 200 -> close."""
    if dip_after is None:
        pts = [(0, o), (low_minute, l), (high_minute, h), (389, c)]
    else:
        pts = [(0, o), (6, o + 0.55 * (h - o)), (dip_after, l), (200, h), (389, c)]
    closes = np.interp(np.arange(390), [p[0] for p in pts], [p[1] for p in pts])
    out = []
    for m in range(390):
        op = o if m == 0 else float(closes[m - 1])
        cl = float(closes[m])
        et = dt.datetime(day.year, day.month, day.day, 9, 30, tzinfo=ET) + dt.timedelta(minutes=m)
        out.append({"ts": et.astimezone(dt.timezone.utc), "open": op, "high": max(op, cl), "low": min(op, cl),
                    "close": cl, "volume": 1000})
    return out


class FakeStore:
    """The shadow's db surface, in memory. Every guard the SQL has is reproduced (entry: only a `no_minutes`
    abstain may be overwritten; exit: a mature row is final), because the job's behaviour depends on them."""

    def __init__(self, market: Market):
        self.m = market
        self.watch: dict = {}              # (ticker, scan_date) -> row
        self.entry: dict = {}              # natural key -> row (with id)
        self.exit: dict = {}               # (entry_id, arm) -> row
        self.sic: dict = {}
        self.splits: list = []             # dicts: ticker, execution_date, split_from, split_to, adjustment_applied
        self.audit: list = []              # (event_type, summary, detail)
        self._next_id = 1
        self.calls = defaultdict(int)

    # ── reads of mi_daily_closes ───────────────────────────────────────────────────
    async def cb_get_calendar(self, upto, limit=400):
        self.calls["cal"] += 1
        return [d for d in self.m.cal if d <= upto][-limit:]

    async def cb_get_universe_bars(self, today, start, liq_start, *, min_price, prefilter_dollar_vol):
        out = []
        for t, rows in self.m.bars.items():
            todays = [r for r in rows if r[0] == today]
            if not todays or todays[0][4] < min_price:
                continue
            liq = sorted(r[4] * r[5] for r in rows if liq_start <= r[0] <= today)
            if not liq or float(np.median(liq)) < prefilter_dollar_vol:
                continue
            out.extend((t, *r) for r in rows if start <= r[0] <= today)
        return sorted(out, key=lambda r: (r[0], r[1]))

    async def cb_get_ticker_bars(self, tickers, start, end):
        out = []
        for t in tickers:
            out.extend((t, *r) for r in self.m.bars.get(t, []) if start <= r[0] <= end)
        return sorted(out, key=lambda r: (r[0], r[1]))

    async def cb_get_security_types(self, tickers):
        return {t: self.m.sectypes[t] for t in tickers if t in self.m.sectypes}

    async def get_unapplied_splits(self, since=None, upto=None):
        """`db.get_unapplied_splits` with an explicit `upto` (the shadow always passes one)."""
        return [dict(s) for s in sorted(self.splits, key=lambda s: (s["execution_date"], s["ticker"]))
                if not s["adjustment_applied"] and (since is None or s["execution_date"] >= since)
                and s["execution_date"] <= upto]

    async def cb_get_splits_after(self, tickers, after_date, upto_date):
        out: dict = {}
        for s in sorted(self.splits, key=lambda s: (s["ticker"], s["execution_date"])):
            if s["ticker"] in tickers and after_date < s["execution_date"] <= upto_date:
                out.setdefault(s["ticker"], []).append(dict(s))
        return out

    # ── the shadow tables ──────────────────────────────────────────────────────────
    async def cb_upsert_watch_rows(self, rows):
        for r in rows:
            self.watch[(r["ticker"], r["scan_date"])] = dict(r)
        return len(rows)

    async def cb_get_watch_rows(self, scan_date):
        return [dict(v) for k, v in sorted(self.watch.items()) if k[1] == scan_date]

    async def cb_get_watch_poles(self, tickers, upto):
        return sorted({(k[0], v["pole_date"]) for k, v in self.watch.items() if k[0] in tickers and k[1] <= upto})

    async def cb_upsert_entry_rows(self, rows):
        for r in rows:
            key = (r["ticker"], r["pole_date"], r["k"], r["entry_variant"], r["break_date"])
            old = self.entry.get(key)
            if old is None:
                self.entry[key] = dict(r, id=self._next_id)
                self._next_id += 1
            elif old["status"] == "abstain" and old["reason"] == "no_minutes":
                self.entry[key] = dict(r, id=old["id"])
        return len(rows)

    async def cb_get_entry_state(self, break_date):
        return [dict(ticker=v["ticker"], pole_date=v["pole_date"], k=v["k"], entry_variant=v["entry_variant"],
                     status=v["status"], reason=v["reason"]) for v in self.entry.values()
                if v["break_date"] == break_date]

    async def cb_get_candidate_history(self, tickers, before):
        seen: dict = {}
        for v in sorted(self.entry.values(), key=lambda v: (v["ticker"], v["pole_date"], v["k"], v["break_date"])):
            if v["ticker"] in tickers and v["break_date"] < before:
                seen.setdefault((v["ticker"], v["pole_date"], v["k"], v["break_date"]),
                                dict(ticker=v["ticker"], pole_date=v["pole_date"], k=v["k"],
                                     break_date=v["break_date"], cells=v["cells"]))
        return list(seen.values())

    def _open_entries(self, n_arms):
        mature = defaultdict(list)
        for (eid, arm), x in self.exit.items():
            if x["mature"]:
                mature[eid].append(arm)
        return [dict(v, mature_arms=sorted(mature[v["id"]]))
                for v in sorted(self.entry.values(), key=lambda v: (v["break_date"], v["ticker"], v["k"],
                                                                    v["entry_variant"]))
                if v["status"] == "filled" and len(mature[v["id"]]) < n_arms]

    async def cb_get_open_entries(self, n_arms, stale_before):
        return [v for v in self._open_entries(n_arms) if v["break_date"] >= stale_before]

    async def cb_count_stale_open_entries(self, n_arms, stale_before):
        return sum(1 for v in self._open_entries(n_arms) if v["break_date"] < stale_before)

    async def cb_upsert_exit_rows(self, rows):
        for r in rows:
            old = self.exit.get((r["entry_id"], r["arm"]))
            if old is None or not old["mature"]:
                self.exit[(r["entry_id"], r["arm"])] = dict(r)
        return len(rows)

    async def cb_get_sic(self, tickers):
        return {t: dict(v) for t, v in self.sic.items() if t in tickers}

    async def cb_upsert_sic_rows(self, rows):
        for r in rows:
            self.sic[r["ticker"]] = dict(r, fetched_at=dt.datetime.now(dt.timezone.utc))
        return len(rows)

    async def log_audit_event(self, event_type, summary, detail="", *, conn=None):
        self.audit.append((event_type, summary, detail))

    # ── wiring ─────────────────────────────────────────────────────────────────────
    NAMES = ("cb_get_calendar", "cb_get_universe_bars", "cb_get_ticker_bars", "cb_get_security_types",
             "get_unapplied_splits", "cb_get_splits_after", "cb_upsert_watch_rows", "cb_get_watch_rows",
             "cb_get_watch_poles", "cb_upsert_entry_rows", "cb_get_entry_state", "cb_get_candidate_history",
             "cb_get_open_entries", "cb_count_stale_open_entries", "cb_upsert_exit_rows", "cb_get_sic", "cb_upsert_sic_rows", "log_audit_event")

    def install(self, monkeypatch, shadow_module) -> None:
        for name in self.NAMES:
            monkeypatch.setattr(shadow_module, name, getattr(self, name))


class FakeCollector:
    """Stands in for `collector.get_alpaca_minute_bars_window` and `_polygon_get`."""

    def __init__(self, market: Market, *, minutes_for=None, outage_days=(), polygon=None):
        self.m = market
        self.minutes_for = minutes_for or {}        # {(ticker, date): list of alpaca bars}
        self.outage_days = set(outage_days)
        self.minute_calls: list = []
        self.polygon = polygon
        self.polygon_calls: list = []

    async def get_alpaca_minute_bars_window(self, tickers, start_et, end_et, timeout_s=6.0):
        day = start_et.date()
        self.minute_calls.append((day, tuple(tickers)))
        if day in self.outage_days:
            return {}
        out = {}
        for t in tickers:
            bars = self.minutes_for.get((t, day))
            if bars:
                out[t] = bars
        return out

    async def _polygon_get(self, path, params=None):
        self.polygon_calls.append(path)
        if self.polygon is None:
            raise RuntimeError("no polygon fake")
        return self.polygon(path)

    def install(self, monkeypatch) -> None:
        from agents.market_intelligence import collector
        monkeypatch.setattr(collector, "get_alpaca_minute_bars_window", self.get_alpaca_minute_bars_window)
        monkeypatch.setattr(collector, "_polygon_get", self._polygon_get)
