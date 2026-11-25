"""COT family — live ALERTS, no orders (operator ruled "Go", 2026-11-15).

SSoT: docs/setups/cot_family.md ("Live alerts"). Research workspace: ~/cmr_lab (private). The newsletter text never
enters this repo — only the method and numbers we computed ourselves from public data.

WHAT RUNS
  cot_weekly  Fri 17:40 + 18:40 ET. CFTC legacy Futures-Only report -> the rebuilt COT index -> this week's set ups
              -> mi_cot_index_weekly, ONE paper-chat message (set ups, markets that left / reached neutral, the
              Friday-confirmation alerts). Idempotent: one message per report week.
  cot_daily   Mon-Fri 17:15 ET. For every market set up in the week KNOWN BEFORE today (no look-ahead): today's
              daily futures bar, the day's scheduled events, feed A (N1 news day closing against the crowd; C1 peers
              closing the crowd's way) -> mi_cot_alerts, ONE paper-chat message when there is an alert (silence
              otherwise), ONE audit row every run. Mon-Thu it first catches up a holiday-delayed CFTC release.

READ-ONLY DATA. No broker import, no strategy row, no order, no sizing. Free public sources only:
  CFTC   publicreporting.cftc.gov legacy futures-only API; fallback www.cftc.gov/files/dea/history/deacot<YEAR>.zip
  Bars   yfinance continuous front futures (`=F`), daily and 1-minute. A Yahoo daily close is the last trade, NOT
         the exchange settlement, so a close within a tick of the previous close can read the other way.
  Events fxempire.com economic calendar (US macro + EIA, and central-bank decisions per country), usda.gov WASDE
         release dates, yfinance earnings dates for the ten mega-caps, the announced OPEC+ meeting dates (a dated
         table, opec.org press releases) and the USDA weekly export sales schedule (a rule, fas.usda.gov).

The rules are copied from the research (cot_index.py, detector.py, detector_friday.py, surprise_rules.py,
first_tick_1min.py) and are FROZEN there; nothing here is tuned. Everything pure is in the first half of this file
and is tested without a network or a database; the I/O is the `Io` class (replaced whole in tests) plus the one `_send`.
"""
from __future__ import annotations

import asyncio
import csv
import functools
import io as _io
import json
import logging
import math
import re
import statistics
import time as _time
import zipfile
from datetime import date, datetime, time, timedelta
from typing import Optional
from zoneinfo import ZoneInfo

from shared.dates import _ET, recovery_pin

logger = logging.getLogger(__name__)

JOB_WEEKLY = "cot_weekly"
JOB_DAILY = "cot_daily"
EVT_WEEKLY = "cot_weekly"
EVT_DAILY = "cot_daily"

# ═══════════════════════════════════════════════════════════════════════════════════════════════
# Frozen tables (provenance: ~/cmr_lab, copied 2026-11-15)
# ═══════════════════════════════════════════════════════════════════════════════════════════════
# key: (display name, CFTC legacy futures-only contract code(s) spliced oldest..newest, lookback L in weekly reports
#       BACK from the current one, yfinance ticker, sector).
# Codes: scripts/cot_index.py MAP (chosen by name, proven on the 12-month column). Lookbacks: data/lookback_final.csv
# column L_weeks (fitted so the formula reproduces the unadjusted index sheet; 126 of 129 cells on 2026-11-08).
# Tickers + sectors: scripts/markets.py. Oats is left out: the CFTC no longer reports it.
MARKETS: dict[str, tuple[str, tuple[str, ...], int, str, str]] = {
    "sp500": ("S&P 500", ("13874A",), 26, "ES=F", "equities"),
    "nasdaq": ("NASDAQ", ("209742",), 27, "NQ=F", "equities"),
    "dow": ("DOW", ("124603",), 27, "YM=F", "equities"),
    "russell": ("RUSSELL", ("23977A", "239742"), 27, "RTY=F", "equities"),
    "bonds_30y": ("30-YEAR BONDS", ("020601",), 97, "ZB=F", "fixed_income"),
    "notes_10y": ("10-YEAR NOTES", ("043602",), 97, "ZN=F", "fixed_income"),
    "notes_5y": ("5-YEAR NOTES", ("044601",), 98, "ZF=F", "fixed_income"),
    "notes_2y": ("2-YEAR NOTES", ("042601",), 98, "ZT=F", "fixed_income"),
    "australian_dollar": ("AUSTRALIAN DOLLAR", ("232741",), 80, "6A=F", "currencies"),
    "british_pound": ("BRITISH POUND", ("096742",), 30, "6B=F", "currencies"),
    "canadian_dollar": ("CANADIAN DOLLAR", ("090741",), 30, "6C=F", "currencies"),
    "euro": ("EURO", ("099741",), 90, "6E=F", "currencies"),
    "japanese_yen": ("JAPANESE YEN", ("097741",), 30, "6J=F", "currencies"),
    "swiss_franc": ("SWISS FRANC", ("092741",), 30, "6S=F", "currencies"),
    "new_zealand_dollar": ("NEW ZEALAND DOLLAR", ("112741",), 79, "6N=F", "currencies"),
    "dollar_index": ("DOLLAR INDEX", ("098662",), 90, "DX-Y.NYB", "currencies"),
    "crude_oil": ("CRUDE OIL", ("067651",), 40, "CL=F", "energies"),
    "heating_oil": ("HEATING OIL", ("022651",), 40, "HO=F", "energies"),
    "unleaded_gas": ("UNLEADED GAS", ("111659",), 40, "RB=F", "energies"),
    "natural_gas": ("NATURAL GAS", ("023651",), 68, "NG=F", "energies"),
    "corn": ("CORN", ("002602",), 86, "ZC=F", "grains"),
    "soybean_meal": ("SOYBEAN MEAL", ("026603",), 30, "ZM=F", "grains"),
    "soybean_oil": ("SOYBEAN OIL", ("007601",), 34, "ZL=F", "grains"),
    "soybeans": ("SOYBEANS", ("005602",), 127, "ZS=F", "grains"),
    "wheat": ("WHEAT", ("001602",), 10, "ZW=F", "grains"),
    "lean_hogs": ("LEAN HOGS", ("054642",), 13, "HE=F", "livestock"),
    "live_cattle": ("LIVE CATTLE", ("057642",), 13, "LE=F", "livestock"),
    "copper": ("COPPER", ("085692",), 86, "HG=F", "metals"),
    "gold": ("GOLD", ("088691",), 24, "GC=F", "metals"),
    "palladium": ("PALLADIUM", ("075651",), 223, "PA=F", "metals"),
    "platinum": ("PLATINUM", ("076651",), 16, "PL=F", "metals"),
    "silver": ("SILVER", ("084691",), 23, "SI=F", "metals"),
    "cocoa": ("COCOA", ("073732",), 10, "CC=F", "softs"),
    "coffee": ("COFFEE", ("083731",), 8, "KC=F", "softs"),
    "cotton": ("COTTON", ("033661",), 40, "CT=F", "softs"),
    "lumber": ("LUMBER", ("058643", "058644"), 143, "LBR=F", "softs"),
    "orange_juice": ("ORANGE JUICE", ("040701",), 8, "OJ=F", "softs"),
    "sugar": ("SUGAR", ("080732",), 131, "SB=F", "softs"),
    "bitcoin": ("BITCOIN", ("133741",), 89, "BTC=F", "crypto"),
    "ethereum": ("ETHEREUM", ("146021",), 89, "ETH=F", "crypto"),
}
EQUITIES = frozenset({"sp500", "nasdaq", "dow", "russell"})
# Close-to-a-set-up thresholds (non-equity; operator "ok" 2026-11-16, see classify). Long side shown; short mirrors.
CLOSE_COMM_BAND = 5          # Commercials >= 95 (long) / <= 5 (short): at or very close to max crowded
CLOSE_LSPEC_BAND = 15        # Large Specs <= 15 (long) / >= 85 (short): leaning the crowded way (plateau 15-40)
CLOSE_SSPEC_OPPOSITE = 80    # Small Specs <= 80 (long) / >= 20 (short): not at the opposite extreme
# Markets whose first-minute label is not read. NOTE (review 2026-11-15): the original reason — "DX-Y.NYB has no
# 1-minute history on yfinance" — no longer holds (8,003 one-minute rows over 8 days that day; the weekly archive
# saves them). The label is left off for it until that is ruled on; this set changes no alert.
NO_MINUTE_BARS = frozenset({"dollar_index"})


def name_of(m: str) -> str:
    return MARKETS[m][0]


def sector_of(m: str) -> str:
    return MARKETS[m][4]


def ticker_of(m: str) -> str:
    return MARKETS[m][3]


ALL_CODES: tuple[str, ...] = tuple(sorted({c for v in MARKETS.values() for c in v[1]}))
HISTORY_WEEKS = max(v[2] for v in MARKETS.values()) + 40      # palladium 223 + margin (~5 years)
TRAIL_WEEKS = 26                                              # how far back an exit signal looks for its set up

# Peers for the correlation failure (detector.py PEERS, step5.md P5). (peer, sign): sign -1 = inverse.
_CUR = ["australian_dollar", "british_pound", "canadian_dollar", "euro", "japanese_yen", "swiss_franc",
        "new_zealand_dollar"]
_PM = ["gold", "silver", "platinum", "palladium"]
_EN = ["crude_oil", "heating_oil", "unleaded_gas"]
_FI = ["bonds_30y", "notes_10y", "notes_5y", "notes_2y"]
PEERS: dict[str, list[tuple[str, int]]] = {}
for _k in sorted(EQUITIES):
    PEERS[_k] = [(p, 1) for p in sorted(EQUITIES) if p != _k]
for _k in _CUR:
    PEERS[_k] = [(p, 1) for p in _CUR if p != _k] + [("dollar_index", -1)]
PEERS["dollar_index"] = [(p, -1) for p in _CUR]
for _k in _PM:
    PEERS[_k] = [(p, 1) for p in _PM if p != _k]
PEERS["copper"] = [("sp500", 1), ("silver", 1), ("platinum", 1)]
for _k in _EN:
    PEERS[_k] = [(p, 1) for p in _EN if p != _k]
PEERS["soybean_oil"] = [("crude_oil", 1), ("soybeans", 1)]
for _k in ("soybeans", "corn", "wheat"):
    PEERS[_k] = [(p, 1) for p in ("soybeans", "soybean_meal", "corn", "wheat") if p != _k]
PEERS["soybean_meal"] = [(p, 1) for p in ("soybeans", "corn", "wheat")]
PEERS["cotton"] = [("crude_oil", 1)]
PEERS["sugar"] = [("crude_oil", 1)]
for _k in _FI:
    PEERS[_k] = [(p, 1) for p in _FI if p != _k]
C1_THRESHOLD = 0.5            # median peer move the crowd's way, in each peer's own 20-day range (detector.py C1)
ATR_DAYS = 20
MIN_BARS = ATR_DAYS + 1       # features_at needs ATR_DAYS sessions BEFORE the day: a shorter 3-month series can never be read
FIRST_MINUTE_BIG = 0.25       # of a day's range, the crowd's way (first_tick_1min.py F25)
SURPRISE_DEAD_ZONE = 0.25     # |z| below this = in line (surprise_rules.py DEAD)
MAX_WEEK_AGE_DAYS = 17        # the research carries an issue at most 12 days past its Sunday = report Tuesday + 17
# A report is normally released 3 days after its Tuesday, a holiday-delayed one within a week. One FIRST SEEN later
# than that was not released today: it is stamped known from its scheduled Friday, and its Friday check is skipped
# (the "set up just completed" moment has passed).
LATE_FIRST_SIGHT_DAYS = 7
FRIDAY_CHECK_MAX_AGE_DAYS = 10

# Scheduled-event types -> the markets they are news for (news_calendar.py REL). ISM was never an N1 trigger. PCE was
# not one in the research either (it scored PCE days only as extra events); it is watched since 2026-11-22 because
# Shapiro's issue of that date named it (operator: "we should continually expand our news failure sources").
_US_TYPES = ("CPI", "PPI", "NFP", "RETAIL", "GDP", "FOMC", "PCE")
_MACRO_MARKETS = tuple(m for m in MARKETS if sector_of(m) in ("equities", "fixed_income", "currencies", "metals", "crypto"))
EVENT_MARKETS: dict[str, tuple[str, ...]] = {
    **{t: _MACRO_MARKETS for t in _US_TYPES},
    "WASDE": tuple(m for m in MARKETS if sector_of(m) in ("grains", "livestock")) + ("cotton", "sugar"),
    "EIA_PETRO": ("crude_oil", "heating_oil", "unleaded_gas"),
    "EIA_NATGAS": ("natural_gas",),
    "BOE": ("british_pound",), "ECB": ("euro",), "BOJ": ("japanese_yen",), "BOC": ("canadian_dollar",),
    "RBA": ("australian_dollar",), "SNB": ("swiss_franc",),
    # Named in Shapiro's 2026-11-16 issue as news-failure triggers (no actual-vs-consensus label: see SURPRISE_COMPONENTS)
    "FED_MINUTES": _MACRO_MARKETS,
    "RBA_MINUTES": ("australian_dollar",), "AU_JOBS": ("australian_dollar",), "AU_WAGES": ("australian_dollar",),
    # Named in his 2026-11-22 issue (PCE is in _US_TYPES above). None of these three has an actual-vs-consensus label.
    "AU_CPI": ("australian_dollar",),
    "OPEC": ("crude_oil", "heating_oil", "unleaded_gas"),
    "USDA_EXPORTS": ("soybean_oil", "soybeans", "soybean_meal", "corn", "wheat"),
}
EARNINGS_TICKERS = ("NVDA", "MSFT", "AAPL", "AMZN", "GOOGL", "META", "TSLA", "MU", "INTC", "AVGO")
EARNINGS_MARKETS = ("nasdaq", "sp500", "dow")


def markets_for_event(event_type: str) -> tuple[str, ...]:
    return EARNINGS_MARKETS if event_type.startswith("EARN_") else EVENT_MARKETS.get(event_type, ())


# FXEmpire calendar: EXACT event name -> our trigger type (the day that carries the name is the event day).
FX_US_TRIGGERS = {
    "Inflation Rate MoM": "CPI", "PPI MoM": "PPI", "Non Farm Payrolls": "NFP", "Retail Sales MoM": "RETAIL",
    "GDP Growth Rate QoQ Adv": "GDP", "GDP Growth Rate QoQ 2nd Est": "GDP", "GDP Growth Rate QoQ Final": "GDP",
    "Fed Interest Rate Decision": "FOMC", "EIA Crude Oil Stocks Change": "EIA_PETRO",
    "EIA Natural Gas Stocks Change": "EIA_NATGAS", "FOMC Minutes": "FED_MINUTES",
    # the monthly PCE release (one row per release in the served answers of 2026-11-17; the quarterly "PCE Prices QoQ"
    # rows that ride on GDP days are a different name and are not read)
    "PCE Price Index MoM": "PCE",
}
# country slug -> {exact event name: type}: that country's rate decision plus any other watched release. ECB / BoE /
# BoJ names were seen on the calendar 2026-11-15; the BoC / SNB names follow the same pattern but no such row was listed
# that day (coverage gap until one is seen). The Australian names were read from the served answer 2026-11-17
# (scripts/probes/_cot_events_1117/australia.json); "Employment Change" is the headline jobs series (one row per release).
# "Inflation Rate MoM" on the australia page is the monthly CPI (same stored answer: 4 releases, 11:30 Sydney); the
# quarterly CPI rows come out on the same day, so the one name covers both. It is read on that page only.
FX_COUNTRY_EVENTS: dict[str, dict[str, str]] = {
    "euro-area": {"ECB Interest Rate Decision": "ECB"}, "united-kingdom": {"BoE Interest Rate Decision": "BOE"},
    "japan": {"BoJ Interest Rate Decision": "BOJ"}, "canada": {"BoC Interest Rate Decision": "BOC"},
    "australia": {"RBA Interest Rate Decision": "RBA", "RBA Meeting Minutes": "RBA_MINUTES",
                  "Employment Change": "AU_JOBS", "Wage Price Index QoQ": "AU_WAGES",
                  "Inflation Rate MoM": "AU_CPI"},
    "switzerland": {"SNB Interest Rate Decision": "SNB"},
}
FX_CENTRAL_BANKS = FX_COUNTRY_EVENTS   # the countries read besides the US (loops iterate the keys)
# Standing release times (news_calendar_times.csv conventions) — used when a source gives a date without a time.
RELEASE_CONVENTION: dict[str, tuple[int, int, str]] = {
    "CPI": (8, 30, "America/New_York"), "PPI": (8, 30, "America/New_York"), "NFP": (8, 30, "America/New_York"),
    "RETAIL": (8, 30, "America/New_York"), "GDP": (8, 30, "America/New_York"), "FOMC": (14, 0, "America/New_York"),
    "EIA_PETRO": (10, 30, "America/New_York"), "EIA_NATGAS": (10, 30, "America/New_York"),
    "WASDE": (12, 0, "America/New_York"), "BOC": (9, 45, "America/Toronto"), "BOE": (12, 0, "Europe/London"),
    "ECB": (14, 15, "Europe/Berlin"), "RBA": (14, 30, "Australia/Sydney"),
    "FED_MINUTES": (14, 0, "America/New_York"), "RBA_MINUTES": (11, 30, "Australia/Sydney"),
    "AU_JOBS": (11, 30, "Australia/Sydney"), "AU_WAGES": (11, 30, "Australia/Sydney"), "SNB": (9, 30, "Europe/Zurich"),
    "EARN": (16, 0, "America/New_York"),
    "PCE": (8, 30, "America/New_York"), "AU_CPI": (11, 30, "Australia/Sydney"),
    "USDA_EXPORTS": (8, 30, "America/New_York"),
    # OPEC has NO entry on purpose: a meeting has no standing release minute (its row carries no release time).
}

# Actual-vs-consensus components (event_surprises.py COMP): type -> [(FXEmpire series, sign, rms)]. rms = the root
# mean square of (actual - forecast) for that series over 2023-08..2026-11, computed in ~/cmr_lab
# (data/event_surprises_components.csv) and FROZEN here; z = sign * (actual - forecast) / rms.
SURPRISE_COMPONENTS: dict[str, list[tuple[str, int, float]]] = {
    "CPI": [("Inflation Rate MoM", 1, 0.1), ("Core Inflation Rate MoM", 1, 0.0931891),
            ("Inflation Rate YoY", 1, 0.122474), ("Core Inflation Rate YoY", 1, 0.114708)],
    "PPI": [("PPI MoM", 1, 0.357699), ("Core PPI MoM", 1, 0.309673), ("PPI YoY", 1, 0.42517),
            ("Core PPI YoY", 1, 0.352646)],
    "NFP": [("Non Farm Payrolls", 1, 81274.4), ("Unemployment Rate", -1, 0.11547)],
    "RETAIL": [("Retail Sales MoM", 1, 0.353735), ("Retail Sales Ex Autos MoM", 1, 0.358057)],
    "GDP": [("GDP Growth Rate QoQ Adv", 1, 0.8362), ("GDP Growth Rate QoQ 2nd Est", 1, 0.270801),
            ("GDP Growth Rate QoQ Final", 1, 0.323443)],
    "FOMC": [("Fed Interest Rate Decision", 1, 0.049029)],
    "PCE": [("PCE Price Index MoM", 1, 0.0531085), ("Core PCE Price Index MoM", 1, 0.0599145),
            ("PCE Price Index YoY", 1, 0.0767948), ("Core PCE Price Index YoY", 1, 0.0800641)],
    "EIA_CRUDE": [("EIA Crude Oil Stocks Change", 1, 4634920.0)],
    "EIA_GASOLINE": [("EIA Gasoline Stocks Change", 1, 2687560.0)],
    "EIA_DISTILLATE": [("EIA Distillate Stocks Change", 1, 2365150.0)],
    "EIA_NATGAS": [("EIA Natural Gas Stocks Change", 1, 9.47194)],
}
# EPS surprise % rms per ticker, same window, same source (yfinance earnings dates); z = surprise% / rms.
EARNINGS_RMS = {"AAPL": 5.0821, "AMZN": 69.4314, "AVGO": 2.9774, "GOOGL": 67.0832, "INTC": 1367.1919,
                "META": 32.3879, "MSFT": 7.5999, "MU": 77.4192, "NVDA": 11.6332, "TSLA": 17.9719}
_EIA_OF = {"crude_oil": "EIA_CRUDE", "unleaded_gas": "EIA_GASOLINE", "heating_oil": "EIA_DISTILLATE"}
_INFLATION, _GROWTH = {"CPI", "PPI", "PCE"}, {"NFP", "RETAIL", "GDP"}   # surprise_rules.py INFL / GROW (ISM not read)
CLASS_ORDER = ("WITH", "AGAINST", "INLINE", "AMBIG", "UNKNOWN")
CLASS_WORDS = {"WITH": "with the crowd", "AGAINST": "against the crowd", "INLINE": "in line",
               "AMBIG": "unknown (no clear read for this market)", "UNKNOWN": "unknown"}


class CotError(RuntimeError):
    """A COT job could not do its work (the page)."""


class CalendarRefused(CotError):
    """A calendar source answered 401 / 403 / 429: stop, do not retry, do not change the request."""


# ═══════════════════════════════════════════════════════════════════════════════════════════════
# The index (cot_index.py: series + index_at(weeks=L+1), calendar window, round half up)
# ═══════════════════════════════════════════════════════════════════════════════════════════════
def tuesday_of(d: date) -> date:
    """The Tuesday of d's week. A holiday week's report is dated Monday; normalising makes 'L weeks back' one thing."""
    return d + timedelta(days=1 - d.weekday())


def build_series(nets_by_code: dict[str, dict[date, tuple]], codes) -> dict[date, tuple]:
    """{normalised Tuesday: (comm, lspec, sspec, report_date)} for one market. With several codes, a later code wins
    from ITS first report on (the contract was replaced)."""
    out: dict[date, tuple] = {}
    for code in codes:
        rows = nets_by_code.get(code) or {}
        if not rows:
            continue
        first = min(rows)
        out = {k: v for k, v in out.items() if v[3] < first}
        for rd, (c, l, s) in rows.items():
            out[tuesday_of(rd)] = (c, l, s, rd)
    return out


def _round_half_up(v: float) -> int:
    return int(math.floor(v + 0.5))


def index_at(series: dict[date, tuple], asof: date, lookback: int) -> Optional[tuple]:
    """(comm, lspec, sspec) index 0..100 at the report week `asof` (a normalised Tuesday), or None.

    Window = the current report plus `lookback` weekly reports back, by CALENDAR on the normalised dates (dates later
    than asof - 7*(lookback+1) days). Index = 100 * (net - min) / (max - min), rounded half up. A group whose window
    is flat is None. A market whose history does not reach the start of the window returns None (never a silently
    narrower window)."""
    if asof not in series or not series:
        return None
    start = asof - timedelta(days=7 * lookback)
    if min(series) > start:
        return None
    win = [v for d, v in series.items() if start <= d <= asof]
    cur = series[asof]
    out = []
    for g in range(3):
        vals = [v[g] for v in win]
        lo, hi = min(vals), max(vals)
        out.append(_round_half_up(100 * (cur[g] - lo) / (hi - lo)) if hi > lo else None)
    return tuple(out)


def classify(market: str, comm, lspec, sspec) -> tuple[Optional[str], Optional[str]]:
    """(setup, close_setup), each 'short' / 'long' / None.

    MAIN: Commercials <= 5 and both speculator groups >= 95 -> short (fade a crowd that is long); the mirror -> long;
    equity indices on Commercials alone.
    CLOSE (operator "ok" 2026-11-16; his heat-map footnote: Commercials at or very close to max, WAITING for both
    speculator groups; his note: a speculator group at the OPPOSITE extreme is not a set up): not main, Commercials
    <= 5 and Large Specs >= 85 and Small Specs >= 20 -> short; Commercials >= 95 and Large Specs <= 15 and Small
    Specs <= 80 -> long. Equity indices keep the Commercials-only 6-10 / 90-94 band. Study: ~/cmr_lab
    docs/close_rule_study.md (2026 holdout: catches 78% of his close list, 92% of flags on his lists, ~6.8 a week;
    the old both-specs rule caught 20%)."""
    if comm is None:
        return None, None
    eq = market in EQUITIES
    have = lspec is not None and sspec is not None

    def both(lo=None, hi=None):
        if eq:
            return True
        if not have:
            return False
        return (lspec >= lo and sspec >= lo) if lo is not None else (lspec <= hi and sspec <= hi)

    if comm <= 5 and both(lo=95):
        return "short", None
    if comm >= 95 and both(hi=5):
        return "long", None
    if eq:
        if comm <= 10:
            return None, "short"
        if comm >= 90:
            return None, "long"
        return None, None
    if not have:
        return None, None
    if comm <= CLOSE_COMM_BAND and lspec >= 100 - CLOSE_LSPEC_BAND and sspec >= 100 - CLOSE_SSPEC_OPPOSITE:
        return None, "short"
    if comm >= 100 - CLOSE_COMM_BAND and lspec <= CLOSE_LSPEC_BAND and sspec <= CLOSE_SSPEC_OPPOSITE:
        return None, "long"
    return None, None


def index_table(nets_by_code: dict, weeks: list[date]) -> dict[date, dict[str, dict]]:
    """{week: {market: {comm, lspec, sspec, setup, close_setup, report_date}}} for every market with an index."""
    out: dict[date, dict[str, dict]] = {w: {} for w in weeks}
    for m, (_n, codes, look, _t, _s) in MARKETS.items():
        ser = build_series(nets_by_code, codes)
        for w in weeks:
            ix = index_at(ser, w, look)
            if ix is None or ix[0] is None:
                continue
            setup, close = classify(m, *ix)
            out[w][m] = {"comm": ix[0], "lspec": ix[1], "sspec": ix[2], "setup": setup, "close_setup": close,
                         "report_date": ser[w][3], "nets": ser[w][:3], "lookback": look}
    return out


def _neutral(market: str, direction: str, r: dict) -> bool:
    """The exit reading: the relevant group back at ~50 (Commercials for equity indices; any group otherwise)."""
    c, l, s = r["comm"], r["lspec"], r["sspec"]
    if direction == "short":
        return c >= 50 or (market not in EQUITIES and ((l is not None and l <= 50) or (s is not None and s <= 50)))
    return c <= 50 or (market not in EQUITIES and ((l is not None and l >= 50) or (s is not None and s >= 50)))


def exit_signals(table: dict[date, dict[str, dict]], weeks: list[date]) -> list[dict]:
    """Markets that LEFT a main set up this week, or whose index reached neutral this week for the first time since
    their last main set up (within TRAIL_WEEKS). `weeks` ascending, the last one is this week."""
    if len(weeks) < 2:
        return []
    cur_w, prev_w = weeks[-1], weeks[-2]
    out = []
    for m, cur in table[cur_w].items():
        prev = table[prev_w].get(m)
        left = bool(prev and prev["setup"] and cur["setup"] != prev["setup"])
        direction = prev["setup"] if left else None
        neutral = False
        last = None
        for w in reversed(weeks[:-1][-TRAIL_WEEKS:]):
            r = table[w].get(m)
            if r and r["setup"]:
                last = w
                break
        if last is not None and not cur["setup"]:
            d = table[last][m]["setup"]
            between = [table[w].get(m) for w in weeks if last < w < cur_w]
            if not any(r and _neutral(m, d, r) for r in between) and _neutral(m, d, cur):
                neutral, direction = True, d
        if left or neutral:
            out.append({"market": m, "direction": direction, "left": left, "neutral": neutral,
                        "now": "close list" if cur["close_setup"] == direction else "not set up",
                        "comm": cur["comm"], "lspec": cur["lspec"], "sspec": cur["sspec"]})
    return sorted(out, key=lambda r: r["market"])


# ═══════════════════════════════════════════════════════════════════════════════════════════════
# Daily features + feed A (detector.py) + the Friday confirmation (detector_friday.py, primary cell)
# ═══════════════════════════════════════════════════════════════════════════════════════════════
def features_at(bars: list[tuple], day: date) -> Optional[dict]:
    """bars: weekday-only (date, open, high, low, close) ascending. Returns the day's reading or None when there is
    no bar DATED `day` or fewer than ATR_DAYS earlier sessions. atr = mean true range of the ATR_DAYS sessions BEFORE
    the day; z = (close - previous close) / atr."""
    idx = next((i for i, b in enumerate(bars) if b[0] == day), None)
    if idx is None or idx < ATR_DAYS:
        return None
    trs = []
    for i in range(idx - ATR_DAYS, idx):
        _d, _o, h, l, _c = bars[i]
        pc = bars[i - 1][4] if i > 0 else None
        trs.append(max(h - l, abs(h - pc), abs(l - pc)) if pc is not None else h - l)
    atr = sum(trs) / ATR_DAYS
    if not atr > 0:
        return None
    _d, _o, h, l, c = bars[idx]
    pc = bars[idx - 1][4]
    return {"date": day, "high": h, "low": l, "close": c, "prev_close": pc, "atr": atr, "z": (c - pc) / atr}


def crowd_sign(direction: str) -> int:
    """+1 for a short set up (the crowd is long: crowd-friendly = up, a failure = a down close)."""
    return 1 if direction == "short" else -1


def peer_reading(market: str, direction: str, z_by_market: dict[str, float]) -> Optional[float]:
    """Median peer close in each peer's own daily range, signed so + = the peers closed the CROWD's way."""
    sg = crowd_sign(direction)
    v = [sg * s2 * z_by_market[p] for p, s2 in PEERS.get(market, []) if z_by_market.get(p) is not None]
    return float(statistics.median(v)) if v else None


def detect(market: str, direction: str, feat: Optional[dict], events: list[str],
           z_by_market: dict[str, float]) -> Optional[dict]:
    """Feed A for one set-up market on one day. None = no alert. N1: a scheduled event today and the close AGAINST
    the crowd. C1: the close against the crowd while the peers' median close was >= 0.5 of their range the crowd's
    way."""
    if feat is None:
        return None
    sg = crowd_sign(direction)
    against = feat["z"] < 0 if sg == 1 else feat["z"] > 0
    if not against:
        return None
    peer = peer_reading(market, direction, z_by_market)
    kinds = (["news"] if events else []) + (["correlation"] if peer is not None and peer >= C1_THRESHOLD else [])
    if not kinds:
        return None
    return {"market": market, "direction": direction, "kinds": kinds, "events": list(events), "z": feat["z"],
            "peer_z": peer, "close": feat["close"], "stop": feat["high"] if sg == 1 else feat["low"],
            "stop_rule": f"a close {'above' if sg == 1 else 'below'} {_px(feat['high'] if sg == 1 else feat['low'])}"
                         f" (the {feat['date']:%m-%d} {'high' if sg == 1 else 'low'})",
            "atr": feat["atr"]}


def friday_confirmation(market: str, direction: str, bars: list[tuple], report_date: date, release_day: date,
                        events_by_day: dict[date, list[str]], z_by_day: dict[date, dict[str, float]]) -> Optional[dict]:
    """A set up that COMPLETED in this report: was there a live failure day (N1 or C1) from the Wednesday after the
    report Tuesday through the release day? The LAST such day whose stop has not already been closed through.
    None when there is none (a failure already stopped out is not an alert)."""
    sg = crowd_sign(direction)
    start = tuesday_of(report_date) + timedelta(days=1)
    live = None
    closes = {b[0]: b[4] for b in bars}
    for b in bars:
        day = b[0]
        if not (start <= day <= release_day):
            continue
        hit = detect(market, direction, features_at(bars, day), events_by_day.get(day, []), z_by_day.get(day, {}))
        if hit is None:
            continue
        later = [c for d, c in closes.items() if day < d <= release_day]
        dead = any(c > hit["stop"] for c in later) if sg == 1 else any(c < hit["stop"] for c in later)
        if not dead:
            live = {**hit, "failure_day": day}
    return live


# ═══════════════════════════════════════════════════════════════════════════════════════════════
# Labels: the first minute after the release, and actual vs consensus
# ═══════════════════════════════════════════════════════════════════════════════════════════════
def first_minute(minute_bars: list[tuple], release: Optional[datetime], atr: float, direction: str) -> dict:
    """minute_bars: (bar START time, tz-aware; close) ascending. Baseline = the last bar that started before the
    release minute (no older than 30 minutes); the move = the close of the bar that STARTS at the release minute,
    minus the baseline, in units of the market's 20-day daily range, signed so + = the crowd's way. 'big' when
    >= 0.25. (The research measured this on ETF minute bars in ETF-range units; here it is the future itself.)"""
    if release is None:
        return {"status": "no release time"}
    if not minute_bars:
        return {"status": "no minute bars"}
    before = [b for b in minute_bars if b[0] < release]
    if not before or before[-1][0] < release - timedelta(minutes=30):
        return {"status": "no bar just before the release"}
    inside = [b for b in minute_bars if release <= b[0] < release + timedelta(minutes=1)]
    if not inside:
        return {"status": "no bar in the release minute"}
    move = crowd_sign(direction) * (inside[-1][1] - before[-1][1]) / atr
    return {"status": "ok", "move": move, "big": move >= FIRST_MINUTE_BIG}


_MULT = {"K": 1e3, "M": 1e6, "B": 1e9, "T": 1e12}


def parse_number(x, mult: bool = True) -> Optional[float]:
    """'114K' -> 114000, '-1.6M' -> -1.6e6, '0.2%' -> 0.2, '18Bcf' -> 18. mult=False ignores the unit letter (gas
    storage is printed 'Bcf' or 'B')."""
    if x is None:
        return None
    s = str(x).strip().replace(",", "").replace("$", "").replace("€", "").replace(" ", "")
    m = re.match(r"^(-?\d+(?:\.\d+)?)([A-Za-z%]*)$", s)
    if not m:
        return None
    v, u = float(m.group(1)), m.group(2)
    return v * _MULT[u] if (mult and u in _MULT) else v


def _fx_ts(e: dict) -> Optional[datetime]:
    try:
        return datetime.fromisoformat(str(e["date"]).replace("Z", "+00:00")).astimezone(_ET)
    except Exception:  # loud-ok: an unparseable calendar row is dropped by the caller, which counts what it kept
        return None


def surprises_from_fx(events: list[dict]) -> dict[tuple, dict]:
    """{(ET date, surprise type): {z, text}} from FXEmpire rows that carry an ACTUAL. z = mean over the type's
    components of sign * (actual - forecast) / rms; FOMC: +-9 on any surprise, 0 when the decision was the forecast."""
    by_name: dict[tuple, dict] = {}
    for e in events:
        ts = _fx_ts(e)
        if ts is not None:
            by_name[(ts.date(), str(e.get("name", "")).strip())] = e
    out: dict[tuple, dict] = {}
    for typ, comps in SURPRISE_COMPONENTS.items():
        for d in {k[0] for k in by_name}:
            zs, parts = [], []
            for series, sign, rms in comps:
                e = by_name.get((d, series))
                if e is None:
                    continue
                gas = series == "EIA Natural Gas Stocks Change"
                a, f = parse_number(e.get("actual"), not gas), parse_number(e.get("forecast"), not gas)
                if a is None:
                    continue
                parts.append(f"{series} {e.get('actual')} vs {e.get('forecast') or '?'}")
                if f is not None:
                    zs.append((a - f) if typ == "FOMC" else sign * (a - f) / rms)
            if not parts:
                continue
            if not zs:
                z = None
            elif typ == "FOMC":
                z = 0.0 if zs[0] == 0 else math.copysign(9.0, zs[0])
            else:
                z = sum(zs) / len(zs)
            out[(d, typ)] = {"z": z, "text": "; ".join(parts)}
    return out


def news_sign(event_type: str, market: str) -> Optional[int]:
    """The sign a POSITIVE surprise gives the market: +1 / -1; 0 = ambiguous; None = no mapping (surprise_rules.py
    `mapping`, primary: growth data is ambiguous for stock indices)."""
    sec = sector_of(market)
    if event_type.startswith("EARN_"):
        return 1 if market in EARNINGS_MARKETS else None
    if event_type == "EIA_PETRO":
        return -1 if market in _EIA_OF else None
    if event_type == "EIA_NATGAS":
        return -1 if market == "natural_gas" else None
    if event_type in _INFLATION or event_type == "FOMC" or event_type in _GROWTH:
        g = event_type in _GROWTH
        if sec == "equities":
            return 0 if g else -1
        if sec == "fixed_income":
            return -1
        if sec == "currencies":
            return 1 if market == "dollar_index" else -1
        if market in ("gold", "silver"):
            return -1
        if market == "copper":
            return 1 if g else 0
        if market in ("platinum", "palladium"):
            return 0
        if sec == "crypto":
            return 0 if g else -1
    return None


def news_class(event_type: str, market: str, direction: str, day: date, surprises: dict[tuple, dict]) -> dict:
    """{cls, z, text}: was the news WITH the crowd, AGAINST it, INLINE, AMBIG (no clear read) or UNKNOWN."""
    src = _EIA_OF.get(market) if event_type == "EIA_PETRO" else event_type
    mp = news_sign(event_type, market)
    if mp is None or src is None:
        return {"cls": "UNKNOWN", "z": None, "text": ""}
    r = None
    for off in ((0, 1, -1) if event_type.startswith("EIA") else (0,)):
        r = surprises.get((day + timedelta(days=off), src))
        if r is not None:
            break
    if r is None or r.get("z") is None:
        return {"cls": "UNKNOWN", "z": None, "text": (r or {}).get("text", "")}
    z = r["z"]
    if mp == 0:
        return {"cls": "AMBIG", "z": z, "text": r["text"]}
    if abs(z) < SURPRISE_DEAD_ZONE or z == 0:
        return {"cls": "INLINE", "z": z, "text": r["text"]}
    news_dir = 1 if z * mp > 0 else -1
    return {"cls": "WITH" if news_dir == crowd_sign(direction) else "AGAINST", "z": z, "text": r["text"]}


def overall_class(classes: list[str]) -> str:
    return next((c for c in CLASS_ORDER if c in classes), "UNKNOWN")


# ═══════════════════════════════════════════════════════════════════════════════════════════════
# The forward calendar
# ═══════════════════════════════════════════════════════════════════════════════════════════════
def session_date(release_et: datetime, earnings: bool = False) -> date:
    """The daily futures session a release belongs to: a release at or after 17:00 ET (the daily close; 16:00 for a
    company's earnings, as in the research) belongs to the NEXT weekday."""
    d = release_et.date()
    if release_et.hour >= (16 if earnings else 17):
        d += timedelta(days=1)
    while d.weekday() >= 5:
        d += timedelta(days=1)
    return d


def calendar_rows_from_fx(events: list[dict], country: str = "united-states") -> list[dict]:
    """Trigger rows from FXEmpire events (exact names only)."""
    out = {}
    for e in events:
        name = str(e.get("name", "")).strip()
        if country == "united-states":
            typ = FX_US_TRIGGERS.get(name)
        else:
            typ = FX_COUNTRY_EVENTS.get(country, {}).get(name)
        ts = _fx_ts(e)
        if typ is None or ts is None:
            continue
        d = session_date(ts)
        out[(d, typ)] = {"event_date": d, "event_type": typ, "release_et": ts,
                         "source": f"fxempire.com economic calendar ({country})"}
    return list(out.values())


_MONTHS = {m: i + 1 for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"])}


def parse_wasde_dates(page_html: str) -> list[date]:
    """usda.gov WASDE page: 'In 2027 the WASDE report will be released on Jan. 12, Feb. 10, ... and Dec. 10.'"""
    text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", page_html))
    out = []
    for m in re.finditer(r"In (20\d\d) the WASDE report will be released on ([^<]{20,400}?\d)\s*\.(?!\d)", text):
        year = int(m.group(1))
        for mm in re.finditer(r"([A-Z][a-z]{2})[a-z]*\.?\s+(\d{1,2})", m.group(2)):
            mon = _MONTHS.get(mm.group(1).lower())
            if mon:
                out.append(date(year, mon, int(mm.group(2))))
    return sorted(set(out))


WASDE_SOURCE = "usda.gov WASDE release dates"     # the exact string the rows carry: calendar_age_days matches it


def calendar_rows_from_wasde(dates: list[date]) -> list[dict]:
    h, mi, tz = RELEASE_CONVENTION["WASDE"]
    return [{"event_date": d, "event_type": "WASDE",
             "release_et": datetime.combine(d, time(h, mi), ZoneInfo(tz)).astimezone(_ET),
             "source": WASDE_SOURCE} for d in dates]


# ── OPEC+ meetings: a dated table (opec.org answered a scripted read with HTTP 403 on 2026-11-22) ──
# Each date is the meeting day as ANNOUNCED in an opec.org press release; add the next one when it is announced.
# tests/test_cot_family.py fails once the newest date is more than OPEC_STALE_DAYS in the past (the table was left
# to rot). Only announced dates go in: an unannounced extraordinary meeting cannot be seen here.
OPEC_SOURCE_URL = "https://www.opec.org/pr-detail/620-1-november-2026.html"
OPEC_SOURCE = "opec.org press releases (announced OPEC+ meeting dates)"
OPEC_MEETINGS: tuple[date, ...] = (
    date(2026, 11, 29),      # "The next meeting will be held on 29 November 2026." (press release of 1 November 2026)
)
OPEC_STALE_DAYS = 21     # the seven-country meeting is MONTHLY (opec.org 2026-11-01): under one cycle, so a meeting
                         # cannot pass unseen. Each meeting's press release names the next date: add it then.


def opec_table_age_days(today: date) -> int:
    """Days the newest announced meeting lies in the past (negative = it is still ahead)."""
    return (today - max(OPEC_MEETINGS)).days


def calendar_rows_from_opec(meetings=OPEC_MEETINGS, d0: Optional[date] = None, d1: Optional[date] = None) -> list[dict]:
    """A meeting on a weekday is that day's session; one on a Saturday / Sunday (most are) is Monday's. No release
    time: a meeting ends when it ends, so the first-minute label reads 'no release time'. `d0` / `d1` (optional)
    keep only the sessions in d0..d1, as the USDA rule's rows are."""
    out = []
    for d in meetings:
        s = d
        while s.weekday() >= 5:
            s += timedelta(days=1)
        if (d0 is not None and s < d0) or (d1 is not None and s > d1):
            continue
        out.append({"event_date": s, "event_type": "OPEC", "release_et": None, "source": OPEC_SOURCE})
    return out


# ── USDA weekly export sales: a rule, not a read (www.fas.usda.gov answered a script with 403 on 2026-11-22) ──
# FAS Export Sales Reporting Program (https://www.fas.usda.gov/programs/export-sales-reporting-program): the weekly
# summary is published Thursdays at 8:30 ET unless a change is announced; when the preceding Friday or the Monday
# is a national holiday the reporting deadline moves to Tuesday and the summary is published on Friday. INFERRED,
# not stated there: a holiday on the Tuesday, Wednesday or Thursday also moves it to Friday (Thanksgiving week 2026:
# Fri 11-27, the date his issue gave). OUR OWN GUESS, from no source: when that Friday is itself a federal holiday
# the next working day is taken (first case Fri 2027-01-01 -> Mon 2027-01-04). A change FAS announces on its own
# (a shutdown) cannot be seen by a rule.
USDA_EXPORTS_SOURCE = "fas.usda.gov weekly export sales schedule (rule)"


def _observed(d: date) -> date:
    return d - timedelta(days=1) if d.weekday() == 5 else d + timedelta(days=1) if d.weekday() == 6 else d


def _nth_weekday(year: int, month: int, weekday: int, n: int) -> date:
    """n-th `weekday` (Mon=0) of the month; n = -1 is the last one."""
    if n > 0:
        d = date(year, month, 1)
        return d + timedelta(days=(weekday - d.weekday()) % 7 + 7 * (n - 1))
    d = date(year + (month == 12), month % 12 + 1, 1) - timedelta(days=1)
    return d - timedelta(days=(d.weekday() - weekday) % 7)


@functools.lru_cache(maxsize=None)
def us_federal_holidays(year: int) -> frozenset[date]:
    """The eleven US federal holidays that fall in `year` as OBSERVED (a Saturday one on Friday, a Sunday one on
    Monday; next New Year's Day when it is observed on Dec 31). Not the stock market's list: Columbus Day and
    Veterans Day are federal holidays, Good Friday is not."""
    days = {_observed(date(year, 1, 1)), _nth_weekday(year, 1, 0, 3), _nth_weekday(year, 2, 0, 3),
            _nth_weekday(year, 5, 0, -1), _observed(date(year, 6, 19)), _observed(date(year, 7, 4)),
            _nth_weekday(year, 9, 0, 1), _nth_weekday(year, 10, 0, 2), _observed(date(year, 11, 11)),
            _nth_weekday(year, 11, 3, 4), _observed(date(year, 12, 25)), _observed(date(year + 1, 1, 1))}
    return frozenset(d for d in days if d.year == year)


def usda_export_sales_dates(d0: date, d1: date) -> list[date]:
    """The weekly export sales release days in d0..d1 (the rule above)."""
    def holiday(d: date) -> bool:
        return d in us_federal_holidays(d.year)
    out = []
    thu = d0 - timedelta(days=7) + timedelta(days=(3 - d0.weekday()) % 7)
    while thu <= d1:
        rel = thu
        if any(holiday(thu - timedelta(days=k)) for k in (6, 3, 2, 1, 0)):    # the Friday before, Mon, Tue, Wed, Thu
            rel = thu + timedelta(days=1)
            while rel.weekday() >= 5 or holiday(rel):
                rel += timedelta(days=1)
        if d0 <= rel <= d1:
            out.append(rel)
        thu += timedelta(days=7)
    return out


def calendar_rows_from_usda_exports(d0: date, d1: date) -> list[dict]:
    h, mi, tz = RELEASE_CONVENTION["USDA_EXPORTS"]
    return [{"event_date": d, "event_type": "USDA_EXPORTS",
             "release_et": datetime.combine(d, time(h, mi), ZoneInfo(tz)).astimezone(_ET),
             "source": USDA_EXPORTS_SOURCE} for d in usda_export_sales_dates(d0, d1)]


def calendar_rows_from_earnings(ticker: str, stamps: list[datetime]) -> list[dict]:
    """After-close report -> the next session (the research rule)."""
    out = []
    for ts in stamps:
        ts = ts.astimezone(_ET)
        out.append({"event_date": session_date(ts, earnings=True), "event_type": f"EARN_{ticker}", "release_et": ts,
                    "source": "yfinance earnings dates"})
    return out


# ═══════════════════════════════════════════════════════════════════════════════════════════════
# News watch (2026-11-25): the news to watch for, then the verdict. Display only: nothing here reads into detect(), the
# alert rule or the Telegram messages. Owner doc: docs/setups/cot_family.md §News watch; spec docs/design/cot_news_watch_2026-11-25.md.
# ═══════════════════════════════════════════════════════════════════════════════════════════════
WATCH_DAYS = 7                  # how far ahead a card lists events (and how far back the page shows them)
FM_FLAT_BAND = 0.01             # of a day's range: a first minute at or below this is "flat" (the page's flat band)
NO_FORECAST_TYPES = frozenset({"WASDE", "OPEC", "USDA_EXPORTS", "FED_MINUTES", "RBA_MINUTES"})   # kind C
def _fx_names_of_type() -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for names in FX_COUNTRY_EVENTS.values():
        for n, t in names.items():
            out.setdefault(t, []).append(n)
    return out


_FX_NAMES_OF_TYPE = _fx_names_of_type()
_US_NAME_TYPE = {s: ("EIA_PETRO" if t in ("EIA_CRUDE", "EIA_GASOLINE", "EIA_DISTILLATE") else t)
                 for t, comps in SURPRISE_COMPONENTS.items() for s, _sg, _rms in comps}
_SERIES_LABEL = {
    "Non Farm Payrolls": "payrolls", "Unemployment Rate": "unemployment", "Inflation Rate MoM": "CPI m/m",
    "Core Inflation Rate MoM": "core CPI m/m", "Inflation Rate YoY": "CPI y/y", "Core Inflation Rate YoY": "core CPI y/y",
    "PPI MoM": "PPI m/m", "Core PPI MoM": "core PPI m/m", "PPI YoY": "PPI y/y", "Core PPI YoY": "core PPI y/y",
    "Retail Sales MoM": "retail sales m/m", "Retail Sales Ex Autos MoM": "retail sales ex autos m/m",
    "GDP Growth Rate QoQ Adv": "GDP q/q", "GDP Growth Rate QoQ 2nd Est": "GDP q/q", "GDP Growth Rate QoQ Final": "GDP q/q",
    "Fed Interest Rate Decision": "the Fed rate", "PCE Price Index MoM": "PCE m/m", "Core PCE Price Index MoM": "core PCE m/m",
    "PCE Price Index YoY": "PCE y/y", "Core PCE Price Index YoY": "core PCE y/y",
    "EIA Crude Oil Stocks Change": "crude stocks change", "EIA Gasoline Stocks Change": "gasoline stocks change",
    "EIA Distillate Stocks Change": "distillate stocks change", "EIA Natural Gas Stocks Change": "gas stocks change",
    "EPS": "EPS"}
# type -> (words for a surprise ABOVE forecast, words for one BELOW): "above" = z > 0 in SURPRISE_COMPONENTS' own signs
_NEWS_WORDS = {
    **{t: ("inflation hotter than forecast", "inflation cooler than forecast") for t in _INFLATION},
    "NFP": ("jobs stronger than forecast", "jobs weaker than forecast"),
    "RETAIL": ("retail sales stronger than forecast", "retail sales weaker than forecast"),
    "GDP": ("growth stronger than forecast", "growth weaker than forecast"),
    "FOMC": ("a rate above forecast (a hawkish surprise)", "a rate below forecast (a dovish surprise)"),
    "EIA_PETRO": ("a bigger stock build, or a smaller draw, than forecast",
                  "a smaller build, or a bigger draw, than forecast"),
    "EIA_NATGAS": ("a bigger stock build, or a smaller draw, than forecast",
                   "a smaller build, or a bigger draw, than forecast"),
    "EARN": ("an EPS beat", "an EPS miss")}
VERDICT_WORDS = {
    "failure_full": "NEWS FAILURE, all three steps",
    "failure": "News failure: news favoured the crowd, closed against them",
    "followed_news": "No failure: the market followed the news",
    "against_unread": "Closed against the crowd on a news day; the news had no clear read (a failure by the live rule only)",
    "shrugged": "No failure: bad news for the crowd, and the market closed their way anyway",
    "no_failure": "No failure: closed the crowd's way",
    "pending": "Pending close"}


def _blank(x) -> Optional[str]:
    s = "" if x is None else str(x).strip()
    return s or None


def watch_series_names(event_type: str, market: str) -> list[str]:
    """The source series an event card shows for this market. [] = kind C: the source lists no forecast for this event."""
    if event_type in NO_FORECAST_TYPES:
        return []
    if event_type.startswith("EARN_"):
        return ["EPS"]
    src = _EIA_OF.get(market) if event_type == "EIA_PETRO" else event_type
    if src in SURPRISE_COMPONENTS:
        return [c[0] for c in SURPRISE_COMPONENTS[src]]
    return list(_FX_NAMES_OF_TYPE.get(event_type, []))          # kind B: central banks and Australian data


def watch_read(event_type: str, market: str) -> str:
    """mapped = the research maps a surprise to a direction for this market (a crowd read); ambiguous = a forecast is
    shown but there is no crowd read; none = no forecast and no read."""
    mp = news_sign(event_type, market)
    if mp in (1, -1):
        return "mapped"
    return "ambiguous" if (mp == 0 or watch_series_names(event_type, market)) else "none"


def expectations_from_fx(events: list[dict], country: str = "united-states") -> dict[tuple, dict[str, dict]]:
    """{(session day, event type): {series name: {forecast, previous, actual}}} from the raw FXEmpire rows, text as
    printed (a blank is None). Only series the watch shows (the surprise components; a central bank's own decision)."""
    out: dict[tuple, dict[str, dict]] = {}
    for e in events:
        name = str(e.get("name", "")).strip()
        typ = _US_NAME_TYPE.get(name) if country == "united-states" else FX_COUNTRY_EVENTS.get(country, {}).get(name)
        ts = _fx_ts(e)
        if typ is None or ts is None or typ in NO_FORECAST_TYPES:
            continue
        out.setdefault((session_date(ts), typ), {})[name] = {
            "forecast": _blank(e.get("forecast")), "previous": _blank(e.get("previous")), "actual": _blank(e.get("actual"))}
    return out


def lookup_expectation(exp: dict, day: date, event_type: str) -> Optional[dict[str, dict]]:
    """One event's series from `expectations_from_fx`; EIA may sit a day either side (as news_class allows)."""
    for off in ((0, 1, -1) if event_type.startswith("EIA") else (0,)):
        r = exp.get((day + timedelta(days=off), event_type))
        if r is not None:
            return r
    return None


def merge_series(names: list[str], old: Optional[list], fresh: Optional[dict], released: bool) -> list[dict]:
    """The stored series after one more read. BEFORE the release a read that carries a figure refreshes `forecast`
    (and `previous`); a blank never erases. AT or AFTER the release a read never touches `forecast`: it fills `actual`
    and keeps the figure the source lists then as `forecast_after`."""
    olds = {s.get("name"): s for s in (old or [])}
    out = []
    for n in names:
        o, f = olds.get(n) or {}, (fresh or {}).get(n) or {}
        row = {"name": n, "forecast": o.get("forecast"), "previous": o.get("previous"), "actual": o.get("actual"),
               "forecast_after": o.get("forecast_after")}
        if f and not released:
            row["forecast"] = f.get("forecast") or row["forecast"]
            row["previous"] = f.get("previous") or row["previous"]
        elif f:
            row["actual"] = f.get("actual") or row["actual"]
            row["forecast_after"] = f.get("forecast") or row["forecast_after"]
            row["previous"] = row["previous"] or f.get("previous")
        out.append(row)
    return out


def favoured_z_sign(event_type: str, market: str, direction: str) -> Optional[int]:
    """The sign of the surprise (z, in SURPRISE_COMPONENTS' own signs) that FAVOURS the crowd: +1 = above forecast.
    `direction` is the side to fade into, so the crowd is the other side. None = no crowd read for this pair."""
    mp = news_sign(event_type, market)
    return None if mp not in (1, -1) else crowd_sign(direction) * mp


def crowd_outcome_words(event_type: str, market: str, direction: str, series: list[dict]) -> str:
    """The plain 'news to watch for' sentence; "" unless the pair has a crowd read."""
    fz = favoured_z_sign(event_type, market, direction)
    if fz is None:
        return ""
    cs = crowd_sign(direction)                      # +1: the crowd is long
    key = "EARN" if event_type.startswith("EARN_") else event_type
    words = _NEWS_WORDS[key][0 if fz > 0 else 1]
    src = _EIA_OF.get(market) if event_type == "EIA_PETRO" else event_type
    signs = {c[0]: c[1] for c in SURPRISE_COMPONENTS.get(src, [])} if src else {}
    if event_type.startswith("EARN_"):
        signs = {"EPS": 1}
    figs = [f"{_SERIES_LABEL.get(s['name'], s['name'])} {'above' if fz * signs.get(s['name'], 1) > 0 else 'below'} {s['forecast']}"
            for s in series if s.get("forecast")]
    mk = name_of(market).title()
    return (f"Crowd is {'LONG' if cs > 0 else 'SHORT'} {mk}. News that favours the crowd: {words}"
            f"{' (' + ', '.join(figs) + ')' if figs else ''} = {'bullish' if cs > 0 else 'bearish'} {mk}. "
            f"Failure to watch for: that news, a first move {'up' if cs > 0 else 'down'}, "
            f"then a close {'DOWN' if cs > 0 else 'UP'}.")


def watch_verdict(close_z: Optional[float], direction: str, news_cls: str, fm: Optional[dict]) -> tuple[str, bool]:
    """(verdict code, strict). Step 3 (the close) decides failure or not; steps 1 and 2 say how clean it is. `strict` is
    the design doc's three-step rule: the news favoured the crowd, the first minute went their way, the close went
    against them. The live alert rule is looser (any event + a close against), which `alerted` records."""
    if close_z is None:
        return "pending", False
    against = close_z < 0 if crowd_sign(direction) == 1 else close_z > 0
    if against:
        if news_cls == "WITH":
            if (fm or {}).get("status") == "ok" and fm["move"] > FM_FLAT_BAND:
                return "failure_full", True
            return "failure", False
        return ("followed_news" if news_cls == "AGAINST" else "against_unread"), False
    return {"WITH": "followed_news", "AGAINST": "shrugged"}.get(news_cls, "no_failure"), False


def _watch_row(ev: dict, market: str, direction: str, level: str, report_date: date, read: str) -> dict:
    return {"event_date": ev["event_date"], "event_type": ev["event_type"], "market": market,
            "release_et": ev.get("release_et"), "direction": direction, "level": level, "report_date": report_date,
            "read": read, "crowd_outcome": "", "series": [], "forecast_seen_at": None, "news_class": None,
            "surprise_z": None, "first_minute": None, "close_z": None, "close_against": None, "verdict": None,
            "strict": None, "alerted": None, "judged_at": None}


def upcoming_watch_row(ev: dict, market: str, direction: str, level: str, report_date: date, old: Optional[dict],
                       fresh: Optional[dict], now: datetime) -> dict:
    """A row for an event that has not been judged: the forecast as last read BEFORE the release, plus the sentence."""
    et = ev["event_type"]
    row = _watch_row(ev, market, direction, level, report_date, watch_read(et, market))
    rel = ev.get("release_et")
    released = rel is not None and now >= rel
    names = watch_series_names(et, market)
    row["series"] = merge_series(names, (old or {}).get("series"), fresh, released)
    seen = (old or {}).get("forecast_seen_at")
    if not released and any(((fresh or {}).get(n) or {}).get("forecast") for n in names):
        seen = now
    row["forecast_seen_at"] = seen
    row["crowd_outcome"] = crowd_outcome_words(et, market, direction, row["series"])
    return row


def frozen_news_class(event_type: str, market: str, direction: str, day: date, series: list[dict]) -> Optional[dict]:
    """news_class scored on the LINED-UP forecast: the figure stored before the release (`forecast`), against the actual.
    None = no series holds both a stored pre-release figure and an actual (or it cannot be read): the caller then falls
    back to the release-day read, which the card labels "forecast read after the release". (His 11-25 words: "news to
    watch for and what's expectation, once news is here, we assess vs expectation.")"""
    pairs = [(s["name"], s["forecast"], s["actual"]) for s in series if _blank(s.get("forecast")) and _blank(s.get("actual"))]
    if not pairs:
        return None
    if event_type.startswith("EARN_"):
        tk = event_type[5:]
        a, f = parse_number(pairs[0][2]), parse_number(pairs[0][1])
        if a is None or not f or tk not in EARNINGS_RMS:
            return None
        sur = {(day, event_type): {"z": (a - f) / abs(f) * 100 / EARNINGS_RMS[tk], "text": f"{tk} EPS {pairs[0][2]} vs {pairs[0][1]}"}}
    else:
        ts = datetime(day.year, day.month, day.day, 12, 0, tzinfo=_ET).isoformat()
        sur = surprises_from_fx([{"date": ts, "name": n, "forecast": f, "actual": a} for n, f, a in pairs])
    nc = news_class(event_type, market, direction, day, sur)
    return None if nc["cls"] == "UNKNOWN" else nc


def judged_watch_row(ev: dict, market: str, direction: str, level: str, report_date: date, old: Optional[dict],
                     fresh: Optional[dict], nc: dict, fm: dict, feat: Optional[dict], alerted: bool,
                     now: datetime) -> dict:
    """The row for an event day, judged after the close. `nc` is `news_class()` (the same value the alert label uses),
    `fm` is `first_minute()`, `feat` the day's `features_at()` (None = no bar), `alerted` = a news alert was stored."""
    et = ev["event_type"]
    row = _watch_row(ev, market, direction, level, report_date, watch_read(et, market))
    row["series"] = merge_series(watch_series_names(et, market), (old or {}).get("series"), fresh, True)
    row["forecast_seen_at"] = (old or {}).get("forecast_seen_at")
    row["crowd_outcome"] = crowd_outcome_words(et, market, direction, row["series"])
    # scored on the figure lined up BEFORE the release; only when none was ever stored does the release-day read (`nc`) stand
    nc = frozen_news_class(et, market, direction, ev["event_date"], row["series"]) or nc
    row["news_class"], row["surprise_z"], row["first_minute"] = nc["cls"], nc["z"], fm
    if feat is not None:
        z = feat["z"]
        row["close_z"] = z
        row["close_against"] = z < 0 if crowd_sign(direction) == 1 else z > 0
    row["verdict"], row["strict"] = watch_verdict(row["close_z"], direction, nc["cls"], fm)
    row["alerted"], row["judged_at"] = alerted, now
    return row


# ═══════════════════════════════════════════════════════════════════════════════════════════════
# Messages (pure; the paper tag routes them to the paper chat through briefing.send_telegram_message)
# ═══════════════════════════════════════════════════════════════════════════════════════════════
HEADER = "*COT family — research alerts, no orders*"


def _px(v: float) -> str:
    return f"{v:.6g}" if abs(v) < 10 else f"{v:,.2f}"


def _ix(v) -> str:
    return "  -" if v is None else f"{v:>3d}"


def _index_line(r: dict) -> str:
    return f"C{_ix(r['comm'])} L{_ix(r['lspec'])} S{_ix(r['sspec'])}"


def _event_words(events: list[str]) -> str:
    return ", ".join(e.replace("EARN_", "earnings ").replace("_", " ") for e in events)


def format_weekly_message(report_date: date, rows: dict[str, dict], prev: dict[str, dict], exits: list[dict],
                          friday: list[dict], entry_label: str, notes: list[str]) -> str:
    """The ONE weekly message. `rows` / `prev`: this and last week's {market: index row}."""
    from agents.market_intelligence.constants import mode_prefix
    main = sorted((m for m, r in rows.items() if r["setup"]), key=lambda m: (rows[m]["setup"], m))
    close = sorted((m for m, r in rows.items() if r["close_setup"]), key=lambda m: (rows[m]["close_setup"], m))
    out = [f"{mode_prefix('paper')}{HEADER}",
           f"COT report of {report_date.isoformat()}. Our rebuilt index, no price adjustment. "
           "C = Commercials, L = large speculators, S = small speculators; 0 = most short, 100 = most long. "
           "A set up is a condition, not a trade: the trade needs a failure day."]

    def block(title, markets, key):
        lines = [title]
        for m in markets:
            r = rows[m]
            new = "" if (prev.get(m) or {}).get(key) == r[key] else "  new"
            lines.append(f"{name_of(m):<18s} {r[key]:<5s} {_index_line(r)}{new}")
        return lines

    body = block("SET UP (fade the crowd)", main, "setup") if main else ["SET UP: none this week"]
    if close:
        body += [""] + block("CLOSE TO A SET UP (Commercials at max, speculators not there yet)", close, "close_setup")
    if exits:
        body += ["", "LEFT A SET UP / BACK TO NEUTRAL (exit signal if held)"]
        for x in exits:
            why = " + ".join(w for w, on in (("left", x["left"]), ("neutral ~50", x["neutral"])) if on)
            body.append(f"{name_of(x['market']):<18s} was {x['direction']:<5s} {_index_line(x)}  {why}")
    out.append("```\n" + "\n".join(body) + "\n```")
    if friday:
        lines = []
        for a in friday:
            what = " + ".join(a["kinds"]) + (f" ({_event_words(a['events'])})" if a["events"] else "")
            lines += [f"{name_of(a['market'])} {a['direction'].upper()}  failure day {a['failure_day']:%a %m-%d}: {what}",
                      f"  entry: {entry_label}   stop: {a['stop_rule']}"]
        out.append("Friday confirmation: the set up completed this week after a failure day.\n```\n"
                   + "\n".join(lines) + "\n```")
    out += notes
    return "\n".join(out)


def format_daily_message(day: date, report_date: date, alerts: list[dict]) -> Optional[str]:
    """The ONE daily message; None when there is no alert (silence)."""
    if not alerts:
        return None
    from agents.market_intelligence.constants import mode_prefix
    lines = []
    for a in sorted(alerts, key=lambda a: a["market"]):
        what = " + ".join(a["kinds"]) + (f" ({_event_words(a['events'])})" if a["events"] else "")
        lines += [f"{name_of(a['market'])} {a['direction'].upper()}  {what}",
                  f"  {'main' if a['level'] == 'main' else 'close-list'} set up, {_index_line(a)}",
                  f"  entry: today's close {_px(a['close'])} (or the next open)",
                  f"  stop: {a['stop_rule']}"]
        if a.get("bar_suspect"):
            lines.append("  price bar looks broken (close or open outside the day's range): check the stop on a chart")
        if a.get("peer_z") is not None and "correlation" in a["kinds"]:
            lines.append(f"  peers closed {a['peer_z']:+.2f} of a day's range the crowd's way")
        if "news" in a["kinds"]:
            fm = a.get("first_minute") or {}
            if fm.get("status") == "ok" and fm["move"] >= 0:
                lines.append(f"  first minute: {fm['move']:.2f} of a day's range the crowd's way"
                             f" ({'big' if fm['big'] else 'small'})")
            elif fm.get("status") == "ok":
                lines.append(f"  first minute: {-fm['move']:.2f} of a day's range AGAINST the crowd")
            else:
                lines.append(f"  first minute: unknown ({fm.get('status', 'not read')})")
            lines.append(f"  news vs consensus: {CLASS_WORDS[a.get('news_class', 'UNKNOWN')]}")
            for t in a.get("news_text") or []:
                lines.append(f"    {t}")
        lines.append("")
    return (f"{mode_prefix('paper')}{HEADER}\n"
            f"{day.isoformat()}: {len(alerts)} failure day{'s' if len(alerts) != 1 else ''} in a set-up market "
            f"(COT report of {report_date.isoformat()}). Fade the crowd; the stop is a daily CLOSE beyond the level, "
            "never trailed. Yahoo closes are last trades, not settlements.\n"
            "```\n" + "\n".join(lines).rstrip() + "\n```")


# ═══════════════════════════════════════════════════════════════════════════════════════════════
# I/O — network and database. Replaced whole in tests.
# ═══════════════════════════════════════════════════════════════════════════════════════════════
CFTC_API = "https://publicreporting.cftc.gov/resource/6dca-aqww.json"       # legacy, futures only
CFTC_ZIP = "https://www.cftc.gov/files/dea/history/deacot{year}.zip"
FX_URL = "https://www.fxempire.com/api/v1/en/economic-calendar"
WASDE_URL = ("https://www.usda.gov/about-usda/general-information/staff-offices/office-chief-economist/"
             "commodity-markets/wasde-report")
_UA = "Mozilla/5.0 (research script; personal use)"
_API_FIELDS = ("report_date_as_yyyy_mm_dd", "cftc_contract_market_code", "open_interest_all",
               "noncomm_positions_long_all", "noncomm_positions_short_all", "comm_positions_long_all",
               "comm_positions_short_all", "nonrept_positions_long_all", "nonrept_positions_short_all")
_ZIP_FIELDS = {"date": "As of Date in Form YYYY-MM-DD", "code": "CFTC Contract Market Code",
               "oi": "Open Interest (All)", "nc_long": "Noncommercial Positions-Long (All)",
               "nc_short": "Noncommercial Positions-Short (All)", "c_long": "Commercial Positions-Long (All)",
               "c_short": "Commercial Positions-Short (All)", "nr_long": "Nonreportable Positions-Long (All)",
               "nr_short": "Nonreportable Positions-Short (All)"}


def _http_get(url: str, params: dict | None = None, timeout: float = 60.0):
    import httpx  # lazy: scheduler.py is on the execution image's module list
    return httpx.get(url, params=params, headers={"User-Agent": _UA}, timeout=timeout, follow_redirects=True)


def _net_row(code, rd, c_long, c_short, nc_long, nc_short, nr_long, nr_short, oi) -> tuple:
    f = lambda v: int(float(v))  # noqa: E731
    return (str(code).strip(), rd, f(c_long) - f(c_short), f(nc_long) - f(nc_short), f(nr_long) - f(nr_short), f(oi))


def fetch_cftc_api(since: date, get=_http_get) -> list[tuple]:
    """(code, report_date, comm net, large-spec net, small-spec net, open interest) for our contracts since `since`."""
    codes = ", ".join(f"'{c}'" for c in ALL_CODES)
    r = get(CFTC_API, {"$select": ", ".join(_API_FIELDS),
                       "$where": f"report_date_as_yyyy_mm_dd >= '{since.isoformat()}T00:00:00.000' "
                                 f"AND cftc_contract_market_code in ({codes})",
                       "$order": "report_date_as_yyyy_mm_dd", "$limit": "50000"})
    if r.status_code != 200:
        raise CotError(f"CFTC API answered {r.status_code}")
    out = []
    for j in r.json():
        out.append(_net_row(j["cftc_contract_market_code"], date.fromisoformat(j["report_date_as_yyyy_mm_dd"][:10]),
                            j["comm_positions_long_all"], j["comm_positions_short_all"],
                            j["noncomm_positions_long_all"], j["noncomm_positions_short_all"],
                            j["nonrept_positions_long_all"], j["nonrept_positions_short_all"], j["open_interest_all"]))
    if len(out) >= 50000:
        raise CotError("CFTC API answer hit the row limit (the window is cut)")
    return out


def fetch_cftc_zip(years, since: date, get=_http_get) -> list[tuple]:
    """The same rows from the yearly history files (the research's source), for when the API is down."""
    out = []
    for y in years:
        r = get(CFTC_ZIP.format(year=y), timeout=120.0)
        if r.status_code != 200 or not r.content.startswith(b"PK"):
            raise CotError(f"CFTC history file {y}: not a zip (http {r.status_code})")
        with zipfile.ZipFile(_io.BytesIO(r.content)) as z:
            text = z.read(z.namelist()[0]).decode("utf-8", errors="replace")
        rd = csv.DictReader(_io.StringIO(text))
        rd.fieldnames = [c.strip() for c in rd.fieldnames or []]
        for row in rd:
            code = (row[_ZIP_FIELDS["code"]] or "").strip()
            if code not in ALL_CODES:
                continue
            d = date.fromisoformat(row[_ZIP_FIELDS["date"]].strip())
            if d < since:
                continue
            g = lambda k: row[_ZIP_FIELDS[k]].strip()  # noqa: E731
            out.append(_net_row(code, d, g("c_long"), g("c_short"), g("nc_long"), g("nc_short"), g("nr_long"),
                                g("nr_short"), g("oi")))
    return out


def fetch_fxempire(country: str, d0: date, d1: date, get=_http_get, sleep=_time.sleep) -> list[dict]:
    """Raw calendar events, one request per page. 401 / 403 / 429 stops the run (CalendarRefused)."""
    out, page = [], 1
    while page <= 12:
        r = get(FX_URL, {"dateFrom": d0.isoformat(), "dateTo": d1.isoformat(), "country": country, "page": str(page)},
                40.0)
        if r.status_code in (401, 403, 429):
            raise CalendarRefused(f"fxempire calendar refused the request ({r.status_code}) for {country}")
        if r.status_code != 200:
            raise CotError(f"fxempire calendar answered {r.status_code} for {country}")
        try:
            j = r.json()
        except ValueError as e:
            raise CotError(f"fxempire calendar for {country}: the answer is not JSON ({type(e).__name__})") from e
        # An HTTP 200 whose body is empty or reshaped must never read as "no events" (the caller would then drop the
        # stored future rows). The real answer always carries both keys, also for an empty range (seen 2026-11-15).
        if not isinstance(j, dict) or not isinstance(j.get("calendar"), list) or "last" not in j:
            raise CotError(f"fxempire calendar for {country}: the answer has no 'calendar' list / 'last' flag "
                           "(the body changed shape)")
        for day in j["calendar"]:
            out.extend(day.get("events", []))
        if j["last"]:
            return out
        page += 1
        sleep(1.5)
    raise CotError(f"fxempire calendar for {country} {d0}..{d1} did not end within 12 pages")


def _bars_from_frame(df) -> list[tuple]:
    out = []
    if df is None or len(df) == 0:
        return out
    for ts, (o, h, l, c) in zip(df.index, df[["Open", "High", "Low", "Close"]].itertuples(index=False)):
        d = ts.date()
        if c != c or h != h or l != l or d.weekday() >= 5:
            continue
        out.append((d, float(o), float(h), float(l), float(c)))
    return sorted(out)


def fetch_daily_bars(ticker: str) -> list[tuple]:
    import yfinance as yf  # lazy, like collector.py
    return _bars_from_frame(yf.Ticker(ticker).history(period="3mo", interval="1d", auto_adjust=False))


def fetch_minute_frame(ticker: str, period: str = "5d"):
    """The ONE 1-minute pull (extended hours included). cot_minutes_archive reads the same frame over 8 days."""
    import yfinance as yf
    return yf.Ticker(ticker).history(period=period, interval="1m", prepost=True, auto_adjust=False)


def et_index(df):
    """The frame's bar times in ET (a naive index is UTC)."""
    idx = df.index
    if getattr(idx, "tz", None) is None:
        idx = idx.tz_localize("UTC")
    return idx.tz_convert(_ET)


def fetch_minute_bars(ticker: str) -> list[tuple]:
    df = fetch_minute_frame(ticker)
    if df is None or len(df) == 0:
        return []
    return [(ts.to_pydatetime(), float(c)) for ts, c in zip(et_index(df), df["Close"]) if c == c]


def fetch_earnings(ticker: str) -> list[dict]:
    """[{ts (tz-aware), surprise_pct, reported, estimate}] newest first."""
    import yfinance as yf
    df = yf.Ticker(ticker).get_earnings_dates(limit=8)
    out = []
    if df is None:
        return out
    for ts, row in df.iterrows():
        g = lambda k: (None if row.get(k) != row.get(k) else float(row.get(k)))  # noqa: E731
        out.append({"ts": ts.to_pydatetime(), "surprise_pct": g("Surprise(%)"), "reported": g("Reported EPS"),
                    "estimate": g("EPS Estimate")})
    return out


_COT_NETS_UPSERT_SQL = """
    INSERT INTO mi_cot_nets_weekly (code, report_date, comm_net, lspec_net, sspec_net, open_interest)
    VALUES ($1, $2, $3, $4, $5, $6)
    ON CONFLICT (code, report_date) DO UPDATE SET comm_net = EXCLUDED.comm_net, lspec_net = EXCLUDED.lspec_net,
        sspec_net = EXCLUDED.sspec_net, open_interest = EXCLUDED.open_interest
"""
_COT_WEEK_UPSERT_SQL = """
    INSERT INTO mi_cot_weeks (report_date, known_from) VALUES ($1, $2)
    ON CONFLICT (report_date) DO NOTHING
"""
_COT_INDEX_UPSERT_SQL = """
    INSERT INTO mi_cot_index_weekly (report_date, market, comm, lspec, sspec, setup, close_setup,
                                     comm_net, lspec_net, sspec_net, lookback_weeks)
    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
    ON CONFLICT (report_date, market) DO UPDATE SET comm = EXCLUDED.comm, lspec = EXCLUDED.lspec,
        sspec = EXCLUDED.sspec, setup = EXCLUDED.setup, close_setup = EXCLUDED.close_setup,
        comm_net = EXCLUDED.comm_net, lspec_net = EXCLUDED.lspec_net, sspec_net = EXCLUDED.sspec_net,
        lookback_weeks = EXCLUDED.lookback_weeks
"""
_COT_WEEK_SENT_SQL = "UPDATE mi_cot_weeks SET message_sent_at = NOW() WHERE report_date = $1"
# No look-ahead: the week a day may use is the latest one KNOWN BEFORE that day.
_COT_KNOWN_WEEK_SQL = "SELECT MAX(report_date) FROM mi_cot_weeks WHERE known_from < $1"
_COT_CALENDAR_UPSERT_SQL = """
    INSERT INTO mi_cot_calendar (event_date, event_type, release_et, source) VALUES ($1, $2, $3, $4)
    ON CONFLICT (event_date, event_type) DO UPDATE SET release_et = EXCLUDED.release_et, source = EXCLUDED.source,
        refreshed_at = NOW()
"""
_COT_ALERT_COLS = ("alert_date", "market", "direction", "kind", "level", "report_date", "events", "z", "peer_z",
                   "entry_price", "entry_note", "stop_price", "stop_rule", "failure_day", "comm", "lspec", "sspec",
                   "first_minute", "first_minute_big", "news_class", "detail")
_COT_ALERT_UPSERT_SQL = (
    f"INSERT INTO mi_cot_alerts ({', '.join(_COT_ALERT_COLS)}) VALUES ("
    + ", ".join(f"${i + 1}{'::jsonb' if c == 'detail' else ''}" for i, c in enumerate(_COT_ALERT_COLS))
    + ") ON CONFLICT (alert_date, market, direction, kind) DO UPDATE SET "
    + ", ".join(f"{c} = EXCLUDED.{c}" for c in _COT_ALERT_COLS if c not in ("alert_date", "market", "direction", "kind"))
    + " RETURNING id, sent_at")
_COT_ALERTS_SENT_SQL = "UPDATE mi_cot_alerts SET sent_at = NOW() WHERE id = ANY($1::int[])"
_COT_WATCH_COLS = ("event_date", "event_type", "market", "release_et", "direction", "level", "report_date", "read",
                   "crowd_outcome", "series", "forecast_seen_at", "news_class", "surprise_z", "first_minute", "close_z",
                   "close_against", "verdict", "strict", "alerted", "judged_at")
_COT_WATCH_JSON = ("series", "first_minute")
_COT_WATCH_UPSERT_SQL = (
    f"INSERT INTO mi_cot_news_watch ({', '.join(_COT_WATCH_COLS)}) VALUES ("
    + ", ".join(f"${i + 1}{'::jsonb' if c in _COT_WATCH_JSON else ''}" for i, c in enumerate(_COT_WATCH_COLS))
    + ") ON CONFLICT (event_date, event_type, market) DO UPDATE SET "
    + ", ".join(f"{c} = EXCLUDED.{c}" for c in _COT_WATCH_COLS if c not in ("event_date", "event_type", "market"))
    + ", updated_at = NOW()")
_COT_WATCH_DELETE_SQL = "DELETE FROM mi_cot_news_watch WHERE event_date BETWEEN $1 AND $2"
_COT_WATCH_READ_SQL = f"SELECT {', '.join(_COT_WATCH_COLS)} FROM mi_cot_news_watch WHERE event_date BETWEEN $1 AND $2"


class Io:
    """Every network and database touch of the two jobs. Tests subclass it."""

    # ── network (blocking; the jobs call these through asyncio.to_thread) ──
    def cftc(self, since: date, today: date) -> tuple[list[tuple], str]:
        try:
            return fetch_cftc_api(since), "api"
        except Exception as e:  # loud-ok: the fallback source is tried next; if it fails too, that raise is the page
            logger.warning(f"cot: CFTC API failed ({type(e).__name__}: {e}); trying the yearly history files")
            return fetch_cftc_zip(range(since.year, today.year + 1), since), "zip"

    def daily_bars(self, ticker: str) -> list[tuple]:
        return fetch_daily_bars(ticker)

    def minute_bars(self, ticker: str) -> list[tuple]:
        return fetch_minute_bars(ticker)

    def fxempire(self, country: str, d0: date, d1: date) -> list[dict]:
        return fetch_fxempire(country, d0, d1)

    def wasde_dates(self) -> list[date]:
        r = _http_get(WASDE_URL, timeout=40.0)
        if r.status_code != 200:
            raise CotError(f"usda.gov WASDE page answered {r.status_code}")
        dates = parse_wasde_dates(r.text)
        if not dates:
            raise CotError("usda.gov WASDE page: no release dates found (the page changed)")
        return dates

    def earnings(self, ticker: str) -> list[dict]:
        return fetch_earnings(ticker)

    def pause(self, seconds: float) -> None:
        _time.sleep(seconds)

    def is_stock_holiday(self, day: date) -> bool:
        """A weekday the US stock market is shut. Futures follow it only on the full holidays, so this is asked
        ONLY when no set-up market has a bar for the day: holiday -> a quiet day, otherwise -> a data failure."""
        from agents.market_intelligence.trading_calendar import get_market_status
        return not get_market_status(day).is_trading_day

    # ── database ──
    async def _pool(self):
        from agents.market_intelligence.db import get_pool
        return await get_pool()

    async def load_nets(self) -> dict[str, dict[date, tuple]]:
        pool = await self._pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch("SELECT code, report_date, comm_net, lspec_net, sspec_net FROM mi_cot_nets_weekly")
        out: dict[str, dict[date, tuple]] = {}
        for r in rows:
            out.setdefault(r["code"], {})[r["report_date"]] = (r["comm_net"], r["lspec_net"], r["sspec_net"])
        return out

    async def upsert_nets(self, rows: list[tuple]) -> None:
        if not rows:
            return
        pool = await self._pool()
        async with pool.acquire() as conn:
            await conn.executemany(_COT_NETS_UPSERT_SQL, rows)

    async def latest_week(self) -> Optional[dict]:
        pool = await self._pool()
        async with pool.acquire() as conn:
            r = await conn.fetchrow("SELECT report_date, known_from, message_sent_at FROM mi_cot_weeks "
                                    "ORDER BY report_date DESC LIMIT 1")
        return dict(r) if r else None

    async def store_week(self, report_date: date, known_from: date, rows: dict[str, dict]) -> None:
        vals = [(report_date, m, r["comm"], r["lspec"], r["sspec"], r["setup"], r["close_setup"], *r["nets"],
                 r["lookback"]) for m, r in rows.items()]
        pool = await self._pool()
        async with pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(_COT_WEEK_UPSERT_SQL, report_date, known_from)
                if vals:
                    await conn.executemany(_COT_INDEX_UPSERT_SQL, vals)

    async def mark_week_sent(self, report_date: date) -> None:
        pool = await self._pool()
        async with pool.acquire() as conn:
            await conn.execute(_COT_WEEK_SENT_SQL, report_date)

    async def known_week(self, day: date) -> Optional[tuple[date, dict[str, dict]]]:
        """(report_date, {market: row}) of the latest week known BEFORE `day`, or None."""
        pool = await self._pool()
        async with pool.acquire() as conn:
            rd = await conn.fetchval(_COT_KNOWN_WEEK_SQL, day)
            if rd is None:
                return None
            rows = await conn.fetch("SELECT market, comm, lspec, sspec, setup, close_setup FROM mi_cot_index_weekly "
                                    "WHERE report_date = $1", rd)
        return rd, {r["market"]: dict(r) for r in rows}

    async def calendar_age_days(self, today: date) -> Optional[int]:
        """Days since the last WEEKLY (full) calendar refresh, read off the WASDE rows it rewrites; None = never."""
        pool = await self._pool()
        async with pool.acquire() as conn:
            ts = await conn.fetchval("SELECT MAX(refreshed_at) FROM mi_cot_calendar WHERE source = $1", WASDE_SOURCE)
        return None if ts is None else (today - ts.astimezone(_ET).date()).days

    async def replace_calendar(self, today: date, rows: list[dict], sources: list[str], until: date) -> None:
        """Upsert `rows`; the refreshed sources' rows dated AFTER today and up to `until` are dropped first (a moved
        release must not leave its old date behind). Today's and past rows are never deleted: the Friday check
        reads the week's events."""
        pool = await self._pool()
        async with pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute("DELETE FROM mi_cot_calendar WHERE event_date > $1 AND event_date <= $2 "
                                   "AND source = ANY($3::text[])", today, until, sources)
                await conn.executemany(_COT_CALENDAR_UPSERT_SQL,
                                       [(r["event_date"], r["event_type"], r["release_et"], r["source"]) for r in rows])

    async def calendar(self, d0: date, d1: date) -> list[dict]:
        pool = await self._pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch("SELECT event_date, event_type, release_et FROM mi_cot_calendar "
                                    "WHERE event_date BETWEEN $1 AND $2 ORDER BY event_date, event_type", d0, d1)
        return [dict(r) for r in rows]

    async def calendar_first_date(self) -> Optional[date]:
        """The earliest stored event date; None = the table is empty. The Friday check reads the sources itself for
        any part of its window that lies before this (a new install holds nothing before its first day)."""
        pool = await self._pool()
        async with pool.acquire() as conn:
            return await conn.fetchval("SELECT MIN(event_date) FROM mi_cot_calendar")

    async def watch_rows(self, d0: date, d1: date) -> list[dict]:
        """The stored news-watch rows with event_date in d0..d1."""
        pool = await self._pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(_COT_WATCH_READ_SQL, d0, d1)
        out = []
        for r in rows:
            d = dict(r)
            for k in _COT_WATCH_JSON:       # the pool's jsonb codec decodes; a plain string is decoded here
                if isinstance(d.get(k), str):
                    d[k] = json.loads(d[k])
            out.append(d)
        return out

    async def replace_watch(self, d0: date, d1: date, rows: list[dict]) -> None:
        """Make the stored rows dated d0..d1 EXACTLY `rows` (a market no longer set up, or a moved event, leaves no row
        behind). The rows already carry everything worth keeping (the caller read the old ones first)."""
        pool = await self._pool()
        async with pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(_COT_WATCH_DELETE_SQL, d0, d1)
                if rows:
                    # the pool's jsonb codec json.dumps()es the bind itself: pass plain objects, never strings
                    await conn.executemany(_COT_WATCH_UPSERT_SQL, [
                        [json.loads(json.dumps(r.get(c), default=str)) if c in _COT_WATCH_JSON else r.get(c)
                         for c in _COT_WATCH_COLS] for r in rows])

    async def store_alerts(self, rows: list[dict]) -> list[dict]:
        """Upsert; returns the rows NOT yet sent, each with its id."""
        out = []
        pool = await self._pool()
        async with pool.acquire() as conn:
            for r in rows:
                rec = await conn.fetchrow(_COT_ALERT_UPSERT_SQL, *[
                    # the pool's jsonb codec json.dumps()es the bind itself; a string here is stored as a JSON
                    # string (double-encoded, 11-17). Round-trip to plain JSON types (dates -> str) and pass the object.
                    json.loads(json.dumps(r.get(c), default=str)) if c == "detail" else r.get(c)
                    for c in _COT_ALERT_COLS])
                if rec["sent_at"] is None:
                    out.append({**r, "id": rec["id"]})
        return out

    async def mark_alerts_sent(self, ids: list[int]) -> None:
        if not ids:
            return
        pool = await self._pool()
        async with pool.acquire() as conn:
            await conn.execute(_COT_ALERTS_SENT_SQL, ids)

    async def audit(self, event: str, summary: str, detail: dict) -> None:
        from agents.market_intelligence.db import log_audit_event
        await log_audit_event(event, summary[:300], json.dumps(detail, default=str))


# ═══════════════════════════════════════════════════════════════════════════════════════════════
# Shared steps
# ═══════════════════════════════════════════════════════════════════════════════════════════════
async def _send(text: str) -> bool:
    """The one send. A module-level function called BY NAME from both jobs (not a method on `Io`), so the derived
    job census (scripts/check_job_date_sources.py) sees that these jobs reach a Telegram sender. The text starts with
    the paper tag, so briefing.send_telegram_message routes it to the paper chat (#699)."""
    from agents.market_intelligence.briefing import send_telegram_message
    return await send_telegram_message(text)


async def _bars_for(io: Io, markets, errors: dict) -> dict[str, list[tuple]]:
    """Daily bars per market; one market's failure is recorded and never stops the rest."""
    out = {}
    for m in sorted(set(markets)):
        try:
            out[m] = await asyncio.to_thread(io.daily_bars, ticker_of(m))
        except Exception as e:  # loud-ok: counted in the run's audit row; an all-fail run raises after it
            logger.warning(f"cot: daily bars for {m} failed: {type(e).__name__}: {e}")
            errors[m] = f"{type(e).__name__}: {e}"[:160]
    return out


def _with_peers(markets) -> set[str]:
    return set(markets) | {p for m in markets for p, _s in PEERS.get(m, [])}


def _events_by_day(cal_rows: list[dict], market: str) -> dict[date, list[dict]]:
    out: dict[date, list[dict]] = {}
    for r in cal_rows:
        if market in markets_for_event(r["event_type"]):
            out.setdefault(r["event_date"], []).append(r)
    return out


def _alert_row(day: date, a: dict, kind: str, level: str, report_date: date, ix: dict, entry_note: str,
               failure_day: Optional[date] = None) -> dict:
    fm = a.get("first_minute") or {}
    detail = {"kinds": a["kinds"], "first_minute": fm, "news": a.get("news_detail"), "atr": a.get("atr")}
    if a.get("bar_suspect"):
        detail["bar_suspect"] = True
    # A Friday confirmation is entered at the NEXT open, a price not known yet: no entry price is stored (the failure
    # day's close is kept in `detail`, it is not the entry).
    entry = a["close"]
    if kind == "friday":
        entry, detail["failure_day_close"] = None, a["close"]
    return {"alert_date": day, "market": a["market"], "direction": a["direction"], "kind": kind, "level": level,
            "report_date": report_date, "events": ";".join(a["events"]), "z": a["z"], "peer_z": a["peer_z"],
            "entry_price": entry, "entry_note": entry_note, "stop_price": a["stop"], "stop_rule": a["stop_rule"],
            "failure_day": failure_day, "comm": ix["comm"], "lspec": ix["lspec"], "sspec": ix["sspec"],
            "first_minute": fm.get("move"), "first_minute_big": fm.get("big"), "news_class": a.get("news_class"),
            "detail": detail}


US_SOURCE = "fxempire.com economic calendar (united-states)"
FAR = date(2099, 12, 31)


async def read_us_week(io: Io, monday: date) -> tuple[list[dict], list[dict]]:
    """One whole US week from the source -> (raw events, trigger rows dated in that week). A week with NO trigger row
    is a FAILED read (CotError): every real week lists the EIA releases, so an empty answer means the source answered
    200 with an empty or renamed body — and reading it as "no events" would drop the stored rows. (Checked on the
    weeks of 2026-11-09 / 11-16 / 11-23: 2-3 trigger rows each.)"""
    sunday = monday + timedelta(days=6)
    events = await asyncio.to_thread(io.fxempire, "united-states", monday, sunday)
    rows = [r for r in calendar_rows_from_fx(events) if monday <= r["event_date"] <= sunday]
    if not rows:
        raise CotError(f"fxempire listed no trigger event for the US week of {monday} ({len(events)} events read): "
                       "taken as a failed read, the stored rows are kept")
    return events, rows


async def refresh_this_week(io: Io, today: date) -> list[dict]:
    """EVERY day: this week's US calendar, read fresh (the source lists a release only a week or two ahead, and can
    move one). Returns the raw events — the same read carries the day's actual-vs-consensus numbers. Raises, and
    then nothing stored is touched."""
    monday = today - timedelta(days=today.weekday())
    events, rows = await read_us_week(io, monday)
    await io.replace_calendar(today, rows, [US_SOURCE], monday + timedelta(days=6))
    return events


async def read_past_calendar(io: Io, d0: date, d1: date, fx_ok: bool = True) -> tuple[list[dict], list[str]]:
    """The news days d0..d1 read from the SOURCES instead of the table, for a Friday check whose window starts before
    the table does (a new install). US weeks before this one (this week's is read fresh every day), the central-bank
    decisions, WASDE and the earnings dates. -> (rows, the sources that could not be read, in plain words). Nothing
    is stored. `fx_ok=False`: FXEmpire refused a request earlier in this run, so it is not asked again."""
    rows: list[dict] = []
    failed: list[str] = []
    this_monday = d1 - timedelta(days=d1.weekday())
    if fx_ok:
        try:
            monday = d0 - timedelta(days=d0.weekday())
            while monday < this_monday:
                rows += (await read_us_week(io, monday))[1]
                await asyncio.to_thread(io.pause, 1.5)
                monday += timedelta(days=7)
        except Exception as e:  # loud-ok: named in the weekly message (the blind line) and the audit row
            logger.warning(f"cot: past US calendar {d0}..{d1} could not be read: {type(e).__name__}: {e}")
            failed.append("US releases")
            fx_ok = not isinstance(e, CalendarRefused)
    else:
        failed.append("US releases")
    if fx_ok:
        try:
            for country in FX_CENTRAL_BANKS:
                rows += calendar_rows_from_fx(await asyncio.to_thread(io.fxempire, country, d0, d1), country)
                await asyncio.to_thread(io.pause, 1.5)
        except Exception as e:  # loud-ok: named in the weekly message (the blind line) and the audit row
            logger.warning(f"cot: past central-bank calendar {d0}..{d1} could not be read: {type(e).__name__}: {e}")
            failed.append("central-bank decisions")
    else:
        failed.append("central-bank decisions")
    try:
        rows += calendar_rows_from_wasde(await asyncio.to_thread(io.wasde_dates))
    except Exception as e:  # loud-ok: named in the weekly message (the blind line) and the audit row
        logger.warning(f"cot: past WASDE dates could not be read: {type(e).__name__}: {e}")
        failed.append("WASDE")
    rows += calendar_rows_from_opec(d0=d0, d1=d1) + calendar_rows_from_usda_exports(d0, d1)     # a table and a rule: no read to fail
    bad = 0
    for tk in EARNINGS_TICKERS:
        try:
            rows += calendar_rows_from_earnings(tk, [e["ts"] for e in await asyncio.to_thread(io.earnings, tk)])
        except Exception as e:  # loud-ok: counted; named in the weekly message (the blind line) and the audit row
            logger.warning(f"cot: past earnings dates for {tk} could not be read: {type(e).__name__}: {e}")
            bad += 1
    if bad:
        failed.append(f"earnings dates ({bad} of {len(EARNINGS_TICKERS)} companies)")
    return [r for r in rows if d0 <= r["event_date"] <= d1], failed


async def refresh_calendar(io: Io, today: date, fx_ok: bool = True, raw_out: Optional[dict] = None) -> dict:
    """WEEKLY: the forward calendar beyond this week (3 more weeks of US macro / EIA, central-bank decisions, WASDE
    dates, earnings). Returns {rows, errors}; a source that fails keeps its stored rows. `fx_ok=False` (fxempire
    refused today's request) skips its sources. `raw_out`: filled with the raw FXEmpire rows it read (a country slug ->
    rows; ("united-states", that week's Monday) -> rows) so the news watch keeps their forecasts without a second request."""
    monday = today - timedelta(days=today.weekday())
    sunday = monday + timedelta(days=6)
    errors: dict[str, str] = {}
    n = 0

    async def take(label, fn, source, first: date):
        """Store one source's rows dated `first` or later."""
        nonlocal n
        try:
            got, whole = await asyncio.to_thread(fn)
        except CalendarRefused as e:
            errors[label] = f"REFUSED: {e}"[:160]
            raise
        except Exception as e:  # loud-ok: recorded per source; the run raises after its audit row when one failed
            logger.warning(f"cot: calendar source {label} failed: {type(e).__name__}: {e}")
            errors[label] = f"{type(e).__name__}: {e}"[:160]
            return
        got = [r for r in got if r["event_date"] >= first]
        # stored rows from `first` on (never today's or earlier) are replaced; a partly-read source only ADDS rows
        # (its other future rows are kept): its delete window is empty
        floor = max(today, first - timedelta(days=1))
        await io.replace_calendar(floor, got, [source], FAR if whole else floor)
        n += len(got)

    async def take_us():
        """The 3 US weeks after this one, each replaced ON ITS OWN and only when its read holds a trigger row. The
        source lists a release only ~2 weeks out, so a FAR week with no row is normal: it replaces nothing (its
        stored rows stay). NEXT week with no row is a failed read (review 2026-11-15: an HTTP-200 answer with an
        empty or renamed body used to delete every stored future US row)."""
        nonlocal n
        label = "fxempire united-states"
        weeks = []
        try:
            for w in (1, 2, 3):
                m = monday + timedelta(days=7 * w)
                ev = await asyncio.to_thread(io.fxempire, "united-states", m, m + timedelta(days=6))
                if raw_out is not None:
                    raw_out[("united-states", m)] = ev
                await asyncio.to_thread(io.pause, 1.5)
                weeks.append((m, [r for r in calendar_rows_from_fx(ev) if r["event_date"] >= m]))
        except CalendarRefused as e:
            errors[label] = f"REFUSED: {e}"[:160]
            raise
        except Exception as e:  # loud-ok: recorded per source; the run raises after its audit row when one failed
            logger.warning(f"cot: calendar source {label} failed: {type(e).__name__}: {e}")
            errors[label] = f"{type(e).__name__}: {e}"[:160]
            return
        if not weeks[0][1]:
            errors[label] = (f"no trigger event listed for next week ({weeks[0][0]}): taken as a failed read, "
                             "the stored rows are kept")
            return
        rows = [r for _m, got in weeks for r in got]
        placed = 0
        for m, got in weeks:
            if not got:
                continue
            s_ = m + timedelta(days=6)
            mine = [r for r in rows if m <= r["event_date"] <= s_]
            await io.replace_calendar(m - timedelta(days=1), mine, [US_SOURCE], s_)
            placed += len(mine)
        # a row whose session falls in a week that answered empty (or past the last week read): added, nothing deleted
        rest = [r for r in rows if not any(got and m <= r["event_date"] <= m + timedelta(days=6) for m, got in weeks)]
        if rest:
            await io.replace_calendar(today, rest, [US_SOURCE], today)
        n += placed + len(rest)

    def bank(country):
        def f():
            io.pause(1.5)
            ev = io.fxempire(country, monday, monday + timedelta(days=41))
            if raw_out is not None:
                raw_out[country] = ev
            return calendar_rows_from_fx(ev, country), True
        return f

    def earn():
        out, bad = [], []
        for tk in EARNINGS_TICKERS:
            try:
                out += calendar_rows_from_earnings(tk, [e["ts"] for e in io.earnings(tk)])
            except Exception as e:  # loud-ok: counted; every ticker failing raises just below
                bad.append(f"{tk}: {type(e).__name__}")
        if bad:
            errors["earnings (partial)"] = ", ".join(bad)[:160]
        if len(bad) == len(EARNINGS_TICKERS):
            raise CotError("no earnings dates for any ticker")
        return out, not bad

    if fx_ok:
        try:
            await take_us()
            for country in FX_CENTRAL_BANKS:
                await take(f"fxempire {country}", bank(country), f"fxempire.com economic calendar ({country})", today)
        except CalendarRefused:  # loud-ok: recorded in `errors` above (the run raises after its audit row); no further fxempire request this run
            logger.warning("cot: fxempire refused the calendar request; not retried")
    else:
        errors["fxempire"] = "skipped: refused earlier in this run"
    await take("usda wasde", lambda: (calendar_rows_from_wasde(io.wasde_dates()), True), WASDE_SOURCE, today)
    await take("yfinance earnings", earn, "yfinance earnings dates", today)
    await take("opec meetings", lambda: (calendar_rows_from_opec(), True), OPEC_SOURCE, today)
    if opec_table_age_days(today) > OPEC_STALE_DAYS:       # the CI date-test is not enough: it only runs on a commit
        errors["opec table"] = (f"newest announced meeting is {opec_table_age_days(today)} days old: "
                                "add the next date")
    await take("usda export sales", lambda: (calendar_rows_from_usda_exports(today, monday + timedelta(days=41)), True),
               USDA_EXPORTS_SOURCE, today)
    return {"rows": n, "errors": errors}


_READ_IT = object()


def no_price_data(markets, bars: dict[str, list[tuple]]) -> list[str]:
    """The markets (of `markets`) whose 3-month daily series was read, holds SOME bars, and is too short to EVER give
    a reading (1..MIN_BARS-1 sessions: a ticker the price source no longer serves, e.g. OJ=F answering with one bar).
    Such a market is named once in the weekly message and skipped daily without a page. An EMPTY answer is never
    excused — that is also how a rate-limited read looks, so it stays a no-bar and pages. Judged only when some
    series in the same read IS usable: when nothing is, the source is down and the run pages as before."""
    if not any(len(b) >= MIN_BARS for b in bars.values()):
        return []
    return sorted(m for m in set(markets) if 0 < len(bars.get(m) or []) < MIN_BARS)


async def ensure_week(io: Io, today: date, calendar_error=_READ_IT, fx_ok: bool = True) -> dict:
    """Fetch the CFTC report, and when it holds a week not yet messaged: compute, store, run the Friday check, send
    the ONE weekly message. Returns a summary; raises CotError when the data could not be fetched or the send failed.
    `calendar_error`: the outcome of THIS run's read of this week's calendar (None = read fine, a string = it failed);
    left out, the Friday check makes that read itself when it needs it (cot_weekly). `fx_ok=False`: FXEmpire refused
    a request earlier in this run (no further request is sent to it)."""
    cache = await io.load_nets()
    latest = await io.latest_week()
    have = max((d for rows in cache.values() for d in rows), default=None)
    full_from = today - timedelta(days=7 * HISTORY_WEEKS)
    since = full_from if have is None or min(min(r) for r in cache.values() if r) > full_from + timedelta(days=14) \
        else have - timedelta(days=28)
    fetched, source = await asyncio.to_thread(io.cftc, since, today)
    if not fetched:
        raise CotError(f"CFTC {source} returned no rows since {since}")
    await io.upsert_nets(fetched)
    for code, rd, c, l, s, _oi in fetched:
        cache.setdefault(code, {})[rd] = (c, l, s)
    report = max(d for rows in cache.values() for d in rows)
    res = {"report_date": report, "source": source, "fetched": len(fetched)}
    if latest and latest["report_date"] >= report and latest["message_sent_at"] is not None:
        return {**res, "status": "no new report"}

    cur_w = tuesday_of(report)
    weeks = [cur_w - timedelta(days=7 * i) for i in range(TRAIL_WEEKS + 1)][::-1]
    table = index_table(cache, weeks)
    rows = table[cur_w]
    if not rows:
        raise CotError(f"no market has an index for the {report} report (history too short?)")
    prev_w = next((w for w in reversed(weeks[:-1]) if table[w]), None)
    prev = table[prev_w] if prev_w else {}
    if latest is None and prev:
        # First run: the previous week is stored too, known from its scheduled Friday release, so the daily job has a
        # week it may use before this one becomes usable.
        prd = next(iter(prev.values()))["report_date"]
        await io.store_week(prd, tuesday_of(prd) + timedelta(days=3), prev)
    age = (today - cur_w).days
    # known_from. Only the FIRST run may back-date (the report was public long before we existed). Later, a report
    # first seen today was not in hand before today's session, however old its date (a backlog release after a CFTC
    # outage): it is known from today, and so are the weeks between it and the last one stored.
    known_from = cur_w + timedelta(days=3) if latest is None and age > LATE_FIRST_SIGHT_DAYS else today
    if latest is not None:
        for w in weeks[:-1]:
            if table[w] and (wrd := next(iter(table[w].values()))["report_date"]) > latest["report_date"]:
                await io.store_week(wrd, today, table[w])
    await io.store_week(report, known_from, rows)
    # A message retried on a later day keeps its Friday rows under the day the week was FIRST held (one row per
    # market, updated), instead of leaving unsent rows behind under the earlier date.
    first_seen = latest["known_from"] if latest and latest["report_date"] == report else known_from
    missing = sorted(set(MARKETS) - set(rows))

    # ── Friday confirmation: a MAIN set up that was not main last week ──
    new_main = [m for m, r in rows.items() if r["setup"] and (prev.get(m) or {}).get("setup") != r["setup"]]
    friday, errors = [], {}
    bars: dict[str, list[tuple]] = {}
    backfill: Optional[dict] = None
    check_friday = age <= FRIDAY_CHECK_MAX_AGE_DAYS
    if new_main and check_friday:
        if calendar_error is _READ_IT:
            try:
                await refresh_this_week(io, today)
                calendar_error = None
            except Exception as e:  # loud-ok: named in the weekly message and the audit row; the stored rows still serve
                logger.warning(f"cot: the Friday check could not read this week's calendar: {type(e).__name__}: {e}")
                calendar_error = f"{type(e).__name__}: {e}"[:200]
                fx_ok = fx_ok and not isinstance(e, CalendarRefused)
        bars = await _bars_for(io, _with_peers(new_main), errors)
        start = cur_w + timedelta(days=1)
        cal = await io.calendar(start, today)
        # A new install: the table holds nothing before its first day, so the window's earlier news days (last week's,
        # on a report that lands on a Monday) are read from the sources. Whatever cannot be read is SAID in the message.
        first = await io.calendar_first_date()
        if first is None or first > start:
            past, failed = await read_past_calendar(io, start, today, fx_ok)
            have = {(r["event_date"], r["event_type"]) for r in cal}
            cal = cal + [r for r in past if (r["event_date"], r["event_type"]) not in have]
            backfill = {"from": start, "to": today, "stored_from": first, "rows": len(past), "failed": failed}
        days = sorted({b[0] for bs in bars.values() for b in bs if start <= b[0] <= today})
        z_by_day = {d: {m: f["z"] for m, bs in bars.items() if (f := features_at(bs, d))} for d in days}
        for m in sorted(new_main):
            if m not in bars:
                continue
            try:
                ev = {d: [r["event_type"] for r in rs] for d, rs in _events_by_day(cal, m).items()}
                hit = friday_confirmation(m, rows[m]["setup"], bars[m], report, today, ev, z_by_day)
            except Exception as e:  # loud-ok: counted in the audit row and named in the message
                errors[m] = f"{type(e).__name__}: {e}"[:160]
                continue
            if hit:
                friday.append(hit)
    entry_label = "Sunday open" if today.weekday() == 4 else "the next open"
    stored = []
    if friday:
        stored = await io.store_alerts([_alert_row(first_seen, a, "friday", "main", report, rows[a["market"]],
                                                   entry_label, a["failure_day"]) for a in friday])
    # Set-up markets whose price series can never be read (review 2026-11-15, OJ=F): one read of every set-up market
    # not read above; a failed read here is not "no price data" (the daily job pages a market it cannot read).
    setup_markets = sorted(m for m, r in rows.items() if r["setup"] or r["close_setup"])
    scan = await _bars_for(io, [m for m in setup_markets if m not in bars and m not in errors], {})
    dead = no_price_data(setup_markets, {**bars, **scan})
    notes = []
    if new_main and not check_friday:
        notes.append(f"This report is {age} days old, so the Friday confirmation check was not run.")
    if backfill and backfill["failed"]:
        notes.append(f"The Friday check could not read {', '.join(backfill['failed'])} for {backfill['from']:%m-%d} to "
                     f"{backfill['to']:%m-%d} (days before this calendar was first stored), so it may have missed a "
                     "news failure day.")
    if dead:
        notes.append("No usable price data for: " + ", ".join(name_of(m) for m in dead)
                     + " (the daily alerts skip them; the set up stays listed).")
    cal_err = calendar_error if isinstance(calendar_error, str) else None
    if new_main and check_friday and cal_err:
        notes.append("This week's calendar could not be read today, so the Friday check may have missed a news "
                     "failure day.")
    if errors:
        notes.append("Friday check could not read prices for: " + ", ".join(name_of(m) for m in sorted(errors)) + ".")
    if missing:
        notes.append("No index this week for: " + ", ".join(name_of(m) for m in missing) + ".")
    text = format_weekly_message(report, rows, prev, exit_signals(table, [w for w in weeks if table[w]]), friday,
                                 entry_label, notes)
    if not await _send(text):
        raise CotError(f"the weekly COT message for {report} was not delivered (it is retried on the next run)")
    await io.mark_week_sent(report)
    await io.mark_alerts_sent([r["id"] for r in stored])
    return {**res, "status": "sent", "setups": sum(1 for r in rows.values() if r["setup"]),
            "close": sum(1 for r in rows.values() if r["close_setup"]), "friday": len(friday),
            "errors": errors, "missing": missing, "calendar_error": cal_err, "no_price_data": dead,
            **({"calendar_backfill": backfill} if backfill else {})}


# ═══════════════════════════════════════════════════════════════════════════════════════════════
# The jobs
# ═══════════════════════════════════════════════════════════════════════════════════════════════
async def run_weekly(today: date, io: Optional[Io] = None, now_et: Optional[datetime] = None) -> dict:
    """cot_weekly. ONE audit row per run; a fetch / send failure raises AFTER it (audit_wrap pages)."""
    io = io or Io()
    try:
        res = await ensure_week(io, today)
    except Exception as e:
        await io.audit(EVT_WEEKLY, f"{today}: FAILED {type(e).__name__}: {e}", {"error": str(e)})
        raise
    if res.get("status") == "sent":
        # a new week was stored: rebuild the next days' news-watch rows on it (no calendar request; the stored figures
        # stay). Its own try: it can never change the message or the audit row's outcome.
        nw: dict = {"errors": {}}
        try:
            await _watch_upcoming(io, today, now_et or datetime.now(_ET), nw, None, False, {}, None)
        except Exception as e:  # loud-ok: recorded in the audit row below; never changes the weekly outcome
            logger.warning(f"cot: the news watch (weekly rebuild) failed: {type(e).__name__}: {e}")
            nw["errors"]["upcoming"] = f"{type(e).__name__}: {e}"[:160]
        if nw["errors"]:
            nw["error_count"] = len(nw["errors"])
        else:
            del nw["errors"]
        res["news_watch"] = nw
    await io.audit(EVT_WEEKLY, f"{today}: report {res['report_date']} - {res['status']}; "
                               f"set ups {res.get('setups', '-')}, close {res.get('close', '-')}, "
                               f"Friday alerts {res.get('friday', '-')}" + _watch_errors_text(res), res)
    return res


async def _daily_body(io: Io, today: date, res: dict, problems: list[str], held: bool,
                      now: Optional[datetime] = None) -> None:
    """Everything cot_daily does after its gates. Fills `res` and `problems`; run_daily writes the audit row."""
    # 1. the calendar. Every day: this week's US releases, read fresh (also the day's actual-vs-consensus numbers).
    #    Mondays, or when the weekly refresh is over a week old: everything beyond this week.
    now = now or datetime.now(_ET)
    week_events: Optional[list[dict]] = None
    fx_ok = True
    raw_out: dict = {}              # the raw FXEmpire rows refresh_calendar reads on a full refresh (the news watch keeps their forecasts)
    cache: dict = {}                # reads shared by the alert label and the news watch (minute bars, earnings rows)
    watch_ctx: Optional[dict] = None
    try:
        week_events = await refresh_this_week(io, today)
    except Exception as e:  # loud-ok: recorded in the audit row; the run raises after it (stored rows still serve today)
        fx_ok = not isinstance(e, CalendarRefused)
        res["calendar_today"] = {"error": f"{type(e).__name__}: {e}"[:200]}
        problems.append(f"this week's US calendar could not be read (news alerts may be blind): {type(e).__name__}: {e}")
    try:
        age = await io.calendar_age_days(today)
        if age is None or age >= 7 or today.weekday() == 0:
            res["calendar"] = await refresh_calendar(io, today, fx_ok, raw_out)
            hard = {k: v for k, v in res["calendar"]["errors"].items() if "partial" not in k and not v.startswith("skipped")}
            if hard:
                problems.append("calendar source failed (news alerts may be blind): " + "; ".join(sorted(hard)))
    except Exception as e:  # loud-ok: recorded in the audit row; the run raises after it
        res["calendar"] = {"error": f"{type(e).__name__}: {e}"[:200]}
        problems.append(f"calendar refresh failed (news alerts may be blind): {type(e).__name__}: {e}")

    # 2. a holiday-delayed CFTC release (Mon-Thu; Friday belongs to cot_weekly). AFTER the calendar read: its Friday
    #    check reads this week's events, and is told whether today's read failed.
    if today.weekday() < 4 and not held:
        try:
            refused = any(str(v).startswith("REFUSED") for v in ((res.get("calendar") or {}).get("errors") or {}).values())
            res["catch_up"] = await ensure_week(io, today, (res.get("calendar_today") or {}).get("error"),
                                                fx_ok and not refused)
        except Exception as e:  # loud-ok: recorded in the audit row; the run raises after it
            res["catch_up"] = {"status": "FAILED", "error": f"{type(e).__name__}: {e}"[:200]}
            problems.append(f"CFTC catch-up failed: {type(e).__name__}: {e}")

    # 3. stale COT data. Keyed on the NEWEST STORED report (not the week usable today: on the day a fresh report
    #    lands, the week known BEFORE today is still the old one). The CFTC API can keep answering 200 with old rows,
    #    so every run reads "no new report" and the alerts go dark with a normal-looking audit row. Paged on MONDAYS
    #    only while it lasts: report Tuesday + 18 days is a Saturday, so the first stale run is always a Monday.
    latest = await io.latest_week()
    newest = latest["report_date"] if latest else None
    res["newest_report"] = newest
    res["stale"] = newest is None or (today - newest).days > MAX_WEEK_AGE_DAYS
    if newest is None and today.weekday() == 4:
        pass        # nothing stored yet on a Friday: cot_weekly stores the first week at 17:40 (and pages if it cannot)
    elif newest is None:
        problems.append("no COT report is stored: the daily alerts cannot run")
    elif res["stale"] and today.weekday() == 0:
        problems.append(f"the newest COT report is {newest}, {(today - newest).days} days old: the daily alerts are "
                        "off until a newer report is stored (the CFTC source may be stuck)")

    # 4. the week known BEFORE today
    known = await io.known_week(today)
    if known is None or (today - known[0]).days > MAX_WEEK_AGE_DAYS:
        res["status"] = "no usable COT week" if known is None else f"COT week {known[0]} is too old to use"
        res["report_date"] = known[0] if known else None
    else:
        report, index_rows = known
        res["report_date"] = report
        setups = _setups_of(index_rows)
        res["set_up_markets"] = len(setups)
        errors: dict[str, str] = {}
        found: list[dict] = []
        feats: dict[str, dict] = {}
        bars: dict[str, list] = {}
        cal: list[dict] = []
        if setups:
            bars = await _bars_for(io, _with_peers(setups), errors)
            z = {m: f["z"] for m, bs in bars.items() if (f := features_at(bs, today))}
            cal = await io.calendar(today, today)
            no_bar, closes, suspect = [], {}, []
            # a set-up market the price source no longer serves (OJ=F: one bar): recorded, skipped, never paged; the
            # weekly message named it. An EMPTY answer is not this: it stays a no-bar below and pages.
            dead = no_price_data(setups, bars)
            res["no_price_data"] = dead
            for m, (direction, level) in sorted(setups.items()):
                if m in errors or m in dead:
                    continue
                try:
                    feat = features_at(bars.get(m, []), today)
                    if feat is None:
                        no_bar.append(m)
                        continue
                    # Yahoo's newest daily close is the last trade (restated later to a settlement-like value);
                    # tomorrow's prev_close against today's close measures that gap. Recorded, never used to decide.
                    closes[m] = {"close": feat["close"], "prev_close": feat["prev_close"], "z": feat["z"]}
                    feats[m] = feat
                    # A bar whose close or open is outside its own high-low is broken data. The research kept such
                    # rows, so it is still judged as it comes, but flagged: the printed stop may already be crossed.
                    _d, o, h, l, c = next(b for b in bars[m] if b[0] == today)
                    broken = not (l <= c <= h and l <= o <= h)
                    if broken:
                        suspect.append(m)
                    ev_rows = _events_by_day(cal, m).get(today, [])
                    hit = detect(m, direction, feat, [r["event_type"] for r in ev_rows], z)
                    if hit:
                        found.append({**hit, "level": level, "bar_suspect": broken, "event_rows": ev_rows, **{
                            k: index_rows[m][k] for k in ("comm", "lspec", "sspec")}})
                except Exception as e:  # loud-ok: counted in the audit row; an all-fail run raises after it
                    errors[m] = f"{type(e).__name__}: {e}"[:160]
            res["no_bar_today"] = no_bar
            res["errors"] = errors
            res["closes"] = closes
            if suspect:
                res["suspect_bars"] = suspect
            # a peer with no reading today drops out of the correlation median (as in the research): recorded only
            res["peers_unread"] = sorted(p for p in _with_peers(setups) - set(setups) if p not in z)
            # A weekday the stock market is shut: futures trade a short session or none, so a market with no bar is a
            # quiet no-bar (recorded above), not a gap. A failed READ is never excused by the calendar.
            if no_bar and io.is_stock_holiday(today):
                res["holiday"] = True
            unread = sorted(m for m in setups if m in errors or (m in no_bar and not res.get("holiday")))
            if unread and len(unread) == len(setups) - len(dead):
                problems.append(f"no set-up market could be read today (errors {len(errors)}, no bar {len(no_bar)})")
            elif unread:
                # the readable markets alert and send below; the gap pages after, because nothing re-reads it
                problems.append(f"{len(unread)} of {len(setups)} set-up markets could not be read today: "
                                + ", ".join(name_of(m) for m in unread) + " (no alert for them today)")
            await _label(io, today, [a for a in found if "news" in a["kinds"]], res, week_events, cache)
            rows = []
            for a in found:
                for kind in a["kinds"]:
                    rows.append(_alert_row(today, a, kind, a["level"], report, a, "today's close (or the next open)"))
            unsent = await io.store_alerts(rows)
            res["alerts"] = len(found)
            to_send = [a for a in found if any(u["market"] == a["market"] for u in unsent)]
            text = format_daily_message(today, report, to_send)
            if text:
                if await _send(text):
                    if not held:
                        await io.mark_alerts_sent([u["id"] for u in unsent])
                    res["sent"] = not held
                else:
                    problems.append("the daily COT alert message was not delivered")
        watch_ctx = {"setups": setups, "cal": cal, "feats": feats, "report": report, "bars": bars,
                     "alerted": {a["market"] for a in found if "news" in a["kinds"]}}
        res["status"] = "ok"
    # 5. the news watch: AFTER the alert path, outside the branch above (the rows for the days ahead need only the
    #    newest stored week, and are written also when no week is usable today)
    await _news_watch_daily(io, today, now, res, watch_ctx, week_events, fx_ok, held, cache, raw_out)


def bar_is_final(day: date, now_et: datetime) -> bool:
    """The day's futures bar is final after the 17:00 ET close (5 minutes of margin)."""
    return now_et >= datetime.combine(day, time(17, 5), _ET)


async def run_daily(today: date, io: Optional[Io] = None, now_et: Optional[datetime] = None) -> dict:
    """cot_daily. ONE audit row per run. One market's error never stops the rest; a run where ANY set-up market could
    not be read, whose calendar / CFTC catch-up failed, or whose COT data is stale, raises AFTER the audit row."""
    io = io or Io()
    now = now_et or datetime.now(_ET)
    res: dict = {"day": today, "alerts": 0, "sent": False}
    problems: list[str] = []

    if today.weekday() >= 5 or not bar_is_final(today, now):
        res["status"] = "skipped: weekend" if today.weekday() >= 5 else "skipped: the day's bar is not final yet"
        await io.audit(EVT_DAILY, f"{today}: {res['status']}", res)
        return res

    # A #672 recovery re-run of a missed day: its Telegrams are HELD at the httpx layer (the send still answers
    # "ok"), so it must neither run the weekly catch-up (that week's one message would be swallowed) nor mark an
    # alert as sent.
    held = recovery_pin() is not None
    res["held"] = held

    try:
        await _daily_body(io, today, res, problems, held, now)
    except Exception as e:
        # one audit row EVERY run, also when something outside the per-market guards broke (a database read, the
        # alert store); audit_wrap pages on the re-raise
        res["problems"] = problems
        await io.audit(EVT_DAILY, f"{today}: FAILED {type(e).__name__}: {e}", {**res, "error": str(e)})
        raise
    res["problems"] = problems
    await io.audit(EVT_DAILY, f"{today}: {res['status']}; week {res.get('report_date')}; set-up markets "
                              f"{res.get('set_up_markets', 0)}; alerts {res['alerts']}; sent {res['sent']}"
                              + (f"; PROBLEMS {len(problems)}" if problems else "") + _watch_errors_text(res),
                   {k: v for k, v in res.items()})
    if problems:
        raise CotError(f"{JOB_DAILY} {today}: " + " | ".join(problems))
    return res


async def _label(io: Io, today: date, alerts: list[dict], res: dict, week_events: Optional[list[dict]],
                 cache: Optional[dict] = None) -> None:
    """The two labels on a news alert. A label that cannot be read is 'unknown'; it never blocks the alert.
    `week_events`: this week's US calendar as read a moment ago (None = that read failed). `cache`: the run's shared reads
    (the news watch reuses the minute bars and earnings rows fetched here)."""
    if not alerts:
        return
    label_errors = {}
    surprises: dict[tuple, dict] = dict(surprises_from_fx(week_events or []))
    types = {r["event_type"] for a in alerts for r in a["event_rows"]}
    if week_events is None and any(t in _US_TYPES or t.startswith("EIA") for t in types):
        label_errors["consensus"] = "this week's US calendar was not read"
    for t in sorted(t for t in types if t.startswith("EARN_")):
        tk = t[5:]
        try:
            for e in await _cached(cache, ("earn", tk), io.earnings, tk):
                if e["surprise_pct"] is not None and session_date(e["ts"].astimezone(_ET), earnings=True) == today:
                    surprises[(today, t)] = {"z": e["surprise_pct"] / EARNINGS_RMS[tk],
                                             "text": f"{tk} EPS {e['reported']} vs {e['estimate']}"}
        except Exception as e:  # loud-ok: the label reads 'unknown' and the reason is in the audit row
            label_errors[t] = f"{type(e).__name__}: {e}"[:160]
    for a in alerts:
        m = a["market"]
        minutes: list[tuple] = []
        if m not in NO_MINUTE_BARS:
            try:
                minutes = await _cached(cache, ("min", m), io.minute_bars, ticker_of(m))
            except Exception as e:  # loud-ok: the label reads 'unknown' and the reason is in the audit row
                label_errors[f"minutes {m}"] = f"{type(e).__name__}: {e}"[:160]
        best, detail, texts = None, [], []
        for r in a["event_rows"]:
            fm = first_minute(minutes, r.get("release_et"), a["atr"], a["direction"])
            nc = news_class(r["event_type"], m, a["direction"], today, surprises)
            detail.append({"event": r["event_type"], "first_minute": fm, "class": nc["cls"], "z": nc["z"]})
            if nc["text"]:
                texts.append(f"{r['event_type'].replace('_', ' ')}: {nc['text']} -> {CLASS_WORDS[nc['cls']]}")
            if fm.get("status") == "ok" and (best is None or fm["move"] > best["move"]):
                best = fm
        a["first_minute"] = best or (detail[0]["first_minute"] if detail else {"status": "not read"})
        a["news_class"] = overall_class([d["class"] for d in detail])
        a["news_detail"] = detail
        a["news_text"] = texts
    if label_errors:
        res["label_errors"] = label_errors


# ═══════════════════════════════════════════════════════════════════════════════════════════════
# The news watch, I/O side. Runs AFTER the alert path, each part in its own try: a failure here is recorded in the audit
# row (res["news_watch"]) and can never change an alert, a message or the job's outcome.
# ═══════════════════════════════════════════════════════════════════════════════════════════════
async def _cached(cache: Optional[dict], key: tuple, fn, *args):
    """One read per (kind, key) per run, shared by the alert label and the watch. A failure is cached too (the same
    refused request is not sent twice) and re-raised to each caller."""
    if cache is not None and key in cache:
        if isinstance(cache[key], Exception):
            raise cache[key]
        return cache[key]
    try:
        v = await asyncio.to_thread(fn, *args)
    except Exception as e:  # loud-ok: cached and re-raised to the caller, which records it
        if cache is not None:
            cache[key] = e
        raise
    if cache is not None:
        cache[key] = v
    return v


def _setups_of(index_rows: dict[str, dict]) -> dict[str, tuple[str, str]]:
    """{market: (direction to fade into, 'main' | 'close')} for every set-up or near-set-up market of a stored week."""
    return {m: (r["setup"] or r["close_setup"], "main" if r["setup"] else "close")
            for m, r in index_rows.items() if (r["setup"] or r["close_setup"]) and m in MARKETS}


def _num_text(x) -> Optional[str]:
    return None if x is None else f"{x:g}"


async def _earnings_expectations(io: Io, cache: dict, types, day_of) -> tuple[dict, dict, dict]:
    """(expectations, surprises, errors) for the EARN_ types: the EPS estimate / reported figure and the surprise z, from
    the same yfinance rows the alert label reads. `day_of(type)` = the session day to match."""
    exp, surprises, errors = {}, {}, {}
    for t in sorted(t for t in types if t.startswith("EARN_")):
        tk, day = t[5:], day_of(t)
        try:
            entries = await _cached(cache, ("earn", tk), io.earnings, tk)
        except Exception as e:  # loud-ok: recorded; the card reads "no forecast listed yet" / unknown
            errors[t] = f"{type(e).__name__}: {e}"[:160]
            continue
        for e in entries:
            if session_date(e["ts"].astimezone(_ET), earnings=True) != day:
                continue
            exp[(day, t)] = {"EPS": {"forecast": _num_text(e["estimate"]), "previous": None, "actual": _num_text(e["reported"])}}
            if e["surprise_pct"] is not None:
                surprises[(day, t)] = {"z": e["surprise_pct"] / EARNINGS_RMS[tk],
                                       "text": f"{tk} EPS {e['reported']} vs {e['estimate']}"}
    return exp, surprises, errors


async def _watch_judge(io: Io, today: date, now: datetime, nw: dict, ctx: dict, week_events: Optional[list[dict]],
                       fx_ok: bool, cache: dict) -> bool:
    """Today's rows: every set-up / near-set-up market with an event today, alert or not, judged on the same bar,
    surprises and first minute the alert uses. Returns whether FXEmpire may still be asked (False after a refusal)."""
    setups, cal, feats = ctx["setups"], ctx["cal"], ctx["feats"]
    evs = {m: r for m in sorted(setups) if (r := _events_by_day(cal, m).get(today, []))}
    rows: list[dict] = []
    if evs:
        old = {(r["event_type"], r["market"]): r for r in await io.watch_rows(today, today)}
        surprises = dict(surprises_from_fx(week_events or []))
        exp = expectations_from_fx(week_events or [])
        types = {r["event_type"] for v in evs.values() for r in v}
        for country, names in FX_COUNTRY_EVENTS.items():           # a non-US event today: that page, for its actual
            if fx_ok and types & (set(names.values()) - NO_FORECAST_TYPES):
                try:
                    exp.update(expectations_from_fx(await asyncio.to_thread(
                        io.fxempire, country, today - timedelta(days=1), today), country))
                except Exception as e:  # loud-ok: recorded; the card keeps the forecast it holds
                    nw["errors"][f"fxempire {country}"] = f"{type(e).__name__}: {e}"[:160]
                    fx_ok = fx_ok and not isinstance(e, CalendarRefused)
        e_exp, e_sur, e_err = await _earnings_expectations(io, cache, types, lambda t: today)
        exp.update(e_exp)
        surprises.update(e_sur)
        nw["errors"].update(e_err)
        for m, ev_rows in evs.items():
            direction, level = setups[m]
            feat = feats.get(m)
            minutes: list[tuple] = []
            if feat is not None and m not in NO_MINUTE_BARS and any(r.get("release_et") for r in ev_rows):
                try:
                    minutes = await _cached(cache, ("min", m), io.minute_bars, ticker_of(m))
                except Exception as e:  # loud-ok: the first minute reads "no minute bars"; recorded
                    nw["errors"][f"minutes {m}"] = f"{type(e).__name__}: {e}"[:160]
            for r in ev_rows:
                et = r["event_type"]
                fm = first_minute(minutes, r.get("release_et"), feat["atr"], direction) if feat else {"status": "not read"}
                rows.append(judged_watch_row(
                    {"event_date": today, "event_type": et, "release_et": r.get("release_et")}, m, direction, level,
                    ctx["report"], old.get((et, m)), lookup_expectation(exp, today, et),
                    news_class(et, m, direction, today, surprises), fm, feat, m in ctx["alerted"], now))
    await io.replace_watch(today, today, rows)
    nw["judged"] = len(rows)
    nw["verdicts"] = {v: sum(1 for r in rows if r["verdict"] == v) for v in sorted({r["verdict"] for r in rows})}
    try:
        await _watch_rejudge_pending(io, today, now, ctx.get("bars") or {}, nw)
    except Exception as e:  # loud-ok: recorded; today's rows above are already written
        nw["errors"]["rejudge"] = f"{type(e).__name__}: {e}"[:160]
    return fx_ok


async def _watch_rejudge_pending(io: Io, today: date, now: datetime, bars: dict, nw: dict) -> None:
    """A row left 'pending' (no bar at the 17:15 run) is judged again by a later run, within the 7-day window the page
    shows, once a bar exists for its day. It keeps what it stored (actuals, first minute, the alert flag); only the
    close, the class (scored on the stored forecast) and the verdict are re-derived."""
    stale = [r for r in await io.watch_rows(today - timedelta(days=WATCH_DAYS), today - timedelta(days=1))
             if r.get("verdict") == "pending"]
    by_day: dict[date, list[dict]] = {}
    for r in stale:
        if (feat := features_at(bars.get(r["market"], []), r["event_date"])) is not None:
            by_day.setdefault(r["event_date"], []).append((r, feat))
    n = 0
    for day, items in sorted(by_day.items()):
        keep = {(r["event_type"], r["market"]): r for r in await io.watch_rows(day, day)}
        for r, feat in items:
            keep[(r["event_type"], r["market"])] = judged_watch_row(
                {"event_date": day, "event_type": r["event_type"], "release_et": r.get("release_et")}, r["market"],
                r["direction"], r["level"], r["report_date"], r, None,
                {"cls": r.get("news_class") or "UNKNOWN", "z": r.get("surprise_z")}, r.get("first_minute") or {"status": "not read"},
                feat, bool(r.get("alerted")), now)
            n += 1
        await io.replace_watch(day, day, list(keep.values()))
    if n:
        nw["rejudged"] = n


async def _watch_upcoming(io: Io, today: date, now: datetime, nw: dict, week_events: Optional[list[dict]],
                          may_read: bool, cache: dict, raw_out: Optional[dict]) -> None:
    """The next WATCH_DAYS days' rows for the newest stored COT week. `week_events` / `raw_out` = what this run already
    read (None = nothing read). `may_read`: one more request for NEXT week's US page is allowed (the daily job when
    FXEmpire has not refused; never the weekly job, which makes no calendar request and keeps the stored figures)."""
    known = await io.known_week(FAR)
    if known is None:
        return
    report, index_rows = known
    setups = _setups_of(index_rows)
    d0, d1 = today + timedelta(days=1), today + timedelta(days=WATCH_DAYS)
    exp = expectations_from_fx(week_events or [])
    for key, ev in (raw_out or {}).items():
        if isinstance(key, str):
            exp.update(expectations_from_fx(ev, key))
        else:
            exp.update(expectations_from_fx(ev))
    nm = today - timedelta(days=today.weekday()) + timedelta(days=7)
    if may_read and d1 >= nm and ("united-states", nm) not in (raw_out or {}):
        # next week's figures (a Friday card would otherwise hold Monday's); its calendar rows replace the stored ones only when
        # the answer holds a trigger row. An empty or failed read is recorded, never paged (Monday's full refresh pages).
        try:
            await asyncio.to_thread(io.pause, 1.5)
            ev = await asyncio.to_thread(io.fxempire, "united-states", nm, nm + timedelta(days=6))
            exp.update(expectations_from_fx(ev))
            rows = [r for r in calendar_rows_from_fx(ev) if nm <= r["event_date"] <= nm + timedelta(days=6)]
            if rows:
                await io.replace_calendar(nm - timedelta(days=1), rows, [US_SOURCE], nm + timedelta(days=6))
            else:
                nw["errors"]["next week"] = f"no trigger event listed for the week of {nm}: the stored rows are kept"
        except Exception as e:  # loud-ok: recorded in the audit row; the stored calendar and figures stay
            nw["errors"]["next week"] = f"{type(e).__name__}: {e}"[:160]
    cal = await io.calendar(d0, d1)
    old_rows = await io.watch_rows(d0, d1)
    old = {(r["event_type"], r["market"], r["event_date"]): r for r in old_rows}
    sibling = {(r["event_type"], r["event_date"]): r for r in old_rows if r["event_type"] != "EIA_PETRO"}
    e_exp, _sur, e_err = await _earnings_expectations(
        io, cache, {r["event_type"] for r in cal if any(m in setups for m in markets_for_event(r["event_type"]))},
        lambda t: next(r["event_date"] for r in cal if r["event_type"] == t))
    exp.update(e_exp)
    nw["errors"].update(e_err)
    rows = []
    for ev in cal:
        for m in markets_for_event(ev["event_type"]):
            if m not in setups:
                continue
            et, day = ev["event_type"], ev["event_date"]
            prior = old.get((et, m, day)) or sibling.get((et, day))      # a market new to the list copies a sibling's figures
            direction, level = setups[m]
            rows.append(upcoming_watch_row(ev, m, direction, level, report, prior, lookup_expectation(exp, day, et), now))
    await io.replace_watch(d0, d1, rows)
    nw["upcoming"] = len(rows)
    nw["with_forecast"] = sum(1 for r in rows if any(s.get("forecast") for s in r["series"]))


def _watch_errors_text(res: dict) -> str:
    """The audit summary line's news-watch part: a watch failure never pages, so the count must be visible on the line."""
    n = (res.get("news_watch") or {}).get("error_count")
    return f"; NEWS WATCH ERRORS {n}" if n else ""


async def _news_watch_daily(io: Io, today: date, now: datetime, res: dict, ctx: Optional[dict],
                            week_events: Optional[list[dict]], fx_ok: bool, held: bool, cache: dict,
                            raw_out: dict) -> None:
    nw = res["news_watch"] = {"errors": {}}
    if ctx is not None:
        try:
            fx_ok = await _watch_judge(io, today, now, nw, ctx, week_events, fx_ok, cache)
        except Exception as e:  # loud-ok: recorded in the audit row; never changes an alert or the job's outcome
            logger.warning(f"cot: the news watch (today's rows) failed: {type(e).__name__}: {e}")
            nw["errors"]["judge"] = f"{type(e).__name__}: {e}"[:160]
    if not held:                         # a #672 recovery re-run of a past day must not rewrite the days ahead
        try:
            await _watch_upcoming(io, today, now, nw, week_events, fx_ok, cache, raw_out)
        except Exception as e:  # loud-ok: recorded in the audit row; never changes an alert or the job's outcome
            logger.warning(f"cot: the news watch (upcoming rows) failed: {type(e).__name__}: {e}")
            nw["errors"]["upcoming"] = f"{type(e).__name__}: {e}"[:160]
    if nw["errors"]:
        nw["error_count"] = len(nw["errors"])
    else:
        del nw["errors"]
