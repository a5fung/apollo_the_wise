"""HTF labelled corpus — replay the SHIPPED detector over trader-labelled names.

Members + labels: `tests/fixtures/htf_labelled.py`. Bars: `tests/fixtures/htf_labelled_bars.psv`.
State is threaded day by day the way `flag_scan` threads it (the three 5-day-lookback
queries: prior pivot, yesterday's stage, recent stages), from the variant's own prior
outputs — not from stored rows.
"""
from __future__ import annotations

import bisect
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

import pytest

from agents.market_intelligence import flag_detector as fd
from tests.fixtures.htf_labelled import HTF_LABELLED

_BARS = Path(__file__).parent / "fixtures" / "htf_labelled_bars.psv"
_ACTIONABLE = ("WATCH", "TIGHTENING", "COILED", "TRIGGERED")
_REPLAY_FROM = date(2026, 6, 15)     # two weeks of state before the earliest labelled window


def _load_bars() -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = defaultdict(list)
    for line in _BARS.read_text().splitlines():
        if not line.strip():
            continue
        t, d, o, h, l, c, v = line.split("|")
        out[t].append({"trade_date": date.fromisoformat(d), "open_price": float(o),
                       "high_price": float(h), "low_price": float(l), "close": float(c),
                       "volume": float(v)})
    for t in out:
        out[t].sort(key=lambda r: r["trade_date"])
    return out


def _replay(ticker: str, bars: list[dict], through: date) -> dict[date, dict]:
    """Shipped compute_flag_metrics, one scan per trading day, prod-style state threading."""
    dates = [r["trade_date"] for r in bars]
    prior: list[dict] = []
    out: dict[date, dict] = {}
    for d in dates:
        if d < _REPLAY_FROM or d > through:
            continue
        lo = bisect.bisect_left(dates, d - timedelta(days=fd._HISTORY_DAYS))
        hi = bisect.bisect_right(dates, d)
        rows = bars[lo:hi]
        cutoff = d - timedelta(days=5)
        window = [m for m in prior if cutoff <= m["scan_date"] < d]
        ppiv = next(((m["pivot_high_date"], m["pivot_high_price"])
                     for m in reversed(window) if m["pivot_high_date"] is not None), None)
        m = fd.compute_flag_metrics(
            rows, ticker=ticker,
            yesterday_stage=window[-1]["stage"] if window else None,
            recent_stages=[w["stage"] for w in window],
            prior_pivot_date=ppiv[0] if ppiv else None,
            prior_pivot_high=ppiv[1] if ppiv else None,
        )
        m["scan_date"] = d
        prior.append(m)
        out[d] = m
    return out


@pytest.fixture(scope="module")
def bars():
    b = _load_bars()
    assert b, "htf_labelled_bars.psv is empty"
    return b


def test_every_member_has_an_operator_sourced_label():
    for m in HTF_LABELLED:
        assert m.label_source and "operator" in m.label_source, (
            f"{m.ticker}: label_source must name where the operator-shared label came from"
        )
        assert m.expected in ("actionable", "rejected:runup"), m


@pytest.mark.parametrize("member", HTF_LABELLED, ids=[m.ticker for m in HTF_LABELLED])
def test_labelled_member_matches_recorded_verdict(member, bars):
    assert member.ticker in bars, f"no bars for {member.ticker} in {_BARS.name}"
    res = _replay(member.ticker, bars[member.ticker], through=max(member.assert_dates))
    for d in member.assert_dates:
        m = res.get(d)
        assert m is not None, f"{member.ticker}: no bar on {d}"
        if member.expected == "actionable":
            assert m["stage"] in _ACTIONABLE, (
                f"{member.ticker} {d}: MUST-NOT-MISS regressed — stage={m['stage']} reason={m['reason']}"
            )
        else:
            assert m["stage"] == "unqualified" and (m["reason"] or "").startswith("runup_"), (
                f"{member.ticker} {d}: the RECORDED verdict changed (stage={m['stage']} "
                f"reason={m['reason']}). If this is deliberate, update the member's `expected` "
                f"AND docs/setups/htf.md § Known limitations in the same commit."
            )
            assert m["runup_pct"] is not None and m["runup_pct"] < fd._RUNUP_MIN_RATIO - 1.0
