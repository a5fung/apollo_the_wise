"""`check_operator_ep_downgraded` — the automated version of the operator's 2026-09-07 ask.

Operator: "a safeguard here is to also trigger whenever we negatively impact a real EP, but that
will likely need to be manual." Then, clarifying: "not just current EP list, i meant future EPs
if we/i spot we had a bad rubric read but it's a real EP per my read." This file proves the
automation actually does what he asked instead of needing him to notice by hand: it fires on an
unacknowledged catalyst-rubric downgrade of an operator-labelled real EP, stays quiet on an
acknowledged one, and is not quietly blind to any of the three event types the rubric can
downgrade through.

Read-only telemetry (THE LINE): these tests exercise a check that reads mi_audit_log only and
changes no grade, threshold, or trade state.
"""
from __future__ import annotations

import re

import pytest

from agents.market_intelligence import audit_invariants as ai
from shared.operator_labelled_eps import ACKNOWLEDGED_DOWNGRADES, OPERATOR_LABELLED_EPS


class _FakeConn:
    """Stand-in for an asyncpg conn routing the ONE query shape
    `check_operator_ep_downgraded` issues per operator-labelled EP:

        SELECT event_type, COUNT(*) AS n, MIN(created_at) AS first_seen
        FROM mi_audit_log
        WHERE event_type = ANY($1) AND detail LIKE $2 AND detail LIKE $3
        GROUP BY event_type

    `rows` is the flat set of raw audit rows this fake `mi_audit_log` holds — each a dict with
    ticker/alert_date/event_type/created_at. `fetch()` filters and groups them exactly like the
    real SQL would, so a test can plant rows and assert on the check's real grouping/dedup
    behaviour rather than on a canned return value.
    """

    def __init__(self, rows):
        self._rows = list(rows)

    async def fetch(self, sql, *args):
        event_types, ticker_pat, date_pat = args
        ticker = re.search(r'"ticker": "([^"]+)"', ticker_pat).group(1)
        alert_date = re.search(r'"alert_date": "([^"]+)"', date_pat).group(1)
        matches = [
            r for r in self._rows
            if r["event_type"] in event_types
            and r["ticker"] == ticker and r["alert_date"] == alert_date
        ]
        grouped: dict[str, dict] = {}
        for r in matches:
            g = grouped.setdefault(r["event_type"], {"n": 0, "first_seen": r["created_at"]})
            g["n"] += 1
            g["first_seen"] = min(g["first_seen"], r["created_at"])
        return [
            {"event_type": et, "n": v["n"], "first_seen": v["first_seen"]}
            for et, v in sorted(grouped.items())
        ]


def _row(ticker, alert_date, event_type, created_at="2026-01-01T00:00:00Z"):
    return {"ticker": ticker, "alert_date": alert_date, "event_type": event_type,
            "created_at": created_at}


# ── Quiet today, against the REAL acknowledged set ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_quiet_today_with_the_real_acknowledged_set():
    """Reproduces the exact prod shape verified 2026-09-07 (SELECT against mi_audit_log): BFLY
    and TEAM each carry exactly one `catalyst_earnings_revenue_weak_downgrade` row, both are in
    the real, shipped `ACKNOWLEDGED_DOWNGRADES`, and nothing else on the operator-labelled list
    has ever been downgraded. The check must pass, count 0.

    MUTATION TARGET: deleting either acknowledged-set entry (or its event_type) flips this red —
    proven directly by test_removing_an_acknowledgment_makes_it_fire below.
    """
    rows = [
        _row("BFLY", "2026-06-18", "catalyst_earnings_revenue_weak_downgrade"),
        _row("TEAM", "2026-08-07", "catalyst_earnings_revenue_weak_downgrade"),
    ]
    ok, body = await ai.check_operator_ep_downgraded(_FakeConn(rows))
    assert ok is True
    assert body["count"] == 0
    assert body["offending"] == []


@pytest.mark.asyncio
async def test_quiet_with_no_rows_at_all():
    """The trivial clean case — an empty mi_audit_log breaches nothing."""
    ok, body = await ai.check_operator_ep_downgraded(_FakeConn([]))
    assert ok is True
    assert body["count"] == 0


# ── Fires on an unacknowledged downgrade ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_fires_on_an_unacknowledged_downgrade():
    """PLTR is operator-labelled and carries NO acknowledged-set entry. A downgrade row against
    it must breach.

    MUTATION TARGET: an invariant that always returns (True, ...) — or one that forgets to check
    membership against OPERATOR_LABELLED_EPS at all — passes trivially; this fails against either.
    """
    rows = [_row("PLTR", "2026-08-04", "catalyst_earnings_revenue_weak_downgrade")]
    ok, body = await ai.check_operator_ep_downgraded(_FakeConn(rows))
    assert ok is False
    assert body["count"] == 1
    assert "PLTR 2026-08-04 catalyst_earnings_revenue_weak_downgrade" in body["offending"][0]


@pytest.mark.asyncio
async def test_a_ticker_not_on_the_operator_list_is_never_checked():
    """A downgrade on some other, non-operator-labelled ticker must never breach — this check is
    scoped to OPERATOR_LABELLED_EPS only, not every downgrade in the log."""
    rows = [_row("RANDOM", "2026-08-04", "catalyst_earnings_revenue_weak_downgrade")]
    ok, body = await ai.check_operator_ep_downgraded(_FakeConn(rows))
    assert ok is True
    assert body["count"] == 0


# ── Not quietly blind to the other two downgrade event types ──────────────────────────────────


@pytest.mark.asyncio
async def test_fires_on_a_prose_mismatch_downgrade_not_just_the_revenue_gate():
    """HTFL is operator-labelled and unacknowledged. A `catalyst_prose_mismatch_downgrade` row
    (the #72 downgrade path, not the earnings-revenue one) must breach exactly like the
    revenue-weak event would.
    """
    rows = [_row("HTFL", "2026-08-14", "catalyst_prose_mismatch_downgrade")]
    ok, body = await ai.check_operator_ep_downgraded(_FakeConn(rows))
    assert ok is False
    assert "catalyst_prose_mismatch_downgrade" in body["offending"][0]


@pytest.mark.asyncio
async def test_fires_on_a_pplx_hedge_downgrade():
    """Same proof for the third path — the Perplexity hollow-search hedge downgrade."""
    rows = [_row("MRNA", "2026-08-19", "catalyst_pplx_hedge_downgrade")]
    ok, body = await ai.check_operator_ep_downgraded(_FakeConn(rows))
    assert ok is False
    assert "catalyst_pplx_hedge_downgrade" in body["offending"][0]


@pytest.mark.asyncio
async def test_narrowing_the_event_type_tuple_makes_the_check_quietly_blind(monkeypatch):
    """Proves WHY all three event types must be watched: with the real
    `_CATALYST_DOWNGRADE_EVENT_TYPES`, a `catalyst_pplx_hedge_downgrade` row breaches. Narrow the
    tuple back down to just the one event type named in the original ask and the SAME row goes
    completely unseen — the exact blind spot this check exists to close.

    MUTATION TARGET: this test IS the regression guard for `_CATALYST_DOWNGRADE_EVENT_TYPES`
    losing an entry — if a future edit drops `catalyst_prose_mismatch_downgrade` or
    `catalyst_pplx_hedge_downgrade` from the real tuple, `test_fires_on_a_prose_mismatch_downgrade
    _not_just_the_revenue_gate` / `test_fires_on_a_pplx_hedge_downgrade` above go red directly.
    """
    rows = [_row("MRNA", "2026-08-19", "catalyst_pplx_hedge_downgrade")]

    ok_full, _ = await ai.check_operator_ep_downgraded(_FakeConn(rows))
    assert ok_full is False, "sanity: the full tuple must catch this row"

    monkeypatch.setattr(
        ai, "_CATALYST_DOWNGRADE_EVENT_TYPES", ("catalyst_earnings_revenue_weak_downgrade",)
    )
    ok_narrow, body_narrow = await ai.check_operator_ep_downgraded(_FakeConn(rows))
    assert ok_narrow is True, (
        "narrowing the event-type tuple should make this row invisible — proving the full tuple "
        "is load-bearing, not decorative"
    )
    assert body_narrow["count"] == 0


# ── The acknowledged set is load-bearing, not decoration ──────────────────────────────────────


@pytest.mark.asyncio
async def test_removing_an_acknowledgment_makes_it_fire(monkeypatch):
    """Take the real, shipped acknowledged set, strip BFLY's entry out of it, and prove the exact
    same BFLY row that is silent today now breaches. This is the "no vacuous guard" proof for
    ACKNOWLEDGED_DOWNGRADES itself.
    """
    rows = [_row("BFLY", "2026-06-18", "catalyst_earnings_revenue_weak_downgrade")]

    ok_acked, _ = await ai.check_operator_ep_downgraded(_FakeConn(rows))
    assert ok_acked is True, "sanity: BFLY's real downgrade is acknowledged today"

    stripped = {
        k: v for k, v in ACKNOWLEDGED_DOWNGRADES.items()
        if k != ("BFLY", "2026-06-18", "catalyst_earnings_revenue_weak_downgrade")
    }
    monkeypatch.setattr(ai, "ACKNOWLEDGED_DOWNGRADES", stripped)
    ok_stripped, body_stripped = await ai.check_operator_ep_downgraded(_FakeConn(rows))
    assert ok_stripped is False
    assert body_stripped["count"] == 1
    assert "BFLY 2026-06-18" in body_stripped["offending"][0]


@pytest.mark.asyncio
async def test_acknowledgment_is_scoped_to_its_own_event_type():
    """Acknowledging BFLY's revenue-weak downgrade must NOT silence a DIFFERENT downgrade
    mechanism on the same ticker+date that nobody has looked at — the acknowledged set is keyed
    by (ticker, alert_date, event_type), not just (ticker, alert_date).

    MUTATION TARGET: keying ACKNOWLEDGED_DOWNGRADES (or the check's lookup) by (ticker,
    alert_date) alone flips this green when it must be red.
    """
    rows = [_row("BFLY", "2026-06-18", "catalyst_prose_mismatch_downgrade")]
    ok, body = await ai.check_operator_ep_downgraded(_FakeConn(rows))
    assert ok is False, (
        "BFLY's acknowledgment covers only catalyst_earnings_revenue_weak_downgrade — a prose- "
        "mismatch downgrade on the same name/date is a DIFFERENT, unacknowledged mechanism"
    )
    assert "catalyst_prose_mismatch_downgrade" in body["offending"][0]


# ── Registry wiring ─────────────────────────────────────────────────────────────────────────────


def test_registered_in_all_invariants():
    """The whole point of adding this to `all_invariants()` is that system_audit.py's sweep and
    readiness_check.py pick it up with no special-casing — prove it is actually in the list."""
    import datetime
    names = [name for name, _fn, _kwargs in ai.all_invariants(
        since=datetime.date(2026, 1, 1), since_dt=datetime.datetime(2026, 1, 1)
    )]
    assert ai.INV_OPERATOR_EP_DOWNGRADED in names


@pytest.mark.asyncio
async def test_every_operator_labelled_ep_is_actually_queried():
    """Guard the guard: if `check_operator_ep_downgraded` stopped iterating the FULL
    `OPERATOR_LABELLED_EPS` (e.g. hardcoded to a shorter slice), every test above using one
    specific name like MRNA/HTFL would still pass regardless — none of them would notice a
    ticker silently dropped from the loop. This runs the check against an EMPTY fake log and
    asserts every single operator-labelled ticker was actually queried, not just the ones the
    other tests happen to exercise.

    MUTATION TARGET: changing the check's loop to `for ep in OPERATOR_LABELLED_EPS[:3]:` flips
    this red (only 3 of 7 tickers get queried) while every other test in this file stays green.
    """
    class _RecordingConn(_FakeConn):
        def __init__(self):
            super().__init__(rows=[])
            self.queried_tickers: set[str] = set()

        async def fetch(self, sql, *args):
            _event_types, ticker_pat, _date_pat = args
            self.queried_tickers.add(re.search(r'"ticker": "([^"]+)"', ticker_pat).group(1))
            return await super().fetch(sql, *args)

    conn = _RecordingConn()
    await ai.check_operator_ep_downgraded(conn)
    assert conn.queried_tickers == {ep.ticker for ep in OPERATOR_LABELLED_EPS}
