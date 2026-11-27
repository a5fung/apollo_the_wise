"""COT family live alerts (2026-11-15): the index against known values, the set-up rule, no look-ahead, feed A on
synthetic bars, the Friday confirmation, the two labels, the forward calendar, the messages, the two jobs (silence,
isolation, all-fail, one message per week), registration and the DDL. No network, no database.

The index fixtures are NUMBERS ONLY: CFTC public nets for four short-lookback markets and the index values our
research workspace holds for the same report (2026-11-03)."""
import asyncio
import re
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from agents.market_intelligence import cot_family as cf
from shared.dates import _ET

REPO = Path(__file__).resolve().parents[1]

# (report date, Commercials net, large-speculator net, small-speculator net)
NETS = {
    "coffee": [("2026-09-01", -26295, 23979, 2316), ("2026-09-08", -19640, 18001, 1639), ("2026-09-15", -16878, 15470, 1408),
               ("2026-09-22", -11375, 10273, 1102), ("2026-09-29", -14532, 13492, 1040), ("2026-10-06", -17512, 16213, 1299),
               ("2026-10-13", -14252, 13536, 716), ("2026-10-20", -21763, 20132, 1631), ("2026-10-27", -17821, 16549, 1272),
               ("2026-11-03", -13915, 11956, 1959)],
    "wheat": [("2026-08-18", 16381, -18765, 2384), ("2026-08-25", 7475, -6779, -696), ("2026-09-01", -23736, 24703, -967),
              ("2026-09-08", -12548, 10470, 2078), ("2026-09-15", -4799, 1228, 3571), ("2026-09-22", 2978, -7360, 4382),
              ("2026-09-29", 13451, -16462, 3011), ("2026-10-06", 13670, -16048, 2378), ("2026-10-13", 14876, -17606, 2730),
              ("2026-10-20", 29782, -29270, -512), ("2026-10-27", 51028, -50762, -266), ("2026-11-03", 64325, -62538, -1787)],
    "lean_hogs": [("2026-07-28", 43112, -42430, -682), ("2026-08-04", 51254, -48897, -2357), ("2026-08-11", 56535, -55369, -1166),
                  ("2026-08-18", 63608, -62655, -953), ("2026-08-25", 64227, -65921, 1694), ("2026-09-01", 61557, -62771, 1214),
                  ("2026-09-08", 56605, -57989, 1384), ("2026-09-15", 67751, -69211, 1460), ("2026-09-22", 66744, -68295, 1551),
                  ("2026-09-29", 71972, -76231, 4259), ("2026-10-06", 73985, -76468, 2483), ("2026-10-13", 78874, -81787, 2913),
                  ("2026-10-20", 76013, -76730, 717), ("2026-10-27", 81275, -82361, 1086), ("2026-11-03", 80474, -81035, 561)],
    "gold": [("2026-05-12", -210258, 171622, 38636), ("2026-05-19", -191629, 159833, 31796), ("2026-05-26", -185766, 154260, 31506),
             ("2026-06-02", -206345, 176020, 30325), ("2026-06-09", -201036, 173837, 27199), ("2026-06-16", -207563, 180220, 27343),
             ("2026-06-23", -205404, 181339, 24065), ("2026-06-30", -221070, 194019, 27051), ("2026-07-07", -222282, 194246, 28036),
             ("2026-07-14", -214788, 186682, 28106), ("2026-07-21", -213199, 183910, 29289), ("2026-07-28", -212309, 182070, 30239),
             ("2026-08-04", -226491, 197634, 28857), ("2026-08-11", -252640, 217940, 34700), ("2026-08-18", -258418, 222189, 36229),
             ("2026-08-25", -279585, 243334, 36251), ("2026-09-01", -264718, 228124, 36594), ("2026-09-08", -270274, 231960, 38314),
             ("2026-09-15", -261721, 230338, 31383), ("2026-09-22", -262903, 225853, 37050), ("2026-09-29", -250967, 218632, 32335),
             ("2026-10-06", -244527, 210335, 34192), ("2026-10-13", -242531, 207879, 34652), ("2026-10-20", -235582, 199865, 35717),
             ("2026-10-27", -215624, 186451, 29173), ("2026-11-03", -204902, 179548, 25354)],
}
KNOWN = {"coffee": (76, 17, 100), "wheat": (100, 0, 0), "lean_hogs": (97, 4, 44), "gold": (80, 28, 9)}
REPORT = date(2026, 11, 3)


def _nets_by_code(markets=NETS):
    return {cf.MARKETS[m][1][0]: {date.fromisoformat(d): (c, l, s) for d, c, l, s in rows} for m, rows in markets.items()}


# ── the index ────────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("market", sorted(NETS))
def test_index_reproduces_the_known_values(market):
    _n, codes, look, _t, _s = cf.MARKETS[market]
    ser = cf.build_series(_nets_by_code(), codes)
    assert cf.index_at(ser, REPORT, look) == KNOWN[market]


def test_the_window_is_the_current_report_plus_L_back_and_no_wider():
    """L = 3: the report 3 weeks back is IN the window, the one 4 weeks back is not. The extremes sit on exactly those
    two weeks, so a window one week too wide or too narrow gives a different number."""
    d = [date(2026, 1, 6) + timedelta(days=7 * i) for i in range(6)]
    nets = [0, -1000, 0, 60, 100, 50]                    # d[1] is 4 back from d[5]; d[2] is 3 back
    ser = {x: (n, n, n, x) for x, n in zip(d, nets)}
    assert cf.index_at(ser, d[5], 3) == (50, 50, 50)     # window d[2..5]: min 0, max 100
    assert cf.index_at(ser, d[5], 4)[0] == 95            # one week wider takes in the -1000
    assert cf.index_at(ser, d[5], 2)[0] == 0             # one week narrower loses the 0: min 50 = the current
    # a missing week does not pull an older report in: the window is by calendar, not by row count
    gap = {k: v for k, v in ser.items() if k != d[3]}
    assert cf.index_at(gap, d[5], 3) == (50, 50, 50)


def test_round_half_up_and_a_flat_group():
    d = [date(2026, 1, 6) + timedelta(days=7 * i) for i in range(4)]
    ser = {d[0]: (0, 5, 0, d[0]), d[1]: (200, 5, 8, d[1]), d[2]: (100, 5, 8, d[2]), d[3]: (25, 5, 1, d[3])}
    # 25 of 200 = 12.5 -> 13 (half up; Python's round() would give 12); a flat group has no index; 1 of 8 = 12.5 -> 13
    assert cf.index_at(ser, d[3], 3) == (13, None, 13)
    assert cf._round_half_up(0.5) == 1 and cf._round_half_up(2.5) == 3 and cf._round_half_up(2.4999) == 2


def test_history_shorter_than_the_window_gives_no_index():
    ser = cf.build_series(_nets_by_code(), cf.MARKETS["gold"][1])
    assert cf.index_at(ser, REPORT, 24) == KNOWN["gold"]
    assert cf.index_at(ser, REPORT, 26) is None            # the data starts 25 reports back
    assert cf.index_at(ser, date(2026, 11, 10), 24) is None  # a week we do not hold


def test_a_holiday_report_dated_monday_counts_as_its_week():
    rows = {"X": {date(2026, 1, 5): (10, 0, 0), date(2026, 1, 13): (20, 0, 5), date(2026, 1, 20): (30, 5, 0)}}
    ser = cf.build_series(rows, ("X",))
    assert sorted(ser) == [date(2026, 1, 6), date(2026, 1, 13), date(2026, 1, 20)]
    assert ser[date(2026, 1, 6)][3] == date(2026, 1, 5)     # the true report date is kept


def test_a_replaced_contract_is_spliced_from_its_first_report():
    rows = {"OLD": {date(2026, 1, 6): (1, 1, 1), date(2026, 1, 13): (2, 2, 2), date(2026, 1, 20): (3, 3, 3)},
            "NEW": {date(2026, 1, 13): (20, 20, 20), date(2026, 1, 20): (30, 30, 30)}}
    ser = cf.build_series(rows, ("OLD", "NEW"))
    assert [ser[d][0] for d in sorted(ser)] == [1, 20, 30]


def test_market_table_is_whole():
    assert len(cf.MARKETS) == 40 and "oats" not in cf.MARKETS
    assert cf.MARKETS["russell"][1] == ("23977A", "239742") and cf.MARKETS["nasdaq"][1] == ("209742",)
    for m, peers in cf.PEERS.items():
        assert m in cf.MARKETS and all(p in cf.MARKETS for p, _ in peers)
    assert all(m in cf.MARKETS for ms in cf.EVENT_MARKETS.values() for m in ms)
    assert not ({"ISM_MFG", "ISM_SERV"} & set(cf.EVENT_MARKETS))   # never N1 triggers in the research (PCE: watched since 11-22)


# ── the set-up rule ──────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("market,ix,want", [
    ("gold", (5, 95, 95), ("short", None)),
    ("gold", (95, 5, 5), ("long", None)),
    ("gold", (5, 95, 94), (None, "short")),          # one speculator group short of 95 -> the close list
    ("gold", (6, 99, 99), (None, None)),             # close needs Commercials at max (<= 5), 11-16 rule
    ("gold", (5, 85, 20), (None, "short")),
    ("gold", (5, 84, 50), (None, None)),             # Large Specs not yet leaning the crowded way
    ("gold", (3, 100, 4), (None, None)),             # Small Specs at the OPPOSITE extreme (Yen 11-10): not a set up
    ("gold", (95, 15, 80), (None, "long")),
    ("gold", (95, 16, 50), (None, None)),
    ("gold", (94, 0, 0), (None, None)),              # Commercials below 95 (Euro 11-10): not close outside stock indices
    ("gold", (0, 100, 50), (None, "short")),         # Commercials at max, waiting on Small Specs (Swiss franc 11-10)
    ("natural_gas", (100, 0, 16), (None, "long")),   # his 11-16 Discord: "close set up"; the old rule missed it
    ("natural_gas", (100, 0, 81), (None, None)),
    ("gold", (95, None, 10), (None, None)),          # a missing group never makes a close set up
    ("nasdaq", (5, 10, 10), ("short", None)),        # stock indices: Commercials alone
    ("nasdaq", (95, 99, 99), ("long", None)),
    ("nasdaq", (6, 84, 76), (None, "short")),
    ("nasdaq", (50, 99, 99), (None, None)),
    ("nasdaq", (10, 50, 50), (None, "short")),       # stock indices keep the Commercials-only 6-10 / 90-94 close band
    ("nasdaq", (11, 50, 50), (None, None)),
    ("nasdaq", (90, None, None), (None, "long")),
    ("nasdaq", (89, 50, 50), (None, None)),
    ("gold", (3, None, 99), (None, None)),           # a group with no index cannot complete a set up
    ("gold", (None, 99, 99), (None, None)),
])
def test_classify(market, ix, want):
    assert cf.classify(market, *ix) == want


def test_exit_signals_left_and_neutral():
    w = [date(2026, 10, 6) + timedelta(days=7 * i) for i in range(4)]
    row = lambda c, l, s, setup=None, close=None: {"comm": c, "lspec": l, "sspec": s, "setup": setup, "close_setup": close}  # noqa: E731
    table = {
        w[0]: {"gold": row(3, 97, 96, "short"), "sugar": row(2, 99, 99, "short"), "sp500": row(4, 50, 50, "short")},
        w[1]: {"gold": row(3, 97, 96, "short"), "sugar": row(20, 80, 80), "sp500": row(30, 50, 50)},
        w[2]: {"gold": row(3, 97, 96, "short"), "sugar": row(30, 70, 70), "sp500": row(40, 99, 1)},
        w[3]: {"gold": row(8, 90, 90, None, "short"), "sugar": row(40, 60, 45), "sp500": row(55, 50, 50)},
    }
    got = {x["market"]: x for x in cf.exit_signals(table, w)}
    assert got["gold"]["left"] and not got["gold"]["neutral"] and got["gold"]["now"] == "close list"
    assert got["sugar"]["neutral"] and not got["sugar"]["left"] and got["sugar"]["direction"] == "short"   # small specs back under 50
    assert got["sp500"]["neutral"]            # a stock index goes neutral on Commercials alone (55), not on the 1 before
    # a market already neutral in an earlier week is not reported again
    table[w[2]]["sugar"] = row(30, 70, 49)
    assert "sugar" not in {x["market"] for x in cf.exit_signals(table, w)}


# ── synthetic bars ───────────────────────────────────────────────────────────────────────────

def weekdays_to(end: date, n: int) -> list[date]:
    out, d = [], end
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d)
        d -= timedelta(days=1)
    return out[::-1]


def bars_to(end: date, last_close: float, n: int = 30, base: float = 100.0, last=None) -> list[tuple]:
    """Flat history (every day high base+1, low base-1, close base -> a daily range of 2) and one final bar closing at
    `last_close`: its z is (last_close - base) / 2."""
    days = weekdays_to(end, n)
    out = [(d, base, base + 1, base - 1, base) for d in days[:-1]]
    out.append(last or (days[-1], base, max(base + 1, last_close), min(base - 1, last_close), last_close))
    return out


WED = date(2026, 11, 11)


def test_features_need_a_bar_dated_today_and_twenty_before():
    b = bars_to(WED, 99.0)
    f = cf.features_at(b, WED)
    assert f["atr"] == pytest.approx(2.0) and f["z"] == pytest.approx(-0.5) and f["prev_close"] == 100.0
    assert cf.features_at(b[:-1], WED) is None                       # yesterday's bar is never today's reading
    assert cf.features_at(bars_to(WED, 99.0, n=20), WED) is None     # 19 earlier sessions: no range


def test_n1_news_day_closing_against_the_crowd():
    feat = cf.features_at(bars_to(WED, 99.0), WED)
    a = cf.detect("gold", "short", feat, ["CPI"], {})
    assert a["kinds"] == ["news"] and a["stop"] == 101.0 and "above 101.00" in a["stop_rule"] and a["close"] == 99.0
    assert cf.detect("gold", "short", feat, [], {}) is None                                  # no event, no peers
    assert cf.detect("gold", "short", cf.features_at(bars_to(WED, 101.0), WED), ["CPI"], {}) is None   # closed WITH the crowd
    assert cf.detect("gold", "short", cf.features_at(bars_to(WED, 100.0), WED), ["CPI"], {}) is None   # unchanged
    up = cf.features_at(bars_to(WED, 101.0), WED)                                            # a LONG set up: failure = an UP close
    b = cf.detect("wheat", "long", up, ["WASDE"], {})
    assert b["kinds"] == ["news"] and b["stop"] == 99.0 and "below 99.00" in b["stop_rule"]
    assert cf.detect("wheat", "long", feat, ["WASDE"], {}) is None


def test_c1_peers_closed_the_crowds_way_by_half_a_range():
    feat = cf.features_at(bars_to(WED, 99.0), WED)
    z = {"silver": 0.6, "platinum": 0.5, "palladium": -2.0}
    a = cf.detect("gold", "short", feat, [], z)
    assert a["kinds"] == ["correlation"] and a["peer_z"] == pytest.approx(0.5)               # the MEDIAN, at the bar
    assert cf.detect("gold", "short", feat, [], {**z, "platinum": 0.49}) is None
    assert cf.detect("gold", "short", feat, ["CPI"], z)["kinds"] == ["news", "correlation"]
    # an inverse peer: the dollar index DOWN is the currencies' crowd-friendly way for a short euro set up
    assert cf.peer_reading("dollar_index", "short", {"euro": -1.0, "japanese_yen": -1.0}) == pytest.approx(1.0)
    # a long set up: peers DOWN is the crowd's way
    up = cf.features_at(bars_to(WED, 101.0), WED)
    assert cf.detect("gold", "long", up, [], {"silver": -0.7, "platinum": -0.6})["kinds"] == ["correlation"]


def test_friday_confirmation_takes_the_last_live_failure_from_wednesday_on():
    fri, report = date(2026, 11, 13), date(2026, 11, 10)
    days = weekdays_to(fri, 30)
    flat = lambda d: (d, 100.0, 101.0, 99.0, 100.0)  # noqa: E731
    bars = [flat(d) for d in days]
    put = lambda d, c: bars.__setitem__(days.index(d), (d, 100.0, max(101.0, c), min(99.0, c), c))  # noqa: E731
    cpi = {date(2026, 11, 10): ["CPI"], date(2026, 11, 11): ["CPI"], date(2026, 11, 12): ["CPI"]}
    # a failure on the report TUESDAY itself is outside the window (Wed .. release)
    put(date(2026, 11, 10), 99.0)
    assert cf.friday_confirmation("gold", "short", bars, report, fri, cpi, {}) is None
    # Wednesday failure, still live on Friday
    put(date(2026, 11, 11), 98.0)
    hit = cf.friday_confirmation("gold", "short", bars, report, fri, cpi, {})
    assert hit["failure_day"] == date(2026, 11, 11) and hit["stop"] == 101.0
    # ... but a later CLOSE through its stop kills it (dead on arrival = no alert)
    put(date(2026, 11, 13), 102.0)
    assert cf.friday_confirmation("gold", "short", bars, report, fri, cpi, {}) is None
    # a holiday-shifted release: the window runs through the release day
    put(date(2026, 11, 13), 100.0)
    mon = date(2026, 11, 16)
    bars.append((mon, 100.0, 101.0, 98.0, 98.5))
    hit = cf.friday_confirmation("gold", "short", bars, report, mon, {**cpi, mon: ["RETAIL"]}, {})
    assert hit["failure_day"] == mon


# ── labels ───────────────────────────────────────────────────────────────────────────────────

def _t(h, m, d=WED):
    return datetime(d.year, d.month, d.day, h, m, tzinfo=_ET)


def test_first_minute_uses_the_bar_that_starts_at_the_release_minute():
    rel = _t(8, 30)
    bars = [(_t(8, 28), 100.0), (_t(8, 29), 100.2), (_t(8, 30), 101.0), (_t(8, 31), 99.0)]
    fm = cf.first_minute(bars, rel, 2.0, "short")
    assert fm["status"] == "ok" and fm["move"] == pytest.approx(0.4) and fm["big"] is True    # 101.0 - 100.2, / 2
    assert cf.first_minute(bars, rel, 2.0, "long")["move"] == pytest.approx(-0.4)             # signed the crowd's way
    assert cf.first_minute(bars, rel, 4.0, "short")["big"] is False                           # 0.2 < 0.25
    assert cf.first_minute([(_t(8, 29), 100.0), (_t(8, 30), 100.5)], rel, 2.0, "short")["big"] is True   # exactly 0.25 counts
    assert cf.first_minute([b for b in bars if b[0] != rel], rel, 2.0, "short")["status"] == "no bar in the release minute"
    assert cf.first_minute([(_t(7, 50), 100.0), (_t(8, 30), 101.0)], rel, 2.0, "short")["status"].startswith("no bar just before")
    assert cf.first_minute([], rel, 2.0, "short")["status"] == "no minute bars"
    assert cf.first_minute(bars, None, 2.0, "short")["status"] == "no release time"


def _fx(name, actual, forecast, ts="2026-11-11T13:30:00.000Z"):
    return {"name": name, "actual": actual, "forecast": forecast, "date": ts}


def test_parse_number():
    assert cf.parse_number("114K") == 114000 and cf.parse_number("-1.6M") == -1.6e6 and cf.parse_number("0.2%") == 0.2
    assert cf.parse_number("18Bcf") == 18 and cf.parse_number("18B", mult=False) == 18
    assert cf.parse_number("") is None and cf.parse_number(None) is None and cf.parse_number("n/a") is None


def test_news_class_with_against_inline_unknown():
    hot = cf.surprises_from_fx([_fx("Inflation Rate MoM", "0.4%", "0.2%"), _fx("Core Inflation Rate MoM", "0.4%", "0.3%"),
                                _fx("Atlanta Fed GDPNow", "3%", "1%")])
    assert set(hot) == {(WED, "CPI")} and hot[(WED, "CPI")]["z"] == pytest.approx((2.0 + 0.1 / 0.0931891) / 2)
    # hot inflation is bearish for gold: with a crowd that is SHORT (a long set up), against one that is LONG
    assert cf.news_class("CPI", "gold", "long", WED, hot)["cls"] == "WITH"
    assert cf.news_class("CPI", "gold", "short", WED, hot)["cls"] == "AGAINST"
    assert cf.news_class("CPI", "dollar_index", "short", WED, hot)["cls"] == "WITH"        # bullish for the dollar
    assert cf.news_class("CPI", "platinum", "short", WED, hot)["cls"] == "AMBIG"
    assert cf.news_class("CPI", "corn", "short", WED, hot)["cls"] == "UNKNOWN"             # no mapping for the market
    flat = cf.surprises_from_fx([_fx("Inflation Rate MoM", "0.22%", "0.2%")])
    assert cf.news_class("CPI", "gold", "short", WED, flat)["cls"] == "INLINE"             # |z| 0.2 < 0.25
    nofc = cf.surprises_from_fx([_fx("Inflation Rate MoM", "0.4%", "")])
    assert cf.news_class("CPI", "gold", "short", WED, nofc)["cls"] == "UNKNOWN"            # no consensus
    assert cf.news_class("CPI", "gold", "short", WED, {})["cls"] == "UNKNOWN"
    assert cf.news_class("WASDE", "corn", "short", WED, hot)["cls"] == "UNKNOWN"
    # growth data: no clear read for stock indices; a build in crude stocks is bearish crude, read from the crude series
    jobs = cf.surprises_from_fx([_fx("Non Farm Payrolls", "250K", "150K")])
    assert cf.news_class("NFP", "sp500", "short", WED, jobs)["cls"] == "AMBIG"
    eia = cf.surprises_from_fx([_fx("EIA Crude Oil Stocks Change", "6M", "1M", "2026-11-12T15:30:00.000Z"),
                                _fx("EIA Gasoline Stocks Change", "-4M", "1M", "2026-11-12T15:30:00.000Z")])
    assert cf.news_class("EIA_PETRO", "crude_oil", "long", WED, eia)["cls"] == "WITH"      # a day apart is allowed for EIA
    assert cf.news_class("EIA_PETRO", "unleaded_gas", "long", WED, eia)["cls"] == "AGAINST"
    gas = cf.surprises_from_fx([_fx("EIA Natural Gas Stocks Change", "45Bcf", "20B")])
    assert gas[(WED, "EIA_NATGAS")]["z"] == pytest.approx(25 / 9.47194)                    # the unit letter is ignored
    fomc = cf.surprises_from_fx([_fx("Fed Interest Rate Decision", "4.5%", "4.5%")])
    assert cf.news_class("FOMC", "gold", "short", WED, fomc)["cls"] == "INLINE"
    assert cf.overall_class(["UNKNOWN", "AGAINST", "WITH"]) == "WITH" and cf.overall_class([]) == "UNKNOWN"


# ── the forward calendar ─────────────────────────────────────────────────────────────────────

def test_session_date():
    assert cf.session_date(_t(8, 30)) == WED
    assert cf.session_date(_t(22, 30)) == date(2026, 11, 12)                    # an evening release: the next session
    assert cf.session_date(_t(16, 0), earnings=True) == date(2026, 11, 12)      # earnings after the close
    assert cf.session_date(_t(16, 0)) == WED                                    # a 16:00 macro print is still today's bar
    assert cf.session_date(_t(22, 0, date(2026, 11, 13))) == date(2026, 11, 16)  # Friday evening -> Monday
    assert cf.session_date(_t(19, 0, date(2026, 11, 15))) == date(2026, 11, 16)  # Sunday evening -> Monday


def test_calendar_rows_take_exact_names_only():
    ev = [_fx("Inflation Rate MoM", None, "0.2%"), _fx("Atlanta Fed GDPNow", None, "3%"), _fx("Retail Sales YoY", None, "1%"),
          _fx("EIA Crude Oil Stocks Change", None, "", "2026-11-12T15:30:00.000Z"),
          _fx("PCE Prices QoQ Adv", None, "0.2%"), _fx("ISM Manufacturing PMI", None, "50")]
    rows = {(r["event_date"], r["event_type"]) for r in cf.calendar_rows_from_fx(ev)}
    assert rows == {(WED, "CPI"), (date(2026, 11, 12), "EIA_PETRO")}
    boj = [_fx("BoJ Interest Rate Decision", None, "", "2026-12-18T03:00:00.000Z"), _fx("Inflation Rate MoM", None, "")]
    got = cf.calendar_rows_from_fx(boj, "japan")
    assert [(r["event_date"], r["event_type"]) for r in got] == [(date(2026, 12, 18), "BOJ")]   # 22:00 ET the evening before
    assert cf.markets_for_event("EARN_NVDA") == ("nasdaq", "sp500", "dow") and cf.markets_for_event("BOJ") == ("japanese_yen",)
    assert "gold" in cf.markets_for_event("CPI") and "corn" not in cf.markets_for_event("CPI") and cf.markets_for_event("X") == ()


def test_wasde_dates_from_the_usda_sentence():
    page = ("<p>2026 WASDE Release Dates (12:00pm ET)</p><p>In 2026 the WASDE report will be released on Jan. 12, Feb. 10, "
            "Nov. 10, and Dec. 10.</p><h3>2027 WASDE Release Dates</h3><p>In 2027 the WASDE report will be released on "
            "Jan. 12, Mar.  10, Jul.  9, and Dec. 10.</p><p>November 2026 WASDE Report (Release time: 12:00 PM ET, November 10)</p>")
    assert cf.parse_wasde_dates(page) == [date(2026, 1, 12), date(2026, 2, 10), date(2026, 11, 10), date(2026, 12, 10),
                                          date(2027, 1, 12), date(2027, 3, 10), date(2027, 7, 9), date(2027, 12, 10)]
    rows = cf.calendar_rows_from_wasde([date(2026, 12, 10)])
    assert rows[0]["event_type"] == "WASDE" and rows[0]["release_et"] == _t(12, 0, date(2026, 12, 10))
    assert cf.parse_wasde_dates("<p>nothing here</p>") == []


def test_fxempire_refusal_stops_without_a_retry():
    calls = []

    class R:
        def __init__(self, code, body=None):
            self.status_code, self._b = code, body or {}

        def json(self):
            return self._b

    def get(url, params=None, timeout=0):
        calls.append(params["page"])
        return R(429)
    with pytest.raises(cf.CalendarRefused):
        cf.fetch_fxempire("united-states", WED, WED, get=get, sleep=lambda s: None)
    assert calls == ["1"]
    pages = iter([R(200, {"calendar": [{"events": [{"name": "a"}]}], "last": False}),
                  R(200, {"calendar": [{"events": [{"name": "b"}]}], "last": True})])
    got = cf.fetch_fxempire("united-states", WED, WED, get=lambda *a, **k: next(pages), sleep=lambda s: None)
    assert [e["name"] for e in got] == ["a", "b"]


# ── messages ─────────────────────────────────────────────────────────────────────────────────

def _alert(**kw):
    a = {"market": "gold", "direction": "short", "kinds": ["news", "correlation"], "events": ["CPI", "EARN_NVDA"], "level": "main",
         "comm": 3, "lspec": 97, "sspec": 96, "close": 2650.3, "stop": 2671.0, "stop_rule": "a close above 2,671.00 (the 11-11 high)",
         "peer_z": 0.8, "z": -0.6, "first_minute": {"status": "ok", "move": 0.31, "big": True}, "news_class": "WITH",
         "news_text": ["CPI: inflation hotter than forecast (Inflation Rate MoM 0.4% vs 0.2%) = bullish Gold"],
         "news_detail": [{"event": "CPI", "class": "WITH", "z": 1.2, "fact": "inflation hotter than forecast", "read": "bullish"}]}
    a.update(kw)
    return a


def _no_pipe_table(text: str):
    assert not re.search(r"^\s*\|", text, re.M) and "|--" not in text and " | " not in text
    assert text.count("```") % 2 == 0 and text.count("```") >= 2


def test_daily_message_is_paper_tagged_plain_and_silent_when_empty():
    from agents.market_intelligence import constants
    assert cf.format_daily_message(WED, REPORT, []) is None
    text = cf.format_daily_message(WED, REPORT, [_alert(), _alert(market="soybean_oil", kinds=["correlation"], events=[])])
    assert constants.is_paper_message(text) and "research alerts, no orders" in text.splitlines()[0]
    _no_pipe_table(text)
    assert "GOLD SHORT  news + correlation (CPI, earnings NVDA)" in text and "SOYBEAN OIL SHORT  correlation" in text
    assert "entry: today's close 2,650.30 (or the next open)" in text and "stop: a close above 2,671.00" in text
    # gold SHORT set up: the crowd is long, so a first minute stored +0.31 (the crowd's way) is the asset UP 0.31
    assert "first minute after the release: up 0.31 of a day's range (big; big starts at 0.25)" in text
    assert "first minute after the release: down 0.54 of a day's range (big; big starts at 0.25)" in cf.format_daily_message(
        WED, REPORT, [_alert(first_minute={"status": "ok", "move": -0.54, "big": False})])
    assert "Gold closed down 0.60 of a day's range (a day's range = its 20-day average)" in text
    assert "news vs consensus: bullish Gold" in text and "= bullish Gold" in text
    assert "a news failure: bullish news for Gold (US CPI inflation), yet Gold closed DOWN." in text
    assert "Crowded long: large specs 97 of 100, small specs 96 of 100, commercials 3 of 100. The set up is short (it fades the crowd)." in text
    assert "close-list set up" in cf.format_daily_message(WED, REPORT, [_alert(level="close")])
    # the crowd is named ONCE per alert, in the set-up line only: no other operator-facing line mentions it
    for line in text.splitlines():
        assert "crowd" not in line.lower() or line.strip().startswith(("main set up", "close-list set up"))
    assert "crowd's way" not in text and "AGAINST the crowd" not in text and "with the crowd" not in text
    outside = re.sub(r"```.*?```", "", text, flags=re.S)
    assert "_" not in outside                              # a bare underscore outside the block breaks Telegram Markdown
    unread = cf.format_daily_message(WED, REPORT, [_alert(first_minute={"status": "no minute bars"}, news_class="UNKNOWN", news_text=[])])
    assert "first minute: unknown (no minute bars)" in unread and "news vs consensus: no clear read" in unread


def test_weekly_message_lists_set_ups_exits_and_the_friday_alert():
    from agents.market_intelligence import constants
    row = lambda c, l, s, setup=None, close=None: {"comm": c, "lspec": l, "sspec": s, "setup": setup, "close_setup": close}  # noqa: E731
    rows = {"gold": row(3, 97, 96, "short"), "wheat": row(100, 0, 0, "long"), "nasdaq": row(6, 84, 76, None, "short"),
            "corn": row(50, 50, 50)}
    prev = {"gold": row(3, 97, 96, "short"), "wheat": row(80, 10, 10)}
    exits = [{"market": "crude_oil", "direction": "short", "left": True, "neutral": True, "now": "not set up", "comm": 52, "lspec": 47, "sspec": 60}]
    fri = [{"market": "wheat", "direction": "long", "kinds": ["news"], "events": ["WASDE"], "failure_day": WED,
            "stop_rule": "a close below 540.25 (the 11-11 low)"}]
    text = cf.format_weekly_message(date(2026, 11, 10), rows, prev, exits, fri, "Sunday open", ["note."])
    assert constants.is_paper_message(text) and "no orders" in text.splitlines()[0]
    _no_pipe_table(text)
    assert re.search(r"GOLD\s+short C  3 L 97 S 96\n", text)                # carried from last week: not 'new'
    assert re.search(r"WHEAT\s+long  C100 L  0 S  0  new", text)
    assert "CLOSE TO A SET UP (Commercials at max, speculators not there yet)" in text and re.search(r"NASDAQ\s+short C  6 L 84 S 76", text)
    assert "CORN" not in text
    assert re.search(r"CRUDE OIL\s+was short C 52 L 47 S 60  left \+ neutral ~50", text)
    assert "WHEAT LONG  failure day Wed 11-11: news (WASDE)" in text and "entry: Sunday open   stop: a close below 540.25" in text
    empty = cf.format_weekly_message(date(2026, 11, 10), {"corn": row(50, 50, 50)}, {}, [], [], "Sunday open", [])
    assert "SET UP: none this week" in empty and "Friday confirmation" not in empty


# ── the jobs, on a fake Io ───────────────────────────────────────────────────────────────────

class FakeIo(cf.Io):
    current = None                     # the fake the patched cf._send delivers to (the newest one built)

    def __init__(self):
        FakeIo.current = self
        self.nets, self.cftc_rows, self.cftc_exc = {}, [], None
        self.weeks = {}                # report_date -> {known_from, sent, rows}
        self.bars, self.bar_fail, self.minutes = {}, set(), {}
        self.cal, self.cal_age, self.fx, self.fx_exc = [], 1, [], None
        self.alerts, self.sent, self.audits, self.send_ok = {}, [], [], True
        self.bar_calls, self.fx_calls, self.holiday = [], [], False
        # fx_eia: every US week read also lists that week's Thursday EIA release, as every real week does (an answer
        # with no trigger row is a FAILED read). fx_weeks: {monday: events} overrides one week's answer whole.
        self.fx_eia, self.fx_weeks, self.fx_bank = True, {}, {}
        self.wasde, self.wasde_exc, self.earn = [date(2026, 12, 10)], None, {}
        self.cal_first = date(2020, 1, 1)      # the stored calendar reaches far back (a long-running install); None = read off self.cal
        self.watch = {}                        # (event_date, event_type, market) -> the stored news-watch row
        self.watch_fail = None                 # an exception the watch's database writes raise (isolation tests)

    def cftc(self, since, today):
        if self.cftc_exc:
            raise self.cftc_exc
        return list(self.cftc_rows), "api"

    def daily_bars(self, ticker):
        self.bar_calls.append(ticker)
        if ticker in self.bar_fail:
            raise RuntimeError("yahoo down")
        return self.bars.get(ticker, [])

    def minute_bars(self, ticker):
        return self.minutes.get(ticker, [])

    def fxempire(self, country, d0, d1):
        self.fx_calls.append((country, d0))
        if self.fx_exc:
            raise self.fx_exc
        if country != "united-states":
            return list(self.fx_bank.get(country, []))
        if d0 in self.fx_weeks:
            return list(self.fx_weeks[d0])
        thu = d0 - timedelta(days=d0.weekday()) + timedelta(days=3)
        return list(self.fx) + ([_fx("EIA Natural Gas Stocks Change", None, None, f"{thu.isoformat()}T15:30:00.000Z")]
                                if self.fx_eia else [])

    def wasde_dates(self):
        if self.wasde_exc:
            raise self.wasde_exc
        return list(self.wasde)

    def earnings(self, ticker):
        return list(self.earn.get(ticker, []))

    def pause(self, seconds):
        pass

    def is_stock_holiday(self, day):
        return self.holiday

    async def load_nets(self):
        return {c: dict(r) for c, r in self.nets.items()}

    async def upsert_nets(self, rows):
        for code, rd, c, l, s, _oi in rows:
            self.nets.setdefault(code, {})[rd] = (c, l, s)

    async def latest_week(self):
        if not self.weeks:
            return None
        rd = max(self.weeks)
        return {"report_date": rd, "known_from": self.weeks[rd]["known_from"], "message_sent_at": self.weeks[rd]["sent"]}

    async def store_week(self, report_date, known_from, rows):
        self.weeks.setdefault(report_date, {"known_from": known_from, "sent": None, "rows": None})["rows"] = dict(rows)

    async def mark_week_sent(self, report_date):
        self.weeks[report_date]["sent"] = "now"

    async def known_week(self, day):
        ok = [rd for rd, w in self.weeks.items() if w["known_from"] < day]      # the SQL: known_from < $1
        return (max(ok), self.weeks[max(ok)]["rows"]) if ok else None

    async def calendar_age_days(self, today):
        return self.cal_age

    async def replace_calendar(self, today, rows, sources, until):
        keys = {(r["event_date"], r["event_type"]) for r in rows}
        self.cal = [r for r in self.cal if not (today < r["event_date"] <= until and r.get("source") in sources)
                    and (r["event_date"], r["event_type"]) not in keys] + list(rows)

    async def calendar(self, d0, d1):
        return [r for r in self.cal if d0 <= r["event_date"] <= d1]

    async def calendar_first_date(self):
        return self.cal_first or min((r["event_date"] for r in self.cal), default=None)

    async def watch_rows(self, d0, d1):
        if self.watch_fail:
            raise self.watch_fail
        return [dict(r) for k, r in self.watch.items() if d0 <= k[0] <= d1]

    async def replace_watch(self, d0, d1, rows):
        if self.watch_fail:
            raise self.watch_fail
        self.watch = {k: r for k, r in self.watch.items() if not d0 <= k[0] <= d1}
        for r in rows:
            self.watch[(r["event_date"], r["event_type"], r["market"])] = dict(r)

    async def store_alerts(self, rows):
        out = []
        for r in rows:
            k = (r["alert_date"], r["market"], r["direction"], r["kind"])
            old = self.alerts.get(k)
            self.alerts[k] = {**r, "id": (old or {}).get("id", len(self.alerts) + 1), "sent": (old or {}).get("sent")}
            if not self.alerts[k]["sent"]:
                out.append(self.alerts[k])
        return out

    async def mark_alerts_sent(self, ids):
        for a in self.alerts.values():
            if a["id"] in ids:
                a["sent"] = True

    async def send(self, text):
        self.sent.append(text)
        return self.send_ok

    async def audit(self, event, summary, detail):
        self.audits.append((event, summary, detail))


@pytest.fixture(autouse=True)
def _no_real_send(monkeypatch):
    async def send(text):
        return await FakeIo.current.send(text)
    monkeypatch.setattr(cf, "_send", send)


def _ix(c, l, s, setup=None, close=None):
    return {"comm": c, "lspec": l, "sspec": s, "setup": setup, "close_setup": close}


AFTER_CLOSE = datetime(2026, 11, 11, 17, 15, tzinfo=_ET)
FRI_BEFORE = date(2026, 11, 6)


def _daily_io(gold_close=99.0, weeks=None):
    """Wednesday 11-11. The week known since Friday 11-06 has GOLD set up short; flat peers."""
    io = FakeIo()
    io.weeks[REPORT] = {"known_from": FRI_BEFORE, "sent": "x", "rows": {"gold": _ix(3, 97, 96, "short"), "corn": _ix(50, 50, 50)}}
    io.weeks.update(weeks or {})
    io.bars = {"GC=F": bars_to(WED, gold_close), "SI=F": bars_to(WED, 100.0), "PL=F": bars_to(WED, 100.0), "PA=F": bars_to(WED, 100.0)}
    io.cal = [{"event_date": WED, "event_type": "CPI", "release_et": _t(8, 30), "source": "s"}]
    io.fx = [_fx("Inflation Rate MoM", None, "0.2%")]    # today's fresh read: CPI at 08:30 ET, no actual posted
    io.cftc_rows = [("088691", REPORT, 1, 2, 3, 4)]      # the catch-up finds nothing newer than the stored week
    return io


def _run(coro):
    return asyncio.run(coro)


def test_daily_alert_end_to_end_with_both_labels():
    io = _daily_io()
    io.minutes["GC=F"] = [(_t(8, 29), 100.0), (_t(8, 30), 101.0)]
    io.fx = [_fx("Inflation Rate MoM", "0.4%", "0.2%")]
    res = _run(cf.run_daily(WED, io, AFTER_CLOSE))
    assert res["alerts"] == 1 and res["sent"] is True and res["report_date"] == REPORT and len(io.sent) == 1
    row = io.alerts[(WED, "gold", "short", "news")]
    assert row["entry_price"] == 99.0 and row["stop_price"] == 101.0 and row["level"] == "main" and row["events"] == "CPI"
    assert row["first_minute"] == pytest.approx(0.5) and row["first_minute_big"] is True
    assert row["news_class"] == "AGAINST"                      # hot inflation is bearish gold; the crowd is long
    assert (row["comm"], row["lspec"], row["sspec"]) == (3, 97, 96) and row["sent"] is True
    assert "GOLD SHORT  news (CPI)" in io.sent[0] and "news vs consensus: bearish Gold" in io.sent[0]
    assert [a[0] for a in io.audits] == ["cot_daily"] and "alerts 1" in io.audits[0][1]
    assert "DX-Y.NYB" not in io.bar_calls and set(io.bar_calls) == {"GC=F", "SI=F", "PL=F", "PA=F"}   # the market + its peers only


def test_a_wednesday_alert_uses_the_week_known_before_wednesday():
    """No look-ahead: a newer week first held TODAY (a holiday-delayed release caught up at 17:15) is not used for
    today's bar, even though it is the latest stored. Silver is set up only in the newer week."""
    newer = {date(2026, 11, 10): {"known_from": WED, "sent": "x", "rows": {"silver": _ix(2, 99, 99, "short")}}}
    io = _daily_io(weeks=newer)
    io.bars["SI=F"] = bars_to(WED, 99.0)                       # silver also closed down on the CPI day
    io.cftc_rows = [("088691", date(2026, 11, 10), 1, 2, 3, 4)]
    res = _run(cf.run_daily(WED, io, AFTER_CLOSE))
    assert res["report_date"] == REPORT and {k[1] for k in io.alerts} == {"gold"}
    thu = date(2026, 11, 12)
    io.bars = {t: b + [(thu, 100.0, 101.0, 98.0, 98.5 if t == "SI=F" else 100.0)] for t, b in io.bars.items()}
    io.cal.append({"event_date": thu, "event_type": "PPI", "release_et": _t(8, 30, thu), "source": "s"})
    res = _run(cf.run_daily(thu, io, AFTER_CLOSE + timedelta(days=1)))
    assert res["report_date"] == date(2026, 11, 10) and (thu, "silver", "short", "news") in io.alerts    # usable from Thursday
    assert "known_from < $1" in cf._COT_KNOWN_WEEK_SQL


def test_daily_is_silent_but_audited_when_nothing_failed():
    io = _daily_io(gold_close=101.0)                           # gold closed WITH the crowd
    res = _run(cf.run_daily(WED, io, AFTER_CLOSE))
    assert res["alerts"] == 0 and io.sent == [] and io.alerts == {} and len(io.audits) == 1 and res["status"] == "ok"


def test_daily_never_alerts_on_an_unfinished_or_stale_bar():
    io = _daily_io()
    early = _run(cf.run_daily(WED, io, datetime(2026, 11, 11, 16, 59, tzinfo=_ET)))
    assert early["status"].startswith("skipped") and io.sent == [] and io.bar_calls == [] and len(io.audits) == 1
    io = _daily_io()
    io.bars = {t: b[:-1] for t, b in io.bars.items()}          # Yahoo has not posted today's bar: yesterday's is the last
    with pytest.raises(cf.CotError, match="no set-up market could be read"):
        _run(cf.run_daily(WED, io, AFTER_CLOSE))
    assert io.sent == [] and io.alerts == {} and io.audits[0][2]["no_bar_today"] == ["gold"]
    assert cf.bar_is_final(WED, datetime(2026, 11, 12, 6, 0, tzinfo=_ET))        # a next-morning recovery re-run may read it
    io = _daily_io()
    io.bars = {t: b[:-1] for t, b in io.bars.items()}
    io.holiday = True                                           # ... unless the market was shut: a quiet day, no page
    res = _run(cf.run_daily(WED, io, AFTER_CLOSE))
    assert res["holiday"] is True and res["alerts"] == 0 and io.sent == [] and len(io.audits) == 1
    io = _daily_io()
    io.bar_fail, io.holiday = {"GC=F"}, True                    # a fetch ERROR is never excused by the calendar
    with pytest.raises(cf.CotError):
        _run(cf.run_daily(WED, io, AFTER_CLOSE))


def test_one_markets_error_never_stops_the_rest():
    io = _daily_io()
    io.weeks[REPORT]["rows"]["crude_oil"] = _ix(2, 99, 99, "short")
    io.bars.update({"CL=F": bars_to(WED, 99.0), "HO=F": bars_to(WED, 100.0), "RB=F": bars_to(WED, 100.0)})
    io.cal.append({"event_date": WED, "event_type": "EIA_PETRO", "release_et": _t(10, 30), "source": "s"})
    io.bar_fail = {"GC=F"}
    with pytest.raises(cf.CotError, match="1 of 2 set-up markets could not be read today: GOLD"):
        _run(cf.run_daily(WED, io, AFTER_CLOSE))               # crude was read and alerted FIRST; gold's gap then pages
    assert set(io.audits[0][2]["errors"]) == {"gold"} and {k[1] for k in io.alerts} == {"crude_oil"} and len(io.sent) == 1
    assert io.alerts[(WED, "crude_oil", "short", "news")]["sent"] is True and len(io.audits) == 1


def test_a_set_up_market_with_no_bar_today_pages_after_the_others_alert():
    """Yahoo has not posted today's bar for ONE of two set-up markets: the other still alerts, and the gap pages
    (nothing re-reads it later). A missing PEER is recorded, not paged (the research drops it from the median too)."""
    io = _daily_io()
    io.weeks[REPORT]["rows"]["crude_oil"] = _ix(2, 99, 99, "short")
    io.bars.update({"CL=F": bars_to(WED, 99.0)[:-1], "HO=F": bars_to(WED, 100.0), "RB=F": bars_to(WED, 100.0)})
    io.bars["PA=F"] = io.bars["PA=F"][:-1]                     # a peer of gold without today's bar
    with pytest.raises(cf.CotError, match="1 of 2 set-up markets could not be read today: CRUDE OIL"):
        _run(cf.run_daily(WED, io, AFTER_CLOSE))
    d = io.audits[0][2]
    assert d["no_bar_today"] == ["crude_oil"] and d["peers_unread"] == ["palladium"] and len(io.audits) == 1
    assert {k[1] for k in io.alerts} == {"gold"} and len(io.sent) == 1
    io = _daily_io()
    io.bars["PA=F"] = io.bars["PA=F"][:-1]                     # only a peer missing: no page
    res = _run(cf.run_daily(WED, io, AFTER_CLOSE))
    assert res["peers_unread"] == ["palladium"] and res["alerts"] == 1


def test_a_stock_holiday_excuses_a_market_with_no_bar_but_never_a_failed_read():
    """A US holiday: some futures trade a short session, others (grains, softs) are shut. The shut ones are a quiet
    no-bar, recorded; the open one still alerts. A fetch ERROR on the same day still pages."""
    io = _daily_io()
    io.holiday = True
    io.weeks[REPORT]["rows"]["crude_oil"] = _ix(2, 99, 99, "short")
    io.bars.update({"CL=F": bars_to(WED, 99.0)[:-1], "HO=F": bars_to(WED, 100.0), "RB=F": bars_to(WED, 100.0)})
    res = _run(cf.run_daily(WED, io, AFTER_CLOSE))
    assert res["holiday"] is True and res["no_bar_today"] == ["crude_oil"] and res["problems"] == []
    assert {k[1] for k in io.alerts} == {"gold"} and len(io.sent) == 1
    io.bar_fail = {"GC=F"}
    with pytest.raises(cf.CotError, match="1 of 2 set-up markets could not be read today: GOLD"):
        _run(cf.run_daily(WED, io, AFTER_CLOSE))


def test_the_audit_row_carries_each_set_up_markets_close_and_previous_close():
    """Yahoo's newest daily close is the last trade and is restated later; tomorrow's `prev_close` against today's
    `close` is the measurement of that gap (finding: the research compared settlement with settlement)."""
    io = _daily_io()
    _run(cf.run_daily(WED, io, AFTER_CLOSE))
    assert io.audits[0][2]["closes"] == {"gold": {"close": 99.0, "prev_close": 100.0, "z": pytest.approx(-0.5)}}


def test_a_bar_whose_close_is_outside_its_own_range_is_flagged_not_dropped():
    io = _daily_io()
    io.bars["GC=F"] = bars_to(WED, 99.0, last=(WED, 100.0, 98.5, 98.0, 99.0))    # high 98.5 under the close 99.0
    res = _run(cf.run_daily(WED, io, AFTER_CLOSE))
    assert res["alerts"] == 1 and res["suspect_bars"] == ["gold"]               # still alerted: the research keeps such rows
    assert "price bar looks broken" in io.sent[0] and "check the stop on a chart" in io.sent[0]
    assert io.alerts[(WED, "gold", "short", "news")]["detail"]["bar_suspect"] is True
    io = _daily_io()
    _run(cf.run_daily(WED, io, AFTER_CLOSE))
    assert "suspect_bars" not in io.audits[0][2] and "price bar looks broken" not in io.sent[0]


def test_an_exception_outside_the_per_market_guards_still_leaves_one_audit_row():
    io = _daily_io()

    async def boom(day):
        raise RuntimeError("db down")
    io.known_week = boom
    with pytest.raises(RuntimeError, match="db down"):
        _run(cf.run_daily(WED, io, AFTER_CLOSE))
    assert len(io.audits) == 1 and "FAILED RuntimeError: db down" in io.audits[0][1]


def test_an_all_fail_run_raises_after_its_audit_row():
    io = _daily_io()
    io.bar_fail = {"GC=F"}
    with pytest.raises(cf.CotError):
        _run(cf.run_daily(WED, io, AFTER_CLOSE))
    assert len(io.audits) == 1 and "PROBLEMS 1" in io.audits[0][1] and io.sent == []


def test_a_rerun_does_not_send_the_same_alert_twice():
    io = _daily_io()
    _run(cf.run_daily(WED, io, AFTER_CLOSE))
    _run(cf.run_daily(WED, io, AFTER_CLOSE))
    assert len(io.sent) == 1 and len(io.audits) == 2
    io = _daily_io()
    io.send_ok = False                                          # an undelivered message is a failure, and is retried
    with pytest.raises(cf.CotError, match="not delivered"):
        _run(cf.run_daily(WED, io, AFTER_CLOSE))
    io.send_ok = True
    _run(cf.run_daily(WED, io, AFTER_CLOSE))
    assert len(io.sent) == 2 and io.alerts[(WED, "gold", "short", "news")]["sent"] is True


def test_a_week_older_than_the_research_carry_is_not_used():
    io = _daily_io()
    late = date(2026, 11, 23)                                   # 20 days after the 11-03 report
    io.bars = {t: bars_to(late, 99.0 if t == "GC=F" else 100.0) for t in io.bars}
    with pytest.raises(cf.CotError, match="newest COT report is 2026-11-03, 20 days old"):
        _run(cf.run_daily(late, io, datetime(2026, 11, 23, 17, 15, tzinfo=_ET)))
    assert "too old" in io.audits[0][2]["status"] and io.sent == [] and io.alerts == {} and len(io.audits) == 1
    # the page repeats on MONDAYS only (the first stale run is always a Monday: report Tuesday + 18 is a Saturday)
    io = _daily_io()
    tue = date(2026, 11, 24)
    io.bars = {t: bars_to(tue, 99.0 if t == "GC=F" else 100.0) for t in io.bars}
    res = _run(cf.run_daily(tue, io, datetime(2026, 11, 24, 17, 15, tzinfo=_ET)))
    assert "too old" in res["status"] and res["stale"] is True and io.sent == [] and io.alerts == {}


def test_stale_cot_data_pages_even_when_the_cftc_keeps_answering():
    """The CFTC API answers 200 with the same old rows for weeks: every status is a quiet 'no new report'. The page
    keys on the age of the NEWEST STORED report, so it must NOT fire on the day a fresh report arrived (that day the
    week known BEFORE today is still the old one)."""
    mon = date(2026, 11, 23)
    io = _daily_io()
    io.weeks.clear()                                             # nothing ever stored and the catch-up finds nothing usable
    io.cftc_exc = RuntimeError("cftc down")
    with pytest.raises(cf.CotError, match="no COT report is stored"):
        _run(cf.run_daily(mon, io, datetime(2026, 11, 23, 17, 15, tzinfo=_ET)))
    io = _daily_io(weeks={date(2026, 11, 17): {"known_from": mon, "sent": "x", "rows": {"gold": _ix(3, 97, 96, "short")}}})
    io.cftc_rows = [("088691", date(2026, 11, 17), 1, 2, 3, 4)]
    res = _run(cf.run_daily(mon, io, datetime(2026, 11, 23, 17, 15, tzinfo=_ET)))
    assert "COT week 2026-11-03 is too old" in res["status"] and res["stale"] is False and res["problems"] == []


def test_a_blind_calendar_pages_after_the_alerts():
    io = _daily_io()
    io.cal_age = 9
    io.fx_exc = cf.CalendarRefused("fxempire calendar refused the request (429)")
    with pytest.raises(cf.CotError, match="US calendar could not be read"):
        _run(cf.run_daily(WED, io, AFTER_CLOSE))
    assert len(io.sent) == 1 and len(io.audits) == 1            # the stored calendar still produced today's alert
    assert "news vs consensus: no clear read" in io.sent[0] and io.audits[0][2]["label_errors"]["consensus"]
    assert io.fx_calls == [("united-states", date(2026, 11, 9))]   # refused once: no second request this run
    assert any(r["event_type"] == "WASDE" for r in io.cal)      # the sources that answered were stored
    assert any(r["event_type"] == "CPI" and r["event_date"] == WED for r in io.cal)   # today's row was not wiped


def test_the_calendar_is_read_fresh_every_day_and_in_full_weekly():
    """Today's releases come from a read made today (the source lists a release late and can move one); everything
    further out is rebuilt on Mondays or when the weekly refresh is over a week old."""
    io = _daily_io()
    io.cal = [{"event_date": date(2026, 11, 13), "event_type": "PPI", "release_et": None, "source": cf.US_SOURCE},
              {"event_date": date(2026, 11, 10), "event_type": "WASDE", "release_et": None, "source": "usda.gov WASDE release dates"}]
    io.fx = [_fx("Inflation Rate MoM", "0.4%", "0.2%")]         # CPI is today; the PPI the source no longer lists is gone
    res = _run(cf.run_daily(WED, io, AFTER_CLOSE))
    # this week's read, then the news watch's one extra read of NEXT week (its figures; a trigger row replaces that week's rows)
    assert res["alerts"] == 1 and "calendar" not in res and io.fx_calls == [("united-states", date(2026, 11, 9)),
                                                                           ("united-states", date(2026, 11, 16))]
    assert {(r["event_date"], r["event_type"]) for r in io.cal} == {
        (WED, "CPI"), (date(2026, 11, 12), "EIA_NATGAS"), (date(2026, 11, 10), "WASDE"), (date(2026, 11, 19), "EIA_NATGAS")}
    io = _daily_io()
    io.cal_age = 8
    res = _run(cf.run_daily(WED, io, AFTER_CLOSE))
    assert res["calendar"]["errors"] == {} and len(io.fx_calls) == 1 + 3 + 6      # this week, 3 more, 6 central banks (the news watch reuses next week's rows: no 11th request)
    assert (date(2026, 12, 10), "WASDE") in {(r["event_date"], r["event_type"]) for r in io.cal}


def _weekly_io():
    io = FakeIo()
    io.cftc_rows = [(cf.MARKETS[m][1][0], date.fromisoformat(d), c, l, s, 0) for m, rows in NETS.items() for d, c, l, s in rows]
    return io


FRI = date(2026, 11, 6)


def test_weekly_stores_the_index_and_sends_one_message_per_report():
    io = _weekly_io()
    days = weekdays_to(FRI, 30)
    wheat = [(d, 100.0, 101.0, 99.0, 100.0) for d in days]
    wheat[-2] = (days[-2], 100.0, 101.5, 99.0, 101.0)           # Thursday 11-05: an UP close in a market set up LONG
    io.bars = {"ZW=F": wheat, "ZS=F": bars_to(FRI, 100.0), "ZM=F": bars_to(FRI, 100.0), "ZC=F": bars_to(FRI, 100.0),
               "HE=F": bars_to(FRI, 100.0), "LE=F": bars_to(FRI, 100.0)}  # lean hogs (97/4/44) is a close set up since 11-16
    io.cal = [{"event_date": date(2026, 11, 5), "event_type": "WASDE", "release_et": None, "source": "s"}]
    res = _run(cf.run_weekly(FRI, io))
    assert res["status"] == "sent" and res["report_date"] == REPORT and res["setups"] == 1 and res["friday"] == 1
    w = io.weeks[REPORT]
    assert w["known_from"] == FRI and w["sent"] and set(w["rows"]) == set(NETS)
    assert (w["rows"]["wheat"]["comm"], w["rows"]["wheat"]["setup"]) == (100, "long")
    assert (w["rows"]["gold"]["comm"], w["rows"]["gold"]["lspec"], w["rows"]["gold"]["sspec"]) == KNOWN["gold"]
    # the first run also stores the week before, known from ITS scheduled Friday, so the daily job has a usable week
    assert io.weeks[date(2026, 10, 27)]["known_from"] == date(2026, 10, 30)
    assert len(io.sent) == 1 and re.search(r"WHEAT\s+long  C100 L  0 S  0  new", io.sent[0])
    assert "WHEAT LONG  failure day Thu 11-05: news (WASDE)" in io.sent[0] and "entry: Sunday open" in io.sent[0]
    fa = io.alerts[(FRI, "wheat", "long", "friday")]
    assert fa["failure_day"] == date(2026, 11, 5) and fa["stop_price"] == 99.0 and fa["entry_note"] == "Sunday open"
    assert fa["sent"] is True
    # the entry is the NEXT open, not known yet: no price is stored as the entry; the failure day's close is in detail
    assert fa["entry_price"] is None and fa["detail"]["failure_day_close"] == 101.0
    assert io.fx_calls == [("united-states", date(2026, 11, 2))]      # the Friday check read this week's calendar itself
    # the retry slot: nothing new, no second message, an audit row all the same
    res = _run(cf.run_weekly(FRI, io))
    assert res["status"] == "no new report" and len(io.sent) == 1 and [a[0] for a in io.audits] == ["cot_weekly"] * 2
    assert len(io.fx_calls) == 1                                      # ... and no calendar request


def _wheat_week_io(end):
    io = _weekly_io()
    days = weekdays_to(end, 30)
    wheat = [(d, 100.0, 101.0, 99.0, 100.0) for d in days]
    i = days.index(date(2026, 11, 5))
    wheat[i] = (days[i], 100.0, 101.5, 99.0, 101.0)             # Thursday 11-05: an UP close in a market set up LONG
    io.bars = {"ZW=F": wheat, "ZS=F": bars_to(end, 100.0), "ZM=F": bars_to(end, 100.0), "ZC=F": bars_to(end, 100.0),
               "HE=F": bars_to(end, 100.0), "LE=F": bars_to(end, 100.0)}  # lean hogs (97/4/44) is a close set up since 11-16
    io.cal = [{"event_date": date(2026, 11, 5), "event_type": "WASDE", "release_et": None, "source": "s"}]
    return io


def test_the_friday_check_says_so_when_it_could_not_read_the_calendar():
    """The Friday check reads mi_cot_calendar, which only the daily job filled. It now reads this week's calendar
    itself, and a failed read is named in the weekly message and the audit row (stored rows still serve)."""
    io = _wheat_week_io(FRI)
    io.fx_exc = RuntimeError("fxempire down")
    res = _run(cf.run_weekly(FRI, io))
    assert res["status"] == "sent" and res["friday"] == 1 and "fxempire down" in res["calendar_error"]
    assert "calendar could not be read today" in io.sent[0] and "may have missed a news failure day" in io.sent[0]
    assert len(io.fx_calls) == 1
    ok = _wheat_week_io(FRI)
    _run(cf.run_weekly(FRI, ok))
    assert "calendar could not be read" not in ok.sent[0]


def test_the_daily_catch_up_checks_friday_on_a_calendar_read_today():
    """Mon-Thu the delayed-release catch-up runs AFTER the day's calendar read (one request, shared), never before."""
    mon = date(2026, 11, 9)
    io = _wheat_week_io(mon)
    seen = []
    real = io.calendar

    async def calendar(d0, d1):
        seen.append(len(io.fx_calls))
        return await real(d0, d1)
    io.calendar = calendar
    res = _run(cf.run_daily(mon, io, datetime(2026, 11, 9, 17, 15, tzinfo=_ET)))
    assert res["catch_up"]["status"] == "sent" and res["catch_up"]["friday"] == 1
    assert seen and min(seen) >= 1 and io.fx_calls.count(("united-states", mon)) == 1


def test_a_weekly_message_retried_on_a_later_day_keeps_one_friday_row():
    """Friday's send failed twice; Monday's daily catch-up retries it. The Friday row is keyed on the day the week
    was FIRST held, so the retry updates that row instead of leaving an unsent one behind under Friday's date."""
    mon = date(2026, 11, 9)
    io = _wheat_week_io(mon)
    io.send_ok = False
    with pytest.raises(cf.CotError, match="not delivered"):
        _run(cf.ensure_week(io, FRI))
    assert [k for k in io.alerts if k[3] == "friday"] == [(FRI, "wheat", "long", "friday")]
    io.send_ok = True
    assert _run(cf.ensure_week(io, mon))["status"] == "sent"
    assert [k for k in io.alerts if k[3] == "friday"] == [(FRI, "wheat", "long", "friday")]
    assert io.alerts[(FRI, "wheat", "long", "friday")]["sent"] is True and "entry: the next open" in io.sent[-1]


def test_a_backlog_report_published_late_is_not_used_on_the_day_it_lands():
    """NOT the first run: a week is already stored, then the CFTC publishes a 13-day-old report on a Monday (as after
    a shutdown). It was not in hand before today's session, so it is known from TODAY; the weeks between are stored
    too. (The first run keeps the scheduled-Friday stamp: see the test above.)"""
    mon = date(2026, 11, 16)
    io = _weekly_io()
    io.weeks[date(2026, 10, 20)] = {"known_from": date(2026, 10, 23), "sent": "x", "rows": {"corn": _ix(50, 50, 50)}}
    res = _run(cf.run_daily(mon, io, datetime(2026, 11, 16, 17, 15, tzinfo=_ET)))
    assert io.weeks[REPORT]["known_from"] == mon and io.weeks[date(2026, 10, 27)]["known_from"] == mon
    assert io.weeks[date(2026, 10, 27)]["rows"] and res["report_date"] == date(2026, 10, 20) and io.alerts == {}
    assert "too old" in res["status"] and res["stale"] is False        # the fresh report arrived: no stale page


def test_weekly_retries_an_undelivered_message_and_pages_a_failed_fetch():
    io = _weekly_io()
    io.send_ok = False
    with pytest.raises(cf.CotError, match="not delivered"):
        _run(cf.run_weekly(FRI, io))
    assert io.weeks[REPORT]["sent"] is None and "FAILED" in io.audits[-1][1]
    io.send_ok = True
    assert _run(cf.run_weekly(FRI, io))["status"] == "sent" and io.weeks[REPORT]["known_from"] == FRI
    io = _weekly_io()
    io.cftc_exc = RuntimeError("cftc down")
    with pytest.raises(RuntimeError):
        _run(cf.run_weekly(FRI, io))
    assert len(io.audits) == 1 and io.sent == []


def test_a_report_first_seen_late_is_known_from_its_friday_and_gets_no_friday_alert():
    """First run on Mon 11-16 while the newest report is still 11-03 (13 days old): it was released on 11-06, not
    today, so Monday's bar may use it; and a 'set up just completed' alert ten days late would be wrong."""
    io = _weekly_io()
    mon = date(2026, 11, 16)
    wheat = bars_to(mon, 101.0)                                  # an UP close today in a market set up long, on a news day
    days = [b[0] for b in wheat]
    wheat[days.index(date(2026, 11, 10))] = (date(2026, 11, 10), 100.0, 101.5, 99.0, 101.0)
    wheat[-1] = (mon, 101.0, 103.0, 100.5, 102.5)
    io.bars = {"ZW=F": wheat, "ZS=F": bars_to(mon, 100.0), "ZM=F": bars_to(mon, 100.0), "ZC=F": bars_to(mon, 100.0),
               "HE=F": bars_to(mon, 100.0), "LE=F": bars_to(mon, 100.0)}  # lean hogs (97/4/44) is a close set up since 11-16
    io.cal = [{"event_date": date(2026, 11, 10), "event_type": "WASDE", "release_et": None, "source": "s"},
              {"event_date": mon, "event_type": "WASDE", "release_et": None, "source": "s"}]
    res = _run(cf.run_daily(mon, io, datetime(2026, 11, 16, 17, 15, tzinfo=_ET)))
    assert io.weeks[REPORT]["known_from"] == date(2026, 11, 6)
    assert res["catch_up"]["friday"] == 0 and not any(k[3] == "friday" for k in io.alerts)
    assert "13 days old, so the Friday confirmation check was not run" in io.sent[0]
    assert res["report_date"] == REPORT and (mon, "wheat", "long", "news") in io.alerts     # Monday IS judged on it
    assert len(io.sent) == 2


def test_a_recovery_rerun_neither_catches_up_the_week_nor_marks_a_held_alert_sent(monkeypatch):
    monkeypatch.setattr(cf, "recovery_pin", lambda: object())   # the #672 sweep is re-running this slot; sends are held
    io = _daily_io()
    io.cftc_exc = AssertionError("the weekly catch-up must not run inside a recovery re-run")
    res = _run(cf.run_daily(WED, io, AFTER_CLOSE))
    assert res["alerts"] == 1 and res["sent"] is False and res["held"] is True and "catch_up" not in res
    assert io.alerts[(WED, "gold", "short", "news")]["sent"] is None


def test_the_real_sender_puts_the_alert_in_the_paper_chat_with_its_block_intact(monkeypatch):
    """Every other test replaces cf._send. This one drives the REAL briefing.send_telegram_message (httpx recorded)."""
    from unittest.mock import AsyncMock
    from agents.market_intelligence import briefing
    from tests.test_699_paper_chat_routing import MAIN, PAPER, _Router
    monkeypatch.undo()                                           # drop the autouse fake: the real cf._send
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "tok")
    monkeypatch.setenv("TELEGRAM_ALLOWED_USER_IDS", str(MAIN))
    monkeypatch.setenv("TELEGRAM_PAPER_CHAT_ID", str(PAPER))
    r = _Router()
    monkeypatch.setattr(briefing.httpx, "AsyncClient", r)
    monkeypatch.setattr(briefing, "log_audit_event", AsyncMock())
    row = lambda c, l, s, setup=None, close=None: {"comm": c, "lspec": l, "sspec": s, "setup": setup, "close_setup": close}  # noqa: E731
    daily = cf.format_daily_message(WED, REPORT, [_alert()])
    weekly = cf.format_weekly_message(REPORT, {"sp500": row(3, 50, 50, "short")}, {}, [], [], "Sunday open", [])
    assert _run(cf._send(daily)) is True and _run(cf._send(weekly)) is True
    assert r.chats() == [PAPER, PAPER]
    for p in r.posts:
        assert p["parse_mode"] == "HTML" and "<pre>" in p["text"] and "```" not in p["text"]
    assert "GOLD SHORT  news + correlation (CPI, earnings NVDA)" in r.posts[0]["text"]
    assert "S&amp;P 500" in r.posts[1]["text"]                  # an ampersand in a market name is escaped, not dropped


def test_a_delayed_release_is_caught_up_by_the_daily_job_with_next_open():
    io = _weekly_io()
    mon = date(2026, 11, 9)
    io.bars = {"ZW=F": bars_to(mon, 100.0), "HE=F": bars_to(mon, 100.0), "LE=F": bars_to(mon, 100.0)}
    res = _run(cf.run_daily(mon, io, datetime(2026, 11, 9, 17, 15, tzinfo=_ET)))
    assert res["catch_up"]["status"] == "sent" and io.weeks[REPORT]["known_from"] == mon and len(io.sent) == 1
    assert res["report_date"] == date(2026, 10, 27)             # Monday's own bar is judged on the week known before Monday
    io2 = _weekly_io()
    _run(cf.run_daily(FRI, io2, datetime(2026, 11, 6, 17, 15, tzinfo=_ET)))
    assert io2.weeks == {}                                       # Friday's release belongs to cot_weekly, not the daily job


# ── fetch parsing, registration, DDL, isolation ──────────────────────────────────────────────

def test_cftc_api_rows_become_nets():
    class R:
        status_code = 200

        def json(self):
            return [{"report_date_as_yyyy_mm_dd": "2026-11-03T00:00:00.000", "cftc_contract_market_code": "088691",
                     "noncomm_positions_long_all": "220530", "noncomm_positions_short_all": "40982",
                     "comm_positions_long_all": "64326", "comm_positions_short_all": "269228",
                     "nonrept_positions_long_all": "46024", "nonrept_positions_short_all": "20670", "open_interest_all": "399169"}]
    seen = {}

    def get(url, params=None, timeout=0):
        seen.update(params)
        return R()
    assert cf.fetch_cftc_api(date(2021, 1, 1), get=get) == [("088691", REPORT, -204902, 179548, 25354, 399169)]
    assert seen["$limit"] == "50000" and "'088691'" in seen["$where"] and "2021-01-01" in seen["$where"]
    R.status_code = 503
    with pytest.raises(cf.CotError):
        cf.fetch_cftc_api(date(2021, 1, 1), get=get)


def test_both_jobs_are_registered_in_et_and_intelligence_owned():
    from scripts.check_job_date_sources import Module, registrations
    from agents.market_intelligence import scheduler as sched
    regs = {r["job_id"]: r["cron"] for r in registrations(Module(REPO / "agents" / "market_intelligence" / "scheduler.py"))
            if r["job_id"] in (cf.JOB_DAILY, cf.JOB_WEEKLY)}
    d, w = regs[cf.JOB_DAILY], regs[cf.JOB_WEEKLY]
    assert d["day_of_week"] == "mon-fri" and d["hour"] == 17 and d["minute"] == 15 and d["timezone"] == "America/New_York"
    assert w["day_of_week"] == "fri" and w["hour"] == "17-18" and w["minute"] == 40 and w["timezone"] == "America/New_York"
    for j in (cf.JOB_DAILY, cf.JOB_WEEKLY):
        assert j in sched.INTELLIGENCE_OWNED_JOB_IDS and j not in sched.EXECUTION_OWNED_JOB_IDS


def test_the_ddl_is_idempotent_writes_only_its_own_tables_and_runs_at_init():
    from agents.market_intelligence import db
    ddl = db._COT_FAMILY_DDL
    creates = re.findall(r"CREATE\s+TABLE\s+(IF NOT EXISTS)?\s*(\w+)", ddl)
    assert {c[1] for c in creates} == {"mi_cot_nets_weekly", "mi_cot_weeks", "mi_cot_index_weekly", "mi_cot_calendar", "mi_cot_alerts",
                                       "mi_cot_news_watch"}
    assert all(c[0] for c in creates) and not re.search(r"\bDROP\b|\bTRUNCATE\b|\bALTER\b", ddl)
    for col in ("report_date", "market", "comm", "lspec", "sspec", "setup", "close_setup"):
        assert re.search(rf"mi_cot_index_weekly \((?:.|\n)*?\b{col}\b", ddl)
    assert "UNIQUE (alert_date, market, direction, kind)" in ddl
    # source-pin-ok: that the schema init EXECUTES this DDL is decidable only from its source (the _BREAKOUT_V1_DDL precedent)
    assert "await conn.execute(_COT_FAMILY_DDL)" in (REPO / "agents" / "market_intelligence" / "db.py").read_text()
    for sql in (cf._COT_ALERT_UPSERT_SQL, cf._COT_INDEX_UPSERT_SQL, cf._COT_CALENDAR_UPSERT_SQL, cf._COT_NETS_UPSERT_SQL,
                cf._COT_WATCH_UPSERT_SQL):
        table = re.search(r"INSERT INTO (\w+)", sql).group(1)
        cols = [c.strip() for c in re.search(r"\(([^)]*)\)", sql).group(1).split(",")]
        body = re.search(rf"CREATE TABLE IF NOT EXISTS {table} \((.*?)\n    \);", ddl, re.S).group(1)
        assert all(re.search(rf"^\s+{c}\s", body, re.M) for c in cols), (table, cols)
    assert "$21::jsonb" in cf._COT_ALERT_UPSERT_SQL and "sent_at" not in cf._COT_ALERT_UPSERT_SQL.split("RETURNING")[0]


def test_the_module_has_no_broker_or_order_path():
    """Behaviour, not text: importing the module (and building both messages) loads no broker / strategy module and
    none of the heavy network libraries its fetchers import lazily."""
    import subprocess
    import sys
    code = ("import sys, datetime as d; from agents.market_intelligence import cot_family as c; "
            "c.format_daily_message(d.date(2026, 11, 11), d.date(2026, 11, 3), []); "
            "bad = sorted(m for m in sys.modules if 'broker' in m or 'alpaca' in m or 'entry_pipeline' in m "
            "or m.startswith('agents.market_intelligence.strategies') or m in ('pandas', 'yfinance', 'httpx')); "
            "print(bad); sys.exit(1 if bad else 0)")
    r = subprocess.run([sys.executable, "-c", code], cwd=REPO, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr


# ── review fixes 2026-11-15 ──────────────────────────────────────────────────────────────────

class _R:
    def __init__(self, code, body=None):
        self.status_code, self._b = code, body

    def json(self):
        if self._b is None:
            raise ValueError("no json")
        return self._b


@pytest.mark.parametrize("body", [{}, {"last": True}, {"calendar": []}, {"calendar": {"x": 1}, "last": True}, [], None])
def test_a_200_answer_with_a_reshaped_or_empty_body_is_a_failed_read(body):
    """fix 1: an HTTP 200 whose body lost 'calendar' / 'last' (or is not JSON) was read as 'no events'."""
    with pytest.raises(cf.CotError):
        cf.fetch_fxempire("united-states", WED, WED, get=lambda *a, **k: _R(200, body), sleep=lambda s: None)


def test_a_us_week_with_no_trigger_row_keeps_the_stored_rows_and_pages():
    """fix 1: the source answers 200 with no release at all for THIS week. Every real week lists the EIA releases, so
    it is a failed read: the stored future rows stay, the run pages through its problems path."""
    io = _daily_io()
    io.fx_eia, io.fx = False, []
    io.cal.append({"event_date": date(2026, 11, 13), "event_type": "PPI", "release_et": None, "source": cf.US_SOURCE})
    with pytest.raises(cf.CotError, match="this week's US calendar could not be read"):
        _run(cf.run_daily(WED, io, AFTER_CLOSE))
    assert (date(2026, 11, 13), "PPI") in {(r["event_date"], r["event_type"]) for r in io.cal}
    assert "no trigger" in io.audits[0][2]["calendar_today"]["error"] and len(io.sent) == 1    # today's alert still went


def test_an_empty_forward_week_never_deletes_stored_rows_and_an_empty_next_week_pages():
    """fix 1, the weekly forward read. The source lists a release only ~2 weeks out, so a FAR week with no row is
    normal and replaces nothing; NEXT week with no row is a failed read (rows kept, the run pages)."""
    def io_with(weeks):
        io = _daily_io()
        io.cal_age = 8
        io.cal += [{"event_date": date(2026, 11, 18), "event_type": "RETAIL", "release_et": None, "source": cf.US_SOURCE},
                   {"event_date": date(2026, 11, 25), "event_type": "GDP", "release_et": None, "source": cf.US_SOURCE}]
        io.fx_weeks = weeks
        return io
    have = lambda io: {(r["event_date"], r["event_type"]) for r in io.cal}  # noqa: E731
    # next week answers with its rows (the RETAIL date moved), the week after answers empty: its GDP row is kept
    io = io_with({date(2026, 11, 16): [_fx("Retail Sales MoM", None, "0.1%", "2026-11-17T13:30:00.000Z")],
                  date(2026, 11, 23): [], date(2026, 11, 30): []})
    res = _run(cf.run_daily(WED, io, AFTER_CLOSE))
    assert res["calendar"]["errors"] == {} and res["problems"] == []
    assert (date(2026, 11, 17), "RETAIL") in have(io) and (date(2026, 11, 18), "RETAIL") not in have(io)
    assert (date(2026, 11, 25), "GDP") in have(io)
    # every forward week answers empty: nothing is deleted, and the run pages
    io = io_with({date(2026, 11, 16): [], date(2026, 11, 23): [], date(2026, 11, 30): []})
    with pytest.raises(cf.CotError, match="calendar source failed"):
        _run(cf.run_daily(WED, io, AFTER_CLOSE))
    assert {(date(2026, 11, 18), "RETAIL"), (date(2026, 11, 25), "GDP")} <= have(io)
    assert "no trigger" in io.audits[0][2]["calendar"]["errors"]["fxempire united-states"]


def _first_run_io(mon):
    """A FIRST run on Monday 11-09: the 11-03 report (wheat newly set up long) lands today, and the calendar table
    holds nothing before today. Wheat's failure day (Thu 11-05, a WASDE day) is known only from the source."""
    io = _wheat_week_io(mon)
    io.cal, io.cal_first = [], None
    io.wasde = [date(2026, 11, 5), date(2026, 12, 10)]
    return io


def test_the_first_run_friday_check_reads_last_weeks_news_from_the_source():
    """fix 2: the Friday check's window (Wed 11-04 .. today) starts before the stored calendar's first date, so the
    news days in it are read from the sources (past FXEmpire weeks, WASDE, earnings dates)."""
    mon = date(2026, 11, 9)
    io = _first_run_io(mon)
    res = _run(cf.run_daily(mon, io, datetime(2026, 11, 9, 17, 15, tzinfo=_ET)))
    cu = res["catch_up"]
    assert cu["status"] == "sent" and cu["friday"] == 1 and cu["calendar_backfill"]["failed"] == []
    # Thursday 11-05 is also a weekly export sales day (2026-11-22): both events are named
    assert "WHEAT LONG  failure day Thu 11-05: news (WASDE, USDA EXPORTS)" in io.sent[0] and "could not read" not in io.sent[0]
    assert ("united-states", date(2026, 11, 2)) in io.fx_calls            # last week's US releases, from the source
    # a long-running install (the table reaches back past the window) makes no such request
    io = _wheat_week_io(mon)
    _run(cf.run_daily(mon, io, datetime(2026, 11, 9, 17, 15, tzinfo=_ET)))
    assert ("united-states", date(2026, 11, 2)) not in io.fx_calls


def test_the_first_run_friday_check_says_which_days_it_was_blind_for():
    """fix 2: a source that cannot be read back is named in the weekly message with the days; a refusal earlier in
    the run sends no further FXEmpire request."""
    mon = date(2026, 11, 9)
    io = _first_run_io(mon)
    io.wasde_exc = RuntimeError("usda down")
    with pytest.raises(cf.CotError, match="calendar source failed"):       # the forward WASDE refresh pages as before
        _run(cf.run_daily(mon, io, datetime(2026, 11, 9, 17, 15, tzinfo=_ET)))
    cu = io.audits[0][2]["catch_up"]
    # blind for WASDE, and said so; Thursday 11-05 is still known as a news day from the export sales rule
    # (2026-11-22: before it, this check found nothing — friday was 0)
    assert cu["status"] == "sent" and cu["friday"] == 1 and cu["calendar_backfill"]["failed"] == ["WASDE"]
    assert "WHEAT LONG  failure day Thu 11-05: news (USDA EXPORTS)" in io.sent[0]
    assert "could not read WASDE for 11-04 to 11-09" in io.sent[0] and "may have missed a news failure day" in io.sent[0]
    io = _first_run_io(mon)
    io.fx_exc = cf.CalendarRefused("refused (429)")
    with pytest.raises(cf.CotError):
        _run(cf.run_daily(mon, io, datetime(2026, 11, 9, 17, 15, tzinfo=_ET)))
    assert io.fx_calls == [("united-states", mon)]                         # refused once: nothing more was asked
    assert "could not read US releases, central-bank decisions for 11-04 to 11-09" in io.sent[0]
    assert "WHEAT LONG  failure day Thu 11-05: news (WASDE, USDA EXPORTS)" in io.sent[0]  # the sources that answered still served


def test_a_set_up_market_with_no_usable_price_series_is_skipped_without_a_page():
    """fix 3: OJ=F answers with one bar. Such a market can never be read, so it must not page every day: it is
    recorded and skipped; the other set-up markets alert as usual."""
    io = _daily_io()
    io.weeks[REPORT]["rows"]["orange_juice"] = _ix(2, 99, 99, "short")
    io.bars["OJ=F"] = bars_to(WED, 100.0)[-1:]
    res = _run(cf.run_daily(WED, io, AFTER_CLOSE))
    assert res["no_price_data"] == ["orange_juice"] and res["problems"] == [] and res["no_bar_today"] == []
    assert res["alerts"] == 1 and len(io.sent) == 1 and io.audits[0][2]["no_price_data"] == ["orange_juice"]
    # a USABLE series that only lacks today's bar still pages (it is a gap, not a dead ticker)
    io = _daily_io()
    io.weeks[REPORT]["rows"]["orange_juice"] = _ix(2, 99, 99, "short")
    io.bars["OJ=F"] = bars_to(WED, 100.0)[:-1]
    with pytest.raises(cf.CotError, match="1 of 2 set-up markets could not be read today: ORANGE JUICE"):
        _run(cf.run_daily(WED, io, AFTER_CLOSE))


def test_an_empty_price_answer_is_never_taken_for_a_dead_ticker():
    """fix 3 guard: an empty frame is also how a rate-limited read looks. Only a series that HOLDS bars and is too
    short is a dead ticker; an empty one stays a no-bar and pages, while the readable markets alert first."""
    io = _daily_io()
    io.weeks[REPORT]["rows"]["orange_juice"] = _ix(2, 99, 99, "short")
    io.bars["OJ=F"] = []
    with pytest.raises(cf.CotError, match="1 of 2 set-up markets could not be read today: ORANGE JUICE"):
        _run(cf.run_daily(WED, io, AFTER_CLOSE))
    d = io.audits[0][2]
    assert d["no_price_data"] == [] and d["no_bar_today"] == ["orange_juice"] and len(io.sent) == 1


def test_a_source_that_serves_no_usable_series_at_all_still_pages():
    """fix 3 guard: Yahoo answering short / empty for EVERYTHING is an outage, not a list of dead tickers."""
    io = _daily_io()
    io.bars = {t: b[-1:] for t, b in io.bars.items()}
    with pytest.raises(cf.CotError, match="no set-up market could be read today"):
        _run(cf.run_daily(WED, io, AFTER_CLOSE))
    assert io.audits[0][2]["no_price_data"] == []


def test_the_weekly_message_names_a_set_up_market_with_no_price_data_once():
    """fix 3: the weekly message and its audit row say it; the market stays in the index and the set-up list."""
    io = _wheat_week_io(FRI)
    io.bars["ZW=F"] = io.bars["ZW=F"][-1:]
    res = _run(cf.run_weekly(FRI, io))
    assert res["status"] == "sent" and res["no_price_data"] == ["wheat"] and io.audits[0][2]["no_price_data"] == ["wheat"]
    assert "No usable price data for: WHEAT" in io.sent[0] and re.search(r"WHEAT\s+long", io.sent[0])
    assert "wheat" in io.weeks[REPORT]["rows"]
    ok = _wheat_week_io(FRI)
    assert _run(cf.run_weekly(FRI, ok))["no_price_data"] == [] and "No usable price data" not in ok.sent[0]


# ── 2026-11-17: Fed minutes + Australian news (names read from the served answers, scripts/probes/_cot_events_1117) ──
_PROBE = Path(__file__).resolve().parent.parent / "scripts" / "probes" / "_cot_events_1117"


def _probe(country):
    import json
    return json.loads((_PROBE / f"{country}.json").read_text())


def test_new_event_types_map_to_the_right_markets():
    macro = cf.markets_for_event("CPI")
    assert cf.markets_for_event("FED_MINUTES") == macro and "gold" in macro
    for t in ("RBA_MINUTES", "AU_JOBS", "AU_WAGES"):
        assert cf.markets_for_event(t) == ("australian_dollar",)
        assert cf.RELEASE_CONVENTION[t] == (11, 30, "Australia/Sydney")
    assert cf.RELEASE_CONVENTION["FED_MINUTES"] == (14, 0, "America/New_York")


def test_fx_parser_emits_the_new_types_from_the_real_answers():
    au = {(r["event_date"], r["event_type"]) for r in cf.calendar_rows_from_fx(_probe("australia"), "australia")}
    types = {t for _d, t in au}
    assert {"RBA", "RBA_MINUTES", "AU_JOBS", "AU_WAGES"} <= types
    assert (date(2026, 11, 17), "RBA_MINUTES") in au and (date(2026, 11, 19), "AU_JOBS") in au
    assert (date(2026, 11, 18), "AU_WAGES") in au and (date(2026, 11, 3), "RBA") in au
    jobs = [d for d, t in au if t == "AU_JOBS"]
    assert len(jobs) == len(set(jobs)) == 5                   # one row per release: the other jobs series are not read
    us = {(r["event_date"], r["event_type"]) for r in cf.calendar_rows_from_fx(_probe("united-states"))}
    assert (date(2026, 11, 18), "FED_MINUTES") in us and (date(2026, 10, 7), "FED_MINUTES") in us
    assert not any(t in ("RBA_MINUTES", "AU_JOBS", "AU_WAGES") for _d, t in us)
    # a name is only read on its own country's page
    assert cf.calendar_rows_from_fx([_fx("RBA Meeting Minutes", None, "")], "united-states") == []
    assert cf.calendar_rows_from_fx([_fx("FOMC Minutes", None, "")], "australia") == []


def test_existing_types_unchanged_by_the_country_generalisation():
    assert cf.FX_COUNTRY_EVENTS["euro-area"] == {"ECB Interest Rate Decision": "ECB"}
    assert cf.FX_COUNTRY_EVENTS["switzerland"] == {"SNB Interest Rate Decision": "SNB"}
    assert set(cf.FX_CENTRAL_BANKS) == {"euro-area", "united-kingdom", "japan", "canada", "australia", "switzerland"}
    assert cf.FX_US_TRIGGERS["Fed Interest Rate Decision"] == "FOMC" and cf.FX_US_TRIGGERS["FOMC Minutes"] == "FED_MINUTES"


def test_a_type_without_surprise_components_gives_no_label_and_does_not_break():
    for t in ("FED_MINUTES", "RBA_MINUTES", "AU_JOBS", "AU_WAGES"):
        assert t not in cf.SURPRISE_COMPONENTS
    s = cf.surprises_from_fx([_fx("FOMC Minutes", None, ""), _fx("Employment Change", "76.3K", "15K")])
    assert s == {}
    assert cf.news_class("FED_MINUTES", "gold", "short", WED, s)["cls"] == "UNKNOWN"
    assert cf.news_class("AU_JOBS", "australian_dollar", "long", WED, s)["cls"] == "UNKNOWN"


def test_daily_alert_on_a_fed_minutes_day_sends_with_an_unknown_label():
    io = _daily_io()
    io.minutes["GC=F"] = [(_t(14, 0), 100.0), (_t(14, 1), 101.0)]
    io.cal = [{"event_date": WED, "event_type": "FED_MINUTES", "release_et": _t(14, 0), "source": "s"}]
    io.fx = [_fx("FOMC Minutes", None, "", "2026-11-11T19:00:00.000Z")]
    res = _run(cf.run_daily(WED, io, AFTER_CLOSE))
    assert res["alerts"] == 1 and res["sent"] is True
    row = io.alerts[(WED, "gold", "short", "news")]
    assert row["events"] == "FED_MINUTES" and row["news_class"] == "UNKNOWN"
    assert "FED MINUTES" in io.sent[0]


# ── 2026-11-22: PCE, Australian CPI, OPEC+ meetings, USDA weekly export sales (his issue of that date) ──
def test_the_1122_types_map_to_their_markets_and_release_times():
    assert cf.markets_for_event("PCE") == cf.markets_for_event("CPI")
    assert cf.markets_for_event("AU_CPI") == ("australian_dollar",)
    assert cf.markets_for_event("OPEC") == ("crude_oil", "heating_oil", "unleaded_gas") == cf.markets_for_event("EIA_PETRO")
    assert cf.markets_for_event("USDA_EXPORTS") == ("soybean_oil", "soybeans", "soybean_meal", "corn", "wheat")
    assert all(m in cf.MARKETS for t in ("PCE", "AU_CPI", "OPEC", "USDA_EXPORTS") for m in cf.markets_for_event(t))
    assert cf.RELEASE_CONVENTION["PCE"] == (8, 30, "America/New_York") == cf.RELEASE_CONVENTION["USDA_EXPORTS"]
    assert cf.RELEASE_CONVENTION["AU_CPI"] == (11, 30, "Australia/Sydney")
    assert "OPEC" not in cf.RELEASE_CONVENTION                 # a meeting has no standing release minute


def test_fx_parser_emits_pce_and_australian_cpi_from_the_real_answers():
    us = {(r["event_date"], r["event_type"]): r for r in cf.calendar_rows_from_fx(_probe("united-states"))}
    pce = sorted(d for d, t in us if t == "PCE")
    assert pce == [date(2026, 7, 30), date(2026, 8, 26), date(2026, 9, 30), date(2026, 10, 29)]   # one row per release
    assert all((us[(d, "PCE")]["release_et"].hour, us[(d, "PCE")]["release_et"].minute) == (8, 30) for d in pce)
    au = {(r["event_date"], r["event_type"]): r for r in cf.calendar_rows_from_fx(_probe("australia"), "australia")}
    cpi = sorted(d for d, t in au if t == "AU_CPI")
    assert cpi == [date(2026, 7, 29), date(2026, 8, 26), date(2026, 9, 30), date(2026, 10, 28)]   # monthly; the quarterly rides along
    syd = au[(date(2026, 10, 28), "AU_CPI")]["release_et"].astimezone(ZoneInfo("Australia/Sydney"))
    assert (syd.hour, syd.minute) == (11, 30)                  # 11:30 Sydney = the evening before in New York -> next session
    assert au[(date(2026, 10, 28), "AU_CPI")]["release_et"].date() == date(2026, 10, 27)
    # each name is read on its own country's page only: the US "Inflation Rate MoM" stays CPI, the Australian one AU_CPI
    assert not any(t == "AU_CPI" for _d, t in us) and not any(t in ("CPI", "PCE") for _d, t in au)
    assert [r["event_type"] for r in cf.calendar_rows_from_fx([_fx("Inflation Rate MoM", None, "")], "japan")] == []
    assert [r["event_type"] for r in cf.calendar_rows_from_fx([_fx("PCE Price Index MoM", None, "")], "australia")] == []
    assert [r["event_type"] for r in cf.calendar_rows_from_fx([_fx("Core PCE Price Index MoM", None, "")])] == []


def test_pce_is_signed_like_cpi_and_the_other_1122_types_read_unknown():
    assert cf.SURPRISE_COMPONENTS["PCE"] == [
        ("PCE Price Index MoM", 1, 0.0531085), ("Core PCE Price Index MoM", 1, 0.0599145),
        ("PCE Price Index YoY", 1, 0.0767948), ("Core PCE Price Index YoY", 1, 0.0800641)]
    for m in cf.MARKETS:
        assert cf.news_sign("PCE", m) == cf.news_sign("CPI", m)
    hot = cf.surprises_from_fx([_fx("PCE Price Index MoM", "0.4%", "0.2%"), _fx("Core PCE Price Index MoM", "0.3%", "0.2%")])
    assert hot[(WED, "PCE")]["z"] == pytest.approx((0.2 / 0.0531085 + 0.1 / 0.0599145) / 2)
    assert cf.news_class("PCE", "gold", "short", WED, hot)["cls"] == "AGAINST"      # hot inflation: gold down, the crowd is long
    assert cf.news_class("PCE", "gold", "long", WED, hot)["cls"] == "WITH"
    assert cf.news_class("PCE", "platinum", "long", WED, hot)["cls"] == "AMBIG"
    flat = cf.surprises_from_fx([_fx("PCE Price Index MoM", "0.2%", "0.2%")])
    assert cf.news_class("PCE", "gold", "short", WED, flat)["cls"] == "INLINE"
    assert cf.news_class("PCE", "gold", "short", WED, {})["cls"] == "UNKNOWN"
    assert (WED, "CPI") not in hot                               # a PCE print is never read as CPI
    for t, m in (("AU_CPI", "australian_dollar"), ("OPEC", "crude_oil"), ("USDA_EXPORTS", "soybean_oil")):
        assert t not in cf.SURPRISE_COMPONENTS and cf.news_sign(t, m) is None
        s = cf.surprises_from_fx([_fx("Inflation Rate MoM", "0.9%", "0.2%")])   # a number exists, yet no mapping reads it
        assert cf.news_class(t, m, "long", WED, s)["cls"] == "UNKNOWN"


def test_opec_meeting_rows_and_the_table_is_not_stale():
    assert cf.OPEC_SOURCE_URL.startswith("https://www.opec.org/") and date(2026, 11, 29) in cf.OPEC_MEETINGS
    rows = cf.calendar_rows_from_opec((date(2026, 11, 29), date(2026, 12, 5), date(2026, 12, 9)))
    assert [(r["event_date"], r["event_type"], r["release_et"]) for r in rows] == [
        (date(2026, 11, 30), "OPEC", None),                    # a Sunday meeting is Monday's session
        (date(2026, 12, 7), "OPEC", None),                     # so is a Saturday one
        (date(2026, 12, 9), "OPEC", None)]                     # a weekday meeting is that day's
    assert all(r["source"] == cf.OPEC_SOURCE for r in rows)
    assert cf.opec_table_age_days(date(2026, 11, 22)) == -7 and cf.opec_table_age_days(date(2026, 12, 21)) == 22
    # THE GUARD: the newest announced meeting may not lie more than OPEC_STALE_DAYS (21) days back (the meeting is monthly). When this fails, read the latest
    # opec.org press release ("The next meeting will be held on ...") and add the date to cf.OPEC_MEETINGS.
    age = cf.opec_table_age_days(datetime.now(_ET).date())
    assert age <= cf.OPEC_STALE_DAYS, (f"cot_family.OPEC_MEETINGS is stale: its newest meeting was {age} days ago. "
                                       f"Add the next announced date ({cf.OPEC_SOURCE_URL} names the source).")


def test_usda_export_sales_is_thursday_unless_a_federal_holiday_moves_it_to_friday():
    assert cf.usda_export_sales_dates(date(2026, 11, 1), date(2026, 12, 31)) == [
        date(2026, 11, 5), date(2026, 11, 13),                 # Veterans Day (Wed 11-11) -> Friday
        date(2026, 11, 19), date(2026, 11, 27),                # Thanksgiving (Thu 11-26) -> Friday: the date in his issue
        date(2026, 12, 3), date(2026, 12, 10), date(2026, 12, 17), date(2026, 12, 24)]
    assert cf.usda_export_sales_dates(date(2026, 11, 26), date(2026, 11, 26)) == []
    assert cf.usda_export_sales_dates(date(2026, 5, 25), date(2026, 5, 31)) == [date(2026, 5, 29)]   # Memorial Day Monday
    assert cf.usda_export_sales_dates(date(2026, 6, 22), date(2026, 6, 28)) == [date(2026, 6, 26)]   # Juneteenth on the Friday before
    assert cf.usda_export_sales_dates(date(2024, 6, 17), date(2024, 7, 7)) == [date(2024, 6, 21), date(2024, 6, 27), date(2024, 7, 5)]
    assert date(2026, 10, 12) in cf.us_federal_holidays(2026) and date(2026, 7, 3) in cf.us_federal_holidays(2026)
    assert len(cf.us_federal_holidays(2026)) == 11 and date(2027, 12, 31) in cf.us_federal_holidays(2027)
    rows = cf.calendar_rows_from_usda_exports(date(2026, 11, 23), date(2026, 11, 29))
    assert [(r["event_date"], r["event_type"], r["release_et"]) for r in rows] == [
        (date(2026, 11, 27), "USDA_EXPORTS", _t(8, 30, date(2026, 11, 27)))]
    # the calendar's age is read off the WASDE rows ('usda.gov%'): this source must never be taken for them
    assert rows[0]["source"] == cf.USDA_EXPORTS_SOURCE and not cf.USDA_EXPORTS_SOURCE.startswith("usda.gov")


def test_the_weekly_refresh_stores_the_opec_and_export_sales_rows():
    io = _daily_io()
    io.cal_age = 8
    io.cal = io.cal + [{"event_date": date(2026, 12, 1), "event_type": "OPEC", "release_et": None, "source": cf.OPEC_SOURCE}]
    io.fx_bank = {"australia": [_fx("Inflation Rate MoM", None, "0.3%", "2026-11-25T00:30:00.000Z")]}
    res = _run(cf.run_daily(WED, io, AFTER_CLOSE))
    assert res["calendar"]["errors"] == {} and len(io.fx_calls) == 1 + 3 + 6      # no extra request to anyone
    have = {(r["event_date"], r["event_type"]) for r in io.cal}
    assert (date(2026, 11, 30), "OPEC") in have and (date(2026, 12, 1), "OPEC") not in have   # a moved meeting leaves no old row
    assert {(date(2026, 11, 13), "USDA_EXPORTS"), (date(2026, 11, 19), "USDA_EXPORTS"), (date(2026, 11, 27), "USDA_EXPORTS"),
            (date(2026, 12, 17), "USDA_EXPORTS")} <= have
    assert (date(2026, 11, 25), "AU_CPI") in have              # Wed 11:30 Sydney = Tue evening ET -> Wednesday's session
    assert (WED, "CPI") in have                                # today's row was not touched


def test_daily_alerts_on_an_export_sales_day_and_an_opec_day_read_unknown():
    io = _daily_io()
    io.weeks[REPORT]["rows"] = {"soybean_oil": _ix(3, 97, 96, "short"), "crude_oil": _ix(3, 97, 96, "short")}
    io.bars = {"ZL=F": bars_to(WED, 99.0), "CL=F": bars_to(WED, 99.0), "ZS=F": bars_to(WED, 100.0),
               "HO=F": bars_to(WED, 100.0), "RB=F": bars_to(WED, 100.0)}
    io.cal = [{"event_date": WED, "event_type": "USDA_EXPORTS", "release_et": _t(8, 30), "source": cf.USDA_EXPORTS_SOURCE},
              {"event_date": WED, "event_type": "OPEC", "release_et": None, "source": cf.OPEC_SOURCE}]
    io.fx = []
    res = _run(cf.run_daily(WED, io, AFTER_CLOSE))
    assert res["alerts"] == 2 and res["sent"] is True
    soy, oil = io.alerts[(WED, "soybean_oil", "short", "news")], io.alerts[(WED, "crude_oil", "short", "news")]
    assert soy["events"] == "USDA_EXPORTS" and soy["news_class"] == "UNKNOWN"
    assert oil["events"] == "OPEC" and oil["news_class"] == "UNKNOWN"
    assert "USDA EXPORTS" in io.sent[0] and "OPEC" in io.sent[0]
    assert "consensus" not in res.get("label_errors", {})      # nothing was expected from the US calendar for these


def test_daily_alert_on_a_pce_day_carries_the_consensus_read():
    io = _daily_io()
    io.cal = [{"event_date": WED, "event_type": "PCE", "release_et": _t(8, 30), "source": cf.US_SOURCE}]
    io.fx = [_fx("PCE Price Index MoM", "0.0%", "0.2%"), _fx("Core PCE Price Index MoM", "0.1%", "0.2%")]
    res = _run(cf.run_daily(WED, io, AFTER_CLOSE))
    row = io.alerts[(WED, "gold", "short", "news")]
    assert res["alerts"] == 1 and row["events"] == "PCE" and row["news_class"] == "WITH"   # cool inflation: gold up, the crowd's way
    assert any(r["event_type"] == "PCE" and r["event_date"] == WED for r in io.cal)        # read fresh from the US page


def test_store_alerts_binds_detail_as_an_object_not_a_string():
    """The pool's jsonb codec encodes the bind; a pre-dumped string was stored double-encoded (11-17)."""
    import asyncio
    from datetime import date as _d
    from agents.market_intelligence import cot_family as cf

    seen = []

    class _Conn:
        async def fetchrow(self, sql, *args):
            seen.append(args)
            return {"id": 1, "sent_at": None}

    class _Acq:
        async def __aenter__(self):
            return _Conn()

        async def __aexit__(self, *a):
            return False

    class _Pool:
        def acquire(self):
            return _Acq()

    class _Io(cf.Io):
        async def _pool(self):
            return _Pool()

    row = {c: None for c in cf._COT_ALERT_COLS}
    row["detail"] = {"kinds": ["news"], "when": _d(2026, 11, 17)}
    asyncio.run(_Io().store_alerts([row]))
    detail = seen[0][cf._COT_ALERT_COLS.index("detail")]
    assert isinstance(detail, dict) and detail["when"] == "2026-11-17"


# ── 2026-11-22 cleanups: cached holidays, a bounded OPEC window, a runtime stale-table check, an exact WASDE match ──
def test_us_federal_holidays_is_cached_and_immutable():
    h = cf.us_federal_holidays(2026)
    assert isinstance(h, frozenset) and cf.us_federal_holidays(2026) is h


def test_opec_rows_in_a_past_window_exclude_a_future_meeting():
    meetings = (date(2026, 10, 4), date(2026, 11, 29))
    got = cf.calendar_rows_from_opec(meetings, date(2026, 9, 28), date(2026, 10, 9))
    assert [r["event_date"] for r in got] == [date(2026, 10, 5)]          # the Sunday meeting is Monday's session
    assert len(cf.calendar_rows_from_opec(meetings)) == 2                  # no window: unchanged


def test_the_weekly_refresh_flags_a_stale_opec_table_at_runtime():
    io = _daily_io()
    late = max(cf.OPEC_MEETINGS) + timedelta(days=cf.OPEC_STALE_DAYS + 1)
    res = _run(cf.refresh_calendar(io, late))
    assert "newest announced meeting is 22 days old: add the next date" == res["errors"]["opec table"]
    res = _run(cf.refresh_calendar(io, max(cf.OPEC_MEETINGS)))
    assert "opec table" not in res["errors"]


def test_calendar_age_matches_the_wasde_source_exactly():
    seen = []

    class Conn:
        async def fetchval(self, sql, *args):
            seen.append(args)
            return datetime(2026, 11, 20, 12, tzinfo=_ET)

    class Acq:
        async def __aenter__(self): return Conn()
        async def __aexit__(self, *a): return False

    class Pool:
        def acquire(self): return Acq()

    class PgIo(cf.Io):
        async def _pool(self): return Pool()

    assert _run(PgIo().calendar_age_days(date(2026, 11, 22))) == 2
    assert seen == [("usda.gov WASDE release dates",)]       # the exact string its rows carry (no prefix match)
    assert cf.calendar_rows_from_wasde([date(2026, 12, 10)])[0]["source"] == cf.WASDE_SOURCE


# ── news watch (2026-11-25): the news to watch for, then the verdict ─────────────────────────────

THU, FRI_NEXT = date(2026, 11, 12), date(2026, 11, 13)


@pytest.mark.parametrize("close_z,direction,cls,fm,want,strict", [
    # a short set up = the crowd is long: a close DOWN (z < 0) is against them
    (-0.5, "short", "WITH", {"status": "ok", "move": 0.31}, "failure_full", True),
    (-0.5, "short", "WITH", {"status": "ok", "move": 0.01}, "failure", False),        # flat first minute (the band edge is flat)
    (-0.5, "short", "WITH", {"status": "ok", "move": -0.2}, "failure", False),        # first minute against the crowd
    (-0.5, "short", "WITH", {"status": "no minute bars"}, "failure", False),          # first minute not read
    (-0.5, "short", "AGAINST", {"status": "ok", "move": -0.4}, "followed_news", False),
    (-0.5, "short", "INLINE", None, "against_unread", False),
    (-0.5, "short", "AMBIG", None, "against_unread", False),
    (-0.5, "short", "UNKNOWN", None, "against_unread", False),
    (0.5, "short", "WITH", None, "followed_news", False),
    (0.5, "short", "AGAINST", None, "shrugged", False),
    (0.5, "short", "INLINE", None, "no_failure", False),
    (0.5, "short", "UNKNOWN", None, "no_failure", False),
    (0.0, "short", "WITH", None, "followed_news", False),                             # unchanged is not against (as detect())
    (0.5, "long", "WITH", {"status": "ok", "move": 0.5}, "failure_full", True),       # a long set up: the crowd is short, UP is against
    (-0.5, "long", "AGAINST", None, "shrugged", False),
    (None, "short", "WITH", None, "pending", False),
])
def test_the_verdict_table_row_by_row(close_z, direction, cls, fm, want, strict):
    assert cf.watch_verdict(close_z, direction, cls, fm) == (want, strict)
    assert want in cf.VERDICT_WORDS


def test_the_crowd_sentence_for_a_long_and_a_short_set_up():
    sil = [{"name": "Non Farm Payrolls", "forecast": "82.0K"}, {"name": "Unemployment Rate", "forecast": "4.2%"}]
    # the doc's example: a LONG set up (fade into long) = the crowd is SHORT silver; stronger jobs = bearish silver = their way
    # 2026-11-27: whose release and which, the figures to beat, and WHY that news reads bearish / bullish for the market
    assert cf.crowd_outcome_words("NFP", "silver", "long", sil) == (
        "US jobs report: jobs stronger than forecast (payrolls above 82.0K, unemployment below 4.2%) → a stronger US jobs "
        "market lifts US interest rates and the dollar; Silver pays no interest and is priced in dollars → bearish Silver. "
        "A failure: that news, a first move down, then a close UP.")
    # the SHORT set up: the crowd is long, so the opposite news and the opposite figures (two components, opposite signs)
    assert cf.crowd_outcome_words("NFP", "silver", "short", sil) == (
        "US jobs report: jobs weaker than forecast (payrolls below 82.0K, unemployment above 4.2%) → a weaker US jobs "
        "market lowers US interest rates and the dollar; Silver pays no interest and is priced in dollars → bullish Silver. "
        "A failure: that news, a first move up, then a close DOWN.")
    cpi = [{"name": "Inflation Rate MoM", "forecast": "0.2%", "period": "October"}, {"name": "Core Inflation Rate MoM", "forecast": None}]
    assert cf.crowd_outcome_words("CPI", "gold", "short", cpi).startswith(
        "US CPI inflation (October): inflation cooler than forecast (CPI m/m below 0.2%) → cooler US inflation lowers")
    assert "→ bearish Gold." in cf.crowd_outcome_words("CPI", "gold", "long", cpi)
    # the dollar is bought on hot inflation: the sign flips with the market
    assert "inflation hotter than forecast (CPI m/m above 0.2%) → hotter US inflation lifts US interest rates and the US " \
           "dollar → bullish Dollar Index." in cf.crowd_outcome_words("CPI", "dollar_index", "short", cpi)
    # EIA is read off the market's own stocks series; a build is bearish crude
    eia = [{"name": "EIA Crude Oil Stocks Change", "forecast": "1.5M"}]
    assert "a smaller build, or a bigger draw, than forecast (crude stocks change below 1.5M) → " in \
        cf.crowd_outcome_words("EIA_PETRO", "crude_oil", "short", eia)
    assert "means less Crude Oil supply on hand → bullish Crude Oil." in cf.crowd_outcome_words("EIA_PETRO", "crude_oil", "short", eia)
    assert "a bigger stock build, or a smaller draw, than forecast" in cf.crowd_outcome_words("EIA_PETRO", "crude_oil", "long", eia)
    # no forecast figure listed yet: the sentence still names the news, without figures
    assert "(" not in cf.crowd_outcome_words("NFP", "silver", "long", [{"name": "Non Farm Payrolls", "forecast": None}]).split("→")[0]
    # an ambiguous pair, an unmapped pair and a no-forecast event carry no sentence
    for et, m in (("NFP", "sp500"), ("CPI", "platinum"), ("OPEC", "crude_oil"), ("WASDE", "corn"), ("AU_CPI", "australian_dollar")):
        assert cf.crowd_outcome_words(et, m, "short", []) == ""
    assert [cf.watch_read(et, m) for et, m in (("CPI", "gold"), ("NFP", "sp500"), ("AU_CPI", "australian_dollar"),
                                               ("OPEC", "crude_oil"), ("ECB", "euro"), ("EARN_NVDA", "nasdaq"))] == \
        ["mapped", "ambiguous", "ambiguous", "none", "ambiguous", "mapped"]


def test_a_surprise_on_the_favoured_side_is_with_the_crowd_for_every_mapped_pair():
    """The sentence and the alert label must agree: the surprise the sentence calls 'favours the crowd' is class WITH
    under news_class, and the opposite one is AGAINST — for every mapped (event, market) pair and both directions."""
    n = 0
    for et in list(cf._US_TYPES) + ["EIA_PETRO", "EIA_NATGAS", "EARN_NVDA"]:
        for m in cf.markets_for_event(et):
            for direction in ("short", "long"):
                fz = cf.favoured_z_sign(et, m, direction)
                if fz is None:
                    continue
                src = cf._EIA_OF.get(m) if et == "EIA_PETRO" else et
                n += 1
                assert cf.news_class(et, m, direction, WED, {(WED, src): {"z": 1.0 * fz, "text": "t"}})["cls"] == "WITH", (et, m, direction)
                assert cf.news_class(et, m, direction, WED, {(WED, src): {"z": -1.0 * fz, "text": "t"}})["cls"] == "AGAINST", (et, m, direction)
    assert n > 100


def test_the_forecast_is_frozen_at_the_release():
    names = ["Non Farm Payrolls", "Unemployment Rate"]
    pre = cf.merge_series(names, None, {"Non Farm Payrolls": {"forecast": "82.0K", "previous": "165K", "actual": None},
                                        "Unemployment Rate": {"forecast": "4.2%", "previous": "4.1%", "actual": None}}, False)
    assert pre[0]["forecast"] == "82.0K" and pre[0]["previous"] == "165K" and pre[0]["actual"] is None
    # a later pre-release read refreshes it; a blank read never erases it
    again = cf.merge_series(names, pre, {"Non Farm Payrolls": {"forecast": "85.0K"}, "Unemployment Rate": {"forecast": None}}, False)
    assert again[0]["forecast"] == "85.0K" and again[1]["forecast"] == "4.2%"
    blank = cf.merge_series(names, again, {"Non Farm Payrolls": {"forecast": ""}}, False)
    assert blank[0]["forecast"] == "85.0K"
    # a read AT or AFTER the release never touches the forecast: it fills the actual and keeps the listed figure apart
    post = cf.merge_series(names, again, {"Non Farm Payrolls": {"forecast": "120.0K", "actual": "120K"},
                                          "Unemployment Rate": {"forecast": "4.1%", "actual": "4.1%"}}, True)
    assert [(s["forecast"], s["forecast_after"], s["actual"]) for s in post] == [("85.0K", "120.0K", "120K"), ("4.2%", "4.1%", "4.1%")]
    assert cf.merge_series(names, post, None, True) == post


def test_forecast_seen_at_is_stamped_by_every_pre_release_read_and_never_after():
    ev = {"event_date": FRI_NEXT, "event_type": "NFP", "release_et": _t(8, 30, FRI_NEXT)}
    fx = {"Non Farm Payrolls": {"forecast": "82.0K", "previous": "165K", "actual": None}}
    wed, thu, rel = _t(17, 15), _t(17, 15, THU), _t(8, 31, FRI_NEXT)
    r1 = cf.upcoming_watch_row(ev, "silver", "long", "main", REPORT, None, fx, wed)
    assert r1["forecast_seen_at"] == wed
    r2 = cf.upcoming_watch_row(ev, "silver", "long", "main", REPORT, r1, fx, thu)
    assert r2["forecast_seen_at"] == thu                                  # the latest pre-release read that carried a figure
    r3 = cf.upcoming_watch_row(ev, "silver", "long", "main", REPORT, r2, {"Non Farm Payrolls": {"forecast": None}}, wed + timedelta(days=2))
    assert r3["forecast_seen_at"] == thu and r3["series"][0]["forecast"] == "82.0K"   # a blank read changes nothing
    r4 = cf.upcoming_watch_row(ev, "silver", "long", "main", REPORT, r2, {"Non Farm Payrolls": {"forecast": "1K"}}, rel)
    assert r4["forecast_seen_at"] == thu and r4["series"][0]["forecast"] == "82.0K"   # after the release: untouched


def _nfp_io():
    """Wednesday 11-11 17:15: gold set up short; NFP is listed for Friday 11-13 with a forecast; CPI is today."""
    io = _daily_io()
    io.fx = [_fx("Inflation Rate MoM", "0.4%", "0.2%"), _fx("Non Farm Payrolls", None, "82.0K", "2026-11-13T13:30:00.000Z"),
             _fx("Unemployment Rate", None, "4.2%", "2026-11-13T13:30:00.000Z")]
    io.minutes["GC=F"] = [(_t(8, 29), 100.0), (_t(8, 30), 101.0)]
    return io


def test_a_daily_run_writes_today_judged_and_the_days_ahead_with_their_forecast():
    io = _nfp_io()
    res = _run(cf.run_daily(WED, io, AFTER_CLOSE))
    assert "errors" not in res["news_watch"] and res["news_watch"]["judged"] == 1 and res["news_watch"]["upcoming"] >= 1
    today = io.watch[(WED, "CPI", "gold")]
    assert today["verdict"] == "followed_news" and today["alerted"] is True and today["news_class"] == "AGAINST"
    assert today["close_against"] is True and today["close_z"] == pytest.approx(-0.5) and today["strict"] is False
    assert today["first_minute"] == {"status": "ok", "move": 0.5, "big": True} and today["judged_at"] == AFTER_CLOSE
    # the actual and the figure the source lists after the release; no forecast was seen BEFORE it (the run is the first read)
    s0 = today["series"][0]
    assert (s0["actual"], s0["forecast_after"], s0["forecast"]) == ("0.4%", "0.2%", None) and today["forecast_seen_at"] is None
    nfp = io.watch[(FRI_NEXT, "NFP", "gold")]
    assert nfp["verdict"] is None and nfp["read"] == "mapped" and nfp["forecast_seen_at"] == AFTER_CLOSE
    assert [(s["name"], s["forecast"]) for s in nfp["series"]] == [("Non Farm Payrolls", "82.0K"), ("Unemployment Rate", "4.2%")]
    assert "US jobs report: jobs weaker than forecast (payrolls below 82.0K, unemployment above 4.2%) → " in nfp["crowd_outcome"]
    assert "→ bullish Gold." in nfp["crowd_outcome"]
    assert all(k[0] > WED for k in io.watch if k[1] == "NFP")             # upcoming rows are dated after today
    assert (THU, "EIA_NATGAS", "natural_gas") not in io.watch              # natural gas is not a set-up market


def test_the_card_then_the_judgement_the_same_row_keeps_thursdays_forecast():
    io = _nfp_io()
    _run(cf.run_daily(WED, io, AFTER_CLOSE))
    thu_run = AFTER_CLOSE + timedelta(days=1)
    io.fx = [_fx("Non Farm Payrolls", None, "90.0K", "2026-11-13T13:30:00.000Z"),
             _fx("Unemployment Rate", None, "4.2%", "2026-11-13T13:30:00.000Z")]
    io.bars = {t: b + [(THU, 100.0, 101.0, 99.0, 100.0)] for t, b in io.bars.items()}
    _run(cf.run_daily(THU, io, thu_run))
    row = io.watch[(FRI_NEXT, "NFP", "gold")]
    assert row["series"][0]["forecast"] == "90.0K" and row["forecast_seen_at"] == thu_run
    # Friday: the release, then the 17:15 run. The source now lists the actual (and a revised forecast)
    fri_run = datetime(2026, 11, 13, 17, 15, tzinfo=_ET)
    io.fx = [_fx("Non Farm Payrolls", "120K", "95.0K", "2026-11-13T13:30:00.000Z"),
             _fx("Unemployment Rate", "4.1%", "4.2%", "2026-11-13T13:30:00.000Z")]
    io.cal = [r for r in io.cal if r["event_type"] != "CPI"]
    io.bars = {t: b + [(FRI_NEXT, 100.0, 101.0, 98.0, 98.5 if t == "GC=F" else 100.0)] for t, b in io.bars.items()}
    io.minutes["GC=F"] = [(_t(8, 29, FRI_NEXT), 100.0), (_t(8, 30, FRI_NEXT), 100.5)]
    res = _run(cf.run_daily(FRI_NEXT, io, fri_run))
    j = io.watch[(FRI_NEXT, "NFP", "gold")]
    assert "errors" not in res["news_watch"]
    assert j["series"][0]["forecast"] == "90.0K" and j["series"][0]["forecast_after"] == "95.0K"     # Thursday's figure stays
    assert j["series"][0]["actual"] == "120K" and j["forecast_seen_at"] == thu_run
    # stronger jobs are bearish gold = against a LONG crowd; the close was down (against the crowd) -> followed the news
    assert j["news_class"] == "AGAINST" and j["close_against"] is True and j["verdict"] == "followed_news"


def test_a_news_day_with_no_alert_still_gets_a_no_failure_row():
    io = _nfp_io()
    io.bars["GC=F"] = bars_to(WED, 101.0)                                   # gold closed the crowd's way (up)
    res = _run(cf.run_daily(WED, io, AFTER_CLOSE))
    assert res["alerts"] == 0 and io.alerts == {}
    row = io.watch[(WED, "CPI", "gold")]
    assert row["alerted"] is False and row["close_against"] is False and row["verdict"] == "shrugged"   # hot CPI = bad for a gold long
    assert row["strict"] is False


def test_a_strict_failure_needs_news_with_the_crowd_a_first_move_their_way_and_a_close_against():
    io = _nfp_io()
    io.fx = [_fx("Inflation Rate MoM", "0.0%", "0.2%")]                     # cooler inflation = good for gold = WITH a long crowd
    io.minutes["GC=F"] = [(_t(8, 29), 100.0), (_t(8, 30), 100.8)]           # the first minute went the crowd's way (up, 0.4 of a range)
    _run(cf.run_daily(WED, io, AFTER_CLOSE))
    row = io.watch[(WED, "CPI", "gold")]
    assert (row["verdict"], row["strict"], row["alerted"]) == ("failure_full", True, True)
    # the same day with no minute bars: still a news failure by the close, but not the strict three-step one
    io2 = _nfp_io()
    io2.fx = [_fx("Inflation Rate MoM", "0.0%", "0.2%")]
    io2.minutes = {}
    _run(cf.run_daily(WED, io2, AFTER_CLOSE))
    row2 = io2.watch[(WED, "CPI", "gold")]
    assert (row2["verdict"], row2["strict"], row2["alerted"]) == ("failure", False, True)


def test_an_event_with_no_forecast_and_a_market_with_no_bar_still_get_rows():
    io = _nfp_io()
    io.weeks[REPORT]["rows"]["crude_oil"] = _ix(3, 97, 96, "short")
    io.bars["CL=F"] = bars_to(WED, 99.0)
    io.bars.update({t: bars_to(WED, 100.0) for t in ("HO=F", "RB=F")})
    io.cal.append({"event_date": WED, "event_type": "OPEC", "release_et": None, "source": cf.OPEC_SOURCE})
    _run(cf.run_daily(WED, io, AFTER_CLOSE))
    k = io.watch[(WED, "OPEC", "crude_oil")]
    assert k["series"] == [] and k["read"] == "none" and k["crowd_outcome"] == ""
    assert k["first_minute"] == {"status": "no release time"} and k["verdict"] == "against_unread"
    # a set-up market the price source gave no bar for: judged "pending", never missing
    io2 = _nfp_io()
    io2.bars["GC=F"] = io2.bars["GC=F"][:-1]
    with pytest.raises(cf.CotError):                     # the missing bar pages, as before; the watch still ran
        _run(cf.run_daily(WED, io2, AFTER_CLOSE))
    assert io2.watch[(WED, "CPI", "gold")]["verdict"] == "pending" and io2.watch[(WED, "CPI", "gold")]["close_z"] is None
    assert io2.alerts == {}


def test_a_failing_watch_changes_neither_the_alert_nor_the_message_nor_the_outcome():
    ok = _nfp_io()
    _run(cf.run_daily(WED, ok, AFTER_CLOSE))
    bad = _nfp_io()
    bad.watch_fail = RuntimeError("database says no")
    res = _run(cf.run_daily(WED, bad, AFTER_CLOSE))          # no raise: a watch failure never pages or fails the job
    assert res["alerts"] == 1 and res["sent"] is True and res.get("problems") == []
    assert bad.sent == ok.sent and {k: (v["entry_price"], v["stop_price"], v["news_class"]) for k, v in bad.alerts.items()} == \
        {k: (v["entry_price"], v["stop_price"], v["news_class"]) for k, v in ok.alerts.items()}
    assert set(res["news_watch"]["errors"]) == {"judge", "upcoming"} and "database says no" in res["news_watch"]["errors"]["judge"]
    assert [a[0] for a in bad.audits] == ["cot_daily"] and bad.watch == {}


def test_upcoming_rows_follow_the_newest_week_and_todays_rows_follow_the_week_known_before_today():
    newer = {date(2026, 11, 10): {"known_from": WED, "sent": "x", "rows": {"silver": _ix(2, 99, 99, "short")}}}
    io = _nfp_io()
    io.weeks.update(newer)
    io.cftc_rows = [("088691", date(2026, 11, 10), 1, 2, 3, 4)]
    _run(cf.run_daily(WED, io, AFTER_CLOSE))
    assert (WED, "CPI", "gold") in io.watch and (WED, "CPI", "silver") not in io.watch      # today = the week known before today
    assert io.watch[(WED, "CPI", "gold")]["report_date"] == REPORT
    assert (FRI_NEXT, "NFP", "silver") in io.watch and (FRI_NEXT, "NFP", "gold") not in io.watch   # ahead = the newest stored week
    assert io.watch[(FRI_NEXT, "NFP", "silver")]["report_date"] == date(2026, 11, 10)


def test_the_next_weeks_page_is_read_once_and_a_bad_read_is_recorded_not_paged():
    io = _nfp_io()
    res = _run(cf.run_daily(WED, io, AFTER_CLOSE))
    assert io.fx_calls == [("united-states", date(2026, 11, 9)), ("united-states", date(2026, 11, 16))]
    assert res["problems"] == []
    # an empty answer for next week: recorded, the stored calendar rows kept, no page
    io = _nfp_io()
    io.cal.append({"event_date": date(2026, 11, 19), "event_type": "EIA_NATGAS", "release_et": _t(10, 30, date(2026, 11, 19)), "source": cf.US_SOURCE})
    io.fx_weeks = {date(2026, 11, 16): []}
    res = _run(cf.run_daily(WED, io, AFTER_CLOSE))
    assert "next week" in res["news_watch"]["errors"] and res["problems"] == []
    assert (date(2026, 11, 19), "EIA_NATGAS") in {(r["event_date"], r["event_type"]) for r in io.cal}
    # a refusal on that extra request: recorded, no page, the alert already went out
    class Refuse(FakeIo):
        def fxempire(self, country, d0, d1):
            if d0 == date(2026, 11, 16):
                raise cf.CalendarRefused("429")
            return super().fxempire(country, d0, d1)
    io = _nfp_io()
    io.__class__ = Refuse
    res = _run(cf.run_daily(WED, io, AFTER_CLOSE))
    assert res["alerts"] == 1 and res["sent"] is True and res["problems"] == [] and "next week" in res["news_watch"]["errors"]


def test_on_a_full_refresh_day_the_watch_reuses_the_rows_the_refresh_read():
    io = _nfp_io()
    io.cal_age = 8
    res = _run(cf.run_daily(WED, io, AFTER_CLOSE))
    assert len(io.fx_calls) == 1 + 3 + 6 and "errors" not in res["news_watch"]


def test_the_weekly_job_rebuilds_the_days_ahead_without_any_calendar_request():
    io = _weekly_io()
    mon = date(2026, 11, 9)
    io.cal = [{"event_date": mon, "event_type": "WASDE", "release_et": _t(12, 0, mon), "source": "usda.gov WASDE release dates"},
              {"event_date": mon, "event_type": "OPEC", "release_et": None, "source": cf.OPEC_SOURCE}]
    io.watch[(mon, "WASDE", "corn")] = {"event_date": mon, "event_type": "WASDE", "market": "corn", "series": []}   # corn is not set up
    res = _run(cf.run_weekly(FRI, io, datetime(2026, 11, 6, 17, 40, tzinfo=_ET)))
    # the watch makes no request of its own (the only reads are the Friday check's, of the weeks BEFORE the next days)
    assert res["status"] == "sent" and all(d0 < mon for _c, d0 in io.fx_calls) and "errors" not in res["news_watch"]
    assert set(io.watch) == {(mon, "WASDE", "wheat"), (mon, "WASDE", "lean_hogs")}      # exactly the newest week's set ups
    assert io.watch[(mon, "WASDE", "wheat")]["read"] == "none" and io.watch[(mon, "WASDE", "wheat")]["series"] == []
    # a weekly watch failure never changes the weekly outcome
    io2 = _weekly_io()
    io2.cal = list(io.cal)
    io2.watch_fail = RuntimeError("boom")
    res2 = _run(cf.run_weekly(FRI, io2, datetime(2026, 11, 6, 17, 40, tzinfo=_ET)))
    assert res2["status"] == "sent" and "boom" in res2["news_watch"]["errors"]["upcoming"]


def test_a_market_new_to_the_list_copies_the_stored_figures_of_the_same_event():
    io = FakeIo()
    io.weeks[REPORT] = {"known_from": FRI_BEFORE, "sent": "x",
                        "rows": {"gold": _ix(3, 97, 96, "short"), "silver": _ix(3, 97, 96, "short"), "crude_oil": _ix(3, 97, 96, "short")}}
    mon = date(2026, 11, 9)
    io.cal = [{"event_date": mon, "event_type": "NFP", "release_et": _t(8, 30, mon), "source": cf.US_SOURCE},
              {"event_date": mon, "event_type": "EIA_PETRO", "release_et": _t(10, 30, mon), "source": cf.US_SOURCE}]
    figs = [{"name": "Non Farm Payrolls", "forecast": "82.0K", "previous": "165K", "actual": None, "forecast_after": None},
            {"name": "Unemployment Rate", "forecast": "4.2%", "previous": "4.1%", "actual": None, "forecast_after": None}]
    seen = _t(17, 15)
    io.watch[(mon, "NFP", "gold")] = {"event_date": mon, "event_type": "NFP", "market": "gold", "series": figs, "forecast_seen_at": seen}
    io.watch[(mon, "EIA_PETRO", "gold")] = {"event_date": mon, "event_type": "EIA_PETRO", "market": "gold", "series": [], "forecast_seen_at": None}
    nw = {"errors": {}}
    _run(cf._watch_upcoming(io, date(2026, 11, 6), datetime(2026, 11, 6, 17, 40, tzinfo=_ET), nw, None, False, {}, None))
    sil = io.watch[(mon, "NFP", "silver")]
    assert sil["series"][0]["forecast"] == "82.0K" and sil["forecast_seen_at"] == seen and "payrolls below 82.0K" in sil["crowd_outcome"]
    # EIA stocks are per market (crude / gasoline / distillate): a figure is never copied across them
    assert io.watch[(mon, "EIA_PETRO", "crude_oil")]["series"][0]["forecast"] is None and nw["errors"] == {}
    assert io.fx_calls == []


def test_an_earnings_estimate_listed_ahead_is_the_forecast_and_the_reported_eps_the_actual():
    io = _daily_io()
    io.weeks[REPORT]["rows"]["nasdaq"] = _ix(3, 97, 96, "short")
    io.bars["NQ=F"] = bars_to(WED, 100.0)
    io.bars.update({t: bars_to(WED, 100.0) for t in ("YM=F", "RTY=F", "ES=F")})
    after = datetime(2026, 11, 12, 16, 30, tzinfo=_ET)                      # Thursday after the close: its session is Friday
    io.earn = {"NVDA": [{"ts": after, "surprise_pct": None, "reported": None, "estimate": 1.25}]}
    io.cal.append({"event_date": FRI_NEXT, "event_type": "EARN_NVDA", "release_et": after, "source": "yfinance earnings dates"})
    res = _run(cf.run_daily(WED, io, AFTER_CLOSE))
    assert "errors" not in res["news_watch"]
    row = io.watch[(FRI_NEXT, "EARN_NVDA", "nasdaq")]
    assert row["series"] == [{"name": "EPS", "forecast": "1.25", "previous": None, "actual": None, "forecast_after": None,
                              "label": "EPS", "period": None}]
    assert row["crowd_outcome"].startswith("NVDA earnings: an EPS beat (EPS above 1.25) → NVDA earnings beating forecast "
                                           "lifts large US stocks broadly → bullish Nasdaq.")


def _fake_pool_io(fetched=None):
    """An Io over a recording fake pool: the REAL watch_rows / replace_watch run against it (FakeIo overrides both)."""
    log = []

    class _Tx:
        async def __aenter__(self):
            log.append(("begin",))

        async def __aexit__(self, *a):
            log.append(("commit",))
            return False

    class _Conn:
        def transaction(self):
            return _Tx()

        async def execute(self, sql, *args):
            log.append(("execute", sql, args))

        async def executemany(self, sql, rows):
            log.append(("executemany", sql, [list(r) for r in rows]))

        async def fetch(self, sql, *args):
            log.append(("fetch", sql, args))
            return list(fetched or [])

    class _Acq:
        async def __aenter__(self):
            return _Conn()

        async def __aexit__(self, *a):
            return False

    class _Pool:
        def acquire(self):
            return _Acq()

    class _RealIo(cf.Io):
        async def _pool(self):
            return _Pool()

    return _RealIo(), log


def test_the_real_watch_writer_deletes_then_inserts_in_one_transaction_with_objects_bound_as_objects():
    io, log = _fake_pool_io()
    row = {c: None for c in cf._COT_WATCH_COLS}
    row.update(event_date=THU, event_type="NFP", market="gold", release_et=_t(8, 30, THU), direction="short", level="main",
               report_date=REPORT, read="mapped", series=[{"name": "Non Farm Payrolls", "forecast": "82.0K"}],
               first_minute={"status": "ok", "move": 0.3, "big": True}, forecast_seen_at=_t(17, 15))
    _run(io.replace_watch(THU, THU, [row]))
    assert [e[0] for e in log] == ["begin", "execute", "executemany", "commit"]
    assert log[1][1] == cf._COT_WATCH_DELETE_SQL and log[1][2] == (THU, THU)
    sql, binds = log[2][1], log[2][2]
    assert sql == cf._COT_WATCH_UPSERT_SQL and len(binds) == 1 and len(binds[0]) == len(cf._COT_WATCH_COLS) == 20
    b = dict(zip(cf._COT_WATCH_COLS, binds[0]))
    assert isinstance(b["series"], list) and isinstance(b["first_minute"], dict)        # objects: the jsonb codec encodes them
    assert b["forecast_seen_at"] == _t(17, 15) and b["verdict"] is None and b["close_z"] is None
    # nothing to write still clears the range (a market no longer set up leaves no row behind)
    io2, log2 = _fake_pool_io()
    _run(io2.replace_watch(THU, THU, []))
    assert [e[0] for e in log2] == ["begin", "execute", "commit"]


def test_the_real_watch_reader_decodes_a_json_string_and_keeps_objects():
    rec = {c: None for c in cf._COT_WATCH_COLS}
    rec.update(series='[{"name": "x"}]', first_minute={"status": "ok"})
    io, log = _fake_pool_io([rec])
    got = _run(io.watch_rows(THU, THU))
    assert got[0]["series"] == [{"name": "x"}] and got[0]["first_minute"] == {"status": "ok"}
    assert log[0][1] == cf._COT_WATCH_READ_SQL and log[0][2] == (THU, THU)


def test_a_refusal_on_a_country_page_stops_the_next_weeks_request_too():
    io = _nfp_io()
    io.weeks[REPORT]["rows"]["australian_dollar"] = _ix(3, 97, 96, "short")
    io.bars["6A=F"] = bars_to(WED, 100.0)
    io.bars.update({t: bars_to(WED, 100.0) for t in ("6B=F", "6C=F", "6E=F", "6J=F", "6S=F", "6N=F", "DX-Y.NYB")})
    io.cal.append({"event_date": WED, "event_type": "AU_CPI", "release_et": _t(6, 30), "source": "s"})

    class Refuse(FakeIo):
        def fxempire(self, country, d0, d1):
            if country == "australia":
                raise cf.CalendarRefused("429")
            return super().fxempire(country, d0, d1)
    io.__class__ = Refuse
    res = _run(cf.run_daily(WED, io, AFTER_CLOSE))
    assert "fxempire australia" in res["news_watch"]["errors"] and res["problems"] == []
    assert io.fx_calls == [("united-states", date(2026, 11, 9))]     # the refused call is not recorded, and no next-week request follows it


# ── 11-25 review round: scored on the lined-up forecast, pending re-judged, visible failures, two surviving mutations ──
def _nfp_series(stored, after, actual):
    return [{"name": "Non Farm Payrolls", "forecast": stored, "previous": "165K", "actual": actual, "forecast_after": after}]


def test_the_news_is_scored_on_thursdays_stored_forecast_not_the_release_day_read():
    """The reviewer's NFP case: stored 82.0K on Thursday, the source lists 200K after the release, actual 150K. Scored on
    the release-day read it is AGAINST the (short silver) crowd; on the lined-up 82.0K it is WITH them: full failure."""
    ev = {"event_date": FRI_NEXT, "event_type": "NFP", "release_et": _t(8, 30, FRI_NEXT)}
    old = {"series": _nfp_series("82.0K", None, None), "forecast_seen_at": _t(17, 15, THU)}
    fresh = {"Non Farm Payrolls": {"forecast": "200K", "previous": "165K", "actual": "150K"}}
    release_day = {"cls": "AGAINST", "z": -1.0, "text": "Non Farm Payrolls 150K vs 200K"}      # what news_class() gives from `fresh`
    fm = {"status": "ok", "move": 0.3, "big": True}
    row = cf.judged_watch_row(ev, "silver", "long", "main", REPORT, old, fresh, release_day, fm, {"z": 0.4}, True,
                              _t(17, 15, FRI_NEXT))
    s = row["series"][0]
    assert (s["forecast"], s["forecast_after"], s["actual"]) == ("82.0K", "200K", "150K")
    assert row["news_class"] == "WITH" and row["surprise_z"] > 0
    assert (row["verdict"], row["strict"], row["close_against"]) == ("failure_full", True, True)


def test_with_no_stored_forecast_the_release_day_read_stands():
    ev = {"event_date": FRI_NEXT, "event_type": "NFP", "release_et": _t(8, 30, FRI_NEXT)}
    fresh = {"Non Farm Payrolls": {"forecast": "200K", "previous": "165K", "actual": "150K"}}
    nc = {"cls": "AGAINST", "z": -1.0, "text": ""}
    row = cf.judged_watch_row(ev, "silver", "long", "main", REPORT, None, fresh, nc, {"status": "ok", "move": 0.3}, {"z": 0.4}, False,
                              _t(17, 15, FRI_NEXT))
    assert row["series"][0]["forecast"] is None and row["series"][0]["forecast_after"] == "200K"
    assert row["news_class"] == "AGAINST" and row["verdict"] == "followed_news"
    assert cf.frozen_news_class("NFP", "silver", "long", FRI_NEXT, row["series"]) is None


def test_a_pending_row_is_judged_again_once_its_bar_exists_and_keeps_what_it_stored(monkeypatch):
    io = _nfp_io()
    tue = WED - timedelta(days=1)
    io.bars["GC=F"] = [b if b[0] != tue else (tue, 100.0, 101.0, 99.0, 98.0) for b in io.bars["GC=F"]]   # Tuesday closed DOWN
    pend = cf.judged_watch_row({"event_date": tue, "event_type": "CPI", "release_et": _t(8, 30, tue)}, "gold", "short", "main", REPORT,
                               {"series": [{"name": "Inflation Rate MoM", "forecast": "0.3%", "previous": None, "actual": "0.2%",
                                            "forecast_after": "0.3%"}]}, None, {"cls": "WITH", "z": 0.5, "text": ""},
                               {"status": "ok", "move": 0.4, "big": True}, None, True, _t(17, 15, tue))
    assert pend["verdict"] == "pending"
    io.watch[(tue, "CPI", "gold")] = pend
    res = _run(cf.run_daily(WED, io, AFTER_CLOSE))
    row = io.watch[(tue, "CPI", "gold")]
    assert res["news_watch"]["rejudged"] == 1 and "errors" not in res["news_watch"]
    assert row["close_against"] is True and row["verdict"] != "pending" and row["alerted"] is True
    assert row["first_minute"] == {"status": "ok", "move": 0.4, "big": True}        # what it stored is kept
    # still no bar for its day: left pending, nothing rewritten
    io2 = _nfp_io()
    io2.bars["GC=F"] = [b for b in io2.bars["GC=F"] if b[0] != tue]
    io2.watch[(tue, "CPI", "gold")] = pend
    res2 = _run(cf.run_daily(WED, io2, AFTER_CLOSE))
    assert "rejudged" not in res2["news_watch"] and io2.watch[(tue, "CPI", "gold")]["verdict"] == "pending"


def test_a_watch_failure_is_counted_on_the_audit_summary_line():
    bad = _nfp_io()
    bad.watch_fail = RuntimeError("database says no")
    res = _run(cf.run_daily(WED, bad, AFTER_CLOSE))
    assert res["news_watch"]["error_count"] == 2
    assert "NEWS WATCH ERRORS 2" in bad.audits[-1][1]
    ok = _nfp_io()
    _run(cf.run_daily(WED, ok, AFTER_CLOSE))
    assert "NEWS WATCH ERRORS" not in ok.audits[-1][1]


def test_a_recovery_rerun_judges_today_but_never_rewrites_the_days_ahead(monkeypatch):
    """Kills the mutation that drops the `held` guard: a #672 re-run of a past slot would overwrite tomorrow's cards."""
    monkeypatch.setattr(cf, "recovery_pin", lambda: object())
    io = _nfp_io()
    ahead = (FRI_NEXT, "NFP", "gold")
    io.watch[ahead] = {**cf.upcoming_watch_row({"event_date": FRI_NEXT, "event_type": "NFP", "release_et": _t(8, 30, FRI_NEXT)},
                                               "gold", "short", "main", REPORT, None, None, _t(17, 15, THU)), "crowd_outcome": "SENTINEL"}
    res = _run(cf.run_daily(WED, io, AFTER_CLOSE))
    assert res["held"] is True and res["news_watch"]["judged"] == 1 and "upcoming" not in res["news_watch"]
    assert io.watch[ahead]["crowd_outcome"] == "SENTINEL"                      # untouched
    assert (WED, "CPI", "gold") in io.watch                                    # today IS judged


def test_a_market_no_longer_set_up_leaves_no_row_behind():
    """Kills the mutation that skips the delete in replace_watch's callers: stored rows of a market that dropped out of the
    set-ups (today's and the days ahead) are gone after the run; the set-up market's rows stay."""
    io = _nfp_io()
    for d, et in ((WED, "CPI"), (FRI_NEXT, "NFP")):
        io.watch[(d, et, "copper")] = cf._watch_row({"event_date": d, "event_type": et}, "copper", "short", "main", REPORT, "mapped")
    _run(cf.run_daily(WED, io, AFTER_CLOSE))
    assert (WED, "CPI", "copper") not in io.watch and (FRI_NEXT, "NFP", "copper") not in io.watch
    assert (WED, "CPI", "gold") in io.watch and (FRI_NEXT, "NFP", "gold") in io.watch


def test_a_stale_row_is_deleted_even_when_no_set_up_market_has_an_event_today():
    io = _nfp_io()
    io.cal = [r for r in io.cal if r["event_date"] != WED]
    io.fx = [_fx("Non Farm Payrolls", None, "82.0K", "2026-11-13T13:30:00.000Z"), _fx("Unemployment Rate", None, "4.2%", "2026-11-13T13:30:00.000Z")]
    io.watch[(WED, "CPI", "copper")] = cf._watch_row({"event_date": WED, "event_type": "CPI"}, "copper", "short", "main", REPORT, "mapped")
    res = _run(cf.run_daily(WED, io, AFTER_CLOSE))
    assert res["news_watch"]["judged"] == 0 and (WED, "CPI", "copper") not in io.watch


def test_the_watchs_own_minute_pulls_are_spaced_and_a_cached_one_is_not_paused():
    io = _nfp_io()
    pauses = []
    io.pause = lambda sec: pauses.append(sec)
    io.minutes["GC=F"] = [(_t(8, 29), 100.0), (_t(8, 30), 101.0)]
    ctx = {"setups": {"gold": ("short", "main")}, "cal": [{"event_date": WED, "event_type": "CPI", "release_et": _t(8, 30), "source": "s"}],
           "feats": {"gold": {"z": -0.5, "atr": 2.0}}, "report": REPORT, "alerted": set(), "bars": {}}
    nw = {"errors": {}}
    _run(cf._watch_judge(io, WED, AFTER_CLOSE, nw, ctx, [], False, {}))
    assert pauses == [cf.MINUTE_PULL_PAUSE]
    pauses.clear()
    _run(cf._watch_judge(io, WED, AFTER_CLOSE, nw, ctx, [], False, {("min", "gold"): [(_t(8, 29), 100.0), (_t(8, 30), 101.0)]}))
    assert pauses == []


# ── plain wording: the news is read in ASSET terms (11-25 ruling: no "the crowd's way" outside the set-up line) ────

@pytest.mark.parametrize("cls,direction,want", [
    ("WITH", "short", "bullish"),       # short set up = the crowd is LONG: news with them is bullish
    ("AGAINST", "short", "bearish"),
    ("WITH", "long", "bearish"),        # long set up = the crowd is SHORT: news with them is bearish
    ("AGAINST", "long", "bullish"),
    ("INLINE", "long", "in line"), ("AMBIG", "short", "no clear read"), ("UNKNOWN", "long", "no clear read")])
def test_news_read_is_in_asset_terms_for_a_long_and_a_short_set_up(cls, direction, want):
    assert cf.news_read(cls, direction) == want


def test_first_minute_and_peers_convert_to_asset_terms_for_a_long_and_a_short_set_up():
    # long set up (crowd SHORT): +0.20 the crowd's way = the asset DOWN 0.20; short set up (crowd LONG) = UP
    assert cf.asset_move(0.20, "long") == -0.20 and cf.asset_move(0.20, "short") == 0.20
    silver_long = _alert(market="silver", direction="long", kinds=["news"], events=["GDP", "PCE"], z=0.5, peer_z=None,
                         first_minute={"status": "ok", "move": 0.20, "big": False}, news_class="WITH",
                         news_text=["GDP: growth stronger than forecast (GDP QoQ 3.0% vs 2.5%) = bearish Silver"],
                         news_detail=[{"event": "GDP", "class": "WITH", "z": 2.95, "fact": "growth stronger than forecast", "read": "bearish"},
                                      {"event": "PCE", "class": "WITH", "z": 0.31, "fact": "inflation hotter than forecast", "read": "bearish"}],
                         comm=100, lspec=0, sspec=0)
    t = cf.format_daily_message(WED, REPORT, [silver_long])
    assert "first minute after the release: down 0.20 of a day's range (small; big starts at 0.25)" in t
    assert "Silver closed up 0.50 of a day's range" in t and "news vs consensus: bearish Silver" in t
    assert "a news failure: bearish news for Silver (US GDP, US PCE inflation), yet Silver closed UP." in t
    assert ("Crowded short: large specs 0 of 100 (max short), small specs 0 of 100 (max short), commercials 100 of 100 "
            "(max long). The set up is long (it fades the crowd).") in t
    assert "crowd's way" not in t and "against the crowd" not in t.lower()
    gold_short = cf.format_daily_message(WED, REPORT, [_alert(first_minute={"status": "ok", "move": 0.2, "big": False})])
    assert "first minute after the release: up 0.20 of a day's range (small; big starts at 0.25)" in gold_short
    # peers: stored + = the crowd's way; a short set up (crowd long) = peers UP
    assert "its peers (" in gold_short and "closed UP (median 0.80 of a day's range)" in gold_short


def test_news_facts_and_verdict_words_in_the_markets_own_terms():
    assert cf.news_fact("PCE", 0.31) == "inflation hotter than forecast" and cf.news_fact("PCE", -0.4) == "inflation cooler than forecast"
    assert cf.news_fact("EARN_NVDA", 1.0) == "an EPS beat" and cf.news_fact("CPI", None) == "" and cf.news_fact("OPEC", 1.0) == ""
    assert cf.verdict_words("failure_full", "short", "gold") == "NEWS FAILURE: bullish news, first move up, closed DOWN"
    assert cf.verdict_words("failure_full", "long", "silver") == "NEWS FAILURE: bearish news, first move down, closed UP"
    assert cf.verdict_words("failure", "long", "silver") == "News failure: bearish news, closed UP"
    assert cf.verdict_words("followed_news", "long", "silver") == "No failure: Silver followed the news"
    assert cf.verdict_words("shrugged", "short", "gold") == "No failure: bearish news, Gold closed up anyway"
    assert cf.verdict_words("shrugged", "long", "silver") == "No failure: bullish news, Silver closed down anyway"
    assert cf.verdict_words("no_failure", "long", "silver") == "No failure: closed DOWN"
    for code in cf.VERDICT_WORDS:
        for d in ("long", "short"):
            assert "crowd" not in cf.verdict_words(code, d, "gold").lower() and "crowd" not in cf.VERDICT_WORDS[code].lower()


def test_the_alert_detail_carries_a_plain_fact_and_read_per_news_item():
    io = _daily_io()
    io.minutes["GC=F"] = [(_t(8, 29), 100.0), (_t(8, 30), 101.0)]
    io.fx = [_fx("Inflation Rate MoM", "0.4%", "0.2%")]
    _run(cf.run_daily(WED, io, AFTER_CLOSE))
    row = io.alerts[(WED, "gold", "short", "news")]
    det = row["detail"] if isinstance(row["detail"], dict) else __import__("json").loads(row["detail"])
    item = det["news"][0]
    assert item["fact"] == "inflation hotter than forecast" and item["read"] == "bearish"   # hot CPI, a long crowd: bearish gold
    # 2026-11-27: whose release, the figures that made the surprise, and why
    assert item["country"] == "US" and item["release"] == "US CPI inflation"
    assert item["series"][0]["actual"] == "0.4%" and item["series"][0]["forecast"] == "0.2%" and item["series"][0]["vs"] == "hotter"
    assert item["why"] == ("hotter US inflation lifts US interest rates and the dollar; Gold pays no interest and is priced "
                           "in dollars → bearish Gold")
    assert "US CPI inflation: CPI m/m 0.4% vs 0.2% forecast: hotter → hotter US inflation" in io.sent[0]
    assert "→ bearish Gold" in io.sent[0] and "news vs consensus: bearish Gold" in io.sent[0]


# ── news in plain words (2026-11-27): whose release, which one, the figures, why ─────────────────────────────────
# The 11-25 rows, as FXEmpire served them (scripts/probes/_cot_newswatch_design_1125/nw_fx_1123_1206.json).
def _fx1125(name, actual, forecast, previous, reference):
    return {"name": name, "actual": actual, "forecast": forecast, "previous": previous, "reference": reference,
            "date": "2026-11-25T13:30:00.000Z"}


FX_1125 = [_fx1125("GDP Growth Rate QoQ 2nd Est", "4.3%", "3.5%", "2.2%", "Q3"),
           _fx1125("PCE Price Index MoM", "0.3%", "0.3%", "0.5%", "Oct"),
           _fx1125("Core PCE Price Index MoM", "0.3%", "0.3%", "0.3%", "Oct"),
           _fx1125("PCE Price Index YoY", "3.8%", "3.8%", "3.7%", "Oct"),
           _fx1125("Core PCE Price Index YoY", "3.3%", "3.2%", "3.1%", "Oct")]
D1125 = date(2026, 11, 25)


def _item_1125(event, market, direction="long"):
    sur = cf.surprises_from_fx(FX_1125)
    return cf.news_item(event, market, direction, cf.news_class(event, market, direction, D1125, sur), {"status": "ok"})


def test_a_gdp_beat_on_the_new_zealand_dollar_reads_bearish_with_the_dollar_chain():
    it = _item_1125("GDP", "new_zealand_dollar")
    assert it["z"] == pytest.approx(2.954198839738405)           # the stored 11-25 z: these are the figures that made it
    assert it["class"] == "WITH" and it["read"] == "bearish"
    assert it["text"] == ("US GDP (Q3, second estimate): GDP q/q 4.3% vs 3.5% forecast (previous 2.2%): stronger → stronger "
                          "US growth lifts US interest rates and the US dollar against the New Zealand Dollar → bearish New "
                          "Zealand Dollar")


def test_a_hotter_pce_on_silver_reads_bearish_and_says_which_of_the_four_figures_moved():
    it = _item_1125("PCE", "silver")
    assert it["z"] == pytest.approx(0.3122498098398647) and it["read"] == "bearish"
    assert it["text"] == ("US PCE inflation (October): core PCE y/y 3.3% vs 3.2% forecast (previous 3.1%): hotter; as forecast: "
                          "PCE m/m 0.3%, core PCE m/m 0.3%, PCE y/y 3.8% → hotter US inflation lifts US interest rates and "
                          "the dollar; Silver pays no interest and is priced in dollars → bearish Silver")


def test_unemployment_above_forecast_is_weaker_jobs_not_stronger():
    s = cf.surprises_from_fx([_fx("Non Farm Payrolls", "150K", "100K"), _fx("Unemployment Rate", "4.3%", "4.2%")])
    assert [x["vs"] for x in s[(WED, "NFP")]["series"]] == ["stronger", "weaker"]


def test_periods_and_releases_in_plain_words():
    assert cf.period_words("GDP Growth Rate QoQ Adv", "Q3") == "Q3, first estimate"
    assert cf.period_words("EIA Crude Oil Stocks Change", "Nov/20") == "week to Nov 20"
    assert cf.period_words("PCE Price Index MoM", "Oct") == "October" and cf.period_words("Fed Interest Rate Decision", "") == ""
    assert cf.release_label("AU_CPI", [{"period": "October"}]) == "Australia CPI inflation (October)"
    assert cf.release_label("EARN_NVDA") == "NVDA earnings" and cf.release_label("OPEC") == "OPEC+ meeting"
    for et in set(cf.EVENT_MARKETS) | {"EARN_NVDA"}:          # every event that can fire names whose release it is
        key = "EARN" if et.startswith("EARN_") else et
        assert key in cf.RELEASE_NAMES and cf.release_country(et), et


def _every_pair():
    """Every (event, market) the calendar can attach: the derived population, never a hand list."""
    for et in sorted(set(cf.EVENT_MARKETS) | {f"EARN_{tk}" for tk in cf.EARNINGS_TICKERS}):
        for m in cf.markets_for_event(et):
            yield et, m


def test_the_why_table_covers_every_mapped_pair_and_never_contradicts_the_sign():
    n = 0
    for et, m in _every_pair():
        mp = cf.news_sign(et, m)
        key = "EARN" if et.startswith("EARN_") else et
        entry = cf.WHY.get((cf.WHY_FAMILY.get(key), cf.WHY_GROUP.get(m)))
        if mp in (1, -1):
            assert entry is not None and entry[0] == mp, (et, m)          # a chain exists, and it explains THIS sign
            for z in (1.0, -1.0):
                w = cf.why_words(et, m, z)
                read = "bullish" if z * mp > 0 else "bearish"
                assert w.endswith(f"→ {read} {cf.name_of(m).title()}"), (et, m, z, w)
                # the alert label's read for the same surprise, both set-up directions
                for direction in ("short", "long"):
                    src = cf._EIA_OF.get(m) if et == "EIA_PETRO" else et
                    nc = cf.news_class(et, m, direction, WED, {(WED, src): {"z": z, "text": ""}})
                    assert cf.news_read(nc["cls"], direction) == read, (et, m, z, direction)
                n += 1
        else:                                                            # 0 = no clear read, None = no mapping: no reason
            assert entry is None, (et, m)
            assert cf.why_words(et, m, 1.0) == "" and cf.why_words(et, m, -1.0) == ""
    assert n > 150


def test_an_unmapped_or_in_line_item_states_the_fact_and_no_invented_reason():
    au = cf.news_item("AU_CPI", "australian_dollar", "short", {"cls": "UNKNOWN", "z": None, "text": ""}, {},
                      [cf.series_entry("Inflation Rate MoM", "0.5%", "0.4%", "0.8%", "Oct", 1, "AU_CPI")])
    assert au["text"] == ("Australia CPI inflation (October): CPI m/m 0.5% vs 0.4% forecast (previous 0.8%): above forecast → "
                          "no bullish / bearish read is mapped for this release on Australian Dollar") and au["why"] == ""
    amb = _item_1125("GDP", "platinum")
    assert amb["class"] == "AMBIG" and amb["why"] == "" and amb["text"].endswith("no clear read for Platinum (the research maps "
                                                                                "no direction for this release on this market)")
    flat = cf.news_item("CPI", "gold", "short", {"cls": "INLINE", "z": 0.1, "text": ""}, {})
    assert flat["why"] == "" and flat["surprise"] == "in line with forecast" and flat["text"] == \
        "US CPI inflation → in line with forecast: no read either way for Gold"


def test_a_friday_confirmation_names_whose_release_it_was():
    a = {"market": "wheat", "direction": "long", "kinds": ["news"], "events": ["WASDE", "USDA_EXPORTS"],
         "failure_day": date(2026, 11, 5), "stop_rule": "a close below 5"}
    t = cf.format_weekly_message(REPORT, {}, {}, [], [a], "Sunday open", [])
    assert "releases: US USDA WASDE crop report; US USDA weekly export sales" in t


def _au_io(close=101.0):
    """Wednesday 11-11: the Australian dollar on the close list LONG (crowd short), closing UP on Australian CPI day."""
    io = _daily_io()
    io.weeks[REPORT]["rows"] = {"australian_dollar": _ix(97, 3, 30, None, "long")}
    io.bars = {"6A=F": bars_to(WED, close)}
    io.cal = [{"event_date": WED, "event_type": "AU_CPI", "release_et": _t(19, 30, date(2026, 11, 10)), "source": "s"}]
    io.fx_bank["australia"] = [{"name": "Inflation Rate MoM", "actual": "0.5%", "forecast": "0.4%", "previous": "0.8%",
                                "reference": "Oct", "date": "2026-11-11T00:30:00.000Z"}]
    return io


def test_a_non_us_release_prints_its_own_page_figures_read_once_per_run():
    io = _au_io()
    res = _run(cf.run_daily(WED, io, AFTER_CLOSE))
    assert res["alerts"] == 1 and res["sent"] is True and res["problems"] == []
    item = io.alerts[(WED, "australian_dollar", "long", "news")]["detail"]["news"][0]
    assert item["release"] == "Australia CPI inflation (October)" and item["country"] == "Australia"
    assert (item["series"][0]["actual"], item["series"][0]["forecast"], item["series"][0]["vs"]) == ("0.5%", "0.4%", "above forecast")
    assert item["class"] == "UNKNOWN" and item["why"] == ""                     # no read is mapped: the fact, no reason
    assert "Australia CPI inflation (October): CPI m/m 0.5% vs 0.4% forecast (previous 0.8%): above forecast" in io.sent[0]
    assert [c for c in io.fx_calls if c[0] == "australia"] == [("australia", date(2026, 11, 10))]   # the watch reused it
    assert io.watch[(WED, "AU_CPI", "australian_dollar")]["series"][0]["actual"] == "0.5%"


def test_a_refused_country_page_never_blocks_the_alert():
    class Refuse(FakeIo):
        def fxempire(self, country, d0, d1):
            if country == "australia":
                self.fx_calls.append((country, d0))
                raise cf.CalendarRefused("429")
            return super().fxempire(country, d0, d1)
    io = _au_io()
    io.__class__ = Refuse
    res = _run(cf.run_daily(WED, io, AFTER_CLOSE))
    assert res["alerts"] == 1 and res["sent"] is True and res["problems"] == []
    assert "fxempire australia" in res["label_errors"]
    item = io.alerts[(WED, "australian_dollar", "long", "news")]["detail"]["news"][0]
    assert item["series"] == [] and item["text"] == ("Australia CPI inflation → no bullish / bearish read is mapped for this "
                                                     "release on Australian Dollar")
    assert len([c for c in io.fx_calls if c[0] == "australia"]) == 1            # a refusal is not asked again


def test_an_item_stored_before_the_plain_words_still_renders():
    old = {"event": "GDP", "class": "WITH", "z": 2.95, "first_minute": {"status": "ok", "move": 0.2, "big": False}}
    assert cf.news_line(old, "silver", "long") == "US GDP → bearish Silver"
    assert cf.news_line(old, "silver") == "US GDP → no clear read"           # no direction: never a guessed read
    msg = cf.format_daily_message(WED, REPORT, [_alert(market="silver", direction="long", z=0.5, kinds=["news"], events=["GDP"],
                                                       news_text=[], news_detail=[old])])
    assert "a news failure: bearish news for Silver (US GDP), yet Silver closed UP." in msg


def test_a_heavy_news_day_still_goes_out_in_whole_blocks(monkeypatch):
    """The nine news alerts of 11-25 with the longer lines, through the REAL sender: every chunk fits Telegram and keeps
    its code block."""
    from unittest.mock import AsyncMock
    from agents.market_intelligence import briefing
    from tests.test_699_paper_chat_routing import MAIN, PAPER, _Router
    monkeypatch.undo()
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "tok")
    monkeypatch.setenv("TELEGRAM_ALLOWED_USER_IDS", str(MAIN))
    monkeypatch.setenv("TELEGRAM_PAPER_CHAT_ID", str(PAPER))
    r = _Router()
    monkeypatch.setattr(briefing.httpx, "AsyncClient", r)
    monkeypatch.setattr(briefing, "log_audit_event", AsyncMock())
    alerts = []
    for m in ("silver", "platinum", "notes_10y", "new_zealand_dollar", "gold", "euro", "copper"):
        items = [_item_1125(e, m) for e in ("GDP", "PCE")]
        alerts.append(_alert(market=m, direction="long", z=0.5, kinds=["news"], events=["GDP", "PCE"], news_class="WITH",
                             news_text=[i["text"] for i in items], news_detail=items))
    for m in ("natural_gas", "crude_oil"):
        alerts.append(_alert(market=m, direction="long", z=0.5, kinds=["news"], events=["EIA_PETRO"], news_text=["x" * 200]))
    text = cf.format_daily_message(D1125, REPORT, alerts)
    assert len(text) > 4000                                                   # it does need splitting
    assert _run(cf._send(text)) is True
    assert len(r.posts) >= 2
    for p in r.posts:
        assert len(p["text"]) <= 4096 and p["text"].count("<pre>") == p["text"].count("</pre>") >= 1


def test_the_export_mirrors_the_why_table():
    """scripts/export_cot_snapshot.sql gives OLD alerts the same words: its VALUES lists equal the tables here."""
    sql = (REPO / "scripts" / "export_cot_snapshot.sql").read_text()

    def block(head):
        return sql.split(head, 1)[1].split("\n),", 1)[0]

    def lit(x):
        return None if x == "NULL" else int(x) if re.fullmatch(r"-?\d+", x) else x[1:-1].replace("''", "'")

    def rows(head):
        return [[lit(v) for v in re.findall(r"NULL|-?\d+(?=[,)])|'(?:[^']|'')*'", r)]
                for r in re.findall(r"^\s+\((.*)\),?$", block(head), re.M)]
    nd = {r[0]: r[1:] for r in rows("newsdef(event_type, country, release, family, cause_up, cause_down) AS (")}
    assert nd == {et: [who, what, cf.WHY_FAMILY.get(et), *cf.WHY_CAUSE.get(et, (None, None))]
                  for et, (who, what) in cf.RELEASE_NAMES.items()}
    assert {r[0]: r[1] for r in rows("whygrp(market, grp) AS (")} == cf.WHY_GROUP
    assert {(r[0], r[1]): tuple(r[2:]) for r in rows("whydef(family, grp, sign, effect_up, effect_down) AS (")} == cf.WHY
