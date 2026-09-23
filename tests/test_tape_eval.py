"""#299 — unit tests for the point-in-time tape RECONSTRUCTION helpers in eval_tape_judge.

The tz handling (epoch-ms UTC bars vs ET wall-clock cuts) is the codebase's recurring bug class,
and the point-in-time truncation is the lookahead guard — both are pure and testable without
network/DB. Fixtures build a synthetic 2026-06-15 (EDT, UTC-4) minute tape from ET wall times."""
from datetime import datetime
from zoneinfo import ZoneInfo

from scripts.eval_tape_judge import (
    OR_END_MIN, _bar_et_minute, _format_delta, _modal_stable, cum_volumes, opening_range,
    slice_pit, tradeability_bucket,
)

_ET = ZoneInfo("America/New_York")
_DAY = "2026-06-15"  # a Monday in EDT (UTC-4)


def _ms(h, m):
    """epoch-ms for HH:MM ET on the fixture day (DST-correct via ZoneInfo)."""
    dt = datetime(2026, 6, 15, h, m, tzinfo=_ET)
    return int(dt.timestamp() * 1000)


def _bar(h, m, *, o=10.0, hi=10.0, lo=10.0, c=10.0, v=1000):
    return {"t": _ms(h, m), "o": o, "h": hi, "l": lo, "c": c, "v": v}


def _detected(h, m):
    return datetime(2026, 6, 15, h, m, tzinfo=_ET)


def test_bar_et_minute_is_dst_correct():
    # 09:30 ET on an EDT day = 13:30 UTC; the helper must return ET minute-of-day = 570.
    assert _bar_et_minute(_ms(9, 30)) == 9 * 60 + 30
    assert _bar_et_minute(_ms(4, 0)) == 4 * 60
    assert _bar_et_minute(_ms(9, 35)) == OR_END_MIN


def test_slice_pit_truncates_at_detected_at_no_lookahead():
    bars = [_bar(9, 30), _bar(9, 34), _bar(9, 35), _bar(9, 40)]
    pit = slice_pit(bars, _detected(9, 35))  # cut AT 9:35 → 9:30,9:34,9:35 in; 9:40 OUT
    mins = [_bar_et_minute(b["t"]) for b in pit]
    assert mins == [570, 574, 575]
    assert all(m <= 575 for m in mins)  # nothing after the grade cut is visible


def test_opening_range_extracts_930_934_hilo():
    bars = [
        _bar(9, 30, hi=10.5, lo=10.0),
        _bar(9, 31, hi=10.8, lo=9.7),   # window high/low
        _bar(9, 34, hi=10.2, lo=10.1),
        _bar(9, 35, hi=12.0, lo=8.0),   # 9:35 is OUTSIDE the OR window — must be ignored
    ]
    orr = opening_range(bars, detected_et_min=9 * 60 + 40)
    assert orr == (10.8, 9.7)


def test_opening_range_none_before_935():
    bars = [_bar(9, 30, hi=10.5, lo=10.0), _bar(9, 32, hi=10.6, lo=9.9)]
    # graded at 9:33 — OR not complete yet → None BY CONSTRUCTION (the tradeability segmentation)
    assert opening_range(bars, detected_et_min=9 * 60 + 33) is None


def test_opening_range_none_when_no_window_bars():
    bars = [_bar(9, 36, hi=11.0, lo=10.0)]  # gap — nothing in 9:30–9:34
    assert opening_range(bars, detected_et_min=9 * 60 + 40) is None


def test_cum_volumes_splits_at_open_and_sums_dollars():
    bars = [
        _bar(4, 0, c=10.0, v=500),    # premarket
        _bar(8, 0, c=10.0, v=1500),   # premarket
        _bar(9, 30, c=11.0, v=2000),  # session
        _bar(9, 31, c=12.0, v=1000),  # session
    ]
    pm, sess, dollars = cum_volumes(bars)
    assert pm == 2000          # 500 + 1500
    assert sess == 3000        # 2000 + 1000
    # dollar vol over all >=04:00 bars: 500*10 + 1500*10 + 2000*11 + 1000*12 = 5k+15k+22k+12k
    assert dollars == 54000.0


def test_cum_volumes_ignores_overnight_before_pm_open():
    bars = [_bar(3, 0, c=10.0, v=9999), _bar(4, 0, c=10.0, v=100)]
    pm, sess, dollars = cum_volumes(bars)
    assert pm == 100 and sess == 0 and dollars == 1000.0  # the 03:00 bar is excluded


def test_tradeability_buckets():
    assert "premarket" in tradeability_bucket(9 * 60 + 0)
    assert "OR-forming" in tradeability_bucket(9 * 60 + 32)
    assert "ORB-tradeable" in tradeability_bucket(9 * 60 + 40)
    assert "out-of-ORB" in tradeability_bucket(9 * 60 + 50)
    assert "post-ORB" in tradeability_bucket(10 * 60 + 5)


def test_modal_stable_detects_stability_and_flip():
    # both-arms noise floor (advisor B): stable iff every replicate is the same non-None tier.
    modal, stable, tiers = _modal_stable([{"tier": "HIGH"}, {"tier": "HIGH"}, {"tier": "HIGH"}])
    assert modal == "HIGH" and stable is True and tiers == ["HIGH", "HIGH", "HIGH"]
    modal, stable, _ = _modal_stable([{"tier": "HIGH"}, {"tier": "MODERATE"}, {"tier": "HIGH"}])
    assert modal == "HIGH" and stable is False           # flipped → noise-dominated
    modal, stable, _ = _modal_stable([None, None])
    assert modal is None and stable is False              # all fail-open → not a stable verdict


def test_format_delta_renders_without_keyerror():
    # advisor C: the full run's least-exercised path (smoke produced 0 deltas) must not KeyError
    # after the spend. Exercise it on a synthetic delta record carrying every key it reads.
    rec = {
        "ticker": "TEST", "alert_date": "2026-06-15",
        "bucket": "OR+ORB-tradeable(9:35-9:44)",
        "presence": {"or_atr": True, "pm_vol_curve": False, "liquidity": True},
        "nt_modal": "HIGH", "wt_modal": "MODERATE",
        "tape": {"opening_range_atr": 0.41, "pm_vol_curve": None, "liquidity": "$120M traded"},
        "wt_verdict": {"tier": "MODERATE", "rationale": "violent open — bracket geometry poor"},
    }
    out = "\n".join(_format_delta(rec))
    assert "TEST" in out and "0.41" in out and "violent open" in out
    assert "or_atr" in out and "liquidity" in out        # present-features list rendered


def test_format_delta_tolerates_missing_tape_and_verdict():
    rec = {
        "ticker": "AAA", "alert_date": "2026-06-15", "bucket": "premarket(<9:30) OR=None",
        "presence": {"or_atr": False, "pm_vol_curve": True, "liquidity": False},
        "nt_modal": "MODERATE", "wt_modal": "HIGH", "tape": None, "wt_verdict": None,
    }
    out = "\n".join(_format_delta(rec))   # must not raise on tape=None / wt_verdict=None
    assert "AAA" in out and "pm_vol_curve" in out
