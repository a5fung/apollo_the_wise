"""#732 — the liquidity block beside market breadth (agents/market_intelligence/liquidity_read.py). Offline.

1. REPRODUCTION: the production code, run the reference script's way (no publication lag), gives the numbers the
   11-22 reference read printed for 2026-11-20 (scripts/probes/_liquidity_1122/current_read_2026-11-22.txt) on the
   same inputs (tests/fixtures/liquidity_1122/ = the reference's own input files, closes only). The two places the
   production rule departs from the reference script are pinned by name, not hidden.
2. PRODUCTION mode (the prereg's publication lags): what moves, and that today's read does not.
3. The rules one at a time: lags + freshness, the turn rule, the caution state.
4. FAIL-SAFE: a failed or stale source = that leg "unavailable"; no source at all = an "unavailable" block; the
   command exits non-zero with EMPTY stdout. (That the breadth FILE still ships is tested by behaviour on the real
   shell script: tests/test_719_export_breadth_sql.py, "#732: the liquidity block's splice".)
5. DISPLAY ONLY: nothing imports this module (derived by walking the repo, never hand-listed).
"""
from __future__ import annotations

import ast
import asyncio
import json
import re
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import pytest

from agents.market_intelligence import liquidity_read as L

REPO = Path(__file__).resolve().parents[1]
FIX = REPO / "tests" / "fixtures" / "liquidity_1122"
REF = REPO / "scripts" / "probes" / "_liquidity_1122" / "current_read_2026-11-22.txt"
ET = ZoneInfo("America/New_York")


def _inputs(**drop) -> L.Inputs:
    adj = pd.read_csv(FIX / "etf_closes_all.csv", index_col=0, parse_dates=True)
    raw = pd.read_csv(FIX / "etf_closes_raw.csv", index_col=0, parse_dates=True)
    fred = {i: L.parse_fred_csv((FIX / f"{i}.csv").read_text()) for i in L.FRED_IDS}
    for t in drop.get("tickers", ()):
        adj = adj.drop(columns=t)
    for s in drop.get("fred", ()):
        fred.pop(s)
    return L.Inputs(adj=adj, raw=raw, fred=fred)


@pytest.fixture(scope="module")
def ref_text() -> str:
    return REF.read_text()


@pytest.fixture(scope="module")
def ref_block():
    return L.build_block(_inputs(), lags=L.NO_LAGS)


@pytest.fixture(scope="module")
def ref_series():
    return L.compute(_inputs(), L.NO_LAGS)


@pytest.fixture(scope="module")
def prod_block():
    return L.build_block(_inputs(), generated_at=datetime(2026, 11, 20, 18, 30, tzinfo=ET))


# reference row label -> leg id (the reference prints its own short names)
REF_ROWS = {"C3 Baa spread": "C3", "F1 net liquidity": "F1", "F2 funds rate": "F2", "R1 10y real yield": "R1",
            "R2 2y yield": "R2", "D1 dollar (UUP)": "D1", "M1 gold/silver": "M1", "M2 copper/gold": "M2",
            "K1 small/large": "K1", "K5 spec growth": "K5"}


def _ref_legs(text: str) -> dict[str, tuple[str, str, int, str]]:
    out = {}
    for label, lid in REF_ROWS.items():
        m = re.search(re.escape(label) + r"\s+(TIGHT|easy|flat)\s+since (\d{4}-\d\d-\d\d) \(\s*(\d+)\)\s+(\w+)", text)
        assert m, f"reference row not found: {label}"
        out[lid] = (m.group(1).lower(), m.group(2), int(m.group(3)), m.group(4))
    return out


# ───────────────────────────────────────────────────────────────── 1. reproduction of the 11-20 reference read
def test_reference_is_as_of_the_fixture_last_session(ref_text, ref_block):
    assert "AS OF 2026-11-20" in ref_text
    assert ref_block["as_of"] == "2026-11-20" and ref_block["status"] == "ok" and ref_block["unavailable"] == []


@pytest.mark.parametrize("lid", L.LEG_IDS)
def test_every_leg_row_matches_the_reference(lid, ref_text, ref_block):
    trend, since, n, fast = _ref_legs(ref_text)[lid]
    leg = next(l for l in ref_block["legs"] if l["id"] == lid)
    assert (leg["trend"], leg["trend_since"], leg["trend_sessions"], leg["fast"]) == (trend, since, n, fast)


def test_group_count_and_score_match_the_reference(ref_text, ref_block):
    m = re.search(r"GROUPS TIGHT \(channel score > 0\): (\d) of (\d); score S = ([+-][\d.]+)", ref_text)
    assert (ref_block["groups_tight"]["n"], ref_block["groups_tight"]["of"]) == (int(m.group(1)), int(m.group(2)))
    assert ref_block["score"] == float(m.group(3))
    assert sum(g["tight"] for g in ref_block["groups"]) == int(m.group(1))


def test_caution_and_composite_trend_match_the_reference(ref_text, ref_block):
    m = re.search(r"composite state .*: (\w+) since (\d{4}-\d\d-\d\d)", ref_text)
    assert m.group(1) == "Draining"
    c = ref_block["caution"]
    assert c["on"] is True and c["since"] == m.group(2) and c["text"] == "Caution — liquidity draining"
    m = re.search(r"composite trend \(20d vs 50d of S\): (\w+) since (\d{4}-\d\d-\d\d)", ref_text)
    assert (ref_block["composite_trend"]["direction"], ref_block["composite_trend"]["since"]) == (m.group(1), m.group(2))


# The reference script left Draining / Easing on ONE close back inside the exit line; the rule run 2 judged (prereg
# §4.3, scripts/probes/_liquidity_1122/r2_03_composite_w0_w1.py) needs THREE closes. Production ships the judged rule.
# These are the only month-end rows where the two differ on the reference inputs.
STATE_DEPARTURES = {"2026-05-29": ("Neutral", "E"), "2026-09-30": ("Neutral", "D")}


def test_month_end_history_matches_the_reference(ref_text, ref_series):
    rows = re.findall(r"^\s+(\d{4}-\d\d-\d\d)\s+S ([+-][\d.]+)\s+(\w+)(?:\s+groups tight (\d))?", ref_text, re.M)
    assert len(rows) == 16
    word = {"Draining": "D", "Neutral": "N", "Easing": "E"}
    seen = {}
    for d, s, state, nt in rows:
        ts = pd.Timestamp(d)
        assert round(float(ref_series.S[ts]), 1) == float(s), d
        if nt:
            assert int(ref_series.n_tight[ts]) == int(nt), d
        if ref_series.state[ts] != word[state]:
            seen[d] = (state, ref_series.state[ts])
    assert seen == STATE_DEPARTURES


def test_seed_tiles_hy_spread_and_net_liquidity_match_the_reference(ref_text, ref_block):
    m = re.search(r"SEED JNK .*: ([\d.]+)  vs 20d ([\d.]+)  vs 50d ([\d.]+)  20d slope ([+-][\d.]+)/wk  "
                  r"1-month change ([+-][\d.]+)%", ref_text)
    j = ref_block["seeds"]["jnk"]
    assert [j["latest"], j["ma20"], j["ma50"], j["ma20_slope_wk"], j["chg_1m_pct"]] == [float(x) for x in m.groups()]
    assert (j["vs_ma20"], j["vs_ma50"], j["ma20_vs_ma50"]) == ("below", "below", "below")
    m = re.search(r"SEED gold/silver .*: ([\d.]+)  vs 20d ([\d.]+)  vs 50d ([\d.]+)  1-month change ([+-][\d.]+)%",
                  ref_text)
    g = ref_block["seeds"]["gold_silver"]
    assert [g["latest"], g["ma20"], g["ma50"], g["chg_1m_pct"]] == [float(x) for x in m.groups()]
    m = re.search(r"HY spread: ([\d.]+)%  1 month ago ([\d.]+)%  3 months ago ([\d.]+)%", ref_text)
    h = ref_block["hy_spread"]
    assert [h["latest"], h["month_ago"], h["three_months_ago"]] == [float(x) for x in m.groups()]
    m = re.search(r"Net liquidity: \$([\d.]+)T  3 months ago \$([\d.]+)T", ref_text)
    nl = ref_block["net_liquidity_tn"]
    assert [nl["latest"], nl["three_months_ago"]] == [float(x) for x in m.groups()]


# ───────────────────────────────────────────────────────────────── 2. production mode (publication lags applied)
def test_lags_leave_the_market_price_legs_and_todays_read_unchanged(ref_block, prod_block):
    for lid in ("D1", "M1", "M2", "K1", "K5"):          # Alpaca legs: same day, no lag
        a, b = (next(l for l in blk["legs"] if l["id"] == lid) for blk in (ref_block, prod_block))
        assert a == b
    for key in ("as_of", "groups", "score", "caution", "seeds", "net_liquidity_tn", "status"):
        assert prod_block[key] == ref_block[key], key
    assert prod_block["groups_tight"] == {"n": 3, "of": 6, "n_20d_ago": 3, "chg_20d": 0}
    assert [(l["id"], l["trend"]) for l in prod_block["legs"]] == [(l["id"], l["trend"]) for l in ref_block["legs"]]


def test_lags_move_the_fed_series_legs_to_the_session_the_value_was_published(prod_block):
    """A Treasury / Fed value is known the NEXT session, so those legs change side one session later than in the
    reference read; net liquidity (Wednesday level usable Friday) two sessions later on this change."""
    got = {l["id"]: (l["trend"], l["trend_since"], l["trend_sessions"]) for l in prod_block["legs"]}
    assert got["C3"] == ("tight", "2026-11-10", 8)
    assert got["F1"] == ("tight", "2026-11-10", 8)
    assert got["F2"] == ("tight", "2026-07-10", 94)
    assert got["R1"] == ("easy", "2026-11-10", 8)
    assert got["R2"] == ("easy", "2026-11-10", 8)
    assert prod_block["composite_trend"] == {"direction": "tightening", "since": "2026-11-03", "sessions": 13}
    assert prod_block["hy_spread"] == {"latest": 3.52, "obs_date": "2026-11-19", "month_ago": 3.27, "chg_1m": 0.25,
                                       "three_months_ago": prod_block["hy_spread"]["three_months_ago"]}


def test_leg_turns_and_composite_turn_markers(prod_block):
    turn = {l["id"]: l["turn"] for l in prod_block["legs"]}
    # K1 changed side on 11-16 and 11-20 is its 5th session there: the turn is confirmed today, dated today
    assert turn["K1"] == {"date": "2026-11-20", "to": "easy", "sessions": 0}
    assert turn["D1"] == {"date": "2026-09-30", "to": "tight", "sessions": 37}
    # C3 changed side 11-10: confirmed on its 5th session, 11-16
    assert turn["C3"] == {"date": "2026-11-16", "to": "tight", "sessions": 4}
    assert prod_block["composite_turns"] == [
        {"date": "2026-06-25", "to": "tightening", "sessions": 104},
        {"date": "2026-09-23", "to": "easing", "sessions": 42},
        {"date": "2026-11-09", "to": "tightening", "sessions": 9}]
    lo = pd.Timestamp(prod_block["as_of"]) - pd.Timedelta(days=200)
    assert all(pd.Timestamp(t["date"]) > lo for t in prod_block["composite_turns"])


def test_three_legs_and_the_count_recomputed_independently():
    """A second route (pandas rolling means on the fixture, no production helper) for 3 legs + the count."""
    adj = pd.read_csv(FIX / "etf_closes_all.csv", index_col=0, parse_dates=True)
    b = L.build_block(_inputs())
    for lid, x in (("D1", adj["UUP"]), ("M1", adj["GLD"] / adj["SLV"]), ("K5", -(adj["ARKK"] / adj["QQQ"]))):
        sg = np.sign(x.rolling(20).mean() - x.rolling(50).mean()).dropna()
        first = sg[sg != sg.shift()].index[-1]
        leg = next(l for l in b["legs"] if l["id"] == lid)
        assert leg["trend"] == {1: "tight", -1: "easy"}[int(sg.iloc[-1])]
        assert leg["trend_since"] == first.date().isoformat()
        assert leg["trend_sessions"] == int((sg.index > first).sum())
    score = {g["key"]: g["score"] for g in b["groups"]}
    votes = {l["id"]: {"tight": 1, "easy": -1, "flat": 0}[l["trend"]] for l in b["legs"]}
    for g, _ in L.GROUPS:
        mine = [votes[l[0]] for l in L.LEGS if l[2] == g]
        assert score[g] == round(sum(mine) / len(mine), 2)
    assert b["groups_tight"]["n"] == sum(v > 0 for v in score.values()) == 3
    assert b["score"] == sum(score.values())


def test_the_block_is_labelled_and_carries_no_state_word(prod_block):
    assert prod_block["label"] == "context, not validated"
    text = json.dumps(prod_block)
    for banned in ("Neutral", "Easing", "neutral", '"state"', "bottom", "Bottom", '"top"', "early marker"):
        assert banned not in text, banned
    assert "state" not in prod_block and all("state" not in l for l in prod_block["legs"])
    assert prod_block["caution"]["history"] == L.CAUTION_HISTORY and "33% of 730" in L.CAUTION_HISTORY
    assert prod_block["generated_at"] == "2026-11-20T18:30:00 ET"
    json.dumps(prod_block, allow_nan=False)
    assert len(text) < 12_000


def test_no_caution_when_the_composite_is_not_draining():
    inp = _inputs()
    cut = pd.Timestamp("2026-06-30")          # the reference's month-end row: S +0.0, not draining
    inp.adj, inp.raw = inp.adj[inp.adj.index <= cut], inp.raw[inp.raw.index <= cut]
    inp.fred = {k: v[v.index <= cut] for k, v in inp.fred.items()}
    b = L.build_block(inp)
    assert b["as_of"] == "2026-06-30" and b["caution"] == {"on": False}
    assert "Caution" not in json.dumps({k: v for k, v in b.items() if k != "definitions"})


def test_history_start_is_fixed_not_rolling():
    assert L.HISTORY_START == date(2025, 6, 2)
    assert L.build_block(_inputs())["history_start"] == "2025-06-02"


# ───────────────────────────────────────────────────────────────── 3. the rules one at a time
def _grid(*days):
    return pd.DatetimeIndex([pd.Timestamp(d) for d in days])


def test_a_daily_fed_series_is_usable_only_the_next_session():
    s = pd.Series([1.0, 2.0, 3.0], index=pd.to_datetime(["2026-11-17", "2026-11-18", "2026-11-19"]))
    g = _grid("2026-11-18", "2026-11-19", "2026-11-20", "2026-11-23")
    val, fresh, obs = L.fred_on_grid(s, g, *L.PREREG_LAGS["DGS2"])
    assert list(val) == [1.0, 2.0, 3.0, 3.0] and fresh.all()
    assert pd.Timestamp(obs[-1]) == pd.Timestamp("2026-11-19")
    val, _, _ = L.fred_on_grid(s, g, *L.PREREG_LAGS["RRPONTSYD"])          # same day
    assert list(val) == [2.0, 3.0, 3.0, 3.0]


def test_the_fed_balance_sheet_wednesday_level_is_usable_on_friday():
    s = pd.Series([10.0, 20.0], index=pd.to_datetime(["2026-11-11", "2026-11-18"]))      # Wednesdays
    g = _grid("2026-11-18", "2026-11-19", "2026-11-20")
    val, fresh, _ = L.fred_on_grid(s, g, *L.PREREG_LAGS["WALCL"])
    assert list(val) == [10.0, 10.0, 20.0] and fresh.all()


def test_a_value_older_than_the_freshness_limit_is_stale():
    s = pd.Series([1.0], index=pd.to_datetime(["2026-11-10"]))
    g = _grid("2026-11-17", "2026-11-18")
    _, fresh, _ = L.fred_on_grid(s, g, *L.PREREG_LAGS["DFF"])               # 7 calendar days
    assert list(fresh) == [True, False]
    _, fresh, _ = L.fred_on_grid(s, _grid("2026-11-24", "2026-11-25"), *L.PREREG_LAGS["WALCL"])   # 14
    assert list(fresh) == [True, False]


def test_turn_rule_needs_five_sessions_and_ties_carry():
    nan = float("nan")
    s = np.array([1] * 5 + [-1] * 4 + [1] * 3 + [-1, -1, 0, nan, -1, -1], float)
    #            start=+1    4 only: no turn        -1 held 5 counting the carried tie and gap -> turn at the 5th
    tl, conf = L.turns(s)
    assert tl == [(16, -1)] and conf == -1
    assert L.turns(np.array([1, 1, 1, 1, 1, 1, 1], float)) == ([], 1)        # a starting direction is not a turn
    assert L.turns(np.array([nan, 0, nan])) == ([], None)


def test_draining_needs_three_closes_in_and_three_closes_out():
    S = np.array([0, 2, 2, 1.5, 2, 2, 2, 1, 1.5, 1, 1, 2, 1, 1, 1], float)
    st = "".join(L.draining_series(S))
    #            0  2  2  1.5 2  2  2  1  1.5 1  1  2  1  1  1
    assert st == "NNNNNNDDDDDDDDN"[:len(S)]
    assert "".join(L.draining_series(np.array([-2, -2, -2, 2, 2, 2], float))) == "NNEEED"   # a direct flip
    assert list(L.draining_series(np.array([np.nan, np.nan, 2, 2, 2], float))) == ["", "", "N", "N", "D"]


def test_exact_tie_is_flat_not_a_side():
    a = np.full(60, 3.88)
    assert list(L._side(L._ma(a, 20), L._ma(a, 50))[49:]) == [0.0] * 11
    assert np.isnan(L._side(L._ma(a, 20), L._ma(a, 50))[:49]).all()


# ───────────────────────────────────────────────────────────────── 4. fail-safe
def test_a_failed_fred_series_marks_only_its_leg_unavailable():
    b = L.build_block(_inputs(fred=("DFII10",)))
    assert b["status"] == "partial" and b["unavailable"] == ["R1"]
    r1 = next(l for l in b["legs"] if l["id"] == "R1")
    assert r1 == {"id": "R1", "name": "10-year real yield", "group": "rates", "tight_when": "real yield rising",
                  "status": "unavailable", "reason": "source failed: DFII10"}
    assert sum(l["status"] == "ok" for l in b["legs"]) == 9
    # the missing leg votes 0 and STAYS in its group's mean (never re-weighted over the legs present): R2 easy -> -0.5
    assert next(g for g in b["groups"] if g["key"] == "rates")["score"] == -0.5
    json.dumps(b, allow_nan=False)


def test_one_part_of_net_liquidity_missing_makes_the_leg_unavailable():
    b = L.build_block(_inputs(fred=("WTREGEN",)))
    assert b["unavailable"] == ["F1"] and b["net_liquidity_tn"] is None


def test_a_missing_ticker_marks_every_leg_that_needs_it():
    b = L.build_block(_inputs(tickers=("GLD",)))
    assert b["unavailable"] == ["M1", "M2"]
    assert all("GLD" in l["reason"] for l in b["legs"] if l["id"] in ("M1", "M2"))
    assert b["seeds"]["jnk"] is not None            # the raw-price tiles come from their own fetch


def test_a_stale_source_is_unavailable_not_shown_as_current():
    inp = _inputs()
    inp.fred["DGS2"] = inp.fred["DGS2"][inp.fred["DGS2"].index <= pd.Timestamp("2026-11-05")]
    b = L.build_block(inp)
    assert b["unavailable"] == ["R2"]
    assert next(l for l in b["legs"] if l["id"] == "R2")["reason"].startswith("stale")


def test_the_hy_spread_and_seed_tiles_fail_on_their_own():
    inp = _inputs(fred=("BAMLH0A0HYM2",))
    inp.raw = None
    b = L.build_block(inp)
    assert b["hy_spread"] is None and b["seeds"] == {"jnk": None, "gold_silver": None}
    assert b["status"] == "ok" and b["groups_tight"]["n"] == 3      # no voting leg was touched


def test_no_bars_at_all_is_an_unavailable_block_not_an_exception():
    b = L.build_block(L.Inputs(adj=None, raw=None, fred={}, errors={"alpaca_adj": "Alpaca returned no daily bars"}))
    assert b["status"] == "unavailable" and "legs" not in b and b["label"] == "context, not validated"
    assert L.build_block(L.Inputs(adj=pd.DataFrame(), raw=None))["status"] == "unavailable"


def test_everything_from_fred_failing_still_builds_a_block():
    inp = _inputs(fred=L.FRED_IDS)
    b = L.build_block(inp)
    assert b["unavailable"] == ["C3", "F1", "F2", "R1", "R2"] and b["hy_spread"] is None
    assert b["groups_tight"]["of"] == 6


def test_collect_inputs_records_each_failed_source_and_never_raises(monkeypatch):
    import httpx

    async def no_bars(tickers, start, end, adjustment="all", **_):
        if adjustment == "raw":
            raise RuntimeError("boom")
        assert start.tzinfo is not None and end.tzinfo is not None
        return {"SPY": [(date(2026, 11, 19), 1.0), (date(2026, 11, 20), 2.0)]}

    class FakeClient:
        def __init__(self, *a, **k): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def get(self, url, params=None):
            if params["id"] == "DFF":
                return httpx.Response(200, text="observation_date,DFF\n2026-11-19,3.88\n",
                                      request=httpx.Request("GET", url))
            raise httpx.ConnectError("no network in tests")

    monkeypatch.setattr(L, "fetch_daily_closes", no_bars)
    monkeypatch.setattr(httpx, "AsyncClient", FakeClient)
    inp = asyncio.run(L.collect_inputs(datetime(2026, 11, 20, 18, 30, tzinfo=ET)))
    assert list(inp.adj.columns) == ["SPY"] and len(inp.adj) == 2 and inp.raw is None
    assert list(inp.fred) == ["DFF"]
    assert "alpaca_raw" in inp.errors and "fred_BAA10Y" in inp.errors and "fred_DFF" not in inp.errors
    b = L.build_block(inp)                                   # two sessions of one ticker: still a block, no crash
    assert b["status"] == "partial" and len(b["unavailable"]) == 10 and b["caution"] is None


def test_the_command_fails_closed_with_empty_stdout():
    async def boom(now_et):
        raise RuntimeError("alpaca down")

    code, out, err = L.run_cli(["--splice"], '{"version": 1}\n', collect=boom)
    assert code == 1 and out == "" and "FAILED" in err
    for bad in ("", "not json", "[1, 2]", '{"liquidity": {}}'):
        async def ok(now_et):
            return _inputs()
        code, out, _ = L.run_cli(["--splice"], bad, collect=ok)
        assert code == 1 and out == "", bad


def test_the_command_splices_the_block_without_touching_the_breadth_bytes():
    async def ok(now_et):
        assert now_et.tzinfo is not None
        return _inputs()

    breadth = '{"version": 1, "as_of": "2026-11-20",  "odd  spacing": [1,2,  3], "definitions": {"a": "é"}}\n'
    code, out, err = L.run_cli(["--splice"], breadth, collect=ok)
    assert code == 0 and err == ""
    assert out.startswith(breadth.rstrip()[:-1]) and out.endswith("}\n")
    doc = json.loads(out)
    assert list(doc)[-1] == "liquidity" and doc["liquidity"]["groups_tight"]["n"] == 3
    assert {k: v for k, v in doc.items() if k != "liquidity"} == json.loads(breadth)
    assert doc["liquidity"]["generated_at"].endswith(" ET")


def test_todays_unfinished_bar_is_dropped_before_the_close():
    df = pd.DataFrame({"SPY": [1.0, 2.0]}, index=pd.to_datetime(["2026-11-19", "2026-11-20"]))
    assert len(L.drop_unfinished_session(df, datetime(2026, 11, 20, 13, 0, tzinfo=ET))) == 1
    assert len(L.drop_unfinished_session(df, datetime(2026, 11, 20, 18, 30, tzinfo=ET))) == 2
    assert len(L.drop_unfinished_session(df, datetime(2026, 11, 21, 9, 0, tzinfo=ET))) == 2


def test_the_bar_reader_returns_nothing_without_credentials(monkeypatch):
    for k in ("ALPACA_PAPER_API_KEY", "ALPACA_API_KEY", "ALPACA_PAPER_SECRET_KEY", "ALPACA_SECRET_KEY"):
        monkeypatch.delenv(k, raising=False)
    s = datetime(2025, 6, 2, tzinfo=ET)
    assert asyncio.run(L.fetch_daily_closes(["SPY"], s, s)) == {}
    assert asyncio.run(L.fetch_daily_closes([], s, s)) == {}


# ───────────────────────────────────────────────────────────────── 5. display only: nothing imports it
_SKIP_DIRS = {".git", ".claude", "node_modules", "__pycache__", ".venv", "venv", "tests"}
ALLOWED_IMPORTERS: set[str] = set()      # the nightly export runs it as `python -m`; no Python module may import it
ALLOWED_MENTIONS = {"agents/market_intelligence/liquidity_read.py"}


def _py_files():
    for p in REPO.rglob("*.py"):
        rel = p.relative_to(REPO)
        if not _SKIP_DIRS.intersection(rel.parts):
            yield rel.as_posix(), p


def test_no_module_imports_the_liquidity_read():
    """Display only (THE LINE): the population is DERIVED — every .py in the repo outside tests/ — and the importers
    found must equal the allowlist. A textual sweep backs the AST walk so an importlib / string import is seen too."""
    importers, mentions, n = set(), set(), 0
    for rel, p in _py_files():
        n += 1
        src = p.read_text(errors="replace")
        if "liquidity_read" not in src:
            continue
        mentions.add(rel)
        for node in ast.walk(ast.parse(src)):
            names = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [f"{node.module or ''}.{a.name}" for a in node.names] + [node.module or ""]
            if any("liquidity_read" in x for x in names):
                importers.add(rel)
    assert n > 300 and "agents/market_intelligence/collector.py" in dict(_py_files())    # the walk saw the repo
    assert "agents/market_intelligence/liquidity_read.py" in mentions                    # ... and can see the name
    assert importers == ALLOWED_IMPORTERS
    assert mentions == ALLOWED_MENTIONS, f"new mention(s) of liquidity_read: {sorted(mentions - ALLOWED_MENTIONS)}"


def test_importing_the_module_loads_no_other_apollo_module():
    """Behaviour, in a fresh interpreter: the display read pulls in no trade, broker, regime or scheduler code."""
    import subprocess
    import sys
    code = ("import sys, agents.market_intelligence.liquidity_read\n"
            "print(sorted(m for m in sys.modules if m.split('.')[0] in "
            "('agents', 'core', 'shared', 'channels', 'broker')))")
    r = subprocess.run([sys.executable, "-c", code], cwd=REPO, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == str(["agents", "agents.market_intelligence",
                                    "agents.market_intelligence.liquidity_read"])


def test_the_deploy_stays_market_agent_only():
    """collector.py is loaded by the execution service; this feature must not need that service redeployed."""
    loaded = (REPO / "scripts" / "exec_loaded_modules.txt").read_text().split()
    assert "agents/market_intelligence/collector.py" in loaded          # why the reader is not in the collector
    assert "agents/market_intelligence/liquidity_read.py" not in loaded
