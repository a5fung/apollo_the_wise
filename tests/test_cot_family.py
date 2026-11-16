"""COT family live alerts (2026-11-15): the index against known values, the set-up rule, no look-ahead, feed A on
synthetic bars, the Friday confirmation, the two labels, the forward calendar, the messages, the two jobs (silence,
isolation, all-fail, one message per week), registration and the DDL. No network, no database.

The index fixtures are NUMBERS ONLY: CFTC public nets for four short-lookback markets and the index values our
research workspace holds for the same report (2026-11-03)."""
import asyncio
import re
from datetime import date, datetime, timedelta
from pathlib import Path

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
    assert not ({"PCE", "ISM_MFG", "ISM_SERV"} & set(cf.EVENT_MARKETS))   # never N1 triggers in the research


# ── the set-up rule ──────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("market,ix,want", [
    ("gold", (5, 95, 95), ("short", None)),
    ("gold", (95, 5, 5), ("long", None)),
    ("gold", (5, 95, 94), (None, "short")),          # one speculator group short of 95 -> the close list
    ("gold", (6, 99, 99), (None, "short")),
    ("gold", (10, 85, 85), (None, "short")),
    ("gold", (11, 99, 99), (None, None)),
    ("gold", (90, 15, 15), (None, "long")),
    ("gold", (90, 16, 15), (None, None)),
    ("gold", (0, 100, 50), (None, None)),            # Commercials alone are not enough outside stock indices
    ("nasdaq", (5, 10, 10), ("short", None)),        # stock indices: Commercials alone
    ("nasdaq", (95, 99, 99), ("long", None)),
    ("nasdaq", (6, 84, 76), (None, "short")),
    ("nasdaq", (50, 99, 99), (None, None)),
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
          _fx("PCE Price Index MoM", None, "0.2%"), _fx("ISM Manufacturing PMI", None, "50")]
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
         "news_text": ["CPI: Inflation Rate MoM 0.4% vs 0.2% -> with the crowd"]}
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
    assert "first minute: 0.31 of a day's range the crowd's way (big)" in text
    assert "first minute: 0.54 of a day's range AGAINST the crowd" in cf.format_daily_message(
        WED, REPORT, [_alert(first_minute={"status": "ok", "move": -0.54, "big": False})])
    assert "news vs consensus: with the crowd" in text and "main set up, C  3 L 97 S 96" in text
    assert "close-list set up" in cf.format_daily_message(WED, REPORT, [_alert(level="close")])
    outside = re.sub(r"```.*?```", "", text, flags=re.S)
    assert "_" not in outside                              # a bare underscore outside the block breaks Telegram Markdown
    unread = cf.format_daily_message(WED, REPORT, [_alert(first_minute={"status": "no minute bars"}, news_class="UNKNOWN", news_text=[])])
    assert "first minute: unknown (no minute bars)" in unread and "news vs consensus: unknown" in unread


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
    assert "CLOSE TO A SET UP (approximate rule)" in text and re.search(r"NASDAQ\s+short C  6 L 84 S 76", text)
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
        return list(self.fx) if country == "united-states" else []

    def wasde_dates(self):
        return [date(2026, 12, 10)]

    def earnings(self, ticker):
        return []

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
    assert "GOLD SHORT  news (CPI)" in io.sent[0] and "against the crowd" in io.sent[0]
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
    res = _run(cf.run_daily(WED, io, AFTER_CLOSE))             # no raise: crude was read
    assert set(res["errors"]) == {"gold"} and {k[1] for k in io.alerts} == {"crude_oil"} and len(io.sent) == 1


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
    res = _run(cf.run_daily(late, io, datetime(2026, 11, 23, 17, 15, tzinfo=_ET)))
    assert "too old" in res["status"] and io.sent == [] and io.alerts == {} and len(io.audits) == 1


def test_a_blind_calendar_pages_after_the_alerts():
    io = _daily_io()
    io.cal_age = 9
    io.fx_exc = cf.CalendarRefused("fxempire calendar refused the request (429)")
    with pytest.raises(cf.CotError, match="US calendar could not be read"):
        _run(cf.run_daily(WED, io, AFTER_CLOSE))
    assert len(io.sent) == 1 and len(io.audits) == 1            # the stored calendar still produced today's alert
    assert "news vs consensus: unknown" in io.sent[0] and io.audits[0][2]["label_errors"]["consensus"]
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
    assert res["alerts"] == 1 and "calendar" not in res and io.fx_calls == [("united-states", date(2026, 11, 9))]
    assert {(r["event_date"], r["event_type"]) for r in io.cal} == {(WED, "CPI"), (date(2026, 11, 10), "WASDE")}
    io = _daily_io()
    io.cal_age = 8
    res = _run(cf.run_daily(WED, io, AFTER_CLOSE))
    assert res["calendar"]["errors"] == {} and len(io.fx_calls) == 1 + 3 + 6      # this week, 3 more, 6 central banks
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
    io.bars = {"ZW=F": wheat, "ZS=F": bars_to(FRI, 100.0), "ZM=F": bars_to(FRI, 100.0), "ZC=F": bars_to(FRI, 100.0)}
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
    # the retry slot: nothing new, no second message, an audit row all the same
    res = _run(cf.run_weekly(FRI, io))
    assert res["status"] == "no new report" and len(io.sent) == 1 and [a[0] for a in io.audits] == ["cot_weekly"] * 2


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
    io.bars = {"ZW=F": wheat, "ZS=F": bars_to(mon, 100.0), "ZM=F": bars_to(mon, 100.0), "ZC=F": bars_to(mon, 100.0)}
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
    io.bars = {"ZW=F": bars_to(mon, 100.0)}
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
    assert {c[1] for c in creates} == {"mi_cot_nets_weekly", "mi_cot_weeks", "mi_cot_index_weekly", "mi_cot_calendar", "mi_cot_alerts"}
    assert all(c[0] for c in creates) and not re.search(r"\bDROP\b|\bTRUNCATE\b|\bALTER\b", ddl)
    for col in ("report_date", "market", "comm", "lspec", "sspec", "setup", "close_setup"):
        assert re.search(rf"mi_cot_index_weekly \((?:.|\n)*?\b{col}\b", ddl)
    assert "UNIQUE (alert_date, market, direction, kind)" in ddl
    # source-pin-ok: that the schema init EXECUTES this DDL is decidable only from its source (the _BREAKOUT_V1_DDL precedent)
    assert "await conn.execute(_COT_FAMILY_DDL)" in (REPO / "agents" / "market_intelligence" / "db.py").read_text()
    for sql in (cf._COT_ALERT_UPSERT_SQL, cf._COT_INDEX_UPSERT_SQL, cf._COT_CALENDAR_UPSERT_SQL, cf._COT_NETS_UPSERT_SQL):
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
