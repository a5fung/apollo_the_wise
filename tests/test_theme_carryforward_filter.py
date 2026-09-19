"""Tests for _apply_carryforward_deterministic_filter (2026-05-15).

Regression: the 4 oncology biotechs (RVMD/AVBP/DAWN/AJRD) cycling through
Satellite-named themes for ~3 weeks despite Fix B global ban + validation
cooldowns. Filter closes the adds/removes asymmetry: deterministic removes
(banned/cooldown/outlier) now run daily against carryforward members.

Critical invariant under test: STRIP-ONLY behavior. Themes with 0 members
after strip must PERSIST in the list (not retired). Retirement is handled
by the existing post-assignment logic so assignment LLM gets a chance to
refill the theme.
"""
from __future__ import annotations

import pytest

from agents.market_intelligence import theme_engine


@pytest.mark.asyncio
async def test_strips_all_banned_members_does_not_retire(monkeypatch):
    """SATELLITE BIOTECH CASE: a theme with 4 banned members should have all
    4 stripped, but the theme MUST persist in the list (zero members) so
    assignment LLM can refill it in the same run."""
    audit_calls: list[tuple[str, str]] = []

    async def fake_audit(event_type, summary, detail=None):
        audit_calls.append((event_type, summary))

    monkeypatch.setattr(theme_engine, "log_audit_event", fake_audit)

    themes = [
        {
            "name": "Satellite Earth Observation & Geospatial Intelligence",
            "tickers": ["RVMD", "AVBP", "DAWN", "AJRD"],
            "score": 79.5,
            "stage": "Mainstream",
        },
    ]
    globally_banned = {"RVMD", "AVBP", "DAWN", "AJRD"}
    cooldown_set: set[tuple[str, str]] = set()
    stocks_by_ticker: dict = {}

    stripped = await theme_engine._apply_carryforward_deterministic_filter(
        themes, globally_banned, cooldown_set, stocks_by_ticker,
    )

    assert stripped == 4
    # Theme still in the list (NOT retired) — critical retire-deferral
    assert len(themes) == 1
    # All members stripped
    assert themes[0]["tickers"] == []
    # Audit event fired
    assert any(e[0] == "theme_carryforward_filter_stripped" for e in audit_calls)


@pytest.mark.asyncio
async def test_partial_strip_preserves_other_members(monkeypatch):
    """Theme with mixed members: only banned/cooldown should be stripped."""
    async def fake_audit(*a, **kw): pass
    monkeypatch.setattr(theme_engine, "log_audit_event", fake_audit)

    themes = [
        {
            "name": "AI Memory & Storage",
            "tickers": ["MU", "SNDK", "WDC", "BANNED_X", "STX"],
            "score": 80.0,
            "stage": "Mainstream",
        },
    ]
    globally_banned = {"BANNED_X"}
    cooldown_set: set[tuple[str, str]] = set()
    stocks_by_ticker: dict = {}

    stripped = await theme_engine._apply_carryforward_deterministic_filter(
        themes, globally_banned, cooldown_set, stocks_by_ticker,
    )

    assert stripped == 1
    assert "BANNED_X" not in themes[0]["tickers"]
    # Other members preserved
    assert {"MU", "SNDK", "WDC", "STX"}.issubset(set(themes[0]["tickers"]))


@pytest.mark.asyncio
async def test_cooldown_pair_strip(monkeypatch):
    """(ticker, theme_name) cooldown should strip even if ticker not globally banned."""
    async def fake_audit(*a, **kw): pass
    monkeypatch.setattr(theme_engine, "log_audit_event", fake_audit)

    themes = [
        {
            "name": "Theme A",
            "tickers": ["X", "Y", "Z"],
            "score": 70.0,
            "stage": "Accelerating",
        },
        {
            "name": "Theme B",
            "tickers": ["X", "W"],
            "score": 70.0,
            "stage": "Accelerating",
        },
    ]
    globally_banned: set[str] = set()
    # X is cooled-down only for Theme A, not Theme B
    cooldown_set = {("X", "Theme A")}
    stocks_by_ticker: dict = {}

    stripped = await theme_engine._apply_carryforward_deterministic_filter(
        themes, globally_banned, cooldown_set, stocks_by_ticker,
    )

    assert stripped == 1
    assert themes[0]["tickers"] == ["Y", "Z"]  # X stripped from Theme A
    assert "X" in themes[1]["tickers"]          # X remains in Theme B


@pytest.mark.asyncio
async def test_sector_outlier_strip(monkeypatch):
    """Singleton-sector members in a ≥3 member theme should be stripped."""
    async def fake_audit(*a, **kw): pass
    monkeypatch.setattr(theme_engine, "log_audit_event", fake_audit)

    themes = [
        {
            "name": "Semiconductors",
            "tickers": ["NVDA", "AMD", "INTC", "JPM"],  # JPM is the outlier
            "score": 75.0,
            "stage": "Mainstream",
        },
    ]
    stocks_by_ticker = {
        "NVDA": {"sector": "Technology"},
        "AMD": {"sector": "Technology"},
        "INTC": {"sector": "Technology"},
        "JPM": {"sector": "Financial Services"},
    }

    stripped = await theme_engine._apply_carryforward_deterministic_filter(
        themes, set(), set(), stocks_by_ticker,
    )

    assert stripped == 1
    assert "JPM" not in themes[0]["tickers"]
    assert set(themes[0]["tickers"]) == {"NVDA", "AMD", "INTC"}


@pytest.mark.asyncio
async def test_noop_when_no_violations(monkeypatch):
    """Clean theme: no strips, no audit events."""
    audit_calls: list = []

    async def fake_audit(*a, **kw):
        audit_calls.append(a)

    monkeypatch.setattr(theme_engine, "log_audit_event", fake_audit)

    themes = [
        {
            "name": "Clean Theme",
            "tickers": ["A", "B", "C"],
            "score": 70.0,
            "stage": "Accelerating",
        },
    ]
    stocks_by_ticker = {
        "A": {"sector": "Tech"},
        "B": {"sector": "Tech"},
        "C": {"sector": "Tech"},
    }

    stripped = await theme_engine._apply_carryforward_deterministic_filter(
        themes, set(), set(), stocks_by_ticker,
    )

    assert stripped == 0
    assert themes[0]["tickers"] == ["A", "B", "C"]
    assert len(audit_calls) == 0


@pytest.mark.asyncio
async def test_sector_outlier_skipped_for_small_themes(monkeypatch):
    """Themes with <3 members don't trigger sector outlier strip
    (insufficient data to define a majority)."""
    async def fake_audit(*a, **kw): pass
    monkeypatch.setattr(theme_engine, "log_audit_event", fake_audit)

    themes = [
        {
            "name": "Small Theme",
            "tickers": ["NVDA", "JPM"],
            "score": 70.0,
            "stage": "Nascent",
        },
    ]
    stocks_by_ticker = {
        "NVDA": {"sector": "Technology"},
        "JPM": {"sector": "Financial Services"},
    }

    stripped = await theme_engine._apply_carryforward_deterministic_filter(
        themes, set(), set(), stocks_by_ticker,
    )

    assert stripped == 0
    assert set(themes[0]["tickers"]) == {"NVDA", "JPM"}


# ─────────────────────────────────────────────────────────────────────────────────────────
# ARM 4 (#671) — a BOUGHT-OUT name must leave the themes it is ALREADY in
# ─────────────────────────────────────────────────────────────────────────────────────────
#
# Found by an expectation that was WRONG. #671 filtered deal-pinned names out of all six RS
# pools on 2026-09-17 and predicted CBZ would therefore LEAVE `Management & Business Advisory
# Consulting Firms`. It did not, and could not: the pools gate what ENTERS discovery and
# assignment, while an existing roster is carried forward through this function — which had no
# deal-pin arm at all. Measured on 2026-09-18: 54 names deal-pinned, ZERO in any pool, and four
# still sitting inside themes (CBZ, TECH, SAFT, UTZ).
#
# The real shape, from prod: CBZ traded a 0.15–0.33% daily range at 54.60 every session after a
# 17.6% gap on 24.1x volume — a cash deal price. HURN, in the same two-member theme, ranged
# 2.3–4.6% a day and rose 147.64 -> 158.33. One is pinned, one is a live stock, and the theme
# must end up `{HURN}`.


def _pin(monkeypatch, pinned, *, calls=None, boom=False):
    """Stub the classifier. `calls` collects each invocation so a test can assert the query
    happens ONCE for every theme rather than once per theme."""
    import agents.market_intelligence.db as dbmod

    async def fake(as_of, tickers=None, **kw):
        if calls is not None:
            calls.append(tuple(tickers or ()))
        if boom:
            raise RuntimeError("classifier down")
        return {t for t in (tickers or ()) if t in pinned}

    monkeypatch.setattr(dbmod, "get_deal_pinned_tickers", fake)


def _themes():
    return [
        {"name": "Management & Business Advisory Consulting Firms",
         "tickers": ["CBZ", "HURN"], "score": 61.0, "stage": "Mainstream"},
        {"name": "Emerging Medical Device Innovators Breakout",
         "tickers": ["ITGR", "ATEC", "INSP"], "score": 55.0, "stage": "Fading"},
    ]


@pytest.mark.asyncio
async def test_a_deal_pinned_member_is_stripped_and_a_live_one_is_not(monkeypatch):
    """The real 2026-09-18 board. MUTATION: dropping `pinned_hits` from `to_remove` leaves CBZ
    in and reddens this — verified before commit."""
    async def fake_audit(*a, **kw): pass
    monkeypatch.setattr(theme_engine, "log_audit_event", fake_audit)
    _pin(monkeypatch, {"CBZ"})
    themes = _themes()

    stripped = await theme_engine._apply_carryforward_deterministic_filter(
        themes, set(), set(), {}, as_of="2026-09-18")

    assert stripped == 1
    assert themes[0]["tickers"] == ["HURN"], (
        "CBZ is pinned at a cash deal price and must leave; HURN is a live stock and must stay")
    assert themes[1]["tickers"] == ["ITGR", "ATEC", "INSP"], (
        "ITGR is NOT deal-pinned — it fails the volume bar at 6.0x against 10x — so this theme "
        "is the over-removal control and must be untouched")


@pytest.mark.asyncio
async def test_without_a_date_the_arm_does_not_run_at_all(monkeypatch):
    """`as_of=None` is the pre-change path byte-for-byte. Without this, adding the arm would
    silently change every existing caller and test."""
    async def fake_audit(*a, **kw): pass
    monkeypatch.setattr(theme_engine, "log_audit_event", fake_audit)
    called = []
    _pin(monkeypatch, {"CBZ"}, calls=called)
    themes = _themes()

    stripped = await theme_engine._apply_carryforward_deterministic_filter(
        themes, set(), set(), {})

    assert stripped == 0
    assert called == [], "the classifier was queried with no date supplied"
    assert themes[0]["tickers"] == ["CBZ", "HURN"]


@pytest.mark.asyncio
async def test_the_classifier_is_queried_ONCE_for_every_theme(monkeypatch):
    """Cost, not correctness — and it is the mistake that would actually have been made. The
    board carries ~130 themes a night; querying per theme is 130 scans for one answer."""
    async def fake_audit(*a, **kw): pass
    monkeypatch.setattr(theme_engine, "log_audit_event", fake_audit)
    called = []
    _pin(monkeypatch, {"CBZ"}, calls=called)

    await theme_engine._apply_carryforward_deterministic_filter(
        _themes(), set(), set(), {}, as_of="2026-09-18")

    assert len(called) == 1, f"the pin classifier ran {len(called)} times, expected 1"
    assert set(called[0]) == {"CBZ", "HURN", "ITGR", "ATEC", "INSP"}, (
        "the single query must cover every theme's members")


@pytest.mark.asyncio
async def test_a_classifier_failure_keeps_members_and_does_not_stop_the_nightly(monkeypatch):
    """Fail SAFE toward KEEPING. A missed strip is a name lingering one more night; an
    exception here would take down the whole theme run, which is the 2026-09-18 class of
    damage this task exists to stop.

    MUTATION: removing the try/except propagates RuntimeError and reddens this."""
    async def fake_audit(*a, **kw): pass
    monkeypatch.setattr(theme_engine, "log_audit_event", fake_audit)
    _pin(monkeypatch, {"CBZ"}, boom=True)
    themes = _themes()

    stripped = await theme_engine._apply_carryforward_deterministic_filter(
        themes, set(), set(), {}, as_of="2026-09-18")

    assert stripped == 0
    assert themes[0]["tickers"] == ["CBZ", "HURN"], "a classifier outage must not strip anything"


@pytest.mark.asyncio
async def test_the_strip_reason_names_the_tickers(monkeypatch):
    """The audit row has to say WHICH names and WHY, or the next person reads a count and has
    to re-derive the set — the exact failure this week kept producing."""
    seen = []

    async def fake_audit(event_type, summary=None, detail=None):
        seen.append((event_type, summary or "", detail or ""))

    monkeypatch.setattr(theme_engine, "log_audit_event", fake_audit)
    _pin(monkeypatch, {"CBZ"})

    await theme_engine._apply_carryforward_deterministic_filter(
        _themes(), set(), set(), {}, as_of="2026-09-18")

    rows = [r for r in seen if r[0] == "theme_carryforward_filter_stripped"]
    assert rows, "no audit row for the strip"
    assert "deal_pinned" in rows[0][2] and "CBZ" in rows[0][2], (
        f"the reason must name the arm and the ticker; got {rows[0][2]!r}")
