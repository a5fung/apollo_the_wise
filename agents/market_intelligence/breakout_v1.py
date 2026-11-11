"""Breakout v1 — the operator's PAPER rule set for Qullamaggie's breakout, as PURE functions (no I/O).

Owner of the rules: `docs/setups/consolidation_breakout.md` (change log 2026-11-02 "breakout v1's list REBUILT from
Qullamaggie's own trades"; the earlier v1 entries 2026-10-28 / 10-29 are history). The rules are the spec he signed off
2026-11-02 ("signd off"): `docs/analysis/cb_rebuild_from_qm_trades_2026-11-02.md` §1-§3, reproduced from the research
in `scripts/probes/_qm_breakouts_vs_v1_1102/` (14_ / 15_ / 17_ / 18_ the rules, 23_ the 6-month move, 28_ / 32_ the
last-10-close spread, 33_ the order score, backward/12_final_rules.json the backward thresholds). This module DECIDES
nothing on its own — the nightly list (`breakout_v1_list.py`) calls it. The acceptance bar is the SCORECARD test
(`tests/test_breakout_v2_stage1.py` on `tests/fixtures/qm_breakout_scorecard/`): 263 of Qullamaggie's 269 dated
breakout buys on the list the night before, 26 of 26 big winners, the 6 off exactly his 6 NOs.

INITIAL RULE SET 2026-11-11 (PENDING HIS SIGN-OFF BEFORE PAPER; `docs/analysis/cb_initial_rules_2026-11-11.md`, his
"we are trying to buy like qullamaggie ... buy his setups period"): built on the 84 high-confidence Qullamaggie buys
(`docs/analysis/cb_qm_buy_confidence_2026-11-11.md`). It SUPERSEDES the lines below where they differ:
  prior_move >= 20% (was 32.1%) · base_depth 1.51-11 daily ranges (was -8.98) · ema21 >= -0.9 (was -0.6335) ·
  sma50 NO LONGER A GATE (still measured, `out["sma50"]`, telemetry) · the LEVEL = the LOWER of the lowest qualifying
  RANGE HIGH (`range_levels`: 10+ sessions counting to E, gives back no more than half its run; `out["range"]`) and
  the 5-day high (`level5`); no range = the 5-day high as before (`level_source`) — a missing range never takes a
  name off the list ·
  the VOLUME BAR is unchanged (1.2 x the last 10 sessions, his 2026-11-02 ruling).
  The $2 / $5M / ADR / 86-session floors are unchanged (they cost 5 of the 84: BNGO, INO, HEXO, FCEL, PLTR).

THE LIST RULES, at the watch night D (every measure on bars <= D; the breakout day is E = D + 1):
  history    >= 86 consecutive sessions ending D (the data guard, unchanged)
  universe   RAW close(D) >= $2 and the 20-session median dollar volume ending D >= $5M (adjusted close x volume,
             `cb._dollar_vol_median`); the security type is decided upstream (`security_admitted`)
  pinned     ADR20(D) >= 1% — a deal-pinned stock (his "both", 2026-11-02; inside the 2.1% floor, kept so the reason
             a deal target is out stays visible in the per-gate counts)
  adr        ADR20(D) >= 2.1% (the mean of (h-l)/c over the 20 sessions ending D) — his good EW 2.11%, LMT 2.6%
  rs         rs_best(D) >= 35 — the best of the 21 / 63 / 126-session return percentiles over the night's pool
             (`cb.cross_section_one_date`; computed by the caller, this module only reads it). The LIST's own
             constant: the shadow's `cb.RS_BEST_PRIMARY` (98) is not touched
  prior_move P = the pole top in [D-45, D-10] (`cb._pole_top`, the #592 walk); high(P) / min low[P-40, P] - 1
             >= 0.3213536987121892 (the backward step; the list's own constant, `cb.PRIOR_MOVE_MIN` stays 0.30)
  base_depth (high(P) - the base low) / high(P) / ADR20(D) inside [1.511376833908041, 8.979719460898997] daily
             ranges, inclusive; the base low = the lowest low of P+1..D
  ema21      (close(D) / EMA21(D) - 1) / ADR20(D) >= -0.6335 — the close no more than 0.6335 daily ranges under the
             21-day EMA (EMA seeded at the series' first bar, as the research)
  sma50      close(D) >= the 50-day SMA (the mean of the 50 closes ending D)
  REMOVED 2026-11-02: higher lows, surf (riding an average), tightening and the breakdown check — his CODX / PENN
  charts showed those definitions misread his pattern. NO base anchor (unchanged).
  SHAPE GATES (2026-11-11, `shape_gates`): higher_lows, no_lower_low, rising_avg, not_extended, tight10 — written
  from Qullamaggie's words and the operator's reads, pre-registered and scored in
  `docs/analysis/cb_shape_gates_2026-11-11.md`. The score FAILED its bar, so `ENFORCED_SHAPE_GATES` is EMPTY and the
  list is these seven rules only; the function is the measured, tested starting point for the next definition.
And on E (`breakout_triggered`): high(E) > the LEVEL = the highest high of D-4..D (strict) and volume(E) >= the VOLUME
BAR = 1.2 x the mean volume of D-9..D — the LAST 10 SESSIONS (his ruling 2026-11-02, "Yes"; was the 50-day).

THE ORDER INPUTS (`order_inputs`, per name, bars <= D; the night's ranking is `breakout_v1_list.rank_rows`):
  runup6m      the biggest gain from a low to a later high inside the 126 sessions to D, the low no more than 63
               sessions before the high: max over j in [D-125, D] of high(j) / min low[j-63, j] - 1
  runup6m_adr  runup6m / ADR20(D) — the 6-month run-up in daily ranges (bigger first)
  spread10_adr (max close / min close - 1) / ADR20(D) over the 10 sessions D-9..D (tighter first)

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

# ── the list's constants (the signed-off spec §1, 2026-11-02; each cites its source) ─────────────────────────
MIN_PRICE = 2.0                      # RAW close at D (v1, unchanged)
MIN_DOLLAR_VOL = 5_000_000.0         # 20-session median of close x volume ending D (v1, unchanged)
DOLLAR_VOL_WINDOW = cb.DOLLAR_VOL_WINDOW
# rule 2: strength rank >= 35 — Qullamaggie's 269 buys' lowest is 35.3 (was 98, which blocked 175 of the 269). The
# LIST's own constant; `cb.RS_BEST_PRIMARY` (98) is the forward shadow's and is not touched.
RS_MIN = 35.0
RS_HORIZONS = cb.RS_HORIZONS         # (21, 63, 126)
# rule 5: the run-up into the pole (v1's prior move) >= 32.1% — backward/12_final_rules.json step 3 (the 4th smallest
# of the 162 fit buys); it dropped only his NOs (W, DOCU x2, SQM). The list's own; `cb.PRIOR_MOVE_MIN` (0.30) stays.
PRIOR_MOVE_MIN = 0.20                # 2026-11-11 initial rule set (was 0.3213536987121892): the lowest High-tier buy is 21% (PBR)
POLE_LOOKBACK = cb.POLE_LOOKBACK     # 40: pole low = min low over [P-40, P]
BASE_MIN = cb.BASE_MIN_SESSIONS      # 10
BASE_MAX = cb.BASE_MAX_SESSIONS      # 45
RECENT = 5                           # the level = the highest high of the last 5 sessions
ADR_WINDOW = 20
VOL_X = 1.2
# His ruling 2026-11-02 ("Yes"): the volume bar = 1.2 x the mean volume of the LAST 10 SESSIONS (the base), not the
# 50-day (which carries the run-up's heavy volume): 145 of Qullamaggie's 245 era-A buys fire on his day (was 116),
# 21/26 big winners (was 15) — `scripts/probes/_qm_breakouts_vs_v1_1102/36_trigger_vol10.txt`.
VOL_WINDOW = 10
VOL_WINDOW_50 = 50                   # telemetry only (`vol50` on the row): the old bar's base, never a gate
DEEP = BASE_MAX + POLE_LOOKBACK      # 85: the deepest look-back from D (the pole-low window of the oldest pole)
MIN_BARS = DEEP + 1                  # 86 bars ending D, consecutive sessions (the data guard)

# rule 3 (2026-11-02, his spec sign-off): a DAILY-RANGE FLOOR ADR20 >= 2.1% — his good EW 2.11% and LMT 2.6% sit under
# the 11-02 morning 4.26% floor, which is REPLACED (the SSoT's change log says why it was wrong).
ADR_MIN = 0.021
# His "both" (2026-11-02): a named PINNED-DEAL rule, ADR20 >= 1% (the deal targets BWMN 0.16% / ARX 0.25% / PCRX
# 0.73%). Inside the 2.1% floor (the list is the same) — kept so the per-gate counts name WHY a deal target is out.
PINNED_ADR_MAX = 0.01
# rule 4: base depth from the pole top in daily ranges, inclusive band — the backward step (12_final_rules.json
# step 2, upper end 8.98) with the low end moved to his good LRN 2020-08-05 (1.511; 14_after_his_labels.py).
BASE_DEPTH_ADR_MIN = 1.511376833908041
BASE_DEPTH_ADR_MAX = 11.0            # 2026-11-11 initial rule set (was 8.979719460898997): HEXO 2020-08-13 is 10.8
# rule 6: close no more than 0.6335 daily ranges under the 21-day EMA — loosened to keep the 7 buys he rated ok or
# better (17_ema21_loosened.py); pinned at TSLA 2022-04-21's value (-0.63349 on the research EMA; -0.63 drops it).
EMA_SPAN = 21
EMA21_ADR_MIN = -0.9                 # 2026-11-11 initial rule set (was -0.6335): NVAX 2021-04-13 is -0.85
# rule 7: close at or above the 50-day SMA (18_sma50_rule.py's plain line; drops none of Qullamaggie's buys).
SMA_SESSIONS = 50
# The order inputs (spec §2; 23_move126_rule.py, 32_tight_recently.py, 33_rank_topn.py).
RUNUP6M_SESSIONS = 126               # the highs: the 126 sessions ending D
RUNUP6M_LOW_SESSIONS = 63            # each high's low: the 64 sessions j-63..j (the low no more than 63 before)
SPREAD_SESSIONS = 10                 # the last-10-close spread
# 2026-11-11 initial rule set: `sma50` is no longer a gate (9 of the 31 widened High buys sat under the 50-day; it is
# still measured as telemetry) and `range` is new (a qualifying range to buy the break of).
# 2026-11-11 fix-up: a qualifying range is NOT a gate — it only sets the level (the range high) where one exists.
GATES = ("history", "universe", "pinned", "adr", "rs", "prior_move", "base_depth", "ema21")
# The range break (docs/analysis/cb_initial_rules_2026-11-11.md (b); the High tier of the Qullamaggie buy rating).
RANGE_LOOKBACK = 126                 # how far back from D a level may sit
RANGE_MIN_LEN = 10                   # sessions from the range's start to E = D + 1 (two weeks)
RANGE_GIVE_BACK = 0.5                # the range's low gives back no more than half the run into it
RANGE_RUN_LOOKBACK = 60              # the run = level - the lowest low of the 60 sessions before the range starts
RANGE_TOL_SESSIONS = 20              # "touched the level" = within one mean (high - low) of the 20 sessions ending D
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


def ema_at(c: np.ndarray, D: int, span: int = EMA_SPAN) -> Optional[float]:
    """The `span`-session EMA of the closes at session D, SEEDED AT THE SERIES' FIRST BAR (ema[0] = c[0], then
    ema[i] = a x c[i] + (1 - a) x ema[i-1], a = 2 / (span + 1)) — the research's `ema()` (10_feature_table.py), on
    bars <= D only. With the list job's 200 bars the seed's weight at D is ~1e-8. None on a non-finite close."""
    x = np.asarray(c[:D + 1], dtype=float)
    if x.size == 0 or not np.isfinite(x).all():
        return None
    a = 2.0 / (span + 1)
    e = float(x[0])
    for xi in x[1:]:
        e = a * float(xi) + (1.0 - a) * e
    return e


def history_ok(D: int, cidx: Optional[Sequence[int]] = None) -> bool:
    """>= MIN_BARS bars ending D, and (when the calendar index is given) they are CONSECUTIVE sessions — a hole is
    a halt, a data gap or a reused ticker (`cb.contiguous_window_mask`'s reading)."""
    if D < DEEP:
        return False
    if cidx is None:
        return True
    return int(cidx[D]) - int(cidx[D - DEEP]) == DEEP


def range_levels(h: np.ndarray, l: np.ndarray, D: int) -> list:
    """Every qualifying RANGE at night D (bars <= D), lowest level first: [{"level", "start", "len"}].

    Walk back from D (at most `RANGE_LOOKBACK` sessions): each high above every later high is a level; its range starts
    at the earliest session, among those it stands above, whose high came within one average daily range (mean
    high - low of the `RANGE_TOL_SESSIONS` ending D, in price) of it. It qualifies when it is `RANGE_MIN_LEN`+ sessions
    long counting to E = D + 1 and holds its gains: level - the range's lowest low <= `RANGE_GIVE_BACK` x (level - the
    lowest low of the `RANGE_RUN_LOOKBACK` sessions before the range). The lowest level is the buy point."""
    a = max(0, D - RANGE_TOL_SESSIONS + 1)
    tol = float((h[a:D + 1] - l[a:D + 1]).mean())
    steps, m = [], -math.inf
    for j in range(D, max(-1, D - RANGE_LOOKBACK), -1):
        if h[j] > m:
            m = float(h[j])
            steps.append([m, j])
        if h[j] >= m - tol:
            steps[-1][1] = j
    out = []
    for level, s in steps:
        n = D + 1 - s
        if n < RANGE_MIN_LEN or s < 1:
            continue
        run = level - float(l[max(0, s - RANGE_RUN_LOOKBACK):s].min())
        depth = level - float(l[s:D + 1].min())
        if run > 0 and depth <= RANGE_GIVE_BACK * run:
            out.append({"level": level, "start": int(s), "len": int(n)})
    return out


def v1_gates(bars: "cb.DailyBars", D: int, *, rs_best: Optional[float], raw_close: Optional[float] = None,
             cidx: Optional[Sequence[int]] = None) -> dict:
    """Every v1 gate at watch night D, pass AND value, plus the next session's breakout LEVEL and VOLUME BAR.

    `bars` = one ticker's ascending daily bars (split-adjusted), D an index into them; `rs_best` = that ticker's
    best-of-three RS percentile at D over the night's v1 universe (None = not in the cross-section -> the rs gate
    fails); `raw_close` = the RAW close at D for the $2 floor (default: the stored close, which IS the raw close on
    the latest night); `cidx` = the calendar index of each bar (None = no hole check).

    Returns {"ok", "failed", "gates": {name: {"pass", "value"}}, "level", "vol_bar", "vol10", "vol50", "adr20", "close",
    "pole_idx", "pole_date", "pole_high", "prior_move", "base_low", "watch_date"}. "ok" = every gate in `GATES` passes
    — the name goes on tonight's list. Every gate is evaluated (no short-circuit) so a night's per-gate fail counts
    are complete; only a failed `history` gate leaves the rest unevaluated (None). A value that cannot be computed
    (a non-finite ADR, a zero low) FAILS its gate (the research's "NaN never passes")."""
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

    # pinned + adr — the deal-pinned rule (1%) and the daily-range floor (2.1%); constants above
    adr_d = _f(adr20_at(rng, D))
    g["pinned"] = {"pass": bool(adr_d is not None and adr_d >= PINNED_ADR_MAX),
                   "value": {"adr20": adr_d, "min": PINNED_ADR_MAX}}
    g["adr"] = {"pass": bool(adr_d is not None and adr_d >= ADR_MIN), "value": {"adr20": adr_d, "min": ADR_MIN}}
    adr_pos = adr_d is not None and adr_d > 0

    # rs (the list's own 35)
    g["rs"] = {"pass": bool(rs_best is not None and rs_best >= RS_MIN), "value": {"rs_best": _f(rs_best), "min": RS_MIN}}

    # prior move (the run-up into the pole, the module's pole top) and the base low
    P = cb._pole_top(h, c, D - BASE_MAX, D - BASE_MIN)
    pole_high = float(h[P])
    pole_low = float(l[P - POLE_LOOKBACK:P + 1].min())
    prior = pole_high / pole_low - 1.0 if pole_low > 0 else -1.0
    base_low = float(l[P + 1:D + 1].min())
    g["prior_move"] = {"pass": bool(math.isfinite(prior) and prior >= PRIOR_MOVE_MIN),
                       "value": {"prior_move": _f(prior), "pole_high": pole_high, "pole_low": pole_low,
                                 "pole_date": str(bars.dates[P]), "base_len": D - P, "min": PRIOR_MOVE_MIN}}

    # base depth from the pole top, in daily ranges (inclusive band)
    depth = _f((pole_high - base_low) / pole_high / adr_d) if (adr_pos and pole_high > 0) else None
    g["base_depth"] = {"pass": bool(depth is not None and BASE_DEPTH_ADR_MIN <= depth <= BASE_DEPTH_ADR_MAX),
                       "value": {"depth_adr": depth, "pole_high": pole_high, "base_low": base_low,
                                 "min": BASE_DEPTH_ADR_MIN, "max": BASE_DEPTH_ADR_MAX}}

    # the close vs the 21-day EMA, in daily ranges
    close_d = float(c[D])
    e21 = ema_at(c, D, EMA_SPAN)
    vs21 = _f((close_d / e21 - 1.0) / adr_d) if (adr_pos and e21 is not None and e21 > 0) else None
    g["ema21"] = {"pass": bool(vs21 is not None and vs21 >= EMA21_ADR_MIN),
                  "value": {"ema21": _f(e21), "close": _f(close_d), "vs_ema21_adr": vs21, "min": EMA21_ADR_MIN}}

    # the close at or above the 50-day SMA
    s50 = cb._sma_at(bars, D, SMA_SESSIONS)
    sma50 = {"pass": bool(s50 is not None and math.isfinite(s50) and close_d >= s50),
             "value": {"sma50": _f(s50), "close": _f(close_d)}}
    out["sma50"] = sma50                                     # telemetry since 2026-11-11 (no longer in GATES)
    if "sma50" in GATES:
        g["sma50"] = sma50

    # the range to buy the break of: the LEVEL is the lowest qualifying range high (2026-11-11; was the 5-day high)
    rl = range_levels(np.asarray(h, float), np.asarray(l, float), D)
    out["range"] = {"pass": bool(rl), "value": {"n_levels": len(rl), "level": rl[0]["level"] if rl else None,
                                                "start_date": str(bars.dates[rl[0]["start"]]) if rl else None,
                                                "len": rl[0]["len"] if rl else None, "min_len": RANGE_MIN_LEN}}
    if "range" in GATES:
        g["range"] = out["range"]

    v10 = float(v[D - VOL_WINDOW + 1:D + 1].mean())
    v50 = float(v[D - VOL_WINDOW_50 + 1:D + 1].mean())
    level5 = float(h[D - RECENT + 1:D + 1].max())
    # the LOWER of the range high and the 5-day high: a name is bought through whichever comes first, so no buy the
    # 5-day level made is lost and a range break under it is bought at the range high (13_head_to_head_fixup.out)
    use_range = bool(rl) and float(rl[0]["level"]) < level5
    out.update(level=(float(rl[0]["level"]) if use_range else level5), level5=level5,
               level_source="range" if use_range else "five_day",
               vol_bar=VOL_X * v10, vol10=v10, vol50=v50,
               adr20=adr_d, pole_idx=int(P), pole_date=str(bars.dates[P]), pole_high=pole_high,
               prior_move=_f(prior), base_low=base_low)
    out["failed"] = [k for k in GATES if not g[k]["pass"]]
    if ENFORCED_SHAPE_GATES:                                 # empty today: no shape gate acts on the list
        sg = shape_gates(bars, D, P=int(P), adr20=adr_d)
        for k in ENFORCED_SHAPE_GATES:
            g[k] = sg[k]
            if not sg[k]["pass"]:
                out["failed"].append(k)
    out["ok"] = not out["failed"]
    return out


# ═══════════════════════════════════════════════════════════════════════════════════════════════
# 2b. The SHAPE gates (2026-11-11; pre-registered in docs/analysis/cb_shape_gates_2026-11-11.md)
# ═══════════════════════════════════════════════════════════════════════════════════════════════
# Qullamaggie's breakout shape — "higher lows", price "surfing" a RISING 10/20-day, "tightening" into the breakout
# (the article, operator_shared_notes L1936-1937; the operator's 2026-10-28 / 10-29 / 11-02 / 11-10 words) — each a
# list gate. Every constant below is fixed in the pre-registration BEFORE any score; the sources are cited there.
SHAPE_HL_RECENT = 5            # higher_lows: the base's bottom is older than the last 5 sessions (v1's 10-28 unit)
SHAPE_SWING_HALF = 2           # no_lower_low: a swing low = a 5-bar pivot (2 each side), wholly inside the base
SHAPE_LOWER_LOW_ADR = 1.0      # no_lower_low: ...that sits within 1.0 daily range above the bottom (the 10-28 "near" band)
SHAPE_RISING_SESSIONS = 5      # rising_avg: EMA10 and EMA21 both above their value 5 sessions earlier
SHAPE_EMA_FAST = 10
SHAPE_EXTENDED_ADR_MAX = 1.0   # not_extended: close no more than 1.0 daily range above the 10-day EMA (the 10-28 band)
SHAPE_TIGHT_ADR_MAX = 4.0      # tight10: the last 10 closes' spread no more than 4 daily ranges (11-02 table, 40/48 yes)
SHAPE_GATES = ("higher_lows", "no_lower_low", "rising_avg", "not_extended", "tight10")
# Amendment 2 (2026-11-11, round 2 — "stick with qullamaggie first"): four gates sized against Qullamaggie's own buys.
SHAPE_BASE_ABOVE_ADR_MAX = 0.0   # in_base: close no higher than the pole top (none of his 263 listed buys closed above it)
SHAPE_E21_S50_ADR_MIN = -1.0     # ema21_vs_sma50: the 21-day EMA no more than 1 daily range under the 50-day SMA
SHAPE_FALLING_WINDOWS = (5, 10, 20)   # ema21_not_falling: fails only when the EMA21 is lower than at ALL three
SHAPE_GATES_V2 = ("in_base", "ema21_not_falling", "ema21_vs_sma50", "low_not_today")
# Amendment 3 (2026-11-11, round 3): ONE trend-context gate on top of amendment 2 — four pre-declared variants.
SHAPE_SMA_LONG = 200
SHAPE_SMA200_RISING_SESSIONS = 20
SHAPE_TREND_GATES = ("above_200", "sma50_above_200", "sma200_rising", "above_rising_200")
# Amendment 4 (2026-11-11, round 4 — his "a few more tight days"): ONE tightness gate at the RIGHT EDGE, three variants.
SHAPE_RC_MAX = 1.1               # range_contract: mean range of D-4..D <= 1.1 x the mean of D-9..D-5 (his 10-28 "Yes")
SHAPE_C5_ADR_MAX = 1.5           # tight_closes5: the last 5 closes inside 1.5 daily ranges
SHAPE_TIGHT_RUN = 3              # tight_run3: the last 3 sessions each no wider than ...
SHAPE_TIGHT_RUN_X = 1.0          # ... 1.0 x ADR20 (a normal day), and each close within that of the one before
SHAPE_TIGHT_GATES = ("range_contract", "tight_closes5", "tight_run3")
# Which shape gates the LIST enforces. EMPTY = none: the list is exactly the seven signed-off rules. The 2026-11-11
# score FAILED its bar (first set 11/12 `no` but 6/16 of his good/ok kept; the revised set `("not_extended",
# "tight10")` 9/12 and 13/16 — SIG, ABCL, NVAX still pass), so nothing is enforced; a hard gate ships only on the
# operator's sign-off on the filter list (CHANGE_PROCESS rule 3) with the SSoT change-log entry in the same commit.
ENFORCED_SHAPE_GATES: tuple = ()


def ema_series(c: np.ndarray, D: int, span: int) -> Optional[np.ndarray]:
    """The `span`-session EMA of the closes for every session 0..D, seeded at the series' first bar (`ema_at`'s
    arithmetic: ema_series(c, D, n)[D] == ema_at(c, D, n)). None on a non-finite close."""
    x = np.asarray(c[:D + 1], dtype=float)
    if x.size == 0 or not np.isfinite(x).all():
        return None
    a = 2.0 / (span + 1)
    out = np.empty(x.size)
    out[0] = x[0]
    for i in range(1, x.size):
        out[i] = a * x[i] + (1.0 - a) * out[i - 1]
    return out


def shape_gates(bars: "cb.DailyBars", D: int, *, P: int, adr20: Optional[float]) -> dict:
    """The SHAPE gates at the watch night D — the first five (`SHAPE_GATES`) and amendment 2's four (`SHAPE_GATES_V2`:
    in_base = close(D) <= the pole top's high; ema21_not_falling = the EMA21 is NOT lower than 5, 10 AND 20 sessions
    earlier; ema21_vs_sma50 = (EMA21 / SMA50 - 1) / ADR20 >= -1.0; low_not_today = the base's lowest low is not made
    on D). The first five, at the watch night D (bars <= D only), pass AND value: {name: {"pass", "value"}}.
    `P` = the pole top `v1_gates` found (`pole_idx`); the base = the sessions P+1..D; `adr20` = ADR20 at D.

      higher_lows  B = the base's lowest low (first occurrence): B <= D-5, i.e. the lowest low of the last 5 sessions
                   D-4..D is STRICTLY above low(B) — the lows since the bottom sit above it.
      no_lower_low the bottom B is not a LOWER low against an earlier swing low of the same base: no session i in
                   [P+3, B-3] with low(i) <= every low of i-2..i+2 (a 5-bar pivot wholly inside the base) AND
                   low(i) <= low(B) x (1 + 1.0 x ADR20(D)). An earlier swing low within one daily range above the
                   bottom, then undercut (by any amount), is flat-to-lower lows — chop; one far above the bottom is a
                   pause on the way down to it, not a lower low.
      rising_avg   EMA10(D) > EMA10(D-5) AND EMA21(D) > EMA21(D-5) (strict) — the 10- and the 20-day both rising.
      not_extended (close(D) / EMA10(D) - 1) / ADR20(D) <= 1.0 — price near the average it surfs, not run away from it.
      tight10      (max close / min close - 1 over D-9..D) / ADR20(D) <= 4.0 — tight into the breakout (the list's own
                   `spread10_adr`, as `order_inputs`).
    A value that cannot be computed FAILS its gate (as `v1_gates`)."""
    l = np.asarray(bars.l, dtype=float)
    c = np.asarray(bars.c, dtype=float)
    adr = _f(adr20)
    adr_pos = adr is not None and adr > 0
    out: dict = {}
    B = P + 1 + int(np.argmin(l[P + 1:D + 1]))               # first occurrence of the base's lowest low
    recent_low = float(l[D - SHAPE_HL_RECENT + 1:D + 1].min())
    out["higher_lows"] = {"pass": bool(B <= D - SHAPE_HL_RECENT and recent_low > float(l[B])),
                          "value": {"bottom_date": str(bars.dates[B]), "bottom_low": float(l[B]),
                                    "sessions_since_bottom": D - B, "recent_low": recent_low}}
    k = SHAPE_SWING_HALF
    near = float(l[B]) * (1.0 + SHAPE_LOWER_LOW_ADR * adr) if adr_pos else None
    earlier = [i for i in range(P + 1 + k, B - k) if l[i] <= l[i - k:i + k + 1].min()]
    undercut = [i for i in earlier if near is not None and l[i] <= near]
    out["no_lower_low"] = {"pass": bool(near is not None and not undercut),
                           "value": {"undercut_swing_lows": [[str(bars.dates[i]), float(l[i])] for i in undercut],
                                     "earlier_swing_lows": [[str(bars.dates[i]), float(l[i])] for i in earlier],
                                     "near_band_top": _f(near)}}
    e10 = ema_series(c, D, SHAPE_EMA_FAST)
    e21 = ema_series(c, D, EMA_SPAN)
    n = SHAPE_RISING_SESSIONS
    ok_e = e10 is not None and e21 is not None and D - n >= 0
    out["rising_avg"] = {"pass": bool(ok_e and e10[D] > e10[D - n] and e21[D] > e21[D - n]),
                         "value": {"ema10": _f(e10[D]) if ok_e else None, "ema10_prev": _f(e10[D - n]) if ok_e else None,
                                   "ema21": _f(e21[D]) if ok_e else None, "ema21_prev": _f(e21[D - n]) if ok_e else None}}
    ext = _f((float(c[D]) / float(e10[D]) - 1.0) / adr) if (ok_e and adr_pos and e10[D] > 0) else None
    out["not_extended"] = {"pass": bool(ext is not None and ext <= SHAPE_EXTENDED_ADR_MAX),
                           "value": {"close_vs_ema10_adr": ext, "max": SHAPE_EXTENDED_ADR_MAX}}
    # ── amendment 2 (2026-11-11): the four gates sized against Qullamaggie's own buys ──
    pole_high = float(bars.h[P])
    above = _f((float(c[D]) / pole_high - 1.0) / adr) if (adr_pos and pole_high > 0) else None
    out["in_base"] = {"pass": bool(above is not None and above <= SHAPE_BASE_ABOVE_ADR_MAX),
                      "value": {"close_vs_pole_high_adr": above, "max": SHAPE_BASE_ABOVE_ADR_MAX}}
    wins = [w for w in SHAPE_FALLING_WINDOWS if D - w >= 0]
    full = e21 is not None and len(wins) == len(SHAPE_FALLING_WINDOWS)
    falling = bool(full and all(e21[D] < e21[D - w] for w in wins))
    out["ema21_not_falling"] = {"pass": bool(full and not falling),
                                "value": {"ema21": _f(e21[D]) if e21 is not None else None,
                                          "ema21_before": {str(w): _f(e21[D - w]) for w in wins} if e21 is not None else None}}
    s50 = cb._sma_at(bars, D, SMA_SESSIONS)
    stack = (_f((float(e21[D]) / float(s50) - 1.0) / adr)
             if (e21 is not None and adr_pos and s50 is not None and math.isfinite(s50) and s50 > 0) else None)
    out["ema21_vs_sma50"] = {"pass": bool(stack is not None and stack >= SHAPE_E21_S50_ADR_MIN),
                             "value": {"ema21_vs_sma50_adr": stack, "min": SHAPE_E21_S50_ADR_MIN}}
    out["low_not_today"] = {"pass": bool(B < D), "value": {"sessions_since_bottom": D - B}}
    # ── amendment 3: the trend-context variants. A 200-day that does not EXIST yet (a young listing) does not fail:
    #    the gate reads a falling long-term trend, and a stock with no 200-day has none to read. ──
    s200 = cb._sma_at(bars, D, SHAPE_SMA_LONG)
    s200p = cb._sma_at(bars, D - SHAPE_SMA200_RISING_SESSIONS, SHAPE_SMA_LONG) if D - SHAPE_SMA200_RISING_SESSIONS >= 0 else None
    above = None if s200 is None else bool(float(c[D]) >= s200)
    stacked = None if (s200 is None or s50 is None) else bool(s50 >= s200)
    rising = None if (s200 is None or s200p is None) else bool(s200 > s200p)
    tv = {"sma200": _f(s200), "sma200_prev": _f(s200p), "sma50": _f(s50), "close": _f(c[D])}
    out["above_200"] = {"pass": above is not False, "value": tv}
    out["sma50_above_200"] = {"pass": stacked is not False, "value": tv}
    out["sma200_rising"] = {"pass": rising is not False, "value": tv}
    out["above_rising_200"] = {"pass": above is not False and rising is not False, "value": tv}
    # ── amendment 4: tightness at the right edge ("a few more tight days") ──
    hh = np.asarray(bars.h, dtype=float)
    with np.errstate(invalid="ignore", divide="ignore"):
        rng = (hh - l) / c
    r_last, r_prev = float(rng[D - 4:D + 1].mean()), float(rng[D - 9:D - 4].mean())
    rc = _f(r_last / r_prev) if r_prev > 0 else None
    out["range_contract"] = {"pass": bool(rc is not None and rc <= SHAPE_RC_MAX), "value": {"range5_over_prev5": rc}}
    c5 = _f((float(c[D - 4:D + 1].max()) / float(c[D - 4:D + 1].min()) - 1.0) / adr) if adr_pos else None
    out["tight_closes5"] = {"pass": bool(c5 is not None and c5 <= SHAPE_C5_ADR_MAX), "value": {"spread5_adr": c5}}
    run = 0
    if adr_pos:
        for i in range(D, 0, -1):
            if rng[i] <= SHAPE_TIGHT_RUN_X * adr and abs(c[i] / c[i - 1] - 1.0) <= SHAPE_TIGHT_RUN_X * adr:
                run += 1
            else:
                break
    out["tight_run3"] = {"pass": bool(run >= SHAPE_TIGHT_RUN), "value": {"tight_days_in_a_row": run}}
    sp = order_inputs(bars, D, adr)["spread10_adr"] if adr_pos else None
    out["tight10"] = {"pass": bool(sp is not None and sp <= SHAPE_TIGHT_ADR_MAX),
                      "value": {"spread10_adr": sp, "max": SHAPE_TIGHT_ADR_MAX}}
    return out


def runup6m_at(bars: "cb.DailyBars", D: int) -> Optional[float]:
    """The 6-month move at D (spec §2; `23_move126_rule.py` / `stage0/s0_lib.bar_features`): the biggest gain from a
    low to a LATER-or-same high inside the 126 sessions ending D, the low no more than 63 sessions before the high —
    max over j in [D-125, D] of high(j) / min(low[j-63 .. j]) - 1, each window clipped at the first bar (the
    research's rolling(..., min_periods=1)). Bars <= D only. None when no window has a finite positive low."""
    h = np.asarray(bars.h[:D + 1], dtype=float)
    lo = np.asarray(bars.l[:D + 1], dtype=float)
    best: Optional[float] = None
    for j in range(max(0, D - RUNUP6M_SESSIONS + 1), D + 1):
        w = lo[max(0, j - RUNUP6M_LOW_SESSIONS):j + 1]
        w = w[np.isfinite(w)]
        if not w.size or not math.isfinite(h[j]):
            continue
        m_low = float(w.min())
        if m_low <= 0:
            continue
        m = float(h[j]) / m_low - 1.0
        if best is None or m > best:
            best = m
    return best


def order_inputs(bars: "cb.DailyBars", D: int, adr20: Optional[float]) -> dict:
    """The two per-name inputs of the night's ORDER SCORE (spec §2), bars <= D, `adr20` = ADR20 at D (`v1_gates`):
    {"runup6m": the 6-month move (a fraction), "runup6m_adr": it in daily ranges (bigger ranks first),
     "spread10_adr": (max close / min close - 1) / ADR20 over the 10 sessions D-9..D (tighter ranks first)}.
    A value that cannot be computed is None (the name is ranked after every scored name). The ranking itself is
    over the night's whole passing list: `breakout_v1_list.rank_rows`."""
    adr = _f(adr20)
    mv = runup6m_at(bars, D)
    out = {"runup6m": _f(mv), "runup6m_adr": None, "spread10_adr": None}
    if adr is None or adr <= 0:
        return out
    if mv is not None:
        out["runup6m_adr"] = _f(mv / adr)
    if D - SPREAD_SESSIONS + 1 >= 0:
        cw = np.asarray(bars.c[D - SPREAD_SESSIONS + 1:D + 1], dtype=float)
        if np.isfinite(cw).all() and float(cw.min()) > 0:
            out["spread10_adr"] = _f((float(cw.max()) / float(cw.min()) - 1.0) / adr)
    return out


def _bar_get(bar: Mapping, *keys):
    for k in keys:
        if k in bar and bar[k] is not None:
            return float(bar[k])
    return None


def breakout_triggered(bar_E: Mapping, gates: dict) -> dict:
    """The breakout on E = D + 1 for the night-D result `gates` (`v1_gates`): high(E) > level (strict) and
    volume(E) >= the volume bar (1.2x the mean volume of the last 10 sessions to D, inclusive; his ruling 2026-11-02). `bar_E` carries the session's high and
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
