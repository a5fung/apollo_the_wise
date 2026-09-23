"""Large-cap rel_volume floor SHADOW observer (operator shadow-approved 2026-07-19).

data_gated_reviews.yaml `large_cap_relvol_floor_shadow_evidence` — forward-tracking
successor to the retrospective `rel_volume_large_cap_floor_evidence` review (large-cap,
ADV$ >= $50M, HIGH EP alerts with rel_volume < 0.5 at alert time underperformed sharply
vs. the >=0.5 control on entry-aware mi_live_trades evidence).

THE LINE: `_emit_large_cap_relvol_floor_shadow` is AUDIT-ONLY. It must NEVER mutate the
`r` dict, never touch score_tier/grade/entry, and never skip the alert — it only writes
ONE `filter:large_cap_relvol_floor_shadow` mi_audit_log row observing that a (separate,
future, operator-signed) LIVE floor would have skipped this entry.

Coverage:
  • fires with all captured fields when HIGH + ADV$ >= $50M + rel_volume < 0.5
  • does NOT fire: rel_volume >= 0.5, ADV$ < $50M, non-HIGH tier, flag OFF, missing inputs
  • dedup: one event per (ticker, alert_date) even across repeated 5-min-tick calls
  • never mutates `r` (THE LINE pin, mirrors test_structure_axis_shadow's zero-mutation test)
  • never raises (swallows internally; a synthetic exception path still doesn't propagate)
"""
from __future__ import annotations

import asyncio
import copy
import json
from datetime import date, datetime
from unittest.mock import AsyncMock
from zoneinfo import ZoneInfo

from agents.market_intelligence import ep_detector
from agents.market_intelligence.ep_detector import _emit_large_cap_relvol_floor_shadow

_ET = ZoneInfo("America/New_York")


def _run(coro):
    return asyncio.run(coro)


def _base_r(**overrides) -> dict:
    r = {
        "ticker": "LCAP",
        "alert_date": date(2026, 7, 20),
        "score_tier": "HIGH",
        "adv": 2_000_000.0,       # shares (mi_stock_scores.adv_20)
        # PRE-GAP price (matches mi_stock_scores.close / the retrospective + predicate_sql
        # definition of large-cap) — NOT current_price (today's already-gapped price would
        # run ADV$ hot by the gap size and admit names the retrospective set excluded).
        "prev_close": 30.0,       # ADV$ = 2,000,000 * 30 = $60,000,000 >= $50M
        "current_price": 33.75,  # +12.5% gapped price — deliberately DIFFERENT from
                                 # prev_close so a test regressing to current_price fails.
        "rel_volume": 0.30,       # < 0.5
        "gap_pct": 12.5,
    }
    r.update(overrides)
    return r


def _reset_dedupe():
    ep_detector._audit_dedupe = set()
    ep_detector._audit_dedupe_date = None


def _now_et(hour=9, minute=40) -> datetime:
    return datetime(2026, 7, 20, hour, minute, tzinfo=_ET)


# ─── Fires + captures all fields ────────────────────────────────────────────────────────

def test_fires_with_all_fields_when_high_largecap_low_relvol(monkeypatch):
    _reset_dedupe()
    monkeypatch.setenv("LARGE_CAP_RELVOL_FLOOR_SHADOW_ENABLED", "true")
    audit = AsyncMock()
    monkeypatch.setattr(ep_detector, "log_audit_event", audit)

    r = _base_r()
    _run(_emit_large_cap_relvol_floor_shadow(r, _now_et(9, 40)))

    assert audit.await_count == 1
    (event_type, summary, detail), _ = audit.call_args
    assert event_type == "filter:large_cap_relvol_floor_shadow"
    assert "LCAP" in summary
    assert "not skipped" in summary.lower() or "not skip" in summary.lower()

    payload = json.loads(detail)
    assert payload["ticker"] == "LCAP"
    assert payload["alert_date"] == "2026-07-20"
    assert payload["rel_volume"] == 0.30
    assert payload["adv_dollar"] == 60_000_000.0
    assert payload["adv_20"] == 2_000_000.0
    assert payload["prev_close"] == 30.0  # pre-gap basis, NOT current_price (33.75)
    assert payload["alert_timestamp_et"] == _now_et(9, 40).isoformat()
    assert payload["alert_time_et"] == "09:40"
    assert payload["score_tier"] == "HIGH"
    assert payload["gap_pct"] == 12.5


# ─── Non-firing branches ────────────────────────────────────────────────────────────────

def test_no_event_when_rel_volume_at_or_above_half(monkeypatch):
    _reset_dedupe()
    monkeypatch.setenv("LARGE_CAP_RELVOL_FLOOR_SHADOW_ENABLED", "true")
    audit = AsyncMock()
    monkeypatch.setattr(ep_detector, "log_audit_event", audit)

    r = _base_r(rel_volume=0.5)  # exactly at the floor -> control cohort, not the shadow cohort
    _run(_emit_large_cap_relvol_floor_shadow(r, _now_et()))
    assert audit.await_count == 0

    r2 = _base_r(rel_volume=1.2)
    _run(_emit_large_cap_relvol_floor_shadow(r2, _now_et()))
    assert audit.await_count == 0


def test_no_event_when_small_cap(monkeypatch):
    """ADV$ = 500,000 shares * $20 prev_close = $10M < $50M large-cap floor."""
    _reset_dedupe()
    monkeypatch.setenv("LARGE_CAP_RELVOL_FLOOR_SHADOW_ENABLED", "true")
    audit = AsyncMock()
    monkeypatch.setattr(ep_detector, "log_audit_event", audit)

    r = _base_r(adv=500_000.0, prev_close=20.0)
    _run(_emit_large_cap_relvol_floor_shadow(r, _now_et()))
    assert audit.await_count == 0


def test_uses_prev_close_not_current_price_for_adv_dollar(monkeypatch):
    """Regression pin for the advisor-flagged methodology-drift fix: ADV$ must use the
    PRE-GAP prev_close (matching mi_stock_scores.close / the retrospective evidence +
    this review's own predicate_sql), not current_price (today's already-gapped price,
    which would run every ADV$ figure hot by the gap size and admit names the
    retrospective cohort would have excluded)."""
    _reset_dedupe()
    monkeypatch.setenv("LARGE_CAP_RELVOL_FLOOR_SHADOW_ENABLED", "true")
    audit = AsyncMock()
    monkeypatch.setattr(ep_detector, "log_audit_event", audit)

    # prev_close puts ADV$ just BELOW $50M; current_price (gapped up) would put it just
    # ABOVE — if the code used current_price this would wrongly fire.
    r = _base_r(adv=2_000_000.0, prev_close=24.9, current_price=33.0, gap_pct=32.5)
    _run(_emit_large_cap_relvol_floor_shadow(r, _now_et()))
    assert audit.await_count == 0  # ADV$ = 2,000,000 * 24.9 = $49.8M < $50M -> no event


def test_no_event_when_not_high_tier(monkeypatch):
    _reset_dedupe()
    monkeypatch.setenv("LARGE_CAP_RELVOL_FLOOR_SHADOW_ENABLED", "true")
    audit = AsyncMock()
    monkeypatch.setattr(ep_detector, "log_audit_event", audit)

    for tier in ("MODERATE", None, "", "high"):  # case-sensitive, exact 'HIGH' only
        r = _base_r(score_tier=tier)
        _run(_emit_large_cap_relvol_floor_shadow(r, _now_et()))
    assert audit.await_count == 0


def test_no_event_when_flag_off(monkeypatch):
    _reset_dedupe()
    monkeypatch.setenv("LARGE_CAP_RELVOL_FLOOR_SHADOW_ENABLED", "false")
    audit = AsyncMock()
    monkeypatch.setattr(ep_detector, "log_audit_event", audit)

    r = _base_r()
    _run(_emit_large_cap_relvol_floor_shadow(r, _now_et()))
    assert audit.await_count == 0


def test_flag_defaults_on_when_unset(monkeypatch):
    """Default ON — audit-only, safe to default-on (mirrors ENRICH_SHADOW_ENABLED)."""
    _reset_dedupe()
    monkeypatch.delenv("LARGE_CAP_RELVOL_FLOOR_SHADOW_ENABLED", raising=False)
    audit = AsyncMock()
    monkeypatch.setattr(ep_detector, "log_audit_event", audit)

    r = _base_r()
    _run(_emit_large_cap_relvol_floor_shadow(r, _now_et()))
    assert audit.await_count == 1


def test_no_event_on_missing_inputs(monkeypatch):
    """adv/prev_close/rel_volume unavailable (e.g. ADV fetch failed) -> fail-closed to
    NO shadow event rather than guessing; must not raise."""
    _reset_dedupe()
    monkeypatch.setenv("LARGE_CAP_RELVOL_FLOOR_SHADOW_ENABLED", "true")
    audit = AsyncMock()
    monkeypatch.setattr(ep_detector, "log_audit_event", audit)

    for missing in ("adv", "prev_close", "rel_volume"):
        r = _base_r(**{missing: None})
        _run(_emit_large_cap_relvol_floor_shadow(r, _now_et()))
    assert audit.await_count == 0


# ─── Dedup across repeated 5-min-tick calls ─────────────────────────────────────────────

def test_dedupe_one_event_per_ticker_per_day(monkeypatch):
    _reset_dedupe()
    monkeypatch.setenv("LARGE_CAP_RELVOL_FLOOR_SHADOW_ENABLED", "true")
    audit = AsyncMock()
    monkeypatch.setattr(ep_detector, "log_audit_event", audit)

    r = _base_r()
    _run(_emit_large_cap_relvol_floor_shadow(r, _now_et(9, 35)))
    _run(_emit_large_cap_relvol_floor_shadow(r, _now_et(9, 40)))  # next scan tick, same ticker/day
    _run(_emit_large_cap_relvol_floor_shadow(r, _now_et(9, 45)))

    assert audit.await_count == 1  # not 3


def test_dedupe_is_per_ticker_not_global(monkeypatch):
    _reset_dedupe()
    monkeypatch.setenv("LARGE_CAP_RELVOL_FLOOR_SHADOW_ENABLED", "true")
    audit = AsyncMock()
    monkeypatch.setattr(ep_detector, "log_audit_event", audit)

    _run(_emit_large_cap_relvol_floor_shadow(_base_r(ticker="AAA"), _now_et()))
    _run(_emit_large_cap_relvol_floor_shadow(_base_r(ticker="BBB"), _now_et()))
    assert audit.await_count == 2


# ─── THE LINE — zero-live-mutation + non-skip pin ───────────────────────────────────────

def test_never_mutates_r(monkeypatch):
    """THE LINE pin: the shadow computation must leave the caller's `r` dict byte-identical
    — score_tier/grade/every downstream-read field is untouched regardless of whether the
    shadow event fires."""
    _reset_dedupe()
    monkeypatch.setenv("LARGE_CAP_RELVOL_FLOOR_SHADOW_ENABLED", "true")
    monkeypatch.setattr(ep_detector, "log_audit_event", AsyncMock())

    r = _base_r(fire_axes=["catalyst"], judge_rationale="strong 8-K")
    r_before = copy.deepcopy(r)
    _run(_emit_large_cap_relvol_floor_shadow(r, _now_et()))
    assert r == r_before


def test_alert_not_skipped_result_dict_shape_preserved(monkeypatch):
    """The alert dict returned to the caller (what the ORB-entry job reads) is the exact
    same object/keys whether or not the shadow fires — proving the alert proceeds exactly
    as it would have without this observer."""
    _reset_dedupe()
    monkeypatch.setenv("LARGE_CAP_RELVOL_FLOOR_SHADOW_ENABLED", "true")
    monkeypatch.setattr(ep_detector, "log_audit_event", AsyncMock())

    r = _base_r()
    keys_before = set(r.keys())
    _run(_emit_large_cap_relvol_floor_shadow(r, _now_et()))
    assert set(r.keys()) == keys_before
    assert r["score_tier"] == "HIGH"  # still HIGH -> still alerts + still ORB-enters


def test_never_raises_when_log_audit_event_itself_errors(monkeypatch):
    """SHADOW contract: even a bug in the audit writer must not propagate into the judge
    shadow / alert path. log_audit_event itself never raises in production (it swallows
    internally) but this pins the belt-and-suspenders wrap around the call site too."""
    _reset_dedupe()
    monkeypatch.setenv("LARGE_CAP_RELVOL_FLOOR_SHADOW_ENABLED", "true")
    monkeypatch.setattr(
        ep_detector, "log_audit_event", AsyncMock(side_effect=RuntimeError("db down")))

    r = _base_r()
    _run(_emit_large_cap_relvol_floor_shadow(r, _now_et()))  # must not raise
