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



# ─────────────────────────────────────────────────────────────────────────────────────────
# #727 (a) — the sector arm can never empty a theme, and his promotions get 3 nights
# ─────────────────────────────────────────────────────────────────────────────────────────
#
# Prod, 2026-11-03 (audit id 66326) and 11-05 (id 69172): his 11-02 promotion 'Home Pest Control &
# Lawn/Garden Residential Services' (ROL Consumer Cyclical / RTO Industrials / SMG Basic Materials)
# lost all three members on its first engine night. In a small theme where every member carries a
# different sector, every member is "the odd one out", so the arm removed the whole theme.

from datetime import date  # noqa: E402

PEST = "Home Pest Control & Lawn/Garden Residential Services"
PEST_SECTORS = {
    "ROL": {"sector": "Consumer Cyclical"},
    "RTO": {"sector": "Industrials"},
    "SMG": {"sector": "Basic Materials"},
}
FLOOR_EVENT = "theme_sector_filter_floor_kept"
EXEMPT_EVENT = "theme_sector_filter_operator_exempt"
STRIP_EVENT = "theme_carryforward_filter_stripped"


def test_727_the_event_names_are_the_registered_constants():
    from agents.market_intelligence import audit_events
    assert audit_events.THEME_SECTOR_FILTER_FLOOR_KEPT == FLOOR_EVENT
    assert audit_events.THEME_SECTOR_FILTER_OPERATOR_EXEMPT == EXEMPT_EVENT


def _audit(monkeypatch):
    rows: list[tuple[str, str, str]] = []

    async def fake_audit(event_type, summary=None, detail=None):
        rows.append((event_type, summary or "", detail or ""))

    monkeypatch.setattr(theme_engine, "log_audit_event", fake_audit)
    return rows


def _pest():
    return [{"name": PEST, "tickers": ["ROL", "RTO", "SMG"], "score": 60.0, "stage": "Nascent"}]


@pytest.mark.asyncio
async def test_727_three_members_three_sectors_survive(monkeypatch):
    """THE PROD CASE: nobody is the odd one out when everybody is. The theme is kept whole and
    ONE floor row names what the arm would have removed; no strip row is written."""
    rows = _audit(monkeypatch)
    themes = _pest()

    stripped = await theme_engine._apply_carryforward_deterministic_filter(
        themes, set(), set(), PEST_SECTORS,
    )

    assert stripped == 0
    assert themes[0]["tickers"] == ["ROL", "RTO", "SMG"]
    kept = [r for r in rows if r[0] == FLOOR_EVENT]
    assert len(kept) == 1
    assert PEST in kept[0][1]
    for t in ("ROL", "RTO", "SMG"):
        assert t in kept[0][2]
    assert not [r for r in rows if r[0] == STRIP_EVENT]


@pytest.mark.asyncio
async def test_727_survives_when_the_tape_rejects_every_member(monkeypatch):
    """Same shape with the co-movement test ON and saying no to all three (`comove_below_bar`
    starts from the same singleton label, so it is the same arm and the same floor)."""
    rows = _audit(monkeypatch)
    monkeypatch.setattr(
        theme_engine, "_comove_verdict",
        lambda t, members, ctx: theme_engine.ComoveVerdict(
            admit=False, corr=0.1, overlap=60, basket_n=2, reason="below_bar"))
    themes = _pest()

    stripped = await theme_engine._apply_carryforward_deterministic_filter(
        themes, set(), set(), PEST_SECTORS, comove_ctx=object(),
    )

    assert stripped == 0
    assert themes[0]["tickers"] == ["ROL", "RTO", "SMG"]
    assert len([r for r in rows if r[0] == FLOOR_EVENT]) == 1


@pytest.mark.asyncio
async def test_727_two_known_sectors_and_an_unknown_survive(monkeypatch):
    """A / B / Unknown: the arm would leave ONE member — under the floor, so nothing is removed."""
    rows = _audit(monkeypatch)
    themes = [{"name": "T", "tickers": ["A", "B", "U"]}]
    stocks = {"A": {"sector": "Tech"}, "B": {"sector": "Energy"}}

    stripped = await theme_engine._apply_carryforward_deterministic_filter(themes, set(), set(), stocks)

    assert stripped == 0 and themes[0]["tickers"] == ["A", "B", "U"]
    assert len([r for r in rows if r[0] == FLOOR_EVENT]) == 1


@pytest.mark.asyncio
async def test_727_a_clear_majority_still_loses_its_true_outlier(monkeypatch):
    """The filter's purpose is intact, down to the smallest theme it runs on: 2 + 1 loses the 1
    (2 survive = the engine's floor) and no floor row is written."""
    rows = _audit(monkeypatch)
    themes = [{"name": "Chips", "tickers": ["NVDA", "AMD", "JPM"]}]
    stocks = {"NVDA": {"sector": "Technology"}, "AMD": {"sector": "Technology"},
              "JPM": {"sector": "Financial Services"}}

    stripped = await theme_engine._apply_carryforward_deterministic_filter(themes, set(), set(), stocks)

    assert stripped == 1 and themes[0]["tickers"] == ["NVDA", "AMD"]
    assert [r[0] for r in rows] == [STRIP_EVENT]


@pytest.mark.asyncio
async def test_727_the_floor_counts_what_the_hard_arms_leave(monkeypatch):
    """4 members: one banned, one true outlier, a majority of two. Banned goes; the outlier would
    leave 2 = the floor, so it goes too. Then the same theme with TWO banned: the sector strip would
    leave 1, so the sector arm stands down — the ban still applies."""
    rows = _audit(monkeypatch)
    stocks = {"A": {"sector": "Tech"}, "B": {"sector": "Tech"}, "C": {"sector": "Tech"},
              "X": {"sector": "Energy"}}
    themes = [{"name": "T", "tickers": ["A", "B", "C", "X"]}]
    assert await theme_engine._apply_carryforward_deterministic_filter(themes, {"C"}, set(), stocks) == 2
    assert themes[0]["tickers"] == ["A", "B"]

    rows.clear()
    themes = [{"name": "T", "tickers": ["A", "B", "C", "X"]}]
    assert await theme_engine._apply_carryforward_deterministic_filter(themes, {"B", "C"}, set(), stocks) == 2
    assert themes[0]["tickers"] == ["A", "X"]
    assert len([r for r in rows if r[0] == FLOOR_EVENT]) == 1
    strip = [r for r in rows if r[0] == STRIP_EVENT]
    assert len(strip) == 1 and "sector_outlier" not in strip[0][2]


@pytest.mark.asyncio
async def test_727_hard_arms_can_still_empty_a_theme(monkeypatch):
    """The floor guards the SECTOR arm only: banned / cooldown / deal-pinned still strip to zero."""
    _audit(monkeypatch)
    themes = _pest()
    stripped = await theme_engine._apply_carryforward_deterministic_filter(
        themes, {"ROL", "RTO", "SMG"}, set(), PEST_SECTORS)
    assert stripped == 3 and themes[0]["tickers"] == []


def _promoted_theme():
    # A clear majority + one true outlier: OUTSIDE the window this loses JPM, so the exemption
    # (not the floor) is what a kept JPM proves.
    return [{"name": PEST, "tickers": ["NVDA", "AMD", "INTC", "JPM"]}]


PROMO_STOCKS = {"NVDA": {"sector": "Technology"}, "AMD": {"sector": "Technology"},
                "INTC": {"sector": "Technology"}, "JPM": {"sector": "Financial Services"}}


def _exempt(nights_left):
    return theme_engine.OperatorExempt(nights_left=nights_left)


@pytest.mark.asyncio
async def test_727_a_promoted_theme_inside_its_window_is_untouched(monkeypatch):
    rows = _audit(monkeypatch)
    themes = _promoted_theme()
    exempt = _exempt({PEST: 3})

    stripped = await theme_engine._apply_carryforward_deterministic_filter(
        themes, set(), set(), PROMO_STOCKS, operator_exempt=exempt)

    assert stripped == 0 and themes[0]["tickers"] == ["NVDA", "AMD", "INTC", "JPM"]
    ex = [r for r in rows if r[0] == EXEMPT_EVENT]
    assert len(ex) == 1 and PEST in ex[0][1] and "night 1 of 3" in ex[0][1] and "JPM" in ex[0][2]
    assert not [r for r in rows if r[0] in (STRIP_EVENT, FLOOR_EVENT)]
    # Pass 1.5's own once-per-run written-set is NOT used up by this row.
    assert exempt.logged == set()


@pytest.mark.asyncio
async def test_727_a_promoted_theme_with_nothing_to_strip_writes_no_row(monkeypatch):
    rows = _audit(monkeypatch)
    themes = [{"name": PEST, "tickers": ["NVDA", "AMD", "INTC"]}]
    await theme_engine._apply_carryforward_deterministic_filter(
        themes, set(), set(), PROMO_STOCKS, operator_exempt=_exempt({PEST: 2}))
    assert rows == []


@pytest.mark.asyncio
async def test_727_a_promoted_theme_still_loses_a_banned_member(monkeypatch):
    """Only the sector arm is exempt — a ban, a cooldown or a deal pin still applies to his theme."""
    rows = _audit(monkeypatch)
    themes = _promoted_theme()

    stripped = await theme_engine._apply_carryforward_deterministic_filter(
        themes, {"AMD"}, set(), PROMO_STOCKS, operator_exempt=_exempt({PEST: 1}))

    assert stripped == 1 and themes[0]["tickers"] == ["NVDA", "INTC", "JPM"]
    assert len([r for r in rows if r[0] == EXEMPT_EVENT]) == 1


@pytest.mark.asyncio
async def test_727_nights_1_to_3_exempt_and_night_4_filtered_normally(monkeypatch):
    """Driven through the SAME window helper Pass 1.5 uses (`_operator_exempt_nights_left`): his
    Mon 11-02 promotion is untouched on engine nights 11-03 / 11-04 / 11-05 and filtered on 11-06."""
    rows = _audit(monkeypatch)
    mon, tue, wed, thu, fri = (date(2026, 11, d) for d in (2, 3, 4, 5, 6))
    promos = [(theme_engine._OPERATOR_PROMOTED_SUMMARY.format(name=PEST, n=4), mon)]
    nights = [mon, tue, wed, thu, fri]

    for k, today in enumerate((tue, wed, thu), start=1):
        rows.clear()
        themes = _promoted_theme()
        exempt = _exempt(theme_engine._operator_exempt_nights_left(promos, nights, today))
        assert await theme_engine._apply_carryforward_deterministic_filter(
            themes, set(), set(), PROMO_STOCKS, operator_exempt=exempt) == 0
        assert "JPM" in themes[0]["tickers"]
        assert f"night {k} of 3" in rows[0][1]

    rows.clear()
    themes = _promoted_theme()
    exempt = _exempt(theme_engine._operator_exempt_nights_left(promos, nights, fri))
    assert exempt.nights_left == {}
    assert await theme_engine._apply_carryforward_deterministic_filter(
        themes, set(), set(), PROMO_STOCKS, operator_exempt=exempt) == 1
    assert themes[0]["tickers"] == ["NVDA", "AMD", "INTC"]
    assert [r[0] for r in rows] == [STRIP_EVENT]


def test_727_the_nightly_hands_the_filter_the_runs_one_exemption_set():
    """Wiring: the nightly's filter call passes `operator_exempt=`, and the exemption set is read
    ONCE per run, before the filter (a second read = a second query and a duplicate error row)."""
    # source-pin-ok: wiring — a correct filter the nightly never hands the exemption set is the failure; exercising it means running the whole nightly (LLM + DB)
    import ast
    import inspect
    tree = ast.parse(inspect.getsource(theme_engine))
    calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)]
    filt = [c for c in calls if c.func.id == "_apply_carryforward_deterministic_filter"]
    assert filt and all("operator_exempt" in {k.arg for k in c.keywords} for c in filt)
    loads = [c for c in calls if c.func.id == "_load_operator_exempt"]
    assert len(loads) == 1
    assert loads[0].lineno < min(c.lineno for c in filt)
