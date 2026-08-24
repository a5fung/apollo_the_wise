"""/scanned — rejection-visibility surface (2026-08-24).

Pins the registration points FIRST — the failure this repo has actually hit
(May 2026: six commands were invisible because one of the three registration
places was missed):
  1. BotCommand("scanned", ...) in channels/telegram.py::_register_commands
  2. CommandHandler wiring ("scanned" in the _dispatch_market_slash tuple)
  3. agent-side dispatch ("/scanned" -> _handle_scanned_query)

Also pins: the /trades button swap (Scanned in, Paper OUT — button only; the
trades:paper query path must keep answering old pinned messages), and the
renderer's funnel/scorecard behavior: zero stages still print, graded names
never drown in bulk counts, stale mi_ep_missed_outcomes rows never rank
(#583), a bulk cut that ran hard earns a line.
"""
from datetime import date, datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agents.market_intelligence.scanned_report import render_scanned_day

_NOW = datetime(2026, 8, 24, 13, 0, tzinfo=timezone.utc)
_DAY = date(2026, 8, 24)


def _data(scan=(), graded=(), alerts=(), trades=(), outcomes=()):
    return {"scan": list(scan), "graded": list(graded), "alerts": list(alerts),
            "trades": list(trades), "outcomes": list(outcomes)}


def _scan_row(ticker, reason=None, gap=10.0, ep_score=None, tier=None):
    return {"ticker": ticker, "gap_pct": gap, "prev_close": 12.0,
            "rel_volume": 1.0, "filter_reason": reason, "ep_score": ep_score,
            "score_tier": tier, "catalyst_quality": None, "adv": None,
            "pm_rvol": None, "rank_by_gap": None}


def _request(text):
    req = MagicMock()
    req.task = text
    return req


class _FakeAgent:
    def _ok(self, request, *, result):
        return MagicMock(ok=True, result=result)


# ── 1-3: the three registration points ──────────────────────────────────────

def _telegram_src():
    return open("channels/telegram.py").read()


def test_botcommand_registered():
    assert 'BotCommand("scanned"' in _telegram_src(), \
        "/scanned missing from the BotFather menu (registration point 1 of 3)"


def test_commandhandler_registered():
    src = _telegram_src()
    start = src.index("for _cmd in (")
    end = src.index("app.add_handler(CommandHandler(_cmd", start)
    assert '"scanned"' in src[start:end], \
        "/scanned missing from the CommandHandler tuple — BotCommand alone " \
        "only affects autocomplete; without this the command is silently dead " \
        "(registration point 2 of 3)"


@pytest.mark.asyncio
async def test_agent_slash_dispatch_reaches_handler():
    """Registration point 3 of 3 — '/scanned' resolves in the agent's slash
    dispatch dict and lands on _handle_scanned_query."""
    from agents.market_intelligence.agent import MarketIntelligenceAgent

    fake = MagicMock()
    fake._handle_scanned_query = AsyncMock(return_value="rendered")
    req = _request("/scanned")
    result = await MarketIntelligenceAgent._handle_slash_command(fake, req)
    fake._handle_scanned_query.assert_awaited_once_with(req)
    assert result == "rendered"


# ── /trades button swap ─────────────────────────────────────────────────────

def test_trades_keyboards_scanned_in_paper_out():
    src = _telegram_src()
    assert 'callback_data="trades:paper"' not in src, \
        "Paper (legacy) button should be removed (1 paper trade in 45 days)"
    assert src.count("trades:scanned") >= 2, \
        "Scanned button must be on BOTH /trades keyboards (summary + drill-down)"


@pytest.mark.asyncio
async def test_paper_view_query_path_intact():
    """Button removed, view retained — an old pinned message pressing
    trades:paper must still answer."""
    from agents.market_intelligence.agent import MarketIntelligenceAgent
    from agents.market_intelligence import agent as agent_mod
    from tests.conftest import make_mock_pool

    pool, conn = make_mock_pool()
    conn.fetch = AsyncMock(return_value=[])
    with patch.object(agent_mod, "get_pool", new=AsyncMock(return_value=pool)):
        resp = await MarketIntelligenceAgent._handle_trades_detail(
            _FakeAgent(), _request("/trades_detail paper"))
    assert "paper" in resp.result.lower()


@pytest.mark.asyncio
async def test_trades_detail_scanned_view_delegates():
    """The [Scanned] button (trades:scanned:<date>) routes to the /scanned
    handler without touching the trades pool."""
    from agents.market_intelligence.agent import MarketIntelligenceAgent

    fake = MagicMock()
    fake._handle_scanned_query = AsyncMock(return_value="rendered")
    req = _request("/trades_detail scanned 2026-08-24")
    result = await MarketIntelligenceAgent._handle_trades_detail(fake, req)
    fake._handle_scanned_query.assert_awaited_once_with(req)
    assert result == "rendered"


# ── handler date parsing ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_handler_rejects_malformed_date():
    from agents.market_intelligence.agent import MarketIntelligenceAgent

    resp = await MarketIntelligenceAgent._handle_scanned_query(
        _FakeAgent(), _request("/scanned 2026-13-99"))
    assert "Usage" in resp.result


@pytest.mark.asyncio
async def test_handler_passes_explicit_date_to_query():
    from agents.market_intelligence.agent import MarketIntelligenceAgent

    fetch = AsyncMock(return_value=_data())
    with patch("agents.market_intelligence.db.get_ep_scanned_day", new=fetch):
        resp = await MarketIntelligenceAgent._handle_scanned_query(
            _FakeAgent(), _request("/scanned 2026-08-07"))
    fetch.assert_awaited_once_with(date(2026, 8, 7))
    assert "2026-08-07" in resp.result


# ── renderer: the funnel ────────────────────────────────────────────────────

def test_zero_stages_still_print():
    """A silent stage is how a broken gate hides — every canonical stage
    renders even at zero."""
    out = render_scanned_day(
        _DAY, _data(scan=[_scan_row("ABCD", "filter:universe_prev_close_too_low: prior close $0.68 < $5.00 floor")]),
        now=_NOW)
    assert "   1  prior close under the $5 universe floor" in out
    for must_show_even_at_zero in (
        "   0  prior-day volume under the 50k-share universe floor",
        "   0  average daily dollar volume too thin",
        "   0  already ran too far before this gap",
        "   0  pre-market volume below its usual pace",
        "   0  didn't make the top-20 grading shortlist",
        "   0  graded, then a mechanical filter cut it",
        "   0  graded and scored, but under the alert bar",
        "   0  alerted, no entry attempted",
        "   0  alerted, then blocked or unfilled at entry",
        "   0  traded",
    ):
        assert must_show_even_at_zero in out, f"missing funnel line: {must_show_even_at_zero!r}"


def test_graded_then_cut_outranks_bulk_bucket():
    """The AERO case: graded (tier-shadow row, NULL score) then filter-cut.
    It counts in the graded-then-cut stage — never in the bulk pm-volume
    count — and earns a named line with the killing rule."""
    out = render_scanned_day(_DAY, _data(
        scan=[_scan_row("AERO", "pre-mkt volume 3,037 < 25,000 shares", gap=9.2)],
        graded=[{"ticker": "AERO", "live_tier": None, "live_ep_score": None,
                 "live_quality_last": "strong", "gap_pct_last": 9.2,
                 "adv_dollar": 3.4e6, "live_side": "lattice"}],
    ), now=_NOW)
    assert "   1  graded, then a mechanical filter cut it" in out
    assert "   0  pre-market volume below its usual pace" in out
    assert "AERO" in out
    assert "graded strong, then cut: pre-mkt volume 3,037 < 25,000 shares" in out


def test_alerted_ticker_never_counted_as_duplicate():
    """Last scan tick often says 'already scored earlier today' for a name
    that ALERTED — precedence must land it in the alert stages, and the
    duplicate line (zero) stays hidden (not a canonical stage)."""
    out = render_scanned_day(_DAY, _data(
        scan=[_scan_row("ACMR", "already scored earlier today", gap=15.1)],
        alerts=[{"ticker": "ACMR", "ep_score": 100.8, "score_tier": "HIGH",
                 "gap_pct": 15.1, "catalyst_quality": "strong"}],
    ), now=_NOW)
    assert "   1  alerted, no entry attempted" in out
    assert "already handled by an earlier scan today" not in out


def test_score_below_bar_reads_plain():
    out = render_scanned_day(_DAY, _data(
        scan=[_scan_row("NSSC", "score 52 < bar 65 (catalyst=strong)",
                        gap=34.2, ep_score=52.5)],
    ), now=_NOW)
    assert "   1  graded and scored, but under the alert bar" in out
    assert "scored 52, bar was 65 (strong catalyst)" in out


def test_blocked_entry_reason_is_humanized():
    """Machine prefixes must never reach the operator raw."""
    out = render_scanned_day(_DAY, _data(
        alerts=[{"ticker": "TWLO", "ep_score": 84.0, "score_tier": "HIGH",
                 "gap_pct": 22.0, "catalyst_quality": "strong"}],
        trades=[{"ticker": "TWLO", "status": "skipped",
                 "skip_reason": "block:max_positions: 5/5 (mode=live)",
                 "total_pnl": 0, "account_mode": "live"}],
    ), now=_NOW)
    assert "   1  alerted, then blocked or unfilled at entry" in out
    assert "Max open positions reached" in out
    assert "block:max_positions" not in out


def test_traded_shows_pnl():
    out = render_scanned_day(_DAY, _data(
        alerts=[{"ticker": "FIGS", "ep_score": 96.0, "score_tier": "HIGH",
                 "gap_pct": 26.7, "catalyst_quality": "game_changer"}],
        trades=[{"ticker": "FIGS", "status": "closed", "skip_reason": None,
                 "total_pnl": -6.84, "account_mode": "live"}],
    ), now=_NOW)
    assert "   1  traded" in out
    assert "traded, P&L $-7" in out


# ── renderer: outcome ranking (#583 stale guard) ────────────────────────────

def _outcome(ticker, mh, r5, refreshed):
    return {"ticker": ticker, "ret_1d": None, "ret_5d": r5,
            "max_high_5d": mh, "last_refreshed_at": refreshed}


def test_stale_outcome_never_ranks():
    """A row that stopped refreshing before its 5-session outcome settled is
    the exact class that corrupted a prior ranking table (#583) — it must
    display as stale and sort below fresh rows."""
    old_day = date(2026, 7, 1)
    stale_refresh = datetime(2026, 7, 3, tzinfo=timezone.utc)   # neither recent nor settled
    fresh_refresh = datetime(2026, 7, 20, tzinfo=timezone.utc)  # after settling
    out = render_scanned_day(old_day, _data(
        scan=[
            _scan_row("STALE", "score 40 < 50 (catalyst=routine)", gap=50.0, ep_score=40),
            _scan_row("FRESH", "score 41 < 50 (catalyst=routine)", gap=10.0, ep_score=41),
        ],
        outcomes=[
            _outcome("STALE", 9.99, 9.99, stale_refresh),
            _outcome("FRESH", 0.10, 0.05, fresh_refresh),
        ],
    ), now=_NOW)
    assert "outcome stale, not ranked" in out
    assert "+999%" not in out  # the stale numbers never render
    # Fresh row ranks first despite the stale row's (untrusted) huge number.
    assert out.index("FRESH") < out.index("STALE")


def test_fresh_outcomes_rank_by_run():
    d = _DAY - timedelta(days=10)
    out = render_scanned_day(d, _data(
        scan=[
            _scan_row("SMALL", "score 40 < 50 (catalyst=routine)", ep_score=40),
            _scan_row("BIGRN", "score 41 < 50 (catalyst=routine)", ep_score=41),
        ],
        outcomes=[
            _outcome("SMALL", 0.02, 0.01, _NOW),
            _outcome("BIGRN", 0.25, 0.21, _NOW),
        ],
    ), now=_NOW)
    assert "ran +25% high, settled +21% in 5 sessions" in out
    assert out.index("BIGRN") < out.index("SMALL")


def test_bulk_cut_that_ran_earns_a_line():
    """A rejected name that ran +46% earns a line; one that went nowhere
    stays a count."""
    d = _DAY - timedelta(days=10)
    out = render_scanned_day(d, _data(
        scan=[
            _scan_row("CTEV", "filter:pm_rvol_too_low: pm_rvol=0.4x", gap=34.0),
            _scan_row("SLEEP", "filter:pm_rvol_too_low: pm_rvol=0.2x", gap=12.0),
        ],
        outcomes=[
            _outcome("CTEV", 0.46, 0.31, _NOW),
            _outcome("SLEEP", 0.02, -0.01, _NOW),
        ],
    ), now=_NOW)
    assert "Bulk cuts that ran anyway" in out
    assert "CTEV" in out
    assert "SLEEP" not in out  # went nowhere — stays a count
    assert "   2  pre-market volume below its usual pace" in out


def test_empty_day_says_so_loudly():
    out = render_scanned_day(date(2026, 8, 23), _data(), now=_NOW)
    assert "No scan rows" in out


def test_no_pipe_tables():
    """Telegram cannot render pipe tables — the design constraint."""
    out = render_scanned_day(_DAY, _data(
        scan=[_scan_row("ABCD", "filter:universe_prev_close_too_low: prior close $0.68 < $5.00 floor")],
    ), now=_NOW)
    assert "|" not in out
