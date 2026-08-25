#!/usr/bin/env python3
"""STRUCTURE-READ BACKTEST — STAGE 1: compute the read for every name-day. ($0, READ-ONLY.)

MEASUREMENT ONLY. Nothing is wired, no rule/threshold/toggle/trade-state is touched, and
nothing here is a recommendation (THE LINE). The measure is
`scripts/probes/_structure_read_v2.py` used UNCHANGED — not one parameter is adjusted.

Inputs, all captured ONCE from prod (read-only) and re-read, never re-pulled:
  _srbt_bars.psv.gz   mi_daily_closes OHLCV for every scan-log ticker + the 26 fixture names
  _srbt_scanlog.psv   mi_ep_scan_log deduped to one row per (scan_date, ticker), last tick
  _structax_bars_polygon.psv  the 08-25 replay's Polygon capture (bar-source fidelity only)
  _structax_scanlog.psv       the 08-25 replay's own reject arm (fidelity only)

Output (written ONCE, then read by _srbt_analyze.py): _srbt_reads.psv
"""
from __future__ import annotations

import gzip
import statistics as st
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))
sys.path.insert(0, str(HERE))

import _structure_read_v2 as V2  # noqa: E402
from tests.fixtures.must_not_miss_eps import MUST_NOT_MISS  # noqa: E402


def _d(s: str) -> date:
    y, m, dd = s.split("-")
    return date(int(y), int(m), int(dd))


def _f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


# ── bars ──────────────────────────────────────────────────────────────────────────────
def load_bars_prod() -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = defaultdict(list)
    with gzip.open(HERE / "_srbt_bars.psv.gz", "rt") as fh:
        for ln in fh:
            p = ln.rstrip("\n").split("|")
            if len(p) < 7 or p[3] == "" or p[4] == "":     # high/low NOT NULL, as the live accessor
                continue
            out[p[0]].append({"trade_date": _d(p[1]), "open_price": _f(p[2]),
                              "high_price": _f(p[3]), "low_price": _f(p[4]),
                              "close": _f(p[5]), "volume": _f(p[6])})
    for t in out:
        out[t].sort(key=lambda r: r["trade_date"])
    return dict(out)


def load_bars_poly() -> dict[tuple[str, date], list[dict]]:
    out: dict[tuple[str, date], list[dict]] = defaultdict(list)
    for ln in (HERE / "_structax_bars_polygon.psv").read_text().splitlines():
        p = ln.split("|")
        if len(p) < 8 or p[0].startswith("#"):
            continue
        out[(p[0], _d(p[1]))].append({"trade_date": _d(p[2]), "open_price": _f(p[3]),
                                      "high_price": _f(p[4]), "low_price": _f(p[5]),
                                      "close": _f(p[6]), "volume": _f(p[7])})
    for k in out:
        out[k].sort(key=lambda r: r["trade_date"])
    return dict(out)


PROD = load_bars_prod()
POLY = load_bars_poly()
MAX_BAR = max(b["trade_date"] for bs in PROD.values() for b in bs)

FIELDS = ["n_bars", "reason", "thin_history", "open", "prior_close", "gap_open_pct",
          "adr20_pct", "overhead_vol_frac", "overhead_vol_frac_60d",
          "overhead_vol_frac_at_prior_close", "n_gaps", "n_unfilled_gaps",
          "overhead_unfilled_gap_span_adr", "inside_unfilled_gap",
          "nearest_overhead_gap_bottom_adr", "n_levels", "n_qualified",
          "zones_overhead_at_prior_close", "zones_cleared", "zones_remaining",
          "zones_remaining_in_band", "adr_to_next_zone", "blue_sky", "rmv_15",
          "rmv_tight", "base_range_adr", "base_gap_max_adr", "base_gap_span_adr",
          "base_gap_count_1p0x", "tight_v2", "label"]
EXTRA = ["trailing_high", "near_high_frac", "open_above_trailing_high", "advd20",
         "first_bar", "last_prior_bar"]


def read_one(ticker: str, ad: date, bars_all: list[dict]) -> dict:
    r: dict = {"ticker": ticker, "alert_date": ad}
    prior = [b for b in bars_all if b["trade_date"] < ad]
    same = [b for b in bars_all if b["trade_date"] == ad]
    if not prior:
        r["reason"] = "no_prior_bars"
        return r
    if not same or same[0]["open_price"] in (None, 0):
        r["reason"] = "no_alert_day_open"
        return r
    open_px = float(same[0]["open_price"])
    try:
        r.update(V2.structure_read_v2(prior, ad, open_px))
    except AssertionError as e:                       # the module's own lookahead guard
        r["reason"] = f"lookahead_guard:{e}"
        return r
    highs = [b["high_price"] for b in prior if b["high_price"] is not None]
    r["trailing_high"] = max(highs) if highs else None
    r["near_high_frac"] = (r["prior_close"] / r["trailing_high"]
                           if r.get("prior_close") and r.get("trailing_high") else None)
    r["open_above_trailing_high"] = (open_px > r["trailing_high"]) if r.get("trailing_high") else None
    b20 = prior[-20:]
    dv = [b["close"] * (b["volume"] or 0.0) for b in b20 if b["close"]]
    r["advd20"] = st.median(dv) if len(dv) >= 5 else None
    r["first_bar"] = prior[0]["trade_date"]
    r["last_prior_bar"] = prior[-1]["trade_date"]
    return r


def fmt(v) -> str:
    if v is None:
        return ""
    if isinstance(v, bool):
        return "1" if v else "0"
    if isinstance(v, float):
        return f"{v:.6g}"
    return str(v)


# ── the name-day universe ─────────────────────────────────────────────────────────────
jobs: list[tuple[str, str, date]] = []           # (tag, ticker, alert_date)
seen: set[tuple[str, str, date]] = set()


def add(tag, t, d):
    if (tag, t, d) not in seen:
        seen.add((tag, t, d))
        jobs.append((tag, t, d))


for ln in (HERE / "_srbt_scanlog.psv").read_text().splitlines():
    p = ln.split("|")
    if len(p) < 2:
        continue
    add("cohort", p[1], _d(p[0]))

FIXMEM = [m for m in MUST_NOT_MISS if not m.excluded]
for m in FIXMEM:
    add("fixture", m.ticker, _d(m.alert_date))

_s: set[tuple[str, str]] = set()
for ln in (HERE / "_structax_scanlog.psv").read_text().splitlines():
    p = ln.split("|")
    if len(p) < 7 or p[6].startswith("filter:universe_") or (p[1], p[0]) in _s:
        continue
    _s.add((p[1], p[0]))
    add("v2rej", p[1], _d(p[0]))

print(f"prod bars: {len(PROD)} tickers, last bar {MAX_BAR}", file=sys.stderr)
print(f"jobs: {len(jobs)}", file=sys.stderr)

rows = []
for i, (tag, t, ad) in enumerate(jobs):
    if i % 500 == 0:
        print(f"  {i}/{len(jobs)}", file=sys.stderr)
    r = read_one(t, ad, PROD.get(t, []))
    r["tag"], r["src"] = tag, "prod"
    rows.append(r)

# bar-source fidelity: the SAME name-days re-read off the 08-25 Polygon capture
for tag, t, ad in jobs:
    if tag not in ("fixture", "v2rej"):
        continue
    bs = POLY.get((t, ad))
    if not bs:
        continue
    r = read_one(t, ad, bs)
    r["tag"], r["src"] = tag, "poly"
    rows.append(r)

hdr = ["src", "tag", "ticker", "alert_date"] + FIELDS + EXTRA
out = [ "|".join(hdr) ]
for r in rows:
    out.append("|".join(fmt(r.get(k)) for k in hdr))
(HERE / "_srbt_reads.psv").write_text("\n".join(out) + "\n")
print(f"wrote _srbt_reads.psv  rows={len(rows)}", file=sys.stderr)
