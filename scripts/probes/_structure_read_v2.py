#!/usr/bin/env python3
"""STRUCTURE READ v2 — the SUPPLY LADDER, made measurable at admission time.
(READ-ONLY · SHADOW ONLY · $0 · MEASUREMENT ONLY. Wired into nothing. Changes no rule,
no threshold, no toggle, no trade state. Promotion is fork S-3 — THE LINE.)

WHY THIS EXISTS
---------------
Operator, 2026-08-25, on CAPR: *"the gap up just barely made up for the most recent drop
but just at where there's a huge gap down from July 27; not an EP by a mile."* And, on
hearing the live structure axis scores CAPR and MRNA identically: *"even base tightness
seems off — how can CAPR have a tight base when there's two large gap downs? We need to
fix chart reading, otherwise what's the point of shadow."*

`docs/analysis/structure_axis_replay_2026-08-25.md` measured the live axis on the same
two populations used here: AUC 0.481 (a coin flip is 0.500), the same zero-credit verdict
for 52 of 53 name-days, and **no congestion / level / gap-zone concept anywhere in it**.

WHAT IS REUSED, AND WHAT IS NEW (P15 — a third definition of structure is the fork this
repo keeps paying for)
------------------------------------------------------------------------------------
REUSED, IMPORTED, NOT RE-IMPLEMENTED:
  * `_533_nbis_structure_encoder.pivot_levels` / `.sma50_level` / `.adr20_pct` — the
    operator-blessed level derivation: daily pivot highs merged within 0.3% (his own RMVP
    developer parameter), qualified by >=2 FAILED TEST EPISODES, level dies on a daily
    close above it, and **the lookback is each level's own test dates — no window
    parameter** (`docs/methodology/structure_model.md` §3). Parity-checked at import time
    against the four level values §4 documents (NBIS 226.81 · EROC 11.88 · SE 118.09 ·
    FRMI's 50-day 7.06) — see `parity_check()`.
  * `flag_detector._compute_rmv` — the live tightness primitive, so the v1-vs-v2 tightness
    comparison is against the real thing, not a lookalike.

NEW HERE (the three things nothing in the repo encodes):
  1. **VOLUME-AT-PRICE OVERHEAD** — the share of the name's own traded volume that sits
     ABOVE the open. This is his supply argument taken literally (*"congestion of prices
     is where potential supply is... that's where lots of buy/sell happened"*), and it is
     **threshold-free**: no cutline, no window, no tuned constant. 0.0 = blue sky.
  2. **UNFILLED GAP ZONES** — a true price vacuum (`high[i] < low[i-1]` down, or
     `low[i] > high[i-1]` up) with the part later sessions never traded back through
     subtracted away. This is the July-27 CAPR object. It answers "where is this gap
     LANDING" — below / inside / above each unfilled vacuum.
  3. **GAP-AWARE BASE TIGHTNESS** — a base containing a large unfilled gap is not tight,
     whatever its range statistics say. See the RMV defect note below.

🔴 THE RMV DEFECT THIS MEASURES (the operator's second objection, mechanically)
------------------------------------------------------------------------------
`_compute_rmv` is a RATIO: mean(gap-aware true range over the last 3 bars) ÷ mean(the same
over the last 15). A large gap inside the 15-bar baseline inflates the DENOMINATOR, so the
name reads *tighter*. A large gap just outside the 15-bar window is invisible to it
entirely. Either way "tight base" is being decided without reference to the gaps.
`base_range_adr` below is the gap-robust alternative: it divides the base's close-to-close
SPAN (which gaps inflate) by ADR20 (an intraday-range mean, which gaps do NOT inflate).

DISCLOSED CONSTANTS (this file invents no new number)
-----------------------------------------------------
  * `LARGE_GAP_ADR = 1.0` — the size at which a gap counts as "large" for the base test.
    Reused from the encoder's `REJECT_ADR` (one typical day's range = the natural unit for
    "this is a discontinuity, not noise"). Sensitivity at 0.5x and 2.0x is reported.
  * `MARGIN_ADR = 0.25` (imported) — the encoder's "through, not onto" margin, used ONLY
    for the descriptive IFFY label. ⚠ It is **fixture-calibrated on the operator's eight
    labelled reads** (the encoder header says so). Reusing it INHERITS that calibration
    rather than avoiding one — which is why nothing tested here depends on it.
  * Every level parameter (0.3% merge, 0.5xADR test proximity, 1.0xADR episode
    separation, 1.5xADR band) comes from the encoder, i.e. from his own shared sources.

NO LOOKAHEAD — enforced, not assumed. Every function takes bars STRICTLY PRIOR to the
alert date plus the alert-day OPEN (known at 09:30, which is when admission decides), and
`structure_read_v2` ASSERTS the prior-bar list contains nothing dated on or after the
alert date. The alert-day high/low/close/volume are never read.
"""
from __future__ import annotations

import statistics as st
import sys
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
_REPO = HERE.parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import _533_nbis_structure_encoder as ENC  # noqa: E402  (the blessed level derivation)

from agents.market_intelligence.flag_detector import _compute_rmv  # noqa: E402

# ── constants, all inherited (see the header's DISCLOSED CONSTANTS block) ──────────────
LARGE_GAP_ADR = ENC.REJECT_ADR        # 1.0 — "large" gap = one typical day's range
MARGIN_ADR = ENC.MARGIN_ADR           # 0.25 — descriptive IFFY label only (⚠ calibrated)
BAND_ADR = ENC.BAND_ADR               # 1.5 — the RMVP congestion band above the open
RMV_LOOKBACK = 15                     # the live axis's own base window
MIN_BARS = 10                         # the encoder's own hard floor for any read at all
THIN_HISTORY_BARS = 30                # the encoder's `MIN_HISTORY` flag level


# ── bar helpers ───────────────────────────────────────────────────────────────────────
def _tuples(bars: list[dict]) -> list[tuple]:
    """dict bars -> the encoder's own (date, o, h, l, c, v) tuple shape."""
    return [(str(b["trade_date"]), float(b["open_price"]), float(b["high_price"]),
             float(b["low_price"]), float(b["close"]), float(b.get("volume") or 0.0))
            for b in bars]


def adr20(bars: list[dict]) -> float | None:
    """ADR20 in percent — the encoder's own `adr20_pct`, over the last 20 PRIOR bars."""
    days = _tuples(bars)
    return ENC.adr20_pct(days, len(days))


# ── 1 — VOLUME AT PRICE (threshold-free overhead supply) ──────────────────────────────
def overhead_volume_fraction(bars: list[dict], price: float) -> float | None:
    """Share of traded volume sitting ABOVE `price`.

    Each session spreads its volume uniformly across its own [low, high] — the simplest
    faithful reading of *"congestion of prices is where potential supply is (that's where
    lots of buy/sell happened)"*. A zero-range session is a point mass at its close.

    0.0 = blue sky (nothing above). 1.0 = every share ever traded is overhead.
    Returns None when there is no volume at all to weigh.
    """
    tot = 0.0
    above = 0.0
    for b in bars:
        v = float(b.get("volume") or 0.0)
        if v <= 0:
            continue
        h, l = float(b["high_price"]), float(b["low_price"])
        if h > l:
            frac = min(1.0, max(0.0, (h - price) / (h - l)))
        else:
            frac = 1.0 if float(b["close"]) > price else 0.0
        tot += v
        above += v * frac
    return None if tot <= 0 else above / tot


# ── 2 — UNFILLED GAP ZONES (the July-27 CAPR object) ──────────────────────────────────
def _subtract(intervals: list[tuple[float, float]], lo: float, hi: float
              ) -> list[tuple[float, float]]:
    """Remove [lo, hi] from a list of disjoint (a, b) intervals."""
    out: list[tuple[float, float]] = []
    for a, b in intervals:
        if hi <= a or lo >= b:          # no overlap
            out.append((a, b))
            continue
        if lo > a:
            out.append((a, min(lo, b)))
        if hi < b:
            out.append((max(hi, a), b))
    return [(a, b) for a, b in out if b - a > 1e-12]


def gap_zones(bars: list[dict]) -> list[dict]:
    """Every TRUE price vacuum in the prior history, with the part later sessions traded
    back through subtracted away.

    A gap DOWN at bar i is `high[i] < low[i-1]` — the band (high[i], low[i-1]) is a range
    of prices at which *nothing has ever traded on that day or since, unless a later
    session reached back into it*. A gap UP is `low[i] > high[i-1]`.

    Returns one dict per gap, oldest first:
      direction 'down'|'up' · date · bottom · top · span_pct (of the gap's own reference
      price) · unfilled (list of remaining sub-intervals) · unfilled_span (price units) ·
      filled_frac.
    """
    out: list[dict] = []
    n = len(bars)
    for i in range(1, n):
        prev, cur = bars[i - 1], bars[i]
        ph, pl = float(prev["high_price"]), float(prev["low_price"])
        ch, cl = float(cur["high_price"]), float(cur["low_price"])
        if ch < pl:
            bottom, top, direction = ch, pl, "down"
        elif cl > ph:
            bottom, top, direction = ph, cl, "up"
        else:
            continue
        ref = float(prev["close"]) or bottom
        remaining = [(bottom, top)]
        for j in range(i + 1, n):
            remaining = _subtract(remaining,
                                  float(bars[j]["low_price"]), float(bars[j]["high_price"]))
            if not remaining:
                break
        span = top - bottom
        unfilled_span = sum(b - a for a, b in remaining)
        out.append({
            "direction": direction, "date": bars[i]["trade_date"],
            "bottom": bottom, "top": top,
            "span_pct": (span / ref * 100.0) if ref else None,
            "unfilled": remaining, "unfilled_span": unfilled_span,
            "filled_frac": 1.0 - (unfilled_span / span if span > 0 else 0.0),
        })
    return out


def gap_landing(zones: list[dict], open_px: float, adr_pct: float) -> dict:
    """WHERE IS THIS GAP LANDING? — the open placed against every unfilled vacuum.

    * `overhead_unfilled_gap_span_adr` — how much untraded air sits ABOVE the open,
      summed over every unfilled remnant, in ADR20 units. CAPR's July-27 wreckage is this
      number; a name gapping to new highs has 0.
    * `inside_unfilled_gap` — the open landed INSIDE a vacuum: no supply right here, but
      a wall of trapped holders starting at that zone's top.
    * `nearest_overhead_gap_top_adr` — ADR distance up to the bottom of the nearest
      unfilled remnant above the open (the runway before the next untraded air).
    """
    unit = open_px * adr_pct / 100.0 if adr_pct else None
    above = 0.0
    nearest = None
    inside = None
    for z in zones:
        for a, b in z["unfilled"]:
            if b <= open_px:
                continue
            lo = max(a, open_px)
            above += b - lo
            if a <= open_px < b:
                inside = z
            elif a > open_px and (nearest is None or a < nearest):
                nearest = a
    return {
        "overhead_unfilled_gap_span_adr": (above / unit) if unit else None,
        "inside_unfilled_gap": inside is not None,
        "inside_unfilled_gap_dir": inside["direction"] if inside else None,
        "inside_unfilled_gap_date": str(inside["date"]) if inside else None,
        "inside_unfilled_gap_top_adr": ((inside["top"] - open_px) / unit
                                        if inside and unit else None),
        "nearest_overhead_gap_bottom_adr": ((nearest - open_px) / unit
                                            if nearest is not None and unit else None),
    }


# ── 3 — THE SUPPLY LADDER (levels cleared / remaining), on the blessed derivation ─────
def supply_ladder(bars: list[dict], open_px: float, adr_pct: float) -> dict:
    """How many congestion zones does this move CLEAR, and what is still overhead?

    Levels come from the encoder unchanged. "Overhead" is judged AS OF THE PRIOR CLOSE
    (what the stock had to get through); "cleared" means the OPEN printed above it.
    """
    days = _tuples(bars)
    ia = len(days)
    prior_close = days[-1][4]
    unit = open_px * adr_pct / 100.0 if adr_pct else None
    levels = ENC.pivot_levels(days, ia, adr_pct)
    s50 = ENC.sma50_level(days, ia, adr_pct)
    if s50:
        levels.append(s50)
    qualified = [L for L in levels if L["n_episodes"] >= 2 or L["kind"] == "sma50"]
    overhead = [L for L in qualified if L["price"] > prior_close]
    cleared = [L for L in overhead if L["price"] < open_px]
    remaining = [L for L in overhead if L["price"] >= open_px]
    band_top = open_px * (1 + BAND_ADR * adr_pct / 100.0) if adr_pct else None
    nxt = min((L["price"] for L in remaining), default=None)
    return {
        "n_levels": len(levels), "n_qualified": len(qualified),
        "zones_overhead_at_prior_close": len(overhead),
        "zones_cleared": len(cleared),
        "zones_remaining": len(remaining),
        "zones_remaining_in_band": sum(1 for L in remaining
                                       if band_top and L["price"] <= band_top),
        "adr_to_next_zone": ((nxt - open_px) / unit) if (nxt is not None and unit) else None,
        "blue_sky": len(remaining) == 0,
        "levels": sorted(({"price": round(L["price"], 4), "kind": L["kind"],
                           "episodes": L["n_episodes"], "first_test": L["first_test"],
                           "last_test": L["last_test"]} for L in qualified),
                         key=lambda x: x["price"]),
    }


# ── 4 — GAP-AWARE BASE TIGHTNESS ──────────────────────────────────────────────────────
def base_tightness(bars: list[dict], adr_pct: float, window: int = RMV_LOOKBACK) -> dict:
    """Is the base actually tight, or does it merely AVERAGE tight?

    `rmv_15` is the live measure, kept for the head-to-head. `base_range_adr` is the
    gap-robust alternative: the base's close-to-close SPAN (which a gap inflates) divided
    by ADR20 (a mean of intraday ranges, which a gap does NOT inflate). `base_gap_*`
    counts the vacuums sitting inside the base at all — the operator's own objection.
    """
    days = _tuples(bars)
    idx = len(days) - 1
    rmv = _compute_rmv([{"open_price": o, "high_price": h, "low_price": l, "close": c}
                        for _, o, h, l, c, _ in days], idx, lookback=window)
    win = bars[-window:] if len(bars) >= window else bars[:]
    closes = [float(b["close"]) for b in win]
    med = st.median(closes) if closes else None
    span_pct = ((max(closes) - min(closes)) / med * 100.0) if med else None
    base_range_adr = (span_pct / adr_pct) if (span_pct is not None and adr_pct) else None
    # gaps whose ORIGIN bar sits inside the base window
    win_dates = {b["trade_date"] for b in win}
    zs = [z for z in gap_zones(bars) if z["date"] in win_dates]
    sizes = sorted(((z["span_pct"] / adr_pct) if adr_pct else 0.0) for z in zs)
    counts = {f"base_gap_count_{m}x".replace(".", "p"):
              sum(1 for s in sizes if s >= m) for m in (0.5, 1.0, 2.0)}
    return {
        "rmv_15": rmv,
        "rmv_tight": (rmv <= 30.0) if rmv is not None else None,   # the live cutline
        "base_range_adr": base_range_adr,
        "base_gap_max_adr": (sizes[-1] if sizes else 0.0),
        "base_gap_span_adr": sum(sizes),
        **counts,
        "tight_v2": ((rmv is not None and rmv <= 30.0)
                     and counts["base_gap_count_1p0x"] == 0) if rmv is not None else None,
    }


# ── the whole read ────────────────────────────────────────────────────────────────────
def structure_read_v2(bars: list[dict], alert_date: date, open_px: float) -> dict:
    """The complete admission-time structure read.

    `bars` MUST be ascending and STRICTLY PRIOR to `alert_date` — asserted, not trusted
    (the 08-25 alert-day row is physically present in the capture files and its volume is
    partial; letting it leak would corrupt ADR20 and the volume profile in a way that
    still looks plausible).
    """
    assert all(b["trade_date"] < alert_date for b in bars), (
        f"lookahead: a bar dated >= {alert_date} reached structure_read_v2")
    out: dict = {"n_bars": len(bars), "open": open_px, "reason": None,
                 "thin_history": len(bars) < THIN_HISTORY_BARS}
    if len(bars) < MIN_BARS:
        out["reason"] = f"history_too_thin({len(bars)}d)"
        return out
    adr = adr20(bars)
    if not adr or adr <= 0:
        out["reason"] = "no_adr"
        return out
    prior_close = float(bars[-1]["close"])
    out.update(adr20_pct=adr, prior_close=prior_close,
               gap_open_pct=(open_px / prior_close - 1) * 100.0)

    out["overhead_vol_frac"] = overhead_volume_fraction(bars, open_px)
    out["overhead_vol_frac_60d"] = overhead_volume_fraction(bars[-60:], open_px)
    out["overhead_vol_frac_at_prior_close"] = overhead_volume_fraction(bars, prior_close)

    zs = gap_zones(bars)
    out["n_gaps"] = len(zs)
    out["n_unfilled_gaps"] = sum(1 for z in zs if z["unfilled_span"] > 0)
    out.update(gap_landing(zs, open_px, adr))
    lad = supply_ladder(bars, open_px, adr)
    out["levels"] = lad.pop("levels")
    out.update(lad)
    out.update(base_tightness(bars, adr))

    # descriptive label only — OUTSIDE the tested set (see the doc's §"what was tested")
    nxt = out.get("adr_to_next_zone")
    if out["zones_remaining"] == 0 and not out["inside_unfilled_gap"] \
            and (out["overhead_unfilled_gap_span_adr"] or 0.0) <= 0.0:
        out["label"] = "CLEAR_AIR"
    elif nxt is not None and abs(nxt) <= MARGIN_ADR:
        out["label"] = "IFFY_AT_FIRST_ZONE"
    elif out["inside_unfilled_gap"] or (nxt is not None and nxt < LARGE_GAP_ADR):
        out["label"] = "INTO_SUPPLY"
    elif out["zones_cleared"] > 0:
        out["label"] = "LADDER_CLIMBING"
    else:
        out["label"] = "CLEARED_NOTHING"
    return out


# ── PARITY — the reused level code must reproduce structure_model.md §4 through THIS
#    adapter before any number computed on top of it means anything ────────────────────
PARITY_TARGETS = [
    # (ticker, alert_date, expected level price, tolerance, what structure_model.md §4 says)
    ("NBIS", "2026-08-12", 226.81, 0.02, "his own '~$227' prior-highs level"),
    ("EROC", "2026-08-12", 11.88, 0.02, "its 6-test base top"),
    ("SE", "2026-08-11", 118.09, 0.02, "base top; the January $129 shelf stays overhead"),
    ("FRMI", "2026-08-11", 7.06, 0.02, "the 50-day it landed ON (7.07 open vs 7.06)"),
]


def _load_533n_daily() -> dict[str, list[dict]]:
    """The encoder's own capture (`_533n_daily.tsv`) — the exact rows its fixture gate ran on."""
    from collections import defaultdict
    out: dict[str, list[dict]] = defaultdict(list)
    p = HERE / "_533n_daily.tsv"
    for ln in p.read_text(encoding="utf-8").splitlines():
        q = ln.split("|")
        if len(q) != 7:
            continue
        try:
            y, m, d = q[1].split("-")
            out[q[0]].append({"trade_date": date(int(y), int(m), int(d)),
                              "open_price": float(q[2]), "high_price": float(q[3]),
                              "low_price": float(q[4]), "close": float(q[5]),
                              "volume": float(q[6] or 0)})
        except ValueError:
            continue
    for t in out:
        out[t].sort(key=lambda r: r["trade_date"])
    return dict(out)


def parity_check(verbose: bool = True) -> list[tuple[str, bool, float | None, float]]:
    """Reproduce the four level values documented in structure_model.md §4 through the
    dict->tuple adapter used everywhere in this module. Returns (name, ok, got, want)."""
    daily = _load_533n_daily()
    rows = []
    for tkr, ds, want, tol, why in PARITY_TARGETS:
        y, m, d = ds.split("-")
        ad = date(int(y), int(m), int(d))
        bars = [b for b in daily.get(tkr, []) if b["trade_date"] < ad]
        got = None
        if len(bars) >= MIN_BARS:
            adr = adr20(bars)
            days = _tuples(bars)
            lv = ENC.pivot_levels(days, len(days), adr)
            s50 = ENC.sma50_level(days, len(days), adr)
            if s50:
                lv.append(s50)
            cands = [L["price"] for L in lv
                     if L["n_episodes"] >= 2 or L["kind"] == "sma50"]
            if cands:
                got = min(cands, key=lambda p: abs(p - want))
        ok = got is not None and abs(got - want) <= tol
        rows.append((f"{tkr} {ds}", ok, got, want))
        if verbose:
            print(f"  {'OK ' if ok else 'XX '} {tkr:<5} {ds}  want {want:>8.2f}  "
                  f"got {('%.2f' % got) if got is not None else '   none':>8}   ({why})")
    return rows


if __name__ == "__main__":
    print("PARITY — reused level derivation vs structure_model.md §4, through this adapter:")
    rows = parity_check()
    print(f"  {sum(1 for _, ok, _, _ in rows if ok)}/{len(rows)} reproduced")
