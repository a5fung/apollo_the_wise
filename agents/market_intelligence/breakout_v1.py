"""Breakout v1 — the operator's PAPER rule set for Qullamaggie's breakout, as PURE functions (no I/O).

Owner of the rules: `docs/setups/consolidation_breakout.md` (change log 2026-10-28 "v1 FINAL" + "his PAPER GO", and the
2026-10-29 rulings: single-asset funds join the universe, the breakdown check is in v1). Build plan:
`docs/design/breakout_v1_build_spec_2026-10-29.md` (component B1). This module DECIDES nothing on its own — the nightly
list (`breakout_v1_list.py`) calls it, and the parity test (`tests/test_breakout_v1_parity.py`) pins it to the
reference arithmetic it was ported from (`scripts/probes/_qm_0810_review/v1_check.py` + `v1_check_variant.py`, variant
V3 + the best-of-three RS gate: 12 of his 24 dated good setups caught).

THE RULES, at the watch night D (every measure on bars <= D; the breakout day is E = D + 1):
  universe   RAW close(D) >= $2 and the 20-session median dollar volume ending D >= $5M (adjusted close x volume,
             `cb._dollar_vol_median`); the security type is decided upstream (`security_admitted`)
  rs         rs_best(D) >= 98 — the best of the 21 / 63 / 126-session return percentiles over the night's v1 universe
             (`cb.cross_section_one_date`; computed by the caller, this module only reads it)
  prior_move P = the pole top in [D-45, D-10] (`cb._pole_top`, the #592 walk); high(P) / min low[P-40, P] - 1 >= 0.30
  higher_lows the lowest low of D-4..D is above the base low (the lowest low of P+1..D), strict
  surf       >= 5 sessions in a row ending at D whose LOW is within 1.0 x ADR20(s) x close(s) of ONE of the 10 / 20 / 50-day
             (each session's own ADR20 — the mean of (h-l)/c over the 20 sessions ending s — and its own close; inclusive)
  tightening mean (h-l)/c of D-4..D <= 1.1 x the mean of D-9..D-5 (inclusive)
  breakdown  (his "yes" 2026-10-29) close(D) NOT below ALL of the 10 / 20 / 50-day AND low(D) NOT below the lowest low of
             the 10 sessions D-10..D-1
  NO base anchor (a close above an earlier peak no longer ends the base).
And on E (`breakout_triggered`): high(E) > the LEVEL = the highest high of D-4..D (strict) and volume(E) >= the VOLUME
BAR = 1.2 x the mean volume of D-49..D (inclusive).

Fund rule (his ruling 2026-10-29, "yes, single asset makes sense"): common stock (CS) and ADRs (ADRC) are in; of the
exchange-traded vehicles (ETV) only SINGLE-ASSET funds — one coin, one metal, one commodity, one currency — decided from
the fund's NAME (`fund_rule`): no leveraged / inverse marker, no basket marker, and exactly ONE known underlying named.
An ETV whose name names no known underlying is EXCLUDED (fail closed) and the caller counts and names it.

Units: ADR20 is a FRACTION of the close (0.05 = 5%), as everywhere in `consolidation_breakout`.
"""
from __future__ import annotations

import math
import re
from typing import Mapping, Optional, Sequence

import numpy as np

from agents.market_intelligence import consolidation_breakout as cb

# ── v1 constants (the SSoT's "v1 FINAL" table) ──────────────────────────────────────────────────────────────
MIN_PRICE = 2.0                      # RAW close at D
MIN_DOLLAR_VOL = 5_000_000.0         # 20-session median of close x volume ending D
DOLLAR_VOL_WINDOW = cb.DOLLAR_VOL_WINDOW
RS_MIN = cb.RS_BEST_PRIMARY          # 98.0, best of the 21/63/126-session percentiles
RS_HORIZONS = cb.RS_HORIZONS         # (21, 63, 126)
PRIOR_MOVE_MIN = cb.PRIOR_MOVE_MIN   # 0.30
POLE_LOOKBACK = cb.POLE_LOOKBACK     # 40: pole low = min low over [P-40, P]
BASE_MIN = cb.BASE_MIN_SESSIONS      # 10
BASE_MAX = cb.BASE_MAX_SESSIONS      # 45
RECENT = 5                           # the last-5-session windows (higher lows, tightening, level)
SURF_SESSIONS = 5
SURF_ADR_K = 1.0
SURF_SMAS = (10, 20, 50)
ADR_WINDOW = 20
TIGHT_MAX = 1.1
VOL_X = 1.2
VOL_WINDOW = 50
BREAKDOWN_SMAS = (10, 20, 50)
BREAKDOWN_LOW_SESSIONS = 10
DEEP = BASE_MAX + POLE_LOOKBACK      # 85: the deepest look-back from D (the pole-low window of the oldest pole)
MIN_BARS = DEEP + 1                  # 86 bars ending D, consecutive sessions (the data guard)

GATES = ("history", "universe", "rs", "prior_move", "higher_lows", "surf", "tightening", "breakdown")
STOCK_SECURITY_TYPES = frozenset({"CS", "ADRC"})
FUND_SECURITY_TYPE = "ETV"


# ═══════════════════════════════════════════════════════════════════════════════════════════════
# 1. The fund rule (single-asset ETVs only)
# ═══════════════════════════════════════════════════════════════════════════════════════════════
# A leveraged or inverse fund: excluded whatever it holds.
_LEVERAGED_INVERSE = (
    r"\bultra", r"\bshort\b", r"\bbear(?:ish)?\b", r"\binverse\b", r"\bleveraged?\b", r"\bdaily\b",
    r"(?<![\w.])-?\d+(?:\.\d+)?x\b",
)
# A multi-asset basket named as one: excluded whatever single words it also carries.
_BASKET = (
    r"\bbasket\b", r"\bcommodit", r"\bagricultur", r"\bbase metals?\b", r"\bprecious metals?\b", r"\benergy\b",
    r"\bcrypto\b", r"\bdiversified\b", r"\bmulti\b", r"\bgsci\b", r"\bbroad\b",
)
# The known single underlyings, (key, lower-case pattern). ORDER MATTERS: a multi-word name is matched and blanked
# before its parts (so "Australian Dollar" is one AUD, not AUD + USD). Several patterns may share a key ("Brent Oil").
_UNDERLYINGS = (
    ("aud", r"australian dollar"), ("cad", r"canadian dollar"), ("nzd", r"new zealand dollar"),
    ("gbp", r"british pound|pound sterling|\bsterling\b"), ("chf", r"swiss franc"),
    ("jpy", r"japanese yen|\byen\b"), ("eur", r"\beuro\b"), ("cny", r"chinese yuan|\byuan\b|renminbi"),
    ("usd", r"\bdollar\b"),
    ("natural_gas", r"natural gas"), ("oil", r"crude oil|\bbrent\b|\bwti\b|\bcrude\b|\boil\b"),
    ("gasoline", r"\bgasoline\b"), ("heating_oil", r"heating oil"),
    ("gold", r"\bgold\b"), ("silver", r"\bsilver\b"), ("platinum", r"\bplatinum\b"), ("palladium", r"\bpalladium\b"),
    ("copper", r"\bcopper\b"), ("uranium", r"\buranium\b"),
    ("corn", r"\bcorn\b"), ("wheat", r"\bwheat\b"), ("soybean", r"\bsoybeans?\b"), ("sugar", r"\bsugar\b"),
    ("coffee", r"\bcoffee\b"), ("cocoa", r"\bcocoa\b"), ("cotton", r"\bcotton\b"),
    ("carbon", r"\bcarbon\b"),
    ("bitcoin", r"\bbitcoin\b"), ("ethereum", r"\bethereum\b|\bether\b"), ("solana", r"\bsolana\b"),
    ("xrp", r"\bxrp\b"), ("zcash", r"\bzcash\b"), ("avalanche", r"\bavalanche\b"), ("hyperliquid", r"\bhyperliquid\b"),
    ("chainlink", r"\bchainlink\b"), ("sui", r"\bsui\b"), ("dogecoin", r"\bdogecoin\b"), ("litecoin", r"\blitecoin\b"),
    ("cardano", r"\bcardano\b"), ("polkadot", r"\bpolkadot\b"), ("hedera", r"\bhedera\b"), ("stellar", r"\bstellar\b"),
    ("tron", r"\btron\b"), ("aptos", r"\baptos\b"), ("bittensor", r"\bbittensor\b"),
)
_CASE_SENSITIVE_UNDERLYINGS = (("near", r"\bNEAR\b"),)   # the coin is written in capitals; "near" is an English word

_LEV_RE = [re.compile(p) for p in _LEVERAGED_INVERSE]
_BASKET_RE = [re.compile(p) for p in _BASKET]
_UND_RE = [(k, re.compile(p)) for k, p in _UNDERLYINGS]
_UND_CS_RE = [(k, re.compile(p)) for k, p in _CASE_SENSITIVE_UNDERLYINGS]


def fund_rule(name: Optional[str]) -> dict:
    """The single-asset decision for one ETV's NAME: {keep, reason, underlyings}. reason is one of
    'single_asset' (kept) | 'no_name' | 'leveraged_or_inverse' | 'basket' | 'no_known_underlying' |
    'several_underlyings' (all excluded). Fails CLOSED: an unknown name is excluded and named by the caller."""
    if not name or not str(name).strip():
        return {"keep": False, "reason": "no_name", "underlyings": []}
    raw = " ".join(str(name).split())
    low = raw.lower()
    if any(r.search(low) for r in _LEV_RE):
        return {"keep": False, "reason": "leveraged_or_inverse", "underlyings": []}
    if any(r.search(low) for r in _BASKET_RE):
        return {"keep": False, "reason": "basket", "underlyings": []}
    found: list = []
    rest = low
    for key, rx in _UND_RE:
        for m in list(rx.finditer(rest)):
            found.append(key)
        rest = rx.sub(lambda m: " " * len(m.group(0)), rest)
    for key, rx in _UND_CS_RE:
        if rx.search(raw):
            found.append(key)
    keys = sorted(set(found))
    if not keys:
        return {"keep": False, "reason": "no_known_underlying", "underlyings": []}
    if len(keys) > 1:
        return {"keep": False, "reason": "several_underlyings", "underlyings": keys}
    return {"keep": True, "reason": "single_asset", "underlyings": keys}


def fund_is_single_asset(name: Optional[str]) -> bool:
    return bool(fund_rule(name)["keep"])


def security_admitted(ticker: str, security_type: Optional[str], fund_name: Optional[str] = None) -> tuple:
    """(admitted, reason) for the v1 universe's TYPE half. Test symbols and tickers off `^[A-Z]{1,5}$` are out (as
    `cb.universe_ok`); CS / ADRC in; an UNKNOWN type (no `mi_security_types` row) is admitted, as `cb.universe_ok`
    does in prod; an ETV only when `fund_rule(fund_name)` keeps it; every other type out."""
    if not (isinstance(ticker, str) and cb.UNIVERSE_TICKER_RE.fullmatch(ticker)) or cb.is_test_symbol(ticker):
        return False, "ticker"
    st = (security_type or "").strip()
    if not st:
        return True, "type_unknown"
    if st in STOCK_SECURITY_TYPES:
        return True, "stock"
    if st == FUND_SECURITY_TYPE:
        fr = fund_rule(fund_name)
        return (True, "fund_kept") if fr["keep"] else (False, "fund_" + fr["reason"])
    return False, "type_other"


# ═══════════════════════════════════════════════════════════════════════════════════════════════
# 2. The gates at the watch night D
# ═══════════════════════════════════════════════════════════════════════════════════════════════
def _f(x) -> Optional[float]:
    """A plain float, None for a non-finite value (jsonb has no NaN)."""
    if x is None:
        return None
    x = float(x)
    return x if math.isfinite(x) else None


def adr20_at(rng: np.ndarray, s: int) -> Optional[float]:
    """Mean of (h-l)/c over the 20 sessions ending s (the calibration's ADR); None before 20 sessions exist."""
    if s - ADR_WINDOW + 1 < 0:
        return None
    return float(rng[s - ADR_WINDOW + 1:s + 1].mean())


def surf_run(bars: "cb.DailyBars", rng: np.ndarray, D: int, n: int) -> int:
    """Sessions in a row ending at D whose low sits within SURF_ADR_K x ADR20(s) x close(s) of SMA n at s."""
    run = 0
    s = D
    while s >= 0:
        sma = cb._sma_at(bars, s, n)
        adr = adr20_at(rng, s)
        if sma is None or adr is None:
            break
        band = SURF_ADR_K * adr * float(bars.c[s])
        if not (math.isfinite(sma) and math.isfinite(band) and abs(float(bars.l[s]) - sma) <= band):
            break
        run += 1
        s -= 1
    return run


def history_ok(D: int, cidx: Optional[Sequence[int]] = None) -> bool:
    """>= MIN_BARS bars ending D, and (when the calendar index is given) they are CONSECUTIVE sessions — a hole is
    a halt, a data gap or a reused ticker (`cb.contiguous_window_mask`'s reading)."""
    if D < DEEP:
        return False
    if cidx is None:
        return True
    return int(cidx[D]) - int(cidx[D - DEEP]) == DEEP


def v1_gates(bars: "cb.DailyBars", D: int, *, rs_best: Optional[float], raw_close: Optional[float] = None,
             cidx: Optional[Sequence[int]] = None) -> dict:
    """Every v1 gate at watch night D, pass AND value, plus the next session's breakout LEVEL and VOLUME BAR.

    `bars` = one ticker's ascending daily bars (split-adjusted), D an index into them; `rs_best` = that ticker's
    best-of-three RS percentile at D over the night's v1 universe (None = not in the cross-section -> the rs gate
    fails); `raw_close` = the RAW close at D for the $2 floor (default: the stored close, which IS the raw close on
    the latest night); `cidx` = the calendar index of each bar (None = no hole check).

    Returns {"ok", "failed", "gates": {name: {"pass", "value"}}, "level", "vol_bar", "adr20", "close", "pole_idx",
    "pole_date", "pole_high", "prior_move", "base_low", "watch_date"}. "ok" = every gate in `GATES` passes — the
    name goes on tonight's list. Every gate is evaluated (no short-circuit) so a night's per-gate fail counts are
    complete; only a failed `history` gate leaves the rest unevaluated (None)."""
    n = len(bars)
    if not (0 <= D < n):
        raise IndexError(f"v1_gates: D={D} outside 0..{n - 1}")
    out = {"watch_date": bars.dates[D].isoformat() if hasattr(bars.dates[D], "isoformat") else str(bars.dates[D]),
           "gates": {}, "level": None, "vol_bar": None, "adr20": None, "close": _f(bars.c[D]), "pole_idx": None,
           "pole_date": None, "pole_high": None, "prior_move": None, "base_low": None}
    g = out["gates"]
    hist = history_ok(D, cidx)
    g["history"] = {"pass": hist, "value": {"bars_to_d": D + 1, "need": MIN_BARS,
                                            "consecutive": None if cidx is None else hist}}
    if not hist:
        for k in GATES[1:]:
            g[k] = {"pass": None, "value": None}
        out["ok"], out["failed"] = False, ["history"]
        return out

    h, l, c, v = bars.h, bars.l, bars.c, bars.v
    with np.errstate(invalid="ignore", divide="ignore"):
        rng = (h - l) / c

    # universe ($2 raw close, $5M median dollar volume)
    rc = float(c[D]) if raw_close is None else float(raw_close)
    dv20 = cb._dollar_vol_median(bars, D)
    g["universe"] = {"pass": bool(rc >= MIN_PRICE and dv20 >= MIN_DOLLAR_VOL),
                     "value": {"raw_close": _f(rc), "dollar_vol20": _f(dv20)}}

    # rs
    g["rs"] = {"pass": bool(rs_best is not None and rs_best >= RS_MIN), "value": {"rs_best": _f(rs_best)}}

    # prior move + higher lows (v1_check.structure, the module's pole top)
    P = cb._pole_top(h, c, D - BASE_MAX, D - BASE_MIN)
    pole_high = float(h[P])
    pole_low = float(l[P - POLE_LOOKBACK:P + 1].min())
    prior = pole_high / pole_low - 1.0 if pole_low > 0 else -1.0
    base_low = float(l[P + 1:D + 1].min())
    recent_low = float(l[D - RECENT + 1:D + 1].min())
    g["prior_move"] = {"pass": bool(prior >= PRIOR_MOVE_MIN),
                       "value": {"prior_move": _f(prior), "pole_high": pole_high, "pole_low": pole_low,
                                 "pole_date": str(bars.dates[P]), "base_len": D - P}}
    g["higher_lows"] = {"pass": bool(recent_low > base_low), "value": {"recent_low": recent_low, "base_low": base_low}}

    # surf (one of the 10/20/50-day, each session's own ADR20 and close)
    runs = {f"run{k}": surf_run(bars, rng, D, k) for k in SURF_SMAS}
    best = max(runs.values())
    g["surf"] = {"pass": bool(best >= SURF_SESSIONS), "value": dict(runs, best=best)}

    # tightening
    r_recent = float(rng[D - RECENT + 1:D + 1].mean())
    r_early = float(rng[D - 2 * RECENT + 1:D - RECENT + 1].mean())
    with np.errstate(invalid="ignore", divide="ignore"):
        tight = float(np.float64(r_recent) / np.float64(r_early))
    g["tightening"] = {"pass": bool(math.isfinite(tight) and tight <= TIGHT_MAX),
                       "value": {"ratio": _f(tight), "range_recent5": _f(r_recent), "range_early5": _f(r_early)}}

    # breakdown (his ODD reading, 2026-10-29)
    smas = {f"sma{k}": cb._sma_at(bars, D, k) for k in BREAKDOWN_SMAS}
    close_d = float(c[D])
    below_all = all(s is not None and close_d < s for s in smas.values())
    prior_low10 = float(l[D - BREAKDOWN_LOW_SESSIONS:D].min())
    new_low = bool(float(l[D]) < prior_low10)
    g["breakdown"] = {"pass": bool(not below_all and not new_low),
                      "value": dict({k: _f(s) for k, s in smas.items()}, close=close_d, below_all=below_all,
                                    low=float(l[D]), prior_low10=prior_low10, new_low=new_low)}

    v50 = float(v[D - VOL_WINDOW + 1:D + 1].mean())
    out.update(level=float(h[D - RECENT + 1:D + 1].max()), vol_bar=VOL_X * v50, vol50=v50,
               adr20=_f(adr20_at(rng, D)), pole_idx=int(P), pole_date=str(bars.dates[P]), pole_high=pole_high,
               prior_move=_f(prior), base_low=base_low)
    out["failed"] = [k for k in GATES if not g[k]["pass"]]
    out["ok"] = not out["failed"]
    return out


def _bar_get(bar: Mapping, *keys):
    for k in keys:
        if k in bar and bar[k] is not None:
            return float(bar[k])
    return None


def breakout_triggered(bar_E: Mapping, gates: dict) -> dict:
    """The breakout on E = D + 1 for the night-D result `gates` (`v1_gates`): high(E) > level (strict) and
    volume(E) >= the volume bar (1.2x the 50-session mean to D, inclusive). `bar_E` carries the session's high and
    volume ("h"/"v" or "high"/"volume"). `fired` = the setup passed at D AND both hold on E. The caller owns that E
    is the NEXT session after D (a hole between them is not a breakout of that list)."""
    hi = _bar_get(bar_E, "h", "high")
    vol = _bar_get(bar_E, "v", "volume")
    level, bar = gates.get("level"), gates.get("vol_bar")
    level_pass = bool(hi is not None and level is not None and hi > level)
    vol_pass = bool(vol is not None and bar is not None and vol >= bar)
    return {"level_pass": level_pass, "volume_pass": vol_pass,
            "fired": bool(gates.get("ok")) and level_pass and vol_pass,
            "high": hi, "volume": vol, "level": level, "vol_bar": bar}


# ═══════════════════════════════════════════════════════════════════════════════════════════════
# 3. The RS inputs (the caller builds the cross-section with `cb.cross_section_one_date`)
# ═══════════════════════════════════════════════════════════════════════════════════════════════
def rs_returns_contiguous(bars: "cb.DailyBars", i: int, cidx: Optional[Sequence[int]] = None) -> tuple:
    """(r21, r63, r126) at session i — `cb.rs_returns`, except a horizon whose window crosses a HOLE in the
    calendar (when `cidx` is given) is None rather than a return measured over the wrong span."""
    r = list(cb.rs_returns(bars, i))
    if cidx is not None:
        for k, hz in enumerate(RS_HORIZONS):
            j = i - hz
            if r[k] is not None and (j < 0 or int(cidx[i]) - int(cidx[j]) != hz):
                r[k] = None
    return tuple(r)
