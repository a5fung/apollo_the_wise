#!/usr/bin/env python3
"""#519 FREE STEP — which of HIS chart reasons can be measured from daily bars for $0, and how
well does each separate the dates he condemned from the dates he approved and from real EPs?
(READ-ONLY · $0 · MEASUREMENT ONLY. Wired into nothing. Changes no rule, threshold, toggle or
trade state. Operator ruling 2026-09-23: build the free step first, HOLD the ~$190 paid vision
run until this is scored. Any promotion is his fork — THE LINE.)

INPUT — captured ONCE, read many
--------------------------------
`scratchpad/519/bars.psv`: daily bars from prod `mi_daily_closes` for every ticker named by
`tests/fixtures/must_not_trade_charts.py` + `tests/fixtures/must_not_miss_eps.py` (63 tickers,
derived from the fixtures, not hand-listed; SQL in `scratchpad/519/bars.sql`). History starts
2025-08-18, so NOTHING here sees more than ~13 months. Every row reports `n_prior_sessions`.

NO LOOKAHEAD — every measure reads prior bars plus the alert-day OPEN, exactly like v2/v3.
The OPEN is the daily open in `mi_daily_closes` — the same basis as the 09-21 and 09-23
scorings. ⚠ The fixtures' own `gap_open_pct` for review samples #1/#2 is the scan-log's
alert-tick read (`_594_review_sample.py` reads `gap_pct` / MAX(gap_pct) from mi_ep_scan_log),
so it differs from the daily-open gap on 15 rows by 1-16pp. That is a BASIS difference, not a
population error; the tickers and dates line up bar for bar.

REUSED, NOT RE-IMPLEMENTED (P15)
--------------------------------
`_structure_read_v3.structure_read_v3` supplies the supply-ladder read (overhead_vol_frac,
zones_cleared/remaining, label, base_range_adr, rmv_15), the run-up family (runup_low_pct_n,
runup_adr_n, pct_of_captured_range) and the live extension replica. `V2.overhead_volume_fraction`
is re-called on a FIXED 120-session window so the cross-population table compares like with like
(real EPs are Mar–May alerts with ~140–180 prior sessions; his rulings are Jun–Aug with ~200–250;
a full-history number is not comparable across those).

🔴 PRE-DECLARED, BEFORE ANY NUMBER WAS SEEN (this docstring is the declaration — nothing here
gets committed, so it is the only evidence the rules came first)
------------------------------------------------------------------------------------------------
WINDOWS, fixed once: MA 10/20/50/200 · volume 10-vs-50 and up-vs-down over 20 · prior highs at
20/60/120 sessions and all captured history · trend at 60/120 · base depth bands 15% (the books'
FLAT base) and 35% (O'Neil's typical cup-depth ceiling). No window is re-picked after looking.

RULES evaluated AS RULES — each taken from his words or the books, each reported RULE 0 FIRST
(how many of the 30 real EPs and how many of his 9 approved dates it would reject):
  R1  base_len_35 < 25 sessions      — TraderLion/DOCU: "at a bare minimum at least 5 weeks for
                                        a flat base and 7 weeks for any other base". 5 wk = 25
                                        sessions is the MORE permissive floor, used on purpose.
  R2  open <= SMA50                  — BW: "still below 50d"; WYFI: "didn't clear ... nor 50d".
  R3  open < 60-session prior high   — "didn't clear local highs" (WYFI), "bumping into recent
                                        highs" (MRVI), "didn't clear the left side" (FRMI, BW).
  R4  up-day vol <= down-day vol, 20 — TraderLion/CRWD: "Volume on Up Days bigger than Volume
                                        on Down Days".
  R5  prior close <= SMA200          — RARE "stuck in multi year downtrend", MRLN "in downtrend":
                                        the nearest thing our 13 months can say. n/a when fewer
                                        than 200 prior sessions exist — n/a is NEVER a pass or a
                                        fail (the 09-21 unreadable rule).
  R6  vol10 / vol50 >= 1.0           — books: "consolidation on below-average volume", "volume
                                        dry up". Rejects a base that is NOT quiet.
  R7  runup_low_pct_20 >= 75         — ANCHOR-75, the rule already scored on 09-21/09-23, kept
                                        as the comparator. (⚠ the LIVE MAX_EXTENSION_PCT is
                                        50.0 since 08-29; v3's docstring still says 75. Flagged,
                                        not fixed here.)
NO cutline search. NO union of rules is scored as a rule; if one is shown it is labelled post-hoc.

BASE LENGTH — declared here, not tuned:
  base_len_35 / base_len_15  — the longest trailing run of prior sessions whose closes stay within
                               a 35% / 15% band (max/min − 1). Counts the consolidation the books
                               call a base, from wherever it started.
  left_high_age              — sessions since price last TRADED at or above the prior close
                               (excluding the prior session itself). ⚠ DEGENERATE — the first
                               run gave a median of 1 in every population (inside any range the
                               level is re-touched constantly). Kept in the output so the
                               failure is visible; no rule and no separation number uses it.
  pivot_age_120              — ADDED AFTER THE FIRST RUN to replace it (disclosed): sessions
                               since the highest high of the last 120 prior sessions — the
                               books' left-side high, in sessions. Descriptive only; no rule
                               was declared on it and none is evaluated.
  open_level_age             — sessions since price last traded at or above the gap OPEN. None
                               when the open clears every captured prior high ("cleared the
                               left side" entirely, within 13 months).
MRNA (his reference EP, base annotated at 74 sessions) is printed for all — disclosed, not tuned.

SEPARATION — one threshold-free number per measure: AUC = the chance that a randomly drawn
condemned date sits on the BAD side of a randomly drawn approved date (0.5 = no separation,
1.0 = perfect). The bad side is declared per measure from his words / the books (`DIRECTION`).
Noise floor stated in the doc: at 21 vs 9 a null AUC has a standard error near 0.12, so
0.30-0.70 is indistinguishable from chance; at 12 vs 9 near 0.13.

DATA ARTIFACTS — `mi_daily_closes` is unadjusted and carries scale defects. A bar is an
ARTIFACT day when (a) its own open/close ratio is > 2.5 or < 0.4 (the first ten rows of CRWG,
VEEE, TDIC carry OHL on one scale and close on another), or (b) open/prev_close is > 2.5 or
< 0.4 AND the day's volume is below the prior-20 median or under 1,000 shares (GDC 2025-10-22
4.41 -> 1105 on 248 shares; QH 2025-11-10 and 2026-05-29). A real 3x move (OMER 2025-10-15 on
125M shares, QURE 2025-09-24 on 70M) is NOT an artifact. Any window that reaches back past the
last artifact day is n/a for that row — never a pass, never a fail — and full-history fields
are n/a whenever any artifact precedes the alert.
"""
from __future__ import annotations

import statistics as st
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
for p in (str(REPO), str(REPO / "scripts" / "probes")):
    if p not in sys.path:
        sys.path.insert(0, p)

import _structure_read_v2 as V2  # noqa: E402
import _structure_read_v3 as V3  # noqa: E402

from tests.fixtures.must_not_miss_eps import MUST_NOT_MISS  # noqa: E402
from tests.fixtures.must_not_trade_charts import (  # noqa: E402
    CHART_RULINGS, MUST_NOT_REJECT_DATES, MUST_NOT_TRADE, NO_SETUP_ON_THIS_DATE,
    POINTED_AT_DATES, WRONG_DAY, WRONG_STAGE)

SCRATCH = Path("/private/tmp/claude-501/-Users-alvinfung-apollo-the-wise/"
               "d30e3944-e07e-4b44-97de-010acba78d0b/scratchpad/519")
BARS_PSV = SCRATCH / "bars.psv"
READS_PSV = SCRATCH / "reads.psv"

# ── fixed windows (declared once) ─────────────────────────────────────────────────────
MA_WINDOWS = (10, 20, 50, 200)
HIGH_WINDOWS = (20, 60, 120)
TREND_WINDOWS = (60, 120)
VOL_SHORT, VOL_LONG, UPDOWN_WIN = 10, 50, 20
FIXED_WIN = 120
BASE_BANDS = {"base_len_15": 0.15, "base_len_35": 0.35}
BOOK_BASE_MIN_SESSIONS = 25          # 5 weeks × 5
PIVOT_MIN_CLEAN = 20                 # pivot_age_120 needs at least this much clean history

# ── bars ──────────────────────────────────────────────────────────────────────────────
_BARS: dict[str, list[dict]] = defaultdict(list)
_ARTIFACT_DAYS: dict[str, list[date]] = defaultdict(list)


def detect_artifact_days(bs: list[dict]) -> list[date]:
    """Scale-defect artifact days for ONE ticker's bars (ascending by trade_date, each carrying
    at least open_price/close/volume/trade_date). See the module docstring's 'DATA ARTIFACTS'
    section for the rule. Pure function — factored out of `_load_bars` (2026-09-24, #519 option
    A) so the paid-run probe (`scripts/probes/_519_option_a.py`) can reuse the IDENTICAL rule
    against freshly DB-fetched bars, not only this module's captured PSV. Behaviour is
    UNCHANGED from the inline loop it replaces — same inputs give the same artifact-day list."""
    out: list[date] = []
    for i, b in enumerate(bs):
        r_row = b["open_price"] / b["close"] if b["close"] else 1.0
        if r_row > 2.5 or r_row < 0.4:
            out.append(b["trade_date"])
            continue
        if i == 0:
            continue
        pc = bs[i - 1]["close"]
        r = b["open_price"] / pc if pc else 1.0
        if r > 2.5 or r < 0.4:
            med = st.median(x["volume"] for x in bs[max(0, i - 20):i])
            if b["volume"] < med or b["volume"] < 1000:
                out.append(b["trade_date"])
    return out


def clean_len_for(prior: list[dict], artifact_days: list[date]) -> int:
    """Number of `prior` sessions (ascending, each carrying trade_date) AFTER the last artifact
    day at or before the last prior session — the usable window. Pure (no module-level ticker
    lookup), factored out of `_clean_len` (2026-09-24, #519 option A) for the same reuse reason
    as `detect_artifact_days`: a caller fetching bars fresh from the DB has no entry in this
    module's `_ARTIFACT_DAYS` dict to key off of. `_clean_len` below is now a thin wrapper and
    its own behaviour is unchanged."""
    if not prior:
        return 0
    arts = [d for d in artifact_days if d <= prior[-1]["trade_date"]]
    if not arts:
        return len(prior)
    last = max(arts)
    return sum(1 for b in prior if b["trade_date"] > last)


def _load_bars() -> None:
    for ln in BARS_PSV.read_text().splitlines():
        if not ln.strip():
            continue
        tk, d, o, h, l, c, v = ln.split("|")
        y, m, dd = d.split("-")
        _BARS[tk].append({"trade_date": date(int(y), int(m), int(dd)),
                          "open_price": float(o), "high_price": float(h),
                          "low_price": float(l), "close": float(c),
                          "volume": float(v) if v else 0.0})
    for t in _BARS:
        _BARS[t].sort(key=lambda b: b["trade_date"])
        arts = detect_artifact_days(_BARS[t])
        if arts:  # preserves the pre-refactor defaultdict-on-append behaviour: a ticker with
            _ARTIFACT_DAYS[t] = arts  # zero artifacts never gets a key (the diagnostic print
            # below iterates _ARTIFACT_DAYS.items(), so an unconditional assign would have
            # listed every clean ticker as "[]" — a display change this refactor must not make).


def _split(ticker: str, iso: str):
    y, m, d = iso.split("-")
    ad = date(int(y), int(m), int(d))
    allb = _BARS.get(ticker) or []
    prior = [b for b in allb if b["trade_date"] < ad]
    on = [b for b in allb if b["trade_date"] == ad]
    return ad, prior, (on[0] if on else None)


def _clean_len(ticker: str, prior: list[dict]) -> int:
    """Number of prior sessions AFTER the last artifact day (= the usable window)."""
    return clean_len_for(prior, _ARTIFACT_DAYS.get(ticker, []))


# ── the new measures ──────────────────────────────────────────────────────────────────
def _sma(closes: list[float], n: int) -> float | None:
    return st.fmean(closes[-n:]) if len(closes) >= n else None


def base_len(closes: list[float], band: float) -> int:
    lo = hi = closes[-1]
    n = 0
    for c in reversed(closes):
        lo, hi = min(lo, c), max(hi, c)
        if hi / lo - 1 > band:
            break
        n += 1
    return n


def age_since_traded_at(bars: list[dict], px: float, exclude_last: bool) -> int | None:
    for i in range(len(bars) - (2 if exclude_last else 1), -1, -1):
        if bars[i]["high_price"] >= px:
            return len(bars) - 1 - i
    return None


def measures(ticker: str, prior: list[dict], ad: date, open_px: float) -> dict:
    out = V3.structure_read_v3(prior, ad, open_px)
    clean = _clean_len(ticker, prior)
    any_art = clean < len(prior)
    out["n_prior_sessions"] = len(prior)
    out["clean_sessions"] = clean
    out["artifact_in_history"] = any_art

    def ok(w: int) -> bool:
        return clean >= w

    closes = [b["close"] for b in prior]
    highs = [b["high_price"] for b in prior]
    vols = [b["volume"] for b in prior]
    pc = closes[-1]
    out["gap_open_pct_bars"] = (open_px / pc - 1) * 100.0
    adr = out.get("adr20_pct") if ok(20) else None
    out["adr20_pct"] = adr
    out["gap_adr"] = (out["gap_open_pct_bars"] / adr) if adr else None

    # full-history fields from v2/v3 are n/a when an artifact precedes the alert
    for k in ("overhead_vol_frac", "zones_cleared", "zones_remaining", "label",
              "pct_of_captured_range", "overhead_vol_frac_at_prior_close"):
        if any_art:
            out[k] = None
    for n in V3.RUNUP_WINDOWS:
        if not ok(n):
            for k in ("ext_close_pct", "runup_low_pct", "runup_adr"):
                out[f"{k}_{n}"] = None
    if not ok(15):
        out["base_range_adr"] = None
        out["rmv_15"] = None
    ext_win = [b for b in prior if b["trade_date"] >= ad - __import__("datetime").timedelta(days=V3.LIVE_EXT_WINDOW_DAYS)]
    if any(b["trade_date"] in set(_ARTIFACT_DAYS.get(ticker, [])) for b in ext_win) or clean < len(ext_win):
        out["extension_live_pct"] = None

    # base length (the run itself stops at any 2.5x jump, so it needs no artifact guard)
    for k, band in BASE_BANDS.items():
        out[k] = min(base_len(closes, band), clean)
    lha = age_since_traded_at(prior, pc, exclude_last=True)
    out["left_high_age"] = None if any_art else (lha if lha is not None else len(prior))
    out["left_high_age_capped"] = (not any_art) and lha is None
    ola = age_since_traded_at(prior, open_px, exclude_last=False)
    out["open_level_age"] = None if any_art else ola
    out["open_clears_all_history"] = None if any_art else (ola is None)
    w = min(FIXED_WIN, clean)
    if w >= PIVOT_MIN_CLEAN:
        hw = highs[-w:]
        out["pivot_age_120"] = (w - 1) - max(range(w), key=lambda i: hw[i])
        out["pivot_window"] = w
    else:
        out["pivot_age_120"] = None
        out["pivot_window"] = w

    # moving averages
    n_avail = n_close_above = n_open_above = 0
    smas = {}
    for n in MA_WINDOWS:
        s = _sma(closes, n) if ok(n) else None
        smas[n] = s
        out[f"sma{n}_avail"] = s is not None
        out[f"close_vs_sma{n}_pct"] = (pc / s - 1) * 100.0 if s else None
        out[f"open_vs_sma{n}_pct"] = (open_px / s - 1) * 100.0 if s else None
        if s:
            n_avail += 1
            n_close_above += pc > s
            n_open_above += open_px > s
    out["mas_avail"] = n_avail
    out["mas_close_above"] = n_close_above if n_avail else None
    out["mas_open_above"] = n_open_above if n_avail else None
    out["open_above_all_avail_mas"] = (n_open_above == n_avail) if n_avail else None
    s50, s200 = smas[50], smas[200]
    out["open_above_sma50"] = (open_px > s50) if s50 else None
    out["close_above_sma200"] = (pc > s200) if s200 else None
    s50_prev = _sma(closes[:-20], 50) if ok(70) else None
    out["sma50_slope_20_pct"] = (s50 / s50_prev - 1) * 100.0 if (s50 and s50_prev) else None

    # volume
    if ok(VOL_LONG) and st.fmean(vols[-VOL_LONG:]) > 0:
        out["vol_dryup_10_50"] = st.fmean(vols[-VOL_SHORT:]) / st.fmean(vols[-VOL_LONG:])
    else:
        out["vol_dryup_10_50"] = None
    if ok(UPDOWN_WIN + 1):
        win = prior[-(UPDOWN_WIN + 1):]
        up = sum(b["volume"] for a, b in zip(win, win[1:]) if b["close"] > a["close"])
        dn = sum(b["volume"] for a, b in zip(win, win[1:]) if b["close"] < a["close"])
        out["updown_vol_20"] = (up / dn) if dn > 0 else None
    else:
        out["updown_vol_20"] = None

    # clears prior highs
    for n in HIGH_WINDOWS:
        out[f"open_vs_high{n}_pct"] = (open_px / max(highs[-n:]) - 1) * 100.0 if ok(n) else None
    out["open_vs_histhigh_pct"] = None if any_art else (open_px / max(highs) - 1) * 100.0
    out["overhead_vol_frac_120"] = (V2.overhead_volume_fraction(prior[-FIXED_WIN:], open_px)
                                    if ok(FIXED_WIN) else None)

    # long trend, limited to captured history
    for n in TREND_WINDOWS:
        out[f"trend_{n}_pct"] = (pc / closes[-n - 1] - 1) * 100.0 if ok(n + 1) else None
    if ok(FIXED_WIN):
        wb = prior[-FIXED_WIN:]
        hi, lo = max(b["high_price"] for b in wb), min(b["low_price"] for b in wb)
        out["pct_of_range_120"] = (pc - lo) / (hi - lo) if hi > lo else None
    else:
        out["pct_of_range_120"] = None

    # the pre-declared rules — True = REJECT, None = cannot evaluate
    out["R1_base_short"] = (out["base_len_35"] < BOOK_BASE_MIN_SESSIONS) if ok(BOOK_BASE_MIN_SESSIONS) else None
    out["R2_open_below_50"] = (not out["open_above_sma50"]) if s50 else None
    h60 = out["open_vs_high60_pct"]
    out["R3_open_below_high60"] = (h60 < 0) if h60 is not None else None
    ud = out["updown_vol_20"]
    out["R4_down_vol_dominates"] = (ud <= 1.0) if ud is not None else None
    out["R5_close_below_200"] = (not out["close_above_sma200"]) if s200 else None
    vd = out["vol_dryup_10_50"]
    out["R6_no_dryup"] = (vd >= 1.0) if vd is not None else None
    out["R7_anchor75"] = V3.anchor75_rejects(out)
    return out


RULES = ["R1_base_short", "R2_open_below_50", "R3_open_below_high60", "R4_down_vol_dominates",
         "R5_close_below_200", "R6_no_dryup", "R7_anchor75"]
RULE_TEXT = {
    "R1_base_short": "base shorter than 5 weeks (25 sessions, 35% band) — the books' floor",
    "R2_open_below_50": "gap opens at or below the 50-day — his 'still below 50d'",
    "R3_open_below_high60": "gap opens below the 60-session high — 'didn't clear local highs'",
    "R4_down_vol_dominates": "down-day volume >= up-day volume over 20 sessions — the books",
    "R5_close_below_200": "prior close at or below the 200-day — the nearest 'downtrend' read",
    "R6_no_dryup": "last 10 sessions' volume >= 50-session average — no dry-up in the base",
    "R7_anchor75": "run-up from the 20-session low >= 75% — ANCHOR-75, the comparator",
}

# bad side per measure, declared from his words / the books: "low" = a LOWER value is the bad side
DIRECTION = {
    "base_len_35": "low", "base_len_15": "low", "pivot_age_120": "low",
    "mas_open_above": "low", "updown_vol_20": "low", "vol_dryup_10_50": "high",
    "open_vs_high60_pct": "low", "open_vs_high120_pct": "low", "overhead_vol_frac_120": "high",
    "zones_remaining": "high", "zones_cleared": "low",
    "runup_low_pct_10": "high", "runup_low_pct_20": "high", "runup_adr_10": "high",
    "gap_adr": "low", "trend_120_pct": "low", "base_range_adr": "high",
}

# ── his reasons, tagged to measurable concepts (read off the words, per ruling) ────────
CONCEPTS = {
    "CLEARS_LEFT_SIDE": "did the gap clear prior highs / the left side / local highs",
    "MULTI_YEAR": "structure older than our bars (a 2022 base, an Oct-2025 double top, 'multi year')",
    "TREND": "prior trend up or down",
    "MA_POSITION": "above/below the 10/20/50/200-day",
    "BASE": "a base exists / is long / still in base / bottoming base",
    "GAP_STRENGTH": "the gap itself weak, absent, or 'chopping in range'",
    "RECENT_GAP_DOWN": "a gap down just before the gap up",
    "CLOSE_IN_RANGE": "where the alert day CLOSED in its range",
    "HOLDS_AFTER": "what happened in the sessions after the gap",
    "PRIOR_RUNUP": "already up a lot before the gap (the session-1 charts)",
    "NO_WORDS": "no per-name words recorded",
}
MEASURABLE = {
    "CLEARS_LEFT_SIDE": "yes, within 13 months — open vs the 20/60/120-session high, zones cleared/remaining, overhead volume share",
    "MULTI_YEAR": "NO — bars start 2025-08-18",
    "TREND": "partly — 60/120-session change, 50-day slope, close vs 200-day (200-day only for alerts after ~2026-06-04)",
    "MA_POSITION": "yes — open/close vs the 10/20/50-day (200-day where available)",
    "BASE": "yes, within 13 months — base_len_15/35, pivot_age_120",
    "GAP_STRENGTH": "yes — gap % and gap in ADR units",
    "RECENT_GAP_DOWN": "yes — v2 gap zones",
    "CLOSE_IN_RANGE": "computable but NOT at admission (reads the alert-day close)",
    "HOLDS_AFTER": "computable but NOT at admission (reads later sessions)",
    "PRIOR_RUNUP": "yes — run-up from the 5/10/20-session low, the live extension replica",
    "NO_WORDS": "—",
}
TAGS = {
    ("NVTX", "2026-06-03"): ["CLEARS_LEFT_SIDE", "MULTI_YEAR", "HOLDS_AFTER"],
    ("NVTS", "2026-06-03"): ["CLOSE_IN_RANGE", "HOLDS_AFTER"],
    ("MRLN", "2026-06-05"): ["TREND", "CLEARS_LEFT_SIDE"],
    ("AVGU", "2026-06-02"): ["NO_WORDS"],
    ("CRWG", "2026-06-01"): ["NO_WORDS"],
    ("ABVX", "2026-06-03"): ["NO_WORDS"],
    ("CGEM", "2026-06-08"): ["NO_WORDS"],
    ("AVAH", "2026-06-02"): ["NO_WORDS"],
    ("OMER", "2026-07-27"): ["CLEARS_LEFT_SIDE", "BASE", "MA_POSITION", "HOLDS_AFTER"],
    ("RNG", "2026-07-24"): ["BASE", "MULTI_YEAR", "CLEARS_LEFT_SIDE", "CLOSE_IN_RANGE", "MA_POSITION", "HOLDS_AFTER"],
    ("GDC", "2026-05-06"): ["PRIOR_RUNUP"], ("CAR", "2026-04-22"): ["PRIOR_RUNUP"],
    ("CAR", "2026-04-21"): ["PRIOR_RUNUP"], ("ADVB", "2026-07-24"): ["PRIOR_RUNUP"],
    ("JLHL", "2026-06-08"): ["PRIOR_RUNUP"], ("IPCX", "2026-07-29"): ["NO_WORDS"],
    ("QH", "2026-06-18"): ["PRIOR_RUNUP"], ("MRAM", "2026-05-13"): ["PRIOR_RUNUP"],
    ("YOU", "2026-08-05"): ["NO_WORDS"], ("AEHR", "2026-08-14"): ["PRIOR_RUNUP"],
    ("QTTB", "2026-07-13"): ["NO_WORDS"],
    ("CAR", "2026-04-01"): ["PRIOR_RUNUP"],
    ("ARQQ", "2026-06-15"): ["BASE"],
    ("MXL", "2026-04-21"): ["BASE"],
    ("VEEE", "2026-07-08"): ["GAP_STRENGTH"],
    ("RARE", "2026-08-20"): ["MULTI_YEAR", "TREND", "RECENT_GAP_DOWN", "CLEARS_LEFT_SIDE"],
    ("BW", "2026-08-11"): ["GAP_STRENGTH", "CLEARS_LEFT_SIDE", "MA_POSITION"],
    ("LPTH", "2026-08-14"): ["GAP_STRENGTH"],
    ("WYFI", "2026-08-12"): ["GAP_STRENGTH", "CLEARS_LEFT_SIDE", "MA_POSITION"],
    ("FRMI", "2026-08-11"): ["CLEARS_LEFT_SIDE"],
    ("AVAH", "2026-08-13"): ["CLEARS_LEFT_SIDE", "BASE"],
    ("NIQ", "2026-08-11"): ["BASE", "CLEARS_LEFT_SIDE"],
    ("TBBB", "2026-08-13"): ["NO_WORDS"],
    ("MRVI", "2026-08-19"): ["CLEARS_LEFT_SIDE"],
    ("HAE", "2026-08-18"): ["NO_WORDS"],
}


def populations() -> dict[str, list[tuple[str, str, str]]]:
    assertable = [m for m in MUST_NOT_MISS if not getattr(m, "excluded", False)]
    return {
        "REAL_EP": [(m.ticker, m.alert_date, "REAL_EP") for m in assertable],
        "APPROVED": [(t, d, v) for t, d, v in MUST_NOT_REJECT_DATES],
        "BAD_CHART": [(r.ticker, r.alert_date, r.verdict) for r in MUST_NOT_TRADE],
        "OTHER_REJECTED": [(r.ticker, r.alert_date, r.verdict) for r in CHART_RULINGS
                           if r.verdict in (WRONG_DAY, WRONG_STAGE)],
        "DATA_DEFECT": [(r.ticker, r.alert_date, r.verdict) for r in CHART_RULINGS
                        if r.verdict == NO_SETUP_ON_THIS_DATE],
        "POINTED_AT": [(t, d, v) for t, d, v in POINTED_AT_DATES],
    }


FIELDS = [
    "n_prior_sessions", "clean_sessions", "artifact_in_history", "gap_open_pct_bars", "gap_adr",
    "adr20_pct", "base_len_15", "base_len_35", "left_high_age", "left_high_age_capped",
    "pivot_age_120", "pivot_window", "open_level_age", "open_clears_all_history",
    "close_vs_sma10_pct", "close_vs_sma20_pct", "close_vs_sma50_pct", "close_vs_sma200_pct",
    "open_vs_sma10_pct", "open_vs_sma20_pct", "open_vs_sma50_pct", "open_vs_sma200_pct",
    "mas_avail", "mas_close_above", "mas_open_above", "open_above_all_avail_mas",
    "open_above_sma50", "close_above_sma200", "sma50_slope_20_pct",
    "vol_dryup_10_50", "updown_vol_20",
    "open_vs_high20_pct", "open_vs_high60_pct", "open_vs_high120_pct", "open_vs_histhigh_pct",
    "overhead_vol_frac", "overhead_vol_frac_120", "zones_cleared", "zones_remaining", "label",
    "trend_60_pct", "trend_120_pct", "pct_of_range_120", "pct_of_captured_range",
    "runup_low_pct_5", "runup_low_pct_10", "runup_low_pct_20", "runup_adr_10",
    "extension_live_pct", "base_range_adr", "rmv_15",
] + RULES


def _fmt(v):
    if v is None:
        return ""
    if isinstance(v, bool):
        return "T" if v else "F"
    if isinstance(v, float):
        return f"{v:.3f}"
    return str(v)


def fixture_gap(tk: str, d: str) -> float | None:
    for r in CHART_RULINGS:
        if (r.ticker, r.alert_date) == (tk, d) and r.gap_open_pct is not None:
            return r.gap_open_pct
    for m in MUST_NOT_MISS:
        if (m.ticker, m.alert_date) == (tk, d):
            return m.gap_pct
    return None


def auc(bad: list[float], good: list[float], direction: str) -> float | None:
    """P(bad row is on the bad side of a good row); ties count half."""
    if not bad or not good:
        return None
    s = 0.0
    for b in bad:
        for g in good:
            if b == g:
                s += 0.5
            elif (b < g) if direction == "low" else (b > g):
                s += 1.0
    return s / (len(bad) * len(good))


def main() -> None:
    _load_bars()
    print("== artifact days detected (see docstring for the rule) ==")
    for t, ds in sorted(_ARTIFACT_DAYS.items()):
        print(f"  {t}: {[d.isoformat() for d in ds]}")

    pops = populations()
    rows: list[dict] = []
    for pop, members in pops.items():
        for tk, d, verdict in members:
            ad, prior, on = _split(tk, d)
            row = {"pop": pop, "ticker": tk, "date": d, "verdict": verdict}
            if not prior or on is None or not on["open_price"] or len(prior) < V2.MIN_BARS:
                row["unreadable"] = True
                rows.append(row)
                continue
            m = measures(tk, prior, ad, on["open_price"])
            row["unreadable"] = bool(m.get("reason"))
            row.update({k: m.get(k) for k in FIELDS})
            fg = fixture_gap(tk, d)
            row["fixture_gap_pct"] = fg
            row["gap_mismatch"] = (fg is not None and abs(fg - m["gap_open_pct_bars"]) > 1.0)
            row["concepts"] = ",".join(TAGS.get((tk, d), []))
            rows.append(row)

    cols = ["pop", "ticker", "date", "verdict", "unreadable", "fixture_gap_pct", "gap_mismatch",
            "concepts"] + FIELDS
    with READS_PSV.open("w") as f:
        f.write("|".join(cols) + "\n")
        for r in rows:
            f.write("|".join(_fmt(r.get(c)) for c in cols) + "\n")
    print(f"\nwrote {READS_PSV} ({len(rows)} rows)")

    print("\n== integrity: gap% from bars vs fixture (|diff| > 1pp) — a BASIS difference (see docstring) ==")
    for r in rows:
        if r.get("gap_mismatch"):
            print(f"  {r['pop']} {r['ticker']} {r['date']}: daily-open gap {r['gap_open_pct_bars']:.1f}% "
                  f"vs fixture {r['fixture_gap_pct']}%")
    unread = [r for r in rows if r.get("unreadable")]
    print(f"unreadable rows: {len(unread)} {[(r['ticker'], r['date']) for r in unread]}")
    print("rows with an artifact before the alert: " +
          ", ".join(f"{r['ticker']} {r['date']} (clean {r['clean_sessions']} of {r['n_prior_sessions']})"
                    for r in rows if r.get("artifact_in_history")))

    print("\n== populations ==")
    for pop, members in pops.items():
        print(f"  {pop}: n={len(members)} distinct dates={len({d for _, d, _ in members})}")
    c0408 = [t for t, d, _ in pops["REAL_EP"] if d == "2026-04-08"]
    print(f"  REAL_EP on 2026-04-08: {len(c0408)} {c0408}")

    for r in rows:
        if r["ticker"] == "MRNA":
            print(f"\n== MRNA {r['date']} (he annotates the base at 74 sessions) == base_len_35="
                  f"{r['base_len_35']} base_len_15={r['base_len_15']} pivot_age_120={r['pivot_age_120']} "
                  f"left_high_age={r['left_high_age']} n_prior={r['n_prior_sessions']}")

    # extension split of the condemned set — the population the run-up rule does NOT handle
    for r in rows:
        r["not_extended"] = (r["pop"] == "BAD_CHART" and r.get("R7_anchor75") is False)
    ne = [r for r in rows if r["not_extended"]]
    print(f"\ncondemned & NOT caught by ANCHOR-75 (the run-up rule): n={len(ne)} "
          f"{[r['ticker'] + ' ' + r['date'] for r in ne]}")

    def tally(pop: str, rule: str, subset=None):
        rs = [r for r in rows if r["pop"] == pop and not r.get("unreadable")
              and (subset is None or subset(r))]
        return ([r for r in rs if r.get(rule) is True], [r for r in rs if r.get(rule) is None], rs)

    print("\n== pre-declared rules — RULE 0 first ==")
    print("| rule | real EPs rejected (of 30) | of which 04-08 | approved lost (of 9) | condemned caught (of 21) | of the not-extended condemned | other rejected (of 4) | cannot evaluate |")
    print("|---|---|---|---|---|---|---|---|")
    for rule in RULES:
        ep_rej, ep_na, _ = tally("REAL_EP", rule)
        ap_rej, ap_na, _ = tally("APPROVED", rule)
        bd_rej, bd_na, _ = tally("BAD_CHART", rule)
        ne_rej, ne_na, ne_all = tally("BAD_CHART", rule, lambda r: r["not_extended"])
        ot_rej, ot_na, _ = tally("OTHER_REJECTED", rule)
        n0408 = sum(1 for r in ep_rej if r["date"] == "2026-04-08")
        na_txt = f"EP {len(ep_na)} · appr {len(ap_na)} · cond {len(bd_na)} · other {len(ot_na)}"
        print(f"| {rule} — {RULE_TEXT[rule]} | {len(ep_rej)} | {n0408} | {len(ap_rej)} "
              f"[{' '.join(r['ticker'] for r in ap_rej)}] | {len(bd_rej)} | {len(ne_rej)} of {len(ne_all)} | "
              f"{len(ot_rej)} | {na_txt} |")
        if ep_rej:
            print(f"    real EPs rejected: {' '.join(r['ticker'] + '/' + r['date'][5:] for r in ep_rej)}")
        if bd_rej:
            print(f"    condemned caught: {' '.join(r['ticker'] + '/' + r['date'][5:] for r in bd_rej)}")

    DESC = [
        ("n_prior_sessions", "sessions of history before the alert", "n"),
        ("clean_sessions", "of which usable (after the last data artifact)", "n"),
        ("base_len_35", "base length, sessions (closes within a 35% band)", "n"),
        ("base_len_15", "flat-base length, sessions (15% band)", "n"),
        ("pivot_age_120", "sessions since the 120-session high (the left-side high)", "n"),
        ("open_level_age", "sessions since price last traded at the gap OPEN (n counts only dates that had traded there)", "n"),
        ("mas_open_above", "of the available 10/20/50/200-day averages, how many the OPEN clears", "n"),
        ("open_vs_sma50_pct", "open vs the 50-day, %", "p"),
        ("close_vs_sma200_pct", "prior close vs the 200-day, % (only where 200 sessions exist)", "p"),
        ("sma50_slope_20_pct", "50-day average's change over the last 20 sessions, %", "p"),
        ("vol_dryup_10_50", "last-10-session volume / 50-session average (below 1 = dry-up)", "f"),
        ("updown_vol_20", "up-day volume / down-day volume, last 20 sessions (above 1 = accumulation)", "f"),
        ("open_vs_high20_pct", "open vs the 20-session high, % (positive = clears it)", "p"),
        ("open_vs_high60_pct", "open vs the 60-session high, %", "p"),
        ("open_vs_high120_pct", "open vs the 120-session high, %", "p"),
        ("overhead_vol_frac_120", "share of the last 120 sessions' volume traded ABOVE the open", "f"),
        ("zones_cleared", "congestion zones the open clears (v2, full history)", "n"),
        ("zones_remaining", "congestion zones still overhead (v2, full history)", "n"),
        ("trend_60_pct", "prior close vs 60 sessions earlier, %", "p"),
        ("trend_120_pct", "prior close vs 120 sessions earlier, %", "p"),
        ("pct_of_range_120", "where the prior close sits in the 120-session range (0 low, 1 high)", "f"),
        ("runup_low_pct_10", "run-up from the 10-session low to the prior close, %", "p"),
        ("runup_low_pct_20", "run-up from the 20-session low to the prior close, %", "p"),
        ("runup_adr_10", "the same 10-session run in ADR units", "f"),
        ("gap_adr", "the gap itself in ADR units", "f"),
        ("base_range_adr", "15-session close span in ADR units (v2 tightness)", "f"),
    ]

    def vals(sel, key):
        return sorted(r[key] for r in rows if sel(r) and not r.get("unreadable") and r.get(key) is not None)

    def dist(sel, key, kind):
        v = vals(sel, key)
        if not v:
            return "—"
        f = (lambda x: f"{x:.0f}") if kind in ("n", "p") else (lambda x: f"{x:.2f}")
        return f"{f(st.median(v))} ({f(v[0])} to {f(v[-1])}) n={len(v)}"

    sel = {"BAD": lambda r: r["pop"] == "BAD_CHART", "NE": lambda r: r["not_extended"],
           "APP": lambda r: r["pop"] == "APPROVED", "EP": lambda r: r["pop"] == "REAL_EP",
           "OTH": lambda r: r["pop"] == "OTHER_REJECTED"}
    print("\n== distributions: median (min to max) n ==")
    print("| measure | condemned, all 21 | condemned NOT extended (%d) | approved (9) | real EPs (30) | other rejected (4) |" % len(ne))
    print("|---|---|---|---|---|---|")
    for key, label, kind in DESC:
        print(f"| {label} | {dist(sel['BAD'], key, kind)} | {dist(sel['NE'], key, kind)} | "
              f"{dist(sel['APP'], key, kind)} | {dist(sel['EP'], key, kind)} | {dist(sel['OTH'], key, kind)} |")

    print("\n== separation (AUC, bad side declared per measure; 0.5 = none) ==")
    print("| measure | bad side | condemned vs approved | not-extended condemned vs approved | condemned vs real EPs | real EPs vs approved (should be ~0.5) |")
    print("|---|---|---|---|---|---|")
    for key, label, _ in DESC:
        if key not in DIRECTION:
            continue
        d = DIRECTION[key]
        a1 = auc(vals(sel["BAD"], key), vals(sel["APP"], key), d)
        a2 = auc(vals(sel["NE"], key), vals(sel["APP"], key), d)
        a3 = auc(vals(sel["BAD"], key), vals(sel["EP"], key), d)
        a4 = auc(vals(sel["EP"], key), vals(sel["APP"], key), d)
        f = lambda x: "—" if x is None else f"{x:.2f}"
        print(f"| {label} | {'lower' if d == 'low' else 'higher'} | {f(a1)} | {f(a2)} | {f(a3)} | {f(a4)} |")

    def g(r, k, f="{:.0f}"):
        v = r.get(k)
        return "n/a" if v is None else f.format(v)

    hdr = ("| pop | ticker | date | verdict | hist (clean) | base35 | pivot age | open level age | MAs open> | "
           "open/50d% | close/200d% | vol10/50 | up/dn | open/hi60% | ovh120 | zones rem | trend120% | runup20% | rules firing |")
    print("\n== per-ruling rows ==")
    print(hdr)
    print("|" + "---|" * 19)
    for r in rows:
        if r["pop"] == "REAL_EP" or r.get("unreadable"):
            continue
        firing = ",".join(k.split("_")[0] for k in RULES if r.get(k) is True)
        ola = "all" if r.get("open_clears_all_history") else g(r, "open_level_age")
        print(f"| {r['pop']} | {r['ticker']} | {r['date']} | {r['verdict']} | {r['n_prior_sessions']} ({r['clean_sessions']}) | "
              f"{r['base_len_35']} | {g(r, 'pivot_age_120')} | {ola} | {g(r, 'mas_open_above')}/{r['mas_avail']} | "
              f"{g(r, 'open_vs_sma50_pct')} | {g(r, 'close_vs_sma200_pct')} | {g(r, 'vol_dryup_10_50', '{:.2f}')} | "
              f"{g(r, 'updown_vol_20', '{:.2f}')} | {g(r, 'open_vs_high60_pct')} | {g(r, 'overhead_vol_frac_120', '{:.2f}')} | "
              f"{g(r, 'zones_remaining')} | {g(r, 'trend_120_pct')} | {g(r, 'runup_low_pct_20')} | {firing} |")

    print("\n== real EP rows ==")
    print(hdr)
    print("|" + "---|" * 19)
    for r in rows:
        if r["pop"] != "REAL_EP" or r.get("unreadable"):
            continue
        firing = ",".join(k.split("_")[0] for k in RULES if r.get(k) is True)
        ola = "all" if r.get("open_clears_all_history") else g(r, "open_level_age")
        print(f"| {r['pop']} | {r['ticker']} | {r['date']} | {r['verdict']} | {r['n_prior_sessions']} ({r['clean_sessions']}) | "
              f"{r['base_len_35']} | {g(r, 'pivot_age_120')} | {ola} | {g(r, 'mas_open_above')}/{r['mas_avail']} | "
              f"{g(r, 'open_vs_sma50_pct')} | {g(r, 'close_vs_sma200_pct')} | {g(r, 'vol_dryup_10_50', '{:.2f}')} | "
              f"{g(r, 'updown_vol_20', '{:.2f}')} | {g(r, 'open_vs_high60_pct')} | {g(r, 'overhead_vol_frac_120', '{:.2f}')} | "
              f"{g(r, 'zones_remaining')} | {g(r, 'trend_120_pct')} | {g(r, 'runup_low_pct_20')} | {firing} |")

    print("\n== his reasons, by concept ==")
    counts = defaultdict(lambda: defaultdict(int))
    for (tk, d), cs in TAGS.items():
        v = next((r.verdict for r in CHART_RULINGS if (r.ticker, r.alert_date) == (tk, d)), "?")
        for c in cs:
            counts[c][v] += 1
    print("| concept | what he said | rulings using it | measurable today? |")
    print("|---|---|---|---|")
    for c, desc in CONCEPTS.items():
        by = ", ".join(f"{v} {n}" for v, n in sorted(counts[c].items()))
        print(f"| {c} | {desc} | {sum(counts[c].values())} ({by}) | {MEASURABLE[c]} |")
    all_r = {(r.ticker, r.alert_date) for r in CHART_RULINGS}
    print(f"rulings tagged: {len(set(TAGS) & all_r)} of {len(all_r)}; untagged: {sorted(all_r - set(TAGS))}")


if __name__ == "__main__":
    main()
