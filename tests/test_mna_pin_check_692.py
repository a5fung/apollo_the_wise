"""#692 — THE PRICE DECIDES (operator 2026-10-03). The news answer NOMINATES a name (target of a
deal, signed OR proposed, on pinning terms); the PRICE decides, read over the detector's own
decision window. His sign-off on the 10-02 replay: release DSGN 05-18 / THR 05-22 / PD 05-29 ("is
not a buyout"), keep HZO 08-10 / RNW 08-11 blocked ("is a real buyout") — *"can't we reuse our
pinned price check? It's clearly pinned to a buyout price"*.

These tests pin:
  1. THE RULE — `deal_nominates` + `pin_verdict` (pure), its three reading states.
  2. THE READINGS — the open window (09:30-09:34, <= 1.0% of the open, >= 4 bars) and the day
     window (own-day range <= 2.0% of close), from bars / rows; the Alpaca reader's states.
  3. EVERY 2026-10-03 CALL as a named regression through the production `is_likely_ma`, driven
     by the recorded answers and the RECORDED price readings (scripts/probes/_692/pin/ exports,
     carried on the harness cases) — plus the three approved rows the price now changes
     (NUVL / MGM / IRDM, agent-read, his to label), the shells (news alone), and the mutation
     guard: with the price condition removed, his five corrections go red.
  4. THE CALLERS — the EP filter holds a nominated name while the window is unreadable, writes
     no `mna_filter_fired` row for a hold, and keeps the reason under the prefix the legacy
     stage classifier maps; the headline path acts on a nomination, not only a signed pin.
Backtest evidence: scripts/probes/_692/pin_backtest.py; SSoT docs/setups/magna53_ep.md 2026-10-03.
"""
from __future__ import annotations

import asyncio
import importlib.util
from datetime import date, datetime
from pathlib import Path
from unittest.mock import AsyncMock, patch
from zoneinfo import ZoneInfo

import pytest

from agents.market_intelligence import ma_filter as mf
from agents.market_intelligence.ma_filter import DealAnswer, PinReading, deal_nominates, pin_verdict

_REPO = Path(__file__).resolve().parents[1]
_ET = ZoneInfo("America/New_York")


def _load_harness():
    spec = importlib.util.spec_from_file_location(
        "mna_harness_692_pin", _REPO / "scripts" / "probes" / "_284_mna_acquirer_backtest.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


H = _load_harness()


def _run(coro):
    return asyncio.run(coro)


def _r(window: str, rng, *, readable=True, why="", n=5) -> PinReading:
    thr = mf.OPEN_WINDOW_PIN_MAX_PCT if window == "open5m" else mf.DAY_WINDOW_PIN_MAX_PCT
    return PinReading(window, rng, thr, n, readable, why, "t")


# ── 1. THE RULE ───────────────────────────────────────────────────────────────────────────────

def test_nomination_is_a_target_signed_or_proposed_on_pinning_terms():
    assert deal_nominates(DealAnswer("target", "signed", "cash")) is True
    assert deal_nominates(DealAnswer("target", "proposed", "unknown")) is True     # HZO / RNW
    assert deal_nominates(DealAnswer("target", "proposed", "cash")) is True        # MGM
    assert deal_nominates(DealAnswer("target", "signed", "stock")) is False        # CSR — floats
    assert deal_nominates(DealAnswer("target", "speculation", "none")) is False    # VKTX / IOVA
    assert deal_nominates(DealAnswer("target", "proposed", "none")) is False       # FRMI
    assert deal_nominates(DealAnswer("buyer", "signed", "cash")) is False          # CHYM
    assert deal_nominates(DealAnswer("shell", "signed", "stock")) is False         # news-only arm
    assert deal_nominates(None) is False


def test_nomination_set_is_exactly_target_x_signed_proposed_x_pinning_terms():
    got = {(r, s, c) for r in mf.DEAL_ROLES for s in mf.DEAL_STATUSES for c in mf.DEAL_CONSIDERATIONS
           if deal_nominates(DealAnswer(r, s, c))}
    assert got == {("target", s, c) for s in ("signed", "proposed") for c in mf._PINNING_CONSIDERATIONS}


def test_verdict_three_reading_states():
    nominated = DealAnswer("target", "proposed", "unknown")
    assert pin_verdict(nominated, None) == (False, "no_price_reading")          # no reader: 10-02 rule
    assert pin_verdict(DealAnswer("target", "signed", "cash"), None) == (True, "no_price_reading")
    assert pin_verdict(nominated, _r("open5m", None, readable=False, why="pre_market", n=0)) == (None, "pin_pending")
    assert pin_verdict(nominated, _r("open5m", 0.15)) == (True, "pinned")
    assert pin_verdict(nominated, _r("open5m", 5.36)) == (False, "pin_free")
    assert pin_verdict(DealAnswer("buyer", "signed", "cash"), _r("open5m", 0.01)) == (False, "not_nominated")


def test_a_signed_shell_blocks_on_the_news_alone_whatever_the_price():
    """Ruling 1 + his SUNE / CLRO rulings + the 10-03 approvals: a reverse-merger shell is
    re-rated, not pinned (SUNE ranged 124%, CLRO 100% on their days)."""
    assert pin_verdict(DealAnswer("shell", "signed", "stock"), _r("day", 123.6)) == (True, "shell_signed")
    assert pin_verdict(DealAnswer("shell", "signed", "unknown"), None) == (True, "shell_signed")
    assert pin_verdict(DealAnswer("shell", "proposed", "stock"), _r("day", 0.1)) == (False, "not_nominated")


def test_the_ceiling_is_inclusive_and_an_unreadable_reading_never_pins():
    assert _r("open5m", mf.OPEN_WINDOW_PIN_MAX_PCT).pinned is True
    assert _r("open5m", mf.OPEN_WINDOW_PIN_MAX_PCT + 1e-6).pinned is False
    assert _r("day", mf.DAY_WINDOW_PIN_MAX_PCT).pinned is True
    assert _r("open5m", 0.0, readable=False, why="bars:2", n=2).pinned is False


def test_the_thresholds_are_the_backtested_ones():
    """pin_backtest.py 2026-10-03: open window — labelled pinned <= 0.74 (RNW), labelled free
    >= 2.65 (IMAX); approved corridor 0.74 <-> 1.24 (MGM). Day window — pinned <= 1.84 (ROKU),
    free >= 2.39 (THR). Changing either is a CHANGE_PROCESS event, not a tweak."""
    assert (mf.OPEN_WINDOW_MINUTES, mf.OPEN_WINDOW_MIN_BARS) == (5, 4)
    assert mf.OPEN_WINDOW_PIN_MAX_PCT == 1.0 and mf.DAY_WINDOW_PIN_MAX_PCT == 2.0


# ── 2. THE READINGS ───────────────────────────────────────────────────────────────────────────

_PD = [(9.33, 9.39, 9.26), (9.29, 9.3171, 9.16), (9.1, 9.25, 8.94), (9.13, 9.33, 9.08), (9.28, 9.44, 9.12)]


def _bars(day: date, ohl, start_minute: int = 30, tz=_ET):
    return [{"ts": datetime(day.year, day.month, day.day, 9, start_minute + i, tzinfo=tz),
             "open": o, "high": h, "low": l, "close": o, "volume": 1}
            for i, (o, h, l) in enumerate(ohl)]


def test_open_window_reads_PD_exactly_as_the_backtest():
    r = mf.open_window_pin_from_bars(_bars(date(2026, 5, 29), _PD), date(2026, 5, 29))
    assert r.readable and r.bars_n == 5 and r.range_pct == pytest.approx(5.3591, abs=1e-3)
    assert r.pinned is False


def test_open_window_keeps_only_the_five_minutes_and_needs_four_bars():
    day = date(2026, 5, 29)
    bars = _bars(day, _PD) + _bars(day, [(20.0, 30.0, 10.0)], start_minute=35)   # 09:35 is outside
    assert mf.open_window_pin_from_bars(bars, day).range_pct == pytest.approx(5.3591, abs=1e-3)
    short = mf.open_window_pin_from_bars(_bars(day, _PD[:3]), day)
    assert not short.readable and short.why == "bars:3" and short.bars_n == 3
    four = mf.open_window_pin_from_bars(_bars(day, _PD[:4]), day)
    assert four.readable and four.bars_n == 4 and four.range_pct == pytest.approx(4.8232, abs=1e-3)


def test_open_window_converts_utc_timestamps_and_rejects_naive_or_bad_bars():
    from datetime import timezone
    day = date(2026, 5, 29)
    utc = _bars(day, _PD, tz=timezone.utc)
    for i, b in enumerate(utc):   # 09:30 ET = 13:30 UTC on 2026-05-29 (EDT)
        b["ts"] = datetime(2026, 5, 29, 13, 30 + i, tzinfo=timezone.utc)
    assert mf.open_window_pin_from_bars(utc, day).readable
    naive = [{**b, "ts": b["ts"].replace(tzinfo=None)} for b in _bars(day, _PD)]
    assert mf.open_window_pin_from_bars(naive, day).why == "bars:0"
    bad = _bars(day, _PD)
    bad[0]["open"] = 0
    assert mf.open_window_pin_from_bars(bad, day).why == "bad_bar"


def test_day_window_reads_both_row_shapes_and_holds_without_the_own_day_bar():
    thr = mf.day_window_pin([{"trade_date": date(2026, 5, 22), "high_price": "10.24",
                              "low_price": "10.0", "close": "10.04"}], date(2026, 5, 22))
    assert thr.readable and thr.range_pct == pytest.approx(2.3904, abs=1e-3) and thr.pinned is False
    roku = mf.day_window_pin([{"date": "2026-06-24", "h": 101.84, "l": 100.0, "c": 100.25}], date(2026, 6, 24))
    assert roku.pinned is True and roku.range_pct == pytest.approx(1.8354, abs=1e-3)
    missing = mf.day_window_pin([{"trade_date": "2026-05-21", "high_price": 1, "low_price": 1, "close": 1}],
                                date(2026, 5, 22))
    assert not missing.readable and missing.why == "no_own_day_bar"


def _fetch(bars_by_ticker):
    return patch("agents.market_intelligence.collector.get_alpaca_minute_bars_window",
                 new=AsyncMock(return_value=bars_by_ticker))


def test_reader_states_pre_market_window_open_readable_memoized():
    mf.reset_headline_day()
    day = date(2026, 5, 29)
    pre = _run(mf.read_open_window_pin("PD", day, datetime(2026, 5, 29, 7, 5, tzinfo=_ET)))
    assert (pre.readable, pre.why) == (False, "pre_market")
    mid = _run(mf.read_open_window_pin("PD", day, datetime(2026, 5, 29, 9, 33, tzinfo=_ET)))
    assert (mid.readable, mid.why) == (False, "window_open")
    with _fetch({"PD": _bars(day, _PD)}) as fetch:
        got = _run(mf.read_open_window_pin("PD", day, datetime(2026, 5, 29, 9, 35, 40, tzinfo=_ET)))
        assert got.readable and got.range_pct == pytest.approx(5.3591, abs=1e-3)
        again = _run(mf.read_open_window_pin("PD", day, datetime(2026, 5, 29, 9, 40, tzinfo=_ET)))
        assert again == got and fetch.await_count == 1, "a readable window is read once per day"
        assert fetch.await_args.args[0] == ["PD"]
        start, end = fetch.await_args.args[1], fetch.await_args.args[2]
        assert (start.hour, start.minute, end.hour, end.minute) == (9, 30, 9, 35)


def test_reader_holds_and_does_not_memoize_on_no_bars_or_a_failed_fetch():
    mf.reset_headline_day()
    day = date(2026, 5, 29)
    at = datetime(2026, 5, 29, 9, 36, tzinfo=_ET)
    with _fetch({}):
        r = _run(mf.read_open_window_pin("PD", day, at))
        assert (r.readable, r.why) == (False, "bars:0")
    with patch("agents.market_intelligence.collector.get_alpaca_minute_bars_window",
               new=AsyncMock(side_effect=RuntimeError("alpaca down"))):
        r = _run(mf.read_open_window_pin("PD", day, at))
        assert (r.readable, r.why) == (False, "fetch_error:RuntimeError")
    assert ("PD", day.isoformat()) not in mf._PIN_MEMO


# ── 3. HIS 2026-10-03 CALLS, through the production function ─────────────────────────────────

def _case(ticker: str):
    case = H.CASES_BY_TICKER[ticker]
    out = _run(H.run_new(case))
    assert not out.unplanned, f"{ticker}: {out.unplanned}"
    return case, out


def _released_on_price(out):
    rows = [a for a in out.audits if a[0] == "mna_filter_released"]
    return rows and "pin_free" in rows[0][2]["old_reasons"] and rows[0][2]["pin_release"]["pin"]["pinned"] is False


def test_PD_2026_05_29_signed_take_private_read_but_the_open_ranged_5pct_is_released():
    case, out = _case("PD")
    assert case.ground_truth and case.expected == "PASS" and out.blocked is False
    assert _released_on_price(out)


def test_DSGN_2026_05_18_agreed_to_acquire_but_the_open_ranged_6pct_is_released():
    case, out = _case("DSGN")
    assert case.ground_truth and out.blocked is False and _released_on_price(out)


def test_THR_2026_05_22_signed_mixed_merger_but_the_day_ranged_2_4pct_is_released():
    case, out = _case("THR")
    assert case.ground_truth and out.blocked is False and _released_on_price(out)
    rel = [a for a in out.audits if a[0] == "mna_filter_released"][0][2]
    assert rel["pin_release"]["pin"]["window"] == "day" and rel["pin_release"]["source"] == "polygon_headline_model"


def test_HZO_2026_08_10_a_proposal_at_a_pinned_price_stays_blocked():
    case, out = _case("HZO")
    assert case.ground_truth and out.blocked is True
    assert out.meta["source"] == "claude_deal_fields" and out.meta["why"] == "pinned"
    assert out.meta["pin"]["pinned"] is True and out.meta["pin"]["range_pct"] == pytest.approx(0.1542)
    assert (out.meta["role"], out.meta["status"]) == ("target", "proposed")


def test_RNW_2026_08_11_a_proposal_at_a_pinned_price_stays_blocked():
    _, out = _case("RNW")
    assert out.blocked is True and out.meta["why"] == "pinned" and out.meta["pin"]["range_pct"] == pytest.approx(0.7396)


def test_ACVA_2026_09_11_signed_cash_at_a_pinned_price_stays_blocked():
    _, out = _case("ACVA")
    assert out.blocked is True and out.meta["why"] == "pinned" and out.meta["pin"]["window"] == "open5m"
    assert out.calls == []


@pytest.mark.parametrize("ticker", ["SUNE", "CLRO"])
def test_the_shells_block_on_the_news_alone(ticker):
    _, out = _case(ticker)
    assert out.blocked is True and out.meta["why"] == "shell_signed" and "pin" not in out.meta


@pytest.mark.parametrize("ticker", ["IMAX", "WAY"])
def test_the_earlier_proposed_targets_are_now_released_on_price_not_on_wording(ticker):
    _, out = _case(ticker)
    assert out.blocked is False and _released_on_price(out)


def test_NUVL_2026_06_09_ruling4_a_GSK_bid_at_a_pinned_price_is_blocked():
    """His ruling 4 (2026-10-03, 'Go with rec'): the 10-02 list released NUVL as a proposal; the
    open ranged 0.11% on a +39% gap. Ground truth now."""
    case, out = _case("NUVL")
    assert case.ground_truth and out.blocked is True and out.meta["why"] == "pinned"
    assert out.meta["pin"]["range_pct"] == pytest.approx(0.114)


def test_IRDM_2026_06_29_ruling4_a_signed_headline_at_a_free_price_is_released():
    """His ruling 4: the 10-02 list blocked IRDM on a Viasat article's 'Rocket Lab announced an
    $8B acquisition'; the open ranged 3.28% on a +19% gap. Ground truth now."""
    case, out = _case("IRDM")
    assert case.ground_truth and out.blocked is False and _released_on_price(out)


def test_MGM_stays_agent_read_and_released_by_0_24pp():
    case, out = _case("MGM")
    assert not case.ground_truth and out.blocked is False and _released_on_price(out)


def test_every_2026_10_03_call_is_a_named_ground_truth_case():
    calls = {"PD": "PASS", "DSGN": "PASS", "THR": "PASS", "HZO": "BLOCK", "RNW": "BLOCK",
             "NUVL": "BLOCK", "IRDM": "PASS"}
    for t, exp in calls.items():
        c = H.CASES_BY_TICKER[t]
        assert c.ground_truth and c.expected == exp and c.pin is not None, t


def test_every_labelled_case_still_passes_with_its_recorded_reading():
    for c in H.CASES:
        if c.ground_truth:
            out = _run(H.run_new(c))
            assert ("BLOCK" if out.blocked else "PASS") == c.expected and not out.unplanned, c.ticker


def test_mutation_guard_without_the_price_condition_his_five_corrections_go_red():
    """The pin condition is load-bearing: decide on the news alone (the 10-02 rule) and PD /
    DSGN / THR block again while HZO / RNW pass — exactly the five he corrected."""
    def news_only(a, reading):
        return mf.deal_pins_price(a), "no_price_reading"
    # the price-only arm (ruling 3) is switched off here so the guard isolates the NEWS arm's
    # price condition — with the arm on, HZO (+45%, 0.15%) would still block on price alone.
    with patch.object(mf, "pin_verdict", new=news_only), patch.object(mf, "PRICE_ONLY_GAP_MIN_PCT", 1e9):
        got = {t: ("BLOCK" if _run(H.run_new(H.CASES_BY_TICKER[t])).blocked else "PASS")
               for t in ("PD", "DSGN", "THR", "HZO", "RNW", "ACVA", "SUNE")}
    assert got == {"PD": "BLOCK", "DSGN": "BLOCK", "THR": "BLOCK", "HZO": "PASS", "RNW": "PASS",
                   "ACVA": "BLOCK", "SUNE": "BLOCK"}


def test_without_a_reader_the_10_02_verdict_stands():
    """A caller that carries no price (9M) keeps the ruled 10-02 behaviour: a signed target
    blocks, a proposal passes — so the replay grid test and every pre-10-03 test hold."""
    hzo = _run(H.run_new(H.CASES_BY_TICKER["HZO"], use_case_pin=False))
    acva = _run(H.run_new(H.CASES_BY_TICKER["ACVA"], use_case_pin=False))
    assert hzo.blocked is False and acva.blocked is True and acva.meta["why"] == "no_price_reading"


def test_a_nominated_name_whose_window_is_unreadable_is_held_and_audited():
    case = H.CASES_BY_TICKER["HZO"]._replace(pin=None, pin_pending=True)
    out = _run(H.run_new(case))
    assert out.blocked is True and out.meta["pending"] is True and out.meta["why"] == "pin_pending"
    assert out.meta["pin"]["why"] == "pre_market"
    pend = [a for a in out.audits if a[0] == "mna_pin_pending"]
    assert pend and pend[0][2]["answer"]["status"] == "proposed" and pend[0][2]["source"] == "claude_deal_fields"
    assert not [a for a in out.audits if a[0] == "mna_filter_released"]


def test_a_failing_reader_holds_rather_than_releases():
    async def boom():
        raise RuntimeError("alpaca down")
    out = _run(H.run_new(H.CASES_BY_TICKER["PD"], pin_reader=boom))
    assert out.blocked is True and out.meta["pending"] is True
    assert out.meta["pin"]["why"] == "reader_error:RuntimeError"


def test_the_reader_is_awaited_once_and_only_for_a_nomination():
    calls = []

    async def counting():
        calls.append(1)
        return _r("open5m", 5.0)
    _run(H.run_new(H.CASES_BY_TICKER["CHYM"], pin_reader=counting))      # buyer: never nominated
    assert calls == []
    _run(H.run_new(H.CASES_BY_TICKER["PD"], pin_reader=counting))
    assert calls == [1]


# ── 4. THE HEADLINE PATH ACTS ON A NOMINATION; THE CALLERS ───────────────────────────────────

_MGM_TITLE = "Barry Diller's People Makes Move To Take Casino Giant MGM Private"


def test_headline_nomination_blocks_pinned_releases_free_and_passes_without_a_reader():
    case = H.CASES_BY_TICKER["MGM"]
    pinned = _run(H.run_new(case, pin_reader=lambda: _async(_r("open5m", 0.3))))
    assert pinned.blocked is True and pinned.meta["source"] == "polygon_headline_model"
    assert pinned.meta["why"] == "pinned" and pinned.meta["title"] == _MGM_TITLE
    free = _run(H.run_new(case))
    assert free.blocked is False and _released_on_price(free)
    no_reader = _run(H.run_new(case, use_case_pin=False))
    assert no_reader.blocked is False, "a proposal with no price reading passes (the 10-02 rule)"


async def _async(v):
    return v


def test_a_target_graded_mna_is_the_prompt_rule_not_holding_and_is_counted():
    """His ruling 2 (2026-10-03): 'mna' is for a signed SHELL only, so PD's recorded 10-02 shape
    (grade 'mna' + target/signed/unknown) is now the prompt rule NOT holding — the price still
    releases it (`pin_free`) and the `mna_grade_without_pin` counter fires once. A signed shell
    graded 'mna' is the rule holding: no row."""
    out = _run(H.run_new(H.CASES_BY_TICKER["PD"]))
    assert out.blocked is False and _released_on_price(out)
    rows = [a for a in out.audits if a[0] == "mna_grade_without_pin"]
    assert len(rows) == 1 and "not a signed shell" in rows[0][1]
    shell = H.CASES_BY_TICKER["SUNE"]._replace(catalyst_quality="mna",
                                               grader=H.Ans("shell", "signed", "unknown", "Suniva"))
    out = _run(H.run_new(shell))
    assert out.blocked is True and not [a for a in out.audits if a[0] == "mna_grade_without_pin"]


def test_a_free_nominating_hit_does_not_swallow_the_unanswered_row_of_its_scan():
    """Ruling 4's row is written for the other candidates even when the newest one nominated
    and the price released it (an `elif` would have skipped it)."""
    case = H.CASES_BY_TICKER["MGM"]
    extra = H._item("MGM buyout chatter grows", published="2026-05-31T10:00:00Z")   # no fixture → unanswered
    case = case._replace(articles=case.articles + (extra,))
    out = _run(H.run_new(case))
    assert out.blocked is False and _released_on_price(out)
    un = [a for a in out.audits if a[0] == "mna_headline_unanswered"]
    assert un and un[0][2]["unanswered"][0]["title"] == "MGM buyout chatter grows"


def test_ruling7_still_governs_a_grader_answered_deal_against_a_nominating_headline():
    case = H.CASES_BY_TICKER["MGM"]._replace(grader=H.Ans("buyer", "signed", "cash", "X"))
    out = _run(H.run_new(case, pin_reader=lambda: _async(_r("open5m", 0.1))))
    assert out.blocked is False
    assert any(a[0] == "mna_deal_answers_conflict" and a[2]["blocked"] is False for a in out.audits)


# ── 5. THE PRICE-ONLY ARM (his ruling 3, 2026-10-03: "Go with rec") ─────────────────────────

_SEVEN = ["TMHC", "APGE", "SAFT", "FBRX", "VREX", "ARX", "WEAV"]


def test_price_only_verdict_states():
    free = _r("open5m", 0.99)
    assert mf.price_only_pin_verdict(None, free) == (False, "gap_below_arm")
    assert mf.price_only_pin_verdict(19.99, _r("open5m", 0.1)) == (False, "gap_below_arm")
    assert mf.price_only_pin_verdict(20.0, None) == (False, "no_price_reading")
    assert mf.price_only_pin_verdict(25.0, _r("open5m", None, readable=False, why="pre_market", n=0)) == (None, "pin_pending")
    assert mf.price_only_pin_verdict(22.35, _r("open5m", 0.2515)) == (True, "price_only_pinned")
    assert mf.price_only_pin_verdict(22.35, _r("open5m", mf.PRICE_ONLY_PIN_MAX_PCT)) == (True, "price_only_pinned")
    assert mf.price_only_pin_verdict(31.81, free) == (False, "price_only_free")
    assert (mf.PRICE_ONLY_GAP_MIN_PCT, mf.PRICE_ONLY_PIN_MAX_PCT) == (20.0, 0.5)


@pytest.mark.parametrize("ticker", _SEVEN)
def test_the_seven_news_missed_buyouts_block_on_the_price_alone(ticker):
    case, out = _case(ticker)
    assert case.ground_truth and case.grader == H._NONE and case.gap_pct >= 20
    assert out.blocked is True and out.meta["source"] == "open_window_price_pin"
    assert out.meta["why"] == "price_only_pinned" and out.meta["pin"]["pinned"] is True
    assert out.meta["pin"]["threshold_pct"] == 0.5 and out.meta["gap_pct"] == pytest.approx(case.gap_pct)
    assert out.calls == []


def test_price_only_arm_lets_free_big_gappers_through_and_never_reads_small_gaps():
    for t in ("VKTX", "ATAI"):          # +23% / 3.38%, +32% / 0.99%
        case, out = _case(t)
        assert case.gap_pct >= 20 and out.blocked is False, t
    calls = []

    async def counting():
        calls.append(1)
        return _r("open5m", 0.05)
    out = _run(H.run_new(H.CASES_BY_TICKER["CHYM"]._replace(gap_pct=9.35), pin_reader=counting))
    assert out.blocked is False and calls == [], "below 20% the window is never read"
    out = _run(H.run_new(H.CASES_BY_TICKER["CHYM"]._replace(gap_pct=25.0), pin_reader=counting))
    assert out.blocked is True and out.meta["source"] == "open_window_price_pin" and calls == [1]


def test_price_only_arm_holds_a_big_gapper_while_the_window_is_unreadable():
    case = H.CASES_BY_TICKER["TMHC"]._replace(pin=None, pin_pending=True)
    out = _run(H.run_new(case))
    assert out.blocked is True and out.meta["pending"] is True
    assert out.meta["source"] == "open_window_price_pin" and out.meta["why"] == "pin_pending"
    pend = [a for a in out.audits if a[0] == "mna_pin_pending"]
    assert pend and pend[0][2]["source"] == "open_window_price_pin" and pend[0][2]["gap_pct"] == pytest.approx(22.35)
    assert "price-only arm" in pend[0][1]


def test_price_only_arm_needs_a_reader_and_never_runs_without_the_gap():
    assert _run(H.run_new(H.CASES_BY_TICKER["TMHC"], use_case_pin=False)).blocked is False
    assert _run(H.run_new(H.CASES_BY_TICKER["TMHC"]._replace(gap_pct=None))).blocked is False


def test_price_only_arm_runs_after_the_news_arm_and_reads_the_window_once():
    """A nominated AND >= 20% name: the news arm reads the window; the arm reuses the reading."""
    calls = []

    async def counting():
        calls.append(1)
        return _r("open5m", 5.36)
    out = _run(H.run_new(H.CASES_BY_TICKER["PD"], pin_reader=counting))   # PD: nominated, +25%, free
    assert out.blocked is False and calls == [1]


def test_mutation_guard_the_arm_is_load_bearing_for_the_seven():
    with patch.object(mf, "PRICE_ONLY_GAP_MIN_PCT", 1e9):
        got = {t: _run(H.run_new(H.CASES_BY_TICKER[t])).blocked for t in _SEVEN}
    assert got == {t: False for t in _SEVEN}


def test_ep_filter_passes_the_gap_and_holds_under_the_arm_with_the_classified_prefix():
    from agents.market_intelligence import ep_detector
    from agents.market_intelligence.theme_axis_shadow import classify_legacy_filter_reason
    seen, audits = {}, []

    async def fake_is_likely_ma(ticker, **kw):
        seen.update(kw)
        return True, {"source": "open_window_price_pin", "pending": True, "why": "pin_pending",
                      "gap_pct": 22.35, "pin": {"why": "pre_market", "readable": False}}

    async def audit(event_type, summary, detail=""):
        audits.append(event_type)
    with patch.object(ep_detector, "is_likely_ma", new=fake_is_likely_ma), \
         patch.object(ep_detector, "log_audit_event", new=audit):
        reason = _run(ep_detector._post_grade_filters(
            "TMHC", "routine", "a", "s", 22.35, 1_000_000, 3.0, date(2026, 6, 1),
            lattice_acting=False, deal_answer=DealAnswer("none", "none", "none")))
    assert seen["gap_pct"] == 22.35
    assert reason.startswith("M&A/buyout catalyst") and "price-only arm" in reason and "held" in reason
    assert classify_legacy_filter_reason(reason) == "post_grade_filter"
    assert "mna_filter_fired" not in audits


def test_ep_filter_holds_a_pending_name_under_the_classified_prefix_and_writes_no_fired_row():
    from agents.market_intelligence import ep_detector
    from agents.market_intelligence.theme_axis_shadow import classify_legacy_filter_reason
    seen, audits = {}, []

    async def fake_is_likely_ma(ticker, **kw):
        seen.update(kw)
        return True, {"source": "claude_deal_fields", "pending": True, "why": "pin_pending",
                      "pin": {"why": "pre_market", "readable": False}}

    async def audit(event_type, summary, detail=""):
        audits.append(event_type)
    with patch.object(ep_detector, "is_likely_ma", new=fake_is_likely_ma), \
         patch.object(ep_detector, "log_audit_event", new=audit):
        reason = _run(ep_detector._post_grade_filters(
            "HZO", "routine", "analysis", "summary", 45.0, 1_000_000, 3.0,
            date(2026, 8, 10), lattice_acting=False,
            deal_answer=DealAnswer("target", "proposed", "unknown")))
    assert reason.startswith("M&A/buyout catalyst") and "held" in reason and "pre_market" in reason
    assert classify_legacy_filter_reason(reason) == "post_grade_filter"
    assert "mna_filter_fired" not in audits
    assert callable(seen["pin_reader"])


def test_ep_filter_still_writes_the_fired_row_for_a_decided_block():
    from agents.market_intelligence import ep_detector
    audits = []

    async def fake_is_likely_ma(ticker, **kw):
        return True, {"source": "claude_deal_fields", "why": "pinned",
                      "pin": {"range_pct": 0.15, "pinned": True}}

    async def audit(event_type, summary, detail=""):
        audits.append((event_type, summary))
    with patch.object(ep_detector, "is_likely_ma", new=fake_is_likely_ma), \
         patch.object(ep_detector, "log_audit_event", new=audit), \
         patch("agents.market_intelligence.ma_filter.should_log_mna_filter_fired",
               new=AsyncMock(return_value=True)):
        reason = _run(ep_detector._post_grade_filters(
            "HZO", "routine", "a", "s", 45.0, 1_000_000, 3.0, date(2026, 8, 10),
            lattice_acting=False, deal_answer=DealAnswer("target", "proposed", "unknown")))
    assert reason == "M&A/buyout catalyst — no momentum trade"
    assert audits and audits[0][0] == "mna_filter_fired" and "HZO via claude_deal_fields (ep)" in audits[0][1]


def test_ep_filters_reader_is_the_open_window_of_the_scan_date():
    from agents.market_intelligence import ep_detector
    seen = {}

    async def fake_is_likely_ma(ticker, **kw):
        seen.update(kw)
        return False, None
    with patch.object(ep_detector, "is_likely_ma", new=fake_is_likely_ma), \
         patch.object(ep_detector, "log_audit_event", new=AsyncMock(return_value=None)), \
         patch.object(mf, "read_open_window_pin", new=AsyncMock(return_value=_r("open5m", 0.2))) as rd:
        _run(ep_detector._post_grade_filters(
            "ACVA", "mna", "a", "s", 44.8, 1_000_000, 3.0, date(2026, 9, 11), lattice_acting=False,
            deal_answer=DealAnswer("target", "signed", "cash")))
        got = _run(seen["pin_reader"]())
    assert got.range_pct == 0.2 and rd.await_args.args == ("ACVA", date(2026, 9, 11))


def test_the_flag_readers_composition_reads_the_scan_dates_bar_from_the_history_query():
    """The flag scan's reader is `day_window_pin(await db.get_recent_daily_history(ticker, 5,
    end_date=scan_date), scan_date)` — exercise that composition end to end through the real
    db function with the pool mocked to return mi_daily_closes-shaped records."""
    from tests.conftest import make_mock_pool
    from agents.market_intelligence import db
    pool, conn = make_mock_pool()
    seen = {}

    async def _fetch(sql, *args):
        seen["args"] = args
        return [{"trade_date": date(2026, 5, 21), "open_price": 9.9, "high_price": 10.0,
                 "low_price": 9.8, "close": 9.95, "volume": 1},
                {"trade_date": date(2026, 5, 22), "open_price": 10.1, "high_price": 10.24,
                 "low_price": 10.0, "close": 10.04, "volume": 1}]
    conn.fetch = _fetch
    with patch("agents.market_intelligence.db.get_pool", new=AsyncMock(return_value=pool)):
        async def _reader():
            rows = await db.get_recent_daily_history("THR", 5, end_date=date(2026, 5, 22))
            return mf.day_window_pin(rows or [], date(2026, 5, 22))
        reading = _run(_reader())
    assert "THR" in seen["args"]
    assert reading.readable and reading.window == "day"
    assert reading.range_pct == pytest.approx(2.3904, abs=1e-3) and reading.pinned is False
