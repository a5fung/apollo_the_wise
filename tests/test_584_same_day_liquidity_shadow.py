"""#584 (2026-08-31) — SAME-DAY liquidity read on the universe-floor shadow.

WHY THIS EXISTS. Every liquidity test the live pipeline runs reads YESTERDAY's
numbers (the D-1 floors read snap['prevDay']; the ADV gate's 20-day median
ends at yesterday's close). #570 measured the cost: ~26.5 names/day dropped,
~6/day of which reach tier-A ($50M+) dollar volume ON the gap day — the
fattest-tailed slice in the study AND the worst-crashing. #570's conclusion:
the instrument is a SAME-DAY RE-CHECK, never a lower D-1 floor. #584 extends
the #606 shadow lane (NOT a second recorder — same table, same writer, same
rows) with today's traded volume / price / computed same-day dollar volume in
the same first/at_open/last observation slots. SHADOW ONLY — admission is
unchanged; any live flip is operator sign-off + CHANGE_PROCESS (THE LINE).

MUTATION DISCIPLINE (operator, repeated): every assertion below is on
BEHAVIOUR (the returned dict's values, the exact SQL sent, the wiring source)
— never on a comment or docstring string.
"""
from __future__ import annotations

import inspect
import pathlib
import re
from datetime import date, datetime
from unittest.mock import AsyncMock

import pytest
import yaml

from agents.market_intelligence import universe_floor_shadow as ufs
from agents.market_intelligence import db
from agents.market_intelligence import ep_detector

_PRICE_FLOOR = 5.0
_VOLUME_FLOOR = 50_000
_D = date(2026, 8, 31)


# ── build_universe_floor_shadow_row: the same-day reading (mock-free) ────────


def test_same_day_dollar_volume_is_today_volume_times_today_price():
    """The ninem_detector.py precedent exactly: dollar_volume = today_volume *
    current_price — computed from TODAY's reads, never from prev-day values.
    MUTATION TARGET: computing it off prev_close (the D-1 number this task
    exists to stop being the only read) flips this test — 4.0 * 2_000_000
    != 3.0 * 2_000_000."""
    row = ufs.build_universe_floor_shadow_row(
        "DAIC", 3.0, 10_000, 34.0, _PRICE_FLOOR, _VOLUME_FLOOR, _D,
        minutes_since_open=5, seen_et=datetime(2026, 8, 31, 9, 35),
        today_volume=2_000_000, current_price=4.0)
    assert row["today_volume"] == 2_000_000
    assert row["today_price"] == 4.0
    assert row["today_dollar_volume"] == 4.0 * 2_000_000


def test_same_day_read_missing_yields_none_not_a_fake_zero_fact():
    """No read (volume None, or price 0/None — the snapshot had nothing) must
    store NULL, never a fabricated $0 dollar volume a later sweep would score
    as 'measured illiquid'."""
    row = ufs.build_universe_floor_shadow_row(
        "XXXX", 3.0, 10_000, 20.0, _PRICE_FLOOR, _VOLUME_FLOOR, _D,
        today_volume=None, current_price=4.0)
    assert row["today_volume"] is None
    assert row["today_dollar_volume"] is None

    row = ufs.build_universe_floor_shadow_row(
        "YYYY", 3.0, 10_000, 20.0, _PRICE_FLOOR, _VOLUME_FLOOR, _D,
        today_volume=500_000, current_price=0)
    assert row["today_price"] is None
    assert row["today_dollar_volume"] is None


def test_zero_volume_with_a_price_is_a_real_measured_fact():
    """volume=0 with a live price IS a measurement (nothing traded yet) — it
    must survive as 0.0, not be coerced to NULL (the falsy-zero trap)."""
    row = ufs.build_universe_floor_shadow_row(
        "ZZZZ", 3.0, 10_000, 20.0, _PRICE_FLOOR, _VOLUME_FLOOR, _D,
        today_volume=0, current_price=4.0)
    assert row["today_volume"] == 0
    assert row["today_dollar_volume"] == 0.0


def test_omitting_the_same_day_args_keeps_the_606_row_shape_working():
    """#606 call-compat: the same-day reading is additive — a caller passing
    only the D-1 arguments still gets a valid row (keys present, None)."""
    row = ufs.build_universe_floor_shadow_row(
        "ETON", 20.0, 500_000, 9.5, _PRICE_FLOOR, _VOLUME_FLOOR, _D)
    assert row["today_volume"] is None
    assert row["today_price"] is None
    assert row["today_dollar_volume"] is None
    assert row["failed_price_floor"] is False  # the #606 half is untouched


def test_same_day_keys_store_no_threshold_verdict():
    """#583 class, extended to the same-day family: raw reads only — no
    'cleared the $50M bar' flag; thresholds are a function of today's rule
    set and are swept later from these same rows."""
    row = ufs.build_universe_floor_shadow_row(
        "DAIC", 3.0, 10_000, 34.0, _PRICE_FLOOR, _VOLUME_FLOOR, _D,
        today_volume=2_000_000, current_price=4.0)
    banned = ("passes_", "admit", "verdict", "would_", "cleared", "tier")
    for key in row:
        low = key.lower()
        assert not any(b in low for b in banned), \
            f"column {key!r} looks like a stored verdict against a swept level"


# ── the writer (db.py): slot reconciliation for the same-day columns ─────────


_ROW = {
    "scan_date": _D, "ticker": "DAIC", "seen_et": datetime(2026, 8, 31, 9, 35),
    "gap_pct": 34.0, "minutes_since_open": 5, "prev_close": 3.0, "prev_day_volume": 5_000_000,
    "prev_day_dollar_volume": 15_000_000.0, "failed_price_floor": True,
    "failed_volume_floor": False, "acting_price_floor": 5.0, "acting_volume_floor": 50_000,
    "today_volume": 2_000_000, "today_price": 4.0, "today_dollar_volume": 8_000_000.0,
}


@pytest.mark.asyncio
async def test_writer_binds_the_same_day_reads_into_the_same_single_insert(monkeypatch):
    """One batched INSERT still — the same-day columns ride the existing
    round trip (3 more bind params/row), never a second statement. The
    latency-critical scan gains zero new I/O."""
    from tests.conftest import make_mock_pool
    pool, conn = make_mock_pool()
    executed = []

    async def _executemany(sql, argrows):
        executed.append((sql, argrows))
    conn.executemany = _executemany
    monkeypatch.setattr(db, "get_pool", AsyncMock(return_value=pool))

    n = await db.insert_universe_floor_shadow_rows([_ROW])
    assert n == 1 and len(executed) == 1
    sql, argrows = executed[0]
    for col in ("today_volume_first", "today_volume_at_open", "today_volume_last",
                "today_price_first", "today_price_at_open", "today_price_last",
                "today_dollar_volume_first", "today_dollar_volume_at_open",
                "today_dollar_volume_last"):
        assert col in sql, f"same-day column {col!r} missing from the INSERT"
    # The three same-day values are bound (in the documented $13/$14/$15 order).
    assert argrows[0][-3:] == (2_000_000, 4.0, 8_000_000.0)


def _do_update_sql() -> str:
    src = inspect.getsource(db.insert_universe_floor_shadow_rows)
    return src.split("ON CONFLICT (scan_date, ticker) DO UPDATE SET", 1)[1]


def test_writer_updates_the_last_slot_every_tick():
    upd = _do_update_sql()
    for col in ("today_volume_last", "today_price_last", "today_dollar_volume_last"):
        assert re.search(rf"{col}\s*=\s*EXCLUDED\.{col}", upd), \
            f"{col} must track the most recent tick"


def test_writer_sets_at_open_once_and_only_post_open():
    """The #595 guard, extended to the same-day family: _at_open must be (a)
    COALESCE-guarded so a later tick can never overwrite the first post-open
    read, and (b) gated on minutes_since_open so a pre-market print can never
    masquerade as the at-open liquidity read.
    MUTATION RESULT (verified by hand, 2026-08-31): rewriting
    today_dollar_volume_at_open to the unconditional
    `= EXCLUDED.today_dollar_volume_last` flips exactly this test — the rest
    of the file stays green."""
    upd = _do_update_sql()
    for col in ("today_volume_at_open", "today_price_at_open",
                "today_dollar_volume_at_open"):
        m = re.search(
            rf"{col}\s*=\s*COALESCE\(\s*mi_universe_floor_shadow\.{col}\s*,\s*"
            rf"CASE\s+WHEN\s+EXCLUDED\.minutes_since_open_last\s+IS\s+NOT\s+NULL",
            upd)
        assert m, f"{col} must be set once, first post-open tick only"


def test_ddl_has_the_same_day_columns_and_the_deploy_order_guard():
    """The CREATE TABLE carries the columns for a fresh install; the
    idempotent ALTERs (mi_stock_scores pattern) cover a prod that already
    created the #606-shaped table before this ships — either deploy ordering
    must be correct."""
    db_src = inspect.getsource(db)
    ddl = db_src.split("CREATE TABLE IF NOT EXISTS mi_universe_floor_shadow", 1)[1]
    create_body = ddl.split(");", 1)[0]
    cols = ("today_volume_first", "today_price_first", "today_dollar_volume_first",
            "today_volume_at_open", "today_price_at_open", "today_dollar_volume_at_open",
            "today_volume_last", "today_price_last", "today_dollar_volume_last")
    for col in cols:
        assert col in create_body, f"CREATE TABLE missing {col!r}"
        assert re.search(
            rf"ALTER TABLE mi_universe_floor_shadow ADD COLUMN IF NOT EXISTS {col}\b",
            ddl), f"missing idempotent ALTER guard for {col!r}"


# ── wiring inside run_ep_scan: one lane, three sites, one volume source ──────


def test_all_three_shadow_sites_pass_the_same_day_reading():
    """Both reject branches AND the admitted side must carry the same-day
    read — the comparison population needs it on both sides of the floor.
    MUTATION TARGET: dropping `today_volume=` from any one recording site
    flips this count.

    The three sites route through the `_record_floor_shadow` helper (one
    guarded builder call) rather than repeating the build — so the count to
    pin is the RECORDING sites, not the build sites."""
    src = inspect.getsource(ep_detector.run_ep_scan)
    n_calls = src.count("_record_floor_shadow(") - 1   # minus the def itself
    n_today = src.count("today_volume=_today_vol")
    assert n_calls >= 3, (
        "expected a recording site at the close-floor branch, the volume-floor "
        "branch, and the admitted-candidate site")
    assert n_today == n_calls, (
        f"{n_calls} shadow recording sites but only {n_today} pass the same-day "
        f"volume — a site without it silently records a name as unread")
    assert src.count("current_price=current_price") >= n_calls
    # And the helper must actually forward both to the builder, or every site
    # above would pass them into a black hole.
    build = src[src.index("build_universe_floor_shadow_row("):]
    assert "today_volume=today_volume" in build[:400]
    assert "current_price=current_price" in build[:400]


def test_today_volume_is_single_sourced_with_the_live_pipeline():
    """Anti-drift pin: the shadow's 'today volume' and the live pipeline's
    volume must be the SAME expression. _snap_candidate (live) and the scan
    loop (shadow) both read via _snap_today_volume — two hand-synced copies
    of `day.v or min.av` is the #260 class this forbids."""
    assert "_snap_today_volume(snap)" in inspect.getsource(ep_detector._snap_candidate)
    assert "_snap_today_volume(snap)" in inspect.getsource(ep_detector.run_ep_scan)
    # The expression itself lives in exactly one function.
    snap_reads = inspect.getsource(ep_detector).count('.get("day", {}).get("v", 0) or')
    assert snap_reads == 1, "today-volume expression duplicated — single-source it"


def test_snap_today_volume_prefers_session_volume_then_accumulated():
    assert ep_detector._snap_today_volume(
        {"day": {"v": 123}, "min": {"av": 456}}) == 123
    assert ep_detector._snap_today_volume({"day": {}, "min": {"av": 456}}) == 456
    assert ep_detector._snap_today_volume({}) == 0


# ── the settle-forward half: review registration (data_gated_reviews.yaml) ───


def _review() -> dict:
    reg = yaml.safe_load(pathlib.Path("data_gated_reviews.yaml").read_text())["reviews"]
    matches = [r for r in reg if r["review_id"] == "same_day_liquidity_recheck_584"]
    assert len(matches) == 1
    return matches[0]


def test_review_gates_on_rejected_side_rows_with_a_post_open_read():
    """The review must accrue on the population the re-check would act on —
    D-1-REJECTED names with a post-open same-day read — not on the admitted
    side, which accrues trivially every day."""
    r = _review()
    sql = r["predicate_sql"]
    assert "failed_price_floor OR failed_volume_floor" in sql
    assert "today_dollar_volume_at_open IS NOT NULL" in sql
    assert isinstance(r["threshold"], int) and r["threshold"] >= 15
    assert r["kind"] == "accrual"
    assert r["discriminates_on"] == []  # declared, with the both-sides rationale in-file


def test_review_action_settles_forward_honestly():
    """The stated action must harvest outcomes (mi_daily_closes join), label
    peaks as excursions never returns, and route any proposal through the
    operator — the honesty rules the rest of the codebase runs on."""
    action = _review()["action_when_ready"]
    assert "mi_daily_closes" in action
    assert "excursion" in action
    assert "CHANGE_PROCESS" in action
